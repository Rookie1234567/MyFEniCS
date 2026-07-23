# Task035 测试摘要

## 结论

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
phase_b_unlocked = true
task035_target_pde_started = true
actual_global_two_level_R5 = pass_hexa_control_mpi8
actual_discrete_DtN_adjoint = pass
actual_goal_weighted_DWR = pass
high_order_dwr_mpi8 = pass
high_order_stage_full_regression = fail_one_task034_classifier
classifier_fix_targeted = pass
second_full_regression = not_run_phase_limit
selected_research_strategy = p3_p4_R_total_DWR_theta0p5_one_cycle
heavy_p4_started = true
thresholds_relaxed = false
```

## 已通过检查

| 检查 | 结果 |
|---|---|
| JSON syntax | pass |
| hermetic Phase A checker | pass |
| explicit artifact hash checker | pass；6/6 materialized hash match |
| focused Case093/Task034/Task035 tests | 24 passed |
| targeted Ruff | pass |
| targeted compileall | pass |
| git diff --check（失败发生前） | pass |

## 初始阻断 Gate（历史保留）

命令：

```bash
pytest -q
```

结果：

```text
1 failed, 488 passed, 18 skipped in 247.53s
```

失败测试：

```text
src/test/test_26_documentation_contract.py::
DocumentationContractTests::
test_numbered_benchmark_cases_use_case_contained_contracts
```

直接原因是新增编号目录 `094_hcurl_goal_oriented_adaptivity` 只有 Phase A
`records/base_manifest.json`，尚未进入项目的完整 numbered-case contract 集合。当时按 Gate
规则保存证据并停止；Review V1 随后授权局部 staging lifecycle 修正。

## Review V1 合同修正与最终验证

Review V1 授权把 numbered case 生命周期拆分为 formal/frozen 与 staging/in-progress。
Case001–Case093 的完整严格合同保持不变；Case094 显式注册为 staging，新增最小
README/config/expected/test_command scaffold，普通入口只运行 hermetic checker。

| 顺序 | 命令范围 | 结果 |
|---:|---|---:|
| 1 | 原失败 test26 method | 1 passed |
| 2 | test26 + test87 | 23 passed |
| 3 | governance + Case093/Task034 + Task035 focused | 49 passed |
| 4 | full `pytest -q`（仅一次） | 494 passed, 18 skipped in 247.77s |
| quality | scoped Ruff / compileall / diff-check | pass / pass / pass |

最终状态：

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
phase_b_unlocked = true
```

`records/phase_a_regression_failure.json` 继续保存首次失败历史，未删除、覆盖或改写为通过。
Gate 规则保存证据并停止；Review V1 随后授权局部 staging lifecycle 修正。

## Phase B fixture 与 full regression 恢复

| 检查 | 结果 |
|---|---:|
| algebraic precursor targeted（历史） | 12 passed |
| Task035 focused suite | 35 passed |
| serial / MPI2 / MPI4 component identity | pass / pass / pass |
| scoped Ruff / compileall / diff-check | pass / pass / pass |
| 首次错误 launcher full pytest | controlled stop；36 failed, 453 passed, 18 skipped, 17 errors |
| 正确 sourced complex activation full pytest | 506 passed, 18 skipped in 248.08s |

首次 Phase B full failure 由遗漏 `source .venv/bin/activate-myfenics` 引起，已原样保存到
`records/phase_b_regression_failure.json`。用户明确授权后，仅用正确 activation 重跑一次；
恢复记录为 `records/phase_b_regression_recovery.json`。

```text
phase_b_algebraic_precursor = pass
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
phase_c_formal_completion = pending_B3_B4
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

## Review V2：真实 B1/B2 最低 Gate

| 检查 | 结果 |
|---|---:|
| lightweight ABI rank probe（不含 solver microfixture） | pass；Linux venv、complex128、ABI identity |
| B1/B2 serial targeted | 3 passed |
| algebraic precursor + B1/B2 + record tests | 17 passed |
| B1 real periodic Nédélec p1/p2 | pass |
| B2 real flat lossy layer，三个 h/p 点与 official fixture goal | pass |
| serial/MPI2 scalar metric identity | pass；differences = `{}` |
| R2 policy | diagnostic only；未缩放 R1 |

本轮没有重跑 Phase A、Task034 heavy PDE、MPI 全量资格化或 full repository pytest。
Phase C-low-cost 已按 Review V2 自动解锁；B3/B4 继续并行且在 Phase D/p4 heavy 前仍为强制待办。

## Review V3：Phase C/D

| 检查 | 结果 |
|---|---:|
| Phase C 新增 targeted | 3 passed |
| B3/B4 targeted | 2 passed |
| Phase D backend targeted | 3 passed |
| Phase C focused test88–test94 | 25 passed |
| 新增 C/D direct tests（formatter 后） | 10 passed |
| final record contract | 3 passed |
| serial C+D | `phase_cd_complete_controlled_negative` |
| MPI2 C+D | `phase_cd_complete_controlled_negative` |
| serial/MPI2 identity | pass；failures = `[]` |
| scoped Ruff / compileall / diff-check | pass / pass / pass |
| C+D focused test88–test97 | 33 passed |
| full repository pytest（本 Phase 唯一一次） | 527 passed, 18 skipped in 245.98s |

首次 MPI2 C+D run 在 tetra volume measurement 得到伪零值并按 Gate 返回 2；原始失败保存在
`records/phase_cd_mpi2_initial_volume_measurement_failure.json`。根因是 refined mesh 的 topology
vertex ID 被错误用于 geometry indexing；修复为 `geometry.dofmap[cell]` 后 serial/MPI2 与 identity
均通过。失败证据没有删除、覆盖或改写。

本轮没有运行 Phase A full pytest、环境/MPI/MUMPS/PEP 全量资格化、Task034 artifact 全量 hash、
Task034 p3/p4/M heavy matrix、新 Task035 PDE、adaptive cycle 或 p4/h5 heavy case。

## Review V4：actual global R5 首个目标运行

| 检查 | 结果 |
|---|---:|
| manufactured actual-R5 serial | 2 passed |
| manufactured actual-R5 MPI2 | 2 passed per rank |
| Stage-4 entrypoint + R5 + watchdog targeted | 8 passed |
| actual-R5 record contract | 3 passed |
| scoped Ruff / compileall / diff-check | pass / pass / pass |
| target p2/p3 h10 MPI8 watchdog | `actual_global_r5_pass` |
| true residual p2 / p3 | `2.304e-13` / `2.765e-12` |
| cell-energy closure | `5.106e-16` |
| periodic tetra trace/tag/orientation serial + MPI2 | 3 passed per rank |
| target tetra p2/p3 h50 MPI2 watchdog | `actual_global_r5_pass` |
| tetra true residual / energy closure | `9.388e-14`, `9.134e-13` / `5.810e-16` |
| process-tree peak / swap | `2.870 GiB` / `0` |
| periodic tetra audit/refinement serial | 2 passed |
| periodic tetra audit/refinement MPI2 | 2 passed per rank |
| initial / refined mesh hash identity | `67478577...e824` / `c4be7bfb...62f2` |
| refined orientation / x-y periodic closure | zero nonpositive / pass |
| first actual marked cycle MPI2 / clean SHA | completed / `5bfc1a0...7cac` |
| cells / marked / periodic-closed | 180→1142 / 49 / 60 |
| first-cycle residual max / peak / swap | `7.989e-12` / `0.951 GiB` / 0 |
| old moving p-gap Gate | `formal_not_pass`，`5.538e-2`→`8.894e-1` |
| fixed p4/h5 reference p2 reduction | 1.060% |
| fixed p4/h5 reference p3 reduction | 62.832% |
| second distributed-refine attempt | controlled stop before cycle2 PDE |
| second-refine orientation / minimum quality | zero nonpositive / `0.0456` |
| second-refine periodic x / y | fail, `6/6` / `8/16` unmatched |
| deterministic full-boundary two-level serial | 2 passed |
| deterministic full-boundary two-level MPI2 | 2 passed per rank |
| first / second deterministic mesh hashes | `65c11dbe...b0ac` / `f4c0533e...49fc` |
| actual deterministic two-cycle MPI2 | `actual_r5_adaptive_cycles_pass` |
| adaptive cells / p2 DoF / p3 DoF | 180→1308→8785 / 1470→9504→60330 / 4011→26730→172257 |
| p2 fixed-ref error | 1.202635→1.087687→0.195353 |
| p3 fixed-ref error | 1.147343→0.142113→0.007041 |
| final p2 / p3 true residual | `4.798e-12` / `2.341e-11` |
| two-cycle process-tree peak / swap | `6.401 GiB` / 0 |
| watchdog qualification failures | `[]` |
| true-uniform mechanism serial / MPI2 | 3 passed / 3 passed per rank |
| uniform cells / p2 / p3 DoF | 11,520 / 78,000 / 223,656 |
| uniform p2 / p3 fixed-ref error | 0.010697 / 0.001227 |
| uniform p2 / p3 true residual | `7.943e-12` / `8.721e-12` |
| uniform peak / swap / wall | `8.473 GiB` / 0 / `523.44 s` |
| adaptive/uniform error ratio p2 / p3 | 18.263 / 5.738 |
| pure R5 production marking | controlled negative；diagnostic only |

正式运行绑定 clean SHA `307907a1bb5a7a0a08c46ec75881d890fb3d1549`，watchdog
观测 8 个 rank，完整进程组 termination policy 已启用，全部 qualification checks 为 true。
原始 field、timeline、stdout 与 solver outputs 位于 ignored artifact 目录；tracked record 只保存
轻量指标、路径与 SHA-256。没有重跑 Review V4 已接受的 Phase A/full pytest/Task034 heavy matrix，
没有放宽 residual、energy、marking 或 resource Gate。

## Actual adjoint/DWR 与 p3/p4 高阶收口

| 检查 | 结果 |
|---|---:|
| actual DtN adjoint / R,T gradient / true adjoint residual | pass |
| p2/p3 DWR fixture serial / MPI2 | pass / pass per rank |
| p2/p3 DWR formal cycle1 MPI2 | mixed research result；record contract pass |
| uniform level1 p3/p4 MPI2 | pass；2.549 GiB，73.40 s |
| uniform level1 p3/p4 MPI8 | pass；4.020 GiB，27.81 s；MPI identity pass |
| p3/p4 DWR theta=.5 cycle1 MPI8 | pass；3.983 GiB，37.80 s；p4 engineering positive |
| p3/p4 DWR theta=.5 cycle2 pre-tie MPI8 | pass；19.283 GiB，554.15 s；历史 drift evidence |
| Dörfler cutoff tie expansion unit serial / MPI2 | 3 passed / 3 passed per rank |
| actual marker identity p2/p3 serial / MPI8 | 1 passed / 1 passed per rank |
| p3/p4 DWR theta=.5 cycle2 tie-policy-v1 MPI8 | pass；18.831 GiB，583.87 s；cost negative |
| p3/p4 DWR theta=.3 cycle1 MPI8 | pass internal Gates；engineering controlled negative |
| final high-order record/cost contract test107 | 13 passed |
| scoped Ruff / compileall / diff-check | pass / pass / pass |

首次 DWR watchdog 的 numerical worker 已通过，但 parent compactor 未映射新 record 字段；原始失败
永久保存在 `records/actual_dwr_r_adaptive_watchdog_compaction_failure.json`，修复 mapper 后只重跑
正式 case。p3/p4 repeat runs 的 cycle1 marked sets 均为 215 cells，pairwise overlap
`214/216=0.9907407`；exact hashes 不同，测试明确锁定 overlap ≥0.99 而不是虚假 exact identity。

正式高阶 runs 全部使用 clean SHA、MPI8、one-heavy-at-a-time watchdog、warning/termination preflight、
full true residual、adjoint residual、orientation、periodic、memory 和 no-swap Gates。两轮 run 的
warning 16 GiB 被实测跨过，但 32 GiB termination 未触发；没有降低 residual、marking、资源或
repeatability 阈值。第二轮保存为“数值通过、工程成本判负”，未继续第三轮。

| p4/p5 hp audit 检查 | 结果 |
|---|---:|
| p5 Basix layout/S3 transform serial | 2 passed |
| p5 refined-tetra sparse MPC MPI8 | 1 passed per rank |
| related p1--p5 serial regression | 17 passed, 2 skipped |
| p4/p5 minimal-closure cycle2 MPI8 | pass；27.768 GiB，778.93 s，swap 0 |
| p4/p5 final p5 error / DoF | `0.000220336` / `339,850`；数值正、成本受限 |
| p4/p5 full-sleeve cycle1 MPI8 | pass；7.901 GiB，109.57 s，swap 0 |
| full-sleeve p5 error / DoF | `0.000589604` / `103,330`；strong hp tradeoff signal |
| p4/p5 theta=.7 full-sleeve cycle1 MPI8 | pass；8.080 GiB，109.79 s，swap 0 |
| theta=.7 p5 error / DoF | `0.000538286` / `106,355`；adaptive-control compression，structured same-error 未通过 |
| p4/p5 uniform-level1 MPI8 | pass；8.011 GiB，swap 0 |
| uniform p5 error / DoF | `0.000735191` / `116,120`；DWR `.7` 少 8.4% DoF且误差低 26.8% |

本高阶阶段没有重跑 Task034 p4/h5 reference、M funnel 或既有 MPI heavy matrix；结构化 p4/h10、
p4/h7.5 与 p4/h5 数字全部从已接受、hash-bound Case093 records 读取。

本阶段唯一一次 full repository pytest 真实结果为
`1 failed, 571 passed, 18 skipped in 322.08s`。唯一失败是 Task034 fail-closed numerical-blob checker
尚未分类 Task035 在 `src/geometry/mesh_builder_3d.py` 新增的 opt-in periodic-tetra/retagging 路径；
环境、ABI、MPI、PDE 和数值 Gate 均未失败。证据永久保存在
`records/high_order_full_regression_classifier_failure.json`。修复只新增显式
`requires_corresponding_pde_rerun=true` 分类并更新精确路径合同；已有 Task035 tetra PDE records
就是对应 rerun evidence，ordinary hexa default 未改变。原失败测试随后 `1 passed`，完整 test73
与关键 Task035 合同组合 `50 passed`。按每阶段最多一次 full pytest 的固定节奏不执行第二次全仓
回归，因此不得把 targeted recovery 写成当前 HEAD 的 full-regression pass。
