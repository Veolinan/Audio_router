import threading
import time
import customtkinter as ctk
from .audio_engine import play_metronome_click


class SyncWizardModal(ctk.CTkToplevel):
    def __init__(self, parent, device_id, device_name, on_sync_complete):
        super().__init__(parent)
        self.title(f"Sync Helper — {device_name}")
        self.geometry("460x320")
        self.resizable(False, False)
        self.device_id = device_id
        self.on_sync_complete = on_sync_complete
        self.running = True
        self.tap_times = []
        self.click_times = []

        self.configure(fg_color="#1E1E1E")
        self.attributes("-topmost", True)

        ctk.CTkLabel(
            self,
            text="🎧 Audio Latency Sync Helper",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#00BCF2",
        ).pack(pady=(16, 6))

        ctk.CTkLabel(
            self,
            text="Listen to the metronome beat in your device.\nTap the button or press SPACE on the beat.",
            font=ctk.CTkFont(size=11),
            text_color="#AAAAAA",
        ).pack(pady=(0, 12))

        self.flash_indicator = ctk.CTkFrame(self, width=120, height=20, corner_radius=10, fg_color="#333333")
        self.flash_indicator.pack(pady=6)

        self.btn_tap = ctk.CTkButton(
            self,
            text="TAP HERE (or Spacebar)",
            width=220,
            height=48,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._record_tap,
        )
        self.btn_tap.pack(pady=10)

        self.lbl_result = ctk.CTkLabel(
            self, text="Waiting for taps...", font=ctk.CTkFont(size=12), text_color="#A0A0A0"
        )
        self.lbl_result.pack(pady=6)

        self.btn_apply = ctk.CTkButton(
            self, text="Apply Offset", state="disabled", command=self._apply_offset
        )
        self.btn_apply.pack(pady=(8, 12))

        self.bind("<space>", lambda e: self._record_tap())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.calculated_delay = 0
        threading.Thread(target=self._click_loop, daemon=True).start()

    def _click_loop(self):
        while self.running:
            now = time.time()
            self.click_times.append(now)
            play_metronome_click(self.device_id)
            if self.running:
                self.after(0, self._flash_on)
            time.sleep(1.0)

    def _flash_on(self):
        # Guard against destroyed Tkinter widgets
        try:
            if self.running and self.winfo_exists():
                self.flash_indicator.configure(fg_color="#00BCF2")
                self.after(80, self._flash_off)
        except Exception:
            pass

    def _flash_off(self):
        try:
            if self.running and self.winfo_exists():
                self.flash_indicator.configure(fg_color="#333333")
        except Exception:
            pass

    def _record_tap(self):
        if not self.running:
            return
        tap_time = time.time()
        self.tap_times.append(tap_time)

        if self.click_times:
            closest_click = min(self.click_times, key=lambda c: abs(c - tap_time))
            diff_ms = int(abs(tap_time - closest_click) * 1000)
            if diff_ms < 400:
                self.calculated_delay = diff_ms
                self.lbl_result.configure(
                    text=f"Detected Latency: ~{diff_ms} ms", text_color="#107C41"
                )
                self.btn_apply.configure(state="normal")

    def _apply_offset(self):
        self.on_sync_complete(self.calculated_delay)
        self._on_close()

    def _on_close(self):
        self.running = False
        try:
            self.destroy()
        except Exception:
            pass