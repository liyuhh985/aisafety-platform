__all__ = ["Agent", "Tool"]


def __getattr__(name):
    if name == "Agent":
        from core.agent import Agent
        return Agent
    if name == "Tool":
        from core.tool import Tool
        return Tool
    raise AttributeError(name)
