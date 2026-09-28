"""Semantic colors and dimensions for the shared star-trail desktop UI."""

import re
from dataclasses import dataclass

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


def build_component_overrides(is_dark: bool) -> str:
    p = DARK_PALETTE if is_dark else LIGHT_PALETTE
    m = UI_METRICS
    notice = "#342c22" if is_dark else "#fff5e0"
    success_surface = "#20362e" if is_dark else "#edf8f2"
    return f"""
    * {{ font-size: 10pt; color: {p.text}; }}
    QWidget {{ background: transparent; }}
    QMainWindow, QDialog, #AppSurface, #Workspace {{ background: {p.background}; }}
    #Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.divider}; }}
    QLabel#BrandTitle {{ font-size: 15pt; font-weight: 800; }}
    QLabel#PageTitle, QLabel#DialogTitle {{ font-size: 20pt; font-weight: 700; }}
    QLabel#SectionTitle, QLabel#VideoTitle {{ font-size: 12pt; font-weight: 700; }}
    QLabel#Caption, QLabel#DialogCaption, QLabel#MetaLabel, QLabel#MutedLabel,
    QLabel#SidebarCaption, QLabel#FieldLabel, QLabel#InfoChip {{ color: {p.muted}; font-size: 9pt; }}
    QLabel#NavSection {{ color: {p.muted}; font-size: 9pt; padding: 8px; }}
    QLabel#HeroEyebrow {{ color: {p.muted}; font-size: 9pt; }}
    QLabel#HeroTitle {{ font-size: 12pt; font-weight: 700; }}
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
    QPushButton:focus {{ border-color: {p.focus}; }}
    QPushButton:disabled {{ background: {p.surface_raised}; color: {p.disabled}; }}
    QPushButton#PrimaryButton, QPushButton#DownloadButton, QPushButton#HeroButton {{
        min-height: {m.primary_height - 4}px; background: {p.accent}; color: {p.accent_text}; border-color: {p.focus};
    }}
    QPushButton#PrimaryButton:hover, QPushButton#DownloadButton:hover, QPushButton#HeroButton:hover {{ background: {p.accent_hover}; }}
    QPushButton#PrimaryButton:pressed, QPushButton#DownloadButton:pressed, QPushButton#HeroButton:pressed {{ background: {p.accent_pressed}; }}
    QPushButton#PrimaryButton:focus, QPushButton#DownloadButton:focus, QPushButton#HeroButton:focus {{ border-color: {p.accent_text}; }}
    QPushButton#PrimaryButton:disabled, QPushButton#DownloadButton:disabled, QPushButton#HeroButton:disabled {{ background: {p.surface_raised}; color: {p.disabled}; border-color: {p.divider}; }}
    QPushButton#SubtleButton, QPushButton#SecondaryButton, QPushButton#SidebarAction {{ background: {p.surface_raised}; }}
    QPushButton#GhostButton, QPushButton#TextButton, QPushButton#ActivityButton {{ background: transparent; color: {p.muted}; }}
    QPushButton#TextButton:hover, QPushButton#GhostButton:hover, QPushButton#ActivityButton:hover {{ background: {p.selection}; color: {p.text}; }}
    QPushButton#DangerButton, QPushButton#TableDangerButton {{ color: {p.danger}; background: {p.danger_surface}; }}
    QPushButton#DangerButton:hover, QPushButton#TableDangerButton:hover {{ border-color: {p.danger_border}; }}
    QPushButton#DangerButton:pressed, QPushButton#TableDangerButton:pressed {{ background: {p.danger_border}; }}
    QPushButton#DangerButton:disabled, QPushButton#TableDangerButton:disabled {{ color: {p.disabled}; background: {p.surface_raised}; }}
    QPushButton#TablePrimaryButton, QPushButton#TableSubtleButton, QPushButton#TableDangerButton,
    QPushButton#ActivityButton {{ min-height: 28px; max-height: 28px; padding: 0 10px; font-size: 9pt; }}
    QPushButton#TablePrimaryButton, QPushButton#TableSubtleButton {{ background: {p.surface_raised}; }}
    QPushButton#TablePrimaryButton:hover, QPushButton#TableSubtleButton:hover {{ background: {p.selection}; }}
    QPushButton#TableSubtleButton:pressed, QPushButton#TablePrimaryButton:pressed {{ border-color: {p.border}; }}
    QPushButton#TablePrimaryButton:disabled, QPushButton#TableSubtleButton:disabled {{ color: {p.disabled}; }}
    QPushButton#NavButton, QPushButton#NavButtonActive {{
        min-height: 40px; padding: 0 10px; text-align: left; background: transparent; color: {p.muted};
    }}
    QPushButton#NavButton:hover {{ background: {p.surface_raised}; color: {p.text}; }}
    QPushButton#NavButtonActive {{ background: {p.selection}; color: {p.text}; border-left-color: {p.accent}; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
        background: {p.surface}; color: {p.text}; border: 2px solid {p.border}; border-radius: 8px;
        min-height: 36px; padding: 0 10px; selection-background-color: {p.selection}; selection-color: {p.text};
    }}
    QPlainTextEdit, QTextEdit {{ padding: 10px; }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {p.border_hover}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {p.focus}; }}
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
    QProgressBar#PausedProgress::chunk, QProgressBar#CancelledProgress::chunk {{ background: {p.border}; }}
    QProgressBar#CompletedProgress::chunk {{ background: {p.success}; }}
    QProgressBar#ErrorProgress::chunk {{ background: {p.danger_border}; }}
    QProgressBar#WarningProgress::chunk {{ background: {p.warning}; }}
    QTabWidget::pane {{ border: none; background: transparent; padding-top: 16px; }}
    QTabWidget::tab-bar {{ alignment: left; }}
    QTabBar::tab {{
        background: {p.surface_raised}; color: {p.muted}; border: 2px solid transparent;
        border-radius: 8px; min-height: 36px; padding: 0 18px; margin-right: 6px;
    }}
    QTabBar::tab:selected {{ background: {p.selection}; color: {p.text}; border-bottom-color: {p.accent}; }}
    QTabBar::tab:hover {{ color: {p.text}; }}
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
    """


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
