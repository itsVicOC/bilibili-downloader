"""Subtitle downloader and JSON-to-SRT converter."""

import json
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import httpx

from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.core.timed_text import (
    ConversionReport,
    atomic_text_output,
    clean_text,
    time_units,
)
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

MAX_SUBTITLE_BYTES = 10 * 1024 * 1024


class SubtitleDownloader:
    """Download and convert Bilibili subtitles from JSON to SRT."""

    @staticmethod
    def download_and_convert(subtitle_url: str, output_path: Path) -> ConversionReport:
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

        if not isinstance(data, dict):
            raise ValueError("字幕数据格式无效")
        return SubtitleDownloader._write_srt(data.get("body", []), output_path)

    @staticmethod
    def _write_srt(entries: list[dict], output_path: Path) -> ConversionReport:
        """Write subtitle entries to SRT file."""
        if not isinstance(entries, list):
            raise ValueError("字幕内容必须是列表")
        report = ConversionReport()
        valid = []
        for entry in entries:
            try:
                if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
                    raise ValueError("字幕正文必须是字符串")
                start = time_units(entry["from"], 1000)
                end = time_units(entry["to"], 1000)
                if end <= start:
                    raise ValueError("字幕结束时间必须晚于开始时间")
                raw = entry["content"]
                # Empty lines separate SRT cues, so keep only non-empty text lines.
                content = "\n".join(
                    line for line in clean_text(raw).strip().split("\n") if line.strip()
                )
                if not content:
                    raise ValueError("字幕正文为空")
                if any(
                    unicodedata.category(char) in {"Cs", "Cc"} and char not in "\r\n\t"
                    for char in raw
                ):
                    report.normalized += 1
                valid.append((start, end, content))
            except (ValueError, KeyError):
                report.invalid += 1
        valid.sort(key=lambda cue: cue[0])
        if not valid:
            details = "；".join(report.warnings("字幕"))
            raise ValueError("字幕轨道没有有效内容" + (f"；{details}" if details else ""))
        with atomic_text_output(output_path) as handle:
            for index, (start, end, content) in enumerate(valid, 1):
                handle.write(
                    f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{content}\n\n"
                )
                report.exported += 1
        return report


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
    return _srt_time(time_units(seconds, 1000))


def _srt_time(units: int) -> str:
    hours, remainder = divmod(units, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
