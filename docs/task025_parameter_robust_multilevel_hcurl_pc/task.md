# CODEX TASK 20260710：parameter-robust multilevel H(curl) preconditioner

## 0. 任务名称

```text
Task025: Parameter-robust multilevel H(curl) preconditioner
for mesh / grazing-angle / wavelength sweeps
```

中文定位：

```text
面向网格收敛、掠入射角扫描和波长扫描的
参数鲁棒多层 H(curl) 预条件器与完整 augmented Maxwell 求解器
```

---

## 1. 任务背景

Task021–Task024 已经明确：

```text
1. DtN 主导慢模态识别稳定：top (0,0) s。
2. FE-response + auxiliary Schur 数学结构成立。
3. h=5 使用高质量 FE inverse 时可以达到 production-like residual，official R/T/A 与 direct 一致。
4. PETSc/MPI、解回填、R/T/A、低内存 CSR 导出和 manual FGMRES 验证均已打通。
5. h=2 的唯一核心瓶颈是：低内存、足够准确地近似 A_FE^{-1}。
6. plain ASM/ILU 与 block Jacobi 太弱；全局 LU/SPILU、local LU/MUMPS 或 full-p2 AMS/HX 太贵。
7. Task024 的 m=1 reduced FE-response 只是低内存可扩展性证据，不是完整求解器突破。
```

后续工程使用不只包含一个固定参数点。需要：

```text
- 改变有限元网格尺寸，完成 R/T/A 收敛性分析；
- 在掠入射范围内改变入射角；
- 改变波长以及随波长变化的材料参数；
- 在一系列参数点上重复求解；
- 尽量复用预条件器层级、patch、transfer、symbolic data 和上一个参数点的解。
```

因此 Task025 不允许只针对 `h=2, theta=80 deg, lambda=13.5 nm` 调出一组特例参数。目标是得到一套**规则固定、参数可更新、无需逐点人工调参**的迭代求解器架构。

ChatGPT 不创建分支。Codex 如需执行分支，应自行从合适 base 创建；不得修改 ordinary default solver。

---

## 2. 总体目标

Task025 的核心目标是：

```text
开发一个混合 p/h 多层 H(curl) FE 预条件器，
通过 PETSc FieldSplit/Schur 接入完整 FE + 80 auxiliary augmented system，
在 14 GB 内使目标模型 p=2 h=2 的完整 true residual 达到 <= 1e-6，
并完成 official R/T/A；
随后验证其对网格、掠入射角和波长变化的鲁棒性。
```

完整系统：

```math
\begin{bmatrix}
A_{FE}(h,\lambda,\theta) & C(\lambda,\theta) \\
D(\lambda,\theta) & A_{aux}(\lambda,\theta)
\end{bmatrix}
\begin{bmatrix}
x_{FE}\\x_{aux}
\end{bmatrix}
=
\begin{bmatrix}
b_{FE}\\b_{aux}
\end{bmatrix}.
```

其中：

```text
A_FE = H(curl) Maxwell FE block
A_aux = 80-mode DtN auxiliary block
C,D = FE 与 DtN modal coupling
```

Task025 只围绕“如何构造参数鲁棒、低内存的 A_FE^{-1} 近似”展开，不再进行无边界外层算法和普通 PC 全扫。

---

## 3. 必须保持的物理参考模型

参考点继续使用：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate / top air = 10 / 10 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s, E along y
reference wavelength = 13.5 nm
reference material n = 0.999002304859 + 0.00182649365j
boundary = double Floquet x/y + 80-mode auxiliary DtN
```

必须把以下参数变成显式输入，不得散落硬编码：

```text
mesh size / mesh level
polynomial degree
wavelength
material n(lambda)
theta_from_z
phi
polarization
Floquet phase
DtN order set / propagating classification
outer and inner solver profile
```

输出：

```text
outcomes/operator_parameterization.md
outcomes/parameter_schema.json
```

---

## 4. 鲁棒性的准确含义

本任务不假设迭代法天然对参数不敏感。参数变化会改变：

```text
k0 = 2*pi/lambda
curl-curl 与 mass 项相对强度
材料损耗
Floquet phase
DtN modal admittance
传播/倏逝衍射级集合
矩阵不定性和非 Hermitian 程度
```

Task025 所称参数鲁棒，是指：

```text
1. 不为每个 h/theta/lambda 人工换一套 solver；
2. 所有 case 使用同一 PC 架构和自动参数规则；
3. 迭代次数和内存随网格细化、角度和波长变化保持可控；
4. 不在某些掠入射或波长点突然完全失效；
5. 固定网格上的角度/波长扫描可以复用 hierarchy 和 topology data。
```

允许按无量纲量自动调整：

```text
k0*h
local material wavelength
polynomial degree p
coarse-grid points/elements per wavelength
```

但禁止逐 case 手动试出不同 overlap、omega、shift 或 solver tree 后再称为鲁棒。

---

## 5. 固定外层与分块架构

### 5.1 外层 Krylov

主线固定为 PETSc native：

```text
KSPFGMRES
right preconditioning
restart = 50 as initial default; 100 only as bounded comparison
explicit full true residual monitor
Krylov memory guard
```

备选仅允许：

```text
GCRO-DR / GCROT for parameter-sweep recycling
```

不得继续全扫 BiCGStab、TFQMR、普通 GMRES 等外层算法。COMSOL 的 TFQMR/GMRES 结果用于证明 GMG 结构有效，不意味着本任务必须复刻 TFQMR。

Task024 manual FGMRES 只保留为验证参考，不进入 production outer API。

### 5.2 FE/aux 分块

保留：

```text
PETSc PCFieldSplit + Schur
split 0 = FE unknowns
split 1 = 80 DtN auxiliary unknowns
```

auxiliary block 很小，应使用：

```text
explicit small dense/sparse exact solve
或精确小 Schur action
```

不得用 m=1 reduced approximation 替代完整 80-aux outer solve。

输出：

```text
outcomes/augmented_solver_architecture.md
outcomes/fieldsplit_index_validation.csv
```

---

## 6. COMSOL 参考与本任务的实现原则

用户的 COMSOL 扫描表明：

```text
direct MUMPS: peak about 22.99 GB
TFQMR + 5-level GMG: peak about 9.01 GB
GMRES + 5-level GMG restart 100: peak about 11.70 GB
```

成功 PC 的核心不是单独 SOR、Vanka、ILU 或 AMS，而是：

```text
5-level geometric multigrid
V-cycle
local/vector-aware pre/post smoothing
small coarse direct solve
```

Task025 不要求逐项复制 COMSOL 的内部实现，但必须复现三个原则：

```text
1. fine/local high-frequency error 由 H(curl) patch smoother 处理；
2. global low-frequency error 进入真正多层 coarse space；
3. direct solve 只出现在足够小的最粗层。
```

Task024 的 same-mesh `p2 -> p1 -> root SPLU` 不是完整 GMG，不能作为否定 GMG 的证据。

输出：

```text
outcomes/comsol_gmg_mapping.md
```

---

## 7. 决策漏斗总览

必须按顺序执行：

```text
A. 固化可复现 baseline 与统一预算
B. fine-level H(curl) patch smoother
C. p2 -> p1 transfer + p1 AMS/HX coarse correction
D. 若 C 不够，建立最小 3-level h-GMG
E. 接入完整 FieldSplit/Schur + 80 aux FGMRES
F. reference h=2 达到 production-like 后做参数鲁棒性矩阵
G. 参数扫描中加入 hierarchy reuse、warm start 和 recycling
H. 强 PC 成立后才研究 fine-level matrix-free
```

禁止：

```text
- 再次广泛扫描 plain ILU/Jacobi/ASM 参数；
- 继续 full-p2 AMS/HX；
- 继续 p1 root SPLU 作为唯一 coarse solve；
- 只增加 m=2/4 response columns 而 FE response 仍很弱；
- 在 h=2 production gate 前跑 h=1.5/h=1 production campaign；
- 用 improvement_vs_zero 作为成功指标。
```

---

## 8. Stage A：统一、严格的 baseline

必须从同一 runner、同一 operator 和同一 residual API 运行：

```text
1. PETSc FGMRES + Jacobi
2. GCROT/GCRO-DR + Jacobi, only if available in same API
3. Task024 MatNest + block Jacobi research baseline
4. h=5 LU-based FE-response/Schur reference
5. direct MUMPS reference where resource permits
```

比较条件必须统一：

```text
same mesh
same MPI ranks
same initial guess
same full true residual definition
same matvec count
same wall-time budget
same memory cap
```

统一残差：

```math
r_{true}=\frac{\|Ax-b\|}{\|b\|}.
```

输出：

```text
outcomes/equal_budget_baseline.csv
outcomes/baseline_true_residual_history.csv
outcomes/baseline_resource.csv
```

Task025 的 minimum signal 定义为：

```text
相对严格同预算 baseline 至少改善 2x。
```

---

## 9. Stage B：fine-level H(curl) patch smoother

这是第一项核心算法工作。

不得继续只使用 diagonal/block Jacobi。必须构造至少两类真正局部 patch：

```text
Candidate B1: edge-star patch
Candidate B2: vertex-star patch
Candidate B3 optional: element-star patch
Candidate B4 optional: z/slab/line patch for grazing propagation
```

实现优先级：

```text
PETSc PCPATCH if compatible with Nedelec/MPC ownership;
否则自定义 additive overlapping patch Schwarz。
```

每个 patch 内允许使用小型 dense/sparse LU，并缓存：

```text
patch topology
local dof map
local matrix sparsity
symbolic factorization
```

数值系数随 lambda/theta 更新时，只重建必须更新的 local numeric factors。

patch 必须正确处理：

```text
Nedelec edge orientation
Floquet MPC reduced ownership
complex coefficients / real split
MPI overlap and ghost dofs
```

### 9.1 单独测试的 RHS

至少测试：

```text
selected DtN response RHS C_j
physical FE RHS b_FE
random FE error vector
```

### 9.2 Stage B gate

一个固定成本 smoother cycle 必须满足：

```text
selected response cancellation < 0.15，目标 < 0.10
physical FE residual reduction >= 2x
random-vector residual reduction >= 1.5x
peak RSS < 8 GB on h=2
```

必须明显优于 Task024 block Jacobi。

输出：

```text
outcomes/patch_design.md
outcomes/patch_topology_statistics.csv
outcomes/patch_smoother_ablation.csv
outcomes/patch_response_quality.csv
outcomes/patch_mpi_consistency.csv
```

若所有 patch 均不能优于 Jacobi 20%，停止盲目调 patch 参数，转入阻尼/shifted local operator 诊断。

---

## 10. Stage C：p2 -> p1 + p1 AMS/HX coarse correction

复用 Task024 已验证的 H(curl) p1->p2 transfer，但必须重新确认当前参数化 operator 下：

```text
adjoint identity
orientation consistency
Floquet phase consistency
MPI ownership
```

推荐结构：

```text
p2 patch pre-smooth
-> restrict to p1 same-mesh space
-> p1 AMS/HX one or a few cycles
-> prolongate
-> p2 patch post-smooth
```

关键要求：

```text
1. 不让 p1 AMS/HX 内层求解到收敛；只做 1-3 次固定 coarse correction。
2. hierarchy 构造一次并复用。
3. 正确提供 discrete gradient / coordinates / interpolation data。
4. 使用独立 PETSc options prefix。
5. 避免 Task018/019 的 repeated setup/destroy 和 communicator lifecycle 问题。
```

### Stage C gate

相对仅 patch smoother：

```text
response cancellation 至少再降低 30%
或完整 FE residual 至少再降低 2x
peak RSS < 12 GB
coarse setup 可复用
```

输出：

```text
outcomes/p_transfer_validation.csv
outcomes/p1_ams_hx_design.md
outcomes/p1_ams_hx_lifecycle.csv
outcomes/p_multilevel_response_quality.csv
outcomes/p_multilevel_resource.csv
```

如果 p1 AMS/HX 不产生明显收益，不继续增加其 inner iterations；转入 Stage D。

---

## 11. Stage D：最小 3-level h-GMG

只有 Stage C 未达到 FE PC gate 时启动。

最小层级建议：

```text
Level 0: p=2, h=2 nm fine
Level 1: p=1, h about 4 nm
Level 2: p=1, h about 8 nm or a mesh small enough for cheap direct solve
```

不要求一开始实现 5 层。只有 3 层产生正信号后才增加层数。

必须验证：

```text
H(curl) prolongation/restriction
commuting/adjoint consistency
Floquet phase on each level
material and geometry representation
rediscretized vs Galerkin coarse operator
coarse DtN/Floquet treatment
```

最粗层目标：

```text
small enough that MUMPS/LU is a small fraction of total memory
```

不得把 80k dofs 的 p1 system 称为最终 coarse level。

### Stage D gate

```text
one V-cycle FE residual reduction >= 3x
selected response cancellation < 0.05
peak RSS < 12 GB
coarse direct factor <= 25% total peak RSS
```

输出：

```text
outcomes/hierarchy_design.md
outcomes/h_transfer_validation.csv
outcomes/coarse_operator_comparison.csv
outcomes/vcycle_ablation.csv
outcomes/multilevel_response_quality.csv
outcomes/multilevel_memory_breakdown.csv
```

---

## 12. Stage E：完整 augmented solver 集成

只有 FE PC 单独达到以下条件才进入：

```text
selected response cancellation < 0.10
physical FE solve 相对 baseline 至少改善 2x
```

集成：

```text
PETSc FGMRES
+ FieldSplit/Schur
+ multilevel H(curl) FE PC
+ exact 80-aux small solve
```

selected FE-response columns 可作为：

```text
Schur enrichment
deflation vectors
optional coarse basis
```

但完整外层必须求解全部 FE 与 80 auxiliary unknowns。

输出：

```text
outcomes/full_augmented_solver_config.json
outcomes/full_augmented_true_residual_history.csv
outcomes/full_augmented_resource.csv
outcomes/aux_schur_diagnostics.csv
```

---

## 13. Stage F：reference production gate

先只使用参考点：

```text
p=2
h=2 nm
theta=80 deg
lambda=13.5 nm
```

分级 gate：

```text
minimum signal:
  relative equal-budget baseline improvement >= 2x

strong:
  full true residual <= 1e-2

engineering:
  full true residual <= 1e-4

production-like:
  full true residual <= 1e-6
```

Task025 reference-point 成功必须同时满足：

```text
full true residual <= 1e-6
peak RSS < 14 GB
official R/T/A available
|Delta R|, |Delta T|, |Delta A| <= 1e-6 or stricter against direct/reference
closure error <= 1e-6
MPI=1 and MPI=4 consistent
no per-case manual solver retuning
```

输出：

```text
outcomes/reference_h2_gate.csv
outcomes/reference_h2_official_rta.csv
outcomes/reference_h2_vs_direct.csv
outcomes/reference_h2_mpi_consistency.csv
```

在 reference production gate 通过前，不允许声称参数鲁棒 solver 完成。

---

## 14. Stage G：网格、角度和波长鲁棒性矩阵

只有 Stage F 通过后执行完整鲁棒性验证。

### 14.1 初始资格矩阵

最终范围必须来自用户工程需求并写入 `parameter_schema.json`。若尚未提供最终范围，使用以下 provisional qualification matrix：

```text
mesh h_nm = [5, 3, 2]
theta_from_z_deg = [75, 80, 85]
lambda_ratio = [0.9, 1.0, 1.1] relative to 13.5 nm
```

即 provisional wavelengths：

```text
[12.15, 13.5, 14.85] nm
```

这些值只用于 solver qualification，不代表最终工程扫描范围。材料必须通过 `n(lambda)` 参数接口更新，不允许固定 reference n。

为了控制成本，执行漏斗：

```text
G1: h=5 全 3x3 angle/wavelength smoke
G2: h=3 选择角落 + reference cases
G3: h=2 全 3x3 只在 G1/G2 全通过后执行
```

### 14.2 鲁棒性 gate

所有资格 case：

```text
100% convergence to <= 1e-6
同一 PC 架构和自动参数规则
无人工逐点改 solver tree
peak RSS < 14 GB for h=2 cases
```

迭代数鲁棒性目标：

```text
max outer iterations / min outer iterations <= 3
```

网格鲁棒性目标：

```text
h=5 -> h=2 outer iteration growth <= 3x
memory approximately proportional to FE unknowns, without factorization explosion
```

必须特别记录：

```text
propagating order changes
near-cutoff DtN modes
most grazing angle
shortest wavelength
least lossy material point
```

输出：

```text
outcomes/robustness_case_matrix.csv
outcomes/robustness_iteration_map.csv
outcomes/robustness_memory_map.csv
outcomes/robustness_failure_modes.md
outcomes/robustness_official_rta.csv
```

---

## 15. Stage H：参数扫描复用与 recycling

固定网格、改变 theta/lambda 时，优先复用：

```text
mesh topology and partition
patch index sets
p/h transfer operators
matrix sparsity patterns
symbolic patch/coarse factors
AMS/HX hierarchy topology, where mathematically valid
```

必须更新：

```text
mass/material coefficients
Floquet phase
DtN modal admittance and propagating classification
patch numeric matrices
coarse numeric operators
```

测试：

```text
previous solution warm start
previous Krylov/deflation space recycling with GCRO-DR/GCROT
selected response/coarse basis reuse
```

比较：

```text
first-case setup
subsequent-case numeric update
cold start vs warm start
with vs without recycling
```

输出：

```text
outcomes/parameter_reuse_design.md
outcomes/setup_reuse_benchmark.csv
outcomes/warm_start_benchmark.csv
outcomes/krylov_recycling_benchmark.csv
```

recycling 只能用于加速；不得用它掩盖基础 PC 在 cold start 下不收敛。

---

## 16. Stage I：网格收敛性工作流准备

Task025 需要提供自动网格收敛 harness，但物理解读必须与 solver convergence 区分。

对每个 `(theta, lambda)`：

```text
run mesh sequence
record k0*h, p, dofs, residual, iterations, RSS, R/T/A
compare R/T/A between successive meshes
identify numerical-convergence plateau
```

建议输出：

```text
outcomes/mesh_convergence_template.csv
outcomes/mesh_convergence_driver.md
```

必须区分：

```text
linear solver residual convergence
finite-element discretization convergence
energy closure
parameter sweep variation
```

不得用迭代残差小替代网格收敛证明。

---

## 17. Matrix-free 的进入条件

h=2 显式 PETSc matrix 当前仍可承受，因此 Task025 初期优先使用 assembled operator 以便开发强 PC。

只有在以下条件满足后才接 matrix-free：

```text
multilevel FE PC 已经达到 strong/engineering gate
或 h<2 显式 fine matrix 成为主要内存瓶颈
```

允许结构：

```text
matrix-free fine A_FE action
+ assembled patch/coarse operators
+ p/h multilevel PC
+ explicit small auxiliary Schur
```

禁止：

```text
matrix-free + weak/no inner PC
```

输出：

```text
outcomes/matrix_free_entry_decision.md
outcomes/matrix_free_multilevel_memory.csv
```

---

## 18. 文献和现有实现映射

Task025 必须先复用并更新：

```text
notes/theory/maxwell_iterative_preconditioners_task012.md
notes/theory/task021_dtn_auxiliary_schur_fe_response.md
notes/theory/task024_manual_fgmres_real_split_response.md
```

新增设计笔记：

```text
notes/theory/task025_parameter_robust_multilevel_hcurl_pc.md
```

必须至少覆盖：

```text
Hiptmair-Xu / AMS auxiliary-space preconditioning
p-multigrid for high-order H(curl)
geometric h-multigrid
edge/vertex/element patch smoothers
wave-number-aware / shifted local operators
coarse-space requirements for indefinite Maxwell
Krylov recycling for parameter sweeps
```

每个文献思想必须映射到：

```text
本项目中的 block
预期解决的误差类型
内存代价
参数依赖
可验证 gate
```

不得只做文献综述而没有 prototype 或 gate。

---

## 19. Gated fallback：方向型或 sweeping PC

如果完成 patch + p1 AMS/HX + 最小 h-GMG 后，reference h=2 仍不能达到 strong gate，则记录失败谱和残差空间，再单独建议下一任务研究：

```text
z-slab domain decomposition
impedance transmission conditions
sweeping / approximate block-LDU
moving-PML-like Schur approximation
```

Task025 不应在多层 H(curl) 主线尚未完成前同时全面开发 sweeping。

输出：

```text
outcomes/sweeping_fallback_trigger.md
```

---

## 20. 工程保底与直接法

必须保留：

```text
MUMPS / MUMPS-BLR / direct solver
```

作为：

```text
correctness reference
R/T/A reference
short-term engineering fallback
```

对固定 operator、多 RHS 或局部参数扫描可研究：

```text
factorization reuse
selected response cache
symbolic factor reuse
```

但不得把接近直接法成本的 fallback 包装成低内存 production PC。

---

## 21. 统一记录字段

每个 case 必须记录：

```text
git commit SHA
container image digest and package versions
h, p, theta, phi, lambda, material n
k0*h and local wavelength metric
MPI ranks
rows, nnz, n_FE, n_aux
outer KSP/restart/iterations/reason
FieldSplit/Schur options
patch type/count/size/overlap
p/h hierarchy sizes
AMS/HX setup/apply data
coarse solver and factor size
true residual history
R/T/A when qualified
setup time, solve time, update time
current and peak total RSS
failure stage
```

不得只报告 PETSc preconditioned residual。

---

## 22. 必须输出文件

```text
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/summary.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/parameter_schema.json
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/operator_parameterization.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/comsol_gmg_mapping.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/equal_budget_baseline.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/patch_design.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/patch_smoother_ablation.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/patch_response_quality.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/p_transfer_validation.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/p1_ams_hx_design.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/p_multilevel_response_quality.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/hierarchy_design.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/h_transfer_validation.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/vcycle_ablation.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/full_augmented_true_residual_history.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/reference_h2_gate.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/reference_h2_official_rta.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/robustness_case_matrix.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/robustness_iteration_map.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/robustness_memory_map.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/parameter_reuse_design.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/setup_reuse_benchmark.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/krylov_recycling_benchmark.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/mesh_convergence_template.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/gate_decision.csv
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/solver_profile_ranking.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/merge_recommendation.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/next_decision.md
docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/parameters.json
notes/theory/task025_parameter_robust_multilevel_hcurl_pc.md
```

`raw_runs/` 仅提交轻量日志和小型测试；大型 mesh、matrix、NPZ、XDMF、HDF5、VTU 和完整 results 保持 Git ignore。

---

## 23. summary.md 必答问题

```text
1. 是否建立了严格同预算 baseline？
2. 哪种 H(curl) patch smoother 最有效，为什么？
3. patch 对 selected/physical/random RHS 的降低率是多少？
4. p2->p1 transfer 是否在所有参考参数下正确？
5. p1 AMS/HX coarse correction 是否提供稳定附加收益？
6. 是否需要 h-GMG；若需要，最小有效层数是多少？
7. 完整 FE+80 aux FGMRES 是否在 h=2 达到 <=1e-6？
8. h=2 peak RSS 是否低于 14 GB？
9. official R/T/A 是否与 direct/reference 一致？
10. 同一 PC 架构在不同 h/theta/lambda 下是否全部收敛？
11. 最大/最小迭代数比是多少？
12. 哪些 hierarchy/patch 数据可在角度和波长扫描中复用？
13. warm start/recycling 的实际收益是多少？
14. 是否具备开始系统网格收敛和参数扫描的条件？
15. 下一步应进入 h<2、完整工程参数区间还是 sweeping fallback？
```

---

## 24. Merge strategy

默认：

```text
merge_docs: yes after review
merge_parameterized_operator: yes after regression
merge_patch/transfer infrastructure: only after isolated tests
merge_experimental multilevel profiles: no default
merge production solver: only after reference and robustness gates
production_default_change: no during Task025 development
```

任何 failed PC 路线留在 research branch，不因单一参数点成功而改 ordinary default。

---

## 25. 最终目标句

任务结束时必须回答：

```text
是否已经构建一个无需逐参数人工调节的 PETSc FGMRES + FieldSplit/Schur + multilevel H(curl) 预条件器，在 14 GB 内使参考 p=2 h=2 完整 FE+80 auxiliary 系统达到 true residual <= 1e-6 和 official R/T/A，并在网格、掠入射角与波长资格矩阵中保持可控迭代数和内存？
```
