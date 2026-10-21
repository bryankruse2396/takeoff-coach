"""Lines that must use disconnected points (G or the Disconnected Point button)."""
from winstub import patch_all

STEP = {"id": "walls", "type": "measure", "kind": "length", "disconnected": True, "min_disconnects": 2,
        "min_points": 4, "dwg": "A1.1", "text": "x", "skill": "Disconnected points"}


def setup_step(c):
    from coach import lessons
    lessons.LESSON.clear()
    lessons.LESSON.update({"id": "t", "title": "T", "steps": [dict(STEP)]})
    c.step_i, c.step_i_locked, c.test = 0, -1, None
    c.cur = {"id": "walls", "wrong": 0, "failed": set(), "hints": 0, "clicks": 0}
    patch_all("pid_of", lambda h: 7)


def test_g_presses_are_counted_and_required(app):
    setup_step(app)
    assert "3 separate pieces" in app._disconnect_problem(STEP)
    app._disconnect_used("G key")
    assert app._disconnect_problem(STEP)  # one break isn't enough here
    app._disconnect_used("G key")
    assert app._disconnect_problem(STEP) is None


def test_the_ribbon_button_counts_too(app):
    setup_step(app)
    app.targets["disconnected"] = (850, 100, 1010, 125)
    patch_all("click_is_in_etakeoff", lambda x, y, h: True)
    app.last_click_t, app.last_click_xy = 0, (0, 0)
    app.on_click(900, 110)
    app.on_click(905, 112)
    assert app.cur["disconnects"] == 2 and app._disconnect_problem(STEP) is None


def test_a_miss_starts_the_count_over(app):
    setup_step(app)
    app._disconnect_used("G key")
    app._disconnect_used("G key")
    app._miss("try again")
    assert app.cur["disconnects"] == 0 and app._disconnect_problem(STEP)


def test_steps_without_disconnected_points_dont_care(app):
    setup_step(app)
    assert app._disconnect_problem({"id": "x", "kind": "length"}) is None
