# Task029 changed files

## Commit A: telemetry

- `benchmarks/run_direct_memory_forensics.py`
- `src/solvers/common_3d_utils.py`
- `src/solvers/common_3d_solve.py`
- `src/solvers/dtn_port_3d.py`
- `src/solvers/common_3d_case_flow.py`
- `src/test/test_28_direct_memory_telemetry.py`

## Case050 与入口文档

- `benchmarks/cases/050_stage4_direct_memory_forensics/`
- benchmark checker/documentation contract/index files
- `docs/task029_stage4_direct_memory_forensics/outcomes/`

后续 Commit B–G 的文件与结果将在对应阶段追加；本文件不把用户未跟踪的 `papers/` 或 Task023 raw runs 列为 Task029 改动。

## Commit B checkpoint：h5 baseline evidence

- `benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_baseline.json`
- `docs/task029_stage4_direct_memory_forensics/outcomes/baseline_memory_timeline.csv`
- `docs/task029_stage4_direct_memory_forensics/outcomes/baseline_matrix_inventory.csv`
- `docs/task029_stage4_direct_memory_forensics/outcomes/baseline_factorization_summary.csv`
- Case050 `README.md` / `expected.json` / records index
- `benchmarks/records/benchmark_gate_report.json`（final implementation SHA `208aaab`，149/149）
- Task029 outcomes summary、run log、test summary 与 lifecycle 归因
- 顶层文档、benchmark、result schema 与 code walkthrough 状态同步

为使证据可信，h5 checkpoint 前还提交了 `5d71500`（factor Mat 不再二次 assemble）和 `208aaab`（最终 checkpoint 最大值与派生 factor ratio）。Commit B 仍需等待 h3 baseline，当前不进入优化候选。
