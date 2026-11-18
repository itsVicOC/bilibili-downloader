"""Opt-in anonymous CDN download, interruption, resume and full-decode smoke.

Only sanitized JSON is retained. Signed URLs and temporary media stay in memory
or an automatically removed temporary directory; no account/config is loaded.
"""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core import downloader as downloader_module
from bilibili_downloader.core.downloader import (
    SSL_CONTEXT,
    STREAM_HEADERS,
    StreamDownloader,
)
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import (
    DownloadItem,
    OutputMode,
    VideoInfo,
    VideoQuality,
)
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bvid", default="BV1GJ411x7h7")
    parser.add_argument("--cid", type=int, default=137649199)
    parser.add_argument("--require-country")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    report = {"bvid": args.bvid, "cid": args.cid, "authenticated": False,
              "range_chunk_size": downloader_module.RANGE_CHUNK_SIZE,
              "downloader_sha256": sha256(Path(downloader_module.__file__)), "requests": []}
    real_client = httpx.Client
    state = {"phase": "full", "track": ""}

    def observe_request(request):
        assert re.fullmatch(r"bytes=\d+-\d+", request.headers["range"])
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers

    def observe_response(response):
        report["requests"].append({
            **state, "host": response.request.url.host,
            "range": response.request.headers["range"], "status": response.status_code,
            "content_range": response.headers.get("content-range"),
        })

    def recording_client(**kwargs):
        client = real_client(**kwargs)
        client.event_hooks["request"].append(observe_request)
        client.event_hooks["response"].append(observe_response)
        return client

    class RecordingDownloader(StreamDownloader):
        def _download_stream(self, stream, dest, callback, referer="https://www.bilibili.com/"):
            state["track"] = dest.stem
            super()._download_stream(stream, dest, callback, referer=referer)
            if state["phase"] == "full":
                report[dest.stem] = {"bytes": dest.stat().st_size, "sha256": sha256(dest)}

    api = BilibiliAPIClient(request_timeout=20)
    try:
        with real_client(timeout=20) as client:
            trace = client.get("https://www.cloudflare.com/cdn-cgi/trace")
            trace.raise_for_status()
            fields = dict(line.split("=", 1) for line in trace.text.splitlines() if "=" in line)
            report["country"] = fields.get("loc")
        if args.require_country:
            assert report["country"] == args.require_country
        zone = api._client.get("/x/web-interface/zone")
        zone.raise_for_status()
        report["bilibili_country"] = (zone.json().get("data") or {}).get("country")
        streams = api.get_play_url(args.bvid, args.cid, VideoQuality.Q480P, preferred_codec=7)
        video = next(stream for stream in streams["video_streams"] if stream.id == 32 and stream.codecid == 7)
        audio = streams["audio_streams"][0]
        selected = {}
        for track, stream in (("video", video), ("audio", audio)):
            url = next(url for url in [stream.base_url, *stream.backup_url]
                       if httpx.URL(url).host == "upos-hz-mirrorakam.akamaized.net")
            url = trusted_https_url(url, BILIBILI_RESOURCE_HOSTS)
            selected[track] = stream.model_copy(update={"base_url": url, "backup_url": []})
            with real_client(transport=httpx.HTTPTransport(verify=SSL_CONTEXT), timeout=20) as client:
                with client.stream("GET", url, headers=STREAM_HEADERS, follow_redirects=False) as response:
                    report[track + "_original_status"] = response.status_code

        class Playback:
            def get_play_url(self, **kwargs):
                return {"video_streams": [selected["video"]], "audio_streams": [selected["audio"]]}

        with tempfile.TemporaryDirectory(prefix="biliflow-cdn-smoke-") as temporary:
            directory = Path(temporary)
            with patch.object(downloader_module.httpx, "Client", recording_client):
                downloader = RecordingDownloader(Playback(), temporary, max_retries=1, ffmpeg_path=args.ffmpeg)
                item = DownloadItem(video_info=VideoInfo(bvid=args.bvid, cid=args.cid, title="CDN validation"),
                                    selected_quality=VideoQuality.Q480P, selected_video_codec=7)
                output = Path(downloader.download(item, lambda fraction, text: None))
                state["phase"] = "decode"
                inspection = FFmpegManager.inspect_media(output, OutputMode.VIDEO, custom_path=args.ffmpeg)
                assert inspection["valid"] and inspection["has_video"] and inspection["has_audio"]
                exe = FFmpegManager.find_executable(args.ffmpeg)
                assert exe is not None
                decoded = subprocess.run(
                    [str(exe), "-nostdin", "-hide_banner", "-v", "error", "-xerror",
                     "-protocol_whitelist", "file", "-i", str(output), "-f", "null", "-"],
                    capture_output=True, timeout=120,
                )
                assert decoded.returncode == 0
                report["merged"] = {"bytes": output.stat().st_size, "sha256": sha256(output),
                                    "duration": inspection["duration"], "has_video": True, "has_audio": True,
                                    "full_decode_passed": True}

                state["phase"] = "interruption"
                interrupted = RecordingDownloader(Playback(), temporary, max_retries=1)
                partial = directory / "resume.m4s"

                def cancel_after_prefix(fraction):
                    if 0.1 <= fraction < 1.0:
                        interrupted.cancel()

                try:
                    interrupted._download_stream(selected["video"], partial, cancel_after_prefix)
                except RuntimeError:
                    assert interrupted._cancelled
                else:
                    raise AssertionError("interruption did not occur")
                offset = partial.stat().st_size
                assert 0 < offset < report["video"]["bytes"]
                assert not partial.with_suffix(".m4s.complete").exists()
                state["phase"] = "resume"
                resumed = RecordingDownloader(Playback(), temporary, max_retries=1)
                progress = []
                resumed._download_stream(selected["video"], partial, progress.append)
                assert progress == sorted(progress) and progress[-1] == 1.0
                assert all(value < 1.0 for value in progress[:-1])
                assert sha256(partial) == report["video"]["sha256"]
                assert int(partial.with_suffix(".m4s.complete").read_text()) == partial.stat().st_size
                resume_requests = [request for request in report["requests"] if request["phase"] == "resume"]
                assert resume_requests[0]["range"].startswith(f"bytes={offset}-")
                report["resume"] = {"offset": offset, "bytes": partial.stat().st_size,
                                    "matches_full_download_sha256": True, "progress_monotonic": True,
                                    "completion_marker_bytes": int(partial.with_suffix(".m4s.complete").read_text())}
        assert all(request["status"] == 206 for request in report["requests"])
        for track in ("video", "audio"):
            responses = [request for request in report["requests"] if request["phase"] == "full" and request["track"] == track]
            assert int(responses[-1]["content_range"].split("/")[-1]) == report[track]["bytes"]
        report.update(passed=True, temporary_media_removed=True)
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__)
        if isinstance(error, httpx.HTTPStatusError):
            report.update(status=error.response.status_code, host=error.request.url.host)
    finally:
        api.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "requests"}, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
