# 阶段 3 + 3b 设计：报告交付进历史 + 初步报告「一次调用产出判断 + 依据 + 一个追问」

日期：2026-09-27
范围：`ai-module/core/assistant_graph.py`、`ai-module/core/stream_guard.py`（评测侧新增 `eval_increment.py`、`db/measure_increment_turns.py`）

## 1. 为什么这两件事必须一起做（3b 是硬前置）

核实到的断链：

| 位置 | 事实 |
| --- | --- |
| `core/langgraph_state.py` | `draft_report: str` 字段 |
| `core/assistant_graph.py` 的 `report` 节点 | 两处写入 `draft_report` |
| 全项目 | **没有任何地方读它** |
| `report` 节点 | **没有往 `messages` 追加 AIMessage**（`answer_reply` 等都会追加） |

后果不是「重复」这么轻：模型看不见上一轮引了哪些法条、下了什么结论，于是第 2 轮可能**引不同法条、给不一致结论** —— 同一段对话对同一件事给出两套分析。这解释了多轮对话为什么显得「没在听我说话」。

所以顺序不能反：**先让它看到（把报告并进 `messages`），再要求它只输出增量**。

要区分两件事：
- **措辞重复**（同一内容同样的话）→ 换说法能解决；
- **内容重复**（同一份分析换个说法又讲一遍）→ 换说法**不能**解决，只能靠「只输出增量」这个产物结构要求。

## 2. 断链怎么修

`report` 节点两条路径（初步 / 完整）统一走 `_deliver_report(state, body, offer_task)`：
把交付给用户的正文**同时**写进 `messages`（`AIMessage`）与 `draft_report`。
`messages` 是归宿（`build_planner_messages` 会把最近 12 条里的 assistant 轮次读进规划器请求）；
`draft_report` 保留为本轮交付正文的记录（既有测试与可观测性读它，因此不删）。

安全性核对：`uncertainty._latest_user_text` 只认 `HumanMessage`/`role in (None, "user")`，
`_source_text` 同理 —— 追加 assistant 消息**不会**污染 `danger_veto` 与接地判定。

## 3. 初步报告走 (b)：一次调用产出「判断 + 依据 + 追问」

统一原则：**代码管「必须包含什么」，模型管「怎么说」，代码核对「有没有包含」** —— 与 `emergency_guidance` 同一形状。

- 必含三块：① 初步判断 ② 缺失信息 ③ **一个指向 A 类缺失槽的追问**
- 提示词要求「整段话最多只能有一个问句」，并带上**只输出增量**的指令（初步/完整两档都带）
- **至多一个问句**由 `stream_guard.question_limiter(1)` 在流上按句计数保证：
  第一个问句保留，之后的问句**只去问号、不丢整句**（报告里「仍需确认」那段是内容）
- **必含③**由代码兜底：模型一个字都没问 → 补上该小类缺的那个 A 类槽的固定问句
  （与 `ask_slot_question` 的三级降级同一形状），并留 `logger.info`（不静默）
- 三块的核对 `preliminary_coverage()` 是**弱层次**（词面标记）：只用于（a）决定要不要补问句，
  （b）把「齐不齐」变成可测可观测；**不用来改写正文**

## 4. 诚实的边界（写进代码注释，不假装能兜住）

| 能不能兜 | 内容 |
| --- | --- |
| **能兜** | 报告里「三块在不在」（词面标记）、「问句数 ≤ 1」（句级计数）、「A 类缺失为空就不补问句」 |
| **兜不住** | 内容是否与上一轮**实质重复** —— 没有客观判据 |
| **兜不住** | 「必含③」里的问句是否**真的问在缺的那个槽上** —— 需语义判定 |

实测证据（`db/eval_increment_turns.txt`）：第 2 轮把同一份分析换个说法重讲时，
整篇重合度 0.162、逐句重复率 0.00 —— **两个客观指标都抓不住内容重复**。
所以那部分只靠提示词 + 人工抽查。

## 5. 硬约束与验收

1. **危险路径不追问**：危险走 `emergency_guidance`，压根不进 `search`/`report`（既有测试 + 新增端到端测试）
2. **一轮最多一个问句**：`question_limiter(1)` + 测试（模型问 3 个 → 交付文本恰好 1 个，内容不丢）
3. **`report_full` 不带追问**：合并只影响 `preliminary` 一档；完整报告路径不拼追问，提示词也禁止提问
4. **验收**：`report` 之后 `messages` 里能看到那份报告；两轮对话里第 2 轮的规划器请求含第 1 轮报告正文；
   重合度/法规对照落盘（`db/eval_increment_turns.txt`）

## 6. 已知缺口（决策 2 之后已关闭）

- **完整报告路径没有代码级问号过滤**。为保住「完整报告仍是逐 token 流」
  （`tests/test_stream_guard.py::test_full_report_stays_on_the_previous_token_stream` 锁着），
  这条路径只做到「不拼追问 + 提示词禁止提问」。**实测甲臂（反事实）的完整报告里仍然出现过追问**，
  说明提示词不是 100% 保证。要强保证需要：在 token 粒度上剥掉问号（改动 `stream_guard`），
  或把完整报告也纳入逐句执行器（代价：流式粒度变粗，且要改那条既有断言）。**留给决策。**

## 7. 追加决策（2026-09-27，用户拍板）

### 决策 1：旧不变式「初步报告零问号」作废（改述，不是搬位置）

`tests/test_stream_guard.py::test_preliminary_report_chunks_never_contain_a_question_mark`
锁的是阶段 3a 的「初步报告任何 chunk 都不含问号」，而决策 (b) 要求初步报告**必须含一个追问** ——
这是结构性冲突，不是「机制搬走」。

- 旧不变式：**零问号** → 作废
- 新不变式：**至多一个问句**，上限之外多出来的问句**只去问号、不丢整句**
- 测试改述为 `test_report_chunks_carry_at_most_one_question`，**初步 / 完整两个产物参数化共用**
- docstring 里写明旧不变式作废及原因

### 决策 2：完整报告也走逐句执行器（同一套机制），问号上限同样是 1

- 不采用「token 粒度只剥问号」：那是第二套机制、只管问号，以后必然分叉
- **关键修正**：完整报告不是零问句，而是**至多一个** —— 材料里有 `report_missing`（A+B 类），
  可能合法地列出一条 B 类开放问题。这样两个产物是**真的同一套规则**
- 提示词同步改：完整档从「不要提出任何问题」改成「最多只能提一个问句」
- 连带作废的不变式：`tests/test_stream_guard.py::test_full_report_stays_on_the_previous_token_stream`
  （锁「完整报告逐 token」）→ 改述为 `test_full_report_streams_sentence_by_sentence_and_keeps_headings`：
  **逐句流式、三段式标题原样保留、任意 chunk 拼接 == 落库文本、首块不必等整篇**
- 两条路径的 prefix 发送也统一走 `_emit_chunk`（顺手删掉只服务旧路径的 `writer` 局部变量）

### 真实模型冒烟（本机，完整报告档）

输入「楼下消防通道堆了大量纸箱和旧家具，堆了半年多了，人都得侧身过，帮我查法规和案例」：

| 项 | 值 |
| --- | --- |
| `report_mode` | `full` |
| chunk 数 | **46**（逐句，不再是「一个 token 一块」） |
| 拼接 == 落库 | **True** |
| 三段式标题 | `### 一、` / `### 二、` / `### 三、` **全部保留** |
| 问号数 | **1** —— 「请问堆放纸箱和旧家具的是业主个人还是商铺/物业？」（责任归属，B 类开放信息，符合「至多一个」） |
| 正文进 `messages` | **True** |

### 决定 2 引出的**新**冲突（未获批，未改动）

同一行为（完整报告逐 token）还有两条既有断言锁着，**不在批准范围内**，因此**原样保留（当前红）**：

| 测试 | 断言 | 建议改述 |
| --- | --- | --- |
| `tests/test_hazard_flow.py::test_report_writes_custom_chunks`（114 行） | `sent == [{"chunk": "## "}, {"chunk": "占道"}, {"chunk": "被堵"}]` | `assert sent == [{"chunk": "## 占道被堵"}]`；`assert "".join(item["chunk"] for item in sent) == up["draft_report"]` |
| `tests/test_hazard_flow.py::test_bridge_custom_chunk_from_report`（151 行） | `len([c for c in chunks if c in ("#", "报告", "正文")]) == 3` | `assert "".join(chunks).count("报告正文") == 1`（保证正文仍走 custom 流且内容完整） |

**已于批准后改述到位**：

- `test_report_writes_custom_chunks`：`assert sent == [{"chunk": "## 占道被堵"}]`
  ＋ `assert "".join(item["chunk"] for item in sent) == up["draft_report"]`
  （`draft_report == "## 占道被堵"` 那半条**仍然成立**，塌的只是「逐 token」那一半）
- `test_bridge_custom_chunk_from_report`：`assert "".join(chunks).count("报告正文") == 1`
  （保证正文仍**只经 custom 流**到达前端、内容完整不重复）

### 爆炸半径提醒（本次改动最重要的教训）

为了让「完整报告也走逐句执行器」，一共动了 **5 条**断言：

| # | 文件 | 断言（旧 → 新） | 属于 |
| --- | --- | --- | --- |
| 1 | `tests/test_stream_guard.py` | `test_preliminary_report_chunks_never_contain_a_question_mark` → `test_report_chunks_carry_at_most_one_question`（参数化，含完整档） | 决策 1 |
| 2 | `tests/test_stream_guard.py` | `test_full_report_stays_on_the_previous_token_stream` → `test_full_report_streams_sentence_by_sentence_and_keeps_headings` | 决策 2 |
| 3 | `tests/test_hazard_flow.py` | `test_report_writes_custom_chunks` | 决策 2 |
| 4 | `tests/test_hazard_flow.py` | `test_bridge_custom_chunk_from_report` | 决策 2 |
| 5 | `tests/test_preliminary_increment.py` | `test_full_report_gets_no_question_tail`（零问句）→ `test_full_report_has_the_same_question_rule_as_preliminary` + 拆出 `test_full_report_does_not_append_the_slot_question` | 决策 2 |

**「逐 token 流式」这个属性此前被 3 个文件分别锁着**（`test_stream_guard.py`、`test_hazard_flow.py`，以及本轮的 `test_preliminary_increment.py`） —— 属性保护得好（好事），
但也意味着**改流式粒度的爆炸半径很大**。

> **规矩：以后要改流式粒度，先搜全仓哪些断言锁了它**，再决定改哪几条、怎么改述；
> 不要按「我以为只有一条」去动手。
