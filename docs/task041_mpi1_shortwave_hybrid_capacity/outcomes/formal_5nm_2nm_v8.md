# Task041 V8：5 nm 正式 consumer 终态与 2 nm 后续

5 nm cell-condensed 路线先消去单元内部自由度，再恢复完整场并检查原方程；内部目标 `5e-13` 最多追加两次同因子修正，原物理残差门不变。

## S1：5 nm 完整 consumer 已完成

| 项目 | 结果 |
|---|---|
| 运行身份 | unit `task041-v8-5nm-cellcond-formal-20260928.service`，Invocation `755aeb44c48a4d1cbc8bbf6db9f6fd3e`；运行源码 SHA `d86ee4afb352304c9ff0d5042256ad9a7d0c9a4f`，结束仓库 HEAD `499c25de74c30ed0bdee17180f5315765f35efbe`。两者间仅五条获准文档路径有提交，运行代码与输入绑定未变。 |
| 模型/范围 | W，5 nm，p6/h4，M480，MPI8×1，CPU1–8/node0，registered `cell_condensed`；正式响应 1920/1920，RTA/EH/衍射及清理完成。QEP复用，未重算。 |
| 数值门 | consumer `TASK041_CONSUMER_PASS`；reported/global/bottom/top/modal/recovery/physics 原门全过。五项 true residual 最大 `6.221702926229589e-11`，均不超过 `5e-9`。`R/T/A/A_volume = 0.7331842733877258 / 0.00022009869572838214 / 0.2665956279165458 / 0.2665962726230213`；closure `6.447064755388254e-7`。 |
| 迭代与target | outer right FGMRES 共5步、reason=2；target `5e-13` 请求已传入，worker记录实际cell-condensed路线。 |
| Exact参考对照 | R/T/A/A_volume 最大绝对差 `5.6561e-13`，低于 `1e-8`；canonical E/H相对差最大约 `4.011e-10`，低于 `1e-5`；显著衍射项及normal-flux检查通过。离线比较整体分类仍为resource/inherited-producer对照不完整：旧exact producer缺少本次所需的 `exact_raw_phase_measured`，不把其资源可比性记为通过。 |
| 资源 | cap/warning/reserve=`53,221,163,008 / 47,899,046,707 / 412,316,860,416 B`。process-tree RSS峰 `43,153,915,904 B`，authority峰 `43,858,726,912 B`。cgroup `memory.peak=43,867,639,808 B` 是历史计数器峰值，不是采样到的 `memory.current` 峰值。job/cgroup swap峰为0；global swap/pswp活动仅按V8记录观察。 |
| 时间/终态 | consumer worker wall `189,308.766050059 s`（`52.585768 h`）；public workflow wall `189,317.508985 s`；public至finalizer `189,323.841971 s`（`52.589956 h`）。24 h目标未达到，不自动强停。unit自然执行worker exit0，但public以exit3结束：结束时SHA不等于运行SHA。finalizer保留该失败分类；闭合artifact hash、清场及唯一ledger写入通过。 |

旧worker基线 `53.239672 h` 与本场worker wall是同口径：本场约少 `0.653904 h`，即约 `1.23%`。另一个常用的 `52.589956 h` 是public至finalizer墙钟，与旧worker口径不同；跨口径约`1.22%`只能作粗略参考。邻heavy任务并行且未触碰，性能不是无竞争资格。

public runroot：`results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8_cell_condensed/task041_5nm_p6h4_m480_mpi8_cell_condensed__hybrid_iterative__mpi8__M480/20260928T085850.487306Z`。outer root：`results/task041_v8_5nm_cellcond_formal_run_20260928`。离线exact比较记录：`results/task041_v8_5nm_cellcond_formal_run_20260928/exact_comparison_offline_v1.json`；终态与原始finalizer证据均留在ignored results中。

## S2：2 nm 最小下一步

复用旧D1e的W/2 nm、p6/h1.5、M1200物理与QEP packet，沿既有registered入口改用cell-condensed及`5e-13` target；同一生命周期完成early repeat准入后接续4800项响应。p4/KSP需要重建，QEP不重算。node0可用内存须按当时现场满足旧2 nm hard/warning与412,316,860,416 B reserve；swap仅观察。旧D1e repeat失败保留为必须由新early样本重新验证的数值风险。2 nm 尚未启动。

机器记录见[Task041 V8 record](records/task041_v8_formal_5nm_2nm.json)。
