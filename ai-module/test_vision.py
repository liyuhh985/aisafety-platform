"""
测试脚本: MiMo 识图 + 结构化 JSON 输出。
用法: python test_vision.py [图片路径]
"""
import json
import sys

from mimo_client import client
from prompts import HAZARD_ANALYSIS_PROMPT


def main():
    # 默认测试图片
    image_path = sys.argv[1] if len(sys.argv) > 1 else "../demo.png"
    print(f"[INFO] 测试图片: {image_path}")
    print(f"[INFO] 模型: {client.model}")
    print("=" * 60)

    print("\n>>> 发送识图请求...\n")
    result = client.analyze_json(image_path, HAZARD_ANALYSIS_PROMPT)

    if result is None:
        print("[FAIL] 识别失败")
        return 1

    print(">>> 结构化分析结果:\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n" + "=" * 60)

    # 校验关键字段
    missing = []
    required = ["has_hazard", "hazard_category", "severity", "description", "location_hint", "rectification"]
    for k in required:
        if k not in result:
            missing.append(k)
    if missing:
        print(f"[WARN] 缺少字段: {', '.join(missing)}")
    else:
        print("[OK] 所有字段齐全")

    return 0


if __name__ == "__main__":
    sys.exit(main())
