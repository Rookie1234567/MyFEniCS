# Task035 测试摘要

## 结论

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
phase_b_unlocked = true
task035_target_pde_started = true
actual_global_two_level_R5 = pass_hexa_control_mpi8
heavy_p4_started = false
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

正式运行绑定 clean SHA `307907a1bb5a7a0a08c46ec75881d890fb3d1549`，watchdog
观测 8 个 rank，完整进程组 termination policy 已启用，全部 qualification checks 为 true。
原始 field、timeline、stdout 与 solver outputs 位于 ignored artifact 目录；tracked record 只保存
轻量指标、路径与 SHA-256。没有重跑 Review V4 已接受的 Phase A/full pytest/Task034 heavy matrix，
没有放宽 residual、energy、marking 或 resource Gate。
