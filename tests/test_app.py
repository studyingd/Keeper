import os
import signal
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QListWidgetItem, QPushButton, QToolButton

from password_manager.app import (
    EXPORT_COLUMNS,
    GENERATED_PASSWORD_LENGTH,
    PASSWORD_CHARSETS,
    THROTTLE_FILE_NAME,
    CredentialDialog,
    EntryDialog,
    PasswordGenerator,
    RekeyDialog,
    STYLESHEET,
    UnlockDialog,
    VaultWindow,
    _allow_console_interrupt,
    acquire_single_instance,
    application_icon,
    collect_export_rows,
    generate_password,
    load_unlock_throttle,
    save_unlock_throttle,
    single_instance_name,
    unlock_failure_delay_ms,
    write_export_xlsx,
)
import password_manager.app as app_module
from password_manager.models import CredentialDraft, EntryDraft
from password_manager.vault.repository import VaultRepository


@pytest.fixture(scope="session")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def keep_tests_off_the_real_pasteboard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route clipboard assertions through Qt instead of the real pasteboard.

    On macOS copy_secret shells out to osascript to mark the item concealed,
    which writes the system pasteboard; under the offscreen Qt platform the
    tests can neither observe nor undo that, so they take the Qt fallback.
    """
    monkeypatch.setattr(app_module, "set_concealed_clipboard", lambda value: False)


@pytest.fixture
def vault(tmp_path: Path) -> VaultRepository:
    repository = VaultRepository(tmp_path / "vault.db")
    repository.initialize("correct horse battery staple")
    yield repository
    repository.lock()



def test_password_generator_uses_requested_character_sets() -> None:
    for mode, characters in PASSWORD_CHARSETS.items():
        password = generate_password(mode, 32)
        assert len(password) == 32
        assert set(password) <= set(characters)

    combined = generate_password("digits+letters", 24)
    assert set(combined) <= set(PASSWORD_CHARSETS["digits"] + PASSWORD_CHARSETS["letters"])

    with pytest.raises(ValueError):
        generate_password("unknown", 8)
    with pytest.raises(ValueError):
        generate_password("digits", 0)
    with pytest.raises(ValueError):
        generate_password("digits", 129)
    with pytest.raises(ValueError):
        generate_password("", 8)


def test_password_strength_maps_entropy_onto_four_levels() -> None:
    from password_manager.generator import STRENGTH_THRESHOLDS, entropy_bits, strength_level

    assert STRENGTH_THRESHOLDS == (36.0, 60.0, 90.0)
    assert strength_level(0) == 0
    assert strength_level(entropy_bits(6, ["digits"])) == 1
    assert strength_level(entropy_bits(12, ["digits"])) == 2
    assert strength_level(entropy_bits(12, ["digits", "letters", "symbols"])) == 3
    assert strength_level(entropy_bits(16, ["digits", "letters", "symbols"])) == 4
    # A long digits-only password can still reach the top: entropy grows with length.
    assert strength_level(entropy_bits(128, ["digits"])) == 4


def test_credential_dialog_shares_the_home_generator_controls(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    dialog = CredentialDialog(None, parent)
    dialog.name.setText("Generated password")
    dialog.username.setText("admin")
    dialog.extra.setText("https://example.test")

    # The dialog embeds the same charset toggles, length slider and strength meter.
    assert dialog.char_toggles.selected_keys() == ["digits", "letters", "symbols"]
    assert dialog.length_slider.value() == GENERATED_PASSWORD_LENGTH == 12

    dialog.length_slider.setValue(16)
    dialog.char_toggles.button("letters").click()
    dialog.char_toggles.button("symbols").click()
    assert dialog.char_toggles.selected_keys() == ["digits"]

    dialog.generate_password_button.click()

    password = dialog.password.text()
    assert len(password) == 16
    assert password.isdigit()
    assert dialog.password.echoMode() == dialog.password.EchoMode.Normal
    assert dialog.username.text() == "admin"
    assert dialog.draft().password == password
    dialog.close()
    parent.close()


def test_server_dialog_contains_only_server_fields(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    dialog = EntryDialog("server", None, parent)

    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert dialog.draft() == EntryDraft(kind="server", name="", address="")

    dialog.close()
    parent.close()


def test_entry_dialog_offers_tag_input(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    for kind in ("application", "server"):
        dialog = EntryDialog(kind, None, parent)
        assert hasattr(dialog, "tag_edit")
        assert not hasattr(dialog, "notes")
        assert dialog.tag_edit.tags() == []
        dialog.close()
    parent.close()


def test_entry_dialog_type_cards_switch_fields_and_kind(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    dialog = EntryDialog("server", None, parent)

    assert dialog.draft().kind == "server"
    assert dialog.address_label.text() == "服务器 IP"
    assert dialog.save.text() == "保存服务器"

    dialog.type_cards["application"].click()

    assert dialog.draft().kind == "application"
    assert dialog.address_label.text() == "网站地址（可选）"
    assert dialog.name_label.text() == "应用名称"
    assert dialog.save.text() == "保存应用"
    dialog.close()
    parent.close()


def test_entry_dialog_collects_tags_from_input_and_suggestions(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    dialog = EntryDialog("server", None, parent)

    suggestion = next(
        button
        for button in dialog.tag_edit.findChildren(QToolButton)
        if button.objectName() == "tagSuggest" and button.text() == "MySQL"
    )
    suggestion.click()
    dialog.tag_edit.input.setText("生产环境, 备份")
    dialog.tag_edit.commit()

    assert dialog.tag_edit.tags() == ["MySQL", "生产环境", "备份"]
    assert dialog.draft().tags == ["MySQL", "生产环境", "备份"]

    # Tags survive a type switch; suggestions change to the other kind's set.
    dialog.type_cards["application"].click()
    assert dialog.draft().tags == ["MySQL", "生产环境", "备份"]
    assert dialog.draft().kind == "application"
    dialog.close()
    parent.close()


def test_credential_dialog_uses_custom_project_fields(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    dialog = CredentialDialog(None, parent)
    dialog.name.setText("宝塔后台")
    dialog.username.setText("admin")
    dialog.password.setText("secret")
    dialog.extra.setText("https://panel.example.test")

    draft = dialog.draft()

    assert dialog.draft() == CredentialDraft(
        kind="custom",
        label="宝塔后台",
        username="admin",
        password="secret",
        extra="https://panel.example.test",
    )
    assert "项目名称" in [item.text() for item in dialog.findChildren(QLabel)]

    dialog.close()
    parent.close()



def test_homepage_password_generator_displays_generated_password(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    generator = window.home_password_generator

    assert generator.length_slider.value() == GENERATED_PASSWORD_LENGTH
    assert not window.home_copy_password.isEnabled()

    generator.toggles.button("letters").click()
    generator.toggles.button("symbols").click()
    generator.length_slider.setValue(16)
    generator.generate_password()

    password = generator.result.text()
    assert len(password) == 16
    assert password.isdigit()
    assert window.home_copy_password.isEnabled()
    window.close()


def test_homepage_generator_leaves_the_last_charset_on(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    toggles = window.home_password_generator.toggles

    toggles.button("letters").click()
    toggles.button("symbols").click()

    # Only digits remain: it stays checked and is disabled so the pool is never empty.
    assert toggles.selected_keys() == ["digits"]
    assert not toggles.button("digits").isEnabled()
    window.close()


def test_homepage_generator_slider_bounds_drive_strength(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    generator = window.home_password_generator

    generator.length_slider.setValue(128)
    generator.generate_password()
    assert len(generator.result.text()) == 128
    assert generator.strength_label.text() == "极强"

    generator.length_slider.setValue(4)
    generator.generate_password()
    assert len(generator.result.text()) == 4
    assert generator.strength_label.text() == "弱"
    window.close()


def test_dark_surfaces_style_scroll_viewport_and_detail_pages(application: QApplication) -> None:
    assert "QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }" in STYLESHEET
    assert "QWidget#detailPage { background: transparent; }" in STYLESHEET
    assert "QLabel { background: transparent; }" in STYLESHEET
    assert "QWidget#lockedPage" in STYLESHEET

    window = VaultWindow(Path("unused-test-vault.db"))
    assert window.pages.objectName() == "pages"
    assert window.empty.objectName() == "emptyPage"
    assert window.locked.objectName() == "lockedPage"
    window.close()


def test_home_navigation_returns_from_entry_detail(application: QApplication, vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    window.render_entry(entry)

    assert window.pages.currentWidget() is window.detail_scroll
    window.show_home()

    assert window.selected_entry_id is None
    assert window.entries.currentItem() is None
    assert window.pages.currentWidget() is window.empty
    window.home_password_generator.generate_password()
    assert len(window.home_password_generator.result.text()) == 12
    window.close()


def test_credential_card_shows_visit_only_for_http_url(application: QApplication, vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    with_url = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="Portal", extra="https://portal.example.test"))
    without_url = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="SSH", extra="ssh://host.example.test"))
    window = VaultWindow(vault.path)
    window.repository = vault

    with_url_card = window.credential_card(entry, with_url)
    without_url_card = window.credential_card(entry, without_url)
    with_url_buttons = [item.text() for item in with_url_card.findChildren(QPushButton)]
    without_url_buttons = [item.text() for item in without_url_card.findChildren(QPushButton)]

    assert "↗ 访问网站" in with_url_buttons
    assert "↗ 访问网站" not in without_url_buttons
    window.close()


def test_credential_card_move_buttons_respect_boundaries_and_reorder(application: QApplication, vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    first = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="SSH 登录", password="a"))
    second = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="MySQL", password="b"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    first_card = window.credential_card(entry, first, index=0, total=2)
    second_card = window.credential_card(entry, second, index=1, total=2)

    def hover_actions(card) -> dict[str, QToolButton]:
        return {item.objectName(): item for item in card.findChildren(QToolButton) if item.objectName() in {"moveUp", "moveDown"}}

    first_buttons = hover_actions(first_card)
    second_buttons = hover_actions(second_card)

    assert not first_buttons["moveUp"].isEnabled() and first_buttons["moveDown"].isEnabled()
    assert second_buttons["moveUp"].isEnabled() and not second_buttons["moveDown"].isEnabled()

    first_buttons["moveDown"].click()
    assert [credential.label for credential in vault.list_credentials(entry.id)] == ["MySQL", "SSH 登录"]
    window.close()


def test_credential_card_can_reveal_and_hide_the_password(application: QApplication, vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    credential = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="MySQL", password="hunter2"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    card = window.credential_card(entry, credential)
    dots = card.findChild(QLabel, "pwDots")
    eye = card.findChild(QToolButton, "pwToggle")

    assert "hunter2" not in dots.text() and "•" in dots.text()
    eye.click()
    assert dots.text() == "hunter2"
    eye.click()
    assert "hunter2" not in dots.text()
    window.close()


def test_moving_credential_keeps_the_card_in_view(application: QApplication, vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    for number in range(3):
        vault.save_credential(entry.id, CredentialDraft(kind="custom", label=f"项目 {number}", password="p"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    window.render_entry(entry)

    scrolled: list = []
    window.detail_scroll.ensureWidgetVisible = lambda widget, *args: scrolled.append(widget)

    moved = vault.list_credentials(entry.id)[2]
    window.move_credential(entry, moved, "up")
    application.processEvents()

    assert len(scrolled) == 1
    assert "项目 2" in [item.text() for item in scrolled[0].findChildren(QLabel)]
    window.close()


def test_login_dialog_offers_platform_choice_and_kind(application: QApplication) -> None:
    parent = VaultWindow(Path("unused-test-vault.db"))
    dialog = CredentialDialog(None, parent, login_mode=True)

    assert dialog.login_mode
    assert dialog.ssh_radio.isChecked() and not dialog.rdp_radio.isChecked()
    # System-login dialog: no project name / description rows, platform first.
    row_labels = [item.text() for item in dialog.findChildren(QLabel)]
    assert "项目名称" not in row_labels
    assert "说明 / 网站地址（可选）" not in row_labels
    assert row_labels.index("登录平台") < row_labels.index("登录账号")
    # New dialog pre-fills the typical account for the selected platform.
    assert dialog.username.text() == "root"
    dialog.rdp_radio.setChecked(True)
    assert dialog.username.text() == "administrator"
    dialog.ssh_radio.setChecked(True)
    assert dialog.username.text() == "root"
    # Custom input survives platform switches.
    dialog.username.setText("deploy")
    dialog.rdp_radio.setChecked(True)
    assert dialog.username.text() == "deploy"
    # The credential label is a fixed default, independent of the account.
    draft = dialog.draft()
    assert draft.kind == "rdp" and draft.label == "系统登录账号" and draft.extra == ""
    dialog.close()

    plain = CredentialDialog(None, parent)
    assert not plain.login_mode
    assert not hasattr(plain, "rdp_radio")
    assert plain.draft().kind == "custom"
    plain.close()
    parent.close()


def test_editing_login_credential_reenters_login_mode(application: QApplication, vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    credential = vault.save_credential(entry.id, CredentialDraft(kind="rdp", label="RDP 登录", username="itadmin", password="p"))
    parent = VaultWindow(vault.path, tray_available=False)
    parent.repository = vault

    dialog = CredentialDialog(credential, parent)

    assert dialog.login_mode
    assert dialog.rdp_radio.isChecked()
    # A saved custom account is never overwritten by the platform default.
    assert dialog.username.text() == "itadmin"
    dialog.ssh_radio.setChecked(True)
    assert dialog.draft().kind == "ssh"
    assert dialog.username.text() == "itadmin"
    dialog.close()
    parent.close()


def test_server_page_offers_system_login_button(application: QApplication, vault: VaultRepository) -> None:
    server = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    app_entry = vault.save_entry(EntryDraft(kind="application", name="阿里云"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    window.render_entry(server)
    server_buttons = [item.text() for item in window.detail_scroll.widget().findChildren(QPushButton)]
    assert "+ 系统登录" in server_buttons

    window.render_entry(app_entry)
    app_buttons = [item.text() for item in window.detail_scroll.widget().findChildren(QPushButton)]
    assert "+ 系统登录" not in app_buttons
    window.close()


def test_credential_card_shows_connect_button_only_for_server_logins(application: QApplication, vault: VaultRepository) -> None:
    server = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    ssh = vault.save_credential(server.id, CredentialDraft(kind="ssh", label="SSH 登录", username="root", password="p"))
    rdp = vault.save_credential(server.id, CredentialDraft(kind="rdp", label="RDP 登录", username="administrator", password="p"))
    custom = vault.save_credential(server.id, CredentialDraft(kind="custom", label="MySQL", password="p"))
    app_entry = vault.save_entry(EntryDraft(kind="application", name="阿里云"))
    stray = vault.save_credential(app_entry.id, CredentialDraft(kind="ssh", label=" stray ", password="p"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    def button_texts(entry, credential) -> list[str]:
        card = window.credential_card(entry, credential)
        return [item.text() for item in card.findChildren(QPushButton)]

    assert "SSH 连接" in button_texts(server, ssh)
    assert "RDP 连接" in button_texts(server, rdp)
    assert not any(text.endswith("连接") for text in button_texts(server, custom))
    assert not any(text.endswith("连接") for text in button_texts(app_entry, stray))
    window.close()


def test_connect_credential_launches_ssh_and_copies_password(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    import password_manager.app as app_module

    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    credential = vault.save_credential(entry.id, CredentialDraft(kind="ssh", label="SSH 登录", username="root", password="sekrit"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    calls: list[tuple] = []
    monkeypatch.setattr(app_module, "connect_ssh", lambda host, username, password: calls.append((host, username, password)))

    window.connect_credential(entry, credential)

    assert calls == [("192.168.1.101", "root", "sekrit")]
    assert QApplication.clipboard().text() == "sekrit"
    window.close()


def test_copy_secret_prefers_the_concealed_pasteboard(application: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    copied: list[str] = []

    def concealed(text: str) -> bool:
        copied.append(text)
        return True

    monkeypatch.setattr(app_module, "set_concealed_clipboard", concealed)
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    QApplication.clipboard().clear()

    window.copy_secret("s3cret", "已复制")

    assert copied == ["s3cret"]
    # The marker went straight to the pasteboard, so Qt is left untouched.
    assert QApplication.clipboard().text() == ""
    window.close()


def test_connect_credential_shows_warning_when_connection_fails(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    import password_manager.app as app_module

    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    credential = vault.save_credential(entry.id, CredentialDraft(kind="rdp", label="RDP 登录", password="p"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    warnings: list[str] = []

    class fake_box:
        @staticmethod
        def warning(_parent, _title, message):
            warnings.append(message)

    def boom(host, username, password):
        raise ValueError("该服务器没有保存 IP 地址。")

    monkeypatch.setattr(app_module, "connect_rdp", boom)
    monkeypatch.setattr(app_module, "QMessageBox", fake_box)

    window.connect_credential(entry, credential)

    assert warnings == ["该服务器没有保存 IP 地址。"]
    window.close()





def test_entry_selection_handles_lock_between_check_and_read(application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    item = QListWidgetItem("应用\nPortal")
    item.setData(Qt.ItemDataRole.UserRole, 1)

    def locked_get_entry(_entry_id: int):
        raise RuntimeError("保险库已锁定。")

    monkeypatch.setattr(vault, "get_entry", locked_get_entry)
    window.select_entry(item, None)

    assert window.selected_entry_id is None
    assert window.pages.currentWidget() is window.empty
    window.close()

    repository = VaultRepository(Path("unused-test-vault.db"))
    parent = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    dialog = UnlockDialog(repository, parent)

    assert "退出 Keeper" in [item.text() for item in dialog.findChildren(QPushButton)]
    dialog.close()
    parent.close()


def test_locked_vault_ignores_entry_selection_signal(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    item = QListWidgetItem("应用\nPortal")
    item.setData(Qt.ItemDataRole.UserRole, 1)

    window.select_entry(item, None)

    assert window.selected_entry_id is None
    assert window.pages.currentWidget() is window.empty
    window.close()


def test_sidebar_groups_entries_by_kind(application: QApplication, vault: VaultRepository) -> None:
    vault.save_entry(EntryDraft(kind="application", name="阿里云"))
    unnamed = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    vault.save_entry(EntryDraft(kind="server", name="生产机", address="10.0.0.7", tags=["数据库"]))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    window.refresh_entries()

    # Two group headers plus three asset rows.
    assert window.entries.count() == 5
    headers = []
    for index in range(5):
        widget = window.entries.itemWidget(window.entries.item(index))
        headers.append(widget.text() if widget.objectName() == "groupLabel" else None)
    assert headers == ["服务器", None, None, "应用", None]

    def row_texts(index: int) -> list[str]:
        return [item.text() for item in window.entries.itemWidget(window.entries.item(index)).findChildren(QLabel)]

    assert "192.168.1.101" in row_texts(1)  # unnamed server falls back to the IP
    assert "生产机" in row_texts(2) and "数据库" in row_texts(2)  # tag surfaces in the sub line
    assert "阿里云" in row_texts(4)
    assert unnamed.name == "192.168.1.101"
    window.close()


def test_sidebar_search_finds_servers_by_ip_and_tag(application: QApplication, vault: VaultRepository) -> None:
    vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    vault.save_entry(EntryDraft(kind="server", name="生产机", address="10.0.0.7", tags=["MySQL"]))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    def asset_rows() -> int:
        return sum(
            1
            for index in range(window.entries.count())
            if window.entries.item(index).data(Qt.ItemDataRole.UserRole) is not None
        )

    window.search.setText("192.168.1")
    window.refresh_entries()
    assert asset_rows() == 1

    window.search.setText("mysql")
    window.refresh_entries()
    assert asset_rows() == 1

    window.search.setText("redis")
    window.refresh_entries()
    assert asset_rows() == 0
    window.close()


def test_sidebar_filter_chips_narrow_the_list(application: QApplication, vault: VaultRepository) -> None:
    vault.save_entry(EntryDraft(kind="application", name="阿里云"))
    vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    window.refresh_entries()
    assert window.entries.count() == 4  # 服务器 header+row, 应用 header+row

    window._set_filter("server")
    assert window.entries.count() == 2  # header + row

    window._set_filter("application")
    assert window.entries.count() == 2

    window._set_filter("all")
    assert window.entries.count() == 4
    window.close()


def test_tray_menu_excludes_manual_lock_action(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=True)
    assert window.tray_icon is not None

    menu = window.tray_icon.contextMenu()
    assert menu is not None
    action_texts = [action.text() for action in menu.actions()]
    assert "打开 Keeper" in action_texts
    assert "锁定并显示" not in action_texts
    assert "完全退出" in action_texts
    window.quit_application()


def test_hide_to_tray_stays_silent(application: QApplication, vault: VaultRepository) -> None:
    window = VaultWindow(vault.path, tray_available=True)
    window.repository = vault
    balloon_calls: list[tuple] = []
    window.tray_icon.showMessage = lambda *args, **kwargs: balloon_calls.append(args)

    window.hide_to_tray()

    assert balloon_calls == []
    assert not window.isVisible()
    window.quit_application()


def test_application_icon_loads_from_packaged_assets(application: QApplication) -> None:
    icon = application_icon()
    assert not icon.isNull()


def test_hidden_window_auto_locks_and_clears_sensitive_ui(application: QApplication, vault: VaultRepository) -> None:
    window = VaultWindow(vault.path, tray_available=True, auto_lock_ms=1)
    window.repository = vault
    window.show()

    window.hide_to_tray()
    assert not window.isVisible()
    assert window.repository.unlocked
    assert window.auto_lock_timer.isActive()

    window.auto_lock()

    assert not window.repository.unlocked
    assert window.selected_entry_id is None
    assert window.entries.count() == 0
    assert window.pages.currentWidget() is window.locked
    window.quit_application()


def test_close_without_tray_locks_and_exits(application: QApplication, vault: VaultRepository) -> None:
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    window.close()

    assert not window.repository.unlocked


def test_unlock_failure_delay_grows_from_half_second_to_eight_second_cap() -> None:
    assert unlock_failure_delay_ms(0) == 0
    assert unlock_failure_delay_ms(1) == 500
    assert unlock_failure_delay_ms(2) == 1_000
    assert unlock_failure_delay_ms(3) == 2_000
    assert unlock_failure_delay_ms(4) == 4_000
    assert unlock_failure_delay_ms(5) == 8_000
    assert unlock_failure_delay_ms(9) == 8_000


def test_failed_unlock_starts_throttle_and_blocks_retry(application: QApplication, vault: VaultRepository) -> None:
    parent = VaultWindow(vault.path, tray_available=False)
    dialog = UnlockDialog(vault, parent)
    dialog.password.setText("wrong-password")

    dialog._submit()

    assert dialog.failure_count == 1
    assert dialog.throttle_timer.isActive()
    assert not dialog.submit.isEnabled()
    assert not dialog.password.isEnabled()
    assert "重试" in dialog.error.text()

    dialog._submit()
    assert dialog.failure_count == 1

    dialog._throttle_remaining_ms = 100
    dialog._tick_throttle()

    assert not dialog.throttle_timer.isActive()
    assert dialog.submit.isEnabled()
    assert dialog.password.isEnabled()

    dialog.password.setText("correct horse battery staple")
    dialog._submit()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert vault.unlocked
    parent.close()


def test_failed_unlock_delays_increase_with_consecutive_failures(application: QApplication, vault: VaultRepository) -> None:
    parent = VaultWindow(vault.path, tray_available=False)
    dialog = UnlockDialog(vault, parent)
    dialog.password.setText("wrong-password")

    dialog._submit()
    assert dialog.failure_count == 1
    first_delay = dialog._throttle_remaining_ms
    assert first_delay == unlock_failure_delay_ms(1)

    dialog._throttle_remaining_ms = 100
    dialog._tick_throttle()
    dialog._submit()

    assert dialog.failure_count == 2
    assert dialog._throttle_remaining_ms == first_delay * 2 == unlock_failure_delay_ms(2)
    parent.close()


def test_unlock_throttle_carries_into_new_dialog(application: QApplication, vault: VaultRepository) -> None:
    parent = VaultWindow(vault.path, tray_available=False)

    still_throttled = UnlockDialog(vault, parent, failure_count=3, throttled_until=time.monotonic() + 2.0)
    assert still_throttled.throttle_timer.isActive()
    assert not still_throttled.submit.isEnabled()
    assert not still_throttled.password.isEnabled()

    # A carried-over countdown has no original failure message; once it expires
    # the error label must disappear instead of showing empty text.
    still_throttled._throttle_remaining_ms = 100
    still_throttled._tick_throttle()
    assert not still_throttled.error.isVisible()
    still_throttled.close()

    expired = UnlockDialog(vault, parent, failure_count=3, throttled_until=time.monotonic() - 1.0)
    assert not expired.throttle_timer.isActive()
    assert expired.submit.isEnabled()
    assert expired.failure_count == 3
    expired.close()
    parent.close()


def test_open_unlock_resets_failure_state_after_success_and_keeps_it_after_failure(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    import password_manager.app as app_module

    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    window.unlock_failure_count = 3
    window.unlock_throttled_until = time.monotonic() + 5.0

    class FakeDialog:
        def __init__(self, repository, parent, *, failure_count, throttled_until):
            self.failure_count = failure_count
            self.throttled_until = throttled_until

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "UnlockDialog", FakeDialog)
    assert window.open_unlock()
    assert window.unlock_failure_count == 0
    assert window.unlock_throttled_until == 0.0

    class FailedDialog(FakeDialog):
        def exec(self):
            self.failure_count += 1
            self.throttled_until = time.monotonic() + 0.5
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "UnlockDialog", FailedDialog)
    assert not window.open_unlock()
    assert window.unlock_failure_count == 1
    assert window.unlock_throttled_until > time.monotonic()
    window.close()


def test_export_rows_cover_applications_and_servers(vault: VaultRepository) -> None:
    app_entry = vault.save_entry(EntryDraft(kind="application", name="Portal", address="https://portal.example.test", tags=["云平台"]))
    server_entry = vault.save_entry(EntryDraft(kind="server", name="数据库", address="10.0.0.5"))
    vault.save_credential(
        app_entry.id,
        CredentialDraft(kind="custom", label="网站后台", username="admin", password="p@ssw0rd", extra="https://panel.example.test"),
    )
    vault.save_credential(server_entry.id, CredentialDraft(kind="custom", label="MySQL", username="root", password="hunter2"))

    rows = collect_export_rows(vault)

    assert rows == [
        ("应用", "Portal", "https://portal.example.test", "网站后台", "admin", "p@ssw0rd", "https://panel.example.test", "云平台"),
        ("服务器", "数据库", "10.0.0.5", "MySQL", "root", "hunter2", "", ""),
    ]


def test_write_export_xlsx_contains_headers_rows_and_filter(tmp_path: Path, vault: VaultRepository) -> None:
    from openpyxl import load_workbook

    entry = vault.save_entry(EntryDraft(kind="server", name="数据库", address="10.0.0.5"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="MySQL", username="root", password="hunter2"))
    rows = collect_export_rows(vault)
    target = tmp_path / "export.xlsx"

    assert write_export_xlsx(target, rows) == 1

    sheet = load_workbook(target).active
    assert [cell.value for cell in sheet[1]] == list(EXPORT_COLUMNS)
    actual_rows = [[cell.value if cell.value is not None else "" for cell in row] for row in sheet.iter_rows(min_row=2)]
    assert actual_rows == [list(row) for row in rows]
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == sheet.dimensions


def test_sidebar_offers_export_button(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)

    assert window.export_button.text() == "导出 Excel"
    assert window.export_button in window.findChildren(QPushButton)
    window.close()


def test_console_interrupt_handler_rejects_open_dialogs(application: QApplication) -> None:
    original = signal.getsignal(signal.SIGINT)
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    dialog = UnlockDialog(window.repository, window)
    dialog.show()

    try:
        _allow_console_interrupt(application, window)
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler) and handler is not original

        handler(signal.SIGINT, None)
        application.processEvents()

        assert dialog.result() == QDialog.DialogCode.Rejected
        assert not dialog.isVisible()
    finally:
        signal.signal(signal.SIGINT, original)
        window.close()


def test_enter_saves_entry_dialogs_instead_of_cancelling(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)

    server_dialog = EntryDialog("server", None, window)
    server_dialog.show()
    server_dialog.address.setText("10.0.0.5")
    QTest.keyClick(server_dialog.address, Qt.Key_Return)
    assert server_dialog.result() == QDialog.DialogCode.Accepted

    app_dialog = EntryDialog("application", None, window)
    app_dialog.show()
    app_dialog.name.setText("Portal")
    QTest.keyClick(app_dialog.name, Qt.Key_Return)
    assert app_dialog.result() == QDialog.DialogCode.Accepted

    invalid_dialog = EntryDialog("application", None, window)
    invalid_dialog.show()
    QTest.keyClick(invalid_dialog.name, Qt.Key_Return)
    assert invalid_dialog.result() != QDialog.DialogCode.Accepted
    assert invalid_dialog.isVisible()
    assert invalid_dialog.error.isVisible()

    server_dialog.close(); app_dialog.close(); invalid_dialog.close()
    window.close()


def test_enter_saves_credential_dialog(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    dialog = CredentialDialog(None, window)
    dialog.show()
    dialog.name.setText("MySQL")
    dialog.username.setText("root")
    dialog.password.setText("hunter2")

    QTest.keyClick(dialog.password, Qt.Key_Return)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.draft().password == "hunter2"
    dialog.close()
    window.close()


def test_enter_in_unlock_dialog_submits_exactly_once(application: QApplication, vault: VaultRepository) -> None:
    window = VaultWindow(vault.path, tray_available=False)

    wrong = UnlockDialog(vault, window)
    wrong.show()
    wrong.password.setText("wrong-password")
    QTest.keyClick(wrong.password, Qt.Key_Return)

    assert wrong.failure_count == 1  # would be 2 if the default button double-fired
    assert wrong.throttle_timer.isActive()
    assert wrong.result() != QDialog.DialogCode.Accepted
    wrong.close()

    correct = UnlockDialog(vault, window)
    correct.show()
    correct.password.setText("correct horse battery staple")
    QTest.keyClick(correct.password, Qt.Key_Return)

    assert correct.result() == QDialog.DialogCode.Accepted
    assert vault.unlocked
    correct.close()
    window.close()


def test_enter_in_create_vault_dialog_creates_vault(application: QApplication, tmp_path: Path) -> None:
    repository = VaultRepository(tmp_path / "new-vault.sqlcipher")
    window = VaultWindow(repository.path, tray_available=False)
    dialog = UnlockDialog(repository, window)
    dialog.show()

    dialog.password.setText("new-master-password")
    dialog.confirm.setText("new-master-password")
    QTest.keyClick(dialog.confirm, Qt.Key_Return)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert repository.unlocked
    dialog.close()
    window.close()
    repository.lock()


def test_create_vault_shows_disk_errors_inside_dialog(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = VaultRepository(tmp_path / "vault.sqlcipher")
    window = VaultWindow(repository.path, tray_available=False)
    dialog = UnlockDialog(repository, window)
    dialog.show()
    dialog.password.setText("pw")
    dialog.confirm.setText("pw")

    def broken_initialize(_password: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(repository, "initialize", broken_initialize)
    dialog._submit()

    assert dialog.isVisible()
    assert "操作失败" in dialog.error.text() and "disk full" in dialog.error.text()
    assert not repository.unlocked
    dialog.close()
    window.close()


def test_server_dialog_rejects_invalid_ip_inline(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)
    dialog = EntryDialog("server", None, window)
    dialog.show()

    dialog.address.setText("db.internal")
    QTest.keyClick(dialog.address, Qt.Key_Return)

    assert dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "IPv4 或 IPv6" in dialog.error.text()

    dialog.address.setText("10.0.0.1")
    QTest.keyClick(dialog.address, Qt.Key_Return)

    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()
    window.close()


def test_lock_button_keeps_the_window_on_the_lock_screen(
    application: QApplication, vault: VaultRepository
) -> None:
    """Locking must never leave the process running with nothing on screen."""
    for tray_available in (True, False):
        vault.unlock("correct horse battery staple")
        window = VaultWindow(vault.path, tray_available=tray_available)
        window.repository = vault
        window.show()
        window.search.setText("10.0.0")

        window.lock()

        assert not window.repository.unlocked
        assert window.isVisible()
        assert not window._allow_exit
        assert window.pages.currentWidget() is window.locked
        assert window.entries.count() == 0
        assert window.search.text() == ""  # no stale filter on the next unlock
        assert window.statusBar().currentMessage() == "保险库已锁定。"
        window.close()
        window.deleteLater()


def test_existing_vault_starts_on_the_lock_screen(
    application: QApplication, vault: VaultRepository
) -> None:
    vault.save_entry(EntryDraft(kind="application", name="Portal"))
    vault.lock()

    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    assert window.pages.currentWidget() is window.locked
    texts = [item.text() for item in window.locked.findChildren(QLabel)]
    assert "保险库已锁定" in texts
    assert any("没丢" in item and "加密文件" in item for item in texts)
    assert "解锁保险库" in [item.text() for item in window.locked.findChildren(QPushButton)]
    window.close()


def test_a_vault_that_does_not_exist_yet_starts_on_the_home_page(
    application: QApplication, tmp_path: Path
) -> None:
    window = VaultWindow(tmp_path / "fresh.sqlcipher", tray_available=False)

    assert not window.repository.exists
    assert window.pages.currentWidget() is window.empty
    window.close()


def test_home_navigation_while_locked_stays_on_the_lock_screen(
    application: QApplication, vault: VaultRepository
) -> None:
    vault.lock()
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    window.show_home()

    assert window.pages.currentWidget() is window.locked
    window.close()


def test_lock_screen_button_loads_the_saved_entries_again(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault.save_entry(EntryDraft(kind="application", name="Portal"))
    vault.save_entry(EntryDraft(kind="server", name="生产机", address="10.0.0.7"))
    vault.lock()
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault

    def unlock_vault() -> bool:
        vault.unlock("correct horse battery staple")
        return True

    monkeypatch.setattr(window, "open_unlock", unlock_vault)
    unlock_button = window.locked.findChildren(QPushButton)[0]

    unlock_button.click()

    assert vault.unlocked
    assert window.pages.currentWidget() is window.empty
    asset_rows = sum(
        1
        for index in range(window.entries.count())
        if window.entries.item(index).data(Qt.ItemDataRole.UserRole) is not None
    )
    assert asset_rows == 2
    assert "已解锁" in window.statusBar().currentMessage()
    window.close()


def test_lock_screen_button_keeps_the_lock_screen_when_unlock_is_cancelled(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault.lock()
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    monkeypatch.setattr(window, "open_unlock", lambda: False)

    window.locked.findChildren(QPushButton)[0].click()

    assert window.pages.currentWidget() is window.locked
    assert "锁定" in window.statusBar().currentMessage()
    window.close()


def test_adding_an_entry_while_locked_asks_for_the_master_password_first(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidebar's add buttons stay clickable on the lock screen."""
    vault.lock()
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    prompts: list[str] = []

    def refuse_unlock() -> bool:
        prompts.append("unlock")
        return False

    def refuse_dialog(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a locked vault must not open the entry dialog")

    monkeypatch.setattr(window, "open_unlock", refuse_unlock)
    monkeypatch.setattr(app_module, "EntryDialog", refuse_dialog)

    window.edit_entry("server")

    assert prompts == ["unlock"]
    assert not vault.unlocked
    window.close()


def test_credential_actions_while_locked_ask_for_the_master_password_first(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dialogs left open across an auto-lock must not save into a locked vault."""
    entry = vault.save_entry(EntryDraft(kind="application", name="ChatGPT"))
    credential = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="主账号"))
    vault.lock()
    window = VaultWindow(vault.path, tray_available=False)
    window.repository = vault
    prompts: list[str] = []
    monkeypatch.setattr(window, "open_unlock", lambda: prompts.append("unlock") or False)

    def refuse_dialog(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a locked vault must not open a credential dialog")

    monkeypatch.setattr(app_module, "CredentialDialog", refuse_dialog)
    window.edit_credential(entry, credential)
    window.delete_entry(entry)
    window.delete_credential(entry, credential)
    window.move_credential(entry, credential, "up")

    assert prompts == ["unlock"] * 4
    vault.unlock("correct horse battery staple")
    assert vault.get_entry(entry.id) is not None
    assert [item.id for item in vault.list_credentials(entry.id)] == [credential.id]
    window.close()


def test_reactivating_the_application_restores_a_hidden_window(
    application: QApplication, vault: VaultRepository
) -> None:
    """A Dock or taskbar click must not leave the process invisible."""
    window = VaultWindow(vault.path, tray_available=True)
    window.repository = vault
    window.show()
    window.hide_to_tray()
    assert not window.isVisible()

    window.restore_when_reactivated(Qt.ApplicationState.ApplicationActive)

    assert window.isVisible()
    assert window.repository.unlocked
    window.quit_application()


def test_reactivation_ignores_other_states_and_visible_windows(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = VaultWindow(vault.path, tray_available=True)
    window.repository = vault
    window.show()
    calls: list[str] = []
    monkeypatch.setattr(window, "restore_from_tray", lambda: calls.append("restore"))

    window.restore_when_reactivated(Qt.ApplicationState.ApplicationActive)
    assert calls == []  # already on screen

    window.hide_to_tray()
    window.restore_when_reactivated(Qt.ApplicationState.ApplicationInactive)
    assert calls == []
    window.quit_application()


def test_export_never_writes_formula_cells(tmp_path: Path, vault: VaultRepository) -> None:
    from openpyxl import load_workbook

    entry = vault.save_entry(EntryDraft(kind="application", name="=malicious"))
    vault.save_credential(
        entry.id,
        CredentialDraft(
            kind="custom",
            label="=cmd|'/C calc'!A0",
            username="+user",
            password='=HYPERLINK("http://evil.example")',
            extra="@note",
        ),
    )
    target = tmp_path / "export.xlsx"

    write_export_xlsx(target, collect_export_rows(vault))

    sheet = load_workbook(target).active
    data_rows = list(sheet.iter_rows(min_row=2))
    assert len(data_rows) == 1
    for cell in data_rows[0]:
        assert cell.data_type != "f"
    assert data_rows[0][1].value == "=malicious"
    assert data_rows[0][3].value == "=cmd|'/C calc'!A0"
    assert data_rows[0][5].value == '=HYPERLINK("http://evil.example")'


def test_sidebar_offers_a_change_master_password_button(application: QApplication) -> None:
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)

    assert window.rekey_button.text() == "修改主密码"
    assert window.rekey_button in window.findChildren(QPushButton)
    window.close()


def test_rekey_dialog_rejects_a_mismatched_confirmation(application: QApplication, vault: VaultRepository) -> None:
    parent = VaultWindow(vault.path, tray_available=False)
    dialog = RekeyDialog(vault, parent)
    dialog.current.setText("correct horse battery staple")
    dialog.new.setText("one")
    dialog.confirm.setText("two")

    dialog._save()

    assert dialog.error.text() == "两次输入的新密码不一致。"
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert vault.unlocked  # nothing was rewritten
    parent.close()


def test_rekey_dialog_reports_a_wrong_current_password(application: QApplication, vault: VaultRepository) -> None:
    parent = VaultWindow(vault.path, tray_available=False)
    dialog = RekeyDialog(vault, parent)
    dialog.current.setText("not the master password")
    dialog.new.setText("brand-new-pass")
    dialog.confirm.setText("brand-new-pass")

    dialog._save()

    assert dialog.error.text() == "当前主密码不正确。"
    assert dialog.result() != QDialog.DialogCode.Accepted
    parent.close()


def test_rekey_dialog_rewrites_the_vault(application: QApplication, vault: VaultRepository) -> None:
    parent = VaultWindow(vault.path, tray_available=False)
    dialog = RekeyDialog(vault, parent)
    dialog.current.setText("correct horse battery staple")
    dialog.new.setText("brand-new-pass")
    dialog.confirm.setText("brand-new-pass")

    dialog._save()

    assert dialog.result() == QDialog.DialogCode.Accepted
    path = vault.path
    vault.lock()
    reopened = VaultRepository(path)
    reopened.unlock("brand-new-pass")
    reopened.lock()
    parent.close()


def test_a_visible_window_locks_when_the_system_goes_idle(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "system_idle_seconds", lambda: 999.0)
    window = VaultWindow(vault.path, tray_available=False, auto_lock_ms=600_000)
    window.repository = vault
    window.show()
    assert window.isVisible() and window.repository.unlocked

    window.lock_when_idle()

    assert not window.repository.unlocked
    assert "10 分钟无操作自动锁定" in window.statusBar().currentMessage()
    assert not window.idle_poll_timer.isActive()
    window.close()


def test_a_visible_window_stays_unlocked_while_input_is_recent(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "system_idle_seconds", lambda: 5.0)
    window = VaultWindow(vault.path, tray_available=False, auto_lock_ms=600_000)
    window.repository = vault
    window.show()

    window.lock_when_idle()

    assert window.repository.unlocked
    window.close()


def test_the_idle_poll_leaves_a_hidden_window_to_its_own_timer(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hidden window locks on elapsed time even if the user is busy elsewhere."""
    monkeypatch.setattr(app_module, "system_idle_seconds", lambda: 999.0)
    window = VaultWindow(vault.path, tray_available=True, auto_lock_ms=600_000)
    window.repository = vault
    window.show()
    window.hide_to_tray()

    window.lock_when_idle()

    assert window.repository.unlocked
    assert window.auto_lock_timer.isActive()
    window.quit_application()


def test_the_idle_poll_needs_a_readable_platform_counter(
    application: QApplication, vault: VaultRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "system_idle_seconds", lambda: None)
    window = VaultWindow(vault.path, tray_available=False, auto_lock_ms=600_000)
    window.repository = vault
    window.show()

    window.lock_when_idle()

    assert window.repository.unlocked
    window.close()


def test_unlock_throttle_survives_a_new_window(application: QApplication, vault: VaultRepository) -> None:
    first = VaultWindow(vault.path, tray_available=False)
    save_unlock_throttle(3, time.monotonic() + 4.0, first.throttle_path)
    first.close()

    second = VaultWindow(vault.path, tray_available=False)

    assert second.unlock_failure_count == 3
    assert second.unlock_throttled_until > time.monotonic()
    assert load_unlock_throttle(second.throttle_path)[0] == 3
    second.close()


def test_a_clean_throttle_state_is_never_written_to_disk(application: QApplication, vault: VaultRepository) -> None:
    window = VaultWindow(vault.path, tray_available=False)

    save_unlock_throttle(0, time.monotonic(), window.throttle_path)

    assert not window.throttle_path.exists()
    window.close()


def test_a_successful_unlock_clears_the_persisted_throttle(application: QApplication, vault: VaultRepository) -> None:
    window = VaultWindow(vault.path, tray_available=False)
    save_unlock_throttle(3, time.monotonic() + 4.0, window.throttle_path)
    assert window.throttle_path.exists()

    save_unlock_throttle(0, 0.0, window.throttle_path)

    assert load_unlock_throttle(window.throttle_path) == (0, 0.0)
    window.close()


def test_a_corrupt_throttle_file_falls_back_to_no_delay(application: QApplication, vault: VaultRepository) -> None:
    path = vault.path.parent / THROTTLE_FILE_NAME
    path.write_text("{not json", encoding="utf-8")

    assert load_unlock_throttle(path) == (0, 0.0)


def test_a_second_instance_is_refused(application: QApplication, tmp_path: Path) -> None:
    vault_path = tmp_path / "vault.sqlcipher"
    name = single_instance_name(vault_path)
    first, taken = acquire_single_instance(vault_path)
    assert first is not None and taken is False

    try:
        second, taken = acquire_single_instance(vault_path)
        assert second is None and taken is True
    finally:
        first.close()
        QLocalServer.removeServer(name)


def test_a_socket_left_by_a_crash_is_reclaimed(application: QApplication, tmp_path: Path) -> None:
    vault_path = tmp_path / "vault.sqlcipher"
    name = single_instance_name(vault_path)
    crashed = QLocalServer()
    assert crashed.listen(name)
    crashed.close()  # a crash leaves the socket behind: nobody answers on it

    recovered, taken = acquire_single_instance(vault_path)

    try:
        assert recovered is not None and taken is False
    finally:
        if recovered is not None:
            recovered.close()
        QLocalServer.removeServer(name)


def test_console_interrupt_is_skipped_in_a_frozen_build(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    original = signal.getsignal(signal.SIGINT)
    window = VaultWindow(Path("unused-test-vault.db"), tray_available=False)

    _allow_console_interrupt(application, window)

    assert signal.getsignal(signal.SIGINT) is original
    window.close()
