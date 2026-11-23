"""Retrieve the daily public snapshot and the signed-in account's video feed."""

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event

import httpx

from bilibili_downloader.api.client import BilibiliAPIClient, BilibiliAPIError
from bilibili_downloader.core.update_protocol import atomic_json
from bilibili_downloader.utils.validators import extract_bvid

logger = logging.getLogger(__name__)

BEIJING = timezone(timedelta(hours=8))
RANKING_SIZE = 100
PUBLIC_CACHE_VERSION = 2
MAX_FEED_PAGES = 5
PLAY_COUNT = re.compile(r"([0-9]+(?:\.[0-9]+)?)([万亿]?)")
PLAY_UNITS = {"": 1, "万": 10_000, "亿": 100_000_000}


@dataclass(frozen=True)
class RankedVideo:
    bvid: str
    title: str
    author: str
    play_text: str
    published_at: int = 0
    cover_url: str = ""
    duration_text: str = ""

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}"


@dataclass(frozen=True)
class RankingSnapshot:
    fetched_at: datetime
    videos: tuple[RankedVideo, ...]

    @property
    def day(self):
        return self.fetched_at.astimezone(BEIJING).date()


@dataclass(frozen=True)
class RankingResult:
    snapshot: RankingSnapshot | None = None
    message: str = ""
    login_required: bool = False
    stale: bool = False


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _play_text(value) -> str:
    if type(value) is int and value >= 0:
        return str(value)
    return _text(value)


def _play_count(text: str) -> Decimal | None:
    match = PLAY_COUNT.fullmatch(text)
    if match is None:
        return None
    number, unit = match.groups()
    return Decimal(number) * PLAY_UNITS[unit]


def _duration_text(value) -> str:
    if type(value) is int and value > 0:
        minutes, seconds = divmod(value, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
    return _text(value)


def rank_following_videos(videos: tuple[RankedVideo, ...], *, by_plays=False) -> tuple[RankedVideo, ...]:
    def rank(video):
        recent, plays = -video.published_at, -_play_count(video.play_text)
        return (plays, recent, video.bvid) if by_plays else (recent, plays, video.bvid)

    return tuple(sorted(videos, key=rank)[:RANKING_SIZE])


def _error_result(error: Exception, *, following=False) -> RankingResult:
    if isinstance(error, BilibiliAPIError):
        code = error.code
    elif isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
    else:
        code = None
    if following and code in (-101, 401):
        return RankingResult(message="B 站登录已失效，请重新登录后查看关注榜。", login_required=True)
    if code in (403, 412, 429, -352, -412, -509):
        return RankingResult(message="B 站暂时限制了榜单请求，请稍后重试。")
    return RankingResult(message="暂时无法读取榜单，请重试或打开 B 站查看。")


def _read_public_snapshot(path: Path) -> tuple[RankingSnapshot | None, bool]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        current_format = payload.get("version") == PUBLIC_CACHE_VERSION
        if fetched_at.tzinfo is None or not 1 <= len(payload["videos"]) <= RANKING_SIZE:
            return None, False
        videos = tuple(RankedVideo(**item) for item in payload["videos"])
        if any(
            extract_bvid(video.bvid) != video.bvid
            or not video.title.strip()
            or not isinstance(video.author, str)
            or not isinstance(video.play_text, str)
            or not isinstance(video.cover_url, str)
            or not isinstance(video.duration_text, str)
            or video.published_at != 0
            for video in videos
        ):
            return None, False
        return RankingSnapshot(fetched_at, videos), current_format
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, False


def load_public_ranking(path: Path) -> RankingResult:
    cached, current_format = _read_public_snapshot(path)
    today = beijing_now().date()
    if current_format and cached is not None and cached.day == today:
        return RankingResult(cached)
    try:
        entries = BilibiliAPIClient.get_video_ranking()["list"]
        if not isinstance(entries, list):
            raise ValueError("invalid ranking")
        videos = []
        seen = set()
        for raw in entries:
            entry = _object(raw)
            bvid = extract_bvid(_text(entry.get("bvid")))
            title = _text(entry.get("title"))
            if not bvid or not title or bvid in seen:
                continue
            seen.add(bvid)
            videos.append(RankedVideo(
                bvid, title, _text(_object(entry.get("owner")).get("name")),
                _play_text(_object(entry.get("stat")).get("view")),
                cover_url=_text(entry.get("pic")), duration_text=_duration_text(entry.get("duration")),
            ))
            if len(videos) == RANKING_SIZE:
                break
        if not videos:
            raise ValueError("empty ranking")
    except (httpx.HTTPError, BilibiliAPIError, AttributeError, KeyError, TypeError, ValueError) as error:
        stale = cached if cached is not None and cached.day <= today else None
        return RankingResult(stale, _error_result(error).message, stale=stale is not None)

    snapshot = RankingSnapshot(beijing_now(), tuple(videos))
    try:
        atomic_json(path, {
            "version": PUBLIC_CACHE_VERSION,
            "fetched_at": snapshot.fetched_at.isoformat(),
            "videos": [asdict(video) for video in snapshot.videos],
        })
    except OSError:
        logger.warning("Could not save the public ranking snapshot")
    return RankingResult(snapshot)


def load_following_ranking(client: BilibiliAPIClient, cancelled: Event) -> RankingResult:
    start = beijing_now()
    newest_ts = int(start.timestamp())
    videos: dict[str, RankedVideo] = {}
    offset = ""
    seen_offsets = set()
    message = ""
    missing_counts = False
    missing_timestamps = False
    for page in range(1, MAX_FEED_PAGES + 1):
        if cancelled.is_set():
            return RankingResult()
        try:
            data = client.get_following_video_feed(offset)
            items = data.get("items")
            if not isinstance(items, list) or type(data.get("has_more")) is not bool:
                raise ValueError("invalid video feed")
        except (httpx.HTTPError, BilibiliAPIError, AttributeError, TypeError, ValueError) as error:
            result = _error_result(error, following=True)
            if page == 1 or result.login_required:
                return result
            message = f"读取在第 {page} 页中断，展示已读取的前 {page - 1} 页。{result.message}"
            break
        if cancelled.is_set():
            return RankingResult()

        for raw in items:
            item = _object(raw)
            if item.get("type") != "DYNAMIC_TYPE_AV":
                continue
            modules = _object(item.get("modules"))
            author = _object(modules.get("module_author"))
            if author.get("following") is not True:
                continue
            pub_ts = author.get("pub_ts")
            if isinstance(pub_ts, str) and re.fullmatch(r"[0-9]{1,12}", pub_ts):
                pub_ts = int(pub_ts)
            if type(pub_ts) is not int or not 0 < pub_ts <= newest_ts:
                missing_timestamps = True
                continue
            dynamic = _object(modules.get("module_dynamic"))
            archive = _object(_object(dynamic.get("major")).get("archive"))
            bvid = extract_bvid(_text(archive.get("bvid")))
            title = _text(archive.get("title"))
            if not bvid or not title or bvid in videos:
                continue
            play_text = _play_text(_object(archive.get("stat")).get("play"))
            if _play_count(play_text) is None:
                missing_counts = True
                continue
            videos[bvid] = RankedVideo(
                bvid, title, _text(author.get("name")), play_text, pub_ts,
                _text(archive.get("cover")), _duration_text(archive.get("duration_text")),
            )

        if not data["has_more"]:
            break
        offset = _text(data.get("offset"))
        if not offset or offset in seen_offsets:
            message = f"分页在第 {page} 页结束，展示已读取的结果。"
            break
        seen_offsets.add(offset)
    else:
        message = f"展示关注动态前 {MAX_FEED_PAGES} 页内的结果。"

    if missing_counts:
        message = f"{message}部分投稿缺少可用的播放量。"
    if missing_timestamps:
        message = f"{message}部分投稿缺少可用的发布时间。"
    fetched_at = beijing_now()
    if fetched_at.date() != start.date():
        return RankingResult(message="北京时间已跨天，请刷新关注榜。")
    return RankingResult(RankingSnapshot(fetched_at, tuple(videos.values())), message)
