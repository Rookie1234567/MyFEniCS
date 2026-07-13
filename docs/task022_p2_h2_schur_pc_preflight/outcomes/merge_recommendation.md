# Merge Recommendation

| 项目 | 建议 | 原因 |
|---|---|---|
| task022 outcomes | 合并 | 记录 h=5 可重复、h=2 阻塞点、RSS 和生产化设计 |
| `run_task022_p2_h2_schur_pc_preflight.py` | 可选合并 | research/preflight runner，有复现价值，不接入默认 solver |
| production Stage4 solver | 不合并变更 | h=2 PETSc/MPI production PC 尚未实现 |
| matrix-free docs | 合并 | 明确 matrix-free 的正确位置 |

审查重点：h=2 SPILU timeout 是否足以支持停止 serial SciPy 路线；PETSc/MPI PCShell 设计是否作为下一任务；official R/T/A blocked 是否需要优先于 h=2 继续求解。
