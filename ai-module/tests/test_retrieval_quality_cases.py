import os
import statistics
import time
import unittest

from tools.hybrid_search import HybridSearcher


RETRIEVAL_EVALUATION_CASES = (
    {"query": "消防通道被占用", "source": "tb_hazard_case", "acceptable_ids": (6,)},
    {"query": "消防通道堵塞", "source": "tb_hazard_knowledge", "acceptable_ids": (1,)},
    {"query": "建筑设计防火规范", "source": "tb_regulation", "acceptable_ids": (9, 10)},
    {"query": "施工现场脚手架坍塌", "source": "tb_hazard_case", "acceptable_ids": (10, 11)},
    {"query": "高处作业防护措施", "source": "tb_regulation", "acceptable_ids": (15, 16)},
    {"query": "电线裸露隐患", "source": "tb_hazard_knowledge", "acceptable_ids": (8,)},
    {"query": "液化气罐泄漏爆燃", "source": "tb_hazard_case", "acceptable_ids": (13, 14, 15)},
    {"query": "低压配电用电安全", "source": "tb_regulation", "acceptable_ids": (19, 20)},
    {"query": "交通信号灯故障", "source": "tb_hazard_knowledge", "acceptable_ids": (4,)},
    {"query": "路面塌陷隐患", "source": "tb_hazard_knowledge", "acceptable_ids": (3,)},
)


class RetrievalQualityCaseTests(unittest.TestCase):
    def test_fixed_evaluation_set_has_ten_seeded_cases(self):
        self.assertEqual(len(RETRIEVAL_EVALUATION_CASES), 10)
        for case in RETRIEVAL_EVALUATION_CASES:
            self.assertTrue(case["query"])
            self.assertIn(case["source"], {
                "tb_hazard_case",
                "tb_hazard_knowledge",
                "tb_regulation",
            })
            self.assertTrue(case["acceptable_ids"])


@unittest.skipUnless(
    os.getenv("RUN_RETRIEVAL_QUALITY") == "1",
    "set RUN_RETRIEVAL_QUALITY=1 after Milvus backfill to run live quality checks",
)
class LiveRetrievalQualityTests(unittest.TestCase):
    def test_milvus_top_three_contains_seeded_expected_document(self):
        searcher = HybridSearcher(
            vector_backend="milvus",
            milvus_enabled=True,
            milvus_fallback_to_mysql=False,
        )
        for case in RETRIEVAL_EVALUATION_CASES:
            with self.subTest(query=case["query"]):
                results = searcher.vector_search(case["query"], case["source"], top_k=3)
                result_ids = {int(result["id"]) for result in results}
                self.assertTrue(result_ids.intersection(case["acceptable_ids"]))

    def test_vector_latency_records_p50_and_p95_for_both_backends(self):
        query = RETRIEVAL_EVALUATION_CASES[0]
        measurements = {}
        for backend in ("mysql", "milvus"):
            searcher = HybridSearcher(
                vector_backend=backend,
                milvus_enabled=backend == "milvus",
                milvus_fallback_to_mysql=False,
            )
            durations = []
            for _ in range(20):
                started = time.perf_counter()
                searcher.vector_search(query["query"], query["source"], top_k=3)
                durations.append((time.perf_counter() - started) * 1000)
            ordered = sorted(durations)
            measurements[backend] = {
                "p50_ms": statistics.median(ordered),
                "p95_ms": ordered[18],
            }
        self.assertEqual(set(measurements), {"mysql", "milvus"})


if __name__ == "__main__":
    unittest.main()
