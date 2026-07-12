# 本轮改动文件

| 文件 | 内容 |
|---|---|
| `src/studies/run_task024_engineering_iterative_solver.py` | real-split AMS/GMG 漏斗、原生 MatNest、手工 FGMRES、严格 m=1 outer、低峰值 CSR 导出、MPI collective 修复 |
| `src/studies/task024_numerics.py` | 独立 manual FGMRES、向量化/参考 CSR 过滤和不变量检查 |
| `src/studies/audit_task024_export.py` | 大缓存流式审计与 rank packet 顺序无关摘要 |
| `src/test/test_20_task024_numerics.py` | SciPy/PETSc、real/complex、MPI 与 CSR 单元测试 |
| `docs/task024_engineering_iterative_solver_fast_track/outcomes/*.csv` | h=5 回归、AMS/GMG 消融、h=2/h=1.5 residual/RSS/耗时 |
| `docs/task024_engineering_iterative_solver_fast_track/outcomes/*.md` | 设计、总结、门槛与合并建议 |
| `docs/README.md` | Task024 最新结论索引 |
| `notes/README.md` | 理论笔记索引 |
| `notes/theory/task024_manual_fgmres_real_split_response.md` | 本轮迭代器与 reduced outer 理论说明 |
| `docs/task024_engineering_iterative_solver_fast_track/response_v1.md` | 对 ChatGPT V1 审阅的逐条回应 |

`results/` 中的 rank NPZ、mesh 和完整运行目录保留在本地，不提交 Git。
