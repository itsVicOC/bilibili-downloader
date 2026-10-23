"""Durable live subscriptions and recording manifests; never stores play URLs."""

import json
import os
import sqlite3
import threading
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.live_models import (
    LiveExport,
    LiveSubscription,
    RecordingSession,
)
from bilibili_downloader.core.task_repository import TaskDatabaseVersionError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def history_removal_reason(session: RecordingSession) -> str:
    if session.status not in {"completed", "stopped", "failed", "interrupted"}:
        return "请等待场次结束并完成收尾后再移除记录。"
    if session.mp4_export and session.mp4_export.status in {"queued", "running"}:
        return "此场次正在等待或执行导出，完成后可移除记录。"
    return ""


class LiveRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.history_revision = 0
        self._removed_session_ids = set()
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
        self.save_subscriptions([subscription])

    def save_subscriptions(self, subscriptions: list[LiveSubscription]):
        with self._db() as db:
            db.executemany(
                "INSERT INTO subscriptions VALUES (?, ?) ON CONFLICT(room_id) DO UPDATE SET payload=excluded.payload",
                [(subscription.room.room_id, self._serialize(subscription)) for subscription in subscriptions],
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
        with self._lock:
            self._save_session(session)

    def session(self, session_id: str) -> RecordingSession | None:
        with self._db() as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (session_id,)).fetchone()
        return RecordingSession.model_validate_json(row[0]) if row else None

    def update_export(self, session_id: str, export: LiveExport):
        # Merge into the latest recording payload rather than saving an old GUI
        # snapshot over the final segments or recording warnings.
        with self._lock:
            session = self.session(session_id)
            if session is None or session.status == "recording":
                raise ValueError("场次尚未结束或已不存在")
            session.mp4_export = export
            self._save_session(session)

    def remove_session(self, session_id: str) -> RecordingSession | None:
        """Remove only the DB record; leave all media and manifests untouched."""
        with self._lock:
            with self._db() as db:
                row = db.execute("SELECT payload FROM sessions WHERE id=?", (session_id,)).fetchone()
                if row is None:
                    return None
                session = RecordingSession.model_validate_json(row[0])
                reason = history_removal_reason(session)
                if reason:
                    raise ValueError(reason)
                db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            self._removed_session_ids.add(session_id)
            self.history_revision += 1
            return session

    def restore_session(self, session: RecordingSession) -> bool:
        """Restore a removed snapshot without rewriting a manifest or another ID."""
        with self._lock:
            with self._db() as db:
                cursor = db.execute(
                    "INSERT INTO sessions(id, payload) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
                    (session.id, self._serialize(session)),
                )
                restored = cursor.rowcount == 1
            if restored:
                self._removed_session_ids.discard(session.id)
                self.history_revision += 1
            return restored

    def _save_session(self, session: RecordingSession):
        if session.id in self._removed_session_ids:
            raise ValueError("该场次记录已移除，不会重新写入旧快照")
        serialized = self._serialize(session)
        with self._db() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (session.id, serialized),
            )
            self.history_revision += 1
        directory = Path(session.directory)
        if directory.is_dir():
            temporary = directory / f".manifest-{uuid.uuid4().hex}.tmp"
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
