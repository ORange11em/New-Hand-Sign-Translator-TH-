"""Capture the HandVox training page for visual QA without opening the camera."""

import argparse
from pathlib import Path
import sys
import tkinter as tk

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handvox.ui import HandVoxApp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--page",
        default="training",
        choices=("dashboard", "sentence", "gestures", "dataset", "training", "settings", "help"),
    )
    parser.add_argument("--tab", type=int, default=0, choices=range(5))
    args = parser.parse_args()
    root = tk.Tk()
    root.geometry("1280x820+24+24")
    root.attributes("-topmost", True)
    app = HandVoxApp(root)
    app.show_page(args.page)
    if args.page == "training":
        app.pages["training"].show_step(args.tab)
    root.lift()
    root.focus_force()

    def capture():
        root.update_idletasks()
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        width = root.winfo_width()
        height = root.winfo_height()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(args.output)
        root.attributes("-topmost", False)
        app.close()

    root.after(900, capture)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
