"""Live identities are intentionally independent from finite video tasks."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class LiveState(str, Enum):
    DISABLED = "disabled"
    WAITING = "waiting"
    PREPARING = "preparing"
    QUEUED = "queued"
    RECORDING = "recording"
    RECONNECTING = "reconnecting"
    FINALIZING = "finalizing"
    ERROR = "error"


LIVE_STATE_LABELS = {
    LiveState.DISABLED: "未监控",
    LiveState.WAITING: "等待开播",
    LiveState.PREPARING: "准备录制",
    LiveState.QUEUED: "等待录制名额",
    LiveState.RECORDING: "录制中",
    LiveState.RECONNECTING: "等待重连",
    LiveState.FINALIZING: "正在收尾",
    LiveState.ERROR: "需要处理",
}


class LiveRoom(BaseModel):
    room_id: int = Field(gt=0)
    short_id: int = 0
    uid: int = 0
    author: str = ""
    title: str = ""
    live_status: int = 0
    live_time: str = ""

    @property
    def broadcast_key(self) -> str:
        return f"{self.room_id}:{self.live_time or 'unknown'}"


class LiveQuality(BaseModel):
    qn: int
    label: str


class LiveStream(BaseModel):
    # This type is ephemeral: never serialize it into a repository or manifest.
    url: str = Field(repr=False)
    format: str
    quality: int
    quality_label: str = ""
    codec: str = "avc"
    qualities: list[LiveQuality] = Field(default_factory=list)
    warning: str = ""


class LiveSubscription(BaseModel):
    room: LiveRoom
    enabled: bool = True
    quality: int = Field(default=0, ge=0)  # 0 = best available
    output_dir: str
    segment_seconds: int = Field(default=1800, ge=60, le=86400)
    skipped_broadcast: str = ""


class RecordingSegment(BaseModel):
    path: str
    duration: float = Field(default=0, ge=0)
    size: int = Field(default=0, ge=0)
    finalized_at: str
    quality: int = 0
    codec: str = "avc"
    format: str = ""


class RecordingSession(BaseModel):
    id: str
    room: LiveRoom
    directory: str
    started_at: str
    ended_at: str = ""
    status: str = "recording"
    quality: int = 0
    quality_label: str = ""
    codec: str = "avc"
    format: str = ""
    warnings: list[str] = Field(default_factory=list)
    gaps: list[dict[str, str]] = Field(default_factory=list)
    segments: list[RecordingSegment] = Field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(segment.size for segment in self.segments)


class LiveSettings(BaseModel):
    recorder_path: str = ""
    output_dir: str = Field(
        default_factory=lambda: str(Path.home() / "Downloads" / "bilibili" / "live")
    )
    max_concurrent: int = Field(default=2, ge=1, le=4)
    segment_seconds: int = Field(default=1800, ge=60, le=86400)
    minimum_free_bytes: int = Field(default=2 * 1024**3, ge=1024**3)
