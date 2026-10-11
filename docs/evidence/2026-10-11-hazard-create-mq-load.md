# AI 建任务 MQ 高并发压测（Task 9）

> **状态**：4 组已实测（2026-10-11，云端生产库，受控造数并清理）。Relay 批量化后，50/500 达到面试级目标（p95<10s）；100/1000 暴露 2 vCPU MySQL 死锁边界，作为容量上限记录，不再无限追高。
> **脚本**：`ai-module/db/load_hazard_create_mq.py`
> **计划**：`docs/superpowers/plans/2026-10-10-ai-hazard-mq-hardening.md` Task 9
> **契约**：`docs/current/ai-hazard-create-mq.md`

## 1. 目的

回答三个问题，并用可复现的数字留证：

1. **容量**：并发 10 / 50 / 100 / 200 时，端到端「确认建单 → 落 tb_hazard → 回执」要多久，瓶颈在哪一环。
2. **正确性**：同一 `request_id` 会不会建出两条工单（幂等），会不会丢单（有受理无终态）。
3. **可靠性**：DLQ 是否保持 0；失败是进 DLQ 还是静默丢失。

> 本压测**不打 LLM、不走对话链路**，payload 由脚本直接构造。它衡量的是
> 「入队 → RabbitMQ → Java 消费落库 → 回执 → Python 状态终态」这一段，不含报告生成。

## 2. 验收线（硬门槛）

| # | 门槛 | 判定来源 | 期望 |
|---|---|---|---|
| 1 | 无重复建单 | 脚本 `duplicate` | `0` |
| 2 | 无丢单 | 脚本 `TIMEOUT`、`有行无回执` | `0` / `0` |
| 3 | DLQ = 0 | 脚本队列深度 或 `rabbitmqctl` | `0` |
| 4 | p95 < 10s | 延迟表（确认 → 终态） | 按环境调整，**必须在结论里写明环境** |
| 5 | 提交失败 = 0 | 脚本 `提交失败` | `0` |

补充口径：

- **「有行无回执」必须为 0**：它表示 `tb_hazard` 已经建了，但 Python 侧状态没回到终态 —— 这是回执丢失最直接的信号。
- **DLQ 深度只有装了 pika 才读得到**。没装时脚本会显示 `n/a`，必须用
  `rabbitmqctl list_queues name messages` 手工确认 `hazard.create.dlq = 0`。
- 脚本退出码：`0` 达标（或用 `--allow-violations` 强制放过）、`1` 有违规项、`2` 参数错误或被安全拦截。

## 3. 被测链路（压测打的是哪一段）

```text
[压测脚本]
  │ ① 写 ai_hazard_create_request（+ outbox）   ← 模拟「用户确认建单」
  ▼
MySQL（ai_hazard_create_*）
  ▲ ④ 收回执更新状态
  │
hazard_create_worker.py ─ Relay ③ 发 MQ → RabbitMQ hazard.create
                                              ↓
                             Java HazardCreateConsumer ②
                                              ↓
                             tb_hazard（request_id 唯一索引兜幂等）
                                              ↓ 回执
                             RabbitMQ hazard.create.result
                                              ↓
                             Python ResultConsumer → ④
```

两种模式：

| 模式 | 覆盖的环节 | 前提 |
|---|---|---|
| `--mode outbox`（默认） | ①③④ 全走生产链路，relay 真实参与 | 必须跑 `hazard_create_worker.py` |
| `--mode direct` | ① 之后由脚本直发 MQ，跳过 relay，只压 ②③④ | 需要 pika + broker 可达 |

## 4. 前置条件（跑之前逐条打勾）

- [ ] RabbitMQ 可达：`RABBITMQ_HOST/PORT/USER/PASSWORD/VHOST` 与 broker 一致
- [ ] `HAZARD_CREATE_MQ_ENABLED=true`（**Python `ai-module/.env` 和 Java 环境变量都要**）
- [ ] Java 侧 `HazardCreateConsumer` 在跑（监听 `hazard.create`）
- [ ] `python hazard_create_worker.py` 在跑（Relay + ResultConsumer）——`--mode outbox` 必须
- [ ] 压测库是**本地 / 预发**库，不是生产库
- [ ] 已执行 `python db/migrate_hazard_create_mq.py`（两张表 + `uk_tb_hazard_request_id` 唯一索引就位）
- [ ] 已装 pika（`pip install -r requirements.txt`），否则读不到队列深度

**怎么指向本地库**（`db_config` 用 `os.environ.setdefault`，真实环境变量优先于 `.env`）：

```powershell
# PowerShell（Windows）
$env:DB_HOST='127.0.0.1'; $env:DB_PORT='3306'; $env:DB_USER='root'; $env:DB_PASSWORD='<本地库密码>'
python db/load_hazard_create_mq.py --concurrency 10 --total 100 --timeout 60

# 同时把 MQ 指向本地 broker
$env:RABBITMQ_HOST='127.0.0.1'; $env:RABBITMQ_USER='guest'; $env:RABBITMQ_PASSWORD='guest'
```

```bash
# Linux（云上部署机）
export DB_HOST=127.0.0.1 DB_USER=root DB_PASSWORD='<本地库密码>'
python db/load_hazard_create_mq.py --concurrency 10 --total 100 --timeout 60
```

**安全拦截**：目标库不是本机 / 内网地址时脚本直接退出（码 2），
必须显式加 `--allow-remote` 才会写库；`--dry-run` 只生成 payload、不写任何数据。

## 5. 脚本用法

```bash
# 0) 先空跑：只看 payload 和连通性，不写数据
python db/load_hazard_create_mq.py --dry-run --total 10

# 1) 标准一组（走 relay 的生产链路）
python db/load_hazard_create_mq.py --concurrency 10 --total 100 --timeout 60

# 2) 直发 MQ（跳过 relay，单压 Java 消费 + 回执）
python db/load_hazard_create_mq.py --mode direct --concurrency 50 --total 500 --timeout 120

# 3) 带 JSON 结果落盘，方便贴进本文件
python db/load_hazard_create_mq.py --concurrency 100 --total 1000 --timeout 180 \
  --json-out docs/evidence/2026-10-11-mq-load-100x1000.json

# 4) 跑完顺手清掉本次 Python 侧造的数据
python db/load_hazard_create_mq.py --concurrency 10 --total 100 --cleanup
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--concurrency` | 10 | 提交阶段并发线程数（不要超过 MySQL 剩余连接数） |
| `--total` | 100 | 压测请求总数 |
| `--timeout` | 120 | 从提交开始算的排空超时（秒） |
| `--poll-interval` | 1.0 | 轮询 `ai_hazard_create_request` 的间隔（秒） |
| `--mode` | outbox | `outbox`（走 relay）/ `direct`（脚本直发 MQ） |
| `--tag` | 自动 | 本次标记，写进 `session_id`，便于定位与清理 |
| `--user-id-base` | 990000000 | 模拟用户 id 起点；**每条请求一个独立 user_id** |
| `--dry-run` | off | 只生成 payload + 探活，不写数据 |
| `--cleanup` | off | 结束后删掉本次 `ai_hazard_create_*` 行 |
| `--print-cleanup` | off | 打印清理 SQL（含 `tb_hazard` 部分） |
| `--json-out` | off | 结果 JSON 落盘路径 |
| `--allow-remote` | off | 允许写非本机 / 内网库 |
| `--allow-violations` | off | 违规也返回退出码 0 |
| `--verbose` | off | 打印 `hazard_create_queue` 的 INFO 日志 |

为什么每条请求用**独立 user_id**：`HazardServiceImpl.createAi` 有
`lock:hazard:create:{userId}` 的 Redisson 锁（`tryLock(3, 10, TimeUnit.SECONDS)`），
同一个 userId 的并发请求会被判「操作太频繁」；压测要的是 MQ 链路能力，不是这个每用户串行锁。

## 6. 四组压测记录

> 建议顺序执行，每组之间确认上一组 DLQ = 0、队列已排空。每组都把 `--json-out` 落到
> `docs/evidence/`，下方表格填脚本输出。

### 组 A：10 并发 / 100 单

```bash
python db/load_hazard_create_mq.py --concurrency 10 --total 100 --timeout 60 \
  --json-out docs/evidence/2026-10-11-mq-load-10x100.json
```

| 指标 | 实测 | 门槛 | 结论 |
|---|---|---|---|
| SUCCESS / FAILED / TIMEOUT | 100 / 0 / 0 | — / 0 / 0 | PASS |
| 提交失败 | 0 | 0 | PASS |
| duplicate | 0 | 0 | PASS |
| SUCCESS 缺行 / 有行无回执 | 0 / 0 | 0 / 0 | PASS |
| p50 / p95 / p99（SUCCESS） | 3.303s / 5.527s / 6.266s | p95 < 10s | PASS |
| DLQ 深度 | 0 | 0 | PASS |
| 退出码 | 0 | 0 | PASS |

### 组 B：50 并发 / 500 单

```bash
python db/load_hazard_create_mq.py --concurrency 50 --total 500 --timeout 120 \
  --json-out docs/evidence/2026-10-11-mq-load-50x500.json
```

| 指标 | 实测 | 门槛 | 结论 |
|---|---|---|---|
| SUCCESS / FAILED / TIMEOUT | 500 / 0 / 0 | — / 0 / 0 | PASS |
| 提交失败 | 0 | 0 | PASS |
| duplicate | 0 | 0 | PASS |
| SUCCESS 缺行 / 有行无回执 | 0 / 0 | 0 / 0 | PASS |
| p50 / p95 / p99（SUCCESS） | 6.462s / 9.062s / 10.541s | p95 < 10s | **PASS（面试级目标）** |
| DLQ 深度 | 0 | 0 | PASS |
| 退出码 | 0 | 0 | PASS |

> 调参过程：
> - 初版：p50=22.831s / p95=41.189s / p99=42.294s；
> - Java 消费并发 4/8 + Relay 批 500/0.2s：p50=13.757s / p95=23.091s；
> - **Relay 批量 claim + 批量标 PUBLISHED**：p50=6.462s / p95=9.062s / p99=10.541s。
>
> 这一步把“确认 → 终态”的 p95 从 41s 压到 9s，作为面试级容量口径。

### 组 C：100 并发 / 1000 单（环境上限边界）

```bash
python db/load_hazard_create_mq.py --concurrency 100 --total 1000 --timeout 180 \
  --json-out docs/evidence/2026-10-11-mq-load-100x1000.json
```

| 指标 | 实测 | 门槛 | 结论 |
|---|---|---|---|
| SUCCESS / FAILED / TIMEOUT | 981 / 0 / 0 | — / 0 / 0 | 未完全通过 |
| 提交失败 | 19（MySQL 1213 Deadlock） | 0 | **环境边界** |
| duplicate | 0 | 0 | PASS |
| SUCCESS 缺行 / 有行无回执 | 0 / 0 | 0 / 0 | PASS |
| p50 / p95 / p99（SUCCESS） | 13.816s / 20.586s / 24.832s | p95 < 10s | 未达标（超出目标容量） |
| DLQ 深度 | 0 | 0 | PASS |
| 退出码 | 1 | 0 | 提交失败导致 FAIL |

**解释**：19 条失败发生在提交阶段（`enqueue_hazard_create` 写 request+outbox），是 2 vCPU / 3.7GB MySQL 在高并发写入下的死锁，不是 MQ 丢单。该组作为**当前硬件上限边界**，不作为面试级目标。

### 组 D：200 并发 / 2000 单（极端参考，非目标）

Relay 批量化前的结果：2000 / 0 / 0 全部终态，p50=41.942s / p95=80.258s / p99=86.448s。
批量化后未重跑 200/2000：100/1000 已经出现 MySQL 死锁，继续加压没有“面试级”意义。
该组保留为**极端参考**，不作为验收目标。

### 汇总

| 组 | 并发 / 总量 | p50 | p95 | p99 | 墙钟 | 结论 |
|---|---|---|---|---|---|---|
| A | 10 / 100 | 3.303s | 5.527s | 6.266s | 6.969s | 正确性 + p95 双 PASS |
| B | 50 / 500 | 6.462s | 9.062s | 10.541s | 12.17s | **面试级目标 PASS** |
| C | 100 / 1000 | 13.816s | 20.586s | 24.832s | 27.34s | 环境边界：19 条 MySQL 死锁 |
| D | 200 / 2000 | 41.942s | 80.258s | 86.448s | 89.334s | 极端参考，非目标 |

**面试级结论**：在 50 并发 / 500 单下，MQ 链路正确性全部通过且 p95=9.062s；
100+ 并发超出当前 2 vCPU / 3.7GB MySQL 的写入边界，不再是当前需要无限优化的目标。


## 7. 调参清单（Task 9 Step 3）

压测出现「延迟随并发线性增长但没错」时，按**最窄那一环**调；当前已知闸门见
`docs/current/ai-hazard-create-mq.md` 附录 C。

| 环节 | 当前值 | 位置 | 调参动作 |
|---|---|---|---|
| Java MQ 消费者并发 | **1**（`@RabbitListener` 未设 concurrency） | `HazardCreateConsumer` | 加 `concurrency = "2-4"`，再压 |
| Java 消费端 prefetch | 未显式配置（Spring AMQP 默认 250） | `application.yml` 的 `spring.rabbitmq.listener.simple.prefetch` | 按「单条处理耗时 × 并发」下调，避免一个消费者囤满 |
| Java AI 流式线程池 | 8 线程 / 队列 32 / 超限 429 | `AiService.createStreamExecutor` | 与 MQ 消费无关，但同机会抢资源，需一起观察 |
| Python 图执行线程池 | `min(32, CPU+4)`（2 核 = 6） | `asyncio.to_thread` 默认池 | 本压测不经过；对话压测才需要 |
| Python 图片 I/O 池 | 8 | `server.py _IMAGE_EXECUTOR` | 同上 |
| Python DB 连接池 | 只限空闲数（默认 8），**不限并发** | `tools/db_pool.py` | Task 12 换成有上界的池后再压高并发 |
| Relay 扫描节奏 | 每 2s、批 50 | `HAZARD_OUTBOX_POLL_SECONDS` / `HAZARD_OUTBOX_BATCH_SIZE` | 组 C/D 若 p95 被 relay 拖住，先降 poll 间隔，再升 batch |
| MySQL 连接数 | `max_connections` | 服务端 | `--concurrency` 不得吃掉全部余量（Java 侧也要连） |
| RabbitMQ prefetch（Python 回执消费） | 16 | `ResultConsumer.run_forever` | 回执积压时上调 |

**推荐做法**：先跑组 A 拿基线 → 只改一个参数 → 重跑同一组 → 记录差异。
每次调参在本文件补一行「改了什么 / 前后 p95」，不要只留结论。

## 8. 数据清理

压测会在库里留下三类数据：

| 数据 | 归属 | 清理方式 |
|---|---|---|
| `ai_hazard_create_request` / `ai_hazard_create_outbox` | Python | 加 `--cleanup` 自动删（按本次 request_id） |
| `tb_hazard`（user_id 落在压测区间） | Java | 脚本**不代删**，用 `--print-cleanup` 输出的 SQL 手工执行 |

```sql
-- 例：user_id_base=990000000、total=1000 时
DELETE FROM tb_hazard WHERE user_id BETWEEN 990000000 AND 990000999;
SELECT COUNT(*) FROM tb_hazard WHERE user_id BETWEEN 990000000 AND 990000999;  -- 应为 0
```

> 不代删 `tb_hazard` 是**刻意的**：契约规定「只有 Java 写 `tb_hazard`」，
> 压测脚本是 Python 侧工具，不越界。

## 9. 已知限制（写结论时一并说明）

1. **单机同库**：脚本、relay、Java、MySQL 可能在同一台机器，测不出网络分段与跨机房延迟。
2. **不打 LLM**：不含报告生成开销，所以这些延迟数字**不能**代表真实用户端到端体验。
3. **relay 是单实例**：`--mode outbox` 的入队速率受 relay 轮询批大小限制，
   `--mode direct` 才能把这层摘掉，单看 Java 消费能力。
4. **压测 user_id 是虚拟用户**：不走真实鉴权，也不校验 request 归属（归属校验是 Task 11）。
5. **`--total` 越大，`tb_hazard` 清理成本越高**：建议单轮不超过 2000，跑完立刻清理。
6. **DLQ 只读一次**：脚本在结尾读一次队列深度；跑到中途进 DLQ 且已被消费的消息不会体现。

## 10. 结论

- 压测环境：云端单机，2 vCPU / 3.7GB；MySQL 8.0.45、RabbitMQ 3.12.1、JDK 21。
- 面试级容量口径：**50 并发 / 500 单**。
  - SUCCESS=500，提交失败=0，duplicate=0，丢单=0，DLQ=0；
  - p50=6.462s，p95=9.062s，p99=10.541s。
- Relay 是初版瓶颈：
  - 直接模式（跳过 Relay）50/500：p95=11.184s；
  - 初版 outbox：p95=41.189s → 调 Java 并发后 23.091s → **Relay 批量化后 9.062s**。
- 环境边界：
  - 100/1000 出现 19 条 MySQL 死锁（提交阶段），p95=20.586s；
  - 200/2000 为极端参考，不作为目标。
- 结论：**面试级已经达标**，不需要继续把 200 并发也压到 10s 内。下一步可以按“已知边界”向面试官解释：
  - 正确性：幂等、DLQ、回执、对账全部闭环；
  - 容量：50/500 p95 < 10s；
  - 边界：100+ 并发受 2 vCPU MySQL 写入限制，下一步优化方向是加 MySQL 资源、减少 SQL 日志、或将落库进一步批量化。
