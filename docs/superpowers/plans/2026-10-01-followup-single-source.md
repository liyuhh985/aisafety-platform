# Plan：追问单一出处 + 判否清锁 + 越界回滚

依据：`docs/superpowers/specs/2026-10-01-followup-single-source-design.md`（决策 1–8）

**总原则**：每个阶段结束都必须 **全量 pytest 绿**（唯一例外：既有失败
`tests/test_server_upload_validation.py`）。**先加新东西、最后删旧东西** ——
`clarification_question` 一次删会同时打红 44 处测试断言，必须放到最后。

**当前基线**：805 passed / 1 failed（既有）/ 3 skipped。

---

## 阶段 1：state 契约（只加不删）

> 为什么排第一：`core/langgraph_state.py` 是真契约 —— 未声明的键会被 LangGraph **静默丢弃**
> （`AssistantGraphState` 的 docstring 已实测记过）。后面的阶段都要往新字段里写，所以先开。

- [ ] 1. `core/langgraph_state.py` 新增两个字段：
      `question_target: str`（唯一写问句的节点用它自报"问的是哪个槽"）、
      `facts_snapshot: dict`（本轮之前的事实快照，供越界回滚）
- [ ] 2. 写失败测试：照 `tests/test_graph_state_persistence.py` 的写法，跑两轮真图，
      断言这两个字段**跨轮存活**（未声明的键会在这一步红）
- [ ] 3. 跑全量，确认绿

## 阶段 2：越界撤销本轮锁定（决策 7）

- [ ] 4. 写失败测试（打到 `scope_guard`）：构造"已锁定一条隐患"的会话，再说一句越界的话，
      断言 `locked_major` / `locked_subcategory` / `categories` / `issues` / `category_slots`
      与本轮之前**逐字相同**
- [ ] 5. 写失败测试（**回归**，修既有 bug）：同上场景，断言已积累的槽位**没有被清空**
      —— 现在规划器不给 `issues` 时 `focus` 会被重建成 `slots: {}`（`core/assistant_graph.py:547`），
      随后 `category_slots[code] = {}` 覆盖旧值（`:560`）
- [ ] 6. `begin_turn` 写 `facts_snapshot`（本轮之前的事实）
- [ ] 7. `scope_guard` 判 `ambiguous` / `out_of_scope` 时按快照回滚
- [ ] 8. 跑全量，确认绿

## 阶段 3：纯回答节点自给自足（决策 5 前半）

- [ ] 9. 写失败测试：纯回答节点**自己调一次模型**产出正文（不再读 `plan["answer"]`），
      且产出**不含任何问句**（纯回答不追问）
- [ ] 10. 改 `answer_reply`：调一次模型，产出 `{answer, is_hazard}`；`is_hazard` 先只写日志
- [ ] 11. 跑全量，确认绿
      （注意：这一步**不改**规划器契约 —— 规划器还在给 `answer`，只是没人在这一条路径上读了）

## 阶段 4：判否即清锁（决策 6）

- [ ] 12. 写失败测试：模型返回"不是隐患" → `locked_major`、`locked_subcategory`、`categories`、
      `issues`、`missing`、`category_slots`、`category_results` **七个字段全清**
- [ ] 13. 写失败测试（反方向）：模型返回"是隐患" → state **逐字未变**
- [ ] 14. 在纯回答节点里实现：`is_hazard` 为真 → 不改 state；为假 → 清那七个字段。
      同时留一行日志（`judge_negative_cleared ...`），只为线上可查、可统计判否率
- [ ] 15. 跑全量，确认绿

## 阶段 5：写问句收成一个节点（决策 1 / 2 / 3 / 8）

- [ ] 16. 写失败测试：规划器提示词里**没有** `question` / `question_target` / `answer`
      （断言提示词内容，照 `tests/test_planner_missing_contract.py` 的写法）
- [ ] 17. 写失败测试：`dialogue_policy` 不再调用 `_question_for_missing`
- [ ] 18. 改 `dialogue_policy`：判据从"模型有没有写问句"改成 `missing` 非空 + 风险等级
- [ ] 19. 改规划器契约（`core/dialogue_understanding.py`）：去掉 `question` / `question_target` / `answer`；
      同步改 `_planner_system_prompt()` 与 `parse_plan()`
- [ ] 20. 把"写问句"收进"初步判断 + 追问"节点：一次调用产出 `{body, question, question_target}`，
      **自己交付**（不再经过 `clarification_question` 中转）
- [ ] 21. 删 `preliminary_question_tail`（`core/assistant_graph.py:1515` 起）与报告路径的
      `question_limiter(1)`（`:1887`、`:1916`）
- [ ] 22. 删 `resolve_slot_question` 的第二级（`understand` 自带问句，`core/dialogue_understanding.py:475`）
- [ ] 23. 改 `_issue_blocks` 的 `[仍缺信息]` 后半句（`core/assistant_graph.py:1457-1458`）：
      "（这一项由本轮末尾的那一个追问承载）" → "（**这一项缺了，正文不要展开**）"
- [ ] 24. 流式节奏按**直接流**落地（铺垫先流，问句随后单独流，不攒整篇），
      并保持 `"".join(chunks) == draft_report` 不变式
- [ ] 25. 跑全量，确认绿

## 阶段 6：删废弃 state 字段（最后做）

- [ ] 26. 删 `question_source`：生产 1 处真读者（`core/assistant_graph.py:641`）+
      **13 处测试断言**（3 个文件，其中 `tests/test_slot_question_observability.py` 整个文件为它而写，
      要评估是改还是退役）+ **2 个测量脚本共 5 处**
- [ ] 27. 删 `clarification_question`：生产 5 处 + **44 处测试断言**（10 个文件）+
      **18 处测量脚本**（8 个文件）
- [ ] 28. 删 `optional_question`（纯回答不追问之后这个概念消失）
- [ ] 29. 跑全量，确认绿

## 阶段 7：部署与线上验证

- [ ] 30. 备份 → 上传 → `compileall` + `import server` 校验 → 重启 8000 → 健康检查
      （流程照 `docs/deployment/AI_DEPLOYMENT_INDEX.md`）
- [ ] 31. 线上冒烟三条：
      - **纯回答路径**：问"X 算不算隐患" → 得到一个判断、**没有问句**；
        紧接着问"那 Y 呢"（换一个东西）→ **正常回答 Y**（不是越界通知）
      - **判否清锁**：问一个明显不是隐患的东西 → 再问一个真隐患（跨大类）→ 不再被挡
      - **越界回滚**：一段真隐患对话中途插一句越界的话 → 回到原话题 → 事实还在
- [ ] 32. 把 spec 的状态从"待评审"改成"已执行"，并把线上实测结果写回 spec §6

---

## 待办（本计划外，已登记不要忘）

- 越界路径的**模板**本身不动（`boundary_reply` 仍是固定文本）—— 只改"回滚"这一处
- 紧急应答 / 寒暄两条路径**完全不动**
- 不上 `interrupt`、不把追问做成暂停点（spec §8）
- JEV 决策模型：登记为"待评估"，不开工作项（spec 外，见会话记录）
