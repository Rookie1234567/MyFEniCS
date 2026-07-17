# 变更文件

- `src/solvers/local_slab_solver.py`：持久 SciPy CSR action。
- `src/solvers/batched_reduced_smoother.py`：冻结线性映射、checkpoint、batch、融合审计及 shadow/active adapter。
- `benchmarks/neural_pc/benchmark_local_action.py`、`fit_linear_reduced_map.py`、`evaluate_batched_reduced_smoother.py`：P1/P2 工具。
- `benchmarks/run_workstation_iterative.py`：显式 opt-in one-slab P3/P4 集成。
- `src/test/test_34_para_task002_linear_reduced.py`：合同测试。
- Case091、本 outcomes 目录及 `docs/development_progress.md`：轻量证据。
