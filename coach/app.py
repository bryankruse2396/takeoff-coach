"""The Coach window. Each screen or job lives in its own part under coach/ui/; this file joins them
and holds the window itself, the timer loop (tick) and run()."""
import copy
import os
import queue
import threading
import time
import traceback
import tkinter as tk
from pynput import mouse

from coach import lessons
from coach.cloud import Cloud
from coach.config import ACTIVE_TEST_FILE, COACH_VERSION, copy_notices
from coach.lessons import apply_answer_key, tier_label
from coach.log import dlog
from coach.ocr import QtyReader
from coach.qty_list import parse_qty_list
from coach.updater import check_for_update, just_updated
from coach.winapi import find_etakeoff, foreground_title, pid_of, user32, win_rect
from coach.ui.start_screen import StartScreen
from coach.ui.calibration import Calibration
from coach.ui.project_check import ProjectCheck
from coach.ui.test_flow import TestFlow
from coach.ui.lesson_flow import LessonFlow
from coach.ui.checking import Checking
from coach.ui.callout import Callout
from coach.ui.results import Results
from coach.ui.screen_watch import ScreenWatch


class Coach(StartScreen, Calibration, ProjectCheck, TestFlow, LessonFlow, Checking, Callout, Results, ScreenWatch):
    BG = "#ff00fe"  # overlay transparency key

    def __init__(self):
        copy_notices()
        self.root = tk.Tk()
        self.root.title(f"Takeoff Coach {COACH_VERSION}")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#f4f7fb")
        self.q = queue.Queue()
        self.targets = self._load_targets()
        self.watcher = None
        self.mode = tk.StringVar(value="practice")
        self.cloud = Cloud()
        self.learner = tk.StringVar(value=self.cloud.account.get("name") or os.environ.get("USERNAME", ""))
        self.instructor = tk.BooleanVar(value=False)
        self.test = None              # the test being taken: session id, timeout, pass mark
        self.test_choice = tk.StringVar(value="")
        self.email = tk.StringVar(value=self.cloud.account.get("email", ""))
        self.password = tk.StringVar(value="")
        self.cloud_note = ""
        self.last_activity = time.time()
        self.lessons = self._pick_lessons()
        lessons.LESSON = copy.deepcopy(self.lessons[0])
        self.lesson_title = tk.StringVar(value=tier_label(lessons.LESSON))
        self.answers = apply_answer_key()
        self.step_i = -1
        self.results = []
        self.hint_on = False
        self.recording = None
        self.kb = None
        self.flash = None
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-transparentcolor", self.BG)
        self.overlay.configure(bg=self.BG)
        self.cv = tk.Canvas(self.overlay, bg=self.BG, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.overlay.withdraw()
        self._build_callout()
        try:
            self.reader = QtyReader()
            self.reader_error = None
        except Exception as e:
            self.reader, self.reader_error = None, f"{e.__class__.__name__}: {e}"
        self._build_panel()
        self._show_start()
        old = just_updated()
        if old:
            self.status.config(text=f"Takeoff Coach updated itself from {old} to {COACH_VERSION}.", fg="#2e7d32")
        def _click(x, y, button, pressed):  # must return None: returning False stops pynput's listener
            if pressed and button == mouse.Button.left:
                self.q.put(("click", x, y))
        self.ml = mouse.Listener(on_click=_click)
        self.ml.start()
        self.clip_seq = user32.GetClipboardSequenceNumber()
        self.qty_hash = None
        self.qty_last = None       # last parsed Quantity List
        self.passed_vals = set()
        self.finish_at = None
        self.last_click_t = 0
        self.last_click_xy = (0, 0)
        self.lesson_kb = None
        self.root.after(100, self.tick)
        self.ticks = 0
        self._close_interrupted_test()
        self.sync_in_background(catalog=True)
        self.update_info = None
        threading.Thread(target=lambda: (lambda m: m and self.ui(lambda: self._update_found(m)))(check_for_update()),
                         daemon=True).start()

    def _build_panel(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        k = self.k = max(1.0, self.root.winfo_fpixels("1i") / 96)  # Windows display scaling (125%, 150%...)
        w, h = int(460 * k), int(420 * k)
        self.root.geometry(f"{w}x{h}+{sw - w - int(20 * k)}+{sh - h - int(70 * k)}")
        self.root.minsize(int(380 * k), int(320 * k))
        f = ("Segoe UI", 10)
        self.h1 = tk.Label(self.root, font=("Segoe UI Semibold", 13), bg="#f4f7fb", anchor="w")
        self.h1.pack(fill="x", padx=12, pady=(10, 0))
        self.sub = tk.Label(self.root, font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb", anchor="w")
        self.sub.pack(fill="x", padx=12)
        self.body = tk.Frame(self.root, bg="#f4f7fb")
        self.body.pack(fill="both", expand=True, padx=12, pady=8)
        self.font = f

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def ui(self, fn):
        """Run fn on the window's thread (background work must not touch the window directly)."""
        self.q.put(("ui", fn))

    def tick(self):
        try:
            while True:
                ev = self.q.get_nowait()
                if ev[0] == "ui":
                    try:
                        ev[1]()
                    except Exception:
                        dlog("ui callback failed:\n" + traceback.format_exc())
                    continue
                if ev[0] in ("click", "finish"):
                    self.last_activity = time.time()
                if ev[0] == "click":
                    self.on_click(ev[1], ev[2])
                elif ev[0] == "disconnect":
                    self._disconnect_used("G key")
                elif ev[0] == "f8" and self.recording:
                    self._record_capture()
                elif ev[0] == "finish":
                    h, _ = find_etakeoff()
                    if h and pid_of(user32.GetForegroundWindow()) == pid_of(h):
                        cur = lessons.LESSON["steps"][self.step_i] if 0 <= self.step_i < len(lessons.LESSON["steps"]) else {}
                        if cur.get("type") == "describe" and ev[1] == "s":
                            continue  # they're typing the description; S is just a letter here
                        if ev[1] == "s":
                            # S only finishes drawing (eTakeoff goes back to Select). The learner may still
                            # adjust corners, so nothing is graded until they press Enter.
                            dlog("S pressed (drawing finished, waiting for Enter)")
                            if cur.get("type") == "measure":
                                self._render_step("Drawing finished. Adjust any corner if you need to, then press "
                                                  "Enter to submit.", ok=None)
                                self.nudged = True
                            continue
                        dlog("Enter pressed in eTakeoff: checking")
                        self.check_src = "key"
                        self.finish_at = time.time() + 0.6  # let eTakeoff update the Quantity List first
        except queue.Empty:
            pass
        self.ticks += 1
        if self.test and 0 <= self.step_i < len(lessons.LESSON["steps"]):
            idle = time.time() - self.last_activity
            left = self.test["timeout"] - idle
            if left <= 0:
                dlog(f"test timed out after {idle:.0f}s without activity")
                self.void_test("timed_out")
            elif left <= 60:
                self._show_warning(f"No activity for {int(idle // 60)} min. The test ends in {int(left)} seconds "
                                   "unless you continue in eTakeoff.")
            else:
                self._hide_warning()
        if self.ticks % 20 == 0 and 0 <= self.step_i < len(lessons.LESSON["steps"]) and getattr(self, "scan_size", None):
            hw, _ = find_etakeoff()
            if hw and not user32.IsIconic(hw):
                l0, t0, r0, b0 = win_rect(hw)
                if (r0 - l0, b0 - t0) != self.scan_size:
                    self.scan_size = (r0 - l0, b0 - t0)
                    dlog(f"eTakeoff window resized to {self.scan_size}: finding the Quantity List again")
                    self.auto_locate(pane_only=True)
        try:
            seq = user32.GetClipboardSequenceNumber()
            if seq != self.clip_seq:
                self.clip_seq = seq
                dlog(f"clipboard sequence changed (front window: {foreground_title()[:60]!r})")
                if self.watcher and 0 <= self.step_i < len(lessons.LESSON["steps"]):
                    time.sleep(0.15)  # let eTakeoff finish writing the clipboard
                    rec = self.watcher.from_clipboard()
                    dlog("clipboard changed: " + (f"{rec['trace']!r} {rec['desc']!r} qty {rec['qty']:.2f} pts {rec['points']}"
                                                  if rec else "no eTakeoff measurement on it (ignored)"))
                    if rec:
                        self.on_clipboard(rec)
        except Exception:
            traceback.print_exc()
        try:
            self._tick_screen()
        except Exception:
            traceback.print_exc()
        try:
            if self.watcher and self.step_i >= 0 and self.ticks % 20 == 0:
                self.verify_published(self.watcher.poll())
            if self.ticks % 3 == 0:
                self.draw_overlay()
        except Exception:
            traceback.print_exc()
        self.root.after(100, self.tick)

    def _tick_screen(self):
        if not self.reader:
            return
        # Back in Select mode during a measuring step (S, Esc, right-click > Select...)? Remind them to submit.
        if self.ticks % 5 == 0 and 0 <= self.step_i < len(lessons.LESSON["steps"]) and \
                lessons.LESSON["steps"][self.step_i]["type"] == "measure" and "select" in self.targets and self.cur.get("clicks", 0) >= 2:
            act = self.button_active("select")
            if act and not getattr(self, "select_was_active", True) and not getattr(self, "nudged", False):
                dlog("eTakeoff is back in Select mode")
                self._render_step("Back in Select mode. If your measurement is done, press Enter to submit.", ok=None)
                self.nudged = True
            self.select_was_active = act
        # results from the OCR worker
        try:
            while True:
                tag, lines, err, w, h, rgb = self.reader.results.get_nowait()
                if tag == "scan":
                    self._scan_done(lines, err, w, h, rgb)
                    continue
                if tag in ("dwg", "traces"):
                    self._on_watch_read(tag, lines, err)
                    continue
                if tag == "test":
                    if not self.status.winfo_exists():
                        continue
                    if err:
                        self.status.config(text=f"Reading failed: {err}", fg="#c0392b")
                    else:
                        p = parse_qty_list(lines or [], w, h, rgb)
                        txt = " | ".join(l["text"] for l in sorted(lines, key=lambda d: d["y"])) or "(no text found)"
                        self.status.config(text=f"Read: {txt}\nUnderstood: " + (
                            f"name '{p['header']}', values {p['values']}, main quantity {p['primary']}" if p else "no quantities"),
                            fg="#2e7d32" if p else "#a15c00")
                    continue
                if err:
                    dlog(f"screen read error ({tag}): {err}")
                    continue
                parsed = parse_qty_list(lines, w, h, rgb)
                if parsed is None:
                    if tag == "check":
                        raw = " | ".join(l["text"] for l in sorted(lines or [], key=lambda d: d["y"])) or "(no text)"
                        dlog(f"check reading not understood: {raw}  box={self.qty_box()}")
                        if getattr(self, "pane_refound_step", None) != self.step_i:
                            # maybe the Quantity List was moved or resized: find it again, then check again
                            self.pane_refound_step = self.step_i
                            self.auto_locate(then=lambda: setattr(self, "finish_at", time.time() + 0.3), pane_only=True)
                            continue
                        if 0 <= self.step_i < len(lessons.LESSON["steps"]) and lessons.LESSON["steps"][self.step_i]["type"] != "click":
                            self._render_step("The coach couldn't read the Quantity List. Make sure it's showing your "
                                              "measurement, then click Check again. Or right-click your measurement, choose Copy "
                                              "Measurement > Copy Total, and the coach will grade the copy.", ok=False)
                    continue
                if self.qty_last is None or parsed["sig"] != self.qty_last["sig"]:
                    dlog(f"Quantity List ({tag}): '{parsed['header']}' {parsed['values']} main={parsed['primary']}")
                self.qty_last = parsed
                # The Quantity List updates live while corners are being clicked, so only grade a reading
                # taken after the learner finished the measurement (S, Enter, double-click) or pressed Check again.
                if tag == "check":
                    self.on_qtylist(parsed, forced=True)
                elif 0 <= self.step_i < len(lessons.LESSON["steps"]) and lessons.LESSON["steps"][self.step_i]["type"] in ("describe", "click"):
                    self.on_qtylist(parsed, forced=False)  # passes as soon as the right name shows; never fails
        except queue.Empty:
            pass
        self._watch_tick()
        if not (0 <= self.step_i < len(lessons.LESSON["steps"])):
            return
        box = self.qty_box()
        if not box:
            return
        if self.finish_at and time.time() >= self.finish_at:
            self.finish_at = None
            dlog(f"checking Quantity List at {box}")
            self.reader.submit("check", *self._grab_clear(box))
            return
        # background reading (for the log and for "what was showing when this step began"), once a second
        if self.ticks % 10 == 0 and not getattr(self, "callout_drag", None):
            w, h, rgb = self._grab_clear(box)
            hsh = hash(rgb)
            if hsh != self.qty_hash and self.reader.jobs.qsize() < 2:
                self.qty_hash = hsh
                self.reader.submit("live", w, h, rgb)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self.test:  # window closed mid-test: it can't be resumed
                self.cloud.queue({"kind": "finish_test", "session_id": self.test["session_id"],
                                  "status": "abandoned", "summary": {"coach_version": COACH_VERSION}})
                try:
                    os.remove(ACTIVE_TEST_FILE)
                except OSError:
                    pass
            self.ml.stop()
            if self.kb:
                self.kb.stop()
            if self.lesson_kb:
                self.lesson_kb.stop()
