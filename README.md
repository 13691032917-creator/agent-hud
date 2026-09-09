# Agent HUD

跨 agent 的**可拖拽置顶浮窗**：显示当前模型的轮次、步数、缓存命中率、上下文用量，以及当前/其他模型在各 AI 平台的余额。

支持：**MiMo Desktop · Claude Code · Codex · Trae · WorkBuddy · DeepSeekHarness**（及任何能执行 Python 的 agent）。

```
┌─────────────────────────────┐
│ Agent HUD            PIN ×  │
│ mimo · ses_xxx              │
│ 模型 mimo-v2.5-pro  $12.40  │
├─────────────────────────────┤
│ 模型     mimo-v2.5-pro      │
│ 轮次     12                 │
│ 步数     45                 │
│ 缓存命中 72.0%              │
│ 上下文   45k / 200k (22.5%) │
│ 状态     working            │
├─────────────────────────────┤
│ 余额                        │
│ 当前 · DeepSeek             │
│   deepseek-chat  $12.40     │
│ 其他余额 …                  │
└─────────────────────────────┘
```

## 特性

- 标题栏自由拖拽，默认置顶，可调透明度
- 多会话并列，右键切换
- `report.py` 统一自上报协议（全平台）
- 可选本地日志 adapter 兜底扫描（Claude / Codex / Trae 等）
- 余额支持 DeepSeek、OpenAI、OpenRouter、Moonshot、SiliconFlow、new-api/one-api 中转站、手动余额

## 安装

### 方式 A：作为 Claude / MiMo 技能

```powershell
git clone https://github.com/13691032917-creator/agent-hud.git
# Windows
Copy-Item -Recurse agent-hud "$env:USERPROFILE\.claude\skills\agent-hud"
# 或 macOS / Linux
# cp -R agent-hud ~/.claude/skills/agent-hud
```

新对话中说：**「打开 HUD」** / **「悬浮窗」**。

### 方式 B：仅作为桌面浮窗（不装技能）

```bash
python scripts/start_hud.py
python scripts/report.py --agent myagent --session demo --model deepseek-chat --turn 1 --step 1
```

依赖：**Python 3.10+**，标准库 `tkinter`（Windows 官方安装包自带）。

## 快速开始

### 1. 启动浮窗

```powershell
# Windows
scripts\start_hud.cmd
# 或
python scripts/start_hud.py
```

### 2. 上报会话

```bash
python scripts/report.py \
  --agent claude-code \
  --session main \
  --model claude-sonnet-4 \
  --turn 8 \
  --step 20 \
  --cache-read-tokens 12000 \
  --cache-write-tokens 1500 \
  --input-tokens 3000 \
  --context-used 16500 \
  --context-limit 200000 \
  --status working
```

缓存命中率可自动计算：

`cache_hit = cache_read / (cache_read + cache_write + input)`

### 3. 配置余额

首次运行后编辑：

- Windows: `%LOCALAPPDATA%\agent-hud\config.json`
- macOS/Linux: `~/.local/share/agent-hud/config.json`

示例见仓库内 [`config.example.json`](./config.example.json)。把 provider 的 `enabled` 设为 `true` 并填入 API Key，然后：

```bash
python scripts/collect.py --balances
```

> **安全**：真实 `config.json` 不要提交到 Git；本仓库 `.gitignore` 已排除。

## 目录

```
agent-hud/
├── SKILL.md                 # 技能说明（给 agent）
├── config.example.json      # 余额/UI 配置模板
├── locales/                 # 插件页展示文案
├── references/              # 协议与平台文档
└── scripts/
    ├── start_hud.py         # 启动浮窗
    ├── start_hud.cmd
    ├── report.py            # 自上报 CLI
    ├── collect.py           # 扫描 / 余额 / 列表
    └── agent_hud/           # 实现包
```

## 数据落盘位置

| 内容 | Windows | Unix |
|------|---------|------|
| 会话状态 | `%LOCALAPPDATA%\agent-hud\sessions\` | `~/.local/share/agent-hud/sessions/` |
| 配置 | `%LOCALAPPDATA%\agent-hud\config.json` | 同上目录下 |
| 余额缓存 | `balances.json` | 同上 |

可用环境变量 `AGENT_HUD_CONFIG` 覆盖配置路径。

## 各平台接入要点

| 平台 | 建议 |
|------|------|
| MiMo / Claude Code | `--agent mimo` / `claude-code`；可 `collect.py --scan` 读 `~/.claude/projects/**/*.jsonl` |
| Codex | `--agent codex`；可扫 `~/.codex/sessions` |
| Trae / WorkBuddy / DeepSeekHarness | 以 `report.py` 自上报为主 |

更细的协议见 [`references/state-protocol.md`](./references/state-protocol.md)。

## License

MIT
