"""
全量构建与更新本地案例库向量缓存 (case_embeddings.json)。
用于 MySQL 降级模式下的高性能向量检索。
"""
import os
import sys
import json
import pymysql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import DB_CONFIG
from tools.knowledge_sync import SiliconFlowEmbeddingClient

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "case_embeddings.json")


def main():
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[缓存] 读取现有缓存 {len(cache)} 条")
        except Exception:
            cache = {}

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, description, cause, rectification FROM tb_hazard_case")
            cases = cur.fetchall()
    finally:
        conn.close()

    print(f"[数据库] 共读取到 {len(cases)} 条案例")
    client = SiliconFlowEmbeddingClient()

    needed = []
    needed_ids = []
    for row in cases:
        cid = str(row[0])
        if cid not in cache:
            text = f"{row[1]} {row[2]} {row[3] or ''} {row[4] or ''}"[:1500]
            needed.append(text)
            needed_ids.append(cid)

    if not needed:
        print("[完成] 所有案例均已存在于本地向量缓存中，无需重复生成。")
        return

    print(f"[生成] 开始为缺失的 {len(needed)} 条案例批量生成 BAAI/bge-m3 语义向量...")
    import time
    batch_size = 4
    for i in range(0, len(needed), batch_size):
        sub_texts = needed[i:i + batch_size]
        sub_ids = needed_ids[i:i + batch_size]
        success = False
        for attempt in range(3):
            try:
                vectors = client.embed(sub_texts)
                for cid, vec in zip(sub_ids, vectors):
                    cache[cid] = vec
                success = True
                break
            except Exception as e:
                print(f"  [重试] 批次 {i} 失败，第 {attempt+1} 次重试...")
                time.sleep(1)
        if not success:
            print(f"  [警告] 批次 {i} 最终失败，跳过该批次")
        print(f"  - 已完成 {min(i + batch_size, len(needed))}/{len(needed)} 条...")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)

    print(f"[成功] 缓存文件更新完成，当前本地向量库共计 {len(cache)} 条。")


if __name__ == "__main__":
    main()
