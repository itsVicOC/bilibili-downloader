"""Capture isolated action bars and popup states with no account or media access."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--color-theme", default="star_trail")
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--record-baseline", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(args.source_root.resolve() if args.source_root else root))
    if args.native:
        os.environ["QT_QPA_PLATFORM"] = {"darwin": "cocoa", "win32": "windows"}.get(sys.platform, "xcb")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QPoint, QRect, qVersion
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    from bilibili_downloader import __version__
    from bilibili_downloader.gui.resources import load_stylesheet
    from bilibili_downloader.gui.resources.styles import theme_palette
    from bilibili_downloader.gui.resources.theme import ThemeManager
    from bilibili_downloader.gui.widgets.combo_box import ComboBox
    from bilibili_downloader.gui.widgets.components import (
        OutputActionBar,
        TaskDetailPanel,
    )
    from bilibili_downloader.gui.widgets.row_hover import RowHoverTable
    from bilibili_downloader.gui.widgets.selection import SelectionBar, SelectionState

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    theme = ThemeManager(app, args.color_theme, "light")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "geometry.json"
    report_path.write_text(json.dumps({"complete": False}) + "\n")
    rows = []

    def flush():
        for _ in range(8):
            app.processEvents()
        QTest.qWait(35)

    def shell():
        host = QWidget()
        host.setObjectName("FeedbackPreview")
        host.setStyleSheet(f"#FeedbackPreview {{ background: {theme_palette(theme.is_dark, args.color_theme).background}; }}")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(16, 16, 16, 16)
        return host, layout

    def save(host, width, name):
        host.resize(width, 480)
        host.show()
        host.raise_()
        host.activateWindow()
        QApplication.setActiveWindow(host)
        flush()
        widget = host.layout().itemAt(0).widget()
        host.resize(width, widget.height() + 32)
        flush()
        clipped = []
        for button in host.findChildren(QPushButton):
            if button.isVisible():
                bounds = QRect(button.mapTo(host, QPoint()), button.size())
                if not host.rect().contains(bounds) or button.width() < button.sizeHint().width():
                    clipped.append(button.text())
        clipped_labels = []
        for label in host.findChildren(QLabel):
            if label.isVisible() and label.wordWrap() and label.height() < label.heightForWidth(label.width()):
                clipped_labels.append(label.text())
        row = dict(file=name, requested_width=width, actual_width=host.width(),
                   height=host.height(), clipped_buttons=clipped, clipped_labels=clipped_labels)
        rows.append(row)
        if not args.record_baseline:
            assert host.width() == width and not clipped and not clipped_labels, row
        assert host.grab().save(str(args.output_dir / name))
        host.close()
        host.deleteLater()
        flush()

    for mode in ("light", "dark"):
        theme.set_mode(mode)
        for width in (420, 560, 780):
            for kind in ("output", "selection", "detail"):
                host, layout = shell()
                if kind == "output":
                    widget = OutputActionBar("已选 10000 个作品 · 10000 个任务")
                    widget.directory.set_full_text("预计：作者归档/很长的作品目录/001 - 夜航篇.mp4")
                    widget.primary_button.setText("加入 10000 个任务")
                    widget.primary_button.setEnabled(True)
                elif kind == "selection":
                    widget = SelectionBar()
                    widget.update_state(SelectionState(order=list(range(10000)), selected=set(range(10000)), visible={1, 2}))
                else:
                    widget = TaskDetailPanel()
                    widget.set_details("星轨旅记：夜航篇", "需要处理", "", "~/BiliFlow-demo/示例作品/001 - 夜航篇.mp4")
                    widget.set_actions(("重新选择位置…", lambda: None), ("打开文件夹", lambda: None))
                    widget.result_row.show()
                    widget.status.hide()
                    for badge, text in zip(widget.result_badges, ("媒体无法访问", "规格尚未确认", "字幕等附件待补全")):
                        badge.setText(text)
                layout.addWidget(widget)
                layout.addStretch()
                save(host, width, f"feedback-{kind}-{mode}-{width}.png")
        host, layout = shell()
        combo = ComboBox()
        combo.addItems(["当前选项 · 1080P", "其他选项 · 720P", "另一选项 · 480P"])
        layout.addWidget(combo)
        host.resize(360, 80)
        host.show()
        host.raise_()
        host.activateWindow()
        QApplication.setActiveWindow(host)
        flush()
        combo.showPopup()
        flush()
        view = combo.view()
        QTest.mouseMove(view.viewport(), view.visualRect(combo.model().index(1, 0)).center())
        flush()
        assert view.window().grab().save(str(args.output_dir / f"feedback-hover-{mode}.png"))
        from PySide6.QtCore import Qt
        QTest.keyClick(view, Qt.Key_Down)
        flush()
        assert view.window().grab().save(str(args.output_dir / f"feedback-keyboard-{mode}.png"))
        combo.hidePopup()
        host.close()
        host.deleteLater()
        flush()
        host, layout = shell()
        table = RowHoverTable(3, 2)
        table.setHorizontalHeaderLabels(["作品", "结果"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(48)
        table.setShowGrid(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for row in range(3):
            for column, text in enumerate((f"星轨旅记 · 第 {row + 1} 节", "媒体已保存")):
                table.setItem(row, column, QTableWidgetItem(text))
        layout.addWidget(table)
        host.resize(560, 250)
        host.show()
        host.raise_()
        host.activateWindow()
        QApplication.setActiveWindow(host)
        table.setFocus(Qt.TabFocusReason)
        flush()
        QTest.mouseMove(table.viewport(), table.visualItemRect(table.item(0, 0)).center())
        flush()
        assert host.grab().save(str(args.output_dir / f"feedback-row-hover-{mode}.png"))
        table.setCurrentCell(0, 0)
        QTest.keyClick(table, Qt.Key_Down)
        flush()
        if not args.record_baseline:
            assert table.hasFocus() and table.property("keyboardFocus")
        assert host.grab().save(str(args.output_dir / f"feedback-row-keyboard-{mode}.png"))
        host.close()
        host.deleteLater()
        flush()
        app.setStyleSheet(load_stylesheet(theme.is_dark, font_scale=theme._font_scale * 1.5,
                                         font_family=theme._font_family, theme_id=args.color_theme))
        host, layout = shell()
        widget = OutputActionBar("已选 10000 个作品 · 10000 个任务")
        widget.directory.set_full_text("预计：作者归档/很长的作品目录/001 - 夜航篇.mp4")
        widget.primary_button.setEnabled(True)
        widget.primary_button.setText("加入 10000 个任务")
        layout.addWidget(widget)
        layout.addStretch()
        save(host, 420, f"feedback-output-{mode}-font150.png")
        theme.apply_theme(theme.is_dark)
    profile = dict(complete=True, platform=sys.platform, qt=qVersion(), backend=app.platformName(),
                   version=__version__, color_theme=args.color_theme,
                   baseline=args.record_baseline, cases=rows)
    if not args.source_root:
        profile["revision"] = os.environ.get("GITHUB_SHA") or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        profile["working_tree_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    report_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(list(args.output_dir.glob('*.png')))} native/layout screenshots; {len(rows)} boundary cases")


if __name__ == "__main__":
    main()
