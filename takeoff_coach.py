r"""Takeoff Coach: starts the program. The code itself is in the coach/ folder (see README, "How the code is organized").

Run from source (Windows, with eTakeoff Dimension installed):
    pip install -r build/requirements.txt
    python takeoff_coach.py
Options:
    --version     print the version and exit
    --self-test   check that every part the program needs loads (used by the build machine)
"""
import sys

try:
    import pynput  # noqa: F401
except ImportError:
    sys.exit("Missing package. Run:  pip install -r build/requirements.txt")


def main():
    if "--version" in sys.argv:
        from coach.config import COACH_VERSION
        if sys.stdout:
            print(COACH_VERSION)
    elif "--self-test" in sys.argv:
        from coach.selftest import self_test
        self_test()
    else:
        from coach.app import Coach
        Coach().run()


if __name__ == "__main__":
    main()
