import ctypes
import queue
import threading
import warnings
import numpy as np
import soundcard as sc
import sounddevice as sd

warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)

SAMPLE_RATE = 48000
BLOCK_SIZE = 1024


def play_test_chime(device_id, channels=2):
    """Generates an immediate 440 Hz test chime on the target device."""
    def _chime():
        duration = 0.4
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        # Apply gentle envelope fade-out to prevent speaker pop
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
            print(f"[Chime Error] Could not play test tone on ID {device_id}: {e}")

    threading.Thread(target=_chime, daemon=True).start()


class DevicePlaybackWorker(threading.Thread):
    def __init__(self, device_id, name, channels=2, volume=1.0, delay_ms=0):
        super().__init__(daemon=True)
        self.device_id = device_id
        self.name = name
        self.channels = channels
        self.volume = volume
        self.delay_ms = delay_ms
        self.audio_queue = queue.Queue(maxsize=50)
        self.running = True

        # Circular buffer for millisecond latency synchronization
        max_delay_samples = int(SAMPLE_RATE * 0.5)  # Max 500 ms buffer
        self.delay_buffer = np.zeros((max_delay_samples, self.channels), dtype=np.float32)
        self.write_cursor = 0

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

                        # Match channel layout
                        if data.shape[1] != self.channels:
                            if data.shape[1] > self.channels:
                                data = data[:, :self.channels]
                            else:
                                data = np.repeat(data, self.channels // data.shape[1], axis=1)

                        if self.volume != 1.0:
                            data = data * self.volume

                        # Apply millisecond ring delay
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
    def __init__(self, on_level_callback=None, on_error_callback=None):
        self.on_level = on_level_callback
        self.on_error = on_error_callback
        self.workers = {}
        self.is_routing = False
        self.stream_thread = None

    def probe_device(self, device_id, channels=2):
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

    def start(self, targets):
        """targets: list of dicts: [{'id': int, 'name': str, 'channels': int, 'vol': float, 'delay': int}]"""
        self.workers.clear()
        for t in targets:
            worker = DevicePlaybackWorker(
                device_id=t["id"],
                name=t["name"],
                channels=t["channels"],
                volume=t["vol"],
                delay_ms=t["delay"],
            )
            self.workers[t["id"]] = worker
            worker.start()

        self.is_routing = True
        self.stream_thread = threading.Thread(target=self._run_loopback, daemon=True)
        self.stream_thread.start()

    def update_worker_params(self, device_id, volume, delay_ms):
        if device_id in self.workers:
            self.workers[device_id].volume = volume
            self.workers[device_id].delay_ms = delay_ms

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

            with loopback_mic.recorder(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE) as rec:
                while self.is_routing:
                    data = rec.record(numframes=BLOCK_SIZE)
                    data_float = np.ascontiguousarray(data, dtype=np.float32)

                    if self.on_level:
                        rms = float(np.sqrt(np.mean(data_float**2)))
                        self.on_level(rms)

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