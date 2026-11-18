"""两处观感修正的锁定测试。

1. 危险路径不再挂那句通用话 —— 安全文本只有一个出处：emergency_guidance。
2. 初步报告不套小标题模板 —— 内容要求由代码保证，排版交给模型自然发挥。
"""
import core.assistant_graph as ag

GENERIC = "不要为了补全信息而停留"          # 那句通用话的特征片段
DANGER_FIRE = "楼道里全是浓烟，人都出不来"
DANGER_QUAKE = "地震了，房子一直在晃"


def _plan(code="fire_lane_blocked", major="fire", danger=False):
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "immediate_danger": danger,
        "issues": [{"major_code": major, "subcategory_code": code, "slots": {}}],
        "categories": [code], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    }


def _streamed(chunks):
    return "".join(str(c.get("chunk", "")) for c in chunks)


# ---------- 1. 危险路径不再有那句通用话 ----------
def test_danger_path_does_not_emit_the_generic_guidance_line(monkeypatch):
    chunks = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(danger=True))
    out = ag.understand({"messages": [ag.HumanMessage(content=DANGER_FIRE)]})
    assert out["danger_veto"] is True
    text = _streamed(chunks)
    assert GENERIC not in text
    assert ag.GUIDANCE_LINE not in text


def _run_guidance(monkeypatch, user_text, model_text):
    chunks = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", model_text)]),
    )
    update = ag.emergency_guidance({"messages": [ag.HumanMessage(content=user_text)]})
    return update["messages"][-1].content, _streamed(chunks)


def test_fire_guidance_has_no_generic_line_and_no_question(monkeypatch):
    model = ("请立刻低姿撤离到室外安全地带，用湿毛巾捂住口鼻，拨打 119 说明楼层和被困位置，"
             "不要为取回物品返回室内。")
    content, streamed = _run_guidance(monkeypatch, DANGER_FIRE, model)
    assert GENERIC not in content and ag.GUIDANCE_LINE not in content
    assert "119" in content
    assert "？" not in content and "?" not in content
    assert content == streamed                      # 缓冲后一次性流出，内容一致


def test_earthquake_falls_back_to_earthquake_wording_not_fire(monkeypatch):
    """模型漏掉要点时前置的兜底句必须是地震的 —— 原来是火灾用词那句通用话。"""
    content, _ = _run_guidance(monkeypatch, DANGER_QUAKE, "注意安全。")
    assert GENERIC not in content and ag.GUIDANCE_LINE not in content
    assert "空旷" in content or "室外" in content     # 地震兜底句才有的用词
    assert "低姿撤离" not in content                  # 火灾兜底句的用词不该出现
    assert "？" not in content


# ---------- 2. 初步报告不套小标题模板 ----------
def _state(mode="preliminary", missing_slots=("blocker",)):
    return {
        "messages": [],
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"persistence": "长期"}, "missing": list(missing_slots)}],
        "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {"regulation": "消防法第28条",
                                                   "case": "萍乡案例"}},
        "missing": ["fire_lane_blocked_" + s for s in missing_slots],
        "report_mode": mode,
    }


def _capture_report_prompt(monkeypatch, state):
    captured = {}

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", "BODY")

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    update = ag.report(state)
    return captured["prompt"], update


def test_preliminary_prompt_forbids_headings_and_keeps_three_contents(monkeypatch):
    prompt, _ = _capture_report_prompt(monkeypatch, _state())
    assert "###" not in prompt                       # 不再给三段式模板
    assert "初步判断" in prompt and "仍需确认" in prompt and "建议动作" in prompt
    assert "自然" in prompt
    assert "[仍缺信息]" in prompt                     # missing 确实进了提示词
    assert "被什么东西占用了？" in prompt


def test_preliminary_output_headings_are_stripped(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([
            ("chunk", "### 一、初步判断\n"),
            ("chunk", "楼下消防通道被杂物占了，这属于占用消防通道。\n"),
            ("chunk", "### 二、仍需确认\n"),
            ("chunk", "还需要知道被什么占用。"),
        ]),
    )
    draft = ag.report(_state())["draft_report"]
    assert "###" not in draft
    assert "楼下消防通道被杂物占了" in draft
    assert "还需要知道被什么占用" in draft


def test_full_report_keeps_the_three_section_structure(monkeypatch):
    prompt, _ = _capture_report_prompt(monkeypatch, _state(mode="full", missing_slots=()))
    assert "### 一、触犯法规" in prompt
    assert "自然、口语化" not in prompt                # 完整报告仍走三段式
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([
            ("chunk", "### 一、触犯法规\n消防法第28条。\n"),
            ("chunk", "### 二、安全隐患\n通道被占。\n"),
            ("chunk", "### 三、类似案例\n萍乡案例。"),
        ]),
    )
    draft = ag.report(_state(mode="full", missing_slots=()))["draft_report"]
    assert "### 一、触犯法规" in draft
    assert "### 三、类似案例" in draft
