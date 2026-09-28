from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import verify_release_bundle as verifier
from scripts.prepare_bundled_ffmpeg import FFMPEG_SOURCE_FILENAME
from scripts.verify_release_bundle import VerificationError, verify_release_bundle

RELEASE_ID = "dry-run-42"


def _write_zip(path: Path, executable: str, includes_ffmpeg: bool) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(executable, b"binary")
        archive.writestr("README.txt", b"release")
        if includes_ffmpeg:
            if "macOS" in path.name:
                root = "BilibiliDownloader.app/Contents/Resources/"
                ffmpeg_name = "ffmpeg"
            else:
                root = "BilibiliDownloader/"
                ffmpeg_name = "ffmpeg.exe"
            archive.writestr(root + ffmpeg_name, b"ffmpeg")
            archive.writestr(root + "FFMPEG-NOTICE.txt", b"notice")
            archive.writestr(root + "COPYING.LGPLv2.1", b"license")
            archive.writestr(root + "FFMPEG-LICENSE.md", b"upstream")
            archive.writestr(root + ("biliflow-recorder" if "macOS" in path.name else "biliflow-recorder.exe"), b"recorder")
            archive.writestr(root + "RECORDER-NOTICE.txt", b"recorder notice")


def _write_source_archive(path: Path) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in (
            ("FFmpeg-test/configure", b"#!/bin/sh\n"),
            ("FFmpeg-test/COPYING.LGPLv2.1", b"license"),
            ("FFmpeg-test/LICENSE.md", b"notice"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _write_bundle(directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assets = {
        f"BilibiliDownloader-macOS-lite-{RELEASE_ID}.zip": (
            "BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader",
            False,
        ),
        f"BilibiliDownloader-macOS-full-{RELEASE_ID}.zip": (
            "BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader",
            True,
        ),
        f"BilibiliDownloader-Windows-lite-{RELEASE_ID}.zip": (
            "BilibiliDownloader/BilibiliDownloader.exe",
            False,
        ),
        f"BilibiliDownloader-Windows-full-{RELEASE_ID}.zip": (
            "BilibiliDownloader/BilibiliDownloader.exe",
            True,
        ),
    }
    for filename, (executable, includes_ffmpeg) in assets.items():
        _write_zip(directory / filename, executable, includes_ffmpeg)

    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [{"name": "x"}]}
    for platform in ("macOS", "Windows"):
        for variant in ("lite", "full"):
            payload = json.loads(json.dumps(sbom))
            if variant == "full":
                payload["components"].append(
                    {
                        "name": "FFmpeg",
                        "version": "7.1",
                        "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(b"ffmpeg").hexdigest()}],
                    }
                )
                payload["components"].append({"name": "biliflow-recorder", "version": "0.1.0",
                    "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(b"recorder").hexdigest()}],
                    "properties": [{"name": "biliflow:mesio-revision",
                                    "value": "1897d736a4560f267700d7c4c1cf02dffc3c4c56"}]})
            path = directory / (
                f"BilibiliDownloader-{platform}-{variant}-{RELEASE_ID}.cdx.json"
            )
            path.write_text(json.dumps(payload), encoding="utf-8")

    source_path = directory / FFMPEG_SOURCE_FILENAME
    _write_source_archive(source_path)
    monkeypatch.setattr(
        verifier,
        "FFMPEG_SOURCE_SHA256",
        hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )

    (directory / "release-notes.md").write_text("## Release\n", encoding="utf-8")
    checksum_lines = []
    checksum_assets = (
        sorted(directory.glob("*.zip"))
        + sorted(directory.glob("*.cdx.json"))
        + sorted(directory.glob("*.tar.gz"))
    )
    for path in checksum_assets:
        checksum_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (directory / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )


def test_verify_release_bundle_accepts_complete_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)

    counts = verify_release_bundle(tmp_path, RELEASE_ID)

    assert counts["archives"] == 4
    assert counts["sboms"] == 4
    assert counts["components"] == 8
    assert counts["source_files"] == 3


def test_verify_release_bundle_rejects_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    archive = tmp_path / f"BilibiliDownloader-Windows-lite-{RELEASE_ID}.zip"
    archive.write_bytes(archive.read_bytes() + b"changed")

    with pytest.raises(VerificationError, match="SHA-256 mismatch"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_missing_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    archive = tmp_path / f"BilibiliDownloader-macOS-lite-{RELEASE_ID}.zip"
    _write_zip(
        archive,
        "BilibiliDownloader.app/Contents/Resources/icon.png",
        False,
    )

    with pytest.raises(VerificationError, match="expected executable"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_unsafe_archive_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    archive = tmp_path / f"BilibiliDownloader-Windows-lite-{RELEASE_ID}.zip"
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("../escape.txt", b"unsafe")

    with pytest.raises(VerificationError, match="unsafe path"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_windows_absolute_archive_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    archive = tmp_path / f"BilibiliDownloader-Windows-lite-{RELEASE_ID}.zip"
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("C:/escape.txt", b"unsafe")

    with pytest.raises(VerificationError, match="unsafe path"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_invalid_sbom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    sbom = tmp_path / f"BilibiliDownloader-macOS-lite-{RELEASE_ID}.cdx.json"
    sbom.write_text('{"bomFormat": "other"}', encoding="utf-8")

    with pytest.raises(VerificationError, match="not a CycloneDX SBOM"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_ffmpeg_in_lite_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    archive = tmp_path / f"BilibiliDownloader-Windows-lite-{RELEASE_ID}.zip"
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("BilibiliDownloader/ffmpeg.exe", b"unexpected")

    with pytest.raises(VerificationError, match="unexpectedly contains"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_incomplete_full_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(tmp_path, monkeypatch)
    archive = tmp_path / f"BilibiliDownloader-macOS-full-{RELEASE_ID}.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader", b"binary"
        )
        bundle.writestr(
            "BilibiliDownloader.app/Contents/Resources/ffmpeg", b"ffmpeg"
        )

    with pytest.raises(VerificationError, match="required file"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_pre_signing_media_hash(tmp_path, monkeypatch):
    _write_bundle(tmp_path, monkeypatch)
    sbom = tmp_path / f"BilibiliDownloader-macOS-full-{RELEASE_ID}.cdx.json"
    payload = json.loads(sbom.read_text())
    next(c for c in payload["components"] if c["name"] == "biliflow-recorder")["hashes"][0]["content"] = "0" * 64
    sbom.write_text(json.dumps(payload))
    with pytest.raises(VerificationError, match="hash differs from SBOM"):
        verify_release_bundle(tmp_path, RELEASE_ID)
