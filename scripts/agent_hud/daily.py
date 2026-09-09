from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from .ids import stable_key
from .paths import daily_path

_lock = threading.Lock()


def today_str() -> str:
    return datetime.now().astimezone().date().isoformat()


def _empty_daily(date: str | None = None) -> dict[str, Any]:
    return {
        "date": date or today_str(),
        "total_tokens": 0,
        "by_agent": {},
        "by_model": {},
        "by_session": {},
        "updated_at": "",
    }


def load_daily() -> dict[str, Any]:
    path = daily_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_daily()
    except (OSError, json.JSONDecodeError):
        return _empty_daily()
    if data.get("date") != today_str():
        return _empty_daily()
    for key in ("by_agent", "by_model", "by_session"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    try:
        data["total_tokens"] = int(data.get("total_tokens") or 0)
    except (TypeError, ValueError):
        data["total_tokens"] = 0
    return data


def save_daily(data: dict[str, Any]) -> None:
    path = daily_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["date"] = today_str()
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def session_key(agent: str, session_id: str) -> str:
    return stable_key(agent, session_id)


def usage_snapshot_total(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> int:
    return max(
        0,
        int(input_tokens or 0)
        + int(output_tokens or 0)
        + int(cache_read_tokens or 0)
        + int(cache_write_tokens or 0),
    )


def _get_session(daily: dict[str, Any], agent: str, session_id: str) -> dict[str, Any]:
    key = session_key(agent, session_id)
    sess = daily["by_session"].get(key)
    if not isinstance(sess, dict):
        sess = {}
    return {
        "last_cumulative": int(sess.get("last_cumulative") or 0),
        "tokens_today": int(sess.get("tokens_today") or 0),
        "model": str(sess.get("model") or ""),
    }


def _apply_delta(
    daily: dict[str, Any],
    agent: str,
    session_id: str,
    sess: dict[str, Any],
    delta: int,
    model: str,
) -> int:
    delta = max(0, int(delta))
    if delta:
        daily["total_tokens"] = int(daily.get("total_tokens") or 0) + delta
        daily["by_agent"][agent] = int(daily["by_agent"].get(agent) or 0) + delta
        if model:
            daily["by_model"][model] = int(daily["by_model"].get(model) or 0) + delta
        sess["tokens_today"] = int(sess.get("tokens_today") or 0) + delta
    if model:
        sess["model"] = model
    daily["by_session"][session_key(agent, session_id)] = sess
    return delta


def record_tokens(
    agent: str,
    session_id: str,
    *,
    add_tokens: int | None = None,
    session_total: int | None = None,
    tokens_today: int | None = None,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> dict[str, Any]:
    """Update today's token counters.

    Modes (first match wins):
    - add_tokens: explicit increment
    - session_total / usage snapshot sum: cumulative session tokens; add the positive delta
    - tokens_today: absolute "tokens so far today for this session"; add the positive delta
    """
    with _lock:
        daily = load_daily()
        sess = _get_session(daily, agent, session_id)
        delta = 0

        if add_tokens is not None:
            delta = _apply_delta(daily, agent, session_id, sess, add_tokens, model)
            sess["last_cumulative"] = int(sess.get("last_cumulative") or 0) + delta
            daily["by_session"][session_key(agent, session_id)] = sess
        elif tokens_today is not None:
            prev = sess["tokens_today"]
            delta = _apply_delta(daily, agent, session_id, sess, int(tokens_today) - prev, model)
            # tokens_today is absolute; last_cumulative tracks it for consistency
            sess["last_cumulative"] = sess["tokens_today"]
            daily["by_session"][session_key(agent, session_id)] = sess
        else:
            snap = session_total
            if snap is None:
                snap = usage_snapshot_total(
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
                )
            snap = int(snap or 0)
            prev_cum = sess["last_cumulative"]
            if snap > prev_cum:
                delta = _apply_delta(daily, agent, session_id, sess, snap - prev_cum, model)
                sess["last_cumulative"] = snap
            elif snap < prev_cum:
                # cumulative counter reset (restarted session): count full snapshot as new
                delta = _apply_delta(daily, agent, session_id, sess, snap, model)
                sess["last_cumulative"] = snap
            else:
                _apply_delta(daily, agent, session_id, sess, 0, model)
                sess["last_cumulative"] = snap
            daily["by_session"][session_key(agent, session_id)] = sess

        save_daily(daily)
        return {
            "date": daily["date"],
            "total_tokens": int(daily["total_tokens"]),
            "session_tokens_today": int(sess["tokens_today"]),
            "delta": int(delta),
            "by_agent": dict(daily["by_agent"]),
            "by_model": dict(daily["by_model"]),
        }


def get_daily_summary() -> dict[str, Any]:
    daily = load_daily()
    return {
        "date": daily.get("date"),
        "total_tokens": int(daily.get("total_tokens") or 0),
        "by_agent": dict(daily.get("by_agent") or {}),
        "by_model": dict(daily.get("by_model") or {}),
    }


def reset_daily() -> dict[str, Any]:
    with _lock:
        data = _empty_daily()
        save_daily(data)
        return data
