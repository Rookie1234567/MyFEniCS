# h=2 启动决定

```text
h2_launch_decision = not_run
selected_diagnostic_profile = default MUMPS MPI2, one thread per rank
predicted_peak_range = 18.882–27.913 GiB
safe_h2_rss_limit = 13.5 GiB
blocking_stage = KSPSetUp / MUMPS analysis and numeric factorization
recommended_machine_memory = at least 48 GB physical; 64 GB preferred
```

## 阻塞 Gate

- G3 失败：h5 simultaneous RSS 下降 28.893%，但 h3 仅下降 15.119%，低于要求的 20%。
- G5 失败：27.913 GiB 预测上界超过 13.5 GiB。
- G7 失败：最终 preflight 可用内存约 12.83 GiB，低于 18.882 GiB 预测下界。
- G9 保持 false：更早的硬 Gate 已禁止启动，因此没有实现或激活 h2 watchdog。

h3 full run 的 residual/R/T/A 通过且无 swap，但这些条件不能覆盖其他失败 Gate。没有创建任何 h=2 进程或 artifact，Task28 reviewed h2 record 保持不变。按 Task29 合同，这是正确的安全决策，不是求解器失败。
