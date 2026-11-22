# 轻量级业务 Agent Skill Harness 设计

> 状态：proposed
> 日期：2026-11-22
> 范围：Python 编排层
> 依赖：`core/hazard_taxonomy.py`、`core/slot_schemas.py`、`core/dialogue_understanding.py`、`core/assistant_graph.py`

## 1. 目标

为城市安全隐患对话增加按八大类加载的轻量级 Skill Harness：

```text
Skill metadata 路由
+ Skill 正文按需加载
+ 领域 SOP 注入
+ active_skills 下游复用
```

具体目标：

1. 启动时只解析 8 个 `SKILL.md` 的 YAML metadata，正文只确认存在但不缓存。
2. 第一轮先确定 `active_skills`，再进入 `understand`。
3. `understand` 只加载当前 1～3 个 Skill 的正文。
4. 多隐患允许最多 3 个 Skill 同时激活。
5. Skill 正文不进入 Redis checkpoint，只持久化 Skill code 和版本。
6. 保留 `allowed_tools` 作为未来扩展契约，但当前不承诺分类工具收敛效果。
7. 不改变 Java、MySQL、SSE、前端接口。

## 2. 非目标

1. 不新增 Agent Runtime。
2. 不改变 Graph 固定拓扑，只增加 Skill 路由与上下文注入。
3. 不让 Skill 决定 A 类完整性、报告类型、建单闸门或工具执行时机。
4. 不向模型 Prompt 注入 YAML frontmatter。
5. 不向用户展示 Skill 正文、证据编号、路由置信度或内部审计信息。
6. 不复制 `slot_schemas.py` 的 A/B/C 分类，代码仍是槽位事实来源。
7. 不在本设计中修复非焦点追问、多隐患报告覆盖等逻辑缺陷；这些属于后续逻辑修复阶段。
8. 当前所有 Skill 共用统一工具目录，不虚构分类工具收益。

## 3. Skill 的定位

本项目中的 Skill 定义为：

> 按隐患大类加载、可版本化、可路由的领域上下文包。

它主要改变模型上下文，不改变 Graph 控制权。

```text
Skill 负责：
    领域 SOP
    法规引用约束
    报告表述约束
    建单注意事项
    工具允许声明（Harness 使用，不进入 Prompt）

代码负责：
    小类合法性
    槽位完整性
    证据校验
    是否追问
    是否检索
    是否完整报告
    是否进入建单闸门
```

## 4. 目录结构

目录直接使用 `hazard_taxonomy.py` 的 8 个 canonical code：

```text
ai-module/skills/
├── README.md
├── traffic/SKILL.md
├── municipal/SKILL.md
├── fire/SKILL.md
├── building/SKILL.md
├── utility/SKILL.md
├── construction/SKILL.md
├── elevator_special/SKILL.md
└── environment_other/SKILL.md
```

不允许另起一套 `fire_safety`、`electrical` 等分类 code，避免 Skill code 与 taxonomy code 双轨。

## 5. SKILL.md 标准结构

### 5.1 YAML frontmatter

```yaml
---
name: fire
category: fire
description: 消防安全隐患，包括消防通道占用、消防设施故障和消防水源异常。
allowed_tools:
  - search_regulation
  - search_cases
routing_keywords:
  - 消防通道
  - 消防设施
  - 消火栓
  - 灭火器
  - 防火门
  - 消防水源
version: "1"
---
```

字段约束：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 必须等于目录名和 canonical major code |
| `category` | 是 | 必须存在于 `HAZARD_TAXONOMY` |
| `description` | 是 | 用于 metadata-only LLM 路由 |
| `allowed_tools` | 否 | 仅 Harness 使用，不注入模型 Prompt |
| `routing_keywords` | 否 | 用于确定性关键词路由；缺失时由 taxonomy 标签补充 |
| `version` | 否 | 用于审计和 checkpoint 兼容排查 |

### 5.2 Markdown 正文建议

```markdown
# 消防安全

## 适用范围

描述本 Skill 覆盖哪些小类和边界。

## 追问 SOP

说明该类隐患应优先确认哪些现场要素。
槽位 key 必须与 `slot_schemas.py` 一致，不在这里重新定义 A/B/C。

## 法规引用约束

说明法规、责任和处罚表述限制。
明确禁止编造条款和金额。

## 报告约束

说明完整报告和初步判断在本领域的差异。

## 建单注意事项

说明描述、严重程度和附加字段的领域要求。

## 危险升级与禁止行为

说明何时必须走应急指引、不得追问或不得普通报告。
```

### 5.3 完整示例：`skills/fire/SKILL.md`

```markdown
---
name: fire
category: fire
description: 消防安全隐患，包括消防通道占用、消防设施故障和消防水源异常。
allowed_tools:
  - search_regulation
  - search_cases
routing_keywords:
  - 消防通道
  - 消防设施
  - 消火栓
  - 灭火器
  - 防火门
  - 消防水源
version: "1"
---

# 消防安全

## 适用范围

覆盖 fire_lane_blocked、fire_equipment_fault、fire_water_abnormal。

## 追问 SOP

- 消防通道占用优先确认 blocker 和 persistence。
- 消防设施故障优先确认 facility_type 和 condition。
- 消防水源异常优先确认水源类型和当前可用状态。
- 每次只问一个 A 类槽位；多隐患时由代码统一组织并列追问。

## 法规引用约束

只使用检索结果中出现的法规和案例。
不得编造条款、处罚金额或责任主体。
正在燃烧、浓烟、人员被困等场景不得走普通报告链路。

## 报告约束

完整报告必须区分现场事实、法规依据和类似案例。
证据不足时不得写成确定性的违法结论。

## 建单注意事项

描述应包含隐患对象、当前状态和影响范围。
不得编造用户未描述的位置、楼层或人员伤亡信息。

## 危险升级与禁止行为

出现明火、浓烟、人员被困、燃气味或爆炸风险时，优先给出应急动作，不继续追问。
```

## 6. YAML 和正文的使用边界

### 模型可见

只允许 Markdown 正文进入模型 Prompt。

### 模型不可见

以下字段只供 Registry、Router、Harness 使用：

```text
name
category
description
allowed_tools
routing_keywords
version
```

原因：

1. `allowed_tools` 不是调用计划，不应让模型误以为拥有工具。
2. YAML 字段进入 Prompt 会增加无关 token。
3. 工具权限由代码层决定，不应通过自然语言提示授予。

## 7. SkillRegistry 设计

### 7.1 启动扫描

启动时只做：

```text
扫描 skills/*/SKILL.md
解析 frontmatter
校验 name/category 一致
校验 category 属于 HAZARD_TAXONOMY
校验 category 不重复
校验 allowed_tools 工具名存在
缓存 metadata + body_path
解析 frontmatter 后不缓存正文内容
```

建议接口：

```python
class SkillRegistry:
    def scan_metadata(self) -> None: ...
    def get_metadata(self, category: str) -> dict: ...
    def load_body(self, category: str) -> str: ...
    def load_section(self, category: str, heading: str) -> str: ...
    def resolve_tools(self, categories: list[str]) -> list[str]: ...
    def metadata_catalog(self) -> list[dict]: ...
```

### 7.2 正文加载

- 运行时按需读取；
- 可按 `(path, mtime)` 缓存；
- 不把正文写入 LangGraph state；
- 不把正文写入 Redis checkpoint；
- 文件变更后可重新读取，不需要重启整个服务。

### 7.3 异常处理

| 情况 | 行为 |
|---|---|
| YAML 无法解析 | 启动失败，明确报文件路径 |
| category 缺失或非法 | 启动失败 |
| 重复 category | 启动失败 |
| allowed_tools 工具名不存在 | 启动失败 |
| 正文为空 | 启动失败 |
| 单份正文超过 token 预算 | 启动 warning，记录路径和长度 |
| 运行时读取失败 | 记录 error，当前轮降级为无 Skill 基础 Prompt |

## 8. Skill 路由

### 8.1 路由优先级

```text
1. 会话已锁定 locked_majors
2. 前端显式 selected_major_codes
3. 视觉结果明确大类
4. taxonomy 标签和 routing_keywords 高置信匹配
5. metadata-only 小模型路由
6. 全部失败 -> active_skills 为空，使用无 Skill 降级路径
```

### 8.2 显式选择规则

- 前端显式选择 1～3 个大类时，作为本会话硬范围。
- `active_skills = selected_major_codes[:3]`。
- 不自动补充未选择大类。
- 文本出现范围外大类时只提示，不扩锁。
- 不选择大类时进入自动路由。

### 8.3 关键词高置信算法

建议词表分为：

```text
小类完整标签      权重 3
强领域别名        权重 3
大类名称          权重 1
泛化词            权重 0，不参与
```

规则：

1. 文本归一化：去标点、空白，全角数字转半角，英文小写。
2. 每个词在单条文本中最多计一次。
3. 单个大类达到 `score >= 3` 且至少命中一个强领域词，视为高置信候选。
4. 多候选时，每个候选都必须达到 `score >= 3` 且至少命中一个强领域词。
5. 候选数量最多 3 个；超过 3 个时不视为高置信，进入 LLM 路由或要求用户显式选择。
6. 命中越界短语时取消候选，例如“消防员招聘”“燃气费缴费”。
7. 不满足高置信条件时，调用 metadata-only 小模型路由。

### 8.4 metadata-only LLM 路由

模型只接收：

```json
[
  {"category": "fire", "description": "消防安全隐患……"},
  {"category": "utility", "description": "电气与燃气隐患……"}
]
```

输出：

```json
{
  "active_skills": ["fire", "utility"],
  "confidence": 0.86
}
```

约束：

- 输出必须是 canonical category；
- 最多 3 个；
- 低置信度不得激活 Skill；
- 路由结果记录 `skill_route_source=llm`；
- 路由模型不读取 Skill 正文。

### 8.5 路由状态

持久化：

```python
active_skills: list[str]
locked_majors: list[str]
skill_route_source: str       # locked | frontend | vision | keyword | llm | fallback
skill_route_confidence: float
skill_versions: dict[str, str]
```

不持久化：

```python
skill_bodies
skill_prompt_text
```

## 9. LangGraph 接入

### 9.1 节点位置

正确主流程：

```text
begin_turn
  -> skill_route
  -> understand
  -> scope_guard
  -> route
  -> ...下游节点
```

不能再出现主路径：

```text
understand -> load_skills -> route
```

因为该路径下 Skill 正文无法参与当前轮 `understand`。

### 9.2 `skill_route` 节点

职责：

```text
读取 metadata
决定 active_skills
复用已锁定的 locked_majors
写入 skill_route_source / confidence / versions
不加载正文
不调用任何工具
```

### 9.3 `understand` 节点

职责：

```text
读取 active_skills
从 Registry 按需加载正文
组装规划器 Prompt
调用规划器
输出 issues / locked_majors / slots / missing
```

正文仅在函数内部使用，不返回为 state 通道。

### 9.4 `plan_retrieval` 节点

职责：

```text
读取 active_skills
从 Registry 获取 allowed_tools 元数据
与当前阶段允许工具取交集
只发出允许的检索 Send
```

当前所有 Skill 工具相同，因此该交集不会产生分类差异。

### 9.5 `report` 节点

职责：

```text
读取 active_skills
按需加载正文中的报告约束片段
与 issue blocks、检索结果一起组装报告 Prompt
不把 Skill 正文写进最终报告
```

### 9.6 `task_gate` 和 `submit_task`

Skill 不决定是否建单。

建单仍由：

```text
A 类完整性
+ 任务参数校验
+ interrupt 用户确认
+ 幂等键
```

控制。

## 10. 多隐患处理

```python
active_skills = locked_majors
issues = 当前活跃隐患，最多 3 条
```

规则：

1. 最多 3 个大类。
2. 最多 3 条活跃隐患。
3. 同一大类可以有多个小类，但总 issues 不超过 3。
4. 不新增 `focus_skill`。
5. 不因为 Skill 激活而自动创建隐患。
6. `issues[0]` 最多作为展示顺序和报告排序，不参与完整性判断。
7. 多隐患时，每条隐患问一个 A 类槽位，可由代码组织并列追问。
8. 单隐患时一轮只问一个 A 类槽位。

## 11. 前端多选契约

前端允许：

- 自动判断：传空值；
- 显式选择 1～3 个大类；
- 多个 code 使用英文逗号拼接。

示例：

```javascript
const majorCode = selectedMajorCodes.value.slice(0, 3).join(',')
if (majorCode) {
  fd.append('selected_major_code', majorCode)
}
```

约束：

- 不允许超过 3 个；
- 锁定后只读；
- 切换大类需要新会话；
- Java 和 Python 现有逗号字符串接口可复用，不新增 Java 字段；
- 自动判断时由后端路由确定 `active_skills`。

## 12. 工具白名单设计

### 12.1 原则

```text
allowed_tools 是 Harness 元数据
不是工具实现
不是工具调用计划
不是模型 Prompt 内容
```

### 12.2 当前状态

当前工具：

```text
search_regulation
search_cases
analyze_image
```

当前主 LangGraph 实际使用：

```text
search_regulation
search_cases
```

图片分析在进入 LangGraph 前完成，因此当前 Skill 不声明 `analyze_image`。

建议当前 Skill 统一声明：

```yaml
allowed_tools:
  - search_regulation
  - search_cases
```

该声明当前不产生分类差异，只作为未来分类工具扩展契约。

### 12.3 未来生效方式

```python
effective_tools = (
    allowed_by_active_skills
    & allowed_by_current_phase
    & eligible_by_input_precondition
)
```

示例：

```text
skill_route     -> 无工具
understand      -> 无工具
retrieve        -> search_regulation + search_cases
image_analysis  -> analyze_image
report          -> 无工具
```

只有未来出现分类工具时，Skill 白名单才会产生独立收敛收益。

## 13. Prompt 组装

`understand` 的 Prompt 建议结构：

```text
【基础规则】
代码校验优先于模型输出……

【激活 Skill 正文】
fire body
utility body

【当前 active 小类 Schema】
只列出 active majors 下的小类和槽位

【全部大类索引】
只给 code + label，用于发现漏路由大类，不给正文

【当前会话事实】
issues / slots / missing / evidence status

【本轮任务契约】
抽取 issues、槽位、evidence、question 等
```

不得加入：

```text
YAML frontmatter
allowed_tools 文本
version 文本
完整 8 大类正文
```

## 14. 漏路由兜底

如果 `understand` 发现文本明显属于未激活大类：

1. 输出 `suggested_major_code`；
2. 不自动把该大类加入当前 active_skills；
3. 前端提示用户新开会话或重新选择；
4. 记录路由漏召回日志；
5. 将样本加入路由评估集。

## 15. 测试设计

新增测试建议：

```text
tests/test_skill_registry.py
tests/test_skill_routing.py
tests/test_skill_prompt_assembly.py
tests/test_skill_graph_integration.py
```

至少覆盖：

1. 扫描 8 个 Skill metadata。
2. category 重复/非法导致启动失败。
3. allowed_tools 不存在导致启动失败。
4. 启动扫描只保留 metadata，不缓存正文内容。
5. `load_body()` 按需读取并缓存。
6. 会话锁定后不重新路由。
7. 前端多选转为 1～3 个 active_skills。
8. 关键词单大类高置信。
9. 关键词多隐患高置信。
10. 弱匹配进入 LLM 路由。
11. 越界短语不激活 Skill。
12. LLM 路由最多返回 3 个大类。
13. `understand` Prompt 只包含 active 正文。
14. `understand` Prompt 不包含 YAML 和 allowed_tools。
15. Redis checkpoint 只保存 Skill code/version，不保存正文。
16. 多隐患最多 3 条 issues。
17. 单隐患只产生一个追问。
18. 多隐患可产生并列追问。
19. SSE 不出现 Skill 正文和路由内部信息。
20. Skill 缺失或读取失败时回退到基础 Prompt。

现有回归测试必须通过，包括：

```text
tests/test_graph_state_persistence.py
tests/test_task_gate_interrupt.py
tests/test_uncertainty.py
tests/test_uncertainty_gating.py
tests/test_multi_hazard_followup.py
tests/test_report_sections.py
```

## 16. 验收标准

1. 启动时只解析 metadata，不缓存正文内容。
2. 第一轮先路由 active_skills，再进入 understand。
3. understand 只注入当前 1～3 个 Skill 正文。
4. Skill 正文不进入 checkpoint。
5. YAML 和 allowed_tools 不进入模型 Prompt。
6. 当前工具白名单不产生虚假的分类收敛声明。
7. 单隐患一轮只问一个 A 类槽位。
8. 多隐患可并列追问，最多 3 条。
9. 报告链路不会被 Skill 绕过。
10. Java、MySQL、SSE、前端 API 契约不变。
11. 路由规则有一组正负样本测试。
12. Skill 读取或路由失败时可降级运行。

## 17. 实施顺序

1. 建立 `skills/` 目录和 8 份模板。
2. 实现 frontmatter 解析和 metadata 扫描。
3. 实现 on-demand body loader。
4. 增加 `active_skills` 等状态字段。
5. 实现关键词评分和 metadata-only LLM 路由。
6. 增加 `skill_route` 节点。
7. 改造 understand 的 Prompt 组装。
8. 在 plan_retrieval 和 report 中复用 active_skills。
9. 增加测试与评估样本。
10. 做真实对话对比：token、延迟、路由命中率、误激活率。

## 18. 风险与取舍

| 风险 | 处理 |
|---|---|
| 关键词路由误判 | 强词阈值、负向上下文、LLM 兜底、评估集 |
| 每轮多一次 LLM 路由 | 前端/视觉/锁定/关键词优先，只低置信度调用 |
| 路由漏掉大类 | 全量大类索引 + suggested_major_code + 日志 |
| Skill 正文过长 | 设 token 预算，报告只加载相关 section |
| 正文写入 checkpoint | 只持久化 active_skills/version |
| YAML 工具名进入 Prompt | frontmatter 与 body 分离 |
| 所有 Skill 使用同一工具 | 明确声明为未来契约，不包装为当前收益 |
| 多隐患上下文膨胀 | active skills 和 issues 都限制为 3 |
| 旧会话无 Skill 状态 | Redis 兼容回退：无 active_skills 时使用基础 Prompt |

## 19. 面试表达

可以这样表述：

> 我们没有把 Skill 做成新的 Agent Runtime，而是做成固定 LangGraph 上的领域上下文治理层。启动时只扫描 metadata，第一轮由前端选择、视觉结果和关键词路由优先确定 active_skills，低置信度时才调用一个 metadata-only 小模型。understand 节点按需加载 1～3 份 Skill 正文，正文不进入 Redis checkpoint。当前法规和案例工具是全类共享的，因此 allowed_tools 只保留为 Harness 扩展契约，不作为当前性能收益宣传。多隐患时所有 active skills 都加载，焦点不再参与完整性判断。

## 20. 后续阶段

本设计不包含：

1. 证据引用式槽位校验的具体实现；
2. 非焦点隐患追问修复；
3. 初步报告重复生成修复；
4. 全部 active issues 的严格 A 类报告门禁；
5. 报告覆盖全部 issues 的 Prompt 改造；
6. 分类专属工具实现。

这些在对应独立设计或实施计划中处理。