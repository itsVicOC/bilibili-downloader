"""Application QSS stylesheet."""

DARK_STYLE = """
    * {
        font-family: "PingFang SC", Arial;
        font-size: 13px;
        color: #e3e7e7;
        outline: none;
    }

    QMainWindow, QDialog, #AppSurface {
        background-color: #151617;
    }

    QWidget {
        background-color: transparent;
    }

    #TopBar, #Panel {
        background-color: #1d2021;
        border: 1px solid #2d3334;
        border-radius: 8px;
    }

    #Toolbar {
        background-color: #191c1d;
        border: 1px solid #2d3334;
        border-radius: 8px;
    }

    #EmptyCover {
        background-color: #141616;
        border: 1px dashed #3a4142;
        border-radius: 8px;
    }

    QLabel {
        color: #e3e7e7;
        background-color: transparent;
    }

    QLabel#AppTitle {
        color: #f3f6f6;
        font-size: 18px;
        font-weight: 700;
    }

    QLabel#SectionTitle {
        color: #f3f6f6;
        font-weight: 700;
    }

    QLabel#Caption, QLabel#MetaLabel, QLabel#MutedLabel {
        color: #99a3a5;
    }

    QLabel#VideoTitle {
        color: #f3f6f6;
        font-size: 16px;
        font-weight: 700;
    }

    QLabel#StatusPill {
        color: #7fd7f7;
        background-color: rgba(0, 161, 214, 0.15);
        border: 1px solid rgba(0, 161, 214, 0.30);
        border-radius: 8px;
        padding: 3px 9px;
        font-weight: 600;
    }

    QLabel#WarningBanner {
        color: #f3c969;
        background-color: #2b2518;
        border: 1px solid #5b4825;
        border-radius: 8px;
        padding: 9px 11px;
    }

    QGroupBox {
        background-color: #1d2021;
        border: 1px solid #2d3334;
        border-radius: 8px;
        margin-top: 16px;
        padding: 18px 12px 12px 12px;
        color: #f3f6f6;
        font-weight: 700;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #7fd7f7;
    }

    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
        background-color: #131515;
        border: 1px solid #353b3d;
        border-radius: 7px;
        padding: 8px 11px;
        color: #eef2f2;
        selection-background-color: #00a1d6;
        selection-color: #ffffff;
    }

    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover {
        border-color: #4a5254;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
        background-color: #161a1a;
        border-color: #00a1d6;
    }

    QLineEdit:read-only {
        color: #b5bcbc;
        background-color: #171a1b;
    }

    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
        color: #6e787a;
        background-color: #171819;
        border-color: #292d2e;
    }

    QComboBox {
        background-color: #131515;
        border: 1px solid #353b3d;
        border-radius: 7px;
        padding: 7px 32px 7px 11px;
        min-width: 132px;
        color: #eef2f2;
    }

    QComboBox:hover {
        background-color: #161a1a;
        border-color: #4a5254;
    }

    QComboBox:focus, QComboBox:on {
        border-color: #00a1d6;
    }

    QComboBox::drop-down {
        width: 28px;
        border: none;
    }

    QComboBox::down-arrow {
        image: none;
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #99a3a5;
        margin-right: 9px;
    }

    QComboBox QAbstractItemView {
        background-color: #1b1e1f;
        color: #e3e7e7;
        border: 1px solid #353b3d;
        border-radius: 7px;
        padding: 5px 0;
        selection-background-color: #00a1d6;
        selection-color: #ffffff;
    }

    QComboBox QAbstractItemView::item {
        min-height: 30px;
        padding: 0 12px;
    }

    QPushButton {
        background-color: #262b2d;
        border: 1px solid #3b4446;
        border-radius: 7px;
        color: #e7ecec;
        padding: 8px 15px;
        font-weight: 600;
    }

    QPushButton:hover {
        background-color: #303638;
        border-color: #566164;
    }

    QPushButton:pressed {
        background-color: #1b1f20;
    }

    QPushButton:disabled {
        color: #707a7c;
        background-color: #1c1f20;
        border-color: #2d3334;
    }

    QPushButton#PrimaryButton {
        background-color: #00a1d6;
        border-color: #00a1d6;
        color: #ffffff;
    }

    QPushButton#PrimaryButton:hover {
        background-color: #16addf;
        border-color: #16addf;
    }

    QPushButton#PrimaryButton:pressed {
        background-color: #0089ba;
        border-color: #0089ba;
    }

    QPushButton#SubtleButton {
        background-color: transparent;
        border-color: #3b4446;
        color: #c9d1d1;
    }

    QPushButton#DangerButton {
        background-color: #40262d;
        border-color: #743847;
        color: #ffb7c5;
    }

    QPushButton#DangerButton:hover {
        background-color: #53313b;
        border-color: #914555;
    }

    QPushButton#SuccessButton {
        background-color: #17372e;
        border-color: #28624f;
        color: #a8ead6;
    }

    QCheckBox {
        spacing: 8px;
        color: #d4dbdb;
    }

    QCheckBox::indicator {
        width: 17px;
        height: 17px;
        border: 1px solid #465052;
        border-radius: 5px;
        background-color: #131515;
    }

    QCheckBox::indicator:hover {
        border-color: #00a1d6;
    }

    QCheckBox::indicator:checked {
        background-color: #00a1d6;
        border-color: #00a1d6;
    }

    QTableWidget {
        background-color: #191c1d;
        alternate-background-color: #1d2021;
        border: 1px solid #2d3334;
        border-radius: 8px;
        gridline-color: transparent;
        color: #e3e7e7;
        selection-background-color: rgba(0, 161, 214, 0.20);
    }

    QTableWidget::item {
        padding: 6px 8px;
        border-bottom: 1px solid #272c2d;
    }

    QTableWidget::item:selected {
        background-color: rgba(0, 161, 214, 0.20);
        color: #ffffff;
    }

    QHeaderView::section {
        background-color: #161819;
        color: #99a3a5;
        border: none;
        border-bottom: 1px solid #2d3334;
        padding: 9px 8px;
        font-weight: 700;
    }

    QProgressBar {
        background-color: #111313;
        border: 1px solid #303739;
        border-radius: 6px;
        color: #cbd3d3;
        height: 18px;
        text-align: center;
        font-size: 11px;
    }

    QProgressBar::chunk {
        background-color: #00a1d6;
        border-radius: 5px;
    }

    QProgressBar#ErrorProgress::chunk {
        background-color: #e05c73;
    }

    QMenuBar {
        background-color: #151617;
        color: #b5bcbc;
        border-bottom: 1px solid #272c2d;
    }

    QMenuBar::item {
        padding: 6px 10px;
        margin: 2px;
        border-radius: 5px;
    }

    QMenuBar::item:selected {
        background-color: #262b2d;
        color: #ffffff;
    }

    QMenu {
        background-color: #1d2021;
        border: 1px solid #353b3d;
        border-radius: 8px;
        padding: 6px;
    }

    QMenu::item {
        padding: 7px 28px 7px 12px;
        border-radius: 6px;
    }

    QMenu::item:selected {
        background-color: #2a3032;
    }

    QMenu::separator {
        height: 1px;
        background-color: #353b3d;
        margin: 5px 8px;
    }

    QStatusBar {
        background-color: #151617;
        color: #848f91;
        border-top: 1px solid #272c2d;
    }

    QTabWidget::pane {
        background-color: #1d2021;
        border: 1px solid #2d3334;
        border-radius: 8px;
    }

    QTabBar::tab {
        background-color: #171919;
        border: 1px solid #2d3334;
        border-bottom: none;
        border-top-left-radius: 7px;
        border-top-right-radius: 7px;
        color: #99a3a5;
        padding: 8px 18px;
    }

    QTabBar::tab:selected {
        background-color: #1d2021;
        border-color: #40494b;
        color: #ffffff;
    }

    QTabBar::tab:hover:!selected {
        background-color: #222728;
        color: #e3e7e7;
    }

    QMessageBox {
        background-color: #151617;
    }

    QMessageBox QPushButton {
        min-width: 86px;
    }
"""
