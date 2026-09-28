"""Popup usability across themes, including keyboard and long-label handling."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.widgets.combo_box import ComboBox


@pytest.fixture(params=[True, False], ids=["dark", "light"])
def dropdown_theme(qapp, request):
    previous = qapp.styleSheet(), qapp.property("darkTheme")
    qapp.setProperty("darkTheme", request.param)
    qapp.setStyleSheet(load_stylesheet(request.param))
    yield
    qapp.setProperty("darkTheme", previous[1])
    qapp.setStyleSheet(previous[0])


def test_keyboard_selects_enabled_data_and_escape_cancels(qtbot, dropdown_theme):
    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItem("自动选择", 0)
    combo.addItem("不可用的画质", 80)
    combo.model().item(1).setEnabled(False)
    combo.addItem("1080P 高清", 120)
    activated = []
    combo.activated.connect(activated.append)
    combo.resize(240, 40)
    combo.show()
    combo.showPopup()
    qtbot.keyClick(combo.view(), Qt.Key_Down)
    qtbot.keyClick(combo.view(), Qt.Key_Return)
    assert combo.currentData() == 120
    assert activated == [2]
    assert not combo.view().isVisible()
    assert not combo.property("popupOpen")
    assert combo.toolTip() == "1080P 高清"

    combo.showPopup()
    qtbot.keyClick(combo.view(), Qt.Key_Up)
    qtbot.keyClick(combo.view(), Qt.Key_Escape)
    assert combo.currentData() == 120
    assert activated == [2]
    assert not combo.view().isVisible()
    assert not combo.property("popupOpen")
    combo.setEnabled(False)
    combo.showPopup()
    assert not combo.view().isVisible()


def test_long_popup_fits_screen_scrolls_and_keeps_selection(qtbot, dropdown_theme):
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    combo = ComboBox()
    combo.setFixedWidth(228)
    for number in range(30):
        combo.addItem(f"P{number + 1} · " + "非常长的作品章节标题" * 8, number)
    combo.setCurrentIndex(15)
    layout.addWidget(combo)
    available = QApplication.primaryScreen().availableGeometry()
    host.adjustSize()
    host.move(available.right() - host.width(), available.bottom() - host.height())
    host.show()
    QApplication.processEvents()
    combo.showPopup()
    QApplication.processEvents()
    view = combo.view()
    popup = view.window()
    assert available.contains(popup.frameGeometry())
    assert popup.width() <= combo.width() + 20
    assert view.horizontalScrollBar().maximum() == 0
    assert view.verticalScrollBar().maximum() > 0
    assert view.visualRect(view.currentIndex()).height() >= 40
    assert view.viewport().rect().intersects(view.visualRect(view.currentIndex()))
    assert combo.currentData() == 15
    assert combo.toolTip() == combo.currentText()
    # Exercise the actual delegate and its current-item checkmark in each theme.
    assert not popup.grab().isNull()
    combo.hidePopup()
