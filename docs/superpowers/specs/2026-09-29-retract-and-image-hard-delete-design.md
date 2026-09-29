# 设计：隐患任务"撤回" + 删除报告时硬删图片（含失败重试）

日期：2026-09-29（v2，按使用者决定更新）　　类型：spec（未实现）

## 0. 本轮范围（决定表）

| 项 | 决定 | 是否本轮 |
| --- | --- | --- |
| 隐患任务撤回 | 仅**创建人**、仅 `status=0`（未接单）；**不审核**；撤回后**只有管理员能看到**；状态值 **5**（4 被「已驳回」占用） | ✅ 本轮 |
| 删报告时删图片 | **同步硬删对象**（不做软删、不做回收桶） | ✅ 本轮 |
| 删对象失败 | **进 outbox 重试**（照向量删除那条链的模式），不静默堆积孤儿对象 | ✅ 本轮 |
| `image_key` | 加列 + **一次性回填存量**，让兜底解析路径几乎用不上 | ✅ 本轮 |
| 语料（案例/法规/知识）DELETE 权限 | 收紧到 **ADMIN** | ✅ 本轮（新纳入） |
| Python `/api/ai/internal/vectors/delete`（当前 404） | 实现 + 给 outbox 加重试上限 | ✅ 本轮（新纳入） |
| 隐患 `GET` 系列 | **保持公开**（产品选择）；风险登记见 §6 | 已定 |
| 语料管理页 / 新增案例法规写入接口 | 不做 | ❌ |
| 图片软删 + 异步清理 / 回收桶 | 不做（改用硬删 + 失败重试） | ❌ |
| 撤回走审核 | 不做 | ❌ |

---

## 1. 背景与实测依据（查代码/线上得到，非推测）

1. 图片存 MinIO：`FileUploadService.upload()` 只 `putObject`，返回 `{base-url}/{bucket}/{filename}`；入口 `POST /api/upload`。
   全仓**没有任何** `removeObject` 调用 → 现在删报告只删 DB 行，对象永久残留。
2. `ReportService.delete()` 只有 `mapper.delete(q)`。
3. 桶策略**匿名可读、不可列**（匿名 HEAD 不存在的对象返回 404 而非 403）；图片 URL 用公网 IP 拼：`http://106.53.219.214:9100/safety-images/{uuid}.jpg`。
4. `/api/hazard` 是状态机 `0 待处理 → 1 已接单 → 2 整改中 → 3 完成 → 管理员审核`，**没有任何撤回/删除入口**。
5. `SecurityConfig`：`anyRequest().authenticated()`；`GET /api/hazard`、`/api/hazard/{id}`、`/api/hazard/stats` 为 `permitAll`。
   三张语料表的 **DELETE 仅要求登录**（`CaseController/RegulationController/KnowledgeController` 都没有 `@PreAuthorize`）。
6. 向量删除链：`CaseService:35` / `RegulationService:36` / `KnowledgeService:40` 调 `enqueueDelete` → `VectorDeleteOutboxWorker` → 调 AI 侧端点（**404**）；
   且 `VectorSyncOutboxMapper.findClaimable` **没有 retry_count 上限**，`markFailed` 只在 `VectorSyncPermanentException` 时触发 → **无限重试**。

---

## 2. 需求 A：隐患任务撤回（withdraw）

### 2.1 规则

- 新状态：**`5 = 已撤回`**（⚠️ 实现时发现 `4` 已被占用为「已驳回」，见 `HazardServiceImpl.toVO` 的 switch）；`withdrawn_at` / `withdrawn_by` 留痕。
- **仅 `status=0` 可撤**；`status>=1` 一律拒绝（409）。
- **仅创建人本人可撤**；管理员不代撤（走既有 `review` 驳回）。
- **AI 上报的隐患同样可撤**（`status=0` 且是本人上报）。*（默认，可否决）*
- **不审核**，撤回立即生效。

### 2.2 接口

```
POST /api/hazard/{id}/withdraw        （需登录）
→ 200 R<HazardVO>（status=4）
→ 404 "任务不存在或无权限"（非本人/不存在）
→ 409 "该任务已被受理，无法撤回"（status != 0）
```

并发与幂等用**一条条件更新**，不要先查后改：

```sql
UPDATE tb_hazard
   SET status = 4, withdrawn_at = NOW(), withdrawn_by = #{userId}, update_time = NOW()
 WHERE id = #{id} AND user_id = #{userId} AND status = 0
```

影响 0 行 → 再查一次区分 404 / 409；重复点撤回 → 幂等（第二次直接 200，前端不用特判）。

### 2.3 可见性（按决定：只有管理员能看到已撤回）

| 角色 | 列表 | 详情 | 统计 |
| --- | --- | --- | --- |
| 普通用户 | 不显示自己的已撤回 | 自己的已撤回 → 404 | 不计入 |
| 处理人 | 不显示 | — | 不计入 |
| 管理员 | **显示**（可筛 `status=5`） | 可看 | 单列"已撤回"计数；"待处理"不含撤回 |

实现：`HazardService.page()` 非管理员分支加 `status <> 4`；`getById` 非管理员且 `status=4` → 返回空。

### 2.4 验收测试（Java 单测）

1. 创建人撤自己 `status=0` → 200 且 `status=4`、留痕字段落库。
2. 撤别人的 → 404 且**零副作用**。
3. 撤 `status=1` → 409。
4. 重复撤 → 幂等。
5. 普通用户列表看不到已撤回；管理员能看到。
6. `/stats` 口径：撤回不计入待处理，单列计数。

### 2.5 前端最小改动清单（转前端）

- `status==0 && 是我的` 显示"撤回"；点击 → `POST /api/hazard/{id}/withdraw` → 成功后移除该项。
- 确认文案："撤回后该记录只对管理员可见，确定撤回吗？"
- 管理员列表加"已撤回"筛选项（普通用户拿不到这些数据，无需处理）。

---

## 3. 需求 B：删除报告时硬删图片（失败进 outbox 重试）

### 3.1 精确流程（顺序很关键，保证不产生孤儿）

1. **取行 + 属主校验**（管理员可删他人）；拿到 `image_key`，为空则从 `image_url` 末段解析。
2. **尝试 `removeObject(key)`**：
   - 成功，或对象不存在（`NoSuchKey`）→ 进入第 3 步（后者视为成功，幂等）；
   - **真实失败**（网络/权限/5xx）→ **在同一事务内**插入一条 `tb_resource_cleanup_outbox` 任务
     （`target='MINIO'`, `bucket`, `object_key`, `source_table='tb_hazard_report'`, `ref_id=报告id`）→ 进入第 3 步；
     若**插入任务也失败** → 整体回滚，返回 500（**绝不删行**，否则 key 丢失、对象永久孤儿）。
3. **删 DB 行** → 200。重复删除 → 行不存在也不报错（保持现状语义）。

### 3.2 代码改动

1. `FileUploadService.removeObject(String objectKey)`：`NoSuchKey` 静默成功，其他异常抛出。
2. `tb_hazard_report` 加列 **`image_key VARCHAR(128) NULL`**；`ReportService.save()` 落库（`FileUploadVO.filename` 就是 key）。
3. `ReportService.delete(id, userId)` 按 3.1 改造（先查行 → 删对象 → 兜底入队 → 删行）。
4. 新表 `tb_resource_cleanup_outbox`（字段见 3.3）+ `ResourceCleanupWorker`（与 `VectorDeleteOutboxWorker` 同模式：claim/退避/永久失败），**重试上限 10 次**（退避 30s→1h），超限 `FAILED` + error 日志。
5. 迁移脚本 `db/migrate_withdraw_and_image_cleanup.py`（幂等：`SHOW COLUMNS/TABLES` 先探测），步骤：
   ① `tb_hazard` 加 `withdrawn_at`、`withdrawn_by`；
   ② `tb_hazard_report` 加 `image_key`；
   ③ **回填**：`UPDATE tb_hazard_report SET image_key = SUBSTRING_INDEX(image_url, '/', -1) WHERE image_key IS NULL AND image_url LIKE '%/%'`，打印回填条数；
   ④ 建 `tb_resource_cleanup_outbox`（并留档 `db/resource_cleanup_outbox.sql`）。

### 3.3 为什么用新表而不是复用 `tb_vector_sync_outbox`

后者的 `doc_id` 是数字、`source_table` 有白名单（`enqueueDelete` 拒绝未知表），塞不下对象 key。
**TODO（记一笔）**：将来可以把两张表合并成一张带 `target('MINIO'|'MILVUS')` 的表，本次不合并以免动到既有 claim SQL 与测试。

### 3.4 验收测试

1. 删自己的报告 → 对象 404（`statObject`）+ 行消失。
2. 对象已不存在 → 幂等成功，行仍被删。
3. `removeObject` 抛异常 → 行仍在，且**新增一条 outbox 任务**（status=PENDING）。
4. outbox 插入失败（mock）→ 行仍在，返回 500。
5. 越权删除 → 403/404，**对象与行都不动**。
6. 老数据（`image_key` 为空）→ URL 末段解析成功照样删；URL 异常 → 入队 outbox 而不是静默失败。
7. Worker：成功 → SUCCEEDED；连续失败 → retry_count 递增、超 10 次 → FAILED。

---

## 4. 本轮同时修的两条（新纳入）

### 4.1 语料 DELETE 收紧到 ADMIN

- `CaseController.delete` / `RegulationController.delete` / `KnowledgeController.delete` 加 `@PreAuthorize("hasRole('ADMIN')")`。
- 测试：普通用户 → 403；ADMIN → 200。附带：这三处 delete 已投递向量删除 outbox，见 4.2。

### 4.2 补齐向量删除闭环（现在会造僵尸任务）

1. 实现 Python `POST /api/ai/internal/vectors/delete`：header `X-Internal-Token` 校验，body `{table, ids}`，表名白名单，返回删除条数；**解开 `tests/test_vector_delete_api.py` 的 `xfail(strict=True)`**。
2. `VectorSyncOutboxMapper.findClaimable` 增加 `retry_count < 10`；worker 把 HTTP 4xx（除 429）归类为 `VectorSyncPermanentException` → `markFailed`。
3. 测试：端点三例（未授权 401 / 未知表 400 / 正常删除）+ mapper 上限行为 + worker 4xx 不再无限重试。

---

## 5. 明确不做

- ❌ 语料管理页面 / 新增案例法规的写入接口
- ❌ 图片软删 + 回收桶 + 延迟物理删除
- ❌ 撤回走审核

## 6. 风险登记（已知且接受 / 待办）

1. **隐患 GET 保持公开**（已定）→ 匿名可分页枚举"未撤回"的隐患并拿到图片 URL。**撤回过滤必须在服务端做**，否则撤回后仍可被匿名看到。将来要收紧：`SecurityConfig` 一行 + 公开接口不返回 `imageUrl`。
2. **两套 outbox 机制并存**（向量 / 对象清理）→ 记 TODO 合并；本轮不合并。
3. **FAILED 任务目前只有日志、无告警** → 生产要接告警（本轮不做）。
4. 撤回后"重新提交"不支持（要报就重新报一条）。

## 7. 回归与部署

- Java 单测全绿（新增 §2.4 / §3.4 / §4 的用例）+ `ai-module` 全量 pytest 保持 798 passed 基线（本次含解开一条 xfail）。
- 迁移先本地库跑通、再线上库跑（幂等，可重复执行）。
- 部署：重建 `safety-web` jar → 上传 `/home/ubuntu/safety-backend.jar` → 重启（**重启方式待确认**：当前云端进程是 `java -jar /home/ubuntu/safety-backend.jar --spring.profiles.active=local`，需要先看有没有现成重启脚本）。
- 回滚：新增列/表可保留（无害）；代码回滚即回到现状（对象残留问题复现，但不新增故障）。
