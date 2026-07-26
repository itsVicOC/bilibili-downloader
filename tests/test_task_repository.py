"""Tests for durable task lifecycle persistence."""

import sqlite3

import pytest

from bilibili_downloader.core.models import (
    DownloadItem,
    StreamInfo,
    SubtitleInfo,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.core.task_repository import (
    TASK_SCHEMA_VERSION,
    TaskDatabaseVersionError,
    TaskRepository,
)


def _item(cid: int = 1) -> DownloadItem:
    return DownloadItem(
        video_info=VideoInfo(bvid="BV1GJ411x7h7", cid=cid, title="Example")
    )


def test_repository_round_trips_task_and_output(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    task_id = repository.add(_item())

    repository.update(
        task_id,
        status=TaskStatus.COMPLETED,
        progress=1.0,
        output_path=str(tmp_path / "Example.mp4"),
        completed_at="2026-07-26T00:00:00+00:00",
    )

    record = repository.get(task_id)
    assert record is not None
    assert record.status == TaskStatus.COMPLETED
    assert record.progress == 1.0
    assert record.item.video_info.title == "Example"


def test_repository_recovers_process_bound_states(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    first = repository.add(_item(1))
    second = repository.add(_item(2))
    repository.update(first, status=TaskStatus.DOWNLOADING)
    repository.update(second, status=TaskStatus.MERGING)

    assert repository.recover_interrupted() == 2
    assert [record.status for record in repository.list_tasks()] == [
        TaskStatus.PAUSED,
        TaskStatus.PAUSED,
    ]


def test_repository_duplicate_detection_ignores_failed_task(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    item = _item()
    task_id = repository.add(item)
    assert repository.find_duplicate(item).id == task_id

    repository.update(task_id, status=TaskStatus.FAILED)

    assert repository.find_duplicate(item) is None


def test_repository_clear_completed_keeps_paused(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    completed = repository.add(_item(1))
    repository.update(completed, status=TaskStatus.COMPLETED)
    repository.add(_item(2), status=TaskStatus.PAUSED)

    assert repository.clear_completed() == 1
    assert [record.status for record in repository.list_tasks()] == [
        TaskStatus.PAUSED
    ]


def test_repository_does_not_persist_expiring_resource_urls(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    item = DownloadItem(
        video_info=VideoInfo(
            bvid="BV1GJ411x7h7",
            cid=1,
            video_streams=[StreamInfo(base_url="https://cdn.example/signed")],
            audio_streams=[StreamInfo(base_url="https://cdn.example/audio")],
            subtitle_list=[SubtitleInfo(url="https://cdn.example/subtitle")],
        )
    )

    task_id = repository.add(item)
    restored = repository.get(task_id).item.video_info

    assert restored.video_streams == []
    assert restored.audio_streams == []
    assert restored.subtitle_list == []


def test_repository_persists_completion_warnings(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.sqlite3")
    task_id = repository.add(_item())

    repository.update(
        task_id,
        status=TaskStatus.COMPLETED,
        warnings=["字幕下载失败", "已回退音频规格"],
    )

    assert repository.get(task_id).warnings == [
        "字幕下载失败",
        "已回退音频规格",
    ]


def test_repository_migrates_v1_with_consistent_backup(tmp_path):
    database_path = tmp_path / "tasks.sqlite3"
    item = _item()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                status_text TEXT NOT NULL DEFAULT '',
                error TEXT,
                output_path TEXT,
                speed_bytes_per_second REAL NOT NULL DEFAULT 0,
                eta_seconds INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO tasks (
                fingerprint, payload_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "legacy-fingerprint",
                item.model_dump_json(),
                TaskStatus.PAUSED.value,
                "2026-07-26T00:00:00+00:00",
                "2026-07-26T00:00:00+00:00",
            ),
        )
        connection.execute("PRAGMA user_version = 1")

    repository = TaskRepository(database_path)

    record = repository.list_tasks()[0]
    assert record.fingerprint == item.fingerprint
    assert record.warnings == []
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    with sqlite3.connect(tmp_path / "tasks.sqlite3.bak") as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        columns = {
            row[1] for row in backup.execute("PRAGMA table_info(tasks)")
        }
        assert "warnings_json" not in columns


def test_repository_rejects_database_from_future_version(tmp_path):
    database_path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"PRAGMA user_version = {TASK_SCHEMA_VERSION + 1}")

    with pytest.raises(TaskDatabaseVersionError, match="更新版本"):
        TaskRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            TASK_SCHEMA_VERSION + 1
        )


def test_repository_quarantines_corrupt_database(tmp_path):
    database_path = tmp_path / "tasks.sqlite3"
    database_path.write_bytes(b"not a sqlite database")

    repository = TaskRepository(database_path)

    assert repository.recovered_database_path is not None
    assert repository.recovered_database_path.read_bytes() == b"not a sqlite database"
    assert repository.list_tasks() == []
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_repository_does_not_quarantine_schema_migration_failure(tmp_path):
    database_path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
        connection.execute("PRAGMA user_version = 1")

    with pytest.raises((sqlite3.DatabaseError, TaskDatabaseVersionError)):
        TaskRepository(database_path)

    assert database_path.exists()
    assert list(tmp_path.glob("tasks.corrupt-*.sqlite3")) == []
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
