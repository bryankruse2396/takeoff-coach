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
