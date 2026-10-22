"""Checking what the learner did: clicks, finished measurements, descriptions, eTakeoff's own data."""
import time

from coach import lessons
from coach.builtin_lessons import RIBBON, TARGETS
from coach.grading import evaluate, measured, points_matter
from coach.log import dlog
from coach.qty_list import DEFAULT_NAMES, screen_rec
from coach.textmatch import exact_text, same_text
from coach.winapi import click_is_in_etakeoff, find_etakeoff, pid_of, user32, win_rect


class Checking:
    """Part of the Coach window (see coach/app.py)."""

    def on_click(self, x, y):
        if self.step_i < 0 or self.step_i >= len(lessons.LESSON["steps"]) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        if lessons.LESSON["steps"][self.step_i]["type"] == "info":
            return  # an intro or recap screen: nothing to check
        px, py, pw, ph = self.root.winfo_rootx(), self.root.winfo_rooty(), self.root.winfo_width(), self.root.winfo_height()
        if px <= x <= px + pw and py <= y <= py + ph:
            return  # click on the coach panel
        h, _ = find_etakeoff()
        if not h:
            return
        if not click_is_in_etakeoff(x, y, h):
            return  # another program, even one sitting on top of eTakeoff
        l, t, r, b = win_rect(h)
        dlog(f"click at window offset ({x - l},{y - t})")
        now = time.time()
        if now - self.last_click_t < 0.45 and abs(x - self.last_click_xy[0]) < 6 and abs(y - self.last_click_xy[1]) < 6:
            pass  # a double-click finishes drawing in eTakeoff; grading still waits for Enter
        self.last_click_t, self.last_click_xy = now, (x, y)
        s = lessons.LESSON["steps"][self.step_i]
        self.cur["clicks"] += 1
        inside = lambda k: k in self.targets and (lambda b: l + b[0] - 3 <= x <= l + b[2] + 3 and
                                                                t + b[1] - 3 <= y <= t + b[3] + 3)(self.targets[k])
        if s["type"] == "measure" and inside("disconnected"):
            return self._disconnect_used("Disconnected Point button")
        if s["type"] != "click":
            return
        if inside(s["target"]):
            self._pass("")
        elif any(inside(k) for k in s.get("also", [])):
            alt = next(k for k in s.get("also", []) if inside(k))
            self._pass(f"That works too. This lesson uses {TARGETS[s['target']]}; {TARGETS[alt]} does the same thing.")
        else:
            # Clicks on the drawing or side panels are navigation (zoom, pan, select), not wrong answers.
            # A wrong button is a click up in the ribbon band, or on another button the coach knows about.
            ribbon_bottom = max((v[3] for k, v in self.targets.items() if k in RIBBON), default=150) + 40
            ribbon_top = min((v[1] for k, v in self.targets.items() if k in RIBBON), default=60) - 12
            in_band = ribbon_top <= y - t <= ribbon_bottom  # not the title bar or the tabs (window buttons, Home...)
            if not in_band and not any(inside(k) for k in TARGETS):
                return
            self.cur["wrong"] += 1
            self._render_step("Not quite. Try again." if self.test else
                              f"Not quite. That wasn't {TARGETS[s['target']]}. Try again.", ok=False)

    def _disconnect_used(self, how):
        """The learner started a new piece of the same measurement (G or the Disconnected Point button)."""
        if not (0 <= self.step_i < len(lessons.LESSON["steps"])) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        s = lessons.LESSON["steps"][self.step_i]
        if s["type"] != "measure":
            return
        h, _ = find_etakeoff()
        if how == "G key" and not (h and pid_of(user32.GetForegroundWindow()) == pid_of(h)):
            return  # G typed somewhere else
        self.cur["disconnects"] = self.cur.get("disconnects", 0) + 1
        dlog(f"disconnected point #{self.cur['disconnects']} ({how})")

    def _disconnect_problem(self, s, rec=None):
        """For steps that must use disconnected points: a message if the learner didn't, else None.
        Proof is eTakeoff's own "Group ..." row in the Quantity List, or the G presses / Disconnected Point
        clicks the coach saw while the step was drawn."""
        need = s.get("min_disconnects", 1 if s.get("disconnected") else 0)
        if need == 0 or (rec and rec.get("groups")) or self.cur.get("disconnects", 0) >= need:
            return None
        return (f"This needs to be one measurement made of {need + 1} groups, and the coach doesn't see the groups. At the "
                "end of each piece (at a door opening), press G or click Disconnected Point, then start the next group "
                "on the other side. Delete this line and try again.")

    def check_now(self):
        """Re-read the Quantity List now (and the clipboard, if a measurement was copied)."""
        h, _ = find_etakeoff()
        if not h:
            return self._render_step("eTakeoff isn't open.", ok=False)
        dlog("Check button")
        self.check_src = "button"
        s = lessons.LESSON["steps"][self.step_i] if 0 <= self.step_i < len(lessons.LESSON["steps"]) else None
        if s and s["type"] == "click" and getattr(self, "step_i_locked", -1) != self.step_i:
            lit = [k for k in [s["target"]] + list(s.get("also", [])) if k in RIBBON and self.button_active(k)]
            if lit:
                dlog(f"click step {s['id']}: {lit[0]} is lit")
                return self._pass(f"{TARGETS[lit[0]].split(' (')[0]} is active.")
        self.finish_at = time.time()

    def defer(self):
        """Move on now; grade this step when eTakeoff publishes the measurement (after the next one is drawn)."""
        dlog(f"step {self.cur['id']} deferred")
        self._close_step("pending", 0, "waiting for eTakeoff to publish the measurement")

    def _read_after_check(self):
        self.clip_seq = user32.GetClipboardSequenceNumber()  # handled here, not again in tick
        rec = self.watcher.from_clipboard()
        dlog("after Check: " + (f"{rec['trace']!r} {rec['desc']!r} qty {rec['qty']:.2f} pts {rec['points']}"
                                if rec else "no eTakeoff measurement on the clipboard"))
        self.on_clipboard(rec)

    def on_clipboard(self, rec):
        """The learner copied a measurement (right-click > Copy Measurement). rec is it, or None if no measurement was copied.
        (Reading the whole project lags: eTakeoff only publishes a measurement after the next one is started,
        so grading uses the copied measurement, which comes straight from eTakeoff's memory.)"""
        if self.step_i < 0 or self.step_i >= len(lessons.LESSON["steps"]) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        s = lessons.LESSON["steps"][self.step_i]
        if s["type"] == "click":
            return
        if rec is None:
            return self._render_step("There's no measurement on the clipboard yet. Right-click your measurement on the "
                                     "drawing and choose Copy Measurement, then any Copy Total option.", ok=False)
        graded = getattr(self, "graded", {})
        if rec["guid"] in self.watcher.baseline_guids:
            return self._render_step("That measurement was there before this lesson. Copy the one you just drew.", ok=False)
        if s["type"] == "describe":
            return self._grade_description(s, rec["desc"] if rec["desc"] != rec["trace"] else "",
                                           {"area": rec.get("area"), "length": rec.get("length"),
                                            "perimeter": rec.get("perim")}, True)
        if rec["guid"] in graded and graded[rec["guid"]] not in (s["id"], s.get("continues")):
            return self._render_step("That's the measurement from an earlier step. Draw a new one for this step.", ok=False)
        if self.instructor.get():
            free = {k: v for k, v in s.items() if k not in ("expected", "points", "known")}
            ok, msg, _ = evaluate(free, rec)
            if ok:
                val = measured(rec, s["kind"])
                if "expected" in s:
                    self.answers[s["id"]] = {"expected": round(val, 2), "points": rec["points"]}
                    self.save_answers()
                    msg = f"Saved {val:,.2f} with {rec['points']} points as the answer key."
                graded[rec["guid"]] = s["id"]
                self.graded = graded
                return self._pass(msg, partial=(ok == "partial"))
            return self._render_step(msg, ok=False)
        ok, msg, skill = evaluate(s, rec)
        if ok and self._disconnect_problem(s, rec):
            ok, msg, skill = False, self._disconnect_problem(s, rec), "Disconnected points"
        dlog(f"grade {s['id']}: {ok} {msg}")
        graded[rec["guid"]] = s["id"]
        self.graded = graded
        if ok:
            self.last_guid = rec["guid"]
            return self._pass(msg, partial=(ok == "partial"))
        self.cur["failed"].add(rec["guid"] + f"@{len(self.cur['failed'])}")
        self.cur.setdefault("missed_skills", []).append(skill)
        self._miss(msg)

    def on_qtylist(self, parsed, forced=False, quiet=99.0):
        """A finished measurement read off the Quantity List. Grades the current step instantly.
        Returns 'wait' when a miss might just be a measurement still being drawn (checked again shortly)."""
        if self.step_i < 0 or self.step_i >= len(lessons.LESSON["steps"]) or getattr(self, "step_i_locked", -1) == self.step_i:
            return
        if lessons.LESSON["steps"][self.step_i]["type"] == "info":
            return  # an intro or recap screen: nothing to check
        s = lessons.LESSON["steps"][self.step_i]
        if s["type"] == "click" and parsed:
            # Picking a trace (Traces panel or ribbon) shows that trace, still empty, in the Quantity List.
            # That proves the right trace is active even if the coach couldn't outline the button.
            want = s["target"].replace("trace_", "")
            if want in ("area", "length", "perimeter", "count") and parsed["primary"] in (want, "point count" if want == "count" else want) \
                    and all(abs(v) < 0.005 for v in parsed["values"].values()) and (forced or parsed["sig"] != self.qty_at_start):
                dlog(f"click step {s['id']}: Quantity List shows an empty {want} trace")
                return self._pass(f"{want.title()} trace is active.")
            if forced:
                dlog(f"click step {s['id']}: checked, not active yet ({parsed['primary']} {parsed['values']})")
                self._render_step(f"The coach doesn't see {TARGETS[s['target']]} selected yet. Click it, then "
                                  f"Check again.", ok=False)
            return
        if not parsed:
            return
        if s["type"] == "describe":
            return self._grade_description(s, parsed["header"], parsed["values"], forced)
        if parsed["sig"] == self.qty_at_start and not forced:
            return  # still showing whatever was selected when the step began
        dlog(f"check for step {s['id']}: '{parsed['header']}' {parsed['values']} main={parsed['primary']}")
        if s["type"] == "measure" and parsed["sig"][1] in self.passed_vals:
            dlog("  ignored: same numbers as a measurement that passed an earlier step")
            return  # a measurement that already passed an earlier step
        rec = screen_rec(parsed)
        # Is it a measurement that existed before this step? (published ones are known exactly)
        # Steps that continue an earlier step's measurement (adding a cutout) expect exactly that.
        for old in ([] if s.get("continues") else self.watcher.state.values()):
            if old["guid"] in self.step_known and any(
                    k in rec["has"] and abs(old[f] - parsed["values"][k]) < 0.006
                    for k, f in (("area", "area"), ("length", "length"), ("perimeter", "perim"))
                    if parsed["values"].get(k)):
                if s["type"] == "describe" and parsed["header"].lower() not in DEFAULT_NAMES and old["guid"] not in self.watcher.baseline_guids:
                    return self._pass(f"Named it \"{parsed['header']}\".")
                dlog(f"  ignored: matches an existing measurement ({old['trace']} {old['desc']})")
                return self._render_step("That's a measurement that was already there. Draw a new one for this step.", ok=False)
        if s["type"] == "describe":
            if parsed["header"] and parsed["header"].lower() not in DEFAULT_NAMES:
                return self._pass(f"Named it \"{parsed['header']}\".")
            if forced:
                self._render_step("The Quantity List still shows the default name. Right-click the line, choose Edit "
                                  "Measurement Description, type a name and press Enter.", ok=False)
            return
        kind = s["kind"]
        if kind not in rec["has"]:
            if rec["primary"] in ("area", "length", "perimeter", "count"):
                msg = (f"That measurement is a {rec['primary']} measurement. This step needs a {kind}: "
                       f"use the {kind.title()} button or double-click '{kind.title()}' in the Traces list.")
                if not forced and quiet < 4:
                    return "wait"
                return self._screen_fail(parsed, msg, "Choosing the right trace")
            dlog(f"  no {kind} row in this reading")
            if forced:
                self._render_step(f"The coach can't see a {kind.title()} row in the Quantity List. Click your "
                                  f"measurement so it's selected, then click Check again.", ok=False)
            return
        if self.instructor.get():
            free = {k: v for k, v in s.items() if k not in ("expected", "points", "known")}
            ok, msg, _ = evaluate(free, rec)
            if ok and "expected" in s:
                val = measured(rec, kind)
                entry = {"expected": round(val, 2)}
                if rec["points"]:
                    entry["points"] = rec["points"]
                self.answers[s["id"]] = entry
                self.save_answers()
                msg = f"Saved {val:,.2f} as the answer key."
            if ok:
                self.cur["graded_val"] = (kind, measured(rec, kind))
                self.passed_vals.add(parsed["sig"][1])
                self.cur["_passed_sig"] = parsed["sig"][1]
                return self._pass(msg, partial=(ok == "partial"))
            if not forced and quiet < 4:
                return "wait"
            return self._screen_fail(parsed, msg, None)
        ok, msg, skill = evaluate(s, rec)
        if ok and self._disconnect_problem(s, rec):
            ok, msg, skill = False, self._disconnect_problem(s, rec), "Disconnected points"
        dlog(f"grade {s['id']} from screen: {ok} {msg}")
        if not ok and skill == "Choosing the right trace":
            # Which line of the Quantity List is the main quantity is read from its shading, which can be misread.
            # eTakeoff's own data knows the trace for sure: use it when it has the measurement.
            exact = self._exact_record(parsed)
            if exact:
                ok, msg, skill = evaluate(s, exact)
                dlog(f"  re-graded from eTakeoff data ({exact['trace']} {exact['qty']:.2f} {exact.get('uom')}): {ok} {msg}")
            elif not parsed["header"] or kind in rec["has"]:
                # Not sure, and the reading does include the quantity asked for: don't count a miss on a guess.
                dlog("  trace unclear from the screen and eTakeoff hasn't published it yet: not graded")
                if forced:
                    self._render_step("The coach couldn't tell which trace that measurement used yet. Click your "
                                      "measurement once, wait a second, then click Check again.", ok=False)
                return "wait" if not forced else None
        if ok:
            self.cur["graded_val"] = (kind, measured(rec, kind))
            self.passed_vals.add(parsed["sig"][1])
            self.cur["_passed_sig"] = parsed["sig"][1]
            return self._pass(msg, partial=(ok == "partial"))
        if not forced and quiet < 4:
            return "wait"  # they may still be clicking corners; look again shortly
        self._screen_fail(parsed, msg, skill)

    def _grade_description(self, s, name, values, forced):
        """Describe step: the measurement from step s["of"] must carry exactly the description the lesson asks for."""
        want = s.get("answer")
        name = (name or "").strip()
        of = s.get("of", "len")
        drew = next((r.get("graded_val") for r in self.results if r.get("id") == of and r.get("graded_val")), None)
        values = values or {}
        if drew and drew[0] == "count" and "count" not in values:
            values = {**values, "count": values.get("point count")}  # the Quantity List may say Point Count
        have = values.get(drew[0]) if drew else None
        if forced:
            dlog(f"check for step {s['id']}: name '{name}' values {values} (want '{want}' on {of} = {drew})")
        if drew and (have is None or abs(have - drew[1]) > 0.02):
            if forced:
                unit = {"area": "SF", "count": "EA"}.get(drew[0], "LF")
                self._render_step(f"That's a different measurement. Click the {drew[0]} you drew earlier "
                                  f"({drew[1]:,.2f} {unit}) so the Quantity List shows it, then press D.", ok=False)
            return
        named = name and name.lower() not in DEFAULT_NAMES
        if named and (not want or same_text(name, want)):
            return self._pass(f"Named it \"{want or name}\".")
        if not forced:
            return  # still typing, or the list hasn't caught up yet
        exact = self._exact_description(drew)
        if exact is not None:
            dlog(f"describe {s['id']}: screen read '{name}', eTakeoff's data says '{exact}'")
            if not want or exact_text(exact, want):
                return self._pass(f"Named it \"{exact}\".")
            name, named = exact, True
        if named:
            msg = f"The description reads \"{name}\". It should be exactly \"{want}\". Press D again and fix it."
            if ("desc", name.lower()) not in self.qty_failed_sigs:
                self.qty_failed_sigs.add(("desc", name.lower()))
                self.cur["failed"].add(f"desc@{len(self.cur['failed'])}")
            return self._miss(msg)
        if getattr(self, "check_src", "") == "button":
            self._render_step(f"The Quantity List still shows the default name. Select the measurement, press D, "
                              f"type {want or 'a description'} and press Enter.", ok=False)

    def _exact_description(self, drew):
        """The description eTakeoff itself stores for the measurement drawn earlier (matched by quantity),
        or None if eTakeoff hasn't published it yet. Screen reading can misread letters; this can't."""
        if not drew or not self.watcher:
            return None
        key = {"area": "area", "length": "length", "perimeter": "perim"}.get(drew[0])
        try:
            rows = self.watcher.read_all().values()
        except Exception as e:
            dlog(f"exact description lookup failed: {e!r}")
            return None
        for rec in rows:
            if key and abs((rec.get(key) or 0) - drew[1]) < 0.011 and rec.get("desc") and rec["desc"] != rec["trace"]:
                return rec["desc"]
        return None

    def _exact_record(self, parsed):
        """eTakeoff's own record of the measurement shown in the Quantity List (matched by its quantities),
        or None if it hasn't published it yet."""
        if not self.watcher:
            return None
        try:
            rows = list(self.watcher.read_all().values())
        except Exception as e:
            dlog(f"exact record lookup failed: {e!r}")
            return None
        vals = {k: v for k, v in parsed["values"].items() if k in ("area", "length", "perimeter") and v}
        if not vals:
            return None
        field = {"area": "area", "length": "length", "perimeter": "perim"}
        hits = [r for r in rows if all(abs((r.get(field[k]) or 0) - v) < 0.011 for k, v in vals.items())]
        if not hits or len({h["guid"] for h in hits}) != 1:
            return None  # not published yet, or two measurements with the same numbers
        own = [h for h in hits if any(abs((h.get("qty") or 0) - (h.get(f) or 0)) < 0.011 for f in ("area", "length", "perim"))]
        return (own or hits)[0]

    def _screen_fail(self, parsed, msg, skill):
        # Only count a miss once per distinct result, and not while the learner may still be clicking points.
        if parsed["sig"] in self.qty_failed_sigs:
            return
        self.qty_failed_sigs.add(parsed["sig"])
        self.cur["failed"].add(f"screen@{len(self.cur['failed'])}")
        if skill:
            self.cur.setdefault("missed_skills", []).append(skill)
        self._miss(msg)

    def verify_published(self, events):
        """eTakeoff publishes a measurement once the next one is drawn. Use that exact data to double-check
        steps graded from the screen (point count, drawing) and to grade steps marked 'Done, check it later'."""
        steps = {st["id"]: st for st in lessons.LESSON["steps"]}
        cur = lessons.LESSON["steps"][self.step_i] if 0 <= self.step_i < len(lessons.LESSON["steps"]) else None
        if cur and cur["type"] == "describe" and getattr(self, "step_i_locked", -1) != self.step_i:
            for kind_ev, rec, _ in events:
                if kind_ev in ("NEW", "CHANGED") and rec.get("desc") and rec["desc"] != rec["trace"] \
                        and same_text(rec["desc"], cur.get("answer") or rec["desc"]):
                    self._grade_description(cur, rec["desc"], {"area": rec["area"], "length": rec["length"],
                                                               "perimeter": rec["perim"], "count": rec.get("points")},
                                            False)
                    break
        for kind_ev, rec, _ in events:
            if kind_ev != "NEW" or rec["guid"] in self.watcher.baseline_guids:
                continue
            for r in self.results:
                st = steps.get(r["id"])
                if not st or st["type"] != "measure" or r.get("verified"):
                    continue
                val = measured(rec, st["kind"])
                if r["status"] == "passed" and r.get("graded_val") and abs(r["graded_val"][1] - val) < 0.011:
                    ok, msg, _ = evaluate(st, rec)
                    r["verified"] = {"points": rec["points"], "drawing": rec["dwg"], "trace": rec["trace"]}
                    if self.instructor.get() and st["id"] in self.answers:
                        # the screen has no point count; add it to the answer key once eTakeoff publishes it
                        self.answers[st["id"]]["points"] = rec["points"]
                        self.save_answers()
                        ok = True
                    if not ok:
                        r["note"] = (r.get("note", "") + f" Double-check: {msg}").strip()
                        r["score"] = min(r["score"], 50)
                    elif points_matter(st) and st.get("points") and rec["points"] != st["points"]:
                        r["note"] = (r.get("note", "") + f" Used {rec['points']} points (expected {st['points']}).").strip()
                        r["score"] = min(r["score"], 80)
                    dlog(f"verified {r['id']}: pts {rec['points']} {rec['dwg']} -> {r.get('note')}")
                    break
                if r["status"] == "pending" and abs(rec["qty"] - val) < max(0.01, abs(val) * 0.001):
                    ok, msg, skill = evaluate(st, rec)
                    r["verified"] = {"points": rec["points"], "drawing": rec["dwg"], "trace": rec["trace"]}
                    r["status"], r["note"] = ("passed (checked later)" if ok else "missed (checked later)"), msg
                    r["score"] = max(0, 100 - 20 * r["hints"]) if ok else 0
                    if ok == "partial":
                        r["score"] = min(r["score"], lessons.LESSON.get("grading", {}).get("partial_score", 75))
                    if not ok and skill:
                        r.setdefault("missed_skills", []).append(skill)
                    dlog(f"late grade {r['id']}: {ok} {msg}")
                    break
