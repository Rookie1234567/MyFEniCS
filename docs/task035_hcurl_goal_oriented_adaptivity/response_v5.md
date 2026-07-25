# Task035 Response V5：适度更细 tetra base、multi-goal 与 hp 准备

## 1. 权威与执行身份

本响应对应 `review_report_v5.md`，没有新建任务分支、没有从 master 重开，也没有 reset、rebase、
force push 或删除历史失败证据。

```text
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
review_v5_start_head = 7136be8043fa6ddfe026e3185d56f9384c19401c
h37p5_R_only_record_source_sha = 7136be8043fa6ddfe026e3185d56f9384c19401c
normalized_multigoal_record_source_sha = 4e334a527ad57452ca3b12ab38d3059406f5a4c9
execution_backend = WSL_Ubuntu_24_04
canonical_activation = source scripts/activate_myfenics_wsl.sh
PETSc.ScalarType = complex128
PETSc.IntType = int32
```

## 2. 环境与 replay blocker 修复

- WSL 安装系统 `bubblewrap 0.9.0`，恢复 Codex 受审计文件沙盒；
- activation 固定 `TMPDIR/TMP/TEMP=/tmp`，MPI 与 pytest 不再使用 `/mnt/c` 临时文件；
- activation 使用稳定 `/tmp/myfenics-matplotlib-$UID` cache，避免每次随机重建 Matplotlib cache；
- common-mesh replay 原先错误依赖跨进程可能漂移的 DOLFINx global cell IDs；现改为从 record
  已保存的 canonical geometry IDs 解析当前 IDs，并复核 marker、最终 mesh 与 tag hashes；
- h37.5 replay 的首次真实失败为 1,644 cells、hash mismatch；修复后 MPI8 精确恢复 1,600-cell
  authority。没有把该基础设施失败改写为 PDE failure。

## 3. moderately-finer base 筛选

axis-plan preflight 结果：

| nominal base | resolved axis plan | tetra cells | 决策 |
|---|---|---:|---|
| h50 | `(3,2,5)` | 180 | accepted authority |
| h40 | `(3,2,5)` | 180 | 与 h50 重复，不运行 |
| h37.5 | `(3,2,6)` | 216 | 唯一新增候选 |
| h35 | `(3,2,6)` | 216 | 与 h37.5 重复，不运行 |

h37.5 只执行一次 `R_total` DWR/full-sleeve local-h：

| cells | p5 DoF | R/T/A_volume | vector error | strict-R error | peak GiB | wall s |
|---:|---:|---|---:|---:|---:|---:|
| 1,600 | 129,005 | 0.000880846 / 0.602567555 / 0.396551599 | 1.588e-4 | 1.145e-4 | 9.491 | 129.66 |

相对 h50 selected authority，完整向量误差降低 70.49%，DoF 增加 21.30%，内存增加 17.45%；
相对 true-uniform tetra p5，误差降低 78.39%，但 DoF 与内存分别增加 11.10% 与 18.47%。
h37.5 p5 保持 62.05% DoF 节约并通过 normalized vector control，但 strict-R 仍失败。

## 4. fixed-mesh p+1 受控停止

从 h37.5 final mesh 的 p4/p5 DoF 精确反解：

```text
cells = 1600
edges = 2305
faces = 3474
predicted p6 DoF = 214050
50% DoF ceiling = 169946
predicted saving = 37.02%
```

因此固定该 mesh 的 p5/p6 在 PDE 前已违反 Review V5 50% DoF Gate，没有启动 p6 heavy，也没有
继续 p+2。

## 5. tolerance-normalized multi-goal

新增 `tolerance_normalized_R_T`，分别求解 R/T 伴随，并用 structured p4/h7.5 相对 p4/h5
reference 的分量误差归一化后作 cell-wise weighted L2。`A_volume` 进入最终 vector audit；由于
当前 qualified field 能量闭合且没有独立 volume goal gradient，不伪造第三个伴随。

formal h37.5 MPI8 run 全部 Gate 通过，peak `9.452 GiB`、swap 0、wall `129.21 s`。初始 base 上
normalized 与 R-only 恰好选中同一 98 cells，故允许的一次 refinement 与最终 observables 相同；
refined-mesh 的只读下一候选已分化为 655 vs 687 cells，但不执行第二次 h。

```text
multi_goal_mechanism = pass
one_cycle_mesh_gain_vs_R_only = controlled_neutral_identical
normalized_RTA_vector_gate = pass
strict_R_gate = controlled_negative
second_h_cycle = not_run_by_contract
```

## 6. h/p smoothness classifier

新增 research-only correction-decay classifier，输入同一 mesh 上的 p4/p5 与 p5/p6 local goal
indicators，以 `eta_p5p6/eta_p4p5 <= 0.5` 标记 `p_candidate`，慢衰减标记 `h_candidate`，低显著性
标记 `undetermined`。它只输出 canonical-cell 决策，不创建 variable-p space、不改 mesh。

h37.5 p6 被 DoF Gate 阻止；旧 h50 p6 records 没有保存两级 local indicator snapshots。因此本轮
完成 classifier 与 synthetic fail-closed tests，但没有伪称完成真实 cell-level p4/p5/p6 验证。

## 7. 独立 COMSOL 直接法参照

用户新增 `docs/COMSOL_direct_solver_report.md`。COMSOL MUMPS p4 hexa/h5 的
`R/T=0.000766316/0.602677531` 与仓库 p4/h5 离散参考
`0.000766313/0.602677531` 高度一致。COMSOL `A_total` 与仓库 `A_volume` 定义和闭合口径不同，
所以只作 cross-solver sanity reference，不替代 full true residual 或仓库 accuracy Gate。

## 8. 测试、证据与最终边界

| 检查 | 结果 |
|---|---:|
| ordinary pytest capture after `/tmp` fix | 18 passed, 2 skipped |
| h37.5 canonical replay targeted MPI8 | 1 passed per rank |
| full common-mesh test110 MPI8 | 13 passed, 1 skipped per rank |
| normalized DWR MPI2 fixture | 3 passed per rank |
| pre-heavy focused contracts | 39 passed, 3 skipped |
| normalized record/replay/classifier | 17 passed, 3 skipped |
| final Task035 focused suite | 136 passed, 3 skipped, 502 deselected |
| Ruff / compileall / JSON / diff-check | pass / pass / pass / pass |

主要证据：

- `records/actual_dwr_r_adaptive_tetra_p4_p5_h37p5_theta0p7_cycle1_full_periodic_closure_mpi8.json`
- `records/actual_dwr_multigoal_normalized_tetra_p4_p5_h37p5_theta0p7_cycle1_full_periodic_closure_mpi8.json`
- `outcomes/summary.md`
- `outcomes/test_summary.md`
- `outcomes/estimator_definitions.md`

最终边界：

```text
h37p5_one_cycle_R_only = vector_positive_strict_R_negative
h37p5_fixed_mesh_p6 = not_run_preflight_budget_failure
tolerance_normalized_multigoal = mechanism_pass_no_one_cycle_mesh_gain
hp_classifier = implementation_pass_real_three_level_validation_not_available
strict_RTA_resource_solution_10deg = structured_p4_h7p5
ordinary_default_changed = false
production_estimator_selected = false
production_backend_selected = false
master_merge = not_authorized
```

最终 response/docs commit 与远程 branch HEAD 由交付消息报告，不在本文制造自引用 SHA。
