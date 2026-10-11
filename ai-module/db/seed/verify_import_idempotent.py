# -*- coding: utf-8 -*-
"""import_all_new_data 的法规导入幂等性验证（2026-09-29 并入 batch2026 时新增）。

为什么需要它：把 batch2026 并进导入清单之后，"重建库会不会重复写入"只能靠幂等性证明。
main() 不能直接拿来验（它还会写备份文件并 commit），所以这里只做两件事：

  1) 只读预检：**独立于被测函数**，按去重键 (law_name, article, category) 逐条查库，
     得到"预计会被跳过几条"；
  2) 真跑代码路径：调用 import_all_new_data.import_regulations(cur)，拿它返回的 inserted，
     然后在**同一事务里 rollback** —— 即使去重键失效、真的执行了 INSERT，也不会留在库里。

判定：预期与实际都必须 0 inserted、全部 skipped，否则退出码 1。
口径：连 db_config.DB_CONFIG 指向的库；只读 + rollback，不留副作用。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pymysql

from db_config import DB_CONFIG
# 注意：import_all_new_data 在 import 时就把 sys.stdout 换成了 UTF-8 包装器，
# 所以这里**不要**再包一层 —— 二次包装会让前一个包装器被回收、连带关掉底层 buffer
# （症状：ValueError: I/O operation on closed file）。
from db.seed.import_all_new_data import (ALL_NEW_REGULATIONS, NEW_REGULATIONS_2026,
                                    import_regulations)

DEDUP_SQL = ("SELECT id FROM tb_regulation "
             "WHERE law_name = %s AND article = %s AND category = %s")


def precheck(cur, regs):
    """只读预检：复刻被测函数的去重 SQL，但一条都不写。"""
    skipped, would_insert = 0, []
    for reg in regs:
        key = (reg["law_name"].strip(), reg["article"].strip(), reg["category"].strip())
        cur.execute(DEDUP_SQL, key)
        if cur.fetchone():
            skipped += 1
        else:
            would_insert.append(key)
    return skipped, would_insert


def main():
    total = len(ALL_NEW_REGULATIONS)
    print("法规导入清单规模（batch2 + batch2026）: %d 条" % total)
    conn = pymysql.connect(**DB_CONFIG)
    ok = True
    try:
        cur = conn.cursor()
        skipped, would_insert = precheck(cur, ALL_NEW_REGULATIONS)
        print("[1] 只读预检：预计 skipped=%d，预计 inserted=%d" % (skipped, len(would_insert)))
        for key in would_insert:
            print("    预计会插入（三元组未命中）: %s | %s | %s" % key)
        if would_insert:
            ok = False

        # 本次并入的批次单列一次：验收要求是"batch2026 这 10 条必须 0 inserted / 10 skipped"。
        sub_skipped, sub_insert = precheck(cur, NEW_REGULATIONS_2026)
        print("[1b] 其中 batch2026 子集：skipped=%d / inserted=%d（共 %d 条）"
              % (sub_skipped, len(sub_insert), len(NEW_REGULATIONS_2026)))
        for key in sub_insert:
            print("    batch2026 三元组未命中: %s | %s | %s" % key)
        if sub_insert:
            ok = False

        print("[2] 真跑 import_regulations（事务内，跑完 rollback）...")
        inserted = import_regulations(cur)
        derived_skipped = total - inserted
        print("    实际：inserted=%d，skipped=%d（skipped 由 总数 - inserted 得出）"
              % (inserted, derived_skipped))
        conn.rollback()
        print("    已 rollback：本次未对库产生任何写入")

        if inserted != 0 or derived_skipped != total:
            ok = False
        print("\n判定：%s（幂等要求 inserted=0 / skipped=%d）"
              % ("PASS" if ok else "FAIL", total))
    finally:
        conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
