> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/hazard-lifecycle.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 执行计划：撤回 + 图片硬删（含失败重试）+ 权限与向量闭环

上游 spec：`docs/superpowers/specs/2026-09-29-retract-and-image-hard-delete-design.md`
流程要求：TDD（先写失败测试 → 实现 → 全量回归）→ 迁移 → 部署 → 线上冒烟。**每个阶段独立可回滚。**

## 阶段 0：迁移（先库、后码）

1. 新增 `ai-module/db/migrate_withdraw_and_image_cleanup.py`（幂等：`SHOW COLUMNS/TABLES` 探测后再改）：
   - `tb_hazard` + `withdrawn_at DATETIME NULL`、`withdrawn_by BIGINT NULL`
   - `tb_hazard_report` + `image_key VARCHAR(128) NULL`
   - 回填 `image_key = SUBSTRING_INDEX(image_url,'/',-1)`，打印回填条数
   - 建 `tb_resource_cleanup_outbox`（留档 `db/resource_cleanup_outbox.sql`，风格对齐 `vector_sync_outbox.sql`）
2. 验收：脚本连跑两次都不报错、第二次全部走"已存在跳过"；回填条数 > 0；`SHOW COLUMNS` 确认列都在。

## 阶段 1：隐患撤回（Java）

1. 测试先行：`HazardServiceTest` 加 §2.4 的 6 条。
2. 实现：`HazardMapper.withdraw(id, userId)`（条件更新 SQL）→ `HazardService.withdraw()` → `HazardController.withdraw()`。
3. 可见性：`page()` 非管理员加 `status <> 4`；`getById` 非管理员 + status=4 → 空；`stats` 分列。
4. 验收：6 条测试全绿；手工 curl（带 token）撤回一条 `status=0` 的任务 → `status=4`、再撤 → 幂等、撤 `status=1` → 409。

## 阶段 2：删报告硬删图片（Java）

1. 测试先行：`ReportServiceTest` 加 §3.4 的 7 条（MinIO 用 mock）。
2. 实现：`FileUploadService.removeObject()`（NoSuchKey 幂等）→ `ReportService.delete()` 按 3.1 顺序改造 → 新 outbox 实体/Mapper/Service/`ResourceCleanupWorker`（上限 10 次）。
3. 验收：7 条测试全绿；手工删一条线上报告 → `statObject` 返回 404、行消失；mock 失败路径产生 PENDING 任务。

## 阶段 3：权限与向量闭环（Java + Python）

1. 三个语料 controller 的 delete 加 `@PreAuthorize("hasRole('ADMIN')")` + 测试（普通用户 403）。
2. Python 实现 `POST /api/ai/internal/vectors/delete`（token 校验 + 表名白名单 + 返回条数）。
3. 解开 `ai-module/tests/test_vector_delete_api.py` 的 `xfail(strict=True)`；**跑全量 pytest 确认 798 → 799+ passed 且 0 failed**（那条 xfail 变 passed）。
4. `VectorSyncOutboxMapper.findClaimable` 加 `retry_count < 10`；worker 把 4xx（除 429）判为永久失败；补测试。
5. 验收：Java 与 Python 双侧测试全绿；线上手工删一条 case → outbox 任务 SUCCEEDED（Milvus 里对应向量消失）。

## 阶段 4：部署与冒烟

1. 重建 jar → 上传 `/home/ubuntu/safety-backend.jar` → 重启（**先确认重启脚本**；若无则记录实际命令并补一个脚本）。
2. 线上冒烟（带测试账号）：撤回一条自建待办 → 列表消失、管理员可见；删一份报告 → 图片 URL 变 404、列表刷新后不存在；删一条 case（ADMIN）→ outbox SUCCEEDED。
3. 冒烟脚本/命令落盘到 `docs/superpowers/` 便于复跑。

## 阶段 5：文档收口

- spec 状态改为"已实现"，把实测结果（回填条数、outbox 成功/失败计数、冒烟输出）写回。
- 前端改动清单（§2.5）单独拎出来交给前端那边。

## 风险与边界

- 迁移不可逆项：新增列/表（回滚时保留即可，无破坏）。
- 两套 outbox 并存 → 记 TODO，本轮不合并。
- `image_key` 回填只对"URL 形态未变"的老数据有效，解析不出的仍走兜底（并进 outbox）。
- 部署重启方式未确认 → 阶段 4 第一步就是把它确认清楚，避免"改了没生效"。
