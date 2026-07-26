"""Resolvers for single and batch Bilibili download inputs."""

import re
from urllib.parse import parse_qs, urlparse

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.models import ContentCollection, VideoInfo
from bilibili_downloader.utils.validators import (
    extract_aid,
    extract_bvid,
    is_short_link,
    resolve_short_link,
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

        if is_collection_source(source):
            raise BatchResolveError("这是合集或收藏夹链接，请使用批量导入")

        if is_short_link(source):
            bvid = resolve_short_link(source)
            if not bvid:
                raise BatchResolveError("无法展开 b23.tv 短链")
            return self._client.get_video_info(bvid)

        bvid = extract_bvid(source)
        if bvid:
            return self._client.get_video_info(bvid)

        aid = extract_aid(source)
        if aid:
            return self._client.get_video_info_by_aid(aid)

        raise BatchResolveError("无法识别 BV 号、AV 号或 B站视频链接")


class ContentSourceResolver:
    """Resolve videos, favorites and UP-owned lists into one collection model."""

    def __init__(self, client: BilibiliAPIClient):
        self._client = client

    def resolve(self, text: str) -> ContentCollection:
        source = text.strip()
        if not source:
            raise BatchResolveError("输入为空")
        if not is_collection_source(source):
            info = BatchResolver(self._client).resolve_one(source)
            info = info.model_copy(
                update={
                    "source_url": source if source.startswith("https://") else "",
                    "source_type": "video",
                },
                deep=True,
            )
            return ContentCollection(
                title=info.title,
                source_type="video",
                source_url=source,
                items=[info],
            )

        parsed = urlparse(source)
        query = parse_qs(parsed.query)
        path = parsed.path

        media_match = MEDIA_LIST_PATH_PATTERN.search(path)
        if media_match:
            return self._client.get_favorite_collection(
                int(media_match.group(1)), source
            )

        space_match = SPACE_LIST_PATTERN.match(path)
        if space_match:
            mid = int(space_match.group(1))
            list_id = space_match.group(2)
            if "/favlist" in path:
                favorite_id = _first_int(query, "fid", "media_id")
                if favorite_id is None:
                    raise BatchResolveError("收藏夹链接缺少 fid")
                return self._client.get_favorite_collection(favorite_id, source)
            source_id = (
                int(list_id)
                if list_id
                else _first_int(query, "sid", "series_id")
            )
            if source_id is None:
                raise BatchResolveError("空间列表链接缺少列表编号")
            source_type = (query.get("type") or ["season"])[0].lower()
            if source_type == "series" or "seriesdetail" in path:
                return self._client.get_series_collection(mid, source_id, source)
            return self._client.get_season_collection(mid, source_id, source)

        bvid = extract_bvid(source)
        if bvid and _first_int(query, "sid", "season_id") is not None:
            return self._client.get_video_season_collection(bvid, source)

        favorite_id = _first_int(query, "fid", "media_id", "mlid")
        if favorite_id is not None and "medialist" in path:
            return self._client.get_favorite_collection(favorite_id, source)
        raise BatchResolveError("无法从该合集链接识别列表编号")


def _split_inputs(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def classify_batch_inputs(text: str) -> tuple[list[str], list[str]]:
    """Return unique supported inputs and unrecognized lines."""
    valid = []
    invalid = []
    seen = set()
    for source in _split_inputs(text):
        collection_source = is_collection_source(source)
        if collection_source:
            identity = ("collection", source.lower())
            bvid = None
            aid = None
        else:
            bvid = extract_bvid(source)
            aid = extract_aid(source)
        if collection_source:
            pass
        elif bvid:
            identity = ("bvid", bvid.lower())
        elif aid:
            identity = ("aid", aid)
        elif is_short_link(source):
            identity = ("short", source.lower())
        else:
            invalid.append(source)
            continue

        if identity not in seen:
            seen.add(identity)
            valid.append(source)
    return valid, invalid


def is_collection_source(text: str) -> bool:
    source = text.strip()
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
