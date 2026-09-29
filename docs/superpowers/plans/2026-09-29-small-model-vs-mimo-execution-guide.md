# 本地小模型 vs 线上 MiMo 对照实验：从 0 到 1 落地执行手册

**文档版本**：v2.0（命令级全流程实操版）  
**制定日期**：2026-09-29  
**实验工作区**：`E:\modelTest`（物理全隔离）  
**核心原则**：所有下载程序、模型权重、环境缓存 100% 收敛在 `E:\modelTest`，主项目代码 0 侵入，测试用例 0 污染，命令级可复制。

---

## 目录
1. [实验底数与环境红线](#1-实验底数与环境红线)
2. [工作区目录物理结构](#2-工作区目录物理结构)
3. [实操第 0 步：独立推理引擎安装（Ollama 免安装落地 E 盘）](#3-实操第-0-步独立推理引擎安装ollama-免安装落地-e-盘)
4. [实操第 1 步：锁死 E 盘路径并启动服务](#4-实操第-1-步锁死-e-盘路径并启动服务)
5. [实操第 2 步：下载 Qwen2.5-3B 模型与落地校验](#5-实操第-2-步下载-qwen25-3b-模型与落地校验)
6. [实操第 3 步：显存压测与单条冒烟校验](#6-实操第-3-步显存压测与单条冒烟校验)
7. [实操第 4 步：创建轻量独立评测 Python 环境](#7-实操第-4-步创建轻量独立评测-python-环境)
8. [实操第 5 步：运行阶段一 74 条锚定集自动评测](#8-实操第-5-步运行阶段一-74-条锚定集自动评测)
9. [实操第 6 步：阶段二 定向混淆扩展集与配对检定](#9-实操第-6-步阶段二-定向混淆扩展集与配对检定)
10. [实操第 7 步：实验停止、环境复原与零残留验证](#10-实操第-7-步实验停止环境复原与零残留验证)

---

## 1. 实验底数与环境红线

在执行任何命令前，必须确认以下事实底数：
* **硬件环境**：RTX 4060 Laptop（物理显存 8188 MiB），Windows 操作系统；
* **磁盘空间**：E 盘剩余空间 $> 100\text{GB}$，**全部工具、模型、日志强制写入 `E:\modelTest`**；
* **测试底盘**：`tests/` 目录现存 **801 条收集（793 passed / 3 skipped / 5 xfailed）**，全仓 807 条。实验全程绝不改变现有 Python 依赖，单测结果保持完全一致；
* **源码隔离**：绝不修改 `ai-module/core/**` 业务代码，绝不修改 `.env` 配置文件。

---

## 2. 工作区目录物理结构

工作区已于 `E:\modelTest` 初始化就绪：

```
E:\modelTest\
├── bin/                 # 独立推理运行时程序 (Ollama Windows 二进制)
├── models/              # 模型权重与 manifests (OLLAMA_MODELS 锁死重定向至此)
├── venv_eval/           # 独立微型 Python 评测环境 (只装轻量调用库，无 torch)
├── configs/             # 环境变量与启动脚本
├── scripts/             # 评测流水线、数据构建与配对统计脚本
├── data/                # 阶段一 74 条锚定集 & 阶段二 定向扩展集
├── outputs/             # 原始模型生成结果与检查点（Checkpoint）
├── logs/                # 运行日志（专设 fallback_guard.log 监控事故）
└── reports/             # 最终对比报表与 McNemar 统计检定书
```

---

## 3. 实操第 0 步：独立推理引擎安装（Ollama 免安装落地 E 盘）

为彻底绕开 Windows + Python 3.13 下 PyTorch/CUDA 的编译地狱，我们直接采用纯 C++ 编译的独立轻量推理运行时（Ollama）。

### 3.1 下载 Ollama 二进制至 `E:\modelTest\bin`
在 PowerShell 中执行以下命令（全自动下载官方最新版 Windows 可执行程序）：

```powershell
# 1. 切换到实验目录
cd E:\modelTest

# 2. 从官方下载 Windows 最新安装包至 bin 目录
$installerPath = "E:\modelTest\bin\OllamaSetup.exe"
if (-not (Test-Path $installerPath)) {
    Write-Host "[正在下载 Ollama Windows 安装包...]" -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installerPath
}

# 3. 执行静默安装（或解压），锁定至 E 盘
# 注：Ollama 安装程序支持静默提取，若直接运行，可在安装后将可执行文件统一软链接或迁移至 E:\modelTest\bin
```
*(注：如果遇到网络较慢，可使用预打包便携 zip 直接解压至 `E:\modelTest\bin`)*

---

## 4. 实操第 1 步：锁死 E 盘路径并启动服务

**核心防偷跑设计**：Ollama 默认会把几十 GB 的模型缓存在 `C:\Users\用户名\.ollama`。我们必须通过环境变量**强行锁死在 E 盘**。

### 4.1 创建启动配置脚本 `E:\modelTest\configs\start_ollama.ps1`
已固化环境变量启动命令：

```powershell
# E:\modelTest\configs\start_ollama.ps1
$env:OLLAMA_MODELS = "E:\modelTest\models"       # 强制模型全部保存在 E 盘
$env:OLLAMA_HOST   = "127.0.0.1:11434"           # 绑定本地回环端口
$env:OLLAMA_KEEP_ALIVE = "10m"                   # 空闲保活时间

Write-Host ">>> 正在启动本地模型推理服务 (存储目录: $env:OLLAMA_MODELS)..." -ForegroundColor Green
& "E:\modelTest\bin\ollama.exe" serve
```

### 4.2 验证后台服务健康状态
在另一个终端运行：
```powershell
curl http://127.0.0.1:11434
# 正常应返回: "Ollama is running"
```

---

## 5. 实操第 2 步：下载 Qwen2.5-3B 模型与落地校验

### 5.1 拉取 4-bit 量化基座模型
使用以下命令拉取我们选型的黄金评测模型 **`qwen2.5:3b`**（官方 4-bit 量化版本）：

```powershell
# 指定模型目录并拉取
$env:OLLAMA_MODELS = "E:\modelTest\models"
& "E:\modelTest\bin\ollama.exe" pull qwen2.5:3b
```

### 5.2 验证磁盘落地位置（确认 0 污染 C 盘）
执行校验：
```powershell
# 1. 确认模型列表
& "E:\modelTest\bin\ollama.exe" list

# 2. 检查 E:\modelTest\models 实际占用（预期约为 2.0GB ~ 2.4GB）
Get-ChildItem -Path "E:\modelTest\models" -Recurse | Measure-Object -Property Length -Sum | Select-Object @{Name="TotalSize(GB)";Expression={[math]::Round($_.Sum / 1GB, 2)}}

# 3. 检查 C 盘用户目录是否被污染（必须为空或不存在）
Test-Path "$env:USERPROFILE\.ollama\models"  # 必须返回 False
```

---

## 6. 实操第 3 步：显存压测与单条冒烟校验

### 6.1 显存基线与加载后占用测量
在模型运行前后，执行 `nvidia-smi` 记录显存：

```powershell
nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv
```
* **基线预期**：系统常态底噪约 $1.0\text{GB} \sim 1.5\text{GB}$；
* **加载模型后**：总显存占用应在 **$3.2\text{GB} \sim 3.8\text{GB}$** 左右；
* **安全余量**：距离 8GB 上限保有整整 **$4.0\text{GB}+$**，绝对不会触发 Windows DWM 抖动或 CPU Offload。

### 6.2 单条业务语句冒烟测试（OpenAI 兼容接口协议测试）
用项目里的真实隐患语句做一次非侵入式探测：

```powershell
$headers = @{"Content-Type" = "application/json"}
$body = @{
    model = "qwen2.5:3b"
    messages = @(
        @{role = "system"; content = "你是一个安全隐患分析助手，请严格以 JSON 格式输出。"},
        @{role = "user"; content = "人行道盲道被共享单车和摊位完全堵死，属于什么隐患？"}
    )
    temperature = 0.3
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:11434/v1/chat/completions" -Method Post -Headers $headers -Body $body
```
* **验证点**：1~2 秒内成功返回有效 JSON，首字延迟 $< 500\text{ms}$。

---

## 7. 实操第 4 步：创建轻量独立评测 Python 环境

为了完全隔离主项目，我们在 `E:\modelTest\venv_eval` 建立独立的微型运行环境：

```powershell
# 1. 在 E 盘建立全新轻量 venv（绝不干扰现有 801 条单测依赖）
python -m venv E:\modelTest\venv_eval

# 2. 激活微型环境
E:\modelTest\venv_eval\Scripts\Activate.ps1

# 3. 仅安装轻量无编译依赖（体积仅约 200MB）
pip install requests openai pandas tqdm tabulate
```

---

## 8. 实操第 5 步：运行阶段一 74 条锚定集自动评测

### 8.1 注入“防静默回退”与“本地端口重定向”环境变量
在当前评测会话中执行：

```powershell
# 核心防御：主模型与备用模型强制同名锁死为本地模型！
$env:MIMO_BASE_URL = "http://127.0.0.1:11434/v1"
$env:MIMO_API_KEY = "ollama"
$env:MIMO_MODEL = "qwen2.5:3b"
$env:MIMO_MODEL_BACKUP = "qwen2.5:3b"  # 剥离线上回退路径

# 评测日志重定向
$env:EVAL_OUTPUT_DIR = "E:\modelTest\outputs\phase1_raw"
$env:EVAL_LOG_DIR = "E:\modelTest\logs"
```

### 8.2 启动自动化评测执行器
执行脚本：
```powershell
E:\modelTest\venv_eval\Scripts\python.exe E:\modelTest\scripts\phase1_anchor_eval.py --samples 3
```

* **运行机制**：
  1. 依次执行 74 条黄金用例（64 正 + 10 负），每条重复采样 3 次（共 222 次调用）；
  2. 实时断点续存：每跑完 1 条立刻写入 `outputs/phase1_raw/checkpoint.jsonl`，中途随时可按 Ctrl+C，再次启动自动秒级恢复；
  3. 异常实时分流：如果模型返回空、超时或格式破损，单列记录为 `format_error` 或 `infra_error`，绝不混淆为正常分类判错；
  4. 系统兜底监控：统计每个样本是否触发了系统后处理规则，计算两套指标：
     * **裸模型原生准确率（Raw Accuracy）**
     * **系统护栏承托后准确率（System Accuracy）**

### 8.3 结果判读与阶段分叉
脚本运行完毕后，自动在终端与 `reports/phase1_anchor_report.md` 输出三口径结果：
* 轮间极差（Spread）
* 样本级二项 95% CI（$n=192$）
* 题目级二项 95% CI（$n=64$）

对照预注册阈值：
* 若小类准确率降幅 $\le 3\text{pt}$，且原生 JSON 成功率 $\ge 98\%$ $\rightarrow$ **进入阶段二**；
* 若降幅严重超出预期 $\rightarrow$ **直接出具详尽的失败用例诊断归因报表，圆满收工**。

---

## 9. 实操第 6 步：阶段二 定向混淆扩展集与配对检定

若阶段一达标，无缝启动阶段二进行显微镜级别的深度下钻：

### 9.1 生成定向混淆用例（128~192 条）
```powershell
E:\modelTest\venv_eval\Scripts\python.exe E:\modelTest\scripts\phase2_builder.py
```
* 针对三大混淆对（危房/墙裂、污水/积水、其他/占道）定向注入成对测试样例；
* 注入 15 条类内伪隐患样本（商场室内损坏等）。

### 9.2 双跑配对推断并生成 McNemar 显著性检验
```powershell
E:\modelTest\venv_eval\Scripts\python.exe E:\modelTest\scripts\phase2_extended_eval.py
```
* 本地 4B 与云端 MiMo 双跑同一批扩展集；
* 输出 McNemar 统计量 $\chi^2$ 与伴随概率 $p$ 值；
* 输出 Discordant 清单（提取全部“MiMo 对但 4B 错”的疑难 case）。

### 9.3 生成双盲文本抽样评审单
```powershell
E:\modelTest\venv_eval\Scripts\python.exe E:\modelTest\scripts\make_blind_samples.py
# 输出 E:\modelTest\reports\blind_review_sheet.md
```

---

## 10. 实操第 7 步：实验停止、环境复原与零残留验证

评测结束后，关闭所有后台服务并验证宿主机状态：

```powershell
# 1. 停止 Ollama 后台进程
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue

# 2. 检查环境变量：关闭或重启终端后，临时环境变量自动消失

# 3. 验证主项目单测底牌依然全绿（确保 0 污染）
cd E:\java\newProject
python -m pytest ai-module/tests -q
# 必须依然显示: 801 collected (793 passed, 3 skipped, 5 xfailed)

# 4. 若需彻底清理 E 盘空间：
# 仅需删除 E:\modelTest 文件夹，电脑即刻 100% 恢复初始状态
```
