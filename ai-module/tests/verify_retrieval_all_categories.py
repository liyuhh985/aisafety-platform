"""
验证 8 大类 26 细分类全量案例与法规检索能力。
"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.hybrid_search import searcher
from core.case_relevance import filter_by_major
from core.hazard_taxonomy import HAZARD_TAXONOMY

TEST_QUERIES = [
    ("fire", "消防设施故障 消火栓无水 灭火器过期", "消防安全"),
    ("utility", "燃气泄漏 闻到煤气味 管道破裂", "电气与燃气"),
    ("building", "高空坠物 窗户滑落 瓷砖外立面脱落", "建筑安全"),
    ("elevator_special", "电梯困人 停运 剧烈异响 坠落", "电梯与特种设备"),
    ("municipal", "路面塌陷 井盖缺失 空洞 积水", "市政设施"),
    ("traffic", "盲道占用 共享单车 违停 占道经营", "交通与通行"),
    ("construction", "深基坑坍塌 脚手架防护缺失 未设置围挡", "施工安全"),
    ("environment_other", "垃圾大面积堆积 污水外溢 恶臭", "环境与其他"),
]

def main():
    print("=" * 60)
    print("开始对 8 大一级领域的端到端检索与类别过滤进行验证...")
    print("=" * 60)

    all_passed = True
    import time
    for major_code, query, major_name in TEST_QUERIES:
        print(f"\n[测试领域: {major_name} ({major_code})]")
        print(f"  查询词: {query}")

        # 1. 案例检索 (带网络偶发超时重试)
        case_res = ""
        for attempt in range(2):
            case_res = searcher.hybrid_search(query, table="tb_hazard_case", vector_k=3, keyword_k=2)
            if "retrieval timeout" not in case_res:
                break
            time.sleep(1)
        filtered_cases = filter_by_major(case_res, major_code)
        has_case_match = "库内暂未检索到" not in filtered_cases and "【结果" in filtered_cases

        time.sleep(1)

        # 2. 法规检索 (带网络偶发超时重试)
        reg_res = ""
        for attempt in range(2):
            reg_res = searcher.hybrid_search(query, table="tb_regulation", vector_k=3, keyword_k=2)
            if "retrieval timeout" not in reg_res:
                break
            time.sleep(2)
        filtered_regs = filter_by_major(reg_res, major_code)
        has_reg_match = "库内暂未检索到" not in filtered_regs and "【法规" in filtered_regs

        print(f"  案例召回校验: {'PASS (已精准匹配并保留)' if has_case_match else 'FAIL (未匹配或被过滤)'}")
        print(f"  法规召回校验: {'PASS (已精准匹配并保留)' if has_reg_match else 'FAIL (未匹配或被过滤)'}")

        if not has_case_match or not has_reg_match:
            all_passed = False
            if not has_case_match:
                print(f"    [案例原始结果片段]: {case_res[:150]}...")
            if not has_reg_match:
                print(f"    [法规原始结果片段]: {reg_res[:150]}...")

        time.sleep(1)

    print("\n" + "=" * 60)
    if all_passed:
        print("恭喜！8 大一级领域全部通过端到端案例与法规召回与分类过滤校验！")
    else:
        print("警告：部分领域未能通过过滤校验，请检查。")
    print("=" * 60)

if __name__ == "__main__":
    main()
