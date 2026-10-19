"""Exercise the frozen installer with disposable frozen application fixtures."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from bilibili_downloader.core.update_protocol import (
    BUILD_INFO_FILENAME,
    BuildInfo,
    atomic_json,
    build_payload,
    normalize_arch,
    sha256,
)
from bilibili_downloader.core.updater import (
    PreparedUpdate,
    UpdateRelease,
    UpdateService,
    clean_subprocess_environment,
)
from scripts.update_helper import process_alive

APPLICATION = """
import json, os, sqlite3, time
from contextlib import closing
from pathlib import Path
from bilibili_downloader.core.update_protocol import RuntimeLease, atomic_json
markers = Path(os.environ["BILIFLOW_SMOKE_MARKERS"])
data = Path(os.environ["BILIFLOW_SMOKE_DATA"])
transaction = os.environ.get("BILIFLOW_UPDATE_TRANSACTION")
lease = RuntimeLease(data / "runtime.lock")
if transaction:
    path = Path(transaction)
    value = json.loads(path.read_text("utf-8"))
    if os.environ.get("BILIFLOW_SMOKE_FAIL"):
        (data / "config.json").write_text("failed migration")
        (data / "backgrounds" / "original.png").unlink()
        (data / "backgrounds" / "new.png").write_bytes(b"failed migration image")
        with closing(sqlite3.connect(data / "tasks.sqlite3")) as db, db:
            db.execute("UPDATE fixture SET value='failed migration'")
        raise SystemExit(3)
    atomic_json(path.parent / "startup-ready.json", {"token": value["token"], "version": value["build"]["version"]})
    while not (path.parent / "commit.json").is_file() or not lease.acquire():
        time.sleep(0.05)
    atomic_json(markers / "new-ready.json", {"pid": os.getpid(), "bootloader_pid": os.getppid()})
else:
    if not lease.acquire():
        raise SystemExit(4)
    name = "rollback-ready.json" if os.environ.get("BILIFLOW_UPDATE_FAILURE") else "old-ready.json"
    atomic_json(markers / name, {"pid": os.getpid(), "bootloader_pid": os.getppid()})
sentinel = "old-quit" if os.environ.get("BILIFLOW_SMOKE_OLD") else "new-quit"
while not (markers / sentinel).exists():
    time.sleep(0.05)
lease.release()
"""


def wait_until(predicate, timeout=90):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise RuntimeError("Frozen updater smoke test timed out")
        time.sleep(0.1)


def _wait_for_application_exit(marker):
    receipt = json.loads(marker.read_text("utf-8"))
    # One-file applications keep their executable open in the bootloader parent
    # while it removes extracted DLLs, even after the Python child has exited.
    pids = (receipt["pid"], receipt["bootloader_pid"])
    wait_until(lambda: all(not process_alive(pid) for pid in pids), timeout=30)


def _application(root, build, executable, helper):
    resources = root / build.resource_dir
    resources.mkdir(parents=True)
    (root / build.executable).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, root / build.executable)
    shutil.copy2(helper, resources / build.helper)
    atomic_json(resources / BUILD_INFO_FILENAME, build_payload(build))
    if build.platform == "macOS":
        os.symlink(BUILD_INFO_FILENAME, resources / "metadata-alias")


def exercise(directory, executable, helper, system, variant, fail):
    data = directory / "user data with spaces"
    markers = directory / "markers"
    data.mkdir(parents=True)
    markers.mkdir()
    (data / "config.json").write_text('{"original": true}')
    (data / "backgrounds").mkdir()
    (data / "backgrounds" / "original.png").write_bytes(b"original image")
    with closing(sqlite3.connect(data / "tasks.sqlite3")) as db, db:
        db.execute("CREATE TABLE fixture (value TEXT)")
        db.execute("INSERT INTO fixture VALUES ('original')")
    media = directory / "saved-media.mp4"
    media.write_bytes(b"preserve media")
    build = BuildInfo(
        "0.8.0", system, normalize_arch(__import__("platform").machine()), variant
    )
    new_build = replace(build, version="0.9.0")
    target = directory / "install location with spaces" / build.archive_root
    _application(target, build, executable, helper)
    source = directory / "new" / build.archive_root
    _application(source, new_build, executable, helper)
    cache = data / "updates"
    cache.mkdir()
    archive = cache / "smoke-package.zip"
    if system == "macOS":
        subprocess.run(
            [
                "/usr/bin/ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(source),
                str(archive),
            ],
            check=True,
        )
    else:
        with zipfile.ZipFile(archive, "w") as output:
            for path in source.rglob("*"):
                output.write(path, path.relative_to(source.parent))
    service = UpdateService(
        data, current_version=build.version, installation=(target, build)
    )
    prepared = service.stage(
        PreparedUpdate(
            UpdateRelease("0.9.0", "v0.9.0", "", "", ()),
            new_build,
            archive,
            sha256(archive),
            target,
        )
    )
    transaction_dir = cache / uuid.uuid4().hex
    transaction_dir.mkdir()
    updater = transaction_dir / build.helper
    shutil.copy2(helper, updater)
    environment = clean_subprocess_environment()
    environment.update(
        BILIFLOW_SMOKE_MARKERS=str(markers), BILIFLOW_SMOKE_DATA=str(data)
    )
    if fail:
        environment["BILIFLOW_SMOKE_FAIL"] = "1"
    original = subprocess.Popen(
        [str(target / build.executable)], env={**environment, "BILIFLOW_SMOKE_OLD": "1"}
    )
    installer = None
    try:
        wait_until(
            lambda: (markers / "old-ready.json").exists() or original.poll() is not None
        )
        if not (markers / "old-ready.json").exists():
            raise RuntimeError(
                f"Fixture application failed to start: {original.returncode}"
            )
        transaction = transaction_dir / "transaction.json"
        atomic_json(
            transaction,
            {
                "protocol": 1,
                "token": uuid.uuid4().hex,
                "parent_pid": original.pid,
                "target": str(target),
                "staged": str(prepared.staged),
                "archive": str(archive),
                "checksum": prepared.checksum,
                "data_dir": str(data),
                "build": build_payload(new_build),
            },
        )
        installer = subprocess.Popen(
            [str(updater), "--transaction", str(transaction)],
            env=environment,
            cwd=transaction_dir,
        )
        wait_until(
            lambda: (
                (transaction_dir / "helper-ready.json").exists()
                or installer.poll() is not None
            )
        )
        if installer.poll() is not None:
            raise RuntimeError((transaction_dir / "status.json").read_text("utf-8"))
        (markers / "old-quit").touch()
        original.wait(timeout=30)
        installer.wait(timeout=90)
        status = json.loads((transaction_dir / "status.json").read_text("utf-8"))
        expected = "failed" if fail else "committed"
        if status["state"] != expected:
            raise RuntimeError(status)
        marker = markers / ("rollback-ready.json" if fail else "new-ready.json")
        wait_until(marker.exists)
        actual = new_build.read_from(target)
        assert actual == (build if fail else new_build)
        assert (data / "config.json").read_text() == '{"original": true}'
        assert (data / "backgrounds" / "original.png").read_bytes() == b"original image"
        assert not (data / "backgrounds" / "new.png").exists()
        with closing(sqlite3.connect(data / "tasks.sqlite3")) as db:
            assert db.execute("SELECT value FROM fixture").fetchone()[0] == "original"
        assert media.read_bytes() == b"preserve media"
        if system == "macOS":
            assert (target / build.resource_dir / "metadata-alias").is_symlink()
        print(
            f"{system} {variant}: {'startup failure rollback' if fail else 'install and restart'} passed",
            flush=True,
        )
    finally:
        (markers / "old-quit").touch()
        (markers / "new-quit").touch()
        if original.poll() is None:
            original.terminate()
            original.wait(timeout=10)
        if installer and installer.poll() is None:
            installer.terminate()
            installer.wait(timeout=10)
        for name in ("new-ready.json", "rollback-ready.json"):
            marker = markers / name
            if marker.exists():
                _wait_for_application_exit(marker)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=("macOS", "Windows"))
    args = parser.parse_args()
    helper = args.helper.resolve()
    with tempfile.TemporaryDirectory(prefix="biliflow-updater-smoke-") as temporary:
        work = Path(temporary)
        entry = work / "fixture.py"
        entry.write_text(APPLICATION)
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--log-level",
            "WARN",
            "--onefile",
            "--console",
            "--name",
            "smoke-application",
            "--paths",
            str(Path(__file__).resolve().parents[1]),
            "--distpath",
            str(work / "dist"),
            "--workpath",
            str(work / "build"),
            "--specpath",
            str(work),
            str(entry),
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        executable = (
            work
            / "dist"
            / (
                "smoke-application.exe"
                if args.platform == "Windows"
                else "smoke-application"
            )
        )
        for variant in ("lite", "full"):
            for fail in (False, True):
                exercise(
                    work / f"{variant}-{'rollback' if fail else 'success'}",
                    executable,
                    helper,
                    args.platform,
                    variant,
                    fail,
                )


if __name__ == "__main__":
    main()
