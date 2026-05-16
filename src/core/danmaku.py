"""Danmaku (bullet comments) downloader and XML-to-ASS converter."""

import logging
import re
from pathlib import Path

import defusedxml.ElementTree as ET
import httpx

from src.api import endpoints as ep
from src.api.endpoints import USER_AGENT

logger = logging.getLogger(__name__)

# Maximum danmaku XML file size to prevent billion-laughs attacks (10 MB)
MAX_XML_SIZE = 10 * 1024 * 1024

# Danmaku mode mapping
DANMAKU_MODES = {
    "1": "scroll-right",
    "2": "scroll-left",
    "3": "bottom",
    "4": "top",
    "5": "fixed",
    "6": "bottom-fixed",
    "7": "top-fixed",
}

# Default ASS header template
ASS_HEADER = """\
[Script Info]
Title: Bilibili Danmaku
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Scroll,Microsoft YaHei,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
Style: Bottom,Microsoft YaHei,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,8,10,10,10,1
Style: Top,Microsoft YaHei,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,4,10,10,10,1
Style: Fixed,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


class DanmakuDownloader:
    """Download and convert Bilibili danmaku."""

    @staticmethod
    def download_xml(cid: int) -> bytes:
        """Download danmaku in XML format from Bilibili."""
        url = ep.DANMAKU_XML_URL.format(cid=cid)
        resp = httpx.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.bilibili.com/",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.content
        if len(content) > MAX_XML_SIZE:
            raise RuntimeError(
                f"Danmaku XML too large ({len(content)} bytes > {MAX_XML_SIZE})"
            )
        return content

    @staticmethod
    def xml_to_ass(xml_content: bytes, output_path: Path) -> None:
        """Convert Bilibili XML danmaku to ASS subtitle format.

        XML format: <d p="time,mode,size,color,timestamp,pool,hash,text">text</d>
        - time: appears at this many seconds
        - mode: 1=scroll-right, 2=scroll-left, 3=bottom, 4=top, 5=fixed
        - size: font size
        - color: RGB decimal
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise RuntimeError(f"Failed to parse danmaku XML: {e}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ASS_HEADER)
            f.write("\n")

            for danmaku in root.findall("d"):
                p_attr = danmaku.get("p", "")
                if not p_attr:
                    continue

                parts = p_attr.split(",")
                if len(parts) < 8:
                    continue

                try:
                    time_sec = float(parts[0])
                    mode = parts[1]
                    size = int(parts[2])
                    color = int(parts[3])
                except (ValueError, IndexError) as e:
                    logger.debug("Skipping malformed danmaku entry: %s", e)
                    continue

                # Convert color from RGB decimal to ASS hex (AABBGGRR)
                r = color & 0xFF
                g = (color >> 8) & 0xFF
                b = (color >> 16) & 0xFF
                color_hex = f"&H00{b:02X}{g:02X}{r:02X}"

                # Map mode to ASS style and position
                style = _mode_to_style(mode)
                effect = _mode_to_effect(mode)

                # Convert time to ASS format (H:MM:SS.cc)
                start = _seconds_to_ass_time(time_sec)
                end = _seconds_to_ass_time(time_sec + 4.0)  # Default 4s duration

                # Escape text
                text = danmaku.text or ""
                text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

                # Apply color
                text = f"{{\\c{color_hex}}}{text}"

                f.write(f"Dialogue: 0,{start},{end},{style},,0,0,0,{effect},{text}\n")

    @staticmethod
    def download_and_convert(cid: int, output_path: Path) -> None:
        """Convenience: download XML and convert to ASS in one call."""
        xml_data = DanmakuDownloader.download_xml(cid)
        DanmakuDownloader.xml_to_ass(xml_data, output_path)


def _mode_to_style(mode: str) -> str:
    """Map danmaku mode to ASS style name."""
    mapping = {
        "1": "Scroll",
        "2": "Scroll",
        "3": "Bottom",
        "4": "Top",
        "5": "Fixed",
        "6": "Bottom",
        "7": "Top",
    }
    return mapping.get(mode, "Scroll")


def _mode_to_effect(mode: str) -> str:
    """Map danmaku mode to ASS effect (for scroll direction)."""
    mapping = {
        "1": "\\move(1920,0,-500,0)",
        "2": "\\move(-500,0,1920,0)",
    }
    return mapping.get(mode, "")


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
