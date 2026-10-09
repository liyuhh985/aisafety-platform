# 前端需求：助手「建单」这条链路的三个改动（已按后端就绪的契约写死）

日期：2026-10-09　后端：已完成并上线　前端：待改（`src/views/HomeView.vue`，另见文末“别改错文件”）

要改三处，都在同一个文件、同一张建单卡片附近：
| # | 改什么 | 依赖的后端能力 |
| --- | --- | --- |
| 1 | 建单成功后显示「查看工单」按钮 | `task_created` 事件（已上线） |
| 2 | `ask_address`（追问地址）卡片按类型分流 | `interrupt` 事件的 `type` 字段（已有） |
| 3 | 确认卡片回显位置 + 可改 + 地图选点 | `confirm_create_task` payload 的 `address` 字段 + 请求的 `interrupt_reply` 字段（已上线） |

---

## 一、契约总表（后端已就绪，可直接对接）

**后端 → 前端（SSE，经 Java/nginx 转发后 `data:` 后没有空格，现有解析已兼容）**

```json
{"type": "task_created", "content": {"hazard_id": 67, "hazard_code": "#HAZ-67"}}
{"type": "interrupt", "content": {"type": "confirm_create_task", "question": "需要我帮你在系统建一条隐患任务吗？", "issues": [...], "address": "三明市三明万达广场东南角"}}
{"type": "interrupt", "content": {"type": "ask_address", "question": "请提供具体地址（如 XX 市 XX 区 XX 路 XX 小区或明显地标），我好帮你定位并创建隐患任务。"}}
```

- `address` 可能是**空串**：表示后端没从对话里抽出可定位的地址（例：用户只说「楼道里的消防栓生锈了」）。这种情况不要显示“位置：”。
- `task_created` 事件**可能不出现**（后端拿不到工单 id 时只发正文 `✅ 已创建隐患任务`），所以按钮是“可能出现”的，别假设一定有。
- 同一轮里**先**发正文 chunk、**再**发事件；前端代码要能容忍顺序颠倒。

**前端 → 后端（请求新增可选字段 `interrupt_reply`，JSON 字符串）**

```
POST /api/ai/assistant/stream   （FormData 或 JSON 都行）
  message=         <照旧：用户在对话里说的那句话 / 按钮文案>
  session_id=      <照旧>
  interrupt_reply= {"decision":"confirm","address":"三明市梅列区东新四路万达广场","longitude":117.638919,"latitude":26.263455}
```

- `decision` ∈ `confirm` / `decline` / `other`；**不传 `interrupt_reply` 时行为与现在完全一样**（后端回落成对 `message` 文本的分类）。
- `address` 非空 → 覆盖后端预抽取的地址（**这就是“用户改地址”的通道**）。
- `longitude` 与 `latitude` **都给**才生效（直接采用，跳过地理编码）；只给一个 → 后端忽略。
- `interrupt_reply` 只在「确认卡片」这条路上有意义；`ask_address` 相位的回复仍然是**纯文本地址**（直接当 `message` 发）。

---

## 二、改动 1：建单成功后的「查看工单」入口

### 2.1 消费事件（SSE 循环里，`event.type === 'interrupt'` 那一支之后，当前约 765-774 行）

```js
} else if (event.type === 'task_created') {
  // 后端建单成功：把工单信息挂在当前这条助手消息上，渲染「查看工单」按钮
  const t = event.content || {}
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.taskCreated = t
  } else {
    messages.value.push({ role: 'assistant', content: '', taskCreated: t })  // 顺序兜底
  }
  saveChatCache()
  scrollToBottom()
}
```

### 2.2 渲染按钮（每条消息模板里、确认卡片（约 220-243 行）之后）

```vue
<!-- 建单成功后的「查看工单」入口（消费 task_created 事件） -->
<div v-if="msg.taskCreated" class="task-created-row">
  <button type="button" class="task-created-btn"
          @click="router.push(`/hazard/${msg.taskCreated.hazard_id}`)">
    <span>查看工单</span>
    <span class="task-created-code num-font">{{ msg.taskCreated.hazard_code }}</span>
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  </button>
</div>
```

`router` 已存在（419/424 行）；路由 `/hazard/:id` 已存在且带 `requiresAuth`。不想要 `#HAZ-67` 小标签就删掉那个 span。

---

## 三、改动 2：`ask_address` 卡片按类型分流

现在两种中断都渲染成「✓ 好的，立即建单 / ✕ 不用了」两个按钮。`ask_address` 时点“确认建单”会把 `好的` 当地址发回去 → 后端只能**再问一次地址**（实测死循环）。改成：

```vue
<div v-if="msg.interrupt.type === 'ask_address'" class="interrupt-hint-row">
  <span class="interrupt-hint">请在下方输入框里写出具体地址后发送，例如：XX 市 XX 区 XX 路 XX 小区 / XX 地标。</span>
</div>
<div v-else class="interrupt-actions"><!-- 原来两个按钮 --></div>
```

并在 `executeStreamChat` 开头（`if (analyzing.value) return` 之后）补一行，让用户用输入框回应时收起旧卡片（`interruptHandled` 现在只有点按钮才会置位）：

```js
messages.value.forEach((m) => { if (m.interrupt) m.interruptHandled = true })
```

**这一相位不需要 `interrupt_reply`**：用户在输入框里打的地址会作为普通 `message` 发过去，后端按纯文本当地址用。

---

## 四、改动 3：确认卡片回显位置 + 可改 + 地图选点（本轮重点）

### 4.1 三态显示

```vue
<div v-if="msg.interrupt.type === 'confirm_create_task'" class="interrupt-address-row">
  <template v-if="msg.interrupt.address">
    <span class="addr-label">📍 位置：</span>
    <span class="addr-text">{{ msg.interrupt.address }}</span>
    <button type="button" class="addr-edit-btn" @click="openLocationEditor(msg)">修改</button>
  </template>
  <template v-else>
    <span class="addr-label">📍 未识别到位置，请补充：</span>
    <input v-model="msg.locationDraft" class="addr-input" placeholder="XX 市 XX 区 XX 路 XX 小区 / 明显地标" />
    <button type="button" class="addr-edit-btn" @click="openLocationEditor(msg)">在地图上选点</button>
  </template>
</div>
```

（`msg.locationDraft = msg.interrupt.address || ''`、`msg.locationPick = null` 要在收到 `interrupt` 事件时初始化。）

### 4.2 点「确认建单」时带上结构化回复

```js
async function respondTaskGate(msg, decision) {
  if (analyzing.value) return            // 与 handleInterruptAction 同款守卫
  msg.interruptHandled = true
  const addr = (msg.locationDraft || msg.interrupt.address || '').replace(/[\r\n\\]/g, ' ').trim()
  const pick = msg.locationPick          // {lng, lat} 或 null
  const reply = { decision }             // 'confirm' | 'decline'
  if (decision === 'confirm') {
    if (addr) reply.address = addr
    if (pick && pick.lng != null && pick.lat != null) {
      reply.longitude = pick.lng
      reply.latitude = pick.lat
    }
  }
  const text = decision === 'confirm'
    ? (addr ? `好的，位置：${addr}` : '好的')
    : '不用了'
  await executeStreamChat(text, null, null, false, JSON.stringify(reply))
}
```

需要给 `executeStreamChat` 加第 5 个参数 `interruptReply`，并在它拼 FormData 处加一行（`fd.append('session_id', sessionId)` 附近）：

```js
if (interruptReply) fd.append('interrupt_reply', interruptReply)
```

两个按钮改成 `@click="respondTaskGate(msg, 'confirm')"` / `respondTaskGate(msg, 'decline')`。

> 为什么地址文本要做一次清洗：Java 那层拼 JSON 时对字段只转义双引号，地址里若带换行或反斜杠会让请求体变形，所以发送前统一换成空格。

### 4.3 地图选点弹窗（高德 SDK 前端已经在用）

- 复用 `MapPage.vue:462` 的 `loadAMap()` 写法（`window._AMapSecurityConfig` 已在 `index.html` 配好）。**script src 的 plugin 参数追加** `,AMap.AutoComplete,AMap.PlaceSearch`。
- 弹窗里：输入框驱动 `AutoComplete`（`input: '地址'`），选中或回车用 `PlaceSearch.search(keyword)` 出结果列表；点某一条：
  - `msg.locationDraft = poi.name`（或 `${poi.address}${poi.name}`，二选一，别拼太长）
  - `msg.locationPick = { lng: poi.location.lng, lat: poi.location.lat }`
  - 关掉弹窗，卡片上显示已改的地址
- 不接地图时的降级：只让用户改文本（4.1 的输入框），`interrupt_reply` 里只带 `address`，后端照旧做地理编码。
- 坐标是 **GCJ-02 火星坐标**，和你们地图页同一套，**不要做坐标系转换**。
- 选中后建议在地图上放个 marker 让用户确认（可选，不作为验收项）。

---

## 五、构建发布

`/var/www/safety-platform/assets` 属主是 root，要 sudo；不要先 `rm -rf`，免得出现资源短暂 404 的窗口。

```bash
cd /home/ubuntu/aisafety-platform-frontend
npm run build
sudo cp dist/index.html /var/www/safety-platform/index.html
sudo cp -r dist/assets/. /var/www/safety-platform/assets/
```

## 六、验收步骤

1. **回显**：发 `三明万达广场东南角那个消防栓已经生锈了，已经过了使用年限，而且还出不了水` → 报告 + 卡片显示 `📍 位置：三明市…`
2. **改地址**：把位置改成别的、点「确认建单」→ 回复 `✅ 已创建隐患任务` + 出现「查看工单 #HAZ-N」→ 点进详情页，**地址是改后的那个**
3. **选点**：发 `楼道里的消防栓生锈了，已经出不了水`（故意不带可定位位置）→ 卡片显示「未识别到位置」→ 用地图选点选一个 → 确认 → 详情页**有地址且地图上有坐标**
4. **追问回归**：同上一句，若卡片上没有可用位置而直接点确认 → 后端回到「请提供具体地址…」追问；在输入框里打字给地址 → 建单成功
5. **老路径回归**：不点卡片、直接打字说 `好的` → 行为与以前一致（后端回落文本分类）
6. 提醒：规划器偶尔把同一句话判成别的产物（不出报告/不问建单），这时第 1 步的卡片不会出现——换一句再试，不是前端问题

## 七、别改错文件

`src/components/AiAssistant.vue` **全项目没有任何地方 import，是死代码**，真正在跑的是 `src/views/HomeView.vue`。