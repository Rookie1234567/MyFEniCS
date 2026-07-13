# REVIEW REPORT：Task027 mesh-independent spectral Schwarz preconditioner

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260711-task27-mesh-independent-spectral-schwarz
reviewed_result_commit = 52ba708cc872e122fa8d21ac3cfa5e93075e9948
```

Task027 的原始目标是在 Task026 已验证的 auxiliary-free 凝聚算子

```math
A=F-CH^{-1}D
```

上构造低内存、可并行、对网格细化稳定的预条件器，使 `p=2, h=2 nm` 完整三维 Maxwell 系统达到 production residual，并以同一算法规则比较 `h=5/3/2 nm`。

本报告审查以下证据：

```text
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/gate_decision.csv
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/distributed_physical_slab_scaling.csv
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/mesh_independence_gate.csv
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/mpi_consistency.csv
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/h2_production_solver.json
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/h2_production_residual_history.csv
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/h2_production_memory.csv
docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/solver_profile_ranking.md
src/solvers/spectral_schwarz.py
src/studies/run_task027_mesh_independent_spectral_schwarz.py
src/test/test_23_task027_spectral_schwarz.py
```

---

## 2. 最终审查结论

```text
review_status = pass_with_qualifications
practical_solver_objective = pass
mpi4_h2_production = pass
tested_range_mesh_robustness = pass
memory_mandatory_gate = pass
memory_preferred_target = fail
spectral_coarse_hypothesis = fail
physical_mesh_convergence = fail_or_pending
ordinary_default_change = no
merge_recommendation = selective_merge
```

Task027 可以先行验收通过。

通过的不是原计划中的 operator-adaptive spectral coarse，而是以下固定结构：

```text
exact auxiliary-free matrix-free condensed operator
+ MPI4 owner-computes complete physical z-slab Schwarz
+ shifted local ILU1
+ two fixed GMRES smoothing steps on matrix-free shifted F
+ fixed 75-dimensional no-RHS z-hat Galerkin coarse space
+ right FGMRES(restart=100)
+ explicit true-residual checkpoints
```

该结构在 `h=5/3/2 nm` 上使用同一算法规则，分别以 `1201/993/1804` 步达到显式真残差小于 `1e-6`，实际迭代比为

```math
\frac{1804}{993}=1.8167170191<2.
```

`h=2` 含 official R/T/A 的峰值总 RSS 为 `12.958454 GB < 14 GB`。因此 Task027 预设的实际工程 Gate 已关闭。

准确状态应写为：

```text
mesh_robust_parallel_workstation_production_candidate_fixed_coarse
```

或沿用 outcomes 中的：

```text
mesh_independent_parallel_production_candidate_fixed_coarse
```

但在严格数学语境中，建议使用 `tested-range mesh-robust`，因为当前证据来自三个离散网格，而不是关于 `h -> 0` 的统一理论证明。

---

## 3. 核心数值证据

### 3.1 三网格统一规则

最终 MPI4 profile 在三个网格中没有逐网格调整：

```text
MPI ranks = 4
physical slabs = 16
overlap = 0.25 slab = 2.1875 nm
local factor = shifted-F ILU1
local solve = one fixed local application
shift = 0.1
inner smoother = two fixed GMRES steps
coarse basis = fixed-rule 75D no-RHS z-hat basis
coarse operator = true Galerkin Z^H A Z
outer solver = right FGMRES, restart=100
stopping residual = explicit true residual against exact condensed A
```

只有与不同 FE 空间对应的 basis/cache 数值内容发生变化；basis 规则和 solver 参数没有按网格人工调优。

### 3.2 最终结果

| h (nm) | FE DoF | iterations | explicit true residual | solve time (s) | peak total RSS incl. R/T/A (GB) |
|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | `9.8394899473e-7` | 91.10 | 1.957 |
| 3 | 198,438 | 993 | `9.9326487399e-7` | 317.85 | 5.070 |
| 2 | 615,108 | 1,804 | `9.9973779520e-7` | 2,179.96 | 12.958 |

Gate：

```text
all meshes true residual <= 1e-6 = pass
h2 RSS < 14 GB = pass
max/min iteration ratio <= 2 = pass
same algorithm rule = pass
```

### 3.3 h=2 residual 可信性

最终 h=2：

```text
PETSc reported residual       = 9.9973779560e-7
condensed explicit residual   = 9.9973779520e-7
full augmented residual       = 9.9973779520e-7
```

reported、condensed 与回代后的 full augmented residual 一致，未出现 HPDDM recycling 中曾观察到的 projected-residual 假收敛。

残差历史从 iteration 0 到 1804 连续下降；在 iteration 1800 时仍为 `1.01437e-6`，iteration 1804 才进入 Gate。该结果是真实收敛，但安全余量较小。

### 3.4 official R/T/A

| h (nm) | R | T | A_volume | R+T+A_volume | closure error |
|---:|---:|---:|---:|---:|---:|
| 5 | 0.0890216032 | 0.4425882752 | 0.4683901190 | 0.9999999974 | `-2.551e-9` |
| 3 | 0.0046130324 | 0.5836533646 | 0.4117336036 | 1.0000000006 | `6.180e-10` |
| 2 | 0.0013429363 | 0.5992132418 | 0.3994438284 | 1.0000000066 | `6.579e-9` |

h=2 MPI4 与此前 MPI1 production reference 的差异约为：

```text
abs(delta R)        = 3.30e-9
abs(delta T)        = 1.26e-8
abs(delta A_volume) = 8.50e-9
```

因此并行实现与既有高精度解一致。

---

## 4. 关键工程突破审查

### 4.1 旧 MPI 分片子域的问题

旧 MPI4 physical ASM 把每个物理 z-slab 按 PETSc ownership 切成 rank-local fragments。16 个物理 slab 在 4 ranks 上会产生最多 64 个 fragment 因子：

```text
physical slab != algebraic rank fragment
```

这会：

```text
- 破坏完整物理子域的传播结构；
- 重复存储 overlap；
- 增加局部因子数；
- 使 PC 强度依赖 MPI partition；
- 在 h=2 下产生高内存和极慢 apply。
```

### 4.2 owner-computes complete physical slab

新实现首先在 Floquet/MPC reduction 后收集完整 reduced-DoF slab：

```text
1. 每个物理 slab 形成完整全局 reduced-DoF index set；
2. 采用 deterministic largest-first 规则分配 owner rank；
3. 每个完整 slab 全局只提取、因子化一次；
4. owner 使用 sequential ILU1；
5. RHS 通过 forward VecScatter 收集；
6. overlap correction 通过 reverse ADD_VALUES scatter 返回；
7. 支持 owner rank 没有任何 slab factor 的情况。
```

h=2 中：

```text
global accumulated slab rows = 938,300
global slab-factor nnz       = 95,617,608
owner row range              = 230,202 ... 238,948
```

负载分配较均衡，也没有 rank0 gather 完整 FE 矩阵。

该设计是 Task027 最重要的可复用工程成果。它使并行预条件器的子域由物理几何定义，而不是由 MPI partition 定义。

### 4.3 两步 shifted-F smoothing

完整 owner-slab 一步平滑的三网格实际迭代为：

```text
2765 / 1836 / 3682
ratio = 2.0054
```

只差很小幅度未通过严格 `<=2` Gate。

固定两步 GMRES smoothing 后：

```text
1201 / 993 / 1804
ratio = 1.8167
```

说明完整物理 slab 已经提供主要局部修正，而第二步全局 smoothing 进一步处理一层 additive Schwarz 未覆盖的误差。

但该 inner GMRES 每个 outer PC apply 需要多次 one-level action，增加了单次 PC 成本。它应被视作当前 workstation 配置，而不是最终最优并行实现。

---

## 5. MPI 和代数正确性审查

以下证据通过：

```text
- complete slab owner balance；
- MPI1/MPI2 dense-reference action；
- repeated apply determinism；
- empty-owner-rank behavior；
- universal coarse cache action certification；
- h=5/h=3/h=2 coarse action error <= 4.99e-14；
- h=2 MPI1/MPI4 physical output consistency；
- exact condensed forward and Hermitian-transpose actions；
- explicit true residual checkpoints。
```

Cached coarse matrix 不是未经验证地跨 MPI partition 使用。每次加载后均重新执行：

```math
\frac{\|Z^HA(Zc)-A_0c\|}{\|A_0c\|}\le10^{-10}.
```

最大观测误差约 `4.99e-14`，通过 Gate。

---

## 6. 内存审查

h=2 主要阶段：

| stage | current total RSS (GB) | peak total RSS (GB) |
|---|---:|---:|
| after FE assembly | 4.273 | 7.273 |
| after hand coarse basis | 5.235 | 7.273 |
| after distributed sparse basis | 6.493 | 7.273 |
| after coarse factor | 6.691 | 7.273 |
| after local PC setup | 11.488 | 12.846 |
| during solve | 12.513 | 12.958 |

结论：

```text
mandatory RSS < 14 GB = pass
preferred RSS <= 12 GB = fail
```

主内存来自完整 slab 子矩阵和 ILU1 因子，不是 75 维 coarse solve。Krylov 运行期间峰值没有持续增长；swap 最终约 `0.454 GB`，没有 thrashing。

风险是可用余量仅约 `1.04 GB`。不同 PETSc/MPI build、系统后台进程或后处理临时数组可能使峰值越过 14 GB，因此 profile 仍应是显式 opt-in，而不应静默成为普通默认。

---

## 7. 谱粗空间假设审查

Task027 原计划中的 operator-adaptive spectral coarse 没有成功：

| variant | h=5 100-step true residual | decision |
|---|---:|---|
| fixed hand no-RHS reference | `6.272e-3` | reference |
| full-slab energy spectral | about `2.45e-1` | fail |
| interface harmonic | `2.504e-1` | fail |
| hand + interface | `7.162e-3` | negative gain |
| shifted near-null | `2.588e-1` | fail |
| HPDDM Ritz + true Galerkin | `7.435e-3` | negative gain |
| PCHPDDM energy GenEO | `2.187e-1` | fail |

PoU、SPD local energy、eigenpair residual 和 orthogonality 均通过代数 Gate，但所选局部能量模态没有捕获当前复系数、非正规、强不定、Floquet-DtN 系统的实际慢误差。

因此必须明确：

```text
spectral implementation algebra = largely pass
spectral preconditioning performance = fail
final solver breakthrough mechanism = non-spectral physical Schwarz
```

不得将固定 75 维 coarse 的成功包装成 GenEO、PCHPDDM 或 operator-adaptive spectral coarse 的成功。

失败谱 profile 可以保留在 research branch 作为负证据，但不进入 ordinary production default。

---

## 8. Mesh-independent 术语边界

按 Task027 预先定义的工程 Gate：

```text
same rule on h=5/3/2
all true residual <= 1e-6
max/min iterations <= 2
```

最终 profile 通过，因此称为 `mesh-independent candidate` 在项目内部是可接受的。

但严格数学上，目前只能证明：

```text
从 44,698 DoF 到 615,108 DoF 的已测试区间中，
迭代数保持在 993–1804，未随自由度增长约 13.8 倍而爆炸。
```

尚未证明：

```math
\sup_{h\to0}N_{\mathrm{iter}}(h)<\infty.
```

因此对外或论文表述建议使用：

```text
tested-range mesh-robust parallel iterative solver
```

而不是无条件宣称已获得理论意义上的 mesh-independent convergence。

---

## 9. 物理网格收敛边界

每个网格上的：

```text
- linear true residual；
- modal R/T；
- volume absorption；
- energy closure
```

均已通过。

但 h=3 到 h=2 的物理量仍明显变化，特别是较小的反射率 R。Task027 只证明线性求解器对三个离散系统有效，不能证明 h=2 已是物理网格收敛解。

必须持续区分：

```text
solver mesh robustness = pass
physical discretization convergence = pending/fail
```

下一阶段的物理网格收敛研究不影响 Task027 作为线性求解器任务先行验收。

---

## 10. Gate 总表

| Gate | Status | Review decision |
|---|---|---|
| exact matrix-free condensed operator | pass | retain |
| exact Hermitian-transpose action | pass | retain |
| h=2 MPI4 true residual <=1e-6 | pass | production candidate |
| h=2 full augmented residual <=1e-6 | pass | production candidate |
| h=2 RSS <14 GB | pass | workstation budget passed |
| preferred RSS <=12 GB | fail | optimization remains |
| h=5/h=3/h=2 same-rule convergence | pass | retain |
| iteration ratio <=2 | pass, `1.8167` | tested-range mesh robust |
| official R/T/A and closure | pass | valid per mesh |
| MPI owner/scatter/action tests | pass | retain |
| cached coarse true-action certification | pass | retain |
| spectral coarse performance | fail | research-only negative evidence |
| parameter robustness | not run | future independent task |
| physical R/T/A mesh convergence | fail/pending | future discretization task |
| ordinary default replacement | no | explicit opt-in only |

---

## 11. 合并建议

### 11.1 建议审查后选择性合并

```text
- DistributedPhysicalSlabSmoother；
- complete reduced-DoF slab collection；
- deterministic balanced owner assignment；
- owner-only submatrix extraction and ILU setup；
- forward gather / reverse overlap scatter；
- fixed multi-step matrix-free shifted-F smoothing；
- distributed sparse Galerkin coarse action；
- true-action-certified coarse cache；
- exact condensed transpose/Hermitian actions；
- MPI dense-reference/repeatability/empty-owner tests；
- residual/RSS/swap/RTA diagnostic infrastructure；
- Task027 review/outcome documentation。
```

### 11.2 保留为 research-only

```text
- full-slab energy spectral coarse；
- interface harmonic spectral coarse；
- shifted near-null spectral coarse；
- PCHPDDM energy GenEO；
- HPDDM Ritz experiments；
- cross-solve recycling path with false projected residual；
- broad spectral tau/cap experiment runner。
```

### 11.3 不应修改

```text
- ordinary production default；
- existing auxiliary DtN reference path；
- standard entry max_it；
- default Docker image/environment。
```

最终 profile 应作为显式选择的 workstation production candidate，而不是静默默认。

---

## 12. 验收后的剩余风险

### 12.1 residual 安全余量

当前 h=2 最终真残差为：

```text
9.9973779520e-7
```

刚刚进入 `1e-6` Gate。建议以后用于正式批量运行时显式使用：

```text
rtol = 8e-7
```

形成更宽余量，并继续以显式 true residual 决定是否允许 official R/T/A。

### 12.2 内存余量

12.958 GB 距 14 GB 只有约 1.04 GB。正式复跑应：

```text
- 关闭不必要后台进程；
- 继续记录 sum RSS 与 swap；
- 不同时保存额外显式 condensed matrix；
- 后处理完成后及时释放临时场和数组。
```

### 12.3 扩展性

每个完整 slab 仍由单个 owner rank 使用顺序 ILU1。当前结构适合 4 ranks、16 slabs、615k FE DoF，但不是面向更大问题的最终强扩展方法。

### 12.4 参数鲁棒性

75 维 no-RHS coarse 已排除明显的 RHS 过拟合，但仍没有完成角度、波长、材料损耗和 near-Rayleigh 条件下的统一 qualification。

### 12.5 吞吐量

h=2 solve 约 36.3 分钟，已比旧 BJacobi MPI4 profile 快约 46%，但大规模 parameter sweep 仍然昂贵。后续优化应优先降低两步 smoothing 的 one-level apply 次数，而不是继续扫描已失败的 energy spectral tau/cap。

---

## 13. 最终验收决定

```text
Task027 practical solver objective = ACCEPTED
Task027 branch status = PASS WITH QUALIFICATIONS
Task027 may be closed for now = YES
```

理由：

```text
1. 完整 h=2 MPI4 系统达到显式真残差 <1e-6；
2. 峰值 RSS 低于 14 GB；
3. official R/T/A 和能量闭合通过；
4. 同一规则在 h=5/3/2 全部收敛；
5. 实际迭代比 1.8167 通过预设 Gate；
6. reported/true/full residual 一致；
7. MPI owner/scatter/coarse cache 均有回归和真实 action 证据；
8. 谱机制失败被诚实保留，没有包装为成功。
```

Task027 可以先过去。下一项工作应在独立任务中处理，而不是继续扩大本分支范围：

```text
- rtol=8e-7 安全余量复跑；
- 角度/波长/材料参数鲁棒性；
- 物理 R/T/A 网格收敛；
- 两步 smoothing 成本优化；
- 更大问题的 slab 内并行或真正 H(curl) multilevel 方法。
```
