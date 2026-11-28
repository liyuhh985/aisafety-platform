# -*- coding: utf-8 -*-
"""
最终评测：在 test 集上跑一次（不受调参污染）

输出：
  · 严格准确率 / 大类准确率
  · 漏报率 / 误报率
  · Wilson 置信区间
  · 分层统计（按难度、按标注来源、按是否含文字）
  · 分场景 P/R/F1
  · 混淆矩阵

用法：
    python final_eval.py
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = r'E:\java\newProject\ai-module\eval\vision'
_AI = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, _AI):
    if p not in sys.path:
        sys.path.insert(0, p)

TEST = os.path.join(HERE, 'test_set')
ANN = os.path.join(HERE, 'test_set_annotations.json')
OUT = os.path.join(HERE, 'FINAL_EVAL.txt')
CACHE = os.path.join(HERE, 'test_set', 'pred')

TAX = json.load(open(os.path.join(HERE, '_taxonomy_final.json'), encoding='utf-8'))
CODE2 = {}
NAME = {}
for m in TAX:
    for s in m['subcategories']:
        CODE2[s['code']] = m['code']
        NAME[s['code']] = (m['label'], s['label'])


def wilson(k, n, z=1.96):
    """Wilson 置信区间"""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0, centre - half), min(1, centre + half)


def pred_path(cat, f):
    d = os.path.join(CACHE, cat)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f + '.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--rerun', action='store_true')
    args = ap.parse_args()

    from mimo_client import VisionClient
    from prompts import VISION_PROMPT
    cl = VisionClient('opendesign')
    print(f'被评测模型: {cl.model}\n')

    ann = json.load(open(ANN, encoding='utf-8'))
    print(f'标注 {len(ann)} 条')

    # 推理（带缓存，可重跑）
    tasks = []
    for key in ann:
        cat, f = key.split('/', 1)
        p = os.path.join(TEST, cat, f)
        if os.path.isfile(p):
            tasks.append((cat, f, p))
    print(f'可评测 {len(tasks)} 张\n')

    results = {}
    todo = []
    for cat, f, p in tasks:
        pp = pred_path(cat, f)
        if not args.rerun and os.path.isfile(pp):
            try:
                results[(cat, f)] = json.load(open(pp, encoding='utf-8'))
                continue
            except Exception:
                pass
        todo.append((cat, f, p))

    if todo:
        print(f'需推理 {len(todo)} 张')
        def run(p):
            for att in range(5):
                try:
                    out = cl.analyze_json(p, VISION_PROMPT)
                    if isinstance(out, dict):
                        return out
                except Exception as e:
                    if any(k in str(e) for k in ('402', '401', '403')):
                        raise
                    time.sleep(min(2 ** att, 8))
            return None

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run, p): (c, f) for c, f, p in todo}
            done = 0
            for fu in as_completed(futs):
                c, f = futs[fu]
                try:
                    r = fu.result()
                except Exception:
                    r = None
                results[(c, f)] = r
                if r:
                    try:
                        json.dump(r, open(pred_path(c, f), 'w', encoding='utf-8'),
                                  ensure_ascii=False)
                    except Exception:
                        pass
                done += 1
                if done % 40 == 0:
                    print(f'  进度 {done}/{len(todo)}', flush=True)
        print()

    # 评分
    rows = []
    for key, gold in ann.items():
        cat, f = key.split('/', 1)
        pred = results.get((cat, f))
        g_hz = gold.get('has_hazard', True)
        g_sub = gold.get('subcategory', '')

        if not isinstance(pred, dict):
            rows.append({'cat': cat, 'file': f, 'verdict': 'failed',
                         'g': g_sub if g_hz else '(负)', 'p': '(失败)',
                         'src': gold.get('label_source', ''),
                         'dif': gold.get('difficulty', ''),
                         'txt': gold.get('text_in_image', False)})
            continue

        p_hz = pred.get('has_hazard')
        p_sub = str(pred.get('subcategory') or '').strip().lower()

        if g_hz is False and p_hz is False:
            v = 'OK'
        elif g_hz is False and p_hz is True:
            v = 'FP'
        elif g_hz is True and p_hz is False:
            v = 'FN'
        elif p_sub == g_sub:
            v = 'OK'
        elif CODE2.get(p_sub) and CODE2.get(p_sub) == CODE2.get(g_sub):
            v = 'MAJOR'
        else:
            v = 'WRONG'

        rows.append({'cat': cat, 'file': f, 'verdict': v,
                     'g': g_sub if g_hz else '(负样本)',
                     'p': p_sub if p_hz else '(判无隐患)',
                     'src': gold.get('label_source', ''),
                     'dif': gold.get('difficulty', ''),
                     'txt': gold.get('text_in_image', False)})

    T = Counter()
    for r in rows:
        T['n'] += 1
        if r['verdict'] == 'OK':
            T['ok'] += 1
        elif r['verdict'] == 'MAJOR':
            T['major'] += 1
        elif r['verdict'] == 'FN':
            T['fn'] += 1
        elif r['verdict'] == 'FP':
            T['fp'] += 1
        elif r['verdict'] == 'failed':
            T['fail'] += 1
        else:
            T['wrong'] += 1

    n = T['n']
    buf = []

    def W(s=''):
        buf.append(s)
        print(s)

    W('=' * 78)
    W('最终评测（独立 test 集，只跑一次，未参与任何调参）')
    W('=' * 78)
    W(f'生成时间   {time.strftime("%Y-%m-%d %H:%M")}')
    W(f'被评测模型 {cl.model}')
    W(f'样本       {n} 张')
    W()

    p, lo, hi = wilson(T['ok'], n)
    W('一、总体指标')
    W('-' * 78)
    W(f'  严格准确率   {T["ok"]}/{n} = {p*100:.1f}%   95%CI [{lo*100:.1f}%, {hi*100:.1f}%]')
    pm, lom, him = wilson(T['ok'] + T['major'], n)
    W(f'  大类准确率   {T["ok"]+T["major"]}/{n} = {pm*100:.1f}%   '
      f'95%CI [{lom*100:.1f}%, {him*100:.1f}%]')
    W(f'  漏报率       {T["fn"]}/{n} = {T["fn"]/n*100:.1f}%')
    W(f'  误报率       {T["fp"]}/{n} = {T["fp"]/n*100:.1f}%')
    W(f'  推理失败     {T["fail"]} 张')
    W()

    # 分层：标注来源
    W('二、按标注可信度分层')
    W('-' * 78)
    by_src = defaultdict(Counter)
    for r in rows:
        by_src[r['src']]['n'] += 1
        if r['verdict'] == 'OK':
            by_src[r['src']]['ok'] += 1
    W(f'{"标注来源":<16}{"样本":>6}{"严格正确":>8}{"准确率":>8}')
    for s, c in sorted(by_src.items(), key=lambda x: -x[1]['n']):
        acc = c['ok'] / c['n'] * 100 if c['n'] else 0
        W(f'{s:<16}{c["n"]:>6}{c["ok"]:>8}{acc:>7.0f}%')
    W()

    # 分层：难度
    W('三、按难度分层')
    W('-' * 78)
    by_dif = defaultdict(Counter)
    for r in rows:
        d = r['dif'] or 'unknown'
        by_dif[d]['n'] += 1
        if r['verdict'] == 'OK':
            by_dif[d]['ok'] += 1
    W(f'{"难度":<12}{"样本":>6}{"严格正确":>8}{"准确率":>8}')
    for d in ('easy', 'medium', 'hard', 'unknown'):
        if d not in by_dif:
            continue
        c = by_dif[d]
        acc = c['ok'] / c['n'] * 100 if c['n'] else 0
        W(f'{d:<12}{c["n"]:>6}{c["ok"]:>8}{acc:>7.0f}%')
    W()

    # 分层：含文字
    W('四、按是否含文字分层')
    W('-' * 78)
    by_txt = defaultdict(Counter)
    for r in rows:
        k = '含文字' if r['txt'] else '无文字'
        by_txt[k]['n'] += 1
        if r['verdict'] == 'OK':
            by_txt[k]['ok'] += 1
    W(f'{"分组":<12}{"样本":>6}{"严格正确":>8}{"准确率":>8}')
    for k, c in by_txt.items():
        acc = c['ok'] / c['n'] * 100 if c['n'] else 0
        W(f'{k:<12}{c["n"]:>6}{c["ok"]:>8}{acc:>7.0f}%')
    W()

    # 分类别
    W('五、分类别准确率')
    W('-' * 78)
    by_cat = defaultdict(Counter)
    for r in rows:
        by_cat[r['g']]['n'] += 1
        if r['verdict'] == 'OK':
            by_cat[r['g']]['ok'] += 1
    W(f'{"类别":<32}{"样本":>5}{"正确":>5}{"准确率":>7}')
    for c, s in sorted(by_cat.items(), key=lambda x: -(x[1]['ok'] / max(x[1]['n'], 1))):
        nm = NAME.get(c, ('', c))[1] if c != '(负样本)' else '(负样本)'
        acc = s['ok'] / s['n'] * 100 if s['n'] else 0
        W(f'{nm:<32}{s["n"]:>5}{s["ok"]:>5}{acc:>6.0f}%')
    W()

    # 错误
    W('六、主要错误类型')
    W('-' * 78)
    conf = Counter((r['g'], r['p'], r['verdict'])
                   for r in rows if r['verdict'] in ('WRONG', 'MAJOR', 'FN', 'FP'))
    if conf:
        W(f'{"期望":<28}{"实际":<28}{"类型":>8}{"次数":>5}')
        for (g, p2, v), c in conf.most_common(15):
            gn = NAME.get(g, ('', g))[1] if g != '(负样本)' else '(负样本)'
            pn = NAME.get(p2, ('', p2))[1] if not p2.startswith('(') else p2
            W(f'{gn:<28}{pn:<28}{v:>8}{c:>5}')
    else:
        W('  无错误')
    W()

    text = '\n'.join(buf)
    open(OUT, 'w', encoding='utf-8').write(text)
    print(f'→ {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
