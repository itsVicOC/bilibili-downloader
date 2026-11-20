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
    StreamDownloader,
    _stream_urls,
)
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import (
    DownloadItem,
    OutputMode,
    VideoInfo,
    VideoQuality,
)
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

ISSUE33_HOST = "upos-hz-mirrorakam.akamaized.net"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_type(header):
    if header is None:
        return "full"
    match = re.fullmatch(r"bytes=\d+-(\d*)", header)
    if match is None:
        raise AssertionError("Invalid media Range header")
    return "bounded" if match.group(1) else "open"


def verify_sequence(requests, expected, initial_type):
    # Redirects forward the same Range policy and do not provide the media body.
    transfers = [row for row in requests if row["status"] is None or not 300 <= row["status"] < 400]
    assert transfers and transfers[0]["type"] == initial_type
    if expected == "fast":
        assert len(transfers) == 1
        assert transfers[0]["status"] in ((200, 206) if initial_type == "full" else (206,))
    if expected == "bounded":
        assert len(transfers) > 1 and transfers[0]["status"] == 403
        assert all(row["type"] == "bounded" and row["status"] == 206 for row in transfers[1:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bvid", default="BV1GJ411x7h7")
    parser.add_argument("--cid", type=int, default=137649199)
    parser.add_argument("--require-country")
    parser.add_argument("--expect", choices=("auto", "fast", "bounded"), default="auto",
                        help="Check a single continuous transfer or a 403 followed by bounded ranges")
    parser.add_argument("--cdn-host", help="Select one CDN host from the playback response")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    cdn_host = args.cdn_host.lower() if args.cdn_host else (ISSUE33_HOST if args.expect == "bounded" else None)
    report = {"bvid": args.bvid, "cid": args.cid, "authenticated": False,
              "expected_mode": args.expect, "selected_cdn": cdn_host,
              "range_chunk_size": downloader_module.RANGE_CHUNK_SIZE,
              "downloader_sha256": sha256(Path(downloader_module.__file__)), "requests": []}
    real_client = httpx.Client
    state = {"phase": "full", "track": ""}

    def observe_request(request):
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers
        byte_range = request.headers.get("range")
        record = {**state, "host": request.url.host, "type": request_type(byte_range),
                  "range": byte_range, "status": None, "content_range": None}
        request.extensions["biliflow_smoke_record"] = record
        report["requests"].append(record)

    def observe_response(response):
        record = response.request.extensions["biliflow_smoke_record"]
        content_range = response.headers.get("content-range", "")
        record["status"] = response.status_code
        if re.fullmatch(r"bytes (?:\d+-\d+|\*)/(?:\d+|\*)", content_range, re.I):
            record["content_range"] = content_range

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
        report["step"] = "location"
        try:
            with real_client(timeout=20) as client:
                trace = client.get("https://www.cloudflare.com/cdn-cgi/trace")
                trace.raise_for_status()
                fields = dict(line.split("=", 1) for line in trace.text.splitlines() if "=" in line)
                report["country"] = fields.get("loc")
        except httpx.HTTPError:
            report["country"] = None
        if args.require_country:
            assert report["country"] == args.require_country
        try:
            zone = api._client.get("/x/web-interface/zone")
            zone.raise_for_status()
            report["bilibili_country"] = (zone.json().get("data") or {}).get("country")
        except (httpx.HTTPError, ValueError):
            report["bilibili_country"] = None
        report["step"] = "playback"
        streams = api.get_play_url(args.bvid, args.cid, VideoQuality.Q480P, preferred_codec=7)
        video = next(stream for stream in streams["video_streams"] if stream.id == 32 and stream.codecid == 7)
        audio = streams["audio_streams"][0]
        selected = {"video": video, "audio": audio}
        report["available_cdns"] = {
            track: sorted({httpx.URL(url).host for url in _stream_urls(stream)})
            for track, stream in selected.items()
        }
        if cdn_host:
            report["step"] = "select_cdn"
            for track, stream in selected.items():
                url = next((url for url in _stream_urls(stream) if httpx.URL(url).host == cdn_host), None)
                if url is None:
                    report["missing_cdn_for"] = track
                    raise ValueError("Requested CDN was not offered for the public sample")
                url = trusted_https_url(url, BILIBILI_RESOURCE_HOSTS)
                selected[track] = stream.model_copy(update={"base_url": url, "backup_url": []})

        class Playback:
            def get_play_url(self, **kwargs):
                return {"video_streams": [selected["video"]], "audio_streams": [selected["audio"]]}

        with tempfile.TemporaryDirectory(prefix="biliflow-cdn-smoke-") as temporary:
            directory = Path(temporary)
            with patch.object(downloader_module.httpx, "Client", recording_client):
                report["step"] = "download"
                downloader = RecordingDownloader(Playback(), temporary, max_retries=1, ffmpeg_path=args.ffmpeg)
                item = DownloadItem(video_info=VideoInfo(bvid=args.bvid, cid=args.cid, title="CDN validation"),
                                    selected_quality=VideoQuality.Q480P, selected_video_codec=7)
                output = Path(downloader.download(item, lambda fraction, text: None))
                report["step"] = "decode"
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

                report["step"] = state["phase"] = "interruption"
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
                report["step"] = state["phase"] = "resume"
                resumed = RecordingDownloader(Playback(), temporary, max_retries=1)
                progress = []
                resumed._download_stream(selected["video"], partial, progress.append)
                assert progress == sorted(progress) and progress[-1] == 1.0
                assert all(value < 1.0 for value in progress[:-1])
                assert sha256(partial) == report["video"]["sha256"]
                assert int(partial.with_suffix(".m4s.complete").read_text()) == partial.stat().st_size
                resume_requests = [request for request in report["requests"] if request["phase"] == "resume"]
                assert resume_requests[0]["range"] == f"bytes={offset}-"
                report["resume"] = {"offset": offset, "bytes": partial.stat().st_size,
                                    "matches_full_download_sha256": True, "progress_monotonic": True,
                                    "range_honored": any(row["status"] == 206 for row in resume_requests),
                                    "completion_marker_bytes": int(partial.with_suffix(".m4s.complete").read_text())}
        report["step"] = "sequence"
        verify_sequence(resume_requests, args.expect, "open")
        for track in ("video", "audio"):
            responses = [request for request in report["requests"] if request["phase"] == "full" and request["track"] == track]
            verify_sequence(responses, args.expect, "full")
            assert responses[-1]["status"] in (200, 206, 416)
            if responses[-1]["content_range"] is not None:
                assert int(responses[-1]["content_range"].split("/")[-1]) == report[track]["bytes"]
        report.update(step="complete", passed=True, temporary_media_removed=True)
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__)
        http_error = error if isinstance(error, httpx.HTTPStatusError) else error.__cause__
        if isinstance(http_error, httpx.HTTPStatusError):
            report.update(status=http_error.response.status_code, host=http_error.request.url.host)
    finally:
        api.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "requests"}, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
