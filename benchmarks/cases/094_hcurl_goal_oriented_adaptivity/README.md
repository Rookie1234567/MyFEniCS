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
- `records/actual_r5_adaptive_tetra_p2_p3_h50_cycle2_deterministic_mpi2.json`：修复后
  clean-SHA、watchdog 保护的两轮 actual adaptive pass。cells `180→1308→8785`；p2 fixed-reference
  error `1.2026→1.0877→0.19535`，p3 `1.1473→0.14211→0.007041`；所有 true residual、
  R5 closure、Dörfler、orientation、periodic、source、memory 与 no-swap Gates 通过。该结果是
  research backend success；完成 cost-matched uniform control 前不宣称 adaptive efficiency 胜出。
- `records/actual_uniform_tetra_level2_p2_p3_mpi2.json`：同一 h50 起点连续两次全单元
  tetra refinement 的 true-uniform cost control，11,520 cells；所有 watchdog/PDE/mesh Gates 通过。
  对照显示 adaptive 使用 76.3% cells、75.5% peak memory 和 56.5% wall time，但 p2/p3
  fixed-reference error 是 uniform 的 18.26/5.74 倍。因此关闭 pure R5 production-marking lane，
  保留其 actual convergence evidence，下一主线转 actual goal-weighted DWR/adjoint。
- actual DtN discrete adjoint 已实现 official R/T gradient、`A^H z=g`、full true adjoint
  residual 和 correction-adjoint cell localization；p2/p3 serial/MPI2 identity 与独立共轭检查通过。
- `records/actual_dwr_r_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json`：首次 actual R-total
  DWR marked cycle，180→1276 cells。p2 fixed-reference error `1.202635→1.023485`，在比
  uniform level1 少 11.4% cells 时仅改善约 0.16%；p3 error `0.171653` 是 uniform 的 2.54 倍，
  因而保存为 mixed research result，不提升 production。
- `records/actual_uniform_tetra_level1_p3_p4_mpi2.json` 与
  `records/actual_uniform_tetra_level1_p3_p4_mpi8.json`：1440-cell p3/p4 uniform control。
  MPI2/MPI8 observable identity 通过；p4 error `0.00597711`，MPI8 wall `27.81 s`，并证明
  p4/uniform1 以 63,104 DoF、4.020 GiB MPI8 peak 胜过旧 p2/uniform2 的误差和资源。
- `records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_mpi8.json`：当前主要正结果。
  180→1268 cells，p4 DoF 55,884、error `0.00460020`、peak 3.983 GiB；相对 uniform1
  约少 11% p4 DoF 且 error 低约 23%。p3 同时仍较差，结论只限定为 high-order p4 positive。
- 两份 p3/p4 cycle2 record 保存连续收敛与复现实验：tie-policy-v1 run 最终 7348 cells、
  p4 DoF 315,444、error `0.000536345`、peak 18.831 GiB。它继续降低误差，但被 Task034
  structured p4/h7.5（147,844 DoF、约 `0.000328` error、12.724 GiB）同时支配，故第二轮为
  cost-dominated controlled negative。
- `records/actual_dwr_r_adaptive_tetra_p3_p4_h50_theta0p3_cycle1_mpi8.json`：theta=0.3
  只少约 4.9% p4 DoF，error 却为 theta=0.5 的 2.30 倍，关闭更低 theta/cycle2 sweep。
- Dörfler cutoff 已采用 near-tie expansion policy。低阶 fixture 的 serial/MPI hash 仍精确一致；
  三个独立高阶 MPI8 run 各标记 215 cells，pairwise overlap 为 `214/216=0.9907407`，但 solve-level
  浮点漂移使 exact marker hash 不同。因此 record 逐次绑定实际 hash，高阶重复性 Gate 使用
  overlap ≥0.99，文件名中的 `tie_stable` 不表示 exact-hash identity。

固定 Task034 geometry、S、10° grazing 上的当前 research stop rule 是
`p3/p4 + R_total DWR + theta=0.5 + exactly one tetra refinement`。尚未覆盖 robust-angle、
P 入射、Hybrid common mesh 或 production backend qualification，ordinary default 未改变。

这些 record 是 Task execution evidence，不由 ordinary Phase A checker 读取，也不改变顶部冻结的
staging 字段。Phase C/D 历史分类仍是 `phase_cd_complete_controlled_negative`；Review V4 的
actual global R5 mechanism 已通过，但 periodic tetra target backend、adaptive cycles 与
production estimator/backend 尚未资格化。Case094 仍不是 canonical benchmark；
`config.json`、`expected.json` 和 ordinary checker 的 `phase_b_or_later_results = not_available`
继续表示“staging ordinary contract 不提供后续正式 benchmark 结果”，不是否认 branch 上存在
noncanonical task evidence。
