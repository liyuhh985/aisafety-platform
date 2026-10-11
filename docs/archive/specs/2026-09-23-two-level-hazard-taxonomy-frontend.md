> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Two-Level Hazard Taxonomy Frontend Specification

## Purpose

This document is the frontend contract for the two-level hazard taxonomy. It is written so a separate frontend implementation can be completed without reading the AI backend source.

The frontend selects a major hazard category as context. The AI backend decides the detailed subcategory, facts, and whether the problem is safe to route into retrieval, reporting, or task creation.

## Canonical Taxonomy

Use these exact codes in requests, filters, and persisted display mapping. Labels are for display only and may change without changing codes.

```js
export const HAZARD_TAXONOMY = [
  {
    code: "traffic",
    label: "交通与通行",
    subcategories: [
      { code: "road_occupancy", label: "占道经营/乱堆乱放" },
      { code: "vehicle_occupancy", label: "车辆占道" },
      { code: "blind_path_occupied", label: "盲道占用" },
      { code: "traffic_facility_damage", label: "交通设施损坏" },
    ],
  },
  {
    code: "municipal",
    label: "市政设施",
    subcategories: [
      { code: "manhole_damage", label: "井盖缺失/破损" },
      { code: "road_surface_collapse", label: "路面塌陷" },
      { code: "drainage_flood", label: "排水/积水" },
      { code: "street_light_pole", label: "路灯/线杆损坏" },
    ],
  },
  {
    code: "fire",
    label: "消防安全",
    subcategories: [
      { code: "fire_lane_blocked", label: "消防通道占用" },
      { code: "fire_equipment_fault", label: "消防设施故障" },
      { code: "fire_water_abnormal", label: "消防水源异常" },
    ],
  },
  {
    code: "building",
    label: "建筑安全",
    subcategories: [
      { code: "dangerous_building", label: "危房" },
      { code: "wall_crack_lean", label: "墙体开裂/倾斜" },
      { code: "facade_fall", label: "外立面脱落" },
      { code: "falling_object", label: "高空坠物" },
      { code: "illegal_structure", label: "违规搭建" },
    ],
  },
  {
    code: "utility",
    label: "电气与燃气",
    subcategories: [
      { code: "exposed_wire", label: "裸露/老化电线" },
      { code: "distribution_box_fault", label: "配电设施故障" },
      { code: "illegal_wiring", label: "私拉乱接" },
      { code: "gas_leak", label: "燃气泄漏" },
      { code: "gas_pipe_aging", label: "燃气管道老化" },
    ],
  },
  {
    code: "construction",
    label: "施工安全",
    subcategories: [
      { code: "no_barrier", label: "未设置围挡" },
      { code: "no_warning", label: "无安全警示" },
      { code: "scaffold_guard", label: "脚手架/临边防护" },
      { code: "deep_pit", label: "深基坑风险" },
      { code: "temporary_power", label: "施工临时用电" },
    ],
  },
  {
    code: "elevator_special",
    label: "电梯与特种设备",
    subcategories: [
      { code: "elevator_trapped", label: "电梯困人" },
      { code: "elevator_stopped", label: "停运/异响" },
      { code: "elevator_inspection", label: "超期未检" },
    ],
  },
  {
    code: "environment_other",
    label: "环境与其他",
    subcategories: [
      { code: "garbage_pile", label: "垃圾堆积" },
      { code: "sewage_odor", label: "污水/异味" },
      { code: "other", label: "其他" },
    ],
  },
];
```

Do not duplicate category labels and subcategory lists in multiple Vue components. Put them in one frontend module, for example `src/constants/hazardTaxonomy.js`.

## UI/UX

The filter is two-level.

```text
一级：
全部 | 交通与通行 | 市政设施 | 消防安全 | 建筑安全 |
电气与燃气 | 施工安全 | 电梯与特种设备 | 环境与其他

选中“消防安全”后，二级出现：
全部 | 消防通道占用 | 消防设施故障 | 消防水源异常
```

Required behavior:

- `全部` on level one shows every task.
- Selecting a level-one category filters by major code.
- Selecting a level-two category filters by both major and subcategory code.
- Changing the level-one category resets the level-two selection to `全部`.
- If no level-two match exists, show an empty state and a clear reset action.
- On small screens, level one is horizontally scrollable; level two may be a horizontal chip row or a compact select.

Chat input behavior:

- Above the chat input, show the selected major category as a removable chip: `消防安全`.
- Add a `不确定，自动判断` option that sends no major code.
- The selected major is a hint and must not block the backend from resolving a different major.
- If the backend reports a different resolution, show a small non-blocking banner:

```text
已按“消防安全 / 消防设施故障”记录
[接受] [修改类别]
```

Do not ask the user to choose both levels before sending a message.

## API Contract

### Assistant stream request

The frontend calls the existing Java endpoint:

```text
POST /api/ai/assistant/stream
Content-Type: multipart/form-data
```

Fields:

| Field | Required | Meaning |
|---|---|---|
| `message` | yes, unless file only | User text |
| `session_id` | no | Conversation session |
| `file` | no | Optional image |
| `selected_major_code` | no | Major-code hint from the frontend, or empty |

Example:

```text
message=三明市万达广场对面的消防设施过于老旧，无法正常使用
session_id=8f3...
selected_major_code=fire
```

If `selected_major_code` is absent or invalid, the backend must treat it as `自动判断`.

### SSE events

Existing event types remain:

```text
status | chunk | done | error
```

The backend may additionally emit one optional taxonomy event after understanding:

```json
{
  "type": "taxonomy",
  "content": {
    "selected_major_code": "fire",
    "major_mismatch": false,
    "issues": [
      {
        "major_code": "fire",
        "major_label": "消防安全",
        "subcategory_code": "fire_equipment_fault",
        "subcategory_label": "消防设施故障",
        "confidence": 0.95
      }
    ]
  }
}
```

Frontend rules:

- Ignore the event when a client cannot consume it.
- When present, replace the removable major chip with the resolved labels.
- When `major_mismatch` is true, show the non-blocking confirmation banner.
- When multiple issues are present, render one compact tag per issue.

### Task payload display

New task records store `hazardType` as:

```text
<major_code>/<subcategory_code>
```

Example:

```text
fire/fire_equipment_fault
traffic/vehicle_occupancy
```

Treat `hazardType` as a display code. Do not assume it is one of four Chinese words.

The list/detail resolver must:

1. Split a new value on `/`.
2. Resolve the major label and subcategory label from `HAZARD_TAXONOMY`.
3. Fall back to the legacy mapping below for old records.
4. Fall back to the raw value when no mapping exists.

## Legacy Mapping

Old records may still contain the four old values or the earlier consultation values.

| Legacy value | Major code | Subcategory code |
|---|---|---|
| `占道` | `traffic` | `road_occupancy` |
| `井盖/道路` | `municipal` | `manhole_damage` |
| `消防通道` | `fire` | `fire_lane_blocked` |
| `消防设施` | `fire` | `fire_equipment_fault` |
| `危房` | `building` | `dangerous_building` |
| `高空坠物` | `building` | `falling_object` |
| `电气` | `utility` | `exposed_wire` |
| `施工` | `construction` | `no_barrier` |
| `其他` | `environment_other` | `other` |

Old rows do not need a database migration for this phase. Resolve them in the frontend adapter and in the backend compatibility helper.

## Filter Matching

Given a task:

```js
const [majorCode, subcategoryCode] = String(task.hazardType || "").split("/");
```

Rules:

- Major filter matches when the resolved major code equals the selected major code.
- Subcategory filter matches only when both codes equal the selected codes.
- Legacy values are first converted through the legacy mapping.
- `全部` is the only filter that matches unknown raw values.

## Acceptance Criteria

- The frontend uses one shared taxonomy module.
- The chat request can send an optional `selected_major_code`.
- `不确定，自动判断` sends no major code.
- The task list supports a major filter and a subcategory filter.
- New `major/subcategory` values display their labels.
- Legacy values from the table above display their new labels.
- Unknown values display the raw value and do not crash the page.
- A taxonomy event with multiple issues renders multiple tags.
- A major mismatch is displayed as a non-blocking suggestion, not a modal.
- Mobile layout remains usable with horizontal chip scrolling.

## Out Of Scope

- Changing the AI streaming transport.
- Replacing the existing report page or task-detail workflow.
- Adding database columns for major and subcategory in this phase.
- Changing task status transitions.
