---
name: agent-hud
description: 启动并维护可悬挂在 agent 页面旁的自由拖拽浮窗 HUD，展示当前模型的轮次、步数、缓存命中率、上下文用量、今日 Token 用量，以及当前/其他模型在各 AI 平台的余额。Use when the user says 打开 HUD、悬浮窗、监控窗、显示余额、上下文用量、缓存命中率、今日 token、today tokens、token 用量、floating window、agent monitor、show model balance。Works with MiMo Desktop、Claude Code、Codex、Trae、WorkBuddy、DeepSeekHarness via a shared report CLI and optional log adapters. Do NOT use for unrelated UI design or general status questions without starting the HUD workflow.
---

# Agent HUD

可跨 agent 安装的悬浮监控窗：**SKILL.md 负教会 agent 怎么上报**，**Python 浮窗负责展示**。

## 能力

- 置顶、可拖拽、右键菜单的小窗（默认 300×500）
- 每个会话显示：模型、轮次、步数、缓存命中率、上下文用量/上限、今日 Token、状态
- 全局「今日 Token」跨会话累计（本地日期跨零点自动重置）
- 按模型匹配余额；并列出其他平台/模型余额
- 任意 agent 通过 `report.py` 自上报；本地日志 adapter 做兜底扫描

## Important

1. 上报路径与启动命令必须用本 skill 目录下的脚本，不要临时改到别的位置。
2. Windows 上优先用 `$env:MIMO_PYTHON`；若未设置，用系统 `python` / `py`。
3. 配置文件在 `%LOCALAPPDATA%\agent-hud\config.json`（首次运行从 `config.example.json` 复制）。**API Key 只写在这里，不要写进 SKILL 或聊天记录。**
4. 浮窗是独立进程：启动后可挂在任意 agent 窗口旁；skill 调用方不需要一直阻塞。
5. 上报应轻量：每次用户回合结束或步数变化时调用一次即可，不要每个工具调用都刷。

## 脚本约定

| 脚本 | 作用 |
|------|------|
| `scripts/start_hud.py` | 启动浮窗（单实例） |
| `scripts/report.py` | 会话自上报（所有平台共用） |
| `scripts/collect.py` | adapter 扫描 / 拉余额 / 列会话 |

设 `SKILL` 为本 skill 根目录绝对路径，例如：

`C:\Users\<user>\.claude\skills\agent-hud`

### 启动浮窗

```powershell
# Windows (MiMo Desktop)
$py = if ($env:MIMO_PYTHON) { $env:MIMO_PYTHON } else { "python" }
Start-Process -WindowStyle Hidden $py -ArgumentList "$env:USERPROFILE\.claude\skills\agent-hud\scripts\start_hud.py"
```

```bash
# macOS / Linux
python3 ~/.claude/skills/agent-hud/scripts/start_hud.py &
```

若已运行会打印 `HUD already running`，这是成功。

### 自上报（所有 agent 通用）

```bash
python "$SKILL/scripts/report.py" \
  --agent mimo \
  --session "$SESSION_ID" \
  --model "mimo-v2.5-pro" \
  --turn 12 \
  --step 45 \
  --cache-hit-rate 0.72 \
  --cache-read-tokens 12000 \
  --cache-write-tokens 1500 \
  --input-tokens 3000 \
  --output-tokens 400 \
  --context-used 45000 \
  --context-limit 200000 \
  --status working
```

字段说明：

- `--agent`: `mimo` | `claude-code` | `codex` | `trae` | `workbuddy` | `deepseek-harness` | 自定义 id
- `--session`: 稳定会话 id（会话标题 / thread id / 文件名 stem）
- `--cache-hit-rate`: 0~1；若只有 token 数，改传 `--cache-read-tokens` / `--cache-write-tokens` / `--input-tokens`，脚本会自动算命中率
- `--context-used` / `--context-limit`: 上下文窗口占用
- `--status`: `working` | `idle` | `error`
- `--balance`: 可选，临时覆盖当前模型余额展示

### 今日 Token 上报

今日 Token 存在 `%LOCALAPPDATA%\agent-hud\daily.json`（Unix: `~/.local/share/agent-hud/daily.json`），按本地日期跨零点自动清零。

任选一种写法（不要在同一命令里混用多种增量语义，除非你清楚结果）：

```bash
# A. 增量：本回合新消耗 N token
python report.py --agent mimo --session "$SID" --add-tokens 1500

# B. 绝对值：该会话今天累计用了 N token
python report.py --agent mimo --session "$SID" --tokens-today 28000

# C. 会话累计（推荐，能自动算正增量）：input+output+cache 的会话累计值
python report.py --agent mimo --session "$SID" \
  --session-total-tokens 52000 \
  --input-tokens 3000 --output-tokens 400 \
  --cache-read-tokens 12000 --cache-write-tokens 1500

# 仅传 usage 快照时，也会把 input+output+cache_read+cache_write 之和当作 session_total 处理
```

查看 / 重置：

```bash
python report.py --agent mimo --show-daily
python report.py --agent mimo --reset-daily   # 清空今日全部计数
python collect.py --daily
```

浮窗展示：摘要行「今日 xxx」为全局合计；指标「今日Token」为 `本会话今日 / 全局今日 · 会话累计`。

### 拉余额 / 扫描

```bash
python "$SKILL/scripts/collect.py" --balances
python "$SKILL/scripts/collect.py" --scan --list --daily
```

## Instructions

### Step 1 — 确认并启动 HUD

1. 若用户要求打开 HUD / 悬浮窗 / 监控窗：
   - 解析平台，选上面的启动命令执行。
   - 提示用户：窗口默认置顶，可拖拽；右键菜单可刷新、改透明度、切换会话、退出。
2. 若用户要配置余额：
   - 打开/创建 `%LOCALAPPDATA%\agent-hud\config.json`
   - 只启用需要的 provider（`enabled: true`），填入 API Key
   - 运行 `collect.py --balances`

### Step 2 — 建立当前会话上报

在用户当前对话中选定 `session_id`（优先用平台真实 id；否则用短哈希或会话标题 slug）。然后：

1. 立刻 `report.py` 一次，让浮窗出现当前模型。
2. 此后在下列时机再上报（字段有多少传多少，缺省不传）：
   - 每次用户回合结束
   - 长任务每完成一个主要步骤
   - 用户问「上下文还剩多少 / 花了多少」时，把已知 token 写入 `--context-used` / `--context-limit`
   - 每次能拿到 usage 时更新 token 字段（见「今日 Token 上报」），保证今日计数增长
   - 模型切换时立刻更新 `--model`

### Step 3 — 按平台补齐数据

#### MiMo Desktop / Claude Code

优先自上报；可选扫描本地 transcript 增强：

```bash
python "$SKILL/scripts/collect.py" --scan
```

adapter 会读 `~/.claude/projects/**/*.jsonl`，从 `message.usage` 提取 cache / input / output tokens。`cache_hit_rate ≈ cache_read / (cache_read + cache_write + input)`。

#### Codex

```bash
# 自上报
python report.py --agent codex --session "$CODEX_SESSION" --model "$MODEL" ...

# 兜底扫描 ~/.codex/sessions
python collect.py --scan
```

#### Trae

Trae 无统一公开 hook 时，以自上报为主：

```bash
python report.py --agent trae --session "$SESSION" --model "$MODEL" --turn N --step M --status working
```

可先 `collect.py --scan` 试扫 `workspaceStorage`；扫不到不要硬凑数据。

#### WorkBuddy

```bash
python report.py --agent workbuddy --session "$SESSION" --model "$MODEL" ...
```

#### DeepSeekHarness

```bash
python report.py --agent deepseek-harness --session "$SESSION" --model deepseek-chat ...
```

余额若走 DeepSeek 官方，配置：

```json
{
  "id": "deepseek",
  "name": "DeepSeek",
  "type": "deepseek",
  "api_key": "sk-...",
  "models": ["deepseek-chat", "deepseek-reasoner"],
  "enabled": true
}
```

### Step 4 — 多会话同时挂

每个 agent / 每个对话使用不同 `--session`（和合理不同的 `--agent`）。浮窗会在会话列表间轮播；右键「下一个会话」可手动切换。

## Examples

**用户：打开 HUD，把当前对话的上下文和模型余额挂上去**

1. 启动 `start_hud.py`
2. `report.py --agent mimo --session <id> --model <model> --status working --add-tokens 0`
3. 若已配 provider，`collect.py --balances`
4. 告知：拖动标题栏移动，右键打开菜单；今日 Token 在摘要与指标区可见

**用户：我换了 deepseek，余额也显示一下**

1. `report.py --agent ... --session ... --model deepseek-chat ...`
2. 确认 config 中 deepseek provider `enabled: true` 且 Key 有效
3. `collect.py --balances`

**用户：Codex 那边也挂上**

1. 在 Codex 会话中（或本会话代为）对 Codex 项目目录跑 `report.py --agent codex ...`
2. 可选 `collect.py --scan` 读 `~/.codex/sessions`

## Troubleshooting

| 现象 | 原因 | 处理 |
|------|------|------|
| 浮窗没弹出 | 被单实例挡住或 Tk 不可用 | 查 `%LOCALAPPDATA%\agent-hud\hud.pid`；换 `MIMO_PYTHON` 再启 |
| 会话不显示 | 超过 `session_max_age_sec` | 重新 `report.py`；右键清理后重报 |
| 缓存命中率是 — | 只有 turn/step 没有 token | 补 `--cache-read-tokens` 等，或跑 `--scan` |
| 今日 Token 不涨 | 只报了 turn/step，没有 usage 或 `--add-tokens` | 每回合带 usage 或 `--add-tokens`/`--tokens-today` |
| 今日 Token 虚高 | 把每次请求的 cumulative 又当成增量相加 | 用 `--session-total-tokens` 或 usage 快照，不要对 cumulative 反复 `--add-tokens` |
| 余额全是 — | provider 未启用 / Key 无效 / 接口不匹配 | 读 `raw_note`；改用 `type: manual` 手动填 |
| 中转站余额数量级怪 | new-api quota 以 500000 = $1 计 | 确认用的是 `access_token`；必要时改 `manual` |
| 想换数据目录 | — | 设 `AGENT_HUD_CONFIG` 指向自定义 config.json |

## 安全

- 不要把用户粘贴的 API Key 写入会话上报内容或 git 仓库。
- 配置文件权限：Windows 默认用户目录即可；不要同步到公开仓库。
- `collect.py --balances` 会向已配置的 base_url 发 HTTPS GET。

## 参考

- 状态协议：`references/state-protocol.md`
- 今日 Token：`daily.json` + `report.py --add-tokens / --tokens-today / --session-total-tokens`
- 平台适配：`references/platforms.md`
- 余额 provider：`references/balance-providers.md`
