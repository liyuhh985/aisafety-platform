# Day33 修复：图片多轮追问 + 记忆串联

> 日期：2026-08-28
> 问题：1. 只发图没文字直接三段式，未做多轮追问；2. 第二轮“需要”失忆，回全新问候
> 目标：有图也必问持续性/堵死程度；同 session_id 下历史必串联

## 一、要做

### 1. 图片也必追问
- `core/assistant_agent.py` SYSTEM 加严：有图时即使已有视觉结果，若用户未提“长期/临时、是否完全堵死”，仍追问一次，再检索
- 关键词：先调 `analyze_image` 已写死，后续仍按“缺槽位就问”

### 2. 记忆串联
- `ai-module/server.py` 的 `assistant_stream`：
  - 有图时 `image_path` 存后，`vision` 注入 `history` 的同时立刻 `mem.add_user` + `mem.add_system(vision)` 落库（原来只在 `generate()` 结束才落库，第二轮来得快就读不到）
  - 无图时保持原 `generate()` 内落库，但保证 `get_history()` 取最近 6 条
- 前端 `AiAssistant.vue` 已加 `loadHistory`，刷新不丢；本次不改前端

## 二、不做
- 新增工具/权限/MQ、样式大改

## 三、文件改动
- `ai-module/core/assistant_agent.py`
- `ai-module/server.py`

## 四、验证
1. `py_compile` 全过
2. 只发图+“有啥隐患？” → 追问“长期还是临时？完全堵死吗？”
3. 回“长期完全堵死” → 三段式
4. 再回“需要” → 基于上一轮三段式给整改建议，不失忆
