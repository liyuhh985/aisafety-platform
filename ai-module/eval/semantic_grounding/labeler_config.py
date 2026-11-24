# -*- coding: utf-8 -*-
"""Offline MiniMax/GLM pseudo-labelers; never imported by runtime code."""

import json
import os

from core.agent import Agent

OFFLINE_LABELER_PROMPT = (
    "你是离线伪标签标注器。只判断 quote 是否支持 value。"
    "relation 只能是 entailed / neutral / contradicted。"
    "entailed 表示 quote 直接支持 value；contradicted 表示 quote 与 value 冲突；"
    "neutral 表示 quote 既不能支持也不能否定 value。"
    "不重新抽取事实，不参考对话，不使用工具。"
    "输入是一个 JSON 数组，每个元素包含 id、slot、slot_question、value、quote。"
    '只输出一个 JSON 对象：{"labels":[{"id":"...","label":"...","confidence":0.0}]}。'
    "每个输入 id 必须恰好返回一次，不添加其他字段。"
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
        system_prompt=OFFLINE_LABELER_PROMPT,
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


def _normalize_label(value):
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


def call_labeler(key, candidates, cancellation=None) -> dict:
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


_call_labeler = call_labeler
