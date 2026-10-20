"""Run by the build machine (TakeoffCoach.exe --self-test): every part the program needs must load."""
import os
import tkinter as tk

from coach.config import COACH_VERSION, HERE


def self_test():
    """Run by the build machine: every part the packaged program needs must load. Exit code 0 = good."""
    import comtypes.client  # noqa: F401
    import mss  # noqa: F401
    from PIL import Image, ImageOps  # noqa: F401
    from winrt.windows.media.ocr import OcrEngine  # noqa: F401
    from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat  # noqa: F401
    from winrt.windows.storage.streams import Buffer  # noqa: F401
    from winrt.windows.globalization import Language  # noqa: F401
    import winrt.windows.foundation.collections  # noqa: F401
    from pynput import mouse as _m, keyboard as _k  # noqa: F401
    import coach.app  # noqa: F401  (every part of the coach loads)
    from coach.config import SITE_KEY, SITE_URL
    if not (SITE_URL.startswith("https://") and SITE_KEY.startswith("sb_publishable_")):
        raise SystemExit("The training-site settings (.env) weren't packed into the program.")
    root = tk.Tk()
    pw = _print_window_check(root)
    root.destroy()
    with open(os.path.join(HERE, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"Takeoff Coach {COACH_VERSION} self-test passed\nPrintWindow: {pw}\n")


def _print_window_check(root):
    """Informational only (the build machine may have no real desktop): can the coach read a window's own
    picture while something covers it? Shows a red window, covers it, and reads it back."""
    try:
        import ctypes
        from coach.winapi import print_window_region, win_rect
        root.geometry("200x120+100+100")
        root.configure(bg="#ff0000")
        cover = tk.Toplevel(root)
        cover.geometry("200x120+100+100")
        cover.configure(bg="#0000ff")
        cover.attributes("-topmost", True)
        root.update()
        cover.update()
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
        l, t, r, b = win_rect(hwnd)
        shot = print_window_region(hwnd, (l + 60, t + 60, l + 90, t + 90))
        if not shot:
            return "not available (falls back to hiding the callout)"
        w, h, rgb = shot
        mid = (h // 2 * w + w // 2) * 3
        return f"ok, read {tuple(rgb[mid:mid + 3])} under a blue window (red expected)"
    except Exception as e:
        return f"error {e!r}"
