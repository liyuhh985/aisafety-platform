# -*- coding: utf-8 -*-
"""AI 建任务 MQ + Outbox（Python 侧）单测。

不连真实 MySQL、不连 RabbitMQ：用假连接 + 假 publisher。
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import hazard_create_queue as q


# ---------------------------------------------------------------- 纯函数

def test_new_request_id_is_prefixed_and_unique():
    a, b = q.new_request_id(), q.new_request_id()
    assert a.startswith("req-") and b.startswith("req-")
    assert a != b and len(a) > 8


def test_backoff_grows_and_is_capped():
    assert q.backoff_seconds(0) == 30
    assert q.backoff_seconds(1) == 60
    assert q.backoff_seconds(3) == 240
    assert q.backoff_seconds(99) == 3600
    assert q.backoff_seconds(-5) == 30


def test_build_message_keeps_request_id_and_payload_fields():
    msg = q.build_message("req-1", 10, "s1", {"category": "fire/x", "severity": 1})
    assert msg["requestId"] == "req-1"
    assert msg["userId"] == 10 and msg["sessionId"] == "s1"
    assert msg["category"] == "fire/x" and msg["severity"] == 1
    assert "createdAt" in msg


def test_status_payload_mapping():
    assert q.status_payload(q.REQ_PENDING)["message"] == "任务创建中"
    assert q.status_payload(q.REQ_PUBLISHED)["message"] == "任务创建中"
    ok = q.status_payload(q.REQ_SUCCESS, hazard_id=61)
    assert ok["status"] == "SUCCESS" and ok["hazardId"] == 61 and ok["message"] == "创建成功"
    bad = q.status_payload(q.REQ_FAILED, error_message="boom")
    assert bad["message"] == "boom"


# ---------------------------------------------------------------- 假连接

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        self.conn.current_sql = sql
        if self.conn.fail_on and self.conn.fail_on in sql:
            raise RuntimeError("fake db error")
        flat = " ".join(sql.split())
        if flat.startswith("SELECT") and "ai_hazard_create_outbox" in flat:
            self._rows = list(self.conn.claimable)
            self.rowcount = len(self._rows)
        else:
            self._rows = []
            self.rowcount = 1
        if self.conn.fetchone_queue:
            self._rows = [self.conn.fetchone_queue.pop(0)]

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, claimable=(), fetchone=None, fail_on=None):
        self.executed = []
        self.claimable = list(claimable)
        self.fetchone_queue = [fetchone] if fetchone else []
        self.fail_on = fail_on
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def sql_containing(self, needle):
        return [(s, p) for s, p in self.executed if needle in s]


class FakePublisher(q.Publisher):
    def __init__(self, raise_on_publish=False):
        self.calls = []
        self.raise_on_publish = raise_on_publish
        self.closed = False
        self.keepalives = 0

    def process_data_events(self):
        self.keepalives += 1

    def publish(self, routing_key, body):
        if self.raise_on_publish:
            raise RuntimeError("rabbit down")
        self.calls.append((routing_key, body))

    def close(self):
        self.closed = True


# ---------------------------------------------------------------- 入队

def test_enqueue_writes_request_and_outbox_then_commits():
    conn = FakeConn()
    res = q.enqueue_hazard_create(7, "sess-1", {"category": "fire/x"}, connect=lambda: conn)

    assert res["ok"] is True
    assert res["requestId"].startswith("req-")
    assert res["status"] == q.REQ_PENDING
    assert conn.commits == 1 and conn.rollbacks == 0 and conn.closed is True
    assert conn.sql_containing("INSERT INTO ai_hazard_create_request")
    assert conn.sql_containing("INSERT INTO ai_hazard_create_outbox")
    # outbox.payload 与 request.payload 是同一份消息体，含 requestId
    _, params = conn.sql_containing("INSERT INTO ai_hazard_create_outbox")[0]
    assert res["requestId"] in params[2]


def test_enqueue_missing_user_id_does_not_touch_db():
    res = q.enqueue_hazard_create(None, "s", {}, connect=lambda: (_ for _ in ()).throw(AssertionError("no db")))
    assert res["ok"] is False


def test_enqueue_rolls_back_and_raises_on_failure():
    conn = FakeConn(fail_on="INSERT INTO ai_hazard_create_outbox")
    with pytest.raises(RuntimeError):
        q.enqueue_hazard_create(7, "s", {}, connect=lambda: conn)
    assert conn.rollbacks == 1 and conn.commits == 0


# ---------------------------------------------------------------- 状态查询

def test_get_request_status_maps_row():
    conn = FakeConn(fetchone=(q.REQ_SUCCESS, 61, None))
    body = q.get_request_status("req-1", connect=lambda: conn)
    assert body == {"status": "SUCCESS", "hazardId": 61, "message": "创建成功",
                    "requestId": "req-1"}


def test_get_request_status_none_when_missing():
    assert q.get_request_status("", connect=lambda: FakeConn()) is None


# ---------------------------------------------------------------- Relay

def test_relay_publishes_and_marks_published():
    row = (1, "req-x", '{"requestId":"req-x"}', 0)
    conn = FakeConn(claimable=[row])
    pub = FakePublisher()
    published = q.RelayWorker(pub).run_once(connect=lambda: conn)

    assert published == 1
    assert pub.calls == [(q.HAZARD_CREATE_ROUTING_KEY, '{"requestId":"req-x"}')]
    assert conn.sql_containing("SET status = %s, locked_at = NULL, last_error = NULL")
    assert conn.sql_containing("UPDATE ai_hazard_create_request SET status = %s")


def test_relay_retries_when_publish_fails():
    row = (1, "req-x", "{}", 0)
    conn = FakeConn(claimable=[row])
    published = q.RelayWorker(FakePublisher(raise_on_publish=True)).run_once(connect=lambda: conn)

    assert published == 0
    assert conn.sql_containing("next_retry_time = DATE_ADD")  # RETRY 分支
    assert not conn.sql_containing("last_error = NULL")       # 没标成 PUBLISHED


def test_relay_moves_to_failed_when_retry_cap_reached():
    row = (1, "req-x", "{}", 9)
    conn = FakeConn(claimable=[row])
    published = q.RelayWorker(FakePublisher(raise_on_publish=True), max_retry=10).run_once(
        connect=lambda: conn)

    assert published == 0
    failed = conn.sql_containing("SET status = %s, retry_count = %s, locked_at = NULL, last_error = %s")
    assert failed, "expected outbox -> FAILED"
    assert conn.sql_containing("SET status = %s, error_message = %s")  # request -> FAILED


# ---------------------------------------------------------------- 回执

def test_apply_result_success_updates_status_and_hazard_id():
    conn = FakeConn()
    assert q.apply_result({"requestId": "req-1", "status": "SUCCESS", "hazardId": 61},
                          connect=lambda: conn) is True
    assert conn.commits == 1
    sql, params = conn.sql_containing("SET status = %s, hazard_id = %s")[0]
    assert params[0] == q.REQ_SUCCESS and params[1] == 61


def test_apply_result_failed_records_message():
    conn = FakeConn()
    q.apply_result({"requestId": "req-1", "status": "FAILED", "message": "java boom"},
                   connect=lambda: conn)
    sql, params = conn.sql_containing("SET status = %s, error_message = %s")[0]
    assert params[0] == q.REQ_FAILED and params[1] == "java boom"


def test_apply_result_rejects_bad_message():
    with pytest.raises(ValueError):
        q.apply_result({"requestId": "", "status": "SUCCESS"})
    with pytest.raises(ValueError):
        q.apply_result({"requestId": "r", "status": "WEIRD"})

def test_relay_run_forever_keeps_connection_alive():
    """空闲保活：每轮都要跑 process_data_events，否则心跳超时会被 broker 断连。"""
    import threading
    pub = FakePublisher()
    conn = FakeConn(claimable=[])
    worker = q.RelayWorker(pub, batch_size=1, max_retry=10)
    stop = threading.Event()

    def _stop_soon():
        stop.set()

    t = threading.Timer(0.05, _stop_soon)
    t.start()
    worker.run_forever(stop, connect=lambda: conn)
    t.cancel()
    assert pub.keepalives >= 1

def test_result_queue_declares_dead_letter_exchange():
    class FakeChannel:
        def __init__(self):
            self.queue_declares = []

        def exchange_declare(self, *args, **kwargs):
            pass

        def queue_declare(self, name, **kwargs):
            self.queue_declares.append((name, kwargs))

        def queue_bind(self, *args, **kwargs):
            pass

    ch = FakeChannel()
    q.RabbitPublisher._declare_topology(ch)
    result = [item for item in ch.queue_declares if item[0] == q.HAZARD_RESULT_QUEUE]
    assert len(result) == 1
    assert result[0][1]["arguments"]["x-dead-letter-exchange"] == q.RABBITMQ_DLX


# ---------------------------------------------------------------- Reconciler

def test_reconciler_marks_success_when_java_has_hazard():
    conn = FakeConn()
    ok = q.reconcile_request(
        "req-1", connect=lambda: conn,
        java_status={"found": True, "hazardId": 61})
    assert ok is True
    assert conn.sql_containing("SET status = %s, hazard_id = %s")
    assert conn.commits == 1


def test_reconciler_requeues_when_java_missing():
    conn = FakeConn(claimable=[("PUBLISHED", 0)])
    ok = q.reconcile_request(
        "req-1", connect=lambda: conn,
        java_status={"found": False})
    assert ok is True
    assert conn.sql_containing("next_retry_time = NOW()")
    assert conn.sql_containing("SET status = %s")


def test_reconciler_marks_failed_when_outbox_exhausted():
    conn = FakeConn(claimable=[("FAILED", 10)])
    ok = q.reconcile_request(
        "req-1", connect=lambda: conn,
        java_status={"found": False})
    assert ok is True
    assert conn.sql_containing("SET status = %s, error_message = %s")


def test_reconciler_skips_java_query_error():
    conn = FakeConn()
    ok = q.reconcile_request(
        "req-1", connect=lambda: conn,
        java_status={"found": False, "error": "timeout"})
    assert ok is False
    assert conn.executed == []



def test_get_request_status_filters_by_user_id():
    conn = FakeConn(fetchone=(q.REQ_SUCCESS, 61, None))
    body = q.get_request_status("req-1", user_id=7, connect=lambda: conn)
    assert body["requestId"] == "req-1"
    sql, params = conn.executed[-1]
    assert "AND user_id = %s" in sql
    assert params == ("req-1", 7)


def test_retention_no_rows_returns_zero():
    conn = FakeConn(claimable=[])
    worker = q.RequestRetentionWorker(batch_size=10)
    assert worker.run_once(connect=lambda: conn) == 0
    assert conn.commits == 1
