"""Tests for danmaku converter."""

import re
import tempfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from bilibili_downloader.core.danmaku import (
    FONT_FAMILY,
    DanmakuDownloader,
    _seconds_to_ass_time,
)
from bilibili_downloader.core.subtitle import _seconds_to_srt_time


def test_seconds_to_ass_time():
    assert _seconds_to_ass_time(0) == "0:00:00.00"
    assert _seconds_to_ass_time(65.5) == "0:01:05.50"
    assert _seconds_to_ass_time(3661.25) == "1:01:01.25"


def test_seconds_to_srt_time():
    assert _seconds_to_srt_time(0) == "00:00:00,000"
    assert _seconds_to_srt_time(65.5) == "00:01:05,500"
    assert _seconds_to_srt_time(3661.25) == "01:01:01,250"


def test_xml_to_ass_basic():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<i>
  <d p="1.0,1,25,16777215,1234567890,0,abcdef01,Hello">Hello</d>
  <d p="5.0,3,25,65280,1234567890,0,abcdef01,World">World</d>
</i>"""

    with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
        path = Path(f.name)

    DanmakuDownloader.xml_to_ass(xml, path)

    content = path.read_text(encoding="utf-8")
    path.unlink()

    assert "[Script Info]" in content
    assert "[Events]" in content
    assert "Hello" in content
    assert "World" in content
    assert "Scroll" in content  # mode 1 = scroll


def test_danmaku_mode_mapping():
    from bilibili_downloader.core.danmaku import _mode_to_effect, _mode_to_style

    assert _mode_to_style("1") == "Scroll"
    assert _mode_to_style("3") == "Scroll"
    assert _mode_to_style("4") == "Bottom"
    assert _mode_to_style("5") == "Top"
    assert _mode_to_style("6") == "Reverse"
    assert "\\move" in _mode_to_effect("1")
    assert _mode_to_effect("5") == ""


def test_xml_to_ass_rgb_color_order():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<i>
  <d p="1.0,1,25,16711680,1234567890,0,abcdef01,Red">Red</d>
</i>"""

    with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
        path = Path(f.name)

    DanmakuDownloader.xml_to_ass(xml, path)
    content = path.read_text(encoding="utf-8")
    path.unlink()

    assert r"\c&H0000FF&\fs25}" in content


@pytest.mark.parametrize(
    ("mode", "style"),
    [
        (1, "Scroll"),
        (2, "Scroll"),
        (3, "Scroll"),
        (4, "Bottom"),
        (5, "Top"),
        (6, "Reverse"),
    ],
)
def test_ass_motion_is_inside_text_override_not_effect(tmp_path, mode, style):
    xml = (
        f'<i><d p="1.5,{mode},25,16711680,0,0,hash,1">'
        '重温经典, Hello, world</d></i>'
    ).encode()
    path = tmp_path / "danmaku.ass"
    DanmakuDownloader.xml_to_ass(xml, path)
    event = next(line for line in path.read_text().splitlines() if line.startswith("Dialogue: "))
    fields = event.removeprefix("Dialogue: ").split(",", 9)
    assert len(fields) == 10
    assert fields[:4] == [
        "0", "0:00:01.50", "0:00:05.50" if mode in (4, 5) else "0:00:09.50", style
    ]
    assert fields[4:9] == ["", "0", "0", "0", ""]
    tags, text = fields[9].split("}", 1)
    assert tags.startswith(r"{\an7\q2")
    assert tags.endswith(r"\c&H0000FF&\fs25")
    assert text == "重温经典, Hello, world"
    if mode in (4, 5):
        x, y = map(int, re.search(r"\\pos\((\d+),(\d+)\)", tags).groups())
        assert 0 < x < 1920
        assert y > 540 if mode == 4 else y < 540
    else:
        x1, y1, x2, y2 = map(int, re.search(r"\\move\((-?\d+),(\d+),(-?\d+),(\d+)\)", tags).groups())
        assert y1 == y2 and y1 > 0
        assert x1 < 0 and x2 > 1920 if mode == 6 else x1 > 1920 and x2 < 0


def test_ass_fixed_modes_have_correct_vertical_alignment(tmp_path):
    path = tmp_path / "danmaku.ass"
    DanmakuDownloader.xml_to_ass(
        b'<i><d p="1,5,25,16777215,0,0,h,1">Top</d></i>', path
    )
    lines = path.read_text().splitlines()
    style_format = next(line for line in lines if line.startswith("Format: Name,"))
    columns = style_format.removeprefix("Format: ").split(", ")
    styles = {
        fields[0]: dict(zip(columns, fields))
        for line in lines if line.startswith("Style: ")
        for fields in [line.removeprefix("Style: ").split(",")]
    }
    assert styles["Top"]["Alignment"] == "8"
    assert styles["Bottom"]["Alignment"] == "2"


@pytest.mark.parametrize(
    ("color", "outline"), [(0, "FFFFFF"), (0x202020, "FFFFFF"), (0xFFFFFF, "000000")]
)
def test_dark_and_light_danmaku_have_contrasting_outlines(tmp_path, color, outline):
    _report, _content, events = _convert(tmp_path, [
        (f"1,5,25,{color},0,0,h,1", "清晰可见"),
    ])
    assert f"\\3c&H{outline}&" in events[0][9]


def _convert(tmp_path, entries):
    root = Element("i")
    for fields, text in entries:
        node = SubElement(root, "d", p=fields)
        node.text = text
    path = tmp_path / "converted.ass"
    report = DanmakuDownloader.xml_to_ass(tostring(root, encoding="utf-8"), path)
    content = path.read_text(encoding="utf-8")
    events = [
        line.removeprefix("Dialogue: ").split(",", 9)
        for line in content.split("\n") if line.startswith("Dialogue: ")
    ]
    return report, content, events


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"C:\abc", r"C:\abc"),
        (r"C:\new", "C:\\\u2060new"),
        (r"Hello\NWorld", "Hello\\\u2060NWorld"),
        (r"Hello\hWorld", "Hello\\\u2060hWorld"),
        (r"\\N", "\\\\\u2060N"),
        ("第一行\r\n第二行", r"第一行\N第二行"),
        (r"{\pos(0,0)}正文", r"｛\pos(0,0)｝正文"),
        ("  中文 & English, 😀 👨‍👩‍👧‍👦 é 🇨🇳  ", "  中文 & English, 😀 👨‍👩‍👧‍👦 é 🇨🇳  "),
    ],
)
def test_ass_literal_text_and_unicode_are_not_interpreted_as_tags(tmp_path, text, expected):
    report, content, events = _convert(tmp_path, [("1,5,25,16777215,0,0,h,1", text)])
    assert report.exported == 1
    assert events[0][9].split("}", 1)[1] == expected
    assert report.normalized == (1 if "{" in text or "}" in text else 0)
    assert f",{FONT_FAMILY}," in content


@pytest.mark.parametrize("timestamp", ["1.13", "1.14", "9.10", "60.01", "59.995"])
def test_ass_times_quantize_once_without_float_truncation(timestamp):
    expected = {
        "1.13": "0:00:01.13", "1.14": "0:00:01.14", "9.10": "0:00:09.10",
        "60.01": "0:01:00.01", "59.995": "0:01:00.00",
    }
    assert _seconds_to_ass_time(timestamp) == expected[timestamp]
    assert _seconds_to_ass_time(float(timestamp)) == expected[timestamp]


def test_invalid_and_unsupported_comments_do_not_abort_valid_export(tmp_path):
    entries = [
        (f"{time},1,25,16777215,0,0,h,1", "bad")
        for time in ("NaN", "inf", "-1", "1e1000", "not-a-time")
    ] + [
        ("1,1,25,-1,0,0,h,1", "bad"),
        ("1,1,25,16777216,0,0,h,1", "bad"),
        ("1,1,25,16777215,0,0,h,1", " "),
        ("1,1,25,16777215,0,0,h,1", "字" * 4097),
        ("broken", "bad"),
    ] + [
        (f"1,{mode},25,16777215,0,0,h,1", '{"payload":"special"}')
        for mode in (7, 8, 9, 99)
    ] + [("2,1,25,16777215,0,0,h,2", "正常😀")]
    report, _content, events = _convert(tmp_path, entries)
    assert report.exported == len(events) == 1
    assert report.invalid == 10
    assert report.unsupported == 4
    assert events[0][9].endswith("正常😀")
    assert len(report.warnings("弹幕")) == 2


def test_export_sorts_times_and_reuses_tracks_without_chasing_or_crossing(tmp_path):
    entries = [
        ("0.5,1,25,16777215,0,0,h,2", "短句"),
        ("0,1,25,16777215,0,0,h,1", "短句"),
        ("0.6,1,72,16777215,0,0,h,3", "追上前面的长弹幕" * 8),
        ("0.7,6,25,16777215,0,0,h,4", "反向弹幕"),
    ]
    report, _content, events = _convert(tmp_path, entries)
    coordinates = [
        tuple(map(int, re.search(r"\\move\((-?\d+),(\d+),(-?\d+),(\d+)\)", event[9]).groups()))
        for event in events
    ]
    assert [event[1] for event in events] == [
        "0:00:00.00", "0:00:00.50", "0:00:00.60", "0:00:00.70"
    ]
    assert coordinates[0][1] == coordinates[1][1]
    assert coordinates[2][1] != coordinates[0][1]
    assert coordinates[3][1] != coordinates[0][1]
    assert report.crowded == 0


def test_long_comments_wrap_without_splitting_emoji_and_have_safe_boundaries(tmp_path):
    text = ("👨‍👩‍👧‍👦🇨🇳é" * 25) + "A" * 200
    report, _content, events = _convert(tmp_path, [("1,1,72,16777215,0,0,h,1", text)])
    payload = events[0][9].split("}", 1)[1]
    lines = payload.split(r"\N")
    assert "".join(lines) == text
    assert len(lines) > 1
    assert all(not line.endswith("\u200d") for line in lines)
    assert all(not line.startswith("\u0301") for line in lines)
    x1, y1, x2, y2 = map(int, re.search(r"\\move\((-?\d+),(\d+),(-?\d+),(\d+)\)", events[0][9]).groups())
    assert x1 > 1920 and x2 < -1000
    assert 0 < y1 == y2 < 1080
    assert report.exported == 1


def test_crowded_comments_keep_original_text_and_times_with_a_warning(tmp_path):
    entries = [
        ("1,1,72,16777215,0,0,h,1", f"密集弹幕 {index}")
        for index in range(600)
    ]
    report, _content, events = _convert(tmp_path, entries)
    assert len(events) == report.exported == 600
    assert {event[1] for event in events} == {"0:00:01.00"}
    assert report.crowded > 0
    assert "已保留原时间与正文" in " ".join(report.warnings("弹幕"))


def test_large_multiline_comment_shrinks_to_fit_without_losing_text(tmp_path):
    text = "字" * 2000
    report, _content, events = _convert(tmp_path, [("1,5,72,16777215,0,0,h,1", text)])
    tags, payload = events[0][9].split("}", 1)
    assert payload.replace(r"\N", "") == text
    assert int(re.search(r"\\fs(\d+)", tags).group(1)) < 72
    assert report.exported == 1 and report.normalized == 1


def test_fixed_and_moving_comments_share_collision_aware_tracks(tmp_path):
    _report, _content, events = _convert(tmp_path, [
        ("0,5,25,16777215,0,0,h,1", "固定顶部"),
        ("0,5,72,16777215,0,0,h,2", "另一个固定顶部"),
        ("0,4,25,16777215,0,0,h,3", "固定底部"),
        ("0,1,25,16777215,0,0,h,4", "经过固定文字"),
    ])
    positions = [
        tuple(map(int, re.search(r"\\pos\((\d+),(\d+)\)", event[9]).groups()))
        for event in events[:3]
    ]
    assert positions[0][1] < positions[1][1] < 540
    assert positions[2][1] > 540
    moving_y = int(re.search(r"\\move\(-?\d+,(\d+)", events[3][9]).group(1))
    assert moving_y > positions[1][1]


def test_ass_failed_publication_preserves_existing_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "existing.ass"
    path.write_text("previous valid export")

    def fail(*_args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("bilibili_downloader.core.timed_text.os.replace", fail)
    with pytest.raises(OSError, match="disk unavailable"):
        DanmakuDownloader.xml_to_ass(
            b'<i><d p="1,1,25,16777215,0,0,h,1">valid</d></i>', path
        )
    assert path.read_text() == "previous valid export"
    assert list(tmp_path.iterdir()) == [path]


def test_malformed_xml_preserves_existing_export(tmp_path):
    path = tmp_path / "existing.ass"
    path.write_text("previous valid export")
    with pytest.raises(RuntimeError, match="parse"):
        DanmakuDownloader.xml_to_ass(b"<i><d>", path)
    assert path.read_text() == "previous valid export"


@pytest.mark.parametrize(
    "xml",
    [
        b"<i/>",
        b'<i><d p="NaN,1,25,16777215,0,0,h,1">bad</d></i>',
        b'<i><d p="1,9,25,16777215,0,0,h,1">special</d></i>',
    ],
)
def test_no_convertible_comments_preserve_existing_export(tmp_path, xml):
    path = tmp_path / "existing.ass"
    path.write_text("previous valid export")
    with pytest.raises(ValueError, match="没有可导出"):
        DanmakuDownloader.xml_to_ass(xml, path)
    assert path.read_text() == "previous valid export"
    assert list(tmp_path.iterdir()) == [path]
