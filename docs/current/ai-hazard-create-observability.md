# AI 建任务 MQ 观测与告警（当前真相）

> 状态：current
> 最后核对：2026-10-11

## 1. Java / Prometheus 指标

启用 Spring Boot Actuator，暴露：

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/prometheus
```

MQ 指标：

| 指标 | 含义 |
|---|---|
| `hazard_create_consume_success_total` | Java 消费并成功建单/补发回执次数 |
| `hazard_create_consume_failure_total` | Java 消费失败次数（含非法消息） |
| `hazard_create_result_publish_success_total` | Java 回执发送成功次数 |
| `hazard_create_result_publish_failure_total` | Java 回执发送失败次数（会触发 listener 重试） |

## 2. Python worker 日志指标

`hazard_create_worker.py` 的 `MetricsReporter` 每 60 秒打一条：

```text
hazard_create_metrics request={...} outbox={...} stuck=...
```

字段含义：

- `request`：`ai_hazard_create_request.status` 各状态计数；
- `outbox`：`ai_hazard_create_outbox.status` 各状态计数；
- `stuck`：`PENDING/PUBLISHED` 且超过 `HAZARD_RECONCILE_AFTER_SECONDS`（默认 300 秒）的条数。

可用 `HAZARD_METRICS_INTERVAL_SECONDS` 调整打点周期。

## 3. 告警建议

| 判据 | 级别 | 动作 |
|---|---|---|
| `hazard_create_consume_failure_total` 持续增长 | P1 | 查 Java 日志、DLQ、`request_id` |
| `hazard_create_result_publish_failure_total` > 0 | P1 | 查 RabbitMQ 连接与队列可用性 |
| `stuck > 0` 持续 10 分钟 | P1 | 查 `RequestReconciler` 日志、Java 内部查询、DLQ |
| 任意 `outbox FAILED > 0` | P1 | 人工处理 DLQ / request 状态 |
| worker 进程不在 | P0 | 先拉起，再查 crash 日志 |

## 4. 当前已知边界

- Python 指标是**日志指标**，不是 Prometheus exporter；要接监控系统需再加 exporter 或写入时序库。
- watchdog 负责“拉起 + 告警”；`RequestReconciler` 负责“代码级补状态”，两者职责分离。
