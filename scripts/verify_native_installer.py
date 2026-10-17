"""Verify native installer payloads against ZIP, then attest the exact assets.

Windows validation installs/uninstalls in a disposable path, and refuses to run
if the current account already has an installer-managed BiliFlow installation.
No GUI, credentials, configuration or network services are started.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from bilibili_downloader.core.installation import INSTALL_ID, write_payload_manifest
from bilibili_downloader.core.update_protocol import (
    BuildInfo,
    atomic_json,
    build_payload,
    sha256,
    validate_archive,
)
from scripts.package_installers import installer_filename


def tree_manifest(root: Path):
    result = {}
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = {"link": os.readlink(path)}
        elif path.is_file():
            result[name] = {"sha256": sha256(path)}
    return result


def zip_manifest(archive: Path, build: BuildInfo):
    validate_archive(archive, build)
    result = {}
    prefix = build.archive_root + "/"
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if not entry.filename.startswith(prefix) or entry.is_dir():
                continue
            name = entry.filename[len(prefix):]
            if stat.S_ISLNK(entry.external_attr >> 16):
                result[name] = {"link": source.read(entry).decode("utf-8")}
            else:
                import hashlib
                with source.open(entry) as stream:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                result[name] = {"sha256": digest.hexdigest()}
    return result


def verify_payload(root: Path, archive: Path, system: str):
    build = BuildInfo("", system, "", "full").read_from(root)
    if build.platform != system or build.variant != "full":
        raise ValueError("Incorrect installed build")
    expected, actual = zip_manifest(archive, build), tree_manifest(root)
    if expected != actual:
        differences = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
        raise ValueError(f"Installed payload differs from ZIP: {differences[:10]}")
    subprocess.run([str(root / build.executable), "--help"], check=True, timeout=60)
    return build, len(actual)


def verify_macos(installer: Path, archive: Path, temporary: Path):
    subprocess.run(["/usr/bin/hdiutil", "verify", str(installer)], check=True)
    mount = temporary / "mount"
    subprocess.run([
        "/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(installer),
    ], check=True)
    try:
        if not (mount / "Applications").is_symlink() or os.readlink(mount / "Applications") != "/Applications":
            raise ValueError("DMG has no Applications install target")
        if not (mount / "安装说明.txt").is_file():
            raise ValueError("DMG has no installation instructions")
        root = temporary / "installed" / "BilibiliDownloader.app"
        subprocess.run(["/usr/bin/ditto", str(mount / root.name), str(root)], check=True)
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(root)], check=True)
        return verify_payload(root, archive, "macOS"), ["mount", "applications-link", "copy", "signature", "payload", "cli"]
    finally:
        subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=True)


def verify_windows(installer: Path, archive: Path, temporary: Path):
    import winreg

    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{{{INSTALL_ID}}}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise ValueError("Use a clean Windows account: BiliFlow is already installed")
    except FileNotFoundError:
        pass
    parent = temporary / "中文 installation with spaces"
    root = parent / "BilibiliDownloader"
    command = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/NOICONS", "/TASKS=", f"/DIR={parent}"]
    uninstall = parent / "uninst/unins000.exe"
    try:
        subprocess.run(command, check=True, timeout=300)
        result = verify_payload(root, archive, "Windows")
        subprocess.run(command, check=True, timeout=300)
        verify_payload(root, archive, "Windows")
        # AppMutex protects both application processes and standalone updaters.
        blocker = subprocess.Popen([
            sys.executable, "-c",
            "from bilibili_downloader.core.installation import WindowsInstallationGuard; "
            "import time; guard=WindowsInstallationGuard(); guard.acquire(); "
            "print('ready', flush=True); time.sleep(120)",
        ], stdout=subprocess.PIPE, text=True)
        try:
            if blocker.stdout.readline().strip() != "ready":
                raise ValueError("Failed to acquire runtime guard")
            blocked = subprocess.run(command, timeout=60)
            if blocked.returncode == 0:
                raise ValueError("Installer overwrote an active application")
        finally:
            blocker.terminate()
            blocker.wait(timeout=10)
        # Exercise uninstall after the same whole-directory swap used by ZIP
        # updates; a new program file must be removed, user media must survive.
        replacement = parent / "replacement"
        shutil.copytree(root, replacement)
        introduced = replacement / "introduced-by-update.bin"
        introduced.write_bytes(b"updated program file")
        write_payload_manifest(replacement)
        media = replacement / "user-saved-video.mp4"
        media.write_bytes(b"user data")
        shutil.rmtree(root)
        replacement.rename(root)
        subprocess.run([str(uninstall), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=120)
        if (root / introduced.name).exists() or (root / "BilibiliDownloader.exe").exists():
            raise ValueError("Updated program files survived uninstall")
        if (root / media.name).read_bytes() != b"user data":
            raise ValueError("Uninstall removed user media")
        return result, ["install", "payload", "cli", "reinstall", "running-guard", "updated-uninstall", "preserve-media"]
    finally:
        if uninstall.exists():
            subprocess.run([str(uninstall), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=120, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--platform", choices=("macOS", "Windows"), required=True)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    installer = directory / installer_filename(args.platform, args.release_id)
    archive = directory / f"BilibiliDownloader-{args.platform}-full-{args.release_id}.zip"
    with tempfile.TemporaryDirectory(prefix="biliflow-native-check-") as temporary:
        verify = verify_macos if args.platform == "macOS" else verify_windows
        (build, count), checks = verify(installer, archive, Path(temporary))
    report = {
        "protocol": 1, "build": build_payload(build), "files": count,
        "installer": installer.name, "installer_sha256": sha256(installer),
        "archive": archive.name, "archive_sha256": sha256(archive), "checks": checks,
    }
    atomic_json(installer.with_suffix(".verification.json"), report)


if __name__ == "__main__":
    main()
