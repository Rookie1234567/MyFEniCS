# 改动文件

| 文件 | 内容 |
|---|---|
| `src/studies/run_task025_parameter_robust_multilevel_hcurl_pc.py` | 新增 shifted ASM、gradient/p/h coarse、2D coarse、BDDC、full FieldSplit、cached 80-response Schur runner |
| `src/studies/run_task023_petsc_mpi_fe_response_pc.py` | FieldSplit FE 子 KSP 支持独立 shifted preconditioning matrix 和 ILU level/order |
| `src/studies/run_task024_engineering_iterative_solver.py` | complex p-transfer 验证修复、cache 转实数无警告、p1 AMS degree 修复 |
| `docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/*` | Task025 表格、日志、参数、gate 与总结 |
| `notes/theory/task025_parameter_robust_multilevel_hcurl_pc.md` | 本轮理论与实现结论 |
| `docs/README.md` | 更新最新任务结论 |
