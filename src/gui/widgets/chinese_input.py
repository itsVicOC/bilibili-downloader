"""Shared QLineEdit subclass with Chinese context menu."""

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLineEdit, QMenu


class ChineseLineEdit(QLineEdit):
    """QLineEdit with Chinese context menu."""

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        undo_act = menu.addAction("撤销")
        redo_act = menu.addAction("重做")
        menu.addSeparator()
        cut_act = menu.addAction("剪切")
        copy_act = menu.addAction("复制")
        paste_act = menu.addAction("粘贴")
        delete_act = menu.addAction("删除")
        menu.addSeparator()
        select_all_act = menu.addAction("全选")

        undo_act.setEnabled(self.isUndoAvailable())
        redo_act.setEnabled(self.isRedoAvailable())
        has_sel = self.hasSelectedText()
        cut_act.setEnabled(has_sel)
        copy_act.setEnabled(has_sel)
        delete_act.setEnabled(has_sel)
        paste_act.setEnabled(bool(QGuiApplication.clipboard().text()))

        action = menu.exec(event.globalPos())
        if action == undo_act:
            self.undo()
        elif action == redo_act:
            self.redo()
        elif action == cut_act:
            self.cut()
        elif action == copy_act:
            self.copy()
        elif action == paste_act:
            self.paste()
        elif action == delete_act:
            self.del_()
        elif action == select_all_act:
            self.selectAll()
