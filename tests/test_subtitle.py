"""Tests for subtitle converter."""

import tempfile
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        ("1.001", "00:00:01,001"), ("1.003", "00:00:01,003"),
        ("60.01", "00:01:00,010"), ("59.9995", "00:01:00,000"),
        ("3600.0005", "01:00:00,001"),
    ],
)
def test_srt_quantization_and_time_carry(seconds, expected):
    assert _seconds_to_srt_time(seconds) == expected
    assert _seconds_to_srt_time(float(seconds)) == expected


@pytest.mark.parametrize("seconds", ["NaN", "Infinity", "-0.1", "1e1000", None, True, []])
def test_srt_rejects_invalid_timestamps(seconds):
    with pytest.raises(ValueError):
        _seconds_to_srt_time(seconds)


def test_srt_skips_bad_entries_and_keeps_unicode_in_chronological_order(tmp_path):
    path = tmp_path / "subtitles.srt"
    entries = [
        None, 1, "invalid", {}, {"from": 1, "to": 2, "content": None},
        {"from": 1, "to": 2, "content": 123},
        {"from": "NaN", "to": 2, "content": "bad"},
        {"from": -1, "to": 2, "content": "bad"},
        {"from": 3, "to": 2, "content": "bad"},
        {"from": 1, "to": 1.0001, "content": "too short"},
        {"from": 1, "to": 2, "content": " "},
        {"from": "3.001", "to": 4, "content": r"字面量 \N \h {花括号}"},
        {"from": "1.001", "to": 2, "content": "中文😀 é 👨‍👩‍👧‍👦\r\n\r\n第二行\x00"},
        {"from": 5, "to": 6, "content": "坏代理项\ud800结束"},
    ]
    report = SubtitleDownloader._write_srt(entries, path)
    content = path.read_text(encoding="utf-8")
    assert report.exported == 3
    assert report.invalid == 11
    assert report.normalized == 2
    assert content.startswith("1\n00:00:01,001 --> 00:00:02,000\n中文😀 é 👨‍👩‍👧‍👦\n第二行\n\n")
    assert r"字面量 \N \h {花括号}" in content
    assert "坏代理项�结束" in content
    assert "\r" not in content and "\x00" not in content
    assert content.count("\n\n") == 3


def test_srt_invalid_payload_and_io_failure_preserve_existing_export(tmp_path, monkeypatch):
    path = tmp_path / "existing.srt"
    path.write_text("previous subtitles")
    with pytest.raises(ValueError, match="列表"):
        SubtitleDownloader._write_srt({"invalid": True}, path)
    assert path.read_text() == "previous subtitles"

    def fail(*_args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("bilibili_downloader.core.timed_text.os.replace", fail)
    with pytest.raises(OSError, match="disk unavailable"):
        SubtitleDownloader._write_srt([{"from": 0, "to": 1, "content": "new"}], path)
    assert path.read_text() == "previous subtitles"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "entries",
    [[], [{"from": 1, "to": 0, "content": "bad"}], [{"from": 0, "to": 1, "content": ""}]],
)
def test_no_valid_cues_preserve_existing_subtitles(tmp_path, entries):
    path = tmp_path / "existing.srt"
    path.write_text("previous subtitles")
    with pytest.raises(ValueError, match="没有有效内容"):
        SubtitleDownloader._write_srt(entries, path)
    assert path.read_text() == "previous subtitles"
