# REVIEW REPORT V1：Task026 auxiliary-free 3D periodic modal port

## 1. 审查状态

```text
review_status = partial_pass_research
auxiliary_free_condensation = pass
h5_direct_equivalence = pass
h5_matrix_free_action = pass
h5_iterative_physics = pass
h2_plain_iterative = fail
h2_two_level = pending_remote_result
h2_direct_reference = pending
parameter_robustness = not_run
production_default_change = no
```

Task026 已经完成一个重要的架构性突破：现有 3D auxiliary DtN 系统可以被精确静态凝聚为只包含 FE unknown 的系统，且显式 condensed operator、matrix-free condensed operator 和原 auxiliary operator 在 h=5 上达到机器精度等价。

这意味着 Task021–Task025 中由于 FE-block Schur / response-column 路线而产生的

```math
Q \approx A_{FE}^{-1}C
```

不再是新迭代路线的必需组成部分。

但是，Task026 尚未完成 h=2 two-level 收敛结果、h=2 actual action equivalence、h=2 direct/OOC reference、MPI two-level 和参数鲁棒性验证。因此本轮只能判为研究性部分通过，不能宣称 h=2 production solver 已完成。

最终定性：

```text
Task026 auxiliary-free operator architecture = success
Task026 h=5 iterative proof = success
Task026 h=2 production solver = unresolved
Task026 parameter-robust solver = not established
```

---

## 2. 核心数学结构审查

原 augmented system：

```math
\begin{bmatrix}
F & C\\
D & H
\end{bmatrix}
\begin{bmatrix}
u\\a
\end{bmatrix}
=
\begin{bmatrix}
b_F\\b_H
\end{bmatrix}.
```

消去 modal auxiliary unknown：

```math
a=H^{-1}(b_H-Du),
```

得到：

```math
A_{cond}u=b_{cond},
```

其中：

```math
A_{cond}=F-CH^{-1}D,
```

```math
b_{cond}=b_F-CH^{-1}b_H.
```

当前 3D port 的 `H=I`，所以：

```math
A_{cond}=F-CD.
```

Task026 同时实现了：

```text
1. explicit condensed operator
2. matrix-free condensed operator
3. auxiliary recovery / back-substitution
```

matrix-free action 为：

```math
y=Fx-C\left(H^{-1}Dx\right).
```

该实现不再构造：

```text
- Q = F^-1 C
- 80-response cache
- approximate auxiliary Schur
- 80 auxiliary global unknowns in the iterative operator
```

审查判断：

```text
static_condensation_formula = correct
matrix_free_low_rank_action = correct
auxiliary_backsubstitution = correct
```

---

## 3. 二维回归审查

真实 2D `p=2, h=5 nm` auxiliary 与 explicit condensed 直接法结果：

| metric | difference |
|---|---:|
| FE field relative error | `1.696e-14` |
| absolute R difference | `6.32e-16` |
| absolute T difference | `1.33e-15` |
| absolute closure difference | `2.00e-15` |

这说明二维 explicit outer-product implementation 与 auxiliary formulation 在场和功率层面等价。

但任务书要求的真实二维 matrix-action equivalence 尚未单独运行；当前只有 synthetic nonidentity-H block test。

因此 Stage 2 应细分为：

```text
2D field equivalence = pass
2D R/T equivalence = pass
2D actual matrix-action gate = pending
```

该缺口不推翻现有物理结论，但必须在 Task026 关闭前补齐。

---

## 4. 三维 h=5 代数等价审查

实际 h=5 结果：

| check | relative / absolute error |
|---|---:|
| random-vector explicit vs matrix-free action | `3.311e-17` |
| physical-RHS action | `3.244e-16` |
| direct-solution action | `3.639e-15` |
| auxiliary vs condensed FE field | `3.712e-13` |
| delta R | `3.009e-14` |
| delta T | `-8.332e-14` |
| delta A_volume | `-2.565e-14` |
| delta closure | `-7.894e-14` |

直接法：

```text
auxiliary MUMPS residual = 7.818e-12
condensed MUMPS residual = 5.993e-12
```

显式 condensed matrix：

```text
size = 44698 x 44698
nnz = 5284876
explicit port nnz = 460800
```

审查判断：

```text
3D h5 auxiliary vs explicit = pass
3D h5 explicit vs matrix-free action = pass
3D h5 field and R/T/A equivalence = pass
```

这已经足以确认当前 80-mode 3D periodic modal port 可以无 auxiliary 地实现，而不改变端口物理。

---

## 5. Matrix-free 生命周期与内存审查

h=5 matrix-free operator 连续执行 1000 次 apply，current RSS 前后均约为：

```text
0.65961 GB
```

没有发现持续增长。

operator-only storage 证据表明，matrix-free condensation 可以避免显式 port matrix 和 Task025 Q cache。

当前实现中仍有以下工程改进点：

1. `SmallDenseInverse` 对小型 `H` 使用 `np.linalg.inv`；未来如果 `H` 不再是单位块，建议改为 LU/QR factorization + solve。
2. 每次 apply 对小型 auxiliary vector进行一次 collective gather；80 维时成本有限，但高迭代次数下仍是同步点。
3. 必须持续禁止在 MatMult 内构造全局 FE-sized NumPy arrays。
4. work vectors 和 small-factor 生命周期当前基本正确，应继续保留 repeated-apply RSS regression。

审查判断：

```text
matrix_free_lifecycle = pass_research
matrix_free_memory_behavior = pass
production_mpi_scalability = not_yet_established
```

---

## 6. h=5 新迭代器审查

通过的 profile：

```text
FGMRES(restart=300)
+ exact matrix-free condensed operator
+ shifted FE smoother, beta=0.1
+ 8 topology z-slab ASM subdomains
+ local ILU2
+ slab overlap = 0.25
+ 24 z coarse intervals
+ 76-dimensional Floquet-phase vector-hat Galerkin coarse space
+ pre-smoothing + coarse correction
+ no post-smoothing
```

结果：

```text
iterations = 795
full true residual = 9.999205e-10
peak RSS = 1.829 GB
elapsed = 101.7 s
```

official R/T/A：

```text
R = 0.08902160293472974
T = 0.442588278660677
A_volume = 0.46839011840325523
R + T + A = 0.999999999998662
closure error = -1.338e-12
```

审查判断：

```text
h5 auxiliary-free iterative physical closure = pass
h5 production-like residual = pass
h5 solver efficiency = weak due to 795 iterations
```

795 次迭代说明 coarse space 有效，但 PC 仍不够强，不能据此宣称参数鲁棒或网格鲁棒。

---

## 7. complex inner product 修复审查

初始 Galerkin prototype 对 petsc4py `Vec.dot` 的共轭方向处理错误。

当前修复使用：

```python
np.conjugate(left.dot(right))
```

来构造标准数学意义上的：

```math
left^H right.
```

修复覆盖：

```text
- modified Gram-Schmidt
- Z^H A Z
- Z^H r
```

同一 76 维 coarse profile 的 200-step residual 从约：

```text
0.2591
```

改善到：

```text
0.0010455
```

该修复具有决定性影响。

审查要求：

```text
1. 必须保留 dedicated complex-dot regression；
2. Task025 和更早的 Galerkin/coarse negative evidence 不得自动视为最终结论；
3. 如旧实验使用同类 dot 方向，应标记 potentially contaminated，不能直接引用。
```

---

## 8. topology two-level PC 的适用边界

当前 smoother 是 z 方向 slab decomposition：

```text
8 slabs
local ILU2
fractional overlap 0.25 slab
```

coarse basis 是：

```text
piecewise-linear z hats
x current Floquet phase exp(i(kx x + ky y))
x three vector components
+ physical RHS vector
```

24 coarse intervals 对应约：

```text
5.83 nm spacing < lambda/2
```

8 intervals 的约 `17.5 nm` spacing 不满足当前波长分辨率，已被否定。

当前 coarse space 的优点：

```text
- 能捕获 z 方向长波误差；
- 保留当前 Floquet phase；
- 体量仅 76 维；
- h=5 产生决定性正收益。
```

当前局限：

```text
- 只支持 MPI=1；
- coarse phase 依赖当前角度/波长；
- 显式加入 physical RHS，可能对参考 case 过拟合；
- 不是真正 nonmatching 3D h-GMG；
- 尚未验证 h refinement robustness；
- 尚未验证 angle/wavelength robustness。
```

因此准确名称应为：

```text
problem-informed topology two-level prototype
```

不应称为完整 COMSOL-style GMG 或 parameter-robust multigrid。

---

## 9. h=2 当前证据审查

已经落盘的 plain profile：

```text
matrix-free condensed operator
+ shifted global ILU2
+ 200 outer iterations
```

结果：

```text
full true residual = 0.166485
peak RSS = 12.883 GB
```

该结果：

```text
memory gate = pass
algorithm gate = fail
```

它没有优于 Task025 cached-Schur `0.118475`。

关键 h=2 two-level case：

```text
8 z slabs
24 coarse intervals
overlap 0.25
restart 50
100-step qualification
```

在 summary 写入时仍在后台运行，远程分支没有：

```text
two_level.json
residual_history.csv
final gate decision
```

因此：

```text
h2 topology-two-level result = unknown
```

禁止根据 observed RSS `~12.7 GB` 推断收敛结果。

---

## 10. h=2 direct 与 action 验证审查

尚未完成：

```text
1. h=2 actual explicit vs matrix-free action equivalence；
2. h=2 auxiliary MUMPS OOC direct；
3. h=2 explicit condensed MUMPS OOC direct；
4. h=2 auxiliary vs condensed field/R/T/A reference。
```

当前缺失原因是执行额度停止，不是已证明资源失败。

因此：

```text
h2 physical equivalence = strongly supported by h5 but not directly closed
h2 direct reference = pending
```

---

## 11. MPI 审查

matrix-free condensation utilities 已有 MPI synthetic tests。

但是 topology-aware slab smoother 当前代码明确要求：

```text
MPI size = 1
```

所以 h=5 iterative breakthrough 和 h=2 running case 都是串行 PETSc profile。

Task026 当前不能声称：

```text
MPI-scalable two-level solver
```

后续必须实现：

```text
- distributed slab ownership；
- cross-rank overlap / ghost dofs；
- parallel coarse projection；
- MPI1/MPI4 residual consistency；
- MPI memory scaling。
```

---

## 12. Gate V1

| Gate | Status | Evidence |
|---|---|---|
| Task025 freeze | pass | selective merge boundary recorded |
| 2D field/RTA equivalence | pass | machine precision |
| 2D actual action | pending | not run |
| 3D h5 explicit condensation | pass | field/action/RTA |
| h5 matrix-free action | pass | `3.64e-15` max reported actual error |
| h5 repeated-apply RSS | pass | 1000 applies stable |
| h5 iterative residual | pass | `9.999e-10` |
| h5 official R/T/A | pass | closure `~1e-12` |
| h2 plain iterative | fail | `0.166485` |
| h2 two-level | pending | result not committed |
| h2 actual action | pending | not run |
| h2 direct/OOC | pending | not run |
| MPI two-level | fail/not implemented | MPI1 only |
| angle/wavelength robustness | not run | h2 gate not closed |
| Task026 final | partial_pass_research | closure required |

---

## 13. Merge recommendation V1

### Review 后可选择性合并

```text
- src/solvers/condensed_dtn.py 的通用 condensation utilities；
- static-condensation dense/synthetic tests；
- matrix-free condensed operator；
- auxiliary recovery/back-substitution；
- h5 explicit/matrix-free/direct regression；
- complex-dot regression；
- Task026 文档与小体积 outcomes。
```

### 继续保留为 research-only

```text
- topology z-slab smoother；
- Floquet vector-hat coarse basis；
- physical-RHS enriched coarse basis；
- h2 plain/two-level profiles；
- large restart settings；
- all parameter-specific PC tuning。
```

### 不修改

```text
ordinary production default
existing auxiliary DtN reference path
```

在 h=2 residual、R/T/A 和 MPI Gate 通过前，不建议合并整个 Task026 research runner 到 production mainline。

---

# PART II：Task026 收尾工作任务书

## 14. 收尾目标

Task026 收尾阶段不再扩展新路线，只关闭现有证据链。

必须回答：

```text
1. h=2 topology two-level 是否比 plain ILU2 和 Task025 cached-Schur 更好？
2. h=2 matrix-free action 是否与 explicit condensation 等价？
3. h=2 auxiliary/condensed direct reference 是否可获得？
4. h=2 是否能达到 strong 或 production residual？
5. topology two-level 是否可以 MPI 化并保持一致？
6. 当前 h=5 coarse space 是否对小范围 angle/wavelength perturbation 稳定？
```

Task026 最终成功标准仍为：

```text
h=2 full true residual <= 1e-6
official R/T/A pass
peak RSS < 14 GB
no auxiliary global unknowns in iterative operator
no Q cache
MPI1/MPI4 consistency
```

---

## 15. Closure Stage A：回收正在运行的 h=2 two-level case

第一优先级，不得跳过。

### A1. 检查现有运行

检查：

```text
results/
Docker container state
stdout/stderr
process exit status
raw run directory
```

如果运行已经完成，提交：

```text
two_level.json
residual_history.csv
resource summary
command line
commit SHA
container/image metadata
```

如果运行失败或被终止，必须记录：

```text
last completed iteration
last reported residual
last RSS/current/peak
wall time
failure signal
swap-in/swap-out
whether setup or solve failed
```

不得只保留 `system_metadata.json`。

### A2. monitor 改为流式写盘

当前 monitor 只在进程结束后写 CSV，长任务失败时会丢失 history。

必须修改为：

```text
rank0 append/flush every monitor_stride
atomic temp-file or append-only CSV
record iteration, reported residual, explicit true residual checkpoint, RSS, elapsed
```

建议每 5 或 10 步显式计算一次 true residual，不要每步都增加昂贵 MatMult。

### A3. h=2 100-step Gate

比较：

```text
plain ILU2 residual = 0.166485
Task025 cached-Schur residual = 0.118475
```

判定：

```text
positive signal: residual <= 0.10
strong signal: residual <= 0.05
strong gate: residual <= 1e-2
production gate: residual <= 1e-6
```

停止条件：

```text
- 100 步 residual >= 0.14：停止当前 profile，不盲目延长；
- 100 步 residual 0.10~0.14：只允许一次有限参数 refinement；
- 100 步 residual < 0.10 且尾部仍明显下降：允许延长；
- peak RSS >= 14 GB 或持续 swap thrashing：停止。
```

输出：

```text
outcomes/h2_two_level_recovered_run.json
outcomes/h2_two_level_residual_history.csv
outcomes/h2_two_level_gate.csv
outcomes/h2_two_level_resource.csv
```

---

## 16. Closure Stage B：h=2 actual action equivalence

必须在同一 h=2 assembled system 上构造：

```text
explicit condensed operator
matrix-free condensed operator
```

至少测试：

```text
random vector
physical condensed RHS
plain iterative solution
如可用：two-level iterative solution
selected modal trace-related vector
```

指标：

```math
\frac{\|A_{explicit}x-A_{mf}x\|}{\|A_{explicit}x\|}.
```

Gate：

```text
all action errors <= 1e-11
MPI1/MPI4 within reduction tolerance
```

如果 explicit matrix 因内存不能完整保留，可采用：

```text
block-wise/reference port product action
or isolated explicit-action process
```

但不得只用 synthetic test 替代实际 h=2 action。

输出：

```text
outcomes/h2_matrix_free_action_equivalence.csv
outcomes/h2_action_memory.csv
```

---

## 17. Closure Stage C：h=2 direct/OOC reference

在独立进程中分别尝试：

```text
A. auxiliary augmented + MUMPS OOC
B. explicit condensed + MUMPS OOC
```

要求：

```text
native complex system
no real split
one route per clean process
no simultaneous auxiliary/condensed matrix retention
release Python temporary arrays before factor setup
record physical RSS and swap separately
```

必须记录：

```text
matrix rows/nnz
port-product nnz
ordering
MUMPS memory estimates if available
factor setup time
solve time
OOC file size
swap-in/swap-out
peak physical RSS
failure phase
```

成功 Gate：

```text
true residual <= 1e-9
auxiliary vs condensed FE field error <= 1e-7
R/T/A difference <= 1e-7
closure difference <= 1e-7
```

如果 direct solve 无法完成，不得反复无边界尝试。最多允许：

```text
1. baseline ordering
2. one memory-oriented ordering/OOC profile
```

随后必须形成明确的 resource failure report。

输出：

```text
outcomes/h2_auxiliary_direct_ooc.csv
outcomes/h2_condensed_direct_ooc.csv
outcomes/h2_direct_equivalence.csv
outcomes/h2_direct_resource_failure.md
outcomes/h2_ooc_swap_log.md
```

---

## 18. Closure Stage D：two-level profile 的有限 refinement

只有 Closure Stage A 得到 positive signal 才执行。

禁止重新做无边界参数扫描。

允许的候选维度：

```text
num_slabs = current 8 plus at most one alternative
coarse_intervals = 24 plus at most 32 or wavelength-rule-derived value
overlap = current 0.25 plus at most one alternative
ILU level = current 2, or level 1 if memory must be released
restart = 50 and at most 100
post_smooth = false unless independent evidence supports it
```

优先按物理规则选择 coarse resolution：

```text
coarse z spacing <= lambda_material / 2
prefer <= lambda_material / 3 near grazing/strong variation
```

必须记录：

```text
coarse dimension
coarse condition number
smallest singular value
basis rank after orthogonalization
preconditioner setup time
per-apply time
iteration count
true residual
peak RSS
```

停止条件：

```text
- refinement 相对 current profile 改善 < 20%：停止；
- coarse condition > 1e10 或 rank loss：重新构造 basis，不使用 pinv 掩盖；
- per-PC apply 增长 > 2x 且 residual 收益 < 2x：淘汰；
- physical-RHS enrichment 去除后完全失效：标记 overfit risk。
```

输出：

```text
outcomes/h2_two_level_ablation.csv
outcomes/h2_coarse_basis_diagnostics.csv
outcomes/h2_pc_cost_breakdown.csv
```

---

## 19. Closure Stage E：MPI-compatible topology two-level

该阶段在 h=2 串行 profile有明确正信号后执行。

目标：

```text
MPI1 and MPI4 use the same physical slab decomposition
not one MPI rank = one slab
```

需要实现：

```text
- distributed cell-to-slab assignment；
- global/owned/ghost FE dof collection；
- cross-rank overlapping patch IS；
- deterministic slab numbering；
- distributed coarse basis；
- global coarse Gram/Galerkin products；
- one replicated small coarse factor or distributed small solve；
- correct complex inner products。
```

Gate：

```text
MPI1/MPI4 matrix-free action difference <= 1e-11
MPI1/MPI4 true residual difference <= 1e-8
R/T/A difference <= 1e-8 when converged
MPI4 peak total RSS < MPI1 total RSS or has justified overhead
no rank0 FE-vector allgather
```

输出：

```text
outcomes/two_level_mpi_design.md
outcomes/two_level_mpi_consistency.csv
outcomes/two_level_mpi_memory.csv
```

---

## 20. Closure Stage F：h=5 small parameter perturbation check

该阶段不做完整参数矩阵，只检查 coarse-space 过拟合风险。

在 h=5 上使用完全相同的 solver rule，不进行逐点手工调参，测试：

```text
theta = 78, 80, 82 deg
lambda = 13.0, 13.5, 14.0 nm
```

至少包括：

```text
reference case
one lower-angle case
one higher-angle case
one shorter-wavelength case
one longer-wavelength case
```

每个 case 重新按参数生成 Floquet phase basis，但保持：

```text
num_slabs rule
coarse-spacing rule
shift rule
ILU level
restart
stopping criteria
```

记录：

```text
iterations
residual
coarse dimension
coarse condition
peak RSS
setup/solve time
R/T/A if residual <= gate
```

资格判断：

```text
all h5 cases residual <= 1e-6
max iterations / min iterations <= 3
no manual point-specific parameter changes
```

该阶段只验证局部参数稳定性，不得称为完整 parameter robustness。

输出：

```text
outcomes/h5_local_parameter_robustness.csv
outcomes/h5_coarse_condition_map.csv
outcomes/h5_parameter_failure_modes.md
```

---

## 21. Closure Stage G：补齐二维 actual action test

使用真实二维 EUV case，比较：

```text
auxiliary-derived condensed action
existing explicit outer-product action
```

至少对：

```text
random vector
physical RHS
converged direct solution
```

Gate：

```text
relative action error <= 1e-12
```

输出：

```text
outcomes/two_d_actual_action_equivalence.csv
```

---

## 22. Task026 最终 Gate

### Architecture Gate

```text
h5 auxiliary/explicit/matrix-free action and physics = pass
h2 actual action = pass
no Q cache / no iterative auxiliary unknown = pass
```

### Solver Gate

```text
h2 full true residual <= 1e-6
peak RSS < 14 GB
reasonable iteration count reported
```

### Physics Gate

```text
h2 official R/T/A completed
energy closure <= 1e-6
comparison against direct reference or justified reference <= 1e-6
```

### Parallel Gate

```text
MPI1/MPI4 consistency pass
no serial-only topology PC in production claim
```

### Robustness Qualification

```text
h5 local angle/wavelength perturbation pass
```

只有上述 Gate 全部通过，Task026 才能标记：

```text
completed_production_candidate
```

否则应按以下之一关闭：

```text
architecture_success_solver_research_only
or
partial_pass_h2_unresolved
```

---

## 23. 必须更新的结果文件

收尾后必须更新或新增：

```text
outcomes/summary.md
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
outcomes/run_log.txt
outcomes/parameters.json
outcomes/h2_two_level_recovered_run.json
outcomes/h2_two_level_residual_history.csv
outcomes/h2_matrix_free_action_equivalence.csv
outcomes/h2_direct_equivalence.csv
outcomes/h2_two_level_ablation.csv
outcomes/two_level_mpi_consistency.csv
outcomes/h5_local_parameter_robustness.csv
outcomes/two_d_actual_action_equivalence.csv
```

大体积 factor、matrix、mesh 和 field 结果保留在 `results/`，不得提交 Git。

---

## 24. 最终审查结论 V1

Task026 已经完成本项目中一个重要的结构性转向：精确 matrix-free condensation 在不改变 modal-port 物理的前提下，消除了 auxiliary global unknown、response cache 和 \(A_{FE}^{-1}C\) 依赖。h=5 上已经获得 direct、action、field、R/T/A 和 production-like iterative residual 的完整闭环。

当前主要不确定性已经从“端口代数结构是否可行”转变为：

```text
problem-informed z-slab / Floquet coarse PC
能否在 h=2、MPI 和参数变化下保持有效。
```

因此 Task026 不应另起新方向，而应严格完成上述收尾任务。首先回收 h=2 background result，再补 h=2 action/direct reference；只有 h=2 two-level 有明确正信号时，才进行有限 refinement、MPI 化和局部参数鲁棒性测试。
