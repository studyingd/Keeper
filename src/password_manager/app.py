"""PySide6 desktop application for the local encrypted vault."""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFont, QIcon, QPainter, QPalette, QRadialGradient
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from password_manager.generator import (  # re-exported for backwards compatibility
    GENERATED_PASSWORD_LENGTH,
    PASSWORD_CHARSETS,
    STRENGTH_LABELS,
    STRENGTH_THRESHOLDS,
    entropy_bits,
    generate_password,
    strength_label,
    strength_level,
)
from password_manager.models import Credential, CredentialDraft, Entry, EntryDraft
from password_manager.services.actions import (
    connect_rdp,
    connect_ssh,
    extract_url,
    open_url,
    set_concealed_clipboard,
    system_idle_seconds,
)
from password_manager.ui.icons import credential_icon_name, icon, kind_icon_name
from password_manager.ui.fonts import ensure_fonts_loaded
from password_manager.ui.motion import dialog_spring, drop_shadow, fade_widget, glow, pulse_forever
from password_manager.ui.theme import (
    ACCENT,
    ACCENT_INK,
    BG,
    BG_DEEP,
    BORDER,
    BORDER_SOFT,
    BORDER_STRONG,
    DANGER,
    GLOW_BLUE,
    GLOW_TEAL,
    OK,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
    STYLESHEET,
)
from password_manager.ui.widgets import (
    Card,
    CharSetToggles,
    PasswordGenerator,
    StrengthMeter,
    TagEdit,
    Toast,
)
from password_manager.controller import (  # re-exported for backwards compatibility
    EXPORT_COLUMNS,
    IDLE_POLL_MS,
    THROTTLE_FILE_NAME,
    UNLOCK_FAILURE_DELAY_MAX_MS,
    UNLOCK_FAILURE_DELAY_MIN_MS,
    acquire_single_instance,
    collect_export_rows,
    load_unlock_throttle,
    save_unlock_throttle,
    single_instance_name,
    unlock_failure_delay_ms,
    write_export_xlsx,
)
from password_manager.vault.repository import (
    MAX_ENTRY_TAGS,
    VaultRepository,
    normalize_entry_tags,
    validate_credential_draft,
    validate_entry_draft,
)

APP_NAME = "Keeper"
DEFAULT_VAULT = Path(os.environ.get("PASSWORD_MANAGER_VAULT", Path.home() / ".keeper" / "vault.sqlcipher"))

SERVER_TAG_SUGGESTIONS = ["MySQL", "Redis", "Nginx", "Docker", "数据库", "生产环境"]
APPLICATION_TAG_SUGGESTIONS = ["云平台", "开发", "工作", "个人", "AI", "邮箱"]


def focus_existing_window(window: "VaultWindow", server: QLocalServer) -> None:
    """A second Keeper was started: drain its socket and come to the front."""
    connection = server.nextPendingConnection()
    if connection is not None:
        connection.readAll()
        connection.disconnectFromServer()
        connection.deleteLater()
    window.restore_from_tray()


# ---------------------------------------------------------------------------
# Small widget helpers
# ---------------------------------------------------------------------------


def button(text: str, *, primary: bool = False, danger: bool = False, ghost: bool = False) -> QPushButton:
    result = QPushButton(text)
    if primary:
        result.setProperty("variant", "primary")
        glow(result, blur=18, dy=4, alpha=80)
    elif danger:
        result.setProperty("variant", "danger")
    elif ghost:
        result.setProperty("variant", "ghost")
    return result


def icon_button(name: str, tooltip: str, *, danger: bool = False, bordered: bool = False, accent: str = TEXT_MUTED) -> QToolButton:
    result = QToolButton()
    result.setObjectName("iconButton")
    result.setIcon(icon(name, DANGER if danger else accent))
    result.setToolTip(tooltip)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if danger:
        result.setProperty("danger", True)
    if bordered:
        result.setProperty("bordered", True)
    return result


def label(text: str, *, muted: bool = False, faint: bool = False, eyebrow: bool = False, error: bool = False, h1: bool = False, h2: bool = False, h3: bool = False, mono: bool = False, wrap: bool = True) -> QLabel:
    result = QLabel(text)
    if muted:
        result.setObjectName("muted")
    elif faint:
        result.setObjectName("faint")
    elif eyebrow:
        result.setObjectName("eyebrow")
        eyebrow_font = result.font()
        eyebrow_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        result.setFont(eyebrow_font)
    elif error:
        result.setObjectName("error")
    elif h1:
        result.setObjectName("h1")
    elif h2:
        result.setObjectName("h2")
    elif h3:
        result.setObjectName("h3")
    if mono:
        result.setProperty("mono", True)
    result.setWordWrap(wrap)
    return result


def hchip(text: str, *, mono: bool = False, tag: bool = False) -> QLabel:
    chip = label(text, wrap=False)
    chip.setObjectName("hchip")
    if mono:
        chip.setProperty("mono", True)
    if tag:
        chip.setProperty("tag", True)
    return chip


def sidebar_row(entry: Entry, credential_count: int) -> QWidget:
    """Sidebar asset row: icon, name, address/tags sub-lines, count badge."""
    widget = QWidget()
    widget.setObjectName("entryItem")
    row = QHBoxLayout(widget)
    row.setContentsMargins(9, 8, 9, 8)
    row.setSpacing(10)

    kind_badge = QToolButton()
    kind_badge.setObjectName("tileSmall")
    kind_badge.setIcon(icon(kind_icon_name(entry.kind), TEXT_MUTED))
    kind_badge.setEnabled(False)
    kind_badge.setFixedSize(QSize(32, 32))
    row.addWidget(kind_badge)

    text = QVBoxLayout()
    text.setSpacing(1)
    name = label(entry.name if entry.name else "未命名服务器", wrap=False)
    name.setStyleSheet("font-weight: 600;")
    text.addWidget(name)
    if entry.kind == "server":
        sub = " · ".join(entry.tags[:3]) if entry.tags else (entry.address or "")
    else:
        sub = entry.address or ""
        if entry.tags:
            sub = (sub + " · " if sub else "") + " · ".join(entry.tags[:3])
    text.addWidget(label(sub, faint=True, mono=True, wrap=False))
    row.addLayout(text, 1)

    count = QLabel(str(credential_count))
    count.setObjectName("entryCount")
    count.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(count, alignment=Qt.AlignmentFlag.AlignVCenter)
    return widget


class MainArea(QWidget):
    """The right-hand workspace: bg colour plus the demo's radial glows."""

    def paintEvent(self, event) -> None:  # type: ignore[override] # noqa: ANN001
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(BG))
        width, height = self.width(), self.height()
        teal = QRadialGradient(QPointF(width * 0.85, height * -0.05), width * 0.55)
        teal_color = QColor(GLOW_TEAL)
        teal_color.setAlpha(89)  # demo: oklch(0.24 0.045 210 / 0.35)
        teal.setColorAt(0.0, teal_color)
        teal.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), teal)
        blue = QRadialGradient(QPointF(width * 0.05, height * 1.05), width * 0.55)
        blue_color = QColor(GLOW_BLUE)
        blue_color.setAlpha(115)  # demo: oklch(0.20 0.040 200 / 0.45)
        blue.setColorAt(0.0, blue_color)
        blue.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), blue)
        painter.end()


class CenteredDialog(QDialog):
    """A parented modal dialog: solid dark backdrop with a floating shadowed
    surface, centered over the active window and sprung in like the demo.

    The backdrop is painted (not WA_TranslucentBackground): per-pixel window
    transparency composites badly on RDP sessions and machines without DWM,
    where the transparent margins render as pure black instead.
    """

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.adjustSize()
        frame = self.frameGeometry()
        parent = self.parentWidget()
        if parent is not None:
            frame.moveCenter(parent.frameGeometry().center())
            self.move(frame.topLeft())
        dialog_spring(self)


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------


class UnlockDialog(CenteredDialog):
    def __init__(
        self,
        repository: VaultRepository,
        parent: QWidget,
        *,
        failure_count: int = 0,
        throttled_until: float = 0.0,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.is_new = not repository.exists
        self.failure_count = failure_count
        self.throttled_until = throttled_until
        self._failure_message = ""
        self._throttle_remaining_ms = 0
        self.setWindowTitle("Create vault" if self.is_new else "Unlock vault")
        self.setModal(True)
        self.setMinimumWidth(430)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)
        layout.addWidget(label("KEEPER", eyebrow=True))
        heading = QLabel("创建保险库" if self.is_new else "欢迎回来")
        heading.setObjectName("h1")
        layout.addWidget(heading)
        layout.addWidget(label("设置一个只用于解锁此本地保险库的主密码。" if self.is_new else "输入主密码以解锁本地加密保险库。", muted=True))

        form_box = QVBoxLayout()
        form_box.setSpacing(9)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form_box.addWidget(label("主密码", muted=True))
        form_box.addWidget(self.password)
        self.confirm: QLineEdit | None = None
        if self.is_new:
            self.confirm = QLineEdit()
            self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
            form_box.addWidget(label("确认密码", muted=True))
            form_box.addWidget(self.confirm)
        layout.addLayout(form_box)
        self.error = label("", error=True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        exit_button = button("退出 Keeper")
        exit_button.setAutoDefault(False)
        exit_button.clicked.connect(self.reject)
        actions.addWidget(exit_button)
        actions.addStretch()
        self.submit = button("创建加密保险库" if self.is_new else "解锁保险库", primary=True)
        self.submit.setDefault(True)
        self.submit.clicked.connect(self._submit)
        actions.addWidget(self.submit)
        layout.addLayout(actions)

        drop_shadow(surface, blur=44, dy=14, alpha=160)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(surface)
        self.password.setFocus()

        self.throttle_timer = QTimer(self)
        self.throttle_timer.setInterval(100)
        self.throttle_timer.timeout.connect(self._tick_throttle)
        remaining_ms = int((self.throttled_until - time.monotonic()) * 1_000)
        if remaining_ms > 0:
            self._begin_throttle(remaining_ms)

    def _submit(self) -> None:
        if self.throttle_timer.isActive():
            return
        try:
            if self.is_new:
                if self.password.text() != (self.confirm.text() if self.confirm else ""):
                    raise ValueError("两次输入的密码不一致。")
                self.repository.initialize(self.password.text())
            else:
                self.repository.unlock(self.password.text())
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            if not self.is_new:
                self._register_failed_attempt()
            return
        except Exception as exc:  # noqa: BLE001 - disk/SQLCipher failures must not crash the dialog
            self.error.setText(f"操作失败：{exc}")
            self.error.show()
            return
        self.accept()

    def _register_failed_attempt(self) -> None:
        self.failure_count += 1
        delay_ms = unlock_failure_delay_ms(self.failure_count)
        self.throttled_until = time.monotonic() + delay_ms / 1_000
        self._failure_message = self.error.text()
        self._begin_throttle(delay_ms)

    def _begin_throttle(self, delay_ms: int) -> None:
        self._throttle_remaining_ms = delay_ms
        self.password.setEnabled(False)
        if self.confirm is not None:
            self.confirm.setEnabled(False)
        self.submit.setEnabled(False)
        self._render_throttle_message()
        self.throttle_timer.start()

    def _tick_throttle(self) -> None:
        self._throttle_remaining_ms -= self.throttle_timer.interval()
        if self._throttle_remaining_ms <= 0:
            self.throttle_timer.stop()
            self._throttle_remaining_ms = 0
            self.password.setEnabled(True)
            if self.confirm is not None:
                self.confirm.setEnabled(True)
            self.submit.setEnabled(True)
            if self._failure_message:
                self.error.setText(self._failure_message)
            else:
                self.error.hide()
            self.password.setFocus()
        else:
            self._render_throttle_message()

    def _render_throttle_message(self) -> None:
        seconds = math.ceil(self._throttle_remaining_ms / 1_000)
        self.error.setText(f"解锁失败，请 {seconds} 秒后重试。")
        self.error.show()


class RekeyDialog(CenteredDialog):
    """Re-encrypt the unlocked vault under a new master password."""

    def __init__(self, repository: VaultRepository, parent: QWidget) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("修改主密码")
        self.setModal(True)
        self.setMinimumWidth(460)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(13)
        layout.addWidget(label("修改主密码", h2=True))
        layout.addWidget(label("会用新主密码重新加密整个保险库，内容保持不变。主密码无法恢复，请确认新密码已妥善保存。", muted=True))

        form_box = QVBoxLayout()
        form_box.setSpacing(9)
        self.current = QLineEdit()
        self.current.setEchoMode(QLineEdit.EchoMode.Password)
        self.new = QLineEdit()
        self.new.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        for text, field in (("当前主密码", self.current), ("新主密码", self.new), ("确认新密码", self.confirm)):
            form_box.addWidget(label(text, muted=True))
            form_box.addWidget(field)
        layout.addLayout(form_box)

        self.error = label("", error=True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("取消")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        save = button("重新加密保险库", primary=True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

        drop_shadow(surface, blur=44, dy=14, alpha=160)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(surface)
        self.current.setFocus()

    def _save(self) -> None:
        if self.new.text() != self.confirm.text():
            self._fail("两次输入的新密码不一致。")
            return
        try:
            self.repository.rekey(self.current.text(), self.new.text())
        except ValueError as exc:
            self._fail(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - disk/SQLCipher failures must not crash the dialog
            self._fail(f"操作失败：{exc}")
            return
        self.accept()

    def _fail(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()


class EntryDialog(CenteredDialog):
    """Create or edit an asset; the type is chosen inside the dialog."""

    def __init__(self, kind: str, entry: Entry | None, parent: QWidget) -> None:
        super().__init__(parent)
        self._kind = kind if kind in {"server", "application"} else "server"
        self.entry = entry
        if entry is not None:
            self._kind = entry.kind
        self.setWindowTitle("编辑资产")
        self.setModal(True)
        self.setMinimumWidth(480)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        head.addWidget(label("新增资产" if entry is None else "编辑资产", h2=True))
        head.addStretch()
        layout.addLayout(head)

        # Type cards: icon + title in a row; exclusive.
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.type_cards: dict[str, QToolButton] = {}
        for key, text, icon_name in (("server", "服务器", "server"), ("application", "应用", "globe")):
            card = QToolButton()
            card.setObjectName("typeCard")
            card.setText(text)
            card.setIcon(icon(icon_name, TEXT if key == self._kind else TEXT_MUTED))
            card.setIconSize(QSize(18, 18))
            card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            card.setCheckable(True)
            card.setChecked(key == self._kind)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(lambda _checked=False, chosen=key: self._select_kind(chosen))
            self.type_cards[key] = card
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        form = QVBoxLayout()
        form.setSpacing(9)
        self.name = QLineEdit(entry.name if entry else "")
        self.address = QLineEdit(entry.address or "" if entry else "")
        self.name_label = label("显示名称（可选）", muted=True)
        self.address_label = label("服务器 IP", muted=True)
        form.addWidget(self.name_label)
        form.addWidget(self.name)
        form.addWidget(self.address_label)
        form.addWidget(self.address)
        self.tag_edit = TagEdit(SERVER_TAG_SUGGESTIONS if self._kind == "server" else APPLICATION_TAG_SUGGESTIONS)
        form.addSpacing(4)
        form.addWidget(label("标签（可选）", muted=True))
        form.addWidget(self.tag_edit)
        layout.addLayout(form)

        self.error = label("", error=True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("取消")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        self.save = button("保存服务器", primary=True)
        self.save.setDefault(True)
        self.save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(self.save)
        layout.addLayout(actions)

        drop_shadow(surface, blur=44, dy=14, alpha=160)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(surface)
        self._apply_kind(self._kind, first=True)
        self.name.setFocus()

    def _select_kind(self, kind: str) -> None:
        self._apply_kind(kind)

    def _apply_kind(self, kind: str, first: bool = False) -> None:
        self._kind = kind
        for key, card in self.type_cards.items():
            card.setChecked(key == kind)
            card.setIcon(icon("server" if key == "server" else "globe", TEXT if key == kind else TEXT_MUTED))
            if key == kind:
                glow(card, blur=16, dy=0, alpha=70)
            else:
                card.setGraphicsEffect(None)
        if kind == "server":
            self.name_label.setText("显示名称（可选）")
            self.name.setPlaceholderText("如：生产数据库服务器")
            self.address_label.setText("服务器 IP")
            self.address.setPlaceholderText("如：192.168.1.101 或 192.168.1.101:2222")
            self.save.setText("保存服务器")
        else:
            self.name_label.setText("应用名称")
            self.name.setPlaceholderText("如：阿里云、OpenAI、GitHub")
            self.address_label.setText("网站地址（可选）")
            self.address.setPlaceholderText("如：https://console.aliyun.com")
            self.save.setText("保存应用")
        if not first:
            self.tag_edit.set_suggestions(SERVER_TAG_SUGGESTIONS if kind == "server" else APPLICATION_TAG_SUGGESTIONS)

    def draft(self) -> EntryDraft:
        return EntryDraft(kind=self._kind, name=self.name.text(), address=self.address.text(), tags=self.tag_edit.tags())

    def _save(self) -> None:
        try:
            validate_entry_draft(self.draft())
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


class CredentialDialog(CenteredDialog):
    """Create or edit a credential, with the shared generator inline."""

    def __init__(self, credential: Credential | None, parent: QWidget, *, login_mode: bool = False) -> None:
        super().__init__(parent)
        self.credential = credential
        self.login_mode = login_mode or (credential is not None and credential.kind in {"ssh", "rdp"})
        self.setWindowTitle("编辑系统登录" if credential and self.login_mode else "新增系统登录" if self.login_mode else "编辑项目" if credential else "新增项目")
        self.setModal(True)
        self.setMinimumWidth(480)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(12)
        layout.addWidget(label(self.windowTitle(), h2=True))

        form = QVBoxLayout()
        form.setSpacing(9)
        self.name = QLineEdit(credential.label if credential else "")
        self.name.setPlaceholderText("如：SSH 登录、MySQL、网站后台")
        self.username = QLineEdit(credential.username if credential else "")
        self.username.setPlaceholderText("如：root / administrator")
        self.password = QLineEdit(credential.password if credential else "")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setProperty("mono", True)

        password_row = QHBoxLayout()
        password_row.setSpacing(8)
        password_row.addWidget(self.password, 1)
        self.eye_button = icon_button("eye", "显示 / 隐藏密码")
        self.eye_button.clicked.connect(self._toggle_password_echo)
        password_row.addWidget(self.eye_button)
        self.generate_password_button = button("生成", primary=True)
        self.generate_password_button.setAutoDefault(False)
        self.generate_password_button.clicked.connect(self.generate_password)
        password_row.addWidget(self.generate_password_button)
        self.extra = QLineEdit(credential.extra if credential else "")
        self.extra.setPlaceholderText("可选：https:// 网址或补充说明")

        if self.login_mode:
            self.ssh_radio = QRadioButton("Linux（SSH）")
            self.rdp_radio = QRadioButton("Windows（RDP）")
            is_rdp = (credential.kind if credential else "ssh") == "rdp"
            self.ssh_radio.setChecked(not is_rdp)
            self.rdp_radio.setChecked(is_rdp)
            platform_row = QHBoxLayout()
            platform_row.setSpacing(10)
            platform_row.addWidget(self.ssh_radio)
            platform_row.addWidget(self.rdp_radio)
            platform_row.addStretch()
            form.addWidget(label("登录平台", muted=True))
            form.addLayout(platform_row)
            form.addWidget(label("登录账号", muted=True))
            form.addWidget(self.username)
            form.addWidget(label("密码（可选）", muted=True))
            form.addLayout(password_row)
            self.ssh_radio.toggled.connect(self._sync_default_username)
            if credential is None:
                self.username.setText("root")
        else:
            form.addWidget(label("项目名称", muted=True))
            form.addWidget(self.name)
            form.addWidget(label("用户名（可选）", muted=True))
            form.addWidget(self.username)
            form.addWidget(label("密码（可选）", muted=True))
            form.addLayout(password_row)
            form.addWidget(label("说明 / 网站地址（可选）", muted=True))
            form.addWidget(self.extra)
        layout.addLayout(form)

        # Shared generator controls: same charsets, slider and strength meter
        # as the home page, wired to the password field.
        generator_row = QHBoxLayout()
        generator_row.setSpacing(12)
        self.char_toggles = CharSetToggles()
        generator_row.addWidget(self.char_toggles)
        length_box = QHBoxLayout()
        length_box.setSpacing(8)
        length_box.addWidget(label("长度", muted=True))
        self.length_slider = QSlider(Qt.Orientation.Horizontal)
        self.length_slider.setRange(1, 128)
        self.length_slider.setValue(GENERATED_PASSWORD_LENGTH)
        self.length_slider.setFixedWidth(110)
        length_box.addWidget(self.length_slider)
        self.length_value = QLabel(str(GENERATED_PASSWORD_LENGTH))
        self.length_value.setObjectName("mono")
        length_box.addWidget(self.length_value)
        generator_row.addLayout(length_box)
        generator_row.addStretch(1)
        layout.addLayout(generator_row)
        strength_row = QHBoxLayout()
        strength_row.setSpacing(10)
        self.strength = StrengthMeter(compact=True)
        strength_row.addWidget(self.strength, 1)
        self.strength_label = QLabel("—" if not self.password.text() else "")
        self.strength_label.setFixedWidth(36)
        self.strength_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        strength_row.addWidget(self.strength_label)
        layout.addLayout(strength_row)
        self.char_toggles.selection_changed.connect(self._refresh_strength)
        self.length_slider.valueChanged.connect(self._refresh_strength)
        if self.password.text():
            self._refresh_strength()

        self.error = label("", error=True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("取消")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        save = button("保存项目", primary=True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

        drop_shadow(surface, blur=44, dy=14, alpha=160)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(surface)
        (self.username if self.login_mode else self.name).setFocus()

    def _toggle_password_echo(self) -> None:
        hidden = self.password.echoMode() == QLineEdit.EchoMode.Password
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.eye_button.setIcon(icon("eye-off" if hidden else "eye"))

    def _sync_default_username(self, ssh_selected: bool) -> None:
        """Pre-fill the typical account per platform; keep custom input."""
        chosen, other = ("root", "administrator") if ssh_selected else ("administrator", "root")
        current = self.username.text().strip()
        if not current or current == other:
            self.username.setText(chosen)

    def _refresh_strength(self) -> None:
        keys = self.char_toggles.selected_keys()
        bits = entropy_bits(self.length_slider.value(), keys)
        self.strength.set_bits(bits)
        self.strength_label.setText(strength_label(strength_level(bits)))
        self.length_value.setText(str(self.length_slider.value()))

    def generate_password(self) -> None:
        password = generate_password("+".join(self.char_toggles.selected_keys()), self.length_slider.value())
        self.password.setText(password)
        self.password.setEchoMode(QLineEdit.EchoMode.Normal)
        self.eye_button.setIcon(icon("eye-off"))
        self._refresh_strength()

    def draft(self) -> CredentialDraft:
        if self.login_mode:
            kind = "rdp" if self.rdp_radio.isChecked() else "ssh"
            return CredentialDraft(kind=kind, label="系统登录账号", username=self.username.text(), password=self.password.text(), extra="")
        return CredentialDraft(kind="custom", label=self.name.text(), username=self.username.text(), password=self.password.text(), extra=self.extra.text())

    def _save(self) -> None:
        try:
            validate_credential_draft(self.draft())
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class VaultWindow(QMainWindow):
    AUTO_LOCK_MS = 10 * 60 * 1_000

    def __init__(self, vault_path: Path = DEFAULT_VAULT, *, tray_available: bool | None = None, auto_lock_ms: int | None = None) -> None:
        super().__init__()
        self.repository = VaultRepository(vault_path)
        self.selected_entry_id: int | None = None
        self.clipboard_token = 0
        self.throttle_path = vault_path.expanduser().parent / THROTTLE_FILE_NAME
        self.unlock_failure_count, self.unlock_throttled_until = load_unlock_throttle(self.throttle_path)
        self._allow_exit = False
        self.hidden_to_tray = False
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable() if tray_available is None else tray_available
        self.auto_lock_interval_ms = auto_lock_ms if auto_lock_ms is not None else self.AUTO_LOCK_MS
        self.auto_lock_timer = QTimer(self)
        self.auto_lock_timer.setSingleShot(True)
        self.auto_lock_timer.setInterval(self.auto_lock_interval_ms)
        self.auto_lock_timer.timeout.connect(self.auto_lock)
        self.idle_poll_timer = QTimer(self)
        self.idle_poll_timer.setInterval(IDLE_POLL_MS)
        self.idle_poll_timer.timeout.connect(self.lock_when_idle)
        self.tray_icon: QSystemTrayIcon | None = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(1280, 800)
        self.setMinimumSize(980, 640)
        self._recent: list[tuple[str, str]] = []
        self._build_shell()
        self.toast = Toast(self)
        application = QApplication.instance()
        if application is not None:
            application.applicationStateChanged.connect(self.restore_when_reactivated)
        if self._tray_available:
            self._build_tray()

    # -- shell ---------------------------------------------------------------

    def _build_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu(self)
        open_action = QAction("打开 Keeper", menu)
        open_action.triggered.connect(self.restore_from_tray)
        quit_action = QAction("完全退出", menu)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(open_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.restore_from_tray()

    def _build_shell(self) -> None:
        splitter = QSplitter()
        splitter.setObjectName("workspace")
        splitter.setChildrenCollapsible(False)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(300)
        sidebar.setMaximumWidth(400)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(20, 20, 18, 16)
        left.setSpacing(11)

        # 第一段：品牌 + 锁定。
        top = QHBoxLayout()
        top.setSpacing(10)
        brand_icon = QToolButton()
        brand_icon.setObjectName("brandMark")
        brand_icon.setEnabled(False)
        brand_icon.setIcon(icon("shield-check", ACCENT_INK, stroke_width=2.2))
        brand_icon.setFixedSize(QSize(34, 34))
        glow(brand_icon, blur=14, dy=3, alpha=90)
        top.addWidget(brand_icon)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_name = label("Keeper", wrap=False)
        brand_name.setObjectName("brandName")
        brand_sub = label("本地加密保险库", wrap=False)
        brand_sub.setObjectName("brandSub")
        brand_text.addWidget(brand_name)
        brand_text.addWidget(brand_sub)
        top.addLayout(brand_text)
        top.addStretch()
        self.lock_button = icon_button("lock", "锁定保险库")
        self.lock_button.clicked.connect(self.lock)
        top.addWidget(self.lock_button)
        left.addLayout(top)

        # 第二段：资产区（搜索、筛选、新增、列表）。
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_lead = icon_button("search", "")
        search_lead.setEnabled(False)
        search_lead.setProperty("flat", True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称、IP 或标签…")
        self.search.textChanged.connect(self.refresh_entries)
        search_row.addWidget(search_lead)
        search_row.addWidget(self.search, 1)
        left.addLayout(search_row)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.filter_chips: dict[str, QToolButton] = {}
        self._filter_kind = "all"
        for key, text in (("all", "全部"), ("server", "服务器"), ("application", "应用")):
            chip = QToolButton()
            chip.setObjectName("chip")
            chip.setText(text)
            chip.setCheckable(True)
            chip.setChecked(key == "all")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, chosen=key: self._set_filter(chosen))
            self.filter_chips[key] = chip
            chips.addWidget(chip)
        chips.addStretch()
        left.addLayout(chips)

        self.add_button = button("新增资产", primary=True)
        add_icon = icon("plus", ACCENT_INK)
        self.add_button.setIcon(add_icon)
        self.add_button.clicked.connect(lambda: self.edit_entry("server"))
        left.addWidget(self.add_button)

        self.entries = QListWidget()
        self.entries.currentItemChanged.connect(self.select_entry)
        left.addWidget(self.entries, 1)

        # 第三段：保险库状态 + 工具。
        status = QFrame()
        status.setObjectName("vaultStatus")
        status_row = QHBoxLayout(status)
        status_row.setContentsMargins(11, 8, 11, 8)
        status_row.setSpacing(9)
        dot = QLabel()
        dot.setObjectName("statusDot")
        dot.setFixedSize(6, 6)
        pulse_forever(dot)
        status_row.addWidget(dot)
        minutes = max(1, round(self.auto_lock_interval_ms / 60_000))
        self.vault_status_label = label(f"保险库已解锁 · {minutes} 分钟无操作自动锁定", faint=True, wrap=False)
        status_row.addWidget(self.vault_status_label, 1)
        left.addWidget(status)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.export_button = button("导出 Excel")
        self.export_button.setIcon(icon("download"))
        self.export_button.clicked.connect(self.export_credentials)
        tools.addWidget(self.export_button, 1)
        self.rekey_button = button("修改主密码")
        self.rekey_button.setIcon(icon("key"))
        self.rekey_button.setToolTip("用新的主密码重新加密整个保险库，内容保持不变")
        self.rekey_button.clicked.connect(self.change_master_password)
        tools.addWidget(self.rekey_button, 1)
        left.addLayout(tools)

        splitter.addWidget(sidebar)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.empty = self._home_page()
        self.pages.addWidget(self.empty)
        self.locked = self._locked_page()
        self.pages.addWidget(self.locked)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("detailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages.addWidget(self.detail_scroll)
        main = MainArea()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.pages)
        splitter.addWidget(main)
        splitter.setSizes([340, 940])
        self.setCentralWidget(splitter)
        if self.repository.exists:
            self.pages.setCurrentWidget(self.locked)

    def _set_filter(self, kind: str) -> None:
        self._filter_kind = kind
        for key, chip in self.filter_chips.items():
            chip.setChecked(key == kind)
        self.refresh_entries()

    # -- home ----------------------------------------------------------------

    def _home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("emptyPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(18)

        head = QHBoxLayout()
        head_text = QVBoxLayout()
        head_text.setSpacing(5)
        head_text.addWidget(label("保险库总览", eyebrow=True))
        title = label("一切安全，一切就绪", h1=True)
        head_text.addWidget(title)
        self.home_subtitle = label("", muted=True, wrap=False)
        head_text.addWidget(self.home_subtitle)
        head.addLayout(head_text)
        head.addStretch()
        layout.addLayout(head)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_labels: dict[str, QLabel] = {}
        for key, caption, icon_name in (
            ("servers", "服务器", "server"),
            ("applications", "应用", "globe"),
            ("credentials", "凭据总数", "lock"),
            ("autolock", "自动锁定", "clock"),
        ):
            card = Card(object_name="statCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 15, 18, 15)
            box.setSpacing(3)
            number = label("0", wrap=False)
            number.setObjectName("statNum")
            self.stat_labels[key] = number
            box.addWidget(number)
            cap_row = QHBoxLayout()
            cap_row.setSpacing(6)
            cap_lead = icon_button(icon_name, "")
            cap_lead.setEnabled(False)
            cap_lead.setProperty("flat", True)
            cap_row.addWidget(cap_lead)
            if key == "autolock":
                minutes = max(1, round(self.auto_lock_interval_ms / 60_000))
                number.setText(f"{minutes}")
                cap = label("分钟", muted=True, wrap=False)
            else:
                cap = label(caption, muted=True, wrap=False)
            cap_row.addWidget(cap)
            cap_row.addStretch()
            box.addLayout(cap_row)
            stats.addWidget(card, 1)
        layout.addLayout(stats)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        self.home_password_generator = PasswordGenerator()
        self.home_password_generator.password_generated.connect(lambda _password: self.home_copy_password.setEnabled(True))
        columns.addWidget(self.home_password_generator, 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        recent = Card()
        recent_box = QVBoxLayout(recent)
        recent_box.setContentsMargins(20, 16, 20, 14)
        recent_box.setSpacing(8)
        recent_box.addWidget(label("最近访问", h3=True))
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(2)
        recent_box.addLayout(self.recent_list)
        self._render_recent()
        right.addWidget(recent)

        security = Card()
        security_box = QVBoxLayout(security)
        security_box.setContentsMargins(20, 16, 20, 14)
        security_box.setSpacing(7)
        security_box.addWidget(label("安全状态", h3=True))
        for text in (
            "整库加密 — SQLCipher 4 · PBKDF2 512,000 次迭代",
            "剪贴板保护 — 复制后 30 秒自动清除",
            "离线运行 — 不联网、不同步、无云端副本",
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            lead = icon_button("check", OK)
            lead.setEnabled(False)
            lead.setProperty("flat", True)
            row.addWidget(lead)
            row.addWidget(label(text, muted=True, wrap=False))
            row.addStretch()
            security_box.addLayout(row)
        right.addWidget(security)
        right.addStretch()
        columns.addLayout(right, 2)
        layout.addLayout(columns)

        self.home_copy_password = button("复制生成的密码", primary=True)
        self.home_copy_password.setEnabled(False)
        self.home_copy_password.clicked.connect(lambda: self.copy_secret(self.home_password_generator.result.text(), "密码已复制，30 秒后清除"))
        layout.addWidget(self.home_copy_password, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _render_recent(self) -> None:
        while self.recent_list.count():
            item = self.recent_list.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        if not self._recent:
            self.recent_list.addWidget(label("复制密码或发起连接后，这里会记录最近的操作。", faint=True))
            return
        for title, sub in self._recent[:4]:
            row = QVBoxLayout()
            row.setSpacing(1)
            row.addWidget(label(title, wrap=False))
            row.addWidget(label(sub, faint=True, wrap=False))
            holder = QWidget()
            holder.setLayout(row)
            self.recent_list.addWidget(holder)

    def _remember_use(self, title: str, sub: str) -> None:
        self._recent.insert(0, (title, sub))
        del self._recent[6:]
        self._render_recent()

    def _refresh_home_stats(self) -> None:
        if not self.repository.unlocked:
            return
        entries = self.repository.list_entries()
        servers = sum(1 for entry in entries if entry.kind == "server")
        applications = len(entries) - servers
        credentials = sum(len(self.repository.list_credentials(entry.id)) for entry in entries)
        self.stat_labels["servers"].setText(str(servers))
        self.stat_labels["applications"].setText(str(applications))
        self.stat_labels["credentials"].setText(str(credentials))
        self.home_subtitle.setText(f"{servers} 台服务器 · {applications} 个应用 · {credentials} 条凭据，整库 SQLCipher 加密")

    # -- locked page -----------------------------------------------------------

    def _locked_page(self) -> QWidget:
        """The lock screen: a locked vault must not look like an empty one.

        Locking clears the sidebar, and landing on the home page made it look as
        if every saved entry had vanished. This says out loud that the data is
        still on disk, encrypted, and one master password away.
        """
        page = QWidget()
        page.setObjectName("lockedPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(42, 35, 42, 35)
        layout.setSpacing(14)
        layout.addStretch()
        mark = QToolButton()
        mark.setObjectName("tile")
        mark.setEnabled(False)
        mark.setIcon(icon("lock", ACCENT, stroke_width=1.8))
        mark.setFixedSize(QSize(56, 56))
        glow(mark, blur=26, dy=0, alpha=70)
        layout.addWidget(mark, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label("保险库已锁定", h1=True), alignment=Qt.AlignmentFlag.AlignHCenter)
        explanation = label("你的数据一条都没丢：它们仍完整保存在本地的加密文件里，只是现在不解密显示。解锁后所有资产和项目会立刻全部回来。", muted=True)
        explanation.setMaximumWidth(520)
        layout.addWidget(explanation, alignment=Qt.AlignmentFlag.AlignHCenter)
        unlock = button("解锁保险库", primary=True)
        unlock.setToolTip("输入主密码，重新加载全部资产与项目")
        unlock.clicked.connect(self.unlock_from_locked_page)
        layout.addWidget(unlock, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return page

    # -- navigation ------------------------------------------------------------

    def _switch_page(self, widget: QWidget) -> None:
        """Swap the workspace page with the demo's screenIn fade."""
        if self.pages.currentWidget() is widget:
            return
        self.pages.setCurrentWidget(widget)
        fade_widget(self.pages, start=0.0, end=1.0, duration=240)

    def show_home(self) -> None:
        self.selected_entry_id = None
        self.entries.blockSignals(True)
        self.entries.clearSelection()
        self.entries.blockSignals(False)
        self._switch_page(self.empty if self.repository.unlocked else self.locked)

    def leave_locked_page(self) -> None:
        """Any successful unlock swaps the lock screen for the workspace."""
        if self.pages.currentWidget() is self.locked:
            self.show_home()

    def unlock_from_locked_page(self) -> None:
        """The lock screen's own button: unlock and report the result."""
        if not self.unlock_for_display():
            self.statusBar().showMessage("保险库仍处于锁定状态。")
            return
        self.statusBar().showMessage("保险库已解锁，数据已全部加载。", 6_000)

    def restore_when_reactivated(self, state: Qt.ApplicationState) -> None:
        """Bring the window back when the app itself is re-activated."""
        if state != Qt.ApplicationState.ApplicationActive:
            return
        if not self.hidden_to_tray or self._allow_exit or self.isVisible():
            return
        self.restore_from_tray()

    # -- unlock / lock -----------------------------------------------------------

    def open_unlock(self) -> bool:
        dialog = UnlockDialog(
            self.repository,
            self,
            failure_count=self.unlock_failure_count,
            throttled_until=self.unlock_throttled_until,
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self.unlock_failure_count = 0
            self.unlock_throttled_until = 0.0
        else:
            self.unlock_failure_count = dialog.failure_count
            self.unlock_throttled_until = dialog.throttled_until
        save_unlock_throttle(self.unlock_failure_count, self.unlock_throttled_until, self.throttle_path)
        return accepted

    def unlock_for_display(self) -> bool:
        if self.repository.unlocked:
            self.idle_poll_timer.start()
            self.leave_locked_page()
            return True
        if not self.open_unlock():
            return False
        self.refresh_entries()
        self._refresh_home_stats()
        self.idle_poll_timer.start()
        self.leave_locked_page()
        return True

    def restore_from_tray(self) -> None:
        self.hidden_to_tray = False
        self.auto_lock_timer.stop()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if not self.unlock_for_display():
            self.hide_to_tray()

    def lock_vault(self, *, status_message: str | None = None) -> None:
        self.auto_lock_timer.stop()
        self.idle_poll_timer.stop()
        self.clipboard_token += 1
        QApplication.clipboard().clear()
        self.repository.lock()
        self.selected_entry_id = None
        previous_signals_blocked = self.entries.blockSignals(True)
        self.entries.clear()
        self.entries.blockSignals(previous_signals_blocked)
        self.search.clear()
        self._recent.clear()
        self._render_recent()
        self.pages.setCurrentWidget(self.locked)
        self.statusBar().showMessage(status_message or "保险库已锁定。")

    def auto_lock(self) -> None:
        if not self.isVisible() and self.repository.unlocked:
            self.lock_vault()
            if self.tray_icon is not None:
                self.tray_icon.showMessage(APP_NAME, f"保险库已因 {self._auto_lock_minutes()} 分钟未打开而自动锁定。")

    def lock_when_idle(self) -> None:
        """Lock a window that is still open but has seen no input for a while."""
        if not self.repository.unlocked or not self.isVisible():
            return
        idle_seconds = system_idle_seconds()
        if idle_seconds is None or idle_seconds * 1_000 < self.auto_lock_interval_ms:
            return
        self.lock_vault(status_message=f"已因 {self._auto_lock_minutes()} 分钟无操作自动锁定。")

    def _auto_lock_minutes(self) -> int:
        return max(1, round(self.auto_lock_interval_ms / 60_000))

    def hide_to_tray(self) -> None:
        self.hidden_to_tray = True
        self.hide()
        if self.repository.unlocked:
            self.auto_lock_timer.start()

    def quit_application(self) -> None:
        self._allow_exit = True
        self.hidden_to_tray = False
        self.lock_vault()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.close()

    # -- sidebar ----------------------------------------------------------------

    def refresh_entries(self) -> None:
        if not self.repository.unlocked:
            return
        selected = self.selected_entry_id
        counts = {
            entry.id: len(self.repository.list_credentials(entry.id))
            for entry in self.repository.list_entries()
        }
        self.entries.blockSignals(True)
        self.entries.clear()
        grouped: dict[str, list[Entry]] = {"server": [], "application": []}
        for entry in self.repository.list_entries(self.search.text()):
            if self._filter_kind != "all" and entry.kind != self._filter_kind:
                continue
            grouped.setdefault(entry.kind, []).append(entry)
        for kind, group_title in (("server", "服务器"), ("application", "应用")):
            items = grouped.get(kind, [])
            if not items:
                continue
            header = QListWidgetItem(group_title)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header_widget = label(group_title, faint=True, wrap=False)
            header_widget.setObjectName("groupLabel")
            group_font = header_widget.font()
            group_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
            header_widget.setFont(group_font)
            self.entries.addItem(header)
            self.entries.setItemWidget(header, header_widget)
            header.setSizeHint(QSize(0, 26))
            for entry in items:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                self.entries.addItem(item)
                widget = sidebar_row(entry, counts.get(entry.id, 0))
                item.setSizeHint(QSize(0, 60))
                self.entries.setItemWidget(item, widget)
                if entry.id == selected:
                    self.entries.setCurrentItem(item)
        self.entries.blockSignals(False)

    def select_entry(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None or not self.repository.unlocked:
            return
        entry_id = current.data(Qt.ItemDataRole.UserRole)
        if entry_id is None:  # group header
            return
        try:
            entry = self.repository.get_entry(int(entry_id))
        except RuntimeError:
            self.show_home()
            return
        self.selected_entry_id = int(entry_id)
        if entry is not None:
            self.render_entry(entry)

    # -- detail -----------------------------------------------------------------

    def render_entry(self, entry: Entry, *, focus_credential_id: int | None = None) -> None:
        self.selected_entry_id = entry.id
        page = QWidget()
        page.setObjectName("detailPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 28, 36, 32)
        layout.setSpacing(14)

        # Header: tile + eyebrow/title/chips + actions.
        head = QHBoxLayout()
        head.setSpacing(14)
        tile = QToolButton()
        tile.setObjectName("tile")
        tile.setEnabled(False)
        tile.setIcon(icon(kind_icon_name(entry.kind), ACCENT, stroke_width=1.8))
        tile.setFixedSize(QSize(50, 50))
        glow(tile, blur=18, dy=4, alpha=60)
        head.addWidget(tile)
        head_text = QVBoxLayout()
        head_text.setSpacing(4)
        head_text.addWidget(label("服务器工作区" if entry.kind == "server" else "应用", eyebrow=True))
        heading = label(entry.name, h1=True, wrap=False)
        head_text.addWidget(heading)
        chips = QHBoxLayout()
        chips.setSpacing(7)
        if entry.address:
            chips.addWidget(hchip(entry.address, mono=True))
        credentials = self.repository.list_credentials(entry.id)
        chips.addWidget(hchip(f"{len(credentials)} 个项目"))
        for tag in entry.tags[:4]:
            chips.addWidget(hchip(tag, tag=True))
        chips.addStretch()
        head_text.addLayout(chips)
        head.addLayout(head_text, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        edit_asset = icon_button("pencil", "编辑资产", bordered=True)
        edit_asset.clicked.connect(lambda: self.edit_entry(entry.kind, entry))
        delete_asset = icon_button("trash", "删除资产", danger=True, bordered=True)
        delete_asset.clicked.connect(lambda: self.delete_entry(entry))
        actions.addWidget(edit_asset)
        actions.addWidget(delete_asset)
        if entry.kind == "server":
            add_login = button("+ 系统登录")
            add_login.setToolTip("创建这台服务器的登录账号（Linux/SSH 或 Windows/RDP），卡片上会出现一键连接按钮")
            add_login.clicked.connect(lambda: self.edit_credential(entry, login_mode=True))
            actions.addWidget(add_login)
        add_credential = button("+ 新增项目", primary=True)
        add_credential.clicked.connect(lambda: self.edit_credential(entry))
        actions.addWidget(add_credential)
        head.addLayout(actions)
        layout.addLayout(head)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {BORDER_SOFT};")
        layout.addWidget(divider)

        if not credentials:
            empty_hint = Card()
            hint_box = QVBoxLayout(empty_hint)
            hint_box.setContentsMargins(18, 22, 18, 22)
            hint_text = label("还没有项目。" + ("添加第一个系统登录或应用密码。" if entry.kind == "server" else "点右上角「+ 新增项目」添加第一条凭据。"), muted=True)
            hint_box.addWidget(hint_text)
            layout.addWidget(empty_hint)
        cards: dict[int, QWidget] = {}
        for index, credential in enumerate(credentials):
            card = self.credential_card(entry, credential, index, len(credentials))
            cards[credential.id] = card
            layout.addWidget(card)
        layout.addStretch()
        self.detail_scroll.setWidget(page)
        self._switch_page(self.detail_scroll)
        target = cards.get(focus_credential_id) if focus_credential_id is not None else None
        if target is not None:
            QTimer.singleShot(0, lambda: self.detail_scroll.ensureWidgetVisible(target, 0, 60))

    def credential_card(self, entry: Entry, credential: Credential, index: int = 0, total: int = 1) -> QWidget:
        is_login = credential.kind in {"ssh", "rdp"}
        # Low-frequency actions share one container so they fade in and out
        # together on hover (the demo's .hover-actions row).
        hover_row = QWidget()
        hover_box = QHBoxLayout(hover_row)
        hover_box.setContentsMargins(0, 0, 0, 0)
        hover_box.setSpacing(2)
        up = icon_button("chevron-up", "上移")
        up.setObjectName("moveUp")
        up.setEnabled(index > 0)
        up.clicked.connect(lambda: self.move_credential(entry, credential, "up"))
        down = icon_button("chevron-down", "下移")
        down.setObjectName("moveDown")
        down.setEnabled(index < total - 1)
        down.clicked.connect(lambda: self.move_credential(entry, credential, "down"))
        edit = icon_button("pencil", "编辑")
        edit.setObjectName("editCredential")
        edit.clicked.connect(lambda: self.edit_credential(entry, credential))
        remove = icon_button("trash", "删除", danger=True)
        remove.setObjectName("removeCredential")
        remove.clicked.connect(lambda: self.delete_credential(entry, credential))
        for action_button in (up, down, edit, remove):
            hover_box.addWidget(action_button)

        card = Card(reveal=hover_row)
        if is_login:
            card.setProperty("accent", True)
        content = QVBoxLayout(card)
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(9)
        kind_glyph = QToolButton()
        kind_glyph.setObjectName("tileSmall")
        kind_glyph.setIcon(icon(credential_icon_name(credential), ACCENT if is_login else TEXT_MUTED))
        kind_glyph.setEnabled(False)
        kind_glyph.setFixedSize(QSize(30, 30))
        header.addWidget(kind_glyph)
        name = label(credential.label, h3=True, wrap=False)
        header.addWidget(name)
        badge_text = {"ssh": "系统登录 · SSH", "rdp": "系统登录 · RDP"}.get(credential.kind)
        if badge_text:
            badge = hchip(badge_text, tag=True)
            header.addWidget(badge)
        header.addStretch()
        header.addWidget(hover_row)
        content.addLayout(header)

        details = QHBoxLayout()
        details.setSpacing(9)
        details.addSpacing(38)
        user = credential.username or "未保存用户名"
        user_label = label(user, mono=True, wrap=False)
        user_label.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: 600;")
        details.addWidget(user_label)
        if credential.extra:
            details.addWidget(label("·", faint=True, wrap=False))
            details.addWidget(label(credential.extra, faint=True, mono=True, wrap=False))
        if credential.password:
            details.addWidget(label("·", faint=True, wrap=False))
            dots = label("•" * min(12, max(6, len(credential.password))), faint=True, mono=True, wrap=False)
            dots.setObjectName("pwDots")
            eye = icon_button("eye", "显示 / 隐藏密码")
            eye.setObjectName("pwToggle")
            eye.clicked.connect(lambda: self._toggle_card_password(dots, credential, eye))
            details.addWidget(dots)
            details.addWidget(eye)
        details.addStretch()
        content.addLayout(details)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addSpacing(38)
        copy_user = button("复制用户名")
        copy_user.setIcon(icon("copy"))
        copy_user.clicked.connect(lambda: self.copy_secret(credential.username, "用户名已复制，30 秒后清除", recent=(entry.name, credential.label, "复制了用户名")))
        buttons.addWidget(copy_user)
        copy_password = button("复制密码")
        copy_password.setIcon(icon("copy"))
        copy_password.clicked.connect(lambda: self.copy_secret(credential.password, "密码已复制，30 秒后清除", recent=(entry.name, credential.label, "复制了密码")))
        buttons.addWidget(copy_password)
        if entry.kind == "server" and is_login:
            connect = button("SSH 连接" if credential.kind == "ssh" else "RDP 连接", primary=True)
            connect.clicked.connect(lambda: self.connect_credential(entry, credential))
            buttons.addWidget(connect)
        url = extract_url(credential.extra, credential.label)
        if url:
            visit = button("↗ 访问网站", primary=True)
            visit.setIcon(icon("external", ACCENT_INK))
            visit.clicked.connect(lambda: self.open_address(url))
            buttons.addWidget(visit)
        buttons.addStretch()
        content.addLayout(buttons)
        return card

    @staticmethod
    def _toggle_card_password(dots: QLabel, credential: Credential, eye: QToolButton) -> None:
        showing = dots.property("revealed") is True
        if showing:
            dots.setText("•" * min(12, max(6, len(credential.password))))
            dots.setProperty("revealed", False)
            eye.setIcon(icon("eye"))
        else:
            dots.setText(credential.password)
            dots.setProperty("revealed", True)
            eye.setIcon(icon("eye-off"))
        dots.style().unpolish(dots)
        dots.style().polish(dots)

    # -- actions --------------------------------------------------------------

    def edit_entry(self, kind: str, entry: Entry | None = None) -> None:
        if not self.unlock_for_display():
            return
        dialog = EntryDialog(kind, entry, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            saved = self.repository.save_entry(dialog.draft(), entry.id if entry else None)
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.selected_entry_id = saved.id
        self.refresh_entries()
        self._refresh_home_stats()
        self.render_entry(saved)

    def edit_credential(self, entry: Entry, credential: Credential | None = None, *, login_mode: bool = False) -> None:
        if not self.unlock_for_display():
            return
        dialog = CredentialDialog(credential, self, login_mode=login_mode)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.repository.save_credential(entry.id, dialog.draft(), credential.id if credential else None)
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        refreshed = self.repository.get_entry(entry.id)
        if refreshed is not None:
            self.refresh_entries()
            self._refresh_home_stats()
            self.render_entry(refreshed)

    def move_credential(self, entry: Entry, credential: Credential, direction: str) -> None:
        if not self.unlock_for_display():
            return
        try:
            self.repository.move_credential(credential.id, direction)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        refreshed = self.repository.get_entry(entry.id)
        if refreshed is not None:
            self.render_entry(refreshed, focus_credential_id=credential.id)

    def copy_secret(self, value: str, message: str, *, recent: tuple[str, str, str] | None = None) -> None:
        if not value:
            QMessageBox.information(self, APP_NAME, "没有可复制的内容。")
            return
        self.clipboard_token += 1
        token = self.clipboard_token
        if not set_concealed_clipboard(value):
            QApplication.clipboard().setText(value)
        self.statusBar().showMessage(message, 4_000)
        self.toast.show_message(message)
        if recent is not None:
            self._remember_use(f"{recent[0]} · {recent[1]}", recent[2])
        QTimer.singleShot(30_000, lambda: self.clear_clipboard(token))

    def clear_clipboard(self, token: int) -> None:
        if token == self.clipboard_token:
            QApplication.clipboard().clear()

    def export_credentials(self) -> None:
        if not self.repository.unlocked:
            QMessageBox.information(self, APP_NAME, "请先解锁保险库再导出。")
            return
        rows = collect_export_rows(self.repository)
        if not rows:
            QMessageBox.information(self, APP_NAME, "保险库中没有可导出的项目。")
            return
        choice = QMessageBox.warning(
            self,
            APP_NAME,
            "导出的 Excel 文件不会加密，且包含所有明文密码。请只保存到受信任的位置，使用完毕后及时删除。确定继续导出？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        default_name = f"Keeper-凭据导出-{datetime.now().strftime('%Y%m%d')}.xlsx"
        target, _selected_filter = QFileDialog.getSaveFileName(self, "导出凭据到 Excel", default_name, "Excel 工作簿 (*.xlsx)")
        if not target:
            return
        try:
            count = write_export_xlsx(Path(target), rows)
        except PermissionError:
            QMessageBox.warning(self, APP_NAME, "无法写入该文件，它可能正在被 Excel 打开。请关闭文件后重试。")
            return
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"导出失败：{exc}")
            return
        self.statusBar().showMessage(f"已导出 {count} 个项目到 {target}", 8_000)
        QMessageBox.information(self, APP_NAME, f"已导出 {count} 个项目到：\n{target}")

    def change_master_password(self) -> None:
        if not self.unlock_for_display():
            return
        dialog = RekeyDialog(self.repository, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.statusBar().showMessage("主密码已更换，保险库已用新密码重新加密。", 6_000)

    def open_address(self, address: str) -> None:
        try:
            open_url(address)
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def connect_credential(self, entry: Entry, credential: Credential) -> None:
        try:
            if credential.kind == "ssh":
                connect_ssh(entry.address or "", credential.username, credential.password)
            else:
                connect_rdp(entry.address or "", credential.username, credential.password)
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self._remember_use(f"{entry.name} · {credential.label}", "SSH 连接" if credential.kind == "ssh" else "RDP 连接")
        if credential.password:
            self.copy_secret(credential.password, "已发起连接，密码已自动填充；如客户端仍要求输入请手动粘贴（剪贴板 30 秒后清除）")
        else:
            self.statusBar().showMessage("已发起连接。", 4_000)

    def delete_entry(self, entry: Entry) -> None:
        if not self.unlock_for_display():
            return
        choice = QMessageBox.question(self, APP_NAME, "删除这个资产及其全部项目？此操作无法撤销。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if choice == QMessageBox.StandardButton.Yes:
            self.repository.delete_entry(entry.id)
            self.selected_entry_id = None
            self.refresh_entries()
            self._refresh_home_stats()
            self.pages.setCurrentWidget(self.empty)

    def delete_credential(self, entry: Entry, credential: Credential) -> None:
        if not self.unlock_for_display():
            return
        choice = QMessageBox.question(self, APP_NAME, "删除这个项目？此操作无法撤销。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if choice == QMessageBox.StandardButton.Yes:
            self.repository.delete_credential(credential.id)
            refreshed = self.repository.get_entry(entry.id)
            if refreshed is not None:
                self.refresh_entries()
                self.render_entry(refreshed)

    def lock(self) -> None:
        """Lock and stay on the lock screen."""
        self.lock_vault()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_exit or not self._tray_available:
            self.lock_vault()
            if self.tray_icon is not None:
                self.tray_icon.hide()
            event.accept()
            return
        self.hide_to_tray()
        event.ignore()


def _allow_console_interrupt(application: QApplication, parent: QWidget) -> None:
    """Let Ctrl+C terminate the app when it runs in a terminal."""
    if getattr(sys, "frozen", False):
        return

    def _interrupt(*_args: object) -> None:
        for widget in application.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.reject()
        application.quit()

    signal.signal(signal.SIGINT, _interrupt)
    interrupt_pump = QTimer(parent)
    interrupt_pump.setInterval(200)
    interrupt_pump.timeout.connect(lambda: None)
    interrupt_pump.start()


def application_icon() -> QIcon:
    """Load the packaged Keeper icon; works from source and from frozen builds."""
    roots = [Path(__file__).parent / "assets"]
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        roots.insert(0, Path(bundle_dir) / "password_manager" / "assets")
    names = ("keeper.icns", "keeper.ico") if sys.platform == "darwin" else ("keeper.ico",)
    for root in roots:
        for name in names:
            path = root / name
            if path.exists():
                return QIcon(str(path))
    return QIcon()


def main() -> None:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    ensure_fonts_loaded()
    instance, already_running = acquire_single_instance(DEFAULT_VAULT)
    if already_running:
        QMessageBox.information(None, APP_NAME, "Keeper 已经在运行，已把它的窗口调到前台。")
        return
    application.setStyle("Fusion")
    # Match the window title bar and native chrome to the dark UI (Qt 6.8+).
    try:
        from PySide6.QtCore import Qt as _Qt

        application.styleHints().setColorScheme(_Qt.ColorScheme.Dark)
    except (AttributeError, RuntimeError):
        pass
    icon = application_icon()
    if icon.isNull():
        icon = application.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    application.setWindowIcon(icon)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_DEEP))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE_2))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_INK))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_2))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    application.setPalette(palette)
    application.setStyleSheet(STYLESHEET)
    window = VaultWindow()
    window.setWindowIcon(icon)
    window.show()
    if instance is not None:
        instance.newConnection.connect(lambda: focus_existing_window(window, instance))
    _allow_console_interrupt(application, window)
    if not getattr(sys, "frozen", False):
        print(f"提示：关闭窗口后 {APP_NAME} 会驻留在系统通知区域；右键托盘图标选择“完全退出”，或在终端按 Ctrl+C 退出。", flush=True)
    try:
        if window.unlock_for_display():
            sys.exit(application.exec())
    except KeyboardInterrupt:
        pass
    finally:
        window.quit_application()
        application.quit()


if __name__ == "__main__":
    main()
