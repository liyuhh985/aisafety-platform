# Taxonomy v3 全 33 类视觉诊断集（200 张实拍）评测基线报告

> 日期：2026-11-27
> 模型：`OpenDesign`（`deepseek-v4.1-flash`，`temperature=0.0`）
> 提示词快照：[prompt_v3.txt](../../ai-module/eval/vision/v3/prompt_v3.txt)（对应 [prompts.py](../../ai-module/prompts.py) 修复冲突后版本）
> 数据集清单：[diagnostic_manifest.v3.json](../../ai-module/eval/vision/v3/diagnostic_manifest.v3.json)
> 原始指标 JSON：[metrics.v3_baseline.json](../../ai-module/eval/vision/v3/metrics.v3_baseline.json)

---

## 1. 数据集构造与定标说明（非双模型伪标注）

为彻底消除旧版 `v2` 测试集（80 张）中 **13 个小类正样本为 0**（含 4 个新增类全部为 0）及负样本混入示意图/产品图的问题，新建 `v3` 全 33 类诊断集：

- **样本规模**：共 **200 张**全部为实拍照片，经 SHA-256 与 dHash（距离 > 3）严格去重：
  - **正样本 132 张**：严格按 **33 个小类 × 每小类 4 张** 均等覆盖；
  - **负样本 68 张**：全实拍同场景正常/规范对照硬负样本（排除旧版书封面、交通标志图鉴、商品效果图等）。
- **来源渠道**：
  - 开放真实摄影图源（`Wikimedia Commons API` + `Openverse API`）：补齐 `tree_fall_hazard`、`confined_space`、`hazmat_storage`、`other`、`elevator_inspection`、`elevator_stopped`、`gas_leak` 及对应规范场景硬负样本；
  - 本机图库盘活清洗：从 `pool/`（优先未进旧 `v2b` 测试集的图）与 `negatives/` 中筛选其余主体类及本土 `ebike_hazard`（居民楼飞线充电、楼梯间违停电动车）。
- **定标方式**：**未使用 GLM + MiMo 双模型伪标注**，全部 200 张由人工/多模态读图通过联系表（`eval/vision/v3/previews/*.jpg`）逐张核验确认并定标。

---

## 2. 核心总体指标（200 张全集）

| 指标 | 数值 | Wilson 95% CI | 说明 |
|---|---:|---|---|
| **Recall（召回率）** | **0.955** (126/132) | [0.904, 0.979] | `TP=126`, `FN=6` |
| **Precision（精确率）** | **0.894** (126/141) | — | — |
| **FPR（误报率）** | **0.221** (15/68) | [0.138, 0.333] | `TN=53`, `FP=15` |
| **F1 / Accuracy** | **0.923 / 0.895** | — | — |
| **大类准确率（MajorAcc）** | **0.795** (105/132) | — | 正样本大类一致率 |
| **小类准确率（SubAcc）** | **0.674** (89/132) | — | 正样本 33 小类严格一致率 |
| **Review-Aware 覆盖** | **96.5%** | — | `review_rate=0.035`, `critical_miss_rate=0.023` |
| **JSON 解析 / 类别合法性** | **0 失败 / 0 非法** | — | `invalid_confidence=7`（模型返回低置信度触发复核） |

### 分层诊断（纯视觉 30 类 vs 弱视觉 3 类）

| 分层 | 样本数 | Recall | MajorAcc | SubAcc | 包含类别 |
|---|---:|---:|---:|---:|---|
| **pure_visual** | 120 (30类×4) | **0.967** | **0.833** | **0.717** | 常规视觉可辨别隐患 |
| **weak_visual_evidence** | 12 (3类×4) | **0.833** | **0.417** | **0.250** | `gas_leak`, `elevator_inspection`, `confined_space` |

---

## 3. 新增 4 类与关键薄弱类逐类表现

### 新增 4 个小类首份实测诊断

| 小类 | 样本数 | Recall | MajorAcc | SubAcc | 主要预测结果 / 混淆去向 |
|---|---:|---:|---:|---:|---|
| `fire/ebike_hazard`（电动自行车违规停放/充电） | 4 | **1.00** | **1.00** | **1.00** | 4/4 全部准确命中 |
| `municipal/tree_fall_hazard`（树木倒伏/断枝风险） | 4 | **1.00** | **1.00** | **1.00** | 4/4 全部准确命中 |
| `environment_other/hazmat_storage`（危化品存运） | 4 | **1.00** | **1.00** | **1.00** | 4/4 全部准确命中 |
| `construction/confined_space`（有限空间作业风险） | 4 | **1.00** | **0.25** | **0.00** | **3 张误判 `manhole_damage`，1 张误判 `no_warning`** |

### 表现突出小类（SubAcc = 4/4）与主要短板小类

- **4/4 全对小类（11 个）**：`road_occupancy`、`manhole_damage`、`road_surface_collapse`、`drainage_flood`、`ebike_hazard`、`illegal_wiring`、`deep_pit`、`scaffold_guard`、`hazmat_storage`、`garbage_pile`、`tree_fall_hazard`。
- **突出短板小类（SubAcc ≤ 0.25）**：
  1. `confined_space` (`0.00`) → `manhole_damage` (3)、`no_warning` (1)
  2. `temporary_power` (`0.00`) → `distribution_box_fault` (3)、`exposed_wire` (1)
  3. `no_warning` (`0.00`) → `deep_pit` (2)、`manhole_damage` (1)、`no_barrier` (1)
  4. `gas_leak` (`0.00`) → `gas_pipe_aging` (1)、`hazmat_storage` (1)、`other` (1)、`FN` (1)
  5. `sewage_odor` (`0.25`) → `garbage_pile` (2)、`drainage_flood` (1)

### 高频混淆与误报分析（下一轮调优方向）

- **Prompt 规则缺口**：视觉 Prompt 尚未明确区分“井口打开 + 有人清掏/探查作业（`confined_space`）”与“无人施工的井盖破损（`manhole_damage`）”，以及“工地临时配电（`temporary_power`）”与“一般配电故障（`distribution_box_fault`）”。
- **硬负样本（15 条 FP）两类成因**：
  1. **旧 `negatives/` / 候选池自带隐蔽缺陷（被视觉模型真实检出）**：例如 `NEGSEW08.jpg` 格栅确实有横条断裂缺失、`NEGGAR01.jpg` 右侧禁停牌下确实停着红车、`ab0df63f6e35.jpg` 蓝桶实际放在木托盘而非防漏塑料托盘上——说明后续可对这几张负样本继续替补净化；
  2. **正常作业/微湿路面过敏感误报**：如雨后微湿路面被判 `drainage_flood`、环卫工清理落叶被判堵塞加无锥桶、专业工具掀井盖巡检被判 `no_warning`。

---

## 4. 局限性声明

1. `v3` 为公开图库与本地存量清洗后的人工单审诊断集（每小类 4 张），单类小样本置信区间仍较宽，不能替代线上真实流量 A/B 或生产级分布评估；
2. 仅包含视觉单帧信息，对于高度依赖上下文/气味/日期文字的类别（`gas_leak`、`elevator_inspection`、`confined_space`），实际线上需结合用户文字对话槽位联合判断。
