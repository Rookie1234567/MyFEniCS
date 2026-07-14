# 变更文件

## 核心实现

- `src/solvers/hcurl_multilevel.py`：baseline pin、active DoF、nonmatching transfer/cache、condensed Galerkin 与 research candidates；Review V2 后公共 `__all__` 只包含 validated infrastructure API，失败的 Jacobi/p-h/Woodbury lane 仅供 research runner/tests 直接导入。
- `src/solvers/physical_slab_two_level.py`：subdomain-local diagonal shift、逐块建因子、factor-only storage、因子 nnz 遥测、生命周期清理，以及 MPI 空 owner collective 同步。
- `benchmarks/run_workstation_iterative.py`：只增加成功机制的显式 opt-in 参数；普通配置不变；Review V2 增加 exact clean-SHA host attestation，容器 HEAD 不匹配时 fail closed。
- `benchmarks/run_task030_multilevel_hcurl.py`：Task30 hierarchy 与统一 h5 funnel runner。

## 测试与合同

- `src/test/test_23_physical_slab_two_level.py`：local shift 与 factor-only action 等价性。
- `src/test/test_26_documentation_contract.py`：Case060 记录合同。
- `src/test/test_29_task_retrospective_contract.py`：Task30 outcome/progress 合同。
- `src/test/test_29_hcurl_multilevel.py`：baseline fail-closed、adapter、active DoF、transfer/cache、Galerkin、Woodbury 代数与生命周期，以及 validated/research API 隔离和 clean-SHA attestation 回归。
- `benchmarks/check_benchmarks.py`：Case060 provenance、identity、residual、R/T/A、energy、memory 与分类数值 Gate。

## Benchmark 与项目文档

- `benchmarks/cases/060_multilevel_hcurl_iterative_solver/`：config、gates、runner 与带实际 provenance/SHA-256 的轻量 records。
- `benchmarks/benchmark_manifest.csv`、`benchmarks/benchmark_summary.csv`：Task30 三份 experimental records 的可重复生成链。
- `docs/task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/`：完整执行档案。
- `docs/README.md`、`docs/benchmark.md`、`docs/capability_matrix.md`、`docs/development_progress.md`、`docs/solver_guide.md`：项目级同步。
- `notes/reference/` 与 `notes/theory/` 中相应 walkthrough、边界和迭代法说明。
- `docs/task030_multilevel_hcurl_low_memory_iterative_solver/response_v1.md`：Review V1 P0 逐项回应与验证证据。
- `docs/task030_multilevel_hcurl_low_memory_iterative_solver/response_v2.md`：Review V2 clean h5/h3、historical h2、API 隔离、文档与最终验证回应。

未触碰用户本地 `papers/` 和 Task023 raw runs；重型 Task30 artifacts 不进入 Git。
