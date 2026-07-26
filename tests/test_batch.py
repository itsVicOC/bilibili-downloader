"""Tests for batch/single input resolution."""

import pytest

from bilibili_downloader.core.batch import (
    BatchResolveError,
    BatchResolver,
    ContentSourceResolver,
    classify_batch_inputs,
    is_collection_source,
)
from bilibili_downloader.core.models import VideoInfo


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_video_info(self, bvid):
        self.calls.append(("bvid", bvid))
        return VideoInfo(bvid=bvid, title="BV video")

    def get_video_info_by_aid(self, aid):
        self.calls.append(("aid", aid))
        return VideoInfo(bvid="BVfromAid123", aid=aid, title="AV video")

    def get_favorite_collection(self, media_id, source_url=""):
        from bilibili_downloader.core.models import ContentCollection

        return ContentCollection(
            title="Favorites",
            source_type="favorite",
            source_url=source_url,
            items=[VideoInfo(bvid="BV1GJ411x7h7", title=str(media_id))],
        )

    def get_season_collection(self, mid, season_id, source_url=""):
        from bilibili_downloader.core.models import ContentCollection

        return ContentCollection(
            title="Season",
            source_type="season",
            source_url=source_url,
            items=[VideoInfo(bvid="BV1GJ411x7h7", title=f"{mid}:{season_id}")],
        )


def test_resolve_bv_url():
    client = FakeClient()
    info = BatchResolver(client).resolve_one(
        "https://www.bilibili.com/video/BV1GJ411x7h7?p=1"
    )

    assert info.bvid == "BV1GJ411x7h7"
    assert client.calls == [("bvid", "BV1GJ411x7h7")]


def test_resolve_av_url():
    client = FakeClient()
    info = BatchResolver(client).resolve_one("https://www.bilibili.com/video/av123456")

    assert info.aid == 123456
    assert client.calls == [("aid", 123456)]


def test_resolve_short_link(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(
        "bilibili_downloader.core.batch.resolve_short_link",
        lambda url: "BV1GJ411x7h7",
    )

    info = BatchResolver(client).resolve_one("https://b23.tv/abc123")

    assert info.bvid == "BV1GJ411x7h7"
    assert client.calls == [("bvid", "BV1GJ411x7h7")]


def test_single_resolver_routes_collections_to_batch_import():
    with pytest.raises(BatchResolveError):
        BatchResolver(FakeClient()).resolve_one(
            "https://space.bilibili.com/123/favlist?fid=456"
        )


def test_resolve_text_keeps_order():
    client = FakeClient()
    infos = BatchResolver(client).resolve_text("BV1GJ411x7h7\nav123456")

    assert [info.bvid for info in infos] == ["BV1GJ411x7h7", "BVfromAid123"]


def test_classify_batch_inputs_deduplicates_and_reports_invalid():
    valid, invalid = classify_batch_inputs(
        "BV1GJ411x7h7\n"
        "https://www.bilibili.com/video/BV1GJ411x7h7\n"
        "av123456\n"
        "not-a-video"
    )

    assert valid == ["BV1GJ411x7h7", "av123456"]
    assert invalid == ["not-a-video"]


def test_resolves_favorite_source():
    source = "https://space.bilibili.com/123/favlist?fid=456"
    collection = ContentSourceResolver(FakeClient()).resolve(source)

    assert collection.source_type == "favorite"
    assert collection.items[0].title == "456"


def test_resolves_space_season_source():
    source = "https://space.bilibili.com/123/lists/456?type=season"
    collection = ContentSourceResolver(FakeClient()).resolve(source)

    assert collection.source_type == "season"
    assert collection.items[0].title == "123:456"


def test_classification_accepts_collection_sources():
    source = "https://space.bilibili.com/123/lists/456?type=season"

    assert is_collection_source(source)
    assert classify_batch_inputs(source) == ([source], [])


def test_old_space_collection_link_is_supported():
    source = "https://space.bilibili.com/123/channel/collectiondetail?sid=456"
    collection = ContentSourceResolver(FakeClient()).resolve(source)

    assert collection.source_type == "season"
    assert collection.items[0].title == "123:456"
