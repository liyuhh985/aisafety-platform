# AI 部署总入口：yydp + 安全隐患平台

本目录是给 AI 部署代理使用的操作手册。执行前先阅读本文件，然后按目标任务阅读对应的项目 Runbook。

- yydp：[`docs/deployment/yydp-deployment.md`](./yydp-deployment.md)
- 安全隐患平台：[`docs/deployment/safety-platform-deployment.md`](./safety-platform-deployment.md)

## 0. 执行原则

AI 部署代理必须遵守：

1. 只读探查优先：先备份、校验、再替换。
2. 严禁打印、复制或提交任何密码、Token、API Key。需要环境变量时，在服务器上 `source` 对应 `.env` 文件，不要把内容回显到终端。
3. 不要删除以下目录或数据卷：
   - `/home/ubuntu/ai-deploy-backups`
   - `/home/ubuntu/safety-backend.jar.bak-*`
   - `/home/ubuntu/milvus`
   - `/var/www/hmdp`
   - `/var/www/safety-platform`
4. 不要用会匹配 SSH 自身命令行的 `pkill -f xxx.jar`。停止 Java 时优先使用项目自带 `stop-*.sh`，或使用端口定位：
   `pid=$(sudo lsof -ti :PORT)`。
5. 每次部署必须完成“备份 → 上传 → 校验 → 重启 → 健康检查 → 冒烟测试”六步。
6. 任何一步失败，立即回滚到最近备份，不要把线上留在半启动状态。

## 1. 云服务器快照

连接信息：

```text
SSH: ubuntu@106.53.219.214
工作目录: /home/ubuntu
系统: Ubuntu
JDK: 21.0.11
Maven: /usr/bin/mvn
Node: /usr/bin/node (v26.5.0)
npm: /usr/bin/npm (11.17.0)
rsync: /usr/bin/rsync
Docker: 已安装，当前用户可直接执行 docker
磁盘: 约 59G，部署前用 `df -h /` 检查，至少保留 5G
```

当前端口与用途：

| 端口 | 项目 | 进程/用途 | 目录或入口 |
|---|---|---|---|
| 80 | yydp | Nginx 静态站点 + 反代 | `/var/www/hmdp` |
| 443 | openclaw | OpenClaw SSL 接口 | `/etc/nginx/sites-enabled/openclaw` |
| 8081 | 安全隐患平台 | 前端静态站点 | `/var/www/safety-platform` |
| 8080 | 安全隐患平台 | Java 后端 | `/home/ubuntu/safety-backend.jar` |
| 8000 | 安全隐患平台 | Python AI (FastAPI) | `/home/ubuntu/ai-module` |
| 9000 | yydp | Java 后端 | `/home/ubuntu/yydp-backend.jar` |
| 3306 | 两套项目共用 | MySQL | `safety_platform` / `hmdp` 两个库 |
| 6379 | 两套项目共用 | Redis | 通过各自 env 区分 DB/密码 |
| 5672 | yydp | RabbitMQ | yydp Java 后端使用 |
| 19530 | 安全隐患平台 | Milvus gRPC | `/home/ubuntu/milvus` |
| 9100 | 安全隐患平台 | MinIO S3 API | Docker 容器 `minio` |

部署前必须执行：

```bash
ssh -o BatchMode=yes ubuntu@106.53.219.214 'hostname; whoami; df -h /; ss -lntp | grep -E ":(80|443|8000|8080|8081|9000|3306|6379|5672|19530|9100)\\b"'
```

## 2. 源码仓库

本地源码根目录：

| 项目 | 本地目录 | Git remote | 当前分支 |
|---|---|---|---|
| 安全隐患平台 | `E:\java\newProject` | `https://github.com/liyuhh985/aisafety-platform.git` | `main` |
| yydp | `E:\java\yydp` | `https://github.com/liyuhh985/hmdp.git` | `main` |

云服务器上的源码目录仅作参考，不能假设它们与本地工作区一致：

- 安全隐患平台源码参考：`/home/ubuntu/aisafety-platform`
- yydp 源码参考：`/home/ubuntu/yydp-source`

默认部署策略：**本地构建 → 上传产物 → 云端重启**。只有确认云端源码与本地一致时，才在云端直接 `mvn package` 或 `npm run build`。

## 3. 环境文件

以下文件包含真实密钥，只允许在服务器上 `source`，禁止 `cat` 或打印内容：

| 文件 | 项目 | 用途 |
|---|---|---|
| `/home/ubuntu/.backend.env` | 安全隐患平台 Java | DB、Redis、MinIO、邮件、AI 内部 Token |
| `/home/ubuntu/ai-module/.env` | 安全隐患平台 Python AI | MiMo、MySQL、Milvus、Redis、高德、Java 内部地址 |
| `/home/ubuntu/.yydp.env` | yydp Java | MySQL、Redis、RabbitMQ、DeepSeek、DashScope |
| `/home/ubuntu/yydp-source/python-ai/.env` | yydp Python AI（可选） | DeepSeek、DashScope、LangFuse |

## 4. 当前已验证健康检查

执行部署前后都应检查：

```text
安全隐患平台前端: http://127.0.0.1:8081/              -> 200
安全隐患平台 Java: http://127.0.0.1:8080/api/ai/health -> 200
安全隐患平台 AI:   http://127.0.0.1:8000/api/ai/health -> 200
yydp 前端:        http://127.0.0.1/                    -> 200
yydp Swagger:     http://127.0.0.1:9000/swagger-ui/index.html -> 200
```

## 5. 推荐部署顺序

### 只部署 yydp

```text
1. 检查 MySQL / Redis / RabbitMQ
2. 构建 yydp Java Jar
3. 备份并替换 /home/ubuntu/yydp-backend.jar
4. 用 restart-yydp.sh 重启（必须加载 .yydp.env，端口必须为 9000）
5. 部署 /var/www/hmdp 前端静态文件
6. nginx -t && reload
7. 冒烟测试
```

### 只部署安全隐患平台

```text
1. 检查 MySQL / Redis / Milvus / MinIO
2. 部署 Python AI 到 /home/ubuntu/ai-module，重启 8000
3. 构建并部署 Java Jar 到 /home/ubuntu/safety-backend.jar，重启 8080
4. 构建前端并部署到 /var/www/safety-platform
5. nginx -t && reload
6. 冒烟测试
```

### 两个项目同时部署

先 yydp，后安全隐患平台，最后统一 reload Nginx。因为 yydp 后端默认端口与安全隐患平台前端同为 8081，必须确认 yydp 使用 `SERVER_PORT=9000` 后再启动。

## 6. 回滚原则

每个项目 Runbook 都定义了具体回滚命令。通用规则：

1. Jar 回滚：恢复 `*.jar.bak-*`，再执行对应 `restart-*.sh`。
2. 前端回滚：恢复 `/var/www/*.bak-*` 目录，再 `sudo nginx -t && sudo systemctl reload nginx`。
3. AI 回滚：恢复 `ai-deploy-backups/<timestamp>/` 中的 Python 文件，再重启 Python 进程。
4. 配置回滚：不要修改 `.env` 文件；如果必须修改，先复制为 `.env.bak-<timestamp>`。

## 7. AI 执行结束报告格式

部署完成后必须报告：

```text
项目：
部署时间：
变更文件/产物：
备份位置：
重启的进程与端口：
健康检查结果：
冒烟测试结果：
是否需要回滚：
```
