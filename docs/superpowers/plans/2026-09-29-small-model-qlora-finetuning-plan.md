# 本地 3B 小模型 QLoRA 微调与三臂对比实验执行手册 (阶段 B)

**文档版本**：v1.0 (已执行完成并完成同标尺复测)  
**制定日期**：2026-09-29  
**实验状态**：已执行闭环 (实测获得 +15.1 pt 净增益)  
**工作目录**：`E:\modelTest`  
**核心目标**：基于阶段 A 测出的 **58.3% 基线（口语 51.1% 断层）**，利用项目 231 条真实案例数据构建领域 SFT 训练集，在单卡 RTX 4060 (8GB) 上进行 QLoRA 微调，验证“微调能否大幅拉齐小模型与云端 MiMo (93.8%) 的差距”，并产出终极三臂对比成果。

---

## 目录
1. [三臂对照实验架构设计](#1-三臂对照实验架构设计)
2. [硬件预算与 QLoRA 技术选型](#2-硬件预算与-qlora-技术选型)
3. [训练集工程：数据提炼与防泄露机制](#3-训练集工程数据提炼与防泄露机制)
4. [环境准备：训练虚拟环境部署 (E:\modelTest\venv_train)](#4-环境准备训练虚拟环境部署)
5. [QLoRA 训练执行与超参数配置](#5-qlora-训练执行与超参数配置)
6. [权重导出与推理引擎挂载 (GGUF/Ollama)](#6-权重导出与推理引擎挂载)
7. [终极三臂复测与成果交付](#7-终极三臂复测与成果交付)

---

## 1. 三臂对照实验架构设计

本次实验形成严格的闭环三臂矩阵：

```
[第一臂：天花板] 云端商业 API (MiMo-v2.6-flash) ───────────────> 基准: 93.8% (已实测)
[第二臂：裸底座] 本地原生小模型 (Qwen2.5-3B-Instruct 4bit) ────> 基线: 58.3% (已实测)
[第三臂：微调态] QLoRA 领域微调后 (Qwen2.5-3B + SFT LoRA) ────> 目标: 85%+ (本次实验)
```

### 核心论证逻辑：
* 如果没有第二臂的 58.3%，第三臂的 85% 无法证明是微调带来的增益；
* 正因为阶段 A 铁证了裸模型只有 58.3% 且口语只有 51.1%，阶段 B 的微调才能清晰量化出 **+25~30 pt 的巨大净收益**。

---

## 2. 硬件预算与 QLoRA 技术选型

在 RTX 4060 Laptop (8GB 显存) 硬约束下，参数与显存精细预算：

| 模块 | 方案 / 选型 | 显存占用预算 |
| :--- | :--- | :--- |
| **基座模型** | `Qwen2.5-3B-Instruct` (BitsAndBytes 4-bit NF4 量化) | 约 2.2 GB |
| **训练模式** | **QLoRA** (冻结 4bit 主干，仅训练 LoRA 适配器权重) | 约 150 MB (参数量 ~16M) |
| **优化器** | `paged_adamw_8bit` (自动在 CPU/GPU 内存间分页换出，杜绝 OOM) | 约 400 MB |
| **激活值缓存** | 开启 **Gradient Checkpointing** (计算换显存，极度省显存) | 约 800 MB |
| **Batch 策略** | `per_device_train_batch_size = 1`, `gradient_accumulation_steps = 4` | 控制上下文峰值 |
| **系统常驻** | Windows 桌面与基础底噪 | 约 1.5 GB ~ 2.0 GB |
| **训练峰值总显存** | **预计 5.2 GB ~ 6.0 GB** | **低于 8.0 GB 上限，完全安全** |

---

## 3. 训练集工程：数据提炼与防泄露机制

### 3.1 真实数据源
* 源文件：`ai-module/db/data_cases.py`、`data_cases_batch2.py`、`data_cases_batch3.py`
* 语料基础：231 条涵盖全国真实处罚与隐患整改案例。

### 3.2 训练样本格式（Alpaca / ChatML 标准格式）
每条训练样本包含指令、输入描述与目标严格 JSON：

```json
{
  "instruction": "你是一个城市公共空间安全隐患助手。请严格输出 JSON，格式为: {\"major\": string, \"subcategory\": string}。",
  "input": "长峰医院住院部自动报警系统和喷淋管网故障，水阀关闭无法联动。",
  "output": "{\"major\": \"fire\", \"subcategory\": \"fire_equipment_fault\"}"
}
```

### 3.3 绝对安全防线（防考卷泄露）
* **红线**：阶段一跑过的 **74 条基准集（`eval_queries.py`）严禁以任何形式混入训练集**；
* 训练集生成脚本自动计算 Jaccard / 编辑距离，剔除任何与 74 条基准用例相似度 $> 0.6$ 的样本，确保三臂评测具有绝对客观效度。

---

## 4. 环境准备：训练虚拟环境部署 (`E:\modelTest\venv_train`)

由于训练需要用到 `torch`、`peft`、`transformers`、`bitsandbytes`，为了**坚决不污染现有的微型评测环境（venv_eval）和主项目 801 条单测**，我们在 `E:\modelTest` 创建专门的微调环境：

```powershell
# 1. 建立独立微调虚拟环境
python -m venv E:\modelTest\venv_train

# 2. 安装 CUDA 加速版 PyTorch 与微调工具链
E:\modelTest\venv_train\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
E:\modelTest\venv_train\Scripts\pip install transformers datasets peft bitsandbytes accelerate trl
```

---

## 5. QLoRA 训练执行与超参数配置

### 5.1 核心超参数配置 (`E:\modelTest\configs\train_qlora_config.json`)
* **LoRA Rank ($r$)**：`16`
* **LoRA Alpha ($\alpha$)**：`32`
* **LoRA Dropout**：`0.05`
* **目标模块 (Target Modules)**：`["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]`
* **学习率 (Learning Rate)**：`2e-4` (带余弦退火)
* **训练轮数 (Epochs)**：`3`
* **最大序列长度 (Max Seq Length)**：`512` (隐患描述短文本，极大节约显存)

### 5.2 启动训练命令
```powershell
E:\modelTest\venv_train\Scripts\python.exe E:\modelTest\scripts\train_qlora.py
```
* 实时监控：终端输出 Loss 下降曲线与当前显存峰值；
* 检查点存放在：`E:\modelTest\outputs\qlora_adapter`。

---

## 6. 权重导出与推理引擎挂载 (GGUF/Ollama)

训练完成后，适配器权重体积仅约 **30 MB**。将其合并并导入推理端：

1. **导出合并模型**：将 LoRA 权重与 4-bit 基座合成为完整权重或直接导出 GGUF；
2. **构建 Modelfile 并注册到 Ollama**：
   ```dockerfile
   FROM E:\modelTest\models\qwen2.5-3b-q4.gguf
   ADAPTER E:\modelTest\outputs\qlora_adapter
   TEMPLATE ...
   ```
3. **注册新模型**：`ollama create qwen2.5:3b-finetuned -f Modelfile`。

---

## 7. 终极三臂复测与成果交付

### 7.1 执行同标尺复测
将评测脚本环境变量切换为微调模型：
```powershell
$env:MIMO_MODEL = "qwen2.5:3b-finetuned"
$env:MIMO_MODEL_BACKUP = "qwen2.5:3b-finetuned"
python E:\modelTest\scripts\phase1_anchor_eval.py --samples 3
```

### 7.2 交付成果
自动生成《终极三臂对比成果复盘大表》并更新入原项目方案：
* 给出三臂柱状图数据；
* 重点检验：**老百姓口语化表述（`colloquial`）是否成功从 51.1% 修复至 80%+**；
* 重点检验：三大混淆对是否成功解离。
