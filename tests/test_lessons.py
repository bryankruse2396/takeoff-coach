"""Turning the site's blocks into coach steps, for practice and for tests."""
from coach.lessons import build_steps

BLOCKS = [{"id": "meas_area", "title": "Measure an area", "answer_key": {"area": {"expected": 604.42, "points": 8}},
           "steps": [
               {"id": "btn", "type": "click", "text": "Practice: click Area.", "test_text": "Select the Area trace.",
                "ungraded": True},
               {"id": "tip", "type": "click", "text": "Practice only.", "test_skip": True},
               {"id": "area", "type": "measure", "kind": "area", "expected": 559, "text": "Practice: 8 corners.",
                "test_text": "Measure the Laundry Room."},
               {"id": "desc", "type": "describe", "of": "area", "text": "Name it."}]}]


def test_practice_keeps_every_step_and_its_wording():
    steps = build_steps(["meas_area"], BLOCKS)
    assert [s["id"] for s in steps] == ["meas_area.btn", "meas_area.tip", "meas_area.area", "meas_area.desc"]
    assert steps[0]["text"] == "Practice: click Area."


def test_tests_state_the_task_not_the_method():
    steps = build_steps(["meas_area"], BLOCKS, test=True)
    assert [s["id"] for s in steps] == ["meas_area.btn", "meas_area.area", "meas_area.desc"]
    assert steps[0]["text"] == "Select the Area trace." and steps[0]["ungraded"]
    assert steps[1]["text"] == "Measure the Laundry Room."


def test_answer_key_replaces_guide_values_and_links_describe_steps():
    steps = build_steps(["meas_area"], BLOCKS)
    area = next(s for s in steps if s["id"] == "meas_area.area")
    assert area["expected"] == 604.42 and area["points"] == 8
    assert steps[-1]["of"] == "meas_area.area"


def test_unknown_blocks_are_skipped():
    assert build_steps(["nope"], BLOCKS) == []
