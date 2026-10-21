"""Tests: starting, timing out, reviewing, submitting and closing."""
import datetime
import json
import os
import threading
import tkinter as tk

from coach import lessons
from coach.cloud import Offline
from coach.config import ACTIVE_TEST_FILE, COACH_VERSION
from coach.lessons import build_steps, lesson_problems, pick_descriptions, read_catalog
from coach.log import dlog
from coach.winapi import find_etakeoff


class TestFlow:
    """Part of the Coach window (see coach/app.py)."""

    def begin_test(self):
        tests = (read_catalog() or {}).get("tests") or []
        names = [f"{t['tier'].title()} · {t['title']}" for t in tests]
        if self.test_choice.get() not in names:
            return
        t = tests[names.index(self.test_choice.get())]
        h, _ = find_etakeoff()
        if not h:
            self.status.config(text="Open eTakeoff Dimension first.", fg="#c0392b")
            return
        self.status.config(text="Starting your test: the site is choosing your tasks...", fg="#5a6878")

        def work():
            try:
                res, err = self.cloud.rpc("start_test", p_test=t["id"]), None
            except Offline:
                res, err = None, "Tests need an internet connection. Check your connection and try again."
            except Exception as e:
                res, err = None, f"Couldn't start the test: {e}"
            self.ui(lambda: self._test_started(res, err))
        threading.Thread(target=work, daemon=True).start()

    def _test_started(self, res, err):
        if err or not res:
            self.status.config(text=err or "Couldn't start the test.", fg="#c0392b")
            return
        info = res["test"]
        blocks = res.get("blocks") or []
        lessons.LESSON = {"id": info["id"], "title": info["title"], "tier": info.get("tier"), "version": 1,
                  "drawing": "004 A1.1 1st Floor Plan", "scale": "3/32\" = 1'-0\"",
                  "grading": {"full_credit_within": 0.03, "pass_within": 0.10, "partial_score": 75},
                  "block_ids": [b["id"] for b in blocks],
                  "steps": pick_descriptions(build_steps([b["id"] for b in blocks], blocks, test=True),
                                             info.get("describe_percent"))}
        problems = lesson_problems(lessons.LESSON)
        if problems or not lessons.LESSON["steps"]:
            dlog(f"test {info['id']} can't run: {problems}")
            self.test = {"session_id": res["session_id"], "title": info["title"], "id": info["id"],
                         "pass_score": 0, "timeout": 300, "blocks": 0}
            self.end_test("abandoned")
            self._show_start()
            self.status.config(text="This test has a task this coach version can't run yet. It wasn't counted. "
                                    "Update Takeoff Coach, or tell your trainer.", fg="#c0392b")
            return
        self.answers = {}
        self.instructor.set(False)
        self.test = {"session_id": res["session_id"], "title": info["title"], "id": info["id"],
                     "pass_score": info.get("pass_score", 80),
                     "timeout": 60 * int(info.get("inactivity_minutes") or 5), "blocks": len(blocks)}
        with open(ACTIVE_TEST_FILE, "w", encoding="utf-8") as fh:
            json.dump({"session_id": res["session_id"], "title": info["title"],
                       "started": datetime.datetime.now().isoformat()}, fh)
        dlog(f"test {info['id']} started: {lessons.LESSON['block_ids']}")
        self.start_lesson()

    def _close_interrupted_test(self):
        """A test that was running when the coach closed can't be resumed: record it as abandoned."""
        try:
            with open(ACTIVE_TEST_FILE, encoding="utf-8") as fh:
                t = json.load(fh)
        except Exception:
            return
        self.cloud.queue({"kind": "finish_test", "session_id": t["session_id"], "status": "abandoned",
                          "summary": {"coach_version": COACH_VERSION}})
        os.remove(ACTIVE_TEST_FILE)
        self.cloud_note = f"Your last test ({t.get('title', '')}) was closed before it finished, so it was recorded as abandoned."

    def end_test(self, status, score=None, summary=None):
        """Close the test on the site (completed, timed_out or abandoned). Queued first so it is never lost."""
        t, self.test = self.test, None
        try:
            os.remove(ACTIVE_TEST_FILE)
        except OSError:
            pass
        item = {"kind": "finish_test", "session_id": t["session_id"], "status": status, "score": score,
                "summary": summary or {"coach_version": COACH_VERSION}}
        path = self.cloud.queue(dict(item))

        def work():
            res, err = None, None
            try:
                res = self.cloud.rpc("finish_test", p_session=item["session_id"], p_status=status, p_score=score,
                                     p_summary=item["summary"])
                os.remove(path)
                self.cloud.flush()
            except Offline:
                err = "offline"
            except Exception as e:
                err = str(e)
                dlog(f"finish_test failed: {e}")
            self.ui(lambda: self._test_closed(t, status, res, err))
        threading.Thread(target=work, daemon=True).start()
        return t

    def _test_closed(self, t, status, res, err):
        if status != "completed" or not hasattr(self, "result_note"):
            return
        if res:
            ok = res.get("passed")
            self.result_note.config(
                text=(f"PASSED · recorded on the training site (pass mark {res.get('pass_score', t['pass_score'])}%)."
                      if ok else f"Not passed yet: you need {res.get('pass_score', t['pass_score'])}%. "
                                 "Practice the skills below, then take the test again (you'll get new tasks)."),
                fg="#1b5e20" if ok else "#8e2a1f")
        else:
            self.result_note.config(text="Saved. It will upload to the training site when you're back online."
                                    if err == "offline" else f"Saved on this PC; upload failed ({err}). "
                                    "It will retry next time the coach starts.", fg="#a15c00")

    def void_test(self, status):
        """Inactivity timeout or the learner ended the test: it can't be finished or resumed."""
        t = self.end_test(status)
        self.step_i = len(lessons.LESSON["steps"])
        self._hide_overlay()
        self.cv.delete("all")
        self._hide_warning()
        self._clear()
        if status == "timed_out":
            self.h1.config(text="Test ended: no activity")
            msg = (f"There was no activity in eTakeoff for {t['timeout'] // 60} minutes, so this test ended. "
                   "Tests can't be paused or resumed. Start the test again when you're ready; you'll get a new "
                   "set of tasks.")
        else:
            self.h1.config(text="Test ended")
            msg = "You ended the test, so it was recorded as not finished. Start again any time for a new set of tasks."
        self.sub.config(text=t["title"])
        tk.Label(self.body, text=msg, font=("Segoe UI", 11), bg="#f4f7fb", wraplength=int(420 * self.k),
                 justify="left").pack(anchor="w")
        row = tk.Frame(self.body, bg="#f4f7fb")
        row.pack(fill="x", side="bottom")
        tk.Button(row, text="Home", font=self.font, command=self.go_home).pack(side="left")
        tk.Button(row, text="Start the test again", font=("Segoe UI Semibold", 10),
                  command=lambda: (self.go_home(), self.begin_test())).pack(side="right")

    def _show_warning(self, text):
        if not hasattr(self, "warn"):
            self.warn = tk.Label(self.root, font=("Segoe UI Semibold", 10), bg="#fff3cd", fg="#7a4b00",
                                 wraplength=int(430 * self.k), justify="left", padx=8, pady=4)
        self.warn.config(text=text)
        if not self.warn.winfo_ismapped():
            self.warn.pack(fill="x", padx=12, before=self.body)

    def _hide_warning(self):
        if hasattr(self, "warn") and self.warn.winfo_ismapped():
            self.warn.pack_forget()

    def review_test(self):
        self.step_i = len(lessons.LESSON["steps"])
        self.reviewing = True
        self._hide_overlay()
        self._clear()
        t = self.test
        self.h1.config(text="Review your test")
        self.sub.config(text=f"TEST \u00b7 {t['title']} \u00b7 not submitted yet")
        tk.Label(self.body, text=f"Redo any task you want to fix, then submit. You can't change it after you submit. "
                                 f"The test still ends after {t['timeout'] // 60} minutes with no activity.",
                 font=("Segoe UI", 10), bg="#f4f7fb", wraplength=int(420 * self.k), justify="left").pack(anchor="w")
        res = {r["id"]: r for r in self.results}
        box = tk.Frame(self.body, bg="#f4f7fb")
        box.pack(fill="x", pady=(8, 0))
        for n, bid in enumerate(lessons.LESSON.get("block_ids") or [], 1):
            steps = [st for st in lessons.LESSON["steps"] if st.get("block") == bid and not st.get("ungraded")]
            rs = [res.get(st["id"]) for st in steps]
            if any(r and r["status"] == "pending" for r in rs):
                mark, color = "\u2026 waiting for eTakeoff", "#a15c00"
            elif all(r and r["status"].startswith("passed") for r in rs):
                mark, color = "\u2713 done", "#1b5e20"
            else:
                mark, color = "\u2717 not right yet", "#8e2a1f"
            row = tk.Frame(box, bg="#f4f7fb")
            row.pack(fill="x", pady=2)
            title = next((st.get("block_title") for st in lessons.LESSON["steps"] if st.get("block") == bid), bid)
            tk.Label(row, text=f"{n}. {title}", font=self.font, bg="#f4f7fb", anchor="w").pack(side="left")
            tk.Button(row, text="Redo", font=("Segoe UI", 9), command=lambda b=bid: self.redo_block(b)).pack(side="right")
            tk.Label(row, text=mark, font=("Segoe UI", 9), fg=color, bg="#f4f7fb").pack(side="right", padx=8)
        bottom = tk.Frame(self.body, bg="#f4f7fb")
        bottom.pack(fill="x", side="bottom")
        tk.Button(bottom, text="End test", font=self.font, command=self.stop_lesson).pack(side="left")
        tk.Button(bottom, text="Submit test", font=("Segoe UI Semibold", 10), command=self.submit_test).pack(side="right")

    def redo_block(self, bid):
        ids = [st["id"] for st in lessons.LESSON["steps"] if st.get("block") == bid]
        for r in [r for r in self.results if r["id"] in ids]:
            self.results.remove(r)
            self.parked[r["id"]] = r
        first = min(i for i, st in enumerate(lessons.LESSON["steps"]) if st["id"] in ids)
        dlog(f"redo task {bid}")
        self.reviewing = False
        self.step_i = first - 1
        self.next_step()

    def submit_test(self):
        from tkinter import messagebox
        if messagebox.askyesno("Submit test", "Submit your test now? It can't be changed afterwards.",
                               parent=self.root):
            self.reviewing = False
            self.finish()
