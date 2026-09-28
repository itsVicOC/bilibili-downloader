"""Small, replaceable Bilibili live API adapter. No media requests carry cookies."""

import re
from urllib.parse import urlparse

import httpx

from bilibili_downloader.api.auth import filter_auth_cookies
from bilibili_downloader.api.client import USER_AGENT, BilibiliAPIError
from bilibili_downloader.core.live_models import LiveQuality, LiveRoom, LiveStream
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url
from bilibili_downloader.utils.validators import is_short_link, resolve_short_url

BASE = "https://api.live.bilibili.com"


class LiveAccessError(ValueError):
    pass


class BilibiliLiveClient:
    def __init__(self, auth_cookies=None, transport=None):
        self._client = httpx.Client(
            base_url=BASE,
            headers={"User-Agent": USER_AGENT, "Referer": "https://live.bilibili.com/"},
            cookies=filter_auth_cookies(auth_cookies),
            timeout=15,
            follow_redirects=False,
            transport=transport,
        )

    def close(self):
        self._client.close()

    def _get(self, endpoint, **params):
        response = self._client.get(endpoint, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise BilibiliAPIError(
                payload.get("code", -1), payload.get("message", "直播接口错误")
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise LiveAccessError("直播接口未返回有效房间信息")
        return data

    @staticmethod
    def parse_room_id(source: str) -> int:
        source = source.strip()
        if is_short_link(source):
            source = resolve_short_url(source) or ""
        if re.fullmatch(r"[0-9]{1,18}", source):
            room_id = int(source)
        else:
            parsed = urlparse(source)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname != "live.bilibili.com"
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 80, 443}
            ):
                raise ValueError("请输入直播间房间号、live.bilibili.com 链接或直播短链")
            match = re.fullmatch(r"/(?:blanc/)?([0-9]{1,18})/?", parsed.path)
            if not match:
                raise ValueError("直播间链接中缺少房间号")
            room_id = int(match[1])
        if room_id <= 0:
            raise ValueError("房间号必须大于 0")
        return room_id

    @staticmethod
    def _check_access(data):
        if data.get("is_locked") or data.get("is_hidden"):
            raise LiveAccessError("直播间不可访问或已被锁定")
        if data.get("encrypted") or data.get("is_sp") or data.get("special_type") == 1:
            raise LiveAccessError("首版不支持加密或付费特殊直播间")
        if data.get("all_special_types"):
            raise LiveAccessError("首版不支持特殊权限直播间")

    def get_status(self, room_id: int) -> LiveRoom:
        data = self._get("/room/v1/Room/room_init", id=room_id)
        self._check_access(data)
        return LiveRoom(
            room_id=data["room_id"],
            short_id=data.get("short_id", 0),
            uid=data.get("uid", 0),
            live_status=data.get("live_status", 0),
            live_time=str(data.get("live_time") or ""),
        )

    def resolve_room(self, source: str) -> LiveRoom:
        room = self.get_status(self.parse_room_id(source))
        return self.refresh_metadata(room)

    def refresh_metadata(self, room: LiveRoom) -> LiveRoom:
        data = self._get("/xlive/web-room/v1/index/getInfoByRoom", room_id=room.room_id)
        info = data.get("room_info") or {}
        self._check_access(info)
        room.title = str(info.get("title") or f"直播间 {room.room_id}")
        room.author = str(
            ((data.get("anchor_info") or {}).get("base_info") or {}).get("uname")
            or room.uid
        )
        return room

    def get_streams(self, room_id: int, quality: int = 0) -> list[LiveStream]:
        data = self._get(
            "/xlive/web-room/v2/index/getRoomPlayInfo",
            room_id=room_id,
            protocol="0,1",
            format="0,1,2",
            codec="0",
            qn=quality or 30000,
            platform="web",
            ptype=8,
        )
        self._check_access(data)
        if data.get("live_status") != 1:
            return []
        play = (data.get("playurl_info") or {}).get("playurl") or {}
        qualities = [
            LiveQuality(qn=q["qn"], label=q["desc"]) for q in play.get("g_qn_desc", [])
        ]
        labels = {q.qn: q.label for q in qualities}
        streams = []
        for protocol in play.get("stream", []):
            for fmt in protocol.get("format", []):
                format_name = fmt.get("format_name")
                if (protocol.get("protocol_name"), format_name) not in {
                    ("http_stream", "flv"),
                    ("http_hls", "ts"),
                    ("http_hls", "fmp4"),
                }:
                    continue
                for codec in fmt.get("codec", []):
                    if codec.get("codec_name") != "avc":
                        continue
                    qn = int(codec.get("current_qn", 0))
                    for address in codec.get("url_info", []):
                        url = f"{address.get('host', '')}{codec.get('base_url', '')}{address.get('extra', '')}"
                        url = trusted_https_url(
                            url, BILIBILI_RESOURCE_HOSTS, upgrade_http=True
                        )
                        streams.append(
                            LiveStream(
                                url=url,
                                format=format_name,
                                quality=qn,
                                quality_label=labels.get(qn, str(qn)),
                                qualities=qualities,
                                warning=f"请求画质 {quality}，实际为 {labels.get(qn, qn)}"
                                if quality and qn != quality
                                else "",
                            )
                        )
        return sorted(
            streams,
            key=lambda s: (-s.quality, {"flv": 0, "ts": 1, "fmp4": 2}[s.format]),
        )
