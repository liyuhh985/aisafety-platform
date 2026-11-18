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
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pymysql

from config import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_TIMEOUT_SECONDS,
    SESSION_BACKEND,
    SESSION_REDIS_FALLBACK,
    SESSION_REDIS_PREFIX,
    SESSION_REDIS_TTL_SECONDS,
)
from db_config import DB_CONFIG
from tools import db_pool

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

    def add_system(self, content: str):
        """追加一条 system 消息（如 server.py 注入的 [视觉分析]）。"""
        self.messages.append({"role": "system", "content": content})

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


# ====== 会话管理（SESSION_BACKEND=memory 进程内 / redis 跨 worker 共享）======

sessions: dict[str, WorkingMemory] = {}

# 本进程已构造的 Redis 会话对象：只做对象复用，不做消息缓存（消息永远以 Redis 为准）。
_redis_sessions: dict[str, "RedisWorkingMemory"] = {}


class SessionStoreUnavailable(RuntimeError):
    """会话后端（Redis）不可用。只有 SESSION_REDIS_FALLBACK=strict 才会抛出来。"""


class SessionTurnBusy(RuntimeError):
    """同一个用户会话已有一个 turn 在执行。"""


_SESSION_TURN_LOCKS: dict[str, threading.Lock] = {}
_SESSION_TURN_LOCKS_GUARD = threading.Lock()
_SESSION_TURN_LOCK_PREFIX = f"{SESSION_REDIS_PREFIX}turn-lock:"
_SESSION_TURN_LOCK_TTL_SECONDS = max(30, min(300, SESSION_REDIS_TTL_SECONDS))
_RELEASE_SESSION_TURN_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


def session_namespace(user_id: int, session_id: str) -> str:
    """会话与 LangGraph checkpoint 共用的安全命名空间。"""
    if user_id is None:
        raise ValueError("user_id is required for session access")
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    return f"{int(user_id)}:{sid}"


class SessionTurnLease:
    """一次会话 turn 的锁持有凭据；release 幂等。"""

    def __init__(self, key: str, *, local_lock: Any = None,
                 redis_client=None, redis_token: str = ""):
        self._key = key
        self._local_lock = local_lock
        self._redis_client = redis_client
        self._redis_token = redis_token
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        if self._redis_client is not None:
            try:
                self._redis_client.eval(
                    _RELEASE_SESSION_TURN_LOCK_SCRIPT,
                    1,
                    self._key,
                    self._redis_token,
                )
            except Exception as exc:
                LOGGER.warning("release session turn lock failed key=%s: %s", self._key, exc)
            return
        if self._local_lock is None:
            return
        with _SESSION_TURN_LOCKS_GUARD:
            try:
                self._local_lock.release()
            except RuntimeError:
                pass
            if (not self._local_lock.locked()
                    and _SESSION_TURN_LOCKS.get(self._key) is self._local_lock):
                _SESSION_TURN_LOCKS.pop(self._key, None)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _decode_session_message(raw) -> dict | None:
    """把 Redis LIST 里的一条记录还原成消息 dict；坏数据直接丢弃，不让脏值传播。"""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if isinstance(data, dict) and data.get("role"):
        return data
    return None


class RedisWorkingMemory(WorkingMemory):
    """messages 落 Redis 的会话记忆：同一 session_id 跨进程 / 跨重启可恢复。

    为什么这么设计：
    - messages 是唯一需要跨 worker 共享的东西（对话历史）。用 Redis LIST 存，
      写是 RPUSH + LTRIM（原子追加 + 截断），读是 LRANGE，**不做进程内缓存**，
      否则 A worker 写、B worker 读到的还是旧快照。
    - current_vision / current_cases / current_policy 是"本轮请求"的临时上下文，
      跨进程恢复没有意义，仍留在进程内；跨轮需要的内容由 server.py 以
      [视觉分析] 这类 system 消息写进 messages。
    - Redis 抖动时不抛给调用方（除 strict）：记告警 + 退回进程内副本，
      保证单个 worker 仍能继续对话，不因为缓存故障把整个 AI 服务拖死。
    """

    def __init__(self, session_id: str, client, *,
                 key_prefix: str = SESSION_REDIS_PREFIX,
                 ttl_seconds: int = SESSION_REDIS_TTL_SECONDS,
                 max_turns: int = 10,
                 strict: bool = False):
        # 先置 _client=None + _local=[]：让基类 __init__ 里的 self.messages 赋值
        # 只落到进程内副本，构造时不碰 Redis（Redis 连不上也要能构造出对象）。
        self._client = None
        self._local: list[dict] = []
        self._degraded = False
        self._key = ""
        self._ttl = 0
        self._strict = strict
        super().__init__(session_id=session_id, max_turns=max_turns)
        self._client = client
        self._key = f"{key_prefix}{session_id}"
        self._ttl = max(1, int(ttl_seconds))

    # ---------- 内部 ----------

    def _max_messages(self) -> int:
        return max(2, self.max_turns * 2)

    def _note_redis_failure(self, op: str, exc: Exception) -> None:
        self._degraded = True
        LOGGER.warning(
            "session redis unavailable op=%s session_id=%s: %s",
            op, self.session_id, exc,
        )
        if self._strict:
            raise SessionStoreUnavailable(
                f"redis session store failed: op={op} session_id={self.session_id}"
            ) from exc

    def _trim_local(self) -> None:
        max_msgs = self._max_messages()
        if len(self._local) > max_msgs:
            self._local = self._local[-max_msgs:]

    def _load(self) -> list[dict]:
        """读全部消息。Redis 不可用 -> 退回进程内副本（degrade 策略）。"""
        client = getattr(self, "_client", None)
        if client is None:
            return list(self._local)
        try:
            raw = client.lrange(self._key, 0, -1)
        except Exception as exc:
            self._note_redis_failure("lrange", exc)
            return list(self._local)
        out = []
        for item in raw or []:
            data = _decode_session_message(item)
            if data is not None:
                out.append(data)
        self._local = out
        return list(out)

    def _append(self, message: dict) -> None:
        client = getattr(self, "_client", None)
        if client is None:
            self._local.append(message)
            self._trim_local()
            return
        try:
            pipe = client.pipeline()
            pipe.rpush(self._key, json.dumps(message, ensure_ascii=False))
            pipe.ltrim(self._key, -self._max_messages(), -1)
            if self._ttl:
                pipe.expire(self._key, self._ttl)
            pipe.execute()
        except Exception as exc:
            self._note_redis_failure("rpush", exc)
        self._local.append(message)
        self._trim_local()

    def _replace(self, messages: list[dict]) -> None:
        self._local = list(messages or [])
        self._trim_local()
        client = getattr(self, "_client", None)
        if client is None:
            return
        try:
            values = [json.dumps(m, ensure_ascii=False) for m in self._local]
            pipe = client.pipeline()
            pipe.delete(self._key)
            if values:
                pipe.rpush(self._key, *values)
                if self._ttl:
                    pipe.expire(self._key, self._ttl)
            pipe.execute()
        except Exception as exc:
            self._note_redis_failure("replace", exc)

    # ---------- 对外的读 ----------

    @property
    def messages(self) -> list[dict]:
        """每次读都回 Redis 拿最新（多 worker 下不允许进程内缓存）。"""
        return self._load()

    @messages.setter
    def messages(self, value):
        # 基类 __init__ 会走这里：_client 还没接力（None）时只写本地副本。
        self._replace(list(value or []))

    def get_context_for_agent(self, include_current: bool = True) -> list[dict]:
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
        ctx.extend(self._load())
        return ctx

    def get_compressed_dialogue(self) -> str:
        msgs = self._load()
        if not msgs:
            return ""
        parts = []
        for m in msgs:
            role = "用户" if m["role"] == "user" else "AI" if m["role"] == "assistant" else "系统"
            content = (m.get("content") or "")[:200]
            parts.append(f"[{role}]: {content}")
        return "\n".join(parts)

    def get_history(self, last_n: int | None = None) -> list[dict]:
        msgs = self._load()
        if last_n is None or last_n <= 0:
            return msgs
        return msgs[-last_n:]

    # ---------- 对外的写 ----------

    def add_user(self, content: str):
        self._append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self._append({"role": "assistant", "content": content})

    def add_report(self, content: str):
        self._append({"role": "system", "content": f"[分析报告]\n{content}"})

    def add_system(self, content: str):
        self._append({"role": "system", "content": content})

    def clear(self):
        self.current_vision = None
        self.current_cases = ""
        self.current_policy = ""
        self._local = []
        client = getattr(self, "_client", None)
        if client is None:
            return
        try:
            client.delete(self._key)
        except Exception as exc:
            self._note_redis_failure("del", exc)

    def _trim(self):
        # Redis 后端在 _append 里已经 LTRIM，这里只需要保证本地副本不越界。
        self._trim_local()


def _session_backend() -> str:
    """运行时读取会话后端，便于测试和不改代码切换；非法值按 memory 处理。"""
    value = os.getenv("SESSION_BACKEND", SESSION_BACKEND).strip().lower()
    return value if value in {"memory", "redis"} else "memory"


def _session_redis_fallback() -> str:
    value = os.getenv("SESSION_REDIS_FALLBACK", SESSION_REDIS_FALLBACK).strip().lower()
    return value if value in {"degrade", "strict"} else "degrade"


def _session_redis():
    """会话共享存储的客户端（复用历史记忆那套 Redis 连接配置）。

    单独抽一层是为了可测：测试里 monkeypatch 这个函数就能模拟 Redis 故障。
    """
    return _redis()


def _memory_session(session_key: str) -> WorkingMemory:
    if session_key not in sessions:
        sessions[session_key] = WorkingMemory(session_id=session_key)
    return sessions[session_key]


def get_session(user_id: int, session_id: str) -> WorkingMemory:
    """按 user_id + session_id 取隔离会话对象。"""
    session_key = session_namespace(user_id, session_id)
    if _session_backend() != "redis":
        return _memory_session(session_key)

    mem = _redis_sessions.get(session_key)
    if mem is None:
        strict = _session_redis_fallback() == "strict"
        try:
            client = _session_redis()
        except Exception as exc:
            LOGGER.warning("session redis client unavailable session_key=%s: %s", session_key, exc)
            if strict:
                raise SessionStoreUnavailable("redis session client unavailable") from exc
            return _memory_session(session_key)
        mem = RedisWorkingMemory(session_key, client, strict=strict)
        _redis_sessions[session_key] = mem
    return mem


def _acquire_local_session_turn(session_key: str) -> SessionTurnLease:
    with _SESSION_TURN_LOCKS_GUARD:
        lock = _SESSION_TURN_LOCKS.setdefault(session_key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise SessionTurnBusy(f"session turn already running: {session_key}")
    return SessionTurnLease(session_key, local_lock=lock)


def acquire_session_turn(user_id: int, session_id: str) -> SessionTurnLease:
    """获取会话级单飞锁；Redis 后端优先使用跨 worker 的 SET NX 锁。"""
    session_key = session_namespace(user_id, session_id)
    if _session_backend() == "redis":
        strict = _session_redis_fallback() == "strict"
        try:
            client = _session_redis()
            token = uuid.uuid4().hex
            lock_key = f"{_SESSION_TURN_LOCK_PREFIX}{session_key}"
            acquired = client.set(
                lock_key,
                token,
                nx=True,
                ex=_SESSION_TURN_LOCK_TTL_SECONDS,
            )
            if not acquired:
                raise SessionTurnBusy(f"session turn already running: {session_key}")
            return SessionTurnLease(
                lock_key,
                redis_client=client,
                redis_token=token,
            )
        except SessionTurnBusy:
            raise
        except Exception as exc:
            LOGGER.warning("session turn redis lock unavailable session_key=%s: %s", session_key, exc)
            if strict:
                raise SessionStoreUnavailable("redis session turn lock unavailable") from exc
    return _acquire_local_session_turn(session_key)


def reset_sessions() -> None:
    """清空本进程的会话缓存（测试用；不动 Redis 里的数据）。"""
    sessions.clear()
    _redis_sessions.clear()
    with _SESSION_TURN_LOCKS_GUARD:
        _SESSION_TURN_LOCKS.clear()


def session_backend_status() -> dict:
    """给 /api/ai/health 和排障用：配置的后端 + 本进程的真实情况。

    会话降级是"每个 session 对象各自记录"的（Redis 可能只挂了一段时间），
    所以这里统计本进程已构造的 Redis 会话里有几条真的降级过 —— 数字大于 0
    就说明 SESSION_BACKEND=redis 名义上开着、实际上在走进程内记忆。
    """
    backend = _session_backend()
    if backend == "redis":
        cached = len(_redis_sessions)
        degraded = sum(1 for m in _redis_sessions.values() if getattr(m, "_degraded", False))
        effective = "memory" if cached and degraded == cached else "redis"
    else:
        cached = len(sessions)
        degraded = 0
        effective = "memory"
    return {
        "configured": backend,
        "effective": effective,
        "ttl_seconds": SESSION_REDIS_TTL_SECONDS,
        "fallback": _session_redis_fallback(),
        "cached_sessions": cached,
        "degraded_sessions": degraded,
    }


# ====== Historical Memory (按用户持久化) ======

def _mysql_connection():
    """从共享池取连接（见 tools/db_pool.py）；用完 _mysql_release()。

    原来每次新建连接 + 5s 超时：超时仍是 10s 级别的兜底，但省掉每次 ~45ms 握手。
    """
    return db_pool.pool().acquire()


def _mysql_release(conn):
    db_pool.pool().release(conn)


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
            _mysql_release(conn)
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
            _mysql_release(conn)
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
