"""Offline component state atlas and runtime coverage for GUI detail reviews."""

import ast
import importlib
import json
import warnings
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.combo_box import ComboBox
from bilibili_downloader.gui.widgets.components import PopupMenu, ReadOnlyPath, stepper
from bilibili_downloader.gui.widgets.download_options import DownloadOptionCard

try:
    from bilibili_downloader.gui.widgets.check_box import CheckBox
except ImportError:  # Also render the previous revision for a real baseline.
    CheckBox = QCheckBox


def _component(kind):
    if kind == "multiline":
        return QPlainTextEdit("第一行说明\n第二行内容，可选择与复制。")
    if kind == "readonly":
        control = ReadOnlyPath()
        control.set_full_text("~/收藏/星轨旅记/城市夜航.mp4")
        return control
    if kind in ("input", "password"):
        control = ChineseLineEdit()
        control.setPlaceholderText("请输入内容")
        if kind == "password":
            control.setEchoMode(QLineEdit.Password)
            control.setText("offline-example")
        return control
    if kind == "combo":
        control = ComboBox()
        control.addItems(["1080P 高清", "4K 超清", "暂不可用"])
        control.model().item(2).setEnabled(False)
        return control
    if kind == "checkbox":
        return CheckBox("保存封面 · 图片")
    if kind == "card":
        return DownloadOptionCard("下载弹幕", "ASS", "star")
    if kind in ("primary", "secondary", "danger"):
        control = QPushButton({"primary": "加入队列（12 项）", "secondary": "修改目录", "danger": "删除文件"}[kind])
        control.setObjectName({"primary": "PrimaryButton", "secondary": "SecondaryButton", "danger": "DangerButton"}[kind])
        return control
    if kind == "stepper":
        spin = QSpinBox()
        spin.setRange(1, 1440)
        spin.setValue(30)
        spin.setSuffix(" 分钟")
        row, _, _ = stepper(spin)
        return row
    control = QSlider(Qt.Horizontal)
    control.setRange(0, 100)
    control.setValue(65)
    return control


def _activate(widget):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*setActiveWindow.*")
        QApplication.setActiveWindow(widget)


def capture_components(app, theme, capture, font_scale=1.0):
    records = []
    kinds = ("input", "multiline", "readonly", "password", "combo", "checkbox", "card",
             "primary", "secondary", "danger", "stepper", "slider")
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            if font_scale != 1:
                app.setStyleSheet(load_stylesheet(dark, theme._font_scale * font_scale, theme._font_family, theme_id=theme_id))
            mode = "dark" if dark else "light"
            for kind in kinds:
                states = ["normal", "hover", "pressed", "focus", "disabled"]
                if kind in ("input", "multiline", "password", "combo", "stepper"):
                    states.append("error")
                if kind in ("checkbox", "card"):
                    states.append("checked")
                if kind == "checkbox":
                    states.append("partial")
                for state in states:
                    host = QDialog()
                    host.setWindowTitle("BiliFlow · 组件状态验收")
                    root = QVBoxLayout(host)
                    root.setContentsMargins(24, 24, 24, 24)
                    root.setSpacing(16)
                    caption = QLabel(f"{kind} · {state}")
                    caption.setObjectName("MetaLabel")
                    root.addWidget(caption)
                    control = _component(kind)
                    control.setAccessibleName(f"验收：{kind}")
                    root.addWidget(control)
                    # Reserve the same explanation line in every atlas state;
                    # an empty QLabel otherwise changes the expanding text area's
                    # height by one pixel at 150%, unrelated to its border state.
                    error = QLabel("请选择可用的值，然后重试。")
                    error.setObjectName("FieldError")
                    if state != "error":
                        error.setStyleSheet("color: transparent;")
                    root.addWidget(error)
                    host.resize(460, 216 if kind == "multiline" else 164)
                    host.show()
                    _activate(host)
                    capture._flush_events(app)
                    target = control.focusProxy() or control
                    if isinstance(control, QCheckBox):
                        control.setChecked(state == "checked")
                        if state == "partial":
                            control.setTristate(True)
                            control.setCheckState(Qt.PartiallyChecked)
                    if QApplication.focusWidget():
                        QApplication.focusWidget().clearFocus()
                    QTest.mouseMove(host, QPoint(4, 4))
                    target.setProperty("keyboardFocus", state == "focus")
                    target.setProperty("invalid", state == "error")
                    target.style().unpolish(target)
                    target.style().polish(target)
                    control.setEnabled(state != "disabled")
                    if state in ("hover", "pressed"):
                        QTest.mouseMove(target, target.rect().center())
                    if state == "pressed":
                        QTest.mousePress(target, Qt.LeftButton, pos=target.rect().center())
                    if state == "focus":
                        target.setFocus(Qt.TabFocusReason)
                    capture._flush_events(app)
                    if state == "focus":
                        assert target.hasFocus(), (kind, state, app.platformName())
                    focused = target.hasFocus()
                    filename = f"component-{theme_id}-{kind}-{mode}-{state}.png"
                    if font_scale != 1:
                        filename = filename.removesuffix(".png") + f"-font{round(font_scale * 100)}.png"
                    capture._save_widget(app, host, filename)
                    records.append({"id": f"{kind}:{state}", "theme": theme_id, "mode": mode,
                                    "class": type(control).__name__, "state": state, "image": filename, "font_scale": font_scale,
                                    "focused": focused, "enabled": control.isEnabled(),
                                    "size": [control.width(), control.height()]})
                    if state == "pressed":
                        QTest.mouseRelease(target, Qt.LeftButton, pos=QPoint(-1, -1))
                    host.deleteLater()
                    capture._flush_events(app)
    name = "component-checks.json" if font_scale == 1 else f"component-checks-font{round(font_scale * 100)}.json"
    (capture.OUTPUT_DIR / name).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if font_scale == 1:
        capture_popups(app, theme, capture)


def capture_popups(app, theme, capture):
    records = []
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            host = QDialog()
            layout = QVBoxLayout(host)
            layout.setContentsMargins(24, 24, 24, 24)
            layout.addWidget(QLabel("下拉框与菜单 · 离线状态验收"))
            combo = ComboBox()
            for number in range(30):
                combo.addItem(f"P{number + 1} · " + "很长的作品章节标题" * 4, number)
            combo.setCurrentIndex(15)
            combo.model().item(16).setEnabled(False)
            layout.addWidget(combo)
            host.resize(460, 164)
            for side in ("below", "above"):
                screen = host.screen().availableGeometry()
                host.move(screen.left() + 32, screen.top() + 32 if side == "below" else screen.bottom() - 180)
                host.show()
                capture._flush_events(app)
                combo.setFocus(Qt.TabFocusReason)
                combo.showPopup()
                capture._flush_events(app)
                popup = combo.view().window()
                filename = f"floating-{theme_id}-{mode}-combo-{side}.png"
                records.append({"image": filename, "theme": theme_id, "mode": mode,
                                "popup": list(popup.geometry().getRect()), "within_screen": screen.contains(popup.frameGeometry()),
                                "current_value": combo.currentData(), "horizontal_scroll": combo.view().horizontalScrollBar().maximum()})
                capture._save_widget(app, host, filename, popup=popup)
                combo.hidePopup()
            host.move(host.screen().availableGeometry().topLeft() + QPoint(32, 32))
            host.show()
            menu = PopupMenu(host)
            menu.addAction("打开文件夹")
            menu.addAction("复制完整路径")
            menu.addSeparator()
            menu.addAction("暂不可用").setEnabled(False)
            submenu = PopupMenu(menu)
            submenu.setTitle("更多操作")
            submenu.addAction("移除记录")
            menu.addMenu(submenu)
            menu.popup(host.mapToGlobal(QPoint(24, 100)))
            capture._flush_events(app)
            QTest.keyClick(menu, Qt.Key_Down)
            capture._save_widget(app, host, f"floating-{theme_id}-{mode}-menu.png", popup=menu)
            menu.hide()
            menu.deleteLater()
            host.deleteLater()
            capture._flush_events(app)
    (capture.OUTPUT_DIR / "popup-checks.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


INTERACTIVE = (QAbstractButton, QLineEdit, QPlainTextEdit, QTextEdit, QComboBox,
               QAbstractSpinBox, QSlider, QAbstractItemView, QTabBar)


class Registry:
    def __init__(self, app, capture):
        self.app, self.capture = app, capture
        self.cases, self.controls = [], {}
        self.context = {}

    def save(self, name, root, *, dialog=False, image_name=None, write_image=True):
        root.show()
        self.capture._flush_events(self.app)
        if dialog and image_name is None and hasattr(root, "_screen_bounds"):
            width, height = self.context["size"]
            origin = root.screen().availableGeometry().topLeft()
            root._screen_bounds.available_geometry = lambda: QRect(origin.x(), origin.y(), width, height)
            root._screen_bounds.fit()
            self.capture._flush_events(self.app)
        filename = "detail-" + "-".join((self.context["theme"], self.context["mode"], str(self.context["size"][0]), name)) + ".png"
        if self.context.get("font_scale", 1) != 1:
            filename = filename.removesuffix(".png") + f"-font{round(self.context['font_scale'] * 100)}.png"
        filename = image_name or filename
        case = {"name": name, "image": filename, **self.context,
                "actual_size": [root.width(), root.height()], "dialog": dialog}
        self.cases.append(case)
        def visit(parent, prefix):
            counts = Counter()
            for child in parent.children():
                if not isinstance(child, QWidget) or child.objectName() == "ControlFocusRing":
                    continue
                kind = type(child).__name__
                counts[kind] += 1
                node = f"{child.objectName() or kind}[{counts[kind]}]"
                path = prefix + "/" + node
                internal = child.objectName().startswith("qt_") or isinstance(child.parentWidget(), (QAbstractSpinBox, QComboBox))
                if isinstance(child, INTERACTIVE) and not internal:
                    label = child.accessibleName()
                    if not label:
                        for method in ("text", "placeholderText", "toolTip"):
                            candidate = getattr(child, method, lambda: "")()
                            if isinstance(candidate, str) and candidate:
                                label = candidate
                                break
                    key = (name if dialog else "workspace") + path
                    record = self.controls.setdefault(key, {"id": key, "class": kind, "label": label,
                                                           "rule": self.rule(child), "states": []})
                    visible = child.isVisible() and not child.visibleRegion().isEmpty()
                    clipped = visible and not child.visibleRegion().boundingRect().contains(child.rect())
                    ancestor, scrolling = child.parentWidget(), False
                    while ancestor and ancestor is not root:
                        scrolling = scrolling or isinstance(ancestor, QAbstractScrollArea)
                        ancestor = ancestor.parentWidget()
                    record["states"].append({"case": filename, "visible": visible, "enabled": child.isEnabled(),
                                             "focus_policy": child.focusPolicy().value,
                                             "size": [child.width(), child.height()],
                                             "clipped": clipped, "scrollable": scrolling})
                visit(child, path)
        visit(root, "")
        if write_image:
            self.capture._save_widget(self.app, root, filename)
        return QDialog.Rejected

    @staticmethod
    def rule(widget):
        if isinstance(widget, QAbstractItemView):
            return "列表／树／表格：行状态、选择、滚动与列宽"
        if isinstance(widget, QAbstractButton):
            return "选择指示器／按钮：命中、焦点、禁用与动作同步"
        if isinstance(widget, (QComboBox, QAbstractSpinBox, QSlider)):
            return "选择与数值：边界、滚轮保护、键盘和单位"
        if isinstance(widget, QTabBar):
            return "页签：选中、键盘焦点与溢出"
        return "文本：输入法、只读、选区、右键菜单与校验"

    def write(self):
        content = json.dumps({
            "cases": self.cases, "controls": list(self.controls.values()),
            "notes": ["滚动区内的局部不可见项单独标记，不视作固定操作遮挡。",
                      "Qt 内部编辑器、视口及系统管理的装饰由所属组件的规则验证。"],
        }, ensure_ascii=False, indent=2)
        temp_root = self.app.property("docsTempRoot")
        if temp_root:
            content = content.replace(str(temp_root), "~/BiliFlow-demo")
        (self.capture.OUTPUT_DIR / "instance-checks.json").write_text(content + "\n", encoding="utf-8")


def _sample(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(value.value if isinstance(value, ast.Constant) else "12" for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _sample(node.left) + _sample(node.right)
    return "离线演示：目录暂时无法访问，请检查磁盘连接及目录权限后重试。\n已有文件将保留。"


def message_entries():
    root = Path(__file__).resolve().parents[1]
    records = []
    for path in sorted((root / "bilibili_downloader/gui").rglob("*.py")):
        tree = ast.parse(path.read_text())
        module = importlib.import_module(".".join(path.relative_to(root).with_suffix("").parts))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "MessageBox" and len(node.args) >= 2:
                    # Nested functions are visited separately below.
                    if any(isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)) and inner is not function
                           and inner.lineno <= node.lineno <= inner.end_lineno for inner in ast.walk(function)):
                        continue
                    keywords = {keyword.arg: keyword.value for keyword in node.keywords}
                    def standard(value, fallback):
                        if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id == "QMessageBox":
                            return getattr(QMessageBox, value.attr)
                        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
                            return standard(value.left, fallback) | standard(value.right, fallback)
                        return fallback
                    title = getattr(module, node.args[0].id, None) if isinstance(node.args[0], ast.Name) else None
                    if not isinstance(title, str):
                        title = "操作确认" if isinstance(node.args[0], ast.Name) else _sample(node.args[0])
                    records.append({"id": f"message-{path.stem}-{function.name.strip('_')}-{node.lineno}",
                                    "source": str(path.relative_to(root)), "line": node.lineno,
                                    "entry": function.name, "title": title, "text": _sample(node.args[1]),
                                    "tone": _sample(keywords["tone"]) if "tone" in keywords else "info",
                                    "buttons": standard(keywords.get("buttons"), QMessageBox.Ok),
                                    "default": standard(keywords.get("default"), QMessageBox.Ok),
                                    "dynamic_sample": not all(isinstance(arg, ast.Constant) for arg in node.args[:2])})
    return records


def capture_dialogs(app, theme, window, capture, registry):
    import qrcode

    from bilibili_downloader.core.models import DownloadItem, DownloadOutcome
    from bilibili_downloader.gui.dialogs.attachments import (
        AttachmentDialog,
        confirm_media_copy,
    )
    from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery
    from bilibili_downloader.gui.dialogs.close_dialog import CloseWindowDialog
    from bilibili_downloader.gui.dialogs.file_picker import file_picker
    from bilibili_downloader.gui.dialogs.login_dialog import LoginDialog
    from bilibili_downloader.gui.dialogs.naming_fields import NamingFieldDialog
    from bilibili_downloader.gui.dialogs.page_selection import PageSelectionDialog
    from bilibili_downloader.gui.dialogs.relocate_directory import (
        RelocateDirectoryDialog,
    )
    from bilibili_downloader.gui.dialogs.result_details import ResultDetailsDialog
    from bilibili_downloader.gui.dialogs.settings_dialog import (
        NAMING_FIELDS,
        SettingsDialog,
    )
    from bilibili_downloader.gui.dialogs.update_dialog import UpdateDialog
    from bilibili_downloader.gui.settings_sections import SettingsSection
    from bilibili_downloader.gui.threads.batch_worker import ImportIssue, ImportReport
    from bilibili_downloader.gui.widgets.components import MessageBox
    from bilibili_downloader.gui.widgets.library_page import OperationDialog
    info = capture._demo_video()
    item = DownloadItem(video_info=info, download_subtitle=True)
    media = Path(app.property("docsTempRoot")) / "audit-media.mp4"
    media.write_bytes(b"offline demonstration")
    outcome = DownloadOutcome(video_path=str(media), actual_quality=80, actual_video_codec=12,
                              actual_audio_quality=30280, missing_artifacts=["subtitle"], warnings=["字幕未保存，可补全。"])
    factories = [
        ("pages", lambda: PageSelectionDialog(info.pages, {info.pages[0].cid}, window)),
        ("attachments", lambda: AttachmentDialog(item, window, outcome=outcome)),
        ("attachments-unavailable", lambda: AttachmentDialog(item, window, outcome=DownloadOutcome(video_path="/unavailable/demo.mp4"))),
        ("result", lambda: ResultDetailsDialog("保存结果", "字幕暂未保存，可补全。\n" + str(media), window, item=item, outcome=outcome)),
        ("naming-fields", lambda: NamingFieldDialog(NAMING_FIELDS, window)),
        ("relocate", lambda: RelocateDirectoryDialog(window._library, str(media.parent), window)),
        ("room-settings", lambda: window._live_page._build_room_settings_dialog(window._live_controller.rows[1])),
        ("account", lambda: LoginDialog("offline", window, account={"uname": "星海漫游", "mid": "123456"}, account_valid=True)),
        ("account-expired", lambda: LoginDialog("offline", window, account_valid=False)),
        ("login-cookie", lambda: LoginDialog("", window)),
        ("update", lambda: UpdateDialog(capture.UpdateRelease("0.9.0", "v0.9.0", "2026-10-21", capture.DEMO_RELEASE_NOTES, ()), window)),
        ("close", lambda: CloseWindowDialog(window, active=True)),
        ("close-no-tray", lambda: CloseWindowDialog(window, active=True, tray_available=False)),
        ("background-gallery", lambda: BackgroundGallery(window._settings_page._background_pickers["download"])),
        ("file-operation", lambda: OperationDialog("移入回收站？", "共 10000 个文件，包含 5000 个附件。可从系统回收站恢复。",
                                                   "\n".join(f"收藏/示例作品/{n}.mp4" for n in range(100)), window, confirm="移入回收站")),
    ]
    entries = message_entries()
    sources = []
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            samples = [((900, 640), 1), ((1120, 760), 1), ((1320, 860), 1), ((900, 640), 1.25), ((900, 640), 1.5)]
            for size, font_scale in samples:
                theme.apply_theme(dark)
                if font_scale != 1:
                    app.setStyleSheet(load_stylesheet(dark, theme._font_scale * font_scale, theme._font_family, theme_id=theme_id))
                window.resize(*size)
                registry.context = {"theme": theme_id, "mode": "dark" if dark else "light", "size": list(size), "font_scale": font_scale}
                for name, factory in factories:
                    dialog = factory()
                    registry.save("dialog-" + name, dialog, dialog=True)
                    if name == "login-cookie":
                        dialog._tabs.setCurrentIndex(1)
                        dialog._generate_btn.hide()
                        dialog._on_qr_generated("offline", "demo", qrcode.make("BiliFlow offline audit"))
                        dialog._poll_timer.stop()
                        registry.save("dialog-login-qr", dialog, dialog=True)
                        dialog._on_qr_status_result({"status": 86038})
                        registry.save("dialog-login-qr-expired", dialog, dialog=True)
                    dialog.reject()
                    dialog.deleteLater()
                panel = SettingsDialog(window._settings, window, background_store=window._background_store)
                for section in SettingsSection:
                    panel.show_section(section)
                    registry.save("dialog-settings-" + section.value, panel, dialog=True)
                panel.reject()
                panel.deleteLater()
                with patch.object(QDialog, "exec", lambda dialog: registry.save("dialog-media-copy", dialog, dialog=True)):
                    confirm_media_copy(item, window)
                with patch.object(QDialog, "exec", lambda dialog: registry.save("dialog-output-review", dialog, dialog=True)):
                    window._show_download_configuration()
                with patch.object(QMessageBox, "exec", lambda dialog: registry.save("dialog-copyright", dialog, dialog=True)):
                    window._confirm_copyright_acknowledgement()
                batch = capture._make_batch_dialog()
                batch._on_report(ImportReport(items=batch._resolved_items, issues=[ImportIssue("BVfailed", "离线示例：部分来源无法访问。请检查权限后重试。")]))
                registry.save("dialog-batch", batch, dialog=True)
                with patch.object(QDialog, "exec", lambda dialog: registry.save("dialog-source-errors", dialog, dialog=True)):
                    batch._show_errors()
                batch.reject()
                batch.deleteLater()
                picker = file_picker(window)
                for kind in ("directory", "open-file", "save-file"):
                    if kind == "directory":
                        dialog = picker.directory("选择保存目录", str(media.parent), lambda _: None)
                    elif kind == "open-file":
                        dialog = picker.open_file("选择背景图片", "", "图片 (*.png *.jpg *.webp)", lambda _: None)
                    else:
                        dialog = picker.save_file("导出 MP4", str(media.parent / "export.mp4"), "MP4 (*.mp4)", lambda _: None)
                    # Test the existing Qt file window; Windows native is external.
                    if dialog.testOption(dialog.Option.DontUseNativeDialog):
                        registry.save("dialog-file-" + kind, dialog, dialog=True)
                    dialog.reject()
                for entry in entries:
                    box = MessageBox(entry["title"], entry["text"], window, tone=entry["tone"],
                                     buttons=entry["buttons"], default=entry["default"])
                    registry.save(entry["id"], box, dialog=True)
                    box.reject()
                    box.deleteLater()
                sources = [{key: value for key, value in entry.items() if key not in {"buttons", "default"}} for entry in entries]
    (capture.OUTPUT_DIR / "message-entries.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(app, theme, window, capture, *, components_only=False, dialogs_only=False, fonts_only=False):
    if fonts_only:
        registry = Registry(app, capture)
        capture._populate_main_window(window)
        capture._populate_live_page(window, Path(app.property("docsTempRoot")) / "audit-live")
        capture_font_workspaces(app, theme, window, capture, registry)
        registry.write()
        return
    if not dialogs_only:
        for scale in (1, 1.25, 1.5):
            capture_components(app, theme, capture, scale)
    if not components_only:
        capture._populate_main_window(window)
        capture._populate_live_page(window, Path(app.property("docsTempRoot")) / "audit-live")
        registry = Registry(app, capture)
        capture_dialogs(app, theme, window, capture, registry)
        if not dialogs_only:
            original = capture._save_widget
            def observe(app, root, filename, popup=None):
                registry.context = {"theme": app.property("colorTheme"),
                                    "mode": "dark" if app.property("darkTheme") else "light",
                                    "size": [root.width(), root.height()], "font_scale": 1}
                registry.save(filename.removesuffix(".png"), root, dialog=isinstance(root, QDialog),
                              image_name=filename, write_image=False)
                original(app, root, filename, popup=popup)
            capture._save_widget = observe
            try:
                capture._capture_warm_workspaces(app, theme, window)
                window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(capture.OutputMode.VIDEO))
                capture._capture_warm_details(app, theme, window)
                capture._capture_refinement(app, theme, window)
                capture_backgrounds(app, theme, window, capture)
            finally:
                capture._save_widget = original
            capture_font_workspaces(app, theme, window, capture, registry)
        registry.write()


def capture_backgrounds(app, theme, window, capture):
    from bilibili_downloader.core.appearance import prepare_background
    from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
    from bilibili_downloader.gui.resources.paths import asset_path
    from bilibili_downloader.gui.settings_sections import SettingsSection
    prepared = prepare_background(Path(asset_path("nebula.jpg")))
    window._background_store.install(prepared)
    capture._populate_main_window(window)
    for theme_id in ("star_trail", "bilibili_blue"):
        window._settings.appearance.theme = theme_id
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for source, reference in (("none", ""), ("builtin", BUILTIN_BACKGROUNDS[0].reference), ("custom", prepared.reference)):
                for workspace in ("download", "live", "tasks", "settings"):
                    setattr(window._settings.appearance.backgrounds, workspace, reference)
                for width, height in ((900, 640), (1120, 760), (1320, 860)):
                    window.resize(width, height)
                    for workspace, select in (
                        ("download", lambda: window._show_workspace(0)),
                        ("live", lambda: window._show_workspace(1)),
                        ("tasks", lambda: window._show_tasks(0)),
                        ("settings", lambda: window._show_settings_tab(SettingsSection.DOWNLOAD)),
                    ):
                        select()
                        if workspace == "download":
                            window._download_tabs.setCurrentIndex(0)
                            window._workspace_scroll.verticalScrollBar().setValue(0)
                        capture._save_widget(app, window, f"detail-background-{theme_id}-{mode}-{source}-{workspace}-{width}.png")


def capture_font_workspaces(app, theme, window, capture, registry):
    """Small-screen typography with long content and 130 selected works."""
    from bilibili_downloader.gui.settings_sections import SettingsSection
    info = capture._demo_video().model_copy(update={
        "title": "星轨旅记：穿过漫长的夜色与城市街巷，记录沿途的每一束光。" * 8,
        "author": "一个很长的离线演示 UP 主昵称" * 5,
    })
    long_path = "~/Downloads/" + "长目录与 Unicode 演示/" * 12 + "BiliFlow"
    window._settings.output_dir = long_path
    window._output_summary.setText(long_path)
    window._on_resolve_success(info, [capture.StreamInfo(id=80, codecid=7)], [capture.StreamInfo(id=30280)], True)
    items = [info.model_copy(update={"bvid": f"BVfont{i:06d}", "cid": i}) for i in range(130)]
    window._batch_page._on_resolved(items, [])
    window._download_list.item(0, 0).setText(info.title)
    window._settings_page.load_settings(window._settings)
    checks = []
    for theme_id in ("star_trail", "bilibili_blue"):
        theme.set_color_theme(theme_id)
        for dark in (False, True):
            theme.apply_theme(dark)
            mode = "dark" if dark else "light"
            for scale in (1.25, 1.5):
                app.setStyleSheet(load_stylesheet(dark, theme._font_scale * scale, theme._font_family, theme_id=theme_id))
                window.resize(900, 640)
                for name, select in (
                    ("download", lambda: (window._show_workspace(0), window._download_tabs.setCurrentIndex(0))),
                    ("batch", lambda: (window._show_workspace(0), window._download_tabs.setCurrentIndex(1))),
                    ("live", lambda: window._show_workspace(1)),
                    ("tasks", lambda: window._show_tasks(0)),
                    ("settings", lambda: window._show_settings_tab(SettingsSection.DOWNLOAD)),
                ):
                    select()
                    window.show()
                    capture._flush_events(app)
                    scroll = window._workspace_scroll if name in ("download", "batch") else None
                    if scroll:
                        scroll.verticalScrollBar().setValue(0)
                    registry.context = {"theme": theme_id, "mode": mode, "size": [900, 640], "font_scale": scale}
                    registry.save(f"font-workspace-{name}", window)
                    checks.append({"theme": theme_id, "mode": mode, "font_scale": scale, "workspace": name,
                                   "size": [window.width(), window.height()],
                                   "horizontal_scroll": scroll.horizontalScrollBar().maximum() if scroll else None})
    (capture.OUTPUT_DIR / "font-workspace-checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
