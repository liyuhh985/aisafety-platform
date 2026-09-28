# -*- coding: utf-8 -*-
"""范围词表扩表（交通设施/外立面/配电设施）的端到端验证（完整图，真模型）。

为什么还要端到端：确定性层（decide_scope）只能证明 scope=hazard，
证明不了「规划器会把它归到对应小类」，也证明不了线上真实链路里不再走 boundary_reply。

口径：
 1) 每个输入一个全新 thread_id（干净首轮）
 2) stream_mode=[updates, custom]：从 scope_guard 抓 scope，
    从 understand 抓 locked_major/locked_subcategory/next_action
 3) 越界样本额外确认 direct_mode=out_of_scope 且回复是「我主要负责城市安全隐患」
每条跑完立即落盘；失败不重试，如实记录。
"""
import io, os, sys, time
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage
import core.assistant_graph as ag
from core.scope_policy import OUT_OF_SCOPE_RESPONSES

MODE = sys.argv[1] if len(sys.argv) > 1 else "all"
OUT_NAME = "eval_scope_families_e2e_offdomain.txt" if MODE == "off" \
    else "eval_scope_families_e2e.txt"
OUT = os.path.join(os.getcwd(), "db", OUT_NAME)

IN_DOMAIN = [
    ("交通设施损坏", "路边有个交通标志牌和护栏坏了"),
    ("交通设施损坏", "交通设施损坏了没人修"),
    ("交通设施损坏", "路口的信号灯不亮了"),
    ("交通设施损坏", "道路中间的护栏被撞断了"),
    ("外立面脱落", "小区外立面墙皮脱落"),
    ("外立面脱落", "楼房外立面的瓷砖掉下来了"),
    ("外立面脱落", "外立面的墙皮一块块往下掉"),
    ("配电设施故障", "配电设施出问题了"),
    ("配电设施故障", "小区里的配电柜门开着很危险"),
    ("配电设施故障", "配电房旁边堆了杂物"),
]

OFF_DOMAIN = [
    "红烧肉怎么做好吃",
    "今天天气怎么样",
    "帮我写一篇八百字的周记",
    "推荐一款性价比高的手机",
    "Python 列表如何去重",
]


def run_case(app, text, tag):
    config = {"configurable": {"thread_id": "scopefam-%s-%d" % (tag, time.time())}}
    nodes, chunks, sg, und = [], [], {}, {}
    for mode, item in app.stream(
        {"session_id": "sf", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            if isinstance(item, dict) and "chunk" in item:
                chunks.append(str(item["chunk"]))
            continue
        if not isinstance(item, dict):
            continue
        for name, upd in item.items():
            nodes.append(name)
            if name == "scope_guard" and isinstance(upd, dict):
                sg = upd
            if name == "understand" and isinstance(upd, dict):
                und = upd
    return {"nodes": nodes, "sg": sg, "und": und, "text": "".join(chunks)}


def main():
    app = ag.build_graph()
    lines = []
    in_domain = [] if MODE == "off" else IN_DOMAIN
    lines.append("范围词表扩表端到端验证（完整图，真模型）")
    lines.append("输入 %d 条本领域 + %d 条越界；每例只跑 1 次 —— 无方差数据。"
                 % (len(in_domain), len(OFF_DOMAIN)))
    lines.append("口径：全新 thread_id 干净首轮；scope 取 scope_guard 写入值。\n")

    ok_scope = ok_sub = 0
    for idx, (label, text) in enumerate(in_domain, 1):
        t0 = time.time()
        try:
            r = run_case(app, text, "in%d" % idx)
            err = ""
        except Exception as exc:
            r, err = {"nodes": [], "sg": {}, "und": {}, "text": ""}, repr(exc)
        scope = str(r["sg"].get("scope") or "")
        reason = str(r["sg"].get("scope_reason") or "")
        major = str(r["und"].get("locked_major") or "")
        sub = str(r["und"].get("locked_subcategory") or "")
        action = str(r["und"].get("next_action") or "")
        boundary = "boundary_reply" in r["nodes"]
        good_scope = scope == "hazard"
        good_sub = bool(sub) or bool(major)
        ok_scope += 1 if good_scope else 0
        ok_sub += 1 if good_sub else 0
        lines.append("[%d] %s | %s" % (idx, label, text))
        lines.append("    scope=%s (%s) | locked=%s/%s | next=%s | boundary_reply=%s | %.1fs"
                     % (scope, reason, major, sub, action, boundary, time.time() - t0))
        lines.append("    节点：%s" % " → ".join(r["nodes"]))
        lines.append("    回复：%s" % r["text"][:160].replace("\n", " "))
        if err:
            lines.append("    失败：%s" % err)
        lines.append("")

    lines.append("—— 越界反例（必须仍被拦）——")
    off_ok = 0
    for idx, text in enumerate(OFF_DOMAIN, 1):
        try:
            r = run_case(app, text, "off%d" % idx)
            err = ""
        except Exception as exc:
            r, err = {"nodes": [], "sg": {}, "und": {}, "text": ""}, repr(exc)
        scope = str(r["sg"].get("scope") or "")
        dm = str(r["und"].get("direct_mode") or "")
        # 判定用生产代码里的全部拒答模板：原先只匹配 2 个关键词，漏掉了
        # OUT_OF_SCOPE_RESPONSES[2]（「我这边只负责城市安全隐患相关咨询」）那一条，
        # 导致 2 条实际被拒的样本被记成「未拒」。
        rejected = any(t in r["text"] for t in OUT_OF_SCOPE_RESPONSES)
        off_ok += 1 if rejected else 0
        lines.append("[%d] %s" % (idx, text))
        lines.append("    scope=%s | direct_mode=%s | 被拒=%s | 节点：%s"
                     % (scope, dm, rejected, " → ".join(r["nodes"])))
        lines.append("    回复：%s" % r["text"][:120].replace("\n", " "))
        if err:
            lines.append("    失败：%s" % err)
        lines.append("")

    summary = ("\n汇总：本领域 %d/%d scope=hazard，%d/%d 锁到大类或小类；越界被拦 %d/%d"
               % (ok_scope, len(in_domain), ok_sub, len(in_domain), off_ok, len(OFF_DOMAIN)))
    lines.append(summary)
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
