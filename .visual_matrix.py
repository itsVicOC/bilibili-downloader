"""Capture matching desktop workspaces with isolated offline data."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from bilibili_downloader.core.appearance import prepare_background
from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.models import DownloadItem, DownloadOutcome, TaskStatus, VideoInfo
from bilibili_downloader.core.progress import DownloadPhase
from bilibili_downloader.gui.dialogs.result_details import ResultDetailsDialog
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsSection
from bilibili_downloader.gui.resources.paths import asset_path
from scripts import capture_docs_screenshots as capture


def matrix(app, theme, window):
    artwork = prepare_background(Path(asset_path("nebula.jpg")))
    window._background_store.install(artwork)
    capture._populate_main_window(window)
    capture._populate_live_page(window, Path(app.property("docsTempRoot")) / "tuning-live")
    table = window._download_list
    table.mark_downloading(1)
    table.update_phase(1, DownloadPhase("transfer", "传输音频", .69))
    table.update_progress(1, .68, "传输音频 · 14.2 MB/s · 剩余 1:42")
    if hasattr(table, "update_transfer_metrics"):
        table.update_transfer_metrics(1, 14.2 * 1024**2, 102)
    base_id = 20
    for offset, (stage, label, fraction, progress, state) in enumerate((
        ("mux", "封装媒体", .33, .79, TaskStatus.MERGING),
        ("attachments", "补全字幕", None, .95, TaskStatus.DOWNLOADING),
    )):
        key = base_id + offset
        item = DownloadItem(video_info=VideoInfo(bvid=f"BVdemo{key}", title=f"星轨旅记 · {label}"))
        table.add_item(item, download_id=key, status=state, progress=progress, status_text=label)
        table.update_phase(key, DownloadPhase(stage, label, fraction, 1, 3))
        table.update_progress(key, progress, label, state)
    partial = DownloadOutcome(video_path="~/BiliFlow-demo/夜航.mp4", missing_artifacts=["subtitle"],
                              warnings=["字幕暂不可用，可稍后单独补全。"])
    table.mark_done(3, partial)
    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for kind, reference in (("none", ""), ("builtin", BUILTIN_BACKGROUNDS[0].reference), ("custom", artwork.reference)):
                for workspace in ("download", "live", "tasks", "settings"):
                    setattr(window._settings.appearance.backgrounds, workspace, reference)
                sizes = ((1120, 760),)
                if os.environ.get("QT_SCALE_FACTOR", "1") not in ("1", "1.0"):
                    sizes = ((900, 640),)
                for width, height in sizes:
                    window.resize(width, height)
                    stem = f"{theme_id}-{mode}-{kind}-{width}"
                    window._show_workspace(0)
                    window._workspace_scroll.verticalScrollBar().setValue(0)
                    capture._save_widget(app, window, f"resolved-{stem}.png")
                    window._show_workspace(1)
                    capture._save_widget(app, window, f"live-{stem}.png")
                    window._show_tasks(0)
                    capture._save_widget(app, window, f"progress-{stem}.png")
                    if width == 1120:
                        dialog = ResultDetailsDialog("保存与处理详情", "\n".join(partial.warnings), window, outcome=partial)
                        capture._save_widget(app, window, f"dialog-{stem}.png", popup=dialog)
                        dialog.accept()
                        dialog.deleteLater()
                    window._show_settings_tab(SettingsSection.DOWNLOAD)
                    capture._save_widget(app, window, f"settings-{stem}.png")
                    window._show_settings_tab(SettingsSection.APPEARANCE)
                    capture._save_widget(app, window, f"appearance-{stem}.png")


capture._capture_glass = matrix
raise SystemExit(capture.main())
