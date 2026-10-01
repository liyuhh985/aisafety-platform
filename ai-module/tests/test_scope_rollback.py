# -*- coding: utf-8 -*-
"""决策 7：越界/模糊时**撤销本轮**的锁定，而不是清零。

为什么不是清零：用户只是跑题（"今天天气不错"）时，正在跟的那条隐患要留着。
要撤销的是"**本轮造成的改动**"。

实现期间实测到两件比预想更重要的事，都记在这里：

1. **`out_of_scope` 在"已锁定"时几乎不可达** —— `understand` 会把锁定的那条隐患重新塞回
   `plan["issues"]`，于是 `decide_scope` 的 `if issues:` 分支先命中，永远判 hazard。
   真正可达的是 **`ambiguous`**（`unbacked_hazard_claim` 判"这条说法没有依据"）。
   所以本文件的端到端用例走的是 ambiguous 那条。
2. **槽位被清空的真凶不在越界路径上** —— 是 `understand` 里重建 focus 时硬写了 `slots: {}`。
   那句已经单独修掉，并有独立回归测试（见本文件第 3 条）。
"""
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag

FACT_KEYS = ("locked_major", "locked_subcategory", "categories",
             "issues", "category_slots", "missing")


def _stub_plans(monkeypatch, plans):
    seq = [dict(p) for p in plans]
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **k: {
        "question": "这些杂物是一直堆着吗？", "target_slot": "persistence"})
    monkeypatch.setattr(ag, "_run_tool", lambda name, keyword, cancellation=None: "")
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)


def _turn(app, config, text):
    for _mode, _item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        pass
    return app.get_state(config).values


def _facts(values):
    return {key: values.get(key) for key in FACT_KEYS}


# ---------------------------------------------------------------- 1. 端到端：没依据的说法不留锁

# 第 1 轮：规划器声称这是"交通设施损坏"，但原文里既没有物件词（交通/标志/信号灯…）
# 也没有场所词（路/道/街/公共…）→ decide_scope 判 ambiguous
UNBACKED_PLAN = {
    "ok": True, "intent": "other", "risk_level": "low",
    "answer": "", "question": "", "needs_search": False,
    "perceived_major": "traffic",
    "issues": [{"major_code": "traffic", "subcategory_code": "traffic_facility_damage",
                "slots": {}}],
    "categories": ["traffic_facility_damage"],
    "category_slots": {"traffic_facility_damage": {}},
}


def test_unbacked_claim_does_not_leave_a_lock(monkeypatch):
    """一次"没有依据、拒答"的话，不该把会话锁在它上面。

    不撤销的话：锁会停在 `traffic_facility_damage`，用户接着问一个**别的**大类里的真隐患时，
    会被 `out_of_major` 当成越界挡掉 —— "一次拒答堵住后面所有问题"。
    """
    _stub_plans(monkeypatch, [UNBACKED_PLAN])
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "rollback-unbacked"}}

    values = _turn(app, config, "商场里的指示牌歪了")

    assert values.get("scope") == "ambiguous", values.get("scope")
    assert not values.get("locked_subcategory"), values.get("locked_subcategory")
    assert not values.get("locked_major"), values.get("locked_major")
    assert not values.get("categories")


# ---------------------------------------------------------------- 2. 单元：回滚机制本身

def test_scope_guard_rolls_back_facts_to_before_this_turn(monkeypatch):
    """直接钉住机制：越界时按快照回滚（不依赖 scope 判定能不能被真实输入触达）。"""
    monkeypatch.setattr(ag, "decide_scope", lambda *a, **k: {
        "scope": "out_of_scope", "reason": "stub", "response": "（越界模板）"})

    before = {"locked_major": "fire", "locked_subcategory": "fire_lane_blocked",
              "categories": ["fire_lane_blocked"],
              "issues": [{"subcategory_code": "fire_lane_blocked"}],
              "category_slots": {"fire_lane_blocked": {"blocker": "纸箱"}},
              "missing": ["fire_lane_blocked_persistence"]}
    state = {
        **{key: "本轮被改坏了" for key in FACT_KEYS},
        "facts_snapshot": dict(before),
        "dialogue_plan": {"ok": True, "issues": []},
        "messages": [HumanMessage(content="今天天气真好啊")],
        "session_id": "unit-rollback",
    }

    update = ag.scope_guard(state)

    assert update["scope"] == "out_of_scope"
    for key in FACT_KEYS:
        assert update[key] == before[key], key


def test_scope_guard_does_nothing_without_a_snapshot():
    """没有快照就不动 —— 宁可不动，也不要按空快照把事实抹掉。"""
    update = ag._facts_rollback({"locked_major": "fire"})
    assert update == {}


# ---------------------------------------------------------------- 3. 回归：规划器这轮不说话，槽位不能丢

SILENT_SECOND_PLAN = {
    "ok": True, "intent": "other", "risk_level": "low",
    "answer": "", "question": "", "needs_search": False,
    "scope": "out_of_scope",
    "issues": [], "categories": [], "category_slots": {},
}

FIRST_PLAN = {
    "ok": True, "intent": "other", "risk_level": "low",
    "answer": "", "question": "", "needs_search": False,
    "perceived_major": "fire",
    "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                "slots": {"blocker": "纸箱"}}],
    "categories": ["fire_lane_blocked"],
    "category_slots": {"fire_lane_blocked": {"blocker": "纸箱"}},
}


def test_planner_silent_turn_keeps_accumulated_slots(monkeypatch):
    """既有 bug 的回归：某一轮规划器不给该小类的 issue 时，已积累的槽位不能被清空。

    真凶是 `understand` 里重建 focus 时的 `slots: {}` —— 重建出来的空槽随即覆盖掉持久化的那份，
    用户会被重新问一遍已经答过的问题。
    """
    _stub_plans(monkeypatch, [FIRST_PLAN, SILENT_SECOND_PLAN])
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "rollback-slots"}}

    _turn(app, config, "楼道消防通道被纸箱占了")
    after = _turn(app, config, "今天天气真好啊")

    assert after["category_slots"].get("fire_lane_blocked") == {"blocker": "纸箱"}
    assert after["missing"] == ["fire_lane_blocked_persistence"]


def test_rollback_is_load_bearing(monkeypatch):
    """变异测试：把 `_facts_rollback` 换成空实现，锁就必须留下来。

    这条是防"假绿"的 —— 如果没有它，上面那条端到端用例可能只是因为"什么都没变"而通过。
    它证明回滚**真的在起作用**：是它把本轮建上的锁撤掉的。
    """
    _stub_plans(monkeypatch, [UNBACKED_PLAN])
    monkeypatch.setattr(ag, "_facts_rollback", lambda state: {})
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "rollback-mutation"}}

    values = _turn(app, config, "商场里的指示牌歪了")

    assert values.get("scope") == "ambiguous"
    assert values.get("locked_subcategory") == "traffic_facility_damage"
