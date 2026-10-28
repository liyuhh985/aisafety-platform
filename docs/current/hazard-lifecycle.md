# 隐患生命周期（当前真相）

> 状态：current
> 最后核对：2026-10-28
> 事实来源：`safety-pojo/.../entity/Hazard.java`、`HazardAction.java`、`User.java`、`safety-service/.../impl/HazardServiceImpl.java`、`HazardMapper.java`、`safety-web/.../HazardController.java`。
> 命名以代码为准：状态 1 是 **「已接单」**（不是「已派单」）；状态 3 的文案取决于 `reviewed`。

## 一、角色

| role | 含义 | 权限概要 |
|------|------|----------|
| `0` | 普通用户（举报者） | 上报、查看/撤回**自己**的上报 |
| `1` | 管理员 | 派单、审查、批量审查、看全部、可统计已撤回 |
| `2` | 处理人员 | 对**派给自己**的任务整改/完成 |

`User.role`；JWT 携带 role，`JwtAuthenticationFilter` 注入 `ROLE_USER/ROLE_ADMIN/ROLE_HANDLER`。

## 二、状态与流转

| status | 含义 | 备注 |
|--------|------|------|
| `0` | 待处理 | 新建/AI 建单的初始状态 |
| `1` | 已接单 | 管理员派单或改派后（写 `handler_id`） |
| `2` | 整改中 | 处理人开始整改 |
| `3` | 待验收 / 已办结 | `reviewed=0` → 待验收；`reviewed=1` → 已办结 |
| `4` | 已驳回 | 管理员审查驳回 |
| `5` | 已撤回 | 创建人撤回（`withdrawn_at`/`withdrawn_by` 留痕） |

```
0 待处理 --(管理员派单 assign)--> 1 已接单 --(处理人 start)--> 2 整改中 --(处理人 complete)--> 3 待验收
3 待验收 --(管理员 review pass)--> 3 + reviewed=1 已办结
3 待验收 --(管理员 review reject)--> 4 已驳回
1 已接单 --(管理员改派 assign)--> 1 已接单（替换 handler_id）
4 已驳回 --(管理员重新 assign)--> 1 已接单
0 待处理 --(创建人 withdraw)--> 5 已撤回
```

流转规则（服务层强校验）：

- `assign`：仅 `status ∈ {0, 1, 4}` 可派/改派；管理员；写 `handler_id`，`reviewed=0`。
- 派单目标必须存在且角色为 `HANDLER`；`accept`、`start`、`complete` 也会在服务层复核处理人员身份。
- `start`：仅 `1 → 2`；处理人必须是 `handler_id` 本人（管理员可任意）。
- `complete`：仅 `2 → 3`；同样要求 `handler_id==自己`（管理员可任意）；`reviewed` 置 0。
- `review(pass=true)`：仅 `status=3`；`reviewed` 置 1；已办结不可重复办结。
- `review(pass=false)`：仅 `status=3`；置 `status=4`，`reviewed=1`；已办结/已驳回不可重复驳回。
- `withdraw`：仅 `status=0` 且仅创建人本人；**不审核**，立即生效；重复点幂等返回当前状态。
- 非法跳转/越权：`BusinessException`（404 不存在或无权限 / 403 非本人 handler / 409 状态不允许）。

## 三、接口与权限

| 接口 | 权限 | 作用 |
|------|------|------|
| `POST /api/hazard` | 登录 | 用户上报 |
| `GET /api/hazard` | 登录 | 业务列表（登录用户可看全量） |
| `GET /api/hazard/map` | 匿名 | 脱敏地图点位（最多 100） |
| `GET /api/hazard/{id}` | 登录 | 详情 |
| `GET /api/hazard/stats` | 匿名 | 统计 |
| `POST /api/hazard/{id}/assign` | `hasRole('ADMIN')` | 派单 / 改派 |
| `POST /api/hazard/{id}/accept` | `hasRole('HANDLER')` | 接单 |
| `POST /api/hazard/{id}/start` | `hasRole('HANDLER')` | 开始整改 |
| `POST /api/hazard/{id}/complete` | `hasRole('HANDLER')` | 完成整改 |
| `POST /api/hazard/{id}/review` | `hasRole('ADMIN')` | 验收/驳回 |
| `POST /api/hazard/batch-review` | `hasRole('ADMIN')` | 批量验收/驳回 |
| `POST /api/hazard/{id}/withdraw` | 登录 | 创建人撤回 |
| `GET /api/users/handlers` | `hasRole('ADMIN')` | 管理员派单用处理人员目录 |

> 注：`accept` 接口存在且要求 HANDLER；管理员 `assign` 与处理人员自主认领共同完成 `0/4→1`，管理员可在 `status=1` 改派。以服务层规则为准。

## 四、可见性与数据隔离（`page`）

- 业务列表和详情要求登录；产品约定登录用户可查看全量业务隐患。
- 匿名只能访问 `/api/hazard/map`，响应仅含 `id/经纬度/类别/状态/区县`，不含上报人、描述、地址、图片和报告。
- 非管理员：已撤回（status=5）不显示在业务列表。
- 管理员（role=1）：可看全部，含已撤回，可统计。
- 所有状态流转使用条件 UPDATE/CAS；更新行数为 0 时返回 409，不允许旧实体整行回写。

## 五、留痕 `HazardAction`

每次流转写一条 `tb_hazard_action`：

| action_type | 触发 |
|-------------|------|
| `ASSIGN` | 管理员派单 / 改派 |
| `START` | 处理人开始整改 |
| `COMPLETE` | 处理人完成 |
| `REVIEW_PASS` | 验收通过 |
| `REVIEW_REJECT` | 审查驳回 |
| `WITHDRAW` | 创建人撤回 |

字段：`hazard_id` / `operator_id` / `action_type` / `remark` / `create_time`。

## 六、类别字段（2026-10-14）

- `hazard_type`：**主类别**，canonical `major_code/subcategory_code`，语义未变。
- `hazard_types`：**全部类别**，英文逗号分隔、最多 3 条、第一条恒等于 `hazard_type`。
  一次上报里含多个隐患时用它；单类别工单两列相同。存量数据已回填（= `hazard_type`）。
- 迁移脚本：`ai-module/db/schema/migrate_multi_hazard.py`（幂等）。
- 前端筛选口径（2026-10-14 起）：列表页/地图页**只按一级大类**筛选，工单任一类别的 `major_code`
  命中即显示；**不做二级子类筛选**（级联「细分类型」Chips 已移除）；列表/地图/详情三处
  对多类别**同级等样并排展示**，无 `+N` 角标、无主副区分。见 `docs/current/hazard-multi-category-frontend-patch.md`。

## 七、缓存

流转成功后失效详情缓存 + 列表缓存（`invalidateDetailCache` / `invalidateListCache`）；隐患详情走 Caffeine + Redis + MySQL 多级缓存。

## 八、图片与删除

- 报告删除触发 MinIO 图片硬删；失败进 `ResourceCleanupOutbox` 重试。
- 语料（案例/法规/知识）DELETE 收紧为 ADMIN，删除后入 `VectorSyncOutbox` 做向量最终一致删除。

## 九、AI 上报与建单的关系

- AI 建单走 MQ：Python Outbox → RabbitMQ → Java 消费写 `tb_hazard`（`status=0`、`reviewed=0`）；AI 侧只发 `task_accepted`，前端轮询状态查询。
- `AiHazardDTO.district` 是 `String`；Python 侧 `geocode()` 未命中必须收敛成字符串（历史 bug：返回 `[]` 导致 Jackson 反序列化 500）。
