# 文档入口

> 最后更新：2026-11-18

本目录保留适合公开阅读的架构、接口、部署和评测资料。历史计划、个人资料、评测原始样本与运行产物存放在私有存档仓库中。

## 当前系统文档

- [项目总览](./current/project-overview.md)
- [总体架构](./current/architecture.md)
- [Agent 编排](./current/agent-orchestration.md)
- [AI 助手 SSE 契约](./current/ai-assistant-sse-contract.md)
- [AI 建任务 MQ 契约](./current/ai-hazard-create-mq.md)
- [MQ 可观测性](./current/ai-hazard-create-observability.md)
- [隐患生命周期](./current/hazard-lifecycle.md)
- [模型配置](./current/model-config.md)
- [前端展示约定](./current/frontend-display-conventions.md)
- [隐患轮询端到端说明](./current/hazard-polling-e2e.md)

## 前端联调契约

- [工单多类别展示与地图底图](./current/hazard-multi-category-frontend-patch.md)
- [助手多隐患会话类别锁定](./current/ai-multi-hazard-frontend-patch.md)
- [建单 MQ 状态轮询](./current/ai-hazard-create-mq-frontend-patch.md)

## 部署与运维

- [部署主入口](./deployment/safety-platform-deployment.md)
- [Milvus 远程运维](./milvus-remote-runbook.md)

## 评测与压测

- [评测与压测摘要](./evidence/README.md)

> 文档中的服务器地址均已脱敏为示例地址。实际环境参数应通过环境变量或私有配置注入。


