"""Watching two small parts of eTakeoff's screen during practice:
- the drawing box in Home > Navigation, so a learner on the wrong drawing is shown how to get to the right one;
- the Traces list during "pick the trace" steps, so the coach follows the rows when the list is scrolled."""
import time

from coach import lessons
from coach.builtin_lessons import TARGETS
from coach.find_buttons import trace_rows
from coach.log import dlog
from coach.projects import open_sheet
from coach.winapi import find_etakeoff, user32, win_rect


class ScreenWatch:
    """Part of the Coach window (see coach/app.py)."""

    def _cur_step(self):
        steps = lessons.LESSON.get("steps") or []
        return steps[self.step_i] if 0 <= self.step_i < len(steps) else None

    @staticmethod
    def _is_trace_step(s):
        return bool(s) and s["type"] == "click" and str(s.get("target", "")).startswith("trace_")

    def _abs_box(self, key):
        h, _ = find_etakeoff()
        if not h or user32.IsIconic(h) or key not in self.targets:
            return None
        l, t, _, _ = win_rect(h)
        x1, y1, x2, y2 = self.targets[key]
        return (l + x1, t + y1, l + x2, t + y2)

    def _watch_tick(self):
        """Called every tick: now and then, read the drawing box or the Traces list."""
        if not self.reader or self.reader.jobs.qsize() >= 2 or getattr(self, "callout_drag", None):
            return
        s = self._cur_step()
        want_dwg = (s.get("dwg") if s and s["type"] != "info" and not self.test else None) or getattr(self, "watch_codes", None)
        if want_dwg and self.ticks % 15 == 0:
            box = self._abs_box("dwg_box")
            if box:
                self.reader.submit("dwg", *self._grab_clear(box))
        trace_click = getattr(self, "trace_click", None)
        fresh = trace_click and not trace_click.get("sent")
        if self._is_trace_step(s) and (fresh or self.ticks % 15 == 7):
            box = self._abs_box("traces_pane")
            if box:
                if fresh:
                    trace_click["sent"] = True
                self.reader.submit("traces", *self._grab_clear(box))

    def _on_watch_read(self, tag, lines, err):
        if err:
            dlog(f"screen read error ({tag}): {err}")
            return
        if tag == "dwg":
            return self._on_dwg_read(lines or [])
        return self._on_traces_read(lines or [])

    # ---- which drawing is open -------------------------------------------------------------
    def _on_dwg_read(self, lines):
        text = " ".join(ln["text"] for ln in sorted(lines, key=lambda d: (d["y"], d["x"])))
        code = open_sheet(text)
        if code is None:
            return  # couldn't read it (the list may be dropped down): keep what was known
        # the same reading twice in a row before acting on it, so one misread never shows a wrong message
        if code == getattr(self, "_dwg_seen", None):
            self._dwg_t = time.time()
        if code == getattr(self, "_dwg_seen", None) and code != getattr(self, "dwg_now", None):
            dlog(f"open drawing: {code} ({text!r})")
            self.dwg_now = code
            self._dwg_changed()
        self._dwg_seen = code

    def _dwg_changed(self):
        cb = getattr(self, "on_dwg_change", None)
        if cb:
            cb()

    def wrong_drawing(self, s):
        """(drawing open now, drawing the step needs) when the learner is on the wrong one, else None."""
        want = (s or {}).get("dwg")
        have = getattr(self, "dwg_now", None)
        if not want or not have or have.upper() == str(want).upper():
            return None
        if time.time() - getattr(self, "_dwg_t", 0) > 5:
            return None  # an old reading: they may have changed drawings since
        return have, want

    @staticmethod
    def wrong_drawing_text(have, want):
        return (f"This step is on drawing {want}, and you're on {have}. On the Home tab, in Navigation, click the "
                f"drawing list and pick {want}. (The arrows beside it step through the drawings too.)")

    # ---- the Traces list ---------------------------------------------------------------------
    def _on_traces_read(self, lines):
        s = self._cur_step()
        pane = self.targets.get("traces_pane")
        if not self._is_trace_step(s) or not pane:
            self.trace_click = None
            return
        px1, py1, px2, py2 = pane
        rows = trace_rows(lines, px2 - px1, py2 - py1)
        for key in ("area", "count", "length", "perimeter"):
            k = "trace_" + key
            if key in rows:
                x1, y1, x2, y2 = rows[key]
                self.targets[k] = [px1 + x1, py1 + y1, px1 + x2, py1 + y2]
            else:
                self.targets.pop(k, None)  # not showing: don't point at (or accept clicks on) an old spot
        hidden = s["target"] if s["target"] not in self.targets else None
        if hidden != getattr(self, "trace_hidden", None):
            dlog(f"{s['target']} {'not showing in the Traces list' if hidden else 'showing again'}; rows {rows}")
        self.trace_hidden = hidden
        click = getattr(self, "trace_click", None)
        if click and click.get("sent") and click["step"] == self.step_i:
            self.trace_click = None
            self._judge_trace_click(s, click["x"], click["y"])

    def trace_hidden_text(self, s):
        name = TARGETS[s["target"]].split(" (")[0]
        return (f"Can't see {name} in the Traces list? Scroll the list down, or drag the bottom edge of the Traces "
                "panel down to make it taller.")

    def in_traces_pane(self, xr, yr):
        p = self.targets.get("traces_pane")
        return bool(p) and p[0] <= xr <= p[2] and p[1] <= yr <= p[3]

    def note_trace_click(self, xr, yr):
        """A click in the Traces list during a "pick the trace" step: judged on a fresh reading of the list,
        since the rows move when it's scrolled."""
        self.trace_click = {"x": xr, "y": yr, "step": self.step_i, "t": time.time()}

    def _judge_trace_click(self, s, xr, yr):
        if getattr(self, "step_i_locked", -1) == self.step_i:
            return
        on = lambda k: k in self.targets and (lambda b: b[0] - 3 <= xr <= b[2] + 3 and b[1] - 3 <= yr <= b[3] + 3)(self.targets[k])
        if on(s["target"]):
            dlog(f"trace click on {s['target']} (fresh reading)")
            return self._pass("")
        other = next((k for k in ("trace_area", "trace_count", "trace_length", "trace_perimeter") if on(k)), None)
        if other:
            self.cur["wrong"] += 1
            self._render_step("Not quite. Try again." if self.test else
                              f"Not quite. That was {TARGETS[other].split(' (')[0]}, not {TARGETS[s['target']]}. Try again.",
                              ok=False)
