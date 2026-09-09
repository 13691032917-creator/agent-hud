from __future__ import annotations

import copy
from typing import Any

from .config import load_config, save_config

PROVIDER_TYPES = [
    ("deepseek", "DeepSeek 官方"),
    ("openai", "OpenAI"),
    ("openrouter", "OpenRouter"),
    ("moonshot", "Moonshot"),
    ("siliconflow", "SiliconFlow"),
    ("openai_compatible", "OpenAI 兼容网关"),
    ("new_api", "new-api / one-api 中转"),
    ("one_api", "one-api 中转"),
    ("anthropic", "Anthropic 兼容"),
    ("manual", "手动余额（无网络）"),
]


def normalize_provider(raw: dict[str, Any]) -> dict[str, Any]:
    p = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    p.setdefault("id", "")
    p.setdefault("name", "")
    p.setdefault("type", "openai_compatible")
    p.setdefault("api_key", "")
    p.setdefault("access_token", "")
    p.setdefault("base_url", "")
    p.setdefault("models", [])
    p.setdefault("enabled", False)
    p.setdefault("currency", "")
    p.setdefault("note", "")
    cn_types = {"deepseek", "moonshot", "siliconflow", "new_api", "one_api", "zhipu", "qwen", "mimo", "xiaomi-mimo"}
    if p.get("type") in cn_types:
        p["currency"] = "CNY"
    if not p.get("currency"):
        p["currency"] = "CNY"
    p["currency"] = str(p["currency"]).upper().replace("RMB", "CNY")
    if isinstance(p.get("models"), str):
        p["models"] = [m.strip() for m in p["models"].split(",") if m.strip()]
    if not isinstance(p.get("models"), list):
        p["models"] = []
    p["models"] = [str(m).strip() for m in p["models"] if str(m).strip()]
    if p.get("amount") is not None:
        try:
            p["amount"] = float(p["amount"])
        except (TypeError, ValueError):
            p["amount"] = None
    return p


def upsert_provider(cfg: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    provider = normalize_provider(provider)
    if not provider["id"]:
        provider["id"] = (provider["name"] or provider["type"] or "provider").lower().replace(" ", "-")
    providers = list(cfg.get("providers") or [])
    out: list[dict[str, Any]] = []
    replaced = False
    for item in providers:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == provider["id"]:
            out.append(provider)
            replaced = True
        else:
            out.append(normalize_provider(item))
    if not replaced:
        out.append(provider)
    cfg = {**cfg, "providers": out}
    return cfg


def remove_provider(cfg: dict[str, Any], provider_id: str) -> dict[str, Any]:
    providers = [normalize_provider(p) for p in (cfg.get("providers") or []) if isinstance(p, dict)]
    cfg = {**cfg, "providers": [p for p in providers if p.get("id") != provider_id]}
    return cfg


def blank_provider() -> dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "type": "deepseek",
        "api_key": "",
        "access_token": "",
        "base_url": "",
        "models": [],
        "enabled": True,
        "currency": "USD",
        "note": "",
    }


def models_to_text(models: list[str] | str | None) -> str:
    if isinstance(models, str):
        return models
    return ", ".join(models or [])


def text_to_models(text: str) -> list[str]:
    return [m.strip() for m in (text or "").replace("，", ",").split(",") if m.strip()]


def save_providers(cfg: dict[str, Any], providers: list[dict[str, Any]]) -> Any:
    cfg = {**cfg, "providers": [normalize_provider(p) for p in providers]}
    return save_config(cfg)


def load_providers() -> list[dict[str, Any]]:
    cfg = load_config()
    return [normalize_provider(p) for p in (cfg.get("providers") or []) if isinstance(p, dict)]
