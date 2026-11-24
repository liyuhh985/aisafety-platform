import pytest


@pytest.fixture(autouse=True)
def stub_skill_route_llm(monkeypatch):
    """Keep unit tests offline; routing algorithms are tested with injected callbacks."""
    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_skill_route_llm", lambda *args, **kwargs: {})