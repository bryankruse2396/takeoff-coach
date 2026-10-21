"""The count lesson end to end through the coach's checking code: pick Count, count, describe."""
import unittest.mock as um


BLOCKS = [{"id": "meas_count", "title": "Count items (toilets)", "answer_key": {}, "steps": [
    {"id": "cnt", "type": "measure", "kind": "count", "expected": 15, "dwg": "A1.1", "skill": "Counting items", "text": "x"},
    {"id": "desc", "type": "describe", "of": "cnt", "answer": "Toilets", "skill": "Finish, undo, describe", "text": "y"}]}]


def settle(c, seconds=2.0):
    """A passed step shows its message for a moment before the next one opens."""
    import time
    end = time.time() + seconds
    while time.time() < end:
        c.root.update()
        time.sleep(0.05)


def reading(header, values, primary):
    return {"header": header, "values": values, "primary": primary,
            "sig": (header, tuple(sorted((k, round(v, 2)) for k, v in values.items())))}


def test_count_then_describe(app):
    from coach import lessons
    from coach.lessons import build_steps
    c = app
    c.watcher = um.MagicMock(state={}, baseline_guids=set())
    c._upload_practice = lambda *a, **k: None
    lessons.LESSON.clear()
    lessons.LESSON.update({"id": "basic_more_measuring", "title": "Counts", "block_ids": ["meas_count"],
                           "steps": build_steps(["meas_count"], BLOCKS), "grading": {}})
    c.test = None
    c.results, c.parked, c.step_i, c.step_i_locked, c.passed_vals = [], {}, -1, -1, set()
    c.next_step()
    c.root.update()
    assert c.cur["id"] == "meas_count.cnt"
    # 14 toilets: not passed, and the message doesn't give the answer away
    c.on_qtylist(reading("Count", {"point count": 14.0}, "point count"), forced=True)
    assert c.cur["id"] == "meas_count.cnt" and c.cur["failed"]
    # all 15
    c.on_qtylist(reading("Count", {"point count": 15.0}, "point count"), forced=True)
    settle(c)
    assert c.cur["id"] == "meas_count.desc", c.cur["id"]
    c.on_qtylist(reading("Toilets", {"point count": 15.0}, "point count"), forced=True)
    settle(c)
    assert c.results[-1]["id"] == "meas_count.desc" and c.results[-1]["status"].startswith("passed"), c.results[-1]
