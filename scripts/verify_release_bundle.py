from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


class VerificationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_archive(path: Path, executable_suffix: str) -> int:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
    except zipfile.BadZipFile as exc:
        raise VerificationError(f"{path.name} is not a valid ZIP archive") from exc

    if not members:
        raise VerificationError(f"{path.name} is empty")

    for name in members:
        member = PurePosixPath(name.replace("\\", "/"))
        has_windows_drive = bool(member.parts and member.parts[0].endswith(":"))
        if member.is_absolute() or has_windows_drive or ".." in member.parts:
            raise VerificationError(f"{path.name} contains unsafe path {name!r}")

    if not any(name.replace("\\", "/").endswith(executable_suffix) for name in members):
        raise VerificationError(
            f"{path.name} does not contain expected executable {executable_suffix!r}"
        )
    return len(members)


def _verify_sbom(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{path.name} is not valid JSON") from exc

    if payload.get("bomFormat") != "CycloneDX":
        raise VerificationError(f"{path.name} is not a CycloneDX SBOM")
    if not isinstance(payload.get("specVersion"), str):
        raise VerificationError(f"{path.name} has no CycloneDX specVersion")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise VerificationError(f"{path.name} has no components")
    return len(components)


def _read_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise VerificationError(f"{path.name} is not valid UTF-8 text") from exc
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line)
        if not match:
            raise VerificationError(
                f"{path.name}:{line_number} is not a SHA-256 checksum entry"
            )
        checksum, filename = match.groups()
        if filename in checksums:
            raise VerificationError(f"{path.name} repeats {filename!r}")
        checksums[filename] = checksum.lower()
    return checksums


def verify_release_bundle(directory: Path, release_id: str) -> dict[str, int]:
    directory = directory.resolve()
    assets = {
        f"BilibiliDownloader-macOS-{release_id}.zip": (
            "archive",
            "BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader",
        ),
        f"BilibiliDownloader-Windows-{release_id}.zip": (
            "archive",
            "BilibiliDownloader/BilibiliDownloader.exe",
        ),
        f"BilibiliDownloader-macOS-{release_id}.cdx.json": ("sbom", ""),
        f"BilibiliDownloader-Windows-{release_id}.cdx.json": ("sbom", ""),
    }

    notes_path = directory / "release-notes.md"
    if not notes_path.is_file() or not notes_path.read_text(encoding="utf-8").strip():
        raise VerificationError("release-notes.md is missing or empty")

    counts = {"archives": 0, "archive_members": 0, "sboms": 0, "components": 0}
    for filename, (kind, expected) in assets.items():
        path = directory / filename
        if not path.is_file():
            raise VerificationError(f"missing release asset {filename}")
        if kind == "archive":
            counts["archives"] += 1
            counts["archive_members"] += _verify_archive(path, expected)
        else:
            counts["sboms"] += 1
            counts["components"] += _verify_sbom(path)

    checksum_path = directory / "SHA256SUMS.txt"
    if not checksum_path.is_file():
        raise VerificationError("SHA256SUMS.txt is missing")
    checksums = _read_checksums(checksum_path)
    if set(checksums) != set(assets):
        missing = sorted(set(assets) - set(checksums))
        unexpected = sorted(set(checksums) - set(assets))
        raise VerificationError(
            f"checksum manifest mismatch: missing={missing}, unexpected={unexpected}"
        )
    for filename, expected in checksums.items():
        actual = _sha256(directory / filename)
        if actual != expected:
            raise VerificationError(f"SHA-256 mismatch for {filename}")

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a BiliFlow release bundle")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args(argv)

    try:
        counts = verify_release_bundle(args.directory, args.release_id)
    except (OSError, VerificationError) as exc:
        print(f"release bundle verification failed: {exc}", file=sys.stderr)
        return 1

    print(
        "release bundle verified: "
        f"{counts['archives']} archives/{counts['archive_members']} files, "
        f"{counts['sboms']} SBOMs/{counts['components']} components"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
