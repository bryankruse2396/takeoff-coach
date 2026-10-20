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
