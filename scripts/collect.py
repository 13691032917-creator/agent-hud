#!/usr/bin/env python3
"""Run local log adapters and/or refresh balances from the CLI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_hud.adapters import run_all_adapters  # noqa: E402
from agent_hud.balances import refresh_balances  # noqa: E402
from agent_hud.daily import get_daily_summary  # noqa: E402
from agent_hud.store import clear_stale, list_states  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Collect Agent HUD metrics")
    p.add_argument("--scan", action="store_true", help="scan local agent logs via adapters")
    p.add_argument("--balances", action="store_true", help="refresh balance providers")
    p.add_argument("--clean", action="store_true", help="remove stale session files")
    p.add_argument("--list", action="store_true", help="list current sessions")
    p.add_argument("--daily", action="store_true", help="show today's token totals")
    p.add_argument("--json", action="store_true", help="print JSON for --list")
    args = p.parse_args(argv)

    if not any([args.scan, args.balances, args.clean, args.list, args.daily]):
        args.scan = True
        args.balances = True
        args.list = True
        args.daily = True

    if args.scan:
        n = run_all_adapters()
        print(f"scan: updated {n} session file(s)")
    if args.balances:
        items = refresh_balances()
        print(f"balances: {len(items)} row(s)")
        for it in items:
            amount = "—" if it.amount is None else f"{it.amount} {it.currency}"
            print(f"  - {it.provider_name} · {it.model}: {amount} ({it.raw_note})")
    if args.clean:
        n = clear_stale()
        print(f"clean: removed {n}")
    if args.daily:
        daily = get_daily_summary()
        print(f"daily tokens ({daily.get('date')}): {daily.get('total_tokens')}")
        by_agent = daily.get("by_agent") or {}
        by_model = daily.get("by_model") or {}
        for k, v in sorted(by_agent.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  agent {k}: {v}")
        for k, v in sorted(by_model.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  model {k}: {v}")
    if args.list:
        states = list_states()
        if args.json:
            import json

            print(json.dumps([s.to_dict() for s in states], ensure_ascii=False, indent=2))
        else:
            if not states:
                print("no active sessions")
            for s in states:
                print(
                    f"- {s.agent}/{s.session_id} model={s.model or '?'} "
                    f"turn={s.turn} step={s.step} cache={s.cache_hit_rate} "
                    f"ctx={s.context_used}/{s.context_limit} "
                    f"tokens_today={s.tokens_today} status={s.status} src={s.source}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
