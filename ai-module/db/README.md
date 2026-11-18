# ai-module/db 目录说明

> 最后更新：2026-11-18

本目录包含数据库结构、迁移、开发语料导入和建单链路压测工具：

```text
schema/                    建表、迁移与幂等修复脚本
seed/                      开发语料、法规、案例与知识库导入脚本
load_hazard_create_mq.py   建单 MQ 压测工具
README.md                  本文件
```

## 运行约定

- 数据库连接统一读取 `ai-module/db_config.py`，优先使用环境变量，其次使用本地 `.env`。
- `schema/` 中的迁移脚本通常可以重复执行，但升级生产环境前仍应先备份数据库。
- `seed/` 中的脚本用于本地或演示环境准备数据；执行前确认目标库，避免将开发数据导入生产库。
- 建单压测会将数据写入目标数据库，只应在本地或预发环境运行。

## 常用命令

```bash
cd ai-module
python db/schema/run_migrate.py
python db/seed/import_all_new_data.py
python db/load_hazard_create_mq.py --help
```

一次性度量、评测原始输出和历史诊断脚本已归档到私有仓库，不进入公开版本。公开评测代码位于 `ai-module/eval/`。
