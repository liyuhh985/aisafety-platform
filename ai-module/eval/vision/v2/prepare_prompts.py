from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

AI_MODULE_DIR = Path(__file__).resolve().parents[3]
if str(AI_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODULE_DIR))

from prompts import VISION_PROMPT

FINAL_RULES = """【v2.1 精度优先补充规则】
- 只有在画面清楚显示目标隐患时才输出 has_hazard=true。
- 不得仅凭新闻标题、字幕、文字说明、常识或上下文推测隐患。
- 场景正常或有可见证据表明符合要求时，输出 has_hazard=false。
- 因遮挡、模糊、信息不足而无法判断时，输出 has_hazard=false、confidence=低、subcategory 为空，并说明需要人工复核。
- confidence=低 仅表示需要人工复核，不代表无隐患。"""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_prompts(output_dir: Path, manifest_path: Path | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = VISION_PROMPT
    final = baseline + "\n\n" + FINAL_RULES
    baseline_path = output_dir / "baseline.txt"
    final_path = output_dir / "final.txt"
    baseline_path.write_text(baseline, encoding="utf-8")
    final_path.write_text(final, encoding="utf-8")

    manifest = {
        "baseline": {
            "id": "baseline",
            "path": str(baseline_path),
            "sha256": _sha256_text(baseline),
            "characters": len(baseline),
        },
        "final": {
            "id": "final",
            "path": str(final_path),
            "sha256": _sha256_text(final),
            "characters": len(final),
        },
    }
    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot v2.1 baseline and final prompts")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare_prompts(args.output_dir, args.manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

