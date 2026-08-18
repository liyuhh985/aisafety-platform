# Day 21 RAG and Report Evaluation Design

## Goal

Extend the existing offline RAG evaluation from loose category hit-rate checks to reproducible ranking metrics and negative-sample analysis, then evaluate generated reports with deterministic key-point coverage checks.

## Scope

The existing `ai-module/eval_rag.py` remains the executable entry point. The evaluation corpus will explicitly define positive queries, expected categories, and negative queries. Each retrieval result will expose enough ranked evidence to calculate:

- `Recall@k`: whether an expected-category result appears in the first `k` retrieved items.
- `MRR`: reciprocal rank of the first expected-category result, or `0` when none is retrieved.
- Negative false-positive rate: the proportion of negative queries that incorrectly retrieve the category explicitly marked as absent.

The script will print each failure with its query, expected category, ranked categories, rank, and reason. Aggregate metrics must distinguish basic, difficult, and negative subsets so a high overall score cannot conceal poor edge-case behavior.

Report evaluation will use a small fixed fixture set. Each fixture defines required points and forbidden claims; `check_report()` returns missing required points, forbidden claims found, and pass/fail. This measures factual coverage and simple contradiction markers only. It does not claim to measure fluency, completeness beyond the fixture, or semantic faithfulness.

## Design Choices

The chosen approach is deterministic, offline evaluation against the current `hybrid_search` path. It is reproducible in local development and works without model credentials or a judge model.

Two alternatives remain out of scope for this day:

- LLM-as-judge can assess semantic quality, but adds cost, prompt sensitivity, and judge calibration work.
- Human annotation gives the strongest quality signal, but is not repeatable at every code change without a labeled review workflow.

## Files and Boundaries

- Modify `ai-module/eval_rag.py` to define cases, normalize ranked category evidence, calculate metrics, and report failures.
- Add focused tests under `ai-module/tests/` for metric calculations and report-fixture behavior. Tests must use fixed ranked inputs and not require Milvus, a network connection, or model credentials.
- Append the Day 21 learning record to `docs/superpowers/plans/2026-07-28-agent-application-learning-plan.md` after all code and test evidence is available.

No production retrieval behavior, vector schema, model prompt, or historical-memory behavior changes in this work.

## Error Handling and Evidence

Individual retrieval exceptions are reported as failed cases and excluded from neither the displayed case list nor the final failure analysis. Aggregate denominators include all planned cases so infrastructure failure cannot improve a metric.

Day 21 is complete only when the focused metric tests pass and the real evaluation script runs against the configured local retrieval backend. The final record must state actual metric values, false-positive observations, failure cases, and the limits of the report checker.
