> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/project-overview.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 城市安全隐患分析平台：项目进度、能力评估与交接计划

> 文档用途：交接给 Codex，作为当前项目状态、收尾范围和后续学习计划的唯一参考。
>
> 更新时间：2026-07-27
>
> 当前阶段：V1.0 功能冻结前的最后验证，不再新增业务功能。

---

## 1. 当前结论

这个项目已经达到可以写入实习简历、用于面试讲解的水平，但还没有达到商业生产系统的完整工程标准。

综合完成度约为 **80%**。主要业务链路已经打通，当前剩余工作不是继续增加功能，而是：

1. 验证报告保存和历史查询的完整闭环；
2. 修复或确认云端前端部署版本；
3. 做最小必要的回归测试；
4. 整理项目文档和面试表达；
5. 冻结项目，进入 Java 后端、算法和面试知识的吸收阶段。

项目可以从“持续开发项目”转为“V1.0 学习项目 / 简历项目”。不建议继续无限堆叠 MQ、微服务拆分、复杂任务队列或新的业务模块。

---

## 2. 项目定位

### 2.1 一句话介绍

基于 Spring Boot、Python FastAPI 和多模态 AI 的城市安全隐患分析平台，实现隐患图片上传、视觉识别、相关案例与法规检索、流式分析报告生成、报告保存和历史查询。

### 2.2 核心业务闭环

```text
用户注册/登录
    ↓
上传隐患图片
    ↓
Java 接收请求并转发给 Python AI 服务
    ↓
Python 完成图片校验、缩放、Vision 识别、案例/法规检索、报告生成
    ↓
通过 SSE 将阶段状态、视觉结果和报告文本流式返回前端
    ↓
用户保存报告
    ↓
图片上传到 MinIO，报告写入 MySQL
    ↓
历史列表、详情和删除
```

### 2.3 当前真实部署架构

```text
云端浏览器
    ↓
云端 Nginx :8081
    ├── 静态文件 → /var/www/safety-platform
    └── /api/* → 127.0.0.1:8080
                    ↓ FRP 转发
                本地 Spring Boot :8080
                    ├── MySQL
                    ├── Redis
                    ├── MinIO
                    └── Python FastAPI :8000
                            ↓
                       外部多模态模型服务
```

重要事实：Python 服务也是本地运行的，不是云端独立部署。云端前端通过 Nginx 和 FRP 访问本地 Java，Java 再访问本地 Python。

---

## 3. 当前技术栈

### 3.1 后端 Java

- Java 21
- Spring Boot 3.3.5
- Maven 多模块项目
- Spring MVC
- Spring Security 6.x
- JWT Bearer Token
- MyBatis-Plus
- MySQL
- Redis
- Caffeine / Redis / MySQL 多级缓存相关实现
- MinIO 文件对象存储
- `RestTemplate` 调用 Python AI 服务
- `SseEmitter` 对外提供 SSE
- BCrypt 密码加密

主要模块：

```text
safety-common   公共常量、通用能力
safety-pojo     DTO、实体对象
safety-service  业务服务、Mapper、数据库逻辑
safety-web      Controller、安全配置、AI 客户端、文件上传
```

### 3.2 Python AI 服务

- Python
- FastAPI
- Uvicorn
- Pillow
- OpenAI-compatible 多模态模型接口
- Agent 编排结构
- Vision Agent
- Router Agent
- Retrieval Agent
- Report Agent
- 会话记忆
- SSE 流式输出

主要目录：

```text
ai-module/server.py
ai-module/config.py
ai-module/core/orchestrator.py
ai-module/core/agent.py
ai-module/agents/
ai-module/mimo_client.py
```

### 3.3 前端与部署

- Vue 3
- Vite
- Nginx
- 云端静态文件部署
- FRP TCP 转发
- 浏览器 `fetch`、`FormData`、SSE 流读取

注意：当前本地 Java 仓库中没有云端 Vue 源码。云端前端源码位置为：

```text
/home/ubuntu/aisafety-platform-frontend
```

云端静态部署目录为：

```text
/var/www/safety-platform
```

### 3.4 数据和基础设施

- MySQL：用户、隐患、报告、案例、知识、法规等持久化数据
- Redis：验证码、Token、限流、缓存等
- MinIO：分析报告关联图片的对象存储
- Caffeine：部分本地热点缓存
- Nginx：静态资源、API 代理、SSE 代理配置

真实密码、密钥、`.env`、`application-local.yml` 等敏感内容不得写入本文档、Git 或聊天消息。

---

## 4. 已完成的主要工作

### 4.1 用户认证和接口权限

- 登录流程已经具备。
- 使用 JWT 进行认证。
- Spring Security 对受保护接口进行拦截。
- 报告保存、列表、详情和删除按当前登录用户隔离。
- 报告 Controller 当前通过认证主体获取 `userId`。
- AI 分析接口根据当前联调需要已配置访问权限。
- SSE 异步派发相关的 `ASYNC` / `ERROR` dispatch 问题已经处理，避免响应已提交后再次被 Security 误判为 403。

关键文件：

```text
safety-web/src/main/java/com/safety/web/config/SecurityConfig.java
safety-web/src/main/java/com/safety/web/controller/ReportController.java
```

### 4.2 图片分析链路

- Java 接收前端 multipart 请求。
- Java 将图片和文本转发给 Python FastAPI。
- Python 在入口处限制上传大小。
- Python 校验实际图片内容和支持格式，不信任原始文件名。
- Python 将图片转为 RGB，并缩放到适合模型分析的尺寸。
- Python 使用临时文件，分析完成、异常或连接结束后清理。
- Vision Agent 输出隐患类别、严重程度、描述、位置提示和整改建议。
- Vision 已经能返回正确结果，例如：

```json
{
  "has_hazard": true,
  "hazard_category": "建筑施工",
  "severity": "高",
  "description": "隐患描述",
  "location_hint": "位置提示",
  "rectification": ["整改建议"]
}
```

- 当 Vision 已经返回有效 `hazard_category` 时，Orchestrator 会优先使用该类别进行检索，避免不必要的 Router 调用。

关键文件：

```text
ai-module/server.py
ai-module/config.py
ai-module/core/orchestrator.py
safety-web/src/main/java/com/safety/web/service/AiService.java
```

### 4.3 SSE 流式分析

当前分析接口：

```text
POST /api/ai/analyze/stream
```

主要事件：

```text
status   阶段状态
vision   视觉识别 JSON
retrieval 检索结果或阶段信息
report   报告文本片段
 done    分析完成
```

已实际验证本地 Java → Python → 外部模型的完整 SSE 流程可以成功返回。真实分析耗时约 66～74 秒，主要原因是 Vision、检索和 Report 依次调用外部模型/数据源，不是服务完全失效。

Java 端已经从裸线程改为固定线程池，连接和读取超时也已经设置。

### 4.4 缓存和地图相关能力

- 已有 Redis 缓存和失效相关实现。
- 隐患详情存在缓存思路和实测记录。
- 已经做过 Redis 与内存存储的性能对比。
- 已经记录 Caffeine + Redis + MySQL 多级缓存结构。
- 已经做过验证码限流和详情缓存验证。

详细测试记录：

```text
docs/redis-benchmark.md
```

当前不再新增缓存功能。收尾时只需要确认已有功能没有被本次报告链路修改破坏。

### 4.5 云端问题排查能力

项目过程中实际处理过：

- 前端调用 AI 分析接口时缺少 JWT，导致 403；
- SSE 响应已经提交后 Spring Security 再次处理异步派发；
- 云端 Nginx 监听端口与旧站点冲突；
- 云端前端通过 Nginx、FRP、本地 Java、本地 Python 联调；
- 前端字段结构和后端平铺字段不一致；
- 图片上传请求和报告保存请求使用不同 Authorization 格式；
- 通过浏览器 Network 对比请求头定位问题。

这些真实排查过程本身就是项目的重要工程成果，后续面试可以重点讲。

---

## 5. 当前完成度评估

| 模块 | 当前估计 | 说明 |
|---|---:|---|
| 用户登录与 JWT | 85% | 主流程和权限拦截已有，需继续做最小回归验证 |
| Spring Security | 80% | 认证和报告用户隔离已有，SSE 异步 dispatch 已处理 |
| 图片上传与存储 | 85% | 上传、校验、压缩、MinIO 链路已有 |
| AI 图片分析 | 90% | Vision、检索、报告生成和 Python 服务链路已打通 |
| SSE 流式返回 | 80% | 可运行，仍需确认异常和断开场景 |
| 报告保存 | 80% | 前端 403 根因已定位并已部署修复，需重新实测 200 |
| 历史列表 | 75% | 前端映射和后端字段已处理，需确认云端实际数据 |
| 历史详情 | 75% | 后端详情接口存在，需确认报告文本和整改字段展示 |
| Redis 与缓存 | 75% | 已有实现和测试记录，不再扩展 |
| 云端部署 | 75% | 已能联调，部署流程仍较手工 |
| 自动化测试 | 35% | 目前主要依赖手动验证，是项目主要短板 |
| 项目文档与面试表达 | 50% | 本文档开始补齐，后续需要形成简历和口述材料 |
| **整体** | **约 80%** | 可以冻结为实习项目 V1.0 |

这个评价不是说项目可以直接用于高并发生产环境，而是说：它已经足够证明具备真实后端和 AI 应用开发经历，下一步收益最高的工作是巩固和表达，而不是继续加模块。

---

## 6. 当前已知问题和边界

### 6.1 报告保存必须最后验证

最近一次线上问题：

```text
POST /api/upload/image → 200
POST /api/report       → 403
```

原因是云端前端曾经发送：

```http
Authorization: *** <token>
```

而正确格式必须是：

```http
Authorization: Bearer <token>
```

云端 `AnalysisView.vue` 已经修复并重新构建部署，部署后的 bundle 已验证包含 Bearer 认证头，但仍必须在浏览器强制刷新后实际点击保存，确认 `/api/report` 返回 200。

### 6.2 历史分页字段

本地 Java `ReportService.page()` 已补充返回：

- `reportText`
- `rectification`

此前分页只选择了基础字段，可能导致历史页面没有完整报告内容。

本地修改文件：

```text
safety-service/src/main/java/com/safety/service/service/ReportService.java
```

如果本地 Java 服务当前没有加载最新源码，需要重启开发中的 Spring Boot 服务。按当前学习项目工作流，不需要为了这次修改执行完整 Maven 打包。

### 6.3 云端前端缓存

如果浏览器仍使用旧 bundle：

1. 退出并重新登录；
2. 执行 `Ctrl + F5`；
3. 手机浏览器关闭页面后重新打开；
4. 必要时清理站点缓存。

### 6.4 AI 分析耗时

当前分析约一分钟属于已知限制。项目阶段目标是不再继续优化速度。面试中可以说明：

- 使用 SSE 改善长耗时请求的用户体验；
- 图片入口先压缩，减少传输和模型输入体积；
- 已避免在 Vision 有效分类时额外调用 Router；
- 更大范围的并行化、任务队列和断点恢复属于后续生产化方向，不在本项目收尾范围内。

### 6.5 测试和部署自动化不足

当前没有完善的 CI/CD 和完整自动化测试。不要为了项目收尾临时引入复杂工具。把它作为已知限制记录，并在后续学习中补充测试思想和部署基础。

---

## 7. 今天必须完成的收尾任务

目标：今天结束后把项目定义为 **V1.0 功能闭环完成、进入维护状态**。

### 任务 A：验证报告保存

使用真实登录账号在云端前端执行：

1. 打开分析页面；
2. 上传一张隐患图片；
3. 等待 Vision 和报告生成完成；
4. 点击保存到历史；
5. 在浏览器 Network 确认：
   - `/api/upload/image` 返回 200；
   - `/api/report` 返回 200；
   - `/api/report` 请求头为 `Bearer <token>`；
   - 请求 body 包含 `hazardCategory`、`severity`、`description`、`rectification`、`reportText`。

如果 `/api/report` 仍返回 403：

- 先确认浏览器加载的 bundle 是否是最新版本；
- 确认 localStorage 中 `token` 没有过期；
- 退出并重新登录；
- 不要先改 Java 权限配置，因为图片上传已经证明同一个 Token 可以通过认证。

### 任务 B：验证历史列表和详情

保存成功后：

1. 打开历史页面；
2. 确认当前报告显示危险类别、严重程度和描述；
3. 打开详情；
4. 确认报告正文和整改建议存在；
5. 刷新页面后数据仍存在；
6. 删除报告后列表更新；
7. 重新登录后仍只能看到当前用户自己的记录。

### 任务 C：最小回归测试

只需要执行以下清单，不追求测试数量：

- 未登录访问 `/api/report`：应被拒绝；
- 登录用户保存报告：应成功；
- 登录用户查询自己的报告：应成功；
- 用户不能查看其他用户的报告详情；
- 用户不能删除其他用户的报告；
- 非图片上传被拒绝；
- 超过大小限制的图片被拒绝；
- AI 分析完成后能收到 `done`；
- AI 服务不可用时前端有明确错误提示；
- Java 和 Python health 接口正常。

### 任务 D：冻结项目

收尾验证通过后：

- 不新增业务功能；
- 不重新设计 JWT；
- 不继续增加 AI Agent；
- 不引入 MQ、Docker、微服务拆分等新内容；
- 不为追求“生产级”而无限重构；
- 保留已知限制，并准备面试时如实说明；
- 只允许修复阻断主流程的 bug。

---

## 8. 交给 Codex 的执行边界

### 8.1 Codex 首先做什么

1. 阅读本文档；
2. 检查 Git 工作区，不覆盖已有用户修改；
3. 只围绕“报告保存—历史列表—历史详情”做最终验证；
4. 需要修改时优先修改现有源码，不创建重复实现；
5. 修改 Java 后直接重启开发服务验证，不默认完整打包；
6. 云端前端若要修改，先确认源码和部署 bundle 的对应关系；
7. 验证通过后不要继续开发新功能。

### 8.2 必须保护的已有修改

当前工作区已有修改，不能擅自丢弃、重置或覆盖：

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

不要执行以下操作，除非用户明确要求：

- `git reset --hard`
- 删除文件、分支或数据库数据；
- 强制推送；
- 提交真实配置、密码、Token 或 `.env`；
- 重新引入必须通过环境变量才能启动的 JWT_SECRET 方案；
- 大规模重构或更换技术栈。

### 8.3 当前用户工作流偏好

这是学习项目。用户明确偏好：

- 直接修改 Java/Python 源代码；
- 重启开发中的服务；
- 不要每次修改后都完整打包，因为会浪费时间和 token；
- 只有发布、部署或需要验证构建产物时才打包。

---

## 9. 面试能力评估

### 9.1 当前可以证明的能力

目前项目可以证明以下能力：

- 能够使用 Spring Boot 构建多模块后端；
- 能够实现 JWT 和 Spring Security 基础权限控制；
- 能够完成 MySQL、Redis、MinIO 的综合接入；
- 能够使用 Java 调用 Python FastAPI 服务；
- 能够处理 multipart 图片上传和文件生命周期；
- 能够使用 SSE 处理长耗时 AI 分析；
- 能够处理 Nginx、FRP、云端前端和本地服务联调；
- 能够使用浏览器 Network、服务日志和接口响应定位问题；
- 能够解释缓存命中、认证失败、异步 dispatch、代理转发等问题。

### 9.2 当前能力等级的客观定位

比较准确的定位是：

> 具备独立完成中小型 Java 后端 / AI 应用项目的能力，正在从“功能实现”阶段进入“工程理解、稳定性和面试表达”阶段。

还不能声称：

- 熟练掌握高并发生产系统；
- 熟练掌握分布式事务、消息队列和微服务治理；
- 具备大型系统架构经验；
- 具备完善的自动化测试和 CI/CD 能力。

这不是缺点，而是实习阶段的正常边界。后续通过复习和面试准备补齐即可。

### 9.3 推荐的项目面试表达

#### 为什么使用 SSE？

AI 分析包含视觉识别、检索和报告生成，响应时间较长。SSE 可以先返回阶段状态和视觉结果，再逐步返回报告文本，避免用户长时间面对无反馈的同步请求。

#### 如何实现报告权限隔离？

登录后通过 JWT 识别当前用户，在保存时写入 `userId`，列表、详情和删除操作都将当前用户作为查询条件，不能只根据报告 ID 查询。

#### 遇到过什么真实问题？

图片上传请求使用了正确的 Bearer Token，但报告保存请求使用了错误的 Authorization 格式，导致上传成功、保存返回 403。通过浏览器 Network 对比两个请求的请求头定位问题，修复云端前端并重新构建部署。

#### 为什么图片要在 Python 入口压缩？

入口压缩可以尽早减少后续模型调用的输入体积，同时统一格式、限制像素和清理临时文件，避免把非法或过大的文件传递到模型调用阶段。

#### 为什么没有继续做任务队列？

当前项目目标是学习和完成一个可运行闭环。SSE 已经满足当前交互需求，任务队列、持久化任务状态和分布式取消属于生产化增强，不纳入 V1.0，以避免为了堆技术而扩大项目范围。

---

## 10. 明天开始的学习计划

项目收尾后，切换为“向内吸收”，不再以开发新功能为主。

### 10.1 每天 4 小时的建议分配

#### 算法：1 小时

第一轮重点：

- 数组、字符串、哈希；
- 双指针、滑动窗口；
- 链表；
- 栈和队列；
- 二分查找；
- 二叉树；
- DFS / BFS；
- 回溯；
- 动态规划基础；
- 常见排序和复杂度分析。

目标不是盲目刷题，而是能够独立写出常见题、解释思路、分析时间和空间复杂度。

#### Java 和后端基础：1.5 小时

建议顺序：

1. Java 集合和泛型；
2. Java 异常、IO 和反射基础；
3. Java 并发、线程池、锁、CAS；
4. JVM 内存、垃圾回收和类加载；
5. Spring IOC、AOP、事务；
6. Spring MVC 请求链路；
7. Spring Security 和 JWT；
8. MySQL 索引、事务、锁和 SQL 优化；
9. Redis 数据结构、缓存一致性、过期和穿透；
10. 计算机网络、HTTP、TCP、HTTPS；
11. 常见设计模式和基础系统设计。

每学一个主题，都要回到本项目寻找对应位置并回答：

- 这里为什么这样设计？
- 如果请求失败会怎样？
- 如果并发增加会怎样？
- 目前实现有哪些限制？

#### 项目复盘和表达：1 小时

不要重新开发项目。每天只复盘一个主题：

- 认证链路；
- 图片上传链路；
- Java 调 Python；
- SSE；
- Agent 编排；
- Redis 缓存；
- MySQL 报告保存；
- MinIO；
- Nginx 和 FRP；
- 一次真实故障排查。

目标：

- 3 分钟讲清项目；
- 10 分钟讲清架构；
- 能回答关键技术追问；
- 能说清当前实现和生产化方案的差异。

#### 投递和面试反馈：0.5 小时

不要等到完全准备好才投递：

- 先完成一版简历；
- 针对 Java 后端、AI 应用、Agent 开发岗位投递；
- 记录岗位要求和面试问题；
- 每周根据真实反馈调整学习重点。

如果当天有面试，优先复盘面试，不必机械保持固定时间分配。

### 10.2 阶段目标

#### 第 1～2 周

- 完成安全平台闭环验证；
- 冻结 V1.0；
- 完成简历第一版；
- 能做 3 分钟项目介绍；
- 开始少量投递。

#### 第 3～6 周

- 完成 Java、Spring、MySQL、Redis 第一轮系统复习；
- 完成算法常见题型第一轮；
- 每周至少一次模拟面试；
- 根据真实面试问题补短板。

#### 之后到寒假

- 保持算法和八股复习；
- 持续投递并优化简历；
- 针对目标方向分别准备 Java 后端或 Agent/AI 应用岗位；
- 从“学更多”转向“写得出、答得出、讲得清”。

### 10.3 现实目标

每天稳定投入 4 小时，坚持到寒假，配合项目整理和持续投递，获得实习面试是现实目标，拿到普通 Java 后端或 AI 应用实习也具有较大可能。

不能把结果理解为“学习小时数达到某个数字就必然拿到 offer”。影响结果的因素还包括：

- 当前 Java 和算法基础；
- 简历质量；
- 投递数量和岗位匹配度；
- 城市和招聘周期；
- 面试发挥；
- 真实面试反馈后的调整速度。

正确的判断标准不是每天是否焦虑，而是：

- 能否写出常见算法；
- 能否讲清项目每个关键设计；
- 能否回答 Java、MySQL、Redis 基础问题；
- 是否逐渐获得更多笔试和面试；
- 每次面试后是否明确知道下一个短板。

---

## 11. 两个项目的求职定位

### 城市安全隐患分析平台

更适合：

- Java 后端实习；
- 全栈开发实习；
- AI 应用开发实习；
- Agent 应用开发实习。

优势：后端技术栈完整，包含真实联调、认证、文件、缓存、流式接口和部署问题。

### yydp 项目

适合作为第二个项目，重点展示 Agent / AI 应用方向的能力。交接给 Codex 时，应补充该项目自身的准确技术栈、架构、核心功能和个人贡献，不要让它只停留在“调用了模型 API”的描述。

两个项目一起放在简历中时，重点不是展示功能数量，而是证明：

- 能把 AI 能力接入真实业务；
- 能设计后端接口和数据流；
- 能处理认证、异常、存储和部署；
- 能定位真实问题并完成闭环。

---

## 12. 最终交接标准

当以下条件全部满足时，可以认为安全平台项目今天正式结束：

- [ ] 图片分析能够完成；
- [ ] Vision 结果正常显示；
- [ ] `/api/upload/image` 返回 200；
- [ ] `/api/report` 使用 Bearer Token 并返回 200；
- [ ] 报告确实写入数据库；
- [ ] 历史列表显示当前报告；
- [ ] 历史详情显示正文和整改建议；
- [ ] 刷新页面后报告仍存在；
- [ ] 删除报告成功；
- [ ] 用户之间的报告数据隔离；
- [ ] 未登录请求受保护接口被拒绝；
- [ ] 非法图片和超大图片被拒绝；
- [ ] Java/Python health 正常；
- [ ] 不再新增业务功能；
- [ ] 已知限制已记录；
- [ ] 简历和面试讲解材料开始整理。

完成后，项目状态写作：

> 城市安全隐患分析平台 V1.0：核心业务闭环完成，具备实习项目展示条件，进入维护和面试准备阶段。后续以 Java 后端基础、算法、项目复盘和持续投递为主，不再继续扩展业务功能。
