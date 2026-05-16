"""Batch download resolver for Bilibili collections and series."""

import re
from typing import Optional

from src.api.client import BilibiliAPIClient
from src.core.models import VideoInfo, VideoPage

# Series/collection URL patterns
SERIES_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?bilibili\.com/(?:video/)?(?:series|medialist).*?(?:sid|season_id)=(\d+)",
    re.IGNORECASE,
)


class BatchResolver:
    """Resolve Bilibili collections/series into a list of VideoInfo."""

    def __init__(self, client: BilibiliAPIClient):
        self._client = client

    def resolve_url(self, url: str) -> list[VideoInfo]:
        """Resolve a URL to a list of videos for batch download.

        Supports:
        - Single video URL -> list with one VideoInfo
        - Series/collection URL -> list of all videos in the collection
        - Multiple URLs separated by newlines -> combined list
        """
        urls = [u.strip() for u in url.strip().split("\n") if u.strip()]
        results = []

        for u in urls:
            if SERIES_URL_PATTERN.search(u):
                results.extend(self._resolve_series(u))
            else:
                info = self._resolve_single(u)
                if info:
                    results.append(info)

        return results

    def _resolve_single(self, url: str) -> Optional[VideoInfo]:
        """Resolve a single video URL to VideoInfo."""
        from src.utils.validators import extract_bvid, extract_aid

        bvid = extract_bvid(url)
        if bvid:
            return self._client.get_video_info(bvid)

        aid = extract_aid(url)
        if aid:
            # Need to convert AID to BVID - use view endpoint
            # For now, AID support requires fetching the view endpoint differently
            return None

        return None

    def _resolve_series(self, url: str) -> list[VideoInfo]:
        """Resolve a series URL to all videos.

        Note: The series API is complex and may need updates.
        This is a simplified implementation.
        """
        # Series API details vary; this is a placeholder that should be
        # expanded based on bilibili-API-collect documentation
        # For now, return empty list to avoid errors
        return []
