"""The start screen: sign-in, choosing a lesson or test, syncing and updating."""
import copy
import json
import threading
import tkinter as tk

from coach import lessons
from coach.builtin_lessons import PANES, TARGETS
from coach.cloud import Offline, SiteError
from coach.config import FROZEN
from coach.lessons import ANSWERS_FILE, apply_answer_key, lessons_from_catalog, load_lessons, read_answer_file, read_catalog, tier_label
from coach.log import dlog
from coach.updater import install_update


class StartScreen:
    """Part of the Coach window (see coach/app.py)."""

    def choose_lesson(self, title):
        les = next((l for l in self.lessons if title in (l["title"], tier_label(l))), None)
        if les:
            lessons.LESSON = copy.deepcopy(les)
            self.answers = apply_answer_key()
            self.lesson_title.set(tier_label(lessons.LESSON))
            self._show_start()

    def _pick_lessons(self):
        cat = read_catalog() if self.cloud.signed_in else None
        site = lessons_from_catalog(cat) if cat else []
        return site or load_lessons()

    def sync_in_background(self, catalog=False):
        def work():
            note = ""
            try:
                if self.cloud.signed_in:
                    try:
                        self.cloud.refresh_profile()
                    except SiteError as e:
                        note = str(e)
                    if catalog and not note:
                        self.cloud.download_catalog()
                    sent, left = self.cloud.flush()
                    note = note or (f"{left} result(s) waiting to upload." if left else
                                    (f"Uploaded {sent} result(s)." if sent else ""))
            except Offline:
                n = len(self.cloud.pending())
                note = "Offline: practice works; results upload when you're back online." + (
                    f" ({n} waiting)" if n else "")
            except Exception as e:
                dlog(f"sync failed: {e!r}")
                note = f"Couldn't reach the training site: {e}"
            self.ui(lambda: self._sync_done(note, catalog))
        threading.Thread(target=work, daemon=True).start()

    def _sync_done(self, note, catalog):
        self.cloud_note = note or self.cloud_note
        if self.cloud.account.get("name"):
            self.learner.set(self.cloud.account["name"])
        if catalog and self.step_i < 0 and not self.test:
            keep = lessons.LESSON.get("id")
            self.lessons = self._pick_lessons()
            lessons.LESSON = copy.deepcopy(next((l for l in self.lessons if l["id"] == keep), self.lessons[0]))
            self.answers = apply_answer_key()
            self.lesson_title.set(tier_label(lessons.LESSON))
        if self.step_i < 0 and not self.test:
            self._show_start()

    def _update_found(self, manifest):
        self.update_info = manifest
        dlog(f"update available: {manifest.get('version')}")
        if self.step_i < 0 and not self.test:
            self._show_start()

    def apply_update(self):
        m = self.update_info
        if not FROZEN:
            from tkinter import messagebox
            messagebox.showinfo("Update available", f"Takeoff Coach {m['version']} is available. Download the new "
                                "version from the training site.", parent=self.root)
            return
        self.status.config(text=f"Downloading Takeoff Coach {m['version']}...", fg="#5a6878")

        def work():
            try:
                install_update(m, lambda f: self.ui(lambda: self.status.config(
                    text=f"Downloading Takeoff Coach {m['version']}... {int(100 * f)}%")))
                self.ui(self.root.destroy)  # the update script restarts the new version
            except Exception as e:
                dlog(f"update failed: {e!r}")
                msg = f"Update failed: {e}"
                self.ui(lambda: self.status.config(text=msg, fg="#c0392b"))
        threading.Thread(target=work, daemon=True).start()

    def sign_in(self):
        email, pw = self.email.get().strip(), self.password.get()
        if not email or not pw:
            self.status.config(text="Enter your email and password.", fg="#c0392b")
            return
        self.status.config(text="Signing in...", fg="#5a6878")

        def work():
            try:
                self.cloud.sign_in(email, pw)
                self.cloud.download_catalog()
                sent, _ = self.cloud.flush()
                msg = None
            except Offline:
                msg = "Can't reach the training site. Check your internet connection."
            except SiteError as e:
                msg = ("Wrong email or password." if "invalid" in str(e).lower() else
                       "Confirm your email first: open the link the site sent you." if "confirm" in str(e).lower()
                       else str(e))
            except Exception as e:
                msg = f"Sign-in failed: {e}"

            def done():
                if msg:
                    self.status.config(text=msg, fg="#c0392b")
                else:
                    self.password.set("")
                    self._sync_done("Signed in.", True)
            self.ui(done)
        threading.Thread(target=work, daemon=True).start()

    def sign_out(self):
        from tkinter import messagebox
        n = len(self.cloud.pending())
        if n and not messagebox.askyesno("Sign out", f"{n} result(s) haven't uploaded yet. They'll upload the next "
                                         "time this account signs in. Sign out anyway?", parent=self.root):
            return
        self.cloud.sign_out()
        self.cloud_note = ""
        self._sync_done("", True)

    def save_answers(self):
        allans = read_answer_file()
        allans[lessons.LESSON["id"]] = self.answers
        with open(ANSWERS_FILE, "w", encoding="utf-8") as fh:
            json.dump(allans, fh, indent=1)
        if self.cloud.account.get("role") == "owner":
            items = [(k.split(".", 1), v) for k, v in self.answers.items() if "." in k and v.get("expected") is not None]

            def work():
                for (bid, sid), v in items:
                    try:
                        self.cloud.rpc("set_answer_key", p_block=bid, p_step=sid, p_expected=v["expected"],
                                       p_points=v.get("points"))
                    except Exception as e:
                        dlog(f"answer key upload for {bid}.{sid} failed: {e}")
                        return
                dlog(f"answer key uploaded ({len(items)} measurements)")
            threading.Thread(target=work, daemon=True).start()

    def _show_start(self):
        self._clear()
        self.h1.config(text="Takeoff Coach")
        b = self.body
        acct = self.cloud.account
        signed = self.cloud.signed_in
        if getattr(self, "update_info", None):
            urow = tk.Frame(b, bg="#e5eefb")
            urow.pack(fill="x", pady=(0, 6))
            tk.Label(urow, text=f"A new version ({self.update_info['version']}) is ready.", bg="#e5eefb",
                     font=("Segoe UI Semibold", 10)).pack(side="left", padx=8, pady=4)
            tk.Button(urow, text="Update now", font=("Segoe UI", 9), command=self.apply_update).pack(side="right", padx=6, pady=3)
        if signed:
            arow = tk.Frame(b, bg="#f4f7fb")
            arow.pack(fill="x")
            who = acct.get("name") or acct.get("email", "")
            tk.Label(arow, text=f"Signed in as {who}" + (f" · {acct['company']}" if acct.get("company") else ""),
                     font=("Segoe UI Semibold", 10), bg="#f4f7fb").pack(side="left")
            tk.Button(arow, text="Sign out", font=("Segoe UI", 9), command=self.sign_out).pack(side="right")
            if self.cloud_note:
                tk.Label(b, text=self.cloud_note, font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb",
                         wraplength=int(410 * self.k), justify="left").pack(anchor="w")
        else:
            tk.Label(b, text="Sign in with your training-site account. Your practice and tests are saved to it "
                             "automatically.", font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb",
                     wraplength=int(410 * self.k), justify="left").pack(anchor="w")
            g = tk.Frame(b, bg="#f4f7fb")
            g.pack(fill="x", pady=(2, 0))
            tk.Label(g, text="Email", font=self.font, bg="#f4f7fb").grid(row=0, column=0, sticky="w")
            tk.Entry(g, textvariable=self.email, font=self.font).grid(row=0, column=1, sticky="ew", padx=(6, 0))
            tk.Label(g, text="Password", font=self.font, bg="#f4f7fb").grid(row=1, column=0, sticky="w")
            pw = tk.Entry(g, textvariable=self.password, show="\u2022", font=self.font)
            pw.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(2, 0))
            pw.bind("<Return>", lambda e: self.sign_in())
            g.columnconfigure(1, weight=1)
            tk.Button(b, text="Sign in", font=("Segoe UI Semibold", 10), command=self.sign_in).pack(anchor="e", pady=(4, 0))
        if signed and self.training_project():
            tk.Label(b, text=f"Practice project: {self.training_project()}\nTest project: {self.training_project(True)}",
                     font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb", justify="left", anchor="w",
                     wraplength=int(420 * self.k)).pack(anchor="w", fill="x")
        mrow = tk.Frame(b, bg="#f4f7fb")
        mrow.pack(fill="x", pady=(8, 0))
        tk.Radiobutton(mrow, text="Practice", variable=self.mode, value="practice", bg="#f4f7fb", font=self.font,
                       command=self._show_start).pack(side="left")
        tk.Radiobutton(mrow, text="Test", variable=self.mode, value="test", bg="#f4f7fb", font=self.font,
                       command=self._show_start).pack(side="left", padx=(12, 0))
        cat = read_catalog() if signed else None
        tests = (cat or {}).get("tests") or []
        if self.mode.get() == "test":
            self.sub.config(text="Test: random tasks in a random order. No arrows; hints cost points.")
            if not tests:
                tk.Label(b, text="Sign in to see your tests." if not signed else "No tests are available yet.",
                         font=self.font, bg="#f4f7fb").pack(anchor="w", pady=(4, 0))
            else:
                names = [f"{t['tier'].title()} · {t['title']}" for t in tests]
                if self.test_choice.get() not in names:
                    self.test_choice.set(names[0])
                om = tk.OptionMenu(b, self.test_choice, *names, command=lambda _v: self._show_start())
                om.config(font=self.font)
                om.pack(anchor="w", fill="x", pady=(2, 0))
                t = tests[names.index(self.test_choice.get())]
                tk.Label(b, text=f"{t['draw_count']} tasks · pass at {t['pass_score']}%. A test can't be paused: "
                                 f"after {t['inactivity_minutes']} minutes with no activity in eTakeoff it ends and "
                                 "you start over. Tests need an internet connection.",
                         font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb", wraplength=int(410 * self.k),
                         justify="left").pack(anchor="w", pady=(2, 0))
        else:
            self.sub.config(text=f"Practice: {lessons.LESSON['title']} · {len(lessons.LESSON['steps'])} steps · arrows show where to click")
            if len(self.lessons) > 1:
                om = tk.OptionMenu(b, self.lesson_title, *[tier_label(l) for l in self.lessons],
                                   command=self.choose_lesson)
                om.config(font=self.font)
                om.pack(anchor="w", fill="x", pady=(2, 0))
            if acct.get("role") == "owner":
                tk.Checkbutton(b, text="Instructor: record my measurements as the answer key",
                               variable=self.instructor, bg="#f4f7fb", font=self.font).pack(anchor="w", pady=(4, 0))
                keyed = [st["id"] for st in lessons.LESSON["steps"] if st["id"] in self.answers]
                tk.Label(b, text=(f"Answer key: yours ({len(keyed)} measurements)" if keyed else
                                  "Answer key: guide values or the site's"),
                         font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb").pack(anchor="w")
            else:
                self.instructor.set(False)
        missing = [t for s in lessons.LESSON["steps"] if s["type"] == "click" for t in [s["target"]]
                   if t not in self.targets and not any(a in self.targets for a in s.get("also", []))]
        msg = (("The coach will find the buttons when the lesson starts." if self.reader else
                f"Button positions needed: {', '.join(sorted(set(missing)))}. Click Record manually first.")
               if missing else "Button positions known. They're re-checked each time a lesson starts.")
        self.status = tk.Label(b, text=msg, font=("Segoe UI", 9), fg="#a15c00" if missing else "#2e7d32",
                               bg="#f4f7fb", wraplength=int(410 * self.k), justify="left")
        self.status.pack(anchor="w", pady=(8, 4))
        if self.reader is None:
            ocr = ("Instant checking is off: screen-reading packages are missing. Running from source? Run "
                   f"pip install -r build/requirements.txt. ({self.reader_error})")
        elif "qtylist" not in self.targets:
            ocr = "Instant checking: click Record Quantity List so the coach can read your results."
        else:
            ocr = "Instant checking is on (reads the Quantity List)."
        tk.Label(b, text=ocr, font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb", wraplength=int(410 * self.k),
                 justify="left").pack(anchor="w")
        row = tk.Frame(b, bg="#f4f7fb")
        row.pack(fill="x", side="bottom")
        row2 = tk.Frame(b, bg="#f4f7fb")
        row2.pack(fill="x", side="bottom", pady=(0, 6))
        tk.Button(row2, text="Find buttons automatically", font=self.font,
                  command=lambda: self.auto_locate()).pack(side="left")
        tk.Button(row2, text="Test reading", font=self.font, command=self.test_reading).pack(side="left", padx=6)
        tk.Button(row, text="Record manually", command=lambda: self.start_record(list(TARGETS) + list(PANES)),
                  font=self.font).pack(side="left")
        can = signed and not (missing and not self.reader) and (self.mode.get() == "practice" or bool(tests))
        tk.Button(row, text="Start test" if self.mode.get() == "test" else "Start practice",
                  command=self.start_clicked, font=("Segoe UI Semibold", 10),
                  state="normal" if can else "disabled").pack(side="right")

    def start_clicked(self):
        if self.mode.get() == "test":
            tests = (read_catalog() or {}).get("tests") or []
            names = [f"{t['tier'].title()} \u00b7 {t['title']}" for t in tests]
            t = tests[names.index(self.test_choice.get())] if self.test_choice.get() in names else None
            return self.preflight(self.begin_test, test=True, steps=self._test_pool_steps(t["id"]) if t else [])
        les = next((l for l in self.lessons if tier_label(l) == self.lesson_title.get()), None)
        return self.preflight(self._start_practice, steps=(les or lessons.LESSON)["steps"])

    def _start_practice(self):
        les = next((l for l in self.lessons if tier_label(l) == self.lesson_title.get()), None)
        if les:
            lessons.LESSON = copy.deepcopy(les)
            self.answers = apply_answer_key()
        self.test = None
        self.start_lesson()

    def go_home(self):
        self.setup_token = None
        self._hide_warning()
        self.step_i = -1
        self.step_i_locked = -1
        self.results = []
        self.finish_at = None
        self._hide_overlay()
        self.cv.delete("all")
        self._show_start()

    def start_lesson_titled(self, title):
        self.choose_lesson(title)
        self.preflight(self.start_lesson, steps=lessons.LESSON["steps"])
