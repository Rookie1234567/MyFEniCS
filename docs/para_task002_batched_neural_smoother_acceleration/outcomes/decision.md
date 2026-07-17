# 决策

- P1/P2：通过；SciPy CSR 与 rank-32 固定线性映射通过局部门。
- P3：shadow 数值与 fail-closed 审计通过；墙钟有运行间波动，不据此宣称加速。
- P4：数值通过，性能信号失败。849→847 不满足 5% 迭代下降；151.343→137.261 s 的 9.30% 下降不满足独立 10% 门。
- P5/all-slab/h3/h2：按停机规则未运行。

最终分类为 `local_microkernel_success_global_signal_insufficient`。保留显式 opt-in 研究实现，不启用 ordinary default。
