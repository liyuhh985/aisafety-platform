"""户内/公共边界：只加一个字段 + 两句文案，不挡流程、不改分类。"""
import core.assistant_graph as ag
from core.dialogue_understanding import parse_plan
from langchain_core.messages import HumanMessage


def _plan(**over):
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "premises_scope": "public",
        "issues": [{"major_code": "utility", "subcategory_code": "gas_leak",
                    "slots": {"source": "管道"}}],
        "categories": ["gas_leak"],
        "category_slots": {"gas_leak": {"source": "管道"}},
        "question": "", "answer": "管道在漏气。", "needs_search": True,
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


def test_parser_defaults_to_public():
    plan = parse_plan('{"intent":"report_hazard","issues":[{"major_code":"utility",'
                      '"subcategory_code":"gas_leak","slots":{}}]}')
    assert plan["premises_scope"] == "public"


def test_parser_accepts_the_three_values():
    for value in ("public", "indoor", "indoor_risk"):
        plan = parse_plan('{"intent":"other","premises_scope":"%s","issues":[]}' % value)
        assert plan["premises_scope"] == value


def test_parser_rejects_an_unknown_value():
    plan = parse_plan('{"intent":"other","premises_scope":"kitchen","issues":[]}')
    assert plan["premises_scope"] == "public"


def test_indoor_scope_is_explained_in_the_reply(monkeypatch):
    out = _run(monkeypatch, "我家厨房燃气管道漏气", plan=_plan(premises_scope="indoor"))
    assert out["premises_scope"] == "indoor"
    assert any("户内" in c for c in out["_chunks"])


def test_public_scope_says_nothing(monkeypatch):
    out = _run(monkeypatch, "小区里的燃气管道漏气")
    assert out["premises_scope"] == "public"
    assert not any("户内" in c for c in out["_chunks"])


def test_the_indoor_line_is_not_repeated_every_turn(monkeypatch):
    first = _run(monkeypatch, "我家厨房燃气管道漏气", plan=_plan(premises_scope="indoor"))
    assert any("户内" in c for c in first["_chunks"])
    second = _run(monkeypatch, "已经打电话了", plan=_plan(premises_scope="indoor"),
                  premises_scope="indoor")
    assert not any("户内" in c for c in second["_chunks"])


def test_indoor_scope_does_not_change_classification_or_block_the_flow(monkeypatch):
    """户内不改变分类、也不挡流程。

    注意这个用例的输入与 fixture 在 2026-09-27 改过，原因值得记：
    原输入「我家厨房燃气管道漏气」是**危险句**，它当时能通过，是因为危险否决把
    ask_critical_question 降级成了 report_preliminary —— 也就是说**断言是被危险路径掩盖着的**。
    危险路径改走 emergency_guidance 之后，真实动作露出来了：ask_critical_question，
    因为 fixture 里 gas_leak 只填了 source、没填 describe（gas_leak 回落到「其他」槽位表）。

    所以这里补全槽位（describe 也填上），让"不挡流程"这条断言断言的是它本身，
    而不是靠危险否决兜出来的。
    """
    slots = {"leak_sign": "管道老化但暂未见泄漏", "ventilation": "户内通风一般"}
    plan = _plan(
        premises_scope="indoor",
        issues=[{"major_code": "utility", "subcategory_code": "gas_leak", "slots": slots}],
        category_slots={"gas_leak": dict(slots)},
    )
    out = _run(monkeypatch, "我家厨房的燃气管道老化了，外皮都脆了", plan=plan)
    assert out["categories"] == ["gas_leak"]
    assert out["locked_subcategory"] == "gas_leak"
    assert out["next_action"] in {"report_full", "report_preliminary"}


def test_task_invitation_carries_an_indoor_reminder():
    from core.assistant_graph import task_invitation_question
    public = task_invitation_question({"premises_scope": "public"})
    indoor = task_invitation_question({"premises_scope": "indoor"})
    assert public == "需要我帮你在系统建一条隐患任务吗？"
    assert "户内" in indoor and "建一条隐患任务" in indoor


def test_premises_scope_is_exposed_in_state():
    from core.langgraph_state import AssistantState
    assert "premises_scope" in AssistantState.__annotations__
