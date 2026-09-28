"""G1（全量 64 条）：模型自由写的追问句，是否命中代码算出的 missing 槽。

口径（启发式，非人工逐条判定）：
  1) 问句为空 -> 未问（missing 非空）/ 无（missing 为空）
  2) 问句与某个 Slot.question 完全相同 -> 归到该槽（这是"走了固定兜底"，最强信号）
  3) 否则按 SLOT_HINTS 关键词线索打分归类，命中数最多者胜，并列按定义顺序取先者
  4) 归到的槽在 missing 里 = 命中；不在 = 未命中；归不出来 = 无法归类

每条处理完立即 append；单条失败记录失败原因，不重试。
"""
import io
import os
import sys
import time
import traceback

sys.path.insert(0, os.getcwd())

from langchain_core.messages import HumanMessage

from core.assistant_graph import understand
from core.slot_schemas import SLOT_SCHEMAS
from eval_queries import QUERY_SET

OUT = os.path.join(os.getcwd(), "db", "eval_question_target.txt")

# 槽位语义线索（写死；仅用于把模型自由写的问句归到一个槽）
SLOT_HINTS = {
    "persistence": ["长期", "临时", "多久", "多长时间", "持续多久", "存在多长", "多久了"],
    "behavior": ["摆摊", "车辆停放", "哪一类占", "什么占道", "怎么占"],
    "blocked": ["堵死", "完全堵", "部分占", "能不能过", "能否通过"],
    "blocker": ["什么东西", "被什么", "谁占", "占用", "堆的是", "停的是", "什么挡住"],
    "structure": ["裂缝", "倾斜", "沉降", "结构"],
    "occupancy": ["有人住", "有人居住", "住人", "使用中", "里面有人", "居住或使用"],
    "risk": ["坍塌", "倒塌", "垮", "即时", "随时倒"],
    "facility_type": ["消火栓", "喷淋", "报警器", "灭火器", "哪一类消防设施", "哪类消防设施"],
    "condition": ["老旧", "损坏", "无法使用", "失灵", "能不能用", "完全不能用"],
    "function_impact": ["整栋", "报警或灭火", "消防功能"],
    "source": ["从哪", "哪掉", "来源", "外墙", "阳台", "广告牌", "哪里来"],
    "target": ["人行道", "车行道", "下面是"],
    "exposure": ["围挡", "警示", "警告标志"],
    "defect": ["缺失", "破损", "松动", "井盖"],
    "traffic": ["行人", "车辆通行", "影响交通", "车过不去"],
    "impact": ["影响通行", "通行", "受到影响"],
    "contact": ["接触到", "碰到", "触碰", "够得到"],
    "site": ["施工区域", "围挡", "现场管理"],
    "safety": ["安全警示", "防护", "警示标志"],
    "describe": ["再具体描述", "具体描述", "详细说说", "具体是什么隐患"],
}

Q2SLOT = {}
for _name, _slots in SLOT_SCHEMAS.items():
    for _s in _slots:
        Q2SLOT.setdefault(_s.question.strip(), (_s.key, _name))


def is_in_major_question(q: str) -> bool:
    """类内枚举问句（"具体是哪一类XX隐患"）不是槽位问句，单独归类。"""
    text = (q or "").strip()
    return "具体是哪一类" in text and "隐患" in text
def classify_question(q: str) -> str:
    """把一句追问归到一个槽位 key；归不出返回空串。"""
    text = (q or "").strip()
    if not text or is_in_major_question(text):
        return ""
    exact = Q2SLOT.get(text)
    if exact:
        return exact[0]
    best, best_hits = "", 0
    for key, hints in SLOT_HINTS.items():
        hits = sum(1 for h in hints if h in text)
        if hits > best_hits:
            best, best_hits = key, hits
    return best if best_hits > 0 else ""
def missing_slot_keys(out: dict) -> list:
    cats = list(out.get("categories") or [])
    if not cats:
        cats = [i.get("subcategory_code", "") for i in (out.get("issues") or [])]
    keys = []
    for entry in out.get("missing") or []:
        for cat in cats:
            if cat and entry.startswith(cat + "_"):
                keys.append(entry[len(cat) + 1:])
                break
    return keys
def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    total = len(QUERY_SET)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("G1：plan[question] 是否命中代码算的 missing（全量 %d 条，每例只跑 1 次，无方差数据)\n" % total)
        fh.write("口径：启发式归类（schema 问句精确匹配优先，否则按关键词线索打分）；未命中/无法归类逐条列出。\n")
        fh.write("线索表：%s\n\n===== 逐条明细（每条跑完立即追加）=====\n" % SLOT_HINTS)
    stat = {"命中": 0, "未命中": 0, "未问": 0, "多余": 0, "多余(类内枚举)": 0, "无": 0, "无法归类": 0, "失败": 0}
    rows, t0 = [], time.time()
    for idx, item in enumerate(QUERY_SET, 1):
        try:
            out = understand({"messages": [HumanMessage(content=item["query"])]})
        except Exception as exc:  # 记录失败，不重试
            stat["失败"] += 1
            print("[%d/%d] 失败 %s: %s" % (idx, total, item.get("subcategory"), exc.__class__.__name__), flush=True)
            with open(OUT, "a", encoding="utf-8") as fh:
                fh.write("[%d/%d] 失败 %s\n%s\n" % (idx, total, item.get("subcategory"), traceback.format_exc()))
            continue
        mkeys = missing_slot_keys(out)
        question = (out.get("clarification_question") or "").strip()
        matched = classify_question(question)
        if not question:
            verdict = "未问" if mkeys else "无"
        elif not mkeys:
            verdict = "多余(类内枚举)" if is_in_major_question(question) else "多余"
        elif matched and matched in mkeys:
            verdict = "命中"
        else:
            verdict = "未命中"
            if not matched:
                stat["无法归类"] += 1
        stat[verdict] += 1
        rows.append((verdict, item.get("subcategory", ""), item.get("style", ""), ",".join(mkeys) or "-",
                     question or "-", matched or "-", item["query"]))
        line = "[%d/%d] %s missing=%s 归到=%s | %s" % (idx, total, verdict, ",".join(mkeys) or "-",
                                                        matched or "-", question or "(未问)")
        print(line, flush=True)
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write("%s %s [%s] %s\n" % (verdict, item.get("subcategory", ""), item.get("style", ""),
                                           question or "(未问)"))
    asked = stat["命中"] + stat["未命中"] + stat["多余"] + stat["多余(类内枚举)"]
    denom = stat["命中"] + stat["未命中"] + stat["未问"]
    out_lines = ["", "===== 汇总（耗时 %.0f 秒）=====" % (time.time() - t0),
                 "总条数=%d  失败=%d（不计入分母）" % (total, stat["失败"]),
                 "命中=%d  未命中=%d  未问=%d  多余追问=%d（其中类内枚举=%d）  无需问=%d" % (
                     stat["命中"], stat["未命中"], stat["未问"],
                     stat["多余"] + stat["多余(类内枚举)"], stat["多余(类内枚举)"], stat["无"]),
                 "其中无法归类（关键词线索没覆盖）=%d" % stat["无法归类"],
                 "有 missing 且该追问的样本=%d，其中一条都没问（黑洞风险）=%d" % (denom, stat["未问"]),
                 "命中率（命中/(命中+未命中+未问)）=%.3f" % (stat["命中"] / denom if denom else 0.0),
                 "命中率（命中/所有实际提问）=%.3f" % (stat["命中"] / asked if asked else 0.0),
                 "", "===== 命中 / 未命中 / 多余 逐条 ====="]
    for v, expect, style, mk, q, matched, orig in rows:
        if v in ("命中", "未命中", "多余", "多余(类内枚举)"):
            out_lines.append("- [%s] %s/%s missing=%s 归到=%s\n    问句: %s\n    用户原话: %s" % (
                v, expect, style, mk, matched, q, orig))
    out_lines += ["", "===== 未问 逐条（missing 非空 = 该问没问）====="]
    for v, expect, style, mk, q, matched, orig in rows:
        if v == "未问":
            out_lines.append("- %s/%s missing=%s\n    用户原话: %s" % (expect, style, mk, orig))
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines) + "\n")
    print("\n".join(out_lines[:10]), flush=True)
if __name__ == "__main__":
    main()
