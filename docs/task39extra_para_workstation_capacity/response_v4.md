# Task39extra 执行归档 V4：2 nm h1.5 实测内存运行快照

> 快照时间：2026-09-20 01:35:10 UTC。以下只归档小型身份、阶段 marker、末次资源样本和 guard 状态；没有扫描或复制数 GB 的 `resources.jsonl`，阶段峰值未从完整资源日志聚合。

## 当前结论

| 项目 | 当前事实 |
|---|---|
| 运行 | `20260918T035017.294454Z`，状态 `RUNNING` |
| source / input / physical | `41caf5141493ad6c5d6c518a64ee74fda8d7a7db` / `1f54c3429625eefcdc65e4ec7dec356a8475e4249fe179d1f2957381701fb76b` / `fb8d259274ea968deb243ab9fa2b5c360b74f19dd8ebcf606aeba643cb59b6ef` |
| 当前阶段 | `reference_numeric_preflight` marker 之后；按用户现场事实处于 p4/MUMPS numeric，尚无 `reference_numeric_complete` marker |
| symbolic / numeric | symbolic 完成快照记录 `symbolic_calls=1`、`INFOG(1)=0`、`INFOG(7)=4`、`INFOG(16)=1222577`、`RINFOG(1)=1100362818940466`；该快照的 `numeric_calls=0`、`solve_calls=0` 只表示当时 audit，当前 numeric 调用进行中、尚未返回 |
| outer / RTA | 尚未开始 / 未运行；没有 full true、R/T/A 或物理 Gate 结论 |
| 最新整树样本 | `RSS=477900079104 B`（约 477.900 GB 十进制），swap=0；global `pswpin=0`、`pswpout=2`，沿用基线 |
| 监督 | 原 1537.5 GB watchdog 仍在；另有独立 1300 GB measured-RSS guard，当前样本持续、未触发停止 |
| 监督资格 | 运行中，不能提前写成终态 `RESOURCE_PASS`；完整阶段峰值未聚合 |

紧凑证据见 [`2nm_h1p5_measured_running_snapshot_v1.json`](outcomes/records/2nm_h1p5_measured_running_snapshot_v1.json)。其中单独区分了 `guard_script_sha256` 与 guard `config.json` 的 `config_sha256`，以及数学库线程配置和实际 OS 线程数。

## 运行身份、材料和离散规模

本次材料身份是用户给定的 Si，密度 `2.33 g/cm^3`，`n=0.99880148307+0.000213688647i`，对应 `epsilon=0.9976043569199937+0.00042686507507764344i`；本记录不声称独立数据库验证。

| 量 | 数值 |
|---|---:|
| cells | 54332 |
| p6 rows | 35594790 |
| p4 rows | 10604228 |
| augmented p4 rows | 10608132 |
| augmented p4 NNZ | 4899800920 |
| modes / propagating | 3904 / 3902 |

A6 为 matrix-free、H6 为 partial assembly；显式 augmented A4 进入 MUMPS LU 路径。配置是 MPI1、数学库线程1；宿主进程角色为 root/MPI/worker 三个进程，worker 内观测到3个 OS 线程。worker 绑定 CPU23、root/监督绑定 CPU9，内存策略为 `preferred_node1`，允许节点 `[0,1]`。不据此推断无共享内存带宽或功耗竞争；邻项目未被改动。

ABI 为 complex128/PETSc `PetscInt=int64`/PORD query64，PETSc 3.19.6、MUMPS 5.5.1；唯一新 PETSc 映射及 SHA 记录在 compact。正式入口使用的 source/input/environment 身份没有改写。

## 阶段时间（相邻 marker；秒）

| 阶段 | measured span | 口径 |
|---|---:|---|
| H6 setup | 33988.685043355 | `h6_original_setup_started` → `h6_original_window_and_packed_action_complete` |
| fine physical setup | 13632.805344747 | `fine_physical_started` → `native_physical_started` |
| native physical setup | 2598.162078627 | `native_physical_started` → `owner_transfer_started` |
| p4 volume pattern/assembly | 105595.228423629 | `reference_volume_pattern` → `reference_volume_complete`，数值体装配 |
| p4 augmentation construction | 358.422948160 | `reference_volume_complete` → `reference_augmentation_complete` |
| MUMPS symbolic | 266.830387278 | `reference_symbolic_started` → `reference_symbolic_complete`，已完成 |
| numeric observation | 7620.283222800 | `reference_numeric_preflight` marker → 末次 run resource sample；不是精确 numeric wall |

workflow marker 到末次样本的累计时间为 `164642.508297824 s`。`stages.jsonl` 的 SHA256 为 `f6baa2db169fd07258a26095cf71149bf07f51ee9d50d3f1eaa28ab213429f81`，`run_manifest.json` 的 SHA256 为 `c2d05d59fdeaae5194cd635ec58fa79d8889a7c3d6183233a1e4e90257f28fe4`。

## 内存与资源边界

末次 run sample 的 inner profile 仍记录：launch cap `1153229508404 B`、symbolic factor estimate padded `1222578000000 B`、diagnostic predicted peak `2716819309312 B`、future workspace `48545448448 B`。预测峰明确只是诊断/规划量，不是 RSS 严格上界，也不能替代 numeric 实测。

独立 measured guard 的上限是 `1300000000000 B`（十进制 1300 GB），0.25 s 采样；本快照时样本数 `28833`、attachment peak `477900079104 B`、swap=0。guard 配置文件和脚本均保留在原目录；`config_sha256` 指配置文件，`guard_script_sha256` 指配置内记录的 guard.py 哈希。该 guard 只覆盖接管后的 attachment，不追溯整个 run 的历史峰。原始完整资源日志路径保留在 compact，但没有在本归档中复制或全量归并。

## 性能交接：已测、推导、预测与未知

5 nm 历史实测 run `20260911T065955.813489Z` 为 698 次迭代、solve `206568.51908412296 s`、workflow `217665.16384237396 s`、full true `9.986638454029182e-7`；其资源连续资格仍不追认。该结果与当前 2 nm h1.5 只作为尺度讨论材料，不能替代当前 numeric/outer 测量。

当前 2 nm 已测到 4,899,800,920 augmented NNZ 和 symbolic facts；numeric/solve/outer 的完成时间及迭代速度尚未知。用户明确无法接受 `34.36 d` 量级工期，下一轮应在不改变物理/残差条件下评估降低单步成本的途径，并单独讨论是否需要另立并行化研究；本轮不实现算法或 MPI 变更。已有实测证据是 p4 体装配约 `29.33 h`、H6 setup 约 `9.44 h`，当前 MPI1/数学库线程1、跨 NUMA preferred-node1 和全局 p4 factor 都应纳入分析。以下两项只保留为假设推导，不是 ETA：

- 迭代线性外推：`57.38 h × 14.3735 = 34.36 d`，没有 2 nm 迭代证据，不能称确定工期。
- LU 同吞吐外推：`460.476 s × 176.065 = 22.52 h`，不是当前 run 的实测 numeric 完成时间。

待后续审阅的问题是：当前 numeric 的真实 RSS/阶段边界能否建立容量边界；4.8998e9 NNZ 对实际 MUMPS factor/工作区的增幅能否从本 run 直接测出；preferred-node1 及跨节点回落对 numeric wall/RSS 的实际影响；如何在 fine residual≤1e-6、p4 residual≤1e-10 且 refinement≤2、energy≤1e-5、screen128和max2048不变的条件下降低单步成本；是否应另立并行研究。这里不自行批准算法、MPI、预条件器或 Gate 变更。

## 历史边界

- 13.5 nm R1、R2 notch、5 nm 和 h1.5 历次失败均保留原记录；不以本快照覆盖。
- 5 nm own 数值/物理输出已通过，但 `REFERENCE_AUTHORITY_LIMITED` 与资源监督断档仍有效；其 600 通道证据是 5 nm 历史，不得套到本次 2 nm 的 3904 modes。
- h1.5 早期 affine 失败、PORD/MUMPS `INFOG(1)=-9999, INFOG(2)=4` 失败和预测资源阻断均保留；正式图的 NEDGES 未记录，`-51` 只来自有界 PORD 边界 probe 的强证据推断，不写成正式实测。
- 本次当前 run 尚未 numeric 完成、尚未 outer、尚无 RTA；h2 未启动。
