"""阶段 4 实测：B 类缺失时，报告是不是真的写成「若…则…」分情况判断（只读，不部署）。

产物：db/eval_report_branch.txt
"""
import io
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import core.assistant_graph as ag

ag.get_stream_writer = lambda: None          # 不在图里跑，状态流不适用


def _state(**over):
    state = {
        "messages": [],
        "premises_scope": "public",
        "vision_summary": "",
    }
    state.update(over)
    return state


CASES = [
    ("A 完整报告 / 只缺 impact(B) —— 消防通道", _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车", "persistence": "长期"},
                 "missing": [], "report_missing": ["impact"]}],
        categories=["fire_lane_blocked"],
        category_results={"fire_lane_blocked": {
            "regulation": "《消防法》第28条：任何单位、个人不得占用、堵塞、封闭疏散通道、安全出口、消防车通道；"
                          "第60条第1款第3项：占用、堵塞、封闭消防车通道，妨碍消防车通行的，责令改正，处5000元以上5万元以下罚款。",
            "case": "萍乡某小区火灾，5 辆私家车占用消防车通道，延误救援。"}},
        missing=[], report_mode="full")),
    ("B 完整报告 / 只缺 traffic(B) —— 井盖", _state(
        issues=[{"major_code": "municipal", "subcategory_code": "manhole_damage",
                 "slots": {"defect": "井盖缺失"}, "missing": [], "report_missing": ["traffic"]}],
        categories=["manhole_damage"],
        category_results={"manhole_damage": {
            "regulation": "《城市道路管理条例》相关规定：道路附属设施缺失应及时修复并设置警示标志。",
            "case": "库内暂未检索到"}},
        missing=[], report_mode="full")),
    ("C 初步报告 / 缺 persistence(A) + impact(B)", _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "废旧家具"}, "missing": ["persistence"],
                 "report_missing": ["persistence", "impact"]}],
        categories=["fire_lane_blocked"],
        category_results={"fire_lane_blocked": {
            "regulation": "《消防法》第28条；长期占用可依第60条处罚，临时占用以责令改正为主。",
            "case": "库内暂未检索到"}},
        missing=["fire_lane_blocked_persistence"], report_mode="preliminary")),
]

lines = []
for name, state in CASES:
    print("=" * 78)
    print("用例:", name)
    print("材料里的 B 行:", ag.report_branch_keys(state))
    try:
        out = ag.report(state)
    except Exception as exc:                     # noqa: BLE001
        print("调用失败:", type(exc).__name__, exc)
        lines.append("用例 %s -> FAILED %s: %s" % (name, type(exc).__name__, exc))
        continue
    body = out.get("draft_report") or ""
    branch = body.count("若") >= 2 or ("若" in body and "则" in body)
    hits = ag.empty_talk_hits(body)
    print("---- 原文 ----")
    print(body)
    print("---- 判定 ----")
    print("分情况判断:", branch, "| 空话命中:", hits,
          "| 问号数:", body.count("？") + body.count("?"),
          "| 井号标题:", "###" in body)
    lines.append("用例 %s -> branch=%s empty_talk=%s q=%d heading=%s"
                 % (name, branch, hits, body.count("？") + body.count("?"), "###" in body))
    print()

print("=" * 78)
with open(os.path.join("db", "eval_report_branch.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print("summary -> db/eval_report_branch.txt")
