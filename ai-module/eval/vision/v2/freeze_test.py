from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import contract
from dedupe import find_near_duplicate_pairs

MAX_DHASH_DISTANCE = 4
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _label_sha(item: dict) -> str:
    payload = {
        "has_hazard": item.get("has_hazard"),
        "major_category": item.get("major_category", ""),
        "subcategory": item.get("subcategory", ""),
        "difficulty": item.get("difficulty", ""),
        "text_in_image": item.get("text_in_image"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_taxonomy(path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        sub["code"]: major["code"]
        for major in data
        for sub in major.get("subcategories", [])
    }


def _load_prompt_manifest(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("baseline", "final"):
        entry = data.get(key)
        if not isinstance(entry, dict) or not entry.get("id"):
            raise ValueError(f"prompt manifest missing {key} id")
        digest = str(entry.get("sha256", ""))
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"prompt manifest has invalid {key} sha256")
    return data


def freeze_test_manifest(
    manifest_path: Path,
    output_path: Path,
    protocol_version: str,
    prompt_manifest_path: Path,
    force: bool = False,
    taxonomy_path: Path | None = None,
) -> dict:
    output_path = Path(output_path)
    if output_path.exists() and not force:
        raise FileExistsError(f"frozen manifest already exists: {output_path}")
    if protocol_version != contract.PROTOCOL_VERSION:
        raise ValueError(f"protocol version must be {contract.PROTOCOL_VERSION}")

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    if len(items) != contract.TOTAL_ITEMS:
        raise ValueError(f"expected 160 items, got {len(items)}")
    if any(item.get("label_status") != "reviewed" for item in items):
        raise ValueError("all final items must be reviewed")
    if any(item.get("label_source") not in contract.ALLOWED_LABEL_SOURCES for item in items):
        raise ValueError("final manifest contains disallowed label source")

    test = [item for item in items if item.get("split") == "test"]
    dev = [item for item in items if item.get("split") == "dev"]
    test_pos = [item for item in test if item.get("has_hazard") is True]
    test_neg = [item for item in test if item.get("has_hazard") is False]
    if len(test) != contract.TEST_ITEMS:
        raise ValueError(f"expected 80 test items, got {len(test)}")
    if len(dev) != contract.TOTAL_ITEMS - contract.TEST_ITEMS:
        raise ValueError(f"expected 80 dev items, got {len(dev)}")
    if len(test_pos) != contract.TEST_POSITIVES or len(test_neg) != contract.TEST_NEGATIVES:
        raise ValueError(
            f"expected 40 positive / 40 negative test items, got {len(test_pos)} / {len(test_neg)}"
        )

    for major in contract.MAJOR_CODES:
        total = sum(item.get("has_hazard") is True and item.get("major_category") == major for item in items)
        test_count = sum(item.get("has_hazard") is True and item.get("major_category") == major for item in test)
        if total != contract.PER_MAJOR:
            raise ValueError(f"major {major} expected 10 positives, got {total}")
        if test_count != contract.TEST_PER_MAJOR:
            raise ValueError(f"test major {major} expected 5 positives, got {test_count}")

    taxonomy = _load_taxonomy(
        Path(taxonomy_path) if taxonomy_path else Path(__file__).resolve().parents[1] / "_taxonomy_final.json"
    )
    for item in items:
        has_hazard = item.get("has_hazard")
        if not isinstance(has_hazard, bool):
            raise ValueError(f"invalid has_hazard: {item.get('file')}")
        if has_hazard and item.get("candidate_kind") != "positive":
            raise ValueError(f"candidate_kind mismatch: {item.get('file')}")
        if not has_hazard and item.get("candidate_kind") != "negative":
            raise ValueError(f"candidate_kind mismatch: {item.get('file')}")
        major = item.get("major_category", "")
        subcategory = item.get("subcategory", "")
        if has_hazard:
            if taxonomy.get(subcategory) != major:
                raise ValueError(f"invalid taxonomy label: {item.get('file')}")
        elif major or subcategory:
            raise ValueError(f"negative label contains categories: {item.get('file')}")
        if not Path(item.get("source_path", "")).is_file():
            raise ValueError(f"source image missing: {item.get('file')}")

    hashes = [item["sha256"] for item in items]
    if len(hashes) != len(set(hashes)):
        raise ValueError("duplicate SHA-256 in final manifest")
    duplicates = find_near_duplicate_pairs(items, MAX_DHASH_DISTANCE)
    if duplicates:
        left, right, distance = duplicates[0]
        raise ValueError(f"near duplicate pair: {left} {right} distance={distance}")

    prompt_manifest = _load_prompt_manifest(Path(prompt_manifest_path))
    baseline_sha = prompt_manifest["baseline"]["sha256"]
    final_sha = prompt_manifest["final"]["sha256"]

    frozen_items = []
    for item in test:
        frozen_item = dict(item)
        frozen_item["file_sha256"] = item["sha256"]
        frozen_item["label_sha256"] = _label_sha(item)
        frozen_item["prompt_baseline_sha256"] = baseline_sha
        frozen_item["prompt_final_sha256"] = final_sha
        frozen_items.append(frozen_item)

    frozen = {
        "_meta": {
            "version": "v2.1",
            "protocol_version": protocol_version,
            "dataset_version": manifest.get("_meta", {}).get("version", ""),
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "test_total": len(test),
            "test_positive": len(test_pos),
            "test_negative": len(test_neg),
            "dev_total": len(dev),
            "major_positive_counts": {major: contract.TEST_PER_MAJOR for major in contract.MAJOR_CODES},
            "prompt_manifest": prompt_manifest,
        },
        "items": frozen_items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return frozen


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze the v2.1 test split")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-version", default=contract.PROTOCOL_VERSION)
    parser.add_argument("--prompt-manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    frozen = freeze_test_manifest(
        args.manifest,
        args.output,
        protocol_version=args.protocol_version,
        prompt_manifest_path=args.prompt_manifest,
        force=args.force,
        taxonomy_path=args.taxonomy,
    )
    print(f"froze {len(frozen['items'])} test items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
