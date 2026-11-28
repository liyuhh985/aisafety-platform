# 安全与并发加固实施计划（2026-10-25）

## 1. 目标与产品边界

本轮目标不是把项目改成企业级安全平台，而是把面试会被追问、且会破坏业务不变量的边界补上，并用测试留证。

已确认的产品边界：

- 首页、流转图和地图点位可匿名查看；
- 地图公开数据只返回脱敏字段：id、经纬度、隐患类别、状态、区县；不返回上报人、完整地址、描述、图片、报告；
- 隐患业务列表、隐患详情、AI 分析必须登录；
- 普通登录用户是否可查看全部业务隐患，按现行业务保留；不再限制为只看本人数据；
- 当前部署为单机：Nginx 只暴露前端和 Java API，Python 绑定 127.0.0.1:8000，Java -> Python 使用内部 Token；
- 图片最终存储为 MinIO 对象 + MySQL 元数据；前端预览使用本地 blob URL，保存时使用服务端生成的 fileId/objectKey，不接受任意 imageUrl。

## 2. 非目标

- 不引入 OAuth2/OIDC、mTLS、多租户、Kubernetes、分库分表；
- 不为了演示继续追 200 并发；
- 不在测试中发送真实邮件；
- 不重写现有 LangGraph 主链路。

## 3. 任务拆分

### Task A：JWT、登录和验证码加固

**文件范围**

- safety-common/src/main/java/com/safety/common/util/JwtUtil.java
- safety-service/src/main/java/com/safety/service/service/impl/UserServiceImpl.java
- safety-service/src/main/java/com/safety/service/service/MailService.java
- safety-web/src/main/java/com/safety/web/controller/AuthController.java
- safety-web/src/main/java/com/safety/web/config/JwtAuthenticationFilter.java
- safety-web/src/main/resources/application.yml
- safety-web/src/main/resources/application-local.yml.example
- 对应单元测试

**要求**

- 删除硬编码 JWT 密钥，改为环境变量/配置项；密钥为空、占位符或长度不足时失败；
- Token 增加 jti，Redis 保存有效 Token 会话；过滤器要求 JWT 验签通过且会话仍存在；
- 增加 logout，删除当前 Token 会话；
- 登录失败统一返回“邮箱或密码错误”；用户不存在时也执行一次 BCrypt 比较，降低枚举/时序差异；
- 验证码改用 SecureRandom；
- 验证码校验改为原子消费，增加错误次数上限；不发送真实邮件，测试使用 mock；
- 登录、发送验证码补 IP + 邮箱维度限流；先使用现有 RateLimit，不实现复杂风控；
- 保持现有注册成功返回 Token 的行为；
- 所有新增逻辑必须有单元测试或 WebMvc 测试。

### Task B：隐患公开地图 + 状态流转 CAS

**文件范围**

- safety-pojo/src/main/java/com/safety/pojo/vo/HazardMapVO.java（新增）
- safety-service/src/main/java/com/safety/service/service/HazardService.java
- safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java
- safety-service/src/main/java/com/safety/service/mapper/HazardMapper.java
- safety-web/src/main/java/com/safety/web/controller/HazardController.java
- 对应单元测试
- .codex-remote-frontend-edit/MapPage.vue
- safety-web/src/main/java/com/safety/web/config/SecurityConfig.java 由 Task A 统一处理公开 matcher；Task B 只提交所需路径说明，不并行修改该文件

**要求**

- 新增公开地图接口 GET /api/hazard/map?limit<=100，只返回脱敏字段；不返回 userId/description/address/imageUrl/report；
- GET /api/hazard、GET /api/hazard/{id} 恢复登录保护；
- GET /api/hazard/stats 和 GET /api/hazard/map 保持匿名可读；
- MapPage.vue 改用 /api/hazard/map；未登录点击详情跳登录页；
- 所有状态流转改成条件更新/CAS，更新行数为 0 返回 409，不允许用旧实体整行回写；
- 覆盖 assign、start、complete、review、updateLocation；withdraw 保持现有条件更新；
- 状态更新和操作日志尽可能在同一事务内；
- 测试：成功、状态冲突、重复派单、审核并发、定位与撤回并发、Mapper SQL 参数。

### Task C：Python 内部服务 + 会话隔离

**文件范围**

- ai-module/config.py
- ai-module/server.py
- ai-module/core/memory.py
- ai-module/core/assistant_graph.py（仅必要的 session/thread key 和 image_url 透传）
- safety-web/src/main/java/com/safety/web/service/AiService.java
- safety-web/src/main/java/com/safety/web/controller/AiController.java
- 对应 Python/Java 测试

**要求**

- Python 默认绑定 127.0.0.1；通过环境变量允许容器内网监听，但不能在本轮默认暴露公网；
- 除 health 外的 AI 业务接口统一校验 X-Internal-Token；
- Java 调用 Python 的所有请求携带内部 Token；
- 会话 namespace 使用 user_id + session_id，Java history/delete/stream 必须传当前登录 userId；
- 新会话由服务端生成；不允许仅凭 session ID 读取/删除；
- 同一会话加单飞/锁，重复 turn 返回 409/429；优先使用现有 Redisson/Redis 能力；
- LangGraph thread_id 使用 userId:sessionId；
- 补 Python 单元测试：无 Token、错误 Token、跨用户 session、同 session 并发。

### Task D：图片上传、预览、保存

**文件范围**

- safety-pojo/src/main/java/com/safety/pojo/vo/FileUploadVO.java
- safety-pojo/src/main/java/com/safety/pojo/dto/ReportSaveDTO.java
- safety-pojo/src/main/java/com/safety/pojo/entity（新增文件元数据实体）
- safety-service/src/main/java/com/safety/service/service/FileUploadService.java
- safety-service/src/main/java/com/safety/service/service/ReportService.java
- safety-service/src/main/java/com/safety/service/mapper（新增 mapper）
- safety-web/src/main/java/com/safety/web/controller/UploadController.java
- safety-web/src/main/java/com/safety/web/controller/ReportController.java
- safety-web/src/main/java/com/safety/web/controller/AiController.java（与 Task C 协调，优先由一个智能体负责）
- .codex-remote-frontend-edit/AnalysisView.vue
- .codex-remote-frontend-edit/AiAssistant.vue
- 新增文件元数据迁移脚本

**要求**

- MinIO 保存文件本体，MySQL 只保存元数据，不保存 blob；
- 上传接口返回 fileId、objectKey、受控 URL；记录 userId/status(TEMP|ATTACHED)/expiresAt/size/contentType；
- 校验文件头、真实图片解码、像素和大小；保留现有 10MB 上限；
- 前端预览继续使用 URL.createObjectURL(file)；不得把 blob URL 保存到数据库；
- 保存报告/建隐患时只接受当前用户的 fileId 或服务端认可的 objectKey；
- 文件读取接口校验归属，或返回短时签名 URL；
- 取消/失败/超时进入资源清理 outbox；
- AI 分析上传文件时，Java 先落 MinIO，再将服务端 image URL 随请求传给 Python；Python 不自行决定图片所有权；
- 地图页不再拼接未转义 imageUrl。

## 4. 冒烟测试顺序

1. mvn -B test；
2. python -m pytest -q（ai-module）；
3. 真实 HTTP 10/100 冒烟：登录、验证码 mock 不在真实环境发信、地图匿名访问、详情未登录 401/403、登录后详情、建单、撤回、状态冲突；
4. 文件：上传 -> 预览 -> 分析 -> 保存 -> 刷新详情；取消上传 -> 清理任务；
5. AI：内部 Token 缺失 401、跨用户 session 404、同 session 并发 409/429；
6. MQ：50/500 回归，验证 duplicate=0、丢单=0、DLQ=0；100/1000 只做容量边界回归。

## 5. 验收标准

- 未登录无法读取隐患详情或调用 AI；匿名地图只能拿到脱敏字段；
- 旧 JWT 在密钥轮换后失效，logout 后 Token 立即失效；
- 同一 requestId 不产生重复工单；
- 并发撤回与派单不会出现“已撤回后又变成已派单”；
- A 用户不能用 B 用户的 session/file；
- 数据库不出现 blob URL；
- 50/500 压测正确性指标不退化；
- 所有新增核心逻辑有测试，测试过程不发送真实邮件。


## 6. 实施状态（2026-10-25）

- Task A：已完成。JWT 环境密钥、jti/Redis 会话、logout、登录统一错误、验证码 SecureRandom/原子消费/错误上限、登录与验证码限流均已落地。
- Task B：已完成。公开地图 /api/hazard/map、业务列表/详情登录保护、状态流转 CAS 与事务化操作日志均已落地。
- Task C：已完成。Python 默认本机监听、内部 Token、user/session 命名空间、同会话单飞锁和 LangGraph thread_id 隔离均已落地。
- Task D：第一阶段已完成。图片上传改为受控 fileId + objectKey + MinIO，MySQL 新增 tb_file_asset 元数据，前端预览与保存分离，报告保存不再接收 blob/任意 imageUrl。
- 2026-10-25 已部署云端：Java、Python、worker、前端和 `tb_file_asset` 迁移均完成；健康检查、匿名地图、匿名业务拦截、Python 内部 Token、真实 IP 限流均通过。
- 四项遗留已补齐：临时图片清理 worker、AI 助手建单 imageFileId 透传、角色变更批量撤销 Token、真实登录态图片上传/保存/读取 E2E。
- 后续只保留运行期观察和按真实需求迭代。
