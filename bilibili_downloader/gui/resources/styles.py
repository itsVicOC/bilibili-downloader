"""Application QSS stylesheet and shared visual design tokens."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UiMetrics:
    """Logical-pixel measurements shared by QSS and widget geometry."""

    control_height: int = 36
    compact_button_height: int = 32
    primary_height: int = 44
    hero_control_height: int = 48
    radius: int = 8
    row_height: int = 48


@dataclass(frozen=True)
class ThemePalette:
    """Semantic colors used by the final component-state overrides."""

    text: str
    muted: str
    surface: str
    surface_raised: str
    border: str
    border_hover: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    danger: str
    danger_surface: str
    danger_border: str
    success: str
    warning: str
    focus: str


UI_METRICS = UiMetrics()

DARK_PALETTE = ThemePalette(
    text="#f4f1f7",
    muted="#aaa4b0",
    surface="#202027",
    surface_raised="#2a2931",
    border="#6d6974",
    border_hover="#8a8490",
    accent="#ff79b3",
    accent_hover="#ff96c2",
    accent_pressed="#e75391",
    accent_text="#181319",
    danger="#ffc1cc",
    danger_surface="#422730",
    danger_border="#70404d",
    success="#82d9b6",
    warning="#e7ba62",
    focus="#ff9ac5",
)

LIGHT_PALETTE = ThemePalette(
    text="#29242f",
    muted="#6e6675",
    surface="#ffffff",
    surface_raised="#f1eff3",
    border="#948c9a",
    border_hover="#756b7a",
    accent="#ef5f9d",
    accent_hover="#e94f91",
    accent_pressed="#d94382",
    accent_text="#251820",
    danger="#9f2945",
    danger_surface="#fff0f3",
    danger_border="#df9eae",
    success="#247052",
    warning="#7b5a1c",
    focus="#b84777",
)

DARK_STYLE = """
    * {
        font-size: 10pt;
        letter-spacing: 0px;
        color: #f4f1f7;
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

    QScrollArea#WorkspaceScroll, QScrollArea#WorkspaceScroll > QWidget > QWidget {
        background-color: #18181e;
        border: none;
    }

    QScrollBar:vertical {
        width: 10px;
        margin: 4px 1px;
        background-color: transparent;
        border: none;
    }

    QScrollBar::handle:vertical {
        min-height: 32px;
        margin: 0 2px;
        background-color: #4b4852;
        border: none;
        border-radius: 3px;
    }

    QScrollBar::handle:vertical:hover {
        margin: 0 1px;
        background-color: #77727d;
    }

    QScrollBar::handle:vertical:pressed {
        margin: 0 1px;
        background-color: #b76589;
    }

    QScrollBar:horizontal {
        height: 10px;
        margin: 1px 4px;
        background-color: transparent;
        border: none;
    }

    QScrollBar::handle:horizontal {
        min-width: 32px;
        margin: 2px 0;
        background-color: #4b4852;
        border: none;
        border-radius: 3px;
    }

    QScrollBar::handle:horizontal:hover {
        margin: 1px 0;
        background-color: #77727d;
    }

    QScrollBar::handle:horizontal:pressed {
        margin: 1px 0;
        background-color: #b76589;
    }

    QScrollBar::add-line, QScrollBar::sub-line {
        width: 0;
        height: 0;
        background-color: transparent;
        border: none;
    }

    QScrollBar::add-page, QScrollBar::sub-page {
        background-color: transparent;
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
        font-size: 15pt;
        font-weight: 800;
    }

    QLabel#SidebarCaption {
        color: #8f8998;
        font-size: 8.25pt;
    }

    QLabel#NavSection {
        color: #8f8998;
        font-size: 7.5pt;
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
        font-size: 17.25pt;
        font-weight: 800;
    }

    QLabel#DialogTitle {
        color: #ffffff;
        font-size: 16.5pt;
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
        border-color: #9c647d;
    }

    #HeroPanel {
        border: 1px solid #44354e;
        border-radius: 8px;
    }

    QLabel#HeroEyebrow {
        color: #8be4ff;
        font-size: 7.5pt;
        font-weight: 800;
    }

    QLabel#HeroTitle {
        color: #ffffff;
        font-size: 20.25pt;
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
        border-color: #d46f9c;
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
        font-size: 11.25pt;
        font-weight: 800;
    }

    QLabel#FieldLabel {
        color: #b6b0bd;
        font-size: 8.25pt;
        font-weight: 700;
    }

    QLabel#VideoTitle {
        color: #ffffff;
        font-size: 13.5pt;
        font-weight: 800;
    }

    QLabel#StatusPill, QLabel#SuccessPill {
        color: #baf2ff;
        background-color: #18333a;
        border: 1px solid #285b66;
        border-radius: 8px;
        padding: 3px 9px;
        font-size: 8.25pt;
        font-weight: 700;
    }

    QLabel#InfoChip {
        color: #d0cad5;
        background-color: #2a2931;
        border: 1px solid #3d3a45;
        border-radius: 7px;
        padding: 5px 9px;
        font-size: 8.25pt;
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

    QLabel#LoginInstructions {
        color: #d1ccd5;
        background-color: #19191f;
        border: 1px solid #39363f;
        border-radius: 7px;
        padding: 9px 11px;
    }

    QLabel#LoginInstructions:focus {
        border-color: #8a6074;
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
        border-color: #c66b93;
        background-color: #1b1b21;
    }

    QLineEdit:read-only {
        color: #aaa5b0;
        background-color: #1b1b20;
    }

    QSpinBox {
        padding: 7px 10px;
    }

    QPushButton#StepperButton {
        min-width: 36px;
        max-width: 36px;
        min-height: 38px;
        max-height: 38px;
        padding: 0;
        color: #d9d3dd;
        background-color: #24232a;
        border-color: #3a3942;
        font-size: 12.75pt;
        font-weight: 600;
    }

    QPushButton#StepperButton:hover {
        color: #ffffff;
        background-color: #3a2b34;
        border-color: #8a6074;
    }

    QPushButton#StepperButton:pressed {
        background-color: #4b3040;
    }

    QPushButton#StepperButton:disabled {
        color: #5f5a64;
        background-color: #1d1c22;
        border-color: #302e36;
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
        border-color: #8a6377;
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
        min-height: 34px;
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

    QPushButton:focus, QComboBox:focus {
        border: 1px solid #d46f9c;
    }

    QCheckBox:focus {
        color: #ffffff;
        border: none;
    }

    QCheckBox::indicator:focus {
        border: 2px solid #ff9ac5;
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
        border-color: #9c647d;
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
        spacing: 9px;
        min-height: 24px;
        padding: 2px 0;
        color: #d1ccd5;
        background-color: transparent;
        border: none;
    }

    QCheckBox:hover {
        color: #f7f3f8;
    }

    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        background-color: #17171c;
        border: 1px solid #4b4852;
        border-radius: 4px;
    }

    QCheckBox::indicator:hover {
        background-color: #211f25;
        border-color: #8a7f8d;
    }

    QCheckBox::indicator:checked {
        background-color: #ff5fa2;
        border-color: #ff8fbe;
        image: url("__CHECKMARK_ICON__");
    }

    QCheckBox:disabled {
        color: #716c77;
    }

    QCheckBox::indicator:disabled {
        background-color: #1c1c21;
        border-color: #34323a;
    }

    QCheckBox::indicator:checked:disabled {
        background-color: #624051;
        border-color: #745064;
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
        font-size: 8.25pt;
        font-weight: 700;
    }

    QProgressBar {
        height: 18px;
        color: #d7d1db;
        background-color: #15151a;
        border: 1px solid #34323b;
        border-radius: 6px;
        text-align: center;
        font-size: 7.5pt;
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

    QScrollArea#WorkspaceScroll, QScrollArea#WorkspaceScroll > QWidget > QWidget {
        background-color: #f7f7fa;
    }

    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
        background-color: #c5c0c9;
    }

    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
        background-color: #938d99;
    }

    QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {
        background-color: #b6507c;
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
        color: #756e7d;
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
        border-color: #b46b89;
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
        border-color: #b84777;
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

    QLabel#LoginInstructions {
        color: #514a58;
        background-color: #f8f6f9;
        border-color: #ddd8e1;
    }

    QLabel#LoginInstructions:focus {
        border-color: #b46b89;
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
        border-color: #b84777;
    }

    QLineEdit:read-only {
        color: #726b78;
        background-color: #f3f1f5;
    }

    QPushButton#StepperButton {
        color: #5d5563;
        background-color: #f3f1f5;
        border-color: #d8d4dc;
    }

    QPushButton#StepperButton:hover {
        color: #2f2934;
        background-color: #fff0f6;
        border-color: #c9819f;
    }

    QPushButton#StepperButton:pressed {
        background-color: #f7d9e6;
    }

    QPushButton#StepperButton:disabled {
        color: #c2bdc5;
        background-color: #f4f2f5;
        border-color: #e4e0e6;
    }

    QComboBox {
        color: #29242f;
        background-color: #ffffff;
        border-color: #d8d4dc;
    }

    QComboBox:hover, QComboBox:on {
        color: #29242f;
        background-color: #ffffff;
        border-color: #9b7184;
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

    QPushButton:focus, QComboBox:focus {
        border-color: #b84777;
    }

    QCheckBox:focus {
        color: #211d27;
        border: none;
    }

    QCheckBox::indicator:focus {
        border-color: #b84777;
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
        border-color: #b46b89;
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
        background-color: #faf7f9;
        border-color: #857b89;
    }

    QCheckBox::indicator:checked {
        background-color: #ef4f91;
        border-color: #ef4f91;
    }

    QCheckBox:disabled {
        color: #a29ca6;
    }

    QCheckBox::indicator:disabled {
        background-color: #f0eef2;
        border-color: #d7d2da;
    }

    QCheckBox::indicator:checked:disabled {
        background-color: #d69ab4;
        border-color: #d08da9;
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


def build_component_overrides(is_dark: bool) -> str:
    """Build the final, semantic control-state layer from design tokens."""
    palette = DARK_PALETTE if is_dark else LIGHT_PALETTE
    metrics = UI_METRICS
    compact_content_height = metrics.compact_button_height - 2
    primary_content_height = metrics.primary_height - 2
    hero_content_height = metrics.hero_control_height - 2
    disabled_text = "#77727d" if is_dark else "#aaa4ae"
    disabled_surface = "#222127" if is_dark else "#efedf0"
    disabled_border = "#33313a" if is_dark else "#e0dde3"
    return f"""
        QPushButton {{
            min-height: {metrics.control_height - 2}px;
            border-radius: {metrics.radius - 1}px;
            border-color: {palette.border};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
            border-color: {palette.border};
        }}

        QCheckBox::indicator {{
            border-color: {palette.border};
        }}

        QLineEdit#UrlInput {{ border-color: {palette.border}; }}
        QLineEdit#UrlInput:hover {{ border-color: {palette.border_hover}; }}
        QLineEdit#UrlInput:focus {{ border: 2px solid {palette.focus}; }}

        QPushButton:focus, QComboBox:focus, QLineEdit:focus,
        QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
            border: 2px solid {palette.focus};
        }}

        QPushButton#PrimaryButton, QPushButton#DownloadButton {{
            min-height: {primary_content_height}px;
            color: {palette.accent_text};
            background-color: {palette.accent};
            border-color: {palette.accent};
            font-weight: 800;
        }}

        QPushButton#PrimaryButton:hover, QPushButton#DownloadButton:hover {{
            color: {palette.accent_text};
            background-color: {palette.accent_hover};
            border-color: {palette.accent_hover};
        }}

        QPushButton#PrimaryButton:pressed, QPushButton#DownloadButton:pressed {{
            color: {palette.accent_text};
            background-color: {palette.accent_pressed};
            border-color: {palette.accent_pressed};
        }}

        QPushButton#HeroButton {{
            min-height: {hero_content_height}px;
            max-height: {hero_content_height}px;
            color: {palette.accent_text};
            background-color: {palette.accent};
            border-color: {palette.accent};
        }}

        QPushButton#HeroButton:hover {{
            color: {palette.accent_text};
            background-color: {palette.accent_hover};
            border-color: {palette.accent_hover};
        }}

        QPushButton#HeroButton:pressed {{
            color: {palette.accent_text};
            background-color: {palette.accent_pressed};
            border-color: {palette.accent_pressed};
        }}

        QPushButton#PrimaryButton:disabled, QPushButton#DownloadButton:disabled,
        QPushButton#HeroButton:disabled {{
            color: {disabled_text};
            background-color: {disabled_surface};
            border-color: {disabled_border};
        }}

        QPushButton#SecondaryButton, QPushButton#SubtleButton,
        QPushButton#GhostButton {{
            color: {palette.muted};
            background-color: transparent;
            border-color: {palette.border};
        }}

        QPushButton#SecondaryButton:hover, QPushButton#SubtleButton:hover,
        QPushButton#GhostButton:hover {{
            color: {palette.text};
            background-color: {palette.surface_raised};
            border-color: {palette.border_hover};
        }}

        QPushButton#SecondaryButton:pressed, QPushButton#SubtleButton:pressed,
        QPushButton#GhostButton:pressed {{
            color: {palette.text};
            background-color: {palette.surface};
            border-color: {palette.focus};
        }}

        QPushButton#SecondaryButton:disabled, QPushButton#SubtleButton:disabled,
        QPushButton#GhostButton:disabled, QPushButton#DangerButton:disabled {{
            color: {disabled_text};
            background-color: {disabled_surface};
            border-color: {disabled_border};
        }}

        QPushButton#DangerButton {{
            color: {palette.danger};
            background-color: {palette.danger_surface};
            border-color: {palette.danger_border};
        }}

        QPushButton#DangerButton:hover {{
            color: {palette.text};
            border-color: {palette.danger};
        }}

        QPushButton#DangerButton:pressed {{
            color: {palette.text};
            background-color: {palette.danger_border};
        }}

        QPushButton#TableSubtleButton, QPushButton#TablePrimaryButton,
        QPushButton#TableDangerButton {{
            min-height: {compact_content_height}px;
            max-height: {compact_content_height}px;
            padding: 0 12px;
            border-radius: 6px;
        }}

        QPushButton#TableSubtleButton {{
            color: {palette.muted};
            background-color: transparent;
            border-color: {palette.border};
        }}

        QPushButton#TableSubtleButton:hover {{
            color: {palette.text};
            background-color: {palette.surface_raised};
            border-color: {palette.border_hover};
        }}

        QPushButton#TableSubtleButton:pressed {{
            color: {palette.text};
            background-color: {palette.surface};
            border-color: {palette.focus};
        }}

        QPushButton#TablePrimaryButton {{
            color: {palette.accent_text};
            background-color: {palette.accent};
            border-color: {palette.accent};
        }}

        QPushButton#TablePrimaryButton:hover {{
            background-color: {palette.accent_hover};
            border-color: {palette.accent_hover};
        }}

        QPushButton#TablePrimaryButton:pressed {{
            background-color: {palette.accent_pressed};
            border-color: {palette.accent_pressed};
        }}

        QPushButton#TableDangerButton {{
            color: {palette.danger};
            background-color: {palette.danger_surface};
            border-color: {palette.danger_border};
        }}

        QPushButton#TableDangerButton:hover {{
            color: {palette.text};
            border-color: {palette.danger};
        }}

        QPushButton#TableDangerButton:pressed {{
            color: {palette.text};
            background-color: {palette.danger_border};
        }}

        QPushButton#TableSubtleButton:disabled,
        QPushButton#TablePrimaryButton:disabled,
        QPushButton#TableDangerButton:disabled {{
            color: {disabled_text};
            background-color: {disabled_surface};
            border-color: {disabled_border};
        }}

        QPushButton#PrimaryButton:focus, QPushButton#DownloadButton:focus,
        QPushButton#HeroButton:focus, QPushButton#SecondaryButton:focus,
        QPushButton#SubtleButton:focus, QPushButton#GhostButton:focus,
        QPushButton#DangerButton:focus, QPushButton#TableSubtleButton:focus,
        QPushButton#TablePrimaryButton:focus, QPushButton#TableDangerButton:focus {{
            border: 2px solid {palette.focus};
        }}

        QLabel#StatusSuccess {{ color: {palette.success}; font-weight: 700; }}
        QLabel#StatusWarning {{ color: {palette.warning}; font-weight: 700; }}
        QLabel#StatusDanger {{ color: {palette.danger}; font-weight: 700; }}

        QGroupBox#SettingsSection {{
            margin-top: 12px;
            padding: 16px 14px 12px 14px;
            color: {palette.text};
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: {metrics.radius}px;
            font-weight: 700;
        }}

        QGroupBox#SettingsSection::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
            color: {palette.text};
            background-color: transparent;
        }}

        QScrollArea#DialogScroll,
        QScrollArea#DialogScroll > QWidget > QWidget {{
            background-color: transparent;
            border: none;
        }}
    """
