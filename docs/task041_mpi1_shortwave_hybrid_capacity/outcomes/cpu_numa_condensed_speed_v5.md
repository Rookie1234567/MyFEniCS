# Task041 Review V5：R1d-B CPU/NUMA 匹配负载终态

## 结论

这次 R1d-B 只做了一个有界的内存吞吐诊断：每个 worker 是一个固定 CPU 上的单线程程序，先在本地 NUMA 节点完成 first-touch，再连续执行三个 60 秒窗口。它不是 PDE、MPI、QEP 或 Schur 计算，也不能把 driver `rc=0` 当成 CPU1 通过。

CPU0/socket0/node0 的三窗总吞吐稳定在约 32.18 GB/s；CPU1/socket1/node1 在相同本地 NUMA 约束下从 33.2632 降至 28.3382、再降至 9.2660 GB/s，第三窗比第一窗低约 72.14%（full-precision arithmetic 为 `72.14346483257299%`）。因此当前分类为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_COLLAPSE`，R2 继续 blocked。结果复现了 socket1 的性能异常，但没有证明 CPU 损坏、DRAM 热限流或唯一根因。

## 固定运行与窗口结果

| 项目 | 事实 |
|---|---|
| runroot / driver | [`r1d_result_summary.json`](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1d_load_20260920/run_20260920T131433.133791839Z/r1d_result_summary.json)，driver PID `2051231`，SID `2051231`，rc `0` |
| driver wall | 父侧 `CLOCK_MONOTONIC` `630.795106023 s`；UTC `13:14:33.179410647Z`–`13:25:03.994581030Z` |
| 负载 | 64 MiB 双缓冲、math threads=1；CPU1–8/node0 与 CPU25–32/node1 各 8 workers、各 3×60 s；无 MPI |
| socket0/node0 | `32.173939890 / 32.183022717 / 32.190473984 GB/s`；iterations sum `28771 / 28774 / 28779` |
| socket1/node1 | `33.263204952 / 28.338248830 / 9.265976385 GB/s`；iterations sum `29745 / 25343 / 8283` |
| 完成 | 16/16 worker 均 rc0，三个窗口均完成；启动和 near-end NUMA 观察均各 `8/8` local |

窗口吞吐是 8 个 worker 的 `bytes_per_second` 求和；不是单 worker 数值，也不是 32 个并行窗口。每窗精确 JSONL 与 hash 清单见 raw summary，未把并行 worker 时间重复计入账本。

## 频率、热与资源边界

600 个 turbostat 采样帧的活跃样本筛选（`Busy>=95%`，没有精确逐窗口时间戳）显示：socket0 1409 个样本平均 `Bzy_MHz=3596.151171`、核心峰温 `51°C`；socket1 1392 个样本平均 `3597.654454`、核心峰温 `52°C`，两侧 `CoreThr=0`。这排除了“核心频率掉到约 1 GHz”这一解释，但不能把高忙频率称为 CPU1 资格通过。

稀疏 PCI/BMC 采样全部 rc0，socket0 DIMM 峰 `64°C`、socket1 DIMM 峰 `78°C`，观测线为 `80°C`；状态保持 `ok`。前后 SEL 无新增差异；sticky 字段不当作当前限频。当前只读快照另见：resctrl 未挂载，`mc0..mc3` 的 CE/UE 计数为 0；这是一个当前快照，不能外推整个负载期间没有 MCE/EDAC 事件。

资源采样 364 行，`MemAvailable` 最低 `2115000832000 B`；global swap 使用 `299008 B`、pswpin `0`、pswpout `73`，本批新增 global swap delta 为 `0`。job/cgroup swap 未独立测量。没有 host thermal/resource Gate 触发停止；这不是完整硬件资格。

本批未测完整 process-tree/cgroup RSS 峰；双缓冲约 1 GiB 仅表示对象规模，不作为峰值资格。

## 清场、账本与后续

精确 PID 清场记录 [`r1d_cleanup_check.txt`](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1d_load_20260920/run_20260920T131433.133791839Z/r1d_cleanup_check.txt) 逐项检查 driver、turbostat、low-load worker 和 16 个 phase worker，20/20 在 `/proc` 中消失。此前按 `comm` 名称过滤得到零行仅作辅助，不能证明 bash/python 进程退出，该局限已保留。

唯一 V5 ledger 保留原 R1 两次计费条目，R1b/c 只读不计重型，并仅追加本次父侧 wall 一次：`803.973349829 + 630.795106023 = 1434.768455852 s`，当前 ledger SHA 为 `69aa9738e83d3d9d042124ef3a71e92df3489d6461c3d32a4465c64092ab0508`。compact 中的旧 `0ccfc62...` 是追加前的 `historical_as_of` 快照 hash，不是当前 hash。没有另建账本，也没有把 worker、BMC 或 turbostat 的嵌套时间相加。

R2–R6、PDE/QEP、R3 p4 草稿测试和新负载均 `not_run`。安全后续只建议在独占窗口下检查第二路 DIMM/IMC/供电与风道，并做已审的受控对照；本阶段没有改硬件、BIOS、功率限制、寄存器或源码。

## 证据入口

- driver 脚本 SHA：`37bea39b72656f2c8e0ce3bb293bbfc8ff41d7a17fa28fd1fc0cedf90976a584`。
- worker JSONL、resource gate、turbostat、BMC/SEL、NUMA observation 与 PID 身份文件均保存在上述 runroot；原始摘要 SHA：`b118353510dfb813ab4bee2ea6f93ee23ad56de23e437fb6fd218d7fd23f5bab`。
- 合并记录：[`task041_v5_cpu_numa.json`](records/task041_v5_cpu_numa.json)。
