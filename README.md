# Takeoff Coach

On-screen coach for eTakeoff Dimension training. Learners download **TakeoffCoach.exe** from the
training site (it links to the latest release here) and the program updates itself.

The coach only **reads** from eTakeoff (its COM interface and the screen); it never changes a project.

© 2026 Takeoff Training LLC. All rights reserved (see `LICENSE`). Takeoff Training is independent and is not
affiliated with, sponsored by, or endorsed by eTakeoff, LLC; eTakeoff and eTakeoff Dimension are trademarks of
their owner. Open-source components and their licenses: `THIRD_PARTY_NOTICES.md`.

## Publishing a new version

1. Change `COACH_VERSION` in `coach/config.py`.
2. Push to `main`. GitHub Actions (`.github/workflows/build.yml`) runs the checks and tests, then builds
   the .exe on Windows, self-tests it, and publishes the release with `latest.json`, which every
   learner's coach reads to offer **Update now**.

If a test fails, nothing is built or released.

## How the code is organized

`takeoff_coach.py` only starts the program. Everything else is in `coach/`, one job per file:

| File | What it does |
|---|---|
| `config.py` | Version number, website address, file locations, training-project names |
| `cloud.py` | The training website: sign-in, downloading lessons and tests, uploading results (queued offline) |
| `updater.py` | Self-update from the GitHub releases |
| `lessons.py` | The current lesson, answer keys, and turning the site's blocks into steps |
| `builtin_lessons.py` | Buttons and panes the coach knows, and the lessons built into the program |
| `projects.py` | The learner's own practice/test projects and which drawing a step uses |
| `grading.py` | Grading a measurement against the answer key |
| `etakeoff.py` | Reading measurements from eTakeoff (COM, read-only) |
| `winapi.py` | Windows helpers: eTakeoff's window, its position, its own picture (PrintWindow) |
| `ocr.py` | Windows' built-in OCR, on a background thread |
| `qty_list.py` | Understanding the Quantity List read off the screen |
| `find_buttons.py` | Finding eTakeoff's buttons and panes in a screenshot |
| `textmatch.py` | Comparing text, forgiving typical OCR misreads |
| `log.py` | The debug log, `Documents\TakeoffCoach\coach_debug.log` |
| `selftest.py` | `TakeoffCoach.exe --self-test`, run by the build machine |
| `app.py` | The Coach window: joins the parts below, the timer loop, `run()` |

`coach/ui/` holds the parts of the window, one per screen or job:

| File | What it does |
|---|---|
| `start_screen.py` | Sign-in, choosing a lesson or test, syncing, updating |
| `project_check.py` | Before practice or a test: right training project open, test drawings clean |
| `calibration.py` | Finding eTakeoff's buttons and Quantity List on screen |
| `lesson_flow.py` | Moving through steps: next, back, hint, skip, pass, miss |
| `checking.py` | Checking what the learner did: clicks, measurements, descriptions |
| `test_flow.py` | Tests: start, idle time-out, review, submit |
| `callout.py` | The instruction callout and arrows over eTakeoff |
| `screen_watch.py` | Which drawing is open (wrong drawing: how to get to the right one), and following the Traces list when it's scrolled |
| `results.py` | The results screen and uploading practice sessions |

## Lesson content

Lessons, tests and quizzes are written in Takeoff Training's own words. Don't copy text, exercises or images
from eTakeoff's training guide or website: describe how the software works in your own words instead.

## Running it from source (Windows)

```
pip install -r build/requirements.txt
python takeoff_coach.py
```

## Tests

`tests/` runs on any machine: Windows-only parts are replaced by stand-ins (`tests/winstub.py`).
The window tests need a display; on Linux run them on a virtual one:

```
pip install pytest ruff pillow
ruff check
xvfb-run -a python -m pytest -v
```

## Snapshots

Every commit is a saved version, and every release (v0.19, v0.20, ...) can be downloaded from
**Releases**. Named snapshots are kept as branches, e.g. `snapshot-2026-10-19` (the last single-file
version, before the code was split into modules).
