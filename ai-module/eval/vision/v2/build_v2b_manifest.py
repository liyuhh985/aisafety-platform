from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

AI_MODULE_DIR=Path(__file__).resolve().parents[3]
if str(AI_MODULE_DIR) not in sys.path:
    sys.path.insert(0,str(AI_MODULE_DIR))

from build_v2a_manifest import (
    SOURCE_TO_V2A,
    production_taxonomy,
    taxonomy_map,
    write_json,
)


def map_positive_label(item: dict, major_by_sub: dict[str,str]) -> tuple[str,str]:
    source=str(item.get("source_category") or "")
    subcategory=str(item.get("subcategory") or "")
    notes=" ".join(str(item.get(key) or "") for key in ("notes","evidence","description"))
    candidate=SOURCE_TO_V2A.get(source)
    if candidate is None and source in {"illegal_wiring","fire_lane_blocked"} and (
        "电动自行车" in notes or "飞线" in notes or "电池入户" in notes
    ):
        candidate="ebike_hazard"
    if candidate is None and source=="road_surface_collapse" and "树木倒伏" in notes:
        candidate="tree_fall_hazard"
    if candidate is None:
        candidate=source if source in major_by_sub else subcategory
    if candidate not in major_by_sub:
        raise ValueError("cannot map v2b label: source_category=%r subcategory=%r" % (source,subcategory))
    return major_by_sub[candidate],candidate


def remap_manifest(source: dict, major_by_sub: dict[str,str], version: str) -> dict:
    data=json.loads(json.dumps(source,ensure_ascii=False))
    meta=data.setdefault("_meta",{})
    meta["taxonomy_version"]=version
    meta["taxonomy"]="_taxonomy_v2b.json"
    for item in data.get("items",[]):
        if item.get("has_hazard") is True:
            major,sub=map_positive_label(item,major_by_sub)
            item["major_category"]=major
            item["subcategory"]=sub
            if "mapped_category" in item:
                item["mapped_category"]=sub
        else:
            item["major_category"]=""
            item["subcategory"]=""
            if "mapped_category" in item:
                item["mapped_category"]=""
    return data


def main() -> int:
    parser=argparse.ArgumentParser(description="Build Taxonomy v2b vision artifacts")
    parser.add_argument("--dataset",type=Path,required=True)
    parser.add_argument("--test",type=Path,required=True)
    parser.add_argument("--taxonomy",type=Path,required=True)
    parser.add_argument("--output-dataset",type=Path,required=True)
    parser.add_argument("--output-test",type=Path,required=True)
    args=parser.parse_args()
    taxonomy=production_taxonomy()
    major_by_sub=taxonomy_map(taxonomy)
    if len(major_by_sub)!=33:
        raise ValueError("v2b taxonomy must contain exactly 33 subcategories")
    write_json(args.taxonomy,taxonomy)
    for src,dst,version in (
        (args.dataset,args.output_dataset,"v2b-vision-consensus"),
        (args.test,args.output_test,"v2b-vision-frozen-test"),
    ):
        data=json.loads(Path(src).read_text(encoding="utf-8"))
        write_json(dst,remap_manifest(data,major_by_sub,version))
    print("wrote v2b vision artifacts")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
