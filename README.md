# Windows Multi-Audio Router

A lightweight, modern Windows desktop utility that captures active system audio via native WASAPI loopback and simultaneously broadcasts it across multiple output endpoints (e.g., laptop speakers and multiple Bluetooth earbuds) with millisecond-precision latency synchronization.

---

## Releases & Downloads

Pre-built standalone executables are compiled, packaged, and verified for every production version. You do not need Python or developer dependencies installed to run them.

| Release | Status | Direct Download | Notes |
| :--- | :--- | :--- | :--- |
| **v1.1.0** | **Latest** | [**Download AudioRouter-v1.1.0-win64.exe**](https://github.com/Veolinan/Audio_router/releases/tag/v1.1.0) | Tap-to-sync wizard, anti-clipping limiter, native `.ico`, speaker auto-mute. |
| **v1.0.0** | Stable | [Download AudioRouter-v1.0.0-win64.exe](https://github.com/Veolinan/Audio_router/releases/tag/v1.0.0) | Initial production release with core WASAPI routing engine. |

Browse all past releases, changelogs, and attached source archives on the [GitHub Releases Page](https://github.com/Veolinan/Audio_router/releases).

---

## Practical Use Cases

* **Silent Parties & Shared Media:** Broadcast audio to multiple pairs of Bluetooth headphones or earbuds from a single PC—ideal for dorm movie nights, study sessions, and private listening events.
* **Affordable Conference & Group Calls:** Share meeting and presentation audio across multiple personal headsets in co-working spaces or meeting rooms without investing in expensive proprietary multi-headset hardware hubs.
* **Speaker & Headphone Dual-Listening:** Keep audio playing through internal speakers while routing a personal feed to an earbud for individuals who need higher volume or clearer dialogue.

---

## Features

* **Simultaneous Multi-Device Playback:** Route real-time desktop audio across multiple connected audio devices concurrently.
* **Zero Virtual Cables Required:** Leverages native Windows CoreAudio/WASAPI loopback capture directly from hardware memory.
* **Millisecond Latency Calibration:** Adjustable per-device delay buffers (0–300 ms) with quick presets (`0ms`, `120ms`, `200ms`) to eliminate the echo effect caused by Bluetooth latency differences.
* **Interactive Tap-to-Sync Wizard:** Built-in metronome calibration tool to measure and apply Bluetooth latency offsets automatically.
* **Modern Windows 11 Dark UI:** Built with CustomTkinter featuring clean card containers, responsive toggle switches, and centered window positioning.
* **Audio Visualizers:** Live master and per-device VU level meters to verify active audio paths at a glance.
* **Per-Endpoint Controls:** Independent volume sliders, stereo panning (L/R balance), and instant mute toggles (`🔊`/`🔇`) with double-click reset snapping.
* **Anti-Clipping Limiter:** Soft-knee saturation guard (`np.tanh`) prevents digital distortion and crackling when boosting output volume.
* **Auto-Mute Speakers:** Optional automatic muting of internal laptop speakers when two or more headphones are connected.
* **Custom Device Nicknames:** Rename long Bluetooth system names to personal aliases stored in `config.json`.
* **System Tray & Background Operation:** Minimizes to the Windows taskbar tray with global hotkey support (`Ctrl + Alt + S`).

---

## Requirements

* **Operating System:** Windows 10 or Windows 11 (64-bit)
* **Audio Devices:** Two or more connected playback devices (e.g., internal speakers, wired headphones, Bluetooth earbuds)
* **Python (Source only):** Python 3.10+ (only required if building or running from source)

---

## Installation

### Option 1: Standalone Binary (Recommended)

1. Download **`AudioRouter-v1.1.0-win64.exe`** directly from the [Releases Page](https://github.com/Veolinan/Audio_router/releases/latest).
2. Move the `.exe` to your preferred folder (such as `C:\Program Files\AudioRouter` or your Desktop).
3. *(Optional)* Right-click the `.exe` → **Show more options** → **Create shortcut**, then drag the shortcut to your Desktop or Start Menu.
4. Double-click the file to run.

> **Windows SmartScreen Tip:** If Windows SmartScreen displays *"Windows protected your PC"*, click **More info** → **Run anyway** (standard for open-source binaries published without an expensive commercial code-signing certificate).

---

### Option 2: Run from Source

**Step 1: Clone the repository**
```bash
git clone [https://github.com/Veolinan/Audio_router.git](https://github.com/Veolinan/Audio_router.git)
cd Audio_router
```

**Step 2: Create and activate a virtual environment**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Step 3: Install required dependencies**
```powershell
pip install -r requirements.txt
```

**Step 4: Launch the app**
```powershell
python main.py
```

---

## How to Use

1. Ensure your Bluetooth earbuds, headphones, and external speakers are paired and connected to Windows.
2. Launch **Windows Multi-Audio Router**.
3. Click **↻ Rescan** if recently connected Bluetooth endpoints are not listed.
4. Turn on the switch next to each device you want to output sound to.
5. Calibrate the latency:
   * Keep low-latency outputs (like built-in laptop speakers) at `0ms`.
   * Set Bluetooth devices to their transmission delay (commonly `120ms`–`200ms`), or click **⚡ Sync** to open the metronome tap tool to calibrate it automatically.
6. Click **Start Audio Splitting**.
7. Minimize the window to let the app run quietly in the Windows system tray. Press `Ctrl + Alt + S` anytime to toggle splitting on or off globally.

---

## Architecture

```text
Audio_router/
├── main.py                  # Entry point
├── config.json              # Saved device selections, aliases, and offsets
├── app.ico                  # Embedded multi-resolution application icon
└── modules/
    ├── audio_engine.py      # WASAPI loopback capture, DSP workers, delay ring-buffers, limiter
    ├── gui.py               # CustomTkinter interface, VU visualizers, controls
    ├── sync_wizard.py       # Latency calibration modal and metronome clicker
    ├── tray_manager.py      # System tray icon and restore behaviors
    └── config_manager.py    # Configuration persistence and Windows autostart handling
```

---

## Troubleshooting

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| **Echo / Reverb Sound** | Speaker audio plays earlier than Bluetooth audio | Drag the **Delay** slider on the faster device (speakers) higher to match your Bluetooth headphones (~120–180 ms). |
| **Audio Popping / Stuttering** | Bluetooth packets dropping or buffer underrun | Set the **Buffer** selector in the top toolbar to `2048 (Stable)` or `4096 (High)`. |
| **Device Missing from List** | Windows put the device in power-save mode | Click **↻ Rescan** to force PortAudio to query active endpoints. |
| **Hotkey Not Working** | Focused app has Administrator privileges | Right-click `AudioRouter.exe` and select **Run as Administrator**. |

---

## Building the Executable from Source

To compile the application into a standalone `.exe` using PyInstaller:

```powershell
pyinstaller --noconsole --onefile --clean `
  --icon=app.ico `
  --add-data "app.ico;." `
  --collect-all customtkinter `
  --collect-all soundcard `
  --collect-all cffi `
  main.py
```

The resulting file will be ready inside the `dist/` directory.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.