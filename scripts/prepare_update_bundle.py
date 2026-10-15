"""Embed the installer and a verifiable platform/variant descriptor."""

import argparse
import platform
import shutil
from pathlib import Path

from packaging.version import Version

from bilibili_downloader import __version__
from bilibili_downloader.core.update_protocol import (
    BUILD_INFO_FILENAME,
    BuildInfo,
    atomic_json,
    build_payload,
    normalize_arch,
)


def prepare_update_bundle(
    root: Path, helper: Path, system: str, variant: str
) -> BuildInfo:
    info = BuildInfo(
        str(Version(__version__)), system, normalize_arch(platform.machine()), variant
    )
    info = BuildInfo.parse(build_payload(info))
    if not (root / info.executable).is_file() or not helper.is_file():
        raise ValueError("Application or standalone updater is missing")
    resources = root / info.resource_dir
    resources.mkdir(parents=True, exist_ok=True)
    destination = resources / info.helper
    shutil.copy2(helper, destination)
    destination.chmod(0o755)
    atomic_json(resources / BUILD_INFO_FILENAME, build_payload(info))
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--helper", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=("macOS", "Windows"))
    parser.add_argument("--variant", required=True, choices=("full", "lite"))
    args = parser.parse_args()
    prepare_update_bundle(args.root, args.helper, args.platform, args.variant)


if __name__ == "__main__":
    main()
