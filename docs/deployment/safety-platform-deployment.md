> 状态：current
> 最后核对：2026-10-14
> 说明：部署主入口

# 安全隐患平台全栈部署 Runbook

适用项目：`E:\java\newProject`（Git: `https://github.com/liyuhh985/aisafety-platform.git`）

## 1. 当前线上形态

```text
浏览器 :8081
  -> Nginx /var/www/safety-platform
  -> /api/* -> Java :8080
Java :8080
  -> MySQL safety_platform
  -> Redis
  -> MinIO
  -> Python AI :8000 /api/ai/*
  -> RabbitMQ :5672（建单消息 / 回执）
Python AI :8000
  -> MiMo 大模型
  -> Milvus :19530（可降级 MySQL）
  -> 高德地理编码
  -> RabbitMQ :5672 / safety.hazard（发布建单消息 / 消费回执；worker 独立进程）
    · 建单队列 hazard.create -> Java 消费 -> 写 tb_hazard -> 回执 hazard.create.result
```

| 组件 | 端口 | 目录/文件 | 启动方式 |
|---|---|---|---|
| 前端 | 8081 | `/var/www/safety-platform` | Nginx |
| Java 后端 | 8080 | `/home/ubuntu/safety-backend.jar` | `/home/ubuntu/start-backend.sh` |
| Python AI | 8000 | `/home/ubuntu/ai-module` | `venv/bin/python3 -u server.py` |
| Python MQ worker | — | `/home/ubuntu/ai-module` | `/home/ubuntu/restart-hazard-worker.sh`（单实例） |
| RabbitMQ | 5672 / 15672 | 系统服务 | `systemctl`（`rabbitmq-server`），管理台 15672 |
| MySQL | 3306 | `safety_platform` | 系统 MySQL |
| Redis | 6379 | 由 env 指定 DB | 系统 Redis |
| Milvus | 19530 | `/home/ubuntu/milvus` | Docker Compose |
| MinIO | 9100 | Docker 容器 `minio` | Docker |
| Nginx | 8081 | `/etc/nginx/sites-enabled/safety-platform` | systemd |

## 2. 部署前检查

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  df -h / &&
  java -version &&
  mvn -v | head -3 &&
  node -v &&
  npm -v &&
  docker ps --format "{{.Names}} {{.Status}}" &&
  ss -lntp | grep -E ":(8080|8000|8081|3306|6379|19530|9100|5672|15672)\\b" &&
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1:8081/ &&
  curl -s -o /dev/null -w "java=%{http_code}\\n" http://127.0.0.1:8080/api/ai/health &&
  curl -s -o /dev/null -w "ai=%{http_code}\\n" http://127.0.0.1:8000/api/ai/health &&
  pgrep -af hazard_create_worker.py || echo 'worker=NOT-RUNNING'
'
```

期望：

```text
frontend=200
java=200
ai=200
worker 在跑（MQ 模式；开关为 false 时可不跑）
```

## 3. 环境文件

不要打印内容，只在服务器上 source：

| 文件 | 用途 |
|---|---|
| `/home/ubuntu/.backend.env` | Java 后端：DB、Redis、MinIO、邮件、AI 内部 Token、`RABBITMQ_*` |
| `/home/ubuntu/ai-module/.env` | Python AI：MiMo、MySQL、Milvus、Redis、高德、JAVA_BASE_URL、`RABBITMQ_*` |

已确认的关键非敏感配置：

```text
Python AI: VECTOR_BACKEND=milvus, MILVUS_ENABLED=true, MILVUS_FALLBACK_TO_MYSQL=true
Python AI: MILVUS_HOST=106.53.219.214, MILVUS_PORT=19530
Python AI: DB_NAME=safety_platform
Python AI: JAVA_BASE_URL=http://127.0.0.1:8080
建单路径: MQ 唯一路径（Outbox → RabbitMQ → Java 消费）
RabbitMQ: RABBITMQ_HOST/PORT(5672)/USER/PASSWORD/VHOST 两端必须一致
DB 池: DB_POOL_MAX_CONNECTIONS(默认8) / DB_POOL_MAX_IDLE / DB_POOL_ACQUIRE_TIMEOUT_SECONDS(默认30)
```


## 4. 部署 Python AI

### 4.1 本地打包（不包含 .env 和运行时目录）

在本地 `E:\java\newProject` 执行：

```powershell
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
tar -czf "ai-module-$stamp.tar.gz" `
  --exclude=".env" `
  --exclude="venv" `
  --exclude="__pycache__" `
  --exclude="uploads" `
  --exclude=".pytest_cache" `
  -C ai-module .
scp "ai-module-$stamp.tar.gz" "ubuntu@106.53.219.214:/home/ubuntu/ai-module-$stamp.tar.gz"
```

### 4.2 云端备份并解压

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  STAMP=<STAMP>
  cd /home/ubuntu
  mkdir -p "ai-deploy-backups/$STAMP"
  tar -czf "ai-deploy-backups/$STAMP/ai-module-before.tar.gz" -C ai-module .
  tar -xzf "ai-module-$STAMP.tar.gz" -C ai-module
  cd ai-module
  test -f .env
  venv/bin/python3 -m compileall -q core server.py tools
  venv/bin/python3 -c "import server; print(\"import ok\")"
'
```

如果编译或导入失败：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu
  tar -xzf "ai-deploy-backups/<STAMP>/ai-module-before.tar.gz" -C ai-module
'
```

### 4.3 重启 Python AI

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  pid=$(pgrep -f "^venv/bin/python3 -u server.py$" | head -1 || true)
  if [ -n "$pid" ]; then
    kill -TERM "$pid"
    i=0
    while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 15 ]; do sleep 1; i=$((i+1)); done
  fi
  cd /home/ubuntu/ai-module
  setsid venv/bin/python3 -u server.py >> /home/ubuntu/ai-server.log 2>&1 < /dev/null &
  echo started
'
```

不要用会匹配 SSH 自身命令的 `pkill -f server.py`。

### 4.4 健康检查

```bash
ssh -o BatchMode=yes 106.53.219.214 '
  curl -fsS --max-time 5 http://127.0.0.1:8000/api/ai/health
  echo
  tail -n 30 /home/ubuntu/ai-server.log
'
```

期望返回：

```json
{"status":"ok","model":"mimo-v2.6-flash"}
```

### 4.5 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu
  tar -xzf "ai-deploy-backups/<STAMP>/ai-module-before.tar.gz" -C ai-module
  pid=$(pgrep -f "^venv/bin/python3 -u server.py$" | head -1 || true)
  if [ -n "$pid" ]; then kill -TERM "$pid"; sleep 3; fi
  cd /home/ubuntu/ai-module
  setsid venv/bin/python3 -u server.py >> /home/ubuntu/ai-server.log 2>&1 < /dev/null &
'
```

## 5. 部署 RabbitMQ 与 AI 建任务 worker

> 建单链路契约见 `docs/current/ai-hazard-create-mq.md`；本节只讲「怎么部署 / 启停 / 回滚」。

### 5.1 RabbitMQ（broker）

形态：系统服务 `rabbitmq-server`，端口 `5672`（AMQP）、`15672`（管理台），当前线上 active。

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  systemctl is-active rabbitmq-server
  ss -lntp | grep -E ":(5672|15672)\b"
  sudo -n rabbitmqctl list_queues name messages | grep hazard
'
```

期望：`active`，且 `hazard.create` / `hazard.create.result.q` / `hazard.create.dlq` 三个队列都在。

- 应用凭据 `RABBITMQ_HOST/PORT/USER/PASSWORD/VHOST` 写在两个 env 文件里，两端必须指向同一 broker 与 vhost（线上 vhost 为 `/`）。
- 换机或首次搭建：`sudo apt-get install -y rabbitmq-server`，再建应用用户并授权（用户名/密码只进 env，不写文档、不入库）。
- **5672 / 15672 只走内网**，管理台不要暴露公网。

### 5.2 队列拓扑与 DLX 迁移提醒（重要）

拓扑（Java `RabbitConfig` 与 Python `RabbitPublisher._declare_topology` 必须逐字一致，否则重复声明会 406）：

| 项 | 值 |
|---|---|
| Exchange | `safety.hazard`（topic） |
| 建单 | `hazard.create.requested` → `hazard.create`（Java 消费，带 DLX） |
| 回执 | `hazard.create.result` → `hazard.create.result.q`（Python 消费，带 DLX） |
| DLX / DLQ | `safety.hazard.dlx` → `hazard.create.dlq` |

**迁移提醒**：RabbitMQ 不允许同名队列用不同 `arguments` 重复声明。老环境里若 `hazard.create.result.q`（或 `hazard.create`）已存在但**没有** DLX 参数，升级后重启会报：

```text
PRECONDITION_FAILED - inequivalent arg 'x-dead-letter-exchange'
```

处置（灰度期队列无积压，代价最低）：删队列 → 重启 worker 让它按新参数重新声明。

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  sudo -n rabbitmqctl delete_queue hazard.create.result.q
  /home/ubuntu/restart-hazard-worker.sh
'
```

验证 arguments：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'sudo -n rabbitmqctl list_queues name arguments | grep hazard'
```

期望 `hazard.create` 与 `hazard.create.result.q` 都带 `x-dead-letter-exchange = safety.hazard.dlx`。

> 严禁 `rabbitmqctl reset`（会清掉全部队列与用户）。删队列前先确认它没有积压消息。

### 5.3 worker 启停（单实例）

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '/home/ubuntu/restart-hazard-worker.sh'
```

- 脚本用锚定 pattern `^venv/bin/python3 -u hazard_create_worker\.py$`，避免 `pgrep -f` 误杀调用方自身。
- 日志：`/home/ubuntu/ai-hazard-worker.log`。
- 停止：`pkill -TERM -f '^venv/bin/python3 -u hazard_create_worker\.py$'`；不要用会匹配 SSH 自身的宽 pattern。
- **保持单实例**：Relay 靠 outbox claim 取任务，多实例虽不会重复建单（Java 侧 `request_id` 幂等），但会重复拉消息、增加无谓负载。
- 部署顺序：**先** Python（server + worker，含拓扑声明）→ **再** Java Consumer；反过来会出现消息无人消费。
- `HAZARD_CREATE_WORKER_INLINE=true`（跑在 FastAPI lifespan 里）只用于本地开发，线上用独立 worker。

### 5.4 建单路径（MQ 唯一）

旧同步开关 `HAZARD_CREATE_MQ_ENABLED`、`POST /api/hazard/ai` 与 `task_created` 已删除。建单唯一路径是：

```text
Python Outbox → RabbitMQ → Java Consumer → tb_hazard → 回执 → Python request 状态
```

上线顺序：**Python server + worker → Java backend**。不要只启动一端：只有 Python 会停在 PUBLISHED，只有 Java 没有消息可消费。

### 5.5 巡检 watchdog（卡单 / DLQ 告警）

cron（每 2 分钟，幂等，只在状态变化时写告警）：

```cron
*/2 * * * * /bin/bash /home/ubuntu/hazard-mq-watchdog.sh >/dev/null 2>&1
```

它检查四件事：worker 存活（不在就拉起）、request 卡在 `PUBLISHED` 超 5 分钟（Java 没回执）、卡在 `PENDING` 超 5 分钟（Relay 没发出去）、`hazard.create.dlq` 非 0。

| 文件 | 用途 |
|---|---|
| `/home/ubuntu/hazard-mq-watchdog.log` | 巡检日志 |
| `/home/ubuntu/hazard-mq-alerts.log` | 告警流水 |
| `/home/ubuntu/.hazard-mq-alert-state` | 去重状态（避免重复告警） |
| `/home/ubuntu/.hazard-mq-watchdog.last` | 心跳（证明 cron 还在跑） |

安装后确认心跳在刷新：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'date +%s; cat /home/ubuntu/.hazard-mq-watchdog.last'
```

### 5.6 回滚（MQ 相关）

1. **最轻回滚（先做这个）**：双端开关置 `false` → 重启 Java + Python server；worker 可停可留（不再有消息）。旧同步链路行为与 MQ 上线前一致。
2. **worker 回滚**：从 `ai-deploy-backups/<STAMP>/ai-module-before.tar.gz` 恢复（见 4.5），再 `restart-hazard-worker.sh`。
3. **Java 回滚**：`cp -f safety-backend.jar.bak-<STAMP> safety-backend.jar` + `restart-backend.sh`（见 6.5）。
4. **队列不用回滚**：残留消息都是「待建单请求」，恢复后会被继续消费（`request_id` 幂等保证不重复建单）。确需清空：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'sudo -n rabbitmqctl purge_queue hazard.create'
```

> 清空队列会让对应 request 永远停在 `PENDING/PUBLISHED`（当前没有超时对账），只有在确认这些请求作废后才执行。
## 6. 部署 Java 后端

### 6.1 本地构建

本地需要 Maven。若 `mvn` 不在 PATH，可使用 Trae 自带 Maven：

```powershell
cd E:\java\newProject
& 'C:\Users\21556\.trae\tools\maven\latest\bin\mvn.cmd' -pl safety-web -am -DskipTests package
Get-ChildItem .\safety-web\target\*.jar
```

预期产物：

```text
E:\java\newProject\safety-web\target\safety-web-1.0.0-SNAPSHOT.jar
```

### 6.2 上传、备份、替换

```powershell
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$jar = 'E:\java\newProject\safety-web\target\safety-web-1.0.0-SNAPSHOT.jar'
scp $jar "ubuntu@106.53.219.214:/home/ubuntu/safety-backend-deploy-$stamp.jar"
```

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  cd /home/ubuntu
  STAMP=<STAMP>
  cp -p safety-backend.jar "safety-backend.jar.bak-$STAMP"
  cp -f "safety-backend-deploy-$STAMP.jar" safety-backend.jar
  sha256sum safety-backend.jar
'
```

本地与云端 SHA256 必须一致后再重启。

### 6.3 重启

必须使用脚本，脚本会加载 `.backend.env`：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '/home/ubuntu/restart-backend.sh'
```

如果因端口 8080 尚未释放失败，等待 3 秒重试：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'sleep 3; /home/ubuntu/start-backend.sh'
```

不要直接 `java -jar` 启动；否则 Redis 会因缺少 `.backend.env` 报 `WRONGPASS`。

### 6.4 健康检查

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  ss -lntp | grep ":8080"
  curl -s -o /dev/null -w "java=%{http_code}\\n" http://127.0.0.1:8080/api/ai/health
  tail -n 30 /home/ubuntu/safety-backend.log
'
```

期望 `java=200`。

### 6.5 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu
  cp -f safety-backend.jar.bak-<STAMP> safety-backend.jar
  /home/ubuntu/restart-backend.sh
'
```

## 7. 部署前端

云端前端源码目录：`/home/ubuntu/aisafety-platform-frontend`  
构建产物：`/home/ubuntu/aisafety-platform-frontend/dist`  
发布目录：`/var/www/safety-platform`

### 7.1 备份发布目录

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  STAMP=$(date +%Y%m%dT%H%M%S)
  cp -a /var/www/safety-platform "/var/www/safety-platform.bak-$STAMP"
  echo $STAMP
'
```

### 7.2 构建

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  cd /home/ubuntu/aisafety-platform-frontend
  npm install
  npm run build
  test -f dist/index.html
'
```

如果前端源码只在本机，先在本地 `npm run build`，再把 `dist/` 上传到云端。

### 7.3 发布并 reload

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  rsync -a --delete /home/ubuntu/aisafety-platform-frontend/dist/ /var/www/safety-platform/
  sudo nginx -t
  sudo systemctl reload nginx
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1:8081/
'
```

期望 `frontend=200`。

### 7.4 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  rsync -a --delete "/var/www/safety-platform.bak-<STAMP>/" /var/www/safety-platform/
  sudo nginx -t && sudo systemctl reload nginx
'
```

## 8. MySQL / Milvus / MinIO

### 8.1 MySQL

数据库：`safety_platform`。

必须确认表结构脚本已执行：

```text
ai-module/db/schema/migrate.sql
ai-module/db/schema/migrate_hazard_type_length.sql
ai-module/db/schema/migrate_hazard_create_mq.py    # AI 建任务 MQ：request/outbox 表 + tb_hazard.request_id
```

建单 MQ 相关表（幂等脚本，可重复执行；会先备份 tb_hazard）：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu/ai-module && venv/bin/python3 db/schema/migrate_hazard_create_mq.py
'
```

复核四项：tb_hazard.request_id 列、唯一索引 uk_tb_hazard_request_id、ai_hazard_create_request、ai_hazard_create_outbox。

至少检查：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -a; source /home/ubuntu/.backend.env; set +a
  mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" safety_platform -N -e "SHOW COLUMNS FROM tb_hazard" | grep hazard_type
'
```

期望字段为 `varchar(64)`。如果仍是 `varchar(20)`，先执行：

```sql
ALTER TABLE tb_hazard MODIFY COLUMN hazard_type VARCHAR(64) NOT NULL;
```

### 8.2 Milvus

管理目录：`/home/ubuntu/milvus`  
容器：`milvus-standalone`、`milvus-minio`、`milvus-etcd`

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu/milvus
  docker compose ps
  ss -lntp | grep 19530
'
```

需要启动时：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'cd /home/ubuntu/milvus && docker compose up -d'
```

严禁删除 Milvus 数据卷或 `docker compose down -v`。

### 8.3 MinIO

Docker 容器名：`minio`  
S3 端口：`9100`

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'docker ps --format "{{.Names}} {{.Status}}" | grep -E "minio|milvus"'
```

## 9. Nginx 说明

安全隐患平台前端使用：

```text
/etc/nginx/sites-enabled/safety-platform
```

核心规则：

```text
listen 8081
root /var/www/safety-platform
/api/ -> 127.0.0.1:8080
SSE: proxy_buffering off
```

不要改到 yydp 的 `/var/www/hmdp`。

## 10. 冒烟测试

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1:8081/
  curl -s -o /dev/null -w "java=%{http_code}\\n" http://127.0.0.1:8080/api/ai/health
  curl -sS --max-time 5 http://127.0.0.1:8000/api/ai/health
  echo
'
```

AI 对话冒烟：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  curl -sS -N --max-time 60 \
    -F "message=消防设施老旧，无法正常使用" \
    -F "session_id=deploy-smoke-$(date +%s)" \
    http://127.0.0.1:8000/api/ai/assistant/stream | tail -c 1500
'
```

建单 MQ 冒烟：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  pgrep -af hazard_create_worker.py
  sudo -n rabbitmqctl list_queues name messages | grep hazard
  tail -n 20 /home/ubuntu/ai-hazard-worker.log
  tail -n 20 /home/ubuntu/hazard-mq-alerts.log
'
```

MQ 建单端到端（需要登录态）：在 AI 助手走完「确认建单」后，SSE 应先收到 `task_accepted`，再轮询状态接口到终态。

```bash
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/hazard/requests/$REQUEST_ID
```

期望 `status` 依次出现 `PENDING`/`PUBLISHED`，最终到 `SUCCESS`（带 `hazardId`）或 `FAILED`（带失败原因）。

通过标准：

```text
frontend=200
java=200
AI health status=ok
AI SSE 正常返回 status/chunk/done
worker 进程在；三个 hazard 队列存在；DLQ = 0
建单请求能走到 SUCCESS，或给出明确 FAILED
```

## 11. 常见故障

### 建单一直「创建中」（MQ 模式）

按顺序查四件事：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  pgrep -af hazard_create_worker.py                                                          # worker 必须在
  sudo -n rabbitmqctl list_queues name messages | grep hazard                                # 三个队列 + DLQ
  tail -n 50 /home/ubuntu/ai-hazard-worker.log                                               # relay/consumer 异常
  tail -n 20 /home/ubuntu/hazard-mq-alerts.log                                               # watchdog 告警
'
```

- 卡在 `PENDING`：Relay 没投出去（worker 不在 / outbox 重试到上限 / broker 连不上）。
- 卡在 `PUBLISHED`：Java 没回执（Consumer 没起、建单异常重试耗尽进 DLQ、或回执发送失败被吞）。查 `/home/ubuntu/safety-backend.log` 与 DLQ。

### 队列声明报 PRECONDITION_FAILED / 406 inequivalent arg

同名队列已存在但 arguments 不同（典型：缺 `x-dead-letter-exchange`）。按 5.2 删队列后重启 worker 重建；不要只改一边的参数去凑合另一边。

### DLQ 有消息（hazard.create.dlq 非 0）

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'sudo -n rabbitmqctl list_queues name messages | grep dlq'
```

先看 `/home/ubuntu/safety-backend.log` 里重试耗尽的原因（缺 `requestId`/`userId`/`category`、body 非法、建单持续异常）。**注意**：消息进 DLQ 后对应 request 可能仍停在 `PUBLISHED`，当前没有超时对账，需要人工置 `FAILED` 或重投。

### MQ worker 反复被 watchdog 拉起

看 `/home/ubuntu/ai-hazard-worker.log`：常见是 broker 连不上（`RABBITMQ_*` 两端不一致）、`venv` 缺 `pika`、或 `ai-module/.env` 缺 `DB_*` 导致 Relay 启动即崩。
### Java 启动后立即退出，日志出现 Redis WRONGPASS

原因：没有加载 `.backend.env`。使用 `restart-backend.sh` 或先 `source /home/ubuntu/.backend.env`。

### AI 端口 8000 被占用

检查是否是 yydp 的 `python-ai` 启动在同一端口。两者不能同时用 8000。

### Milvus 不可用

先检查：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'docker ps; cd /home/ubuntu/milvus && docker compose logs --tail=80 standalone'
```

如果 Milvus 短期不可用，Python AI 配置中 `MILVUS_FALLBACK_TO_MYSQL=true` 可以降级到 MySQL。

### 建任务报“系统繁忙”

优先检查 Java 日志中的真实异常：

```bash
grep -nE "ERROR|Exception|Caused by" /home/ubuntu/safety-backend.log | tail -40
```

最近一次同类故障根因是 `hazard_type` 列长度不足。当前应为 `varchar(64)`。

### 前端页面是旧版本

检查 `index.html` 是否 no-cache，以及 `dist` 是否真的同步到 `/var/www/safety-platform`。

### 地图页底图空白（控制台报 `Unimplemented type: 3` / `INVALID_USER_DOMAIN`，或底图近乎空白 / 切换风格后变空白）

当前实现为"**矢量优先 + 栅格自动兜底**"：`MapPage.vue` 加载 SDK 前预检矢量样式接口，可用走 WebGL 官方风格
（macaron / whitesmoke / dark），不可用自动降级栅格瓦片 + 滤镜。历史根因（均已修复）：

1. Key 未配域名白名单 → 矢量样式接口（`custyle.amap.com` / `o4.amap.com`）返回 `INVALID_USER_DOMAIN`，
   PBF 解析失败 → 底图空白。**修复：在高德控制台为该 Key 配置域名白名单**
   （`106.53.219.214`、`safety.onlyliyuu.online`、`onlyliyuu.online`、`www.onlyliyuu.online`）。
2. 栅格兜底时 SDK 默认 `webrd` + `style=8` 浅色瓦片低缩放近乎空白。修复：显式彩色路网瓦片
   `wprd0{1,2,3,4}.is.autonavi.com/appmaptile?...&style=8`（浅白用 `webrd` + `style=7`）。
3. Tailwind v4 preflight 的 `img,video{max-width:100%;height:auto}` 把瓦片 `<img>` 在 0 宽瓦片层内压成
   0 宽（**切换风格后整片空白的主因**）。修复：`src/map-tile-fix.css` 豁免 `.amap-layer img{max-width:none}`。

再次出现时的排查顺序：

1. 确认线上产物：`grep -c getMergedStyleData <MapPage-*.js>`、`grep -c wprd0 <MapPage-*.js>`、
   `grep -c "max-width:none" <index-*.css>` 均非 0；
2. 确认 `dist` 已 rsync 到 `/var/www/safety-platform` 并 reload nginx（见第 7 节）；
3. 浏览器强刷（`Ctrl + F5`），Network 里应看到 `custyle.amap.com/...getMergedStyleData`（200，protobuf，
   矢量模式）或 `wprd0*.is.autonavi.com`（栅格兜底）其一。


## 12. Redis Stack（Python AI 专用，单实例重启恢复）

> 目标：只解决 `server.py` 单实例重启后 LangGraph interrupt 可恢复，不做多实例部署。

- 容器：`safety-redis-stack`
- 镜像：`redis/redis-stack-server:latest`
- 端口：`127.0.0.1:6380 -> 6379`（不占 Java 现有 6379）
- 卷：`safety-redis-stack-data:/data`
- 密码：与 `ai-module/.env` 的 `REDIS_PASSWORD` 一致；不要在文档/聊天中明文记录
- Python `.env`：
  ```text
  REDIS_HOST=127.0.0.1
  REDIS_PORT=6380
  SESSION_BACKEND=redis
  CHECKPOINT_BACKEND=redis
  ```
- Java `/home/ubuntu/.backend.env` 的 Redis 仍指 6379，不变。

### 启动容器

```bash
REDIS_PASSWORD=$(sed -n 's/^REDIS_PASSWORD=//p' /home/ubuntu/ai-module/.env | head -1 | tr -d '\r')
docker run -d --name safety-redis-stack --restart unless-stopped \
  -p 127.0.0.1:6380:6379 \
  -v safety-redis-stack-data:/data \
  -e REDIS_ARGS="--requirepass $REDIS_PASSWORD" \
  redis/redis-stack-server:latest
```

### 重启 Python AI

```bash
bash /home/ubuntu/restart_ai_tmp.sh
bash /home/ubuntu/restart-hazard-worker.sh
curl -sS --max-time 5 http://127.0.0.1:8000/api/ai/health
```

通过标准：

```text
session_backend.effective = redis
checkpoint_backend.effective = redis
checkpoint_backend.error = null
```

### 重启恢复验收

1. 在 AI 助手对话中触发 `confirm_create_task` interrupt；
2. 重启 `server.py`；
3. 用同一 `session_id` 发送确认；
4. 必须恢复 `task_gate` 并完成建单，而不是被当成新会话。
