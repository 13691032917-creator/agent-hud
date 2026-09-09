from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
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


def _parse_money(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip() or "0")
        except ValueError:
            return None
    return None


def _load_mimo_key_from_mimocode() -> str:
    """Best-effort read of Xiaomi MiMo API key from local mimocode config."""
    candidates = []
    home = Path.home()
    candidates.append(home / ".config" / "mimocode" / "mimocode.jsonc")
    candidates.append(Path.home() / "AppData" / "Roaming" / "Xiaomi MiMo" / "mimocode.jsonc")
    import json as _json
    import re as _re
    for path in candidates:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        # strip // comments for jsonc
        raw = _re.sub(r"^\s*//.*$", "", raw, flags=_re.M)
        try:
            data = _json.loads(raw)
            key = (
                _dig(data, "provider.xiaomi-mimo-api.options.apiKey")
                or _dig(data, "providers.xiaomi-mimo-api.options.apiKey")
            )
            if isinstance(key, str) and key.startswith("sk-"):
                return key
        except Exception:
            m = _re.search(r'"apiKey"\s*:\s*"(sk-[^"]+)"', raw)
            if m:
                return m.group(1)
    return ""


def fetch_mimo(provider: dict[str, Any]) -> tuple[float | None, str]:
    """Xiaomi MiMo.

    Public API currently has no stable balance endpoint. Strategy:
    1. Use provider api_key, or auto-import from ~/.config/mimocode/mimocode.jsonc
    2. Validate key via GET /v1/models
    3. If provider has manual `amount`, return that (user-maintained)
    4. Otherwise return None with a clear note
    """
    from pathlib import Path as _Path  # local import if not already

    key = str(provider.get("api_key") or "").strip()
    if not key:
        key = _load_mimo_key_from_mimocode()
    amount = _parse_money(provider.get("amount"))
    base = (provider.get("base_url") or "https://api.xiaomimimo.com").rstrip("/")
    if base.endswith("/v1"):
        root = base[:-3].rstrip("/")
    else:
        root = base

    if not key:
        return amount, "MiMo 未配置 Key（可自动读 mimocode.jsonc）"

    # validate key
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    models_ok = False
    model_note = ""
    try:
        data = _http_json(f"{root}/v1/models", headers)
        ids = [str(x.get("id") or "") for x in (data.get("data") or []) if isinstance(x, dict)]
        models_ok = bool(ids)
        model_note = f"{len(ids)} models"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return amount, f"MiMo Key 无效 HTTP {exc.code}"
        model_note = f"models HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        model_note = f"models error: {exc}"

    # try a few balance paths (in case they add later)
    for path in (
        f"{root}/v1/dashboard/billing/subscription",
        f"{root}/v1/user/balance",
        f"{root}/v1/billing/balance",
        f"{root}/v1/account/balance",
    ):
        try:
            data = _http_json(path, headers)
        except Exception:
            continue
        for keypath in ("balance", "data.balance", "total_balance", "quota", "amount"):
            val = _parse_money(_dig(data, keypath))
            if val is not None:
                return round(val, 4), f"MiMo {keypath}"

    if amount is not None:
        note = "MiMo 手动余额"
        if models_ok:
            note += f"（API Key 有效，{model_note}）"
        else:
            note += f"（{model_note or '无余额接口'}）"
        return round(float(amount), 4), note

    if models_ok:
        return None, f"MiMo API Key 有效（{model_note}），官方暂无余额接口；请在 API 窗填「余额金额」"
    return None, f"MiMo 余额不可用（{model_note or 'unknown'}）"


def fetch_deepseek(api_key: str) -> tuple[float | None, str]:
    """DeepSeek official balance.

    Documented shape:
    {
      "is_available": true,
      "balance_infos": [
        {"currency": "CNY", "total_balance": "1.23", "granted_balance": "...", "topped_up_balance": "..."}
      ]
    }
    """
    if not api_key:
        return None, "empty api_key"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_note = "DeepSeek balance unavailable"
    for url in (
        "https://api.deepseek.com/user/balance",
        "https://api.deepseek.com/v1/user/balance",
    ):
        try:
            data = _http_json(url, headers)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:160]
            except Exception:
                pass
            last_note = f"HTTP {exc.code}: {body or exc.reason}"
            continue
        except Exception as exc:  # noqa: BLE001
            last_note = f"request error: {exc}"
            continue
        if not isinstance(data, dict):
            last_note = "invalid json"
            continue

        infos = data.get("balance_infos")
        if not isinstance(infos, list):
            nested = _dig(data, "data.balance_infos")
            if isinstance(nested, list):
                infos = nested
            elif isinstance(_dig(data, "data"), dict) and "balance_infos" not in (data.get("data") or {}):
                # maybe flat legacy fields under data
                infos = [data.get("data") or {}]
            else:
                infos = []

        preferred = None
        for row in infos:
            if not isinstance(row, dict):
                continue
            cur = str(row.get("currency") or "CNY").upper()
            total = _parse_money(row.get("total_balance"))
            if total is None:
                granted = _parse_money(row.get("granted_balance")) or 0.0
                topped = _parse_money(row.get("topped_up_balance")) or 0.0
                total = granted + topped
            if total is None:
                continue
            item = (cur, total, row)
            if preferred is None:
                preferred = item
            if cur == "CNY":
                preferred = item
                break

        if preferred:
            cur, total, row = preferred
            note = f"DeepSeek {cur} total_balance"
            if data.get("is_available") is False:
                note += " (is_available=false)"
            return round(float(total), 4), note

        # fallback top-level numbers
        for key in ("total_balance", "balance", "data.balance"):
            val = _parse_money(_dig(data, key))
            if val is not None:
                return round(val, 4), f"DeepSeek {key}"

        last_note = f"no balance field: keys={list(data.keys())[:8]}"
    return None, last_note


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
    "mimo": lambda p: fetch_mimo(p),
    "xiaomi-mimo": lambda p: fetch_mimo(p),
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
        for item in items:
            if item.amount is not None:
                return item
        return items[0] if items else None
    m = model.lower()
    # exact model match first
    for item in items:
        if item.model.lower() == m:
            return item
    # token in model name (mimo-v2.5-pro / deepseek-v4-flash)
    for item in items:
        name = (item.provider_name or "").lower()
        pid = (item.provider_id or "").lower()
        model_in_item = (item.model or "").lower()
        if name and (name in m or m.startswith(name) or name.replace(" ", "") in m):
            if item.amount is not None or model_in_item in {"(provider balance)", "*", ""}:
                return item
        if pid and pid in m:
            if item.amount is not None:
                return item
        if model_in_item and model_in_item in m:
            if item.amount is not None:
                return item
    # provider-wide placeholder
    for item in items:
        if item.model in {"(provider balance)", "*", ""} and item.provider_name:
            if item.provider_name.lower() in m or any(
                token and token in m for token in item.provider_name.lower().split()
            ):
                return item
    for item in items:
        pid = (item.provider_id or "").lower()
        if pid and pid in m and item.amount is not None:
            return item
    return None
    # provider-wide placeholder
    for item in items:
        if item.model in {"(provider balance)", "*", ""} and item.provider_name:
            if item.provider_name.lower() in m or any(
                token and token in m for token in item.provider_name.lower().split()
            ):
                return item
    # any enabled amount for that provider id prefix
    for item in items:
        pid = (item.provider_id or "").lower()
        if pid and pid in m and item.amount is not None:
            return item
    return None
