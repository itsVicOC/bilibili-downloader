"""Tests for stream downloader retry helpers."""

import httpx
import pytest

from bilibili_downloader.core.downloader import (
    StreamDownloader,
    _reserved_download_cache,
    _reserved_output_path,
    _response_total_size,
    _stream_urls,
)
from bilibili_downloader.core.models import DownloadItem, StreamInfo, VideoInfo


def test_stream_urls_deduplicates_base_and_backups():
    stream = StreamInfo(base_url="base", backup_url=["base", "backup", "backup"])

    assert _stream_urls(stream) == ["base", "backup"]


def test_download_stream_falls_back_to_backup_url(monkeypatch, tmp_path):
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path), max_retries=1)
    calls = []

    def fake_download_url(client, url, dest, progress_callback):
        calls.append(url)
        if url == "base":
            raise OSError("primary failed")
        progress_callback(1.0)

    monkeypatch.setattr(downloader, "_download_url", fake_download_url)

    downloader._download_stream(
        StreamInfo(base_url="base", backup_url=["backup"]),
        tmp_path / "video.m4s",
        lambda progress: None,
    )

    assert calls == ["base", "backup"]


def test_download_stream_requires_at_least_one_url(tmp_path):
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path), max_retries=1)

    with pytest.raises(RuntimeError, match="流地址为空"):
        downloader._download_stream(StreamInfo(), tmp_path / "video.m4s", lambda progress: None)


def test_response_total_size_ignores_invalid_content_length():
    class Response:
        status_code = 200
        headers = {"content-length": "not-a-number"}

    assert _response_total_size(Response(), 0) == 0


def test_retry_wait_is_cancellable(tmp_path):
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path))
    downloader.cancel()

    with pytest.raises(RuntimeError, match="cancelled"):
        downloader._wait_for_retry(1.0)


def test_output_path_reservation_avoids_existing_and_concurrent_files(tmp_path):
    requested = tmp_path / "episode.mp4"
    requested.write_bytes(b"existing")

    with _reserved_output_path(requested) as first:
        with _reserved_output_path(requested) as second:
            assert first.name == "episode (2).mp4"
            assert second.name == "episode (3).mp4"


def test_download_cache_is_stable_and_audio_specific(tmp_path):
    base = DownloadItem(video_info=VideoInfo(bvid="BV1xx", cid=123))
    alternate_audio = base.model_copy(update={"selected_audio_quality": 30216})

    with _reserved_download_cache(tmp_path, base) as first:
        first_path = first
    with _reserved_download_cache(tmp_path, base) as second:
        second_path = second
    with _reserved_download_cache(tmp_path, alternate_audio) as third:
        third_path = third

    assert first_path == second_path
    assert third_path != first_path


def test_download_url_rejects_redirect_to_untrusted_host(tmp_path):
    def handler(request):
        return httpx.Response(
            302,
            headers={"location": "https://example.org/private"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path))
    try:
        with pytest.raises(ValueError, match="不受信任"):
            downloader._download_url(
                client,
                "https://upos-sz.bilivideo.com/video.m4s",
                tmp_path / "video.m4s",
                lambda _progress: None,
            )
    finally:
        client.close()


def test_write_response_resumes_valid_partial_content(tmp_path):
    request = httpx.Request("GET", "https://upos-sz.bilivideo.com/video.m4s")
    response = httpx.Response(
        206,
        headers={"content-range": "bytes 3-5/6"},
        content=b"def",
        request=request,
    )
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"abc")
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path))

    downloader._write_response(response, dest, 3, lambda _progress: None)

    assert dest.read_bytes() == b"abcdef"


def test_write_response_rejects_mismatched_partial_range(tmp_path):
    request = httpx.Request("GET", "https://upos-sz.bilivideo.com/video.m4s")
    response = httpx.Response(
        206,
        headers={"content-range": "bytes 2-4/6"},
        content=b"cde",
        request=request,
    )
    dest = tmp_path / "video.m4s"
    dest.write_bytes(b"abc")
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path))

    with pytest.raises(httpx.ProtocolError, match="续传起点"):
        downloader._write_response(response, dest, 3, lambda _progress: None)

    assert dest.read_bytes() == b"abc"


def test_download_stream_reuses_only_matching_completion_marker(
    monkeypatch, tmp_path
):
    downloader = StreamDownloader(api_client=object(), output_dir=str(tmp_path))
    dest = tmp_path / "video.m4s"
    marker = tmp_path / "video.m4s.complete"
    dest.write_bytes(b"complete")
    marker.write_text(str(dest.stat().st_size), encoding="ascii")
    calls = []
    monkeypatch.setattr(
        downloader,
        "_download_url",
        lambda *_args: calls.append("downloaded"),
    )

    downloader._download_stream(
        StreamInfo(base_url="https://upos-sz.bilivideo.com/video.m4s"),
        dest,
        lambda _progress: None,
    )
    assert calls == []

    dest.write_bytes(b"changed")
    downloader._download_stream(
        StreamInfo(base_url="https://upos-sz.bilivideo.com/video.m4s"),
        dest,
        lambda _progress: None,
    )
    assert calls == ["downloaded"]
