"""G5：追问轮数。A 上界（critical 槽位数）；B 线上多轮实测（5 小类 × 2 开场，最多 4 轮）。
问句提取=最后一个以 ？/吗/呢 结尾的句子；建单邀请不计槽位轮；每轮跑完立即 append。"""
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "db"))
from core.hazard_taxonomy import SUBCATEGORY_TO_MAJOR
from core.slot_schemas import SUBCATEGORY_SLOT_SCHEMAS, get_slot_schema
from eval_queries import QUERY_SET
from g1_question_target import classify_question
OUT = os.path.join(os.getcwd(), "db", "eval_followup_rounds.txt")
HOST = "ubuntu@106.53.219.214"
PAYLOAD = os.path.join(os.getcwd(), "db", "_g5payload.json")
CURL = ("curl -N -s -X POST -H 'Content-Type: application/json' "
        "--data-binary @/tmp/g5_payload.json http://127.0.0.1:8000/api/ai/assistant/stream")
TARGETS = ["fire_lane_blocked", "road_occupancy", "dangerous_building", "gas_leak", "manhole_damage"]
SPARSE = {"fire_lane_blocked": "楼下通道全停了车", "road_occupancy": "路边全是摆摊的",
          "dangerous_building": "有栋楼看着要倒", "gas_leak": "楼道里有很重的煤气味",
          "manhole_damage": "路上一个井盖没了"}
MAX_ROUNDS = 4
INVITE_KEYS = ("建一条隐患任务", "建任务", "创建任务", "上报任务")
DECLINE = "先不用建任务，谢谢"
DEFAULT_ANSWER = "具体情况我也说不太清楚，大概就是这样，一直没人处理"
ANSWERS = {
    "persistence": "已经这样挺长时间了，大概半年多了，一直没人管", "behavior": "就是摆摊卖东西，还有一堆杂物堆在那儿", "blocked": "基本堵死了，人得侧着身子才过得去", "blocker": "堆的是旧家具和纸箱，还有一辆废弃三轮车", "structure": "墙上裂缝很明显，看着有点往外倾斜",
    "occupancy": "里面还住着人，有老人", "risk": "感觉随时可能塌下来，挺危险的", "facility_type": "是楼道的消火栓", "condition": "已经完全坏了，打不开也出不了水", "function_impact": "整栋楼的消防报警都受影响了",
    "source": "是从六楼阳台外墙掉下来的", "target": "下面就是人行道，来来往往的人很多", "exposure": "没有任何围挡和警示标志", "defect": "井盖整个掉下去了，露着一个大坑", "traffic": "行人和车都得绕行，影响挺大",
    "impact": "影响挺大，基本没法正常通行", "contact": "能碰到，就在人手够得到的位置", "site": "完全没做围挡，随便进出", "safety": "没有任何安全警示和防护", "describe": "就是一个看着挺危险的情况，具体我也说不太清",
}

def last_question(text):
    """回复里最后一个以 ？/吗/呢 结尾的句子（追问拼在末尾）。"""
    buf, sents = "", []
    for ch in (text or "").replace("?", "？"):
        buf += ch
        if ch in "。！？\n":
            sents.append(buf.strip())
            buf = ""
    if buf.strip():
        sents.append(buf.strip())
    for s in reversed(sents):
        if s.endswith("？") or s.endswith("吗") or s.endswith("呢"):
            return s
    return ""
def one_round(session_id, message):
    """经 ssh 在服务器本机 curl 打 SSE；中文用文件传，避免 shell 转码。"""
    with open(PAYLOAD, "w", encoding="utf-8") as fh:
        json.dump({"message": message, "session_id": session_id}, fh, ensure_ascii=False)
    scp = subprocess.run(["scp", "-q", PAYLOAD, HOST + ":/tmp/g5_payload.json"],
                         capture_output=True, timeout=60)
    if scp.returncode != 0:
        raise RuntimeError("scp failed: " + scp.stderr.decode("utf-8", "replace")[:120])
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, CURL], capture_output=True, timeout=300)
    if res.returncode != 0:
        raise RuntimeError("ssh failed: " + res.stderr.decode("utf-8", "replace")[:120])
    reply, status, tax = [], [], {}
    for raw in res.stdout.decode("utf-8", "replace").splitlines():
        raw = raw.strip()
        if not raw.startswith("data: "):
            continue
        try:
            evt = json.loads(raw[6:])
        except Exception:
            continue
        kind, content = evt.get("type"), evt.get("content")
        if kind == "chunk":
            reply.append(content or "")
        elif kind == "status":
            status.append(content or "")
        elif kind == "taxonomy" and isinstance(content, dict):
            tax = content
        elif kind == "error":
            reply.append("[error] %s" % content)
    return "".join(reply), status, tax

def part_a(fh):
    dist, lines = {}, ["===== A 上界：每个小类 critical=True 的槽位数（覆盖 taxonomy 全部 %d 个小类）====="
                       % len(SUBCATEGORY_TO_MAJOR)]
    for sub in sorted(SUBCATEGORY_TO_MAJOR):
        keys = [s.key for s in get_slot_schema(sub) if s.critical]
        dist[len(keys)] = dist.get(len(keys), 0) + 1
        tag = "" if sub in SUBCATEGORY_SLOT_SCHEMAS else "  <-- 槽位表未单独定义，回落到「其他」"
        lines.append("%-26s critical=%d  %s%s" % (sub, len(keys), keys, tag))
    lines += ["", "分布：%s（共 %d 个小类）" % (
        " / ".join("%d个×%d" % (v, k) for k, v in sorted(dist.items())),
        len(SUBCATEGORY_TO_MAJOR)),
        "含义：critical=2 的小类追问上界 2 轮，critical=3 的上界 3 轮。", ""]
    print("\n".join(lines), flush=True)
    fh.write("\n".join(lines) + "\n")

def opening(sub, style):
    if style == "sparse":
        return SPARSE[sub]
    for item in QUERY_SET:
        if item.get("subcategory") == sub and item.get("style") == "explicit":
            return item["query"]
    return sub

def run_session(fh, sub, style):
    sid, message = "g5-%s-%s-%d" % (sub, style, int(time.time())), opening(sub, style)
    lines = ["", "--- %s [%s开场] session=%s ---" % (sub, style, sid),
             "  [第1轮] 我说: %s" % message]
    rounds, slots = 0, []
    for rnd in range(1, MAX_ROUNDS + 1):
        try:
            reply, status, tax = one_round(sid, message)
        except Exception as exc:
            lines.append("  [第%d轮] 失败: %s（停止该 session）" % (rnd, exc.__class__.__name__))
            break
        if rnd == 1:
            lines.append("  识别小类=%s 大类=%s 末段状态=%s" % (
                tax.get("locked_subcategory") or "-", tax.get("locked_major") or "-",
                " > ".join(status[-3:])))
        q = last_question(reply)
        if not q:
            lines.append("  [第%d轮] 回复末尾无问句 -> 追问结束" % rnd)
            break
        if any(k in q for k in INVITE_KEYS):
            lines.append("  [第%d轮] 建单邀请（不计槽位轮）: %s" % (rnd, q))
            lines.append("  [第%d轮] 我答: %s" % (rnd, DECLINE))
            message = DECLINE
            continue
        slot = classify_question(q)
        rounds += 1
        slots.append(slot or "?")
        lines.append("  [第%d轮] 槽位追问: %s  (线索=%s)" % (rnd, q, slot or "?"))
        message = ANSWERS.get(slot, DEFAULT_ANSWER)
        lines.append("  [第%d轮] 我答: %s" % (rnd, message))
    lines.append("  => 实际槽位追问轮数=%d  槽位序列=%s" % (rounds, " -> ".join(slots) or "-"))
    print("\n".join(lines), flush=True)
    fh.write("\n".join(lines) + "\n")
def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("G5：追问轮数（上界 + 线上实测 5 小类 × 2 开场；每例 1 次，无方差数据）\n\n")
        part_a(fh)
        fh.write("\n===== B 实测：线上多轮 SSE（最多 %d 轮）=====\n" % MAX_ROUNDS)
        fh.write("线上地址 http://127.0.0.1:8000/api/ai/assistant/stream（全句：8000 未对公网开放，经 ssh 调用）\n")
        for style in ("explicit", "sparse"):
            for sub in TARGETS:
                run_session(fh, sub, style)
        fh.write("\n===== 汇总 =====\n上界见 A；实测轮数见 B 每小节末尾的「实际槽位追问轮数」。\n")
    print("done", flush=True)
if __name__ == "__main__":
    main()
