> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Verifiable Uncertainty Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the assistant's actions on three signals code can verify - ungrounded slot values, a danger-veto lexicon, and `major_mismatch` - so it stops asking questions during an active danger and stops building full reports and work orders on invented facts.

**Architecture:** A new pure module `core/uncertainty.py` computes the signals from data the turn already has (planner plan + user text + vision summary). `understand` calls it and writes the result into graph state; `dialogue_policy` reads those fields to forbid `ask_critical_question`; `direct_reply` and `report` prepend a code-owned guidance sentence. No model call is added.

**Tech Stack:** Python 3.11, LangGraph 1.2.11, pytest, existing SSE bridge.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-25-verifiable-uncertainty-gating-design.md`.
- Do not use the model's self-reported `confidence` as a gate; record it only as a non-gating signal.
- Thresholds are fixed: `coverage >= 0.6` grounded, `0.34 <= coverage < 0.6` weak, `< 0.34` strong. Only `strong` is actionable.
- Never let a false "ungrounded" verdict degrade a good turn: when in doubt, treat a value as grounded.
- `danger_veto` restricts the **action**; it must never suppress retrieval, the report, or task creation outright.
- Do not touch the Java backend. No new SSE event.
- The household / public-space scope boundary is out of scope for this plan.
- Do not `git commit` unless asked.
- If a test fails twice for reasons outside the current task, stop and report instead of iterating.

---

### Task 1: The signals module

**Files:**
- Create: `ai-module/core/uncertainty.py`
- Test: `ai-module/tests/test_uncertainty.py`

**Interfaces:**
- Produces: `normalize_text(value) -> str`; `slot_status(value, source) -> str`; `DANGER_TERMS`; `has_active_danger(text) -> bool`; `assess(plan, messages, vision_summary="") -> dict` with keys `uncertainty_level`, `danger_veto`, `ungrounded_slots`, `grounding_ratio`, `uncertainty_signals`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test**

```python
from core.uncertainty import assess, has_active_danger, normalize_text, slot_status

SMOKE_SOURCE = "楼道里全是浓烟，人都出不来"


def test_normalize_text_strips_punctuation_and_fullsized_digits():
    assert normalize_text("１２号院，楼 道。") == "12号院楼道"


def test_slot_status_grounded_cases():
    assert slot_status("浓烟", SMOKE_SOURCE) == "grounded"
    assert slot_status("占用", "盲道被机动车长期占用") == "grounded"
    assert slot_status("下方人行道", "下面就是人行道") == "grounded"


def test_slot_status_tolerates_a_synonym_as_weak_not_strong():
    # 用户写"消防栓"，模型归一成"消火栓"：只差一个字，不该判成编造
    assert slot_status("消火栓", "消防栓箱体破损") == "weak"


def test_slot_status_flags_invented_values_as_strong():
    assert slot_status("持续中", SMOKE_SOURCE) == "strong"
    assert slot_status("杂物", "楼下消火栓坏了算隐患吗") == "strong"


def test_slot_status_flags_invented_numbers_as_strong():
    assert slot_status("3人被困", "楼上着火了") == "strong"
    assert slot_status("2层以上", SMOKE_SOURCE) == "strong"


def test_slot_status_empty_value():
    assert slot_status("", SMOKE_SOURCE) == "empty"
    assert slot_status(None, SMOKE_SOURCE) == "empty"


def test_has_active_danger_hits_colloquial_phrasing():
    for text in ("楼上火烧起来了，好几个人在里面", "楼道里全是浓烟，人都出不来",
                 "厨房煤气味道很重", "楼下饭店的油锅烧起来了", "人都下不来"):
        assert has_active_danger(text) is True, text


def test_has_active_danger_does_not_fire_on_routine_hazards():
    for text in ("紧急出口被堵住了", "马上就要下雨了", "这事很紧急，帮我看下这个井盖",
                 "紧急疏散通道被杂物堵住，需要尽快清理", "小区外墙广告牌锈蚀"):
        assert has_active_danger(text) is False, text


def test_assess_flags_cautious_on_an_invented_slot():
    plan = {
        "ok": True,
        "issues": [{
            "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "浓烟", "persistence": "持续中"},
        }],
    }
    result = assess(plan, [{"role": "user", "content": SMOKE_SOURCE}])
    assert result["uncertainty_level"] == "cautious"
    assert result["ungrounded_slots"] == ["fire_lane_blocked.persistence=持续中"]
    assert any(sig.startswith("ungrounded_slot:") for sig in result["uncertainty_signals"])


def test_assess_stays_ok_when_every_slot_is_grounded():
    plan = {
        "ok": True,
        "issues": [{
            "subcategory_code": "blind_path_occupied",
            "slots": {"behavior": "占用", "persistence": "长期", "blocked": "完全堵死"},
        }],
    }
    result = assess(plan, [{"role": "user", "content": "盲道被机动车长期占用，完全堵死"}])
    assert result["uncertainty_level"] == "ok"
    assert result["ungrounded_slots"] == []
    assert result["danger_veto"] is False


def test_assess_sets_danger_veto_from_the_user_text():
    plan = {"ok": True, "issues": [{"subcategory_code": "fire_lane_blocked", "slots": {}}]}
    result = assess(plan, [{"role": "user", "content": SMOKE_SOURCE}])
    assert result["danger_veto"] is True
    assert any(sig.startswith("danger_term:") for sig in result["uncertainty_signals"])


def test_assess_treats_major_mismatch_as_cautious():
    plan = {
        "ok": True,
        "major_mismatch": True,
        "selected_major_code": "traffic",
        "issues": [{"subcategory_code": "fire_equipment_fault", "slots": {}}],
    }
    result = assess(plan, [{"role": "user", "content": "消防设施老旧"}])
    assert result["uncertainty_level"] == "cautious"
    assert any(sig.startswith("major_mismatch:") for sig in result["uncertainty_signals"])


def test_assess_includes_vision_summary_in_the_source():
    plan = {
        "ok": True,
        "issues": [{"subcategory_code": "falling_object", "slots": {"source": "外墙广告牌"}}],
    }
    result = assess(plan, [{"role": "user", "content": "你看这张图"}],
                    vision_summary="[视觉分析] 外墙广告牌严重锈蚀")
    assert result["uncertainty_level"] == "ok"


def test_assess_ignores_plans_without_issues():
    result = assess({}, [{"role": "user", "content": "你好"}])
    assert result["uncertainty_level"] == "ok"
    assert result["ungrounded_slots"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_uncertainty.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'core.uncertainty'`.

- [ ] **Step 3: Write the implementation**

```python
"""Deterministic uncertainty signals: what code can verify without asking the model."""
import re

ZERO_WIDTH = "\u3000"
_PUNCT = re.compile(r"[\s，。、；：！？（）()\"'\-—,.!?;:" + ZERO_WIDTH + r"]")
_FULL_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")

GROUNDED_COVERAGE = 0.6
WEAK_COVERAGE = 0.34

DANGER_TERMS = (
    "火烧起来", "起火", "着火了", "着火", "冒烟", "浓烟", "烟很大", "油烟",
    "油锅", "煤气味", "燃气味", "煤气泄漏", "燃气泄漏", "爆炸", "炸了",
    "有人被困", "人被困", "被困", "人出不来", "出不去", "下不来", "被困在里面",
    "触电", "坍塌", "塌了", "救命", "晕倒", "昏迷", "有人掉下去",
)


def normalize_text(value) -> str:
    return _PUNCT.sub("", str(value or "").translate(_FULL_DIGITS))


def _coverage(value: str, source: str) -> float:
    chars = set(value)
    if not chars:
        return 1.0
    return len(chars & set(source)) / len(chars)


def _has_bigram(value: str, source: str) -> bool:
    if len(value) < 2:
        return value in source
    return any(value[i:i + 2] in source for i in range(len(value) - 1))


def _digits_preserved(value: str, source: str) -> bool:
    return all(digit in source for digit in re.findall(r"\d+", value))


def slot_status(value, source: str) -> str:
    """grounded | weak | strong | empty.

    阈值刻意偏松：把好值误判成"编造"会让好回合降级，而漏判只是维持现状。
    """
    normalized = normalize_text(value)
    if not normalized:
        return "empty"
    normalized_source = normalize_text(source)
    if not _digits_preserved(normalized, normalized_source):
        return "strong"
    if _has_bigram(normalized, normalized_source):
        return "grounded"
    coverage = _coverage(normalized, normalized_source)
    if coverage >= GROUNDED_COVERAGE:
        return "grounded"
    if coverage >= WEAK_COVERAGE:
        return "weak"
    return "strong"


def has_active_danger(text) -> bool:
    """这里只做动作否决，不做分类，所以宁可漏、不可误杀常规隐患上报。"""
    value = normalize_text(text)
    return any(normalize_text(term) in value for term in DANGER_TERMS)


def _source_text(messages, vision_summary: str) -> str:
    parts = []
    for message in messages or []:
        role = (message or {}).get("role")
        if role in (None, "user"):
            parts.append(str((message or {}).get("content") or ""))
    if vision_summary:
        parts.append(str(vision_summary))
    return " ".join(parts)


def assess(plan: dict, messages: list, vision_summary: str = "") -> dict:
    plan = plan if isinstance(plan, dict) else {}
    source = _source_text(messages, vision_summary)
    signals = []
    ungrounded = []
    slots_total = 0
    slots_grounded = 0

    for issue in plan.get("issues") or []:
        code = issue.get("subcategory_code") or ""
        for key, value in (issue.get("slots") or {}).items():
            status = slot_status(value, source)
            if status == "empty":
                continue
            slots_total += 1
            if status == "grounded":
                slots_grounded += 1
            elif status == "strong":
                ungrounded.append(f"{code}.{key}={value}")
                signals.append(f"ungrounded_slot:{code}.{key}={value}")

    if plan.get("major_mismatch"):
        signals.append(
            "major_mismatch:%s->%s" % (
                plan.get("selected_major_code") or "?",
                ",".join(i.get("major_code") or "" for i in plan.get("issues") or []),
            )
        )

    danger_term = ""
    raw_source = _source_text(messages, vision_summary)
    normalized_source = normalize_text(raw_source)
    for term in DANGER_TERMS:
        if normalize_text(term) in normalized_source:
            danger_term = term
            break
    if danger_term:
        signals.append(f"danger_term:{danger_term}")

    cautions = bool(ungrounded) or bool(plan.get("major_mismatch"))
    return {
        "uncertainty_level": "cautious" if cautions else "ok",
        "danger_veto": bool(danger_term),
        "ungrounded_slots": ungrounded,
        "grounding_ratio": (slots_grounded / slots_total) if slots_total else 1.0,
        "uncertainty_signals": signals,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ai-module; python -m pytest tests/test_uncertainty.py -q`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/uncertainty.py ai-module/tests/test_uncertainty.py
git commit -m "feat(uncertainty): verifiable signals for grounding, danger, major mismatch"
```

---

### Task 2: Wire the signals into the turn

**Files:**
- Modify: `ai-module/core/langgraph_state.py`
- Modify: `ai-module/core/assistant_graph.py` (`understand` at :186, `scope_guard`)
- Test: `ai-module/tests/test_uncertainty_gating.py`

**Interfaces:**
- Consumes: `assess` from Task 1.
- Produces: `understand` writes `uncertainty_level`, `danger_veto`, `ungrounded_slots`, `grounding_ratio`, `uncertainty_signals`; the emergency early return is gone; `clarification_question` is forced empty under veto; `scope_guard` passes a vetoed turn through as `emergency`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag


def _plan(**overrides):
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "浓烟", "persistence": "持续中", "impact": "人员无法疏散"},
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {
            "blocker": "浓烟", "persistence": "持续中", "impact": "人员无法疏散"}},
        "question": "被什么东西堵住了？", "answer": "我理解为消防通道被占。",
        "needs_search": True,
    }
    plan.update(overrides)
    return plan


def test_understand_no_longer_hijacks_an_emergency_turn(monkeypatch):
    """紧急不再提前返回：这轮仍要走规划器、检索、报告。"""
    seen = {}

    def fake_plan(messages, vision_summary, selected_major_code=""):
        seen["called"] = True
        return _plan()

    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert seen.get("called") is True
    assert out["danger_veto"] is True
    assert out["uncertainty_level"] == "cautious"
    assert out["ungrounded_slots"] == ["fire_lane_blocked.persistence=持续中"]


def test_understand_forbids_questions_under_a_danger_veto(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert out["clarification_question"] == ""
    assert out["next_action"] != "ask_critical_question"


def test_understand_forbids_full_reports_when_cautious(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert out["next_action"] == "report_preliminary"
    assert out["report_mode"] == "preliminary"


def test_routine_hazard_is_not_vetoed(monkeypatch):
    monkeypatch.setattr(
        ag, "_understand_plan",
        lambda *a, **k: _plan(
            issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                     "slots": {"blocker": "杂物", "persistence": "长期"}}],
            category_slots={"fire_lane_blocked": {"blocker": "杂物", "persistence": "长期"}},
            question="", answer="",
        ),
    )
    out = ag.understand({
        "messages": [HumanMessage(content="紧急出口被杂物堵住了，长期堆放")],
    })
    assert out["danger_veto"] is False
    assert out["uncertainty_level"] == "ok"


def test_scope_guard_does_not_downgrade_a_vetoed_turn(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    understood = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    update = ag.scope_guard({
        **understood,
        "messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")],
        "session_id": "veto-1",
    })
    assert update["scope"] == "emergency"


def test_state_exposes_the_uncertainty_fields():
    from core.langgraph_state import AssistantState
    for key in ("uncertainty_level", "danger_veto", "ungrounded_slots",
                "grounding_ratio", "uncertainty_signals"):
        assert key in AssistantState.__annotations__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_uncertainty_gating.py -q`
Expected: FAIL - `KeyError: 'danger_veto'`.

- [ ] **Step 3: Add the state fields**

In `ai-module/core/langgraph_state.py`:

```python
    # 不确定性（见 core/uncertainty.py）
    uncertainty_level: str              # "ok" | "cautious" | "fallback"
    danger_veto: bool                   # 正在发生的危险：禁止追问
    ungrounded_slots: list[str]
    grounding_ratio: float
    uncertainty_signals: list[str]
```

- [ ] **Step 4: Replace the emergency early return in `understand`**

```python
from core.uncertainty import assess

    # （删除原来的 decide_scope 紧急提前返回分支）
```

and after the plan is normalized:

```python
    verdict = assess(plan, [
        {"role": "user", "content": getattr(m, "content", "")}
        for m in state.get("messages") or []
        if isinstance(m, HumanMessage)
    ], vision_summary)
```

then merge it into what `understand` returns, and apply the two hard rules:

```python
    veto = verdict["danger_veto"]
    cautious = verdict["uncertainty_level"] == "cautious"
```

- if `veto` or `cautious`, `clarification_question` must be `""` and `optional_question` must be `False`;
- if `veto` and the policy chose `ask_critical_question`, replace the action with `report_preliminary`;
- if `cautious` and the policy chose `report_full`, replace it with `report_preliminary`;
- the planner-failure branch also runs `assess` so a veto still applies with an empty plan.

Report the reason through the existing `policy_reason` field, prefixed with the first signal.

- [ ] **Step 5: Make `scope_guard` honour the veto**

In `ai-module/core/assistant_graph.py`, `scope_guard`:

```python
    if state.get("danger_veto"):
        return {"scope": "emergency", "scope_reason": "active danger veto",
                "next_action": "answer_now" if not state.get("issues") else state.get("next_action")}
```

Placed before the `_SCOPE_DIRECT_MODES` early return and before `decide_scope` is consulted, so a missed emergency term cannot become an out-of-scope refusal.

- [ ] **Step 6: Run tests**

Run: `cd ai-module; python -m pytest tests/test_uncertainty_gating.py tests/test_uncertainty.py tests/test_thin_route.py -q`
Expected: PASS.

- [ ] **Step 7: Retarget the tests that encoded the old emergency template**

Run: `cd ai-module; python -m pytest tests/ -q --deselect tests/test_hazard_flow.py::test_report_writes_custom_chunks --deselect tests/test_vector_delete_api.py`
Expected failures are the assertions that the old emergency early return produced a template-only reply. Retarget them to the new contract (veto forbids questions, guidance is prepended, retrieval still runs). Do not delete behaviour assertions.

- [ ] **Step 8: Commit**

```bash
git add -A ai-module
git commit -m "feat(uncertainty): gate actions on verifiable signals in understand"
```

---

### Task 3: Forbid the question in the policy

**Files:**
- Modify: `ai-module/core/dialogue_policy.py`
- Test: `ai-module/tests/test_dialogue_policy.py` (extend)

**Interfaces:**
- Consumes: `state["danger_veto"]`, `state["uncertainty_level"]`.
- Produces: `decide_next_action` never returns `ask_critical_question` when either is set.

- [ ] **Step 1: Write the failing test**

```python
def test_danger_veto_forbids_asking_but_keeps_retrieval():
    from core.dialogue_policy import decide_next_action

    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {}, "missing": ["blocker"]}],
        "categories": ["fire_lane_blocked"], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    }
    result = decide_next_action(plan, {"user_text": "楼道里全是浓烟", "danger_veto": True})
    assert result["action"] != "ask_critical_question"
    assert result["needs_search"] is True


def test_cautious_uncertainty_forbids_asking_and_full_reports():
    from core.dialogue_policy import decide_next_action

    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {}, "missing": ["blocker"]}],
        "categories": ["fire_lane_blocked"], "category_slots": {},
        "question": "被什么堵住了？", "answer": "", "needs_search": True,
    }
    result = decide_next_action(plan, {
        "user_text": "楼道里全是浓烟", "uncertainty_level": "cautious",
    })
    assert result["action"] != "ask_critical_question"
    assert result["report_mode"] != "full"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_dialogue_policy.py -q -k "veto or cautious"`
Expected: FAIL - `ask_critical_question` is still returned.

- [ ] **Step 3: Implement the two guards**

At the top of `decide_next_action`, right after `intent` and `answer` are read:

```python
    no_questions = bool(state.get("danger_veto")) or \
        state.get("uncertainty_level") == "cautious"

    def _answer_or_preliminary(reason: str) -> dict:
        if issues:
            return _decision(
                "report_preliminary", reason=reason,
                needs_search=True, report_mode="preliminary",
            )
        return _decision("answer_now", reason=reason, needs_search=True)
```

Then replace each `ask_critical_question` return with:

```python
        if no_questions:
            return _answer_or_preliminary("<same reason>, but questions are forbidden by the "
                                          "uncertainty signals: " + ",".join(state.get("uncertainty_signals") or [])[:120])
```

and, in the branch that forces `report_full`, downgrade when `no_questions`:

```python
        return _decision(
            "report_full" if not no_questions else "report_preliminary",
            reason="...",
            needs_search=True,
            report_mode="full" if not no_questions else "preliminary",
        )
```

- [ ] **Step 4: Run tests**

Run: `cd ai-module; python -m pytest tests/test_dialogue_policy.py tests/test_uncertainty_gating.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/dialogue_policy.py ai-module/tests/test_dialogue_policy.py
git commit -m "feat(policy): forbid questions under danger veto or cautious uncertainty"
```

---

### Task 4: Guarantee the guidance in code

**Files:**
- Modify: `ai-module/core/assistant_graph.py` (`direct_reply`, `report`)
- Test: `ai-module/tests/test_uncertainty_gating.py` (extend)

**Interfaces:**
- Consumes: `state["danger_veto"]`, `state["uncertainty_level"]`, `state["danger_term"]` via `uncertainty_signals`.
- Produces: `prepend_guidance(text, state) -> str`; `prepend_interpretation(text, state) -> str`; replies under veto start with the fixed guidance sentence.

- [ ] **Step 1: Write the failing test**

```python
def test_guidance_is_prepended_by_code_even_when_the_model_omits_it(monkeypatch):
    chunks = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "### 一、触犯法规\n- 《消防法》第28条")]),
    )
    update = ag.report({
        "messages": [], "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {"regulation": "法", "case": "案例"}},
        "missing": [], "issues": [{"subcategory_code": "fire_lane_blocked"}],
        "report_mode": "preliminary", "danger_veto": True,
    })
    assert "119" in update["draft_report"]
    assert update["draft_report"].index("119") < update["draft_report"].index("消防法")


def test_guidance_is_not_duplicated_when_the_model_already_says_119(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda _: None)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "请立即拨打 119 报警")]),
    )
    update = ag.report({
        "messages": [], "categories": ["fire_lane_blocked"],
        "category_results": {}, "missing": [],
        "issues": [{"subcategory_code": "fire_lane_blocked"}],
        "report_mode": "preliminary", "danger_veto": True,
    })
    assert update["draft_report"].count("119") == 1


def test_cautious_reply_states_its_interpretation(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda _: None)
    update = ag.direct_reply({
        "direct_mode": "", "next_action": "report_preliminary",
        "clarification_question": "", "uncertainty_level": "cautious",
        "ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
        "messages": [],
        "dialogue_plan": {"ok": True, "answer": "我理解为消防通道被占。", "question": ""},
    })
    content = update["messages"][-1].content
    assert "核实" in content or "按" in content
    assert "？" not in content


def test_vetoed_reply_never_ends_in_a_question(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda _: None)
    update = ag.direct_reply({
        "direct_mode": "", "next_action": "answer_now", "danger_veto": True,
        "clarification_question": "被什么东西堵住了？",
        "messages": [],
        "dialogue_plan": {"ok": True, "answer": "浓烟环境应低姿撤离。", "question": ""},
    })
    content = update["messages"][-1].content
    assert "119" in content
    assert "？" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_uncertainty_gating.py -q -k "guidance or cautious or vetoed"`
Expected: FAIL - 119 is absent.

- [ ] **Step 3: Implement the two helpers and call them**

```python
GUIDANCE_LINE = (
    "如果现场正在起火、有人被困、燃气泄漏，或存在触电、坍塌等即时危险，"
    "请先确保自身安全并立即拨打 119（火警/救援）或 110，不要为填写信息而停留。"
)

_CAUTIOUS_NOTE = "（以下为初步判断，有一条现场信息我无法从你的描述中确认，建议先核实再上报。）"


def prepend_guidance(text: str, state: AssistantState) -> str:
    if not state.get("danger_veto") or "119" in (text or ""):
        return text
    return GUIDANCE_LINE + "\n\n" + (text or "")


def prepend_interpretation(text: str, state: AssistantState) -> str:
    if state.get("uncertainty_level") != "cautious":
        return text
    return _CAUTIOUS_NOTE + "\n\n" + (text or "")
```

Wire `prepend_guidance` then `prepend_interpretation` into both `direct_reply` (before writing the chunk) and `report` (on the final `draft_report`, and stream the prepended text too).

- [ ] **Step 4: Run tests**

Run: `cd ai-module; python -m pytest tests/test_uncertainty_gating.py -q`
Expected: PASS.

- [ ] **Step 5: Full regression**

Run: `cd ai-module; python -m pytest tests/ -q --deselect tests/test_hazard_flow.py::test_report_writes_custom_chunks --deselect tests/test_vector_delete_api.py`
Expected: PASS. Compare against the 195-passed baseline and explain any delta.

- [ ] **Step 6: Commit**

```bash
git add -A ai-module
git commit -m "feat(reply): code-owned guidance and interpretation notes"
```

---

### Task 5: Deploy and smoke

- [ ] **Step 1: Deploy** following `docs/deployment/safety-platform-deployment.md` section 4, then confirm health.

- [ ] **Step 2: Smoke the acceptance list**

```bash
# 1. must contain 119 and no form question
curl -sS -N -X POST http://127.0.0.1:8000/api/ai/assistant/stream -H "Content-Type: application/json" \
  -d '{"message":"楼道里全是浓烟，人都出不来","session_id":"und-smoke-1","user_id":1}'
# 2. danger veto, report action, 119 present, analysis still present
curl ... -d '{"message":"楼上火烧起来了，好几个人在里面","session_id":"und-smoke-2","user_id":1}'
# 3. no veto, normal flow, task creation still offered
curl ... -d '{"message":"紧急出口被杂物堵住了，长期堆放","session_id":"und-smoke-3","user_id":1}'
# 4. no veto
curl ... -d '{"message":"马上就要下雨了，井盖破了","session_id":"und-smoke-4","user_id":1}'
```

Assert per case: presence of `119`, absence of a trailing question under veto, presence of an `interrupt` for case 3, and that case 4 keeps the normal flow.

- [ ] **Step 3: Roll back if the smoke fails**, then report the failing case instead of patching live.
