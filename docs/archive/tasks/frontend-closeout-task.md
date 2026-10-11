> 状态：historical
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 安全平台 V1.0 前端收尾任务

## 任务目标

完成云端 Vue 前端的最后验证和必要修复，闭环确认：

```text
图片分析完成 -> 保存报告 -> 历史列表 -> 历史详情 -> 刷新仍存在 -> 删除
```

只处理上述闭环中的阻断问题，不新增业务功能、不重做页面设计、不扩大技术范围。

## 当前环境

- SSH 目标：`ubuntu@106.53.219.214`
- 前端源码：`/home/ubuntu/aisafety-platform-frontend`
- 云端部署目录：`/var/www/safety-platform`
- Nginx 前端入口：`:8081`
- 构建命令：`npm run build`

当前已确认：

- Nginx `http://127.0.0.1:8081/` 返回 `200`。
- `frps` 正在运行，云端 API 通过既有代理链路访问本地 Java。
- 当前 `index.html` 引用的是 2026-07-26 构建产物。
- 当前线上 `AnalysisView` bundle 已包含 `Bearer` 认证头和报告保存字段。

## 必须保护的现有修改

进入任务后先执行：

```bash
cd /home/ubuntu/aisafety-platform-frontend
git status --short --branch
```

当前源码有未提交修改，不能重置、覆盖或清理：

- `src/views/AnalysisView.vue`
- `src/views/HistoryView.vue`
- `src/views/MapPage.vue`

不要输出或提交真实 API Key、Token、密码、`.env` 或其他敏感配置。

## 已发现的前端阻断问题

`HistoryView.vue` 当前点击报告时会跳转：

```text
/report/:id
```

但当前 `src/router/index.js` 没有 `/report/:id` 路由，源码中也没有报告详情页组件。需要补齐最小详情展示闭环，或者采用与现有页面一致的等价实现，但不能删除历史详情需求。

详情页至少要：

- 携带当前登录用户的 Bearer Token 调用 `GET /api/report/{id}`；
- 展示隐患类别、严重程度、描述、报告正文和整改建议；
- 处理报告不存在、无权限、Token 失效和网络错误；
- 能返回历史列表或分析页；
- 不把接口错误当成空报告静默展示。

## 前端接口契约

### 保存报告

```http
POST /api/report
Authorization: Bearer <token>
Content-Type: application/json
```

请求 body：

```json
{
  "imageUrl": "图片地址",
  "hazardCategory": "建筑施工",
  "severity": "高",
  "description": "隐患描述",
  "rectification": ["整改建议"],
  "reportText": "完整报告正文"
}
```

### 查询历史列表

```http
GET /api/report?current=1&size=50
Authorization: Bearer <token>
```

后端列表记录是平铺字段，重点检查前端兼容以下字段：

```text
id
imageUrl
hazardCategory
severity
description
rectification
reportText
createTime
```

不要只依赖不存在的 `vision` 嵌套对象。若保留兼容映射，必须优先使用后端平铺字段。

### 查询详情

```http
GET /api/report/{id}
Authorization: Bearer <token>
```

### 删除报告

```http
DELETE /api/report/{id}
Authorization: Bearer <token>
```

## 执行顺序

1. 检查源码 Git 状态，阅读当前 `AnalysisView.vue`、`HistoryView.vue` 和路由配置。
2. 检查 `/var/www/safety-platform/index.html` 当前引用的入口 bundle，确认源码和部署产物对应关系。
3. 如果没有可用真实账号，先完成代码和 bundle 静态检查，不伪造“保存成功”的线上结果。
4. 如需修复详情路由或字段映射，只做最小修改。
5. 只有源码确实修改后才执行 `npm run build`，并确认构建成功。
6. 部署前保留当前部署目录状态；不要删除旧 assets，除非确认有明确的可恢复部署方案。
7. 部署后重新检查 `index.html` 和新 bundle，确认浏览器实际会加载新版本。
8. 使用真实账号进行浏览器验证，必要时退出登录、重新登录和 `Ctrl + F5`。

## 浏览器验收清单

- [ ] 分析页能上传合法图片并收到 Vision、检索、报告和 `done` 事件。
- [ ] `/api/upload/image` 返回 `200`。
- [ ] 保存请求 `/api/report` 返回 `200`。
- [ ] 保存请求头严格为 `Authorization: Bearer <token>`。
- [ ] 保存 body 包含 `hazardCategory`、`severity`、`description`、`rectification`、`reportText`。
- [ ] 历史列表显示当前报告的类别、严重程度和描述。
- [ ] 点击历史报告能够进入详情页，而不是落到未匹配路由。
- [ ] 详情页显示完整报告正文和整改建议。
- [ ] 刷新详情页后数据仍存在。
- [ ] 删除报告后历史列表立即更新。
- [ ] Token 失效或接口返回错误时有明确提示并能回到登录流程。
- [ ] 重新登录后只能看到当前用户自己的报告。

## 交付内容

任务结束时报告：

1. 是否修改源码，修改了哪些文件。
2. 是否重新构建和部署，实际加载的入口 bundle 名称。
3. 保存、列表、详情、删除各请求的实际 HTTP 状态。
4. 尚未完成的验收项及原因。
5. 不要继续扩展其他页面或业务功能。

