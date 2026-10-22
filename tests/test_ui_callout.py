"""The instruction callout never gets in the way of reading the Quantity List."""
import unittest.mock as um

from winstub import patch_all


def test_callout_shown_beside_the_quantity_list(app):
    app.targets["qtylist"] = (0, 760, 460, 870)
    app.callout_pos = (0.0, 0.84)  # the learner left it on top of the list
    app.callout_text = None
    bx, by, bw, bh = app._show_callout("7. Measure the Laundry room area", False, 0, 0, 1400, 900)
    app.root.update()
    assert bx >= 460 or by + bh <= 760 or by >= 870
    assert app.callout_pos == (0.0, 0.84)  # their spot is kept for when it doesn't cover the list


def test_dragged_over_the_list_reads_etakeoffs_own_picture_without_hiding(app):
    app._show_callout("x", False, 0, 0, 1400, 900)
    app.root.update()
    app.callout.geometry("+10+770")
    app.root.update()
    seen = []
    patch_all("print_window_region", lambda h, box: seen.append(app.callout.state()) or (1, 1, b"\0\0\0"))
    app.reader = um.MagicMock()
    shot = app._grab_clear((0, 760, 460, 870))
    assert shot == (1, 1, b"\0\0\0") and seen == ["normal"]  # never hidden, so it doesn't flash
    app.reader.grab.assert_not_called()


def test_falls_back_to_hiding_if_windows_cant(app):
    app._show_callout("x", False, 0, 0, 1400, 900)
    app.root.update()
    app.callout.geometry("+10+770")
    app.root.update()
    patch_all("print_window_region", lambda h, box: None)
    seen = []
    app.reader = um.MagicMock()
    app.reader.grab.side_effect = lambda box: seen.append(app.callout.state()) or (1, 1, b"\0\0\0")
    app._grab_clear((0, 760, 460, 870))
    app.root.update()
    assert seen == ["withdrawn"] and app.callout.state() == "normal"


def test_not_over_the_list_is_a_plain_screenshot(app):
    app._show_callout("x", False, 0, 0, 1400, 900)
    app.root.update()
    app.callout.geometry("+900+100")
    app.root.update()
    app.reader = um.MagicMock()
    app.reader.grab.return_value = (1, 1, b"\0\0\0")
    app._grab_clear((0, 760, 460, 870))
    app.reader.grab.assert_called_once()


def test_wrong_trace_from_screen_is_rechecked_with_etakeoff_data(app):
    parsed = {"header": "", "values": {"perimeter": 114.18, "area": 626.66}, "primary": "perimeter",
              "sig": ("", (("area", 626.66), ("perimeter", 114.18)))}
    app.watcher = um.MagicMock()
    app.watcher.read_all = lambda: {("g", "Area"): {"guid": "g", "trace": "Area", "desc": "Area", "qty": 626.66,
                                                     "uom": "SqFt", "area": 626.66, "length": 0.0, "perim": 114.18,
                                                     "points": 8, "dwg": "004 A1.1 1ST FLOOR PLAN"}}
    ex = app._exact_record(parsed)
    assert ex and ex["trace"] == "Area"
    app.watcher.read_all = lambda: {}
    assert app._exact_record(parsed) is None


def test_arrow_is_not_redrawn_when_nothing_changed(app):
    """Redrawing the box and arrow on every tick made them flicker; only redraw when they change."""
    from coach import lessons
    lessons.LESSON.clear()
    lessons.LESSON.update({"id": "x", "title": "x", "grading": {},
                           "steps": [{"id": "ms", "type": "click", "target": "multiselect", "text": "Click Multi-Select."}]})
    app.test, app.step_i, app.flash, app.showing_found_until = None, 0, None, 0
    app.targets["multiselect"] = (380, 120, 500, 150)
    app.callout_pos = (0.3, 0.8)
    app.draw_overlay()
    app.root.update()
    first = app.cv.find_all()
    assert len(first) == 2  # the box and the arrow
    for _ in range(5):
        app.draw_overlay()
    app.root.update()
    assert app.cv.find_all() == first  # same drawing kept, never erased
    app.cv.delete("all")  # another screen cleared it
    app.draw_overlay()
    assert len(app.cv.find_all()) == 2
    app.targets["multiselect"] = (600, 120, 720, 150)  # the button moved: redraw
    app.draw_overlay()
    assert app.cv.find_all() != first
