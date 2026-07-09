# Changed Files

## Code

- `src/common/config_3d.py`：新增 task010 MUMPS-BLR、shifted Maxwell、positive Maxwell profiles。
- `src/solvers/common_3d_solve.py`：新增 FGMRES right-preconditioned options、MUMPS-BLR options、operator-preconditioner metadata。
- `src/solvers/dtn_port_3d.py`：新增 `KSP.setOperators(A, P)` 路径和 Stage 4 operator preconditioner matrix assembly。
- `src/solvers/common_3d_case_flow.py`：在 success/failure summary 中写出 preconditioner metadata 和 P matrix stats。
- `src/studies/run_3d_matrix_scale.py`：CSV 新增 BLR、P matrix、A/P nnz、RSS、operator preconditioner 字段。
- `src/test/test_18_3d_direct_solver_profile_cleanup.py`：新增 task010 profile options 和 metadata 单元测试。

## Docs / Outcomes

- `docs/task010_shifted_maxwell_preconditioner/outcomes/`：生成本轮 summary、CSV、feasibility、ranking、raw_runs 与运行日志。
- `docs/README.md`、`README.md`、`notes/reference/current_version_boundaries.md`、`notes/reference/code_walkthrough.md`：同步 task010 结论和入口说明。

## Not committed

- `papers/High Performance Parallel Solvers for the time-harmonic Maxwell Equations.pdf`：用户提供论文，当前作为本地参考资料，不纳入本次提交。
- `results/`：本地完整运行结果目录，仍按项目约定不纳入 git。
