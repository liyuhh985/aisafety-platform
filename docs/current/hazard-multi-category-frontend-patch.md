# 前端补丁：工单支持多个隐患类别（列表 / 地图筛选 / 详情）

> 状态：current（2026-10-14）
> 适用文件：`src/constants/hazardTaxonomy.js`、`src/views/HazardListView.vue`、
> `src/views/MapPage.vue`、`src/views/HazardDetailView.vue`
> 后端已上线：工单表新增 `hazard_types` 列并回填存量；建单消息新增 `categoryList`；
> 列表/详情接口的 VO 多返回一个 `hazardTypes` 字段。
> 背景（产品口径）：处置团队按「全能型」处理，**不按类别派单** —— 所以一张工单可以同时
> 包含多个隐患类别（最多 3 条）。地图/列表按大类筛选时，**这张单在涉及的每个大类下都要出现**。

## 1. 契约

| 字段 | 位置 | 说明 |
|------|------|------|
| `hazardType` | 工单对象 | **主类别**，canonical `major_code/subcategory_code`。语义没变，别改它的用法 |
| `hazardTypes` | 工单对象 | **全部类别**，英文逗号分隔（如 `municipal/manhole_damage,fire/fire_equipment_fault`），最多 3 条，第一条恒等于 `hazardType`。老数据可能为空/null |

要点：`hazardTypes` 里的每一项格式与 `hazardType` **完全一样**（都是 `major/sub`），
所以现成的 `resolveHazard()` 直接能吃，不需要新的解析器。

## 2. `constants/hazardTaxonomy.js`（改一处，列表页和地图页共用）

- 新增 `resolveHazardList(raw)`：按英文逗号切开 → 逐项 `resolveHazard` → 去掉空项与重复项；
  `raw` 为空时回退成 `[raw_hazardType]` 的单元素数组（兼容老数据）。
- `matchHazardFilter(taskType, filterMajor, filterSub)` **签名不变**（列表页 `HazardListView.vue`
  和地图页 `MapPage.vue` 都在调它），只把内部判定改成「**列表里任一命中即命中**」：

```js
export function matchHazardFilter(taskType, filterMajor, filterSub) {
  if (!filterMajor || filterMajor === 'all' || filterMajor === '全部') return true
  // 支持逗号分隔的多类别：任一命中即算命中
  const raw = String(taskType || '')
  const parts = raw.includes(',') ? raw.split(',') : [raw]
  return parts.some((one) => {
    const r = resolveHazard(one.trim())
    if (r.majorCode !== filterMajor) return false
    if (!filterSub || filterSub === 'all' || filterSub === '全部') return true
    return r.subcategoryCode === filterSub
  })
}
```

## 3. 三个页面的调用点

- 列表页 `HazardListView.vue`（约 1123 行）：把 `item.hazardType` 换成 `item.hazardTypes || item.hazardType`。
- 地图页 `MapPage.vue`（约 445 行）：同样换成 `item.hazardTypes || item.hazardType`。
- 地图 marker 上色仍用**主类别** `item.hazardType`（一张单一个 marker，不要按类别画多个）；
  抽屉/弹窗里的类别文字改成显示全部（见下）。
- 明细/徽章：把只显示一个类别的地方改成显示全部，建议主次分明：
  「市政设施 · 井盖破损 ＋1」或两行列出；`formatCategory()` 保持对单值的兼容。

## 4. 验收清单

1. 一张单含 `municipal/…` + `fire/…` 时：地图筛「消防安全」**和**筛「市政设施」都能搜到**同一张单**。
2. 单类别工单的显示与筛选**与改动前完全一致**。
3. 存量工单（`hazardTypes` 已回填）行为不变；若接口给的是 null，走 `hazardType` 回退。
4. 二级小类筛选：按小类筛时，这张单只在小类命中时才出现（另一个类别的小类不应误命中）。
5. 详情页能看到这张单包含的全部类别。
