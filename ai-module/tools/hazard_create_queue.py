# -*- coding: utf-8 -*-
"""AI 建任务 MQ + Outbox（Python 生产侧）。

三块职责，设计见 docs/current/ai-hazard-create-mq.md：

  1. enqueue_hazard_create()  用户确认后，**事务内**写 request + outbox，再返回 accepted
  2. get_request_status()     前端轮询
  3. RelayWorker / ResultConsumer  后台：把 outbox 发到 RabbitMQ / 收回执更新状态

边界（硬约束）：
  - ai_hazard_create_request / ai_hazard_create_outbox 只有 Python 写；
  - Python 不写 tb_hazard，Java 不写 ai_* 表。

导入本模块**不依赖 pika**（在 RabbitPublisher 里延迟 import），
所以没有 RabbitMQ 的机器也能跑单测。
"""
import json
import os
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta

import pymysql

from db_config import DB_CONFIG
from tools import db_pool
from config import (
    RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_VHOST,
    RABBITMQ_EXCHANGE, RABBITMQ_DLX,
    HAZARD_CREATE_QUEUE, HAZARD_CREATE_ROUTING_KEY, HAZARD_CREATE_DLQ,
    HAZARD_RESULT_QUEUE, HAZARD_RESULT_ROUTING_KEY,
    HAZARD_OUTBOX_POLL_SECONDS, HAZARD_OUTBOX_BATCH_SIZE,
    HAZARD_OUTBOX_MAX_RETRY, HAZARD_OUTBOX_LOCK_SECONDS,
    HAZARD_RECONCILE_AFTER_SECONDS, HAZARD_RECONCILE_BATCH_SIZE,
    HAZARD_RECONCILE_POLL_SECONDS,
)

LOGGER = logging.getLogger("safety.ai.hazard_queue")

# ---- request.status ----
REQ_PENDING = "PENDING"        # request+outbox 已写，还没发 MQ
REQ_PUBLISHED = "PUBLISHED"    # 已成功投递到 RabbitMQ
REQ_SUCCESS = "SUCCESS"        # Java 回执：已落 tb_hazard
REQ_FAILED = "FAILED"          # 最终失败
TERMINAL_REQUEST_STATUS = (REQ_SUCCESS, REQ_FAILED)

# ---- outbox.status ----
OB_PENDING = "PENDING"
OB_PUBLISHING = "PUBLISHING"   # 已被某个 relay 实例认领（in-flight）
OB_PUBLISHED = "PUBLISHED"
OB_RETRY = "RETRY"
OB_FAILED = "FAILED"

EVENT_TYPE = "HAZARD_CREATE_REQUESTED"
MSG_MAX_ERROR = 1000


# ============================================================
# 连接 / 纯函数（可单测）
# ============================================================

def _release(conn) -> None:
    """归还连接到共享池（见 tools/db_pool.py）。"""
    db_pool.pool().release(conn)


def _connect():
    """从共享池取一个 autocommit=False 的连接；调用方用完必须 _release(conn)。"""
    return db_pool.pool().acquire()


def new_request_id() -> str:
    return "req-" + uuid.uuid4().hex


def _existing_request_result(row, user_id, session_id):
    """把已有 request 行转成幂等返回；归属不一致时拒绝复用。"""
    if not row:
        return None
    request_id, status, hazard_id, error_message, owner_id, owner_session = row
    if owner_id != user_id:
        return {"ok": False, "message": "request confirmation id conflict"}
    if owner_session and session_id and owner_session != session_id:
        return {"ok": False, "message": "request confirmation id session conflict"}
    body = status_payload(status, hazard_id=hazard_id, error_message=error_message)
    return {
        "ok": True,
        "requestId": request_id,
        "status": status,
        "hazardId": hazard_id,
        "message": body["message"],
        "idempotent": True,
    }


def _select_existing_request(cur, request_id):
    cur.execute(
        "SELECT request_id, status, hazard_id, error_message, user_id, session_id "
        "FROM ai_hazard_create_request WHERE request_id = %s LIMIT 1",
        (request_id,),
    )
    return cur.fetchone()


def backoff_seconds(retry_count: int) -> int:
    """退避：30 * 2^n，上限 3600s。与 Java 现有 outbox 语义一致。"""
    exponent = max(0, min(int(retry_count), 30))
    return int(min(30 * (1 << exponent), 3600))


def build_message(request_id: str, user_id, session_id, payload: dict) -> dict:
    """组装投递到 MQ 的消息体（也落进 outbox.payload）。"""
    message = {
        "requestId": request_id,
        "userId": user_id,
        "sessionId": session_id,
        "createdAt": datetime.now().isoformat(timespec="seconds"),
    }
    for key, value in (payload or {}).items():
        message.setdefault(key, value)
    return message


def status_payload(status: str, hazard_id=None, error_message=None) -> dict:
    """把 request 行转成前端状态接口的返回体。"""
    if status == REQ_SUCCESS:
        message = "创建成功"
    elif status == REQ_FAILED:
        message = error_message or "创建失败"
    else:
        message = "任务创建中"
    return {
        "status": status,
        "hazardId": hazard_id,
        "message": message,
    }


def _truncate(text, limit: int = MSG_MAX_ERROR) -> str:
    value = "" if text is None else str(text)
    return value if len(value) <= limit else value[:limit]


# ============================================================
# 1. 入队：先写库，再返回 accepted
# ============================================================

def enqueue_hazard_create(user_id, session_id, payload: dict, *, request_id=None,
                          connect=None) -> dict:
    """事务内写 request + outbox；提交成功后才返回 accepted。

    返回 {"ok": True, "requestId": ..., "status": "PENDING"}。
    任何异常都不返回 accepted —— 否则用户看到"已受理"但任务永远不会创建。
    """
    if user_id is None:
        return {"ok": False, "message": "缺少 user_id，无法建单"}
    request_id = str(request_id or "").strip() or new_request_id()
    if len(request_id) > 64:
        return {"ok": False, "message": "request id too long"}
    message = build_message(request_id, user_id, session_id or "", payload)
    message_json = json.dumps(message, ensure_ascii=False)

    conn = (connect or _connect)()
    try:
        with conn.cursor() as cur:
            existing = _select_existing_request(cur, request_id)
            if existing:
                result = _existing_request_result(existing, user_id, session_id or "")
                conn.rollback()
                return result
            cur.execute(
                "INSERT INTO ai_hazard_create_request "
                "(request_id, user_id, session_id, payload, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (request_id, user_id, session_id or "", message_json, REQ_PENDING),
            )
            cur.execute(
                "INSERT INTO ai_hazard_create_outbox "
                "(request_id, event_type, payload, status, next_retry_time) "
                "VALUES (%s, %s, %s, %s, NOW())",
                (request_id, EVENT_TYPE, message_json, OB_PENDING),
            )
        conn.commit()
    except pymysql.err.IntegrityError:
        # 两个确认请求并发使用同一 requestId：回滚后回查赢家，返回同一请求。
        conn.rollback()
        with conn.cursor() as cur:
            existing = _select_existing_request(cur, request_id)
        result = _existing_request_result(existing, user_id, session_id or "")
        if result:
            return result
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)

    LOGGER.info("hazard create accepted request_id=%s user_id=%s", request_id, user_id)
    return {"ok": True, "requestId": request_id, "status": REQ_PENDING}


# ============================================================
# 2. 状态查询
# ============================================================

def get_request_status(request_id: str, *, user_id=None, connect=None):
    """返回前端状态体；找不到或不属于该 user_id 时返回 None。"""
    if not request_id:
        return None
    sql = ("SELECT status, hazard_id, error_message FROM ai_hazard_create_request "
           "WHERE request_id = %s")
    params = [request_id]
    if user_id is not None:
        sql += " AND user_id = %s"
        params.append(user_id)
    conn = (connect or _connect)()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
    finally:
        _release(conn)
    if not row:
        return None
    body = status_payload(row[0], row[1], row[2])
    body["requestId"] = request_id
    return body


# ============================================================
# 3a. Relay（outbox -> RabbitMQ）
# ============================================================

class Publisher:
    """投递接口；测试可注入假实现。"""

    def publish(self, routing_key: str, body: str) -> None:  # pragma: no cover - 接口
        raise NotImplementedError

    def process_data_events(self) -> None:
        """保活钩子：空闲时也要跑，否则心跳发不出去会被 broker 断连。"""
        pass

    def close(self) -> None:  # pragma: no cover - 接口
        pass


class RabbitPublisher(Publisher):
    """pika 发布器：连接懒建立，失败时丢弃连接由下次重连。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._conn = None
        self._channel = None

    def _ensure(self):
        if (self._channel is not None and self._conn is not None
                and self._conn.is_open and self._channel.is_open):
            return self._channel
        import pika  # 延迟导入：没装 pika 也不影响 import 本模块

        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        params = pika.ConnectionParameters(
            host=RABBITMQ_HOST, port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST, credentials=credentials,
            heartbeat=30, blocked_connection_timeout=10,
            # 关键：没有 socket 超时，半开连接上的 basic_publish 会永久阻塞
            socket_timeout=10,
        )
        self._conn = pika.BlockingConnection(params)
        channel = self._conn.channel()
        self._declare_topology(channel)
        # 发布确认：basic_publish 返回 == broker 已接收；没有它就有丢消息窗口
        channel.confirm_delivery()
        self._channel = channel
        return channel

    def process_data_events(self) -> None:
        """空闲保活：把心跳跑出去，避免 broker 因心跳超时断连。"""
        if self._conn is None or self._channel is None:
            return
        try:
            if self._conn.is_open:
                self._conn.process_data_events(time_limit=0)
        except Exception:
            self.close()

    @staticmethod
    def _declare_topology(channel):
        """与 Java 侧 RabbitConfig 声明完全一致（幂等；不一致会 406）。"""
        channel.exchange_declare(RABBITMQ_EXCHANGE, exchange_type="topic", durable=True)
        channel.exchange_declare(RABBITMQ_DLX, exchange_type="topic", durable=True)
        channel.queue_declare(
            HAZARD_CREATE_QUEUE, durable=True,
            arguments={"x-dead-letter-exchange": RABBITMQ_DLX},
        )
        channel.queue_bind(HAZARD_CREATE_QUEUE, RABBITMQ_EXCHANGE, HAZARD_CREATE_ROUTING_KEY)
        channel.queue_declare(HAZARD_CREATE_DLQ, durable=True)
        channel.queue_bind(HAZARD_CREATE_DLQ, RABBITMQ_DLX, "#")
        channel.queue_declare(
            HAZARD_RESULT_QUEUE, durable=True,
            arguments={"x-dead-letter-exchange": RABBITMQ_DLX},
        )
        channel.queue_bind(HAZARD_RESULT_QUEUE, RABBITMQ_EXCHANGE, HAZARD_RESULT_ROUTING_KEY)

    def publish(self, routing_key: str, body: str) -> None:
        import pika

        with self._lock:
            try:
                channel = self._ensure()
                channel.basic_publish(
                    exchange=RABBITMQ_EXCHANGE,
                    routing_key=routing_key,
                    body=body.encode("utf-8"),
                    # mandatory：路由不到队列时抛 UnroutableError（配合 confirm 才有效）
                    mandatory=True,
                    properties=pika.BasicProperties(delivery_mode=2),
                )
            except Exception:
                # 连接可能已坏：丢掉，下次重建
                self.close()
                raise

    def close(self) -> None:
        try:
            if self._conn is not None and self._conn.is_open:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
        self._channel = None


class RelayWorker:
    """扫 outbox -> 发 MQ -> 标 PUBLISHED / RETRY / FAILED。"""

    def __init__(self, publisher: Publisher = None, *,
                 batch_size=None, max_retry=None, stale_seconds=None, logger=None):
        self.publisher = publisher or RabbitPublisher()
        self.batch_size = batch_size or HAZARD_OUTBOX_BATCH_SIZE
        self.max_retry = max_retry or HAZARD_OUTBOX_MAX_RETRY
        self.stale_seconds = stale_seconds or HAZARD_OUTBOX_LOCK_SECONDS
        self.logger = logger or LOGGER

    def run_once(self, *, connect=None) -> int:
        conn = (connect or _connect)()
        published = 0
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, request_id, payload, retry_count "
                    "FROM ai_hazard_create_outbox "
                    "WHERE ((status IN (%s, %s) AND next_retry_time <= NOW()) "
                    "   OR (status = %s AND locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND))) "
                    "  AND retry_count < %s "
                    "ORDER BY id LIMIT %s",
                    (OB_PENDING, OB_RETRY, OB_PUBLISHING, self.stale_seconds,
                     self.max_retry, self.batch_size),
                )
                rows = cur.fetchall()
            if not rows:
                return 0

            row_ids = [row[0] for row in rows]
            claimed_ids = self._claim_batch(conn, row_ids)
            if len(claimed_ids) != len(row_ids):
                claimed_ids = [rid for rid in row_ids if self._claim(conn, rid)]

            successes = []
            for row_id, request_id, payload, retry_count in rows:
                if row_id not in claimed_ids:
                    continue
                try:
                    self.publisher.publish(HAZARD_CREATE_ROUTING_KEY, payload)
                except Exception as exc:  # noqa: BLE001
                    self._mark_retry(conn, row_id, request_id, retry_count, exc)
                    self.logger.warning(
                        "outbox publish failed id=%s request=%s retry=%s err=%s",
                        row_id, request_id, retry_count, exc)
                    continue
                successes.append((row_id, request_id))
            if successes:
                self._mark_published_batch(conn, successes)
                published = len(successes)
        finally:
            _release(conn)
        return published

    def run_forever(self, stop_event=None, *, connect=None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                self.publisher.process_data_events()   # 空闲保活（否则心跳超时被断连）
                self.run_once(connect=connect)
            except Exception:  # noqa: BLE001
                self.logger.exception("relay run_once failed")
            stop.wait(HAZARD_OUTBOX_POLL_SECONDS)

    # ---- 带条件更新的 claim / 状态迁移（各自独立事务，语义同 Java outbox）----

    def _claim(self, conn, row_id) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ai_hazard_create_outbox "
                "SET status = %s, locked_at = NOW() "
                "WHERE id = %s "
                "  AND ((status IN (%s, %s) AND next_retry_time <= NOW()) "
                "    OR (status = %s AND locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND))) "
                "  AND retry_count < %s",
                (OB_PUBLISHING, row_id, OB_PENDING, OB_RETRY, OB_PUBLISHING,
                 self.stale_seconds, self.max_retry),
            )
            claimed = cur.rowcount == 1
        conn.commit()
        return claimed

    def _claim_batch(self, conn, row_ids) -> list:
        if not row_ids:
            return []
        placeholders = ",".join(["%s"] * len(row_ids))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ai_hazard_create_outbox "
                "SET status = %s, locked_at = NOW() "
                "WHERE id IN (" + placeholders + ") "
                "  AND ((status IN (%s, %s) AND next_retry_time <= NOW()) "
                "    OR (status = %s AND locked_at < DATE_SUB(NOW(), INTERVAL %s SECOND))) "
                "  AND retry_count < %s",
                (OB_PUBLISHING, *row_ids, OB_PENDING, OB_RETRY, OB_PUBLISHING,
                 self.stale_seconds, self.max_retry),
            )
            claimed = cur.rowcount == len(row_ids)
        conn.commit()
        return list(row_ids) if claimed else []

    def _mark_published(self, conn, row_id, request_id) -> None:
        self._mark_published_batch(conn, [(row_id, request_id)])

    def _mark_published_batch(self, conn, pairs) -> None:
        if not pairs:
            return
        row_ids = [item[0] for item in pairs]
        request_ids = [item[1] for item in pairs]
        row_ph = ",".join(["%s"] * len(row_ids))
        req_ph = ",".join(["%s"] * len(request_ids))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ai_hazard_create_outbox "
                "SET status = %s, locked_at = NULL, last_error = NULL "
                "WHERE id IN (" + row_ph + ")",
                (OB_PUBLISHED, *row_ids),
            )
            cur.execute(
                "UPDATE ai_hazard_create_request SET status = %s "
                "WHERE request_id IN (" + req_ph + ") AND status = %s",
                (REQ_PUBLISHED, *request_ids, REQ_PENDING),
            )
        conn.commit()

    def _mark_retry(self, conn, row_id, request_id, previous_retry, exc) -> None:
        next_retry = previous_retry + 1
        error = _truncate(exc)
        with conn.cursor() as cur:
            if next_retry >= self.max_retry:
                cur.execute(
                    "UPDATE ai_hazard_create_outbox "
                    "SET status = %s, retry_count = %s, locked_at = NULL, last_error = %s "
                    "WHERE id = %s",
                    (OB_FAILED, next_retry, error, row_id),
                )
                cur.execute(
                    "UPDATE ai_hazard_create_request "
                    "SET status = %s, error_message = %s "
                    "WHERE request_id = %s AND status <> %s",
                    (REQ_FAILED, error, request_id, REQ_SUCCESS),
                )
            else:
                delay = backoff_seconds(previous_retry)
                cur.execute(
                    "UPDATE ai_hazard_create_outbox "
                    "SET status = %s, retry_count = %s, locked_at = NULL, last_error = %s, "
                    "    next_retry_time = DATE_ADD(NOW(), INTERVAL %s SECOND) "
                    "WHERE id = %s",
                    (OB_RETRY, next_retry, error, delay, row_id),
                )
        conn.commit()


# ============================================================
# 3b. ResultConsumer（Java 回执 -> 更新 Python 侧状态）
# ============================================================

def apply_result(message: dict, *, connect=None) -> bool:
    """处理一条 Java 回执。幂等：已终态不再改。返回是否命中已有请求。"""
    request_id = str((message or {}).get("requestId") or "").strip()
    status = str((message or {}).get("status") or "").strip().upper()
    if not request_id or status not in TERMINAL_REQUEST_STATUS:
        raise ValueError("invalid result message: %r" % (message,))

    conn = (connect or _connect)()
    try:
        with conn.cursor() as cur:
            if status == REQ_SUCCESS:
                cur.execute(
                    "UPDATE ai_hazard_create_request "
                    "SET status = %s, hazard_id = %s, error_message = NULL "
                    "WHERE request_id = %s AND status <> %s",
                    (REQ_SUCCESS, message.get("hazardId"), request_id, REQ_SUCCESS),
                )
            else:
                cur.execute(
                    "UPDATE ai_hazard_create_request "
                    "SET status = %s, error_message = %s "
                    "WHERE request_id = %s AND status <> %s",
                    (REQ_FAILED, _truncate(message.get("message") or "创建失败"),
                     request_id, REQ_SUCCESS),
                )
            hit = cur.rowcount
        conn.commit()
        return hit > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


class ResultConsumer:
    """消费 hazard.create.result.q，更新 Python 侧 request 状态。"""

    def __init__(self, *, connect=None, logger=None):
        self.connect = connect
        self.logger = logger or LOGGER

    def run_forever(self, stop_event=None) -> None:
        import pika  # 延迟导入

        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        params = pika.ConnectionParameters(
            host=RABBITMQ_HOST, port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST, credentials=credentials,
            heartbeat=30, blocked_connection_timeout=10,
        )
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                conn = pika.BlockingConnection(params)
                channel = conn.channel()
                RabbitPublisher._declare_topology(channel)
                channel.basic_qos(prefetch_count=16)

                def _on_message(ch, method, properties, body):
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        apply_result(payload, connect=self.connect)
                        ch.basic_ack(method.delivery_tag)
                    except Exception:  # noqa: BLE001
                        self.logger.exception("hazard result handling failed; drop to DLQ")
                        ch.basic_nack(method.delivery_tag, requeue=False)

                channel.basic_consume(
                    queue=HAZARD_RESULT_QUEUE, on_message_callback=_on_message)
                while not stop.is_set():
                    conn.process_data_events(time_limit=1)
                channel.close()
                conn.close()
            except Exception:  # noqa: BLE001
                self.logger.exception("hazard result consumer loop error; retry in 5s")
                stop.wait(5)



# ============================================================
# 3c. RequestReconciler（超时行 -> Java 真实落库结果）
# ============================================================

def _request_java_status(request_id: str) -> dict:
    """查 Java 内部接口：该 request_id 是否已经落 tb_hazard。"""
    from tools.java_client import hazard_create_result
    return hazard_create_result(request_id)


def reconcile_request(request_id: str, *, connect=None, java_status=None) -> bool:
    """对账单条 request。

    规则：
    - Java 已查到 tb_hazard -> request 补 SUCCESS + hazard_id；
    - Java 查不到，但 outbox 还有重试余额 -> outbox 改 RETRY，request 回 PENDING，下一轮 Relay 重投；
    - outbox 已 FAILED / 重试耗尽 -> request FAILED；
    - Java 查询本身报错 -> 本轮跳过，不误判。
    """
    if not request_id:
        return False
    status = java_status if java_status is not None else _request_java_status(request_id)
    if status.get("error"):
        return False

    conn = (connect or _connect)()
    try:
        with conn.cursor() as cur:
            if status.get("found") and status.get("hazardId") is not None:
                cur.execute(
                    "UPDATE ai_hazard_create_request "
                    "SET status = %s, hazard_id = %s, error_message = NULL "
                    "WHERE request_id = %s AND status IN (%s, %s)",
                    (REQ_SUCCESS, status.get("hazardId"), request_id,
                     REQ_PENDING, REQ_PUBLISHED),
                )
                conn.commit()
                return cur.rowcount > 0

            cur.execute(
                "SELECT status, retry_count FROM ai_hazard_create_outbox "
                "WHERE request_id = %s",
                (request_id,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "UPDATE ai_hazard_create_request SET status = %s, error_message = %s "
                    "WHERE request_id = %s AND status IN (%s, %s)",
                    (REQ_FAILED, "outbox missing", request_id, REQ_PENDING, REQ_PUBLISHED),
                )
                conn.commit()
                return cur.rowcount > 0

            ob_status, retry_count = row[0], int(row[1] or 0)
            if ob_status == OB_FAILED or retry_count >= HAZARD_OUTBOX_MAX_RETRY:
                cur.execute(
                    "UPDATE ai_hazard_create_request SET status = %s, error_message = %s "
                    "WHERE request_id = %s AND status IN (%s, %s)",
                    (REQ_FAILED, "reconcile exhausted", request_id,
                     REQ_PENDING, REQ_PUBLISHED),
                )
                conn.commit()
                return cur.rowcount > 0

            cur.execute(
                "UPDATE ai_hazard_create_outbox "
                "SET status = %s, next_retry_time = NOW(), locked_at = NULL "
                "WHERE request_id = %s",
                (OB_RETRY, request_id),
            )
            cur.execute(
                "UPDATE ai_hazard_create_request SET status = %s "
                "WHERE request_id = %s AND status IN (%s, %s)",
                (REQ_PENDING, request_id, REQ_PENDING, REQ_PUBLISHED),
            )
            conn.commit()
            return True
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


class RequestReconciler:
    """定时扫描超时未终态的 request，防止 PUBLISHED 永久卡死。"""

    def __init__(self, *, connect=None, logger=None,
                 after_seconds=None, batch_size=None, poll_seconds=None):
        self.connect = connect
        self.logger = logger or LOGGER
        self.after_seconds = after_seconds or HAZARD_RECONCILE_AFTER_SECONDS
        self.batch_size = batch_size or HAZARD_RECONCILE_BATCH_SIZE
        self.poll_seconds = poll_seconds or HAZARD_RECONCILE_POLL_SECONDS

    def run_once(self, *, connect=None) -> int:
        conn = (self.connect or connect or _connect)()
        reconciled = 0
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT r.request_id "
                    "FROM ai_hazard_create_request r "
                    "JOIN ai_hazard_create_outbox o ON o.request_id = r.request_id "
                    "WHERE r.status IN (%s, %s) "
                    "  AND r.updated_at < DATE_SUB(NOW(), INTERVAL %s SECOND) "
                    "ORDER BY r.updated_at LIMIT %s",
                    (REQ_PENDING, REQ_PUBLISHED, self.after_seconds, self.batch_size),
                )
                rows = cur.fetchall()
            for (request_id,) in rows:
                try:
                    if reconcile_request(request_id, connect=conn):
                        reconciled += 1
                except Exception:  # noqa: BLE001
                    self.logger.exception("reconcile request failed request_id=%s", request_id)
        finally:
            _release(conn)
        return reconciled

    def run_forever(self, stop_event=None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:  # noqa: BLE001
                self.logger.exception("request reconciler loop error")
            stop.wait(self.poll_seconds)


# ============================================================
# 3d. MetricsReporter（Outbox / Request 指标打点）
# ============================================================

HAZARD_METRICS_INTERVAL_SECONDS = float(
    os.getenv("HAZARD_METRICS_INTERVAL_SECONDS", "60"))


def metrics_snapshot(*, connect=None) -> dict:
    """返回 request/outbox 各状态计数与卡单计数，供 worker 周期打日志。"""
    conn = (connect or _connect)()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) FROM ai_hazard_create_request GROUP BY status")
            request_counts = {str(row[0]): int(row[1]) for row in (cur.fetchall() or [])}
            cur.execute(
                "SELECT status, COUNT(*) FROM ai_hazard_create_outbox GROUP BY status")
            outbox_counts = {str(row[0]): int(row[1]) for row in (cur.fetchall() or [])}
            cur.execute(
                "SELECT COUNT(*) FROM ai_hazard_create_request "
                "WHERE status IN (%s, %s) "
                "AND updated_at < DATE_SUB(NOW(), INTERVAL %s SECOND)",
                (REQ_PENDING, REQ_PUBLISHED, HAZARD_RECONCILE_AFTER_SECONDS),
            )
            row = cur.fetchone()
            stuck = int(row[0]) if row else 0
    finally:
        _release(conn)
    return {"request": request_counts, "outbox": outbox_counts, "stuck": stuck}


class MetricsReporter:
    """周期性把 MQ 状态打进日志；无外部 metrics 系统时这是最直接的观测面。"""

    def __init__(self, *, interval_seconds=None, logger=None):
        self.interval = interval_seconds or HAZARD_METRICS_INTERVAL_SECONDS
        self.logger = logger or LOGGER

    def run_forever(self, stop_event=None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                snap = metrics_snapshot()
                self.logger.info(
                    "hazard_create_metrics request=%s outbox=%s stuck=%s",
                    snap["request"], snap["outbox"], snap["stuck"])
            except Exception:  # noqa: BLE001
                self.logger.exception("hazard create metrics failed")
            stop.wait(self.interval)


# ============================================================
# 3e. RequestRetentionWorker（历史归档 + 清理）
# ============================================================

REQUEST_ARCHIVE_TABLE = "ai_hazard_create_request_archive"
OUTBOX_ARCHIVE_TABLE = "ai_hazard_create_outbox_archive"
RETENTION_SUCCESS_DAYS = int(os.getenv("HAZARD_RETENTION_SUCCESS_DAYS", "90"))
RETENTION_FAILED_DAYS = int(os.getenv("HAZARD_RETENTION_FAILED_DAYS", "180"))
RETENTION_OUTBOX_DAYS = int(os.getenv("HAZARD_RETENTION_OUTBOX_DAYS", "30"))
RETENTION_BATCH_SIZE = int(os.getenv("HAZARD_RETENTION_BATCH_SIZE", "500"))
RETENTION_INTERVAL_SECONDS = float(os.getenv("HAZARD_RETENTION_INTERVAL_SECONDS", "3600"))


class RequestRetentionWorker:
    """把终态 request / 已投递 outbox 搬到 archive 表并删除原行。"""

    def __init__(self, *, connect=None, logger=None, batch_size=None):
        self.connect = connect
        self.logger = logger or LOGGER
        self.batch_size = batch_size or RETENTION_BATCH_SIZE

    def _move(self, conn, src_table: str, dst_table: str, id_col: str,
              where_sql: str, params: tuple) -> int:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {id_col} FROM {src_table} WHERE {where_sql} LIMIT %s",
                (*params, self.batch_size),
            )
            ids = [row[0] for row in (cur.fetchall() or [])]
            if not ids:
                return 0
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"INSERT IGNORE INTO {dst_table} SELECT * FROM {src_table} "
                f"WHERE {id_col} IN ({placeholders})",
                tuple(ids),
            )
            cur.execute(
                f"DELETE FROM {src_table} WHERE {id_col} IN ({placeholders})",
                tuple(ids),
            )
            return len(ids)

    def run_once(self, *, connect=None) -> int:
        conn = (self.connect or connect or _connect)()
        moved = 0
        try:
            moved += self._move(
                conn, "ai_hazard_create_request", REQUEST_ARCHIVE_TABLE, "request_id",
                "status = %s AND updated_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
                (REQ_SUCCESS, RETENTION_SUCCESS_DAYS),
            )
            moved += self._move(
                conn, "ai_hazard_create_request", REQUEST_ARCHIVE_TABLE, "request_id",
                "status = %s AND updated_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
                (REQ_FAILED, RETENTION_FAILED_DAYS),
            )
            moved += self._move(
                conn, "ai_hazard_create_outbox", OUTBOX_ARCHIVE_TABLE, "id",
                "status = %s AND updated_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
                (OB_PUBLISHED, RETENTION_OUTBOX_DAYS),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _release(conn)
        return moved

    def run_forever(self, stop_event=None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                moved = self.run_once()
                if moved:
                    self.logger.info("hazard create retention moved=%s", moved)
            except Exception:  # noqa: BLE001
                self.logger.exception("hazard create retention failed")
            stop.wait(RETENTION_INTERVAL_SECONDS)
