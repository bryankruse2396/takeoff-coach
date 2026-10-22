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


def test_tests_keep_only_some_descriptions():
    import random
    from coach.lessons import pick_descriptions
    steps = [{"id": f"m{i}", "type": "measure"} for i in range(10)] + [{"id": f"d{i}", "type": "describe"} for i in range(10)]
    kept = pick_descriptions(steps, 20, random.Random(1))
    assert len([s for s in kept if s["type"] == "measure"]) == 10
    assert len([s for s in kept if s["type"] == "describe"]) == 2
    few = pick_descriptions(steps[:10] + steps[10:12], 20, random.Random(1))  # 2 descriptions: still at least one
    assert len([s for s in few if s["type"] == "describe"]) == 1
    assert pick_descriptions(steps, None) == steps  # older databases: keep them all
    assert not [s for s in pick_descriptions(steps, 0) if s["type"] == "describe"]
    assert [s["id"] for s in kept] == [s["id"] for s in steps if s in kept]  # order unchanged


def test_practice_opens_and_closes_blocks_with_intro_and_recap():
    from coach.lessons import lesson_problems
    blocks = [{**BLOCKS[0], "intro": "You'll learn areas.", "recap": "You can measure areas."}]
    practice = build_steps(["meas_area"], blocks)
    assert practice[0]["type"] == "info" and practice[0]["kind"] == "intro" and practice[0]["ungraded"]
    assert practice[-1]["type"] == "info" and practice[-1]["kind"] == "recap"
    assert lesson_problems({"id": "x", "title": "x", "steps": [practice[0], practice[-1]]}) == []
    test = build_steps(["meas_area"], blocks, test=True)
    assert not [s for s in test if s["type"] == "info"]
    assert not [s for s in build_steps(["meas_area"], BLOCKS) if s["type"] == "info"]  # none written: none shown
