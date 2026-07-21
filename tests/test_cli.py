"""Tests for CLI page and companion-file options."""

import argparse

from bilibili_downloader import __main__ as cli
from bilibili_downloader.core.models import (
    AppSettings,
    DownloadOutcome,
    VideoInfo,
    VideoPage,
)


def test_cli_download_expands_all_pages_and_forwards_options(monkeypatch, tmp_path):
    info = VideoInfo(
        bvid="BV1GJ411x7h7",
        cid=11,
        title="Series",
        pages=[
            VideoPage(cid=11, page=1, part="One"),
            VideoPage(cid=22, page=2, part="Two"),
        ],
    )
    captured = []

    class FakeClient:
        def __init__(self, sessdata=None):
            self.sessdata = sessdata

        def close(self):
            pass

    class FakeService:
        def __init__(self, client, output_dir, ffmpeg_path=None):
            assert output_dir == str(tmp_path)

        def download(self, item, callback):
            captured.append(item)
            return DownloadOutcome(video_path=str(tmp_path / item.filename))

    monkeypatch.setattr(
        "bilibili_downloader.api.client.BilibiliAPIClient", FakeClient
    )
    monkeypatch.setattr(
        "bilibili_downloader.core.batch.BatchResolver.resolve_one",
        lambda self, source: info,
    )
    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.DownloadService", FakeService
    )
    monkeypatch.setattr(
        "bilibili_downloader.utils.config.ConfigManager.load",
        lambda self: AppSettings(output_dir=str(tmp_path)),
    )
    args = argparse.Namespace(
        source="BV1GJ411x7h7",
        quality=80,
        output=None,
        danmaku=True,
        subtitle=True,
        codec=7,
        page="all",
        subtitle_language="en-US",
    )

    cli._cli_download(args)

    assert [item.video_info.cid for item in captured] == [11, 22]
    assert all(item.selected_video_codec == 7 for item in captured)
    assert all(item.download_danmaku and item.download_subtitle for item in captured)
    assert all(item.selected_subtitle_lan == "en-US" for item in captured)
