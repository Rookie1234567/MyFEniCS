# Changed Files

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/studies/run_stage4_true_fe_sampled_schur_krylov.py` | 新增 | Task018 研究 runner |
| `docs/task018_true_fe_sampled_schur_krylov_integration/review_report.md` | 新增 | Task018 审查报告，确认 strong gate 通过并记录工程化风险 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/summary.md` | 新增 | 本轮中文总结 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/solver_profile_ranking.md` | 新增 | profile 排名 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/merge_recommendation.md` | 更新 | 合并建议，补充 SciPy selected FE RHS 与 PETSc selected FE-AMS 风险 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/next_decision.md` | 更新 | 下一步建议，指向 Task019 p=2 h=5 qualification |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/run_log.txt` | 新增 | 运行命令和关键日志 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/*.csv` | 新增/更新 | 数值结果表 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/parameters.json` | 新增/更新 | 可复现实验参数 |
| `docs/task019_p2_h5_true_fe_sampled_schur_qualification/task.md` | 新增 | Task019 任务书 |
| `docs/task019_p2_h5_true_fe_sampled_schur_qualification/outcomes/.gitkeep` | 新增 | Task019 outcomes 占位 |
| `docs/README.md` | 更新 | task018 审查结论、task019 索引与阶段结论 |
| `notes/theory/maxwell_iterative_preconditioners_task012.md` | 更新 | task018 后的理论路线笔记和工程化风险 |

未提交大体积矩阵/网格文件；`raw_runs` 中的 `.npz` 会在提交前清理。
