import customtkinter as ctk
from tkinter import messagebox
import sounddevice as sd
from .audio_engine import AudioRouterEngine, play_test_chime
from .config_manager import load_config, save_config
from .tray_manager import TrayManager

# Set CustomTkinter global theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ModernAudioRouterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Windows Multi-Audio Router")
        self.geometry("820x680")
        self.minsize(740, 520)

        self.wasapi_idx = self._get_wasapi_index()
        self.engine = AudioRouterEngine(
            on_level_callback=self._update_master_vu,
            on_error_callback=lambda err: self.after(0, self.stop_routing),
        )

        self.config_data = load_config()
        self.device_cards = {}
        self.last_known_devices = []

        self._setup_ui()
        self.refresh_devices()

        # Tray Setup
        self.tray = TrayManager(self, on_quit_callback=self.safe_exit)
        self.tray.setup()
        self.protocol("WM_DELETE_WINDOW", self.tray.hide_window)

        # Background auto-poll for new/removed devices every 4 seconds
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
        header = ctk.CTkFrame(self, corner_radius=12, fg_color="#212121")
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        self.btn_refresh = ctk.CTkButton(
            header,
            text="↻ Rescan Devices",
            width=130,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.refresh_devices,
        )
        self.btn_refresh.grid(row=0, column=0, padx=12, pady=10)

        self.lbl_status = ctk.CTkLabel(
            header,
            text="● Inactive",
            text_color="#888888",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.lbl_status.grid(row=0, column=2, padx=16, pady=10)

        # Master VU Signal Meter
        vu_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#181818")
        vu_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        vu_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            vu_frame, text="Master Signal", font=ctk.CTkFont(size=11), text_color="#A0A0A0"
        ).grid(row=0, column=0, padx=(12, 8), pady=6)

        self.master_vu = ctk.CTkProgressBar(
            vu_frame, height=8, corner_radius=4, progress_color="#1f6aa5"
        )
        self.master_vu.grid(row=0, column=1, padx=(0, 16), pady=6, sticky="ew")
        self.master_vu.set(0.0)

        # Scrollable Device Container
        self.scrollable = ctk.CTkScrollableFrame(
            self,
            label_text="Available Playback Endpoints",
            label_font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=12,
            fg_color="#181818",
        )
        self.scrollable.grid(row=2, column=0, padx=16, pady=4, sticky="nsew")
        self.scrollable.grid_columnconfigure(0, weight=1)

        # Footer Action Area
        footer = ctk.CTkFrame(self, corner_radius=12, fg_color="#212121")
        footer.grid(row=3, column=0, padx=16, pady=12, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.btn_toggle = ctk.CTkButton(
            footer,
            text="Start Audio Splitting",
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.toggle_routing,
        )
        self.btn_toggle.grid(row=0, column=0, padx=12, pady=10, sticky="ew")

    def _update_master_vu(self, rms):
        # Soft normalized level scaling
        level = min(1.0, rms * 4.5)
        self.after(0, lambda: self.master_vu.set(level))

    def refresh_devices(self):
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
                    name, {"selected": False, "volume": 1.0, "delay": 0}
                )

                # Modern Device Card
                card = ctk.CTkFrame(
                    self.scrollable,
                    corner_radius=10,
                    fg_color="#262626" if connected else "#1C1C1C",
                    border_width=1,
                    border_color="#333333" if connected else "#242424",
                )
                card.grid(row=row_idx, column=0, padx=4, pady=4, sticky="ew")
                card.grid_columnconfigure(1, weight=1)
                row_idx += 1

                # Variables
                chk_var = ctk.BooleanVar(value=saved["selected"] if connected else False)
                vol_var = ctk.DoubleVar(value=saved["volume"])
                delay_var = ctk.IntVar(value=saved["delay"])

                # Badge Construction
                badge = "🎧 Bluetooth" if any(k in name.lower() for k in bt_keys) else "🔊 Speaker"
                if is_default:
                    badge += " • Default"
                if not connected:
                    badge += " (Disconnected)"

                # Top Row: Check Switch and Test Button
                chk = ctk.CTkSwitch(
                    card,
                    text=f"{badge}  {name}",
                    font=ctk.CTkFont(size=12, weight="bold" if connected else "normal"),
                    variable=chk_var,
                    state="normal" if connected else "disabled",
                    command=self._on_setting_changed,
                )
                chk.grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

                btn_test = ctk.CTkButton(
                    card,
                    text="♪ Test Tone",
                    width=86,
                    height=26,
                    corner_radius=6,
                    font=ctk.CTkFont(size=11),
                    fg_color="#3A3A3A",
                    hover_color="#4A4A4A",
                    state="normal" if connected else "disabled",
                    command=lambda i=idx, ch=channels: play_test_chime(i, ch),
                )
                btn_test.grid(row=0, column=2, padx=12, pady=(10, 6), sticky="e")

                # Bottom Controls: Volume + Latency Presets
                ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
                ctrl_frame.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 10), sticky="ew")
                ctrl_frame.grid_columnconfigure(1, weight=1)
                ctrl_frame.grid_columnconfigure(4, weight=1)

                # Volume slider
                ctk.CTkLabel(
                    ctrl_frame, text="Vol", font=ctk.CTkFont(size=11), text_color="#A0A0A0"
                ).grid(row=0, column=0, padx=(0, 6))

                vol_slider = ctk.CTkSlider(
                    ctrl_frame,
                    from_=0.0,
                    to=1.5,
                    variable=vol_var,
                    height=14,
                    width=130,
                    state="normal" if connected else "disabled",
                    command=lambda val, i=idx: self._on_param_slider(i),
                )
                vol_slider.grid(row=0, column=1, padx=(0, 16), sticky="ew")

                # Latency sync slider + readout
                ctk.CTkLabel(
                    ctrl_frame, text="Delay", font=ctk.CTkFont(size=11), text_color="#A0A0A0"
                ).grid(row=0, column=2, padx=(0, 6))

                lbl_delay = ctk.CTkLabel(
                    ctrl_frame,
                    text=f"{delay_var.get()}ms",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#1f6aa5",
                    width=42,
                )
                lbl_delay.grid(row=0, column=3, padx=(0, 6))

                delay_slider = ctk.CTkSlider(
                    ctrl_frame,
                    from_=0,
                    to=300,
                    variable=delay_var,
                    height=14,
                    width=130,
                    state="normal" if connected else "disabled",
                    command=lambda val, i=idx, l=lbl_delay, v=delay_var: self._on_delay_slider(
                        i, l, v
                    ),
                )
                delay_slider.grid(row=0, column=4, padx=(0, 8), sticky="ew")

                # Fast Sync Presets
                preset_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
                preset_frame.grid(row=0, column=5, sticky="e")

                for ms, label in [(0, "0ms"), (120, "120ms"), (200, "200ms")]:
                    btn_p = ctk.CTkButton(
                        preset_frame,
                        text=label,
                        width=42,
                        height=20,
                        corner_radius=4,
                        font=ctk.CTkFont(size=9),
                        fg_color="#333333",
                        hover_color="#444444",
                        state="normal" if connected else "disabled",
                        command=lambda v=ms, i=idx, l=lbl_delay, d=delay_var: self._apply_preset(
                            i, l, d, v
                        ),
                    )
                    btn_p.pack(side="left", padx=2)

                self.device_cards[idx] = {
                    "name": name,
                    "channels": channels,
                    "connected": connected,
                    "selected": chk_var,
                    "volume": vol_var,
                    "delay": delay_var,
                }

    def _apply_preset(self, device_id, label, delay_var, value):
        delay_var.set(value)
        label.configure(text=f"{value}ms")
        self._on_param_slider(device_id)

    def _on_param_slider(self, device_id):
        ctrls = self.device_cards[device_id]
        vol = ctrls["volume"].get()
        delay = ctrls["delay"].get()
        self.engine.update_worker_params(device_id, vol, delay)
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
                })

        if not targets:
            messagebox.showwarning("Warning", "Select at least one connected output device.")
            return

        self.engine.start(targets)
        self.lbl_status.configure(text="● Active", text_color="#107C41")
        self.btn_toggle.configure(text="Stop Audio Splitting", fg_color="#C42B1C", hover_color="#B32417")
        self.btn_refresh.configure(state="disabled")

    def stop_routing(self):
        self.engine.stop()
        self.lbl_status.configure(text="● Inactive", text_color="#888888")
        self.btn_toggle.configure(text="Start Audio Splitting", fg_color="#1f6aa5", hover_color="#144870")
        self.btn_refresh.configure(state="normal")
        self.master_vu.set(0.0)

    def safe_exit(self):
        self.stop_routing()
        self._on_setting_changed()
        self.destroy()