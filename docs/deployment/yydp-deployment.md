# yydp 全栈部署 Runbook

适用项目：`E:\java\yydp`（Git: `https://github.com/liyuhh985/hmdp.git`）

## 1. 当前线上形态

```text
浏览器
  -> Nginx :80 (/var/www/hmdp 静态前端)
  -> Nginx /api/* -> Java :9000
Java :9000 -> MySQL hmdp
Java :9000 -> Redis
Java :9000 -> RabbitMQ
Java :9000 -> DeepSeek / DashScope
```

| 组件 | 端口 | 目录/文件 | 启动脚本 |
|---|---|---|---|
| 前端静态站 | 80 | `/var/www/hmdp` | Nginx |
| Java 后端 | 9000 | `/home/ubuntu/yydp-backend.jar` | `/home/ubuntu/start-yydp.sh` |
| 源码参考 | - | `/home/ubuntu/yydp-source` | - |
| Python AI（可选，当前未运行） | 默认 8000 | `/home/ubuntu/yydp-source/python-ai` | 需手动启动 |

## 2. 部署前检查

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  df -h / &&
  java -version &&
  mvn -v | head -3 &&
  npm -v &&
  ss -lntp | grep -E ":(80|9000|3306|6379|5672)\\b" &&
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1/ &&
  curl -s -o /dev/null -w "swagger=%{http_code}\\n" http://127.0.0.1:9000/swagger-ui/index.html
'
```

期望：

```text
frontend=200
swagger=200
```

## 3. 构建 Java 后端

在本地或装有 Maven/JDK 的构建机执行：

```powershell
cd E:\java\yydp
mvn -q -DskipTests package
Get-ChildItem .\target\*.jar
```

预期产物：

```text
E:\java\yydp\target\hm-dianping-0.0.1-SNAPSHOT.jar
```

注意：

- 该 Jar 是 Spring Boot fat jar。
- `application.yaml` 默认端口是 `8081`，但线上必须覆盖为 `9000`。
- 不要在源码里写入真实密码；线上依赖 `/home/ubuntu/.yydp.env`。

## 4. 部署 Java 后端

### 4.1 上传新 Jar

```powershell
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$jar = 'E:\java\yydp\target\hm-dianping-0.0.1-SNAPSHOT.jar'
scp $jar "ubuntu@106.53.219.214:/home/ubuntu/yydp-backend-new-$stamp.jar"
```

### 4.2 云端备份并替换

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  cd /home/ubuntu
  STAMP='"$stamp"'
  test -f "yydp-backend-new-$STAMP.jar"
  cp -p yydp-backend.jar "yydp-backend.jar.bak-$STAMP"
  sha256sum "yydp-backend-new-$STAMP.jar"
  mv "yydp-backend-new-$STAMP.jar" yydp-backend.jar
'
```

### 4.3 重启

必须使用启动脚本，脚本会加载 `.yydp.env`：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '/home/ubuntu/restart-yydp.sh'
```

如果脚本因端口未释放失败，等待 3 秒后重试：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'sleep 3; /home/ubuntu/start-yydp.sh'
```

不要手工执行不带环境变量的 `java -jar`。必须手工启动时，先执行：

```bash
set -a
source /home/ubuntu/.yydp.env
set +a
```

并确保 `SERVER_PORT=9000`。

### 4.4 健康检查

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  ss -lntp | grep ":9000" &&
  curl -s -o /dev/null -w "swagger=%{http_code}\\n" http://127.0.0.1:9000/swagger-ui/index.html
'
```

期望 `swagger=200`。根路径 `http://127.0.0.1:9000/` 返回 401 是正常安全行为。

### 4.5 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  cd /home/ubuntu
  cp -f yydp-backend.jar.bak-<STAMP> yydp-backend.jar
  /home/ubuntu/restart-yydp.sh
'
```

## 5. 部署前端

yydp 当前前端是静态 HTML 站点，不是 Vite 构建产物。

源目录（云端）：`/home/ubuntu/hmdp-frontend`  
发布目录（Nginx root）：`/var/www/hmdp`

### 5.1 备份

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  STAMP=$(date +%Y%m%dT%H%M%S)
  cp -a /var/www/hmdp "/var/www/hmdp.bak-$STAMP"
  echo $STAMP
'
```

### 5.2 同步静态文件

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  rsync -a --delete --exclude ".git" /home/ubuntu/hmdp-frontend/ /var/www/hmdp/
'
```

如果前端源码只在本机，先上传到云端临时目录，再执行同样的 `rsync`。

### 5.3 校验并 reload Nginx

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  sudo nginx -t
  sudo systemctl reload nginx
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1/
'
```

期望 `frontend=200`。

### 5.4 回滚

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  rsync -a --delete "/var/www/hmdp.bak-<STAMP>/" /var/www/hmdp/
  sudo nginx -t && sudo systemctl reload nginx
'
```

## 6. 可选：部署 yydp Python AI

当前线上没有运行 yydp 的 `python-ai`。只有明确需要 `/ai/agent`、`/ai/react`、`/ai/multi` 时才启动。

重要冲突：

- `main.py` 默认监听 `8000`。
- 安全隐患平台 Python AI 也监听 `8000`。
- 两个服务不能同时使用 `8000`。

启动前必须把 yydp `python-ai/main.py` 的端口改为 `8010`，或用启动命令显式指定端口。

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  set -eu
  cd /home/ubuntu/yydp-source/python-ai
  test -f .env || { echo "缺少 .env"; exit 1; }
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -q -r requirements.txt
  nohup python -u main.py > /home/ubuntu/yydp-ai.log 2>&1 &
  echo started
'
```

启动异常时查看：

```bash
tail -n 100 /home/ubuntu/yydp-ai.log
```

## 7. Nginx 说明

yydp 前端使用：

```text
/etc/nginx/sites-enabled/hmdp
```

核心规则：

```text
listen 80
root /var/www/hmdp
/api/ -> 127.0.0.1:9000
/ai   -> 127.0.0.1:9000
```

不要改 root 到安全隐患平台目录。

## 8. 冒烟测试

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 '
  curl -s -o /dev/null -w "frontend=%{http_code}\\n" http://127.0.0.1/
  curl -s -o /dev/null -w "swagger=%{http_code}\\n" http://127.0.0.1:9000/swagger-ui/index.html
  ps -eo pid,args | grep "[y]ydp-backend.jar"
  tail -n 30 /home/ubuntu/yydp-backend.log
'
```

通过标准：

```text
frontend=200
swagger=200
存在 java ... yydp-backend.jar 进程
日志无启动异常
```

## 9. 常见故障

### 端口 8081 被占用

原因：yydp 后端没有设置 `SERVER_PORT=9000`，使用了默认 8081，与安全隐患平台前端冲突。

处理：

```bash
grep -n SERVER_PORT /home/ubuntu/.yydp.env
```

确认 `SERVER_PORT=9000` 后重启。

### Redis 认证失败

原因：启动时没有加载 `.yydp.env`。

处理：

```bash
/home/ubuntu/stop-yydp.sh
sleep 2
/home/ubuntu/start-yydp.sh
```

### 前端 404 或路由错误

检查 `/var/www/hmdp` 是否包含 `index.html`，并确认 Nginx root 没被改错。

### RabbitMQ 连接失败

检查 `.yydp.env` 中相关变量是否存在；不要在终端打印变量值。
