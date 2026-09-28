"""阶段 4：B 类（报告级）缺失要写成「若…则…」的条件分支，不是省略、也不是空话。

三类缺失的分工（core/slot_schemas.py 的 A/B/C）：
  A 决策级 -> 追问，材料里走 [仍缺信息]
  B 报告级 -> 不追问，材料里走 [法规适用待确认]，报告要分情况判断
  C 装饰级 -> 不追问，也不进材料
"""
import logging

import core.assistant_graph as ag


def _state(**overrides):
    state = {
        "messages": [],
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"blocker": "私家车", "persistence": "长期"},
                    "missing": [], "report_missing": ["impact"]}],
        "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {
            "regulation": "消防法第28条", "case": "萍乡案例"}},
        "missing": [],
        "report_mode": "full",
    }
    state.update(overrides)
    return state


def _capture(monkeypatch, state, reply="BODY"):
    captured = {}

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", reply)

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    update = ag.report(state)
    return captured["prompt"], update


def _line(prompt, label):
    hits = [ln for ln in prompt.splitlines() if ln.startswith(label)]
    assert hits, "material is missing the %s line" % label
    return hits[0]


def _has_branch(text):
    """「若…则…」类分支表达：至少两个分情况，或若+则配对出现。"""
    return str(text).count("若") >= 2 or ("若" in str(text) and "则" in str(text))


# ---------- ① report_missing 进材料 ----------

def test_b_class_missing_enters_the_material_with_its_question(monkeypatch):
    """完整报告（A 类齐、只缺 impact(B)）：材料里要有 B 行 + 它自带的问句作为线索。"""
    prompt, _ = _capture(monkeypatch, _state())
    assert "（信息完整）" in prompt
    assert "[法规适用待确认]" in prompt
    assert "是否影响消防车或人员通行？" in prompt
    assert "[仍缺信息]" not in prompt          # A 类已齐，不该出现那一行


def test_a_and_b_missing_use_separate_lines_without_duplication(monkeypatch):
    """只缺 persistence(A) 与 impact(B)：A 走 [仍缺信息]，B 走 [法规适用待确认]，不重复。"""
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}, "missing": ["persistence"],
                 "report_missing": ["persistence", "impact"]}],
        missing=["fire_lane_blocked_persistence"],
        report_mode="preliminary",
    )
    prompt, _ = _capture(monkeypatch, state)
    a_line = _line(prompt, "[仍缺信息]")
    b_line = _line(prompt, "[法规适用待确认]")
    assert "是长期还是临时？" in a_line
    assert "是否影响消防车或人员通行？" in b_line
    assert "是长期还是临时？" not in b_line     # A 类那一项不在 B 行里重复
    assert "是否影响消防车或人员通行？" not in a_line


def test_report_branch_keys_is_only_b_class():
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}, "missing": ["persistence"],
                 "report_missing": ["persistence", "impact"]}],
    )
    assert ag.report_branch_keys(state) == ["impact"]


def test_c_class_missing_is_not_written_as_a_branch(monkeypatch):
    """C 类（装饰级）既不追问，也不进报告材料 —— 否则报告又长又绕。"""
    # dangerous_building: structure(A) / occupancy(A) / risk(C)
    assert ag.rebuild_report_missing(
        ["dangerous_building"],
        {"dangerous_building": {"structure": "有裂缝", "occupancy": "有人居住"}}) == []
    state = _state(
        issues=[{"major_code": "building", "subcategory_code": "dangerous_building",
                 "slots": {"structure": "有裂缝", "occupancy": "有人居住"},
                 "missing": [], "report_missing": []}],
        categories=["dangerous_building"],
        category_results={"dangerous_building": {
            "regulation": "危房鉴定标准", "case": "某案例"}},
    )
    assert ag.report_branch_keys(state) == []
    prompt, _ = _capture(monkeypatch, state)
    assert "[法规适用待确认]" not in prompt
    assert "即时坍塌风险" not in prompt


def test_branch_rule_is_not_injected_when_nothing_is_pending(monkeypatch):
    """没有 B 类缺失时，规则里不该出现分支要求 —— 否则模型会以为还有信息没确认。"""
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车", "persistence": "长期", "impact": "影响通行"},
                 "missing": [], "report_missing": []}],
    )
    prompt, _ = _capture(monkeypatch, state)
    assert "若…则…" not in prompt
    assert "[法规适用待确认]" not in prompt


# ---------- ② 提示词要求写成分情况判断 ----------

def test_rules_ask_for_a_conditional_branch_and_ban_empty_talk(monkeypatch):
    prompt, _ = _capture(monkeypatch, _state())
    assert "若…则…" in prompt
    assert "建议进一步核实" in prompt          # 明示的禁止写法（作为反例出现在规则里）
    assert "分情况判断" in prompt


# ---------- ③ 空话检测：只告警，不改写 ----------

def test_branch_wording_is_delivered_and_not_flagged(monkeypatch):
    reply = ("是否影响通行还没有确认：若完全堵死，适用《消防法》第60条第1款第3项，可责令改正并处罚款；"
             "若只是部分占用，则以责令限期整改为主。")
    _, update = _capture(monkeypatch, _state(), reply=reply)
    body = update["draft_report"]
    assert _has_branch(body)
    assert ag.empty_talk_hits(body) == []


def test_empty_talk_hits_matches_the_bad_wording_only():
    assert ag.empty_talk_hits("关于持续时长，信息尚不完整，建议进一步核实。")
    assert ag.empty_talk_hits("这一项还有待核实。")
    # 合格写法：说了「不完整」，但紧跟具体到槽位的确认项 —— 不能误伤
    assert ag.empty_talk_hits(
        "目前信息还不完整，需要确认的问题是：被什么东西占用了（比如废旧家具、私家车）") == []


def test_empty_talk_in_a_full_report_triggers_a_warning(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        _capture(monkeypatch, _state(),
                 reply="关于是否影响通行，信息尚不完整，建议进一步核实。")
    assert any("report_empty_talk" in r.getMessage() for r in caplog.records)


def test_empty_talk_in_a_preliminary_report_triggers_a_warning(monkeypatch, caplog):
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}, "missing": ["persistence"],
                 "report_missing": ["persistence"]}],
        missing=["fire_lane_blocked_persistence"],
        report_mode="preliminary",
    )
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        _capture(monkeypatch, state,
                 reply="占用消防车通道违反第28条。是长期还是临时？剩下的事项建议进一步核实。")
    assert any("report_empty_talk" in r.getMessage() for r in caplog.records)


def test_warning_is_not_raised_for_clean_reports(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        _capture(monkeypatch, _state(), reply="若为长期占用则适用第28条；若为临时则责令改正。")
    assert not [r for r in caplog.records if "report_empty_talk" in r.getMessage()]


def test_preliminary_coverage_recognises_the_real_wording(monkeypatch, caplog):
    """实测补的标记：真实模型写「目前仍然缺的就是…」「这一项尚未确认」，都要认得。"""
    assert ag.preliminary_coverage(
        "目前仍然缺的就是占用时长这一条，它直接决定按哪一款处理。")["missing"] is True
    assert ag.preliminary_coverage(
        "是否实际影响通行这一项尚未确认。")["missing"] is True
    assert ag.preliminary_coverage("通道被占了。")["missing"] is False


def test_preliminary_coverage_recognises_hai_cha_wording():
    """阶段 6 补的标记：真实模型写「还差一项会影响定档的信息」「还缺两个方面」也要认得。"""
    assert ag.preliminary_coverage(
        "还差一项会影响定档的信息，就是这次占用是否实际影响了消防车通行。")["missing"] is True
    assert ag.preliminary_coverage(
        "目前还缺两个方面：占用时长和占用物类型。")["missing"] is True


# ---------- ④ 不回退小标题模板 ----------

def test_preliminary_branch_report_still_has_no_headings(monkeypatch):
    reply = ("### 一、初步判断\n占用消防车通道违反第28条。\n"
             "### 二、仍需确认\n是否长期占用？若为长期占用，适用第28条可处罚；若为临时，以责令改正为主。")
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}, "missing": ["persistence"],
                 "report_missing": ["persistence", "impact"]}],
        missing=["fire_lane_blocked_persistence"],
        report_mode="preliminary",
    )
    _, update = _capture(monkeypatch, state, reply=reply)
    body = update["draft_report"]
    assert "###" not in body
    assert "占用消防车通道违反第28条" in body
    assert body.count("？") + body.count("?") == 1     # 仍至多一个问句
    assert _has_branch(body)                           # 条件分支没被削掉
