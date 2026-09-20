"""Parsing helpers and access controls for Bilibili PGC (bangumi) data."""

from __future__ import annotations

import json
from enum import Enum
from typing import Iterable

from bilibili_downloader.core.models import (
    ContentCollection,
    ContentKind,
    VideoInfo,
    VideoPage,
)


class BangumiAccessReason(str, Enum):
    LOGIN_REQUIRED = "login_required"
    FULL_ACCESS_REQUIRED = "full_access_required"
    PREVIEW_ONLY = "preview_only"
    GEO_BLOCKED = "geo_blocked"
    UNAVAILABLE = "unavailable"


class BangumiAccessError(RuntimeError):
    """Raised before download when Bilibili does not grant full playback."""

    def __init__(self, reason: BangumiAccessReason, message: str = ""):
        self.reason = reason
        super().__init__(message or reason.value)


def parse_bangumi_collection(
    data: dict,
    source_url: str,
) -> ContentCollection:
    """Convert a season response into ordered main and extra episodes."""
    series_title = (
        (data.get("series") or {}).get("series_title")
        or data.get("series_title")
        or data.get("title")
        or "番剧"
    )
    season_title = data.get("season_title") or data.get("title") or "本季"
    season_id = _as_int(data.get("season_id"))
    media_id = _as_int(data.get("media_id"))
    owner = (data.get("up_info") or {}).get("uname") or "哔哩哔哩番剧"

    items: list[VideoInfo] = []
    seen: set[int] = set()
    sections: list[tuple[str, bool, Iterable[dict]]] = [
        ("正片", True, data.get("episodes") or []),
    ]
    for section in data.get("section") or []:
        if not isinstance(section, dict):
            continue
        sections.append(
            (
                str(section.get("title") or "附加内容"),
                False,
                section.get("episodes") or [],
            )
        )

    for section_title, is_main, episodes in sections:
        for index, raw in enumerate(episodes, 1):
            if not isinstance(raw, dict):
                continue
            episode_id = _as_int(raw.get("id") or raw.get("ep_id"))
            if not episode_id or episode_id in seen:
                continue
            seen.add(episode_id)
            items.append(
                _parse_episode(
                    raw,
                    series_title=series_title,
                    season_title=season_title,
                    section_title=section_title,
                    is_main=is_main,
                    section_index=index,
                    season_id=season_id,
                    media_id=media_id,
                    owner=owner,
                )
            )

    if not items:
        raise RuntimeError("该番剧没有可解析的剧集")
    return ContentCollection(
        title=season_title,
        source_type="bangumi_season",
        source_url=source_url,
        items=items,
    )


def find_bangumi_episode(collection: ContentCollection, episode_id: int) -> VideoInfo:
    for item in collection.items:
        if item.episode_id == episode_id:
            return item
    raise RuntimeError(f"番剧中未找到剧集 ep{episode_id}")


def normalize_pgc_playurl(payload: dict) -> tuple[dict, int]:
    """Unwrap known PGC playurl response layouts and enforce full access."""
    layers = [payload]
    data = payload
    for wrapper in ("raw", "data", "result"):
        if isinstance(data.get(wrapper), dict):
            data = data[wrapper]
            layers.append(data)
    status_code = next(
        (_as_int(layer.get("code")) for layer in layers if _as_int(layer.get("code"))),
        0,
    )
    access_data = {"layers": layers}

    if _is_geo_blocked(access_data):
        raise BangumiAccessError(
            BangumiAccessReason.GEO_BLOCKED,
            "该番剧受地区版权限制，BiliFlow 不会绕过地区限制。",
        )
    if status_code == -10403:
        raise BangumiAccessError(
            BangumiAccessReason.FULL_ACCESS_REQUIRED,
            "当前账号没有该剧集的完整播放权限。",
        )
    if status_code in {-101, -111}:
        raise BangumiAccessError(
            BangumiAccessReason.LOGIN_REQUIRED,
            "该剧集需要登录后访问。",
        )
    if status_code != 0:
        raise BangumiAccessError(
            BangumiAccessReason.UNAVAILABLE,
            "番剧播放接口未返回可用内容。",
        )

    play_state = _play_state(access_data).upper()
    preview_flag = _find_value(access_data, "is_preview")
    if play_state in {"PLAY_PREVIEW", "PREVIEW"} or preview_flag in {1, True, "1"}:
        raise BangumiAccessError(
            BangumiAccessReason.PREVIEW_ONLY,
            "当前账号只能试看，BiliFlow 不会把试看片段保存为完整剧集。",
        )
    if play_state in {"PLAY_NONE", "NONE"}:
        raise BangumiAccessError(
            BangumiAccessReason.FULL_ACCESS_REQUIRED,
            "当前账号未获得完整播放权限。",
        )

    has_full_access = play_state in {"PLAY_WHOLE", "WHOLE"} or preview_flag in {
        0,
        False,
        "0",
    }
    if not has_full_access:
        raise BangumiAccessError(
            BangumiAccessReason.FULL_ACCESS_REQUIRED,
            "平台未明确授予当前账号完整播放权限。",
        )

    video_info = data.get("video_info") if isinstance(data, dict) else None
    if not isinstance(video_info, dict):
        video_info = data if isinstance(data, dict) else {}
    if (
        _is_drm(access_data)
        or _is_drm(video_info)
        or not _has_media_formats(video_info)
    ):
        raise BangumiAccessError(
            BangumiAccessReason.UNAVAILABLE,
            "平台未提供可下载的完整、未加密媒体流。",
        )
    return video_info, status_code


def extract_assigned_json(page: str, marker: str) -> dict | None:
    """Decode a JSON object assigned after a trusted literal marker."""
    start = page.find(marker)
    if start < 0:
        return None
    tail = page[start + len(marker):].lstrip(" \t=:")
    try:
        value, _ = json.JSONDecoder().raw_decode(tail)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _parse_episode(
    raw: dict,
    *,
    series_title: str,
    season_title: str,
    section_title: str,
    is_main: bool,
    section_index: int,
    season_id: int,
    media_id: int,
    owner: str,
) -> VideoInfo:
    episode_id = _as_int(raw.get("id") or raw.get("ep_id"))
    cid = _as_int(raw.get("cid"))
    short_title = str(raw.get("title") or "").strip()
    long_title = str(raw.get("long_title") or raw.get("share_copy") or "").strip()
    episode_title = long_title or short_title or f"第 {section_index} 集"
    display_title = " ".join(value for value in (short_title, long_title) if value)
    duration = _as_int(raw.get("duration"))
    if duration > 10_000:
        duration //= 1000
    episode_number = _format_episode_number(section_index)
    canonical_url = f"https://www.bilibili.com/bangumi/play/ep{episode_id}"
    return VideoInfo(
        bvid=str(raw.get("bvid") or ""),
        aid=_as_int(raw.get("aid")),
        cid=cid,
        title=display_title or episode_title,
        desc=str(raw.get("desc") or raw.get("subtitle") or ""),
        duration=duration,
        author=owner,
        owner_name=owner,
        cover_url=str(raw.get("cover") or raw.get("square_cover") or ""),
        pages=[VideoPage(cid=cid, page=1, part=episode_title, duration=duration)],
        pubdate=_as_int(raw.get("pub_time") or raw.get("pubdate")),
        source_url=canonical_url,
        source_type="bangumi_episode",
        collection_title=season_title,
        content_kind=ContentKind.BANGUMI_EPISODE,
        episode_id=episode_id,
        season_id=season_id,
        media_id=media_id,
        series_title=series_title,
        season_title=season_title,
        section_title=section_title,
        episode_title=episode_title,
        episode_number=episode_number,
        episode_index=section_index,
        is_main_section=is_main,
    )


def _format_episode_number(index: int) -> str:
    """Use a stable two-digit ordinal within each section."""
    return f"{index:02d}"


def _play_state(data: dict) -> str:
    for key in ("play_video_type", "play_type"):
        value = _find_value(data, key)
        if isinstance(value, str):
            return value
    for key in ("play_check", "play_detail"):
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""


def _is_geo_blocked(data: dict) -> bool:
    for plugin in _find_lists(data, "plugins"):
        if not isinstance(plugin, dict) or plugin.get("name") != "AreaLimitPanel":
            continue
        return bool((plugin.get("config") or {}).get("is_block"))
    return False


def _has_media_formats(data: dict) -> bool:
    dash = data.get("dash") or {}
    return bool(dash.get("video"))


def _is_drm(data: dict) -> bool:
    drm_type = _find_value(data, "drm_tech_type")
    return drm_type not in {None, "", 0, "0", False}


def _find_value(value, target: str):
    if isinstance(value, dict):
        if target in value:
            return value[target]
        for child in value.values():
            result = _find_value(child, target)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _find_value(child, target)
            if result is not None:
                return result
    return None


def _find_lists(value, target: str) -> list:
    results = []
    if isinstance(value, dict):
        candidate = value.get(target)
        if isinstance(candidate, list):
            results.extend(candidate)
        for child in value.values():
            results.extend(_find_lists(child, target))
    elif isinstance(value, list):
        for child in value:
            results.extend(_find_lists(child, target))
    return results


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
