# Case094：H(curl) goal-oriented adaptivity（staging）

## 当前身份

```text
status = phase_a_in_progress
canonical = false
production_qualified = false
pde_run = false
phase_b_or_later_results = not_available
```

Case094 当前只是 Task035 Phase A staging case，用于保存环境、Task034 baseline 与
artifact descriptor 的可移植绑定。它不是冻结 benchmark，不包含 estimator、adaptive
cycle、p4 主线或生产结果。

## 当前证据

- `records/base_manifest.json`：tracked、clean-checkout hermetic 的 Phase A base binding；
- `records/phase_a_regression_failure.json`：首次旧 numbered-case 合同失败历史，永久保留；
- ignored 环境与 Task034 artifacts 只由路径和 SHA-256 descriptor 绑定。

## Checker

从仓库根目录执行：

```bash
source .venv/bin/activate-myfenics
python -m benchmarks.task035_case094
```

该命令只运行 hermetic Phase A checker，不读取 ignored artifacts、不启动 MPI、不组装
PDE。需要本机人工复核 ignored artifact 时必须显式使用 `--verify-artifacts`；该模式
不是 `test_command.txt` 的普通入口。

## 可用与不可用结果

当前可用：环境/base descriptor、Task034 compact reference binding、首次失败历史。
当前不可用：Phase B estimator fixtures、Phase C bake-off、adaptive cycles、p4/Hybrid
adaptive results、robust common mesh 和任何 production qualification。

## 升级条件

只有 Task035 Phase B–K 按任务书完成相应 fixture、mesh、数值和资源 Gate，并在 Phase K
冻结完整 Case094 benchmark 后，才能：

1. 从 `STAGING_OR_IN_PROGRESS_CASES` 移入 `QUALIFIED_OR_FROZEN_CASES`；
2. 将 `canonical` 或 `production_qualified` 改为 true；
3. 启用正式 case 的 22 项参数表、全部章节、record/run/test 合同；
4. 宣称 Phase B 或后续 measured results 可用。

升级前不得把本 staging scaffold 冒充 canonical Case094。

## Task execution evidence（不改变 staging contract）

Review V3 已完成 Phase C/D 低成本执行，新增：

- `records/phase_cd_mpi1.json`：clean-SHA serial C+D record；
- `records/phase_cd_mpi2.json`：clean-SHA MPI2 C+D record；
- `records/phase_cd_mpi_identity.json`：compact metric identity；
- `records/phase_cd_mpi2_initial_volume_measurement_failure.json`：首次伪零体积 measurement failure 历史。
- `records/actual_global_r5_p2_p3_h10_mpi8.json`：Review V4 clean-SHA、watchdog 保护的
  target Full3D p2/h10→p3/h10 actual global two-level R5；包含 true residual、official
  R/T/A、逐 owned cell correction energy、Dörfler hash、资源峰值与 raw artifact SHA-256。
- `records/actual_global_r5_tetra_p2_p3_h50_mpi2.json`：matching periodic tetra、exact
  material planes、triangular N1curl trace 下的真实 target p2→p3 R5；用于解锁 estimator-marked
  tetra refinement research lane，不代表 adaptive cycle 或 production qualification 已通过。
- estimator-marked tetra mechanism 已新增 facet-authoritative periodic cell closure、实际 refinement
  edge closure、正 orientation 重建及 partition-independent mesh/tag hashes；serial/MPI2 fixture
  identity 通过，但真实 adaptive cycle 仍须由后续 clean-SHA watchdog run 证明。
- `records/actual_r5_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json`：首次 clean-SHA actual
  marked cycle 的历史记录。mesh、PDE、R5 和资源 Gate 均通过；旧 moving p2/p3 gap Gate 将
  结果标为 `formal_not_pass`。相对 Task034 hash-bound p4/h5 fixed reference，p2/p3 error
  实际分别下降 1.06%/62.83%，因此该记录是 metric-definition controlled failure，不是 estimator negative。
- `records/actual_r5_adaptive_tetra_p2_p3_h50_cycle2_reference_gate_mpi2.json`：fixed-reference
  Gate 修正后的第二次受控停止。首轮 reduction 通过；第二层 distributed DOLFINx propagation
  产生 unmatched periodic triangles，故在 cycle2 PDE 前停止。orientation、quality、tags 和资源仍通过。
  后续 mechanism 改为 full periodic boundary-edge synchronization，并用 replicated `COMM_SELF`
  deterministic refine 后再分发；两层 serial/MPI2 mesh hash identity fixture 已通过。

这些 record 是 Task execution evidence，不由 ordinary Phase A checker 读取，也不改变顶部冻结的
staging 字段。Phase C/D 历史分类仍是 `phase_cd_complete_controlled_negative`；Review V4 的
actual global R5 mechanism 已通过，但 periodic tetra target backend、adaptive cycles 与
production estimator/backend 尚未资格化。Case094 仍不是 canonical benchmark；
`config.json`、`expected.json` 和 ordinary checker 的 `phase_b_or_later_results = not_available`
继续表示“staging ordinary contract 不提供后续正式 benchmark 结果”，不是否认 branch 上存在
noncanonical task evidence。
