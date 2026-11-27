from tests.reply_helpers import (collect_chunks, fake_report_model,
                                  render_reply, render_update, run_turn,
                                  streamed_text)
import core.assistant_graph as assistant_graph
import pytest
from core import dialogue_understanding
from core.scope_policy import DOMAIN_KEYWORDS, decide_scope


def test_hazard_text_is_in_scope():
    out = decide_scope({}, "消防设施老旧，无法正常使用")
    assert out["scope"] == "hazard"


def test_weather_question_is_out_of_scope():
    out = decide_scope({}, "今天天气怎么样")
    assert out["scope"] == "out_of_scope"
    assert out["response"]


def test_emergency_has_priority_over_scope():
    out = decide_scope({}, "楼下着火了，有人被困")
    assert out["scope"] == "emergency"
    assert "119" in out["response"]


def test_ambiguous_request_gets_anchoring_question():
    out = decide_scope({}, "我有个问题想问")
    assert out["scope"] == "ambiguous"
    assert "是否涉及" in out["response"]


def test_generic_fire_word_does_not_create_false_positive():
    out = decide_scope({"scope": "out_of_scope"}, "消防员招聘条件")
    assert out["scope"] == "out_of_scope"


def test_planner_issue_overrides_weak_text():
    out = decide_scope(
        {"ok": True, "issues": [{"subcategory_code": "fire_equipment_fault"}]},
        "你说的这个",
    )
    assert out["scope"] == "hazard"


def test_plan_reads_scope_metadata():
    raw = (
        '{"intent":"other","scope":"out_of_scope","scope_confidence":0.92,'
        '"issues":[],"question":"","answer":"","needs_search":false}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["scope"] == "out_of_scope"
    assert plan["scope_confidence"] == 0.92


def test_invalid_scope_defaults_to_empty_hint():
    raw = (
        '{"intent":"other","scope":"invalid","issues":[],"question":"",'
        '"answer":"","needs_search":false}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["scope"] == ""


def test_scope_guard_refuses_out_of_scope_without_search(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "other",
        "scope": "out_of_scope",
        "scope_confidence": 0.95,
        "issues": [],
        "categories": [],
        "category_slots": {},
        "question": "",
        "answer": "今天多云",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="今天天气怎么样")],
    })
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="今天天气怎么样")],
    })
    assert update["scope"] == "out_of_scope"
    assert update["direct_mode"] == "out_of_scope"


def test_scope_guard_keeps_hazard_flow(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "report_hazard",
        "scope": "hazard",
        "scope_confidence": 0.95,
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "categories": ["fire_equipment_fault"],
        "category_slots": {},
        "question": "",
        "answer": "",
        "needs_search": True,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
    })
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
    })
    assert update["scope"] == "hazard"
    assert "direct_mode" not in update


def test_scope_guard_emergency(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "other",
        "scope": "emergency",
        "scope_confidence": 0.9,
        "issues": [],
        "categories": [],
        "category_slots": {},
        "question": "",
        "answer": "",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="楼下着火了，有人被困")],
    })
    # 紧急不再由 understand 提前劫持整轮；它只表达 danger_veto，
    # 范围由 scope_guard 钉成 emergency。
    assert understood["danger_veto"] is True
    assert understood["direct_mode"] == ""
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="楼下着火了，有人被困")],
    })
    assert update["scope"] == "emergency"


def test_scope_guard_ambiguous(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "other",
        "scope": "ambiguous",
        "scope_confidence": 0.4,
        "issues": [],
        "categories": [],
        "category_slots": {},
        "question": "",
        "answer": "",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="我有个问题想问")],
    })
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="我有个问题想问")],
    })
    assert update["scope"] == "ambiguous"
    assert update["direct_mode"] == "anchor_domain"


def test_scope_guard_does_not_override_smalltalk_fast_path():
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="你好")],
    })
    assert understood["direct_mode"] == "smalltalk"
    assert assistant_graph.scope_guard({**understood}) == {}


def test_safety_text_comes_only_from_the_emergency_node(monkeypatch):
    """新契约：understand 不再发安全文本（即时反馈换成唯一出处），但规划器照常参与；
    安全文本由 emergency_guidance 产出，危险轮不进检索/报告/建单。
    """
    seen = {}

    def slow_plan(messages, vision_summary="", selected_major_code=""):
        seen["called"] = True
        return {"ok": True, "intent": "other", "issues": [], "categories": [],
                "category_slots": {}, "question": "", "answer": "", "needs_search": False}

    monkeypatch.setattr(assistant_graph, "_understand_plan", slow_plan)
    chunks = collect_chunks(monkeypatch)
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="楼下着火了，有人被困")],
    })
    assert update["danger_veto"] is True
    assert update["guidance_emitted"] is True
    assert streamed_text(chunks) == ""            # understand 一个字都不发
    assert seen.get("called") is True             # 不再劫持这一轮
    fake_report_model(monkeypatch, "请立即撤离到楼下并拨打 119。")
    nodes, answer, _values = run_turn(
        assistant_graph.build_graph(), {"configurable": {"thread_id": "emg-scope"}},
        "楼下着火了，有人被困")
    assert "emergency_guidance" in nodes
    for forbidden in ("search", "report", "task_gate"):
        assert forbidden not in nodes, forbidden
    assert "119" in answer


def test_planner_smalltalk_does_not_hijack_non_greeting():
    out = decide_scope({"scope": "smalltalk"}, "今天天气")
    assert out["scope"] == "out_of_scope"
    assert "我主要负责城市安全隐患" in out["response"]


def test_exact_greeting_still_wins_over_planner_scope():
    out = decide_scope({"scope": "out_of_scope"}, "你好")
    assert out["scope"] == "smalltalk"


def test_out_of_scope_templates_vary_by_scope_key():
    first = decide_scope({}, "今天天气", scope_key="session-a|1")
    second = decide_scope({}, "今天天气", scope_key="session-a|2")
    assert first["response"] != second["response"]


def test_direct_reply_greeting_variants_are_contextual(monkeypatch):
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda _: None)
    cases = {
        "你好": "你好，我在",
        "在吗": "在的",
        "嗨": "嗨，我在",
        "谢谢": "不客气",
    }
    for text, expected in cases.items():
        update = render_update({
            "direct_mode": "smalltalk",
            "messages": [assistant_graph.HumanMessage(content=text)],
        })
        assert update["messages"][-1].content.startswith(expected)


def test_scope_guard_uses_varied_response(monkeypatch):
    first = assistant_graph.scope_guard({
        "dialogue_plan": {"ok": True, "scope": "out_of_scope", "issues": []},
        "messages": [assistant_graph.HumanMessage(content="今天天气")],
        "session_id": "scope-session",
    })
    second = assistant_graph.scope_guard({
        "dialogue_plan": {"ok": True, "scope": "out_of_scope", "issues": []},
        "messages": [
            assistant_graph.HumanMessage(content="今天天气"),
            assistant_graph.AIMessage(content=first["scope_response"]),
            assistant_graph.HumanMessage(content="今天天气"),
        ],
        "session_id": "scope-session",
    })
    assert first["scope_response"] != second["scope_response"]


def test_direct_reply_scope_templates_are_fixed(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    update = render_update({
        "direct_mode": "out_of_scope",
        "messages": [],
    })
    content = update["messages"][-1].content
    assert "我主要负责城市安全隐患" in content
    assert chunks == [{"chunk": content}]

# ===== 占道家族：确定性兜底的回归（2026-09-28 扩表）=====
# 背景：扩表前这一族在 DOMAIN_KEYWORDS 里只有字面「占道」一个词，范围判据完全依赖
# 规划器稳定抽出 issues；实测记录过一次真实误拦（db/eval_stage5_e2e.txt：
# 「有人在人行道上摆摊经营」被规划器报成 smalltalk → out_of_scope → boundary_reply）。
# 下面这组用例把「规划器什么都没给」当成最坏情况，锁住确定性兜底。

ROAD_OCCUPANCY_PHRASINGS = (
    "有人在人行道上摆摊经营",
    "路口那边摆摊的特别多",
    "人行道上摆了很多摊",
    "人行道被摊位占了",
    "店门口摆摊卖东西",
    "马路市场把路都占了",
    "小商贩占道摆摊",
    "流动摊贩占道经营",
    "路边有人占道卖水果",
    "马路边上占道的情况挺严重",
    "有建材乱堆在人行道上",
    "路边堆放了不少杂物",
    "私家车违停在人行道上",
)

OFF_DOMAIN_SAMPLES = (
    "今天天气怎么样",
    "红烧肉怎么做好吃",
    "帮我写一首关于秋天的诗",
    "推荐一部适合周末看的电影",
    "Python 列表如何去重",
    "今天股市收盘涨了多少",
)


@pytest.mark.parametrize("text", ROAD_OCCUPANCY_PHRASINGS)
def test_road_occupancy_phrasings_survive_a_silent_planner(text):
    """plan={}（规划器没抽 issues、也没给 scope 信心）时也必须判成 hazard。"""
    out = decide_scope({}, text)
    assert out["scope"] == "hazard", (text, out)


@pytest.mark.parametrize("text", OFF_DOMAIN_SAMPLES)
def test_off_domain_samples_are_still_rejected_after_widening(text):
    """扩表不能把越界输入一起放进来 —— 反向误伤检查。"""
    out = decide_scope({}, text)
    assert out["scope"] == "out_of_scope", (text, out)


def test_bare_tan_is_deliberately_not_a_domain_keyword():
    """有意不收单字「摊」：摊开/摊牌/摊销是域外说法，收了会误放。"""
    assert "摊" not in DOMAIN_KEYWORDS
    assert decide_scope({}, "把事情摊开讲清楚")["scope"] == "out_of_scope"
    assert decide_scope({}, "他准备跟老板摊牌了")["scope"] == "out_of_scope"


# ===== 交通设施 / 外立面 / 配电设施：确定性兜底的回归（2026-09-28 第二次扩表）=====
# 背景：扩表前这一族只有「外墙」「配电箱」两个词，用户说「外立面」「配电设施」就判越界。
# 实测（plan={}，不调模型）扩表前 10 条本领域表述 10/10 被判 out_of_scope —— 回复是
# 「不在我的专业范围内」，与占道那次同属"用户描述本领域隐患却被拒绝"。
# 语料计数见 core/scope_policy.py 的注释（db/experiments/measure_scope_words.py 可复现）。

TRAFFIC_FACILITY_PHRASINGS = (
    "路边有个交通标志牌和护栏坏了",
    "交通设施损坏了没人修",
    "路口的信号灯不亮了",
    "道路中间的护栏被撞断了",
    # 2026-09-29 第三次扩表补的两条（扩表前均判越界）
    "路上的交通标线看不清了",
    "交通标线磨损掉色了",
)

FACADE_FALL_PHRASINGS = (
    "小区外立面墙皮脱落",
    "楼房外立面的瓷砖掉下来了",
    "外立面的墙皮一块块往下掉",
)

DISTRIBUTION_BOX_PHRASINGS = (
    "配电设施出问题了",
    "小区里的配电柜门开着很危险",
    "配电房旁边堆了杂物",
)

NEW_FAMILY_PHRASINGS = (
    TRAFFIC_FACILITY_PHRASINGS + FACADE_FALL_PHRASINGS + DISTRIBUTION_BOX_PHRASINGS
)

EXTRA_OFF_DOMAIN_SAMPLES = (
    "帮我写一篇八百字的周记",
    "这道数学题怎么解",
    "推荐一款性价比高的手机",
)


@pytest.mark.parametrize("text", NEW_FAMILY_PHRASINGS)
def test_new_family_phrasings_survive_a_silent_planner(text):
    """plan={}（规划器什么都没给）时也必须判成 hazard。"""
    out = decide_scope({}, text)
    assert out["scope"] == "hazard", (text, out)


@pytest.mark.parametrize("text", OFF_DOMAIN_SAMPLES + EXTRA_OFF_DOMAIN_SAMPLES)
def test_extended_off_domain_samples_are_still_rejected(text):
    """扩表不能把越界输入一起放进来 —— 反向误伤检查。"""
    out = decide_scope({}, text)
    assert out["scope"] == "out_of_scope", (text, out)


def test_over_broad_words_are_deliberately_excluded():
    """「脱落」「变压器」跨类别或域外用法多，有意不收（理由见 scope_policy 注释）。"""
    assert "脱落" not in DOMAIN_KEYWORDS
    assert "变压器" not in DOMAIN_KEYWORDS
    assert "电箱" not in DOMAIN_KEYWORDS          # 是「配电箱」的子串，不新增覆盖
    assert decide_scope({}, "最近头发脱落得厉害")["scope"] == "out_of_scope"
    assert decide_scope({}, "变压器的工作原理是什么")["scope"] == "out_of_scope"


def test_new_family_words_are_present():
    """把扩表的词钉住，防止回退。"""
    for word in ("交通设施", "交通标志", "标志牌", "护栏", "信号灯", "交通标线",
                 "外立面", "墙皮", "配电设施", "配电柜", "配电房"):
        assert word in DOMAIN_KEYWORDS, word


# ===== 交通标线 收录 / 指示牌·光杆标线 排除（2026-09-29 第三次扩表）=====
# 背景：扩表前「路上的交通标线看不清了」判 out_of_scope，与前面几次同属
# "用户描述本领域隐患却被拒绝"。收录依据见 core/scope_policy.py 的注释（语料计数是 0，
# 依据是 taxonomy 标签「交通设施损坏」+ 同族构词 + 自带域标记「交通」）。
# 「指示牌」和光杆「标线」有域外家族，有意不收 —— 下面同时钉住"收了的能过"和"没收的不被误放"。

SIGN_WORD_OFF_DOMAIN = (
    "商场里的指示牌歪了",
    "楼层指示牌挂得太低了",
    "Excel 表格怎么加标线",
    "图纸上的标线怎么画",
)


@pytest.mark.parametrize("text", SIGN_WORD_OFF_DOMAIN)
def test_sign_word_off_domain_samples_are_still_rejected(text):
    """光杆「指示牌」「标线」没收，所以这些域外输入不会被范围层放行。"""
    out = decide_scope({}, text)
    assert out["scope"] == "out_of_scope", (text, out)


def test_ambiguous_sign_words_are_deliberately_excluded():
    """「指示牌」/光杆「标线」有域外家族（商场指示牌、表格标线），有意不收；只收自带域标记
    的「交通标线」。理由见 scope_policy 的注释。

    另外钉住本次有意留下的取舍（已知残留）：不含「交通」的域内说法仍会判越界 ——
    要覆盖它们得靠域锚共现，那要改判据机制，不在词表改动范围内。
    """
    assert "交通标线" in DOMAIN_KEYWORDS
    assert "标线" not in DOMAIN_KEYWORDS          # 光杆词：域外家族（表格/图纸/衣服标线）
    assert "指示牌" not in DOMAIN_KEYWORDS        # 域外家族（商场/楼层/导览指示牌）
    assert "道路标线" not in DOMAIN_KEYWORDS      # 无任何语料或用户措辞证据，本次未收
    for residual in ("地上的标线看不清", "道路标线模糊不清", "路口的指示牌歪了"):
        assert decide_scope({}, residual)["scope"] == "out_of_scope", residual

# ===== 物件型小类的原文核对（2026-09-29）=====
# 背景：端到端实测（db/eval_scope_families_e2e_offdomain.txt、db/_diag_planner_leak.py）
# 「商场里的指示牌歪了」「楼层指示牌挂得太低了」被**规划器自己**判成 hazard、归成
# traffic/traffic_facility_damage（有时是 environment_other/other），进而出一份引
# 《公路安全保护条例》的完整报告。分类是语义判断，代码看不见；能看见的是
# "原文有没有交代这件事发生在公共空间、或有没有点到那个物件"。
# 规则与表见 core/scope_policy.py 的 OBJECT_CLASS_EVIDENCE，设计见
# docs/superpowers/specs/2026-09-29-object-claim-grounding-design.md

from core.hazard_taxonomy import SUBCATEGORY_TO_MAJOR
from core.scope_policy import (CATCH_ALL_SUBCATEGORIES, OBJECT_CLASS_EVIDENCE,
                               PUBLIC_SPACE_WORDS, unbacked_hazard_claim)

OBJECT_CLASS_CODES = (
    "traffic_facility_damage", "manhole_damage", "street_light_pole",
    "distribution_box_fault", "falling_object",
)


def plan_claiming(subcategory_code, text=""):
    """造一个"规划器说这是某小类隐患"的 plan（模型自报的部分就是这些）。"""
    return {
        "ok": True, "scope": "hazard", "scope_confidence": 0.95,
        "issues": [{
            "major_code": "?",
            "subcategory_code": subcategory_code,
            "slots": {"describe": text}, "confidence": 0.8,
        }],
    }


UNBACKED_OBJECT_CLAIMS = (
    "商场里的指示牌歪了",
    "楼层指示牌挂得太低了",
    "小区门口的导览指示牌歪了",
)


@pytest.mark.parametrize("text", UNBACKED_OBJECT_CLAIMS)
def test_object_claim_without_public_space_evidence_is_not_accepted(text):
    """模型说是交通设施损坏，但原文既没点到物件也没说公共空间 → 不采信，不给报告。"""
    out = decide_scope(plan_claiming("traffic_facility_damage", text), text)
    assert out["scope"] != "hazard", (text, out)
    assert out["scope"] == "ambiguous", (text, out)
    assert out["reason"].startswith("unbacked hazard claim"), out
    assert "是否涉及" in out["response"]


OBJECT_CLASS_PHRASES = (
    ("traffic_facility_damage", "那个路口的灯早就不亮了，车和人都不知道什么时候能走"),   # 场所词
    ("traffic_facility_damage", "交通标线磨损掉色了"),                                  # 物件词
    ("manhole_damage", "马路上一个铁盖子没了，就留个黑洞，晚上看不见掉下去就完了"),        # 场所词
    ("manhole_damage", "暴雨夜雨水井盖缺失移位，行人涉水坠井"),                          # 物件词
    ("street_light_pole", "那条路晚上黑得看不见人，旁边的杆子还歪着"),                  # 场所词
    ("street_light_pole", "小区外路灯连片不亮，线杆底座倾斜开裂"),                        # 物件词
    ("distribution_box_fault", "楼下的电表箱子门掉了，里面还冒烟有糊味"),                 # 物件词
    ("distribution_box_fault", "小区配电箱箱门缺失、接线端子烧蚀冒烟"),                   # 物件词
    ("falling_object", "楼上掉下来一大块外墙的砖，把车都砸穿了"),                            # 物件词
    ("falling_object", "高层大厦外立面大理石瓷砖脱落砸坏车辆"),                              # 物件词
    ("falling_object", "楼上有人往下扔东西，瓶子掉下来把车玻璃砸碎了"),                      # 抛物词
)


@pytest.mark.parametrize("code,text", OBJECT_CLASS_PHRASES)
def test_object_claims_with_real_evidence_still_pass(code, text):
    """真实的本领域表述（含宽松口吻）不能被核对误伤 —— 这些同时是分类评测的口语样本。

    断言"没被降级"而不是"== hazard"：其中几条含「冒烟」等危险词，按既有规则本来就走
    emergency（危险优先），那是另一条既存行为，不该被这条核对改掉。
    """
    out = decide_scope(plan_claiming(code, text), text)
    assert out["scope"] not in {"ambiguous", "out_of_scope"}, (code, text, out)


@pytest.mark.parametrize("code", OBJECT_CLASS_CODES)
def test_every_object_evidence_word_is_effective(code):
    """表里每个词都真的能放行（防止写错字/写死词）。"""
    for word in OBJECT_CLASS_EVIDENCE[code]:
        assert unbacked_hazard_claim([{"subcategory_code": code}], "这儿有个" + word + "坏了") == "", (code, word)
    assert unbacked_hazard_claim([{"subcategory_code": code}], "一切正常") == code


def test_v2b_scope_keywords_are_present():
    required = (
        "电动自行车", "飞线充电", "危化品", "危险化学品", "烟花爆竹",
        "有限空间", "化粪池", "树木倒伏", "行道树",
    )
    for word in required:
        assert word in DOMAIN_KEYWORDS, word


def test_public_space_words_are_a_whitelist_not_a_veto():
    """场所词只用于放行：原文提到公共空间时，即使没说物件也不否决。"""
    for word in PUBLIC_SPACE_WORDS:
        assert unbacked_hazard_claim(
            [{"subcategory_code": "manhole_damage"}], "那边" + word + "上的东西坏了") == "", word


def test_non_object_classes_need_no_evidence():
    """非物件型小类的判据是"情形"而不是"物件"，不适用这条核对。"""
    out = decide_scope(plan_claiming("fire_lane_blocked"), "楼道里堆了很多纸箱")
    assert out["scope"] == "hazard"
    out = decide_scope(plan_claiming("elevator_trapped"), "有人在里面")
    assert out["scope"] == "hazard"
    out = decide_scope(plan_claiming("road_occupancy"), "路口那边摆摊的特别多")
    assert out["scope"] == "hazard"


def test_object_evidence_can_come_from_vision_summary():
    """视觉摘要也是原文的一部分：用户只说「这个歪了」，物件在图片说明里。"""
    text = "这个歪了，你看下"
    assert decide_scope(plan_claiming("traffic_facility_damage"), text)["scope"] == "ambiguous"
    out = decide_scope(plan_claiming("traffic_facility_damage"), text,
                       support_text="路口交通标志牌倾斜，底座松动")
    assert out["scope"] == "hazard"


def test_object_evidence_table_covers_only_registered_classes():
    """表有意只有这 5 类；扩表必须先有"模型误判 + 原文没有该物件词"的实例（见 spec §6）。"""
    assert set(OBJECT_CLASS_EVIDENCE) == set(OBJECT_CLASS_CODES)
    for code in OBJECT_CLASS_EVIDENCE:
        assert code in SUBCATEGORY_TO_MAJOR, code
    assert CATCH_ALL_SUBCATEGORIES == ("other",)
    for code in CATCH_ALL_SUBCATEGORIES:
        assert code in SUBCATEGORY_TO_MAJOR, code


def test_catch_all_claim_needs_a_domain_or_place_word():
    """兜底类（其他）：说"其他隐患"时，原文至少要有领域词或场所词（它自己不是物件）。"""
    assert unbacked_hazard_claim([{"subcategory_code": "other"}], "楼层指示牌挂得太低了") == "other"
    assert unbacked_hazard_claim([{"subcategory_code": "other"}], "公共区域出现来源不明的危化品桶") == ""
    assert unbacked_hazard_claim([{"subcategory_code": "other"}], "路边放着几个大桶") == ""


def test_catch_all_leak_variant_is_not_accepted():
    """漏放的另一个变体：规划器把「楼层指示牌」归成 environment_other/other（实测 3/6 次）。"""
    out = decide_scope(plan_claiming("other"), "楼层指示牌挂得太低了")
    assert out["scope"] == "ambiguous", out
    assert out["reason"].startswith("unbacked hazard claim"), out


def test_unbacked_check_is_pure_and_handles_junk():
    """纯函数边界：issues 为空 / 不是 dict / 没有小类编码都不该抛。"""
    assert unbacked_hazard_claim(None, "商场里的指示牌歪了") == ""
    assert unbacked_hazard_claim([], "商场里的指示牌歪了") == ""
    assert unbacked_hazard_claim(["x", {}, {"subcategory_code": ""}], "商场里的指示牌歪了") == ""


def test_detached_sign_word_is_deliberately_not_evidence():
    """「指示牌」有域外家族（商场/楼层/导览牌），与词表同一条理由，有意不做物件词。"""
    words = OBJECT_CLASS_EVIDENCE["traffic_facility_damage"]
    assert not any("指示牌" in word for word in words)
    assert "灯" not in OBJECT_CLASS_EVIDENCE["street_light_pole"]
