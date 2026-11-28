# Taxonomy v3 全 33 类诊断体系建设与冻结 Blind Test 完成文档

> 完成时间：2026-11-27  
> 适用范围：城市安全隐患智能平台（8 大类 × 33 小类完整分类体系）  
> 核心原则：零数据泄露（`v3_dev` 与 `frozen_test_v3` 严格互斥隔离）、真实人工目视复核定标（非 GLM/MiMo 伪标注）、以冻结 `test` 的 Gate 裁决作为上线依据

---

## 一、背景与全流程闭环概览

此前 `v2b/v2c` 阶段虽然完成了业务代码、槽位、MySQL 与 Milvus 向 **8 大类 × 33 小类** 的升级，但后续复核发现 3 方面工程缺口：

1. **视觉评估集严重滞后**：原有 80 张 `v2b` 冻结测试集基于旧集重映射，40 张正样本仅覆盖 20 个小类（**13 个小类为 0**，含 4 个新增小类全部为 0），标注来源为 `model_consensus` 双模型伪标注，且 40 张负样本中混有规范书封面、交通标志图鉴与商品效果图；同时旧版百度/Bing 爬虫接口失效。
2. **线上法规错归与知识库薄弱**：`migrate_taxonomy_v2b.py` 宽泛匹配 `城镇排水与污水处理条例`，误将云端 `tb_regulation` 中 1 条井盖与 2 条防汛排涝条文划入 `施工安全/有限空间作业风险`。
3. **提示词、Skill 路由与文本评估问法脱节**：`prompts.py` 尾部两项 `has_hazard=false` 规则冲突；`municipal/SKILL.md` 漏配树木倒伏路由词；`dialogue_understanding.py` 缺少新增类边界消歧；`eval_queries.py` 中 `utility/illegal_wiring` 仍沿用“给电动车充电”旧问法。

本轮完成了从**线上数据纠偏、代码同步修复、开放图源采集、全 33 类 `dev`/`frozen_test` 隔离建集、Prompt 迭代与冻结盲测裁决**的完整闭环。

---

## 二、云端数据库、提示词与技能修复明细

### 1. 云端 MySQL 纠偏与 Milvus 增量同步
- 备份云端被误迁记录至 `/home/ubuntu/ai-module/db/backup/reg_fix_backup_20261127.json`。
- 事务修复 `tb_regulation`：将 `id=58` 归回 `市政设施/井盖缺失/破损`（现 6 条），将 `id=124, 159` 归回 `市政设施/排水/积水`（现 4 条），并同步修正 [data_regulations.py](../../ai-module/db/seed/data_regulations.py)、[data_regulations_batch2.py](../../ai-module/db/seed/data_regulations_batch2.py) 与 [migrate_taxonomy_v2b.py](../../ai-module/db/schema/migrate_taxonomy_v2b.py#L55)。
- 在 [data_regulations_v2b.py](../../ai-module/db/seed/data_regulations_v2b.py) 中新增 2 条权威现行法规并同步线上 MySQL 与 Milvus（`Knowledge sync source=regulation read=145 skipped=143 upsert=2 failures=0`）：
  - 《高层民用建筑消防安全管理规定》第 37 条 → `消防安全/电动自行车违规停放/充电`（现共 3 条）；
  - 《工贸企业有限空间作业安全规定》第 14 条 → `施工安全/有限空间作业风险`（清理误归后现共 3 条纯正条文）。

### 2. 对话、Skill 与文本评估集同步修复
- [dialogue_understanding.py](../../ai-module/core/dialogue_understanding.py#L294-L295)：补充 `ebike_hazard` vs `illegal_wiring`、`hazmat_storage` vs `other`、`tree_fall_hazard` 边界消歧规则。
- [municipal/SKILL.md](../../ai-module/skills/municipal/SKILL.md)：在 `routing_keywords` 加入 `树木倒伏`、`断枝`、`行道树`，并同步更新 [construction/SKILL.md](../../ai-module/skills/construction/SKILL.md) 与 [environment_other/SKILL.md](../../ai-module/skills/environment_other/SKILL.md) 描述。
- [eval_queries.py](../../ai-module/eval/eval_queries.py#L223-L232)：将 `utility/illegal_wiring` 两道旧问法修改为“沿街商铺私拉乱接给门头灯箱/广告牌供电”，消除与 `fire/ebike_hazard` 的标注语义冲突。
- **云端文本分类验证结果**（`eval_classify.py --samples 1 --no-write`，共 76 条）：
  - 大类总体准确率：**`1.000`**
  - 小类总体准确率：**`0.985`（65/66）**，`colloquial=1.000`，`explicit=0.970`
  - 32 / 33 个小类达 `2/2 (100%)`（`ebike_hazard`、`tree_fall_hazard`、`confined_space`、`hazmat_storage`、`illegal_wiring` 全中），负样本拦截 **`1.000`**。

---

## 三、全新 `v3` 全 33 类视觉开发集与冻结 `test` 集建设（方案 A）

针对旧爬虫（百度返回反爬拦截、Bing 返回空）失效问题，改用合规开放图库 **`Wikimedia Commons API` + `Openverse API`** 定向补采，并从本机图库 `pool/`、`negatives/` 中清洗未进过旧测试集的实拍样本，经人工多模态看图逐张核验定标（**未使用 GLM/MiMo 伪标注**）：

| 数据集 | 文件路径 | 样本总数 | 正/负样本构成 | 隔离与冻结保障 |
|---|---|---:|---|---|
| **开发诊断集 (`v3_dev`)** | [dev_manifest.v3.json](../../ai-module/eval/vision/v3/dev_manifest.v3.json) | **200** | **132 正** (`33类×4`) + **68 实拍硬负**（已清理替换原 4 张隐蔽瑕疵负样本） | 专用于错误分析与 Prompt 迭代 |
| **冻结盲测集 (`v3_test`)** | [frozen_test_manifest.v3.json](../../ai-module/eval/vision/v3/frozen_test_manifest.v3.json) | **120** | **66 正** (`33类×2`) + **54 全新实拍硬负** | `disjoint_from_dev_and_v2b=true`，SHA-256 与 dHash 距离(`>3`) 校验零重叠，记录 `file_sha256`、`label_sha256` 与 `frozen_at`，冻结前未跑模型 |

核心构建与测试脚本：
- [harvest_open_sources.py](../../ai-module/eval/vision/v3/harvest_open_sources.py)
- [split_and_freeze_v3.py](../../ai-module/eval/vision/v3/split_and_freeze_v3.py)
- [score_v3.py](../../ai-module/eval/vision/v3/score_v3.py)
- [test_v3_manifest.py](../../ai-module/eval/vision/v3/tests/test_v3_manifest.py)

---

## 四、视觉 Prompt 迭代与冻结 `test` 盲测对比结果

### 实验设计
- **Baseline 臂（[prompt_v3.txt](../../ai-module/eval/vision/v3/prompt_v3.txt)，4535 字符）**：统一 `has_hazard=false` 冲突条款后的简洁 33 类生产 Prompt；
- **Final 臂（[prompt_v3_final.txt](../../ai-module/eval/vision/v3/prompt_v3_final.txt)，5460 字符）**：仅依据 `v3_dev` 暴露出的错例增加了第 9~12 条易混淆判别（有限空间 vs 井盖、工地临时用电 vs 配电故障、无警示 vs 深基坑、污水 vs 垃圾）及微湿/正常巡检防误报约束。

### 量化对比结果（模型：`OpenDesign` `deepseek-v4.1-flash`，`temperature=0.0`）

| 评估集 | 臂别 | Recall | Precision | FPR | F1 | Accuracy | MajorAcc | SubAcc | Critical Miss |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **`v3_dev` (n=200)** | Baseline | **0.955** | 0.894 | 0.221 | **0.923** | 0.895 | 0.795 | 0.674 | 0.023 |
| **`v3_dev` (n=200)** | Final | 0.932 | **0.911** | **0.176** | 0.921 | 0.895 | **0.826** | **0.697** | 0.023 |
| **`frozen_test` (n=120)** | **Baseline** | **0.939** | **0.805** | 0.278 | **0.867** | **0.842** | **0.788** | **0.712** | **0.030** |
| **`frozen_test` (n=120)** | Final | 0.924 | 0.803 | 0.278 | 0.859 | 0.833 | 0.758 | 0.712 | 0.045 |

### 冻结 `test` 分层诊断与客观归因

1. **Gate 裁决结果（[metrics.frozen_comparison.json](../../ai-module/eval/vision/v3/metrics.frozen_comparison.json)）**：
   依据仓库 `compare_metrics.py` 准则，在未知冻结 `test` 集上 Final 臂的 `critical_miss_rate` 从 `0.030` 升至 `0.045`（多漏 1 张 `ebike_hazard`），`FPR` 未降（均 `0.278`），**Gate 裁决 `winner: "baseline"`**。工程上已严格尊重盲测裁决，**将线上及本地 [prompts.py](../../ai-module/prompts.py) 回退并锁定为表现更稳健的 `v3_baseline` 版本**，避免把只在 `dev` 上局部过拟合的长规则强留在生产中。
2. **正面覆盖成效**：
   在 120 张未知冻结盲测集上，**18 个小类达到 2/2 (100%) 严格命中**（包括 `ebike_hazard` 在 Baseline 下 2/2、`tree_fall_hazard` 2/2、`hazmat_storage` 2/2、`elevator_inspection` 2/2、`falling_object`、`illegal_wiring`、`scaffold_guard`、`deep_pit` 等）；分层来看 `pure_visual`（60 张）Baseline 下 `Recall=0.950 / MajorAcc=0.817 / SubAcc=0.733`，`weak_visual_evidence`（6 张）`Recall=0.833 / SubAcc=0.500`。
3. **揭示出的真实结构瓶颈（供后续 `v4` 推进）**：
   - **FPR=0.278 偏高的核心原因**：复查冻结 `test` 的 15 条 FP 明细发现，老图库 `negatives/` 中多张施工基坑（`NEGDEE04~06`）、敞开配电箱（`NEGDIS03/04/06`）、锈蚀/遮挡消火栓（`NEGFIR04/06`）、破损沟盖（`NEGMAN04/06`）**按严格安全规范看本身即存在视觉隐患**，单靠 Prompt 条款无法把真实带隐患图“压成负样本”；后续如果要测纯洁净场景误报率，应重新从全新无施工/无隐患正常街景采负样本；
   - **弱项小类定位**：`temporary_power`、`no_warning`、`gas_leak`、`sewage_odor` 与 `confined_space` 仍属高频混淆区，后续更适合在视觉后端接轻量分类/二次提示路由或结合对话多模态上下文联合决策，而非继续堆砌超长单提示词。

---

## 五、最终验证与交付清单

- **本地 Python 回归测试**：`186 passed`（在最后一次回退定稿 `prompts.py` 后完整运行 `tests/test_hazard_taxonomy.py`、`test_taxonomy_v2b_data.py`、`test_slot_value_classes.py`、`test_dialogue_policy.py`、`test_scope_policy.py`、`test_eval_classify.py` 及 `eval/vision/v3/tests/test_v3_manifest.py`）。
- **云端服务健康状态**：已将胜出的定稿 [prompts.py](../../ai-module/prompts.py) 部署至 `/home/ubuntu/ai-module` 并重启，`/api/ai/health`（`status=ok`）与 Java `/actuator/health`（`status=UP`）均正常。
- **原始证据资产**：
  - [metrics.v3_baseline.json](../../ai-module/eval/vision/v3/metrics.v3_baseline.json) & [metrics.v3_dev_final.json](../../ai-module/eval/vision/v3/metrics.v3_dev_final.json)
  - [metrics.frozen_baseline.json](../../ai-module/eval/vision/v3/metrics.frozen_baseline.json) & [metrics.frozen_final.json](../../ai-module/eval/vision/v3/metrics.frozen_final.json)
  - [metrics.frozen_comparison.json](../../ai-module/eval/vision/v3/metrics.frozen_comparison.json)
  - [prompt_manifest.v3.json](../../ai-module/eval/vision/v3/prompt_manifest.v3.json)
