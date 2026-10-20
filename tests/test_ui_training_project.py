"""Practice and tests only run in the learner's own projects, and tests start on clean drawings."""
import time

from conftest import buttons, press

STEPS = [{"id": "a", "type": "measure", "kind": "area", "dwg": "A1.1", "text": "x", "skill": "s", "page": 1}]


def wait_for_watch(c, seconds=2.3):
    end = time.time() + seconds
    while time.time() < end:
        c.root.update()
        time.sleep(0.05)


def status(c):
    return c.status.cget("text")


def test_project_names_follow_the_learner(app):
    assert app.training_project() == "Takeoff Training Practice - John Doe"
    assert app.training_project(True) == "Takeoff Training Test - John Doe"


def test_first_practice_walks_through_setup(app):
    started = []
    app._show_start()
    app.preflight(lambda: started.append("practice"), steps=STEPS)
    app.root.update()
    assert app.h1.cget("text") == "Set up your practice project" and not started
    # a typo in the name is pointed out
    app.et.title = "eTakeoff Dimension - Project: Takeoff Training Practice - Jon Doe"
    wait_for_watch(app)
    assert "should be exactly" in status(app)
    # fixed (case and dash style don't matter): practice starts
    app.et.title = "eTakeoff Dimension - Project: takeoff training practice – john doe"
    wait_for_watch(app, 4.0)
    assert started == ["practice"]


def test_wrong_project_open_asks_for_the_right_one(app):
    app.et.projects.append(("g2", "Takeoff Training Practice - John Doe"))
    app.et.title = "eTakeoff Dimension - Project: Takeoff Training Test - John Doe"
    started = []
    app._show_start()
    app.preflight(lambda: started.append("p"), steps=STEPS)
    app.root.update()
    assert "Takeoff Training Practice - John Doe" in status(app) and not started


def test_test_needs_a_clean_drawing(app):
    app.et.title = "eTakeoff Dimension - Project: Takeoff Training Test - John Doe"
    app.et.rows.update({("m1", "Area"): {"dwg": "004 A1.1 1ST FLOOR PLAN"},
                        ("m2", "Length"): {"dwg": "004 A1.1 1ST FLOOR PLAN"},
                        ("m3", "Length"): {"dwg": "005 A1.2 2ND FLOOR PLAN"},
                        ("m4", "Area"): {"dwg": "014 A1.10 DETAILS"}})
    started = []
    app._show_start()
    app.preflight(lambda: started.append("test"), test=True, steps=STEPS)
    app.root.update()
    assert app.h1.cget("text") == "Clear the drawing first" and "2 measurements" in app.sub.cget("text")
    assert "Start anyway" not in buttons(app.body)
    for k in [k for k, v in app.et.rows.items() if "A1.1 " in v["dwg"]]:
        app.et.rows.pop(k)
    press(app.body, "Check again")
    assert started == ["test"]


def test_practice_can_start_anyway(app):
    app.et.title = "eTakeoff Dimension - Project: Takeoff Training Practice - John Doe"
    app.et.rows[("m5", "Area")] = {"dwg": "004 A1.1 1ST FLOOR PLAN"}
    started = []
    app._show_start()
    app.preflight(lambda: started.append("p"), steps=STEPS)
    app.root.update()
    assert app.h1.cget("text") == "Start on a clean drawing?"
    press(app.body, "Start anyway")
    assert started == ["p"]


def test_not_signed_in(app):
    app.cloud.account = {}
    app.learner.set("")
    started = []
    app._show_start()
    app.preflight(lambda: started.append("x"), steps=STEPS)
    app.root.update()
    assert "Sign in first" in status(app) and not started
