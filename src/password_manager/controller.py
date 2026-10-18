"""The bridge between the QML view layer and the Python backend.

Everything the UI needs from the vault lives here as QObject properties and
slots; QML never imports a backend module and the backend never knows QML
exists. The business rules are the ones app.py grew over time - unlocking
with its persisted throttle, auto-lock timers, clipboard hygiene, tray,
entry/credential CRUD with validation, export - relocated, not rewritten.

The controller is deliberately testable without a QML engine: tests drive it
as a plain QObject under the offscreen platform.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication

from password_manager.generator import (
    GENERATED_PASSWORD_LENGTH,
    STRENGTH_LABELS,
    entropy_bits,
    generate_password,
    strength_level,
)
from password_manager.models import Credential, CredentialDraft, Entry, EntryDraft

# Imported into this module's namespace so tests can monkeypatch them here,
# exactly the way the widgets app did with password_manager.app.
from password_manager.services.actions import (
    connect_rdp,
    connect_ssh,
    extract_url,
    open_url,
    set_concealed_clipboard,
    system_idle_seconds,
)
from password_manager.vault.repository import (
    VaultRepository,
)

if TYPE_CHECKING:
    from PySide6.QtNetwork import QLocalServer

APP_NAME = "Keeper"
DEFAULT_VAULT = Path(os.environ.get("PASSWORD_MANAGER_VAULT", Path.home() / ".keeper" / "vault.sqlcipher"))

UNLOCK_FAILURE_DELAY_MIN_MS = 500
UNLOCK_FAILURE_DELAY_MAX_MS = 8_000
THROTTLE_FILE_NAME = "unlock-throttle.json"
IDLE_POLL_MS = 5_000
CLIPBOARD_CLEAR_MS = 30_000
AUTO_LOCK_MS = 10 * 60 * 1_000


def unlock_failure_delay_ms(failure_count: int) -> int:
    """Lockout delay for consecutive failed unlocks: 0.5s doubling to 8s."""
    if failure_count <= 0:
        return 0
    return min(UNLOCK_FAILURE_DELAY_MIN_MS * 2 ** (failure_count - 1), UNLOCK_FAILURE_DELAY_MAX_MS)


def load_unlock_throttle(path: Path) -> tuple[int, float]:
    """Read the persisted failure count and deadline as (failures, monotonic)."""
    import json

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        failures = int(raw["failures"])
        deadline = float(raw["until"])
    except (OSError, ValueError, TypeError, KeyError):
        return 0, 0.0
    if failures <= 0:
        return 0, 0.0
    remaining = deadline - time.time()
    return failures, (time.monotonic() + remaining if remaining > 0 else 0.0)


def save_unlock_throttle(failures: int, deadline: float, path: Path) -> None:
    """Persist the throttle state; ``deadline`` is on the monotonic clock."""
    import json
    import os

    if failures <= 0 and not path.exists():
        return
    remaining = max(0.0, deadline - time.monotonic())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"failures": max(0, failures), "until": time.time() + remaining}, handle)
    except OSError:
        pass


def single_instance_name(vault_path: Path) -> str:
    import hashlib

    digest = hashlib.sha256(os.fsencode(vault_path.expanduser())).hexdigest()[:16]
    return f"keeper-vault-{digest}"


def acquire_single_instance(vault_path: Path) -> tuple[QLocalServer | None, bool]:
    """Report whether another Keeper already owns this vault.

    The existing owner is probed *before* listening: on Windows, two
    QLocalServers may both accept ``listen()`` on one pipe name, so a
    successful listen does not by itself prove exclusivity - asking the
    running instance directly does.
    """
    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    name = single_instance_name(vault_path)
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):
        probe.write(b"activate")
        probe.waitForBytesWritten(300)
        probe.close()
        return None, True
    probe.close()

    server = QLocalServer()
    if server.listen(name):
        return server, False

    # Nobody answered but the name is taken: a socket left behind by a crash.
    QLocalServer.removeServer(name)
    return (server, False) if server.listen(name) else (None, False)


EXPORT_COLUMNS = ("类型", "资产名称", "地址", "项目", "用户名", "密码", "说明", "标签")


def collect_export_rows(repository: VaultRepository) -> list[tuple[str, ...]]:
    """One plaintext row per credential across all entries."""
    rows: list[tuple[str, ...]] = []
    for entry in repository.list_entries():
        entry_type = "应用" if entry.kind == "application" else "服务器"
        for credential in repository.list_credentials(entry.id):
            rows.append(
                (
                    entry_type,
                    entry.name,
                    entry.address or "",
                    credential.label,
                    credential.username,
                    credential.password,
                    credential.extra,
                    ",".join(entry.tags),
                )
            )
    return rows


def write_export_xlsx(path: Path, rows: list[tuple[str, ...]]) -> int:
    """Write the export rows to an .xlsx workbook and return the row count."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "凭据导出"
    sheet.append(list(EXPORT_COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(list(row))
        # Exported values are untrusted free text: openpyxl would store a value
        # starting with "=" as a live spreadsheet formula. Force plain text.
        for cell in sheet[sheet.max_row]:
            if cell.value is not None:
                cell.data_type = "s"
    for index, width in enumerate((8, 24, 28, 24, 20, 24, 32, 18), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(path)
    return len(rows)


def masked_password(password: str) -> str:
    return "•" * min(12, max(6, len(password)))


CHARSET_INFO = (
    {"key": "digits", "label": "数字 0-9"},
    {"key": "letters", "label": "英文 aA"},
    {"key": "symbols", "label": "符号 !@#"},
)


class EntryListModel(QAbstractListModel):
    """Sidebar rows: grouped by kind, searchable, filterable."""

    IdRole = Qt.ItemDataRole.UserRole + 1
    KindRole = Qt.ItemDataRole.UserRole + 2
    NameRole = Qt.ItemDataRole.UserRole + 3
    SubtitleRole = Qt.ItemDataRole.UserRole + 4
    CountRole = Qt.ItemDataRole.UserRole + 5
    TagsRole = Qt.ItemDataRole.UserRole + 6
    SectionRole = Qt.ItemDataRole.UserRole + 7

    ROLE_NAMES = {
        IdRole: b"eid",
        KindRole: b"kind",
        NameRole: b"name",
        SubtitleRole: b"subtitle",
        CountRole: b"count",
        TagsRole: b"tags",
        SectionRole: b"section",
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, ARG002, B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        return row.get(self.ROLE_NAMES.get(role, b"").decode(), None)

    def roleNames(self) -> dict:  # noqa: N802
        return dict(self.ROLE_NAMES)

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_for(self, entry_id: int) -> dict | None:
        return next((row for row in self._rows if row["eid"] == entry_id), None)


class VaultController(QObject):
    """All state and actions the QML UI binds to."""

    vaultStateChanged = Signal()
    entriesChanged = Signal()
    selectedEntryChanged = Signal()
    recentChanged = Signal()
    statsChanged = Signal()
    toastRequested = Signal(str)
    showWindowRequested = Signal()
    quitRequested = Signal()

    def __init__(
        self,
        vault_path: Path = DEFAULT_VAULT,
        *,
        tray_available: bool | None = None,
        auto_lock_ms: int | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = VaultRepository(vault_path)
        self.throttle_path = vault_path.expanduser().parent / THROTTLE_FILE_NAME
        self.unlock_failure_count, self.unlock_throttled_until = load_unlock_throttle(self.throttle_path)
        self._vault_state = "fresh"
        if self.repository.exists:
            self._vault_state = "locked"
        self.auto_lock_interval_ms = auto_lock_ms if auto_lock_ms is not None else AUTO_LOCK_MS
        self._clipboard_token = 0
        self._recent: list[dict] = []
        self._search = ""
        self._filter_kind = "all"
        self._selected_entry: dict = {}
        self._credentials: list[dict] = []
        self._stats = {"servers": 0, "applications": 0, "credentials": 0}
        self._ui_visible = False
        self._hidden_to_tray = False
        self._allow_exit = False
        self.entries_model = EntryListModel(self)

        self.auto_lock_timer = QTimer(self)
        self.auto_lock_timer.setSingleShot(True)
        self.auto_lock_timer.setInterval(self.auto_lock_interval_ms)
        self.auto_lock_timer.timeout.connect(self.autoLock)
        self.idle_poll_timer = QTimer(self)
        self.idle_poll_timer.setInterval(IDLE_POLL_MS)
        self.idle_poll_timer.timeout.connect(self.lockWhenIdle)

        self._tray_available = self._probe_tray() if tray_available is None else tray_available
        self.tray_icon = None
        if self._tray_available:
            self._build_tray()

    # -- tray ----------------------------------------------------------------

    @staticmethod
    def _probe_tray() -> bool:
        from PySide6.QtWidgets import QSystemTrayIcon

        return QSystemTrayIcon.isSystemTrayAvailable()

    def _build_tray(self) -> None:
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        self.tray_icon = QSystemTrayIcon(QGuiApplication.windowIcon(), self)
        menu = QMenu()
        open_action = QAction("打开 Keeper", menu)
        open_action.triggered.connect(self._tray_open)
        quit_action = QAction("完全退出", menu)
        quit_action.triggered.connect(self._tray_quit)
        menu.addAction(open_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_open(self) -> None:
        self.showWindowRequested.emit()

    def _tray_quit(self) -> None:
        self.prepare_quit()
        self.quitRequested.emit()

    def _tray_activated(self, reason) -> None:  # noqa: ANN001
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.showWindowRequested.emit()

    # -- state properties ------------------------------------------------------

    @Property(str, notify=vaultStateChanged)
    def vaultState(self) -> str:  # noqa: N802
        return self._vault_state

    @Property(int, constant=True)
    def autoLockMinutes(self) -> int:  # noqa: N802
        return max(1, round(self.auto_lock_interval_ms / 60_000))

    @Property(bool, constant=True)
    def trayAvailable(self) -> bool:  # noqa: N802
        return self._tray_available

    @Property("QVariantList", constant=True)
    def charsets(self) -> list:  # noqa: N802
        return [dict(info) for info in CHARSET_INFO]

    @Property("QVariantList", constant=True)
    def strengthLabels(self) -> list:  # noqa: N802
        return list(STRENGTH_LABELS)

    @Property("QVariantList", notify=recentChanged)
    def recentUses(self) -> list:  # noqa: N802
        return list(self._recent)

    @Property("QVariantMap", notify=selectedEntryChanged)
    def selectedEntry(self) -> dict:  # noqa: N802
        return dict(self._selected_entry)

    @Property("QVariantList", notify=selectedEntryChanged)
    def credentials(self) -> list:  # noqa: N802
        return list(self._credentials)

    @Property(int, notify=statsChanged)
    def serversCount(self) -> int:  # noqa: N802
        return self._stats["servers"]

    @Property(int, notify=statsChanged)
    def applicationsCount(self) -> int:  # noqa: N802
        return self._stats["applications"]

    @Property(int, notify=statsChanged)
    def credentialsCount(self) -> int:  # noqa: N802
        return self._stats["credentials"]

    def get_search(self) -> str:
        return self._search

    def set_search(self, value: str) -> None:
        if value == self._search:
            return
        self._search = value
        self.refresh_entries()

    Search = Property(str, get_search, set_search, notify=entriesChanged)

    def get_filter_kind(self) -> str:
        return self._filter_kind

    def set_filter_kind(self, value: str) -> None:
        if value == self._filter_kind:
            return
        self._filter_kind = value if value in {"all", "server", "application"} else "all"
        self.refresh_entries()

    FilterKind = Property(str, get_filter_kind, set_filter_kind, notify=entriesChanged)

    @Property(QObject, constant=True)
    def entriesModel(self) -> EntryListModel:  # noqa: N802
        return self.entries_model

    # -- unlock / lock ----------------------------------------------------------

    @Slot(str, str, result="QVariantMap")
    def createVault(self, password: str, confirm: str) -> dict:  # noqa: N802
        if password != confirm:
            return {"ok": False, "error": "两次输入的密码不一致。"}
        try:
            self.repository.initialize(password)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - disk failures must surface in the dialog
            return {"ok": False, "error": f"操作失败：{exc}"}
        self._after_unlock_success()
        return {"ok": True}

    @Slot(str, result="QVariantMap")
    def attemptUnlock(self, password: str) -> dict:  # noqa: N802
        remaining_ms = int((self.unlock_throttled_until - time.monotonic()) * 1_000)
        if remaining_ms > 0:
            return {"ok": False, "error": "throttled", "throttleMs": remaining_ms}
        try:
            self.repository.unlock(password)
        except ValueError as exc:
            self._register_failed_attempt()
            delay = unlock_failure_delay_ms(self.unlock_failure_count)
            return {"ok": False, "error": str(exc), "throttleMs": delay}
        except FileNotFoundError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"操作失败：{exc}"}
        self._after_unlock_success()
        return {"ok": True}

    def _register_failed_attempt(self) -> None:
        self.unlock_failure_count += 1
        delay_ms = unlock_failure_delay_ms(self.unlock_failure_count)
        self.unlock_throttled_until = time.monotonic() + delay_ms / 1_000
        self._persist_throttle()

    def _after_unlock_success(self) -> None:
        self.unlock_failure_count = 0
        self.unlock_throttled_until = 0.0
        self._persist_throttle()
        self._vault_state = "unlocked"
        self.vaultStateChanged.emit()
        self.refresh_entries()
        self.idle_poll_timer.start()

    def _persist_throttle(self) -> None:
        save_unlock_throttle(self.unlock_failure_count, self.unlock_throttled_until, self.throttle_path)

    @Slot()
    def lock(self) -> None:
        self.auto_lock_timer.stop()
        self.idle_poll_timer.stop()
        self._clipboard_token += 1
        QGuiApplication.clipboard().clear()
        self.repository.lock()
        self._vault_state = "locked"
        self._selected_entry = {}
        self._credentials = []
        self.selectedEntryChanged.emit()
        self._search = ""
        self._recent = []
        self.recentChanged.emit()
        self.refresh_entries()
        self.vaultStateChanged.emit()
        self.toastRequested.emit("保险库已锁定。")

    @Slot()
    def autoLock(self) -> None:  # noqa: N802
        if not self._ui_visible and self.repository.unlocked:
            self.lock()
            if self.tray_icon is not None:
                self.tray_icon.showMessage(APP_NAME, f"保险库已因 {self.autoLockMinutes} 分钟未打开而自动锁定。")

    @Slot()
    def lockWhenIdle(self) -> None:  # noqa: N802
        if not self.repository.unlocked or not self._ui_visible:
            return
        idle_seconds = system_idle_seconds()
        if idle_seconds is None or idle_seconds * 1_000 < self.auto_lock_interval_ms:
            return
        self.lock()
        self.toastRequested.emit(f"已因 {self.autoLockMinutes} 分钟无操作自动锁定。")

    @Slot(bool)
    def setUiVisible(self, visible: bool) -> None:  # noqa: N802
        self._ui_visible = visible

    @Slot()
    def markHiddenToTray(self) -> None:  # noqa: N802
        self._hidden_to_tray = True
        self._ui_visible = False
        if self.repository.unlocked:
            self.auto_lock_timer.start()

    @Slot()
    def restoreFromTray(self) -> None:  # noqa: N802
        self._hidden_to_tray = False
        self.auto_lock_timer.stop()
        self.showWindowRequested.emit()

    @Slot()
    def prepareQuit(self) -> None:  # noqa: N802
        self._allow_exit = True
        self.lock()

    # -- entries ---------------------------------------------------------------

    def refresh_entries(self) -> None:
        if not self.repository.unlocked:
            self.entries_model.set_rows([])
            self._recompute_stats([])
            return
        counts = self.repository.entry_credential_counts()
        rows: list[dict] = []
        all_entries = self.repository.list_entries(self._search)
        for entry in all_entries:
            if self._filter_kind != "all" and entry.kind != self._filter_kind:
                continue
            subtitle = self._entry_subtitle(entry)
            rows.append(
                {
                    "eid": entry.id,
                    "kind": entry.kind,
                    "name": entry.name or "未命名服务器",
                    "subtitle": subtitle,
                    "count": counts.get(entry.id, 0),
                    "tags": entry.tags[:3],
                    "section": "服务器" if entry.kind == "server" else "应用",
                }
            )
        self.entries_model.set_rows(rows)
        self._recompute_stats(all_entries, counts)
        self.entriesChanged.emit()

    @staticmethod
    def _entry_subtitle(entry: Entry) -> str:
        if entry.kind == "server":
            return " · ".join(entry.tags[:3]) if entry.tags else (entry.address or "")
        address = entry.address or ""
        for scheme in ("https://", "http://"):
            if address.startswith(scheme):
                address = address[len(scheme):]
                break
        sub = address
        if entry.tags:
            sub = (sub + " · " if sub else "") + " · ".join(entry.tags[:3])
        return sub

    def _recompute_stats(self, entries: list[Entry], counts: dict[int, int] | None = None) -> None:
        if counts is None:
            counts = self.repository.entry_credential_counts() if self.repository.unlocked else {}
        servers = sum(1 for entry in entries if entry.kind == "server")
        credentials = sum(counts.get(entry.id, 0) for entry in entries) if self.repository.unlocked else 0
        new_stats = {"servers": servers, "applications": len(entries) - servers, "credentials": credentials}
        if new_stats != self._stats:
            self._stats = new_stats
            self.statsChanged.emit()

    @Slot(int)
    def selectEntry(self, entry_id: int) -> None:  # noqa: N802
        if not self.repository.unlocked:
            return
        entry = self.repository.get_entry(entry_id)
        if entry is None:
            self.clearSelection()
            return
        self._selected_entry = {
            "id": entry.id,
            "kind": entry.kind,
            "name": entry.name,
            "address": entry.address or "",
            "tags": entry.tags,
            "eyebrow": "服务器工作区" if entry.kind == "server" else "应用",
            "credentialCount": len(self.repository.list_credentials(entry.id)),
        }
        self._reload_credentials()
        self.selectedEntryChanged.emit()

    @Slot()
    def clearSelection(self) -> None:  # noqa: N802
        self._selected_entry = {}
        self._credentials = []
        self.selectedEntryChanged.emit()

    def _reload_credentials(self) -> None:
        entry = self.repository.get_entry(self._selected_entry["id"])
        if entry is None:
            self._credentials = []
            return
        self._credentials = [self._credential_dict(entry, c) for c in self.repository.list_credentials(entry.id)]

    @staticmethod
    def _credential_dict(entry: Entry, credential: Credential) -> dict:
        is_login = credential.kind in {"ssh", "rdp"}
        url = extract_url(credential.extra, credential.label)
        return {
            "id": credential.id,
            "kind": credential.kind,
            "label": credential.label,
            "username": credential.username or "未保存用户名",
            "password": credential.password,
            "masked": masked_password(credential.password) if credential.password else "",
            "extra": credential.extra,
            "hasPassword": bool(credential.password),
            "isLogin": is_login,
            "showConnect": entry.kind == "server" and is_login,
            "connectLabel": ("SSH 连接" if credential.kind == "ssh" else "RDP 连接") if is_login else "",
            "badge": {"ssh": "系统登录 · SSH", "rdp": "系统登录 · RDP"}.get(credential.kind, ""),
            "url": url or "",
            "icon": {"ssh": "terminal", "rdp": "monitor"}.get(credential.kind) or ("globe" if url else "key"),
        }

    @Slot(str, str, str, "QVariantList", int, result="QVariantMap")
    def saveEntry(self, kind: str, name: str, address: str, tags, entry_id: int) -> dict:  # noqa: N802
        draft = EntryDraft(kind=kind, name=name, address=address, tags=[str(tag) for tag in tags])
        try:
            saved = self.repository.save_entry(draft, entry_id if entry_id and entry_id > 0 else None)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        self.refresh_entries()
        return {"ok": True, "entryId": saved.id}

    @Slot(int)
    def deleteEntry(self, entry_id: int) -> None:  # noqa: N802
        self.repository.delete_entry(entry_id)
        self.clearSelection()
        self.refresh_entries()

    @Slot(int, str, str, str, str, str, int, result="QVariantMap")
    def saveCredential(self, entry_id: int, kind: str, label: str, username: str, password: str, extra: str, credential_id: int) -> dict:  # noqa: N802
        draft = CredentialDraft(kind=kind, label=label, username=username, password=password, extra=extra)
        try:
            self.repository.save_credential(entry_id, draft, credential_id if credential_id and credential_id > 0 else None)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        self._refresh_after_credential_change(entry_id)
        return {"ok": True}

    @Slot(int, int)
    def deleteCredential(self, credential_id: int, entry_id: int) -> None:  # noqa: N802
        self.repository.delete_credential(credential_id)
        self._refresh_after_credential_change(entry_id)

    @Slot(int, str, result=bool)
    def moveCredential(self, credential_id: int, direction: str) -> bool:  # noqa: N802
        try:
            self.repository.move_credential(credential_id, direction)
        except (ValueError, RuntimeError):
            return False
        self._reload_credentials()
        self.selectedEntryChanged.emit()
        return True

    def _refresh_after_credential_change(self, entry_id: int) -> None:
        self.refresh_entries()
        if self._selected_entry.get("id") == entry_id:
            self.selectEntry(entry_id)

    # -- generator ---------------------------------------------------------------

    @Slot(str, int, result=str)
    def generate(self, mode: str, length: int) -> str:
        try:
            return generate_password(mode, length)
        except ValueError:
            return generate_password("digits+letters+symbols", GENERATED_PASSWORD_LENGTH)

    @Slot(str, int, result=int)
    def strengthFor(self, mode: str, length: int) -> int:  # noqa: N802
        keys = [key for key in mode.split("+") if key]
        return strength_level(entropy_bits(length, keys))

    # -- secrets -----------------------------------------------------------------

    def _copy_secret(self, value: str, message: str, recent: tuple[str, str] | None = None) -> bool:
        if not value:
            self.toastRequested.emit("没有可复制的内容。")
            return False
        self._clipboard_token += 1
        token = self._clipboard_token
        if not set_concealed_clipboard(value):
            QGuiApplication.clipboard().setText(value)
        self.toastRequested.emit(message)
        if recent is not None:
            self._remember_use(*recent)
        QTimer.singleShot(CLIPBOARD_CLEAR_MS, lambda: self._clear_clipboard(token, value))
        return True

    def _clear_clipboard(self, token: int, secret: str = "") -> None:
        """Wipe the copied secret, unless the user has since copied something else.

        The token only changes when Keeper itself copies again, so a plain
        token match does not prove the pasteboard still holds our value: the
        user may have copied unrelated text in another app in the meantime.
        Clearing blindly would destroy that content, so the clipboard is only
        emptied when it still shows the secret we put there.
        """
        if token != self._clipboard_token:
            return
        clipboard = QGuiApplication.clipboard()
        if not secret or clipboard.text() == secret:
            clipboard.clear()

    @Slot(int, str)
    def copyCredentialSecret(self, credential_id: int, what: str) -> None:  # noqa: N802
        credential = self.repository.get_credential(credential_id)
        if credential is None:
            return
        entry = self.repository.get_entry(credential.entry_id)
        title = f"{entry.name} · {credential.label}" if entry else credential.label
        if what == "username":
            self._copy_secret(credential.username, "用户名已复制，30 秒后清除", (title, "复制了用户名"))
        else:
            self._copy_secret(credential.password, "密码已复制，30 秒后清除", (title, "复制了密码"))

    @Slot(str)
    def copyGeneratedPassword(self, password: str) -> None:  # noqa: N802
        self._copy_secret(password, "密码已复制，30 秒后清除")

    @Slot(int)
    def connectLogin(self, credential_id: int) -> None:  # noqa: N802
        credential = self.repository.get_credential(credential_id)
        if credential is None:
            return
        entry = self.repository.get_entry(credential.entry_id)
        if entry is None:
            return
        try:
            if credential.kind == "ssh":
                connect_ssh(entry.address or "", credential.username, credential.password)
            else:
                connect_rdp(entry.address or "", credential.username, credential.password)
        except ValueError as exc:
            self.toastRequested.emit(str(exc))
            return
        self._remember_use(f"{entry.name} · {credential.label}", "SSH 连接" if credential.kind == "ssh" else "RDP 连接")
        if credential.password:
            self._copy_secret(
                credential.password,
                "已发起连接，密码已自动填充；如客户端仍要求输入请手动粘贴（剪贴板 30 秒后清除）",
            )
        else:
            self.toastRequested.emit("已发起连接。")

    @Slot(str)
    def openAddress(self, address: str) -> None:  # noqa: N802
        try:
            open_url(address)
        except ValueError as exc:
            self.toastRequested.emit(str(exc))

    def _remember_use(self, title: str, sub: str) -> None:
        self._recent.insert(0, {"title": title, "sub": sub})
        del self._recent[6:]
        self.recentChanged.emit()

    # -- export / rekey -------------------------------------------------------------

    @Slot(QUrl, result="QVariantMap")
    def exportVault(self, target) -> dict:  # noqa: N802
        """Export the vault; ``target`` is the FileDialog's selected file.

        QML hands over a url, which must be resolved with ``QUrl.toLocalFile``:
        stringifying it in QML yields the fully percent-encoded form (a path
        with spaces or Chinese characters would be written out literally as
        ``%20``/``%E5...``), and stripping ``file:///`` by hand drops the
        leading slash on POSIX systems. Plain strings are still accepted for
        direct callers and tests.
        """
        if not self.repository.unlocked:
            return {"ok": False, "error": "请先解锁保险库再导出。"}
        path = target.toLocalFile() if isinstance(target, QUrl) else str(target)
        if not path:
            return {"ok": False, "error": "没有选择导出位置。"}
        rows = collect_export_rows(self.repository)
        if not rows:
            return {"ok": False, "error": "保险库中没有可导出的项目。"}
        try:
            count = write_export_xlsx(Path(path), rows)
        except PermissionError:
            return {"ok": False, "error": "无法写入该文件，它可能正在被 Excel 打开。请关闭文件后重试。"}
        except OSError as exc:
            return {"ok": False, "error": f"导出失败：{exc}"}
        return {"ok": True, "count": count, "path": path}

    @Slot(str, str, str, result="QVariantMap")
    def rekeyVault(self, current: str, new_password: str, confirm: str) -> dict:  # noqa: N802
        if new_password != confirm:
            return {"ok": False, "error": "两次输入的新密码不一致。"}
        try:
            self.repository.rekey(current, new_password)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"操作失败：{exc}"}
        return {"ok": True}
