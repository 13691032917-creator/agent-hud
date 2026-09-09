# Agent HUD 状态协议

所有数据落在用户数据目录（Windows: `%LOCALAPPDATA%\agent-hud\`，Unix: `~/.local/share/agent-hud/`）：

```
agent-hud/
├── config.json          # providers / UI 间隔
├── balances.json        # 余额缓存（collect --balances 写入）
├── hud.pid              # 浮窗单实例
├── hud.log
└── sessions/
    └── <agent>__<session>.json
```

## Session 文件 schema

```json
{
  "agent": "mimo",
  "session_id": "ses_abc",
  "model": "mimo-v2.5-pro",
  "turn": 12,
  "step": 45,
  "cache_hit_rate": 0.72,
  "cache_read_tokens": 10000,
  "cache_write_tokens": 2000,
  "input_tokens": 5000,
  "output_tokens": 800,
  "context_used": 17800,
  "context_limit": 200000,
  "status": "working",
  "source": "self-report",
  "balance_usd": null,
  "balance_currency": "USD",
  "note": "",
  "updated_at": "2026-09-09T12:00:00+08:00"
}
```

### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| agent | str | 平台 id |
| session_id | str | 会话稳定 id |
| model | str | 当前模型名（用于余额匹配） |
| turn | int | 用户轮次 |
| step | int | 工具/内部步数 |
| cache_hit_rate | float\|null | 0~1；优先自算 |
| cache_read_tokens | int | 缓存读 |
| cache_write_tokens | int | 缓存写/创建 |
| input_tokens / output_tokens | int | 最近一次 usage 快照 |
| context_used / context_limit | int | 上下文占用与窗口上限 |
| status | enum | working / idle / error |
| source | str | self-report 或 adapter:name |
| balance_usd | float\|null | 内联余额（通常交给 balances.json） |
| updated_at | ISO8601 | 浮窗用其过滤陈旧会话 |

## 缓存命中率

无官方统一字段时使用：

```
cache_hit_rate = cache_read / (cache_read + cache_write + input_tokens)
```

Anthropic / Claude Code：`cache_read_input_tokens`、`cache_creation_input_tokens`、`input_tokens`。  
OpenAI 兼容：常见 `prompt_tokens_details.cached_tokens`（本包读作 cache_read）。

## 浮窗刷新

- 会话列表：每 `refresh_interval_sec`（默认 3s）读 `sessions/*.json`
- 超过 `session_max_age_sec`（默认 180s）的会话隐藏
- 余额：`balance_refresh_sec`（默认 300s）后台线程刷新

## 兼容其它 agent

只要能执行 Python3 与写 JSON，即可接入；不依赖特定 UI 框架。  
最小接入：每回合调用 `report.py`。增强接入：实现与 `adapters.py` 同等的本地日志扫描。
