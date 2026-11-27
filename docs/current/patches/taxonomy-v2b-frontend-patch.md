# 前端补丁：Taxonomy v2b 新增 4 类

> 状态：current
> 最后核对：2026-11-27
> 标准补丁：`docs/superpowers/patches/2026-11-27-hazard-taxonomy-v2b-frontend.patch`

- 新增 `fire/ebike_hazard`：电动自行车违规停放/充电
- 新增 `municipal/tree_fall_hazard`：树木倒伏/断枝风险
- 新增 `construction/confined_space`：有限空间作业风险
- 新增 `environment_other/hazmat_storage`：危化品/易燃易爆违规存运
- 前端 taxonomy 从 29 类扩展为 33 类，不引入静默兼容 alias。
- Node 测试与 5 个 Vue consumer 的 SFC 编译校验通过。
