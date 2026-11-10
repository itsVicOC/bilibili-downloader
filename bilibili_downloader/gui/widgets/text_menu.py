"""Consistent editing actions without replacing Qt text or IME handling."""

from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import QLineEdit

from bilibili_downloader.gui.widgets.popup_menu import PopupMenu


def text_context_menu(editor):
    menu = PopupMenu(editor)
    readonly = editor.isReadOnly()
    if isinstance(editor, QLineEdit):
        selected = editor.hasSelectedText()
        undo, redo = editor.isUndoAvailable(), editor.isRedoAvailable()
        copyable = editor.echoMode() == QLineEdit.Normal
        nonempty = bool(editor.text())
        delete = editor.del_
    else:
        selected = editor.textCursor().hasSelection()
        undo, redo = editor.document().isUndoAvailable(), editor.document().isRedoAvailable()
        copyable = True
        nonempty = not editor.document().isEmpty()
        def delete():
            cursor = editor.textCursor()
            cursor.removeSelectedText()
            editor.setTextCursor(cursor)
    entries = (
        ("撤销", editor.undo, not readonly and undo, QKeySequence.Undo),
        ("重做", editor.redo, not readonly and redo, QKeySequence.Redo),
        None,
        ("剪切", editor.cut, not readonly and selected and copyable, QKeySequence.Cut),
        ("复制", editor.copy, selected and copyable, QKeySequence.Copy),
        ("粘贴", editor.paste, not readonly and bool(QGuiApplication.clipboard().text()), QKeySequence.Paste),
        ("删除", delete, not readonly and selected, None),
        None,
        ("全选", editor.selectAll, nonempty, QKeySequence.SelectAll),
    )
    for entry in entries:
        if entry is None:
            menu.addSeparator()
            continue
        label, callback, enabled, shortcut = entry
        action = menu.addAction(label, callback)
        action.setEnabled(enabled)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
    if hasattr(editor, "_copy_value"):
        menu.addSeparator()
        menu.addAction("复制完整路径", lambda: QGuiApplication.clipboard().setText(editor._copy_value))
    return menu
