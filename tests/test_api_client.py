"""Tests for resilient Bilibili API response parsing."""

import httpx
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
    BilibiliAPIError,
    _build_fnval,
    _parse_playurl,
)
from bilibili_downloader.core.models import VideoInfo, VideoQuality
from bilibili_downloader.core.resolve_control import ResolveControl


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
    client._resolve_control = ResolveControl()
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
    assert collection.errors == []


@pytest.mark.parametrize(
    "error",
    [
        BilibiliAPIError(-404, "视频不存在"),
        BilibiliAPIError(62002, "稿件不可见"),
        BilibiliAPIError(62004, "稿件审核中"),
        httpx.ReadTimeout("Timed out"),
        httpx.HTTPStatusError(
            "Not found",
            request=httpx.Request("GET", "https://api.bilibili.com/"),
            response=httpx.Response(404),
        ),
    ],
)
def test_favorite_collection_keeps_valid_items_when_one_video_fails(monkeypatch, error):
    from bilibili_downloader.api import endpoints as ep

    first, unavailable, last = "BV1GJ411x7h7", "BV1xx411x7h8", "BV1Q541167Qg"
    pages = [
        {"medias": [{"bvid": first}, {"bvid": unavailable}], "has_more": True},
        {"medias": [{"bvid": unavailable}, {"bvid": last}], "has_more": False},
    ]
    page_calls, video_calls = [], []

    def handle(request):
        assert request.url.path == ep.FAVORITE_LIST_ENDPOINT
        page = int(request.url.params["pn"])
        page_calls.append(page)
        return httpx.Response(
            200,
            json={"code": 0, "data": {"info": {"title": "Favorites"}, **pages[page - 1]}},
        )

    def get_video_info(bvid):
        video_calls.append(bvid)
        if bvid == unavailable:
            raise error
        return VideoInfo(bvid=bvid, title=bvid)

    client = BilibiliAPIClient()
    client._client.close()
    client._client = httpx.Client(
        base_url="https://api.bilibili.com", transport=httpx.MockTransport(handle)
    )
    monkeypatch.setattr(client, "get_video_info", get_video_info)
    try:
        collection = client.get_favorite_collection(123, "https://example")
    finally:
        client.close()

    assert page_calls == [1, 2]
    assert video_calls == [first, unavailable, last]
    assert [item.bvid for item in collection.items] == [first, last]
    assert all(item.collection_title == "Favorites" for item in collection.items)
    assert all(item.source_url == "https://example" for item in collection.items)
    assert len(collection.errors) == 1
    assert unavailable in collection.errors[0]


def test_collection_reports_all_unavailable_items(monkeypatch):
    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._resolve_control = ResolveControl()

    def get_video_info(_bvid):
        raise BilibiliAPIError(62002, "稿件不可见")

    monkeypatch.setattr(client, "get_video_info", get_video_info)

    collection = client._collection_from_entries(
        "Favorites", "favorite", "", [{"bvid": "BV1GJ411x7h7"}]
    )

    assert collection.items == []
    assert len(collection.errors) == 1
    assert "BV1GJ411x7h7" in collection.errors[0]


def test_collection_cancel_between_videos_preserves_streamed_metadata(monkeypatch):
    from bilibili_downloader.core.resolve_control import ResolveCancelled

    streamed, calls = [], []
    control = ResolveControl(item_ready=streamed.append)
    client = BilibiliAPIClient(resolve_control=control)
    def get_video_info(bvid):
        calls.append(bvid)
        control.cancel.set()
        return VideoInfo(bvid=bvid)
    monkeypatch.setattr(client, "get_video_info", get_video_info)
    try:
        with pytest.raises(ResolveCancelled):
            client._collection_from_entries("收藏夹", "favorite", "https://example", [
                {"bvid": "BV1GJ411x7h7"}, {"bvid": "BV1Q541167Qg"},
            ])
    finally:
        client.close()
    assert calls == ["BV1GJ411x7h7"]
    assert streamed[0].collection_title == "收藏夹"


def test_missing_video_ids_are_counted_as_skipped_items():
    client = BilibiliAPIClient()
    try:
        result = client._collection_from_entries("Favorites", "favorite", "https://example", [{"title": "已失效"}])
    finally:
        client.close()
    assert len(result.failures) == len(result.errors) == 1
    assert result.failures[0].url == "https://example"


def test_favorite_collection_still_raises_when_list_is_inaccessible():
    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._resolve_control = ResolveControl()
    client._client = httpx.Client(
        base_url="https://api.bilibili.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"code": -403, "message": "访问权限不足"}
            )
        ),
    )
    try:
        with pytest.raises(BilibiliAPIError) as exc:
            client.get_favorite_collection(123)
    finally:
        client.close()

    assert exc.value.code == -403


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
    client._resolve_control = ResolveControl()
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
