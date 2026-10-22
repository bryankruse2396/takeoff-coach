"""The on-screen instruction callout and arrows drawn over eTakeoff."""
import json
import time
import tkinter as tk

from coach import lessons
from coach.config import CALLOUT_DEFAULT, PREFS_FILE
from coach.log import dlog
from coach.winapi import find_etakeoff, make_click_through, print_window_region, user32, win_rect


class Callout:
    """Part of the Coach window (see coach/app.py)."""

    def draw_overlay(self):
        if time.time() < getattr(self, "showing_found_until", 0):
            return
        h, _ = find_etakeoff()
        active = 0 <= self.step_i < len(lessons.LESSON["steps"]) and lessons.LESSON["steps"][self.step_i]["type"] != "info"
        if not h or user32.IsIconic(h) or not active:
            self._hide_overlay()
            return
        l, t, r, b = win_rect(h)
        w, ht = r - l, b - t
        if self.overlay.state() == "withdrawn":
            self.overlay.deiconify()
            self.overlay.update_idletasks()
            make_click_through(self.overlay)
            self._overlay_geo = self._overlay_shapes = None
        geo = f"{w}x{ht}+{l}+{t}"
        if geo != getattr(self, "_overlay_geo", None):
            self.overlay.geometry(geo)
            self._overlay_geo = geo
        shapes = []  # what to draw; the canvas is only redrawn when this changes, so nothing flickers
        s = lessons.LESSON["steps"][self.step_i]
        text = s["text"]
        if self.flash and time.time() < self.flash[1]:
            text, good = self.flash[0], True
        else:
            good = False
        target = self.targets.get(s.get("target")) if s["type"] == "click" and not good else None
        if self.test:
            # Tests: the task is in the coach window; nothing is drawn on eTakeoff except a used hint's box.
            self.callout.withdraw()
            self.callout_text = None
            if target and self.hint_on:
                tx1, ty1, tx2, ty2 = target
                shapes.append(("rect", tx1 - 3, ty1 - 3, tx2 + 3, ty2 + 3))
            self._draw_shapes(shapes)
            return
        bx, by, bw, bh = self._show_callout(f"{self.step_i + 1}. {text}", good, l, t, w, ht)
        if target:
            tx1, ty1, tx2, ty2 = target
            shapes.append(("rect", tx1 - 3, ty1 - 3, tx2 + 3, ty2 + 3))
            # arrow from the callout edge nearest the button
            cx, cy = (tx1 + tx2) // 2, (ty1 + ty2) // 2
            sx = min(max(cx, bx + 12), bx + bw - 12)
            if cy < by:
                sy, ey = by, ty2 + 6
            elif cy > by + bh:
                sy, ey = by + bh, ty1 - 6
            else:  # button beside the callout
                sy, ey = cy, cy
                sx = bx if cx < bx else bx + bw
                cx = tx2 + 6 if cx < bx else tx1 - 6
            if not (bx <= cx <= bx + bw and by <= cy <= by + bh):
                shapes.append(("arrow", sx, sy, cx, ey))
        self._draw_shapes(shapes)

    def _draw_shapes(self, shapes):
        """Redraw the overlay only when the box or arrow actually changed (redrawing every tick flickers)."""
        cv = self.cv
        # also redraw if another screen cleared or drew on the canvas since (calibration does)
        if shapes == getattr(self, "_overlay_shapes", None) and cv.find_all() == getattr(self, "_overlay_items", None):
            return
        self._overlay_shapes = shapes
        cv.delete("all")
        for kind, x1, y1, x2, y2 in shapes:
            if kind == "rect":
                cv.create_rectangle(x1, y1, x2, y2, outline="#e53935", width=3)
            else:
                cv.create_line(x1, y1, x2, y2, fill="#e53935", width=4, arrow=tk.LAST, arrowshape=(18, 22, 7))
        self._overlay_items = cv.find_all()

    def _build_callout(self):
        try:
            with open(PREFS_FILE, encoding="utf-8") as fh:
                self.callout_pos = tuple(json.load(fh).get("callout", CALLOUT_DEFAULT))
        except Exception:
            self.callout_pos = CALLOUT_DEFAULT
        c = self.callout = tk.Toplevel(self.root)
        c.overrideredirect(True)
        c.attributes("-topmost", True)
        c.configure(bg="#2a7fd0")  # shows as the border
        inner = tk.Frame(c, bg="#ffffff", cursor="fleur")
        inner.pack(fill="both", expand=True, padx=3, pady=3)
        self.callout_grip = tk.Label(inner, text="\u2630  drag to move  \u00b7  double-click to reset", bg="#ffffff",
                                     fg="#8a97a8", font=("Segoe UI", 8), cursor="fleur", anchor="w")
        self.callout_grip.pack(fill="x", padx=12, pady=(4, 0))
        self.callout_label = tk.Label(inner, bg="#ffffff", font=("Segoe UI", 13), justify="left", anchor="w",
                                      cursor="fleur")
        self.callout_label.pack(fill="both", padx=14, pady=(0, 10))
        for wdg in (c, inner, self.callout_grip, self.callout_label):
            wdg.bind("<ButtonPress-1>", self._callout_press)
            wdg.bind("<B1-Motion>", self._callout_drag)
            wdg.bind("<ButtonRelease-1>", self._callout_release)
            wdg.bind("<Double-Button-1>", self._callout_reset)
        self.callout_text, self.callout_drag = None, None
        c.withdraw()

    def _callout_press(self, ev):
        self.callout_drag = (ev.x_root - self.callout.winfo_rootx(), ev.y_root - self.callout.winfo_rooty())

    def _callout_drag(self, ev):
        if self.callout_drag:
            dx, dy = self.callout_drag
            self.callout.geometry(f"+{ev.x_root - dx}+{ev.y_root - dy}")

    def _callout_release(self, ev):
        if not self.callout_drag:
            return
        self.callout_drag = None
        h, _ = find_etakeoff()
        if not h:
            return
        l, t, r, b = win_rect(h)
        rx = (self.callout.winfo_rootx() - l) / max(1, r - l)
        ry = (self.callout.winfo_rooty() - t) / max(1, b - t)
        self.callout_pos = (min(0.95, max(0.0, rx)), min(0.95, max(0.0, ry)))
        self._save_prefs()
        self.draw_overlay()

    def _callout_reset(self, ev=None):
        self.callout_drag = None
        self.callout_pos = CALLOUT_DEFAULT
        self._save_prefs()
        self.draw_overlay()

    def _save_prefs(self):
        try:
            with open(PREFS_FILE, "w", encoding="utf-8") as fh:
                json.dump({"callout": list(self.callout_pos)}, fh)
        except OSError as e:
            dlog(f"could not save prefs: {e!r}")

    def _off_qty_list(self, x, y, cw, ch, l, t, w, ht):
        """The coach reads the Quantity List off the screen, so the callout must never sit on it.
        If it would, show it just beside the list instead (the learner's chosen spot is kept)."""
        q = self.targets.get("qtylist")
        if not q:
            return x, y
        qx1, qy1, qx2, qy2 = l + q[0], t + q[1], l + q[2], t + q[3]
        if x >= qx2 or x + cw <= qx1 or y >= qy2 or y + ch <= qy1:
            return x, y
        options = [(qx2 + 10, y), (x, qy2 + 10), (x, qy1 - ch - 10), (qx1 - cw - 10, y)]
        for nx, ny in options:
            if l <= nx and nx + cw <= l + w and t <= ny and ny + ch <= t + ht:
                return nx, ny
        return qx2 + 10, y

    def _grab_clear(self, box):
        """Screenshot the Quantity List without the callout in the picture.
        If the callout is over the list, ask eTakeoff for its own picture of that spot (nothing flashes);
        only if Windows can't do that, hide the callout for an instant instead."""
        c = getattr(self, "callout", None)
        over = False
        try:
            if c is not None and c.state() != "withdrawn":
                cx, cy = c.winfo_rootx(), c.winfo_rooty()
                cw, ch = c.winfo_width(), c.winfo_height()
                l, t, r, b = box
                over = not (cx >= r or cx + cw <= l or cy >= b or cy + ch <= t)
                if over != getattr(self, "_was_over", False):
                    dlog(f"callout {'over' if over else 'clear of'} the Quantity List: callout {(cx, cy, cw, ch)} list {box}")
                self._was_over = over
        except Exception:
            over = False
        if not over:
            return self.reader.grab(box)
        h, _ = find_etakeoff()
        try:
            shot = print_window_region(h, box) if h else None
        except Exception as e:
            dlog(f"PrintWindow failed: {e!r}")
            shot = None
        if shot:
            return shot
        c.withdraw()
        c.update()
        time.sleep(0.05)  # let Windows repaint what was under it
        try:
            return self.reader.grab(box)
        finally:
            c.deiconify()
            c.lift()

    def _hide_overlay(self):
        self._overlay_geo = self._overlay_shapes = None
        self.overlay.withdraw()
        self.callout.withdraw()
        self.callout_text = None

    def _show_callout(self, text, good, l, t, w, ht):
        """Place the callout (where the learner left it) and return its box in eTakeoff-window coordinates."""
        c = self.callout
        if text != self.callout_text:
            self.callout_text = text
            self.callout_label.config(text=text, fg="#1b5e20" if good else "#24384f",
                                      wraplength=min(520, int(w * 0.42)))
        c.update_idletasks()
        cw, ch = c.winfo_reqwidth(), c.winfo_reqheight()
        if self.callout_drag:  # being dragged: it is where the mouse put it
            x, y = c.winfo_rootx(), c.winfo_rooty()
        else:  # follow eTakeoff if its window moves; keep fully on it
            x = l + min(int(self.callout_pos[0] * w), max(0, w - cw))
            y = t + min(int(self.callout_pos[1] * ht), max(0, ht - ch))
            x, y = self._off_qty_list(x, y, cw, ch, l, t, w, ht)
            c.geometry(f"+{x}+{y}")
        if c.state() == "withdrawn":
            c.deiconify()  # placed first, so it never flashes up in the screen corner
            c.update_idletasks()
            # tool window (no taskbar button) that never takes the keyboard from eTakeoff when dragged
            hwnd = user32.GetAncestor(c.winfo_id(), 2)
            user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x80 | 0x08000000)
            c.lift()
        elif self.ticks % 30 == 0:  # keep it above the overlay now and then, not on every redraw
            c.lift()
        return x - l, y - t, cw, ch
