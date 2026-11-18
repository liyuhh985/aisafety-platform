import importlib
import os
import unittest
from unittest.mock import patch


class MilvusConfigTests(unittest.TestCase):
    ENV_DEFAULTS = {
        "VECTOR_BACKEND": "mysql",
        "MILVUS_ENABLED": "false",
        "MILVUS_HOST": "127.0.0.1",
        "MILVUS_PORT": "19530",
        "MILVUS_ALIAS": "safety_platform",
        "MILVUS_USER": "root",
        "MILVUS_PASSWORD": "test-secret",
        "MILVUS_EMBEDDING_DIM": "1024",
        "MILVUS_TIMEOUT_SECONDS": "5",
        "MILVUS_FALLBACK_TO_MYSQL": "true",
        "MILVUS_CASE_COLLECTION": "hazard_cases",
        "MILVUS_POLICY_COLLECTION": "hazard_policies",
        "MILVUS_REGULATION_COLLECTION": "hazard_regulations",
    }

    def load_config(self, **overrides):
        values = {**self.ENV_DEFAULTS, **overrides}
        with patch.dict(os.environ, values, clear=False):
            import config
            return importlib.reload(config)

    def test_milvus_defaults_are_typed_and_named(self):
        config = self.load_config()

        self.assertEqual(config.VECTOR_BACKEND, "mysql")
        self.assertFalse(config.MILVUS_ENABLED)
        self.assertEqual(config.MILVUS_HOST, "127.0.0.1")
        self.assertEqual(config.MILVUS_PORT, 19530)
        self.assertEqual(config.MILVUS_ALIAS, "safety_platform")
        self.assertEqual(config.MILVUS_USER, "root")
        self.assertEqual(config.MILVUS_PASSWORD, "test-secret")
        self.assertEqual(config.MILVUS_EMBEDDING_DIM, 1024)
        self.assertEqual(config.MILVUS_TIMEOUT_SECONDS, 5.0)
        self.assertTrue(config.MILVUS_FALLBACK_TO_MYSQL)
        self.assertEqual(config.MILVUS_CASE_COLLECTION, "hazard_cases")
        self.assertEqual(config.MILVUS_POLICY_COLLECTION, "hazard_policies")
        self.assertEqual(config.MILVUS_REGULATION_COLLECTION, "hazard_regulations")

    def test_boolean_and_numeric_environment_values_are_parsed(self):
        config = self.load_config(
            VECTOR_BACKEND="milvus",
            MILVUS_ENABLED="TRUE",
            MILVUS_PORT="19531",
            MILVUS_EMBEDDING_DIM="1536",
            MILVUS_TIMEOUT_SECONDS="2.5",
            MILVUS_FALLBACK_TO_MYSQL="0",
        )

        self.assertEqual(config.VECTOR_BACKEND, "milvus")
        self.assertTrue(config.MILVUS_ENABLED)
        self.assertEqual(config.MILVUS_PORT, 19531)
        self.assertEqual(config.MILVUS_EMBEDDING_DIM, 1536)
        self.assertEqual(config.MILVUS_TIMEOUT_SECONDS, 2.5)
        self.assertFalse(config.MILVUS_FALLBACK_TO_MYSQL)

    def test_unsupported_vector_backend_fails_with_clear_error(self):
        with patch.dict(os.environ, {**self.ENV_DEFAULTS, "VECTOR_BACKEND": "redis"}, clear=False):
            import config
            with self.assertRaisesRegex(ValueError, "VECTOR_BACKEND"):
                importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
