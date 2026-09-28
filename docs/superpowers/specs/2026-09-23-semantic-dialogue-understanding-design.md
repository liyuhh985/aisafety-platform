# Semantic Dialogue Understanding Design

## Goal

Fix the assistant's context mismatch without replacing the existing LangGraph, SSE API, retrieval tools, image-report endpoints, or Java task-creation flow.

The concrete failure is:

> 三明市万达广场对面的消防设施过于老旧，不能正常使用

The old pipeline maps the generic keyword `消防` to `消防通道`, then asks:

> 消防通道目前是被什么东西挡住的呢？这种情况已经持续多久了？

The issue is not model capability. The workflow performs semantic classification with keywords and only asks the model to phrase already-decided slot questions.

## Current Architecture

```text
/api/ai/assistant/stream
  -> server.py
  -> core.assistant_graph.run_stream_events
  -> route (keyword classification + LLM slot extraction)
  -> clarify / search / report
  -> optional Java task creation
```

Image report endpoints are separate and remain stable:

```text
/api/ai/analyze
/api/ai/analyze/stream
  -> core.orchestrator.Orchestrator
  -> vision / retrieval / report agents
```

## Design

Add one logical `understand` stage before the existing policy nodes. It is one structured model call for normal consultation, not an extra model or fine-tuned model.

```text
messages + vision summary
  -> understand (structured intent/facts/issues/question)
  -> route (deterministic validation and policy)
  -> direct_reply | clarify | search
  -> report or task creation
```

The `understand` stage returns:

```json
{
  "intent": "quick_assessment",
  "categories": ["消防设施"],
  "category_slots": {
    "消防设施": {
      "facility_type": "",
      "condition": "老旧",
      "function_impact": "不能正常使用"
    }
  },
  "question": "具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？",
  "answer": "我理解为消防设施老旧、无法正常使用。",
  "needs_search": false,
  "relationship_hint": "add",
  "confidence": 0.9
}
```

Rules:

- Explicit `消防设施` must not be classified as `消防通道`.
- `消防设施故障` and `消防通道占用` are separate consultation categories.
- A normal consultation asks at most one question.
- Already answered facts are not asked again.
- Missing non-critical facts do not block a preliminary answer.
- The planner answers first when possible; a clarification is optional.
- Retrieval and task creation remain deterministic downstream actions.
- Planner failure falls back to the existing route logic.

## State

The transcript in `WorkingMemory` remains the durable source of truth. LangGraph structured fields are treated as a per-turn derived view and are reconstructed from the transcript by `understand`. This removes the need for a second, competing structured history to survive every HTTP request.

## Latency

The new planner call replaces the existing `_infer_categories`, `_llm_extract_slots`, and `_llm_phrase` calls for normal consultation. It is not added on top of them. Greetings and thanks keep the deterministic fast path and make no planner call.

## Compatibility

- Existing SSE event types remain `status`, `chunk`, `error`, and `done`.
- `/api/ai/analyze` and `/api/ai/analyze/stream` remain on the compatibility Orchestrator path for now.
- Automatic task creation remains limited to `占道`, `井盖/道路`, `消防通道`, and `施工`.
- `消防设施` can be consulted and reported, but does not automatically create a task.
- `core/agent.py` remains the model/tool client, not a second business workflow.

## Out of Scope

- Fine-tuning.
- Removing the legacy Orchestrator before image-report traffic is migrated.
- Rewriting the retrieval store or Java service.
- A full form-based task-creation UI.

## Verification

- The screenshot utterance produces `消防设施` and at most one relevant question.
- A detailed request still reaches retrieval and report.
- Existing image-report imports and endpoints still load.
- All new behavior is covered by focused pytest cases and the existing assistant graph tests.

## Execution Notes

Implemented on 2026-09-23 and deployed to the cloud AI service as deployments `20260923T202213` and `20260923T202717`.

- Local focused regression: 67 passed, 1 pre-existing report-prompt test deselected.
- Broader local regression: 105 passed, 3 skipped, 6 deselected; the only remaining full-suite failure is the pre-existing vector-delete endpoint test.
- Cloud health: `{"status":"ok","model":"mimo-v2.6-flash"}`.
- Cloud screenshot smoke: the response correctly identified `消防设施老旧失效` and asked exactly one question about the facility type; it did not mention a blocked fire lane.
- After tightening the planner prompt, the response asked only for the facility type and no longer bundled a location question.
- Cloud detailed smoke: the request still completed retrieval and generated a regulation/case report in about 65 seconds.
- Cloud multi-turn smoke: adding a dangerous building in the next turn kept both the fire-facility issue and the new building issue.
- Image-report compatibility: `server.get_orch()` imports successfully; the legacy `/api/ai/analyze` path was not removed or rerouted.
