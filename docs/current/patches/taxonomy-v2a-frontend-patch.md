# 前端补丁：Taxonomy v2a 29 类硬切换

> 状态：current
> 最后核对：2026-11-27
> 标准补丁：`docs/superpowers/patches/2026-11-27-hazard-taxonomy-v2a-frontend.patch`

## 变更范围

- 从 `.frontend-work/src/constants/hazardTaxonomy.js` 移除 3 个退役小类：
  - `fire_water_abnormal`（消防水源异常）
  - `wall_crack_lean`（墙体开裂/倾斜）
  - `facade_fall`（外立面脱落）
- 保留目标类的既有编码与中文名：
  - `fire_equipment_fault` / 消防设施故障
  - `dangerous_building` / 危房
  - `falling_object` / 高空坠物
- 不在写路径的 `LEGACY_HAZARD_MAP` 中为退役 3 类增加静默 alias。

## 交付文件

- `docs/superpowers/patches/2026-11-27-hazard-taxonomy-v2a-frontend.patch`
  - 修改 `hazardTaxonomy.js`
  - 新增 Node 单测 `hazardTaxonomy.test.mjs`
  - 新增 Vue SFC 编译校验脚本 `compileHazardTaxonomyConsumers.mjs`

## 验证命令

```powershell
node --test .frontend-work/test/hazardTaxonomy.test.mjs
node .frontend-work/test/compileHazardTaxonomyConsumers.mjs
```

期望：4 个 Node 测试通过，5 个引用 `hazardTaxonomy.js` 的 `.vue` 文件均完成 SFC parse、script compile 与 template compile。

## 部署边界

`.frontend-work/` 被 `.gitignore` 忽略，因此真实交付以仓库内 tracked unified diff 为准；不得只保留工作副本。
