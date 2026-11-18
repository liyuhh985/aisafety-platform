from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import contract
from build_manifest import collect_excluded_hashes
from dedupe import find_near_duplicate_pairs, hamming64

MAX_DHASH_DISTANCE = 4


def _eligible_item(item: dict) -> dict | None:
    if item.get("label_status") != "reviewed":
        return None
    if item.get("label_source") not in contract.ALLOWED_LABEL_SOURCES:
        return None

    has_hazard = item.get("has_hazard")
    if not isinstance(has_hazard, bool):
        raise ValueError(f"reviewed item requires boolean has_hazard: {item.get('file')}")
    major = str(item.get("major_category", "")).strip()
    subcategory = str(item.get("subcategory", "")).strip()
    candidate_kind = item.get("candidate_kind")

    if has_hazard:
        if candidate_kind != "positive":
            raise ValueError(f"candidate_kind mismatch for positive label: {item.get('file')}")
        if major not in contract.MAJOR_CODES:
            raise ValueError(f"invalid positive major_category: {major!r}")
        if not subcategory:
            raise ValueError(f"positive label requires subcategory: {item.get('file')}")
    else:
        if candidate_kind != "negative":
            raise ValueError(f"candidate_kind mismatch for negative label: {item.get('file')}")
        if major or subcategory:
            raise ValueError(f"negative label must not contain categories: {item.get('file')}")
        if item.get("confuser_group") not in contract.MAJOR_CODES:
            raise ValueError(f"invalid confuser_group: {item.get('confuser_group')!r}")
    return item


def _pick_far_enough(
    candidates: list[dict],
    count: int,
    seed: int,
    existing: list[dict],
) -> list[dict]:
    ordered = sorted(candidates, key=lambda item: (item["sha256"], item["source_path"]))
    random.Random(seed).shuffle(ordered)
    picked: list[dict] = []
    for item in ordered:
        if any(
            hamming64(int(item["dhash64"]), int(other["dhash64"])) <= MAX_DHASH_DISTANCE
            for other in existing + picked
        ):
            continue
        picked.append(item)
        if len(picked) == count:
            return picked
    raise ValueError(f"not enough non-duplicate candidates for quota {count}")


def _split_group(items: list[dict], seed: int) -> None:
    ordered = list(items)
    random.Random(seed).shuffle(ordered)
    for index, item in enumerate(ordered):
        item["split"] = "test" if index < contract.TEST_PER_MAJOR else "dev"


def select_reviewed_set(pool: dict, seed: int = 20261106) -> dict:
    eligible = [item for item in (_eligible_item(item) for item in pool.get("items", [])) if item]
    positives = [item for item in eligible if item["has_hazard"] is True]
    negatives = [item for item in eligible if item["has_hazard"] is False]

    selected: list[dict] = []
    for offset, major in enumerate(contract.MAJOR_CODES):
        group = [item for item in positives if item["major_category"] == major]
        if len(group) < contract.PER_MAJOR:
            raise ValueError(f"{major}: {contract.PER_MAJOR - len(group)}")
        selected.extend(
            _pick_far_enough(group, contract.PER_MAJOR, seed + 100 + offset, selected)
        )

    for offset, major in enumerate(contract.MAJOR_CODES):
        group = [item for item in negatives if item["confuser_group"] == major]
        if len(group) < contract.PER_CONFUSER_GROUP:
            raise ValueError(f"{major}: {contract.PER_CONFUSER_GROUP - len(group)}")
        selected.extend(
            _pick_far_enough(group, contract.PER_CONFUSER_GROUP, seed + 200 + offset, selected)
        )

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in selected:
        kind = "positive" if item["has_hazard"] else "negative"
        group_key = item["major_category"] if kind == "positive" else item["confuser_group"]
        grouped[(kind, group_key)].append(item)

    for offset, key in enumerate(sorted(grouped)):
        _split_group(grouped[key], seed + 300 + offset)

    manifest = {
        "_meta": {
            "version": "v2.1",
            "protocol_version": contract.PROTOCOL_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "positive_total": contract.POSITIVES,
            "negative_total": contract.NEGATIVES,
            "test_total": contract.TEST_ITEMS,
            "test_positive": contract.TEST_POSITIVES,
            "test_negative": contract.TEST_NEGATIVES,
            "positive_by_major": {major: contract.PER_MAJOR for major in contract.MAJOR_CODES},
            "negative_by_group": {
                major: contract.PER_CONFUSER_GROUP for major in contract.MAJOR_CODES
            },
        },
        "items": selected,
    }
    verify_manifest(manifest)
    return manifest


def verify_manifest(manifest: dict, vision_dir: Path | None = None) -> dict:
    items = manifest.get("items", [])
    if len(items) != contract.TOTAL_ITEMS:
        raise ValueError(f"expected 160 items, got {len(items)}")
    if any(item.get("label_status") != "reviewed" for item in items):
        raise ValueError("all final items must be reviewed")
    if any(item.get("label_source") not in contract.ALLOWED_LABEL_SOURCES for item in items):
        raise ValueError("final manifest contains disallowed label source")
    if any(
        (item.get("has_hazard") is True and item.get("candidate_kind") != "positive")
        or (item.get("has_hazard") is False and item.get("candidate_kind") != "negative")
        for item in items
    ):
        raise ValueError("candidate_kind mismatch in final manifest")

    test = [item for item in items if item.get("split") == "test"]
    dev = [item for item in items if item.get("split") == "dev"]
    test_pos = [item for item in test if item.get("has_hazard") is True]
    test_neg = [item for item in test if item.get("has_hazard") is False]
    if len(test) != contract.TEST_ITEMS or len(dev) != contract.TEST_ITEMS:
        raise ValueError(f"expected 80 test / 80 dev, got {len(test)} / {len(dev)}")
    if len(test_pos) != contract.TEST_POSITIVES or len(test_neg) != contract.TEST_NEGATIVES:
        raise ValueError(
            f"expected 40 positive / 40 negative test items, got {len(test_pos)} / {len(test_neg)}"
        )

    for major in contract.MAJOR_CODES:
        if sum(item.get("has_hazard") is True and item.get("major_category") == major for item in items) != contract.PER_MAJOR:
            raise ValueError(f"major {major} must contain 10 positives")
        if sum(item.get("has_hazard") is False and item.get("confuser_group") == major for item in items) != contract.PER_CONFUSER_GROUP:
            raise ValueError(f"confuser group {major} must contain 10 negatives")
        if sum(item.get("split") == "test" and item.get("has_hazard") is True and item.get("major_category") == major for item in items) != contract.TEST_PER_MAJOR:
            raise ValueError(f"major {major} must contain 5 test positives")
        if sum(item.get("split") == "test" and item.get("has_hazard") is False and item.get("confuser_group") == major for item in items) != contract.TEST_PER_CONFUSER_GROUP:
            raise ValueError(f"confuser group {major} must contain 5 test negatives")

    hashes = [item["sha256"] for item in items]
    if len(hashes) != len(set(hashes)):
        raise ValueError("duplicate SHA-256 in final manifest")
    duplicates = find_near_duplicate_pairs(items, MAX_DHASH_DISTANCE)
    if duplicates:
        left, right, distance = duplicates[0]
        raise ValueError(f"near duplicate pair: {left} {right} distance={distance}")

    if vision_dir is not None:
        excluded = collect_excluded_hashes(Path(vision_dir))
        overlap = excluded & set(hashes)
        if overlap:
            raise ValueError(f"v1 test overlap detected: {len(overlap)} images")

    return {
        "total": len(items),
        "positive": sum(item.get("has_hazard") is True for item in items),
        "negative": sum(item.get("has_hazard") is False for item in items),
        "dev": len(dev),
        "test": len(test),
        "test_positive": len(test_pos),
        "test_negative": len(test_neg),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Select the final v2.1 reviewed dataset")
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--vision-dir", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    if args.verify_only:
        manifest = json.loads(args.output.read_text(encoding="utf-8"))
        summary = verify_manifest(manifest, vision_dir=args.vision_dir)
    else:
        pool = json.loads(args.pool.read_text(encoding="utf-8"))
        manifest = select_reviewed_set(pool, seed=args.seed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = verify_manifest(manifest, vision_dir=args.vision_dir)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
