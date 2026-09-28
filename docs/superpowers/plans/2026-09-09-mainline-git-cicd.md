# 主线计划：Git / CI-CD（引导式）

> 日期：2026-09-09
> 目标：补上"完全不会"的 Git / CI/CD（工作 + 面试必备），用引导式（一段一概念 + 考确认）带过。
> 主线顺序：**Git / CI/CD → 八股**；算法**每天至少 1 题保手感**（别断）。

---

## 一、为什么先补这块
- Git：你一直用 AI 提交（`git add`/`commit`），知其然不知其所以然；面试必问（分支/冲突/回退），工作日常。
- CI/CD：面试会问"你们怎么集成/部署"，且和你项目上云强相关。

## 二、Git 大纲（第 1 段，重点）

### 1. 三个区（已讲，明天确认）
```
工作区 ──add──> 暂存区 ──commit──> 仓库(本地历史)
```
- `add`=挑哪些，`commit`=存档；分两步是为了能"只提交部分改动"。

### 2. 分支 + 合并 + 冲突（高频，最懵）
- 分支：`git branch dev` 建 / `git checkout dev` 切 / `git switch dev`。
- 合并：`git checkout main; git merge dev`。
- **冲突**：两人都改同一文件同一处 → 合并报冲突 → 手动改文件（保留要的）→ `git add` 后 `git commit`。
- 概念：合并是"把另一个分支的改动合到当前分支"。

### 3. 回退
- `git revert <commit>`：**新增一次反向提交**（安全，不动历史）。
- `git reset --hard <commit>`：**丢弃到某提交**（危险，丢改动，慎用）。
- `git reset --soft`：只移分支指针，改动留暂存区。
- 记住：**`revert` 保历史，`reset` 改/删历史**。

### 4. 其他常用
- `git stash`：暂存当前未提交改动，切去做别的，回来 `git stash pop`。
- `git log --oneline` / `git diff` / `git show`。
- `git remote add origin <url>` / `git push -u origin main` / `git pull` / `git fetch`。
- `.gitignore`：忽略不该提交的（target/、node_modules/、.env、.idea/）。

---

## 三、CI/CD 大纲（第 3 段，理解为主）

### 1. 是什么
- **CI（持续集成）**：每次提交/PR 自动跑**构建 + 测试**，尽早发现集成问题。
- **CD（持续部署）**：通过后自动**打包 + 部署**到环境/线上。
- 一句话：**提交代码 → 自动测试 → 自动上线**。

### 2. 工具 / 流程
- 工具：GitHub Actions（写 `.github/workflows/*.yml`）/ Jenkins（`Jenkinsfile`）。
- 一条流水线（结合你项目）：
  ```
  checkout → 装 JDK/Maven → mvn test → mvn package → docker build → docker push → 部署到服务器
  ```
- 触发器：`on: push / pull_request`（push 到 main 或开 PR 时触发）。

### 3. 安全（secret）
- 密钥（DB 密码、SSH key、云凭证）用 **GitHub Secrets / 环境变量** 注入，**不写进仓库**。
- 和你刚配的 `DB_PASSWORD` 走环境变量是一个道理。

### 4. 常见问题
- 凭据、缓存依赖（`actions/cache`）、测试失败自动重跑/拦截、构建产物。

---

## 四、每天节奏（引导式）

1. **先自己刷算法 1 题**（保手感）。
2. **一块 Git/CI-CD 概念**：我讲 + 考你确认，你不用背，**会用自己话复述**即可。
3. 每学完一块，**结合你项目**想一遍（比如"我项目为什么这么提交"）。

## 五、主线后续
- git/CI-CD 学完 → **八股**（MySQL → Redis → JVM → 并发 → Spring → Docker 八股）。
- 面试前：八股二遍背诵 + 模拟问答；算法保持。

> 备注：每天算法 **至少 1 题**，别让算法的坑又拖大。
