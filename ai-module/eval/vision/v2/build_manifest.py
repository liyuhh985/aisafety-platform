from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import contract
from dedupe import dhash64, sha256_file

DEFAULT_SEED = 20261106
DEFAULT_POSITIVES_PER_MAJOR = 30
DEFAULT_NEGATIVES_PER_GROUP = 15
MIN_IMAGE_BYTES = 20_000
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}

# Explicit mapping from source folders to the canonical 25-class taxonomy.
SOURCE_TO_CANONICAL = {
    "falling_object": "facade_risk",
    "facade_fall": "facade_risk",
    "dangerous_building": "structural_damage",
    "wall_crack_lean": "structural_damage",
    "exposed_wire": "wire_fault",
    "illegal_wiring": "wire_fault",
    "temporary_power": "wire_fault",
    "fire_equipment_fault": "fire_facility",
    "fire_water_abnormal": "fire_facility",
    "no_warning": "construction_prot",
    "no_barrier": "construction_prot",
    "sewage_odor": "sewage_overflow",
}


@dataclass(frozen=True)
class Taxonomy:
    major_codes: tuple[str, ...]
    major_by_sub: dict[str, str]
    subcategories_by_major: dict[str, tuple[str, ...]]


def load_taxonomy(path: Path) -> Taxonomy:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    major_by_sub: dict[str, str] = {}
    subcategories_by_major: dict[str, list[str]] = {}
    major_codes: list[str] = []
    for major in data:
        code = major["code"]
        major_codes.append(code)
        subs: list[str] = []
        for sub in major.get("subcategories", []):
            sub_code = sub["code"]
            if sub_code in major_by_sub:
                raise ValueError(f"duplicate subcategory: {sub_code}")
            major_by_sub[sub_code] = code
            subs.append(sub_code)
        subcategories_by_major[code] = subs
    return Taxonomy(
        major_codes=tuple(major_codes),
        major_by_sub=major_by_sub,
        subcategories_by_major={k: tuple(v) for k, v in subcategories_by_major.items()},
    )


def canonical_code(source_category: str, taxonomy: Taxonomy) -> str | None:
    code = SOURCE_TO_CANONICAL.get(source_category, source_category)
    if code in taxonomy.major_by_sub:
        return code
    return None


def allocate_quotas(counts: dict[str, int], total: int, minimum: int) -> dict[str, int]:
    if total < 0 or minimum < 0:
        raise ValueError("total and minimum must be non-negative")
    active = {key: int(value) for key, value in counts.items() if value > 0}
    if total < len(active) * minimum or total > sum(active.values()):
        raise ValueError("insufficient capacity for requested quotas")

    quotas = {key: minimum for key in active}
    remaining = total - sum(quotas.values())
    while remaining > 0:
        progressed = False
        for key in sorted(active):
            if remaining == 0:
                break
            if quotas[key] < active[key]:
                quotas[key] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            raise ValueError("insufficient capacity for requested quotas")
    return quotas


def _shuffle_bucket(items: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: (item["sha256"], item.get("source_path", "")))
    random.Random(seed).shuffle(ordered)
    return ordered


def _pick_balanced(
    candidates: list[dict[str, Any]],
    quota: int,
    group_key: str,
    seed: int,
) -> list[dict[str, Any]]:
    if quota < 0:
        raise ValueError("quota must be non-negative")
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        buckets[str(item.get(group_key) or "")].append(item)

    for key in sorted(buckets):
        buckets[key] = _shuffle_bucket(buckets[key], seed)

    picked: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while len(picked) < quota:
        progressed = False
        for key in keys:
            if len(picked) >= quota:
                break
            if buckets[key]:
                picked.append(buckets[key].pop(0))
                progressed = True
        if not progressed:
            raise ValueError(f"not enough candidates to pick quota {quota}")
    return picked


def _pick_with_seed_priority(
    candidates: list[dict[str, Any]],
    quota: int,
    seed: int,
) -> list[dict[str, Any]]:
    seeds = [item for item in candidates if item.get("label_status") in {"reviewed", "excluded"}]
    pending = [item for item in candidates if item.get("label_status") not in {"reviewed", "excluded"}]
    if len(seeds) >= quota:
        return _pick_balanced(seeds, quota, "source_category", seed)
    picked = list(seeds)
    remaining = quota - len(picked)
    if remaining:
        picked.extend(_pick_balanced(pending, remaining, "source_category", seed))
    return picked


def collect_excluded_hashes(vision_dir: Path) -> set[str]:
    excluded: set[str] = set()
    for name in ("test_set", "images_merged"):
        base = Path(vision_dir) / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                excluded.add(sha256_file(path))
    return excluded


def collect_positive_candidates(
    vision_dir: Path,
    taxonomy: Taxonomy,
    excluded_hashes: set[str],
) -> list[dict[str, Any]]:
    pool = Path(vision_dir) / "pool"
    if not pool.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    seen = set(excluded_hashes)

    for source_dir in sorted(pool.iterdir()):
        if not source_dir.is_dir():
            continue
        annotation_path = source_dir / "annotations.json"
        if not annotation_path.is_file():
            continue
        annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
        items = annotations.get("items", {})
        if not isinstance(items, dict):
            items = {}
        mapped = canonical_code(source_dir.name, taxonomy)
        if not mapped:
            continue

        rejected: set[str] = set()
        for record in annotations.get("rejected", []):
            if isinstance(record, dict) and record.get("file"):
                rejected.add(record["file"])
            elif isinstance(record, str):
                rejected.add(record)

        audit2_path = source_dir / "audit2.json"
        invalid: set[str] = set()
        if audit2_path.is_file():
            audit2 = json.loads(audit2_path.read_text(encoding="utf-8"))
            invalid = {row.get("file") for row in audit2.get("invalid", [])}

        review_dir = source_dir / "review"
        if not review_dir.is_dir():
            continue
        for source_path in sorted(review_dir.iterdir()):
            if not source_path.is_file() or source_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            filename = source_path.name
            if filename in rejected or filename in invalid:
                continue
            known = items.get(filename)
            if isinstance(known, dict) and known.get("has_hazard") is False:
                continue
            if source_path.stat().st_size < MIN_IMAGE_BYTES:
                continue
            digest = sha256_file(source_path)
            if digest in seen:
                continue
            seen.add(digest)
            candidates.append({
                "file": filename,
                "source_path": str(source_path.resolve()),
                "source_category": source_dir.name,
                "mapped_category": mapped,
                "major_category": taxonomy.major_by_sub[mapped],
                "confuser_group": taxonomy.major_by_sub[mapped],
                "candidate_kind": "positive",
                "sha256": digest,
                "dhash64": dhash64(source_path),
                "prelabel_confidence": known.get("label_confidence", "") if isinstance(known, dict) else "",
                "label_status": "pending_review",
                "label_source": "",
            })
    return candidates


def collect_negative_candidates(
    vision_dir: Path,
    taxonomy: Taxonomy,
    excluded_hashes: set[str],
) -> list[dict[str, Any]]:
    neg_root = Path(vision_dir) / "negatives"
    if not neg_root.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    seen = set(excluded_hashes)

    for source_dir in sorted(neg_root.iterdir()):
        if not source_dir.is_dir():
            continue
        mapped = canonical_code(source_dir.name, taxonomy)
        if not mapped:
            continue
        for source_path in sorted(source_dir.iterdir()):
            if not source_path.is_file() or source_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if source_path.stat().st_size < MIN_IMAGE_BYTES:
                continue
            digest = sha256_file(source_path)
            if digest in seen:
                continue
            seen.add(digest)
            candidates.append({
                "file": source_path.name,
                "source_path": str(source_path.resolve()),
                "source_category": source_dir.name,
                "mapped_category": mapped,
                "major_category": "",
                "confuser_group": taxonomy.major_by_sub[mapped],
                "candidate_kind": "negative",
                "sha256": digest,
                "dhash64": dhash64(source_path),
                "prelabel_confidence": "",
                "label_status": "pending_review",
                "label_source": "",
            })
    return candidates


def select_candidate_reservoir(
    items: list[dict[str, Any]],
    positives_per_major: int = DEFAULT_POSITIVES_PER_MAJOR,
    negatives_per_group: int = DEFAULT_NEGATIVES_PER_GROUP,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, Any]]:
    positives = [dict(item) for item in items if item.get("candidate_kind") == "positive"]
    negatives = [dict(item) for item in items if item.get("candidate_kind") == "negative"]
    selected: list[dict[str, Any]] = []

    for major in contract.MAJOR_CODES:
        group = [item for item in positives if item.get("major_category") == major]
        if len(group) < contract.PER_MAJOR:
            raise ValueError(f"{major}: {len(group)} positive candidates, need {contract.PER_MAJOR}")
        quota = min(positives_per_major, len(group))
        selected.extend(_pick_with_seed_priority(group, quota, seed))

    for offset, group_name in enumerate(contract.MAJOR_CODES, start=1):
        group = [item for item in negatives if item.get("confuser_group") == group_name]
        if len(group) < contract.PER_CONFUSER_GROUP:
            raise ValueError(
                f"{group_name}: {len(group)} negative candidates, need {contract.PER_CONFUSER_GROUP}"
            )
        quota = min(negatives_per_group, len(group))
        selected.extend(_pick_with_seed_priority(group, quota, seed + offset * 100))

    return selected

def apply_seed_decisions(items: list[dict[str, Any]], decisions_path: Path) -> int:
    path = Path(decisions_path)
    if not path.is_file():
        return 0

    by_path = {item.get("source_path", ""): item for item in items}
    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_sha[str(item.get("sha256", ""))].append(item)

    applied = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        decision = json.loads(line)
        label_source = str(decision.get("label_source", "")).strip()
        if label_source == "ai_direct":
            raise ValueError("ai_direct cannot be used as a v2.1 seed label")
        if label_source not in contract.ALLOWED_LABEL_SOURCES:
            raise ValueError(f"unsupported seed label source: {label_source!r}")

        status = decision.get("label_status")
        if status not in {"reviewed", "excluded"}:
            raise ValueError(f"seed label_status must be reviewed or excluded: {status!r}")

        target = by_path.get(str(decision.get("source_path", "")))
        if target is None and decision.get("sha256"):
            matches = by_sha.get(str(decision["sha256"]), [])
            if len(matches) > 1:
                raise ValueError(f"ambiguous seed sha256: {decision['sha256']}")
            target = matches[0] if matches else None
        if target is None:
            continue

        target.update({
            "has_hazard": decision.get("has_hazard"),
            "major_category": str(decision.get("major_category", "")).strip(),
            "subcategory": str(decision.get("subcategory", "")).strip(),
            "difficulty": str(decision.get("difficulty", "")).strip(),
            "text_in_image": decision.get("text_in_image"),
            "notes": str(decision.get("notes", "")).strip(),
            "reviewer": str(decision.get("reviewer", "")).strip(),
            "review_time": str(decision.get("review_time", "")).strip(),
            "label_status": status,
            "label_source": label_source,
        })
        if status == "excluded":
            target["exclude_reason"] = str(decision.get("exclude_reason", "")).strip()
        else:
            target.pop("exclude_reason", None)
        applied += 1
    return applied


def build_candidate_pool(
    vision_dir: Path,
    output_path: Path,
    seed_decisions_path: Path | None = None,
    seed: int = DEFAULT_SEED,
    positives_per_major: int = DEFAULT_POSITIVES_PER_MAJOR,
    negatives_per_group: int = DEFAULT_NEGATIVES_PER_GROUP,
) -> dict[str, Any]:
    vision_dir = Path(vision_dir)
    taxonomy = load_taxonomy(vision_dir / "_taxonomy_final.json")
    excluded = collect_excluded_hashes(vision_dir)
    positives = collect_positive_candidates(vision_dir, taxonomy, excluded)
    negatives = collect_negative_candidates(
        vision_dir,
        taxonomy,
        excluded | {item["sha256"] for item in positives},
    )

    all_items = positives + negatives
    seeded = apply_seed_decisions(all_items, seed_decisions_path) if seed_decisions_path else 0
    reservoir = select_candidate_reservoir(
        all_items,
        positives_per_major=positives_per_major,
        negatives_per_group=negatives_per_group,
        seed=seed,
    )

    manifest = {
        "_meta": {
            "version": "v2.1-candidate-pool",
            "protocol_version": contract.PROTOCOL_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "positives_per_major": positives_per_major,
            "negatives_per_group": negatives_per_group,
            "seed_decisions_path": str(seed_decisions_path) if seed_decisions_path else "",
            "seeded_labels": seeded,
            "available_positive_candidates": len(positives),
            "available_negative_candidates": len(negatives),
        },
        "items": reservoir,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the v2.1 visual evaluation candidate pool")
    parser.add_argument("--vision-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "candidate_pool.json")
    parser.add_argument("--seed-decisions", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--positives-per-major", type=int, default=DEFAULT_POSITIVES_PER_MAJOR)
    parser.add_argument("--negatives-per-group", type=int, default=DEFAULT_NEGATIVES_PER_GROUP)
    args = parser.parse_args()

    manifest = build_candidate_pool(
        vision_dir=args.vision_dir,
        output_path=args.output,
        seed_decisions_path=args.seed_decisions,
        seed=args.seed,
        positives_per_major=args.positives_per_major,
        negatives_per_group=args.negatives_per_group,
    )
    counts = {
        "positive": sum(item["candidate_kind"] == "positive" for item in manifest["items"]),
        "negative": sum(item["candidate_kind"] == "negative" for item in manifest["items"]),
    }
    print(f"wrote {args.output}")
    print(f"positive={counts['positive']} negative={counts['negative']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

