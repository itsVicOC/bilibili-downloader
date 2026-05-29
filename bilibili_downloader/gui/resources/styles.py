"""Bilibili dark theme QSS stylesheet."""

# 配色: 主色 #00A1D6(哔哩蓝), 辅色 #FB7299(哔哩粉), 深色背景 #212121
DARK_STYLE = """
    QMainWindow, QWidget {
        background-color: #212121;
        color: #e0e0e0;
        font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
        font-size: 13px;
    }

    /* ── GroupBox ── */
    QGroupBox {
        font-weight: bold;
        border: 1px solid #333333;
        border-radius: 8px;
        margin-top: 1.2ex;
        padding-top: 14px;
        background-color: #262626;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: #00A1D6;
        font-size: 13px;
    }

    /* ── Input Fields ── */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        padding: 8px 12px;
        color: #e0e0e0;
        font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
        font-size: 13px;
        selection-background-color: #00A1D6;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid #00A1D6;
        background-color: #2d2d2d;
    }
    QLineEdit:disabled, QTextEdit:disabled {
        background-color: #222222;
        color: #666;
    }

    /* ── ComboBox ── */
    QComboBox {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        padding: 7px 32px 7px 12px;
        color: #e0e0e0;
        min-width: 140px;
        font-size: 13px;
    }
    QComboBox:hover {
        border-color: #00A1D6;
        background-color: #2d2d2d;
    }
    QComboBox:disabled {
        background-color: #222222;
        color: #555;
        border-color: #303030;
    }
    QComboBox::drop-down {
        border: none;
        width: 28px;
        border-left: 1px solid #3a3a3a;
    }
    QComboBox:hover::drop-down {
        border-left-color: #00A1D6;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #999;
        margin-right: 6px;
    }
    QComboBox:pressed::down-arrow {
        border-top-color: #00A1D6;
    }
    QComboBox:on {
        border-color: #00A1D6;
    }
    QComboBox QAbstractItemView {
        background-color: #2a2a2a;
        color: #e0e0e0;
        border: 1px solid #404040;
        border-radius: 6px;
        selection-background-color: #00A1D6;
        selection-color: white;
        outline: none;
        padding: 4px 0;
        font-size: 13px;
    }
    QComboBox QAbstractItemView::item {
        min-height: 32px;
        padding: 0 12px;
        border: none;
    }
    QComboBox QAbstractItemView::item:hover {
        background-color: rgba(0, 161, 214, 0.2);
    }
    QComboBox QAbstractItemView::item:selected {
        background-color: #00A1D6;
        color: white;
    }

    /* ── Table ── */
    QTableWidget {
        background-color: #252525;
        gridline-color: #2e2e2e;
        border: 1px solid #333333;
        border-radius: 6px;
        color: #e0e0e0;
        alternate-background-color: #2a2a2a;
    }
    QTableWidget::item {
        padding: 4px;
    }
    QTableWidget::item:selected {
        background-color: rgba(0, 161, 214, 0.3);
        color: white;
    }
    QHeaderView::section {
        background-color: #2a2a2a;
        color: #00A1D6;
        font-weight: bold;
        border: none;
        border-bottom: 1px solid #333333;
        padding: 8px;
    }

    /* ── Buttons ── */
    QPushButton {
        background-color: #333333;
        border: 1px solid #404040;
        border-radius: 6px;
        padding: 7px 18px;
        color: #e0e0e0;
        font-size: 13px;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #3d3d3d;
        border: 1px solid #00A1D6;
    }
    QPushButton:pressed {
        background-color: #1d1d1d;
        padding-top: 8px;
        padding-bottom: 6px;
    }
    QPushButton:disabled {
        background-color: #262626;
        color: #555;
        border-color: #303030;
    }

    /* Primary / accent buttons */
    QPushButton#PrimaryButton {
        background-color: #00A1D6;
        border: 1px solid #00A1D6;
        color: white;
        font-weight: bold;
    }
    QPushButton#PrimaryButton:hover {
        background-color: #23a2d9;
    }
    QPushButton#PrimaryButton:pressed {
        background-color: #0088b8;
        padding-top: 9px;
        padding-bottom: 7px;
    }
    QPushButton#PrimaryButton:disabled {
        background-color: #1a4a5c;
        border-color: #1a4a5c;
        color: #557788;
    }

    QPushButton#DangerButton {
        background-color: #d32f2f;
        border: 1px solid #d32f2f;
        color: white;
    }
    QPushButton#DangerButton:hover {
        background-color: #e03e3e;
    }

    QPushButton#SuccessButton {
        background-color: #2e7d32;
        border: 1px solid #2e7d32;
        color: white;
    }
    QPushButton#SuccessButton:hover {
        background-color: #3a8f3e;
    }

    /* ── Menu Bar ── */
    QMenuBar {
        background-color: #212121;
        color: #e0e0e0;
        border-bottom: 1px solid #333333;
    }
    QMenuBar::item {
        padding: 6px 10px;
        border-radius: 4px;
        margin: 2px;
    }
    QMenuBar::item:selected {
        background-color: rgba(0, 161, 214, 0.3);
    }
    QMenu {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #404040;
        border-radius: 6px;
        padding: 6px;
    }
    QMenu::item {
        padding: 6px 24px 6px 12px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: rgba(0, 161, 214, 0.3);
    }
    QMenu::separator {
        height: 1px;
        background-color: #404040;
        margin: 4px 8px;
    }

    /* ── Status Bar ── */
    QStatusBar {
        background-color: #212121;
        color: #777;
        border-top: 1px solid #333333;
    }

    /* ── Progress Bar ── */
    QProgressBar {
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        text-align: center;
        color: #e0e0e0;
        background-color: #333333;
        font-size: 11px;
        height: 18px;
    }
    QProgressBar::chunk {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #00A1D6, stop:1 #0088b8);
        border-radius: 5px;
    }

    /* ── CheckBox ── */
    QCheckBox {
        color: #e0e0e0;
        spacing: 6px;
        padding: 2px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 2px solid #404040;
        border-radius: 4px;
        background-color: #2a2a2a;
    }
    QCheckBox::indicator:hover {
        border-color: #00A1D6;
    }
    QCheckBox::indicator:checked {
        background-color: #00A1D6;
        border-color: #00A1D6;
    }

    /* ── Tab Widget ── */
    QTabWidget::pane {
        border: 1px solid #333333;
        border-radius: 6px;
        background-color: #262626;
    }
    QTabBar::tab {
        background-color: #2a2a2a;
        color: #888;
        padding: 8px 24px;
        border: 1px solid #333333;
        border-bottom: none;
        border-radius: 6px 6px 0 0;
    }
    QTabBar::tab:selected {
        background-color: #00A1D6;
        color: white;
    }
    QTabBar::tab:hover:!selected {
        color: #00A1D6;
        background-color: #303030;
    }

    /* ── Label ── */
    QLabel { color: #e0e0e0; }

    /* ── Dialog ── */
    QMessageBox { background-color: #212121; }
    QMessageBox QLabel { color: #e0e0e0; }
    QMessageBox QPushButton { min-width: 80px; }
"""
