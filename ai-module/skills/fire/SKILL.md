---
name: fire
category: fire
description: 消防安全隐患，包括消防通道占用、消防设施/水源故障和电动自行车违规停放/充电。
allowed_tools:
  - search_regulation
  - search_cases
routing_keywords:
  - 消防通道
  - 消防设施
  - 消火栓
  - 灭火器
  - 防火门
  - 消防水源
  - 电动自行车
  - 飞线充电
  - 电池入户
version: "1"
---

# 消防安全

## 适用范围

覆盖 fire_lane_blocked、fire_equipment_fault（含消防水源异常）、ebike_hazard。

## 追问 SOP

- 消防通道占用优先确认 blocker 和 persistence。
- 消防设施/水源故障优先确认 facility_type 和 condition（含无水、无压、被埋压等状态）。
- 电动自行车隐患优先确认 hazard_mode 和 charging_state；飞线充电可并发 illegal_wiring。
- 每次只问一个 A 类槽位；多隐患时由代码统一组织并列追问。

## 法规引用约束

只使用检索结果中出现的法规和案例。
不得编造条款、处罚金额或责任主体。
正在燃烧、浓烟、人员被困等场景不得走普通报告链路。

## 报告约束

完整报告必须区分现场事实、法规依据和类似案例。
证据不足时不得写成确定性的违法结论。

## 建单注意事项

描述应包含隐患对象、当前状态和影响范围。
不得编造用户未描述的位置、楼层或人员伤亡信息。

## 危险升级与禁止行为

出现明火、浓烟、人员被困、燃气味或爆炸风险时，优先给出应急动作，不继续追问。