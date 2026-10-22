"""Wrong drawing: the coach shows how to get to the right one. Traces list: the coach follows it when it's scrolled."""
import time

from coach import lessons
from coach.find_buttons import locate_targets, trace_rows
from coach.projects import open_sheet


def word(text, x, y, w=None, h=14):
    return {"text": text, "x": x, "y": y - h / 2, "w": w or 8 * len(text), "h": h}


def line(text, x, y, h=14):
    ws, cx = [], x
    for t in text.split():
        ws.append(word(t, cx, y, h=h))
        cx += 8 * len(t) + 6
    return {"text": text, "x": x, "y": y, "words": ws}


def test_sheet_code_read_off_the_drawing_box():
    assert open_sheet("006 A1.3 3RD FLOOR PLAN") == "A1.3"
    assert open_sheet("004 AI.1 1ST FLOOR PLAN") == "A1.1"  # OCR read 1 as I
    assert open_sheet("004 A1.l 1ST FLOOR PLAN") == "A1.1"
    assert open_sheet("014 A1.10 DETAILS") == "A1.10"
    assert open_sheet("001 CS1.1 COVER SHEET") == "CS1.1"
    assert open_sheet("FLOOR PLAN") is None and open_sheet("") is None


def test_scan_finds_the_navigation_drawing_box():
    lines = [line("004 A1.1 1ST FLOOR PLAN", 122, 114), line("Page 1 of 1", 122, 145),
             line("Navigation", 205, 172), line("Takeoff", 738, 172), line("Select", 410, 94)]
    found = locate_targets(lines, 2000, 1150)
    x1, y1, x2, y2 = found["dwg_box"]
    assert x1 < 122 and y1 < 107 and y2 > 121 and x2 > 300  # around the drawing name, not the Page box
    assert y2 < 138


def rows_lines(names, top=20, pitch=23, x=1570):
    return [line(n, x if not n.startswith(" ") else x + 40, top + i * pitch) for i, n in enumerate(names)]


def test_trace_rows_only_what_is_showing():
    # Perimeter is scrolled out of sight below Length: it must not be guessed
    lines = rows_lines(["Paint & Wall Covering", "Roofing", " Roof Area", "Area", "Count", "Length"])
    rows = trace_rows(lines, 470, 330)
    assert set(rows) == {"area", "count", "length"}
    assert rows["area"][1] < 20 + 3 * 23 < rows["area"][3]  # the top-level Area, not "Roof Area"


def test_trace_rows_fill_in_one_ocr_missed_between_two():
    # Count's name hidden by its swatch: Area at 100, Count not read, Length at 146, Perimeter at 169
    lines = [line("Area", 1570, 100), line("Length", 1570, 146), line("Perimeter", 1570, 169)]
    rows = trace_rows(lines, 470, 330)
    assert rows["count"][1] < 123 < rows["count"][3]


def _practice(app, steps):
    lessons.LESSON.clear()
    lessons.LESSON.update({"id": "x", "title": "x", "grading": {}, "steps": steps})
    app.test, app.step_i, app.flash, app.showing_found_until, app.step_i_locked = None, 0, None, 0, -1
    app.cur = {"id": steps[0]["id"], "clicks": 0, "wrong": 0, "failed": set(), "hints": 0}
    app.callout_pos = (0.3, 0.8)


def _read_dwg(app, text):
    for _ in range(2):  # the same reading twice before the coach acts on it
        app._on_watch_read("dwg", [line(text, 122, 114)], None)


def test_wrong_drawing_points_to_the_navigation_box(app):
    _practice(app, [{"id": "m", "type": "measure", "kind": "area", "dwg": "A1.1", "text": "Measure the Laundry room."}])
    app.targets["dwg_box"] = [112, 100, 368, 128]
    _read_dwg(app, "006 A1.3 3RD FLOOR PLAN")
    app.draw_overlay()
    app.root.update()
    txt = app.callout_label.cget("text")
    assert "A1.1" in txt and "you're on A1.3" in txt and "Navigation" in txt
    assert len(app.cv.find_all()) == 2  # box around the drawing list and an arrow to it
    _read_dwg(app, "004 A1.1 1ST FLOOR PLAN")
    app.draw_overlay()
    assert "Laundry" in app.callout_label.cget("text") and app.cv.find_all() == ()


def test_one_misread_or_an_old_reading_never_shows_it(app):
    _practice(app, [{"id": "m", "type": "measure", "kind": "area", "dwg": "A1.1", "text": "Measure the Laundry room."}])
    app.targets["dwg_box"] = [112, 100, 368, 128]
    _read_dwg(app, "004 A1.1 1ST FLOOR PLAN")
    app._on_watch_read("dwg", [line("006 A1.3 3RD FLOOR PLAN", 122, 114)], None)  # once only
    assert app.wrong_drawing(lessons.LESSON["steps"][0]) is None
    _read_dwg(app, "006 A1.3 3RD FLOOR PLAN")
    app._dwg_t = time.time() - 30
    assert app.wrong_drawing(lessons.LESSON["steps"][0]) is None


def test_clean_drawing_screen_says_which_drawing_is_open(app):
    app._clear()
    app.show_clear_drawing(lambda: None, False, [], 1, {"A1.1"})
    _read_dwg(app, "006 A1.3 3RD FLOOR PLAN")
    assert "You're on A1.3 now" in app.status.cget("text") and "Navigation" in app.status.cget("text")
    _read_dwg(app, "004 A1.1 1ST FLOOR PLAN")
    assert "You're on A1.1." in app.status.cget("text")


def test_scrolled_traces_list_is_followed(app):
    _practice(app, [{"id": "p", "type": "click", "target": "trace_perimeter", "also": ["perimeter"],
                     "text": "Pick the Perimeter trace in the Traces control panel."}])
    pane = [1510, 270, 1980, 600]
    app.targets["traces_pane"] = pane
    app.targets["trace_perimeter"] = [1510, 590, 1960, 615]  # an old guess, below the list
    passed = []
    app._pass = lambda msg="", **k: passed.append(msg)
    # Perimeter isn't showing: no box at the old spot, and the callout says to scroll
    app._on_watch_read("traces", [line(n, 60, 20 + 23 * i) for i, n in enumerate(["Roofing", "Area", "Count", "Length"])], None)
    assert "trace_perimeter" not in app.targets
    app.draw_overlay()
    assert "Scroll the list down" in app.callout_label.cget("text")
    # the learner scrolls; a click on Perimeter is judged on a fresh reading
    app.note_trace_click(1600, 270 + 20 + 23 * 3)
    app.trace_click["sent"] = True
    app._on_watch_read("traces", [line(n, 60, 20 + 23 * i) for i, n in enumerate(["Area", "Count", "Length", "Perimeter"])], None)
    assert passed == [""]
    assert app.targets["trace_perimeter"][1] < 270 + 20 + 69 < app.targets["trace_perimeter"][3]


def test_click_on_another_trace_is_wrong(app):
    _practice(app, [{"id": "p", "type": "click", "target": "trace_perimeter", "skill": "Choosing the right trace", "text": "Pick the Perimeter trace."}])
    app.targets["traces_pane"] = [1510, 270, 1980, 600]
    app.note_trace_click(1600, 270 + 20 + 23)  # on Count
    app.trace_click["sent"] = True
    app._on_watch_read("traces", [line(n, 60, 20 + 23 * i) for i, n in enumerate(["Area", "Count", "Length", "Perimeter"])], None)
    assert app.cur["wrong"] == 1
