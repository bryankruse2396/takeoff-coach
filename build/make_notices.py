"""Writes THIRD_PARTY_NOTICES.txt: the license of every open-source component packed into TakeoffCoach.exe.
Run by the build machine after installing build/requirements.txt, so the texts always match the versions
actually shipped. The file is packed into the exe and copied to Documents\\TakeoffCoach on start."""
import glob
import importlib.metadata as md
import os
import sys

# Packages that end up inside TakeoffCoach.exe (build-only tools such as altgraph/pefile are not shipped).
SHIPPED = ["comtypes", "pynput", "six", "mss", "pillow", "typing_extensions", "winrt-runtime",
           "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections", "winrt-Windows.Media.Ocr",
           "winrt-Windows.Graphics.Imaging", "winrt-Windows.Storage.Streams", "winrt-Windows.Globalization",
           "pyinstaller"]

MIT = """Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
USE OR OTHER DEALINGS IN THE SOFTWARE."""
# Wheels that ship without a license file: their published license (https://github.com/pywinrt/pywinrt).
FALLBACK = {"winrt": "MIT License\n\nCopyright (c) Microsoft Corporation. All rights reserved.\n"
                     "Copyright (c) 2021-2025 David Lechner <david@pybricks.com>\n\n" + MIT}
NOTES = {
    "pynput": "pynput is licensed under the GNU Lesser General Public License v3. Its source code is available at "
              "https://github.com/moses-palmer/pynput, and the source code of Takeoff Coach, which uses it, at "
              "https://github.com/bryankruse2396/takeoff-coach, so the library can be replaced or modified.",
    "pyinstaller": "Only PyInstaller's bootloader is inside TakeoffCoach.exe. Its license (GPL v2 or later with the "
                   "bootloader exception, below) allows distributing programs built with it, including commercial ones.",
}


def license_text(dist):
    texts = []
    for f in dist.files or []:
        name = os.path.basename(str(f)).upper()
        if name.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE")):
            try:
                with open(f.locate(), encoding="utf-8", errors="replace") as fh:
                    texts.append(fh.read().strip())
            except OSError:
                pass
    return "\n\n".join(texts)


def main(out_path):
    parts = ["Takeoff Coach - third-party notices",
             "Copyright 2026 Takeoff Training LLC. All rights reserved (Takeoff Coach itself; see LICENSE).",
             "Takeoff Training is independent and is not affiliated with, sponsored by, or endorsed by eTakeoff, LLC.",
             "", "TakeoffCoach.exe includes the following open-source software, each under its own license:", ""]
    missing = []
    for name in SHIPPED:
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            missing.append(name)
            continue
        meta = dist.metadata
        lic = meta.get("License-Expression") or meta.get("License") or ""
        text = license_text(dist) or next((v for k, v in FALLBACK.items() if name.lower().startswith(k)), "")
        if not text:
            missing.append(f"{name} (no license text)")
        parts += ["=" * 100, f"{meta['Name']} {dist.version}  ({lic.splitlines()[0] if lic else 'see below'})", "=" * 100]
        if name in NOTES:
            parts += [NOTES[name], ""]
        parts += [text, ""]
    # Python itself and the Tcl/Tk libraries it brings for the coach's window
    for title, pattern in (("Python " + sys.version.split()[0], os.path.join(sys.base_prefix, "LICENSE*")),
                           ("Tcl/Tk", os.path.join(sys.base_prefix, "tcl", "tcl8*", "license.terms"))):
        files = glob.glob(pattern)
        if files:
            parts += ["=" * 100, title, "=" * 100, open(files[0], encoding="utf-8", errors="replace").read().strip(), ""]
        elif sys.platform == "win32":
            missing.append(title)
    if missing:
        sys.exit(f"Missing license information for: {', '.join(missing)}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")
    print(f"wrote {out_path} ({len(SHIPPED)} packages + Python)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "THIRD_PARTY_NOTICES.txt")
