import os
import sys
import ctypes
import customtkinter as ctk
from tkinter import messagebox
from PIL import ImageTk
import sounddevice as sd
import keyboard

from .audio_engine import AudioRouterEngine, play_test_chime
from .config_manager import load_config, save_config
from .tray_manager import TrayManager, generate_app_icon

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ModernAudioRouterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Windows Multi-Audio Router")

        # Set taskbar icon explicitly in Windows
        try:
            myappid = "audiorouter.multidevice.pro.1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            self.icon_image = ImageTk.PhotoImage(generate_app_icon())
            self.iconphoto(False, self.icon_image)
        except Exception:
            pass

        # --- Dynamic Monitor Centering (Compact Dimensions) ---
        app_width = 760
        app_height = 580
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int((screen_width / 2) - (app_width / 2))
        center_y = int((screen_height / 2) - (app_height / 2))
        self.geometry(f"{app_width}x{app_height}+{center_x}+{center_y}")
        self.minsize(680, 480)

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

        # System Tray Initialization
        self.tray = TrayManager(self, on_quit_callback=self.safe_exit)
        self.tray.setup()
        self.protocol("WM_DELETE_WINDOW", self.tray.hide_window)

        # Global Hotkey (Ctrl + Alt + S to start/stop audio routing globally)
        try:
            keyboard.add_hotkey("ctrl+alt+s", lambda: self.after(0, self.toggle_routing))
        except Exception as e:
            print(f"[Hotkey Warning] Could not register hotkey: {e}")

        # Periodic check for paired/disconnected Bluetooth endpoints
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

        # 1. Header Frame
        header = ctk.CTkFrame(self, corner_radius=10, fg_color="#212121")
        header.grid(row=0, column=0, padx=14, pady=(12, 6), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        self.btn_refresh = ctk.CTkButton(
            header,
            text="↻ Rescan Devices",
            width=110,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.refresh_devices,
        )
        self.btn_refresh.grid(row=0, column=0, padx=10, pady=8)

        # Buffer Dropdown Selector
        buffer_frame = ctk.CTkFrame(header, fg_color="transparent")
        buffer_frame.grid(row=0, column=1, padx=6, sticky="w")

        ctk.CTkLabel(buffer_frame, text="Buffer:", font=ctk.CTkFont(size=10), text_color="#A0A0A0").pack(side="left", padx=4)
        self.cmb_buffer = ctk.CTkComboBox(
            buffer_frame,
            values=["512 (Ultra-Low)", "1024 (Balanced)", "2048 (Stable)", "4096 (High Buffer)"],
            width=140,
            height=26,
            font=ctk.CTkFont(size=10),
        )
        self.cmb_buffer.set("1024 (Balanced)")
        self.cmb_buffer.pack(side="left")

        # Global Hotkey Tip Label
        ctk.CTkLabel(
            header, text="[Ctrl+Alt+S]", font=ctk.CTkFont(size=10), text_color="#666666"
        ).grid(row=0, column=2, padx=4)

        self.lbl_status = ctk.CTkLabel(
            header, text="● Inactive", text_color="#888888", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_status.grid(row=0, column=3, padx=14, pady=8)

        # 2. Master VU Meter
        vu_frame = ctk.CTkFrame(self, corner_radius=8, fg_color="#181818")
        vu_frame.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")
        vu_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(vu_frame, text="Master Signal", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=0, padx=(10, 8), pady=4)

        self.master_vu = ctk.CTkProgressBar(vu_frame, height=6, corner_radius=3, progress_color="#00BCF2")
        self.master_vu.grid(row=0, column=1, padx=(0, 14), pady=4, sticky="ew")
        self.master_vu.set(0.0)

        # 3. Scrollable Device Target Container
        self.scrollable = ctk.CTkScrollableFrame(
            self,
            label_text="Active Playback Targets",
            label_font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            fg_color="#181818",
        )
        self.scrollable.grid(row=2, column=0, padx=14, pady=4, sticky="nsew")
        self.scrollable.grid_columnconfigure(0, weight=1)

        # 4. Footer
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

    def _update_master_vu(self, rms):
        val = min(1.0, rms * 4.5)
        self.after(0, lambda: self.master_vu.set(val))

    def _update_device_vu(self, dev_id, rms):
        if dev_id in self.device_cards:
            meter = self.device_cards[dev_id]["vu_meter"]
            val = min(1.0, rms * 4.5)
            self.after(0, lambda: meter.set(val))

    def refresh_devices(self):
        if self.engine.is_routing:
            return

        # 1. Force PortAudio to re-enumerate Windows audio endpoints
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass

        for w in self.scrollable.winfo_children():
            w.destroy()

        self.device_cards.clear()

        # 2. Query all host APIs and devices
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        self.last_known_devices = [d["name"] for d in devices]
        default_out = sd.default.device[1]

        bt_keys = ["bluetooth", "hands-free", "airpods", "buds", "wireless", "headset", "headphones"]
        
        seen_names = set()
        row_idx = 0

        for idx, dev in enumerate(devices):
            # Only pick playback endpoints
            if dev["max_output_channels"] <= 0:
                continue

            name = dev["name"]
            api_name = hostapis[dev["hostapi"]]["name"]

            # Prefer WASAPI if duplicates exist, but accept MME/DirectSound if it's the only one
            unique_key = f"{name}_{dev['max_output_channels']}"
            if "WASAPI" in api_name:
                pass  # Preferred
            elif unique_key in seen_names:
                continue

            seen_names.add(unique_key)
            channels = min(2, dev["max_output_channels"])
            connected = self.engine.probe_device(idx, channels)
            is_default = (idx == default_out)

            saved = self.config_data.get(
                name, {"selected": False, "volume": 1.0, "delay": 0, "pan": 0.0}
            )

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

            badge = "🎧 Bluetooth" if any(k in name.lower() for k in bt_keys) else "🔊 Speaker"
            if is_default:
                badge += " • Default"
            if not connected:
                badge += " (Disconnected)"

            # Switch & Tone
            chk = ctk.CTkSwitch(
                card,
                text=f"{badge}  {name}",
                font=ctk.CTkFont(size=11, weight="bold" if connected else "normal"),
                variable=chk_var,
                state="normal" if connected else "disabled",
                command=self._on_setting_changed,
            )
            chk.grid(row=0, column=0, padx=10, pady=(8, 4), sticky="w")

            dev_vu = ctk.CTkProgressBar(card, width=70, height=4, corner_radius=2, progress_color="#00BCF2")
            dev_vu.grid(row=0, column=1, padx=6, pady=(8, 4), sticky="e")
            dev_vu.set(0.0)

            btn_test = ctk.CTkButton(
                card,
                text="♪ Test",
                width=60,
                height=22,
                corner_radius=6,
                font=ctk.CTkFont(size=10),
                fg_color="#3A3A3A",
                hover_color="#4A4A4A",
                state="normal" if connected else "disabled",
                command=lambda i=idx, ch=channels: play_test_chime(i, ch),
            )
            btn_test.grid(row=0, column=2, padx=10, pady=(8, 4), sticky="e")

            # Sliders
            ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
            ctrl_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 8), sticky="ew")
            ctrl_frame.grid_columnconfigure(1, weight=1)
            ctrl_frame.grid_columnconfigure(3, weight=1)
            ctrl_frame.grid_columnconfigure(5, weight=1)

            # Vol
            ctk.CTkLabel(ctrl_frame, text="Vol", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=0, padx=(0, 4))
            vol_slider = ctk.CTkSlider(
                ctrl_frame,
                from_=0.0,
                to=1.5,
                variable=vol_var,
                height=12,
                width=90,
                state="normal" if connected else "disabled",
                command=lambda val, i=idx: self._on_param_slider(i),
            )
            vol_slider.grid(row=0, column=1, padx=(0, 8), sticky="ew")

            # Balance
            ctk.CTkLabel(ctrl_frame, text="Bal", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=2, padx=(0, 4))
            pan_slider = ctk.CTkSlider(
                ctrl_frame,
                from_=-1.0,
                to=1.0,
                variable=pan_var,
                height=12,
                width=70,
                state="normal" if connected else "disabled",
                command=lambda val, i=idx: self._on_param_slider(i),
            )
            pan_slider.grid(row=0, column=3, padx=(0, 8), sticky="ew")

            # Delay
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
                width=90,
                state="normal" if connected else "disabled",
                command=lambda val, i=idx, l=lbl_delay, v=delay_var: self._on_delay_slider(i, l, v),
            )
            delay_slider.grid(row=0, column=6, padx=(0, 6), sticky="ew")

            # Latency Presets
            preset_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
            preset_frame.grid(row=0, column=7, sticky="e")

            for ms, label in [(0, "0ms"), (120, "120ms"), (200, "200ms")]:
                btn_p = ctk.CTkButton(
                    preset_frame,
                    text=label,
                    width=36,
                    height=18,
                    corner_radius=4,
                    font=ctk.CTkFont(size=9),
                    fg_color="#333333",
                    hover_color="#444444",
                    state="normal" if connected else "disabled",
                    command=lambda v=ms, i=idx, l=lbl_delay, d=delay_var: self._apply_preset(i, l, d, v),
                )
                btn_p.pack(side="left", padx=1)

            self.device_cards[idx] = {
                "name": name,
                "channels": channels,
                "connected": connected,
                "selected": chk_var,
                "volume": vol_var,
                "delay": delay_var,
                "pan": pan_var,
                "vu_meter": dev_vu,
            }
        if self.engine.is_routing:
            return

        for w in self.scrollable.winfo_children():
            w.destroy()

        self.device_cards.clear()
        devices = sd.query_devices()
        self.last_known_devices = [d["name"] for d in devices]
        default_out = sd.default.device[1]
        bt_keys = ["bluetooth", "hands-free", "airpods", "buds", "wireless", "headset", "headphones"]

        row_idx = 0
        for idx, dev in enumerate(devices):
            if dev["hostapi"] == self.wasapi_idx and dev["max_output_channels"] > 0:
                name = dev["name"]
                channels = min(2, dev["max_output_channels"])
                connected = self.engine.probe_device(idx, channels)
                is_default = idx == default_out

                saved = self.config_data.get(
                    name, {"selected": False, "volume": 1.0, "delay": 0, "pan": 0.0}
                )

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

                badge = "🎧 Bluetooth" if any(k in name.lower() for k in bt_keys) else "🔊 Speaker"
                if is_default:
                    badge += " • Default"
                if not connected:
                    badge += " (Disconnected)"

                # Row 0: Switch, Mini VU bar, Test Tone Button
                chk = ctk.CTkSwitch(
                    card,
                    text=f"{badge}  {name}",
                    font=ctk.CTkFont(size=11, weight="bold" if connected else "normal"),
                    variable=chk_var,
                    state="normal" if connected else "disabled",
                    command=self._on_setting_changed,
                )
                chk.grid(row=0, column=0, padx=10, pady=(8, 4), sticky="w")

                dev_vu = ctk.CTkProgressBar(card, width=70, height=4, corner_radius=2, progress_color="#00BCF2")
                dev_vu.grid(row=0, column=1, padx=6, pady=(8, 4), sticky="e")
                dev_vu.set(0.0)

                btn_test = ctk.CTkButton(
                    card,
                    text="♪ Test",
                    width=60,
                    height=22,
                    corner_radius=6,
                    font=ctk.CTkFont(size=10),
                    fg_color="#3A3A3A",
                    hover_color="#4A4A4A",
                    state="normal" if connected else "disabled",
                    command=lambda i=idx, ch=channels: play_test_chime(i, ch),
                )
                btn_test.grid(row=0, column=2, padx=10, pady=(8, 4), sticky="e")

                # Row 1: Volume, Pan Balance, and Latency Presets
                ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
                ctrl_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 8), sticky="ew")
                ctrl_frame.grid_columnconfigure(1, weight=1)
                ctrl_frame.grid_columnconfigure(3, weight=1)
                ctrl_frame.grid_columnconfigure(5, weight=1)

                # Volume
                ctk.CTkLabel(ctrl_frame, text="Vol", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=0, padx=(0, 4))
                vol_slider = ctk.CTkSlider(
                    ctrl_frame,
                    from_=0.0,
                    to=1.5,
                    variable=vol_var,
                    height=12,
                    width=90,
                    state="normal" if connected else "disabled",
                    command=lambda val, i=idx: self._on_param_slider(i),
                )
                vol_slider.grid(row=0, column=1, padx=(0, 8), sticky="ew")

                # Balance (L/R)
                ctk.CTkLabel(ctrl_frame, text="Bal", font=ctk.CTkFont(size=10), text_color="#A0A0A0").grid(row=0, column=2, padx=(0, 4))
                pan_slider = ctk.CTkSlider(
                    ctrl_frame,
                    from_=-1.0,
                    to=1.0,
                    variable=pan_var,
                    height=12,
                    width=70,
                    state="normal" if connected else "disabled",
                    command=lambda val, i=idx: self._on_param_slider(i),
                )
                pan_slider.grid(row=0, column=3, padx=(0, 8), sticky="ew")

                # Delay ms
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
                    width=90,
                    state="normal" if connected else "disabled",
                    command=lambda val, i=idx, l=lbl_delay, v=delay_var: self._on_delay_slider(i, l, v),
                )
                delay_slider.grid(row=0, column=6, padx=(0, 6), sticky="ew")

                # Latency Presets
                preset_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
                preset_frame.grid(row=0, column=7, sticky="e")

                for ms, label in [(0, "0ms"), (120, "120ms"), (200, "200ms")]:
                    btn_p = ctk.CTkButton(
                        preset_frame,
                        text=label,
                        width=36,
                        height=18,
                        corner_radius=4,
                        font=ctk.CTkFont(size=9),
                        fg_color="#333333",
                        hover_color="#444444",
                        state="normal" if connected else "disabled",
                        command=lambda v=ms, i=idx, l=lbl_delay, d=delay_var: self._apply_preset(i, l, d, v),
                    )
                    btn_p.pack(side="left", padx=1)

                self.device_cards[idx] = {
                    "name": name,
                    "channels": channels,
                    "connected": connected,
                    "selected": chk_var,
                    "volume": vol_var,
                    "delay": delay_var,
                    "pan": pan_var,
                    "vu_meter": dev_vu,
                }

    def _apply_preset(self, device_id, label, delay_var, value):
        delay_var.set(value)
        label.configure(text=f"{value}ms")
        self._on_param_slider(device_id)

    def _on_param_slider(self, device_id):
        ctrls = self.device_cards[device_id]
        vol = ctrls["volume"].get()
        delay = ctrls["delay"].get()
        pan = ctrls["pan"].get()
        self.engine.update_worker_params(device_id, vol, delay, pan)
        self._on_setting_changed()

    def _on_delay_slider(self, device_id, label, delay_var):
        val = int(delay_var.get())
        label.configure(text=f"{val}ms")
        self._on_param_slider(device_id)

    def _on_setting_changed(self):
        for ctrls in self.device_cards.values():
            self.config_data[ctrls["name"]] = {
                "selected": ctrls["selected"].get(),
                "volume": ctrls["volume"].get(),
                "delay": ctrls["delay"].get(),
                "pan": ctrls["pan"].get(),
            }
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
        for idx, ctrls in self.device_cards.items():
            if ctrls["selected"].get() and ctrls["connected"]:
                targets.append({
                    "id": idx,
                    "name": ctrls["name"],
                    "channels": ctrls["channels"],
                    "vol": ctrls["volume"].get(),
                    "delay": ctrls["delay"].get(),
                    "pan": ctrls["pan"].get(),
                })

        if not targets:
            messagebox.showwarning("Warning", "Select at least one connected output device.")
            return

        # Parse selected buffer size
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