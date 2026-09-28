# -*- coding: utf-8 -*-
"""阶段 5a 实测：消冗余的双向验收（只读，不改生产代码）。

同一份脚本在改动前后各跑一次，产物对比，才能看出「冗余降了没」和「有没有反噬」：

  双向验收：冗余必须下降，同时（a）条件分支数量不得下降、（b）三块内容覆盖不得下降
  三个反噬信号：报告变短 / 「仍需确认」消失 / 分支变少或变成套话

用法：python db/measure_stage5a_redundancy.py <tag> [samples]
产物：db/eval_stage5a_<tag>.txt

指标全部由本脚本本地实现（不依赖生产代码里的新函数），这样 baseline 与 after 才可比；
如果生产代码里已经有 redundancy_reasons，会额外打印它，用来核对两边是否一致。
"""
import io
import os
import re
import sys

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import core.assistant_graph as ag

TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 1

ag.get_stream_writer = lambda: None          # 不在图里跑，状态流不适用

_SENT_SPLIT = re.compile(r"(?<=[。！？?!；;\n])")


def question_sentences(text):
    """正文里能算「问句」的整句 —— 取严口径。

    为什么不用「什么/怎么/多少/是否」这类疑问词：它们在建议句和从句里大量出现，
    实测把「向现场人员问清占用从什么时候开始的」这种建议句误判成问句，
    用它计数会造出假告警。所以只认两种：带问号，或以 吗/呢 结尾
    （后一种是 question_limiter 把多余问号去掉之后的残留形态）。
    """
    out = []
    for sentence in _SENT_SPLIT.split(str(text or "")):
        value = sentence.strip()
        if not value:
            continue
        if "？" in value or "?" in value:
            out.append(value)
            continue
        if value.rstrip("。！!；;，,、 ").endswith(("吗", "呢")):
            out.append(value)
    return out


def _cjk_ngrams(text, n=3):
    grams = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        for i in range(len(run) - n + 1):
            grams.add(run[i:i + n])
    return grams


def _overlap(a, b, n=3, threshold=2):
    return len(_cjk_ngrams(a, n) & _cjk_ngrams(b, n)) >= threshold


def _branch_keys(state):
    """本地实现：report_missing 减掉 A 类 missing。"""
    out = []
    for issue in state.get("issues") or []:
        missing = set(str(k) for k in (issue.get("missing") or []))
        for key in issue.get("report_missing") or []:
            key = str(key)
            if key not in missing and key not in out:
                out.append(key)
    return out


def _a_missing(state):
    return [str(k) for issue in state.get("issues") or []
            for k in (issue.get("missing") or [])]


def _code_of(state):
    issues = state.get("issues") or []
    return str((issues[0] or {}).get("subcategory_code") or "") if issues else ""


def _schema_question(code, key):
    return next((s.question for s in ag.get_slot_schema(code) if s.key == key), "")


_FULL_SECTIONS = ("一、", "二、", "三、")


def full_sections(body):
    """完整档的三段式契约（触犯法规 / 安全隐患 / 类似案例）在不在。"""
    return [mark in str(body or "") for mark in _FULL_SECTIONS]


def local_redundancy(state, body):
    """本地实现冗余判定，规则与生产实现一致（即使生产还没改也能跑 baseline）。

    硬判：b_class_also_branched / question_without_decision_missing /
          extra_question_beside_followup
    启发式：b_slot_question_overlap:<key> / a_slot_expanded_beside_followup:<key>
    """
    reasons = []
    questions = question_sentences(body)
    branches = _branch_keys(state)
    a_missing = _a_missing(state)
    if questions and not a_missing:
        reasons.append("question_without_decision_missing")
        if branches:
            reasons.append("b_class_also_branched")
    if questions and a_missing and branches and len(questions) > 1:
        reasons.append("extra_question_beside_followup")
    for issue in state.get("issues") or []:
        code = str(issue.get("subcategory_code") or "")
        missing = set(str(k) for k in (issue.get("missing") or []))
        for key in issue.get("report_missing") or []:
            key = str(key)
            if key in missing:
                continue
            hint = _schema_question(code, key)
            if hint and any(_overlap(q, hint) for q in questions):
                reasons.append("b_slot_question_overlap:%s" % key)
    if questions and a_missing:
        joined = set(questions)
        non_question = " ".join(s for s in _SENT_SPLIT.split(str(body or ""))
                                if s.strip() and s.strip() not in joined)
        for issue in state.get("issues") or []:
            code = str(issue.get("subcategory_code") or "")
            for key in issue.get("missing") or []:
                hint = _schema_question(code, str(key))
                if hint and _overlap(non_question, hint):
                    reasons.append("a_slot_expanded_beside_followup:%s" % key)
    return list(dict.fromkeys(reasons))


def _state(**over):
    state = {"messages": [], "premises_scope": "public", "vision_summary": ""}
    state.update(over)
    return state


CASES = [
    ("A 完整档 / 只缺 impact(B) —— 消防通道", _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车", "persistence": "长期"},
                 "missing": [], "report_missing": ["impact"]}],
        categories=["fire_lane_blocked"],
        category_results={"fire_lane_blocked": {
            "regulation": "《消防法》第28条：任何单位、个人不得占用、堵塞、封闭疏散通道、安全出口、消防车通道；"
                          "第60条第1款第3项：占用、堵塞、封闭消防车通道，妨碍消防车通行的，责令改正，处5000元以上5万元以下罚款。",
            "case": "萍乡某小区火灾，5 辆私家车占用消防车通道，延误救援。"}},
        missing=[], report_mode="full")),
    ("B 完整档 / 只缺 traffic(B) —— 井盖", _state(
        issues=[{"major_code": "municipal", "subcategory_code": "manhole_damage",
                 "slots": {"defect": "井盖缺失"}, "missing": [], "report_missing": ["traffic"]}],
        categories=["manhole_damage"],
        category_results={"manhole_damage": {
            "regulation": "《城市道路管理条例》相关规定：道路附属设施缺失应及时修复并设置警示标志。",
            "case": "库内暂未检索到"}},
        missing=[], report_mode="full")),
    ("C 初步档 / 缺 persistence(A) + impact(B)", _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "废旧家具"}, "missing": ["persistence"],
                 "report_missing": ["persistence", "impact"]}],
        categories=["fire_lane_blocked"],
        category_results={"fire_lane_blocked": {
            "regulation": "《消防法》第28条；长期占用可依第60条处罚，临时占用以责令改正为主。",
            "case": "库内暂未检索到"}},
        missing=["fire_lane_blocked_persistence"], report_mode="preliminary")),
    ("D 初步档 / A 类齐 + 只缺 impact(B) —— 线上复现「小区消防通道老是停着车」", _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "停着的车", "persistence": "长期"},
                 "missing": [], "report_missing": ["impact"]}],
        categories=["fire_lane_blocked"],
        category_results={"fire_lane_blocked": {
            "regulation": "《消防法》第28条；第60条第1款第3项。",
            "case": "库内暂未检索到"}},
        missing=[], report_mode="preliminary")),
]

lines = []
print("tag=%s samples=%d" % (TAG, SAMPLES))
for name, state in CASES:
    for sample in range(1, SAMPLES + 1):
        try:
            out = ag.report(state)
        except Exception as exc:                       # noqa: BLE001
            print("用例 %s sample=%d -> FAILED %s: %s" % (name, sample, type(exc).__name__, exc))
            lines.append("用例 %s sample=%d -> FAILED %s" % (name, sample, type(exc).__name__))
            continue
        body = out.get("draft_report") or ""
        coverage = ag.preliminary_coverage(body)
        reasons = local_redundancy(state, body)
        prod = getattr(ag, "redundancy_reasons", None)
        prod_reasons = prod(state, body) if prod else None
        sections = full_sections(body)
        row = {
            "case": name, "sample": sample,
            "sections": sections,
            "branches": body.count("若"),
            "chars": len(body),
            "coverage": coverage,
            "all_blocks": all(coverage.values()),
            "qmark": body.count("？") + body.count("?"),
            "questions": len(question_sentences(body)),
            "redundancy": reasons,
            "prod_redundancy": prod_reasons,
            "empty_talk": ag.empty_talk_hits(body),
        }
        print("---- %s sample=%d" % (name, sample))
        print("branches(若)=%d chars=%d coverage=%s all=%s qmark=%d qsent=%d"
              % (row["branches"], row["chars"], row["coverage"], row["all_blocks"],
                 row["qmark"], row["questions"]))
        print("sections=%s all_sections=%s" % (sections, all(sections)))
        print("redundancy=%s prod=%s empty_talk=%s"
              % (row["redundancy"], row["prod_redundancy"], row["empty_talk"]))
        print(body)
        print()
        lines.append(
            "用例 %s | sample=%d | 分支数=%d | 字数=%d | 三块=%s/%s/%s all=%s | 三段式=%s | "
            "问号=%d | 问句=%d | 冗余=%s | 生产冗余=%s | 空话=%s"
            % (name, sample, row["branches"], row["chars"],
               coverage["judgment"], coverage["missing"], coverage["question"], row["all_blocks"],
               sections, row["qmark"], row["questions"], reasons, prod_reasons,
               row["empty_talk"]))
        lines.append("---- 正文 ----")
        lines.append(body)
        lines.append("")

path = os.path.join("db", "eval_stage5a_%s.txt" % TAG)
with open(path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print("summary -> %s" % path)
