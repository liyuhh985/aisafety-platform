"""
双层记忆架构: Working Memory(当前) + Historical Memory(历史)。

  ┌─────────────────────────────────┐
  │     Working Memory (session级)   │
  │  - 本轮视觉识别结果                │
  │  - 本轮检索结果                    │
  │  - 最近 N 轮对话                   │
  │  → 直接注入 Agent messages        │
  └──────────────┬──────────────────┘
                 │ 超出窗口后 → 压缩摘要
                 ▼
  ┌─────────────────────────────────┐
  │   Historical Memory (跨session)  │
  │  - 历史分析摘要列表                │
  │  - 用户关注偏好统计                │
  │  → 新分析时注入 system prompt     │
  │  → 持久化到 JSON 文件             │
  └─────────────────────────────────┘
"""
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent / "db" / "historical_memory.json"


# ====== Working Memory (当前) ======

@dataclass
class WorkingMemory:
    """当前会话的工作记忆。注入 Agent 的消息上下文。"""
    session_id: str = ""
    max_turns: int = 3  # 保留的对话轮数

    # 当前轮次上下文
    current_vision: dict | None = None      # 本轮视觉识别结果
    current_cases: str = ""                 # 本轮检索的案例
    current_policy: str = ""                # 本轮检索的法规政策

    # 对话历史
    messages: list[dict] = field(default_factory=list)

    # 会话元信息
    created_at: float = field(default_factory=time.time)
    image_count: int = 0

    def set_vision(self, result: dict):
        self.current_vision = result
        self.image_count += 1

    def set_retrieval(self, cases: str, policy: str = ""):
        self.current_cases = cases
        self.current_policy = policy

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_report(self, content: str):
        """报告存为 system 消息，区别于普通对话。"""
        self.messages.append({"role": "system", "content": f"[分析报告]\n{content}"})

    def get_context_for_agent(self, include_current: bool = True) -> list[dict]:
        """
        构造注入 Agent 的上下文消息列表。
        include_current=True: 包含本轮视觉+检索结果（用于 Report Agent）
        include_current=False: 仅历史对话（用于 Chat Agent）
        """
        ctx = []
        if include_current and self.current_vision:
            ctx.append({
                "role": "system",
                "content": f"本轮视觉识别结果:\n{json.dumps(self.current_vision, ensure_ascii=False, indent=2)}"
            })
        if include_current and self.current_cases:
            ctx.append({"role": "system", "content": f"本轮检索案例:\n{self.current_cases}"})
        if include_current and self.current_policy:
            ctx.append({"role": "system", "content": f"本轮检索法规:\n{self.current_policy}"})
        # 历史对话
        ctx.extend(self.messages)
        return ctx

    def get_compressed_dialogue(self) -> str:
        """压缩对话历史为文本摘要，用于写入历史记忆。"""
        if not self.messages:
            return ""
        parts = []
        for m in self.messages:
            role = "用户" if m["role"] == "user" else "AI" if m["role"] == "assistant" else "系统"
            content = m["content"][:200]
            parts.append(f"[{role}]: {content}")
        return "\n".join(parts)

    def clear(self):
        self.current_vision = None
        self.current_cases = ""
        self.current_policy = ""
        self.messages.clear()

    def _trim(self):
        max_msgs = self.max_turns * 2
        if len(self.messages) > max_msgs:
            self.messages = self.messages[-max_msgs:]


# ====== Historical Memory (历史) ======

@dataclass
class HistoricalMemory:
    """
    跨会话的持久化历史记忆。
    超过 Working Memory 窗口的对话压缩后存入此处。
    """

    analyses: list[dict] = field(default_factory=list)    # 历史分析摘要
    preferences: dict[str, int] = field(default_factory=dict)  # 类别偏好计数

    def add_analysis(self, vision_result: dict, report_summary: str,
                     dialogue_summary: str = ""):
        """添加一次分析记录。"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": vision_result.get("hazard_category", ""),
            "severity": vision_result.get("severity", ""),
            "description": (vision_result.get("description", "") or "")[:200],
            "report": report_summary[:500],
            "dialogue": dialogue_summary,
        }
        self.analyses.append(entry)

        # 更新偏好
        cat = vision_result.get("hazard_category", "")
        if cat:
            self.preferences[cat] = self.preferences.get(cat, 0) + 1

        # 只保留最近 50 条
        if len(self.analyses) > 50:
            self.analyses = self.analyses[-50:]

    def get_context_for_new_analysis(self) -> str:
        """
        生成注入新分析 system prompt 的历史上下文。
        让 Agent 了解: 用户关注什么类别、历史分析过哪些场景。
        """
        if not self.analyses:
            return ""

        lines = ["=== 历史分析记录（来自用户之前的会话）==="]

        # 用户偏好
        if self.preferences:
            sorted_prefs = sorted(self.preferences.items(), key=lambda x: x[1], reverse=True)
            top_cats = ", ".join(f"{cat}({cnt}次)" for cat, cnt in sorted_prefs[:5])
            lines.append(f"用户关注隐患类别: {top_cats}")

        # 最近 5 次分析摘要
        recent = self.analyses[-5:]
        for i, a in enumerate(recent, 1):
            lines.append(
                f"{i}. [{a['timestamp']}] {a['category']} | {a['severity']} | "
                f"{a['description'][:100]}"
            )

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "analyses": self.analyses,
            "preferences": self.preferences,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoricalMemory":
        return cls(
            analyses=data.get("analyses", []),
            preferences=data.get("preferences", {}),
        )


# ====== 会话管理 ======

sessions: dict[str, WorkingMemory] = {}
_historical: HistoricalMemory | None = None


def get_session(session_id: str) -> WorkingMemory:
    if session_id not in sessions:
        sessions[session_id] = WorkingMemory(session_id=session_id)
    return sessions[session_id]


def get_historical() -> HistoricalMemory:
    global _historical
    if _historical is None:
        _historical = _load_historical()
    return _historical


def _load_historical() -> HistoricalMemory:
    if HISTORY_FILE.exists():
        try:
            return HistoricalMemory.from_dict(
                json.loads(HISTORY_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return HistoricalMemory()


def save_historical():
    """持久化历史记忆到 JSON 文件。"""
    if _historical is None:
        return
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(_historical.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8")


def archive_working_to_historical(session_id: str, report: str):
    """
    将当前 Working Memory 的关键信息压缩存入 Historical Memory。
    调用时机: 一次分析完成后。
    """
    wm = get_session(session_id)
    historical = get_historical()

    vision = wm.current_vision or {}
    dialogue = wm.get_compressed_dialogue()

    historical.add_analysis(
        vision_result=vision,
        report_summary=report[:500],
        dialogue_summary=dialogue,
    )

    save_historical()
