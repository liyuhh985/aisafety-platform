# Single Active Hazard Per Conversation

## Goal

One conversation tracks **one** active hazard. The assistant follows whatever the user is describing now; if the user starts describing a different kind of hazard in the same conversation, the backend switches focus instead of managing two hazards in parallel.

## Position

The business object is already single: Java files **one** hazard record with **one** category, **one** address and **one** handler (`tools/hazard_submit._extract` extracts a single category; `create_hazard` returns a single `hazardId`). The dialogue layer has been treating hazards as a list. That mismatch is the root of most of this project's complexity.

Everything below exists **only** to support a list of hazards, and disappears with this change:

| machinery | why it existed |
|---|---|
| `route` at 210 lines (merge / relocate / negation / pending) | tracking several hazards across turns |
| `pending_categories` + `meta_clarify` + "same place or separate?" | asking the relationship between hazards |
| global `report_mode` downgrading every hazard when one was incomplete | several hazards in one report |
| per-issue report templates and per-issue "to verify" lines | the same |
| the task gate being unable to offer per hazard | submit can only file one |
| the subcategory-set "topic fingerprint" | deciding whether the user was adding a second hazard |
| `Send` fan-out over N hazards | retrieving for several |

The fingerprint is also demonstrably unreliable: in one measured session the planner read the same fire as `fire_lane_blocked` in one turn and `fire_equipment_fault` in the next. Comparing two non-deterministic classifications to drive behaviour was the wrong instrument for an unnecessary question.

## Semantics

### The category is decided once, then locked

- The hazard category is classified **once**: on the first turn that yields a category (not literally turn 1 — a user often opens with "你好" or a vague sentence, and there is nothing to lock then).
- From then on the planner is **not asked to classify**. It only extracts slots for the locked category from what the user just said.
- `state["issues"]` stays a list with 0 or 1 elements, so the `taxonomy` SSE payload, `_issue_blocks` and the front-end contract keep their shape.
- `categories` therefore holds 0 or 1 entries; `category_results` holds one entry.

This removes the entire "classification drifted between turns" failure class. In one measured session the planner read the same fire as `fire_lane_blocked` and then `fire_equipment_fault`; with a lock that cannot happen, and no code has to compare two model outputs to decide anything.

### Slots are still extracted from every turn

The lock applies to the **category**, not to slot extraction. Every turn runs the extractor against the **locked category**, whatever the user's sentence appears to be about. A sentence about something else often still carries a fact about the locked hazard:

- locked category = 消防通道占用; the user says "旁边那栋危房把消防通道也挡了一半" -> `blocker` is filled from it.
- Skipping extraction because "the user is talking about something else" would silently discard that fact.

Because the category never varies, this is a single unconditional rule, and drift detection plays no part in it.

### Drift does not change the lock; a user correction does

The one escape hatch is the user, and it already exists in the planner contract as `intent="correction"`:

- **model drift -> the lock holds.** The category does not change. A one-line notice is prepended (informational, never a question, never blocking). Drift is used *only* to decide whether to show that notice — it never gates extraction:

  ```text
  （本次对话记录的是「<当前类别>」。如果这是另一回事，建议另开一个对话；要改说这个，直接告诉我。）
  ```

- **user correction -> re-lock.** "其实不是消防，是危房" (or, within the picked major, "其实是消防设施坏了") re-classifies and re-locks. The previous category's slots are **left in place** — they are keyed by category code, so they cannot leak into the new category, and keeping them means a correction back does not re-ask for what the user already said. Without a correction path, a wrong first classification would be unrecoverable.

### What happens mechanically on a re-lock

1. **Swap the lock**: `categories` becomes the new subcategory. Old entries stay in `category_slots` (inert).
2. **The normal planner call already covers "fill from history + current message".** It receives the last 12 messages plus this turn, so nothing new is needed to re-read the conversation — the only change is which category's slot questions it is filling.
3. **The anti-force-fit instruction still applies.** Re-reading history introduces a new force-fit surface: a description belonging to the *previous* category ("被杂物长期堵住") must never become the new category's slot (`facility_type=杂物`). The prompt already forbids forcing a value into a slot; the code-side grounding and echo checks remain the backstop.
4. **In-major validation**: the new subcategory must belong to the locked major, or the re-lock is refused (see the front-end bound above).

### What counts as a user correction

A correction is the user saying **"the one you recorded is wrong / not the thing I mean"** — a negation or a revision, as opposed to adding information or mentioning something else:

| user says | correction? | why |
|---|---|---|
| 不是消防通道，是消防设施坏了 | yes | negation plus replacement |
| 我说的是危房 | yes | re-states what they mean |
| 你搞错了，是施工围挡 | yes | names the mistake |
| 其实是消防设施 | yes | revision marker |
| 另外旁边还有一栋危房 | **no** | this is an addition |
| 旁边那栋危房把消防通道也挡了一半 | **no** | this adds a fact about the locked hazard |
| 还有呢 / 但是呢 | **no** | no revision intent |

Markers: **negation** (不是… / 搞错了) and **revision** (其实是 / 我说的是 / 应该算). "另外 / 还有" is an addition, not a correction — that is precisely the case the lock exists to hold, so the prompt has to spell the difference out.

A correction **may cross a subcategory, and it may also cross a major.** Both are allowed, and neither is required — the only question is whether the user is correcting:

- locked on 消防通道占用, "其实是消防设施坏了" -> same major, different subcategory -> re-lock.
- locked on 消防通道占用, "其实不是消防，是危房" -> different major -> re-lock.
- locked on 消防通道占用, "另外旁边还有一栋危房" -> not a correction -> the lock holds.

Requiring a changed *major* would reject the first case and leave the assistant asking the wrong category's slot questions forever; requiring the major to stay the same would reject the second. Neither condition appears in the rule.

Because the two misjudgements are not equally costly, the prompt must be **conservative**: only an explicit negation or revision marker counts as a correction ("另外 / 还有 / 旁边那个" never does). Treating an addition as a correction would swap the category while the user was merely adding detail and would discard already-extracted slots — which is exactly the "you asked about 设施, why are you suddenly talking about 通道" behaviour this design exists to prevent.

Detection uses `intent="correction"`, which already exists in the planner contract. **It is a model judgement, not keyword matching**: the keyword/negation-regex approach this project used to use (`_find_negated`) was deleted precisely because "另外还有一栋危房" and "其实是一栋危房" share their nouns and differ only in intent, which no word list separates. Code does not look for negation words. This is a **reading of what the user said**, not a self-assessment of the model's own certainty — and that distinction is why a model judgement is right here while the self-reported `confidence` field is not usable as a gate (measured: wrong and right classifications both scored 0.95).

The rule in one line: **a user correction is followed; model drift is not.**

Warning: "always extract for the locked category" invites force-fitting — the user says "旁边还有一栋危房" and the model writes `blocker=危房`. That value *is* in the user's own words, so the grounding check cannot catch it; it is the same failure class as the echo-filling bug. The guard belongs in the prompt, not in code:

- the prompt must say: extract only values relevant to the current category, and if the sentence is about a different hazard, do **not** force a value into a slot — just flag the drift.
- code must **not** gain a blunt "reject any other category's label" filter: locked on 消防通道 with "被一辆占道经营的三轮车堵住了", the value `blocker=占道经营` happens to equal another category's label but is the correct answer. Deciding that needs context, which is the model's job.

The primary answer for "I want a different hazard" is still a front-end one — guide the user to start a new conversation. This section is the backend fallback for when they did not see that guidance.

### Re-locking is bounded by the front-end major choice

The front end already lets the user pick a major category up front and sends it as `selected_major_code` (`understand` passes it to the planner, and `major_mismatch` is already reported back in the `taxonomy` event). That explicit choice is a stronger statement of intent than any single sentence, so it bounds re-locks:

| `selected_major_code` | re-lock rule |
|---|---|
| a specific major (the user picked one) | allowed **only** if the corrected category's major equals it |
| empty — the user chose "自动判断" | no bound; re-lock is free |

This also removes most of the risk in the model's correction judgement: a false-positive correction can no longer drag the category outside the scope the user declared. The judgement becomes bounded.

**When a re-lock is refused**: the lock holds, the slots are kept as they are, and a notice explains the two ways out. It is informational — not a question, and it does not block the turn:

```text
（你开始时选择的是「<前端选的大类>」，所以我先按这一类记录。如果这确实属于「<纠正后的大类>」，建议另开一个对话并选择对应大类；如果是「<当前类别>」的问题，直接继续补充就行。）
```

**The bound applies from the first turn, and the major is never re-negotiated.** When the user picked a major, the whole conversation stays inside it:

- turn 1 matches the **closest subcategory inside the picked major**. It does not second-guess the user's declaration and does not leave the major;
- if the message clearly belongs to a **different** major (picked 消防, first message "楼下井盖破了"), the major stays and the **subcategory stays empty**. Nothing is fabricated and the notice gives both ways out:

```text
（你开始时选择的是「消防安全」，但这句话更像是「市政设施」类的问题。如果确实是井盖，建议另开一个对话并选择对应大类；如果你想报的是消防类问题，说说具体情况就行。）
```

- if the message is vague but plausibly in-major, the subcategory also stays empty, but here the assistant **asks** — the category is the single most critical fact and `dialogue_policy` already asks when a critical fact is missing:

```text
具体是哪一类消防隐患？比如通道被占、设施故障还是水源异常？
```

- later turns keep the lock; an explicit correction changes the subcategory **within** the picked major. A correction pointing outside it is refused, with the notice above.

So the major never changes through dialogue at all — only the front end can change it (a new conversation, or a different pick). One rule instead of two: **the front-end choice bounds the whole session, including its first read.**

**Never fabricate a subcategory to satisfy "must be inside the major".** Matching the closest subcategory inside the major is required; *having* a subcategory is not. Picked 消防 with "楼下井盖破了" has three candidates — 消防通道占用 / 消防设施故障 / 消防水源异常 — and the nearest is 消防设施故障, whose slot schema then asks "具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？". The assistant would be asking a manhole reporter which hydrant is broken. That is the same failure class as the echo-filling bug (`structure=危房`), one level up: forcing a category instead of forcing a slot. Leave the subcategory empty and resolve it with a notice or a question.

Consequence for the planner prompt: it must be told "choose a subcategory inside `<major>` only; if the message does not belong to it, return no issue and set `major_mismatch`". Without that instruction the planner will happily return a 井盖 subcategory for a fire-scoped session.

**Cost, accepted deliberately**: a user who picked the wrong major — or who describes a different kind of hazard — is routed to a new conversation instead of being served on the spot. What that buys is complete freedom from cross-turn scope drift. It is also the same rule the front end already teaches the user ("want a different hazard? start a new conversation").

**Contract requirement for the front end**: "自动判断" must be sent as an **empty or absent** `selected_major_code`. A sentinel such as `"auto"` or `"unknown"` would be read as a real major and would wrongly block every re-lock. This line goes into `docs/superpowers/specs/2026-09-25-assistant-sse-interrupt-contract.md`.

### Slot carry-over is unconditional while the lock holds

- Once locked, the same slot schema applies for the rest of the conversation, so per-slot accumulation across turns needs no conditions: "被堵" -> "长期" -> "完全堵死" becomes one complete issue.
- Nothing is decided by comparing schema or category identity, so there is no carry-over rule to get wrong.
- **A re-lock leaves the previous slots in place, and that is deliberate.** Slots are stored per category code (`category_slots = {subcategory_code: {slot_key: value}}`) and `issues` / `missing` are recomputed each turn against the current focus only, so an entry belonging to a previous category can never be read as the new category's slot. It is inert. Keeping it is strictly better: if the user corrects back ("不对，还是消防通道"), what they already told us is still there instead of being asked again.

### Consequence for the planner prompt

Turns after the lock can use a much smaller prompt: no taxonomy, no classification request — just "extract the slots of the current category from this message, and flag `intent=correction` if the user is correcting the category". Cheaper and more deterministic than today's full classification prompt.

### Nothing is lost

The user's own text is still carried into the work order: `_extract` builds `description` from the conversation, so a record for "消防通道被堵" still contains the sentence about the 危房 if the user wrote them together. What is dropped is managing them as separate objects, not the information.

## Notice copy

```text
（本次对话记录的是「<当前类别>」。如果这是另一回事，建议另开一个对话；要改说这个，直接告诉我。）
```

Rendered by `understand`, together with the safety guidance and the cautious note — the same place that already owns "开场白". It is emitted per turn (a per-turn flag, reset by `begin_turn`), unlike the guidance which is per danger episode.

## What is deleted

- multi-issue accumulation in `_merge_persisted_slots`
- `report_mode = "mixed"` and the per-issue template split in `report` / `_REPORT_RULES`
- the coupling that let one incomplete hazard suppress the task invitation for all of them
- the subcategory-set topic fingerprint in `uncertainty.assess` (`topic_changed`) **and** the major comparison — with a locked category there is nothing to compare at all
- cross-turn re-classification: turns after the lock no longer request a category

## What stays

- `Send` parallel retrieval — now a fixed two branches (regulation + case). It is half of the 60s -> 9s improvement.
- grounding and echo-slot checks, danger veto with its two sources, scope guard, the `interrupt` task gate.
- `issues` as a 0/1-element list, so the SSE contract does not change.

## Consequences for three open items

1. **Per-hazard task offers** — no longer a problem. There is one hazard, locked, so the gate is simply "is this one complete". The submit path's inability to target a specific hazard stops mattering, and the extractor cannot pick the wrong one because there is only one to pick.
2. **Report cost / full rewrite** — shrinks with the material. Whether a report is regenerated in full remains a separate product decision.
3. **Topic fingerprint fragility** — gone, as described above.

## Tests

As built:

- **Renamed, not deleted** (their themes were gone but most assertions were still valid): `test_multi_hazard.py` -> `test_hazard_flow.py`; `test_per_issue_report.py` -> `test_report_sections.py`, rewritten around a single-hazard fixture.
- **Deleted (2)**: the `report_mode="mixed"` pair — the mode no longer exists.
- **Retargeted (8)**: the fan-out tests now assert one hazard x two tools; the drift/merge tests now assert the lock holds and a scope notice fires; three tests whose names said "multi"/"mixed" were renamed to match what they actually assert.
- **Added**: `tests/test_hazard_lock.py` (14 tests) covering lock, in-major match, out-of-major notice, the code-generated in-major question, corrections inside and outside the major, the front-end picker change, inert old slots, and `perceived_major`.
- The known pre-existing failure moved with the rename: `test_hazard_flow.py::test_report_writes_custom_chunks`.

Two things live verification changed in the design:

- The `taxonomy` event used to fire only when a hazard was recognised, so the out-of-scope turn produced **no** event and the front end had nothing to render a "switch category" entry from. It now also fires when a lock exists or a major is suggested.
- Deriving "what major does the model actually think this belongs to" from `issues[0].major_code` does not work: when a front-end hint is present the model tends to *comply* with it and label the issue in that major. A dedicated `perceived_major` field was added, and the prompt now requires the model to answer it truthfully even when it organises `issues` to match the hint.
- New:
  - the first turn that yields a category locks it; a turn with no category locks nothing;
  - a later turn describing another hazard does **not** change the category, but its slots **are** extracted for the locked category;
  - that turn prepends the "we are still recording X" notice exactly once, and the notice is not a question;
  - `intent="correction"` re-locks to the new category (including across subcategories inside one major), keeps the previous slots inert under their old code, and prepends no notice;
  - after a re-lock, a fact stated **before** the correction that belongs to the new category is recovered (the planner sees the history), while a fact belonging to the previous category is not forced into the new category's slots;
  - "另外旁边还有一栋危房" does **not** re-lock and does **not** drop slots;
  - with `selected_major_code="fire"`, a correction to `fire_equipment_fault` re-locks, while a correction to `dangerous_building` is refused: the lock holds, the slots are kept, and the refusal notice is emitted;
  - with `selected_major_code=""`, the same correction to `dangerous_building` re-locks freely;
  - picked `fire` with the first message "楼下井盖破了": the major stays `fire`, the **subcategory stays empty**, nothing is fabricated, and the mismatch notice with both ways out is emitted;
  - picked `fire` with a vague but plausibly-fire message: the subcategory stays empty and the assistant **asks** which kind of fire hazard it is;
  - picked `fire` with "消防通道被杂物堵了": the subcategory locks immediately with no notice and no question;
  - the planner prompt carries the "inside `<major>` only, otherwise no issue plus `major_mismatch`" instruction;
  - after the lock, the planner is not asked to classify (assert the prompt carries the locked category);
  - a sentence about another hazard that also carries a fact about the locked hazard fills that slot (the 危房挡消防通道 case);
  - `issues` never exceeds one element after `understand`.
- Keep the existing invariants: `danger_veto` never asks, cautious never produces a full report, guidance appears first.

## Out of scope

- The front-end guidance UI and copy: owned by the front-end model. This document only fixes the backend fallback; the contract note goes into `docs/superpowers/specs/2026-09-25-assistant-sse-interrupt-contract.md`.
- Whether a report is regenerated in full on later turns.
- The durable-checkpointer and old-`Orchestrator` cleanups.
