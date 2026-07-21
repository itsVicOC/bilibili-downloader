"""Application QSS stylesheet."""

DARK_STYLE = """
    * {
        font-family: "PingFang SC", "Microsoft YaHei", Arial;
        font-size: 13px;
        letter-spacing: 0px;
        color: #f4f1f7;
        outline: none;
    }

    QMainWindow, QDialog, #AppSurface {
        background-color: #15151a;
    }

    QWidget {
        background-color: transparent;
    }

    #Workspace {
        background-color: #18181e;
    }

    #Sidebar {
        background-color: #101014;
        border-right: 1px solid #2a2931;
    }

    QLabel#BrandIcon {
        background-color: #25212c;
        border: 1px solid #42394e;
        border-radius: 8px;
        padding: 4px;
    }

    QLabel#BrandTitle {
        color: #ffffff;
        font-size: 20px;
        font-weight: 800;
    }

    QLabel#SidebarCaption {
        color: #8f8998;
        font-size: 11px;
    }

    QLabel#NavSection {
        color: #66616d;
        font-size: 10px;
        font-weight: 700;
        padding: 0 8px 5px 8px;
    }

    QPushButton#NavButton, QPushButton#NavButtonActive {
        min-height: 38px;
        border: none;
        border-radius: 7px;
        padding: 0 10px;
        text-align: left;
        color: #aaa5b0;
        font-weight: 600;
        background-color: transparent;
    }

    QPushButton#NavButton:hover {
        color: #ffffff;
        background-color: #1d1c23;
    }

    QPushButton#NavButtonActive {
        color: #ffffff;
        background-color: #2c2230;
        border-left: 3px solid #ff5fa2;
    }

    #MascotCard {
        background-color: #1c1b22;
        border: 1px solid #33303b;
        border-radius: 8px;
    }

    QLabel#MascotTitle {
        color: #ffffff;
        font-weight: 700;
    }

    QPushButton#SidebarAction {
        min-height: 40px;
        color: #f5f1f7;
        background-color: #242129;
        border: 1px solid #3b3641;
        border-radius: 7px;
        font-weight: 700;
    }

    QPushButton#SidebarAction:hover {
        background-color: #302a35;
        border-color: #ff5fa2;
    }

    QLabel#PageTitle {
        color: #ffffff;
        font-size: 23px;
        font-weight: 800;
    }

    QLabel#DialogTitle {
        color: #ffffff;
        font-size: 22px;
        font-weight: 800;
    }

    QLabel#DialogCaption {
        color: #96909e;
        margin-bottom: 4px;
    }

    #DialogPanel {
        background-color: #202027;
        border: 1px solid #36343d;
        border-radius: 8px;
    }

    QLabel#Caption, QLabel#MetaLabel, QLabel#MutedLabel {
        color: #96909e;
    }

    QPushButton#GhostButton {
        min-width: 150px;
        min-height: 34px;
        padding: 0 14px;
        color: #b9b4c0;
        background-color: #202027;
        border: 1px solid #35343d;
        border-radius: 7px;
    }

    QPushButton#GhostButton:hover {
        color: #ffffff;
        border-color: #62d5ff;
    }

    #HeroPanel {
        border: 1px solid #44354e;
        border-radius: 8px;
    }

    QLabel#HeroEyebrow {
        color: #8be4ff;
        font-size: 10px;
        font-weight: 800;
    }

    QLabel#HeroTitle {
        color: #ffffff;
        font-size: 27px;
        font-weight: 800;
    }

    QLineEdit#UrlInput {
        min-height: 28px;
        padding: 10px 15px;
        color: #ffffff;
        background-color: rgba(13, 12, 22, 225);
        border: 1px solid rgba(255, 255, 255, 48);
        border-radius: 8px;
        selection-background-color: #ff5fa2;
    }

    QLineEdit#UrlInput:hover {
        border-color: rgba(255, 255, 255, 90);
    }

    QLineEdit#UrlInput:focus {
        background-color: rgba(13, 12, 22, 242);
        border-color: #62d5ff;
    }

    QPushButton#HeroButton {
        min-width: 132px;
        min-height: 48px;
        padding: 0 18px;
        color: #171219;
        background-color: #ff79b3;
        border: 1px solid #ff9bc5;
        border-radius: 8px;
        font-weight: 800;
    }

    QPushButton#HeroButton:hover {
        background-color: #ff95c1;
        border-color: #ffd0e3;
    }

    QPushButton#HeroButton:pressed {
        background-color: #e75391;
    }

    QPushButton#HeroButton:disabled {
        color: #8f8190;
        background-color: #493641;
        border-color: #5f4655;
    }

    #Panel, #ControlPanel {
        background-color: #202027;
        border: 1px solid #34343d;
        border-radius: 8px;
    }

    QLabel#SectionTitle {
        color: #ffffff;
        font-size: 15px;
        font-weight: 800;
    }

    QLabel#FieldLabel {
        color: #b6b0bd;
        font-size: 11px;
        font-weight: 700;
    }

    QLabel#VideoTitle {
        color: #ffffff;
        font-size: 18px;
        font-weight: 800;
    }

    QLabel#StatusPill, QLabel#SuccessPill {
        color: #baf2ff;
        background-color: #18333a;
        border: 1px solid #285b66;
        border-radius: 8px;
        padding: 3px 9px;
        font-size: 11px;
        font-weight: 700;
    }

    QLabel#InfoChip {
        color: #d0cad5;
        background-color: #2a2931;
        border: 1px solid #3d3a45;
        border-radius: 7px;
        padding: 5px 9px;
        font-size: 11px;
    }

    QLabel#EmptyCover {
        color: #77717f;
        background-color: #17171c;
        border: 1px dashed #46424d;
        border-radius: 8px;
    }

    QLabel#WarningBanner {
        color: #ffe099;
        background-color: #352d1d;
        border: 1px solid #675330;
        border-radius: 8px;
        padding: 9px 11px;
    }

    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
        min-height: 24px;
        padding: 7px 10px;
        color: #f5f1f7;
        background-color: #17171c;
        border: 1px solid #3a3942;
        border-radius: 7px;
        selection-background-color: #ff5fa2;
        selection-color: #ffffff;
    }

    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover {
        border-color: #55515d;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
        border-color: #62d5ff;
        background-color: #1b1b21;
    }

    QLineEdit:read-only {
        color: #aaa5b0;
        background-color: #1b1b20;
    }

    QComboBox {
        min-width: 138px;
        min-height: 24px;
        padding: 7px 30px 7px 10px;
        color: #f5f1f7;
        background-color: #17171c;
        border: 1px solid #3a3942;
        border-radius: 7px;
    }

    QComboBox:hover, QComboBox:on {
        border-color: #62d5ff;
        background-color: #1c1c22;
    }

    QComboBox::drop-down {
        width: 28px;
        border: none;
    }

    QComboBox QAbstractItemView {
        color: #f5f1f7;
        background-color: #222229;
        border: 1px solid #44414b;
        border-radius: 7px;
        padding: 5px 0;
        selection-background-color: #473143;
        selection-color: #ffffff;
    }

    QPushButton {
        min-height: 32px;
        padding: 0 14px;
        color: #eeebf0;
        background-color: #2a2931;
        border: 1px solid #403e48;
        border-radius: 7px;
        font-weight: 700;
    }

    QPushButton:hover {
        background-color: #35333c;
        border-color: #5d5865;
    }

    QPushButton:pressed {
        background-color: #222127;
    }

    QPushButton:disabled {
        color: #77727d;
        background-color: #222127;
        border-color: #33313a;
    }

    QPushButton#PrimaryButton, QPushButton#DownloadButton {
        color: #181319;
        background-color: #ff79b3;
        border-color: #ff94bf;
    }

    QPushButton#PrimaryButton:hover, QPushButton#DownloadButton:hover {
        background-color: #ff96c2;
        border-color: #ffc3da;
    }

    QPushButton#DownloadButton {
        min-height: 36px;
        margin-top: 2px;
        font-weight: 800;
    }

    QPushButton#SecondaryButton, QPushButton#SubtleButton {
        color: #c8c2ce;
        background-color: transparent;
        border-color: #45424c;
    }

    QPushButton#SecondaryButton:hover, QPushButton#SubtleButton:hover {
        color: #ffffff;
        background-color: #2a2931;
        border-color: #62d5ff;
    }

    QPushButton#DangerButton {
        color: #ffc1cc;
        background-color: #422730;
        border-color: #70404d;
    }

    QPushButton#SuccessButton {
        color: #c0f5df;
        background-color: #1f3a31;
        border-color: #376451;
    }

    QCheckBox {
        spacing: 8px;
        color: #d1ccd5;
    }

    QCheckBox::indicator {
        width: 17px;
        height: 17px;
        background-color: #17171c;
        border: 1px solid #4b4852;
        border-radius: 5px;
    }

    QCheckBox::indicator:hover {
        border-color: #62d5ff;
    }

    QCheckBox::indicator:checked {
        background-color: #ff5fa2;
        border-color: #ff7db3;
    }

    QTableWidget {
        min-height: 120px;
        color: #eeebf0;
        background-color: #202027;
        alternate-background-color: #24242b;
        border: 1px solid #34343d;
        border-radius: 8px;
        gridline-color: transparent;
        selection-background-color: #342b38;
    }

    QTableWidget::item {
        padding: 6px 8px;
        border-bottom: 1px solid #302f37;
    }

    QHeaderView::section {
        padding: 9px 8px;
        color: #8f8998;
        background-color: #1a1a20;
        border: none;
        border-bottom: 1px solid #34343d;
        font-size: 11px;
        font-weight: 700;
    }

    QProgressBar {
        height: 18px;
        color: #d7d1db;
        background-color: #15151a;
        border: 1px solid #34323b;
        border-radius: 6px;
        text-align: center;
        font-size: 10px;
    }

    QProgressBar::chunk {
        background-color: #62d5ff;
        border-radius: 5px;
    }

    QProgressBar#ErrorProgress::chunk {
        background-color: #ff6685;
    }

    QStatusBar {
        color: #85808b;
        background-color: #101014;
        border-top: 1px solid #2a2931;
    }

    QTabWidget::pane, QGroupBox {
        background-color: #202027;
        border: 1px solid #36343d;
        border-radius: 8px;
    }

    QTabBar::tab {
        padding: 8px 16px;
        color: #96909e;
        background-color: #1a1a20;
        border: 1px solid #34323b;
        border-bottom: none;
        border-top-left-radius: 7px;
        border-top-right-radius: 7px;
    }

    QTabBar::tab:selected {
        color: #ffffff;
        background-color: #29272f;
        border-color: #554650;
    }

    QMenu {
        color: #f4f1f7;
        background-color: #222229;
        border: 1px solid #44414b;
        border-radius: 8px;
        padding: 5px;
    }

    QMenu::item {
        padding: 7px 28px 7px 12px;
        border-radius: 6px;
    }

    QMenu::item:selected {
        background-color: #3b2c3a;
    }
"""


LIGHT_OVERRIDES = """
    * {
        color: #29242f;
    }

    QMainWindow, QDialog, #AppSurface {
        background-color: #f5f5f8;
    }

    #Workspace {
        background-color: #f7f7fa;
    }

    #Sidebar {
        background-color: #ffffff;
        border-right: 1px solid #e1dee5;
    }

    QLabel#BrandIcon {
        background-color: #f2edf6;
        border-color: #d9d0e0;
    }

    QLabel#BrandTitle, QLabel#PageTitle, QLabel#DialogTitle,
    QLabel#MascotTitle, QLabel#SectionTitle, QLabel#VideoTitle {
        color: #211d27;
    }

    QLabel#SidebarCaption, QLabel#DialogCaption,
    QLabel#Caption, QLabel#MetaLabel, QLabel#MutedLabel {
        color: #756e7d;
    }

    QLabel#NavSection {
        color: #99929f;
    }

    QPushButton#NavButton, QPushButton#NavButtonActive {
        color: #625b69;
    }

    QPushButton#NavButton:hover {
        color: #211d27;
        background-color: #f2eff4;
    }

    QPushButton#NavButtonActive {
        color: #211d27;
        background-color: #fff0f6;
        border-left-color: #ef4f91;
    }

    #MascotCard, #DialogPanel {
        background-color: #faf8fb;
        border-color: #e1dce5;
    }

    QPushButton#SidebarAction {
        color: #332d39;
        background-color: #f3eff5;
        border-color: #ddd6e1;
    }

    QPushButton#SidebarAction:hover {
        background-color: #fff0f6;
        border-color: #ef4f91;
    }

    QPushButton#GhostButton {
        color: #514a58;
        background-color: #ffffff;
        border-color: #ddd9e1;
    }

    QPushButton#GhostButton:hover {
        color: #211d27;
        border-color: #159fc5;
    }

    #HeroPanel {
        border-color: #d9cfdf;
    }

    QLabel#HeroEyebrow {
        color: #007f9f;
    }

    QLabel#HeroTitle {
        color: #211d27;
    }

    QLineEdit#UrlInput {
        color: #211d27;
        background-color: rgba(255, 255, 255, 235);
        border-color: rgba(65, 49, 76, 55);
        selection-background-color: #ef4f91;
    }

    QLineEdit#UrlInput:hover {
        border-color: rgba(65, 49, 76, 95);
    }

    QLineEdit#UrlInput:focus {
        color: #211d27;
        background-color: rgba(255, 255, 255, 250);
        border-color: #159fc5;
    }

    QPushButton#HeroButton, QPushButton#PrimaryButton,
    QPushButton#DownloadButton {
        color: #251820;
        background-color: #ff79b3;
        border-color: #ef5d9b;
    }

    QPushButton#HeroButton:hover, QPushButton#PrimaryButton:hover,
    QPushButton#DownloadButton:hover {
        color: #251820;
        background-color: #ff91c1;
        border-color: #e34c8b;
    }

    QPushButton#HeroButton:disabled {
        color: #9a8791;
        background-color: #ead9e1;
        border-color: #ddcbd4;
    }

    #Panel, #ControlPanel {
        background-color: #ffffff;
        border-color: #e0dde4;
    }

    QLabel#FieldLabel {
        color: #68616e;
    }

    QLabel#StatusPill, QLabel#SuccessPill {
        color: #17677a;
        background-color: #e8f8fc;
        border-color: #b7e3ed;
    }

    QLabel#InfoChip {
        color: #554e5c;
        background-color: #f5f3f7;
        border-color: #e0dce4;
    }

    QLabel#EmptyCover {
        color: #8d8693;
        background-color: #faf9fb;
        border-color: #d9d4de;
    }

    QLabel#WarningBanner {
        color: #755519;
        background-color: #fff7df;
        border-color: #ead69b;
    }

    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
        color: #29242f;
        background-color: #ffffff;
        border-color: #d8d4dc;
        selection-background-color: #ef4f91;
    }

    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover {
        border-color: #b8b1bd;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
        color: #29242f;
        background-color: #ffffff;
        border-color: #159fc5;
    }

    QLineEdit:read-only {
        color: #726b78;
        background-color: #f3f1f5;
    }

    QComboBox {
        color: #29242f;
        background-color: #ffffff;
        border-color: #d8d4dc;
    }

    QComboBox:hover, QComboBox:on {
        color: #29242f;
        background-color: #ffffff;
        border-color: #159fc5;
    }

    QComboBox QAbstractItemView {
        color: #29242f;
        background-color: #ffffff;
        border-color: #d4cfd9;
        selection-background-color: #fff0f6;
        selection-color: #211d27;
    }

    QPushButton {
        color: #423b49;
        background-color: #f1eff3;
        border-color: #d8d4dc;
    }

    QPushButton:hover {
        color: #211d27;
        background-color: #eae7ed;
        border-color: #b9b2be;
    }

    QPushButton:pressed {
        background-color: #ded9e2;
    }

    QPushButton:disabled {
        color: #aaa4ae;
        background-color: #efedf0;
        border-color: #e0dde3;
    }

    QPushButton#SecondaryButton, QPushButton#SubtleButton {
        color: #5b5462;
        background-color: transparent;
        border-color: #d4cfd9;
    }

    QPushButton#SecondaryButton:hover, QPushButton#SubtleButton:hover {
        color: #211d27;
        background-color: #f4f1f5;
        border-color: #159fc5;
    }

    QPushButton#DangerButton {
        color: #a93650;
        background-color: #fff0f3;
        border-color: #efbdc8;
    }

    QPushButton#SuccessButton {
        color: #257154;
        background-color: #edf9f3;
        border-color: #bce3d1;
    }

    QCheckBox {
        color: #514a58;
    }

    QCheckBox::indicator {
        background-color: #ffffff;
        border-color: #bdb7c3;
    }

    QCheckBox::indicator:hover {
        border-color: #159fc5;
    }

    QCheckBox::indicator:checked {
        background-color: #ef4f91;
        border-color: #ef4f91;
    }

    QTableWidget {
        color: #332e38;
        background-color: #ffffff;
        alternate-background-color: #faf9fb;
        border-color: #e0dde4;
        selection-background-color: #fff0f6;
    }

    QTableWidget::item {
        border-bottom-color: #ece9ee;
    }

    QHeaderView::section {
        color: #756e7d;
        background-color: #f3f1f5;
        border-bottom-color: #ddd9e1;
    }

    QProgressBar {
        color: #5f5866;
        background-color: #f0edf2;
        border-color: #d7d2dc;
    }

    QProgressBar::chunk {
        background-color: #22b8dc;
    }

    QStatusBar {
        color: #77707e;
        background-color: #ffffff;
        border-top-color: #e0dde4;
    }

    QTabWidget::pane, QGroupBox {
        background-color: #ffffff;
        border-color: #ddd9e1;
    }

    QTabBar::tab {
        color: #756e7d;
        background-color: #f3f1f5;
        border-color: #ddd9e1;
    }

    QTabBar::tab:selected {
        color: #211d27;
        background-color: #ffffff;
        border-color: #d2cbd7;
    }

    QMenu {
        color: #29242f;
        background-color: #ffffff;
        border-color: #d4cfd9;
    }

    QMenu::item:selected {
        color: #211d27;
        background-color: #fff0f6;
    }
"""
