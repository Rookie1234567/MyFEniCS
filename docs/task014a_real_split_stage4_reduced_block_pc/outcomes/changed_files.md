# Changed Files

## 代码

| 文件 | 说明 |
|---|---|
| `src/studies/run_stage4_real_split_block_pc.py` | 新增 task14a 隔离实验脚本：complex export、real split matrix、Jacobi/FE-AMS+aux identity 对比 |
| `src/constraints/floquet_3d.py` | 增加 real-mode Floquet MPC 系数兼容层；纯实相位可转为 real scalar，复相位显式报错 |

## 输出文档

| 文件 | 说明 |
|---|---|
| `docs/README.md` | 追加 task014a 索引与执行结论 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/summary.md` | 本轮中文总结 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/stage4_real_split_equivalence.csv` | Stage A 等价性结果 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_summary.csv` | Jacobi 与 FE-AMS+aux identity 求解对比 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_memory.csv` | 内存与 AMS 数据规模 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/p2_h5_reduced_stage4_decision.md` | p2 h5 不运行决策 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/solver_profile_ranking.md` | profile 排名与改善倍数 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/merge_recommendation.md` | 合并建议 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/next_decision.md` | 下一步建议 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/parameters.json` | 参数与命令记录 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/run_log.txt` | 简要运行日志 |
| `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/raw_runs/` | 轻量 raw JSON、progress 和 metadata；`.npz/.h5/.xdmf` 二进制中间件未保留 |

## Notes

| 文件 | 说明 |
|---|---|
| `notes/theory/maxwell_iterative_preconditioners_task012.md` | 追加 task14a 后续记录和下一步路线 |
