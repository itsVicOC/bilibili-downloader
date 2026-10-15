"""Standalone, standard-library-only installer. Never imports the GUI."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

from bilibili_downloader.core.update_protocol import (
    DATA_FILES,
    BuildInfo,
    RuntimeLease,
    UpdateError,
    atomic_json,
    ensure_install_data_outside,
    sha256,
    subprocess_environment,
    validate_archive,
)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return (
                kernel.GetLastError() == 5
            )  # Access denied must not be treated as exit.
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_transaction(path: Path) -> dict:
    path = path.resolve()
    value = json.loads(path.read_text("utf-8"))
    if value.get("protocol") != 1 or not re.fullmatch(
        r"[a-f0-9]{32}", value.get("token", "")
    ):
        raise UpdateError("更新事务协议或凭据无效")
    if type(value.get("parent_pid")) is not int or value["parent_pid"] <= 0:
        raise UpdateError("更新事务父进程无效")
    data = Path(value["data_dir"]).resolve()
    target = Path(value["target"]).resolve()
    staged = Path(value["staged"]).resolve()
    archive = Path(value["archive"]).resolve()
    build = BuildInfo.parse(value["build"])
    if (
        path.name != "transaction.json"
        or path.parent.parent != data / "updates"
        or not re.fullmatch(r"[a-f0-9]{32}", path.parent.name)
        or archive.parent != data / "updates"
        or staged.parent.parent != target.parent
        or not staged.parent.name.startswith(f".{target.name}.update-")
        or staged.name != build.archive_root
        or data == target
        or target in data.parents
        or data in target.parents
        or not re.fullmatch(r"[a-f0-9]{64}", value.get("checksum", ""))
    ):
        raise UpdateError("更新事务路径无效")
    current = build.read_from(target)
    extra_paths = value.get("protected_paths", [])
    if not isinstance(extra_paths, list) or not all(
        isinstance(path, str) for path in extra_paths
    ):
        raise UpdateError("更新事务中的数据路径无效")
    ensure_install_data_outside(target, data, current, extra_paths=extra_paths)
    if (current.platform, current.architecture, current.variant) != (
        build.platform,
        build.architecture,
        build.variant,
    ):
        raise UpdateError("当前程序与更新包类型不匹配")
    if sha256(archive) != value["checksum"]:
        raise UpdateError("安装前更新包校验失败")
    validate_archive(archive, build)
    if build.read_from(staged) != build or not (staged / build.executable).is_file():
        raise UpdateError("暂存更新程序无效")
    return {
        **value,
        "data": data,
        "target_path": target,
        "staged_path": staged,
        "info": build,
    }


def _status(directory, state, message="", **extra):
    atomic_json(
        directory / "status.json",
        {"state": state, "message": message, "helper_pid": os.getpid(), **extra},
    )


def _wait_for_parent(pid, directory, timeout):
    deadline = time.monotonic() + timeout
    while process_alive(pid):
        if (directory / "cancel.json").exists():
            raise UpdateError("安装已取消")
        if time.monotonic() > deadline:
            raise UpdateError("主程序未能及时退出，更新已中止")
        time.sleep(0.1)


def _snapshot(data, directory):
    directory.mkdir(mode=0o700)
    existed = {}
    for name in DATA_FILES:
        source = data / name
        existed[name] = source.is_file()
        if not existed[name]:
            continue
        if name.endswith(".sqlite3"):
            with closing(
                sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            ) as original:
                with closing(sqlite3.connect(directory / name)) as backup:
                    original.backup(backup)
        else:
            shutil.copy2(source, directory / name)
        if os.name != "nt":
            (directory / name).chmod(0o600)
    atomic_json(directory / "files.json", existed)


def _restore_snapshot(data, directory):
    existed = json.loads((directory / "files.json").read_text("utf-8"))
    for name in DATA_FILES:
        destination = data / name
        if name.endswith(".sqlite3"):
            for suffix in ("-wal", "-shm"):
                Path(str(destination) + suffix).unlink(missing_ok=True)
        if existed[name]:
            shutil.copy2(directory / name, destination)
        else:
            destination.unlink(missing_ok=True)


def _launch(target, build, directory, *, probation, token=""):
    environment = subprocess_environment()
    if probation:
        environment["BILIFLOW_UPDATE_TRANSACTION"] = str(directory / "transaction.json")
        environment["BILIFLOW_UPDATE_TOKEN"] = token
    else:
        environment["BILIFLOW_UPDATE_FAILURE"] = str(directory / "status.json")
    kwargs = (
        {"start_new_session": True}
        if os.name != "nt"
        else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    )
    if os.name == "nt" and getattr(sys, "frozen", False):
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        return subprocess.Popen(
            [str(target / build.executable)],
            cwd=target.parent,
            env=environment,
            **kwargs,
        )
    finally:
        if os.name == "nt" and getattr(sys, "frozen", False):
            ctypes.windll.kernel32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))


def _stop_child(child):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)


def run_transaction(path: Path, *, parent_timeout=120, health_timeout=60) -> int:
    directory = path.resolve().parent
    value = read_transaction(path)
    target, staged, build, data = (
        value["target_path"],
        value["staged_path"],
        value["info"],
        value["data"],
    )
    backup = target.with_name(f".{target.name}.backup-{directory.name}")
    failed = target.with_name(f".{target.name}.failed-{directory.name}")
    old_build = build.read_from(target)
    child = None
    replaced = False
    snapshot = directory / "snapshot"
    lease = RuntimeLease(data / "runtime.lock", exclusive=True)
    mutex = RuntimeLease(data / "updates/install.lock", exclusive=True)
    atomic_json(directory / "helper-ready.json", {"token": value["token"]})
    try:
        _wait_for_parent(value["parent_pid"], directory, parent_timeout)
        if (directory / "cancel.json").exists():
            raise UpdateError("安装已取消")
        if not mutex.acquire() or not lease.acquire():
            raise UpdateError("其他 BiliFlow 实例尚未退出，更新已中止")
        # Pre-updater GUI versions only own this Qt lock, not runtime.lock.
        # Our parent releases it during graceful shutdown before exiting.
        if (data / "live.lock").exists():
            raise UpdateError("其他实例或未释放的直播锁仍在占用数据，请关闭所有 BiliFlow 实例后重试")
        _snapshot(data, snapshot)
        _status(directory, "installing", backup=str(backup))
        if backup.exists() or failed.exists():
            raise UpdateError("此更新事务已执行，请重新检查更新")
        target.rename(backup)
        try:
            staged.rename(target)
            replaced = True
        except OSError:
            backup.rename(target)
            raise
        child = _launch(target, build, directory, probation=True, token=value["token"])
        deadline = time.monotonic() + health_timeout
        while True:
            if child.poll() is not None:
                raise UpdateError("新版程序启动失败，已恢复旧版本")
            try:
                ready = json.loads(
                    (directory / "startup-ready.json").read_text("utf-8")
                )
            except (OSError, ValueError):
                ready = {}
            if (
                ready.get("token") == value["token"]
                and ready.get("version") == build.version
            ):
                break
            if time.monotonic() > deadline:
                raise UpdateError("新版程序启动确认超时，已恢复旧版本")
            time.sleep(0.1)
        _status(directory, "committed")
        atomic_json(directory / "commit.json", {"token": value["token"]})
        lease.release()
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(staged.parent, ignore_errors=True)
        try:
            (data / "updates/prepared.json").unlink(missing_ok=True)
        except OSError:
            pass  # Cache cleanup must never roll back an already committed update.
        return 0
    except Exception as exc:
        message = str(exc)
        try:
            _stop_child(child)
            if replaced:
                target.rename(failed)
                backup.rename(target)
                _restore_snapshot(data, snapshot)
            _status(directory, "failed", message)
        except Exception as rollback_error:
            _status(
                directory,
                "rollback_failed",
                f"{message}；恢复失败：{rollback_error}；旧程序备份：{backup}；数据备份：{snapshot}",
                backup=str(backup),
            )
            return 2
        finally:
            lease.release()
        if (
            not process_alive(value["parent_pid"])
            and not (directory / "cancel.json").exists()
        ):
            try:
                _launch(target, old_build, directory, probation=False)
            except OSError as restart_error:
                _status(
                    directory, "failed", f"{message}；请手动打开旧版本：{restart_error}"
                )
        shutil.rmtree(failed, ignore_errors=True)
        return 1
    finally:
        lease.release()
        mutex.release()


def main():
    parser = argparse.ArgumentParser(description="BiliFlow update installer")
    parser.add_argument("--transaction", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run_transaction(args.transaction)
    except Exception as exc:
        # Validation failures occur before the parent receives helper-ready.
        _status(args.transaction.resolve().parent, "failed", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
