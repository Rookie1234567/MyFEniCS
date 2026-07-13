# 3D 网格、双 Floquet 与 PML

本文解释 3D mesh 如何对齐材料面，Nedelec trace 如何施加 x/y Bloch 相位，以及 z-PML 如何进入弱式。

## 1. 网格对象与入口

```text
geometry/mesh_builder_3d::build_airbox_mesh_3d(cfg,out_dir) -> AirBox3DMesh
```

`AirBox3DMesh` 保存 distributed mesh、cell/facet tags、resolved cell counts、spacing mode、轴统计、材料面对齐报告和 z alignment warnings。`HexaAxisPlan` 保存 x/y/z 坐标数组、refinement region 与 required planes。

Stage4 在生成 cell 前把 interface、grating 六个面、physical/PML 边界加入 required planes。`_material_plane_alignment_report` 检查每个材料面是否恰为网格面；未对齐意味着一个 cell 横跨材料跃变，不能由小 residual 弥补。

## 2. 轴规划与分布

| 函数 | 输入/输出 |
|---|---|
| `_stage4_required_planes_by_axis(cfg)` | 各轴必须包含的命名坐标 |
| `_stage4_axis_plan(cfg,comm_size)` | uniform/boundary-fitted/local-refined 轴 |
| `_structured_hexa_mesh(...)` | distributed hexa mesh |
| `_rank_cell_ids(total,rank,size)` | 连续 global cell id ownership |
| `_mark_cells/_mark_boundary_facets` | distributed tags |

轴数组长度分别为 `nx+1,ny+1,nz+1`，cell 总数为 `nx*ny*nz`。每个 rank 只构造分给自己的 global cell id；DOLFINx 再建立 ghost topology。配置和轴统计可复制，mesh entity 不可按串行 NumPy 索引假设全局存在。

## 3. Double Floquet 数据

```text
constraints/floquet_3d::build_double_floquet_mpc(
    V, mesh_data, cfg, log=None
) -> DoubleFloquet3DData
```

返回对象包括 `mpc`、x/y/corner 约束统计、phase/orientation 诊断和回代所需数据。Bloch 条件是

$$E(x+L_x,y,z)=e^{ik_xL_x}E(x,y,z),\qquad
E(x,y+L_y,z)=e^{ik_yL_y}E(x,y,z).$$

p=1 通过 topology edge DoF 匹配；p=2 还需 edge/face trace moment 变换。corner 同时跨 x/y，系数必须是两相位乘积且不能重复约束。

## 4. 公式到约束代码

| 数学动作 | 代码锚点 |
|---|---|
| 找周期 boundary edge/face | `_periodic_boundary_edges/_periodic_boundary_faces` |
| 建 global entity records | `_build_topological_edge_context/_build_topological_trace_context_p2` |
| p2 orientation/trace transform | `_edge_transform_p2/_face_transform_p2` |
| 发出 slave-master rows | `_emit_block_constraint_rows` |
| 合并 x/y/corner | `_merge_constraint_data_blocks` |
| 创建 MPC | `build_double_floquet_mpc` |

Nedelec orientation 会产生符号或小型复 transform，不能只按几何最近点复制 coefficient。`_validate_owned_constraint_coverage` 在 MPI 上检查 owned slave 是否恰好被覆盖。

## 5. PML 公式和代码

z 向复坐标拉伸设 `s_z=dz_tilde/dz`。对只沿 z 拉伸的 Maxwell 方程，变换介质张量为对角形式；代码入口是：

```text
common/pml_3d::z_stretch_derivative_value(z,cfg,side)
common/pml_3d::z_pml_diagonal_values(z,cfg,side,eps_background)
common/pml_3d::z_pml_tensors(x,cfg,side,eps_background)
```

第一个是可直接单测的标量参考，第二个返回解析 diagonal，第三个构造 UFL tensors。`common_3d_forms::_build_variational_forms` 在 top PML 使用 air epsilon，在 bottom PML 使用该 stage 的 substrate/background epsilon。

## 6. 弱式组合

Floquet 只处理 x/y trace；PML 只修改 z 外层 cell 的体积分。物理区仍使用原 `epsilon_r,mu_r`，PML 区使用 transformed tensors：

$$\int_{PML}(\mu_{pml}^{-1}curlE)\cdot\overline{curlv}
-k_0^2(\epsilon_{pml}E)\cdot\bar v\,dV.$$

PML 外表面按 stage 使用边界条件。Stage4 DtN 则完全不建立 PML cells，直接在 physical z faces 施加 modal operator。

## 7. 一次调用顺序

```text
run_stage2b_pml_airbox_3d_case
-> run_prepared_3d_case_flow
-> build_airbox_mesh_3d
-> _create_nedelec_space
-> build_double_floquet_mpc
-> _build_variational_forms with z_pml_tensors
-> dolfinx_mpc assembly/direct solve
-> MPC backsubstitution
-> field/PML decay diagnostics
```

Stage2A 跳过 PML tensors；Stage2C 增加平界面材料和背景源；Stage4A/B 把 z 开边界改为 DtN。

## 8. Shape 与 ownership

- axis coordinates 是 replicated 1D arrays；mesh cells、facets、tags 分布。
- `V` 是 3 分量 H(curl) 空间，但 DoF 不是“节点数 x 3”的简单乘积。
- MPC slave 数按 rank 局部统计并全局归约；constraint coefficients 与 owner 一起存活。
- constrained PETSc matrix 仍为 distributed sparse AIJ；项目不显式形成全局 `C^HAC`。
- p2 trace fit 只在边界 entity 上工作，不复制全局 FE matrix。

## 9. 输出与判读

summary 中应同时看：resolved `(nx,ny,nz)`、材料面对齐、global cells/DoF、Floquet constraint count、orientation/probe error、PML 参数、真残差和场衰减。只看 solver convergence 会漏掉网格跨材料或周期配对错误。

## 10. 测试、身份与限制

- `test_02_pml_tensor.py`：PML tensor 解析值。
- `test_05/06/12/17`：p1/p2 Floquet、orientation 和 PDE 行为。
- `test_15_stage4_hexa_mesh_spacing.py`：required planes 与 spacing。
- Case011：Stage2A test-backed；Case012/013：组合路径存在但精度仍 experimental。
- official：mesh/tag、MPC constraint、离散 residual；PML decay 是验证量。
- 限制：near-Rayleigh、极细局部 refinement 和新 cell type 仍需单独 MPI/精度验证。

理论见 [`../../theory/floquet_periodicity.md`](../../theory/floquet_periodicity.md) 与 [`../../theory/pml_robin_and_open_boundaries.md`](../../theory/pml_robin_and_open_boundaries.md)。
