"""Pydantic data models for Bilibili API responses."""

from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field


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
        return {
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
        }.get(self.value, f"Unknown({self.value})")


VIDEO_CODEC_MAP = {
    7: "AVC/H.264",
    12: "HEVC/H.265",
    13: "AV1",
}

AUDIO_CODEC_MAP = {
    0: "M4A",
    30280: "AAC 192kbps",
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


class DownloadItem(BaseModel):
    """Tracks a single download task."""
    video_info: VideoInfo
    selected_quality: VideoQuality = VideoQuality.Q1080P
    selected_video_codec: int = 12  # HEVC default
    selected_audio_quality: int = 30280  # AAC 192kbps
    output_path: str = ""
    download_danmaku: bool = False
    download_subtitle: bool = False
    selected_subtitle_lan: str = "zh-Hans"
    status: str = "pending"  # pending/downloading/merging/done/failed
    progress: float = 0.0
    status_text: str = ""
    error: Optional[str] = None
    file_size: int = 0

    @property
    def filename(self) -> str:
        from src.utils.validators import sanitize_filename

        info = self.video_info
        safe_title = sanitize_filename(info.title)
        # Use the selected page's part name
        selected_part = ""
        if info.is_multi_part:
            for page in info.pages:
                if page.cid == info.cid:
                    selected_part = sanitize_filename(page.part)
                    break
        if selected_part:
            return f"{safe_title}_{selected_part}.mp4"
        # Single-part or fallback: use title only
        return f"{safe_title}.mp4"


class AppSettings(BaseModel):
    """Application settings persisted to JSON."""
    output_dir: str = "./downloads"
    default_quality: VideoQuality = VideoQuality.Q1080P
    default_video_codec: int = 12  # HEVC
    download_danmaku: bool = False
    download_subtitle: bool = False
    sessdata: str = ""
    ffmpeg_path: str = ""
    max_concurrent_downloads: int = 3
    dark_mode: bool = True
    last_login_at: Optional[str] = None
