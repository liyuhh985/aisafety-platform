> 状态：implemented
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 用户级历史记忆隔离与持久化设计

日期：2026-08-15
状态：已确认，直接进入实施

## 背景与问题

- 当前 `HistoricalMemory` 是全局单例，没有 `user_id` 维度，多用户部署时会跨用户串记忆。
- 历史记忆只持久化到本地 JSON 文件（`historical_memory.json`），不适合多用户、多实例。
- 图片分析接口 `/api/ai/analyze`、`/api/ai/analyze/stream` 在 Spring Security 中是 `permitAll()`，Java 拿不到可信 `userId`。

## 已确认决策

1. 图片分析接口改为必须登录，Java 从 `SecurityContext` 取 `userId`。
2. Java 把 `userId` 通过 multipart 请求体传给 Python。
3. 图片分析流程不再注入历史记忆（移除 `get_context_for_new_analysis()` 注入）。
4. 历史记忆按 `user_id` 隔离，MySQL 持久化 + Redis 缓存，Redis 不可用时降级到 MySQL。
5. 旧 `historical_memory.json` 数据清空废弃，不再读写。
6. 本次不把历史记忆接入 chat，只为未来 chat 功能准备存储与读取能力。

## 数据流

```text
前端带 JWT
-> Java JwtAuthenticationFilter 校验并放入 SecurityContext
-> AiController 取 userId
-> AiService 把 userId 加入 multipart body
-> Python server.py 接收 user_id
-> Orchestrator 分析流程：不再读取历史记忆
-> 分析完成：按 user_id 归档到 MySQL，并更新 Redis 缓存
-> 未来 chat：按 user_id 读取该用户自己的历史上下文
```

## MySQL 数据模型

新表：

```sql
CREATE TABLE IF NOT EXISTS ai_historical_analysis (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  hazard_category VARCHAR(64) NOT NULL,
  severity VARCHAR(16) NOT NULL,
  description VARCHAR(500) NOT NULL,
  report TEXT NOT NULL,
  dialogue TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

偏好统计：

```sql
SELECT hazard_category, COUNT(*) AS cnt
FROM ai_historical_analysis
WHERE user_id = ?
GROUP BY hazard_category
ORDER BY cnt DESC LIMIT 5;
```

最近摘要：

```sql
SELECT hazard_category, severity, description, created_at
FROM ai_historical_analysis
WHERE user_id = ?
ORDER BY created_at DESC LIMIT 5;
```

## Redis 设计

- key：`ai:hist:{user_id}:context`
- 结构：JSON 字符串，包含 top 偏好和最近 5 条摘要。
- 写：归档后删除该 key，下次读取时从 MySQL 重建（简单且避免缓存与库不一致）。
- 读：先查 Redis，未命中查 MySQL 并回填。
- 降级：Redis 异常时直接查 MySQL，功能不中断。

## Java 改动

- `SecurityConfig`：从 `permitAll` 移除 `/api/ai/analyze`、`/api/ai/analyze/stream`，改为必须认证。
- `AiController`：`analyze`、`analyzeStream`、`chat`、`chatStream` 从 `SecurityContext` 取 `userId` 并传给 Service。
- `AiService`：方法增加 `userId`，加入发给 Python 的 multipart body。

## Python 改动

- `config.py`：新增 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`REDIS_DB`。
- `memory.py`：新增 MySQL 持久化存储与 Redis 缓存；提供 `get_historical(user_id)`、`archive_analysis(user_id, ...)`；移除 JSON 单例读写。
- `orchestrator.py`：分析流程移除历史记忆注入；归档调用传入 `user_id`。
- `server.py`：`analyze`、`analyze/stream`、`chat`、`chat/stream` 接收 `user_id` 并传递。

## 测试

- Python：用户 A 写入不影响用户 B 读取的隔离测试；更新受影响的单测。
- Java：无 token 调用分析接口返回 401/403；有 token 时 `userId` 正确透传。
- 前端：确认 AI 分析请求带 Bearer 头（云服务器检查），必要时最小修改并重新构建部署。

## 部署与验证

- 本地 Python 连接云端 MySQL（沿用 `.env` 的 `DB_HOST`），新增 `REDIS_*` 配置。
- 在云端 MySQL 执行建表 DDL。
- 安装 `redis-py`。
- 运行 Python 测试与本地冒烟验证。
- 云服务器确认前端 Bearer 头，必要时构建部署。