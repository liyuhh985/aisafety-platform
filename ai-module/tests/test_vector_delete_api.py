import unittest
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

import server

# 端点未实现：Python 侧没有 /api/ai/internal/vectors/delete 这个路由（当前返回 404）。
# 它归属另一条线 —— Java 侧的向量删除 outbox 已经写好，Python 侧的端点还没补。
# 首次记录：2026-09-28。
# strict=True：端点真被实现之后，这里会以 XPASS 失败的形式提醒回来拆掉 xfail，
# 符合本项目"不要静默留缺口"的原则。
XFAIL_REASON = (
    "internal/vectors/delete 端点未实现：Python 侧没有该路由（404）；"
    "属 Java 向量删除 outbox 那条线，Python 端点待补（2026-09-28 首次记录）"
)

pytestmark = pytest.mark.xfail(strict=True, reason=XFAIL_REASON)


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

    # unittest 的 subTest 不会把父测试判为失败（子测试失败单独上报），
    # 所以端点缺失时父测试仍然是 pass，strict 会把这里变成 XPASS 失败。
    # 用 run=False 让它按"已知缺口"直接记 xfail，不参与 strict 判定。
    @pytest.mark.xfail(run=False, reason=XFAIL_REASON)
    def test_missing_or_incorrect_internal_token_is_rejected(self):
        for headers in ({}, {"X-Internal-Token": "wrong-token"}):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/api/ai/internal/vectors/delete",
                    headers=headers,
                    json={"table": "tb_hazard_case", "ids": [42]},
                )

                self.assertEqual(response.status_code, 401)

    # unittest 的 subTest 不会把父测试判为失败（子测试失败单独上报），
    # 所以端点缺失时父测试仍然是 pass，strict 会把这里变成 XPASS 失败。
    # 用 run=False 让它按"已知缺口"直接记 xfail，不参与 strict 判定。
    @pytest.mark.xfail(run=False, reason=XFAIL_REASON)
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
