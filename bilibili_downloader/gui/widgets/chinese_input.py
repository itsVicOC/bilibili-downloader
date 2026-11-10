"""Shared QLineEdit subclass with Chinese context menu."""

from PySide6.QtWidgets import QLineEdit

from bilibili_downloader.gui.widgets.text_menu import text_context_menu


class ChineseLineEdit(QLineEdit):
    """QLineEdit with Chinese context menu."""

    def createStandardContextMenu(self):
        return text_context_menu(self)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.exec(event.globalPos())
        menu.deleteLater()
