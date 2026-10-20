"""Windows helpers: finding eTakeoff's window, its position, and click-through overlay windows."""
import ctypes
from ctypes import wintypes


# Use real screen pixels everywhere (mouse hook, window positions, our windows).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_etakeoff():
    found = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, b, n + 1)
                if b.value.startswith("eTakeoff Dimension"):
                    found.append((h, b.value))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else (None, "")


def win_rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD


def pid_of(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def click_is_in_etakeoff(x, y, et_hwnd):
    """True only if the window actually under the cursor belongs to eTakeoff (its main window or its dialogs).
    Our overlay is click-through, so Windows skips it here."""
    h = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return bool(h) and pid_of(h) == pid_of(et_hwnd)


def foreground_title():
    h = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


def make_click_through(tkwin):
    hwnd = user32.GetAncestor(tkwin.winfo_id(), 2)  # GA_ROOT
    style = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80 | 0x08000000)


# --- eTakeoff's own picture of its window (PrintWindow), so other windows on top don't get in the way
class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _gdi():
    """Our own handles to user32/gdi32 with 64-bit-safe types (kept apart from the shared user32 above)."""
    if not hasattr(_gdi, "libs"):
        u, g = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
        H = ctypes.c_void_p
        u.GetDC.argtypes, u.GetDC.restype = [wintypes.HWND], H
        u.ReleaseDC.argtypes = [wintypes.HWND, H]
        u.PrintWindow.argtypes, u.PrintWindow.restype = [wintypes.HWND, H, wintypes.UINT], wintypes.BOOL
        g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = [H], H
        g.CreateCompatibleBitmap.argtypes, g.CreateCompatibleBitmap.restype = [H, ctypes.c_int, ctypes.c_int], H
        g.SelectObject.argtypes, g.SelectObject.restype = [H, H], H
        g.DeleteObject.argtypes, g.DeleteDC.argtypes = [H], [H]
        g.GetDIBits.argtypes = [H, H, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        g.GetDIBits.restype = ctypes.c_int
        _gdi.libs = (u, g)
    return _gdi.libs


def print_window_region(hwnd, box):
    """The part of a window inside box (screen pixels) as drawn by that window itself, even where another
    window (like the coach's callout) covers it. Returns (width, height, rgb bytes), or None if Windows can't."""
    from PIL import Image
    u, g = _gdi()
    l, t, r, b = win_rect(hwnd)
    W, H = r - l, b - t
    x1, y1, x2, y2 = max(0, box[0] - l), max(0, box[1] - t), min(W, box[2] - l), min(H, box[3] - t)
    if W <= 0 or H <= 0 or x2 <= x1 or y2 <= y1:
        return None
    screen = u.GetDC(None)
    mem = g.CreateCompatibleDC(screen)
    bmp = g.CreateCompatibleBitmap(screen, W, H)
    old = g.SelectObject(mem, bmp)
    try:
        if not u.PrintWindow(hwnd, mem, 2):  # 2 = PW_RENDERFULLCONTENT
            return None
        hdr = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down
        buf = ctypes.create_string_buffer(W * H * 4)
        g.SelectObject(mem, old)
        if g.GetDIBits(mem, bmp, 0, H, buf, ctypes.byref(hdr), 0) != H:
            return None
        img = Image.frombuffer("RGB", (W, H), buf.raw, "raw", "BGRX", 0, 1).crop((x1, y1, x2, y2))
        if img.getextrema() in (((0, 0), (0, 0), (0, 0)),):
            return None  # all black: the window didn't draw itself for us
        return img.width, img.height, img.tobytes()
    finally:
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, screen)
