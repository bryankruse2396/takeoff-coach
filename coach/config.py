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
COACH_VERSION = "0.36"


def _read_env_file(path):
    """KEY=value lines from a .env file (blank lines and # comments skipped; quotes around values removed)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _setting(name):
    """A setting from the environment, or from the .env file: next to takeoff_coach.py when run from source,
    or the one the build machine packed into TakeoffCoach.exe. .env is never committed (see .env.example)."""
    if os.environ.get(name):
        return os.environ[name]
    folder = getattr(sys, "_MEIPASS", None) if FROZEN else HERE
    return _read_env_file(os.path.join(folder or HERE, ".env")).get(name, "")


def copy_notices():
    """Put the license notices packed into TakeoffCoach.exe where the learner can read them."""
    if not FROZEN:
        return
    import shutil
    for name in ("THIRD_PARTY_NOTICES.txt", "LICENSE"):
        src = os.path.join(getattr(sys, "_MEIPASS", ""), name)
        if os.path.exists(src):
            try:
                shutil.copyfile(src, os.path.join(RESULTS_DIR, "LICENSE.txt" if name == "LICENSE" else name))
            except OSError:
                pass


# Training site (Supabase). Kept out of the code on GitHub: they come from .env (see .env.example).
SITE_URL = _setting("SUPABASE_URL").rstrip("/")
SITE_KEY = _setting("SUPABASE_PUBLISHABLE_KEY")
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
