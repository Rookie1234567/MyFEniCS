# 2D Floquet、PML 与端口弱式

## TM scattered

`solve_vector_maxwell.run_case`：

1. 检查 complex scalar 与 TM；
2. `build_mesh`，创建 `N1curl` 空间；
3. 构造目标/背景 epsilon 和 `E_background`；
4. `build_floquet_constraints`；
5. 物理区装配 curl-curl，PML 区装配变换张量；
6. RHS 为 `k0^2*(eps-eps_bg)*E_background`；
7. manual `C^HAC`/SuperLU 或 dolfinx_mpc/PETSc；
8. `E_total=E_background+E_scat`；
9. 场、RTA、mismatch 输出。

`_solve_manual` 是串行参考；`_solve_mpc/_solve_mpc_auto` 是分布式路径。manual 与 MPC 结果一致性属于约束验证，不是 PML 收敛证明。

## TE scattered

`solve_te_maxwell.run_te_case` 用 Lagrange 标量空间，梯度弱式和 scalar PML coefficient。`build_scalar_floquet_constraints` 约束节点标量相位。H/Poynting 由 `Ez` 导数重构。

## Robin total field

`solve_port_maxwell.run_port_case` 和 `solve_te_maxwell.run_te_port_case` 在上下物理边界加局部 impedance/Robin 项，并在 top 加入射 source。port 路径禁止 PML，避免只有物理 cells 装配而 PML DOF 未约束。

## 2D PML API

| 函数 | 数学对象 |
|---|---|
| `_pml_coordinate` | 复坐标继续 |
| `_pml_tensors_from_coordinate_map` | TM Maxwell epsilon/mu tensors |
| `_scalar_pml_coefficients_from_coordinate_map` | TE gradient/mass coefficients |
| `top_*`, `bottom_*` | 分别延拓 air/substrate |

## Floquet API

constraint 对象保存 slave/master、coefficients、orientation、pairing/probe error。`dof_trace_mismatch` 在解后重算。3D 与 2D constraint 数据结构不同，不应跨模块直接复用。

方程见 theory `maxwell_strong_weak_and_fem.md` 与 `pml_robin_and_open_boundaries.md`。
