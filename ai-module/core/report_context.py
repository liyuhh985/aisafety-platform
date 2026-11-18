"""报告上下文的拼装（纯函数，无副作用）。

原先挂在 Orchestrator 上；2026-09-25 合并后 Orchestrator 被移除，
这里保留一份给评测工具（eval_rag）和它的测试使用。
"""
import json


def build_report_context(query: str, results: dict) -> str:
    parts = []
    if results.get("vision"):
        v = results["vision"]
        parts.append("## 视觉识别结果\n" + (
            json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, dict) else str(v)))
    if results.get("cases"):
        parts.append("## 相关案例\n" + str(results["cases"]))
    if results.get("policy"):
        parts.append("## 政策法规\n" + str(results["policy"]))
    if results.get("regulations"):
        parts.append("## 法规依据\n" + str(results["regulations"]))
    return "用户请求: " + query + "\n\n" + "\n\n".join(parts)
