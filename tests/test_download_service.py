"""Tests for the shared CLI/GUI download workflow."""

from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.models import (
    DownloadItem,
    StreamInfo,
    SubtitleInfo,
    VideoInfo,
    VideoQuality,
)


class FakeAPI:
    def __init__(self, tracks=None):
        self.tracks = tracks or []
        self.subtitle_calls = []

    def get_subtitle_tracks(self, bvid, cid):
        self.subtitle_calls.append((bvid, cid))
        return self.tracks


def test_service_reports_quality_and_codec_fallback(monkeypatch, tmp_path):
    service = DownloadService(FakeAPI(), str(tmp_path))

    def fake_download(item, callback):
        service._downloader.last_video_stream = StreamInfo(id=64, codecid=7)
        callback(1.0, "视频下载完成")
        return str(tmp_path / "video.mp4")

    monkeypatch.setattr(service._downloader, "download", fake_download)
    item = DownloadItem(
        video_info=VideoInfo(bvid="BV1xx", cid=1),
        selected_quality=VideoQuality.Q1080P,
        selected_video_codec=12,
    )

    outcome = service.download(item, lambda _progress, _text: None)

    assert outcome.actual_quality == 64
    assert outcome.actual_video_codec == 7
    assert len(outcome.warnings) == 2


def test_service_discovers_subtitle_for_selected_page(monkeypatch, tmp_path):
    api = FakeAPI([SubtitleInfo(lan="zh-Hans", url="https://i0.hdslb.com/sub.json")])
    service = DownloadService(api, str(tmp_path))
    video_path = tmp_path / "video.mp4"

    def fake_download(item, callback):
        service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
        return str(video_path)

    monkeypatch.setattr(service._downloader, "download", fake_download)
    converted = []
    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert",
        lambda url, path: converted.append((url, path)),
    )
    item = DownloadItem(
        video_info=VideoInfo(bvid="BV1xx", cid=22),
        download_subtitle=True,
    )

    outcome = service.download(item, lambda _progress, _text: None)

    assert api.subtitle_calls == [("BV1xx", 22)]
    assert converted == [("https://i0.hdslb.com/sub.json", video_path.with_suffix(".srt"))]
    assert outcome.subtitle_paths == [str(video_path.with_suffix(".srt"))]
    assert outcome.warnings == []


def test_service_keeps_video_success_when_companion_fails(monkeypatch, tmp_path):
    service = DownloadService(FakeAPI(), str(tmp_path))

    def fake_download(item, callback):
        service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
        return str(tmp_path / "video.mp4")

    monkeypatch.setattr(service._downloader, "download", fake_download)
    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.DanmakuDownloader.download_and_convert",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    item = DownloadItem(
        video_info=VideoInfo(bvid="BV1xx", cid=1),
        download_danmaku=True,
    )

    outcome = service.download(item, lambda _progress, _text: None)

    assert outcome.video_path.endswith("video.mp4")
    assert outcome.is_partial
    assert "弹幕下载失败" in outcome.warnings[0]
