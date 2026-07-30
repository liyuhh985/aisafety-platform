"""Milvus collection adapter for the public knowledge sources."""

from config import (
    MILVUS_ALIAS,
    MILVUS_EMBEDDING_DIM,
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_TIMEOUT_SECONDS,
)
from tools.hybrid_search import TABLE_TO_COLLECTION


class MilvusDimensionError(ValueError):
    """Raised when a vector does not match the configured collection dimension."""


class MilvusVectorStore:
    def __init__(
        self,
        client=None,
        host: str = MILVUS_HOST,
        port: int = MILVUS_PORT,
        alias: str = MILVUS_ALIAS,
        timeout_seconds: float = MILVUS_TIMEOUT_SECONDS,
        embedding_dim: int = MILVUS_EMBEDDING_DIM,
    ):
        if embedding_dim <= 0:
            raise ValueError("MILVUS_EMBEDDING_DIM must be positive")
        self.client = client
        self.host = host
        self.port = port
        self.alias = alias
        self.timeout_seconds = timeout_seconds
        self.embedding_dim = embedding_dim

    def connect(self) -> None:
        """Create the SDK client lazily so importing this module never connects."""
        if self.client is not None:
            return
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError(
                "pymilvus is required to connect to Milvus; install the pinned requirements"
            ) from exc

        self.client = MilvusClient(
            uri=f"http://{self.host}:{self.port}",
            timeout=self.timeout_seconds,
        )

    def ensure_collections(self) -> None:
        """Create the three logical collections and their cosine indexes if absent."""
        self.connect()
        data_type = self._data_type()
        for collection_name in TABLE_TO_COLLECTION.values():
            if self.client.has_collection(collection_name=collection_name):
                continue

            schema = self.client.create_schema(
                auto_id=False,
                enable_dynamic_field=False,
            )
            schema.add_field(
                field_name="doc_id",
                datatype=data_type.INT64,
                is_primary=True,
                auto_id=False,
            )
            schema.add_field(
                field_name="content_hash",
                datatype=data_type.VARCHAR,
                max_length=64,
            )
            schema.add_field(
                field_name="embedding",
                datatype=data_type.FLOAT_VECTOR,
                dim=self.embedding_dim,
            )

            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type="AUTOINDEX",
                metric_type="COSINE",
            )
            self.client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )

    def healthcheck(self) -> bool:
        try:
            self.connect()
            self.client.list_collections()
            return True
        except Exception:
            return False

    def upsert(self, table: str, records: list[dict]) -> None:
        collection_name = self._collection_for(table)
        if not records:
            return

        data = []
        for record in records:
            doc_id = record.get("id", record.get("doc_id"))
            if doc_id is None:
                raise ValueError("Milvus upsert records require id or doc_id")
            content_hash = str(record.get("content_hash", ""))
            if len(content_hash) > 64:
                raise ValueError("content_hash must be at most 64 characters")
            embedding = record.get("embedding")
            self._validate_vector(embedding)
            data.append(
                {
                    "doc_id": int(doc_id),
                    "content_hash": content_hash,
                    "embedding": embedding,
                }
            )

        self.connect()
        self.client.upsert(collection_name=collection_name, data=data)

    def delete_ids(self, table: str, doc_ids: list[int]) -> None:
        collection_name = self._collection_for(table)
        if not doc_ids:
            return
        self.connect()
        self.client.delete(
            collection_name=collection_name,
            ids=[int(doc_id) for doc_id in doc_ids],
        )

    def search(self, table: str, query_vector: list[float], top_k: int) -> list[dict]:
        collection_name = self._collection_for(table)
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self._validate_vector(query_vector)
        self.connect()
        raw_results = self.client.search(
            collection_name=collection_name,
            data=[query_vector],
            limit=top_k,
            output_fields=["content_hash"],
            search_params={"metric_type": "COSINE"},
        )
        if not raw_results:
            return []
        hits = raw_results[0] if isinstance(raw_results[0], list) else raw_results
        return [self._normalize_hit(hit) for hit in hits]

    @staticmethod
    def _data_type():
        try:
            from pymilvus import DataType
        except ImportError as exc:
            raise RuntimeError(
                "pymilvus is required to create Milvus collections"
            ) from exc
        return DataType

    @staticmethod
    def _collection_for(table: str) -> str:
        try:
            return TABLE_TO_COLLECTION[table]
        except KeyError as exc:
            raise ValueError(f"Unsupported retrieval table: {table}") from exc

    def _validate_vector(self, vector: list[float]) -> None:
        if vector is None or len(vector) != self.embedding_dim:
            actual_dim = 0 if vector is None else len(vector)
            raise MilvusDimensionError(
                f"Vector dimension mismatch: expected {self.embedding_dim}, got {actual_dim}"
            )

    @staticmethod
    def _value(hit, key, default=None):
        if isinstance(hit, dict):
            return hit.get(key, default)
        return getattr(hit, key, default)

    @classmethod
    def _normalize_hit(cls, hit) -> dict:
        entity = cls._value(hit, "entity", {}) or {}
        content_hash = cls._value(entity, "content_hash", "")
        return {
            "id": int(cls._value(hit, "id")),
            "distance": float(cls._value(hit, "distance")),
            "content_hash": content_hash or "",
        }
