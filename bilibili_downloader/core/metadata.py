"""Companion cover and metadata artifact writers."""

import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from PIL import Image, UnidentifiedImageError

from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.core.models import DownloadItem, DownloadOutcome
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

MAX_COVER_BYTES = 10 * 1024 * 1024
MAX_COVER_PIXELS = 25_000_000


def download_cover(url: str, media_path: Path) -> Path:
    """Download and validate a Bilibili cover beside the media file."""
    current_url = trusted_https_url(
        url,
        BILIBILI_RESOURCE_HOSTS,
        upgrade_http=True,
    )
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}
    content = bytearray()
    with httpx.Client(headers=headers, timeout=30.0, follow_redirects=False) as client:
        for _ in range(8):
            with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    current_url = trusted_https_url(
                        urljoin(current_url, location), BILIBILI_RESOURCE_HOSTS
                    )
                    continue
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_COVER_BYTES:
                        raise RuntimeError("封面文件过大")
                break
        else:
            raise RuntimeError("封面地址重定向次数过多")

    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > MAX_COVER_PIXELS:
                raise RuntimeError("封面像素尺寸过大")
            image_format = (image.format or "JPEG").lower()
            image.verify()
    except UnidentifiedImageError as exc:
        raise RuntimeError("封面不是有效图片") from exc

    extension = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}.get(
        image_format, ".jpg"
    )
    destination = media_path.with_name(f"{media_path.stem}.cover{extension}")
    _atomic_write_bytes(destination, bytes(content))
    return destination


def write_metadata(
    item: DownloadItem,
    outcome: DownloadOutcome,
    media_path: Path,
) -> Path:
    """Write a portable JSON manifest beside a downloaded artifact."""
    info = item.video_info
    page = next((entry for entry in info.pages if entry.cid == info.cid), None)
    payload = {
        "schema_version": 1,
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "url": info.source_url or f"https://www.bilibili.com/video/{info.bvid}",
            "type": info.source_type,
            "collection": info.collection_title or None,
        },
        "video": {
            "bvid": info.bvid,
            "aid": info.aid,
            "cid": info.cid,
            "title": info.title,
            "description": info.desc,
            "author": info.author or info.owner_name,
            "duration": info.duration,
            "published_at": info.pubdate,
            "cover_url": info.cover_url,
            "page": page.page if page else 1,
            "part": page.part if page else "",
        },
        "artifact": {
            "file": media_path.name,
            "mode": item.output_mode.value,
            "requested_quality": item.selected_quality.value,
            "actual_quality": outcome.actual_quality,
            "requested_video_codec": item.selected_video_codec,
            "actual_video_codec": outcome.actual_video_codec,
            "requested_audio_quality": item.selected_audio_quality,
            "actual_audio_quality": outcome.actual_audio_quality,
            "danmaku": _artifact_name(outcome.danmaku_path),
            "subtitles": [
                _artifact_name(path) for path in outcome.subtitle_paths
            ],
            "cover": _artifact_name(outcome.cover_path),
            "warnings": outcome.warnings,
        },
    }
    destination = media_path.with_name(f"{media_path.stem}.info.json")
    _atomic_write_bytes(
        destination,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return destination


def _artifact_name(path: str | None) -> str | None:
    return Path(path).name if path else None


def _atomic_write_bytes(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
