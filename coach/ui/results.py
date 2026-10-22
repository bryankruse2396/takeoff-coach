"""The results screen and uploading practice sessions."""
import csv
import datetime
import json
import os
import uuid
import tkinter as tk

from coach import lessons
from coach.config import COACH_VERSION, RESULTS_DIR


class Results:
    """Part of the Coach window (see coach/app.py)."""

    def _upload_practice(self, status, total=None, weak=()):
        """Queue this practice session for the site and send it in the background."""
        if not hasattr(self, "started_utc") or not self.cloud.signed_in:
            return
        ended = datetime.datetime.now(datetime.timezone.utc)
        res = [r for r in (self.results or []) if r.get("type") != "info"]  # intro and recap screens aren't results
        rec = {"client_id": str(uuid.uuid4()), "mode": "practice", "lesson_id": lessons.LESSON["id"], "title": lessons.LESSON["title"],
               "tier": lessons.LESSON.get("tier"), "status": status,
               "block_ids": list(dict.fromkeys(st.get("block") for st in lessons.LESSON["steps"] if st.get("block"))),
               "started_at": self.started_utc.isoformat(), "ended_at": ended.isoformat(),
               "seconds": int((ended - self.started_utc).total_seconds()), "score": total,
               "steps_total": sum(1 for st in lessons.LESSON["steps"] if st["type"] != "info"),
               "steps_first_try": sum(1 for r in res if r["status"].startswith("passed") and r["score"] == 100),
               "wrong_clicks": sum(r.get("wrong", 0) for r in res), "hints": sum(r.get("hints", 0) for r in res),
               "work_on": [k for _, k in weak],
               "steps": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in r.items()
                          if k != "t0" and not k.startswith("_")} for r in res],
               "project": getattr(self, "project_name", ""), "coach_version": COACH_VERSION}
        self.cloud.queue(rec)
        self.sync_in_background()

    def finish(self):
        if self.step_i < 0:
            self.root.destroy()
            return
        done_ids = {r["id"] for r in self.results}
        for s in lessons.LESSON["steps"]:
            if s["id"] not in done_ids:
                self.results.append({"id": s["id"], "skill": s["skill"], "type": s["type"],
                                     "ungraded": bool(s.get("ungraded")),
                                     "status": "not reached", "score": 0, "wrong": 0, "hints": 0,
                                     "failed": set(), "clicks": 0, "seconds": 0, "note": ""})
        self.step_i = len(lessons.LESSON["steps"])
        self.reviewing = False
        self._hide_overlay()
        order = {st["id"]: i for i, st in enumerate(lessons.LESSON["steps"])}
        self.results.sort(key=lambda r: order.get(r["id"], 999))
        self.test_was = bool(self.test)
        scored = [r for r in self.results if not r.get("ungraded")] or self.results
        total = round(sum(r["score"] for r in scored) / len(scored))
        skills = {}
        for r in scored:
            skills.setdefault(r["skill"], []).append(r["score"])
            for ms in r.get("missed_skills", []):
                if ms and ms != r["skill"]:
                    skills.setdefault(ms, []).append(50)
        weak = sorted([(sum(v) / len(v), k) for k, v in skills.items() if sum(v) / len(v) < 80])
        os.makedirs(RESULTS_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        base = os.path.join(RESULTS_DIR, f"{self.learner.get() or 'learner'}-{stamp}")
        out = {"learner": self.learner.get(), "lesson": lessons.LESSON["title"], "lesson_id": lessons.LESSON["id"],
               "lesson_version": lessons.LESSON.get("version", 1), "mode": self.mode.get(),
               "project": getattr(self, "project_name", ""), "started": str(getattr(self, "started", "")),
               "score": total, "work_on": [k for _, k in weak],
               "steps": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in r.items()
                          if k != "t0" and not k.startswith("_")} for r in self.results if r.get("type") != "info"]}
        with open(base + ".json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=str)
        test = self.test
        if test:
            self.end_test("completed", total, {
                "steps_total": len(scored),
                "steps_first_try": sum(1 for r in scored if r["status"].startswith("passed") and r["score"] == 100),
                "wrong_clicks": sum(r.get("wrong", 0) for r in self.results),
                "hints": sum(r.get("hints", 0) for r in self.results),
                "work_on": [k for _, k in weak], "steps": out["steps"], "project": out["project"],
                "coach_version": COACH_VERSION})
        else:
            self._upload_practice("completed", total, weak)
        with open(base + ".csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["step", "skill", "status", "score", "wrong clicks", "missed attempts", "hints", "seconds", "note"])
            for r in self.results:
                if r.get("type") == "info":
                    continue
                w.writerow([r["id"], r["skill"], r["status"], r["score"], r["wrong"],
                            len(r["failed"]), r["hints"], r.get("seconds", 0), r.get("note", "")])
        self._clear()
        self.h1.config(text=f"Score: {total}%")
        self._hide_warning()
        self.sub.config(text=f"{lessons.LESSON['title']} · {'Test' if test else 'Practice'} · "
                             + ("checking with the training site..." if test else
                                "saved and uploading to your training record" if self.cloud.signed_in else
                                "saved to Documents\\TakeoffCoach"))
        if test:
            self.result_note = tk.Label(self.body, text="Sending your result to the training site...",
                                        font=("Segoe UI Semibold", 10), fg="#5a6878", bg="#f4f7fb",
                                        wraplength=int(420 * self.k), justify="left")
            self.result_note.pack(anchor="w", pady=(0, 6))
        first = sum(1 for r in scored if r["status"].startswith("passed") and r["score"] == 100)
        pending = [r["id"] for r in self.results if r["status"] == "pending"]
        if pending:
            tk.Label(self.body, text=f"Not checked yet: {', '.join(pending)}. eTakeoff only publishes a measurement after "
                                     "the next one is drawn.", font=("Segoe UI", 9), fg="#a15c00", bg="#f4f7fb",
                     wraplength=int(420 * self.k), justify="left").pack(anchor="w")
        tk.Label(self.body, text=f"{first} of {len(scored)} scored steps right on the first try.",
                 font=("Segoe UI", 11), bg="#f4f7fb").pack(anchor="w")
        if weak:
            tk.Label(self.body, text="Work on:", font=("Segoe UI Semibold", 10), bg="#f4f7fb").pack(anchor="w", pady=(8, 0))
            for sc, k in weak:
                tk.Label(self.body, text=f"\u2022 {k} ({sc:.0f}%)",
                         font=("Segoe UI", 10), bg="#f4f7fb").pack(anchor="w")
        else:
            tk.Label(self.body, text="Every skill at 80% or better.", font=("Segoe UI", 10), bg="#f4f7fb").pack(anchor="w")
        missed = self._missed_tasks(scored)
        if missed:
            tk.Label(self.body, text=("Your test is submitted. Practice what you missed:" if test else
                                      "Practice what you missed:"),
                     font=("Segoe UI Semibold", 10), bg="#f4f7fb").pack(anchor="w", pady=(8, 2))
            for title, lid, steps in missed[:5]:
                tk.Button(self.body, text=f"\u25b6 {title}", font=("Segoe UI", 9), anchor="w",
                          command=lambda a=title, b=lid, c=steps: self.start_retry(a, b, c)).pack(fill="x", pady=1)
        row = tk.Frame(self.body, bg="#f4f7fb")
        row.pack(fill="x", side="bottom")
        titles = [l["title"] for l in self.lessons]
        nxt = (titles[titles.index(lessons.LESSON["title"]) + 1] if not test and lessons.LESSON["title"] in titles[:-1] else None)
        row2 = tk.Frame(self.body, bg="#f4f7fb")
        row2.pack(fill="x", side="bottom", pady=(0, 6))
        if test:
            tk.Button(row2, text="Take the test again (new tasks)", font=self.font,
                      command=lambda: (self.go_home(), self.begin_test())).pack(side="left")
        else:
            if nxt:
                tk.Button(row2, text=f"Next lesson: {nxt}", font=("Segoe UI Semibold", 10),
                          command=lambda: self.start_lesson_titled(nxt)).pack(side="left")
            tk.Button(row2, text="Try again", font=self.font,
                      command=lambda t=lessons.LESSON["title"]: self.start_lesson_titled(t)).pack(side="left", padx=6)
        tk.Button(row, text="Home", font=self.font, command=self.go_home).pack(side="left")
        tk.Button(row, text="Open results folder", font=self.font,
                  command=lambda: os.startfile(RESULTS_DIR)).pack(side="left", padx=6)
        tk.Button(row, text="Close", font=self.font, command=self.root.destroy).pack(side="right")
