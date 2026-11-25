from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

FFMPEG_VERSION = "7.1"
FFMPEG_COMMIT = "b08d7969c550a804a59511c7b83f2dd8cc0499b8"
FFMPEG_SOURCE_FILENAME = "FFmpeg-7.1-source.tar.gz"
FFMPEG_SOURCE_SHA256 = "02fa6d9827da3b6786e4df821218cc036db2b4481e7f48267c2dcda695633afc"
FFMPEG_SOURCE_URL = (
    "https://github.com/FFmpeg/FFmpeg/archive/"
    f"{FFMPEG_COMMIT}.tar.gz"
)
DAV1D_VERSION = "1.5.5"
DAV1D_SOURCE_URL = f"https://download.videolan.org/pub/videolan/dav1d/{DAV1D_VERSION}/dav1d-{DAV1D_VERSION}.tar.xz"
DAV1D_SOURCE_SHA256 = "ca96b1d0ba3f01f55de7231d775892b64994ba061aaeeaaa4f662a390b3abf9e"

CONFIGURE_ARGS = (
    "--disable-everything",
    "--disable-autodetect",
    "--disable-doc",
    "--disable-debug",
    "--disable-network",
    "--disable-x86asm",
    "--disable-ffplay",
    "--disable-ffprobe",
    "--enable-ffmpeg",
    "--enable-protocol=file",
    "--enable-protocol=pipe",
    "--enable-demuxer=mov",
    "--enable-demuxer=flv",
    "--enable-demuxer=mpegts",
    "--enable-demuxer=concat",
    "--enable-parser=h264",
    "--enable-parser=aac",
    "--enable-parser=hevc,av1",
    "--enable-decoder=aac",
    "--enable-decoder=h264,hevc,libdav1d",
    "--enable-libdav1d",
    "--pkg-config-flags=--static",
    "--enable-encoder=mjpeg",
    "--enable-swscale",
    "--enable-filter=scale,format,transpose,hflip,vflip,rotate",
    "--enable-bsf=aac_adtstoasc",
    "--enable-bsf=extract_extradata",
    "--enable-bsf=h264_mp4toannexb",
    "--enable-muxer=mp4",
    "--enable-muxer=ipod",
    "--enable-muxer=flac",
    "--enable-muxer=image2pipe",
)
MACOS_CONFIGURE_ARGS = (
    "--extra-cflags=-mmacosx-version-min=12.0",
    "--extra-ldflags=-mmacosx-version-min=12.0",
)
WINDOWS_CONFIGURE_ARGS = (
    "--disable-pthreads",
    "--enable-w32threads",
    "--extra-ldflags=-static",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_source(output: Path, url=FFMPEG_SOURCE_URL, expected_sha256=FFMPEG_SOURCE_SHA256) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BiliFlow release builder"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open(
            "wb"
        ) as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        actual = sha256(temporary)
        if actual != expected_sha256:
            raise ValueError(f"Source SHA-256 mismatch: expected {expected_sha256}, got {actual}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def inspect_binary(binary: Path) -> tuple[str, str]:
    version = subprocess.run(
        [str(binary), "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    license_result = subprocess.run(
        [str(binary), "-L"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    version_text = (version.stdout + version.stderr).strip()
    license_text = (license_result.stdout + license_result.stderr).strip()
    validate_binary_output(version_text, license_text)
    if platform.system() == "Darwin":
        validate_macos_binary_output(version_text)
    elif platform.system() == "Windows":
        validate_windows_binary_output(version_text)
    return version_text, license_text


def verify_thumbnails(binary: Path) -> None:
    from PySide6.QtGui import QImage

    from bilibili_downloader.core.ffmpeg import FFmpegManager

    fixture_ffmpeg = shutil.which("ffmpeg")
    if not fixture_ffmpeg:
        raise RuntimeError("The FFmpeg fixture encoder is unavailable")
    encoders = subprocess.check_output([fixture_ffmpeg, "-hide_banner", "-encoders"], timeout=10, text=True)
    av1_encoder = "libsvtav1" if "libsvtav1" in encoders else "libaom-av1"
    with tempfile.TemporaryDirectory(prefix="biliflow-thumbnails-") as temporary:
        for codec, encoder in (("H.264", "libx264"), ("HEVC", "libx265"), ("AV1", av1_encoder)):
            video = Path(temporary) / "视频样本.mp4"
            subprocess.run([
                fixture_ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=352x198:rate=12",
                "-t", "1", "-c:v", encoder, "-threads", "1", str(video),
            ], check=True, timeout=30)
            frame = QImage.fromData(FFmpegManager.thumbnail_frame(video, binary.resolve(), 1))
            if frame.isNull() or frame.width() > 480 or frame.height() > 270:
                raise ValueError(f"Bundled FFmpeg failed to extract a thumbnail from {codec}")
            print(f"{codec}: {frame.width()} x {frame.height()}")


def validate_binary_output(version_text: str, license_text: str) -> None:
    if f"ffmpeg version {FFMPEG_VERSION}" not in version_text:
        raise ValueError(f"bundled executable is not FFmpeg {FFMPEG_VERSION}")
    normalized_version = version_text.replace("'", "").replace('"', "")
    missing_args = [arg for arg in CONFIGURE_ARGS if arg not in normalized_version]
    if missing_args:
        raise ValueError(f"bundled FFmpeg is missing configure args: {missing_args}")
    normalized_license = " ".join(license_text.split())
    if "GNU Lesser General Public License" not in normalized_license:
        raise ValueError("bundled FFmpeg does not report the LGPL")
    if "--enable-gpl" in version_text or "--enable-nonfree" in version_text:
        raise ValueError("bundled FFmpeg enables GPL or nonfree components")


def validate_macos_binary_output(version_text: str) -> None:
    normalized_version = version_text.replace("'", "").replace('"', "")
    missing_args = [arg for arg in MACOS_CONFIGURE_ARGS if arg not in normalized_version]
    if missing_args:
        raise ValueError(
            f"bundled macOS FFmpeg is missing deployment target args: {missing_args}"
        )


def validate_windows_binary_output(version_text: str) -> None:
    missing_args = [arg for arg in WINDOWS_CONFIGURE_ARGS if arg not in version_text]
    if missing_args:
        raise ValueError(
            f"bundled Windows FFmpeg is missing self-contained threading args: {missing_args}"
        )


def prepare_release_metadata(
    binary: Path,
    base_sbom: Path,
    lite_sbom: Path,
    full_sbom: Path,
    notice: Path,
    dav1d_license: Path,
) -> None:
    version_text, license_text = inspect_binary(binary)
    binary_sha256 = sha256(binary)

    notice.parent.mkdir(parents=True, exist_ok=True)
    notice.write_text(
        "\n".join(
            [
                "BiliFlow bundled FFmpeg notice",
                "",
                f"Version: {FFMPEG_VERSION}",
                f"Source commit: {FFMPEG_COMMIT}",
                f"Source archive: {FFMPEG_SOURCE_FILENAME}",
                f"Source URL: {FFMPEG_SOURCE_URL}",
                f"Source SHA-256: {FFMPEG_SOURCE_SHA256}",
                f"Binary SHA-256: {binary_sha256}",
                "License: LGPL-2.1-or-later",
                "",
                "The bundled executable is a separate FFmpeg program for local lossless",
                "stream packaging and video thumbnails. The FFmpeg source archive is",
                "published beside the BiliFlow full downloads.",
                "",
                version_text,
                "",
                license_text,
                "",
                f"Statically linked component: dav1d {DAV1D_VERSION} (BSD-2-Clause)",
                f"Source URL: {DAV1D_SOURCE_URL}",
                f"Source SHA-256: {DAV1D_SOURCE_SHA256}",
                "",
                dav1d_license.read_text(encoding="utf-8").strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = json.loads(base_sbom.read_text(encoding="utf-8"))
    lite_sbom.parent.mkdir(parents=True, exist_ok=True)
    lite_sbom.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    components = payload.setdefault("components", [])
    if any(component.get("name") == "FFmpeg" for component in components):
        raise ValueError("base SBOM already contains FFmpeg")
    ffmpeg_ref = f"pkg:generic/ffmpeg@{FFMPEG_VERSION}"
    dav1d_ref = f"pkg:generic/dav1d@{DAV1D_VERSION}"
    components.append(
        {
            "type": "application",
            "bom-ref": ffmpeg_ref,
            "name": "FFmpeg",
            "version": FFMPEG_VERSION,
            "licenses": [{"license": {"id": "LGPL-2.1-or-later"}}],
            "hashes": [{"alg": "SHA-256", "content": binary_sha256}],
            "purl": ffmpeg_ref,
            "externalReferences": [
                {
                    "type": "vcs",
                    "url": f"https://github.com/FFmpeg/FFmpeg/tree/{FFMPEG_COMMIT}",
                },
                {"type": "distribution", "url": FFMPEG_SOURCE_URL},
            ],
        }
    )
    components.append({
        "type": "library",
        "bom-ref": dav1d_ref,
        "name": "dav1d",
        "version": DAV1D_VERSION,
        "licenses": [{"license": {"id": "BSD-2-Clause"}}],
        "purl": dav1d_ref,
        "externalReferences": [{"type": "distribution", "url": DAV1D_SOURCE_URL,
                                "hashes": [{"alg": "SHA-256", "content": DAV1D_SOURCE_SHA256}]}],
    })
    payload.setdefault("dependencies", []).append({"ref": ffmpeg_ref, "dependsOn": [dav1d_ref]})
    full_sbom.parent.mkdir(parents=True, exist_ok=True)
    full_sbom.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare bundled FFmpeg release files")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_parser = subparsers.add_parser("download-source")
    download_parser.add_argument("--output", type=Path, required=True)
    dav1d_parser = subparsers.add_parser("download-dav1d-source")
    dav1d_parser.add_argument("--output", type=Path, required=True)
    thumbnail_parser = subparsers.add_parser("verify-thumbnails")
    thumbnail_parser.add_argument("--binary", type=Path, required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--binary", type=Path, required=True)
    prepare_parser.add_argument("--base-sbom", type=Path, required=True)
    prepare_parser.add_argument("--lite-sbom", type=Path, required=True)
    prepare_parser.add_argument("--full-sbom", type=Path, required=True)
    prepare_parser.add_argument("--notice", type=Path, required=True)
    prepare_parser.add_argument("--dav1d-license", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "download-source":
        download_source(args.output)
    elif args.command == "download-dav1d-source":
        download_source(args.output, DAV1D_SOURCE_URL, DAV1D_SOURCE_SHA256)
    elif args.command == "verify-thumbnails":
        verify_thumbnails(args.binary)
    else:
        prepare_release_metadata(
            args.binary,
            args.base_sbom,
            args.lite_sbom,
            args.full_sbom,
            args.notice,
            args.dav1d_license,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
