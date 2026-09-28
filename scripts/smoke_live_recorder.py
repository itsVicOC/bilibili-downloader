"""Cross-platform recorder gate using generated media, never a real live room.

Build with --features test-fixtures for this gate. Distributed binaries must be
built without that feature (prepare_bundled_recorder rejects fixture builds).
"""

import argparse
import functools
import json
import queue
import subprocess
import tempfile
import threading
import time
from contextlib import nullcontext
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def generate(root, ffmpeg):
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(
        [
            *base,
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "7.3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "50",
            "-c:a",
            "aac",
            str(root / "sample.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [*base, "-i", str(root / "sample.mp4"), "-c", "copy", str(root / "sample.flv")],
        check=True,
    )
    for kind in ("mpegts", "fmp4"):
        directory = root / kind
        directory.mkdir()
        subprocess.run(
            [
                *base,
                "-i",
                str(root / "sample.mp4"),
                "-c",
                "copy",
                "-f",
                "hls",
                "-hls_time",
                "2",
                "-hls_list_size",
                "0",
                "-hls_segment_type",
                kind,
                str(directory / "index.m3u8"),
            ],
            check=True,
        )
    second = root / "changed"
    second.mkdir()
    subprocess.run(
        [
            *base,
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=44100",
            "-t",
            "3.3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "50",
            "-c:a",
            "aac",
            str(second / "sample.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            *base,
            "-i",
            str(second / "sample.mp4"),
            "-c",
            "copy",
            str(second / "sample.flv"),
        ],
        check=True,
    )
    (root / "changed.flv").write_bytes(
        (root / "sample.flv").read_bytes() + (second / "sample.flv").read_bytes()[13:]
    )
    for kind in ("mpegts", "fmp4"):
        directory = second / kind
        directory.mkdir()
        subprocess.run(
            [
                *base,
                "-i",
                str(second / "sample.mp4"),
                "-c",
                "copy",
                "-f",
                "hls",
                "-hls_time",
                "2",
                "-hls_list_size",
                "0",
                "-hls_segment_type",
                kind,
                str(directory / "index.m3u8"),
            ],
            check=True,
        )

        def lines(path, prefix):
            result = []
            for line in path.read_text().splitlines():
                if not line.startswith("#"):
                    line = prefix + line
                elif 'URI="' in line:
                    line = line.replace('URI="', f'URI="{prefix}')
                result.append(line)
            return result

        first_lines = lines(root / kind / "index.m3u8", kind + "/")
        second_lines = lines(directory / "index.m3u8", f"changed/{kind}/")
        second_lines = [
            line
            for line in second_lines
            if line != "#EXTM3U"
            and not line.startswith(
                ("#EXT-X-VERSION:", "#EXT-X-TARGETDURATION:", "#EXT-X-MEDIA-SEQUENCE:")
            )
        ]
        joined = (
            [line for line in first_lines if line != "#EXT-X-ENDLIST"]
            + ["#EXT-X-DISCONTINUITY"]
            + second_lines
        )
        (root / f"changed-{kind}.m3u8").write_text("\n".join(joined) + "\n")


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/continuous.flv":
            source = (Path(self.directory) / "sample.flv").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/x-flv")
            self.end_headers()
            try:
                self.wfile.write(source)
                self.wfile.flush()
                while True:
                    time.sleep(0.1)
                    # Skip the FLV file header; the repair pipeline handles the
                    # timestamp reset between copies of the synthetic stream.
                    self.wfile.write(source[13:])
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        else:
            super().do_GET()


def run_recording(
    binary, url, directory, format_name, stop_mode=None, expected_error=None
):
    process = subprocess.Popen(
        [str(binary)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    events = queue.Queue()

    def read():
        for line in process.stdout:
            events.put(json.loads(line))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    process.stdin.write(
        (
            json.dumps(
                {
                    "v": 1,
                    "command": "start",
                    "url": url,
                    "output_dir": str(directory),
                    "format": format_name,
                    "segment_seconds": 2,
                }
            )
            + "\n"
        ).encode()
    )
    process.stdin.flush()
    received = []
    started = time.monotonic()
    stopped = False
    try:
        while time.monotonic() - started < 30:
            if stop_mode and not stopped and time.monotonic() - started > 2:
                if stop_mode == "stop":
                    process.stdin.write(b'{"v":1,"command":"stop"}\n')
                    process.stdin.flush()
                process.stdin.close()
                stopped = True
            try:
                event = events.get(timeout=0.1)
                received.append(event)
                if event["event"] == "segment_finalized":
                    assert Path(event["path"]).is_file(), event
                if event["event"] == "stopped":
                    break
            except queue.Empty:
                if process.poll() is not None:
                    break
        process.wait(timeout=12)
        reader.join(timeout=2)
        while not events.empty():
            received.append(events.get_nowait())
        assert process.returncode == 0, process.stderr.read().decode()
        assert received and received[-1]["event"] == "stopped", received
        errors = [e for e in received if e["event"] == "error"]
        if expected_error:
            assert any(e.get("code") == expected_error for e in errors), received
            assert not [e for e in received if e["event"] == "segment_finalized"], (
                received
            )
            assert "fixture-secret" not in json.dumps(received)
            return []
        assert not errors, received
        segments = [e for e in received if e["event"] == "segment_finalized"]
        assert segments, received
        if not stop_mode:
            assert len(segments) >= 2, received
        return segments
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()


def probe(path, ffprobe):
    # Count stored AAC packets, including preroll hidden by an MP4 edit list.
    options = ["-ignore_editlist", "1"] if path.suffix in {".mp4", ".m4s"} else []
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            *options,
            "-count_packets",
            "-show_entries",
            "format=duration:stream=codec_name,codec_type,nb_read_packets",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument(
        "--remux-ffmpeg", help="Test the bundled minimal FFmpeg for MP4 export"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Keep generated fixtures and recordings for inspection",
    )
    args = parser.parse_args()
    with (
        nullcontext(args.work_dir)
        if args.work_dir
        else tempfile.TemporaryDirectory(prefix="biliflow-live-smoke-")
    ) as temporary:
        root = Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        generate(root, args.ffmpeg)
        (root / "encrypted.m3u8").write_text(
            '#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-KEY:METHOD=AES-128,URI="key?sign=fixture-secret"\n#EXTINF:2,\nmpegts/index0.ts\n#EXT-X-ENDLIST\n'
        )
        (root / "external.m3u8").write_text(
            "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\nhttps://untrusted.invalid/media?sign=fixture-secret\n#EXT-X-ENDLIST\n"
        )
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(root))
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            for name, error in (
                ("encrypted", "encrypted_media_unsupported"),
                ("external", "untrusted_media_url"),
            ):
                run_recording(
                    args.binary.resolve(),
                    f"{base}/{name}.m3u8",
                    root / name,
                    "ts",
                    expected_error=error,
                )
                print(
                    f"PASS {name}: refused before media access, no signed URL in events",
                    flush=True,
                )
            for name, format_name in (
                ("sample.flv", "flv"),
                ("mpegts/index.m3u8", "ts"),
                ("fmp4/index.m3u8", "fmp4"),
            ):
                segments = run_recording(
                    args.binary.resolve(),
                    f"{base}/{name}",
                    root / f"out-{format_name}",
                    format_name,
                )
                duration = 0
                packets = {"video": 0, "audio": 0}
                for index, segment in enumerate(segments):
                    path = Path(segment["path"])
                    info = probe(path, args.ffprobe)
                    assert {s["codec_name"] for s in info["streams"]} >= {
                        "h264",
                        "aac",
                    }, info
                    for stream in info["streams"]:
                        packets[stream["codec_type"]] += int(stream["nb_read_packets"])
                    mp4 = root / f"export-{format_name}-{index}.mp4"
                    subprocess.run(
                        [
                            args.remux_ffmpeg or args.ffmpeg,
                            "-v",
                            "error",
                            "-y",
                            "-protocol_whitelist",
                            "file",
                            "-i",
                            str(path),
                            "-c",
                            "copy",
                            "-movflags",
                            "+faststart",
                            str(mp4),
                        ],
                        check=True,
                    )
                    exported = probe(mp4, args.ffprobe)
                    # Mesio 0.6.0 stores an integer duration in FLV metadata.
                    # Check packet preservation too, so rounding cannot mask loss.
                    tolerance = 1.1 if format_name == "flv" else 0.3
                    # fMP4 fragments retain the broadcast decode timeline;
                    # ffprobe's format duration includes the absolute offset.
                    expected_duration = (
                        segment["duration"]
                        if format_name == "fmp4"
                        else float(info["format"]["duration"])
                    )
                    assert (
                        abs(float(exported["format"]["duration"]) - expected_duration)
                        < tolerance
                    ), (format_name, index, info, exported, segment)
                    assert [s["nb_read_packets"] for s in info["streams"]] == [
                        s["nb_read_packets"] for s in exported["streams"]
                    ], (info, exported)
                    duration += float(exported["format"]["duration"])
                reference = probe(root / "sample.mp4", args.ffprobe)
                expected = {
                    s["codec_type"]: int(s["nb_read_packets"])
                    for s in reference["streams"]
                }
                assert packets == expected, (format_name, packets, expected)
                assert 7.1 <= duration <= 8.5, (format_name, duration)
                print(
                    f"PASS {format_name}: {len(segments)} playable segments, {duration:.2f}s; MP4 exports verified",
                    flush=True,
                )
            for mode in ("stop", "parent-eof"):
                segments = run_recording(
                    args.binary.resolve(),
                    f"{base}/continuous.flv",
                    root / mode,
                    "flv",
                    mode,
                )
                print(
                    f"PASS {mode}: exited and finalized {len(segments)} segments",
                    flush=True,
                )
            expected_packets = {"video": 0, "audio": 0}
            for source in (root / "sample.mp4", root / "changed/sample.mp4"):
                for stream in probe(source, args.ffprobe)["streams"]:
                    expected_packets[stream["codec_type"]] += int(
                        stream["nb_read_packets"]
                    )
            for name, format_name in (
                ("changed.flv", "flv"),
                ("changed-mpegts.m3u8", "ts"),
                ("changed-fmp4.m3u8", "fmp4"),
            ):
                segments = run_recording(
                    args.binary.resolve(),
                    f"{base}/{name}",
                    root / f"switch-{format_name}",
                    format_name,
                )
                packets = {"video": 0, "audio": 0}
                for segment in segments:
                    for stream in probe(Path(segment["path"]), args.ffprobe)["streams"]:
                        packets[stream["codec_type"]] += int(stream["nb_read_packets"])
                assert packets == expected_packets, (
                    format_name,
                    packets,
                    expected_packets,
                )
                print(
                    f"PASS {format_name}: resolution/timeline change, discontinuity; all media packets retained",
                    flush=True,
                )
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
