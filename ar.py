import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import warnings
import numpy as np
import soundcard as sc
import sounddevice as sd

warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)

SAMPLE_RATE = 48000
BLOCK_SIZE = 1024


class DevicePlaybackWorker(threading.Thread):
    def __init__(self, device_id, name, channels=2, volume=1.0):
        super().__init__(daemon=True)
        self.device_id = device_id
        self.name = name
        self.channels = channels
        self.volume = volume
        self.audio_queue = queue.Queue(maxsize=30)
        self.running = True

    def run(self):
        try:
            with sd.OutputStream(
                device=self.device_id,
                samplerate=SAMPLE_RATE,
                channels=self.channels,
                blocksize=BLOCK_SIZE,
                dtype="float32",
            ) as stream:
                while self.running:
                    try:
                        data = self.audio_queue.get(timeout=0.2)

                        if data.shape[1] != self.channels:
                            if data.shape[1] > self.channels:
                                data = data[:, :self.channels]
                            else:
                                data = np.repeat(data, self.channels // data.shape[1], axis=1)

                        if self.volume != 1.0:
                            data = data * self.volume

                        if not data.flags["C_CONTIGUOUS"]:
                            data = np.ascontiguousarray(data, dtype=np.float32)

                        stream.write(data)
                    except queue.Empty:
                        continue
        except Exception as e:
            print(f"[Worker Error] Device {self.name} (ID {self.device_id}): {e}")

    def push(self, data):
        if self.running:
            try:
                self.audio_queue.put_nowait(data)
            except queue.Full:
                pass

    def stop(self):
        self.running = False


class AudioRouterGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Windows Multi-Audio Router")
        self.geometry("680x600")
        self.minsize(560, 440)

        self.wasapi_idx = self._get_wasapi_index()
        self.workers = {}
        self.device_vars = {}
        self.volume_vars = {}
        self.stream_thread = None
        self.is_routing = False

        self._setup_ui()
        self.refresh_devices()

    def _get_wasapi_index(self):
        for idx, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                return idx
        messagebox.showerror("Error", "WASAPI host API not detected.")
        sys.exit(1)

    def _setup_ui(self):
        header_frame = ttk.Frame(self, padding=10)
        header_frame.pack(fill=tk.X)

        self.btn_refresh = ttk.Button(
            header_frame, text="↻ Rescan Audio Devices", command=self.refresh_devices
        )
        self.btn_refresh.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(
            header_frame, text="Status: Stopped", font=("Segoe UI", 10, "bold"), foreground="gray"
        )
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        container = ttk.LabelFrame(
            self, 
            text="Available Output Targets (Connected endpoints enabled)", 
            padding=10
        )
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        self.scrollable_frame = ttk.Frame(canvas)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)

        canvas.configure(xscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas_frame = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_frame, width=e.width))

        footer_frame = ttk.Frame(self, padding=10)
        footer_frame.pack(fill=tk.X)

        self.btn_toggle = ttk.Button(
            footer_frame, text="Start Audio Splitting", command=self.toggle_routing
        )
        self.btn_toggle.pack(fill=tk.X, ipady=6)

    def is_device_accessible(self, device_id, channels):
        """Probes the device to ensure it is actually connected and responsive."""
        try:
            sd.check_output_settings(
                device=device_id,
                channels=channels,
                dtype="float32",
                samplerate=SAMPLE_RATE,
            )
            return True
        except Exception:
            return False

    def refresh_devices(self):
        if self.is_routing:
            messagebox.showwarning("Busy", "Stop audio routing before scanning for new devices.")
            return

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.device_vars.clear()
        self.volume_vars.clear()

        devices = sd.query_devices()
        bt_keywords = ["bluetooth", "hands-free", "airpods", "buds", "wireless", "headset", "headphones"]
        
        # Determine the current default OS playback endpoint
        default_out_idx = sd.default.device[1]

        found_any = False
        for idx, dev in enumerate(devices):
            if dev["hostapi"] == self.wasapi_idx and dev["max_output_channels"] > 0:
                found_any = True
                name = dev["name"]
                is_bt = any(kw in name.lower() for kw in bt_keywords)
                channels = min(2, dev["max_output_channels"])

                # Probe connection state
                connected = self.is_device_accessible(idx, channels)
                is_default = (idx == default_out_idx)

                # Build descriptive label tags
                type_tag = "[Bluetooth]" if is_bt else "[Speakers]"
                if is_default:
                    type_tag += " [DEFAULT OUTPUT]"

                if not connected:
                    status_tag = " (Disconnected)"
                else:
                    status_tag = ""

                display_text = f"{type_tag} {name}{status_tag}"

                row = ttk.Frame(self.scrollable_frame, padding=4)
                row.pack(fill=tk.X, expand=True, pady=2)

                chk_var = tk.BooleanVar(value=False)
                self.device_vars[idx] = chk_var

                chk = ttk.Checkbutton(
                    row, 
                    text=display_text, 
                    variable=chk_var,
                    state=tk.NORMAL if connected else tk.DISABLED
                )
                chk.pack(side=tk.LEFT, fill=tk.X, expand=True)

                vol_var = tk.DoubleVar(value=1.0)
                self.volume_vars[idx] = vol_var

                vol_slider = ttk.Scale(
                    row, 
                    from_=0.0, 
                    to=1.5, 
                    variable=vol_var, 
                    orient=tk.HORIZONTAL, 
                    length=100,
                    state=tk.NORMAL if connected else tk.DISABLED
                )
                vol_slider.pack(side=tk.RIGHT, padx=5)

        if not found_any:
            ttk.Label(self.scrollable_frame, text="No WASAPI playback devices detected.").pack(pady=10)

    def toggle_routing(self):
        if self.is_routing:
            self.stop_routing()
        else:
            self.start_routing()

    def start_routing(self):
        # Filter strictly for devices that are both checked and reachable
        selected_ids = [idx for idx, var in self.device_vars.items() if var.get()]

        if not selected_ids:
            messagebox.showwarning("Warning", "Please select at least one connected output device.")
            return

        self.workers.clear()
        devices = sd.query_devices()

        for idx in selected_ids:
            out_channels = min(2, devices[idx]["max_output_channels"])
            
            # Final check before creating thread to prevent PaErrorCode -9992
            if not self.is_device_accessible(idx, out_channels):
                messagebox.showerror(
                    "Device Disconnected",
                    f"Could not reach {devices[idx]['name']}.\nEnsure it is powered on and connected."
                )
                self.refresh_devices()
                return

            vol = self.volume_vars[idx].get()
            worker = DevicePlaybackWorker(
                idx, devices[idx]["name"], channels=out_channels, volume=vol
            )
            self.workers[idx] = worker
            worker.start()

        self.is_routing = True
        self.lbl_status.config(text="Status: Active", foreground="green")
        self.btn_toggle.config(text="Stop Audio Splitting")
        self.btn_refresh.config(state=tk.DISABLED)

        self.stream_thread = threading.Thread(target=self._run_loopback, daemon=True)
        self.stream_thread.start()

    def _run_loopback(self):
        try:
            default_spk = sc.default_speaker()

            loopback_mic = None
            for mic in sc.all_microphones(include_loopback=True):
                if mic.isloopback and default_spk.name in mic.name:
                    loopback_mic = mic
                    break

            if loopback_mic is None:
                loopbacks = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
                if loopbacks:
                    loopback_mic = loopbacks[0]
                else:
                    raise RuntimeError("No Windows loopback audio endpoint found.")

            with loopback_mic.recorder(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE) as recorder:
                while self.is_routing:
                    data = recorder.record(numframes=BLOCK_SIZE)
                    data_float = np.ascontiguousarray(data, dtype=np.float32)

                    for idx, worker in self.workers.items():
                        worker.volume = self.volume_vars[idx].get()
                        worker.push(data_float)
        except Exception as e:
            print(f"[Loopback Error]: {e}")
            self.after(0, self.stop_routing)

    def stop_routing(self):
        self.is_routing = False
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()

        self.lbl_status.config(text="Status: Stopped", foreground="gray")
        self.btn_toggle.config(text="Start Audio Splitting")
        self.btn_refresh.config(state=tk.NORMAL)


if __name__ == "__main__":
    app = AudioRouterGUI()
    app.mainloop()