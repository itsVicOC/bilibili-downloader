"""Popup usability across themes, including keyboard and long-label handling."""

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.widgets.combo_box import ComboBox, popup_geometry


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
    qtbot.waitUntil(lambda: not combo.view().isVisible())
    assert combo.currentData() == 120
    assert activated == [2]
    assert not combo.view().isVisible()
    assert not combo.property("popupOpen")
    assert combo.toolTip() == "1080P 高清"

    combo.showPopup()
    qtbot.keyClick(combo.view(), Qt.Key_Up)
    qtbot.keyClick(combo.view(), Qt.Key_Escape)
    qtbot.waitUntil(lambda: not combo.view().isVisible())
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
    anchor = QRect(combo.mapToGlobal(QPoint()), combo.size())
    assert available.contains(popup.frameGeometry())
    assert popup.width() == combo.width()
    assert not popup.geometry().intersects(anchor)
    assert popup.geometry().bottom() == anchor.top() - 5
    assert view.horizontalScrollBar().maximum() == 0
    assert view.verticalScrollBar().maximum() > 0
    assert view.visualRect(view.currentIndex()).height() >= 40
    assert view.viewport().rect().intersects(view.visualRect(view.currentIndex()))
    assert combo.currentData() == 15
    assert combo.toolTip() == combo.currentText()
    # Exercise the actual delegate and its current-item checkmark in each theme.
    assert not popup.grab().isNull()
    combo.hidePopup()


def test_popup_starts_below_field_with_equal_width(qtbot, dropdown_theme):
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    combo = ComboBox()
    combo.addItems(["原画", "超清"])
    layout.addWidget(combo)
    available = QApplication.primaryScreen().availableGeometry()
    host.resize(360, 100)
    host.move(available.topLeft() + QPoint(40, 40))
    host.show()
    QApplication.processEvents()
    combo.showPopup()
    QApplication.processEvents()
    anchor = QRect(combo.mapToGlobal(QPoint()), combo.size())
    popup = combo.view().window()
    assert popup.geometry().left() == anchor.left()
    assert popup.width() == combo.width()
    assert popup.geometry().top() == anchor.bottom() + 5
    combo.hidePopup()


def test_mouse_selection_uses_repositioned_rows(qtbot, dropdown_theme):
    combo = ComboBox()
    qtbot.addWidget(combo)
    for index in range(10):
        combo.addItem(f"选项 {index + 1}", index)
    combo.resize(240, 40)
    combo.show()
    combo.showPopup()
    # Qt protects against the opening click's release; native close is animated.
    qtbot.wait(200)
    view = combo.view()
    target = view.model().index(3, 0)
    qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(target).center())
    qtbot.waitUntil(lambda: not view.isVisible())
    assert combo.currentData() == 3
    assert not combo.property("popupOpen")


@pytest.mark.parametrize(
    "screen, anchor, preferred, below",
    [
        (QRect(0, 24, 1280, 800), QRect(500, 120, 240, 40), QSize(240, 334), True),
        (QRect(-1280, 24, 1280, 800), QRect(-450, 650, 260, 40), QSize(260, 334), False),
        (QRect(0, 0, 400, 300), QRect(100, 120, 228, 40), QSize(228, 334), True),
        (QRect(0, 0, 400, 300), QRect(300, 160, 228, 40), QSize(228, 334), False),
        (QRect(0, 0, 400, 300), QRect(0, 100, 640, 40), QSize(640, 334), True),
    ],
)
def test_popup_uses_available_screen_without_covering_field(
    screen, anchor, preferred, below
):
    popup = popup_geometry(anchor, preferred, screen)
    assert screen.contains(popup)
    assert not anchor.intersects(popup)
    assert popup.width() == min(anchor.width(), screen.width())
    if below:
        assert popup.top() == anchor.bottom() + 5
    else:
        assert popup.bottom() == anchor.top() - 5
