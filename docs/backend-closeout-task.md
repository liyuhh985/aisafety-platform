# 安全平台 V1.0 后端收尾任务

## 任务目标

完成本地 Java/Python 后端对报告闭环的最终检查，确认：

```text
认证 -> 保存报告 -> 用户隔离查询 -> 详情 -> 删除 -> SSE 分析完成
```

只修复阻断主流程的 bug，不新增业务模块、不重做 JWT、不引入 MQ、Docker、微服务拆分或新的 Agent。

## 当前环境和工作区约束

- 本地项目根目录：`E:\java\newProject`
- Java：Java 21、Spring Boot 3.3.5、Maven 多模块
- Python：`ai-module`，FastAPI/Uvicorn，默认端口 `8000`
- Java 默认端口：`8080`
- 云端通过 Nginx、FRP 访问本地 Java；Python 也是本地运行。

进入任务后先执行：

```powershell
git status --short --branch
```

以下已有修改必须保留，不能重置、覆盖或回滚：

```text
.claude/settings.local.json
.gitignore
ai-module/config.py
ai-module/core/orchestrator.py
ai-module/server.py
safety-common/src/main/java/com/safety/common/constant/RedisConstant.java
safety-service/src/main/java/com/safety/service/service/ReportService.java
safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java
safety-web/src/main/java/com/safety/web/config/SecurityConfig.java
safety-web/src/main/java/com/safety/web/controller/ReportController.java
safety-web/src/main/java/com/safety/web/service/AiService.java
safety-web/src/main/resources/application-local.yml.example
```

真实密码、JWT secret、Token、`.env` 和本地真实配置不得写入文档、Git 或聊天消息。

## 已确认的后端实现

报告 Controller：

```text
safety-web/src/main/java/com/safety/web/controller/ReportController.java
```

报告 Service：

```text
safety-service/src/main/java/com/safety/service/service/ReportService.java
```

保存 DTO：

```text
safety-pojo/src/main/java/com/safety/pojo/dto/ReportSaveDTO.java
```

当前接口：

```text
POST   /api/report
GET    /api/report?current=1&size=10
GET    /api/report/{id}
DELETE /api/report/{id}
```

报告保存 DTO 字段：

```text
imageUrl
hazardCategory
severity
description
rectification: List<String>
reportText
```

保存时由认证主体获取 `userId`，不允许前端传入或覆盖 `userId`。报告详情和删除均使用 `id + 当前 userId` 查询条件。

分页查询已经选择返回：

```text
id
imageUrl
hazardCategory
severity
description
rectification
reportText
createTime
```

`rectification` 在数据库中是 JSON 字符串，保存时由 `ReportService` 序列化。

## 认证和 SSE 重点

受保护请求统一使用：

```http
Authorization: Bearer <token>
```

重点检查：

- 未登录访问 `/api/report` 应被拒绝。
- 报告保存、列表、详情和删除不能只按报告 ID 操作。
- 用户 A 不能读取或删除用户 B 的报告。
- SSE 异步派发的 `ASYNC` / `ERROR` 请求不能在响应已提交后被 Security 再次误判为 `403`。
- AI 分析异常时 SSE 应结束并留下可定位的服务日志，不能无限挂起。

AI Controller：

```text
safety-web/src/main/java/com/safety/web/controller/AiController.java
```

主要接口：

```text
GET  /api/ai/health
POST /api/ai/analyze/stream
POST /api/ai/analyze
```

当前流式事件至少应能收到：

```text
vision
retrieval
report
done
```

Java `/api/ai/health` 会检查 AI 服务就绪状态；Python 内部健康接口也是 `/api/ai/health`，不要把敏感配置或外部模型响应写入日志。

## 最小回归测试

优先使用现有开发服务和真实测试账号；不要为了本次收尾完整打包或引入复杂测试框架。

### 报告权限

- [ ] 未登录访问 `GET /api/report` 被拒绝。
- [ ] 登录用户可以 `POST /api/report` 保存报告。
- [ ] 登录用户可以查询自己的报告列表。
- [ ] 登录用户可以查询自己的报告详情。
- [ ] 登录用户可以删除自己的报告。
- [ ] 用户 A 不能查询用户 B 的详情。
- [ ] 用户 A 不能删除用户 B 的报告。
- [ ] 删除不存在或不属于当前用户的报告不会误删其他数据。

### 图片和 AI

- [ ] 非图片上传被拒绝。
- [ ] 超过大小限制的图片被拒绝。
- [ ] 合法图片能够完成 Java -> Python -> 外部模型链路。
- [ ] SSE 能收到 `done`。
- [ ] Python 不可用时 Java/前端能够得到明确错误，不出现无限等待。
- [ ] Java `/api/ai/health` 正常。
- [ ] Python `/api/ai/health` 正常。

### 数据完整性

- [ ] 保存后的报告确实写入 MySQL。
- [ ] 列表包含 `reportText` 和 `rectification`。
- [ ] 详情包含完整报告正文和整改建议。
- [ ] 刷新后报告仍存在。
- [ ] 本次验证没有破坏既有 Redis、缓存、MinIO 和图片上传链路。

## 推荐执行顺序

1. 检查 Git 工作区和当前服务状态。
2. 阅读 `ReportController`、`ReportSaveDTO`、`ReportService`、`SecurityConfig` 和 `AiService` 的现状。
3. 先做只读接口和健康检查，记录实际状态码与响应字段。
4. 再做报告保存、列表、详情、删除的用户隔离验证。
5. 最后做一次完整图片 SSE 验证；分析耗时约一分钟属于已知限制，不以速度优化为目标。
6. 只有发现阻断主流程的问题才修改源码；修改后优先重启开发服务验证，不默认执行完整 Maven 打包。
7. 不改变现有认证方案、不回滚已有用户修改、不提交敏感配置。

## 交付内容

任务结束时报告：

1. 实际验证过的接口、请求条件和 HTTP 状态。
2. 报告保存、历史查询和用户隔离是否通过。
3. 是否修改源码，修改了哪些文件及原因。
4. Java/Python 服务重启情况和 health 结果。
5. 未通过的项目、复现方式和是否需要前端任务配合。
6. 验证完成后停止继续开发新功能，保留已知限制。

