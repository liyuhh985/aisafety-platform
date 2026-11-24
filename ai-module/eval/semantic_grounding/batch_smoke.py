# -*- coding: utf-8 -*-
"""Run a reproducible real-API smoke for the frozen batch-label contract.

This is an integration probe, not part of the ordinary unit-test suite.
It exits non-zero unless both models return exactly one valid label per id.
"""

import json
import os
import sys
from pathlib import Path

from core.semantic_verifier import SEMANTIC_LABELER_PROMPT, _call_labeler
from eval.semantic_grounding.protocol import LABEL_SET, sha256_text

CANDIDATES = [
    {
        "id": "smoke-a",
        "slot": "structure",
        "slot_question": "房屋是否有裂缝、倾斜或沉降？",
        "value": "墙体倾斜",
        "quote": "房子明显往一边斜",
    },
    {
        "id": "smoke-b",
        "slot": "persistence",
        "slot_question": "是长期占压还是临时停放？",
        "value": "长期",
        "quote": "只是今天临时停了十分钟",
    },
]


def main(output_path=None):
    labels = {key: _call_labeler(key, CANDIDATES) for key in ("A", "B")}
    expected_ids = {row["id"] for row in CANDIDATES}
    for key, result in labels.items():
        if set(result) != expected_ids:
            raise RuntimeError(f"labeler {key} did not return every id exactly once")
        if any(row.get("label") not in LABEL_SET for row in result.values()):
            raise RuntimeError(f"labeler {key} returned an invalid label")
    record = {
        "prompt_sha256": sha256_text(SEMANTIC_LABELER_PROMPT),
        "models": {
            "A": os.getenv("SEMANTIC_LABELER_A_MODEL", ""),
            "B": os.getenv("SEMANTIC_LABELER_B_MODEL", ""),
        },
        "candidates": CANDIDATES,
        "labels": labels,
    }
    text = json.dumps(record, ensure_ascii=False, indent=2) + chr(10)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return record


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
