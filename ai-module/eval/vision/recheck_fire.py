# -*- coding: utf-8 -*-
"""
消防通道标注复核 v2（用模型判断，不用关键词）

v1 用关键词匹配，把"地面黄色网状禁停标线"（明显是消防网格）
误判成"无证据"，不可靠。

本版：直接让模型看每张图，只回答一个问题——
  "画面里有没有消防通道的可视标识？"

预算：70 张（仅 fire_lane_blocked 类），成本很低。
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = r'E:\java\newProject\ai-module\eval\vision'
_AI = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, _AI):
    if p not in sys.path:
        sys.path.insert(0, p)

POOL = os.path.join(HERE, 'pool')

PROMPT = """这是一个消防通道标注核查任务。请只看一件事：

**画面中是否存在"消防通道"的可视标识？**

算（存在）：
- 黄色网格线 / 黄色网状禁停标线
- 黄黑斜纹 / 红色消防标线
- 地面喷字「消防通道」「消防车道」「禁止占用」
- 立牌/铁牌「消防通道 禁止停车」
- 消防车道标识、消防登高面标线

不算（不存在）：
- 普通禁停标志（红圈蓝底或蓝底红叉，无"消防"字样）
- 普通道路标线（白实线、黄实线、双黄线）
- 仅仅是"通道被堵"（楼梯间、楼道、窄巷、小区门口、单元门前）
- 疏散指示牌、安全出口指示灯 —— 这是疏散通道，不是消防车道
- 消防栓、灭火器、消防柜 —— 这是设施，不是通道标识

只输出 JSON：
{"has_fire_lane_mark": true或false, "evidence": "若true，具体是什么标识；若false，画面主体是什么", "is_evacuation_route": true或false}
"""


def check(client, path):
    try:
        out = client.analyze_json(path, PROMPT)
        if isinstance(out, dict):
            return out
    except Exception:
        pass
    return None


def main():
    from mimo_client import MiMoVisionClient
    client = MiMoVisionClient()

    p = os.path.join(POOL, 'fire_lane_blocked', 'annotations.json')
    j = json.load(open(p, encoding='utf-8'))
    items = j.get('items', {})

    print(f'核查 {len(items)} 张，模型={client.model}\n')

    res = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(check, client,
                          os.path.join(POOL, 'fire_lane_blocked', 'review', f)): f
                for f in items}
        done = 0
        for fu in as_completed(futs):
            f = futs[fu]
            res[f] = fu.result()
            done += 1
            if done % 20 == 0:
                print(f'  进度 {done}/{len(items)}')

    has_mark, no_mark, failed = [], [], []
    for f, r in res.items():
        if not r:
            failed.append(f)
        elif r.get('has_fire_lane_mark'):
            has_mark.append((f, r.get('evidence', '')))
        else:
            no_mark.append((f, r.get('evidence', ''), r.get('is_evacuation_route')))

    print()
    print('=' * 88)
    print(f'有消防通道标识（保留 fire_lane_blocked）: {len(has_mark)} 张')
    print(f'无消防通道标识（应改判）              : {len(no_mark)} 张')
    print(f'失败                                : {len(failed)} 张')
    print('=' * 88)

    print('\n--- 应改判的 ---')
    for f, ev, evac in no_mark:
        tag = '疏散通道' if evac else ''
        print(f'  {f:<16} {ev[:52]} {tag}')

    out = {f: 'vehicle_occupancy' for f, ev, _ in no_mark}
    json.dump(out, open(os.path.join(POOL, 'fire_lane_blocked', 'reclass.json'), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(res, open(os.path.join(POOL, 'fire_lane_blocked', 'fire_mark_check.json'),
                        'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n改判 {len(out)} 张 → reclass.json')


if __name__ == '__main__':
    main()
