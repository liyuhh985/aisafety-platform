# -*- coding: utf-8 -*-
"""
最终评测 v2（修正版）

修复 final_eval.py 的三个错误：
  1. 模型输出是旧 32 类名，需映射到新 25 类名再比对（严重错误）
  2. 误报率分母应为负样本数，不是总样本数
  3. 负样本占比需要明确说明

预测结果复用 test_set/pred/ 缓存，不重新调 API。
"""
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

HERE = r'E:\java\newProject\ai-module\eval\vision'
TEST = os.path.join(HERE, 'test_set')
ANN = os.path.join(HERE, 'test_set_annotations.json')
CACHE = os.path.join(HERE, 'test_set', 'pred')
OUT = os.path.join(HERE, 'FINAL_EVAL_v2.txt')

TAX = json.load(open(os.path.join(HERE, '_taxonomy_final.json'), encoding='utf-8'))
CODE2, NAME = {}, {}
for m in TAX:
    for s in m['subcategories']:
        CODE2[s['code']] = m['code']
        NAME[s['code']] = (m['label'], s['label'])

# ★ 关键修复：旧类名 → 新类名
MERGE = {
    'falling_object': 'facade_risk',
    'facade_fall': 'facade_risk',
    'dangerous_building': 'structural_damage',
    'wall_crack_lean': 'structural_damage',
    'exposed_wire': 'wire_fault',
    'illegal_wiring': 'wire_fault',
    'temporary_power': 'wire_fault',
    'fire_equipment_fault': 'fire_facility',
    'fire_water_abnormal': 'fire_facility',
    'no_warning': 'construction_prot',
    'no_barrier': 'construction_prot',
    'sewage_odor': 'sewage_overflow',
}

# 旧体系里的兜底类，映射后视为无效预测
DROP = {'other'}


def norm_pred(sub):
    """把模型输出映射到新体系；返回 (类别码, 是否有效)"""
    s = (sub or '').strip().lower()
    if not s:
        return '', False
    if s in DROP:
        return '', False
    s = MERGE.get(s, s)
    if s not in CODE2:
        return '', False
    return s, True


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def main():
    ann = json.load(open(ANN, encoding='utf-8'))
    rows = []
    missing = 0

    for key, gold in ann.items():
        cat, f = key.split('/', 1)
        pp = os.path.join(CACHE, cat, f + '.json')
        pred = None
        if os.path.isfile(pp):
            try:
                pred = json.load(open(pp, encoding='utf-8'))
            except Exception:
                pred = None
        if not isinstance(pred, dict):
            missing += 1
            continue

        g_hz = bool(gold.get('has_hazard', True))
        g_sub = gold.get('subcategory', '') or ''

        p_hz = pred.get('has_hazard')
        p_raw = str(pred.get('subcategory') or '').strip().lower()
        p_sub, p_valid = norm_pred(p_raw)

        if not g_hz and not p_hz:
            v = 'OK'
        elif not g_hz and p_hz:
            v = 'FP'
        elif g_hz and not p_hz:
            v = 'FN'
        elif g_hz and p_hz:
            if not p_valid:
                v = 'WRONG'          # 输出无效类别（如 other）
            elif p_sub == g_sub:
                v = 'OK'
            elif CODE2.get(p_sub) == CODE2.get(g_sub):
                v = 'MAJOR'
            else:
                v = 'WRONG'
        else:
            v = 'WRONG'

        rows.append({
            'cat': cat, 'file': f, 'v': v,
            'g': g_sub if g_hz else '(负样本)',
            'p': (p_sub or p_raw or '?') if p_hz else '(判无隐患)',
            'src': gold.get('label_source', ''),
            'dif': gold.get('difficulty', ''),
            'txt': bool(gold.get('text_in_image')),
            'ghz': g_hz,
        })

    n = len(rows)
    pos = [r for r in rows if r['ghz']]
    neg = [r for r in rows if not r['ghz']]
    np_, nn = len(pos), len(neg)

    T = Counter(r['v'] for r in rows)
    Tp = Counter(r['v'] for r in pos)
    Tn = Counter(r['v'] for r in neg)

    buf = []

    def W(s=''):
        buf.append(s)
        print(s)

    W('=' * 80)
    W('最终评测 v2（独立 test 集 · 修正类别映射后）')
    W('=' * 80)
    W(f'生成时间  {time.strftime("%Y-%m-%d %H:%M")}')
    W(f'被评测     deepseek-v4.1-flash')
    W(f'样本      {n} 张（正样本 {np_}，负样本 {nn}）')
    if missing:
        W(f'缺失预测  {missing} 张')
    W()

    W('一、总体指标')
    W('-' * 80)
    p, lo, hi = wilson(T['OK'], n)
    W(f'  严格准确率（全部样本）  {T["OK"]}/{n} = {p*100:.1f}%   '
      f'95%CI [{lo*100:.1f}%, {hi*100:.1f}%]')
    pm, lom, him = wilson(T['OK'] + T['MAJOR'], n)
    W(f'  大类准确率（全部样本）  {T["OK"]+T["MAJOR"]}/{n} = {pm*100:.1f}%   '
      f'95%CI [{lom*100:.1f}%, {him*100:.1f}%]')
    W()
    W('  【正样本】有隐患的图')
    pp, plo, phi = wilson(Tp['OK'], np_)
    W(f'    严格准确率            {Tp["OK"]}/{np_} = {pp*100:.1f}%   '
      f'95%CI [{plo*100:.1f}%, {phi*100:.1f}%]')
    W(f'    大类准确率            {Tp["OK"]+Tp["MAJOR"]}/{np_} = '
      f'{(Tp["OK"]+Tp["MAJOR"])/np_*100:.1f}%')
    W(f'    漏报率                {Tp["FN"]}/{np_} = {Tp["FN"]/np_*100:.1f}%')
    W()
    W('  【负样本】正常场景的图')
    W(f'    正确判为无隐患         {Tn["OK"]}/{nn} = {Tn["OK"]/nn*100:.1f}%')
    W(f'    误报率                {Tn["FP"]}/{nn} = {Tn["FP"]/nn*100:.1f}%   '
      f'← 分母是负样本数')
    W()

    # 分层
    def group(rows_, keyfn, title, order=None):
        W(title)
        W('-' * 80)
        g = defaultdict(Counter)
        for r in rows_:
            k = keyfn(r)
            g[k]['n'] += 1
            if r['v'] == 'OK':
                g[k]['ok'] += 1
        W(f'{"分组":<18}{"样本":>6}{"正确":>6}{"准确率":>8}')
        keys = order or sorted(g, key=lambda x: -g[x]['n'])
        for k in keys:
            if k not in g:
                continue
            c = g[k]
            W(f'{str(k):<18}{c["n"]:>6}{c["ok"]:>6}{c["ok"]/c["n"]*100:>7.0f}%')
        W()

    group(pos, lambda r: r['src'], '二、正样本 · 按标注可信度分层')
    group(pos, lambda r: r['dif'] or 'unknown',
          '三、正样本 · 按难度分层', ['easy', 'medium', 'hard', 'unknown'])
    group(pos, lambda r: '含文字' if r['txt'] else '无文字',
          '四、正样本 · 按是否含文字分层', ['无文字', '含文字'])

    # 分类别（仅正样本）
    W('五、分类别准确率（正样本）')
    W('-' * 80)
    bc = defaultdict(Counter)
    for r in pos:
        bc[r['g']]['n'] += 1
        if r['v'] == 'OK':
            bc[r['g']]['ok'] += 1
    W(f'{"类别":<30}{"样本":>5}{"正确":>5}{"准确率":>7}   备注')
    for c, s in sorted(bc.items(), key=lambda x: -(x[1]['ok'] / max(x[1]['n'], 1))):
        nm = NAME.get(c, ('', c))[1]
        acc = s['ok'] / s['n'] * 100
        note = '⚠️ 样本<10' if s['n'] < 10 else ''
        W(f'{nm:<30}{s["n"]:>5}{s["ok"]:>5}{acc:>6.0f}%   {note}')
    W()

    # 负样本被误判成什么
    W('六、负样本误判去向（模型把正常图判成了什么）')
    W('-' * 80)
    fpc = Counter(r['p'] for r in neg if r['v'] == 'FP')
    for k, v in fpc.most_common(15):
        nm = NAME.get(k, ('', k))[1] if k in NAME else k
        W(f'  {nm:<30} {v:>3} 次')
    W()

    # 正样本错误
    W('七、正样本主要错误')
    W('-' * 80)
    conf = Counter((r['g'], r['p'], r['v']) for r in pos
                   if r['v'] in ('WRONG', 'MAJOR', 'FN'))
    if conf:
        W(f'{"期望":<26}{"实际":<26}{"类型":>7}{"次数":>5}')
        for (g, p2, v), c in conf.most_common(15):
            gn = NAME.get(g, ('', g))[1]
            pn = NAME.get(p2, ('', p2))[1] if p2 in NAME else p2
            W(f'{gn:<26}{pn:<26}{v:>7}{c:>5}')
    else:
        W('  无错误')
    W()

    text = '\n'.join(buf)
    open(OUT, 'w', encoding='utf-8').write(text)
    json.dump({'n': n, 'pos': np_, 'neg': nn,
               'strict_all': T['OK'] / n,
               'major_all': (T['OK'] + T['MAJOR']) / n,
               'strict_pos': Tp['OK'] / np_ if np_ else 0,
               'major_pos': (Tp['OK'] + Tp['MAJOR']) / np_ if np_ else 0,
               'fn_rate': Tp['FN'] / np_ if np_ else 0,
               'fp_rate': Tn['FP'] / nn if nn else 0},
              open(os.path.join(HERE, '_final_eval_v2.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'→ {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
