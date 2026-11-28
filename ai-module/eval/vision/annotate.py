# -*- coding: utf-8 -*-
"""
详细标注（主进程并发调用视觉模型，替代子智能体逐批审核）

为什么换实现：
    子智能体方式每批要 10-20 分钟，110 批要十几小时，且会丢结果。
    改为在进程内并发调用模型，同一模型、同样提示词，速度提升一个数量级。

铁律：
    1. 拿不准 → 保留（KEEP），绝不因"看不清"而淘汰
    2. 文字规则：物体自带的字可收，叠加字/大标题/手持告示不收
    3. 只收「隐患现场」，整改中一律淘汰

用法：
    python annotate.py --cat manhole_damage --limit 10     # 冒烟
    python annotate.py --cat manhole_damage                # 单类全量
    python annotate.py --all --per-cat 40                  # 全部类别
    python annotate.py --cat xxx --validate                # 与子智能体结果对比
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
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


def load_tax():
    tax = json.load(open(os.path.join(_HERE, "_taxonomy.json"), encoding="utf-8-sig"))
    m = {}
    for maj in tax:
        for sub in maj["subcategories"]:
            m[sub["code"]] = {"major_code": maj["code"], "major": maj["label"],
                              "label": sub["label"]}
    return m


TAX = load_tax()

PROMPT = """你是城市安全隐患图片标注员。请判断这张图片能否作为「{major} / {label}」类别的评测样本，并给出标注。

## 第一步：是否可以收（verdict）

**DROP（不收）** — 满足任一：
1. `非该类别`：画面主体不是「{label}」，而是别的东西或别的隐患
2. `正面案例`：设施完好规范，没有任何隐患
3. `整改中`：工人正在维修/更换/清理/施工，隐患已被处置中
4. `产品广告`：商品图、产品展示图
5. `示意图`：插画、漫画、CAD图、AI合成图、宣传海报
6. `拼接对比`：多图拼接、左右对比、修复前后对比
7. `图库水印`：大面积售卖水印（dreamstime/shutterstock/视觉中国）
8. `文字是唯一信息源`：文字叠加在画面上（大字标题、字幕条、曝光台合成图），或手持打印纸/文件特写/纯标语图 —— 遮住文字就啥也看不出

**KEEP（收）** — 同时满足：
1. 真实拍摄照片
2. 画面主体确实是「{label}」隐患，且处于**未被处置的危险状态**

## 文字规则（关键）
判据：**把图中文字全部遮住，还能看出这是该类隐患吗？**
- 还能看出来 → KEEP。文字只是现场附属物（如地面喷的「消防通道」、门柱的禁停牌、井圈的铸字、桶身的分类标识）。必须记 text_in_image=true 和 text_content。
- 看不出来了 → DROP。文字是唯一信息源。

口诀：**物体自带的字可收；后来压上去的字不收。**

## 重要
- 画质差、主体小、远景、夜间、模糊 → **照样 KEEP**，只在 difficulty 标 hard
- 拿不准 → **KEEP**（宁可多留）

## 第二步：标注字段

- severity：`高`=危险直接威胁通行安全/可能致伤；`中`=明显隐患但需触发条件；`低`=轻微
- difficulty：`easy`=主体占画面1/3以上且特征清晰；`medium`=占1/10~1/3；`hard`=主体小/逆光/遮挡/夜间/模糊
- key_evidence：30字内，描述**画面上能看到什么**，不要写新闻标题

只输出 JSON：
{{"verdict":"KEEP或DROP","reject_reason":"DROP时填上述8种之一，KEEP留空","severity":"高或中或低","difficulty":"easy或medium或hard","key_evidence":"30字内画面特征","text_in_image":true或false,"text_content":"图中可读文字，无则空"}}
"""

REASONS = {"非该类别", "正面案例", "整改中", "产品广告", "示意图",
           "拼接对比", "图库水印", "文字是唯一信息源"}


class ApiUnavailable(Exception):
    """API 不可用（余额不足/鉴权失败），必须中止，不能当成样本判定"""


def one(client, path, cat, retries=3):
    info = TAX.get(cat, {"major_code": None, "major": "隐患", "label": cat})
    prompt = PROMPT.format(major=info["major"], label=info["label"])

    last = None
    for att in range(retries):
        try:
            out = client.analyze_json(path, prompt)
            if out is None:
                raw = client.analyze(path, prompt)
                if raw and repair_json:
                    out = repair_json(raw)
            if not isinstance(out, dict):
                return {"verdict": "keep", "reject_reason": "",
                        "severity": "中", "difficulty": "medium",
                        "key_evidence": "", "text_in_image": False,
                        "text_content": "", "_note": "解析失败→保守保留"}

            v = str(out.get("verdict", "")).strip().upper()
            if v not in ("KEEP", "DROP"):
                return {"verdict": "keep", "reject_reason": "",
                        "severity": "中", "difficulty": "medium",
                        "key_evidence": str(out.get("key_evidence", ""))[:40],
                        "text_in_image": bool(out.get("text_in_image")),
                        "text_content": str(out.get("text_content", "")),
                        "_note": f"verdict非法({v})→保守保留"}

            rec = {
                "verdict": v.lower(),
                "reject_reason": str(out.get("reject_reason", "")).strip() if v == "DROP" else "",
                "severity": str(out.get("severity", "中")).strip() or "中",
                "difficulty": str(out.get("difficulty", "medium")).strip() or "medium",
                "key_evidence": str(out.get("key_evidence", ""))[:60],
                "text_in_image": bool(out.get("text_in_image")),
                "text_content": str(out.get("text_content", ""))[:80],
            }
            # 规范化枚举
            if rec["severity"] not in ("高", "中", "低"):
                rec["severity"] = "中"
            if rec["difficulty"] not in ("easy", "medium", "hard"):
                rec["difficulty"] = "medium"
            if v == "DROP" and rec["reject_reason"] not in REASONS:
                rec["reject_reason"] = rec["reject_reason"] or "非该类别"
            if v == "DROP" and not rec["key_evidence"]:
                rec["key_evidence"] = "无隐患"
            rec["has_hazard"] = (v == "KEEP")
            rec["major_code"] = info["major_code"]
            rec["subcategory"] = cat
            return rec
        except Exception as e:
            msg = str(e)
            # 余额不足/鉴权失败 → 直接中止，绝不能当成"保留"
            if any(k in msg for k in ("402", "insufficient_balance",
                                      "Payment Required", "401", "Unauthorized")):
                raise ApiUnavailable(msg[:120])
            last = type(e).__name__
            if att < retries - 1:
                time.sleep(2 * (att + 1))
    return {"verdict": "keep", "reject_reason": "", "severity": "中",
            "difficulty": "medium", "key_evidence": "", "text_in_image": False,
            "text_content": "", "_note": f"异常{last}→保守保留",
            "has_hazard": True, "major_code": info["major_code"], "subcategory": cat}


def targets(cat, per_cat):
    """从 triage.json 取粗筛保留的图"""
    d = os.path.join(POOL, cat)
    tp = os.path.join(d, "triage.json")
    kp = os.path.join(d, "keep.json")
    if not os.path.isfile(kp):
        return []
    items = json.load(open(kp, encoding="utf-8"))["items"]
    if os.path.isfile(tp):
        tri = json.load(open(tp, encoding="utf-8"))
        keep = set(tri["keep"])
        items = [it for it in items if it["file"] in keep]
    # 已标注的跳过
    ap = os.path.join(d, "annotations.json")
    done = set()
    if os.path.isfile(ap):
        try:
            done = set(json.load(open(ap, encoding="utf-8")).get("items", {}))
        except Exception:
            pass
    items = [it for it in items if it["file"] not in done]
    # 等距抽样控制数量
    if per_cat and len(items) > per_cat:
        ranked = sorted(items, key=lambda x: -min(x.get("w") or 0, x.get("h") or 0))
        n = per_cat
        idx = [round(i * (len(ranked) - 1) / (n - 1)) for i in range(n)]
        seen, out = set(), []
        for i in idx:
            i = min(max(i, 0), len(ranked) - 1)
            if i in seen:
                continue
            seen.add(i)
            out.append(ranked[i])
        items = out
    return items


def run_cat(client, cat, per_cat, workers, validate=False):
    items = targets(cat, per_cat)
    if not items:
        print(f"{cat:<26} 无可标注图片")
        return None

    d = os.path.join(POOL, cat)
    print(f"{cat:<26} 开始标注 {len(items)} 张", end="", flush=True)

    res = {}
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, client, os.path.join(d, "review", it["file"]), cat): it["file"]
                for it in items}
        for f in as_completed(futs):
            fn = futs[f]
            res[fn] = f.result()
            done += 1
    kept = [f for f, r in res.items() if r["verdict"] == "keep"]
    dt = time.time() - t0
    print(f"\r{cat:<26} {len(items):>4} 张 → 留 {len(kept):>3} 弃 {len(items)-len(kept):>3}"
          f"  ({dt/60:.1f}分钟)")

    # 合并进 annotations.json
    ap = os.path.join(d, "annotations.json")
    old = {"items": {}, "rejected": []}
    if os.path.isfile(ap):
        try:
            old = json.load(open(ap, encoding="utf-8"))
        except Exception:
            pass
    old_items = old.get("items", {})
    old_rej = {x["file"]: x for x in old.get("rejected", [])}

    info = TAX.get(cat, {})
    for f, r in res.items():
        if r["verdict"] == "keep":
            old_items[f] = {
                "has_hazard": True,
                "major_category": r.get("major_code"),
                "subcategory": cat,
                "severity": r["severity"],
                "key_evidence": r["key_evidence"],
                "multi_hazard": False,
                "secondary_categories": [],
                "text_in_image": r["text_in_image"],
                "text_content": r["text_content"],
                "difficulty": r["difficulty"],
                "label_confidence": "high" if r["difficulty"] == "easy" else "medium",
                "is_negative_sample": False,
                "notes": r.get("_note", ""),
            }
            old_rej.pop(f, None)
        else:
            old_rej[f] = {"file": f, "reason": r["reject_reason"],
                          "detail": r["key_evidence"]}
            old_items.pop(f, None)

    out = {
        "category": cat,
        "total": len(res) + len(old_items) - len([f for f in res if f in old_items]),
        "keep": len(old_items),
        "reject": len(old_rej),
        "items": old_items,
        "rejected": list(old_rej.values()),
    }
    json.dump(out, open(ap, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    reasons = Counter(r["reject_reason"] for r in res.values() if r["verdict"] == "drop")
    if reasons:
        print(f"{'':26} 淘汰原因: " + ", ".join(f"{k}{v}" for k, v in reasons.most_common(5)))

    if validate:
        do_validate(d, res)
    return out


def do_validate(d, res):
    """与子智能体已复核结果对比"""
    odir = os.path.join(d, "review_out")
    gold = {}
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
                        gold[rec["file"]] = rec.get("verdict")
            except Exception:
                pass
    common = [f for f in res if f in gold]
    if not common:
        return
    agree = sum(1 for f in common if res[f]["verdict"] == gold[f])
    tp = sum(1 for f in common if res[f]["verdict"] == "keep" and gold[f] == "keep")
    fp = sum(1 for f in common if res[f]["verdict"] == "keep" and gold[f] == "reject")
    fn = sum(1 for f in common if res[f]["verdict"] == "drop" and gold[f] == "keep")
    print(f"{'':26} [校验] 对比 {len(common)} 张，一致 {agree} ({agree/len(common)*100:.0f}%)")
    print(f"{'':26}   机器KEEP/人工keep {tp}  机器KEEP/人工reject {fp}  "
          f"机器DROP/人工keep {fn}")
    if fn:
        print(f"{'':26}   ⚠️ 机器错杀 {fn} 张：")
        for f in common:
            if res[f]["verdict"] == "drop" and gold[f] == "keep":
                print(f"{'':30}{f:<14} {res[f]['reject_reason']:<14} {res[f]['key_evidence'][:28]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--per-cat", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    try:
        from mimo_client import MiMoVisionClient
    except Exception as e:
        print(f"[错误] 无法导入 MiMoVisionClient: {e}")
        return 1
    client = MiMoVisionClient()
    print(f"模型={getattr(client, 'model', '?')}  并发={args.workers}\n")

    if args.all:
        tax = json.load(open(os.path.join(_HERE, "_taxonomy.json"), encoding="utf-8-sig"))
        cats = [s["code"] for m in tax for s in m["subcategories"]
                if os.path.isdir(os.path.join(POOL, s["code"]))]
    else:
        cats = [args.cat]

    T = 0
    for c in cats:
        try:
            r = run_cat(client, c, args.per_cat, args.workers, validate=args.validate)
        except ApiUnavailable as e:
            print(f"\n\n[中止] API 不可用：{e}")
            print("[中止] 已完成的类别已存盘，修复后重跑会自动跳过。")
            print("[中止] 注意：不要使用本轮异常期间的任何标注结果。")
            return 2
        if r:
            T += r["keep"]
    print(f"\n合计保留 {T} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
