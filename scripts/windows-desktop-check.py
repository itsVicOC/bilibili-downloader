import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image, ImageChops, ImageGrab


user32 = ctypes.WinDLL("user32")
WindowCallback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WindowCallback, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
user32.SetProcessDpiAwarenessContext(wintypes.HANDLE(-4))


def locate_window(pid):
    windows = []

    @WindowCallback
    def visit(handle, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(handle):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(handle, title, len(title))
            if title.value.startswith("BiliFlow"):
                windows.append(handle)
        return True

    user32.EnumWindows(visit, 0)
    return windows[0] if windows else None


def capture_window(process):
    for _ in range(15):
        handle = locate_window(process.pid)
        if handle:
            try:
                return ImageGrab.grab(window=handle).convert("RGB")
            except OSError:
                # The hosted desktop can briefly deny a per-window device context.
                rect = wintypes.RECT()
                if user32.GetWindowRect(handle, ctypes.byref(rect)):
                    user32.SetForegroundWindow(handle)
                    time.sleep(0.25)
                    return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).convert("RGB")
        time.sleep(0.2)
    raise RuntimeError("Unable to capture the frozen application window")


def run(executable, theme, mode, screenshot):
    with TemporaryDirectory(prefix="biliflow-frozen-desktop-") as temporary:
        data = Path(temporary)
        (data / "config.json").write_text(json.dumps({
            "output_dir": str(data / "output"),
            "auto_check_updates": False,
            "clipboard_monitor_enabled": False,
            "appearance": {"theme": theme, "mode": mode},
        }), encoding="utf-8")
        env = dict(os.environ, BILIFLOW_DATA_DIR=str(data), QT_QPA_PLATFORM="windows",
                   PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring")
        with screenshot.with_suffix(".log").open("wb") as log:
            process = subprocess.Popen([executable], env=env, stdout=log, stderr=log)
            try:
                for _ in range(160):
                    if process.poll() is not None:
                        raise RuntimeError(f"Frozen GUI exited with {process.returncode}")
                    if locate_window(process.pid):
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Frozen GUI did not open a BiliFlow window")
                time.sleep(0.75)
                frame = capture_window(process)
                assert frame.width > 400 and frame.height > 300 and frame.getbbox()
                frame.save(screenshot)
                print(executable, theme, mode, frame.size)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)


def check_installer_upgrade(baseline, candidate, output):
    with TemporaryDirectory(prefix="biliflow-frozen-upgrade-") as temporary:
        installation = Path(temporary) / "中文 Upgrade With Spaces"
        app = installation / "BilibiliDownloader"
        args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/NOICONS",
                "/TASKS=", f"/DIR={installation}"]
        uninstaller = installation / "uninst" / "unins000.exe"
        try:
            subprocess.run([baseline, *args], check=True, timeout=300)
            user_media = app / "user-media.mp4"
            user_media.write_bytes(b"placeholder user media")
            old = json.loads((app / "biliflow-payload.json").read_text(encoding="utf-8"))["files"]
            subprocess.run([candidate, *args], check=True, timeout=300)
            new = json.loads((app / "biliflow-payload.json").read_text(encoding="utf-8"))["files"]
            assert user_media.read_bytes() == b"placeholder user media"
            run(app / "BilibiliDownloader.exe", "star_trail", "light", output / "installer-upgrade.png")
            stale = [name for name in sorted(old.keys() - new.keys()) if (app / name).is_file()]
            bytes_left = sum((app / name).stat().st_size for name in stale)
            (output / "installer-upgrade.json").write_text(json.dumps({
                "user_media_preserved": True, "legacy_files_remaining": stale,
                "legacy_bytes_remaining": bytes_left,
            }, indent=2), encoding="utf-8")
        finally:
            if uninstaller.is_file():
                subprocess.run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                               check=True, timeout=180)
                for _ in range(80):
                    if not uninstaller.is_file():
                        break
                    time.sleep(0.25)
                assert not uninstaller.is_file(), "uninstaller did not finish cleanup"


themes = [(theme, mode) for theme in ("star_trail", "bilibili_blue") for mode in ("light", "dark")]
output = Path("windows-frozen-desktop")
output.mkdir(exist_ok=True)
for flavor, source in zip(("baseline", "candidate"), sys.argv[1:], strict=True):
    archive, = Path(source).glob("*-full-*.zip")
    with TemporaryDirectory(prefix="biliflow-frozen-extract-") as temporary:
        with ZipFile(archive) as package:
            package.extractall(temporary)
        executable = Path(temporary) / "BilibiliDownloader/BilibiliDownloader.exe"
        for theme, mode in themes:
            run(executable, theme, mode, output / f"{flavor}-{theme}-{mode}.png")

comparison = {}
for theme, mode in themes:
    name = f"{theme}-{mode}"
    with Image.open(output / f"baseline-{name}.png") as baseline, Image.open(output / f"candidate-{name}.png") as candidate:
        assert baseline.size == candidate.size, (name, baseline.size, candidate.size)
        bounds = ImageChops.difference(baseline, candidate).getbbox()
        comparison[name] = {"dimensions": candidate.size, "difference_bounds": bounds}
(output / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
print(comparison)
installers = [next(Path(source).glob("*-full-*-setup.exe")).resolve() for source in sys.argv[1:]]
check_installer_upgrade(*installers, output)
