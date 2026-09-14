import os
import sys
import threading
from PIL import Image, ImageDraw
import pystray


def get_writable_icon_path():
    """Returns a safe, user-writable directory path for persistent files."""
    app_data = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Windows Multi-Audio Router")
    os.makedirs(app_data, exist_ok=True)
    return os.path.join(app_data, "app.ico")


def generate_app_icon():
    """Renders a modern, high-res gradient headphone & soundwave icon."""
    size = (128, 128)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 1. Rounded container background
    draw.rounded_rectangle([4, 4, 124, 124], radius=28, fill="#181818", outline="#007ACC", width=4)

    # 2. Outer Headphone Band
    draw.arc([32, 28, 96, 90], start=180, end=0, fill="#00BCF2", width=6)

    # 3. Left & Right Ear Cushions
    draw.rounded_rectangle([26, 56, 40, 88], radius=6, fill="#FFFFFF")
    draw.rounded_rectangle([88, 56, 102, 88], radius=6, fill="#FFFFFF")

    # 4. Center Soundwave Bars
    bars = [
        ((48, 66), (48, 78)),
        ((56, 58), (56, 86)),
        ((64, 52), (64, 92)),
        ((72, 58), (72, 86)),
        ((80, 66), (80, 78)),
    ]
    for start, end in bars:
        draw.line([start, end], fill="#00BCF2", width=3)

    return image


def ensure_icon_exists():
    """Locates the bundled icon or safely saves to user AppData without permission errors."""
    # 1. First priority: Check PyInstaller bundled temporary root
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled_path = os.path.join(sys._MEIPASS, "app.ico")
        if os.path.exists(bundled_path):
            return bundled_path

    # 2. Second priority: Check next to the executable
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    local_path = os.path.join(exe_dir, "app.ico")
    if os.path.exists(local_path):
        return local_path

    # 3. Third priority: Root source project directory
    if os.path.exists("app.ico"):
        return os.path.abspath("app.ico")

    # 4. Fallback: Save generated icon into safe user-writable APPDATA
    writable_path = get_writable_icon_path()
    if not os.path.exists(writable_path):
        try:
            img = generate_app_icon()
            img.save(
                writable_path,
                format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
            )
        except Exception as e:
            print(f"[Icon Save Warning]: {e}")
    return writable_path


class TrayManager:
    def __init__(self, root, on_quit_callback):
        self.root = root
        self.on_quit = on_quit_callback
        self.icon = None

    def setup(self):
        icon_path = ensure_icon_exists()
        try:
            tray_image = Image.open(icon_path)
        except Exception:
            tray_image = generate_app_icon()

        menu = pystray.Menu(
            pystray.MenuItem("Show Window", self.show_window, default=True),
            pystray.MenuItem("Exit Router", self.quit_app),
        )
        self.icon = pystray.Icon("AudioRouter", tray_image, "Windows Multi-Audio Router", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self._restore)

    def _restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self, icon=None, item=None):
        if self.icon:
            self.icon.stop()
        self.root.after(0, self.on_quit)