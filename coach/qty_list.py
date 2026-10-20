"""Understanding the Quantity List as read off the screen."""
import difflib
import re


# "26.69 Length". Tolerates a stray border/swatch character in front ("| 26.69 Length").
NUM_ROW = re.compile(r"^[^\w\-.]*(?:[Il|!]\s+)?(-?[\d,]*\.?\d+)\s+([A-Za-z].*?)\s*$")
NUM_ONLY = re.compile(r"^[^\w\-.]*(-?[\d,]*\.?\d+)\W*$")


def merge_rows(lines):
    """OCR sometimes splits one Quantity List row into a number line and a label line ("610.70" + "Area").
    Join them back up when they sit on the same row."""
    lines = [dict(l) for l in lines]
    nums = [l for l in lines if NUM_ONLY.match(l["text"].strip())]
    used = set()
    for n in nums:
        hgt = max((wd["h"] for wd in n.get("words", [])), default=8)
        best = None
        for i, l in enumerate(lines):
            if i in used or l is n or NUM_ONLY.match(l["text"].strip()) or NUM_ROW.match(l["text"]):
                continue
            if abs(l["y"] - n["y"]) <= max(5, hgt * 0.7) and l["x"] > n["x"] and re.match(r"\s*[A-Za-z]", l["text"]):
                if best is None or l["x"] < lines[best]["x"]:
                    best = i
        if best is not None:
            used.add(best)
            n["text"] = NUM_ONLY.match(n["text"].strip()).group(1) + " " + lines[best]["text"].strip()
    return [l for i, l in enumerate(lines) if i not in used]


def count_rows(lines):
    return sum(1 for l in merge_rows(lines) if NUM_ROW.match(l["text"].replace(" .", ".").replace(". ", ".")))


DEFAULT_NAMES = {"area", "length", "perimeter", "count"}
TITLE_SKIP = re.compile(r"quantity\s*l[il1]st|^\W*\w{0,3}\s*l[il1]st\W*$|^\W*quant", re.I)


def read_title(strip, ocr):
    """Read the bold name line above the quantities. Windows OCR often skips a short bold word next to the
    coloured swatch, so try a few clean-ups: drop the swatch, then black-and-white, then larger."""
    from PIL import ImageOps
    base = strip.copy()
    px = base.load()
    for yy in range(base.height):
        for xx in range(base.width):
            r, g, b = px[xx, yy]
            if max(r, g, b) - min(r, g, b) > 18 or min(r, g, b) > 200:  # swatch, blue title bar, light fill -> white
                px[xx, yy] = (255, 255, 255)
    bw = ImageOps.grayscale(base).point(lambda v: 0 if v < 150 else 255).convert("RGB")
    for img, scale in ((base, 3), (bw, 3), (bw, 5), (base, 6), (bw, 7)):
        got = [l for l in ocr(img, 0, 0, scale) if l["text"].strip() and not TITLE_SKIP.search(l["text"])]
        if got:
            return got
    return []


QTY_LABELS = ["point count", "perimeter", "length", "area", "count"]


def canon_label(label):
    """Map an OCR'd label to eTakeoff's quantity name, forgiving small misreads ("Permeter", "Lenght")."""
    low = label.lower().strip()
    if low.startswith("group") or low.startswith("grp"):
        return "group " + canon_label(low.split(" ", 1)[1] if " " in low else "")
    if low.startswith(("poi", "pon", "pnt")) and "count" in low.replace("coun", "count"):
        return "point count"
    for k in QTY_LABELS:
        if k in low:
            return k
    m = difflib.get_close_matches(low, QTY_LABELS, n=1, cutoff=0.7)
    return m[0] if m else low


def parse_qty_list(lines, w, h, rgb):
    """Turn OCR lines of the Quantity List into {header, values{label: number}, primary}.
    The primary quantity is the row eTakeoff shades blue."""
    header, rows = None, []
    for ln in sorted(merge_rows(lines), key=lambda d: d["y"]):
        if TITLE_SKIP.search(ln["text"]):
            continue  # the blue "Quantity List" bar, if it was included when recording
        m = NUM_ROW.match(ln["text"].replace(" .", ".").replace(". ", "."))
        if m:
            try:
                rows.append((float(m.group(1).replace(",", "")), m.group(2).strip(), ln["y"]))
            except ValueError:
                pass
        elif header is None and not rows:
            header = ln["text"].strip()
    if not rows:
        return None
    values, primary, best = {}, None, 0
    for val, label, y in rows:
        key = canon_label(label)
        values.setdefault(key, val)
        yy = min(h - 1, max(0, int(y)))
        blue = 0
        for x in (3, 8, max(9, w // 4)):
            if x < w:
                i = (yy * w + x) * 3
                r, b = rgb[i], rgb[i + 2]
                blue = max(blue, b - r)
        if blue > best:
            best, primary = blue, key
    if best < 18:
        primary = None
    return {"header": header or "", "values": values, "primary": primary,
            "sig": (header or "", tuple(sorted((k, round(v, 2)) for k, v in values.items())))}


def screen_rec(parsed):
    """A measurement record built from the Quantity List (same shape as the eTakeoff-data records)."""
    v = parsed["values"]
    p = parsed["primary"]
    return {"guid": None, "desc": parsed["header"], "trace": parsed["header"],
            "qty": v.get(p) if p in ("area", "length", "perimeter", "count") else None, "uom": "",
            "area": v.get("area", 0.0), "length": v.get("length", 0.0), "perim": v.get("perimeter", 0.0),
            "points": int(v["point count"]) if "point count" in v else None, "dwg": None,
            "has": set(v), "primary": p}
