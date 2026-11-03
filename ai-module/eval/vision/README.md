# 城市安全隐患视觉识别 · 评测集

真实新闻图片构建的领域评测集，用于横向比较不同视觉模型在本业务场景下的表现。

---

## 快速开始

```bash
cd ai-module/eval/vision
export PYTHONIOENCODING=utf-8      # Windows PowerShell: $env:PYTHONIOENCODING='utf-8'

# 评测（复用缓存的预测结果）
python final_eval_v2.py

# 查看报告
cat REPORT_FINAL.md
```

---

## 核心结果

| 指标 | 数值 |
|---|---:|
| **正样本严格准确率** | **71.3%** |
| 正样本大类准确率 | 77.0% |
| 漏报率 | 3.4% |
| 误报率 | 53.5% |
| 标注一致性（Kappa） | 0.705 |

测试集：378 张独立图片（178 正样本 + 200 负样本），从未参与调参。

> **注意**：误报率 53.5% 主要源于提示词"拿不准即报警"策略，
> 详见 `REPORT_FINAL.md` 第四节。

---

## 目录结构

```
eval/vision/
├── REPORT_FINAL.md            最终报告（先看这个）
├── ANNOTATION_RULES.md        标注判定规则
├── TAXONOMY_REFACTOR.md       分类体系合并依据（32→25 类）
├── README.md                  本文件
│
├── _taxonomy.json             原始分类体系（32 小类）
├── _taxonomy_final.json       最终分类体系（25 小类）
├── _merge_final.json          32→25 的映射表
│
├── test_set/                  测试集（378 张，带标注）
│   ├── <category>/            图片
│   ├── labels/                两个模型的独立标注原始记录
│   └── pred/                  被评测模型的预测结果（缓存）
├── test_set_annotations.json  测试集合并后的标注
├── *_final_eval_v2.json       评测指标
│
├── images_merged/             dev 集（1,447 张，25 类，已调参）
├── dev_annotations/           dev 集标注（仅 JSON，图在 images_merged）
├── negatives/                 负样本（216 张采集 + 61 张清洗合格）
│
├── pool/                      原始图片池 3,385 张（含 1,520 张未使用）
│
└── _archive/                  归档：历史脚本、旧文档、中间结果
```

---

## 生产流程

```
1. 采集      harvest.py           百度多关键词多页 → pool/
2. 筛选      screen.py            分辨率/去重/水印/图库域名
3. 粗筛      triage.py            模型快速剔除整改中/正面案例/产品图
4. 标注      annotate.py          判定类别、严重度、难度、文字标记
5. 复检      audit.py             核对核心视觉特征是否成立
6. 专项核查  recheck_cat.py       针对低分类别逐张复核
7. 定稿      build_dataset.py     生成 images_merged/
```

## 评测流程

```
1. 切分      split_dev_test.py    从未用过的图里切出 test 集
2. 标注      label_test_v2.py     双模型独立标注 + 第三方仲裁
3. 一致性    kappa.py             算 Cohen's Kappa
4. 评测      final_eval.py        推理（带缓存）
5. 打分      final_eval_v2.py     准确率 / CI / 分层统计
6. 报告      gen_final_report.py  生成 REPORT_FINAL.md
```

---

## 关键实现细节

### 模型输出需要映射

**被评测模型输出的是旧 32 类名称**（提示词未同步更新），
打分前必须映射到新 25 类体系：

```python
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
```

忘记映射会导致准确率虚低（实测从 58.2% 掉到 51.3%）。

### 百度采集需要 Cookie

先 `GET https://image.baidu.com/` 拿 `BAIDUID`，再用同一 Session 请求 acjson。
否则返回 82 字节空壳。必须用 `replaceUrl[0].ObjURL` 取原图，`middleURL` 只有 500px。

### 网络限流

OpenDesign 在 `workers>6` 时频繁返回 SSL/连接重置。
推荐 `--workers 4`，重试 5 次，每张图独立落盘（断点续跑）。

### API 错误不能当成结果

401/402/403 必须向上抛出并中止，否则会把失败的请求当成"保留"，
污染整个数据集（这个坑踩过一次，8 个类别被污染）。

---

## 已知局限

| 项 | 说明 |
|---|---|
| 数据来源 | 网络新闻图，偏向"已曝光的典型隐患"，非真实业务分布 |
| 负样本比例 | 测试集负样本占 53%，真实业务中正常图约占 95% |
| 标注方式 | AI 标注 + AI 交叉验证（Kappa 0.705），非人工专家 |
| 类别覆盖 | 17 个类别样本 <10 张，准确率不具统计意义 |
| 未覆盖 | 跨季节、跨城市、跨设备的时间漂移 |

---

## 环境

```
Python 3.11+
pillow, requests, opencv-python, numpy, rapidocr-onnxruntime
```

模型配置见 `ai-module/config.py`：

```ini
VISION_PROVIDER=opendesign
OPENDESIGN_BASE_URL=https://amr-link.open-design.ai/v1
OPENDESIGN_VISION_MODEL=deepseek-v4.1-flash
```

---

## 归档说明

`_archive/` 里是开发过程中的一次性脚本和中间结果，
保留是为了可追溯，正常使用不需要。

其中 `_archive/docs/` 有早期版本的交接文档，
如果之后要重构可以翻看踩坑记录。
