"""Lets the coach's code load on a machine without Windows (the test runner):
Windows calls, the mouse/keyboard hooks and screen capture are replaced by stand-ins.
Import this before importing anything from coach."""
import ctypes
import sys
import types
import unittest.mock as um

if not hasattr(ctypes, "windll"):
    ctypes.windll = um.MagicMock()
    ctypes.WinDLL = lambda *a, **k: um.MagicMock()
    ctypes.WINFUNCTYPE = lambda *a, **k: (lambda f: f)
    import ctypes.wintypes  # noqa: F401  (loads fine on Linux once the above exist)

if "pynput" not in sys.modules:
    p = types.ModuleType("pynput")
    p.mouse, p.keyboard = um.MagicMock(), um.MagicMock()
    sys.modules["pynput"] = p

import tkinter  # noqa: E402

_attrs = tkinter.Wm.wm_attributes


def _attributes(self, *a, **k):
    if a and a[0] == "-transparentcolor":  # Windows-only window option
        return None
    return _attrs(self, *a, **k)


tkinter.Wm.wm_attributes = tkinter.Wm.attributes = _attributes


def patch_all(name, value):
    """Replace a function everywhere the coach imported it (e.g. find_etakeoff)."""
    for mod_name, mod in list(sys.modules.items()):
        if (mod_name == "coach" or mod_name.startswith("coach.")) and hasattr(mod, name):
            setattr(mod, name, value)
