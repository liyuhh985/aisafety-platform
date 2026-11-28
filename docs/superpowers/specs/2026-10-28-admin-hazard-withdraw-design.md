# 管理员撤回无效隐患工单设计

> 状态：approved
> 日期：2026-10-28
> 分支：codex/hazard-reassign-handler-validation

## 1. 背景

当前前端在 `status=0/1/2` 展示“驳回”按钮，但实际调用的是仅允许 `status=3` 的终审接口 `/api/hazard/{id}/review`。线上复现结果：

- `status=0` 点击驳回：409
- `status=1` 点击驳回：409
- `status=2` 点击驳回：409

管理员需要一个能力，在 AI 误建单、无关内容、重复上报或无效工单进入处置前终止它。该操作不应复用“验收驳回”，也不宜直接删除按钮。

## 2. 决策

- `status=0/1/2` 的“驳回”改为“管理员撤回”。
- 复用 `status=5`，不新增状态值。
- 管理员撤回必须填写原因。
- 操作日志使用 `ADMIN_WITHDRAW`，与上报人主动撤回的 `WITHDRAW` 区分。
- `status=3` 仍仅允许验收通过或验收驳回返工。
- `status=4` 保持“验收驳回、整改待补正”。
- 已撤回工单继续仅管理员可见。

## 3. 后端设计

### 3.1 数据字段

`tb_hazard` 新增：

```sql
withdrawn_reason VARCHAR(500) NULL COMMENT '撤回原因'
```

新增幂等迁移脚本：

```text
ai-module/db/schema/migrate_admin_withdraw_reason.py
```

`Hazard` 与 `HazardVO` 增加：

```java
private String withdrawnReason;
```

上报人主动撤回时可保持为空；管理员撤回时必填。

### 3.2 管理员撤回接口

新增：

```http
POST /api/hazard/{id}/admin-withdraw
Authorization: Bearer <admin-token>
Content-Type: application/json

{"reason":"AI 误识别，与隐患平台业务无关"}
```

权限：

```java
@PreAuthorize("hasRole('ADMIN')")
```

请求 DTO：

```java
@Data
public class AdminWithdrawDTO {
    @NotBlank(message = "撤回原因不能为空")
    @Size(max = 500, message = "撤回原因不能超过500字")
    private String reason;
}
```

### 3.3 状态更新

Mapper 条件更新：

```sql
UPDATE tb_hazard
SET status = 5,
    withdrawn_at = NOW(),
    withdrawn_by = #{adminId},
    withdrawn_reason = #{reason},
    update_time = NOW()
WHERE id = #{id}
  AND status IN (0, 1, 2)
```

规则：

- `0 -> 5`：待处理阶段撤回
- `1 -> 5`：已接单阶段终止并撤回
- `2 -> 5`：整改中阶段终止并撤回
- `status=3/4`：409，不能通过此接口撤回
- `status=5`：幂等返回当前记录
- 保留 `handler_id` 和既有流程数据用于审计
- 已撤回后，处理人员的 `start` / `complete` 因状态条件不匹配而失败

### 3.4 操作日志

写一条 `tb_hazard_action`：

```text
action_type = ADMIN_WITHDRAW
operator_id = 管理员ID
remark = 撤回原因
```

上报人主动撤回仍记录：

```text
action_type = WITHDRAW
```

### 3.5 服务与缓存

`HazardService` 新增：

```java
HazardVO adminWithdraw(Long id, Long adminId, String reason);
```

服务层完成后：

- 失效详情缓存
- 列表直接查库，刷新即可
- 返回最新 `HazardVO`

## 4. 前端设计

### 4.1 列表页

管理员操作调整：

| 状态 | 操作 |
|---|---|
| `0` | 调度派单 + 撤回工单 |
| `1` | 改派专员 + 终止并撤回 |
| `2` | 专员施工中 + 终止并撤回 |
| `3` | 核准办结 + 验收不通过，驳回返工 |
| `4` | 重新派单返工 |
| `5` | 无操作，仅管理员查看 |

撤回确认弹窗：

- 标题：撤回无效工单
- 工单描述摘要
- 必填文本域：撤回原因
- 提示：撤回后仅管理员可见，处理人员将无法继续操作
- 按钮：取消 / 确认撤回

### 4.2 详情页

详情页使用同一套状态语义，替换 `0/1/2` 的“审查驳回工单”按钮。

### 4.3 空值兜底

修复：

```vue
<span>专员 #{{ item.handlerId }} 处置中</span>
```

为：

```vue
<span v-if="item.handlerId">专员 #{{ item.handlerId }} 处置中</span>
<span v-else>尚未指派处理人员</span>
```

详情页：

```vue
<p v-if="hazard.handlerId">本工单已指定由责任专员 #{{ hazard.handlerId }} 全程推进...</p>
<p v-else>该工单尚未指派责任专员。</p>
```

### 4.4 撤回原因展示

管理员查看已撤回工单时显示：

```text
撤回原因：AI 误识别，与隐患平台业务无关
```

没有原因的上报人主动撤回记录不展示该行。

## 5. 测试

### 5.1 后端

- 管理员可撤回 `status=0`
- 管理员可撤回 `status=1`
- 管理员可撤回 `status=2`
- `status=3` 撤回返回 409
- `status=4` 撤回返回 409
- 重复撤回 `status=5` 幂等
- 写入 `withdrawn_by`、`withdrawn_at`、`withdrawn_reason`
- 写入 `ADMIN_WITHDRAW` 日志
- 原上报人 `withdraw` 行为保持不变
- 接口仅 `ADMIN` 可访问
- 原因为空时返回 400

### 5.2 前端

- 0/1/2 不再显示“驳回”，显示“撤回工单/终止并撤回”
- 3 仍显示验收通过/驳回返工
- 空 `handlerId` 不再渲染“专员 # 处置中”
- 撤回原因必填
- 撤回成功后列表刷新，工单进入管理员已撤回筛选
- 前端构建成功

## 6. 不在本轮范围

- 不新增 `status=6 已作废`
- 不新增业务工单编号
- 不改变普通用户和处理人员看到的内部 ID 规则
- 不改变 `status=3` 的验收驳回逻辑

## 7. 发布

1. 执行 `withdrawn_reason` 数据库迁移。
2. 发布后端并健康检查。
3. 构建发布前端。
4. 使用管理员账号验证 0/1/2 撤回与 3 阶段验收驳回。
5. 使用处理人员账号确认已撤回工单不可继续操作。

## 8. 文档同步

更新：

- `docs/current/hazard-lifecycle.md`
- `docs/current/architecture.md`
- `docs/current/project-overview.md`
