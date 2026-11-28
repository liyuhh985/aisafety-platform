> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/hazard-lifecycle.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 角色权限 + 状态流转 执行计划

> 日期：2026-09-07
> 背景：AI 上报闭环已打通（建隐患 `status=0`）。本期给隐患加上**角色权限**和**状态流转**，让"上报 → 待处理 → 已接单 → 整改中 → 已完成"形成闭环，并按角色区分（普通用户 / 处理人员 / 管理员）。

---

## 一、角色与状态定义（需拍板）

| 角色 role | 含义 | 权限概要 |
|---|---|---|
| `0` | 普通用户（举报者） | 上报隐患、查看**自己上报的** |
| `1` | 管理员 | 派单、审查、管理全部、任意流转 |
| `2` | 处理人员 | 接单、整改、完成（处理自己接的） |

| 状态 status | 含义 |
|---|---|
| `0` | 待处理 |
| `1` | 已接单 |
| `2` | 整改中 |
| `3` | 已完成 |

**权限矩阵**：

| 操作 | 普通用户 | 处理人员 | 管理员 |
|---|---|---|---|
| 上报（现有 create/AI） | ✔ | ✔ | ✔ |
| 查看自己的上报 | ✔（仅自己） | （看分配/全待处理） | ✔（全部） |
| 接单 0→1 | ✘ | ✔ | ✔ |
| 开始整改 1→2 | ✘ | ✔ | ✔ |
| 完成 2→3 | ✘ | ✔ | ✔ |
| 派单（指定 handler） | ✘ | ✘ | ✔ |
| 审查/回退 | ✘ | ✘ | ✔ |

---

## 二、现状盘点

- `User.role`：Integer，现有 `0`=普通、`1`=管理员，**无 `2` 处理人员**；登录返回带 role。
- `tb_hazard`：有 `status`（0/1/2/3 已在 stats 里用 2/3），**无 handler_id（处理人）**。
- `HazardAction`：实体 + `HazardActionMapper` 已存在（id/hazardId/operatorId/actionType/remark/createTime），**无 Service/Controller**。
- `HazardVO`：有 status/statusText，**无 district/report**（上报用到，建议补齐）。
- `Security`：仅 URL 级 permitAll/authenticated；**未启用方法级权限**；JWT 只含 userId、**不含 role**；`JwtAuthenticationFilter` 设置的 Authentication **无 authorities**。
- `HazardServiceImpl`：有 `create/createAi/page/getById/getStats`，**无 status 流转方法**。

---

## 三、Task 分解

### Task 1：角色与安全上下文（让权限可用）
**Files:** `safety-common/.../JwtUtil.java`、`safety-web/.../config/JwtAuthenticationFilter.java`、`AuthController`/`UserService`（登录处）
- [ ] `JwtUtil.generate(userId, role)`：把 `role` 写入 claim；保留 `parseUserId`，新增 `parseRole`。
- [ ] `JwtAuthenticationFilter`：解析 `role`，设置 `UsernamePasswordAuthenticationToken(userId, null, List.of(new SimpleGrantedAuthority("ROLE_"+roleName)))`（role 0→ROLE_USER、1→ROLE_ADMIN、2→ROLE_HANDLER）。兼容旧 token（无 role claim 时回退查 Redis/User）。
- [ ] `@EnableMethodSecurity` 加到 `SecurityConfig`。
- [ ] 登录/注册处调用 `generate(userId, role)`。

### Task 2：隐患处理人 + VO 补齐
**Files:** `safety-pojo/.../entity/Hazard.java`、`safety-pojo/.../vo/HazardVO.java`、`ai-module/db/migrate_ai_report.py`（或新 SQL）
- [ ] `tb_hazard` 加 `handler_id BIGINT NULL`（当前处理人），加索引。
- [ ] `Hazard` 实体加 `handlerId`。
- [ ] `HazardVO` 加 `district`、`report`、`handlerId`；`statusText` 映射 0/1/2/3。

### Task 3：状态流转 Service
**Files:** `safety-service/.../service/HazardService.java`、`service/impl/HazardServiceImpl.java`、`.../mapper/HazardActionMapper.java`（已存在）、`.../service/HazardActionService.java`（新增）
- [ ] 新增方法：`accept(id, userId)`、`start(id, userId)`、`complete(id, userId)`、或统一 `updateStatus(id, from, to, userId, remark)`。
- [ ] 流转校验：仅允许 `0→1→2→3` 顺序；非法跳转/重复流转抛 `BusinessException`。
- [ ] 每次流转：`Hazard.status` 更新 + 写 `HazardAction`（operatorId=当前用户、actionType=ACCEPT/START/COMPLETE、remark）。
- [ ] 接单时 `handler_id = userId`（处理人员/管理员）。
- [ ] 删除/失效相关缓存（invalidateDetailCache/invalidateListCache）。

### Task 4：Controller + 权限
**Files:** `safety-web/.../controller/HazardController.java`、`SecurityConfig.java`
- [ ] 新增：`POST /api/hazard/{id}/accept`、`/start`、`/complete`，`@PreAuthorize("hasAnyRole('HANDLER','ADMIN')")`。
- [ ] 新增：`GET /api/hazard/mine`（普通用户：只看自己 user_id）。
- [ ] `SecurityConfig`：这些路径需认证；`@PreAuthorize` 做角色判定。
- [ ] 普通用户查看列表默认过滤只自己；处理人员/管理员看全部（或分配）。

### Task 5：测试 + 验证
- [ ] 不同角色访问约束（user/handler/admin）返回 200/403。
- [ ] 状态流转：0→1→2→3 合法；跳转（如 0→2）拒绝；多次流转写 `HazardAction`。
- [ ] `tb_hazard.handler_id`、`status` 正确更新。
- [ ] 前端（二期）：MapPage/Home 按角色显示按钮（接单/整改/完成）。

---

## 四、待你拍板

1. **role 取值**：`0` 普通 / `1` 管理员 / `2` 处理人员，OK？
2. **流转是否严格顺序**：只允许 `0→1→2→3`，不允许跳转（如 0→2、1→3），OK？
3. **处理人（handler_id）**：接单时记录当前处理人（处理人员/管理员），管理员的接单也算，OK？
4. **普通用户列表**：是否只让普通用户看**自己上报的**（`/api/hazard/mine`），处理人员看全部待处理＋自己已接的，管理员看全部？
5. **前端按钮**：本期先做后端接口 + 权限，前端按角色显隐按钮放二期，OK？

---

## 五、自检清单

- [ ] JWT 带 role，SecurityContext 有 authorities，`@PreAuthorize` 生效。
- [ ] 0→1→2→3 顺序流转，非法跳转被拒，`HazardAction` 记录完整。
- [ ] `handler_id` 接单时写入，`statusText` 正确。
- [ ] 普通用户只能看自己的；处理人员/管理员按矩阵授权。
- [ ] 相关 pytest / mvn 编译 + 联调通过。

---

## 联调完成（2026-09-07 更新）

**角色权限 + 状态流转** 已实现并联调验证：

- [x] Task 1：JWT 带 role + `JwtAuthenticationFilter` 设 `ROLE_USER/ROLE_ADMIN/ROLE_HANDLER` + `@EnableMethodSecurity`。
- [x] Task 2：`tb_hazard.handler_id` + `Hazard.handlerId` + `HazardVO` 补 district/report/handlerId + `statusText` 0待处理/1已接单/2整改中/3已完成（`toVO` 更新）。
- [x] Task 3：`accept/start/complete` 严格 0→1→2→3，写 `HazardAction`，接单写 handler_id；`page(current,size,userId,role)` 按角色过滤（普通用户只看自己）。
- [x] Task 4：Controller `POST /api/hazard/{id}/accept|start|complete`（`@PreAuthorize("hasAnyRole('HANDLER','ADMIN')")`）；`page` 带 auth 过滤；`GlobalExceptionHandler` 授权失败返回 403（修复：原本被 `@ExceptionHandler(Exception)` 吞成 500）。
- [x] 联调验证：处理人员 0→1→2→3、管理员流转、普通用户接单被拒 403、普通用户 page 只看自己、处理人员看全部、`HazardAction` 记录完整。

> 说明：`mvn package` 用 `-Dmaven.test.skip=true`（部分旧测试引用了旧 `page(int,int)` 签名，待更新测试）；前端按钮显隐（按角色）放二期。

---

## 人工审查 / 派单 完成（2026-09-08）

- [x] `tb_hazard.reviewed`（0未审/1通过）+ `Hazard/VO.reviewed` + `statusText` 补 `4 已驳回`。
- [x] 流程调整为：**0→1 只能管理员派单**；处理人员只能 `1→2→3` 且必须 `handler_id==自己`（越权拒绝）；管理员可任意。
- [x] 接口：
  - `POST /api/hazard/{id}/assign {handlerId}`（ADMIN，0→1，写 ASSIGN）
  - `POST /api/hazard/{id}/review {pass,remark}`（ADMIN，通过→reviewed=1；驳回→status=4）
  - `POST /api/hazard/{id}/start|complete`（HANDLER/ADMIN，handler 绑定校验）
- [x] 联调验证：派单 0→1、整改 1→2、完成 2→3、处理人被拒(处理别人)、审查通过/驳回、`HazardAction` 留痕。
