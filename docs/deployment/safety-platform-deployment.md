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
Python AI :8000
  -> MiMo 大模型
  -> Milvus :19530（可降级 MySQL）
  -> 高德地理编码
  -> Java :8080 /api/hazard/ai（建任务内部接口）
```

| 组件 | 端口 | 目录/文件 | 启动方式 |
|---|---|---|---|
| 前端 | 8081 | `/var/www/safety-platform` | Nginx |
| Java 后端 | 8080 | `/home/ubuntu/safety-backend.jar` | `/home/ubuntu/start-backend.sh` |
| Python AI | 8000 | `/home/ubuntu/ai-module` | `venv/bin/python3 -u server.py` |
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
  ss -lntp | grep -E ":(8080|8000|8081|3306|6379|19530|9100)\\b" &&
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1:8081/ &&
  curl -s -o /dev/null -w "java=%{http_code}\\n" http://127.0.0.1:8080/api/ai/health &&
  curl -s -o /dev/null -w "ai=%{http_code}\\n" http://127.0.0.1:8000/api/ai/health
'
```

期望：

```text
frontend=200
java=200
ai=200
```

## 3. 环境文件

不要打印内容，只在服务器上 source：

| 文件 | 用途 |
|---|---|
| `/home/ubuntu/.backend.env` | Java 后端：DB、Redis、MinIO、邮件、AI 内部 Token |
| `/home/ubuntu/ai-module/.env` | Python AI：MiMo、MySQL、Milvus、Redis、高德、JAVA_BASE_URL |

已确认的关键非敏感配置：

```text
Python AI: VECTOR_BACKEND=milvus, MILVUS_ENABLED=true, MILVUS_FALLBACK_TO_MYSQL=true
Python AI: MILVUS_HOST=106.53.219.214, MILVUS_PORT=19530
Python AI: DB_NAME=safety_platform
Python AI: JAVA_BASE_URL=http://127.0.0.1:8080
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

## 5. 部署 Java 后端

### 5.1 本地构建

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

### 5.2 上传、备份、替换

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

### 5.3 重启

必须使用脚本，脚本会加载 `.backend.env`：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '/home/ubuntu/restart-backend.sh'
```

如果因端口 8080 尚未释放失败，等待 3 秒重试：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'sleep 3; /home/ubuntu/start-backend.sh'
```

不要直接 `java -jar` 启动；否则 Redis 会因缺少 `.backend.env` 报 `WRONGPASS`。

### 5.4 健康检查

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  ss -lntp | grep ":8080"
  curl -s -o /dev/null -w "java=%{http_code}\\n" http://127.0.0.1:8080/api/ai/health
  tail -n 30 /home/ubuntu/safety-backend.log
'
```

期望 `java=200`。

### 5.5 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu
  cp -f safety-backend.jar.bak-<STAMP> safety-backend.jar
  /home/ubuntu/restart-backend.sh
'
```

## 6. 部署前端

云端前端源码目录：`/home/ubuntu/aisafety-platform-frontend`  
构建产物：`/home/ubuntu/aisafety-platform-frontend/dist`  
发布目录：`/var/www/safety-platform`

### 6.1 备份发布目录

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  STAMP=$(date +%Y%m%dT%H%M%S)
  cp -a /var/www/safety-platform "/var/www/safety-platform.bak-$STAMP"
  echo $STAMP
'
```

### 6.2 构建

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

### 6.3 发布并 reload

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

### 6.4 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  rsync -a --delete "/var/www/safety-platform.bak-<STAMP>/" /var/www/safety-platform/
  sudo nginx -t && sudo systemctl reload nginx
'
```

## 7. MySQL / Milvus / MinIO

### 7.1 MySQL

数据库：`safety_platform`。

必须确认表结构脚本已执行：

```text
ai-module/db/migrate.sql
ai-module/db/migrate_hazard_type_length.sql
```

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

### 7.2 Milvus

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

### 7.3 MinIO

Docker 容器名：`minio`  
S3 端口：`9100`

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'docker ps --format "{{.Names}} {{.Status}}" | grep -E "minio|milvus"'
```

## 8. Nginx 说明

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

## 9. 冒烟测试

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

通过标准：

```text
frontend=200
java=200
AI health status=ok
AI SSE 正常返回 status/chunk/done
```

## 10. 常见故障

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
