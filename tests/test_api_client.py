"""Tests for resilient Bilibili API response parsing."""

import pytest

from bilibili_downloader.api.client import (
    FNVAL_4K,
    FNVAL_8K,
    FNVAL_AV1,
    FNVAL_DASH,
    FNVAL_DOLBY_AUDIO,
    FNVAL_DOLBY_VIDEO,
    FNVAL_HDR,
    _build_fnval,
    _parse_playurl,
)
from bilibili_downloader.core.models import VideoQuality


def test_parse_playurl_supports_camel_case_and_premium_audio():
    parsed = _parse_playurl({
        "dash": {
            "video": [{
                "id": 80,
                "baseUrl": "https://cdn/video",
                "backupUrl": ["https://backup/video"],
                "mimeType": "video/mp4",
                "codecid": 12,
            }],
            "audio": None,
            "dolby": {
                "audio": [{
                    "id": 30250,
                    "baseUrl": "https://cdn/dolby",
                    "mimeType": "audio/mp4",
                }],
            },
            "flac": {
                "audio": {
                    "id": 30251,
                    "base_url": "https://cdn/flac",
                },
            },
        },
    })

    assert parsed["video_streams"][0].base_url == "https://cdn/video"
    assert parsed["video_streams"][0].backup_url == ["https://backup/video"]
    assert [stream.id for stream in parsed["audio_streams"]] == [30250, 30251]


def test_parse_playurl_accepts_missing_dash():
    parsed = _parse_playurl({"dash": None})

    assert parsed["video_streams"] == []
    assert parsed["audio_streams"] == []


def test_parse_playurl_ignores_malformed_stream_entries():
    parsed = _parse_playurl({
        "dash": {"video": [None], "audio": [None], "dolby": None}
    })

    assert parsed["video_streams"] == []
    assert parsed["audio_streams"] == []


@pytest.mark.parametrize(
    ("quality", "codec", "expected"),
    [
        (VideoQuality.Q1080P, 7, FNVAL_DASH),
        (VideoQuality.Q4K, 12, FNVAL_DASH | FNVAL_4K),
        (VideoQuality.QHDR, 12, FNVAL_DASH | FNVAL_HDR),
        (
            VideoQuality.Q_DOLBY,
            12,
            FNVAL_DASH | FNVAL_DOLBY_AUDIO | FNVAL_DOLBY_VIDEO,
        ),
        (VideoQuality.Q8K, 13, FNVAL_DASH | FNVAL_8K | FNVAL_AV1),
    ],
)
def test_build_fnval_requests_only_needed_capabilities(quality, codec, expected):
    assert _build_fnval(quality, preferred_codec=codec) == expected


def test_build_fnval_discovery_requests_all_capabilities():
    expected = (
        FNVAL_DASH | FNVAL_HDR | FNVAL_4K | FNVAL_DOLBY_AUDIO
        | FNVAL_DOLBY_VIDEO | FNVAL_8K | FNVAL_AV1
    )
    assert _build_fnval(VideoQuality.Q8K, discover_all=True) == expected


def test_parse_playurl_marks_hdr_quality_not_dolby_as_hdr():
    hdr = _parse_playurl({"dash": {"video": [{"id": 125}]}})
    dolby = _parse_playurl({"dash": {"video": [{"id": 126}]}})

    assert hdr["has_hdr"] is True
    assert dolby["has_hdr"] is False
