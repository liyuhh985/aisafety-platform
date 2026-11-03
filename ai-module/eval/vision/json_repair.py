# -*- coding: utf-8 -*-
"""
修复模型输出的非法 JSON（字符串值内含未转义双引号）

策略：逐字符扫描，跟踪是否在字符串内，遇到字符串值内部的双引号时判断
      "它是分隔符还是内容"——看它后面紧跟的是否是 , } ] : 等结构字符。
"""
import json
import re

STRUCT_AFTER = re.compile(r'\s*[,}\]:]')


def repair_json(text: str):
    if not text:
        return None

    # 0. 去 markdown 包裹
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:]) if len(lines) > 1 else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    s = s.strip()

    # 1. 先试原样
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 2. 提取最外层 { }
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end <= start:
        return None
    s = s[start:end + 1]

    # 3. 逐字符扫描修复
    out = []
    i = 0
    n = len(s)
    in_str = False
    while i < n:
        ch = s[i]

        if ch == '\\' and in_str:
            # 转义序列原样保留
            out.append(ch)
            if i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            i += 1
            continue

        if ch == '"':
            if not in_str:
                in_str = True
                out.append(ch)
                i += 1
                continue
            else:
                # 在字符串内遇到双引号：判断是否为结构分隔
                rest = s[i + 1:]
                if STRUCT_AFTER.match(rest):
                    # 是真正的字符串结束
                    in_str = False
                    out.append(ch)
                    i += 1
                    continue
                else:
                    # 是内容里的引号 → 转义
                    out.append('\\"')
                    i += 1
                    continue
        else:
            out.append(ch)
            i += 1

    fixed = "".join(out)

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 4. 最后兜底：把中文引号统一成单引号
    alt = fixed.replace('\u201c', "'").replace('\u201d', "'")
    alt = alt.replace('\u2018', "'").replace('\u2019', "'")
    try:
        return json.loads(alt)
    except json.JSONDecodeError:
        return None
