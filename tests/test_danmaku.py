"""Tests for danmaku converter."""

import tempfile
from pathlib import Path

from bilibili_downloader.core.danmaku import DanmakuDownloader, _seconds_to_ass_time
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
    from bilibili_downloader.core.danmaku import _mode_to_style, _mode_to_effect

    assert _mode_to_style("1") == "Scroll"
    assert _mode_to_style("3") == "Bottom"
    assert _mode_to_style("4") == "Top"
    assert _mode_to_style("5") == "Fixed"

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

    assert "{\\c&H000000FF}" in content
