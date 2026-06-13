"""Aicademy CLI Configuration"""

import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── API Config ────────────────────────────────────────────────────────────────
API_BASE_URL = os.environ.get("AICADEMY_API_URL", "https://www.aicademy.ac")

# ─── Config File ───────────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".aicademy"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config() -> dict:
    """Load config from ~/.aicademy/config.json"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Save config to ~/.aicademy/config.json"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_token() -> str | None:
    """Return the stored CLI token, or None if not logged in."""
    return get_config().get("token")


def get_active_session() -> dict | None:
    """Return the locally-cached active session info, or None."""
    return get_config().get("active_session")


def set_active_session(session: dict | None) -> None:
    """Persist (or clear) the active session in config."""
    cfg = get_config()
    if session is None:
        cfg.pop("active_session", None)
    else:
        cfg["active_session"] = session
    save_config(cfg)
