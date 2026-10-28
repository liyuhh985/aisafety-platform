# 总体架构（当前真相）

> 状态：current
> 最后核对：2026-10-11
> 事实来源：当前代码 + 线上部署形态（`docs/deployment/safety-platform-deployment.md`）。

## 1. 运行时拓扑

```text
浏览器 :8081
  -> Nginx /var/www/safety-platform（静态前端）
  -> /api/* -> Java :8080
Java :8080（Spring Boot 3.3.5）
  -> MySQL safety_platform
  -> Redis
  -> MinIO（图片对象，桶 safety-images）
  -> Python AI :8000 /api/ai/*
  -> RabbitMQ :5672（声明拓扑 + 回执发布 + 建单消费）
Python AI :8000（FastAPI + LangGraph）
  -> MiMo 多模态模型
  -> Milvus :19530（可降级 MySQL）
  -> 高德地理编码
  -> RabbitMQ :5672（发布建单消息 + 消费回执；跑在独立 worker 进程）
```

边界规则：

- **前端只调 Java `/api/ai/*`**；Python 不由浏览器直连；SSE 由 Java `SseEmitter` 透传 Python 的 `text/event-stream`。
- **建单走 MQ**：Python 只写 `ai_hazard_create_*` 表并投递消息，Java 只写 `tb_hazard`（见第 6 节与 `docs/current/ai-hazard-create-mq.md`）。

## 2. 代码分层

### Java（Maven 多模块）

```
safety-common   工具/常量/异常
safety-pojo     entity / dto / vo（含 HazardCreateMessage / HazardCreateResult / AiHazardDTO）
safety-service  service + mapper + 缓存 + 状态流转
safety-web      controller + security + ai client + upload + MQ（RabbitConfig / HazardCreateConsumer / HazardCreateResultPublisher）
```

### Python（`ai-module`）

```
server.py               FastAPI 入口（全部 /api/ai/* 路由）
hazard_create_worker.py 建单 MQ worker 独立进程（Relay + ResultConsumer + RequestReconciler + MetricsReporter + RequestRetentionWorker）
config.py / db_config.py
core/                   编排与策略（assistant_graph, dialogue_*, scope_policy, uncertainty...）
tools/                  外部能力（hybrid_search, milvus_store, amap_geo, hazard_submit, hazard_create_queue, java_client, knowledge_sync）
tests/                  pytest
eval/                   检索/分类/报告评测（eval_queries, eval_metrics, eval_retrieval, ...）
db/schema/              建表与迁移（migrate*.py / *.sql）
db/seed/                语料录入与数据修复（data_* / append_* / enrich_* / import_*）
db/experiments/         一次性度量与诊断（measure_* / g1_ / g3_ / g5_）
db/load_hazard_create_mq.py  建单 MQ 压测脚本（运维用）
```

## 3. HTTP 接口面

### 认证 `AuthController` → `/api/auth`

- `POST /send-code`（别名 `/code`）、`POST /login`、`POST /register`

### AI `AiController` → `/api/ai`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | AI 健康检查（匿名） |
| POST | `/analyze` | 非流式分析（兼容/调试） |
| POST | `/analyze/stream` | 旧图片分析 SSE（**兼容接口**） |
| POST | `/assistant/stream` | **当前主链路**，SSE 助手 |
| GET | `/history` | 会话历史 |
| DELETE | `/session` | 清会话 |

> Python 侧另有 `/api/ai/analyze`、`/api/ai/chat`、`/api/ai/chat/stream`、`/api/ai/internal/vectors/delete`、`/api/ai/hazard-create/requests/{id}`。

### 业务

| 前缀 | Controller | 主要接口 |
|------|-----------|----------|
| `/api/hazard` | HazardController | `POST`（上报）/ `GET` / `GET /map`（匿名脱敏）/ `GET /stats`（匿名）/ `GET /{id}` / **`GET /requests/{requestId}`（AI 建单状态查询，代理 Python）** / `GET /ai/requests/{requestId}`（内部对账，校验 `X-Internal-Token`，供 Python `RequestReconciler` 调用）；`assign`、`accept`、`start`、`complete`、`review`、`batch-review`、`withdraw`、`admin-withdraw`、`PUT /{id}/location` |
| `/api/users` | UserController | `GET /handlers`（管理员处理人员目录）/ `PUT /{id}/role`（管理员修改角色并撤销该用户全部 Token） |
| `/api/report` | ReportController | `POST` / `GET` / `GET /{id}` / `DELETE /{id}` |
| `/api/upload` | UploadController | `POST /image` |
| `/api/case` | CaseController | `GET` / `DELETE /{id}` |
| `/api/regulation` | RegulationController | `GET` / `GET /{id}` / `DELETE /{id}` |
| `/api/knowledge` | KnowledgeController | `GET` / `GET /{id}` / `DELETE /{id}` |

## 4. 安全与权限（`SecurityConfig`）

- JWT 密钥由 `JWT_SECRET` 注入；Token 带 `jti`，Redis 保存有效会话；`JwtAuthenticationFilter` 校验验签和服务端会话后注入 `ROLE_USER` / `ROLE_ADMIN` / `ROLE_HANDLER`。
- 匿名：`/api/auth/**`、`/api/ai/health`、`GET /api/case|knowledge|regulation/**`、`GET /api/hazard/map`、`GET /api/hazard/stats`。
- 需登录：`GET /api/hazard`、`GET /api/hazard/{id}`、AI 分析、报告、上传和业务写操作。
- `GET /api/hazard/requests/{requestId}` 需登录并只返回当前用户请求；内部 `/api/hazard/ai/requests/{requestId}` 需 `X-Internal-Token`。
- ASYNC / ERROR dispatcher 放行（避免 SSE 异步派发被误判 403）。
- 方法级：
  - `assign` / `review` / `batch-review` / `admin-withdraw` / `GET /api/users/handlers` → `hasRole('ADMIN')`
  - `assign` 目标用户及 `accept` / `start` / `complete` 操作人需在服务层校验为 `HANDLER`
  - `accept` / `start` / `complete` → `hasRole('HANDLER')`
  - 语料 `DELETE`（case / regulation / knowledge）→ `hasRole('ADMIN')`
  - `withdraw` → 需登录，服务层校验「仅创建人 + 仅 status=0」
  - `admin-withdraw` → 仅 ADMIN，允许 `status=0/1/2 -> 5`，原因写入 `tb_hazard.withdrawn_reason` 与 `ADMIN_WITHDRAW` 留痕

## 5. 数据与缓存

- **MySQL** `safety_platform`：`tb_user`、`tb_file_asset`、`tb_hazard`（含 `request_id` 唯一索引及 `withdrawn_reason` 撤回原因）、`tb_hazard_action`、`tb_hazard_report`、`tb_hazard_case`、`tb_regulation`、`tb_hazard_knowledge`、`tb_vector_sync_outbox`、`tb_resource_cleanup_outbox`、**`ai_hazard_create_request`、`ai_hazard_create_outbox`**（后两张只有 Python 写）。
- **RabbitMQ**：topic exchange `safety.hazard`；`hazard.create`（Java 消费）与 `hazard.create.result.q`（Python 消费）均带 `x-dead-letter-exchange=safety.hazard.dlx`；死信进 `hazard.create.dlq`。
- **Redis**：验证码、Token、限流、缓存、用户级历史记忆。
- **Caffeine**：本地热点缓存（如隐患详情多级缓存 L1）。
- **MinIO** `safety-images`：文件本体；MySQL `tb_file_asset` 保存 `userId/objectKey/status/expiresAt` 元数据。报告保存只接受当前用户上传得到的 `fileId`，不再接受任意 `imageUrl`。临时文件由 `FileAssetCleanupWorker` 定时清理；图片不再暴露 MinIO 公网路径，统一通过需登录的 `GET /api/files/{fileId}` 读取，未绑定业务的临时图片仅上传者本人可读。
- **Milvus**：案例/法规/知识向量；删除走 outbox 最终一致，Python 侧 `/api/ai/internal/vectors/delete` 承接。

## 6. 关键横切

- **AI 建任务（MQ）**：Python 同事务写 `ai_hazard_create_request` + `ai_hazard_create_outbox` → 返回 `accepted(request_id)` → Relay 投递 → Java 幂等写 `tb_hazard` → 回执 → Python 置 `SUCCESS/FAILED`。幂等键 `request_id`；MQ 是唯一建单路径。详见 `docs/current/ai-hazard-create-mq.md`。
- **SSE 取消传播**：浏览器断开 → Java `SseEmitter.onError/onCompletion` → 取消 → Python `CancellationToken` 停止检索/生成。详见 `docs/current/ai-assistant-sse-contract.md`。
- **图片上传**：`multipart/form-data`，单文件 ≤ 10MB；Python 校验真实图片内容，不信任文件名，转 RGB 缩放，临时文件用后清理。
- **报告删除**：删报告 → 硬删 MinIO 图片 → 失败进 `ResourceCleanupOutbox` 重试。
- **向量删除**：语料删除 → 入 `VectorSyncOutbox` → `VectorDeleteOutboxWorker` → Python 向量删除，带重试上限。
- **建单链路的重试/DLX/卡单告警**：Java listener 重试到上限后回 `FAILED` 并丢 DLQ；线上由 `hazard-mq-watchdog.sh`（cron 每 2 分钟）守护 worker 并告警卡单/DLQ，见部署 Runbook。

- **会话 / Checkpoint 后端**：`SESSION_BACKEND`、`CHECKPOINT_BACKEND` 默认 `memory`；云端 Python AI 已使用独立的 `safety-redis-stack` 容器（`127.0.0.1:6380`）并切到 `redis` 模式，health 返回 `effective=redis`。当前目标只是 **单实例 `server.py` 重启后 interrupt 可恢复**，不做多实例部署；Java 侧 Redis 仍在 `6379`。
- **可观测性**：Java 暴露 Actuator/Prometheus（`hazard_create_consume_*`、`hazard_create_result_publish_*`）；Python worker 由 `MetricsReporter` 每 60 秒打 `request / outbox / stuck` 日志。详见 `docs/current/ai-hazard-create-observability.md`。

## 7. 非 MQ 主题（另见独立文档）

以下内容与 MQ 契约无关，当前暂存于 `docs/current/ai-hazard-create-mq.md` 的附录，后续拆分到独立文档：

- **Python MySQL 连接池**：`tools/db_pool.py`（默认池 + 检索池），使用方 `hazard_create_queue` / `core/memory` / `hybrid_search`。
- **LLM 调用链**：主端点重试 → 同供应商备用模型 → 跨供应商降级（DeepSeek）。
- **并发闸门**：Java `streamExecutor` 8+32（超限 429）；Python 图执行在线程池中运行，并按 `userId:sessionId` 做单飞锁（重复 turn 409）。

## 8. 构建与部署

- Java：`mvn package`（缺省 profile `local`）。
- Python：`venv/bin/python3 -u server.py`（端口 8000）；MQ worker 另起 `venv/bin/python3 -u hazard_create_worker.py`（单实例）。
- 部署见 `docs/deployment/safety-platform-deployment.md`（主入口，含 RabbitMQ / worker / 开关 / 回滚）与 `AI_DEPLOYMENT_INDEX.md`、`docs/milvus-remote-runbook.md`。
- 仓库内**无 CI 配置**（无 `.github/workflows/*`、无 Jenkinsfile）；部署目前是手动 Runbook。

## 9. 敏感约定

`.env`、`application-local.yml`、真实密码/密钥/Token 一律不入库、不入文档、不入聊天。

