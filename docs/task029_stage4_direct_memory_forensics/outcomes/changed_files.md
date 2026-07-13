# Task029 changed files

## Commit D–G：profile 筛选、候选资格与最终决策

- `benchmarks/run_direct_memory_forensics.py`：两点幂律预测 helper；h2 Gate 补齐 G1–G10 字段。
- `src/test/test_28_direct_memory_telemetry.py`：prediction、blocked launch、candidate record 合同。
- Case050 `records/h5_mpi2_candidate.json` 与 `records/h3_mpi2_candidate.json`。
- `candidate_comparison.csv`、最终 `optimization_hypotheses.csv` / `optimization_manifest.csv`。
- `gate_decision.csv`、`h2_memory_prediction.md`、`h2_launch_decision.md`。
- `merge_recommendation.md`、`next_decision.md` 及 outcomes/Case050/index/walkthrough 同步。

正式候选 full solve 来自 clean source `6babe4700328be2b3b93aad7e3e6c212b6dbad10`；之后只增加纯预测 helper、测试、轻量 records 与文档，不改变 worker 的物理/数值求解路径。h2 未运行，Task28 canonical records 未覆盖，用户未跟踪的 `papers/` 与 Task023 `raw_runs/` 仍未修改或暂存。

## Commit C 候选：低风险生命周期与 profile 证据

- `SimulationConfig3D.direct_release_base_after_augmentation`（默认 false）
- DtN copy 后 opt-in 释放 `A_base/b_base`
- `DirectSolveFailure.cleanup()` 与 failure summary finally cleanup
- 显式可用 MPI distributed factor package 选择
- Case050 OOC scratch/I/O sampler 与 candidate lifecycle record
- `optimization_hypotheses.csv`、`optimization_manifest.csv`、`direct_object_lifecycle.md`
- `test_18` / `test_28` 与 code walkthrough 更新

普通 default 不变；所有内存候选仍需提交后 clean-source full solve。

## Commit B checkpoint：Stage B 完整 baseline evidence

- 新增 `benchmarks/cases/050_stage4_direct_memory_forensics/records/h3_baseline.json`
- h5/h3 共同更新三份 baseline CSV
- 新增 `docs/task029_stage4_direct_memory_forensics/outcomes/rank_scaling.csv`
- 更新 outcomes summary、lifecycle、test summary、Case050 状态与 records index

h3 MPI4 full solve 通过且无 swap；h5 MUMPS MPI1/2/4 rank-count 诊断完成。MPI2/MUMPS 被选为后续 h3 低风险候选。重型 artifacts 仍被 gitignore 排除。

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

后续 Commit C–G 的文件与结果将在对应阶段追加；本文件不把用户未跟踪的 `papers/` 或 Task023 raw runs 列为 Task029 改动。

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
