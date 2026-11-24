# -*- coding: utf-8 -*-
"""One-shot test-set manifest freezing."""

import json
from datetime import datetime, timezone
from pathlib import Path

from eval.semantic_grounding.protocol import BASE_DATASET, sha256_file, sha256_text


def freeze_manifest(dataset_path, model_a, model_b, prompt, thresholds,
                    output_path=None) -> dict:
    target = Path(output_path) if output_path else None
    if target is not None and target.exists():
        raise FileExistsError(str(target))
    manifest = {
        "dataset": BASE_DATASET,
        "split": "test",
        "test_sha256": sha256_file(dataset_path),
        "prompt_sha256": sha256_text(prompt),
        "models": [str(model_a), str(model_b)],
        "thresholds": dict(thresholds or {}),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return manifest


def load_frozen_manifest(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
