# 变更文件

| 路径 | 作用 |
|---|---|
| `src/solvers/local_slab_solver.py` | 新增 factorization-before-action 的 `LocalBackendPlan` |
| `src/solvers/physical_slab_two_level.py` | exact slab跳过 ILU；全 rank diagnostics；apply/factor/destroy lifecycle |
| `src/solvers/lu_teacher_local_solver.py` | exact solve mean/p95/max telemetry |
| `benchmarks/run_workstation_iterative.py` | exact no-hidden contract、one/two-step CLI、destroy record |
| `benchmarks/run_task031_memory_forensics.py` | 透传 exact allow-list 和 smoother steps |
| `benchmarks/neural_pc/benchmark_all_slab_exact_oracle.py` | 16-slab census/predictor |
| `benchmarks/cases/093_full_16_slab_exact_oracle/` | config、expected、recipe、轻量 records |
| `src/test/test_36_exact_lu_oracle_petsc_adapter.py` | 旧 exact adapter升级为 no-hidden |
| `src/test/test_38_local_backend_plan.py` | planning、ordinary ILU、MPI gather、destroy |
| `src/test/test_39_all_slab_exact_oracle_contract.py` | G4/G8/G16、census、predictor |
| `src/test/test_40_para_task004_contract.py` | outcomes、轻量 records、最终 Gate 一致性 |
| `src/test/test_26_documentation_contract.py` | 注册 Case093 |
| `docs/para_task003_*/response_v1.md` | 回应 Task003 review |
| `docs/para_task004_*/outcomes/` | Task004 全部结果 |
| `docs/development_progress.md` | 项目级阶段回顾 |
