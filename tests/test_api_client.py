"""Tests for resilient Bilibili API response parsing."""

from bilibili_downloader.api.client import _parse_playurl


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
