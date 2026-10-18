from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

EntryKind = Literal["application", "server"]


def split_host_port(address: str) -> tuple[str, int | None]:
    """Split a stored server address into an IP and an optional port.

    Accepted forms are ``192.168.1.101``, ``192.168.1.101:2222``, ``fd00::1``
    and ``[fd00::1]:2222``. A malformed port raises ValueError with a
    user-facing Chinese message rather than being silently ignored.
    """
    text = (address or "").strip()
    if text.startswith("["):
        bracketed, bracket, rest = text.partition("]")
        if not bracket:
            raise ValueError("IPv6 地址的方括号没有闭合。")
        host = bracketed[1:]
        port_text = rest[1:] if rest.startswith(":") else rest
    elif text.count(":") == 1:
        host, _, port_text = text.partition(":")
    else:
        host, port_text = text, ""
    port_text = port_text.strip()
    if not port_text:
        return host.strip(), None
    if not port_text.isdigit():
        raise ValueError("端口必须是数字。")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间。")
    return host.strip(), port


def format_host_port(host: str, port: int | None) -> str:
    """Re-join a host and port the way .rdp files and mstsc expect to read them."""
    if port is None:
        return host
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


@dataclass(frozen=True)
class Entry:
    id: int
    kind: EntryKind
    name: str
    address: str | None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Credential:
    id: int
    entry_id: int
    kind: str
    label: str
    username: str
    password: str
    extra: str
    created_at: datetime
    updated_at: datetime
    sort_order: int = 0


@dataclass(frozen=True)
class EntryDraft:
    kind: EntryKind
    name: str
    address: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CredentialDraft:
    kind: str
    label: str
    username: str = ""
    password: str = ""
    extra: str = ""
