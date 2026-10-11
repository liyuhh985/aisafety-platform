#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AI 建任务 MQ 高并发压测脚本（Task 9）。

对应计划：docs/superpowers/plans/2026-10-10-ai-hazard-mq-hardening.md
证据模板：docs/evidence/2026-10-11-hazard-create-mq-load.md

做什么
======
在没有真实前端的情况下模拟 N 个用户「确认建单」，然后轮询 Python 侧状态表
ai_hazard_create_request 直到终态，统计：

    SUCCESS / FAILED / TIMEOUT / duplicate / p50 / p95 / p99

两种投递模式（--mode）
======================
outbox  默认，与生产链路一致：enqueue_hazard_create() 事务内写 request + outbox，
        由 hazard_create_worker.py 的 Relay 投递到 RabbitMQ。
        前提：relay + ResultConsumer + Java 消费者都在跑。

direct  只写 request 行，然后本脚本自己把消息直接发到 RabbitMQ
        （需要 pika + broker 可达）。用于把 relay 排除在外，
        单独压「Java 消费 + 回执」这一段。

安全须知（先读再跑）
====================
1. 会往 DB_CONFIG 指向的库写数据。默认只允许本机 / 内网地址；连远程库必须显式
   加 --allow-remote，避免误压生产库。
2. 想压本地 / 预发库：先设环境变量再运行（db_config 用 os.environ.setdefault，
   真实环境变量优先于 ai-module/.env）：

       PowerShell:  $env:DB_HOST='127.0.0.1'
                    python db/load_hazard_create_mq.py --concurrency 10 --total 100

3. --dry-run 只生成 payload + 探活，不写任何数据。
4. 脚本只碰 ai_hazard_create_* 两张表（Python 侧）；Java 侧 tb_hazard 一律只读
   校验，不删。清理 SQL 由 --print-cleanup 打印。

用法
====
    python db/load_hazard_create_mq.py --dry-run
    python db/load_hazard_create_mq.py --concurrency 10 --total 100 --timeout 60
    python db/load_hazard_create_mq.py --concurrency 50 --total 500 --timeout 120 --cleanup
    python db/load_hazard_create_mq.py --mode direct --concurrency 100 --total 1000 \
        --timeout 180 --allow-remote
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from db_config import DB_CONFIG          # noqa: E402  项目唯一 DB 配置来源
from tools import db_pool                # noqa: E402  项目共享连接池
from tools import hazard_create_queue as q  # noqa: E402  项目唯一建单队列实现

try:
    # 类别清单直接取项目 taxonomy，避免压测脚本里再抄一份枚举
    from core.hazard_taxonomy import HAZARD_TAXONOMY, format_hazard_type
except Exception:  # pragma: no cover - taxonomy 不可用时退化成内置四类
    HAZARD_TAXONOMY = ()
    format_hazard_type = None

STATUS_TIMEOUT = 'TIMEOUT'                         # 脚本自定义：超时仍未到终态
TERMINAL_STATUS = set(q.TERMINAL_REQUEST_STATUS)   # SUCCESS / FAILED

DEFAULT_USER_ID_BASE = 990000000   # 明显不属于真实用户的区间，便于事后清理
CHUNK = 500                        # IN (...) 分批大小

# 模拟的地址：固定用三明市，和项目真实业务域一致（地理编码不会在压测里被调用）
_ADDRESSES = (
    '福建省三明市三元区翡翠城小区门口',
    '福建省三明市三元区新市中路 187 号人行道',
    '福建省三明市三元区梅园新村 3 幢消防通道',
    '福建省三明市沙县区虬江街道建设路施工现场',
    '福建省三明市永安市燕东街道解放路 88 号',
)

_DESCRIPTIONS = (
    '压测造数：车辆长期占用通道，行人无法通行',
    '压测造数：井盖破损，存在坠落风险',
    '压测造数：消防通道被杂物堆放占用',
    '压测造数：施工围挡缺失，未设置安全警示',
)

# taxonomy 不可用时的兜底类别（major/subcategory 编码形态，与线上一致）
_FALLBACK_CATEGORIES = (
    'traffic/road_occupancy',
    'municipal/manhole_damage',
    'fire/fire_lane_blocked',
    'construction/no_barrier',
)


def log(message: str = '') -> None:
    """直接写 stdout：压测日志要和进度条一样实时可见。"""
    print(message, flush=True)


def _fmt(value, suffix=''):
    """None -> n/a；数字 -> 保留 3 位。"""
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return '%.3f%s' % (value, suffix)
    return '%s%s' % (value, suffix)


def percentile(values, pct):
    """nearest-rank 百分位；无样本返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    rank = int(math.ceil(pct / 100.0 * len(ordered)))
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return round(ordered[index], 3)


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _placeholders(count: int) -> str:
    return ','.join(['%s'] * count)


def _is_private_host(host: str) -> bool:
    """只允许本机 / 内网直连；其余地址必须 --allow-remote 才动。"""
    value = (host or '').strip().lower()
    if not value:
        return False
    if value in ('localhost', '::1', '0.0.0.0'):
        return True
    if value.startswith('127.') or value.startswith('10.') or value.startswith('192.168.'):
        return True
    if value.startswith('172.'):
        parts = value.split('.')
        if len(parts) > 1:
            try:
                return 16 <= int(parts[1]) <= 31
            except ValueError:
                return False
    return False


def _categories():
    """major/subcategory 编码列表，取自项目 taxonomy。"""
    codes = []
    if format_hazard_type:
        for item in HAZARD_TAXONOMY:
            for sub_code, _label in item.get('subcategories', ()):
                try:
                    codes.append(format_hazard_type(item['code'], sub_code))
                except Exception:  # pragma: no cover - taxonomy 形状变化时别炸
                    continue
    return codes or list(_FALLBACK_CATEGORIES)


class Record:
    """一条压测请求的全生命周期观测点。"""

    __slots__ = ('seq', 'user_id', 'session_id', 'payload', 'request_id', 'body',
                 'status', 'hazard_id', 'error', 'enqueued_at', 'terminal_at')

    def __init__(self, seq, user_id, session_id, payload):
        self.seq = seq
        self.user_id = user_id
        self.session_id = session_id
        self.payload = payload
        self.request_id = ''
        self.body = ''
        self.status = 'SUBMIT_FAILED'   # 提交阶段就失败的，不再是 TIMEOUT
        self.hazard_id = None
        self.error = ''
        self.enqueued_at = 0.0
        self.terminal_at = 0.0

    @property
    def latency(self):
        if self.enqueued_at and self.terminal_at:
            return self.terminal_at - self.enqueued_at
        return None


class LoadRunner:

    def __init__(self, args, tag: str):
        self.args = args
        self.tag = tag
        self.records = []
        self.submit_seconds = 0.0
        self.drain_seconds = 0.0
        self.duplicate_rows = 0
        self.duplicate_ids = []
        self.success_without_row = []
        self.row_without_result = []
        self.depths = None

    # ---------------- 准备 ----------------

    def _build_payloads(self):
        categories = _categories()
        payloads = []
        for seq in range(self.args.total):
            payloads.append({
                'userId': self.args.user_id_base + seq,
                'category': categories[seq % len(categories)],
                'address': _ADDRESSES[seq % len(_ADDRESSES)],
                'district': '福建省三明市',
                'longitude': None,
                'latitude': None,
                'description': _DESCRIPTIONS[seq % len(_DESCRIPTIONS)],
                'severity': seq % 3,
                'imageUrl': '',
                'report': '',
            })
        return payloads

    def _banner(self, payloads):
        target = '%s:%s/%s (user=%s)' % (
            DB_CONFIG.get('host'), DB_CONFIG.get('port'),
            DB_CONFIG.get('database'), DB_CONFIG.get('user'))
        log('=' * 72)
        log('AI 建任务 MQ 压测')
        log('  目标库      : %s' % target)
        log('  tag         : %s' % self.tag)
        log('  模式        : %s' % self.args.mode)
        log('  并发 / 总量  : %s / %s' % (self.args.concurrency, self.args.total))
        log('  超时 / 轮询 : %ss / %ss' % (self.args.timeout, self.args.poll_interval))
        log('  用户 id 区间 : %s .. %s' % (
            self.args.user_id_base, self.args.user_id_base + self.args.total - 1))
        if self.args.dry_run:
            log('  DRY-RUN     : 只生成 payload，不写任何数据')
        log('=' * 72)
        log('payload 示例（第 1 条）：')
        log(json.dumps(payloads[0], ensure_ascii=False, indent=2))
        log()

    # ---------------- 提交阶段 ----------------

    def _submit(self, payloads):
        started = time.time()
        log('[1/4] 提交 %d 条建单请求（并发 %d，模式 %s）...'
            % (len(payloads), self.args.concurrency, self.args.mode))

        def work(seq_payload):
            seq, payload = seq_payload
            return self._submit_one(seq, payload)

        with ThreadPoolExecutor(max_workers=self.args.concurrency) as pool:
            futures = [pool.submit(work, item) for item in enumerate(payloads)]
            for index, future in enumerate(as_completed(futures), start=1):
                self.records.append(future.result())
                if index % 100 == 0 or index == len(futures):
                    log('      ... 已提交 %d/%d' % (index, len(futures)))

        self.records.sort(key=lambda item: item.seq)
        self.submit_seconds = time.time() - started
        accepted = sum(1 for item in self.records if item.request_id)
        failed = len(self.records) - accepted
        log('[1/4] 完成：受理 %d 条，提交失败 %d 条，耗时 %.2fs' %
            (accepted, failed, self.submit_seconds))
        if failed:
            sample = next(r.error for r in self.records if not r.request_id) if failed else ''
            log('      提交失败示例：%s' % sample)
        log()

    def _submit_one(self, seq, payload):
        record = Record(seq, payload['userId'], '%s-%d' % (self.tag, seq), payload)
        record.enqueued_at = time.time()
        try:
            if self.args.mode == 'outbox':
                # 与生产完全同一条路径：事务内写 request + outbox
                accepted = q.enqueue_hazard_create(record.user_id, record.session_id, payload)
                if accepted.get('ok'):
                    record.request_id = accepted.get('requestId') or ''
                    record.status = accepted.get('status') or q.REQ_PENDING
                else:
                    record.error = str(accepted.get('message') or 'enqueue failed')
            else:
                # direct：只写 request 行，outbox 由本脚本自己发（避免 relay 重复投递）
                record.request_id = q.new_request_id()
                message = q.build_message(record.request_id, record.user_id,
                                          record.session_id, payload)
                record.body = json.dumps(message, ensure_ascii=False)
                conn = db_pool.pool().acquire()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            'INSERT INTO ai_hazard_create_request '
                            '(request_id, user_id, session_id, payload, status) '
                            'VALUES (%s, %s, %s, %s, %s)',
                            (record.request_id, record.user_id, record.session_id,
                             record.body, q.REQ_PENDING),
                        )
                    conn.commit()
                    record.status = q.REQ_PENDING
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    db_pool.pool().release(conn)
        except Exception as exc:  # noqa: BLE001 - 单条失败不能拖垮整轮压测
            record.error = '%s: %s' % (type(exc).__name__, exc)
        return record

    # ---------------- direct 模式：自己投递 ----------------

    def _publish_direct(self):
        try:
            import pika
        except ImportError:
            raise SystemExit(
                '--mode direct 需要 pika：pip install pika（或 pip install -r requirements.txt）')

        log('[2/4] 直连 RabbitMQ 投递 %d 条消息（%s:%s%s）...'
            % (len(self.records), q.RABBITMQ_HOST, q.RABBITMQ_PORT, q.RABBITMQ_VHOST))
        started = time.time()
        credentials = pika.PlainCredentials(q.RABBITMQ_USER, q.RABBITMQ_PASSWORD)
        params = pika.ConnectionParameters(
            host=q.RABBITMQ_HOST, port=q.RABBITMQ_PORT,
            virtual_host=q.RABBITMQ_VHOST, credentials=credentials,
            heartbeat=30, blocked_connection_timeout=10, socket_timeout=10,
        )
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            # 拓扑复用生产实现，保证两边声明参数一致（不一致会 406）
            q.RabbitPublisher._declare_topology(channel)
            channel.confirm_delivery()
            published = 0
            for record in self.records:
                if not record.request_id:
                    continue
                channel.basic_publish(
                    exchange=q.RABBITMQ_EXCHANGE,
                    routing_key=q.HAZARD_CREATE_ROUTING_KEY,
                    body=record.body.encode('utf-8'),
                    mandatory=True,
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                published += 1
        finally:
            try:
                connection.close()
            except Exception:
                pass
        log('[2/4] 完成：投递 %d 条，耗时 %.2fs' % (published, time.time() - started))
        log()

    # ---------------- 轮询阶段 ----------------

    def _refresh(self, conn):
        """批量刷新状态。用主键 IN 分批，避免 2000 次单行查询。"""
        ids = [item.request_id for item in self.records if item.request_id]
        latest = {}
        with conn.cursor() as cur:
            for chunk in _chunks(ids, CHUNK):
                cur.execute(
                    'SELECT request_id, status, hazard_id, error_message '
                    'FROM ai_hazard_create_request WHERE request_id IN (%s)'
                    % _placeholders(len(chunk)),
                    chunk,
                )
                for request_id, status, hazard_id, error in cur.fetchall():
                    latest[request_id] = (status, hazard_id, error)
        # 关键：同一连接上重复 SELECT 会吃 REPEATABLE READ 固定快照，
        # 不 rollback 就一直读到第一次的快照（db_pool 文档里记录过的坑）。
        conn.rollback()

        now = time.time()
        for record in self.records:
            row = latest.get(record.request_id)
            if not row:
                continue
            status, hazard_id, error = row
            record.status = status
            record.hazard_id = hazard_id
            record.error = error or ''
            if status in TERMINAL_STATUS and not record.terminal_at:
                record.terminal_at = now

    def _poll(self, conn):
        log('[3/4] 轮询状态（每 %ss，最长 %ss）...' % (self.args.poll_interval, self.args.timeout))
        deadline = time.time() + self.args.timeout
        tick = 0
        while True:
            tick += 1
            self._refresh(conn)
            pending = [r for r in self.records
                       if r.request_id and r.status not in TERMINAL_STATUS]
            done = len(self.records) - len(pending)
            log('      [t+%5.1fs] 终态 %d/%d  %s' % (
                time.time() - deadline + self.args.timeout, done, len(self.records),
                self._counts_line()))
            if not pending:
                break
            if tick == 3 and done == 0:
                log('      [提示] 一条都没流转：确认 hazard_create_worker.py 在跑、'
                    'RabbitMQ 可达、Java 消费者已启动（MQ 唯一建单路径）。')
            if time.time() >= deadline:
                break
            time.sleep(self.args.poll_interval)

        self.drain_seconds = time.time() - (deadline - self.args.timeout)
        timed_out = [r for r in self.records
                     if r.request_id and r.status not in TERMINAL_STATUS]
        for record in timed_out:
            record.status = STATUS_TIMEOUT
        log('[3/4] 完成：超时未终态 %d 条，排空耗时 %.2fs' % (len(timed_out), self.drain_seconds))
        if timed_out:
            log('      超时样例 request_id：%s' %
                ', '.join(r.request_id for r in timed_out[:5]))
        log()

    def _counts_line(self):
        counts = {}
        for record in self.records:
            counts[record.status] = counts.get(record.status, 0) + 1
        return ' '.join('%s=%d' % (k, v) for k, v in sorted(counts.items()))

    # ---------------- 校验阶段 ----------------

    def _verify(self, conn):
        log('[4/4] 校验 tb_hazard（重复建单 / 缺行 / 有行无回执）...')
        ids = [item.request_id for item in self.records if item.request_id]
        counts = {}
        with conn.cursor() as cur:
            for chunk in _chunks(ids, CHUNK):
                cur.execute(
                    'SELECT request_id, COUNT(*) FROM tb_hazard '
                    'WHERE request_id IN (%s) GROUP BY request_id'
                    % _placeholders(len(chunk)),
                    chunk,
                )
                for request_id, count in cur.fetchall():
                    counts[request_id] = int(count)
        conn.rollback()   # 同上：只读校验也别留固定快照

        for record in self.records:
            if not record.request_id:
                continue
            rows = counts.get(record.request_id, 0)
            if rows > 1:
                self.duplicate_rows += rows - 1
                self.duplicate_ids.append(record.request_id)
            if record.status == q.REQ_SUCCESS and rows == 0:
                self.success_without_row.append(record.request_id)
            if record.status not in TERMINAL_STATUS and rows > 0:
                self.row_without_result.append(record.request_id)

        log('      duplicate=%d  success_without_row=%d  row_without_result=%d'
            % (self.duplicate_rows, len(self.success_without_row),
               len(self.row_without_result)))
        log()

    def _queue_depths(self):
        """读队列深度（含 DLQ）。pika 不可用或 broker 不可达时返回 None。"""
        try:
            import pika
        except ImportError:
            return None
        try:
            credentials = pika.PlainCredentials(q.RABBITMQ_USER, q.RABBITMQ_PASSWORD)
            params = pika.ConnectionParameters(
                host=q.RABBITMQ_HOST, port=q.RABBITMQ_PORT,
                virtual_host=q.RABBITMQ_VHOST, credentials=credentials,
                heartbeat=30, blocked_connection_timeout=10, socket_timeout=10,
            )
            connection = pika.BlockingConnection(params)
        except Exception as exc:  # noqa: BLE001
            return {'error': '%s: %s' % (type(exc).__name__, exc)}
        depths = {}
        try:
            channel = connection.channel()
            for name in (q.HAZARD_CREATE_QUEUE, q.HAZARD_CREATE_DLQ, q.HAZARD_RESULT_QUEUE):
                try:
                    method = channel.queue_declare(queue=name, passive=True).method
                    depths[name] = int(method.message_count)
                except Exception as exc:  # noqa: BLE001
                    depths[name] = 'n/a (%s)' % exc
        finally:
            try:
                connection.close()
            except Exception:
                pass
        return depths

    # ---------------- 清理 ----------------

    def _cleanup(self, conn):
        """只删 Python 侧两表；tb_hazard 属于 Java 侧，只打印 SQL。"""
        ids = [item.request_id for item in self.records]
        if not ids:
            return
        log('[清理] 删除本次压测的 ai_hazard_create_* 行 ...')
        deleted = 0
        affected = 0
        with conn.cursor() as cur:
            for chunk in _chunks(ids, CHUNK):
                cur.execute('DELETE FROM ai_hazard_create_outbox WHERE request_id IN (%s)'
                            % _placeholders(len(chunk)), chunk)
                deleted += cur.rowcount
                cur.execute('DELETE FROM ai_hazard_create_request WHERE request_id IN (%s)'
                            % _placeholders(len(chunk)), chunk)
                deleted += cur.rowcount
                affected += cur.rowcount
        conn.commit()
        log('[清理] 已删除 %d 行（覆盖 %d 条 request）' % (deleted, affected))
        log()

    def _cleanup_sql(self):
        low = self.args.user_id_base
        high = self.args.user_id_base + self.args.total - 1
        return ('-- 本次压测在 tb_hazard 里产生的行（Java 侧数据，按 user_id 区间删）\n'
                'DELETE FROM tb_hazard WHERE user_id BETWEEN %d AND %d;\n'
                '-- 复核：应该只剩 0 行\n'
                'SELECT COUNT(*) FROM tb_hazard WHERE user_id BETWEEN %d AND %d;'
                % (low, high, low, high))

    # ---------------- 汇总 ----------------

    def _summary(self, started, summary_name):
        success = [r for r in self.records if r.status == q.REQ_SUCCESS]
        failed = [r for r in self.records if r.status == q.REQ_FAILED]
        timeout = [r for r in self.records if r.status == STATUS_TIMEOUT]
        submit_failed = [r for r in self.records if not r.request_id]
        latencies = [r.latency for r in self.records if r.latency is not None]
        success_latency = [r.latency for r in success if r.latency is not None]
        wall = time.time() - started

        summary = {
            'runName': summary_name,
            'tag': self.tag,
            'generatedAt': datetime.now().isoformat(timespec='seconds'),
            'mode': self.args.mode,
            'target': {
                'host': DB_CONFIG.get('host'),
                'port': DB_CONFIG.get('port'),
                'database': DB_CONFIG.get('database'),
                'user': DB_CONFIG.get('user'),
            },
            'params': {
                'concurrency': self.args.concurrency,
                'total': self.args.total,
                'timeout': self.args.timeout,
                'pollInterval': self.args.poll_interval,
                'userIdBase': self.args.user_id_base,
            },
            'counts': {
                'submitted': len(self.records),
                'accepted': sum(1 for r in self.records if r.request_id),
                'submitFailed': len(submit_failed),
                'success': len(success),
                'failed': len(failed),
                'timeout': len(timeout),
            },
            'correctness': {
                'duplicateRows': self.duplicate_rows,
                'duplicateRequestIds': self.duplicate_ids[:20],
                'successWithoutHazardRow': len(self.success_without_row),
                'successWithoutHazardRowSample': self.success_without_row[:20],
                'hazardRowWithoutResult': len(self.row_without_result),
                'hazardRowWithoutResultSample': self.row_without_result[:20],
            },
            'timing': {
                'submitSeconds': round(self.submit_seconds, 3),
                'drainSeconds': round(self.drain_seconds, 3),
                'wallSeconds': round(wall, 3),
                'submitRps': round(len(self.records) / self.submit_seconds, 2)
                if self.submit_seconds > 0 else None,
                'terminalRps': round((len(success) + len(failed)) / wall, 2) if wall > 0 else None,
                },
            'latencySeconds': {
                'success': {
                    'p50': percentile(success_latency, 50),
                    'p95': percentile(success_latency, 95),
                    'p99': percentile(success_latency, 99),
                    'max': round(max(success_latency), 3) if success_latency else None,
                },
                'allTerminal': {
                    'p50': percentile(latencies, 50),
                    'p95': percentile(latencies, 95),
                    'p99': percentile(latencies, 99),
                    'max': round(max(latencies), 3) if latencies else None,
                },
            },
            'queueDepths': self.depths,
        }
        return summary

    def print_summary(self, summary):
        counts = summary['counts']
        correct = summary['correctness']
        latency = summary['latencySeconds']
        total = counts['submitted'] or 1

        log('=' * 72)
        log('压测结果  tag=%s  mode=%s' % (summary['tag'], summary['mode']))
        log('目标库      : %s:%s/%s' % (summary['target']['host'],
                                        summary['target']['port'],
                                        summary['target']['database']))
        log('并发 / 总量  : %s / %s' % (summary['params']['concurrency'],
                                        summary['params']['total']))
        log('-' * 72)
        log('SUCCESS     : %5d  (%.2f%%)' % (counts['success'],
                                             100.0 * counts['success'] / total))
        log('FAILED      : %5d  (%.2f%%)' % (counts['failed'],
                                             100.0 * counts['failed'] / total))
        log('TIMEOUT     : %5d  (%.2f%%)' % (counts['timeout'],
                                             100.0 * counts['timeout'] / total))
        log('提交失败     : %5d' % counts['submitFailed'])
        log('-' * 72)
        log('duplicate   : %5d  (同一 request_id 建出多条 tb_hazard，必须 0)'
            % correct['duplicateRows'])
        log('SUCCESS 缺行 : %5d  (回执 SUCCESS 但 tb_hazard 无行，必须 0)'
            % correct['successWithoutHazardRow'])
        log('有行无回执   : %5d  (已建单但状态未到终态 = 回执丢失信号，必须 0)'
            % correct['hazardRowWithoutResult'])
        log('-' * 72)
        for label, key in (('SUCCESS', 'success'), ('ALL-TERMINAL', 'allTerminal')):
            data = latency[key]
            log('延迟(确认->终态) %-13s: p50=%s p95=%s p99=%s max=%s' % (
                label, _fmt(data['p50'], 's'), _fmt(data['p95'], 's'),
                _fmt(data['p99'], 's'), _fmt(data['max'], 's')))
        log('-' * 72)
        log('提交阶段     : %.2fs (%s req/s)' % (
            summary['timing']['submitSeconds'],
            _fmt(summary['timing']['submitRps'], '')))
        log('排空阶段     : %.2fs' % summary['timing']['drainSeconds'])
        log('整体墙钟     : %.2fs' % summary['timing']['wallSeconds'])
        if summary['queueDepths'] is None:
            log('队列深度     : n/a（pika 不可用）')
        elif 'error' in summary['queueDepths']:
            log('队列深度     : n/a（%s）' % summary['queueDepths']['error'])
        else:
            for name, depth in summary['queueDepths'].items():
                log('队列 %-24s : %s' % (name, depth))
        log('=' * 72)

    def violations(self, summary):
        problems = []
        if summary['counts']['submitFailed']:
            problems.append('提交失败 %d 条' % summary['counts']['submitFailed'])
        if summary['correctness']['duplicateRows']:
            problems.append('重复建单 %d 行' % summary['correctness']['duplicateRows'])
        if summary['correctness']['successWithoutHazardRow']:
            problems.append('SUCCESS 但无 tb_hazard 行 %d 条'
                            % summary['correctness']['successWithoutHazardRow'])
        if summary['counts']['timeout']:
            problems.append('超时未终态 %d 条' % summary['counts']['timeout'])
        if summary['counts']['failed']:
            problems.append('FAILED %d 条' % summary['counts']['failed'])
        depths = summary.get('queueDepths')
        if isinstance(depths, dict) and isinstance(depths.get(q.HAZARD_CREATE_DLQ), int) \
                and depths[q.HAZARD_CREATE_DLQ] > 0:
            problems.append('DLQ 非空：%s' % depths[q.HAZARD_CREATE_DLQ])
        return problems

    # ---------------- 主流程 ----------------

    def run(self):
        payloads = self._build_payloads()
        self._banner(payloads)
        started = time.time()

        if self.args.dry_run:
            summary = self._summary(started, 'dry-run')
            summary['queueDepths'] = self._queue_depths()
            self.print_summary(summary)
            log('DRY-RUN：未写任何数据。去掉 --dry-run 即按上方参数执行。')
            return summary

        conn = db_pool.pool().acquire()
        try:
            self._submit(payloads)
            if self.args.mode == 'direct':
                self._publish_direct()
            else:
                log('[2/4] 跳过：outbox 模式由 hazard_create_worker.py 的 Relay 投递。')
                log()
            self._poll(conn)
            self._verify(conn)
            self.depths = self._queue_depths()
            if self.args.cleanup:
                self._cleanup(conn)
        finally:
            db_pool.pool().release(conn)

        summary = self._summary(started, self.args.name or self.tag)
        self.print_summary(summary)
        if self.args.print_cleanup or not self.args.cleanup:
            log('清理 SQL（tb_hazard 属 Java 侧数据，脚本不代删）：')
            log(self._cleanup_sql())
        if self.args.json_out:
            self._write_json(summary)
        return summary

    def _write_json(self, summary):
        path = os.path.abspath(self.args.json_out)
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
        log('JSON 结果已写入：%s' % path)


def build_parser():
    parser = argparse.ArgumentParser(
        description='AI 建任务 MQ 高并发压测（Task 9）',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--concurrency', type=int, default=10,
                        help='提交阶段并发线程数（不要超过 MySQL max_connections 余量）')
    parser.add_argument('--total', type=int, default=100, help='压测请求总数')
    parser.add_argument('--timeout', type=float, default=120.0,
                        help='从提交开始算的排空超时（秒）')
    parser.add_argument('--poll-interval', type=float, default=1.0,
                        help='轮询状态表的间隔（秒）')
    parser.add_argument('--mode', choices=('outbox', 'direct'), default='outbox',
                        help='outbox=走 relay（生产链路）；direct=脚本直发 RabbitMQ')
    parser.add_argument('--tag', default=None,
                        help='本次压测标记，写进 session_id（默认 loadtest-<时间戳>）')
    parser.add_argument('--name', default=None, help='结果里的 runName（默认用 tag）')
    parser.add_argument('--user-id-base', type=int, default=DEFAULT_USER_ID_BASE,
                        help='模拟用户 id 起点；每条请求占用一个独立 user_id')
    parser.add_argument('--dry-run', action='store_true', help='只生成 payload，不写数据')
    parser.add_argument('--cleanup', action='store_true',
                        help='结束后删除本次压测的 ai_hazard_create_* 行')
    parser.add_argument('--print-cleanup', action='store_true', help='只打印清理 SQL')
    parser.add_argument('--json-out', default=None, help='把结果 JSON 写到指定路径')
    parser.add_argument('--allow-remote', action='store_true',
                        help='允许连接非本机/内网数据库（生产库务必先确认）')
    parser.add_argument('--allow-violations', action='store_true',
                        help='即使验收线不满足也返回退出码 0')
    parser.add_argument('--verbose', action='store_true', help='打印 hazard_create_queue 的 INFO 日志')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.total <= 0:
        log('--total 必须大于 0')
        return 2
    if args.concurrency <= 0:
        log('--concurrency 必须大于 0')
        return 2
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('safety.ai.hazard_queue').setLevel(
        logging.INFO if args.verbose else logging.WARNING)

    host = DB_CONFIG.get('host')
    if not _is_private_host(host) and not (args.dry_run or args.allow_remote):
        log('拒绝执行：目标库 %s 不是本机/内网地址。' % host)
        log('  压测请指向本地/预发库：先设 $env:DB_HOST=\'127.0.0.1\' 再运行；')
        log('  确实要在该库上压测，请显式加 --allow-remote（并确认不会污染真实数据）。')
        return 2

    tag = args.tag or 'loadtest-%s' % datetime.now().strftime('%Y%m%d-%H%M%S')
    runner = LoadRunner(args, tag)
    summary = runner.run()

    if args.dry_run:
        return 0
    problems = runner.violations(summary)
    if problems:
        log('验收判定：FAIL —— %s' % '；'.join(problems))
        return 0 if args.allow_violations else 1
    log('验收判定：PASS（无重复建单 / 无丢单 / DLQ=0 / 全部终态）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
