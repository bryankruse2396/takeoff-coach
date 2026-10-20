"""Settings: version, website address, file locations, training-project names."""
import os
import sys


FROZEN = getattr(sys, "frozen", False)  # True when running as TakeoffCoach.exe
EXE_PATH = sys.executable if FROZEN else None
HERE = (os.path.join(os.path.expanduser("~"), "Documents", "TakeoffCoach") if FROZEN
        else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # from source: next to takeoff_coach.py
os.makedirs(HERE, exist_ok=True)
TARGETS_FILE = os.path.join(HERE, "coach_targets.json")
PREFS_FILE = os.path.join(HERE, "coach_prefs.json")       # where the learner dragged the callout to
CALLOUT_DEFAULT = (0.24, 0.70)                            # top-left of the callout, as a fraction of eTakeoff's window
RESULTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "TakeoffCoach")
COACH_VERSION = "0.26"
# Training site (Supabase). The publishable key is meant to be public; what each account can do is
# enforced by the database's security rules.
SITE_URL = "https://ylhhgqxbngvpqmtceois.supabase.co"
SITE_KEY = "sb_publishable_H7oV3RkzMEyRfxCQcRjK2w_NdJPz8sT"
ACCOUNT_FILE = os.path.join(RESULTS_DIR, "account.json")      # sign-in token, so learners sign in once
CATALOG_FILE = os.path.join(RESULTS_DIR, "catalog.json")      # last lessons/tests downloaded (works offline)
OUTBOX_DIR = os.path.join(RESULTS_DIR, "outbox")              # results waiting to upload
ACTIVE_TEST_FILE = os.path.join(RESULTS_DIR, "active_test.json")  # a test that was running when the coach closed
# Where the coach looks for a newer version of itself: {"version": "0.20", "url": "...exe", "sha256": "..."}
UPDATE_MANIFEST = "https://github.com/bryankruse2396/takeoff-coach/releases/latest/download/latest.json"
TIERS = ["basic", "intermediate", "advanced", "expert"]
PRACTICE_PREFIX = "Takeoff Training Practice - "  # + the learner's name from their training-site account
TEST_PREFIX = "Takeoff Training Test - "
SAMPLE_DIR = r"C:\ProgramData\eTakeoffProjects\eTakeoffSamples\LaQuintaHotel"
