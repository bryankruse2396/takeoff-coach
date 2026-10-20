"""Finding eTakeoff's buttons and Quantity List on screen (automatically, or recorded by hand)."""
import ctypes
import json
import time
from ctypes import wintypes
import tkinter as tk
from pynput import keyboard

from coach import lessons
from coach.builtin_lessons import ALL_TARGETS, TARGETS
from coach.config import TARGETS_FILE
from coach.find_buttons import locate_targets
from coach.log import dlog
from coach.winapi import find_etakeoff, make_click_through, user32, win_rect


class Calibration:
    """Part of the Coach window (see coach/app.py)."""

    def _load_targets(self):
        try:
            with open(TARGETS_FILE, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def start_record(self, names):
        h, _ = find_etakeoff()
        if not h:
            self.status.config(text="Open eTakeoff Dimension first.", fg="#c0392b")
            return
        self.recording = {"queue": [(k, c) for k in names for c in ("top-left", "bottom-right")], "pts": {}}
        def _key(k):  # only F8 is used; return None so the listener keeps running
            if k == keyboard.Key.f8:
                self.q.put(("f8",))
        self.kb = keyboard.Listener(on_press=_key)
        self.kb.start()
        self._record_prompt()

    def _record_prompt(self):
        self._clear()
        self.h1.config(text="Record positions")
        if not self.recording["queue"]:
            with open(TARGETS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.targets, fh, indent=1)
            self.kb.stop()
            self.recording = None
            self._show_start()
            return
        name, corner = self.recording["queue"][0]
        self.sub.config(text=f"{len(self.recording['queue'])} captures left")
        if name == "qtylist":
            msg = ("Put the mouse ON the blue 'Quantity List' title bar, at its left end, and press F8."
                   if corner == "top-left" else
                   "Put the mouse at the bottom-right corner of the white area under 'Quantity List' "
                   "(just above 'Measurement Summary') and press F8.")
        else:
            msg = f"Hover the mouse over the {corner.upper()} corner of\n{ALL_TARGETS[name]}\nand press F8."
        tk.Label(self.body, text=msg,
                 wraplength=int(420 * self.k),
                 font=("Segoe UI", 12), bg="#f4f7fb", justify="left").pack(anchor="w", pady=10)
        tk.Button(self.body, text="Skip this button", font=self.font,
                  command=lambda: self._record_skip(name)).pack(anchor="w")

    def _record_skip(self, name):
        self.recording["queue"] = [x for x in self.recording["queue"] if x[0] != name]
        self._record_prompt()

    def _record_capture(self):
        h, _ = find_etakeoff()
        if not h:
            return
        l, t, _, _ = win_rect(h)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        name, corner = self.recording["queue"].pop(0)
        self.recording["pts"].setdefault(name, []).append((pt.x - l, pt.y - t))
        if corner == "bottom-right":
            (x1, y1), (x2, y2) = self.recording["pts"][name]
            self.targets[name] = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        self._record_prompt()

    def button_active(self, name):
        """Is this ribbon button lit up (eTakeoff shows the active tool in orange)?"""
        h, _ = find_etakeoff()
        if not h or not self.reader or name not in self.targets:
            return False
        l, t, _, _ = win_rect(h)
        x1, y1, x2, y2 = self.targets[name]
        w, hh, rgb = self.reader.grab((l + x1, t + y1, l + x2, t + y2))
        n = w * hh
        orange = sum(1 for i in range(0, len(rgb) - 2, 3 * 3)
                     if rgb[i] > 200 and 90 < rgb[i + 1] < 215 and rgb[i + 2] < 140)
        return n > 0 and orange * 3 > 0.25 * n

    def hover_fit(self, labels, rgb, w, h):
        """Find each button's real outline: point the mouse at it (no click), and see which pixels light up.
        The lit-up rectangle is exactly what eTakeoff treats as the button."""
        hwnd, _ = find_etakeoff()
        if not hwnd or not rgb:
            return {}
        user32.SetForegroundWindow(hwnd)
        l, t, _, _ = win_rect(hwnd)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        out = {}
        try:
            for key, (x1, y1, x2, y2) in labels.items():
                hh = max(8, y2 - y1)
                rx1, rx2 = max(0, int(x1 - 3 * hh)), min(w - 1, int(x2 + 2 * hh))
                ry1, ry2 = max(0, int(y1 - 1.5 * hh)), min(h - 1, int(y2 + 1.5 * hh))
                cx, cy = int(l + (x1 + x2) / 2), int(t + (y1 + y2) / 2)
                user32.SetCursorPos(cx + 1, cy)
                time.sleep(0.05)
                user32.SetCursorPos(cx, cy)
                time.sleep(0.22)
                sw, sh, shot = self.reader.grab((l + rx1, t + ry1, l + rx2 + 1, t + ry2 + 1))
                xs, ys = [], []
                for yy in range(sh):
                    for xx in range(sw):
                        i = (yy * sw + xx) * 3
                        j = ((ry1 + yy) * w + rx1 + xx) * 3
                        if j + 2 < len(rgb) and max(abs(shot[i] - rgb[j]), abs(shot[i + 1] - rgb[j + 1]),
                                                    abs(shot[i + 2] - rgb[j + 2])) > 24:
                            xs.append(xx)
                            ys.append(yy)
                if len(xs) < 0.5 * (x2 - x1) * hh:
                    dlog(f"hover fit {key}: no highlight seen")
                    continue
                # trim stray specks: keep the range holding 98% of the changed pixels
                xs.sort(); ys.sort()
                k = max(0, int(len(xs) * 0.01))
                bx1, bx2 = rx1 + xs[k], rx1 + xs[-1 - k]
                by1, by2 = ry1 + ys[k], ry1 + ys[-1 - k]
                if bx1 <= x1 + 2 and bx2 >= x2 - 2 and by2 - by1 < 3.5 * hh and bx2 - bx1 < (x2 - x1) + 6 * hh:
                    out[key] = [bx1, by1, bx2, by2]
                else:
                    dlog(f"hover fit {key}: odd shape {[bx1, by1, bx2, by2]}, kept the estimate")
        finally:
            user32.SetCursorPos(pt.x, pt.y)
        return out

    def qty_box(self):
        h, _ = find_etakeoff()
        if not h or user32.IsIconic(h) or "qtylist" not in self.targets:
            return None
        l, t, _, _ = win_rect(h)
        x1, y1, x2, y2 = self.targets["qtylist"]
        return (l + x1, t + y1, l + x2, t + y2)

    def test_reading(self):
        box = self.qty_box()
        if not self.reader or not box:
            self.status.config(text="Needs eTakeoff open, the screen-reading packages, and Record Quantity List.", fg="#c0392b")
            return
        self.status.config(text="Reading...", fg="#5a6878")
        self.reader.submit("test", *self._grab_clear(box))

    def _say(self, text, color):
        if getattr(self, "status", None) is not None and self.status.winfo_exists():
            self.status.config(text=text, fg=color)

    def auto_locate(self, then=None, pane_only=False):
        """Screenshot the eTakeoff window and find the buttons and Quantity List by their labels.
        pane_only: during a lesson, just find the Quantity List again (no mouse movement)."""
        h, _ = find_etakeoff()
        if not h or not self.reader:
            self._say("Needs eTakeoff open and the screen-reading packages.", "#c0392b")
            return
        if user32.IsIconic(h):
            self._say("eTakeoff is minimized. Restore it and try again.", "#c0392b")
            return
        user32.SetForegroundWindow(h)
        self._say("Finding eTakeoff's buttons...", "#5a6878")
        self.after_scan = then
        self.scan_pane_only = pane_only
        if not pane_only:
            self.cv.delete("all")  # don't let our own green outlines end up in the screenshot
            self.overlay.update_idletasks()
        self.root.after(300, lambda: self.reader.submit("scan", *self.reader.grab(win_rect(h))))

    def _scan_done(self, lines, err, w, h, rgb=None):
        then, self.after_scan = getattr(self, "after_scan", None), None
        if err:
            dlog(f"auto-locate error: {err}")
            if self.status.winfo_exists():
                self.status.config(text=f"Couldn't read the screen: {err}", fg="#c0392b")
            return
        found = locate_targets(lines or [], w, h, rgb)
        labels = found.pop("_labels", {})
        hwnd, _ = find_etakeoff()
        if hwnd:
            l0, t0, r0, b0 = win_rect(hwnd)
            self.scan_size = (r0 - l0, b0 - t0)
        if getattr(self, "scan_pane_only", False):
            self.scan_pane_only = False
            if "qtylist" in found:
                self.targets["qtylist"] = found["qtylist"]
                dlog(f"Quantity List found again at {found['qtylist']}")
            else:
                dlog("Quantity List not found on re-scan")
            if any(k not in found for k in ("select", "area", "length")):
                dlog("ribbon labels not visible on re-scan (window too narrow?)")
            if then:
                then()
            return
        # A narrow eTakeoff window hides the button names (icons only), so the buttons can't be read.
        btns = [k for k in TARGETS if k in found]
        if len(btns) < 3 and hwnd and not user32.IsZoomed(hwnd) and not getattr(self, "_maxed_once", False):
            self._maxed_once = True
            dlog("button names not visible: maximizing eTakeoff and scanning again")
            self._say("eTakeoff's window was too narrow to show the button names, so the coach maximized it. "
                      "Scanning again...", "#a15c00")
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            self.root.after(900, lambda: self.auto_locate(then=then))
            return
        self._maxed_once = False
        try:
            fitted = self.hover_fit(labels, rgb, w, h)
        except Exception as e:
            fitted = {}
            dlog(f"hover fit failed: {e!r}")
        found.update(fitted)
        dlog(f"auto-locate found: {found} (outlined by hover: {sorted(fitted)})")
        self.targets.update(found)
        with open(TARGETS_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.targets, fh, indent=1)
        # a step's button counts as found if it, or an equally good alternative ("also"), was found
        needed = {st["target"] for st in lessons.LESSON["steps"] if st["type"] == "click"
                  and not any(a in found for a in st.get("also", []))} | {"qtylist"}
        missing = sorted(needed - set(found))
        names = {**{k: (("Traces > " if k.startswith("trace_") else "") + v.split(" (")[0]) for k, v in TARGETS.items()},
                 "qtylist": "Quantity List"}
        stale = [m for m in missing if m in self.targets]
        txt = "Found: " + ", ".join(names[k] for k in found if k in names) + "."
        if missing:
            txt += (f" Not found: {', '.join(names[m] for m in missing)}"
                    + (" (using the last known position)." if len(stale) == len(missing) else
                       ". Make sure the Home tab and the Quantity List are showing, or use Record manually."))
        if self.status.winfo_exists():
            self.status.config(text=txt, fg="#2e7d32" if not missing else "#a15c00")
        self.show_found(found)
        if then and (not missing or len(stale) == len(missing)):
            then()
        else:
            self._located_now = False

    def show_found(self, found):
        """Briefly outline what was found on top of eTakeoff so the user can see it worked."""
        h, _ = find_etakeoff()
        if not h:
            return
        l, t, r, b = win_rect(h)
        self.overlay.deiconify()
        self.overlay.update_idletasks()
        make_click_through(self.overlay)
        self.overlay.geometry(f"{r - l}x{b - t}+{l}+{t}")
        self.cv.delete("all")
        for k, (x1, y1, x2, y2) in found.items():
            self.cv.create_rectangle(x1, y1, x2, y2, outline="#2e9e44", width=3)
        self.showing_found_until = time.time() + 2.5
