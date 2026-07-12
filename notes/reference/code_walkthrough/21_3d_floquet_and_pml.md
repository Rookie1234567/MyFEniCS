# 3D 网格、Floquet 与 PML

## `mesh_builder_3d.py`

`HexaAxisPlan` 保存 x/y/z 坐标、spacing mode、材料面对齐报告和最终 cells。Stage 4 先列出 interface、grating 六个面、物理/PML 边界等 required planes，再按模式生成：uniform、boundary_fitted 或 local_refined 轴。

重要函数：

| 函数 | 作用 |
|---|---|
| `_stage4_required_planes_by_axis` | 材料/边界必需坐标 |
| `_stage4_axis_plan` | 解析 spacing、refinement、MPI 最小 cell 数 |
| `_structured_hexa_mesh` | 按全局 cell id 分配 rank |
| `_mark_cells/_mark_boundary_facets` | 生成物理 tags |
| `_material_plane_alignment_report` | 阻止跨材料 cell |
| `build_airbox_mesh_3d` | 唯一公共建网入口 |

## `floquet_3d.py`

`build_double_floquet_mpc` 读取 x/y facet tags、config phase 与阶次，建立一个 `MultiPointConstraint`。p=1 使用 topology edge；p=2 使用 trace moment 映射。返回数据含 slave 统计、corner/edge 诊断和重构工具，生命周期必须覆盖 assembly 与 solution backsubstitution。

## `pml_3d.py`

`z_stretch_derivative_value` 是可单测标量参考；`z_pml_diagonal_values` 给出解析 diagonal；`z_pml_tensors` 构造 UFL tensors。`common_3d_forms` 在 top PML 用 air epsilon，在有基座的 bottom PML 用 substrate epsilon。

## 组合边界

Floquet 作用 x/y；PML 或 DtN 作用 z。Stage 2A 的 z face 可用解析 Dirichlet/correction；Stage 4 DtN 不加 z Dirichlet。边界集合错误会产生封闭腔或 overconstraint，因此由 stage flow 集中决定。

## 证据

`test_02` 检查 PML tensor，`test_05/06/12/17` 检查 Floquet，`test_15` 检查 Stage4 mesh spacing，Stage 2 cases 011-013 记录组合行为。
