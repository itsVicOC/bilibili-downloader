"""Deterministic visual gate for live export and directory inheritance."""

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.live_models import LiveExport, RecordingSegment
from bilibili_downloader.gui.resources.theme import ThemeManager
from scripts import capture_docs_screenshots as capture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "docs/images/live-export"
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    capture.OUTPUT_DIR = args.output_dir
    app = QApplication.instance() or QApplication(sys.argv)
    theme = ThemeManager(app)
    with tempfile.TemporaryDirectory(prefix="biliflow-live-visual-") as temporary:
        root = Path(temporary)
        app.setProperty("docsTempRoot", str(root))
        window = capture._make_main_window(root / "workspace")
        controller = window._live_controller
        controller._background_enabled = False
        capture._populate_live_page(window, root / "workspace/直播归档")
        session = controller.repository.sessions()[0]
        session.segments = []
        for index in range(4):
            path = (
                Path(session.directory)
                / f"attempt_{1 + index // 2:04d}"
                / f"part_{index % 2:03d}.flv"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            session.segments.append(
                RecordingSegment(
                    path=str(path),
                    duration=1800,
                    size=980000000,
                    finalized_at="2026-10-20T04:00:00+00:00",
                )
            )
        merged = Path(session.directory) / "整场直播.mp4"
        merged.touch()
        for theme_id in ("star_trail", "bilibili_blue"):
            theme.set_color_theme(theme_id)
            for dark in (True, False):
                theme.apply_theme(dark)
                mode = "dark" if dark else "light"
                for width, height in ((900, 640), (1120, 760), (1320, 860)):
                    window.resize(width, height)
                    states = (
                        ("normal", "queued", "running", "completed", "failed")
                        if width == 900
                        else ("normal",)
                    )
                    for state in states:
                        session.mp4_export = (
                            None
                            if state == "normal"
                            else LiveExport(
                                path=str(merged),
                                status=state,
                                progress="整理片段 2/4"
                                if state == "running"
                                else "等待导出"
                                if state == "queued"
                                else "已导出 MP4",
                                error="片段 3（part_000.flv）与首段的分辨率或音频参数不兼容，无法无损合并。"
                                if state == "failed"
                                else "",
                            )
                        )
                        controller.exporting = state in {"queued", "running"}
                        page = window._task_page
                        page.update_history([session])
                        page.history.setCurrentItem(page.history.topLevelItem(0))
                        page.history.expandAll()
                        window._show_tasks(2)
                        capture._save_widget(
                            app, window, f"{theme_id}-{mode}-{state}-{width}.png"
                        )
                        capture._flush_events(app)
                        assert window.width() == width and window.height() == height
                        assert (
                            page.history_actions.geometry().bottom()
                            <= page.tabs.height()
                        )
                        assert page.history.viewport().height() >= 70
                        assert page.history.horizontalScrollBar().maximum() == 0
                        assert page.history_actions.rect().contains(
                            page.export_button.geometry()
                        )
                        assert (
                            page.history_summary.geometry().bottom()
                            < page.history_actions.geometry().top()
                        )
                controller.exporting = False
                window.resize(900, 640)
                rows = controller.service.rows
                rows[0].update(
                    output_dir_mode="default",
                    active_output_dir=session.directory,
                    output_dir="~/Downloads/BiliFlow/新的直播保存目录",
                )
                rows[1].update(output_dir_mode=None)
                controller.refresh()
                window._show_workspace(1)
                window._live_page._scroll.ensureWidgetVisible(
                    window._live_page._directory_hint
                )
                capture._save_widget(
                    app, window, f"{theme_id}-{mode}-directory-900.png"
                )
                window._settings_page.set_live_rooms(rows)
                window._show_settings_tab(1)
                capture._save_widget(app, window, f"{theme_id}-{mode}-settings-900.png")
                window._settings_page.tabs.widget(1).ensureWidgetVisible(
                    window._settings_page._directory_review
                )
                capture._save_widget(
                    app, window, f"{theme_id}-{mode}-directory-review-900.png"
                )
                window._settings_page.tabs.widget(1).verticalScrollBar().setValue(0)
        controller.shutdown()
        controller.service.rows = []
        controller.refresh()
        window._settings_page.load_settings(window._settings)
        window.close()
    print(f"Saved live export screenshots: {args.output_dir}")


if __name__ == "__main__":
    main()
