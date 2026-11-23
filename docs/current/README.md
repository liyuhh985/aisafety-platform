# 当前真相层索引

> 状态：current
> 最后核对：2026-11-23

**最高规则：当前代码 > current 文档 > 历史设计/计划。**

本目录是唯一可以「照着实现」的文档层。`docs/archive/` 只用于追溯为什么这样做；`docs/evidence/` 只放实验/压测/复盘证据。

| 文档 | 内容 |
|------|------|
| [project-overview.md](./project-overview.md) | 项目定位、技术栈、总体架构、核心闭环、能力/边界、下一步 |
| [architecture.md](./architecture.md) | 运行时拓扑、代码分层、HTTP 接口面、安全权限、数据缓存、横切、构建部署 |
| [ai-assistant-sse-contract.md](./ai-assistant-sse-contract.md) | 助手主链路、SSE 事件（含 task_accepted）、interrupt/地址/地图选点、建单状态查询、兼容接口、断连取消 |
| [ai-hazard-create-observability.md](./ai-hazard-create-observability.md) | MQ / Outbox 指标、日志指标、告警建议 |
| [ai-hazard-create-mq.md](./ai-hazard-create-mq.md) | AI 建任务 MQ 契约：Python Outbox → RabbitMQ → Java 幂等消费 → 回执 → request 状态、拓扑/表/开关/前端契约、已知边界 |
| [hazard-lifecycle.md](./hazard-lifecycle.md) | 角色、状态流转、接口权限、可见性、HazardAction 留痕、多类别字段与前端筛选口径 |
| [agent-orchestration.md](./agent-orchestration.md) | LangGraph 20 节点、状态通道、两级分类、槽位 A/B/C、证据链灰度、Skill 路由、范围/不确定性、检索重试、建单闸门 |

## 前端补丁（含本目录文档与仓库内 patch）

| 文档 | 内容 |
|------|------|
| [hazard-multi-category-frontend-patch.md](./hazard-multi-category-frontend-patch.md) | 工单多类别同级展示、仅一级大类筛选、高德底图（矢量优先 + 栅格自动兜底）、图标精修 |
| [ai-multi-hazard-frontend-patch.md](./ai-multi-hazard-frontend-patch.md) | 助手多隐患会话：大类多选（≤3）、锁定后硬上锁、改报走新会话 |
| [ai-hazard-create-mq-frontend-patch.md](./ai-hazard-create-mq-frontend-patch.md) | 建单 MQ：`task_accepted` + 状态轮询、`task_created` 清理 |
| [HomeView 大类多选 patch](../superpowers/patches/2026-11-22-homeview-major-multiselect.patch) | 最多选择 3 个大类、逗号串传参、锁定后只读；部署时必须实际应用 |

## 部署（保留在 `docs/deployment/`）

- 主入口：`docs/deployment/safety-platform-deployment.md`（含 RabbitMQ、Python MQ worker 的启停与回滚）
- AI 部署附录：`docs/deployment/AI_DEPLOYMENT_INDEX.md`
- Milvus 运维附录：`docs/milvus-remote-runbook.md`
- 另一项目：`docs/deployment/yydp-deployment.md`

## 文档身份约定

```markdown
> 状态：current | implemented | superseded | historical | evidence
> 最后核对：2026-10-11
> 替代文档：xxx（superseded 时必填）
```

- 新建/更新的现行文档用 `current`。
- 归档的已落地设计用 `implemented`；纯历史用 `historical`；被取代用 `superseded`。
- 实验证据用 `evidence`。
