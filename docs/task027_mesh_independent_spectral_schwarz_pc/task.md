# CODEX TASK 20260711：mesh-independent spectral Schwarz preconditioner

## 0. 任务名称

```text
Task027: Mesh-independent spectral Schwarz preconditioner
for the auxiliary-free condensed 3D Maxwell operator
```

中文定位：

```text
基于 Task026 已验证的 auxiliary-free matrix-free 凝聚算子，
用最小可行的局部谱粗空间替代手工 Floquet/z-hat 粗空间，
优先突破 h=2 production residual，并验证 h=5/h=3/h=2 的网格鲁棒性，
同时将峰值内存控制在 14 GB 以内，目标尽量低于 12 GB。
```

ChatGPT 不创建分支。Codex 如需执行分支，应自行从当前已审查的 Task026 分支创建；不得修改 ordinary production default。

---

## 1. 背景与当前基线

Task026 已完成以下架构性闭环：

```text
1. 原 auxiliary DtN 系统可精确静态凝聚；
2. 真实 operator 为 A = F - C H^{-1} D；
3. explicit condensed 与 matrix-free condensed 在 h=5/h=2 上 action 等价；
4. h=2 MPI1/MPI4 actual action error 约 1e-15；
5. 迭代路径不再包含 auxiliary global unknown、Q=F^{-1}C 或 Q cache；
6. official R/T/A 后处理仍可通过 auxiliary back-substitution 恢复。
```

当前 h=2 最好 research profile：

```text
outer             = FGMRES(restart=100)
operator          = exact matrix-free F - C H^{-1} D
subdomains        = 16 physical z-slabs
local PC          = shifted local ILU1
shift             = empirical beta=0.1
slab overlap      = 0.25 slab
coarse space      = 24 z intervals, 76 hand-built Floquet vector-hat vectors
iterations        = 600
full true residual= 7.0511534435e-4
peak RSS          = 11.380 GB
```

100-step qualification result：

```text
full true residual = 5.0239925265e-3
peak RSS           = 10.436 GB
```

该结果已经证明 two-level correction 方向正确，但仍未达到：

```text
production gate = full true residual <= 1e-6
```

手工扩展 Fourier harmonics、coarse intervals、restart、shift、inner GMRES 和普通 Krylov 已出现明显边际收益递减。Task027 禁止再次进行无边界参数扫描。

---

## 2. Task027 的核心判断

当前主要瓶颈不是端口，也不是外层 Krylov 名称，而是：

```text
局部 ILU1 无法消除的慢误差，
没有被固定的 76 维手工 coarse space 稳定覆盖。
```

Task027 要验证的核心假设是：

> 在现有 16 个重叠 z-slab 上，通过局部广义特征问题自动选择困难模式，可形成对网格细化更稳定的 coarse space，并显著降低 h=2 的残差平台。

Task027 的第一优先级是尽快得到可证伪的数值答案，而不是一次实现完整理论框架。

研究笔记：

```text
notes/theory/task027_shifted_impedance_spectral_schwarz_convergence_framework.md
```

该笔记中的 mass shift、local impedance Maxwell problem、Maxwell-harmonic extension、adjoint 与严格 q_direct certification 作为后续参考；除非本任务明确进入升级 Gate，否则不得把全部内容一次性塞进第一版实现。

---

## 3. 不变的真实物理算子

真实外层 operator 必须保持：

```math
A = F - C H^{-1} D.
```

matrix-free action：

```math
y = Fx - C\left(H^{-1}Dx\right).
```

禁止重新引入：

```text
- auxiliary global unknowns；
- Q = F^{-1}C；
- cached 80-response Schur；
- Woodbury correction requiring F^{-1}C；
- 端口物理近似替代真实 condensed DtN。
```

只有 PC 可以使用 shifted/proxy operator；外层 residual 必须基于真实 A 显式计算。

---

## 4. 总体执行漏斗

必须按以下顺序执行：

```text
Stage A：固化严格 mesh baseline 与过拟合诊断；
Stage B：实现 reduced-space partition of unity 与局部 SPD energy matrices；
Stage C：实现最小 full-slab spectral coarse proof-of-concept；
Stage D：同规则 h=5/h=3/h=2 mesh-independence qualification；
Stage E：只有 Stage C/D 有正信号时，做 h=2 production run；
Stage F：若简单 energy spectral coarse 不足，再二选一升级：
         F1. Maxwell-harmonic/interface spectral coarse；
         F2. isolated PETSc+SLEPc+HPDDM/PCHPDDM proof-of-concept；
Stage G：达到 h=2 <=1e-6 后，立即做 official R/T/A，再考虑 MPI PC 与参数扫描。
```

禁止：

```text
- 再扫描大量 restart/shift/ILU/Fourier-order 组合；
- 在 spectral coarse 尚无正信号时实现完整 adjoint certification；
- 在 h=2 production gate 前做大规模 angle/wavelength campaign；
- 用 h=5 单点成功声称 mesh-independent；
- 为不同 h 手工选择完全不同 coarse basis 规则；
- 用 relative-to-zero improvement 作为成功指标。
```

---

## 5. Stage A：严格 baseline 与 coarse-space 过拟合诊断

### 5.1 统一 baseline

在同一个 runner、同一个真实 operator、同一个 residual API 下运行：

```text
mesh h = 5, 3, 2 nm
outer = FGMRES
restart = 50 and 100 only
local topology = physical z-slabs
slab physical thickness rule = fixed physical scale, not fixed arbitrary dof count
local PC = shifted ILU1 baseline
coarse = current 76-dimensional hand-built basis
```

所有 mesh 必须使用同一算法规则。允许 slab 数量随物理厚度自动变化，但不得逐网格人工调出不同 profile。

记录：

```text
- FE rows / nnz；
- slab count / overlap physical width；
- coarse dimension；
- setup time；
- 100-step true residual；
- 300/600-step true residual where affordable；
- peak RSS；
- mean PC apply time；
- swap used；
- convergence reason。
```

输出：

```text
outcomes/mesh_baseline.csv
outcomes/mesh_baseline_residual_history.csv
outcomes/mesh_baseline_memory.csv
```

### 5.2 过拟合诊断

在 h=5 上只做以下低成本对照：

```text
A. current hand-built coarse with physical RHS vector；
B. same coarse without physical RHS vector；
C. same construction at one nearby angle；
D. same construction at one nearby wavelength。
```

目的不是参数 qualification，而是判断当前 coarse 成功是否主要依赖：

```text
- 当前 RHS enrichment；
- 当前固定 Floquet phase；
- 当前单一参数点。
```

Gate：

```text
若去掉 physical RHS 后 100-step residual 恶化超过 5x，
则当前手工 coarse 标记为 load-overfit，不再作为 mesh-independent 候选。
```

输出：

```text
outcomes/hand_coarse_overfit_diagnostic.csv
```

---

## 6. Stage B：reduced-space partition of unity 与局部能量矩阵

### 6.1 Reduced FE space 中的子域

必须在 Floquet/MPC reduction 之后的 FE numbering 中构造重叠 slabs：

```math
\Omega = \bigcup_i \Omega_i.
```

限制算子：

```math
R_i:V_h\to V_i.
```

partition-of-unity 权重：

```math
\sum_i R_i^T D_i R_i = I.
```

必须实际验证：

```text
- reduced dof coverage；
- overlap multiplicity；
- partition-of-unity random-vector error；
- Floquet master/slave consistency；
- Nedelec orientation consistency；
- MPI ownership metadata，即使第一版 solver 仍为 MPI1。
```

Gate：

```text
relative PoU error <= 1e-12
no uncovered reduced dofs
no negative/NaN weights
```

### 6.2 局部 SPD energy proxy

第一版不直接解非 Hermitian local eigenproblem。构造 Hermitian 正定局部能量矩阵：

```math
R_i^+
=K_{|\mu^{-1}|,i}
+k_0^2M_{|\varepsilon|,i}
+\gamma_i M_{\Gamma,i}.
```

第一版允许：

```text
- 使用局部 curl-curl + positive mass；
- 人工接口正定 trace mass；
- 物理边界保留真实 topology metadata；
- 仅用于 eigenproblem，不替代真实 outer operator。
```

必须检查：

```text
Hermitian error <= 1e-12
smallest eigenvalue > 0 within tolerance
finite condition estimate
```

输出：

```text
outcomes/partition_of_unity_validation.csv
outcomes/local_energy_matrix_diagnostics.csv
outcomes/slab_topology_statistics.csv
```

---

## 7. Stage C：最小 full-slab spectral coarse proof-of-concept

### 7.1 第一版谱问题

优先实现不需要显式 harmonic extension 的 full-slab energy spectral problem。

推荐第一候选：

```math
D_i^H R_i^+ D_i\phi_{i,j}
=\lambda_{i,j}R_i^+\phi_{i,j}.
```

采用该约定时，选择：

```math
\lambda_{i,j}>\tau.
```

如果实现采用倒数形式，必须在代码和文档中固定选择方向，禁止一处选大特征值、一处选小特征值。

全局 coarse vectors：

```math
z_{i,j}=R_i^TD_i\phi_{i,j}.
```

汇总：

```math
Z=[z_1,\ldots,z_{n_c}].
```

粗矩阵必须使用完整真实或 shifted-condensed operator：

```math
A_0=Z^HA_{pc}Z.
```

其中第一版允许：

```text
A_pc = current verified shifted condensed PC operator
```

但禁止只使用一个与端口完全脱离的粗矩阵而不做 action consistency 检查。

### 7.2 特征求解策略

不得显式构造巨大 dense local eigenproblem。

优先顺序：

```text
1. SLEPc/PETSc EPS if available；
2. scipy eigsh only for small h=5 slabs and serial proof-of-concept；
3. matrix-free LOBPCG/eigensolver；
4. randomized subspace only as diagnostic，不可直接宣称严格 GenEO。
```

只求阈值附近或前若干目标特征对。记录每个 slab：

```text
local rows
selected eigenvectors
first omitted eigenvalue
eigenpair residual
R_i^+-orthogonality
setup time
peak RSS
```

### 7.3 Coarse rank gate

构造：

```math
A_0=Z^HA_{pc}Z.
```

必须检查：

```text
coarse rank
smallest singular value
condition number
complex dot direction
```

Gate：

```text
rank = coarse dimension
condition <= 1e10
no pinv fallback to hide rank deficiency
```

### 7.4 第一轮尺寸预算

第一轮只能测试有限的谱阈值或每 slab 模态上限：

```text
max 3 candidate thresholds
max 2 per-slab caps
```

禁止大规模阈值扫描。

目标 coarse dimension：

```text
h=5 proof-of-concept: preferably <= 200
h=2 engineering target: preferably <= 300
hard cap before justification: 500
```

输出：

```text
outcomes/spectral_eigenproblem_design.md
outcomes/local_spectral_diagnostics.csv
outcomes/spectral_coarse_rank.csv
outcomes/spectral_setup_memory.csv
```

---

## 8. Stage C Gate：是否值得继续谱路线

与当前手工 coarse 做严格比较。

### h=5 Gate

相同或相近 PC apply 成本下，至少满足一个：

```text
- 达到 1e-8 所需迭代数减少 >= 2x；
- 100-step true residual 改善 >= 5x；
- 去除 physical RHS enrichment 后仍保持稳定收敛。
```

### h=2 early Gate

100 步必须相对当前基线：

```text
current = 5.0239925265e-3
```

达到：

```text
minimum positive signal <= 2.5e-3
strong signal          <= 1.0e-3
breakthrough signal    <= 1.0e-4
```

并满足：

```text
peak RSS < 13 GB
setup does not enter swap thrashing
coarse setup + solve total wall time is finite and recorded
```

停止条件：

```text
- h=5 无正收益：停止 full-slab energy spectral variant；
- h=2 100-step residual > 3e-3：不做长跑；
- setup RSS >= 14 GB：停止；
- 单 slab eigenproblem 不能在预算内完成：转 interface/harmonic reduced variant；
- coarse dim > 500 且仍无数量级改善：停止。
```

---

## 9. Stage D：mesh-independent qualification

只有 Stage C 有正信号才执行。

### 9.1 同一规则

必须使用同一：

```text
spectral formulation
threshold selection rule
physical overlap rule
local solver rule
outer FGMRES policy
residual definition
```

在：

```text
h = 5, 3, 2 nm
```

上运行。

允许 coarse dimension 随谱阈值自动变化，但不允许逐 mesh 手工挑不同 Fourier harmonics 或不同物理策略。

### 9.2 mesh-independent 指标

第一资格线：

```text
all meshes converge to true residual <= 1e-6
peak RSS(h=2) < 14 GB
```

网格鲁棒性目标：

```text
max(iterations_h5,h3,h2) / min(iterations_h5,h3,h2) <= 2.0
```

候选 engineering signal：

```text
iteration ratio <= 3.0
and h=2 <= 1e-6
```

如果 h=2 能收敛但迭代增长过大，应标记：

```text
production-capable but not mesh-independent
```

输出：

```text
outcomes/mesh_independence_gate.csv
outcomes/mesh_iteration_scaling.csv
outcomes/mesh_memory_scaling.csv
outcomes/mesh_coarse_dimension_scaling.csv
```

---

## 10. Stage E：h=2 production run

只有 early Gate 通过才允许长跑。

硬目标：

```text
full true residual <= 1e-6
peak RSS < 14 GB
target RSS <= 12 GB
no sustained swap thrashing
```

推荐 outer：

```text
FGMRES restart 50 or 100 only
```

不得重新使用 restart 300。

必须流式写入：

```text
iteration
reported residual
explicit true residual checkpoint
RSS current/peak
swap used
elapsed time
coarse apply time
local solve time
```

达到 residual Gate 后立即：

```text
1. recover auxiliary modal amplitudes；
2. compute official R_m/T_m；
3. compute R_total/T_total/A_volume；
4. check energy closure；
5. compare with h=5/direct/COMSOL reference where applicable。
```

official Gate：

```text
linear true residual <= 1e-6
R/T/A finite
energy closure within agreed numerical tolerance
no use of unconverged field for official output
```

输出：

```text
outcomes/h2_production_solver.json
outcomes/h2_production_residual_history.csv
outcomes/h2_production_memory.csv
outcomes/h2_official_rta.csv
```

---

## 11. Stage F：只有简单谱粗空间不足时的升级决策

### F1. Maxwell-harmonic/interface spectral coarse

触发条件：

```text
full-slab eigenproblem setup too expensive
or
full-slab energy spectral coarse h=2 residual stalls above 1e-4
```

参考：

```text
notes/theory/task027_shifted_impedance_spectral_schwarz_convergence_framework.md
```

升级内容限定为：

```text
1. local interface identification；
2. matrix-free Maxwell-harmonic extension；
3. interface-reduced spectral problem；
4. local impedance transmission；
5. PDE mass shift。
```

不得在一个步骤中同时引入全部改动。建议顺序：

```text
interface spectral reduction
-> harmonic extension
-> local impedance
-> PDE mass shift
```

每一步都必须与上一步做单变量对照。

### F2. HPDDM/PCHPDDM proof-of-concept

如果当前 PETSc 环境没有：

```text
HPDDM
SLEPc
PCHPDDM
GCRODR
```

允许构建独立 research image，不修改普通镜像。

目标是快速验证：

```text
现成 spectral Schwarz 是否能明显突破 7.051e-4 baseline。
```

环境 Gate：

```text
complex PETSc
SLEPc available
HPDDM enabled
same operator data import verified
small h=5 smoke test first
```

PCHPDDM 路线若 100-step h=2 不能改善当前基线至少 2x，停止，不进行大规模环境调参。

输出：

```text
outcomes/hpddm_environment.md
outcomes/hpddm_spectral_pc_benchmark.csv
```

---

## 12. 内存优先规则

Task027 的目标不是用巨大 coarse space 换取一次收敛。

必须分阶段记录：

```text
after FE assembly
after slab maps
after local energy matrices
after eigen setup
after selected eigenvectors
after global Z construction
after coarse matrix/factor
after local PC setup
after Krylov allocation
peak during solve
```

禁止：

```text
- 同时长期保留 augmented 与 condensed 大矩阵；
- 存储所有未选 local eigenvectors；
- 将 global Z 构造为 dense N_FE x n_c NumPy array；
- rank0 gather complete FE matrices；
- 每次 PC apply 临时创建 large vectors；
- 以 pinv 掩盖粗空间秩亏；
- 让 Krylov restart 吃掉 spectral coarse 节省的内存。
```

推荐：

```text
- PETSc distributed Vec basis；
- selected eigenvectors only；
- coarse action streaming construction；
- reuse A*Z work vector；
- small dense coarse factor only after rank gate；
- explicit destroy lifecycle；
- per-stage RSS/swap checkpoint。
```

内存 Gate：

```text
h=2 spectral setup peak < 13 GB preferred
h=2 total peak < 14 GB mandatory
target production peak <= 12 GB
```

输出：

```text
outcomes/spectral_memory_breakdown.csv
outcomes/spectral_basis_storage.csv
outcomes/spectral_pc_cost_breakdown.csv
```

---

## 13. 代码质量与回归要求

必须新增测试：

```text
1. reduced-space partition-of-unity identity；
2. local R_i^+ Hermitian/positive check；
3. generalized eigenpair residual；
4. local eigenvector R_i^+-orthogonality；
5. selected/omitted eigenvalue ordering；
6. global coarse rank and condition；
7. complex dot regression；
8. matrix-free condensed operator action regression；
9. no-RHS-enrichment coarse regression；
10. repeated PC apply RSS stability。
```

MPI：

```text
第一版 spectral solver 可先 MPI1 proof-of-concept；
但数据结构必须保存 distributed ownership metadata；
达到 h=2 <=1e-6 后，再实现 MPI4 solver consistency；
不得用 MPI1 proof 直接宣称 parallel production。
```

---

## 14. 统一 Gate 总表

| Gate | 条件 | 状态要求 |
|---|---|---|
| Architecture | exact matrix-free A unchanged | 必须 pass |
| PoU | relative identity error <= 1e-12 | 必须 pass |
| Local energy | Hermitian/SPD checks pass | 必须 pass |
| Eigenproblem | residual/orthogonality pass | 必须 pass |
| Coarse rank | full rank, cond <=1e10 | 必须 pass |
| h5 spectral signal | >=2x iterations or >=5x residual gain | 进入 h2 前 pass |
| h2 100-step minimum | residual <=2.5e-3 | positive |
| h2 100-step strong | residual <=1e-3 | strong |
| h2 production | residual <=1e-6 | 必须 pass |
| h2 memory | peak <14 GB | 必须 pass |
| mesh-independent | h5/h3/h2 iteration ratio <=2 | 最终目标 |
| official physics | converged R/T/A and closure | 必须 pass |
| MPI PC | MPI1/MPI4 consistent | production 前最终 pass |

---

## 15. 输出清单

必须产出：

```text
outcomes/summary.md
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/changed_files.md
outcomes/run_log.txt
outcomes/mesh_baseline.csv
outcomes/hand_coarse_overfit_diagnostic.csv
outcomes/partition_of_unity_validation.csv
outcomes/local_energy_matrix_diagnostics.csv
outcomes/local_spectral_diagnostics.csv
outcomes/spectral_coarse_rank.csv
outcomes/spectral_setup_memory.csv
outcomes/spectral_pc_benchmark.csv
outcomes/mesh_independence_gate.csv
outcomes/mesh_iteration_scaling.csv
outcomes/mesh_memory_scaling.csv
outcomes/h2_production_solver.json
outcomes/h2_official_rta.csv
outcomes/merge_recommendation.md
outcomes/next_decision.md
```

大体积矩阵、eigenvectors、mesh、factor files 和 raw checkpoint 放入：

```text
results/
```

不得提交 Git。

---

## 16. 最终决策规则

### 成功

只有同时满足：

```text
h=2 true residual <= 1e-6
h=2 peak RSS < 14 GB
official R/T/A pass
same spectral rule works for h=5/h=3/h=2
iteration growth controlled
```

才可标记：

```text
mesh_independent_production_candidate
```

### 部分成功

如果：

```text
h=2 <=1e-6
但 iteration ratio >2
```

标记：

```text
production_capable_not_mesh_independent
```

### 研究正信号

如果：

```text
h=2 100-step <=1e-3
但长跑仍未到1e-6
```

标记：

```text
spectral_coarse_strong_research_signal
```

### 失败或转向

如果最小 spectral coarse：

```text
h=5 无显著收益
or h=2 100-step >3e-3
or setup >=14 GB
or coarse dim >500 without order-of-magnitude gain
```

则停止 full-slab energy variant，转：

```text
Maxwell-harmonic/interface spectral coarse
or PCHPDDM proof-of-concept
```

如果两者仍不能突破当前 `7.051e-4` baseline，则 Task027 应明确建议进入真正 3D H(curl) h-GMG，而不是继续手工调参。

---

## 17. 一句话目标

```text
用最小可行的 operator-adaptive spectral coarse space，
把 Task026 的 h=2 residual 从 7.051e-4 推进到 <=1e-6，
在 <14 GB 内证明同一算法规则对 h=5/h=3/h=2 具有可接受的网格鲁棒性。
```
