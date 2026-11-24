# -*- coding: utf-8 -*-
"""Runtime dual-model semantic verifier for grey-zone slot evidence."""

import json
import os
from typing import Optional

from config import (
    SEMANTIC_VERIFIER_A_THRESHOLD,
    SEMANTIC_VERIFIER_B_THRESHOLD,
    SEMANTIC_VERIFIER_C_THRESHOLD,
    SEMANTIC_VERIFIER_MAX_ITEMS,
)
from core.agent import Agent
from core.slot_schemas import get_slot_schema

SEMANTIC_LABELER_PROMPT = (
    "你是槽位证据关系标注器。只判断 quote 是否支持 value。"
    "relation 只能是 entailed / contradicted / neutral。"
    "entailed 表示 quote 直接支持 value；contradicted 表示 quote 与 value 冲突；"
    "neutral 表示 quote 既不能支持也不能否定 value。"
    "不重新抽取事实，不参考对话，不使用工具。"
    '只输出一个 JSON 对象：{"label":"...","confidence":0.0}。'
)

_LABELERS = {}


def build_labeler(key: str):
    normalized = str(key or "").upper()
    if normalized not in {"A", "B"}:
        raise ValueError("labeler key must be A or B")
    base = os.getenv(f"SEMANTIC_LABELER_{normalized}_BASE_URL", "").strip()
    api_key = os.getenv(f"SEMANTIC_LABELER_{normalized}_API_KEY", "").strip()
    model = os.getenv(f"SEMANTIC_LABELER_{normalized}_MODEL", "").strip()
    if not base or not api_key or not model:
        raise RuntimeError(f"semantic labeler {normalized} is not configured")
    return Agent(
        name=f"semantic_labeler_{normalized.lower()}",
        system_prompt=SEMANTIC_LABELER_PROMPT,
        tools=[],
        base_url=base,
        api_key=api_key,
        model=model,
        temperature=0.0,
        use_configured_slot=False,
        allow_fallback=False,
    )


def _configured_labeler(key: str):
    if key not in _LABELERS:
        _LABELERS[key] = build_labeler(key)
    return _LABELERS[key]


def _slot_schema(code: str, slot_key: str):
    for slot in get_slot_schema(code):
        if slot.key == slot_key:
            return slot
    return None


def _slot_question(code: str, slot_key: str) -> str:
    slot = _slot_schema(code, slot_key)
    return slot.question if slot else ""


def _slot_class(code: str, slot_key: str) -> str:
    slot = _slot_schema(code, slot_key)
    return slot.value_class if slot else "C"


def collect_weak_candidates(issues, audit, max_items=5) -> list[dict]:
    candidates = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("subcategory_code") or "")
        if not code:
            continue
        for slot, value in (issue.get("slots") or {}).items():
            result = ((audit.get(code) or {}).get(slot) or {})
            if result.get("status") != "weak":
                continue
            quote = str(result.get("quote") or "")
            source_ref = str(result.get("source_ref") or "")
            if not quote or source_ref[:1] not in {"u", "v"}:
                continue
            candidates.append({
                "id": f"{code}:{slot}",
                "category": code,
                "slot": slot,
                "slot_question": _slot_question(code, slot),
                "value": str(value),
                "quote": quote,
                "value_class": _slot_class(code, slot),
            })
    rank = {"A": 0, "B": 1, "C": 2}
    candidates.sort(key=lambda row: rank.get(row["value_class"], 3))
    return candidates[:max(1, int(max_items or 5))]


def _normalize_label(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    confidence = value.get("confidence")
    if label not in {"entailed", "neutral", "contradicted"}:
        return None
    if (not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 1.0):
        return None
    return {"label": label, "confidence": float(confidence)}


def parse_batch_response(text) -> dict:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(payload, dict) and "labels" in payload:
        payload = payload.get("labels")
    result = {}
    if isinstance(payload, dict):
        for identifier, value in payload.items():
            normalized = _normalize_label(value)
            if normalized is not None:
                result[str(identifier)] = normalized
    elif isinstance(payload, list):
        for value in payload:
            if not isinstance(value, dict) or not value.get("id"):
                continue
            normalized = _normalize_label(value)
            if normalized is not None:
                result[str(value["id"])] = normalized
    return result


def _call_labeler(key, candidates, cancellation=None) -> dict:
    labeler = _configured_labeler(key)
    visible = [
        {field: row.get(field, "") for field in (
            "id", "slot", "slot_question", "value", "quote",
        )}
        for row in candidates
    ]
    messages = [
        {"role": "system", "content": labeler.system_prompt},
        {"role": "user", "content": json.dumps(
            visible, ensure_ascii=False, sort_keys=True
        )},
    ]
    response = labeler._call_llm(messages, cancellation=cancellation)
    return parse_batch_response((response or {}).get("content"))


def _a_class_status(a, b) -> str:
    if (a["label"] == b["label"] == "entailed"
            and min(a["confidence"], b["confidence"]) >= SEMANTIC_VERIFIER_A_THRESHOLD):
        return "grounded_by_model"
    if (a["label"] == b["label"] == "contradicted"
            and min(a["confidence"], b["confidence"]) >= SEMANTIC_VERIFIER_C_THRESHOLD):
        return "rejected"
    return "unavailable"


def _b_class_status(a, b) -> str:
    if (a["label"] == "entailed"
            and a["confidence"] >= SEMANTIC_VERIFIER_B_THRESHOLD):
        return "grounded_by_model"
    if (a["label"] == "contradicted" and b is not None
            and b["label"] == "contradicted"
            and min(a["confidence"], b["confidence"]) >= SEMANTIC_VERIFIER_C_THRESHOLD):
        return "rejected"
    return "unavailable"


def _apply_status(result, status, a=None, b=None) -> None:
    result["status"] = status
    result["business_status"] = status
    if status == "grounded_by_model":
        result["reason"] = "model_consensus_entailed"
    elif status == "rejected":
        result["reason"] = "model_consensus_contradicted"
    else:
        result["reason"] = "model_indeterminate_or_failed"
    if a is not None:
        result["model_a"] = dict(a)
    if b is not None:
        result["model_b"] = dict(b)


def verify_weak_slots(issues, audit, cancellation=None) -> dict:
    audit = audit if isinstance(audit, dict) else {}
    candidates = collect_weak_candidates(
        issues, audit, max_items=SEMANTIC_VERIFIER_MAX_ITEMS
    )
    if not candidates:
        return audit
    try:
        labels_a = _call_labeler("A", candidates, cancellation=cancellation)
    except Exception:
        labels_a = {}
    b_candidates = []
    for candidate in candidates:
        a = labels_a.get(candidate["id"])
        if candidate["value_class"] == "A" or (
            a is not None and a.get("label") == "contradicted"
        ):
            b_candidates.append(candidate)
    labels_b = {}
    if b_candidates:
        try:
            labels_b = _call_labeler("B", b_candidates, cancellation=cancellation)
        except Exception:
            labels_b = {}

    for candidate in candidates:
        code = candidate["category"]
        slot = candidate["slot"]
        result = ((audit.get(code) or {}).get(slot) or {})
        if not result:
            continue
        a = labels_a.get(candidate["id"])
        b = labels_b.get(candidate["id"])
        if a is None:
            _apply_status(result, "unavailable")
            continue
        if candidate["value_class"] == "A":
            status = _a_class_status(a, b) if b is not None else "unavailable"
        else:
            status = _b_class_status(a, b)
        _apply_status(result, status, a=a, b=b)
    return audit
