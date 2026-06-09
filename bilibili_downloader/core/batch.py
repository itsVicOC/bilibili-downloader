"""Resolvers for single and batch Bilibili download inputs."""

import re

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.models import VideoInfo
from bilibili_downloader.utils.validators import (
    extract_aid,
    extract_bvid,
    is_short_link,
    resolve_short_link,
)

# Series/collection URL patterns. They are detected so the UI can explain that
# this input is not currently supported instead of silently ignoring it.
SERIES_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?bilibili\.com/(?:video/)?(?:series|medialist).*?"
    r"(?:sid|season_id|mlid|media_id)=\d+",
    re.IGNORECASE,
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
            results.append(self.resolve_one(line))
        return results

    def resolve_one(self, text: str) -> VideoInfo:
        """Resolve one BV/AV/full URL/b23 short link to ``VideoInfo``."""
        source = text.strip()
        if not source:
            raise BatchResolveError("输入为空")

        if SERIES_URL_PATTERN.search(source):
            raise BatchResolveError("暂不支持合集或系列链接，请粘贴其中的视频链接")

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


def _split_inputs(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]
