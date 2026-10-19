"""Tests for CLI page and companion-file options."""

import argparse

import pytest

from bilibili_downloader import __main__ as cli
from bilibili_downloader.core.models import (
    AppSettings,
    ContentCollection,
    DownloadOutcome,
    VideoInfo,
    VideoPage,
)


@pytest.mark.parametrize(
    ("errors", "has_items"),
    [([], True), (["BV1xx411x7h8：视频已失效"], True), (["视频已失效"], False)],
)
def test_cli_download_handles_collection_results_and_forwards_options(
    monkeypatch, tmp_path, capsys, errors, has_items
):
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
        "bilibili_downloader.core.batch.ContentSourceResolver.resolve",
        lambda self, source: ContentCollection(
            items=[info] if has_items else [], errors=errors
        ),
    )
    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.DownloadService", FakeService
    )
    monkeypatch.setattr(
        "bilibili_downloader.utils.config.ConfigManager.load",
        lambda self: AppSettings(
            output_dir=str(tmp_path), copyright_notice_version=1
        ),
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
        all_subtitles=True,
        audio_only=True,
        audio_quality=0,
        cover=True,
        metadata=True,
        path_template="{author}/{title}{part_suffix}",
    )

    if not has_items:
        with pytest.raises(SystemExit) as exc:
            cli._cli_download(args)
        assert exc.value.code == 1
        assert captured == []
        output = capsys.readouterr().out
        assert "该来源没有可下载的作品" in output
        assert f"Skipped: {errors[0]}" in output
        return

    cli._cli_download(args)

    assert [item.video_info.cid for item in captured] == [11, 22]
    assert all(item.selected_video_codec == 7 for item in captured)
    assert all(item.download_danmaku and item.download_subtitle for item in captured)
    assert all(item.download_all_subtitles for item in captured)
    assert all(item.download_cover and item.download_metadata for item in captured)
    assert all(item.output_mode.value == "audio" for item in captured)
    assert all(item.selected_audio_quality == 0 for item in captured)
    assert all(item.path_template == "{author}/{title}{part_suffix}" for item in captured)
    assert all(item.selected_subtitle_lan == "en-US" for item in captured)
    output = capsys.readouterr().out
    for error in errors:
        assert f"Skipped: {error}" in output


def test_noninteractive_copyright_requires_explicit_flag():
    assert cli._confirm_cli_copyright(True) is True
    assert cli._confirm_cli_copyright(False) is False
