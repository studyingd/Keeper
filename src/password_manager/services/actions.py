"""Safe adapters for opening external resources."""

from __future__ import annotations

import ctypes
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Callable

from password_manager.models import format_host_port, split_host_port

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Microsoft Windows App (formerly Microsoft Remote Desktop) on macOS.
WINDOWS_APP_BUNDLE_ID = "com.microsoft.rdc.macos"

# macOS SSH autofill: how long the private socket stays open waiting for
# OpenSSH to ask, and how many prompts it will answer before disappearing.
# ssh may ask for an identity file's passphrase before it ever asks for the
# password, so a single answer is not enough.
MACOS_ASKPASS_TIMEOUT = 120.0
MACOS_ASKPASS_ATTEMPTS = 5
# The only environment keys the macOS launcher may inline into the Terminal
# command line. Neither carries a secret; the allowlist keeps it that way.
MACOS_INLINE_ENV_KEYS = ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE")
# BSD sockets store their path in a 104-byte field.
UNIX_PATH_MAX = 104


def extract_url(*values: str) -> str | None:
    """Return the first HTTP(S) URL from freeform credential data."""
    for value in values:
        match = URL_PATTERN.search(value or "")
        if match:
            return match.group(0).rstrip(".,;:)")
    return None


def chrome_executable() -> Path | None:
    """Locate a Chrome installation, if present."""
    if sys.platform == "darwin":
        candidate = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if candidate.exists():
            return candidate
        which = shutil.which("google-chrome")
        return Path(which) if which else None

    roots = (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA"))
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if candidate.exists():
            return candidate
    which = shutil.which("chrome")
    return Path(which) if which else None


def default_opener() -> Callable[[str], bool]:
    """Prefer Chrome; fall back to the system default browser when Chrome is absent."""
    chrome = chrome_executable()
    if chrome is None:
        return webbrowser.open

    def open_with_chrome(url: str) -> bool:
        subprocess.Popen([str(chrome), url])
        return True

    return open_with_chrome


def open_url(url: str, opener: Callable[[str], bool] | None = None) -> None:
    if not url.strip():
        raise ValueError("该资产没有保存网站地址。")
    normalized = url if "://" in url else f"https://{url}"
    (opener or default_opener())(normalized)


CONCEALED_CLIPBOARD_SCRIPT = """
ObjC.import('AppKit');
var text = $.NSProcessInfo.processInfo.environment.objectForKey('KEEPER_CLIP_TEXT');
var pasteboard = $.NSPasteboard.generalPasteboard;
pasteboard.clearContents;
if (text && text.js) { pasteboard.setStringForType(text, 'public.utf8-plain-text'); }
pasteboard.setStringForType('true', 'org.nspasteboard.ConcealedType');
pasteboard.setStringForType('true', 'org.nspasteboard.TransientType');
""".strip()


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


_CORE_GRAPHICS: ctypes.CDLL | None = None


def _core_graphics() -> ctypes.CDLL | None:
    """Load CoreGraphics once; the idle poll calls this every few seconds."""
    global _CORE_GRAPHICS
    if _CORE_GRAPHICS is None:
        try:
            library = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        except OSError:
            return None
        probe = library.CGEventSourceSecondsSinceLastEventType
        probe.restype = ctypes.c_double
        probe.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        _CORE_GRAPHICS = library
    return _CORE_GRAPHICS


def system_idle_seconds() -> float | None:
    """Return how long the user has been idle system-wide, or None if unknown.

    Used to lock a window that is still open but unattended. Reading the
    platform counter instead of watching this app's own events means a session
    Keeper started (an SSH terminal, say) counts as activity and is not cut off.
    """
    if sys.platform == "darwin":
        core_graphics = _core_graphics()
        if core_graphics is None:
            return None
        # kCGEventSourceStateCombinedSessionState + kCGAnyInputEventType
        return float(core_graphics.CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF))

    if sys.platform == "win32":
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(_LastInputInfo)
        try:
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return None
            return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
        except (OSError, AttributeError):
            return None

    return None


def set_concealed_clipboard(text: str) -> bool:
    """Copy ``text`` on macOS marked so clipboard managers and Handoff skip it.

    Qt 6 renames every custom pasteboard flavour to ``com.trolltech.anymime.*``,
    which no clipboard manager recognises, so the ``org.nspasteboard.ConcealedType``
    marker is written by a short JXA script instead. The text rides in an
    environment variable and never reaches argv. Returns False when osascript is
    unavailable or fails, so the caller falls back to the plain Qt clipboard.
    """
    if sys.platform != "darwin":
        return False
    osascript = Path("/usr/bin/osascript")
    if not osascript.exists():
        return False
    env = os.environ.copy()
    env["KEEPER_CLIP_TEXT"] = text
    try:
        completed = subprocess.run(
            [str(osascript), "-l", "JavaScript", "-e", CONCEALED_CLIPBOARD_SCRIPT],
            env=env,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def ssh_executable() -> Path | None:
    """Locate the system OpenSSH client.

    On Windows, prefer the bundled client over anything earlier on PATH (such as
    Git/MSYS ssh): the native build is a true console application and honors
    SSH_ASKPASS_REQUIRE, which the password autofill relies on.
    """
    if sys.platform == "win32":
        candidate = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
        if candidate.exists():
            return candidate
    else:
        candidate = Path("/usr/bin/ssh")
        if candidate.exists():
            return candidate
    which = shutil.which("ssh")
    return Path(which) if which else None


def rdp_executable() -> Path | None:
    if sys.platform == "darwin":
        candidate = Path("/usr/bin/open")
        return candidate if candidate.exists() else None

    which = shutil.which("mstsc")
    if which:
        return Path(which)
    candidate = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "mstsc.exe"
    return candidate if candidate.exists() else None


def askpass_executable() -> Path | None:
    """Locate the bundled Windows helper used for SSH autofill."""
    if sys.platform != "win32":
        return None

    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = Path(base) / "password_manager" / "assets" / "keeper-askpass.exe"
        if candidate.exists():
            return candidate
    candidate = Path(__file__).resolve().parent.parent / "assets" / "keeper-askpass.exe"
    return candidate if candidate.exists() else None


def netcat_executable() -> Path | None:
    """Locate the BSD netcat that the macOS SSH askpass helper talks through."""
    if sys.platform != "darwin":
        return None

    candidate = Path("/usr/bin/nc")
    if candidate.exists():
        return candidate
    which = shutil.which("nc")
    return Path(which) if which else None


def _silent_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _silent_rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _schedule_cleanup(path: Path, delay: float = 60.0) -> None:
    timer = threading.Timer(delay, _silent_unlink, args=(path,))
    timer.daemon = True
    timer.start()


def _schedule_directory_cleanup(path: Path, delay: float = 120.0) -> None:
    timer = threading.Timer(delay, _silent_rmtree, args=(path,))
    timer.daemon = True
    timer.start()


def _bind_askpass_socket(socket_path: Path, attempts: int) -> socket.socket | None:
    """Create the listening socket before anything can observe it.

    Binding and tightening the permissions happen here, in the caller's
    thread, so the socket is never briefly world reachable while a background
    thread is still being scheduled.
    """
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        server.listen(attempts)
        return server
    except OSError:
        server.close()
        _silent_unlink(socket_path)
        return None


def _serve_password_over_socket(
    server: socket.socket,
    password: str,
    socket_path: Path,
    token: str,
    timeout: float,
    attempts: int,
) -> None:
    """Hand ``password`` to the askpass helper over a private unix socket.

    The socket sits in a directory only the current user may enter, answers a
    few prompts and then disappears along with that directory. A caller has to
    present the random token, so another local process cannot simply connect
    and fish the password out.
    """
    try:
        server.settimeout(timeout)
        for _ in range(attempts):
            connection, _ = server.accept()
            with connection:
                if connection.recv(256).decode("utf-8", "replace").strip() == token:
                    connection.sendall(password.encode("utf-8"))
    except OSError:
        pass
    finally:
        server.close()
        _silent_unlink(socket_path)


def _macos_askpass_environment(password: str) -> dict[str, str] | None:
    """Build the macOS environment used for OpenSSH password autofill.

    OpenSSH on macOS honours SSH_ASKPASS_REQUIRE=force just like the Windows
    build does, but the environment route is unavailable here: the session is
    started by telling Terminal.app to run a command, and that shell inherits
    Terminal's environment rather than ours. So the generated helper pulls the
    password from a short-lived unix socket instead. The helper script itself
    holds nothing but a random token, which keeps the password out of argv,
    out of the Terminal command line and off the disk.
    """
    netcat = netcat_executable()
    if netcat is None:
        return None

    directory = Path(tempfile.mkdtemp(prefix="keeper-ssh-"))
    try:
        os.chmod(directory, 0o700)
        socket_path = directory / "askpass.sock"
        if len(os.fsencode(socket_path)) >= UNIX_PATH_MAX:
            _silent_rmtree(directory)
            return None
        token = secrets.token_urlsafe(24)
        helper = directory / "askpass.sh"
        helper.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' {shlex.quote(token)} | "
            f"{shlex.quote(str(netcat))} -U {shlex.quote(str(socket_path))}\n",
            encoding="utf-8",
        )
        os.chmod(helper, 0o700)
    except OSError:
        _silent_rmtree(directory)
        return None

    server = _bind_askpass_socket(socket_path, MACOS_ASKPASS_ATTEMPTS)
    if server is None:
        _silent_rmtree(directory)
        return None

    worker = threading.Thread(
        target=_serve_password_over_socket,
        args=(server, password, socket_path, token, MACOS_ASKPASS_TIMEOUT, MACOS_ASKPASS_ATTEMPTS),
        daemon=True,
    )
    worker.start()
    _schedule_directory_cleanup(directory, MACOS_ASKPASS_TIMEOUT + 5.0)
    return {"SSH_ASKPASS": str(helper), "SSH_ASKPASS_REQUIRE": "force"}


def _askpass_environment(password: str) -> dict[str, str] | None:
    """Build the environment used for OpenSSH password autofill.

    OpenSSH refuses passwords on the command line, but its SSH_ASKPASS hook
    asks an external program for the password, and SSH_ASKPASS_REQUIRE=force
    makes it do so even when a terminal is attached.

    On Windows the preferred helper is the bundled keeper-askpass.exe: it
    merely prints the KEEPER_SSH_PASSWORD environment variable, which only the
    child ssh process can see, so no secret ever touches argv or disk. If the
    helper is missing, fall back to a generated batch file with the same trick
    (deleted again shortly after).

    macOS cannot pass an environment to Terminal.app, so it uses the socket
    backed helper described in _macos_askpass_environment.
    """
    if sys.platform == "darwin":
        return _macos_askpass_environment(password)
    if sys.platform != "win32":
        return None

    helper = askpass_executable()
    if helper is None:
        fd, script = tempfile.mkstemp(prefix="keeper-askpass-", suffix=".bat")
        with os.fdopen(fd, "w", newline="") as handle:
            handle.write('@echo off\r\nset /p ="%KEEPER_SSH_PASSWORD%" < nul\r\n')
        helper = Path(script)
        _schedule_cleanup(helper)
    env = os.environ.copy()
    env["KEEPER_SSH_PASSWORD"] = password
    env["SSH_ASKPASS"] = str(helper)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    env["DISPLAY"] = "1"
    return env


def default_ssh_launcher(command: list[str], env: dict[str, str] | None = None) -> None:
    if sys.platform == "darwin":
        # Terminal.app is spawned through AppleScript and inherits nothing from
        # this process, so the askpass settings are prefixed onto the command
        # it runs. The allowlist guarantees no secret can be inlined here.
        prefix = "".join(
            f"{key}={shlex.quote(value)} "
            for key, value in sorted((env or {}).items())
            if key in MACOS_INLINE_ENV_KEYS
        )
        shell_command = prefix + shlex.join(command)
        escaped = shell_command.replace("\\", "\\\\").replace("\"", "\\\"")
        apple_command = f'tell application "Terminal" to do script "{escaped}"'
        subprocess.Popen(["/usr/bin/osascript", "-e", apple_command])
        return

    # ssh is a console program: allocate a fresh console window for it so the
    # session survives independently of this windowed (console-less) app.
    if sys.platform == "win32":
        subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE, env=env)
    else:
        subprocess.Popen(command, env=env)


def default_rdp_launcher(command: list[str], env: dict[str, str] | None = None) -> None:
    if sys.platform == "darwin":
        try:
            subprocess.run(command, env=env, check=True)
        except subprocess.CalledProcessError as exc:
            raise ValueError("未找到 Microsoft Windows App。请从 App Store 安装后重试。") from exc
        return

    subprocess.Popen(command, env=env)


def connect_ssh(
    host: str,
    username: str = "",
    password: str = "",
    launcher: Callable[[list[str], dict[str, str] | None], None] | None = None,
) -> None:
    """Launch the system OpenSSH client; the password never enters argv."""
    if not host.strip():
        raise ValueError("该服务器没有保存 IP 地址。")
    ssh = ssh_executable()
    if ssh is None:
        if sys.platform == "win32":
            raise ValueError("未找到 ssh.exe。请在 Windows 设置 → 应用 → 可选功能 中启用 OpenSSH 客户端后重试。")
        raise ValueError("未找到 ssh。请安装 OpenSSH 客户端后重试。")
    ip, port = split_host_port(host)
    target = f"{username.strip()}@{ip}" if username.strip() else ip
    command = [str(ssh), "-o", "StrictHostKeyChecking=accept-new"]
    if port is not None:
        command += ["-p", str(port)]
    command.append(target)
    env = _askpass_environment(password) if password else None
    # accept-new: trust a server's host key the very first time (one-click
    # connections cannot answer the interactive yes/no prompt), but still
    # reject a key that later changes.
    (launcher or default_ssh_launcher)(command, env)


def _dpapi_protect(data: bytes) -> str | None:
    """DPAPI-encrypt ``data`` for the current user and return lowercase hex."""
    if sys.platform != "win32":
        return None

    try:
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

        buf = ctypes.create_string_buffer(data, len(data))
        in_blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            return None
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
        return encrypted.hex()
    except (OSError, AttributeError, ValueError):
        return None


def _generate_rdp_file(host: str, username: str, password: str) -> Path | None:
    """Write a temporary .rdp that lets mstsc log on without a prompt.

    The password is embedded the same way mstsc's own "remember my
    credentials" stores it: a DPAPI blob ("password 51:b:"), which only the
    current Windows user can decrypt. Credential-manager entries are not
    used: mstsc ignores the password of GENERIC credentials and Windows
    strips the password from DOMAIN_PASSWORD entries written by third
    parties, so an .rdp file is the only mechanism that actually auto-fills.
    """
    blob = _dpapi_protect(password.encode("utf-16-le"))
    if blob is None:
        return None
    return _write_rdp_file(rdp_connection_lines(host, username) + [f"password 51:b:{blob}"])


def rdp_connection_lines(host: str, username: str) -> list[str]:
    # Screen mode/size deliberately omitted so the session inherits the
    # client's own defaults (typically fullscreen at native resolution);
    # smart sizing lets a windowed session scale freely when resized.
    lines = [
        f"full address:s:{host}",
        "prompt for credentials:i:0",
        "smart sizing:i:1",
    ]
    if username.strip():
        lines.append(f"username:s:{username.strip()}")
    return lines


def write_rdp_file(path: Path, lines: list[str]) -> None:
    """Write .rdp content in the UTF-16 encoding every RDP client expects."""
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-16"))


def _write_rdp_file(lines: list[str]) -> Path:
    fd, path = tempfile.mkstemp(prefix="keeper-rdp-", suffix=".rdp")
    os.close(fd)
    target = Path(path)
    write_rdp_file(target, lines)
    return target


def _generate_macos_rdp_file(host: str, username: str) -> Path | None:
    """Write a temporary .rdp that Windows App on macOS will actually open.

    Windows App 11.x answers every ``rdp://`` URL with "failed processing
    import URL" and ``notSupported``, so handing it a .rdp file is the only
    programmatic way left to start a session. macOS has no DPAPI and cannot
    build the "password 51:b:" blob, so the file carries the address and
    username only; the password travels on the clipboard for one paste, or is
    not needed at all once Windows App holds a saved credential for that PC.
    """
    try:
        return _write_rdp_file(rdp_connection_lines(host, username))
    except OSError:
        return None


def connect_rdp(
    host: str,
    username: str = "",
    password: str = "",
    launcher: Callable[[list[str], dict[str, str] | None], None] | None = None,
) -> None:
    """Launch the system Remote Desktop client, auto-filling credentials.

    With a saved username/password a temporary .rdp file carrying a
    DPAPI-encrypted password blob is generated and removed again shortly
    after launch; without one, mstsc simply opens the connection dialog.
    """
    if not host.strip():
        raise ValueError("该服务器没有保存 IP 地址。")
    address = format_host_port(*split_host_port(host))
    if sys.platform == "darwin":
        opener = rdp_executable()
        if opener is None:
            raise ValueError("未找到 macOS 的 open 命令。")
        rdp = _generate_macos_rdp_file(address, username)
        if rdp is None:
            raise ValueError("无法写入临时 .rdp 文件，请检查磁盘空间和临时目录权限。")
        _schedule_cleanup(rdp)
        (launcher or default_rdp_launcher)([str(opener), "-b", WINDOWS_APP_BUNDLE_ID, str(rdp)], None)
        return

    mstsc = rdp_executable()
    if mstsc is None:
        raise ValueError("未找到远程桌面客户端 mstsc.exe。")
    command = [str(mstsc), f"/v:{address}"]
    if username.strip() and password:
        rdp = _generate_rdp_file(address, username, password)
        if rdp is not None:
            command = [str(mstsc), str(rdp)]
            _schedule_cleanup(rdp)
    (launcher or default_rdp_launcher)(command, None)
