"""检索评测指标：纯函数，不触网、不读库。

新口径与旧 `eval_rag.py` 的区别：
- 金标准是**库内真实 case id 集合**（按 category 查出），不是模糊的"同类别即相关"
- 新增 `precision_at_k`：直接暴露"返回一堆无关条目"的噪声
- `recall_at_k` 同时返回**上限**，避免把 `3/15=0.20` 这种数学上限误读成低分
"""


def hit_at_k(ranked_ids, gold_ids, k: int = 5) -> bool:
    """top-k 里是否至少命中一条金标准。"""
    if k <= 0:
        return False
    gold = set(gold_ids)
    if not gold:
        return False
    return bool(set(ranked_ids[:k]) & gold)


def first_relevant_rank(ranked_ids, gold_ids):
    """第一条金标准的排名（从 1 开始）；没有命中返回 None。"""
    gold = set(gold_ids)
    if not gold:
        return None
    for rank, item_id in enumerate(ranked_ids, 1):
        if item_id in gold:
            return rank
    return None


def mrr(ranked_ids, gold_ids) -> float:
    """单条查询的 reciprocal rank（1/排名）；无命中为 0.0。"""
    rank = first_relevant_rank(ranked_ids, gold_ids)
    return 1.0 / rank if rank else 0.0


def precision_at_k(ranked_ids, gold_ids, k: int = 5) -> float:
    """top-k 里属于金标准的条数 ÷ k（分母固定为 k）。"""
    if k <= 0:
        return 0.0
    gold = set(gold_ids)
    hits = sum(1 for item_id in ranked_ids[:k] if item_id in gold)
    return hits / k


def recall_at_k(ranked_ids, gold_ids, k: int = 5):
    """返回 (recall, ceiling)。

    ceiling 是这条查询在当前 k 下的数学上限：min(k, 金标准条数) / 金标准条数。
    报告里必须一起打印，否则读者会把上限当成绩。
    """
    gold = set(gold_ids)
    if not gold:
        return 0.0, 0.0
    hits = sum(1 for item_id in ranked_ids[:k] if item_id in gold)
    return hits / len(gold), min(k, len(gold)) / len(gold)


def major_hit_at_k(ranked_majors, gold_major: str, k: int = 5) -> bool:
    """宽松口径：top-k 里是否有**同大类**的结果（不要求同小类）。"""
    if k <= 0:
        return False
    return gold_major in list(ranked_majors[:k])


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def spread(values) -> float:
    """极差（max-min），用于多次采样的离散度。"""
    values = list(values)
    return (max(values) - min(values)) if values else 0.0
