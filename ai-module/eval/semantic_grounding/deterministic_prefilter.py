# -*- coding: utf-8 -*-
"""Deterministic routing that must run before either semantic labeler."""

from core.uncertainty import (
    _digits_preserved,
    _negated_near_quote,
    is_echo_slot,
    normalize_text,
)


def prefilter_sample(sample: dict) -> dict:
    value = str((sample or {}).get("value") or "").strip()
    quote = str((sample or {}).get("quote") or "").strip()
    source = str((sample or {}).get("source_text") or "").strip()
    category = str((sample or {}).get("category") or "").strip()
    if not quote or not source or normalize_text(quote) not in normalize_text(source):
        return {"decision": "invalid_source", "reason": "quote_not_in_source"}
    if is_echo_slot(value, category):
        return {"decision": "echo", "reason": "label_echo"}
    if not _digits_preserved(value, source):
        return {"decision": "contradicted", "reason": "numeric_mismatch"}
    if _negated_near_quote(source, quote, value):
        return {"decision": "contradicted", "reason": "negation_conflict"}
    if normalize_text(value) in normalize_text(quote):
        return {"decision": "grounded", "reason": "direct_quote_support"}
    return {"decision": "needs_verifier", "reason": "weak_value"}
