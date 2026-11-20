"""Continuous transfers, bounded fallback and resumable byte integrity."""

import hashlib
from types import SimpleNamespace

import httpx
import pytest

from bilibili_downloader.core import downloader as module
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.models import StreamInfo
from bilibili_downloader.utils.network import UntrustedResourceURLError

URL = "https://upos-hz-mirrorakam.akamaized.net/video.m4s?token=test%2Fsignature"
BACKUP = "https://upos-sz.bilivideo.com/video.m4s"


def range_response(request, payload):
    assert request.headers["accept-encoding"] == "identity"
    assert "cookie" not in request.headers
    assert request.headers["referer"] == "https://www.bilibili.com/"
    requested = request.headers.get("range")
    if requested is None:
        return httpx.Response(200, content=payload)
    first, last = requested.removeprefix("bytes=").split("-")
    start = int(first)
    end = min(int(last), len(payload) - 1) if last else len(payload) - 1
    return httpx.Response(206, headers={"content-range": f"bytes {start}-{end}/{len(payload)}"},
                          content=payload[start:end + 1])


@pytest.mark.parametrize(("existing", "expected_range"), [(b"", None), (b"abc", "bytes=3-")])
def test_fast_download_uses_one_request(tmp_path, existing, expected_range):
    payload = b"abcdefghij"
    requests = []

    def handler(request):
        requests.append(request.headers.get("range"))
        return range_response(request, payload)

    dest = tmp_path / "video.m4s"
    if existing:
        dest.write_bytes(existing)
    progress = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, progress.append)

    assert hashlib.sha256(dest.read_bytes()).digest() == hashlib.sha256(payload).digest()
    assert requests == [expected_range] and progress == [1.0]


@pytest.mark.parametrize("existing", [b"", b"abc"])
def test_download_assembles_bounded_ranges_without_early_completion(monkeypatch, tmp_path, existing):
    payload = b"abcdefghij"
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    ranges = []

    def handler(request):
        ranges.append(request.headers.get("range"))
        assert str(request.url) == URL
        if len(ranges) == 1:
            return httpx.Response(403)
        return range_response(request, payload)

    dest = tmp_path / "video.m4s"
    if existing:
        dest.write_bytes(existing)
    downloader = StreamDownloader(object(), str(tmp_path))
    progress = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        downloader._download_url(client, URL, dest, progress.append)

    assert dest.read_bytes() == payload
    assert ranges == (["bytes=3-", "bytes=3-6", "bytes=7-9"] if existing else [None, "bytes=0-3", "bytes=4-7", "bytes=8-9"])
    assert progress[-1] == 1.0 and all(value < 1.0 for value in progress[:-1])
    assert progress == sorted(progress)
    assert downloader.transfer_metrics.downloaded_bytes == len(payload)
    assert downloader.transfer_metrics.total_bytes == len(payload)


@pytest.mark.parametrize("requires_bounded", [False, True])
def test_download_accepts_smaller_ranges_returned_by_server(monkeypatch, tmp_path, requires_bounded):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    payload = b"abcdef"
    ranges = []

    def handler(request):
        requested = request.headers.get("range")
        ranges.append(requested)
        if requested is None and requires_bounded:
            return httpx.Response(403)
        start = int(requested[6:].split("-")[0]) if requested else 0
        end = min(start + 1, len(payload) - 1)
        return httpx.Response(206, headers={"content-range": f"bytes {start}-{end}/{len(payload)}"},
                              content=payload[start:end + 1])

    dest = tmp_path / "video.m4s"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda value: None)
    expected = [None, "bytes=0-3", "bytes=2-5", "bytes=4-5"] if requires_bounded else [None, "bytes=2-", "bytes=4-"]
    assert ranges == expected and dest.read_bytes() == payload


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
    assert len(requests) == 1 and requests[0].headers["range"] == "bytes=3-"
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
    def handler(request):
        if request.headers["range"] == "bytes=3-":
            return httpx.Response(403)
        return httpx.Response(206, headers=headers, stream=httpx.ByteStream(body))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ProtocolError):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, progress.append)
    assert dest.read_bytes() == b"abc" and 1.0 not in progress


@pytest.mark.parametrize("status", [200, 206, 416])
def test_changed_total_size_is_rejected_before_append(monkeypatch, tmp_path, status):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"

    def handler(request):
        if "range" not in request.headers:
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
    payload = b"abcdefgh"
    requests = []
    progress = []

    def handler(request):
        requested = request.headers.get("range")
        requests.append((request.url.host, requested))
        if request.url.host == "upos-hz-mirrorakam.akamaized.net":
            if requested is None:
                return httpx.Response(403)
            return httpx.Response(206, headers={"content-range": "bytes 0-3/8", "content-length": "4"}, content=b"ab")
        assert not dest.with_suffix(".m4s.complete").exists()
        return range_response(request, payload)

    monkeypatch.setattr(module.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(handler))
    StreamDownloader(object(), str(tmp_path), max_retries=1)._download_stream(
        StreamInfo(base_url=URL, backup_url=[BACKUP]), dest, progress.append
    )
    assert requests == [("upos-hz-mirrorakam.akamaized.net", None),
                        ("upos-hz-mirrorakam.akamaized.net", "bytes=0-3"),
                        ("upos-sz.bilivideo.com", "bytes=2-")]
    assert dest.read_bytes() == payload
    assert dest.with_suffix(".m4s.complete").read_text() == "8"
    assert progress[-1] == 1.0 and all(value < 1.0 for value in progress[:-1])


@pytest.mark.parametrize("status", [200, 206])
def test_truncated_body_is_not_marked_complete(monkeypatch, tmp_path, status):
    dest = tmp_path / "video.m4s"
    headers = {"content-length": "4"}
    if status == 206:
        headers["content-range"] = "bytes 0-3/4"
    def handler(request):
        if request.headers.get("range") == "bytes=2-":
            return httpx.Response(503)
        return httpx.Response(status, headers=headers, content=b"ab")
    monkeypatch.setattr(module.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(handler))
    progress = []
    with pytest.raises(RuntimeError):
        StreamDownloader(object(), str(tmp_path), max_retries=1)._download_stream(
            StreamInfo(base_url=URL), dest, progress.append
        )
    assert dest.read_bytes() == b"ab"
    assert not dest.with_suffix(".m4s.complete").exists() and 1.0 not in progress


class InterruptedBody(httpx.SyncByteStream):
    def __init__(self, prefix, error):
        self.prefix = prefix
        self.error = error

    def __iter__(self):
        yield self.prefix
        if self.error is not None:
            raise self.error("incomplete body")


@pytest.mark.parametrize("failures", [
    (None,), (httpx.ReadTimeout,), (None, None), (httpx.ReadError, httpx.RemoteProtocolError),
])
def test_body_interruptions_resume_fast_once_then_use_bounded_ranges(monkeypatch, tmp_path, failures):
    block = 64 * 1024
    payload = b"".join(bytes([i]) * block for i in range(5))
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 2 * block)
    seen = []

    def handler(request):
        requested = request.headers.get("range")
        attempt = len(seen)
        seen.append(requested)
        if attempt >= len(failures):
            return range_response(request, payload)
        offset = attempt * block
        headers = {"content-length": str(len(payload) - offset)}
        if offset:
            headers["content-range"] = f"bytes {offset}-{len(payload) - 1}/{len(payload)}"
        return httpx.Response(
            206 if offset else 200, headers=headers,
            stream=InterruptedBody(payload[offset:offset + block], failures[attempt]),
        )

    dest = tmp_path / "video.m4s"
    progress = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, progress.append)

    expected = [None, f"bytes={block}-"]
    if len(failures) == 2:
        expected += [f"bytes={2 * block}-{4 * block - 1}", f"bytes={4 * block}-{5 * block - 1}"]
    assert seen == expected
    assert hashlib.sha256(dest.read_bytes()).digest() == hashlib.sha256(payload).digest()
    assert progress == sorted(progress) and progress.count(1.0) == 1


def test_dropped_eof_requires_confirmation_before_reporting_completion(tmp_path):
    payload = b"p" * (64 * 1024)
    seen = []
    progress = []

    def handler(request):
        seen.append(request.headers.get("range"))
        assert 1.0 not in progress
        if len(seen) == 1:
            return httpx.Response(200, headers={"content-length": str(len(payload))},
                                  stream=InterruptedBody(payload, httpx.RemoteProtocolError))
        if len(seen) == 2:
            return httpx.Response(403)
        return httpx.Response(416, headers={"content-range": f"bytes */{len(payload)}"})

    dest = tmp_path / "video.m4s"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, progress.append)

    assert seen == [None, f"bytes={len(payload)}-", f"bytes={len(payload)}-{len(payload)}"]
    assert dest.read_bytes() == payload and progress == [1.0]


@pytest.mark.parametrize("status", [401, 404, 429, 503])
def test_other_http_errors_leave_fallback_to_the_existing_retry_loop(tmp_path, status):
    seen = []

    def handler(request):
        seen.append(request.headers.get("range"))
        return httpx.Response(status)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, tmp_path / "video.m4s", lambda _: None)
    assert seen == [None]


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ReadTimeout])
def test_failure_before_response_headers_does_not_switch_to_bounded_ranges(tmp_path, error):
    seen = []

    def handler(request):
        seen.append(request.headers.get("range"))
        raise error("request did not receive a response", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, tmp_path / "video.m4s", lambda _: None)
    assert seen == [None]


def test_fast_invalid_range_is_not_retried_as_a_body_failure(tmp_path):
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"abc")
    seen = []

    def handler(request):
        seen.append(request.headers.get("range"))
        return httpx.Response(206, headers={"content-range": "bytes 2-4/5"}, content=b"cde")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ProtocolError, match="续传起点"):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda _: None)
    assert seen == ["bytes=3-"] and dest.read_bytes() == b"abc"


def test_fallback_keeps_the_known_total_when_changing_cdns(monkeypatch, tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers.get("range"))
        if len(seen) == 1:
            return httpx.Response(200, headers={"content-length": "8"}, content=b"ab")
        if len(seen) == 2:
            return httpx.Response(503)
        return httpx.Response(206, headers={"content-range": "bytes 2-5/6"}, content=b"cdef")

    monkeypatch.setattr(module.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(handler))
    dest = tmp_path / "video.m4s"
    with pytest.raises(RuntimeError, match="媒体总大小发生变化"):
        StreamDownloader(object(), str(tmp_path), max_retries=1)._download_stream(
            StreamInfo(base_url=URL, backup_url=[BACKUP]), dest, lambda _: None,
        )
    assert seen == [None, "bytes=2-", "bytes=2-"]
    assert dest.read_bytes() == b"ab" and not dest.with_suffix(".m4s.complete").exists()


def test_transfer_speed_counts_the_gap_between_bounded_responses(monkeypatch, tmp_path):
    now = 0
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now))
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)

    class TimedBody(httpx.SyncByteStream):
        def __iter__(self):
            nonlocal now
            now += 1
            yield b"data"

    def handler(request):
        nonlocal now
        now += 1
        header = request.headers.get("range")
        if header is None:
            return httpx.Response(403)
        interval = header.removeprefix("bytes=")
        return httpx.Response(206, headers={"content-range": f"bytes {interval}/8"}, stream=TimedBody())

    downloader = StreamDownloader(object(), str(tmp_path))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        downloader._download_url(client, URL, tmp_path / "video.m4s", lambda _: None)

    assert downloader.transfer_metrics.speed_bytes_per_second == pytest.approx(8 / 3)


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
        if len(requests) == 1:
            return httpx.Response(403)
        return range_response(request, b"abcdefgh")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="cancelled"):
            downloader._download_url(client, URL, dest, lambda value: downloader.cancel())
    assert len(requests) == 2 and dest.read_bytes() == b"abcd"


def test_later_range_redirect_cannot_escape_host_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "RANGE_CHUNK_SIZE", 4)
    dest = tmp_path / "video.m4s"
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(403)
        if len(requests) == 2:
            return range_response(request, b"abcdefgh")
        return httpx.Response(302, headers={"location": "https://evil.test/segment"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UntrustedResourceURLError):
            StreamDownloader(object(), str(tmp_path))._download_url(client, URL, dest, lambda value: None)
    assert len(requests) == 3 and dest.read_bytes() == b"abcd"
