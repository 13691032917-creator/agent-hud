#!/usr/bin/env python3
"""Launch the Agent HUD floating window (single instance)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python start_hud.py` without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_hud.paths import ensure_data_dir, pid_path  # noqa: E402


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong(0)
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    ensure_data_dir()
    p = pid_path()
    if p.exists():
        try:
            old = int(p.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            old = 0
        if old and _pid_alive(old) and old != os.getpid():
            print(f"HUD already running (pid={old})")
            return 0
    from agent_hud.window import run_window

    return run_window()


if __name__ == "__main__":
    raise SystemExit(main())
