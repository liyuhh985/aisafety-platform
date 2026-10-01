# -*- coding: utf-8 -*-
"""量「被判否/拒答之后，下一轮换一个问题时，规划器会不会把旧隐患重新抓回来抢锁」。

背景（spec 决策 7）：`locked_subcategory` 取的是 `in_major[0]` —— 规划器 issues 里该大类的
**第一条**。而**大类**有防护（读 `perceived_major`，不看 `issues[0]`，见
`core/assistant_graph.py:558` 的注释），小类没有。

所以问题是：第 1 轮被判否/拒答（锁被撤销）之后，第 2 轮用户换个东西问，
规划器会不会把第 1 轮那个小类也输出进 `issues`、而且排在前面。

两种条件各跑一遍：
  A(with-rollback)    = 当前代码（决策 7 已实现）
  B(no-rollback)      = 把 `_facts_rollback` 换成空实现（等价于改动前）

只量规划器行为，检索与报告都 stub 掉（本实验不关心产物，只关心 issues 顺序与锁）。

用法：python db/measure_lock_regrab.py [每个场景的重复次数]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402

# 第 1 轮：规划器会声称它是 traffic_facility_damage，但原文里没有物件词/场所词
# → decide_scope 判 ambiguous → 拒答（这正是决策 7 要撤销锁的场景）
# 第 2 轮：换一个**别的**东西问
SCENARIOS = [
    ("indicator->manhole", "商场里的指示牌歪了", "小区门口那个井盖不见了，挺危险的"),
    ("indicator->firelane", "商场里的指示牌歪了", "楼道里的消防通道被电动车占了"),
]

CASE_OK = ("=== mixed ===\n\n【结果1】[语义匹配] x\n  类别: 消防安全/消防通道占用\n")


def _stub_everything_but_planner():
    ag._slot_question_llm = lambda **k: {"question": "能再具体描述一下吗？", "target_slot": ""}
    ag._run_tool = lambda name, keyword, cancellation=None: CASE_OK
    ag._probe_top1_score = lambda *a, **k: None
    ag._report_llm = type("F", (), {"_call_llm_stream_events": staticmethod(
        lambda messages, cancellation=None: iter([("chunk", "（略）")]))})()
    ag._rewrite_llm = type("F", (), {"_call_llm": staticmethod(
        lambda messages, cancellation=None: {"content": "消防 通道"})})()


def _run_turn(app, config, text):
    """跑一轮，返回 (understand 节点的 update, 终态)。"""
    und = {}
    for mode, item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            for node, update in item.items():
                if node == "understand":
                    und = update or {}
    return und, app.get_state(config).values


def _codes(update):
    return [str((i or {}).get("subcategory_code") or "") for i in (update.get("issues") or [])]


def measure(condition, repeats):
    if condition == "B":
        ag._facts_rollback = lambda state: {}
    rows = []
    for name, q1, q2 in SCENARIOS:
        for i in range(repeats):
            app = ag.build_graph()
            cfg = {"configurable": {"thread_id": "rg-%s-%s-%d" % (condition, name, i)}}
            u1, v1 = _run_turn(app, cfg, q1)
            t1_scope = v1.get("scope")
            old = u1.get("locked_subcategory") or ""
            u2, v2 = _run_turn(app, cfg, q2)
            codes = _codes(u2)
            rows.append({
                "scenario": name,
                "t1_scope": t1_scope,
                "old": old,
                "t2_codes": codes,
                "t2_old_at": codes.index(old) if old and old in codes else -1,
                "t2_locked": u2.get("locked_subcategory") or "",
            })
            sys.stdout.flush()
    return rows


def report(condition, rows):
    print("=" * 78)
    print("### 条件 %s" % condition)
    n = len(rows)
    hit = [r for r in rows if r["t2_old_at"] >= 0]
    front = [r for r in rows if r["t2_old_at"] == 0]
    hijack = [r for r in rows if r["old"] and r["t2_locked"] == r["old"]]
    for r in rows:
        print("  %-22s t1_scope=%-10s old=%-24s t2_issues=%-46s old_at=%s -> locked=%s"
              % (r["scenario"], r["t1_scope"], r["old"], ",".join(r["t2_codes"]) or "-",
                 r["t2_old_at"], r["t2_locked"]))
    print("  ---")
    print("  第1轮被判 ambiguous 的比例 : %d/%d" % (len([r for r in rows if r["t1_scope"] == "ambiguous"]), n))
    print("  第2轮 issues 里含旧类别     : %d/%d" % (len(hit), n))
    print("  其中旧类别排在第 0 位（会抢锁）: %d/%d" % (len(front), n))
    print("  第2轮锁**真的被抢回旧类别**   : %d/%d" % (len(hijack), n))
    return {"n": n, "ambiguous": len([r for r in rows if r["t1_scope"] == "ambiguous"]),
            "hit": len(hit), "front": len(front), "hijack": len(hijack)}


if __name__ == "__main__":
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    _stub_everything_but_planner()
    original_rollback = ag._facts_rollback
    out = {}
    for cond in ("A", "B"):
        t0 = time.time()
        rows = measure(cond, repeats)
        out[cond] = report(cond, rows)
        print("  （%.0fs）" % (time.time() - t0))
        ag._facts_rollback = original_rollback
    print("=" * 78)
    print("汇总: A=%s  B=%s" % (out.get("A"), out.get("B")))
