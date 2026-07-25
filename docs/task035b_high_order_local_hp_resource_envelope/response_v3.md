# Task035b Response V3：Review V2 集中回应

## 1. 交付身份与结论

```text
response_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
review_v2_commit = d547e9d7e903e9e8639346715770e56f9c17e86d
evidence_source_through = cf14e84f4a0f9216b6139a146eba78cdcfd45bb9
final_tested_source_head = 56ed6cdb44e90a820274092ac6661c1e6a95f934
metadata_delivery_head = documentation-only successor reported in Git handoff
geometry_scope = Task034 fixed rectangular block grating only
best_in_budget_candidate = fixed_p5trace_p6interior_h13_directional_z
best_candidate_full3d_equivalent_dofs = 89740
best_candidate_active_rows = 20120
best_candidate_significant_power = 10_of_12
best_candidate_significant_complex_amplitude = 10_of_12
same_error_12_plus_12_candidate_count = 0
hybrid_eligible_candidate_count = 0
ordinary_default_changed = false
master_merge_performed = false
user_hard_blocker = false
```

Review V2 的 setup、direct-memory 和 opt-in iterative 研究均取得了可复核
证据，但完整精度 Gate 仍未通过。最强预算内 h13 保持 `10/12 + 10/12`；
两个 fixed-DoF z-node 判别点分别只有 `8/12 + 8/12` 和 `7/12 + 8/12`；
selective-trace 仍只有 fixture/correctness capability，没有 actual channel
DWR、正式 runner 或候选 PDE。因此本批次状态是
`PARTIAL_WITH_CONTROLLED_NEGATIVES`，不能写成 Task035b 完成。

当前没有需要用户输入凭据、安装系统包或处理 ABI 的硬 blocker。剩余 blocker
是数值与 production integration：

- numerical blocker：没有 `<=90k` 且 `12/12 power + 12/12 complex
  amplitude` 的 Full3D 候选；
- production-integration blocker：actual channel-DWR selection、正式
  live-capture runner 和 standard-full-p6-storage selective PDE 尚未闭环。

## 2. 最强 accuracy authority 与 12 通道结论

独立 accuracy authority 仍是 fixed p5 trace + p6 cell interior、
directional-z h13 `(6,2,12)`：

| metric | measured authority |
|---|---:|
| Full3D-equivalent DoF | **89,740** |
| active rows | **20,120** |
| matrix NNZ | **11,013,212** |
| factor NNZ | **36,273,200** |
| factor fill | 3.294 |
| full explicit true residual | `5.81e-12` |
| significant power | **10/12** |
| significant complex amplitude | **10/12** |

失败并集仍为 `T(-4,0)`、`R(-4,0)`、`R(-5,0)`；h13 只有 260 DoF
headroom，不能直接增加完整 p6 trace 或整层网格。setup profiler 在同一
mesh 上测得的 `11,014,172` matrix NNZ 和 `35,746,600` factor NNZ 是
source-stage-specific setup authority，不覆盖上表的 accuracy authority。

### 2.1 Fixed-DoF z-node 两个判别点

| case | DoF / rows / matrix NNZ / factor NNZ | peak | residual | actual power / amplitude | decision |
|---|---:|---:|---:|---:|---|
| unchanged directional-z h13 authority | 89,740 / 20,120 / 11,013,212 / 36,273,200 | 6.411 GiB | `5.81e-12` | **10/12 / 10/12** | best in budget |
| h13 top-two phase redistribution | 89,740 / 20,120 / 11,013,212 / 36,273,200 | 5.886 GiB | `4.262e-12` | **8/12 / 8/12** | controlled negative |
| h14 exact reverse of h13 top-two move | 82,315 / 18,500 / 10,104,512 / 32,338,600 | 5.958 GiB | `7.006e-12` | **7/12 / 8/12** | controlled negative |

h14 reverse point运行前的 `9/12 + 11/12` 只是 derived projection；实测
是 `7/12 + 8/12`，不得把预测当 PDE 结果。两个 bounded points 都没有
超过各自 unchanged authority，且第二点已经是对第一点机制的精确反向判别。
因此 fixed-DoF z-node lane 在两个成本/精度负信号后关闭；不再进行节点盲扫，
历史 R5-slab 和这两个负结果全部保留。

### 2.2 冻结的完整 12 通道表

表中 `P/A` 分别表示 power 与 complex amplitude；`pass/fail` 使用未放宽的
`significant_channel_reference_v1` acceptance bands。selective trace
没有 actual candidate，因此全部为 `not_run`，不能从 fixture 推导通道结果。

| significant channel | best h13 P/A | h13 top2 P/A | h14 reverse P/A | selective trace P/A |
|---|---|---|---|---|
| `T(-7,0)_s` | pass / pass | pass / pass | pass / pass | not_run / not_run |
| `T(-5,0)_s` | pass / pass | fail / fail | fail / pass | not_run / not_run |
| `T(-4,0)_s` | fail / pass | fail / fail | fail / fail | not_run / not_run |
| `T(-2,0)_s` | pass / pass | pass / pass | pass / fail | not_run / not_run |
| `T(-1,0)_s` | pass / pass | pass / pass | pass / pass | not_run / not_run |
| `T(0,0)_s` | pass / pass | pass / pass | pass / pass | not_run / not_run |
| `R(-7,0)_s` | pass / pass | pass / pass | pass / pass | not_run / not_run |
| `R(-5,0)_s` | pass / fail | pass / fail | fail / fail | not_run / not_run |
| `R(-4,0)_s` | fail / fail | fail / fail | fail / fail | not_run / not_run |
| `R(-2,0)_s` | pass / pass | fail / pass | fail / pass | not_run / not_run |
| `R(-1,0)_s` | pass / pass | pass / pass | pass / pass | not_run / not_run |
| `R(0,0)_s` | pass / pass | pass / pass | pass / pass | not_run / not_run |
| **count** | **10 / 10** | **8 / 8** | **7 / 8** | **0 measured / 0 measured** |

三个 PDE 均通过 geometry/tag/Floquet/orientation、exact-sequence、scalar、
normalized vector、selected field/interface 和 full-residual 层级；通道
Gate 仍为正式否决项，不能被低 residual 或总 R/T 掩盖。

## 3. Physical selective trace：能力已推进，候选仍为零

`physical_selective_trace_execution_capability_v2.json` 只接受以下
fixture/correctness 能力：

- typed physical caller expansion 可从 Stage4b 入口进入 common flow 和
  DtN assembly-time condensation；
- complete periodic/Floquet pullback 由 caller expansion 唯一拥有，不与
  legacy MPC 同时传入；
- fixture 中 inactive missing-p6 modes 没有 PETSc rows，完整 p6 trace
  matrix 未构造后置零；
- generalized recovery 使用同一 caller pullback，不再执行重复 MPC
  backsubstitution；
- owner-aware PETSc MatShell 的 local-Schur action 与 fixture assembled
  action一致，不构造 global explicit matrix、global LU、replicated active
  vector 或 full-vector allreduce/allgather；
- default-off pre-release callback 能在 true-residual diagnostics 之后、
  solver release 与 postprocess 之前借用 `A/b/x/KSP`。

正式边界保持：

```text
evidence_class = fixture_and_correctness_only
actual_channel_dwr_selection = false
actual_enriched_residual_weighted_channel_dwr = false
formal_actual_pde_ready = false
runner_wired = false
selective_candidate_count = 0
selective_pde_run_count = 0
inactive_missing_rows_in_fixture = 0
Hybrid_eligible = false
```

### 3.1 为什么 reduced fixed-trace 与 generalized recovery 互斥

当前最强 h13/h14 authority 使用自定义 reduced element：local Schur 的
storage trace 本身只有 p5 trace，p6 只存在于 cell interior；恢复时写回
原 p5 trace，并由 legacy Floquet MPC 完成 backsubstitution。缺失的 p6
edge/face trace basis 在这个 storage element 中根本不存在。

selective p6 trace 路径则必须从 standard full-p6 N1curl storage element
出发，在 local 432-dimensional p6 trace storage 上形成 generalized
`C_K`，只给 p5 quotient rows 和被选中的 periodic-closed missing-p6
orbits 编 active rows。该 `C_K` 已包含 transitive periodic/Floquet
pullback；恢复必须由同一个 generalized expansion 完成，禁止再次 MPC
backsubstitution。

因此两条路径不能在同一 solve 中叠加：

```text
reduced fixed-p5-trace local Schur + legacy MPC recovery
    is mutually exclusive with
standard full-p6 storage + generalized selective C_K + generalized recovery
```

把 selective expansion 直接塞入 reduced fixed-trace element 会缺少需要
选择的物理 p6 trace storage modes；同时再传 legacy MPC 会重复约束和恢复。
正式候选必须切换到 standard full-p6 storage，在 assembly-time 通过
generalized `C_K` 物理省略 inactive rows，而不是复用 reduced element 或
先构造完整 p6 trace matrix 再置零。

### 3.2 Exact-sequence、orbit 与 active-row状态

| requirement | current evidence | formal candidate status |
|---|---|---|
| physical Piola/Riesz and orientation | fixture-qualified contracts | not run on h14 candidate |
| periodic transitive orbit/Floquet pullback | caller expansion fixture pass | actual selected orbit set absent |
| exact-sequence compatibility | fixture/correctness checks | formal candidate Gate not run |
| complement/local Schur action | algebraic fixture pass | actual enriched residual/DWR absent |
| active numbering | fixture owner-contiguous rows; inactive rows 0 | actual candidate rows/NNZ unknown |
| channel-aware DWR | API/contract groundwork only | `actual_channel_dwr_selection=false` |
| Stage4 execution | default-off plumbing present | formal runner and PDE count 0 |

这是一项工程正结果，但不是 selective-trace accuracy positive。

## 4. Cold/new-process-warm setup 子集分解

### 4.1 Phase timing

下表单位均为秒。`—` 表示该 authority 没有把该项独立拆出，不得以 0
替代。`non-KSP build` 与 MUMPS symbolic/numeric/backsolve、residual 和
postprocess 互斥报告。

| phase | h15 cold | h15 warm | h13 cold | h13 warm |
|---|---:|---:|---:|---:|
| module import | — | — | 2.292 | 1.423 |
| mesh build | — | — | 0.010 | 0.009 |
| function-space total | 7.704 | 2.674 | 7.835 | 2.725 |
| fixed-trace cold build | 7.569 | 0 | 7.698 | 0 |
| fixed-trace read/reconstruct | 0 | 0.044 / 2.532 | 0 | 0.046 / 2.585 |
| tensor total | 2.677 | 0 | 2.693 | 0 |
| `A_ii` factor / solve | — | — | 0.269 / 1.139 | 0 / 0 |
| local Schur total | 1.981 | 0 | 1.922 | 0 |
| condensed-class read / write | 0.061 / 3.228 | 0.845 / 0 | 0.180 / 3.716 | 1.020 / 0 |
| trace preallocation | 0.054 | 0.055 | 0.066 | 0.065 |
| cell-block insertion | 0.029 | 0.032 | 0.037 | 0.044 |
| base condensed matrix assembly | 8.741 | 1.770 | 8.649 | 2.074 |
| complete non-KSP build | **19.242** | **6.141** | **19.410** | **6.696** |
| DtN outer, including KSP | 25.212 | 12.333 | 32.864 | 19.564 |
| MUMPS symbolic | 0.132 | 0.136 | 0.154 | 0.159 |
| MUMPS numeric | 5.807 | 6.028 | 13.266 | 12.675 |
| backsolve | 0.031 | 0.028 | 0.034 | 0.034 |
| full explicit residual | 3.435 | 3.444 | 3.557 | 3.587 |
| postprocess total | 3.665 | 3.473 | 3.808 | 3.598 |
| common solver | **37.595** | **19.489** | **45.568** | **26.899** |

setup/resource profiles 通过 true residual 和 cold/warm scalar closure，但没有
重算 significant-channel comparison，所以不获得 accuracy credit。

这些 phase clocks 存在嵌套关系，不能相加后再除以 common-solver 时间来制造
“占比”。尤其当前 profiler 没有给出互斥的 `Python overhead` 总桶；能正式
报告的是 tensor、`A_ii`、Schur、preallocation、insertion、DtN、MUMPS、
residual 和 postprocess 的实测 phase time，不能把剩余时间全部归因于
Python。正式 cold 与 new-process persistent warm 已完成；same-process
second assembly、same-topology/new-RHS `<=2 s` stretch PDE 和
new-material/frequency invalidation PDE 未形成正式 timing authority，保持
`not_run`，只有 cache identity/invalidation fixture 证据。

### 4.2 加速语义

- h15 cold non-KSP build 从 Review V2 preoptimization `61.61 s` 降到
  `19.242 s`，是 `3.202x` 的 hash-bound complete-build 工程正结果，达到
  cold `>=2x` 与 25–30 s 目标；
- h15 warm non-KSP 为 `6.141 s`，达到 `<10 s`；cold→warm
  `3.133x` 只表示 persistent-cache reuse；
- h15 fixed-trace element component 相对前一 canonical implementation
  是 `13.2709 -> 7.5687 s = 1.753x`，不得把 complete-build 的 3.202x
  错写成每个子组件都达到 3.202x；
- h13 cold/warm non-KSP 为 `19.410/6.696 s`，cold→warm
  `2.899x` 只表示 cache reuse；没有 same-h13 preoptimization cold
  baseline，所以**不声明 h13 cold-code 2x 加速**；
- h13/h15 rows 和 matrix NNZ 比值只有 `1.192x/1.198x`，factor NNZ
  却是 `1.346x`，fill 从 `2.887` 增至 `3.246`。direct factor 成本不能
  按 DoF 线性外推。

缓存均绑定 geometry/material/wavelength/degree/orientation/source identity；
ordinary default 没有改成 research cache 路径。

## 5. MPI1/2/4/8 direct 内存与时间

同一 h15、74,890 Full3D-equivalent DoF、16,880 rows、
9,195,812 used matrix NNZ 的 cold direct rank study：

| MPI | process-tree RSS peak GiB | PSS sum GiB | USS sum GiB | factor NNZ | common solver s | MUMPS symbolic+numeric s | swap |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | **1.295** | 1.257 | 1.243 | 26,854,000 | 76.007 | 29.969 | 0 |
| 2 | 2.158 | 2.013 | 1.918 | 28,507,400 | 74.913 | 19.437 | 0 |
| 4 | 3.100 | 2.723 | 2.612 | 26,575,000 | 61.849 | 12.400 | 0 |
| 8 | 4.711 | 3.876 | 3.758 | 27,916,600 | **53.901** | **6.527** | 0 |

四点保持相同 mesh/operator、rows/NNZ、R/T 和 full residual。MPI1
`1.295 GiB` 是当前 direct 路径的**最低实测点**，不是数学、软件栈或
factor-free 下限。MPI8 相对 MPI1 使用 `3.64x` process-tree RSS，wall
time 仅改善 `1.41x`。因此早期 `5.8–6.4 GiB` 不是八九万 DoF 的最低
内存，也不能作为 0.7 nm 正式外推锚点。

每个 rank 在 MUMPS 阶段观察到预期的 3 个 Linux threads。MPI4/8 的
50-thread-per-rank 峰值出现在 solver-object release 后的 field
postprocess，结合 `libtbb` 与 futex-waiting workers，只能界定为
PyVista/VTK/TBB dormant pool；没有把它归因于 MUMPS/BLAS 有效并行。
本轮 rank records 没有冻结 CPU affinity，也没有记录 MUMPS ordering，
因此这两项为 `not_recorded`，不能据此声称 rank scaling 已完成完整的
ordering/affinity 资格化。

h13 MPI8 canonical cold/warm 的 process-tree peaks 为
`5.030/5.016 GiB`、PSS sums 为 `4.208/4.198 GiB`、USS sums 为
`4.098/4.089 GiB`，均为 0 swap。它们是 setup/resource measurements，
不是下限，并且 h13 accuracy 仍只有 `10/12 + 10/12`。

真实内存下限研究仍有明确 open gaps：本地运行没有取得任务专用 cgroup
peak，PETSc native-object bytes 和 allocator `malloc_info` 未形成正式
实测 ledger，MUMPS factor bytes 仍由 factor NNZ 及数据类型派生，Python/
MPI/PETSc/loader runtime floor 也没有从求解对象中完全隔离。因此当前只能
报告每个 MPI 配置的 simultaneous process-tree RSS/PSS/USS 和 factor
inventory；`1.295 GiB` 必须称为 best observed direct point，不能称为
runtime、native-object、factor-free 或生产环境的真实下限。

## 6. Iterative formal screens：三条 controlled negatives

三个 profile 都由独立 programmatic opt-in 配置运行，未用 raw PETSc
options；全部达到 200 iterations 上限而未收敛，所有 official
R00/R/T/A、channel 和 field outputs 均为 null/not produced。

| profile | factor inventory | final/initial unpreconditioned residual | explicit reduced / full recovered residual | peak / elapsed | official output |
|---|---|---:|---:|---:|---|
| GMRES(30) + Jacobi | global direct factor `0`；无 MUMPS symbolic/numeric | 0.861662 | 0.861662 / 0.861661 | 3.921 GiB / 39.534 s | none |
| FGMRES(30) + ASM(1)/ILU(0) | global factor `0`；local subdomain ILU active，local factor NNZ未记录 | 0.999661 | 0.999661 / 0.999659 | 4.462 GiB / 46.073 s | none |
| FGMRES(30) + physical z-slab ILU(0) + DtN-trace Galerkin | global factor `0`；22,280 local factor rows、9,576,512 local ILU NNZ、80×80 coarse dense LU | 0.996265 | 0.996265 / 0.996263 | 3.885 GiB / 49.946 s | none |

Jacobi 没有 global factor，但 residual Gate 失败，因此不是 factor-free
success。ASM 与 physical profile 含 local factors；physical profile 另含
coarse LU，明确 `strictly_factorless=false`。三个较低 RSS 只能作为
failed-screen resource evidence，不能称为合格解的内存下限或 0.7 nm
projection anchor。

assembled iterative lane 只有在出现实质不同的 spectral/auxiliary-space、
block-Schur 或 Fourier/DtN harmonic preconditioner 后才可重开。单纯把同一
谱问题换成 matrix-free operator 不足以重开 heavy PDE。

## 7. Matrix-free 状态

owner-aware selective-p6 trace MatShell 已通过 fixture correctness：

```text
global_explicit_matrix_constructed = false
global_matrix_storage_bytes = 0
global_LU_constructed = false
replicated_factor_allocated = false
replicated_active_vector_allocated = false
full_vector_allreduce_used_by_action = false
full_vector_allgather_used_by_action = false
inactive_missing_rows_allocated = 0
production_execution_enabled = false
candidate_promotion = false
```

它只实现 `sum_K C_K^H S_K C_K` 的 owner-aware local action 与 PETSc
ghost forward/reverse，尚无 production DtN action、preconditioner、KSP
profile、actual h14 selection 或正式 PDE。状态是
`correctness_only_matrix_free_action_ready`，不是 matrix-free solver
success，也没有内存/时间 authority。

## 8. Hybrid、M/DtN funnel 与 0.7 nm resource model v3

因为 `hybrid_eligible_candidate_count=0`：

| downstream item | status | reason |
|---|---|---|
| Full3D–Hybrid same-degree closure | `not_run` | no `12/12 + 12/12` Full3D candidate |
| Hybrid `M80/M120/M160` | `not_run` | selected-candidate Gate closed |
| optional `M240` | `not_run` | M funnel not started |
| external DtN order/evanescent buffer funnel | `not_run` | cannot separate from unresolved Full3D error |
| Hybrid 12-channel closure | `not_run` | no Hybrid field |
| 0.7 nm PDE | `not_run` | no production layout |
| resource model v3 | `not_run_by_selected_candidate_gate` | selected `N_equiv`、Hybrid fraction、M、component lifecycle unknown |
| predicted simultaneous peak | `null` | unknown components cannot be summed into a peak |
| 0.7 nm / 2 TiB feasibility | `unknown` | neither proven feasible nor universally disproven |

Task034 resource model v2.1 仍是 current-layout stress authority。Task035b 的
1.295 GiB MPI1 direct point、3.885–4.462 GiB failed iterative points和
5.030/5.016 GiB h13 setup points都不能取得 accuracy credit，不能缩放成
production v3。`2 TiB = 2048 GiB` 目标保留；只有 passing Full3D 候选、
Hybrid/M/DtN closure 与完整 measured/derived/predicted/unknown component
ledger 才能解除 `not_run`。

## 9. Controlled negatives、preserved failures 与 not-run

`outcomes/all_candidates.json` 与 `outcomes/all_candidates.csv` 是 68 个唯一
candidate rows 的 exhaustive index，source snapshot 为
`cf14e84f4a0f9216b6139a146eba78cdcfd45bb9`。以下表格集中列出其
controlled-negative、formal-not-pass 和 stopped/not-run lanes；没有删除
或改写任何历史负证据。

### 9.1 Controlled negatives

| lane / candidate IDs | result | evidence |
|---|---|---|
| global p6 h15 / same-error audit | channels fail；6/12 power、8/12 amplitude | `records/global_hexa_p5_p6_h15_assembly_time_condensed_independent_mpi8.json`; `records/global_hexa_p6_h15_vs_h10_same_error_audit.json` |
| fixed h15 baseline/dedup/preallocation | engineering improves；accuracy remains 6/12 + 7/12 | `records/fixed_p5trace_p6interior_h15_mpi8.json`; `records/fixed_p5trace_p6interior_h15_tensor_dedup_mpi8.json`; `records/fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json` |
| p4-trace regionwise N105 | resource positive；all formal accuracy layers fail | `records/regionwise_p4trace_p6interior_h10_mpi8.json` |
| p5-trace N62 | linear solve/resource measured but p5-trace+p4-interior low space is non-exact-sequence；not a valid accuracy candidate | `records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8.json` |
| h-vs-p proxy | vector favors h、strict-R favors p；strict-R/90k fail | `records/actual_sequential_h_vs_p_competition_mpi8.json` |
| Task035 tetra h50 theta0.4 | vector pass；strict-R/90k fail | `../094_hcurl_goal_oriented_adaptivity/records/actual_hp_budget_theta0p4_tetra_p5_p6_h50_mpi8.json` |
| DtN q31 | no recovery；6/12 + 7/12 | `records/fixed_p5trace_p6interior_h15_dtn_q31_mpi8.json` |
| scaled evanescent buffer1 | safe scaling；no recovery；6/12 + 7/12 | `records/fixed_p5trace_p6interior_h15_dtn_evanescent_buffer1_scaled_mpi8.json` |
| directional x / y controls | x 5/12 + 6/12；y 3/12 + 1/12 | `records/fixed_p5trace_p6interior_h15_directional_x_mpi8.json`; `records/y_only_global_p5_directional_control_comparison_v1.json` |
| directional z h14 / h13 | positive recovery but incomplete：7/12 + 9/12；10/12 + 10/12 | `records/fixed_p5trace_p6interior_h14_directional_z_mpi8.json`; `records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json` |
| h14 R5 slab bisect | count regression：5/12 + 9/12 | `records/fixed_p5trace_p6interior_h14_r5_slab_bisect_mpi8.json` |
| global p6 h14 trace discriminator | 9/12 + 12/12；DoF 92,850 over cap | `records/global_p6_h14_trace_discriminator.json` |
| h13 top2 / h14 exact reverse | actual 8/12 + 8/12；7/12 + 8/12 | `records/fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json`; `records/fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json` |
| assembled iterative Jacobi / ASM-ILU | 200 iterations，nonconverged，no official output | `records/h15_factor_free_iterative_mpi8_v1.json` |
| physical-slab/DtN iterative | 200 iterations，nonconverged，local ILU + coarse LU，no official output | `records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json` |

表中 `records/...` 均相对于
`benchmarks/cases/095_high_order_local_hp_resource_envelope/`。

### 9.2 Preserved formal failures

| failed evidence | status / reason | evidence |
|---|---|---|
| early independent-condensation run | incomplete process；not formal | `records/global_hexa_p5_p6_h10_p6_condensed_independent_mpi8.json` |
| N62 wrong-control preflight | PDE not launched | `records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8_wrong_control_preflight_failure.json` |
| N62 postprocess failure | not a formal result | `records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8_postprocess_failure.json` |
| Task035 theta0.3 evaluator failure | post-solve metadata failure preserved | `../094_hcurl_goal_oriented_adaptivity/records/actual_hp_budget_theta0p3_tetra_p5_p6_h50_mpi8.json` |
| first h15 channel-adjoint attempt | adjoint/recovery qualification failed | `records/fixed_p5trace_p6interior_h15_channel_adjoints_mpi8.json` |

### 9.3 Stopped / not-run

| lane | status / reason | evidence |
|---|---|---|
| p5-trace N18 | `not_run`；shares non-exact low space with N62 | `outcomes/high_p_memory_anatomy.md` |
| Task035 h37.5 p6 | preflight stop；214,050 DoF over gate | `../task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md` |
| hexa local-h | no qualified conforming transition implementation | `outcomes/local_hp_capability.md` |
| p7/h10 | projected DoF exceeds 90k by 183,581 | `records/p7_h10_capability_resource_gate.json` |
| unscaled buffer1 | numerical-safety preflight controlled stop | `records/fixed_trace_h15_evanescent_buffer1_preflight_controlled_stop.json` |
| inverse trace/interior budget exchange | both inverse spaces fail local exact-sequence audit；PDE 0 | `records/inverse_trace_interior_budget_exchange_preflight.json` |
| legacy physical trace lane | capability stop；candidate/PDE 0 | `records/physical_trace_lane_capability_gate.json` |
| selective trace v2 | fixture/correctness only；actual DWR/runner/candidate/PDE 0 | `records/physical_selective_trace_execution_capability_v2.json` |
| legacy iterative capability | superseded not-run gate preserved | `records/condensed_trace_iterative_capability_gate.json` |
| matrix-free formal PDE | correctness only；production disabled | `records/physical_selective_trace_execution_capability_v2.json` |
| same-process second assembly / new-RHS timing | no formal timing authority | `records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json`; `records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json` |
| new-material/frequency cache invalidation PDE | fixture-only invalidation checks；formal PDE not run | `records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json`; `records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json` |
| symbolic-ordering reuse / `MatZeroEntries` bake-off | `not_run`；no timing authority | `records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json` |
| best-workstation-rank iterative screen | `not_run` after three MPI8 residual negatives；no accuracy-qualified reason to repeat the same preconditioners | `records/h15_factor_free_iterative_mpi8_v1.json`; `records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json` |
| Hybrid integration | no eligible Full3D candidate | `outcomes/resource_projection_0p7nm.md` |
| M/DtN funnels | selected-candidate Gate closed | `outcomes/resource_projection_0p7nm.md` |
| resource model v3 / 0.7 nm PDE | `not_run`；no production accuracy layout | `outcomes/resource_projection_0p7nm.md` |
| irregular geometry | `out_of_scope_by_user; not_run; not_a_completion_gate` | `task_scope_addendum_v1.md` |

其中 `outcomes/...` 和 `task_scope_addendum_v1.md` 相对于
`docs/task035b_high_order_local_hp_resource_envelope/`；Task035 references
按表中 `../` 解析。

## 10. Evidence index

### Accuracy、z-node 与 selective trace

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_selective_trace_execution_capability_v2.json`
- `src/test/test_176_task035b_physical_selective_execution_capability_record.py`

### Setup、memory 与 iterative

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_direct_mpi1_2_4_8_resource_floor_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_memory_floor_factor_inventory_ledger_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_solve_thread_memory_semantics_audit_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_factor_free_iterative_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_and_trace_harmonic_iterative_capability_v3_stage4_recertification.json`

### Aggregates 与 resource boundary

- `docs/task035b_high_order_local_hp_resource_envelope/outcomes/all_candidates.json`
- `docs/task035b_high_order_local_hp_resource_envelope/outcomes/all_candidates.csv`
- `docs/task035b_high_order_local_hp_resource_envelope/outcomes/high_p_memory_anatomy.md`
- `docs/task035b_high_order_local_hp_resource_envelope/outcomes/resource_projection_0p7nm.md`
- `src/test/test_177_task035b_response_v3_records.py`

## 11. Ordinary default、merge 与后续 blocker

- 所有新 cache、selective trace、pre-release callback、iterative 和 MatShell
  路径均为显式 opt-in；ordinary default 未修改；
- 没有 merge `master`，Review V2 也未授权 merge；
- 没有删除 records、failed evidence、controlled-negative evidence 或 ignored
  raw artifacts；
- 当前无需用户操作；继续工作需要的是 actual channel-DWR/runner 与
  production selective-p6 integration，而不是密码、环境或权限。

## 12. Final validation

| final Gate | result |
|---|---|
| final tested source/evidence HEAD | `56ed6cdb44e90a820274092ac6661c1e6a95f934` |
| metadata delivery HEAD | documentation-only successor；精确 SHA 由最终 Git handoff 报告，避免文档自引用 |
| evidence source included through | `cf14e84f4a0f9216b6139a146eba78cdcfd45bb9` |
| targeted Task035b serial | `491 passed, 28 skipped in 507.27 s` at `b2545bac516afcf41f3a3fd12303cfb8aa50a511`；全部再次包含于 final full-repository pass |
| MPI2 final-source regression | each rank `95 passed, 24 skipped in 151.72/151.64 s` |
| MPI8 final-source smoke | eight ranks each `1 passed in 1.94–2.01 s` |
| Task034/035 targeted regression | `245 passed, 3 skipped in 67.82 s` at `1d8b190b119677413d70f46d54d9e6bc45b23855`；全部再次包含于 final full-repository pass |
| full repository pytest | **`1130 passed, 49 skipped in 884.08 s`** at final tested source HEAD |
| Ruff | Review V2 以来 95 个 changed-Python files pass；full-repository 仍有 5 个未改文件中的 15 个 inherited findings |
| compileall | `src`、`benchmarks`、root `conftest.py` pass |
| JSON/schema/hash checks | 992 tracked JSON parse；68/68 unique JSON/CSV rows；63 hash-bound records recompute |
| documentation/evidence | 48 documentation/record tests pass；response 60 个 evidence paths resolve；无 capability-v4 |
| diff-check | pass |
| tested-HEAD worktree | clean before this metadata-only writeback |

验证过程保留了真实失败与修复链：

1. 首次 focused combined run 为 `489 passed, 28 skipped, 2 errors`，暴露
   cross-module fixture 在组合收集时未注册；
2. 直接修改 `test_171` 后为 `490 passed, 28 skipped, 1 failed`，暴露历史
   capability-v2 测试哈希漂移；最终改为 root `conftest.py` 注册并恢复原哈希；
3. 首次 Task034/035 regression 为 `243 passed, 3 skipped, 2 failed`，暴露
   Task035b geometry successor binding 落后于当前 mesh source；冻结 Task035
   manifest 未改写，只追加 current Review V2 successor；
4. 首次 full-repository collection 因 `src/test/` 下的 non-top-level
   conftest fail-fast；移动到 repository-root 后 1179 项完整收集并通过
   上述全仓 Gate。

这些都是测试/治理负证据，不是 PDE accuracy failure；均未删除或重分类。
