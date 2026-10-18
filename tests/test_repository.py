import sqlite3
from pathlib import Path

import pytest

from password_manager.models import CredentialDraft, EntryDraft
from password_manager.vault.repository import SCHEMA_VERSION, SQLCIPHER_KDF_ITER, VaultRepository, validate_entry_draft

MASTER_PASSWORD = "correct horse battery staple"


@pytest.fixture
def vault(tmp_path: Path) -> VaultRepository:
    repository = VaultRepository(tmp_path / "vault.sqlcipher")
    repository.initialize(MASTER_PASSWORD)
    yield repository
    repository.lock()


def test_sqlcipher_engine_is_available(tmp_path: Path) -> None:
    vault = VaultRepository(tmp_path / "probe.sqlcipher")
    connection = vault._connect("test-password")
    try:
        version = connection.execute("PRAGMA cipher_version").fetchone()[0]
    finally:
        connection.close()

    assert version


def test_new_vault_uses_fixed_sqlcipher_kdf_profile(tmp_path: Path) -> None:
    vault = VaultRepository(tmp_path / "vault.sqlcipher")
    vault.initialize(MASTER_PASSWORD)

    connection = vault._require_connection()
    settings = [row[0] for row in connection.execute("PRAGMA cipher_settings").fetchall()]

    assert connection.execute("PRAGMA kdf_iter").fetchone()[0] == str(SQLCIPHER_KDF_ITER)
    assert connection.execute("PRAGMA cipher_kdf_algorithm").fetchone()[0] == "PBKDF2_HMAC_SHA512"
    assert f"PRAGMA kdf_iter = {SQLCIPHER_KDF_ITER};" in settings
    vault.lock()

    reopened = VaultRepository(vault.path)
    reopened.unlock(MASTER_PASSWORD)
    assert reopened._require_connection().execute("PRAGMA kdf_iter").fetchone()[0] == str(SQLCIPHER_KDF_ITER)
    reopened.lock()


def test_unlock_rejects_wrong_master_password(tmp_path: Path) -> None:
    path = tmp_path / "vault.sqlcipher"
    VaultRepository(path).initialize("right-password")
    reopened = VaultRepository(path)

    with pytest.raises(ValueError, match="无法解锁"):
        reopened.unlock("wrong-password")


def test_unlock_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        VaultRepository(tmp_path / "missing.sqlcipher").unlock("any-password")


def test_initialize_requires_master_password(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="必须设置主密码"):
        VaultRepository(tmp_path / "vault.sqlcipher").initialize("")


def test_new_vault_records_schema_version(tmp_path: Path) -> None:
    vault = VaultRepository(tmp_path / "vault.sqlcipher")
    vault.initialize(MASTER_PASSWORD)

    assert vault._require_connection().execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    vault.lock()


def test_unlock_rejects_vault_from_newer_version(tmp_path: Path) -> None:
    path = tmp_path / "vault.sqlcipher"
    vault = VaultRepository(path)
    vault.initialize(MASTER_PASSWORD)
    vault._require_connection().execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    vault.lock()

    with pytest.raises(ValueError, match="更新版本"):
        VaultRepository(path).unlock(MASTER_PASSWORD)


def test_sqlcipher_encrypts_all_vault_content_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "vault.sqlcipher"
    vault = VaultRepository(path)
    vault.initialize(MASTER_PASSWORD)
    entry = vault.save_entry(
        EntryDraft(
            kind="application",
            name="Private Portal",
            address="https://portal.private.example",
        )
    )
    vault.save_credential(
        entry.id,
        CredentialDraft(
            kind="custom",
            label="Private account",
            username="private-admin",
            password="private-password",
            extra="https://login.private.example",
        ),
    )
    vault.lock()

    raw_database = path.read_bytes()
    assert not raw_database.startswith(b"SQLite format 3\x00")
    for plaintext in (
        b"Private Portal",
        b"portal.private.example",
        b"Private account",
        b"private-admin",
        b"private-password",
        b"login.private.example",
    ):
        assert plaintext not in raw_database

    with sqlite3.connect(path) as plain_connection:
        with pytest.raises(sqlite3.DatabaseError):
            plain_connection.execute("SELECT * FROM sqlite_master").fetchall()

    reopened = VaultRepository(path)
    reopened.unlock(MASTER_PASSWORD)
    entries = reopened.list_entries()
    credentials = reopened.list_credentials(entries[0].id)

    assert entries[0].name == "Private Portal"
    assert credentials[0].username == "private-admin"
    assert credentials[0].password == "private-password"
    assert credentials[0].extra == "https://login.private.example"
    reopened.lock()


def test_legacy_plain_sqlite_vault_is_not_opened(tmp_path: Path) -> None:
    path = tmp_path / "vault.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy (value TEXT)")
        connection.execute("INSERT INTO legacy VALUES ('leave this file untouched')")

    vault = VaultRepository(path)
    original = path.read_bytes()

    with pytest.raises(ValueError, match="旧版未整库加密"):
        vault.unlock("any-password")

    assert path.read_bytes() == original
    assert not vault.unlocked


def test_searches_entry_name_and_address(vault: VaultRepository) -> None:
    vault.save_entry(EntryDraft(kind="application", name="Monitoring", address="status.example.test"))

    assert [entry.name for entry in vault.list_entries("alert")] == []
    assert [entry.name for entry in vault.list_entries("status.example")] == ["Monitoring"]


def test_server_requires_valid_ip_and_uses_ip_when_name_empty(vault: VaultRepository) -> None:
    with pytest.raises(ValueError, match="IPv4 或 IPv6"):
        vault.save_entry(EntryDraft(kind="server", name="Production", address="server.example.test"))

    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.0.2.15"))

    assert entry.name == "192.0.2.15"
    assert entry.address == "192.0.2.15"


def test_entry_credential_counts_serves_every_entry_in_one_query(vault: VaultRepository) -> None:
    server = vault.save_entry(EntryDraft(kind="server", name="", address="192.0.2.9"))
    app_entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    empty = vault.save_entry(EntryDraft(kind="application", name="Empty"))
    vault.save_credential(server.id, CredentialDraft(kind="ssh", label="登录", password="a"))
    vault.save_credential(server.id, CredentialDraft(kind="custom", label="MySQL", password="b"))
    vault.save_credential(app_entry.id, CredentialDraft(kind="custom", label="主账号", password="c"))

    counts = vault.entry_credential_counts()

    # Entries without credentials produce no GROUP BY row; callers cover
    # them with counts.get(entry_id, 0).
    assert counts == {server.id: 2, app_entry.id: 1}
    assert counts.get(empty.id, 0) == 0


def test_delete_entry_cascades_its_credentials(vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="admin", password="secret"))

    vault.delete_entry(entry.id)

    assert vault.list_credentials(entry.id) == []
    assert vault._require_connection().execute("SELECT count(*) FROM credentials").fetchone()[0] == 0


def test_credentials_are_listed_in_manual_insertion_order(vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    for label in ("MySQL", "SSH 登录", "网站后台"):
        vault.save_credential(entry.id, CredentialDraft(kind="custom", label=label, password="secret"))

    assert [credential.label for credential in vault.list_credentials(entry.id)] == ["MySQL", "SSH 登录", "网站后台"]


def test_new_system_login_is_pinned_to_the_top(vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="MySQL", password="a"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="网站后台", password="b"))

    vault.save_credential(entry.id, CredentialDraft(kind="ssh", label="系统登录账号", username="root", password="c"))

    assert [credential.label for credential in vault.list_credentials(entry.id)] == ["系统登录账号", "MySQL", "网站后台"]

    # A second login goes above the first one, staying at the very top.
    vault.save_credential(entry.id, CredentialDraft(kind="rdp", label="系统登录账号", username="administrator", password="d"))
    assert [credential.username for credential in vault.list_credentials(entry.id)] == ["administrator", "root", "", ""]


def test_move_credential_reorders_within_entry(vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    ssh = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="SSH 登录", password="a"))
    mysql = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="MySQL", password="b"))
    web = vault.save_credential(entry.id, CredentialDraft(kind="custom", label="网站后台", password="c"))

    def labels() -> list[str]:
        return [credential.label for credential in vault.list_credentials(entry.id)]

    vault.move_credential(web.id, "up")
    assert labels() == ["SSH 登录", "网站后台", "MySQL"]

    vault.move_credential(ssh.id, "down")
    assert labels() == ["网站后台", "SSH 登录", "MySQL"]

    # Moving past an edge keeps the item in place.
    vault.move_credential(web.id, "up")
    assert labels() == ["网站后台", "SSH 登录", "MySQL"]
    vault.move_credential(mysql.id, "down")
    assert labels() == ["网站后台", "SSH 登录", "MySQL"]

    with pytest.raises(ValueError, match="排序方向"):
        vault.move_credential(ssh.id, "sideways")


def test_move_credential_missing_id_returns_none(vault: VaultRepository) -> None:
    assert vault.move_credential(999, "up") is None


def test_credential_kind_roundtrip_and_validation(vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="server", name="", address="192.168.1.101"))
    vault.save_credential(entry.id, CredentialDraft(kind="ssh", label="SSH 登录", username="root", password="p"))
    rdp = vault.save_credential(entry.id, CredentialDraft(kind="rdp", label="RDP 登录", username="administrator", password="p"))

    # Both are system logins (top-pinned, newest first); order is covered elsewhere.
    assert {credential.kind for credential in vault.list_credentials(entry.id)} == {"ssh", "rdp"}

    updated = vault.save_credential(entry.id, CredentialDraft(kind="ssh", label=rdp.label, username=rdp.username, password="p"), rdp.id)
    assert updated.kind == "ssh"

    with pytest.raises(ValueError, match="项目类型"):
        vault.save_credential(entry.id, CredentialDraft(kind="ftp", label="FTP", password="p"))


def test_unlock_migrates_older_vault_to_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "vault.sqlcipher"
    vault = VaultRepository(path)
    vault.initialize(MASTER_PASSWORD)
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="zeta", password="p1"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="alpha", password="p2"))
    connection = vault._require_connection()
    # Simulate a version-2 vault: no sort_order column, entries still carry a legacy notes column.
    connection.execute("ALTER TABLE credentials DROP COLUMN sort_order")
    connection.execute("ALTER TABLE entries ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 2}")
    connection.commit()
    vault.lock()

    reopened = VaultRepository(path)
    reopened.unlock(MASTER_PASSWORD)
    connection = reopened._require_connection()

    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    entry_columns = {row["name"] for row in connection.execute("PRAGMA table_info(entries)").fetchall()}
    # v6 keeps asset tags (and never had a notes column to begin with).
    assert "tags" in entry_columns and "notes" not in entry_columns
    # The migration keeps the previous label-sorted display order as the initial manual order.
    assert [credential.label for credential in reopened.list_credentials(entry.id)] == ["alpha", "zeta"]
    reopened.lock()


def test_initialize_failure_leaves_no_vault_file_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A half-created file would be mistaken for a vault forever."""
    path = tmp_path / "vault.sqlcipher"
    vault = VaultRepository(path)

    def explode(self) -> None:
        raise RuntimeError("simulated disk failure")

    monkeypatch.setattr(VaultRepository, "_create_schema", explode)

    with pytest.raises(RuntimeError):
        vault.initialize(MASTER_PASSWORD)

    assert not path.exists()
    assert not vault.unlocked


def test_search_treats_like_wildcards_literally(vault: VaultRepository) -> None:
    vault.save_entry(EntryDraft(kind="application", name="alpha-one"))
    vault.save_entry(EntryDraft(kind="application", name="betaXone"))

    assert [entry.name for entry in vault.list_entries("alpha-one")] == ["alpha-one"]
    assert vault.list_entries("%") == []
    assert vault.list_entries("alpha_one") == []
    assert vault.list_entries("_") == []


def test_rekey_requires_the_current_password(vault: VaultRepository) -> None:
    with pytest.raises(ValueError, match="当前主密码不正确"):
        vault.rekey("not the master password", "brand-new-pass")

    # A rejected attempt must leave the vault usable under the old password.
    assert vault.list_entries() == []
    vault.lock()
    VaultRepository(vault.path).unlock(MASTER_PASSWORD)


def test_rekey_reopens_only_with_the_new_password(vault: VaultRepository) -> None:
    entry = vault.save_entry(EntryDraft(kind="application", name="Portal"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="admin", password="p1"))

    vault.rekey(MASTER_PASSWORD, "brand-new-pass")
    # The live connection keeps working after the rewrite.
    assert [credential.label for credential in vault.list_credentials(entry.id)] == ["admin"]
    path = vault.path
    vault.lock()

    with pytest.raises(ValueError):
        VaultRepository(path).unlock(MASTER_PASSWORD)
    reopened = VaultRepository(path)
    reopened.unlock("brand-new-pass")
    assert [entry.name for entry in reopened.list_entries()] == ["Portal"]
    assert reopened._require_connection().execute("PRAGMA kdf_iter").fetchone()[0] == str(SQLCIPHER_KDF_ITER)
    reopened.lock()


def test_master_password_with_a_nul_byte_is_rejected_in_chinese(tmp_path: Path) -> None:
    vault = VaultRepository(tmp_path / "vault.sqlcipher")
    with pytest.raises(ValueError, match="空字符"):
        vault.initialize("bad\x00pass")
    assert not vault.unlocked


def test_unlock_migrates_version_four_vault_by_dropping_database_name(tmp_path: Path) -> None:
    path = tmp_path / "vault.sqlcipher"
    vault = VaultRepository(path)
    vault.initialize(MASTER_PASSWORD)
    entry = vault.save_entry(EntryDraft(kind="server", name="db", address="10.0.0.9"))
    vault.save_credential(entry.id, CredentialDraft(kind="custom", label="mysql", username="root", password="p1"))
    connection = vault._require_connection()
    # Simulate a version-4 vault: credentials still carry the unused column.
    connection.execute("ALTER TABLE credentials ADD COLUMN database_name TEXT NOT NULL DEFAULT ''")
    connection.execute("PRAGMA user_version = 4")
    connection.commit()
    vault.lock()

    reopened = VaultRepository(path)
    reopened.unlock(MASTER_PASSWORD)
    connection = reopened._require_connection()
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(credentials)").fetchall()}
    assert "database_name" not in columns
    (credential,) = reopened.list_credentials(entry.id)
    assert credential.label == "mysql" and credential.password == "p1"
    reopened.lock()


def test_vault_written_with_the_legacy_pragma_order_still_opens(tmp_path: Path) -> None:
    """Older builds set kdf_iter after PRAGMA key; their vaults must keep opening."""
    from sqlcipher3 import dbapi2 as sqlcipher

    from password_manager.vault.repository import APPLICATION_ID

    path = tmp_path / "legacy.sqlcipher"
    legacy = sqlcipher.connect(path)
    legacy.execute("PRAGMA cipher_log_level = none")
    legacy.execute("PRAGMA cipher_compatibility = 4")
    legacy.execute("PRAGMA cipher_default_kdf_iter = 512000")
    legacy.execute(f"PRAGMA key = '{MASTER_PASSWORD}'")
    legacy.execute("PRAGMA kdf_iter = 512000")
    legacy.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    legacy.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    legacy.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    legacy.commit()
    legacy.close()

    vault = VaultRepository(path)
    vault.unlock(MASTER_PASSWORD)
    assert vault._require_connection().execute("PRAGMA kdf_iter").fetchone()[0] == str(SQLCIPHER_KDF_ITER)
    vault.lock()


def test_server_address_accepts_an_optional_port() -> None:
    from password_manager.models import format_host_port, split_host_port

    assert split_host_port("192.168.1.101") == ("192.168.1.101", None)
    assert split_host_port("192.168.1.101:2222") == ("192.168.1.101", 2222)
    assert split_host_port("fd00::1") == ("fd00::1", None)
    assert split_host_port("[fd00::1]:3389") == ("fd00::1", 3389)
    assert format_host_port("10.0.0.5", 2222) == "10.0.0.5:2222"
    assert format_host_port("fd00::1", 3389) == "[fd00::1]:3389"
    assert format_host_port("10.0.0.5", None) == "10.0.0.5"

    with pytest.raises(ValueError, match="端口必须是数字"):
        split_host_port("10.0.0.5:ssh")
    with pytest.raises(ValueError, match="1 到 65535"):
        split_host_port("10.0.0.5:70000")
    with pytest.raises(ValueError, match="方括号"):
        split_host_port("[fd00::1")

    validate_entry_draft(EntryDraft(kind="server", name="db", address="10.0.0.9:2222"))
    with pytest.raises(ValueError, match="IPv4 或 IPv6"):
        validate_entry_draft(EntryDraft(kind="server", name="db", address="db.internal:22"))
