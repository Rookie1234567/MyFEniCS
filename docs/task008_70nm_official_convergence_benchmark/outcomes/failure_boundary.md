# Failure Boundary

## 结论

本机 WSL/Docker default MUMPS direct 的 task008 边界为：p=1 可完成到 h=1；p=2 可完成到 h=2，但 p=2 h=1.5 在 KSP setup 阶段被系统 kill。p=2 h=1 甚至 assemble-only 都没有完成，不进入 direct solve 计划。

| p | last completed direct h | first failed direct h | failure stage | returncode/RSS | note |
| --- | --- | --- | --- | --- | --- |
| 1 | 1.0 | 未尝试 h<1 | 无 | RSS upper 18.1 GB | p=1 h=1 completed |
| 2 | 2.0 | 1.5 | stage4_dtn_augmented_ksp_setup | returncode 9, RSS upper 14.4 GB | signal 9 / Killed |
| 2 assemble | 1.5 | 1.0 | stage4_dtn_base_matrix_assembled | timeout 124, swap delta 33.4 GB | h=1 不建议 direct |

## 解释

p=2 h=1.5 的 assemble-only AIJ 矩阵估算约 3.20 GB，看起来不大，但 direct MUMPS 需要 LU factorization fill-in 与内部工作区。失败点发生在 `stage4_dtn_augmented_ksp_setup`，说明瓶颈已经进入求解器设置/因子化准备阶段，而不是几何或能量后处理。

p=2 h=1 的 assemble-only 已经达到约 10.31 GB AIJ 矩阵估算，并在 2400 s 后超时，期间 swap 增加约 33.4 GB。因此本轮没有继续硬跑 p=2 h=1 direct。

后续若要推进 p=2 h=1.5 或更细网格，建议单独任务评估 tuned MUMPS OOC 或迭代法；直接增加普通内存也需要考虑 LU fill-in，不应只按 AIJ 矩阵 GB 线性估算。
