# 变更文件

## 核心实现

- `src/solvers/hcurl_multilevel.py`：baseline pin、active DoF、nonmatching transfer/cache、Jacobi、shifted matrix、condensed Galerkin、multilevel 和 all-mode Woodbury 研究组件。
- `src/solvers/physical_slab_two_level.py`：subdomain-local diagonal shift、逐块建因子、factor-only storage、因子 nnz 遥测、生命周期清理，以及 MPI 空 owner collective 同步。
- `benchmarks/run_workstation_iterative.py`：只增加成功机制的显式 opt-in 参数；普通配置不变。
- `benchmarks/run_task030_multilevel_hcurl.py`：Task30 hierarchy 与统一 h5 funnel runner。

## 测试与合同

- `src/test/test_23_physical_slab_two_level.py`：local shift 与 factor-only action 等价性。
- `src/test/test_26_documentation_contract.py`：Case060 记录合同。
- `src/test/test_29_task_retrospective_contract.py`：Task30 outcome/progress 合同。
- `src/test/test_29_hcurl_multilevel.py`：baseline fail-closed、adapter、active DoF、transfer/cache、Galerkin、Woodbury 代数与生命周期。
- `benchmarks/check_benchmarks.py`：Case060 checker 合同。

## Benchmark 与项目文档

- `benchmarks/cases/060_multilevel_hcurl_iterative_solver/`：config、gates、runner 与轻量 records。
- `benchmarks/cases/README.md`、`benchmarks/benchmark_summary.csv`：Case060 索引和结果摘要。
- `docs/task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/`：完整执行档案。
- `docs/README.md`、`docs/benchmark.md`、`docs/capability_matrix.md`、`docs/development_progress.md`、`docs/solver_guide.md`：项目级同步。
- `notes/reference/` 与 `notes/theory/` 中相应 walkthrough、边界和迭代法说明。

未触碰用户本地 `papers/` 和 Task023 raw runs；重型 Task30 artifacts 不进入 Git。
