from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ids import stable_key
from .paths import sessions_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class SessionState:
    agent: str
    session_id: str
    model: str = ""
    turn: int = 0
    step: int = 0
    cache_hit_rate: float | None = None
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    context_used: int = 0
    context_limit: int = 0
    status: str = "working"
    source: str = "self-report"
    balance_usd: float | None = None
    balance_currency: str = "USD"
    note: str = ""
    tokens_today: int = 0
    total_tokens: int = 0
    last_cumulative_tokens: int = 0
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def session_file(agent: str, session_id: str) -> Path:
    # Hash-based ASCII name: Chinese session titles used to mojibake under some code pages.
    return sessions_dir() / f"{stable_key(agent, session_id)}.json"


def save_state(state: SessionState) -> Path:
    state.updated_at = _now_iso()
    path = session_file(state.agent, state.session_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_state(path: Path) -> SessionState | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return SessionState.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def list_states(max_age_sec: float = 180.0) -> list[SessionState]:
    out: list[SessionState] = []
    now = time.time()
    for path in sorted(sessions_dir().glob("*.json")):
        st = load_state(path)
        if not st:
            continue
        try:
            updated = datetime.fromisoformat(st.updated_at).timestamp()
        except ValueError:
            updated = now
        if now - updated > max_age_sec:
            continue
        out.append(st)
    out.sort(key=lambda s: s.updated_at, reverse=True)
    return out


def touch_activity(agent: str, session_id: str, **fields: Any) -> SessionState:
    """Increment-friendly upsert used by adapters / report CLI."""
    from .daily import record_tokens, today_str

    path = session_file(agent, session_id)
    existing = load_state(path) or SessionState(agent=agent, session_id=session_id)
    for key, value in fields.items():
        if value is None:
            continue
        if hasattr(existing, key):
            setattr(existing, key, value)
    existing.agent = agent
    existing.session_id = session_id

    # Keep daily counters in sync when usage snapshot or token fields change
    snapshot = int(existing.input_tokens or 0) + int(existing.output_tokens or 0)
    snapshot += int(existing.cache_read_tokens or 0) + int(existing.cache_write_tokens or 0)
    explicit_add = fields.get("add_tokens")
    if explicit_add is not None:
        summary = record_tokens(
            agent,
            session_id,
            add_tokens=int(explicit_add),
            model=existing.model,
        )
        existing.tokens_today = summary["session_tokens_today"]
        existing.total_tokens = int(existing.total_tokens or 0) + int(explicit_add)
        existing.last_cumulative_tokens = int(existing.last_cumulative_tokens or 0) + int(explicit_add)
    elif snapshot > 0 or fields.get("tokens_today") is not None or fields.get("session_total_tokens") is not None:
        session_total = fields.get("session_total_tokens")
        summary = record_tokens(
            agent,
            session_id,
            session_total=int(session_total) if session_total is not None else snapshot,
            tokens_today=int(fields["tokens_today"]) if fields.get("tokens_today") is not None else None,
            model=existing.model,
            input_tokens=existing.input_tokens,
            output_tokens=existing.output_tokens,
            cache_read_tokens=existing.cache_read_tokens,
            cache_write_tokens=existing.cache_write_tokens,
        )
        existing.tokens_today = summary["session_tokens_today"]
        existing.last_cumulative_tokens = max(
            int(existing.last_cumulative_tokens or 0),
            int(session_total) if session_total is not None else snapshot,
        )
        if existing.total_tokens < existing.tokens_today:
            existing.total_tokens = existing.tokens_today

    save_state(existing)
    return existing


def compute_cache_hit_rate(
    cache_read: int, cache_write: int, input_tokens: int
) -> float | None:
    denom = cache_read + cache_write + input_tokens
    if denom <= 0:
        return None
    return round(cache_read / denom, 4)


def clear_stale(max_age_sec: float = 86400.0) -> int:
    removed = 0
    now = time.time()
    for path in sessions_dir().glob("*.json"):
        st = load_state(path)
        if not st:
            continue
        try:
            updated = datetime.fromisoformat(st.updated_at).timestamp()
        except ValueError:
            updated = now
        if now - updated > max_age_sec:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
