"""The pool deck in practice: room, then the pool cut out, then the spa, all one measurement.
And the HVAC closet wall, which passes on eTakeoff's Group Length row."""
import sys
import unittest.mock as um

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from test_ui_count_lesson import reading, settle  # noqa: E402


def blocks():
    """The site's blocks for this lesson (a copy of database/updates/05 in the takeoff-training-site repo)."""
    import json
    import os
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "blocks_counts_cutouts.json")) as fh:
        return json.load(fh)


def start(c, block_ids):
    from coach import lessons
    from coach.lessons import build_steps
    c.watcher = um.MagicMock(state={}, baseline_guids=set())
    c._upload_practice = lambda *a, **k: None
    lessons.LESSON.clear()
    lessons.LESSON.update({"id": "basic_more_measuring", "title": "More", "block_ids": block_ids,
                           "steps": build_steps(block_ids, blocks()), "grading": {}})
    c.test = None
    c.results, c.parked, c.step_i, c.step_i_locked, c.passed_vals = [], {}, -1, -1, set()
    c.next_step()
    c.step_known = set()
    c.root.update()


def area(v, perim):
    return reading("Area", {"area": v, "perimeter": perim}, "area")


def test_pool_deck_in_three_checked_steps(app):
    c = app
    start(c, ["meas_cutout"])
    c._close_step("passed", 100)  # the Area trace step
    assert c.cur["id"] == "meas_cutout.room"
    c.on_qtylist(area(1934.85, 190.0), forced=True)
    settle(c)
    assert c.cur["id"] == "meas_cutout.pool", c.cur["id"]
    # eTakeoff has published the room measurement by now; the pool step keeps working on it
    c.watcher.state = {("g1", "Area"): {"guid": "g1", "trace": "Area", "desc": "Area", "area": 1934.85, "length": 0.0,
                                        "perim": 190.0}}
    c.step_known = {"g1"}
    c.on_qtylist(area(1934.85 * 1.0 + 551.97, 190.0), forced=True)  # pool traced clockwise: it added
    assert c.cur["id"] == "meas_cutout.pool" and c.cur["failed"]
    c.on_qtylist(area(1382.88, 190.0), forced=True)
    settle(c)
    assert c.cur["id"] == "meas_cutout.deck", c.cur["id"]
    c.on_qtylist(area(1382.88, 190.0), forced=True)  # spa forgotten: same reading as the last step, ignored
    c.on_qtylist(area(1382.88 + 0.01, 190.0), forced=True)  # nearly the same: spa not cut out
    assert c.cur["id"] == "meas_cutout.deck"
    c.on_qtylist(area(1325.87, 190.0), forced=True)
    settle(c)
    assert c.cur["id"] == "meas_cutout.desc", c.cur["id"]


def test_closet_wall_passes_on_the_group_row(app):
    c = app
    start(c, ["meas_disconnected"])
    c._close_step("passed", 100)
    assert c.cur["id"] == "meas_disconnected.walls"
    c.on_qtylist(reading("Length", {"length": 13.05}, "length"), forced=True)  # one piece: no groups
    assert c.cur["id"] == "meas_disconnected.walls" and c.cur["failed"]
    c.on_qtylist(reading("Length", {"length": 13.02, "group length": 4.1}, "length"), forced=True)
    settle(c)
    assert c.cur["id"] == "meas_disconnected.desc", c.cur["id"]
