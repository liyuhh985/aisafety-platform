# -*- coding: utf-8 -*-
"""
标注质量批量排查

发现的问题模式：
  1. 叠加文字未剔除 —— 画面上压着大字（"危险房屋 紧急撤离"、"曝光台"等）
     违反规则"文字是唯一信息源必须淘汰"
  2. 类别误判 —— 天花板渗水被标成"危房"

本脚本用模型专项复检这两类问题，不改动原标注，只输出可疑清单。

用法：
    python audit.py --cat dangerous_building
    python audit.py --all
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

POOL = os.path.join(_HERE, "pool")

tax = json.load(open(os.path.join(_HERE, "_taxonomy.json"), encoding="utf-8-sig"))
LABEL = {}
for m in tax:
    for s in m["subcategories"]:
        LABEL[s["code"]] = {"major": m["label"], "label": s["label"], "code": s["code"]}

PROMPT = """你是图片审核质检员。这张图已被标为「{major} / {label}」隐患，请严格核查。

## 第一步：这张图真的是「{label}」隐患吗？

用**该类别最核心的视觉特征**判断。但注意：**核心特征成立即可，不要因为"程度不够"或"细节差异"就否定。**

正确判断的例子：
- 「危房」：墙体大面积开裂、房屋明显倾斜、承重结构破坏、屋顶坍塌 → 是
  · 天花板渗水发霉、涂料剥落 → **不是**（这是渗漏，另属别类）
  · 外墙瓷砖局部脱落 → **不是**（属外立面脱落）
- 「井盖缺失/破损」：井盖破洞、缺失、塌陷成坑、**错位翘起露出洞口** → 是
  · 井盖虽完整但明显移位、露出下方黑洞 → **是**（行人会掉下去）
  · 仅仅是井盖周边路面轻微裂缝、井盖平整无异常 → 不是
- 「垃圾堆积」：成堆垃圾长时间未清理 → 是
  · 地上几片纸屑、落叶 → 不是
- 「燃气泄漏」：能看出燃气管道破损、腐蚀穿孔、阀门损坏 → 是
  · 爆炸火球、消防演练、单纯一根完好管道 → **不是**（看不到泄漏本体）

**判断口诀**：问自己"一个普通路人看这张图，能不能意识到这里有安全隐患？"能 → 是。

拿不准时判 `category_ok = true`（宁可放过，不要错杀）。

## 第二步：是否有叠加文字（overlay_text）

**叠加文字** = 后来压到画面上的字：字幕条、大字标题、彩色说明框、"曝光台"字样、新闻标题块。
**不算叠加** = 物体本来带的字：车牌、店招、地面喷字、物品标识、**角落/边角的媒体水印**（如"齐鲁晚报""溧水114""央视新闻"logo）。

只要叠加文字**不是唯一信息源**（遮住字仍能看出隐患），就判 `text_is_only_source = false`。

## 第三步：硬伤检查
- 拼接图/左右对比图 → `spliced = true`
- 明显AI合成/插画/卡通 → `not_photo = true`
- **大面积售卖水印**（dreamstime/shutterstock 满屏水印、居中大logo）→ `watermark = true`
  · 仅角落小字媒体水印 → `watermark = false`

只输出 JSON：
{{"category_ok": true或false, "actual_subject": "画面主体实际是什么，20字内", "core_feature_present": "该类别的核心特征在画面中是否可见，一句话", "overlay_text": true或false, "text_content": "叠加的文字内容，没有则空", "text_is_only_source": true或false, "spliced": true或false, "not_photo": true或false, "watermark": true或false, "reason": "若不通过，一句话说明"}}
"""


def check(client, path, cat, retries=3):
    info = LABEL.get(cat, {"major": "隐患", "label": cat})
    prompt = PROMPT.format(major=info["major"], label=info["label"])
    for att in range(retries):
        try:
            out = client.analyze_json(path, prompt)
            if isinstance(out, dict):
                return out
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ("402", "401", "403", "Payment Required")):
                raise
            if att < retries - 1:
                time.sleep(2 * (att + 1))
    return None


def audit_cat(client, cat, workers):
    p = os.path.join(POOL, cat, "annotations.json")
    if not os.path.isfile(p):
        return None
    j = json.load(open(p, encoding="utf-8"))
    items = j.get("items", {})
    if not items:
        return None

    print(f"{cat:<26} 复检 {len(items):>3} 张", end="", flush=True)
    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(check, client, os.path.join(POOL, cat, "review", f), cat): f
                for f in items}
        for fu in as_completed(futs):
            f = futs[fu]
            try:
                res[f] = fu.result()
            except Exception:
                res[f] = None

    suspect = []
    for f, r in res.items():
        if not r:
            continue
        issues = []
        if r.get("text_is_only_source") is True:
            issues.append("文字是唯一来源")
        if r.get("category_ok") is False:
            issues.append("类别不符")
        if r.get("spliced") is True:
            issues.append("拼接对比图")
        if r.get("not_photo") is True:
            issues.append("非真实照片")
        if r.get("watermark") is True:
            issues.append("图库水印")
        if issues:
            suspect.append({
                "file": f,
                "path": os.path.join(POOL, cat, "review", f),
                "issue": " + ".join(issues),
                "text_content": r.get("text_content", ""),
                "actual_subject": r.get("actual_subject", ""),
                "core_feature": r.get("core_feature_present", ""),
                "reason": r.get("reason", ""),
                "severity": items.get(f, {}).get("severity"),
            })

    print(f"\r{cat:<26} {len(items):>3} 张 → 可疑 {len(suspect):>3} "
          f"({len(suspect)/len(items)*100:.0f}%)")

    out = os.path.join(POOL, cat, "audit.json")
    json.dump({"category": cat, "total": len(items), "suspect": suspect},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"cat": cat, "total": len(items), "suspect": suspect}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    from mimo_client import MiMoVisionClient
    client = MiMoVisionClient()
    print(f"模型={client.model}\n")

    if args.all:
        cats = sorted([d for d in os.listdir(POOL)
                       if os.path.isfile(os.path.join(POOL, d, "annotations.json"))])
    else:
        cats = [args.cat]

    T = S = 0
    for c in cats:
        r = audit_cat(client, c, args.workers)
        if r:
            T += r["total"]
            S += len(r["suspect"])

    print()
    print("=" * 60)
    print(f"复检 {T} 张，发现可疑 {S} 张（{S/max(T,1)*100:.1f}%）")
    print("可疑清单已写入各类 pool/<cat>/audit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
