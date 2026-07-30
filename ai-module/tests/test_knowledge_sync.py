import hashlib
import unittest

from tools.knowledge_sync import (
    EmbeddingServiceError,
    KnowledgeSynchronizer,
    MySQLKnowledgeReader,
    SiliconFlowEmbeddingClient,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query):
        self.executed.append(query)

    def fetchall(self):
        return self.rows

    def fetchmany(self, size):
        rows = self.rows[self.offset : self.offset + size]
        self.offset += len(rows)
        return rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class FakeReader:
    def __init__(self, records):
        self.records = records

    def read(self, source):
        return list(self.records[source])


class FakeEmbedder:
    def __init__(self, vectors=None, error=None):
        self.vectors = vectors or []
        self.error = error
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.error:
            raise self.error
        return self.vectors[: len(texts)]


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        return self.body


class FakeStore:
    def __init__(self, hashes=None):
        self.hashes = hashes or {}
        self.recreate_calls = []
        self.upsert_calls = []

    def get_content_hashes(self, table, doc_ids):
        return {doc_id: self.hashes[doc_id] for doc_id in doc_ids if doc_id in self.hashes}

    def recreate_collection(self, table):
        self.recreate_calls.append(table)

    def upsert(self, table, records):
        self.upsert_calls.append((table, records))


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []

    def info(self, message, *args):
        self.info_messages.append(message % args)

    def error(self, message, *args):
        self.error_messages.append(message % args)


class KnowledgeSyncTests(unittest.TestCase):
    def test_mysql_reader_normalizes_source_text_and_hashes_it(self):
        connection = FakeConnection([(7, "  标题 ", "描述", "原因", "整改")])
        reader = MySQLKnowledgeReader(connection_factory=lambda **kwargs: connection)

        records = reader.read("case")

        self.assertEqual(records[0]["id"], 7)
        self.assertEqual(records[0]["text"], "标题 描述 原因 整改")
        self.assertEqual(
            records[0]["content_hash"],
            hashlib.sha256("标题 描述 原因 整改".encode("utf-8")).hexdigest(),
        )
        self.assertTrue(connection.closed)
        self.assertIn("tb_hazard_case", connection.cursor_instance.executed[0])

    def test_mysql_reader_streams_bounded_batches(self):
        connection = FakeConnection(
            [
                (1, "标题1", "内容1", "原因1", "整改1"),
                (2, "标题2", "内容2", "原因2", "整改2"),
            ]
        )
        reader = MySQLKnowledgeReader(connection_factory=lambda **kwargs: connection)

        batches = list(reader.iter_batches("case", batch_size=1))

        self.assertEqual([[record["id"] for record in batch] for batch in batches], [[1], [2]])
        self.assertTrue(connection.closed)

    def test_mysql_reader_maps_policy_and_regulation_fields(self):
        policy_connection = FakeConnection([(1, "政策", "内容")])
        policy_reader = MySQLKnowledgeReader(
            connection_factory=lambda **kwargs: policy_connection
        )
        regulation_connection = FakeConnection([(2, "法律", "第1条", "条文", "消防")])
        regulation_reader = MySQLKnowledgeReader(
            connection_factory=lambda **kwargs: regulation_connection
        )

        policy = policy_reader.read("policy")[0]
        regulation = regulation_reader.read("regulation")[0]

        self.assertEqual(policy["text"], "政策 内容")
        self.assertEqual(regulation["text"], "法律 第1条 条文 消防")

    def test_incremental_sync_skips_unchanged_and_upserts_changed_records(self):
        records = {
            "case": [
                {"id": 1, "text": "unchanged", "content_hash": "same"},
                {"id": 2, "text": "changed", "content_hash": "new"},
            ]
        }
        reader = FakeReader(records)
        embedder = FakeEmbedder(vectors=[[0.1, 0.2, 0.3]])
        store = FakeStore(hashes={1: "same", 2: "old"})
        synchronizer = KnowledgeSynchronizer(reader, embedder, store, batch_size=2)

        stats = synchronizer.synchronize("case")

        self.assertEqual(stats.skipped_count, 1)
        self.assertEqual(stats.upsert_count, 1)
        self.assertEqual(embedder.calls, [["changed"]])
        self.assertEqual(store.upsert_calls[0][1][0]["id"], 2)
        self.assertEqual(store.upsert_calls[0][1][0]["embedding"], [0.1, 0.2, 0.3])

    def test_rebuild_recreates_only_selected_collection(self):
        reader = FakeReader(
            {"policy": [{"id": 9, "text": "policy", "content_hash": "hash"}]}
        )
        embedder = FakeEmbedder(vectors=[[0.1, 0.2, 0.3]])
        store = FakeStore(hashes={9: "old"})
        synchronizer = KnowledgeSynchronizer(reader, embedder, store, batch_size=1)

        stats = synchronizer.synchronize("policy", rebuild=True)

        self.assertEqual(store.recreate_calls, ["tb_hazard_knowledge"])
        self.assertEqual(stats.skipped_count, 0)
        self.assertEqual(stats.upsert_count, 1)

    def test_embedding_failure_stops_sync_without_upsert(self):
        reader = FakeReader(
            {"regulation": [{"id": 4, "text": "law", "content_hash": "hash"}]}
        )
        embedder = FakeEmbedder(error=RuntimeError("service unavailable"))
        store = FakeStore()
        logger = FakeLogger()
        synchronizer = KnowledgeSynchronizer(
            reader, embedder, store, batch_size=1, logger=logger
        )

        with self.assertRaises(EmbeddingServiceError):
            synchronizer.synchronize("regulation")

        self.assertEqual(store.upsert_calls, [])
        self.assertIn("failures=1", logger.info_messages[0])

    def test_embedding_client_raises_on_service_failure_without_fallback_vector(self):
        client = SiliconFlowEmbeddingClient(
            api_key="test-key",
            http_post=lambda *args, **kwargs: FakeResponse(503, {"error": "down"}),
        )

        with self.assertRaises(EmbeddingServiceError):
            client.embed(["text"])


if __name__ == "__main__":
    unittest.main()
