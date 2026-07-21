"""Tests for subtitle converter."""

import tempfile
from pathlib import Path

from bilibili_downloader.core.subtitle import SubtitleDownloader, _seconds_to_srt_time


def test_seconds_to_srt_time():
    assert _seconds_to_srt_time(0) == "00:00:00,000"
    assert _seconds_to_srt_time(60.5) == "00:01:00,500"
    assert _seconds_to_srt_time(3661.123) == "01:01:01,123"


def test_write_srt_basic():
    entries = [
        {"from": 0.0, "to": 2.0, "content": "Hello"},
        {"from": 3.0, "to": 5.0, "content": "World"},
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        path = Path(f.name)

    SubtitleDownloader._write_srt(entries, path)
    content = path.read_text(encoding="utf-8")
    path.unlink()

    assert "1\n00:00:00,000 --> 00:00:02,000\nHello" in content
    assert "2\n00:00:03,000 --> 00:00:05,000\nWorld" in content


def test_write_srt_empty_content_skipped():
    entries = [
        {"from": 0.0, "to": 2.0, "content": ""},
        {"from": 3.0, "to": 5.0, "content": "Valid"},
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        path = Path(f.name)

    SubtitleDownloader._write_srt(entries, path)
    content = path.read_text(encoding="utf-8")
    path.unlink()

    assert "Valid" in content
    assert content.startswith("1\n")
    assert "\n2\n" not in content
    # Empty content entry should be skipped
    assert content.count("\n\n") <= 2  # Only one valid entry
