"""
混合检索：向量语义匹配 + 关键词精确匹配 → 合并去重排序。
"""
import json
import logging
import math
import os
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
    VECTOR_BACKEND,
)
from db_config import DB_CONFIG

EMBEDDING_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "db", "case_embeddings.json")
LOGGER = logging.getLogger(__name__)

TABLE_TO_COLLECTION = {
    "tb_hazard_case": MILVUS_CASE_COLLECTION,
    "tb_hazard_knowledge": MILVUS_POLICY_COLLECTION,
    "tb_regulation": MILVUS_REGULATION_COLLECTION,
}


class MilvusRetrievalError(RuntimeError):
    """Raised when Milvus retrieval fails and MySQL fallback is disabled."""


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

    def vector_search(self, query: str, table: str, top_k: int = 3) -> list[dict]:
        if table not in TABLE_TO_COLLECTION:
            raise ValueError(f"Unsupported retrieval table: {table}")
        if self.vector_backend == "mysql":
            return self.mysql_vector_search(query, table, top_k)
        if self.vector_backend != "milvus":
            raise ValueError(f"Unsupported VECTOR_BACKEND: {self.vector_backend}")

        try:
            if not self.milvus_enabled:
                raise MilvusRetrievalError("Milvus backend is disabled")
            return self.milvus_vector_search(query, table, top_k)
        except Exception as exc:
            if self.milvus_fallback_to_mysql:
                self.logger.warning(
                    "Milvus unavailable source=%s reason_type=%s; using MySQL fallback",
                    table,
                    type(exc).__name__,
                )
                return self.mysql_vector_search(query, table, top_k)
            if isinstance(exc, MilvusRetrievalError):
                raise
            raise MilvusRetrievalError(
                f"Milvus vector retrieval failed for {table}: {type(exc).__name__}"
            ) from exc

    def mysql_vector_search(self, query: str, table: str, top_k: int = 3) -> list[dict]:
        """
        MySQL fallback: 用 embedding 做全表语义检索。
        table: "tb_hazard_case" | "tb_hazard_knowledge"
        """
        query_emb = self._embed(query)
        if query_emb is None:
            return []

        # 获取表中所有需要检索的记录
        rows = self._fetch_all(table)
        if not rows:
            return []

        scored = []
        for row in rows:
            row_id, title, content = row[0], row[1], row[2]
            # 优先用缓存，否则实时 embedding
            cached = self.embedding_cache.get(row_id)
            if cached:
                doc_emb = cached
            else:
                doc_emb = self._embed(f"{title} {content or ''}"[:500])
                if doc_emb:
                    self.embedding_cache[row_id] = doc_emb

            if doc_emb:
                sim = self._cosine_sim(query_emb, doc_emb)
                scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_ids = [row[0] for _, row in scored[:top_k] if _ > 0.3]
        if not top_ids:
            return []
        # 用 ID 回查完整字段
        return self._get_rows_by_ids(table, top_ids)

    def milvus_vector_search(self, query: str, table: str, top_k: int = 3) -> list[dict]:
        if self.vector_store is None:
            from tools.milvus_store import MilvusVectorStore

            self.vector_store = MilvusVectorStore()
        query_vector = self._milvus_embed(query)
        hits = self.vector_store.search(table, query_vector, top_k)
        if not hits:
            raise MilvusRetrievalError("Milvus collection returned no vector hits")

        ids = [int(hit["id"]) for hit in hits]
        rows = self._get_rows_by_ids(table, ids)
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

    def _milvus_embed(self, query: str) -> list[float]:
        if self.embedding_client is None:
            from tools.knowledge_sync import SiliconFlowEmbeddingClient

            self.embedding_client = SiliconFlowEmbeddingClient()
        vectors = self.embedding_client.embed([query])
        if len(vectors) != 1:
            raise MilvusRetrievalError("Embedding service returned no query vector")
        return vectors[0]

    def _embed(self, text: str) -> Optional[list[float]]:
        """调用硅基流动 BAAI/bge-m3 embedding API 获取语义向量。"""
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
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
            print(f"[WARN] Embedding API 返回 {resp.status_code}: {resp.text[:200]}")
            return self._fallback_embed(text)
        except Exception as e:
            print(f"[WARN] Embedding API 异常: {e}")
            return self._fallback_embed(text)

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
    def keyword_search(keyword: str, table: str, limit: int = 3) -> list[dict]:
        """MySQL LIKE 精确关键词匹配。"""
        conn = pymysql.connect(**DB_CONFIG)
        try:
            with conn.cursor() as cur:
                like = f"%{keyword}%"
                if table == "tb_regulation":
                    cur.execute(
                        "SELECT id, law_name, article, content, category, keywords "
                        "FROM tb_regulation "
                        "WHERE category LIKE %s OR law_name LIKE %s OR keywords LIKE %s "
                        "OR content LIKE %s LIMIT %s",
                        (like, like, like, like, limit),
                    )
                    return [{"id": r[0], "title": f"{r[1]} {r[2]}", "description": r[3],
                             "category": r[4], "keywords": r[5]} for r in cur.fetchall()]
                if table == "tb_hazard_case":
                    cur.execute(
                        "SELECT id, title, description, category, severity, city, "
                        "casualties, cause, rectification, regulation_ref, verdict "
                        "FROM tb_hazard_case "
                        "WHERE category LIKE %s OR title LIKE %s OR description LIKE %s "
                        "LIMIT %s",
                        (like, like, like, limit),
                    )
                    rows = cur.fetchall()
                    results = []
                    for row in rows:
                        results.append({
                            "table": "tb_hazard_case",
                            "id": row[0],
                            "title": row[1],
                            "description": row[2],
                            "category": row[3],
                            "severity": row[4],
                            "city": row[5],
                            "casualties": row[6],
                            "cause": row[7],
                            "rectification": row[8],
                            "regulation_ref": row[9],
                            "verdict": row[10],
                        })
                    return results
                else:
                    cur.execute(
                        "SELECT id, title, content, category, region, source "
                        "FROM tb_hazard_knowledge "
                        "WHERE title LIKE %s OR content LIKE %s LIMIT %s",
                        (like, like, limit),
                    )
                    rows = cur.fetchall()
                    return [
                        {
                            "table": "tb_hazard_knowledge",
                            "id": r[0],
                            "title": r[1],
                            "content": r[2],
                            "category": r[3],
                            "region": r[4],
                            "source": r[5],
                        }
                        for r in rows
                    ]
        finally:
            conn.close()

    # ====== 混合检索 ======

    def hybrid_search(self, query: str, table: str = "tb_hazard_case",
                      vector_k: int = 3, keyword_k: int = 3) -> str:
        """
        混合检索入口：向量 + 关键词 → 合并去重 → 格式化输出。
        """
        if table not in TABLE_TO_COLLECTION:
            raise ValueError(f"Unsupported retrieval table: {table}")

        # 并行两种检索
        try:
            vector_results = self.vector_search(query, table, top_k=vector_k)
        except MilvusRetrievalError as exc:
            return f"Milvus 向量检索不可用：{exc}。请暂时使用 MySQL 检索或稍后重试。"
        keyword_results = self.keyword_search(query, table, limit=keyword_k)

        # 合并去重（按 id）
        seen = set()
        merged = []
        for r in keyword_results:
            if r["id"] not in seen:
                seen.add(r["id"])
                r["match_type"] = "关键词"
                merged.append(r)
        for r in vector_results:
            rid = r.get("id")
            if rid not in seen:
                seen.add(rid)
                r["match_type"] = "语义"
                merged.append(r)

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
    def _get_rows_by_ids(table: str, ids: list[int]) -> list[dict]:
        """按 ID 列表回查完整字段。"""
        if not ids:
            return []
        conn = pymysql.connect(**DB_CONFIG)
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
        finally:
            conn.close()

    # ====== 缓存 ======

    def _fetch_all(self, table: str) -> list:
        """获取表中所有记录 (id, title, content/description)。"""
        conn = pymysql.connect(**DB_CONFIG)
        try:
            with conn.cursor() as cur:
                if table == "tb_regulation":
                    cur.execute("SELECT id, law_name, CONCAT(article, ' ', content) FROM tb_regulation")
                elif table == "tb_hazard_case":
                    cur.execute("SELECT id, title, CONCAT(description, ' ', cause) FROM tb_hazard_case")
                else:
                    cur.execute("SELECT id, title, content FROM tb_hazard_knowledge")
                return cur.fetchall()
        finally:
            conn.close()

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
