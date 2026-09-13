import threading
from PIL import Image, ImageDraw
import pystray


def create_tray_icon():
    """Draws a clean system tray speaker icon."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Circle badge background
    draw.ellipse((4, 4, 60, 60), fill="#007ACC")
    # Speaker cone
    draw.polygon([(22, 26), (32, 18), (32, 46), (22, 38)], fill="white")
    draw.rectangle([(16, 26), (22, 38)], fill="white")
    # Soundwaves
    draw.arc([30, 20, 44, 44], start=290, end=70, fill="white", width=3)
    draw.arc([36, 14, 52, 50], start=290, end=70, fill="white", width=3)
    return image


class TrayManager:
    def __init__(self, root, on_quit_callback):
        self.root = root
        self.on_quit = on_quit_callback
        self.icon = None

    def setup(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show Window", self.show_window, default=True),
            pystray.MenuItem("Exit Router", self.quit_app),
        )
        self.icon = pystray.Icon(
            "AudioRouter", create_tray_icon(), "Multi-Audio Router", menu
        )
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