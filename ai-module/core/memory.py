"""
双层记忆架构: Working Memory(当前) + Historical Memory(按用户持久化)。

  Working Memory (session级)
  - 本轮视觉识别结果 / 检索结果 / 最近 N 轮对话
  - 注入 Agent messages，仅内存

  Historical Memory (user级，MySQL 持久化 + Redis 缓存)
  - 历史分析摘要、用户偏好统计
  - 按 user_id 隔离，MySQL 为最终存储，Redis 只做读取缓存
"""
import json
import logging
import time
from dataclasses import dataclass, field

import pymysql

from config import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_TIMEOUT_SECONDS,
)
from db_config import DB_CONFIG

LOGGER = logging.getLogger(__name__)

_HISTORY_TABLE = "ai_historical_analysis"
_REDIS_KEY_TEMPLATE = "ai:hist:{user_id}:context"
_REDIS_TTL_SECONDS = 300

_redis_client = None


# ====== Working Memory (当前) ======

@dataclass
class WorkingMemory:
    """当前会话的工作记忆。注入 Agent 的消息上下文。"""
    session_id: str = ""
    max_turns: int = 10  # 保留的对话轮数

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

    def get_history(self, last_n: int | None = None) -> list[dict]:
        """返回最近 last_n 条会话消息；不传则返回全部（最多 max_turns*2 条）。"""
        if last_n is None or last_n <= 0:
            return list(self.messages)
        return self.messages[-last_n:]

    def clear(self):
        self.current_vision = None
        self.current_cases = ""
        self.current_policy = ""
        self.messages.clear()

    def _trim(self):
        max_msgs = self.max_turns * 2
        if len(self.messages) > max_msgs:
            self.messages = self.messages[-max_msgs:]


# ====== 会话管理 ======

sessions: dict[str, WorkingMemory] = {}


def get_session(session_id: str) -> WorkingMemory:
    if session_id not in sessions:
        sessions[session_id] = WorkingMemory(session_id=session_id)
    return sessions[session_id]


# ====== Historical Memory (按用户持久化) ======

def _mysql_connection():
    return pymysql.connect(
        **DB_CONFIG,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
    )


def _redis():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
        )
    return _redis_client


def _redis_key(user_id: int) -> str:
    return _REDIS_KEY_TEMPLATE.format(user_id=user_id)


def archive_working_to_historical(user_id: int, session_id: str, report: str,
                                  vision: dict | None = None,
                                  dialogue: str = "") -> None:
    """将一次分析结果归档到该用户的历史记忆（MySQL），并失效 Redis 缓存。

    归档失败只记录日志，不影响本次分析结果返回。
    """
    if user_id is None:
        return
    vision = vision or {}
    category = (vision.get("hazard_category") or "")[:64]
    severity = (vision.get("severity") or "")[:16]
    description = (vision.get("description") or "")[:500]
    report = (report or "")[:5000]
    dialogue = (dialogue or "")[:2000]
    try:
        conn = _mysql_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {_HISTORY_TABLE} "
                    "(user_id, hazard_category, severity, description, report, dialogue) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_id, category, severity, description, report, dialogue),
                )
            conn.commit()
        finally:
            conn.close()
        try:
            _redis().delete(_redis_key(user_id))
        except Exception:
            pass
    except Exception as exc:
        LOGGER.warning("archive historical memory failed user_id=%s: %s", user_id, exc)


def get_historical_context(user_id: int) -> str:
    """返回该用户的历史上下文文本；无记录返回空串。Redis 不可用时降级查 MySQL。"""
    if user_id is None:
        return ""
    try:
        cached = _redis().get(_redis_key(user_id))
        if cached is not None:
            return cached
    except Exception:
        pass
    context = _build_context_from_mysql(user_id)
    try:
        if context:
            _redis().set(_redis_key(user_id), context, ex=_REDIS_TTL_SECONDS)
        else:
            _redis().set(_redis_key(user_id), "", ex=60)
    except Exception:
        pass
    return context


def _build_context_from_mysql(user_id: int) -> str:
    try:
        conn = _mysql_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT hazard_category, COUNT(*) FROM {_HISTORY_TABLE} "
                    "WHERE user_id=%s GROUP BY hazard_category "
                    "ORDER BY COUNT(*) DESC LIMIT 5",
                    (user_id,),
                )
                prefs = cur.fetchall()
                cur.execute(
                    f"SELECT hazard_category, severity, description, created_at "
                    f"FROM {_HISTORY_TABLE} WHERE user_id=%s "
                    "ORDER BY created_at DESC, id DESC LIMIT 5",
                    (user_id,),
                )
                recent = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        LOGGER.warning("load historical context failed user_id=%s: %s", user_id, exc)
        return ""

    if not prefs and not recent:
        return ""

    lines = ["=== 历史分析记录（来自用户之前的会话）==="]
    if prefs:
        top = ", ".join(f"{cat}({cnt}次)" for cat, cnt in prefs)
        lines.append(f"用户关注隐患类别: {top}")
    for i, row in enumerate(recent, 1):
        category, severity, description, created_at = row
        lines.append(
            f"{i}. [{created_at}] {category} | {severity} | {(description or '')[:100]}"
        )
    return "\n".join(lines)
