"""Lessons and tests: the current lesson, answer keys, and turning the site's blocks into steps."""
import copy
import json
import os

from coach.builtin_lessons import BUILTIN_LESSON, BUILTIN_LESSONS, TARGETS
from coach.config import CATALOG_FILE, HERE
from coach.log import dlog


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
        for k in ("id", "text", "skill") + need:
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
    """Instructor-recorded answers replace the starting numbers (eTakeoff results depend on where walls are clicked).
    Returns this lesson's part of the answer file."""
    ans = read_answer_file().get(LESSON["id"], {})
    for st in LESSON["steps"]:
        if st["id"] in ans and st["type"] == "measure" and "expected" in st:
            st["expected"] = ans[st["id"]]["expected"]
            st["points"] = ans[st["id"]].get("points", st.get("points"))
    return ans


def read_catalog():
    try:
        with open(CATALOG_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def build_steps(block_ids, blocks, test=False):
    """Coach steps for a list of blocks. Step ids become 'block.step' so every block's steps stay distinct,
    and the block's answer key (recorded in Instructor mode) replaces the starting values.
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
