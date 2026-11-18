import sys
import types
import unittest
from unittest.mock import patch

from tools.hybrid_search import TABLE_TO_COLLECTION
from tools.milvus_store import (
    MilvusDimensionError,
    MilvusSchemaError,
    MilvusVectorStore,
)


class FakeSchema:
    def __init__(self):
        self.fields = []

    def add_field(self, **kwargs):
        self.fields.append(kwargs)


class FakeIndexParams:
    def __init__(self):
        self.indexes = []

    def add_index(self, **kwargs):
        self.indexes.append(kwargs)


class FakeMilvusClient:
    def __init__(self, search_hits=None):
        self.collections = {}
        self.created_collections = []
        self.upsert_calls = []
        self.delete_calls = []
        self.search_calls = []
        self.search_hits = search_hits or [[]]
        self.collection_descriptions = {}
        self.collection_indexes = {}
        self.query_calls = []
        self.drop_calls = []

    def has_collection(self, collection_name):
        return collection_name in self.collections

    def create_schema(self, **kwargs):
        schema = FakeSchema()
        self.last_schema_options = kwargs
        return schema

    def prepare_index_params(self):
        return FakeIndexParams()

    def create_collection(self, **kwargs):
        self.created_collections.append(kwargs)
        self.collections[kwargs["collection_name"]] = kwargs

    def describe_collection(self, collection_name):
        return self.collection_descriptions[collection_name]

    def list_indexes(self, collection_name, field_name=None):
        return [
            index["index_name"]
            for index in self.collection_indexes.get(collection_name, [])
        ]

    def describe_index(self, collection_name, index_name):
        for index in self.collection_indexes[collection_name]:
            if index["index_name"] == index_name:
                return index
        raise KeyError(index_name)

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return [{"doc_id": 1, "content_hash": "hash-1"}]

    def drop_collection(self, **kwargs):
        self.drop_calls.append(kwargs)
        self.collections.pop(kwargs["collection_name"], None)

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_hits


class MilvusStoreTests(unittest.TestCase):
    def setUp(self):
        self.data_types = types.SimpleNamespace(
            INT64="INT64",
            VARCHAR="VARCHAR",
            FLOAT_VECTOR="FLOAT_VECTOR",
        )
        self.pymilvus = types.SimpleNamespace(DataType=self.data_types)

    def test_ensure_collections_creates_all_mapped_cosine_collections(self):
        client = FakeMilvusClient()
        store = MilvusVectorStore(client=client, embedding_dim=3)

        with patch.dict(sys.modules, {"pymilvus": self.pymilvus}):
            store.ensure_collections()

        self.assertEqual(
            [call["collection_name"] for call in client.created_collections],
            list(TABLE_TO_COLLECTION.values()),
        )
        for call in client.created_collections:
            fields = call["schema"].fields
            self.assertEqual(fields[0]["field_name"], "doc_id")
            self.assertEqual(fields[0]["datatype"], "INT64")
            self.assertTrue(fields[0]["is_primary"])
            self.assertEqual(fields[1]["field_name"], "content_hash")
            self.assertEqual(fields[1]["max_length"], 64)
            self.assertEqual(fields[2]["field_name"], "embedding")
            self.assertEqual(fields[2]["datatype"], "FLOAT_VECTOR")
            self.assertEqual(fields[2]["dim"], 3)
            self.assertEqual(call["index_params"].indexes[0]["metric_type"], "COSINE")

    def test_connect_passes_configured_user_and_password(self):
        captured = {}

        class RecordingClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        store = MilvusVectorStore(
            host="milvus.example",
            port=19530,
            user="root",
            password="test-secret",
            embedding_dim=3,
        )
        module = types.SimpleNamespace(MilvusClient=RecordingClient)

        with patch.dict(sys.modules, {"pymilvus": module}):
            store.connect()

        self.assertEqual(captured["uri"], "http://milvus.example:19530")
        self.assertEqual(captured["user"], "root")
        self.assertEqual(captured["password"], "test-secret")

    def test_upsert_maps_ids_and_search_normalizes_hits(self):
        client = FakeMilvusClient(
            search_hits=[
                [
                    {"id": 2, "distance": 0.41, "entity": {"content_hash": "hash-2"}},
                    {"id": 1, "distance": 0.86, "entity": {"content_hash": "hash-1"}},
                ]
            ]
        )
        store = MilvusVectorStore(client=client, embedding_dim=3)

        store.upsert(
            "tb_hazard_case",
            [{"id": 7, "content_hash": "abc", "embedding": [0.1, 0.2, 0.3]}],
        )
        hits = store.search("tb_hazard_case", [0.3, 0.2, 0.1], top_k=2)

        self.assertEqual(client.upsert_calls[0]["collection_name"], "hazard_cases")
        self.assertEqual(client.upsert_calls[0]["data"][0]["doc_id"], 7)
        self.assertEqual(client.upsert_calls[0]["data"][0]["embedding"], [0.1, 0.2, 0.3])
        self.assertEqual(
            hits,
            [
                {"id": 2, "distance": 0.41, "content_hash": "hash-2"},
                {"id": 1, "distance": 0.86, "content_hash": "hash-1"},
            ],
        )
        self.assertEqual(client.search_calls[0]["limit"], 2)
        self.assertEqual(client.search_calls[0]["search_params"]["metric_type"], "COSINE")

    def test_search_normalizes_pymilvus_named_primary_key(self):
        client = FakeMilvusClient(
            search_hits=[
                [
                    {
                        "doc_id": 7,
                        "distance": 0.73,
                        "entity": {"content_hash": "hash-7"},
                    }
                ]
            ]
        )
        store = MilvusVectorStore(client=client, embedding_dim=3)

        hits = store.search("tb_hazard_case", [0.3, 0.2, 0.1], top_k=1)

        self.assertEqual(
            hits,
            [{"id": 7, "distance": 0.73, "content_hash": "hash-7"}],
        )

    def test_wrong_dimension_is_rejected_for_upsert_and_search(self):
        store = MilvusVectorStore(client=FakeMilvusClient(), embedding_dim=3)

        with self.assertRaises(MilvusDimensionError):
            store.upsert(
                "tb_hazard_case",
                [{"id": 1, "content_hash": "abc", "embedding": [0.1, 0.2]}],
            )
        with self.assertRaises(MilvusDimensionError):
            store.search("tb_hazard_case", [0.1, 0.2], top_k=1)

    def test_existing_collection_with_wrong_dimension_fails_fast(self):
        client = FakeMilvusClient()
        client.collections["hazard_cases"] = {"existing": True}
        client.collection_descriptions["hazard_cases"] = {
            "auto_id": False,
            "enable_dynamic_field": False,
            "fields": [
                {"name": "doc_id", "type": "INT64", "is_primary": True},
                {"name": "content_hash", "type": "VARCHAR", "params": {"max_length": "64"}},
                {
                    "name": "embedding",
                    "type": "FLOAT_VECTOR",
                    "params": {"dim": "2"},
                },
            ],
        }
        client.collection_indexes["hazard_cases"] = [
            {"index_name": "embedding_index", "index_type": "AUTOINDEX", "metric_type": "COSINE"}
        ]
        store = MilvusVectorStore(client=client, embedding_dim=3)

        with patch.dict(sys.modules, {"pymilvus": self.pymilvus}):
            with self.assertRaises(MilvusSchemaError):
                store.ensure_collections()

    def test_existing_collection_with_hnsw_cosine_index_is_accepted(self):
        client = FakeMilvusClient()
        client.collections["hazard_cases"] = {"existing": True}
        client.collection_descriptions["hazard_cases"] = {
            "auto_id": False,
            "enable_dynamic_field": False,
            "fields": [
                {"name": "doc_id", "type": "INT64", "is_primary": True},
                {"name": "content_hash", "type": "VARCHAR", "params": {"max_length": "64"}},
                {
                    "name": "embedding",
                    "type": "FLOAT_VECTOR",
                    "params": {"dim": "3"},
                },
            ],
        }
        client.collection_indexes["hazard_cases"] = [
            {"index_name": "embedding_index", "index_type": "HNSW", "metric_type": "COSINE"}
        ]
        store = MilvusVectorStore(client=client, embedding_dim=3)

        with patch.dict(sys.modules, {"pymilvus": self.pymilvus}):
            store.ensure_collections()

        self.assertEqual(
            [call["collection_name"] for call in client.created_collections],
            ["hazard_policies", "hazard_regulations"],
        )

    def test_store_operations_reject_invalid_table_names(self):
        store = MilvusVectorStore(client=FakeMilvusClient(), embedding_dim=3)

        with self.assertRaises(ValueError):
            store.upsert("tb_unknown", [])
        with self.assertRaises(ValueError):
            store.delete_ids("tb_unknown", [1])
        with self.assertRaises(ValueError):
            store.search("tb_unknown", [0.1, 0.2, 0.3], top_k=1)

    def test_get_content_hashes_reads_only_requested_ids(self):
        client = FakeMilvusClient()
        store = MilvusVectorStore(client=client, embedding_dim=3)

        hashes = store.get_content_hashes("tb_hazard_case", [1, 2])

        self.assertEqual(hashes, {1: "hash-1"})
        self.assertEqual(client.query_calls[0]["collection_name"], "hazard_cases")
        self.assertIn("doc_id in [1,2]", client.query_calls[0]["filter"])

    def test_recreate_collection_drops_and_recreates_only_selected_collection(self):
        client = FakeMilvusClient()
        client.collections["hazard_cases"] = {"existing": True}
        store = MilvusVectorStore(client=client, embedding_dim=3)

        with patch.dict(sys.modules, {"pymilvus": self.pymilvus}):
            store.recreate_collection("tb_hazard_case")

        self.assertEqual(client.drop_calls, [{"collection_name": "hazard_cases"}])
        self.assertEqual(
            [call["collection_name"] for call in client.created_collections],
            ["hazard_cases"],
        )


if __name__ == "__main__":
    unittest.main()
