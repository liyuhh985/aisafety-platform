# -*- coding: utf-8 -*-
"""
最终定稿：5 组合并 → 24 类

执行内容：
  1. 写入最终分类体系 _taxonomy_final.json（24 小类）
  2. 把 images_real/*/ground_truth.json 的类别码按映射改写
  3. 输出最终指标

保留的 5 组：
  组1  高空坠物 + 外立面脱落      → 外立面破损/坠落风险
  组2  危房 + 墙体开裂/倾斜       → 建筑结构损伤
  组3  裸露电线 + 私拉乱接 + 施工临时用电 → 电线裸露/私拉乱接
  组4  消防水源异常 + 消防设施故障 → 消防设施/水源异常
  组5  无安全警示 + 未设置围挡    → 施工防护缺失

撤回：
  组7（基坑）—— 收益仅 0.1 分，且让类别定义变模糊

另外采纳（数据修正，非类别改动）：
  污水/异味 类 8 张误标 → 3 张归垃圾堆积、5 张归排水积水
"""
import json
import os
import re
import shutil
from collections import Counter, defaultdict

HERE = r'E:\java\newProject\ai-module\eval\vision'
POOL = os.path.join(HERE, 'pool')
REAL = os.path.join(HERE, 'images_real')
EVAL_OUT = r'E:\java\newProject\ai-module\db\eval_real_output.txt'

# ---------- 最终映射（5 组）----------
MERGE = {
    "falling_object": "facade_risk",
    "facade_fall": "facade_risk",

    "dangerous_building": "structural_damage",
    "wall_crack_lean": "structural_damage",

    "exposed_wire": "wire_fault",
    "illegal_wiring": "wire_fault",
    "temporary_power": "wire_fault",

    "fire_equipment_fault": "fire_facility",
    "fire_water_abnormal": "fire_facility",

    "no_warning": "construction_prot",
    "no_barrier": "construction_prot",

    # 仅改名，不合并（重新定义后仍为独立类别）
    "sewage_odor": "sewage_overflow",
}

# 最终 24 类
FINAL = [
    ("traffic", "交通与通行", [
        ("road_occupancy", "占道经营/乱堆乱放"),
        ("vehicle_occupancy", "车辆占道"),
        ("blind_path_occupied", "盲道占用"),
        ("traffic_facility_damage", "交通设施损坏"),
    ]),
    ("municipal", "市政设施", [
        ("manhole_damage", "井盖缺失/破损"),
        ("road_surface_collapse", "路面塌陷"),
        ("drainage_flood", "排水/积水"),
        ("street_light_pole", "路灯/线杆损坏"),
    ]),
    ("fire", "消防安全", [
        ("fire_lane_blocked", "消防通道占用"),
        ("fire_facility", "消防设施/水源异常"),
    ]),
    ("building", "建筑安全", [
        ("structural_damage", "建筑结构损伤"),
        ("facade_risk", "外立面破损/坠落风险"),
        ("illegal_structure", "临时构筑物/私搭乱建"),
    ]),
    ("utility", "电气与燃气", [
        ("wire_fault", "电线裸露/私拉乱接"),
        ("distribution_box_fault", "配电设施故障"),
        ("gas_leak", "燃气泄漏"),
        ("gas_pipe_aging", "燃气管道老化"),
    ]),
    ("construction", "施工安全", [
        ("construction_prot", "施工防护缺失"),
        ("scaffold_guard", "脚手架/临边防护"),
        ("deep_pit", "深基坑风险"),
    ]),
    ("elevator_special", "电梯与特种设备", [
        ("elevator_trapped", "电梯困人"),
        ("elevator_stopped", "停运/异响"),
        ("elevator_inspection", "超期未检"),
    ]),
    ("environment_other", "环境与其他", [
        ("garbage_pile", "垃圾堆积"),
        ("sewage_overflow", "污水外溢"),
    ]),
]

CODE2NAME = {}
for mc, ml, subs in FINAL:
    for sc, sl in subs:
        CODE2NAME[sc] = (mc, ml, sl)

# 32 类 → 合并 5 组（-6 类）→ 26 类；再移除兜底类「其他」（-1）→ 25 类
assert len(CODE2NAME) == 25, f"类别数应为 25，实际 {len(CODE2NAME)}"

# 写入分类体系
tax_out = []
for mc, ml, subs in FINAL:
    tax_out.append({"code": mc, "label": ml,
                    "subcategories": [{"code": sc, "label": sl} for sc, sl in subs]})
json.dump(tax_out, open(os.path.join(HERE, '_taxonomy_final.json'), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=1)

# 污水重归类（数据修正）
reclass = {}
rp = os.path.join(POOL, 'sewage_odor', 'reclass.json')
if os.path.isfile(rp):
    reclass = json.load(open(rp, encoding='utf-8'))

# ---------- 改写评测集 ----------
print('=' * 72)
print('改写评测集 ground_truth.json')
print('=' * 72)

# 先收集所有条目
all_items = {}
for c in sorted(os.listdir(REAL)):
    gp = os.path.join(REAL, c, 'ground_truth.json')
    if not os.path.isfile(gp):
        continue
    j = json.load(open(gp, encoding='utf-8-sig'))
    for f, rec in j.get('items', {}).items():
        # 数据修正优先
        if c == 'sewage_odor' and f in reclass:
            tgt = reclass[f]
        elif c == 'sewage_odor':
            tgt = 'sewage_overflow'
        else:
            tgt = MERGE.get(c, c)
        rec = dict(rec)
        rec['subcategory'] = tgt
        rec['major_category'] = CODE2NAME.get(tgt, (None,))[0]
        all_items.setdefault(tgt, []).append((f, rec, c))

print(f'原始条目 {sum(len(v) for v in all_items.values())} 条')
print()
print(f'{"新类别":<32}{"条目":>6}')
print('-' * 72)
TH = 0
for k in sorted(all_items, key=lambda x: -len(all_items[x])):
    n = len(all_items[k])
    TH += n
    print(f'{CODE2NAME.get(k, ("","",k))[2]:<32}{n:>6}')
print('-' * 72)
print(f'{"合计":<32}{TH:>6}')

# 备份旧数据
bak = os.path.join(HERE, '_images_real_backup_32class')
if not os.path.isdir(bak):
    shutil.copytree(REAL, bak)
    print(f'\n已备份旧评测集 → {os.path.basename(bak)}')

# 重写：按新类别分目录
merged = os.path.join(HERE, 'images_merged')
if os.path.isdir(merged):
    shutil.rmtree(merged)
os.makedirs(merged, exist_ok=True)

for cat, entries in all_items.items():
    d = os.path.join(merged, cat)
    os.makedirs(d, exist_ok=True)
    gt_items = {}
    for f, rec, oldcat in entries:
        src = os.path.join(REAL, oldcat, f)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(d, f)
        if not os.path.isfile(dst):
            shutil.copy2(src, dst)
        gt_items[f] = rec
    mc, ml, sl = CODE2NAME.get(cat, (None, "", cat))
    json.dump({
        "_meta": {"category": f"{mc}/{cat}", "category_label": f"{ml}/{sl}",
                  "count": len(gt_items), "taxonomy": "v2-24class"},
        "items": gt_items,
    }, open(os.path.join(d, 'ground_truth.json'), 'w', encoding='utf-8'),
        ensure_ascii=False, indent=1)

print(f'\n新评测集已生成 → {os.path.basename(merged)}/')

# ---------- 重算指标 ----------
txt = open(EVAL_OUT, encoding='utf-8', errors='replace').read()
pat = re.compile(
    r"\[(正确|大类对|错误|漏报|误报|失败)\]\s+(\S+)\s+(\S+)\s+期望=(\S+)\s+实际=(\S+)")


def norm(s):
    if not s or s.startswith('('):
        return None
    s = s.strip()
    return s.split('/')[-1].lower() if '/' in s else s.lower()


rows = [{"mark": m.group(1), "cat": m.group(2), "file": m.group(3),
         "exp": m.group(4), "act": m.group(5)} for m in pat.finditer(txt)]

per = defaultdict(Counter)
T = Counter()
for r in rows:
    e, a = norm(r["exp"]), norm(r["act"])
    if e == 'sewage_odor' and r["file"] in reclass:
        e = reclass[r["file"]]
    if e:
        e = MERGE.get(e, e)
    if a:
        a = MERGE.get(a, a)
    key = e or "(负样本)"
    s = per[key]
    s["total"] += 1
    T["total"] += 1
    if e is None and a is None:
        s["ok"] += 1; T["ok"] += 1
    elif e is None:
        s["fp"] += 1; T["fp"] += 1
    elif a is None:
        s["fn"] += 1; T["fn"] += 1
    elif e == a:
        s["ok"] += 1; T["ok"] += 1
    else:
        em = CODE2NAME.get(e, ("?",))[0]
        am = CODE2NAME.get(a, ("?",))[0]
        if em != "?" and em == am:
            s["major"] += 1
            T["major"] += 1
        else:
            s["wrong"] += 1
            T["wrong"] += 1

print()
print('=' * 72)
print('最终指标（24 类）')
print('=' * 72)
print(f'  严格准确率  {T["ok"]}/{T["total"]} = {T["ok"]/T["total"]*100:.1f}%')
print(f'  大类命中    {T["ok"]+T["major"]}/{T["total"]} = '
      f'{(T["ok"]+T["major"])/T["total"]*100:.1f}%')
print(f'  漏报        {T["fn"]} ({T["fn"]/T["total"]*100:.1f}%)')
print(f'  误报        {T["fp"]} ({T["fp"]/T["total"]*100:.1f}%)')

json.dump({"merge": MERGE,
           "final_taxonomy": tax_out,
           "metrics": {"strict": T["ok"] / T["total"],
                       "major": (T["ok"] + T["major"]) / T["total"],
                       "n": T["total"], "fn": T["fn"], "fp": T["fp"]}},
          open(os.path.join(HERE, '_final_result.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('\n结果 → _final_result.json')
