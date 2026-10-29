"""Resource paths are read-only; user data never belongs in the install folder."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def data_root() -> Path:
    override = os.environ.get("ULTRON_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError("ULTRON_DATA_DIR must be an absolute path")
        return path
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ULTRON"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/ULTRON"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ultron"


def config_path() -> Path:
    return data_root() / "config/api_keys.json"


def child_command() -> list[str]:
    """Keep the splash in one process and the full application in another."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--app"]
    return [sys.executable, str(resource_root() / "main.py")]
