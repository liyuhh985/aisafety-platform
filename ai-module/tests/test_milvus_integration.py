import os
import unittest

from tools.hybrid_search import TABLE_TO_COLLECTION
from tools.milvus_store import MilvusVectorStore


@unittest.skipUnless(
    os.getenv("RUN_MILVUS_INTEGRATION") == "1",
    "set RUN_MILVUS_INTEGRATION=1 to run against a live Milvus service",
)
class MilvusIntegrationTests(unittest.TestCase):
    def test_healthcheck_and_collection_creation(self):
        store = MilvusVectorStore()

        self.assertTrue(store.healthcheck())
        store.ensure_collections()
        collections = set(store.client.list_collections())

        self.assertTrue(set(TABLE_TO_COLLECTION.values()).issubset(collections))


if __name__ == "__main__":
    unittest.main()
