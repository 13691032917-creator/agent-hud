# 余额 Provider 参考

在 `config.json` 的 `providers[]` 配置。公共字段：

| 字段 | 说明 |
|------|------|
| id | 唯一 id |
| name | HUD 显示名 |
| type | 见下表 |
| api_key / access_token | 密钥（按 type） |
| base_url | 自定义网关 |
| models | 用于匹配当前模型的名称列表；省略则显示为 `(provider balance)` |
| enabled | 必须为 `true` 才查询 |
| currency | 默认 USD |
| amount / note | 仅 `type: manual` |

## 支持的 type

| type | 说明 |
|------|------|
| `deepseek` | 官方 `GET https://api.deepseek.com/user/balance` |
| `openai` | 默认 api.openai.com 的 billing 探测（可能随官方策略失效） |
| `openai_compatible` | 任意 OpenAI 风格 base_url + Bearer |
| `new_api` / `one_api` | 中转站；`access_token`；quota 常按 500000 = $1 |
| `openrouter` | `GET https://openrouter.ai/api/v1/credits` |
| `anthropic` | 尝试常见 usage/billing 路径（官方未必开放） |
| `moonshot` | `GET /v1/users/me/balance` |
| `siliconflow` | `GET /v1/user/info` → balance |
| `manual` | 用户手填 `amount`，不发起网络请求 |

## 模型匹配

HUD 显示「当前模型余额」时：

1. 精确匹配 `models[]` 中与当前会话 `model` 相同的名字  
2. 否则匹配 `(provider balance)` 占位行（provider 级余额）  
3. 都失败则显示自上报的 `--balance` 或 —

## 推荐安全实践

- 密钥只放本地 `config.json`，不要进 git。
- 中转站优先使用只读/计费查询权限的 token（若平台支持）。
- 公共电脑上用完可把 provider `enabled: false`。
- 接口失败时查看 `balances.json` 里对应行的 `raw_note`。

## 示例：同时挂官方 + 中转 + 手动

```json
{
  "providers": [
    {
      "id": "deepseek",
      "name": "DeepSeek",
      "type": "deepseek",
      "api_key": "sk-...",
      "models": ["deepseek-chat", "deepseek-reasoner"],
      "enabled": true
    },
    {
      "id": "gw",
      "name": "公司中转",
      "type": "new_api",
      "base_url": "https://gw.example.com",
      "access_token": "tok-...",
      "models": ["claude-sonnet-4-20250514", "mimo-v2.5-pro"],
      "enabled": true
    },
    {
      "id": "bank",
      "name": "手动记账",
      "type": "manual",
      "amount": 30,
      "currency": "USD",
      "models": ["local-llama"],
      "enabled": true
    }
  ]
}
```
