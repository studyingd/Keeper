import os
import shutil
import sys
import subprocess
import time
from pathlib import Path

import pytest

import password_manager.services.actions as actions
from password_manager.services.actions import extract_url, open_url


class FakeTimer:
    daemon = False

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        pass


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific behavior")
macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific behavior")


def test_url_is_normalized_before_opening() -> None:
    opened: list[str] = []

    open_url("portal.example.test", opened.append)

    assert opened == ["https://portal.example.test"]


def test_open_url_without_address_raises_chinese_message() -> None:
    with pytest.raises(ValueError, match="没有保存网站地址"):
        open_url("   ")


def test_extracts_only_http_urls_from_credential_text() -> None:
    assert extract_url("Admin panel: https://panel.example.test/login.") == "https://panel.example.test/login"
    assert extract_url("ssh://host.example.test", "No web page") is None


def test_default_opener_prefers_chrome_when_installed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_chrome = tmp_path / "chrome.exe"
    fake_chrome.write_bytes(b"")
    monkeypatch.setattr(actions, "chrome_executable", lambda: fake_chrome)
    launched: list[list[str]] = []
    monkeypatch.setattr(actions.subprocess, "Popen", launched.append)

    actions.default_opener()("https://console.example.test")

    assert launched == [[str(fake_chrome), "https://console.example.test"]]


def test_default_opener_falls_back_to_system_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "chrome_executable", lambda: None)
    opened: list[str] = []
    monkeypatch.setattr(actions.webbrowser, "open", opened.append)

    actions.default_opener()("https://console.example.test")

    assert opened == ["https://console.example.test"]


@windows_only
def test_connect_ssh_launches_system_client_in_new_console(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh.exe"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    launched: list[tuple] = []
    monkeypatch.setattr(actions.subprocess, "Popen", lambda command, **kwargs: launched.append((command, kwargs)))

    actions.connect_ssh("192.168.1.101", "root")

    command, kwargs = launched[0]
    assert command == [str(fake_ssh), "-o", "StrictHostKeyChecking=accept-new", "root@192.168.1.101"]
    assert kwargs["creationflags"] == actions.subprocess.CREATE_NEW_CONSOLE


def test_connect_ssh_without_username_targets_bare_host(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh.exe"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    launched: list[list[str]] = []

    actions.connect_ssh("192.168.1.101", "  ", launcher=lambda command, env: launched.append(command))

    assert launched == [[str(fake_ssh), "-o", "StrictHostKeyChecking=accept-new", "192.168.1.101"]]


def test_connect_ssh_accepts_injected_launcher(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh.exe"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    captured: list[tuple] = []

    actions.connect_ssh("10.0.0.5", "root", launcher=lambda command, env: captured.append((command, env)))

    assert captured == [([str(fake_ssh), "-o", "StrictHostKeyChecking=accept-new", "root@10.0.0.5"], None)]


@windows_only
def test_connect_ssh_with_password_uses_bundled_askpass_helper(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh.exe"
    fake_ssh.write_bytes(b"")
    fake_helper = tmp_path / "keeper-askpass.exe"
    fake_helper.write_bytes(b"MZ")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    monkeypatch.setattr(actions, "askpass_executable", lambda: fake_helper)
    captured: list[tuple] = []

    actions.connect_ssh("10.0.0.5", "root", password="p@ss&w|ord^<>%", launcher=lambda command, env: captured.append((command, env)))

    (command, env), = captured
    assert env["KEEPER_SSH_PASSWORD"] == "p@ss&w|ord^<>%"
    assert env["SSH_ASKPASS"] == str(fake_helper)
    assert env["SSH_ASKPASS_REQUIRE"] == "force"


@windows_only
def test_connect_ssh_without_helper_falls_back_to_generated_script(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh.exe"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    monkeypatch.setattr(actions, "askpass_executable", lambda: None)
    captured: list[tuple] = []
    timers: list[FakeTimer] = []

    def fake_timer(*args, **kwargs) -> FakeTimer:
        timers.append(timer := FakeTimer(*args, **kwargs))
        return timer

    monkeypatch.setattr(actions.threading, "Timer", fake_timer)

    actions.connect_ssh("10.0.0.5", "root", password="p@ss&w", launcher=lambda command, env: captured.append((command, env)))

    (command, env), = captured
    helper = Path(env["SSH_ASKPASS"])
    assert helper.suffix == ".bat" and helper.exists()
    # The helper merely echoes the environment variable — it holds no secret.
    content = helper.read_text()
    assert "p@ss&w" not in content
    assert "KEEPER_SSH_PASSWORD" in content
    assert timers  # the temporary helper is scheduled for deletion
    helper.unlink()


def test_connect_ssh_missing_client_raises_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "ssh_executable", lambda: None)

    with pytest.raises(ValueError, match="OpenSSH"):
        actions.connect_ssh("192.168.1.101", "root")


def test_connect_ssh_without_host_raises() -> None:
    with pytest.raises(ValueError, match="没有保存 IP"):
        actions.connect_ssh("   ", "root")


@windows_only
def test_connect_rdp_launches_mstsc(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_mstsc = tmp_path / "mstsc.exe"
    fake_mstsc.write_bytes(b"")
    monkeypatch.setattr(actions, "rdp_executable", lambda: fake_mstsc)
    launched: list[list[str]] = []
    monkeypatch.setattr(actions.subprocess, "Popen", lambda command, **kwargs: launched.append(command))

    actions.connect_rdp("192.168.1.101")

    assert launched == [[str(fake_mstsc), "/v:192.168.1.101"]]


def test_connect_rdp_without_host_raises() -> None:
    with pytest.raises(ValueError, match="没有保存 IP"):
        actions.connect_rdp("")


@windows_only
def test_connect_rdp_with_credentials_generates_autologin_rdp_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_mstsc = tmp_path / "mstsc.exe"
    fake_mstsc.write_bytes(b"")
    monkeypatch.setattr(actions, "rdp_executable", lambda: fake_mstsc)
    monkeypatch.setattr(actions, "_dpapi_protect", lambda data: "0123abcd")
    cleaned: list[Path] = []
    monkeypatch.setattr(actions, "_schedule_cleanup", lambda path, delay=60.0: cleaned.append(path))
    launched: list[list[str]] = []

    actions.connect_rdp("192.168.1.101", "administrator", "sekrit pw", launcher=lambda command, env: launched.append(command))

    (command,) = launched
    assert command[0] == str(fake_mstsc)
    rdp = Path(command[1])
    assert rdp.suffix == ".rdp" and rdp.exists()
    content = rdp.read_text(encoding="utf-16")
    assert "full address:s:192.168.1.101" in content
    assert "username:s:administrator" in content
    assert "password 51:b:0123abcd" in content
    assert "prompt for credentials:i:0" in content
    assert "smart sizing:i:1" in content
    # No hardcoded screen mode/size: the session inherits the user's mstsc defaults.
    assert "screen mode" not in content and "desktopwidth" not in content
    assert cleaned == [rdp]
    rdp.unlink()


@windows_only
def test_connect_rdp_without_password_uses_plain_v_switch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_mstsc = tmp_path / "mstsc.exe"
    fake_mstsc.write_bytes(b"")
    monkeypatch.setattr(actions, "rdp_executable", lambda: fake_mstsc)
    generated: list[tuple] = []
    monkeypatch.setattr(actions, "_generate_rdp_file", lambda *args: generated.append(args))
    launched: list[list[str]] = []

    actions.connect_rdp("192.168.1.101", launcher=lambda command, env: launched.append(command))

    assert generated == []
    assert launched == [[str(fake_mstsc), "/v:192.168.1.101"]]


def _dpapi_unprotect(hex_blob: str) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    raw = bytes.fromhex(hex_blob)
    buf = ctypes.create_string_buffer(raw, len(raw))
    in_blob = Blob(len(raw), ctypes.cast(buf, ctypes.c_void_p))
    out_blob = Blob()
    assert ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
    return data


@windows_only
def test_dpapi_protect_roundtrip() -> None:
    password = "p@ss w&rd 中文"
    blob = actions._dpapi_protect(password.encode("utf-16-le"))
    assert blob and blob != password
    assert _dpapi_unprotect(blob).decode("utf-16-le") == password


@windows_only
def test_askpass_helper_is_bundled_with_the_app() -> None:
    helper = actions.askpass_executable()
    assert helper is not None and helper.name == "keeper-askpass.exe" and helper.exists()


def test_macos_ssh_launcher_opens_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    launched: list[tuple] = []
    monkeypatch.setattr(actions.subprocess, "Popen", lambda command, **kwargs: launched.append((command, kwargs)))

    actions.default_ssh_launcher(["/usr/bin/ssh", "root@192.168.1.101"])

    (command, kwargs), = launched
    assert command[:2] == ["/usr/bin/osascript", "-e"]
    assert "do script \"/usr/bin/ssh root@192.168.1.101\"" in command[2]
    assert "env" not in kwargs


def test_macos_ssh_launcher_inlines_only_the_askpass_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terminal.app inherits nothing from us, so the settings ride along inline."""
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    launched: list[list[str]] = []
    monkeypatch.setattr(actions.subprocess, "Popen", lambda command, **kwargs: launched.append(command))

    actions.default_ssh_launcher(
        ["/usr/bin/ssh", "root@192.168.1.101"],
        {"SSH_ASKPASS": "/tmp/keeper-ssh-x/askpass.sh", "SSH_ASKPASS_REQUIRE": "force", "KEEPER_SSH_PASSWORD": "s3cret"},
    )

    (command,) = launched
    assert "SSH_ASKPASS=/tmp/keeper-ssh-x/askpass.sh" in command[2]
    assert "SSH_ASKPASS_REQUIRE=force" in command[2]
    # The allowlist keeps anything secret-bearing out of the command line.
    assert "s3cret" not in command[2] and "KEEPER_SSH_PASSWORD" not in command[2]


def test_macos_ssh_without_netcat_skips_autofill(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    monkeypatch.setattr(actions, "netcat_executable", lambda: None)
    captured: list[tuple] = []

    actions.connect_ssh("10.0.0.5", "root", password="secret", launcher=lambda command, env: captured.append((command, env)))

    (command, env), = captured
    assert command[0] == str(fake_ssh)
    assert env is None


@macos_only
def test_macos_ssh_autofills_password_over_a_private_socket(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    password = "p@ss w&rd 中文"
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    cleaned: list[Path] = []
    monkeypatch.setattr(actions, "_schedule_directory_cleanup", lambda path, delay=120.0: cleaned.append(path))
    captured: list[tuple] = []

    actions.connect_ssh("10.0.0.5", "root", password=password, launcher=lambda command, env: captured.append((command, env)))

    (command, env), = captured
    assert env["SSH_ASKPASS_REQUIRE"] == "force"
    assert all(password not in part for part in command)

    helper = Path(env["SSH_ASKPASS"])
    directory = cleaned[0]
    try:
        assert helper.parent == directory and helper.exists() and os.access(helper, os.X_OK)
        assert oct(directory.stat().st_mode & 0o777) == "0o700"
        # The helper only carries a token and a socket path - never the secret.
        assert password not in helper.read_text(encoding="utf-8")
        assert "-U" in helper.read_text(encoding="utf-8")

        socket_path = directory / "askpass.sock"
        assert socket_path.exists()
        assert oct(socket_path.stat().st_mode & 0o777) == "0o600"

        # Every prompt ssh might raise is answered, then the socket retires.
        for _ in range(actions.MACOS_ASKPASS_ATTEMPTS):
            served = subprocess.run([str(helper)], capture_output=True, timeout=15)
            assert served.stdout.decode("utf-8") == password
        for _ in range(50):
            if not socket_path.exists():
                break
            time.sleep(0.1)
        assert not socket_path.exists()
    finally:
        shutil.rmtree(directory, ignore_errors=True)
def test_macos_rdp_uses_windows_app_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    monkeypatch.setattr(actions, "rdp_executable", lambda: Path("/usr/bin/open"))
    cleaned: list[Path] = []
    monkeypatch.setattr(actions, "_schedule_cleanup", lambda path, delay=60.0: cleaned.append(path))
    captured: list[list[str]] = []

    actions.connect_rdp("192.168.1.101", "administrator", "secret", launcher=lambda command, env: captured.append(command))

    (command,) = captured
    # Windows App 11.x rejects rdp:// outright, so the session is started by
    # handing it a temporary .rdp file instead.
    assert command[:3] == [str(Path("/usr/bin/open")), "-b", actions.WINDOWS_APP_BUNDLE_ID]
    rdp = Path(command[3])
    assert rdp.suffix == ".rdp" and rdp.exists()
    content = rdp.read_text(encoding="utf-16")
    assert "full address:s:192.168.1.101" in content
    assert "username:s:administrator" in content
    assert "prompt for credentials:i:0" in content
    # macOS has no DPAPI: the password must never reach the file.
    assert "secret" not in content and "password 51:b:" not in content
    assert cleaned == [rdp]
    rdp.unlink()


def test_macos_rdp_without_temp_file_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    monkeypatch.setattr(actions, "rdp_executable", lambda: Path("/usr/bin/open"))
    monkeypatch.setattr(actions, "_generate_macos_rdp_file", lambda *args: None)

    with pytest.raises(ValueError, match="临时 .rdp"):
        actions.connect_rdp("192.168.1.101", "administrator", "secret", launcher=lambda command, env: None)


def test_macos_rdp_missing_windows_app_raises_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")

    def fail(*args, **kwargs) -> None:
        raise subprocess.CalledProcessError(1, ["open"])

    monkeypatch.setattr(actions.subprocess, "run", fail)

    with pytest.raises(ValueError, match="Windows App"):
        actions.default_rdp_launcher(["/usr/bin/open", "-b", actions.WINDOWS_APP_BUNDLE_ID, "/tmp/keeper-rdp-x.rdp"])


def test_dpapi_protect_returns_none_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")

    assert actions._dpapi_protect(b"secret") is None


def test_connect_ssh_passes_a_non_default_port(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)
    launched: list[list[str]] = []

    actions.connect_ssh("192.168.1.101:2222", "root", launcher=lambda command, env: launched.append(command))

    assert launched == [[str(fake_ssh), "-o", "StrictHostKeyChecking=accept-new", "-p", "2222", "root@192.168.1.101"]]


def test_connect_ssh_reports_a_malformed_port(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_bytes(b"")
    monkeypatch.setattr(actions, "ssh_executable", lambda: fake_ssh)

    with pytest.raises(ValueError, match="端口必须是数字"):
        actions.connect_ssh("192.168.1.101:ssh", "root", launcher=lambda command, env: None)


@windows_only
def test_connect_rdp_carries_the_port_to_mstsc(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake_mstsc = tmp_path / "mstsc.exe"
    fake_mstsc.write_bytes(b"")
    monkeypatch.setattr(actions, "rdp_executable", lambda: fake_mstsc)
    launched: list[list[str]] = []

    actions.connect_rdp("192.168.1.101:3390", launcher=lambda command, env: launched.append(command))

    assert launched == [[str(fake_mstsc), "/v:192.168.1.101:3390"]]


def test_macos_rdp_carries_the_port_into_the_rdp_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    monkeypatch.setattr(actions, "rdp_executable", lambda: Path("/usr/bin/open"))
    monkeypatch.setattr(actions, "_schedule_cleanup", lambda path, delay=60.0: None)
    captured: list[list[str]] = []

    actions.connect_rdp("192.168.1.101:3390", "administrator", "secret", launcher=lambda command, env: captured.append(command))

    (command,) = captured
    content = Path(command[3]).read_text(encoding="utf-16")
    assert "full address:s:192.168.1.101:3390" in content
    assert "secret" not in content
    Path(command[3]).unlink()


@macos_only
def test_concealed_clipboard_keeps_the_secret_out_of_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    class Done:
        returncode = 0

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Done()

    monkeypatch.setattr(actions.subprocess, "run", fake_run)

    assert actions.set_concealed_clipboard("p@ss 中文 🔒") is True

    (command, kwargs), = calls
    assert command[:3] == ["/usr/bin/osascript", "-l", "JavaScript"]
    assert kwargs["env"]["KEEPER_CLIP_TEXT"] == "p@ss 中文 🔒"
    # argv is world readable through ps, so the secret must never appear there.
    assert all("p@ss" not in str(part) for part in command)
    assert "org.nspasteboard.ConcealedType" in command[-1]


def test_concealed_clipboard_is_skipped_off_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "win32")
    assert actions.set_concealed_clipboard("secret") is False


def test_concealed_clipboard_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    monkeypatch.setattr(actions.Path, "exists", lambda self: True)

    def refuse(*args, **kwargs):
        raise OSError("osascript unavailable")

    monkeypatch.setattr(actions.subprocess, "run", refuse)
    assert actions.set_concealed_clipboard("secret") is False


@macos_only
def test_system_idle_seconds_reports_elapsed_input_time() -> None:
    idle = actions.system_idle_seconds()
    assert idle is not None and idle >= 0.0
