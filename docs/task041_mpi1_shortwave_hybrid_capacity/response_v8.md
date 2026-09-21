# Task041 Response V8：Review V5 R1i 2666 复测与历史终态

本报告保留 D3a 的自然终止证据、R0/R1d/R1e/R1f/R1g/R1h 历史记录，并登记最新一次 R1i 2666 复测。两批 driver `rc=0` 只表示诊断批次正常收尾；CPU1 仍未资格化，不能把异常归为硬件损坏、确定的 DRAM 热限流或核心降频。R2–R6、R3 p4 草稿测试和新 PDE/MPI/QEP 均 `not_run`。

## R1i：Auto→2666 MT/s 未解决吞吐异常

R1i 使用 post-boot `fb33e6f4-078c-4638-becf-e8ea71f8764e`、2 TiB 级内存、16×128 GB DIMM，DMI configured speed=`2666 MT/s`；用户确认 BIOS Memory Frequency 从 `Auto` 改为 `2666`，其它设置未改。两批沿用已审 driver/worker、8×1、3×60 s、原资源/温度/身份/清场门，未运行 PDE 或新负载。 本批运行 repo HEAD 为 `4de7bc82a964ec9de03fc3689595efeb21e45678`，与当前文档工作树及其后续文档提交身份分开记录。

| batch/path | 三窗吞吐（GB/s） | 结论 |
|---|---:|---|
| local socket0 cores1–8 → node0 | `35.63788506479269 / 35.664033252580786 / 35.6967308849817` | 稳定；不据此给 CPU0 新硬件资格结论 |
| local socket1 cores25–32 → node1 | `35.648371306083156 / 31.66995975917892 / 11.024863223982754` | node1 路径崩落；CPU1 仍未准入 |
| cross socket0 cores1–8 → node1 | `23.562553384022838 / 22.956933903624012 / 13.10402684910857` | node1 路径再次崩落 |
| cross socket1 cores25–32 → node0 | `23.408224743881927 / 22.924688775860275 / 21.682633764800535` | 约 `7.37%` 下降，不写成零退化 |

两批均 rc0、worker 三窗完成并清场；local 的精确父侧 monotonic wall 未测，按 `816.976233636 s` 保守上界计账；cross 父侧 wall 为 `629.805876166 s`。CPU 活跃频率约3.6 GHz、CoreThr=0；这些是 gate/排除信息，不是性能资格通过。唯一账本累计 `4774.189605320 s`，after SHA=`e0ce6a02033acd7cd0971b73e4aee5554fbbf2f3d24c486a6794c4da20c010ef`。

新鲜 DIMM 事件是 `@150` 中的 DIMM `TEMPLO/TEMPMID` sticky 字段，不等同外部 MEMHOT `e24`：`ae:0c.6` 的 sample3→4 为 `66→69°C` 且 bit26 `0→1`，sample7→8 为 `77→78°C` 且 bit27 `0→1`；两对分别跨 window1→2、window2→3，均为时间括号而非同刻证明。cross raw 确有 load-time `@140/@144/e24`（`socket1_sample10.raw` 的 `@140=0000200f`，`@144=00000000`，e24=0）；local raw 没有这些 load-time 字段，不能把两批统一写成缺失或统一写成已测。cross `P1-DIMMC1` 的 TEMPLO sample4→5 以 PCI `@150` 的 `65→67°C` 作为时间括号，异步 BMC 列表为 `65→66°C`（差 `+1°C`）；samples1–10 未见新的 TEMPMID bit27，但后续 after_load 已置位，触发时间和温度未知。这里的 TEMPLO/TEMPMID 表示较低/中间温度阈值被越过的事件；sticky 只表示两次读取之间曾发生过置位，不表示此刻仍在限速。

BMC `mc info` rc0、Firmware `1.71`，风扇 GET 原始返回 `01`，按已给 primary sources 可记为 BMC Full mode；这不证明每个物理风扇通道达到额定全速，也不映射用户独立外接风扇。机箱型号未知、侧板打开、外接风扇保持直吹 node1 DIMM；不再要求调风扇。用户历史 `90°C` 是自述，不是本轮 raw。Intel S2600WF TPS §12.3.4.2 仅作为同代机制参考（TSOD fixed/dynamic thermal offset），不是 X11DAi-N 的具体公式；`@140` 的 `0xf` 不换算成已证实 `+15°C`，不声称实测93°C，未改90°C/offset/保护。

紧凑入口：[R1i tracked compact](outcomes/records/task041_r1i_2666_retest_20260921.json)，同内容 ignored 原件为 [compact v3](../../results/task041_review_v5_cpu_numa_condensed_speed/r1i_2666_retest_20260921/r1i_2666_two_batch_compact_v3_20260921.json)，两者 SHA `4e7a3d0e21bfe53da457010493a22c71140b7cf734bfdf4b1034f88bc2cacbc6`；v2 最终 SHA `ceb19601a337b0d40b6eedd0f260faed018c0b5459904aad24147a11a754bf57`，v1/raw/history 保留；43 raw+43 BMC 排序 hash 输出 SHA `b4fbd2eb6197421e382d39d9e5ce97a6878e3f6543c558adf9113c3244516ab1`。

本轮只读阈值边界：评估的是控制器 `TEMP_MID 93→95°C`，不是把显示温度设为95°C，也没有证明 `@140` 的 `0xf` 等于 `+15°C`。`@120` 的 bits15:8 是可写字段，但 Micron 的95°C扩展TC与>85°C时2×刷新要求不自动证明系统安全；实际温差、响应超调、全系统清场和可靠回退尚未资格化，因此未写阈值、未改补偿/刷新/HI保护、未启动负载，原80°C观察线保持。

## Review V5 历史状态：R1h 已完成（已由 R1i 更新），CPU1 仍未准入

R1h 是同一固定 worker 的跨 NUMA 诊断，不是物理模型计算：CPU socket0 的 OS CPU1–8 将双缓冲 first-touch 到 memory node1，CPU socket1 的 OS CPU25–32 将其 first-touch 到 memory node0；两阶段各 8 个单线程 worker、3×60 s。每个阶段开始和末段均观察到 `8/8` 个 buffer 位于预期的远端 node。固定 driver SHA 为 `f81d917bd462e1a5028a8bb8c3f4ca3aaad4122a9f2adaec8a6990a616099bc4`，worker SHA 为 `7ce2dd8ff6f71cf4e9b9c13a156e1f0f0b15b38af010ac0b2b04881ec3ce0ad9`，运行 source 为 `881bb9773a79793d8edd7fe525ad57a4c0d9a494`。

同一 R1h 目录先前直接执行 `664` driver 的 `rc=126` 启动级负结果予以保留；仅用显式 `/bin/bash` 修正启动方式，未将其算作第二轮压力负载或第二个性能负结果。

| R1h phase | 三窗吞吐（GB/s） | iterations sum | 结论 |
|---|---:|---:|---|
| socket0 / OS CPU1–8 → memory node1 | `22.648688106036644 / 21.977584096329075 / 7.395682818558859` | `20254 / 19649 / 6616` | 访问 node1 的路径吞吐崩落约 `67.35%`；CPU1 整体仍未准入 |
| socket1 / OS CPU25–32 → memory node0 | `19.789193732901627 / 19.759391333017003 / 18.843317623093906` | `17697 / 17665 / 16847` | 第三窗较首窗约降 `4.78%`；不写成零退化 |

R1h 共 22 个硬件 sample、110 个 final-read（每条新 PCI/MSR 读取 `rc=0`），44 个 MSR 输出文件各 48 行且值为 0；所有 16 个 worker、driver 和采样进程均已按启动 PID 清场。358 个资源 sample 的 `MemAvailable` 最低为 `2114795454464 B`；swap 为 `299008 B`，`pswpin=0`、`pswpout=73`，本批新增 global swap delta 为 0。16 个 worker 相邻样本的 minor/major fault 与 `stime` delta 均为 0；CPU0/CPU1 最大 `wait/(run+wait)` 分别为 `0.0009933352281917688`/`0.0008195138298330328`；共享 cgroup 的 `nr_throttled/throttled_usec/high/max/oom/oom_kill` 均为 0。global NUMA 计数仍是主机级，未归属于本批。

活跃 `Busy>=95%` 样本中，socket0/1 的平均 `Bzy_MHz` 分别为 `3600.3309404163674`/`3599.549568965517`，CoreThr 均为 0；这削弱“核心降到低频”的解释，但不排除内存控制器、固件或 DIMM 链路路径。BMC 温度是窗口括号而非逐帧同刻，且只涉及 `P1-DIMMC1` 与 `P2-DIMME1` 两个探头，不代表整组 DIMM 的 min/max：CPU0→node1 阶段约为 `P1-DIMMC1 47–54°C / P2-DIMME1 54–78°C`，CPU1→node0 阶段约为 `P1-DIMMC1 57–77°C / P2-DIMME1 76–77°C`；第一阶段第三窗出现 P2-DIMME1 78°C 平台与吞吐下降的时间邻近只构成相关证据，80°C 是本次观察停止线，不是内部热控阈值。R1h 所有 e24 读取为 `0`，只能削弱持续外部 MEMHOT，不能排除采样间瞬态或其他热控路径；sticky 字段不当作当前限速。

证据入口为 [R1h compact](outcomes/records/task041_v5_cpu_numa.json) 与 [R1h raw summary](../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/r1h_result_summary_20260920.json)。runroot 为 `results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/run_20260920T154556.093635044Z`；launch metadata SHA `62496750a7ac9d6bce344bce279e9f31b7dde65e4379aa320ca0aa7825e2945e`，driver log SHA `a7e0a45ca321b65b27a04c75f804a8352faf167bd577da908268c15dd721e977`，hardware aggregate SHA `03c00115b46de257495388999e4bbe7cc605f1bbfca56a66aa62bcdacfb8be21`，worker aggregate SHA `bc56bcc7fec6ae135f0a6327bbe2aa023c584c5c71bfd20401a5e719640daada`。逐文件、字节数和 SHA 的小清单为 [`r1h_small_hash_manifest_20260920.json`](../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/run_20260920T154556.093635044Z/r1h_small_hash_manifest_20260920.json)，SHA `0a2af1b58827eabd41f1e38bdc5e01bc73df8f28cbf69e4573f51043392973b1`；它明确列出22个 hardware `.raw` 和16个 phase worker JSONL，按相对路径排序生成，`low_load_cpu1.jsonl`单列未纳入。21个专属 PID 的 native 只读 `/proc` 清场证据为 [`r1h_cleanup_readonly_20260920T161002Z.json`](../../results/task041_review_v5_cpu_numa_condensed_speed/r1h_sched_mba_20260920/run_20260920T154556.093635044Z/r1h_cleanup_readonly_20260920T161002Z.json)，SHA `8a1ae0aec4095db557c84f3773a4df49068d84e6830be0316f29960c49c7a9b6`，检查时间 `2026-09-20T16:10:02.764589740Z`，结果 `21/21 absent`。父侧 `CLOCK_MONOTONIC` wall 为 `629.724913916 s`，本批已按唯一 V5 ledger 追加一次；ledger SHA `06d8dd9040cdbb306f79337eea80f5f09316b7dc8f04c3d9fe419ad3ac261594`、累计 `3327.407495518 s`。

因此 R1h 历史状态为 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_ANOMALY_REPRODUCED_NO_UNIQUE_CAUSE`，R2 仍 blocked。没有完整 process-tree/cgroup RSS 峰值，也没有新的硬件修复；R1i 已执行 `Auto→2666 MT/s` 对照但 node1 路径仍未稳定，不能称修复。历史建议的边界仍有效：不改电压、Enforce POR、热保护、刷新/纠错、风扇或固件；93→95 仅作只读评估，未写阈值、未启动新负载。

## Review V5 历史状态：R0 已完成，R1d-B 复现负项

R1d-B 使用固定 driver SHA `37bea39b72656f2c8e0ce3bb293bbfc8ff41d7a17fa28fd1fc0cedf90976a584`，在无检测到新 heavy 的独占窗口中完成低负载、socket0/node0 CPU1–8 和 socket1/node1 CPU25–32 三个 60 秒窗口。两侧启动与 near-end NUMA 观察均为 `8/8` local；16 个 worker 和 turbostat 的 600 个采样帧均自然退出，父侧 `CLOCK_MONOTONIC` wall 为 `630.795106023 s`，driver rc0。

| R1d-B | 三窗总吞吐（GB/s） | iterations sum | 结论 |
|---|---:|---:|---|
| CPU0/socket0/node0 | `32.173939890 / 32.183022717 / 32.190473984` | `28771 / 28774 / 28779` | 稳定约 `32.18` |
| CPU1/socket1/node1 | `33.263204952 / 28.338248830 / 9.265976385` | `29745 / 25343 / 8283` | 第三窗相对首窗下降约 `72.14%`，`CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_COLLAPSE` |

活跃 turbostat 样本保持约 `3.6 GHz`，CoreThr=0；BMC DIMM 峰为 socket0 `64°C`、socket1 `78°C`（80°C 观察线，状态 ok）。因此不能称核心降频已修复，也不能判定硬件损坏或 DRAM 热限流。R2 继续 blocked；精确 raw、清场和唯一 ledger 追加见 [R1d-B compact](outcomes/cpu_numa_condensed_speed_v5.md) 与 [`task041_v5_cpu_numa.json`](outcomes/records/task041_v5_cpu_numa.json)。

## 结论先行

这是钨（W）、2nm、p6/h1.5、M1200、MPI8×1 的单次 D1e 运行。Schur 是供外层迭代使用的模态耦合预条件矩阵；本次 consumer 在正式全场 Schur 之前，用两侧合成模态 Schur 的重复样本检查一致性。该重复一致性门失败，consumer 以 `IMPLEMENTATION_FAILURE` 结束；这不是 OOM、超时、外部 kill，也不是投影误差结论。

失败不能归因到 top 单侧：`build_hybrid_action_modal_schur` 先由 bottom+top 形成 `sampled_first`，再由 bottom+top 形成 `sampled_second`。因此准确分类是“**两侧合成模态 Schur 样本重复一致性失败，侧别根因未定位**”；`top_construction_cleanup` 只是退出清理阶段 marker，不是 top 根因定位。

截至终态，producer 的 QEP packet 已保存，32 个 modal shard 保留；consumer 已完成 40 行小 RHS 记录（8 probe + 32 modal，bottom/top 各 16），但正式 Schur 为 `0/4800`，outer FGMRES 为 `not_started`/0 条 outer response，没有完整场、R/T/A 或 official qualification。`reason=2` 与 `true residual<=1e-2` 只说明这些小样本的内层求解达到原目标，不等于重复一致性或最终全局物理通过。

## 身份、终态与证据

| 项目 | 实际值 |
|---|---|
| canonical source / branch | `/home/fenics/Projects/MyFEniCS`；`codex/20260902-task41-mpi1-shortwave-hybrid-capacity`；运行 source `bde0686891af10bb489e4b1cb14500791cb50351` |
| report worktree | `/tmp/task041-d3b-terminal-review-20260920`，本报告不改变运行 checkout |
| report worktree HEAD | `83d84899c401df38dfe8ebc0ea1c56f0914887df`；running source 仍为 `bde0686891af10bb489e4b1cb14500791cb50351` |
| unit / invocation | `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` / `1cf5e34338754dbfa80df487b322c72c` |
| historical MainPID | `571560`；终态已退出 |
| runroot | [`20260918T095546.139183Z`](../../results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/) |
| service root | [`d1e_2nm_p6h1p5_m1200_mpi8_supervision`](../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_2nm_p6h1p5_m1200_mpi8_supervision/) |
| CPU / math threads | OS CPU1–8；MPI ranks 0–7；每 rank 数学线程 1；受保护 CPU23 项目未触碰 |
| report status | `terminal_controlled_negative`；D3a 文档阶段，不重启、不发 signal、不改源码 |

退出链为：producer wall `29504.116038094042 s`、rc0、进程组清理；consumer wall `135717.4772190291 s`、rc1、进程组清理；public total `165222.44361121487 s`。systemd 主进程于 `2026-09-20T07:49:30.066531Z`（CST `2026-09-20T15:49:30.066531+08:00`）以 `SERVICE_RESULT=exit-code`、`EXIT_STATUS=3` 退出；systemd 对代码3的展示别名是 `NOTIMPLEMENTED`，不是算法原因。控制进程于 `07:49:33.807150Z` 退出，failed record 为 `07:49:33.807349Z`。public `run_summary.exit_status=1` 与 service phase `returncode=3` 分别保留；finalizer charged wall 为 `165228.433265082 s`。

finalizer 的准确状态是 `status=failed`、`result=service_boundary_failure`：worker process group gone、post-hash、artifact hash、ledger 写入和专属树清理均为 true，但 `public_result_completed=false`、`service_terminal_normal=false`，不能称 finalizer PASS。原始 consumer 分类仍为 `IMPLEMENTATION_FAILURE`，不能改写为 OOM、resource stop 或 numerical projection failure。

证据入口与 hash 见 [`task041_d3a_terminal_20260920.json`](outcomes/records/task041_d3a_terminal_20260920.json)。主要终态摘要如下：

| 文件 | SHA256 |
|---|---|
| `run_summary.json` | `59ba533551d176feee6198308c3a8814e3ef2db8be051257c829e4ed11e3e0a6` |
| `consumer/consumer_summary.json` | `df2aff13add4a5cf8ddca9b720f0d980965165b9c25e9822607c258e0f9d8187` |
| `supervisor_summary.json` | `65edfd58060e49216b074bd59e27fe15b90a564288defcda50ac8abf400c1a6d` |
| service `summary.json` | `df4620f0fa8018e2a1d05645e1ea6b2c23d34647ee31adef218893863ca35f72` |
| `service_parent_summary.json` | `ee0dad15c23c18fe60c1814c82e66e33452ad534f40b1f887931d687a9c65c81` |
| finalizer summary | `d5ec69c414c93c52b748cdff12a96f9c824760135001bcf7bb44c4f4dbde95af` |
| 40-row RHS audit | `dd06b01eac2928ff0814bef9bd3951ac256d776366ed7fd177392374e0175cde` |

## 失败数值与样本范围

原始错误为：

```text
Early sampled modal repeat Gate failed: absolute=2.637750e-04,
reference_norm=5.957499e+00, relative=4.427612e-05,
max_column=1.169058e-04, finite=True, limit=1.000000e-10
```

上面数值按原 stdout 的 `.6e` 打印精度记录；更高精度原始值不可得，不能从显示值伪造 full precision。

其中 `max_column` 的字段语义是 `max_column_relative_error`，不是绝对差；触发位置为 `hybrid_fem_modal_block_ldu.py:542`，调用链经过 modal Schur 构造，退出阶段 marker 为 `top_construction_cleanup`。由于 first/second 两个合成样本都包含 bottom 与 top，不能从此记录选择失败侧。

| side | modal rows | iterations sum | elapsed sum (s) | true residual max | reason |
|---|---:|---:|---:|---:|---|
| bottom | 16 | 352 | `36004.124497986864` | `0.009981656767193032` | 全部 2 |
| top | 16 | 394 | `40527.54153031926` | `0.009939510152843832` | 全部 2 |

40 行由 8 probe + 32 modal 组成；bottom/top 各 16 modal 行。32 个 modal 行均为 `reason=2`，且 `explicit_true_target_reached=true`。因此小 RHS 内层 residual 门满足 `<=0.01`，但重复样本的 `relative=4.427612e-05` 大于 `1e-10`；这两个门不能互相替代。

正式进度仍是：formal Schur `0/4800`，outer FGMRES `not_started`、outer response `0`（分母不适用），full field/RTA `not_run`。没有把 32 个重复样本当成 4800 项正式进度，也没有把失败写成投影误差失败。

小样本总耗时是嵌套 modal row 成本，不是 service critical path。终态 32 条样本的固定算术为 `(36004.124497986864/16 + 40527.54153031926/16) × 2400 / 86400 = 132.86747574358702 days`；它不能给 ETA。D2a 旧 21 条样本的 `133.57896112787233 days` 只属于旧 bottom13/top8 窗口；旧 8-probe 的约 `115.17 days` 也单列，三者都不代表完整 consumer。`batch_size=32` 是逐批限制常驻内存，不是 32 个样本并行。

## 资源与终态边界

权威 service 全树 summary 的 `peak_process_tree_rss_bytes` 为 `642483171328 B`；较窄 public 树曾记录 `642449637376 B`，两者不可混称。专属 cgroup peak 为 `647904940032 B`；终态 cgroup 已清理，不把 D2a 的 cgroup current 快照写作当前值。PSS/USS 只有稀疏字段，不能替代 RSS。完整采样最大间隔为 `11.7317484519 s`，故短于采样间隔的局部峰不能称完整测得峰值。

global swap 基线为 `8192 B`，终态新增 used `290816 B`、`pswpout` 增加 71 页、`pswpin` 增加 0；job/cgroup swap 仍为 0。该变化需披露，但没有证据表明本 job 因 swap 触发停止，终止原因仍是 implementation failure。资源合同为 warning `1539316278886 B`、hard RSS `1759218604442 B`、runtime reserve `412316860416 B`；service summary 的 `minimum_host_memavailable_bytes=836790292480 B`，全树 sample_count 为 `407853`；PSS/USS 的完整 smaps 样本仅 `5480`，其余按稀疏未测处理。runtime reserve、identity 和清理证据按 service authority 保留；本次没有 RTA 或完整场可供后处理。

独立 2nm ledger 为 [`task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json`](../../results/task041_side_balh_component_audit/d1c_preparation_20260917_8d47747d/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json)，SHA `f01a0027b5303d7dae2ac0be542eb6273160c1ba150596907d55e09879cd2de9`。D1e 这一条 finalizer 只收费一次：before `77232.864925164 s`，charge `165228.433265082 s`，after `242461.29819024602 s`；旧 D1c/D1d records 保留，旧 V2 ledger 不改。

## Producer packet 与以后复用条件

producer 已写出 selected mode packet：32 个 shard、共 33 个文件、`4842723531 B`；manifest SHA 为 `7ef2ecc5587f79a123e44cacfe347356d13b36336948ade1672787c6430163d2`，此前已完成一次流式文件字节/SHA 核验。`mode_prep_summary` 为 `TASK041_MODE_PREP_PACKET_READY`，`producer_scope_released=true`，且 `qep_workspace_persisted=false`：保存的是 consumer 所需 selected packet，不是全部 QEP 中间 workspace。

终态后 `supervisor_summary.json` 已存在并有上表 SHA。随后一次只读 `validate_balh_producer_packet(..., require_public_supervisor_summary=True)` 返回 `rc=0/pass`、`producer_resource_qualified=true`，并核对原 2nm dat、完整 consumer source `bde0686891af10bb489e4b1cb14500791cb50351`、manifest 小文件和 packet 目录统计；结果日志为 [`d3a_producer_packet_validator_20260920.log`](../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_2nm_p6h1p5_m1200_mpi8_supervision/d3a_producer_packet_validator_20260920.log)，SHA `991a49001396b95ad7317148f56c3b05a815f2ff3963c995d6335768e29674b2`。`1.0323800740297884 s` 只是在已导入的同一 Python 进程内的 `load_and_resolve + validator` wall，imports/startup excluded；父侧完整 command wall `not_measured`。stderr 的 7 行 `Authorization required...` 原样保留，不是 validator 失败；本调用没有 fresh MPI8 ABI 或 32-shard hash 重验。这个结果只闭合 producer/public metadata qualification，不是 consumer-only restart 或全量 shard/ABI qualification。

未来启动沿用这次已通过的 metadata validator 入口；实际消费时仍需核对 32 shards、ABI、source/input/physical/resolved identity 与输入兼容性。内存中的 p4 factor、未完成 Schur 和 native workspace 没有 checkpoint，不能从 packet 继续恢复；受控结束也不等于任意强杀都可无条件续算。

已观察到的清理路径释放 owned packet/vector 引用，但未见删除 producer packet 的路径；因此 producer 证据应保留。新 consumer 若要复用，需在另一次明确授权的启动前以终态摘要和现有 validator 重新核验，不修改本次原始 run。

## 历史与后续边界

5nm BAL_H 曾有约 53 h 的组件/候选证据，但 public supervisor/resource 证据不完整，不能升级为完整容量资格；C2 common-layout 的约 26.6% 只属于同进程组件诊断边界，也不是本次 2nm 全场速度依据。D1c 的 `outer_mpi_identity` 失败、D1d 入口修复后的 affine geometry 误判、8ad30732 对平移浮点抵消的修复，以及 bde06868 绑定 D1e，均保留历史链条。

本次没有启动近似 Schur、没有重跑 QEP/PDE、没有改变 M、精度、物理定义、阈值或资源合同。没有完整场，所以没有“后处理拒绝 R/T/A”；RTA 的状态是 `not_run`。D3a 只整理终态证据，待主控审核后才可能推送文档；不修改 canonical 运行 HEAD。
