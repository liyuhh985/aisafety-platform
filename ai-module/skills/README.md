# Hazard Skills

每个 canonical 大类对应一份 `SKILL.md`。目录名、`name` 和 `category` 必须等于 `core/hazard_taxonomy.py` 中的 major code。

## 文件契约

- YAML frontmatter 只供 Registry、Router 和 Harness 使用，不进入模型 Prompt。
- `allowed_tools` 是代码层工具白名单元数据，不是工具调用计划，也不进入 Prompt。
- Markdown 正文按需加载；不得写入 LangGraph / Redis checkpoint。
- 正文不得重新定义 A/B/C 槽位分类；`core/slot_schemas.py` 是唯一事实来源。