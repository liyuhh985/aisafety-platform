# -*- coding: utf-8 -*-
"""Runtime semantic verification contracts (tasks added in TDD order)."""

from core.agent import Agent


def test_semantic_agent_temperature_is_zero():
    agent = Agent(
        name="semantic_labeler_a",
        system_prompt="VERIFY",
        tools=[],
        base_url="http://example.invalid",
        api_key="k",
        model="m",
        temperature=0.0,
        use_configured_slot=False,
        allow_fallback=False,
    )
    payload = agent._build_payload([{"role": "user", "content": "q"}], stream=False)
    assert payload["temperature"] == 0.0


def test_dedicated_agent_ignores_global_slot_and_fallback(monkeypatch):
    from types import SimpleNamespace
    import core.agent as agent_module

    monkeypatch.setattr(
        agent_module,
        "SMALL_MODEL",
        SimpleNamespace(base_url="http://global", api_key="g", model="global", effort=""),
    )
    monkeypatch.setattr(agent_module, "FALLBACK_LLM_BASE_URL", "http://fallback")
    monkeypatch.setattr(agent_module, "FALLBACK_LLM_API_KEY", "f")
    monkeypatch.setattr(agent_module, "FALLBACK_LLM_MODEL", "fallback-model")
    agent = Agent(
        name="semantic_labeler_a",
        system_prompt="VERIFY",
        tools=[],
        base_url="http://dedicated",
        api_key="d",
        model="minimax-m3.1-flash",
        slot="small",
        use_configured_slot=False,
        allow_fallback=False,
    )
    assert agent._llm_endpoints() == [
        ("http://dedicated", "d", "minimax-m3.1-flash", None)
    ]
