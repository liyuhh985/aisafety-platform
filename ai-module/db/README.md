# ai-module/db 目录说明

> 状态：current
> 最后核对：2026-10-11

这个目录按**用途**分层，另外保留一个运维脚本：

```
schema/       建表与迁移（migrate*.py / *.sql / run_migrate.py）
seed/         语料录入与数据修复（data_* / append_* / enrich_* / import_* / cleanup_* / verify_*）
experiments/  一次性度量与诊断（measure_* / g1_ / g3_ / g5_ / mutation_* / recheck_* / analyze_*）
load_hazard_create_mq.py   建单 MQ 压测脚本（运维用，不是一次性实验）
README.md     本文件
```

## 测量产物（不入库）

`experiments/` 里的脚本把结果写到**本目录根下**的 `eval_*.txt`
（如 `eval_stage5a_baseline.txt`、`eval_increment_turns.txt`）；
`eval/eval_rag.py` 把报告缓存写到 `eval_reports/`。
这些是**可重新生成的产物，不是源码**，2026-10-11 起加入 `.gitignore` 并移出版本库：

- `eval_*.txt`
- `eval_reports/`
- `kw_probe*.txt` / `graph_shape.txt` / `score_dist.txt` / `slot_audit.txt` / `question_source.txt`

想看整理后的结论，去 `docs/evidence/`（带日期的那批 md）。
想重新生成原始输出，按对应脚本头部的用法跑（多数需要 `ai-module` 为工作目录 + 真实模型 / MySQL）。

## 运行约定

- 绝大多数脚本假定**工作目录是 `ai-module`**：
  ```bash
  cd ai-module && python db/schema/migrate_hazard_create_mq.py
  cd ai-module && python db/seed/import_all_new_data.py
  cd ai-module && python db/experiments/measure_stage0.py --only g4
  ```
- 数据库连接统一读 `ai-module/db_config.py`（真实环境变量优先，其次 `ai-module/.env`）。
- 两类**路径不要动**，它们被生产代码读取：
  - `db/case_embeddings.json` ← `tools/hybrid_search.py` 读
  - `db/backup/` ← `seed/import_all_new_data.py` 写
- 语料数据现在是**人工录入**：`tb_hazard_case` / `tb_regulation` 由 `seed/` 下的脚本或手工 SQL 维护，
  项目里没有自动抓取链路。
