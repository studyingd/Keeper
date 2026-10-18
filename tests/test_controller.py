"""Logic-level tests for the QML bridge controller (no QML engine needed)."""

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import password_manager.controller as controller_module
from password_manager.controller import (
    VaultController,
    collect_export_rows,
    load_unlock_throttle,
    masked_password,
    save_unlock_throttle,
    unlock_failure_delay_ms,
    write_export_xlsx,
)
from password_manager.models import CredentialDraft, EntryDraft
from password_manager.vault.repository import VaultRepository


MASTER_PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="session")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def keep_tests_off_the_real_pasteboard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(controller_module, "set_concealed_clipboard", lambda value: False)


@pytest.fixture
def vault(tmp_path: Path) -> VaultRepository:
    repository = VaultRepository(tmp_path / "vault.sqlcipher")
    repository.initialize(MASTER_PASSWORD)
    yield repository
    repository.lock()


@pytest.fixture
def controller(vault: VaultRepository) -> VaultController:
    instance = VaultController(vault.path, tray_available=False)
    instance.repository = vault
    yield instance
    if instance.repository.unlocked:
        instance.lock()


# ---------------------------------------------------------------------------
# unlock flow with the persisted throttle
# ---------------------------------------------------------------------------


def test_unlock_failure_delay_grows_from_half_second_to_eight_second_cap() -> None:
    assert unlock_failure_delay_ms(0) == 0
    assert unlock_failure_delay_ms(1) == 500
    assert unlock_failure_delay_ms(5) == 8_000
    assert unlock_failure_delay_ms(9) == 8_000


def test_controller_starts_locked_on_existing_vault(vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)

    assert controller.vaultState == "locked"
    assert controller.autoLockMinutes == 10
    assert controller.trayAvailable is False
    assert controller.entriesModel.rowCount() == 0


def test_failed_unlock_registers_throttle_and_refuses_retry(application: QApplication, vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)

    result = controller.attemptUnlock("wrong-password")

    assert result["ok"] is False and "无法解锁" in result["error"]
    assert result["throttleMs"] == unlock_failure_delay_ms(1)
    assert controller.unlock_failure_count == 1
    assert controller.unlock_throttled_until > time.monotonic()

    refused = controller.attemptUnlock("anything")
    assert refused["ok"] is False and refused["error"] == "throttled"
    assert refused["throttleMs"] > 0
    assert controller.unlock_failure_count == 1  # a refused retry does not count


def test_successful_unlock_resets_and_persists_the_throttle(application: QApplication, vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)
    controller.unlock_failure_count = 3
    controller.unlock_throttled_until = 0.0
    save_unlock_throttle(3, time.monotonic() + 4.0, controller.throttle_path)

    result = controller.attemptUnlock(MASTER_PASSWORD)

    assert result["ok"] is True
    assert controller.vaultState == "unlocked"
    assert controller.unlock_failure_count == 0
    assert load_unlock_throttle(controller.throttle_path) == (0, 0.0)
    assert controller.idle_poll_timer.isActive()


def test_throttle_survives_a_new_controller(application: QApplication, vault: VaultRepository) -> None:
    first = VaultController(vault.path, tray_available=False)
    save_unlock_throttle(3, time.monotonic() + 4.0, first.throttle_path)

    second = VaultController(vault.path, tray_available=False)

    assert second.unlock_failure_count == 3
    assert second.unlock_throttled_until > time.monotonic()


def test_create_vault_validates_confirmation(application: QApplication, tmp_path: Path) -> None:
    controller = VaultController(tmp_path / "fresh.sqlcipher", tray_available=False)

    assert controller.vaultState == "fresh"
    mismatch = controller.createVault("pw-a", "pw-b")
    assert mismatch["ok"] is False and mismatch["error"] == "两次输入的密码不一致。"

    created = controller.createVault("pw-a", "pw-a")
    assert created["ok"] is True
    assert controller.vaultState == "unlocked"
    assert controller.repository.unlocked


# ---------------------------------------------------------------------------
# locking and auto-lock
# ---------------------------------------------------------------------------


def test_lock_clears_sensitive_state_and_recent(application: QApplication, vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="主账号", password="p"))
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    controller.selectEntry(entry.id)
    controller._remember_use("x", "y")
    controller.Search = "Port"

    toasts: list[str] = []
    controller.toastRequested.connect(toasts.append)
    controller.lock()

    assert controller.vaultState == "locked"
    assert controller.credentials == []
    assert controller.selectedEntry == {}
    assert controller.recentUses == []
    assert controller.get_search() == ""
    assert controller.entriesModel.rowCount() == 0
    assert not controller.idle_poll_timer.isActive()
    assert toasts == ["保险库已锁定。"]
    assert not controller.repository.unlocked


def test_auto_lock_only_fires_while_hidden(application: QApplication, vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True

    controller.setUiVisible(True)
    controller.autoLock()
    assert controller.vaultState == "unlocked"

    controller.markHiddenToTray()
    assert controller.auto_lock_timer.isActive()
    controller.autoLock()
    assert controller.vaultState == "locked"


def test_lock_when_idle_uses_the_system_idle_counter(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    controller.setUiVisible(True)

    monkeypatch.setattr(controller_module, "system_idle_seconds", lambda: 5.0)
    controller.lockWhenIdle()
    assert controller.vaultState == "unlocked"

    monkeypatch.setattr(controller_module, "system_idle_seconds", lambda: 999.0)
    toasts: list[str] = []
    controller.toastRequested.connect(toasts.append)
    controller.lockWhenIdle()
    assert controller.vaultState == "locked"
    assert any("无操作自动锁定" in message for message in toasts)

    # A hidden window is left to its own elapsed-time timer.
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    controller.markHiddenToTray()
    monkeypatch.setattr(controller_module, "system_idle_seconds", lambda: 999.0)
    controller.lockWhenIdle()
    assert controller.vaultState == "unlocked"


# ---------------------------------------------------------------------------
# entries model / selection / stats
# ---------------------------------------------------------------------------


def make_data(vault: VaultRepository) -> dict:
    server = vault.save_entry(EntryDraft(kind="server", name="生产数据库服务器", address="192.168.1.101:2222", tags=["MySQL", "生产环境"]))
    app_entry = vault.save_entry(EntryDraft(kind="application", name="阿里云", address="https://console.aliyun.com", tags=["云平台"]))
    ssh = vault.save_credential(server.id, CredentialDraft(kind="ssh", label="系统登录账号", username="root", password="sekrit"))
    mysql = vault.save_credential(server.id, CredentialDraft(kind="custom", label="MySQL", username="db_admin", password="hunter2", extra=""))
    web = vault.save_credential(server.id, CredentialDraft(kind="custom", label="网站后台", username="admin", password="p", extra="https://admin.example.com"))
    main = vault.save_credential(app_entry.id, CredentialDraft(kind="custom", label="主账号", username="ops@example.com", password="p2"))
    return {"server": server, "app": app_entry, "ssh": ssh, "mysql": mysql, "web": web, "main": main}


def test_entries_model_groups_searches_and_filters(application: QApplication, vault: VaultRepository) -> None:
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True

    model = controller.entriesModel
    assert model.rowCount() == 2
    first = model.row_for(data["server"].id)
    assert first["section"] == "服务器" and first["count"] == 3
    assert "MySQL · 生产环境" == first["subtitle"]
    assert model.row_for(data["app"].id)["subtitle"] == "console.aliyun.com · 云平台"

    controller.Search = "192.168.1"
    assert [model.rowCount()] == [1]
    controller.Search = "mysql"
    assert model.rowCount() == 1
    controller.Search = ""
    controller.FilterKind = "application"
    assert model.rowCount() == 1
    controller.FilterKind = "all"
    assert model.rowCount() == 2

    assert controller.serversCount == 1
    assert controller.applicationsCount == 1
    assert controller.credentialsCount == 4


def test_select_entry_loads_credential_cards(application: QApplication, vault: VaultRepository) -> None:
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True

    controller.selectEntry(data["server"].id)

    entry = controller.selectedEntry
    assert entry["eyebrow"] == "服务器工作区"
    assert entry["tags"] == ["MySQL", "生产环境"]

    by_id = {c["id"]: c for c in controller.credentials}
    ssh = by_id[data["ssh"].id]
    assert ssh["isLogin"] and ssh["showConnect"] and ssh["connectLabel"] == "SSH 连接"
    assert ssh["badge"] == "系统登录 · SSH" and ssh["icon"] == "terminal"
    assert ssh["masked"] == masked_password("sekrit") and "sekrit" not in ssh["masked"]
    web = by_id[data["web"].id]
    assert web["url"] == "https://admin.example.com" and web["icon"] == "globe"
    stray = by_id[data["mysql"].id]
    assert not stray["showConnect"] and stray["url"] == ""

    # An application entry never shows connect buttons even for login kinds.
    controller.selectEntry(data["app"].id)
    assert all(not c["showConnect"] for c in controller.credentials)
    assert all(c["connectLabel"] == "" for c in controller.credentials if not c["isLogin"])


def test_save_entry_validates_and_reports_errors(application: QApplication, vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True

    bad = controller.saveEntry("server", "db", "db.internal", [], -1)
    assert bad["ok"] is False and "IPv4 或 IPv6" in bad["error"]

    good = controller.saveEntry("server", "数据库", "10.0.0.5", ["MySQL"], -1)
    assert good["ok"] is True and good["entryId"] > 0
    assert controller.entriesModel.rowCount() == 1
    assert controller.serversCount == 1


def test_credential_crud_and_reorder_via_controller(application: QApplication, vault: VaultRepository) -> None:
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    controller.selectEntry(data["server"].id)

    labels = lambda: [c["label"] for c in controller.credentials]  # noqa: E731
    assert labels() == ["系统登录账号", "MySQL", "网站后台"]

    assert controller.moveCredential(data["web"].id, "up") is True
    assert labels() == ["系统登录账号", "网站后台", "MySQL"]

    assert controller.saveCredential(data["server"].id, "custom", "Redis", "", "redis-pass", "", -1)["ok"] is True
    assert labels()[-1] == "Redis"
    assert controller.credentialsCount == 5  # 服务器 4 + 应用 1，全库口径

    controller.deleteCredential(data["mysql"].id, data["server"].id)
    assert "MySQL" not in labels()
    assert controller.credentialsCount == 4

    bad = controller.saveCredential(data["server"].id, "custom", "  ", "", "", "", -1)
    assert bad["ok"] is False and bad["error"] == "项目名称不能为空。"


def test_delete_entry_clears_selection(application: QApplication, vault: VaultRepository) -> None:
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    controller.selectEntry(data["app"].id)

    controller.deleteEntry(data["app"].id)

    assert controller.selectedEntry == {}
    assert controller.entriesModel.rowCount() == 1
    assert controller.applicationsCount == 0


# ---------------------------------------------------------------------------
# secrets, clipboard and connections
# ---------------------------------------------------------------------------


def test_copy_prefers_the_concealed_pasteboard(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(controller_module, "set_concealed_clipboard", lambda value: (copied.append(value), True)[1])
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    QApplication.clipboard().clear()

    controller.copyCredentialSecret(data["mysql"].id, "password")

    assert copied == ["hunter2"]
    assert QApplication.clipboard().text() == ""  # Qt untouched when concealed works
    assert controller.recentUses[0]["title"] == "生产数据库服务器 · MySQL"

    # The delayed clear only wipes when the token still matches.
    controller._clear_clipboard(controller._clipboard_token)


def test_copy_username_and_generated_password(application: QApplication, vault: VaultRepository) -> None:
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    QApplication.clipboard().clear()

    controller.copyCredentialSecret(data["mysql"].id, "username")
    assert QApplication.clipboard().text() == "db_admin"

    controller.copyGeneratedPassword("Xk9#mP2$vL7@")
    assert QApplication.clipboard().text() == "Xk9#mP2$vL7@"
    controller._clear_clipboard(controller._clipboard_token)
    assert QApplication.clipboard().text() == ""


def test_connect_login_launches_ssh_and_copies_password(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(controller_module, "connect_ssh", lambda host, username, password: calls.append((host, username, password)))
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True

    controller.connectLogin(data["ssh"].id)

    assert calls == [("192.168.1.101:2222", "root", "sekrit")]  # 端口由 actions 内部拆分
    assert QApplication.clipboard().text() == "sekrit"
    assert controller.recentUses[0] == {"title": "生产数据库服务器 · 系统登录账号", "sub": "SSH 连接"}
    controller._clear_clipboard(controller._clipboard_token)


def test_connect_failure_reports_the_error(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(host, username, password):
        raise ValueError("该服务器没有保存 IP 地址。")

    monkeypatch.setattr(controller_module, "connect_rdp", boom)
    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    toasts: list[str] = []
    controller.toastRequested.connect(toasts.append)

    controller.connectLogin(data["ssh"].id)  # ssh works
    rdp = vault.save_credential(data["server"].id, CredentialDraft(kind="rdp", label="系统登录账号", username="a", password="p"))
    controller.connectLogin(rdp.id)

    assert "已发起连接" in toasts[0]  # 成功的那次
    assert toasts[-1] == "该服务器没有保存 IP 地址。"


# ---------------------------------------------------------------------------
# generator bridge
# ---------------------------------------------------------------------------


def test_generator_slots_share_the_pure_module() -> None:
    controller = VaultController(Path("unused-vault.sqlcipher"), tray_available=False)

    password = controller.generate("digits+letters", 16)
    assert len(password) == 16
    assert password.isalnum()

    assert controller.strengthFor("digits", 6) == 1
    assert controller.strengthFor("digits+letters+symbols", 12) == 3
    assert controller.strengthFor("digits+letters+symbols", 16) == 4
    assert controller.strengthLabels == ["弱", "中", "强", "极强"]
    assert [info["key"] for info in controller.charsets] == ["digits", "letters", "symbols"]

    # An invalid mode falls back instead of raising through the bridge.
    assert len(controller.generate("bogus", 12)) == 12


# ---------------------------------------------------------------------------
# export and rekey
# ---------------------------------------------------------------------------


def test_export_vault_writes_the_workbook(application: QApplication, vault: VaultRepository, tmp_path: Path) -> None:
    from openpyxl import load_workbook

    data = make_data(vault)
    controller = VaultController(vault.path, tray_available=False)

    locked_result = controller.exportVault(str(tmp_path / "a.xlsx"))
    assert locked_result["ok"] is False and "解锁" in locked_result["error"]

    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True
    target = tmp_path / "export.xlsx"
    result = controller.exportVault(str(target))
    assert result["ok"] is True and result["count"] == 4

    sheet = load_workbook(target).active
    assert sheet.max_row == 5  # header + 4 credentials（应用在前，服务器在后）
    assert sheet.cell(row=2, column=4).value == "主账号"  # 阿里云的凭据排在前
    assert sheet.cell(row=3, column=4).value == "系统登录账号"
    assert sheet.cell(row=3, column=8).value == "MySQL,生产环境"


def test_rekey_vault_flow(application: QApplication, vault: VaultRepository) -> None:
    controller = VaultController(vault.path, tray_available=False)
    assert controller.attemptUnlock(MASTER_PASSWORD)["ok"] is True

    mismatch = controller.rekeyVault("wrong", "brand-new-pass", "different")
    assert mismatch["ok"] is False and mismatch["error"] == "两次输入的新密码不一致。"

    wrong = controller.rekeyVault("wrong", "brand-new-pass", "brand-new-pass")
    assert wrong["ok"] is False and wrong["error"] == "当前主密码不正确。"

    good = controller.rekeyVault(MASTER_PASSWORD, "brand-new-pass", "brand-new-pass")
    assert good["ok"] is True

    vault.lock()
    with pytest.raises(ValueError):
        vault.unlock(MASTER_PASSWORD)
    vault.unlock("brand-new-pass")
