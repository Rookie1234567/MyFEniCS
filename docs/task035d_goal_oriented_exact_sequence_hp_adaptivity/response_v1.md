# Task035d Response V1

## 1. 集中结论

```text
response_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
execution_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
branch_base = 9c2160d41382026352908d692ad479dc4508424d
formal_MPI = 8
true_local_p_capability = pass
true_local_h_capability = pass
complete_combined_hp_accuracy = fail
best_significant_power_count = 6/12
best_significant_amplitude_count = 6/12
production_hp_candidate = none
hybrid_phase_f = not_run_full3d_hp_gate_failed
ordinary_default = unchanged
```

Task035d 已完成真正的 assembly-time local-p、2:1 balanced-hexa local-h、
H(curl) hanging/Floquet 约束、exact-sequence、cell-interior static
condensation、PETSc owner routing、完整场恢复和 MPI1/2/8 identity。inactive
高阶模式和 slave rows 没有进入矩阵，因此 DoF、rows、NNZ、factor 和内存
压缩都是真实的。

完整 hp 物理 Gate 没有通过。所有正式候选都保持原 `12/12 powers +
12/12 complex amplitudes` Gate；没有删除通道或放宽 tolerance。最佳正式
计数是 h15 top-air local-h 的 `6/12 + 6/12`，所以按任务书归类为
`PARTIAL_WITH_CONTROLLED_NEGATIVES`，而不是成功。

## 2. Phase receipt

| Phase | 结果 | receipt |
|---|---|---|
| 0 | p6/h10、Case095/096、Hybrid M120 authority frozen | pass |
| A | entity catalog、exact sequence、active expansion、Schur、serial/MPI2 | pass |
| B | true local-p 与两条 MPI8 p-only PDE | capability pass；accuracy negative |
| C | true local-h 从 topology 到 production MPI8 PDE | capability pass；accuracy negative |
| D | nested-p 与 selective-trace 36-goal DWR、factorial attribution、bounded selector | partial |
| E | manual bounded h/p discriminators 与 stop rule | partial；automatic cycles 1–4 not completed |
| F | static Hybrid M120 | not run because Full3D Gate failed |

## 3. 正式数值结果

| Candidate | FE DoF / rows | matrix / factor NNZ | peak | residual | powers / amplitudes | result |
|---|---:|---:|---:|---:|---:|---|
| T30 p-only | `87,600 / 28,990` | `15,253,176 / 63,564,300` | `10.09287 GiB` | `1.410e-11` | `0/12 / 0/12` | controlled negative |
| sidewall-z0 guard | `89,870 / 31,064` | `16,490,572 / 76,721,484` | `8.38265 GiB` | `7.559e-12` | `1/12 / 0/12` | controlled negative |
| h15 top-air local-h | `82,925 / 18,470` | `10,186,108 / 30,865,200` | `7.50068 GiB` | `5.740e-12` | `6/12 / 6/12` | controlled negative |
| symmetric h + p-down | `84,240 / 20,060` | `11,176,430 / 32,658,700` | `7.50883 GiB` | `2.124e-11` | `4/12 / 4/12` | controlled negative |
| factorial bridge | `76,205 / 18,470` | `10,186,108 / 30,865,200` | `7.29866 GiB` | `3.433e-12` | `4/12 / 4/12` | controlled negative |
| ten-face selective trace | `83,125 / 18,670` | `10,406,108 / 32,683,000` | `8.06898 GiB` | `1.287e-11` | `5/12 / 6/12` | controlled negative |
| left-grating single-root | `88,915 / 21,650` | `12,382,332 / 37,250,750` | `8.06120 GiB` | `3.267e-11` | `4/12 / 6/12` | controlled negative |

任务书 §3.2 要求的 global p6/p5 h10、Task035 DWR、Task035b fixed
h15/h14/h13 与本任务 p-only/h-only/combined best 已统一列在
[`outcomes/summary.md`](outcomes/summary.md) §4.1；历史未保存的逐通道或
peak 字段明确写为未记录，没有推断补值。

相对 p6/h10 static，factorial bridge 的 rows、matrix NNZ、factor NNZ 和
peak 分别下降 `63.98%/75.74%/85.46%/50.42%`，是最强资源结果；但
`4/12 + 4/12` 使它不能成为 same-error 候选。

最终 left-grating 判别点通过标量 R00/R/T/Aclosure、Avolume、interface
field、true residual 和资源 Gate，峰值下降 `45.24%`；但 volume maximum
point error `0.04688675 > 0.04102079`，且八个 power、六个 amplitude
通道失败。完整逐通道 error/tolerance 表在
[`outcomes/summary.md`](outcomes/summary.md) 与 Case097 README。

## 4. DWR 和自动决策的真实边界

本轮完成两类实际 residual-weighted adjoint：

- same-trace nested-p：12 unit channels / 36 real goals 的 independent
  checker 通过；16 个 remote periodic p-down pair 在 conservative budget
  下无一安全，因而停止继续 p-down；
- selective p6 trace：十面 coarse/enriched endpoint 的 36/36 goal closure
  通过，但物理 endpoint 只有 `5/12 + 6/12`。

selective DWR 是 posthoc action attribution，不是产生十面选择的 causal
selector，所以保留
`posthoc_actual_action_attribution=true`、
`goal_oriented_selection_credit=false`。

最终 bounded selector 使用 compact DWR 作为位置 oracle，并显式保存：

```text
actual_local_h_dwr_surplus_available = false
success_forecast = false
goal_oriented_selection_credit = false
complete_combined_hp_credit = false
```

它只授权一个 MPI8 discriminator，没有把 projection 或 oracle 预测冒充
PDE 结果。

## 5. 为什么停止而不再跑 outer-periodic

同一 `h15 + p5 trace + bounded single-root top-air local-h` lane 已有两个
正式精度负信号：

1. top-air local-h：`6/12 + 6/12`；
2. left-grating：`4/12 + 6/12`，并失败 volume max-point Gate。

未运行 outer-periodic 的 compact-oracle score 还弱于已失败的
left-grating：每 1000 added DoF 为 `35.29 < 55.28`，每 1000 added rows
为 `101.01 < 162.54`，且两者都没有 actual local-h DWR。继续运行会违反
“有正信号继续、同 lane 两个负信号后关闭”的任务规则。

最终状态：

| item | status |
|---|---|
| outer-periodic | `not_run_by_lane_stop`，不是 PDE failure |
| multi-seed combinations | `not_evaluated_by_stop_rule` |
| frozen ten-face subset | `closed_controlled_negative` |
| whole top-port selective trace | `incomplete_not_run_no_authorized_candidate` |
| Hybrid M120/M160 | `not_run_full3d_hp_gate_failed` |

## 6. 证据与失败保留

主要 authority：

- [`outcomes/summary.md`](outcomes/summary.md)
- [`outcomes/test_summary.md`](outcomes/test_summary.md)
- [`../../benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/README.md`](../../benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/README.md)
- `records/h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json`
- `records/selective_face_selection_compact_v1.json`
- `records/bounded_single_seed_top_air_hp_selection_v2.json`
- `records/h15_left_grating_top_closure_p5fine_mpi8_candidate_check_v1.json`
- `records/h15_left_grating_top_closure_p5fine_mpi8_controlled_negative_compact_v1.json`
- `records/bounded_single_root_top_air_lane_closure_v1.json`

失败 evidence 均保留。没有运行不规则几何、tetra static、mixed mesh、
iterative、matrix-free 或 0.7 nm，也没有修改 ordinary default。

收口回归：

```text
Task035d focused serial = 215 passed, 13 skipped
MPI2 components = 80 passed, 10 skipped
MPI8 representative = 16 passed, 4 skipped per rank
full repository = 837 passed, 41 skipped
Ruff / compileall / JSON / registry / Case097 authority / diff-check = pass
```

第一次 full repository 回归暴露 `hybrid_local_dtn.py` 漏向已经要求 collective
communicator 的 `_combine_owned_entries` 传递 `comm`，以及 Case097 未登记到
active-research documentation contract。前者补齐两个 `comm=comm` 调用，
后者增加 Case097 专属 config assertions；Task032/033/035b Hybrid targeted
suite 和第二次全库均通过。Task035d 正式 Full3D PDE 不走该 Hybrid 路径，
所以没有重跑重型 PDE，也没有把新源码冒充为历史 Task035c Hybrid records 的
重资格化。

## 7. 后续 Review 建议

当前不建议在同一 single-root lane 继续增加 PDE。若后续 Review 要重新打开，
应先定义新的 candidate space，并生成 actual per-channel local-h 或
trace-orbit DWR；只有出现独立正信号才授权一个新的 discriminator。

Task035d 未获任务书授权自行 merge master。本 response 完成后提交并推送同一
执行分支，等待集中 Review。
