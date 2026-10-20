"""The debug log (coach_debug.log in Documents/TakeoffCoach)."""
import os
import time

from coach.config import RESULTS_DIR


DEBUG_LOG = os.path.join(RESULTS_DIR, "coach_debug.log")


def dlog(msg):
    try:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass
