# 隐患改派与处理人员身份校验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许管理员在已接单状态改派，并在服务层保证派单对象和处置操作人都是真实处理人员，同时把派单弹窗升级为真实人员选择器并发布管理员“已撤回”页签。

**Architecture:** 后端用条件 UPDATE 统一处理 `0/1/4 -> 1` 的派单与改派，在 `HazardServiceImpl` 中通过 `UserMapper` 行锁校验 `role=2`。前端新增管理员专用处理人员列表接口，派单弹窗用可搜索卡片选择真实人员，最后重新构建并发布前端。

**Tech Stack:** Java 17、Spring Boot、MyBatis-Plus、JUnit 5、Mockito、Vue 3、Vite、Nginx、MySQL。

## Global Constraints

- 角色值固定为：普通用户 `0`、管理员 `1`、处理人员 `2`。
- 已撤回状态固定为 `5`，仅管理员可见，不改变撤回数据保留规则。
- 派单和改派必须使用条件 UPDATE，不能先查后改。
- 派单弹窗不得再手填处理人员 UID，必须从 `GET /api/users/handlers` 选择。
- 前端必须保持现有白色卡片、主蓝 `#1a73e8`、20px 圆角和药丸按钮风格。
- 测试必须先失败，再实现，再通过。
- 不把账号密码写入源码、文档或 Git。

---

### Task 1: 后端允许改派并校验处理人员身份

**Files:**
- Modify: `safety-service/src/main/java/com/safety/service/mapper/HazardMapper.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java`
- Test: `safety-service/src/test/java/com/safety/service/service/impl/HazardStateTransitionTest.java`

**Interfaces:**
- Consumes: `UserMapper.selectByIdForUpdate(Long id): User`
- Produces: `HazardServiceImpl.assign(Long id, Long adminId, Long handlerId): HazardVO`
- Produces: `HazardServiceImpl.start(Long id, Long userId, Integer role): HazardVO`
- Produces: `HazardServiceImpl.complete(Long id, Long userId, Integer role): HazardVO`

- [ ] **Step 1: 写失败测试，锁定改派与身份校验**

在 `HazardStateTransitionTest` 中增加 `UserMapper` mock，并把 setup 改为新构造器：

```java
@Mock private UserMapper userMapper;

@BeforeEach
void setUp() {
    service = new HazardServiceImpl(
            hazardMapper, hazardActionMapper, userMapper,
            redisTemplate, redissonClient, null);
    service.init();
}

private User handlerUser(long id) {
    User user = new User();
    user.setId(id);
    user.setRole(2);
    return user;
}
```

增加测试：

```java
@Test
void reassignAcceptedHazardToAnotherHandler() {
    Long nextHandlerId = 9L;
    when(userMapper.selectByIdForUpdate(nextHandlerId)).thenReturn(handlerUser(nextHandlerId));
    when(hazardMapper.assign(HAZARD_ID, nextHandlerId)).thenReturn(1);
    when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(1, USER_ID, nextHandlerId));

    var result = service.assign(HAZARD_ID, USER_ID, nextHandlerId);

    assertEquals(1, result.getStatus());
    assertEquals(nextHandlerId, result.getHandlerId());
    verify(hazardMapper).assign(HAZARD_ID, nextHandlerId);
}

@Test
void assignRejectsMissingHandler() {
    when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(null);

    BusinessException error = assertThrows(BusinessException.class,
            () -> service.assign(HAZARD_ID, USER_ID, HANDLER_ID));

    assertEquals(404, error.getCode());
    verify(hazardMapper, never()).assign(any(), any());
}

@Test
void assignRejectsNonHandlerUser() {
    User ordinary = handlerUser(HANDLER_ID);
    ordinary.setRole(0);
    when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(ordinary);

    BusinessException error = assertThrows(BusinessException.class,
            () -> service.assign(HAZARD_ID, USER_ID, HANDLER_ID));

    assertEquals(400, error.getCode());
    verify(hazardMapper, never()).assign(any(), any());
}

@Test
void startRejectsNonHandlerAccount() {
    User ordinary = handlerUser(HANDLER_ID);
    ordinary.setRole(0);
    when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(ordinary);

    BusinessException error = assertThrows(BusinessException.class,
            () -> service.start(HAZARD_ID, HANDLER_ID, 2));

    assertEquals(400, error.getCode());
    verify(hazardMapper, never()).transitionForHandler(any(), anyInt(), anyInt(), any());
}
```

同时给现有 `assignUsesConditionalUpdateAndLogsAction`、`startUsesHandlerScopedConditionalUpdate`、`completeSuccessMarksPendingReview`、`staleStartStatusReturnsConflict` 增加：

```java
when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(handlerUser(HANDLER_ID));
```

并把 SQL 断言改为：

```java
assertTrue(assignSql.contains("status in (0, 1, 4)"));
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-service -am "-Dtest=HazardStateTransitionTest" -Dsurefire.failIfNoSpecifiedTests=false test
```

Expected: 编译失败，提示 `HazardServiceImpl` 构造器参数不匹配，或运行失败提示 `status in (0, 1, 4)` 断言不成立。

- [ ] **Step 3: 实现最小后端改动**

`HazardMapper.assign`：

```java
@Update("UPDATE tb_hazard SET status = 1, reviewed = 0, handler_id = #{handlerId},"
        + " update_time = NOW() WHERE id = #{id} AND status IN (0, 1, 4)")
int assign(@Param("id") Long id, @Param("handlerId") Long handlerId);
```

`HazardServiceImpl` 注入 `UserMapper`：

```java
private final UserMapper userMapper;

public HazardServiceImpl(HazardMapper hazardMapper,
                         HazardActionMapper hazardActionMapper,
                         UserMapper userMapper,
                         StringRedisTemplate redisTemplate,
                         RedissonClient redissonClient,
                         FileAssetService fileAssetService) {
    this.hazardMapper = hazardMapper;
    this.hazardActionMapper = hazardActionMapper;
    this.userMapper = userMapper;
    this.redisTemplate = redisTemplate;
    this.redissonClient = redissonClient;
    this.fileAssetService = fileAssetService;
}
```

保留现有四参数测试构造器，并委托为 `userMapper=null`、`fileAssetService=null`：

```java
public HazardServiceImpl(HazardMapper hazardMapper,
                         HazardActionMapper hazardActionMapper,
                         StringRedisTemplate redisTemplate,
                         RedissonClient redissonClient) {
    this(hazardMapper, hazardActionMapper, null,
            redisTemplate, redissonClient, null);
}
```

增加校验方法：

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

在 `assign` 的 UPDATE 前调用：

```java
requireHandlerUser(handlerId);
int rows = hazardMapper.assign(id, handlerId);
```

在 `transition` 的非管理员分支前调用：

```java
if (!isAdmin) {
    requireHandlerUser(userId);
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-service -am "-Dtest=HazardStateTransitionTest,HazardWithdrawTest" -Dsurefire.failIfNoSpecifiedTests=false test
```

Expected: 全部通过，无失败和错误。

- [ ] **Step 5: 提交**

```powershell
git add safety-service/src/main/java/com/safety/service/mapper/HazardMapper.java safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java safety-service/src/test/java/com/safety/service/service/impl/HazardStateTransitionTest.java
git commit -m "feat(hazard): allow reassignment and validate handlers"
```

---

### Task 2: 新增管理员处理人员列表接口

**Files:**
- Modify: `safety-service/src/main/java/com/safety/service/service/UserService.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/impl/UserServiceImpl.java`
- Modify: `safety-web/src/main/java/com/safety/web/controller/UserController.java`
- Test: `safety-service/src/test/java/com/safety/service/service/impl/UserServiceImplHandlerListTest.java`
- Test: `safety-web/src/test/java/com/safety/web/controller/UserControllerAuthorizationTest.java`

**Interfaces:**
- Consumes: `UserMapper.selectList(Wrapper<User>): List<User>`
- Produces: `UserService.listHandlers(): List<UserVO>`
- Produces: `GET /api/users/handlers -> R<List<UserVO>>`

- [ ] **Step 1: 写失败测试**

创建 `UserServiceImplHandlerListTest.java`：

```java
package com.safety.service.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.safety.pojo.entity.User;
import com.safety.pojo.vo.UserVO;
import com.safety.service.mapper.UserMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class UserServiceImplHandlerListTest {

    @Test
    void listHandlersReturnsRoleTwoUsers() {
        UserMapper userMapper = mock(UserMapper.class);
        User handler = new User();
        handler.setId(4L);
        handler.setEmail("handler@example.com");
        handler.setNickname("处理员");
        handler.setRole(2);
        when(userMapper.selectList(any())).thenReturn(List.of(handler));
        UserServiceImpl service = new UserServiceImpl(
                userMapper, null, null, null, null);

        List<UserVO> result = service.listHandlers();

        assertEquals(1, result.size());
        assertEquals(4L, result.get(0).getId());
        assertEquals(2, result.get(0).getRole());
        ArgumentCaptor<Wrapper<User>> wrapper = ArgumentCaptor.forClass(Wrapper.class);
        verify(userMapper).selectList(wrapper.capture());
        assertEquals(true, wrapper.getValue().getSqlSegment().toLowerCase().contains("role"));
    }
}
```

创建 `UserControllerAuthorizationTest.java`：

```java
package com.safety.web.controller;

import com.safety.service.service.UserService;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;

import static org.junit.jupiter.api.Assertions.assertEquals;

class UserControllerAuthorizationTest {

    @Test
    void handlerDirectoryRequiresAdmin() throws Exception {
        PreAuthorize annotation = UserController.class
                .getMethod("handlers")
                .getAnnotation(PreAuthorize.class);
        assertEquals("hasRole('ADMIN')", annotation.value());
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am "-Dtest=UserServiceImplHandlerListTest,UserControllerAuthorizationTest" -Dsurefire.failIfNoSpecifiedTests=false test
```

Expected: 编译失败，提示 `listHandlers` 和 `handlers` 不存在。

- [ ] **Step 3: 实现接口与查询**

`UserService` 增加：

```java
List<UserVO> listHandlers();
```

`UserServiceImpl` 增加：

```java
@Override
public List<UserVO> listHandlers() {
    return userMapper.selectList(new LambdaQueryWrapper<User>()
                    .eq(User::getRole, 2)
                    .orderByAsc(User::getId))
            .stream()
            .map(this::toVO)
            .toList();
}

private UserVO toVO(User user) {
    return UserVO.builder()
            .id(user.getId())
            .email(user.getEmail())
            .nickname(user.getNickname())
            .avatar(user.getAvatar())
            .role(user.getRole())
            .createTime(user.getCreateTime())
            .build();
}
```

`UserController` 增加：

```java
@GetMapping("/handlers")
@PreAuthorize("hasRole('ADMIN')")
public R<java.util.List<UserVO>> handlers() {
    return R.ok(userService.listHandlers());
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am "-Dtest=UserServiceImplHandlerListTest,UserControllerAuthorizationTest,HazardEndpointSecurityTest" -Dsurefire.failIfNoSpecifiedTests=false test
```

Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add safety-service/src/main/java/com/safety/service/service/UserService.java safety-service/src/main/java/com/safety/service/service/impl/UserServiceImpl.java safety-web/src/main/java/com/safety/web/controller/UserController.java safety-service/src/test/java/com/safety/service/service/impl/UserServiceImplHandlerListTest.java safety-web/src/test/java/com/safety/web/controller/UserControllerAuthorizationTest.java
git commit -m "feat(user): expose handler directory for admins"
```

---

### Task 3: 前端派单弹窗与已撤回页签

**Files:**
- Modify: `.codex-remote-frontend-edit/HazardListView.vue`
- Mirror: `/home/ubuntu/aisafety-platform-frontend/src/views/HazardListView.vue`

**Interfaces:**
- Consumes: `GET /api/users/handlers`
- Produces: handler card selection and search UI
- Produces: admin-only `status=5` tab after rebuild

- [ ] **Step 1: 写前端冒烟断言并确认失败**

在浏览器中登录 `admin@qq.com`，打开 `/hazard`。断言：

```js
document.body.innerText.includes('已撤回') === true
document.body.innerText.includes('快捷指定') === false
document.querySelector('[data-testid="handler-picker"]') !== null
```

Expected: 当前线上三条断言全部失败，因为当前 bundle 不含“已撤回”，派单仍为手工 UID。

- [ ] **Step 2: 增加前端状态和请求函数**

在 `HazardListView.vue` 的 setup 区域加入：

```js
const handlers = ref([])
const handlerLoading = ref(false)
const handlerError = ref('')
const handlerSearch = ref('')
const selectedHandlerId = ref(null)

const filteredHandlers = computed(() => {
  const keyword = handlerSearch.value.trim().toLowerCase()
  if (!keyword) return handlers.value
  return handlers.value.filter((handler) =>
    String(handler.id).includes(keyword) ||
    (handler.nickname || '').toLowerCase().includes(keyword) ||
    (handler.email || '').toLowerCase().includes(keyword)
  )
})

const selectedHandler = computed(() =>
  handlers.value.find((handler) => Number(handler.id) === Number(selectedHandlerId.value)) || null
)

const assignActionText = computed(() => {
  if (currentOperatingItem.value?.status === 1) return '确认改派'
  if (currentOperatingItem.value?.status === 4) return '确认重新派单'
  return '确认派单'
})

async function fetchHandlers() {
  handlerLoading.value = true
  handlerError.value = ''
  try {
    const token = localStorage.getItem('token')
    const res = await fetch('/api/users/handlers', {
      headers: { Authorization: 'Bearer ' + token },
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '加载处理人员失败')
    }
    handlers.value = Array.isArray(json.data) ? json.data : []
  } catch (err) {
    handlerError.value = err.message || '加载处理人员失败'
  } finally {
    handlerLoading.value = false
  }
}
```

- [ ] **Step 3: 改造打开与提交派单逻辑**

```js
async function openAssignModal(item) {
  currentOperatingItem.value = item
  selectedHandlerId.value = item.handlerId || null
  handlerSearch.value = ''
  assignModalVisible.value = true
  await fetchHandlers()
}

async function submitAssign() {
  const token = localStorage.getItem('token')
  if (!token || !currentOperatingItem.value || !selectedHandlerId.value) return
  modalLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${currentOperatingItem.value.id}/assign`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ handlerId: Number(selectedHandlerId.value) }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '派单失败')
    }
    assignModalVisible.value = false
    await fetchHazards()
  } catch (err) {
    alert(err.message || '派单未成功，请重试')
  } finally {
    modalLoading.value = false
  }
}
```

- [ ] **Step 4: 替换派单弹窗模板**

把原 UID 输入替换为：

```html
<div class="form-group">
  <label class="form-label">搜索处理人员</label>
  <input
    v-model="handlerSearch"
    class="form-input"
    placeholder="按昵称、邮箱或 UID 搜索"
  />
</div>

<div v-if="handlerLoading" class="handler-state">正在加载处理人员...</div>
<div v-else-if="handlerError" class="handler-state error">{{ handlerError }}</div>
<div v-else-if="!filteredHandlers.length" class="handler-state">暂无匹配的处理人员</div>
<div v-else class="handler-grid" data-testid="handler-picker">
  <button
    v-for="handler in filteredHandlers"
    :key="handler.id"
    type="button"
    class="handler-card"
    :class="{ selected: Number(selectedHandlerId) === Number(handler.id) }"
    @click="selectedHandlerId = handler.id"
  >
    <span class="handler-avatar">{{ (handler.nickname || handler.email || '处').slice(0, 1) }}</span>
    <span class="handler-name">{{ handler.nickname || '未命名处理人员' }}</span>
    <span class="handler-email">{{ handler.email }}</span>
    <span class="handler-id num-font">UID #{{ handler.id }}</span>
    <span v-if="Number(currentOperatingItem?.handlerId) === Number(handler.id)" class="handler-current">当前负责人</span>
  </button>
</div>
```

底部确认按钮：

```html
<button
  class="modal-btn confirm"
  :disabled="!selectedHandlerId || modalLoading || handlerLoading"
  @click="submitAssign"
>
  {{ modalLoading ? '提交中...' : assignActionText }}
</button>
```

- [ ] **Step 5: 增加与现有风格一致的 CSS**

```css
.handler-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
  padding: 4px;
}

.handler-card {
  position: relative;
  display: grid;
  grid-template-columns: 42px 1fr;
  grid-template-rows: auto auto auto;
  column-gap: 12px;
  row-gap: 3px;
  padding: 14px;
  text-align: left;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.handler-card:hover,
.handler-card.selected {
  border-color: #1a73e8;
  background: #f4f8ff;
  box-shadow: 0 8px 24px rgba(26, 115, 232, 0.1);
}

.handler-avatar {
  grid-row: 1 / span 3;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #1a73e8, #60a5fa);
  color: #ffffff;
  display: grid;
  place-items: center;
  font-weight: 700;
}

.handler-name {
  color: #0f172a;
  font-size: 14px;
  font-weight: 650;
}

.handler-email,
.handler-id {
  color: #64748b;
  font-size: 12px;
}

.handler-current {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 11px;
}

.handler-state {
  padding: 28px 16px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}

.handler-state.error {
  color: #dc2626;
}
```

- [ ] **Step 6: 同步源码并构建**

把改后的 `HazardListView.vue` 同步到：

```text
/home/ubuntu/aisafety-platform-frontend/src/views/HazardListView.vue
```

在服务器执行：

```bash
cd /home/ubuntu/aisafety-platform-frontend
npm run build
```

Expected: Vite 构建成功，新 bundle 包含“已撤回”和 `handler-picker` 标记。

- [ ] **Step 7: 发布前端并验证**

将 `dist` 发布到当前 Nginx 静态目录，刷新浏览器后断言：

```js
document.body.innerText.includes('已撤回') === true
document.body.innerText.includes('快捷指定') === false
document.querySelector('[data-testid="handler-picker"]') !== null
```

Expected: 三条断言全部通过。

- [ ] **Step 8: 提交前端源码镜像**

如果 `.codex-remote-frontend-edit` 被 `.gitignore` 排除，则只提交服务器源码对应的受控副本；若项目约定不追踪前端，记录发布校验结果并在最终回复说明。

---

### Task 4: 文档同步、回归和线上冒烟

**Files:**
- Modify: `docs/current/hazard-lifecycle.md`
- Modify: `docs/current/architecture.md`
- Test: live admin/handler API flow

**Interfaces:**
- Consumes: completed backend and frontend changes
- Produces: updated lifecycle and API docs plus release evidence

- [ ] **Step 1: 更新文档**

`hazard-lifecycle.md`：

```markdown
- `assign`：仅 `status ∈ {0, 1, 4}` 可派/改派；管理员；写 `handler_id`，`reviewed=0`。
- 派单目标必须存在且角色为 `HANDLER`；认领、开始、完成也会在服务层复核处理人员身份。
```

`architecture.md`：

```markdown
| `/api/users/handlers` | UserController | `GET`（管理员）处理人员目录 |
```

- [ ] **Step 2: 运行完整后端回归**

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am test
```

Expected: 全部测试通过。

- [ ] **Step 3: 构建并发布后端**

```powershell
C:\Users\21556\.m2\wrapper\dists\apache-maven-3.9.12-bin\5nmfsn99br87k5d4ajlekdq10k\apache-maven-3.9.12\bin\mvn.cmd -q -pl safety-web -am package -DskipTests
```

将 `safety-web/target/*.jar` 发布到现有服务路径并重启后端。

- [ ] **Step 4: 线上 API 冒烟**

1. 管理员登录并调用 `GET /api/users/handlers`，确认只返回 `role=2`。
2. 选取一条 `status=1` 工单，记录旧 `handlerId`。
3. 调用 `POST /api/hazard/{id}/assign` 改成另一名处理人员。
4. 确认返回 `status=1` 且 `handlerId` 已变化。
5. 旧处理人员调用 `start` 应失败，新处理人员调用 `start` 应成功。
6. 管理员打开 `/hazard`，确认出现“已撤回”页签。

- [ ] **Step 5: 提交文档和最终验证结果**

```powershell
git add docs/current/hazard-lifecycle.md docs/current/architecture.md
git commit -m "docs(hazard): document reassignment and handler validation"
```

---

## Self-Review

- Spec coverage：改派状态、处理人员校验、处理人员列表、派单弹窗、已撤回页签、测试和发布均有对应任务。
- Placeholder scan：无 TBD、TODO 或未定义步骤。
- Type consistency：`listHandlers(): List<UserVO>`、`GET /api/users/handlers`、`selectedHandlerId` 与 `handlerId` 命名前后一致。
