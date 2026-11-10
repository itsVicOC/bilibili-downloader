"""Review companion status before starting an independent repair task."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel

from bilibili_downloader.core.library import readable_file
from bilibili_downloader.core.media_policy import ARTIFACT_LABELS
from bilibili_downloader.core.subtitle_provenance import subtitle_verified
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.check_box import CheckBox
from bilibili_downloader.gui.widgets.components import (
    ReadOnlyPath,
    SectionCard,
    StatusBadge,
    help_text,
)


def companion_status(item, outcome, kind):
    if outcome is None:
        return "待确认", False, False
    paths = outcome.subtitle_paths if kind == "subtitle" else [getattr(outcome, f"{kind}_path")]
    available = [p for p in paths if p and readable_file(p)]
    if kind == "subtitle" and any(not subtitle_verified(item.video_info, outcome, p) for p in available):
        return "待重新获取（旧字幕未核验）", False, True
    incomplete = kind in outcome.missing_artifacts or (kind == "subtitle" and item.download_all_subtitles and not outcome.subtitle_discovery_complete)
    if available and not incomplete:
        return (f"已保存 {len(available)} 种语言" if kind == "subtitle" else "已保存"), True, False
    requested = getattr(item, f"download_{kind}") or (kind == "subtitle" and item.download_all_subtitles)
    label = "部分已保存，待补全" if available else "待补全" if incomplete or requested else "尚未保存"
    return label, False, bool(incomplete or requested)


class AttachmentDialog(WorkflowDialog):
    def __init__(self, item, parent=None, *, outcome=None):
        super().__init__("补全附件", "仅补全所选附件，保留已有媒体与附件。", parent, confirm="开始补全")
        self.item = item
        self.choices = {}
        title = QLabel(item.display_title)
        title.setObjectName("SectionTitle")
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        self.body.addWidget(title)
        self.media_available = outcome is None or readable_file(outcome.video_path)
        if outcome:
            path = ReadOnlyPath()
            path.set_full_text(outcome.video_path)
            self.body.addWidget(path)
        group = SectionCard("附加内容")
        formats = {"danmaku": "ASS", "subtitle": "SRT", "cover": "图片", "metadata": "JSON"}
        for kind, label in ARTIFACT_LABELS.items():
            row = QHBoxLayout()
            check = CheckBox(f"{label} · {formats[kind]}")
            state, saved, missing = companion_status(item, outcome, kind)
            check.setEnabled(not saved and self.media_available)
            check.setChecked(missing and self.media_available)
            check.setToolTip("此附件已保存" if saved else "")
            self.choices[kind] = check
            row.addWidget(check, 1)
            row.addWidget(StatusBadge(state, "success" if saved else "warning" if missing else "muted"))
            group.body.addLayout(row)
            check.toggled.connect(self._update)
        self.body.addWidget(group)
        self.all_subtitles = CheckBox("补全全部可用字幕")
        self.all_subtitles.setChecked(item.download_all_subtitles)
        self.all_subtitles.setEnabled(self.choices["subtitle"].isEnabled() and self.choices["subtitle"].isChecked())
        self.body.addWidget(self.all_subtitles)
        self.choices["subtitle"].toggled.connect(lambda checked: self.all_subtitles.setEnabled(checked))
        self.all_subtitles.setToolTip("未勾选沿用原字幕语言；无可用字幕时保留媒体并记录原因。")
        self.all_subtitles.setAccessibleDescription(self.all_subtitles.toolTip())
        self.body.addStretch()
        if not self.media_available:
            self.notice.set_message("无法访问已有媒体，请在下载文件中重新定位或检查磁盘连接。", "warning")
        self._update()
        self.resize(640, 520)

    def _update(self):
        count = sum(check.isChecked() and check.isEnabled() for check in self.choices.values())
        self.confirm_button.setEnabled(count > 0 and self.media_available)
        self.confirm_button.setText(f"开始补全（{count} 项）")

    def selected_item(self):
        flags = {f"download_{key}": check.isChecked() and check.isEnabled() for key, check in self.choices.items()}
        flags["download_all_subtitles"] = flags["download_subtitle"] and self.all_subtitles.isChecked()
        return self.item.model_copy(update=flags, deep=True)


def choose_attachments(item, parent=None, *, outcome=None):
    dialog = AttachmentDialog(item, parent, outcome=outcome)
    return dialog.selected_item() if dialog.exec() else None


def confirm_media_copy(item, parent=None):
    dialog = WorkflowDialog("另存一份媒体", "重新下载为新副本，保留原有文件。", parent, confirm="另存并下载")
    dialog.body.addWidget(help_text(item.display_title))
    dialog.body.addWidget(help_text(f"目标：{item.selected_quality.label} · 输出 {item.output_mode.value.upper()}"))
    path = ReadOnlyPath()
    path.set_full_text(str(Path(item.output_dir or ".") / item.relative_output_path))
    dialog.body.addWidget(path)
    dialog.body.addWidget(help_text("以上为预计路径；同名文件存在时将使用新的副本文件名。"))
    dialog.body.addStretch()
    dialog.resize(640, 360)
    return bool(dialog.exec())
