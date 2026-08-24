# Task038-extra Review Report V10：面向 0.7 nm / 2 TiB 主线的 p-robustness 与 p6 资源双资格

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V10
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = bbd0447f2e798afad0707deae56082658a31864f
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 99 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v9.md
reviewed_outcome                        = docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v9.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
V9_P0                                   = ACCEPTED_PASS
V9_P1_p2_eight_cases                    = ACCEPTED_INDIVIDUAL_PASS
V9_P1_p3_mpi1_random                    = ACCEPTED_FAILED_AT_FIXED_MEMORY_ITERATION_CAP
V9_P1_remaining_seven_cases             = NOT_RUN_BY_GATE
current_memory_first_lifecycle          = ACCEPTED_ARCHITECTURAL_PASS
current_multiplicative_LOR_HX_v1        = HOLD_FOR_ONE_FINAL_BOUNDED_QUALIFICATION
additive_LOR_HX_v2                      = CLOSED; do not reactivate
primary_blocker_A                       = p-robust eventual convergence
primary_blocker_B                       = measured p6/h10 complete live-set memory
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
production_Krylov                       = right-preconditioned GMRES
production_restart                      = 20, fixed
residual_replacement_period             = 20 iterations, fixed
continuous_authorized_batch             = Q0 through Q6 below, conditional on explicit branches
mandatory_review_stop                   = after Q6 or any earlier hard stop
p6_h10_setup_only                       = independently authorized after Q0 algebra pass
p6_h10_positive_longrun                 = conditionally authorized
p6_h10_physical_MPI1                    = conditionally authorized
p6_h10_MPI2_physical                    = not authorized in V10
p6_h5                                   = not authorized in V10
full_0p7nm_PDE                          = forbidden
0p7nm_2TiB_new_capacity_audit           = not authorized until measured p6 evidence exists
ordinary_default_change                 = forbidden
master_merge                            = forbidden
response_required                       = response_v10.md
```

本 Review 严格围绕最终目标：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

当前开发机的 `<2,000,000,000 B` p6/h10 战略线不是最终机器内存上限，而是约千倍规模外推前必须满足的架构资格线。V10 不再扩散到新的 transmission、slab、spectral coarse、GAMG 参数或 Krylov 参数族，只回答两个直接决定主线能否继续的问题：

1. 当前 LOR/HX 路线在升阶后是否至少能够在固定内存生命周期下最终收敛；
2. 完整 p6/h10 LOR/HX live set 是否真实低于 2 GB，而不是只存在纸面预算。

只有两项均通过，才允许进入 p6 正定辅助长求解和 p6 物理 Maxwell MPI1。

---

# 1. 对 Response V9 的审阅

## 1.1 接受的正结果

V9 P0 已建立并验证：

```text
right GMRES restart=20
每20步销毁本周期KSP/Krylov basis
每20步以exact operator重算explicit true residual
只保留当前solution继续下一周期
solution-only checkpoint
checkpoint identity / hash / ownership fail-closed
```

该生命周期通过意味着：

> 总迭代数增加时，Krylov 常驻 basis 不必随历史长度增长；可以用时间换内存。

V9 P1 的 p2/h50、MPI1/MPI2、random/gradient/curl/checkerboard 共 8 个 individual case 全部达到：

```text
final explicit true residual <= 1e-8
PC linear / finite / repeatable
input unchanged
valid high-space primal output
swap = 0
```

且已完成 p2 MPI pair 的 exact source/action identity 与 residual-based action bound 均在限值内。以上接受为当前路线的低阶正信号。

## 1.2 接受的负结果

p3/h50、MPI1、random 在冻结设置：

```text
right GMRES
restart = 20
max_it = 2000
residual replacement every 20
```

下得到：

```text
final explicit true residual = 0.010278389622635529
classification                = FAILED_AT_FIXED_MEMORY_ITERATION_CAP
cycle process-tree peak       = 155,860,992 B
cycle process-tree swap       = 0 B
one-apply rho diagnostic      = 76.31177801908873
```

200–2000 步 checkpoint 为：

| iteration | explicit true residual |
|---:|---:|
| 200 | `0.020121591456069118` |
| 400 | `0.017040041972196853` |
| 600 | `0.015105083608221234` |
| 800 | `0.014102818581032258` |
| 1000 | `0.013302270148598451` |
| 1200 | `0.012632596140229997` |
| 1400 | `0.011947247810146767` |
| 1600 | `0.011291414776885363` |
| 1800 | `0.010741673284057653` |
| 2000 | `0.010278389622635529` |

该结果证明：

```text
内存生命周期没有失败
但当前PC缺少已证明的p-robustness
```

不能把下降趋势外推成 p6 或物理问题的成功，也不能只把上限从 2000 改成 3000/5000 后反复试探。

## 1.3 为什么仍值得做最后一次有界资格

p3 residual 尚未形成完全平台；同时当前记录不能区分退化来自：

```text
high-order <-> LOR global transfer / spectral equivalence
LOR edge auxiliary operator
HX decomposition
scalar nodal PCGAMG approximate inverse
restart20 memory-first cycle
```

因此 V10 只允许：

- 一次小模型 exact-reference 分解诊断；
- 一次固定上限的 p3 eventual-convergence formal；
- 一次与 p3 收敛解耦的 p6/h10 setup-only 资源实测。

这三项足以决定当前 LOR/HX 是否继续；禁止再产生开放式 v2/v3 参数族。

---

# 2. 本轮每项工作消除的最终目标 blocker

| 阶段 | 直接消除的 blocker | 与 0.7 nm / 2 TiB 的关系 |
|---|---|---|
| Q0 exact reference | 判断升阶退化是 LOR 基础代数还是近似 HX/PCGAMG | 避免在错误辅助空间上继续做大规模 PDE |
| Q1 p3 50k | 判断 fixed restart20 是否至少具有 eventual convergence | 证明“时间换内存”是否在升阶后仍成立 |
| Q2 p6 setup-only | 实测完整 LOR/HX live set 是否 `<2 GB` | 为约千倍规模的 2 TiB 外推提供必要 p6 锚点 |
| Q3 decision | 关闭失败 family，防止无限参数扫描 | 保护开发资源并保留可审计负证据 |
| Q4 p6 positive | 验证高阶正定辅助问题最终可解且内存有界 | 物理不定 Maxwell 前的最后数值基础 Gate |
| Q5 p6 physical MPI1 | 求解当前 exact Maxwell + DtN 并恢复 official physics | 直接建立任意三维 Full3D iterative authority 锚点 |

任何不回答上述 blocker 的旁支工作，本轮都不授权。

---

# 3. 全局不变量与禁止项

## 3.1 继续使用的冻结组件

```text
T1 full3d_iterative opt-in .dat contract
T2 full-space matrix-free Maxwell volume action
T3 dynamic streaming Fourier-DtN
T4/R2/R3 Floquet/MPC/canonical source authority
V9 memory-first restart20/checkpoint lifecycle
multiplicative-sequential LOR-HX v1
```

## 3.2 禁止修改或扫描

```text
restart 10/30/40/80
FGMRES / GCROT / LGMRES / BiCGStab
edge Jacobi omega
shift / auxiliary coefficient
PCGAMG type / smoother / threshold / levels
V-cycle count
HX correction order
additive-v2
third HX variant
new slab / transmission / trace-harmonic / local-spectral family
high-order global AIJ
global direct coarse solve
FE-sized numeric allgather
real/imag 2N production split
```

## 3.3 唯一 Krylov 生命周期

```text
right-preconditioned GMRES
restart = 20
zero initial guess for a fresh run
previous solution as the next cycle initial guess
explicit unpreconditioned true residual is authority
residual replacement every 20 steps
completed-cycle KSP and basis destroyed before next cycle
solution-only checkpoint
```

Q0 的小模型 direct solve 仅用于 exact-reference oracle，不得进入 production PC 或 p6 路线。

---

# 4. Q0：p3 exact-reference triage

## 4.1 目的

在同一个：

```text
p3/h50
MPI1
random source
positive high-order B_H
```

上判断当前 2000-step 退化来自哪一层。

## 4.2 允许的两个 exact reference

### Reference E：exact LOR edge inverse

```text
high dual residual
-> T_HL / owner route
-> exact solve of small LOR edge B_L
-> T_LH
-> high primal correction
```

小模型允许：

```text
PETSc PREONLY + LU/MUMPS
```

仅作 oracle。必须记录 direct residual、matrix rows/NNZ/bytes、canonical identities 与 component hashes。

### Reference N：exact nodal HX replay

保持冻结 multiplicative HX 顺序，只把每个 scalar nodal `PCGAMG` V-cycle替换为同一小模型上的 exact scalar nodal solve；edge Jacobi、G/Pi maps、transfer、顺序均不改变。

## 4.3 Q0 必须验证

```text
exact high RHS / action identity
high<->LOR canonical route
edge orientation and phase once
exact edge direct residual <= 1e-12
exact nodal direct residual <= 1e-12
PC output finite
input unchanged
valid high-space primal constraint <= 1e-12
repeat relative <= 1e-13
```

并分别以：

```text
right GMRES
restart = 20
max_it = 500
final explicit true residual <= 1e-8
```

测试 Reference E 与 Reference N。

## 4.4 Q0 决策

| 结果 | 分类与后续 |
|---|---|
| Reference E 不能在 500 步达到 `1e-8` | `LOR_AUXILIARY_FOUNDATION_FAIL`; 关闭整个当前 LOR family，Q1–Q5 不运行 |
| Reference E 通过，Reference N 快速通过 | LOR 与 HX 分解可行，主要 blocker 指向 PCGAMG approximate inverse |
| Reference E 通过，Reference N 仍明显慢 | LOR 可行，但当前 HX decomposition 不具 p-robustness |
| 任一 exact reference 存在 canonical/algebra defect | 停止；只允许修复一个明确 implementation defect，需新 review |

“快速”只作诊断，定义为 500 步内通过；Q0 唯一硬要求是 Reference E 的 algebra 和最终 residual 通过。

## 4.5 Q0 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p3_exact_reference_triage.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json
```

---

# 5. Q1：p3 fixed-memory eventual-convergence formal

## 5.1 启动条件

只有 Q0 Reference E 通过，才允许运行 Q1。

## 5.2 冻结案例

```text
p3/h50
MPI1
random source
multiplicative-sequential-v1
right GMRES
restart = 20
```

旧 2000-step negative 永久保留。Q1 必须使用 fresh source SHA、fresh artifact root 和 fresh zero initial guess；不得覆盖或复用旧 raw 目录。

## 5.3 固定上限

```text
total max_it             = 50,000
residual replacement     = every 20
checkpoint interval      = 1,000
final residual limit     = 1e-8
```

50,000 是本 family 的最终 p3 cap；失败后不得继续增加到 75k/100k。

## 5.4 资源 Gate

```text
process-tree peak RSS       < 500,000,000 B
process-tree/rank swap      = 0
cycle KSP destroyed         = true for every cycle
retained Krylov basis       = none across cycles
checkpoint vector roles     = solution only
nonfinite                   = false
```

该 500 MB 仅为小案例 safety Gate，不是 p6 2 GB authority。

## 5.5 数值 Gate

成功仅定义为：

```text
final explicit true residual <= 1e-8
```

以下只记录为 performance：

```text
iteration 2000 / 5000 / 10000 / 20000 / 30000 / 40000 / 50000
log residual slope
wall time
matvec / PC apply
```

50,000 步仍未通过时，分类：

```text
MULTIPLICATIVE_LOR_HX_V1_CLOSED_BY_P3_EVENTUAL_CAP
```

不得根据下降趋势外推 PASS。

## 5.6 Q1 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p3_eventual_convergence.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_eventual_convergence_v1.json
```

---

# 6. Q2：独立 p6/h10 setup-only 2 GB 资格

## 6.1 与 Q1 的关系

Q2 回答资源架构问题，不能被 p3 的 2000-step 数值失败永久遮蔽。

启动条件：

```text
Q0 Reference E algebra/final residual通过
```

Q2 在此条件下必须运行，无论 Q1 最终 PASS 或 FAIL。这样可获得对 0.7 nm / 2 TiB 主线直接有用的 measured p6 资源锚点。

## 6.2 冻结案例

```text
13.5 nm
p6/h10
MPI1
current exact mesh/material/Floquet identity
multiplicative LOR-HX v1
```

## 6.3 必须构造的完整 live set

```text
mesh / p6 Nedelec space / MPC
T2 matrix-free volume action
T3 streaming Fourier-DtN retained data
LOR refined topology
high<->LOR packed owner-local maps
LOR edge positive AIJ
scalar nodal AIJ
G / Pi representation
one scalar PCGAMG hierarchy
all PC work vectors
one restart20 KSP cycle live set
source / residual / solution vectors
watchdog / provenance
checkpoint reserve
```

不得用 isolated component bytes代替完整同时存活对象。

## 6.4 执行内容

```text
cold setup
-> 10 repeated PC applies on a deterministic finite source
-> one 20-step positive GMRES cycle
-> exact true residual recomputation
-> destroy KSP cycle
-> measure post-cycle retained
-> destroy/rebuild selected lifecycle once
```

这不是最终数值资格；20 步 residual只作 diagnostic。

## 6.5 Q2 资源 Gate

```text
cold / setup / apply / one-cycle process-tree peak < 2,000,000,000 B
post-setup retained                              < 1,800,000,000 B
process-tree/rank swap                           = 0
no high-order global AIJ                         = true
no global direct coarse                          = true
no FE-sized numeric allgather                    = true
no real/imag hierarchy duplication               = true
all 10 applies finite / repeat relative          <= 1e-13
PC linearity relative                            <= 1e-12
valid high-space primal constraint               <= 1e-12
```

任何阶段达到 2 GB 立即 controlled stop。不得预热 cache 后只报告 warm peak。

## 6.6 Q2 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6h10_lor_hx_setup_resource.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p6h10_lor_hx_setup_resource_v1.json
```

---

# 7. Q3：唯一的路线决策

Q0–Q2 后必须按下表执行，不得自行选择更有利的分支。

| Q0 Reference E | Q1 p3 50k | Q2 p6 setup | 后续 |
|---|---|---|---|
| FAIL | 任意 | 不运行 | 关闭整个 LOR family；写 closeout |
| PASS | FAIL | FAIL | 数值与资源均失败；关闭 LOR/HX |
| PASS | FAIL | PASS | 当前 HX v1 数值关闭；只写 LOR edge geometric-MG handoff，不实现新 solver |
| PASS | PASS | FAIL | eventual convergence有正信号但资源失败；不得进入p6 solve |
| PASS | PASS | PASS | 允许 Q4 p6 positive longrun |

若 Q1 FAIL、Q2 PASS，必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_edge_geometric_mg_handoff.md
```

该文档只冻结下一候选需要复用的 measured rows/NNZ/maps/bytes 与禁止项；本轮不得实现、测试或扫描新 multigrid。

---

# 8. Q4：条件 p6/h10 positive fixed-memory longrun

## 8.1 启动条件

```text
Q0 Reference E PASS
Q1 p3 50k PASS
Q2 p6 setup resource PASS
```

三项缺一不可。

## 8.2 案例顺序

```text
1. p6/h10 MPI1 random
2. 只有 random PASS 后运行 p6/h10 MPI1 gradient
```

## 8.3 Krylov 与上限

```text
right GMRES
restart = 20
residual replacement every 20
solution checkpoint every 1,000
max_it = 100,000 per source
final explicit true residual <= 1e-8
```

100,000 是 p6 positive 的最终 cap；不得继续增加。

## 8.4 资源 Gate

```text
每个 uninterrupted segment process-tree peak < 2,000,000,000 B
process-tree/rank swap = 0
KSP basis not retained across cycles
checkpoint is solution-only
nonfinite = false
PC legality remains pass
```

如果 correctness 依赖多个 checkpoint/resume segment，分类为：

```text
CORRECTNESS_PASS_RESOURCE_SEGMENTED_NOT_FULL_WORKFLOW
```

不得称完整 workflow 资源 PASS。若同一 uninterrupted run 完成全部 solve，则可形成完整 positive workflow resource authority。

## 8.5 Q4 停止条件

```text
random达到100,000仍未通过 -> 当前v1正式关闭，gradient不运行
random通过但gradient失败 -> 当前v1不具source robustness，Q5不运行
任一资源Gate失败          -> Q5不运行
```

## 8.6 Q4 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6h10_positive_eventual_convergence.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p6h10_positive_eventual_convergence_v1.json
```

---

# 9. Q5：条件 p6/h10 exact physical Maxwell MPI1

## 9.1 启动条件

Q4 random 与 gradient 均通过最终 `1e-8`，且 setup/solve 资源 Gate 未失败。

## 9.2 冻结物理

```text
13.5 nm p6/h10 authority input
complex128
Nedelec H(curl)
lossy complex materials
dual Floquet
exact matrix-free volume action
exact dynamic streaming Fourier-DtN
current physical RHS authority
multiplicative LOR-HX v1 as auxiliary PC
```

## 9.3 求解合同

```text
right GMRES
restart = 20
residual replacement every 20
solution checkpoint every 1,000
max_it = 100,000
final explicit true residual <= 1e-6
```

迭代数与 wall time只作性能指标。

## 9.4 完整工作流

```text
cold setup
-> solve
-> explicit true residual pass
-> save minimum recovery packet
-> destroy KSP / Krylov / hierarchy objects not needed by recovery
-> verify RSS decrease
-> official E/H recovery
-> R/T/A
-> A_volume
-> 12+12 diffraction channels
-> final provenance/hash closure
```

## 9.5 数值、物理与资源 Gate

```text
final explicit true residual <= 1e-6
all official fields finite
R/T/A and A_volume within frozen direct-authority tolerances
12+12 channels within frozen authority tolerances
energy closure within frozen authority tolerance
complete uninterrupted process-tree peak < 2,000,000,000 B
process-tree/rank swap = 0
release-before-recovery RSS decrease measured
```

若 segmented solve 达到 residual但没有一次 uninterrupted complete workflow：

```text
CORRECTNESS_PASS_RESOURCE_SEGMENTED_NOT_FULL_WORKFLOW
```

若 residual通过但 recovery/postprocess使全过程峰值超过2 GB：

```text
NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL
```

## 9.6 Q5 证据

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6h10_physical_memory_first_mpi1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p6h10_physical_memory_first_mpi1_v1.json
```

本 Review 不授权 MPI2 physical、h5 或 0.7 nm PDE。完成 Q5 后必须停止审阅。

---

# 10. Q6：response、总结与停止

无论在哪个阶段停止，都必须更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/task038_extra_full3d_iterative_0p7nm/response_v10.md
```

`response_v10.md` 至少回答：

1. branch、formal source SHA、base、ahead/behind、worktree、ABI、threads；
2. Q0 exact edge/nodal reference 的 residual、iterations、canonical/algebra结果；
3. Q1 p3 50k 的完整 checkpoint residual history、峰值、swap、最终分类；
4. Q2 p6 rows/NNZ/maps/hierarchy bytes、cold peak、retained、10 apply、20步screen；
5. Q3 实际触发的决策分支；
6. 若 Q4 运行，两个 p6 positive source 的最终 residual、cycles、checkpoints和资源；
7. 若 Q5 运行，physical final residual、全过程峰值、release RSS、official E/H、R/T/A、A_volume、12+12 channels；
8. 哪些是 measured / derived / diagnostic / not_run / failed / controlled_stop；
9. tests、commands、raw/compact hashes、watchdog和provenance；
10. 对 0.7 nm / 2 TiB 主线消除了哪个 blocker，仍剩哪些 blocker。

提交并推送当前同一分支后停止等待 ChatGPT 审阅。

---

# 11. 明确禁止的结论

本轮不得因为：

```text
p3残差持续下降
p6 setup低于2GB
p6 positive通过
p6 physical MPI1通过
```

直接宣称：

```text
0.7 nm arbitrary-3D 已可行
2 TiB完整workflow已证明
MPI2已通过
h5/h1 scaling已通过
physical fields已网格收敛
```

即使 Q5 全部通过，也只建立：

> 13.5 nm、p6/h10、MPI1、当前 authority input 下的固定内存 Full3D iterative 正确性与资源锚点。

后续仍需 MPI2、h10→h5→更细实测、0.7 nm external-channel inventory、材料、DtN/hierarchy/MPI/recovery容量模型和最终物理误差资格。

---

# 12. 最终审阅结论

```text
V9 P0 memory-first lifecycle              = PASS / frozen
V9 p2 eight individual cases              = PASS / frozen
V9 p3 2000-step result                     = real controlled numerical negative
current blocker                           = p-robustness + unmeasured p6 live-set
V10 next action                           = Q0 exact reference + Q1 50k + Q2 p6 setup
new solver family in this batch           = forbidden
physical p6 MPI1                          = only after Q0/Q1/Q2/Q4 all pass
full 0.7 nm PDE                           = forbidden
```

这是一次最终且有界的 current-LOR/HX 资格，不是继续无限增加迭代上限或参数扫描。它保持主线不变：

```text
full-space matrix-free exact A
+ bounded-memory iterative solve
+ official physical recovery
+ measured p6 resource anchor
-> future 0.7 nm / 2 TiB capacity audit
```
