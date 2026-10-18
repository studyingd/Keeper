"""Export every RDP credential of a Keeper vault as a .rdp file.

Windows App for macOS has no scripting interface and no password import
channel: connections enter the app through 文件 → 从 RDP 文件导入..., while
saved passwords live in the login keychain and are written by the app
itself on first connect (the DPAPI "password 51:b:" blobs inside Windows
.rdp files cannot be decrypted on macOS). This helper therefore emits one
.rdp per stored RDP credential, carrying the address and username only, so
the whole set can be imported in one go; each password is typed once on
first connect (or pasted from Keeper) and remembered afterwards.

Handing a .rdp to Windows App any other way (double-click, ``open``) starts
a one-off session instead of importing it, so the menu entry above is the
only way these files become persistent connections.

    python scripts/export_rdp_for_windows_app.py [--vault PATH] [--out DIR]
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
from pathlib import Path

from password_manager.models import format_host_port, split_host_port
from password_manager.services.actions import rdp_connection_lines, write_rdp_file
from password_manager.vault.repository import VaultRepository

DEFAULT_VAULT = Path(os.environ.get("PASSWORD_MANAGER_VAULT", Path.home() / ".keeper" / "vault.sqlcipher"))


def safe_name(value: str) -> str:
    return re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE) or "rdp"


def write_rdp(path: Path, host: str, username: str) -> None:
    # Shared with the in-app RDP launcher so the two cannot drift apart.
    write_rdp_file(path, rdp_connection_lines(host, username))


def export(repository: VaultRepository, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    seen: set[str] = set()
    for entry in repository.list_entries():
        for credential in repository.list_credentials(entry.id):
            if credential.kind != "rdp":
                continue
            if not entry.address:
                print(f"跳过 {credential.label}：资产没有 IP 地址。")
                continue
            try:
                # Same normalisation connect_rdp applies, so an exported file
                # and an in-app launch always carry an identical address.
                address = format_host_port(*split_host_port(entry.address))
            except ValueError as error:
                print(f"跳过 {credential.label}：{error}")
                continue
            stem = f"{safe_name(address)}__{safe_name(credential.label or credential.username)}"
            while stem in seen:
                stem += "_2"
            seen.add(stem)
            target = out_dir / f"{stem}.rdp"
            write_rdp(target, address, credential.username)
            written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="把保险库中的 RDP 凭据导出为 .rdp 文件。")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--out", type=Path, default=Path.home() / "Desktop" / "keeper-rdp")
    args = parser.parse_args()

    repository = VaultRepository(args.vault)
    repository.unlock(getpass.getpass("Keeper 主密码："))
    try:
        written = export(repository, args.out)
    finally:
        repository.lock()

    print(f"已导出 {len(written)} 个 .rdp 到 {args.out}")
    print("在 Windows App 中用 文件 → 从 RDP 文件导入... 选中这些文件即可添加连接；")
    print("首次连接时输入一次密码（或从 Keeper 复制粘贴），之后由钥匙串记住。")


if __name__ == "__main__":
    main()
