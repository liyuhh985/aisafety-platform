# 模型配置

> 状态：current
> 最后核对：2026-11-24
> 事实来源：`ai-module/config.py`、`ai-module/core/agent.py`、`ai-module/mimo_client.py` 和部署 `.env`

## 当前供应商

项目统一使用 OpenDesign 的 OpenAI-compatible 端点：

```env
OPENDESIGN_BASE_URL=https://amr-link.open-design.ai/v1
OPENDESIGN_VISION_MODEL=deepseek-v4.1-flash
```

当前文本、小模型和视觉均使用：

```text
deepseek-v4.1-flash
```

## 槽位

| 槽位 | 用途 | 环境变量前缀 | 当前继承/配置 |
|---|---|---|---|
| `text` | 报告、理解、Skill 路由、长回答 | `LLM_TEXT_` | OpenDesign `deepseek-v4.1-flash` |
| `small` | 追问、地址抽取、检索词改写 | `LLM_SMALL_` | 未单独配置时继承 `LLM_TEXT_` |
| `vision` | 图片识别 | `LLM_VISION_` | 未单独配置时继承 `LLM_TEXT_` |

## 推荐配置

```env
VISION_PROVIDER=opendesign
OPENDESIGN_BASE_URL=https://amr-link.open-design.ai/v1
OPENDESIGN_API_KEY=sk-...
OPENDESIGN_VISION_MODEL=deepseek-v4.1-flash

LLM_TEXT_PROVIDER=opendesign
LLM_TEXT_BASE_URL=https://amr-link.open-design.ai/v1
LLM_TEXT_API_KEY=sk-...
LLM_TEXT_MODEL=deepseek-v4.1-flash
```

说明：

- `LLM_SMALL_*` 未配置时继承 `LLM_TEXT_*`。
- `LLM_VISION_*` 未配置时继承 `LLM_TEXT_*`。
- `VISION_PROVIDER=opendesign` 时，视觉客户端优先使用 `OPENDESIGN_*`。
- 真实 API Key 只能放在 Git 忽略的 `ai-module/.env`，不得写入 `.env.example` 或源码。

## 单独覆盖槽位

例如只让 small 使用另一模型：

```env
LLM_SMALL_PROVIDER=opendesign
LLM_SMALL_BASE_URL=https://amr-link.open-design.ai/v1
LLM_SMALL_API_KEY=sk-...
LLM_SMALL_MODEL=deepseek-v4.1-flash
```

每个槽位支持：

```text
PROVIDER
BASE_URL
API_KEY
MODEL
EFFORT
MAX_TOKENS
TEMPERATURE
```

## 调用链

```text
槽位主端点（LLM_TEXT_* / LLM_SMALL_* / LLM_VISION_*）
  -> 可选跨供应商降级（FALLBACK_LLM_* 三件套齐全时）
```

当前主配置为 OpenDesign。只有未配置完整槽位时，才回落到旧 `MIMO_*` / `DEEPSEEK_*` / `PRIMARY_LLM_*` 兼容变量。

## 全量旧前缀

新的部署不应再配置 `MIMO_*`。代码中保留这些常量只是为了兼容旧脚本和旧环境变量；项目主链路由 `LLM_*` 和 `OPENDESIGN_*` 控制。

## 运行时查看

`GET /api/ai/health` 返回 `models.text / models.small / models.vision`，用于确认实际生效的 provider、model 和配置状态。

修改 `.env` 后必须重启：

- `ai-module/server.py`
- `ai-module/hazard_create_worker.py`（若独立运行）
