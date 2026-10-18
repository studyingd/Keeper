"""SQLCipher-backed schema and encrypted vault persistence."""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from pathlib import Path

from sqlcipher3 import dbapi2 as sqlcipher

from password_manager.models import Credential, CredentialDraft, Entry, EntryDraft, split_host_port

SCHEMA_VERSION = 6
SQLITE_HEADER = b"SQLite format 3\x00"
APPLICATION_ID = 0x564B5032  # "VKP2"
SQLCIPHER_COMPATIBILITY = 4
SQLCIPHER_KDF_ITER = 512_000


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so searching for "%" or "_" stays literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


MAX_ENTRY_TAGS = 8
MAX_ENTRY_TAG_LENGTH = 24


def normalize_entry_tags(tags: list[str]) -> list[str]:
    """Trim, split on commas, drop empties and duplicates."""
    result: list[str] = []
    for raw in tags:
        for part in str(raw).replace("，", ",").split(","):
            tag = part.strip()
            if tag and tag not in result:
                result.append(tag)
    return result


def validate_entry_draft(draft: EntryDraft) -> None:
    """Validate an entry draft; raise ValueError with a user-facing Chinese message."""
    if draft.kind not in {"application", "server"}:
        raise ValueError("资产类型必须是应用或服务器。")
    if draft.kind == "server":
        if not draft.address.strip():
            raise ValueError("服务器 IP 不能为空。")
        host, _port = split_host_port(draft.address)
        try:
            ipaddress.ip_address(host)
        except ValueError as error:
            raise ValueError("请输入有效的 IPv4 或 IPv6 服务器 IP，可选加端口，如 192.168.1.101 或 192.168.1.101:2222。") from error
    elif not draft.name.strip():
        raise ValueError("应用名称不能为空。")
    tags = normalize_entry_tags(draft.tags)
    if len(tags) > MAX_ENTRY_TAGS:
        raise ValueError(f"标签最多 {MAX_ENTRY_TAGS} 个。")
    if any(len(tag) > MAX_ENTRY_TAG_LENGTH for tag in tags):
        raise ValueError(f"每个标签不能超过 {MAX_ENTRY_TAG_LENGTH} 个字符。")


def validate_credential_draft(draft: CredentialDraft) -> None:
    """Validate a credential draft; raise ValueError with a user-facing Chinese message."""
    if draft.kind not in {"custom", "ssh", "rdp"}:
        raise ValueError("项目类型必须是 custom、ssh 或 rdp。")
    if not draft.label.strip():
        raise ValueError("项目名称不能为空。")


class VaultRepository:
    """Persist a vault in a SQLCipher-encrypted SQLite database."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.connection: sqlcipher.Connection | None = None

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        return self.connection is not None

    def initialize(self, master_password: str) -> None:
        if self.exists:
            raise ValueError("该位置已经存在保险库文件。")
        if not master_password:
            raise ValueError("必须设置主密码。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.connection = self._connect(master_password)
            self._create_schema()
            self._require_connection().execute(f"PRAGMA application_id = {APPLICATION_ID}")
            self._require_connection().execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._require_connection().commit()
        except Exception:
            self.lock()
            # The file did not exist when this method was entered, so anything
            # left behind is our own half-written vault. Keeping it would make
            # every later start believe a vault already exists, then fail to
            # unlock it - a dead end only a manual file deletion could escape.
            try:
                self.path.unlink()
            except OSError:
                pass
            raise

    def unlock(self, master_password: str) -> None:
        if not self.exists:
            raise FileNotFoundError("保险库文件尚未创建。")
        if self._is_plain_sqlite_file():
            raise ValueError("检测到旧版未整库加密的 vault.db。请使用新的 vault.sqlcipher 创建保险库；旧文件不会被修改。")
        if not master_password:
            raise ValueError("必须输入主密码。")
        try:
            self.connection = self._connect(master_password)
            connection = self._require_connection()
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except (sqlcipher.DatabaseError, IndexError) as error:
            self.lock()
            raise ValueError("无法解锁保险库。请检查主密码或保险库文件。") from error
        if application_id != APPLICATION_ID:
            self.lock()
            raise ValueError("不是 Keeper SQLCipher 保险库。")
        if schema_version > SCHEMA_VERSION:
            self.lock()
            raise ValueError("该保险库由更新版本的 Keeper 创建，当前版本无法打开。")
        if schema_version < SCHEMA_VERSION:
            self._migrate()

    def lock(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def rekey(self, current_password: str, new_password: str) -> None:
        """Change the master password of the currently unlocked vault.

        SQLCipher rewrites every page under a fresh salt and key; the schema
        version and all stored rows are carried over unchanged. The current
        password is verified on a second connection first, so an unattended but
        already-unlocked window cannot be used to lock the owner out.
        """
        connection = self._require_connection()
        if not new_password:
            raise ValueError("必须设置主密码。")
        probe = self._connect(current_password)
        try:
            probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlcipher.DatabaseError as error:
            raise ValueError("当前主密码不正确。") from error
        finally:
            probe.close()
        escaped_password = new_password.replace("'", "''")
        try:
            connection.execute(f"PRAGMA rekey = '{escaped_password}'")
        except ValueError as error:
            raise ValueError("主密码不能包含空字符（NUL）。") from error
        connection.commit()

    def list_entries(self, query: str = "") -> list[Entry]:
        connection = self._require_connection()
        term = f"%{_escape_like(query.strip())}%"
        rows = connection.execute(
            r"""
            SELECT * FROM entries
            WHERE name LIKE ? ESCAPE '\'
               OR COALESCE(address, '') LIKE ? ESCAPE '\'
               OR tags LIKE ? ESCAPE '\'
            ORDER BY kind, name COLLATE NOCASE
            """,
            (term, term, term),
        ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def get_entry(self, entry_id: int) -> Entry | None:
        row = self._require_connection().execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return self._entry_from_row(row) if row else None

    def save_entry(self, draft: EntryDraft, entry_id: int | None = None) -> Entry:
        connection = self._require_connection()
        validate_entry_draft(draft)
        tags = ",".join(normalize_entry_tags(draft.tags))
        if draft.kind == "server":
            server_ip = draft.address.strip()
            draft = EntryDraft(kind="server", name=draft.name.strip() or server_ip, address=server_ip, tags=normalize_entry_tags(draft.tags))
        now = self._timestamp()
        if entry_id is None:
            cursor = connection.execute(
                """INSERT INTO entries (kind, name, address, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (draft.kind, draft.name.strip(), draft.address.strip() or None, tags, now, now),
            )
            entry_id = cursor.lastrowid
        else:
            connection.execute(
                """UPDATE entries SET kind=?, name=?, address=?, tags=?, updated_at=? WHERE id=?""",
                (draft.kind, draft.name.strip(), draft.address.strip() or None, tags, now, entry_id),
            )
        connection.commit()
        return self.get_entry(entry_id)  # type: ignore[arg-type]

    def delete_entry(self, entry_id: int) -> None:
        connection = self._require_connection()
        connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        connection.commit()

    def list_credentials(self, entry_id: int) -> list[Credential]:
        rows = self._require_connection().execute(
            "SELECT * FROM credentials WHERE entry_id = ? ORDER BY sort_order, id", (entry_id,)
        ).fetchall()
        return [self._credential_from_row(row) for row in rows]

    def get_credential(self, credential_id: int) -> Credential | None:
        row = self._require_connection().execute("SELECT * FROM credentials WHERE id = ?", (credential_id,)).fetchone()
        return self._credential_from_row(row) if row else None

    def save_credential(self, entry_id: int, draft: CredentialDraft, credential_id: int | None = None) -> Credential:
        connection = self._require_connection()
        validate_credential_draft(draft)
        now = self._timestamp()
        if credential_id is None:
            if draft.kind in {"ssh", "rdp"}:
                # System logins are pinned to the top by default (the ↑↓
                # buttons can still move them anywhere afterwards).
                next_order = connection.execute(
                    "SELECT COALESCE(MIN(sort_order), 0) - 1 FROM credentials WHERE entry_id = ?", (entry_id,)
                ).fetchone()[0]
            else:
                next_order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM credentials WHERE entry_id = ?", (entry_id,)
                ).fetchone()[0]
            cursor = connection.execute(
                """INSERT INTO credentials
                (entry_id, kind, label, username, password, extra, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, draft.kind, draft.label.strip(), draft.username, draft.password, draft.extra, next_order, now, now),
            )
            credential_id = cursor.lastrowid
        else:
            connection.execute(
                """UPDATE credentials SET kind=?, label=?, username=?, password=?, extra=?, updated_at=?
                WHERE id=? AND entry_id=?""",
                (draft.kind, draft.label.strip(), draft.username, draft.password, draft.extra, now, credential_id, entry_id),
            )
        connection.commit()
        return self.get_credential(credential_id)  # type: ignore[arg-type]

    def delete_credential(self, credential_id: int) -> None:
        connection = self._require_connection()
        connection.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
        connection.commit()

    def move_credential(self, credential_id: int, direction: str) -> Credential | None:
        """Swap a credential's position with the neighbour above ('up') or below ('down')."""
        if direction not in {"up", "down"}:
            raise ValueError("排序方向必须是 up 或 down。")
        connection = self._require_connection()
        current = connection.execute(
            "SELECT entry_id, sort_order FROM credentials WHERE id = ?", (credential_id,)
        ).fetchone()
        if current is None:
            return None
        if direction == "up":
            neighbour = connection.execute(
                """SELECT id, sort_order FROM credentials
                WHERE entry_id = ? AND (sort_order < ? OR (sort_order = ? AND id < ?))
                ORDER BY sort_order DESC, id DESC LIMIT 1""",
                (current["entry_id"], current["sort_order"], current["sort_order"], credential_id),
            ).fetchone()
        else:
            neighbour = connection.execute(
                """SELECT id, sort_order FROM credentials
                WHERE entry_id = ? AND (sort_order > ? OR (sort_order = ? AND id > ?))
                ORDER BY sort_order, id LIMIT 1""",
                (current["entry_id"], current["sort_order"], current["sort_order"], credential_id),
            ).fetchone()
        if neighbour is None:
            return self.get_credential(credential_id)
        connection.execute("UPDATE credentials SET sort_order = ? WHERE id = ?", (neighbour["sort_order"], credential_id))
        connection.execute("UPDATE credentials SET sort_order = ? WHERE id = ?", (current["sort_order"], neighbour["id"]))
        connection.commit()
        return self.get_credential(credential_id)

    def _migrate(self) -> None:
        """Upgrade an older unlocked vault to the current schema version in place."""
        connection = self._require_connection()
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(credentials)").fetchall()}
        if "sort_order" not in columns:
            connection.execute("ALTER TABLE credentials ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            # Preserve the previous label-sorted display order as the initial manual order.
            rows = connection.execute(
                "SELECT id, entry_id FROM credentials ORDER BY entry_id, label COLLATE NOCASE, id"
            ).fetchall()
            next_order: dict[int, int] = {}
            for row in rows:
                connection.execute("UPDATE credentials SET sort_order = ? WHERE id = ?", (next_order.get(row["entry_id"], 0), row["id"]))
                next_order[row["entry_id"]] = next_order.get(row["entry_id"], 0) + 1
        if "database_name" in columns:
            connection.execute("ALTER TABLE credentials DROP COLUMN database_name")
        entry_columns = {row["name"] for row in connection.execute("PRAGMA table_info(entries)").fetchall()}
        if "notes" in entry_columns:
            # Legacy pre-v4 column; nothing ever read it.
            connection.execute("DROP INDEX IF EXISTS entries_search_idx")
            connection.execute("ALTER TABLE entries DROP COLUMN notes")
            entry_columns.discard("notes")
        if "tags" not in entry_columns:
            # v6 restores asset tags; a pre-v4 vault that still carries a tags
            # column keeps its data, everyone else gets an empty one.
            connection.execute("ALTER TABLE entries ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
        connection.execute("DROP INDEX IF EXISTS entries_search_idx")
        connection.execute("CREATE INDEX IF NOT EXISTS entries_search_idx ON entries(name, address)")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()

    def _connect(self, master_password: str) -> sqlcipher.Connection:
        connection = sqlcipher.connect(self.path)
        connection.row_factory = sqlcipher.Row
        # SQLCipher logs codec failures (e.g. a wrong master password) to stderr at
        # the C level. The application already reports unlock failures through the UI,
        # so silence the raw logs instead of printing scary ERROR lines to the console.
        connection.execute("PRAGMA cipher_log_level = none")
        connection.execute(f"PRAGMA cipher_compatibility = {SQLCIPHER_COMPATIBILITY}")
        # Every KDF setting has to precede PRAGMA key: SQLCipher applies it to a
        # database created by this connection, while an existing one reads its own
        # iteration count back out of the encrypted header.
        connection.execute(f"PRAGMA cipher_default_kdf_iter = {SQLCIPHER_KDF_ITER}")
        # SQLCipher derives the database key with its per-file random salt and KDF.
        escaped_password = master_password.replace("'", "''")
        try:
            connection.execute(f"PRAGMA key = '{escaped_password}'")
        except ValueError as error:
            connection.close()
            raise ValueError("主密码不能包含空字符（NUL）。") from error
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _is_plain_sqlite_file(self) -> bool:
        with self.path.open("rb") as vault_file:
            return vault_file.read(len(SQLITE_HEADER)) == SQLITE_HEADER

    def _create_schema(self) -> None:
        connection = self._require_connection()
        statements = (
            """CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('application','server')),
                name TEXT NOT NULL, address TEXT, tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                kind TEXT NOT NULL, label TEXT NOT NULL, username TEXT NOT NULL DEFAULT '', password TEXT NOT NULL,
                extra TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS entries_search_idx ON entries(name, address)",
            "CREATE INDEX IF NOT EXISTS credentials_entry_idx ON credentials(entry_id)",
        )
        for statement in statements:
            connection.execute(statement)

    def _entry_from_row(self, row: sqlcipher.Row) -> Entry:
        raw_tags = row["tags"] if "tags" in row.keys() else ""
        return Entry(
            id=row["id"], kind=row["kind"], name=row["name"], address=row["address"],
            tags=normalize_entry_tags((raw_tags or "").split(",")),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _credential_from_row(self, row: sqlcipher.Row) -> Credential:
        return Credential(
            id=row["id"], entry_id=row["entry_id"], kind=row["kind"], label=row["label"], username=row["username"],
            password=row["password"], extra=row["extra"], sort_order=row["sort_order"],
            created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _require_connection(self) -> sqlcipher.Connection:
        if self.connection is None:
            raise RuntimeError("保险库已锁定。")
        return self.connection

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
