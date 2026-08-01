from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
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
CONFIGURE_ARGS = (
    "--disable-everything",
    "--disable-autodetect",
    "--disable-doc",
    "--disable-debug",
    "--disable-network",
    "--disable-ffplay",
    "--disable-ffprobe",
    "--enable-ffmpeg",
    "--enable-protocol=file",
    "--enable-demuxer=mov",
    "--enable-muxer=mp4",
    "--enable-muxer=ipod",
    "--enable-muxer=flac",
)
MACOS_CONFIGURE_ARGS = (
    "--extra-cflags=-mmacosx-version-min=12.0",
    "--extra-ldflags=-mmacosx-version-min=12.0",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_source(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.part")
    request = urllib.request.Request(
        FFMPEG_SOURCE_URL,
        headers={"User-Agent": "BiliFlow release builder"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open(
            "wb"
        ) as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        actual = sha256(temporary)
        if actual != FFMPEG_SOURCE_SHA256:
            raise ValueError(
                f"FFmpeg source SHA-256 mismatch: expected {FFMPEG_SOURCE_SHA256}, "
                f"got {actual}"
            )
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
    return version_text, license_text


def validate_binary_output(version_text: str, license_text: str) -> None:
    if f"ffmpeg version {FFMPEG_VERSION}" not in version_text:
        raise ValueError(f"bundled executable is not FFmpeg {FFMPEG_VERSION}")
    missing_args = [arg for arg in CONFIGURE_ARGS if arg not in version_text]
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


def prepare_release_metadata(
    binary: Path,
    base_sbom: Path,
    lite_sbom: Path,
    full_sbom: Path,
    notice: Path,
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
                "The bundled executable is a separate FFmpeg program built only for",
                "local, lossless MP4/M4A/FLAC stream packaging. The matching source",
                "archive is published beside the BiliFlow full downloads.",
                "",
                version_text,
                "",
                license_text,
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
    components.append(
        {
            "type": "application",
            "bom-ref": f"pkg:generic/ffmpeg@{FFMPEG_VERSION}",
            "name": "FFmpeg",
            "version": FFMPEG_VERSION,
            "licenses": [{"license": {"id": "LGPL-2.1-or-later"}}],
            "hashes": [{"alg": "SHA-256", "content": binary_sha256}],
            "purl": f"pkg:generic/ffmpeg@{FFMPEG_VERSION}",
            "externalReferences": [
                {
                    "type": "vcs",
                    "url": f"https://github.com/FFmpeg/FFmpeg/tree/{FFMPEG_COMMIT}",
                },
                {"type": "distribution", "url": FFMPEG_SOURCE_URL},
            ],
        }
    )
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

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--binary", type=Path, required=True)
    prepare_parser.add_argument("--base-sbom", type=Path, required=True)
    prepare_parser.add_argument("--lite-sbom", type=Path, required=True)
    prepare_parser.add_argument("--full-sbom", type=Path, required=True)
    prepare_parser.add_argument("--notice", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "download-source":
        download_source(args.output)
    else:
        prepare_release_metadata(
            args.binary,
            args.base_sbom,
            args.lite_sbom,
            args.full_sbom,
            args.notice,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
