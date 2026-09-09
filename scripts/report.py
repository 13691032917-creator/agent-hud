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

from agent_hud.store import (  # noqa: E402
    SessionState,
    compute_cache_hit_rate,
    save_state,
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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

    rate = _coerce_cache_rate(args)
    if rate is not None:
        fields["cache_hit_rate"] = rate

    state = SessionState(
        agent=args.agent,
        session_id=args.session,
        source="self-report",
    )
    for key, value in fields.items():
        if hasattr(state, key):
            setattr(state, key, value)
    state.source = "self-report"
    path = save_state(state)
    if not args.quiet:
        print(f"ok {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
