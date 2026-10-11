# -*- coding: utf-8 -*-
"""阶段 5a 变异测试：改坏 → 应变红 → 用原始字节恢复 → 比 sha256。

自保：改文件前先把原始字节读进内存；恢复用它，不用 git checkout。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

AG = "core/assistant_graph.py"
DU = "core/dialogue_understanding.py"
TESTS = ["tests/test_redundancy_observation.py"]

MUTATIONS = [
    ("观测：不再判 b_class_also_branched", AG,
     '        if branches:\n            reasons.append("b_class_also_branched")\n',
     '        if False:\n            reasons.append("b_class_also_branched")\n'),
    ("观测：A 类被展开不再报", AG,
     '                if hint and slot_question_overlap(statements, hint[0]):\n'
     '                    reasons.append("a_slot_expanded_beside_followup:%s" % str(key))\n',
     '                if False:\n'
     '                    reasons.append("a_slot_expanded_beside_followup:%s" % str(key))\n'),
    ("观测：问句指向不明不再告警", AG,
     '        logger.warning("question_target_unknown origin=%s code=%s missing=%s question=%s",\n'
     '                       origin, code, keys, value)\n',
     '        pass\n'),
    ("观测：目标槽对不上不再告警", AG,
     '    logger.warning("question_target_mismatch origin=%s code=%s target=%s missing=%s question=%s",\n'
     '                   origin, code, target, keys, value)\n',
     '    pass\n'),
    ("观测：冗余告警不接进 report", AG,
     '        _warn_empty_talk(state, body)\n        _warn_redundancy(state, body)\n'
     '        coverage = preliminary_coverage(body)\n',
     '        _warn_empty_talk(state, body)\n'
     '        coverage = preliminary_coverage(body)\n'),
    ("观测：冗余告警不接进 report（完整档）", AG,
     '    body = "".join(buf)\n    _warn_empty_talk(state, body)\n'
     '    _warn_redundancy(state, body)\n    return _deliver_report(state, body, ask_create)\n',
     '    body = "".join(buf)\n    _warn_empty_talk(state, body)\n'
     '    return _deliver_report(state, body, ask_create)\n'),
    ("提示词：去重规则不再注入", AG,
     '        + (REPORT_DEDUP_RULE if (branch or followup) else "") +',
     '        + "" +'),
    ("提示词：去重规则照抄带方括号的标签", AG,
     '    "材料里标着「仍缺信息」的那一项（缺了它处置方向会判错），"',
     '    "材料里标着「[仍缺信息]」的那一项（缺了它处置方向会判错），"'),
    ("问句识别改宽松（把建议句也算问句）", AG,
     '        if value.rstrip("。！!；;，,、 ").endswith(("吗", "呢")):\n            out.append(value)\n',
     '        if value.rstrip("。！!；;，,、 ").endswith(("吗", "呢")) or "什么时候" in value:\n'
     '            out.append(value)\n'),
    ("材料：A 行不再标注由追问承载", AG,
     '                         + "（这一项由本轮末尾的那一个追问承载）")',
     '                         + "")'),
    ("契约：parse_plan 丢掉 question_target", DU,
     '    question_target = str(data.get("question_target") or "").strip() if question else ""\n',
     '    question_target = ""\n'),
]


def run_tests():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, encoding="utf-8", errors="replace")
    last = [l for l in proc.stdout.splitlines() if "passed" in l or "failed" in l]
    return proc.returncode, (last[-1] if last else proc.stdout[-160:])


code, summary = run_tests()
print("基线（无变异）: rc=%s %s" % (code, summary))
assert code == 0, "基线必须是绿的"

bad = 0
for name, path, old, new in MUTATIONS:
    original = open(path, "rb").read()
    sha = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    if text.count(old) != 1:
        print("SKIP(anchor %d) %s" % (text.count(old), name))
        bad += 1
        continue
    try:
        open(path, "w", encoding="utf-8", newline="\n").write(text.replace(old, new))
        code, summary = run_tests()
    finally:
        open(path, "wb").write(original)
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == sha, name
    verdict = "RED(应红)" if code != 0 else "GREEN(不该绿)"
    if code == 0:
        bad += 1
    print("%-34s -> %s | %s" % (name, verdict, summary))
print("恢复后 sha256 全部一致；异常项=%d" % bad)
