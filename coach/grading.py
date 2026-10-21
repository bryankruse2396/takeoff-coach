"""Grading a measurement against the step's answer key."""

from coach import lessons
from coach.lessons import SCALES, TRUE_FT


def with_article(word):
    """'an Area', 'a Perimeter'."""
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def measured(rec, kind):
    """The quantity a step grades: area (SF), length or perimeter (LF), or the number of items counted."""
    if kind == "count":
        n = rec.get("count")
        return float(n if n is not None else (rec.get("points") or 0))
    return rec[{"area": "area", "length": "length", "perimeter": "perim"}[kind]]


def points_matter(step):
    """Extra or fewer corners don't matter for an area, length or perimeter: the quantity does.
    For counts every point is an item, so the number of points is the answer."""
    return step.get("points_matter", step.get("kind") == "count")


def evaluate(step, rec):
    kind = step["kind"]
    val = measured(rec, kind)
    unit = {"area": "SF", "count": "EA"}.get(kind, "LF")
    if step.get("dwg") and rec.get("dwg") and step["dwg"] not in rec["dwg"]:
        return (False, f"That measurement is on {rec['dwg']}. Do this one on {step.get('dwg_name') or step['dwg']}.",
                "Navigating drawings")
    if rec.get("qty") is not None and abs(rec["qty"] - val) > max(0.01, abs(val) * 0.001):
        if not rec.get("trace") and rec.get("primary"):
            return (False, f"That's {with_article(rec['primary'].title())} measurement ({rec['qty']:,.2f}), "
                           f"not {with_article(kind)}. Delete it and use {with_article(kind.title())} trace: click {kind.title()} on the Home tab or double-click "
                           f"'{kind.title()}' in the Traces list.", "Choosing the right trace")
        return (False, f"That measurement used the trace '{rec['trace']}', whose main quantity isn't {kind} "
                       f"(it reports {rec['qty']:,.2f}). Delete it and use {with_article(kind.title())} trace: double-click "
                       f"'{kind.title()}' in the Traces list.",
                "Choosing the right trace")
    if "expected" not in step:
        need = step.get("min_points", 1 if kind == "count" else 2)
        if (rec.get("points") is None or rec["points"] >= need) and val > 0:
            if kind == "count":
                return True, f"{val:.0f} counted.", None
            return True, f"{val:,.2f} {unit}" + (f" with {rec['points']} points." if rec.get("points") else "."), None
        return False, f"Click at least {need} points before pressing S.", "Finish, undo, describe"
    exp = step["expected"]
    if kind == "count":
        # every item counts: no tolerance, and the message doesn't give the answer away
        n, want = int(round(val)), int(round(exp))
        if n == want:
            return True, f"{n} counted. That's all of them.", None
        if n < want:
            return False, (f"{n} counted, which is too few. Look over the whole drawing again for ones you missed, "
                           "then add them to the same count."), step["skill"]
        return False, (f"{n} counted, which is too many. Check for one clicked twice or something that isn't one of "
                       "them, and remove those points."), step["skill"]
    g = {**lessons.LESSON.get("grading", {}), **{k: step[k] for k in ("full_credit_within", "pass_within") if k in step}}
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
    if step.get("cutout") and r > 1 + pass_tol:
        return False, (f"{val:,.2f} {unit} is {100 * (r - 1):.1f}% more than it should be: the cutout is probably missing "
                       f"or traced the wrong way. After the outline, press G (or click Disconnected Point) and trace the "
                       f"cutout counter-clockwise, so it subtracts.{pts_note}"), step["skill"]
    if step.get("disconnected") and r > 1 + pass_tol:
        return False, (f"{val:,.2f} {unit} is {100 * (r - 1):.1f}% longer than it should be: the gap was probably measured "
                       f"too. At the end of the first piece, press G (or click Disconnected Point), then start the next piece "
                       f"on the other side of the gap.{pts_note}"), step["skill"]
    if kind == "perimeter" and 0.45 < r < 0.9:
        return False, f"{val:,.2f} LF looks like one wall is missing. Check you clicked all 4 corners.", step["skill"]
    if abs(r - 1) <= pass_tol:
        # close enough to pass, for partial credit, with the tip for getting it exact
        return ("partial", f"{val:,.2f} {unit}: close enough to pass ({abs(100 * (r - 1)):.1f}% "
                           f"{'above' if r > 1 else 'below'} {exp:,.2f}). For full credit, zoom in and click each corner "
                           f"on the same face of the wall.{pts_note}", step["skill"])
    return False, f"{val:,.2f} {unit} is {abs(100 * (r - 1)):.1f}% {'high' if r > 1 else 'low'} (target {exp:,.2f}). Zoom in and click each corner on the same wall line the answer key uses (inside face vs. outside face changes the total).{pts_note}", step["skill"]
