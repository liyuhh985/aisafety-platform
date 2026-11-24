# -*- coding: utf-8 -*-
"""Run each labeler independently on deterministic ``needs_verifier`` rows."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.slot_schemas import get_slot_schema
from eval.semantic_grounding.deterministic_prefilter import prefilter_sample
from eval.semantic_grounding.labeler_config import build_labeler
from eval.semantic_grounding.protocol import LABEL_SET, dump_jsonl, load_jsonl


def _slot_question(category: str, slot_key: str) -> str:
    for slot in get_slot_schema(category):
        if slot.key == slot_key:
            return slot.question
    return ""


def build_labeler_input(row: dict) -> dict:
    """The only fields visible to either model.

    Expected labels, split, group id, category, dialogue history and the other
    model's result are deliberately excluded to prevent calibration leakage.
    """
    return {
        "slot": str(row.get("slot") or ""),
        "slot_question": _slot_question(
            str(row.get("category") or ""), str(row.get("slot") or "")
        ),
        "value": str(row.get("value") or ""),
        "quote": str(row.get("quote") or ""),
    }


def parse_label_response(text) -> dict:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"label": "invalid", "reason": "parse_or_request_failed"}
    if not isinstance(payload, dict):
        return {"label": "invalid", "reason": "parse_or_request_failed"}
    label = payload.get("label")
    confidence = payload.get("confidence")
    if label not in LABEL_SET:
        return {"label": "invalid", "reason": "invalid_label"}
    if (not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 1.0):
        return {"label": "invalid", "reason": "invalid_confidence"}
    return {"label": label, "confidence": float(confidence)}


def label_rows(rows, labeler) -> dict:
    """Label each row independently and return ``{id: result}``."""
    results = {}
    for row in rows:
        messages = [
            {"role": "system", "content": labeler.system_prompt},
            {"role": "user", "content": json.dumps(
                build_labeler_input(row), ensure_ascii=False, sort_keys=True
            )},
        ]
        try:
            response = labeler._call_llm(messages)
            parsed = parse_label_response((response or {}).get("content"))
        except Exception:
            parsed = {"label": "invalid", "reason": "parse_or_request_failed"}
        results[str(row.get("id") or "")] = parsed
    return results


def run_labeling(base_path, output_dir, split: str = "dev",
                 labeler_a=None, labeler_b=None) -> dict:
    base_rows = [row for row in load_jsonl(base_path) if row.get("split") == split]
    deterministic = []
    candidates = []
    for row in base_rows:
        decision = prefilter_sample(row)
        deterministic.append({
            "id": row["id"], "slot_class": row.get("slot_class", ""), **decision,
        })
        if decision["decision"] == "needs_verifier":
            candidates.append(row)

    labeler_a = labeler_a or build_labeler("A")
    labeler_b = labeler_b or build_labeler("B")
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="semantic-labeler") as pool:
        future_a = pool.submit(label_rows, candidates, labeler_a)
        future_b = pool.submit(label_rows, candidates, labeler_b)
        labels_a = future_a.result()
        labels_b = future_b.result()
    output = Path(output_dir)
    dump_jsonl(output / "deterministic.jsonl", deterministic)
    dump_jsonl(output / "labels_A.jsonl",
               [{"id": key, **value} for key, value in labels_a.items()])
    dump_jsonl(output / "labels_B.jsonl",
               [{"id": key, **value} for key, value in labels_b.items()])
    return {
        "split": split,
        "rows": len(base_rows),
        "candidates": len(candidates),
        "labels_a": labels_a,
        "labels_b": labels_b,
    }


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    base_path = args[0] if args else str(
        Path(__file__).parent / "dataset" / "qv-pseudo-v1.jsonl"
    )
    output_dir = args[1] if len(args) > 1 else str(Path(__file__).parent / "artifacts")
    split = args[2] if len(args) > 2 else "dev"
    result = run_labeling(base_path, output_dir, split)
    print(json.dumps({key: result[key] for key in ("split", "rows", "candidates")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
