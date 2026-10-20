"""Comparing text read off the screen, forgiving typical OCR misreads."""
import re


def ocr_fold(t):
    """Fold the letter shapes screen reading mixes up in eTakeoff's bold font, so 'Wall' read as 'Wan',
    'Wa1l' or 'WaII' still matches: i/1/|/! look like l, 'll' can read as 'n', 'rn' as 'm', 0 as o."""
    t = " ".join(re.sub(r"[^a-z0-9|!]+", " ", (t or "").lower()).split())
    t = re.sub(r"[i1|!]", "l", t).replace("rn", "m").replace("0", "o")
    return t.replace("ll", "n")


def same_text(a, b):
    """Typed descriptions read back by OCR: ignore case, spacing and punctuation, allow for the font's
    look-alike letters, and forgive one stray misread letter in longer text."""
    na, nb = ocr_fold(a), ocr_fold(b)
    return na == nb or (len(nb) > 5 and edit_distance(na, nb) <= 1)


def edit_distance(a, b):
    """Letters added, removed or changed to turn a into b."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def exact_text(a, b):
    """Descriptions read straight from eTakeoff's data: exact apart from case and spacing."""
    return " ".join((a or "").lower().split()) == " ".join((b or "").lower().split())
