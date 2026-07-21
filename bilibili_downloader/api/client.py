"""Bilibili API client for video metadata and playback URLs."""

import logging
import threading
import time
from typing import Optional

import httpx

from bilibili_downloader.api import endpoints as ep
from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.api.wbi import WBISigner
from bilibili_downloader.core.models import (
    StreamInfo,
    SubtitleInfo,
    VideoInfo,
    VideoPage,
    VideoQuality,
)
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

logger = logging.getLogger(__name__)

FNVAL_DASH = 16
FNVAL_HDR = 64
FNVAL_4K = 128
FNVAL_DOLBY_AUDIO = 256
FNVAL_DOLBY_VIDEO = 512
FNVAL_8K = 1024
FNVAL_AV1 = 2048


class BilibiliAPIClient:
    """HTTP client for Bilibili APIs with WBI signing and cookie management."""

    WBI_CACHE_TTL = 24 * 3600  # 24 hours

    def __init__(self, sessdata: Optional[str] = None):
        self._client = httpx.Client(
            base_url=ep.BASE_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.bilibili.com/",
            },
            cookies={"SESSDATA": sessdata} if sessdata else {},
            timeout=30.0,
            http2=True,
        )
        self._wbi_signer = WBISigner()
        self._wbi_mixin_key: Optional[str] = None
        self._wbi_cached_at: Optional[float] = None
        self._wbi_lock = threading.Lock()
        self._sessdata = sessdata

    @property
    def sessdata(self) -> Optional[str]:
        return self._sessdata

    @sessdata.setter
    def sessdata(self, value: str):
        self._sessdata = value
        self._client.cookies.set("SESSDATA", value)

    # -- WBI Management --

    def _ensure_wbi_keys(self) -> None:
        """Fetch and cache WBI mixin key if expired."""
        now = time.time()
        if self._wbi_mixin_key and self._wbi_cached_at:
            if now - self._wbi_cached_at < self.WBI_CACHE_TTL:
                return

        with self._wbi_lock:
            # Double-checked locking: another thread may have refreshed while we waited
            now = time.time()
            if self._wbi_mixin_key and self._wbi_cached_at:
                if now - self._wbi_cached_at < self.WBI_CACHE_TTL:
                    return

            resp = self._client.get(ep.NAV_ENDPOINT)
            resp.raise_for_status()
            data = resp.json()

            # Nav may return -101 (not logged in) but still provide WBI keys
            wbi_img = data.get("data", {}).get("wbi_img", {})
            if not wbi_img.get("img_url"):
                raise RuntimeError(f"Failed to fetch WBI keys: {data.get('message')}")
            img_key = self._wbi_signer.extract_key_from_url(wbi_img["img_url"])
            sub_key = self._wbi_signer.extract_key_from_url(wbi_img["sub_url"])
            self._wbi_mixin_key = self._wbi_signer.compute_mixin_key(img_key, sub_key)
            self._wbi_cached_at = now

    def _retry_on_wbi_error(self, action):
        """Execute an API call, refreshing WBI keys on -352 errors.

        Args:
            action: Callable that takes no args and returns parsed data.
                  Must rebuild signed params internally on each call.

        Returns:
            Parsed response data.
        """
        try:
            return action()
        except BilibiliAPIError as e:
            if e.code != -352:
                raise
            # WBI signature expired/invalid — refresh keys and retry once
            logger.warning("WBI signature error (-352), refreshing keys")
            with self._wbi_lock:
                self._wbi_mixin_key = None
                self._wbi_cached_at = None
            return action()

    def _sign_params(self, params: dict) -> dict:
        """Apply WBI signature to query parameters."""
        if self._wbi_mixin_key is None:
            self._ensure_wbi_keys()
        return self._wbi_signer.sign(params, self._wbi_mixin_key)

    def _parse_response(self, resp: httpx.Response) -> dict:
        """Parse API response, raise on error."""
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code", -1)
        if code != 0:
            raise BilibiliAPIError(code, data.get("message", "Unknown error"))
        return data.get("data", {})

    # -- API Methods --

    def get_video_info(self, bvid: str) -> VideoInfo:
        """Fetch video metadata by BV number from /x/web-interface/view."""

        def _fetch():
            params = self._sign_params({"bvid": bvid})
            resp = self._client.get(ep.VIEW_ENDPOINT, params=params)
            return self._parse_response(resp)

        data = self._retry_on_wbi_error(_fetch)
        return _parse_video_info(bvid, data)

    def get_video_info_by_aid(self, aid: int) -> VideoInfo:
        """Fetch video metadata by AV/AID number from /x/web-interface/view."""

        def _fetch():
            params = self._sign_params({"aid": aid})
            resp = self._client.get(ep.VIEW_ENDPOINT, params=params)
            return self._parse_response(resp)

        data = self._retry_on_wbi_error(_fetch)
        return _parse_video_info(data.get("bvid", ""), data)

    def get_play_url(
        self,
        bvid: str,
        cid: int,
        quality: VideoQuality = VideoQuality.Q1080P,
        need_hdr: bool = False,
        need_dolby: bool = False,
        preferred_codec: Optional[int] = None,
        discover_all: bool = False,
    ) -> dict:
        """Fetch playback URLs for video and audio streams.

        Returns dict with 'video_streams', 'audio_streams', 'dash' raw data.
        """
        fnval = _build_fnval(
            quality,
            preferred_codec=preferred_codec,
            need_hdr=need_hdr,
            need_dolby=need_dolby,
            discover_all=discover_all,
        )

        def _fetch():
            params = {
                "bvid": bvid,
                "cid": cid,
                "qn": quality.value,
                "fnval": fnval,
                "fourk": 1,
            }
            signed = self._sign_params(params)
            resp = self._client.get(ep.PLAYURL_ENDPOINT, params=signed)
            data = self._parse_response(resp)
            return _parse_playurl(data)

        return self._retry_on_wbi_error(_fetch)

    def get_subtitle_tracks(self, bvid: str, cid: int) -> list[SubtitleInfo]:
        """Fetch subtitle tracks for a specific page."""

        def _fetch():
            params = self._sign_params({"bvid": bvid, "cid": cid})
            resp = self._client.get(ep.PLAYER_INFO_ENDPOINT, params=params)
            return self._parse_response(resp)

        data = self._retry_on_wbi_error(_fetch)
        subtitles = (data.get("subtitle") or {}).get("subtitles") or []
        return [
            SubtitleInfo(
                lan=entry.get("lan", ""),
                lan_doc=entry.get("lan_doc", ""),
                url=entry.get("subtitle_url", ""),
            )
            for entry in subtitles
            if isinstance(entry, dict) and entry.get("subtitle_url")
        ]

    def get_danmaku_xml(self, cid: int) -> bytes:
        """Download danmaku in XML format."""
        url = ep.DANMAKU_XML_URL.format(cid=cid)
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.content

    def get_subtitle_json(self, subtitle_url: str) -> dict:
        """Download subtitle JSON from direct URL."""
        subtitle_url = trusted_https_url(subtitle_url, BILIBILI_RESOURCE_HOSTS)
        resp = self._client.get(
            subtitle_url,
        )
        resp.raise_for_status()
        return resp.json()

    def get_nav_info(self) -> dict:
        """Get user navigation info from /x/web-interface/nav.

        Returns dict with 'isLogin', 'uname', 'mid', 'face', etc.
        Returns empty dict if not logged in.
        """
        resp = self._client.get(ep.NAV_ENDPOINT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0 and data.get("data"):
            return data["data"]
        return {}

    def get_page_list(self, bvid: str) -> list[VideoPage]:
        """Get page list for multi-part videos."""
        params = {"bvid": bvid}
        params = self._sign_params(params)
        resp = self._client.get(ep.PAGELIST_ENDPOINT, params=params)
        data = self._parse_response(resp)
        return [
            VideoPage(
                cid=p["cid"],
                page=p["page"],
                part=p.get("part", f"P{p['page']}"),
                duration=p.get("duration", 0),
            )
            for p in data
        ]

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()


def _parse_video_info(bvid: str, data: dict) -> VideoInfo:
    """Parse /x/web-interface/view response into VideoInfo."""
    pages = []
    for p in data.get("pages", []):
        pages.append(VideoPage(
            cid=p["cid"],
            page=p["page"],
            part=p.get("part", f"P{p['page']}"),
            duration=p.get("duration", 0),
        ))

    subtitle_list = []
    for s in data.get("subtitle", {}).get("subtitles", []):
        subtitle_list.append(SubtitleInfo(
            lan=s.get("lan", ""),
            lan_doc=s.get("lan_doc", ""),
            url=s.get("subtitle_url", ""),
        ))

    owner = data.get("owner", {})
    return VideoInfo(
        bvid=data.get("bvid") or bvid,
        cid=data.get("cid", 0),
        aid=data.get("aid", 0),
        title=data.get("title", ""),
        desc=data.get("desc", ""),
        duration=data.get("duration", 0),
        author=owner.get("name", ""),
        owner_name=owner.get("name", ""),
        cover_url=data.get("pic", ""),
        pages=pages or [VideoPage(cid=data.get("cid", 0), page=1, part="")],
        subtitle_list=subtitle_list,
        pubdate=data.get("pubdate", 0),
    )


def _parse_playurl(data: dict) -> dict:
    """Parse /x/player/playurl response into stream info."""
    dash = data.get("dash") or {}
    video_streams = []
    audio_streams = []

    for stream in dash.get("video") or []:
        if isinstance(stream, dict):
            video_streams.append(_parse_stream_info(stream, "video/mp4", 7))

    audio_entries = list(dash.get("audio") or [])
    dolby_audio = (dash.get("dolby") or {}).get("audio") or []
    audio_entries.extend(dolby_audio if isinstance(dolby_audio, list) else [dolby_audio])
    flac_audio = (dash.get("flac") or {}).get("audio") or []
    audio_entries.extend(flac_audio if isinstance(flac_audio, list) else [flac_audio])

    seen_audio = set()
    for stream in audio_entries:
        if not isinstance(stream, dict):
            continue
        parsed = _parse_stream_info(stream, "audio/mp4", 0)
        identity = (parsed.id, parsed.base_url)
        if identity not in seen_audio:
            seen_audio.add(identity)
            audio_streams.append(parsed)

    return {
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "has_dolby": bool((dash.get("dolby") or {}).get("audio", [])),
        "has_hdr": any(stream.id == VideoQuality.QHDR.value for stream in video_streams),
        "raw_dash": dash,
    }


def _parse_stream_info(data: dict, default_mime: str, default_codec: int) -> StreamInfo:
    """Parse both snake_case and camelCase DASH response variants."""
    return StreamInfo(
        id=data.get("id", 0),
        base_url=data.get("base_url") or data.get("baseUrl") or "",
        backup_url=data.get("backup_url") or data.get("backupUrl") or [],
        codecid=data.get("codecid", default_codec),
        bandwidth=data.get("bandwidth", 0),
        mime_type=data.get("mime_type") or data.get("mimeType") or default_mime,
    )


def _build_fnval(
    quality: VideoQuality,
    preferred_codec: Optional[int] = None,
    need_hdr: bool = False,
    need_dolby: bool = False,
    discover_all: bool = False,
) -> int:
    """Build the documented Bilibili DASH capability bitmask."""
    fnval = FNVAL_DASH
    if discover_all:
        return fnval | FNVAL_HDR | FNVAL_4K | FNVAL_DOLBY_AUDIO | FNVAL_DOLBY_VIDEO | FNVAL_8K | FNVAL_AV1

    if quality == VideoQuality.Q4K:
        fnval |= FNVAL_4K
    elif quality == VideoQuality.QHDR or need_hdr:
        fnval |= FNVAL_HDR
    elif quality == VideoQuality.Q_DOLBY or need_dolby:
        fnval |= FNVAL_DOLBY_AUDIO | FNVAL_DOLBY_VIDEO
    elif quality == VideoQuality.Q8K:
        fnval |= FNVAL_8K

    if preferred_codec == 13:
        fnval |= FNVAL_AV1
    return fnval


class BilibiliAPIError(Exception):
    """Bilibili API error with error code."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Bilibili API error [{code}]: {message}")
