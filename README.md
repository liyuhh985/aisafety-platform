# 城市安全隐患智能分析平台

一个面向城市安全隐患上报、智能分析与工单流转的全栈项目。系统由 Java 业务后端、Python AI 服务、流式对话、检索增强生成（RAG）、异步消息建单和角色化隐患工单闭环组成。

> 本仓库用于代码展示与技术交流，已移除生产环境地址、真实凭据、评测原始样本和开发过程归档。

## 项目亮点

- **AI 隐患分析助手**：FastAPI + LangGraph 编排，支持多轮对话、范围判定、两级隐患分类、案例/法规检索、报告生成和不确定性门控。
- **SSE 流式交互**：Java 透传 Python `text/event-stream`，支持状态事件、中断确认、地址补全和地图选点。
- **可靠异步建单**：Python Outbox -> RabbitMQ -> Java 幂等消费 -> 回执更新，使用唯一索引、重试、DLX/DLQ 和状态对账保证一致性。
- **工单生命周期**：上报、派单、改派、整改、完成、验收、驳回、撤回，全过程留痕并支持角色权限控制。
- **多模态与检索**：图片内容校验、视觉模型分析、MySQL/Milvus 双后端向量检索、外部案例与法规语料。
- **工程化安全**：JWT 验签与 Redis 会话撤销、内部服务 Token、限流、文件访问鉴权、输入校验和幂等控制。
- **评测与压测**：包含模型一致性评测脚本、冻结指标、RAG 评测以及 RabbitMQ 建单链路压测记录。

## 系统架构

```text
Browser / Vue frontend
        |
        v
Java + Spring Boot  :8080
  |-- MySQL            business data
  |-- Redis            session / cache / rate limit
  |-- MinIO            image objects
  |-- RabbitMQ         async hazard creation
  `-- Python AI        /api/ai/*
        |
        v
Python + FastAPI + LangGraph  :8000
  |-- vision / language model
  |-- MySQL / Milvus vector retrieval
  |-- geocoding service
  `-- RabbitMQ worker
```

核心边界：

- 浏览器只访问 Java `/api/*`，不直接访问 Python 服务。
- Python 负责 AI 推理、检索、报告和建单请求持久化。
- Java 负责身份认证、业务权限、文件访问、工单事务和 MQ 消费。
- AI 建单使用 Outbox + RabbitMQ，不同时保留旧的同步建单路径。

## 技术栈

| 层 | 技术 |
|---|---|
| Java 后端 | Java 21, Spring Boot 3.3, Spring Security, JWT, MyBatis-Plus, MySQL, Redis, Caffeine, MinIO, RabbitMQ |
| AI 服务 | Python, FastAPI, LangGraph, Pydantic, PyMySQL, Milvus, Pika |
| AI 能力 | OpenAI-compatible 多模态模型、检索增强生成、结构化输出、Tool Calling、SSE |
| 前端 | Vue 3, Vite, Vue Router, Tailwind CSS, Fetch API |
| 部署 | Nginx + Vue 3 + Java + Python + MySQL + Redis + RabbitMQ + MinIO + Milvus |

## 目录结构

```text
safety-common/     公共常量、异常与通用工具
safety-pojo/       DTO、实体、VO
safety-service/    业务服务、Mapper、缓存、状态流转
safety-web/        Controller、Security、SSE、文件上传、MQ 消费与回执
frontend/          Vue 3 前端、API 调用、AI 对话、工单页面与地图展示
ai-module/         FastAPI、LangGraph、RAG、Embedding、视觉与 MQ worker
  core/            对话编排、分类、范围护栏、不确定性、记忆与报告
  tools/           检索、向量库、模型客户端、Java 客户端、消息队列
  db/              表结构、迁移、语料导入与运维脚本
  eval/            检索、分类、视觉与报告评测
  tests/           Python 测试
docs/              架构、接口契约、部署和评测说明
```

## 核心流程

```text
登录
 -> 上传隐患图片或输入文字
 -> AI 语义理解 + 范围判定 + 案例/法规检索 + 报告生成
 -> 用户确认建单并补全地址
 -> Python 写建单请求与 Outbox
 -> RabbitMQ 投递
 -> Java 幂等创建隐患工单并回执
 -> 管理员派单 -> 处理人整改 -> 管理员验收
```

## 快速开始

### 环境要求

- JDK 21
- Maven 3.9+
- Python 3.11+
- MySQL 8
- Redis
- RabbitMQ
- MinIO
- Milvus 可选，未启用时使用 MySQL 向量回退

### 1. 准备配置

```bash
cp safety-web/src/main/resources/application-local.yml.example \
   safety-web/src/main/resources/application-local.yml

cp ai-module/.env.example ai-module/.env
cp frontend/.env.example frontend/.env
```

请设置至少 32 字节的 `JWT_SECRET`，并确保 Java 与 Python 的 `AI_INTERNAL_TOKEN` 一致。前端地图功能还需要配置 `VITE_AMAP_KEY` 和 `VITE_AMAP_SECURITY_CODE`。真实密码、Token 和密钥不要提交到 Git。

### 2. 初始化数据库

参考 [ai-module/db/README.md](ai-module/db/README.md)，按顺序执行 `schema/` 下的迁移脚本，并按需导入 `seed/` 中的开发语料。

### 3. 构建并启动 Java 后端

```bash
mvn clean package
java -jar safety-web/target/safety-web-1.0.0-SNAPSHOT.jar
```

### 4. 启动 Python AI 服务

```bash
cd ai-module
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
python server.py
```

需要异步建单时，在另一个终端启动 worker：

```bash
cd ai-module
python hazard_create_worker.py
```

### 5. 启动 Vue 前端

```bash
cd frontend
npm ci
npm run dev
```

默认访问地址为 `http://localhost:3000`，开发环境通过 Vite 将 `/api` 代理到 Java 后端。

### 6. 运行测试与构建

```bash
mvn test
cd ai-module && python -m pytest
cd ../frontend && npm test
npm run build
```

部分集成测试依赖 MySQL、Redis、RabbitMQ、Milvus 或外部模型服务；未配置时会自动跳过或需要使用项目内说明的测试开关。

## 关键工程设计

### AI 对话与检索

- 两级隐患分类与类别锁定，减少多轮对话中的类别漂移。
- 范围护栏区分“隐患风险”与一般咨询，避免无限扩写。
- 检索结果不足时明确返回“库内暂未检索到”，不拼接无关依据。
- 并行检索、自评重试、超时取消和不确定性门控。

### SSE 与取消传播

- Java 将 Python 的流式事件转发给浏览器。
- 浏览器断开后，取消信号沿 Java 到 Python 传播，停止检索和生成。
- 结构化事件承载状态、问题、确认卡片和建单结果。

### 建单一致性

- Python 在同一事务中写请求记录和 Outbox。
- Relay 将消息投递到 RabbitMQ，Java 以 `request_id` 唯一索引幂等建单。
- 成功后通过结果队列回写 Python 请求状态。
- 失败消息进入 DLX/DLQ，并提供状态对账和卡单监控。

### 权限与文件安全

- JWT 结合服务端 Redis 会话，支持角色变更后的 Token 撤销。
- 普通用户、管理员、处理人员分层授权。
- 图片通过受控文件接口读取，不直接暴露对象存储路径。
- 临时上传文件由后台任务清理，删除失败进入重试队列。

## 文档

- [项目总览](docs/current/project-overview.md)
- [总体架构](docs/current/architecture.md)
- [Agent 编排](docs/current/agent-orchestration.md)
- [AI 助手 SSE 契约](docs/current/ai-assistant-sse-contract.md)
- [AI 建任务 MQ 契约](docs/current/ai-hazard-create-mq.md)
- [隐患生命周期](docs/current/hazard-lifecycle.md)
- [前端说明](frontend/README.md)
- [部署说明](docs/deployment/safety-platform-deployment.md)
- [评测与压测摘要](docs/evidence/README.md)

## 已知边界

- 这是持续迭代的工程项目，不是生产级商业系统。
- 前端地图功能需要自行配置高德地图 Key 和安全密钥。
- 外部模型和地图能力需要自行配置有效凭据。
- 当前未包含 CI/CD 工作流，部署采用文档化 Runbook。
- AI 输出仍需要人工复核，系统不会自动批准或跳过建单确认。
