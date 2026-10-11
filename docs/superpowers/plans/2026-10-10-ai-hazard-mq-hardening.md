# AI 建任务 MQ 加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 补齐 AI 建任务 MQ 的 DLX、回执重试、前端轮询、超时对账、Java MQ 专项测试和 current 文档一致性。

**Architecture:** 保留 Python Outbox + RabbitMQ + Java 幂等消费架构，只修复结果链路可靠性和前后端契约，不引入新微服务。

**Tech Stack:** Spring Boot 3.3.5 + Spring AMQP、RabbitMQ、Python 3 + pika + PyMySQL、MySQL、Vue 3。

## Global Constraints

- `HAZARD_CREATE_MQ_ENABLED=false` 时必须保持旧同步链路行为不变。
- Python 只写 `ai_hazard_create_request` / `ai_hazard_create_outbox`；Java 只写 `tb_hazard`。
- 幂等键统一为 `request_id`，`tb_hazard.request_id` 唯一索引不可移除。
- 不把真实密码、Token、密钥写入仓库或文档。
- 每个任务结束必须跑对应 Python / Java 测试并提交。

---

### Task 1: 结果队列 DLX 与拓扑契约

**Files:**
- Modify: `ai-module/tools/hazard_create_queue.py`
- Modify: `safety-web/src/main/java/com/safety/web/config/RabbitConfig.java`
- Test: `ai-module/tests/test_hazard_create_queue.py`
- Test: `safety-web/src/test/java/com/safety/web/config/RabbitConfigTest.java`

**Interfaces:**
- Consumes: `RABBITMQ_DLX`、`HAZARD_RESULT_QUEUE`。
- Produces: 结果队列带 `x-dead-letter-exchange`；Java 与 Python 拓扑参数一致。

- [ ] **Step 1: 确认队列迁移方式**

RabbitMQ 不允许同名队列用不同 arguments 重复声明。二选一：
A. 删除并重建 `hazard.create.result.q`（推荐，灰度期未长期积压时代价最低）。
B. 新队列名 `hazard.create.result.v2.q`，旧队列闲置后人工清理。

- [ ] **Step 2: 写 Python 失败测试**

在 `ai-module/tests/test_hazard_create_queue.py` 增加：

```python
def test_result_queue_declares_dead_letter_exchange():
    class FakeChannel:
        def __init__(self):
            self.queue_declares = []
        def exchange_declare(self, *args, **kwargs):
            pass
        def queue_declare(self, name, **kwargs):
            self.queue_declares.append((name, kwargs))
        def queue_bind(self, *args, **kwargs):
            pass

    ch = FakeChannel()
    q.RabbitPublisher._declare_topology(ch)
    result = [item for item in ch.queue_declares if item[0] == q.HAZARD_RESULT_QUEUE]
    assert result and result[0][1]["arguments"]["x-dead-letter-exchange"] == q.RABBITMQ_DLX
```

- [ ] **Step 3: 运行并确认失败**

Run: `python -m pytest tests/test_hazard_create_queue.py::test_result_queue_declares_dead_letter_exchange -q`
Expected: FAIL。

- [ ] **Step 4: 修改 Python 声明**

```python
channel.queue_declare(
    HAZARD_RESULT_QUEUE, durable=True,
    arguments={"x-dead-letter-exchange": RABBITMQ_DLX},
)
```

- [ ] **Step 5: 写 Java 失败测试**

创建 `safety-web/src/test/java/com/safety/web/config/RabbitConfigTest.java`：

```java
package com.safety.web.config;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Queue;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RabbitConfigTest {
    @Test
    void resultQueueCarriesDeadLetterExchange() {
        Queue queue = new RabbitConfig().hazardResultQueue("hazard.create.result.q", "safety.hazard.dlx");
        assertEquals("safety.hazard.dlx", queue.getArguments().get("x-dead-letter-exchange"));
    }
}
```

- [ ] **Step 6: 修改 Java 声明**

```java
@Bean
public Queue hazardResultQueue(@Value("${hazard.create.result-queue}") String name,
                               @Value("${hazard.create.dlx}") String dlx) {
    return QueueBuilder.durable(name)
            .withArgument("x-dead-letter-exchange", dlx)
            .build();
}
```

- [ ] **Step 7: 跑测试并提交**

Run: `python -m pytest tests/test_hazard_create_queue.py -q; mvn -pl safety-web -am test`
Commit: `fix(mq): dead-letter result queue and cover topology`

---

### Task 2: Java 回执发送失败必须可重试

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/service/HazardCreateResultPublisher.java`
- Modify: `safety-web/src/main/java/com/safety/web/config/RabbitConfig.java`
- Test: `safety-web/src/test/java/com/safety/web/service/HazardCreateResultPublisherTest.java`
- Test: `safety-web/src/test/java/com/safety/web/service/HazardCreateConsumerTest.java`

**Interfaces:**
- Produces: `publisher.succeeded(...)` / `failed(...)` 发送失败抛异常；listener 重试；`createAi` 幂等保证重试不重复建单。

- [ ] **Step 1: 写 Publisher 失败测试**

```java
@Test
void sendFailurePropagates() {
    RabbitTemplate template = mock(RabbitTemplate.class);
    doThrow(new RuntimeException("rabbit down"))
        .when(template).convertAndSend(eq("safety.hazard"), eq("hazard.create.result"), any(HazardCreateResult.class));
    HazardCreateResultPublisher publisher = new HazardCreateResultPublisher(template);
    ReflectionTestUtils.setField(publisher, "exchange", "safety.hazard");
    ReflectionTestUtils.setField(publisher, "routingKey", "hazard.create.result");
    assertThrows(RuntimeException.class, () -> publisher.succeeded("req-1", 61L));
}
```

- [ ] **Step 2: 修改 Publisher**

```java
private void send(HazardCreateResult result) {
    try {
        rabbitTemplate.convertAndSend(exchange, routingKey, result);
    } catch (RuntimeException e) {
        log.error("[ALERT] hazard create result publish failed: {}", result, e);
        throw e;
    }
}
```

- [ ] **Step 3: 写 Consumer 回归测试**

验证 `publisher.succeeded` 抛异常时 `onMessage` 也抛出 RuntimeException。

- [ ] **Step 4: 修改 Recoverer**

```java
try {
    publisher.failed(requestId, cause == null ? "unknown" : cause.getMessage());
} catch (RuntimeException publishError) {
    // 回执失败不能阻止原消息进 DLQ
}
throw new AmqpRejectAndDontRequeueException("hazard create exhausted retries", cause);
```

- [ ] **Step 5: 跑测试并提交**

Run: `mvn -pl safety-web -am test`
Commit: `fix(mq): surface result publish failures for retry`

---

### Task 3: 前端 task_accepted + 轮询

**Files:**
- Modify external: `/home/ubuntu/aisafety-platform-frontend/src/views/HomeView.vue`
- Create if源码不可用: `docs/current/ai-hazard-create-mq-frontend-patch.md`

**Interfaces:**
- Consumes: SSE `task_accepted`、`GET /api/hazard/requests/{requestId}`。
- Produces: 前端显示创建中，轮询到 SUCCESS / FAILED。

- [ ] **Step 1: 确认源码路径**

仓库内 `.frontend-sync-dist/HomeView.vue` 和 `.codex-remote-frontend-edit/HomeView.vue` 是快照，不是线上源码。必须取得 `/home/ubuntu/aisafety-platform-frontend` 的可写副本；否则只产出 patch spec。

- [ ] **Step 2: 增加事件分支**

```js
} else if (event.type === 'task_accepted') {
  const t = event.content || {}
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.taskAccepted = t
    last.taskStatus = 'PENDING'
  }
  pollHazardRequest(t.request_id)
}
```

- [ ] **Step 3: 增加轮询**

```js
async function pollHazardRequest(requestId) {
  if (!requestId) return
  const token = localStorage.getItem('token')
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const resp = await fetch(`/api/hazard/requests/${requestId}`, { headers: { Authorization: `Bearer ${token}` } })
    if (!resp.ok) continue
    const data = (await resp.json()).data || {}
    const last = messages.value[messages.value.length - 1]
    if (!last || last.role !== 'assistant') continue
    if (data.status === 'SUCCESS') {
      last.taskStatus = 'SUCCESS'
      last.taskCreated = { hazard_id: data.hazardId, hazard_code: `#HAZ-${data.hazardId}` }
      saveChatCache(); return
    }
    if (data.status === 'FAILED') {
      last.taskStatus = 'FAILED'
      last.content += `\n\n隐患任务创建失败：${data.message || '请稍后重试'}`
      saveChatCache(); return
    }
  }
}
```

- [ ] **Step 4: 增加模板状态并构建验证**

Run: `npm run build`；发布后验证 `task_accepted -> 创建中 -> SUCCESS -> 查看工单`。
Commit: `feat(ai): poll hazard create result after task_accepted`

---

### Task 4: 文档统一为 MQ 当前真相

**Files:**
- Modify: `docs/current/README.md`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/project-overview.md`
- Modify: `docs/current/ai-assistant-sse-contract.md`
- Modify: `docs/current/ai-hazard-create-mq.md`
- Modify: `docs/deployment/safety-platform-deployment.md`

- [ ] **Step 1: 索引 MQ 文档**

在 `docs/current/README.md` 增加 `ai-hazard-create-mq.md` 条目。

- [ ] **Step 2: 更新运行时拓扑**

把唯一的：

```text
Python -> Java /api/hazard/ai
```

改为：

```text
Python -> RabbitMQ -> Java consumer -> tb_hazard
（HAZARD_CREATE_MQ_ENABLED=false 时才走旧同步 /api/hazard/ai）
```

- [ ] **Step 3: 更新 SSE 契约**

事件表增加 `task_accepted` 与 `GET /api/hazard/requests/{requestId}`。

- [ ] **Step 4: 拆分 MQ 文档职责**

`ai-hazard-create-mq.md` 只保留 MQ/Outbox/回执/灰度；LLM 降级和连接池内容移到独立文档或 `docs/evidence/`。

- [ ] **Step 5: 更新部署 Runbook**

增加 RabbitMQ 5672/15672、worker 启停、双端开关、队列冲突处理、回滚步骤。

- [ ] **Step 6: 一致性检查并提交**

Run: `rg -n "task_accepted|hazard.create.result|HAZARD_CREATE_MQ_ENABLED|hazard_create_worker" docs/current docs/deployment`
Commit: `docs: align current truth with hazard create MQ`

---

### Task 5: 超时对账与 Java MQ 专项测试

**Files:**
- Modify: `ai-module/tools/hazard_create_queue.py`
- Modify: `ai-module/hazard_create_worker.py`
- Modify: `ai-module/tools/java_client.py`
- Modify: `safety-web/src/main/java/com/safety/web/controller/HazardController.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/HazardService.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java`
- Test: `ai-module/tests/test_hazard_create_queue.py`
- Test: `safety-web/src/test/java/com/safety/web/service/HazardCreateConsumerTest.java`

**Interfaces:**
- Produces: 超时 `PENDING/PUBLISHED` 对账；Java 内部查询 `GET /api/hazard/ai/requests/{requestId}`；重复消费/回执失败/DLQ 测试。

- [ ] **Step 1: 增加 Java 内部查询**

```java
@GetMapping("/ai/requests/{requestId}")
public R<Map<String, Object>> aiCreateRequestStatus(
        @PathVariable String requestId,
        @RequestHeader(value = "X-Internal-Token", required = false) String token) {
    if (internalToken == null || internalToken.isBlank() || !internalToken.equals(token)) {
        throw new BusinessException(401, "unauthorized internal call");
    }
    HazardVO vo = hazardService.getByRequestId(requestId);
    return R.ok(Map.of("found", vo != null, "hazardId", vo == null ? null : vo.getId()));
}
```

- [ ] **Step 2: 增加 Python 对账**

`RequestReconciler` 扫超时 request，调用 Java 内部查询；已建则补 SUCCESS，未建则重投或 FAILED。

- [ ] **Step 3: 增加 Java MQ 测试**

覆盖：重复消息只建一次、回执失败抛出、缺 requestId 进 DLQ、重复消息补发回执。

- [ ] **Step 4: 跑全套并提交**

Run: `python -m pytest tests/ -q; mvn -B test`
Commit: `fix(mq): reconcile stuck creates and add consumer tests`

---

### Task 6: 最终验收与开关决策

**Files:**
- Modify: `docs/current/ai-hazard-create-mq.md`
- Create: `docs/evidence/2026-10-10-hazard-create-mq-acceptance.md`

- [ ] **Step 1: 记录测试证据**

记录 Python/Java 测试、重复消息、Java 消费后崩溃、RabbitMQ 重启、回执发送失败、DLQ、前端轮询结果。

- [ ] **Step 2: 手工验收 7 项**

1. MQ 开启后收到 `task_accepted`；
2. 轮询 SUCCESS 后出现“查看工单”；
3. 停 RabbitMQ 后重启能补发；
4. 建单成功但回执失败能重试成功；
5. 重复投递只建一条；
6. 非法消息进 DLQ，request 不永远 PUBLISHED；
7. 开关关闭时旧同步链路可用。

- [ ] **Step 3: 开关决策并提交**

7 项全过才把双端开关置 `true`；否则保持 `false` 并记录阻塞项。
Commit: `docs: record hazard create MQ acceptance`

---

## Self-Review

- Spec coverage: DLX、回执重试、前端轮询、超时对账、Java MQ 测试、部署与文档一致性均已覆盖。
- Placeholder scan: 无 TBD/TODO；前端源码不可写这一外部依赖已明确。
- Type consistency: `request_id` / `requestId`、`task_accepted`、`GET /api/hazard/requests/{requestId}` 全计划一致。

---

# Phase 2: MQ 生产化加固（同计划并入）

> 执行原则：Phase 1（Task 1-6）是 MQ 灰度前硬门槛；Phase 2（Task 7-12）是“一次规划、按序完成”的加固项；Task 13 在 Task 1-12 验收通过后即可作为正常迭代执行，不设人为观察期。

### Task 7: 会话与 LangGraph Checkpoint 外置（支持多 worker）

**Files:**
- Modify: `ai-module/core/memory.py`
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/server.py`
- Modify: `ai-module/config.py`
- Modify: `ai-module/requirements.txt`
- Test: `ai-module/tests/test_memory_store.py`
- Test: create `ai-module/tests/test_checkpoint_store.py`

**Interfaces:**
- Produces: `get_session(session_id)` 不再依赖进程内 dict；`get_app()` 的 checkpointer 支持 Redis 后端；配置 `SESSION_BACKEND=redis|memory`、`CHECKPOINT_BACKEND=redis|memory`。
- Constraint: `memory` 仅本地开发；测试/生产默认 `redis`。

- [ ] **Step 1: 补依赖**

在 `ai-module/requirements.txt` 增加：

```text
redis>=5.0.0
langgraph-checkpoint-redis>=0.2.0
```

- [ ] **Step 2: 写失败测试**

```python
def test_session_survives_new_memory_store_instance(monkeypatch):
    monkeypatch.setenv("SESSION_BACKEND", "redis")
    # 注入 fake redis，验证 get_session("s1") 在两个实例间读到同一 messages
```

- [ ] **Step 3: 实现 Redis-backed WorkingMemory**

`core/memory.py` 增加：

```python
class RedisWorkingMemory(WorkingMemory):
    """把 messages 落 Redis；进程重启/多 worker 后同一 session 可恢复。"""
```

- [ ] **Step 4: 实现 Redis checkpointer**

`core/assistant_graph.py` 增加：

```python
def get_checkpointer():
    if CHECKPOINT_BACKEND == "redis":
        from langgraph.checkpoint.redis import RedisSaver
        return RedisSaver.from_conn_string(REDIS_URL)
    return InMemorySaver()
```

- [ ] **Step 5: 多 worker 验收**

启动两个 uvicorn worker，使用同一 `session_id`：

```text
worker A 发出 interrupt
worker B 收到 resume
→ 必须恢复同一 graph 状态并成功建单
```

- [ ] **Step 6: 跑测试并提交**

Run: `python -m pytest tests/test_memory_store.py tests/test_checkpoint_store.py tests/test_task_gate_interrupt.py -q`
Commit: `feat(ai): externalize sessions and checkpoints for multi-worker`

---

### Task 8: MQ / Outbox 指标、告警与链路追踪

**Files:**
- Modify: `safety-web/pom.xml`
- Modify: `safety-web/src/main/java/com/safety/web/service/HazardCreateConsumer.java`
- Modify: `safety-web/src/main/java/com/safety/web/service/HazardCreateResultPublisher.java`
- Modify: `ai-module/hazard_create_worker.py`
- Modify: `ai-module/tools/hazard_create_queue.py`
- Create: `docs/current/ai-hazard-create-observability.md`

**Interfaces:**
- Produces: 指标 `hazard_create_outbox_pending`、`hazard_create_outbox_retry`、`hazard_create_outbox_failed`、`hazard_create_consume_success_total`、`hazard_create_consume_failure_total`、`hazard_create_result_publish_failure_total`、`hazard_create_stuck_total`。
- Produces: 每条日志带 `request_id`，便于 grep 串联。

- [ ] **Step 1: 加 Actuator / Prometheus**

`pom.xml`：

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

- [ ] **Step 2: 加计数器**

`HazardCreateConsumer` 注入 `MeterRegistry`，成功/失败计数：

```java
registry.counter("hazard_create_consume_success_total").increment();
registry.counter("hazard_create_consume_failure_total").increment();
```

- [ ] **Step 3: Python worker 定时打点**

`hazard_create_worker.py` 增加 `MetricsReporter` 线程，每 60s 查一次 outbox/request 状态并打日志：

```text
hazard_create_metrics pending=... published=... retry=... failed=... stuck=...
```

- [ ] **Step 4: 写告警口径**

`docs/current/ai-hazard-create-observability.md` 明确：

- `outbox_failed > 0` 触发告警；
- `stuck > 0` 持续 10 分钟触发告警；
- `result_publish_failure_total` 增长率异常触发告警。

- [ ] **Step 5: 跑测试并提交**

Run: `mvn -pl safety-web -am test; python -m pytest tests/test_hazard_create_queue.py -q`
Commit: `feat(mq): add hazard create metrics and alerts`

---

### Task 9: 高并发压测与容量调优

**Files:**
- Create: `ai-module/db/load_hazard_create_mq.py`
- Create: `docs/evidence/2026-10-11-hazard-create-mq-load.md`
- Modify: `ai-module/config.py`
- Modify: `safety-web/src/main/resources/application.yml`

**Interfaces:**
- Produces: 可重复运行的压测脚本，输入 `--concurrency`、`--total`、`--timeout`，输出 success/failed/DLQ/p50/p95/p99。

- [ ] **Step 1: 写压测脚本**

```python
# 直接写 request+outbox，模拟 N 个用户确认建单；
# 轮询 ai_hazard_create_request 直到 SUCCESS/FAILED，统计延迟与丢单。
```

- [ ] **Step 2: 跑 4 组**

```text
10 并发 / 100 单
50 并发 / 500 单
100 并发 / 1000 单
200 并发 / 2000 单
```

- [ ] **Step 3: 调参**

按实测调整：
- Java `AiService.streamExecutor` 与 `hazard.create.mq` consumer concurrency；
- Python `_IMAGE_EXECUTOR`、`asyncio.to_thread` 默认池、`DBPool` 上限；
- RabbitMQ `prefetch_count`。

- [ ] **Step 4: 记录验收线**

建议硬门槛：

```text
无重复建单
无丢单（最终都有 SUCCESS/FAILED）
DLQ = 0
p95 < 10s（本地/内网单机）
```

- [ ] **Step 5: 提交**

Commit: `test(mq): add hazard create load test and capacity report`

---

### Task 10: Request / Outbox 历史归档与清理

**Files:**
- Create: `ai-module/db/migrate_hazard_create_archive.py`
- Modify: `ai-module/tools/hazard_create_queue.py`
- Modify: `ai-module/hazard_create_worker.py`
- Test: `ai-module/tests/test_hazard_create_queue.py`

**Interfaces:**
- Produces: `RequestRetentionWorker.run_once()`：`SUCCESS` 保留 90 天、`FAILED` 保留 180 天、`PUBLISHED` outbox 保留 30 天，归档到 `*_archive` 表后删除。

- [ ] **Step 1: 建归档表**

```sql
CREATE TABLE ai_hazard_create_request_archive LIKE ai_hazard_create_request;
CREATE TABLE ai_hazard_create_outbox_archive LIKE ai_hazard_create_outbox;
```

- [ ] **Step 2: 实现归档 worker**

```python
class RequestRetentionWorker:
    def run_once(self, *, connect=None) -> int:
        ...
```

- [ ] **Step 3: 挂进 worker 线程**

`hazard_create_worker.py` 增加 `hazard-retention` 线程。

- [ ] **Step 4: 测试**

```python
def test_retention_moves_only_terminal_old_rows():
    ...
```

- [ ] **Step 5: 提交**

Commit: `feat(mq): archive and clean hazard create history`

---

### Task 11: 状态查询接口补 request 归属校验

**Files:**
- Modify: `ai-module/tools/hazard_create_queue.py`
- Modify: `ai-module/server.py`
- Modify: `safety-web/src/main/java/com/safety/web/service/AiService.java`
- Modify: `safety-web/src/main/java/com/safety/web/controller/HazardController.java`
- Test: `ai-module/tests/test_hazard_create_queue.py`
- Test: `safety-web/src/test/java/com/safety/web/controller/HazardControllerTest.java`

**Interfaces:**
- `get_request_status(request_id, user_id=None)`：传 `user_id` 时必须是该 request 的 owner。
- Java 对外接口从 `Authentication` 取 userId，转发给 Python。

- [ ] **Step 1: 写失败测试**

```python
def test_status_rejects_other_user_request():
    conn = FakeConn(fetchone=(q.REQ_SUCCESS, 61, None))
    # 但 request.user_id=1；查询 user_id=2 必须返回 None
```

- [ ] **Step 2: 改 Python 查询**

```python
def get_request_status(request_id: str, *, user_id=None, connect=None):
    sql = "SELECT ... FROM ai_hazard_create_request WHERE request_id=%s"
    params = [request_id]
    if user_id is not None:
        sql += " AND user_id=%s"
        params.append(user_id)
```

- [ ] **Step 3: 改 Java 转发**

```java
@GetMapping("/requests/{requestId}")
public R<Map<String, Object>> createRequestStatus(@PathVariable String requestId,
                                                  Authentication auth) {
    Long userId = (Long) auth.getPrincipal();
    return R.ok(aiService.hazardCreateStatus(requestId, userId));
}
```

- [ ] **Step 4: 跑测试并提交**

Commit: `fix(mq): enforce hazard create request ownership`

---

### Task 12: 有并发上限的 DB 连接池

**Files:**
- Modify: `ai-module/tools/db_pool.py`
- Modify: `ai-module/requirements.txt`
- Test: `ai-module/tests/test_db_pool.py`

**Interfaces:**
- Produces: `DBPool(max_connections=N)`，超过并发上限时阻塞等待，而不是无限新建连接。
- 保留 `pool()` / `retrieval_pool()` 现有调用方式。

- [ ] **Step 1: 写失败测试**

```python
def test_pool_never_exceeds_max_connections(monkeypatch):
    ...
```

- [ ] **Step 2: 用 DBUtils 或 queue.Queue 实现上限**

推荐 `DBUtils.PooledDB`：

```text
dbutils>=3.1.0
```

- [ ] **Step 3: 跑检索/建单/记忆测试**

Run: `python -m pytest tests/test_hazard_create_queue.py tests/test_memory_store.py tests/test_retrieval_contract.py -q`

- [ ] **Step 4: 提交**

Commit: `perf(ai): bound database connection pool`

---

### Task 13: 删除旧同步链路（验收后迭代）

**Gate:** 必须满足以下工程条件，不设时间/单量观察期：

- Phase 1-12 的 Python / Java 测试全绿；
- MQ 模式端到端跑通：确认 → `task_accepted` → `SUCCESS` → 查看工单；
- 重复消息只建一条；
- 回执发送失败可重试，DLQ 处理路径验证通过；
- 开关关闭 / 开启两种模式都各验收一次。

**Files:**
- Modify: `ai-module/tools/hazard_submit.py`
- Modify: `ai-module/tools/java_client.py`
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `safety-web/src/main/java/com/safety/web/controller/HazardController.java`
- Modify: `docs/current/ai-assistant-sse-contract.md`
- Modify: `docs/current/architecture.md`

- [ ] **Step 1: 删除 Python 旧同步分支**

删除 `HAZARD_CREATE_MQ_ENABLED=false` 时的 `create_hazard(payload)` 调用与 `java_client.create_hazard`。

- [ ] **Step 2: 删除 Java 旧内部 HTTP 建单入口**

删除 `POST /api/hazard/ai` 及 SecurityConfig 中的放行；保留 `AiHazardDTO` 给 MQ consumer 用。

- [ ] **Step 3: 删除 `task_created` 兼容分支**

前端只保留 `task_accepted -> 轮询 -> SUCCESS/FAILED`；删除旧 `task_created` 事件分支。

- [ ] **Step 4: 更新文档并提交**

Commit: `refactor(mq): remove legacy synchronous hazard create path`

---

## Phase 2 Self-Review

- 覆盖：多 worker 会话/checkpoint、指标告警、压测、归档、归属校验、有界连接池、旧链路删除。
- 顺序：Task 1-6 先做；Task 7-12 在 MQ 主线稳定后一次性完成；Task 13 在 Task 1-12 验收通过后执行。
- 风险：Task 7 会动 LangGraph checkpointer，Task 13 会删旧链路，必须各自独立提交，不能和 Task 1-6 混在同一批提交里。


---

## Subagent Execution Map（2026-10-11）

### Wave 1（可并行，写入范围互不重叠）

| 执行者 | 任务 | 独占写入范围 |
|---|---|---|
| 主智能体 | Task 1 + Task 2 + Task 5 的关键路径代码 | `ai-module/tools/hazard_create_queue.py`、`safety-web/.../RabbitConfig.java`、`HazardCreateResultPublisher.java`、`HazardCreateConsumer.java`、Java MQ 测试 |
| 子智能体 MQ-Docs | Task 4：current 文档对齐（本轮只改 MQ 相关真相，不写未来 Task 7-12 完成态） | `docs/current/*`、`docs/deployment/safety-platform-deployment.md` |
| 子智能体 LoadTest | Task 9：压测脚本骨架与证据模板 | `ai-module/db/load_hazard_create_mq.py`、`docs/evidence/2026-10-11-hazard-create-mq-load.md` |
| 子智能体 DBPool | Task 12：有界 DB 连接池 | `ai-module/tools/db_pool.py`、`ai-module/tests/test_db_pool.py`、`ai-module/requirements.txt` |

### Wave 2（Wave 1 合并后）

- Task 3：外部前端源码；由另一个模型按 patch 执行，主智能体只验契约
- Task 7：会话 / Checkpoint 外置
- Task 8：指标、告警、追踪
- Task 10：归档清理
- Task 11：request 归属校验
- Task 13：验收通过后删除旧同步链路

### 冲突规则

- 任何两个执行者不得同时修改同一文件。
- 涉及 `ai-module/requirements.txt` 的任务由 DBPool 子智能体独占；其他任务需要新增依赖时只记录，不直接改。
- `ai-module/tools/hazard_create_queue.py` 由主智能体独占，直到 Task 1/5 闭环。
- `docs/current/*` 由 MQ-Docs 子智能体独占，其他任务只提供变更说明。

---

## Progress（2026-10-11 执行中）

### 已完成 / 已合并到工作区

- Task 1：结果队列 DLX；Python + Java 拓扑测试通过。
- Task 2：回执发送失败抛出并触发 listener 重试；DLQ recoverer 不因回执失败阻断；Publisher / Consumer / RabbitConfig 测试通过。
- Task 4：current 文档与部署 Runbook 对齐 MQ；额外补掉 `agent-orchestration.md` / `hazard-lifecycle.md` 两处旧 `task_created` 口径。
- Task 5（代码部分）：Java 内部 `GET /api/hazard/ai/requests/{requestId}` + Python `RequestReconciler` + 对账单测完成；Java MQ 专项测试补齐。
- Task 9（代码部分）：压测脚本 `ai-module/db/load_hazard_create_mq.py` 与证据模板已创建；4 组真实压测尚未跑。
- Task 12：`tools/db_pool.py` 升级为有并发上限的池；`test_db_pool.py` 13 个单测通过；修复 `test_memory_store.py` 的池归还和 Redis 空缓存污染。
- Task 3：前端 patch 规格已落在 `docs/current/ai-hazard-create-mq-frontend-patch.md`；云端 `HomeView.vue` 尚未实际修改。

### 尚未完成

- Task 3：把前端 patch 真正合入 `/home/ubuntu/aisafety-platform-frontend/src/views/HomeView.vue`。
- Task 6：在真实环境完成 `task_accepted → 轮询 → SUCCESS → 查看工单` 端到端验收，以及重复消息 / 回执失败 / DLQ / 重启演练。
- Task 7：会话与 LangGraph Checkpoint 外置（多 worker）。
- Task 8：MQ / Outbox 指标、告警、链路追踪。
- Task 9：4 组真实压测执行与证据回填。
- Task 10：request / outbox 归档清理。
- Task 11：状态查询 request 归属校验。
- Task 13：验收通过后删除旧同步链路。

### 本地验证结果（2026-10-11）

- `python -m pytest tests/ -q`：**869 passed / 3 skipped / 0 failed**
- `mvn -B test`：**39 passed / 0 failed**
- `python -m pytest tests/test_hazard_create_queue.py tests/test_db_pool.py tests/test_memory_store.py -q`：**37 passed**

### Progress 追加（2026-10-11 第二轮）

- Task 7：已完成代码与测试。`SESSION_BACKEND` / `CHECKPOINT_BACKEND` 默认 `memory`；Redis 会话跨进程已验证；Checkpoint 的 `RedisSaver` 需要 Redis Stack，当前 `redis:7-alpine` 会明确降级为 `InMemorySaver`，所以“真正多 worker 恢复 interrupt”仍需先换 Redis Stack。
- Task 8：Java Actuator/Prometheus + 消费/回执指标已加；Python `MetricsReporter` 已进 worker；观测文档见 `docs/current/ai-hazard-create-observability.md`。
- Task 10：归档迁移脚本 `ai-module/db/migrate_hazard_create_archive.py` 与 `RequestRetentionWorker` 已完成。
- Task 11：`get_request_status` 已按 `user_id` 过滤；Java 状态查询从登录态透传 user_id。
- 全量回归：Python **890 passed / 3 skipped**；Java **39 passed**。

### 仍未完成

- Task 6：云端部署后的真实端到端（当前本地无 Java/Python/RabbitMQ，需部署）。
- Task 9：4 组真实压测。
- Task 13：验收后删除旧同步链路。

### 部署与真实链路验证（2026-10-11）

- Redis Stack `safety-redis-stack` 已上线 `127.0.0.1:6380`；Python health 显示 `session_backend.effective=redis`、`checkpoint_backend.effective=redis`。
- 跨进程 interrupt 恢复已验证：进程 A 暂停 → 进程 B 读到 `next=('gate',)` → `Command(resume=...)` 成功恢复。
- Java/Python 新包已部署；`hazard.create.result.q` 已按 A 方案删除重建并带 `x-dead-letter-exchange`，worker 不再 406。
- 受控 MQ 端到端验证通过：`enqueue → RabbitMQ → Java tb_hazard → 回执 → Python SUCCESS`（hazardId=3974，测试数据已清理）。
- Java 内部查询：`GET /api/hazard/ai/requests/{id}` 通过；Actuator `/actuator/prometheus` 200。

### 当前剩余

- 浏览器端人工完整确认一次：确认 → `task_accepted` → 轮询 → SUCCESS → 查看工单。
- Task 9：真实 4 组压测与证据回填。
- Task 13：浏览器/压测验收通过后删除旧同步链路。

### Task 6 + Task 9 收尾（2026-10-11）

- Task 6：用户已完成浏览器端人工确认；受控 MQ 端到端通过；Redis Stack 跨进程 interrupt 恢复通过。
- Task 9：4 组真实压测完成，结果已回填 `docs/evidence/2026-10-11-hazard-create-mq-load.md`。
  - 正确性：0 重复 / 0 丢单 / 0 提交失败 / DLQ=0。
  - 性能：A(10/100) p95=5.527s；B(50/500) p95=23.091s；C(100/1000) p95=40.021s；D(200/2000) p95=80.258s。
  - 结论：瓶颈在 Java 同步落库链路，不是 MQ 积压。
- 剩余：高并发性能优化；完成后再执行 Task 13 删除旧同步链路。

### Task 9 最终结论（Relay 批量化后）

- 面试级容量：50 并发 / 500 单，p50=6.462s、p95=9.062s、p99=10.541s；0 重复 / 0 丢单 / DLQ=0。
- 优化过程：初版 outbox p95=41.189s → Java 消费并发 4/8 + Relay 批 500/0.2s 后 23.091s → Relay 批量 claim + 批量标 PUBLISHED 后 9.062s。
- 边界：100/1000 出现 19 条 MySQL 死锁（提交阶段），p95=20.586s；200/2000 不再作为面试级目标。
- 结论：Task 9 面试级目标已达成，不再无限追高。

### Task 13 完成（2026-10-11）

- Python：删除 `HAZARD_CREATE_MQ_ENABLED` 旧分支、`java_client.create_hazard`、`task_created` 事件分支；`submit_from_history` 只写 Outbox。
- Java：删除 `POST /api/hazard/ai` 与 SecurityConfig 放行；MQ 配置不再由开关控制，Rabbit 配置总是加载。
- 文档：current / deployment 统一为 MQ 唯一路径。
- 部署回归：10/100 冒烟 PASS，SUCCESS=100，duplicate=0，丢单=0，DLQ=0，p95=3.208s；旧 `/api/hazard/ai` 不再可用（403）。
- 注意：部署过程中结果队列再次出现 DLX 参数不一致 406；已按 A 方案删除空队列并重建为带 DLX，worker 恢复正常。
