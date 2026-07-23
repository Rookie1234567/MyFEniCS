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
production mesh backend 均未提升 ordinary default。Review V4 后 pure R5 production marking
受控判负，actual R/T DWR 在限定高阶点形成 research positive。

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

## 6. Actual discrete adjoint、DWR 与 marking policy

对 official real-valued goal `R_total` 或 `T_total`，实现从零级 modal amplitude 解析构造状态梯度
`g`，并解离散共轭转置系统

$$
A^H z=g.
$$

资格化同时检查 full explicit primal residual、`A^H z-g` true adjoint residual、解析梯度与中心
有限差分、以及 midpoint identity。对于本问题的 quadratic R/T，global correction identity 接近 1
是代数性质，不单独证明局部 marking 有效；局部指标由 correction field 与 adjoint sensitivity 的
cell/face contribution 形成，最终价值必须由 refine 后 official observable error reduction 和 uniform
control 判断。

Dörfler 排序使用 canonical global cell ID，并把最小前缀 cutoff 附近 relative `1e-10` 内的非负
等值贡献全部纳入。record 同时保存 `minimal_count_before_tie_expansion`、
`cutoff_tie_expansion_count`、cutoff、容差、global-ID hash 与 geometry hash。该 policy 消除了明确
cutoff tie 的任意截断，但不能消除不同高阶并行解中大于 tolerance 的微小 cell contribution 漂移：
p2/p3 serial/MPI identity 仍要求 exact hash；三个独立 p3/p4 MPI8 runs 的 215-cell sets 则实测
pairwise Jaccard `214/216=0.9907407`，故高阶 repeat Gate 是逐次 hash-bound 且 overlap ≥0.99，
不得把 `tie_stable` 文件名解释为 exact repeat hash。

固定 Task034 geometry、S、10° grazing 的 measured 选择为：

| route | decision |
|---|---|
| pure global R5 correction-energy marking | 收敛但被 cost-matched uniform level2 显著击败；diagnostic only |
| p2/p3 R-total DWR one cycle | p2 微弱正信号、p3 明显落后 uniform1；mixed，不选择 |
| p3/p4 R-total DWR, theta=0.5, one cycle | p4 在更少 DoF 下击败 uniform1；selected research strategy |
| 同路线第二 cycle | 继续收敛但被 structured p4/h7.5 在误差/DoF/内存上支配；controlled negative |
| theta=0.3 one cycle | DoF 节省很小、误差 2.30 倍；controlled negative |

因此当前停止规则是一次 `theta=0.5` tetra local refinement。R2 仍不进入 marking，p4/h5 仍只称
best-available discrete reference。该结论尚未跨 robust angle、P 入射或 Hybrid 验证，故
`production_estimator_selected=false`、`production_backend_selected=false` 和 ordinary default 不变。

## 7. Review V5：tolerance-normalized multi-goal 与 h/p classifier

新增 research-only marker `tolerance_normalized_R_T`。它继续分别求解 `R_total` 和
`T_total` 的真实离散伴随，再按已接受的 structured p4/h7.5 相对 p4/h5 离散参考的分量误差
冻结归一化尺度：

| observable | absolute tolerance |
|---|---:|
| `R_total` | `3.61556382344661e-05` |
| `T_total` | `2.477575966640666e-04` |
| `A_volume_total` | `2.1160195840952412e-04` |

每个 cell 的组合指标定义为

$$
\eta_K^{multi} =
\sqrt{\left(\frac{\eta_{K,R}}{\tau_R}\right)^2+
      \left(\frac{\eta_{K,T}}{\tau_T}\right)^2}.
$$

`A_volume_total` 继续进入最终 `(R,T,A_volume)` 向量审计；当前 qualified field 满足
`R+T+A_volume=1`，且尚未实现独立的 volume-absorption goal gradient，所以不伪造第三个独立
伴随。record 明确保存该依赖关系、control/reference hash、三项 tolerance、canonical marker 与
geometry hash。原 `combined_relative_R_T` 与 ordinary default 均不改变。

新增 `src/adaptivity/hp_smoothness_classifier.py`，只对同一固定网格上的连续
`p4→p5`、`p5→p6` goal-indicator correction 做候选分类：

$$
\rho_K = \frac{\eta_K^{p5\to p6}}{\eta_K^{p4\to p5}}.
$$

`rho_K <= 0.5` 视为快速 p-decay 的 `p_candidate`，更慢的衰减视为 `h_candidate`，两级 correction
都低于全局显著性 floor 时为 `undetermined`。该 classifier 只输出 canonical-cell decision，
不创建 variable-p space、不改变 mesh，也不提升 production；真实 cell-level p4/p5/p6 验证仍需
同一 mesh 的两组 local indicator snapshot。

h37.5 formal run 的初始 normalized 与 R-only marker 都是同一 98-cell set，所以允许的一次
refinement 没有产生新 mesh；refined-mesh 的只读 estimator evaluation 才分化为 655 与 687
cells。该证据说明 tolerance normalization 已实际参与排序，但当前一次-h合同下分类为
`controlled_neutral_identical`，不得据此启动第二次 h 或宣称 multi-goal 优于 R-only。
