"""Subtitle downloader and JSON-to-SRT converter."""

import json
from pathlib import Path

import httpx

from bilibili_downloader.api.endpoints import USER_AGENT


class SubtitleDownloader:
    """Download and convert Bilibili subtitles from JSON to SRT."""

    @staticmethod
    def download_and_convert(subtitle_url: str, output_path: Path) -> None:
        """Download subtitle JSON and convert to SRT format."""
        # Subtitle URLs may be protocol-relative
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url

        resp = httpx.get(
            subtitle_url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.bilibili.com/",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        body = data.get("body", [])
        SubtitleDownloader._write_srt(body, output_path)

    @staticmethod
    def _write_srt(entries: list[dict], output_path: Path) -> None:
        """Write subtitle entries to SRT file."""
        with open(output_path, "w", encoding="utf-8") as f:
            for i, entry in enumerate(entries, 1):
                start = _seconds_to_srt_time(entry.get("from", 0))
                end = _seconds_to_srt_time(entry.get("to", 0))
                content = entry.get("content", "").strip()
                if not content:
                    continue

                f.write(f"{i}\n{start} --> {end}\n{content}\n\n")


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
