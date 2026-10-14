import gc
import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import replace

import pytest

from bilibili_downloader.core.update_protocol import (
    BuildInfo,
    RuntimeLease,
    UpdateError,
    atomic_json,
    build_payload,
    sha256,
)
from scripts import update_helper as helper
from tests.test_updater import installed_root, zip_bytes


class Child:
    def __init__(self, exited=False):
        self.exited = exited
        self.terminated = False

    def poll(self):
        return 1 if self.exited else None

    def terminate(self):
        self.terminated = True
        self.exited = True

    def kill(self):
        self.terminate()

    def wait(self, **_kwargs):
        self.exited = True
        return 1


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    target, current = installed_root(tmp_path)
    new = replace(current, version="0.9.0")
    data = tmp_path / "data"
    directory = data / "updates" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    archive = data / "updates" / "package.zip"
    archive.write_bytes(zip_bytes(new))
    stage = (
        target.parent / f".{target.name}.update-{uuid.uuid4().hex}" / new.archive_root
    )
    (stage / new.resource_dir).mkdir(parents=True)
    (stage / new.executable).write_bytes(b"new executable")
    (stage / new.helper).write_bytes(b"helper")
    atomic_json(stage / "biliflow-build.json", build_payload(new))
    (data / "config.json").write_text('{"original": true}')
    with closing(sqlite3.connect(data / "tasks.sqlite3")) as db, db:
        db.execute("CREATE TABLE example (value TEXT)")
        db.execute("INSERT INTO example VALUES ('original')")
    path = directory / "transaction.json"
    value = {
        "protocol": 1,
        "token": uuid.uuid4().hex,
        "parent_pid": 99999999,
        "target": str(target),
        "staged": str(stage),
        "archive": str(archive),
        "checksum": sha256(archive),
        "data_dir": str(data),
        "build": build_payload(new),
    }
    atomic_json(path, value)
    monkeypatch.setattr(helper, "process_alive", lambda _pid: False)
    return path, value


def test_install_commits_only_after_matching_startup_receipt(transaction, monkeypatch):
    path, value = transaction
    launched = []

    def launch(target, build, directory, *, probation, token=""):
        launched.append(probation)
        assert (target / build.executable).read_bytes() == b"new executable"
        assert (directory / "snapshot/config.json").read_text() == '{"original": true}'
        atomic_json(
            directory / "startup-ready.json", {"token": token, "version": build.version}
        )
        return Child()

    monkeypatch.setattr(helper, "_launch", launch)
    assert helper.run_transaction(path) == 0
    assert launched == [True]
    assert (
        json.loads((path.parent / "commit.json").read_text())["token"] == value["token"]
    )
    assert not list(path.parent.parent.parent.parent.glob("*.backup-*"))
    assert (path.parent / "snapshot/tasks.sqlite3").is_file()


@pytest.mark.parametrize("exited", [True, False])
def test_startup_failure_or_timeout_restores_program_and_databases(
    transaction, monkeypatch, exited
):
    path, value = transaction
    data = path.parent.parent.parent
    launched = []
    child = Child(exited)

    def launch(target, build, directory, *, probation, token=""):
        launched.append(probation)
        if probation:
            (data / "config.json").write_text("changed")
            with closing(sqlite3.connect(data / "tasks.sqlite3")) as db, db:
                db.execute("UPDATE example SET value='changed'")
            (data / "live.sqlite3").write_bytes(b"new database")
            atomic_json(
                directory / "startup-ready.json",
                {"token": "wrong", "version": build.version},
            )
            return child
        assert (target / build.executable).read_bytes() == b"old executable"
        return Child()

    monkeypatch.setattr(helper, "_launch", launch)
    assert helper.run_transaction(path, health_timeout=0) == 1
    assert launched == [True, False]
    assert (data / "config.json").read_text() == '{"original": true}'
    with closing(sqlite3.connect(data / "tasks.sqlite3")) as db:
        assert db.execute("SELECT value FROM example").fetchone()[0] == "original"
    assert not (data / "live.sqlite3").exists()
    assert not (path.parent / "commit.json").exists()
    assert json.loads((path.parent / "status.json").read_text("utf-8"))["state"] == "failed"


def test_snapshot_can_be_restored_without_waiting_for_garbage_collection(transaction):
    path, _value = transaction
    data = path.parent.parent.parent
    snapshot = path.parent / "snapshot"
    enabled = gc.isenabled()
    gc.disable()
    try:
        helper._snapshot(data, snapshot)
        # Windows refuses to delete this file while an SQLite handle is open.
        # Restore must not depend on when cyclic garbage collection runs.
        (data / "tasks.sqlite3").unlink()
        helper._restore_snapshot(data, snapshot)
        (snapshot / "tasks.sqlite3").unlink()
        with closing(sqlite3.connect(data / "tasks.sqlite3")) as db:
            assert db.execute("SELECT value FROM example").fetchone()[0] == "original"
    finally:
        if enabled:
            gc.enable()


def test_running_other_instance_prevents_replacement(transaction, monkeypatch):
    path, value = transaction
    lease = RuntimeLease(path.parent.parent.parent / "runtime.lock")
    assert lease.acquire()
    monkeypatch.setattr(helper, "_launch", lambda *_args, **_kwargs: Child())
    try:
        assert helper.run_transaction(path) == 1
        build = BuildInfo.parse(value["build"])
        assert (
            helper.Path(value["target"]) / build.executable
        ).read_bytes() == b"old executable"
        assert not (path.parent / "snapshot").exists()
    finally:
        lease.release()


def test_failed_directory_swap_restores_old_program(transaction, monkeypatch):
    path, value = transaction
    original = helper.Path.rename

    def rename(source, destination):
        if str(source) == value["staged"]:
            raise PermissionError("file occupied")
        return original(source, destination)

    monkeypatch.setattr(helper.Path, "rename", rename)
    monkeypatch.setattr(helper, "_launch", lambda *_args, **_kwargs: Child())
    assert helper.run_transaction(path) == 1
    assert (
        helper.Path(value["target"]) / "BilibiliDownloader.exe"
    ).read_bytes() == b"old executable"


def test_legacy_gui_live_lock_prevents_replacement(transaction, monkeypatch):
    path, value = transaction
    (path.parent.parent.parent / "live.lock").write_text("legacy GUI lock")
    monkeypatch.setattr(helper, "_launch", lambda *_args, **_kwargs: Child())
    assert helper.run_transaction(path) == 1
    assert not (path.parent / "snapshot").exists()
    assert (
        helper.Path(value["target"]) / "BilibiliDownloader.exe"
    ).read_bytes() == b"old executable"


def test_parent_shutdown_timeout_does_not_touch_installation(transaction, monkeypatch):
    path, value = transaction
    monkeypatch.setattr(helper, "process_alive", lambda _pid: True)
    assert helper.run_transaction(path, parent_timeout=0) == 1
    assert not (path.parent / "snapshot").exists()
    assert (
        helper.Path(value["target"]) / "BilibiliDownloader.exe"
    ).read_bytes() == b"old executable"


def test_invalid_transaction_target_or_package_rejected(transaction):
    path, value = transaction
    atomic_json(path, {**value, "staged": str(path.parent / "unsafe")})
    with pytest.raises(UpdateError, match="路径"):
        helper.read_transaction(path)
    atomic_json(path, value)
    helper.Path(value["archive"]).write_bytes(b"tampered")
    with pytest.raises(UpdateError, match="校验"):
        helper.read_transaction(path)


def test_helper_rechecks_user_data_before_parent_exits(transaction):
    path, value = transaction
    atomic_json(
        path.parent.parent.parent / "config.json", {"output_dir": value["target"]}
    )
    with pytest.raises(UpdateError, match="程序目录内"):
        helper.run_transaction(path)
    assert not (path.parent / "helper-ready.json").exists()


def test_export_inside_application_is_protected(transaction):
    path, value = transaction
    output = helper.Path(value["target"]) / "export.mp4"
    output.write_bytes(b"exported media")
    atomic_json(path, {**value, "protected_paths": [str(output)]})
    with pytest.raises(UpdateError, match="程序目录内"):
        helper.run_transaction(path)
    assert output.read_bytes() == b"exported media"
