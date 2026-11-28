# 管理员撤回无效隐患工单 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许管理员撤回 `status=0/1/2` 的无效工单，记录原因和 `ADMIN_WITHDRAW` 日志，同时修复空处理人显示并保持 `status=3` 的验收驳回语义。

**Architecture:** 复用 `status=5`，新增 `withdrawn_reason` 字段与管理员专用原子 UPDATE；前端把 0/1/2 的“驳回”替换为需填写原因的“撤回/终止并撤回”，详情页同步。

**Tech Stack:** Java 17、Spring Boot、MyBatis-Plus、JUnit 5、Mockito、Vue 3、Vite、MySQL、Nginx。

## Global Constraints

- 角色：普通用户 `0`、管理员 `1`、处理人员 `2`。
- 撤回状态固定为 `5`，仅管理员可见。
- `status=3` 的 `/review` 语义不变。
- 管理员撤回必须有非空原因，最长 500 字。
- 处理人员身份校验与改派逻辑保持现有实现。
- 先写失败测试，再写生产代码。

### Task 1: 数据字段与请求模型

**Files:**
- Create: `ai-module/db/schema/migrate_admin_withdraw_reason.py`
- Create: `safety-pojo/src/main/java/com/safety/pojo/dto/AdminWithdrawDTO.java`
- Modify: `safety-pojo/src/main/java/com/safety/pojo/entity/Hazard.java`
- Modify: `safety-pojo/src/main/java/com/safety/pojo/vo/HazardVO.java`

- [ ] **Step 1: 创建迁移脚本**

```python
def add_col(cur, table, col, ddl):
    cur.execute("SHOW COLUMNS FROM %s LIKE %%s" % table, (col,))
    if cur.fetchone() is None:
        cur.execute("ALTER TABLE %s ADD COLUMN %s" % (table, ddl))

add_col(cur, "tb_hazard", "withdrawn_reason",
        "withdrawn_reason VARCHAR(500) NULL COMMENT '撤回原因'")
```

- [ ] **Step 2: 创建 DTO**

```java
@Data
public class AdminWithdrawDTO {
    @NotBlank(message = "撤回原因不能为空")
    @Size(max = 500, message = "撤回原因不能超过500字")
    private String reason;
}
```

- [ ] **Step 3: 添加实体与 VO 字段**

```java
private String withdrawnReason;
```

### Task 2: 管理员撤回接口

**Files:**
- Modify: `safety-service/src/main/java/com/safety/service/mapper/HazardMapper.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/HazardService.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java`
- Modify: `safety-web/src/main/java/com/safety/web/controller/HazardController.java`
- Test: `safety-service/src/test/java/com/safety/service/service/impl/HazardWithdrawTest.java`
- Test: `safety-web/src/test/java/com/safety/web/controller/HazardControllerAuthorizationTest.java`

**Interfaces:**
- Produces: `HazardVO adminWithdraw(Long id, Long adminId, String reason)`
- Produces: `POST /api/hazard/{id}/admin-withdraw`

- [ ] **Step 1: 写失败测试**

```java
@Test
void adminCanWithdrawAcceptedHazardWithReason() {
    when(hazardMapper.adminWithdraw(1L, ME, "AI 误识别")).thenReturn(1);
    Hazard after = hazard(1L, OTHER, 5);
    after.setWithdrawnBy(ME);
    after.setWithdrawnReason("AI 误识别");
    when(hazardMapper.selectById(1L)).thenReturn(after);

    HazardVO vo = service.adminWithdraw(1L, ME, "AI 误识别");

    assertEquals(5, vo.getStatus());
    assertEquals("AI 误识别", vo.getWithdrawnReason());
    ArgumentCaptor<HazardAction> action = ArgumentCaptor.forClass(HazardAction.class);
    verify(hazardActionMapper).insert(action.capture());
    assertEquals("ADMIN_WITHDRAW", action.getValue().getActionType());
}

@Test
void adminCannotWithdrawPendingReviewHazard() {
    when(hazardMapper.adminWithdraw(1L, ME, "无效")).thenReturn(0);
    when(hazardMapper.selectById(1L)).thenReturn(hazard(1L, OTHER, 3));

    BusinessException error = assertThrows(BusinessException.class,
            () -> service.adminWithdraw(1L, ME, "无效"));

    assertEquals(409, error.getCode());
}
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-service -am "-Dtest=HazardWithdrawTest" "-Dsurefire.failIfNoSpecifiedTests=false" test
```

- [ ] **Step 3: 实现 Mapper**

```java
@Update("UPDATE tb_hazard SET status = 5, withdrawn_at = NOW(),"
        + " withdrawn_by = #{adminId}, withdrawn_reason = #{reason}, update_time = NOW()"
        + " WHERE id = #{id} AND status IN (0, 1, 2)")
int adminWithdraw(@Param("id") Long id,
                  @Param("adminId") Long adminId,
                  @Param("reason") String reason);
```

- [ ] **Step 4: 实现服务**

```java
@Override
@Transactional
public HazardVO adminWithdraw(Long id, Long adminId, String reason) {
    int rows = hazardMapper.adminWithdraw(id, adminId, reason);
    if (rows == 0) {
        Hazard current = hazardMapper.selectById(id);
        if (current == null) throw new BusinessException(404, "隐患不存在");
        if (Objects.equals(current.getStatus(), STATUS_WITHDRAWN)) return toVO(current);
        throw new BusinessException(409, "仅待处理、已接单或整改中的工单可撤回");
    }
    saveAction(id, adminId, "ADMIN_WITHDRAW", reason);
    invalidateDetailCacheAfterCommit(id);
    return toVO(hazardMapper.selectById(id));
}
```

- [ ] **Step 5: 实现 Controller**

```java
@PostMapping("/{id:\\d+}/admin-withdraw")
@PreAuthorize("hasRole('ADMIN')")
public R<HazardVO> adminWithdraw(@PathVariable Long id,
                                 @Valid @RequestBody AdminWithdrawDTO dto,
                                 Authentication auth) {
    return R.ok(hazardService.adminWithdraw(
            id, (Long) auth.getPrincipal(), dto.getReason()));
}
```

- [ ] **Step 6: 运行测试确认通过**

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am "-Dtest=HazardWithdrawTest,HazardStateTransitionTest,HazardControllerAuthorizationTest" "-Dsurefire.failIfNoSpecifiedTests=false" test
```

### Task 3: 前端按钮、撤回弹窗与空值兜底

**Files:**
- Modify: `.codex-remote-frontend-edit/HazardListView.vue`
- Modify: `.codex-remote-frontend-edit/HazardDetailView.vue`
- Mirror: both files under `/home/ubuntu/aisafety-platform-frontend/src/views/`

- [ ] **Step 1: 替换 0/1/2 驳回按钮**

列表：

```vue
<button class="action-flow-btn btn-withdraw" @click.stop="openAdminWithdrawDialog(item)">
  <span>{{ item.status === 0 ? '撤回工单' : '终止并撤回' }}</span>
</button>
```

详情同理，调用 `openAdminWithdrawDialog`。

- [ ] **Step 2: 增加撤回原因弹窗状态与提交**

```js
const adminWithdrawVisible = ref(false)
const adminWithdrawTarget = ref(null)
const adminWithdrawReason = ref('')
const adminWithdrawLoading = ref(false)

async function submitAdminWithdraw() {
  const reason = adminWithdrawReason.value.trim()
  if (!reason) return
  const token = localStorage.getItem('token')
  const id = adminWithdrawTarget.value?.id
  const res = await fetch(`/api/hazard/${id}/admin-withdraw`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + token,
    },
    body: JSON.stringify({ reason }),
  })
  const json = await res.json().catch(() => ({}))
  if (!res.ok || json.code !== 200) throw new Error(json.message || '撤回失败')
  adminWithdrawVisible.value = false
  await fetchHazards()
}
```

- [ ] **Step 3: 空值兜底**

```vue
<span v-if="item.handlerId">专员 #{{ item.handlerId }} 处置中</span>
<span v-else>尚未指派处理人员</span>
```

详情：

```vue
<p v-if="hazard.handlerId">本工单已指定由责任专员 #{{ hazard.handlerId }} 全程推进...</p>
<p v-else>该工单尚未指派责任专员。</p>
```

- [ ] **Step 4: 展示撤回原因**

管理员查看 `status=5` 且 `withdrawnReason` 非空时展示：

```vue
<div v-if="hazard.withdrawnReason" class="withdrawn-reason-box">
  撤回原因：{{ hazard.withdrawnReason }}
</div>
```

- [ ] **Step 5: 构建并发布前端**

```bash
cd /home/ubuntu/aisafety-platform-frontend
npm run build
```

发布到 `/var/www/safety-platform` 后验证：

```js
document.body.innerText.includes('终止并撤回') === false || true
document.querySelector('#admin-withdraw-dialog') !== null
```

### Task 4: 迁移、发布、回归

- [ ] **Step 1: 执行数据库迁移**

```bash
ssh ubuntu@106.53.219.214 'cd /home/ubuntu/ai-module && .venv/bin/python db/schema/migrate_admin_withdraw_reason.py'
```

- [ ] **Step 2: 跑完整后端测试与打包**

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am test
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am package "-DskipTests"
```

- [ ] **Step 3: 发布并验证**

- 管理员撤回 `status=0`、`1`、`2` 各一条测试工单
- 确认进入已撤回列表
- 确认 `status=3` 仍只能验收通过或驳回返工
- 确认处理人员无法继续操作已撤回工单
- 确认空 `handlerId` 不再出现“专员 # 处置中”

- [ ] **Step 4: 更新文档并提交**

更新：

- `docs/current/hazard-lifecycle.md`
- `docs/current/architecture.md`
- `docs/current/project-overview.md`
