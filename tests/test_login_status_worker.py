"""Login identity and optional avatar loading do not share failure states."""

import io
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from bilibili_downloader.gui.threads import login_status_worker as module
from bilibili_downloader.gui.threads.login_status_worker import (
    LoginStatusRunner,
    LoginStatusWorker,
    load_avatar,
)


def png(size=(200, 120)):
    output = io.BytesIO()
    Image.new("RGB", size, "skyblue").save(output, format="PNG")
    return output.getvalue()


def mock_stream(monkeypatch, chunks, *, status=200):
    calls = []

    @contextmanager
    def stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        response = httpx.Response(status, request=httpx.Request(method, url))
        yield SimpleNamespace(
            raise_for_status=response.raise_for_status,
            iter_bytes=lambda: iter(chunks),
        )

    monkeypatch.setattr(module.httpx, "stream", stream)
    return calls


def test_avatar_uses_cookie_free_https_and_normalizes_image(monkeypatch):
    calls = mock_stream(monkeypatch, [png()])
    content = load_avatar("http://i0.hdslb.com/bfs/face/demo.png")
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "PNG"
        assert image.size == (96, 58)
    method, url, options = calls[0]
    assert method == "GET"
    assert url.startswith("https://i0.hdslb.com/")
    assert options == {"timeout": 5.0, "follow_redirects": False}


@pytest.mark.parametrize("url", [
    "https://hdslb.com.example.org/avatar.png", "file:///avatar.png",
    "https://secret@i0.hdslb.com/avatar.png",
])
def test_avatar_rejects_untrusted_destination_before_request(monkeypatch, url):
    calls = mock_stream(monkeypatch, [png()])
    with pytest.raises(ValueError):
        load_avatar(url)
    assert not calls


@pytest.mark.parametrize("case", ["bytes", "pixels", "corrupt", "redirect"])
def test_avatar_rejects_oversize_corrupt_or_redirected_response(monkeypatch, case):
    content = png()
    if case == "bytes":
        monkeypatch.setattr(module, "MAX_AVATAR_BYTES", len(content) - 1)
    if case == "pixels":
        monkeypatch.setattr(module, "MAX_AVATAR_PIXELS", 100)
    if case == "corrupt":
        content = b"not an image"
    mock_stream(monkeypatch, [content], status=302 if case == "redirect" else 200)
    with pytest.raises((ValueError, OSError, httpx.HTTPError)):
        load_avatar("https://i0.hdslb.com/demo.png")


@pytest.mark.parametrize("avatar_fails", [False, True])
def test_login_is_reported_before_avatar_and_survives_avatar_failure(qapp, monkeypatch, avatar_fails):
    info = {"isLogin": True, "uname": "示例用户", "face": "https://i0.hdslb.com/demo.png"}
    worker = LoginStatusWorker(SimpleNamespace(get_nav_info=lambda: info), 7)
    events = []
    worker.finished.connect(lambda *args: events.append(("login", args)))
    worker.error.connect(lambda *args: events.append(("error", args)))
    worker.avatar_ready.connect(lambda *args: events.append(("avatar", args)))

    def fetch(url):
        assert events == [("login", (7, info))]
        if avatar_fails:
            raise OSError("offline")
        return b"small-png"

    monkeypatch.setattr(module, "load_avatar", fetch)
    LoginStatusRunner(worker).run()
    assert events[0] == ("login", (7, info))
    assert events[1:] == ([] if avatar_fails else [("avatar", (7, b"small-png"))])


def test_logged_out_status_never_fetches_avatar(qapp, monkeypatch):
    worker = LoginStatusWorker(
        SimpleNamespace(get_nav_info=lambda: {"isLogin": False, "face": "stale"}), 8
    )
    fetch = Mock()
    monkeypatch.setattr(module, "load_avatar", fetch)
    LoginStatusRunner(worker).run()
    fetch.assert_not_called()
