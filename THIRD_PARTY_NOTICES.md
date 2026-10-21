# Third-party notices

TakeoffCoach.exe includes the open-source software below, each used under its own license. The full
license texts, for the exact versions shipped, are in `THIRD_PARTY_NOTICES.txt`. The build machine
writes that file (`build/make_notices.py`), packs it into the exe, and the coach copies it to
`Documents\TakeoffCoach` when it starts.

| Component | Used for | License |
|---|---|---|
| [Python](https://www.python.org) and Tcl/Tk | Runs the coach and draws its window | PSF License; Tcl/Tk license (BSD-style) |
| [comtypes](https://github.com/enthought/comtypes) | Reading measurements through eTakeoff's COM interface | MIT |
| [pynput](https://github.com/moses-palmer/pynput) | Noticing clicks and the S/Enter keys in eTakeoff | LGPL-3.0 (see below) |
| [six](https://github.com/benjaminp/six) | Needed by pynput | MIT |
| [mss](https://github.com/BoboTiG/python-mss) | Screenshots of the Quantity List | MIT |
| [Pillow](https://python-pillow.org) | Image handling for screen reading | MIT-CMU (HPND) |
| [pywinrt](https://github.com/pywinrt/pywinrt) (`winrt-*` packages) | Windows' built-in OCR | MIT |
| [typing_extensions](https://github.com/python/typing_extensions) | Needed by pywinrt | PSF-2.0 |
| [PyInstaller](https://pyinstaller.org) bootloader | Packs the coach into one .exe | GPL-2.0-or-later with the bootloader exception, which allows distributing programs built with it, including commercial ones |

**pynput (LGPL-3.0):** its source is at https://github.com/moses-palmer/pynput and the coach's source,
which uses it unmodified, is in this repository, so the library can be replaced or modified.

The Takeoff Coach code itself is © 2026 Takeoff Training LLC, all rights reserved (see `LICENSE`).
