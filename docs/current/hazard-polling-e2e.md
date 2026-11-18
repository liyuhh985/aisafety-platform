# 建单状态轮询：单一事实源与测试

前端轮询节奏由 `aisafety-platform-frontend/src/utils/hazardPoll.js` 的
`nextHazardPollDelay(elapsedMs)` 唯一决定；`HomeView.vue` 只调用它，不再复制常量。

## 节奏

| 已用可见时间 | 间隔 |
|---|---|
| 0~10 秒 | 1 秒 |
| 10~60 秒 | 3 秒 |
| 60 秒~10 分钟 | 30 秒 |
| ≥10 分钟 | 返回 -1，停止轮询 |

## 边界单测

文件：`frontend/tests/hazardPoll.test.mjs`（Node 直接运行）

```bash
cd frontend && node tests/hazardPoll.test.mjs
```

覆盖：0、9.9s、9.999s、10s、59.999s、60s、9m59s、距上限 1ms、10m、超 10m、负数、undefined，
并对 0~600s 逐秒扫描断言间隔始终落在 (0, 30000]。

## 浏览器 E2E

脚本：服务器 `/opt/aisafety/e2e/polling-e2e.mjs`（Playwright + Chromium 1223）。
拦截 `/api/**`，不依赖真实登录与真实工单；状态接口先返回 PENDING，再切 SUCCESS。

实测输出（2026-11-08）：

```text
hits=28 elapsed=95.3s
deltas=1013,1011,1016,1008,1011,1007,1010,1006,1012,
       3010,3020,3015,3011,3014,3015,3012,3013,3012,3017,3009,3014,3015,3015,3009,3009,3013,
       30008
creating_visible=true
view_ticket_visible=true
E2E PASS
```

结论：1 秒 / 3 秒 / 30 秒三段与设计一致；SUCCESS 后“查看工单”按钮正常出现。

## 备注

- 前端源码位于本仓库 `frontend/`，轮询边界测试位于 `frontend/tests/hazardPoll.test.mjs`。
- Playwright 安装的 1254 版本下载较慢；实际用 `executablePath` 指向已有的 1223 Chromium 即可运行。
