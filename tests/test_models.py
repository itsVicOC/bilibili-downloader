"""Tests for Pydantic data models."""

import pytest
from bilibili_downloader.core.models import (
    DownloadItem,
    StreamInfo,
    SubtitleInfo,
    VideoInfo,
    VideoPage,
    VideoQuality,
)


class TestVideoQuality:
    def test_labels(self):
        assert VideoQuality.Q240P.label == "240P"
        assert VideoQuality.Q720P.label == "720P"
        assert VideoQuality.Q1080P.label == "1080P"
        assert VideoQuality.Q4K.label == "4K"
        assert VideoQuality.QHDR.label == "HDR"
        assert VideoQuality.Q_DOLBY.label == "Dolby Vision"
        assert VideoQuality.Q8K.label == "8K"

    def test_int_values(self):
        assert VideoQuality.Q240P.value == 6
        assert VideoQuality.Q1080P.value == 80
        assert VideoQuality.Q4K.value == 120

    def test_from_int(self):
        q = VideoQuality(80)
        assert q == VideoQuality.Q1080P


class TestStreamInfo:
    def test_defaults(self):
        s = StreamInfo()
        assert s.id == 0
        assert s.codecid == 7
        assert s.backup_url == []
        assert s.codec_label == "AVC/H.264"

    def test_codec_labels(self):
        assert StreamInfo(codecid=7).codec_label == "AVC/H.264"
        assert StreamInfo(codecid=12).codec_label == "HEVC/H.265"
        assert StreamInfo(codecid=13).codec_label == "AV1"

    def test_backup_urls(self):
        s = StreamInfo(backup_url=["http://a.com", "http://b.com"])
        assert len(s.backup_url) == 2


class TestVideoInfo:
    def test_duration_str(self):
        info = VideoInfo(duration=125)
        assert info.duration_str == "02:05"

    def test_duration_str_long(self):
        info = VideoInfo(duration=3661)
        assert info.duration_str == "61:01"

    def test_is_multi_part(self):
        info = VideoInfo(pages=[VideoPage(cid=1, page=1, part="P1")])
        assert not info.is_multi_part

        info2 = VideoInfo(pages=[
            VideoPage(cid=1, page=1, part="P1"),
            VideoPage(cid=2, page=2, part="P2"),
        ])
        assert info2.is_multi_part

    def test_empty_defaults(self):
        info = VideoInfo()
        assert info.pages == []
        assert info.subtitle_list == []
        assert info.video_streams == []
        assert not info.is_multi_part


class TestDownloadItem:
    def test_filename_single(self):
        info = VideoInfo(title="Test Video", bvid="BV1xx", cid=123)
        item = DownloadItem(video_info=info)
        assert item.filename == "Test Video.mp4"

    def test_filename_multi(self):
        info = VideoInfo(
            title="Series Video",
            bvid="BV1xx",
            cid=200,
            pages=[
                VideoPage(cid=100, page=1, part="Part One"),
                VideoPage(cid=200, page=2, part="Part Two"),
            ],
        )
        item = DownloadItem(video_info=info)
        assert item.filename == "Series Video_Part Two.mp4"

    def test_status_defaults(self):
        info = VideoInfo(title="Test", bvid="BV1xx", cid=1)
        item = DownloadItem(video_info=info)
        assert item.status == "pending"
        assert item.progress == 0.0
        assert item.error is None


class TestAppSettings:
    def test_defaults(self):
        from bilibili_downloader.core.models import AppSettings
        s = AppSettings()
        assert s.output_dir == "./downloads"
        assert s.default_quality == VideoQuality.Q1080P
        assert s.max_concurrent_downloads == 3
        assert s.dark_mode is True
