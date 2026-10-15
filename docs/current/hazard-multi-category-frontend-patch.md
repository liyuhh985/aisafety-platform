# 前端补丁：工单多类别同级展示、一级大类筛选与地图底图修复

> 状态：current
> 最后核对：2026-10-14
> 适用文件：`index.html`、`src/constants/hazardTaxonomy.js`、`src/views/HazardListView.vue`、`src/views/MapPage.vue`、`src/views/HazardDetailView.vue`、`src/views/HomeView.vue`

## 1. 核心原则（修正口径）

1. **多隐患工单与单类别工单完全一致，不造“多类别工单”特殊概念**
   - 一张多隐患工单（如包含井盖 + 消防）只是同时归属于多个类别，它与单类别工单没有任何其他区别。
   - **不显示** `+1` / `+N` 附加角标，**不区分**「主类别 / ↳ 副类别」。
   - 在列表页、地图抽屉、地图弹窗、详情页中，统一用 `resolveHazardList(item.hazardTypes, item.hazardType)` 解析出全部类别，并以**完全同级、相同样式的普通类别胶囊**并排展示。
2. **仅按一级大类筛选，不需要二级子类精准匹配**
   - 列表页与地图页只按一级大类（`majorCode`）过滤，只要工单所属的任意一个类别命中该一级大类即展示。
   - 移除 `HazardListView.vue` 中的「细分类型（二级子类）」筛选行，以及 `matchHazardFilter` 中的二级子类精准匹配逻辑。
3. **地图底图：矢量优先 + 栅格自动兜底（三套官方风格现已恢复）**
   - **当前形态（2026-10-14 晚，Key 白名单已配置后）**：
     - 首选高德 **WebGL 矢量渲染**，直接使用官方风格：`清新全彩 = amap://styles/macaron`、`极简浅白 = amap://styles/whitesmoke`、`深黑科技 = amap://styles/dark`；切换调用 `map.setMapStyle()`。
     - 加载 SDK 前先**预检矢量样式接口**（fetch `custyle.amap.com/.../getMergedStyleData`：返回 JSON 错误或超时视为不可用）：
       可用 → 保持 WebGL；不可用 → `window.forbidenWebGL = true` 降级为 DOM 栅格方案。
     - `index.html` **不再全局强制** `forbidenWebGL`；由 `MapPage.vue` 按预检结果决定。
   - **前提**：高德 Key 已在控制台配置域名白名单（`106.53.219.214`、`safety.onlyliyuu.online`、`onlyliyuu.online`、`www.onlyliyuu.online`）。缺白名单时矢量接口返回 `INVALID_USER_DOMAIN`，自动走栅格兜底。
   - **栅格兜底形态**（预检失败时）：
     - 清新全彩 = 彩色路网瓦片 `wprd` + `style=8`；极简浅白 = 原生浅色瓦片 `webrd` + `style=7`；深黑科技 = 彩色瓦片 + 滤镜 `invert(1) hue-rotate(180deg) brightness(0.92) contrast(1.05)`；
     - 切到/离开浅白时 `mapInstance.add/remove(TileLayer)` 更换瓦片源；首屏无瓦片时 `map.resize()` 自动重试；`visibilitychange` 回前台再 nudge 一次。
   - **历史根因（均已修复，供追溯）**：
     - 根因一：Key 未配白名单 → WebGL 矢量样式接口 `INVALID_USER_DOMAIN`，PBF 解析抛 `Unimplemented type: 3`，底图空白；
     - 根因二：DOM 默认 `webrd style=8` 浅色瓦片在低缩放级别近乎空白；
     - 根因三：Tailwind v4 preflight 的 `img,video{max-width:100%;height:auto}` 把瓦片 `<img>`（位于 0 宽绝对定位瓦片层内）压成 0 宽——切换风格后整片空白的主因。修复：`src/map-tile-fix.css`（`main.js` 引入）豁免 `.amap-layer img { max-width: none }`。
4. **UI 细节去 AI 味与双端适配**
   - 将散落在页面、弹窗、按钮中的粗糙 Emoji（`📍`、`📋`、`⚖️`、`⚠️`、`⏳`、`🔒`、`🏷️` 等）替换为干净统一的线性 SVG 图标，优化按钮与卡片排版，保持现有浅色磨砂视觉体系并兼顾桌面端与移动端体验。

---

## 2. `src/constants/hazardTaxonomy.js`

- `resolveHazardList(rawTypes, fallback)`：按英文逗号切分 → 逐项 `resolveHazard` → 去重去空；为空时回退 `fallback`。
- `matchHazardFilter(taskType, filterMajor)`：只判断一级大类是否命中（任一类别的 `majorCode === filterMajor` 即命中，忽略二级子类参数）：

```js
export function matchHazardFilter(taskType, filterMajor) {
  if (!filterMajor || filterMajor === 'all' || filterMajor === '全部') return true
  const raw = String(taskType || '')
  const parts = raw.includes(',') ? raw.split(',') : [raw]
  return parts.some((one) => {
    const r = resolveHazard(one.trim())
    return r.majorCode === filterMajor
  })
}
```

---

## 3. 页面改造要点

### 3.1 `index.html` 与各页面 `loadAMap`
- `index.html`：**不再**全局写 `window.forbidenWebGL`（否则会把所有页面强制成栅格渲染）。
- `MapPage.vue`：加载 SDK 前先调用 `probeVectorStyles()` 预检矢量样式接口——
  - 可用：保持 WebGL 矢量渲染，构造时传 `mapStyle: currentTheme.value`，切风格调 `map.setMapStyle()`（官方 macaron / whitesmoke / dark）；
  - 不可用：`window.forbidenWebGL = true` 后再加载 SDK，走栅格兜底（彩色路网瓦片 `wprd style=8`；浅白换原生浅色瓦片 `webrd style=7`；深黑叠滤镜），并启动首屏瓦片看门狗。
  - 已存在 `window.AMap`（被地图选点等页面先加载）时不再重复预检，直接沿用 SDK 实际渲染模式（`AMap.Browser.baseRender`）。
- `HomeView.vue` / `HazardDetailView.vue`：选点地图仍按原样先设 `window.forbidenWebGL = true`（栅格即可满足选点需求）；如 SDK 已由 /map 以矢量模式加载，则选点地图会直接复用矢量渲染。
- `src/map-tile-fix.css`（全局，经 `src/main.js` 引入）：豁免 Tailwind preflight 对地图瓦片的影响（矢量模式无瓦片图片，不影响；栅格兜底必需）：
  ```css
  .amap-layer img,
  .amap-marker img,
  .amap-info-card img,
  .amap-info-content img {
    max-width: none;
  }
  ```

### 3.2 `src/views/HazardListView.vue`
- 移除「细分类型」二级子类 Chips 筛选行。
- 工单卡片类别展示改为直接遍历 `resolveHazardList(item.hazardTypes, item.hazardType)`，并排渲染同级 `<span class="category-pill">{{ cat.displayText }}</span>`，移除 `+N` 徽章与 `getExtraCategoryCount` / `getExtraCategoryTitle`。

### 3.3 `src/views/MapPage.vue`
- 底部抽屉与地图 InfoWindow 弹窗中的类别展示改为并排渲染全部同级类别标签，移除 `+N` 徽章。
- 优化 InfoWindow 弹窗、Marker 样式与弹窗图标（用精致 SVG 替代 Emoji）。

### 3.4 `src/views/HazardDetailView.vue`
- 类别胶囊区域直接并排渲染 `allCategories` 中的每一项 `<span class="category-pill">{{ cat.displayText }}</span>`，去掉 `↳` 箭头及主副类别颜色区分。
- 选点地图弹窗与状态提示中的 Emoji 替换为线性 SVG 图标。

---

## 4. 验收清单

1. **地图底图正常显示**：打开 `/map` 底图瓦片完整加载，控制台无 `Unimplemented type: 3` 报错，三种底图风格切换正常，工单点位与弹窗正常展示。
2. **多类别工单任一命中检索**：包含市政井盖+消防的工单，在列表页和地图页筛选「市政设施」或「消防安全」时均能稳定检索到。
3. **多类别与单类别同级无差别展示**：列表页、地图页、详情页中，多隐患工单并排展示所属类别胶囊，无 `+1` 角标、无 `↳` 主副区分。
4. **无二级子类筛选**：列表页与地图页均仅按一级大类简洁筛选，存量老工单（`hazardTypes` 为空）平滑回退 `hazardType`。

---

## 5. 相对旧版口径的差异（追溯用）

| 项 | 旧口径（本次修改前的实现/文档） | 现口径 |
|---|---|---|
| 列表/地图类别展示 | 只显示主类别 + 蓝色 `+N` 角标 | 全部类别**同级等样**并排展示，无角标 |
| 详情页类别展示 | 主类别 + `↳` 副类别（主副颜色区分） | 全部类别同级等样并排展示，无 `↳` |
| 列表筛选 | 一级大类 + 二级「细分类型」级联，按小类精准匹配 | **仅一级大类**，任一类别命中即展示；级联二筛已移除 |
| 地图底图 | WebGL 矢量渲染，但 Key 未配白名单导致样式数据 403/空白；降级方案也有瓦片被 Tailwind preflight 压成 0 宽的 bug | **矢量优先**（官方 macaron/whitesmoke/dark）+ **栅格自动兜底**（预检失败时启用）+ `.amap-layer img { max-width: none }` 豁免 |
| 图标/排版 | 大量 Emoji 图标、部分挤行 | 统一线性 SVG 图标，桌面/移动双端适配 |

---

## 6. 验证记录（2026-10-14 线上）

- 通过真实建单链路创建多隐患工单 **#HAZ-10758**：经由与 AI 助手建单相同的入口
  `enqueue_hazard_create`（直接给定 `categoryList`，不经过 LLM 抽取）→ outbox → RabbitMQ → Java 消费，
  request 状态 `SUCCESS`，落库 `hazard_types = municipal/manhole_damage,fire/fire_equipment_fault`。
- 浏览器实测（`http://106.53.219.214:8081`）：
  1. `/hazard`：卡片并排显示「市政设施 · 井盖缺失/破损」与「消防安全 · 消防设施故障」，无 `+N` 角标；
     筛「市政设施」「消防安全」均可命中，筛「建筑安全」不误命中；页面无「细分类型」筛选行。
  2. `/hazard/10758`：详情页两个类别同级并排，无 `↳`、无主副颜色区分。
  3. `/map`：底图瓦片完整加载，控制台 0 报错；筛「消防安全」时抽屉与弹窗
     均显示该点位及两个类别标签。
- 底图瓦片样本实测（离线下载比对）：DOM 模式默认的 `webrd` + `style=8` 瓦片在低缩放级别几乎无路网
  内容（用户视角即"空白"）；`wprd` + `style=8` 为完整彩色路网。
- "切换风格后瓦片整片消失"根因定位：Tailwind preflight `img,video{max-width:100%;height:auto}` 使
  瓦片 `<img>`（内联 256px）在 0 宽绝对定位父层内被压成 0 宽；页面内合成同结构 DOM 实测：
  未豁免时 0 宽（复现）、豁免后保持 256px（修复生效）；线上入口 CSS 已包含 `.amap-layer img{max-width:none}`。
- **矢量风格恢复验证（2026-10-14 晚，Key 白名单配置后）**：
  - 预检：`custyle.amap.com/.../getMergedStyleData?styleid=macaron` 与 `o4.amap.com/style/...` 均返回
    `200 + application/x-protobuf`（此前为 `INVALID_USER_DOMAIN` JSON）；
  - `/map` 实测：`AMap.Browser.baseRender = "w"`（矢量渲染），容器无栅格滤镜主题类，WebGL canvas 存在；
  - 依次切换 浅白 / 深黑 / 全彩：`getMergedStyleData?styleid=whitesmoke|dark|macaron` 均 `200`，
    控制台 0 报错（原生官方风格生效）。
