"""Comparing what the learner typed (read back off the screen) with what the lesson asks for."""
from coach.textmatch import exact_text, ocr_fold, same_text


def test_ocr_misreads_are_forgiven():
    # Windows OCR read "Wall Segment" as "Wan Segment" (ll -> n)
    assert same_text("Wan Segment", "Wall Segment")
    assert ocr_fold("Wa1l") == ocr_fold("Wall")


def test_case_and_spacing_dont_matter():
    assert same_text("laundry  room area", "Laundry Room Area")


def test_a_different_word_is_not_accepted():
    assert not same_text("Electrical Rm", "Electrical Room")
    assert not same_text("Break Room", "Laundry Room")


def test_exact_text():
    assert exact_text("Wall Segment", "wall segment")
    assert not exact_text("Wan Segment", "Wall Segment")
