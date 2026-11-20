"""Readable result sections shared by task and file details."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPlainTextEdit

from bilibili_downloader.core.library import FILE_STATES, readable_file
from bilibili_downloader.core.media_policy import (
    ARTIFACT_LABELS,
    quality_label,
    specification_warnings,
)
from bilibili_downloader.core.models import AUDIO_CODEC_MAP, VIDEO_CODEC_MAP, OutputMode
from bilibili_downloader.gui.dialogs.attachments import companion_status
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.components import (
    ActionButton,
    CollapsibleSection,
    ReadOnlyPath,
    SectionCard,
    StatusBadge,
    help_text,
)


def result_summary(item, outcome):
    if outcome is None:
        return ("媒体待保存", "目标待确认", "附件待处理")
    verification = outcome.media_verification
    media = "媒体异常" if verification.get("valid") is False else "媒体已保存"
    known = outcome.actual_audio_quality is not None and (item.output_mode == OutputMode.AUDIO or outcome.actual_quality is not None and outcome.actual_video_codec is not None)
    specs = "规格待确认" if not known else "发生规格回退" if specification_warnings(item, outcome) else "规格匹配"
    requested = any(getattr(item, f"download_{kind}") for kind in ARTIFACT_LABELS) or item.download_all_subtitles
    saved = any((outcome.danmaku_path, outcome.subtitle_paths, outcome.cover_path, outcome.metadata_path))
    attachments = f"附件待补全 {len(outcome.missing_artifacts)} 项" if outcome.missing_artifacts else "附件已处理" if requested or saved else "未选择附件"
    return media, specs, attachments


class ResultDetailsDialog(WorkflowDialog):
    def __init__(self, title, text, parent=None, *, item=None, outcome=None, media_state="", can_supplement=False):
        super().__init__(title, parent=parent, confirm="关闭")
        self.repair_requested = False
        self.repair_button = None
        self.cancel_button.hide()
        self.confirm_button.setObjectName("OutputSecondaryButton")
        self.body.setSpacing(8)
        if item is not None and outcome is not None:
            media, specs, _ = result_summary(item, outcome)
            media = media_state or media
            headline = QLabel(item.display_title)
            headline.setTextFormat(Qt.PlainText)
            headline.setObjectName("SectionTitle")
            headline.setWordWrap(True)
            self.body.addWidget(headline)
            tone = {
                "媒体已保存": "success",
                FILE_STATES["available"]: "success",
                FILE_STATES["unchecked"]: "muted",
            }.get(media, "danger")
            self.body.addWidget(StatusBadge(media, tone), alignment=Qt.AlignLeft)
            if outcome.media_verification.get("valid") is False:
                self.body.addWidget(help_text(outcome.media_verification.get("message", "媒体核验未通过。")))
            statuses = {
                kind: companion_status(item, outcome, kind) for kind in ARTIFACT_LABELS
            }
            attention = {kind for kind, (_, _, missing) in statuses.items() if missing}
            assigned_warnings = set()
            extras = SectionCard() if attention else None
            if extras is not None:
                extras.setAccessibleName("需要处理的附件")
                extras.body.setContentsMargins(0, 8, 0, 8)
                extras.body.setSpacing(8)
            attachment_list = CollapsibleSection("其他附件" if attention else "全部附件")
            attachment_list.layout().setContentsMargins(0, 8, 0, 8)
            for kind, name in ARTIFACT_LABELS.items():
                state, _, missing = statuses[kind]
                label = QLabel(f"{name} · {state if state != '尚未保存' else '本次未选择'}")
                label.setTextFormat(Qt.PlainText)
                (extras if missing else attachment_list).body.addWidget(label)
                if missing:
                    reasons = [
                        warning for warning in outcome.warnings if warning.startswith(name)
                    ]
                    for warning in dict.fromkeys(reasons):
                        extras.body.addWidget(help_text(warning))
                        assigned_warnings.add(warning)
            if extras is not None:
                if can_supplement and outcome.missing_artifacts and readable_file(outcome.video_path):
                    self.repair_button = ActionButton("补全附件…")
                    self.repair_button.setObjectName("PrimaryButton")
                    self.repair_button.setAutoDefault(False)
                    self.repair_button.clicked.connect(self._request_repair)
                    extras.body.addWidget(self.repair_button, alignment=Qt.AlignLeft)
                self.body.addWidget(extras)
            for warning in dict.fromkeys((*outcome.spec_warnings, *outcome.warnings)):
                if warning not in assigned_warnings:
                    self.body.addWidget(help_text(warning))
            if len(attention) < len(ARTIFACT_LABELS):
                self.body.addWidget(attachment_list)
            else:
                attachment_list.deleteLater()
            locations = CollapsibleSection("规格与文件位置")
            locations.set_plain()
            locations.layout().setContentsMargins(0, 8, 0, 8)
            path = ReadOnlyPath()
            path.setAccessibleName("媒体文件位置")
            path.set_full_text(outcome.video_path)
            locations.body.addWidget(path)
            target = f"{item.selected_quality.label} · {VIDEO_CODEC_MAP.get(item.selected_video_codec, '自动')} · {AUDIO_CODEC_MAP.get(item.selected_audio_quality, '未知音质')}"
            actual = f"{quality_label(outcome.actual_quality)} · {VIDEO_CODEC_MAP.get(outcome.actual_video_codec, '未知编码')} · {AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '未知音质')}"
            if item.output_mode == OutputMode.AUDIO:
                target, actual = AUDIO_CODEC_MAP.get(item.selected_audio_quality, '未知音质'), AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '未知音质')
            locations.body.addWidget(help_text(f"{specs}\n目标：{target}\n实际：{actual}"))
            for kind, name in ARTIFACT_LABELS.items():
                paths = outcome.subtitle_paths if kind == "subtitle" else [getattr(outcome, f"{kind}_path")]
                for value in filter(None, paths):
                    row = ReadOnlyPath()
                    row.setAccessibleName(f"{name}文件位置")
                    row.set_full_text(value)
                    locations.body.addWidget(row)
            self.body.addWidget(locations)
        if text:
            details = QPlainTextEdit(text)
            details.setReadOnly(True)
            details.setAccessibleName("完整处理详情，可选择复制")
            details.setMinimumHeight(100)
            if item is not None and outcome is not None:
                diagnostics = CollapsibleSection("完整记录")
                diagnostics.set_plain()
                diagnostics.layout().setContentsMargins(0, 8, 0, 8)
                diagnostics.body.addWidget(details)
                self.body.addWidget(diagnostics)
            else:
                self.body.addWidget(details)
        self.body.addStretch()
        self.resize(680, 540)

    def _request_repair(self):
        self.repair_requested = True
        self.accept()
