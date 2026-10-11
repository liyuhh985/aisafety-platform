"""
混合检索：向量语义匹配 + 关键词精确匹配 → 合并去重排序。
"""
import json
import inspect
import logging
import math
import os
import socket
import threading
import time
from typing import Optional

import numpy as np
import pymysql
import requests

from config import (
    MILVUS_ENABLED,
    MILVUS_FALLBACK_TO_MYSQL,
    MILVUS_CASE_COLLECTION,
    MILVUS_POLICY_COLLECTION,
    MILVUS_REGULATION_COLLECTION,
    MIMO_BASE_URL,
    MIMO_API_KEY,
    SF_BASE_URL,
    SF_API_KEY,
    SF_EMBED_MODEL,
    RETRIEVAL_MIN_SCORE,
    RETRIEVAL_TIMEOUT_SECONDS,
    VECTOR_BACKEND,
)
from core.cancellation import CancellationToken, StreamCancelled
from db_config import DB_CONFIG
from tools import db_pool

EMBEDDING_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "db", "case_embeddings.json")
LOGGER = logging.getLogger(__name__)

TABLE_TO_COLLECTION = {
    "tb_hazard_case": MILVUS_CASE_COLLECTION,
    "tb_hazard_knowledge": MILVUS_POLICY_COLLECTION,
    "tb_regulation": MILVUS_REGULATION_COLLECTION,
}


class MilvusRetrievalError(RuntimeError):
    """Raised when Milvus retrieval fails and MySQL fallback is disabled."""


class RetrievalTimeout(TimeoutError):
    """Raised when one logical library lookup exhausts its time budget."""


def _check_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation:
        cancellation.throw_if_cancelled()


def _remaining(deadline: float | None, fallback: float = RETRIEVAL_TIMEOUT_SECONDS) -> float:
    remaining = float(fallback) if deadline is None else deadline - time.monotonic()
    if remaining <= 0:
        raise RetrievalTimeout("retrieval time budget exhausted")
    return remaining


def _call_with_optional_kwargs(func, *args, **kwargs):
    """Keep old test doubles and integrations valid while adding cancellation args."""
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return func(*args, **kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD
           for parameter in parameters.values()):
        return func(*args, **kwargs)
    accepted = {key: value for key, value in kwargs.items() if key in parameters}
    return func(*args, **accepted)


def _mysql_connection(timeout_seconds: float, cancellation: CancellationToken | None):
    """从检索池取连接。

    注意取舍：原来是**每次查询按剩余预算**设 socket 超时；池化后 socket 超时固定为
    RETRIEVAL_TIMEOUT_SECONDS（建池时定），逐次收紧只剩应用侧 deadline 检查。
    代价：单条查询最长等 RETRIEVAL_TIMEOUT_SECONDS（默认 10s，与原来首次预算相同），
    而不是"剩余预算"。换来的是每轮检索省掉 2~4 次 ~45ms 握手。
    取消路径一律 discard，不复用半途的连接。
    """
    try:
        conn = db_pool.retrieval_pool().acquire()
    except Exception as exc:
        _raise_for_cancel_or_timeout(exc, cancellation)
        raise
    closer = lambda: db_pool.retrieval_pool().discard(conn)
    if cancellation:
        cancellation.register(closer)
        try:
            cancellation.throw_if_cancelled()
        except StreamCancelled:
            cancellation.unregister(closer)
            closer()
            raise
    return conn, closer


def _raise_for_cancel_or_timeout(exc: Exception,
                                 cancellation: CancellationToken | None) -> None:
    if cancellation and cancellation.is_cancelled():
        raise StreamCancelled() from exc
    message = str(exc).lower()
    if isinstance(exc, (TimeoutError, socket.timeout, requests.Timeout)) or "timed out" in message:
        raise RetrievalTimeout("retrieval dependency timed out") from exc


# ====== 关键词分支：分词 OR 召回 + Python 打分排序 ======

# 语料规模（案例 231 / 法规 129 / 知识 30）远小于该上限，所以"扫全量候选、在 Python 里打分"
# 是精确的；语料涨到接近这个量级时要一起调大（超过后截断会退化成按 id 丢尾部候选）。
_KEYWORD_SCAN_CAP = 500

# 短于 2 个字的 token 信息量太低（"的""在"），丢掉。
_KEYWORD_TOKEN_MIN_LEN = 2

# 槽位值里常见的中文顿号/逗号/分号，切开后每个词更有机会命中。
# 刻意**不切 "/"**：分类标签里有"井盖缺失/破损""排水/积水""占道经营/乱堆乱放"，
# 切开会让"破损""积水"这类泛词单独进 LIKE，反而污染结果。
_KEYWORD_TOKEN_SEPARATORS = "、，,;；"

_KEYWORD_FIELD_SPECS = {
    "tb_hazard_case": {
        "columns": ("id", "title", "description", "category", "severity", "city",
                    "casualties", "cause", "rectification", "regulation_ref", "verdict"),
        "search_fields": ("category", "title", "description"),
        "bonus_fields": ("title",),
    },
    "tb_regulation": {
        "columns": ("id", "law_name", "article", "content", "category", "keywords"),
        "search_fields": ("category", "law_name", "keywords", "content"),
        "bonus_fields": ("law_name",),
    },
    "tb_hazard_knowledge": {
        "columns": ("id", "title", "content", "category", "region", "source"),
        "search_fields": ("title", "content"),
        "bonus_fields": ("title",),
    },
}

def _tokenize_keyword(keyword: str) -> list[str]:
    """切词 → 丢过短 token → 去重。

    刻意**不区分**"类别标签 token"：标签命中 category 字段时拿到的就是同小类案例，
    这是纯向量检索给不了的精度，丢掉它是净损失（评测实测：改前 Hit@5 1.000/MRR 0.984
    → 丢掉标签后 0.938/0.854）。标签块占住前排的问题改为在合并顺序上解决 ——
    见 HybridSearcher._merge_results（向量在前、关键词只补尾部名额）。

    返回空列表表示"这个串没有词汇级信号"，调用方直接返回空结果、交给纯向量检索
    （绝不能落到 LIKE '%%'，那会匹配全表）。
    """
    text = (keyword or "").strip()
    if not text:
        return []
    for separator in _KEYWORD_TOKEN_SEPARATORS:
        text = text.replace(separator, " ")
    tokens: list[str] = []
    for raw in text.split():
        token = raw.strip()
        if len(token) < _KEYWORD_TOKEN_MIN_LEN:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _like_pattern(token: str) -> str:
    """把 token 变成 LIKE 模式串，并转义 LIKE 通配符（% _ \\）。"""
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _rank_keyword_rows(table: str, rows, tokens: list[str]) -> list[tuple]:
    """按 命中 token 数↓ → 标题类字段命中数↓ → id↑ 排序，返回 [(hits, bonus, id, row)]。

    排序刻意放在 Python 里做：MySQL 那边只负责"召回宽候选"，不负责决定顺序
    （改动前没有 ORDER BY，LIMIT 拿到的是按 id 排的任意 3 条）。
    """
    spec = _KEYWORD_FIELD_SPECS[table]
    columns = spec["columns"]
    search_idx = [columns.index(field) for field in spec["search_fields"]]
    bonus_idx = [columns.index(field) for field in spec["bonus_fields"]]
    id_idx = columns.index("id")
    scored = []
    for row in rows:
        hits = 0
        bonus = 0
        for token in tokens:
            needle = token.lower()
            matched_bonus = False
            matched_any = False
            for idx in search_idx:
                value = row[idx]
                if value and needle in str(value).lower():
                    matched_any = True
                    if idx in bonus_idx:
                        matched_bonus = True
            if matched_any:
                hits += 1
                if matched_bonus:
                    bonus += 1
        scored.append((-hits, -bonus, row[id_idx], row))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return scored


def _keyword_row_to_dict(table: str, row) -> dict:
    """把数据库行还原成调用方依赖的 dict 结构（与改动前逐一对应）。"""
    if table == "tb_regulation":
        return {"id": row[0], "title": f"{row[1]} {row[2]}", "description": row[3],
                "category": row[4], "keywords": row[5]}
    if table == "tb_hazard_case":
        return {"table": "tb_hazard_case", "id": row[0], "title": row[1],
                "description": row[2], "category": row[3], "severity": row[4],
                "city": row[5], "casualties": row[6], "cause": row[7],
                "rectification": row[8], "regulation_ref": row[9], "verdict": row[10]}
    return {"table": "tb_hazard_knowledge", "id": row[0], "title": row[1],
            "content": row[2], "category": row[3], "region": row[4], "source": row[5]}


class HybridSearcher:
    """
    混合检索器:
    1. 向量检索 — embedding 语义相似度匹配 top-K
    2. 关键词检索 — MySQL LIKE 精确匹配
    3. 合并去重 — 加权排序返回
    """

    def __init__(
        self,
        vector_store=None,
        embedding_client=None,
        vector_backend: str | None = None,
        milvus_enabled: bool | None = None,
        milvus_fallback_to_mysql: bool | None = None,
        logger=None,
    ):
        self.embedding_cache: dict[int, list[float]] = {}
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.vector_backend = vector_backend or VECTOR_BACKEND
        self.milvus_enabled = MILVUS_ENABLED if milvus_enabled is None else milvus_enabled
        self.milvus_fallback_to_mysql = (
            MILVUS_FALLBACK_TO_MYSQL
            if milvus_fallback_to_mysql is None
            else milvus_fallback_to_mysql
        )
        self.logger = logger or LOGGER
        self._load_cache()

    # ====== 向量检索 ======

    def vector_search(self, query: str, table: str, top_k: int = 3,
                      cancellation: CancellationToken | None = None,
                      deadline: float | None = None) -> list[dict]:
        if table not in TABLE_TO_COLLECTION:
            raise ValueError(f"Unsupported retrieval table: {table}")
        _check_cancelled(cancellation)
        if self.vector_backend == "mysql":
            return _call_with_optional_kwargs(
                self.mysql_vector_search,
                query,
                table,
                top_k,
                cancellation=cancellation,
                deadline=deadline,
            )
        if self.vector_backend != "milvus":
            raise ValueError(f"Unsupported VECTOR_BACKEND: {self.vector_backend}")

        try:
            if not self.milvus_enabled:
                raise MilvusRetrievalError("Milvus backend is disabled")
            return _call_with_optional_kwargs(
                self.milvus_vector_search,
                query,
                table,
                top_k,
                cancellation=cancellation,
                deadline=deadline,
            )
        except RetrievalTimeout:
            raise
        except StreamCancelled:
            raise
        except Exception as exc:
            if self.milvus_fallback_to_mysql:
                self.logger.warning(
                    "Milvus unavailable source=%s reason_type=%s; using MySQL fallback",
                    table,
                    type(exc).__name__,
                )
                return _call_with_optional_kwargs(
                    self.mysql_vector_search,
                    query,
                    table,
                    top_k,
                    cancellation=cancellation,
                    deadline=deadline,
                )
            if isinstance(exc, MilvusRetrievalError):
                raise
            raise MilvusRetrievalError(
                f"Milvus vector retrieval failed for {table}: {type(exc).__name__}"
            ) from exc

    def mysql_vector_search(self, query: str, table: str, top_k: int = 3,
                            cancellation: CancellationToken | None = None,
                            deadline: float | None = None) -> list[dict]:
        """
        MySQL fallback: 用 embedding 做全表语义检索。
        table: "tb_hazard_case" | "tb_hazard_knowledge"
        """
        _check_cancelled(cancellation)
        query_emb = self._embed(
            query,
            cancellation=cancellation,
            timeout_seconds=_remaining(deadline),
        )
        if query_emb is None:
            return []

        # 获取表中所有需要检索的记录
        rows = self._fetch_all(table, cancellation=cancellation, deadline=deadline)
        if not rows:
            return []

        scored = []
        for row in rows:
            _check_cancelled(cancellation)
            row_id, title, content = row[0], row[1], row[2]
            # 优先用缓存，否则实时 embedding
            cached = self.embedding_cache.get(row_id)
            if cached:
                doc_emb = cached
            else:
                doc_emb = self._embed(
                    f"{title} {content or ''}"[:500],
                    cancellation=cancellation,
                    timeout_seconds=_remaining(deadline),
                )
                if doc_emb:
                    self.embedding_cache[row_id] = doc_emb

            if doc_emb:
                sim = self._cosine_sim(query_emb, doc_emb)
                scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_ids = [row[0] for _, row in scored[:top_k]
                   if _ >= RETRIEVAL_MIN_SCORE]
        if not top_ids:
            return []
        # 用 ID 回查完整字段
        return _call_with_optional_kwargs(
            self._get_rows_by_ids,
            table,
            top_ids,
            cancellation=cancellation,
            deadline=deadline,
        )

    def milvus_vector_search(self, query: str, table: str, top_k: int = 3,
                             cancellation: CancellationToken | None = None,
                             deadline: float | None = None,
                             timeout_seconds: float | None = None) -> list[dict]:
        if self.vector_store is None:
            from tools.milvus_store import MilvusVectorStore

            self.vector_store = MilvusVectorStore()
        _check_cancelled(cancellation)
        requested_timeout = timeout_seconds
        if deadline is None and timeout_seconds is not None:
            deadline = time.monotonic() + timeout_seconds
        query_vector = self._milvus_embed(
            query, cancellation=cancellation, deadline=deadline
        )
        hits = _call_with_optional_kwargs(
            self.vector_store.search,
            table,
            query_vector,
            top_k,
            timeout_seconds=(
                requested_timeout
                if requested_timeout is not None
                else _remaining(deadline)
            ),
            cancellation=cancellation,
        )
        if not hits:
            raise MilvusRetrievalError("Milvus collection returned no vector hits")

        confident = [hit for hit in hits if float(hit["distance"]) >= RETRIEVAL_MIN_SCORE]
        if not confident:
            # 有向量命中但全部低于置信度门槛：这不是故障，是「库内确实没有相关内容」。
            # 这里必须 return [] 而不是 raise —— raise 会触发 MySQL 兜底，
            # 把同一批噪声结果再捞回来，等于阈值白加。
            self.logger.info(
                "Milvus hits below confidence threshold source=%s kept=0 dropped=%d",
                table,
                len(hits),
            )
            return []
        if len(confident) < len(hits):
            self.logger.info(
                "Milvus hits filtered by confidence source=%s kept=%d dropped=%d",
                table,
                len(confident),
                len(hits) - len(confident),
            )
        hits = confident

        ids = [int(hit["id"]) for hit in hits]
        rows = _call_with_optional_kwargs(
            self._get_rows_by_ids,
            table,
            ids,
            cancellation=cancellation,
            deadline=deadline,
        )
        rows_by_id = {int(row["id"]): row for row in rows}
        hydrated = []
        for hit in hits:
            row = rows_by_id.get(int(hit["id"]))
            if row is None:
                continue
            hydrated_row = dict(row)
            hydrated_row["match_score"] = float(hit["distance"])
            hydrated.append(hydrated_row)
        if not hydrated:
            raise MilvusRetrievalError(
                "Milvus hits could not be hydrated from MySQL"
            )
        return hydrated

    def _milvus_embed(self, query: str,
                      cancellation: CancellationToken | None = None,
                      deadline: float | None = None) -> list[float]:
        if self.embedding_client is None:
            from tools.knowledge_sync import SiliconFlowEmbeddingClient

            self.embedding_client = SiliconFlowEmbeddingClient()
        vectors = _call_with_optional_kwargs(
            self.embedding_client.embed,
            [query],
            timeout_seconds=_remaining(deadline),
            cancellation=cancellation,
        )
        if len(vectors) != 1:
            raise MilvusRetrievalError("Embedding service returned no query vector")
        return vectors[0]

    def _embed(self, text: str,
               cancellation: CancellationToken | None = None,
               timeout_seconds: float = 30) -> Optional[list[float]]:
        """调用硅基流动 BAAI/bge-m3 embedding API 获取语义向量。"""
        _check_cancelled(cancellation)
        timeout = max(0.001, float(timeout_seconds))
        resp = None
        close = None
        close_once = None
        try:
            resp = requests.post(
                f"{SF_BASE_URL}/embeddings",
                headers={
                    "Authorization": f"Bearer {SF_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": SF_EMBED_MODEL,
                    "input": text[:8192],  # bge-m3 支持最长 8192 token
                },
                timeout=timeout,
            )
            close = getattr(resp, "close", None)
            if callable(close):
                close_lock = threading.Lock()
                closed = False

                def close_once():
                    nonlocal closed
                    with close_lock:
                        if closed:
                            return
                        closed = True
                    close()

            if cancellation and close_once:
                cancellation.register(close_once)
                cancellation.throw_if_cancelled()
            if resp.status_code == 200:
                result = resp.json()["data"][0]["embedding"]
                _check_cancelled(cancellation)
                return result
            _check_cancelled(cancellation)
            print(f"[WARN] Embedding API 返回 {resp.status_code}: {resp.text[:200]}")
            result = self._fallback_embed(text)
            _check_cancelled(cancellation)
            return result
        except StreamCancelled:
            raise
        except requests.Timeout as e:
            if cancellation and cancellation.is_cancelled():
                raise StreamCancelled() from e
            raise RetrievalTimeout("embedding request timed out") from e
        except Exception as e:
            if cancellation and cancellation.is_cancelled():
                raise StreamCancelled() from e
            print(f"[WARN] Embedding API 异常: {e}")
            return self._fallback_embed(text)
        finally:
            if cancellation and close_once:
                cancellation.unregister(close_once)
            if close_once:
                close_once()

    def _fallback_embed(self, text: str) -> list[float]:
        """
        Fallback: 如果 embedding API 不可用，用字符级 n-gram 哈希生成稀疏向量。
        虽然不是真正的语义向量，但能提供基本的文本相似度。
        """
        text = text.lower()
        # 2-gram 和 3-gram 字符级特征
        vec = np.zeros(256)
        for i in range(len(text) - 1):
            idx = (ord(text[i]) + ord(text[i + 1])) % 256
            vec[idx] += 1
        for i in range(len(text) - 2):
            idx = (ord(text[i]) + ord(text[i + 1]) + ord(text[i + 2])) % 256
            vec[idx] += 0.5
        # 归一化
        norm = np.linalg.norm(vec)
        return (vec / norm).tolist() if norm > 0 else vec.tolist()

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        va, vb = np.array(a), np.array(b)
        dot = np.dot(va, vb)
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        return float(dot / (na * nb)) if na > 0 and nb > 0 else 0.0

    # ====== 关键词检索 ======

    @staticmethod
    def keyword_search(keyword: str, table: str, limit: int = 3,
                       cancellation: CancellationToken | None = None,
                       timeout_seconds: float = RETRIEVAL_TIMEOUT_SECONDS) -> list[dict]:
        """关键词匹配：分词 OR 召回 + Python 打分排序（不是整串 LIKE）。

        改动前是拿整串做 `LIKE '%整串%'`，而生产传进来的是「小类标签 + 槽位值」
        （见 core.assistant_graph._pick_keyword），所以只有整串恰好是某个字段的连续子串
        时才会命中 —— 槽位一多就恒为 0 命中，混合检索退化成纯向量检索。

        现在：按空白/顿号切 token，每个 token 做 OR 匹配，取宽候选后在 Python 里按
        "命中 token 数 → 标题类字段 → id" 排序。token 里包含小类标签是**故意**的
        （标签命中 category 等于同小类过滤，是精度来源）；它占住前排的问题由
        _merge_results 的"向量在前"解决。切不出 token 就返回 []，交给纯向量检索。
        """
        _check_cancelled(cancellation)
        spec = _KEYWORD_FIELD_SPECS.get(table)
        if spec is None:
            raise ValueError(f"Unsupported retrieval table: {table}")
        tokens = _tokenize_keyword(keyword)
        if not tokens:
            return []
        conn, closer = _mysql_connection(timeout_seconds, cancellation)
        try:
            with conn.cursor() as cur:
                columns = ", ".join(spec["columns"])
                clauses = []
                params: list = []
                for field in spec["search_fields"]:
                    clauses.append(
                        "(" + " OR ".join(f"{field} LIKE %s" for _ in tokens) + ")")
                    params.extend(_like_pattern(token) for token in tokens)
                sql = (f"SELECT {columns} FROM {table} WHERE " + " OR ".join(clauses)
                       + " ORDER BY id ASC LIMIT %s")
                params.append(_KEYWORD_SCAN_CAP)
                cur.execute(sql, params)
                rows = cur.fetchall()
        except StreamCancelled:
            raise
        except Exception as exc:
            _raise_for_cancel_or_timeout(exc, cancellation)
            raise
        finally:
            if cancellation:
                cancellation.unregister(closer)
            db_pool.retrieval_pool().release(conn)
        ranked = _rank_keyword_rows(table, rows, tokens)
        return [_keyword_row_to_dict(table, item[3]) for item in ranked[:max(0, limit)]]


    # ====== 混合检索 ======

    def hybrid_search(self, query: str, table: str = "tb_hazard_case",
                      vector_k: int = 3, keyword_k: int = 3,
                      cancellation: CancellationToken | None = None,
                      timeout_seconds: float = RETRIEVAL_TIMEOUT_SECONDS) -> str:
        """
        混合检索入口：向量 + 关键词 → 合并去重 → 格式化输出。
        """
        if table not in TABLE_TO_COLLECTION:
            raise ValueError(f"Unsupported retrieval table: {table}")

        deadline = time.monotonic() + max(0.001, float(timeout_seconds))
        _check_cancelled(cancellation)
        try:
            vector_results = _call_with_optional_kwargs(
                self.vector_search,
                query,
                table,
                top_k=vector_k,
                cancellation=cancellation,
                deadline=deadline,
            )
            _check_cancelled(cancellation)
        except StreamCancelled:
            raise
        except RetrievalTimeout:
            _check_cancelled(cancellation)
            return self._degraded_result(query, table)
        except MilvusRetrievalError as exc:
            _check_cancelled(cancellation)
            return f"Milvus 向量检索不可用：{exc}。请暂时使用 MySQL 检索或稍后重试。"
        try:
            keyword_results = _call_with_optional_kwargs(
                self.keyword_search,
                query,
                table,
                limit=keyword_k,
                cancellation=cancellation,
                timeout_seconds=_remaining(deadline),
            )
            _check_cancelled(cancellation)
        except StreamCancelled:
            raise
        except RetrievalTimeout:
            _check_cancelled(cancellation)
            return self._degraded_result(query, table)

        merged = self._merge_results(keyword_results, vector_results, vector_k, keyword_k)

        # 格式化输出
        if not merged:
            return f"未找到与「{query}」相关的结果。"

        lines = [f"=== 混合检索结果: 「{query}」(语义{vector_k}+关键词{keyword_k}) ==="]
        for i, r in enumerate(merged[:max(vector_k, keyword_k) + 2], 1):
            if table == "tb_regulation":
                lines.append(
                    f"\n【法规{i}】[{r['match_type']}匹配] {r.get('title', '')}\n"
                    f"  类别: {r.get('category', '')}\n"
                    f"  内容: {(r.get('description', '') or '')[:300]}"
                )
            elif table == "tb_hazard_case":
                lines.append(
                    f"\n【结果{i}】[{r['match_type']}匹配] {r.get('title', '')}\n"
                    f"  类别: {r.get('category', '')} | 城市: {r.get('city', '')}"
                    f" | 严重程度: {r.get('severity', '')}\n"
                    f"  描述: {(r.get('description', '') or '')[:200]}\n"
                    f"  原因: {(r.get('cause', '') or '')[:150]}\n"
                    f"  整改: {(r.get('rectification', '') or '')[:200]}\n"
                    f"  法规: {(r.get('regulation_ref', '') or '')[:150]}\n"
                    f"  判决: {(r.get('verdict', '') or '')[:150]}"
                )
            else:
                lines.append(
                    f"\n【结果{i}】[{r['match_type']}匹配] {r.get('title', '')}\n"
                    f"  类别: {r.get('category', '')} | 地区: {r.get('region', '')}\n"
                    f"  内容: {(r.get('content', '') or '')[:300]}\n"
                    f"  来源: {r.get('source', '—')}"
                )
        return "\n".join(lines)

    @staticmethod
    def _merge_results(keyword_results: list[dict], vector_results: list[dict],
                       vector_k: int, keyword_k: int) -> list[dict]:
        """合并去重：**向量在前、关键词只补尾部名额**，按 id 去重，截断到 max(k) + 2。

        顺序是有意的：关键词块内部只按"命中 token 数 → 字段 → id"排，跟语义相关性无关，
        把它放在前面会用 id 顺序占住 top-1~3（评测实测：关键词在前时"槽位有值"MRR
        0.728，改成向量在后…即向量在前后回到 0.844）。所以向量负责相关性排序，
        关键词负责把向量没占满的名额补上（多召回同小类/同 token 的条目）。

        这一段定义了"模型真正看得到的窗口"，eval_retrieval.py 直接调用它，
        保证评测重建的排名与生产同源 —— 两边各写一份迟早会漂移。
        """
        seen = set()
        merged = []
        for r in vector_results:
            rid = r.get("id")
            if rid not in seen:
                seen.add(rid)
                r["match_type"] = "语义"
                merged.append(r)
        for r in keyword_results:
            if r["id"] not in seen:
                seen.add(r["id"])
                r["match_type"] = "关键词"
                merged.append(r)
        return merged[:max(vector_k, keyword_k) + 2]

    @staticmethod
    def _degraded_result(query: str, table: str) -> str:
        return f"{table} retrieval timeout（检索超时），暂未返回结果。查询：{query}"

    @staticmethod
    def _get_rows_by_ids(table: str, ids: list[int],
                         cancellation: CancellationToken | None = None,
                         deadline: float | None = None) -> list[dict]:
        """按 ID 列表回查完整字段。"""
        if not ids:
            return []
        _check_cancelled(cancellation)
        conn, closer = _mysql_connection(_remaining(deadline), cancellation)
        try:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(ids))
                if table == "tb_regulation":
                    cur.execute(
                        f"SELECT id, law_name, article, content, category, keywords "
                        f"FROM tb_regulation WHERE id IN ({placeholders})",
                        ids,
                    )
                    return [
                        {"id": r[0], "title": f"{r[1]} {r[2]}", "description": r[3],
                         "category": r[4] or "", "keywords": r[5] or ""}
                        for r in cur.fetchall()
                    ]
                if table == "tb_hazard_case":
                    cur.execute(
                        f"SELECT id, title, description, category, severity, city, "
                        f"casualties, cause, rectification, regulation_ref, verdict "
                        f"FROM tb_hazard_case WHERE id IN ({placeholders})",
                        ids,
                    )
                    return [
                        {"id": r[0], "title": r[1], "description": r[2], "category": r[3] or "",
                         "severity": r[4] or "", "city": r[5] or "", "casualties": r[6] or "",
                         "cause": r[7] or "", "rectification": r[8] or "",
                         "regulation_ref": r[9] or "", "verdict": r[10] or ""}
                        for r in cur.fetchall()
                    ]
                else:
                    cur.execute(
                        f"SELECT id, title, content, category, region, source "
                        f"FROM tb_hazard_knowledge WHERE id IN ({placeholders})",
                        ids,
                    )
                    return [
                        {"id": r[0], "title": r[1], "content": r[2], "category": r[3] or "",
                         "region": r[4] or "", "source": r[5] or ""}
                        for r in cur.fetchall()
                    ]
        except StreamCancelled:
            raise
        except Exception as exc:
            _raise_for_cancel_or_timeout(exc, cancellation)
            raise
        finally:
            if cancellation:
                cancellation.unregister(closer)
            db_pool.retrieval_pool().release(conn)

    # ====== 缓存 ======

    def _fetch_all(self, table: str,
                   cancellation: CancellationToken | None = None,
                   deadline: float | None = None) -> list:
        """获取表中所有记录 (id, title, content/description)。"""
        _check_cancelled(cancellation)
        conn, closer = _mysql_connection(_remaining(deadline), cancellation)
        try:
            with conn.cursor() as cur:
                if table == "tb_regulation":
                    cur.execute("SELECT id, law_name, CONCAT(article, ' ', content) FROM tb_regulation")
                elif table == "tb_hazard_case":
                    cur.execute("SELECT id, title, CONCAT(description, ' ', cause) FROM tb_hazard_case")
                else:
                    cur.execute("SELECT id, title, content FROM tb_hazard_knowledge")
                return cur.fetchall()
        except StreamCancelled:
            raise
        except Exception as exc:
            _raise_for_cancel_or_timeout(exc, cancellation)
            raise
        finally:
            if cancellation:
                cancellation.unregister(closer)
            db_pool.retrieval_pool().release(conn)

    def _load_cache(self):
        if os.path.exists(EMBEDDING_CACHE_FILE):
            try:
                with open(EMBEDDING_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.embedding_cache = {int(k): v for k, v in data.items()}
            except Exception:
                pass

    def save_cache(self):
        os.makedirs(os.path.dirname(EMBEDDING_CACHE_FILE), exist_ok=True)
        with open(EMBEDDING_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.embedding_cache, f, ensure_ascii=False)


# 单例
searcher = HybridSearcher()
