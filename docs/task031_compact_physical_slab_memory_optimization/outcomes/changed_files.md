# Task031 变更文件

## 实现

- `benchmarks/run_task031_memory_forensics.py`：外部同时 RSS/cgroup/swap/stage sampler、clean SHA、h2 lock/watchdog；Review V1 后 FGMRES 默认不强制 fixed-PC cert，非 FGMRES 仍由 worker 自动 fail closed；
- `benchmarks/run_direct_memory_forensics.py`：识别 MPI worker rank 的采样修正；
- `benchmarks/run_workstation_iterative.py`：KSP/smoother opt-in、PC cert、assembled-F-free public form action、compact lifecycle、ledger/stage/true residual；
- `src/solvers/mpc_form_action.py`：public DOLFINx-MPC form action 与 slave unit rows；
- `src/solvers/condensed_dtn.py`：external fine operator、`require_f/release_f`、safe destroy；
- `src/solvers/physical_slab_two_level.py`：PC cert、exact fingerprints、fixed Richardson/selective research path；
- `src/solvers/stage4_runtime.py`：保留 bilinear form 供 public form action；
- `src/test/test_22_condensation.py`、`src/test/test_23_physical_slab.py`：action/lifecycle/PC/fingerprint 回归；
- `src/test/test_30_task031_contract.py`：Task031 文档/Case070/records/ordinary-default 合同。
- `src/test/test_26_documentation_contract.py`：端口文档、项目规划文档与新增本地链接合同。

## Benchmark

- `benchmarks/cases/070_compact_physical_slab_memory_optimization/`：config、Gate、run、baseline/object/PC/screen/best/memory records；
- `benchmarks/benchmark_manifest.csv`、`benchmarks/check_benchmarks.py`、`benchmarks/cases/README.md`：Case070 自动 Gate 与索引。

## 文档

- `docs/task031_compact_physical_slab_memory_optimization/outcomes/`；
- `docs/task031_compact_physical_slab_memory_optimization/response_v1.md`；
- `docs/iterative_solver_ports.md`；
- `docs/development_progress.md`、`docs/README.md`、`docs/capability_matrix.md`、`docs/solver_guide.md`、`docs/benchmark.md`；
- `notes/quick_start/40_3d_workstation_iterative.md`；
- `notes/theory/iterative_solver_and_preconditioner.md`；
- walkthrough 32/33/50 与索引。

Task031 `task.md` 未修改。用户本地 `docs/task023.../raw_runs/` 与 `papers/` 未读取、未删除、未 stage。
