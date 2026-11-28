"""报告分段：一条会话只有一个隐患，完整就三段式、不完整就初步式。"""
import core.assistant_graph as ag


def _state(**overrides):
    state = {
        "messages": [],
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"blocker": "杂物", "persistence": "长期"}, "missing": []}],
        "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {
            "regulation": "消防法第28条", "case": "萍乡案例"}},
        "missing": [],
        "report_mode": "full",
    }
    state.update(overrides)
    return state


def _incomplete(**overrides):
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"persistence": "长期"}, "missing": ["blocker"]}],
        missing=["fire_lane_blocked_blocker"],
        report_mode="preliminary",
    )
    state.update(overrides)
    return state


def _capture_prompt(monkeypatch, state):
    captured = {}

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", "BODY")

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        ag, "_append_supplemental_report",
        lambda state, body, dict_msgs, preliminary, cancellation: body,
    )
    ag.report(state)
    return captured["prompt"]


def _multi_issue_state():
    return _state(
        issues=[
            {"major_code": "fire", "subcategory_code": "ebike_hazard",
             "slots": {"hazard_mode": "楼梯间飞线充电", "charging_state": "正在充电"},
             "missing": []},
            {"major_code": "fire", "subcategory_code": "fire_lane_blocked",
             "slots": {"blocker": "飞线横跨楼梯口", "persistence": "长期"},
             "missing": []},
        ],
        categories=["ebike_hazard", "fire_lane_blocked"],
        category_results={
            "ebike_hazard": {"regulation": "高层民用建筑消防安全管理规定第37条", "case": "南京案例"},
            "fire_lane_blocked": {"regulation": "消防法第28条", "case": "萍乡案例"},
        },
    )


def test_missing_issue_entries_are_detected_without_raw_material_append():
    state = _multi_issue_state()
    body = "### 隐患2：消防通道占用\n\n现场事实和法规分析。"
    entries = ag._missing_report_issue_entries(state, body)
    assert [(index, issue["subcategory_code"]) for index, issue in entries] == [
        (1, "ebike_hazard")
    ]


def test_supplement_prompt_requests_natural_language_and_no_questions():
    state = _multi_issue_state()
    entries = ag._missing_report_issue_entries(
        state, "### 隐患2：消防通道占用\n\n现场事实。"
    )
    prompt = ag._supplemental_report_prompt(state, entries, preliminary=False)
    assert "请只补写" in prompt
    assert "电动自行车违规停放/充电" in prompt
    assert "不要输出内部方括号标签" in prompt
    assert "不要提问" in prompt


def test_report_requests_a_natural_language_supplement_for_missing_issue(monkeypatch):
    state = _multi_issue_state()
    responses = iter([
        "### 隐患2：消防通道占用\n\n现场事实和法规分析。",
        "### 隐患1：电动自行车违规停放/充电\n\n现场事实和法规分析。",
    ])
    calls = []

    def fake_stream(messages, cancellation=None):
        calls.append(messages[-1]["content"])
        yield ("chunk", next(responses))

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(ag, "can_offer_task_creation", lambda _state: False)
    update = ag.report(state)
    assert len(calls) == 2
    assert "请只补写" in calls[1]
    assert "### 隐患1：电动自行车违规停放/充电" in update["draft_report"]
    assert "### 隐患2：消防通道占用" in update["draft_report"]


def _block(prompt):
    return prompt.split("\n请逐个")[0].split("本次对话只跟踪这一个隐患")[0]


def test_a_complete_issue_is_marked_complete(monkeypatch):
    prompt = _capture_prompt(monkeypatch, _state())
    assert "（信息完整）" in prompt
    assert "[仍缺信息]" not in prompt
    assert "[待核实]" not in prompt


def test_missing_slot_questions_are_given_to_the_model(monkeypatch):
    """模型不该靠猜：缺的是"被什么东西占用了？"，代码里本来就有这个问句。"""
    prompt = _capture_prompt(monkeypatch, _incomplete())
    assert "（信息不完整）" in prompt
    assert "被什么东西占用了？" in prompt
    assert "[仍缺信息]" in prompt


def test_complete_issue_uses_the_three_section_template(monkeypatch):
    prompt = _capture_prompt(monkeypatch, _state())
    assert "触犯法规" in prompt and "类似案例" in prompt


def test_incomplete_issue_uses_the_preliminary_sections(monkeypatch):
    prompt = _capture_prompt(monkeypatch, _incomplete())
    assert "仍需确认" in prompt and "初步判断" in prompt


def test_rules_require_every_active_issue_and_state_the_count(monkeypatch):
    prompt = _capture_prompt(monkeypatch, _state())
    assert "本次对话共有 1 条活动隐患" in prompt
    assert "逐条覆盖全部隐患" in prompt
    assert "本次对话只跟踪这一个隐患" not in prompt


def test_report_prompt_contains_all_issue_blocks(monkeypatch):
    state = _state(
        issues=[
            {"major_code": "fire", "subcategory_code": "fire_lane_blocked",
             "slots": {"blocker": "杂物", "persistence": "长期"}, "missing": []},
            {"major_code": "building", "subcategory_code": "dangerous_building",
             "slots": {"structure": "墙体倾斜", "occupancy": "有人居住"}, "missing": []},
        ],
        categories=["fire_lane_blocked", "dangerous_building"],
        category_results={
            "fire_lane_blocked": {"regulation": "消防法第28条", "case": "萍乡案例"},
            "dangerous_building": {"regulation": "危房管理规定", "case": "危房案例"},
        },
    )
    prompt = _capture_prompt(monkeypatch, state)
    assert "本次对话共有 2 条活动隐患" in prompt
    assert "[隐患1] 消防通道占用" in prompt
    assert "[隐患2] 危房" in prompt
    assert "危房管理规定" in prompt
    assert "本次对话只跟踪这一个隐患" not in prompt


def test_an_invented_slot_makes_the_issue_incomplete(monkeypatch):
    """槽位填了但对不上用户原话 → 必须按"不完整"处理。"""
    state = _state()
    state["issues"][0]["slots"] = {"blocker": "消防通道"}
    state["issues"][0]["unverified"] = ["blocker=消防通道"]
    prompt = _capture_prompt(monkeypatch, state)
    assert "（信息不完整）" in prompt
    assert "[待核实]" in prompt
    assert "消防通道" in prompt


def test_understand_records_unverified_slots(monkeypatch):
    """填了、既不是回声、也在原话里找不到依据 → 记为待核实。

    注意选值：写成"消防通道"会被判成回声（它是自己类别名"消防通道占用"的子串），
    那走的是"清掉→落回 missing"这条路，不会进 unverified。
    """
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"blocker": "施工围挡", "persistence": "长期"}}],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "施工围挡",
                                                "persistence": "长期"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [ag.HumanMessage(content="楼下消防通道的问题，长期这样")]})
    assert out["issues"][0]["unverified"] == ["blocker=施工围挡"]
    assert out["uncertainty_level"] == "cautious"
    assert out["locked_subcategory"] == "fire_lane_blocked"
