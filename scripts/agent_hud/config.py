from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .paths import config_path, skill_scripts_dir


DEFAULT_CONFIG: dict[str, Any] = {
    "refresh_interval_sec": 3,
    "balance_refresh_sec": 300,
    "session_max_age_sec": 180,
    "opacity": 0.96,
    "always_on_top": True,
    "providers": [],
}


def example_config_path() -> Path:
    return skill_scripts_dir().parent / "config.example.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        example = example_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if example.exists():
            try:
                shutil.copyfile(example, path)
            except OSError:
                path.write_text(
                    json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        else:
            path.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root must be object")
    except (OSError, json.JSONDecodeError, ValueError):
        data = {}
    merged = {**DEFAULT_CONFIG, **data}
    if not isinstance(merged.get("providers"), list):
        merged["providers"] = []
    return merged


def save_config(cfg: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
