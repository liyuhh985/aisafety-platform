> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Day33 前端升级：AI 助手支持发图 + 布局清新化

> 日期：2026-08-28
> 前置：后端已完成图文工具（analyze_image）+ 模型降级（主 mimo-v2.5-pro -> 备 mimo-v2.5），`ASSISTANT_TOOLS` 3 个已验
> 目标：前端助手窗口支持发送图片，布局改为清新自然（轻量，不做重设计），严格按本文执行

## 一、本期要做

### 1. 支持发图
- **交互**：输入框左侧加 📷 按钮 + 隐藏 `<input type="file" accept="image/*">`，选图后在输入区上方显示缩略预览（可移除），Enter/发送 时一起发出
- **接口**：`POST /api/ai/assistant/stream` 已是 JSON，本期让它兼容 `multipart/form-data`（后端小改：有 `file` 就存 `uploads/` 得 `image_path` 并后端写死先调 `analyze_image` 一次，结果塞进历史再进 LLM（保证有图必看），无 `file` 保持原 JSON 链路）
  - 前端：有图用 `FormData {message, session_id, file}`，无图用 JSON（保持现有）
  - 后端：`server.py:assistant_stream` 加 `File(None)` 分支，有图时写死先调 `analyze_image`，结果注入历史再进 LLM，其余检索仍由模型自主决定
- **Java 透传**：`AiService.assistantStream` 已透传 JSON，本期加 `Multipart` 分支（有 file 时用 `LinkedMultiValueMap` + `ByteArrayResource`，复用 `analyzeStream` 的写法）

### 2. 布局清新化（轻量）
- **风格**：去重设计，保留现有功能，改色板为白底 + 浅灰 + 主色 `--color-cyan` 淡化，圆角 12px，阴影淡化，字体 13-14px
- **改动**：
  - `aa-panel` 背景 `#ffffff` / 边框 `rgba(0,0,0,0.06)` / 阴影 `0 8px 24px rgba(0,0,0,0.06)`
  - `aa-bubble` 用户 `#e0f2fe` / 助手 `#f8fafc`，文字 `#334155`，不做渐变
  - 输入区 `aa-input` 白底，`aa-send` 实色主色，无 `btn-glow`
  - 保留 `aa-header` 简洁，仅标题 + 关闭

## 二、本期不做
- 创建工单/权限/MQ、地图/天气、历史分页、Markdown 复杂渲染
- 后端向量库/评估集改动

## 三、文件改动清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `ai-module/server.py` | 修改 | `assistant_stream` 加 `File` 分支，存图得 `image_path` |
| `safety-web/.../AiService.java` | 修改 | `assistantStream` 加 `Multipart` 重载（或同方法内分支） |
| `safety-web/.../AiController.java` | 修改 | `assistantStream` 同时支持 `JSON` 和 `multipart` |
| `frontend/AiAssistant.vue` | 修改 | 加选图/预览/发送逻辑 + 清新样式 |

## 四、验证
1. `py_compile` + `mvn -pl safety-web -am compile`
2. 前端本地：文字 -> 三段式；带图文字 -> 先视觉小结 + 三段式；刷新 -> `loadHistory` 回填
3. 云端 `npm run build` 成功

## 五、风险与回滚
- 风险：`multipart` 兼容保持 JSON 原链路可回退
- 回滚：`git checkout -- ai-module/server.py safety-web/.../AiService.java safety-web/.../AiController.java` + 前端 `.tmp_AiAssistant.vue` 恢复

## 六、执行顺序
1. 后端 `server.py` File 分支 → 2. Java 透传 → 3. 前端选图 + 样式 → 4. 编译 + 联调
