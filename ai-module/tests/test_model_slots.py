from config import ModelSlot

import core.agent as agent_mod


def _slot(provider, base, model):
    return ModelSlot(provider=provider, base_url=base, api_key="k", model=model)


def test_small_agents_use_small_slot(monkeypatch):
    monkeypatch.setattr(agent_mod, "TEXT_MODEL", _slot("textp", "http://text", "text-model"))
    monkeypatch.setattr(agent_mod, "SMALL_MODEL", _slot("smallp", "http://small", "small-model"))
    small = agent_mod.Agent("rewrite_query", "", [], "http://x", "k", "x")
    text = agent_mod.Agent("report", "", [], "http://x", "k", "x")
    planner = agent_mod.Agent("dialogue_planner", "", [], "http://x", "k", "x")
    question = agent_mod.Agent("ask_slot_question", "", [], "http://x", "k", "x")
    assert small._llm_endpoints()[0][:3] == ("http://small", "k", "small-model")
    assert text._llm_endpoints()[0][:3] == ("http://text", "k", "text-model")
    assert planner._llm_endpoints()[0][:3] == ("http://text", "k", "text-model")
    assert question._llm_endpoints()[0][:3] == ("http://small", "k", "small-model")


def test_explicit_slot_overrides_name(monkeypatch):
    monkeypatch.setattr(agent_mod, "TEXT_MODEL", _slot("textp", "http://text", "text-model"))
    monkeypatch.setattr(agent_mod, "SMALL_MODEL", _slot("smallp", "http://small", "small-model"))
    agent = agent_mod.Agent("custom", "", [], "http://x", "k", "x", slot="small")
    assert agent._llm_endpoints()[0][:3] == ("http://small", "k", "small-model")


def test_fallback_duplicate_endpoint_is_skipped(monkeypatch):
    monkeypatch.setattr(agent_mod, "TEXT_MODEL", _slot("p", "http://same", "same-model"))
    monkeypatch.setattr(agent_mod, "FALLBACK_LLM_BASE_URL", "http://same")
    monkeypatch.setattr(agent_mod, "FALLBACK_LLM_API_KEY", "k")
    monkeypatch.setattr(agent_mod, "FALLBACK_LLM_MODEL", "same-model")
    agent = agent_mod.Agent("report", "", [], "http://x", "k", "x")
    assert len(agent._llm_endpoints()) == 1


def test_default_slot_uses_opendesign():
    from config import _DEFAULT_SLOT
    assert _DEFAULT_SLOT.provider == "opendesign"
    assert _DEFAULT_SLOT.base_url == "https://amr-link.open-design.ai/v1"
    assert _DEFAULT_SLOT.model == "deepseek-v4.1-flash"
