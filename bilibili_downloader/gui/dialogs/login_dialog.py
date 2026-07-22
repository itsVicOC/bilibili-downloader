"""Login dialog for QR code and SESSDATA input."""

import io
import logging
from typing import Optional

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.api.login import LoginManager
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit

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
            self._worker.error.emit(str(e))
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
            self._worker.error.emit(str(e))
        finally:
            manager.close()


class _CookieValidateWorker(QObject):
    finished = Signal(bool)
    error = Signal(str)


class _CookieValidateRunner(QRunnable):
    def __init__(self, worker: _CookieValidateWorker, sessdata: str):
        super().__init__()
        self._worker = worker
        self._sessdata = sessdata
        self.setAutoDelete(True)

    def run(self):
        manager = LoginManager()
        try:
            self._worker.finished.emit(manager.validate_sessdata(self._sessdata))
        except Exception as e:  # noqa: BLE001
            self._worker.error.emit(str(e))
        finally:
            manager.close()


class LoginDialog(QDialog):
    """Dialog for Bilibili login via QR code or manual SESSDATA."""

    def __init__(self, current_sessdata: Optional[str], parent=None):
        super().__init__(parent)
        self._sessdata = current_sessdata
        self._oauth_key = None
        self._poll_timer = None
        self._poll_in_flight = False
        self._pending_sessdata = ""
        self._logout_requested = False

        self.setWindowTitle("账号登录")
        self.setMinimumSize(480, 540)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        title = QLabel("连接 B 站账号")
        title.setObjectName("DialogTitle")
        caption = QLabel("登录后可解析会员画质与账号专属内容")
        caption.setObjectName("DialogCaption")
        layout.addWidget(title)
        layout.addWidget(caption)

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
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>1.</b> 登录 <a href="https://www.bilibili.com">bilibili.com</a></p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>2.</b> 打开开发者工具：Windows/Linux 按 <code>F12</code>，'
            'macOS 按 <code>Command+Option+I</code></p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>3.</b> 进入 <code>Application</code>（应用）→ '
            '<code>Cookies</code> → <code>bilibili.com</code></p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>4.</b> 复制 <code>SESSDATA</code> 的值并粘贴到下方</p>'
        )
        cookie_layout.addWidget(self._instructions)

        input_label = QLabel("粘贴 SESSDATA 值")
        input_label.setObjectName("MetaLabel")
        cookie_layout.addWidget(input_label)
        self._cookie_input = ChineseLineEdit()
        self._cookie_input.setPlaceholderText("在此粘贴你的 SESSDATA 值")
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
        self._tabs.addTab(cookie_tab, "手动输入 Cookie")

        # -- QR Code Tab --
        qr_tab = QWidget()
        qr_layout = QVBoxLayout(qr_tab)
        qr_layout.setContentsMargins(14, 14, 14, 14)
        qr_layout.setSpacing(12)

        qr_hint = QLabel("请使用哔哩哔哩客户端扫码，并在手机端确认登录。")
        qr_hint.setWordWrap(True)
        qr_hint.setObjectName("WarningBanner")
        qr_layout.addWidget(qr_hint)

        self._qr_label = QLabel()
        self._qr_label.setObjectName("EmptyCover")
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setMinimumSize(250, 250)
        self._qr_label.setText("点击下方按钮生成二维码")
        self._qr_label.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(self._qr_label)

        self._qr_status = QLabel("")
        self._qr_status.setAlignment(Qt.AlignCenter)
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

        layout.addWidget(self._tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        if self._sessdata:
            logout_btn = QPushButton("退出登录")
            logout_btn.setObjectName("DangerButton")
            logout_btn.clicked.connect(self._logout)
            btn_layout.addWidget(logout_btn)
        btn_layout.addStretch()
        cancel_btn = QPushButton("关闭")
        cancel_btn.setObjectName("SubtleButton")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_generate(self):
        """Generate QR code."""
        self._generate_btn.hide()
        self._refresh_btn.hide()
        self._qr_label.setText("正在生成二维码...")
        self._qr_status.setText("")
        self._start_qr_generation()

    def _on_refresh_qr(self):
        """Regenerate QR code after expiration."""
        self._refresh_btn.hide()
        self._qr_label.setText("正在生成二维码...")
        self._qr_status.setText("")
        self._start_qr_generation()

    def _start_qr_generation(self, attempt: int = 0):
        """Generate QR code and start polling for login, with async retry."""
        self._qr_generate_attempt = attempt
        self._qr_worker = _QRGenerateWorker()
        self._qr_worker.finished.connect(self._on_qr_generated)
        self._qr_worker.error.connect(self._on_qr_generate_error)
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
        pixmap = pixmap.scaled(
            250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._qr_label.setPixmap(pixmap)
        self._qr_label.setText("")

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_qr_status)
        self._poll_timer.start(2000)

    def _on_qr_generate_error(self, error: str):
        """Retry QR generation without blocking the dialog."""
        attempt = getattr(self, "_qr_generate_attempt", 0)
        max_retries = 3
        logger.warning("QR generation attempt %d failed: %s", attempt + 1, error)
        if attempt < max_retries - 1:
            QTimer.singleShot(1000, lambda: self._start_qr_generation(attempt + 1))
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
        self._poll_worker.finished.connect(self._on_qr_status_result)
        self._poll_worker.error.connect(self._on_qr_status_error)
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
                self._sessdata = cookies["SESSDATA"]
                self.accept()
            else:
                QMessageBox.warning(
                    self, "登录",
                    "登录成功但未获取到 SESSDATA，请使用手动输入 Cookie 方式。",
                )

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
        self._qr_status.setText(f"状态检查异常：{error}")

    def _validate_cookie(self):
        """Validate the manually entered SESSDATA."""
        sessdata = self._cookie_input.text().strip()
        if not sessdata:
            QMessageBox.warning(self, "验证", "请输入 SESSDATA 值")
            return

        self._pending_sessdata = sessdata
        self._validate_btn.setEnabled(False)
        self._validate_btn.setText("验证中...")
        self._cookie_worker = _CookieValidateWorker()
        self._cookie_worker.finished.connect(self._on_cookie_validated)
        self._cookie_worker.error.connect(self._on_cookie_validate_error)
        self._cookie_runner = _CookieValidateRunner(self._cookie_worker, sessdata)
        QThreadPool.globalInstance().start(self._cookie_runner)

    def _toggle_cookie_visibility(self, visible: bool):
        self._cookie_input.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )
        self._cookie_visibility_btn.setText("隐藏" if visible else "显示")

    def _logout(self):
        answer = QMessageBox.question(
            self,
            "退出登录",
            "确认从本机凭据库和配置中清除 B 站登录信息吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._sessdata = None
            self._logout_requested = True
            self.accept()

    def _on_cookie_validated(self, valid: bool):
        """Handle SESSDATA validation result."""
        self._validate_btn.setEnabled(True)
        self._validate_btn.setText("验证登录")
        if valid:
            self._sessdata = self._pending_sessdata
            QMessageBox.information(self, "验证", "Cookie 有效！")
            self.accept()
        else:
            QMessageBox.warning(self, "验证", "Cookie 无效或已过期")

    def _on_cookie_validate_error(self, error: str):
        self._validate_btn.setEnabled(True)
        self._validate_btn.setText("验证登录")
        QMessageBox.warning(self, "验证", f"验证失败：{error}")

    def get_sessdata(self) -> Optional[str]:
        """Return the SESSDATA from login."""
        return self._sessdata

    @property
    def logout_requested(self) -> bool:
        return self._logout_requested

    def closeEvent(self, event):
        """Clean up resources."""
        if self._poll_timer:
            self._poll_timer.stop()
        super().closeEvent(event)
