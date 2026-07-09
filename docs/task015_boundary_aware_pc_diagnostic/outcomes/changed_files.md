# Changed Files

## Code

| file | change |
|---|---|
| `src/studies/run_stage4_boundary_pc_diagnostic.py` | 新增 task15 boundary-aware diagnostic runner，包含 residual decomposition、aux modal decomposition、aux exact/diag、Schur_diag、aux-space modal 和 tiny10 FE exact 上界诊断 |

## Documentation / Outcomes

| file | change |
|---|---|
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/summary.md` | 中文总结、图表、瓶颈归因和 Task016 建议 |
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/*.csv` | 本轮诊断数据 |
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/charts/*.svg` | 残差、block fraction、top modal residual 图表 |
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/solver_profile_ranking.md` | profile 排名 |
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/merge_recommendation.md` | 合并建议 |
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/next_decision.md` | 下一轮决策 |
| `docs/task015_boundary_aware_pc_diagnostic/outcomes/run_log.txt` | 运行日志 |

## Not Added

| path | reason |
|---|---|
| `papers/` | 用户资料目录仍保持未跟踪 |
| `.npz/.h5/.xdmf/.vtu/.pvtu` runtime files | 大文件/中间文件不提交 |
