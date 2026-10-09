# 前端需求：助手建单成功后的「查看工单」入口（消费 task_created 事件）

日期：2026-10-09　后端：已完成并上线　前端：待改（`HomeView.vue`）

## 1. 背景

助手确认建单成功后，原来由后端直接拼一句话给前端：

```
✅ 已创建隐患任务，任务编号 59
```

用户明确不希望聊天正文里出现裸的工单编号。已改为：

- **正文**只说结果：`✅ 已创建隐患任务`（**不含任何编号**）
- **工单 id 走结构化事件** `task_created`（和现有 `taxonomy` 事件同一套路），前端据此渲染「查看工单」按钮跳详情页

## 2. 后端契约（已上线，可直接对接）

SSE 事件名：`task_created`

```json
{"type": "task_created", "content": {"hazard_id": 61, "hazard_code": "#HAZ-61"}}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `hazard_id` | int | 工单主键，用来拼详情页路由 `/hazard/{id}` |
| `hazard_code` | string | 展示号，全站惯例格式 `#HAZ-{id}`（详情页/列表页/地图页都在用） |

经 Java + nginx 转发后的**原始行**（注意 `data:` 后面没有空格，前端现有解析已经能处理）：

```
data:{"type": "task_created", "content": {"hazard_id": 61, "hazard_code": "#HAZ-61"}}
```

要点：

- **顺序**：同一轮里先发正文 chunk（`✅ 已创建隐患任务`），再发 `task_created`；但前端代码要能容忍两者顺序颠倒。
- **边界**：后端拿不到工单 id 时**不发**这个事件（正文仍有 `✅ 已创建隐患任务`）。所以按钮是"可能不出现"的，不能假设一定有。
- **兼容**：前端改之前页面照常工作，只是没有按钮、正文少了个编号。

## 3. 前端改动（文件：`src/views/HomeView.vue`）

### 3.1 消费事件（必需）

在 SSE 循环里、`event.type === 'interrupt'` 那一支之后（当前约 765-774 行）加一支：

```js
} else if (event.type === 'task_created') {
  // 后端建单成功：把工单信息挂在当前这条助手消息上，渲染「查看工单」按钮
  const t = event.content || {}
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.taskCreated = t
  } else {
    // 顺序兜底：事件比正文先到
    messages.value.push({ role: 'assistant', content: '', taskCreated: t })
  }
  saveChatCache()
  scrollToBottom()
}
```

### 3.2 渲染按钮（必需）

在每条消息的模板里、任务确认卡片（当前约 220-243 行的 `interrupt-confirm-card`）之后加：

```vue
<!-- 建单成功后的「查看工单」入口（消费 task_created 事件） -->
<div v-if="msg.taskCreated" class="task-created-row">
  <button
    type="button"
    class="task-created-btn"
    @click="router.push(`/hazard/${msg.taskCreated.hazard_id}`)"
  >
    <span>查看工单</span>
    <span class="task-created-code num-font">{{ msg.taskCreated.hazard_code }}</span>
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  </button>
</div>
```

- `router` 已存在（`import { useRouter } from 'vue-router'` 约 419 行，`const router = useRouter()` 约 424 行），不用新增导入。
- 路由已存在：`/hazard/:id` → `HazardDetailView`，且带 `requiresAuth`（未登录会被守卫送去登录页）。
- 如果不想要 `#HAZ-61` 这个小标签，把 `<span class="task-created-code">` 那行删掉即可，其余不变。

### 3.3 样式（可选）

`task-created-row / task-created-btn / task-created-code` 自定即可，建议跟现有 `interrupt-btn` 同一视觉家族（浅底 + 主色描边 + 右侧箭头）。

### 3.4 顺带（同一文件，之前已提过的那条）

「追问地址」的中断卡片要按类型分流，否则用户在卡片上点「确认建单」会把 `好的` 当地址发回去，无限追问：

```vue
<div v-if="msg.interrupt.type === 'ask_address'" class="interrupt-hint-row">
  <span class="interrupt-hint">请在下方输入框里写出具体地址后发送，例如：XX 市 XX 区 XX 路 XX 小区 / XX 地标。</span>
</div>
<div v-else class="interrupt-actions"><!-- 原来两个按钮 --></div>
```

并在 `executeStreamChat` 开头（`if (analyzing.value) return` 之后）补一行，让用户用输入框回应时收起旧卡片：

```js
messages.value.forEach((m) => { if (m.interrupt) m.interruptHandled = true })
```

## 4. 构建发布

`/var/www/safety-platform/assets` 属主是 root，要 sudo；不要先 `rm -rf`，免得出现资源短暂 404 的窗口。

```bash
cd /home/ubuntu/aisafety-platform-frontend
npm run build
sudo cp dist/index.html /var/www/safety-platform/index.html
sudo cp -r dist/assets/. /var/www/safety-platform/assets/
```

## 5. 验收步骤

1. 发一句带地址的隐患，例：`三明万达广场东南角那个消防栓已经生锈了，已经过了使用年限，而且还出不了水`
2. 出现完整报告 + 建任务卡片 → 点「确认建单」
3. 期望：正文只显示 `✅ 已创建隐患任务`（**没有编号**），下方出现「查看工单 #HAZ-N」按钮
4. 点按钮 → 跳 `/hazard/N` 详情页，工单内容与刚才描述一致
5. 不稳定性提醒：规划器偶尔会把同一句话判成别的产物（不出报告/不问建单），这时第 3 步不会出现——换一句话再试即可，不是前端问题