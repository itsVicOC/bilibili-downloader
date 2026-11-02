"""Select independent companion work without transferring the media again."""

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout


def choose_attachments(item, parent=None):
    dialog = QDialog(parent)
    dialog.setWindowTitle("补全附件")
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("复用已有媒体，仅保存缺失的附加内容。"))
    choices = {}
    for kind, label in (("danmaku", "弹幕"), ("subtitle", "字幕"), ("cover", "封面"), ("metadata", "元数据")):
        check = QCheckBox(label)
        check.setChecked(getattr(item, f"download_{kind}"))
        choices[kind] = check
        layout.addWidget(check)
    hint = QLabel()
    layout.addWidget(hint)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    def accept():
        if any(c.isChecked() for c in choices.values()):
            dialog.accept()
        else:
            hint.setText("请选择至少一项附件")
    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if not dialog.exec():
        return None
    return item.model_copy(update={**{f"download_{key}": check.isChecked() for key, check in choices.items()},
                                   "download_all_subtitles": item.download_all_subtitles and choices["subtitle"].isChecked()}, deep=True)
