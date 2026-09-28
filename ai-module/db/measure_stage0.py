# -*- coding: utf-8 -*-
"""阶段 0：对话质量整改的五项只读测量（G1~G5）。

只读：不修改任何生产代码；只在本目录下写输出文件。
用法（任意工作目录）：
  python db/measure_stage0.py                 # 全部
  python db/measure_stage0.py --only g1,g3,g4
  python db/measure_stage0.py --only g4        # 纯静态，不联网
"""
import argparse
import io
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

_DB = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DB)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from core.hazard_taxonomy import MAJOR_LABELS, SUBCATEGORY_LABELS, SUBCATEGORY_TO_MAJOR
from core.slot_schemas import SLOT_SCHEMAS, SUBCATEGORY_SLOT_SCHEMAS, get_slot_schema

MAX_ATTEMPTS = 3

# ---------------------------------------------------------------- 槽位语义线索
# 用于把「模型自由写的问句」归到一个槽位上，是启发式，不是事实。
SLOT_HINTS = {
    "behavior": ["摆摊", "摊", "占道", "经营", "堆放", "什么占", "哪种占"],
    "persistence": ["长期", "临时", "多久", "多长时间", "什么时候", "持续"],
    "blocked": ["堵死", "堵住", "完全", "部分", "能不能过", "通行", "过不去"],
    "structure": ["裂缝", "开裂", "倾斜", "沉降", "承重", "墙"],
    "occupancy": ["有人", "居住", "住", "使用", "里面", "住户"],
    "risk": ["坍塌", "塌", "即时", "马上倒", "危险"],
    "blocker": ["什么", "占用", "堵塞", "杂物", "被什么", "挡住"],
    "impact": ["影响", "通行", "消防车", "救援"],
    "facility_type": ["哪一", "哪种", "消火栓", "喷淋", "报警", "灭火器", "设施"],
    "condition": ["老旧", "损坏", "无法使用", "坏了", "失效"],
    "function_impact": ["整栋", "整楼", "报警功能", "灭火功能"],
    "source": ["哪里", "来源", "从哪", "掉落", "漏电", "裸露", "设备", "线"],
    "target": ["人行道", "车行道", "下面", "底下", "砸到"],
    "exposure": ["围挡", "警告", "警示", "标志", "警戒"],
    "defect": ["缺失", "破损", "松动", "井盖", "坏", "塌陷"],
    "traffic": ["影响", "行人", "车辆", "通行"],
    "contact": ["接触", "碰到", "人", "车"],
    "site": ["围挡", "施工区域", "工地"],
    "safety": ["警示", "防护", "护栏", "安全网"],
    "describe": ["具体", "描述", "什么情况", "详细", "哪些"],
}

CANNED_ANSWER = {
    "behavior": "是摆摊占道经营",
    "persistence": "已经长期这样了",
    "blocked": "基本完全堵死了，人过不去",
    "structure": "墙体有明显裂缝而且已经倾斜",
    "occupancy": "现在还有人在里面居住",
    "risk": "有即时坍塌的风险",
    "blocker": "被私家车占用",
    "impact": "影响消防车通行",
    "facility_type": "是消火栓",
    "condition": "已经损坏无法使用",
    "function_impact": "影响整栋楼的报警功能",
    "source": "是外墙上面掉落的",
    "target": "下面是人行道",
    "exposure": "没有任何围挡和警告标志",
    "defect": "井盖已经破损",
    "traffic": "影响了车辆通行",
    "contact": "人可能接触到",
    "site": "施工区域没有围挡",
    "safety": "没有安全警示",
    "describe": "具体是长期堆放的杂物和废旧家具，已经占了大半条通道",
}


def _run_with_retry(fn, attempts=MAX_ATTEMPTS):
    last = ""
    for i in range(attempts):
        try:
            return fn(), "", i + 1
        except Exception as exc:                      # noqa: BLE001
            last = "%s: %s" % (type(exc).__name__, exc)
            time.sleep(1.5 * (i + 1))
    return None, last, attempts


def _understand_once(query, selected_major_code=""):
    from langchain_core.messages import HumanMessage
    import core.assistant_graph as ag
    state = {"messages": [HumanMessage(content=query)]}
    if selected_major_code:
        state["selected_major_code"] = selected_major_code
    return ag.understand(state)


def _focus(info):
    issues = info.get("issues") or []
    if not issues:
        return "", [], []
    issue = issues[0]
    code = issue.get("subcategory_code") or ""
    missing = list(issue.get("missing") or [])
    keys = [s.key for s in get_slot_schema(code)]
    return code, missing, keys


def _hits(question, slot_keys):
    q = question or ""
    out = []
    for key in slot_keys:
        for hint in SLOT_HINTS.get(key, []):
            if hint in q:
                out.append(key)
                break
    return out


def classify_question(question, missing, all_keys):
    """返回 (判定, 备注)。判定 ∈ {未问, 命中, 未命中, 多余}。"""
    q = (question or "").strip()
    if not q:
        return "未问", ""
    if not missing and not all_keys:
        return "多余", "无可问槽位却问了"
    asked = _hits(q, all_keys)
    if not missing:
        return "多余", "missing 为空却问了（命中:" + ",".join(asked) + "）" if asked else "missing 为空却问了"
    hit_missing = [k for k in asked if k in missing]
    if hit_missing:
        return "命中", ",".join(hit_missing)
    if asked:
        return "未命中", "指向已填槽:" + ",".join(asked)
    return "未命中", "无法归属到任何槽"


# ---------------------------------------------------------------- G4
def g4_slot_stats():
    rows = []
    for code in sorted(SUBCATEGORY_SLOT_SCHEMAS):
        schema = get_slot_schema(code)
        critical = [s for s in schema if s.critical]
        rows.append({
            "code": code,
            "major": SUBCATEGORY_TO_MAJOR.get(code, ""),
            "label": SUBCATEGORY_LABELS.get(code, ""),
            "critical": len(critical),
            "keys": [s.key for s in schema],
            "critical_keys": [s.key for s in critical],
            "schema_name": next((n for n, v in SLOT_SCHEMAS.items() if v is schema), "?"),
            "slot_q": [(s.key, s.question) for s in schema],
        })
    path = os.path.join(_DB, "eval_slot_critical.txt")
    lines = []
    lines.append("G4：每个小类的 critical 槽位个数（静态统计，无网络）")
    lines.append("")
    dist = {}
    for r in rows:
        dist[r["critical"]] = dist.get(r["critical"], 0) + 1
    lines.append("critical 个数分布：" + "  ".join(
        "%d 个 x%d 个小类" % (k, dist[k]) for k in sorted(dist)))
    lines.append("")
    lines.append("%-26s %-16s %-5s %s" % ("小类", "槽位表", "个数", "critical 槽位键"))
    for r in rows:
        lines.append("%-26s %-16s %-5d %s" % (r["code"], r["schema_name"], r["critical"], ",".join(r["critical_keys"]) or "-"))
    lines.append("")
    lines.append("===== 全部槽位（键 / critical / 自带问句）=====")
    for r in rows:
        lines.append("[%s] %s (%s)" % (r["code"], r["label"], r["schema_name"]))
        for key, q in r["slot_q"]:
            flag = "critical" if key in r["critical_keys"] else "optional"
            lines.append("    %-16s %-9s %s" % (key, flag, q))
    text = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("\n[G4] 已写入 %s" % path)
    return rows, path


# ---------------------------------------------------------------- G1
def g1_question_target(workers=4, limit=0):
    from eval_queries import QUERY_SET
    items = list(QUERY_SET)
    if limit:
        items = items[:limit]

    def work(item):
        info, failure, attempts = _run_with_retry(lambda: _understand_once(item["query"]))
        return {"item": item, "info": info, "failure": failure, "attempts": attempts}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(work, items))

    rows = []
    for r in results:
        item = r["item"]
        base = {"query": item["query"], "sub": item["subcategory"], "style": item["style"]}
        if r["info"] is None:
            rows.append(dict(base, ok=False, missing=[], plan_q="", final_q="",
                             v_plan="失败", v_final="失败", note=r["failure"],
                             pred_sub="", action="", code=""))
            continue
        info = r["info"]
        code, missing, keys = _focus(info)
        plan = info.get("dialogue_plan") or {}
        q = str(plan.get("question") or "").strip()
        final_q = str(info.get("clarification_question") or "").strip()
        v_plan, _ = classify_question(q, missing, keys)
        v_final, note = classify_question(final_q, missing, keys)
        rows.append(dict(base, ok=True, missing=missing, plan_q=q, final_q=final_q,
                         v_plan=v_plan, v_final=v_final, note=note,
                         pred_sub=info.get("locked_subcategory") or "",
                         action=info.get("next_action") or "", code=code))

    valid = [r for r in rows if r["ok"]]
    failed = [r for r in rows if not r["ok"]]
    asked = [r for r in valid if r["final_q"]]
    hit = [r for r in asked if r["v_final"] == "命中"]
    miss = [r for r in asked if r["v_final"] == "未命中"]
    extra = [r for r in asked if r["v_final"] == "多余"]
    never = [r for r in valid if not r["final_q"]]
    silent = [r for r in never if r["missing"]]
    dropped = [r for r in valid if r["plan_q"] and not r["final_q"]]

    lines = []
    lines.append("G1：追问是否指向代码算出的 missing（QUERY_SET 全量，每例 1 次）")
    lines.append("口径：以真正问出口的 clarification_question 为准；用槽位语义线索把它归到一个槽。")
    lines.append("      plan.question 是模型提议，可能被代码丢弃（discarded），单独统计。")
    lines.append("注意：归类是启发式，不是人工逐条判定；命中以外的清单逐条列出，可人工复核。")
    lines.append("")
    lines.append("样本=%d（有效 %d，失败 %d）" % (len(rows), len(valid), len(failed)))
    lines.append("实际问出口的样本=%d" % len(asked))
    if asked:
        lines.append("  ├ 命中 missing       = %d (%.3f)" % (len(hit), len(hit) / len(asked)))
        lines.append("  ├ 未命中 missing     = %d (%.3f)" % (len(miss), len(miss) / len(asked)))
        lines.append("  └ missing 为空却问了 = %d (%.3f)" % (len(extra), len(extra) / len(asked)))
    lines.append("一句话都没问=%d" % len(never))
    lines.append("  └ 其中 missing 非空（该问没问＝黑洞风险）= %d" % len(silent))
    lines.append("模型提了问句但被代码丢弃=%d（plan.question 非空、clarification_question 为空）" % len(dropped))
    lines.append("")
    lines.append("===== 未命中 missing（逐条）=====")
    if not miss:
        lines.append("(无)")
    for r in miss:
        lines.append("- pred=%s missing=%s" % (r["pred_sub"] or "-", ",".join(r["missing"]) or "-"))
        lines.append("    实际问句: %s" % r["final_q"])
        lines.append("    模型提议: %s" % (r["plan_q"] or "(空)"))
        lines.append("    归属备注: %s" % r["note"])
        lines.append("    用户原话: %s" % r["query"])
        lines.append("")
    lines.append("===== missing 为空却追问（逐条）=====")
    if not extra:
        lines.append("(无)")
    for r in extra:
        lines.append("- pred=%s  动作=%s  问句: %s  原话: %s"
                     % (r["pred_sub"] or "-", r["action"], r["final_q"], r["query"]))
    lines.append("")
    lines.append("===== missing 非空但一句话没问（逐条）=====")
    if not silent:
        lines.append("(无)")
    for r in silent:
        lines.append("- pred=%s missing=%s 动作=%s 原话: %s"
                     % (r["pred_sub"] or "-", ",".join(r["missing"]), r["action"], r["query"]))
    lines.append("")
    lines.append("===== 全量明细 =====")
    lines.append("%-4s %-4s %-19s %-10s %-20s %-22s %s"
                 % ("实问", "提议", "期望小类", "问法", "实际小类", "missing", "实际问句"))
    for r in rows:
        if not r["ok"]:
            lines.append("%-4s %-4s %-19s %-10s %-20s %-22s %s"
                         % ("失败", "失败", r["sub"], r["style"], "-", "-", r["note"]))
            continue
        lines.append("%-4s %-4s %-19s %-10s %-20s %-22s %s" % (
            r["v_final"], r["v_plan"], r["sub"], r["style"], r["pred_sub"] or "-",
            ",".join(r["missing"]) or "-", r["final_q"] or "-"))
    text = "\n".join(lines)
    path = os.path.join(_DB, "eval_question_target.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("\n[G1] 已写入 %s" % path)
    return rows, path


# ---------------------------------------------------------------- G3
FUZZY_INPUTS = [
    "楼下有问题",
    "有味儿",
    "楼道里不对劲",
    "我们小区有个东西坏了",
    "路边那个坏了好久了",
    "门口那玩意儿要塌了",
    "电梯有问题",
    "路上有个坑",
    "小区里乱糟糟的",
    "有隐患吧",
]


def _fixed_questions():
    out = {}
    for name, schema in SLOT_SCHEMAS.items():
        for s in schema:
            out.setdefault(s.question, []).append("%s/%s" % (name, s.key))
    return out


def g3_fallback_rate(inputs=None, workers=4):
    inputs = list(inputs or FUZZY_INPUTS)
    fixed = _fixed_questions()

    def work(text):
        info, failure, attempts = _run_with_retry(lambda: _understand_once(text))
        return {"text": text, "info": info, "failure": failure, "attempts": attempts}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(work, inputs))

    rows = []
    for r in results:
        if r["info"] is None:
            rows.append({"text": r["text"], "fallback": "失败", "q": "", "final_q": "",
                         "pred": "", "missing": [], "note": r["failure"]})
            continue
        info = r["info"]
        code, missing, keys = _focus(info)
        plan = info.get("dialogue_plan") or {}
        q = str(plan.get("question") or "").strip()
        final_q = str(info.get("clarification_question") or "").strip()
        is_fixed = bool(final_q) and final_q in fixed
        rows.append({"text": r["text"], "fallback": "兜底" if is_fixed else ("模型自写" if final_q else "未问"),
                     "q": q, "final_q": final_q, "pred": info.get("locked_subcategory") or "",
                     "missing": missing, "schema_of": fixed.get(final_q, [])})

    valid = [r for r in rows if r["fallback"] != "失败"]
    fb = [r for r in valid if r["fallback"] == "兜底"]
    lines = []
    lines.append("G3：固定问句兜底触发率（模糊/极短输入 %d 条，每例 1 次）" % len(rows))
    lines.append("判据：最终 clarification_question 是否逐字等于 SLOT_SCHEMAS 里某个 Slot.question")
    lines.append("")
    lines.append("兜底触发 %d/%d   模型自写 %d   未问 %d   失败 %d"
                 % (len(fb), len(valid),
                    len([r for r in valid if r["fallback"] == "模型自写"]),
                    len([r for r in valid if r["fallback"] == "未问"]),
                    len(rows) - len(valid)))
    lines.append("")
    for r in rows:
        lines.append("- [%s] %s" % (r["fallback"], r["text"]))
        lines.append("    判定小类: %s   missing=%s" % (r["pred"] or "-", ",".join(r["missing"]) or "-"))
        lines.append("    模型问句: %s" % (r["q"] or "(空)"))
        lines.append("    最终问句: %s" % (r["final_q"] or "(空)"))
        if r["fallback"] == "兜底":
            lines.append("    命中固定串: %s" % ",".join(r["schema_of"]))
        lines.append("")
    text = "\n".join(lines)
    path = os.path.join(_DB, "eval_fallback_rate.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("\n[G3] 已写入 %s" % path)
    return rows, path


# ---------------------------------------------------------------- G5
G5_TARGETS = ["fire_lane_blocked", "road_occupancy", "dangerous_building", "exposed_wire", "manhole_damage"]
G5_SEEDS = {
    "fire_lane_blocked": "楼下消防通道被私家车占了",
    "road_occupancy": "沿街店铺把东西摆到人行道上",
    "dangerous_building": "旁边有栋危房",
    "exposed_wire": "路边有裸露的电线",
    "manhole_damage": "路口井盖坏了",
}
G5_MAX_ROUNDS = 4


def g5_followup_rounds():
    from langchain_core.messages import HumanMessage
    import core.assistant_graph as ag
    app = ag.build_graph()
    rows = []
    for code in G5_TARGETS:
        sid = "g5-" + code + "-" + str(int(time.time() * 1000))
        config = {"configurable": {"thread_id": sid}, "recursion_limit": ag.GRAPH_RECURSION_LIMIT}
        message = G5_SEEDS[code]
        rounds = []
        asked = 0
        for turn in range(1, G5_MAX_ROUNDS + 1):
            nodes = []
            failure = ""
            try:
                for mode, item in app.stream(ag.build_turn_input(sid, message, "", ""), config,
                                             stream_mode=["updates", "custom"]):
                    if mode == "updates" and isinstance(item, dict):
                        nodes.extend([k for k in item.keys() if k != "__interrupt__"])
            except Exception as exc:                  # noqa: BLE001
                failure = "%s: %s" % (type(exc).__name__, exc)
            state = app.get_state(config).values or {}
            q = str(state.get("clarification_question") or "").strip()
            issues = state.get("issues") or []
            missing = list((issues[0] or {}).get("missing") or []) if issues else []
            if q:
                asked += 1
            rounds.append({"turn": turn, "nodes": nodes, "question": q,
                           "missing": missing, "failure": failure,
                           "action": state.get("next_action") or "",
                           "sub": state.get("locked_subcategory") or ""})
            if failure or not q or turn == G5_MAX_ROUNDS:
                break
            nxt = missing[0] if missing else "describe"
            message = CANNED_ANSWER.get(nxt, "具体情况我再补充一下")
        rows.append({"code": code, "seed": G5_SEEDS[code], "rounds": rounds, "asked": asked})

    lines = []
    lines.append("G5：追问轮数（每例 1 次，无方差数据）")
    lines.append("做法：给一句初始描述，之后每轮回答它正在问的那个槽（missing 的第一项），最多 4 轮。")
    lines.append("")
    lines.append("上界 = 该小类 critical 槽位数（静态）：")
    for code in G5_TARGETS:
        schema = get_slot_schema(code)
        lines.append("    %-22s critical=%d  keys=%s" % (
            code, len([s for s in schema if s.critical]), ",".join(s.key for s in schema if s.critical)))
    lines.append("")
    for r in rows:
        lines.append("===== %s（%s）=====" % (r["code"], r["seed"]))
        lines.append("实际追问轮数 = %d" % r["asked"])
        for rd in r["rounds"]:
            lines.append("  第%d轮 小类=%s 动作=%s missing=%s" % (
                rd["turn"], rd["sub"] or "-", rd["action"] or "-", ",".join(rd["missing"]) or "-"))
            lines.append("        问句: %s" % (rd["question"] or "(未问)"))
            lines.append("        节点: %s" % " -> ".join(rd["nodes"]))
            if rd["failure"]:
                lines.append("        失败: %s" % rd["failure"])
        lines.append("")
    text = "\n".join(lines)
    path = os.path.join(_DB, "eval_followup_rounds.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("\n[G5] 已写入 %s" % path)
    return rows, path


# ---------------------------------------------------------------- G2（本地）
DANGER_INPUTS = [
    ("楼道里全是浓烟，人都出不来", "火"),
    ("家里闻到很浓的煤气味", "燃气"),
    ("地震了房子在晃", "地震"),
    ("有人碰到了裸露的电线触电了", "触电"),
    ("墙塌了，下面好像压着人", "坍塌"),
]


def g2_local_product():
    from langchain_core.messages import HumanMessage
    import core.assistant_graph as ag
    app = ag.build_graph()
    rows = []
    for text, kind in DANGER_INPUTS:
        sid = "g2-" + kind + "-" + str(int(time.time() * 1000))
        config = {"configurable": {"thread_id": sid}, "recursion_limit": ag.GRAPH_RECURSION_LIMIT}
        nodes = []
        chunks = []
        failure = ""
        try:
            for mode, item in app.stream(ag.build_turn_input(sid, text, "", ""), config,
                                         stream_mode=["updates", "custom"]):
                if mode == "custom":
                    if isinstance(item, dict) and "chunk" in item:
                        chunks.append(item["chunk"])
                    continue
                if isinstance(item, dict):
                    if "__interrupt__" in item:
                        nodes.append("__interrupt__")
                    nodes.extend([k for k in item.keys() if k != "__interrupt__"])
        except Exception as exc:                      # noqa: BLE001
            failure = "%s: %s" % (type(exc).__name__, exc)
        state = app.get_state(config).values or {}
        msgs = state.get("messages") or []
        assistant = ""
        for m in reversed(msgs):
            if getattr(m, "type", "") == "ai":
                assistant = m.content or ""
                break
        rows.append({
            "kind": kind, "text": text, "nodes": nodes, "failure": failure,
            "action": state.get("next_action") or "",
            "scope": state.get("scope") or "",
            "danger_veto": bool(state.get("danger_veto")),
            "immediate_danger": bool(state.get("immediate_danger")),
            "question": str(state.get("clarification_question") or ""),
            "sub": state.get("locked_subcategory") or "",
            "assistant": assistant,
            "chunks": chunks,
            "report": "report" in nodes,
            "task_gate": "task_gate" in nodes or "__interrupt__" in nodes,
        })

    lines = []
    lines.append("G2（本地）：危险输入当前的实际产物（走真实图，每例 1 次）")
    lines.append("")
    for r in rows:
        lines.append("===== [%s] %s =====" % (r["kind"], r["text"]))
        lines.append("danger_veto=%s  immediate_danger=%s  scope=%s  action=%s  小类=%s"
                     % (r["danger_veto"], r["immediate_danger"], r["scope"] or "-",
                        r["action"] or "-", r["sub"] or "-"))
        lines.append("节点序列: %s" % " -> ".join(r["nodes"]))
        lines.append("产物判定: %s" % ("报告（走了 report 节点）" if r["report"] else "口头回复（未走 report）"))
        lines.append("是否进入建单闸门: %s" % ("是" if r["task_gate"] else "否"))
        lines.append("澄清问句: %s" % (r["question"] or "(空)"))
        lines.append("回复含问号: %s" % ("是" if ("?" in r["assistant"] or "？" in r["assistant"]) else "否"))
        lines.append("--- 回复正文 ---")
        lines.append(r["assistant"] or "(空)")
        if r["failure"]:
            lines.append("失败: %s" % r["failure"])
        lines.append("")
    text = "\n".join(lines)
    path = os.path.join(_DB, "eval_danger_product_local.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("\n[G2-local] 已写入 %s" % path)
    return rows, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="g4,g1,g3,g5,g2")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    wanted = {x.strip().lower() for x in args.only.split(",") if x.strip()}
    if "g4" in wanted:
        g4_slot_stats()
    if "g1" in wanted:
        g1_question_target(workers=args.workers, limit=args.limit)
    if "g3" in wanted:
        g3_fallback_rate(workers=args.workers)
    if "g5" in wanted:
        g5_followup_rounds()
    if "g2" in wanted:
        g2_local_product()


if __name__ == "__main__":
    main()
