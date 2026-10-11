"""G3：兜底触发率 —— 用模糊/极短输入（不是 explicit 长句）。

判定"走了固定兜底"的口径：最终问句与 core.slot_schemas 里某个 Slot.question 完全相同。
每条处理完立即 append；单条失败记录不重试。
"""
import io
import os
import sys
import time

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage

from core.assistant_graph import understand
from core.slot_schemas import SLOT_SCHEMAS

OUT = os.path.join(os.getcwd(), "db", "eval_fallback_rate.txt")

FUZZY = [
    "楼下有问题",
    "有味儿",
    "楼道里不对劲",
    "我们小区有个东西坏了",
    "路边那个坏了好久了",
    "门口那玩意儿要塌了",
    "电梯有问题",
    "路上有个坑",
]

FIXED = {}
for _name, _slots in SLOT_SCHEMAS.items():
    for _s in _slots:
        FIXED.setdefault(_s.question.strip(), _name)


def main() -> None:
    header = [
        "G3：兜底触发率（模糊/极短输入 8 条，每例只跑 1 次，无方差数据）",
        "口径：最终问句 == core.slot_schemas 里某个 Slot.question（完全相同）= 走了固定兜底。",
        "固定问句共 %d 条（去重后）。" % len(FIXED),
        "",
    ]
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header) + "\n")

    fallback = 0
    asked = 0
    failed = 0
    t0 = time.time()
    for idx, text in enumerate(FUZZY, 1):
        try:
            out = understand({"messages": [HumanMessage(content=text)]})
        except Exception as exc:
            failed += 1
            line = "[%d/8] 失败 输入=%s 原因=%s" % (idx, text, exc.__class__.__name__)
            print(line, flush=True)
            with open(OUT, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            continue

        sub = out.get("locked_subcategory") or out.get("locked_major") or "(未锁定)"
        major = out.get("locked_major") or ""
        q = (out.get("clarification_question") or "").strip()
        is_fb = bool(q) and q in FIXED
        if q:
            asked += 1
        if is_fb:
            fallback += 1
        line = "[%d/8] 输入=%s\n      小类=%s 大类=%s\n      问句=%s\n      兜底=%s %s" % (
            idx, text, sub, major, q or "(未问)", "是" if is_fb else "否",
            ("命中固定串来源=%s" % FIXED[q]) if is_fb else "")
        print(line, flush=True)
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    summary = [
        "",
        "===== 汇总（耗时 %.0f 秒）=====" % (time.time() - t0),
        "样本=8  失败=%d" % failed,
        "实际问了=%d  走了固定兜底=%d" % (asked, fallback),
        "兜底率（兜底 / 实际提问）=%.3f" % (fallback / asked if asked else 0.0),
        "兜底率（兜底 / 全部 8 条）=%.3f" % (fallback / 8.0),
        "说明：8 条里没被问的（未锁定小类/越界/无追问）不计入分母分子，逐条见上。",
    ]
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write("\n".join(summary) + "\n")
    print("\n".join(summary), flush=True)


if __name__ == "__main__":
    main()
