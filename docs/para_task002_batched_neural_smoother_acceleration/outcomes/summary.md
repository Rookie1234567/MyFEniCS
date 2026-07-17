# PARA-Task002 结果摘要

最终分类：`local_microkernel_success_global_signal_insufficient`。

任务严格停在 h5 one-slab P4；未运行 P5、all-slab、h3 或 h2，普通默认入口未改变。P1 的持久 SciPy CSR 在三个代表 slab 上耗时为 Python 行循环的 7.13%、7.26%、7.49%，误差为 0；PETSc owner-local MatMult 误差约 `2.6e-16`，但单次调用慢于 SciPy。

GPU 离线构造的 rank-32 固定复数 POD/ridge 映射无非线性激活。独立 validation 的 ILU-residual correction `rho median/p95=0.593884/0.745695`，线性误差 `3.894e-15`，确定性误差和 batch/independent 差异均为 0；推理加融合审计均值 2.281 ms，为 Task001 的 10.39%；p95 2.490 ms，为同数据 Task001 实测 p95 的 7.54%。

P3 shadow 始终写回原 ILU，5166 次候选全部通过非退化审计。P4 数值通过，但迭代仅从 849 降到 847（0.24%），solve 从 151.343 s 降到 137.261 s（9.30%），未达到 5% iteration 或独立 10% solve signal。故不允许扩展到全 slab，也不作全局加速声明。重型证据位于 Git-ignored `benchmarks/artifacts/cases/091/`。
