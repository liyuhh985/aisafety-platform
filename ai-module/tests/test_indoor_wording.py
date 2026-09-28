"""户内场景的措辞：标题不能预设"有人违法"，检索要偏义务，燃气要有对口避险动作。"""
import core.assistant_graph as ag
from core.scope_policy import covers_emergency_points, emergency_guidance_fallback
from tests.reply_helpers import (collect_chunks, fake_report_model, run_turn,
                                streamed_text)


def _state(**over):
    state = {
        "messages": [],
        "issues": [{"major_code": "utility", "subcategory_code": "gas_leak",
                    "slots": {"source": "管道"}, "missing": []}],
        "categories": ["gas_leak"],
        "category_results": {"gas_leak": {"regulation": "燃气条例", "case": "案例"}},
        "missing": [],
        "report_mode": "full",
        "premises_scope": "public",
    }
    state.update(over)
    return state


def _prompt(monkeypatch, state):
    captured = {}

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", "BODY")

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    ag.report(state)
    return captured["prompt"]


def test_public_report_keeps_the_violation_heading(monkeypatch):
    prompt = _prompt(monkeypatch, _state())
    assert "触犯法规" in prompt
    assert "相关法规与责任归属" not in prompt


def test_indoor_report_replaces_the_violation_heading(monkeypatch):
    prompt = _prompt(monkeypatch, _state(premises_scope="indoor"))
    assert "相关法规与责任归属" in prompt
    assert "触犯法规" not in prompt


def test_indoor_risk_report_uses_the_same_replacement(monkeypatch):
    prompt = _prompt(monkeypatch, _state(premises_scope="indoor_risk"))
    assert "相关法规与责任归属" in prompt
    assert "触犯法规" not in prompt


def test_indoor_report_keeps_the_other_sections(monkeypatch):
    prompt = _prompt(monkeypatch, _state(premises_scope="indoor"))
    assert "安全隐患" in prompt and "类似案例" in prompt


def test_indoor_report_tells_the_model_not_to_frame_the_user_as_offending(monkeypatch):
    prompt = _prompt(monkeypatch, _state(premises_scope="indoor"))
    assert "不要" in prompt and "违法" in prompt


def test_public_keyword_is_unchanged():
    assert ag._pick_keyword("gas_leak", {"source": "管道"}) == \
        ag._pick_keyword("gas_leak", {"source": "管道"}, "public")


def test_indoor_keyword_leans_towards_obligation():
    keyword = ag._pick_keyword("gas_leak", {"source": "管道"}, "indoor")
    assert "维护" in keyword or "责任" in keyword or "义务" in keyword


def test_indoor_keyword_still_names_the_hazard():
    keyword = ag._pick_keyword("gas_leak", {"source": "管道"}, "indoor")
    assert "燃气" in keyword


def test_plan_retrieval_passes_the_scope_into_the_keyword():
    state = {"categories": ["gas_leak"], "category_slots": {"gas_leak": {"source": "管道"}},
             "premises_scope": "indoor"}
    keyword = ag.plan_retrieval(state)[0].arg["keyword"]
    assert "维护" in keyword or "责任" in keyword or "义务" in keyword


def test_gas_danger_gets_gas_specific_guidance():
    line = ag.guidance_line("我家厨房燃气管道漏气，味道很大")
    assert "关" in line
    assert "燃气公司" in line
    assert "电器" in line


def test_other_danger_keeps_the_generic_guidance():
    line = ag.guidance_line("楼道里全是浓烟，人都出不来")
    assert "119" in line
    assert "燃气公司" not in line


def test_gas_danger_gets_gas_specific_safety_text(monkeypatch):
    """燃气危险要有关阀/开窗/电器那几句 —— 出处是 emergency_guidance（不再是 understand）。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "utility", "subcategory_code": "gas_leak",
                    "slots": {"source": "管道"}}],
        "categories": ["gas_leak"], "category_slots": {"gas_leak": {"source": "管道"}},
        "question": "", "answer": "", "needs_search": True,
    })
    chunks = collect_chunks(monkeypatch)
    fake_report_model(monkeypatch, "请尽快处理，注意安全。")   # 模型没覆盖要点 → 代码补该类型的兜底句
    nodes, answer, _values = run_turn(
        ag.build_graph(), {"configurable": {"thread_id": "emg-gas"}},
        "我家厨房燃气管道漏气，味道很大")
    assert "emergency_guidance" in nodes
    assert "燃气公司" in answer
    assert covers_emergency_points(answer, "gas")
    # 真正流给前端的就是节点产出的那段（含燃气兜底句），不是别的节点发的
    assert streamed_text(chunks).startswith(emergency_guidance_fallback("gas"))
