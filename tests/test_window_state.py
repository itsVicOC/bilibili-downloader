"""Placement survives fresh processes without touching business settings."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QApplication, QWidget

from bilibili_downloader.gui.window_state import (
    WindowStateStore,
    choose_screen,
    fit_rect,
)


def flush():
    for _ in range(5):
        QApplication.processEvents()


def test_screen_choice_negative_coordinates_and_removed_monitor(qapp, monkeypatch):
    left = SimpleNamespace(name=lambda: "left", availableGeometry=lambda: QRect(-1600, 0, 1600, 900))
    main = SimpleNamespace(name=lambda: "main", availableGeometry=lambda: QRect(0, 0, 1920, 1040))
    monkeypatch.setattr("bilibili_downloader.gui.window_state.QGuiApplication.primaryScreen", lambda: main)
    assert choose_screen([left, main], "left", QRect(-1200, 20, 1000, 700)) is left
    assert choose_screen([main], "left", QRect(-1200, 20, 1000, 700)) is main
    rect = fit_rect(QRect(-4000, -400, 1320, 860), QRect(-960, 0, 960, 540), QSize(4, 24))
    assert QRect(-960, 0, 960, 540).contains(QRect(rect.topLeft(), rect.size() + QSize(4, 24)))


@pytest.mark.parametrize("content", ["{", "[]", '{"version": 9}', '{"version": 1, "normal_rect": [0,0,-1,2]}'])
def test_invalid_state_uses_visible_default(qtbot, tmp_path, content):
    path = tmp_path / "ui-state.json"
    path.write_text(content)
    window = QWidget()
    qtbot.addWidget(window)
    store = WindowStateStore(window, path)
    store.show_initial()
    flush()
    assert window.isVisible() and not window.isMinimized()
    assert window.screen().availableGeometry().contains(window.frameGeometry())


def test_normal_maximized_minimized_and_hidden_do_not_lose_normal_rect(qtbot, tmp_path):
    window = QWidget()
    qtbot.addWidget(window)
    path = tmp_path / "ui-state.json"
    store = WindowStateStore(window, path)
    store.show_initial()
    flush()
    window.setMinimumSize(1, 1)
    window.setGeometry(40, 50, 600, 400)
    flush()
    store.flush()
    normal = json.loads(path.read_text())["normal_rect"]
    window.showMaximized()
    flush()
    store.flush()
    assert json.loads(path.read_text())["maximized"]
    assert json.loads(path.read_text())["normal_rect"] == normal
    window.showMinimized()
    flush()
    window.hide()
    store.flush()
    assert json.loads(path.read_text())["normal_rect"] == normal
    assert json.loads(path.read_text())["maximized"]


def test_failed_atomic_save_keeps_previous_record_and_does_not_raise(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "ui-state.json"
    window = QWidget()
    qtbot.addWidget(window)
    store = WindowStateStore(window, path)
    store.show_initial()
    flush()
    store.flush()
    before = path.read_bytes()
    monkeypatch.setattr("bilibili_downloader.gui.window_state.atomic_json", lambda *_: (_ for _ in ()).throw(OSError("read only")))
    window.setMinimumSize(1, 1)
    window.resize(600, 400)
    store.flush()
    assert path.read_bytes() == before
    assert store._warned and not store._timer.isActive()


@pytest.mark.parametrize("maximized", [False, True])
def test_cold_process_restart_restores_placement(tmp_path, maximized):
    # A new QApplication and interpreter ensure this is disk persistence,
    # rather than an in-memory Qt/lifecycle restoration.
    script = '''
import json, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget
from bilibili_downloader.gui.window_state import WindowStateStore
app = QApplication([])
window = QWidget()
store = WindowStateStore(window, Path(sys.argv[1]))
store.show_initial()
for _ in range(5): app.processEvents()
if sys.argv[2] == "save":
    window.setMinimumSize(1,1)
    window.setGeometry(40,50,600,400)
    for _ in range(5): app.processEvents()
    if sys.argv[3] == "True": window.showMaximized()
    for _ in range(5): app.processEvents()
    store.flush()
else:
    print(json.dumps(dict(maximized=window.isMaximized(), normal=list(store._normal.getRect()), visible=window.isVisible())))
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    path = tmp_path / "ui-state.json"
    subprocess.run([sys.executable, "-c", script, str(path), "save", str(maximized)], env=env, check=True, capture_output=True)
    result = subprocess.run([sys.executable, "-c", script, str(path), "restore", str(maximized)], env=env, check=True, capture_output=True, text=True)
    state = json.loads(result.stdout)
    # The nominal minimum is restored when the work area supports it.
    assert state["visible"] and state["maximized"] == maximized
    assert 0 <= state["normal"][0] <= 40
    assert state["normal"][1] == 50
    assert state["normal"][2] >= 600 and state["normal"][3] >= 400
