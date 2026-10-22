"""In practice a block starts with what you'll learn and ends with a recap; neither is graded or uploaded."""
import tkinter
import unittest.mock as um

from conftest import buttons, press

BLOCK = {"id": "nav_select", "title": "Switch between Select and Multi-Select", "answer_key": {},
         "intro": "In this lesson you'll learn how to select measurements.", "recap": "You can now select measurements.",
         "steps": [{"id": "ms", "type": "click", "target": "multiselect", "skill": "Navigating the ribbon", "text": "Click Multi-Select."}]}


def test_intro_then_step_then_recap(app):
    from coach import lessons
    from coach.lessons import build_steps
    c = app
    c.watcher = um.MagicMock(state={}, baseline_guids=set())
    uploads = []
    c._upload_practice = lambda *a, **k: uploads.append(a)
    lessons.LESSON.clear()
    lessons.LESSON.update({"id": "basic_navigate", "title": "Navigate the window", "block_ids": ["nav_select"],
                           "steps": build_steps(["nav_select"], [BLOCK]), "grading": {}})
    c.test = None
    c.results, c.parked, c.step_i, c.step_i_locked, c.passed_vals = [], {}, -1, -1, set()
    c.next_step()
    c.root.update()
    texts = [w.cget("text") for w in c.body.winfo_children() if isinstance(w, tkinter.Label)]
    assert "What you'll learn" in texts and BLOCK["intro"] in texts
    assert "Start" in buttons(c.body) and "Hint" not in buttons(c.body)
    c.on_click(10, 10)  # clicks don't count against an intro screen
    assert c.cur["wrong"] == 0
    press(c.body, "Start")
    c.root.update()
    assert c.cur["id"] == "nav_select.ms"
    c._close_step("passed", 100)
    c.root.update()
    assert c.cur["id"] == "nav_select.recap" and "Continue" in buttons(c.body)
    press(c.body, "Continue")
    c.root.update()
    assert [r["id"] for r in c.results] == ["nav_select.intro", "nav_select.ms", "nav_select.recap"]
    assert "100%" in c.h1.cget("text")  # only the real step is scored
