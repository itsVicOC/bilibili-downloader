"""Resolvers for single and batch Bilibili download inputs."""

import re
from urllib.parse import parse_qs, urlparse

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.models import ContentCollection, VideoInfo
from bilibili_downloader.utils.validators import (
    extract_aid,
    extract_bangumi_id,
    extract_bvid,
    is_short_link,
    resolve_short_link,
    resolve_short_url,
)

SPACE_LIST_PATTERN = re.compile(
    r"^/(\d+)/(?:lists/(\d+)|favlist|channel/(?:series|collection)detail)",
    re.IGNORECASE,
)
MEDIA_LIST_PATH_PATTERN = re.compile(
    r"/(?:medialist/(?:detail/ml|play/))(\d+)", re.IGNORECASE
)


class BatchResolveError(RuntimeError):
    """Raised when a single pasted input cannot be resolved to a video."""


class BatchResolver:
    """Resolve pasted Bilibili inputs into video metadata."""

    def __init__(self, client: BilibiliAPIClient):
        self._client = client

    def resolve_text(self, text: str) -> list[VideoInfo]:
        """Resolve one or more newline-separated inputs."""
        results = []
        for line in _split_inputs(text):
            results.extend(ContentSourceResolver(self._client).resolve(line).items)
        return results

    def resolve_one(self, text: str) -> VideoInfo:
        """Resolve one BV/AV/full URL/b23 short link to ``VideoInfo``."""
        source = text.strip()
        if not source:
            raise BatchResolveError("输入为空")

        if is_short_link(source):
            resolved = resolve_short_url(source)
            if not resolved:
                # Keep the historical BV-only helper as a compatibility path.
                bvid = resolve_short_link(source)
                if bvid:
                    return self._client.get_video_info(bvid)
                raise BatchResolveError("无法展开 b23.tv 短链")
            source = resolved

        if is_collection_source(source):
            raise BatchResolveError("这是合集或收藏夹链接，请使用批量导入")

        bangumi = extract_bangumi_id(source)
        if bangumi:
            kind, content_id = bangumi
            if kind != "ep":
                raise BatchResolveError("这是番剧季度或媒体页，请使用批量导入")
            return self._client.get_bangumi_episode(content_id)

        bvid = extract_bvid(source)
        if bvid:
            return self._client.get_video_info(bvid)

        aid = extract_aid(source)
        if aid:
            return self._client.get_video_info_by_aid(aid)

        raise BatchResolveError("无法识别 BV、AV、ep 或受支持的 B站链接")


class ContentSourceResolver:
    """Resolve videos, favorites and UP-owned lists into one collection model."""

    def __init__(self, client: BilibiliAPIClient):
        self._client = client

    def resolve(self, text: str) -> ContentCollection:
        source = text.strip()
        if not source:
            raise BatchResolveError("输入为空")
        if is_short_link(source):
            resolved = resolve_short_url(source)
            if not resolved:
                raise BatchResolveError("无法展开 b23.tv 短链")
            source = resolved

        bangumi = extract_bangumi_id(source)
        if bangumi:
            kind, content_id = bangumi
            if kind == "ep":
                info = self._client.get_bangumi_episode(content_id)
                return ContentCollection(
                    title=info.title,
                    source_type="bangumi_episode",
                    source_url=source,
                    items=[info],
                )
            if kind == "ss":
                return self._client.get_bangumi_season(content_id)
            return self._client.get_bangumi_media(content_id)

        if not is_collection_source(source):
            info = BatchResolver(self._client).resolve_one(source)
            info = info.model_copy(
                update={
                    "source_url": source if source.startswith("https://") else "",
                    "source_type": info.source_type,
                },
                deep=True,
            )
            return ContentCollection(
                title=info.title,
                source_type=info.source_type,
                source_url=source,
                items=[info],
            )

        kind, source_id, owner = _collection_reference(source)
        if kind == "favorite":
            return self._client.get_favorite_collection(source_id, source)
        if kind == "video_season":
            return self._client.get_video_season_collection(owner, source)
        if kind == "series":
            return self._client.get_series_collection(owner, source_id, source)
        return self._client.get_season_collection(owner, source_id, source)


def _collection_reference(source: str) -> tuple[str, int, int | str | None]:
    parsed = urlparse(source)
    query = parse_qs(parsed.query)
    path = parsed.path.lower()
    media = MEDIA_LIST_PATH_PATTERN.search(path)
    if media:
        return "favorite", int(media.group(1)), None
    space = SPACE_LIST_PATTERN.match(path)
    if space:
        mid = int(space.group(1))
        if "/favlist" in path:
            favorite = _first_int(query, "fid", "media_id")
            if favorite is None:
                raise BatchResolveError("收藏夹链接缺少 fid")
            return "favorite", favorite, None
        source_id = int(space.group(2)) if space.group(2) else _first_int(query, "sid", "series_id")
        if source_id is None:
            raise BatchResolveError("空间列表链接缺少列表编号")
        source_type = (query.get("type") or ["season"])[0].lower()
        kind = "series" if source_type == "series" or "seriesdetail" in path else "season"
        return kind, source_id, mid
    bvid, season = extract_bvid(source), _first_int(query, "sid", "season_id")
    if bvid and season is not None:
        return "video_season", season, bvid
    favorite = _first_int(query, "fid", "media_id", "mlid")
    if favorite is not None and "medialist" in path:
        return "favorite", favorite, None
    raise BatchResolveError("无法从该合集链接识别列表编号")


def _split_inputs(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def batch_source_key(source: str) -> tuple | None:
    """Return a stable identity for a supported batch source, without a network request."""
    source = source.strip()
    if is_collection_source(source):
        bangumi = extract_bangumi_id(source)
        if bangumi:
            return bangumi
        try:
            kind, source_id, owner = _collection_reference(source)
        except (BatchResolveError, ValueError):
            return "collection", source.lower()
        if kind == "series":
            return kind, source_id, owner
        return ("season" if kind == "video_season" else kind), source_id
    if bvid := extract_bvid(source):
        return "bvid", bvid.lower()
    if aid := extract_aid(source):
        return "aid", aid
    if bangumi := extract_bangumi_id(source):
        return bangumi
    if is_short_link(source):
        return "short", source.lower()
    return None


def classify_batch_inputs(text: str) -> tuple[list[str], list[str]]:
    """Return unique supported inputs and unrecognized lines."""
    valid = []
    invalid = []
    seen = set()
    for source in _split_inputs(text):
        identity = batch_source_key(source)
        if identity is None:
            invalid.append(source)
            continue

        if identity not in seen:
            seen.add(identity)
            valid.append(source)
    return valid, invalid


def is_collection_source(text: str) -> bool:
    source = text.strip()
    bangumi = extract_bangumi_id(source)
    if bangumi:
        return bangumi[0] in {"ss", "md"}
    try:
        parsed = urlparse(source)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host not in ("www.bilibili.com", "space.bilibili.com", "m.bilibili.com"):
        return False
    query = parse_qs(parsed.query)
    path = parsed.path.lower()
    if "medialist" in path or "/favlist" in path or "/lists/" in path:
        return True
    if "seriesdetail" in path or "collectiondetail" in path:
        return True
    return bool(
        extract_bvid(source)
        and _first_int(query, "sid", "season_id") is not None
    )


def _first_int(query: dict[str, list[str]], *keys: str) -> int | None:
    for key in keys:
        values = query.get(key) or []
        if values and values[0].isdigit():
            return int(values[0])
    return None
