# Task035 Phase B estimator 定义与解析 fixture

## 1. 范围与结论边界

本文件区分 NumPy/small-matrix algebraic precursor 与真实 DOLFINx Nédélec fixture。
两类 fixture 都不是目标光栅，不求解 Task035 PDE，不选择 adaptive mesh backend，
也不把任何方法提升为 production default。所有复数量使用 Hermitian 内积；
cell 汇总只归约标量平方和，并以 global cell ID 排序，不使用 full-vector gather。

原 precursor 状态为：R1、R3、R5、G1、G2、B1、M1 =
`algebraic_precursor_pass`，R2 = `resolution_diagnostic_pass`，R4 =
`formula_defined`。真实 B1 periodic Nédélec 和 B2 flat-lossy-layer/official-goal
最低 Gate 已通过。Review V3 的 Phase C/D 已完成；B3/B4 通过，但 target estimator 与
production mesh backend 均受控判负，未提升 ordinary default。

## 2. 公共残差分解

对单元 K，定义非负局部平方指标

$$
\eta_K^2 = \eta_{K,\mathrm{curl}}^2 + \eta_{K,\mathrm{div}}^2
+ \eta_{K,\mathrm{jump}}^2 + \eta_{K,\mathrm{mat}}^2
+ \eta_{K,\mathrm{DtN}}^2 + \eta_{K,\mathrm{Floquet}}^2
+ \eta_{K,E_t}^2 + \eta_{K,H_t}^2.
$$

代码中的八个稳定 component name 分别为
`volume_curl_residual`、`scalar_divergence_residual`、`curl_flux_jump`、
`material_interface_term`、`external_dtn_boundary_term`、
`floquet_pair_residual`、`hybrid_interface_et_residual` 和
`hybrid_interface_ht_residual`。全局量为
$\eta=(\sum_K\eta_K^2)^{1/2}$；复数范数始终计算
$r^HWr$，不使用无共轭转置。

## 3. 候选定义

| ID | 定义 | Phase B 状态 | 限制 |
|---|---|---|---|
| R1 | 上述 volume/face/interface/boundary residual 平方和 | `real_fe_fixture_pass_B1_B2` | B1/B2 已装配真实 UFL form；目标光栅 screen 尚未运行 |
| R2 | $\chi_K=|k|h_K/p_K$ resolution diagnostic | `resolution_diagnostic_pass` | 不修改 R1 marking 权重，不是 formal estimator |
| R3 | $\eta_K=\|G_hE_h-E_h\|_K$；材料界面使用 coefficient-aware recovery | `algebraic_precursor_pass` | 真实 B3 尚未完成 |
| R4 | patch constrained minimization 的目标定义；当前仅验证局部 SPD correction precursor | `formula_defined` | 尚未实现约束平衡与 guaranteed bound |
| R5 | 局部 enriched space 中解 $A_K e_K=r_K$，$\eta_K^2=e_K^HA_Ke_K$ | `algebraic_precursor_pass` | 当前 $A_K$ 仍为小矩阵 precursor |
| G1 | $\eta_J=|z^Hr|$，目标为 total R/T/A | `algebraic_precursor_pass` | 正式离散 adjoint 尚未完成 |
| G2 | 同一 DWR 形式，目标为 R00_s、R00_p 与显著 order amplitude | `real_fe_goal_derivative_pass_B2` | B2 使用实际 FE 零级反射 functional；正式离散 adjoint 尚未完成 |
| B1 | DtN truncation 与 spatial residual 分开记录 | `real_fe_boundary_perturbation_pass_B2` | 尚未选择目标光栅真实截断阶数 |
| M1 | internal-mode truncation 与 spatial residual 分开记录 | `algebraic_precursor_pass` | 真实 B4/QEP/Hybrid 尚未完成 |

多目标组合采用 $\sum_j |w_j|\,|\eta_{J_j}|$，权重和目标名称必须精确匹配。
error split 的 `estimator_total` 只包括 spatial、DtN truncation 和 internal-mode
truncation；`qep_eigen_residual_diagnostic` 不混入 spatial error。

## 4. 四类 fixture 与负向扰动

| Fixture | 正向 Gate | 故意破坏 | 结果 |
|---|---|---|---|
| NumPy homogeneous periodic precursor | 手工 complex residual 与 scalar reduction | face orientation、Floquet phase | `algebraic_precursor_pass` |
| NumPy flat-layer goal precursor | complex weighting 与线性 goal derivative | 手工 DtN trace | `algebraic_precursor_pass` |
| real B1 periodic Nédélec | hexahedral N1curl p1/p2；实际 UFL volume/jump；p2 field error 由 $6.08\times10^{-2}$ 降至 $1.69\times10^{-3}$ | orientation、phase | serial/MPI2 identity，`real_fe_fixture_pass` |
| real B2 lossy layer | piecewise-complex DG0；三个实际 h/p 点；field error 由 0.173 降至 0.00224；R1 由 9.46 降至 0.593；零级反射 goal 达机器精度 | external DtN operator perturbation | serial/MPI2 identity，`real_fe_official_goal_fixture_pass` |
| real B3 material corner | actual Nédélec、DG0 tags、16 interface facets、p1/p2 enriched proxy | material tag fault | serial/MPI2 identity，`component_fixture_pass` |
| measured B4 Hybrid | accepted target Et/Ht、M80/120/160、matched-trace QEP | DtN operator perturbation | serial/MPI2 identity，`component_fixture_pass` |

R/T/A 的中心有限差分方向导数与解析导数最大绝对差为
$1.51\times10^{-10}$。这是复数状态上的实值线性 functional 检查，独立于
DWR 实现；DWR 另由直接 `numpy.vdot` 共轭参考检查。

## 5. Gate 与下一阶段约束

- B1/B2 的 finite/nonnegative、实测 refinement trend、负向扰动、canonical ID、
  serial/MPI2 scalar reduction 与复数共轭检查均通过；
- B1/B2 真实 Gate 的强制 identity 为 serial/MPI2；旧 precursor 的 MPI4 仅为 algebraic component check；
- `phase_b_real_fixture_minimum_gate = pass`，`phase_c_low_cost_unlocked = true`；
- B3/B4 为 `component_fixture_pass`，R4 维持 research `formula_defined`；
- target artifact screen 已运行 sampled R1、discrete two-level R5 proxy、DtN split 与 R2 diagnostic；
- R5 proxy correlation 为 0.989–0.998，但不是 formal hierarchical FE R5；
- sampled R1 correlation 为负，实际 strip/tensor PDE 对照也失败，因此
  `production_estimator_selected = false`；
- Phase D 的 tetra control 通过，但 hexa locality 与 strip physical gates 未通过，因此
  `production_backend_selected = false`、`phase_e_unlocked = false`。

目标 artifact screen 明确使用 Task034 accepted fields 与 p4/h5 best-available discrete reference，
不把后者称为 continuum truth。sampled R1/R5 只用于低成本排序和 backend engineering；不得替代
cell-integrated FE residual、actual enriched local solve 或 discrete adjoint。R2 永远排除出 marking。
Review V3 未授权的 target adaptive cycle、真实 p4 heavy PDE 与 ordinary-default change 均未执行。

实现见 `src/validation/task035_hcurl_estimator_fixtures.py`，runner 见
`benchmarks/task035_estimator_fixtures.py`；真实 FE 实现和 runner 分别见
`src/validation/task035_real_fe_fixtures.py` 与
`benchmarks/task035_real_fe_fixtures.py`。compact records 见 Case094 `records/`。
