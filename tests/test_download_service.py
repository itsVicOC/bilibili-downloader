"""Tests for the shared CLI/GUI download workflow."""

import io
import json

import httpx
from PIL import Image

from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.metadata import download_cover, write_metadata
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
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


def test_service_reports_audio_quality_fallback(monkeypatch, tmp_path):
    service = DownloadService(FakeAPI(), str(tmp_path))

    def fake_download(item, callback):
        service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
        service._downloader.last_audio_stream = StreamInfo(id=30216)
        return str(tmp_path / "video.mp4")

    monkeypatch.setattr(service._downloader, "download", fake_download)
    item = DownloadItem(video_info=VideoInfo(bvid="BV1xx", cid=1))

    outcome = service.download(item, lambda _progress, _text: None)

    assert outcome.actual_audio_quality == 30216
    assert outcome.warnings == [
        "请求的音频规格不可用，实际使用音频代码 30216"
    ]


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


def test_service_downloads_all_unique_subtitle_languages(monkeypatch, tmp_path):
    tracks = [
        SubtitleInfo(lan="zh-Hans", lan_doc="中文", url="https://i0.hdslb.com/a"),
        SubtitleInfo(lan="en-US", lan_doc="English", url="https://i0.hdslb.com/b"),
        SubtitleInfo(lan="zh-Hans", lan_doc="中文", url="https://i0.hdslb.com/c"),
    ]
    service = DownloadService(FakeAPI(tracks), str(tmp_path))
    video_path = tmp_path / "video.mp4"

    def fake_download(item, callback):
        service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
        return str(video_path)

    converted = []
    monkeypatch.setattr(service._downloader, "download", fake_download)
    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert",
        lambda url, path: converted.append((url, path.name)),
    )
    item = DownloadItem(
        video_info=VideoInfo(bvid="BV1xx", cid=22),
        download_subtitle=True,
        download_all_subtitles=True,
    )

    outcome = service.download(item, lambda _progress, _text: None)

    assert converted == [
        ("https://i0.hdslb.com/a", "video.zh-Hans.srt"),
        ("https://i0.hdslb.com/b", "video.en-US.srt"),
    ]
    assert len(outcome.subtitle_paths) == 2


def test_service_writes_metadata_manifest(monkeypatch, tmp_path):
    service = DownloadService(FakeAPI(), str(tmp_path))
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    def fake_download(item, callback):
        service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
        return str(video_path)

    monkeypatch.setattr(service._downloader, "download", fake_download)
    item = DownloadItem(
        video_info=VideoInfo(
            bvid="BV1xx", cid=1, title="Example", author="Creator"
        ),
        download_metadata=True,
    )

    outcome = service.download(item, lambda _progress, _text: None)

    assert outcome.metadata_path == str(tmp_path / "video.info.json")
    payload = json.loads((tmp_path / "video.info.json").read_text(encoding="utf-8"))
    assert payload["video"]["title"] == "Example"
    assert payload["video"]["author"] == "Creator"
    assert payload["artifact"]["requested_audio_quality"] == 30280


def test_metadata_manifest_uses_portable_companion_names(tmp_path):
    media_path = tmp_path / "archive" / "video.mp4"
    media_path.parent.mkdir()
    item = DownloadItem(video_info=VideoInfo(bvid="BV1xx", cid=1))
    outcome = DownloadOutcome(
        video_path=str(media_path),
        danmaku_path=str(media_path.with_suffix(".ass")),
        subtitle_paths=[str(media_path.with_name("video.zh-Hans.srt"))],
        cover_path=str(media_path.with_name("video.cover.jpg")),
    )

    manifest = write_metadata(item, outcome, media_path)
    artifact = json.loads(manifest.read_text(encoding="utf-8"))["artifact"]

    assert artifact["danmaku"] == "video.ass"
    assert artifact["subtitles"] == ["video.zh-Hans.srt"]
    assert artifact["cover"] == "video.cover.jpg"


def test_cover_download_validates_and_preserves_image_format(monkeypatch, tmp_path):
    content = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(content, format="PNG")
    png_bytes = content.getvalue()
    real_client = httpx.Client
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        return httpx.Response(200, content=png_bytes, request=request)

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(
        "bilibili_downloader.core.metadata.httpx.Client", client_factory
    )
    media_path = tmp_path / "video.mp4"

    cover_path = download_cover(
        "http://i0.hdslb.com/video-cover.png", media_path
    )

    assert requested_urls == ["https://i0.hdslb.com/video-cover.png"]
    assert cover_path == tmp_path / "video.cover.png"
    with Image.open(cover_path) as image:
        assert image.size == (2, 2)
