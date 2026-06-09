"""Tests for stream downloader retry helpers."""

import pytest

from bilibili_downloader.core.downloader import StreamDownloader, _stream_urls
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
