# 操作文档：meta 待定类别（pending_categories）

> 目标：`meta_clarify` 提问时能点名“旧焦点 + 新候选”；用户回答后，`route` 按 ADD / SWITCH 落子。
> 现状问题：`meta_clarify` 只把 `active_category` 传给 `_llm_phrase`，没有告诉 LLM 新冒出来的候选类别是谁。

## 变更范围（最小）
- `ai-module/core/langgraph_state.py`：新增 `pending_categories: list[str]`；`relationship` 注释补上 `"pending"`。
- `ai-module/core/assistant_graph.py`：
  1. 新增同处/单独回答的关键词判断（`_is_same_place_answer` / `_is_separate_answer`，单独优先，避免“不是一起”被误判）。
  2. `route`：跨轮首次发现新类别（旧清单非空、有新增、无否定）时，只登记 `pending_categories` 并置 `relationship="pending"`，暂不并入 `categories`；有历史待定时，先按用户回答落子（同一处=ADD 并入，单独=SWITCH 切到待定，明确否定=直接修正并清空待定，模糊=保持待定）。
  3. `route_decider`：`pending_categories` 非空时优先走 `meta_clarify`。
  4. `meta_clarify`：把 `active_category` + `pending_categories` 一起拼进 `_llm_phrase` 的上下文；状态仍只写 `relationship="pending"`，不等用户回答不改 `active_category`。
  5. `run_stream_events` 的 `initial` 补 `pending_categories: []`（与其他字段保持一致）。
- `ai-module/tests/test_multi_hazard.py`：新增待定/落子用例；把 `test_route_no_negation_is_add` 改为“跨轮新类别先待定”的新语义。

## 不改
- `clarify` / `search` / `report` / 图连线；`_find_negated` 的匹配规则；抽槽逻辑。

## 验证
1. `python -c "import ast; ..."` 检查 `assistant_graph.py` 语法；`from core.assistant_graph import build_graph` 检查导入。
2. 运行：`python -m pytest tests/test_multi_hazard.py tests/test_adaptive_slots.py -q` 全过。
3. 行为抽查：
   - 旧 `["占道"]` + “消防通道也被杂物堵了” → `pending_categories=["消防通道"]`，`categories` 仍 `["占道"]`，`relationship="pending"`。
   - 待定 `[消防通道]` + “是同一处” → `categories` 合并，待定清空，`relationship="add"`。
   - 待定 `[消防通道]` + “单独一条” → `categories=["消防通道"]`，旧槽清理，`relationship="switch"`。

## 回滚
- `git checkout -- ai-module/core/assistant_graph.py ai-module/core/langgraph_state.py ai-module/tests/test_multi_hazard.py`
