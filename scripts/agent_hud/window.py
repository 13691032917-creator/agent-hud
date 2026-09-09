from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from .balances import load_balances, match_balance_for_model, refresh_balances
from .config import load_config
from .daily import get_daily_summary
from .ids import truncate
from .paths import is_windows
from .store import SessionState, clear_stale, list_states

ACCENT = "#3DDC97"
ACCENT_DIM = "#2A9D6A"
BG = "#0F1419"
PANEL = "#151C26"
PANEL2 = "#1A2332"
TEXT = "#E7ECF3"
MUTED = "#8B9BB4"
WARN = "#F5A524"
DANGER = "#F31260"
INFO = "#5B9DFF"
BORDER = "#243044"
CHIP_BG = "#1E2A3A"
CARD_W = 300
CARD_H = 540


def _fmt_tokens(n: int | None) -> str:
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(int(n))


def _fmt_pct(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}%"


def _fmt_money(amount: float | None, currency: str) -> str:
    if amount is None:
        return "—"
    sym = {"USD": "$", "CNY": "¥", "RMB": "¥", "EUR": "€"}.get((currency or "USD").upper(), "")
    return f"{sym}{amount:,.2f}"


def _enable_rounded_corners(widget: tk.Misc) -> None:
    """Win11: soft rounded corners for the frameless card."""
    if not is_windows():
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetParent(widget.winfo_id())
        if not hwnd:
            hwnd = widget.winfo_id()
        preference = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference)
        )
    except Exception:
        pass


class HudApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("")
        self.root.configure(bg=BORDER)
        self.root.geometry(f"{CARD_W}x{CARD_H}+140+120")
        self.root.minsize(280, 420)
        self.root.resizable(True, True)

        # Frameless card — hide the native Windows title bar (blue bar + red X)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", bool(self.cfg.get("always_on_top", True)))
        try:
            self.root.attributes("-alpha", float(self.cfg.get("opacity", 0.98)))
        except Exception:
            pass

        family = "Microsoft YaHei UI" if is_windows() else "Segoe UI"
        self.font_ui = tkfont.Font(family=family, size=10)
        self.font_small = tkfont.Font(family=family, size=9)
        self.font_title = tkfont.Font(family=family, size=11, weight="bold")
        self.font_mono = tkfont.Font(family="Consolas" if is_windows() else "Menlo", size=9)

        self._drag = {"x": 0, "y": 0}
        self._selected = 0
        self._states: list[SessionState] = []
        self._bal_items = load_balances()
        self._daily = get_daily_summary()
        self._status = tk.StringVar(value="就绪")
        self._thread_stop = threading.Event()
        self._chip_btns: list[tk.Label] = []
        self._dragging = False

        # Outer 1px frame acts as card border
        self.border = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        self.border.pack(fill="both", expand=True)

        self.card = tk.Frame(self.border, bg=BG)
        self.card.pack(fill="both", expand=True)

        self._build_chrome()
        self._build_body()
        self._bind_drag()
        self._menu()

        self.root.bind("<Map>", lambda e: _enable_rounded_corners(self.root))
        self.root.after(80, lambda: _enable_rounded_corners(self.root))
        self.root.after(200, self._tick)
        self._start_bg()

    def _build_chrome(self) -> None:
        self.top = tk.Frame(self.card, bg=PANEL2, height=34)
        self.top.pack(fill="x", side="top")
        self.top.pack_propagate(False)

        self.title_lbl = tk.Label(
            self.top,
            text="  Agent HUD",
            bg=PANEL2,
            fg=TEXT,
            font=self.font_title,
            anchor="w",
        )
        self.title_lbl.pack(side="left", fill="both", expand=True)

        self.pin_btn = tk.Label(
            self.top,
            text="PIN",
            bg=PANEL2,
            fg=ACCENT if self.cfg.get("always_on_top", True) else MUTED,
            font=self.font_small,
            cursor="hand2",
            padx=8,
        )
        self.pin_btn.pack(side="right", padx=2)
        self.pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())

        self.close_btn = tk.Label(
            self.top,
            text="×",
            bg=PANEL2,
            fg=MUTED,
            font=self.font_title,
            cursor="hand2",
            padx=10,
        )
        self.close_btn.pack(side="right")
        self.close_btn.bind("<Button-1>", lambda e: self.quit())

    def _build_body(self) -> None:
        body = tk.Frame(self.card, bg=BG)
        body.pack(fill="both", expand=True)

        self.chip_bar = tk.Frame(body, bg=BG)
        self.chip_bar.pack(fill="x", padx=8, pady=(8, 0))

        self.summary = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.summary.pack(fill="x", padx=8, pady=(6, 4))
        self.sum_a = tk.Label(self.summary, bg=PANEL, fg=TEXT, font=self.font_ui, anchor="w")
        self.sum_b = tk.Label(self.summary, bg=PANEL, fg=MUTED, font=self.font_small, anchor="w")
        self.sum_c = tk.Label(self.summary, bg=PANEL, fg=INFO, font=self.font_small, anchor="w")
        self.sum_a.pack(fill="x", padx=10, pady=(8, 0))
        self.sum_b.pack(fill="x", padx=10)
        self.sum_c.pack(fill="x", padx=10, pady=(0, 8))

        # Metrics: fixed inner grid — values stay close to labels (like the HTML preview)
        self.metrics_wrap = tk.Frame(body, bg=BG)
        self.metrics_wrap.pack(fill="x", padx=8, pady=0)
        self.metrics = tk.Frame(
            self.metrics_wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1
        )
        self.metrics.pack(fill="x")
        self.metric_labels: dict[str, tk.Label] = {}
        rows = [
            ("model", "模型"),
            ("turn", "轮次"),
            ("step", "步数"),
            ("cache", "缓存命中"),
            ("ctx", "上下文"),
            ("tokens", "今日Token"),
            ("status", "状态"),
        ]
        self.metrics.columnconfigure(1, weight=1, uniform="m")
        for i, (key, label) in enumerate(rows):
            tk.Label(
                self.metrics,
                text=label,
                bg=PANEL,
                fg=MUTED,
                font=self.font_small,
                anchor="w",
            ).grid(row=i, column=0, sticky="w", padx=(12, 6), pady=4)
            val = tk.Label(
                self.metrics,
                text="—",
                bg=PANEL,
                fg=TEXT,
                font=self.font_mono,
                anchor="e",
            )
            val.grid(row=i, column=1, sticky="e", padx=(6, 12), pady=4)
            self.metric_labels[key] = val

        self.bal_title = tk.Label(
            body, text=" 余额", bg=BG, fg=MUTED, font=self.font_small, anchor="w"
        )
        self.bal_title.pack(fill="x", padx=10, pady=(8, 0))

        self.bal_panel = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.bal_panel.pack(fill="both", expand=True, padx=8, pady=(4, 4))
        self.bal_list = tk.Text(
            self.bal_panel,
            bg=PANEL,
            fg=TEXT,
            font=self.font_small,
            bd=0,
            height=9,
            wrap="word",
            insertbackground=TEXT,
            selectbackground=PANEL2,
            state="disabled",
            highlightthickness=0,
            spacing1=1,
            spacing3=1,
        )
        self.bal_list.pack(fill="both", expand=True, padx=8, pady=8)
        self.bal_list.tag_configure("head", foreground=INFO)
        self.bal_list.tag_configure("warn", foreground=WARN)
        self.bal_list.tag_configure("ok", foreground=ACCENT)
        self.bal_list.tag_configure("muted", foreground=MUTED)

        self.status_bar = tk.Label(
            body,
            textvariable=self._status,
            bg=BG,
            fg=MUTED,
            font=self.font_small,
            anchor="w",
        )
        self.status_bar.pack(fill="x", padx=12, pady=(0, 8))

    def _rebuild_chips(self, states: list[SessionState]) -> None:
        for w in self._chip_btns:
            w.destroy()
        self._chip_btns.clear()
        if not states:
            return
        for i, st in enumerate(states[:5]):
            label = f"{truncate(st.agent, 9)}·{truncate(st.session_id, 9)}"
            active = i == self._selected
            chip = tk.Label(
                self.chip_bar,
                text=label,
                bg=ACCENT_DIM if active else CHIP_BG,
                fg=TEXT if active else MUTED,
                font=self.font_small,
                padx=8,
                pady=3,
                cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 4))
            chip.bind("<Button-1>", lambda e, idx=i: self._select(idx))
            self._chip_btns.append(chip)
        if len(states) > 5:
            more = tk.Label(
                self.chip_bar,
                text=f"+{len(states) - 5}",
                bg=BG,
                fg=MUTED,
                font=self.font_small,
            )
            more.pack(side="left")
            self._chip_btns.append(more)

    def _select(self, idx: int) -> None:
        if not self._states:
            return
        self._selected = max(0, min(idx, len(self._states) - 1))
        self._render(self._states)
        self._render_balances(self._states)

    def _bind_drag(self) -> None:
        widgets = (
            self.top,
            self.title_lbl,
            self.summary,
            self.metrics,
            self.metrics_wrap,
            self.status_bar,
            self.chip_bar,
            self.bal_title,
        )
        for widget in widgets:
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)

    def _drag_start(self, event: tk.Event) -> None:
        # Don't start drag from interactive controls
        if getattr(event, "widget", None) in (self.pin_btn, self.close_btn):
            return
        self._dragging = True
        self._drag["x"] = event.x_root - self.root.winfo_x()
        self._drag["y"] = event.y_root - self.root.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        if not self._dragging:
            return
        x = event.x_root - self._drag["x"]
        y = event.y_root - self._drag["y"]
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, event: tk.Event | None = None) -> None:
        self._dragging = False

    def _menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=TEXT, activebackground=ACCENT_DIM)
        menu.add_command(label="刷新状态", command=self._tick_now)
        menu.add_command(label="立即拉取余额", command=self._refresh_balances_now)
        menu.add_command(label="清理过期会话", command=self._clear_stale)
        menu.add_separator()
        menu.add_command(label="切换置顶", command=self._toggle_pin)
        menu.add_command(label="降低不透明度", command=lambda: self._bump_opacity(-0.08))
        menu.add_command(label="提高不透明度", command=lambda: self._bump_opacity(0.08))
        menu.add_separator()
        menu.add_command(label="下一个会话", command=lambda: self._cycle(1))
        menu.add_command(label="上一个会话", command=lambda: self._cycle(-1))
        menu.add_separator()
        menu.add_command(label="退出 HUD", command=self.quit)
        self.root.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        self.root.bind("<Button-2>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _toggle_pin(self) -> None:
        cur = bool(self.root.attributes("-topmost"))
        nxt = not cur
        self.root.attributes("-topmost", nxt)
        # overrideredirect can drop topmost on some builds
        try:
            self.root.lift()
        except tk.TclError:
            pass
        self.pin_btn.configure(fg=ACCENT if nxt else MUTED)
        self.cfg["always_on_top"] = nxt

    def _bump_opacity(self, delta: float) -> None:
        try:
            cur = float(self.root.attributes("-alpha"))
        except Exception:
            cur = 0.98
        nxt = min(1.0, max(0.45, cur + delta))
        self.root.attributes("-alpha", nxt)
        self.cfg["opacity"] = nxt

    def _cycle(self, delta: int) -> None:
        if not self._states:
            return
        self._selected = (self._selected + delta) % len(self._states)
        self._render(self._states)
        self._render_balances(self._states)

    def _clear_stale(self) -> None:
        n = clear_stale()
        self._status.set(f"已清理 {n} 个过期会话文件")
        self._tick_now()

    def _refresh_balances_now(self) -> None:
        self._status.set("正在拉取余额…")
        threading.Thread(target=self._fetch_balances, daemon=True).start()

    def _fetch_balances(self) -> None:
        try:
            self._bal_items = refresh_balances()
            self.root.after(0, self._tick_now)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._status.set(f"余额刷新失败: {exc}"))

    def _start_bg(self) -> None:
        def loop() -> None:
            interval = float(self.cfg.get("balance_refresh_sec", 300) or 300)
            while not self._thread_stop.is_set():
                try:
                    self._bal_items = refresh_balances()
                except Exception:
                    pass
                self._thread_stop.wait(interval)

        threading.Thread(target=loop, daemon=True).start()

    def _tick_now(self) -> None:
        self._tick()

    def _tick(self) -> None:
        try:
            self._daily = get_daily_summary()
            age = float(self.cfg.get("session_max_age_sec", 600) or 600)
            states = list_states(max_age_sec=age)
            self._states = states
            self._rebuild_chips(states)
            self._render(states)
            self._render_balances(states)
            self._status.set(time.strftime("%H:%M:%S 更新"))
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"渲染错误: {exc}")
        delay = int(float(self.cfg.get("refresh_interval_sec", 3) or 3) * 1000)
        self.root.after(max(1000, delay), self._tick)

    def _render(self, states: list[SessionState]) -> None:
        day_total = int((self._daily or {}).get("total_tokens") or 0)
        if not states:
            self.sum_a.configure(text="暂无活跃会话")
            self.sum_b.configure(text="让 agent 调用 report.py 上报")
            self.sum_c.configure(text=f"今日全局 {_fmt_tokens(day_total)} tokens")
            for key in self.metric_labels:
                self.metric_labels[key].configure(text="—", fg=TEXT)
            return
        if self._selected >= len(states):
            self._selected = 0
        st = states[self._selected]
        self.sum_a.configure(text=f"{st.agent} · {truncate(st.session_id, 20)}")
        model = st.model or "—"
        bal = match_balance_for_model(st.model, self._bal_items)
        bal_txt = (
            _fmt_money(bal.amount, bal.currency)
            if bal
            else _fmt_money(st.balance_usd, st.balance_currency)
        )
        self.sum_b.configure(text=f"{truncate(model, 22)} · 余额 {bal_txt}")
        self.sum_c.configure(
            text=f"会话 {self._selected + 1}/{len(states)} · 今日全局 {_fmt_tokens(day_total)}"
        )

        if st.context_limit and st.context_used:
            pct = st.context_used / st.context_limit * 100
            ctx_txt = f"{_fmt_tokens(st.context_used)}/{_fmt_tokens(st.context_limit)} ({pct:.0f}%)"
            self.metric_labels["ctx"].configure(fg=WARN if pct >= 80 else TEXT)
        elif st.context_used:
            ctx_txt = _fmt_tokens(st.context_used)
            self.metric_labels["ctx"].configure(fg=TEXT)
        else:
            ctx_txt = "—"
            self.metric_labels["ctx"].configure(fg=TEXT)

        sess_today = int(st.tokens_today or 0)
        tok_txt = f"{_fmt_tokens(sess_today)} / 全局 {_fmt_tokens(day_total)}"
        self.metric_labels["model"].configure(text=truncate(model, 24))
        self.metric_labels["turn"].configure(text=str(st.turn))
        self.metric_labels["step"].configure(text=str(st.step))
        self.metric_labels["cache"].configure(text=_fmt_pct(st.cache_hit_rate))
        self.metric_labels["ctx"].configure(text=ctx_txt)
        self.metric_labels["tokens"].configure(text=tok_txt)
        status_map = {"working": ACCENT, "idle": MUTED, "error": DANGER}
        self.metric_labels["status"].configure(text=st.status, fg=status_map.get(st.status, TEXT))

    def _render_balances(self, states: list[SessionState]) -> None:
        current_model = states[self._selected].model if states else ""
        self.bal_list.configure(state="normal")
        self.bal_list.delete("1.0", "end")
        if not self._bal_items:
            self.bal_list.insert(
                "end",
                "尚未配置余额源。\n在 config.json 启用 provider 并填入 API Key，\n或右键 → 立即拉取余额。\n",
                "muted",
            )
        else:
            current = match_balance_for_model(current_model, self._bal_items)
            if current:
                self.bal_list.insert("end", f"当前 · {current.provider_name}\n", "head")
                tag = "ok" if current.amount is not None else "warn"
                self.bal_list.insert(
                    "end",
                    f"  {truncate(current.model, 20)}  {_fmt_money(current.amount, current.currency)}\n",
                    tag,
                )
                if current.raw_note:
                    self.bal_list.insert("end", f"  {truncate(current.raw_note, 26)}\n", "muted")
            self.bal_list.insert("end", "\n其他余额\n", "head")
            shown = 0
            for item in self._bal_items:
                if current and item is current:
                    continue
                line = (
                    f"{truncate(item.provider_name, 10)} · {truncate(item.model, 14)}  "
                    f"{_fmt_money(item.amount, item.currency)}\n"
                )
                tag = "ok" if item.amount is not None else "warn"
                self.bal_list.insert("end", line, tag)
                shown += 1
                if shown >= 8:
                    break
        self.bal_list.configure(state="disabled")

    def quit(self) -> None:
        self._thread_stop.set()
        try:
            from .paths import pid_path

            p = pid_path()
            if p.exists():
                p.unlink()
        except OSError:
            pass
        self.root.destroy()

    def run(self) -> None:
        from .paths import pid_path

        try:
            pid_path().write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass
        # Re-assert topmost after frameless setup (Windows)
        try:
            self.root.attributes("-topmost", bool(self.cfg.get("always_on_top", True)))
            self.root.lift()
        except tk.TclError:
            pass
        self.root.mainloop()


def run_window() -> int:
    if is_windows():
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = HudApp()
    app.run()
    return 0
