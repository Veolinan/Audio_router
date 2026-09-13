import ctypes
import queue
import threading
import warnings
import numpy as np
import soundcard as sc
import sounddevice as sd

warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)

SAMPLE_RATE = 48000


def play_test_chime(device_id, channels=2):
    """Plays an immediate 440 Hz soft test chime."""
    def _chime():
        duration = 0.35
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
        tone = 0.25 * np.sin(2 * np.pi * 440 * t)
        envelope = np.linspace(1.0, 0.0, len(tone))
        chime_wave = (tone * envelope).astype(np.float32)
        audio_frame = np.column_stack([chime_wave] * channels)
        try:
            with sd.OutputStream(
                device=device_id,
                samplerate=SAMPLE_RATE,
                channels=channels,
                dtype="float32",
            ) as stream:
                stream.write(audio_frame)
        except Exception as e:
            print(f"[Chime Error] ID {device_id}: {e}")

    threading.Thread(target=_chime, daemon=True).start()


def play_metronome_click(device_id, channels=2):
    """Produces a sharp 1000 Hz calibration tick for the tap-to-sync tool."""
    duration = 0.05
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    tone = 0.4 * np.sin(2 * np.pi * 1000 * t)
    envelope = np.linspace(1.0, 0.0, len(tone))
    click_wave = (tone * envelope).astype(np.float32)
    audio_frame = np.column_stack([click_wave] * channels)
    try:
        with sd.OutputStream(
            device=device_id,
            samplerate=SAMPLE_RATE,
            channels=channels,
            dtype="float32",
        ) as stream:
            stream.write(audio_frame)
    except Exception:
        pass


class DevicePlaybackWorker(threading.Thread):
    def __init__(self, device_id, name, channels=2, volume=1.0, delay_ms=0, pan=0.0, muted=False, block_size=1024, on_level=None):
        super().__init__(daemon=True)
        self.device_id = device_id
        self.name = name
        self.channels = channels
        self.volume = volume
        self.delay_ms = delay_ms
        self.pan = pan
        self.muted = muted
        self.block_size = block_size
        self.on_level = on_level
        self.audio_queue = queue.Queue(maxsize=50)
        self.running = True

        max_delay_samples = int(SAMPLE_RATE * 0.5)
        self.delay_buffer = np.zeros((max_delay_samples, self.channels), dtype=np.float32)
        self.write_cursor = 0

    def run(self):
        try:
            with sd.OutputStream(
                device=self.device_id,
                samplerate=SAMPLE_RATE,
                channels=self.channels,
                blocksize=self.block_size,
                dtype="float32",
            ) as stream:
                while self.running:
                    try:
                        data = self.audio_queue.get(timeout=0.2)

                        if self.muted:
                            data.fill(0.0)
                        else:
                            # Match channel layout
                            if data.shape[1] != self.channels:
                                if data.shape[1] > self.channels:
                                    data = data[:, :self.channels]
                                else:
                                    data = np.repeat(data, self.channels // data.shape[1], axis=1)

                            # Soft-knee saturation limiter prevents clipping distortion above 1.0 gain
                            if self.volume > 1.0:
                                data = np.tanh(data * self.volume)
                            elif self.volume != 1.0:
                                data = data * self.volume

                            # Stereo balance panning
                            if self.channels == 2 and self.pan != 0.0:
                                left_gain = 1.0 - max(0.0, self.pan)
                                right_gain = 1.0 + min(0.0, self.pan)
                                data[:, 0] *= left_gain
                                data[:, 1] *= right_gain

                        # Send per-device RMS back to UI
                        if self.on_level:
                            dev_rms = float(np.sqrt(np.mean(data**2)))
                            self.on_level(self.device_id, dev_rms)

                        # Circular delay buffer
                        delay_samples = int((self.delay_ms / 1000.0) * SAMPLE_RATE)
                        if delay_samples > 0:
                            n = data.shape[0]
                            buf_len = self.delay_buffer.shape[0]

                            for i in range(n):
                                self.delay_buffer[(self.write_cursor + i) % buf_len] = data[i]

                            read_cursor = (self.write_cursor - delay_samples) % buf_len
                            out_data = np.empty_like(data)
                            for i in range(n):
                                out_data[i] = self.delay_buffer[(read_cursor + i) % buf_len]

                            self.write_cursor = (self.write_cursor + n) % buf_len
                            data = out_data

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
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(data)
                except (queue.Empty, queue.Full):
                    pass

    def stop(self):
        self.running = False


class AudioRouterEngine:
    def __init__(self, on_master_level=None, on_device_level=None, on_error=None):
        self.on_master_level = on_master_level
        self.on_device_level = on_device_level
        self.on_error = on_error
        self.workers = {}
        self.is_routing = False
        self.stream_thread = None
        self.block_size = 1024

    def probe_device(self, device_id, channels=2):
        for rate in [48000, 44100, 16000]:
            try:
                sd.check_output_settings(
                    device=device_id,
                    channels=channels,
                    dtype="float32",
                    samplerate=rate,
                )
                return True
            except Exception:
                continue
        try:
            return sd.query_devices(device_id)["max_output_channels"] > 0
        except Exception:
            return False

    def start(self, targets, block_size=1024):
        self.block_size = block_size
        self.workers.clear()
        for t in targets:
            worker = DevicePlaybackWorker(
                device_id=t["id"],
                name=t["name"],
                channels=t["channels"],
                volume=t["vol"],
                delay_ms=t["delay"],
                pan=t["pan"],
                muted=t["muted"],
                block_size=self.block_size,
                on_level=self.on_device_level,
            )
            self.workers[t["id"]] = worker
            worker.start()

        self.is_routing = True
        self.stream_thread = threading.Thread(target=self._run_loopback, daemon=True)
        self.stream_thread.start()

    def update_worker_params(self, device_id, volume, delay_ms, pan, muted):
        if device_id in self.workers:
            self.workers[device_id].volume = volume
            self.workers[device_id].delay_ms = delay_ms
            self.workers[device_id].pan = pan
            self.workers[device_id].muted = muted

    def _run_loopback(self):
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass

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
                    raise RuntimeError("No active WASAPI loopback audio endpoint found.")

            with loopback_mic.recorder(samplerate=SAMPLE_RATE, blocksize=self.block_size) as rec:
                while self.is_routing:
                    data = rec.record(numframes=self.block_size)
                    data_float = np.ascontiguousarray(data, dtype=np.float32)

                    if self.on_master_level:
                        rms = float(np.sqrt(np.mean(data_float**2)))
                        self.on_master_level(rms)

                    for worker in self.workers.values():
                        worker.push(data_float)

        except Exception as e:
            print(f"[Loopback Error]: {e}")
            if self.on_error:
                self.on_error(str(e))
            self.stop()
        finally:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    def stop(self):
        self.is_routing = False
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()