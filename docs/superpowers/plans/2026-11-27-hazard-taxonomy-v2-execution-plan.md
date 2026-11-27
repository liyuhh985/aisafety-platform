# 城市安全隐患两级分类体系（Taxonomy v2）三阶段执行计划

> 状态：Phase 1 已完成并验收；Phase 2/3 尚未执行
> 日期：2026-11-27
> 上游设计参考：`docs/superpowers/specs/2026-11-27-hazard-taxonomy-v2-isolation-design.md`
> 硬隔离边界：本计划**绝不碰任何 `rerank` 改造或评估归因**（`docs/superpowers/plans/2026-11-27-rerank-experiment.md` 中的 `ReadTimeout`、`P95` 与 `fallback=1` 属于独立问题，禁止混入同一次变更或报告）。

---

## 0. 代码实证约束（执行模型必须遵守，禁止自行发挥）

以下结论均已核查仓库当前源码，是本计划的前置硬约束：

1. **Milvus 不存 `category`，但“无需重建”是有条件的**：
   - `ai-module/tools/milvus_store.py`（L100–151）禁用动态字段，集合只有 `doc_id (INT64)`、`content_hash (VARCHAR(64))`、`embedding (FLOAT_VECTOR)` 三列。
   - `ai-module/tools/knowledge_sync.py`（L21–40）与 `ai-module/db/seed/rebuild_case_embeddings.py`（L31）的向量化查询**不包含 `category`**，召回 `doc_id` 后再回查 MySQL 取 `category`。
   - **条件结论**：
     - **仅当**（a）上述 Milvus schema 与 `knowledge_sync.py` 的 `SELECT` 不含 `category`、（b）Phase 1 只修改已有行的 `category` 而**不新增案例、不改动任何 `title/description/cause/rectification/law_name/article/content/keywords`** 时 → **Phase 1 不需要重建 Milvus 或重算存量向量**。
     - **一旦**新增案例/法规或改动正文（如 Phase 2）→ **必须运行 `python tools/knowledge_sync.py` 增量同步到 Milvus，并运行 `python db/seed/rebuild_case_embeddings.py` 更新降级缓存**。
2. **Redis 不能硬编码前缀、也不能 `FLUSHDB`**：
   - 认证白名单 `safety:token:*`、`safety:token:user:*`、`safety:token:version:*` 与限流/验证码 `safety:limit:*`、`safety:email_code:*` 均在同一 Redis 实例（见 `safety-common/.../RedisConstant.java`）。虽然当前无真实线上用户可允许重新登录，但清理脚本仍必须遵守精确作用域：
   - **动态读取配置**：从 `ai-module/config.py` 读取运行时 `SESSION_REDIS_PREFIX`（默认 `ai:sess:`）和 `CHECKPOINT_BACKEND`；合并固定键模板 `ai:hist:*`（`core/memory.py`）、Java 隐患详情/列表缓存 `safety:hazard:*` / `safety:hazard:list:*`；若启用了 `CHECKPOINT_BACKEND=redis`，先通过 `RedisSaver` / `SCAN` 核实实际 checkpoint key 前缀再扫描。
   - **强制先 `--dry-run`**：先使用 `SCAN` 统计各前缀待删 key 数量并打印样本，**显式校验待删集对 `safety:token:`、`safety:email_code:`、`safety:limit:` 的命中数必须为 `0`**，确认无误后再 `--execute` 删除。重启 Python 与 Java 服务以清空进程内 `InMemorySaver` 与 Caffeine `localCache`。
3. **前端 `.frontend-work` 被忽略且无 `index.html`，禁止把 `npm run build` 当通过门槛**：
   - 核对 `.gitignore`（L119）与 `docs/current/patches/README.md`：`.frontend-work/` 已被 `.gitignore` 忽略，且 `.frontend-work` 目录内只有 `src/`、`test/`、`package.json`、`package-lock.json`、`node_modules/`，**没有 `index.html`**，直接执行 `npm run build` 会失败，该失败与本次改造无关。
   - **正确前端交付与验证流**：
     1. 修改 `.frontend-work/src/constants/hazardTaxonomy.js`（以及必要的视图代码）；
     2. 编写/更新 `.frontend-work/test/hazardTaxonomy.test.mjs` 并运行 Node 测试；同时用 `.frontend-work/node_modules/@vue/compiler-sfc` 脚本批量校验所有依赖 `hazardTaxonomy.js` 的 `.vue` 文件（SFC parse + `<script>` + `<template>` 编译通过）；
     3. 生成标准 unified diff 补丁写入 `docs/superpowers/patches/2026-11-27-hazard-taxonomy-v2a-frontend.patch`（Phase 2 同理），并在 `docs/current/patches/` 补充文档索引；
     4. 确认补丁与文档均在 `git status` 可追踪范围内，绝不允许只修改被忽略的 `.frontend-work/` 工作副本。
4. **硬切换拒绝旧类别（不保留静默 alias）**：
   - 决定做硬切换，**不在写路径为已废除的 3 个旧小类保留静默向下映射**：
     - 被废除旧值：`building/wall_crack_lean`、`建筑安全/墙体开裂/倾斜`、`墙体开裂/倾斜`、`building/facade_fall`、`建筑安全/外立面脱落`、`外立面脱落`、`fire/fire_water_abnormal`、`消防安全/消防水源异常`、`消防水源异常`。
   - **旧客户端写请求明确行为**：上述旧路径进入 Java `HazardTypeNormalizer` 或 Python 建单校验（`tools/hazard_submit.py`）时，**直接拒绝并返回 `400`（Java 抛出 `BusinessException(400, "隐患类别已升级，请刷新页面")`；Python 返回不可识别/拒收，不静默映射、不落库）**；必须编写对应单元测试锁死该行为，防止后续误加回长期兼容映射。
   - 注：原有与本次 3 个小类无关的旧粗粒度标签单测（如 `HazardTypeNormalizerTest` 里的 `"占道"`/`"井盖/道路"` 拒绝测试、以及既有 `"消防通道"`/`"消防设施"` 兼容）按原有测试边界保持清晰，不与已退役 3 小类混淆。

---

## Phase 1（`v2a`）：3 组冗余合并与全栈原子切换（32 → 29 类）

**范围边界**：只合并 3 组强冗余小类，**保持目标中文名称（`危房`、`高空坠物`、`消防设施故障`）与 `dangerous_building`、`falling_object` 原槽位 key 不变**，不新增小类，不重构无关小类槽位。

### 1.1 合并清单（唯一真值）
| 已废除旧 `major/sub` | 已废除旧中文路径 | 迁移目标 `major/sub` | 迁移目标中文路径（保持不变） |
| --- | --- | --- | --- |
| `building/wall_crack_lean` | `建筑安全/墙体开裂/倾斜` | `building/dangerous_building` | `建筑安全/危房` |
| `building/facade_fall` | `建筑安全/外立面脱落` | `building/falling_object` | `建筑安全/高空坠物` |
| `fire/fire_water_abnormal` | `消防安全/消防水源异常` | `fire/fire_equipment_fault` | `消防安全/消防设施故障` |

### 1.2 精确执行顺序（10 步，严禁乱序）

#### Step 1：编写迁移脚本并先做 Schema 发现 + `--dry-run`
新增脚本 `ai-module/db/schema/migrate_taxonomy_v2a.py` 与精确清缓存脚本 `ai-module/db/schema/cleanup_redis_v2.py`：
1. **实际 Schema 发现（强制第一步）**：
   执行 SQL 扫描当前库全部潜在分类列：
   ```sql
   SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
   FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND (COLUMN_NAME LIKE '%hazard%' OR COLUMN_NAME LIKE '%category%' OR COLUMN_NAME LIKE '%type%')
   ORDER BY TABLE_NAME, ORDINAL_POSITION;
   ```
   - 核对主读写目标 4 列：`tb_hazard.hazard_types`、`tb_hazard_case.category`、`tb_regulation.category`、`tb_hazard_knowledge.category`。
   - 明确登记非目标表与不迁理由（由脚本校验并打印）：
     - `tb_hazard_report.hazard_category`：经确认仅存储视觉大类中文名（如 `市政设施`、`建筑安全`）；脚本仍扫一遍确认其中不含本次废除的 3 个旧小类路径（若意外存在则纳入中止告警或显式清洗）。
     - `ai_historical_analysis.hazard_category`：用户级历史分析记忆表（`core/memory.py` 仍在读写），执行期实查为 0 行；登记为“不迁移但强制校验”表，脚本断言不含 3 个退役路径。
     - `tb_hazard_knowledge.category`：执行期实查值为知识文档类型枚举 `POLICY/BUILDING/FACILITY/FIRE/TRAFFIC`，**不是隐患 taxonomy**；登记为备份 + 只读审计表，不改写，脚本断言枚举合法且不含 3 个退役路径。
     - `ai_hazard_create_request_archive` / `ai_hazard_create_outbox_archive` / 既有 `*_bak_*` 表：历史只读归档/备份表，不属于线上业务读路径，故不迁移。
     - **若发现任何上述清单外的新增业务表带有分类列**：脚本立即报错退出（**Stop Gate**），先人工确认再继续。
2. **执行 `migrate_taxonomy_v2a.py --dry-run`**：
   - 打印 3 张 taxonomy 主表中待替换旧值的精确行数（`tb_hazard_knowledge` 只做备份与枚举审计）；
   - 检查 `tb_hazard.hazard_types` 中包含逗号多值且映射后会产生重复的记录数（如 `"建筑安全/危房,建筑安全/墙体开裂/倾斜"`），确认保序去重逻辑输出；
   - 执行 `cleanup_redis_v2.py --dry-run`，确认动态读取的 `SESSION_REDIS_PREFIX`、`ai:hist:*`、`safety:hazard:*`、`safety:hazard:list:*`（及启用 RedisSaver 时的 `checkpoint*`）扫描数量，并断言 `safety:token:`、`safety:email_code:`、`safety:limit:` 命中为 `0`。

#### Step 2：停写与 MQ 在途闸门（包含 `PUBLISHING` 与 `PUBLISHED`）
关闭对外写入入口（或置维护状态），停止向 `ai_hazard_create_request` / `ai_hazard_create_outbox` 与 `tb_hazard` 写入新单，然后执行在途检查：
```sql
SELECT status, COUNT(*) AS cnt
FROM ai_hazard_create_outbox
WHERE status IN ('PENDING', 'PUBLISHING', 'RETRY')
GROUP BY status;

SELECT status, COUNT(*) AS cnt
FROM ai_hazard_create_request
WHERE status IN ('PENDING', 'PUBLISHED')
GROUP BY status;
```
- **Stop Gate 1**：上述两条 SQL **任一返回非 0 计数**（注：`OB_PUBLISHING` 是 Relay 已认领尚未确认完成的在途态；`REQ_PUBLISHED` 对 request 不是终态，终态只有 `SUCCESS`/`FAILED`），**严禁继续切换**，必须等待消费者排空或人工排查处理完后再重查。

#### Step 3：停止旧版 Python AI 与 Java 后端进程
确保无运行中 worker 继续持有旧连接或写旧分类。

#### Step 4：MySQL 备份 4 张主表
脚本内事务外先生成快照表（`tb_hazard_bak_v2a_<ts>`、`tb_hazard_case_bak_v2a_<ts>`、`tb_regulation_bak_v2a_<ts>`、`tb_hazard_knowledge_bak_v2a_<ts>`），逐表对比 `COUNT(*)` 完全相等；**任一不等立即中止**。

#### Step 5：执行 MySQL 迁移与保序去重（`migrate_taxonomy_v2a.py --execute`）
在单个事务内执行：
- 更新 `tb_hazard_case.category`、`tb_regulation.category` 中的 3 个旧中文路径为新目标路径；`tb_hazard_knowledge.category` 保持文档类型枚举不变；
- 逐行处理 `tb_hazard.hazard_types`：按 `,` 拆分 → 替换 3 个旧路径 → **按原序去重**（防止 `"建筑安全/危房,建筑安全/墙体开裂/倾斜"` 变成重复串）→ 校验 `1 <= len <= 3` 且全部属于 29 类合法白名单；
- 全表扫描：3 张 taxonomy 表按 29 类白名单校验；`tb_hazard_report`、`ai_historical_analysis` 断言无退役路径；`tb_hazard_knowledge` 断言文档类型枚举合法且无退役路径。全部通过后 `COMMIT`（**任何一行不合法立即 `ROLLBACK` 并中止**）。

#### Step 6：执行 Redis 精确清键（`cleanup_redis_v2.py --execute`）
按 `--dry-run` 已核验的前缀删除：
- 运行时 `SESSION_REDIS_PREFIX + "*"`
- `"ai:hist:*"`
- `"safety:hazard:*"`（含 `"safety:hazard:list:*"`）
- 若 `CHECKPOINT_BACKEND=redis`：清理经核实的 `RedisSaver` checkpoint 键前缀。

#### Step 7：全栈代码修改与前端补丁生成
1. **Python（`ai-module/`）**：
   - `core/hazard_taxonomy.py`：移除 `wall_crack_lean`、`facade_fall`、`fire_water_abnormal`，使 `ALL_SUBCATEGORY_CODES` 为 29 个；**禁止**将这 3 个已废除 code/中文路径加入 `LEGACY_CATEGORY_MAP`。
   - `core/slot_schemas.py`：移除上述 3 个旧 key；**保留 `dangerous_building`（`structure` A、`occupancy` A）、`falling_object`（`source` A、`target` B、`exposure` B）、`fire_equipment_fault`（`facility_type` A、`condition` A、`function_impact` B）既有槽位 key 不变**，仅扩充问句文本以明确涵盖墙体开裂/倾斜、外立面脱落、消防水源/水压异常。
   - `core/scope_policy.py`：将原 `OBJECT_CLASS_EVIDENCE["facade_fall"]` 与高空抛物依据合并为 `falling_object` 核对规则（同时覆盖外立面词表与高空抛物触发词，防止误拦正常抛物上报也防止漏拦室内指示牌）。
   - `prompts.py`：移除 3 个旧小类枚举和第 4/5 条易混淆对比要点，在目标类描述中显式展开原 3 类场景。
   - `skills/building/SKILL.md`、`skills/fire/SKILL.md`：更新适用范围、关键词与 SOP，去除 3 个已合并 code。
   - `tools/hazard_submit.py`：更新注释为 29 小类；确认提交已废除的 3 个旧分类时 `_normalize_category_list` 返回空并触发拒绝响应（不静默映射到目标类）。
2. **Java（`safety-service/`）**：
   - `HazardTypeNormalizer.java`：移除 3 个旧小类 `add(...)`，使 `canonicalTypes().size() == 29`；
   - 对已知的 9 个退役旧标识（`"building/wall_crack_lean"`, `"建筑安全/墙体开裂/倾斜"`, `"墙体开裂/倾斜"`, `"building/facade_fall"`, `"建筑安全/外立面脱落"`, `"外立面脱落"`, `"fire/fire_water_abnormal"`, `"消防安全/消防水源异常"`, `"消防水源异常"`）显式抛出 **`BusinessException(400, "隐患类别已升级，请刷新页面")`**（不静默映射）。
3. **前端源码与可追踪 Patch（`.frontend-work/` + `docs/`）**：
   - 修改 `.frontend-work/src/constants/hazardTaxonomy.js`：从 `HAZARD_TAXONOMY` 移除上述 3 项，更新注释，不在 `LEGACY_HAZARD_MAP` 中为退役 3 类加写路径伪装；
   - 在 `.frontend-work/test/hazardTaxonomy.test.mjs` 新增测试，并使用 `@vue/compiler-sfc` 编译检查引用 `hazardTaxonomy.js` 的所有 `.vue` 文件；
   - 生成补丁 `docs/superpowers/patches/2026-11-27-hazard-taxonomy-v2a-frontend.patch`，并更新 `docs/current/patches/README.md` 与 `docs/current/patches/taxonomy-v2a-frontend-patch.md`。
4. **同步种子文件**：
   - 更新 `ai-module/db/seed/data_cases*.py`、`data_regulations*.py` 中的 3 类旧路径，保持种子与线上迁移后数据库一致。

#### Step 8：单测回归与 29 类评估集重构（`v2a` 版本独立存档）
1. **单测同步与运行**：
   - 更新 `HazardTypeNormalizerTest.java`（断言 `29` 个规范路径，并新增“提交 3 个退役旧小类均返回 400 且报错包含 `隐患类别已升级，请刷新页面`”的测试）；
   - 更新 Python 单测 `test_hazard_taxonomy.py`（新增断言 `normalize_taxonomy` 拒绝退役 3 类）、`test_hazard_lock.py`、`test_multi_hazard_followup.py`、`test_semantic_dialogue.py`、`test_echo_slots.py`、`test_hazard_submit_payload.py`、`test_scope_policy.py`、`test_eval_classify.py`；
   - 执行全量验证：
     - `mvn test`（Java 全过）
     - `cd ai-module && python -m pytest -q`（Python 全过）
     - `.frontend-work` Node 测试 + `@vue/compiler-sfc` 编译全过
   - **Stop Gate 2**：任一单测或编译校验失败，禁止启动新版本服务。
2. **29 类 `v2a` 评估重建**（不修改旧 32 类基线文件，产出新版本基线）：
   - 更新 `eval/eval_queries.py` 为 29 × 2 = 58 条（将原 3 类查询并入目标类并人工核查无同义重复）；
   - 更新 `eval/eval_retrieval.py` 的 `SLOT_VALUES` 与 `SLOT_FIXTURE_KEYS` 为 29 类；
   - 在 `eval/vision/` 弃用 `_taxonomy_final.json` 私有 25 类码，产出仅合并上述 3 组的 `v2a` 测试标注集。

#### Step 9：核查前端补丁已入库追踪，再启动新版服务与迁移后抽样
1. 确认 `git status` 显示前端 `.patch` 文件与 `docs/current/patches/` 文档已进入版本控制（不只改了 `.gitignore` 里的 `.frontend-work/`）；
2. 启动新版 Java 后端与 Python AI 服务，检查 `/api/ai/health` 与 `/actuator/health`；
3. **迁移后双项在线验证**：
   - **Milvus → MySQL 条件验证**：先核查 `milvus_store.py` 无 `category`、`knowledge_sync.py` SQL 不选 `category`；再运行只读抽样脚本随机选取 10 条检索查询（至少包含 3 条来自原被合并类目的案例），验证 Milvus 召回 `doc_id` 后通过 `HybridSearcher._get_rows_by_ids` 从 MySQL 读取出的 `category` 全部为最新 29 类规范路径，无旧值残留；
   - **旧客户端 400 冒烟验证**：用 `curl` 或测试向 Java 创建/校验接口发送 `"建筑安全/墙体开裂/倾斜"`，确认返回 HTTP/业务码 `400` 及 `"隐患类别已升级，请刷新页面"`。

#### Step 10：运行并锁定 `v2a` 基线评估
运行 `eval/eval_classify.py`、`eval/eval_retrieval.py` 与 `v2a` 视觉评估，分别保存为独立版本输出（如 `eval_classify_v2a.txt`、`eval_retrieval_v2a.txt`、`vision_eval_v2a.md`），不覆盖旧 32 类产物。


### 1.3 Phase 1 执行结果（2026-11-27）

- Step 1 Schema 发现 + MySQL/Redis dry-run：通过。
  - 实库补录 `ai_historical_analysis.hazard_category` 为“不迁移但强制校验”；
  - 实库确认 `tb_hazard_knowledge.category` 为知识文档类型枚举，只备份/审计，不按 29 类 taxonomy 改写。
- Step 2 MQ 在途闸门：outbox/request 两组在途计数均为 0。
- Step 3 旧服务停止：Python 8000、Java 8080、MQ worker 均已停止。
- Step 4 四表备份：stamp `20261127_163713`，行数 34/231/139/30 全部一致。
- Step 5 事务迁移：`tb_hazard` 4 行、案例 18 行、法规 9 行完成替换；404 行 taxonomy 全表复审通过后 COMMIT。
- Step 6 Redis 精确清理：预检/执行 3499 个目标 key；安全白名单 `token/email_code/limit` 命中始终为 0；复扫目标 key 为 0。
- Step 7 全栈切换：Python/Java/前端/种子/评估集均切到 29 类；前端 tracked patch 已生成。
- Step 8 回归门槛：Python `1094 passed, 3 skipped`；v2 测试 `66 passed`；Java 全量 `mvn test` 通过；前端 4 个 Node 测试 + 5 个 Vue SFC 编译通过。
- Step 9 在线验证：Python/Java 健康检查通过；Milvus 三集合 schema 无 category；10 条 Milvus → MySQL 抽样全部返回 29 类合法 category；退役 3 类由 Java 单测锁定 400。
- Step 10 v2a 独立基线：
  - 分类：`docs/evidence/2026-11-27-eval-classify-v2a.txt`
  - 检索：`docs/evidence/2026-11-27-eval-retrieval-v2a.txt`
  - 视觉：`docs/evidence/2026-11-27-vision-v2a.md`
  - 验收证据：`docs/evidence/2026-11-27-taxonomy-v2a-phase1-smoke.md`

---

## Phase 2（`v2b`）：新增 4 个高价值独立小类（29 → 33 类）

**前提**：Phase 1 (`v2a`) 全量验收通过、在线运行与 `v2a` 评估基线已锁定。

### 2.1 新增 4 类与独立槽位定义
| `major/sub` | 中文名称 | 处置部门与核心依据 | 独立 A/B 槽位（直接落位，不用 `describe`） |
| --- | --- | --- | --- |
| `fire/ebike_hazard` | `电动自行车违规停放/充电` | 消防/住建/物业；国办发〔2024〕19号、GB 43854-2024 | `hazard_mode` (**A**): 进楼道/电梯/架空层停放充电、电池入户还是飞线充电？<br>`charging_state` (**A**): 现场是否正在通电充电或有发热冒烟/改装迹象？ |
| `municipal/tree_fall_hazard` | `树木倒伏/断枝风险` | 园林绿化/市政应急；《城市绿化条例》 | `tree_state` (**A**): 树木是已倒伏阻断道路/压线，还是严重倾斜或大枯枝悬垂？<br>`impact_target` (**B**): 下方或周边是否为人行道、车位或架空线缆？ |
| `construction/confined_space` | `有限空间作业风险` | 应急/市政排水/住建；《工贸企业有限空间作业安全规定》 | `space_type` (**A**): 具体是化粪池、污水井、地下管廊、泵站还是储罐？<br>`protection` (**A**): 作业前是否已强制通风、气体检测并配备监护防护装备？ |
| `environment_other/hazmat_storage` | `危化品/易燃易爆违规存运` | 应急/公安/消防/生态环保；《危险化学品安全管理条例》 | `material_info` (**A**): 现场是不明化工桶、易燃溶剂、液化气瓶还是烟花爆竹，是否密封？<br>`environment` (**A**): 存放点通风如何、周边有无居民楼、火源或接触风险？ |

### 2.2 Phase 2 实施清单
1. **全栈枚举与护栏同步**：
   - 更新 `core/hazard_taxonomy.py`、`HazardTypeNormalizer.java`（断言更新为 `33`）、`hazardTaxonomy.js`（并输出 `2026-11-27-hazard-taxonomy-v2b-frontend.patch` 并通过 `@vue/compiler-sfc` + JS 单测）；
   - 更新 `prompts.py` 判别优先级（明确给电动车飞线充电主归 `ebike_hazard` 可并发 `illegal_wiring`；`hazmat_storage` 从 `other` 独立；`tree_fall_hazard` 与 `street_light_pole`/`falling_object` 隔离）；
   - 更新 `core/scope_policy.py`（补强 `"电动自行车"`, `"飞线充电"`, `"危化品"`, `"危险化学品"`, `"烟花爆竹"`, `"有限空间"`, `"化粪池"`, `"树木倒伏"`, `"行道树"`，并运行域外负样本反测确认 0 误放）和 `core/uncertainty.py`（`DANGER_TERMS` 增加 `"硫化氢"`, `"中毒"`, `"晕厥"`, `"易燃溶剂"`, `"闪燃"`）；
   - 更新 `skills/{fire,municipal,construction,environment_other}/SKILL.md`。
2. **MySQL 语料归正与增量补全（`migrate_taxonomy_v2b.py`，同样走 `information_schema` 发现 + `--dry-run` + MQ 检查 + 备份 + `--execute`）**：
   - 修正种子脚本与 MySQL 存量：
     - 将原 `环境与其他/其他` 的危化品案例与《危险化学品安全管理条例》→ `环境与其他/危化品/易燃易爆违规存运`；
     - 将原 `环境与其他/其他` 的有限空间中毒案例与《工贸企业有限空间作业安全规定》→ `施工安全/有限空间作业风险`；
     - 将原错放在 `电气与燃气/私拉乱接` / `消防安全/消防通道占用` 的南京雨花台案、北京通州锂电池案、《国办发〔2024〕19号》、《GB 43854-2024》→ 主类改标 `消防安全/电动自行车违规停放/充电`；
     - 修正跨类错标：车辆堵消防通道案从 `车辆占道` 移回 `消防通道占用`；天台/楼道堆可燃物案从 `垃圾堆积` 移回 `消防通道占用`；
     - 为 `municipal/tree_fall_hazard` 补充 `>= 2` 条案例与 `>= 2` 条法规（保证全部 33 类每类均 `>= 2` 案例 + `>= 2` 法规）。
3. **Milvus 增量同步与精确清 Redis**：
   - **必须执行** `python tools/knowledge_sync.py` 将新增案例/法规增量写入 Milvus，并运行 `python db/seed/rebuild_case_embeddings.py` 补全本地降级缓存；
   - 按动态前缀精确清 Redis（与 Phase 1 Step 6 同规范）并重启服务。
4. **评估集升级为 `v2b`（33 类）**：
   - `eval_queries.py` 扩展为 `33 × 2 = 66` 条（原 `other` 危化品桶查询迁至 `hazmat_storage`，`other` 改写为真实长尾场景）；
   - 视觉 `test_set_v2b` 为新增 4 类尽量补齐独立测试图片（特别是 `ebike_hazard`、`tree_fall_hazard`、`hazmat_storage`），重新测算并锁定 `v2b` 基线。

---

## Phase 3（`v2c`）：全量槽位治理、小类风险映射与模糊误报修复

**前提**：Phase 2 (`v2b`) 验收稳定；本阶段不增减分类，只做槽位、风险定级与视觉误报规则治理，便于单独归因效果。

### 3.1 修复剩余 12 个 `describe` 退化与市政/施工错配（`core/slot_schemas.py`）
为以下所有此前退化或错配的小类配置独立 A/B 槽位（**严格控制每个小类 A 槽 `<= 2` 个**）：
- **市政独立槽位**（告别全部问井盖）：
  - `road_surface_collapse`：`collapse_scale` (A: 塌陷规模/深浅/下方空洞), `isolation` (A: 现场是否警戒围挡)
  - `drainage_flood`：`flood_depth` (A: 积水深度与阻断情况), `location_type` (B: 隧道/道路/车库位置类型)
  - `street_light_pole`：`pole_status` (A: 倾斜折断还是不亮), `electric_risk` (A: 周边积水或漏电风险)
- **施工独立槽位**（告别全部问围挡）：
  - `no_barrier`：`site` (A: 是否完全缺硬质围挡还是破损缺口), `impact` (B: 紧邻道路类型)
  - `no_warning`：`warning_status` (A: 全无警示还是缺夜间反光灯), `impact` (B: 路段车速与夜间行人暴露)
  - `scaffold_guard`：`defect` (A: 脚手架连墙件失稳还是临边护栏/安全网缺失), `exposure` (A: 是否仍有高处作业或下方行人)
  - `deep_pit`：`pit_status` (A: 是否出现支护位移、渗水或坑边超载堆料), `isolation` (A: 周边防护与警戒情况)
- **其余此前退化进 `describe` 的类**：
  - `traffic_facility_damage`：`facility_type` (A), `condition` (A)
  - `vehicle_occupancy`：`persistence` (A), `blocked` (A)
  - `blind_path_occupied`：`blocker` (A), `blocked` (A)
  - `illegal_structure`：`structure_detail` (A), `structural_impact` (A)
  - `gas_leak`：`leak_sign` (A), `ventilation` (A)
  - `gas_pipe_aging`：`pipe_condition` (A), `leak_suspect` (A)
  - `elevator_trapped`：`trapped_state` (A), `duration` (B)
  - `elevator_stopped`：`fault_symptom` (A), `occupancy` (A)
  - `elevator_inspection`：`equipment_status` (A), `equipment_type` (B)
  - `garbage_pile`：`waste_type` (A), `impact` (A)
  - `sewage_odor`：`sewage_source` (A), `impact` (B)
- **切换清理**：上线前按第 0 节脚本动态扫描并清理 Redis 会话/checkpoint（防止历史对话里旧 `describe` 槽与新 schema key 冲突）；同步更新 `eval/semantic_grounding/validate_dataset.py`、`eval/eval_retrieval.py` 的 `SLOT_FIXTURE_KEYS` 并重跑验证。

### 3.2 小类粒度 `risk_level` 映射（`core/hazard_taxonomy.py` + `dialogue_understanding.py`）
- 废除 `_planner_system_prompt` 中“环境和其他为 `low`”的粗粒度规则，引入 `SUBCATEGORY_DEFAULT_RISK`：
  - `high`：`fire` 全部 3 类、`dangerous_building`、`falling_object`、`utility` 全部 5 类、`road_surface_collapse`、`scaffold_guard`、`deep_pit`、`temporary_power`、`confined_space`、`elevator_trapped`、`hazmat_storage`。
  - `medium`：`traffic` 全部 4 类、`municipal` 其余 4 类、`illegal_structure`、`no_barrier`、`no_warning`、`elevator_stopped`、`elevator_inspection`、`sewage_odor`、`other`。
  - `low`：`garbage_pile`。

### 3.3 修复模糊图强制报 `other` 与双口径视觉报告（`prompts.py` + `eval/vision/`）
1. 修改 `prompts.py` 第 92 行：删除“图片模棱两可、信息不完整时必须置 `has_hazard: true` 并归 `environment_other/other`”的强制报警条款，改为无清晰客观异常依据时返回 `has_hazard: false` 并在 `reason_if_no_hazard` 注明 `"图像证据不足，无法确认安全隐患"`。
2. 清视觉缓存并在独立 `test_set` 上重跑 `v2c` 评测，单独对比 **FPR 改善幅度**与 **Critical Miss Rate 安全门槛**，输出双口径统计表（区分**视觉外观可判别类**与**非视觉强依赖类：`elevator_inspection`、`gas_leak`、`confined_space`**）。

---

## 附：全阶段 Stop Gates（任一触发即中止，严禁带病推进）

| 关卡 | 触发条件 | 止损处理 |
| --- | --- | --- |
| **Schema 发现闸门** | `information_schema` 发现计划清单之外的线上读/写表存在分类字段 | 中止脚本，核实该表归属后再扩写脚本 |
| **MQ 在途闸门** | `ai_hazard_create_outbox` 存在 `PENDING/PUBLISHING/RETRY`，或 `ai_hazard_create_request` 存在 `PENDING/PUBLISHED` | 禁止停服迁库，等待排空或先处理卡单 |
| **DB 迁移闸门** | 备份行数与原表不一致，或迁移后校验出现任何非当期白名单路径/重复多值/`>3` 项 | 事务 `ROLLBACK`，恢复备份，禁止启动新版本 |
| **Redis 安全闸门** | `--dry-run` 扫描出任意匹配 `safety:token:`、`safety:email_code:`、`safety:limit:` 的键 | 立即修正扫描前缀逻辑，禁止执行删键 |
| **契约与测试闸门** | `mvn test`、`pytest`、前端 JS 单测 + `@vue/compiler-sfc` 编译任一失败；Java `canonicalTypes().size()` 与 Python `ALL_SUBCATEGORY_CODES` 数量不一致；旧小类写入测试未返回 `400` | 阻断上线，全部修复后再重启服务 |
| **版本与实验隔离闸门** | 将 `v2a`/`v2b`/`v2c` 数据直接对比旧 32 类数字作为同口径涨跌，或在同一变更内修改/合并 `rerank` 代码与结论 | 退回重测，各自保留带版本号的基线产物 |
