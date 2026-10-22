"""Windows' built-in OCR, run on a background thread."""
import queue
import threading
import traceback

from coach.qty_list import NUM_ROW, TITLE_SKIP, count_rows, merge_rows, read_title


class QtyReader:
    """Reads eTakeoff's Quantity List pane with Windows' built-in text recognition (OCR).
    Screenshots are taken on the main thread; recognition runs on a worker thread."""

    def __init__(self):
        import mss
        from PIL import Image  # noqa: F401  (checked here so a missing package is reported up front)
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        self.sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.engine_error = None
        threading.Thread(target=self._worker, daemon=True).start()

    def grab(self, box):
        l, t, r, b = box
        shot = self.sct.grab({"left": l, "top": t, "width": max(1, r - l), "height": max(1, b - t)})
        return shot.size[0], shot.size[1], shot.rgb

    def submit(self, tag, w, h, rgb):
        self.jobs.put((tag, w, h, rgb))

    def _worker(self):
        import asyncio
        from PIL import Image
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
        from winrt.windows.storage.streams import Buffer
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            self.engine_error = "Windows has no OCR language installed (Settings > Time & language > Language)."
        while True:
            tag, w, h, rgb = self.jobs.get()
            if engine is None:
                self.results.put((tag, None, self.engine_error, w, h, rgb))
                continue
            try:
                full = Image.frombytes("RGB", (w, h), rgb)

                def ocr(img, x0, y0, scale, pad=24):
                    """OCR one image region; returns lines with positions in the original screenshot's pixels."""
                    big = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
                    canvas = Image.new("RGB", (big.width + 2 * pad, big.height + 2 * pad), "white")
                    canvas.paste(big, (pad, pad))  # white margin helps Windows OCR with text near edges
                    data = canvas.convert("RGBA").tobytes("raw", "BGRA")
                    # This winrt version takes 4 arguments and accepts any Python buffer as the pixel source.
                    try:
                        bmp = SoftwareBitmap.create_copy_from_buffer(data, BitmapPixelFormat.BGRA8, canvas.width, canvas.height)
                    except TypeError:
                        buf = Buffer(len(data))
                        buf.length = len(data)
                        memoryview(buf)[:] = data
                        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.BGRA8, canvas.width, canvas.height)

                    async def rec():
                        return await engine.recognize_async(bmp)
                    out = []
                    for ln in asyncio.run(rec()).lines:
                        words = list(ln.words)
                        if not words:
                            continue
                        ys = [wd.bounding_rect.y + wd.bounding_rect.height / 2 for wd in words]
                        out.append({"text": ln.text,
                                    "x": x0 + (words[0].bounding_rect.x - pad) / scale,
                                    "y": y0 + (sum(ys) / len(ys) - pad) / scale,
                                    "words": [{"text": wd.text,
                                               "x": x0 + (wd.bounding_rect.x - pad) / scale,
                                               "y": y0 + (wd.bounding_rect.y - pad) / scale,
                                               "w": wd.bounding_rect.width / scale,
                                               "h": wd.bounding_rect.height / scale} for wd in words]})
                    return out

                if tag == "scan":  # whole eTakeoff window: find buttons and panes by their labels
                    self.results.put((tag, ocr(full, 0, 0, 2 if max(w, h) * 2 < 9000 else 1), None, w, h, rgb))
                    continue

                if tag in ("dwg", "traces"):  # the drawing name, or the Traces list: plain text with positions
                    self.results.put((tag, ocr(full, 0, 0, 3 if tag == "dwg" else 2), None, w, h, rgb))
                    continue
                lines = ocr(full, 0, 0, 2)
                if count_rows(lines) == 0:
                    # Nothing read as "number + name". Try again larger, then in clean black-and-white
                    # (selected rows are shaded, which can throw the recognizer off).
                    from PIL import ImageOps
                    gray = ImageOps.autocontrast(ImageOps.grayscale(full))
                    bw = gray.point(lambda v: 0 if v < 140 else 255).convert("RGB")
                    for img in (full, bw):
                        again = ocr(img, 0, 0, 3)
                        if count_rows(again) > 0:
                            lines = again
                            break
                lines = merge_rows(lines)
                # The bold title line (the measurement's name) sits beside a colour swatch and is easy for OCR
                # to miss, so read the strip above the first quantity row on its own, without the swatch.
                nums = [l["y"] for l in lines if NUM_ROW.match(l["text"])]
                top = int(min(nums) - 9) if nums else int(h * 0.25)
                if top > 6 and not any(l["y"] < top and not NUM_ROW.match(l["text"]) and not TITLE_SKIP.search(l["text"])
                                       for l in lines):
                    lines += read_title(full.crop((0, 0, w, top)), ocr)
                self.results.put((tag, lines, None, w, h, rgb))
            except Exception as e:
                tb = traceback.extract_tb(e.__traceback__)
                where = f" (line {tb[-1].lineno}: {tb[-1].line})" if tb else ""
                self.results.put((tag, None, repr(e) + where, w, h, rgb))
