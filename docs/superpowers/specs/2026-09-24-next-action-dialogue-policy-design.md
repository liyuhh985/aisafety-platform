# Next-Action Dialogue Policy Design

## Goal

Replace the rigid `missing -> clarify` rule with a deterministic next-best-action policy so the safety assistant behaves like a domain advisor instead of a form.

The number of questions is not fixed. The policy decides whether to answer, ask one critical question, retrieve, produce a preliminary report, produce a full report, or confirm task creation.

## Problem

The current graph treats missing critical slots as the primary trigger:

```text
understand -> route -> clarify/search/report
```

This creates three bad modes:

- short user input can produce a shallow report;
- one-question-only can still feel mechanical;
- fixed clarification rounds do not adapt to user intent or risk.

The missing facts are useful evidence, but they must not directly decide the next response.

## Design

Add one deterministic policy layer between semantic understanding and graph actions:

```text
understand
  -> policy (next best action)
  -> answer | ask_critical_question | retrieve/report | confirm_task
```

Allowed actions:

```text
answer_now
answer_with_optional_question
ask_critical_question
retrieve
report_preliminary
report_full
confirm_task
```

Policy inputs:

- `intent`
- `risk_level`
- issue list and per-issue `missing`
- whether the planner already provided an `answer`
- whether the planner provided a `question`
- explicit user instructions such as `别问了`, `直接查`, `帮我出报告`, `需要`
- current `clarify_count`
- whether at least one issue is fully grounded

Policy output:

```json
{
  "action": "answer_with_optional_question",
  "reason": "low risk and missing fact is not decision-critical",
  "question": "如果方便，再补充一下现场范围。",
  "optional_question": true,
  "needs_search": false,
  "report_mode": "none"
}
```

## Principles

1. Answer before asking when a useful answer is possible.
2. Ask only when the answer materially changes classification, risk, regulation, or remediation.
3. A policy question is optional unless the missing fact changes a high-risk decision.
4. Never ask for a fact the user already provided.
5. Respect explicit instructions such as `别问了`, `直接查`, `直接出报告`.
6. Support two report depths:
   - `preliminary`: says what is known, what is uncertain, and what to verify;
   - `full`: existing three-section report with retrieval evidence.
7. A preliminary report must not invite task creation. A full report may.
8. Multi-hazard issues are evaluated independently; one incomplete issue must not block another complete issue.
9. On planner failure, retain the existing legacy route as fallback.

## Policy Rule Order

Highest priority first:

1. Explicit create confirmation -> `confirm_task`.
2. Small talk -> `answer_now`.
3. Explicit user request to stop questioning -> `report_preliminary` or `answer_now`.
4. Complete grounded issue and report intent -> `report_full` with retrieval.
5. User explicitly asks for regulations/cases/report but facts are incomplete -> `report_preliminary` with retrieval.
6. High-risk issue with a decision-critical missing fact -> `ask_critical_question`.
7. Usable answer plus non-critical missing fact -> `answer_with_optional_question`.
8. Otherwise -> `answer_now` if possible, else `report_preliminary`.

## Additional Edge Cases From Independent Review

- `不需要` / `不用` / `取消` must not be treated as task confirmation.
- A complete issue must still be able to retrieve even if another issue in the same turn is incomplete.
- Per-issue clarification state must not be replaced by one session-wide `clarify_count`.
- Explicit refusal phrases must suppress further questions:
  - `别问了`
  - `不用问了`
  - `直接说怎么办`
  - `就这些，直接给结论`
- `消防设施有点旧` is weaker than `消防栓没水、灭火器过期`; the former may use an optional follow-up, the latter should go to full report.
- When the planner fails, the legacy keyword route remains the fallback.
- The report-offer sentence `建一条隐患任务` is load-bearing for confirmation detection and must not be reworded without updating `_asked_to_create`.
- Preliminary reports must not invite task creation.

## Risk Levels

Initial deterministic risk defaults:

```text
high: fire, building, utility
medium: traffic, municipal, construction, elevator_special
low: environment_other
```

The planner may raise risk but must not lower a deterministic high-risk category.

## Report Modes

`report_full` keeps the current three-section format:

```text
### 一、触犯法规
### 二、安全隐患
### 三、类似案例
```

`report_preliminary` uses:

```text
### 一、初步判断
### 二、仍需确认
### 三、建议动作
```

The preliminary prompt must explicitly forbid fabricated laws, cases, locations, scale, or damage.

## Graph Mapping

```text
answer_now                      -> direct_reply
answer_with_optional_question   -> direct_reply
ask_critical_question           -> direct_reply (answer + one question)
retrieve/report_full            -> search -> report(full)
report_preliminary              -> search -> report(preliminary)
confirm_task                    -> existing task submission branch
```

`clarify` remains only as a legacy fallback when no valid plan exists.

## Non-Goals

- Do not remove LangGraph.
- Do not replace the RAG store or Java task flow.
- Do not add a new model call solely for the policy.
- Do not remove legacy keyword fallback in this phase.

## Verification

Data-driven tests cover:

- short high-risk input;
- short low-risk input;
- explicit `别问了`;
- explicit `直接出报告`;
- complete report request;
- preliminary report;
- full report task offer;
- multi-hazard mixed completeness;
- planner failure fallback.

Integration tests use mocked planner output and must not call external services.
