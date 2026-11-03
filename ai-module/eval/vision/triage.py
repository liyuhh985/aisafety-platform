# -*- coding: utf-8 -*-
"""
粗筛分诊（用视觉模型快速批量判断，只做"扔垃圾"，不做最终标注）

为什么要它：
    逐张精细复核 2835 张要十几小时，但其中约 70% 是明显不合格的
    （产品图、正面案例、整改现场、示意图）。这些不需要人看，
    模型扫一眼就能扔掉。粗筛后只剩真正需要细看的几百张。

铁律（防止把测试集筛得过于容易）：
    1. 只允许扔掉"明显不是该类别隐患"的图
    2. 拿不准的一律 KEEP，交给人工复核
    3. 真正的隐患现场（包括难图、模糊图、远景图）一律 KEEP
    4. 粗筛结果不直接作为标注，只是决定"要不要细看"

用法：
    python triage.py --cat manhole_damage            # 单类
    python triage.py --cat manhole_damage --limit 10  # 冒烟
    python triage.py --cat manhole_damage --validate  # 与已复核结果对比
"""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

POOL = os.path.join(_HERE, "pool")

try:
    from json_repair import repair_json
except Exception:
    repair_json = None


def load_taxonomy():
    tax = json.load(open(os.path.join(_HERE, "_taxonomy.json"), encoding="utf-8-sig"))
    m = {}
    for maj in tax:
        for sub in maj["subcategories"]:
            m[sub["code"]] = {"major": maj["label"], "major_code": maj["code"],
                              "label": sub["label"]}
    return m


TAX = load_taxonomy()

PROMPT_TMPL = """你是安全隐患图片审核员。请判断这张图片是否可以作为「{major} / {label}」这一类别的**隐患现场**样本。

判定标准：

**DROP（不合格，扔掉）** — 满足任一即 DROP：
1. 画面主体不是该类隐患（拍的是别的东西、别的隐患类型）
2. 设施完好规范、无任何隐患（正面案例）
3. 正在整改处置中：工人正在维修/更换/清理/施工（隐患已被处置）
4. 商品图、产品图、广告图、宣传海报
5. 插画、漫画、示意图、CAD图、AI合成图
6. 拼接图、左右对比图、修复前后对比
7. 带大面积图库售卖水印（dreamstime/shutterstock/视觉中国等）

**KEEP（合格，保留）** — 同时满足：
1. 真实拍摄的照片
2. 画面主体确实是「{label}」这一类的隐患，且处于**未被处置的危险状态**
3. 不因画质差、主体小、远景、夜间、模糊而 DROP —— 这些照样 KEEP

**重要：拿不准就 KEEP。** 宁可多留给人看，不可错杀。只有你确信属于上面 7 种 DROP 情况时才判 DROP。

只输出 JSON，不要任何解释：
{{"verdict": "KEEP" 或 "DROP", "reason": "若DROP，填以下之一：非该类别/正面案例/整改中/产品广告/示意图/拼接对比/图库水印；若KEEP则留空", "what": "画面主体是什么，20字内"}}
"""


def triage_one(client, path, cat, retries=3):
    """带退避重试。网络/限流失败时重试，最终仍失败则保守保留。"""
    import time as _t
    info = TAX.get(cat, {"major": "隐患", "label": cat})
    prompt = PROMPT_TMPL.format(major=info["major"], label=info["label"])

    last_err = None
    for attempt in range(retries):
        try:
            out = client.analyze_json(path, prompt)
            if out is None:
                raw = client.analyze(path, prompt)
                if raw and repair_json:
                    out = repair_json(raw)
            if not isinstance(out, dict):
                return {"verdict": "KEEP", "reason": "", "what": "",
                        "note": "解析失败→保守保留"}
            v = str(out.get("verdict", "")).strip().upper()
            if v not in ("KEEP", "DROP"):
                return {"verdict": "KEEP", "what": str(out.get("what", "")),
                        "reason": "", "note": f"verdict非法({v})→保守保留"}
            return {"verdict": v, "reason": str(out.get("reason", "")),
                    "what": str(out.get("what", ""))}
        except Exception as e:
            last_err = type(e).__name__
            if attempt < retries - 1:
                _t.sleep(2 * (attempt + 1))   # 2s, 4s 退避
    return {"verdict": "KEEP", "reason": "", "what": "",
            "note": f"异常{last_err}→保守保留"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--validate", action="store_true", help="与已复核结果对比准确率")
    args = ap.parse_args()

    d = os.path.join(POOL, args.cat)
    kp = os.path.join(d, "keep.json")
    if not os.path.isfile(kp):
        print(f"[错误] 先跑 screen.py")
        return 1
    items = json.load(open(kp, encoding="utf-8"))["items"]
    if args.limit:
        items = items[: args.limit]

    try:
        from mimo_client import MiMoVisionClient
    except Exception as e:
        print(f"[错误] 无法导入 MiMoVisionClient: {e}")
        return 1
    client = MiMoVisionClient()
    print(f"[{args.cat}] 粗筛 {len(items)} 张  模型={getattr(client, 'model', '?')}  并发={args.workers}")

    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(triage_one, client,
                          os.path.join(d, "review", it["file"]), args.cat): it["file"]
                for it in items}
        for f in as_completed(futs):
            fname = futs[f]
            results[fname] = f.result()
            done += 1
            if done % 20 == 0 or done == len(items):
                print(f"  进度 {done}/{len(items)}")

    keep = [f for f, r in results.items() if r["verdict"] == "KEEP"]
    drop = [f for f, r in results.items() if r["verdict"] == "DROP"]
    print(f"\n  保留 {len(keep)}  丢弃 {len(drop)}  丢弃率 {len(drop)/max(len(items),1)*100:.0f}%")

    from collections import Counter
    reasons = Counter(r["reason"] for r in results.values() if r["verdict"] == "DROP")
    for k, v in reasons.most_common(10):
        print(f"    - {k}: {v}")

    out = {
        "category": args.cat,
        "model": getattr(client, "model", "?"),
        "total": len(items),
        "keep": keep,
        "drop": [{"file": f, "reason": results[f]["reason"],
                  "what": results[f]["what"]} for f in drop],
        "detail": results,
    }
    json.dump(out, open(os.path.join(d, "triage.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n  已写入 {os.path.join(d, 'triage.json')}")

    # ---- 校验模式：与已完成的精细复核对比 ----
    if args.validate:
        ann_p = os.path.join(d, "annotations.json")
        gt = {}
        odir = os.path.join(d, "review_out")
        if os.path.isdir(odir):
            for f in os.listdir(odir):
                if not f.startswith("batch_"):
                    continue
                try:
                    data = json.load(open(os.path.join(odir, f), encoding="utf-8"))
                    if isinstance(data, dict):
                        data = data.get("items", [])
                    for rec in data:
                        if isinstance(rec, dict) and "file" in rec:
                            gt[rec["file"]] = rec.get("verdict")
                except Exception:
                    pass
        common = [f for f in results if f in gt]
        if not common:
            print("\n  [校验] 没有可对比的已复核样本")
            return 0
        agree = sum(1 for f in common
                    if (results[f]["verdict"] == "KEEP") == (gt[f] == "keep"))
        print(f"\n  [校验] 可对比 {len(common)} 张，一致 {agree} 张，"
              f"一致率 {agree/len(common)*100:.1f}%")
        # 混淆矩阵
        tp = sum(1 for f in common if results[f]["verdict"] == "KEEP" and gt[f] == "keep")
        fp = sum(1 for f in common if results[f]["verdict"] == "KEEP" and gt[f] == "reject")
        fn = sum(1 for f in common if results[f]["verdict"] == "DROP" and gt[f] == "keep")
        tn = sum(1 for f in common if results[f]["verdict"] == "DROP" and gt[f] == "reject")
        print(f"         粗筛KEEP & 复核keep  {tp}   粗筛KEEP & 复核reject {fp}")
        print(f"         粗筛DROP & 复核keep  {fn}   粗筛DROP & 复核reject {tn}")
        if fn:
            print(f"  ⚠️ 错杀 {fn} 张（真正合格的被粗筛扔掉）：")
            for f in common:
                if results[f]["verdict"] == "DROP" and gt[f] == "keep":
                    print(f"      {f:<14} 粗筛理由={results[f]['reason']:<10} {results[f]['what'][:30]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
