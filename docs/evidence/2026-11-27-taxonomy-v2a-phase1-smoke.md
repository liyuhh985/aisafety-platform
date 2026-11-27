# Taxonomy v2a Phase 1 验收证据

> 状态：current
> 日期：2026-11-27
> 范围：Phase 1（v2a，32 → 29），不含 Phase 2/3，不含 rerank 改造

## 1. Schema 与迁移

- `information_schema` 实际发现并登记：
  - 迁移：`tb_hazard.hazard_types`、`tb_hazard_case.category`、`tb_regulation.category`
  - 只读审计：`tb_hazard_report.hazard_category`、`ai_historical_analysis.hazard_category`
  - 文档类型审计：`tb_hazard_knowledge.category`（`POLICY/BUILDING/FACILITY/FIRE/TRAFFIC`）
  - 历史 `*_bak_*` 表排除
- 备份 stamp：`20261127_163713`
  - `tb_hazard`：34 行
  - `tb_hazard_case`：231 行
  - `tb_regulation`：139 行
  - `tb_hazard_knowledge`：30 行
- Dry-run 待替换：`tb_hazard` 4 行、案例 18 行、法规 9 行
- Execute 在单事务内完成，COMMIT 前 404 行 taxonomy 全部通过 29 类复审
- 迁移后复核：3 张 taxonomy 表及 3 张审计表旧路径命中全部为 0

## 2. Redis 精确清理

- 动态读取 `SESSION_REDIS_PREFIX=ai:sess:`、`CHECKPOINT_BACKEND=redis`
- dry-run：3499 个目标 key，安全白名单命中 `token/email_code/limit = 0/0/0`
- execute：删除 3499 个目标 key
- 删除后 dry-run：目标 key 总数 0
- 未使用 `FLUSHDB`，未触碰认证、验证码、限流前缀

## 3. 契约与测试

- Python：`1094 passed, 3 skipped`
- v2 评估测试：`66 passed`
- Java：完整 `mvn test` 通过
- 旧客户端 400：`HazardTypeNormalizerTest` 覆盖 9 个退役标识，全部返回 400 + `"隐患类别已升级，请刷新页面"`
- 前端：4 个 Node 测试通过；5 个引用 `hazardTaxonomy.js` 的 Vue SFC 完成 parse/script/template 编译
- 前端 Patch：`docs/superpowers/patches/2026-11-27-hazard-taxonomy-v2a-frontend.patch` 已进入 Git 索引

## 4. 在线验证

- Python `/api/ai/health`：200，session/checkpoint 均 effective=redis
- Java `/api/ai/health`：200
- Java `/actuator/health`：UP
- RabbitMQ worker 恢复运行；hazard 相关三队列均为 0
- Milvus 三集合 schema 仅含 `doc_id/content_hash/embedding`
- `knowledge_sync.py` 三类 SQL 均不含 `category`
- 10 条 Milvus → MySQL 抽样（其中 3 条来自被合并类）全部回查到合法 29 类 category
- 抽样明细：`docs/evidence/2026-11-27-taxonomy-v2a-retrieval-sample.json`

## 5. 独立基线

- 分类：`docs/evidence/2026-11-27-eval-classify-v2a.txt`
- 检索：`docs/evidence/2026-11-27-eval-retrieval-v2a.txt`
- 视觉：`docs/evidence/2026-11-27-vision-v2a.md`
