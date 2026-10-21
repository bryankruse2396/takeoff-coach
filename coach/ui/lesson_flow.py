"""Moving through a lesson's steps: next, back, hint, skip, pass and miss."""
import copy
import datetime
import time
import tkinter as tk
from pynput import keyboard

from coach import lessons
from coach.builtin_lessons import TARGETS
from coach.etakeoff import Watcher
from coach.lessons import apply_answer_key, build_steps, read_catalog
from coach.log import dlog
from coach.winapi import find_etakeoff


class LessonFlow:
    """Part of the Coach window (see coach/app.py)."""

    def start_lesson(self):
        if self.reader and not getattr(self, "_located_now", False):
            self._located_now = True
            return self.auto_locate(then=self.start_lesson)
        self._located_now = False
        h, title = find_etakeoff()
        if not h:
            self.status.config(text="Open eTakeoff Dimension first.", fg="#c0392b")
            return
        try:
            self.watcher = Watcher()
            name = self.watcher.bind_to_window_title(title)
            if not name:
                raise RuntimeError("Could not match the open project. Open a project in eTakeoff and try again.")
            self.watcher.start_baseline()
        except Exception as e:
            self.status.config(text=f"Could not read eTakeoff: {e}", fg="#c0392b")
            if self.test:
                self.end_test("abandoned")
            return
        self.project_name = name
        self.started = datetime.datetime.now()
        self.started_utc = datetime.datetime.now(datetime.timezone.utc)
        self.last_activity = time.time()
        if self.lesson_kb is None:
            def _finish_key(k):  # only S and Enter matter; nothing else is looked at or kept
                if k == keyboard.Key.enter:
                    self.q.put(("finish", "enter"))
                elif getattr(k, "char", None) in ("s", "S"):
                    self.q.put(("finish", "s"))
            self.lesson_kb = keyboard.Listener(on_press=_finish_key)
            self.lesson_kb.start()
        self.results = []
        self.parked = {}
        self.reviewing = False
        self.step_i = -1
        self.step_i_locked = -1
        self.finish_at = None
        self.next_step()

    def next_step(self):
        """Open the next step without a result: the next one after this, else any earlier one left open
        (a step redone from the test review). None left: a test goes to its review, practice finishes."""
        steps = lessons.LESSON["steps"]
        done = {r["id"] for r in self.results}
        later = [i for i, st in enumerate(steps) if st["id"] not in done and i > self.step_i]
        left = later or [i for i, st in enumerate(steps) if st["id"] not in done]
        if not left:
            return self.review_test() if self.test else self.finish()
        self._open_step(left[0])

    def _open_step(self, idx, carry=None):
        self.step_i = idx
        self.reviewing = False
        s = lessons.LESSON["steps"][idx]
        carry = carry or self.parked.pop(s["id"], None)
        self.nudged, self.select_was_active = False, True
        self.cur = {"id": s["id"], "skill": s["skill"], "type": s["type"],
                    "ungraded": bool(s.get("ungraded")), "wrong": 0,
                    "hints": 0, "failed": set(), "clicks": 0, "t0": time.time(), "status": "", "note": ""}
        self.hint_on = False
        # measurements that already existed when this step began are never graded for it
        self.step_known = {k[0] for k in self.watcher.state} | self.watcher.baseline_guids
        if carry:  # reopened (Back, or Redo in a test review): what happened before still counts
            for k in ("wrong", "hints", "clicks"):
                self.cur[k] = carry.get(k, 0)
            self.cur["failed"] = set(carry.get("failed", set()))
            for k in ("missed_skills", "misses"):
                if carry.get(k):
                    self.cur[k] = list(carry[k])
            self.cur["t0"] = time.time() - carry.get("seconds", 0)
            self.cur["reopened"] = carry.get("reopened", 0) + (1 if carry.get("status") else 0)
            if carry.get("_known") is not None:
                self.step_known = carry["_known"]
            if carry.get("_passed_sig") is not None:
                self.passed_vals.discard(carry["_passed_sig"])  # its own measurement may be submitted again
        self.cur["_known"] = self.step_known
        self.qty_at_start = self.qty_last["sig"] if self.qty_last else None
        self.finish_at = None
        self.qty_failed_sigs = set()
        dlog(f"step {s['id']} start")
        self._render_step()

    def _render_step(self, feedback="", ok=None):
        s = lessons.LESSON["steps"][self.step_i]
        self._clear()
        self.h1.config(text=f"Step {self.step_i + 1} of {len(lessons.LESSON['steps'])}")
        if self.test:
            n = lessons.LESSON["block_ids"].index(s["block"]) + 1 if s.get("block") in lessons.LESSON.get("block_ids", []) else 0
            self.sub.config(text=f"TEST · {self.test['title']} · Task {n} of {len(lessons.LESSON['block_ids'])}: "
                                 f"{s.get('block_title', '')}")
        else:
            self.sub.config(text=f"{lessons.LESSON['title']} · {s.get('block_title') or ''}{' · ' if s.get('block_title') else ''}"
                                 f"{s['skill']}")
        tk.Label(self.body, text=s["text"], font=("Segoe UI", 11), bg="#f4f7fb", wraplength=int(420 * self.k),
                 justify="left").pack(anchor="w")
        if feedback:
            tk.Label(self.body, text=feedback, font=("Segoe UI", 10), wraplength=int(420 * self.k), justify="left",
                     bg="#e3f2e4" if ok else ("#e6eefb" if ok is None else "#fbe5e2"),
                     fg="#1b5e20" if ok else ("#1f3d6b" if ok is None else "#8e2a1f"),
                     padx=8, pady=6).pack(fill="x", pady=(8, 0))
        stats = f"Wrong clicks: {self.cur['wrong']}   Attempts that missed: {len(self.cur['failed'])}   Hints: {self.cur['hints']}"
        tk.Label(self.body, text=stats, font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb").pack(anchor="w", pady=(8, 0))
        row = tk.Frame(self.body, bg="#f4f7fb")
        row.pack(fill="x", side="bottom")
        brow = tk.Frame(self.body, bg="#f4f7fb")
        brow.pack(anchor="w", pady=(10, 0))
        tk.Button(brow, text="Check again", command=self.check_now, font=self.font).pack(side="left")
        if s["type"] in ("measure", "describe"):
            if s["type"] == "measure":
                tk.Button(brow, text="Done, check it later", command=self.defer, font=self.font).pack(side="left", padx=6)
        if self._back_target() is not None:
            tk.Button(row, text="\u2190 Back", command=self.go_back, font=self.font).pack(side="left", padx=(0, 6))
        tk.Button(row, text="Hint", command=self.hint, font=self.font).pack(side="left")
        tk.Button(row, text="Skip step", command=self.skip, font=self.font).pack(side="left", padx=6)
        tk.Button(row, text="End test" if self.test else "Stop lesson", command=self.stop_lesson,
                  font=self.font).pack(side="right")

    def hint(self):
        self.cur["hints"] += 1
        self.hint_on = True
        s = lessons.LESSON["steps"][self.step_i]
        dwg, scale = lessons.LESSON.get("drawing", "the right drawing"), lessons.LESSON.get("scale", "the drawing's scale")
        tips = {"click": f"Look for {TARGETS.get(s.get('target'), '')}. It's outlined in red now.",
                "measure": f"Check the drawing is {dwg} and the scale is {scale}. Click each corner once; Backspace removes the last point. Press S to finish drawing. Fix any corner you need to, then press Enter to submit.",
                "describe": "Click the measurement to select it and press D (or right-click it, Edit Measurement Description). Type the exact words from the step and press Enter."}
        self._render_step(s.get("hint") or tips[s["type"]], ok=False)

    def skip(self):
        self._close_step("skipped", 0)

    def _back_target(self):
        """Index of the step Back reopens: the nearest earlier step that has a result."""
        done = {r["id"] for r in self.results}
        earlier = [i for i in range(self.step_i) if lessons.LESSON["steps"][i]["id"] in done]
        return earlier[-1] if earlier else None

    def go_back(self):
        if getattr(self, "step_i_locked", -1) == self.step_i:
            return  # this step is passing right now
        idx = self._back_target()
        if idx is None:
            return
        sid = lessons.LESSON["steps"][idx]["id"]
        prev = next(r for r in self.results if r["id"] == sid)
        self.results.remove(prev)
        self.cur["seconds"] = round(time.time() - self.cur["t0"], 1)
        self.parked[self.cur["id"]] = self.cur  # this step's tries so far are kept for when it comes back
        dlog(f"back: {self.cur['id']} -> {sid}")
        self.step_i_locked = -1
        self._open_step(idx, carry=prev)

    def _missed_tasks(self, results):
        """[(title, lesson_id, steps)] for each task with a step not right on the first try, in practice wording."""
        cat = read_catalog() or {}
        blocks = cat.get("blocks") or []
        by_id = {b["id"]: b for b in blocks}
        missed = [r for r in results if not r.get("ungraded")
                  and not (r["status"].startswith("passed") and r["score"] == 100)]
        out, seen = [], set()
        for r in missed:
            st = next((x for x in lessons.LESSON["steps"] if x["id"] == r["id"]), None)
            bid = st.get("block") if st else None
            if bid and bid in by_id:
                if bid in seen:
                    continue
                seen.add(bid)
                lesson = next((l["id"] for l in cat.get("lessons") or [] if bid in (l.get("block_ids") or [])),
                              lessons.LESSON["id"])
                out.append((by_id[bid]["title"], lesson, build_steps([bid], blocks)))
            elif st and not self.test_was:
                # a lesson file without blocks: this step plus the measurement it describes
                need = [x for x in lessons.LESSON["steps"] if x["id"] in (st["id"], st.get("of"))]
                if st["id"] not in seen:
                    seen.add(st["id"])
                    out.append((st["text"][:60] + ("..." if len(st["text"]) > 60 else ""), lessons.LESSON["id"], need))
        return out

    def start_retry(self, title, lesson_id, steps):
        base = lessons.LESSON
        lessons.LESSON = {"id": lesson_id, "title": f"{title} (practice)", "tier": base.get("tier"), "version": 1,
                  "drawing": base.get("drawing", "004 A1.1 1st Floor Plan"), "scale": base.get("scale", ""),
                  "grading": base.get("grading", {"full_credit_within": 0.03, "pass_within": 0.10, "partial_score": 75}),
                  "block_ids": list(dict.fromkeys(st.get("block") for st in steps if st.get("block"))),
                  "steps": copy.deepcopy(steps)}
        self.test = None
        self.mode.set("practice")
        self.answers = apply_answer_key()
        dlog(f"practice what was missed: {title}")
        self.preflight(self.start_lesson, steps=lessons.LESSON["steps"])

    def _close_step(self, status, score, note=""):
        self.cur.update(status=status, score=score, note=note, seconds=round(time.time() - self.cur["t0"], 1))
        self.results.append(self.cur)
        self.next_step()

    def _score(self):
        base = max(0, 100 - 25 * self.cur["wrong"] - 25 * len(self.cur["failed"]) - 20 * self.cur["hints"])
        if self.cur.get("partial"):
            base = min(base, lessons.LESSON.get("grading", {}).get("partial_score", 75))
        return base

    def _miss(self, msg):
        """Feedback after a missed attempt. In a test the coach doesn't coach: the detail is kept for the
        results (shown on the site afterwards) but the learner only hears that it isn't right yet."""
        if self.test:
            self.cur.setdefault("misses", []).append(msg)
            return self._render_step("That isn't right yet. Check your work, fix it or redraw it, and submit again.", ok=False)
        return self._render_step(msg, ok=False)

    def _pass(self, msg, partial=False):
        if self.test:  # no answer-key numbers or tips during a test
            self.cur["note"] = msg
            msg = ""
        first = self.cur["wrong"] == 0 and not self.cur["failed"] and self.cur["hints"] == 0
        cheer = ("Passed." if partial else
                 "Good job! You got it on the first try!" if first else "Got it.")
        self.cur["partial"] = bool(partial)
        self.flash = (f"{cheer}\n{msg}" if msg else cheer, time.time() + 1.8)
        self._render_step(f"{cheer} {msg}", ok=True)
        score = self._score()
        note = msg or self.cur.get("note", "")
        self.root.after(1800, lambda: self._close_step("passed", score, note))
        self.step_i_locked = self.step_i

    def stop_lesson(self):
        """Stop part-way: save what was done (or not), then go back to the start screen."""
        from tkinter import messagebox
        if self.test:
            if messagebox.askyesno("End test", "End this test now?\n\nIt will be recorded as not finished, and "
                                   "tests can't be resumed. You can start a new test any time.", parent=self.root):
                dlog("test ended by the learner")
                self.void_test("abandoned")
            return
        ans = messagebox.askyesnocancel("Stop lesson", "Stop this practice?\n\nYes: save your score for the steps "
                                        "done so far.\nNo: stop without a score (your practice time still counts)."
                                        "\nCancel: keep going.", parent=self.root)
        if ans is None:
            return
        if ans:
            self.finish()
        else:
            dlog("lesson stopped without a score")
            self._upload_practice(status="stopped")
            self.go_home()
