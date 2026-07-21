"""Subtitle downloader and JSON-to-SRT converter."""

import json
from pathlib import Path
from urllib.parse import urljoin

import httpx

from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

MAX_SUBTITLE_BYTES = 10 * 1024 * 1024


class SubtitleDownloader:
    """Download and convert Bilibili subtitles from JSON to SRT."""

    @staticmethod
    def download_and_convert(subtitle_url: str, output_path: Path) -> None:
        """Download subtitle JSON and convert to SRT format."""
        subtitle_url = trusted_https_url(subtitle_url, BILIBILI_RESOURCE_HOSTS)

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
        }
        with httpx.Client(headers=headers, timeout=30.0, follow_redirects=False) as client:
            current_url = subtitle_url
            for _ in range(8):
                with client.stream("GET", current_url) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            resp.raise_for_status()
                        current_url = trusted_https_url(
                            urljoin(current_url, location),
                            BILIBILI_RESOURCE_HOSTS,
                        )
                        continue
                    resp.raise_for_status()
                    content = bytearray()
                    for chunk in resp.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_SUBTITLE_BYTES:
                            raise RuntimeError("字幕文件过大")
                    data = json.loads(content)
                    break
            else:
                raise RuntimeError("字幕地址重定向次数过多")

        body = data.get("body", [])
        SubtitleDownloader._write_srt(body, output_path)

    @staticmethod
    def _write_srt(entries: list[dict], output_path: Path) -> None:
        """Write subtitle entries to SRT file."""
        with open(output_path, "w", encoding="utf-8") as f:
            index = 1
            for entry in entries:
                start = _seconds_to_srt_time(entry.get("from", 0))
                end = _seconds_to_srt_time(entry.get("to", 0))
                content = entry.get("content", "").strip()
                if not content:
                    continue

                f.write(f"{index}\n{start} --> {end}\n{content}\n\n")
                index += 1


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
