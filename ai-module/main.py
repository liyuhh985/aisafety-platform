"""
多 Agent 协同主入口。
用法:
  python main.py                    # 交互模式
  python main.py <图片路径>          # 分析图片
  python main.py <图片路径> "隐患描述"  # 图片 + 文字
"""
import sys

from agents import (
    create_router_agent,
    create_vision_agent,
    create_retrieval_agent,
    create_report_agent,
)
from core import Orchestrator
from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL


def build_orchestrator() -> Orchestrator:
    orch = Orchestrator(base_url=MIMO_BASE_URL, api_key=MIMO_API_KEY, model=MIMO_MODEL)
    orch.register(create_router_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
    orch.register(create_vision_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
    orch.register(create_retrieval_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
    orch.register(create_report_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
    return orch


def main():
    orch = build_orchestrator()

    image_path = None
    user_text = "请分析这张图片中的安全隐患，并生成报告"

    if len(sys.argv) >= 2:
        image_path = sys.argv[1]
    if len(sys.argv) >= 3:
        user_text = sys.argv[2]

    print("=" * 60)
    print("  城市安全隐患分析平台 — 多 Agent 协同系统")
    print("=" * 60)
    print(f"  Model: {MIMO_MODEL}")
    if image_path:
        print(f"  Image: {image_path}")
    print(f"  Query:  {user_text}")
    print("=" * 60)

    results = orch.analyze(user_text, image_path=image_path, session_id="main-cli")

    print("\n" + "=" * 60)
    print("  最终输出")
    print("=" * 60)

    # 优先输出报告
    if results.get("report"):
        print(results["report"])
    elif results.get("vision"):
        print(results["vision"])
    else:
        print("无结果")

    return 0


if __name__ == "__main__":
    sys.exit(main())
