# Verifiable Uncertainty Gating Design

## Goal

Make the assistant behave correctly when it is *not sure*, by gating on signals that code can verify - not on the model's self-reported confidence.

Three things become true after this change:

- the assistant never asks the user a form question while something dangerous is happening;
- it never produces a full report or offers to file a work order on facts it invented;
- when the planner fails, it degrades in a way the user can act on instead of going silent or refusing.

## Position

This is the "managing uncertainty" capability for the project: **the model decides what something is, code decides what to do, and a third layer decides whether to trust the model's classification this time.**

## Evidence (measured on the deployed service, `mimo-v2.6-flash`)

### The two failures that motivated this work

| Input | Model output | Why it is wrong |
|---|---|---|
| 楼上火烧起来了，好几个人在里面 | `fire_equipment_fault`, `missing=[facility_type, condition]`, confidence 0.95 | an active fire read as an equipment fault; the policy then asks about facility details |
| 楼道里全是浓烟，人都出不来 | `fire_lane_blocked`, slots `{blocker: 浓烟, impact: 人员无法从楼道疏散, persistence: 持续中}`, `missing=[]`, confidence 0.45 | `持续中` was invented, which emptied `missing` and produced a **full** report with no 119 anywhere |

### Why the two originally chosen signals are not enough

- **Slot grounding** does not fire on the first case: every critical slot was empty, so there is no value to ground.
- **`major_mismatch`** does not fire on either case: it only exists when the front end sent a `selected_major_code`, and free-text turns never do.
- Slot grounding *does* fire on the second case, but only because of the invented `持续中`; it does not address the missing 119.

So a third signal is required: **a code-side danger lexicon that vetoes the action**, not a classifier.

### Self-reported confidence is not usable as the gate

Across four probes the wrong classifications scored 0.95 and 0.45, and correct ones scored 0.95 and 0.96. It does not track correctness. It is still worth recording as a secondary, non-gating signal.

### Grounding rule, validated on 12 measured slot/source pairs

`grounded = digits preserved AND (any 2-gram of the value appears in the source OR character coverage >= 0.6)`

| value | source | verdict | coverage |
|---|---|---|---|
| 占用 / 长期 / 完全堵死 | 盲道被机动车长期占用，完全堵死 | grounded | 1.00 |
| 小区外墙广告牌（严重锈蚀） | 某小区外墙广告牌严重锈蚀、随时可能掉落 | grounded | 1.00 |
| 下方人行道 | 下面就是人行道 | grounded | 0.80 |
| 随时可能掉落，行人通行受影响 | 广告牌严重锈蚀、随时可能掉落 | grounded | 0.67 |
| 箱体破损、水带缺失 | 消防栓箱体破损、水带缺失 | grounded | 1.00 |
| 浓烟 | 楼道里全是浓烟 | grounded | 1.00 |
| 人员无法从楼道疏散 | 楼道里全是浓烟，人都出不来 | grounded | 0.44 (2-gram 楼道) |
| **持续中** | 楼道里全是浓烟，人都出不来 | **strong** | 0.00 |
| **杂物** | 楼下消火栓坏了算隐患吗 | **strong** | 0.00 |
| **长期堆放** | 楼下消火栓坏了算隐患吗 | **strong** | 0.00 |
| **3人被困** | 楼上着火了 | **strong** (digit) | n/a |
| **2层以上** | 楼道里全是浓烟 | **strong** (digit) | n/a |

12 of 12 behave as intended. Note the two-tier threshold: coverage >= 0.6 is `grounded`, 0.34..0.6 is `weak` (a tolerated paraphrase, e.g. 消火栓 vs the user's 消防栓, coverage 0.67), below 0.34 is `strong`. Only `strong` is actionable. The thresholds err toward "grounded", because a false "ungrounded" would degrade a good turn, while a miss only keeps today's behaviour.

## Design

### New module: `core/uncertainty.py`

Pure and deterministic, no model call:

```python
def normalize_text(value: str) -> str
def slot_status(value: str, source: str) -> str            # "grounded" | "weak" | "strong" | "empty"
def assess(plan: dict, messages: list, vision_summary: str = "") -> dict
```

`assess` returns:

```python
{
  "uncertainty_level": "ok" | "cautious" | "fallback",
  "danger_veto": bool,
  "ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
  "grounding_ratio": float,
  "uncertainty_signals": ["ungrounded_slot:...", "danger_term:浓烟", "major_mismatch:traffic->fire"],
}
```

### Three signals

| signal | source | what it gates |
|---|---|---|
| `ungrounded_slots` (strong only) | code: grounding rule above | **how much we claim** - blocks full report and work-order offer |
| `danger_veto` | code: colloquial danger lexicon | **what action is allowed** - blocks every question |
| `major_mismatch` | planner (already exists) | a human-visible disagreement - escalates to cautious |

The danger lexicon is a *veto list*, not a classifier. Its miss rate no longer matters for the action question, because a miss only returns the turn to normal handling, and its false-positive rate is cheap: a routine hazard input simply loses the right to be asked a question. `紧急` and `马上` are removed (they were false positives on 4 of 4 measured routine inputs - 马上就下雨了, 紧急疏散通道被杂物堵住, 这事很紧急, 紧急出口被堵住了) and replaced with colloquial active-danger phrasing: 火烧起来, 冒烟, 浓烟, 油锅, 煤气味, 人出不来, 下不来, 出不去.

### Effects

1. `danger_veto` true -> `dialogue_policy` forbids `ask_critical_question`; it must select a report action; `direct_reply` and `report` **prepend a fixed guidance sentence in code**, deduped on `119`; `clarification_question` is forced empty so the reply cannot end in a question.
2. `cautious` -> `dialogue_policy` forbids `ask_critical_question` and forces `report_preliminary`; `can_offer_task_creation` already returns `False` for preliminary, so a work order cannot be filed on unverified facts. The reply states its interpretation explicitly.
3. `fallback` (planner failed) -> unchanged minimal behaviour, but `danger_veto` still applies, which fixes the current hole where a missed emergency with a failed planner is answered with the out-of-scope refusal.
4. `major_mismatch` -> recorded, and treated as `cautious`.

### The emergency early return is removed

`understand` currently returns early on emergency keywords with `direct_mode="emergency_reply"`: no retrieval, no report, no task creation, and the whole reply is the template. That is the hijack. It is replaced by `danger_veto`, which restricts the **action** while the turn still runs the normal planner and report path.

## Degradation ladder

| level | trigger | behaviour |
|---|---|---|
| normal | no strong signal | today's flow: question / report / task |
| cautious | any strong ungrounded slot, or `major_mismatch` | no question; preliminary report; states its interpretation; no task offer |
| veto | active-danger term present | no question at all; code-guaranteed guidance first; report or answer follows |
| fallback | planner failed or timed out | keep confirmed facts, say what failed, one minimal action; danger veto still honoured |

Today there are two levels and the second is "answer blandly without retrieval", which reads as the assistant getting dumber. After this change every level has a defined, testable behaviour.

## Where the changes land

| File | Change |
|---|---|
| `ai-module/core/uncertainty.py` | new: signals, grounding rule, danger lexicon, `assess` |
| `ai-module/core/langgraph_state.py` | add `uncertainty_level`, `danger_veto`, `ungrounded_slots`, `grounding_ratio`, `uncertainty_signals` |
| `ai-module/core/assistant_graph.py` | `understand` removes the emergency early return, calls `assess`, and forces `clarification_question=""` under veto; `direct_reply` and `report` prepend the guidance and the interpretation note |
| `ai-module/core/dialogue_policy.py` | `ask_critical_question` forbidden under veto or cautious; reason strings carry the signal |
| `ai-module/core/scope_policy.py` | danger lexicon follows the tightened list; a veto must not be downgraded by the scope guard |

## Acceptance

1. `楼道里全是浓烟，人都出不来` -> reply contains 119, and contains **no** form question; the invented `持续中` is reported as a strong ungrounded slot.
2. `楼上火烧起来了，好几个人在里面` -> `danger_veto` is true, `next_action` is a report action, the reply contains 119 and still contains the model's analysis.
3. `紧急出口被堵住了` -> **no** danger veto (it is a routine hazard report), normal flow, task creation still offered.
4. `马上就要下雨了` -> no veto.
5. Invariant: `danger_veto=True` implies `next_action != "ask_critical_question"` and `clarification_question == ""`.
6. Invariant: `uncertainty_level="cautious"` implies `report_mode != "full"`.
7. The guidance is code-owned: a test asserts 119 appears even when the model output never mentions it.

## Out of scope

- The household / public-space scope boundary (`gas_leak` in a private home). It is a different axis - `scope`, not `certainty` - and is deliberately left for a separate change.
- No new SSE event. The guidance is ordinary reply text; the newly added state fields are internal.
- No extra model call. All three signals are computed from data already present.
- No classifier training.

## Migration notes

- Removing the emergency early return is a prerequisite: while it exists, a keyword hit never reaches the planner, so no signal can be computed.
- `scope_guard` runs after `understand`; it must not turn a vetoed turn into an out-of-scope refusal. The veto pins the scope to `emergency` so the guard passes it through.
- The three changed invariants are covered by existing test files (`test_scope_policy.py`, `test_dialogue_policy.py`), and three of their assertions currently encode the old emergency template behaviour - those get retargeted, not deleted.

## Deviations from this design (as built)

1. **`danger_veto` has two sources, OR-ed.** The design section above lists the danger lexicon as a signal; during implementation it became clear that a code-only veto is just "the lexicon with a new name", and the evidence already showed the lexicon alone misses 5 of 6 colloquial emergencies. So the planner now also returns `immediate_danger` (a new constrained field in `parse_plan` and the planner prompt), and `danger_veto = code term OR planner immediate_danger`. This is what actually closes the recall gap; the lexicon stays as the source that can fire *before* the model answers.

2. **The guidance is emitted immediately, before the planner runs.** After removing the emergency early return, the 119 line would otherwise arrive only after the planner and retrieval (~15s). `understand` now emits it as the first chunk of the turn when the code lexicon fires, which restores the *intent* of the old fast path without the hijack: the safety line does not wait for the model, and the turn still produces retrieval, a report, and a task offer. This is why `guidance_emitted` exists as state.

3. **Guidance de-duplication is asymmetric, deliberately.** `direct_reply` builds the whole answer string before writing, so it de-duplicates on `119`. `report` streams tokens before the full text exists, so it can only guarantee "first and at least once"; a model that also writes 119 will produce two mentions. Recorded as a known, accepted limitation rather than fixed by buffering the report (which would cost real token streaming).

4. **`scope_policy.EMERGENCY_KEYWORDS` now reuses `DANGER_TERMS`.** Two lists for one meaning is how the `紧急` false positive survived: the scope guard treated routine reports as emergencies even after the uncertainty lexicon stopped doing so. `紧急` and `马上` are gone; acceptance cases 3 and 4 confirm the false positive is fixed.

5. **`guidance_emitted` is a per-turn flag and is reset by `begin_turn`.** Otherwise a danger turn would suppress the guidance on every later turn in the same thread.

6. **Grounding thresholds (0.6 grounded / 0.34 weak) are calibrated on 12 measured slot/source pairs.** The `weak` band exists specifically to tolerate domain synonyms: `消火栓` against a user's `消防栓` scores 0.67 coverage, and the thresholds deliberately err toward "grounded" because a false *ungrounded* would degrade a good turn, while a miss only preserves today's behaviour. Calibration on a larger real sample is an open item.

7. **The new invariant caught four existing test fixtures asserting facts the user never stated.** Four tests built a full report and a task offer from slots such as `behavior=摆摊` while the user message was `长期占着盲道完全堵死`, and one asserted the invitation sentence appeared inside the report body. They encoded exactly the bug class this change targets; all were retargeted to internally consistent fixtures, not deleted.

## Measured result (acceptance smoke, deployed)

| case | input | 119 | question | task offer | verdict |
|---|---|---|---|---|---|
| 1 | 楼道里全是浓烟，人都出不来 | first line | none | no (preliminary) | pass |
| 2 | 楼上火烧起来了，好几个人在里面 | first line | none | no (preliminary) | pass |
| 3 | 紧急出口被杂物堵住了，长期堆放 | absent | offer only | yes | pass |
| 4 | 马上就要下雨了，路口的井盖破了 | absent | offer only | yes | pass |

Cases 1 and 2 previously asked the user a question mid-emergency; case 2 previously carried no 119 at all in one measured run. Cases 3 and 4 previously matched the over-broad `紧急` / `马上` terms.
