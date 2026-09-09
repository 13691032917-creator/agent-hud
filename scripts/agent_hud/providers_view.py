from __future__ import annotations

from typing import Any

from .balances import BalanceItem
from .config import load_config
from .daily import get_daily_summary
from .ids import truncate


def _provider_models(provider: dict[str, Any]) -> list[str]:
    models = provider.get("models") or []
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    return [str(m).strip() for m in models if str(m).strip()]


def _tokens_for_provider(provider: dict[str, Any], by_model: dict[str, int]) -> int:
    models = _provider_models(provider)
    pid = str(provider.get("id") or "").lower()
    name = str(provider.get("name") or "").lower()
    total = 0
    for model, n in by_model.items():
        m = str(model).lower()
        if any(m == x.lower() for x in models):
            total += int(n or 0)
        elif pid and pid in m:
            total += int(n or 0)
        elif name and name in m:
            total += int(n or 0)
    return total


def _best_balance_row(provider: dict[str, Any], items: list[BalanceItem]) -> BalanceItem | None:
    pid = str(provider.get("id") or "")
    name = str(provider.get("name") or "")
    models = _provider_models(provider)
    mine = [i for i in items if i.provider_id == pid or (name and i.provider_name == name)]
    if not mine:
        return None
    for m in models:
        for i in mine:
            if i.model.lower() == m.lower():
                return i
    funded = [i for i in mine if i.amount is not None]
    return funded[0] if funded else mine[0]


def build_provider_view() -> list[dict[str, Any]]:
    """User-facing list: each configured API vendor with balance + today tokens."""
    cfg = load_config()
    providers = [p for p in (cfg.get("providers") or []) if isinstance(p, dict) and p.get("enabled")]
    # also include any balance-only vendors if config missing
    items: list[BalanceItem] = []
    try:
        from .balances import load_balances

        items = load_balances(max_age_sec=86400)
    except Exception:
        items = []
    daily = get_daily_summary()
    by_model = daily.get("by_model") or {}
    day_total = int(daily.get("total_tokens") or 0)

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for p in providers:
        pid = str(p.get("id") or p.get("name") or "provider")
        if pid in seen:
            continue
        seen.add(pid)
        bal = _best_balance_row(p, items)
        tokens = _tokens_for_provider(p, by_model)
        # if model keys don't match, try provider name in by_model via balances note
        amount = bal.amount if bal else p.get("amount")
        if amount is None and p.get("amount") is not None:
            try:
                amount = float(p["amount"])
            except (TypeError, ValueError):
                amount = None
        currency = (bal.currency if bal else None) or p.get("currency") or "CNY"
        models = _provider_models(p)
        if not models and bal:
            models = [bal.model]
        rows.append(
            {
                "id": pid,
                "name": str(p.get("name") or pid),
                "type": str(p.get("type") or ""),
                "amount": amount,
                "currency": currency,
                "tokens_today": tokens,
                "day_total": day_total,
                "models": models,
                "model_label": truncate(models[0], 28) if models else "—",
                "note": (bal.raw_note if bal else "") or str(p.get("note") or ""),
                "api_key": bool(p.get("api_key") or p.get("access_token")),
            }
        )

    # balance rows not in config (shouldn't happen often)
    for item in items:
        if item.provider_id in seen:
            continue
        seen.add(item.provider_id)
        tokens = 0
        for m, n in by_model.items():
            if item.model and item.model.lower() in str(m).lower():
                tokens += int(n or 0)
        rows.append(
            {
                "id": item.provider_id,
                "name": item.provider_name or item.provider_id,
                "type": "balance-only",
                "amount": item.amount,
                "currency": item.currency or "CNY",
                "tokens_today": tokens,
                "day_total": day_total,
                "models": [item.model] if item.model else [],
                "model_label": truncate(item.model, 28) if item.model else "—",
                "note": item.raw_note,
                "api_key": True,
            }
        )

    # funded first, then by tokens
    rows.sort(key=lambda r: (0 if r.get("amount") is not None else 1, -(r.get("tokens_today") or 0), r["name"]))
    return rows
