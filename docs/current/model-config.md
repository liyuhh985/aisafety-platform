# 模型三槽位配置

文本、小模型、视觉各自独立配置，互不影响。当前三套都指向 DeepSeek。

## 槽位

| 槽位 | 用途 | 环境变量前缀 |
|---|---|---|
| `text` | 报告生成、长回答 | `LLM_TEXT_` |
| `small` | 意图规划、槽位抽取、检索词改写、地址抽取 | `LLM_SMALL_` |
| `vision` | 图片识别 | `LLM_VISION_` |

每个槽位支持以下变量（以 `LLM_TEXT_` 为例）：

```env
LLM_TEXT_PROVIDER=deepseek
LLM_TEXT_BASE_URL=https://api.deepseek.com
LLM_TEXT_API_KEY=sk-...
LLM_TEXT_MODEL=deepseek-flash
LLM_TEXT_EFFORT=low
LLM_TEXT_MAX_TOKENS=
LLM_TEXT_TEMPERATURE=
```

`LLM_SMALL_*` / `LLM_VISION_*` 同理。

## 当前线上配置

| 槽位 | provider | model |
|---|---|---|
| text | deepseek | deepseek-flash |
| small | deepseek | deepseek-flash |
| vision | deepseek | deepseek-flash |

视觉额外设置了 `LLM_VISION_MAX_TOKENS=1500`：`deepseek-flash` 会先输出 `reasoning_content`，token 给少了会出现正文为空、全被推理吃掉。

## 怎么切换

只改 `.env`，重启 AI 服务（`server.py` 与 `hazard_create_queue` worker）。

例如把文本换成 v4-pro，小模型和视觉保持 flash：

```env
LLM_TEXT_MODEL=deepseek-v4-pro
LLM_SMALL_MODEL=deepseek-flash
LLM_VISION_MODEL=deepseek-flash
```

## 代码里的映射

- `core/agent.py`：`Agent(slot="text" | "small")`；未显式指定时按注册名判断，`hazard_extract / hazard_address_extract / dialogue_planner / rewrite_query` 走 small。
- `mimo_client.py`：`VISION_PROVIDER=deepseek` 时使用 `LLM_VISION_*`。
- `GET /api/ai/health` 返回 `models.text / models.small / models.vision`，用于确认线上实际生效的配置。

## 兼容

旧的 `MIMO_*` / `FALLBACK_LLM_*` / `PRIMARY_LLM_*` 仍保留为兜底：当某个槽位没配齐 base_url/api_key/model 时，会回落到这些旧配置。

