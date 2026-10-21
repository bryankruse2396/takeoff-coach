"""New versions install themselves, but never in the middle of a lesson or test."""
import unittest.mock as um


def test_updates_itself_when_idle(app):
    import coach.ui.start_screen as ss
    with um.patch.object(ss, "FROZEN", True), um.patch.object(type(app), "apply_update") as upd:
        app.step_i, app.test = -1, None
        app._update_found({"version": "9.9", "url": "x"})
        assert upd.call_count == 1
        app._update_found({"version": "9.9", "url": "x"})  # only tried once
        assert upd.call_count == 1


def test_waits_for_the_lesson_to_end(app):
    import coach.ui.start_screen as ss
    with um.patch.object(ss, "FROZEN", True), um.patch.object(type(app), "apply_update") as upd:
        app.step_i, app.test = 2, None
        app._update_found({"version": "9.9", "url": "x"})
        assert upd.call_count == 0
        app.step_i = -1
        app._auto_update()  # what go_home does once the lesson is over
        assert upd.call_count == 1


def test_never_during_a_test(app):
    import coach.ui.start_screen as ss
    with um.patch.object(ss, "FROZEN", True), um.patch.object(type(app), "apply_update") as upd:
        app.step_i, app.test = -1, {"session_id": "s"}
        app._auto_update()
        app.update_info = {"version": "9.9"}
        app._auto_update()
        assert upd.call_count == 0
