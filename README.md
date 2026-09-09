# Agent HUD

璺?agent 鐨?*鍙嫋鎷界疆椤舵诞绐?*锛氭樉绀哄綋鍓嶆ā鍨嬬殑杞銆佹鏁般€佺紦瀛樺懡涓巼銆佷笂涓嬫枃鐢ㄩ噺銆?*浠婃棩 Token**锛屼互鍙婂綋鍓?鍏朵粬妯″瀷鍦ㄥ悇 AI 骞冲彴鐨勪綑棰濄€?
鏀寔锛?*MiMo Desktop 路 Claude Code 路 Codex 路 Trae 路 WorkBuddy 路 DeepSeekHarness**锛堝強浠讳綍鑳芥墽琛?Python 鐨?agent锛夈€?
```
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹?Agent HUD            PIN 脳  鈹?鈹?mimo 路 ses_xxx              鈹?鈹?妯″瀷 mimo-v2.5-pro  $12.40  鈹?鈹?浠婃棩 128.0k                 鈹?鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹?妯″瀷     mimo-v2.5-pro      鈹?鈹?杞     12                 鈹?鈹?姝ユ暟     45                 鈹?鈹?缂撳瓨鍛戒腑 72.0%              鈹?鈹?涓婁笅鏂?  45k / 200k (22.5%) 鈹?鈹?浠婃棩Token 30.0k / 鍏ㄥ眬 128.0k鈹?鈹?鐘舵€?    working            鈹?鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹?浣欓                        鈹?鈹?褰撳墠 路 DeepSeek             鈹?鈹?  deepseek-chat  $12.40     鈹?鈹?鍏朵粬浣欓 鈥?                 鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?```

## 鐗规€?
- 鏍囬鏍忚嚜鐢辨嫋鎷斤紝榛樿缃《锛屽彲璋冮€忔槑搴?- 澶氫細璇濆苟鍒楋紝鍙抽敭鍒囨崲
- **浠婃棩 Token** 鍏ㄥ眬/鍒嗕細璇濈疮璁★紝鏈湴鏃ユ湡璺ㄩ浂鐐硅嚜鍔ㄩ噸缃?- `report.py` 缁熶竴鑷笂鎶ュ崗璁紙鍏ㄥ钩鍙帮級
- 鍙€夋湰鍦版棩蹇?adapter 鍏滃簳鎵弿锛圕laude / Codex / Trae 绛夛級
- 浣欓鏀寔 DeepSeek銆丱penAI銆丱penRouter銆丮oonshot銆丼iliconFlow銆乶ew-api/one-api 涓浆绔欍€佹墜鍔ㄤ綑棰?
## 瀹夎

### 鏂瑰紡 A锛氫綔涓?Claude / MiMo 鎶€鑳?
```powershell
git clone https://github.com/13691032917-creator/agent-hud.git
# Windows
Copy-Item -Recurse agent-hud "$env:USERPROFILE\.claude\skills\agent-hud"
# 鎴?macOS / Linux
# cp -R agent-hud ~/.claude/skills/agent-hud
```

鏂板璇濅腑璇达細**銆屾墦寮€ HUD銆?* / **銆屾偓娴獥銆?*銆?
### 鏂瑰紡 B锛氫粎浣滀负妗岄潰娴獥锛堜笉瑁呮妧鑳斤級

```bash
python scripts/start_hud.py
python scripts/report.py --agent myagent --session demo --model deepseek-chat --turn 1 --step 1
```

渚濊禆锛?*Python 3.10+**锛屾爣鍑嗗簱 `tkinter`锛圵indows 瀹樻柟瀹夎鍖呰嚜甯︼級銆?
## 蹇€熷紑濮?
### 1. 鍚姩娴獥

```powershell
# Windows
scripts\start_hud.cmd
# 鎴?python scripts/start_hud.py
```

### 2. 涓婃姤浼氳瘽

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

缂撳瓨鍛戒腑鐜囧彲鑷姩璁＄畻锛?
`cache_hit = cache_read / (cache_read + cache_write + input)`

### 浠婃棩 Token

```bash
# 鏈洖鍚堟柊澧?python scripts/report.py --agent mimo --session main --add-tokens 1500

# 鎴栦細璇濈疮璁★紙鑷姩鍙栨澧為噺璁″叆浠婃棩锛?python scripts/report.py --agent mimo --session main --session-total-tokens 52000

# 鏌ョ湅 / 閲嶇疆
python scripts/report.py --agent mimo --show-daily
python scripts/report.py --agent mimo --reset-daily
python scripts/collect.py --daily
```

鏁版嵁鏂囦欢锛歚daily.json`锛堜笌浼氳瘽鐘舵€佸悓鐩綍锛夛紝鎸?*鏈湴鏃ユ湡**鍦ㄥ崍澶滆嚜鍔ㄦ竻闆躲€?
### 3. 閰嶇疆浣欓

棣栨杩愯鍚庣紪杈戯細

- Windows: `%LOCALAPPDATA%\agent-hud\config.json`
- macOS/Linux: `~/.local/share/agent-hud/config.json`

绀轰緥瑙佷粨搴撳唴 [`config.example.json`](./config.example.json)銆傛妸 provider 鐨?`enabled` 璁句负 `true` 骞跺～鍏?API Key锛岀劧鍚庯細

```bash
python scripts/collect.py --balances
```

> **瀹夊叏**锛氱湡瀹?`config.json` 涓嶈鎻愪氦鍒?Git锛涙湰浠撳簱 `.gitignore` 宸叉帓闄ゃ€?
## 鐩綍

```
agent-hud/
鈹溾攢鈹€ SKILL.md                 # 鎶€鑳借鏄庯紙缁?agent锛?鈹溾攢鈹€ config.example.json      # 浣欓/UI 閰嶇疆妯℃澘
鈹溾攢鈹€ locales/                 # 鎻掍欢椤靛睍绀烘枃妗?鈹溾攢鈹€ references/              # 鍗忚涓庡钩鍙版枃妗?鈹斺攢鈹€ scripts/
    鈹溾攢鈹€ start_hud.py         # 鍚姩娴獥
    鈹溾攢鈹€ start_hud.cmd
    鈹溾攢鈹€ report.py            # 鑷笂鎶?CLI
    鈹溾攢鈹€ collect.py           # 鎵弿 / 浣欓 / 鍒楄〃
    鈹斺攢鈹€ agent_hud/           # 瀹炵幇鍖?```

## 鏁版嵁钀界洏浣嶇疆

| 鍐呭 | Windows | Unix |
|------|---------|------|
| 浼氳瘽鐘舵€?| `%LOCALAPPDATA%\agent-hud\sessions\` | `~/.local/share/agent-hud/sessions/` |
| 閰嶇疆 | `%LOCALAPPDATA%\agent-hud\config.json` | 鍚屼笂鐩綍涓?|
| 浣欓缂撳瓨 | `balances.json` | 鍚屼笂 |

鍙敤鐜鍙橀噺 `AGENT_HUD_CONFIG` 瑕嗙洊閰嶇疆璺緞銆?
## 鍚勫钩鍙版帴鍏ヨ鐐?
| 骞冲彴 | 寤鸿 |
|------|------|
| MiMo / Claude Code | `--agent mimo` / `claude-code`锛涘彲 `collect.py --scan` 璇?`~/.claude/projects/**/*.jsonl` |
| Codex | `--agent codex`锛涘彲鎵?`~/.codex/sessions` |
| Trae / WorkBuddy / DeepSeekHarness | 浠?`report.py` 鑷笂鎶ヤ负涓?|

鏇寸粏鐨勫崗璁 [`references/state-protocol.md`](./references/state-protocol.md)銆?
## License

MIT
## 与 DeepSeekHarness / DSH

本仓库是 **跨 agent 技能包 + Python 浮窗**，不是 DSH 原生 cordis 插件（无 package.json / dsh 清单），因此不能走 DSH 插件市场安装。

推荐用法：

1. Clone 本仓库到 ~/.claude/skills/agent-hud（或任意路径）
2. 运行 python scripts/start_hud.py
3. DSH 会话内让 agent 调用 scripts/report.py --agent deepseek-harness --session <id> --model <name> ...

