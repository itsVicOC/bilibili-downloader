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
    BilibiliAPIClient,
    _build_fnval,
    _parse_playurl,
)
from bilibili_downloader.core.models import VideoInfo, VideoQuality


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


def test_favorite_collection_reads_all_pages_and_hydrates(monkeypatch):
    pages = [
        {
            "info": {"title": "My favorites"},
            "medias": [{"bvid": "BV1GJ411x7h7"}],
            "has_more": True,
        },
        {
            "info": {"title": "My favorites"},
            "medias": [{"bvid": "BV1xx411x7h8"}],
            "has_more": False,
        },
    ]
    calls = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "data": self._payload}

    class HTTP:
        def get(self, _endpoint, params):
            calls.append(params["pn"])
            return Response(pages[params["pn"] - 1])

    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._client = HTTP()
    monkeypatch.setattr(
        client,
        "get_video_info",
        lambda bvid: VideoInfo(bvid=bvid, title=bvid),
    )

    collection = client.get_favorite_collection(123, "https://example")

    assert calls == [1, 2]
    assert collection.title == "My favorites"
    assert [item.bvid for item in collection.items] == [
        "BV1GJ411x7h7",
        "BV1xx411x7h8",
    ]
    assert all(item.collection_title == "My favorites" for item in collection.items)


def test_series_and_season_collections_read_all_pages(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "data": self._payload}

    class HTTP:
        def get(self, endpoint, params):
            page = params.get("pn", params.get("page_num"))
            calls.append((endpoint, page))
            bvid = "BV1GJ411x7h7" if page == 1 else "BV1xx411x7h8"
            return Response(
                {
                    "archives": [{"bvid": bvid}],
                    "page": {"total": 2},
                    "meta": {"name": "Archive"},
                }
            )

    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._client = HTTP()
    monkeypatch.setattr(
        client,
        "get_video_info",
        lambda bvid: VideoInfo(bvid=bvid, title=bvid),
    )

    series = client.get_series_collection(1, 2)
    season = client.get_season_collection(1, 2)

    assert [item.bvid for item in series.items] == [
        "BV1GJ411x7h7",
        "BV1xx411x7h8",
    ]
    assert [item.bvid for item in season.items] == [
        "BV1GJ411x7h7",
        "BV1xx411x7h8",
    ]
    assert [page for _endpoint, page in calls] == [1, 2, 1, 2]
