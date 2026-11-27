from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AI_MODULE_DIR = Path(__file__).resolve().parents[3]
if str(AI_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODULE_DIR))

from core.hazard_taxonomy import HAZARD_TAXONOMY

SOURCE_TO_V2A = {
    "wall_crack_lean": "dangerous_building",
    "facade_fall": "falling_object",
    "fire_water_abnormal": "fire_equipment_fault",
}


def production_taxonomy() -> list[dict]:
    return [
        {
            "code": major["code"],
            "label": major["label"],
            "subcategories": [
                {"code": code, "label": label}
                for code, label in major["subcategories"]
            ],
        }
        for major in HAZARD_TAXONOMY
    ]


def taxonomy_map(data: list[dict] | None = None) -> dict[str, str]:
    data = data or production_taxonomy()
    return {
        sub["code"]: major["code"]
        for major in data
        for sub in major.get("subcategories", [])
    }


def map_positive_label(item: dict, major_by_sub: dict[str, str]) -> tuple[str, str]:
    source = str(item.get("source_category") or "")
    subcategory = str(item.get("subcategory") or "")
    candidate = SOURCE_TO_V2A.get(source)
    if candidate is None:
        candidate = source if source in major_by_sub else subcategory
    if candidate not in major_by_sub:
        raise ValueError(
            "cannot map v2a label: source_category=%r subcategory=%r"
            % (source, subcategory)
        )
    return major_by_sub[candidate], candidate


def remap_manifest(source: dict, major_by_sub: dict[str, str], version: str) -> dict:
    data = json.loads(json.dumps(source, ensure_ascii=False))
    meta = data.setdefault("_meta", {})
    meta["taxonomy_version"] = version
    meta["taxonomy"] = "_taxonomy_v2a.json"
    meta["remapped_from"] = source.get("_meta", {}).get("version", "")

    for item in data.get("items", []):
        if item.get("has_hazard") is True:
            major, sub = map_positive_label(item, major_by_sub)
            item["major_category"] = major
            item["subcategory"] = sub
            if "mapped_category" in item:
                item["mapped_category"] = sub
        else:
            item["major_category"] = ""
            item["subcategory"] = ""
            if "mapped_category" in item:
                item["mapped_category"] = ""
    return data


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Taxonomy v2a vision artifacts")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output-dataset", type=Path, required=True)
    parser.add_argument("--output-test", type=Path, required=True)
    args = parser.parse_args()

    taxonomy = production_taxonomy()
    major_by_sub = taxonomy_map(taxonomy)
    if len(major_by_sub) != 29:
        raise ValueError("v2a taxonomy must contain exactly 29 subcategories")
    write_json(args.taxonomy, taxonomy)

    for source_path, output_path, version in (
        (args.dataset, args.output_dataset, "v2a-vision-consensus"),
        (args.test, args.output_test, "v2a-vision-frozen-test"),
    ):
        source = json.loads(Path(source_path).read_text(encoding="utf-8"))
        write_json(output_path, remap_manifest(source, major_by_sub, version))

    print("wrote taxonomy:", args.taxonomy)
    print("wrote dataset:", args.output_dataset)
    print("wrote test:", args.output_test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
