import os
import sys
import ctypes
import customtkinter as ctk
from tkinter import simpledialog, messagebox
import sounddevice as sd

from .audio_engine import AudioRouterEngine, play_test_chime
from .config_manager import load_config, save_config, set_windows_autostart
from .tray_manager import TrayManager, ensure_icon_exists
from .sync_wizard import SyncWizardModal

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ModernAudioRouterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Windows Multi-Audio Router")

        # --- Consistent Windows Taskbar, Alt+Tab, and Window Icon ---
        icon_path = ensure_icon_exists()
        try:
            myappid = "audiorouter.multidevice.pro.1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        try:
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"[Icon Warning]: {e}")

        # --- Dynamic Monitor Centering ---
        app_width = 780
        app_height = 580
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int((screen_width / 2) - (app_width / 2))
        center_y = int((screen_height / 2) - (app_height / 2))
        self.geometry(f"{app_width}x{app_height}+{center_x}+{center_y}")
        self.minsize(700, 480)

        self.wasapi_idx = self._get_wasapi_index()
        self.engine = AudioRouterEngine(
            on_master_level=self._update_master_vu,
            on_device_level=self._update_device_vu,
            on_error=lambda err: self.after(0, self.stop_routing),
        )

        self.config_data = load_config()
        self.device_cards = {}
        self.last_known_devices = []

        self._setup_ui()
        self.refresh_devices()

        self.tray = TrayManager(self, on_quit_callback=self.safe_exit)
        self.tray.setup()
        self.protocol("WM_DELETE_WINDOW", self.tray.hide_window)

        self.after(4000, self._auto_poll_devices)

    def _get_wasapi_index(self):
        for idx, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                return idx
        messagebox.showerror("Error", "WASAPI host API not detected.")
        self.destroy()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header Frame
        header = ctk.CTkFrame(self, corner_radius=10, fg_color="#212121")
        header.grid(row=0, column=0, padx=14, pady=(12, 6), sticky="ew")
        header.grid_columnconfigure(3, weight=1)

        self.btn_refresh = ctk.CTkButton(
            header,
            text="↻ Rescan",
            width=90,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.refresh_devices,
        )
        self.btn_refresh.grid(row=0, column=0, padx=8, pady=8)

        ctk.CTkLabel(header, text="Buffer:", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=1, padx=(4, 2))
        self.cmb_buffer = ctk.CTkComboBox(
            header,
            values=["512 (Ultra-Low)", "1024 (Balanced)", "2048 (Stable)", "4096 (High)"],
            width=130,
            height=26,
            font=ctk.CTkFont(size=10),
        )
        self.cmb_buffer.set("1024 (Balanced)")
        self.cmb_buffer.grid(row=0, column=2, padx=4)

        # Options Checkboxes
        self.auto_mute_var = ctk.BooleanVar(value=self.config_data.get("auto_mute_speakers", False))
        self.chk_auto_mute = ctk.CTkCheckBox(
            header,
            text="Auto-Mute Speakers",
            font=ctk.CTkFont(size=11),
            variable=self.auto_mute_var,
            command=self._on_setting_changed,
        )
        self.chk_auto_mute.grid(row=0, column=4, padx=8)

        self.autostart_var = ctk.BooleanVar(value=self.config_data.get("start_on_boot", False))
        self.chk_autostart = ctk.CTkCheckBox(
            header,
            text="Start on Boot",
            font=ctk.CTkFont(size=11),
            variable=self.autostart_var,
            command=self._toggle_autostart,
        )
        self.chk_autostart.grid(row=0, column=5, padx=8)

        self.lbl_status = ctk.CTkLabel(
            header,
            text="● Inactive",
            text_color="#888888",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.lbl_status.grid(row=0, column=6, padx=14, pady=8)

        # Master VU Signal Meter
        vu_frame = ctk.CTkFrame(self, corner_radius=8, fg_color="#181818")
        vu_frame.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")
        vu_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            vu_frame, text="Signal", font=ctk.CTkFont(size=11), text_color="#A0A0A0"
        ).grid(row=0, column=0, padx=(10, 8), pady=4)

        self.master_vu = ctk.CTkProgressBar(
            vu_frame, height=6, corner_radius=3, progress_color="#1f6aa5"
        )
        self.master_vu.grid(row=0, column=1, padx=(0, 14), pady=4, sticky="ew")
        self.master_vu.set(0.0)

        # Scrollable Device Container
        self.scrollable = ctk.CTkScrollableFrame(
            self,
            label_text="Available Playback Endpoints",
            label_font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            fg_color="#181818",
        )
        self.scrollable.grid(row=2, column=0, padx=14, pady=4, sticky="nsew")
        self.scrollable.grid_columnconfigure(0, weight=1)

        # Footer Action Area
        footer = ctk.CTkFrame(self, corner_radius=10, fg_color="#212121")
        footer.grid(row=3, column=0, padx=14, pady=(6, 12), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.btn_toggle = ctk.CTkButton(
            footer,
            text="Start Audio Splitting",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.toggle_routing,
        )
        self.btn_toggle.grid(row=0, column=0, padx=10, pady=8, sticky="ew")

    def _toggle_autostart(self):
        set_windows_autostart(self.autostart_var.get())
        self._on_setting_changed()

    def _update_master_vu(self, rms):
        level = min(1.0, rms * 4.5)
        self.after(0, lambda: self.master_vu.set(level))

    def _update_device_vu(self, dev_id, rms):
        if dev_id in self.device_cards:
            meter = self.device_cards[dev_id]["vu_meter"]
            level = min(1.0, rms * 4.5)
            self.after(0, lambda: meter.set(level))

    def refresh_devices(self):
        if self.engine.is_routing:
            return

        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass

        for w in self.scrollable.winfo_children():
            w.destroy()

        self.device_cards.clear()
        devices = sd.query_devices()
        self.last_known_devices = [d["name"] for d in devices]
        default_out = sd.default.device[1]
        bt_keys = ["bluetooth", "hands-free", "airpods", "buds", "wireless", "headset", "headphones"]

        ignored_names = [
            "microsoft sound mapper",
            "primary sound driver",
            "default audio device",
            "primary sound capture driver",
        ]

        seen_names = set()
        row_idx = 0
        saved_devices = self.config_data.get("devices", {})

        for idx, dev in enumerate(devices):
            name = dev["name"].strip()
            name_lower = name.lower()

            if dev["max_output_channels"] <= 0 or any(ign in name_lower for ign in ignored_names):
                continue

            if dev["hostapi"] != self.wasapi_idx:
                continue

            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            channels = min(2, dev["max_output_channels"])
            connected = self.engine.probe_device(idx, channels)
            is_default = (idx == default_out)
            is_speaker = not any(k in name_lower for k in bt_keys)

            saved = saved_devices.get(
                name, {"selected": False, "volume": 1.0, "delay": 0, "pan": 0.0, "muted": False, "alias": ""}
            )

            display_name = saved.get("alias") if saved.get("alias") else name

            card = ctk.CTkFrame(
                self.scrollable,
                corner_radius=8,
                fg_color="#262626" if connected else "#1C1C1C",
                border_width=1,
                border_color="#333333" if connected else "#242424",
            )
            card.grid(row=row_idx, column=0, padx=2, pady=4, sticky="ew")
            card.grid_columnconfigure(1, weight=1)
            row_idx += 1

            chk_var = ctk.BooleanVar(value=saved["selected"] if connected else False)
            vol_var = ctk.DoubleVar(value=saved["volume"])
            delay_var = ctk.IntVar(value=saved["delay"])
            pan_var = ctk.DoubleVar(value=saved.get("pan", 0.0))
            muted_var = ctk.BooleanVar(value=saved.get("muted", False))

            badge = "🔊 Speaker" if is_speaker else "🎧 Bluetooth"
            if is_default:
                badge += " • Default"
            if not connected:
                badge += " (Disconnected)"

            head_row = ctk.CTkFrame(card, fg_color="transparent")
            head_row.grid(row=0, column=0, columnspan=3, padx=10, pady=(8, 4), sticky="ew")
            head_row.grid_columnconfigure(1, weight=1)

            chk = ctk.CTkSwitch(
                head_row,
                text=f"{badge}  {display_name}",
                font=ctk.CTkFont(size=11, weight="bold" if connected else "normal"),
                variable=chk_var,
                state="normal" if connected else "disabled",
                command=self._on_setting_changed,
            )
            chk.grid(row=0, column=0, sticky="w")

            btn_rename = ctk.CTkButton(
                head_row,
                text="✏",
                width=24,
                height=20,
                font=ctk.CTkFont(size=10),
                fg_color="#333333",
                hover_color="#444444",
                command=lambda orig=name, c=chk, b=badge: self._edit_device_nickname(orig, c, b),
            )
            btn_rename.grid(row=0, column=1, padx=(6, 0), sticky="w")

            dev_vu = ctk.CTkProgressBar(head_row, width=60, height=4, corner_radius=2, progress_color="#00BCF2")
            dev_vu.grid(row=0, column=2, padx=6, sticky="e")
            dev_vu.set(0.0)

            btn_sync = ctk.CTkButton(
                head_row,
                text="⚡ Sync",
                width=54,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10),
                fg_color="#005B94",
                hover_color="#0072B8",
                state="normal" if connected else "disabled",
                command=lambda i=idx, n=display_name, d=delay_var: self._open_sync_wizard(i, n, d),
            )
            btn_sync.grid(row=0, column=3, padx=(0, 4), sticky="e")

            btn_test = ctk.CTkButton(
                head_row,
                text="♪ Test",
                width=50,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10),
                fg_color="#3A3A3A",
                hover_color="#4A4A4A",
                state="normal" if connected else "disabled",
                command=lambda i=idx, ch=channels: play_test_chime(i, ch),
            )
            btn_test.grid(row=0, column=4, sticky="e")

            ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
            ctrl_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 8), sticky="ew")
            ctrl_frame.grid_columnconfigure(1, weight=1)
            ctrl_frame.grid_columnconfigure(3, weight=1)
            ctrl_frame.grid_columnconfigure(5, weight=1)

            btn_mute = ctk.CTkButton(
                ctrl_frame,
                text="🔇" if muted_var.get() else "🔊",
                width=24,
                height=22,
                fg_color="transparent",
                hover_color="#333333",
                font=ctk.CTkFont(size=12),
                command=lambda i=idx, m=muted_var: self._toggle_device_mute(i, m),
            )
            btn_mute.grid(row=0, column=0, padx=(0, 4))

            vol_slider = ctk.CTkSlider(
                ctrl_frame,
                from_=0.0,
                to=1.5,
                variable=vol_var,
                height=12,
                width=85,
                state="normal" if connected else "disabled",
                command=lambda val, i=idx: self._on_param_slider(i),
            )
            vol_slider.grid(row=0, column=1, padx=(0, 8), sticky="ew")
            vol_slider.bind("<Double-Button-1>", lambda e, v=vol_var, i=idx: self._reset_slider(v, 1.0, i))

            ctk.CTkLabel(ctrl_frame, text="Bal", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=2, padx=(0, 4))
            pan_slider = ctk.CTkSlider(
                ctrl_frame,
                from_=-1.0,
                to=1.0,
                variable=pan_var,
                height=12,
                width=65,
                state="normal" if connected else "disabled",
                command=lambda val, i=idx: self._on_param_slider(i),
            )
            pan_slider.grid(row=0, column=3, padx=(0, 8), sticky="ew")
            pan_slider.bind("<Double-Button-1>", lambda e, v=pan_var, i=idx: self._reset_slider(v, 0.0, i))

            ctk.CTkLabel(ctrl_frame, text="Delay", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=4, padx=(0, 4))
            lbl_delay = ctk.CTkLabel(
                ctrl_frame, text=f"{delay_var.get()}ms", font=ctk.CTkFont(size=10, weight="bold"), text_color="#00BCF2", width=36
            )
            lbl_delay.grid(row=0, column=5, padx=(0, 4))

            delay_slider = ctk.CTkSlider(
                ctrl_frame,
                from_=0,
                to=300,
                variable=delay_var,
                height=12,
                width=85,
                state="normal" if connected else "disabled",
                command=lambda val, i=idx, l=lbl_delay, v=delay_var: self._on_delay_slider(i, l, v),
            )
            delay_slider.grid(row=0, column=6, padx=(0, 6), sticky="ew")

            preset_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
            preset_frame.grid(row=0, column=7, sticky="e")
            for ms, label in [(0, "0ms"), (120, "120ms"), (200, "200ms")]:
                ctk.CTkButton(
                    preset_frame,
                    text=label,
                    width=34,
                    height=18,
                    corner_radius=4,
                    font=ctk.CTkFont(size=9),
                    fg_color="#333333",
                    hover_color="#444444",
                    state="normal" if connected else "disabled",
                    command=lambda v=ms, i=idx, l=lbl_delay, d=delay_var: self._apply_preset(i, l, d, v),
                ).pack(side="left", padx=1)

            self.device_cards[idx] = {
                "name": name,
                "display_name": display_name,
                "is_speaker": is_speaker,
                "channels": channels,
                "connected": connected,
                "selected": chk_var,
                "volume": vol_var,
                "delay": delay_var,
                "pan": pan_var,
                "muted": muted_var,
                "mute_btn": btn_mute,
                "vu_meter": dev_vu,
            }

    def _reset_slider(self, var, value, device_id):
        var.set(value)
        self._on_param_slider(device_id)

    def _toggle_device_mute(self, device_id, muted_var):
        new_state = not muted_var.get()
        muted_var.set(new_state)
        btn = self.device_cards[device_id]["mute_btn"]
        btn.configure(text="🔇" if new_state else "🔊")
        self._on_param_slider(device_id)

    def _edit_device_nickname(self, orig_name, switch_widget, badge):
        new_alias = simpledialog.askstring("Device Nickname", f"Enter custom alias for:\n{orig_name}")
        if new_alias is not None:
            new_alias = new_alias.strip()
            switch_widget.configure(text=f"{badge}  {new_alias if new_alias else orig_name}")
            if "devices" not in self.config_data:
                self.config_data["devices"] = {}
            if orig_name not in self.config_data["devices"]:
                self.config_data["devices"][orig_name] = {}
            self.config_data["devices"][orig_name]["alias"] = new_alias
            save_config(self.config_data)

    def _open_sync_wizard(self, device_id, device_name, delay_var):
        def _on_sync_done(ms):
            delay_var.set(ms)
            self._on_param_slider(device_id)
            self.refresh_devices()

        SyncWizardModal(self, device_id, device_name, _on_sync_done)

    def _apply_preset(self, device_id, label, delay_var, value):
        delay_var.set(value)
        label.configure(text=f"{value}ms")
        self._on_param_slider(device_id)

    def _on_param_slider(self, device_id):
        ctrls = self.device_cards[device_id]
        self.engine.update_worker_params(
            device_id,
            ctrls["volume"].get(),
            ctrls["delay"].get(),
            ctrls["pan"].get(),
            ctrls["muted"].get(),
        )
        self._on_setting_changed()

    def _on_delay_slider(self, device_id, label, delay_var):
        val = int(delay_var.get())
        label.configure(text=f"{val}ms")
        self._on_param_slider(device_id)

    def _on_setting_changed(self):
        if "devices" not in self.config_data:
            self.config_data["devices"] = {}

        for ctrls in self.device_cards.values():
            name = ctrls["name"]
            existing_alias = self.config_data["devices"].get(name, {}).get("alias", "")
            self.config_data["devices"][name] = {
                "selected": ctrls["selected"].get(),
                "volume": ctrls["volume"].get(),
                "delay": ctrls["delay"].get(),
                "pan": ctrls["pan"].get(),
                "muted": ctrls["muted"].get(),
                "alias": existing_alias,
            }

        self.config_data["auto_mute_speakers"] = self.auto_mute_var.get()
        self.config_data["start_on_boot"] = self.autostart_var.get()
        save_config(self.config_data)

    def _auto_poll_devices(self):
        if not self.engine.is_routing:
            current_names = [d["name"] for d in sd.query_devices()]
            if current_names != self.last_known_devices:
                self.refresh_devices()
        self.after(4000, self._auto_poll_devices)

    def toggle_routing(self):
        if self.engine.is_routing:
            self.stop_routing()
        else:
            self.start_routing()

    def start_routing(self):
        targets = []
        headphones_active = 0

        for ctrls in self.device_cards.values():
            if ctrls["selected"].get() and ctrls["connected"] and not ctrls["is_speaker"]:
                headphones_active += 1

        for idx, ctrls in self.device_cards.items():
            if ctrls["selected"].get() and ctrls["connected"]:
                is_muted = ctrls["muted"].get()
                if self.auto_mute_var.get() and ctrls["is_speaker"] and headphones_active >= 2:
                    is_muted = True

                targets.append({
                    "id": idx,
                    "name": ctrls["name"],
                    "channels": ctrls["channels"],
                    "vol": ctrls["volume"].get(),
                    "delay": ctrls["delay"].get(),
                    "pan": ctrls["pan"].get(),
                    "muted": is_muted,
                })

        if not targets:
            messagebox.showwarning("Warning", "Select at least one connected output device.")
            return

        buf_str = self.cmb_buffer.get().split()[0]
        block_size = int(buf_str) if buf_str.isdigit() else 1024

        self.engine.start(targets, block_size=block_size)
        self.lbl_status.configure(text="● Active", text_color="#107C41")
        self.btn_toggle.configure(text="Stop Audio Splitting", fg_color="#C42B1C", hover_color="#B32417")
        self.btn_refresh.configure(state="disabled")
        self.cmb_buffer.configure(state="disabled")

    def stop_routing(self):
        self.engine.stop()
        self.lbl_status.configure(text="● Inactive", text_color="#888888")
        self.btn_toggle.configure(text="Start Audio Splitting", fg_color="#1f6aa5", hover_color="#144870")
        self.btn_refresh.configure(state="normal")
        self.cmb_buffer.configure(state="normal")
        self.master_vu.set(0.0)
        for card in self.device_cards.values():
            card["vu_meter"].set(0.0)

    def safe_exit(self):
        self.stop_routing()
        self._on_setting_changed()
        self.destroy()
        sys.exit(0)