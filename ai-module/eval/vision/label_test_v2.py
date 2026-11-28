# -*- coding: utf-8 -*-
"""
test 集标注 v2：双模型 + 仲裁，带断点续跑

针对上一轮 40% 网络失败率的改进：
  · 并发降到 4
  · 重试 5 次，指数退避
  · 每张图独立落盘（标注结果缓存），失败的下次自动补
  · 支持 --resume 只跑失败的

存储：test_set/labels/<model_tag>/<cat>/<file>.json
      单张一文件，任何时刻中断都不丢
"""
import argparse
import json
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
LABELS = os.path.join(HERE, 'test_set', 'labels')

PROMPT = """你是城市安全隐患排查专家。请判断这张图片中的隐患属于哪一类。

只输出 JSON：
{"has_hazard": true或false, "sub": "小类英文码", "severity": "高或中或低", "difficulty": "easy或medium或hard", "evidence": "画面特征,25字内", "text_in_image": true或false}

类别表（小类码: 含义）：
road_occupancy 占道经营/乱堆乱放
vehicle_occupancy 车辆占道
blind_path_occupied 盲道占用
traffic_facility_damage 交通设施损坏
manhole_damage 井盖缺失破损
road_surface_collapse 路面塌陷
drainage_flood 排水积水
street_light_pole 路灯线杆损坏
fire_lane_blocked 消防通道占用
fire_facility 消防设施/水源异常
structural_damage 建筑结构损伤(危房/墙体开裂倾斜)
facade_risk 外立面破损/坠落风险(瓷砖脱落/高空坠物)
illegal_structure 临时构筑物/私搭乱建
wire_fault 电线裸露/私拉乱接
distribution_box_fault 配电设施故障
gas_leak 燃气泄漏
gas_pipe_aging 燃气管道老化
construction_prot 施工防护缺失(无围挡/无警示)
scaffold_guard 脚手架/临边防护
deep_pit 深基坑风险
elevator_trapped 电梯困人
elevator_stopped 停运/异响
elevator_inspection 超期未检
garbage_pile 垃圾堆积
sewage_overflow 污水外溢

规则：
- 画面确实没有隐患 → has_hazard=false，sub 留空字符串
- 只依据画面可见证据，不推测
- 拿不准时选最接近的类别
只输出 JSON，不要解释。"""

VALID_SUB = {
    'road_occupancy', 'vehicle_occupancy', 'blind_path_occupied', 'traffic_facility_damage',
    'manhole_damage', 'road_surface_collapse', 'drainage_flood', 'street_light_pole',
    'fire_lane_blocked', 'fire_facility', 'structural_damage', 'facade_risk',
    'illegal_structure', 'wire_fault', 'distribution_box_fault', 'gas_leak',
    'gas_pipe_aging', 'construction_prot', 'scaffold_guard', 'deep_pit',
    'elevator_trapped', 'elevator_stopped', 'elevator_inspection',
    'garbage_pile', 'sewage_overflow',
}

MODELS = {
    'A': 'deepseek-v4.1-flash',
    'B': 'glm-5.3-flashx',
    'C': 'deepseek-v4-pro',
}


def label_path(tag, cat, f):
    d = os.path.join(LABELS, tag, cat)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f + '.json')


def read_label(tag, cat, f):
    p = label_path(tag, cat, f)
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            return None
    return None


def write_label(tag, cat, f, rec):
    p = label_path(tag, cat, f)
    try:
        json.dump(rec, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass


def call_one(client, path, retries=5):
    for att in range(retries):
        try:
            out = client.analyze_json(path, PROMPT)
            if not isinstance(out, dict):
                return None
            hz = out.get('has_hazard')
            sub = str(out.get('sub') or '').strip().lower()
            if sub not in VALID_SUB:
                sub = ''
            sev = str(out.get('severity') or '').strip()
            if sev not in ('高', '中', '低'):
                sev = '中'
            dif = str(out.get('difficulty') or '').strip()
            if dif not in ('easy', 'medium', 'hard'):
                dif = 'medium'
            return {
                'has_hazard': bool(hz), 'sub': sub, 'severity': sev,
                'difficulty': dif,
                'evidence': str(out.get('evidence') or '')[:50],
                'text_in_image': bool(out.get('text_in_image')),
            }
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ('402', '401', '403', 'Payment')):
                raise
            if att < retries - 1:
                time.sleep(min(2 ** att, 16))
    return None


def collect_tasks():
    tasks = []
    for c in sorted(os.listdir(TEST)):
        d = os.path.join(TEST, c)
        if not os.path.isdir(d) or c == 'labels':
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                tasks.append((c, f, os.path.join(d, f)))
    return tasks


def run_model(tag, model, tasks, workers):
    """跑一个模型，跳过已完成的"""
    from mimo_client import VisionClient
    cl = VisionClient('opendesign')
    cl.model = model

    todo = [(c, f, p) for c, f, p in tasks if read_label(tag, c, f) is None]
    if not todo:
        print(f'  [{tag}] {model}: 全部已完成')
        return 0, 0

    print(f'  [{tag}] {model}: 待跑 {len(todo)}/{len(tasks)}', flush=True)
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(call_one, cl, p): (c, f) for c, f, p in todo}
        done = 0
        for fu in as_completed(futs):
            c, f = futs[fu]
            try:
                r = fu.result()
            except Exception:
                r = None
            if r:
                write_label(tag, c, f, r)
                ok += 1
            else:
                fail += 1
            done += 1
            if done % 40 == 0:
                print(f'      进度 {done}/{len(todo)}  成功{ok} 失败{fail}', flush=True)
    print(f'  [{tag}] 完成：成功 {ok}，失败 {fail}')
    return ok, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--stage', default='all', choices=['ab', 'arb', 'merge', 'all'])
    args = ap.parse_args()

    tasks = collect_tasks()
    print(f'test 集 {len(tasks)} 张\n')

    if args.stage in ('ab', 'all'):
        print('=== 第一轮：双模型独立标注 ===')
        for tag in ('A', 'B'):
            run_model(tag, MODELS[tag], tasks, args.workers)
        print()

    # 找分歧
    agree, dispute = [], []
    for c, f, p in tasks:
        a = read_label('A', c, f)
        b = read_label('B', c, f)
        if not a or not b:
            continue
        if a['has_hazard'] == b['has_hazard'] and a['sub'] == b['sub']:
            agree.append((c, f, a))
        else:
            dispute.append((c, f, p, a, b))

    print(f'=== 比对 ===')
    print(f'  一致   {len(agree)}')
    print(f'  分歧   {len(dispute)}  ({len(dispute)/max(len(agree)+len(dispute),1)*100:.0f}%)')
    print()

    if args.stage in ('arb', 'all') and dispute:
        print('=== 第二轮：第三方仲裁 ===')
        from mimo_client import VisionClient
        cl = VisionClient('opendesign')
        cl.model = MODELS['C']
        todo = [(c, f, p) for c, f, p, a, b in dispute
                if read_label('C', c, f) is None]
        print(f'  待仲裁 {len(todo)}/{len(dispute)}')
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(call_one, cl, p): (c, f) for c, f, p in todo}
            ok = fail = 0
            for fu in as_completed(futs):
                c, f = futs[fu]
                try:
                    r = fu.result()
                except Exception:
                    r = None
                if r:
                    write_label('C', c, f, r)
                    ok += 1
                else:
                    fail += 1
            print(f'  仲裁完成：成功 {ok}，失败 {fail}')
        print()

    # 合并
    if args.stage in ('merge', 'all'):
        final = {}
        stats = Counter()
        for c, f, p in tasks:
            a = read_label('A', c, f)
            b = read_label('B', c, f)
            cc = read_label('C', c, f)

            if a and b and a['has_hazard'] == b['has_hazard'] and a['sub'] == b['sub']:
                rec = dict(a); src = 'A=B'
            elif cc:
                rec = dict(cc); src = 'C仲裁'
            elif a and b:
                rec = dict(a); src = 'A(仲裁缺失)'
            elif a:
                rec = dict(a); src = 'A(单模型)'
            elif b:
                rec = dict(b); src = 'B(单模型)'
            else:
                continue

            rec['label_source'] = src
            rec['subcategory'] = rec.pop('sub', '')
            rec['major_category'] = None
            final[f'{c}/{f}'] = rec
            stats[src] += 1

        json.dump(final, open(os.path.join(HERE, 'test_set_annotations.json'),
                              'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('=== 合并完成 ===')
        for k, v in stats.items():
            print(f'  {k}: {v}')
        print(f'  总计 {len(final)} 张 → test_set_annotations.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
