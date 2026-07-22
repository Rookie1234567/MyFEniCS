# Task035 Phase B estimator 定义与解析 fixture

## 1. 范围与结论边界

本文件只定义 estimator 数学接口并记录 analytic/manufactured fixture。
这些 fixture 不是目标光栅，不调用 DOLFINx PDE，不选择 adaptive mesh backend，
也不把任何方法提升为 production default。所有复数量使用 Hermitian 内积；
cell 汇总只归约标量平方和，并以 global cell ID 排序，不使用 full-vector gather。

当前总体状态为 `fixture_pass`。R1、R2、R3、R5、G1、G2、B1、M1
得到 `fixture_pass`；R4 只有局部 SPD precursor 与公式，保持
`formula_defined`，不得解读为 equilibrated guarantee 或 time-harmonic qualification。

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
| R1 | 上述 volume/face/interface/boundary residual 平方和 | `fixture_pass` | 尚未装配真实 UFL form |
| R2 | $\chi_K=|k|h_K/p_K$，$\eta_K^{R2}=\eta_K^{R1}/\sqrt{1+\chi_K^2}$ | `fixture_pass` | 只验证 resolution-aware scaling，不构成高频可靠性证明 |
| R3 | $\eta_K=\|G_hE_h-E_h\|_K$；材料界面使用 coefficient-aware recovery | `fixture_pass` | 只在制造 jump fixture 验证 |
| R4 | patch constrained minimization 的目标定义；当前仅验证局部 SPD correction precursor | `formula_defined` | 尚未实现约束平衡与 guaranteed bound |
| R5 | 局部 enriched space 中解 $A_K e_K=r_K$，$\eta_K^2=e_K^HA_Ke_K$ | `fixture_pass` | 当前 $A_K$ 为 Hermitian positive-definite analytic fixture |
| G1 | $\eta_J=|z^Hr|$，目标为 total R/T/A | `fixture_pass` | goal derivative 为解析线性 surrogate |
| G2 | 同一 DWR 形式，目标为 R00_s、R00_p 与显著 order amplitude | `fixture_pass` | 尚未接入真实 diffraction postprocess |
| B1 | DtN truncation 与 spatial residual 分开记录 | `fixture_pass` | 未选择真实截断阶数 |
| M1 | internal-mode truncation 与 spatial residual 分开记录 | `fixture_pass` | QEP eigen residual 仅作 diagnostic，不计入 spatial estimator |

多目标组合采用 $\sum_j |w_j|\,|\eta_{J_j}|$，权重和目标名称必须精确匹配。
error split 的 `estimator_total` 只包括 spatial、DtN truncation 和 internal-mode
truncation；`qep_eigen_residual_diagnostic` 不混入 spatial error。

## 4. 四类 fixture 与负向扰动

| Fixture | 正向 Gate | 故意破坏 | 结果 |
|---|---|---|---|
| homogeneous periodic analytic field | exact residual $3.17\times10^{-15}$；MPI1/2/4 global sum 都为 0.1；canonical IDs `[3,7,19,41]` | face orientation、Floquet phase | 均被检测，`fixture_pass` |
| flat lossy layer / modal surrogate | complex weighting；R/T/A directional derivative；均匀加密序列 0.2 至 0.0125 | DtN trace | defect 0.0721，`fixture_pass` |
| material interface manufactured corner | exact interface 与 coefficient-aware recovery 为 0；anisotropic ranking 稳定 | material tag、naive cross-material recovery | defect 分别 0.2406、0.7211，`fixture_pass` |
| Hybrid analytic interface | exact Et/Ht 为 0；spatial、DtN、M、QEP 分列 | Et/Ht trace | defect 分别 0.0361、0.0412，`fixture_pass` |

R/T/A 的中心有限差分方向导数与解析导数最大绝对差为
$1.51\times10^{-10}$。这是复数状态上的实值线性 functional 检查，独立于
DWR 实现；DWR 另由直接 `numpy.vdot` 共轭参考检查。

## 5. Gate 与下一阶段约束

- finite/nonnegative、exact-zero、refinement trend、负向扰动、canonical ID、
  serial/MPI2/MPI4 scalar reduction 与复数共轭检查均通过；
- R4 不满足“受约束 equilibrated patch”资格，维持 `formula_defined`；
- 尚无 real-case screen、adaptive cycle、真实 p4、heavy PDE 或 mesh backend 结论；
- Phase C 只能从已通过 fixture 的方法开始低成本 bake-off，并继续把 R4 当作
  未完成研究项。

实现见 `src/validation/task035_hcurl_estimator_fixtures.py`，runner 见
`benchmarks/task035_estimator_fixtures.py`，compact record 见 Case094
`records/fixture_summary.json`。
