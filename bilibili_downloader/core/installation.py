"""Standard-library support shared by the app, updater and Windows installer."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path, PurePosixPath

from bilibili_downloader.core.update_protocol import atomic_json, sha256

APP_MUTEX = r"Local\BiliFlow.Runtime"
SETUP_MUTEX = r"Local\BiliFlow.Setup"
INSTALL_ID = "390aa6e8-8afd-4b5e-af65-e10892d29a71"
PAYLOAD_MANIFEST = "biliflow-payload.json"
INSTALL_MARKER = ".biliflow-installed"


class WindowsInstallationGuard:
    """Keep installer/uninstaller away from live application and updater files.

    Several app processes may hold the runtime marker. Setup owns a separate
    marker for its whole lifetime; checking on both sides closes the startup race.
    Handles deliberately live until process exit, including Qt shutdown.
    """

    def __init__(self):
        self.handle = None

    def acquire(self):
        if os.name != "nt":
            return
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.OpenMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]

        def setup_running():
            handle = kernel.OpenMutexW(0x00100000, False, SETUP_MUTEX)
            if handle:
                kernel.CloseHandle(handle)
                return True
            return kernel.GetLastError() == 5

        if setup_running():
            raise OSError("安装或卸载正在进行，请完成后再打开 BiliFlow。")
        self.handle = kernel.CreateMutexW(None, False, APP_MUTEX)
        if not self.handle:
            raise ctypes.WinError()
        if setup_running():
            kernel.CloseHandle(self.handle)
            self.handle = None
            raise OSError("安装或卸载正在进行，请完成后再打开 BiliFlow。")


def write_payload_manifest(root: Path):
    files = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != PAYLOAD_MANIFEST
    }
    atomic_json(root / PAYLOAD_MANIFEST, {"protocol": 1, "files": files})


def remove_managed_files(root: Path):
    """Remove new files introduced by ZIP updates, leaving user files alone.

    Inno handles the original installation log. A separate maintenance helper
    outside the update root handles current, hash-matching payload files only.
    """
    if root.is_symlink() or root.name != "BilibiliDownloader":
        raise ValueError("Invalid application directory")
    root = root.resolve()
    if (root.parent / INSTALL_MARKER).read_text("utf-8").strip() != INSTALL_ID:
        raise ValueError("Not an installer-managed application")
    manifest = root / PAYLOAD_MANIFEST
    payload = json.loads(manifest.read_text("utf-8"))
    if payload.get("protocol") != 1 or not isinstance(payload.get("files"), dict):
        raise ValueError("Invalid payload manifest")
    paths = []
    for name, digest in payload["files"].items():
        part = PurePosixPath(name)
        if not name or "\\" in name or ":" in name or part.is_absolute() or ".." in part.parts:
            raise ValueError("Unsafe payload path")
        path = root.joinpath(*part.parts)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
            raise ValueError("Payload traverses a symbolic link")
        if not path.resolve().is_relative_to(root):
            raise ValueError("Payload escapes application directory")
        if path.is_file() and sha256(path) == digest:
            paths.append(path)
    # Validate all paths before deleting anything.
    for path in paths:
        path.unlink()
    manifest.unlink()
    for directory in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()
            except OSError:
                pass


def macos_installation_notice(executable: Path) -> str:
    """Explain running an application on a read-only disk image/translocation."""
    if "/AppTranslocation/" in str(executable) or str(executable).startswith("/Volumes/"):
        return "请将 BiliFlow 拖入“应用程序”文件夹后再打开，以便正常保存程序更新。"
    return ""
