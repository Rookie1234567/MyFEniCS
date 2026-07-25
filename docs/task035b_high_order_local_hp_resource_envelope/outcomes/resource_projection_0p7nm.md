# Task035b 0.7 nm / 2 TiB 资源投影

## Fail-closed 结论

```text
status = stopped_by_gate_no_hybrid_eligible_same_error_candidate
resource_model_v3 = not_run_by_selected_candidate_gate
eligible_12_of_12_candidate_count = 0
selected_candidate_id = null
selected_N_equiv_13p5 = null
selected_hybrid_local_fraction = null
actual_trace_interface_ratio = null
hybrid_closure = stopped_by_gate
m_funnel = not_run_by_selected_candidate_gate
0p7nm_pde = not_run
0p7nm_solver_pass = false
predicted_simultaneous_peak_gib = null
production_target_accuracy_layout = unknown
proves_0p7nm_feasible = false
ordinary_default_changed = false
```

Task035b 只允许把通过完整 same-error Gate 的最佳 1–2 个候选接入 Hybrid。
当前 selected set 为空，因此没有启动新的 Hybrid closure、M funnel 或
0.7 nm PDE。本文保留的是 fail-closed 规划与否证边界；正式
`0.7 nm resource model v3` 仍为 `not_run`，不存在 selected production
layout，也不存在可报告的 predicted simultaneous peak。

## Candidate Gate

| 候选 | 13.5 nm 等效 DoF | 成本结果 | same-error 结果 | Hybrid |
|---|---:|---|---|---|
| global p6/h15 | 84,492 | `<=90k`，12.000 GiB pair peak | scalar/field 通过；significant power 6/12、amplitude 8/12 | stopped |
| fixed p5-trace/p6-interior h15 | 74,890 | preferred DoF；旧 accuracy/setup 生命周期 5.803 GiB；独立 rank study 见下文 | scalar/field 通过；significant power 6/12、amplitude 7/12 | stopped |
| fixed directional-z h14 | 82,315 | 18,500 rows；6.376 GiB | scalar/field 通过；significant power 7/12、amplitude 9/12 | stopped |
| fixed directional-z h13 | 89,740 | 20,120 rows；accuracy-run 6.411 GiB；setup cold/warm 5.030/5.016 GiB | **预算内最佳测得点**；scalar/field 通过；significant power 10/12、amplitude 10/12 | stopped |
| h14 R5-slab bisect | 89,740 | 20,120 rows；6.463 GiB | scalar/field 通过；significant power 5/12、amplitude 9/12，计数回退 | stopped |
| global p6/h14 discriminator | 92,850 | 27,080 rows；12.587 GiB pair peak；超 cap 2,850 | scalar/field 通过；significant power 9/12、amplitude 12/12 | diagnostic only |
| p4-trace regionwise h10 | 88,994 | rows/NNZ/factor/peak 显著下降 | R00/R/T/Aclosure、orders、field 全失败 | stopped |
| p5-trace N62 h10 | 89,755 | 预算内物理减行 | low space 非 exact-sequence，且全部精度 Gate 失败 | stopped |

因此 “DoF 小于 90k” 不是入选依据。full residual、R00、R、T、Aclosure、
normalized vector、significant orders、complex amplitudes、selected
field/interface error、periodic/tag/orientation/geometry identity 必须同时通过。

方向性 z 从 h15 的 `6/12 + 7/12` 推进到 h13 的
`10/12 + 10/12`，但未达到 Review V2 不可放宽的 `12/12 + 12/12`。
完整 p6 trace 在 h14 上把复振幅推进到 12/12，也仍有 3 个功率通道失败，
而且超出 DoF 上限。R5 slab 二分则出现功率计数回退。因此既不能用 h13
作为 selected `N_equiv,13.5`，也不能用 over-cap global p6/h14 替它获得
accuracy credit。

## Setup/resource authority 不等于 accuracy authority

新增的 h15 direct rank study 在相同 74,890 Full3D-equivalent DoF、
16,880 rows 和 9,195,812 matrix NNZ 上得到：

| MPI | measured process-tree peak GiB | common solver s | authority |
|---:|---:|---:|---|
| 1 | **1.295** | 76.007 | direct setup/resource only |
| 2 | 2.158 | 74.913 | direct setup/resource only |
| 4 | 3.100 | 61.849 | direct setup/resource only |
| 8 | 4.711 | **53.901** | direct setup/resource only |

全部为 0 swap、full explicit residual 通过的实测点。MPI1 是该 rank study
中的最低实测 direct 点，但不是理论内存下限；MPI8 相对 MPI1 用 `3.64x`
进程树 RSS 换取 `1.41x` wall-time 改善。旧的 `5.8–6.4 GiB` 测量属于
其他 source/lifecycle authority，不能再描述成八九万 DoF 的最低内存，
更不能直接外推到 0.7 nm。

h13 MPI8 canonical setup profile 的 cold/warm process-tree peaks 为
**5.030/5.016 GiB**，也都只是 setup/resource measured points，不是下限。
其独立 accuracy authority 仍为 `10/12 power + 10/12 amplitude`。同理，
h15 rank study 并未重算 12 个通道，h15 accuracy 仍为 `6/12 + 7/12`。
setup profile 的 residual、R/T closure、cache 或 timing pass 不能覆盖
significant-channel Gate。

direct factor 也不能按 rows 线性外推。在 canonical setup authority 中，
h15→h13 的 rows 与 matrix NNZ 比值只有 `1.192x/1.198x`，factor NNZ
却增长 `1.346x`，fill 从 `2.887` 增至 `3.246`。这说明 ordering、消元图
和 fill 的非线性必须由目标布局实测；用 DoF 比例缩放 MUMPS memory 不能
形成正式 0.7 nm 资格。

## Review V2 capability 与资源分支边界

`significant_channel_reference_v1` 已冻结为 best-available same-code
reference；其 `production_qualified=false`，且没有修改原 h10 p5→p6
12 通道 acceptance bands。它为恢复候选提供固定比较坐标，不会自动产生
Hybrid eligibility。

物理 selective-trace audit 的状态是：

```text
status = fixture_and_correctness_capability_only
actual_channel_dwr_selection = false
formal_actual_pde_ready = false
runner_wired = false
candidate_count = 0
pde_run_count = 0
```

Stage4 caller expansion/row omission、owner-aware MatShell 和 pre-release
callback 已有 fixture/correctness 证据，但尚未产生 actual channel-DWR
selection 或 selective candidate PDE。h14 完整 p6 trace 的增量为
10,535 DoF，而预算 headroom 只有 7,685；h13 增量为 11,468，而 headroom
只有 260。因此没有可用于 v3 的 selective rows/NNZ/peak，也不能按比例从
global p6/h14 库存中扣除。

condensed iterative 已从 capability audit 推进为三个 formal screen，但
三者全部是 `controlled_negative_iterative_nonconvergence`：

| MPI8 screen | factor semantics | terminal explicit reduced residual | peak GiB | v3 credit |
|---|---|---:|---:|---|
| GMRES + Jacobi | no global direct factor | 0.8617 | 3.921 | none |
| FGMRES + ASM/ILU | no global factor；local subdomain ILU | 0.9997 | 4.462 | none |
| FGMRES + physical z-slab/ILU + DtN correction | no global factor；local ILU + 80-D coarse dense LU | 0.9963 | 3.885 | none |

Jacobi 没有 global factor，但未收敛，所以不是 factor-free success。ASM 和
physical profile 还包含 local factors；后者另有 coarse LU，也不是 strictly
factorless。三个较低 peak 都只属于 failed-screen resource evidence，不能
称为合格解的内存下限、不能填入 production component ledger，也不能作为
0.7 nm projection anchor。

## 继承的 Task034 current-layout authority

Task034 resource model v2.1 仍是当前 Hybrid layout 的 stress-test authority，
其 authority 与数值均未因上述 Review V1 诊断而改变。
它将 largest component、local subtotal、modal/runtime subtotal、cumulative
component envelope、measured simultaneous peak 和 unknown predicted peak
严格分开。0.7 nm 三个 current-layout stress scenarios 均有单组件超过
2 TiB：

| Task034 scenario | largest component GiB | cumulative envelope GiB | predicted simultaneous peak |
|---|---:|---:|---|
| p2/h3 | 1,747,721 | 2,014,975 | unknown |
| p3/h3 | 5,713,351 | 6,804,671 | unknown |
| p4/h5 | 2,567,626 | 3,008,763 | unknown |

Task035b 没有同误差 Hybrid 候选，所以不能用其 raw DoF reduction 抵扣这些
分组件库存，也没有推翻 Task034 的 current-layout 单组件瓶颈结论。

## 仅用于规划的 local-FE 敏感性

机械体积缩放

$$
s^3 = (13.5 / 0.7)^3 = 7173.105
$$

与 `f_H=0.30/0.35/0.40` 只能生成
`derived_planning_sensitivity_no_accuracy_credit`：

| 13.5 nm 等效 DoF | f=0.30 | f=0.35 | f=0.40 |
|---:|---:|---:|---:|
| 90,000 | 193.7 M | 226.0 M | 258.2 M |
| 75,000 | 161.4 M | 188.3 M | 215.2 M |
| 70,000 | 150.6 M | 175.7 M | 200.8 M |
| 65,000 | 139.9 M | 163.2 M | 186.5 M |

其中 `f_H=0.40` 是未知未来几何的保守规划包络，不是本任务的不规则几何
证据。2–3 kB/active-DoF 只能作为未来 low-storage iterative/local solver
设计目标，不能冒充当前 MUMPS 测量。

任务书未定义 kB 为 1000 或 1024 bytes，故机器口径固定写
`bytes_per_dof=2000/3000`。按 decimal bytes 换算：

| target | f_H=.30，2/3 kB GiB | f_H=.35，2/3 kB GiB | f_H=.40，2/3 kB GiB |
|---:|---:|---:|---:|
| 90k | 360.746 / 541.118 | 420.870 / 631.305 | 480.994 / 721.491 |
| 75k | 300.621 / 450.932 | 350.725 / 526.087 | 400.828 / 601.243 |
| 70k | 280.580 / 420.870 | 327.343 / 491.015 | 374.107 / 561.160 |
| 65k | 260.539 / 390.808 | 303.962 / 455.942 | 347.385 / 521.077 |

这些只是 local-FE storage design bands，不包含 mesh、coefficients、
Krylov/preconditioner、QEP/modal/interface 或生命周期重叠。

## Component ledger

| component | identity | Task035b v3 value |
|---|---|---|
| local FE active DoF | derived planning sensitivity | 上表；无 accuracy credit |
| mesh / coefficients | production layout unknown | unknown |
| Krylov vectors | three nonconverged screens；no selected iterative layout | unknown |
| preconditioner / local factors | Jacobi/ASM/physical screens all controlled-negative；no selected solver | unknown |
| QEP / modal / interface | M funnel stopped | unknown |
| simultaneous lifecycle overlap | not measured | unknown |
| safety margin | no selected peak | unknown |

这些 unknown 不能相加成 predicted peak。解除 Gate 的条件是先出现一个通过
完整精度与资源合同的 13.5 nm 候选，再运行一个 hash-bound Hybrid closure
和 M funnel，最后测量组件生命周期与 simultaneous peak。

Task034 current layout 还给出：

```text
M_0.7 = ceil(160 * (13.5 / 0.7)^2) = 59,511
single complex (2M)^2 object = 211.093 GiB
six such objects replicated on 48 ranks = 60,793.265 GiB
```

dense multi-RHS 分量按 `s^5` 外推，在 p2/h3、p3/h3、p4/h5 三种场景分别
为 `1,747,721 / 5,713,351 / 2,567,626 GiB`。每个单一分量都已经超过
2 TiB，因此 current layout 的瓶颈不是把 cumulative envelope 误当成 peak。
但是 component overlap 未测，predicted simultaneous peak 仍必须为 null。

## 保留的 2 TiB 目标与下一条可证伪路线

`2 TiB = 2048 GiB` 仍是 production simultaneous process-tree/cgroup peak
目标，但当前没有资格化布局可与该阈值比较。解除 `not_run` 必须按以下顺序
产生可否证证据：

1. 在 `<=90,000` Full3D-equivalent DoF 内，用 actual channel adjoint/DWR
   选择真实 physical p6 trace orbits；inactive modes 不进入矩阵，并通过
   residual、R00/R/T/Aclosure、fields 及 `12/12 + 12/12`。
2. 仅对上述 passing candidate 做 Full3D–Hybrid closure，再运行
   `M80/M120/M160`，必要时 `M240`，以及 external DtN
   evanescent-buffer funnel。任何 closure 或 12-channel Gate 失败都继续
   保持 v3 `not_run`。
3. 对选定 Hybrid layout 实测 mesh、coefficients、Krylov、
   preconditioner/local factors、QEP/modal/interface 和生命周期重叠；优化
   MPI rank 数。迭代 lane 只有采用实质不同的 spectral/auxiliary-space、
   block-Schur 或 Fourier/DtN preconditioner 并收敛后，才可贡献
   factor-free resource credit。
4. 只有 hash-bound measured/derived component ledger 加明确 safety margin
   能支持 simultaneous peak `<=2048 GiB` 时，才可报告 2 TiB 内的正结论。
   任一不可避免的单组件或实测 simultaneous peak 超过 2048 GiB，即否证
   当前布局；不能通过删掉 unknown 或缩放 5.8–6.4 GiB 来规避。

这条路线保留未来可行性，同时使每一步都能被实际 channel、Hybrid closure
或资源测量推翻，而不是先给出乐观的正式外推。

## Fail-closed 机器语义

```json
{
  "schema_version": "task035b.resource-projection.v3",
  "status": "stopped_by_selected_candidate_gate",
  "resource_model_v3_run_status": "not_run",
  "is_pde_run": false,
  "is_solver_pass": false,
  "selected_candidate_gate": {
    "required": true,
    "eligible_candidate_count": 0,
    "selected_candidate": null,
    "pass": false
  },
  "hybrid": {
    "launch_authorized": false,
    "run_status": "not_run_by_selected_candidate_gate",
    "m_funnel_status": "not_run",
    "closure_status": "not_run"
  },
  "projection": {
    "identity": "planning_sensitivity_only",
    "selected_n_equiv_13p5": null,
    "selected_hybrid_local_fraction": null,
    "actual_trace_interface_ratio": null,
    "m_lower_bound": null,
    "m_risk_range": null,
    "selected_predicted_local_fe_dofs_0p7nm": null,
    "predicted_simultaneous_peak_gib": null,
    "production_target_accuracy_0p7nm": "unknown",
    "proves_0p7nm_feasible": false,
    "cumulative_envelope_is_peak": false
  }
}
```

`proves_0p7nm_feasible=false` 表示“本任务没有证明可行”，不是已证明所有未来
算法在数学上不可行。

## 证据

- `docs/task034_workstation_wsl_adaptive_scalability/outcomes/resource_model_v2.md`
- `docs/task034_workstation_wsl_adaptive_scalability/outcomes/resource_model_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p6_h15_vs_h10_same_error_audit.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_directional_z_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_r5_slab_bisect_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_p6_h14_trace_discriminator.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_trace_lane_capability_gate.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_trace_iterative_capability_gate.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_direct_mpi1_2_4_8_resource_floor_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_factor_free_iterative_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_selective_trace_execution_capability_v2.json`
