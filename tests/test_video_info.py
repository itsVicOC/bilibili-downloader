"""Tests for the asynchronously loaded video cover preview."""

import io
from contextlib import contextmanager

import httpx
from PIL import Image

from bilibili_downloader.gui.widgets.video_info import VideoInfoWidget


def test_cover_preview_upgrades_api_http_url_and_keeps_job_alive(
    monkeypatch, qtbot
):
    content = io.BytesIO()
    Image.new("RGB", (16, 9), "red").save(content, format="PNG")
    png_bytes = content.getvalue()
    requested_urls = []
    queued_runners = []

    @contextmanager
    def stream(_method, url, **_kwargs):
        requested_urls.append(url)
        request = httpx.Request("GET", url)
        yield httpx.Response(200, content=png_bytes, request=request)

    monkeypatch.setattr("httpx.stream", stream)
    widget = VideoInfoWidget()
    qtbot.addWidget(widget)
    widget._cover_pool = type(
        "ImmediatePool",
        (),
        {"start": lambda _self, runner: queued_runners.append(runner)},
    )()

    widget._load_cover("http://i1.hdslb.com/bfs/archive/cover.jpg")

    assert len(widget._cover_jobs) == 1
    queued_runners[0].run()
    assert requested_urls == [
        "https://i1.hdslb.com/bfs/archive/cover.jpg"
    ]
    assert widget._cover_jobs == []
    assert widget._cover_label.pixmap() is not None
    assert widget._cover_label.pixmap().width() >= 300
