"""Rich release notes: semantic formatting, theme changes and link handling."""

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QTextCursor, QTextTable
from PySide6.QtWidgets import QTextBrowser

from bilibili_downloader.gui.dialogs.update_dialog import UpdateDialog
from bilibili_downloader.gui.resources.styles import theme_palette
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.release_notes import ReleaseNotesBrowser
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_update_gui import RELEASE

MARKDOWN = '''# 更新内容

## 新功能

**清晰的标题**、*说明*与 `biliflow --help`。

- 支持下载
- 支持直播

> 保留已有设置。

| 平台 | 结果 |
| --- | --- |
| Windows | 通过 |

```python
print("你好")
```

[文档](docs/FLUENT_DESIGN.md) · [定位](#新功能)
'''


def fragments(document):
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                yield fragment
            iterator += 1
        block = block.next()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_markdown_has_semantic_blocks_and_readable_theme(qapp, qtbot, theme_id, dark):
    manager = ThemeManager(qapp, theme_id, "dark" if dark else "light")
    dialog = UpdateDialog(replace(RELEASE, notes=MARKDOWN))
    qtbot.addWidget(dialog)
    dialog.show()
    notes = dialog.notes
    assert isinstance(notes, QTextBrowser)
    assert "**" not in notes.toPlainText() and "```" not in notes.toPlainText()
    assert "更新内容" in notes.toPlainText() and "Windows" in notes.toPlainText()
    blocks = []
    block = notes.document().begin()
    while block.isValid():
        blocks.append(block)
        block = block.next()
    assert any(block.blockFormat().headingLevel() == 2 for block in blocks)
    assert sum(bool(block.textList()) for block in blocks) == 2
    assert any(fragment.charFormat().fontWeight() >= QFont.Bold for fragment in fragments(notes.document()) if "清晰" in fragment.text())
    tables = [frame for frame in notes.document().rootFrame().childFrames() if isinstance(frame, QTextTable)]
    assert len(tables) == 1 and tables[0].rows() == 2
    colors = theme_palette(dark, theme_id)
    for fragment in fragments(notes.document()):
        fmt = fragment.charFormat()
        assert fmt.foreground().color().name() == (colors.active_text if fmt.anchorHref() else colors.text)
    assert notes.horizontalScrollBar().maximum() == 0
    manager.deleteLater()


def test_images_become_descriptions_and_links_are_explicit(qtbot, monkeypatch):
    notes = ReleaseNotesBrowser(replace(RELEASE, notes='![背景预览](https://example.com/bg.png)\n\n![本地图](file:///private/test.png)\n\n[说明](docs/guide.md)'))
    qtbot.addWidget(notes)
    assert "背景预览" in notes.toPlainText() and "本地图" in notes.toPlainText()
    assert "\ufffc" not in notes.toPlainText()
    assert not any(fragment.charFormat().isImageFormat() for fragment in fragments(notes.document()))
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    notes._open_link(QUrl('docs/guide.md'))
    notes._open_link(QUrl('https://example.com/notes'))
    notes._open_link(QUrl('file:///private/test.png'))
    notes._open_link(QUrl('javascript:alert(1)'))
    notes._open_link(QUrl('#定位'))
    assert opened == ['https://github.com/itsVicOC/bilibili-downloader/blob/v0.9.0b1/docs/guide.md', 'https://example.com/notes']


def test_theme_switch_preserves_selection_and_scroll(qapp, qtbot):
    manager = ThemeManager(qapp, mode="light")
    notes = ReleaseNotesBrowser(replace(RELEASE, notes=MARKDOWN * 30))
    qtbot.addWidget(notes)
    notes.resize(540, 360)
    notes.show()
    qtbot.waitUntil(lambda: notes.verticalScrollBar().maximum() > 500)
    cursor = notes.textCursor()
    cursor.setPosition(3)
    cursor.setPosition(10, QTextCursor.KeepAnchor)
    notes.setTextCursor(cursor)
    notes.verticalScrollBar().setValue(240)
    selected = notes.textCursor().selectedText()
    manager.set_mode("dark")
    qtbot.waitUntil(lambda: notes._theme_key[0])
    assert notes.textCursor().selectedText() == selected
    assert notes.verticalScrollBar().value() == 240
    manager.deleteLater()


def test_markdown_copy_uses_rendered_text(qapp, qtbot):
    notes = ReleaseNotesBrowser(replace(RELEASE, notes="## 标题\n\n**内容**与 `命令`"))
    qtbot.addWidget(notes)
    notes.show()
    notes.setFocus()
    notes.selectAll()
    qtbot.keySequence(notes, QKeySequence.Copy)
    assert "标题" in qapp.clipboard().text() and "内容" in qapp.clipboard().text()
    assert "**" not in qapp.clipboard().text() and "`" not in qapp.clipboard().text()


@pytest.mark.parametrize("size", [(480, 360), (680, 520)])
def test_long_release_body_and_actions_fit(qtbot, size):
    body = Path('CHANGELOG.md').read_text(encoding='utf-8').split('\n## v', 2)[1]
    body += '\n\n```\n' + 'long-path/' * 300 + '\n```\n'
    dialog = UpdateDialog(replace(RELEASE, notes=body))
    qtbot.addWidget(dialog)
    dialog.resize(*size)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.notes.horizontalScrollBar().maximum() == 0
    assert dialog.notes.verticalScrollBar().maximum() > 0
    from PySide6.QtWidgets import QPushButton

    assert len(dialog.findChildren(QPushButton)) == 3
    for button in dialog.findChildren(QPushButton):
        assert button.isVisible() and dialog.rect().contains(button.geometry())


@pytest.mark.parametrize("notes", ["", "   ", "普通说明：中文、符号 & 路径。"])
def test_empty_and_plain_notes_remain_readable(qtbot, notes):
    browser = ReleaseNotesBrowser(replace(RELEASE, notes=notes))
    qtbot.addWidget(browser)
    assert browser.toPlainText() == (notes.strip() or "此版本未提供更新说明。")
    assert browser.isReadOnly()
    assert all(not fragment.charFormat().isImageFormat() for fragment in fragments(browser.document()))
