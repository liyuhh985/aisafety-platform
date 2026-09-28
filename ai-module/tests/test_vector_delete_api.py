import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import server


class VectorDeleteApiTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.token_patch = patch.object(
            server, "AI_INTERNAL_TOKEN", "test-token", create=True
        )
        self.store_patch = patch.object(
            server, "MilvusVectorStore", return_value=self.store, create=True
        )
        self.token_patch.start()
        self.store_patch.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.store_patch.stop()
        self.token_patch.stop()

    def test_authorized_request_deletes_exact_table_and_ids(self):
        response = self.client.post(
            "/api/ai/internal/vectors/delete",
            headers={"X-Internal-Token": "test-token"},
            json={"table": "tb_hazard_case", "ids": [42]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted_count": 1})
        self.store.delete_ids.assert_called_once_with("tb_hazard_case", [42])

    def test_missing_or_incorrect_internal_token_is_rejected(self):
        for headers in ({}, {"X-Internal-Token": "wrong-token"}):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/api/ai/internal/vectors/delete",
                    headers=headers,
                    json={"table": "tb_hazard_case", "ids": [42]},
                )

                self.assertEqual(response.status_code, 401)

    def test_invalid_delete_payload_is_rejected(self):
        invalid_payloads = (
            {"table": "tb_unknown", "ids": [42]},
            {"table": "tb_hazard_case", "ids": []},
            {"table": "tb_hazard_case", "ids": [0]},
            {"table": "tb_hazard_case", "ids": list(range(1, 102))},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/ai/internal/vectors/delete",
                    headers={"X-Internal-Token": "test-token"},
                    json=payload,
                )

                self.assertEqual(response.status_code, 400)

    def test_malformed_delete_shape_returns_bad_request_not_validation_error(self):
        response = self.client.post(
            "/api/ai/internal/vectors/delete",
            headers={"X-Internal-Token": "test-token"},
            json={"table": "tb_hazard_case", "ids": "not-a-list"},
        )

        self.assertEqual(response.status_code, 400)

    def test_vector_store_failure_returns_sanitized_service_unavailable(self):
        self.store.delete_ids.side_effect = RuntimeError(
            "milvus password and host must not leak"
        )
        client = TestClient(server.app, raise_server_exceptions=False)

        response = client.post(
            "/api/ai/internal/vectors/delete",
            headers={"X-Internal-Token": "test-token"},
            json={"table": "tb_regulation", "ids": [7]},
        )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("password", response.text.lower())
        self.assertEqual(response.json()["detail"], "Vector store unavailable")


if __name__ == "__main__":
    unittest.main()
