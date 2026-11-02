"""Independent media inventory and recoverable registration of download results."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bilibili_downloader.core.models import DownloadItem, DownloadOutcome, TaskStatus
from bilibili_downloader.core.update_protocol import atomic_json

LIBRARY_SCHEMA_VERSION = 1
FILE_STATES = {
    "unchecked": "待检查",
    "available": "文件存在",
    "missing": "文件缺失",
    "inaccessible": "无法访问",
    "recycled": "已回收",
}
_MEDIA_LOCKS = [threading.Lock() for _ in range(64)]


@dataclass
class MediaMatch:
    state: str
    outcome: DownloadOutcome | None = None
    missing: tuple[str, ...] = ()


def readable_file(path):
    try:
        file = Path(path)
        if not stat.S_ISREG(file.lstat().st_mode) or file.stat().st_size == 0:
            return False
        with file.open("rb") as handle:
            return bool(handle.read(1))
    except (OSError, ValueError):
        return False


def absolute_path(path):
    # Keep the final component intact: deleting a link must never delete its target.
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _artifacts(outcome):
    yield "media", outcome.video_path
    for kind, paths in (
        ("danmaku", [outcome.danmaku_path]),
        ("subtitle", outcome.subtitle_paths),
        ("cover", [outcome.cover_path]),
        ("metadata", [outcome.metadata_path]),
    ):
        for path in paths:
            if path:
                yield kind, path


class LibraryRepository:
    """Assets survive task removal; hidden rows are durable import tombstones."""

    def __init__(self, database_path: Path, *, initialize=True):
        self.database_path = Path(database_path)
        self.pending_dir = self.database_path.parent / "library-pending"
        self._lock = threading.RLock()
        self._ready = False
        if initialize:
            self.initialize()

    def initialize(self):
        if self._ready:
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > LIBRARY_SCHEMA_VERSION:
                raise ValueError("媒体库来自更新版本，当前版本不会修改该文件")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY, identity TEXT NOT NULL,
                    path TEXT NOT NULL, item_json TEXT NOT NULL,
                    outcome_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(identity, path)
                );
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL
                    REFERENCES assets(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, path TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'unchecked',
                    size INTEGER, checked_at TEXT, signature TEXT,
                    UNIQUE(asset_id, path)
                );
                CREATE INDEX IF NOT EXISTS idx_library_file_path ON files(path);
                CREATE INDEX IF NOT EXISTS idx_library_identity ON assets(identity);
                CREATE INDEX IF NOT EXISTS idx_library_bvid_cid ON assets(
                    json_extract(item_json,'$.video_info.bvid'),
                    json_extract(item_json,'$.video_info.cid'));
                CREATE TABLE IF NOT EXISTS imports (
                    identity TEXT NOT NULL, path TEXT NOT NULL,
                    asset_id INTEGER NOT NULL REFERENCES assets(id),
                    PRIMARY KEY(identity,path)
                );
            """)
            db.execute(f"PRAGMA user_version={LIBRARY_SCHEMA_VERSION}")
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass
        self._ready = True

    @contextmanager
    def _connection(self):
        with self._lock:
            db = sqlite3.connect(self.database_path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with db:
                    yield db
            finally:
                db.close()

    def register(
        self,
        item: DownloadItem,
        outcome: DownloadOutcome,
        *,
        imported=False,
        created_at=None,
    ):
        self.initialize()
        path = absolute_path(outcome.video_path)
        identity = item.video_info.content_identity
        info = item.video_info.model_copy(
            update={"video_streams": [], "audio_streams": [], "subtitle_list": []}
        )
        clean = item.model_copy(update={"video_info": info})
        if outcome.media_signature is None and readable_file(path):
            outcome.media_signature = self._signature(Path(path).stat())
        with self._connection() as db:
            db.execute(
                """INSERT INTO assets(identity,path,item_json,outcome_json,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(identity,path) DO UPDATE SET
                item_json=excluded.item_json,outcome_json=excluded.outcome_json""",
                (
                    identity,
                    path,
                    clean.model_dump_json(),
                    outcome.model_dump_json(),
                    created_at or _now(),
                ),
            )
            asset_id = db.execute(
                "SELECT id FROM assets WHERE identity=? AND path=?", (identity, path)
            ).fetchone()[0]
            db.execute(
                "INSERT OR IGNORE INTO imports(identity,path,asset_id) VALUES(?,?,?)",
                (identity, path, asset_id),
            )
            if not imported:
                db.execute("UPDATE assets SET hidden=0 WHERE id=?", (asset_id,))
            for kind, file_path in _artifacts(outcome):
                size, signature, state = None, None, "unchecked"
                try:
                    value = Path(file_path).lstat()
                    if stat.S_ISREG(value.st_mode):
                        size, signature = value.st_size, self._signature(value)
                        if not imported:
                            state = "available"
                except OSError:
                    pass
                db.execute(
                    """INSERT INTO files(asset_id,kind,path,size,signature,state) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(asset_id,path) DO UPDATE SET size=excluded.size,
                    signature=excluded.signature,state=excluded.state""",
                    (asset_id, kind, absolute_path(file_path), size, signature, state),
                )
        return asset_id

    def record_download(self, item, outcome):
        """Write a replayable receipt before changing the independent database."""
        if outcome.media_signature is None and readable_file(outcome.video_path):
            outcome.media_signature = self._signature(Path(outcome.video_path).stat())
        info = item.video_info.model_copy(
            update={"video_streams": [], "audio_streams": [], "subtitle_list": []}
        )
        clean = item.model_copy(update={"video_info": info})
        key = hashlib.sha256(
            f"{info.content_identity}:{absolute_path(outcome.video_path)}".encode()
        ).hexdigest()
        receipt = self.pending_dir / f"{key}.json"
        with self._lock:
            self.pending_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            atomic_json(
                receipt,
                {
                    "item": clean.model_dump(mode="json"),
                    "outcome": outcome.model_dump(mode="json"),
                },
            )
            asset_id = self.register(clean, outcome)
            receipt.unlink(missing_ok=True)
        return asset_id

    def replay_pending(self):
        self.initialize()
        failures = []
        for receipt in self.pending_dir.glob("*.json"):
            try:
                data = json.loads(receipt.read_text("utf-8"))
                self.register(
                    DownloadItem.model_validate(data["item"]),
                    DownloadOutcome.model_validate(data["outcome"]),
                )
                receipt.unlink()
            except (OSError, ValueError, KeyError, sqlite3.Error):
                failures.append(receipt.name)
        return failures

    def import_tasks(self, records):
        for record in records:
            if record.status != TaskStatus.COMPLETED or not record.output_path:
                continue
            outcome = record.outcome or self._legacy_outcome(record)
            # Existing inventory is authoritative, including relocated paths and tombstones.
            with self._connection() as db:
                exists = db.execute(
                    "SELECT 1 FROM imports WHERE identity=? AND path=?",
                    (
                        record.item.video_info.content_identity,
                        absolute_path(record.output_path),
                    ),
                ).fetchone()
            if not exists:
                self.register(
                    record.item, outcome, imported=True, created_at=record.completed_at
                )

    @staticmethod
    def _legacy_outcome(record):
        media = Path(record.output_path)
        outcome = DownloadOutcome(video_path=str(media), warnings=record.warnings)
        manifest = media.with_name(f"{media.stem}.info.json")
        try:
            data = json.loads(manifest.read_text("utf-8"))
            video, artifact = data["video"], data["artifact"]
            info = record.item.video_info
            if (
                video.get("cid") != info.cid
                or video.get("bvid", "") != info.bvid
                or (
                    info.episode_id
                    and data.get("bangumi", {}).get("episode_id") != info.episode_id
                )
                or artifact.get("file") != media.name
            ):
                return outcome

            def companion(name):
                if (
                    isinstance(name, str)
                    and name
                    and name == Path(name).name
                    and "/" not in name
                    and "\\" not in name
                ):
                    return str(media.parent / name)
                return None

            outcome.danmaku_path = companion(artifact.get("danmaku"))
            outcome.cover_path = companion(artifact.get("cover"))
            outcome.subtitle_paths = [
                p for name in artifact.get("subtitles", []) if (p := companion(name))
            ]
            outcome.metadata_path = str(manifest)
            for field in (
                "actual_quality",
                "actual_video_codec",
                "actual_audio_quality",
            ):
                setattr(outcome, field, artifact.get(field))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return outcome

    def list_assets(self, *, include_hidden=False):
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM assets"
                + ("" if include_hidden else " WHERE hidden=0")
                + " ORDER BY id DESC"
            ).fetchall()
            grouped_files = {}
            for entry in db.execute("SELECT * FROM files ORDER BY id"):
                grouped_files.setdefault(entry["asset_id"], []).append(dict(entry))
            result = []
            for row in rows:
                asset = dict(row)
                asset["item"] = DownloadItem.model_validate_json(row["item_json"])
                asset["outcome"] = DownloadOutcome.model_validate_json(
                    row["outcome_json"]
                )
                asset["files"] = grouped_files.get(row["id"], [])
                result.append(asset)
            return result

    @contextmanager
    def media_lock(self, item, cancelled):
        key = (item.video_info.bvid or item.video_info.content_identity, item.video_info.cid)
        lock = _MEDIA_LOCKS[hash(key) % len(_MEDIA_LOCKS)]
        while not lock.acquire(timeout=0.1):
            cancelled()
        try:
            cancelled()
            yield
        finally:
            lock.release()

    def match_media(self, item):
        """Find a usable asset, including hidden inventory, without task history.

        File rows are authoritative after relocation. A requested specification
        is never used as evidence of what was actually saved.
        """
        from bilibili_downloader.core.media_policy import specifications_match

        self.initialize()
        info = item.video_info
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM assets WHERE identity=? OR "
                "(json_extract(item_json,'$.video_info.bvid')=? AND ?<>'' AND "
                "json_extract(item_json,'$.video_info.cid')=?) ORDER BY id DESC",
                (info.content_identity, info.bvid, info.bvid, info.cid),
            ).fetchall()
            assets = [(dict(row), [dict(f) for f in db.execute(
                "SELECT * FROM files WHERE asset_id=?", (row["id"],)
            )]) for row in rows]
        state, best = "not_saved", None
        for asset, files in assets:
            previous = DownloadItem.model_validate_json(asset["item_json"])
            if previous.output_mode != item.output_mode:
                continue
            media = next((f for f in files if f["kind"] == "media"), None)
            if not media or (item.reuse_media_path and absolute_path(item.reuse_media_path) != media["path"]):
                continue
            if not readable_file(media["path"]) or media["state"] == "recycled":
                state = "unavailable"
                continue
            outcome = DownloadOutcome.model_validate_json(asset["outcome_json"])
            signature = outcome.media_signature or media["signature"]
            if signature is None or self._signature(Path(media["path"]).stat()) != signature:
                state = "unavailable"
                continue
            if outcome.media_verification.get("valid") is False:
                state = "unavailable"
                continue
            if not item.reuse_media_path and not specifications_match(item, outcome):
                state = "specification_mismatch"
                continue
            outcome.video_path = media["path"]
            # Keep successful attachments, using relocated file records.
            paths = {f["kind"]: f["path"] for f in files if readable_file(f["path"]) and f["state"] != "recycled"}
            for kind in ("danmaku", "cover", "metadata"):
                setattr(outcome, f"{kind}_path", paths.get(kind))
            old_subtitles = {absolute_path(path) for path in outcome.subtitle_paths}
            subs = [f["path"] for f in files if f["kind"] == "subtitle" and readable_file(f["path"]) and f["state"] != "recycled"]
            outcome.subtitle_paths = subs
            outcome.subtitle_languages = {lan: absolute_path(path) for lan, path in outcome.subtitle_languages.items() if absolute_path(path) in subs}
            if set(subs) != old_subtitles:
                outcome.subtitle_discovery_complete = False
            missing = []
            for kind in ("danmaku", "cover", "metadata"):
                if getattr(item, f"download_{kind}") and not paths.get(kind):
                    missing.append(kind)
            wants_subtitles = item.download_subtitle or item.download_all_subtitles
            has_subtitles = (
                bool(subs) and outcome.subtitle_discovery_complete
                if item.download_all_subtitles else
                item.selected_subtitle_lan in outcome.subtitle_languages or (
                    bool(subs) and not outcome.subtitle_languages
                    and previous.selected_subtitle_lan == item.selected_subtitle_lan
                    and not previous.download_all_subtitles
                )
            )
            if wants_subtitles and (not has_subtitles or "subtitle" in outcome.missing_artifacts):
                missing.append("subtitle")
            match = MediaMatch("missing_attachments" if missing else "saved", outcome, tuple(missing))
            if best is None or len(missing) < len(best.missing):
                best = match
        return best or MediaMatch(state)

    def hide(self, asset_ids):
        with self._connection() as db:
            changed = [
                i
                for i in dict.fromkeys(asset_ids)
                if db.execute(
                    "SELECT 1 FROM assets WHERE id=? AND hidden=0", (i,)
                ).fetchone()
            ]
            db.executemany(
                "UPDATE assets SET hidden=1 WHERE id=?", [(i,) for i in changed]
            )
        return changed

    def restore_hidden(self, asset_ids):
        with self._connection() as db:
            restored = [
                i
                for i in dict.fromkeys(asset_ids)
                if db.execute(
                    "SELECT 1 FROM assets WHERE id=? AND hidden=1", (i,)
                ).fetchone()
            ]
            db.executemany(
                "UPDATE assets SET hidden=0 WHERE id=?", [(i,) for i in restored]
            )
        return restored

    def files_for(self, asset_ids):
        with self._connection() as db:
            return [
                dict(row)
                for asset_id in asset_ids
                for row in db.execute(
                    "SELECT * FROM files WHERE asset_id=? ORDER BY id", (asset_id,)
                )
            ]

    @staticmethod
    def _signature(value):
        return f"{value.st_dev}:{value.st_ino}:{value.st_size}:{value.st_mtime_ns}"

    def check_files(self, asset_ids, cancel=None, progress=None):
        entries = self.files_for(asset_ids)
        report = {
            "total": len(entries),
            "checked": 0,
            "missing": 0,
            "inaccessible": 0,
            "cancelled": False,
            "issues": [],
        }
        for entry in entries:
            if cancel is not None and cancel.is_set():
                report["cancelled"] = True
                break
            path = Path(entry["path"])
            signature, size = None, None
            try:
                # A missing parent (disconnected drive, renamed folder) is not a missing file.
                if not path.parent.is_dir():
                    state = "inaccessible"
                else:
                    value = path.lstat()
                    if not stat.S_ISREG(value.st_mode):
                        state = "inaccessible"
                    else:
                        with path.open("rb") as handle:
                            handle.read(1)
                        state, size, signature = (
                            "available",
                            value.st_size,
                            self._signature(value),
                        )
            except FileNotFoundError:
                state = "recycled" if entry["state"] == "recycled" else "missing"
            except OSError:
                state = "inaccessible"
            with self._connection() as db:
                db.execute(
                    "UPDATE files SET state=?,size=?,signature=?,checked_at=? WHERE id=? AND path=?",
                    (state, size, signature, _now(), entry["id"], entry["path"]),
                )
            report["checked"] += 1
            if state in ("missing", "inaccessible"):
                report[state] += 1
                report["issues"].append(
                    (
                        entry["path"],
                        "文件未找到"
                        if state == "missing"
                        else "无法访问，请检查目录或磁盘连接",
                    )
                )
            if progress:
                progress(report["checked"], len(entries))
        return report

    def relocate(self, file_id, destination):
        destination = absolute_path(destination)
        path = Path(destination)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("请选择普通文件")
        with self._connection() as db:
            entry = db.execute(
                "SELECT asset_id,kind,path FROM files WHERE id=?", (file_id,)
            ).fetchone()
            if entry is None:
                raise ValueError("文件记录已移除")
            if entry["kind"] == "media":
                db.execute(
                    "UPDATE assets SET path=? WHERE id=?",
                    (destination, entry["asset_id"]),
                )
            db.execute(
                "UPDATE files SET path=?,state='unchecked',size=NULL,signature=NULL,checked_at=NULL WHERE id=?",
                (destination, file_id),
            )
            self._sync_outcome_paths(db, entry["asset_id"], {entry["path"]: destination})

    @staticmethod
    def _sync_outcome_paths(db, asset_id, mapping=None):
        row = db.execute("SELECT outcome_json FROM assets WHERE id=?", (asset_id,)).fetchone()
        outcome = DownloadOutcome.model_validate_json(row[0])
        files = [dict(f) for f in db.execute("SELECT * FROM files WHERE asset_id=?", (asset_id,))]
        for kind in ("media", "danmaku", "cover", "metadata"):
            entry = next((f for f in files if f["kind"] == kind), None)
            if entry:
                setattr(outcome, "video_path" if kind == "media" else f"{kind}_path", entry["path"])
        outcome.subtitle_paths = [f["path"] for f in files if f["kind"] == "subtitle"]
        outcome.subtitle_languages = {lan: (mapping or {}).get(absolute_path(path), absolute_path(path)) for lan, path in outcome.subtitle_languages.items()}
        outcome.media_verification = {}
        outcome.media_signature = LibraryRepository._signature(Path(outcome.video_path).stat()) if readable_file(outcome.video_path) else None
        db.execute("UPDATE assets SET outcome_json=? WHERE id=?", (outcome.model_dump_json(), asset_id))

    def relocate_directory(self, old_root, new_root, *, apply=False):
        """Preview or atomically relink a directory; never move media on disk."""
        old_root, new_root = Path(absolute_path(old_root)), Path(absolute_path(new_root))
        if old_root == new_root:
            raise ValueError("新旧目录相同")
        with self._connection() as db:
            changes = []
            for row in db.execute("SELECT * FROM files"):
                try:
                    relative = Path(row["path"]).relative_to(old_root)
                except ValueError:
                    continue
                target = str(new_root / relative)
                changes.append({"id": row["id"], "asset_id": row["asset_id"], "kind": row["kind"],
                                "old": row["path"], "new": target, "available": readable_file(target)})
            if not apply:
                return changes
            if not changes or any(not entry["available"] for entry in changes):
                raise ValueError("部分目标文件无法读取，未修改记录。请检查新目录后重试。")
            # One transaction protects all media and attachment paths against collisions.
            for entry in changes:
                if entry["kind"] == "media":
                    db.execute("UPDATE assets SET path=? WHERE id=?", (entry["new"], entry["asset_id"]))
                db.execute("UPDATE files SET path=?,state='unchecked',checked_at=NULL,signature=NULL,size=NULL WHERE id=?",
                           (entry["new"], entry["id"]))
            mapping = {entry["old"]: entry["new"] for entry in changes}
            for asset_id in {entry["asset_id"] for entry in changes}:
                self._sync_outcome_paths(db, asset_id, mapping)
        return changes

    def verify_media(self, asset_ids, ffmpeg_path=None, cancel=None, progress=None):
        from bilibili_downloader.core.ffmpeg import FFmpegManager
        assets = [a for a in self.list_assets() if a["id"] in set(asset_ids)]
        report = {"checked": 0, "missing": 0, "inaccessible": 0, "invalid": 0, "cancelled": False, "issues": []}
        for asset in assets:
            if cancel is not None and cancel.is_set():
                report["cancelled"] = True
                break
            media = next((f for f in asset["files"] if f["kind"] == "media"), None)
            if not media:
                continue
            result = FFmpegManager.inspect_media(Path(media["path"]), asset["item"].output_mode, ffmpeg_path)
            if result.get("unavailable"):
                report["inaccessible"] += 1
            elif not result["valid"]:
                report["invalid"] += 1
            if not result["valid"]:
                report["issues"].append((media["path"], result["message"]))
            # A missing tool or offline drive is not proof of media corruption.
            if not result.get("unavailable"):
                with self._connection() as db:
                    current = db.execute("SELECT path FROM files WHERE id=?", (media["id"],)).fetchone()
                    if current and current[0] == media["path"]:
                        row = db.execute("SELECT outcome_json FROM assets WHERE id=?", (asset["id"],)).fetchone()
                        outcome = DownloadOutcome.model_validate_json(row[0])
                        outcome.media_verification = {**result, "checked_at": _now()}
                        db.execute("UPDATE assets SET outcome_json=? WHERE id=?", (outcome.model_dump_json(), asset["id"]))
            report["checked"] += 1
            if progress:
                progress(report["checked"], len(assets))
        return report

    def recycle(self, entries, move_to_trash=None, progress=None):
        if move_to_trash is None:
            from PySide6.QtCore import QFile

            move_to_trash = QFile.moveToTrash
        results = []
        for entry in entries:
            path = Path(entry["path"])
            error = ""
            try:
                with self._connection() as db:
                    current = db.execute(
                        "SELECT * FROM files WHERE id=?", (entry["id"],)
                    ).fetchone()
                    shared = db.execute(
                        "SELECT 1 FROM files WHERE path=? AND asset_id<>? LIMIT 1",
                        (entry["path"], entry["asset_id"]),
                    ).fetchone()
                if current is None or current["path"] != entry["path"]:
                    raise ValueError("文件位置已更新，请重新选择")
                if shared:
                    raise ValueError("文件仍被其他媒体记录引用")
                value = path.lstat()
                if not stat.S_ISREG(value.st_mode):
                    raise ValueError("仅支持普通文件，已跳过目录或符号链接")
                if entry["signature"] and self._signature(value) != entry["signature"]:
                    raise ValueError("文件已变化，请核对后重试")
                result = move_to_trash(str(path))
                ok = result[0] if isinstance(result, tuple) else result
                if not ok:
                    raise OSError("无法移入系统回收站")
                with self._connection() as db:
                    db.execute(
                        "UPDATE files SET state='recycled',checked_at=? WHERE id=?",
                        (_now(), entry["id"]),
                    )
            except (OSError, ValueError, sqlite3.Error) as exc:
                error = str(exc)
            results.append((str(path), error))
            if progress:
                progress(len(results), len(entries))
        return results
