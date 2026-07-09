# Changed Files

## 2026-07-07 表格补充

为方便人工阅读和 ChatGPT 审查，本次补充了 Markdown 对比表：

- `summary.md`：新增 Stage A Krylov 总览表、AMS/HX 烟测表、候选路线对比表。
- `profile_ranking.md`：新增 profile 排序表。
- `ams_hx_smoke_notes.md`：新增 AMS/HX 数值表。
- `matrix_free_matvec_feasibility.md`：新增 matvec 误差表。
- `next_decision.md`：新增下一步决策矩阵。

## Code

- `src/common/config_3d.py`：新增 task011 低内存 Krylov profile 名称。
- `src/solvers/common_3d_solve.py`：新增 Jacobi-Krylov option helper 和 profile metadata。
- `src/solvers/common_3d_case_flow.py`：把 low-memory Krylov metadata 写入成功/失败 summary。
- `src/studies/run_3d_matrix_scale.py`：matrix-scale CSV 增加 restart 与 low-memory metadata 字段。
- `src/studies/run_ams_hx_smoke.py`：新增 FE-only hypre AMS/HX smoke runner。
- `src/studies/run_matrix_free_matvec_smoke.py`：新增 UFL action matrix-free matvec smoke runner。
- `src/test/test_18_3d_direct_solver_profile_cleanup.py`：新增 task011 profile option 和 metadata 测试。

## Docs / Outcomes

- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/low_memory_krylov_summary.csv`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/low_memory_krylov_failure_cases.csv`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_notes.md`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_summary.csv`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/stage4_blockdiag_ams_summary.csv`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/stage4_blockdiag_ams_vs_direct_rta.csv`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/matrix_free_matvec_feasibility.md`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/solver_memory_comparison.csv`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/profile_ranking.md`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/next_decision.md`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/parameters.json`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/run_log.txt`
- `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/raw_runs/`

## Notes

本轮同步更新：

- `docs/README.md`
- `notes/reference/current_version_boundaries.md`
- `notes/reference/code_walkthrough.md`
