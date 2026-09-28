# Day32 升级：AI 助手（一期 ReAct 3工具极简版）

> 日期：2026-08-27
> 目标：把安全平台从「固定工作流」升级为「自主决策 ReAct 助手」。一期只做「答疑 + 多轮澄清」，不写库不闭环；create_task/权限/MQ/工单 全部留二期当规划讲。
> 前置：Day30 已完成算法(104/199)、隔离级别、RDB/AOF 收尾；Day31 定版 3工具方案。

## 一、本期要做的（一期范围）

**1. 能力：多轮澄清（不是工具，靠 Prompt + Memory）**
- 用户模糊输入（如「路边摆摊挡盲道」）→ 先问全 `行为/地点/持续性/影响` 槽位 → 齐了才查
- 目的：槽位不齐直接检索会幻觉，问清楚准确率才稳（面试核心一句话）

**2. 工具：`search_regulation(keyword)`**（1个读工具）
- 查 `tb_regulation` 表，答「触犯什么法」：盲道/占道经营/无障碍
- 复用 `tools/hybrid_search.py` 的 `searcher.hybrid_search(query, table, vector_k, keyword_k)`
- 关键词 2-8 字短词，不把整句丢进检索

**3. 工具：`search_cases(keyword)`**（1个读工具）
- 查 `tb_hazard_case` 表，答「有啥相同案例」：盲道被占/占道经营
- 复用同一 `searcher.hybrid_search`

**4. 合成（不是工具）**
- 模型把 2+3 结果合成 **三段式 Markdown**：`### 一、触犯法规` / `### 二、安全隐患` / `### 三、类似案例`
- 法规案例必须来自工具返回，没检索到就说「库内暂未检索到」，不编造
- 结尾引导：「需要我按这个情况生成整改建议吗？」

## 二、本期不做的（二期当规划讲，面试不写代码也加分）

- `create_task` 写库（INSERT tb_rectification_task）
- 角色/权限（USER / CONSTRUCTION_TEAM）
- 前端「施工队待办」按钮 + 待办列表
- RabbitMQ 通知推送
- 地图/天气/画图/详细法规爬虫

二期一句话规划：`assignee_team 字段 + role 权限 + 前端施工队按钮 + 创建时发 MQ → ACK 销项`。

## 三、文件改动清单

### Python（ai-module）
| 文件 | 动作 | 说明 |
|---|---|---|
| `tools/assistant_tools.py` | 新建 | 定义 `search_cases` / `search_regulation` 两个 Tool，包 `searcher.hybrid_search` |
| `core/assistant_agent.py` | 新建 | `ASSISTANT_SYSTEM` 多轮澄清 Prompt + `create_assistant_agent()` 返回 `Agent` |
| `server.py` | 修改 | 加 `POST /api/ai/assistant/stream`，复用 `_stream_with_disconnect` |

### Java（safety-web）
| 文件 | 动作 | 说明 |
|---|---|---|
| `AiService.java` | 修改 | 加 `assistantStream(message, sessionId, userId)` 调 Python `/api/ai/assistant/stream` |
| `AiController.java` | 修改 | 加 `POST /api/ai/assistant/stream` 端点（JSON body + Bearer） |

### 前端（云端 `/home/ubuntu/aisafety-platform-frontend`）
| 文件 | 动作 | 说明 |
|---|---|---|
| 新增 AI 助手窗口组件 | 新建 | 悬浮/侧边对话框，复用现有深色科技风（`glass-card`/`btn-glow`/`--color-cyan`） |
| HomeView 入口按钮 | 修改 | 加「AI 助手」入口 |

## 四、全链路测试

1. Python 单测：`assistant_tools` 两个工具返回非空且来自真实表
2. Python 端到端：`curl` 发「路边摆摊挡盲道」→ 应追问；再发「朝阳区朝阳路，每天都这样」→ 应调两个工具出三段式
3. Java 编译：`mvn -pl safety-web -am compile`
4. 全链路：前端窗口 → Java `/api/ai/assistant/stream` → Python `/api/ai/assistant/stream`

## 五、执行顺序 & 验收

- [x] 摸清项目结构（Python/Java/前端位置）
- [x] Python 工具 + Agent + 端点
- [x] py_compile + 单测（4 passed）
- [x] curl 端到端（追问 + 查库）
- [x] Java AiService/AiController 对接（javac 编译通过 + 更新 fat jar）
- [x] 前端 AI 助手窗口（AiAssistant.vue + App.vue 挂载，云端 build 成功）
- [x] 全链路回归（Java->Python->LLM 三段式，Milvus 降级 MySQL，多轮澄清）



