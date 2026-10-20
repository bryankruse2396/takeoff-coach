"""Reading measurements from eTakeoff through its COM interface (read-only: the coach never changes a project)."""
import ctypes
import struct
import time

from coach.log import dlog


TLB = r"C:\Program Files (x86)\eTakeoff\RView\ETkoInfc64.tlb" if struct.calcsize("P") == 8 \
    else r"C:\Program Files (x86)\eTakeoff\RView\ETkoInfc.tlb"


def bstr_call(fn, *args):
    from comtypes import BSTR
    for t in (args, tuple(BSTR(a) if isinstance(a, str) else a for a in args),
              tuple(ctypes.byref(BSTR(a)) if isinstance(a, str) else a for a in args)):
        try:
            return fn(*t)
        except (TypeError, ctypes.ArgumentError):
            continue
    return fn(*args)


class Watcher:
    """Reads the project's measurements and reports confirmed NEW / CHANGED / DELETED rows.
    eTakeoff briefly drops rows while it saves, so a change must hold for 2 reads,
    and a deletion is confirmed by re-reading the measurement by its ID."""

    def __init__(self):
        import comtypes.client
        mod = comtypes.client.GetModule(TLB)
        self.o = comtypes.client.CreateObject(mod.ETkoObject, interface=mod.IETkoObjectDual)
        self.proj = None
        self.state, self.pending, self.missing = {}, {}, {}
        self.baseline_guids = set()

    def _g(self, name, *a):
        try:
            return getattr(self.o, name)(*a)
        except Exception:
            return None

    def projects(self):
        parts = str(self._g("ProjGuidDescGet") or "").split(";")
        return [(parts[i], parts[i + 1]) for i in range(0, len(parts) - 1, 2) if parts[i]]

    def bind_to_window_title(self, title):
        name = title.split("Project:", 1)[1].strip() if "Project:" in title else ""
        for gid, n in self.projects():
            if n == name:
                self.proj = gid
                return n
        return None

    def _rec(self):
        guid = self._g("GuidQtyGet")
        if not guid:
            return None
        return {"guid": guid, "desc": self._g("DescGet") or "", "trace": self._g("TraceDescGet") or "",
                "qty": self._g("DfltQtyGet") or 0.0, "uom": self._g("UomNameGet") or "",
                "area": self._g("AreaGet") or 0.0, "length": self._g("LengthGet") or 0.0,
                "perim": self._g("PerimeterGet") or 0.0, "points": self._g("CountGet") or 0,
                "dwg": self._g("DwgDescGet") or ""}

    def read_all(self):
        n = int(bstr_call(self.o.UnusedTkoScan, self.proj, "", "") or 0)
        rows = {}
        for i in range(n):
            bstr_call(self.o.UnusedTkoLoad, i)
            rec = self._rec()
            if rec:
                rows[(rec["guid"], rec["trace"])] = rec
        return rows

    def from_clipboard(self):
        """The measurement the learner copied (right-click > Copy Measurement). Comes straight from eTakeoff, no delay."""
        try:
            if not self.o.LoadFromClip():
                return None
        except Exception:
            return None
        return self._rec()

    def start_baseline(self):
        merged = {}
        for _ in range(12):  # eTakeoff sometimes leaves rows out of a single read
            merged.update(self.read_all())
            time.sleep(0.2)
        self.state = merged
        self.baseline_guids = {k[0] for k in merged}
        self.pending, self.missing = {}, {}
        self.last_raw = set(merged)
        dlog(f"baseline: {len(merged)} rows")

    def poll(self):
        raw = self.read_all()
        added, removed = set(raw) - self.last_raw, self.last_raw - set(raw)
        if added or removed:
            dlog(f"raw read: +{[(raw[k]['trace'], round(raw[k]['qty'], 2)) for k in added]} "
                 f"-{[k[1] for k in removed]} (total {len(raw)})")
        self.last_raw = set(raw)
        events = []
        for k, rec in raw.items():
            self.missing.pop(k, None)
            if self.state.get(k) == rec:
                self.pending.pop(k, None)
                continue
            p = self.pending.get(k)
            if p and p[0] == rec:
                kind = "CHANGED" if k in self.state else "NEW"
                events.append((kind, rec, self.state.get(k)))
                self.state[k] = rec
                self.pending.pop(k, None)
            else:
                self.pending[k] = (rec, 1)
        for k in list(self.state):
            if k in raw:
                continue
            self.missing[k] = self.missing.get(k, 0) + 1
            if self.missing[k] >= 3:
                still = bstr_call(self.o.LoadFromGuid, k[0])
                if not still:
                    events.append(("DELETED", self.state[k], None))
                    self.state.pop(k)
                self.missing.pop(k, None)
        for kind, rec, _ in events:
            dlog(f"event {kind}: {rec['trace']!r} {rec['desc']!r} qty {rec['qty']:.2f} pts {rec['points']} {rec['dwg']}")
        return events
