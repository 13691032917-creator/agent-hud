from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable

from .balances import load_balances, match_balance_for_model, refresh_balances
from .config import load_config
from .daily import get_daily_summary
from .ids import truncate
from .paths import is_windows
from .settings import blank_provider, normalize_provider, save_providers
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
CARD_W = 360
CARD_H = 560

# 简化预设：国内平台默认人民币
PRESETS: list[dict] = [
    {
        "label": "DeepSeek",
        "id": "deepseek",
        "name": "DeepSeek",
        "type": "deepseek",
        "currency": "CNY",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "base_url": "",
        "need_url": False,
    },
    {
        "label": "Moonshot",
        "id": "moonshot",
        "name": "Moonshot",
        "type": "moonshot",
        "currency": "CNY",
        "models": ["kimi-k2.5", "moonshot-v1-8k"],
        "base_url": "https://api.moonshot.cn",
        "need_url": False,
    },
    {
        "label": "SiliconFlow",
        "id": "siliconflow",
        "name": "SiliconFlow",
        "type": "siliconflow",
        "currency": "CNY",
        "models": ["deepseek-ai/DeepSeek-V3"],
        "base_url": "",
        "need_url": False,
    },
    {
        "label": "OpenAI",
        "id": "openai",
        "name": "OpenAI",
        "type": "openai",
        "currency": "USD",
        "models": ["gpt-5", "gpt-4.1"],
        "base_url": "",
        "need_url": False,
    },
    {
        "label": "中转站",
        "id": "gateway",
        "name": "中转站",
        "type": "new_api",
        "currency": "CNY",
        "models": [],
        "base_url": "",
        "need_url": True,
    },
]


def _fmt_tokens(n: int | None) -> str:
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(int(n))


def _fmt_pct(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}%"


def _fmt_money(amount: float | None, currency: str) -> str:
    if amount is None:
        return "—"
    cur = (currency or "CNY").upper()
    sym = {"USD": "$", "CNY": "¥", "RMB": "¥", "EUR": "€"}.get(cur, "¥" if cur in {"CNY", "RMB"} else "$")
    return f"{sym}{amount:,.2f}"


def _enable_rounded_corners(widget: tk.Misc) -> None:
    if not is_windows():
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetParent(widget.winfo_id()) or widget.winfo_id()
        preference = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference)
        )
    except Exception:
        pass


class ApiSimpleDialog:
    """只填 API Key 就能查余额的极简配置窗。"""

    def __init__(self, master: tk.Misc, on_saved: Callable[[], None] | None = None) -> None:
        self.on_saved = on_saved
        self.cfg = load_config()
        self.providers = [
            normalize_provider(p) for p in (self.cfg.get("providers") or []) if isinstance(p, dict)
        ]
        self.preset_idx = 0

        self.win = tk.Toplevel(master)
        self.win.title("填写 API · 查余额")
        self.win.configure(bg=BG)
        self.win.geometry("420x420+200+140")
        self.win.resizable(False, False)
        try:
            self.win.transient(master.winfo_toplevel())
        except tk.TclError:
            pass
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass

        family = "Microsoft YaHei UI" if is_windows() else "Segoe UI"
        self.f = tkfont.Font(family=family, size=11)
        self.fs = tkfont.Font(family=family, size=10)
        self.fm = tkfont.Font(family="Consolas" if is_windows() else "Menlo", size=10)

        body = tk.Frame(self.win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(body, text="选择平台，粘贴 API Key", bg=BG, fg=TEXT, font=self.f, anchor="w").pack(
            fill="x"
        )
        tk.Label(
            body,
            text="国内平台默认显示人民币 ¥；保存后自动拉余额",
            bg=BG,
            fg=MUTED,
            font=self.fs,
            anchor="w",
        ).pack(fill="x", pady=(2, 8))

        self.preset_var = tk.StringVar(value=PRESETS[0]["label"])
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        self.preset_box = tk.OptionMenu(row, self.preset_var, *[p["label"] for p in PRESETS])
        self.preset_box.config(bg=PANEL, fg=TEXT, highlightthickness=0, relief="flat", font=self.fs)
        self.preset_box.pack(fill="x")
        self.preset_var.trace_add("write", lambda *_: self._apply_preset_fields())

        self.url_var = tk.StringVar()
        self.key_var = tk.StringVar()
        self.models_var = tk.StringVar()
        self.cur_var = tk.StringVar(value="CNY")

        self._field(body, "API Key", self.key_var, show="•")
        self._field(body, "Base URL（中转站必填）", self.url_var)
        self._field(body, "Models（可选，逗号分隔）", self.models_var)
        self._field(body, "货币", self.cur_var)

        self.hint = tk.Label(body, text="", bg=BG, fg=MUTED, font=self.fs, anchor="w", wraplength=320)
        self.hint.pack(fill="x", pady=(6, 0))

        foot = tk.Frame(body, bg=BG)
        foot.pack(fill="x", pady=(12, 0))
        tk.Button(
            foot,
            text="取消",
            command=self.win.destroy,
            bg=PANEL2,
            fg=MUTED,
            relief="flat",
            font=self.fs,
            padx=10,
            pady=4,
        ).pack(side="right", padx=(6, 0))
        tk.Button(
            foot,
            text="保存并查余额",
            command=self._save_and_fetch,
            bg=ACCENT_DIM,
            fg=TEXT,
            relief="flat",
            font=self.f,
            padx=12,
            pady=4,
        ).pack(side="right")

        self._apply_preset_fields()

    def _field(self, parent, label, var, show=None) -> None:
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x", pady=4)
        tk.Label(wrap, text=label, bg=BG, fg=MUTED, font=self.fs, anchor="w").pack(fill="x")
        tk.Entry(
            wrap,
            textvariable=var,
            show=show or "",
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            font=self.fm,
            relief="flat",
        ).pack(fill="x", ipady=5)

    def _apply_preset_fields(self) -> None:
        label = self.preset_var.get()
        preset = next((p for p in PRESETS if p["label"] == label), PRESETS[0])
        self.cur_var.set(preset.get("currency") or "CNY")
        if preset.get("base_url"):
            self.url_var.set(preset["base_url"])
        elif preset.get("need_url"):
            self.url_var.set("")
        else:
            self.url_var.set(preset.get("base_url") or "")
        self.models_var.set(", ".join(preset.get("models") or []))
        existing = next((p for p in self.providers if p.get("id") == preset["id"]), None)
        if existing:
            if existing.get("api_key"):
                self.key_var.set(existing["api_key"])
            if existing.get("base_url"):
                self.url_var.set(existing["base_url"])
            if existing.get("models"):
                self.models_var.set(", ".join(existing["models"]))
            self.cur_var.set(existing.get("currency") or preset.get("currency") or "CNY")
        self.hint.config(
            text="中转站请填 Base URL + access token（部分站用 api_key 即可）"
            if preset.get("need_url")
            else f"将写入 config · {preset['id']} · 货币 {self.cur_var.get()}"
        )

    def _save_and_fetch(self) -> None:
        label = self.preset_var.get()
        preset = next((p for p in PRESETS if p["label"] == label), PRESETS[0])
        key = self.key_var.get().strip()
        url = self.url_var.get().strip()
        models = [m.strip() for m in self.models_var.get().replace("，", ",").split(",") if m.strip()]
        cur = (self.cur_var.get() or preset.get("currency") or "CNY").upper()
        if preset.get("need_url") and not url:
            self.hint.config(text="中转站需要填写 Base URL", fg=WARN)
            return
        if not key and preset["type"] != "manual":
            self.hint.config(text="请先粘贴 API Key", fg=WARN)
            return

        provider = normalize_provider(
            {
                "id": preset["id"],
                "name": preset["name"],
                "type": preset["type"],
                "api_key": key,
                "access_token": key if preset["type"] in {"new_api", "one_api"} else "",
                "base_url": url,
                "models": models or preset.get("models") or [],
                "currency": cur,
                "enabled": True,
                "note": "simple-api-form",
            }
        )
        # 合并：同 id 覆盖，其它保留
        others = [p for p in self.providers if p.get("id") != provider["id"]]
        save_providers(self.cfg, others + [provider])
        self.win.destroy()
        if self.on_saved:
            self.on_saved()


class HudApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("")
        self.root.configure(bg=BORDER)
        self.root.geometry(f"{CARD_W}x{CARD_H}+120+100")
        self.root.minsize(280, 400)
        self.root.resizable(True, True)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", bool(self.cfg.get("always_on_top", True)))
        try:
            self.root.attributes("-alpha", float(self.cfg.get("opacity", 0.98)))
        except Exception:
            pass

        family = "Microsoft YaHei UI" if is_windows() else "Segoe UI"
        self.font_title = tkfont.Font(family=family, size=12, weight="bold")
        self.font_ui = tkfont.Font(family=family, size=11)
        self.font_small = tkfont.Font(family=family, size=10)
        self.font_mono = tkfont.Font(family="Consolas" if is_windows() else "Menlo", size=10)

        self._drag = {"x": 0, "y": 0}
        self._dragging = False
        self._selected = 0
        self._states: list[SessionState] = []
        self._bal_items = load_balances()
        self._daily = get_daily_summary()
        self._status = tk.StringVar(value="拖动顶栏移动 · 点 API 填密钥")
        self._thread_stop = threading.Event()
        self._chip_btns: list[tk.Label] = []
        self._pressed_btn = False

        self.border = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        self.border.pack(fill="both", expand=True)
        self.card = tk.Frame(self.border, bg=BG)
        self.card.pack(fill="both", expand=True)

        self._build()
        # 全卡片可拖（按钮/输入除外）
        self._bind_drag_tree(self.card)
        self.root.bind("<Button-3>", self._popup_menu)
        self.root.bind("<Button-2>", self._popup_menu)
        self._menu = self._build_menu()

        self.root.bind("<Map>", lambda e: _enable_rounded_corners(self.root))
        self.root.after(60, lambda: _enable_rounded_corners(self.root))
        self.root.after(150, self._tick)
        self._start_bg()

    def _build(self) -> None:
        # chrome
        self.top = tk.Frame(self.card, bg=PANEL2, height=40)
        self.top.pack(fill="x")
        self.top.pack_propagate(False)
        title = tk.Label(
            self.top, text=" Agent HUD", bg=PANEL2, fg=TEXT, font=self.font_title, anchor="w"
        )
        title.pack(side="left", fill="both", expand=True)

        # Real Buttons — click always wins over drag
        self.pin_btn = tk.Button(
            self.top,
            text="PIN",
            command=self._toggle_pin,
            bg=PANEL2,
            fg=ACCENT if self.cfg.get("always_on_top", True) else MUTED,
            activebackground=CHIP_BG,
            activeforeground=TEXT,
            relief="flat",
            font=self.font_small,
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            takefocus=False,
        )
        self.pin_btn.pack(side="right", padx=2, pady=4)

        self.api_btn = tk.Button(
            self.top,
            text="API",
            command=self.open_api_dialog,
            bg=CHIP_BG,
            fg=INFO,
            activebackground=INFO,
            activeforeground=BG,
            relief="flat",
            font=self.font_small,
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            takefocus=False,
        )
        self.api_btn.pack(side="right", padx=2, pady=4)

        self.close_btn = tk.Button(
            self.top,
            text="×",
            command=self.quit,
            bg=PANEL2,
            fg=MUTED,
            activebackground=DANGER,
            activeforeground=TEXT,
            relief="flat",
            font=self.font_title,
            bd=0,
            padx=10,
            pady=2,
            cursor="hand2",
            takefocus=False,
        )
        self.close_btn.pack(side="right", padx=2, pady=4)

        body = tk.Frame(self.card, bg=BG)
        body.pack(fill="both", expand=True)

        self.chip_bar = tk.Frame(body, bg=BG)
        self.chip_bar.pack(fill="x", padx=8, pady=(6, 0))

        # summary compact
        self.summary = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.summary.pack(fill="x", padx=8, pady=(6, 4))
        self.sum_a = tk.Label(self.summary, bg=PANEL, fg=TEXT, font=self.font_ui, anchor="w")
        self.sum_b = tk.Label(self.summary, bg=PANEL, fg=MUTED, font=self.font_small, anchor="w")
        self.sum_c = tk.Label(self.summary, bg=PANEL, fg=INFO, font=self.font_small, anchor="w")
        self.sum_a.pack(fill="x", padx=10, pady=(7, 0))
        self.sum_b.pack(fill="x", padx=10)
        self.sum_c.pack(fill="x", padx=10, pady=(0, 7))

        # metrics 2-col compact
        self.metrics = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.metrics.pack(fill="x", padx=8, pady=2)
        self.metric_labels: dict[str, tk.Label] = {}
        rows = [
            ("model", "模型"),
            ("turnstep", "轮/步"),
            ("cache", "缓存"),
            ("ctx", "上下文"),
            ("tokens", "今日"),
            ("status", "状态"),
        ]
        for i, (key, label) in enumerate(rows):
            tk.Label(
                self.metrics, text=label, bg=PANEL, fg=MUTED, font=self.font_small, anchor="w", width=6
            ).grid(row=i, column=0, sticky="w", padx=(10, 4), pady=2)
            val = tk.Label(
                self.metrics, text="—", bg=PANEL, fg=TEXT, font=self.font_mono, anchor="e"
            )
            val.grid(row=i, column=1, sticky="e", padx=(4, 10), pady=2)
            self.metric_labels[key] = val
        self.metrics.columnconfigure(1, weight=1)

        tk.Label(body, text=" 余额", bg=BG, fg=MUTED, font=self.font_small, anchor="w").pack(
            fill="x", padx=10, pady=(6, 0)
        )

        # scrollable balance area so content is always reachable
        self.bal_wrap = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.bal_wrap.pack(fill="both", expand=True, padx=8, pady=(2, 4))
        self.bal_canvas = tk.Canvas(self.bal_wrap, bg=PANEL, bd=0, highlightthickness=0)
        scroll = tk.Scrollbar(self.bal_wrap, orient="vertical", command=self.bal_canvas.yview)
        self.bal_frame = tk.Frame(self.bal_canvas, bg=PANEL)
        self.bal_frame.bind(
            "<Configure>",
            lambda e: self.bal_canvas.configure(scrollregion=self.bal_canvas.bbox("all")),
        )
        self._bal_window = self.bal_canvas.create_window((0, 0), window=self.bal_frame, anchor="nw")
        self.bal_canvas.configure(yscrollcommand=scroll.set)
        self.bal_canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scroll.pack(side="right", fill="y")
        self.bal_canvas.bind(
            "<Configure>",
            lambda e: self.bal_canvas.itemconfigure(self._bal_window, width=e.width),
        )
        self.bal_labels: list[tk.Label] = []

        self.status_bar = tk.Label(
            body, textvariable=self._status, bg=BG, fg=MUTED, font=self.font_small, anchor="w"
        )
        self.status_bar.pack(fill="x", padx=10, pady=(0, 6))

    def _build_menu(self) -> tk.Menu:
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=TEXT, activebackground=ACCENT_DIM)
        menu.add_command(label="填写 API Key…", command=self.open_api_dialog)
        menu.add_command(label="立即拉取余额", command=self._refresh_balances_now)
        menu.add_command(label="刷新会话", command=self._tick_now)
        menu.add_command(label="清理过期", command=self._clear_stale)
        menu.add_separator()
        menu.add_command(label="切换置顶", command=self._toggle_pin)
        menu.add_command(label="下一个会话", command=lambda: self._cycle(1))
        menu.add_command(label="上一个会话", command=lambda: self._cycle(-1))
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)
        return menu

    def _popup_menu(self, event: tk.Event) -> None:
        self._menu.tk_popup(event.x_root, event.y_root)

    def _press(self, flag: bool) -> None:
        self._pressed_btn = flag

    def _bind_drag_tree(self, widget: tk.Misc) -> None:
        # Never attach drag handlers to interactive controls
        if isinstance(widget, (tk.Button, tk.Entry, tk.Listbox, tk.Checkbutton, tk.OptionMenu)):
            return
        if widget in (self.pin_btn, self.api_btn, self.close_btn):
            return
        widget.bind("<Button-1>", self._drag_start, add="+")
        widget.bind("<B1-Motion>", self._drag_move, add="+")
        widget.bind("<ButtonRelease-1>", self._drag_end, add="+")
        for child in widget.winfo_children():
            self._bind_drag_tree(child)

    def _drag_start(self, event: tk.Event) -> None:
        # Ignore presses that originate on control widgets
        if isinstance(getattr(event, "widget", None), (tk.Button, tk.Entry)):
            return
        if self._pressed_btn:
            return
        self._dragging = True
        self._drag["x"] = event.x_root - self.root.winfo_x()
        self._drag["y"] = event.y_root - self.root.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        if not self._dragging:
            return
        x = event.x_root - self._drag["x"]
        y = event.y_root - self._drag["y"]
        self.root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _drag_end(self, event: tk.Event | None = None) -> None:
        self._dragging = False

    def open_api_dialog(self) -> None:
        try:
            self._status.set("正在打开 API 配置…")
            self.root.update_idletasks()
            ApiSimpleDialog(self.root, on_saved=self._on_api_saved)
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"打开 API 失败: {exc}")
            try:
                from .paths import log_path

                log_path().write_text(f"api dialog error: {exc}\n", encoding="utf-8")
            except OSError:
                pass

    def _on_api_saved(self) -> None:
        self.cfg = load_config()
        self._bal_items = load_balances()
        self._status.set("已保存，正在查询余额…")
        threading.Thread(target=self._fetch_balances, daemon=True).start()

    def _toggle_pin(self) -> None:
        nxt = not bool(self.root.attributes("-topmost"))
        self.root.attributes("-topmost", nxt)
        try:
            self.root.lift()
        except tk.TclError:
            pass
        self.pin_btn.configure(fg=ACCENT if nxt else MUTED)
        self.cfg["always_on_top"] = nxt

    def _cycle(self, delta: int) -> None:
        if not self._states:
            return
        self._selected = (self._selected + delta) % len(self._states)
        self._render(self._states)

    def _clear_stale(self) -> None:
        n = clear_stale()
        self._status.set(f"已清理 {n} 个过期会话")
        self._tick_now()

    def _refresh_balances_now(self) -> None:
        self._status.set("正在拉取余额…")
        threading.Thread(target=self._fetch_balances, daemon=True).start()

    def _fetch_balances(self) -> None:
        try:
            self._bal_items = refresh_balances()
            self.root.after(0, self._tick_now)
            self.root.after(0, lambda: self._status.set(time.strftime("%H:%M:%S 余额已更新")))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._status.set(f"余额失败: {exc}"))

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

    def _rebuild_chips(self, states: list[SessionState]) -> None:
        for w in self._chip_btns:
            w.destroy()
        self._chip_btns.clear()
        for i, st in enumerate(states[:4]):
            label = f"{truncate(st.agent, 8)}·{truncate(st.session_id, 8)}"
            active = i == self._selected
            chip = tk.Label(
                self.chip_bar,
                text=label,
                bg=ACCENT_DIM if active else CHIP_BG,
                fg=TEXT if active else MUTED,
                font=self.font_small,
                padx=7,
                pady=2,
                cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 4))
            chip.bind("<Button-1>", lambda e, idx=i: self._select(idx))
            self._chip_btns.append(chip)

    def _select(self, idx: int) -> None:
        if not self._states:
            return
        self._selected = max(0, min(idx, len(self._states) - 1))
        self._render(self._states)

    def _tick_now(self) -> None:
        self._tick()

    def _tick(self) -> None:
        try:
            self._daily = get_daily_summary()
            age = float(self.cfg.get("session_max_age_sec", 900) or 900)
            states = list_states(max_age_sec=age)
            self._states = states
            self._rebuild_chips(states)
            self._render(states)
            self._status.set(time.strftime("%H:%M:%S 更新"))
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"渲染错误: {exc}")
        delay = int(float(self.cfg.get("refresh_interval_sec", 3) or 3) * 1000)
        self.root.after(max(1000, delay), self._tick)

    def _set_metric(self, key: str, text: str, color: str | None = None) -> None:
        lab = self.metric_labels[key]
        lab.configure(text=text, fg=color or TEXT)

    def _render(self, states: list[SessionState]) -> None:
        day_total = int((self._daily or {}).get("total_tokens") or 0)
        self._render_balance_items(day_total, states[self._selected] if states else None)

        if not states:
            self.sum_a.configure(text="暂无活跃会话")
            self.sum_b.configure(text="点右上角 API 填密钥；agent 调 report.py 上报")
            self.sum_c.configure(text=f"今日全局 {_fmt_tokens(day_total)} tokens")
            for key in self.metric_labels:
                self._set_metric(key, "—")
            return

        if self._selected >= len(states):
            self._selected = 0
        st = states[self._selected]
        self.sum_a.configure(text=f"{st.agent} · {truncate(st.session_id, 18)}")
        model = st.model or "—"
        bal = match_balance_for_model(st.model, self._bal_items)
        bal_txt = (
            _fmt_money(bal.amount, bal.currency)
            if bal
            else _fmt_money(st.balance_usd, st.balance_currency or "CNY")
        )
        self.sum_b.configure(text=f"{truncate(model, 20)} · 余额 {bal_txt}")
        self.sum_c.configure(
            text=f"会话 {self._selected + 1}/{len(states)} · 今日 {_fmt_tokens(day_total)}"
        )

        self._set_metric("model", truncate(model, 28))
        self._set_metric("turnstep", f"{st.turn} / {st.step}")
        self._set_metric("cache", _fmt_pct(st.cache_hit_rate))
        if st.context_limit and st.context_used:
            pct = st.context_used / st.context_limit * 100
            self._set_metric(
                "ctx",
                f"{_fmt_tokens(st.context_used)}/{_fmt_tokens(st.context_limit)} ({pct:.0f}%)",
                WARN if pct >= 80 else TEXT,
            )
        elif st.context_used:
            self._set_metric("ctx", _fmt_tokens(st.context_used))
        else:
            self._set_metric("ctx", "—")
        self._set_metric("tokens", f"{_fmt_tokens(st.tokens_today)} / {_fmt_tokens(day_total)}")
        status_map = {"working": ACCENT, "idle": MUTED, "error": DANGER}
        self._set_metric("status", st.status, status_map.get(st.status, TEXT))

    def _render_balance_items(self, day_total: int, st: SessionState | None) -> None:
        for lab in self.bal_labels:
            lab.destroy()
        self.bal_labels.clear()

        def add(text: str, color: str) -> None:
            lab = tk.Label(
                self.bal_frame,
                text=text,
                bg=PANEL,
                fg=color,
                font=self.font_small,
                anchor="w",
                justify="left",
            )
            lab.pack(fill="x", padx=8, pady=1)
            self.bal_labels.append(lab)

        if not self._bal_items:
            add("尚未配置余额源", MUTED)
            add("点顶栏 API → 选平台 → 贴 Key", MUTED)
            add("国内默认显示人民币 ¥", INFO)
            return

        current = match_balance_for_model(st.model, self._bal_items) if st else None
        if current:
            add(f"当前 · {current.provider_name}", INFO)
            tag = ACCENT if current.amount is not None else WARN
            add(
                f"  {truncate(current.model, 20)}  {_fmt_money(current.amount, current.currency)}",
                tag,
            )
            if current.raw_note:
                add(f"  {truncate(current.raw_note, 26)}", MUTED)
        add("其他", INFO)
        shown = 0
        for item in self._bal_items:
            if current and item is current:
                continue
            color = ACCENT if item.amount is not None else WARN
            add(
                f"{truncate(item.provider_name, 10)} · {truncate(item.model, 14)}  "
                f"{_fmt_money(item.amount, item.currency)}",
                color,
            )
            shown += 1
            if shown >= 12:
                break

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
    HudApp().run()
    return 0
