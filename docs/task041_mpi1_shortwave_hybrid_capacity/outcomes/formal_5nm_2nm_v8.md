# Task041 V8：5 nm 正式 consumer 终态与 2 nm 后续

5 nm cell-condensed 路线先消去单元内部自由度，再恢复完整场并检查原方程；内部目标 `5e-13` 最多追加两次同因子修正，原物理残差门不变。

## 最新正式运行：5 nm A6 consumer 已完成（2026-10-03）

| 项目 | 实际结果 |
|---|---|
| 身份与范围 | unit `task041-v8-5nm-cellcond-a6-formal-20261001T053737Z.service`，Invocation `b00e1993f6a2429185553092fa3ba7e2`，运行源码 `5bfb813870182fda172f658c8f276f58318844a5`；public runroot `results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8_cell_condensed/task041_5nm_p6h4_m480_mpi8_cell_condensed__hybrid_iterative__mpi8__M480/20261001T055115.915457Z`。W、5 nm、p6/h4、M480、MPI8×1，实际 `cell_condensed` 与 `task041_opt_in_sum_factorized_physical_volume`；target `5e-13`、最多2次修正。正式响应1920项完成，QEP复用。 |
| 数值与物理 | consumer `TASK041_CONSUMER_PASS`；完整求解、恢复和物理门通过。五项真实残差 global/bottom/top/modal/reported 分别为 `4.778595132175164e-11 / 6.21753923942821e-11 / 4.4271638517096704e-11 / 6.700061128878644e-13 / 4.778282085648332e-11`，上限均为 `5e-9`。`R/T/A/A_volume = 0.7331842733875563 / 0.00022009869572797534 / 0.2665956279167157 / 0.2665962726229846`；能量闭合差 `6.447062688152982e-7`。 |
| Exact数值对照 | 使用原有 comparator、以两个 public runroot 为输入的修正版 v2：`results/task041_v8_5nm_cellcond_a6_formal_run_20261001T053737Z/exact_comparison_offline_v2.json`，SHA-256 `e10d839252f066835c87da9346fd83f7ed5789b35694e7357a6dc873ca5ced42`。身份、R/T/A/A_volume、E/H、canonical场、600个外部衍射通道和法向通量的数值检查均通过；R/T/A/A_volume最大绝对差 `6.533662499919046e-13`（限 `1e-8`），E/H最大相对差约 `2.296e-11`（限 `1e-6`），canonical最大相对差约 `4.014e-10`（限 `1e-5`），法向通量相对差 `2.096e-12`（限 `1e-4`）。比较器总 `pass=false` 是因为旧exact producer没有可测的 `exact_raw_phase_measured`，所以exact资源/完整workflow资源对照仍不完整；这不否定本次consumer自身的数值和资源门。首次v1错误地把 `consumer/` 子目录当public root，结果保留；v2才是按既有接口正确执行的比较。 |
| 资源与交换观察 | authority峰 `43,966,554,112 B`，process-tree RSS峰 `43,415,531,520 B`，专属cgroup `memory.peak=43,975,204,864 B`（历史峰计数器）；均低于原53,221,163,008 B cap，warning `47,899,046,707 B`，reserve门通过。job/cgroup swap峰为0。global swap仅按V8观察：baseline `5,998,125,056 B`，运行中峰 `8,589,930,496 B`，结束 `2,591,805,440 B`；pswpin/pswpout分别增加 `1,481,020 / 2,781,714` 页，不归因于本job，也不作失败门。进程组已清场。 |
| 终态与耗时 | finalizer `service_complete`、exit 0、10项检查全通过；Invocation与账本条目一致且恰一次。public-to-finalizer wall `202,124.563261555 s`（`56.146 h`），24 h目标未达到且未强杀。相比早先同配置边界的52.590 h服务wall，本场约慢6.76%；此前两条固定RHS上A6约9.6%收益不代表完整consumer加速。 |
| 保留证据 | outer summary SHA-256 `14d5a069acce5be228097872d2ee28390ce1f739575ed296bc7d61bfb7c6ef27`；finalizer summary SHA-256 `5318e54f05a48c64647c1db3dda780a8e9b693f59384f1f7bf622f5ff811cbf4`。复用QEP packet manifest `results/task041_5nm_mpi8_fresh_selected_packet_b01a5932_r1/manifest.json`，SHA-256 `306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f`，producer source `b01a5932e4dfaf895e81e0424e0dd88c276fb0d3`；最终恢复包 manifest SHA-256 `31be97e466f9934bf63e664a5b38222991c716aa3474d030c14f24ed6e84a25c`。未重算大数组。V5 ledger `results/task041_review_v5_cpu_numa_condensed_speed/r0_r1_20260920/r1_load_ledger_20260920.json` 对该 run ID 恰有一条 `202124.563261555 s` 记录；ledger累计 `441571.6888938089 s`，本次不再收费。 |

9月28日的较早S1执行与当前运行身份不同，保留其worker exit0/public exit3及文档HEAD差异历史，不用当前成功覆盖旧记录。

## 早期S1尝试（2026-09-28）：数值通过、public身份合同失败

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

## A6：真实尺寸 action 等价与计时观察（2026-10-01）

A6把当前三维体积方程作用到一个输入场上；融合实现合并了其中的局部计算。本次在5 nm p6布局/MPI8上比较原实现与融合实现，但输入是确定性合成向量，不是由固定RHS求出的响应，因此结果只证明这两种 action 在该输入上的等价与耗时，不构成全场性能资格。

| 侧/动作 | 原实现→融合实现（秒/次，max-rank均值） | 相对节省 | 最大相对差 | 门 |
|---|---:|---:|---:|---|
| bottom / 体积项 | 0.990358→0.396308 | 59.98% | 2.002×10⁻¹⁵ | 1×10⁻¹⁰，通过 |
| bottom / 体积项+一次原DtN | 1.000771→0.417720 | 58.26% | 2.002×10⁻¹⁵ | 1×10⁻¹⁰，通过 |
| top / 体积项 | 0.996565→0.626359 | 37.15% | 7.851×10⁻¹⁵ | 1×10⁻¹⁰，通过 |
| top / 体积项+一次原DtN | 1.008539→0.641315 | 36.41% | 7.851×10⁻¹⁵ | 1×10⁻¹⁰，通过 |

计数为56次 action：48次ABBA计时调用（两侧×两种动作×四段、每段3次）和8次单独warmup。每侧先后构造并销毁；bottom/top side-system setup分别117.643/140.663秒，原/融合 action setup分别为5.598/4.749秒及6.174/5.305秒。完整监督phase wall为325.678秒；性能标记`not_isolated`，不能外推为全响应或完整5 nm consumer加速。

运行身份：源码`92d70a603856bd866ba469444512dd79acb23ef0`，unit `task041-v8-a6-paired-action-r1-20261001T005620Z.service`，Invocation `4d5edf5a63024cac8ae486571663fccd`；r1 config SHA-256 `8a43c699f4c9e05ccc19c3cbce59f5a4fbeb84253fd3f66d13ce59fbe506bddd`。r1 public runroot为`results/task041_review_v8_a6_paired_action/run_20261001T005620Z_r1`。首次尝试因MPI rank未落在node0 membind而在FE/action构造前退出（rc1、phase wall 2.393秒）；保留原记录，修正MPI/numactl顺序后的r1所有rank均绑定CPU1–8/node0并正常退出。

r1全程authority/process-tree峰为17,303,310,336 B，专属cgroup `memory.peak`为15,263,993,856 B；同一侧的原/融合action同时驻留，所以该峰值不是任一单独backend的内存峰。kernel payload为rank-local参考数组7,470,800 B、workspace 412,064 B和cell metadata约288,476–288,544 B；这些是payload计数，不是RSS。job/cgroup swap为0，global swap/pswp增量为0；这些资源读数不改变本次非正式性能范围。

紧凑终态compact为`results/task041_review_v8_a6_paired_action/run_20261001T005620Z_r1/r1_terminal_compact.json`（SHA-256 `cbecf6983a05e0b584d23d20c5a7d2f3f870768a1a02b0aa509d76cad1e4fe21`）。V5既有ledger只追加了首次配置失败phase与r1成功phase，各一次，共328.070209秒；ABI、dispatch和内部action计时未重复收费。ledger从59条增至61条，累计236,114.941209秒；完整身份、首次失败和备份哈希见机器记录。

### A6b：冻结真实 RHS 的有限响应对照（2026-10-01）

本次从既有八项 RHS manifest 选 bottom ordinal 0/formal column 207 与 top ordinal 4/column 310；每侧按 original→fused→fused→original 顺序，在同一布局、同一 `cell_condensed` p4 factor 和零初值下完成四个完整响应。它验证两个固定 RHS 的原/融合 A6 响应与重复一致性，不是全部八项诊断、更不是完整 consumer 或正式性能资格。

| 侧/ordinal/column | 动作序号 | packet max-rank wall（秒） | 侧区内层KSP迭代 | 本响应修正数 | p4回代数 |
|---|---|---:|---:|---:|---:|
| bottom / 0 / 207 | A1 original | 129.761845 | 17 | 1 | 35 |
| bottom / 0 / 207 | B1 fused | 119.016090 | 17 | 1 | 35 |
| bottom / 0 / 207 | B2 fused | 119.222392 | 17 | 1 | 35 |
| bottom / 0 / 207 | A2 original | 134.307245 | 17 | 2 | 36 |
| top / 4 / 310 | A1 original | 146.123131 | 17 | 16 | 50 |
| top / 4 / 310 | B1 fused | 134.487071 | 17 | 17 | 51 |
| top / 4 / 310 | B2 fused | 132.864741 | 17 | 16 | 50 |
| top / 4 / 310 | A2 original | 149.679956 | 17 | 16 | 50 |

按 packet 中的 `call_wall_max_rank_seconds`，bottom 原/融合均值为 `132.034545→119.119241 s`（低 `9.782%`），top 为 `147.901544→133.675906 s`（低 `9.618%`）。rank0 closeout 均值另为 bottom `132.029664→119.114478 s`、top `147.895860→133.670318 s`；两种计时口径分别保留。每条侧区响应的内层 KSP 均迭代17次；本场没有完整 Hybrid outer 求解。8个响应共70次p4修正与342次回代；每次 p4 inverse 实际最多修正1次，目标为 `5e-13`，原 physical/augmented 残差门 `1e-10` 均通过。A6/Q/H6 是各响应内按原定义累积的操作计时，区间存在包含/重叠，不能叠加成响应wall。

每侧四项原/融合及重复比较均通过：`max e_x=2.7499208775347377e-14`、`max e_A=7.785694432043024e-14`，各自限值 `1e-8`；bottom/top最大 side relative residual 分别为 `0.008369286568895733 / 0.0092028481537098`，限值 `1e-2`。这些是两个固定 RHS 的 A6 等价结果，不改变 full consumer 的资格状态。

监督 workflow wall 为 `3319.941774289 s`；authority/process-tree共同峰 `38,147,805,184 B`，cgroup历史 `memory.peak=35,880,628,224 B`，cap/warning/reserve 为 `53,221,163,008 / 47,899,046,707 / 412,316,860,416 B`，资源门通过。原/融合 action 同时驻留，因此该峰不是单一 backend 峰。job/cgroup swap为0；global swap原始增量字段是非负增量钳位值 `0 B`，baseline `5,999,333,376 B`、final `5,999,235,072 B` 的派生有符号差为 `-98,304 B`；global `pswpin` 增 `25` 页、`pswpout` 增 `0` 页。global值为整机观察，不归因于本作业。运行标记 `not_isolated`，不能据此宣称无人竞争性能提升。

worker与supervision均 `rc=0`、无受控终止、专属进程组清场；user journal记录自然结束，transient unit随后卸载。终态依据为worker/supervision及journal，不能单看卸载后的默认unit状态。record与原 compact 入口见 [V8 machine record](records/task041_v8_formal_5nm_2nm.json) 及 `results/task041_review_v8_a6_paired_action/run_20261001T030232Z_real_rhs_abba/a6_real_rhs_abba_closeout.json`（SHA-256 `f4f8800b3b5924466580ae6ee6bc0f694abb804835a823bc3edacdb4af3b4f60`）；8个packet manifest路径与hash、逐响应计时/修正数和唯一账本追加均在machine record中。此诊断不构成全八项、全场或正式性能资格。

机器记录见[Task041 V8 record](records/task041_v8_formal_5nm_2nm.json)。
