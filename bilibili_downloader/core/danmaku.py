"""Danmaku (bullet comments) downloader and XML-to-ASS converter."""

import logging
import math
import os
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import defusedxml.ElementTree as ET
import httpx
from PIL import ImageFont
from PySide6.QtCore import QTextBoundaryFinder

from bilibili_downloader.api import endpoints as ep
from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.core.timed_text import (
    MAX_SECONDS,
    ConversionReport,
    atomic_text_output,
    clean_text,
    time_units,
)

logger = logging.getLogger(__name__)

# Maximum danmaku XML file size to prevent billion-laughs attacks (10 MB)
MAX_XML_SIZE = 10 * 1024 * 1024

# Danmaku mode mapping
DANMAKU_MODES = {
    "1": "scroll-right",
    "2": "scroll-right",
    "3": "scroll-right",
    "4": "bottom",
    "5": "top",
    "6": "scroll-left",
    "7": "advanced",
}

# Default ASS header template
ASS_HEADER = """\
[Script Info]
Title: Bilibili Danmaku
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Scroll,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,10,10,10,1
Style: Reverse,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,10,10,10,1
Style: Bottom,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
Style: Top,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,8,10,10,10,1
Style: Fixed,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


WIDTH, HEIGHT, PADDING = 1920, 1080, 20
BAND_HEIGHT = 12
MAX_TEXT_LENGTH = 4096
MAX_ACTIVE_RESERVATIONS = 512


def _export_font():
    """Prefer a local CJK font without requiring a GUI session."""
    if sys.platform == "win32":
        candidates = [
            ("Microsoft YaHei", Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            ("Hiragino Sans GB", Path("/System/Library/Fonts/Hiragino Sans GB.ttc")),
            ("Songti SC", Path("/System/Library/Fonts/Supplemental/Songti.ttc")),
        ]
    else:
        candidates = [
            ("Noto Sans CJK SC", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")),
            ("Noto Sans CJK SC", Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc")),
            ("WenQuanYi Micro Hei", Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")),
        ]
    for family, path in candidates:
        if path.is_file():
            return family, path
    return ("Microsoft YaHei" if sys.platform == "win32" else "sans-serif"), None


FONT_FAMILY, FONT_PATH = _export_font()
ASS_HEADER = ASS_HEADER.replace(",Arial,", f",{FONT_FAMILY},")


@lru_cache(maxsize=64)
def _font(size):
    if FONT_PATH is not None:
        try:
            return ImageFont.truetype(str(FONT_PATH), size)
        except OSError:
            pass
    return None


@lru_cache(maxsize=8192)
def _cluster_width(cluster, size):
    font = _font(size)
    if font is not None:
        try:
            return font.getlength(cluster) * 1.20
        except (ValueError, OSError):
            pass
    # A conservative em bound also covers missing font metrics and fallback glyphs.
    return sum(
        size * 1.20 for char in cluster
        if not unicodedata.category(char).startswith("M") and char != "\u200d"
    )


def _clusters(text):
    """Use Unicode grapheme boundaries; QtCore works without a GUI application."""
    finder = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, text)
    encoded = text.encode("utf-16-le")
    start = 0
    while (end := finder.toNextBoundary()) != -1:
        yield encoded[start * 2:end * 2].decode("utf-16-le")
        start = end


def _layout_text(text, size):
    lines = []
    widths = []
    maximum = WIDTH - PADDING * 2
    for paragraph in text.split("\n"):
        line, width = "", 0.0
        for cluster in _clusters(paragraph):
            advance = _cluster_width(cluster, size)
            if line and width + advance > maximum - 8:
                lines.append(line)
                widths.append(width)
                line, width = "", 0.0
            line += cluster
            width += advance
        lines.append(line)
        widths.append(width)
    font = _font(size)
    line_height = max(size, sum(font.getmetrics()) if font else size) * 1.25 + 4
    return "\n".join(lines), math.ceil(max(widths, default=0)) + 8, math.ceil(len(lines) * line_height)


def _ass_text(text):
    # Braces have no portable literal escape across libass and VSFilter.
    text = text.replace("{", "｛").replace("}", "｝")
    # A word joiner prevents literal \N, \n and \h from becoming ASS controls.
    result = []
    for index, char in enumerate(text):
        result.append(char)
        if char == "\\" and index + 1 < len(text) and text[index + 1] in "Nnh":
            result.append("\u2060")
    return "".join(result).replace("\n", r"\N")


@dataclass(frozen=True)
class _Comment:
    start: int
    mode: str
    size: int
    color: int
    text: str
    width: int
    height: int

    @property
    def end(self) -> int:
        return self.start + (800 if self.mode in {"1", "2", "3", "6"} else 400)

    @property
    def endpoints(self) -> tuple[float, float]:
        if self.mode in {"1", "2", "3"}:
            return WIDTH + PADDING, -self.width - PADDING
        if self.mode == "6":
            return -self.width - PADDING, WIDTH + PADDING
        center = (WIDTH - self.width) / 2
        return center, center

    def x_at(self, time: int) -> float:
        first, last = self.endpoints
        return first + (last - first) * (time - self.start) / (self.end - self.start)


def _collides(first: _Comment, second: _Comment) -> bool:
    start, end = max(first.start, second.start), min(first.end, second.end)
    if start >= end:
        return False
    delta = [first.x_at(time) - second.x_at(time) for time in (start, end)]
    return max(delta) > -first.width - 8 and min(delta) < second.width + 8


class _Tracks:
    """Share vertical bands across moving and fixed comments; keep source times."""

    def __init__(self):
        self.band_count = (HEIGHT - PADDING * 2) // BAND_HEIGHT
        self.active: list[tuple[_Comment, int, int]] = []
        self.uncertain_until = 0

    def place(self, comment):
        self.active = [
            placement for placement in self.active if placement[0].end > comment.start
        ]
        # Dense floods still export every comment, with bounded layout work.
        if len(self.active) >= MAX_ACTIVE_RESERVATIONS:
            discarded, _offset, _span = self.active.pop(0)
            self.uncertain_until = max(self.uncertain_until, discarded.end)
        span = math.ceil((comment.height + 4) / BAND_HEIGHT)
        if span > self.band_count:
            raise ValueError("弹幕高度超过画面")
        count = self.band_count - span + 1
        differences = [0] * (count + 1)
        for entry, offset, occupied in self.active:
            if _collides(comment, entry):
                first = max(0, offset - span + 1)
                last = min(count - 1, offset + occupied - 1)
                differences[first] += 1
                differences[last + 1] -= 1
        conflicts, current = [], 0
        for difference in differences[:count]:
            current += difference
            conflicts.append(current)
        positions = range(count)
        if comment.mode == "4":
            positions = reversed(positions)
        best = min(positions, key=conflicts.__getitem__)
        self.active.append((comment, best, span))
        crowded = bool(conflicts[best]) or comment.start < self.uncertain_until
        return PADDING + best * BAND_HEIGHT, crowded


class DanmakuDownloader:
    """Download and convert ordinary Bilibili XML comments to portable ASS."""

    @staticmethod
    def download_xml(cid: int) -> bytes:
        url = ep.DANMAKU_XML_URL.format(cid=cid)
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}
        chunks = bytearray()
        with httpx.stream("GET", url, headers=headers, timeout=30.0) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_XML_SIZE:
                    raise RuntimeError(f"Danmaku XML too large (>{MAX_XML_SIZE} bytes)")
        return bytes(chunks)

    @staticmethod
    def xml_to_ass(xml_content: bytes, output_path: Path) -> ConversionReport:
        if len(xml_content) > MAX_XML_SIZE:
            raise RuntimeError(f"Danmaku XML too large (>{MAX_XML_SIZE} bytes)")
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            raise RuntimeError(f"Failed to parse danmaku XML: {exc}") from exc

        report = ConversionReport()
        comments = []
        for node in root.findall("d"):
            try:
                fields = node.get("p", "").split(",")
                if len(fields) < 8:
                    raise ValueError("弹幕参数不完整")
                mode = str(int(fields[1]))
                if mode not in {"1", "2", "3", "4", "5", "6"}:
                    report.unsupported += 1
                    continue
                start = time_units(fields[0], 100)
                requested_size = int(fields[2])
                if requested_size <= 0:
                    raise ValueError("弹幕字号必须大于零")
                size = max(16, min(requested_size, 72))
                color = int(fields[3])
                if not 0 <= color <= 0xFFFFFF:
                    raise ValueError("弹幕颜色超出 RGB 范围")
                raw = node.text or ""
                text = clean_text(raw).replace("{", "｛").replace("}", "｝")
                if not text.strip() or len(text) > MAX_TEXT_LENGTH:
                    raise ValueError("空白或过长弹幕")
                original_size = requested_size
                while True:
                    laid_out, width, height = _layout_text(text, size)
                    if (
                        height + 4 <= (HEIGHT - PADDING * 2) // BAND_HEIGHT * BAND_HEIGHT
                        and width <= WIDTH - PADDING * 2
                    ):
                        break
                    if size == 16:
                        raise ValueError("弹幕尺寸超过画面")
                    size = max(16, size - 4)
                comment = _Comment(start, mode, size, color, laid_out, width, height)
                if comment.end > time_units(MAX_SECONDS, 100):
                    raise ValueError("弹幕结束时间超出范围")
                if (
                    "{" in raw or "}" in raw or size != original_size
                    or any(
                        unicodedata.category(char) in {"Cs", "Cc"} and char not in "\r\n\t"
                        for char in raw
                    )
                ):
                    report.normalized += 1
                comments.append(comment)
            except (ValueError, IndexError) as exc:
                report.invalid += 1
                logger.debug("Skipping malformed danmaku entry: %s", exc)

        comments.sort(key=lambda comment: comment.start)
        if not comments:
            details = "；".join(report.warnings("弹幕"))
            raise ValueError("没有可导出的普通弹幕" + (f"；{details}" if details else ""))
        tracks = _Tracks()
        with atomic_text_output(output_path) as handle:
            handle.write(ASS_HEADER)
            handle.write("\n")
            for comment in comments:
                y, crowded = tracks.place(comment)
                report.crowded += crowded
                motion = _mode_to_effect(comment.mode, width=comment.width, y=y)
                if not motion:
                    motion = f"\\pos({(WIDTH - comment.width) // 2},{y})"
                r, g, b = (comment.color >> 16) & 255, (comment.color >> 8) & 255, comment.color & 255
                outline = "FFFFFF" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 128 else "000000"
                tags = (
                    f"\\an7\\q2{motion}\\3c&H{outline}&"
                    f"\\c&H{b:02X}{g:02X}{r:02X}&\\fs{comment.size}"
                )
                text = "{" + tags + "}" + _ass_text(comment.text)
                handle.write(
                    f"Dialogue: 0,{_ass_time(comment.start)},{_ass_time(comment.end)},"
                    f"{_mode_to_style(comment.mode)},,0,0,0,,{text}\n"
                )
                report.exported += 1
        return report

    @staticmethod
    def download_and_convert(cid: int, output_path: Path) -> ConversionReport:
        return DanmakuDownloader.xml_to_ass(DanmakuDownloader.download_xml(cid), output_path)


def _mode_to_style(mode: str) -> str:
    return {
        "1": "Scroll", "2": "Scroll", "3": "Scroll",
        "4": "Bottom", "5": "Top", "6": "Reverse",
    }.get(mode, "Scroll")


def _mode_to_effect(mode: str, lane: int = 0, *, width: int = 600, y: int | None = None) -> str:
    """Return top-left anchored motion with the entire text offscreen at either end."""
    if y is None:
        y = PADDING + lane * 42
    if mode in {"1", "2", "3"}:
        return f"\\move({WIDTH + PADDING},{y},{-width - PADDING},{y})"
    if mode == "6":
        return f"\\move({-width - PADDING},{y},{WIDTH + PADDING},{y})"
    return ""


def _ass_time(units):
    hours, remainder = divmod(units, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _seconds_to_ass_time(seconds: float) -> str:
    return _ass_time(time_units(seconds, 100))
