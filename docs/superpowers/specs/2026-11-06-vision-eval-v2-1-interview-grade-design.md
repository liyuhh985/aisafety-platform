# Vision Evaluation v2.1 Interview-Grade Design

> 状态：approved direction, pending written-spec review  
> 日期：2026-11-06  
> 范围：`ai-module/eval/vision/v2/` 的评估协议、数据构建、冻结、对比实验和面试证据链  
> 目标岗位：Java 后端开发 / AI 应用开发实习

## 1. 问题定义

当前 v2 标注工作已经完成，但候选池不能直接冻结：

- 200 个候选中只有 124 个可用标签；
- 最终正样本 25 个、负样本 99 个；
- test split 只有 8 个最终正样本；
- 118 条 `ai_direct` 标签尚未人工确认；
- 当前 `freeze_test.py` 按 `candidate_kind` 计数，而不是按最终 `has_hazard` 计数。

如果直接把当前数据冻结，会得到三个不可接受的后果：

1. 用候选池类别冒充最终标签；
2. 把 AI 初标包装成人工评估集；
3. 用 8 个 test 正样本报告召回率。

本设计不解决“如何把数字做得好看”，而解决“如何得到经得起追问的真实证据”。

## 2. 设计原则

本方案参考成熟视觉评估集的共同做法，而不是简单模仿规模：

- COCO：固定任务定义、固定 split、固定指标，结果可复现；
- LVIS：承认长尾类别，不把少样本类别混成一个总体准确率；
- Open Images：标签体系必须明确，未标注类别不能被随意当作负样本；
- MVTec AD：正常样本、缺陷类型和分布变化都要覆盖，不能只用随机负样本。

参考链接：

- COCO: https://cocodataset.org/#detection-eval
- LVIS: https://arxiv.org/abs/1908.03195
- Open Images: https://storage.googleapis.com/openimages/web/evaluation.html
- MVTec AD: https://openaccess.thecvf.com/content_CVPR_2019/papers/Bergmann_MVTec_AD_--_A_Comprehensive_Real-World_Dataset_for_Unsupervised_Anomaly_Detection_CVPR_2019_paper.pdf

由此确定四项原则：

1. 任务定义先于数据收集；
2. 类别配额和困难负样本优先于总样本量；
3. 人工确认、去重和冻结先于模型评测；
4. 面试只引用冻结 test 上可追溯的真实指标。

## 3. 备选方案与决策

### 方案 A：继续原计划 100 正 / 100 负

优点：

- 与已有 plan 数字一致；
- 总规模看起来完整。

问题：

- 需要重新确认约 75 个正样本；
- 按原 quota，test 每个大类只有 3 到 4 个正样本；
- 候选正样本噪声高，继续按原方式抽取会重复返工。

结论：不采用。

### 方案 B：直接冻结当前 25 正 / 99 负

优点：

- 最快；
- 保留已完成的标注工作。

问题：

- test 只有 8 个正样本；
- 无法支持有意义的召回率结论；
- 正负分布严重失衡；
- 不能称为 benchmark。

结论：不采用。

### 方案 C：v2.1 平衡诊断集，160 张

- 80 个正样本；
- 80 个硬负样本；
- dev/test 各 80 张；
- test 40 正 / 40 负；
- 8 个大类各 10 个正样本，test 每类 5 个。

优点：

- 每个大类都有明确配额；
- test 正负平衡，能分别报告 recall 和 FPR；
- 比 100/100 总标注量少，但大类覆盖更好；
- 能做 baseline/final prompt 对比，而不是只展示一个数据集。

结论：采用。

## 4. 目标与非目标

### 4.1 目标

1. 建立一个可复现、人工确认、冻结后不再修改的小型视觉诊断集；
2. 评估二分类隐患识别和 8 大类分类；
3. 比较 baseline prompt 与 final prompt；
4. 用具体错误案例解释模型边界；
5. 让每条面试结论都能追溯到 manifest、prediction 或 metrics 文件。

### 4.2 非目标

- 不估计真实用户生产分布；
- 不证明线上误报率或线上准确率；
- 不声称 25 个子类都有统计可靠性；
- 不声称标签来自多名专家共识；
- 不让视觉模型自动创建正式工单；
- 不把平衡测试集准确率解释成生产准确率；
- 不把模型置信度当作已校准概率。

## 5. 数据集设计

### 5.1 总配额

| split | 正样本 | 负样本 | 合计 |
|---|---:|---:|---:|
| dev | 40 | 40 | 80 |
| test | 40 | 40 | 80 |
| 总计 | 80 | 80 | 160 |

### 5.2 正样本配额

8 个大类各 10 个正样本：

| major category | 总数 | dev | test |
|---|---:|---:|---:|
| traffic | 10 | 5 | 5 |
| municipal | 10 | 5 | 5 |
| fire | 10 | 5 | 5 |
| building | 10 | 5 | 5 |
| utility | 10 | 5 | 5 |
| construction | 10 | 5 | 5 |
| elevator_special | 10 | 5 | 5 |
| environment_other | 10 | 5 | 5 |

配额约束：

- 每个大类至少覆盖 2 个子类；不足 2 个子类的大类必须记录原因；
- 同一 `source_category` 在一个大类的 10 个正样本中最多占 5 个；
- dev/test 按子类来源尽可能均衡，避免同一来源集中在单侧；
- 任何大类不足 10 个合格正样本时暂停构建，不跨大类借样本；
- 不使用 v1 `test_set/` 或 `images_merged/` 中的图片。

### 5.3 负样本设计

负样本不是随机风景图，而是 8 组硬负样本，每组 10 张，test/dev 各 5 张：

| confuser group | 负样本定义 |
|---|---|
| traffic | 车辆、行人或临时设施正常通行，无占道或设施损坏 |
| municipal | 井盖、路面、排水、路灯正常，或仅有不构成隐患的表面水迹 |
| fire | 消防器材完好、消防通道畅通 |
| building | 建筑表面存在污渍、旧化或装饰性裂缝，但无可见结构风险 |
| utility | 线缆整理规范、配电箱闭合、燃气设施外观正常 |
| construction | 围挡、警示、脚手架和临边防护符合要求 |
| elevator_special | 电梯正常运行，检验标识有效，无困人或停运证据 |
| environment_other | 垃圾容器关闭、周边整洁，无堆积或外溢 |

硬负样本必须满足：

- 肉眼可见且能说明为什么不是目标隐患；
- 不能依赖“图片没拍清楚”作为负样本理由；
- 不能把维修过程、示意图、海报或截图当作负样本；
- 与对应大类的正样本在场景上有视觉相似性。

### 5.4 正负标签定义

正样本：

- 图片可见至少一个当前 taxonomy 中的目标隐患；
- 记录主要隐患的大类和子类；
- 多隐患图片允许存在，但若两个不同大类同样显著，排除该图片；
- 类别以主要安全风险为准，不按文字描述推断。

负样本：

- 图片可见目标场景，但不存在当前 taxonomy 中的目标隐患；
- 必须写明排除隐患的可见依据；
- 不确定是否合规时排除，不强行标负。

统一排除项：

- 答案依赖文字、标题、海报说明或新闻字幕；
- 示意图、插画、AI 生成图、纯产品图；
- 维修/施工过程导致无法判断最终状态；
- 图片不可用、严重遮挡、分辨率不足；
- 多个大类无法确定主类别；
- 重复或近重复图片。

## 6. 数据质量与去重

### 6.1 精确去重

- 所有候选使用 SHA-256；
- 数据集内部不允许重复 SHA-256；
- 与 v1 `test_set/`、`images_merged/` 的哈希集合不得重叠。

### 6.2 近重复去重

- 使用 64-bit dHash；
- Hamming distance `<= 4` 视为近重复；
- 近重复图片不得同时进入数据集；
- dev/test 之间额外执行一次近重复检查。

### 6.3 抽样

- 固定随机种子 `20261106`；
- 先按大类、候选来源和 split 配额分层；
- dev/test 分配在标签确认前完成；
- 被人工排除的样本只允许从同一大类/同一 split 的候选中补位；
- 不允许为了提高某个指标换入更容易的样本。

## 7. 人工复核协议

### 7.1 复核范围

- dev 80 张和 test 80 张全部人工复核；
- `ai_direct` 只能作为初标提示，不能直接成为最终标签；
- 评测模型不能参与最终标签确认；
- 复核人：余博洋；
- 只能表述为“单人复核”，不能表述为“专家共识”。

### 7.2 复核字段

每条最终标签至少包含：

```text
reviewer
review_time
label_status=reviewed
label_source
has_hazard
major_category
subcategory
difficulty
text_in_image
notes
```

约束：

- `has_hazard=true` 时，`major_category` 和 `subcategory` 必须与 taxonomy 一致；
- `has_hazard=false` 时，类别字段为空，`notes` 必须说明正常依据；
- `text_in_image` 只记录与判断实质相关的文字；
- 水印、账号名、视频时间戳不算 `text_in_image`；
- 无法判断时标记排除，不强行选择。

### 7.3 标签来源

冻结 test 中只允许：

- `human_reviewed`；
- `human_confirmed_ai_prelabel`；
- `legacy_review`。

禁止：

- `ai_direct`；
- 无 reviewer 的标签；
- 无 review_time 的标签。

## 8. 冻结协议

`freeze_test.py` 必须按最终标签而不是候选类型校验：

### 8.1 强校验

1. 总样本 160；
2. dev 80，test 80；
3. test 正样本 40，负样本 40；
4. test 8 个大类各 5 个正样本；
5. test 所有 `label_status=reviewed`；
6. test 所有标签来源允许；
7. test 所有 major/subcategory 合法；
8. test/dev SHA-256 无重叠；
9. test/dev dHash 无近重复；
10. 所有 test 文件存在；
11. 协议版本和模型配置已记录；
12. prompt SHA-256 已记录。

### 8.2 冻结产物

`frozen_test_manifest.json` 包含：

- `protocol_version=v2.1`；
- `dataset_seed`；
- `frozen_at`；
- 每个 test item 的 `file_sha256`；
- 每个 test item 的 `label_sha256`；
- 每个 test item 的 `prompt_sha256`；
- 正负计数和 major 计数；
- baseline/final prompt ID。

冻结后：

- 不修改 test 标签；
- 不修改抽样规则；
- 不根据 test 结果调 prompt；
- 如需修改，创建新版本并重新冻结，不能覆盖旧 manifest。

## 9. 对比实验设计

### 9.1 两个实验臂

| arm | 定义 |
|---|---|
| baseline | 当前生产 `VISION_PROMPT` 的冻结快照 |
| final | 只在 dev 上迭代后的提示词版本 |

约束：

- 两个 arm 使用同一模型、同一图片、同一 temperature；
- 只在 dev 上调 final prompt；
- test 冻结后，两个 arm 各运行一次；
- 不根据 test 结果选择第三个 prompt；
- 模型 ID、prompt SHA-256、运行时间必须记录。

### 9.2 评测设置

- 模型：当前 v2 配置的视觉模型；
- temperature：0，以减少单次评测的随机性；
- 每张图片单独输出 JSON；
- 输出缺失、JSON 解析失败、非法类别都算失败，不得静默丢弃；
- 原始响应和结构化预测分别保存。

### 9.3 置信度与人工复核

保留现有 `confidence` 字段，并定义评估侧规则：

- `confidence=低` 视为需要人工复核；
- `confidence=中/高` 才进入自动判定分析；
- 缺失或非法 confidence 一律视为需要人工复核；
- JSON 解析失败或类别非法时，原始二分类计为失败，复核感知指标计入人工复核；
- 该规则用于评估“自动判定 + 人工复核”的产品语义；
- 不把模型置信度解释为概率。

## 10. 指标设计

### 10.1 原始二分类指标

对每个 arm 计算：

```text
TP = positive gold and positive prediction
TN = negative gold and negative prediction
FP = negative gold and positive prediction
FN = positive gold and negative prediction

Recall = TP / (TP + FN)
Precision = TP / (TP + FP)
FPR = FP / (FP + TN)
F1 = 2 * Precision * Recall / (Precision + Recall)
Balanced Accuracy = (Recall + (1 - FPR)) / 2
```

同时报告：

- Wilson 95% 区间；
- TP/TN/FP/FN 原始计数；
- JSON 解析失败率；
- 非法 major/subcategory 率。

### 10.2 复核感知指标

把 `confidence=低` 视为不自动判定：

- `review_rate = low-confidence items / total items`；
- `auto_coverage = high/medium valid items / total items`；
- `auto_recall = TP_auto / total positives`；
- `critical_miss_rate = FN_auto / total positives`；
- `auto_FPR = FP_auto / total negatives`。

其中：

- `TP_auto`：正样本被自动判为有隐患；
- `FN_auto`：正样本被自动判为无隐患；
- `FP_auto`：负样本被自动判为有隐患；
- 低置信度正样本不算自动召回，必须由人工复核补回。

### 10.3 大类指标

仅对正样本报告：

- 大类混淆矩阵；
- 8 大类 macro recall；
- 每类样本数和正确数；
- 每类点估计仅作诊断，不宣称稳定可靠。

不报告：

- 子类 accuracy；
- 25 类总体排名；
- 用平衡集数据推算生产准确率。

## 11. 错误分析

必须输出 `ERROR_ANALYSIS.md`，至少包含：

1. 每个 arm 的主要错误类型和数量；
2. 至少 3 个具体错误桶；
3. 每个错误桶的典型图片哈希或文件名；
4. 错误的可见原因；
5. 是否属于标签问题、提示词问题、模型能力问题或产品规则问题；
6. 对下一次迭代的具体动作。

错误桶示例：

- 合规场景被判成施工防护缺失；
- 湿路面被判成积水；
- 正常线缆整理被判成裸露线路；
- 建筑污渍被判成结构损伤；
- 井盖附近破损被判成路面塌陷；
- 消防器材存在被判成消防设施故障；
- `other` 兜底导致类别不可用。

## 12. 面试验收门槛

只有以下条件全部满足，才开始写正式面试讲解：

- 160 条最终标签完成人工复核；
- test 40 正 / 40 负；
- 8 个大类 test 各 5 个正样本；
- baseline 和 final 在同一冻结 test 上完成；
- 两份 metrics 文件均存在；
- 至少 3 个错误桶有可追溯证据；
- 面试稿中每个数字都能指向文件；
- 明确写出单复核、小样本、公开场景限制。

如果 final 没有优于 baseline：

- 不写“优化有效”；
- 改讲失败实验、原因分析和下一步；
- 不允许重新抽取 test 或更换指标掩盖结果。

### 12.1 禁止性表述

- 生产准确率；
- 真实业务分布；
- 人工专家共识；
- 25 类全部通过统计评估；
- 线上误报率；
- 模型可以自动建单；
- 评估集“完美”或“金标准”。

## 13. 面试讲解结构

最终讲解按以下顺序，控制在 90 秒主叙事加追问：

1. **背景**：城市安全项目中的视觉隐患识别，模型结果需要人工确认；
2. **问题**：旧评估存在候选噪声、AI 标签和 test 正样本不足；
3. **判断**：停止冻结，重做协议而不是包装指标；
4. **设计**：80 正 / 80 负，8 大类各 10，硬负样本，单人全量复核；
5. **防自欺**：SHA-256 + dHash 去重、固定 seed、冻结、baseline/final 同 test；
6. **结果**：给出真实 recall、FPR、macro recall 和 review rate；
7. **错误**：讲 3 个具体误判和根因；
8. **产品决策**：低置信度转人工，用户确认后才进入异步建单链路；
9. **边界**：公开图片、小样本、单复核，不代表生产分布。

## 14. 预期文件结构

在 `ai-module/eval/vision/v2/` 下：

```text
PROTOCOL.md
dataset_manifest.json
review_worksheet.csv
review_decisions.jsonl
frozen_test_manifest.json
predictions/
  baseline/
  final/
metrics.baseline.json
metrics.final.json
metrics.comparison.json
ERROR_ANALYSIS.md
REPORT.md
INTERVIEW_NOTES.md
build_manifest.py
finalize_labels.py
freeze_test.py
score_v2.py
tests/
```

现有 v2 draft 产物保留为审计记录：

- `review_worksheet.pending_backup.csv`
- `dataset_manifest.pending_backup.json`
- `REVIEW_SUMMARY.md`

## 15. 实施顺序

1. 更新 `PROTOCOL.md` 到 `v2.1`；
2. 修正 `freeze_test.py` 的最终标签计数和门禁测试；
3. 增加 SHA-256 与 dHash 去重测试；
4. 增加正样本分层配额和硬负样本配额；
5. 生成候选 manifest 和复核 worksheet；
6. 人工复核 160 张并生成最终标签；
7. 冻结 test manifest；
8. 固定 baseline/final prompt 快照；
9. 在冻结 test 上各运行一次；
10. 计算 metrics、生成错误分析和报告；
11. 通过面试验收门槛后写 `INTERVIEW_NOTES.md`；
12. 更新面试进度文档和索引。

## 16. 测试策略

单元测试：

- 二分类指标和 Wilson 区间；
- macro recall；
- 冻结门禁按 `has_hazard` 计数；
- `candidate_kind` 与最终标签冲突时拒绝冻结；
- 大类配额不足时拒绝构建；
- test/dev 哈希重叠和 dHash 近重复时拒绝；
- 缺少 prediction 时评分失败。

集成测试：

- 使用 160 条 fixture 构建完整 manifest；
- 人工标签从 worksheet 导入后可复现；
- 冻结产物包含所有 hash；
- baseline/final 评分可重复。

网络测试：

- 不作为 pytest 默认项；
- 模型调用只在显式评测命令中执行；
- 测试运行不产生 API 费用。

## 17. 风险与应对

| 风险 | 应对 |
|---|---|
| 某些大类正样本不足 | 定向补样；不足则暂停，不跨类借样本 |
| 候选正样本质量差 | 只从同类候选补位，人工全量确认 |
| 人工复核成本高 | 每批 20 张，先正样本和硬负样本，不自动接受 AI 标签 |
| test 被无意污染 | 冻结后只读；prompt、阈值和标签哈希记录 |
| 模型输出随机 | temperature=0，单次运行并记录配置 |
| 没有第二个人工标注员 | 明确单人复核限制，不报告专家 Kappa |
| 指标不理想 | 如实报告，转为失败实验和错误分析 |
| 公开图片可能出现在模型训练数据中 | 明确公开场景限制，不推断生产泛化 |

## 18. 成功标准

本设计成功不以“指标高”为标准，而以以下事实为准：

- 数据配额和标签可复现；
- test 冻结可验证；
- baseline/final 对比公平；
- 所有面试数字有证据文件；
- 能解释至少 3 个真实错误和 1 个工程取舍；
- 明确说明评估集不能代表生产。

达到这些条件后，评估集面试内容才视为可讲。

