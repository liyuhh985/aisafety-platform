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


def test_a_mid_conversation_frontend_change_is_ignored(monkeypatch):
    """大类集合一旦锁定就**硬锁**：前端中途改选也不生效，只能新开一个对话。

    2026-10-14 决策：会话内禁止改大类（前端选择器上锁），后端也跟着锁 —— 否则绕过
    UI 就能改。代价是 10/13 那版前端的「改报」按钮点了不再会生效。
    """
    plan = _plan(issues=[{"major_code": "municipal", "subcategory_code": "manhole_damage",
                          "slots": {}}],
                 categories=["manhole_damage"], category_slots={"manhole_damage": {}})
    out = _run(monkeypatch, "楼下井盖破了", plan=plan,
               selected_major_code="municipal",
               locked_major="fire", locked_majors=["fire"],
               locked_subcategory="fire_lane_blocked")
    assert out["locked_majors"] == ["fire"]
    assert out["locked_major"] == "fire"
    assert out["locked_subcategory"] == "fire_lane_blocked"
    assert [i["subcategory_code"] for i in out["issues"]] == ["fire_lane_blocked"]
    # 不静默：模型认为这是市政的事，就照常发那句越界通知
    assert any("市政设施" in c for c in _notice(out))


def test_two_in_major_hazards_are_both_recorded(monkeypatch):
    "同一大类里的两件事都要记下 —— 只留一条等于把第二件事静默丢掉。"
    plan = _plan(issues=[
        {"major_code": "fire", "subcategory_code": "fire_lane_blocked", "slots": {}},
        {"major_code": "fire", "subcategory_code": "fire_equipment_fault", "slots": {}},
    ], categories=["fire_lane_blocked", "fire_equipment_fault"])
    out = _run(monkeypatch, "消防通道被堵，消火栓也坏了", plan=plan)
    assert [i["subcategory_code"] for i in out["issues"]] == [
        "fire_lane_blocked", "fire_equipment_fault"]
    assert out["categories"] == ["fire_lane_blocked", "fire_equipment_fault"]


def test_active_hazards_are_capped(monkeypatch):
    "上界是 MAX_ACTIVE_HAZARDS：并列追问一句最多几条，多出来的丢在这里。"
    plan = _plan(issues=[
        {"major_code": "building", "subcategory_code": "dangerous_building", "slots": {}},
        {"major_code": "building", "subcategory_code": "wall_crack_lean", "slots": {}},
        {"major_code": "building", "subcategory_code": "facade_fall", "slots": {}},
        {"major_code": "building", "subcategory_code": "falling_object", "slots": {}},
    ], categories=["dangerous_building", "wall_crack_lean", "facade_fall", "falling_object"])
    out = _run(monkeypatch, "危房、墙体开裂、外立面脱落、还有东西往下掉", plan=plan)
    assert len(out["issues"]) == ag.MAX_ACTIVE_HAZARDS == 3


def test_a_cross_major_second_hazard_is_still_not_recorded(monkeypatch):
    "跨大类的第二件事仍然只发通知、不进活动集 —— 一张工单只有一个类别。"
    plan = _plan(issues=[
        {"major_code": "municipal", "subcategory_code": "manhole_damage", "slots": {}},
        {"major_code": "fire", "subcategory_code": "fire_lane_blocked", "slots": {}},
    ], categories=["manhole_damage", "fire_lane_blocked"])
    out = _run(monkeypatch, "楼下井盖破了，旁边消防通道也被堵了", plan=plan,
               selected_major_code="municipal")
    assert [i["subcategory_code"] for i in out["issues"]] == ["manhole_damage"]
    assert out["locked_major"] == "municipal"


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


def test_frontend_multi_select_locks_every_picked_major(monkeypatch):
    """前端多选大类：一条消息里两个大类各一件，两条都跟着走。

    多选的传法就是把几个 code 用逗号拼进原来那个 `selected_major_code`，
    所以 Java 那一层一个字都不用改。
    """
    plan = _plan(issues=[
        {"major_code": "municipal", "subcategory_code": "manhole_damage", "slots": {}},
        {"major_code": "fire", "subcategory_code": "fire_equipment_fault", "slots": {}},
    ], categories=["manhole_damage", "fire_equipment_fault"], perceived_major="municipal")
    out = _run(monkeypatch, "楼下井盖破了，旁边的消火栓也坏了", plan=plan,
               selected_major_code="fire,municipal")
    assert out["locked_majors"] == ["fire", "municipal"]
    assert out["locked_major"] == "fire"
    assert [i["subcategory_code"] for i in out["issues"]] == [
        "manhole_damage", "fire_equipment_fault"]
    assert _notice(out) == []


def test_auto_mode_locks_every_major_said_in_the_first_sentence(monkeypatch):
    """前端没选（默认自动）：这一句话涉及几个大类就锁几个，两条都跟。"""
    plan = _plan(issues=[
        {"major_code": "municipal", "subcategory_code": "manhole_damage", "slots": {}},
        {"major_code": "fire", "subcategory_code": "fire_lane_blocked", "slots": {}},
    ], categories=["manhole_damage", "fire_lane_blocked"], perceived_major="municipal")
    out = _run(monkeypatch, "楼下井盖破了，旁边消防通道也被堵了", plan=plan)
    assert out["locked_majors"] == ["municipal", "fire"]
    assert [i["subcategory_code"] for i in out["issues"]] == [
        "manhole_damage", "fire_lane_blocked"]
    assert _notice(out) == []


def test_auto_route_does_not_persist_planner_major_as_frontend_hint(monkeypatch):
    """自动路由时，模型建议不能写回成下一轮的前端预选大类。

    否则首轮自动识别 fire + traffic 后，第二轮会把 fire 当成用户明确预选，
    并把 traffic 误判成 major_mismatch，最终把完整报告降级成初步报告。
    """
    plan = _plan(
        selected_major_code="fire",
        major_mismatch=True,
        perceived_major="fire",
        issues=[
            {"major_code": "fire", "subcategory_code": "fire_lane_blocked",
             "slots": {"blocker": "私家车", "persistence": "长期"}},
            {"major_code": "traffic", "subcategory_code": "blind_path_occupied",
             "slots": {"behavior": "共享单车"}},
        ],
        categories=["fire_lane_blocked", "blind_path_occupied"],
        category_slots={
            "fire_lane_blocked": {"blocker": "私家车", "persistence": "长期"},
            "blind_path_occupied": {"behavior": "共享单车"},
        },
    )
    out = _run(monkeypatch, "消防通道长期被私家车占用，旁边盲道被共享单车占了", plan=plan)
    assert out["locked_majors"] == ["fire", "traffic"]
    assert out["selected_major_code"] == ""
    assert out["major_mismatch"] is False
    assert out["uncertainty_level"] == "ok"


def test_real_frontend_major_mismatch_is_still_reported(monkeypatch):
    plan = _plan(
        selected_major_code="municipal",
        major_mismatch=True,
        perceived_major="fire",
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车", "persistence": "长期"}}],
        categories=["fire_lane_blocked"],
        category_slots={
            "fire_lane_blocked": {"blocker": "私家车", "persistence": "长期"},
        },
    )
    out = _run(
        monkeypatch, "消防通道长期被私家车占用", plan=plan,
        selected_major_code="municipal",
    )
    assert out["selected_major_code"] == "municipal"
    assert out["major_mismatch"] is True


def test_picked_majors_are_a_range_not_a_quota(monkeypatch):
    """前端选了两个大类，但这句话只讲了一件 —— 只记这一条，不按大类数硬凑。"""
    plan = _plan(issues=[{"major_code": "municipal", "subcategory_code": "manhole_damage",
                          "slots": {}}],
                 categories=["manhole_damage"], perceived_major="municipal")
    out = _run(monkeypatch, "楼下井盖破了", plan=plan,
               selected_major_code="fire,municipal")
    assert out["locked_majors"] == ["fire", "municipal"]
    assert [i["subcategory_code"] for i in out["issues"]] == ["manhole_damage"]
    assert _notice(out) == []


def test_a_later_new_major_does_not_join_the_lock(monkeypatch):
    """锁定之后，模型说别的大类也加不进来 —— 只发通知。"""
    plan = _plan(issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                          "slots": {}}],
                 categories=["fire_lane_blocked"], perceived_major="fire")
    out = _run(monkeypatch, "另外还发现消防通道被堵了", plan=plan,
               locked_major="municipal", locked_subcategory="manhole_damage",
               category_slots={"manhole_damage": {}})
    assert out["locked_majors"] == ["municipal"]
    assert out["locked_major"] == "municipal"
    assert [i["subcategory_code"] for i in out["issues"]] == ["manhole_damage"]
    assert any("市政设施" in c for c in _notice(out))


def test_a_correction_cannot_add_a_major(monkeypatch):
    """用户口头纠正也动不了大类集合 —— 大类只由前端改，纠正只能换同大类里的小类。"""
    plan = _plan(intent="correction", issues=[
        {"major_code": "fire", "subcategory_code": "fire_lane_blocked", "slots": {}}],
        categories=["fire_lane_blocked"], perceived_major="fire")
    out = _run(monkeypatch, "其实不是井盖，是消防通道被堵了", plan=plan,
               locked_major="municipal", locked_subcategory="manhole_damage",
               category_slots={"manhole_damage": {}})
    assert out["locked_majors"] == ["municipal"]
    assert out["locked_subcategory"] == "manhole_damage"
    assert any("消防安全" in c for c in _notice(out))


def test_the_notice_names_every_locked_major(monkeypatch):
    """锁了两个大类时，越界通知要把范围说全，不能只说第一个。"""
    plan = _plan(issues=[{"major_code": "traffic", "subcategory_code": "road_occupancy",
                          "slots": {}}],
                 categories=["road_occupancy"], perceived_major="traffic")
    out = _run(monkeypatch, "路边还长期摆摊", plan=plan,
               locked_major="municipal", locked_majors=["municipal", "fire"],
               locked_subcategory="manhole_damage",
               category_slots={"manhole_damage": {}})
    notices = _notice(out)
    assert notices
    assert "市政设施" in notices[0] and "消防安全" in notices[0]


def test_the_model_declared_focus_beats_the_issue_order(monkeypatch):
    """模型把历史里那件也一起报上来、且排在前面时，锁不能被它拉回去。

    焦点听 perceived_subcategory（「这句话指的是哪一件」），不听 issues 的顺序 ——
    顺序会被"把当前仍有效的问题一起报上来"这条契约污染。
    """
    plan = _plan(intent="correction", perceived_major="municipal",
                 perceived_subcategory="street_light_pole",
                 issues=[
                     {"major_code": "municipal", "subcategory_code": "manhole_damage", "slots": {}},
                     {"major_code": "municipal", "subcategory_code": "street_light_pole", "slots": {}},
                 ], categories=["manhole_damage", "street_light_pole"])
    out = _run(monkeypatch, "不是井盖，是旁边那根路灯杆歪了", plan=plan,
               locked_major="municipal", locked_subcategory="manhole_damage",
               category_slots={"manhole_damage": {}})
    assert out["locked_subcategory"] == "street_light_pole"
    assert [i["subcategory_code"] for i in out["issues"]] == [
        "street_light_pole", "manhole_damage"]


def test_the_focus_is_inherited_when_the_model_just_reorders(monkeypatch):
    """不是纠正时，模型换个顺序也动不了锁 —— 焦点默认继承。"""
    plan = _plan(perceived_major="municipal", perceived_subcategory="street_light_pole",
                 issues=[
                     {"major_code": "municipal", "subcategory_code": "manhole_damage", "slots": {}},
                     {"major_code": "municipal", "subcategory_code": "street_light_pole", "slots": {}},
                 ], categories=["manhole_damage", "street_light_pole"])
    out = _run(monkeypatch, "旁边那根路灯杆也歪了", plan=plan,
               locked_major="municipal", locked_subcategory="manhole_damage",
               category_slots={"manhole_damage": {}})
    assert out["locked_subcategory"] == "manhole_damage"
    assert [i["subcategory_code"] for i in out["issues"]] == [
        "manhole_damage", "street_light_pole"]


def test_a_focus_outside_the_active_set_falls_back_to_the_first(monkeypatch):
    """模型说的焦点不在本轮条目里（跑出集合或没这条）→ 退回第一条，不硬造。"""
    plan = _plan(intent="correction", perceived_major="municipal",
                 perceived_subcategory="gas_leak",
                 issues=[{"major_code": "municipal", "subcategory_code": "street_light_pole",
                          "slots": {}}],
                 categories=["street_light_pole"])
    out = _run(monkeypatch, "不是井盖，是旁边那根路灯杆歪了", plan=plan,
               locked_major="municipal", locked_subcategory="manhole_damage",
               category_slots={"manhole_damage": {}})
    assert out["locked_subcategory"] == "street_light_pole"


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
