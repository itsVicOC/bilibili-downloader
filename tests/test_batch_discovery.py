"""Bilibili response contracts for account-scoped batch import sources."""

from threading import Event

import httpx

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core import batch_discovery
from bilibili_downloader.core.batch_discovery import BatchSource


def use_transport(monkeypatch, handle):
    def client_factory(auth_cookies, request_timeout):
        client = BilibiliAPIClient(auth_cookies=auth_cookies, request_timeout=request_timeout)
        client._client.close()
        client._client = httpx.Client(
            base_url="https://api.bilibili.com", cookies=auth_cookies,
            timeout=request_timeout, transport=httpx.MockTransport(handle),
        )
        monkeypatch.setattr(client, "_sign_params", lambda params: params)
        return client

    monkeypatch.setattr(batch_discovery, "BilibiliAPIClient", client_factory)


def response(data):
    return httpx.Response(200, json={"code": 0, "data": data})


def test_own_favorites_use_full_media_ids_and_include_private_folders(monkeypatch):
    def handle(request):
        assert request.url.path == "/x/v3/fav/folder/created/list-all"
        assert request.url.params["up_mid"] == "42"
        assert request.headers["cookie"] == "SESSDATA=fixture"
        return response({"count": 3, "list": [
            {"mid": 42, "id": 10042, "fid": 100, "title": "默认收藏夹", "media_count": 0},
            {"mid": "42", "id": 20042, "fid": 200, "title": "私密收藏夹", "attr": 22,
             "media_count": 3, "cover": "https://i0.hdslb.com/cover.jpg"},
            {"mid": 43, "id": 30043, "title": "其他账号"},
        ]})

    use_transport(monkeypatch, handle)
    page = batch_discovery.load_batch_sources({"SESSDATA": "fixture"}, 42, "favorites", "", Event())
    assert [(source.title, source.count, source.url) for source in page.sources] == [
        ("默认收藏夹", 0, "https://space.bilibili.com/42/favlist?fid=10042"),
        ("私密收藏夹", 3, "https://space.bilibili.com/42/favlist?fid=20042"),
    ]
    assert page.sources[1].cover.endswith("/cover.jpg")


def dynamic(timestamp, payload, *, kind="AV", following=True, mid=42):
    return {"type": f"DYNAMIC_TYPE_{kind}", "modules": {
        "module_author": {"mid": mid, "name": "作者", "pub_ts": timestamp, "following": following},
        "module_dynamic": {"major": {"ugc_season" if kind == "UGC_SEASON" else "archive": payload}},
    }}


def test_dynamic_prioritizes_collection_updates_and_limits_metadata_reads(monkeypatch):
    lookups = []

    def handle(request):
        if request.url.path == "/x/polymer/web-dynamic/v1/feed/all":
            assert dict(request.url.params)["type"] == "all"
            assert request.url.params["offset"] == "old-cursor"
            return response({"has_more": True, "offset": "next-cursor", "items": [
                dynamic(30, {"jump_url": "//space.bilibili.com/42/lists/7?type=season", "title": "已知合集"},
                        kind="UGC_SEASON"),
                dynamic(20, {"ugc_season": {"id": 7, "title": "同一合集的较早动态"}}),
                dynamic(40, {"aid": "80", "title": "单条视频的标题"}, kind="UGC_SEASON"),
                dynamic(41, {"aid": "81"}, kind="UGC_SEASON", following=False),
                dynamic(42, {"aid": "82"}, kind="FORWARD"),
                *(dynamic(100 - aid, {"aid": aid}) for aid in range(1, 9)),
            ]})
        assert request.url.path == "/x/web-interface/view"
        aid = int(request.url.params["aid"])
        lookups.append(aid)
        if aid == 2:
            return response({"owner": {"mid": 43}, "ugc_season": {"id": 99, "title": "其他作者"}})
        if aid in (80, 1):
            return response({"owner": {"mid": 42}, "ugc_season": {"id": 8, "title": "确认的合集"}})
        return response({"owner": {"mid": 42}})

    use_transport(monkeypatch, handle)
    page = batch_discovery.load_batch_sources({"SESSDATA": "fixture"}, 42, "collections", "old-cursor", Event())
    assert lookups == [80, 1, 2, 3, 4]
    assert [(source.title, source.updated_at, source.url) for source in page.sources] == [
        ("确认的合集", 99, "https://space.bilibili.com/42/lists/8?type=season"),
        ("已知合集", 30, "https://space.bilibili.com/42/lists/7?type=season"),
    ]
    assert page.next_offset == "next-cursor"


def test_expired_feed_and_empty_favorites_have_distinct_results(monkeypatch):
    def handle(request):
        if request.url.path == "/x/v3/fav/folder/created/list-all":
            return response({"count": 0, "list": None})
        return httpx.Response(200, json={"code": -101, "data": None})

    use_transport(monkeypatch, handle)
    cookies = {"SESSDATA": "fixture"}
    empty = batch_discovery.load_batch_sources(cookies, 42, "favorites", "", Event())
    expired = batch_discovery.load_batch_sources(cookies, 42, "collections", "", Event())
    assert not empty.sources and not empty.error
    assert expired.login_required and expired.error


def test_following_then_selected_space_paginates_and_skips_series(monkeypatch):
    def handle(request):
        params = request.url.params
        if request.url.path == "/x/relation/followings":
            assert (params["vmid"], params["pn"], params["ps"]) == ("42", "1", "20")
            return response({"total": 21, "list": [{"mid": 38, "uname": "优先展示"}, {"mid": 4, "uname": "第二位"}]})
        assert request.url.path == "/x/polymer/web-space/seasons_series_list"
        assert (params["mid"], params["page_size"]) == ("38", "12")
        page = int(params["page_num"])
        seasons = [] if page == 1 else [{
            "meta": {"mid": 38, "season_id": 7, "name": "空间合集", "total": 1},
            "archives": [{"pic": "https://i2.hdslb.com/first.jpg"}],
        }]
        return response({"items_lists": {
            "page": {"page_num": page, "page_size": 12, "total": 13},
            "seasons_list": seasons, "series_list": [{"meta": {"series_id": 99}}] if page == 1 else [],
        }})

    use_transport(monkeypatch, handle)
    cookies = {"SESSDATA": "fixture"}
    authors = batch_discovery.load_batch_sources(cookies, 42, "following", "", Event())
    assert [(source.owner_mid, source.title) for source in authors.sources] == [(38, "优先展示"), (4, "第二位")]
    assert authors.next_offset == "2"
    author = authors.sources[0]
    first = batch_discovery.load_batch_sources(cookies, 42, "space", "", Event(), creator=author)
    assert not first.sources and first.next_offset == "2" and first.page_key
    last = batch_discovery.load_batch_sources(cookies, 42, "space", first.next_offset, Event(), creator=author)
    assert [(source.url, source.author, source.first_video_cover) for source in last.sources] == [
        ("https://space.bilibili.com/38/lists/7?type=season", "优先展示", "https://i2.hdslb.com/first.jpg"),
    ]
    assert not last.next_offset


def test_cover_lookups_only_read_preview_pages_and_preserve_cover_priority(monkeypatch):
    favorite_cover = "https://i0.hdslb.com/folder.jpg"
    first_video_cover = "https://i0.hdslb.com/first-video.jpg"
    season_cover = "https://archive.biliimg.com/first-archive.jpg"

    def handle(request):
        params = request.url.params
        if request.url.path == "/x/v3/fav/resource/list":
            assert (params["media_id"], params["pn"], params["ps"]) == ("10042", "1", "20")
            return response({"has_more": True, "info": {"cover": favorite_cover}, "medias": [
                {"type": 12, "cover": "https://i0.hdslb.com/audio.jpg"},
                {"type": 2, "bvid": "BV1GJ411x7h7", "cover": first_video_cover},
                {"type": 2, "bvid": "BV1irxt6uEna", "cover": "https://i0.hdslb.com/second-video.jpg"},
            ]})
        assert request.url.path == "/x/polymer/web-space/seasons_archives_list"
        assert (params["mid"], params["season_id"], params["page_size"], params["sort_reverse"]) == ("42", "7", "1", "false")
        return response({"meta": {}, "archives": [{"pic": season_cover}], "page": {"total": 40}})

    use_transport(monkeypatch, handle)
    cookies = {"SESSDATA": "fixture"}
    favorite = BatchSource("", "收藏夹", owner_mid=42, resource_id=10042)
    season = BatchSource("", "合集", owner_mid=42, resource_id=7)
    assert batch_discovery.load_batch_cover(cookies, favorite, favorite=True).images == (favorite_cover, first_video_cover)
    assert batch_discovery.load_batch_cover(cookies, season, favorite=False).images == (season_cover,)
