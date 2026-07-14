# Task031 outcomes 索引

| 文件 | 内容 |
|---|---|
| `summary.md` | 标准化完整回顾、结果、解释、决策与证据入口 |
| `run_log.txt` | 主要 screen/full run 与最终 clean h5/h3/h2 摘要 |
| `test_summary.md` | serial/MPI1/2/4、full unit、checker 和 diff/clean-tree 验证 |
| `environment.json` | branch/SHA/image/host/物理与采样口径 |
| `memory_breakdown.csv` | Task030/Task031 内存、stage 和 payload 对比 |
| `krylov_comparison.csv` / `.md` | FGMRES restart、普通 GMRES 与 fixed-PC 结果 |
| `matrix_free_validation.md` | assembled-F-free public MPC form action、误差、ledger 与时间代价；非低层缓存 kernel |
| `factor_dedup.md` | exact fingerprint 负结果 |
| `overlap_funnel.csv` / `.md` | overlap/slab 筛选 |
| `selective_solver_funnel.csv` / `.md` | selective diagonal/fixed linear solver 筛选 |
| `h2_memory_prediction.md` | 两套独立预测与保守上界 |
| `h2_launch_decision.md` | h2 条件 Gate 与 watchdog 决策 |
| `negative_results.md` | 停止路线与原因 |
| `merge_recommendation.md` | 可合并/不可提升边界 |
| `next_decision.md` | 下一步因果关系 |
| `changed_files.md` | 代码、测试、benchmark、文档清单 |

重型完整 JSON、timeline、stdout 与场输出位于 `benchmarks/artifacts/cases/070/`，按仓库规则不提交。
