> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Agent Dialogue Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the safety assistant's conversational naturalness and category consistency without replacing the existing LangGraph, tools, SSE API, or reporting pipeline.

**Architecture:** Keep the current route → clarify/search → report graph. Add one early direct-response decision for greetings and simple hazard judgments, so those requests do not enter the full slot questionnaire. Centralize the distinction between consultation categories and the four categories supported by automatic task creation. Fix message persistence and vision-failure handling at the HTTP boundary.

**Tech Stack:** Python, FastAPI, LangGraph, pytest, existing MiMo OpenAI-compatible client.

## Global Constraints

- Do not redesign or replace the existing Agent/LangGraph/tool/SSE architecture.
- Consultation supports the existing eight internal categories; automatic task creation remains limited to `占道`, `井盖/道路`, `消防通道`, and `施工`.
- A direct response is preliminary guidance only; it must not invent regulations or case results and must not trigger task creation.
- Do not modify credentials, external API endpoints, unrelated Java modules, or unrelated working-tree changes.
- Keep each user message stored once per request and never inject `[视觉分析] None`.

---

### Task 1: Establish category boundaries and direct-response behavior

**Files:**
- Create: `ai-module/core/hazard_categories.py`
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/tools/hazard_submit.py`
- Test: `ai-module/tests/test_agent_dialogue_optimization.py`

**Interfaces:**
- `core.hazard_categories.CONSULT_CATEGORIES`: tuple of eight categories used by dialogue routing.
- `core.hazard_categories.SUBMIT_CATEGORIES`: tuple of four categories supported by task creation.
- `core.hazard_categories.VISION_CATEGORY_MAP`: normalized vision-to-dialogue mapping.
- `core.assistant_graph._detect_direct_mode(text, vision_summary="")`: returns `"smalltalk"`, `"quick_judgment"`, or `""`.

- [ ] **Step 1: Write failing tests** for shared category boundaries, vision aliases, greetings, quick hazard judgments, and ordinary detailed descriptions.
- [ ] **Step 2: Run the focused tests** and confirm they fail because the shared module and direct-mode helper do not yet exist.
- [ ] **Step 3: Implement the shared constants and minimal direct-response decision.** Reuse the current eight consultation categories and four submit categories; map unsupported vision labels to `其他` rather than claiming task support.
- [ ] **Step 4: Add a `direct_reply` graph node.** Keep small talk as a short fixed response and use the existing report LLM for a concise preliminary judgment. Do not call retrieval or append the task-creation prompt.
- [ ] **Step 5: Route direct modes before slot extraction** and leave the current clarify/search/report path unchanged for detailed requests.
- [ ] **Step 6: Run the focused tests** and confirm they pass.

### Task 2: Fix deterministic context handling

**Files:**
- Modify: `ai-module/server.py`
- Test: `ai-module/tests/test_agent_dialogue_optimization.py`

**Interfaces:**
- Preserve the existing `/api/ai/assistant/stream` request and SSE event contract.

- [ ] **Step 1: Add regression coverage** for storing a user message once and for representing vision failure without a false successful vision record.
- [ ] **Step 2: Run the focused regression tests** and confirm the current implementation fails.
- [ ] **Step 3: Keep the early user-message write and remove the duplicate post-stream write.** This preserves availability to a concurrent follow-up while preventing duplicate history.
- [ ] **Step 4: Make the vision branch append either a real `[视觉分析]` result or one failure message, never both and never `None`.
- [ ] **Step 5: Run focused tests and the existing assistant graph tests.**

### Task 3: Final verification and handoff

**Files:**
- No additional production files.

- [ ] **Step 1: Run the focused dialogue tests.**
- [ ] **Step 2: Run the existing multi-hazard/adaptive-slot tests.**
- [ ] **Step 3: Review the diff for scope, preserving all pre-existing user changes.**
- [ ] **Step 4: Report the changed files, the resulting conversation flow, and any limitations for manual testing.**

## Execution Notes (2026-09-23)

1. Category boundaries: dialogue recognizes eight categories; automatic task creation stays limited to four. Unknown vision labels map to “其他” only if text gives no recognized category. Empty extracted categories cannot silently become “占道”. The report invites task creation only when all categories are supported and required information is present.
2. Context: keep the early user-message write and remove the duplicate post-stream write. Each image request records exactly one successful vision context or one failure context; failure never injects “None” as successful analysis.
3. Direct response: greetings and thanks use short deterministic SSE replies. Straightforward judgment uses the existing report LLM without search, slot extraction, or task creation. Image requests and detailed regulation/case requests retain the existing route → clarification (at most three rounds) → search → report path. No new loop was added.

The cloud server was not accessed. Local tests cannot establish deployment, external MiMo access, real retrieval quality, or Java task creation. A pre-existing multi-hazard test expects no task-creation invitation for a complete supported category even though the existing report adds one; legacy SSE tests import the absent stream_analysis function; and a legacy upload test passes a file stub without filename. Those unrelated legacy tests and interfaces were left untouched.
