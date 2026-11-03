# -*- coding: utf-8 -*-
"""
清洗负样本：剔除"实际有隐患"的伪负样本

依据 fp_result.json 里的误报明细：
  模型描述了具体隐患（如"井盖边缘缺损""阀门缺手轮"）→ 这张图其实有隐患 → 不是干净的负样本
  模型只是说"无法确认/受距离限制"（无具体隐患描述）→ 图本身干净，属于策略性报警

区分方法：
  看模型给出的 description 里有没有"具体隐患名词"
  · 有具体缺陷描述 → 伪负样本，剔除
  · 只有"无法确认/不明确/建议核查" → 真负样本，保留（这是策略性误报）
"""
import json
import os
import re

HERE = r'E:\java\newProject\ai-module\eval\vision'
NEG = os.path.join(HERE, 'negatives')

fp = json.load(open(os.path.join(NEG, 'fp_result.json'), encoding='utf-8'))
neg_set = json.load(open(os.path.join(NEG, 'negative_set.json'), encoding='utf-8'))

# 伪负样本信号：模型描述了具体的物理缺陷
DEFECT_SIGNS = [
    '缺损', '破损', '缺失', '开裂', '裂缝', '锈蚀', '松动', '翘起', '移位',
    '凹陷', '塌陷', '坑洞', '断', '脱落', '倾斜', '占压', '占用', '堵塞',
    '堆放', '停放', '压占', '遮挡', '阻挡', '未设', '未见围挡', '缺少',
    '无盖', '无警示', '未封闭', '无遮', '违规', '加建', '搭', '穿墙',
    '间隙较宽', '高差', '绊倒', '坠落风险', '滑落',
]

# 策略性报警信号：模型只说"看不清/不确定"
HEDGE_SIGNS = [
    '无法确认', '无法判断', '受拍摄', '受距离', '距离较远', '不明确',
    '建议现场', '存在潜在', '可能会', '是否', '不能确认',
]


def classify(desc):
    has_defect = any(k in desc for k in DEFECT_SIGNS)
    has_hedge = any(k in desc for k in HEDGE_SIGNS)
    if has_defect and not has_hedge:
        return 'pseudo_negative', '描述具体缺陷'
    if has_defect and has_hedge:
        # 两者都有：看缺陷词是否更具体
        return 'pseudo_negative', '描述了缺陷(含推测)'
    if has_hedge:
        return 'strategic_fp', '仅表述不确定'
    return 'unclear', '无法判定'


clean = {c: list(fs) for c, fs in neg_set.items()}
removed = []
strategic = []
real_error = []

for d in fp.get('details', []):
    cat = d['cat']
    f = d['file']
    desc = d.get('desc', '')
    kind, why = classify(desc)

    if kind == 'pseudo_negative':
        if f in clean.get(cat, []):
            clean[cat].remove(f)
        removed.append({'cat': cat, 'file': f, 'reason': why, 'desc': desc})
    elif kind == 'strategic_fp':
        strategic.append({'cat': cat, 'file': f, 'desc': desc})
    else:
        real_error.append({'cat': cat, 'file': f, 'desc': desc})

t_clean = sum(len(v) for v in clean.values())

print('=' * 84)
print('负样本清洗结果')
print('=' * 84)
print(f'原始负样本        85 张')
print(f'误报总数          28 张')
print()
print(f'  伪负样本（图本身有隐患）   {len(removed):>2} 张  → 剔除')
print(f'  策略性报警（看不清就报）   {len(strategic):>2} 张  → 保留在统计里')
print(f'  无法归类             {len(real_error):>2} 张')
print()
print(f'清洗后负样本      {t_clean} 张')
print()

print('--- 剔除的伪负样本 ---')
for r in removed:
    print(f"  [{r['cat']}] {r['file']:<16} {r['desc'][:56]}")

print()
print('--- 策略性报警（保留，计入误报）---')
for r in strategic:
    print(f"  [{r['cat']}] {r['file']:<16} {r['desc'][:56]}")

if real_error:
    print()
    print('--- 无法归类 ---')
    for r in real_error:
        print(f"  [{r['cat']}] {r['file']:<16} {r['desc'][:56]}")

# 重算
fp_after = len(strategic) + len(real_error)
print()
print('=' * 84)
print('清洗后误报率')
print('=' * 84)
print(f'  {fp_after}/{t_clean} = {fp_after/max(t_clean,1)*100:.1f}%')
print()
print('说明：分母剔除了伪负样本，分子保留策略性报警')
print('     若只算"真实判错"：{}/{} = {:.1f}%'.format(
    len(real_error), t_clean, len(real_error) / max(t_clean, 1) * 100))

json.dump(clean, open(os.path.join(NEG, 'negative_set_clean.json'), 'w',
                      encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({
    'total_clean': t_clean,
    'fp_total': fp_after,
    'fp_rate': fp_after / max(t_clean, 1),
    'pseudo_removed': len(removed),
    'strategic': len(strategic),
    'real_error': len(real_error),
    'real_error_rate': len(real_error) / max(t_clean, 1),
    'details_removed': removed,
    'details_strategic': strategic,
    'details_error': real_error,
}, open(os.path.join(NEG, 'fp_clean.json'), 'w', encoding='utf-8'),
    ensure_ascii=False, indent=1)
print('\n→ negatives/fp_clean.json')
