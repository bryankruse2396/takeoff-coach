"""The learner's own training projects, and which drawing a measurement is on."""
from coach.projects import drawing_codes, norm_name, on_drawings, open_project_name


def test_project_name_from_the_window_title():
    assert open_project_name("eTakeoff Dimension - Project: Takeoff Training Test - Mary Sue") == \
        "Takeoff Training Test - Mary Sue"
    assert open_project_name("eTakeoff Dimension") == ""


def test_names_compare_without_case_spaces_or_dash_style():
    assert norm_name("takeoff training test – john  doe") == norm_name("Takeoff Training Test - John Doe")
    assert norm_name("Takeoff Training Test - Jon Doe") != norm_name("Takeoff Training Test - John Doe")


def test_sheet_codes_match_whole_codes_only():
    codes = drawing_codes([{"dwg": "A1.1"}, {"dwg": None}, {}])
    assert codes == {"A1.1"}
    assert on_drawings({"dwg": "004 A1.1 1ST FLOOR PLAN"}, codes)
    assert not on_drawings({"dwg": "014 A1.10 DETAILS"}, codes)
    assert not on_drawings({"dwg": "005 A1.2 2ND FLOOR PLAN"}, codes)
