# h2 启动与资格复跑决策

`launch_h2 = true`，仅允许最终候选，不允许第二个 h2 参数族。

解锁依据：

- h5：855 步，真残差 `9.924905e-7`，峰值 1.696136 GB；
- h3：962 步，真残差 `9.903890e-7`，峰值 3.807503 GB；
- h3/h5 迭代比 `1.1251 <= 2`；
- h3 相对 Task27 canonical 5.082275 GB 降幅 `25.08%`；
- 两个独立 h2 中央预测：仿射 `9.5298 GB`、幂律 `7.0337 GB`；保守 15% 上界 `10.9593 GB`；
- 同一 80 模态、exact condensation、无 swap、ordinary default 不变。

首次 h2 运行在 1800 步达到真残差 `1.461130e-6`、峰值 9.342113 GB。内存通过但 residual Gate 失败，未输出 official R/T/A。由于它在 1800 步的 solve time 2220.43 s 仍略低于 Task27 的 2345.26 s，且残差轨迹继续稳定下降，允许同一参数、同一唯一候选把上限延到 2100 做资格复跑；这不是新的候选扫描。

资格复跑使用相同 PC/restart/物理配置，只把 `max_it` 从 1800 延到 2100；共同 monitor 点的残差逐位一致。最终结果：

- `ksp_reason=2`，1873 iterations；
- reported/condensed/full residual：`9.972228396e-7 / 9.972228402e-7 / 9.972228402e-7`；
- 含 R/T/A 峰值 9.374729 GB，较 Task27 降低 28.33%；
- `R/T/A=0.001342934415 / 0.599213236006 / 0.399443832218`；
- closure `2.639063e-9`，对 direct 最大差 `6.561388e-9`；
- 同一 80 modes，ordinary default unchanged。

因此 `workstation_success = true`；`strong_workstation_success = false`，因为 1873 步没有达到 1200/800 迭代目标。
