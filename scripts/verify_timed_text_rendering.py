#!/usr/bin/env python3
"""Validate real ASS rendering using an explicitly supplied local libass library.

Example:
  python scripts/verify_timed_text_rendering.py --libass /path/to/libass.so \
    --output-dir /tmp/biliflow-ass-check

This optional developer check never downloads a renderer or modifies app settings.
"""

from __future__ import annotations

import argparse
import ctypes as C
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from PIL import Image, ImageChops, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bilibili_downloader.core.danmaku import (
    ASS_HEADER,
    FONT_FAMILY,
    FONT_PATH,
    DanmakuDownloader,
)


class _AssImage(C.Structure):
    pass


_AssImage._fields_ = [
    ("w", C.c_int), ("h", C.c_int), ("stride", C.c_int),
    ("bitmap", C.POINTER(C.c_ubyte)), ("color", C.c_uint32),
    ("x", C.c_int), ("y", C.c_int),
    ("next", C.POINTER(_AssImage)), ("type", C.c_int),
]


class Renderer:
    def __init__(self, path: Path):
        self.api = C.CDLL(str(path))
        functions = [
            ("ass_library_init", [], C.c_void_p),
            ("ass_renderer_init", [C.c_void_p], C.c_void_p),
            ("ass_set_frame_size", [C.c_void_p, C.c_int, C.c_int], None),
            ("ass_set_storage_size", [C.c_void_p, C.c_int, C.c_int], None),
            ("ass_set_fonts", [C.c_void_p, C.c_char_p, C.c_char_p, C.c_int, C.c_char_p, C.c_int], None),
            ("ass_read_memory", [C.c_void_p, C.c_char_p, C.c_size_t, C.c_char_p], C.c_void_p),
            ("ass_render_frame", [C.c_void_p, C.c_void_p, C.c_longlong, C.POINTER(C.c_int)], C.POINTER(_AssImage)),
            ("ass_free_track", [C.c_void_p], None),
            ("ass_renderer_done", [C.c_void_p], None),
            ("ass_library_done", [C.c_void_p], None),
        ]
        for name, arguments, result in functions:
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.library = self.api.ass_library_init()
        if not self.library:
            raise RuntimeError("libass initialization failed")
        self.renderer = self.api.ass_renderer_init(self.library)
        if not self.renderer:
            self.api.ass_library_done(self.library)
            raise RuntimeError("libass renderer initialization failed")
        self.api.ass_set_frame_size(self.renderer, 1920, 1080)
        self.api.ass_set_storage_size(self.renderer, 1920, 1080)
        font_path = str(FONT_PATH).encode() if FONT_PATH else None
        self.api.ass_set_fonts(self.renderer, font_path, FONT_FAMILY.encode(), 1, None, 1)

    def close(self):
        self.api.ass_renderer_done(self.renderer)
        self.api.ass_library_done(self.library)

    def render(self, script: str, milliseconds: int = 1500) -> Image.Image:
        data = script.encode("utf-8")
        buffer = C.create_string_buffer(data)
        track = self.api.ass_read_memory(self.library, buffer, len(data), None)
        if not track:
            raise RuntimeError("libass could not parse the exported file")
        try:
            changed = C.c_int()
            node = self.api.ass_render_frame(
                self.renderer, track, milliseconds, C.byref(changed)
            )
            image = Image.new("RGB", (1920, 1080))
            while node:
                part = node.contents
                if part.w and part.h:
                    raw = C.string_at(part.bitmap, part.stride * (part.h - 1) + part.w)
                    packed = b"".join(
                        raw[row * part.stride:row * part.stride + part.w]
                        for row in range(part.h)
                    )
                    mask = Image.frombytes("L", (part.w, part.h), packed)
                    opacity = 255 - (part.color & 255)
                    if opacity != 255:
                        mask = mask.point(lambda value: value * opacity // 255)
                    color = ((part.color >> 24) & 255, (part.color >> 16) & 255, (part.color >> 8) & 255)
                    image.paste(
                        color, (part.x, part.y, part.x + part.w, part.y + part.h), mask
                    )
                node = part.next
            return image
        finally:
            self.api.ass_free_track(track)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libass", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    renderer = Renderer(args.libass)

    def convert(name, text, mode=5, size=25, color=0xFFFFFF):
        root = Element("i")
        node = SubElement(root, "d", p=f"1,{mode},{size},{color},0,0,h,1")
        node.text = text
        path = args.output_dir / f"{name}.ass"
        report = DanmakuDownloader.xml_to_ass(tostring(root, encoding="utf-8"), path)
        assert report.exported == 1, report
        return path.read_text(encoding="utf-8")

    rows = []
    try:
        for index, text in enumerate([r"C:\abc", r"C:\new", r"Hello\NWorld", r"Hello\hWorld", "{Hello}"]):
            script = convert(f"characters-{index}", text)
            # Explicit visual reference: no doubled slashes, no control-sequence interpretation.
            literal = text.replace("{", "｛").replace("}", "｝").replace("\\", "\\\u2060")
            event = next(line for line in script.split("\n") if line.startswith("Dialogue: "))
            fields = event.removeprefix("Dialogue: ").split(",", 9)
            tags = fields[9].split("}", 1)[0] + "}"
            reference = ASS_HEADER + ",".join(
                ["Dialogue: " + fields[0], *fields[1:9], tags + literal]
            ) + "\n"
            actual, expected = renderer.render(script), renderer.render(reference)
            assert actual.getbbox(), (text, "no visible glyphs")
            assert ImageChops.difference(actual, expected).getbbox() is None, text
            row = Image.new("RGB", (1000, 100), "#181818")
            ImageDraw.Draw(row).text((12, 8), f"Verified export: {text}", fill="white")
            box = actual.getbbox()
            row.paste(actual.crop((box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3)), (12, 35))
            rows.append(row)

        for mode in (1, 6):
            for label, text in (("latin", "A" * 200), ("braces", "{}" * 100)):
                script = convert(f"long-motion-{mode}-{label}", text, mode)
                assert renderer.render(script, 1000).getbbox() is None
                assert renderer.render(script, 5000).getbbox()
                assert renderer.render(script, 8990).getbbox() is None
            short = convert(f"direction-{mode}", "SCROLL", mode)
            first = renderer.render(short, 3000).getbbox()
            second = renderer.render(short, 5000).getbbox()
            assert first and second
            assert second[0] < first[0] if mode == 1 else second[0] > first[0]

        large = renderer.render(convert("large-font", "ABCDEFGHIJ", 1, 72), 5000)
        box = large.getbbox()
        assert box and box[1] > 0 and box[3] < 1080, box
        large.save(args.output_dir / "large-font.png")
        for name, mode in (("top", 5), ("bottom", 4)):
            frame = renderer.render(convert(name, "中文 ABC", mode))
            box = frame.getbbox()
            assert box and box[1] > 0 and box[3] < 1080, box
            assert box[1] < 540 if mode == 5 else box[1] > 540
            frame.save(args.output_dir / f"{name}.png")

        red = renderer.render(convert("red", "RED", color=0xFF0000))
        assert red.getbbox()
        assert any(
            r > 160 and g < 20 and b < 20
            for r, g, b in red.crop(red.getbbox()).getdata()
        )
        black = renderer.render(convert("black", "BLACK", color=0))
        assert black.getbbox(), "Black text needs a contrasting outline on a dark frame"
        sheet = Image.new("RGB", (1000, len(rows) * 100))
        for index, row in enumerate(rows):
            sheet.paste(row, (0, index * 100))
        sheet.save(args.output_dir / "verified-characters.png")
        print("PASS: literal characters, motion bounds/directions, large font, fixed positions and RGB color")
        print(f"Artifacts: {args.output_dir}")
    finally:
        renderer.close()


if __name__ == "__main__":
    main()
