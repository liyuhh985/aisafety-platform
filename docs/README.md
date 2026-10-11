# 文档入口

> 状态：current
> 最后核对：2026-10-09

**读文档先看这里。最高规则：当前代码 > current 文档 > 历史设计/计划。**

## 当前真相层（唯一可照着实现的文档）

- [current/README.md](./current/README.md) — 索引
- [current/project-overview.md](./current/project-overview.md) — 项目总览
- [current/architecture.md](./current/architecture.md) — 总体架构
- [current/ai-assistant-sse-contract.md](./current/ai-assistant-sse-contract.md) — AI 助手 SSE 契约
- [current/hazard-lifecycle.md](./current/hazard-lifecycle.md) — 隐患生命周期
- [current/agent-orchestration.md](./current/agent-orchestration.md) — Agent 编排

## 部署

- [deployment/safety-platform-deployment.md](./deployment/safety-platform-deployment.md) — 主入口
- [deployment/AI_DEPLOYMENT_INDEX.md](./deployment/AI_DEPLOYMENT_INDEX.md) — AI 部署附录
- [milvus-remote-runbook.md](./milvus-remote-runbook.md) — Milvus 运维附录
- [deployment/yydp-deployment.md](./deployment/yydp-deployment.md) — 另一项目 yydp

## 历史与证据（只追溯，不作为当前方案）

- `archive/plans/`、`archive/specs/`、`archive/tasks/`、`archive/misc/` — 历史文档（顶部都有状态头）
- `evidence/` — 实验、压测、复盘、面试素材

## 约定

- 现行文档头：`> 状态：current` / `> 最后核对：YYYY-MM-DD`。
- 归档文档头：`implemented` / `historical` / `superseded`（含替代文档指向）。
- 证据文档头：`evidence`。
- 旧文档与代码冲突时，一律以代码为准。
