"""Tests for stream downloader retry helpers."""

import pytest

from bilibili_downloader.core.downloader import (
    StreamDownloader,
    _reserved_output_path,
    _response_total_size,
    _stream_urls,
)
from bilibili_downloader.core.models import StreamInfo


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
