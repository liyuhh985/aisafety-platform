# -*- coding: utf-8 -*-
"""Dedicated independent labeler construction for offline calibration."""

import os

from core.agent import Agent

SEMANTIC_LABELER_PROMPT = (
    "你是槽位证据关系标注器。只判断 quote 是否支持 value。"
    "relation 只能是 entailed / contradicted / neutral。"
    "entailed 表示 quote 直接支持 value；contradicted 表示 quote 与 value 冲突；"
    "neutral 表示 quote 既不能支持也不能否定 value。"
    "不重新抽取事实，不参考对话，不使用工具。"
    '只输出一个 JSON 对象：{"label":"...","confidence":0.0}。'
)


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
