"""Aicademy CLI Configuration"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _get_api_base_url() -> str:
    """Return the validated API base URL.

    Rejects non-HTTPS URLs unless the host is localhost/127.0.0.1.
    Raises RuntimeError for invalid or insecure configurations.
    """
    raw = os.environ.get("AICADEMY_API_URL", "https://www.aicademy.ac").strip()
    if not raw:
        return "https://www.aicademy.ac"

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"AICADEMY_API_URL is not a valid URL: {raw!r}")

    allowed_insecure_hosts = {"localhost", "127.0.0.1"}
    host = parsed.hostname or ""
    if parsed.scheme != "https" and host not in allowed_insecure_hosts:
        raise RuntimeError(
            f"Insecure API URL ({raw!r}). Only HTTPS is allowed outside localhost. "
            "Set AICADEMY_API_URL to an https:// URL."
        )

    return raw.rstrip("/")


# ─── API Config ────────────────────────────────────────────────────────────────
API_BASE_URL = _get_api_base_url()

# ─── Config File ───────────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".aicademy"
CONFIG_FILE = CONFIG_DIR / "config.json"
KUBECONFIG_PATH = CONFIG_DIR / "kubeconfig-aicademy-session"



def get_config() -> dict[str, Any]:
    """Load config from ~/.aicademy/config.json"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _set_unix_permissions(path: Path, mode: int) -> None:
    """Set file/directory permissions on Unix systems."""
    if sys.platform == "win32":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _set_windows_acl(path: Path) -> None:
    """Restrict file/directory access to the current user on Windows.

    This is best-effort: if the system cannot resolve the current user's SID
    or the icacls command fails, we silently continue so the CLI keeps working.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        # Look up the current user's SID string so we do not depend on the
        # account name format required by icacls.
        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)  # TOKEN_QUERY
        ):
            return

        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, 1, buf, size, ctypes.byref(size)
        ):
            kernel32.CloseHandle(token)
            return

        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_str = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(sid_str)):
            kernel32.CloseHandle(token)
            return

        user_sid = sid_str.value
        kernel32.LocalFree(sid_str)
        kernel32.CloseHandle(token)

        if not user_sid:
            return

        # Replace permissions with full control for the current user only,
        # removing inherited perms and Everyone/Builtin\Users.
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{user_sid}:(OI)(CI)F",
                "/remove",
                "*S-1-1-0",
                "*S-1-5-32-545",
            ],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def save_config(data: dict[str, Any]) -> None:
    """Save config to ~/.aicademy/config.json atomically with restrictive permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _set_unix_permissions(CONFIG_DIR, 0o700)
    _set_windows_acl(CONFIG_DIR)

    serialized = json.dumps(data, indent=2)
    # Atomic write: create temp file in same directory, close it, then rename.
    fd, temp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
    os.close(fd)
    temp_file = Path(temp_path)
    try:
        temp_file.write_text(serialized, encoding="utf-8")
        _set_unix_permissions(temp_file, 0o600)
        _set_windows_acl(temp_file)
        temp_file.replace(CONFIG_FILE)
    except Exception:
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass
        raise


_KEYRING_SERVICE = "aicademy-cli"
_KEYRING_USERNAME = "token"

# Token storage prefers the OS credential store (Windows Credential Manager /
# macOS Keychain / Linux Secret Service) — that's real OS-level access
# control, unlike a file on disk which any process running as the same user
# can read. `keyring` is a hard dependency, but the *backend* it finds at
# runtime is environment-dependent: headless Linux boxes, containers, and CI
# runners commonly have no Secret Service daemon running. In that case every
# keyring call raises, and we transparently fall back to the pre-existing
# 0600/ACL-restricted config file so the CLI never breaks — it just loses the
# OS-level protection on that specific machine.
#
# Broad `except Exception` here is deliberate: keyring backends can raise
# implementation-specific errors beyond `keyring.errors.KeyringError` (e.g. a
# missing optional backend dependency), and a credential-storage hiccup must
# never crash login/logout.


def _keyring_get_token() -> str | None:
    try:
        import keyring

        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:
        return None


def _keyring_set_token(token: str) -> bool:
    """Store in the OS keychain. Returns True on success."""
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, token)
        return True
    except Exception:
        return False


def _keyring_delete_token() -> None:
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:
        pass


def get_token() -> str | None:
    """Return the stored CLI token: OS keychain first, then the legacy
    config-file field (auto-migrating it into the keychain if found)."""
    token = _keyring_get_token()
    if token:
        return token

    cfg = get_config()
    legacy_token = cfg.get("token")
    if legacy_token and _keyring_set_token(legacy_token):
        cfg.pop("token", None)
        save_config(cfg)
    return legacy_token


def set_token(token: str) -> bool:
    """Store the CLI token. Returns True if it landed in the OS keychain,
    False if it fell back to the config file (no keychain backend available).
    """
    cfg = get_config()
    in_keychain = _keyring_set_token(token)
    if in_keychain:
        cfg.pop("token", None)  # never leave a stale plaintext copy behind
    else:
        cfg["token"] = token
    save_config(cfg)
    return in_keychain


def delete_token() -> None:
    """Remove the CLI token from both the keychain and the config file."""
    _keyring_delete_token()
    cfg = get_config()
    if "token" in cfg:
        cfg.pop("token", None)
        save_config(cfg)


def get_active_session() -> dict[str, Any] | None:
    """Return the locally-cached active session info, or None."""
    return get_config().get("active_session")


def set_active_session(session: dict[str, Any] | None) -> None:
    """Persist (or clear) the active session in config."""
    cfg = get_config()
    if session is None:
        cfg.pop("active_session", None)
    else:
        cfg["active_session"] = session
    save_config(cfg)


def get_user_config() -> dict[str, Any]:
    """Return user-level preferences."""
    return {}


def is_error_reporting_enabled() -> bool:
    """Whether unhandled-crash reports may be sent to the Aicademy backend.

    Opt-out, not opt-in: enabled unless the user has explicitly turned it off
    with `aicademy config error-reporting off`.
    """
    return get_config().get("error_reporting", True) is not False


def set_error_reporting(enabled: bool) -> None:
    cfg = get_config()
    cfg["error_reporting"] = enabled
    save_config(cfg)


def error_reporting_notice_shown() -> bool:
    return get_config().get("error_reporting_notice_shown", False) is True


def mark_error_reporting_notice_shown() -> None:
    cfg = get_config()
    cfg["error_reporting_notice_shown"] = True
    save_config(cfg)
