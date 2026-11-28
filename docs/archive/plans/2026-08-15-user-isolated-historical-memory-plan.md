> 状态：implemented
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 用户级历史记忆隔离与持久化 Implementation Plan

> **For agentic workers:** 本计划由当前会话内联执行（executing-plans 风格），按任务逐个完成并做检查点。

**Goal:** 将历史记忆改为按 user_id 隔离，使用云端 MySQL 持久化 + Redis 缓存，并让图片分析接口必须登录。

**Architecture:** Java 从 JWT 取 userId 传给 Python；Python 在分析完成后按 userId 归档到 MySQL，读取时先查 Redis 再回源 MySQL；图片分析不再注入历史记忆。

**Tech Stack:** Java 21 / Spring Security、Python 3 / FastAPI / pymysql / redis-py、MySQL、Redis。

## Global Constraints

- 不修改与本功能无关的文件；工作区已有大量用户未提交修改，必须保留。
- 不输出、不打印真实密码、Token、API Key。
- 旧 `historical_memory.json` 数据清空废弃。
- 前端 AI 分析请求已带 Bearer 头，云服务器验证后按需最小修改。
- MySQL/Redis 在云服务器，Python 本地通过 `.env` 连接；新增 `REDIS_*` 配置。

---

### Task 1: Python 配置新增 Redis

**Files:**
- Modify: `ai-module/config.py`
- Modify: `ai-module/.env`

**Interfaces:**
- Produces: `REDIS_HOST: str`、`REDIS_PORT: int`、`REDIS_PASSWORD: str`、`REDIS_DB: int`

- [ ] 在 `config.py` 增加：

```python
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
```

- [ ] 在 `.env` 增加 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`REDIS_DB`（值写入本地 `.env`，不提交）。
- [ ] 安装依赖：`pip install redis`

### Task 2: memory.py 增加 MySQL+Redis 存储

**Files:**
- Modify: `ai-module/core/memory.py`
- Test: `ai-module/tests/test_memory_store.py`（新建）

**Interfaces:**
- Produces:
  - `archive_analysis(user_id: int, vision: dict, report: str, dialogue: str = "")`
  - `get_historical_context(user_id: int) -> str`
  - `get_historical(user_id: int) -> HistoricalMemory`（兼容现有调用）

- [ ] 新增 MySQL DAO：连接用 `db_config.DB_CONFIG`，写入 `ai_historical_analysis`，读取偏好统计与最近 5 条。
- [ ] 新增 Redis 缓存：key `ai:hist:{user_id}:context`，读取未命中回源 MySQL 并回填；归档后删除 key。
- [ ] Redis 异常时捕获并降级到 MySQL。
- [ ] 保留 `WorkingMemory` 不变；移除 JSON 单例读写与旧文件逻辑。

### Task 3: orchestrator.py 移除历史注入并传 user_id 归档

**Files:**
- Modify: `ai-module/core/orchestrator.py`

- [ ] `_run_pipeline` 删除 `historical.get_context_for_new_analysis()` 注入。
- [ ] `analyze_stream` 同步删除历史注入。
- [ ] `archive_working_to_historical` 改为 `archive_working_to_historical(user_id, session_id, report)`，内部调用 `archive_analysis(user_id, ...)`。

### Task 4: server.py 接收并传递 user_id

**Files:**
- Modify: `ai-module/server.py`

- [ ] `analyze`、`analyze_stream`、`chat`、`chat_stream` 增加 `user_id: int = Form(...)`。
- [ ] 调用 `orch.analyze/analyze_stream/chat/chat_stream` 时传入 `user_id`。
- [ ] `archive_working_to_historical(user_id, ...)` 在分析完成时调用。

### Task 5: Java SecurityConfig 要求登录

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/config/SecurityConfig.java`

- [ ] 从 `permitAll()` 移除 `/api/ai/analyze`、`/api/ai/analyze/stream`。

### Task 6: AiController 提取 userId

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/controller/AiController.java`

- [ ] 在 `analyze`、`analyzeStream`、`chat`、`chatStream` 中：

```java
Long userId = (Long) SecurityContextHolder.getContext()
        .getAuthentication().getPrincipal();
```

- [ ] 调用 Service 时传入 `userId`。

### Task 7: AiService 传递 userId 给 Python

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/service/AiService.java`

- [ ] `analyze/analyzeStream/chat/chatStream` 增加 `Long userId` 参数。
- [ ] multipart body 增加 `body.add("user_id", userId);`。

### Task 8: 测试

**Files:**
- Test: `ai-module/tests/test_memory_store.py`
- Modify: 受影响的 Python 单测（server 与 orchestrator 相关）

- [ ] 用户隔离测试：user A 归档后，user B 的上下文为空。
- [ ] 更新受影响单测的 `user_id` 参数。
- [ ] Java 编译检查：`mvn -pl safety-web -am compile`。

### Task 9: 数据库与连通性

- [ ] 云端 MySQL 执行建表 DDL。
- [ ] 本地验证 3306/6379 连通。
- [ ] `pip install redis` 完成。

### Task 10: 前端验证

- [ ] SSH 登录云服务器，检查 `AnalysisView.vue` 的 AI 请求是否带 Bearer。
- [ ] 如有缺失，最小修改并 `npm run build`、部署 `/var/www/safety-platform`。

### Task 11: 冒烟验证与提交

- [ ] 运行 Python 测试通过。
- [ ] 本地启动冒烟：登录态调用分析接口返回正常、归档成功。
- [ ] 分文件提交变更。