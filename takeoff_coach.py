r"""
Takeoff Coach  v0.19  (prototype)
================================
Coaches a learner through eTakeoff Dimension steps on top of the real program:
  * shows the instruction as a callout over eTakeoff, with an arrow to the button (Practice mode)
  * tracks clicks and counts wrong ones
  * reads each finished measurement off eTakeoff's Quantity List (instant) and grades the real quantity,
    then double-checks it against eTakeoff's own data (point count, drawing) once eTakeoff publishes it
  * scores every step and saves a results report
  * signs in to the training site, downloads lessons and tests, and uploads every session automatically
  * Tests: the site draws random blocks in a random order; a test can't be paused or resumed, and it
    ends after a set time with no activity

Learners use the packaged program, TakeoffCoach.exe (download it from the training site; it updates
itself). To run it from source instead:
Setup (once):
    pip install comtypes pynput          (already installed if you ran the probes)
    pip install mss pillow winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Globalization
Run (PowerShell), with eTakeoff open on the project you will practice in:
    cd $env:USERPROFILE\Downloads
    python takeoff_coach.py
The coach finds eTakeoff's buttons and Quantity List by reading the screen when a lesson starts.
If it can't, "Record manually" lets you point them out (hover + F8).

Privacy: while a lesson runs it records mouse clicks inside the eTakeoff window
and reads measurement quantities. During a lesson it reacts only to S and Enter pressed in
eTakeoff (the "finish measurement" keys) and nothing typed is recorded; during "Record" it
reacts only to F8. Results are saved to Documents\TakeoffCoach and sent to your account on the
training site: the lesson or test, time spent, each step's result and score. Nothing you type is sent.
"""
import csv
import ctypes
import datetime
import copy
import json
import os
import difflib
import queue
import re
import struct
import threading
import sys
import time
import traceback
from ctypes import wintypes

# Use real screen pixels everywhere (mouse hook, window positions, our windows).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
import urllib.error
import urllib.request
import uuid

try:
    from pynput import mouse, keyboard
except ImportError:
    sys.exit("Missing package. Run:  pip install pynput comtypes")

FROZEN = getattr(sys, "frozen", False)  # True when running as TakeoffCoach.exe
EXE_PATH = sys.executable if FROZEN else None
HERE = (os.path.join(os.path.expanduser("~"), "Documents", "TakeoffCoach") if FROZEN
        else os.path.dirname(os.path.abspath(__file__)))
os.makedirs(HERE, exist_ok=True)
TARGETS_FILE = os.path.join(HERE, "coach_targets.json")
RESULTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "TakeoffCoach")

COACH_VERSION = "0.19"
# Training site (Supabase). The publishable key is meant to be public; what each account can do is
# enforced by the database's security rules.
SITE_URL = "https://ylhhgqxbngvpqmtceois.supabase.co"
SITE_KEY = "sb_publishable_H7oV3RkzMEyRfxCQcRjK2w_NdJPz8sT"
ACCOUNT_FILE = os.path.join(RESULTS_DIR, "account.json")      # sign-in token, so learners sign in once
CATALOG_FILE = os.path.join(RESULTS_DIR, "catalog.json")      # last lessons/tests downloaded (works offline)
OUTBOX_DIR = os.path.join(RESULTS_DIR, "outbox")              # results waiting to upload
ACTIVE_TEST_FILE = os.path.join(RESULTS_DIR, "active_test.json")  # a test that was running when the coach closed
# Where the coach looks for a newer version of itself: {"version": "0.20", "url": "...exe", "sha256": "..."}
UPDATE_MANIFEST = "https://github.com/bryankruse2396/takeoff-coach/releases/latest/download/latest.json"
TIERS = ["basic", "intermediate", "advanced", "expert"]
TLB = r"C:\Program Files (x86)\eTakeoff\RView\ETkoInfc64.tlb" if struct.calcsize("P") == 8 \
    else r"C:\Program Files (x86)\eTakeoff\RView\ETkoInfc.tlb"
user32 = ctypes.windll.user32

# ------------------------------------------------------------------ lesson
# Buttons the learner must click. Positions are recorded once per screen layout ("Record buttons").
TARGETS = {
    "multiselect": "Multi-Select (Home tab)",
    "select": "Select (Home tab)",
    "length": "Length (Home tab)",
    "area": "Area (Home tab)",
    "perimeter": "Perimeter (Home tab)",
    "count": "Count (Home tab)",
    "trace_area": "Area (Traces panel)",
    "trace_count": "Count (Traces panel)",
    "trace_length": "Length (Traces panel)",
    "trace_perimeter": "Perimeter (Traces panel)",
}
RIBBON = ("multiselect", "select", "length", "area", "perimeter", "count")

# Screen areas the coach reads (recorded the same way as buttons).
PANES = {
    "qtylist": "the Quantity List pane",
}
ALL_TARGETS = {**TARGETS, **PANES}

# Built-in lessons, written to the lessons folder on first run (and replaced when a newer built-in
# version ships). After that the coach reads the lessons folder: the same files the website will serve.
BUILTIN_LESSONS = [
    {
        "id": "getting_around",
        "title": "Getting Around the Window",
        "order": 1,
        "version": 1,
        "guide": "eTakeoff Dimension Online Training Guide",
        "drawing": "004 A1.1 1st Floor Plan",
        "scale": "3/32\" = 1'-0\"",
        "steps": [
            {"id": "ms", "type": "click", "target": "multiselect", "skill": "Navigating the ribbon", "page": 11,
             "text": "On the Home tab, click Multi-Select and notice that your cursor changes."},
            {"id": "sel", "type": "click", "target": "select", "skill": "Navigating the ribbon", "page": 11,
             "text": "Click Select to change it back again."},
        ],
    },
    {
        # Guide p. 28, "Working with Polar mode", practice steps 1-10.
        "id": "taking_measurements",
        "title": "Taking Measurements",
        "order": 2,
        "version": 2,
        "guide": "eTakeoff Dimension Online Training Guide",
        "drawing": "004 A1.1 1st Floor Plan",
        "scale": "3/32\" = 1'-0\"",
        "grading": {"full_credit_within": 0.03, "pass_within": 0.10, "partial_score": 75},
        "steps": [
            {"id": "areabtn", "type": "click", "target": "trace_area", "also": ["area"],
             "skill": "Choosing the right trace", "page": 28,
             "text": "In drawing 004 A1.1 1st Floor Plan, zoom in to grid B5, where you see the Laundry room. "
                     "Then, in the Traces control panel, click Area."},
            {"id": "laundry", "type": "measure", "kind": "area", "expected": 604.42, "points": 8, "dwg": "A1.1",
             "skill": "Polar mode and direction", "page": 28,
             "known": [["bath and elevator included", 1.03, 1.6]],
             "text": "Starting at the top left of the Laundry room, hold down the Ctrl key and click each corner in "
                     "clockwise sequence to define its area, excluding the bathroom and elevator (8 points total). "
                     "Press S when you are finished, then press Enter to submit."},
            {"id": "perbtn", "type": "click", "target": "trace_perimeter", "also": ["perimeter"],
             "skill": "Choosing the right trace", "page": 28,
             "text": "Next, click Perimeter in the Traces control panel."},
            {"id": "elec", "type": "measure", "kind": "perimeter", "expected": 48.86, "points": 4, "dwg": "A1.1",
             "skill": "Choosing the right trace", "page": 28,
             "text": "Directly to the left of the Laundry room, click to measure the perimeter of the Electrical "
                     "room (4 points total). Press S when you are finished, then press Enter to submit."},
            {"id": "desc_laundry", "type": "describe", "of": "laundry", "answer": "Laundry Room Area",
             "skill": "Finish, undo, describe", "page": 28,
             "text": "Return to the area trace over the Laundry room. Click to select it, and then press D. "
                     "Enter  Laundry Room Area  and press Enter. Notice the description now appears in the "
                     "Quantity List and Measurement Summary panes."},
            {"id": "desc_elec", "type": "describe", "of": "elec", "answer": "Electrical Room",
             "skill": "Finish, undo, describe", "page": 28,
             "text": "Assign the description  Electrical Room  to the perimeter trace you completed: click it, "
                     "press D, type the description and press Enter."},
        ],
    },
]
BUILTIN_LESSON = BUILTIN_LESSONS[1]

ANSWERS_FILE = os.path.join(HERE, "coach_answers.json")
LESSONS_DIR = os.path.join(HERE, "lessons")
LESSON = copy.deepcopy(BUILTIN_LESSON)


def load_lessons():
    """All lesson files in the lessons folder, sorted by their 'order' (then title). Bad files are skipped and logged."""
    if not os.path.isdir(LESSONS_DIR):
        os.makedirs(LESSONS_DIR, exist_ok=True)
    for les in BUILTIN_LESSONS:
        path = os.path.join(LESSONS_DIR, les["id"] + ".json")
        try:
            with open(path, encoding="utf-8") as fh:
                have = json.load(fh).get("version", 0)
        except Exception:
            have = -1
        if have < les["version"]:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(les, fh, indent=1)
            dlog(f"lesson file {les['id']}.json written (version {les['version']})")
    out = []
    for name in sorted(os.listdir(LESSONS_DIR)):
        if not name.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(LESSONS_DIR, name), encoding="utf-8") as fh:
                les = json.load(fh)
            problems = lesson_problems(les)
            if problems:
                dlog(f"lesson {name} skipped: {'; '.join(problems)}")
                continue
            out.append(les)
        except Exception as e:
            dlog(f"lesson {name} could not be read: {e!r}")
    return sorted(out, key=lambda l: (l.get("order", 99), l["title"])) or [copy.deepcopy(BUILTIN_LESSON)]


def lesson_problems(les):
    """Checks a lesson file so a typo shows up as a clear message instead of a crash mid-lesson."""
    p = []
    for k in ("id", "title", "steps"):
        if k not in les:
            p.append(f"missing '{k}'")
    for i, st in enumerate(les.get("steps", []), 1):
        t = st.get("type")
        need = {"click": ("target",), "measure": ("kind",), "describe": ()}.get(t)
        if need is None:
            p.append(f"step {i}: unknown type '{t}'")
            continue
        for k in ("id", "text", "skill", "page") + need:
            if k not in st:
                p.append(f"step {i}: missing '{k}'")
        for tg in ([st.get("target")] + list(st.get("also", []))) if t == "click" else []:
            if tg not in TARGETS:
                p.append(f"step {i}: unknown button '{tg}' (known: {', '.join(TARGETS)})")
        if t == "measure" and st.get("kind") not in ("area", "length", "perimeter"):
            p.append(f"step {i}: kind must be area, length or perimeter")
    return p


def read_answer_file():
    try:
        with open(ANSWERS_FILE, encoding="utf-8") as fh:
            ans = json.load(fh)
    except Exception:
        return {}
    # older answer files were for the one built-in lesson: {"laundry": {...}, "elec": {...}}
    if ans and all(isinstance(v, dict) and "expected" in v for v in ans.values()):
        ans = {BUILTIN_LESSON["id"]: ans}
    return ans


def apply_answer_key():
    """Instructor-recorded answers replace the guide's numbers (eTakeoff results depend on where walls are clicked).
    Returns this lesson's part of the answer file."""
    ans = read_answer_file().get(LESSON["id"], {})
    for st in LESSON["steps"]:
        if st["id"] in ans and st["type"] == "measure" and "expected" in st:
            st["expected"] = ans[st["id"]]["expected"]
            st["points"] = ans[st["id"]].get("points", st.get("points"))
    return ans


class Offline(Exception):
    """The training site can't be reached (no internet, or the site is down)."""


class SiteError(Exception):
    """The site answered with an error, e.g. a wrong password or a rule that refused the request."""


class Cloud:
    """Talks to the training site. Everything here is safe to call from a background thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.access, self.expires = None, 0
        try:
            with open(ACCOUNT_FILE, encoding="utf-8") as fh:
                self.account = json.load(fh)
        except Exception:
            self.account = {}

    # --- plumbing
    def _http(self, method, path, body=None, token=None, headers=None, timeout=20):
        req = urllib.request.Request(SITE_URL + path, method=method,
                                     data=None if body is None else json.dumps(body).encode("utf-8"))
        req.add_header("apikey", SITE_KEY)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {token or SITE_KEY}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            try:
                info = json.loads(e.read() or b"{}")
            except Exception:
                info = {}
            msg = info.get("msg") or info.get("message") or info.get("error_description") or info.get("error") or str(e)
            raise SiteError(f"{msg}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise Offline(str(e)) from None

    def _save(self):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(ACCOUNT_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.account, fh)

    def _store_tokens(self, tok):
        self.access = tok["access_token"]
        self.expires = time.time() + int(tok.get("expires_in", 3600))
        self.account["refresh_token"] = tok["refresh_token"]
        self.account["user_id"] = tok.get("user", {}).get("id", self.account.get("user_id"))
        self._save()

    def token(self):
        with self.lock:
            if self.access and time.time() < self.expires - 60:
                return self.access
            if not self.account.get("refresh_token"):
                raise SiteError("Not signed in.")
            try:
                tok = self._http("POST", "/auth/v1/token?grant_type=refresh_token",
                                 {"refresh_token": self.account["refresh_token"]})
            except SiteError as e:
                dlog(f"sign-in expired: {e}")
                self.account.pop("refresh_token", None)
                self._save()
                raise SiteError("Your sign-in has expired. Please sign in again.") from None
            self._store_tokens(tok)
            return self.access

    def api(self, method, path, body=None, headers=None):
        return self._http(method, path, body, token=self.token(), headers=headers)

    def rpc(self, name, **args):
        return self.api("POST", f"/rest/v1/rpc/{name}", args)

    # --- account
    @property
    def signed_in(self):
        return bool(self.account.get("refresh_token"))

    def sign_in(self, email, password):
        tok = self._http("POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": password})
        with self.lock:
            self.account = {"email": email.strip()}
            self._store_tokens(tok)
        self.refresh_profile()

    def refresh_profile(self):
        rows = self.api("GET", f"/rest/v1/profiles?id=eq.{self.account['user_id']}"
                               "&select=full_name,role,companies(name)")
        if rows:
            p = rows[0]
            self.account.update(name=p.get("full_name") or self.account.get("email", ""), role=p.get("role"),
                                company=(p.get("companies") or {}).get("name", ""))
            self._save()

    def sign_out(self):
        with self.lock:
            self.account, self.access = {}, None
            try:
                os.remove(ACCOUNT_FILE)
            except OSError:
                pass

    # --- content
    def download_catalog(self):
        cat = {
            "lessons": self.api("GET", "/rest/v1/lessons?published=eq.true"
                                       "&select=id,title,tier,sort,block_ids,version&order=sort"),
            "tests": self.api("GET", "/rest/v1/tests?published=eq.true"
                                     "&select=id,title,tier,description,draw_count,pass_score,inactivity_minutes,sort"
                                     "&order=sort"),
            "blocks": self.api("GET", "/rest/v1/blocks?coach_ready=eq.true"
                                      "&select=id,title,tier,topic,steps,answer_key,version"),
            "downloaded": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        with open(CATALOG_FILE, "w", encoding="utf-8") as fh:
            json.dump(cat, fh)
        return cat

    # --- results: queued on disk first, so nothing is lost if the PC is offline or the coach is closed
    def queue(self, item):
        os.makedirs(OUTBOX_DIR, exist_ok=True)
        path = os.path.join(OUTBOX_DIR, f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(item, fh, default=str)
        return path

    def pending(self):
        try:
            return sorted(f for f in os.listdir(OUTBOX_DIR) if f.endswith(".json"))
        except OSError:
            return []

    def flush(self):
        """Upload everything waiting. Returns (sent, still_waiting). Stops quietly when offline."""
        sent = 0
        if not self.signed_in:
            return 0, len(self.pending())
        for name in self.pending():
            path = os.path.join(OUTBOX_DIR, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    item = json.load(fh)
                kind = item.pop("kind", "practice")
                if kind == "finish_test":
                    self.rpc("finish_test", p_session=item["session_id"], p_status=item["status"],
                             p_score=item.get("score"), p_summary=item.get("summary", {}))
                else:
                    self.api("POST", "/rest/v1/sessions?on_conflict=client_id", item,
                             headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
                os.remove(path)
                sent += 1
            except Offline:
                break
            except SiteError as e:
                if "sign" in str(e).lower():
                    break
                dlog(f"upload of {name} refused: {e}")
                os.makedirs(os.path.join(OUTBOX_DIR, "refused"), exist_ok=True)
                os.replace(path, os.path.join(OUTBOX_DIR, "refused", name))
            except Exception as e:
                dlog(f"upload of {name} failed: {e!r}")
                break
        return sent, len(self.pending())


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def check_for_update():
    """Returns the manifest if a newer coach is published, else None. Never raises."""
    try:
        req = urllib.request.Request(UPDATE_MANIFEST, headers={"User-Agent": f"TakeoffCoach/{COACH_VERSION}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            m = json.loads(r.read())
        if version_tuple(m.get("version")) > version_tuple(COACH_VERSION) and m.get("url"):
            return m
    except Exception as e:
        dlog(f"update check: {e!r}")
    return None


def install_update(manifest, progress=None):
    """Download the new TakeoffCoach.exe, check it, and swap it in after this program closes.
    Windows won't let a running program replace itself, so a tiny script waits for us to exit,
    moves the new file into place and starts it."""
    import hashlib
    import subprocess
    new = EXE_PATH + ".new"
    req = urllib.request.Request(manifest["url"], headers={"User-Agent": f"TakeoffCoach/{COACH_VERSION}"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    want = (manifest.get("sha256") or "").lower()
    if want and h.hexdigest() != want:
        os.remove(new)
        raise RuntimeError("The download was damaged (checksum mismatch). Try again.")
    script = os.path.join(os.path.dirname(EXE_PATH), "takeoff_coach_update.cmd")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(f'@echo off\r\n'
                 f':wait\r\n'
                 f'tasklist /FI "PID eq {os.getpid()}" | find "{os.getpid()}" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
                 f'move /y "{new}" "{EXE_PATH}" >nul\r\n'
                 f'start "" "{EXE_PATH}"\r\n'
                 f'del "%~f0"\r\n')
    subprocess.Popen(["cmd", "/c", script], creationflags=0x08000000)  # CREATE_NO_WINDOW


def read_catalog():
    try:
        with open(CATALOG_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def build_steps(block_ids, blocks, test=False):
    """Coach steps for a list of blocks. Step ids become 'block.step' so every block's steps stay distinct,
    and the block's answer key (recorded in Instructor mode) replaces the guide values.
    test=True: a test states the task, not the method: test_text replaces the practice wording, and
    steps marked test_skip are left out. Steps marked ungraded (e.g. "Select the Area trace", which points
    the learner at the right trace) still run but don't count toward the score."""
    by_id = {b["id"]: b for b in blocks}
    steps = []
    for bid in block_ids:
        b = by_id.get(bid)
        if not b:
            continue
        key = b.get("answer_key") or {}
        for st in b.get("steps", []):
            if test and st.get("test_skip"):
                continue
            st = copy.deepcopy(st)
            if test and st.get("test_text"):
                st["text"] = st["test_text"]
            sid = st["id"]
            st["id"], st["block"], st["block_title"] = f"{bid}.{sid}", bid, b["title"]
            if st.get("of"):
                st["of"] = f"{bid}.{st['of']}"
            if st.get("type") == "measure" and "expected" in st and isinstance(key.get(sid), dict) \
                    and key[sid].get("expected") is not None:
                st["expected"] = key[sid]["expected"]
                st["points"] = key[sid].get("points", st.get("points"))
            steps.append(st)
    return steps


def lessons_from_catalog(cat):
    out = []
    for les in cat.get("lessons") or []:
        steps = build_steps(les.get("block_ids") or [], cat.get("blocks") or [])
        if not steps:
            continue
        out.append({"id": les["id"], "title": les["title"], "tier": les.get("tier", "basic"),
                    "version": les.get("version", 1), "order": les.get("sort", 99), "source": "site",
                    "block_ids": les.get("block_ids") or [], "drawing": "004 A1.1 1st Floor Plan",
                    "scale": "3/32\" = 1'-0\"",
                    "grading": {"full_credit_within": 0.03, "pass_within": 0.10, "partial_score": 75},
                    "steps": steps})
    problems = [(l["title"], lesson_problems(l)) for l in out]
    for title, p in problems:
        if p:
            dlog(f"site lesson {title} skipped: {'; '.join(p)}")
    return [l for l, (_, p) in zip(out, problems) if not p]


def tier_label(lesson):
    t = lesson.get("tier")
    return f"{t.title()} · {lesson['title']}" if t else lesson["title"]


TRUE_FT = 32 / 3  # 3/32" = 1'-0" (feet per drawing inch)
SCALES = [('1/8" = 1\'-0"', 8), ('1/16" = 1\'-0"', 16), ('1/4" = 1\'-0"', 4), ('3/16" = 1\'-0"', 16 / 3),
          ('1/32" = 1\'-0"', 32), ('1/2" = 1\'-0"', 2)]


# ------------------------------------------------------------------ eTakeoff window helpers
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_etakeoff():
    found = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, b, n + 1)
                if b.value.startswith("eTakeoff Dimension"):
                    found.append((h, b.value))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else (None, "")


def win_rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD


def pid_of(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def click_is_in_etakeoff(x, y, et_hwnd):
    """True only if the window actually under the cursor belongs to eTakeoff (its main window or its dialogs).
    Our overlay is click-through, so Windows skips it here."""
    h = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return bool(h) and pid_of(h) == pid_of(et_hwnd)


def foreground_title():
    h = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


DEBUG_LOG = os.path.join(RESULTS_DIR, "coach_debug.log")


def dlog(msg):
    try:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def make_click_through(tkwin):
    hwnd = user32.GetAncestor(tkwin.winfo_id(), 2)  # GA_ROOT
    style = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80 | 0x08000000)


# ------------------------------------------------------------------ eTakeoff data (read-only)
def bstr_call(fn, *args):
    from comtypes import BSTR
    for t in (args, tuple(BSTR(a) if isinstance(a, str) else a for a in args),
              tuple(ctypes.byref(BSTR(a)) if isinstance(a, str) else a for a in args)):
        try:
            return fn(*t)
        except (TypeError, ctypes.ArgumentError):
            continue
    return fn(*args)


class Watcher:
    """Reads the project's measurements and reports confirmed NEW / CHANGED / DELETED rows.
    eTakeoff briefly drops rows while it saves, so a change must hold for 2 reads,
    and a deletion is confirmed by re-reading the measurement by its ID."""

    def __init__(self):
        import comtypes.client
        mod = comtypes.client.GetModule(TLB)
        self.o = comtypes.client.CreateObject(mod.ETkoObject, interface=mod.IETkoObjectDual)
        self.proj = None
        self.state, self.pending, self.missing = {}, {}, {}
        self.baseline_guids = set()

    def _g(self, name, *a):
        try:
            return getattr(self.o, name)(*a)
        except Exception:
            return None

    def projects(self):
        parts = str(self._g("ProjGuidDescGet") or "").split(";")
        return [(parts[i], parts[i + 1]) for i in range(0, len(parts) - 1, 2) if parts[i]]

    def bind_to_window_title(self, title):
        name = title.split("Project:", 1)[1].strip() if "Project:" in title else ""
        for gid, n in self.projects():
            if n == name:
                self.proj = gid
                return n
        return None

    def _rec(self):
        guid = self._g("GuidQtyGet")
        if not guid:
            return None
        return {"guid": guid, "desc": self._g("DescGet") or "", "trace": self._g("TraceDescGet") or "",
                "qty": self._g("DfltQtyGet") or 0.0, "uom": self._g("UomNameGet") or "",
                "area": self._g("AreaGet") or 0.0, "length": self._g("LengthGet") or 0.0,
                "perim": self._g("PerimeterGet") or 0.0, "points": self._g("CountGet") or 0,
                "dwg": self._g("DwgDescGet") or ""}

    def read_all(self):
        n = int(bstr_call(self.o.UnusedTkoScan, self.proj, "", "") or 0)
        rows = {}
        for i in range(n):
            bstr_call(self.o.UnusedTkoLoad, i)
            rec = self._rec()
            if rec:
                rows[(rec["guid"], rec["trace"])] = rec
        return rows

    def from_clipboard(self):
        """The measurement the learner copied (right-click > Copy Measurement). Comes straight from eTakeoff, no delay."""
        try:
            if not self.o.LoadFromClip():
                return None
        except Exception:
            return None
        return self._rec()

    def start_baseline(self):
        merged = {}
        for _ in range(12):  # eTakeoff sometimes leaves rows out of a single read
            merged.update(self.read_all())
            time.sleep(0.2)
        self.state = merged
        self.baseline_guids = {k[0] for k in merged}
        self.pending, self.missing = {}, {}
        self.last_raw = set(merged)
        dlog(f"baseline: {len(merged)} rows")

    def poll(self):
        raw = self.read_all()
        added, removed = set(raw) - self.last_raw, self.last_raw - set(raw)
        if added or removed:
            dlog(f"raw read: +{[(raw[k]['trace'], round(raw[k]['qty'], 2)) for k in added]} "
                 f"-{[k[1] for k in removed]} (total {len(raw)})")
        self.last_raw = set(raw)
        events = []
        for k, rec in raw.items():
            self.missing.pop(k, None)
            if self.state.get(k) == rec:
                self.pending.pop(k, None)
                continue
            p = self.pending.get(k)
            if p and p[0] == rec:
                kind = "CHANGED" if k in self.state else "NEW"
                events.append((kind, rec, self.state.get(k)))
                self.state[k] = rec
                self.pending.pop(k, None)
            else:
                self.pending[k] = (rec, 1)
        for k in list(self.state):
            if k in raw:
                continue
            self.missing[k] = self.missing.get(k, 0) + 1
            if self.missing[k] >= 3:
                still = bstr_call(self.o.LoadFromGuid, k[0])
                if not still:
                    events.append(("DELETED", self.state[k], None))
                    self.state.pop(k)
                self.missing.pop(k, None)
        for kind, rec, _ in events:
            dlog(f"event {kind}: {rec['trace']!r} {rec['desc']!r} qty {rec['qty']:.2f} pts {rec['points']} {rec['dwg']}")
        return events


# ------------------------------------------------------------------ reading the Quantity List off the screen
# "26.69 Length". Tolerates a stray border/swatch character in front ("| 26.69 Length").
NUM_ROW = re.compile(r"^[^\w\-.]*(?:[Il|!]\s+)?(-?[\d,]*\.?\d+)\s+([A-Za-z].*?)\s*$")
NUM_ONLY = re.compile(r"^[^\w\-.]*(-?[\d,]*\.?\d+)\W*$")


def same_text(a, b):
    """Typed descriptions read back by OCR: ignore case, spacing and punctuation, forgive a misread letter."""
    na = " ".join(re.sub(r"[^a-z0-9]+", " ", (a or "").lower()).split())
    nb = " ".join(re.sub(r"[^a-z0-9]+", " ", (b or "").lower()).split())
    return na == nb or (len(nb) > 3 and difflib.SequenceMatcher(None, na, nb).ratio() >= 0.88)


def merge_rows(lines):
    """OCR sometimes splits one Quantity List row into a number line and a label line ("610.70" + "Area").
    Join them back up when they sit on the same row."""
    lines = [dict(l) for l in lines]
    nums = [l for l in lines if NUM_ONLY.match(l["text"].strip())]
    used = set()
    for n in nums:
        hgt = max((wd["h"] for wd in n.get("words", [])), default=8)
        best = None
        for i, l in enumerate(lines):
            if i in used or l is n or NUM_ONLY.match(l["text"].strip()) or NUM_ROW.match(l["text"]):
                continue
            if abs(l["y"] - n["y"]) <= max(5, hgt * 0.7) and l["x"] > n["x"] and re.match(r"\s*[A-Za-z]", l["text"]):
                if best is None or l["x"] < lines[best]["x"]:
                    best = i
        if best is not None:
            used.add(best)
            n["text"] = NUM_ONLY.match(n["text"].strip()).group(1) + " " + lines[best]["text"].strip()
    return [l for i, l in enumerate(lines) if i not in used]


def count_rows(lines):
    return sum(1 for l in merge_rows(lines) if NUM_ROW.match(l["text"].replace(" .", ".").replace(". ", ".")))
DEFAULT_NAMES = {"area", "length", "perimeter", "count"}


def fit_button(tb, rgb, W, H):
    """If this ribbon button is already lit up (the active tool is orange), return the lit rectangle.
    tb is the label's text box. Returns [x1, y1, x2, y2] or None."""
    tx1, ty1, tx2, ty2 = [int(round(v)) for v in tb]
    hh = max(8, ty2 - ty1)
    if tx1 - 2 * hh < 0 or tx2 + 4 >= W or ty1 - hh < 0 or ty2 + hh >= H:
        return None
    px = lambda x, y: rgb[(y * W + x) * 3:(y * W + x) * 3 + 3]
    cy = (ty1 + ty2) // 2

    # 1) A highlighted button (Select's orange) is a solid coloured block: take the block.
    hl = px(tx1 - 2, cy)
    sat = lambda c: max(c) - min(c) > 60
    close = lambda x, y: 0 <= x < W and max(abs(a - b) for a, b in zip(px(x, y), hl)) < 70
    # the lit block must show on both sides of the label (OCR sometimes clips the last letter, so look a bit right)
    if sat(hl) and any(close(x, cy) for x in range(tx2 + 1, min(W, tx2 + hh))):
        x1 = tx1 - 2
        while x1 > tx1 - 4 * hh and any(close(x1 - k, cy) for k in range(1, hh)):
            x1 -= 1
        x2 = tx2
        while x2 < tx2 + 2 * hh and any(close(x2 + k, cy) for k in range(1, max(4, hh // 2))):
            x2 += 1
        y1 = cy
        while y1 > ty1 - hh and close(tx1 - 2, y1 - 1):
            y1 -= 1
        y2 = cy
        while y2 < ty2 + hh and close(tx1 - 2, y2 + 1):
            y2 += 1
        return [x1 - 1, y1 - 1, x2 + 1, y2 + 1]

    return None  # not lit up; the outline comes from hovering instead


def locate_targets(lines, W, H, rgb=None):
    """Find the ribbon buttons and the Quantity List pane from OCR of the whole eTakeoff window.
    Returns {name: [x1, y1, x2, y2]} relative to the window, like recorded positions."""
    words = [dict(wd) for ln in lines for wd in ln.get("words", [])]
    norm = lambda t: re.sub(r"[^a-z]", "", t.lower())
    found = {}

    btn_labels = {}

    def box(ws, key=None):
        x1 = min(v["x"] for v in ws); y1 = min(v["y"] for v in ws)
        x2 = max(v["x"] + v["w"] for v in ws); y2 = max(v["y"] + v["h"] for v in ws)
        hh = max(8, y2 - y1)
        if key:
            btn_labels[key] = [int(x1), int(y1), int(x2), int(y2)]
        if rgb and len(rgb) >= W * H * 3:
            try:
                fit = fit_button((x1, y1, x2, y2), rgb, W, H)  # an already-lit (orange) button
                if fit:
                    return fit
            except Exception as e:
                dlog(f"fit_button failed: {e!r}")
        # estimate: icon left of the label, button about two text-heights tall (refined by hovering later)
        cy = (y1 + y2) / 2
        return [int(x1 - 1.9 * hh), int(cy - 0.95 * hh), int(x2 + 0.5 * hh), int(cy + 0.95 * hh)]

    # The ribbon ends at its group labels ("Takeoff", "Navigation"...).
    labels = [v for v in words if norm(v["text"]) in ("takeoff", "navigation", "project") and v["y"] < H * 0.35]
    ribbon_bottom = max(v["y"] + v["h"] for v in labels) + 4 if labels else H * 0.2
    rib = [v for v in words if v["y"] + v["h"] <= ribbon_bottom + 2]
    used = []
    for v in rib:
        n = norm(v["text"])
        if n.startswith("multi"):
            ws = [v]
            if "select" not in n:
                ws += [u for u in rib if u is not v and abs(u["y"] - v["y"]) < v["h"] * 0.7
                       and -2 <= u["x"] - (v["x"] + v["w"]) < v["h"] * 2.5 and norm(u["text"]).startswith("select")][:1]
            found["multiselect"] = box(ws, "multiselect")
            used += ws
            break
    close = lambda a, b: a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75  # forgive "5elect", "Lenght"
    for key in ("select", "area", "count", "length", "perimeter"):
        cands = [v for v in rib if close(norm(v["text"]), key) and all(v is not u for u in used)]
        if cands:
            found[key] = box([min(cands, key=lambda v: v["x"])], key)
    # Trace names in the Traces control panel (Area, Count, Length, Perimeter rows under the "Traces" title)
    titles = [ln for ln in lines if norm(ln["text"]) == "traces" and ln["y"] > ribbon_bottom]
    if titles:
        tt = min(titles, key=lambda l: l["y"])
        th = max((v["h"] for v in tt.get("words", [])), default=14)
        nxt = [ln for ln in lines if PANE_TITLES.search(ln["text"]) and ln["y"] > tt["y"] + th
               and abs(ln["x"] - tt["x"]) < 3 * th and norm(ln["text"]) != "traces"]
        tbot = min((ln["y"] for ln in nxt), default=H)
        right = None
        if rgb and len(rgb) >= W * H * 3:
            right = pane_right_edge(rgb, W, H, int(tt["x"] + th), int(tt["y"] + 1.8 * th), int(min(tbot, H - 2) - th))
        order = ("area", "count", "length", "perimeter")  # eTakeoff lists the basic traces in this order
        row_at = {}
        for key in order:
            hits = [wd for ln in lines if tt["y"] < ln["y"] < tbot and -th < ln["x"] - tt["x"] < 8 * th
                    and len(ln.get("words", [])) <= 2 for wd in ln.get("words", []) if close(norm(wd["text"]), key)]
            if hits:
                wd = min(hits, key=lambda v: v["y"])
                row_at[key] = (wd["y"] + wd["h"] / 2, wd["h"])
        if len(row_at) >= 2:
            # rows OCR missed (the swatch beside a name can hide it) sit at the same spacing as the ones it read
            (ka, (ya, ha)), (kb, (yb, _)) = sorted(row_at.items(), key=lambda kv: order.index(kv[0]))[:2]
            pitch = (yb - ya) / (order.index(kb) - order.index(ka))
            if 0.9 * ha < pitch < 3 * ha:
                for key in order:
                    row_at.setdefault(key, (ya + (order.index(key) - order.index(ka)) * pitch, ha))
        for key, (cy, hh) in row_at.items():
            if cy < tbot:
                found["trace_" + key] = [int(max(0, tt["x"] - th)), int(cy - 0.95 * hh),
                                         int(right if right else tt["x"] + 12 * th), int(cy + 0.95 * hh)]
    # Select sits on its orange highlight and OCR sometimes can't read it. It is the button
    # directly above Multi-Select, one ribbon row up (the same spacing as Area -> Count).
    if "select" not in found and "multiselect" in found:
        mx1, my1, mx2, my2 = found["multiselect"]
        row = (found["count"][1] - found["area"][1]) if "area" in found and "count" in found else (my2 - my1) * 1.25
        found["select"] = [mx1, int(my1 - row), int(mx1 + (mx2 - mx1) * 0.62), int(my2 - row)]

    # Quantity List pane: from its title bar down to the "Measurement Summary" title.
    ql = [v for ln in lines if re.search(r"quantity\s*l[il1]st", ln["text"], re.I) for v in ln.get("words", [])[:1]]
    if ql:
        q = min(ql, key=lambda v: v["y"])
        # The pane ends at the next pane's title in the same column (whichever panel it is docked in).
        below = [v for ln in lines if PANE_TITLES.search(ln["text"])
                 for v in ln.get("words", [])[:1] if v["y"] > q["y"] + q["h"] and abs(v["x"] - q["x"]) < 3 * q["h"]]
        bottom = min(below, key=lambda v: v["y"])["y"] - q["h"] * 0.6 if below else H - 2.5 * q["h"]
        right = None
        if rgb and len(rgb) >= W * H * 3:
            right = pane_right_edge(rgb, W, H, int(q["x"] + q["h"]), int(q["y"] + 1.8 * q["h"]), int(bottom))
        if right is None:
            sync = [v for v in words if norm(v["text"]) == "sync" and v["y"] > q["y"]]
            right = (min(sync, key=lambda v: v["y"])["x"] + min(sync, key=lambda v: v["y"])["w"] + 3 * q["h"]
                     if sync else q["x"] + W * 0.21)
        # start just below the blue "Quantity List" title bar so the bar's text isn't mistaken for the measurement name
        found["qtylist"] = [int(max(0, q["x"] - q["h"])), int(q["y"] + 1.5 * q["h"]), int(min(W, right)), int(bottom)]
    found["_labels"] = btn_labels
    return found


PANE_TITLES = re.compile(r"^\W*(quantity\s*l[il1]st|measurement\s*summ|measurement\s*ed|traces\b|drawing\s*tree|favou?rites|"
                         r"work\s*break|control\s*panel|layers\b|bookmarks\b|properties\b|planroom|notes\b)", re.I)


def pane_right_edge(rgb, W, H, x0, y0, y1):
    """Walk right from inside the pane until a mostly-dark column (the pane border or splitter)."""
    if y1 - y0 < 10:
        return None
    ys = range(y0, y1, 3)
    for x in range(x0, W):
        dark = 0
        for y in ys:
            i = (y * W + x) * 3
            if min(rgb[i], rgb[i + 1], rgb[i + 2]) < 175:
                dark += 1
        if dark > 0.6 * len(ys):
            return x - 1
    return W - 1


TITLE_SKIP = re.compile(r"quantity\s*l[il1]st|^\W*\w{0,3}\s*l[il1]st\W*$|^\W*quant", re.I)


def read_title(strip, ocr):
    """Read the bold name line above the quantities. Windows OCR often skips a short bold word next to the
    coloured swatch, so try a few clean-ups: drop the swatch, then black-and-white, then larger."""
    from PIL import Image, ImageOps
    base = strip.copy()
    px = base.load()
    for yy in range(base.height):
        for xx in range(base.width):
            r, g, b = px[xx, yy]
            if max(r, g, b) - min(r, g, b) > 18 or min(r, g, b) > 200:  # swatch, blue title bar, light fill -> white
                px[xx, yy] = (255, 255, 255)
    bw = ImageOps.grayscale(base).point(lambda v: 0 if v < 150 else 255).convert("RGB")
    for img, scale in ((base, 3), (bw, 3), (bw, 5), (base, 6), (bw, 7)):
        got = [l for l in ocr(img, 0, 0, scale) if l["text"].strip() and not TITLE_SKIP.search(l["text"])]
        if got:
            return got
    return []


class QtyReader:
    """Reads eTakeoff's Quantity List pane with Windows' built-in text recognition (OCR).
    Screenshots are taken on the main thread; recognition runs on a worker thread."""

    def __init__(self):
        import mss
        from PIL import Image  # noqa: F401  (checked here so a missing package is reported up front)
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        self.sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.engine_error = None
        threading.Thread(target=self._worker, daemon=True).start()

    def grab(self, box):
        l, t, r, b = box
        shot = self.sct.grab({"left": l, "top": t, "width": max(1, r - l), "height": max(1, b - t)})
        return shot.size[0], shot.size[1], shot.rgb

    def submit(self, tag, w, h, rgb):
        self.jobs.put((tag, w, h, rgb))

    def _worker(self):
        import asyncio
        from PIL import Image
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
        from winrt.windows.storage.streams import Buffer
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            self.engine_error = "Windows has no OCR language installed (Settings > Time & language > Language)."
        while True:
            tag, w, h, rgb = self.jobs.get()
            if engine is None:
                self.results.put((tag, None, self.engine_error, w, h, rgb))
                continue
            try:
                full = Image.frombytes("RGB", (w, h), rgb)

                def ocr(img, x0, y0, scale, pad=24):
                    """OCR one image region; returns lines with positions in the original screenshot's pixels."""
                    big = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
                    canvas = Image.new("RGB", (big.width + 2 * pad, big.height + 2 * pad), "white")
                    canvas.paste(big, (pad, pad))  # white margin helps Windows OCR with text near edges
                    data = canvas.convert("RGBA").tobytes("raw", "BGRA")
                    # This winrt version takes 4 arguments and accepts any Python buffer as the pixel source.
                    try:
                        bmp = SoftwareBitmap.create_copy_from_buffer(data, BitmapPixelFormat.BGRA8, canvas.width, canvas.height)
                    except TypeError:
                        buf = Buffer(len(data))
                        buf.length = len(data)
                        memoryview(buf)[:] = data
                        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.BGRA8, canvas.width, canvas.height)

                    async def rec():
                        return await engine.recognize_async(bmp)
                    out = []
                    for ln in asyncio.run(rec()).lines:
                        words = list(ln.words)
                        if not words:
                            continue
                        ys = [wd.bounding_rect.y + wd.bounding_rect.height / 2 for wd in words]
                        out.append({"text": ln.text,
                                    "x": x0 + (words[0].bounding_rect.x - pad) / scale,
                                    "y": y0 + (sum(ys) / len(ys) - pad) / scale,
                                    "words": [{"text": wd.text,
                                               "x": x0 + (wd.bounding_rect.x - pad) / scale,
                                               "y": y0 + (wd.bounding_rect.y - pad) / scale,
                                               "w": wd.bounding_rect.width / scale,
                                               "h": wd.bounding_rect.height / scale} for wd in words]})
                    return out

                if tag == "scan":  # whole eTakeoff window: find buttons and panes by their labels
                    self.results.put((tag, ocr(full, 0, 0, 2 if max(w, h) * 2 < 9000 else 1), None, w, h, rgb))
                    continue

                lines = ocr(full, 0, 0, 2)
                if count_rows(lines) == 0:
                    # Nothing read as "number + name". Try again larger, then in clean black-and-white
                    # (selected rows are shaded, which can throw the recognizer off).
                    from PIL import ImageOps
                    gray = ImageOps.autocontrast(ImageOps.grayscale(full))
                    bw = gray.point(lambda v: 0 if v < 140 else 255).convert("RGB")
                    for img in (full, bw):
                        again = ocr(img, 0, 0, 3)
                        if count_rows(again) > 0:
                            lines = again
                            break
                lines = merge_rows(lines)
                # The bold title line (the measurement's name) sits beside a colour swatch and is easy for OCR
                # to miss, so read the strip above the first quantity row on its own, without the swatch.
                nums = [l["y"] for l in lines if NUM_ROW.match(l["text"])]
                top = int(min(nums) - 9) if nums else int(h * 0.25)
                if top > 6 and not any(l["y"] < top and not NUM_ROW.match(l["text"]) and not TITLE_SKIP.search(l["text"])
                                       for l in lines):
                    lines += read_title(full.crop((0, 0, w, top)), ocr)
                self.results.put((tag, lines, None, w, h, rgb))
            except Exception as e:
                tb = traceback.extract_tb(e.__traceback__)
                where = f" (line {tb[-1].lineno}: {tb[-1].line})" if tb else ""
                self.results.put((tag, None, repr(e) + where, w, h, rgb))


QTY_LABELS = ["point count", "perimeter", "length", "area", "count"]


def canon_label(label):
    """Map an OCR'd label to eTakeoff's quantity name, forgiving small misreads ("Permeter", "Lenght")."""
    low = label.lower().strip()
    if low.startswith("group") or low.startswith("grp"):
        return "group " + canon_label(low.split(" ", 1)[1] if " " in low else "")
    if low.startswith(("poi", "pon", "pnt")) and "count" in low.replace("coun", "count"):
        return "point count"
    for k in QTY_LABELS:
        if k in low:
            return k
    m = difflib.get_close_matches(low, QTY_LABELS, n=1, cutoff=0.7)
    return m[0] if m else low


def parse_qty_list(lines, w, h, rgb):
    """Turn OCR lines of the Quantity List into {header, values{label: number}, primary}.
    The primary quantity is the row eTakeoff shades blue."""
    header, rows = None, []
    for ln in sorted(merge_rows(lines), key=lambda d: d["y"]):
        if TITLE_SKIP.search(ln["text"]):
            continue  # the blue "Quantity List" bar, if it was included when recording
        m = NUM_ROW.match(ln["text"].replace(" .", ".").replace(". ", "."))
        if m:
            try:
                rows.append((float(m.group(1).replace(",", "")), m.group(2).strip(), ln["y"]))
            except ValueError:
                pass
        elif header is None and not rows:
            header = ln["text"].strip()
    if not rows:
        return None
    values, primary, best = {}, None, 0
    for val, label, y in rows:
        key = canon_label(label)
        values.setdefault(key, val)
        yy = min(h - 1, max(0, int(y)))
        blue = 0
        for x in (3, 8, max(9, w // 4)):
            if x < w:
                i = (yy * w + x) * 3
                r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
                blue = max(blue, b - r)
        if blue > best:
            best, primary = blue, key
    if best < 18:
        primary = None
    return {"header": header or "", "values": values, "primary": primary,
            "sig": (header or "", tuple(sorted((k, round(v, 2)) for k, v in values.items())))}


def screen_rec(parsed):
    """A measurement record built from the Quantity List (same shape as the eTakeoff-data records)."""
    v = parsed["values"]
    p = parsed["primary"]
    return {"guid": None, "desc": parsed["header"], "trace": parsed["header"],
            "qty": v.get(p) if p in ("area", "length", "perimeter", "count") else None, "uom": "",
            "area": v.get("area", 0.0), "length": v.get("length", 0.0), "perim": v.get("perimeter", 0.0),
            "points": int(v["point count"]) if "point count" in v else None, "dwg": None,
            "has": set(v), "primary": p}


# ------------------------------------------------------------------ grading
def points_matter(step):
    """Extra or fewer corners don't matter for an area, length or perimeter: the quantity does.
    For counts every point is an item, so the number of points is the answer."""
    return step.get("points_matter", step.get("kind") == "count")


def evaluate(step, rec):
    kind = step["kind"]
    val = {"area": rec["area"], "length": rec["length"], "perimeter": rec["perim"]}[kind]
    unit = "SF" if kind == "area" else "LF"
    if step.get("dwg") and rec.get("dwg") and step["dwg"] not in rec["dwg"]:
        return False, f"That measurement is on {rec['dwg']}. Do this one on 004 A1.1 1st Floor Plan.", "Navigating drawings"
    if rec.get("qty") is not None and abs(rec["qty"] - val) > max(0.01, abs(val) * 0.001):
        if not rec.get("trace") and rec.get("primary"):
            return (False, f"That's an {rec['primary'].title()} measurement ({rec['qty']:,.2f}), not a {kind}. Delete it and "
                           f"use a {kind.title()} trace: click {kind.title()} on the Home tab or double-click "
                           f"'{kind.title()}' in the Traces list.", "Choosing the right trace")
        return (False, f"That measurement used the trace '{rec['trace']}', whose main quantity isn't {kind} "
                       f"(it reports {rec['qty']:,.2f}). Delete it and use a {kind.title()} trace: double-click "
                       f"'{kind.title()}' in the Traces list.",
                "Choosing the right trace")
    if "expected" not in step:
        if (rec.get("points") is None or rec["points"] >= step.get("min_points", 2)) and val > 0:
            return True, f"{val:,.2f} {unit}" + (f" with {rec['points']} points." if rec.get("points") else "."), None
        return False, "Click at least two points before pressing S.", "Finish, undo, describe"
    exp = step["expected"]
    g = {**LESSON.get("grading", {}), **{k: step[k] for k in ("full_credit_within", "pass_within") if k in step}}
    tol = g.get("full_credit_within", step.get("tol", 0.03))
    pass_tol = max(tol, g.get("pass_within", tol))
    if kind == "area" and val < 0:
        return False, f"{val:,.2f} SF is negative, so the area was traced counter-clockwise. Delete it and click the corners clockwise.", "Polar mode and direction"
    r = val / exp
    pts_note = ""
    if points_matter(step) and step.get("points") and rec.get("points") is not None and rec["points"] != step["points"]:
        pts_note = f" You used {rec['points']} points; this room needs {step['points']}."
    if abs(r - 1) <= tol:
        return True, f"{val:,.2f} {unit}, within {tol * 100:.0f}% of {exp:,.2f}.{pts_note}", None
    for name, f in SCALES:
        sr = (f / TRUE_FT) ** (2 if kind == "area" else 1)
        if abs(r / sr - 1) < 0.03:
            return False, f"{val:,.2f} {unit} matches this room at {name}. Set the drawing scale to 3/32\" = 1'-0\" and re-measure.", "Setting the scale"
    for label, lo, hi in step.get("known", []):
        # "bath and elevator included" only makes sense if corners were skipped to get there
        if lo <= r <= hi and not (step.get("points") and (rec.get("points") or 0) >= step["points"]):
            return False, f"{val:,.2f} {unit} is {100 * (r - 1):.1f}% high: {label}. Click around them.{pts_note}", step["skill"]
    if kind == "perimeter" and 0.45 < r < 0.9:
        return False, f"{val:,.2f} LF looks like one wall is missing. Check you clicked all 4 corners.", step["skill"]
    if abs(r - 1) <= pass_tol:
        # close enough to pass, for partial credit, with the tip for getting it exact
        return ("partial", f"{val:,.2f} {unit}: close enough to pass ({abs(100 * (r - 1)):.1f}% "
                           f"{'above' if r > 1 else 'below'} {exp:,.2f}). For full credit, zoom in and click each corner "
                           f"on the same face of the wall.{pts_note}", step["skill"])
    return False, f"{val:,.2f} {unit} is {abs(100 * (r - 1)):.1f}% {'high' if r > 1 else 'low'} (target {exp:,.2f}). Zoom in and click each corner on the same wall line the answer key uses (inside face vs. outside face changes the total).{pts_note}", step["skill"]


# ------------------------------------------------------------------ app
class Coach:
    BG = "#ff00fe"  # overlay transparency key

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Takeoff Coach")
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
        global LESSON
        self.lessons = self._pick_lessons()
        LESSON = copy.deepcopy(self.lessons[0])
        self.lesson_title = tk.StringVar(value=tier_label(LESSON))
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
        try:
            self.reader = QtyReader()
            self.reader_error = None
        except Exception as e:
            self.reader, self.reader_error = None, f"{e.__class__.__name__}: {e}"
        self._build_panel()
        self._show_start()
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

    # ---------- panel
    def _build_panel(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        k = self.k = max(1.0, self.root.winfo_fpixels("1i") / 96)  # Windows display scaling (125%, 150%...)
        w, h = int(460 * k), int(400 * k)
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

    def choose_lesson(self, title):
        global LESSON
        les = next((l for l in self.lessons if title in (l["title"], tier_label(l))), None)
        if les:
            LESSON = copy.deepcopy(les)
            self.answers = apply_answer_key()
            self.lesson_title.set(tier_label(LESSON))
            self._show_start()

    # ---------- training site: account, catalog, uploads
    def _pick_lessons(self):
        cat = read_catalog() if self.cloud.signed_in else None
        site = lessons_from_catalog(cat) if cat else []
        return site or load_lessons()

    def ui(self, fn):
        """Run fn on the window's thread (background work must not touch the window directly)."""
        self.q.put(("ui", fn))

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
            global LESSON
            keep = LESSON.get("id")
            self.lessons = self._pick_lessons()
            LESSON = copy.deepcopy(next((l for l in self.lessons if l["id"] == keep), self.lessons[0]))
            self.answers = apply_answer_key()
            self.lesson_title.set(tier_label(LESSON))
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
        allans[LESSON["id"]] = self.answers
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
            self.sub.config(text=f"Practice: {LESSON['title']} · {len(LESSON['steps'])} steps · arrows show where to click")
            if len(self.lessons) > 1:
                om = tk.OptionMenu(b, self.lesson_title, *[tier_label(l) for l in self.lessons],
                                   command=self.choose_lesson)
                om.config(font=self.font)
                om.pack(anchor="w", fill="x", pady=(2, 0))
            if acct.get("role") == "owner":
                tk.Checkbutton(b, text="Instructor: record my measurements as the answer key",
                               variable=self.instructor, bg="#f4f7fb", font=self.font).pack(anchor="w", pady=(4, 0))
                keyed = [st["id"] for st in LESSON["steps"] if st["id"] in self.answers]
                tk.Label(b, text=(f"Answer key: yours ({len(keyed)} measurements)" if keyed else
                                  "Answer key: guide values or the site's"),
                         font=("Segoe UI", 9), fg="#5a6878", bg="#f4f7fb").pack(anchor="w")
            else:
                self.instructor.set(False)
        missing = [t for s in LESSON["steps"] if s["type"] == "click" for t in [s["target"]]
                   if t not in self.targets and not any(a in self.targets for a in s.get("also", []))]
        msg = (("The coach will find the buttons when the lesson starts." if self.reader else
                f"Button positions needed: {', '.join(sorted(set(missing)))}. Click Record manually first.")
               if missing else "Button positions known. They're re-checked each time a lesson starts.")
        self.status = tk.Label(b, text=msg, font=("Segoe UI", 9), fg="#a15c00" if missing else "#2e7d32",
                               bg="#f4f7fb", wraplength=int(410 * self.k), justify="left")
        self.status.pack(anchor="w", pady=(8, 4))
        if self.reader is None:
            ocr = ("Instant checking is off: screen-reading packages are missing. Run the second pip line at the top "
                   f"of takeoff_coach.py. ({self.reader_error})")
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

    # ---------- recording button positions
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
        self.reader.submit("test", *self.reader.grab(box))

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
        needed = {st["target"] for st in LESSON["steps"] if st["type"] == "click"
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

    # ---------- lesson flow
    def start_clicked(self):
        if self.mode.get() == "test":
            return self.begin_test()
        global LESSON
        les = next((l for l in self.lessons if tier_label(l) == self.lesson_title.get()), None)
        if les:
            LESSON = copy.deepcopy(les)
            self.answers = apply_answer_key()
        self.test = None
        self.start_lesson()

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
        global LESSON
        if err or not res:
            self.status.config(text=err or "Couldn't start the test.", fg="#c0392b")
            return
        info = res["test"]
        blocks = res.get("blocks") or []
        LESSON = {"id": info["id"], "title": info["title"], "tier": info.get("tier"), "version": 1,
                  "drawing": "004 A1.1 1st Floor Plan", "scale": "3/32\" = 1'-0\"",
                  "grading": {"full_credit_within": 0.03, "pass_within": 0.10, "partial_score": 75},
                  "block_ids": [b["id"] for b in blocks],
                  "steps": build_steps([b["id"] for b in blocks], blocks, test=True)}
        problems = lesson_problems(LESSON)
        if problems or not LESSON["steps"]:
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
        dlog(f"test {info['id']} started: {LESSON['block_ids']}")
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
        self.step_i = len(LESSON["steps"])
        self.overlay.withdraw()
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
        self.step_i = -1
        self.step_i_locked = -1
        self.finish_at = None
        self.next_step()

    def next_step(self):
        self.step_i += 1
        if self.step_i >= len(LESSON["steps"]):
            return self.finish()
        s = LESSON["steps"][self.step_i]
        self.nudged, self.select_was_active = False, True
        self.cur = {"id": s["id"], "skill": s["skill"], "page": s["page"], "type": s["type"],
                    "ungraded": bool(s.get("ungraded")), "wrong": 0,
                    "hints": 0, "failed": set(), "clicks": 0, "t0": time.time(), "status": "", "note": ""}
        self.hint_on = False
        # measurements that already existed when this step began are never graded for it
        self.step_known = {k[0] for k in self.watcher.state} | self.watcher.baseline_guids
        self.qty_at_start = self.qty_last["sig"] if self.qty_last else None
        self.finish_at = None
        self.qty_failed_sigs = set()
        dlog(f"step {s['id']} start")
        self._render_step()

    def _render_step(self, feedback="", ok=None):
        s = LESSON["steps"][self.step_i]
        self._clear()
        self.h1.config(text=f"Step {self.step_i + 1} of {len(LESSON['steps'])}")
        if self.test:
            n = LESSON["block_ids"].index(s["block"]) + 1 if s.get("block") in LESSON.get("block_ids", []) else 0
            self.sub.config(text=f"TEST · {self.test['title']} · Task {n} of {len(LESSON['block_ids'])}: "
                                 f"{s.get('block_title', '')}")
        else:
            self.sub.config(text=f"{LESSON['title']} · {s.get('block_title') or ''}{' · ' if s.get('block_title') else ''}"
                                 f"Guide p. {s['page']} · {s['skill']}")
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
        tk.Button(row, text="Hint", command=self.hint, font=self.font).pack(side="left")
        tk.Button(row, text="Skip step", command=self.skip, font=self.font).pack(side="left", padx=6)
        tk.Button(row, text="End test" if self.test else "Stop lesson", command=self.stop_lesson,
                  font=self.font).pack(side="right")

    def hint(self):
        self.cur["hints"] += 1
        self.hint_on = True
        s = LESSON["steps"][self.step_i]
        dwg, scale = LESSON.get("drawing", "the right drawing"), LESSON.get("scale", "the drawing's scale")
        tips = {"click": f"Look for {TARGETS.get(s.get('target'), '')}. It's outlined in red now.",
                "measure": f"Check the drawing is {dwg} and the scale is {scale}. Click each corner once; Backspace removes the last point. Press S to finish drawing. Fix any corner you need to, then press Enter to submit.",
                "describe": "Click the measurement to select it and press D (or right-click it, Edit Measurement Description). Type the exact words from the step and press Enter."}
        self._render_step(s.get("hint") or tips[s["type"]], ok=False)

    def skip(self):
        self._close_step("skipped", 0)

    def _close_step(self, status, score, note=""):
        self.cur.update(status=status, score=score, note=note, seconds=round(time.time() - self.cur["t0"], 1))
        self.results.append(self.cur)
        self.next_step()

    def _score(self):
        base = max(0, 100 - 25 * self.cur["wrong"] - 25 * len(self.cur["failed"]) - 20 * self.cur["hints"])
        if self.cur.get("partial"):
            base = min(base, LESSON.get("grading", {}).get("partial_score", 75))
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

    # ---------- events
    def on_click(self, x, y):
        if self.step_i < 0 or self.step_i >= len(LESSON["steps"]) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        px, py, pw, ph = self.root.winfo_rootx(), self.root.winfo_rooty(), self.root.winfo_width(), self.root.winfo_height()
        if px <= x <= px + pw and py <= y <= py + ph:
            return  # click on the coach panel
        h, _ = find_etakeoff()
        if not h:
            return
        if not click_is_in_etakeoff(x, y, h):
            return  # another program, even one sitting on top of eTakeoff
        l, t, r, b = win_rect(h)
        dlog(f"click at window offset ({x - l},{y - t})")
        now = time.time()
        if now - self.last_click_t < 0.45 and abs(x - self.last_click_xy[0]) < 6 and abs(y - self.last_click_xy[1]) < 6:
            pass  # a double-click finishes drawing in eTakeoff; grading still waits for Enter
        self.last_click_t, self.last_click_xy = now, (x, y)
        s = LESSON["steps"][self.step_i]
        self.cur["clicks"] += 1
        if s["type"] != "click":
            return
        inside = lambda k: k in self.targets and (lambda b: l + b[0] - 3 <= x <= l + b[2] + 3 and
                                                                t + b[1] - 3 <= y <= t + b[3] + 3)(self.targets[k])
        if inside(s["target"]):
            self._pass("")
        elif any(inside(k) for k in s.get("also", [])):
            alt = next(k for k in s.get("also", []) if inside(k))
            self._pass(f"That works too. The guide uses {TARGETS[s['target']]}; {TARGETS[alt]} does the same thing.")
        else:
            # Clicks on the drawing or side panels are navigation (zoom, pan, select), not wrong answers.
            # A wrong button is a click up in the ribbon band, or on another button the coach knows about.
            ribbon_bottom = max((v[3] for k, v in self.targets.items() if k in RIBBON), default=150) + 40
            ribbon_top = min((v[1] for k, v in self.targets.items() if k in RIBBON), default=60) - 12
            in_band = ribbon_top <= y - t <= ribbon_bottom  # not the title bar or the tabs (window buttons, Home...)
            if not in_band and not any(inside(k) for k in TARGETS):
                return
            self.cur["wrong"] += 1
            self._render_step("Not quite. Try again." if self.test else
                              f"Not quite. That wasn't {TARGETS[s['target']]}. Try again.", ok=False)

    def check_now(self):
        """Re-read the Quantity List now (and the clipboard, if a measurement was copied)."""
        h, _ = find_etakeoff()
        if not h:
            return self._render_step("eTakeoff isn't open.", ok=False)
        dlog("Check button")
        self.check_src = "button"
        s = LESSON["steps"][self.step_i] if 0 <= self.step_i < len(LESSON["steps"]) else None
        if s and s["type"] == "click" and getattr(self, "step_i_locked", -1) != self.step_i:
            lit = [k for k in [s["target"]] + list(s.get("also", [])) if k in RIBBON and self.button_active(k)]
            if lit:
                dlog(f"click step {s['id']}: {lit[0]} is lit")
                return self._pass(f"{TARGETS[lit[0]].split(' (')[0]} is active.")
        self.finish_at = time.time()

    def defer(self):
        """Move on now; grade this step when eTakeoff publishes the measurement (after the next one is drawn)."""
        dlog(f"step {self.cur['id']} deferred")
        self._close_step("pending", 0, "waiting for eTakeoff to publish the measurement")

    def _read_after_check(self):
        self.clip_seq = user32.GetClipboardSequenceNumber()  # handled here, not again in tick
        rec = self.watcher.from_clipboard()
        dlog("after Check: " + (f"{rec['trace']!r} {rec['desc']!r} qty {rec['qty']:.2f} pts {rec['points']}"
                                if rec else "no eTakeoff measurement on the clipboard"))
        self.on_clipboard(rec)

    def on_clipboard(self, rec):
        """The learner copied a measurement (right-click > Copy Measurement). rec is it, or None if no measurement was copied.
        (Reading the whole project lags: eTakeoff only publishes a measurement after the next one is started,
        so grading uses the copied measurement, which comes straight from eTakeoff's memory.)"""
        if self.step_i < 0 or self.step_i >= len(LESSON["steps"]) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        s = LESSON["steps"][self.step_i]
        if s["type"] == "click":
            return
        if rec is None:
            return self._render_step("There's no measurement on the clipboard yet. Right-click your measurement on the "
                                     "drawing and choose Copy Measurement, then any Copy Total option.", ok=False)
        graded = getattr(self, "graded", {})
        if rec["guid"] in self.watcher.baseline_guids:
            return self._render_step("That measurement was there before this lesson. Copy the one you just drew.", ok=False)
        if s["type"] == "describe":
            return self._grade_description(s, rec["desc"] if rec["desc"] != rec["trace"] else "",
                                           {"area": rec.get("area"), "length": rec.get("length"),
                                            "perimeter": rec.get("perim")}, True)
        if rec["guid"] in graded and graded[rec["guid"]] != s["id"]:
            return self._render_step("That's the measurement from an earlier step. Draw a new one for this step.", ok=False)
        if self.instructor.get():
            free = {k: v for k, v in s.items() if k not in ("expected", "points", "known")}
            ok, msg, _ = evaluate(free, rec)
            if ok:
                val = {"area": rec["area"], "length": rec["length"], "perimeter": rec["perim"]}[s["kind"]]
                if "expected" in s:
                    self.answers[s["id"]] = {"expected": round(val, 2), "points": rec["points"]}
                    self.save_answers()
                    msg = f"Saved {val:,.2f} with {rec['points']} points as the answer key."
                graded[rec["guid"]] = s["id"]
                self.graded = graded
                return self._pass(msg, partial=(ok == "partial"))
            return self._render_step(msg, ok=False)
        ok, msg, skill = evaluate(s, rec)
        dlog(f"grade {s['id']}: {ok} {msg}")
        graded[rec["guid"]] = s["id"]
        self.graded = graded
        if ok:
            self.last_guid = rec["guid"]
            return self._pass(msg, partial=(ok == "partial"))
        self.cur["failed"].add(rec["guid"] + f"@{len(self.cur['failed'])}")
        self.cur.setdefault("missed_skills", []).append(skill)
        self._miss(msg)

    def on_qtylist(self, parsed, forced=False, quiet=99.0):
        """A finished measurement read off the Quantity List. Grades the current step instantly.
        Returns 'wait' when a miss might just be a measurement still being drawn (checked again shortly)."""
        if self.step_i < 0 or self.step_i >= len(LESSON["steps"]) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        s = LESSON["steps"][self.step_i]
        if s["type"] == "click" and parsed:
            # Picking a trace (Traces panel or ribbon) shows that trace, still empty, in the Quantity List.
            # That proves the right trace is active even if the coach couldn't outline the button.
            want = s["target"].replace("trace_", "")
            if want in ("area", "length", "perimeter", "count") and parsed["primary"] in (want, "point count" if want == "count" else want) \
                    and all(abs(v) < 0.005 for v in parsed["values"].values()) and (forced or parsed["sig"] != self.qty_at_start):
                dlog(f"click step {s['id']}: Quantity List shows an empty {want} trace")
                return self._pass(f"{want.title()} trace is active.")
            if forced:
                dlog(f"click step {s['id']}: checked, not active yet ({parsed['primary']} {parsed['values']})")
                self._render_step(f"The coach doesn't see {TARGETS[s['target']]} selected yet. Click it, then "
                                  f"Check again.", ok=False)
            return
        if not parsed:
            return
        if s["type"] == "describe":
            return self._grade_description(s, parsed["header"], parsed["values"], forced)
        if parsed["sig"] == self.qty_at_start and not forced:
            return  # still showing whatever was selected when the step began
        dlog(f"check for step {s['id']}: '{parsed['header']}' {parsed['values']} main={parsed['primary']}")
        if s["type"] == "measure" and parsed["sig"][1] in self.passed_vals:
            dlog("  ignored: same numbers as a measurement that passed an earlier step")
            return  # a measurement that already passed an earlier step
        rec = screen_rec(parsed)
        # Is it a measurement that existed before this step? (published ones are known exactly)
        for old in self.watcher.state.values():
            if old["guid"] in self.step_known and any(
                    k in rec["has"] and abs(old[f] - parsed["values"][k]) < 0.006
                    for k, f in (("area", "area"), ("length", "length"), ("perimeter", "perim"))
                    if parsed["values"].get(k)):
                if s["type"] == "describe" and parsed["header"].lower() not in DEFAULT_NAMES and old["guid"] not in self.watcher.baseline_guids:
                    return self._pass(f"Named it \"{parsed['header']}\".")
                dlog(f"  ignored: matches an existing measurement ({old['trace']} {old['desc']})")
                return self._render_step("That's a measurement that was already there. Draw a new one for this step.", ok=False)
        if s["type"] == "describe":
            if parsed["header"] and parsed["header"].lower() not in DEFAULT_NAMES:
                return self._pass(f"Named it \"{parsed['header']}\".")
            if forced:
                self._render_step("The Quantity List still shows the default name. Right-click the line, choose Edit "
                                  "Measurement Description, type a name and press Enter.", ok=False)
            return
        kind = s["kind"]
        if kind not in rec["has"]:
            if rec["primary"] in ("area", "length", "perimeter", "count"):
                msg = (f"That measurement is a {rec['primary']} measurement. This step needs a {kind}: "
                       f"use the {kind.title()} button or double-click '{kind.title()}' in the Traces list.")
                if not forced and quiet < 4:
                    return "wait"
                return self._screen_fail(parsed, msg, "Choosing the right trace")
            dlog(f"  no {kind} row in this reading")
            if forced:
                self._render_step(f"The coach can't see a {kind.title()} row in the Quantity List. Click your "
                                  f"measurement so it's selected, then click Check again.", ok=False)
            return
        if self.instructor.get():
            free = {k: v for k, v in s.items() if k not in ("expected", "points", "known")}
            ok, msg, _ = evaluate(free, rec)
            if ok and "expected" in s:
                val = {"area": rec["area"], "length": rec["length"], "perimeter": rec["perim"]}[kind]
                entry = {"expected": round(val, 2)}
                if rec["points"]:
                    entry["points"] = rec["points"]
                self.answers[s["id"]] = entry
                self.save_answers()
                msg = f"Saved {val:,.2f} as the answer key."
            if ok:
                self.cur["graded_val"] = (kind, {"area": rec["area"], "length": rec["length"], "perimeter": rec["perim"]}[kind])
                self.passed_vals.add(parsed["sig"][1])
                return self._pass(msg, partial=(ok == "partial"))
            if not forced and quiet < 4:
                return "wait"
            return self._screen_fail(parsed, msg, None)
        ok, msg, skill = evaluate(s, rec)
        dlog(f"grade {s['id']} from screen: {ok} {msg}")
        if ok:
            self.cur["graded_val"] = (kind, {"area": rec["area"], "length": rec["length"], "perimeter": rec["perim"]}[kind])
            self.passed_vals.add(parsed["sig"][1])
            return self._pass(msg, partial=(ok == "partial"))
        if not forced and quiet < 4:
            return "wait"  # they may still be clicking corners; look again shortly
        self._screen_fail(parsed, msg, skill)

    def _grade_description(self, s, name, values, forced):
        """Describe step: the measurement from step s["of"] must carry exactly the description the lesson asks for."""
        want = s.get("answer")
        name = (name or "").strip()
        of = s.get("of", "len")
        drew = next((r.get("graded_val") for r in self.results if r.get("id") == of and r.get("graded_val")), None)
        have = (values or {}).get(drew[0]) if drew else None
        if forced:
            dlog(f"check for step {s['id']}: name '{name}' values {values} (want '{want}' on {of} = {drew})")
        if drew and (have is None or abs(have - drew[1]) > 0.02):
            if forced:
                unit = "SF" if drew[0] == "area" else "LF"
                self._render_step(f"That's a different measurement. Click the {drew[0]} you drew earlier "
                                  f"({drew[1]:,.2f} {unit}) so the Quantity List shows it, then press D.", ok=False)
            return
        named = name and name.lower() not in DEFAULT_NAMES
        if named and (not want or same_text(name, want)):
            return self._pass(f"Named it \"{name}\".")
        if not forced:
            return  # still typing, or the list hasn't caught up yet
        if named:
            msg = f"The description reads \"{name}\". It should be exactly \"{want}\". Press D again and fix it."
            if ("desc", name.lower()) not in self.qty_failed_sigs:
                self.qty_failed_sigs.add(("desc", name.lower()))
                self.cur["failed"].add(f"desc@{len(self.cur['failed'])}")
            return self._miss(msg)
        if getattr(self, "check_src", "") == "button":
            self._render_step(f"The Quantity List still shows the default name. Select the measurement, press D, "
                              f"type {want or 'a description'} and press Enter.", ok=False)

    def _screen_fail(self, parsed, msg, skill):
        # Only count a miss once per distinct result, and not while the learner may still be clicking points.
        if parsed["sig"] in self.qty_failed_sigs:
            return
        self.qty_failed_sigs.add(parsed["sig"])
        self.cur["failed"].add(f"screen@{len(self.cur['failed'])}")
        if skill:
            self.cur.setdefault("missed_skills", []).append(skill)
        self._miss(msg)

    def verify_published(self, events):
        """eTakeoff publishes a measurement once the next one is drawn. Use that exact data to double-check
        steps graded from the screen (point count, drawing) and to grade steps marked 'Done, check it later'."""
        steps = {st["id"]: st for st in LESSON["steps"]}
        cur = LESSON["steps"][self.step_i] if 0 <= self.step_i < len(LESSON["steps"]) else None
        if cur and cur["type"] == "describe" and getattr(self, "step_i_locked", -1) != self.step_i:
            for kind_ev, rec, _ in events:
                if kind_ev in ("NEW", "CHANGED") and rec.get("desc") and rec["desc"] != rec["trace"] \
                        and same_text(rec["desc"], cur.get("answer") or rec["desc"]):
                    self._grade_description(cur, rec["desc"], {"area": rec["area"], "length": rec["length"],
                                                               "perimeter": rec["perim"]}, False)
                    break
        for kind_ev, rec, _ in events:
            if kind_ev != "NEW" or rec["guid"] in self.watcher.baseline_guids:
                continue
            for r in self.results:
                st = steps.get(r["id"])
                if not st or st["type"] != "measure" or r.get("verified"):
                    continue
                val = {"area": rec["area"], "length": rec["length"], "perimeter": rec["perim"]}[st["kind"]]
                if r["status"] == "passed" and r.get("graded_val") and abs(r["graded_val"][1] - val) < 0.011:
                    ok, msg, _ = evaluate(st, rec)
                    r["verified"] = {"points": rec["points"], "drawing": rec["dwg"], "trace": rec["trace"]}
                    if self.instructor.get() and st["id"] in self.answers:
                        # the screen has no point count; add it to the answer key once eTakeoff publishes it
                        self.answers[st["id"]]["points"] = rec["points"]
                        self.save_answers()
                        ok = True
                    if not ok:
                        r["note"] = (r.get("note", "") + f" Double-check: {msg}").strip()
                        r["score"] = min(r["score"], 50)
                    elif points_matter(st) and st.get("points") and rec["points"] != st["points"]:
                        r["note"] = (r.get("note", "") + f" Used {rec['points']} points (expected {st['points']}).").strip()
                        r["score"] = min(r["score"], 80)
                    dlog(f"verified {r['id']}: pts {rec['points']} {rec['dwg']} -> {r.get('note')}")
                    break
                if r["status"] == "pending" and abs(rec["qty"] - val) < max(0.01, abs(val) * 0.001):
                    ok, msg, skill = evaluate(st, rec)
                    r["verified"] = {"points": rec["points"], "drawing": rec["dwg"], "trace": rec["trace"]}
                    r["status"], r["note"] = ("passed (checked later)" if ok else "missed (checked later)"), msg
                    r["score"] = max(0, 100 - 20 * r["hints"]) if ok else 0
                    if ok == "partial":
                        r["score"] = min(r["score"], LESSON.get("grading", {}).get("partial_score", 75))
                    if not ok and skill:
                        r.setdefault("missed_skills", []).append(skill)
                    dlog(f"late grade {r['id']}: {ok} {msg}")
                    break

    # ---------- overlay
    def draw_overlay(self):
        if time.time() < getattr(self, "showing_found_until", 0):
            return
        h, _ = find_etakeoff()
        active = 0 <= self.step_i < len(LESSON["steps"])
        if not h or user32.IsIconic(h) or not active:
            self.overlay.withdraw()
            return
        l, t, r, b = win_rect(h)
        w, ht = r - l, b - t
        if self.overlay.state() == "withdrawn":
            self.overlay.deiconify()
            self.overlay.update_idletasks()
            make_click_through(self.overlay)
        self.overlay.geometry(f"{w}x{ht}+{l}+{t}")
        cv = self.cv
        cv.delete("all")
        s = LESSON["steps"][self.step_i]
        text = s["text"]
        if self.flash and time.time() < self.flash[1]:
            text, good = self.flash[0], True
        else:
            good = False
        bx, by, bw = int(w * 0.24), int(ht * 0.70), min(560, int(w * 0.45))
        tid = cv.create_text(bx + 16, by + 12, text=f"{self.step_i + 1}. {text}", anchor="nw", width=bw - 32,
                             font=("Segoe UI", 13), fill="#1b5e20" if good else "#24384f")
        x1, y1, x2, y2 = cv.bbox(tid)
        cv.create_rectangle(bx, by, bx + bw, y2 + 12, fill="#ffffff", outline="#2a7fd0", width=3)
        cv.tag_raise(tid)
        show_arrow = s["type"] == "click" and (self.mode.get() == "practice" or self.hint_on) and not good
        if show_arrow and s.get("target") in self.targets:
            tx1, ty1, tx2, ty2 = self.targets[s["target"]]
            cv.create_rectangle(tx1 - 3, ty1 - 3, tx2 + 3, ty2 + 3, outline="#e53935", width=3)
            cv.create_line(bx + bw // 3, by, (tx1 + tx2) // 2, ty2 + 6, fill="#e53935", width=4,
                           arrow=tk.LAST, arrowshape=(18, 22, 7))

    # ---------- results
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

    def _upload_practice(self, status, total=None, weak=()):
        """Queue this practice session for the site and send it in the background."""
        if not hasattr(self, "started_utc") or not self.cloud.signed_in:
            return
        ended = datetime.datetime.now(datetime.timezone.utc)
        res = self.results or []
        rec = {"client_id": str(uuid.uuid4()), "mode": "practice", "lesson_id": LESSON["id"], "title": LESSON["title"],
               "tier": LESSON.get("tier"), "status": status,
               "block_ids": list(dict.fromkeys(st.get("block") for st in LESSON["steps"] if st.get("block"))),
               "started_at": self.started_utc.isoformat(), "ended_at": ended.isoformat(),
               "seconds": int((ended - self.started_utc).total_seconds()), "score": total,
               "steps_total": len(LESSON["steps"]),
               "steps_first_try": sum(1 for r in res if r["status"].startswith("passed") and r["score"] == 100),
               "wrong_clicks": sum(r.get("wrong", 0) for r in res), "hints": sum(r.get("hints", 0) for r in res),
               "work_on": [k for _, k in weak],
               "steps": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in r.items() if k != "t0"} for r in res],
               "project": getattr(self, "project_name", ""), "coach_version": COACH_VERSION}
        self.cloud.queue(rec)
        self.sync_in_background()

    def go_home(self):
        self._hide_warning()
        self.step_i = -1
        self.step_i_locked = -1
        self.results = []
        self.finish_at = None
        self.overlay.withdraw()
        self.cv.delete("all")
        self._show_start()

    def start_lesson_titled(self, title):
        self.choose_lesson(title)
        self.start_lesson()

    def finish(self):
        if self.step_i < 0:
            self.root.destroy()
            return
        done_ids = {r["id"] for r in self.results}
        for s in LESSON["steps"]:
            if s["id"] not in done_ids:
                self.results.append({"id": s["id"], "skill": s["skill"], "page": s["page"], "type": s["type"],
                                     "ungraded": bool(s.get("ungraded")),
                                     "status": "not reached", "score": 0, "wrong": 0, "hints": 0,
                                     "failed": set(), "clicks": 0, "seconds": 0, "note": ""})
        self.step_i = len(LESSON["steps"])
        self.overlay.withdraw()
        scored = [r for r in self.results if not r.get("ungraded")] or self.results
        total = round(sum(r["score"] for r in scored) / len(scored))
        skills = {}
        for r in scored:
            skills.setdefault(r["skill"], []).append(r["score"])
            for ms in r.get("missed_skills", []):
                if ms and ms != r["skill"]:
                    skills.setdefault(ms, []).append(50)
        weak = sorted([(sum(v) / len(v), k) for k, v in skills.items() if sum(v) / len(v) < 80])
        pages = {s["skill"]: s["page"] for s in LESSON["steps"]}
        os.makedirs(RESULTS_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        base = os.path.join(RESULTS_DIR, f"{self.learner.get() or 'learner'}-{stamp}")
        out = {"learner": self.learner.get(), "lesson": LESSON["title"], "lesson_id": LESSON["id"],
               "lesson_version": LESSON.get("version", 1), "mode": self.mode.get(),
               "project": getattr(self, "project_name", ""), "started": str(getattr(self, "started", "")),
               "score": total, "work_on": [k for _, k in weak],
               "steps": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in r.items() if k != "t0"} for r in self.results]}
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
            w.writerow(["step", "skill", "guide page", "status", "score", "wrong clicks", "missed attempts", "hints", "seconds", "note"])
            for r in self.results:
                w.writerow([r["id"], r["skill"], r["page"], r["status"], r["score"], r["wrong"],
                            len(r["failed"]), r["hints"], r.get("seconds", 0), r.get("note", "")])
        self._clear()
        self.h1.config(text=f"Score: {total}%")
        self._hide_warning()
        self.sub.config(text=f"{LESSON['title']} · {'Test' if test else 'Practice'} · "
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
                tk.Label(self.body, text=f"• {k} ({sc:.0f}%) · review guide p. {pages.get(k, '?')}",
                         font=("Segoe UI", 10), bg="#f4f7fb").pack(anchor="w")
        else:
            tk.Label(self.body, text="Every skill at 80% or better.", font=("Segoe UI", 10), bg="#f4f7fb").pack(anchor="w")
        row = tk.Frame(self.body, bg="#f4f7fb")
        row.pack(fill="x", side="bottom")
        titles = [l["title"] for l in self.lessons]
        nxt = (titles[titles.index(LESSON["title"]) + 1] if not test and LESSON["title"] in titles[:-1] else None)
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
                      command=lambda t=LESSON["title"]: self.start_lesson_titled(t)).pack(side="left", padx=6)
        tk.Button(row, text="Home", font=self.font, command=self.go_home).pack(side="left")
        tk.Button(row, text="Open results folder", font=self.font,
                  command=lambda: os.startfile(RESULTS_DIR)).pack(side="left", padx=6)
        tk.Button(row, text="Close", font=self.font, command=self.root.destroy).pack(side="right")

    # ---------- main loop
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
                elif ev[0] == "f8" and self.recording:
                    self._record_capture()
                elif ev[0] == "finish":
                    h, _ = find_etakeoff()
                    if h and pid_of(user32.GetForegroundWindow()) == pid_of(h):
                        cur = LESSON["steps"][self.step_i] if 0 <= self.step_i < len(LESSON["steps"]) else {}
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
                        dlog(f"Enter pressed in eTakeoff: checking")
                        self.check_src = "key"
                        self.finish_at = time.time() + 0.6  # let eTakeoff update the Quantity List first
        except queue.Empty:
            pass
        self.ticks += 1
        if self.test and 0 <= self.step_i < len(LESSON["steps"]):
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
        if self.ticks % 20 == 0 and 0 <= self.step_i < len(LESSON["steps"]) and getattr(self, "scan_size", None):
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
                if self.watcher and 0 <= self.step_i < len(LESSON["steps"]):
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
        if self.ticks % 5 == 0 and 0 <= self.step_i < len(LESSON["steps"]) and \
                LESSON["steps"][self.step_i]["type"] == "measure" and "select" in self.targets and self.cur.get("clicks", 0) >= 2:
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
                        if 0 <= self.step_i < len(LESSON["steps"]) and LESSON["steps"][self.step_i]["type"] != "click":
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
                elif 0 <= self.step_i < len(LESSON["steps"]) and LESSON["steps"][self.step_i]["type"] in ("describe", "click"):
                    self.on_qtylist(parsed, forced=False)  # passes as soon as the right name shows; never fails
        except queue.Empty:
            pass
        if not (0 <= self.step_i < len(LESSON["steps"])):
            return
        box = self.qty_box()
        if not box:
            return
        if self.finish_at and time.time() >= self.finish_at:
            self.finish_at = None
            dlog(f"checking Quantity List at {box}")
            self.reader.submit("check", *self.reader.grab(box))
            return
        # background reading (for the log and for "what was showing when this step began"), once a second
        if self.ticks % 10 == 0:
            w, h, rgb = self.reader.grab(box)
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


def self_test():
    """Run by the build machine: every part the packaged program needs must load. Exit code 0 = good."""
    import comtypes.client  # noqa: F401
    import mss  # noqa: F401
    from PIL import Image, ImageOps  # noqa: F401
    from winrt.windows.media.ocr import OcrEngine  # noqa: F401
    from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat  # noqa: F401
    from winrt.windows.storage.streams import Buffer  # noqa: F401
    from winrt.windows.globalization import Language  # noqa: F401
    import winrt.windows.foundation.collections  # noqa: F401
    from pynput import mouse as _m, keyboard as _k  # noqa: F401
    root = tk.Tk()
    root.withdraw()
    root.destroy()
    with open(os.path.join(HERE, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"Takeoff Coach {COACH_VERSION} self-test passed\n")


if __name__ == "__main__":
    if "--version" in sys.argv:
        if sys.stdout:
            print(COACH_VERSION)
    elif "--self-test" in sys.argv:
        self_test()
    else:
        Coach().run()
