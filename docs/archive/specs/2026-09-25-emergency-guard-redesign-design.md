> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Emergency Guard Redesign Design

## Goal

Replace the current emergency branch - "keyword match -> hijack the turn with a fixed template" - with a design that cannot hijack a turn, cannot silently miss an urgent message, and can guarantee that safety guidance appears in the reply.

The conversation logic does not otherwise change. `understand` stays the semantic entry point.

## Position

City-safety hazard assistant; users are citizens and grassroots staff. The main path is describing a hazard that already exists. An ongoing emergency is a **rare but high-stakes** input class - which is exactly the case where average model behaviour should not be trusted.

## Evidence

Measured against the deployed model (`mimo-v2.6-flash`), planner and report prompts as they are today.

### 1. "The model will not say 119" is false

With the emergency branch bypassed, the normal report path handles an active fire very well. Actual output for "我家楼上着火了，烟很大，好几个人在里面":

```text
### 三、建议动作
1. 立即拨打119报警，说明地址、楼层、火情及被困人员情况
2. 迅速沿安全通道向下疏散，切勿乘坐电梯
3. 用湿毛巾捂住口鼻，低姿撤离，避免吸入浓烟
```

So "guarantee the 119 sentence" is **not** a good justification for this branch. The model already produces it.

### 2. The real harm is that the pipeline asks a form question

The same input, without the branch, produces:

```text
planner intent  -> report_hazard
planner category-> fire_equipment_fault      # an active fire read as "equipment fault"
missing         -> [facility_type, condition]
policy action   -> ask_critical_question
```

The assistant would therefore ask:

> 具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？

People are trapped upstairs and the system asks whether it is a hydrant, a sprinkler, an alarm or an extinguisher. This is caused by the rule "high risk + missing a critical slot -> ask one question" firing on a life-threatening scene. It has nothing to do with the 119 sentence.

**This is the actual reason the deterministic guard exists: to stop the pipeline from choosing a form-filling action during a life-threatening event.** The model is reliable when *writing the report* and unreliable when *classifying*; the classification result drives a harmful action.

### 3. The 10-keyword list leaks in both directions

`EMERGENCY_KEYWORDS = 着火了 起火 有人被困 燃气泄漏 爆炸 触电 坍塌 救命 马上 紧急`, matched with substring containment (`in text`):

| Input | Verdict |
|---|---|
| 我家楼上着火了，烟很大，好几个人在里面 | caught |
| 楼上火烧起来了，好几个人在里面 | **missed** (people trapped) |
| 楼道里全是浓烟，人都出不来 | **missed** |
| 厨房煤气味道很重，会不会炸 | **missed** (only 爆炸 matches, not 炸) |
| 楼下饭店的油锅烧起来了 | **missed** |
| 有人掉下去了，倒在路边不动了 | **missed** |
| 紧急出口被堵住了 | **false positive** (a routine hazard report) |

5 of 6 real emergencies in colloquial phrasing are missed, while a routine hazard is hijacked. A hand-written list can never be complete; that is a property of the approach, not a matter of writing it better.

## Design

Three layers. Layer 1 does the work; layers 2 and 3 support it.

### Layer 1 - guard the action, not the input (decisive)

Add a state field `immediate_danger: bool` with **two sources, OR-ed together**:

- **code**: the keyword list (model-input time)
- **model**: a new field in the planner's structured output, `immediate_danger`, decided by the model itself

The second source is what closes the 5-of-6 gap; the first covers the case where the model under-reacts.

Then in `dialogue_policy`: **when `immediate_danger` is true, `ask_critical_question` is forbidden.** The policy must fall through to a report action instead (preliminary is fine).

This is the layer that matters, because it blocks the *action* rather than trying to enumerate the *inputs*. Even if the keyword list misses the message entirely, a model that says "this is happening now" still prevents the form question.

Invariant to test:

```python
assert not (state["immediate_danger"] and action == "ask_critical_question")
```

### Layer 2 - guarantee the guidance in code (not by asking the model)

When `immediate_danger` is true, the graph **prepends a fixed guidance sentence to the reply in code**, and the model's normal analysis follows it.

- the sentence comes from code, so its presence is deterministic and testable (`assert "119" in reply`)
- skip prepending if the model output already contains "119", to avoid duplication
- do **not** ask the model to produce it; asking is what makes the guarantee fake

Keeping the model's analysis (rather than replacing the reply) is what stops the turn from being hijacked: retrieval, the report, and task creation all still run.

Giving the model the flag in its prompt is still useful, but only as a tone hint: it stops the model from continuing to probe for details during an emergency. It carries no guarantee.

### Layer 3 - tighten and widen the keyword list (support only)

- remove over-broad words: `紧急`, `马上` (or require them to co-occur with 正在 / 已经 / 马上就要)
- add colloquial variants: 火烧起来, 冒烟, 浓烟, 油锅, 煤气味, 人出不来 / 下不来
- treat this list as a booster for layer 1, never as the primary mechanism

## Where the changes land

| File | Change |
|---|---|
| `ai-module/core/dialogue_understanding.py` | `parse_plan` accepts and constrains `immediate_danger` (bool, default `False`); planner prompt asks for it |
| `ai-module/core/langgraph_state.py` | add `immediate_danger: bool` |
| `ai-module/core/assistant_graph.py` | `understand` no longer early-returns on emergency with `direct_mode="emergency_reply"`; instead it sets `immediate_danger` and continues to the planner |
| `ai-module/core/scope_policy.py` | `EMERGENCY_KEYWORDS` tightened; the emergency branch exposes the fixed guidance text as a value to prepend rather than as a terminal scope |
| `ai-module/core/dialogue_policy.py` | `ask_critical_question` forbidden when `immediate_danger` |
| output assembly (`direct_reply` and `report`) | prepend the fixed guidance, deduped on "119" |

## Out of scope

- No extra model call. The flag rides on the existing planner call.
- No trained classifier. A classifier would be the production answer for the recall question, but it is out of proportion for this project; the model's own `immediate_danger` field is the pragmatic stand-in.
- No front-end change. No new SSE event is introduced; the guidance is ordinary reply text.
- The greeting gate is untouched. It is a pure cost optimisation whose worst failure is one wasted model call, so its keyword list is fine as is.

## Acceptance

1. `楼道里全是浓烟，人都出不来` -> reply contains 119 and evacuation guidance, and contains **no form question**.
2. `紧急出口被堵住了` -> normal hazard flow, full report, task creation still offered.
3. `我家楼上着火了` -> 119 guidance first, the model analysis still present, task creation still offered.
4. Invariant: with `immediate_danger=True`, `next_action` is never `ask_critical_question`.
5. The guidance is prepended by code: a test can assert 119 appears even when the model output does not mention it.

## Migration note

The current `understand` early return makes the emergency path a dead end: no retrieval, no report, no task creation, and the user re-triggers it by repeating the danger word. Removing that early return is required for layers 1 and 2 to work; the fixed guidance text moves from "the whole reply" to "the first sentence of the reply".
