# -*- coding: utf-8 -*-
"""检索自评重试环（evaluator-optimizer）。

三件事必须锁住：
  1. 判定是纯函数（联网/调模型都不在里面），触发原因是可读字符串；
  2. 环有上界：retrieval_attempts >= 1 后一律不触发；
  3. 不触发时不花任何额外模型调用，触发时最多一次。
"""
import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

import core.assistant_graph as ag

CASE_OK = (
    "=== 混合检索结果: 「消防通道占用 私家车」(语义3+关键词3) ===\n"
    "\n【结果1】[语义匹配] 小区消防通道被私家车占用\n  类别: 消防安全/消防通道占用"
    "\n【结果2】[语义匹配] 消防车通道被占用\n  类别: 消防安全/消防通道占用"
)
CASE_KEYWORD_ONLY = (
    "=== 混合检索结果: 「其他」(语义3+关键词3) ===\n"
    "\n【结果1】[关键词匹配] 某地杂物堵塞\n  类别: 消防安全/消防通道占用"
)
CASE_EMPTY = "[案例检索] 关键词=其他\n未找到与「其他」相关的结果。"
CASE_FAILURE = "[案例检索失败] Milvus 向量检索不可用：connection refused"
CASE_DEGRADED = "tb_hazard_case retrieval timeout（检索超时），暂未返回结果。"
CASE_OTHER_MAJOR = (
    "=== 混合检索结果: 「其他」(语义3+关键词3) ===\n"
    "\n【结果1】[语义匹配] 井盖破损\n  类别: 市政设施/井盖破损"
)


def _state(**over):
    state = {
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "私家车"}},
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked"}],
        "locked_major": "fire",
        "category_results": {"fire_lane_blocked": {"case": CASE_OK, "regulation": CASE_OK}},
    }
    state.update(over)
    return state


# ---------- 判定：纯函数 ----------

def test_no_retry_when_results_look_fine():
    assert ag.should_retry_retrieval(_state()) == (False, "")


def test_t1_ungrounded_slot_triggers():
    retry, reason = ag.should_retry_retrieval(
        _state(ungrounded_slots=["fire_lane_blocked.blocker=私家车乱停"]))
    assert retry is True
    assert reason.startswith("T1:")


def test_t2_out_of_major_results_trigger():
    retry, reason = ag.should_retry_retrieval(
        _state(category_results={"fire_lane_blocked": {"case": CASE_OTHER_MAJOR}}))
    assert retry is True
    assert reason.startswith("T2:")


def test_t3_empty_results_trigger():
    retry, reason = ag.should_retry_retrieval(
        _state(category_results={"fire_lane_blocked": {"case": CASE_EMPTY}}))
    assert retry is True
    assert reason == "T3:empty:fire_lane_blocked.case"


def test_t3_all_keyword_hits_trigger():
    """有结果块但一条语义命中都没有 → 向量分支没过门槛，算弱。"""
    retry, reason = ag.should_retry_retrieval(
        _state(category_results={"fire_lane_blocked": {"case": CASE_KEYWORD_ONLY}}))
    assert retry is True
    assert reason == "T3:no_semantic:fire_lane_blocked.case"


def test_t3_weak_score_triggers():
    retry, reason = ag.should_retry_retrieval(
        _state(retrieval_scores={"fire_lane_blocked": {"case": 0.52, "regulation": 0.52}}))
    assert retry is True
    assert reason.startswith("T3:weak_score:")
    assert "0.5200" in reason


def test_t3_strong_score_does_not_trigger():
    assert ag.should_retry_retrieval(
        _state(retrieval_scores={"fire_lane_blocked": {"case": 0.71, "regulation": 0.68}})
    ) == (False, "")


@pytest.mark.parametrize("text", [CASE_FAILURE, CASE_DEGRADED, "", "随便一段不是结果格式的文本"])
def test_failure_unknown_and_junk_texts_never_trigger(text):
    """检索本身失败不该重试（换词救不了）；判不出格式的文本更不该触发。"""
    assert ag.should_retry_retrieval(
        _state(category_results={"fire_lane_blocked": {"case": text, "regulation": text}})
    ) == (False, "")


def test_attempt_limit_vetoes_every_signal():
    """上界优先于一切：已经重试过就不再触发（哪怕是 T1+T2+T3 全中）。"""
    state = _state(
        retrieval_attempts=1,
        ungrounded_slots=["fire_lane_blocked.blocker=私家车乱停"],
        retrieval_scores={"fire_lane_blocked": {"case": 0.1}},
        category_results={"fire_lane_blocked": {"case": CASE_EMPTY}},
    )
    assert ag.should_retry_retrieval(state) == (False, "attempt_limit")


def test_disabled_switch_wins_over_everything(monkeypatch):
    monkeypatch.setattr(ag, "RETRY_ENABLED", False)
    assert ag.should_retry_retrieval(_state(ungrounded_slots=["x"])) == (False, "disabled")


@pytest.mark.parametrize("text,expected", [
    (CASE_OK, "ok"),
    (CASE_KEYWORD_ONLY, "weak"),
    (CASE_EMPTY, "empty"),
    (CASE_FAILURE, "failure"),
    (CASE_DEGRADED, "failure"),
    ("<tool_call>junk", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_retrieval_quality_classification(text, expected):
    assert ag.retrieval_quality(text) == expected


# ---------- 取分数：只在确实有结果块时才发探测 ----------

def test_collect_scores_skips_the_probe_without_result_blocks(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("不该在没有结果块时发起向量探测")

    monkeypatch.setattr(ag, "_probe_top1_score", forbidden)
    assert ag._collect_retrieval_scores(
        _state(category_results={"fire_lane_blocked": {"case": CASE_EMPTY}})) == {}
    assert ag._collect_retrieval_scores(
        _state(category_results={"fire_lane_blocked": {"case": "junk"}})) == {}


def test_collect_scores_probes_only_tables_with_blocks(monkeypatch):
    calls = []

    def fake_probe(keyword, table, cancellation=None):
        calls.append((keyword, table))
        return 0.64

    monkeypatch.setattr(ag, "_probe_top1_score", fake_probe)
    scores = ag._collect_retrieval_scores(
        _state(category_results={"fire_lane_blocked": {"case": CASE_OK, "regulation": ""}}))
    assert calls == [("消防通道占用 私家车", "tb_hazard_case")]
    assert scores == {"fire_lane_blocked": {"case": 0.64}}


def test_collect_scores_probes_both_tables(monkeypatch):
    def fake_probe(keyword, table, cancellation=None):
        return {"tb_hazard_case": 0.61, "tb_regulation": 0.66}[table]

    monkeypatch.setattr(ag, "_probe_top1_score", fake_probe)
    assert ag._collect_retrieval_scores(_state()) == {
        "fire_lane_blocked": {"case": 0.61, "regulation": 0.66}}


def test_two_probes_run_concurrently(monkeypatch):
    """两张表各 0.3s：串行要 0.6s，并发必须显著低于此。

    探测是一次 embedding+Milvus（实测单次 ~0.94s），串行取两次就是白等一次。
    """
    import time as _time

    def slow_probe(keyword, table, cancellation=None):
        _time.sleep(0.3)
        return 0.7

    monkeypatch.setattr(ag, "_probe_top1_score", slow_probe)
    started = _time.monotonic()
    scores = ag._collect_retrieval_scores(_state())
    elapsed = _time.monotonic() - started
    assert elapsed < 0.5, "探测看起来是串行的：%.2fs" % elapsed
    assert scores == {"fire_lane_blocked": {"case": 0.7, "regulation": 0.7}}


def test_score_probe_can_be_switched_off(monkeypatch):
    """关掉灰色带判定就不该再花 embedding：零额外成本的降级路径。"""
    monkeypatch.setattr(ag, "PROBE_TOP1_SCORE", False)

    def forbidden(*args, **kwargs):
        raise AssertionError("开关关掉后不该发探测")

    monkeypatch.setattr(ag, "_probe_top1_score", forbidden)
    assert ag._collect_retrieval_scores(_state()) == {}
    assert ag.evaluate_retrieval(_state()).goto == "report"


def test_probe_score_swallows_backend_errors(monkeypatch):
    """探针不能把检索故障变成图里的异常：拿不到分数就当“没有分数”。"""
    from tools import hybrid_search

    def broken(*args, **kwargs):
        raise RuntimeError("milvus down")

    monkeypatch.setattr(hybrid_search.searcher, "vector_search", broken)
    assert ag._probe_top1_score("消防通道", "tb_hazard_case") is None


def test_probe_score_is_zero_when_the_branch_returns_nothing(monkeypatch):
    from tools import hybrid_search

    monkeypatch.setattr(hybrid_search.searcher, "vector_search", lambda *a, **k: [])
    assert ag._probe_top1_score("其他", "tb_hazard_case") == 0.0


def test_probe_score_reads_match_score(monkeypatch):
    from tools import hybrid_search

    monkeypatch.setattr(hybrid_search.searcher, "vector_search",
                        lambda *a, **k: [{"id": 1, "match_score": 0.61}])
    assert ag._probe_top1_score("其他", "tb_hazard_case") == 0.61


# ---------- evaluate_retrieval 节点 ----------

def test_evaluate_retrieval_routes_to_report_when_fine(monkeypatch):
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: 0.72)
    command = ag.evaluate_retrieval(_state())
    assert isinstance(command, Command)
    assert command.goto == "report"
    assert command.update["retrieval_retry_reason"] == ""
    assert command.update["retrieval_scores"] == {"fire_lane_blocked": {"case": 0.72, "regulation": 0.72}}


def test_evaluate_retrieval_routes_to_rewrite_when_weak(monkeypatch):
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: 0.51)
    command = ag.evaluate_retrieval(_state())
    assert command.goto == "rewrite_query"
    assert command.update["retrieval_retry_reason"].startswith("T3:weak_score:")


def test_evaluate_retrieval_records_after_scores_on_the_retry_pass(monkeypatch):
    """重试跑完这一遍，把"重试后分数"补进日志 —— 触发前/触发后才有可能对照。"""
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)
    log = [{"category": "fire_lane_blocked", "reason": "T3:empty:fire_lane_blocked.case",
            "before_keyword": "其他", "after_keyword": "其他 小区 杂物", "before_scores": {}}]
    command = ag.evaluate_retrieval(_state(retrieval_attempts=1, retrieval_retry_log=log))
    assert command.goto == "report"
    entry = command.update["retrieval_retry_log"][-1]
    assert entry["after_scores"] == {}
    assert entry["before_keyword"] == "其他"


# ---------- rewrite_query 节点 ----------

def test_rewrite_query_swaps_the_keyword_without_touching_the_lock(monkeypatch):
    seen = {}

    def fake_call(messages, cancellation=None):
        seen["prompt"] = messages[0]["content"]
        return {"content": "其他 小区 杂物\n"}

    monkeypatch.setattr(ag._rewrite_llm, "_call_llm", fake_call)
    command = ag.rewrite_query(_state(
        categories=["other"], category_slots={"other": {"describe": "来源不明"}},
        retrieval_retry_reason="T3:empty:other.case",
        retrieval_scores={"other": {"case": 0.0}}))
    assert command.goto == "search"
    assert command.update["retrieval_keyword_override"] == {"other": "其他 小区 杂物"}
    assert command.update["retrieval_attempts"] == 1
    # 只重试检索：分类锁定不能被改写
    assert "locked_major" not in command.update
    assert "locked_subcategory" not in command.update
    assert "category_slots" not in command.update
    # 上一批分数作废，否则"重试后分数"会读到旧值
    assert command.update["retrieval_scores"] == {"other": None}
    entry = command.update["retrieval_retry_log"][-1]
    assert entry["before_keyword"] == "其他 来源不明"
    assert entry["after_keyword"] == "其他 小区 杂物"
    assert "T3" in entry["reason"]


def test_rewrite_query_falls_back_to_the_current_keyword_on_model_failure(monkeypatch):
    monkeypatch.setattr(ag._rewrite_llm, "_call_llm",
                        lambda messages, cancellation=None: {"content": "调用失败: timeout"})
    command = ag.rewrite_query(_state(categories=["other"],
                                      category_slots={"other": {"describe": "杂物"}}))
    assert command.update["retrieval_keyword_override"] == {"other": "其他 杂物"}
    assert command.update["retrieval_attempts"] == 1


@pytest.mark.parametrize("raw,expected", [
    ("消防通道 私家车", "消防通道 私家车"),
    ("  「消防通道 私家车」  ", "消防通道 私家车"),
    ("消防通道 私家车。这样更容易命中", "消防通道 私家车"),
    ("第一行\n第二行", "第一行"),
    ("消防通道   私家车", "消防通道 私家车"),
    ("", "兜底"),
    (None, "兜底"),
    ("一" * 60, "一" * 24),
])
def test_sanitize_keyword_keeps_the_tag_plus_value_shape(raw, expected):
    assert ag._sanitize_keyword(raw, "兜底") == expected


def test_plan_retrieval_prefers_the_rewritten_keyword():
    state = _state(retrieval_keyword_override={"fire_lane_blocked": "消防车通道 私家车 堵住"})
    sends = ag.plan_retrieval(state)
    assert sends and all(send.arg["keyword"] == "消防车通道 私家车 堵住" for send in sends)


# ---------- 图接线 ----------

def _plan():
    return {
        "ok": True, "intent": "report_hazard", "answer": "", "question": "",
        "needs_search": True, "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "私家车", "persistence": "长期"}, "missing": [],
        }],
        "categories": ["fire/fire_lane_blocked"],
        "category_slots": {"fire/fire_lane_blocked": {"blocker": "私家车", "persistence": "长期"}},
        "selected_major_code": "fire",
    }


def _run_graph(monkeypatch, retrieval_text):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(ag, "_run_tool",
                        lambda name, keyword, cancellation=None: retrieval_text)
    monkeypatch.setattr(ag, "_report_llm", type("Fake", (), {
        "_call_llm_stream_events": lambda self, messages, cancellation=None: iter([("chunk", "BODY")]),
    })())
    model_calls = []
    monkeypatch.setattr(ag._rewrite_llm, "_call_llm",
                        lambda messages, cancellation=None: (model_calls.append(messages),
                                                             {"content": "消防通道 私家车 占用"})[1])
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "retry-" + str(len(retrieval_text))}}
    nodes = []
    for mode, item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content="楼下消防通道长期被私家车占用，人都过不去")]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            nodes.extend(item.keys())
    return nodes, model_calls, app.get_state(config).values


def test_graph_runs_evaluate_retrieval_once_and_never_retries_when_fine(monkeypatch):
    nodes, model_calls, values = _run_graph(monkeypatch, CASE_OK)
    assert nodes.count("retrieve") == 2
    assert nodes.count("evaluate_retrieval") == 1     # 汇聚点之后只跑一次
    assert "rewrite_query" not in nodes
    assert model_calls == []                          # 不触发 = 零额外模型调用
    assert values["retrieval_attempts"] == 0
    assert "BODY" in values["draft_report"]


def test_graph_retries_once_then_reports_and_stops(monkeypatch):
    nodes, model_calls, values = _run_graph(monkeypatch, CASE_EMPTY)
    assert nodes.count("retrieve") == 4               # 第一次 2 条 + 重试 2 条
    assert nodes.count("evaluate_retrieval") == 2
    assert nodes.count("rewrite_query") == 1
    assert len(model_calls) == 1                      # 触发路径只多一次模型调用
    assert values["retrieval_attempts"] == 1          # 上界生效，不会第三次
    assert "BODY" in values["draft_report"]
    assert nodes.index("rewrite_query") < nodes.index("report")
    log = values["retrieval_retry_log"]
    assert log and log[-1]["reason"].startswith("T3:empty")
    assert "after_scores" in log[-1]        # 触发前 → 触发后 的对照已落进日志
    assert log[-1]["before_scores"] == {}
