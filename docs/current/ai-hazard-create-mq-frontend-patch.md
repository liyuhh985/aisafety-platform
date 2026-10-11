# 前端补丁：AI 建任务 MQ `task_accepted` + 轮询

> 状态：current  
> 适用文件：`/home/ubuntu/aisafety-platform-frontend/src/views/HomeView.vue`  
> 背景：MQ 模式下 Python 只发 `task_accepted`，不再同步发 `task_created`；前端必须轮询状态接口直到 `SUCCESS/FAILED`。
> 2026-10-11：Task 13 已删除旧同步链路，前端里的 `task_created` 分支已成为死代码，可后续清理。

## 1. 事件分支

在现有 SSE `event.type` 链中，删除旧 `task_created` 分支，并新增：

```js
} else if (event.type === 'task_accepted') {
  const t = event.content || {}
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.taskAccepted = t
    last.taskStatus = 'PENDING'
  }
  pollHazardRequest(t.request_id)
}
```

## 2. 轮询函数

```js
async function pollHazardRequest(requestId) {
  if (!requestId) return
  const token = localStorage.getItem('token')
  if (!token) return

  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const resp = await fetch(`/api/hazard/requests/${requestId}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!resp.ok) continue

    const body = await resp.json()
    const data = body.data || {}
    const last = messages.value[messages.value.length - 1]
    if (!last || last.role !== 'assistant') continue

    if (data.status === 'SUCCESS') {
      last.taskStatus = 'SUCCESS'
      last.taskCreated = {
        hazard_id: data.hazardId,
        hazard_code: `#HAZ-${data.hazardId}`
      }
      saveChatCache()
      return
    }

    if (data.status === 'FAILED') {
      last.taskStatus = 'FAILED'
      last.content += `\n\n隐患任务创建失败：${data.message || '请稍后重试'}`
      saveChatCache()
      return
    }
  }

  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.taskStatus = 'FAILED'
    last.content += '\n\n隐患任务创建超时，请在工单列表中确认结果。'
    saveChatCache()
  }
}
```

## 3. 模板状态

在 `interrupt` 卡片和 `taskCreated` 行附近增加：

```vue
<div v-if="msg.taskAccepted && msg.taskStatus === 'PENDING'" class="task-created-row">
  <span>任务创建中，请稍候…</span>
</div>

<div v-if="msg.taskStatus === 'FAILED'" class="task-created-row">
  <span>创建失败，可稍后重试</span>
</div>
```

## 4. 验收

必须验证：

1. 确认建单后先收到 `task_accepted`；
2. UI 显示“任务创建中”；
3. 轮询到 `SUCCESS` 后出现“查看工单”按钮，跳转 `/hazard/{hazardId}`；
4. 轮询到 `FAILED` 时显示错误文案；
5. 旧 `task_created` 分支已无后端事件来源，可在前端清理。

## 5. 注意

- MQ 模式与旧同步模式必须同时兼容。
- `task_accepted` 只代表受理，不代表已落库。
- 轮询请求必须带 JWT。
- 不要改 `.frontend-sync-dist/` 或 `.codex-remote-frontend-edit/` 快照；必须改真正的云端前端源码。
