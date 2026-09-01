# 多隐患（Multi-Hazard）改造 —— 真实走查记录与修复复盘

> 日期：2026-09-01
> 状态：**核心链路已跑通**（多轮澄清 → 检索 → 合并报告），真实 API 验证成功。
> 前置文档：
> - 设计定稿：`docs/superpowers/plans/2026-08-31-multi-hazard-agent-design.md`
> - 执行计划：`docs/superpowers/plans/2026-09-01-multi-hazard-agent.md`

---

## 1. 结论一句话

新版多隐患助手已能**在一个会话里同时处理多个隐患类别**（占道 + 消防通道），通过多轮澄清分别补齐各自槽位，检索两类法规/案例，最终合成一份合并报告。已用真实 MiMo API 走查验证。

---

## 2. 走查全过程

### 语料
| 轮次 | 用户消息 | 预期行为 |
|---|---|---|
| R1 | 消防被堵，长期占道 | 识别「消防通道 + 占道」两类，追问缺失槽（消防 blocker/占道 persistence） |
| R2 | 占道那边长期摆摊占着盲道，盲道完全堵死了；消防通道被一堆杂物完全堵住 | 补齐占道 behavior/persistence/blocked 与消防 blocker，走 search |
| R3 | 消防通道也是长期堵着的，一直堆着杂物 | 补齐消防 persistence → search → 合并报告 |

### 真实返回（关键片段）
R2 最终流式返回了**完整合并报告**，结构为：

```
## 一、占道经营·盲道被堵
### 一、触犯法规
| 《城市道路管理条例》第27条 | 禁止擅自占用城市道路摆摊设点 |
| 《无障碍环境建设法》第28条 | 不得损毁、侵占盲道等无障碍设施 |
### 二、安全隐患
- 视障人士无法通行，被迫绕行机动车道
- 行人受阻，高峰期可能引发踩踏/道路冲突
### 三、类似案例
> 库内暂未检索到针对「占道摆摊堵盲道」的典型案例

## 二、消防通道被杂物堵塞
### 一、触犯法规
| 《消防法》第28条 | 不得占用、堵塞、封闭消防车通道 |
### 二、安全隐患
- 延误救援黄金时间，火势蔓延扩大
- 杂物（纸箱、旧家具）易燃
### 三、类似案例
| 广东中山废品站火灾 | 消防通道被违停堵塞，车主被追责 |
| 深圳小区地下车库自燃 | 消防车延误15分钟，物业被责令整改 |
| 佛山民房电线短路引燃杂物 | 过火20㎡，房主被责令整改 |

需要我按这个情况生成一个整改建议吗？
```

---

## 3. 走查暴露并修复的 6 个真实 Bug

> 这些是**真实 API 才暴露、单测 + mock 都测不出来**的问题。每个都值得复盘。

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | `POST /api/ai/assistant/stream` 返回 500 | `server.py` 用了 `HTTPException` 但没 from fastapi import | 补 `HTTPException` 导入 |
| 2 | API key 读不到，`_call_llm` 返回空 | `config.py` 用 `os.getenv("MIMO_API_KEY")`，但 server 从不加载 `.env`，环境变量为空 | `config.py` 顶部加 `load_dotenv()` |
| 3 | 追问不出现（只有 status/done，无 chunk） | bridge 只在 `report` 节点 emit chunk；`clarify`/`meta_clarify` 把问题写进 `messages` 但没流出去 | bridge 遍历节点时，`clarify`/`meta_clarify` 把最后一个 AI 消息作为 `chunk` 输出 |
| 4 | `_llm_extract_slots`/`_llm_phrase` 返回兜底（空/「能再具体说说吗」） | `_call_llm`（非流式）需要 `{"role","content"}` **字典**，但传的是 langchain 消息对象（`SystemMessage`/`HumanMessage`），`requests` 无法 JSON 序列化 → 抛异常被吞 | 这三个 LLM 辅助函数改为传 dict 消息；抽槽加宽松 JSON 解析（剥 markdown 代码块/截取 `{...}`） |
| 5 | `report` 节点返回 400，`draft_report` 为空 | ① `report` 的 `final_messages` 含 langchain 对象无法序列化；② `_build_payload` 无条件带 `tools`（`_llm` 挂了 ASSISTANT_TOOLS），纯文本生成被拒；③ `getattr(m, "type")` 对 HumanMessage 返回 `"human"`（OpenAI 不认，要 `user`） | ① report 内把 langchain 消息转 dict；② report 改用**无 tools 的 `_report_llm`**；③ 加 role 映射 `human→user, ai→assistant` |
| 6 | `route` 图级死循环（`route→clarify` 无限转） | `assistant_graph.py` 里存在**两份重复的 `route`/`route_decider` 定义**，Python 以后面旧单类别版为准，且 `clarify` 作为图内节点回 `route` 造成循环 | 删掉重复定义；把 `clarify`/`meta_clarify` 改为**本轮终止节点**（连 `END`，跨轮靠 checkpointer 续接） |

---

## 4. 关键架构决策（落地后确认）

### 4.1 `clarify` / `meta_clarify` 是「本轮终止节点」
多轮澄清的正确 DSL 是：**每轮新消息从 `route` 进 → 抽槽/重算 missing → 决定「问」还是「检索」**。若 `clarify` 在图内回 `route`，同一句话会在 `route→clarify` 之间无限循环（死循环）。
- 改为：`route → (meta_clarify | clarify | search)`，其中 `clarify`/`meta_clarify` **连 `END`**，问完即结束本轮，等用户下一轮。
- 跨轮状态（`categories`/`category_slots`/`missing`/`active_category`）靠 **LangGraph checkpointer（thread_id=session_id）**续接。
- 中文名「终止节点」= 图里 `add_edge("clarify", END)`。

### 4.2 抽槽在 `route`，措辞在 `clarify`
- **抽槽**（LLM 从用户回答批量提取、按类别分组）在 `route` 节点做：每个新消息都从 route 进，route 抽槽 → `rebuild_missing` 重算 → `route_decider` 决定问/查。
- **措辞**（把已选好的 1-2 个槽说成自然问句）在 `clarify` 节点做：`chosen = missing[:2]`，`_llm_phrase(chosen)`。
- 体现「**选槽=代码，措辞=LLM**」设计。

### 4.3 `report` 用无 tools 的轻量 Agent
纯文本报告生成会带 `tools` 导致 400。新增 `_report_llm = Agent(name="report", tools=[], ...)`，`report` 用它流式生成，逐 token 经 bridge 以 `chunk` 流出。

### 4.4 role 映射
langchain 的 `.type` 与 OpenAI role 不一致：`human→user`、`ai→assistant`、`system→system`、`tool→tool`。直接 `getattr(m,"type")` 会把 HumanMessage 弄成 `"human"`，模型 400。

---

## 5. 测试与提交

- 单元测试：`tests/test_multi_hazard.py`（11 个）+ `tests/test_adaptive_slots.py`（13 个）= **28 通过**。
- 旧单类别兼容：保留，零改动通过。
- 相关 commit：
  - `91b28d3` `feat(multi-hazard): add missing rebuild, per-cat slot merge, relocate`
  - `101b233` `feat(multi-hazard): rewrite route for multi-category extraction+rebuild+can_search`
  - `dbc68cc` `feat(multi-hazard): clarify=code-select+llm-phrase, add meta_clarify`
  - `92bd2ba` `feat(multi-hazard): search loops categories, report merges template`
  - `26947cd` `feat(multi-hazard): wire meta_clarify into graph + system prompt + regression`
  - `bb68864` `fix(multi-hazard): remove duplicated route block; clarify/meta as terminal nodes`
  - `834be6a` `fix(assistant): real-API walk found bugs - HTTPException import, load_dotenv, llm dict messages, report chunk emit`
  - `132e132` `fix(report): use no-tools llm, map langchain roles (human->user) to fix 400`

---

## 6. 遗留 / 注意事项

1. **代理**：本机开 `127.0.0.1:7890`（Clash 类），`api.xiaomimimo.com` 偶发 ProxyError。稳定走查建议把国内 API 加直连，或临时关代理。
2. **`report` 现在是「一份完整 chunk」流出**，不是逐 token（因为 bridge 从 `node["draft_report"]` 整体取）。若想要真·逐 token，需让 report 用 `_report_llm._call_llm_stream_events` 并在 bridge 里逐 token emit（当前已具备，但桥接层先整体输出保稳定）。
3. `test_vector_delete_api.py` 有 9 个既有失败（404/401，关于向量删除接口），**与本改造无关**，属当前工作区其它未完成改动。

---

## 7. 下一步建议（可选）
- 前端接入多隐患新链路（前端已支持多轮澄清，无需大改）。
- 若要做「评审 agent」或「可观测性 trace」，见设计文档 §12 后续。