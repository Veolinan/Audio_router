import threading
from PIL import Image, ImageDraw
import pystray


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

    # 4. Sound Wave Bars (Center audio visualizer)
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
            "AudioRouter", generate_app_icon(), "Windows Multi-Audio Router", menu
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