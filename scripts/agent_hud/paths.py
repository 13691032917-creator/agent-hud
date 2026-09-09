from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        root = Path(base) / "agent-hud"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg) / "agent-hud" if xdg else Path.home() / ".local" / "share" / "agent-hud"
    (root / "sessions").mkdir(parents=True, exist_ok=True)
    return root


def sessions_dir() -> Path:
    return data_dir() / "sessions"


def config_path() -> Path:
    env = os.environ.get("AGENT_HUD_CONFIG")
    if env:
        return Path(env)
    return data_dir() / "config.json"


def balances_path() -> Path:
    return data_dir() / "balances.json"


def pid_path() -> Path:
    return data_dir() / "hud.pid"


def log_path() -> Path:
    return data_dir() / "hud.log"


def skill_scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_data_dir() -> None:
    data_dir()


def is_windows() -> bool:
    return sys.platform.startswith("win")
