"""Danmaku (bullet comments) downloader and XML-to-ASS converter."""

import logging
from pathlib import Path

import defusedxml.ElementTree as ET
import httpx

from bilibili_downloader.api import endpoints as ep
from bilibili_downloader.api.endpoints import USER_AGENT

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

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Scroll,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
Style: Reverse,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
Style: Bottom,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,8,10,10,10,1
Style: Top,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,4,10,10,10,1
Style: Fixed,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


class DanmakuDownloader:
    """Download and convert Bilibili danmaku."""

    @staticmethod
    def download_xml(cid: int) -> bytes:
        """Download danmaku in XML format from Bilibili."""
        url = ep.DANMAKU_XML_URL.format(cid=cid)
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
        }
        chunks = bytearray()
        with httpx.stream("GET", url, headers=headers, timeout=30.0) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_XML_SIZE:
                    raise RuntimeError(
                        f"Danmaku XML too large (>{MAX_XML_SIZE} bytes)"
                    )
        return bytes(chunks)

    @staticmethod
    def xml_to_ass(xml_content: bytes, output_path: Path) -> None:
        """Convert Bilibili XML danmaku to ASS subtitle format.

        XML format: <d p="time,mode,size,color,timestamp,pool,hash,text">text</d>
        - time: appears at this many seconds
        - mode: 1-3=scroll-right, 4=bottom, 5=top, 6=scroll-left, 7=advanced
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
            lane_available_at = [0.0] * 24

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

                # Convert Bilibili RGB decimal (RRGGBB) to ASS hex (AABBGGRR)
                r = (color >> 16) & 0xFF
                g = (color >> 8) & 0xFF
                b = color & 0xFF
                color_hex = f"&H00{b:02X}{g:02X}{r:02X}"

                if mode == "7":
                    logger.debug("Skipping unsupported advanced danmaku entry")
                    continue

                # Map mode to ASS style and distribute scrolling entries by lane.
                style = _mode_to_style(mode)
                lane = 0
                if mode in {"1", "2", "3", "6"}:
                    lane = min(range(len(lane_available_at)), key=lane_available_at.__getitem__)
                    lane_available_at[lane] = max(lane_available_at[lane], time_sec) + 0.35
                effect = _mode_to_effect(mode, lane)

                # Convert time to ASS format (H:MM:SS.cc)
                start = _seconds_to_ass_time(time_sec)
                duration = 8.0 if mode in {"1", "2", "3", "6"} else 4.0
                end = _seconds_to_ass_time(time_sec + duration)

                # Escape text
                text = danmaku.text or ""
                text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
                text = text.replace("\r\n", "\\N").replace("\n", "\\N").replace("\r", "\\N")

                # Apply color and the source font size within safe bounds.
                text = f"{{\\c{color_hex}\\fs{max(16, min(size, 72))}}}{text}"

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
        "3": "Scroll",
        "4": "Bottom",
        "5": "Top",
        "6": "Reverse",
    }
    return mapping.get(mode, "Scroll")


def _mode_to_effect(mode: str, lane: int = 0) -> str:
    """Map danmaku mode to ASS effect (for scroll direction)."""
    y = 36 + (lane % 24) * 42
    mapping = {
        "1": f"\\move(1920,{y},-600,{y})",
        "2": f"\\move(1920,{y},-600,{y})",
        "3": f"\\move(1920,{y},-600,{y})",
        "6": f"\\move(-600,{y},1920,{y})",
    }
    return mapping.get(mode, "")


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
