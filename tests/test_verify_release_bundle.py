from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.verify_release_bundle import VerificationError, verify_release_bundle

RELEASE_ID = "dry-run-42"


def _write_zip(path: Path, executable: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(executable, b"binary")
        archive.writestr("README.txt", b"release")


def _write_bundle(directory: Path) -> None:
    assets = {
        f"BilibiliDownloader-macOS-{RELEASE_ID}.zip": (
            "BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader"
        ),
        f"BilibiliDownloader-Windows-{RELEASE_ID}.zip": (
            "BilibiliDownloader/BilibiliDownloader.exe"
        ),
    }
    for filename, executable in assets.items():
        _write_zip(directory / filename, executable)

    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [{"name": "x"}]}
    for platform in ("macOS", "Windows"):
        path = directory / f"BilibiliDownloader-{platform}-{RELEASE_ID}.cdx.json"
        path.write_text(json.dumps(sbom), encoding="utf-8")

    (directory / "release-notes.md").write_text("## Release\n", encoding="utf-8")
    checksum_lines = []
    for path in sorted(directory.glob("*.zip")) + sorted(directory.glob("*.cdx.json")):
        checksum_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (directory / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )


def test_verify_release_bundle_accepts_complete_bundle(tmp_path: Path) -> None:
    _write_bundle(tmp_path)

    counts = verify_release_bundle(tmp_path, RELEASE_ID)

    assert counts == {"archives": 2, "archive_members": 4, "sboms": 2, "components": 2}


def test_verify_release_bundle_rejects_checksum_mismatch(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    archive = tmp_path / f"BilibiliDownloader-Windows-{RELEASE_ID}.zip"
    archive.write_bytes(archive.read_bytes() + b"changed")

    with pytest.raises(VerificationError, match="SHA-256 mismatch"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_missing_executable(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    archive = tmp_path / f"BilibiliDownloader-macOS-{RELEASE_ID}.zip"
    _write_zip(archive, "BilibiliDownloader.app/Contents/Resources/icon.png")

    with pytest.raises(VerificationError, match="expected executable"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_unsafe_archive_path(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    archive = tmp_path / f"BilibiliDownloader-Windows-{RELEASE_ID}.zip"
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("../escape.txt", b"unsafe")

    with pytest.raises(VerificationError, match="unsafe path"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_windows_absolute_archive_path(
    tmp_path: Path,
) -> None:
    _write_bundle(tmp_path)
    archive = tmp_path / f"BilibiliDownloader-Windows-{RELEASE_ID}.zip"
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("C:/escape.txt", b"unsafe")

    with pytest.raises(VerificationError, match="unsafe path"):
        verify_release_bundle(tmp_path, RELEASE_ID)


def test_verify_release_bundle_rejects_invalid_sbom(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    sbom = tmp_path / f"BilibiliDownloader-macOS-{RELEASE_ID}.cdx.json"
    sbom.write_text('{"bomFormat": "other"}', encoding="utf-8")

    with pytest.raises(VerificationError, match="not a CycloneDX SBOM"):
        verify_release_bundle(tmp_path, RELEASE_ID)
