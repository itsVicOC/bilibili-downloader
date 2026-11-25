"""Read the signed-in account's batch import sources without resolving their works."""

from contextlib import closing
from dataclasses import dataclass
from threading import Event
from urllib.parse import parse_qs, urlsplit

import httpx

from bilibili_downloader.api.client import BilibiliAPIClient, BilibiliAPIError
from bilibili_downloader.utils.validators import extract_aid, extract_bvid

MAX_COLLECTION_FEED_PAGES = 5
MAX_VIDEO_LOOKUPS_PER_PAGE = 5
_FOLLOWING_PAGE_SIZE = 20
_SPACE_PAGE_SIZE = 12
_LOGIN_CODES = (-101, 401)
_LIMIT_CODES = (-352, -412, -509, 403, 412, 429)
_READ_ERRORS = (BilibiliAPIError, httpx.HTTPError, AttributeError, TypeError, ValueError)


@dataclass(frozen=True)
class BatchSource:
    url: str
    title: str
    author: str = ""
    cover: str = ""
    count: int | None = None
    updated_at: int = 0
    owner_mid: int = 0
    resource_id: int = 0
    first_video_cover: str = ""


@dataclass(frozen=True)
class BatchSourcePage:
    sources: tuple[BatchSource, ...] = ()
    next_offset: str = ""
    notice: str = ""
    error: str = ""
    login_required: bool = False
    page_key: tuple[str, ...] = ()
    paging_incomplete: bool = False


@dataclass(frozen=True)
class BatchCover:
    images: tuple[str, ...] = ()
    login_required: bool = False
    limited: bool = False


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value) -> int | None:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and len(value) <= 20 and value.isascii() and value.isdigit():
        return int(value)
    return None


def _code(error):
    if isinstance(error, BilibiliAPIError):
        return error.code
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def _favorite_sources(client, mid: int) -> BatchSourcePage:
    data = _object(client.get_created_favorite_folders(mid))
    folders = data.get("list")
    if folders is None and _number(data.get("count")) == 0:
        return BatchSourcePage()
    if not isinstance(folders, list):
        raise ValueError("Invalid favorite folder list")
    sources = {}
    for raw in folders:
        folder = _object(raw)
        # The contents API and space URL take the full media ID, called `id` here.
        media_id = _number(folder.get("id"))
        title = _text(folder.get("title"))
        owner = _number(folder.get("mid"))
        if media_id and title and owner in (None, mid):
            url = f"https://space.bilibili.com/{mid}/favlist?fid={media_id}"
            sources.setdefault(url, BatchSource(
                url, title, cover=_text(folder.get("cover")), count=_number(folder.get("media_count")),
                owner_mid=mid, resource_id=media_id,
            ))
    return BatchSourcePage(tuple(sources.values()))


def _season_source(mid, season, author, timestamp, *, first_video_cover="") -> BatchSource | None:
    season = _object(season)
    season_id = _number(season.get("id")) or _number(season.get("season_id"))
    title = _text(season.get("title")) or _text(season.get("name"))
    if season_id and title:
        url = f"https://space.bilibili.com/{mid}/lists/{season_id}?type=season"
        return BatchSource(
            url, title, author, _text(season.get("cover")), count=_number(season.get("total")),
            updated_at=timestamp, owner_mid=mid, resource_id=season_id, first_video_cover=first_video_cover,
        )
    return None


def _numbered_page(sources, page_key, page, page_size, total) -> BatchSourcePage:
    if total is None or not page_size:
        raise ValueError("Invalid source page count")
    has_more = page * page_size < total
    return BatchSourcePage(
        tuple(sources), str(page + 1) if has_more and page_key else "",
        "列表分页已中断。" if has_more and not page_key else "", page_key=tuple(sorted(page_key)),
        paging_incomplete=bool(has_more and not page_key),
    )


def _following_accounts(client, mid, page) -> BatchSourcePage:
    data = _object(client.get_following_accounts(mid, page, _FOLLOWING_PAGE_SIZE))
    rows = data.get("list")
    if rows is None and _number(data.get("total")) == 0:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("Invalid following list")
    authors = {}
    for row in rows:
        item = _object(row)
        owner = _number(item.get("mid"))
        name = _text(item.get("uname"))
        if owner and name:
            url = f"https://space.bilibili.com/{owner}"
            authors.setdefault(url, BatchSource(url, name, cover=_text(item.get("face")), owner_mid=owner))
    return _numbered_page(authors.values(), authors.keys(), page, _FOLLOWING_PAGE_SIZE, _number(data.get("total")))


def _space_collection_sources(client, creator: BatchSource, page: int) -> BatchSourcePage:
    data = _object(client.get_space_collections(creator.owner_mid, page, _SPACE_PAGE_SIZE))
    catalog = _object(data.get("items_lists"))
    paging = _object(catalog.get("page"))
    if not paging:
        raise ValueError("Invalid space collection page")
    if _number(paging.get("page_num")) != page:
        return BatchSourcePage(notice="合集分页已中断。", paging_incomplete=True)

    sources, page_key = [], []
    for list_name, id_name in (("seasons_list", "season_id"), ("series_list", "series_id")):
        rows = catalog.get(list_name)
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise ValueError("Invalid space collection list")
        for raw in rows:
            item = _object(raw)
            meta = _object(item.get("meta"))
            list_id = _number(meta.get(id_name))
            if list_id:
                page_key.append(f"{list_name}/{list_id}")
            if list_name == "seasons_list" and _number(meta.get("mid")) in (None, creator.owner_mid):
                archives = item.get("archives")
                first = _object(archives[0]) if isinstance(archives, list) and archives else {}
                source = _season_source(
                    creator.owner_mid, meta, creator.title, 0, first_video_cover=_text(first.get("pic")),
                )
                if source is not None:
                    sources.append(source)
    return _numbered_page(sources, page_key, page, _number(paging.get("page_size")), _number(paging.get("total")))


def _season_link_metadata(jump: str, mid: int, entry: dict) -> dict:
    prefix = f"https://space.bilibili.com/{mid}/lists/"
    if not jump.startswith(prefix):
        return {}
    parsed = urlsplit(jump)
    if parse_qs(parsed.query).get("type", ["season"])[0] != "season":
        return {}
    return {"id": parsed.path.removeprefix(f"/{mid}/lists/").rstrip("/"),
            "title": entry.get("title"), "cover": entry.get("cover")}


def _collection_feed(client, offset: str, cancelled: Event) -> BatchSourcePage:
    data = _object(client.get_following_feed(offset))
    items = data.get("items")
    has_more = data.get("has_more")
    if items is None and has_more is False and "items" in data:
        items = []
    if not isinstance(items, list) or type(has_more) is not bool:
        raise ValueError("Invalid following feed page")

    sources = {}

    def keep_newest(source):
        previous = sources.get(source.url)
        if previous is None or previous.updated_at < source.updated_at:
            sources[source.url] = source

    candidates = []
    for raw in items:
        item = _object(raw)
        kind = item.get("type")
        if kind not in ("DYNAMIC_TYPE_AV", "DYNAMIC_TYPE_UGC_SEASON"):
            continue
        modules = _object(item.get("modules"))
        author = _object(modules.get("module_author"))
        mid = _number(author.get("mid"))
        timestamp = _number(author.get("pub_ts"))
        if author.get("following") is not True or not mid or not timestamp:
            continue
        name = _text(author.get("name"))
        major = _object(_object(modules.get("module_dynamic")).get("major"))
        is_update = kind == "DYNAMIC_TYPE_UGC_SEASON"
        video = _object(major.get("ugc_season" if is_update else "archive"))
        jump = _text(video.get("jump_url"))
        if jump.startswith("//"):
            jump = f"https:{jump}"
        season = video.get("ugc_season")
        if season is None:
            season = {"season_id": video.get("season_id"), "title": video.get("season_title"),
                      "cover": video.get("season_cover")}
        source = _season_source(mid, season, name, timestamp)
        if source is None and is_update:
            source = _season_source(mid, _season_link_metadata(jump, mid, video), name, timestamp)
        if source is not None:
            keep_newest(source)
            continue
        bvid = extract_bvid(_text(video.get("bvid"))) or extract_bvid(jump)
        aid = _number(video.get("aid")) or extract_aid(jump)
        if bvid or aid:
            candidates.append((is_update, timestamp, mid, name, bvid, aid))

    # Explicit collection updates get the lookup budget before ordinary submissions.
    candidates.sort(key=lambda entry: entry[:2], reverse=True)
    seen_videos = set()
    notice = ""
    for _, timestamp, mid, name, bvid, aid in candidates:
        if cancelled.is_set() or len(seen_videos) >= MAX_VIDEO_LOOKUPS_PER_PAGE:
            break
        key = (mid, bvid or aid)
        if key in seen_videos:
            continue
        seen_videos.add(key)
        try:
            owner, season = client.get_video_season_metadata(bvid=bvid or "", aid=aid or 0)
        except _READ_ERRORS as error:
            code = _code(error)
            if code in _LOGIN_CODES:
                raise
            if code in (-403, -404, 404):
                continue
            notice = "部分视频的合集信息暂时无法读取。"
            if code in _LIMIT_CODES or isinstance(error, httpx.RequestError):
                break
            continue
        if _number(owner) == mid:
            source = _season_source(mid, season, name, timestamp)
            if source is not None:
                keep_newest(source)

    next_offset = _text(data.get("offset")) if has_more else ""
    if has_more and not next_offset:
        notice = f"{notice}动态分页已中断。"
    return BatchSourcePage(
        tuple(sorted(sources.values(), key=lambda source: source.updated_at, reverse=True)),
        next_offset, notice, paging_incomplete=bool(has_more and not next_offset),
    )


def load_batch_sources(cookies, mid: int, kind: str, offset: str, cancelled: Event, *, creator=None) -> BatchSourcePage:
    with closing(BilibiliAPIClient(auth_cookies=cookies, request_timeout=6.0)) as client:
        try:
            if kind == "favorites":
                return _favorite_sources(client, mid)
            if kind == "following":
                return _following_accounts(client, mid, int(offset) if offset else 1)
            if kind == "space":
                return _space_collection_sources(client, creator, int(offset) if offset else 1)
            return _collection_feed(client, offset, cancelled)
        except _READ_ERRORS as error:
            code = _code(error)
            if code in _LOGIN_CODES:
                return BatchSourcePage(error="B 站登录已失效，请重新登录。", login_required=True)
            if code in _LIMIT_CODES:
                return BatchSourcePage(error="B 站暂时限制了列表请求，请稍后重试。")
            return BatchSourcePage(error="暂时无法读取来源，请重试。")


def load_batch_cover(cookies, source: BatchSource, *, favorite: bool) -> BatchCover:
    with closing(BilibiliAPIClient(auth_cookies=cookies, request_timeout=6.0)) as client:
        try:
            if favorite:
                data = _object(client.get_favorite_page(source.resource_id))
                cover = _text(_object(data.get("info")).get("cover"))
                video_cover = ""
                for raw in data.get("medias") or []:
                    video = _object(raw)
                    if _number(video.get("type")) in (None, 2) and extract_bvid(_text(video.get("bvid"))):
                        video_cover = _text(video.get("cover"))
                        if video_cover:
                            break
            else:
                data = _object(client.get_season_page(source.owner_mid, source.resource_id, page_size=1))
                cover = _text(_object(data.get("meta")).get("cover"))
                first = (data.get("archives") or [{}])[0]
                video_cover = _text(_object(first).get("pic"))
            return BatchCover(tuple(dict.fromkeys(url for url in (cover, video_cover) if url and url != source.cover)))
        except _READ_ERRORS as error:
            code = _code(error)
            return BatchCover(login_required=code in _LOGIN_CODES, limited=code in _LIMIT_CODES)
