"""分类评测：understand 节点在 32 个小类上的判定准确率。

数据源直接 import eval_queries，避免查询集漂移：
  QUERY_SET    64 条（32 小类 x 2 种问法：explicit / colloquial）
  NEGATIVE_SET 10 条（真无关，期望被范围护栏拦下）

链路走真实图节点 core.assistant_graph.understand(state)，再跑 scope_guard
取范围判定；不另写提示词、不 mock 模型。

用法（工作目录 ai-module）：
  python eval/eval_classify.py                 # 全量：64 正 + 10 负 x 3 次采样
  python eval/eval_classify.py --limit 4        # 冒烟：只跑前 4 条
  python eval/eval_classify.py --samples 1 --no-write
  python eval/eval_classify.py --workers 6

结果同时打印 stdout 并写入 db/eval_classify_output.txt（UTF-8）。
"""
import argparse
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from eval.eval_metrics import mean, spread
from eval.eval_queries import NEGATIVE_SET, QUERY_SET, category_label

OUT_PATH = os.path.join(_AI_ROOT, "db", "eval_classify_output.txt")
INTERCEPT_SCOPES = {"out_of_scope", "ambiguous"}
MAX_ATTEMPTS = 3


# ================= 纯函数（可单测，不触网） =================

def predicted_pair(out: dict):
    """从 understand 输出取（大类, 小类）预测。"""
    out = out or {}
    major = str(out.get("locked_major") or "").strip()
    sub = str(out.get("locked_subcategory") or "").strip()
    if not major:
        major = str(out.get("suggested_major_code") or "").strip()
    return major, sub


def subcategory_hit(expected_major, expected_sub, predicted_major, predicted_sub) -> bool:
    """小类命中：要求（大类, 小类）完全一致。"""
    if not expected_major or not expected_sub:
        return False
    return (expected_major, expected_sub) == (predicted_major, predicted_sub)


def major_hit(expected_major, predicted_major) -> bool:
    """大类命中：只比大类，不看小类。"""
    return bool(expected_major) and expected_major == predicted_major


def is_intercepted(scope_decision: dict) -> bool:
    """范围护栏是否把这句挡在风险咨询之外（越界 / 模糊）。"""
    scope = str((scope_decision or {}).get("scope") or "")
    return scope in INTERCEPT_SCOPES


def confusion_pairs(wrong_pairs) -> dict:
    """wrong_pairs: 可迭代的 (expected_sub, predicted_sub)。返回计数字典。"""
    counts = {}
    for expected, predicted in wrong_pairs:
        key = (expected or "<空>", predicted or "<空>")
        counts[key] = counts.get(key, 0) + 1
    return counts


def top_confusions(wrong_pairs, top_n: int = 10):
    """按出现次数降序（并列按字母序）取前 N 个混淆对。"""
    counts = confusion_pairs(wrong_pairs)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:top_n]


def round_accuracy(per_round_flags, samples: int):
    """per_round_flags: list[list[bool]]，长度 samples；返回每轮准确率。"""
    rounds = []
    for r in range(samples):
        flags = per_round_flags[r] if r < len(per_round_flags) else []
        rounds.append(mean(1.0 if flag else 0.0 for flag in flags))
    return rounds


def mean_range(values):
    """返回（均值, 极差）。"""
    values = list(values)
    return mean(values), spread(values)


# ================= 真实调用 =================

def _understand_once(query: str) -> dict:
    """跑一次真实链路：understand -> scope_guard。"""
    from langchain_core.messages import HumanMessage
    import core.assistant_graph as ag

    state = {"messages": [HumanMessage(content=query)]}
    out = ag.understand(state)
    scope = ag.scope_guard({**state, **out})
    return {"understand": out, "scope": scope}


def _run_with_retry(query: str):
    """失败重试；返回 (结果, 失败原因, 实际调用次数)。网络超时不记成判错。"""
    last = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            out = _understand_once(query)
        except Exception as exc:                      # noqa: BLE001
            last = "exception:%s: %s" % (type(exc).__name__, exc)
            time.sleep(1.5 * (attempt + 1))
            continue
        plan = out["understand"].get("dialogue_plan") or {}
        if plan:
            return out, "", attempt + 1
        last = "planner_failed:%s" % (out["understand"].get("policy_reason") or "")
        time.sleep(1.5 * (attempt + 1))
    return None, last, MAX_ATTEMPTS


def _eval_task(task: dict) -> dict:
    """执行一条（查询 x 采样），返回记录。"""
    started = time.time()
    result, failure, attempts = _run_with_retry(task["query"])
    elapsed = time.time() - started
    record = {
        "kind": task["kind"],
        "index": task["index"],
        "sample": task["sample"],
        "query": task["query"],
        "style": task.get("style", ""),
        "expected_major": task.get("expected_major", ""),
        "expected_sub": task.get("expected_sub", ""),
        "note": task.get("note", ""),
        "seconds": elapsed,
        "failure": failure,
        "attempts": attempts,
        "predicted_major": "",
        "predicted_sub": "",
        "scope": "",
        "sub_hit": False,
        "major_ok": False,
        "intercepted": False,
    }
    if result is None:
        return record
    understand = result["understand"]
    major, sub = predicted_pair(understand)
    record["predicted_major"] = major
    record["predicted_sub"] = sub
    record["scope"] = str((result["scope"] or {}).get("scope") or "")
    record["understand"] = understand
    return record


# ================= 汇总与输出 =================

def _label(major, sub):
    if not major and not sub:
        return "-"
    if major and sub:
        return "%s [%s]" % (category_label(major, sub), "%s/%s" % (major, sub))
    return "%s/%s" % (major or "-", sub or "-")


def _build_report(positives, negatives, samples, workers, limit, started_at):
    lines = []
    add = lines.append
    failed = [r for r in positives + negatives if r["failure"]]
    add("分类评测（understand 节点）")
    add("生成时间=%s" % started_at)
    add("模型=%s" % _model_name())
    add("正样本=%d 条（覆盖小类=%d）  负样本=%d  每例采样=%d  并发=%d"
        % (len({(r["expected_major"], r["expected_sub"], r["style"]) for r in positives}),
           len({(r["expected_major"], r["expected_sub"]) for r in positives}),
           len({r["index"] for r in negatives}), samples, workers))
    if limit:
        add("注意：本次为 --limit %d 的冒烟结果，不代表全量。" % limit)
    add("失败（重试耗尽，不计入判错分母）=%d 条" % len(failed))
    add("")

    # ---- 正样本明细 ----
    add("===== 一、正样本明细（每例 %d 次采样） =====" % samples)
    add("命中  问法         期望小类                                 -> 实际小类")
    for idx in sorted({r["index"] for r in positives}):
        group = [r for r in positives if r["index"] == idx]
        style = group[0]["style"]
        ok = sum(1 for r in group if r["sub_hit"])
        exp = "%s/%s" % (group[0]["expected_major"], group[0]["expected_sub"])
        preds = sorted({"%s/%s" % (r["predicted_major"] or "-", r["predicted_sub"] or "-")
                        for r in group})
        scopes = sorted({r["scope"] or "-" for r in group})
        add("[%s] %-11s %-42s -> %-46s scope=%s"
            % ("OK  " if ok == len(group) else ("部分" if ok else "未中"),
               style, exp, " | ".join(preds), "/".join(scopes)))
    add("")

    # ---- 负样本明细 ----
    add("===== 二、负样本明细（每例 %d 次采样） =====" % samples)
    for idx in sorted({r["index"] for r in negatives}):
        group = [r for r in negatives if r["index"] == idx]
        ok = sum(1 for r in group if r["intercepted"])
        scopes = sorted({r["scope"] or "-" for r in group})
        add("[%s] %-32s 拦截 %d/%d  scope=%s"
            % ("OK  " if ok == len(group) else ("部分" if ok else "未中"),
               group[0]["query"], ok, len(group), " | ".join(scopes)))
    add("")

    # ---- 汇总 ----
    def stats(records, flag_key):
        flags = [[] for _ in range(samples)]
        for r in records:
            flags[r["sample"]].append(bool(r[flag_key]))
        return mean_range(round_accuracy(flags, samples))

    exp_recs = [r for r in positives if r["style"] == "explicit"]
    col_recs = [r for r in positives if r["style"] == "colloquial"]

    add("===== 三、汇总 =====  （均值 ± 采样极差）")
    add("小类准确率 explicit   : %.3f ± %.3f" % stats(exp_recs, "sub_hit"))
    add("小类准确率 colloquial : %.3f ± %.3f" % stats(col_recs, "sub_hit"))
    add("小类准确率 总体       : %.3f ± %.3f" % stats(positives, "sub_hit"))
    add("大类准确率 explicit   : %.3f ± %.3f" % stats(exp_recs, "major_ok"))
    add("大类准确率 colloquial : %.3f ± %.3f" % stats(col_recs, "major_ok"))
    add("大类准确率 总体       : %.3f ± %.3f" % stats(positives, "major_ok"))
    add("负样本拦截率          : %.3f ± %.3f" % stats(negatives, "intercepted"))
    blocked = sum(1 for r in positives if is_intercepted({"scope": r["scope"]}))
    emergency = sum(1 for r in positives if r["scope"] == "emergency")
    scope_counts = {}
    for r in positives:
        key = r["scope"] or "-"
        scope_counts[key] = scope_counts.get(key, 0) + 1
    add("误拦正样本(判为越界/模糊)    : %d / %d" % (blocked, len(positives)))
    add("紧急标记正样本(scope=emergency): %d / %d" % (emergency, len(positives)))
    add("正样本范围分布: %s" % "、".join("%s=%d" % (k, v) for k, v in sorted(scope_counts.items())))
    add("失败条数              : %d" % len(failed))
    retried = sum(1 for r in positives + negatives if r.get("attempts", 1) > 1)
    add("重试过的条数          : %d（其中成功重试 %d）" % (retried, retried - len(failed)))
    for r in failed:
        add("    - [%s] %s :: %s" % (r["kind"], r["query"], r["failure"]))
    add("")

    # ---- 混淆对 ----
    add("===== 四、混淆对 Top-10（期望小类 -> 实际小类，按次数降序） =====")
    wrong = [(r["expected_sub"], r["predicted_sub"]) for r in positives if not r["sub_hit"]]
    top = top_confusions(wrong, 10)
    if not top:
        add("（无混淆）")
    for (expected, predicted), count in top:
        add("  %-26s -> %-26s x%d" % (expected, predicted, count))
    add("")

    # ---- 按小类聚合（便于定位需要加护栏的类别） ----
    add("===== 五、逐小类命中（按小类聚合，最弱在前） =====")
    per_sub = {}
    for r in positives:
        key = (r["expected_major"], r["expected_sub"])
        entry = per_sub.setdefault(key, {"total": 0, "hit": 0, "wrong": {}})
        entry["total"] += 1
        if r["sub_hit"]:
            entry["hit"] += 1
        else:
            pred = r["predicted_sub"] or "<空>"
            entry["wrong"][pred] = entry["wrong"].get(pred, 0) + 1
    ranked = sorted(per_sub.items(), key=lambda kv: (kv[1]["hit"] / kv[1]["total"], kv[0]))
    for (major, sub), entry in ranked:
        ratio = entry["hit"] / entry["total"]
        wrong_desc = "、".join("%s x%d" % (p, c) for p, c in
                              sorted(entry["wrong"].items(), key=lambda kv: -kv[1]))
        add("  %-42s %2d/%2d  %s"
            % ("%s/%s" % (major, sub), entry["hit"], entry["total"],
               ("误判为 " + wrong_desc) if wrong_desc else ""))
    return "\n".join(lines) + "\n"


def _model_name():
    try:
        from config import MIMO_MODEL
        return MIMO_MODEL
    except Exception:                                  # noqa: BLE001
        return "unknown"


# ================= 主流程 =================

def run(limit: int = 0, samples: int = 3, workers: int = 5, write: bool = True):
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    positives_in = list(QUERY_SET)
    negatives_in = list(NEGATIVE_SET)
    if limit:
        positives_in = positives_in[:limit]
        negatives_in = negatives_in[:limit]

    tasks = []
    for idx, item in enumerate(positives_in):
        for sample in range(samples):
            tasks.append({
                "kind": "positive", "index": idx, "sample": sample,
                "query": item["query"], "style": item.get("style", ""),
                "expected_major": item["major"], "expected_sub": item["subcategory"],
            })
    for idx, item in enumerate(negatives_in):
        for sample in range(samples):
            tasks.append({
                "kind": "negative", "index": idx, "sample": sample,
                "query": item["query"], "note": item.get("note", ""),
            })

    print("开始分类评测：%d 条任务（%d 正 x %d 采样 + %d 负 x %d 采样），并发=%d"
          % (len(tasks), len(positives_in), samples, len(negatives_in), samples, workers))
    done = 0
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_eval_task, task) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 10 == 0 or done == len(tasks):
                print("  进度 %d/%d" % (done, len(tasks)))

    positives = [r for r in results if r["kind"] == "positive"]
    negatives = [r for r in results if r["kind"] == "negative"]
    for r in positives:
        r["sub_hit"] = subcategory_hit(r["expected_major"], r["expected_sub"],
                                       r["predicted_major"], r["predicted_sub"])
        r["major_ok"] = major_hit(r["expected_major"], r["predicted_major"])
    for r in negatives:
        r["intercepted"] = is_intercepted({"scope": r["scope"]})

    report = _build_report(positives, negatives, samples, workers, limit, started_at)
    print(report)
    if write:
        with open(OUT_PATH, "w", encoding="utf-8") as handle:
            handle.write(report)
        print("结果已写入 %s" % OUT_PATH)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="understand 节点分类准确率评测")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（冒烟用）")
    parser.add_argument("--samples", type=int, default=3, help="每例采样次数，默认 3")
    parser.add_argument("--workers", type=int, default=5, help="线程池并发，默认 5")
    parser.add_argument("--no-write", action="store_true", help="只打印不落盘")
    args = parser.parse_args(argv)
    run(limit=args.limit, samples=args.samples, workers=args.workers,
        write=not args.no_write)


if __name__ == "__main__":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:                                  # noqa: BLE001
        pass
    main()


