"""范围词表候选词的语料计数（只读，不改库）。

用途：为 core/scope_policy.py 的 DOMAIN_KEYWORDS 扩表提供实测依据。
计数口径（可复现）：
  - 每张表逐行拼接全部文本字段，按「行」计一次命中（同一词在同一行出现多次只算 1）
  - 大小写敏感（中文语料，大小写不影响结论）
  - 表：tb_hazard_case（案例库）/ tb_regulation（法规库）/ tb_hazard_knowledge（知识库）
  - 同时给出该词命中行所属的 category 分布，用来确认它是「本小类的用词」而不是别类的噪声

输出：stdout + 落盘 db/eval_scope_words.txt
"""
import io
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from tools.hybrid_search import _mysql_connection  # noqa: E402

TABLES = {
    "case": ("tb_hazard_case", ("category", "title", "description", "cause", "rectification", "verdict")),
    "reg": ("tb_regulation", ("category", "law_name", "article", "content", "keywords", "penalty")),
    "kb": ("tb_hazard_knowledge", ("category", "title", "content")),
}

# 候选词 = 三处待补小类的可能用词 + 有意排除项的对照
CANDIDATES = (
    "交通设施", "交通标志", "标志牌", "护栏", "信号灯", "交通标线", "指示牌",
    "外立面", "墙皮", "外墙", "脱落",
    "配电设施", "配电箱", "配电柜", "配电房", "电箱", "变压器", "电力设施",
)


def load_rows():
    conn, closer = _mysql_connection(20.0, None)
    data = {}
    try:
        cur = conn.cursor()
        for key, (table, fields) in TABLES.items():
            cur.execute("SELECT %s FROM %s" % (",".join(fields), table))
            data[key] = [tuple(row) for row in cur.fetchall()]
    finally:
        closer()
    return data


def main():
    data = load_rows()

    def rows_of(key):
        return data[key]

    def text_of(key, row):
        return " ".join(str(x or "") for x in row)

    lines = []
    lines.append("语料规模：")
    for key, rows in data.items():
        lines.append("  %-6s %d 行" % (key, len(rows)))
    lines.append("")
    header = "%-10s %6s %6s %6s   %s" % ("词", "case", "reg", "kb", "case 命中的 category 分布(top3)")
    lines.append(header)
    lines.append("-" * len(header))
    for word in CANDIDATES:
        counts = {}
        for key, rows in data.items():
            counts[key] = sum(1 for row in rows if word in text_of(key, row))
        dist = Counter(
            row[0] for row in rows_of("case")
            if str(row[0] or "") and word in text_of("case", row)
        )
        top = " / ".join("%s×%d" % (k, v) for k, v in dist.most_common(3)) or "-"
        lines.append("%-10s %6d %6d %6d   %s" % (word, counts["case"], counts["reg"], counts["kb"], top))

    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    with open("db/eval_scope_words.txt", "w", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
