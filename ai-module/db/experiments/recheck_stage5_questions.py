# -*- coding: utf-8 -*-
"""复核：case 1 / 3 走报告路径时交付文本里的那个问号从哪来（只读）。"""
import io, os, sys, time
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from langchain_core.messages import HumanMessage
import core.assistant_graph as ag

CASES = ["楼道里的消防通道被东西占了", "小区消防通道老是停着车", "路边有个井盖不见了"]
app = ag.build_graph()
out = []
for i, text in enumerate(CASES, 1):
    cfg = {"configurable": {"thread_id": "s5-recheck-%d-%d" % (i, time.time())}}
    chunks = []
    for mode, item in app.stream({"session_id": "s5r", "messages": [HumanMessage(content=text)]},
                                cfg, stream_mode=["updates", "custom"]):
        if mode == "custom" and isinstance(item, dict) and "chunk" in item:
            chunks.append(str(item["chunk"]))
    txt = "".join(chunks)
    out.append("=" * 72)
    out.append("[%d] %s" % (i, text))
    out.append("全文：\n" + txt)
    out.append("\n问号出现处：")
    import re
    for m in re.finditer(r"[^。！\n]*[？?]", txt):
        out.append("   ...%s" % m.group(0)[-70:])
    out.append("")
print("\n".join(out))
open(os.path.join("db", "eval_stage5_recheck.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print("saved -> db/eval_stage5_recheck.txt")
