"""Grading a measurement against a step's answer key."""
from coach.grading import evaluate, with_article
from coach.qty_list import screen_rec

AREA_STEP = {"id": "a", "kind": "area", "expected": 600.0, "points": 8, "skill": "Measuring areas"}


def rec(area=0.0, length=0.0, perim=0.0, qty=None, trace="Area", points=8, dwg=None):
    return {"area": area, "length": length, "perim": perim, "qty": area if qty is None else qty,
            "trace": trace, "points": points, "dwg": dwg}


def test_within_3_percent_is_full_credit():
    ok, msg, _ = evaluate(AREA_STEP, rec(area=612.0))
    assert ok is True, msg


def test_within_10_percent_passes_with_partial_credit():
    ok, msg, _ = evaluate(AREA_STEP, rec(area=640.0))
    assert ok == "partial", msg


def test_far_off_fails():
    ok, msg, _ = evaluate(AREA_STEP, rec(area=800.0))
    assert ok is False and "high" in msg


def test_counter_clockwise_area_is_explained():
    ok, msg, skill = evaluate(AREA_STEP, rec(area=-600.0))
    assert ok is False and "counter-clockwise" in msg


def test_wrong_trace_from_eTakeoff_data():
    # a Perimeter trace: its main quantity is the perimeter, not the area asked for
    ok, msg, skill = evaluate(AREA_STEP, rec(area=600.0, perim=100.0, qty=100.0, trace="Perimeter"))
    assert ok is False and skill == "Choosing the right trace" and "an Area trace" in msg


def test_wrong_trace_message_from_the_screen_reads_naturally():
    parsed = {"header": "", "values": {"perimeter": 114.18, "area": 626.66}, "primary": "perimeter", "sig": ("", ())}
    ok, msg, _ = evaluate({**AREA_STEP, "expected": 626.66}, screen_rec(parsed))
    assert ok is False
    assert "a Perimeter measurement" in msg and "not an area" in msg and "an Area trace" in msg


def test_with_article():
    assert with_article("Area") == "an Area" and with_article("Length") == "a Length"


# --- counts, cutouts and disconnected lines
COUNT_STEP = {"id": "c", "kind": "count", "expected": 12, "skill": "Counting items"}


def count_rec(n):
    return {"area": 0.0, "length": 0.0, "perim": 0.0, "qty": float(n), "trace": "Count", "points": n, "dwg": None}


def test_count_must_be_exact_and_doesnt_give_the_answer():
    assert evaluate(COUNT_STEP, count_rec(12))[0] is True
    ok, msg, _ = evaluate(COUNT_STEP, count_rec(11))
    assert ok is False and "too few" in msg and "12" not in msg
    ok, msg, _ = evaluate(COUNT_STEP, count_rec(13))
    assert ok is False and "too many" in msg and "12" not in msg


def test_count_without_answer_key_passes_any_count():
    ok, msg, _ = evaluate({"id": "c", "kind": "count", "skill": "s"}, count_rec(1))
    assert ok is True and "1 counted" in msg


def test_count_read_off_the_screen():
    parsed = {"header": "Count", "values": {"count": 12.0}, "primary": "count", "sig": ("", ())}
    rec = screen_rec(parsed)
    assert "count" in rec["has"] and evaluate(COUNT_STEP, rec)[0] is True
    parsed = {"header": "Count", "values": {"point count": 12.0}, "primary": "point count", "sig": ("", ())}
    rec = screen_rec(parsed)
    assert "count" in rec["has"] and evaluate(COUNT_STEP, rec)[0] is True


def test_area_used_for_a_count_is_the_wrong_trace():
    ok, msg, skill = evaluate(COUNT_STEP, rec(area=50.0, perim=30.0, qty=50.0, trace="Area", points=12))
    assert ok is False and skill == "Choosing the right trace"


def test_cutout_missing_is_explained():
    step = {"id": "p", "kind": "area", "expected": 2000.0, "cutout": True, "skill": "Cutouts"}
    assert evaluate(step, rec(area=2010.0))[0] is True
    ok, msg, _ = evaluate(step, rec(area=2600.0))  # the pool wasn't subtracted
    assert ok is False and "cutout" in msg and "counter-clockwise" in msg


def test_disconnected_gap_measured_is_explained():
    step = {"id": "l", "kind": "length", "expected": 30.0, "disconnected": True, "skill": "Disconnected points"}
    assert evaluate(step, rec(length=30.2, qty=30.2, trace="Length"))[0] is True
    ok, msg, _ = evaluate(step, rec(length=34.0, qty=34.0, trace="Length"))  # the door opening was included
    assert ok is False and "Disconnected Point" in msg


def test_lit_button_box_includes_its_icon():
    from coach.find_buttons import fit_button
    W, H = 200, 60
    px = [[(240, 240, 240)] * W for _ in range(H)]
    for y in range(15, 45):            # an orange (lit) button from x=40 to x=150
        for x in range(40, 150):
            px[y][x] = (250, 140, 40)
    for y in range(20, 40):            # its icon, not orange, at x=44..62
        for x in range(44, 62):
            px[y][x] = (30, 60, 160)
    rgb = bytes(c for row in px for p in row for c in p)
    box = fit_button((70, 24, 130, 36), rgb, W, H)  # the label's text box
    assert box and box[0] <= 46, box
