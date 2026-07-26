"""Pydantic data models for Bilibili API responses."""

from enum import Enum, IntEnum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VIDEO_QUALITY_LABELS = {
    6: "240P",
    16: "360P",
    32: "480P",
    64: "720P",
    80: "1080P",
    112: "1080P+",
    116: "1080P60",
    120: "4K",
    125: "HDR",
    126: "Dolby Vision",
    127: "8K",
}


class VideoQuality(IntEnum):
    """Bilibili video quality codes."""
    Q240P = 6
    Q360P = 16
    Q480P = 32
    Q720P = 64
    Q1080P = 80
    Q1080P_PLUS = 112
    Q1080P60 = 116
    Q4K = 120
    QHDR = 125
    Q_DOLBY = 126
    Q8K = 127

    @property
    def label(self) -> str:
        return _VIDEO_QUALITY_LABELS.get(self.value, f"Unknown({self.value})")


class TaskStatus(str, Enum):
    """Durable lifecycle states for a download task."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputMode(str, Enum):
    """Media artifact produced by a download task."""

    VIDEO = "video"
    AUDIO = "audio"


VIDEO_CODEC_MAP = {
    7: "AVC/H.264",
    12: "HEVC/H.265",
    13: "AV1",
}

AUDIO_CODEC_MAP = {
    0: "M4A",
    30280: "AAC 192kbps",
    30250: "Dolby Atmos",
    30251: "Hi-Res FLAC",
    30285: "Dolby Atmos",
    30216: "AAC 64kbps",
}


class StreamInfo(BaseModel):
    """A single video or audio stream from the playurl response."""
    id: int = 0
    base_url: str = ""
    backup_url: list[str] = Field(default_factory=list)
    codecid: int = 7
    bandwidth: int = 0
    mime_type: str = "video/mp4"
    size: int = 0

    @property
    def codec_label(self) -> str:
        return VIDEO_CODEC_MAP.get(self.codecid, f"Codec({self.codecid})")


class SubtitleInfo(BaseModel):
    """Subtitle track info from playurl response."""
    lan: str = ""
    lan_doc: str = ""
    url: str = ""


class VideoPage(BaseModel):
    """A single page (part) of a multi-part video."""
    cid: int = 0
    page: int = 1
    part: str = ""
    duration: int = 0
    first_frame: str = ""


class VideoInfo(BaseModel):
    """Parsed video metadata from /x/web-interface/view."""
    bvid: str = ""
    cid: int = 0
    aid: int = 0
    title: str = ""
    desc: str = ""
    duration: int = 0  # seconds
    author: str = ""
    owner_name: str = ""
    cover_url: str = ""
    pages: list[VideoPage] = Field(default_factory=list)
    subtitle_list: list[SubtitleInfo] = Field(default_factory=list)
    pubdate: int = 0
    source_url: str = ""
    source_type: str = "video"
    collection_title: str = ""

    # Stream info (populated after playurl call)
    video_streams: list[StreamInfo] = Field(default_factory=list)
    audio_streams: list[StreamInfo] = Field(default_factory=list)
    has_dolby: bool = False
    has_hdr: bool = False

    @property
    def duration_str(self) -> str:
        mins = self.duration // 60
        secs = self.duration % 60
        return f"{mins:02d}:{secs:02d}"

    @property
    def is_multi_part(self) -> bool:
        return len(self.pages) > 1

    def for_page(self, page: VideoPage) -> "VideoInfo":
        """Return an independent video snapshot targeting one page."""
        return self.model_copy(
            update={
                "cid": page.cid,
                "duration": page.duration or self.duration,
                "video_streams": [],
                "audio_streams": [],
                "subtitle_list": [],
            },
            deep=True,
        )


class ContentCollection(BaseModel):
    """A resolved user-facing source containing one or more videos."""

    title: str = ""
    source_type: str = "video"
    source_url: str = ""
    items: list[VideoInfo] = Field(default_factory=list)


class DownloadItem(BaseModel):
    """Tracks a single download task."""
    video_info: VideoInfo
    selected_quality: VideoQuality = VideoQuality.Q1080P
    selected_video_codec: int = 12  # HEVC default
    selected_audio_quality: int = 30280  # AAC 192kbps
    output_path: str = ""
    output_mode: OutputMode = OutputMode.VIDEO
    path_template: str = "{title}{part_suffix}"
    download_danmaku: bool = False
    download_subtitle: bool = False
    download_all_subtitles: bool = False
    download_cover: bool = False
    download_metadata: bool = False
    selected_subtitle_lan: str = "zh-Hans"
    status: TaskStatus = TaskStatus.QUEUED
    progress: float = 0.0
    status_text: str = ""
    error: Optional[str] = None
    file_size: int = 0

    @property
    def filename(self) -> str:
        return self.relative_output_path.name

    @property
    def relative_output_path(self) -> Path:
        """Render the configured safe relative path for this task."""
        from bilibili_downloader.utils.validators import render_path_template

        info = self.video_info
        page = next((page for page in info.pages if page.cid == info.cid), None)
        part = page.part if page else ""
        page_number = page.page if page else 1
        suffix = ".m4a" if self.output_mode == OutputMode.AUDIO else ".mp4"
        stem = render_path_template(
            self.path_template,
            {
                "title": info.title,
                "author": info.author or info.owner_name,
                "bvid": info.bvid,
                "page": str(page_number),
                "part": part,
                "part_suffix": f"_{part}" if info.is_multi_part and part else "",
                "collection": info.collection_title,
                "quality": self.selected_quality.label,
                "codec": VIDEO_CODEC_MAP.get(
                    self.selected_video_codec, str(self.selected_video_codec)
                ),
            },
        )
        return stem.with_name(f"{stem.name}{suffix}")

    @property
    def fingerprint(self) -> str:
        """Return a stable identity used for duplicate detection."""
        return ":".join(
            [
                self.video_info.bvid,
                str(self.video_info.cid),
                str(self.selected_quality.value),
                str(self.selected_video_codec),
                str(self.selected_audio_quality),
                self.output_mode.value,
                self.relative_output_path.as_posix(),
                str(int(self.download_danmaku)),
                str(int(self.download_subtitle)),
                str(int(self.download_all_subtitles)),
                str(int(self.download_cover)),
                str(int(self.download_metadata)),
                self.selected_subtitle_lan,
            ]
        )


class DownloadOutcome(BaseModel):
    """User-visible result for the complete media download workflow."""

    video_path: str
    danmaku_path: Optional[str] = None
    subtitle_paths: list[str] = Field(default_factory=list)
    cover_path: Optional[str] = None
    metadata_path: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    actual_quality: Optional[int] = None
    actual_video_codec: Optional[int] = None
    actual_audio_quality: Optional[int] = None

    @property
    def is_partial(self) -> bool:
        return bool(self.warnings)


class AppSettings(BaseModel):
    """Application settings persisted to JSON."""
    model_config = ConfigDict(validate_assignment=True)

    output_dir: str = Field(default_factory=lambda: str(Path.home() / "Downloads" / "bilibili"))
    default_quality: VideoQuality = VideoQuality.Q1080P
    default_video_codec: int = 12  # HEVC
    default_audio_quality: int = 30280  # AAC 192kbps
    default_output_mode: OutputMode = OutputMode.VIDEO
    path_template: str = "{title}{part_suffix}"
    download_danmaku: bool = False
    download_subtitle: bool = False
    download_all_subtitles: bool = False
    download_cover: bool = False
    download_metadata: bool = False
    sessdata: str = ""
    ffmpeg_path: str = ""
    max_concurrent_downloads: int = Field(default=3, ge=1, le=8)
    last_login_at: Optional[str] = None

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("output_dir cannot be empty")
        return value

    @field_validator("default_video_codec")
    @classmethod
    def validate_video_codec(cls, value: int) -> int:
        if value not in VIDEO_CODEC_MAP:
            raise ValueError("unsupported default_video_codec")
        return value

    @field_validator("default_audio_quality")
    @classmethod
    def validate_audio_quality(cls, value: int) -> int:
        if value not in AUDIO_CODEC_MAP:
            raise ValueError("unsupported default_audio_quality")
        return value

    @field_validator("path_template")
    @classmethod
    def validate_path_template(cls, value: str) -> str:
        from bilibili_downloader.utils.validators import render_path_template

        value = value.strip()
        if not value:
            raise ValueError("path_template cannot be empty")
        render_path_template(
            value,
            {
                "title": "title",
                "author": "author",
                "bvid": "BV1xx",
                "page": "1",
                "part": "part",
                "part_suffix": "_part",
                "collection": "collection",
                "quality": "1080P",
                "codec": "HEVC",
            },
        )
        return value
