import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# keep the coach's files (answers, prefs, outbox) out of the real Documents folder
os.environ["HOME"] = os.environ["USERPROFILE"] = tempfile.mkdtemp()
import winstub  # noqa: E402,F401

import json  # noqa: E402
import unittest.mock as um  # noqa: E402

import pytest  # noqa: E402


class FakeETakeoff:
    """Stands in for the eTakeoff window: its title, position, and what its COM interface reports."""
    def __init__(self):
        self.title = "eTakeoff Dimension - Project: 260817.1_Real Job"
        self.rect = (0, 0, 1400, 900)
        self.projects = [("g1", "260817.1_Real Job")]
        self.rows = {}


@pytest.fixture
def app():
    """A real Coach window (needs a display; CI uses Xvfb) with eTakeoff and the website faked."""
    if not os.environ.get("DISPLAY"):
        pytest.skip("needs a display (run with xvfb-run)")
    from winstub import patch_all
    from coach import config
    from coach.app import Coach
    et = FakeETakeoff()
    patch_all("find_etakeoff", lambda: (1, et.title))
    patch_all("win_rect", lambda h: et.rect)
    patch_all("make_click_through", lambda w: None)
    patch_all("check_for_update", lambda: None)
    patch_all("print_window_region", lambda h, box: None)
    import coach.winapi as w
    w.user32.IsIconic.return_value = 0
    with um.patch.object(Coach, "sync_in_background", lambda self, catalog=False: None):
        c = Coach()
    c.cloud.account = {"name": "John Doe", "email": "john@x.com", "refresh_token": "t"}
    probe = um.MagicMock()
    probe.projects = lambda: et.projects
    probe.read_all = lambda: et.rows
    probe.bind_to_window_title = lambda t: "x"
    c.probe = probe
    c.et = et
    c.catalog_file = config.CATALOG_FILE
    yield c
    try:
        c.root.destroy()
    except Exception:
        pass


def buttons(widget):
    import tkinter
    out = []
    for ch in widget.winfo_children():
        if isinstance(ch, tkinter.Button):
            out.append(ch.cget("text"))
        out += buttons(ch)
    return out


def press(widget, text):
    import tkinter
    for ch in widget.winfo_children():
        if isinstance(ch, tkinter.Button) and ch.cget("text") == text:
            return ch.invoke()
        r = press(ch, text)
        if r is not False:
            return r
    return False


def write_catalog(path, cat):
    with open(path, "w") as fh:
        json.dump(cat, fh)
