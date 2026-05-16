"""Login dialog for QR code and SESSDATA input."""

import io
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QClipboard, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.api.login import LoginManager
from bilibili_downloader.gui.widgets.chinese_input import ChineseLineEdit


class LoginDialog(QDialog):
    """Dialog for Bilibili login via QR code or manual SESSDATA."""

    def __init__(self, current_sessdata: Optional[str], parent=None):
        super().__init__(parent)
        self._sessdata = current_sessdata
        self._login_manager = LoginManager()
        self._oauth_key = None
        self._poll_timer = None

        self.setWindowTitle("账号登录")
        self.setMinimumSize(400, 500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # -- Manual Cookie Tab (primary, since QR API is broken) --
        cookie_tab = QWidget()
        cookie_layout = QVBoxLayout(cookie_tab)

        # Instructions
        cookie_layout.addWidget(QLabel("获取 SESSDATA 的步骤："))

        steps = QTextEdit()
        steps.setReadOnly(True)
        steps.setMaximumHeight(130)
        steps.setHtml(
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>1.</b> 在浏览器中打开 <a href="https://www.bilibili.com">bilibili.com</a> 并登录</p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>2.</b> 按 <code>F12</code> 打开开发者工具</p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>3.</b> 切换到 <code>Application</code>（应用）选项卡</p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>4.</b> 左侧展开 <code>Cookies</code> → 点击 <code>https://www.bilibili.com</code></p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>5.</b> 在右侧列表中找到 <code>SESSDATA</code>，复制其值</p>'
            '<p style="margin:4px 0;font-size:13px;">'
            '<b>6.</b> 粘贴到下方输入框并点击"验证登录"</p>'
        )
        cookie_layout.addWidget(steps)

        cookie_layout.addWidget(QLabel("粘贴 SESSDATA 值："))
        self._cookie_input = ChineseLineEdit()
        self._cookie_input.setPlaceholderText("在此粘贴你的 SESSDATA 值")
        cookie_layout.addWidget(self._cookie_input)

        validate_btn = QPushButton("验证登录")
        validate_btn.setStyleSheet(
            "QPushButton { background-color: #00A1D6; color: white; "
            "padding: 6px 16px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #23a2d9; }"
        )
        validate_btn.clicked.connect(self._validate_cookie)
        cookie_layout.addWidget(validate_btn)

        cookie_layout.addStretch()
        tabs.addTab(cookie_tab, "手动输入 Cookie")

        # -- QR Code Tab (may not work due to B站 API changes) --
        qr_tab = QWidget()
        qr_layout = QVBoxLayout(qr_tab)

        # Warning banner
        warning = QLabel(
            "⚠ 扫码登录当前因B站API变更可能不可用，请使用上方手动输入Cookie方式。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "QLabel { background-color: #332200; color: #ffcc66; "
            "padding: 8px; border-radius: 4px; font-size: 12px; }"
        )
        qr_layout.addWidget(warning)

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setMinimumSize(250, 250)
        self._qr_label.setStyleSheet(
            "QLabel { background-color: #1e1e1e; border-radius: 4px; }"
        )
        self._qr_label.setText("点击下方二维码生成二维码")
        self._qr_label.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(self._qr_label)

        self._qr_status = QLabel("")
        self._qr_status.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(self._qr_status)

        # Generate button
        self._generate_btn = QPushButton("生成二维码")
        self._generate_btn.clicked.connect(self._on_generate)
        qr_layout.addWidget(self._generate_btn, alignment=Qt.AlignCenter)

        # Refresh button (shown when QR expires)
        self._refresh_btn = QPushButton("刷新二维码")
        self._refresh_btn.setStyleSheet(
            "QPushButton { background-color: #00A1D6; color: white; "
            "padding: 6px 16px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #23a2d9; }"
        )
        self._refresh_btn.clicked.connect(self._on_refresh_qr)
        self._refresh_btn.hide()
        qr_layout.addWidget(self._refresh_btn, alignment=Qt.AlignCenter)

        qr_layout.addStretch()
        tabs.addTab(qr_tab, "扫码登录（可能不可用）")

        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #00A1D6; color: white; "
            "padding: 6px 16px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #23a2d9; }"
        )
        btn_layout.addWidget(ok_btn)
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

    def _start_qr_generation(self):
        """Generate QR code and start polling for login, with retry."""
        import logging
        import time
        logger = logging.getLogger(__name__)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                url, oauth_key, qr_img = self._login_manager.generate_qr()
                self._oauth_key = oauth_key
                logger.info("QR code generated, key=%s...", oauth_key[:8])

                # Convert PIL to QPixmap
                buffer = io.BytesIO()
                qr_img.save(buffer, format="PNG")
                pixmap = QPixmap()
                pixmap.loadFromData(buffer.getvalue())
                pixmap = pixmap.scaled(
                    250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self._qr_label.setPixmap(pixmap)
                self._qr_label.setText("")

                # Start polling timer
                self._poll_timer = QTimer()
                self._poll_timer.timeout.connect(self._poll_qr_status)
                self._poll_timer.start(2000)
                return  # Success

            except Exception as e:
                logger.warning("QR generation attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

        # All retries failed
        self._qr_label.setText("二维码生成失败，请检查网络")
        self._qr_status.setText("点击下方按钮重试")
        self._refresh_btn.show()

    def _poll_qr_status(self):
        """Check QR login status."""
        import logging
        logger = logging.getLogger(__name__)

        if self._oauth_key is None:
            return

        try:
            result = self._login_manager.check_qr_status(self._oauth_key)
            status = result.get("status", -1)
            logger.debug("QR poll status: %s", status)

            if status == 0:
                # Login successful
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
                self._poll_timer.stop()
                self._refresh_btn.show()
            else:
                # Unknown status — log for debugging
                logger.warning("Unknown QR status code: %s", status)
        except Exception as e:
            logger.exception("QR status check failed")
            self._qr_status.setText(f"状态检查异常：{e}")

    def _validate_cookie(self):
        """Validate the manually entered SESSDATA."""
        sessdata = self._cookie_input.text().strip()
        if not sessdata:
            QMessageBox.warning(self, "验证", "请输入 SESSDATA 值")
            return

        valid = self._login_manager.validate_sessdata(sessdata)

        if valid:
            self._sessdata = sessdata
            QMessageBox.information(self, "验证", "Cookie 有效！")
            self.accept()
        else:
            QMessageBox.warning(self, "验证", "Cookie 无效或已过期")

    def get_sessdata(self) -> Optional[str]:
        """Return the SESSDATA from login."""
        return self._sessdata

    def closeEvent(self, event):
        """Clean up resources."""
        if self._poll_timer:
            self._poll_timer.stop()
        self._login_manager.close()
        super().closeEvent(event)
