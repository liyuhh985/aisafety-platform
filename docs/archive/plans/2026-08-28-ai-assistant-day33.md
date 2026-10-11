> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Day33 计划：AI 助手一期收尾 — 图文 + 模型降级

> 日期：2026-08-28
> 前置：Day32 一期 2 工具（search_regulation/search_cases + 多轮澄清 + SSE 流式 + 6 条历史 + loadHistory）已通
> 目标：让一期助手“图文都支持、超时可降级”，不扩 scope

## 一、本期要做

### 1. 图文支持 — analyze_image 工具
- tools/assistant_tools.py 新增 ANALYZE_IMAGE_TOOL，复用 MiMoVisionClient.analyze_json
- core/assistant_agent.py SYSTEM 加一句图文

### 2. 模型降级 — 主备切换（备 = mimo-v2.5）
- config.py 新增 MIMO_MODEL_BACKUP = os.getenv("MIMO_MODEL_BACKUP", "mimo-v2.5")
- core/agent.py _call_llm 加主备降级（Timeout/429/5xx 时切备，打 [FALLBACK] 日志）

## 二、本期不做
- create_task / 权限 / MQ / 地图

## 三、文件改动
- ai-module/tools/assistant_tools.py
- ai-module/core/assistant_agent.py
- ai-module/config.py
- ai-module/core/agent.py

## 四、验证
- py_compile + pytest
