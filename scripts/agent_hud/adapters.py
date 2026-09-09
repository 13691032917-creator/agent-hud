from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .store import SessionState, compute_cache_hit_rate, save_state, touch_activity


@dataclass
class AdapterResult:
    agent: str
    session_id: str
    fields: dict[str, Any]


def _parse_iso(ts: str | float | int | None) -> datetime | None:
    try:
        if ts is None:
            return None
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts))
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None


def _file_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def home() -> Path:
    return Path.home()


def _iter_jsonl(path: Path, limit: int = 500) -> Iterable[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            # read tail for large files
            data = fh.readlines()[-limit:]
    except OSError:
        return
    for line in data:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _usage_from_payload(payload: dict[str, Any]) -> dict[str, int | None]:
    usage = payload.get("usage") or payload.get("token_usage") or {}
    if not isinstance(usage, dict):
        usage = {}

    def as_int(key: str, *aliases: str) -> int:
        for k in (key, *aliases):
            if k in usage and usage[k] is not None:
                try:
                    return int(usage[k])
                except (TypeError, ValueError):
                    continue
        return 0

    cache_read = as_int("cache_read_input_tokens", "cache_read_tokens", "cached_tokens")
    cache_write = as_int("cache_creation_input_tokens", "cache_write_tokens")
    inp = as_int("input_tokens", "prompt_tokens")
    out = as_int("output_tokens", "completion_tokens")
    return {
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "input_tokens": inp,
        "output_tokens": out,
    }


# --- Claude Code / MiMo Desktop project transcripts -------------------------


def scan_claude_projects(root: Path | None = None) -> list[AdapterResult]:
    base = root or (home() / ".claude" / "projects")
    if not base.exists():
        return []
    results: list[AdapterResult] = []
    now = datetime.now()
    for project_dir in base.glob("*"):
        if not project_dir.is_dir():
            continue
        files = sorted(
            project_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )[:5]
        for path in files:
            mtime = _file_mtime(path)
            if not mtime or (now - mtime).total_seconds() > 600:
                continue
            model = ""
            turn = 0
            step = 0
            usage = {
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            context_used = 0
            context_limit = 0
            status = "working"
            for row in _iter_jsonl(path):
                # turn-ish counters
                if row.get("type") in {"user", "human"} or row.get("role") == "user":
                    turn += 1
                if row.get("type") in {"assistant", "ai"} or row.get("role") == "assistant":
                    step += 1
                msg = row.get("message") if isinstance(row.get("message"), dict) else {}
                if msg.get("model"):
                    model = str(msg["model"])
                elif row.get("model"):
                    model = str(row["model"])
                u = _usage_from_payload(msg or row)
                if any(v for v in u.values()):
                    usage = u
                    context_used = (
                        u["cache_read_tokens"]
                        + u["cache_write_tokens"]
                        + u["input_tokens"]
                        + u["output_tokens"]
                    )
                # common context limit hints
                for key in ("context_limit", "contextLimit", "max_input_tokens"):
                    if row.get(key):
                        try:
                            context_limit = int(row[key])
                        except (TypeError, ValueError):
                            pass
                if msg.get("stop_reason") or row.get("stop_reason"):
                    status = "idle"
            session_id = path.stem[:80] or project_dir.name
            agent = "claude-code"
            # MiMo Desktop reuses Claude project layout; mark both when env suggests MiMo
            if "mimo" in os.environ.get("APPDATA", "").lower() or "mimo" in os.environ.get(
                "USERPROFILE", ""
            ).lower():
                agent = "mimo"
            results.append(
                AdapterResult(
                    agent=agent,
                    session_id=session_id,
                    fields={
                        "model": model,
                        "turn": turn,
                        "step": step,
                        "cache_read_tokens": usage["cache_read_tokens"],
                        "cache_write_tokens": usage["cache_write_tokens"],
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "cache_hit_rate": compute_cache_hit_rate(
                            usage["cache_read_tokens"],
                            usage["cache_write_tokens"],
                            usage["input_tokens"],
                        ),
                        "context_used": context_used,
                        "context_limit": context_limit,
                        "status": status,
                        "source": "adapter:claude",
                    },
                )
            )
    return results


# --- OpenAI Codex CLI sessions ----------------------------------------------


def scan_codex_sessions(root: Path | None = None) -> list[AdapterResult]:
    candidates = [
        root or home() / ".codex" / "sessions",
        home() / ".codex" / "history",
        home() / ".codex" / "log",
    ]
    results: list[AdapterResult] = []
    now = datetime.now()
    seen: set[Path] = set()
    for base in candidates:
        if not base or not base.exists():
            continue
        files = list(base.rglob("*.jsonl")) + list(base.rglob("*.json"))
        files = sorted(files, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[
            :8
        ]
        for path in files:
            if path in seen:
                continue
            seen.add(path)
            mtime = _file_mtime(path)
            if not mtime or (now - mtime).total_seconds() > 600:
                continue
            model = ""
            turn = 0
            step = 0
            usage = {
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            context_used = 0
            for row in _iter_jsonl(path):
                rtype = str(row.get("type") or row.get("role") or "").lower()
                if rtype in {"user", "message.user", "response.user"}:
                    turn += 1
                if rtype in {"assistant", "message.assistant", "response.done", "item.completed"}:
                    step += 1
                if row.get("model"):
                    model = str(row["model"])
                nested = row.get("message") if isinstance(row.get("message"), dict) else row
                u = _usage_from_payload(nested if isinstance(nested, dict) else row)
                if any(v for v in u.values()):
                    usage = u
                    context_used = sum(int(v or 0) for v in u.values())
            # some codex files store usage at top level of final event
            if not context_used and isinstance(row.get("usage"), dict):
                pass
            session_id = path.stem[:80] or "codex"
            results.append(
                AdapterResult(
                    agent="codex",
                    session_id=session_id,
                    fields={
                        "model": model,
                        "turn": turn,
                        "step": step,
                        "cache_read_tokens": usage["cache_read_tokens"],
                        "cache_write_tokens": usage["cache_write_tokens"],
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "cache_hit_rate": compute_cache_hit_rate(
                            usage["cache_read_tokens"],
                            usage["cache_write_tokens"],
                            usage["input_tokens"],
                        ),
                        "context_used": context_used,
                        "context_limit": 0,
                        "status": "working",
                        "source": "adapter:codex",
                    },
                )
            )
    return results


# --- Trae -------------------------------------------------------------------


def scan_trae(root: Path | None = None) -> list[AdapterResult]:
    """Best-effort Trae agent log scan (layout may vary by version)."""
    bases = [
        root,
        home() / "AppData" / "Roaming" / "Trae" / "User" / "workspaceStorage",
        home() / "AppData" / "Roaming" / "Trae CN" / "User" / "workspaceStorage",
        home() / ".trae" / "sessions",
        home() / ".trae" / "logs",
    ]
    results: list[AdapterResult] = []
    now = datetime.now()
    for base in bases:
        if not base or not Path(base).exists():
            continue
        base_path = Path(base)
        files = list(base_path.rglob("*.jsonl"))[:20]
        files = sorted(files, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[
            :4
        ]
        for path in files:
            mtime = _file_mtime(path)
            if not mtime or (now - mtime).total_seconds() > 300:
                continue
            text_head = ""
            try:
                text_head = path.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            if not re.search(r"model|tokens|assistant|agent", text_head, re.I):
                continue
            model = ""
            m = re.search(r'"model"\s*:\s*"([^"]+)"', text_head)
            if m:
                model = m.group(1)
            results.append(
                AdapterResult(
                    agent="trae",
                    session_id=path.stem[:80],
                    fields={
                        "model": model,
                        "status": "working",
                        "source": "adapter:trae",
                        "note": "Trae log scan is best-effort; prefer report.py",
                    },
                )
            )
    return results


# --- WorkBuddy --------------------------------------------------------------


def scan_workbuddy(root: Path | None = None) -> list[AdapterResult]:
    bases = [
        root,
        home() / ".workbuddy",
        home() / "AppData" / "Roaming" / "workbuddy",
        home() / "AppData" / "Local" / "workbuddy",
    ]
    results: list[AdapterResult] = []
    now = datetime.now()
    for base in bases:
        if not base or not Path(base).exists():
            continue
        base_path = Path(base)
        files = list(base_path.rglob("*.json")) + list(base_path.rglob("*.jsonl"))
        files = sorted(files, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[
            :3
        ]
        for path in files:
            mtime = _file_mtime(path)
            if not mtime or (now - mtime).total_seconds() > 300:
                continue
            results.append(
                AdapterResult(
                    agent="workbuddy",
                    session_id=path.stem[:80],
                    fields={
                        "status": "working",
                        "source": "adapter:workbuddy",
                        "note": "WorkBuddy log scan is best-effort; prefer report.py",
                    },
                )
            )
    return results


# --- DeepSeek Harness -------------------------------------------------------


def scan_deepseek_harness(root: Path | None = None) -> list[AdapterResult]:
    bases = [
        root,
        home() / ".deepseek-harness",
        home() / ".deepseek_harness",
        home() / "AppData" / "Roaming" / "DeepSeekHarness",
        home() / "AppData" / "Local" / "DeepSeekHarness",
    ]
    results: list[AdapterResult] = []
    now = datetime.now()
    for base in bases:
        if not base or not Path(base).exists():
            continue
        base_path = Path(base)
        files = list(base_path.rglob("*.json")) + list(base_path.rglob("*.jsonl"))
        files = sorted(files, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[
            :3
        ]
        for path in files:
            mtime = _file_mtime(path)
            if not mtime or (now - mtime).total_seconds() > 300:
                continue
            model = ""
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:4000]
                m = re.search(r'"model"\s*:\s*"([^"]+)"', head)
                if m:
                    model = m.group(1)
            except OSError:
                pass
            results.append(
                AdapterResult(
                    agent="deepseek-harness",
                    session_id=path.stem[:80],
                    fields={
                        "model": model,
                        "status": "working",
                        "source": "adapter:deepseek-harness",
                        "note": "DeepSeekHarness log scan is best-effort; prefer report.py",
                    },
                )
            )
    return results


def apply_results(results: list[AdapterResult]) -> int:
    count = 0
    for r in results:
        if not r.fields:
            continue
        touch_activity(r.agent, r.session_id, **r.fields)
        count += 1
    return count


def run_all_adapters(extra: dict[str, Path] | None = None) -> int:
    results: list[AdapterResult] = []
    results.extend(scan_claude_projects())
    results.extend(scan_codex_sessions())
    results.extend(scan_trae())
    results.extend(scan_workbuddy())
    results.extend(scan_deepseek_harness())
    if extra:
        for name, path in extra.items():
            if name == "claude":
                results.extend(scan_claude_projects(path))
            elif name == "codex":
                results.extend(scan_codex_sessions(path))
            elif name == "trae":
                results.extend(scan_trae(path))
            elif name == "workbuddy":
                results.extend(scan_workbuddy(path))
            elif name in {"deepseek", "deepseek-harness"}:
                results.extend(scan_deepseek_harness(path))
    return apply_results(results)
