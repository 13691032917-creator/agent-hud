#!/usr/bin/env python3
"""Self-report session metrics for Agent HUD.

Any agent (MiMo, Claude Code, Codex, Trae, WorkBuddy, DeepSeekHarness, …)
can call this CLI after each turn / on idle / when context grows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_hud.daily import get_daily_summary, record_tokens, reset_daily  # noqa: E402
from agent_hud.store import (  # noqa: E402
    SessionState,
    compute_cache_hit_rate,
    save_state,
    session_file,
    load_state,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Report agent session metrics to Agent HUD")
    p.add_argument("--agent", required=True, help="agent id, e.g. mimo | claude-code | codex | trae | workbuddy | deepseek-harness")
    p.add_argument("--session", default="default", help="session id (stable per conversation)")
    p.add_argument("--model", default=None, help="model name shown on HUD")
    p.add_argument("--turn", type=int, default=None, help="conversation turn count")
    p.add_argument("--step", type=int, default=None, help="tool / internal step count")
    p.add_argument("--cache-hit-rate", type=float, default=None, help="0..1 cache hit rate")
    p.add_argument("--cache-read-tokens", type=int, default=None)
    p.add_argument("--cache-write-tokens", type=int, default=None)
    p.add_argument("--input-tokens", type=int, default=None)
    p.add_argument("--output-tokens", type=int, default=None)
    p.add_argument("--context-used", type=int, default=None, help="tokens currently in context window")
    p.add_argument("--context-limit", type=int, default=None, help="model context window size")
    p.add_argument("--add-tokens", type=int, default=None, help="increment today's token counter by N")
    p.add_argument("--tokens-today", type=int, default=None, help="absolute tokens used by this session today")
    p.add_argument("--session-total-tokens", type=int, default=None, help="cumulative tokens for this session lifetime; daily counter uses positive delta")
    p.add_argument("--reset-daily", action="store_true", help="reset today's token counters (all sessions)")
    p.add_argument("--show-daily", action="store_true", help="print today's token summary and exit")
    p.add_argument("--status", choices=["working", "idle", "error"], default=None)
    p.add_argument("--balance", type=float, default=None, help="optional inline balance for current model")
    p.add_argument("--balance-currency", default=None)
    p.add_argument("--note", default=None)
    p.add_argument("--json", dest="json_payload", default=None, help="JSON object merged into the report")
    p.add_argument("--quiet", action="store_true")
    return p


def _coerce_cache_rate(args: argparse.Namespace) -> float | None:
    if args.cache_hit_rate is not None:
        return max(0.0, min(1.0, float(args.cache_hit_rate)))
    read = args.cache_read_tokens or 0
    write = args.cache_write_tokens or 0
    inp = args.input_tokens or 0
    if read or write or inp:
        return compute_cache_hit_rate(read, write, inp)
    return None


def _usage_total(args: argparse.Namespace) -> int:
    return max(
        0,
        int(args.input_tokens or 0)
        + int(args.output_tokens or 0)
        + int(args.cache_read_tokens or 0)
        + int(args.cache_write_tokens or 0),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.show_daily:
        summary = get_daily_summary()
        if args.quiet:
            print(summary["total_tokens"])
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.reset_daily:
        summary = reset_daily()
        if not args.quiet:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    fields: dict[str, object] = {}
    if args.json_payload:
        try:
            extra = json.loads(args.json_payload)
            if isinstance(extra, dict):
                fields.update(extra)
        except json.JSONDecodeError as exc:
            print(f"invalid --json: {exc}", file=sys.stderr)
            return 2

    mapping = {
        "model": args.model,
        "turn": args.turn,
        "step": args.step,
        "cache_read_tokens": args.cache_read_tokens,
        "cache_write_tokens": args.cache_write_tokens,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "context_used": args.context_used,
        "context_limit": args.context_limit,
        "status": args.status,
        "balance_usd": args.balance,
        "balance_currency": args.balance_currency,
        "note": args.note,
    }
    for key, value in mapping.items():
        if value is not None:
            fields[key] = value

    # allow tokens fields via --json as well
    for key in (
        "add_tokens",
        "tokens_today",
        "session_total_tokens",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ):
        if key in fields and fields[key] is not None:
            try:
                fields[key] = int(fields[key])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                fields.pop(key, None)

    rate = _coerce_cache_rate(args)
    if rate is not None:
        fields["cache_hit_rate"] = rate

    # Load previous state so token counters can merge
    prev = load_state(session_file(args.agent, args.session))
    state = prev or SessionState(agent=args.agent, session_id=args.session, source="self-report")
    for key, value in fields.items():
        if hasattr(state, key) and key not in {"add_tokens", "tokens_today", "session_total_tokens"}:
            setattr(state, key, value)
    state.agent = args.agent
    state.session_id = args.session
    state.source = "self-report"

    # Token daily accounting
    add_tokens = args.add_tokens
    if add_tokens is None and "add_tokens" in fields and fields.get("add_tokens") is not None:
        add_tokens = int(fields["add_tokens"])  # type: ignore[arg-type]

    session_total = args.session_total_tokens
    if session_total is None and fields.get("session_total_tokens") is not None:
        session_total = int(fields["session_total_tokens"])  # type: ignore[arg-type]
    if session_total is None and add_tokens is None and args.tokens_today is None:
        snap = _usage_total(args)
        if snap:
            session_total = snap

    summary = record_tokens(
        args.agent,
        args.session,
        add_tokens=add_tokens,
        session_total=session_total,
        tokens_today=args.tokens_today,
        model=state.model,
        input_tokens=int(state.input_tokens or 0),
        output_tokens=int(state.output_tokens or 0),
        cache_read_tokens=int(state.cache_read_tokens or 0),
        cache_write_tokens=int(state.cache_write_tokens or 0),
    )
    state.tokens_today = summary["session_tokens_today"]
    if add_tokens:
        state.total_tokens = int(state.total_tokens or 0) + int(add_tokens)
        state.last_cumulative_tokens = int(state.last_cumulative_tokens or 0) + int(add_tokens)
    elif session_total is not None:
        state.last_cumulative_tokens = max(int(state.last_cumulative_tokens or 0), int(session_total))
        state.total_tokens = max(int(state.total_tokens or 0), int(state.tokens_today or 0))

    path = save_state(state)
    if not args.quiet:
        print(
            f"ok {path} | today={summary['total_tokens']} "
            f"session_today={summary['session_tokens_today']} delta={summary['delta']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
