# AI 助手 SSE 契约（当前真相）

> 状态：current
> 最后核对：2026-11-01
> 事实来源：`safety-web/.../AiController.java`、`AiService.java`、`ai-module/server.py`、`ai-module/core/assistant_graph.py`。
> 前端要求：**只渲染后端推来的事件，不要在前端再写一套状态/文案映射。**

## 一、当前 `assistant/stream` 主链路

```
浏览器  POST /api/ai/assistant/stream
  -> AiController.assistantStream   （生成/回填 session_id，写响应头 X-Session-Id）
  -> AiService.assistantStream      （SseEmitter 300s，转发到 Python）
  -> Python  POST /api/ai/assistant/stream
  -> core/assistant_graph.run_stream_events（LangGraph）
  -> 逐行回传 data:{...}\n\n
  -> Java 逐行透传给浏览器
```

**请求参数**（`multipart/form-data` 或 `application/json`）：

| 参数 | 必填 | 说明 |
|------|------|------|
| `message` | 与 `file` 至少一个 | 用户文本 |
| `session_id` | 否 | 缺省时 Java 生成 UUID 并通过响应头 `X-Session-Id` 返回 |
| `selected_major_code` | 否 | 前端大类提示；**多选就把几个 code 用逗号拼起来**（如 `fire,municipal`）。只在会话**第一次**判定时有效 —— 锁定后再发不再生效（要换大类只能新开对话） |
| `interrupt_reply` | 否 | JSON 字符串，确认卡片的结构化回复 |
| `file` | 否 | 图片（有图走 multipart 分支） |

**关键事实（2026-10-09 修复）**：`X-Session-Id` 必须由 Java 回填给浏览器，否则每轮 `session_id` 为空 → Python 每次新建会话 → LangGraph 的 `interrupt` 闸门永远恢复不了，点「确认建单」会被当成全新闲聊。

## 二、SSE 事件类型

逐帧格式固定为：

```
data: {"type": <kind>, "content": <payload>}\n\n
```

### 助手主链路事件

| type | content | 说明 |
|------|---------|------|
| `status` | string | 节点级进度文案，**带上下文**（如「正在检索「消防通道占用」的法规与案例...」） |
| `taxonomy` | `{selected_major_code, major_mismatch, issues[], locked_major, locked_majors, locked_subcategory, suggested_major_code, immediate_danger, premises_scope}` | 两级分类结果与锁定状态；`issues[]` 一次最多 3 条（同属 `locked_majors`） |
| `chunk` | string | 流式正文：报告 token、回答、追问、确认问句 |
| `interrupt` | `{type, question, issues?, address?, request_id, draft?}` | 结构化中断（确认建单 / 追问地址）；`request_id` 是确认阶段的稳定幂等键；`draft` 是可编辑的工单草稿 |
| `task_accepted` | `{request_id, status}` | 建单已受理，尚未落库；前端轮询状态查询 |
| `done` | `""` | 本轮结束 |
| `error` | string | 错误 |

### 兼容 analyze 链路事件（旧 `/analyze/stream`）

`status` / `vision` / `no_hazard` / `report` / `done` / `error`。

### 状态文案契约

- 数据来源只能是 `status.content`；前端**禁止** node→文案映射。
- 同一轮内**替换**显示，不要追加；`done`/`error` 后清除。
- 上限 24 字，空则显示「处理中...」。
- 禁止营销词（解构 / 深度研判 / 智能研判 / 赋能 / 洞察 / 强大 / 领先）。

## 三、interrupt / 地址 / 地图选点契约

`interrupt` 的 `type` 有两种：

- `confirm_create_task`：报告后询问是否建单。payload 含 `question`、`issues`、`address`（预抽取地址，可能为空）、`request_id` 和 `draft`。
- `ask_address`：用户已同意但无可定位地址，追问具体地址；payload 同样携带 `request_id`。

`draft` 是报告阶段并行生成、并已冻结的建单草稿，字段：

```json
{
  "categoryList": ["fire/fire_water_abnormal"],
  "address": "三明市…XX路XX小区",
  "district": "三明市…",
  "description": "消防栓锈蚀、超期且无法出水",
  "severity": 1,
  "longitude": 117.63,
  "latitude": 26.26,
  "image_file_id": 123
}
```

前端必须用这份草稿渲染预览，而不是自己从 `issues` 拼；用户改哪项就改哪个字段。

**前端回传**：在**同一 `session_id`** 的下一轮请求里带 `interrupt_reply`（JSON 字符串）：

```json
{
  "decision": "confirm",
  "request_id": "req-3f1c…",
  "draft": {
    "categoryList": ["fire/fire_water_abnormal"],
    "address": "三明市…XX路XX小区",
    "district": "三明市…",
    "description": "消防栓锈蚀、超期且无法出水",
    "severity": 1,
    "longitude": 117.63,
    "latitude": 26.26,
    "image_file_id": 123
  }
}
```

- `decision`：`confirm` | `decline`（其他值 → 当作新话题回到 `understand`）。
- `request_id`：**必须原样回传 interrupt 卡片中的值**。这是确认动作的幂等键，不能让前端重新生成；后端会校验它和 checkpoint 中的值一致。
- `draft`：用户确认/修改后的完整草稿；后端按 `categoryList`（必须在 `locked_majors` 内）+ `address` + `severity` + 坐标清洗后提交，**不再重新抽取**。
- `address`：兼容字段；有 `draft` 时以 `draft.address` 为准，`confirm` 且地址仍为空 → 后端回到 `ask_address` 追问。
- `longitude`/`latitude`：兼容字段；坐标系为 GCJ-02，**不要转换**。
- 结构化确认时 `message` 可以为空（`interrupt_reply` 存在即可），后端不会把占位文案写入对话历史。
- 老路径兼容：直接发文本「好的」/「不用了」仍可完成当前会话确认，但无法覆盖“request+outbox 已提交、accepted 响应丢失后重新确认”的窗口。新前端必须回传 `request_id`。

**响应丢失处理（强制）**：前端在用户点击确认前先保存 interrupt 卡片里的 `request_id`。即使 `task_accepted` 没收到，也不能重新生成建单请求；应直接用这个 `request_id` 轮询状态接口。重复确认时，Python 先查已有 request，返回同一个 `requestId` 和当前状态，不会创建第二条 Outbox。

**地址文本清洗（强制）**：Java 拼 JSON 时只转义双引号，地址若含换行/反斜杠会让请求体变形。前端发送前必须把 `address` 里的 `\r\n\\` 替换为空格。

## 四、建任务事件与状态查询

建单链路已收敛为 MQ 唯一路径；后端只发 `task_accepted`。旧 `task_created` 已删除。

### 4.1 `task_accepted`（MQ 模式）

```json
{"type": "task_accepted", "content": {"request_id": "req-3f1c…", "status": "PENDING"}}
```

含义：

- 只表示「**已受理**」——`ai_hazard_create_request` 已写入，**不代表 `tb_hazard` 已落库**。
- 收到后前端显示「创建中」，并用 `request_id` 轮询下面的状态接口。

### 4.2 建单状态查询

```
GET /api/hazard/requests/{requestId}     （Java，需登录 JWT）
  -> 内部代理 Python GET /api/ai/hazard-create/requests/{request_id}
```

响应体：

```json
{
  "requestId": "req-3f1c…",
  "status": "PENDING" | "PUBLISHED" | "SUCCESS" | "FAILED",
  "hazardId": 61,
  "message": "创建成功" | "任务创建中" | "<失败原因>"
}
```

| status | 含义 | 前端行为 |
|--------|------|----------|
| `PENDING` | request + outbox 已写入，还没投递到 MQ | 继续轮询，显示「创建中」 |
| `PUBLISHED` | 已投递到 RabbitMQ | 继续轮询，显示「创建中」 |
| `SUCCESS` | Java 回执：`tb_hazard` 创建成功，`hazardId` 非空 | 显示「查看工单 #HAZ-{hazardId}」，停止轮询 |
| `FAILED` | 最终失败（Relay 超上限 / Java 回执失败 / DLQ） | 显示失败原因，停止轮询 |

- 找不到 `requestId` → HTTP 404（`创建请求不存在`）。
- 轮询节奏（分级，避免长时间高频打库）：

| 区间（页面可见时间） | 间隔 |
|---|---|
| 0~10 秒 | 1 秒 |
| 10~60 秒 | 3 秒 |
| 60 秒~10 分钟 | 30 秒 |
| 超过 10 分钟 | 停止轮询，提示到工单列表查看 |

- 页面切到后台时暂停计时，回到前台立即查一次并继续。
- **轮询失败要容错继续**，不要中断对话；超过 10 分钟仍未终态时保留 `requestId`，刷新页面后重新开始轮询。
- 不要用 `PENDING/PUBLISHED` 去猜「肯定成功」；终态只有 `SUCCESS` / `FAILED`。

### 4.3 `task_created`（已删除）

旧同步链路删除后，后端不再发送 `task_created`。前端里若仍保留该分支，只能作为死代码清理，不再作为契约。
- 同时正文只输出 `✅ 已创建隐患任务`（**不再把工单编号写进正文**）。
- 旧同步链路删除的条件见 `docs/current/ai-hazard-create-mq.md`。

### 4.4 前端处理规则（MQ 唯一路径）

1. 收到 `task_accepted` → 记录 `request_id` + 轮询（4.2）。
2. 不解析正文里的编号；工单入口只由轮询 `SUCCESS` 后的状态接口驱动。

> 当前状态：MQ 是唯一路径；云端前端已合入 `task_accepted` + 轮询，且已完成人工浏览器验收。

## 五、旧兼容接口附录

以下接口仍在代码中，但**不是当前主链路**，前端新功能不要依赖。
注意：下面前两行是 Java 路由（`AiController` 有转发）；`/api/ai/chat*` **只在 Python 侧存在**，Java 没有对应路由，浏览器按现行分层调不到。

| 接口 | 状态 | 说明 |
|------|------|------|
| `POST /api/ai/analyze` | 兼容 | 非流式图片分析，调试用 |
| `POST /api/ai/analyze/stream` | 兼容 | 旧图片分析 SSE（`vision`/`report`/…） |
| `POST /api/ai/chat` | 兼容 | 非流式追问（**仅 Python**） |
| `POST /api/ai/chat/stream` | 兼容 | 流式追问（**仅 Python**） |
| `GET /api/ai/history` | 保留 | 会话历史 |
| `DELETE /api/ai/session` | 保留 | 清会话 |

Python 内部：`POST /api/ai/internal/vectors/delete`（向量删除，Java outbox 调用）、`GET /api/ai/hazard-create/requests/{request_id}`（建单状态，Java 代理）。

## 六、断连取消与错误处理

- Java `SseEmitter` 300s 超时；`onCompletion` / `onTimeout` / `onError` → 取消 → 关闭上游流，Python `CancellationToken` 停止检索/生成。
- Python 侧每轮检查 `request.is_disconnected()`，断开即取消。
- `error` 事件承载异常文本；前端应结束当轮并在 `done`/`error` 后清除状态文案。
- 检索超时/取消会向上传播，不静默返回半截依据。

## 七、前端对接校验清单

1. 从响应头拿 `X-Session-Id` 并在后续轮次带回。
2. 只渲染 `status.content`；`done`/`error` 清除。
3. `interrupt` 渲染确认卡片（可改地址 + 地图选点），`interrupt_reply` 按第三节回传。
4. `task_accepted` → 轮询 `GET /api/hazard/requests/{requestId}` 到 `SUCCESS`/`FAILED`；`task_created` 已删除。
5. 真正在跑的文件是 `src/views/HomeView.vue`；`src/components/AiAssistant.vue` 已于 2026-10-11 物理删除（不要再引用）。
6. 前端已收口：`src/utils/request.js`（统一注入 Bearer + 401 拦截）、`src/api/{auth,hazard}.js`（业务接口分层）、`src/constants/hazardStatus.js`（五态文案/样式字典，视图里不再硬编码状态数字）。
