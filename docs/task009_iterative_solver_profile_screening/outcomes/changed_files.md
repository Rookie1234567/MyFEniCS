# Changed Files

## Code

- `src/common/config_3d.py`：新增 task009 iterative solver profile 名称，并保留 `default` / `mumps_ooc` direct profiles。
- `src/solvers/common_3d_solve.py`：新增 PETSc iterative profile option 表，包括 GMRES/Jacobi、BJacobi/ILU、ASM/ILU/LU、BiCGStab/PETSc `bcgs`，以及额外 GAMG/FieldSplit 探针。
- `src/solvers/dtn_port_3d.py`：记录 KSP setup/solve 时间、initial/final residual；为 FieldSplit Schur profile 注入 FE/auxiliary owned-index IS。
- `src/solvers/common_3d_case_flow.py`：summary 中新增 KSP residual、true residual、setup/solve time，并区分 `direct_lu` 与 `iterative_krylov`；未收敛时保持 diagnostic-only。
- `src/runners/run_3d_cases.py`：CLI 放开 PETSc solver profile choices。
- `src/studies/run_3d_matrix_scale.py`：CSV 输出新增 KSP/PC/sub-PC、reason、iterations、residual、setup/solve time 等 task009 字段。
- `src/test/test_18_3d_direct_solver_profile_cleanup.py`：补充 iterative profiles 映射测试。

## Docs

- `README.md`：更新当前 task009 分支、迭代求解器筛选结论和后续预条件器方向。
- `docs/README.md`：将 task009 从“待执行”更新为“已完成 outcomes，待审查”。
- `notes/reference/current_version_boundaries.md`：新增 task009 边界说明，强调现成 PETSc iterative profiles 尚不能作为生产求解器。
- `notes/reference/code_walkthrough.md`：新增 task009 代码阅读入口，并标注旧 direct solver 说明的历史边界。

## Outcomes

- `docs/task009_iterative_solver_profile_screening/outcomes/summary.md`
- `docs/task009_iterative_solver_profile_screening/outcomes/iterative_profile_summary.csv`
- `docs/task009_iterative_solver_profile_screening/outcomes/iterative_vs_direct_rta.csv`
- `docs/task009_iterative_solver_profile_screening/outcomes/iterative_resource.csv`
- `docs/task009_iterative_solver_profile_screening/outcomes/iterative_failure_cases.csv`
- `docs/task009_iterative_solver_profile_screening/outcomes/profile_ranking.md`
- `docs/task009_iterative_solver_profile_screening/outcomes/workstation_recommendation.md`
- `docs/task009_iterative_solver_profile_screening/outcomes/parameters.json`
- `docs/task009_iterative_solver_profile_screening/outcomes/run_log.txt`
- `docs/task009_iterative_solver_profile_screening/outcomes/raw_runs/`
