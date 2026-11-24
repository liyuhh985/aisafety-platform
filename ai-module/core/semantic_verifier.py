# -*- coding: utf-8 -*-
"""Single production-model verifier for weak slot evidence."""

import json
from typing import Optional

from config import (
    SEMANTIC_VERIFIER_MAX_ITEMS,
    SEMANTIC_VERIFIER_MIN_CONFIDENCE,
    SMALL_MODEL,
)
from core.agent import Agent
from core.slot_schemas import get_slot_schema

RUNTIME_VERIFIER_PROMPT = (
    "你是槽位证据复核器。只判断 quote 是否支持 value，label 只能是 "
    "entailed / contradicted。"
    "entailed 表示 quote 直接陈述、同义改写或语义蕴含足以支持 value。"
    "contradicted 表示 quote 不支持 value，包括信息不足、仅同主题、无关、"
    "明确否定或数字冲突。"
    "不重新抽取事实，不判断风险等级，不参考完整对话，不使用工具。"
    "输入是一个 JSON 数组，每个元素包含 id、slot、slot_question、value、quote。"
    '只输出一个 JSON 对象：{"labels":[{"id":"...","label":"...","confidence":0.0}]}。'
    "每个输入 id 必须恰好返回一次，不添加其他字段。"
)

_VERIFIER = None


def build_verifier():
    return Agent(
        name="semantic_verifier",
        system_prompt=RUNTIME_VERIFIER_PROMPT,
        tools=[],
        base_url=SMALL_MODEL.base_url,
        api_key=SMALL_MODEL.api_key,
        model=SMALL_MODEL.model,
        slot="small",
        temperature=0.0,
        use_configured_slot=True,
        allow_fallback=True,
    )


def _configured_verifier():
    global _VERIFIER
    if _VERIFIER is None:
        _VERIFIER = build_verifier()
    return _VERIFIER


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
    return slot.value_class if slot else "B"


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
    rank = {"A": 0, "B": 1}
    candidates.sort(key=lambda row: rank.get(row["value_class"], 2))
    return candidates[:max(1, int(max_items or 5))]


def _normalize_label(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    confidence = value.get("confidence")
    if label not in {"entailed", "contradicted"}:
        return None
    if (not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 1.0):
        return None
    return {"label": label, "confidence": float(confidence)}


def parse_batch_response(text) -> dict:
    raw = str(text or "").strip()
    if raw.startswith("`" * 3):
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


def _call_verifier(candidates, cancellation=None) -> dict:
    verifier = _configured_verifier()
    visible = [
        {field: row.get(field, "") for field in (
            "id", "slot", "slot_question", "value", "quote",
        )}
        for row in candidates
    ]
    messages = [
        {"role": "system", "content": verifier.system_prompt},
        {"role": "user", "content": json.dumps(
            visible, ensure_ascii=False, sort_keys=True
        )},
    ]
    response = verifier._call_llm(messages, cancellation=cancellation)
    return parse_batch_response((response or {}).get("content"))


def _apply_status(result, status, label=None, confidence=None) -> None:
    result["status"] = status
    result["business_status"] = status
    if status == "grounded_by_model":
        result["reason"] = "runtime_verifier_entailed"
    elif status == "rejected":
        result["reason"] = "runtime_verifier_contradicted"
    else:
        result["reason"] = "runtime_verifier_low_confidence_or_invalid"
    if label is not None:
        result["verifier_label"] = label
    if confidence is not None:
        result["verifier_confidence"] = confidence


def verify_weak_slots(issues, audit, cancellation=None) -> dict:
    audit = audit if isinstance(audit, dict) else {}
    candidates = collect_weak_candidates(
        issues, audit, max_items=SEMANTIC_VERIFIER_MAX_ITEMS
    )
    if not candidates:
        return audit
    try:
        labels = _call_verifier(candidates, cancellation=cancellation)
    except Exception:
        labels = {}

    for candidate in candidates:
        code = candidate["category"]
        slot = candidate["slot"]
        result = ((audit.get(code) or {}).get(slot) or {})
        if not result:
            continue
        verdict = labels.get(candidate["id"])
        if verdict is None:
            _apply_status(result, "unavailable")
            continue
        confidence = verdict["confidence"]
        if confidence < SEMANTIC_VERIFIER_MIN_CONFIDENCE:
            _apply_status(result, "unavailable", verdict["label"], confidence)
            continue
        status = (
            "grounded_by_model"
            if verdict["label"] == "entailed"
            else "rejected"
        )
        _apply_status(result, status, verdict["label"], confidence)
    return audit
