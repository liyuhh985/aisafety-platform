> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/ai-assistant-sse-contract.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 安全隐患分析平台 — 前端对接 API 文档

## 环境

| 服务 | 地址 |
|------|------|
| Java 后端 | `http://106.53.219.214:8080` |
| Python AI | `http://127.0.0.1:8000` (Java 内部调用) |

> 前端只需要调 Java 的 `/api/ai/*`，Java 内部转发给 Python。

---

## 1. 主干流程：上传图片 → 流式分析报告

### POST /api/ai/analyze/stream

前端上传一张隐患图片，后端返回 SSE 流式报告。

**请求**

```
POST /api/ai/analyze/stream
Content-Type: multipart/form-data

file:    <图片文件, jpg/png/gif/webp>
text:    请分析这张图片中的安全隐患，并生成报告 (可选)
```

**响应**

```
Content-Type: text/event-stream

data: {"type":"vision","content":{"has_hazard":true,"hazard_category":"建筑施工","severity":"高","description":"...","location_hint":"...","rectification":["..."]}}

data: {"type":"retrieval","content":"=== 混合检索结果 === ..."}

data: {"type":"retrieval","content":"=== 政策法规 ==="}

data: {"type":"report","content":"##"}

data: {"type":"report","content":" 安全隐患"}

data: {"type":"report","content":"分析报告\n\n### 一、隐患概况\n..."}

... (逐 token 推送直到完毕)

data: {"type":"done","content":""}
```

**SSE 事件类型说明**

| type | 说明 | content 格式 |
|------|------|-------------|
| `vision` | 视觉识别结果 | JSON 对象 |
| `retrieval` | 案例检索 / 法规检索 | 字符串 (Markdown) |
| `report` | 报告文本片段 | 字符串 (Markdown 片段，逐 token) |
| `done` | 传输完成 | 空 |

**前端实现（JavaScript）**

```javascript
async function analyzeHazard(file) {
  const form = new FormData();
  form.append('file', file);
  form.append('text', '请分析这张图片中的安全隐患，并生成报告');

  const response = await fetch('/api/ai/analyze/stream', {
    method: 'POST',
    body: form,
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6));
        switch (event.type) {
          case 'vision':
            showVisionResult(event.content);
            break;
          case 'retrieval':
            showRetrievalResult(event.content);
            break;
          case 'report':
            appendReportText(event.content);
            break;
          case 'done':
            finishReport();
            break;
        }
      }
    }
  }
}
```

---

## 2. 追问对话

分析完成后，用户可以在报告下方追问。

### POST /api/ai/chat

**请求**

```
POST /api/ai/chat
Content-Type: application/x-www-form-urlencoded

message=这条整改建议具体怎么执行&sessionId=<从analyze/stream响应头X-Session-Id获取>
```

**响应**

```json
{
  "code": 200,
  "data": {
    "session_id": "abc123",
    "reply": "具体执行步骤如下：1. ..."
  }
}
```

### POST /api/ai/chat/stream

流式版本，格式同 `/analyze/stream`，但只有 `chat` + `done` 两种 type。

---

## 3. 其他接口

### GET /api/ai/health

检查 AI 服务是否就绪。前端可在上传前调用。

```json
{"status":"ok","model":"mimo-v2.5"}
```

### GET /api/ai/history?sessionId=xxx

获取历史对话记录。

### DELETE /api/ai/session?sessionId=xxx

清除会话。

---

## 4. 非流式版本（可选，调试用）

### POST /api/ai/analyze

和 `/stream` 一样的参数，返回普通 JSON（等待完成后再返回，不适合前端直接展示）。

```json
{
  "code": 200,
  "data": {
    "session_id": "abc123",
    "vision": {
      "has_hazard": true,
      "hazard_category": "建筑施工",
      "severity": "高",
      "description": "...",
      "location_hint": "...",
      "rectification": ["..."]
    },
    "report": "## 安全隐患分析报告\n\n### 一、隐患概况\n..."
  }
}
```

---

## 5. 前端建议 UI 流程

```
用户点击"拍照/上传"
      │
      ▼
┌─────────────────────┐
│  预览图片 + 确认按钮  │
└─────────────────────┘
      │ 点击"开始分析"
      ▼
┌─────────────────────┐
│  流式输出区域         │
│  ┌─────────────────┐│
│  │ 🔍 识别结果:      ││ ← vision event
│  │ 建筑施工 / 高     ││
│  ├─────────────────┤│
│  │ 📋 相关案例:      ││ ← retrieval event
│  │ 本溪拆除坍塌...   ││
│  ├─────────────────┤│
│  │ 📝 分析报告:      ││ ← report event (逐字打字效果)
│  │ ## 一、隐患概况  ││
│  │ ...正在生成...   ││
│  └─────────────────┘│
│                      │
│  [追问...] [发送]     │ ← 报告完成后出现
└─────────────────────┘
```

---

## 6. 注意事项

1. **Python 服务依赖**：Java 后端启动前，需先启动 Python AI 服务 `cd ai-module && python server.py`（端口 8000）
2. **SSE 跨域**：已配置 CORS `*`
3. **session_id**：从 `/analyze/stream` 响应头的 `X-Session-Id` 获取，用于后续追问
4. **图片格式**：支持 jpg/png/gif/webp，单张不超过 10MB
5. **超时**：完整分析约 30-60 秒，SSE 连接默认 5 分钟超时
