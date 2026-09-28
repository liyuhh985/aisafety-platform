# 阶段 2 设计：槽位三类划分（A/B/C）+ missing 喂规划器 + 校验

- 日期：2026-09-27
- 执行文档：`docs/superpowers/plans/2026-09-27-dialogue-quality-execution.md`（阶段 2）
- 落点：`ai-module/core/slot_schemas.py`、`ai-module/core/dialogue_understanding.py`、`ai-module/core/assistant_graph.py`、`ai-module/core/dialogue_policy.py`（只读，未改）

## 1. 为什么重划：`critical` 布尔撑不住「问什么」

阶段 0 的 G1 实测（`ai-module/db/eval_question_target.txt`，64 条）：

| 项 | 数字 |
| --- | --- |
| `missing` 非空、该追问的样本 | 17 |
| 问句命中目标槽 | 5（**29.4%**） |
| 问了但问偏（问位置、问资源、提议建单） | 6 |
| **一条都没问（黑洞）** | 6（**35%**） |
| `missing` 为空（没有追问机会） | 47（73%） |

结论：真问题不是「问太多」，是**不问**和**问偏**。而 G4 显示 32 个小类里 **18 个的追问上界 ≥2 轮**（9 个上界 3）——
`critical=True` 标得太宽，把「写了更好」当成「不写不行」。

## 2. 判据（必须写成这个句式）

| 类 | 判据 | 处理 |
| --- | --- | --- |
| **A 决策级** | 缺了它，**风险等级或用户/系统该采取的动作会判错**（含该不该立即处置、该找谁处置） | **追问**（进 `missing`） |
| **B 报告级** | 结论与动作不变，但**法规适用 / 责任归属 / 处罚档次**会不同 | **不追问**，进报告「仍需确认」的**条件分支** |
| **C 装饰级** | 结论、动作、法规都不变（或已被其它字段覆盖） | 不问、不提 |

边界说明：A 与 B 的分界（「动作会错」vs「责任归属不同」）**本身是判断**。本文件里
「动作」包含**该找谁处置**（例如「找供水公司 / 维保单位 / 物业」算动作不同）。
凡是「结论方向不变、只是引哪一条法规不同」的一律 B。

## 3. 逐槽划分（9 套 schema / 32 个小类）

> **这是初判，需要人工复核。** 每条判据都写成「缺了它，什么会错」；复核时请只质疑判据，不要只看类别字母。

### 3.1 占道（`road_occupancy` / `vehicle_occupancy` / `blind_path_occupied`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `behavior` | **B** | 缺了它「这里违规占道」的结论不变；占用物决定**管辖主体**（摊贩→城管、车辆→交警）与适用法规 |
| `persistence` | **A** | 缺了它：长期占压→需上报执法处置；临时停放→可现场劝离。**用户该采取的动作会判错** |
| `blocked` | **A** | 缺了它：完全堵死→通行中断、需立即处置；部分占用→一般违规。**风险等级与紧迫性会判错** |

### 3.2 危房（`dangerous_building` / `wall_crack_lean`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `structure` | **A** | 缺了它：整体倾斜/沉降 vs 局部外墙开裂，**危险程度与「是否需立即撤离」会判错** |
| `occupancy` | **A** | 缺了它：有人居住→需立即疏散；无人→围挡隔离。**用户该采取的动作会判错** |
| `risk` | **C** | 缺了它不影响新结论：与规划器已返回的 `immediate_danger`（以及 `danger_veto` 词表）重复 |

### 3.3 消防通道（`fire_lane_blocked`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `blocker` | **A** | 缺了它：堆放**可燃杂物**→火灾风险等级高、可能起火；停放车辆→以阻碍通行为主。**风险等级会判错** |
| `persistence` | **A** | 缺了它：长期占用→需执法处置；临时停放→可现场劝离。**用户该采取的动作会判错** |
| `impact` | **B** | 缺了它「通道被占」的结论不变；是否影响消防车通行影响整改要求与处罚要件 → **法规适用不同** |

### 3.4 消防设施（`fire_equipment_fault`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `facility_type` | **A** | 缺了它：消火栓 / 喷淋 / 报警器 / 灭火器的**处置路径与责任主体完全不同**（供水公司 / 维保单位 / 物业），且失灵时的即时风险不同 → **该找谁处置会判错** |
| `condition` | **A** | 缺了它：完全无法使用→需立即更换并报消防；老旧→计划维护。**风险等级与动作会判错** |
| `function_impact` | **B** | 缺了它「设施故障」的结论不变；是否影响整栋消防功能影响危害范围认定 → **责任归属不同** |

### 3.5 高空坠物（`facade_fall` / `falling_object`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `source` | **A** | 缺了它：广告牌→可能需立即封闭现场（城管/业主）；外墙→物业/业主；阳台→住户。**紧迫程度与责任主体会判错** |
| `target` | **B** | 缺了它「有坠落隐患」的结论不变；下方是人行道还是车行道影响适用法规（是否涉及道路交通安全）→ **法规适用不同** |
| `exposure` | **B** | 缺了它结论不变；有无围挡/警示影响「是否已尽管理义务」→ **责任归属不同** |

### 3.6 井盖 / 道路（`manhole_damage` / `road_surface_collapse` / `drainage_flood`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `defect` | **A** | 缺了它：**缺失**（有坠井风险，需立即设警示/围挡）vs 破损/松动（可报修）。**紧急程度与用户该采取的动作会判错** |
| `traffic` | **B** | 缺了它「井盖有问题」的结论不变；是否影响通行影响处置优先级与法规适用 → **法规适用不同** |

> 遗留（不在本阶段范围）：`drainage_flood`（排水/积水）与 `road_surface_collapse`（路面塌陷）
> 目前复用本套槽位表，`defect` 的问句是「井盖是缺失、破损还是松动？」—— 对积水明显不对口。
> 实测里这句话**没被触发过**（模型自己写问句），所以是**潜在**问题。列在这里备查。

### 3.7 电气（`exposed_wire` / `distribution_box_fault` / `illegal_wiring` / `temporary_power`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `source` | **A** | 缺了它：**漏电**（即时触电风险，需立即断电）vs 裸露电线 vs 设备故障。**风险等级与动作会判错** |
| `contact` | **A** | 缺了它：可能被人/车接触到→需立即断电或隔离；接触不到→可报修。**风险等级会判错** |
| `risk` | **C** | 缺了它不影响新结论：冒烟/火花已被 `danger_veto` 词表（冒烟、火花）与 `immediate_danger` 覆盖 |

### 3.8 施工（`no_barrier` / `no_warning` / `scaffold_guard` / `deep_pit`）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `site` | **A** | 缺了它：「未围挡」这条**隐患是否成立**会判错（做了围挡 → 这条隐患不成立，只有别的隐患） |
| `safety` | **B** | 缺了它「防护不到位」的结论不变；有无安全警示影响处罚档次 → **处罚档次不同** |
| `impact` | **B** | 缺了它结论不变；是否影响通行影响处置优先级与法规适用 → **法规适用不同** |

### 3.9 其他（12 个小类，含 `gas_leak` / `elevator_*` / `garbage_pile` / `sewage_odor` / `other` 等）

| 槽 | 类 | 判据 |
| --- | --- | --- |
| `describe` | **A** | 缺了它**无法判断这是什么隐患**（该套表是兜底类，小类本身未被进一步确定）→ **结论完全无法给出** |

> 遗留（不在本阶段范围）：本套表覆盖 12 个小类，其中 `gas_leak`（燃气泄漏）、`elevator_trapped`（电梯困人）
> 这类高危小类也只有一句「能再具体描述一下」。这是**潜在**缺陷：实测里这些例子的问句都由模型
> 自己写、且对症（见阶段 0 的 G1/G3 产物），固定串触发 0 次。是否给它们单独写 schema 另议。

## 4. 结果：追问上界从 3 降到 2

| | 重划前 | 重划后 |
| --- | --- | --- |
| A 类（原 `critical`）个数分布 | 14×1 / 9×2 / 9×3 | **21×1 / 11×2 / 0×3** |
| 追问上界 | 3 轮 | **2 轮** |
| 上界 ≥2 的小类 | 18 / 32 | **11 / 32** |

没有做到「32 个小类全部上界 1」—— 因为剩下那 11 个小类的第 2 个 A 槽确实满足
「缺了它动作会判错」（例：危房的 `structure` 与 `occupancy`；消防通道的 `blocker` 与 `persistence`）。
而 G5-B 实测追问**均值 0.40 轮、最大 1 轮**，所以上界 2 在实践中几乎不会走到。

## 5. `Slot` 结构改动

```python
@dataclass
class Slot:
    key: str
    question: str
    value_class: str = DECISION_CLASS        # "A" | "B" | "C"

    def __post_init__(self) -> None:
        if self.value_class not in VALUE_CLASSES:
            raise ValueError(...)            # 不静默

    @property
    def critical(self) -> bool:
        """兼容旧调用点与既有测试：A 类 == 旧的 critical=True。"""
        return self.value_class == DECISION_CLASS
```

- `critical` 的**旧用法已全部迁移**：生产路径改读显式类别（见第 6 节的两个选择器）。
  属性保留的唯一理由是**兼容既有读取点与测试**，语义等价于「A 类」，不是第二套真相。
- 选择器（`core/slot_schemas.py`）：`unfilled_slots(value, filled, classes)`、
  `missing_decision_slots`（A）、`missing_report_slots`（A+B）。顺序 = schema 书写顺序 = 追问优先级。

## 6. `missing` 的两个口径

| 口径 | 内容 | 消费者 |
| --- | --- | --- |
| `rebuild_missing` → `state["missing"]` / `issue["missing"]` | **只 A 类** | 追问决策（`dialogue_policy`）、报告档位、建任务闸门 |
| `rebuild_report_missing` → `issue["report_missing"]` | **A+B 类** | 阶段 4 的「仍需确认」条件分支（**本阶段只准备字段，不接报告**） |

C 类两个都不进。

## 7. `missing` 喂规划器

`core/dialogue_understanding.build_planner_messages(messages, vision_summary, selected_major_code, missing, known_slots, subcategory_code)`
在系统提示里追加一段（实际拼进请求的文本）：

```
【当前焦点隐患的槽位状态】消防通道占用(fire_lane_blocked)
已知事实：blocker=私家车
仍缺的决策级信息：persistence（想确认的是：是长期还是临时？）
契约：question 必须针对上面「仍缺的决策级信息」里的其中一个来问，并且用你自己的话，
     不要照抄括号里的字；确实无需追问时 question 留空。
```

**注入条件：本会话已锁定小类**（`state["locked_subcategory"]` 非空）。
理由有两层：没有锁定时不存在「这条隐患缺什么」；且注入空上下文会让规划器误以为有活跃隐患。
副作用是**兼容性**：没有锁定小类时不传新参数，老的三参签名调用方（含既有测试替身）继续可用。

### 已知缺口（必须写下来）

**注入只对第 2 轮及以后生效。** 第 1 轮里锁定小类是**规划器运行之后**才定的，
所以第 1 轮的问句仍然只能来自「规划器自觉」或「`Slot.question` 固定兜底」。
实测证据（本地真模型，2026-09-27）：

```
输入：我们小区消防通道长期被私家车占用
→ subcategory=fire_lane_blocked, slots 里没抽到 persistence
→ 规划器问：这类占用是否已经影响到消防车通行或应急救援？   ← 问的是 impact（B 类）
```

即第 1 轮仍会「问偏」（且问的是 B 类槽）。这直接影响**阶段 5**（删固定兜底）：
在解决第 1 轮问句来源之前删掉兜底，第 1 轮会出现「该问不问」。
另外注意 `dialogue_policy._question_for_missing` 是**优先用规划器写的问句**的，
所以即使 `missing` 只含 A 类槽，代码也不会拦住规划器问 B 类槽 —— `missing` 目前只约束
「抑制追问」，不约束「问什么」。

## 8. 校验：`question_missing`（不静默）

`state["missing"]` 非空但这一轮没问出问题时，记录：

| 字段 | 内容 |
| --- | --- |
| `question_missing` | 缺失的键列表（`{code}_{slot}`） |
| `question_missing_reason` | `danger_veto` / `cautious` / `report` / `planner_no_question` |

- `planner_no_question` 用 `logger.warning`（这是我们真正想抓的「该问没问」）
- 其余三种是**按设计不问**，用 `logger.info`
- 每轮由 `understand` 的 `empty` 重置

## 9. 验收对照

| # | 要求 | 状态 |
| --- | --- | --- |
| 1 | A/B/C 划分有依据文档 + ≥5 小类样例；`critical` 旧用法迁移或明确理由 | 本文档（9 套 schema / 32 小类逐槽）；第 5 节 |
| 2 | B 类缺失**不触发追问**（有测试） | `tests/test_slot_value_classes.py::test_b_class_missing_never_triggers_a_followup`；**仅覆盖规划器没给问句的路径**，见第 7 节缺口 |
| 3 | 规划器提示词确实带上 `missing`（有测试） | `tests/test_planner_missing_contract.py`（断言拼进去的文本） |
| 4 | `question_missing` 有测试且不静默 | `tests/test_planner_missing_contract.py`（含 `caplog` 断言） |
| 5 | 本阶段不删固定兜底 | `dialogue_policy._question_for_missing` 未改 |
| 6 | 全量 pytest 0 失败 | `614 passed, 3 skipped` |

## 10. 对照测量：`missing` 喂规划器前 vs 后

原始产物：`ai-module/db/eval_missing_to_planner.txt`（脚本 `ai-module/db/measure_missing_to_planner.py`）
**每例只跑一次，无方差数据。** 真模型 `mimo-v2.6-flash`，2026-09-27，耗时 910 秒。

### 10.1 口径（受控 A/B）

```
T1  真规划器跑原始 query -> 小类 + 抽到的槽（= 第 1 轮结束时的状态）
    A 类缺失为空 -> 「空洞」例，没有可对比的追问目标，跳过
T2  同一段 messages（用户原话 + 助手回执 + 固定跟进语「就是这样，你还需要知道什么？」）跑两次：
      对照 before：不带 missing 上下文   == 改动前的行为
      处理 after ：带 missing / known_slots / subcategory_code
    两次只有「注入块」这一个差别
判定：问句归到哪个槽（复用 G1 的启发式）；命中的槽在 A 类缺失里 = 命中
```

### 10.2 结果

| 项 | 值 |
| --- | --- |
| QUERY_SET | 64 条，T1 成功 64、失败 0 |
| **A 类缺失为空的「空洞」例** | **54 / 64（84%）** |
| 可对比成对样本 | 10 |
| **对照 before 命中** | **3 / 10 = 0.300** |
| **处理 after 命中** | **8 / 10 = 0.800** |
| before / after 未问（黑洞） | 0 / 0 |

「空洞」从 G1 的 73%（47/64）升到 84%（54/64）—— 因为 A 类比旧的 `critical` 更窄：
又有 7 个输入不再需要追问。**这再次说明追问的设计价值只作用在一小部分输入上。**

### 10.3 人工复核（我的判断，不是盲测）

启发式归类有两个方向的噪声，我逐条读了原文：

| # | 小类 / A 类缺失 | before | after |
| --- | --- | --- | --- |
| 1 | road_occupancy / persistence | 命中 | 命中 |
| 2 | vehicle_occupancy / persistence | **未命中**（「需要我帮你整理成一条上报记录吗？」） | 命中（「每天常态还是最近才出现」） |
| 3 | blind_path_occupied / persistence | 命中 | 命中 |
| 4 | blind_path_occupied / persistence | 命中 | 命中 |
| 5 | fire_lane_blocked / persistence | 命中（启发式误判为归不出） | 命中 |
| 6 | wall_crack_lean / occupancy | 命中（启发式误判为 `structure`，因为句子里有「裂缝」） | 命中 |
| 7 | distribution_box_fault / contact | **未命中**（「电表箱具体在哪个小区或哪条路上？」= 问位置） | 命中（「位置是否容易被路人直接碰到」） |
| 8 | no_warning / site | **未命中**（「需要我生成报告或创建任务吗？」= 提议建单） | 命中（「施工区域周围有没有拉围挡」） |
| 9 | elevator_inspection / describe | **未命中**（「这部扶梯现在还在正常运行吗？」不是要求描述） | 命中（「有没有异响、抖动或急停」） |
| 10 | other / persistence + blocked | **未命中**（「需要我帮你进一步处理吗？」） | 命中（「一直长期放着还是刚放不久」） |

人工口径：**before 5/10 = 0.500 → after 10/10 = 1.000**。
启发式的假阴性在两个 arm 各 2 条（对称），所以两种口径给出的**增量都是 +50 个百分点**。

### 10.4 这批数据说明什么

- before 的 5 条未命中里，**4 条是「问位置」或「提议建单」**，1 条是问了一个已经填过的槽 ——
  与 G1 的结论完全一致（未命中的形态是问位置、问资源，不是问槽）。
- after 的 10 条**全部**落在 A 类缺失上，而且措辞各不相同（没有一条照抄括号里的提示）——
  说明「点名缺口 + 让它自己组织语言」这两件事可以同时成立。

### 10.5 方法学局限（不粉饰）

1. **样本小**：n=10，单次采样，无方差数据。每条 ±1 就是 ±10 个百分点。
2. **T2 的跟进语固定**（「就是这样，你还需要知道什么？」）。这句本身**邀请追问**，
   所以两个 arm 都必然给出问句 —— 这会让「黑洞」这一项恒为 0，测不出 before 真实的不问率。
   G1 里 before 侧的黑洞率是 35%，这次没有复现，**不是因为它消失了，是因为测法不同**。
3. **人工复核不是盲测**（我知道哪个是哪个 arm），有确认偏误风险。启发式数字（3→8）是
   事先定好的仪器，人工数字（5→10）是事后判读，两个都列出来就是为了让这个偏差可见。
4. T1 的槽位抽取结果被当成「第 1 轮结束时的事实」，但它本身也是模型输出，会有误差；
   抽取漏了槽会让 A 类缺失变多（对两个 arm 影响相同）。
