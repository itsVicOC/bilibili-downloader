"""Durable live subscriptions and recording manifests; never stores play URLs."""

import json
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.live_models import LiveSubscription, RecordingSession
from bilibili_downloader.core.task_repository import TaskDatabaseVersionError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.history_revision = 0
        self.invalid_records = []
        self.recovered_database_path = None
        try:
            with closing(sqlite3.connect(self.path)) as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("integrity")
        except sqlite3.DatabaseError:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            backup = self.path.with_name(f"live.corrupt-{stamp}.sqlite3")
            self.path.replace(backup)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                if sidecar.exists():
                    sidecar.replace(Path(str(backup) + suffix))
            self.recovered_database_path = backup
        with self._db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise TaskDatabaseVersionError(
                    "直播数据库来自更新版本，当前版本不会修改它"
                )
            if version == 0:
                db.executescript("""
                    CREATE TABLE subscriptions (room_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    PRAGMA user_version = 1;
                """)
            for table, fields in (
                ("subscriptions", {"room_id", "payload"}),
                ("sessions", {"id", "payload"}),
            ):
                if not fields.issubset(
                    {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                ):
                    raise TaskDatabaseVersionError("直播数据库结构不完整")
            db.execute("PRAGMA journal_mode=WAL")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def _db(self):
        with self._lock, closing(sqlite3.connect(self.path, timeout=10)) as db:
            with db:
                yield db

    def subscriptions(self) -> list[LiveSubscription]:
        with self._db() as db:
            rows = db.execute(
                "SELECT payload FROM subscriptions ORDER BY rowid"
            ).fetchall()
        return self._decode(rows, LiveSubscription)

    def save_subscription(self, subscription: LiveSubscription):
        with self._db() as db:
            db.execute(
                "INSERT INTO subscriptions VALUES (?, ?) ON CONFLICT(room_id) DO UPDATE SET payload=excluded.payload",
                (subscription.room.room_id, self._serialize(subscription)),
            )

    def remove_subscription(self, room_id: int):
        with self._db() as db:
            db.execute("DELETE FROM subscriptions WHERE room_id=?", (room_id,))

    def sessions(self) -> list[RecordingSession]:
        with self._db() as db:
            rows = db.execute(
                "SELECT payload FROM sessions ORDER BY rowid DESC"
            ).fetchall()
        return self._decode(rows, RecordingSession)

    def _decode(self, rows, model):
        result = []
        for index, row in enumerate(rows):
            try:
                result.append(model.model_validate_json(row[0]))
            except ValidationError:
                # Leave the original row available for recovery. Do not echo
                # corrupt payloads, which may contain sensitive strings.
                key = (model.__name__, index)
                if key not in self.invalid_records:
                    self.invalid_records.append(key)
        return result

    def save_session(self, session: RecordingSession):
        serialized = self._serialize(session)
        with self._db() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (session.id, serialized),
            )
            self.history_revision += 1
        directory = Path(session.directory)
        if directory.is_dir():
            temporary = directory / ".manifest.json.tmp"
            try:
                with temporary.open("w", encoding="utf-8") as output:
                    output.write(serialized)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(directory / "manifest.json")
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _serialize(value):
        # Remote room titles and error messages are untrusted too.
        def clean(item):
            if isinstance(item, str):
                return redact_sensitive_text(item)
            if isinstance(item, dict):
                return {k: clean(v) for k, v in item.items()}
            if isinstance(item, list):
                return [clean(v) for v in item]
            return item

        return json.dumps(clean(value.model_dump()), ensure_ascii=False)

    def recover_interrupted(self):
        recovered = []
        for session in self.sessions():
            if session.status == "recording":
                session.status = "interrupted"
                session.ended_at = utc_now()
                session.warnings.append(
                    "上次运行异常结束；未封口文件已保留，离线期间无法补录"
                )
                try:
                    self.save_session(session)
                except OSError:
                    # SQLite is already updated even when the output disk is unavailable.
                    pass
                recovered.append(session)
        return recovered
