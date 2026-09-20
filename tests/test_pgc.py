"""Fixture-based tests for mainland Bilibili PGC parsing and access checks."""

import json

import pytest

from bilibili_downloader.api import endpoints
from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.api.pgc import (
    BangumiAccessError,
    BangumiAccessReason,
    normalize_pgc_playurl,
    parse_bangumi_collection,
)
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.models import (
    ContentKind,
    DownloadItem,
    VideoInfo,
    VideoQuality,
)


def _season_fixture():
    return {
        "season_id": 22,
        "media_id": 33,
        "title": "第一季",
        "series": {"series_title": "示例番剧"},
        "episodes": [
            {
                "id": 101,
                "aid": 201,
                "bvid": "BV1GJ411x7h7",
                "cid": 301,
                "title": "1",
                "long_title": "启程",
                "duration": 1_440_000,
            },
            {
                "id": 102,
                "aid": 202,
                "bvid": "BV1xx411x7h8",
                "cid": 302,
                "title": "2",
                "long_title": "再会",
            },
        ],
        "section": [
            {
                "title": "PV",
                "episodes": [
                    {"id": 103, "aid": 203, "cid": 303, "title": "PV1"}
                ],
            },
            {
                "title": "花絮",
                "episodes": [
                    {"id": 104, "aid": 204, "cid": 304, "title": "幕后"}
                ],
            },
        ],
    }


def _video_info():
    return {
        "dash": {
            "video": [{"id": 80, "base_url": "https://cdn/video"}],
            "audio": [{"id": 30280, "base_url": "https://cdn/audio"}],
        }
    }


def test_season_parser_orders_main_before_extras_and_marks_defaults():
    collection = parse_bangumi_collection(
        _season_fixture(), "https://www.bilibili.com/bangumi/play/ss22"
    )

    assert collection.source_type == "bangumi_season"
    assert [item.episode_id for item in collection.items] == [101, 102, 103, 104]
    assert [item.is_main_section for item in collection.items] == [True, True, False, False]
    assert collection.items[0].content_identity == "ep:101:301"
    assert collection.items[0].duration == 1440
    assert collection.items[0].episode_number == "01"
    assert collection.items[2].episode_number == "01"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "code": 0,
            "result": {
                "play_check": {"play_video_type": "PLAY_WHOLE"},
                "video_info": _video_info(),
            },
        },
        {
            "code": 0,
            "data": {
                "result": {
                    "play_video_type": "whole",
                    "video_info": _video_info(),
                }
            },
        },
        {
            "raw": {
                "code": 0,
                "data": {
                    "play_detail": {"play_video_type": "PLAY_WHOLE"},
                    "video_info": _video_info(),
                },
            }
        },
    ],
)
def test_playurl_normalizer_supports_known_response_nesting(payload):
    normalized, _code = normalize_pgc_playurl(payload)
    assert normalized["dash"]["video"][0]["id"] == 80


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"code": -101}, BangumiAccessReason.LOGIN_REQUIRED),
        ({"code": -10403}, BangumiAccessReason.FULL_ACCESS_REQUIRED),
        (
            {
                "code": 0,
                "result": {
                    "play_video_type": "PLAY_PREVIEW",
                    "video_info": _video_info(),
                },
            },
            BangumiAccessReason.PREVIEW_ONLY,
        ),
        (
            {
                "code": 0,
                "result": {
                    "plugins": [
                        {"name": "AreaLimitPanel", "config": {"is_block": True}}
                    ],
                    "video_info": _video_info(),
                },
            },
            BangumiAccessReason.GEO_BLOCKED,
        ),
        (
            {
                "code": 0,
                "result": {
                    "play_video_type": "PLAY_WHOLE",
                    "video_info": {"dash": {}},
                },
            },
            BangumiAccessReason.UNAVAILABLE,
        ),
    ],
)
def test_playurl_normalizer_rejects_non_downloadable_access(payload, reason):
    with pytest.raises(BangumiAccessError) as exc_info:
        normalize_pgc_playurl(payload)
    assert exc_info.value.reason == reason


def test_preview_failure_creates_no_media_or_resume_files(tmp_path):
    class PreviewAPI:
        def get_play_url_for(self, *_args, **_kwargs):
            raise BangumiAccessError(BangumiAccessReason.PREVIEW_ONLY)

    info = VideoInfo(
        content_kind=ContentKind.BANGUMI_EPISODE,
        episode_id=101,
        cid=301,
        title="试看",
    )
    downloader = StreamDownloader(PreviewAPI(), str(tmp_path))

    with pytest.raises(BangumiAccessError):
        downloader.download(DownloadItem(video_info=info), lambda *_args: None)

    assert not (tmp_path / ".biliflow-parts").exists()
    assert list(tmp_path.rglob("*.m4s")) == []


def test_api_client_uses_pgc_endpoint_and_episode_referer():
    calls = []

    class Response:
        content = b"{}"
        text = "{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "code": 0,
                "result": {
                    "play_video_type": "PLAY_WHOLE",
                    "video_info": _video_info(),
                },
            }

    class HTTP:
        def get(self, endpoint, params=None, headers=None):
            calls.append((endpoint, params, headers))
            return Response()

    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._client = HTTP()
    info = VideoInfo(
        content_kind=ContentKind.BANGUMI_EPISODE,
        episode_id=101,
        cid=301,
    )

    streams = client.get_pgc_play_url(info, VideoQuality.Q1080P)

    assert calls[0][0] == endpoints.PGC_PLAYURL_ENDPOINT
    assert calls[0][1]["ep_id"] == 101
    assert calls[0][2]["Referer"].endswith("/ep101")
    assert streams["video_streams"][0].id == 80


def test_media_page_reads_bounded_initial_state_then_resolves_season():
    class Response:
        def __init__(self, *, payload=None, text=""):
            self._payload = payload
            self.text = text
            self.content = text.encode("utf-8")

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class HTTP:
        def get(self, endpoint, params=None):
            if str(endpoint).endswith("/bangumi/media/md33"):
                state = json.dumps({"mediaInfo": {"season_id": 22}})
                return Response(text=f"window.__INITIAL_STATE__={state};")
            assert endpoint == endpoints.PGC_SEASON_ENDPOINT
            assert params == {"season_id": 22}
            return Response(payload={"code": 0, "result": _season_fixture()})

    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._client = HTTP()

    collection = client.get_bangumi_media(33)

    assert collection.source_url.endswith("/md33")
    assert collection.items[0].season_id == 22
    assert collection.items[0].media_id == 33


def test_pgc_playurl_uses_authorized_page_fallback_when_api_has_no_dash():
    calls = []

    class Response:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text
            self.content = text.encode("utf-8")

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class HTTP:
        def get(self, endpoint, params=None, headers=None):
            calls.append(endpoint)
            if endpoint == endpoints.PGC_PLAYURL_ENDPOINT:
                return Response(
                    {
                        "code": 0,
                        "result": {
                            "play_video_type": "PLAY_WHOLE",
                            "video_info": {"dash": {}},
                        },
                    }
                )
            page_data = json.dumps(
                {
                    "play_video_type": "PLAY_WHOLE",
                    "video_info": _video_info(),
                }
            )
            return Response(text=f"window.__playurlSSRData__={page_data};")

    client = BilibiliAPIClient.__new__(BilibiliAPIClient)
    client._client = HTTP()
    info = VideoInfo(
        content_kind=ContentKind.BANGUMI_EPISODE,
        episode_id=101,
        cid=301,
    )

    streams = client.get_pgc_play_url(info)

    assert calls == [endpoints.PGC_PLAYURL_ENDPOINT, info.canonical_url]
    assert streams["audio_streams"][0].id == 30280
