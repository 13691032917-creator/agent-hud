# 平台适配指南

## 总原则

1. **自上报优先**（`report.py`）：字段最准，跨平台最稳。
2. **本地 adapter 兜底**：只在日志路径稳定、mtime 足够新时写入。
3. **不要伪造数据**：扫不到就保持 `—`，并在 note 里说明。

## 各平台要点

### MiMo Desktop

- 会话与技能体系兼容 Claude 风格 transcript。
- 建议 `--agent mimo`，`--session` 用会话标识。
- `collect.py --scan` 会尝试 `~/.claude/projects/**/*.jsonl`；若 MiMo 使用其它项目根，可在扩展 adapter 时增加环境变量 `AGENT_HUD_CLAUDE_PROJECTS`。

### Claude Code

- Hooks（`SessionEnd` / `Stop` / 自定义 PostToolUse）里调用 `report.py` 最合适。
- usage 字段与协议中的 cache 字段一一对应。

### Codex (OpenAI)

- 自上报 `--agent codex`。
- adapter 扫描 `~/.codex/sessions` 下 jsonl；mtime > 10 分钟视为不活跃。

### Trae

- 工作区可能在 `%APPDATA%\Trae\User\workspaceStorage` 或 `Trae CN`。
- 版本差异大：scan 仅 best-effort；生产路径要求 agent 自己 `report.py`。

### WorkBuddy

- 目前无稳定公开 API 假设；以自上报为主。
- 若发现固定数据目录，可仿照 `scan_workbuddy` 增强。

### DeepSeekHarness

- 自上报 `--agent deepseek-harness`。
- 模型名建议与 DeepSeek API 一致（`deepseek-chat` / `deepseek-reasoner`），便于余额匹配。

## 新增 adapter 步骤

1. 在 `scripts/agent_hud/adapters.py` 增加 `scan_xxx()`，返回 `AdapterResult`。
2. 在 `run_all_adapters()` 挂上。
3. 只保留「mtime 新鲜 + 能解析出 model/usage」的文件。
4. 补充本文件与 `SKILL.md` 的平台小节。

## 多窗口共存

- 浮窗全局单实例。
- 多个 agent 同时写不同 `sessions/<agent>__<sid>.json`。
- 同名冲突时用不同 `--session`。
