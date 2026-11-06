from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import contract
from dedupe import find_near_duplicate_pairs, hamming64

MAX_DHASH_DISTANCE = 4


def normalize_consensus_items(pool_items: list[dict], consensus_rows: list[dict], annotators: dict) -> list[dict]:
    source_by_sha = {item["sha256"]: item for item in pool_items}
    normalized = []
    seen: set[str] = set()
    for row in consensus_rows:
        sha = row["sha256"]
        if sha in seen:
            continue
        source = source_by_sha.get(sha)
        if source is None:
            raise ValueError(f"consensus item not found in pool: {sha}")
        label = row["label"]
        if label.get("status") != "valid":
            continue
        has_hazard = label.get("has_hazard")
        if not isinstance(has_hazard, bool):
            continue

        item = dict(source)
        item["source_candidate_kind"] = source.get("candidate_kind", "")
        item["candidate_kind"] = "positive" if has_hazard else "negative"
        item["has_hazard"] = has_hazard
        item["difficulty"] = ""
        item["text_in_image"] = None
        item["notes"] = str(label.get("evidence", "")).strip()
        item["evidence"] = item["notes"]
        item["reviewer"] = "model_consensus"
        item["review_time"] = annotators.get("created_at", "")
        item["label_status"] = "reviewed"
        item["label_source"] = contract.MODEL_LABEL_SOURCE
        item["annotation_models"] = [annotators.get("A", ""), annotators.get("B", "")]
        item["annotation_mode"] = contract.MODEL_LABEL_SOURCE

        if has_hazard:
            major = str(label.get("major_category", "")).strip()
            if major not in contract.MAJOR_CODES:
                continue
            item["major_category"] = major
            item["subcategory"] = str(label.get("subcategory", "")).strip()
            item["confuser_group"] = str(source.get("confuser_group") or major)
        else:
            confuser_group = str(source.get("confuser_group", "")).strip()
            if confuser_group not in contract.MAJOR_CODES:
                continue
            item["major_category"] = ""
            item["subcategory"] = ""
            item["confuser_group"] = confuser_group
        normalized.append(item)
        seen.add(sha)
    return normalized


def _ordered_with_preference(items: list[dict], seed: int, preferred_key) -> list[dict]:
    preferred = [item for item in items if preferred_key(item)]
    fallback = [item for item in items if not preferred_key(item)]
    def shuffled(group: list[dict], offset: int) -> list[dict]:
        ordered = sorted(group, key=lambda item: (item["sha256"], item["source_path"]))
        random.Random(seed + offset).shuffle(ordered)
        return ordered
    return shuffled(preferred, 0) + shuffled(fallback, 10000)


def _pick_far_enough(
    candidates: list[dict],
    count: int,
    seed: int,
    existing: list[dict],
    preferred_key,
) -> list[dict]:
    picked: list[dict] = []
    for item in _ordered_with_preference(candidates, seed, preferred_key):
        if any(
            hamming64(int(item["dhash64"]), int(other["dhash64"])) <= MAX_DHASH_DISTANCE
            for other in existing + picked
        ):
            continue
        picked.append(item)
        if len(picked) == count:
            return picked
    raise ValueError(f"near duplicate constraint prevents quota {count}")


def _split_group(items: list[dict], seed: int) -> None:
    ordered = list(items)
    random.Random(seed).shuffle(ordered)
    for index, item in enumerate(ordered):
        item["split"] = "test" if index < contract.TEST_PER_MAJOR else "dev"


def verify_consensus_manifest(manifest: dict) -> dict:
    items = manifest.get("items", [])
    if len(items) != contract.TOTAL_ITEMS:
        raise ValueError(f"expected 160 items, got {len(items)}")
    if any(item.get("label_source") != contract.MODEL_LABEL_SOURCE for item in items):
        raise ValueError("all consensus items must use model_consensus labels")
    if any(item.get("label_status") != "reviewed" for item in items):
        raise ValueError("all consensus items must be reviewed")
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
        raise ValueError("duplicate SHA-256 in consensus manifest")
    pairs = find_near_duplicate_pairs(items, MAX_DHASH_DISTANCE)
    if pairs:
        left, right, distance = pairs[0]
        raise ValueError(f"near duplicate pair: {left} {right} distance={distance}")
    return {
        "total": len(items),
        "positive": sum(item.get("has_hazard") is True for item in items),
        "negative": sum(item.get("has_hazard") is False for item in items),
        "dev": len(dev),
        "test": len(test),
        "test_positive": len(test_pos),
        "test_negative": len(test_neg),
    }


def select_consensus_dataset(items: list[dict], seed: int = 20261106) -> dict:
    eligible = [
        item for item in items
        if item.get("label_status") == "reviewed"
        and item.get("label_source") == contract.MODEL_LABEL_SOURCE
    ]
    positives = [item for item in eligible if item.get("has_hazard") is True]
    negatives = [item for item in eligible if item.get("has_hazard") is False]

    selected: list[dict] = []
    for offset, major in enumerate(contract.MAJOR_CODES):
        group = [item for item in positives if item.get("major_category") == major]
        if len(group) < contract.PER_MAJOR:
            raise ValueError(f"{major}: {contract.PER_MAJOR - len(group)}")
        selected.extend(
            _pick_far_enough(
                group,
                contract.PER_MAJOR,
                seed + 100 + offset,
                selected,
                lambda item: bool(item.get("subcategory")),
            )
        )

    for offset, major in enumerate(contract.MAJOR_CODES):
        group = [item for item in negatives if item.get("confuser_group") == major]
        if len(group) < contract.PER_CONFUSER_GROUP:
            raise ValueError(f"{major}: {contract.PER_CONFUSER_GROUP - len(group)}")
        selected.extend(
            _pick_far_enough(
                group,
                contract.PER_CONFUSER_GROUP,
                seed + 200 + offset,
                selected,
                lambda item: item.get("source_candidate_kind") == "negative",
            )
        )

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in selected:
        kind = "positive" if item["has_hazard"] else "negative"
        key = item["major_category"] if kind == "positive" else item["confuser_group"]
        grouped[(kind, key)].append(item)
    for offset, key in enumerate(sorted(grouped)):
        _split_group(grouped[key], seed + 300 + offset)

    manifest = {
        "_meta": {
            "version": contract.MODEL_PROTOCOL_VERSION,
            "protocol_version": contract.MODEL_PROTOCOL_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "annotation_mode": contract.MODEL_LABEL_SOURCE,
            "label_source": contract.MODEL_LABEL_SOURCE,
            "human_reviewed": False,
            "positive_total": contract.POSITIVES,
            "negative_total": contract.NEGATIVES,
            "test_total": contract.TEST_ITEMS,
            "test_positive": contract.TEST_POSITIVES,
            "test_negative": contract.TEST_NEGATIVES,
        },
        "items": selected,
    }
    verify_consensus_manifest(manifest)
    return manifest


def build_dataset(pairs: list[tuple[Path, Path]], output_path: Path, seed: int = 20261106) -> dict:
    all_items = []
    for pool_path, summary_path in pairs:
        pool = json.loads(Path(pool_path).read_text(encoding="utf-8"))
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
        all_items.extend(
            normalize_consensus_items(
                pool.get("items", []),
                summary.get("consensus_items", []),
                summary.get("annotators", {}),
            )
        )
    manifest = select_consensus_dataset(all_items, seed=seed)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the v2.1 model-consensus dataset")
    parser.add_argument("--pool", type=Path, action="append", required=True)
    parser.add_argument("--summary", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261106)
    args = parser.parse_args()
    if len(args.pool) != len(args.summary):
        raise SystemExit("--pool and --summary must be provided in pairs")
    manifest = build_dataset(list(zip(args.pool, args.summary)), args.output, seed=args.seed)
    print(json.dumps(verify_consensus_manifest(manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
