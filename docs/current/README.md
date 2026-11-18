# 当前系统文档索引

> 最后更新：2026-11-18

本目录描述当前代码和接口契约。出现冲突时，以代码和测试为准。

| 文档 | 内容 |
|---|---|
| [project-overview.md](./project-overview.md) | 项目定位、技术栈、总体架构、核心流程、能力与边界 |
| [architecture.md](./architecture.md) | 运行时拓扑、代码分层、接口面、安全权限、数据与缓存 |
| [agent-orchestration.md](./agent-orchestration.md) | LangGraph 编排、分类、槽位、范围与不确定性门控、检索重试 |
| [ai-assistant-sse-contract.md](./ai-assistant-sse-contract.md) | SSE 事件、中断确认、地址补全、建单状态查询与取消传播 |
| [ai-hazard-create-mq.md](./ai-hazard-create-mq.md) | Outbox、RabbitMQ、幂等消费、回执、DLX/DLQ 与状态对账 |
| [ai-hazard-create-observability.md](./ai-hazard-create-observability.md) | 建单链路指标、日志和告警建议 |
| [hazard-lifecycle.md](./hazard-lifecycle.md) | 角色、状态流转、接口权限、可见性和操作留痕 |
| [model-config.md](./model-config.md) | 文本、轻量模型与视觉模型配置 |
| [frontend-display-conventions.md](./frontend-display-conventions.md) | 状态与前端展示约定 |
| [hazard-polling-e2e.md](./hazard-polling-e2e.md) | 建单状态轮询的端到端说明 |
| [hazard-multi-category-frontend-patch.md](./hazard-multi-category-frontend-patch.md) | 多类别展示和地图底图降级 |
| [ai-multi-hazard-frontend-patch.md](./ai-multi-hazard-frontend-patch.md) | 多隐患会话的大类锁定规则 |
| [ai-hazard-create-mq-frontend-patch.md](./ai-hazard-create-mq-frontend-patch.md) | `task_accepted` 与轮询接口契约 |
