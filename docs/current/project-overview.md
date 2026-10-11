# 项目总览（当前真相）

> 状态：current
> 最后核对：2026-10-11
> 事实来源：当前代码。与本文冲突的旧文档一律以代码为准。
> 最高规则：当前代码 > current 文档 > 历史设计/计划

## 1. 项目定位

城市安全隐患分析平台：用户上传隐患图片或直接用文字描述，系统做语义理解 → 范围判定 → 案例/法规检索 → 生成分析报告 → 引导建单 → 隐患任务按角色流转闭环。

目标定位是「可面试、可讲解、可持续迭代的 Agent 应用项目」，不是商业生产系统。

## 2. 当前技术栈

### Java 后端（Maven 多模块，Java 21 / Spring Boot 3.3.5）

| 模块 | 职责 |
|------|------|
| `safety-common` | 公共常量、通用能力、异常 |
| `safety-pojo` | DTO / 实体（`Hazard`、`HazardAction`、`User`、`HazardReport` 等）/ VO |
| `safety-service` | 业务服务、Mapper、缓存、状态流转 |
| `safety-web` | Controller、Security、AI 客户端、上传、SSE、MQ 消费与回执 |

关键依赖：Spring Security 6 + JWT、MyBatis-Plus 3.5.7、MySQL、Redis、Caffeine、MinIO、`SseEmitter`、Redisson、**Spring AMQP（RabbitMQ）**。

### Python AI 服务（`ai-module`）

- FastAPI + Uvicorn，入口 `ai-module/server.py`
- LangGraph 编排，核心 `ai-module/core/assistant_graph.py`
- Milvus 向量库（可降级 MySQL）+ MySQL 语料
- 高德地理编码（`tools/amap_geo.py`）
- OpenAI 兼容多模态模型（MiMo），`mimo_client.py`
- **建单链路：Outbox + RabbitMQ（pika），worker 入口 `ai-module/hazard_create_worker.py`**

### 前端 / 部署

- Vue 3 + Vite，云端静态部署
- Nginx（静态 + `/api/*` 反代 + SSE）
- 前端源码不在本仓库：`/home/ubuntu/aisafety-platform-frontend`
- 静态目录：`/var/www/safety-platform`
- **RabbitMQ**：broker `5672` / 管理台 `15672`，topic exchange `safety.hazard`

## 3. 总体架构

```text
浏览器 :8081
  -> Nginx /var/www/safety-platform
  -> /api/* -> Java :8080
Java :8080
  -> MySQL safety_platform
  -> Redis
  -> MinIO（图片对象）
  -> Python AI :8000 /api/ai/*
  <- RabbitMQ :5672（建单消息 / 回执消息）
Python AI :8000
  -> MiMo 多模态模型
  -> Milvus :19530（可降级 MySQL）
  -> 高德地理编码
  -> RabbitMQ：发布建单消息、消费回执（worker 独立进程）
```

分层原则：**前端只调 Java 的 `/api/ai/*`**，Java 再转发给 Python。Python 不直接对浏览器暴露。

## 4. 核心闭环

```
注册/登录
  -> 上传隐患图片 或 直接文字描述
  -> Java 接收并转发 Python
  -> Python：语义理解 + 范围判定 + 案例/法规检索 + 报告生成（SSE 流式）
  -> 报告末尾触发「是否建单」确认（interrupt）
  -> 用户确认（可改地址 / 地图选点）
  -> Python 同事务写 ai_hazard_create_request + ai_hazard_create_outbox，返回 accepted
  -> Relay 发 RabbitMQ → Java 幂等写 tb_hazard（status=0）→ 回执 → Python request 置 SUCCESS
  -> 管理员派单 status=1 -> 处理人整改 status=2 -> 完成 status=3 -> 管理员验收
  -> 支持创建人撤回（status=0 时）-> status=5
  -> 报告/历史查询、删除（删除报告硬删图片）
```

建单链路已收敛为 **MQ 唯一路径**：Python 写 Outbox，RabbitMQ → Java 消费写库 → 回执更新状态，SSE 发 `task_accepted`，前端按 `requestId` 轮询。旧同步 `/api/hazard/ai` 与 `task_created` 已删除。

## 5. 当前能力

- 用户注册/登录、JWT 认证、按角色数据隔离（`0 普通用户 / 1 管理员 / 2 处理人员`）。
- 隐患报告：上传图片、流式分析、保存、历史列表、详情、删除。
- AI 助手：多轮对话、两级隐患分类、范围护栏、不确定性门控、并行检索与自评重试、报告生成。
- 建单闭环：报告后确认卡片 → 地址追问 → 地图选点 → 异步建单（`task_accepted` + 轮询）。
- 建单可靠性：Outbox 至少一次投递、`request_id` 幂等（`tb_hazard.request_id` 唯一索引）、DLX/DLQ、失败重试；回执失败与卡单的处置见「已知边界」。
- 隐患生命周期：派单 / 整改 / 完成 / 验收 / 驳回 / 撤回，`HazardAction` 全量留痕。
- 语料：案例 / 法规 / 知识库；向量同步与删除 outbox。
- 部署：单台云服务器（`106.53.219.214`）承载全部组件 —— Nginx 前端 `8081` / Java `8080` / Python `8000` / MySQL / Redis / Milvus / MinIO / RabbitMQ；MQ worker 由 cron watchdog 守护。

## 6. 已知边界

- 对话规划器存在 **intent 漂移**：同一句输入偶尔被判成另一种产物（已记录，未在代码层根治）。
- 语料只覆盖部分隐患类别：`core/case_relevance.py` 会剔除跨大类的「语义邻近」条目，检索不到时明确回「库内暂未检索到」，不硬凑依据。
- 前端状态文案必须只渲染后端 `status` 事件，禁止在前端再写一套映射。
- 建单 MQ 验收现状（详见 `docs/current/ai-hazard-create-mq.md` 与 `docs/evidence/2026-10-11-hazard-create-mq-load.md`）：
  1. 浏览器端完整确认建单流程已人工验收；
  2. 真实环境 4 组压测已完成：50/500 达到面试级目标（p95=9.062s，0 重复 / 0 丢单 / DLQ=0）；100/1000 暴露 2 vCPU MySQL 死锁边界，作为容量上限记录。
- 敏感信息（`.env`、`application-local.yml`、真实密码/密钥）不得写入文档、Git 或聊天。

## 7. 下一步计划

- 收敛规划器 intent 漂移（同一句输入的产物稳定性）。
- 扩大语料覆盖，减少「库内暂未检索到」。
- 完善检索评测与回归基线（见 `docs/evidence/`）。
- 高并发：50 并发 / 500 单已达面试级目标（p95=9.062s，0 重复 / 0 丢单 / DLQ=0）；100/1000 暴露 2 vCPU 单机 MySQL 写入边界，作为容量上限记录，不再追高（证据见 `docs/evidence/2026-10-11-hazard-create-mq-load.md`）。
- CI/CD 尚未落地（仓库内无 `.github/workflows/*`、无 Jenkinsfile），仅有部署 Runbook。

## 8. 相关文档

- 架构：`docs/current/architecture.md`
- AI 助手 SSE 契约：`docs/current/ai-assistant-sse-contract.md`
- AI 建任务 MQ 契约：`docs/current/ai-hazard-create-mq.md`
- 隐患生命周期：`docs/current/hazard-lifecycle.md`
- Agent 编排：`docs/current/agent-orchestration.md`
- 部署：`docs/deployment/safety-platform-deployment.md`
