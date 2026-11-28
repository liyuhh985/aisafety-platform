> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Scope Guard Design

## Goal

Add a deterministic scope guard so the hazard assistant does not answer clearly unrelated questions, still handles high-risk emergency messages safely, and keeps domain hazard consultation unchanged.

## Position

The product is a city-safety hazard assistant, not a general chatbot. Its scope is:

- hazard identification and quick judgment;
- regulation and case consultation;
- remediation advice;
- hazard task reporting.

It also allows:

- short greetings and thanks;
- emergency-first guidance for ongoing fire, trapped people, gas leaks, electric shock, or collapse.

## Current Gap

Today the off-topic boundary is mostly prompt-level. The planner is told it is a safety-hazard understanding assistant, but there is no explicit `out_of_scope` action. An unrelated question can therefore fall through to `answer_now` and be answered by the model.

There is also no deterministic emergency bypass before normal planning.

## Design

Add a pure deterministic module:

```python
def decide_scope(plan: dict, user_text: str) -> dict
```

Returned scopes:

```text
hazard
emergency
smalltalk
ambiguous
out_of_scope
```

Add one graph node between understanding and routing:

```text
understand -> scope_guard -> route -> actions
```

The scope guard does not call a model. It uses the planner's structured scope plus deterministic keyword and emergency rules.

## Scope Rules

Highest priority first:

1. Emergency phrases -> `emergency`.
2. Exact greeting/thanks -> `smalltalk`.
3. Planner returned one or more hazard issues -> `hazard`.
4. Text contains precise domain markers -> `hazard`.
5. Planner says `hazard` with confidence >= 0.7 -> `hazard`.
6. Ambiguous phrases such as `我有个问题` -> `ambiguous`.
7. Otherwise -> `out_of_scope`.

Precise domain markers must avoid generic false positives. For example, `消防员招聘条件` must not be treated as a hazard merely because it contains `消防`.

## Responses

All scope-guard responses are fixed templates, never model-generated:

### Emergency

> 如果现场正在起火、有人被困、燃气泄漏，或存在触电、坍塌等即时危险，请先确保自身安全并立即拨打 119（火警/救援）或 110。安全后，再描述具体位置和现场情况，我继续帮你判断隐患。

### Ambiguous

> 我主要处理城市安全隐患。你说的情况是否涉及占道、消防、建筑、电气、燃气、施工、电梯或市政设施等现场隐患？

### Out of scope

> 我主要负责城市安全隐患的识别、法规案例查询和隐患上报。你可以描述占道、消防、建筑、电气、燃气、施工、电梯、市政设施等隐患；其他话题我暂时不能提供专业结论。

The out-of-scope response must not answer the unrelated question, even partially.

## Planner Contract

The planner gains:

```json
{
  "scope": "hazard | emergency | smalltalk | ambiguous | out_of_scope",
  "scope_confidence": 0.0
}
```

The planner is a hint. Deterministic emergency and precise-domain rules win over the planner hint.

## Non-Goals

- Do not remove existing hazard planning or policy actions.
- Do not add a general-purpose web search or general knowledge tool.
- Do not use a model-generated refusal.
- Do not change the SSE event types.
- Do not change Java task creation.

## Verification

Tests cover:

- domain hazard text -> `hazard`;
- clear unrelated text -> `out_of_scope`;
- fire/trapped/gas emergency -> `emergency`;
- ambiguous text -> `ambiguous`;
- `消防员招聘条件` -> `out_of_scope`;
- domain report and task offer still work;
- smalltalk fast path still works;
- no retrieval or task creation for scope-guard replies.
