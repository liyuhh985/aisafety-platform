# 隐患改派与处理人员身份校验设计

> 状态：approved
> 日期：2026-10-28
> 分支：codex/hazard-reassign-handler-validation

## 1. 背景

当前隐患流转有两个需要修正的行为：

1. 管理员页面在 `status=1`（已接单）显示“改派专员”，但 `HazardMapper.assign` 只允许 `status IN (0, 4)`，点击后会被服务层拒绝。
2. 管理员派单时只接收一个 `handlerId`，没有校验目标用户是否存在、角色是否为处理人员；`accept`、`start`、`complete` 的身份约束也主要依赖 Controller 注解，服务层缺少统一校验。

此外，管理员“已撤回”页签已存在于当前前端源码，但线上构建产物尚未包含该功能。此次变更需要重新构建并发布前端。

## 2. 目标

- 管理员可在 `status=0`、`status=1`、`status=4` 执行首次派单、改派、驳回后重新派单。
- 所有处理人员相关动作在服务层校验用户存在且 `role=2`。
- 管理员派单弹窗改为真实处理人员选择器，不再手填 UID。
- 管理员前端可见“已撤回”页签并可按 `status=5` 筛选。
- 保持现有白色卡片、蓝色主按钮、大圆角、药丸标签的视觉体系。

## 3. 非目标

- 不新增处理人员启停状态、排班、地域分组或负载均衡。
- 不改变处理人员自主认领的产品入口。
- 不新增通用用户管理页面。
- 不改变撤回后的数据保留规则；`status=5` 仍仅管理员可见。

## 4. 后端设计

### 4.1 改派状态

`HazardMapper.assign` 的条件改为：

```sql
WHERE id = #{id} AND status IN (0, 1, 4)
```

更新字段保持：

```sql
status = 1,
reviewed = 0,
handler_id = #{handlerId},
update_time = NOW()
```

含义：

- `0 -> 1`：首次派单
- `1 -> 1`：改派，替换当前责任人
- `4 -> 1`：驳回后重新派单

改派后旧处理人立即失去 `start` / `complete` 权限，因为后续流转仍要求 `handler_id = 当前用户`。

### 4.2 处理人员校验

在 `HazardServiceImpl` 中注入 `UserMapper`，提供统一校验：

```java
private User requireHandlerUser(Long userId) {
    User user = userMapper.selectByIdForUpdate(userId);
    if (user == null) {
        throw new BusinessException(404, "处理人员不存在");
    }
    if (!Objects.equals(user.getRole(), 2)) {
        throw new BusinessException(400, "目标用户不是处理人员");
    }
    return user;
}
```

使用 `selectByIdForUpdate` 与角色变更流程共用用户行锁，避免派单与降级并发时写入失效责任人。

应用位置：

- `assign(id, adminId, handlerId)`：更新工单前校验目标 `handlerId`。
- `accept(id, userId)`：复用 `assign`，因此自动校验当前用户。
- `start(id, userId, role)` / `complete(id, userId, role)`：非管理员流转前校验当前用户存在且角色为 `HANDLER`。
- 管理员特殊流转保留现有服务能力，但 Controller 仍只把 `start` / `complete` 暴露给 `ROLE_HANDLER`。

### 4.3 处理人员列表接口

新增管理员专用接口：

```http
GET /api/users/handlers
Authorization: Bearer <token>
```

权限：

```java
@PreAuthorize("hasRole('ADMIN')")
```

返回 `R<List<UserVO>>`，仅包含 `role=2` 的用户，按用户 ID 升序。前端使用 `id`、`nickname`、`email`、`avatar` 字段。

服务层新增：

```java
List<UserVO> listHandlers();
```

查询条件：

```java
new LambdaQueryWrapper<User>()
    .eq(User::getRole, 2)
    .orderByAsc(User::getId)
```

### 4.4 错误语义

| 场景 | 错误码 | 信息 |
|---|---:|---|
| 目标处理人员不存在 | 404 | 处理人员不存在 |
| 目标用户不是处理人员 | 400 | 目标用户不是处理人员 |
| 当前处理人员不存在 | 404 | 处理人员不存在 |
| 当前用户不是处理人员 | 400 | 目标用户不是处理人员 |
| 工单状态已变化 | 409 | 工单状态已变化，请刷新后重试 |

## 5. 前端设计

### 5.1 派单弹窗

`HazardListView.vue` 的派单弹窗由“手工 UID 输入”改为“处理人员卡片选择”。

结构：

1. 顶部显示工单编号、当前操作类型：
   - `status=0`：首次派单
   - `status=1`：改派专员
   - `status=4`：重新派单
2. 搜索框：按昵称、邮箱、UID 实时过滤。
3. 处理人员卡片网格：
   - 头像首字母或现有头像
   - 昵称
   - 邮箱
   - `UID #id`
   - 当前责任人标记
   - 选中态使用蓝色边框、浅蓝背景和勾选标记
4. 底部显示当前选中人员摘要与确认按钮。
5. 加载中、加载失败、无处理人员分别显示规范状态。
6. 提交成功后关闭弹窗并重新请求列表，不在前端伪造最终状态。

视觉复用：

- 弹窗：`.modal-mask`、`.modal-box.glass-card`
- 输入：`.form-input`
- 按钮：`.modal-btn.confirm` / `.modal-btn.cancel`
- 卡片：白色背景、细边框、20px 圆角、轻阴影
- 选中色：主蓝 `#1a73e8` 与浅蓝背景
- 字号、间距、过渡动画沿用现有页面

### 5.2 已撤回页签

当前源码的 `statusTabs` 已仅在 `userRole === '1'` 时追加：

```js
if (userRole.value === '1') {
  tabs.push({ val: 5, label: '已撤回' })
}
```

本次不改变普通用户和处理人员的可见性，只确保前端重新构建并部署，使管理员线上页面出现“已撤回”页签。

## 6. 测试策略

### 6.1 后端单元测试

- `status=1` 可改派到另一名处理人员。
- `status=0`、`status=4` 派单保持可用。
- 派单目标用户不存在时失败，且工单不更新。
- 派单目标角色不是 `HANDLER` 时失败，且工单不更新。
- 非处理人员不能认领、开始、完成。
- 非当前责任人不能开始、完成。
- 状态并发冲突仍返回 409。
- 管理员处理人员列表只返回 `role=2` 用户。
- 非管理员访问 `/api/users/handlers` 返回 403。

### 6.2 前端验证

- `npm run build` 成功。
- 管理员派单弹窗可加载处理人员、搜索、选中、提交。
- `status=1` 改派成功，列表责任人同步变化。
- 普通用户和处理人员看不到“已撤回”页签。
- 管理员看到“已撤回”页签，筛选后展示 `status=5` 工单。

### 6.3 线上冒烟

使用管理员账号完成一次：

1. 待处理工单派单。
2. 已接单工单改派。
3. 打开已撤回筛选。
4. 查看已撤回工单详情。

使用处理人员账号确认：

1. 新责任人可开始整改、完成整改。
2. 旧责任人在改派后不能继续操作。

## 7. 发布

1. 后端执行相关 Maven 测试并构建。
2. 发布后端 jar 并重启服务。
3. 前端执行构建，将 `dist` 发布到现有 Nginx 静态目录。
4. 清理浏览器缓存后，用管理员与处理人员账号完成线上冒烟。

## 8. 文档同步

实现后同步更新：

- `docs/current/hazard-lifecycle.md`：`assign` 支持 `status IN (0,1,4)`，增加处理人员身份校验。
- `docs/current/architecture.md`：增加 `GET /api/users/handlers`。
- 如部署步骤有变化，更新 `docs/deployment/safety-platform-deployment.md`。
