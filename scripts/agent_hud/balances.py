from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .config import load_config
from .paths import balances_path


@dataclass
class BalanceItem:
    provider_id: str
    provider_name: str
    model: str
    amount: float | None
    currency: str
    raw_note: str = ""
    updated_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _http_json(url: str, headers: dict[str, str], timeout: float = 15.0) -> Any:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def _dig(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def fetch_openai_like(base_url: str, api_key: str) -> tuple[float | None, str]:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # OpenRouter credits
    if "openrouter" in base.lower():
        data = _http_json(f"{base}/api/v1/credits", headers)
        total = _dig(data, "data.total_credits") or _dig(data, "data.total_usage")
        if total is not None:
            usage = float(_dig(data, "data.total_usage") or 0)
            return round(float(total) - usage, 4), "OpenRouter credits-usage"
    # Generic OpenAI-compatible billing (many gateways)
    for path in (
        f"{base}/v1/dashboard/billing/subscription",
        f"{base}/dashboard/billing/subscription",
        f"{base}/api/user/self",
        f"{base}/v1/dashboard/billing/credit_grants",
    ):
        try:
            data = _http_json(path, headers)
        except Exception:
            continue
        for key in (
            "hard_limit_usd",
            "quota",
            "balance",
            "data.quota",
            "data.balance",
            "total_quota",
        ):
            val = _dig(data, key)
            if isinstance(val, (int, float)):
                # new-api quota is often in 500000 = $1
                if "quota" in key and val > 10000:
                    return round(float(val) / 500000.0, 4), f"quota:{key}"
                return round(float(val), 4), key
    return None, "no billing endpoint matched"


def fetch_deepseek(api_key: str) -> tuple[float | None, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    data = _http_json("https://api.deepseek.com/user/balance", headers)
    info = _dig(data, "data") or {}
    # is_available + balance grants
    total = 0.0
    granted = info.get("granted_balance")
    topped = info.get("topped_up_balance")
    if isinstance(granted, (int, float)):
        total += float(granted)
    if isinstance(topped, (int, float)):
        total += float(topped)
    if total or granted is not None:
        return round(total, 4), "DeepSeek balance"
    return None, "DeepSeek balance unavailable"


def fetch_anthropic_like(base_url: str, api_key: str) -> tuple[float | None, str]:
    base = (base_url or "https://api.anthropic.com").rstrip("/")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Authorization": f"Bearer {api_key}",
    }
    for path in (
        f"{base}/api/oauth/usage",
        f"{base}/v1/dashboard/billing/subscription",
        f"{base}/api/user/self",
    ):
        try:
            data = _http_json(path, headers)
        except Exception:
            continue
        for key in ("balance", "hard_limit_usd", "quota", "data.balance"):
            val = _dig(data, key)
            if isinstance(val, (int, float)):
                return round(float(val), 4), key
    return None, "Anthropic balance endpoint unavailable"


def fetch_moonshot(api_key: str, base_url: str = "https://api.moonshot.cn") -> tuple[float | None, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = _http_json(f"{base_url.rstrip('/')}/v1/users/me/balance", headers)
    val = _dig(data, "available_balance")
    if isinstance(val, (int, float)):
        return round(float(val), 4), "Moonshot available_balance"
    return None, "Moonshot balance unavailable"


def fetch_siliconflow(api_key: str) -> tuple[float | None, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = _http_json("https://api.siliconflow.cn/v1/user/info", headers)
    val = _dig(data, "data.balance") or _dig(data, "balance")
    if isinstance(val, (int, float)):
        return round(float(val), 4), "SiliconFlow balance"
    return None, "SiliconFlow balance unavailable"


FETCHERS: dict[str, Callable[..., tuple[float | None, str]]] = {
    "openai": lambda p: fetch_openai_like(p.get("base_url") or "https://api.openai.com", p.get("api_key") or ""),
    "openai_compatible": lambda p: fetch_openai_like(p.get("base_url") or "", p.get("api_key") or ""),
    "new_api": lambda p: fetch_openai_like(p.get("base_url") or "", p.get("access_token") or p.get("api_key") or ""),
    "one_api": lambda p: fetch_openai_like(p.get("base_url") or "", p.get("access_token") or p.get("api_key") or ""),
    "openrouter": lambda p: fetch_openai_like("https://openrouter.ai", p.get("api_key") or ""),
    "deepseek": lambda p: fetch_deepseek(p.get("api_key") or ""),
    "anthropic": lambda p: fetch_anthropic_like(p.get("base_url") or "", p.get("api_key") or ""),
    "moonshot": lambda p: fetch_moonshot(p.get("api_key") or "", p.get("base_url") or "https://api.moonshot.cn"),
    "siliconflow": lambda p: fetch_siliconflow(p.get("api_key") or ""),
    "manual": lambda p: (
        float(p["amount"]) if isinstance(p.get("amount"), (int, float)) else None,
        p.get("note") or "manual",
    ),
}


def _provider_label(provider: dict[str, Any]) -> str:
    return str(provider.get("name") or provider.get("id") or provider.get("type") or "unknown")


def refresh_balances(force: bool = False) -> list[BalanceItem]:
    cfg = load_config()
    providers = cfg.get("providers") or []
    now = _now()
    items: list[BalanceItem] = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if provider.get("enabled") is False:
            continue
        ptype = str(provider.get("type") or "openai_compatible").lower()
        pid = str(provider.get("id") or ptype)
        pname = _provider_label(provider)
        models = provider.get("models") or []
        if isinstance(models, str):
            models = [models]
        fetch = FETCHERS.get(ptype)
        amount: float | None = None
        note = f"unsupported type: {ptype}"
        if fetch is not None:
            try:
                amount, note = fetch(provider)
            except urllib.error.HTTPError as exc:
                note = f"HTTP {exc.code}: {exc.reason}"
            except Exception as exc:  # noqa: BLE001 — surface any provider error on HUD
                note = f"error: {exc}"
        if not models:
            models = ["(provider balance)"]
        for model in models:
            items.append(
                BalanceItem(
                    provider_id=pid,
                    provider_name=pname,
                    model=str(model),
                    amount=amount,
                    currency=str(provider.get("currency") or "USD"),
                    raw_note=note,
                    updated_at=now,
                )
            )
    payload = {"updated_at": now, "items": [asdict(i) for i in items]}
    path = balances_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return items


def load_balances(max_age_sec: float = 3600.0) -> list[BalanceItem]:
    path = balances_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items") or []
        updated = data.get("updated_at") or ""
        if updated:
            try:
                ts = datetime.fromisoformat(updated).timestamp()
                if time.time() - ts > max_age_sec:
                    # still return stale data; caller may refresh in background
                    pass
            except ValueError:
                pass
        out: list[BalanceItem] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            out.append(
                BalanceItem(
                    provider_id=str(row.get("provider_id") or ""),
                    provider_name=str(row.get("provider_name") or ""),
                    model=str(row.get("model") or ""),
                    amount=row.get("amount"),
                    currency=str(row.get("currency") or "USD"),
                    raw_note=str(row.get("raw_note") or ""),
                    updated_at=str(row.get("updated_at") or ""),
                )
            )
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def match_balance_for_model(model: str, items: list[BalanceItem]) -> BalanceItem | None:
    if not model:
        return None
    m = model.lower()
    # exact model match first
    for item in items:
        if item.model.lower() == m:
            return item
    # provider-wide placeholder
    for item in items:
        if item.model in {"(provider balance)", "*", ""} and item.provider_name:
            if item.provider_name.lower() in m or any(
                token and token in m for token in item.provider_name.lower().split()
            ):
                return item
    return None
