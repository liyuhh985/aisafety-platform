"""
批量识图测试——遍历 test_images/ 下所有图片，输出结构化分析结果。
"""
import json
import os
import sys

from mimo_client import client
from prompts import VISION_PROMPT

TEST_DIR = "test_images"


def main():
    if not os.path.isdir(TEST_DIR):
        print(f"[ERROR] 目录不存在: {TEST_DIR}")
        return 1

    files = sorted(
        [f for f in os.listdir(TEST_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    )
    if not files:
        print(f"[ERROR] {TEST_DIR}/ 下没有图片，先运行 download_images.py")
        return 1

    print(f"[INFO] 模型: {client.model}")
    print(f"[INFO] 共 {len(files)} 张测试图片\n")
    print("=" * 70)

    results = {}
    success = 0
    fail = 0

    for i, filename in enumerate(files, 1):
        path = os.path.join(TEST_DIR, filename)
        print(f"\n[{i}/{len(files)}] {filename}")
        print("-" * 50)

        result = client.analyze_json(path, VISION_PROMPT)
        if result is None:
            print("[FAIL] 识别失败")
            fail += 1
            results[filename] = {"error": "识别失败"}
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            success += 1
            results[filename] = result

    print("\n" + "=" * 70)
    print(f"[汇总] 成功: {success}, 失败: {fail}, 总计: {len(files)}")

    # 保存汇总 JSON
    summary_path = os.path.join(TEST_DIR, "batch_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 详细结果已保存: {summary_path}")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
