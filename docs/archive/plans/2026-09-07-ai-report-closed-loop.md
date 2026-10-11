> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/hazard-lifecycle.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# AI 上报闭环 + 角色权限 执行计划

> 日期：2026-09-07
> 背景：把「AI 聊天/查库」升级为「AI 办事」——用户和 AI 助手对话，AI 分析出隐患后，经用户确认（Human-in-the-loop），**真正写入 `tb_hazard` 建一条隐患任务**，并配合角色权限 + 状态流转。
> 方案已定：**C + B**（新增 AI 专用接口 `POST /api/hazard/ai` + AI 抽地址/高德地理编码）。方向：**Python → Java**（ai-module 用 HTTP 调 Java 建隐患接口，Java 负责鉴权/校验/写库）。

---

## 一、现状盘点（已确认）

- `tb_hazard` 字段：`user_id`(NOT NULL)、`image_url`(NOT NULL)、`hazard_type`(NOT NULL)、`description`、`longitude`(NOT NULL)、`latitude`(NOT NULL)、`address`、`severity`、`status`、`create_time`、`update_time`。
  > 问题：无 `category`/`district` 列；`image_url`、经/纬度在**库层面 NOT NULL**，AI 没图没定位会上报失败。
- `HazardController` 已有 `@PostMapping` 手填上报（从 `Authentication` 取 `userId`）；`HazardService.create(userId, dto)` 已存在。
- `Hazard` 实体有 `status`、`severity`；`HazardAction` 可用于记录状态流转（`hazardId/operatorId/actionType/remark`）。
- `User.role` 为 Integer，现状：`0`=普通用户、`1`=管理员；**尚无「处理人员」角色**。
- `SecurityConfig`：`GET /api/hazard...` permitAll；其余需 JWT 认证；`/api/auth/**`、`/api/ai/health` permitAll。
- Python `ai-module` 目前是「Java→Python」方向（Java `AiService` 调 Python :8000）；**没有 Python→Java 的 HTTP client**。
- 高德 Web Key 已验证有效：`AMAP_WEB_KEY`(已提供)，`/geocode/geo` 返回 `福建省三明市三元区列东街 → 117.640323,26.273526`。
- 消息队列：**第二期**（本期不做，仅预留讲法）。

---

## 二、关键决策（已定）

1. **上报方向**：Python → Java `POST /api/hazard/ai`，带 `X-Internal-Token`（内部令牌）。
2. **Human-in-the-loop**：AI 生成报告 → 问「需要我帮你在系统建一条隐患任务吗？」→ 用户确认 → 再上报。
3. **状态流**：`0 待处理 / 1 已接单 / 2 整改中 / 3 已完成`，AI 上报落库时 `status=0`。
4. **角色**：`0` 普通用户（举报者）、`1` 管理员（人工审查/派单）、`2` 处理人员（线下团队）。
5. **地址策略**：`address`(文本，永远有) + `district`(行政区，地理编码/AI 抽) + `longitude/latitude`（能编码就填，不能留空）。**不要求用户发经纬度**。
6. **地理编码失败降级**：编码失败 → 只存 `address+district`，坐标留空，上报不失败。

---

## 三、Task 分解

### Task 1：迁移 `tb_hazard`（放宽 + 对齐 4 类）
**Files:** `ai-module/db/migrate_ai_report.sql`（或并入 `run_migrate.py`）
- [ ] `ALTER TABLE tb_hazard MODIFY image_url VARCHAR(500) NULL`（AI 可能无图）
- [ ] `ALTER TABLE tb_hazard MODIFY longitude DECIMAL(10,7) NULL, MODIFY latitude DECIMAL(10,7) NULL`（AI 可能无定位）
- [ ] `ADD COLUMN category VARCHAR(30) DEFAULT ''`（4 类：占道/井盖道路/消防通道/施工）
- [ ] `ADD COLUMN district VARCHAR(50) DEFAULT ''`（行政区，地图聚类）
- [ ] `ADD COLUMN report TEXT NULL`（AI 报告全文，可选）
- [ ] `ADD INDEX idx_category (category), idx_status (status)`

### Task 2：Java 新增 AI 上报接口
**Files:** `safety-pojo/.../dto/AiHazardDTO.java`、`safety-web/.../config/SecurityConfig.java`、`safety-web/.../controller/HazardController.java`、`safety-service/.../service/impl/HazardServiceImpl.java`(复用 create)
- [ ] `AiHazardDTO`：`userId`、`category`、`address`、`district`、`longitude`(可空)、`latitude`(可空)、`imageUrl`(可空)、`description`、`severity`、`report`。校验：`category` + `address` 至少一个非空（业务兜底，替代"必填经纬度"）。
- [ ] `HazardController` 新增 `@PostMapping("/ai")`：校验 `X-Internal-Token` 匹配配置 → 从 DTO 取 `userId` → `hazardService.createAi(dto)`（或复用 create，`status=0`）。
- [ ] `SecurityConfig` 放行 `POST /api/hazard/ai`，并加内部令牌校验（新增过滤器或用 controller 内校验）。
- [ ] `HazardServiceImpl.createAi`：写 `tb_hazard` 四类字段（category/hazard_type 同步），`status=0`；记录 `HazardAction`（actionType=CREATE）。

### Task 3：Python 高德地理编码
**Files:** `ai-module/tools/amap_geo.py`、`ai-module/.env`、`ai-module/config.py`(加 `AMAP_WEB_KEY`)
- [ ] `geocode(address) -> {longitude, latitude, province, city, district}`
- [ ] 失败降级：返回空坐标 + 原 `address` + 尽量 `district`，不抛错。
- [ ] `.env` 加 `AMAP_WEB_KEY`；测试 `geocode("三明市三元区列东街")`。

### Task 4：Python → Java 客户端
**Files:** `ai-module/tools/java_client.py`、`ai-module/.env`、`ai-module/config.py`(加 `JAVA_BASE_URL`、`AI_INTERNAL_TOKEN` 已有)
- [ ] `create_hazard(payload) -> {ok, hazardId}`，POST `{JAVA_BASE_URL}/api/hazard/ai`，头 `X-Internal-Token`。
- [ ] 超时/异常处理：AI 上报失败反馈给用户「稍后重试」，不影响对话。

### Task 5：AI 抽取 + 确认 + 上报编排
**Files:** `ai-module/core/assistant_graph.py`、`ai-module/tools/amap_geo.py`、`ai-module/tools/java_client.py`
- [ ] 抽槽扩展：从对话抽 `category`(4类)、`address`、`district`、`severity`、`description`。
- [ ] 生成报告后，在 report 尾部追加「需要我帮你在系统建一条隐患任务吗？」。
- [ ] 用户确认（意图词"要/建/上报/可以"）→ 调 geocode 补坐标 → 调 java_client 上报。
- [ ] 上报成功 → 回复「已创建，任务编号 XXX」；失败 → 降级提示。

### Task 6：角色权限 + 状态流转
**Files:** `safety-pojo/.../entity/User.java`(注释 role 取值)、`safety-web/.../config/SecurityConfig.java`、`safety-web/.../controller/HazardController.java`、`safety-web/.../controller/HazardActionController.java`(新增)
- [ ] role 取值：`0` 普通用户 / `1` 管理员 / `2` 处理人员。
- [ ] 普通用户：可上报、查看自己上报的隐患。
- [ ] 处理人员：可接单、改状态 `0→1→2→3`、填整改（写 `HazardAction`）。
- [ ] 管理员：可审查、派单、管理全部。
- [ ] 接口鉴权：用 Spring Security method security（`@PreAuthorize`）或 URL 级规则约束。

### Task 7：验证 + 测试
- [ ] 迁移后 `SHOW COLUMNS tb_hazard` 确认列可空、有 category/district。
- [ ] 高德 `geocode` 命中 / 失败降级各测一次。
- [ ] `java_client.create_hazard` 命中，`tb_hazard` 新行 status=0、category/address 正确。
- [ ] 无图、无定位（仅 address）也能成功上报。
- [ ] 相关 pytest（如有）全绿。

---

## 四、待你拍板

1. `category` 是否新增列（建议新增，与 `tb_hazard_case/tb_regulation` 的 `category` 对齐），还是复用 `hazard_type`？
2. 角色 role 取值：`0 普通 / 1 管理员 / 2 处理人员`，OK？
3. 状态流转权限：处理人员 `0→1→2→3`；管理员可派单/审查。OK？
4. AI 上报直接 `status=0` 进待处理队列。`「人工审查/派单」作为管理员后续动作` 第二期优化（本期不做）。
5. 前端地图（后期）：无坐标任务按 `district` 聚类/中心点显示，OK？

---

## 五、自检清单

- [ ] `tb_hazard` 可存"没图、没定位"的 AI 上报。
- [ ] `POST /api/hazard/ai` 用内部令牌，Python 能成功建库（status=0）。
- [ ] 地址：`address` 必有，`district` 尽量有，坐标尽量有，失败不阻塞。
- [ ] 角色权限与状态流转可讲清（0/1/2/3）。
- [ ] 第二期 MQ、通知留作讲法。


---

## 进度（2026-09-07 更新）

- [x] Task 1：`tb_hazard` 迁移已完成并验证（image_url/经度/纬度可空 + category/district/report + 索引）。
- [x] Task 2：Java 接口已写（`AiHazardDTO` / `POST /api/hazard/ai` / SecurityConfig 放行 + 内部 token 校验 / `HazardServiceImpl.createAi`，status=0）。**待编译**（本机无 mvn）。
- [x] Task 3：`amap_geo.py` 已验证（命中 + 失败降级）。
- [x] Task 4：`java_client.py` 已验证（后端未启动降级 ok=False）。
- [x] Task 5：userId 链路打通（Java `AiService` 两个重载传 user_id；Python `server.py` 解析并透传）+ `hazard_submit.py`（LLM 抽取已验证）+ `assistant_graph` 报告尾部加"建任务"问句 + 确认拦截（`_is_confirmation`/`_asked_to_create` 已验证）。
- [ ] Task 6：角色权限 + 状态流转 接口（本期先做 AI 上报 status=0；角色/状态接口待后续）。
- [ ] Task 7：端到端验证（需 Java 编译启动 + Python 启动联调）。

> 注：本期已完成"AI 上报 → 建隐患(status=0)"闭环代码；**角色权限/状态流转接口**与**人工审查**列为下一期。

---

## 联调完成（2026-09-07 二次更新）

- [x] AI 上报全链路端到端验证通过：`描述→报告→"要"→ 写库`（id 类型齐全、status=0）。
- [x] 地址兜底：`_regex_address` 正则提取 + 无地址时 `ask_address` 追问 + 下一轮回地址自动补全建任务。端到端验证：无地址→追问→补地址→id=33 入库，地址/坐标/描述齐全。
- [x] 消冗余：删除 `tb_hazard.category` 列，统一用 `hazard_type`（`AiHazardDTO.category` 仅作入参映射到 `hazard_type`）。
- [ ] Task 6：角色权限 + 状态流转（role 0/1/2、0→1→2→3、接单/整改/完成 + HazardAction 记录）——下一期。
- [ ] Task 7：角色/状态接口联调。

> 结论：**AI 上报 → 建隐患(status=0) 闭环已完整打通并验证。** 剩「角色权限 + 状态流转」与「人工审查/派单」。
