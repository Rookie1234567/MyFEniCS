# Task041 Review V5：R1i 2666 复测、R1h 跨 NUMA 复现与历史证据

## 2026-09-22：R3h8 p4 凝聚组件阶段进展（R3–R6尚未完成）

p4 单元凝聚先消去单元内部未知量，解较小的保留耦合系统，再回代恢复完整 FE/端口修正，并用原 A4 和完整残差检查；数学逆和精度没有放宽。p6 已经凝聚，本阶段不重复消元；`cell_condensed` 只是显式可选后端，默认 `full` 路径不变，正式 runner 尚未接入 `cell_condensed`。

| 证据 | 已核对实值 | 边界 |
|---|---|---|
| R3h5 side/backend 回归 | serial `27 passed / 4 skipped`；MPI2 每 rank `31 passed`；最终 ABI 均 `rc=0` | 首轮 ABI NameError 后仍运行 pytest 的尝试不计资格；R3h1–3 的 rc59/gdb/trace 负历史保留 |
| R3h6 serial tiny FE | 同一 side/layout old/new Q `1.3382559074923613e-13`、PC `1.3047558741076922e-13`；四项 A4 最大 `3.1267280149834914e-11`（阈值 `1e-10`）；各路径 backsolve `1`；307 次资源样本，RSS 峰 `3788111872 B`，PSS/USS 为稀疏观测，swap 增量 `0`，清场通过 | tiny FE 资源门通过，不外推正式 MPI8、13.5/5/2nm、大模型或性能资格 |
| R3h6 MPI2 tiny FE | Q `1.2026417833118804e-13`、PC `1.1310942394716736e-13`；四项 A4 最大 `3.2111545815853925e-11`；各路径 backsolve `1`；152 次资源样本，RSS 峰 `1280536576 B`，swap 增量 `0`，清场通过 | 首样本仅含 parent+mpiexec，第二样本才含两 rank；不把 `167 s` 对 `82 s` 写成加速 |

完整来源、七个源码 SHA、donor manifest、原始索引和命令/ABI入口见 [R3h8 tracked record](records/task041_v5_condensed_speed.json)；冻结摘要见 [R3h7 compact](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3h_validation_20260921/r3h7_compact.json)。R3f 是 p4/port 完整逆对照，R3c/R3d2 分别是早期 synthetic 与双端口/preallocation 资格；Q/PC old/new 只归 R3h6。R3h8 已一次追加 `288.010923037 s`，累计 `7600.153469588 s`；后续文档纠偏未再计费。R3–R6 尚未完成。


## R1i 2666 复测终态（历史快照）

R1i 在用户维护重启后仅将 BIOS Memory Frequency 从 `Auto` 改为 `2666 MT/s`，其它设置、风扇、保护和刷新策略未改；本次仍是工作站 CPU/NUMA 内存复制诊断，不是2nm物理模型、PDE或MPI计算。四组路径三窗总吞吐如下：

| path | 三窗吞吐（GB/s） | 结果边界 |
|---|---:|---|
| local socket0 cores1–8 → node0 | `35.63788506479269 / 35.664033252580786 / 35.6967308849817` | 稳定；不据此给 CPU0 新硬件资格结论 |
| local socket1 cores25–32 → node1 | `35.648371306083156 / 31.66995975917892 / 11.024863223982754` | node1 路径继续崩落；CPU1 未准入 |
| cross socket0 cores1–8 → node1 | `23.562553384022838 / 22.956933903624012 / 13.10402684910857` | node1 路径继续崩落 |
| cross socket1 cores25–32 → node0 | `23.408224743881927 / 22.924688775860275 / 21.682633764800535` | 约 `7.37%` 下降，不写成零退化 |

两批均 `rc=0` 并完成清场，但这不等于修复：node1 访问路径仍出现骤降。R1i 共绑定43个 PCI raw 与43个 BMC 文件、16个DIMM槽、688对值，差值范围 `[-1,+1]°C`；六个 TEMPLO 与两个 TEMPMID 事件及逐文件 SHA 见 [R1i tracked compact](records/task041_r1i_2666_retest_20260921.json)，同内容 ignored 原件为 [compact v3](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1i_2666_retest_20260921/r1i_2666_two_batch_compact_v3_20260921.json)，SHA `4e7a3d0e21bfe53da457010493a22c71140b7cf734bfdf4b1034f88bc2cacbc6`。cross `P1-DIMMC1` TEMPLO sample4→5 的时间括号按 PCI `65→67°C`，异步 BMC 为 `65→66°C`；sample1–10 未见新 TEMPMID，但 after_load 后续置位，触发时刻未知。控制器 `TEMP_MID 93→95°C` 仍只是未执行的只读评估，未改阈值、补偿、刷新、保护或80°C观察线；不能把本轮结果写成原因已解决。TEMPLO/TEMPMID 表示较低/中间温度阈值被越过的事件；sticky 只表示两次读取之间曾发生过置位，不表示此刻仍在限速。

字段解释的 primary 入口：[Intel 二代 Xeon Scalable datasheet Vol.2](https://www.intel.com/content/dam/www/public/us/en/documents/datasheets/2nd-gen-xeon-scalable-datasheet-vol-2.pdf)（`@108/@120/@140/@150`）；[Intel S2600WF TPS §12.3.4.2](https://cdrdv2-public.intel.com/610835/Intel_Server_Board_S2600WF_TPS_2_6.pdf) 仅作同代 TSOD offset/风速机制参考；[Micron MTA144ASQ16G72LSZ-2S9E1 datasheet Table 12](https://www.nyang-tech.com/datasheet/1052970336/Micron-Technology-Inc./MTA144ASQ16G72LSZ-2S9E1.pdf) 用于温度与2×刷新边界；[Supermicro FAQ35599](https://www.supermicro.com/en/support/faqs/faq.php?faq=35599) 用于 BMC Full mode。以上不证明 X11DAi-N 的具体补偿公式，也不授权阈值写入。

## R1h 历史终态（已由 R1i 更新）

R1h 是一次不改硬件、不改系统设置的跨 NUMA 内存复制诊断，不是 PDE、MPI、QEP 或物理模型计算。CPU socket0 的 OS CPU1–8 将双缓冲 first-touch 到 memory node1；CPU socket1 的 OS CPU25–32 将其 first-touch 到 memory node0。两阶段均为 8 个单线程 worker、3×60 s；阶段开始和 near-end 均观察到 `8/8` 个 buffer 位于预期的远端 node。

同一 R1h 目录先前直接执行 `664` driver 的 `rc=126` 启动级负结果保留在 compact 中；仅改为显式 `/bin/bash` 启动，未计作第二轮压力负载。

| phase | 三窗吞吐（GB/s） | iterations sum | 结果边界 |
|---|---:|---:|---|
| socket0 / OS CPU1–8 → memory node1 | `22.648688106036644 / 21.977584096329075 / 7.395682818558859` | `20254 / 19649 / 6616` | 第三窗较首窗约降 `67.35%`；未准入 |
| socket1 / OS CPU25–32 → memory node0 | `19.789193732901627 / 19.759391333017003 / 18.843317623093906` | `17697 / 17665 / 16847` | 第三窗较首窗约降 `4.78%`；不写成零退化 |

R1h driver rc0、父侧 `CLOCK_MONOTONIC` wall `629.724913916 s`；16/16 worker 三窗完成，且精确 PID 清场。22 个硬件 raw sample、110 个 final-read、44 个 MSR 文件（每个48行）均已绑定；新 PCI/MSR 读取均 rc0，MSR 输出为0。资源共有358个 sample，最低 `MemAvailable=2114795454464 B`，swap `299008 B`、`pswpin=0`、`pswpout=73`，新增 global swap delta 0。16 个 worker 相邻采样的 minor/major/stime delta 均为0；CPU0/CPU1 最大 `wait/(run+wait)` 为 `0.0009933352281917688`/`0.0008195138298330328`；同一 shared cgroup 的 `nr_throttled/throttled_usec/high/max/oom/oom_kill` 均为0。global NUMA counters 仍只作主机快照，不归属于本批。

活跃 `Busy>=95%` 样本的平均 Bzy_MHz 为 socket0 `3600.3309404163674`、socket1 `3599.549568965517`，CoreThr=0；因此不支持“核心频率降到低档”这一简单解释，但不排除内存控制器、固件、DIMM 链路或内部温控路径。BMC 温度按样本时间对 60 秒窗口作括号归属，并非同刻极值，且仅来自 `P1-DIMMC1` 与 `P2-DIMME1` 两个探头，不代表整组 DIMM 的 min/max：CPU0→node1 阶段约 `P1-DIMMC1 47–54°C / P2-DIMME1 54–78°C`，CPU1→node0 阶段约 `P1-DIMMC1 57–77°C / P2-DIMME1 76–77°C`。第一阶段第三窗在 P2-DIMME1 78°C 平台附近发生下降，只是相关；80°C 是观察线，不是内部限温阈值。所有 e24 读取为0，只削弱持续外部 MEMHOT，不排除采样间瞬态或其他热控路径；sticky 字段不作当前限速证据。

当前分类为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_ANOMALY_REPRODUCED_NO_UNIQUE_CAUSE`，R2 blocked。没有完整 process-tree/cgroup RSS 峰值；双缓冲对象大小不代替峰值资格。没有硬件、BIOS、功率、风扇、寄存器写入，也没有新 R2/PDE。

证据入口：[R1h compact](records/task041_v5_cpu_numa.json)、[R1h raw summary](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/r1h_result_summary_20260920.json)。driver SHA `f81d917bd462e1a5028a8bb8c3f4ca3aaad4122a9f2adaec8a6990a616099bc4`，worker SHA `7ce2dd8ff6f71cf4e9b9c13a156e1f0f0b15b38af010ac0b2b04881ec3ce0ad9`，runroot 为 `results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/run_20260920T154556.093635044Z`。launch metadata SHA `62496750a7ac9d6bce344bce279e9f31b7dde65e4379aa320ca0aa7825e2945e`；driver log SHA `a7e0a45ca321b65b27a04c75f804a8352faf167bd577da908268c15dd721e977`；hardware aggregate SHA `03c00115b46de257495388999e4bbe7cc605f1bbfca56a66aa62bcdacfb8be21`；worker aggregate SHA `bc56bcc7fec6ae135f0a6327bbe2aa023c584c5c71bfd20401a5e719640daada`。逐文件生成口径与字节/SHA 清单见 [`r1h_small_hash_manifest_20260920.json`](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/run_20260920T154556.093635044Z/r1h_small_hash_manifest_20260920.json)，SHA `0a2af1b58827eabd41f1e38bdc5e01bc73df8f28cbf69e4573f51043392973b1`；该小清单列出22个 hardware `.raw` 与16个 phase worker JSONL，按相对路径排序，`low_load_cpu1.jsonl`单列未纳入。21个专属 PID 的 native 只读清场证据见 [`r1h_cleanup_readonly_20260920T161002Z.json`](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/run_20260920T154556.093635044Z/r1h_cleanup_readonly_20260920T161002Z.json)，SHA `8a1ae0aec4095db557c84f3773a4df49068d84e6830be0316f29960c49c7a9b6`，检查时间 `2026-09-20T16:10:02.764589740Z`，`21/21 absent`。唯一 V5 ledger SHA `06d8dd9040cdbb306f79337eea80f5f09316b7dc8f04c3d9fe419ad3ac261594`，累计 `3327.407495518 s`。

### 历史维护建议（R1i 已执行，结果未解决）

原建议已在 R1i 中实际执行为 `Auto→2666 MT/s` 对照，但 node1 路径仍未稳定，不能称修复。保护边界仍是：不改电压、Enforce POR、热保护、刷新/纠错；外接小风扇是用户独立加装且直吹第二路 DIMM，不对应 BMC FAN2/3/5/6，不能用 BMC 转速判断其风量。

## R1d-B 历史结论

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
