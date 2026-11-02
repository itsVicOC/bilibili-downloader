"""Offline, repeatable 1,000-task / 10,000-file desktop baseline.

Uses temporary synthetic one-byte media, never the user's configuration or
files. Results describe UI/database overhead, not real media disk throughput.
"""

import argparse
import json
import os
import platform
import sqlite3
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.library import LibraryRepository
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    TaskStatus,
    VideoInfo,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.widgets.download_list import DownloadListWidget
from bilibili_downloader.gui.widgets.library_page import LibraryPage
from scripts.capture_docs_screenshots import _make_main_window


def timed(call):
    start = time.perf_counter()
    result = call()
    return result, round((time.perf_counter() - start) * 1000, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/archive-benchmark.json"))
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="biliflow-benchmark-") as directory:
        root = Path(directory)
        repository = LibraryRepository(root / "library.sqlite3")
        tasks = TaskRepository(root / "tasks.sqlite3")
        task_items = []
        with sqlite3.connect(repository.database_path) as db:
            for n in range(10_000):
                path = root / f"fixture-{n:05d}.mp4"
                path.write_bytes(b"x")
                item = DownloadItem(video_info=VideoInfo(bvid=f"BVfixture{n:05d}", cid=n + 1,
                                    title=f"演示文件 {n:05d}", author=f"作者 {n % 100}"), output_dir=str(root))
                outcome = DownloadOutcome(video_path=str(path), actual_quality=80, actual_video_codec=12, actual_audio_quality=30280)
                outcome.media_signature = LibraryRepository._signature(path.stat())
                asset_id = db.execute("INSERT INTO assets(identity,path,item_json,outcome_json,created_at) VALUES(?,?,?,?,?)",
                                      (item.video_info.content_identity, str(path), item.model_dump_json(), outcome.model_dump_json(), "2026-11-02")).lastrowid
                db.execute("INSERT INTO files(asset_id,kind,path,state,size) VALUES(?,'media',?,'unchecked',1)", (asset_id, str(path)))
                if n < 1000:
                    task_items.append(item)
        for item in task_items:
            tasks.add(item, TaskStatus.PAUSED)
        records, task_query = timed(tasks.list_tasks)
        table = DownloadListWidget()
        def load_tasks():
            table.blockSignals(True)
            for record in records:
                table.add_item(record.item, download_id=record.id, status=record.status)
            table.blockSignals(False)
        _, queue_load = timed(load_tasks)
        page = LibraryPage()
        page.repository = repository
        _, file_load = timed(page.refresh)
        _, file_search = timed(lambda: page.search.setText("09999"))
        match, lookup = timed(lambda: repository.match_media(task_items[500]))
        assert match.state == "saved"
        page.search.clear()
        heartbeat_gaps = []
        last = time.perf_counter()
        def heartbeat():
            nonlocal last
            now = time.perf_counter()
            heartbeat_gaps.append((now - last) * 1000)
            last = now
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(heartbeat)
        timer.start()
        started = time.perf_counter()
        page.check()
        while page._jobs:
            app.processEvents()
            time.sleep(0.001)
        check_ms = (time.perf_counter() - started) * 1000
        timer.stop()
        # Exercise search in the actual task center, independently of bulk creation.
        window = _make_main_window(root / "window")
        window._download_list.blockSignals(True)
        for record in records:
            window._download_list.add_item(record.item, download_id=record.id, status=record.status)
        window._download_list.blockSignals(False)
        _, queue_search = timed(lambda: window._task_page.search.setText("BVfixture00500"))
        report = {"platform": platform.platform(), "python": platform.python_version(),
                  "backend": app.platformName(), "tasks": 1000, "file_records": 10000,
                  "task_query_ms": task_query, "queue_population_ms": queue_load,
                  "queue_search_ms": queue_search, "file_population_ms": file_load,
                  "file_search_ms": file_search, "indexed_media_lookup_ms": lookup,
                  "background_check_ms": round(check_ms, 1),
                  "max_background_heartbeat_gap_ms": round(max(heartbeat_gaps, default=0), 1),
                  "fixture": "Temporary local one-byte media; measures overhead, not media throughput"}
        window._live_controller.shutdown()
        window.request_quit(confirmed=True)
        page.close()
        table.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
