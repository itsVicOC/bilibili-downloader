"""Semantic colors and dimensions for the shared star-trail desktop UI."""

import re
from dataclasses import dataclass, replace

_FONT_SIZE_PATTERN = re.compile(r"(font-size:\s*)(\d+(?:\.\d+)?)(pt\s*;)")


def scale_font_sizes(stylesheet: str, factor: float) -> str:
    if factor <= 0:
        raise ValueError("font scale must be positive")

    def replace(match):
        value = f"{float(match.group(2)) * factor:.4f}".rstrip("0").rstrip(".")
        return f"{match.group(1)}{value}{match.group(3)}"

    return _FONT_SIZE_PATTERN.sub(replace, stylesheet)


@dataclass(frozen=True)
class UiMetrics:
    control_height: int = 40
    compact_button_height: int = 32
    primary_height: int = 44
    hero_control_height: int = 44
    radius: int = 8
    card_radius: int = 14
    row_height: int = 56
    compact_row_height: int = 44
    page_margin: int = 24
    section_gap: int = 20
    card_padding: int = 20


@dataclass(frozen=True)
class ThemePalette:
    text: str
    muted: str
    surface: str
    surface_raised: str
    border: str
    border_hover: str
    accent: str
    active_text: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    danger: str
    danger_surface: str
    danger_border: str
    success: str
    warning: str
    focus: str
    background: str
    sidebar: str
    divider: str
    selection: str
    disabled: str
    primary: str = ""
    primary_hover: str = ""
    primary_pressed: str = ""
    primary_text: str = ""
    hero_start: str = ""
    hero_end: str = ""
    hero_secondary: str = ""


UI_METRICS = UiMetrics()
DARK_PALETTE = ThemePalette(
    text="#f4f1f7",
    muted="#b7b0c3",
    surface="#201e2a",
    surface_raised="#292635",
    border="#81798c",
    border_hover="#a69ab5",
    accent="#ff79b3",
    active_text="#ff9ac5",
    accent_hover="#ff96c2",
    accent_pressed="#e75391",
    accent_text="#181319",
    danger="#ffc1cc",
    danger_surface="#422730",
    danger_border="#a15a6d",
    success="#82d9b6",
    warning="#e7ba62",
    focus="#ff9ac5",
    background="#14131b",
    sidebar="#101018",
    divider="#393445",
    selection="#35283f",
    disabled="#867e93",
)
LIGHT_PALETTE = ThemePalette(
    text="#292430",
    muted="#706679",
    surface="#ffffff",
    surface_raised="#f0edf6",
    border="#8b8098",
    border_hover="#706079",
    accent="#ef5f9d",
    active_text="#a93668",
    accent_hover="#e94f91",
    accent_pressed="#d94382",
    accent_text="#251820",
    danger="#9f2945",
    danger_surface="#fff0f3",
    danger_border="#b66b7d",
    success="#247052",
    warning="#7b5a1c",
    focus="#b84777",
    background="#f7f5fb",
    sidebar="#ffffff",
    divider="#e3ddea",
    selection="#fceaf3",
    disabled="#837b8e",
)


BLUE_LIGHT_PALETTE = replace(
    LIGHT_PALETTE,
    text="#18191c", muted="#61666d", surface_raised="#f1f2f3",
    border="#858b93", border_hover="#61666d", accent="#00aeec",
    active_text="#00699d", accent_hover="#40c5f1", accent_pressed="#008ac5",
    accent_text="#18191c", focus="#008ac5", background="#f6f7f8",
    divider="#e3e5e7", selection="#dff6fd", disabled="#9499a0",
    primary="#007faf", primary_hover="#0076a5", primary_pressed="#00699d",
    primary_text="#ffffff",
    hero_start="#ffffff", hero_end="#dff6fd", hero_secondary="#f5c9de",
)
BLUE_DARK_PALETTE = replace(
    DARK_PALETTE,
    text="#e7e9eb", muted="#a2a7ae", surface="#17181a", surface_raised="#222426",
    border="#757a81", border_hover="#a2a7ae", accent="#0087bd",
    active_text="#58b1d4", accent_hover="#2c9cc8", accent_pressed="#006996",
    accent_text="#090b0d", focus="#2c9cc8", background="#101011",
    sidebar="#17181a", divider="#2f3134", selection="#0b202a", disabled="#757a81",
    primary="#007faf", primary_hover="#0076a5", primary_pressed="#00699d",
    primary_text="#ffffff",
    hero_start="#17181a", hero_end="#0c2d3b", hero_secondary="#714b67",
)


def theme_palette(is_dark: bool, theme_id: str = "star_trail") -> ThemePalette:
    if theme_id == "bilibili_blue":
        return BLUE_DARK_PALETTE if is_dark else BLUE_LIGHT_PALETTE
    return DARK_PALETTE if is_dark else LIGHT_PALETTE


def background_overlay_alpha(
    is_dark: bool, theme_id: str = "star_trail", visibility: int | None = None
) -> int:
    if visibility is not None:
        return round(255 * (1 - visibility / 100))
    # Existing settings retain the original automatic readability mask.
    light, dark = (238, 214) if theme_id == "bilibili_blue" else (246, 208)
    return dark if is_dark else light


def build_component_overrides(is_dark: bool, theme_id: str = "star_trail") -> str:
    p = theme_palette(is_dark, theme_id)
    m = UI_METRICS
    notice = "#342c22" if is_dark else "#fff5e0"
    success_surface = "#20362e" if is_dark else "#edf8f2"
    primary = p.primary or p.accent
    primary_hover = p.primary_hover or p.accent_hover
    primary_pressed = p.primary_pressed or p.accent_pressed
    primary_text = p.primary_text or p.accent_text
    stylesheet = f"""
    * {{ font-size: 10.5pt; color: {p.text}; }}
    QSlider {{ min-height: 28px; }}
    QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {p.divider}; }}
    QSlider::sub-page:horizontal {{ border-radius: 3px; background: {p.accent}; }}
    QSlider::handle:horizontal {{ width: 16px; margin: -7px 0; border-radius: 9px; background: {p.accent}; border: 2px solid {p.surface}; }}
    QSlider::handle:horizontal:hover, QSlider::handle:horizontal:focus {{ border-color: {p.focus}; }}
    QSlider::handle:horizontal:disabled, QSlider::sub-page:horizontal:disabled {{ background: {p.muted}; }}
    QWidget {{ background: transparent; }}
    QMainWindow, QDialog, #AppSurface, #Workspace {{ background: {p.background}; }}
    #Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.divider}; }}
    QLabel#BrandTitle {{ font-size: 15pt; font-weight: 800; }}
    QLabel#PageTitle, QLabel#DialogTitle {{ font-size: 18pt; font-weight: 600; }}
    QLabel#SectionTitle, QLabel#VideoTitle {{ font-size: 12pt; font-weight: 700; }}
    QLabel#Caption, QLabel#DialogCaption, QLabel#MetaLabel, QLabel#MutedLabel,
    QLabel#SidebarCaption, QLabel#FieldLabel, QLabel#InfoChip {{ color: {p.muted}; font-size: 9pt; }}
    QLabel#NavSection {{ color: {p.muted}; font-size: 9pt; padding: 8px; }}
    QLabel#HeroEyebrow {{ color: {p.muted}; font-size: 9pt; }}
    QLabel#HeroTitle {{ font-size: 12pt; font-weight: 700; }}
    QToolBar#WorkspaceToolbar {{ background: {p.background}; border: none; border-bottom: 1px solid {p.divider}; padding: 0; spacing: 8px; }}
    #WorkspaceHeaders {{ background: transparent; min-height: 52px; }}
    QMenuBar {{ background: {p.sidebar}; color: {p.text}; border-bottom: 1px solid {p.divider}; padding: 2px 8px; }}
    QMenuBar::item {{ padding: 5px 10px; background: transparent; border-radius: 5px; }}
    QMenuBar::item:selected {{ background: {p.selection}; }}
    #Panel, #SectionCard, #ControlPanel, #MascotCard {{
        background: {p.surface}; border: 1px solid {p.divider}; border-radius: {m.card_radius}px;
    }}
    QLabel#InfoChip {{ background: transparent; border: none; padding: 0; }}
    QLabel#EmptyCover {{ background: {p.surface_raised}; border: 1px solid {p.divider}; border-radius: 10px; }}
    QLabel#LoginInstructions {{ background: {p.surface_raised}; border: 1px solid {p.divider}; border-radius: 10px; padding: 12px; }}
    QGroupBox#SettingsSection {{
        background: {p.surface}; border: 1px solid {p.divider}; border-radius: 14px;
        margin-top: 14px; padding: 20px 16px 16px; font-size: 12pt; font-weight: 700;
    }}
    QGroupBox#SettingsSection::title {{ subcontrol-origin: margin; left: 16px; padding: 0 4px; }}
    QLabel#StatusPill, QLabel#StatusBadge {{
        background: {p.surface_raised}; color: {p.muted}; border: 1px solid {p.divider};
        border-radius: 11px; padding: 3px 10px; font-size: 9pt;
    }}
    QLabel[tone="active"], QLabel#StatusBadge[tone="active"] {{ color: {p.active_text}; }}
    QLabel[tone="success"], QLabel#StatusBadge[tone="success"], QLabel#StatusSuccess {{ color: {p.success}; }}
    QLabel[tone="warning"], QLabel#StatusBadge[tone="warning"], QLabel#StatusWarning {{ color: {p.warning}; }}
    QLabel[tone="danger"], QLabel#StatusBadge[tone="danger"], QLabel#StatusDanger {{ color: {p.danger}; }}
    #Notice {{ background: {p.surface_raised}; border: 1px solid {p.divider}; border-radius: 10px; }}
    #Notice[tone="success"] {{ background: {success_surface}; }}
    #Notice[tone="warning"], QLabel#WarningBanner {{ background: {notice}; color: {p.warning}; }}
    #Notice[tone="danger"] {{ background: {p.danger_surface}; }}
    QLabel#WarningBanner {{ border: 1px solid {p.divider}; border-radius: 10px; padding: 12px; }}
    QPushButton {{
        min-height: {m.control_height - 4}px; padding: 0 14px;
        border: 2px solid transparent; border-radius: 8px;
        background: {p.surface_raised}; color: {p.text}; font-weight: 600;
    }}
    QPushButton:hover {{ background: {p.selection}; }}
    QPushButton:pressed {{ background: {p.surface}; border-color: {p.border}; }}
    QPushButton[keyboardFocus="true"]:focus {{ border-color: {p.focus}; }}
    QPushButton:disabled {{ background: {p.surface_raised}; color: {p.disabled}; }}
    QPushButton#PrimaryButton, QPushButton#DownloadButton, QPushButton#HeroButton {{
        min-height: {m.primary_height - 4}px; background: {primary}; color: {primary_text}; border-color: transparent;
    }}
    QPushButton#PrimaryButton:hover, QPushButton#DownloadButton:hover, QPushButton#HeroButton:hover {{ background: {primary_hover}; }}
    QPushButton#PrimaryButton:pressed, QPushButton#DownloadButton:pressed, QPushButton#HeroButton:pressed {{ background: {primary_pressed}; }}
    QPushButton#PrimaryButton[keyboardFocus="true"]:focus, QPushButton#DownloadButton[keyboardFocus="true"]:focus, QPushButton#HeroButton[keyboardFocus="true"]:focus {{ border-color: {primary_text}; }}
    QPushButton#PrimaryButton:disabled, QPushButton#DownloadButton:disabled, QPushButton#HeroButton:disabled {{ background: {p.surface_raised}; color: {p.disabled}; border-color: {p.divider}; }}
    QPushButton#SubtleButton, QPushButton#SecondaryButton, QPushButton#SidebarAction {{ background: {p.surface_raised}; }}
    QPushButton#SidebarAction[signedIn="true"] {{ text-align: left; padding: 0 10px; }}
    QPushButton#SidebarAction[compact="true"] {{ text-align: center; padding: 0; }}
    QPushButton#GhostButton, QPushButton#TextButton, QPushButton#ActivityButton {{ background: transparent; color: {p.muted}; }}
    QPushButton#TextButton:hover, QPushButton#GhostButton:hover, QPushButton#ActivityButton:hover {{ background: {p.selection}; color: {p.text}; }}
    QPushButton#DangerButton, QPushButton#TableDangerButton {{ color: {p.danger}; background: {p.danger_surface}; }}
    QPushButton#DangerButton:hover, QPushButton#TableDangerButton:hover {{ border-color: {p.danger_border}; }}
    QPushButton#DangerButton:pressed, QPushButton#TableDangerButton:pressed {{ background: {p.danger_border}; }}
    QPushButton#DangerButton:disabled, QPushButton#TableDangerButton:disabled {{ color: {p.disabled}; background: {p.surface_raised}; }}
    QPushButton#TablePrimaryButton, QPushButton#TableSubtleButton, QPushButton#TableDangerButton, QPushButton#TableRemoveButton,
    QPushButton#ActivityButton {{ min-height: 28px; max-height: 28px; padding: 0 10px; font-size: 9pt; }}
    QPushButton#TablePrimaryButton, QPushButton#TableSubtleButton {{ background: {p.surface_raised}; }}
    QPushButton#TablePrimaryButton:hover, QPushButton#TableSubtleButton:hover {{ background: {p.selection}; }}
    QPushButton#TableSubtleButton:pressed, QPushButton#TablePrimaryButton:pressed {{ border-color: {p.border}; }}
    QPushButton#TablePrimaryButton:disabled, QPushButton#TableSubtleButton:disabled {{ color: {p.disabled}; }}
    QPushButton#TableRemoveButton {{ background: transparent; color: {p.muted}; }}
    QPushButton#TableRemoveButton:hover, QPushButton#TableRemoveButton[keyboardFocus="true"]:focus {{ background: {p.danger_surface}; color: {p.danger}; border-color: {p.danger_border}; }}
    QPushButton#TableRemoveButton:pressed {{ background: {p.danger_surface}; color: {p.danger}; border-color: {p.danger}; }}
    QPushButton#TableRemoveButton:disabled {{ background: transparent; color: {p.disabled}; border-color: transparent; }}
    QPushButton#NavButton, QPushButton#NavButtonActive {{
        min-height: 40px; padding: 0 10px; text-align: left; background: transparent; color: {p.muted};
    }}
    QPushButton#NavButton:hover {{ background: {p.surface_raised}; color: {p.text}; }}
    QPushButton#NavButtonActive {{ background: {p.selection}; color: {p.text}; border-left-color: {p.accent}; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
        background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; border-radius: 8px;
        min-height: 38px; padding: 0 10px; selection-background-color: {p.selection}; selection-color: {p.text};
    }}
    QPlainTextEdit, QTextEdit {{ padding: 10px; }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {p.border_hover}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {p.focus}; min-height: 36px; }}
    QLineEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{ background: {p.surface_raised}; border: 1px solid {p.divider}; color: {p.muted}; min-height: 38px; }}
    QLineEdit[readOnly="true"]:focus, QPlainTextEdit[readOnly="true"]:focus {{ border-color: {p.focus}; }}
    QLabel#FieldError {{ color: {p.danger}; font-size: 9pt; }}
    QLineEdit[invalid="true"], QComboBox[invalid="true"] {{ border-color: {p.danger_border}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {p.disabled}; background: {p.surface_raised}; border-color: {p.divider}; }}
    QComboBox {{ padding: 0 12px; combobox-popup: 0; }}
    QComboBox:hover {{ background: {p.surface_raised}; }}
    QComboBox[popupOpen="true"] {{ background: {p.selection}; border-color: {p.focus}; }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border: none; }}
    QComboBox::down-arrow {{ image: url(__CHEVRON_ICON__); width: 12px; height: 12px; }}
    ComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QFrame#ComboPopup {{ background: transparent; border: none; }}
    QComboBox QAbstractItemView {{
        background: {p.surface}; color: {p.text}; selection-background-color: {p.selection};
        selection-color: {p.text}; border: 1px solid {p.border}; border-radius: 10px;
        outline: none; padding: 6px;
    }}
    QCheckBox {{ spacing: 8px; min-height: 26px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid {p.border}; border-radius: 5px; background: {p.surface}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.focus}; image: url(__CHECKMARK_ICON__); }}
    QCheckBox::indicator:hover {{ border-color: {p.border_hover}; }}
    QCheckBox::indicator:focus {{ border: 2px solid {p.focus}; }}
    QCheckBox::indicator:checked:focus {{ border-color: {p.accent_text}; }}
    QCheckBox:disabled {{ color: {p.disabled}; }}
    QCheckBox::indicator:disabled {{ background: {p.surface_raised}; border-color: {p.divider}; }}
    QCheckBox::indicator:checked:disabled {{ background: {p.border}; }}
    QTableWidget, QTreeWidget {{
        background: {p.surface}; alternate-background-color: {p.surface}; color: {p.text};
        border: 1px solid {p.divider}; border-radius: 10px; gridline-color: {p.divider};
        selection-background-color: {p.selection}; selection-color: {p.text}; outline: none;
    }}
    QTableWidget::item, QTreeWidget::item {{ padding: 8px; border-bottom: 1px solid {p.divider}; }}
    QTableWidget::item:hover, QTreeWidget::item:hover {{ background: {p.surface_raised}; }}
    QTableWidget::item:selected, QTreeWidget::item:selected {{ background: {p.selection}; color: {p.text}; }}
    QHeaderView::section {{ background: {p.surface_raised}; color: {p.muted}; border: none; border-bottom: 1px solid {p.divider}; padding: 0 10px; min-height: 40px; font-size: 9pt; }}
    QTableCornerButton::section {{ background: {p.surface_raised}; border: none; }}
    QProgressBar {{ min-height: 16px; max-height: 16px; border: none; border-radius: 5px; background: {p.surface_raised}; color: {p.text}; font-size: 9pt; text-align: center; }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 5px; }}
    QProgressBar#ImportProgress {{ min-height: 6px; max-height: 6px; border-radius: 3px; }}
    QProgressBar#PausedProgress::chunk, QProgressBar#CancelledProgress::chunk {{ background: {p.border}; }}
    QProgressBar#CompletedProgress::chunk {{ background: {p.success}; }}
    QProgressBar#ErrorProgress::chunk {{ background: {p.danger_border}; }}
    QProgressBar#WarningProgress::chunk {{ background: {p.warning}; }}
    QTabWidget::pane {{ border: none; background: transparent; padding-top: 16px; }}
    QTabWidget::tab-bar {{ alignment: left; }}
    QTabBar::tab {{
        background: {p.surface}; color: {p.muted}; border: 2px solid transparent;
        border-radius: 7px; min-height: 36px; padding: 0 16px; margin-right: 4px;
    }}
    QTabBar::tab:selected {{ background: {p.selection}; color: {p.active_text}; border-bottom-color: {p.accent}; }}
    QTabBar::tab:hover {{ background: {p.surface_raised}; color: {p.text}; }}
    QTabBar::tab:focus {{ border-color: {p.focus}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; margin: 4px 1px; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 1px 4px; }}
    QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 4px; background: {p.border}; margin: 0 2px; }}
    QScrollBar::handle:horizontal {{ min-width: 32px; border-radius: 4px; background: {p.border}; margin: 2px 0; }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {p.border_hover}; }}
    QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{ background: {p.accent}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QStatusBar {{ background: {p.sidebar}; color: {p.muted}; border-top: 1px solid {p.divider}; }}
    QStatusBar::item {{ border: none; }}
    QMenu {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 9px 18px; border: 1px solid transparent; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p.selection}; color: {p.active_text}; }}
    QMenu::item:disabled {{ color: {p.disabled}; }}
    QMenu::separator {{ height: 1px; background: {p.divider}; margin: 6px 12px; }}
    QPushButton[menuButton="true"], QPushButton#TableSubtleButton[menuButton="true"],
    QPushButton#TextButton[menuButton="true"] {{ padding-right: 30px; }}
    QPushButton[menuButton="true"]:open, QPushButton#TableSubtleButton[menuButton="true"]:open,
    QPushButton#TextButton[menuButton="true"]:open {{ background: {p.selection}; border-color: {p.focus}; }}
    QPushButton::menu-indicator {{
        image: url(__CHEVRON_ICON__); width: 12px; height: 12px;
        subcontrol-origin: padding; subcontrol-position: center right; right: 10px;
    }}
    QPushButton::menu-indicator:open {{ image: url(__CHEVRON_UP_ICON__); }}
    QMessageBox {{ background: {p.background}; }}
    QMessageBox QLabel#qt_msgbox_informativelabel {{ min-width: 320px; }}
    QToolTip {{ background: {p.surface_raised}; color: {p.text}; border: 1px solid {p.border}; padding: 6px; }}
    QPushButton#StepperButton {{ min-width: 32px; max-width: 32px; padding: 0; }}
    #ActionBar, #OutputActionBar {{ background: {p.surface}; border: 1px solid {p.divider}; border-radius: 14px; }}
    #ToolSurface {{ background: {p.surface}; border: 1px solid {p.divider}; border-radius: 10px; }}
    QLabel#OutputSelection {{ font-weight: 700; color: {p.text}; }}
    QPushButton#OutputSecondaryButton {{
        min-height: 28px; max-height: 28px; padding: 0 12px; border: 2px solid transparent;
        background: transparent; color: {p.muted}; font-size: 9pt; font-weight: 500;
    }}
    QPushButton#OutputSecondaryButton:hover {{ background: {p.surface_raised}; color: {p.text}; }}
    QPushButton#OutputSecondaryButton:pressed {{ background: {p.selection}; color: {p.text}; }}
    QPushButton#OutputSecondaryButton[keyboardFocus="true"]:focus {{ border-color: {p.focus}; }}
    QPushButton#OutputSecondaryButton:disabled {{ background: transparent; color: {p.disabled}; }}
    QPushButton#OutputPrimaryButton {{
        min-height: 40px; max-height: 40px; padding: 0 14px; border: 2px solid transparent;
        background: {primary}; color: {primary_text}; font-weight: 600;
    }}
    QPushButton#OutputPrimaryButton:hover {{ background: {primary_hover}; }}
    QPushButton#OutputPrimaryButton:pressed {{ background: {primary_pressed}; }}
    QPushButton#OutputPrimaryButton[keyboardFocus="true"]:focus {{ border-color: {primary_text}; }}
    QPushButton#OutputPrimaryButton:disabled {{ background: {p.surface_raised}; color: {p.disabled}; border-color: {p.divider}; }}
    QDialog#BatchImport[embedded="true"] {{ background: transparent; }}
    #BatchImport QPushButton#TableSubtleButton {{ background: transparent; color: {p.muted}; }}
    #BatchImport QPushButton#TableSubtleButton:hover {{ background: {p.surface_raised}; color: {p.text}; }}
    #BatchImport QPushButton#TableSubtleButton[warningAction="true"] {{ color: {p.warning}; min-height: 22px; max-height: 22px; }}
    #BatchImport QPushButton#TableSubtleButton[warningAction="true"]:hover {{ color: {p.warning}; }}
    QTableWidget#BatchPreview {{ border: none; border-radius: 0; }}
    #BatchImport QHeaderView::section {{ background: {p.surface}; min-height: 34px; }}
    #BatchImport QPlainTextEdit {{ border-color: {p.divider}; }}
    #BatchImport QPlainTextEdit:focus {{ border-color: {p.focus}; }}
    """
    if theme_id == "bilibili_blue":
        # Keep neutral reading surfaces, with localized sky and rose accents.
        stylesheet += f"""
        QToolBar#WorkspaceToolbar {{ background: {p.surface}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
            border-width: 1px; min-height: 38px;
        }}
        QLineEdit[invalid="true"], QComboBox[invalid="true"] {{ border-color: {p.danger_border}; }}
        QPushButton#NavButtonActive {{
            color: {p.active_text}; font-weight: 600;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p.selection}, stop:1 {p.surface});
        }}
        #MascotCard {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p.hero_start}, stop:1 {p.hero_end});
        }}
        QLabel#HeroTitle {{ color: {p.active_text}; }}
        QPushButton#TableSubtleButton, QPushButton#GhostButton, QPushButton#TextButton {{ background: transparent; }}
        QPushButton#TableSubtleButton:hover, QPushButton#GhostButton:hover, QPushButton#TextButton:hover {{ background: {p.surface_raised}; }}
        QCheckBox::indicator:checked {{ background: {primary}; border-color: {primary}; }}
        QCheckBox::indicator:checked:disabled {{ background: {p.border}; border-color: {p.divider}; }}
        QTabBar::tab:selected {{
            background: {p.selection}; color: {p.active_text}; border-bottom-color: {p.accent};
            border-top-left-radius: 8px; border-top-right-radius: 8px;
        }}
        """
    return stylesheet


def readable_fill_text(color: str, dark_text: str) -> str:
    """Pick the higher-contrast foreground for progress text over semantic fills."""

    def luminance(value):
        channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    background = luminance(color)

    def contrast(text):
        high, low = sorted((background, luminance(text)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    return max(("#ffffff", "#101018", dark_text), key=contrast)


# Kept as public imports for older callers; the generated stylesheet is the sole layer.
DARK_STYLE = build_component_overrides(True)
LIGHT_OVERRIDES = build_component_overrides(False)
