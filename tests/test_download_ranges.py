"""Bounded CDN ranges, byte integrity, cancellation and resumable retries."""

import httpx
import pytest

from bilibili_downloader.core import downloader as module
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.models import StreamInfo
from bilibili_downloader.utils.network import UntrustedResourceURLError

URL = "https://upos-hz-mirrorakam.akamaized.net/video.m4s?token=test%2Fsignature"


def range_response(request, payload):
    assert request.headers["accept-encoding"] == "identity"
    assert "cookie" not in request.headers
    assert request.headers["referer"] == "https://www.bilibili.com/"
    start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
    end = min(end, len(payload) - 1)
    return httpx.Response(206, headers={"content-range": f"bytes {start}-{end}/{len(payload)}"},
                          content=payload[start:end + 1])


@pytest.mark.parametrize("existing", [b"", b"abc"])
def test_download_assembles_bounded_ranges_without_early_completion(monkeypatch, tmp_path, existing):
    payload = b"abcdefghij"
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    ranges = []

    def handler(request):
        ranges.append(request.headers["range"])
        assert str(request.url) == URL
        return range_response(request, payload)

    dest = tmp_path / "video.m4s"
    if existing:
        dest.write_bytes(existing)
    downloader = StreamDownloader(object(), str(tmp_path))
    progress = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        downloader._download_url(client, URL, dest, progress.append)

    assert dest.read_bytes() == payload
    assert ranges == (["bytes=3-6", "bytes=7-9"] if existing else ["bytes=0-3", "bytes=4-7", "bytes=8-9"])
    assert progress[-1] == 1.0 and all(value < 1.0 for value in progress[:-1])
    assert progress == sorted(progress)
    assert downloader.transfer_metrics.downloaded_bytes == len(payload)
    assert downloader.transfer_metrics.total_bytes == len(payload)


def test_download_accepts_smaller_ranges_returned_by_server(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    payload = b"abcdef"
    ranges = []

    def handler(request):
        start = int(request.headers["range"][6:].split("-")[0])
        ranges.append(start)
        end = min(start + 1, len(payload) - 1)
        return httpx.Response(206, headers={"content-range": f"bytes {start}-{end}/{len(payload)}"},
                              content=payload[start:end + 1])

    dest = tmp_path / "video.m4s"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda value: None)
    assert ranges == [0, 2, 4] and dest.read_bytes() == payload


def test_server_ignoring_range_replaces_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"old")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b"complete")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda value: None)
    assert len(requests) == 1 and requests[0].headers["range"] == "bytes=3-6"
    assert dest.read_bytes() == b"complete"


@pytest.mark.parametrize("headers,body", [
    ({"content-range": "bytes 2-4/10"}, b"def"),
    ({"content-range": "bytes 3-7/10"}, b"defgh"),
    ({"content-range": "bytes 3-2/10"}, b""),
    ({"content-range": "bytes 3-6/6"}, b"defg"),
    ({"content-range": "bytes 3-6/*"}, b"defg"),
    ({"content-range": "bytes 3-6/10", "content-length": "3"}, b"def"),
    ({"content-range": "bytes 3-6/10", "content-encoding": "gzip"}, b"defg"),
    ({}, b"defg"),
])
def test_invalid_partial_headers_preserve_existing_file(monkeypatch, tmp_path, headers, body):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"abc")
    progress = []
    handler = lambda request: httpx.Response(206, headers=headers, stream=httpx.ByteStream(body))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ProtocolError):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, progress.append)
    assert dest.read_bytes() == b"abc" and 1.0 not in progress


@pytest.mark.parametrize("status", [200, 206, 416])
def test_changed_total_size_is_rejected_before_append(monkeypatch, tmp_path, status):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"

    def handler(request):
        if request.headers["range"] == "bytes=0-3":
            return httpx.Response(206, headers={"content-range": "bytes 0-3/8"}, content=b"abcd")
        if status == 200:
            return httpx.Response(200, content=b"different")
        if status == 416:
            return httpx.Response(416, headers={"content-range": "bytes */4"})
        return httpx.Response(206, headers={"content-range": "bytes 4-7/9"}, content=b"efgh")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ProtocolError):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda value: None)
    assert dest.read_bytes() == b"abcd"


def test_full_response_without_content_length_is_supported(tmp_path):
    dest = tmp_path / "video.m4s"
    handler = lambda request: httpx.Response(200, stream=httpx.ByteStream(b"complete"))
    progress = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, progress.append)
    assert dest.read_bytes() == b"complete" and progress == [1.0]


def test_truncated_range_resumes_on_backup_without_completion_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"
    backup = "https://upos-sz.bilivideo.com/video.m4s"
    payload = b"abcdefgh"
    requests = []
    progress = []

    def handler(request):
        requests.append((request.url.host, request.headers["range"]))
        if request.url.host == "upos-hz-mirrorakam.akamaized.net":
            return httpx.Response(206, headers={"content-range": "bytes 0-3/8", "content-length": "4"}, content=b"ab")
        assert not dest.with_suffix(".m4s.complete").exists()
        return range_response(request, payload)

    monkeypatch.setattr(module.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(handler))
    StreamDownloader(object(), str(tmp_path), max_retries=1)._download_stream(
        StreamInfo(base_url=URL, backup_url=[backup]), dest, progress.append
    )
    assert requests == [("upos-hz-mirrorakam.akamaized.net", "bytes=0-3"),
                        ("upos-sz.bilivideo.com", "bytes=2-5"),
                        ("upos-sz.bilivideo.com", "bytes=6-7")]
    assert dest.read_bytes() == payload
    assert dest.with_suffix(".m4s.complete").read_text() == "8"
    assert progress[-1] == 1.0 and all(value < 1.0 for value in progress[:-1])


@pytest.mark.parametrize("status", [200, 206])
def test_truncated_body_is_not_marked_complete(monkeypatch, tmp_path, status):
    dest = tmp_path / "video.m4s"
    headers = {"content-length": "4"}
    if status == 206:
        headers["content-range"] = "bytes 0-3/4"
    handler = lambda request: httpx.Response(status, headers=headers, content=b"ab")
    monkeypatch.setattr(module.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(handler))
    progress = []
    with pytest.raises(RuntimeError):
        StreamDownloader(object(), str(tmp_path), max_retries=1)._download_stream(
            StreamInfo(base_url=URL), dest, progress.append
        )
    assert dest.read_bytes() == b"ab"
    assert not dest.with_suffix(".m4s.complete").exists() and 1.0 not in progress


def test_oversized_body_is_rejected_before_write(tmp_path):
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"abc")
    response = httpx.Response(206, headers={"content-range": "bytes 3-4/5", "content-length": "2"},
                              content=b"def", request=httpx.Request("GET", URL))
    with pytest.raises(httpx.ProtocolError):
        StreamDownloader(object(), str(tmp_path))._write_response(response, dest, 3, lambda value: None)
    assert dest.read_bytes() == b"abc"


@pytest.mark.parametrize("content_range,success", [("bytes */4", True), ("bytes */5", False), ("invalid/4", False)])
def test_unsatisfied_range_requires_exact_remote_and_local_size(tmp_path, content_range, success):
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"abcd")
    handler = lambda request: httpx.Response(416, headers={"content-range": content_range})
    downloader = StreamDownloader(object(), str(tmp_path))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if success:
            downloader._download_url(client, URL, dest, lambda value: None)
        else:
            with pytest.raises(httpx.HTTPStatusError):
                downloader._download_url(client, URL, dest, lambda value: None)
    assert dest.read_bytes() == b"abcd"


def test_cancel_between_ranges_stops_before_next_request(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"
    requests = []
    downloader = StreamDownloader(object(), str(tmp_path))

    def handler(request):
        requests.append(request)
        return range_response(request, b"abcdefgh")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="cancelled"):
            downloader._download_url(client, URL, dest, lambda value: downloader.cancel())
    assert len(requests) == 1 and dest.read_bytes() == b"abcd"


def test_later_range_redirect_cannot_escape_host_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return range_response(request, b"abcdefgh")
        return httpx.Response(302, headers={"location": "https://evil.test/segment"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UntrustedResourceURLError):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda value: None)
    assert len(requests) == 2 and dest.read_bytes() == b"abcd"
