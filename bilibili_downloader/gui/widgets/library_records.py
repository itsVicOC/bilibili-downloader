"""Browse and search projections of the existing download inventory."""

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from bilibili_downloader.core.library import FILE_STATES
from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    VIDEO_CODEC_MAP,
    ContentKind,
    OutputMode,
    VideoQuality,
)


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold().replace("\\", "/")


def natural_key(text):
    return tuple(int(part) if i % 2 else part for i, part in enumerate(re.split(r"(\d+)", normalize(text))))


def file_size(value):
    if value is None:
        return "未知"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def media_state(media, outcome):
    state = media["state"] if media else "unchecked"
    if state not in {"missing", "inaccessible", "recycled"} and outcome.media_verification.get("valid") is False:
        return "媒体异常"
    return FILE_STATES.get(state, "待检查")


def _download_time(value):
    try:
        date = datetime.fromisoformat(value)
        return (date if date.tzinfo else date.replace(tzinfo=timezone.utc)).timestamp()
    except (TypeError, ValueError, OSError, OverflowError):
        return float("-inf")


_QUALITY_LABELS = {quality.value: quality.label for quality in VideoQuality}


class LibraryRecord:
    def __init__(self, asset):
        self.asset = asset
        self.id = asset["id"]
        self.media = next((entry for entry in asset["files"] if entry["kind"] == "media"), {})
        self.cover = next((entry for entry in asset["files"] if entry["kind"] == "cover"), None)
        self.path = Path(self.media.get("path", asset["path"]))
        item, outcome = asset["item"], asset["outcome"]
        info = item.video_info
        part = next((part for part in info.pages if part.cid == info.cid), None)
        self.audio = item.output_mode == OutputMode.AUDIO
        self.duration = info.duration
        self.author = info.author or info.owner_name
        self.collection = info.collection_title or info.series_title or info.season_title
        self.title = item.display_title or self.path.name
        if info.content_kind == ContentKind.BANGUMI_EPISODE:
            episode_title = info.episode_title or info.title or self.path.name
            self.title = " · ".join(filter(None, (info.episode_number, episode_title)))
        seen = {normalize(self.title.strip()), normalize(info.title.strip()), ""}
        context = []
        for label in (self.author, info.season_title or self.collection):
            key = normalize(label.strip())
            if key not in seen:
                context.append(label.strip())
                seen.add(key)
        self.subtitle = " · ".join(context)
        self.download_time = _download_time(asset.get("created_at"))
        self.title_key = natural_key(self.title)
        self.search_text = normalize(" ".join((
            item.display_title, info.title, info.author, info.owner_name,
            info.collection_title, info.series_title, info.season_title, info.section_title,
            info.episode_title, info.episode_number, info.bvid,
            f"av{info.aid}" if info.aid else "", f"ep{info.episode_id}" if info.episode_id else "",
            info.canonical_url or "", f"P{part.page} {part.part}" if part else "",
            str(self.path), *(entry["path"] for entry in asset["files"]),
        )))
        if self.audio:
            self.kind, self.codec = "仅音频", AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, "规格未知")
        else:
            quality = _QUALITY_LABELS.get(outcome.actual_quality, "规格未知")
            self.kind, self.codec = f"视频 · {quality}", VIDEO_CODEC_MAP.get(outcome.actual_video_codec, "编码未知")

    @property
    def size(self):
        return self.media.get("size")

    @property
    def state(self):
        return media_state(self.media, self.asset["outcome"])

    def table_row(self):
        return [
            "\n".join(filter(None, (self.title, self.subtitle))),
            f"{self.kind}\n{self.codec}",
            file_size(self.size), self.state, str(self.path.parent),
        ]

    def table_tooltip(self):
        lines = [self.title]
        if self.subtitle:
            lines.append(self.subtitle)
        if self.path.name != self.title:
            lines.append(self.path.name)
        lines.append(str(self.path))
        return "\n".join(lines)

    def order_key(self, sort):
        if sort == "title":
            return self.title_key, -self.id
        if sort == "size":
            return -(self.size if self.size is not None else -1), -self.id
        return -self.download_time, -self.id
