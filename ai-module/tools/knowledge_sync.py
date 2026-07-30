"""Idempotently synchronize MySQL knowledge sources into Milvus."""

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass
from typing import Callable

import pymysql
import requests

from config import SF_API_KEY, SF_BASE_URL, SF_EMBED_MODEL
from db_config import DB_CONFIG
from tools.milvus_store import MilvusVectorStore

LOGGER = logging.getLogger(__name__)

SOURCE_DEFINITIONS = {
    "case": {
        "table": "tb_hazard_case",
        "query": (
            "SELECT id, title, description, cause, rectification "
            "FROM tb_hazard_case"
        ),
    },
    "policy": {
        "table": "tb_hazard_knowledge",
        "query": "SELECT id, title, content FROM tb_hazard_knowledge",
    },
    "regulation": {
        "table": "tb_regulation",
        "query": (
            "SELECT id, law_name, article, content, keywords "
            "FROM tb_regulation"
        ),
    },
}


class EmbeddingServiceError(RuntimeError):
    """Raised when the configured embedding service cannot produce vectors."""


@dataclass
class SyncStats:
    source: str
    table: str
    read_count: int = 0
    skipped_count: int = 0
    upsert_count: int = 0
    failure_count: int = 0


class MySQLKnowledgeReader:
    def __init__(
        self,
        connection_factory: Callable = pymysql.connect,
        db_config: dict | None = None,
    ):
        self.connection_factory = connection_factory
        self.db_config = db_config or DB_CONFIG

    def read(self, source: str) -> list[dict]:
        return [
            record
            for batch in self.iter_batches(source, batch_size=512)
            for record in batch
        ]

    def iter_batches(self, source: str, batch_size: int):
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        definition = self._definition(source)
        connection_options = {
            **self.db_config,
            "cursorclass": pymysql.cursors.SSCursor,
        }
        conn = self.connection_factory(**connection_options)
        try:
            with conn.cursor() as cursor:
                cursor.execute(definition["query"])
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    yield [self._record(source, row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _definition(source: str) -> dict:
        try:
            return SOURCE_DEFINITIONS[source]
        except KeyError as exc:
            raise ValueError(f"Unsupported knowledge source: {source}") from exc

    @classmethod
    def _record(cls, source: str, row) -> dict:
        if source == "case":
            doc_id, *parts = row
        elif source == "policy":
            doc_id, *parts = row
        elif source == "regulation":
            doc_id, *parts = row
        else:
            raise ValueError(f"Unsupported knowledge source: {source}")

        text = cls.normalize_text(parts)
        return {
            "id": int(doc_id),
            "text": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def normalize_text(parts) -> str:
        normalized_parts = []
        for part in parts:
            if part is None:
                continue
            value = " ".join(str(part).split())
            if value:
                normalized_parts.append(value)
        return " ".join(normalized_parts)


class SiliconFlowEmbeddingClient:
    def __init__(
        self,
        base_url: str = SF_BASE_URL,
        api_key: str = SF_API_KEY,
        model: str = SF_EMBED_MODEL,
        timeout_seconds: float = 30,
        http_post: Callable = requests.post,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.http_post = http_post

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self.http_post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": texts},
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            raise EmbeddingServiceError("Embedding service request failed") from exc

        if response.status_code != 200:
            raise EmbeddingServiceError(
                f"Embedding service returned HTTP {response.status_code}"
            )
        try:
            items = response.json()["data"]
            items = sorted(items, key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingServiceError("Embedding service returned invalid data") from exc
        if len(vectors) != len(texts):
            raise EmbeddingServiceError("Embedding service returned an unexpected vector count")
        return vectors


class KnowledgeSynchronizer:
    def __init__(self, reader, embedder, store, batch_size: int = 32, logger=None):
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.reader = reader
        self.embedder = embedder
        self.store = store
        self.batch_size = batch_size
        self.logger = logger or LOGGER

    def synchronize(self, source: str, rebuild: bool = False) -> SyncStats:
        definition = MySQLKnowledgeReader._definition(source)
        table = definition["table"]
        stats = SyncStats(source=source, table=table)
        if rebuild:
            self.store.recreate_collection(table)

        try:
            active_batch_size = 0
            for records in self._iter_batches(source):
                stats.read_count += len(records)
                active_batch_size = len(records)
                if rebuild:
                    pending = records
                else:
                    existing_hashes = self.store.get_content_hashes(
                        table, [record["id"] for record in records]
                    )
                    pending = [
                        record
                        for record in records
                        if existing_hashes.get(record["id"]) != record["content_hash"]
                    ]
                    stats.skipped_count += len(records) - len(pending)
                if not pending:
                    active_batch_size = 0
                    continue

                texts = [record["text"] for record in pending]
                try:
                    vectors = self.embedder.embed(texts)
                except Exception as exc:
                    stats.failure_count += len(pending)
                    self.logger.error(
                        "Embedding failed for source=%s batch_size=%d error_type=%s",
                        source,
                        len(pending),
                        type(exc).__name__,
                    )
                    raise EmbeddingServiceError(
                        f"Embedding failed for source {source}; use VECTOR_BACKEND=mysql until it recovers"
                    ) from exc
                if len(vectors) != len(pending):
                    stats.failure_count += len(pending)
                    raise EmbeddingServiceError(
                        f"Embedding returned {len(vectors)} vectors for {len(pending)} records"
                    )
                self.store.upsert(
                    table,
                    [
                        {
                            "id": record["id"],
                            "content_hash": record["content_hash"],
                            "embedding": vector,
                        }
                        for record, vector in zip(pending, vectors)
                    ],
                )
                stats.upsert_count += len(pending)
                active_batch_size = 0
        except EmbeddingServiceError:
            self._log_stats(stats)
            raise
        except Exception:
            stats.failure_count += active_batch_size
            self._log_stats(stats)
            raise

        self._log_stats(stats)
        return stats

    def _iter_batches(self, source: str):
        iter_batches = getattr(self.reader, "iter_batches", None)
        if iter_batches is not None:
            yield from iter_batches(source, self.batch_size)
            return
        records = self.reader.read(source)
        for offset in range(0, len(records), self.batch_size):
            yield records[offset : offset + self.batch_size]

    def _log_stats(self, stats: SyncStats) -> None:
        self.logger.info(
            "Knowledge sync source=%s read=%d skipped=%d upsert=%d failures=%d",
            stats.source,
            stats.read_count,
            stats.skipped_count,
            stats.upsert_count,
            stats.failure_count,
        )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Synchronize MySQL knowledge into Milvus")
    parser.add_argument(
        "--source",
        choices=["all", *SOURCE_DEFINITIONS.keys()],
        default="all",
    )
    parser.add_argument("--rebuild", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    synchronizer = KnowledgeSynchronizer(
        MySQLKnowledgeReader(),
        SiliconFlowEmbeddingClient(),
        MilvusVectorStore(),
    )
    try:
        synchronizer.store.ensure_collections()
        sources = SOURCE_DEFINITIONS if args.source == "all" else {args.source: SOURCE_DEFINITIONS[args.source]}
        for source in sources:
            synchronizer.synchronize(source, rebuild=args.rebuild)
        return 0
    except EmbeddingServiceError as exc:
        LOGGER.error("Knowledge sync stopped: %s", exc)
        return 1
    except Exception as exc:
        LOGGER.error("Knowledge sync stopped error_type=%s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
