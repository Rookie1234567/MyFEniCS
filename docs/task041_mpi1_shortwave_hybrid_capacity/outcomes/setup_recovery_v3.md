# Task041 Response V4：setup/recovery 与配对证据

## 1. 结论和范围

本记录收拢 R2 原算法分侧 baseline 与 R2g 唯一 optimized sequential-component 运行的
构造、响应、释放、资源和离线配对事实。R1 实现了分侧生命周期入口，R2c 实现并验证了
显式 profile 下的 A1 owner-row 批量路径和 A2 复数共轭临时量路径；本轮 R4 文档阶段只
整理已关闭证据，没有重新运行计算。

分侧的含义是：先建 bottom 一套 p4/迭代 KSP，完成四项后释放，再建 top 一套完成四项。
它减少了同一时刻重复驻留的侧区组件，但不改变全局 Maxwell action、RHS、传播因子、
原 residual/精度检查或正式双侧 consumer。最终状态固定为
`PAIRING_IDENTITY_UNPROVEN`：两次 fresh run 的凝聚行缺少可验证的跨运行物理行身份，
所以不宣称数值等价、内存不增或完整 consumer 通过。

## 2. 身份、输入和结果入口

| 项目 | R2 baseline | R2g 唯一 optimized |
|---|---|---|
| source | `3ee452ac0adc0c3c88b9610b6446e93a3c02444a` | `376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab` |
| public root | `.../20260915T140512.548994Z` | `.../20260915T172219.672770Z` |
| full service wall | `4015.539370124 s` | `3630.563676387 s` |
| fixed component apply | `1680.27495998214 s` | `1258.8479048048612 s` |
| response artifacts | 8 manifests / 64 shards / `33901312 B` | 8 manifests / 64 shards / `33901312 B` |
| formal/full output | full Schur/outer/recovery/RTA `not_run` | 同左；额外/重复 optimized run `not_run` |

两次运行共用 5 nm p6/h4/M480/MPI8、`task041_schur_speed_v2`、
`sequential_component`、固定 packet/input 和八项清单；public 命令无外层 `mpiexec`，
worker 使用 MPI8、CPU0–7、每 rank 一个数学线程。完整路径、配置、manifest、closed
artifact 和 ledger 绑定见 [compact JSON](records/task041_setup_recovery_v3.json)。

## 3. 八项响应与生命周期

每次运行都是 bottom 四项（ordinal 0–3）后 top 四项（ordinal 4–7），每项 own
`reason=2` 且 explicit residual `<=0.01`。baseline bottom/top 最大 residual 为
`0.00920818603450433 / 0.009453705395988539`，optimized 为
`0.009208186034505206 / 0.009453705395970853`。R2e 的独立小 FE serial/MPI2
P/PH 全局 relative 均为 `0 <= 1e-11`，但它只证明 linear action/transfer，不证明
fresh response 的物理行配对。

| 生命周期边界 | 实测事实 |
|---|---|
| bottom ready | p4/KSP 各 1；四项顺序写入 owned shards |
| bottom release | diagnostics `destroyed=true`，p4/KSP=0，side live=0 |
| top before build | bottom 已归零，借用 global action/RHS identity 仍通过 |
| top ready/release | top 仅一套 p4/KSP；释放后同样归零 |
| 全 run | `created_total=2`，simultaneously-live peak=1；每侧峰=1、释放后=0 |

这些 counts 来自 raw lifecycle boundary 和 side diagnostics，不是空容器长度或 summary
常量。它是分侧生命周期证据，不能替代双侧同时构造的 p4 资格。

## 4. 构造 marker 的同钟整理

以下数据直接从两份 `consumer/markers.jsonl` 流式读取，并按 `(side,event)` 配对；
`system_ready` 是全局 system setup 完成点，`before_build→after_admission` 是该侧的
构造/准入区间，不能称为全局 system setup。worker wall 用
`worker_origin + worker_wall - outer_workflow_origin` 对齐 outer `CLOCK_MONOTONIC`；
outer RSS 只作 marker 前后的括号，不是同刻精确值。

| run / side | global `system_ready` worker wall | side build→admission | factor setup begin→ready |
|---|---:|---:|---:|
| baseline / bottom | `983.0788940798957` | `674.9525812410284 s` | `983.5931301249657 → 1653.4143726038747` |
| baseline / top | `983.0788940798957` | `669.0089339439292 s` | `2450.2057411340065 → 3114.250514271902` |
| optimized / bottom | `1039.0930612850934` | `660.0814286530949 s` | `1039.5970036741346 → 1696.573750832118` |
| optimized / top | `1039.0930612850934` | `664.6973237530328 s` | `2293.303577498067 → 2954.8940188910346` |

原始 p4 子阶段也已落盘：baseline bottom 的 matrix assembly/factor 为
`497.1479417809751 / 20.62342693703249 s`，top 为
`496.03055016906 / 31.757921094074845 s`；optimized bottom 为
`497.1506807389669 / 19.40718612796627 s`，top 为
`495.17534057307057 / 26.445405110018328 s`。对应 bottom raw lines 为 27–30，
top 为 61–64；完整 full-action/form/transfer/H6/adapter interval 和 line binding
保留在 compact 的 `construction_timing`，不是由 event-only 字典推导。

## 5. S0 归因和成本口径

S0 来源为
`results/task041_side_balh_component_audit/task041_schur_speed_v2_s1a_3890cdd2/s0_rhs_statistics_v2.json`，
18352 B，SHA `36781c22a3565d70ed37364c94a0c2ec104b12279bbad0a8f27c06f2ef8917cf`。它按
side/phase 保存 cost=8、formal modal=1920、sample=32、outer=20 的计数及 RHS wall
sum、median/p90/max、Q/H6/A6 和 uncovered。modal 的 1952 包含每侧 16 sample，正式
formal 是每侧 960。

| side / phase | count | RHS wall sum (s) | median / p90 / max (s) | Q / H6 / A6 (s) |
|---|---:|---:|---|---|
| bottom / cost_probe | 4 | `260.7828994761221` | `68.59954152896535 / 123.52996737207286 / 123.52996737207286` | `139.978631448932 / 17.73412113590166 / 84.75987191987224` |
| bottom / formal_modal | 960 | `90340.85915887542` | `105.87993654445745 / 136.18737301789224 / 306.09375961800106` | `48227.36092880694 / 6099.419908887241 / 29230.498126879567` |
| bottom / sample+modal | 976 | `91474.11646683724` | `105.85667004948482 / 136.14961000392213 / 306.09375961800106` | `48837.256919305306 / 6176.029820939526 / 29594.821537523763` |
| bottom / outer | 10 | `2395.5638189439196` | `80.39208332798444 / 650.1598564439919 / 689.9339378490113` | `1280.078159764642 / 168.65051933540963 / 775.5702761069406` |
| top / cost_probe | 4 | `407.6624744720757` | `94.19762945745606 / 156.4351340380963 / 156.4351340380963` | `219.0618424054701 / 29.374434218974784 / 130.7482474767603` |
| top / formal_modal | 960 | `90443.30406217626` | `105.69277824799065 / 136.9260180380661 / 359.24694890808314` | `48289.96794238221 / 6487.024378872709 / 29061.782369388267` |
| top / sample+modal | 976 | `91493.65305071231` | `105.6035790470196 / 136.7951175631024 / 359.24694890808314` | `48862.51957798959 / 6559.03811931028 / 29394.25792963244` |
| top / outer | 10 | `3087.595475415932` | `162.52467558102217 / 627.8503135940991 / 634.0634857409168` | `1659.1153715432156 / 222.75653227930889 / 995.1049590934999` |

这些是逐 RHS 或分项的 logging-rank/local 累计和同一 MPI.MAX 诊断，不是 campaign
rank-max，也不是可相加的临界路径。P/PH、p4 MatSolve、A4 inclusive residual、A6/H6、
通信/分配与 count delta 的 old/new 表在 compact；嵌套区间不再相加。A4 区间包含提取、
Vec 分配、physical action、norm 和 audit，不能与其内层 `matrix.mult` 相加。

## 6. 资源窗口和未决配对

| run | outer RSS raw / peak | 首次 warning | post I/O peak | PSS/USS |
|---|---|---|---:|---|
| baseline | 13255 行；`51975606272 B`（line 11112） | line 9795，`48513138688 B` | `51879936 B` | sparse `49164102656 / 48765517824 B` |
| optimized | 11999 行；`51796770816 B`（line 11992） | line 9289，`48116490240 B` | `51171328 B` | sparse `49031429120 / 48632651776 B` |

硬 cap 为 `53221163008 B`，baseline/optimized margin 分别为
`1245556736 / 1424392192 B`；观察到的峰差为 `178835456 B = 170.55078125 MiB`。
这是各自 full-service 已观测区间，不是双侧内存不增资格。PSS/USS 稀疏且非同刻 RSS
替代；job swap、global 新增 swap 和 pswp 增量均为 0，global used 的既有 baseline 为
`8192 B`。未知 native workspace/allocator 保留 unknown，RSS 下降不等于已证明释放或
没有泄漏。

正式配对状态是 `PAIRING_IDENTITY_UNPROVEN`。两个 run 的 132300 condensed rows 只有
各自 algebraic ownership range，没有稳定 geometric/topological entity、orientation、
FE basis 或 MPC active-row key；直接按数值位置相减的约 `sqrt(2)` 结果只作
`diagnostic_only_unverified_numbering`，不是 numerical failure 或 pass。未来最低需
补 hash-bound row-to-physical-key 映射并建立完整双侧 admission/capacity 证据；本轮不实现。

## 7. 负证据和未运行项

旧 S1f `53331742720 B > 53221163008 B`、fixed8=`0/8` 的
`process_tree_rss_limit` 受控停止仍是完整双侧构造负证据；旧 H3 的 numerical PASS 与
`RESOURCE_COMPARISON_INCONCLUSIVE` 继续独立保留。本轮没有改写这些结果。

| 项目 | 状态 |
|---|---|
| 新 13.5 nm | `not_run` |
| 新完整 5 nm 双侧 consumer | `not_run / not_qualified` |
| full Schur / outer / recovery / official RTA | `not_run` |
| 新 producer / 新 QEP | `not_run` / `qep_calls=0` |
| 额外或重复 optimized run | `not_run` |
| ordinary production default | 不变；V2/A1/A2 仍显式 opt-in research |

R2g 的完整 run 是 baseline 一场加唯一 optimized 一场；“第二场”只表示这场配对中的
optimized R2g，不表示存在两个 optimized run。预算尚余不等于准入，分侧通过不代表完整
双侧或 full consumer 通过。

## 8. 证据入口

- [Response V4](../response_v4.md)
- [Task041 setup/recovery compact](records/task041_setup_recovery_v3.json)
- R2h v1/v2、R2g index、S0 statistics 和原始 public/service root 均仍在 ignored results；
  compact 只引用路径、bytes、SHA、关键计数和必要字段，不复制大型 finalizer/consumer 快照。

<!-- r4b-final-metadata -->
最终 compact：[task041_setup_recovery_v3.json](records/task041_setup_recovery_v3.json)，153382 B，SHA256 `7f5d84e6a2a9a6809d9438bbb6e9444a4ffead9d6272728b394d3346401852df`；R4b 文档检查 15 passed，diff check passed。
