"""Tests for batch/single input resolution."""

import pytest

from bilibili_downloader.core.batch import BatchResolveError, BatchResolver
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


def test_rejects_series_urls():
    with pytest.raises(BatchResolveError):
        BatchResolver(FakeClient()).resolve_one(
            "https://www.bilibili.com/medialist/play/watchlater?sid=123"
        )


def test_resolve_text_keeps_order():
    client = FakeClient()
    infos = BatchResolver(client).resolve_text("BV1GJ411x7h7\nav123456")

    assert [info.bvid for info in infos] == ["BV1GJ411x7h7", "BVfromAid123"]
