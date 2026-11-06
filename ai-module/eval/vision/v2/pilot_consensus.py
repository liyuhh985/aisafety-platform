from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import contract

AI_MODULE_DIR = Path(__file__).resolve().parents[3]
if str(AI_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODULE_DIR))

SUB_BY_MAJOR = {
    "traffic": {"road_occupancy", "vehicle_occupancy", "blind_path_occupied", "traffic_facility_damage"},
    "municipal": {"manhole_damage", "road_surface_collapse", "drainage_flood", "street_light_pole"},
    "fire": {"fire_lane_blocked", "fire_facility"},
    "building": {"structural_damage", "facade_risk", "illegal_structure"},
    "utility": {"wire_fault", "distribution_box_fault", "gas_leak", "gas_pipe_aging"},
    "construction": {"construction_prot", "scaffold_guard", "deep_pit"},
    "elevator_special": {"elevator_trapped", "elevator_stopped", "elevator_inspection"},
    "environment_other": {"garbage_pile", "sewage_overflow"},
}

DEFAULT_MODEL_A = "mimo-v2.6-flash"
DEFAULT_MODEL_B = "glm-5.3-flash"

ANNOTATOR_PROMPT = """你是城市安全隐患标注员。只根据画面中清晰可见的证据判断，不得依据新闻标题、字幕、常识或推测。

只输出 JSON：
{"has_hazard": true或false, "uncertain": true或false, "major_category": "大类码", "subcategory": "小类码", "evidence": "30字内可见证据"}

8 个大类及其小类：
traffic: road_occupancy(占道经营/乱堆乱放), vehicle_occupancy(车辆占道), blind_path_occupied(盲道占用), traffic_facility_damage(交通设施损坏)
municipal: manhole_damage(井盖缺失/破损), road_surface_collapse(路面塌陷), drainage_flood(排水/积水), street_light_pole(路灯/线杆损坏)
fire: fire_lane_blocked(消防通道占用), fire_facility(消防设施/水源异常)
building: structural_damage(结构损伤), facade_risk(外立面破损/坠落风险), illegal_structure(私搭乱建)
utility: wire_fault(电线裸露/私拉乱接), distribution_box_fault(配电设施故障), gas_leak(燃气泄漏), gas_pipe_aging(燃气管道老化)
construction: construction_prot(施工防护缺失), scaffold_guard(脚手架/临边防护), deep_pit(深基坑风险)
elevator_special: elevator_trapped(电梯困人), elevator_stopped(停运/异响), elevator_inspection(超期未检)
environment_other: garbage_pile(垃圾堆积), sewage_overflow(污水外溢)

规则：
- 画面清楚存在目标隐患：has_hazard=true，uncertain=false，并给出匹配的大类和小类。
- 画面清楚没有目标隐患：has_hazard=false，uncertain=false，大小类留空。
- 图片模糊、遮挡、只靠文字、场景有歧义或无法确认：uncertain=true，不要猜类别。
- 多隐患无法确定主类别时：uncertain=true。
- 只输出 JSON。"""


def _shuffle(items: list[dict], seed: int) -> list[dict]:
    ordered = sorted(items, key=lambda item: (item["sha256"], item["source_path"]))
    random.Random(seed).shuffle(ordered)
    return ordered


def select_pilot_sample(pool: dict, sample_size: int = 60, seed: int = 20261106) -> list[dict]:
    items = pool.get("items", [])
    positives = [item for item in items if item.get("candidate_kind") == "positive"]
    negatives = [item for item in items if item.get("candidate_kind") == "negative"]

    per_major = max(1, sample_size // 12)
    positive_target = per_major * len(contract.MAJOR_CODES)
    if positive_target > sample_size:
        positive_target = sample_size
        per_major = positive_target // len(contract.MAJOR_CODES)
    picked: list[dict] = []
    for index, major in enumerate(contract.MAJOR_CODES):
        group = [item for item in positives if item.get("major_category") == major]
        if len(group) < per_major:
            raise ValueError(f"{major}: {len(group)} positive candidates, need {per_major}")
        picked.extend(_shuffle(group, seed + index)[:per_major])

    remaining = sample_size - len(picked)
    if remaining < 0:
        raise ValueError("positive sample exceeds total sample size")
    base, extra = divmod(remaining, len(contract.MAJOR_CODES))
    for index, major in enumerate(contract.MAJOR_CODES):
        count = base + (1 if index < extra else 0)
        if count == 0:
            continue
        group = [item for item in negatives if item.get("confuser_group") == major]
        if len(group) < count:
            raise ValueError(f"{major}: {len(group)} negative candidates, need {count}")
        picked.extend(_shuffle(group, seed + 1000 + index)[:count])
    return picked


def normalize_annotation(raw: dict | None) -> dict:
    if not isinstance(raw, dict):
        return {"status": "invalid", "reason": "parse_failed"}
    uncertain = raw.get("uncertain")
    if not isinstance(uncertain, bool):
        return {"status": "invalid", "reason": "uncertain_not_bool"}
    has_hazard = raw.get("has_hazard")
    if not isinstance(has_hazard, bool):
        return {"status": "invalid", "reason": "has_hazard_not_bool"}
    evidence = str(raw.get("evidence") or "").strip()
    if uncertain:
        return {
            "status": "uncertain",
            "has_hazard": has_hazard,
            "uncertain": True,
            "major_category": "",
            "subcategory": "",
            "evidence": evidence,
        }

    major = str(raw.get("major_category") or "").strip()
    sub = str(raw.get("subcategory") or "").strip()
    if has_hazard:
        if major not in contract.MAJOR_CODES or sub not in SUB_BY_MAJOR[major]:
            return {"status": "invalid", "reason": "invalid_category", "evidence": evidence}
    elif major or sub:
        return {"status": "invalid", "reason": "negative_has_category", "evidence": evidence}
    return {
        "status": "valid",
        "has_hazard": has_hazard,
        "uncertain": False,
        "major_category": major if has_hazard else "",
        "subcategory": sub if has_hazard else "",
        "evidence": evidence,
    }


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right):
        raise ValueError("left and right must have the same length")
    if not left:
        return 0.0
    total = len(left)
    observed = sum(a == b for a, b in zip(left, right)) / total
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / total) * (right_counts[label] / total)
        for label in set(left_counts) | set(right_counts)
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def _major_label(label: dict) -> str:
    return label.get("major_category", "") if label.get("has_hazard") else "__none__"


def _sub_label(label: dict) -> str:
    return label.get("subcategory", "") if label.get("has_hazard") else "__none__"


def build_pilot_summary(items: list[dict], labels_a: dict[str, dict], labels_b: dict[str, dict]) -> dict:
    valid_pairs = []
    rejected = Counter()
    consensus_items = []
    consensus_exact = 0

    for item in items:
        sha = item["sha256"]
        a = labels_a.get(sha)
        b = labels_b.get(sha)
        if not a or not b or a.get("status") == "invalid" or b.get("status") == "invalid":
            rejected["invalid"] += 1
            continue
        if a.get("status") == "uncertain" or b.get("status") == "uncertain":
            rejected["uncertain"] += 1
            continue

        valid_pairs.append((a, b))
        if a["has_hazard"] != b["has_hazard"]:
            rejected["binary_disagreement"] += 1
            continue
        if _major_label(a) != _major_label(b):
            rejected["major_disagreement"] += 1
            continue

        exact = _sub_label(a) == _sub_label(b)
        if exact:
            consensus_exact += 1
        else:
            rejected["sub_disagreement"] += 1
        label = dict(a)
        if not exact and label.get("has_hazard"):
            label["subcategory"] = ""
        label["label_source"] = "model_consensus"
        label["annotation_models"] = ["A", "B"]
        consensus_items.append({"sha256": sha, "file": item.get("file", ""), "label": label})

    major_a = [_major_label(a) for a, _ in valid_pairs]
    major_b = [_major_label(b) for _, b in valid_pairs]
    sub_a = [_sub_label(a) for a, _ in valid_pairs]
    sub_b = [_sub_label(b) for _, b in valid_pairs]
    binary_agreement = (
        sum(a["has_hazard"] == b["has_hazard"] for a, b in valid_pairs) / len(valid_pairs)
        if valid_pairs else 0.0
    )
    major_agreement = (
        sum(a == b for a, b in zip(major_a, major_b)) / len(valid_pairs)
        if valid_pairs else 0.0
    )
    sub_agreement = (
        sum(a == b for a, b in zip(sub_a, sub_b)) / len(valid_pairs)
        if valid_pairs else 0.0
    )

    return {
        "total": len(items),
        "valid_pairs": len(valid_pairs),
        "binary_agreement": binary_agreement,
        "major_agreement": major_agreement,
        "sub_agreement": sub_agreement,
        "kappa_major": cohen_kappa(major_a, major_b),
        "kappa_sub": cohen_kappa(sub_a, sub_b),
        "consensus": {
            "binary_major": len(consensus_items),
            "exact": consensus_exact,
            "yield": len(consensus_items) / len(items) if items else 0.0,
        },
        "rejected": dict(sorted(rejected.items())),
        "consensus_items": consensus_items,
    }


def _run_model(items: list[dict], client, prompt: str, output_dir: Path, workers: int, temperature: float = 0.0) -> dict[str, dict]:
    def annotate(item: dict) -> tuple[str, dict, str | None]:
        try:
            raw = client.analyze(item["source_path"], prompt, temperature=temperature)
            parsed = client._extract_json(raw) if raw else None
            return item["sha256"], normalize_annotation(parsed), raw
        except Exception as exc:
            return item["sha256"], {"status": "invalid", "reason": f"request_failed:{type(exc).__name__}:{exc}"}, None

    results: dict[str, dict] = {}
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(annotate, item): item for item in items}
        for future in as_completed(futures):
            sha, label, raw = future.result()
            results[sha] = label
            (raw_dir / f"{sha}.json").write_text(
                json.dumps({"raw": raw, "label": label}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a two-model consensus pilot")
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model-a", default=DEFAULT_MODEL_A)
    parser.add_argument("--model-b", default=DEFAULT_MODEL_B)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    from mimo_client import VisionClient

    pool = json.loads(args.pool.read_text(encoding="utf-8"))
    sample = select_pilot_sample(pool, sample_size=args.sample_size, seed=args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "pilot_sample.json").write_text(
        json.dumps({"items": sample}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    clients = {}
    for key, model in (("A", args.model_a), ("B", args.model_b)):
        client = VisionClient("opendesign")
        client.model = model
        clients[key] = client

    labels_a = _run_model(sample, clients["A"], ANNOTATOR_PROMPT, args.output_dir / "A", args.workers, temperature=args.temperature)
    labels_b = _run_model(sample, clients["B"], ANNOTATOR_PROMPT, args.output_dir / "B", args.workers, temperature=args.temperature)
    summary = build_pilot_summary(sample, labels_a, labels_b)
    summary["annotators"] = {
        "A": args.model_a,
        "B": args.model_b,
        "provider": "opendesign",
        "temperature": args.temperature,
        "prompt_sha256": __import__("hashlib").sha256(ANNOTATOR_PROMPT.encode("utf-8")).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.output_dir / "labels_A.json").write_text(
        json.dumps(labels_a, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "labels_B.json").write_text(
        json.dumps(labels_b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "pilot_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "consensus_items"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


