"""Finding eTakeoff's buttons and panes in a screenshot."""
import difflib
import re

from coach.log import dlog


def fit_button(tb, rgb, W, H):
    """If this ribbon button is already lit up (the active tool is orange), return the lit rectangle.
    tb is the label's text box. Returns [x1, y1, x2, y2] or None."""
    tx1, ty1, tx2, ty2 = [int(round(v)) for v in tb]
    hh = max(8, ty2 - ty1)
    if tx1 - 2 * hh < 0 or tx2 + 4 >= W or ty1 - hh < 0 or ty2 + hh >= H:
        return None
    px = lambda x, y: rgb[(y * W + x) * 3:(y * W + x) * 3 + 3]
    cy = (ty1 + ty2) // 2

    # 1) A highlighted button (Select's orange) is a solid coloured block: take the block.
    hl = px(tx1 - 2, cy)
    sat = lambda c: max(c) - min(c) > 60
    close = lambda x, y: 0 <= x < W and max(abs(a - b) for a, b in zip(px(x, y), hl)) < 70
    # the lit block must show on both sides of the label (OCR sometimes clips the last letter, so look a bit right)
    if sat(hl) and any(close(x, cy) for x in range(tx2 + 1, min(W, tx2 + hh))):
        x1 = tx1 - 2
        while x1 > tx1 - 4 * hh and any(close(x1 - k, cy) for k in range(1, hh)):
            x1 -= 1
        x2 = tx2
        while x2 < tx2 + 2 * hh and any(close(x2 + k, cy) for k in range(1, max(4, hh // 2))):
            x2 += 1
        y1 = cy
        while y1 > ty1 - hh and close(tx1 - 2, y1 - 1):
            y1 -= 1
        y2 = cy
        while y2 < ty2 + hh and close(tx1 - 2, y2 + 1):
            y2 += 1
        # the icon left of the label isn't orange, so the walk above stops at it; the button includes it
        x1 = min(x1, int(tx1 - 1.9 * hh))
        return [x1 - 1, y1 - 1, x2 + 1, y2 + 1]

    return None  # not lit up; the outline comes from hovering instead


def locate_targets(lines, W, H, rgb=None):
    """Find the ribbon buttons and the Quantity List pane from OCR of the whole eTakeoff window.
    Returns {name: [x1, y1, x2, y2]} relative to the window, like recorded positions."""
    words = [dict(wd) for ln in lines for wd in ln.get("words", [])]
    norm = lambda t: re.sub(r"[^a-z]", "", t.lower())
    found = {}

    btn_labels = {}

    def box(ws, key=None):
        x1 = min(v["x"] for v in ws); y1 = min(v["y"] for v in ws)
        x2 = max(v["x"] + v["w"] for v in ws); y2 = max(v["y"] + v["h"] for v in ws)
        hh = max(8, y2 - y1)
        if key:
            btn_labels[key] = [int(x1), int(y1), int(x2), int(y2)]
        if rgb and len(rgb) >= W * H * 3:
            try:
                fit = fit_button((x1, y1, x2, y2), rgb, W, H)  # an already-lit (orange) button
                if fit:
                    return fit
            except Exception as e:
                dlog(f"fit_button failed: {e!r}")
        # estimate: icon left of the label, button about two text-heights tall (refined by hovering later)
        cy = (y1 + y2) / 2
        return [int(x1 - 1.9 * hh), int(cy - 0.95 * hh), int(x2 + 0.5 * hh), int(cy + 0.95 * hh)]

    # The ribbon ends at its group labels ("Takeoff", "Navigation"...).
    labels = [v for v in words if norm(v["text"]) in ("takeoff", "navigation", "project") and v["y"] < H * 0.35]
    ribbon_bottom = max(v["y"] + v["h"] for v in labels) + 4 if labels else H * 0.2
    rib = [v for v in words if v["y"] + v["h"] <= ribbon_bottom + 2]
    used = []
    for v in rib:
        n = norm(v["text"])
        if n.startswith("multi"):
            ws = [v]
            if "select" not in n:
                ws += [u for u in rib if u is not v and abs(u["y"] - v["y"]) < v["h"] * 0.7
                       and -2 <= u["x"] - (v["x"] + v["w"]) < v["h"] * 2.5 and norm(u["text"]).startswith("select")][:1]
            found["multiselect"] = box(ws, "multiselect")
            used += ws
            break
    for v in rib:
        if norm(v["text"]).startswith("disconn"):
            ws = [v] + [u for u in rib if u is not v and abs(u["y"] - v["y"]) < v["h"] * 0.7
                        and -2 <= u["x"] - (v["x"] + v["w"]) < v["h"] * 2.5 and norm(u["text"]).startswith("point")][:1]
            found["disconnected"] = box(ws, "disconnected")
            used += ws
            break
    close = lambda a, b: a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75  # forgive "5elect", "Lenght"
    for key in ("select", "area", "count", "length", "perimeter"):
        cands = [v for v in rib if close(norm(v["text"]), key) and all(v is not u for u in used)]
        if cands:
            found[key] = box([min(cands, key=lambda v: v["x"])], key)
    # Trace names in the Traces control panel (Area, Count, Length, Perimeter rows under the "Traces" title)
    titles = [ln for ln in lines if norm(ln["text"]) == "traces" and ln["y"] > ribbon_bottom]
    if titles:
        tt = min(titles, key=lambda l: l["y"])
        th = max((v["h"] for v in tt.get("words", [])), default=14)
        nxt = [ln for ln in lines if PANE_TITLES.search(ln["text"]) and ln["y"] > tt["y"] + th
               and abs(ln["x"] - tt["x"]) < 3 * th and norm(ln["text"]) != "traces"]
        tbot = min((ln["y"] for ln in nxt), default=H)
        right = None
        if rgb and len(rgb) >= W * H * 3:
            right = pane_right_edge(rgb, W, H, int(tt["x"] + th), int(tt["y"] + 1.8 * th), int(min(tbot, H - 2) - th))
        order = ("area", "count", "length", "perimeter")  # eTakeoff lists the basic traces in this order
        row_at = {}
        for key in order:
            hits = [wd for ln in lines if tt["y"] < ln["y"] < tbot and -th < ln["x"] - tt["x"] < 8 * th
                    and len(ln.get("words", [])) <= 2 for wd in ln.get("words", []) if close(norm(wd["text"]), key)]
            if hits:
                wd = min(hits, key=lambda v: v["y"])
                row_at[key] = (wd["y"] + wd["h"] / 2, wd["h"])
        if len(row_at) >= 2:
            # rows OCR missed (the swatch beside a name can hide it) sit at the same spacing as the ones it read
            (ka, (ya, ha)), (kb, (yb, _)) = sorted(row_at.items(), key=lambda kv: order.index(kv[0]))[:2]
            pitch = (yb - ya) / (order.index(kb) - order.index(ka))
            if 0.9 * ha < pitch < 3 * ha:
                for key in order:
                    row_at.setdefault(key, (ya + (order.index(key) - order.index(ka)) * pitch, ha))
        for key, (cy, hh) in row_at.items():
            if cy < tbot:
                found["trace_" + key] = [int(max(0, tt["x"] - th)), int(cy - 0.95 * hh),
                                         int(right if right else tt["x"] + 12 * th), int(cy + 0.95 * hh)]
    # Select sits on its orange highlight and OCR sometimes can't read it. It is the button
    # directly above Multi-Select, one ribbon row up (the same spacing as Area -> Count).
    if "select" not in found and "multiselect" in found:
        mx1, my1, mx2, my2 = found["multiselect"]
        row = (found["count"][1] - found["area"][1]) if "area" in found and "count" in found else (my2 - my1) * 1.25
        found["select"] = [mx1, int(my1 - row), int(mx1 + (mx2 - mx1) * 0.62), int(my2 - row)]

    # Quantity List pane: from its title bar down to the "Measurement Summary" title.
    ql = [v for ln in lines if re.search(r"quantity\s*l[il1]st", ln["text"], re.I) for v in ln.get("words", [])[:1]]
    if ql:
        q = min(ql, key=lambda v: v["y"])
        # The pane ends at the next pane's title in the same column (whichever panel it is docked in).
        below = [v for ln in lines if PANE_TITLES.search(ln["text"])
                 for v in ln.get("words", [])[:1] if v["y"] > q["y"] + q["h"] and abs(v["x"] - q["x"]) < 3 * q["h"]]
        bottom = min(below, key=lambda v: v["y"])["y"] - q["h"] * 0.6 if below else H - 2.5 * q["h"]
        right = None
        if rgb and len(rgb) >= W * H * 3:
            right = pane_right_edge(rgb, W, H, int(q["x"] + q["h"]), int(q["y"] + 1.8 * q["h"]), int(bottom))
        if right is None:
            sync = [v for v in words if norm(v["text"]) == "sync" and v["y"] > q["y"]]
            right = (min(sync, key=lambda v: v["y"])["x"] + min(sync, key=lambda v: v["y"])["w"] + 3 * q["h"]
                     if sync else q["x"] + W * 0.21)
        # start just below the blue "Quantity List" title bar so the bar's text isn't mistaken for the measurement name
        found["qtylist"] = [int(max(0, q["x"] - q["h"])), int(q["y"] + 1.5 * q["h"]), int(min(W, right)), int(bottom)]
    found["_labels"] = btn_labels
    return found


PANE_TITLES = re.compile(r"^\W*(quantity\s*l[il1]st|measurement\s*summ|measurement\s*ed|traces\b|drawing\s*tree|favou?rites|"
                         r"work\s*break|control\s*panel|layers\b|bookmarks\b|properties\b|planroom|notes\b)", re.I)


def pane_right_edge(rgb, W, H, x0, y0, y1):
    """Walk right from inside the pane until a mostly-dark column (the pane border or splitter)."""
    if y1 - y0 < 10:
        return None
    ys = range(y0, y1, 3)
    for x in range(x0, W):
        dark = 0
        for y in ys:
            i = (y * W + x) * 3
            if min(rgb[i], rgb[i + 1], rgb[i + 2]) < 175:
                dark += 1
        if dark > 0.6 * len(ys):
            return x - 1
    return W - 1
