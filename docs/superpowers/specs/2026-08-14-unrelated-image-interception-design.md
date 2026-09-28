# 无关图片拦截设计

## 目标

将明显与安全隐患无关的图片在视觉识别阶段结束，避免后续检索和报告生成浪费资源或编造内容；对不确定的图片保持继续分析，优先降低漏报风险。

## 决策

视觉模型返回 JSON 中的 `has_hazard` 是唯一的拦截信号。编排器仅在值严格为布尔值 `False` 时提前结束；字段缺失、`null`、非布尔值或视觉解析失败都不得拦截，沿用既有流程。这个不对称判断确保模型输出不完整或边界不清时仍会进入检索和报告。

统一提示词定义为 `ai-module/prompts.py` 的 `VISION_PROMPT`，`ai-module/agents/vision_agent.py` 只导入并使用它。提示词的 JSON 契约包括：`has_hazard`、`confidence`、`hazard_category`、`severity`、`description`、`reason_if_no_hazard`、`location_hint`、`rectification`。

提示词约束如下：

- 仅当图片明显无关（例如人像、风景、动物、纯文字）时允许 `has_hazard=false`。
- `has_hazard=false` 必须说明 `reason_if_no_hazard`。
- 模棱两可时必须返回 `has_hazard=true`、`hazard_category="其他"`、`confidence="低"`。
- 移除“图片中一定有某种安全相关问题”的旧约束。

## 数据流

流式 `Orchestrator.analyze_stream` 在视觉结果已成功解析且发出既有 `vision` 事件后，若 `has_hazard is False`，依次发出：

1. `no_hazard`，内容为 `reason_if_no_hazard`，无理由时为空字符串。
2. `done`。

然后立即返回，不调用 router、检索器或 report agent。该路径不写入报告或检索记忆。

非流式 `Orchestrator._run_pipeline` 在保存 `results["vision"]` 后执行相同判断。命中时设置 `results["early_exit"] = "no_hazard"` 并返回，不调用 router、检索器或 report agent。

## 范围

本次交付修改 Python 提示词、视觉 Agent、编排器，并添加聚焦的编排器单元测试。前端展示 `no_hazard` 提示和 `force_continue` 需要跨服务接口和产品交互决策，明确不在本次实现范围内。评估集也不随本次实现创建。

## 测试与验收

- 流式：视觉结果为 `has_hazard=false` 时，事件序列为 `status`、`vision`、`no_hazard`、`done`，检索和报告均未调用。
- 非流式：相同输入返回 `vision` 和 `early_exit=no_hazard`，检索和报告均未调用。
- fail-safe：视觉 JSON 缺失 `has_hazard` 时，流程继续到检索和报告。
- 运行新增测试及既有流式编排器测试，避免重复运行不受影响的整套测试。

## 评估集原则

评估集的图片类别和期望标签应由人工标注，至少覆盖明确无关、明确相关与边界图片。模型只负责在固定评估集上批量推理，系统据人工真值计算误拦截率与漏拦截率；同一个模型不能同时产出预测和作为判定预测正确与否的唯一依据。
