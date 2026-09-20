# Task39extra Response V25：V24 laptop-speed formal B 收口

## 首屏结论

按 Review V22 完成了唯一一次正式 B：`990-cell`、original p6/h7.5、MPI1、单线程、`126` 次外层迭代。正式结果为

`DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`。

旧 V23 的 p4 缺口已被最小前缀复现并做了有界修复：PC2 的首次 native A4 相对残差为 `2.887066115526587e-10`，同一 factor 额外一次 MatSolve 后为 `9.827559370577234e-13`。没有把它改写成“唯一舍入根因”；当前分类仍是 `CAUSE_UNRESOLVED_BOUNDED_REPAIR_QUALIFIED`。正式 B 的显式真实残差为 `9.283164961979326e-7`，释放后相同，物理一致性和清场均通过。

V24 完整 workflow 用时 `4579.015917060999 s`（约 `76.32 min`），旧 V23 同口径为 `5581.178597819002 s`（约 `93.02 min`），端到端观察比值 `1.218859837771`。这一数字是整场 workflow 对照，不能拆成某一个内核的独立因果收益。

线程选择保持保守：正式只采用 MPI1/单线程。没有运行 2/4-thread 的内存中性资格试验，因而没有把多核写成通过；V24 RSS/PSS 为 `7336173568 / 7303877632 B`，swap 为 0。RSS 比旧参考 `7387607040 B` 低 `51433472 B`，只记为单核正式路线的 observed-below-reference，不是多核 memory-neutral 结论。

## 对 Review V22 问题的逐项回应

### 1. 旧 p4 缺口、复现、根因边界与修复

旧失败项不是外层最终收敛不足，而是在线 p4 第一次返回的 native A4 质量超过 `1e-10`。P1 前缀只执行到指定 PC2，保存了原始返回、显式凝聚残差、端口/增广身份和 factor 复用关系。授权修复定义为同一 factor 上最多两次额外 F4；实际 PC2 一次额外 MatSolve 即达 `9.827559370577234e-13`，没有进入第三次逻辑调用。

这证明了“有界同因子修正”可以消除本次观测到的返回质量缺口，但没有证明单一的底层舍入根因。正式完整 B 的 p4 计数为 `254` 个逻辑调用、`255` 次物理 MatSolve；正式 solver、post-release 和 physical gates 均通过。

### 2. 哪些步骤更快

V24 正式路由使用优化的 owner transfer、固定 serial MPI1 owner route、native A6 authority 和原 H6 setup。分项 timing marker 记录了：

- p4 总累计 `230.02264079889574 s`；
- native A4 `255` 次，累计 `426.09123840702523 s`；
- native A6 `283` 次，累计 `1637.1402389939758 s`；
- owner primal/adjoint `255/258` 次，累计 `74.13890026698937 / 65.49211706320057 s`；
- full workflow 相比 V23 减少 `1002.162680758003 s`，约 `16.70 min`。

这些分项存在嵌套关系，只能作为同场成本账，不应相加得到总时间，也不应把整场收益归因到单个 owner kernel。

### 3. 2/4 threads 与内存

没有合格的 2/4-thread memory-neutral 正证据，所以没有采用共享内存多核，也没有启动第二场完整 PDE。正式环境固定：`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1`、MUMPS 1、MPI1。未运行项保持 `NOT_RUN`，不填成 pass。

## 七维裁决

| 维度 | V24 裁决 |
|---|---|
| `A4_RETURN_QUALITY` | `PASS_BOUNDED_REPAIR`；根因未唯一化 |
| `DISCRETE_SOLVE` | `PASS`；explicit/post-release residual 均 `<1e-6` |
| `PHYSICS_CONSISTENCY` | `PASS`；field、channel、power、energy、modal、identity checks 全通过 |
| `AUTHORITY_LIMITED` | `PASS_WITH_LIMITATION`；无匹配 h7.5 reference，不能宣称 continuum convergence |
| `SPEEDUP` | `MEASURED`；`1.218859837771x` end-to-end observed comparison |
| `MEMORY_NONINCREASE` | `OBSERVED_BELOW_REFERENCE_NOT_GENERAL_PROOF`；仅单核与旧正式参考比较 |
| `MULTICORE_ADOPTION` | `NOT_ADOPTED_NO_2_4_THREAD_PASS` |

## 正式物理结果

官方端口结果来自 `dtn_port_modal_amplitudes`：`R/T/A/A_volume = 0.36509755370062585 / 0.013016803347759889 / 0.6218856429516143 / 0.6218856421339044`。`R00_s/p/total = 0.3650608628870489 / 3.441729252877729e-25 / 0.3650608628870489`，80 个端口模式中 78 个传播，Rayleigh warning 为 0，`A_port-A_volume=8.177098997919074e-10`。

同包中的 Fourier E/H probe 给出另一组 diagnostic 数值，来源为 `diagnostic_eh_fourier_probe`，不作为 official R/T/A。这一区分已写入 outcome 和 compact record。

## 身份、测试与边界

正式 source 为 `b480178314efdf434c5f7405f2ab356ff9137c17`，input/physical/resolved SHA 分别为 `2ba250…eb6928`、`d8c5ab…1d036`、`3e4a07…7c4587`。正式服务 `exit=0`、watchdog `COMPLETED`、descendants cleared、zero swap。旧 V23 `58/59`、旧 response/summary、旧 authority-limited 和负结果没有覆盖或改判。

机器可读入口：

- [V24 outcome](outcomes/laptop_speed_v24.md)
- [compact](outcomes/records/laptop_speed_v24_compact.json)
- [A4 repair](outcomes/records/laptop_speed_v24_a4_repair.json)
- [components](outcomes/records/laptop_speed_v24_components.json)
- [checker](outcomes/records/laptop_speed_v24_checker.json)
- [decision](outcomes/records/laptop_speed_v24_decision.json)
- [thread selection](outcomes/records/laptop_speed_v24_thread_selection.json)

本轮没有 master merge approval；提交并推送执行分支后，停止等待主控 review。
