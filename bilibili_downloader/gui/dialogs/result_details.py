"""Readable result sections shared by task and file details."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPlainTextEdit

from bilibili_downloader.core.media_policy import (
    ARTIFACT_LABELS,
    quality_label,
    specification_warnings,
)
from bilibili_downloader.core.models import AUDIO_CODEC_MAP, VIDEO_CODEC_MAP, OutputMode
from bilibili_downloader.gui.dialogs.attachments import companion_status
from bilibili_downloader.gui.dialogs.workflow import WorkflowDialog
from bilibili_downloader.gui.widgets.components import (
    ReadOnlyPath,
    SectionCard,
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
    def __init__(self, title, text, parent=None, *, item=None, outcome=None):
        super().__init__(title, "查看保存结果、目标与实际规格，以及逐项附加内容。", parent, confirm="关闭")
        self.cancel_button.hide()
        self.confirm_button.clicked.disconnect()
        self.confirm_button.clicked.connect(self.accept)
        if item is not None and outcome is not None:
            media, specs, attachments = result_summary(item, outcome)
            self.body.addWidget(help_text(f"{media} · {specs} · {attachments}"))
            path = ReadOnlyPath()
            path.set_full_text(outcome.video_path)
            self.body.addWidget(path)
            target = f"{item.selected_quality.label} · {VIDEO_CODEC_MAP.get(item.selected_video_codec, '自动')} · {AUDIO_CODEC_MAP.get(item.selected_audio_quality, '未知音质')}"
            actual = f"{quality_label(outcome.actual_quality)} · {VIDEO_CODEC_MAP.get(outcome.actual_video_codec, '未知编码')} · {AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '未知音质')}"
            if item.output_mode == OutputMode.AUDIO:
                target, actual = AUDIO_CODEC_MAP.get(item.selected_audio_quality, '未知音质'), AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '未知音质')
            group = SectionCard("规格")
            group.body.addWidget(help_text(f"目标：{target}"))
            group.body.addWidget(help_text(f"实际：{actual}"))
            self.body.addWidget(group)
            extras = SectionCard("附加内容")
            for kind, name in ARTIFACT_LABELS.items():
                state, _, _ = companion_status(item, outcome, kind)
                label = QLabel(f"{name}：{state}")
                label.setTextFormat(Qt.PlainText)
                extras.body.addWidget(label)
                paths = outcome.subtitle_paths if kind == "subtitle" else [getattr(outcome, f"{kind}_path")]
                for value in filter(None, paths):
                    row = ReadOnlyPath()
                    row.set_full_text(value)
                    extras.body.addWidget(row)
            self.body.addWidget(extras)
        if text:
            details = QPlainTextEdit(text)
            details.setReadOnly(True)
            details.setAccessibleName("完整处理详情，可选择复制")
            details.setMinimumHeight(100)
            self.body.addWidget(details)
        self.resize(680, 600)
