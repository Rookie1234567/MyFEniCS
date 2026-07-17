# 内存报告

原 ILU baseline、Task001 负候选、P3 shadow、P4 active 的含 R/T/A 峰值分别为 1.595348、1.650707、1.611607、1.618153 GiB。P4 相对 baseline 增加 1.43%，低于 10% guard；rank-32 模型为 5,390,336 bytes，SciPy slab-9 CSR 副本为 10,554,916 bytes。

P1 重复调用后 slab 9/10 未观察到新 peak RSS 增长，boundary slab 的一次性增长为 768 KiB。未执行 factor removal，因而没有 ILU factor 内存节省声明。
