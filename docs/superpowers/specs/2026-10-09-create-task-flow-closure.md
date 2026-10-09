# 建任务确认链路闭环（完整性总结）

日期：2026-10-09　范围：`ai-module`（Python）+ `safety-web`（Java）　状态：已上线、已线上验收

## 1. 起因

线上真机测试走「完整报告 → 点确认建任务」，出现两个现象：

1. 点「确定要建」之后，AI 回的是越界拒答：「我这边只负责城市安全隐患相关咨询…」，任务没建出来。
2. 完整报告末尾还夹了一句模型自己写的问句（「这个消防栓的产权或者管理责任单位是哪一家？」），紧接着才是「要不要建任务」。

## 2. 根因（都不是措辞问题）

### 2.1 会话号根本没到浏览器 → 图里的确认闸门永远恢复不了

- 前端靠**响应头** `X-Session-Id` 记会话号（`HomeView.vue`），而 Java 转发 SSE 时**从来没设过这个头** → 前端 `sessionId` 恒为空串 → 每轮都带空 `session_id` 打到 Python → `server.py` 每次新生成 uuid → **每一轮都是全新会话**。
- 「建任务确认闸门」靠 `thread_id`（=会话号）恢复中断（`core/assistant_graph.py`），会话对不上就恢复不了 → 用户点确认发来的「好的」被当成**一句全新闲聊** → 判成越界 → 回那句模板。
- 反证：用**真实会话号**直连 Python，同一会话第二轮的「好的」能正常建单。

### 2.2 完整报告被允许带一个问句

- `_report_rules()` 里写的是「最多只能提一个问句」，流式执行器对完整报告也放行 1 个问号（`question_limiter(1)`），模型就把这唯一一次机会用掉了。
- 系统自己早就埋了这个点的告警，线上日志留下过：`report_question_redundancy reasons=['question_without_decision_missing'] code=fire_water_abnormal`。

### 2.3 顺带抓到的第三个（真会导致「系统繁忙」）

- 高德未命中时 `district` 返回的是**空数组 `[]`**，而 Java `AiHazardDTO.district` 是 `String` → Jackson 反序列化抛异常 → 500 → 用户看到「⚠️ 系统繁忙，请稍后再试」。
- 线上错误栈：`HttpMessageNotReadableException: Cannot deserialize value of type java.lang.String from Array value`；抓到的真实 payload 里就是 `"district": []`。
- 注意：`geocode()` 本身**从不抛错**（超时/无 key/未命中一律降级成空坐标），所以「系统繁忙」跟高德失败无关，是**类型**问题。
- 「用户没写地址 / 抽不到地址」走的是另一条路：**追问地址**（`ask_address`），不报错。

## 3. 改动清单

| 文件 | 改了什么 |
| --- | --- |
| `safety-web/.../AiController.java` | `assistantStream` 生成会话号并回 `X-Session-Id` 响应头（没带就生成），随请求转给 Python |
| `ai-module/core/assistant_graph.py` | ① 完整报告 0 问句（规则 + 执行器上限 0）；去重规则只留给初步报告 ② 新增 `_emit_event()`，建单成功推 `task_created` 结构化事件，正文不再显示工单编号 |
| `ai-module/tools/hazard_submit.py` | 上报 payload 在契约边界收口类型（`_as_text` / `_as_severity`），`severity=0` 不再被 `or 1` 吞掉 |
| `ai-module/tools/amap_geo.py` | 高德行政区字段就地收敛成字符串（未命中时是 `[]`） |
| `ai-module/tests/*` | 4 个文件更新断言 + 2 个新测试文件（payload 类型、task_created 事件） |
| `docs/superpowers/specs/2026-10-09-assistant-task-created-frontend-spec.md` | 前端对接规格（交另一个模型执行） |

## 4. 验收证据（全部线上实测，走 nginx→Java→AI 真链路）

- 5 轮完整流程：**4 轮全绿**（有会话号、完整报告 0 问句、点确认成功建单，任务 55–58）；第 5 轮是规划器把同一句话判成了「纯回答+追问」这个**另一种产物**，不是建单链路问题。
- 地址追问链路：不带地址的隐患 → 报告 → 确认 → 追问地址 → **在输入框打字补地址** → `✅ 已创建隐患任务`（任务 59）。说明「没地址」不会报错。
- 事件化改动后的线上原文：`data:{"type": "task_created", "content": {"hazard_id": 61, "hazard_code": "#HAZ-61"}}`，正文为 `✅ 已创建隐患任务`（无编号）。
- 回归：既有 `loop_live.py` 的 M1 3/3、M2 3/3 未被报告改动带坏。
- 单测：`ai-module/tests` → **821 passed / 3 skipped / 0 failed**。
- 测试数据：本轮造的测试工单全部按 id 删除（49–59、61），无关联动作行、无 outbox 残留。

## 5. 已知边界（如实记录）

1. **同句不同产物**：规划器对同一句输入偶尔判成另一种产物（第 5 轮）。属已知的 intent 漂移，本轮未处理。
2. **多轮记忆刚真正生效**：以前线上其实是「每轮独立、无记忆」，所以很多多轮问题被这个 bug 藏住了。会话连续之后，之前登记未拍板的「情况二」（用户没回答追问就换话题）会在真实使用中暴露，目前**没有规则**。
3. **地址很模糊时**：高德定不到位 → 工单照样建得出来，只是**没有坐标**（地图上标不出来）。`AiHazardDTO` 本身允许坐标为空。
4. **前端仍待改**：`ask_address`（追问地址）的中断卡片现在也渲染成「确认建单 / 不用了」两个按钮 —— 点「确认建单」会把「好的」当地址发回去，导致**反复追问**。绕过办法是在输入框里打字给地址；正解见前端规格文档。

## 6. 部署与回滚

- AI：改前文件备份在 `/home/ubuntu/ai-deploy-backups/taskgate-20261008/`（`assistant_graph.py.before`、`hazard_submit.py.before`、`amap_geo.py.before`）与 `/home/ubuntu/ai-deploy-backups/taskevent-20261009/assistant_graph.py.before`；重启脚本 `/home/ubuntu/restart_g2.sh`。
- Java：改前 jar 备份 `/home/ubuntu/backend-deploy-backups/safety-backend.jar.before-taskgate`；起停脚本 `/home/ubuntu/stop-backend.sh` / `start-backend.sh`。
- 线上当前 md5：`assistant_graph.py=09128682c6e93c87645b1713a99d3dbd`、`hazard_submit.py=c09cf3d334d0a1e1b77ffe6595d3db99`、`amap_geo.py=c36f7a2ac556ff675d02a6de47192371`（与本地一致）。