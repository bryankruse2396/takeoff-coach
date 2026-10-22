"""The learner's own training projects and which drawings a lesson uses."""
import re


def norm_name(t):
    """Compare project names ignoring case, extra spaces and the kind of dash."""
    return " ".join((t or "").replace("\u2013", "-").replace("\u2014", "-").lower().split())


def open_project_name(title):
    return title.split("Project:", 1)[1].strip() if title and "Project:" in title else ""


def drawing_codes(steps):
    """Sheet codes a set of steps works on, e.g. {'A1.1'} from steps marked dwg='A1.1'."""
    return {st["dwg"] for st in steps if st.get("dwg")}


def on_drawings(rec, codes):
    d = (rec.get("dwg") or "").upper()
    return any(re.search(r"(^|\s)" + re.escape(c.upper()) + r"(\s|$)", d) for c in codes)


_DIGITS = str.maketrans({"I": "1", "l": "1", "i": "1", "|": "1", "O": "0", "o": "0"})


def open_sheet(text):
    """The sheet code in a drawing name read off the screen ('004 A1.3 3RD FLOOR PLAN' -> 'A1.3'),
    forgiving OCR's usual misreads (AI.1, A1.l). None if there isn't one."""
    for tok in (text or "").replace(",", ".").split():
        for pat in (r"^([A-Za-z])([0-9IlOo|][0-9IlOo|.]*)$", r"^([A-Za-z]{2})([0-9IlOo|][0-9IlOo|.]*)$"):
            m = re.match(pat, tok)
            if m and any(c.isdigit() for c in m.group(2)):
                return (m.group(1).upper() + m.group(2).translate(_DIGITS)).rstrip(".")
    return None
