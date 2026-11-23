"""Daily ranking data, request boundaries, and partial-feed behavior."""

import json
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import Mock

import httpx
import pytest

from bilibili_downloader.api.client import BilibiliAPIClient, BilibiliAPIError
from bilibili_downloader.core import daily_rankings as rankings

TODAY = datetime(2026, 11, 23, 17, tzinfo=rankings.BEIJING)
START = int(TODAY.replace(hour=0).timestamp())


def bvid(number):
    return f"BV{number:010}"


def video_item(number, play, *, published_at=START, followed=True, kind="DYNAMIC_TYPE_AV"):
    return {
        "type": kind,
        "modules": {
            "module_author": {"following": followed, "pub_ts": published_at, "name": "作者"},
            "module_dynamic": {"major": {"archive": {
                "bvid": bvid(number), "title": f"作品 {number}", "stat": {"play": play},
            }}},
        },
    }


@pytest.mark.parametrize("failure", ["network", "rate_limit"])
def test_public_snapshot_keeps_upstream_order_and_rolls_over_at_beijing_midnight(tmp_path, monkeypatch, failure):
    elapsed = datetime(2026, 11, 23, 15, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(rankings, "beijing_now", lambda: elapsed.astimezone(rankings.BEIJING))
    fetch = Mock(return_value={"list": [
        {"bvid": bvid(n), "title": f"作品 {n}", "stat": {"view": n}} for n in range(105)
    ]})
    monkeypatch.setattr(BilibiliAPIClient, "get_video_ranking", fetch)
    path = tmp_path / "rankings.json"
    first = rankings.load_public_ranking(path)
    assert [entry.bvid for entry in first.snapshot.videos] == [bvid(n) for n in range(100)]
    assert rankings.load_public_ranking(path) == first
    fetch.assert_called_once()

    elapsed += timedelta(minutes=1)
    if failure == "rate_limit":
        request = httpx.Request("GET", "https://api.bilibili.com/")
        response = httpx.Response(429, request=request)
        fetch.side_effect = httpx.HTTPStatusError("rate limited", request=request, response=response)
    else:
        fetch.side_effect = httpx.ReadTimeout("timed out")
    stale = rankings.load_public_ranking(path)
    assert stale.snapshot == first.snapshot
    assert stale.stale
    assert "重试" in stale.message
    if failure == "rate_limit":
        assert "限制" in stale.message
    assert fetch.call_count == 2

    fetch.side_effect = None
    refreshed = rankings.load_public_ranking(path)
    assert refreshed.snapshot.day == first.snapshot.day + timedelta(days=1)
    assert rankings.load_public_ranking(path) == refreshed
    assert fetch.call_count == 3


def test_upgrade_refreshes_even_a_same_day_top_ten_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(rankings, "beijing_now", lambda: TODAY)
    path = tmp_path / "rankings.json"
    path.write_text(json.dumps({
        "fetched_at": TODAY.isoformat(),
        "videos": [{"bvid": bvid(1), "title": "旧快照", "author": "", "play_text": ""}],
    }), encoding="utf-8")
    fetch = Mock(side_effect=[
        httpx.ReadTimeout("timed out"),
        {"list": [{"bvid": bvid(2), "title": "新快照"}]},
    ])
    monkeypatch.setattr(BilibiliAPIClient, "get_video_ranking", fetch)
    fallback = rankings.load_public_ranking(path)
    assert fallback.stale and fallback.snapshot.videos[0].bvid == bvid(1)
    updated = rankings.load_public_ranking(path)
    assert not updated.stale and updated.snapshot.videos[0].bvid == bvid(2)
    assert rankings.load_public_ranking(path) == updated
    assert fetch.call_count == 2


def test_api_separates_public_and_authenticated_requests(monkeypatch):
    def handle(request):
        if request.url.path.endswith("/ranking/v2"):
            assert dict(request.url.params) == {"rid": "0", "type": "all", "web_location": "333.934"}
            assert "cookie" not in request.headers
            return httpx.Response(200, json={"code": 0, "data": {"list": []}})
        assert request.url.path.endswith("/feed/all")
        assert request.url.host == "api.bilibili.com"
        assert request.headers["cookie"] == "SESSDATA=test-session"
        assert request.url.params["type"] == "video"
        assert request.url.params["offset"] == "next"
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})

    actual_client = httpx.Client
    def mock_client(**kwargs):
        return actual_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(httpx, "Client", mock_client)
    api = BilibiliAPIClient(sessdata="test-session")
    try:
        assert api.get_video_ranking() == {"list": []}
        assert api.get_following_video_feed("next") == {"items": [], "has_more": False}
    finally:
        api.close()


def test_following_includes_older_videos_and_supports_both_sort_orders(monkeypatch):
    monkeypatch.setattr(rankings, "beijing_now", lambda: TODAY)
    client = Mock()
    client.get_following_video_feed.side_effect = [
        {"has_more": True, "offset": "next", "items": [
            video_item(0, "1亿", published_at=START - 1),
            video_item(1, "1.01万"),
            video_item(2, "10100", published_at=str(START + 1)),
            video_item(3, "7.9万", followed=False),
            video_item(4, "2亿", kind="DYNAMIC_TYPE_FORWARD"),
        ]},
        {"has_more": False, "items": [
            video_item(1, "1万"),
            video_item(5, "0.1亿"),
            video_item(6, 9000),
            video_item(7, "--"),
            video_item(8, "2亿", published_at=str(START + 86400)),
            video_item(9, "3亿", published_at="刚刚"),
        ]},
    ]
    result = rankings.load_following_ranking(client, Event())
    videos = result.snapshot.videos
    assert [entry.bvid for entry in rankings.rank_following_videos(videos)] == [
        bvid(2), bvid(5), bvid(1), bvid(6), bvid(0),
    ]
    assert [(entry.bvid, entry.play_text) for entry in rankings.rank_following_videos(videos, by_plays=True)] == [
        (bvid(0), "1亿"), (bvid(5), "0.1亿"), (bvid(2), "10100"), (bvid(1), "1.01万"), (bvid(6), "9000"),
    ]
    assert "可用的播放量" in result.message and "可用的发布时间" in result.message
    assert [call.args[0] for call in client.get_following_video_feed.call_args_list] == ["", "next"]


def test_following_ranks_across_all_five_pages_before_taking_top_100(monkeypatch):
    monkeypatch.setattr(rankings, "beijing_now", lambda: TODAY)
    client = Mock()
    client.get_following_video_feed.side_effect = [
        {"has_more": True, "offset": str(page), "items": [
            video_item(n, n) for n in range(page * 21, (page + 1) * 21)
        ]}
        for page in range(5)
    ]
    result = rankings.load_following_ranking(client, Event())
    assert [video.bvid for video in rankings.rank_following_videos(result.snapshot.videos, by_plays=True)] == [
        bvid(n) for n in range(104, 4, -1)
    ]
    assert client.get_following_video_feed.call_count == 5
    assert not result.message


@pytest.mark.parametrize("stop", ["last", "limit", "duplicate", "network", "rate_limit", "expired"])
def test_following_bounds_pagination_and_distinguishes_partial_results(stop, monkeypatch):
    monkeypatch.setattr(rankings, "beijing_now", lambda: TODAY)
    client = Mock()
    first = {"has_more": True, "offset": "first", "items": [video_item(1, 10)]}
    if stop == "last":
        client.get_following_video_feed.return_value = {"has_more": False, "items": []}
        expected_calls, message = 1, ""
    elif stop == "limit":
        client.get_following_video_feed.side_effect = [
            {"has_more": True, "offset": str(n), "items": [video_item(n, 10)]}
            for n in range(10)
        ]
        expected_calls, message = 5, ""
    else:
        next_page = {
            "duplicate": first,
            "network": httpx.ReadTimeout("timed out"),
            "rate_limit": BilibiliAPIError(-352, "try later"),
            "expired": BilibiliAPIError(-101, "requires login"),
        }[stop]
        client.get_following_video_feed.side_effect = [first, next_page]
        expected_calls, message = 2, {
            "duplicate": "第 2 页", "network": "中断", "rate_limit": "限制", "expired": "登录",
        }[stop]
    result = rankings.load_following_ranking(client, Event())
    assert client.get_following_video_feed.call_count == expected_calls
    if message:
        assert message in result.message
    else:
        assert not result.message
    if stop == "expired":
        assert result.login_required and result.snapshot is None
    else:
        assert len(result.snapshot.videos) == (0 if stop == "last" else 5 if stop == "limit" else 1)


def test_following_discards_work_that_crossed_midnight(monkeypatch):
    times = iter([TODAY, TODAY + timedelta(days=1)])
    monkeypatch.setattr(rankings, "beijing_now", lambda: next(times))
    client = Mock()
    client.get_following_video_feed.return_value = {"has_more": False, "items": [video_item(1, 20)]}
    result = rankings.load_following_ranking(client, Event())
    assert result.snapshot is None
    assert "跨天" in result.message
