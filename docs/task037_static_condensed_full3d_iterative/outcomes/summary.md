# Task037 结果总览

## Review V3 p4-core部分凝聚收口

本节记录 V3 R7 的当前终点；下方 V2、V1/M3a 内容保留为历史。静态凝聚的通俗含义是先在每个单元内消去内部未知量，只把较小的 trace 系统交给全局求解器。完整 p6 单元局部块是 `882=432` 个 trace slots 加 `450` 个 interior；本轮没有另投影到较小的有限元空间，而是在这一本地代数中保留真实 exact-sequence 嵌入的 `108` 个 p4 core 行，消去 `342` 个 p5/p6 complement 行。这里的 432 是局部 trace slots，不是正式全局系统总行数。

| 阶段 | source | 结果 | 关键证据 |
|---|---|---|---|
| R7a local hierarchy | `ed871cbae51396e30ad5a3fd6bf32dc7601a4020` | PASS | 误差量级 `1e-14–1e-15` |
| R7b1 global retained action | `b93b72bac9095273c838ff653ca3bbf93567123c` | PASS | 最大约 `2.58e-15` |
| R7b2a compiled-form integration | `0c882e7a6da38b6a66625e002fe64fabe0a70674` | PASS | test244 serial/MPI2、test243 serial |
| R7b2b1 public DtN integration | `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a` | CONTROLLED NEGATIVE | complement Gate FAIL |

R7b2a 的 serial test244 为 `1 passed`, `132.33 s`, MaxRSS `548212 kB`，action `3.913e-16`；MPI2 test244 为 `129.36 s`、MaxRSS `536320 kB`、action `4.371e-16`；serial test243 `1 passed`, `34.50 s`。2-cell ledger 为 partial Schur `9331200`、eliminated factor `3745584`、basis `15070464`、maps `37304`、numbering `864` bytes。

R7b2b1 的 tiny 两-cell真实 compiled p6 public test245 结果为 `1 failed, 1 passed`，exit `1`，wall `88.15 s`，MaxRSS `661088 kB`，swap `0`。augmented rows=`760`，KSP reason=`2`，RHS norm=`11.707507837771832`，solution norm=`275.1048734370968`，full relative true residual=`4.271433780052363e-11`。独立 reduced norm=`2.169086505997297e-12`，eliminated complement norm=`5.000737489099658e-10`。

最终 hard Gate 为 `complement_norm / max(independent_reduced_norm, 1.0) <= 1e-11`；实际值超过限值约 `50.00737489099658` 倍，失败位置为 [test245:435](../../../src/test/test_245_task037_retained_dtn_adapter.py:435)。失败前未报错的断言不升级为完整 PASS；后续 recovery/MPC 断言因执行顺序为 `not_run_by_assert_order`。test245 未 xfail/skip/放宽阈值。

R7b2b2、setup-only formal ledger、MPI2 test245、MPI8 20/100/200、full solve、official R/T/A 均为 `not_run_by_gate`。Candidate E 为 `not_run_by_latest_user_sequence`；Candidate F addendum 为 `not_read_pending_v3_closeout`。没有正式目标 p6/h10 memory evidence；`661088 kB` 仅是 tiny test process MaxRSS。CSV 通用字段并集修复由独立 commit `6bc7d1e397834e4c316eaa3c59d4d90640835424` 承载，不改变物理。

Candidate D 的历史 D0 数值负证据（顺序为 `rho_B4 / rho_D / improvement`）为：low `0.24599945418880295 / 0.2540230551088513 / 0.9684138870126958`，high `0.24651896436171644 / 0.26531876351572775 / 0.929142594723057`，mixed `0.24612971921817314 / 0.2715867504171219 / 0.9062655628087525`；p2 factor count=`2`、factor NNZ=`4608`、p6 matrix/factor=`0/0`，rows/aggregate bytes=`not_recorded`。D 的后续 screen/full/restart/MPI1 均为 `not_run_by_D0_gate`。

权威 compact record：[V3 p4-core partial-condensation record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_v3_p4_core_partial_condensation_v1.json)；完整收口：[p4-core controlled negative](p4_core_partial_condensation_controlled_negative.md)。clean numerical carrier 为 `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a`，carrier 时 branch 相对 upstream `d875ba538f8334c5fd9e026192cacbdcd11e0794` 为 ahead/behind `5/0`。

## Review V2 当前候选漏斗收口

本节是当前 V2 结论；下方 V1/M3a 内容保留为历史证据。静态凝聚（先在每个单元内消去内部未知量）把全局问题缩小为 trace 与 auxiliary rows；factor-free（不保留 p6 全局矩阵或 p6 因子）再把局部 slab correction 改为动作计算。p2 auxiliary 是一个较低阶的全局校正空间；RAS 是只让每个共享行由一个固定 slab 回写的非重叠加法 Schwarz。screen Gate 是按 20/100/200 步逐级淘汰研究候选的门槛，不是 full-solve 成功。

权威 compact record：[V2 preconditioner funnel](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_v2_preconditioner_funnel_v1.json)。所有数字均绑定各自 MPI8 ignored artifact 与 source SHA；screen 结果不是 official R/T/A，也不是 production qualification。

| 候选 | 20 步 condensed true | 100 步 condensed true | 200 步 condensed true | 漏斗结果 |
|---|---:|---:|---:|---|
| A：p2 + diagonal pre/post | `0.9798706637378245` | `0.9625338200823326` | not_run | screen100 淘汰 |
| B2：factor-free，2 steps | `0.4263392615374972` | `0.26452427778264737` | `0.20957190163452238` | screen200 淘汰 |
| B4：factor-free，4 steps | `0.42611925267187817` | `0.17083264476239823` | `0.1405734647596501` | screen200 淘汰 |
| C：B4 + optimized Schwarz/RAS | `0.4631648828112781` | `0.18562438468519604` | `0.1488668017254931` | screen200 淘汰 |

四条路径都保持 p6 matrix/factor/NNZ=`0/0/0`、global A/F=`false/false`；B2/B4/C 使用一个 distributed p2 MUMPS factor（p2 rows=`4680`、matrix NNZ=`477216`），MPI8 screen 峰值约 `6.31–6.47 GiB`，不是完整收敛解的峰值。B2 200 的 derived prediction 为 `3845` iterations / `9027.507786733306 s`；B4 为 `6524` / `26451.930413699356 s`；C 的 prediction 为 `not_generated`。C 的真实几何中 interface rows=`51192` 与 active rows 相同，shared-only shift 因此覆盖全部 active rows；C 的新增有效机制主要是 one-hot RAS，但 100/200 步均劣于 B4。

因 A 在 100-step Gate 失败、B2/B4/C 在 200-step Gate 失败，各自后续 full、restart 90→60→40→30→20 与 MPI1 full 均按漏斗要求 `not_run`。这不是遗漏，也不把 KSP max-it 的 screen 当成收敛或 official result。

## 当前 M3a MPI scaling follow-up

同一 p6/h10、13.5 nm、S 偏振、M3a overlap `0.125` partition full-solve
候选现已完成 MPI1/2/4/8 对比。四组均收敛并产生 official R/T/A，MPI1/2/8
相对 MPI4 的 active/full-FE canonical relative L2 全部通过 `<=1e-5`；swap
均为 0。资源结果如下：

| MPI | full-FE residual | process-tree peak | watchdog lifecycle wall | 分类 |
|---:|---:|---:|---:|---|
| 1 | `9.973612808764094e-7` | `4.600486755371094 GiB` | `1999.033196 s` | numerical/resource PASS |
| 2 | `9.998092180122628e-7` | `5.682544708251953 GiB` | `1153.018865 s` | numerical/resource PASS |
| 4 | `9.923273535279698e-7` | `8.265838623046875 GiB` | `711.570295 s` | numerical/resource PASS |
| 8 | `9.861361777006587e-7` | `12.59341049194336 GiB` | `470.571549 s` | numerical PASS；`<=10.30 GiB` FAIL |

因此 MPI1 最省总内存，MPI8 最快但超出 Task37 绝对内存 Gate，MPI4 是该 Gate
内速度较快的折中。完整 canonical、80 modal orders、分阶段内存和 source 边界见
[MPI scaling report](m3a_mpi_scaling_comparison.md) 与
[compact record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_mpi_scaling_v1.json)。
MPI1/2/8 raw runs 绑定 `a51c54576655f36078446766f856fcb96431e190`；MPI4
绑定 `2631a4c47258c9def919530787e409774b8ce029`。`a51c5457` 只扩展 M3a
runner admission/parser tests，没有改变 `src/` 数值内核或 ordinary defaults。
production qualification 和 0.7 nm qualification 仍为 NO。

## 前序源码 v2 收口（MPI 范围由上节扩展）

当前 closeout 绑定 source SHA `2631a4c47258c9def919530787e409774b8ce029`；canonical Floquet edge/face 修复只影响显式 opt-in canonical export/comparator 路径，ordinary defaults 未改变。最新结果分类为 `NUMERICAL_SUCCESS_RESOURCE_REVIEW`：数值和物理 Gate 通过，M3a MPI4 absolute memory Gate 通过，但工程 50% memory 目标与 production qualification 未通过。

| 路径 | MPI / artifact | residual / official | peak / wall | 分类 |
|---|---|---|---:|---|
| Direct v2 | MPI8；[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v2.json) | `1.17818264392128e-11`；official=true | `15.059223175048828 GiB` / `218.851869611 s` | current direct authority |
| M3a full | MPI4；[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_overlap0125_partition_full_v1.json) | `9.923273535279698e-7` full FE；official=true | `8.265838623046875 GiB` / `701.6504903390305 s` | numerical success / resource review |

M3a 的 canonical active/full-FE packets、12/12 powers、12/12 boundary amplitudes和 fresh-mesh H(curl) norms均通过；active/full canonical relative L2 为 `1.2553898016411866e-6` / `7.880394026823442e-7`。M3a/Direct memory ratio `0.5488887791199146`，derived reduction `45.111122088008536%`，cross-MPI descriptive wall ratio `3.206052073423701`；这些不是同 MPI resource authority。`production qualification=NO`、`whole-branch merge recommendation=NO`。

历史 F0/F3/F5b/M2c/M3a screen 和 M4d negative 仍按原 records 保留；本节只提升当前 source v2 的证据，不覆盖历史负结果。完整 M3a 表见 [M3a full outcome](m3a_overlap0125_partition_full.md)。

## 历史 response_v0 快照（已由上节当前源码 v2 收口取代）

Task037 在固定的 13.5 nm、p6/h10、S 偏振、MPI8 Full3D 上完成了 direct
authority、assembled FGMRES 和一次 released matrix-free full solve。求解器真残差、
物理 observables 及 12/12 powers 和 12/12 boundary amplitudes 通过；raw
PETSc-index vector Gate 和资源 Gate 未通过。因此最终分类是
`PARTIAL_WITH_CONTROLLED_NEGATIVES`，不是 production-qualified pass。

静态凝聚把每个单元内部未知量先局部消去，只把 active trace 与 80 个 auxiliary
rows 留给全局系统；收益是全局 rows 降为 `51272`，代价是必须做 interior recovery 和
full explicit residual。assembled FGMRES 先形成 fine `F`，再用右预条件的两层 PC
迭代求解，避免 global direct factor，但仍保留 assembled fine matrix。F5b 在 setup
阶段用同一个 `F` 建立 slab factors 和 coarse basis，随后在 outer KSP 前释放 `F`，
用 cell-local Schur action 继续施加 fine action；它不是 never-materialized 方案。

### 统一结果

| 路径（证据） | 终点与 residual | 物理/向量 Gate | 峰值与 wall | 分类 |
|---|---|---|---|---|
| F0 direct（[authority](direct_authority.md)） | `2.8094057923e-11` | 12+12 pass；direct reference | `15.2550010681 GiB`，`370.18 s` | authority pass |
| F3 screen 20（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_20_screen_v1.json)） | reported/full `0.0302833465991175` | screen-only；decision pass；solver max-it expected；RTA `not_run` | `13.2211914063 GiB`，`159.96 s` | decision pass |
| F3 screen 100（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_100_screen_v1.json)） | reported/full `0.000608485581260`；last-40 ratio `0.1852104694` | screen-only；decision pass；RTA `not_run` | `12.9641036987 GiB`，`212.73 s` | decision pass |
| F3 screen 200（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_200_screen_v1.json)） | full `3.5885919793e-5`；predicted `323` it / `473.764 s` | full-solve authorization pass；RTA `not_run` | `12.9706878662 GiB`，worker `293.35 s` | full-solve authorization pass |
| F3 assembled full（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_assembled_full_v1.json)） | 337 it；three residuals `9.8166e-7` | 12+12/RTA pass；raw vectors fail | `13.6522331238 GiB`，`410.546 s` | not pass |
| F5b matrix-free（[record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f5b_matrix_free_full_v1.json)） | 337 it；three residuals `9.8166e-7` | 12+12/RTA pass；raw vectors fail | `13.6580085754 GiB`，`396.603 s` | partial |

F3 screen 的关键 history 均保留在 records；20 步没有预测值，100 步使用实际
last-40 decline，200 步使用记录中的 last-40 log-linear 预测。三项 screen 都是
screen-only，不是收敛或 official result。

### full solve 数值比较

| 量 | F0 direct | F3 assembled | F5b matrix-free |
|---|---:|---:|---:|
| `R_total` | `0.0007628814751` | `0.0007628816329` | `0.0007628816329` |
| `T_total` | `0.6027016340` | `0.6027016326` | `0.6027016326` |
| `A_balance` | `0.3965354845` | `0.3965354857` | `0.3965354857` |
| `A_volume` | `0.3965354845` | `0.3965354852` | `0.3965354852` |
| `R(0,0)_s` | `7.537612200510555e-4` | `7.537613464884375e-4` | `7.53761346488528e-4` |
| `T(0,0)_s` | `0.6026738723475807` | `0.6026738712269` | `0.6026738712269` |
| energy closure | `4.9916e-12` | `-5.3943e-10` | `-5.3943e-10` |
| significant channels | 12/12 + 12/12 | 12/12 + 12/12 | 12/12 + 12/12 |

F5b 的 fine-action relative error 为 `9.2309237020e-16`，远低于 `1e-11`；其
active-trace 与 recovered-FE ownership-order bytes 相对 F3 的差分别为
`1.5478270800e-14` 和 `1.4162962151e-14`。但相对 F0 direct 的 raw indexwise
relative L2 为 active `1.4210359558`、full FE `1.4121310623`，均失败
`<=1e-5`。这支持 ordering inference，不能替代 Task 7.1 raw-vector Gate。

### 资源与结构 Gate

| 项目 | F0 | F3 full | F5b |
|---|---:|---:|---:|
| process-tree RSS | `15.2550010681 GiB` | `13.6522331238 GiB` | `13.6580085754 GiB` |
| worker PSS / USS | `13254.321 / 13047.027 MiB` | `11980.911 / 11776.828 MiB` | `12058.898 / 11854.363 MiB` |
| swap | 0 | 0 | 0 |
| active / auxiliary / augmented | `51192 / 80 / 51272` | same | same |
| operator / coarse / smoother applies | direct path | `1093 / 337 / 2022` | `1093 / 337 / 2022` |

F5b 相对 F0 只节约约 `1.597 GiB`、约 `10.5%`，仍高于 `10.30 GiB` resource
gate；相对 F3 没有实质改善。它有 `16` physical slabs、75/75 coarse、16
factor-only ILU(0)、global direct factor count `0`；这些结构结果不能替代内存
Gate。

### 规模与分阶段耗时

| 规模/存储量 | F0 direct | F3 assembled | F5b released matrix-free |
|---|---:|---:|---:|
| full FE / active / auxiliary / augmented rows | `173802 / 51192 / 80 / 51272` | same | same |
| full trace rows | `60402` | `60402` | `60402` |
| fine matrix NNZ used / allocated | `41989040 / 42625520` | same and held | setup formed same `F`, released before outer KSP |
| factor inventory | MUMPS `209772680` | global direct factor count `0` | global direct factor count `0` |
| local-factor aggregate | — | `103336560` across 16 local factors, not a global factor | `103336560` across 16 local factors, not a global factor |

| path | measured phase timings (s) | total wall (s) |
|---|---|---:|
| F0 direct | assembly `90.9635`; factor setup `140.3829`; backsolve `0.1941`; recovery `0.1260`; full residual `109.5097`; RTA/post `8.6164` | `370.18` |
| F3 assembled | core setup `26.39295`; core solve `265.87634`; recovery `0.03812`; stage4 `391.65416`; post `9.15041` | `410.54647` |
| F5b released | core setup `26.16943`; core solve `252.79113`; recovery `0.02824`; stage4 `378.93805`; post `9.14910` | `396.60297` |

Core setup/solve/recovery 与 stage4/parent total 是不同的嵌套计时口径，不能相加。

### 受控负结果与边界

- F1 direct-vector oracle 的 residual 约 `3029.7262491090364`，远高于其
  `1e-9` Gate；returned augmented norm `1484.6523798860264` 与 F0
  `742.1374458852146` 不一致，证明 F0 raw active vector 不能直接作为当前运行坐标的 oracle。
- F3/F5b raw vector indexwise Gate 均失败；物理采样、排序 magnitude 和 F3/F5b
  ownership-order 一致性只能说明比较口径疑似受 partition/DoF ordering 影响。
- 两次 serial tiny lifecycle smoke（p2/h50、p6/h50）在 release/KSP 前因 5 层
  z 网格上的固定 75D coarse basis singular，既不证实也不否定 F5b；另有一次目录
  路径拼写错误未形成有效数值 run。正式 p6/h10 MPI8 F5b 只运行一次。
- MPI4 formal full、F4、F5c、F6、Hybrid、hp、0.7 nm 和 Task037b 均未运行，且
  F5c/F6 保持 `not_run`。当前不能外推为 0.7 nm 可用。

### 证据与下一步

完整 12-channel 表和 F5b/F3/F0 对比在
[matrix_free_report.md](matrix_free_report.md)，资源与 MPI 边界在
[resource_and_mpi_report.md](resource_and_mpi_report.md)，F3 full 细节在
[assembled_fgmres_full.md](assembled_fgmres_full.md)。结构化证据还包括
[F0 record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v1.json)
和 [F5b record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f5b_matrix_free_full_v1.json)。

建议下一步先做峰值对象生命周期归因；若另立任务，再评估真正 no-global-F 和
scalable auxiliary multigrid。Task037b 只作为建议，不在本任务启动。
