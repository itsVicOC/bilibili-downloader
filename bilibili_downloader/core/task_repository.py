"""SQLite-backed durable download task storage."""

import json
import os
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bilibili_downloader.core.models import DownloadItem, TaskStatus

TASK_SCHEMA_VERSION = 2


class TaskDatabaseVersionError(RuntimeError):
    """Raised when the task database schema cannot be opened safely."""


@dataclass(frozen=True)
class TaskRecord:
    id: int
    item: DownloadItem
    fingerprint: str
    status: TaskStatus
    progress: float
    status_text: str
    error: Optional[str]
    output_path: Optional[str]
    speed_bytes_per_second: float
    eta_seconds: Optional[int]
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    warnings: list[str]


class TaskRepository:
    """Persist task snapshots and lifecycle transitions across app restarts."""

    _MUTABLE_COLUMNS = {
        "status",
        "progress",
        "status_text",
        "error",
        "output_path",
        "speed_bytes_per_second",
        "eta_seconds",
        "completed_at",
        "payload_json",
        "fingerprint",
        "warnings",
    }

    def __init__(self, database_path: Path):
        self._database_path = Path(database_path)
        self._lock = threading.RLock()
        self.recovered_database_path: Optional[Path] = None
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._database_path.parent.chmod(0o700)
        except OSError:
            pass
        try:
            self._assert_integrity()
        except sqlite3.DatabaseError:
            self.recovered_database_path = self._quarantine_corrupt_database()
        self._initialize()
        try:
            self._database_path.chmod(0o600)
        except OSError:
            pass

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._lock:
            with self._connect() as connection:
                current_version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                has_tasks_table = _table_exists(connection, "tasks")

            if current_version > TASK_SCHEMA_VERSION:
                raise TaskDatabaseVersionError(
                    "任务数据库来自更新版本的 BiliFlow，当前版本不会修改该文件"
                )
            if current_version < TASK_SCHEMA_VERSION and (
                current_version > 0 or has_tasks_table
            ):
                self._backup_before_migration()

            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    while current_version < TASK_SCHEMA_VERSION:
                        if current_version == 0:
                            _migrate_v0_to_v1(connection)
                        elif current_version == 1:
                            _migrate_v1_to_v2(connection)
                        current_version += 1
                        connection.execute(
                            f"PRAGMA user_version = {current_version}"
                        )
                    _validate_schema(connection)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise

    def _assert_integrity(self) -> None:
        if not self._database_path.is_file() or self._database_path.stat().st_size == 0:
            return
        with sqlite3.connect(self._database_path, timeout=10.0) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise sqlite3.DatabaseError("task database integrity check failed")

    def _backup_before_migration(self) -> Path:
        backup_path = self._database_path.with_name(
            f"{self._database_path.name}.bak"
        )
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self._database_path.parent,
                prefix=f".{backup_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
            with sqlite3.connect(self._database_path) as source:
                with sqlite3.connect(temporary_path) as destination:
                    source.backup(destination)
            temporary_path.chmod(0o600)
            os.replace(temporary_path, backup_path)
            return backup_path
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _quarantine_corrupt_database(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        recovered_path = self._database_path.with_name(
            f"{self._database_path.stem}.corrupt-{timestamp}"
            f"{self._database_path.suffix}"
        )
        counter = 2
        while recovered_path.exists():
            recovered_path = self._database_path.with_name(
                f"{self._database_path.stem}.corrupt-{timestamp}-{counter}"
                f"{self._database_path.suffix}"
            )
            counter += 1
        try:
            self._database_path.replace(recovered_path)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{self._database_path}{suffix}")
                if sidecar.exists():
                    sidecar.replace(Path(f"{recovered_path}{suffix}"))
        except OSError as exc:
            raise RuntimeError("损坏的任务数据库无法安全隔离") from exc
        return recovered_path

    def add(self, item: DownloadItem, status: TaskStatus = TaskStatus.QUEUED) -> int:
        now = _utc_now()
        snapshot = _sanitized_item(item).model_copy(
            update={"status": status}, deep=True
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks (
                    fingerprint, payload_json, status, progress, status_text,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.fingerprint,
                    snapshot.model_dump_json(),
                    status.value,
                    snapshot.progress,
                    snapshot.status_text,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def get(self, task_id: int) -> Optional[TaskRecord]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _record_from_row(row) if row is not None else None

    def list_tasks(self) -> list[TaskRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at ASC, id ASC"
            ).fetchall()
        records = []
        for row in rows:
            try:
                records.append(_record_from_row(row))
            except (ValueError, TypeError):
                # One damaged task must not prevent recovery of the remaining queue.
                continue
        return records

    def update(self, task_id: int, **changes) -> None:
        invalid = set(changes) - self._MUTABLE_COLUMNS
        if invalid:
            raise ValueError(f"unsupported task fields: {sorted(invalid)}")
        if not changes:
            return
        normalized = {}
        for key, value in changes.items():
            if key == "status" and isinstance(value, TaskStatus):
                value = value.value
            elif key == "warnings":
                key = "warnings_json"
                value = json.dumps(list(value or []), ensure_ascii=False)
            normalized[key] = value
        normalized["updated_at"] = _utc_now()
        assignments = ", ".join(f"{column} = ?" for column in normalized)
        values = [normalized[column] for column in normalized]
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?",  # noqa: S608
                [*values, task_id],
            )

    def update_item(self, task_id: int, item: DownloadItem) -> None:
        item = _sanitized_item(item)
        self.update(
            task_id,
            payload_json=item.model_dump_json(),
            fingerprint=item.fingerprint,
        )

    def recover_interrupted(self) -> int:
        """Convert process-bound states into resumable paused tasks."""
        now = _utc_now()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = ?, status_text = ?, speed_bytes_per_second = 0,
                    eta_seconds = NULL, updated_at = ?
                WHERE status IN (?, ?)
                """,
                (
                    TaskStatus.PAUSED.value,
                    "上次运行中断，可继续下载",
                    now,
                    TaskStatus.DOWNLOADING.value,
                    TaskStatus.MERGING.value,
                ),
            )
            return cursor.rowcount

    def find_duplicate(self, item: DownloadItem) -> Optional[TaskRecord]:
        statuses = (
            TaskStatus.QUEUED.value,
            TaskStatus.DOWNLOADING.value,
            TaskStatus.PAUSED.value,
            TaskStatus.MERGING.value,
            TaskStatus.COMPLETED.value,
        )
        placeholders = ",".join("?" for _ in statuses)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM tasks
                WHERE fingerprint = ? AND status IN ({placeholders})
                ORDER BY id DESC LIMIT 1
                """,  # noqa: S608
                (item.fingerprint, *statuses),
            ).fetchone()
        return _record_from_row(row) if row is not None else None

    def delete(self, task_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def clear_completed(self) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE status = ?", (TaskStatus.COMPLETED.value,)
            )
            return cursor.rowcount

    def known_bvids(self) -> set[str]:
        return {
            record.item.video_info.bvid
            for record in self.list_tasks()
            if record.item.video_info.bvid
            and record.status != TaskStatus.CANCELLED
        }


def _record_from_row(row: sqlite3.Row) -> TaskRecord:
    item = DownloadItem.model_validate_json(row["payload_json"])
    try:
        warnings = json.loads(row["warnings_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        warnings = []
    if not isinstance(warnings, list):
        warnings = []
    return TaskRecord(
        id=int(row["id"]),
        item=item,
        fingerprint=row["fingerprint"],
        status=TaskStatus(row["status"]),
        progress=float(row["progress"]),
        status_text=row["status_text"],
        error=row["error"],
        output_path=row["output_path"],
        speed_bytes_per_second=float(row["speed_bytes_per_second"]),
        eta_seconds=row["eta_seconds"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        warnings=[str(warning) for warning in warnings],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sanitized_item(item: DownloadItem) -> DownloadItem:
    info = item.video_info.model_copy(
        update={
            "video_streams": [],
            "audio_streams": [],
            "subtitle_list": [],
        },
        deep=True,
    )
    return item.model_copy(update={"video_info": info}, deep=True)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _migrate_v0_to_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
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
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_fingerprint ON tasks(fingerprint)"
    )


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    if "warnings_json" not in _table_columns(connection, "tasks"):
        connection.execute(
            "ALTER TABLE tasks ADD COLUMN warnings_json "
            "TEXT NOT NULL DEFAULT '[]'"
        )
    for row in connection.execute("SELECT id, payload_json FROM tasks"):
        try:
            item = DownloadItem.model_validate_json(row["payload_json"])
        except (ValueError, TypeError):
            continue
        connection.execute(
            "UPDATE tasks SET fingerprint = ? WHERE id = ?",
            (item.fingerprint, row["id"]),
        )


def _validate_schema(connection: sqlite3.Connection) -> None:
    required = {
        "id",
        "fingerprint",
        "payload_json",
        "status",
        "progress",
        "status_text",
        "error",
        "output_path",
        "speed_bytes_per_second",
        "eta_seconds",
        "created_at",
        "updated_at",
        "completed_at",
        "warnings_json",
    }
    if not _table_exists(connection, "tasks"):
        raise TaskDatabaseVersionError("任务数据库缺少 tasks 表")
    missing = required - _table_columns(connection, "tasks")
    if missing:
        raise TaskDatabaseVersionError(
            f"任务数据库结构不完整：缺少 {', '.join(sorted(missing))}"
        )
