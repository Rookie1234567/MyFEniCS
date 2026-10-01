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

机器记录见[Task041 V8 record](records/task041_v8_formal_5nm_2nm.json)。
