# 城市安全隐患智能分析平台前端

Vue 3 + Vite 单页应用，负责登录、隐患上报、AI 对话、报告查看、工单流转和地图展示。

## 开发

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

默认开发地址为 `http://localhost:3000`，`/api` 会代理到 `VITE_API_PROXY_TARGET`。

## 环境变量

| 变量 | 用途 |
|---|---|
| `VITE_API_PROXY_TARGET` | Vite 开发环境 API 代理地址，默认 `http://127.0.0.1:8080` |
| `VITE_AMAP_KEY` | 高德地图 JavaScript API Key |
| `VITE_AMAP_SECURITY_CODE` | 高德地图安全密钥 |

真实 Key、Security Code 和 `.env` 文件不得提交到 Git。

## 构建与测试

```bash
npm run build
npm test
```

构建产物输出到 `dist/`，生产环境由 Nginx 托管并反向代理 `/api` 到 Java 后端。
