"""A test with two tasks: Back, the review screen, Redo, Submit, and practising what was missed."""
import tkinter
import unittest.mock as um

from conftest import buttons, write_catalog

BLOCKS = [
    {"id": "meas_area", "title": "Measure an area (Laundry room)", "answer_key": {}, "steps": [
        {"id": "btn", "type": "click", "target": "trace_area", "skill": "Choosing the right trace",
         "text": "Practice: click Area.", "test_text": "Select the Area trace.", "ungraded": True},
        {"id": "area", "type": "measure", "kind": "area", "expected": 604.42, "points": 8,
         "skill": "Polar mode and direction", "text": "Practice: hold Ctrl, 8 corners.",
         "test_text": "Measure the Laundry Room."},
        {"id": "desc", "type": "describe", "of": "area", "answer": "Laundry Room Area", "skill": "Finish, undo, describe",
         "text": "Practice: press D.", "test_text": "Describe it."}]},
    {"id": "meas_line", "title": "Measure a line segment", "answer_key": {}, "steps": [
        {"id": "len", "type": "measure", "kind": "length", "min_points": 2, "skill": "Choosing the right trace",
         "text": "Practice: click two ends.", "test_text": "Measure one wall."}]}]


def review_labels(c):
    return [w.cget("text") for w in c.body.winfo_children()[1].winfo_children()[0].winfo_children()
            if isinstance(w, tkinter.Label)]


def test_back_review_redo_submit_and_retry(app):
    from coach import lessons
    from coach.lessons import build_steps
    c = app
    write_catalog(c.catalog_file, {"lessons": [{"id": "basic_measure", "title": "Measure", "tier": "basic",
                                                "block_ids": ["meas_area", "meas_line"]}], "tests": [], "blocks": BLOCKS})
    c.watcher = um.MagicMock(state={}, baseline_guids=set())
    ended = []
    c.end_test = lambda status, score=None, summary=None: ended.append((status, score)) or c.__dict__.update(test=None)
    c._upload_practice = lambda *a, **k: None

    def close(status, score, **extra):
        c.cur.update(extra)
        c._close_step(status, score)

    L = lessons.LESSON
    L.clear()
    L.update({"id": "basic_test", "title": "Basic certification", "block_ids": ["meas_area", "meas_line"],
              "steps": build_steps(["meas_area", "meas_line"], BLOCKS, test=True), "grading": {}})
    c.test = {"session_id": "s1", "title": "Basic certification", "id": "basic_test", "pass_score": 80,
              "timeout": 300, "blocks": 2}
    c.results, c.parked, c.step_i, c.step_i_locked, c.passed_vals = [], {}, -1, -1, set()
    c.next_step()
    c.root.update()
    assert c.cur["id"] == "meas_area.btn" and not any("Back" in b for b in buttons(c.body))
    close("passed", 100)
    assert c.cur["id"] == "meas_area.area" and any("Back" in b for b in buttons(c.body))
    c.cur["failed"].add("miss@0")
    c.cur["wrong"] = 1
    close("passed", 50, _passed_sig=("sig",))
    c.passed_vals.add(("sig",))
    assert c.cur["id"] == "meas_area.desc"

    # Back: the area step reopens with its miss carried over, and its measurement can be submitted again
    c.go_back()
    c.root.update()
    assert c.cur["id"] == "meas_area.area"
    assert len(c.cur["failed"]) == 1 and c.cur["wrong"] == 1
    assert ("sig",) not in c.passed_vals
    assert c._score() == 50
    close("passed", c._score())
    assert c.cur["id"] == "meas_area.desc"
    close("skipped", 0)
    close("passed", 100)
    c.root.update()

    # the end of a test is a review screen, not a submit
    assert c.reviewing and not ended and c.h1.cget("text") == "Review your test"
    assert buttons(c.body).count("Redo") == 2 and "Submit test" in buttons(c.body)
    assert any("not right yet" in t for t in review_labels(c))
    c.redo_block("meas_area")
    c.root.update()
    assert c.cur["id"] == "meas_area.btn"
    close("passed", 100)
    close("passed", 50)
    close("passed", 100)
    c.root.update()
    assert c.reviewing and "✓ done" in review_labels(c)
    with um.patch("tkinter.messagebox.askyesno", return_value=True):
        c.submit_test()
    c.root.update()
    assert len(ended) == 1 and ended[0][0] == "completed"
    assert [r["id"] for r in c.results] == [s["id"] for s in L["steps"]]

    # the missed task is offered as practice, in practice wording, logged under its lesson
    c.start_lesson = lambda: None
    c.preflight = lambda then, test=False, steps=None: then()
    btn = [w for w in c.body.winfo_children() if isinstance(w, tkinter.Button) and "Measure an area" in w.cget("text")][0]
    btn.invoke()
    L = lessons.LESSON
    assert c.test is None and c.mode.get() == "practice" and L["block_ids"] == ["meas_area"]
    assert L["steps"][1]["text"].startswith("Practice:")
    assert L["id"] == "basic_measure"
