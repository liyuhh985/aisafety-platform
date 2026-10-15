# AI 建任务：MQ + Outbox 契约（当前真相）

> 状态：current
> 最后核对：2026-10-14
> 事实来源：当前代码（`ai-module/tools/hazard_create_queue.py`、`ai-module/hazard_create_worker.py`、`ai-module/server.py`、`safety-web/.../RabbitConfig.java`、`HazardCreateConsumer.java`、`HazardCreateResultPublisher.java`、`HazardServiceImpl.createAi`）+ 线上运行形态（队列 `hazard.create` / `hazard.create.result.q` / `hazard.create.dlq` 存在，worker 进程在跑）。
> 关联：`docs/current/ai-assistant-sse-contract.md`、`docs/current/hazard-lifecycle.md`、`docs/deployment/safety-platform-deployment.md`

## 0. 目标与非目标

**目标**：把「Python 确认建单 → Java 写 `tb_hazard`」这段同步 HTTP 解耦成异步消息，用户确认后**立即返回 accepted**，且 Python 崩溃 / RabbitMQ 短暂不可用都不丢单。

**非目标**：不拆微服务、不拆库、不让 Python 直接写 `tb_hazard`。

## 0.1 当前实现状态与未完成项

已经在跑：Outbox 同事务落库、Relay 至少一次投递、Java 幂等消费（`tb_hazard.request_id` 唯一索引）、建单队列 DLX、回执队列 DLX、`GET /api/hazard/requests/{requestId}` 状态查询、双端开关（线上已 `true`）。

**2026-10-11 代码加固已完成**：

- 回执发送失败不再吞异常：`HazardCreateResultPublisher` 抛回 listener 触发重试；`createAi` 幂等保证重试不会重复建单。
- 新增 `RequestReconciler`：超时 `PENDING/PUBLISHED` 会查 Java 内部 `GET /api/hazard/ai/requests/{requestId}`，已落库则补 `SUCCESS`，未落库则把 outbox 改 `RETRY` 重新投递；重试耗尽转 `FAILED`。
- 新增 `RabbitConfigTest` / `HazardCreateResultPublisherTest` / `HazardCreateConsumerTest`：覆盖拓扑 DLX、回执失败抛出、缺 requestId 拒绝、重复消息补发回执。

**2026-10-11 已部署验证**：

- Redis Stack（`safety-redis-stack`，`127.0.0.1:6380`）已上线；health 显示 `session_backend.effective=redis`、`checkpoint_backend.effective=redis`。
- 进程 A 暂停 interrupt → 进程 B 读取 `next=('gate',)` 并成功 resume，验证了重启后 interrupt 可恢复。
- Java/Python 新包已部署；结果队列已删除重建，`hazard.create.result.q` 现带 `x-dead-letter-exchange`，worker 不再 406。
- 受控 MQ 端到端：Python 入队 → RabbitMQ → Java 写 `tb_hazard` → 回执 → Python 状态 `SUCCESS`（hazardId=3974，测试数据已清理）。

**尚未完成（不得按已完成描述）**：

| 项 | 现状 | 后果 |
|---|---|---|
| 浏览器端完整确认 | 云端 `HomeView.vue` 已合入 `task_accepted` + 轮询；页面级完整验收已由用户确认 | 无 |
| 真实环境压测 | 4 组已完成：50/500 达到面试级目标（p95=9.062s，0 重复 / 0 丢单 / DLQ=0）；100/1000 暴露 2 vCPU MySQL 死锁边界（19/1000 提交失败） | 50 并发已达标；100+ 是硬件边界，不再无限追高 |

压测证据见 `docs/evidence/2026-10-11-hazard-create-mq-load.md`。

## 1. 架构与唯一写入者

```
用户确认建单
  → Python 本地事务：INSERT ai_hazard_create_request + INSERT ai_hazard_create_outbox
  → 立即返回 accepted(request_id)          ← 先写库再返回，绝不反过来
  → Relay（独立进程）扫 outbox → 发 RabbitMQ
  → Java 消费 → 幂等写 tb_hazard（request_id 唯一索引）
  → Java 发回执消息 hazard.create.result
  → Python 消费回执 → 更新自己的 request 状态
  → 前端按 request_id 轮询状态
```

**写入权边界（硬约束）**
- `ai_hazard_create_request` / `ai_hazard_create_outbox`：**只有 Python 写**，Java 一行都不写。
- `tb_hazard`：**只有 Java 写**，Python 通过 MQ 间接触发。
- 两者共用同一个 MySQL `safety_platform`（一期不拆库）。

## 2. 数据表

### 2.1 `ai_hazard_create_request`（Python 侧，幂等主体）
`request_id`(PK) / `user_id` / `session_id` / `payload` / `status` / `hazard_id` / `error_message` / `created_at` / `updated_at`

状态机（**4 态**，去掉 CREATING）：
```
PENDING    request+outbox 已同事务写入，还没发 MQ
PUBLISHED  已成功投递到 RabbitMQ
SUCCESS    Java 回执：tb_hazard 创建成功（hazard_id 非空）
FAILED     最终失败（Relay 超上限 / Java 回执失败 / DLQ）
```
> 为什么去掉 `CREATING`：它要求 Java 额外回一条「我开始处理了」，多一跳消息换一个中间态，收益低。前端对 `PENDING/PUBLISHED` 统一显示「创建中」即可。

### 2.2 `ai_hazard_create_outbox`（Python 侧）
`id` / `request_id` / `event_type` / `payload` / `status` / `retry_count` / `next_retry_time` / `locked_at` / `last_error` / `created_at` / `updated_at`

- `status`：`PENDING / PUBLISHING / PUBLISHED / RETRY / FAILED`
- `request_id` 唯一索引（一个请求一行）。
- claim/退避语义照抄 Java 现有 outbox（`VectorSyncOutboxMapper` / `ResourceCleanupOutboxMapper`）。

### 2.3 `tb_hazard`（Java 侧）
```sql
ALTER TABLE tb_hazard ADD COLUMN request_id VARCHAR(64) NULL;
ALTER TABLE tb_hazard ADD UNIQUE INDEX uk_tb_hazard_request_id (request_id);
```
MySQL 唯一索引允许多个 `NULL`，存量行不受影响。

### 2.4 建表脚本
`ai-module/db/schema/migrate_hazard_create_mq.py`（幂等，先探测再改，可重复执行）：
备份 `tb_hazard` → 加 `request_id` → 加唯一索引 → 建 `ai_hazard_create_request` → 建 `ai_hazard_create_outbox`。

## 3. MQ 拓扑

| 项 | 值 |
|---|---|
| Exchange | `safety.hazard`（topic） |
| 建单 routing key | `hazard.create.requested` |
| 建单队列 | `hazard.create`（Java 消费，带 `x-dead-letter-exchange=safety.hazard.dlx`） |
| 回执 routing key | `hazard.create.result` |
| 回执队列 | `hazard.create.result.q`（Python 消费，**带 `x-dead-letter-exchange=safety.hazard.dlx`**） |
| DLX / DLQ | `safety.hazard.dlx` → `hazard.create.dlq` |

**声明必须两边一致**：`RabbitConfig.java`（Java）与 `RabbitPublisher._declare_topology`（Python）参数逐字一致，否则队列重复声明会 406。消费端拿原始 `Message` 自己解析（Python 发的 body 无 content_type）。

建单消息体：
```json
{ "requestId": "req-…", "userId": 10, "sessionId": "…",
  "category": "fire/fire_lane_blocked",
  "categoryList": ["fire/fire_lane_blocked", "municipal/manhole_damage"],
  "address": "…", "district": "…",
  "longitude": 117.6, "latitude": 26.2, "description": "…",
  "severity": 1, "imageUrl": "…", "report": "…",
  "createdAt": "2026-10-10T12:00:00" }
```
> 比原方案多保留 `imageUrl`（现有 payload 就带）。
> 2026-10-14：新增 `categoryList`（一次上报可能有多个隐患，最多 3 条、第一条为主类别）。
> `category` 语义不变（= 列表第一条），所以老消费端不受影响；消费端把它拼成逗号串写入
> `tb_hazard.hazard_types`，`hazard_type` 仍是主类别。
> 前端展示/筛选口径（全部类别同级并排、只按一级大类「任一命中」检索）见
> `docs/current/hazard-multi-category-frontend-patch.md`。

回执消息体：
```json
{ "requestId": "req-…", "status": "SUCCESS" | "FAILED",
  "hazardId": 61, "message": "…" }
```

## 4. 幂等与重试（必须同时成立）

1. Outbox **至少发一次**（失败进 RETRY，到上限转 FAILED）。
2. Relay 发成功后才标 `PUBLISHED`；「已发未标」崩溃 → 允许重发，靠 Java 幂等兜。
3. Java 消费按 `request_id` 去重：先查 → 无则插 → 唯一冲突则回查返回已有。
4. 消费者遇到重复消息**不报错**，直接返回已有任务。
5. `request_id` / `userId` / `category` 为空或 body 非法 → `AmqpRejectAndDontRequeueException`，**不重试、直接进 DLQ，不写库**。
6. Java listener 重试上限 `max-attempts=3`；耗尽后 `MessageRecoverer` 回一条 FAILED（前提：回执发送本身成功）并把消息丢 DLQ。

## 5. 降级开关与上线顺序

- MQ 是唯一建单路径；旧同步开关与 `@ConditionalOnProperty` 已删除，Rabbit 配置总是加载。
- 旧同步开关、`POST /api/hazard/ai`、`task_created` 已删除；MQ 是唯一建单路径。
- 上线：建表（`migrate_hazard_create_mq.py`）→ 部署 RabbitMQ → 部署 Python Outbox + Relay（worker）→ 部署 Java Consumer + 回执 → 验重复/断线/重启/DLQ。

## 6. 前端契约

| 模式 | SSE 事件 | 前端行为 |
|---|---|---|
| MQ 唯一路径 | `task_accepted` `{request_id, status}` | 显示「创建中」→ 轮询 `GET /api/hazard/requests/{requestId}` → SUCCESS/FAILED |

- 前端只处理 `task_accepted` + 轮询；旧 `task_created` 分支已无后端事件来源。
- `task_accepted` 只表示「已受理」，**不表示已落库**。

状态查询（Java 对外，内部代理 Python）：
```
GET /api/hazard/requests/{requestId}    （需登录 JWT）
→ { requestId, status, hazardId, message }
```

字段与轮询细节见 `docs/current/ai-assistant-sse-contract.md` 第四节。

### 6.1 进程与文件落地

- 独立 worker 入口：`ai-module/hazard_create_worker.py`（Relay + ResultConsumer + RequestReconciler + MetricsReporter + RequestRetentionWorker 五个线程）。
- 本地内联：`HAZARD_CREATE_WORKER_INLINE=true` 时跑在 FastAPI lifespan 里。
- 云端启停：`/home/ubuntu/restart-hazard-worker.sh`；日志 `/home/ubuntu/ai-hazard-worker.log`。

## 7. 状态表归属说明

状态接口对外挂在 Java（前端只认 Java），但**数据与写入都在 Python**：Java 只是把 `GET /api/hazard/requests/{id}` 代理到 Python 的 `GET /api/ai/hazard-create/requests/{id}`。
> 与既有 `/api/ai/history` 的代理方式一致，不新增「Java 直读 ai_* 表」的越界。

## 8. 卡单、DLQ 与运维告警

线上由 `/home/ubuntu/hazard-mq-watchdog.sh`（cron `*/2 * * * *`）兜底，幂等、只在状态变化时写告警：

| 检查 | 判据 | 动作 |
|---|---|---|
| worker 存活 | `pgrep -f '^venv/bin/python3 -u hazard_create_worker\.py$'` | 不在就拉起 `restart-hazard-worker.sh`，失败则告警 |
| 卡单 PUBLISHED | `status='PUBLISHED' AND updated_at < NOW() - 5min` 有值 | 告警（Java 没回执？） |
| 卡单 PENDING | `status='PENDING' AND created_at < NOW() - 5min` 有值 | 告警（Relay 没发出去？） |
| DLQ 堆积 | `hazard.create.dlq` messages != 0 | 告警，人工处理 |

- 告警文件：`/home/ubuntu/hazard-mq-alerts.log`；巡检日志：`/home/ubuntu/hazard-mq-watchdog.log`；心跳：`/home/ubuntu/.hazard-mq-watchdog.last`。
- watchdog 只做**告警 + 拉起 worker**；代码级超时补状态由 `RequestReconciler` 负责（2026-10-11 已实现）。

---

> **附：以下章节非 MQ 契约**，暂留此处以免信息丢失，后续拆分到独立文档。

## 附录 A. LLM 调用链：重试与跨供应商降级

### A.1 为什么需要（原状态是坏的）

`.env` 里**没有**配置 `MIMO_MODEL_BACKUP`，它与主模型同名（都是 `mimo-v2.6-flash`）。而 `core/agent.py` 的判断是：

```python
if MIMO_MODEL_BACKUP and MIMO_MODEL_BACKUP != self.model:
    models.append(MIMO_MODEL_BACKUP)      # 同名 -> 永远不 append
```

→ `models` 只有 1 个元素 → 出错时 `if idx == 0 and len(models) > 1` 判 false → **一次重试都没有**，直接返回「调用失败」，用户吃兜底话术。

### A.2 现在的链路

```
主端点（重试 LLM_RETRY_PER_ENDPOINT 次，退避 1s × 2^n）
  → 同供应商备用模型（仅当 MIMO_MODEL_BACKUP 与主模型确实不同）
    → 跨供应商降级（仅当 FALLBACK_LLM_* 三件套齐全）
```

| 规则 | 说明 |
|---|---|
| 只重试**瞬时**错误 | 超时 / `408,409,425,429,500,502,503,504` / 连接被切（含 `Response ended prematurely`） |
| 非瞬时（400/401/403） | 跳过本端点剩余重试，直接看下一个端点（重试多少次都一样） |
| 流式降级条件 | **只在未吐出任何 token 时**降级；已吐正文则中断报错（重试会重复内容） |
| 只读 `delta["content"]` | 推理模型的 `reasoning_content` 不会被当成正文写进报告 |

### A.3 配置（服务端 `ai-module/.env`）

```
LLM_RETRY_PER_ENDPOINT=2          # 每个端点重试几次（含首次）
LLM_RETRY_BACKOFF_SECONDS=1.0     # 退避基数
FALLBACK_LLM_BASE_URL=https://api.deepseek.com
FALLBACK_LLM_MODEL=deepseek-flash      # 官方 id，名称 DeepSeek-V4.1-Flash
FALLBACK_LLM_EFFORT=low                # 该模型特有：low/high/max
```

> `deepseek-flash` 是**推理模型**（先 `reasoning_content` 后 `content`），所以 `effort=low` 提速；报告正文只取 `content`，不受影响。
> 该 key 只在 `.env`（gitignored）里；`.env.example` 只放占位符。

### A.4 验证（2026-10-10 实测）

| 场景 | 结果 |
|---|---|
| 主端点指向死端口 | `RETRY×2 → FALLBACK 备用模型 → RETRY×2 → FALLBACK deepseek-flash → 返回正确内容`（2.8s） |
| 主端点正常 | 1.5s 一次成功，**不触发降级** |
| 流式 + 主端点坏 | 未吐字前降级，**从 deepseek 流式输出** |

### A.5 已知边界

- 降级模型**尚未被真实流量检验**（只验证了链路与内容正确）。规划器用 DeepSeek 出 JSON 可能与 MiMo 风格不同，`parse_plan` 有校验兜底，但灰度期要留意 `[FALLBACK]` 日志频率。
- 实测：MiMo 的 `Response ended prematurely` 出现在**长输出**场景；**16 并发短请求 100% 成功** → 不是"并发把配额打爆"，而是上游把长流切断。

## 附录 B. 数据库连接池

`ai-module/tools/db_pool.py` 提供两个池，三个模块统一走池：

| 使用方 | 池 | 说明 |
|---|---|---|
| `tools/hazard_create_queue.py` | `pool()` | 建单链路（入队 / 状态查询 / relay / 回执消费） |
| `core/memory.py` | `pool()` | 历史记忆读写 |
| `tools/hybrid_search.py` | `retrieval_pool()` | 检索（每轮对话热路径），需 socket 级超时，单独一个池 |

**规则（必须遵守）**
1. 取出时 `ping(reconnect=True)`；坏了丢弃重建。
2. **归还前 `rollback()`**：否则上个使用者没提交的 SELECT 事务会被继承，在 REPEATABLE READ 下变成固定快照读到旧数据。
3. **取消 / 异常路径 `discard()`**：半途的连接绝不复用。
4. 默认池显式给超时（connect 5s / read 10s / write 10s）——默认为 `None` 意味着可以无限等，会把调用方一起拖死。

**有意的取舍**：`hybrid_search` 原来按「剩余预算」逐次设 socket 超时；池化后 socket 超时固定为 `RETRIEVAL_TIMEOUT_SECONDS`，逐次收紧只剩应用侧 deadline 检查。代价是单条查询最长等 `RETRIEVAL_TIMEOUT_SECONDS`（默认 10s，与原来首次预算相同），换来每轮检索省 2~4 次握手。

**实测**：状态接口 p50 **50.3ms → 5.3ms**（那 50ms 几乎全是建连接的 TCP+认证握手，查询本身微秒级）；30 次操作后 MySQL 连接数 17 → 19 稳定。

## 附录 C. 并发闸门（端到端上限由最窄那环决定）

| 层 | 真正并行 | 排队 | 超限行为 |
|---|---|---|---|
| Java `AiService.streamExecutor` | **8** | 32 | 第 41 个 → **429「当前服务繁忙」** |
| Python 图执行（`asyncio.to_thread`，2 核默认池） | **6** | 排队 | **不报错，延迟线性增长** |
| Python 图片 I/O 池（`_IMAGE_EXECUTOR`） | 8 | 排队 | 排队 |

- 结论：**端到端真实并行 ≈ 6**，由 Python 默认线程池决定（`min(32, CPU+4)`，2 核 = 6）。
- **不要上 Gunicorn 多 worker**：当前只做单实例重启恢复。Redis Stack 已让会话与 checkpoint 持久化（`SESSION_BACKEND=redis` / `CHECKPOINT_BACKEND=redis`，health 显示 `effective=redis`），但多实例部署还需要额外的路由、锁与工作流并发设计，当前不做。

## 附录 D. 本轮顺带修掉的两个缺陷

| 位置 | 问题 | 修复 | 实测 |
|---|---|---|---|
| `server.py`（`assistant_stream` 等 4 处） | 带图请求在 **async handler 里同步**调 `_save_upload` / `analyze_json`（`requests` 阻塞最长 60s）→ **整个事件循环被冻住**，其他所有会话的打字机效果一起卡 | 挪进显式有界的 `_IMAGE_EXECUTOR`(8)，用 `_run_blocking()` | 图片请求进行中，其他请求最大延迟 **16931ms → 18.8ms** |
| `safety-web/.../RedisConfig.java` | 配了 `RedisCacheManager` bean，但全仓**没有任何** `@EnableCaching` / `@Cacheable` → 死配置，误导"缓存已交给 Spring" | 删掉该 bean（隐患详情的三级缓存是手写在 `HazardServiceImpl` 里的，不依赖它） | Java 重启无报错，各接口 200，详情缓存 p50 17ms |
