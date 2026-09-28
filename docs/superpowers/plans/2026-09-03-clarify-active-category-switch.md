# 操作文档：clarify 切换 active_category

> 目标：当 `active_category` 的槽已齐、但 `missing` 还有下一个类别的槽时，`clarify` 在选出 `chosen` 后，把 `active_category` / `category_index` 一起切到 `chosen` 所属类别。

## 现状
- `clarify` 会用 `missing[:2]` 兜底问下一个类别，但返回值里没有 `active_category` / `category_index`。
- `route` 只在 `active_category` 为空时设置一次，不会跨轮自动推进。
- 结果：问题可以问到下一个类别，但 `active_category` 名义上仍停在旧类别。

## 变更范围
- 只改：`ai-module/core/assistant_graph.py` 中的 `clarify()`。
- 不改：`route`、`route_decider`、图连线、其他节点、测试文件。

## 执行步骤
1. 在 `clarify()` 中选出 `chosen` 后，从 `chosen[0]` 解析出下一个类别。
2. 如果该类别在 `categories` 中存在，则更新 `active_category` / `category_index`。
3. 把 `_llm_phrase` 的上下文从旧 `active` 改为更新后的类别。
4. `clarify()` 返回值新增 `active_category` / `category_index`。
5. 若 `chosen` 为空或类别不在 `categories` 中，保持原值不变。

## 验证
1. `python -c "import ast; ..."` 检查 `assistant_graph.py` 语法。
2. `from core.assistant_graph import build_graph` 检查导入。
3. 运行：`python -m pytest tests/test_multi_hazard.py tests/test_adaptive_slots.py -q`。
4. 行为抽查：构造 `missing=["占道_blocked"]`、`active_category="消防通道"` 的状态并调用 `clarify`，确认返回把 `active_category` 切到 `占道`。

## 回滚
- 若验证失败，用 `git checkout -- ai-module/core/assistant_graph.py` 回滚本次源码改动。
