import unittest

from core.report_context import build_report_context


class ReportContextTests(unittest.TestCase):
    def test_report_context_includes_regulation_evidence(self):
        context = build_report_context(
            "施工现场临时用电隐患",
            {
                "vision": {"hazard_category": "施工安全", "severity": "高"},
                "cases": "案例库结果",
                "policy": "政策库结果",
                "regulations": "法规库结果：某法规第四十一条",
            },
        )

        self.assertIn("法规库结果：某法规第四十一条", context)
        self.assertIn("## 法规依据", context)

    def test_report_context_preserves_regulation_fallback_message(self):
        context = build_report_context(
            "施工现场临时用电隐患",
            {
                "vision": {"hazard_category": "施工安全", "severity": "高"},
                "regulations": "暂未检索到明确法规条款，建议人工复核",
            },
        )

        self.assertIn("暂未检索到明确法规条款，建议人工复核", context)


if __name__ == "__main__":
    unittest.main()
