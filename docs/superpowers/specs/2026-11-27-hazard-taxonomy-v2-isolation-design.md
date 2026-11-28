# 城市安全隐患两级分类体系（Taxonomy v2）隔离重构与评估重建设计方案

> 状态：proposed（待执行）
> 日期：2026-11-27
> 适用范围：Python AI 编排与评估层（`ai-module/`）、Java 业务层（`safety-service/`、`safety-web/`）、前端常量与视图（`.frontend-work/`）、MySQL / Milvus 语料与工单数据
> 依赖核心：`core/hazard_taxonomy.py`、`core/slot_schemas.py`、`core/dialogue_understanding.py`、`core/scope_policy.py`、`prompts.py`、`HazardTypeNormalizer.java`、`hazardTaxonomy.js`

---

## 1. 背景与重构动机

### 1.1 项目真实定位（一切分类决策的基准）
从全栈代码、角色权限与业务闭环看，本系统的定位是**“市民参与上报 + 管理员统筹派单 + 处突专员整改验收”的城市公共安全综合治理平台**：
- **核心业务域**：城市公共空间隐患，以及具有公共安全外溢风险的社区/建筑/设施隐患（由 `dialogue_understanding.py` 的 `premises_scope` 与 `scope_policy.py` 共同守卫，排除纯粹私人户内琐事与内部导视标识）。
- **分类在系统中的 4 个实质作用**：
  1. **应急定级**：触发即时危险避险指引（`emergency_guidance`）与 `risk_level`；
  2. **决策追问**：驱动 `slot_schemas.py` 中 A 类（决定动作/风险/处置主体）追问与 B 类报告分支；
  3. **法规与案例检索**：`_pick_keyword` 直接以“小类中文标签 + 槽位值”检索 `tb_regulation` / `tb_hazard_case`；
  4. **条线派单分流**：区分交警、城管、消防、住建、供电、燃气、水务、园林、应急、市监等处置主体。

### 1.2 当前系统的四大结构性矛盾
1. **生产体系（32 类）与视觉评估体系（25 类）双轨分裂**：
   - `eval/vision/` 此前基于 1,433 张新闻图自行做了 `32→25` 映射（`TAXONOMY_REFACTOR.md`、`final_eval_v2.py` 的 `MERGE`），引入了 `facade_risk`、`structural_damage`、`wire_fault`、`pit_protection` 等**线上代码根本不存在的私有代码**。
   - **不能直接把视觉 25 类方案照搬到线上**：它把 `temporary_power`（住建 JGJ 46）、`illegal_wiring`（私拉飞线）、`exposed_wire`（绝缘破损）强行三合一，也把 `no_barrier`、`no_warning`、`deep_pit` 合并成 `pit_protection`——这会直接破坏线上法规检索、A/B 槽位追问和执法责任主体区分。
2. **线上存在 3 组“视觉不可分 + 槽位同构 + 处置同源”的真冗余小类**：
   - `wall_crack_lean` vs `dangerous_building`（文本分类 Top-1 混淆对，槽位完全同构，视觉双向混淆）；
   - `facade_fall` vs `falling_object`（槽位完全同构，案例库标注已自相矛盾）；
   - `fire_water_abnormal` vs `fire_equipment_fault`（前者无专用槽位、视觉准确率 0%/84% 被判成后者）。
3. **12 个小类槽位退化 + 施工/市政槽位错配**：
   - 燃气（`gas_leak`、`gas_pipe_aging`）、电梯（`elevator_*`）、交通设施、路灯杆等 12 个小类目前在 `slot_schemas.py` 中退化为通用 `"其他"`（仅一句 `describe`）；
   - `drainage_flood`（排水/积水）与 `road_surface_collapse`（路面塌陷）目前复用“井盖是否缺失破损”的槽位问句；
   - `scaffold_guard`、`deep_pit`、`no_warning` 复用 `no_barrier` 的唯一 A 类槽 `site`（“施工区域是否做了围挡？”）。
4. **`environment_other/other` 沦为垃圾桶，且引发高危误定级与 53.5% 视觉误报**：
   - **高危溢出**：`data_cases_batch3.py` 中的危化品违规储存/分装（3 起重大案）、有限空间硫化氢中毒（2 起）、`data_regulations_batch2.py` 的《危险化学品安全管理条例》《工贸企业有限空间作业安全规定》，以及 `eval_queries.py` 中 `other` 的标准测试用例（“公共区域出现来源不明危化品桶”）全部被迫塞进 `environment_other/other`，且在 `dialogue_understanding.py` 中因“环境和其他为 `low`”被错误默认定为低风险。
   - **高频错放**：电动自行车进楼入户/架空层违停充电相关国家新规（《国办发〔2024〕19号》《GB 43854-2024》）和重大火灾案例（南京雨花台、北京通州）被硬劈进 `illegal_wiring` 和 `fire_lane_blocked`；市政行道树倒伏断枝无类可归。
   - **规则误报**：`prompts.py` 第 92 行“图片模棱两可、信息不完整时必须设 `has_hazard: true` 并归入 `other`”导致 `REPORT_FINAL.md` 中 200 张负样本误报 107 张（其中 40 张落在 `other`）。

---

## 2. 分类隔离重构的四条硬准则

执行本次重构时，所有边界取舍必须严格遵守以下规则：
1. **单一真相源（SSOT）**：全仓（Python 生产、Java 后端、前端 UI、RAG 语料、文本评估集、视觉评估集）统一使用 `core/hazard_taxonomy.py` 定义的 Canonical v2 编码，**彻底废除 `eval/vision/` 私有合并码与 `MERGE` 补丁**。
2. **合并准入条件**（必须同时满足）：① 主管处置部门/主干法规一致；② 现场外观/市民口语边界难以稳定区分；③ 合并后可通过 A 类槽位无损区分细微处置差异。
3. **禁止合并红线**：凡**处置部门不同**（如城管 vs 交警 vs 无障碍法规；民用电气 vs 工地临时用电）或**应急响应等级截然不同**（如电梯困人 vs 停运异响；燃气泄漏 vs 管道老化；未设围挡 vs 深基坑滑移）的小类，**绝不合并**，改用**硬边界优先级规则 + 独立槽位**进行隔离。
4. **向后兼容不中断（Zero-Downtime Compatibility）**：所有被合并或重命名的旧编码、旧中文路径，必须在 Python `normalize_taxonomy`、Java `HazardTypeNormalizer`、前端 `hazardTaxonomy.js` 中保留只读归一化映射，同时提供幂等数据库清洗脚本完成存量收敛。

---

## 3. Taxonomy v2 规范全表（8 大类 × 33 小类）

本次方案采用 **“合并 -3、新增 +4”**（32 → 33 小类），保留全部 8 个 canonical `major_code` 不变（避免破坏 `skills/<major>/SKILL.md`、前端大类筛选与 Milvus 过滤契约）。

> **重要命名约定**：新中文小类名称中如含 `/`（如 `危房/结构开裂倾斜`），**必须确保前后端解析与历史相同**：Python `normalize_taxonomy` 先按 `major_code/sub_code` 或精确中文路径匹配；Java `HazardTypeNormalizer.add()` 以 `majorLabel + "/" + subLabel` 为主键精确存入 `TOKEN_TO_PATH`；前端 `hazardTaxonomy.js` 优先以 `subcategoryPathMap.get(trimmed)` 全串精确匹配，再处理 `/` 切分（注意 `hazardTaxonomy.js` 第 163 行 `split("/")` 逻辑只用于英文 `majorCode/subCode`，由于步骤 1 `subcategoryPathMap` 已先行精确命中中文全路径，因此中文路径含 `/` 仍可安全匹配，但仍建议检查所有 `split("/")` 处避免误切中文）。

### 3.1 全量类别定义与隔离边界

#### （1）交通与通行 `traffic`（4 小类）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `road_occupancy` | `占道经营/乱堆乱放` | `medium` | 城管 /《城市道路管理条例》 | 有主货物、摊位、货架、装修材料占用人行道/车行道；**无主垃圾弃置归 `garbage_pile`**。 |
| `vehicle_occupancy` | `车辆占道` | `medium` | 交警 /《道路交通安全法》 | 普通城市道路、人行道、非机动车道、黄色网格线违停；**若停在盲道上优先 `blind_path_occupied`；若占用消防车/救援通道优先 `fire_lane_blocked`**。 |
| `blind_path_occupied` | `盲道占用` | `medium` | 城管+残联+检察公益诉讼 /《无障碍环境建设法》 | **高优先级**：无论占用物是车辆、共享单车、摊位还是地桩，只要明确压占/损毁盲道砖，一律主归此类。 |
| `traffic_facility_damage` | `交通设施损坏` | `medium` | 交警/交通/公路部门 /《公路安全保护条例》 | **仅限公共道路/路口/街边**交通信号灯、道路护栏、交通标志、标线、减速带、凸面镜、限高架损坏；**商场/小区内部导视牌判 `out_of_scope`；公园/河道非交通护栏不归此类**。 |

#### （2）市政设施 `municipal`（5 小类，新增 1 个）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `manhole_damage` | `井盖缺失/破损` | `medium` | 市政/排水/水务/权属单位 /《民法典》1258条 | 圆形井盖、方形雨水篦子、沟盖板缺失、破损、移位、沉降松动（含井盖周边有危险洞口）。 |
| `road_surface_collapse` | `路面塌陷` | `high` | 市政道路养护/水务抢修 | 路面自然塌陷或地下管网掏空形成的不规则深坑、空洞；**人工开挖的规整施工沟槽且无围挡/警示归 `no_barrier`/`no_warning`**。 |
| `drainage_flood` | `排水/积水` | `medium` | 市政排水/应急防汛 /《突发事件应对法》 | 雨水积水、下穿隧道/立交桥下内涝、地下车库入口雨水倒灌导致通行受阻或淹车；**以清水/雨水积涝和阻断通行为主，黑臭污水外溢/工业偷排归 `sewage_odor`**。 |
| `street_light_pole` | `路灯/线杆损坏` | `medium` | 城市照明/供电/通信 /《城市照明管理规定》 | 公共路灯不亮、灯杆/电线杆/通信杆倾斜折断、底座开裂、杆体漏电、灯罩脱落；**交通信号杆/限高架归 `traffic_facility_damage`**。 |
| **`tree_fall_hazard`** `[新增]` | `树木倒伏/断枝风险` | `medium` | 园林绿化/市政应急 | 公共道路、公园、小区公共区域行道树倾斜倒伏、大型枯枝悬垂、树干劈裂或压覆线缆/阻断道路；**与 `street_light_pole`（杆件）及 `falling_object`（建筑物高空坠物）彻底隔离**。 |

#### （3）消防安全 `fire`（3 小类，合并 1 组、新增 1 个）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `fire_lane_blocked` | `消防通道占用` | `high` | 消防救援/物业/公安 /《消防法》28、60条 | **扩充边界**：① 室外黄黑斜纹/消防车通道/消防登高面/小区急救通道被车辆或杂物堵塞；② **室内楼梯间、疏散走道、安全出口、消防连廊被堆放可燃杂物或锁闭**（优先于 `vehicle_occupancy` 与 `garbage_pile`）。 |
| `fire_equipment_fault` | `消防设施/水源故障` | `high` | 消防救援/维保单位/供水/物业 /《消防法》16条、GB 50974 | **合并原 `fire_water_abnormal`**：消火栓、灭火器、自动喷淋、火灾报警器、**防火门/防火卷帘/应急照明及疏散指示标志**损坏/失效/被遮挡；以及**消防水池缺水、消防管网无水无压、室外消火栓被埋压**。 |
| **`ebike_hazard`** `[新增]` | `电动自行车违规停放/充电` | `high` | 消防/住建/物业/市场监管 / 国办发〔2024〕19号、GB 43854-2024 | **高优先级专项**：电动自行车或锂电池**进楼入户、进电梯、在楼梯间/门厅/架空层违规停放或充电、户外飞线给电动车充电**。注：若在户外拉线给电动车充电，**主类归 `ebike_hazard`**，可并发标注 `utility/illegal_wiring`。 |

#### （4）建筑安全 `building`（3 小类，合并 2 组）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `dangerous_building` | `危房/结构开裂倾斜` | `high` | 住建/房管/街道 /《城市危险房屋管理规定》、JGJ 125 | **合并原 `wall_crack_lean`**：承重墙/柱/梁开裂、房屋整体倾斜、地基不均匀沉降、砖木腐朽失稳、**私拆承重墙/私挖地下室/违法加层导致结构变形或开裂**（靠 A 类槽 `structure` 区分裂损程度）。 |
| `falling_object` | `高空坠物/外立面脱落` | `high` | 物业/业主/城管/公安 /《民法典》1253-1254条、《刑法》291条之二 | **合并原 `facade_fall`**：建筑外墙瓷砖/抹灰/保温层/幕墙玻璃空鼓开裂脱落、外挂空调支架/广告牌/花盆/窗扇松动坠落，以及人为高空抛物（靠 A 类槽 `source` 分流责任主体与法规）。 |
| `illegal_structure` | `违规搭建` | `medium` | 城管/自然资源规划 /《城乡规划法》64条 | 视觉可见或明确陈述的无证搭棚、顶楼违建阳光房、占用公共露台/消防连廊违建彩钢房；**若违建已造成结构超载、承重墙拆除或墙体开裂，主类归 `dangerous_building`**。 |

#### （5）电气与燃气 `utility`（5 小类，全保留）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `exposed_wire` | `裸露/老化电线` | `high` | 供电/物业/电力维保 / GB/T 13869 | **非工地、非明显私接路径**的既有电线电缆绝缘层破损、铜芯外露、低垂拖地或浸水漏电。 |
| `distribution_box_fault` | `配电设施故障` | `high` | 供电/物业/电力维保 | 配电箱、电表箱、配电室/分支箱箱门缺失敞开、接线端子烧蚀焦糊、冒烟打火、防鼠封堵失效。 |
| `illegal_wiring` | `私拉乱接` | `high` | 供电/城管/消防/物业 | 非工地场景从室内/门面/公共路灯箱私自牵拉临时电源线（如给冰柜、取暖器供电）；**明确为电动车充电优先归 `fire/ebike_hazard`**。 |
| `gas_leak` | `燃气泄漏` | `high` | 燃气公司/应急/消防 /《城镇燃气管理条例》27条 | **即时高危**：闻到燃气/煤气异味、管道穿孔喷气/冒泡、液化气瓶泄漏、报警器警报或餐饮场所未装燃气报警切断装置。 |
| `gas_pipe_aging` | `燃气管道老化` | `high` | 燃气公司/住建 /《城镇燃气管理条例》17、36条 | **预防维护态**：尚未出现明显燃气味/喷漏，但管道严重锈蚀、防腐层剥落、穿楼板套管缺失、燃气表前老化软管、管线上方被占压。 |

#### （6）施工安全 `construction`（6 小类，保留原 5 类 + 新增 1 个）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `no_barrier` | `未设置围挡` | `medium` | 住建/城管/市政施工监管 /《建设工程安全生产管理条例》28条 | 工地、市政开挖、拆除或维修边界**缺少连续封闭硬质围挡**，行人/车辆可直接闯入作业区。 |
| `no_warning` | `无安全警示` | `medium` | 交警/市政/住建 /《道路交通安全法》32条 | 占道施工、路面开挖、维修点位**缺乏反光锥桶、警示牌、警戒线、夜间爆闪警示灯**（注：可与 `no_barrier` 并存时按“缺实体屏障优先 `no_barrier`，有简单隔离但缺夜间/远距警示归 `no_warning`”区分）。 |
| `scaffold_guard` | `脚手架/临边防护` | `high` | 住建安监 / JGJ 80 | 建筑脚手架搭设变形、连墙件缺失、未满铺脚手板/安全网、高处作业及楼层/洞口**临边防护栏杆缺失**。 |
| `deep_pit` | `深基坑风险` | `high` | 住建安监 /《危大工程安全管理规定》 | 深基坑边坡支护位移、裂缝、渗水管涌、坑边违规超载堆放建材（如钢筋/土方）。 |
| `temporary_power` | `施工临时用电` | `high` | 住建安监 / JGJ 46 | **仅限施工工地场景**的配电箱无三级配电两级漏保、电焊机/抽水泵线缆破皮拖地、开关箱一闸多机。 |
| **`confined_space`** `[新增]` | `有限空间作业风险` | `high` | 应急管理/市政排水/住建 /《工贸企业有限空间作业安全规定》 | 污水泵站、化粪池、地下管道/管廊、暗渠、储罐等**密闭/地下空间清掏或检修**时，未通风检测、无监护人、无防毒/救援装备冒险下井或疑似硫化氢/沼气中毒。 |

#### （7）电梯与特种设备 `elevator_special`（3 小类）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `elevator_trapped` | `电梯困人` | `high` | 市场监管/电梯维保/消防救援 /《特种设备安全法》 | **明确有人被困在电梯轿厢内**（强制触发困人应急提示，不可与普通停运合并）。 |
| `elevator_stopped` | `停运/异响` | `medium` | 市场监管/物业/维保 / TSG T5002、T7001 | 电梯或自动扶梯停运、卡层、剧烈抖动/异响、平层误差大、扶梯踏板松动或虚假纸面维保；**确认无人被困**。 |
| `elevator_inspection` | `超期未检` | `medium` | 市场监管 /《特种设备安全法》40条 | 电梯/自动扶梯检验合格标志过期、未张贴标志、老旧超 15 年未评估带病运行。**说明：因依赖证件文字且样本稀疏，视觉评测中标记为非外观强依赖类，单独统计不拉偏整盘外观评估。** |

#### （8）环境与其他 `environment_other`（4 小类，新增 1 个、严格纯化 `other`）
| sub_code | 中文名称 | 默认 `risk_level` | 处置主体 / 法规锚点 | 严格隔离边界与优先级规则 |
| --- | --- | --- | --- | --- |
| `garbage_pile` | `垃圾堆积` | `low` | 环卫/城管 /《固体废物污染环境防治法》 | 无主生活垃圾、装修/建筑渣土露天大量堆积、河道/空地偷倒垃圾、露天焚烧废塑料泡沫。**注意：堆在居民楼道/安全出口的归 `fire_lane_blocked`；占道经营有主货物归 `road_occupancy`**。 |
| `sewage_odor` | `污水外溢/恶臭污染` | `medium` | 环保/市政排水/城管 /《环境保护法》42条 | 污水管道破裂外溢、化粪池/餐饮隔油池满溢、工厂偷排酸碱/重金属废液、有毒刺激性废水及伴随明显恶臭/油烟泄漏。**视觉主判据：可见黑臭污水漫溢/污染流/渗漏源；纯清水内涝归 `drainage_flood`**。 |
| **`hazmat_storage`** `[新增]` | `危化品/易燃易爆违规存运` | `high` | 应急管理/公安/消防/生态环保 /《危险化学品安全管理条例》24条 | 公共区域遗弃来源不明化工桶/液罐、废弃厂房/仓库/民宅违规储存危化品/烟花爆竹、物流点无防静电分装易燃溶剂（甲苯、香蕉水等）、黑加油点。**高危风险，不再挂靠 `low`！** |
| `other` | `其他` | `medium` | 综合研判分流 | **纯长尾真隐患兜底**（如二次供水污染、非法拆解含氟利昂冷媒设备、公共空间不明危险遗弃设施）。**严禁用于“图片模糊/看不清”的强制报警**！ |

---

### 3.2 v1（32 类）→ v2（33 类）兼容与合并映射表

以下映射表供 Python `LEGACY_CATEGORY_MAP`、Java `HazardTypeNormalizer.alias()`、前端 `LEGACY_HAZARD_MAP` 及数据库迁移脚本**共享使用**：

| 旧编码 / 旧中文路径 | 处理动作 | 新编码 `major/sub` | 新中文路径 |
| --- | --- | --- | --- |
| `building/wall_crack_lean` / `建筑安全/墙体开裂/倾斜` / `墙体开裂/倾斜` | **合并** | `building/dangerous_building` | `建筑安全/危房/结构开裂倾斜` |
| `building/dangerous_building` / `建筑安全/危房` / `危房` | **更名** | `building/dangerous_building` | `建筑安全/危房/结构开裂倾斜` |
| `building/facade_fall` / `建筑安全/外立面脱落` / `外立面脱落` | **合并** | `building/falling_object` | `建筑安全/高空坠物/外立面脱落` |
| `building/falling_object` / `建筑安全/高空坠物` / `高空坠物` | **更名** | `building/falling_object` | `建筑安全/高空坠物/外立面脱落` |
| `fire/fire_water_abnormal` / `消防安全/消防水源异常` / `消防水源异常` | **合并** | `fire/fire_equipment_fault` | `消防安全/消防设施/水源故障` |
| `fire/fire_equipment_fault` / `消防安全/消防设施故障` / `消防设施故障` | **更名** | `fire/fire_equipment_fault` | `消防安全/消防设施/水源故障` |
| `environment_other/sewage_odor` / `环境与其他/污水/异味` / `污水/异味` | **更名收紧** | `environment_other/sewage_odor` | `环境与其他/污水外溢/恶臭污染` |
| *(新增)* | **新增** | `fire/ebike_hazard` | `消防安全/电动自行车违规停放/充电` |
| *(新增)* | **新增** | `municipal/tree_fall_hazard` | `市政设施/树木倒伏/断枝风险` |
| *(新增)* | **新增** | `construction/confined_space` | `施工安全/有限空间作业风险` |
| *(新增)* | **新增** | `environment_other/hazmat_storage` | `环境与其他/危化品/易燃易爆违规存运` |

---

## 4. 全量 A/B 槽位 Schema 重构（`ai-module/core/slot_schemas.py`）

### 4.1 槽位重构原则
- **彻底废除“12 类全塞进 `其他(describe)`”和“施工/市政盲目复用错误问句”**：每个小类必须命中真正影响**动作/风险等级/处置主体**的槽位。
- **控制追问上界**：每个小类最多不超过 2 个 **A 类（决策级）** 槽，保证多轮对话收敛性不退化；法规/责任/处罚档次差异保留在 **B 类（报告级）**。
- **旧 key 向后兼容注意**：`eval/semantic_grounding/`、`eval/eval_retrieval.py` 和测试中若存在旧 fixture key，在重跑同步更新（详见第 8 节）。

### 4.2 33 小类完整 Slot 定义

> 标注格式：`key (A/B) - question`；**A** 为决策追问槽，**B** 为报告条件分支槽。

| 小类 code | 复用或独立 Schema | 槽位清单（按追问优先级排序） |
| --- | --- | --- |
| `road_occupancy` | 独立（占道经营） | `behavior` (**B**): 具体是摆摊经营还是堆放物品？<br>`persistence` (**A**): 是长期占压还是临时堆放？<br>`blocked` (**A**): 是完全堵死人行道/车道还是部分占用？ |
| `vehicle_occupancy` | 独立（车辆占道） | `persistence` (**A**): 车辆是长期僵尸停放还是临时违停？<br>`blocked` (**A**): 是否完全堵死通行道路或导致人车混行？ |
| `blind_path_occupied` | 独立（盲道占用） | `blocker` (**A**): 盲道是被违停车辆、共享单车还是摊位杂物占用？<br>`blocked` (**A**): 盲道是完全被阻断还是部分被压占？ |
| `traffic_facility_damage` | **新增独立** | `facility_type` (**A**): 具体是信号灯、护栏、交通标志、标线还是减速带损坏？<br>`condition` (**A**): 目前是完全失效/倒伏妨碍通行，还是局部松动/模糊？ |
| `manhole_damage` | 独立（井盖） | `defect` (**A**): 井盖或雨水篦子是完全缺失、移位还是破损松动？<br>`traffic` (**B**): 是否位于机动车道或人行道通行主线上？ |
| `road_surface_collapse` | **新增独立**（不再问井盖） | `collapse_scale` (**A**): 塌陷坑洞大约多大、多深，是否看得到下方空洞？<br>`isolation` (**A**): 现场目前有没有拉警戒线、摆锥桶或封闭通行？ |
| `drainage_flood` | **新增独立**（不再问井盖） | `flood_depth` (**A**): 积水大概有多深，有没有淹到车辆轮胎或阻断行人通行？<br>`location_type` (**B**): 积水是在下穿隧道/涵洞、道路低洼处还是小区地下车库？ |
| `street_light_pole` | **新增独立** | `pole_status` (**A**): 是路灯/线杆倾斜折断、线缆拉断还是仅仅照明不亮？<br>`electric_risk` (**A**): 周边是否有积水或可见裸露线头、漏电风险？ |
| `tree_fall_hazard` | **新增独立** | `tree_state` (**A**): 树木是已经倒伏阻断道路/压线，还是严重倾斜、有大枯枝悬垂？<br>`impact_target` (**B**): 下方或周边是不是人行道、停车位或架空电线？ |
| `fire_lane_blocked` | 独立（扩充室内疏散） | `blocker` (**A**): 通道是被车辆停放、可燃杂物堆放还是门禁/铁门锁闭占用？<br>`persistence` (**A**): 是长期堆占还是临时停放？<br>`impact` (**B**): 是否影响消防车通行或人员紧急疏散？ |
| `fire_equipment_fault` | 独立（融合水源） | `facility_type` (**A**): 具体是哪一类消防设施或水源，例如消火栓/消防管网水压、灭火器、喷淋报警还是防火门？<br>`condition` (**A**): 目前是完全失效/断水无压/被掩埋，还是配件损坏/老旧过期？<br>`function_impact` (**B**): 是否影响整栋建筑或片区的消防报警与灭火功能？ |
| `ebike_hazard` | **新增独立** | `hazard_mode` (**A**): 具体是电动车进楼道/电梯/架空层停放充电，还是电池入户、从楼上飞线充电？<br>`charging_state` (**A**): 现场现在是否正在通电充电、或有发热冒烟/改装电池迹象？ |
| `dangerous_building` | 独立（融合危房与开裂） | `structure` (**A**): 是局部墙体/承重墙开裂，还是已经出现整体倾斜、沉降或违法拆改承重结构？<br>`occupancy` (**A**): 现在是否还有人员在里面居住、经营或办公？ |
| `falling_object` | 独立（融合高空与外立面） | `source` (**A**): 是从哪掉落或松动的（外墙瓷砖/幕墙、广告牌/空调支架、还是人为高空抛物）？<br>`target` (**B**): 下方是人行道、公共出入口还是车行道？<br>`exposure` (**B**): 现场下面有没有搭设防护棚、围挡或警示标志？ |
| `illegal_structure` | **新增独立** | `structure_detail` (**A**): 具体是什么违规搭建（如顶楼铁皮房/阳光房、占压公共走廊或外立面违建）？<br>`structural_impact` (**A**): 搭建或施工过程有没有拆改承重墙、堵塞消防通道或存在大风掀翻风险？ |
| `exposed_wire` | 独立（电线裸露） | `source` (**A**): 是普通线路绝缘破损裸露，还是已经出现漏电、打火或断落？<br>`contact` (**A**): 位置是否较低或涉水，容易被人或车辆接触到？ |
| `distribution_box_fault` | **新增微调** | `condition` (**A**): 配电箱目前是箱门缺失敞开、线路老化，还是已经冒烟、有焦糊味或打火？<br>`contact` (**A**): 配电箱是否在公共通道旁，行人或未成年人能否直接触碰到内部带电体？ |
| `illegal_wiring` | **新增微调** | `wiring_path` (**A**): 电线是从哪里私自接出来的（如公共路灯箱、居民窗台或门面），是否横跨公共通道或搭地？<br>`contact` (**A**): 线皮是否有破损裸露、被踩踏碾压或涉水漏电风险？ |
| `gas_leak` | **新增独立**（不再用 describe） | `leak_sign` (**A**): 是闻到明显燃气味、听到漏气声/看到喷冒，还是仅发现未安装燃气报警切断装置？<br>`ventilation` (**A**): 泄漏发生位置是在密闭室内/地下空间，还是通风较好的室外？ |
| `gas_pipe_aging` | **新增独立**（不再用 describe） | `pipe_condition` (**A**): 管道具体有哪些老化问题（严重锈蚀起皮、套管缺失、软管老化还是管线上方被违章占压）？<br>`leak_suspect` (**A**): 现场附近有没有闻到任何轻微臭味或看到腐蚀穿孔？ |
| `no_barrier` | **独立（围挡缺失）** | `site` (**A**): 施工或开挖边界是否完全没有设置硬质围挡，还是围挡倒伏破损形成缺口？<br>`impact` (**B**): 敞口作业区紧邻人行道、盲道还是机动车道？ |
| `no_warning` | **新增独立**（不再问围挡） | `warning_status` (**A**): 施工或路面异常处是完全没有任何锥桶/标志牌，还是仅缺少夜间反光和警示灯？<br>`impact` (**B**): 所在路段车速较快还是以夜间行人非机动车为主？ |
| `scaffold_guard` | **新增独立**（不再问围挡） | `defect` (**A**): 具体是脚手架整体倾斜/连墙件缺失，还是楼层/洞口临边护栏与安全网缺失？<br>`exposure` (**A**): 目前是否仍有人员在上方高处作业或下方有行人通过？ |
| `deep_pit` | **新增独立**（不再问围挡） | `pit_status` (**A**): 深基坑是否已经出现边坡裂缝、支护位移、渗水或坑边违规重物堆载？<br>`isolation` (**A**): 基坑周边是否有有效防护栏杆和监测警戒隔离？ |
| `temporary_power` | **独立（施工用电）** | `defect` (**A**): 工地用电问题是电缆破损拖地、电箱缺漏保，还是电焊机/抽水设备接零保护缺失？<br>`contact` (**A**): 现场地面是否积水或有作业人员可能直接触电？ |
| `confined_space` | **新增独立** | `space_type` (**A**): 具体是什么密闭/地下空间（化粪池、污水井、地下管廊、泵站还是储罐）？<br>`protection` (**A**): 现场人员作业前是否进行了强制通风、气体检测并配备防毒救援装备？ |
| `elevator_trapped` | **新增独立** | `trapped_state` (**A**): 轿厢内被困几人、是否有人身体不适，以及目前能否通过轿厢通话联系上维保/物业？<br>`duration` (**B**): 人员大约被困了多久，救援人员是否已出发？ |
| `elevator_stopped` | **新增独立** | `fault_symptom` (**A**): 设备具体表现是什么异常（骤停滑梯、剧烈抖动异响、门夹人或扶梯踏板异常）？<br>`occupancy` (**A**): 目前设备是否已停用并设好围挡，确认轿厢内没有人员被困？ |
| `elevator_inspection` | **新增独立** | `equipment_status` (**A**): 是张贴的检验合格标志已超期、完全无标志，还是维保记录涉嫌造假且设备仍在载客运行？<br>`equipment_type` (**B**): 涉及的是住宅客梯、商场扶梯还是货梯/其他电梯？ |
| `garbage_pile` | **新增独立** | `waste_type` (**A**): 堆积的是生活垃圾、建筑渣土还是废泡沫/旧木料等易燃废弃物？<br>`impact` (**A**): 是否紧邻居民楼、高压线、河道或占用道路存在火灾或污染风险？ |
| `sewage_odor` | **新增独立** | `sewage_source` (**A**): 污水或刺激性气味来自市政污水井/化粪池漫溢、餐饮隔油池，还是疑似工业废液偷排？<br>`impact` (**B**): 污水是否已经流入雨水管网、河道或影响周边居民正常生活？ |
| `hazmat_storage` | **新增独立** | `material_info` (**A**): 现场发现的是不明化工桶、易燃溶剂、液化气罐还是烟花爆竹，容器是否密封完好？<br>`environment` (**A**): 存放处是否通风、周边有无居民楼、火源或人员直接接触风险？ |
| `other` | `describe` | `describe` (**A**): 能再具体描述一下现场隐患的对象、异常情况和周围环境吗？ |

---

## 5. `risk_level`、Prompt 与边界护栏联动调整

### 5.1 修正 `risk_level` 一刀切规则（`dialogue_understanding.py`）
当前规则 `"消防、建筑结构、电气燃气为 high；交通、市政、施工、电梯为 medium；环境和其他为 low"` 必须废除，改为基于小类的映射常量 `SUBCATEGORY_DEFAULT_RISK`（建议直接维护在 `core/hazard_taxonomy.py` 中）：
- **`high`**：`fire` 全部 3 类、`building` 的 `dangerous_building` 与 `falling_object`、`utility` 全部 5 类、`municipal/road_surface_collapse`、`construction` 的 `scaffold_guard`/`deep_pit`/`temporary_power`/`confined_space`、`elevator_special/elevator_trapped`、`environment_other/hazmat_storage`。
- **`medium`**：`traffic` 全部 4 类、`municipal` 其余 4 类、`building/illegal_structure`、`construction` 的 `no_barrier`/`no_warning`、`elevator_special` 的 `elevator_stopped`/`elevator_inspection`、`environment_other` 的 `sewage_odor`/`other`。
- **`low`**：仅 `environment_other/garbage_pile`（在未出现易燃/占消防通道前提下）。

### 5.2 修正视觉提示词与防误报规则（`ai-module/prompts.py`）
1. **移除或重改第 92 行的强迫报警规则**（这是视觉评估 53.5% 误报率与 `other` 虚高的主因）：
   - **原规则**：“图片模棱两可、信息不完整或无法确认时，必须设置 `has_hazard` 为 `true`，归入 `environment_other/other`”。
   - **新规则**：**只有图片中存在清晰可见的客观异常证据或危险特征时，才置 `has_hazard: true`**；如果图像模糊、遮挡严重、信息不足以判定隐患事实，或属于正常合规场景，必须置 `has_hazard: false`，并在 `reason_if_no_hazard` 中明确填写 `"图像证据不足，无法确认安全隐患"` 或说明合规情况（`other` 只给确实可见隐患但不属于前 32 类的长尾画面）。
2. **更新 `prompts.py` 易混淆判别要点（按新 33 类重写优先级）**：
   - **占道优先级**：`fire_lane_blocked`（有消防通道/黄网格/室内疏散楼道标识） > `blind_path_occupied`（压占盲道砖） > `vehicle_occupancy`（一般道路违停） / `road_occupancy`（商铺摆摊货物） > `garbage_pile`（无主废弃物）。
   - **电动车与私拉电线**：明显看到电动自行车/锂电池进楼、架空层停放充电、向电动车飞线充电 → `fire/ebike_hazard`（可并发 `illegal_wiring`）；普通非电动车私拉线 → `utility/illegal_wiring`；工地内接电 → `construction/temporary_power`；既有线路破损老化 → `utility/exposed_wire`。
   - **开挖与塌陷**：规整人工开挖、工地特征 → `construction/no_barrier`（缺硬质围挡）或 `construction/no_warning`（有简单隔离但缺警示标志/夜灯）；自然形成、边缘不规则空洞塌陷 → `municipal/road_surface_collapse`。
   - **积水与污水**：清水/雨水内涝阻断交通 → `municipal/drainage_flood`；可见黑臭泥水溢流、工业废液偷排、管道渗污 → `environment_other/sewage_odor`。
   - **树木、灯杆与高空坠物**：树木倾倒/枯枝 → `municipal/tree_fall_hazard`；灯杆/线杆 → `municipal/street_light_pole`；交通信号/限高杆 → `traffic/traffic_facility_damage`；建筑外墙/玻璃/空调支架/广告牌坠落 → `building/falling_object`。

### 5.3 边界护栏与紧急危险词表同步（`scope_policy.py` & `uncertainty.py`）
1. **`scope_policy.py` 的 `OBJECT_CLASS_EVIDENCE`**：
   - 把 `"facade_fall"` 的词表（`外立面`、`外墙`、`墙面`、`墙皮`、`瓷砖`、`幕墙`、`招牌`、`广告牌`、`雨棚`、`楼顶`）保留并评估扩展给 `"falling_object"` 时需谨慎——因 `"falling_object"` 也包含“高空抛物”（`"扔东西"`/`"抛物"`/`"瓶子"`），不能用外立面物件词表误伤高空抛物，建议针对 `falling_object` 至少允许公共外墙词 **或** 抛物词（`"高空"`, `"抛"`, `"扔"`, `"掉"`, `"坠"`, `"楼上"`, `"窗户"`, `"阳台"`）+ 原有公共场所词。
   - 对新增物件/场景词补充至 `DOMAIN_KEYWORDS`（必须先用域外反例检验无误放，**不收光杆单字或泛词**）：
     - `"电动车进楼"`, `"飞线充电"`, `"电动自行车"`（接住 `ebike_hazard`）
     - `"危化品"`, `"危险化学品"`, `"烟花爆竹"`, `"甲苯"`, `"易燃易爆"`（接住 `hazmat_storage`）
     - `"树木倒伏"`, `"行道树"`, `"树枝断"`（接住 `tree_fall_hazard`）
     - `"有限空间"`, `"化粪池"`, `"硫化氢"`（接住 `confined_space`）
   - 在 `PUBLIC_SPACE_WORDS` 中核对 `"公园"`, `"河道"`, `"绿化带"`（`公园` 已在列表中，确保临水/河道/绿化带树木倒伏不会被 `unbacked_hazard_claim` 误伤）。
2. **`uncertainty.py` 的 `DANGER_TERMS` 与 `scope_policy.py` 的 `EMERGENCY_GUIDANCE_TYPES`**：
   - 在 `DANGER_TERMS` 增补 `"硫化氢"`, `"中毒"`, `"晕厥"`, `"危险化学品泄漏"`, `"易燃溶剂"`, `"闪燃"`，确保有限空间中毒与危化品泄漏在第一轮就能直接走急救避险指引。

---

## 6. 全栈代码改造清单（Checklist）

执行模型需按以下清单逐文件检查修改，**禁止遗漏任意一端导致校验拒绝或构建报错**：

### 6.1 Python 后端（`ai-module/`）
- [ ] `ai-module/core/hazard_taxonomy.py`：
  - 更新 `HAZARD_TAXONOMY` 为 8 大类 33 小类；
  - 新增 `SUBCATEGORY_DEFAULT_RISK` 映射；
  - 在 `LEGACY_CATEGORY_MAP` 增补所有 v1 旧编码与旧中文路径映射（如 `"building/wall_crack_lean": ("building", "dangerous_building")` 等），确保 `normalize_taxonomy()` 对新旧字符串 100% 幂等归一。
- [ ] `ai-module/core/slot_schemas.py`：
  - 按第 4 节重构 `SLOT_SCHEMAS` 与 `SUBCATEGORY_SLOT_SCHEMAS`，覆盖全部 33 个小类；
  - 核对每个小类的 A 类槽数量 `<= 2`。
- [ ] `ai-module/prompts.py`：
  - 同步 `VISION_PROMPT` 的 33 个小类枚举、排他判别要点；
  - 修改第 92 行模糊图强制报 `other` 规则，消除无依据误报。
- [ ] `ai-module/core/dialogue_understanding.py`：
  - 更新 `_planner_system_prompt` 中的 `risk_level` 规则描述，取消“环境与其他一律 `low`”；
  - 核对设施类公共空间判据（确保树木、公园/市政公共设施不被误拦）。
- [ ] `ai-module/core/scope_policy.py` & `ai-module/core/uncertainty.py`：
  - 更新 `OBJECT_CLASS_EVIDENCE`（`facade_fall` 迁移处理）、`DOMAIN_KEYWORDS` 及高危词表；
  - 确认现有域外负样本测试无退化。
- [ ] `ai-module/tools/hazard_submit.py`：
  - 检查注释与依赖 `HAZARD_TAXONOMY` 的提示词生成逻辑（确认自动加载 33 类且无旧编码硬编码）。
- [ ] `ai-module/skills/{municipal,fire,building,construction,environment_other}/SKILL.md`：
  - 同步更新 `description`、`routing_keywords`、`适用范围` 与 `追问 SOP`（如 `fire/SKILL.md` 增加 `ebike_hazard`、删除 `fire_water_abnormal` 等）。

### 6.2 Java 后端（`safety-service/`）
- [ ] `safety-service/src/main/java/com/safety/service/service/support/HazardTypeNormalizer.java`：
  - 同步更新 `static {}` 块中的 `add(...)` 为 8 大类 33 小类最新中文路径；
  - 使用 `alias(...)` 将第 3.2 节表内**全部旧英文码、旧中文路径、旧中文小类名**（如 `"building/wall_crack_lean"`, `"建筑安全/墙体开裂/倾斜"`, `"墙体开裂/倾斜"`, `"building/dangerous_building"`, `"建筑安全/危房"`, `"危房"`, `"building/facade_fall"`, `"建筑安全/外立面脱落"`, `"外立面脱落"`, `"fire/fire_water_abnormal"`, `"消防安全/消防水源异常"`, `"消防水源异常"`, `"消防安全/消防设施故障"`, `"消防设施故障"`, `"环境与其他/污水/异味"`, `"污水/异味"`）全部映射到新的标准中文路径！
  - 验证：旧历史请求和未升级前端缓存传入旧标签时不报 `400 隐患类别不合法`。

### 6.3 前端（`.frontend-work/` 及实际同步目录）
- [ ] `.frontend-work/src/constants/hazardTaxonomy.js`：
  - 更新 `HAZARD_TAXONOMY` 为 8 大类 33 小类；
  - 在 `LEGACY_HAZARD_MAP` 增补 v1 旧路径/旧 code 兼容映射（保证旧工单列表和详情页 `resolveHazard` / `resolveHazardList` 正确渲染大类与小类标签）；
  - 确认 `resolveHazard` 步骤 1（精确中文路径 `subcategoryPathMap`）在步骤 2（`/` 切割英文码）之前执行，防止含 `/` 的中文新名称（如 `危房/结构开裂倾斜`）被误切。
- [ ] 检查前端构建/同步流程（如 `.frontend-sync-dist/` 等部署目录），确保静态资源与源码一致。

---

## 7. 存量数据库、种子脚本与向量检索（RAG）迁移方案

### 7.1 幂等 MySQL 迁移脚本（新增 `ai-module/db/schema/migrate_taxonomy_v2.py`）
参考 `ai-module/db/schema/migrate_hazard_types_only.py` 的安全范式（支持 `--dry-run` / `--execute`，执行前必须整表备份）：
1. **迁移 `tb_hazard.hazard_types`**（注意该列支持逗号分隔最多 3 个中文路径）：
   - 逐条拆分逗号分隔值 → 映射替换旧路径为新路径 → **按顺序去重**（关键边界：若老工单同时存着 `"建筑安全/危房,建筑安全/墙体开裂/倾斜"`，合并映射后必须去重为 `"建筑安全/危房/结构开裂倾斜"`）→ 校验所有条目均属于新 33 类白名单 → 回写 `tb_hazard.hazard_types`。
2. **迁移检索语料表 `tb_hazard_case.category`、`tb_regulation.category`、`tb_hazard_knowledge.category`**：
   - 将旧中文路径按第 3.2 节表更新；
   - **同时执行针对性的错标清洗（数据归正）**：
     - 原在 `环境与其他/其他` 的危化品/易燃易爆案例与《危险化学品安全管理条例》→ 改标为 `环境与其他/危化品/易燃易爆违规存运`；
     - 原在 `环境与其他/其他` 的有限空间中毒案例与《工贸企业有限空间作业安全规定》→ 改标为 `施工安全/有限空间作业风险`；
     - 原在 `电气与燃气/私拉乱接` 或 `消防安全/消防通道占用` 的电动车进楼/架空层/锂电池新国标（《国办发〔2024〕19号》《GB 43854-2024》、南京雨花台案、北京通州锂电池案）→ 主类改标为 `消防安全/电动自行车违规停放/充电`；
     - 原在 `交通与通行/车辆占道` 中明确属于堵塞消防车/急救通道的案例（如北京海淀堵消防通道拘留案、湖南新邵占用消防车通道案）→ 改标为 `消防安全/消防通道占用`；
     - 原在 `环境与其他/垃圾堆积` 中属于住宅天台/楼道堆放可燃杂物的案例（如昆明小区天台堆旧木家具案）→ 改标为 `消防安全/消防通道占用`；
     - 原在 `建筑安全/违规搭建` 中实际核心为拆改承重结构/违规加层致坍塌或开裂的案例，按主因与 `dangerous_building` 核对对齐。

### 7.2 同步种子文件与重建向量索引
- [ ] 同步修改 `ai-module/db/seed/` 下的数据源脚本（`data_cases.py`、`data_cases_batch2.py`、`data_cases_batch3.py`、`data_regulations.py`、`data_regulations_batch2.py`、`data_regulations_batch2026.py`、`import_all_new_data.py`、`enrich_full_taxonomy.py`），确保重新建库与线上迁移结果完全同源。
- [ ] **新增类别种子补全**：为新增的 `municipal/tree_fall_hazard` 至少补充 2~3 条真实权威案例与 2 条对应法规（如《城市绿化条例》）；为 `fire/ebike_hazard`、`environment_other/hazmat_storage`、`construction/confined_space` 核对案例与法规数量（每小类至少保证 `>= 2` 条案例 + `>= 2` 条法规，保证 RAG `Recall@5` 不出现新类空白）。
- [ ] **同步刷新向量索引**：执行 `ai-module/db/seed/rebuild_case_embeddings.py` 更新本地 `case_embeddings.json`，并同步刷新云主机 Milvus 中 `tb_hazard_case`、`tb_regulation`、`tb_hazard_knowledge` 向量集合。

---

## 8. 评估集重建与回归测试方案

重构完成后，**不得将新旧两套分类的绝对分数直接混淆对比**，需按以下流程重建并重新测出 v2 基线：

### 8.1 单元测试与契约测试更新
需同步修正硬编码断言的测试文件：
- Python（`ai-module/tests/`）：
  - `test_hazard_taxonomy.py`（检查 33 小类、新旧兼容解析、长度 `<= HAZARD_TYPE_MAX_LENGTH`）
  - `test_hazard_lock.py`、`test_multi_hazard_followup.py`、`test_semantic_dialogue.py`、`test_echo_slots.py`、`test_hazard_submit_payload.py`（将测试样例中写死的 `wall_crack_lean`、`facade_fall`、`fire_water_abnormal` 替换为新编码，并补充新类的锁定与追问用例）
  - `test_scope_policy.py`（将 `facade_fall` 物件校验测试用例更新为 `falling_object`，并增加新类的正向放行与域外防误放测试）
  - `test_slot_value_classes.py` / `test_adaptive_slots.py`（验证新补齐槽位的 A/B 类分级及“无 `describe` 错配”）
  - 验证全部测试集：`python -m pytest -q`
- Java（`safety-service/`）：
  - `HazardTypeNormalizerTest.java`（第 61 行从断言 `32` 改为 `33`，同时增加“旧标签 `wall_crack_lean`/`facade_fall`/`fire_water_abnormal` 仍能成功归一化为新路径”的回归测试）
  - 验证编译与测试：`mvn test`
- 前端（`.frontend-work/`）：
  - 若存在 `hazardTaxonomy` 相关单测（检查 `.frontend-work/test/`），补充新 33 类与旧路径兼容测试并跑 `npm test`。

### 8.2 文本分类与检索评测重建（`ai-module/eval/`）
1. **重做 `eval/eval_queries.py`**：
   - 将 `QUERY_SET` 扩展为 **`33 × 2 = 66` 条**（每类 `explicit` + `colloquial`）。
   - 将原 `environment_other/other` 的“危化品桶”查询正式归入 `environment_other/hazmat_storage`，并为 `other` 编写**真正长尾、无前 32 类归属**的新查询（如公共游乐/健身器材尖锐破损、废弃冷媒违规拆解等）。
   - 核查 `sewage_odor` 查询词必须体现“污水污染/恶臭偷排”，避免与纯雨水积涝 `drainage_flood` 含混不清。
2. **重做 `eval/eval_retrieval.py`**：
   - 更新 `SLOT_VALUES` 与 `SLOT_FIXTURE_KEYS` 为新 33 类与真实 schema 首个 key，统一口径后在云主机重新执行 `eval_retrieval.py` 与 `eval_classify.py`，产出 **v2 新基线报告**（保留旧 32 类基线仅作历史存档说明，不跨口径硬比）。
3. **检查 `eval/semantic_grounding/validate_dataset.py`**：
   - 使用新类别与新槽位 key 重新校验标注数据集合法性。

### 8.3 视觉评估集重做与统一（`ai-module/eval/vision/`）
这是最能直观体现分类分离隔离收益的环节，严格遵循以下改造：
1. **废除私有 25 类双轨制**：
   - 弃用 `eval/vision/_taxonomy_final.json` 和 `final_eval_v2.py` 中的 `MERGE` 硬编码映射；直接从生产 `core/hazard_taxonomy.py` 动态读取或导出对齐后的 `_taxonomy_v2.json`。
2. **对已有 `test_set`（378 张）与 `images_merged`（1,447 张）进行分层清洗与重标**：
   - **合并项无损继承**：原标为 `wall_crack_lean` → 改为 `dangerous_building`；`facade_fall` → 改为 `falling_object`；`fire_water_abnormal` → 改为 `fire_equipment_fault`；`sewage_overflow` → 还原编码为 `sewage_odor`（定义保持清晰“可见污水漫溢”）。
   - **必须重新人工/双模型仲裁拆分的类别**（因为之前被视觉测试错误揉在一起）：
     - 原 `wire_fault` 下的图片：按“明显私接路径/飞线”拆回 `illegal_wiring`（如果是给电动车充电则拆到 `ebike_hazard`），“工地场景电线/配电箱”拆回 `temporary_power`，“其余老化破损电线”归 `exposed_wire`。
     - 原 `construction_prot`/`pit_protection` 下的图片：按“缺边界连续硬围挡 (`no_barrier`) / 缺警示牌反光灯 (`no_warning`) / 明显基坑边坡滑移渗水 (`deep_pit`)”重新核对边界并清洗标注。
   - **新增 4 类补齐**：利用 `harvest.py` + `triage.py` + 人工/双模型核验，为 `ebike_hazard`、`tree_fall_hazard`、`hazmat_storage`（以及视视觉图可获取性决定 `confined_space`）各补充 `>= 15~20` 张真实独立测试图入 `test_set_v2`，避免重演 `REPORT_FINAL.md` 中“17 个类样本不足 10 张导致指标无统计意义”的尴尬。
   - **移除被误当成正常模糊图桶的 `other` 污染样本**：确保新 `test_set_v2` 的负样本（200 张正常图）中，配合 `prompts.py` 去掉“模糊就报 `other`”规则重跑推理，单独记录新版的 **Recall / 严格准确率 / FPR（误报率） / Critical Miss Rate**。
3. **分层报告规范（保证统计严谨）**：
   - 在新评估报告中必须拆成两个口径展示：
     - **口径 A（可视觉判别核心集）**：覆盖有明确物理外观特征的类别；
     - **口径 B（文字证件/不可见气味/极低样本类）**：如 `elevator_inspection`（证件文字）、`gas_leak`（无泄漏外观图）、`confined_space`（通风检测流程合规性），单列样本数并注明“需结合文本/多轮对话判定，不混入纯视觉主表误导模型评价”。

---

## 9. 推荐实施顺序与验收门槛

建议另一个模型严格按以下 **5 个阶段** 顺序提交变更（每阶段通过测试后再进下一阶段）：

1. **Phase 1（契约与代码层同源切换）**：修改 `hazard_taxonomy.py`、`slot_schemas.py`、`HazardTypeNormalizer.java`、`hazardTaxonomy.js`、各测试集 → 跑通全量 Python pytest + Java Maven test + 前端构建。
2. **Phase 2（Prompt、Skill 与护栏对齐）**：修改 `prompts.py`、`dialogue_understanding.py`、`scope_policy.py`、`uncertainty.py`、`skills/*/SKILL.md` → 跑通边界词表防误放实验与端到端对话单测。
3. **Phase 3（数据与向量库归正）**：更新种子文件、补充新类真实案例与法规、运行 `migrate_taxonomy_v2.py --dry-run` 核对后 `--execute` 迁移、重算 embeddings 与同步 Milvus。
4. **Phase 4（文本与检索评估重建）**：更新 `eval_queries.py` 与 `eval_retrieval.py`，重新测算分类准确率与检索 `Hit@5` / `MRR` / `EmptyRate`（预期目标：消除 Top-1 混淆后 `eval_classify` 小类整体准确率应较旧版 `0.917` 明显提升，`other` 错判显著下降）。
5. **Phase 5（视觉评估集重建与重测）**：废弃 `eval/vision` 私有 25 类合并补丁，按 Taxonomy v2 清洗重标 `test_set_v2` 并补采新类样本，清缓存重跑推理，对比重测后的**严格准确率**、**FPR**（重点验证去掉“模糊报 `other`”后的大幅下降）与 **Critical Miss Rate**（严守高危漏报不恶化门槛）。
