# 变更文件

- `benchmarks/neural_pc/petsc_capture.py`：slab allow-list 与 raw-RHS-only capture。
- `src/solvers/lu_teacher_local_solver.py`：one-factor/many-RHS sparse-LU teacher/oracle backend。
- `benchmarks/neural_pc/build_lu_teacher_dataset.py`：A/B/C raw capture、teacher labels、资源/精度/checksum。
- `benchmarks/run_workstation_iterative.py`：显式 exact-LU oracle allow-list。
- `src/test/test_35_lu_teacher_contract.py`、`test_36_exact_lu_oracle_petsc_adapter.py`、`test_37_para_task003_contract.py`：teacher lifecycle、MPI owner adapter 与执行阶段合同。
- `benchmarks/cases/092_lu_teacher_nn_only_local_inverse/`：轻量 Case 合同。
- Task002 `response_v1.md` 与 classification 统一；Task003 outcomes 和 `development_progress.md`。
