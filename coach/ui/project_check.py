"""Before practice or a test: the right training project is open, and test drawings are clean."""
import os
import tkinter as tk

from coach.config import PRACTICE_PREFIX, SAMPLE_DIR, TEST_PREFIX
from coach.etakeoff import Watcher
from coach.lessons import build_steps, read_catalog
from coach.log import dlog
from coach.projects import drawing_codes, norm_name, on_drawings, open_project_name
from coach.winapi import find_etakeoff


class ProjectCheck:
    """Part of the Coach window (see coach/app.py)."""

    def training_project(self, test=False):
        name = (self.cloud.account.get("name") or self.learner.get() or "").strip()
        return (TEST_PREFIX if test else PRACTICE_PREFIX) + name if name else ""

    def _probe(self):
        """A connection to eTakeoff for checks before a lesson (the lesson makes its own)."""
        if getattr(self, "probe", None) is None:
            self.probe = Watcher()
        return self.probe

    def _pre_say(self, text, fg):
        try:
            if self.status.winfo_exists():
                return self.status.config(text=text, fg=fg)
        except Exception:
            pass
        self._show_start()
        self.status.config(text=text, fg=fg)

    def preflight(self, then, test=False, steps=None):
        """Only train in the learner's own project, and start tests on clean drawings. Calls then() when ready."""
        self._stop_dwg_watch()
        want = self.training_project(test)
        h, title = find_etakeoff()
        if not h:
            return self._pre_say(text="Open eTakeoff Dimension first.", fg="#c0392b")
        if not want:
            return self._pre_say(text="Sign in first, so the coach knows your training project's name.",
                                      fg="#c0392b")
        if norm_name(open_project_name(title)) != norm_name(want):
            try:
                known = any(norm_name(n) == norm_name(want) for _, n in self._probe().projects())
            except Exception as e:
                dlog(f"project list: {e!r}")
                known = False
            if known:
                return self._pre_say(
                    text=f'Open your training project in eTakeoff: "{want}" (File > Recent Projects). '
                         + ("Tests only run in your own test project." if test else
                            "Practice only runs in your own practice project."), fg="#c0392b")
            return self.show_project_setup(then, test, steps)
        codes = drawing_codes(steps or [])
        if codes:
            try:
                w = self._probe()
                w.bind_to_window_title(title)
                left = [r for r in w.read_all().values() if on_drawings(r, codes)]
            except Exception as e:
                dlog(f"clean check: {e!r}")
                left = []
            if left:
                return self.show_clear_drawing(then, test, steps, len(left), codes)
        then()

    def show_project_setup(self, then, test, steps):
        """One-time: import the La Quinta sample as the learner's own training project."""
        import glob
        import subprocess
        want = self.training_project(test)
        self._clear()
        self.h1.config(text="Set up your test project" if test else "Set up your practice project")
        self.sub.config(text=("Once. All your tests happen in this project" if test else
                              "Once. All your practice happens in this project") + ", never in a real job.")
        b = self.body
        sample = sorted(glob.glob(os.path.join(SAMPLE_DIR, "*.tpxzip")))

        def open_folder():
            if sample:
                subprocess.Popen(["explorer", "/select,", sample[0]])
            elif os.path.isdir(SAMPLE_DIR):
                os.startfile(SAMPLE_DIR)
            else:
                self.status.config(text=f"The sample project isn't in {SAMPLE_DIR}. It comes with eTakeoff "
                                        "Dimension; ask whoever installed it.", fg="#c0392b")
        lines = [
            ("1.", "Click Open the sample folder. In the folder, double-click the La Quinta .tpxzip file "
                   "(LA QUINTA HOTEL - Extended SampleExport). eTakeoff imports it and opens Project Properties."),
            ("2.", "In Project Properties, replace the Description with exactly:"),
        ]
        for n, t in lines:
            row = tk.Frame(b, bg="#f4f7fb")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=n, font=self.font, bg="#f4f7fb", width=2, anchor="nw").pack(side="left", anchor="n")
            tk.Label(row, text=t, font=self.font, bg="#f4f7fb", justify="left", anchor="w",
                     wraplength=int(390 * self.k)).pack(side="left", fill="x")
        nrow = tk.Frame(b, bg="#f4f7fb")
        nrow.pack(fill="x", padx=(22, 0), pady=(0, 4))
        tk.Label(nrow, text=want, font=("Segoe UI Semibold", 11), bg="#ffffff", relief="solid", bd=1,
                 padx=6, pady=2).pack(side="left")

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(want)
            self.status.config(text="Name copied. Paste it into Description with Ctrl+V.", fg="#2e7d32")
        tk.Button(nrow, text="Copy", font=("Segoe UI", 9), command=copy).pack(side="left", padx=6)
        row = tk.Frame(b, bg="#f4f7fb")
        row.pack(fill="x", pady=2)
        tk.Label(row, text="3.", font=self.font, bg="#f4f7fb", width=2, anchor="nw").pack(side="left", anchor="n")
        tk.Label(row, text="Click OK. In Add Drawings to Project, leave every drawing ticked and click Add.",
                 font=self.font, bg="#f4f7fb", justify="left", anchor="w",
                 wraplength=int(390 * self.k)).pack(side="left", fill="x")
        self.status = tk.Label(b, text="Waiting for your training project to open in eTakeoff...",
                               font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb", wraplength=int(410 * self.k),
                               justify="left")
        self.status.pack(anchor="w", pady=(8, 0))
        bottom = tk.Frame(b, bg="#f4f7fb")
        bottom.pack(fill="x", side="bottom")
        tk.Button(bottom, text="Back", font=self.font, command=self.go_home).pack(side="left")
        tk.Button(bottom, text="Open the sample folder", font=("Segoe UI Semibold", 10),
                  command=open_folder).pack(side="right")
        token = object()
        self.setup_token = token

        def watch():
            if getattr(self, "setup_token", None) is not token:
                return  # left the screen
            h, title = find_etakeoff()
            if h and norm_name(open_project_name(title)) == norm_name(want):
                self.setup_token = None
                dlog(f"training project ready: {want}")
                self.status.config(text=f'Your training project "{want}" is ready.', fg="#2e7d32")
                self.root.after(1500, lambda: self.preflight(then, test, steps))
                return
            if h and open_project_name(title) and any(norm_name(open_project_name(title)).startswith(norm_name(p)) for p in (PRACTICE_PREFIX, TEST_PREFIX)):
                self.status.config(text=f'eTakeoff has "{open_project_name(title)}" open, but the name should be exactly '
                                        f'"{want}". Fix it in Home > Edit > Description, then click OK.', fg="#a15c00")
            self.root.after(2000, watch)
        self.root.after(2000, watch)

    def show_clear_drawing(self, then, test, steps, count, codes):
        sheets = ", ".join(sorted(codes))
        self._clear()
        self.h1.config(text="Clear the drawing first" if test else "Start on a clean drawing?")
        self.sub.config(text=f"{count} measurement{'s' if count != 1 else ''} already on {sheets}")
        tk.Label(self.body, text=(f"{'A test starts on a clean drawing.' if test else 'Old practice traces make the drawing hard to read.'} "
                                  f"In eTakeoff, open {sheets}, click Multi-Select, drag a box around the whole drawing "
                                  "and press Delete. Then click Check again."),
                 font=("Segoe UI", 11), bg="#f4f7fb", wraplength=int(420 * self.k), justify="left").pack(anchor="w")
        self.status = tk.Label(self.body, text="", font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb",
                               wraplength=int(410 * self.k), justify="left")
        self.status.pack(anchor="w", pady=(8, 0))
        bottom = tk.Frame(self.body, bg="#f4f7fb")
        bottom.pack(fill="x", side="bottom")
        leave = lambda go: (lambda: (self._stop_dwg_watch(), go()))
        tk.Button(bottom, text="Back", font=self.font, command=leave(self.go_home)).pack(side="left")
        if not test:
            tk.Button(bottom, text="Start anyway", font=self.font, command=leave(then)).pack(side="left", padx=6)
        tk.Button(bottom, text="Check again", font=("Segoe UI Semibold", 10),
                  command=lambda: self.preflight(then, test, steps)).pack(side="right")

        def show_dwg():  # which drawing is open now (read off the Navigation box), and how to get to the right one
            have = getattr(self, "dwg_now", None)
            try:
                if not have or not self.status.winfo_exists():
                    return
            except Exception:
                return
            if any(have.upper() == c.upper() for c in codes):
                self.status.config(text=f"You're on {have}. Now clear it as above, then click Check again.", fg="#2e7d32")
            else:
                self.status.config(text=f"You're on {have} now. First open {sheets}: on the Home tab, in Navigation, "
                                        f"click the drawing list and pick {sheets}.", fg="#a15c00")
        self.watch_codes, self.on_dwg_change = codes, show_dwg
        show_dwg()

    def _stop_dwg_watch(self):
        self.watch_codes = self.on_dwg_change = None

    def _test_pool_steps(self, test_id):
        """Steps of every block a test can draw (to know which drawings must be clean)."""
        cat = read_catalog() or {}
        t = next((x for x in cat.get("tests") or [] if x["id"] == test_id), None)
        pool = (t or {}).get("block_ids") or [b["id"] for b in cat.get("blocks") or [] if b.get("tier") == (t or {}).get("tier")]
        return build_steps(pool, cat.get("blocks") or [])
