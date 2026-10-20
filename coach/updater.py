"""Self-update: checks GitHub for a newer TakeoffCoach.exe and swaps it in."""
import json
import os
import urllib.error
import urllib.request

from coach.config import COACH_VERSION, EXE_PATH, UPDATE_MANIFEST
from coach.log import dlog


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def check_for_update():
    """Returns the manifest if a newer coach is published, else None. Never raises."""
    try:
        req = urllib.request.Request(UPDATE_MANIFEST, headers={"User-Agent": f"TakeoffCoach/{COACH_VERSION}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            m = json.loads(r.read())
        if version_tuple(m.get("version")) > version_tuple(COACH_VERSION) and m.get("url"):
            return m
    except Exception as e:
        dlog(f"update check: {e!r}")
    return None


def install_update(manifest, progress=None):
    """Download the new TakeoffCoach.exe, check it, and swap it in after this program closes.
    Windows won't let a running program replace itself, so a tiny script waits for us to exit,
    moves the new file into place and starts it."""
    import hashlib
    import subprocess
    new = EXE_PATH + ".new"
    req = urllib.request.Request(manifest["url"], headers={"User-Agent": f"TakeoffCoach/{COACH_VERSION}"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    want = (manifest.get("sha256") or "").lower()
    if want and h.hexdigest() != want:
        os.remove(new)
        raise RuntimeError("The download was damaged (checksum mismatch). Try again.")
    script = os.path.join(os.path.dirname(EXE_PATH), "takeoff_coach_update.cmd")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(f'@echo off\r\n'
                 f':wait\r\n'
                 f'tasklist /FI "PID eq {os.getpid()}" | find "{os.getpid()}" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
                 f'move /y "{new}" "{EXE_PATH}" >nul\r\n'
                 f'start "" "{EXE_PATH}"\r\n'
                 f'del "%~f0"\r\n')
    # The new program must start as a fresh, independent copy. Without this it inherits the packaging
    # variables of this (closing) copy, looks for files this copy has already removed, and fails with
    # "Failed to load Python DLL".
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_PYI", "_MEI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(["cmd", "/c", script], creationflags=0x08000000, env=env)  # CREATE_NO_WINDOW
