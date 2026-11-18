import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "bilibili_downloader").is_dir())
sys.path.insert(0, str(ROOT))

import httpx

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.downloader import (
    SSL_CONTEXT,
    STREAM_HEADERS,
    StreamDownloader,
)
from bilibili_downloader.core.models import VideoQuality
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def emit(**value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def error_summary(error):
    result = {"error_type": type(error).__name__}
    if isinstance(error, httpx.HTTPStatusError):
        result.update(status=error.response.status_code, host=error.request.url.host)
    elif hasattr(error, "code"):
        result["api_code"] = error.code
    return result


def sample_response(response):
    value = {
        "status": response.status_code,
        "host": response.request.url.host,
        "content_type": response.headers.get("content-type"),
        "server": response.headers.get("server"),
        "content_range": response.headers.get("content-range"),
    }
    response.raise_for_status()
    value["sampled_bytes"] = len(next(response.iter_bytes(1024), b""))
    return value


class ProbeDownloader(StreamDownloader):
    def _write_response(self, response, dest, resume_from, progress_callback):
        self.result = sample_response(response)


class BoundedClient(httpx.Client):
    def stream(self, *args, **kwargs):
        kwargs["timeout"] = 15
        return super().stream(*args, **kwargs)


def media_client():
    return BoundedClient(transport=httpx.HTTPTransport(http2=False, retries=0, verify=SSL_CONTEXT))


parser = argparse.ArgumentParser()
parser.add_argument("bvid", nargs="?", default="BV1GJ411x7h7")
parser.add_argument("--search", action="store_true")
parser.add_argument("--cid", type=int)
args = parser.parse_args()

with httpx.Client(timeout=15) as client:
    response = client.get("https://www.cloudflare.com/cdn-cgi/trace")
    fields = dict(line.split("=", 1) for line in response.text.splitlines() if "=" in line)
    emit(stage="environment", country=fields.get("loc"), authenticated=False)

api = BilibiliAPIClient(request_timeout=15)


def observe_response(response):
    emit(stage="api_http", host=response.request.url.host,
         endpoint=response.request.url.path, status=response.status_code)


api._client.event_hooks["response"].append(observe_response)
try:
    zone = api._client.get("/x/web-interface/zone")
    if zone.status_code == 200:
        zone_payload = zone.json()
        emit(stage="bilibili_region", country=(zone_payload.get("data") or {}).get("country"))
    if args.search:
        response = api._client.get("/x/web-interface/search/type", params={
            "search_type": "video", "keyword": "灭霸半夜梦游", "page": 1,
        })
        response.raise_for_status()
        payload = response.json()
        emit(stage="search", code=payload.get("code"), results=[
            {"bvid": entry.get("bvid"), "title": entry.get("title")}
            for entry in (payload.get("data") or {}).get("result", [])[:5]
        ])
    if args.cid is None:
        info = api.get_video_info(args.bvid)
        bvid, cid = info.bvid, info.cid
        emit(stage="metadata", bvid=bvid, cid=cid, title=info.title)
    else:
        bvid, cid = args.bvid, args.cid
        emit(stage="known_public_metadata", bvid=bvid, cid=cid)
    streams = api.get_play_url(bvid, cid, VideoQuality(32), preferred_codec=7)
    emit(stage="playurl", videos=len(streams["video_streams"]), audios=len(streams["audio_streams"]))
    with tempfile.TemporaryDirectory(prefix="issue33-probe-") as directory:
        downloader = ProbeDownloader(api, directory, max_retries=1)
        for kind, choices in (("video", streams["video_streams"]), ("audio", streams["audio_streams"])):
            if not choices:
                continue
            stream = next((value for value in choices if value.id == 32 and value.codecid == 7), choices[0])
            candidates = list(dict.fromkeys([stream.base_url, *stream.backup_url]))[:3]
            for index, url in enumerate(candidates):
                try:
                    trusted_https_url(url, BILIBILI_RESOURCE_HOSTS)
                except ValueError:
                    emit(stage="media", track=kind, candidate=index, rejected_by_allowlist=True,
                         host=httpx.URL(url).host)
                    continue
                with media_client() as client:
                    try:
                        downloader._download_url(client, url, Path(directory) / "probe.m4s", lambda value: None)
                        result = downloader.result
                    except Exception as error:
                        result = error_summary(error)
                    emit(stage="media", case="production_initial", track=kind, candidate=index, **result)
                    if result.get("status") != 403:
                        continue
                    range_succeeded = False
                    for range_value in ("bytes=0-1023", "bytes=0-"):
                        try:
                            with media_client() as controlled_client:
                                with controlled_client.stream("GET", url, headers={**STREAM_HEADERS, "Range": range_value},
                                                              follow_redirects=False) as response:
                                    controlled = sample_response(response)
                        except Exception as error:
                            controlled = error_summary(error)
                        range_succeeded |= controlled.get("status") in (200, 206)
                        emit(stage="media", case="range_comparison", range=range_value,
                             track=kind, candidate=index, **controlled)
                    if range_succeeded:
                        with media_client() as repeat_client:
                            try:
                                downloader._download_url(repeat_client, url, Path(directory) / "probe.m4s", lambda value: None)
                                repeated = downloader.result
                            except Exception as error:
                                repeated = error_summary(error)
                        emit(stage="media", case="production_recheck", track=kind, candidate=index, **repeated)
except Exception as error:
    emit(stage="failed", **error_summary(error))
finally:
    api.close()
