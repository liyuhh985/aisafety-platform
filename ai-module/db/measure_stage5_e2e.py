# -*- coding: utf-8 -*-
"""阶段 5 端到端测量：三级降级链在**完整图**里各被用到几次。

为什么要端到端：此前的证据是节点级（直接调 ask_slot_question），
证明不了节点在真实整轮里会被走到。本轮跑完整图，逐轮记录 question_source。

口径：
 1) 每个输入一个全新 thread_id（干净首轮），跑完整图，stream_mode=[updates, custom]
 2) 从 updates 里抓 understand 的 next_action/missing/danger_veto，
    以及 ask_slot_question 的 question_source（节点跑了才有）
 3) 从 custom 收 chunk，拼成交付文本；与终态 draft_report（若有）比对
 4) 独立信号：交付问句是否**逐字等于**该小类 schema 里的固定串
    —— 因为 dialogue_policy._question_for_missing 也会退回 schema 问句，
    所以 source 标 understand 的问句可能是「穿着 understand 外衣的第 3 级」。
每条跑完立即 append；失败记录不重试。
"""
import io, os, sys, time
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage
import core.assistant_graph as ag
from core.slot_schemas import missing_decision_slots, get_slot_schema

OUT = os.path.join(os.getcwd(), "db", "eval_stage5_e2e.txt")

CASES = [
    ("消防通道", "楼道里的消防通道被东西占了"),
    ("消防通道", "消防通道堆了不少杂物，也没人管"),
    ("消防通道", "小区消防通道老是停着车"),
    ("危房", "我们小区旁边有栋危房"),
    ("危房", "村里那栋老房子墙都裂了，看着要塌"),
    ("危房", "老城区有栋楼看着很危险"),
    ("消防设施", "楼道的消防栓有问题"),
    ("消防设施", "小区里的灭火器好像不太对"),
    ("消防设施", "消防设施坏了没人修"),
    ("电气", "路边的电表箱有问题"),
    ("电气", "墙上的电线看着不太对劲"),
    ("电气", "配电箱那边的情况不太正常"),
    ("占道", "路口那边摆摊的特别多"),
    ("占道", "马路边上占道的情况挺严重"),
    ("占道", "有人在人行道上摆摊经营"),
    ("井盖", "路边有个井盖不见了"),
    ("井盖", "路上井盖有点问题"),
    ("其他", "路边放着几个大桶，也不知道装的什么，有股味儿"),
    ("其他", "楼下垃圾堆成山了，一直没人拉走"),
    ("施工", "工地上围挡没了"),
]

ASK_ACTIONS = ("ask_critical_question", "answer_with_optional_question")


def schema_question(code, keys):
    """该小类按 schema 顺序、第一个缺失 A 类槽的固定问句。"""
    want = {str(k).strip() for k in (keys or [])}
    for slot in get_slot_schema(code):
        if slot.key in want:
            return slot.question.strip()
    return ""


def run_case(app, text, tag):
    config = {"configurable": {"thread_id": "stage5-%s-%d" % (tag, time.time())}}
    nodes, chunks, intr = [], [], []
    und, askupd = {}, {}
    for mode, item in app.stream(
        {"session_id": "s5", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            if isinstance(item, dict) and "chunk" in item:
                chunks.append(str(item["chunk"]))
            continue
        if not isinstance(item, dict):
            continue
        if "__interrupt__" in item:
            intr.append(str((item.get("__interrupt__") or [{}])[0]))
        for name, upd in item.items():
            nodes.append(name)
            if name == "understand" and isinstance(upd, dict):
                und = upd
            if name == "ask_slot_question" and isinstance(upd, dict):
                askupd = upd
    values = app.get_state(config).values
    return {
        "nodes": nodes, "und": und, "ask": askupd, "chunks": "".join(chunks),
        "values": values, "interrupts": intr,
    }


def main():
    app = ag.build_graph()
    total = len(CASES)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("阶段 5：三级降级链端到端测量（完整图，真模型）\n")
        fh.write("输入 %d 条，每例只跑 1 次 —— 无方差数据。\n" % total)
        fh.write("口径：全新 thread_id 干净首轮；source 取 ask_slot_question 节点写入值。\n\n")
    stat = {"end_to_end_ask": 0, "ask_slot_question": 0, "understand": 0,
            "slot_schema": 0, "none": 0, "did_not_ask": 0, "failed": 0}
    rows = []
    for idx, (label, text) in enumerate(CASES, 1):
        t0 = time.time()
        head = "=" * 74
        block = [head, "[%d/%d] %s | 输入：%s" % (idx, total, label, text)]
        try:
            r = run_case(app, text, str(idx))
        except Exception as exc:
            stat["failed"] += 1
            block.append("  失败：%r" % (exc,))
            print("\n".join(block), flush=True)
            with open(OUT, "a", encoding="utf-8") as fh:
                fh.write("\n".join(block) + "\n")
            continue
        und, ask, vals = r["und"], r["ask"], r["values"]
        code = str(und.get("locked_subcategory") or "")
        keys = [s.key for s in missing_decision_slots(code, (und.get("category_slots") or {}).get(code) or {})] if code else []
        missing = list(und.get("missing") or [])
        action = str(und.get("next_action") or "")
        source = str(ask.get("question_source") or vals.get("question_source") or "")
        q = str(ask.get("clarification_question") or vals.get("clarification_question") or "")
        fixed = schema_question(code, keys)
        ran = "ask_slot_question" in r["nodes"]
        if ran:
            stat["end_to_end_ask"] += 1
            stat[source if source in ("ask_slot_question", "understand", "slot_schema") else "none"] += 1
        elif action in ASK_ACTIONS and missing:
            stat["did_not_ask"] += 1
        block.append("  节点序列：%s" % " -> ".join(r["nodes"]))
        block.append("  锁定小类：%s | 动作：%s | danger_veto=%s | missing=%s"
                     % (code or "-", action or "-", und.get("danger_veto"), missing or "-"))
        block.append("  A 类缺失：%s" % (keys or "-"))
        block.append("  understand 自带问句：%s" % (und.get("clarification_question") or "-"))
        block.append("  新节点是否分流：%s | source=%s" % (ran, source or "-"))
        block.append("  最终问句：%s" % (q or "（没问）"))
        block.append("  与 schema 固定串逐字相同：%s | 固定串=%s"
                     % (bool(q) and q.strip() == fixed and fixed != "", fixed or "-"))
        draft = str(vals.get("draft_report") or "")
        if draft:
            block.append("  一致性 join(chunks)==draft：%s | chunk 数=%d"
                         % ("".join(r["chunks"]) == draft, len(r["chunks"])))
        block.append("  问号数=%d | 交付文本前 60 字：%s"
                     % (r["chunks"].count("？") + r["chunks"].count("?"), r["chunks"][:60].replace("\n", " ")))
        block.append("  question_dropped=%s | question_missing=%s"
                     % (vals.get("question_dropped") or "-", vals.get("question_missing") or "-"))
        block.append("  耗时：%.1fs" % (time.time() - t0))
        block.append("")
        rows.append((label, text, code, ",".join(keys), ran, source, q))
        print("\n".join(block), flush=True)
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write("\n".join(block) + "\n")
    summary = ["=" * 74, "汇总：", str(stat), "",
               "明细（小类 | A 类缺失 | 分流 | source | 问句）："]
    for label, text, code, keys, ran, source, q in rows:
        summary.append("  %s | %s | %s | 分流=%s | %s | %s" % (label, code or "-", keys or "-", ran, source or "-", q or "-"))
    print("\n".join(summary))
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write("\n".join(summary) + "\n")
    print("saved -> db/eval_stage5_e2e.txt")


if __name__ == "__main__":
    main()
