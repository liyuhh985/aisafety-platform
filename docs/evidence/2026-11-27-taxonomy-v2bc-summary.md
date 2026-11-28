# Taxonomy v2b / v2c 执行汇总

> 日期：2026-11-27
> 范围：v2b 新增 4 类（29→33）；v2c 槽位治理、风险映射、模糊图误报规则修复
> 隔离声明：未修改或混入 rerank 代码与评估归因

## v2b

- 新增 `fire/ebike_hazard`、`municipal/tree_fall_hazard`、`construction/confined_space`、`environment_other/hazmat_storage`
- 4 个新增类均有独立 A/B 槽位，A 槽 ≤2
- MySQL 备份 stamp：`20261127_202824`；迁移后案例 233、法规 143
- 33 类案例/法规均 ≥2
- Milvus 增量：案例 upsert=2，法规 upsert=4；降级缓存 264 条
- 分类基线：小类 0.944±0.030，大类 0.965±0.015，负样本拦截 1.000
- 检索基线：三种情形 Hit@5 均为 1.000；MRR 0.896–0.917；EmptyRate 1.00
- 视觉基线：Recall 0.925，FPR 0.100，Critical Miss 0.050

## v2c

- 18 个退化/错配小类改为独立槽位，全部 A 槽 ≤2
- 33 类 `SUBCATEGORY_DEFAULT_RISK` 全覆盖；环境危化品/有限空间为 high，垃圾堆积为 low
- 模糊图强制 `other` 规则已删除，证据不足返回 `has_hazard=false`
- 分类基线：小类 0.965±0.015，大类 0.980±0.015，负样本拦截 1.000
- 检索基线：三种情形 Hit@5 均为 1.000；MRR 0.896–0.917；EmptyRate 1.00
- 视觉：Critical Miss 0.050 与 v2b 持平；FPR 0.150，较 v2b 的 0.100 变差，未达到预期改善
- 非视觉强依赖类当前仅 2 条正样本，视觉结论不足以形成稳定统计

## 产物

- `2026-11-27-eval-classify-v2b.txt`
- `2026-11-27-eval-retrieval-v2b.txt`
- `2026-11-27-vision-v2b.md`
- `2026-11-27-eval-classify-v2c.txt`
- `2026-11-27-eval-retrieval-v2c.txt`
- `2026-11-27-vision-v2c-dual-metric.md`

## 回归

- Python 全量：1105 passed, 3 skipped
- v2 评估测试：69 passed
- Java 全量 mvn test：通过
- 前端 Node 测试与 5 个 Vue SFC 编译：通过
