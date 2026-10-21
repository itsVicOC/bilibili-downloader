"""Login dialog for QR code and SESSDATA input."""

import io
import logging
from typing import Optional

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from bilibili_downloader.api.auth import filter_auth_cookies, parse_cookie_input
from bilibili_downloader.api.login import LoginManager
from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit
from bilibili_downloader.gui.widgets.components import (
    ElidedLabel,
    MessageBox,
    StatusBadge,
    line_icon,
    palette,
)

logger = logging.getLogger(__name__)


class _QRGenerateWorker(QObject):
    finished = Signal(str, str, object)
    error = Signal(str)


class _QRGenerateRunner(QRunnable):
    def __init__(self, worker: _QRGenerateWorker):
        super().__init__()
        self._worker = worker
        self.setAutoDelete(True)

    def run(self):
        manager = LoginManager()
        try:
            url, qrcode_key, qr_img = manager.generate_qr()
            self._worker.finished.emit(url, qrcode_key, qr_img)
        except Exception as e:  # noqa: BLE001
            self._worker.error.emit(redact_sensitive_text(e))
        finally:
            manager.close()


class _QRPollWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)


class _QRPollRunner(QRunnable):
    def __init__(self, worker: _QRPollWorker, qrcode_key: str):
        super().__init__()
        self._worker = worker
        self._qrcode_key = qrcode_key
        self.setAutoDelete(True)

    def run(self):
        manager = LoginManager()
        try:
            self._worker.finished.emit(manager.check_qr_status(self._qrcode_key))
        except Exception as e:  # noqa: BLE001
            self._worker.error.emit(redact_sensitive_text(e))
        finally:
            manager.close()


class _CookieValidateWorker(QObject):
    finished = Signal(bool)
    error = Signal(str)


class _CookieValidateRunner(QRunnable):
    def __init__(self, worker: _CookieValidateWorker, cookies: dict[str, str]):
        super().__init__()
        self._worker = worker
        self._cookies = cookies
        self.setAutoDelete(True)

    def run(self):
        manager = LoginManager()
        try:
            self._worker.finished.emit(bool(manager.validate_cookies(self._cookies)))
        except Exception as e:  # noqa: BLE001
            self._worker.error.emit(redact_sensitive_text(e))
        finally:
            manager.close()


class LoginDialog(QDialog):
    """Dialog for Bilibili login via QR code or manual SESSDATA."""

    def __init__(self, current_sessdata: Optional[str] | dict[str, str], parent=None, *, account=None, avatar_icon=None, account_valid=None, account_state=None):
        super().__init__(parent)
        if isinstance(current_sessdata, dict):
            self._auth_cookies = filter_auth_cookies(current_sessdata)
        else:
            self._auth_cookies = (
                {"SESSDATA": current_sessdata} if current_sessdata else {}
            )
        self._sessdata = self._auth_cookies.get("SESSDATA")
        self._oauth_key = None
        self._poll_timer = None
        self._poll_in_flight = False
        self._pending_cookies: dict[str, str] = {}
        self._validation_source = "manual"
        self._logout_requested = False
        self._account = account or {}
        self._avatar_icon = avatar_icon
        self._account_state = account_state or ("valid" if account_valid else "expired" if account_valid is False else "unknown")
        self._generation = 0
        self._finished = False
        self._management = bool(self._sessdata) and account_valid is not False
        self._account_expired = bool(self._sessdata) and account_valid is False

        self._login_active = not self._management
        self.setWindowTitle("当前账号" if self._management else "账号登录")
        self.setMinimumSize(480, 560)
        self.resize(500, 600)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        margin = 24 if self._management else 20
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(12 if self._management else 8)

        title = QLabel("当前账号" if self._management else "连接 B 站账号")
        self._title = title
        title.setObjectName("DialogTitle")
        caption = QLabel("登录已失效，请重新验证账号" if self._account_expired else "管理当前连接的 B 站账号" if self._management else "登录后可解析当前账号已获完整播放权限的内容")
        self._caption = caption
        caption.setObjectName("DialogCaption")
        layout.addWidget(title)
        layout.addWidget(caption)
        title.setVisible(not self._management)
        caption.setVisible(not self._management)
        rights_notice = QLabel("账号可观看不等于获得永久复制、传播或商业使用授权。")
        rights_notice.setObjectName("MetaLabel")
        rights_notice.setWordWrap(True)
        self._rights_notice = rights_notice
        if self._management:
            rights_notice.setAlignment(Qt.AlignCenter)

        if self._management:
            self._account_card = QFrame()
            self._account_card.setObjectName("AccountIdentity")
            card = QVBoxLayout(self._account_card)
            card.setContentsMargins(0, 8, 0, 4)
            card.setSpacing(16)
            self._avatar_label = QLabel()
            self._avatar_label.setFixedSize(64, 64)
            card.addWidget(self._avatar_label, alignment=Qt.AlignHCenter)
            self._account_name = ElidedLabel()
            self._account_name.setObjectName("AccountName")
            self._account_name.setAlignment(Qt.AlignCenter)
            card.addWidget(self._account_name)

            self._account_details = QFrame()
            self._account_details.setObjectName("AccountDetails")
            self._account_details.setFixedWidth(240)
            details = QVBoxLayout(self._account_details)
            details.setContentsMargins(16, 0, 16, 0)
            details.setSpacing(0)
            self._account_uid = QLabel()
            self._account_uid.setObjectName("AccountValue")
            self._account_uid.setTextFormat(Qt.PlainText)
            self._account_uid.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            self._account_uid.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self._account_uid.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._account_member = QLabel()
            self._account_member.setObjectName("AccountValue")
            self._account_status = StatusBadge("登录状态待确认", "warning")
            for index, (label, value) in enumerate((
                ("UID", self._account_uid),
                ("会员信息", self._account_member),
                ("登录状态", self._account_status),
            )):
                if index:
                    divider = QFrame()
                    divider.setObjectName("AccountDivider")
                    divider.setFixedHeight(1)
                    details.addWidget(divider)
                row = QHBoxLayout()
                row.setContentsMargins(0, 10, 0, 10)
                row.setSpacing(20)
                key = QLabel(label)
                key.setObjectName("MetaLabel")
                value.setAccessibleName(label)
                row.addWidget(key)
                row.addStretch()
                row.addWidget(value, 1 if value is self._account_uid else 0)
                details.addLayout(row)
            card.addWidget(self._account_details, alignment=Qt.AlignHCenter)
            self._account_detail = QLabel()
            self._account_detail.setObjectName("MetaLabel")
            self._account_detail.setWordWrap(True)
            card.addWidget(self._account_detail)
            self._switch_button = QPushButton("切换账号")
            self._switch_button.setObjectName("PrimaryButton")
            self._switch_button.setAutoDefault(False)
            self._switch_button.clicked.connect(self._show_login_methods)
            layout.addWidget(self._account_card)
            self.set_account(self._account, self._avatar_icon, account_state=self._account_state)

        self._tabs = QTabWidget()

        # -- Manual Cookie Tab --
        cookie_tab = QWidget()
        cookie_layout = QVBoxLayout(cookie_tab)
        cookie_layout.setContentsMargins(14, 14, 14, 14)
        cookie_layout.setSpacing(10)

        # Instructions
        steps_label = QLabel("获取 SESSDATA 的步骤")
        steps_label.setObjectName("SectionTitle")
        cookie_layout.addWidget(steps_label)

        self._instructions = QLabel()
        self._instructions.setObjectName("LoginInstructions")
        self._instructions.setWordWrap(True)
        self._instructions.setOpenExternalLinks(True)
        self._instructions.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._instructions.setAttribute(Qt.WA_MacShowFocusRect, False)
        self._instructions.setText(
            '<p style="margin:4px 0;">'
            '<b>1.</b> 登录 <a href="https://www.bilibili.com">bilibili.com</a></p>'
            '<p style="margin:4px 0;">'
            "<b>2.</b> 打开开发者工具：Windows/Linux 按 <code>F12</code>，"
            "macOS 按 <code>Command+Option+I</code></p>"
            '<p style="margin:4px 0;">'
            "<b>3.</b> 进入 <code>Application</code>（应用）→ "
            "<code>Cookies</code> → <code>bilibili.com</code></p>"
            '<p style="margin:4px 0;">'
            "<b>4.</b> 复制 <code>SESSDATA</code> 的值并粘贴到下方</p>"
        )
        self._instruction_source = self._instructions.text()
        self._sync_instruction_color()
        cookie_layout.addWidget(self._instructions)

        input_label = QLabel("粘贴 SESSDATA 值或完整 Cookie 字符串")
        input_label.setObjectName("MetaLabel")
        cookie_layout.addWidget(input_label)
        self._cookie_input = ChineseLineEdit()
        self._cookie_input.setPlaceholderText("SESSDATA 值，或浏览器 Cookie 字符串")
        self._cookie_input.setEchoMode(QLineEdit.Password)
        cookie_input_row = QHBoxLayout()
        cookie_input_row.addWidget(self._cookie_input, 1)
        self._cookie_visibility_btn = QPushButton("显示")
        self._cookie_visibility_btn.setObjectName("SubtleButton")
        self._cookie_visibility_btn.setCheckable(True)
        self._cookie_visibility_btn.toggled.connect(self._toggle_cookie_visibility)
        cookie_input_row.addWidget(self._cookie_visibility_btn)
        cookie_layout.addLayout(cookie_input_row)

        self._validate_btn = QPushButton("验证登录")
        self._validate_btn.setObjectName("PrimaryButton")
        self._validate_btn.clicked.connect(self._validate_cookie)
        cookie_layout.addWidget(self._validate_btn)

        cookie_layout.addStretch()
        self._tabs.addTab(self._make_scroll_tab(cookie_tab), "手动输入 Cookie")

        # -- QR Code Tab --
        qr_tab = QWidget()
        qr_layout = QVBoxLayout(qr_tab)
        qr_layout.setContentsMargins(8, 4, 8, 4)
        qr_layout.setSpacing(8)

        qr_hint = QLabel("使用哔哩哔哩客户端扫码，在手机端确认。")
        qr_hint.setWordWrap(True)
        qr_hint.setObjectName("DialogCaption")
        qr_layout.addWidget(qr_hint)

        self._qr_label = QLabel()
        self._qr_label.setObjectName("EmptyCover")
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setFixedSize(220, 220)
        self._qr_label.setText("点击下方按钮生成二维码")
        qr_layout.addWidget(self._qr_label, alignment=Qt.AlignCenter)

        self._qr_status = QLabel("")
        self._qr_status.setAlignment(Qt.AlignCenter)
        self._qr_status.setMinimumHeight(20)
        qr_layout.addWidget(self._qr_status)

        # Generate button
        self._generate_btn = QPushButton("生成二维码")
        self._generate_btn.setObjectName("PrimaryButton")
        self._generate_btn.clicked.connect(self._on_generate)
        qr_layout.addWidget(self._generate_btn, alignment=Qt.AlignCenter)

        # Refresh button (shown when QR expires)
        self._refresh_btn = QPushButton("刷新二维码")
        self._refresh_btn.setObjectName("PrimaryButton")
        self._refresh_btn.clicked.connect(self._on_refresh_qr)
        self._refresh_btn.hide()
        qr_layout.addWidget(self._refresh_btn, alignment=Qt.AlignCenter)

        qr_layout.addStretch()
        self._tabs.addTab(qr_tab, "扫码登录")
        self._tabs.setCurrentIndex(1)

        layout.addWidget(self._tabs, 1)

        self._overview_stretch = layout.count()
        layout.addStretch(1 if self._management else 0)
        layout.addWidget(rights_notice)
        self._back_button = QPushButton("返回当前账号")
        self._back_button.setObjectName("TextButton")
        self._back_button.clicked.connect(self._show_account)
        self._back_button.hide()
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addWidget(self._back_button)
        if self._sessdata:
            logout_btn = QPushButton("退出登录")
            logout_btn.setObjectName("TableRemoveButton")
            logout_btn.setAutoDefault(False)
            logout_btn.clicked.connect(self._logout)
            btn_layout.addWidget(logout_btn)
        btn_layout.addStretch()
        cancel_btn = QPushButton("关闭")
        cancel_btn.setObjectName("SubtleButton")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._close_button = cancel_btn
        if self._management:
            btn_layout.addWidget(self._switch_button)
        layout.addLayout(btn_layout)
        if self._management:
            self._tabs.hide()
            self._fit_account()
            self._account_uid.setFocus(Qt.OtherFocusReason)

    def _fit_account(self):
        self.ensurePolished()
        self.layout().invalidate()
        height = max(400, self.layout().minimumSize().height())
        self.setMinimumHeight(height)
        self.resize(500, height)

    def set_account(self, account, avatar_icon=None, account_valid=None, account_state=None):
        self._account = account or {}
        self._avatar_icon = avatar_icon
        self._account_state = account_state or ("valid" if account_valid else "expired" if account_valid is False else "unknown")
        if not hasattr(self, "_account_name") or self._finished:
            return
        name = str(self._account.get("uname") or "已保存账号凭据")
        self._account_name.set_full_text(name)
        self._account_name.ensurePolished()
        self._account_name.setMinimumHeight(self._account_name.fontMetrics().height() + 4)
        self._account_name.setToolTip(name)
        self._account_uid.setText(str(self._account["mid"]) if self._account.get("mid") else "暂不可用")
        vip = self._account.get("vip") or {}
        member_known = self._account.get("vipStatus") is not None or vip.get("status") is not None
        member = "大会员" if self._account.get("vipStatus") or vip.get("status") else "普通会员"
        self._account_member.setText(member if member_known else "会员状态待确认")
        states = {
            "valid": ("已登录", "success", "当前账号已连接，可切换或退出登录。"),
            "checking": ("正在检查", "active", "正在确认登录状态，账号信息暂时保留。"),
            "unknown": ("暂时无法确认", "warning", "暂时无法连接 B 站，可稍后重试或切换账号。"),
            "expired": ("登录已失效", "warning", "请重新登录以继续使用需要账号权限的内容。"),
        }
        label, tone, detail = states[self._account_state]
        self._account_status.setText(label)
        self._account_status.set_tone(tone)
        self._account_detail.setText(detail)
        self._account_detail.setVisible(self._account_state != "valid")
        icon = avatar_icon if avatar_icon is not None and not avatar_icon.isNull() else line_icon("account", size=64)
        dpr = self.devicePixelRatioF()
        size = round(64 * dpr)
        source = icon.pixmap(size, size)
        avatar = QPixmap(size, size)
        avatar.fill(Qt.transparent)
        painter = QPainter(avatar)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addEllipse(0, 0, size, size)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, size, size, source)
        painter.end()
        avatar.setDevicePixelRatio(dpr)
        self._avatar_label.setPixmap(avatar)
        if hasattr(self, "_tabs") and not self._login_active:
            self._fit_account()

    def _reset_attempt(self):
        self._generation += 1
        if self._poll_timer:
            self._poll_timer.stop()
        self._oauth_key = None
        self._poll_in_flight = False
        self._pending_cookies = {}
        self._validate_btn.setEnabled(True)
        self._validate_btn.setText("验证登录")

    def _deliver(self, generation, callback, *args):
        if isValid(self) and not self._finished and self._login_active and generation == self._generation:
            callback(*args)

    def _show_login_methods(self):
        self._reset_attempt()
        self._login_active = True
        self._tabs.setCurrentIndex(1)
        if hasattr(self, "_account_card"):
            self._account_card.hide()
            self._back_button.show()
            self._switch_button.hide()
        self.setWindowTitle("切换账号")
        self._title.show()
        self._caption.show()
        self._rights_notice.setAlignment(Qt.AlignLeft)
        self.layout().setContentsMargins(20, 20, 20, 20)
        self.layout().setSpacing(8)
        self.layout().setStretch(self._overview_stretch, 0)
        self._title.setText("切换账号")
        self._caption.setText("验证新账号成功后才会替换当前账号，关闭可保留原登录。")
        self._caption.setWordWrap(True)
        self._tabs.show()
        self.setMinimumHeight(560)
        self.resize(500, 600)

    def _show_account(self):
        self._reset_attempt()
        self._login_active = False
        self._cookie_input.clear()
        self._cookie_visibility_btn.setChecked(False)
        self._qr_label.clear()
        self._qr_label.setText("点击下方按钮生成二维码")
        self._qr_status.clear()
        self._refresh_btn.hide()
        self._generate_btn.show()
        self._tabs.hide()
        self._back_button.hide()
        self._account_card.show()
        self._switch_button.show()
        self.setWindowTitle("当前账号")
        self._title.hide()
        self._caption.hide()
        self._rights_notice.setAlignment(Qt.AlignCenter)
        self.layout().setContentsMargins(24, 24, 24, 24)
        self.layout().setSpacing(12)
        self.layout().setStretch(self._overview_stretch, 1)
        self._account_uid.setFocus(Qt.OtherFocusReason)
        self._fit_account()

    def done(self, result):
        self._finished = True
        self._generation += 1
        if self._poll_timer:
            self._poll_timer.stop()
        super().done(result)

    def _sync_instruction_color(self):
        self._instructions.setText(
            self._instruction_source.replace(
                "<a href=", f'<a style="color:{palette().active_text}" href='
            )
        )

    def changeEvent(self, event):
        if hasattr(self, "_instruction_source"):
            self._sync_instruction_color()
        super().changeEvent(event)

    @staticmethod
    def _make_scroll_tab(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("DialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _on_generate(self):
        """Generate QR code."""
        self._reset_attempt()
        self._generate_btn.hide()
        self._refresh_btn.hide()
        self._qr_label.setText("正在生成二维码...")
        self._qr_status.setText("")
        self._start_qr_generation()

    def _on_refresh_qr(self):
        """Regenerate QR code after expiration."""
        self._reset_attempt()
        self._refresh_btn.hide()
        self._qr_label.setText("正在生成二维码...")
        self._qr_status.setText("")
        self._start_qr_generation()

    def _start_qr_generation(self, attempt: int = 0):
        """Generate QR code and start polling for login, with async retry."""
        self._qr_generate_attempt = attempt
        self._qr_worker = _QRGenerateWorker()
        generation = self._generation
        self._qr_worker.finished.connect(lambda *args: self._deliver(generation, self._on_qr_generated, *args))
        self._qr_worker.error.connect(lambda error: self._deliver(generation, self._on_qr_generate_error, error))
        self._qr_runner = _QRGenerateRunner(self._qr_worker)
        QThreadPool.globalInstance().start(self._qr_runner)

    def _on_qr_generated(self, _url: str, oauth_key: str, qr_img: Image.Image):
        """Render generated QR code and start polling."""
        self._oauth_key = oauth_key
        logger.info("QR code generated")

        buffer = io.BytesIO()
        qr_img.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        pixmap = pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._qr_label.setPixmap(pixmap)
        self._qr_label.setText("")

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_qr_status)
        self._poll_timer.start(2000)

    def _on_qr_generate_error(self, error: str):
        """Retry QR generation without blocking the dialog."""
        attempt = getattr(self, "_qr_generate_attempt", 0)
        max_retries = 3
        logger.warning("QR generation attempt %d failed: %s", attempt + 1, error)
        if attempt < max_retries - 1:
            generation = self._generation
            QTimer.singleShot(1000, lambda: self._deliver(generation, self._start_qr_generation, attempt + 1))
            return

        self._qr_label.setText("二维码生成失败，请检查网络")
        self._qr_status.setText("点击下方按钮重试")
        self._refresh_btn.show()

    def _poll_qr_status(self):
        """Check QR login status."""
        if self._oauth_key is None or self._poll_in_flight:
            return

        self._poll_in_flight = True
        self._poll_worker = _QRPollWorker()
        generation = self._generation
        self._poll_worker.finished.connect(lambda result: self._deliver(generation, self._on_qr_status_result, result))
        self._poll_worker.error.connect(lambda error: self._deliver(generation, self._on_qr_status_error, error))
        self._poll_runner = _QRPollRunner(self._poll_worker, self._oauth_key)
        QThreadPool.globalInstance().start(self._poll_runner)

    def _on_qr_status_result(self, result: dict):
        """Handle QR login status fetched by a background worker."""
        self._poll_in_flight = False
        status = result.get("status", -1)
        logger.debug("QR poll status: %s", status)

        if status == 0:
            if self._poll_timer:
                self._poll_timer.stop()
            self._qr_status.setText("登录成功！")
            cookies = result.get("cookies", {})
            if "SESSDATA" in cookies:
                self._qr_status.setText("正在验证账号...")
                self._begin_cookie_validation(cookies, source="qr")
            else:
                MessageBox(
                    "登录",
                    "登录成功但未获取到 SESSDATA，请使用手动输入 Cookie 方式。",
                    self,
                    tone="warning",
                ).exec()

        elif status == 86101:
            self._qr_status.setText("等待扫码...")
        elif status == 86090:
            self._qr_status.setText("已扫码，请在手机上确认...")
        elif status == 86038:
            self._qr_status.setText("二维码已过期，点击下方刷新")
            if self._poll_timer:
                self._poll_timer.stop()
            self._refresh_btn.show()
        else:
            logger.warning("Unknown QR status code: %s", status)

    def _on_qr_status_error(self, error: str):
        """Show QR status errors without freezing the dialog."""
        self._poll_in_flight = False
        logger.warning("QR status check failed: %s", error)
        self._qr_status.setText("暂时无法确认扫码状态，正在重试…")
        self._qr_status.setToolTip(f"状态检查异常：{error}")

    def _validate_cookie(self):
        """Validate the manually entered SESSDATA."""
        bundle = parse_cookie_input(self._cookie_input.text())
        if not bundle.is_authenticated:
            MessageBox("验证", "请输入 SESSDATA 值", self, tone="warning").exec()
            return

        self._begin_cookie_validation(bundle.cookies, source="manual")

    def _begin_cookie_validation(self, cookies: dict[str, str], *, source: str) -> None:
        self._reset_attempt()
        self._pending_cookies = filter_auth_cookies(cookies)
        self._validation_source = source
        if source == "manual":
            self._validate_btn.setEnabled(False)
            self._validate_btn.setText("验证中...")
        self._cookie_worker = _CookieValidateWorker()
        generation = self._generation
        self._cookie_worker.finished.connect(lambda valid: self._deliver(generation, self._on_cookie_validated, valid))
        self._cookie_worker.error.connect(lambda error: self._deliver(generation, self._on_cookie_validate_error, error))
        self._cookie_runner = _CookieValidateRunner(
            self._cookie_worker, self._pending_cookies
        )
        QThreadPool.globalInstance().start(self._cookie_runner)

    def _toggle_cookie_visibility(self, visible: bool):
        self._cookie_input.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )
        self._cookie_visibility_btn.setText("隐藏" if visible else "显示")

    def _logout(self):
        box = MessageBox(
            "退出登录",
            "确认从本机凭据库和配置中清除 B 站登录信息吗？",
            self,
            tone="warning",
            buttons=QMessageBox.Yes | QMessageBox.No,
            default=QMessageBox.No,
        )
        box.button(QMessageBox.Yes).setText("退出登录")
        box.button(QMessageBox.Yes).setObjectName("DangerButton")
        if box.exec() == QMessageBox.Yes:
            self._sessdata = None
            self._auth_cookies = {}
            self._logout_requested = True
            self.accept()

    def _on_cookie_validated(self, valid: bool):
        """Handle SESSDATA validation result."""
        self._validate_btn.setEnabled(True)
        self._validate_btn.setText("验证登录")
        if valid:
            self._auth_cookies = self._pending_cookies
            self._sessdata = self._auth_cookies.get("SESSDATA")
            if self._validation_source == "manual":
                MessageBox("验证", "Cookie 有效！", self, tone="success").exec()
            else:
                self._qr_status.setText("登录成功！")
            self.accept()
        else:
            if self._validation_source == "qr":
                self._qr_status.setText("登录验证失败，请重新生成二维码")
                self._refresh_btn.show()
            MessageBox("验证", "Cookie 无效或已过期", self, tone="warning").exec()

    def _on_cookie_validate_error(self, error: str):
        self._validate_btn.setEnabled(True)
        self._validate_btn.setText("验证登录")
        if self._validation_source == "qr":
            self._qr_status.setText("登录验证异常，请重试")
            self._refresh_btn.show()
        MessageBox("验证", f"验证失败：{error}", self, tone="danger").exec()

    def get_sessdata(self) -> Optional[str]:
        """Return the SESSDATA from login."""
        return self._sessdata

    def get_auth_cookies(self) -> dict[str, str]:
        """Return only allow-listed cookies from the completed login."""
        return dict(self._auth_cookies)

    @property
    def logout_requested(self) -> bool:
        return self._logout_requested

    def closeEvent(self, event):
        """Clean up resources."""
        if self._poll_timer:
            self._poll_timer.stop()
        super().closeEvent(event)
