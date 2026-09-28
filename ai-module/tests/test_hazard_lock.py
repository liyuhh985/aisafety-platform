"""一条会话一个活跃隐患：首次上锁 / 类内匹配 / 纠正改锁 / 越界拒绝。"""
import core.assistant_graph as ag
from langchain_core.messages import HumanMessage


def _plan(**over):
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"blocker": "杂物", "persistence": "长期"}}],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物", "persistence": "长期"}},
        "question": "", "answer": "", "needs_search": True, "major_mismatch": False,
    }
    plan.update(over)
    return plan


def _run(monkeypatch, text, plan=None, **state):
    chunks = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan or _plan()))
    out = ag.understand({"messages": [HumanMessage(content=text)], **state})
    out["_chunks"] = [str(c.get("chunk", "")) for c in chunks]
    return out


def _notice(out):
    return [c for c in out["_chunks"] if "本次对话记录的是" in c or "更像是" in c]


def test_first_turn_with_a_category_locks_major_and_subcategory(monkeypatch):
    out = _run(monkeypatch, "消防通道被杂物长期堵住")
    assert out["locked_major"] == "fire"
    assert out["locked_subcategory"] == "fire_lane_blocked"
    assert _notice(out) == []


def test_turn_without_a_category_locks_nothing(monkeypatch):
    out = _run(monkeypatch, "我这边有个情况", plan=_plan(issues=[], categories=[],
                                                        category_slots={}, needs_search=False))
    assert out["locked_major"] == ""
    assert out["locked_subcategory"] == ""


def test_out_of_major_is_detected_from_the_planners_major(monkeypatch):
    """规划器判成别的类：不大类不变、小类留空、通知点出那个大类名。"""
    plan = _plan(issues=[{"major_code": "municipal", "subcategory_code": "manhole_damage",
                          "slots": {}}],
                 categories=["manhole_damage"], category_slots={"manhole_damage": {}})
    out = _run(monkeypatch, "楼下井盖破了", plan=plan,
               selected_major_code="fire", locked_major="fire")
    assert out["locked_major"] == "fire"
    assert out["locked_subcategory"] == ""
    assert any("市政设施" in c for c in _notice(out))


def test_unclassifiable_message_asks_inside_the_major(monkeypatch):
    """规划器给不出类别（也没有越界证据）时：大类保持、小类留空、问类内问句。"""
    out = _run(monkeypatch, "楼道里的东西坏了",
               plan=_plan(intent="other", issues=[], categories=[], category_slots={},
                          needs_search=False),
               selected_major_code="fire", locked_major="fire")
    assert out["locked_subcategory"] == ""
    assert out["next_action"] == "ask_critical_question"
    question = out["clarification_question"]
    assert "消防" in question
    assert "消防通道占用" in question or "消防设施故障" in question
    assert _notice(out) == []


def test_in_major_match_locks_silently(monkeypatch):
    out = _run(monkeypatch, "消防通道被杂物长期堵住", selected_major_code="fire")
    assert out["locked_subcategory"] == "fire_lane_blocked"
    assert _notice(out) == []
    assert out["clarification_question"] == ""


def test_correction_inside_the_major_relocks(monkeypatch):
    plan = _plan(intent="correction",
                 issues=[{"major_code": "fire", "subcategory_code": "fire_equipment_fault",
                          "slots": {"condition": "漏水"}}],
                 categories=["fire_equipment_fault"],
                 category_slots={"fire_equipment_fault": {"condition": "漏水"}})
    out = _run(monkeypatch, "其实是消防设施坏了，消火栓在漏水", plan=plan,
               selected_major_code="fire", locked_major="fire",
               locked_subcategory="fire_lane_blocked",
               category_slots={"fire_lane_blocked": {"blocker": "杂物"}})
    assert out["locked_subcategory"] == "fire_equipment_fault"
    assert out["categories"] == ["fire_equipment_fault"]
    assert _notice(out) == []
    # 旧类别的槽位惰性保留，不会被读成新类别的槽位
    assert out["category_slots"]["fire_lane_blocked"] == {"blocker": "杂物"}


def test_correction_outside_the_major_is_refused(monkeypatch):
    plan = _plan(intent="correction",
                 issues=[{"major_code": "building", "subcategory_code": "dangerous_building",
                          "slots": {}}],
                 categories=["dangerous_building"],
                 category_slots={"dangerous_building": {}})
    out = _run(monkeypatch, "其实不是消防，是危房", plan=plan,
               selected_major_code="fire", locked_major="fire",
               locked_subcategory="fire_lane_blocked")
    assert out["locked_major"] == "fire"
    assert out["locked_subcategory"] == "fire_lane_blocked"
    assert _notice(out)


def test_frontend_major_change_relocks(monkeypatch):
    """B 方案：前端中途改选大类 → 后端重新上锁。"""
    out = _run(monkeypatch, "楼下井盖破了",
               plan=_plan(issues=[{"major_code": "municipal",
                                   "subcategory_code": "manhole_damage", "slots": {}}],
                          categories=["manhole_damage"],
                          category_slots={"manhole_damage": {}}),
               selected_major_code="municipal", locked_major="fire",
               locked_subcategory="fire_lane_blocked")
    assert out["locked_major"] == "municipal"
    assert out["locked_subcategory"] == "manhole_damage"
    assert _notice(out) == []


def test_issues_never_exceed_one(monkeypatch):
    plan = _plan(issues=[
        {"major_code": "fire", "subcategory_code": "fire_lane_blocked", "slots": {}},
        {"major_code": "fire", "subcategory_code": "fire_equipment_fault", "slots": {}},
    ], categories=["fire_lane_blocked", "fire_equipment_fault"])
    out = _run(monkeypatch, "消防通道被堵，消火栓也坏了", plan=plan)
    assert len(out["issues"]) == 1


def test_notice_is_never_a_question(monkeypatch):
    plan = _plan(issues=[{"major_code": "municipal", "subcategory_code": "manhole_damage",
                          "slots": {}}],
                 categories=["manhole_damage"], category_slots={"manhole_damage": {}})
    out = _run(monkeypatch, "楼下井盖破了", plan=plan,
               selected_major_code="fire", locked_major="fire")
    notices = _notice(out)
    assert notices, "这一支必须真的出通知，否则这条测试是空转"
    for chunk in notices:
        assert "？" not in chunk and "?" not in chunk


def test_danger_is_no_longer_inherited_from_an_earlier_turn(monkeypatch):
    """A 方案：代码不再比较话题延续危险，只看本轮原话 + 模型标志。"""
    out = _run(monkeypatch, "我该怎么跑", locked_major="fire",
               locked_subcategory="fire_lane_blocked", danger_veto=True)
    assert out["danger_veto"] is False


def test_model_flagged_danger_still_vetoes(monkeypatch):
    out = _run(monkeypatch, "我该怎么跑", plan=_plan(immediate_danger=True, issues=[],
                                                   categories=[], category_slots={},
                                                   needs_search=False))
    assert out["danger_veto"] is True


def test_state_exposes_the_lock_fields():
    from core.langgraph_state import AssistantState
    assert "locked_major" in AssistantState.__annotations__
    assert "locked_subcategory" in AssistantState.__annotations__


def test_perceived_major_drives_the_out_of_major_check(monkeypatch):
    """模型配合前端提示把 issues 写成 fire，但 perceived_major 说了真话。"""
    plan = _plan(perceived_major="municipal",
                 issues=[{"major_code": "fire", "subcategory_code": "fire_equipment_fault",
                          "slots": {}}],
                 categories=["fire_equipment_fault"],
                 category_slots={"fire_equipment_fault": {}})
    out = _run(monkeypatch, "楼下井盖破了", plan=plan,
               selected_major_code="fire", locked_major="fire")
    assert out["suggested_major_code"] == "municipal"
    assert out["locked_subcategory"] == ""
    assert any("市政设施" in c for c in _notice(out))
