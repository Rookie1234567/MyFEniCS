# Task041 Schur speed v2：S5a 资源受控停止记录

## 当前结论

S1f 的 unoptimized fixed-eight-RHS baseline 在 `top_factor_setup_begin` 后、第一条代表性
RHS 前被严格的同时进程树 RSS cap 停止：`0/8` RHS，full Schur/outer/recovery/official
physics 均 `not_run`。这不是数值方法失败，也没有 speedup。当前阶段分类为
`controlled_negative_resource_stop`，直接原因为 `process_tree_rss_limit`。旧 H3 BAL_H
另行保持 `RESOURCE_COMPARISON_INCONCLUSIVE`，不能覆盖本轮 S1f 的资源受控负结果。

BAL_H 用每侧一个准确 p4 粗因子加迭代平衡响应，替代完整 p6 侧区直接因子驻留；它的收益
目标是减少驻留内存，代价是重复侧区求解，Maxwell 方程、P/PH、全局 action、真实残差和
recovery 定义不变。它必须显式 opt-in，不能提升普通 production default。

## 运行身份与固定范围

| 字段 | S1f 实际值 |
|---|---|
| source | `1c1d36b168bfb3939314ee2faf5b943cca804382` |
| model | `task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8` |
| profile/scope | `task041_schur_speed_v2` / `representative_rhs` |
| input | `input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat`；SHA=`9e77be901d54a8eb6d4f090588dec26c4913facd7c16c53fb46c0025eb31adb2` |
| packet | legacy descriptor SHA=`175a2463e15e039ff4dec91eed6a1f011d8eca338e1d2cc98cd8e30e37d86c86`；manifest SHA=`306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f` |
| fixed RHS manifest | `outcomes/records/task041_representative_rhs_v1.json`；SHA=`fb68011ed3e55861c59455d082be549cdd9f6c2d5a569015cf88bdc739f5636a` |
| physical/resolved | physical value SHA=`65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4`；resolved file SHA=`95a155334dacf75d30c005338ff689fd676532b49ae392e6fad868d0eee23e51` |
| execution | native `.venv` Python，complex128/int32，public 无 outer mpiexec，worker MPI8×1，OS CPU0–7，所有线程环境为1 |

代表清单的八项按 `side/polarity/audit_index/formal_column` 绑定：bottom positive
`227→207`、`35→15`，bottom negative `691→671`、`513→493`；top positive `330→310`、
`32→12`，top negative `686→666`、`513→493`。传播由已审 `modal_coupling_action(e_column)` 内部
完成；S1f 未生成向量，所有 actual RHS/response hash 保持 `not_materialized`。

## 四个已完成对照与 S1f

| 模型 | 结果 | consumer/full wall | 资源与边界 |
|---|---|---:|---|
| 13.5 nm exact | frozen numerical/comparison PASS | `390.9697992079891 s` | public resource contract PASS |
| 13.5 nm BAL_H | frozen numerical/comparison PASS | producer `26.684 s`；consumer `3002.409810984973 s` | RSS 比 exact 少 `254894080 B`（`2.707606%`）；同模型 consumer 约慢 `7.68x` |
| 5 nm exact | frozen numerical/comparison PASS | `1868.4593736410607 s` | 完整 consumer RSS/PSS/USS=`89123696640/87368944640/87121264640 B` |
| 5 nm BAL_H H3 | numerical/comparison PASS，resource inconclusive | worker `191662.819902868 s`；Schur `183016.74211002886 s` | public parent/summary 缺失、orphan terminal gate false；不能称完整 workflow memory pass |
| 5 nm BAL_H S1f | `0/8`，`process_tree_rss_limit` | outer phase `2221.4903851540294 s` | strict outer RSS cap exceeded before RHS；无新数值或提速结论 |

## 资源和生命周期原始摘录

外层 memory 文件：
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/s1e_preparation_20260915_1c1d36b1/unoptimized_rhs_baseline_1c1d36b1/memory_stages.jsonl`，7350 行、26113795 B，SHA=`5a46a99427c7d82e5c4eb9d8209b887e0a33c66f5ff865ae12df0c786e75c5b8`。

| 事件 | raw 证据 |
|---|---|
| 首次90% warning | line 7313，elapsed `2210.5727085701656 s`，RSS `47914586112 B`，threshold `47899046707 B` |
| 首次且唯一 cap 超限/峰 | line 7349，elapsed `2221.3724097050726 s`，RSS `53331742720 B`，cap `53221163008 B`，超出 `110579712 B` |
| 峰值组成 | 同行各 PID RSS 求和精确等于 `53331742720 B`；PSS/USS 不被用作 RSS 替代 |
| 稀疏 PSS/USS | peak=`40538401792/40140140544 B`；74 条 complete、7276 条缺测；RSS poll 和 smaps 峰不要求同刻度 |
| sampling | RSS/VmSwap 设定 `0.25 s`，PSS/USS 稀疏周期 `30 s`，最大相邻间隔 `0.8098343990277499 s` |
| swap/reserve | job swap=`0`；global used=`8192 B` 是既有 baseline，新增 used/pswpin/pswpout delta=`0`；reserve 未触发 |
| 末端 | line 7350 只剩 root RSS=`39407616 B`；是清理后样本，不是完整峰 |

严格 RSS cap 是同时 process-tree RSS，不是 cgroup `memory.current`；hard memory 256 GiB
和 384 GiB reserve 是独立安全线。public-only memory 段的 peak `53134987264 B` 不含外层
service parent，不能用它抵扣 cap。

外层在 cap Gate 后对 public group SIGTERM，`returncode=-15`、`process_group_gone=true`；
parent pre-exit 仍列 mpiexec/ranks，`pre_exit_members_clean=false`。systemd control-group
随后清掉 service cgroup；finalizer 只记录 post 时仅剩自身，不能把前一阶段改成自然 MPI
退出。finalizer 为 `service_boundary_failure`，`SERVICE_RESULT=exit-code`、`EXIT_STATUS=3`，
但关闭 artifact hash 子阶段 returncode=`0`。本次所有已知 Task041 PID 最终消失，foreign
Full3D `1652293/1652340/1652343` 保持未触碰。

## S0 归因基线和未运行项

旧 H3 candidate RHS raw 为 1980 行、3852327 B、SHA=`b84de36f3eacd82eab6ff8fad03c689bb49476efb153e7c4096fcdf61b3fc51b`：
cost8、modal1952（两侧各976，含32 sample、正式1920）、outer20；inner sum30295、
单 RHS max112、显式残差 max=`0.009989594141011119`。这些 counts 是调用次数，不能相加
为 wall；per-rank timing 是 logging rank/local 字典，不能恢复 campaign rank-max。

S0 的已完成归因统计文件为
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/task041_schur_speed_v2_s1a_3890cdd2/s0_rhs_statistics_v2.json`
（18,352 B，SHA=`36781c22a3565d70ed37364c94a0c2ec104b12279bbad0a8f27c06f2ef8917cf`）。
下表直接保留其中按侧、阶段的 wall 总和及分项诊断；`modal_schur_including_samples`
含每侧 16 条 sample，`formal_modal` 才是正式 960 条。Q/H6/A6 是同一 RHS 内
logging-rank 的本地累计后取 max，再跨 RHS 累加的诊断，不是父 wall，也不构成可相加的
临界路径；`uncovered` 是未被这些分项覆盖的累计诊断。

| side | phase | n | RHS wall sum (s) | median / p90 / max (s) | Q / H6 / A6 sum (s) | uncovered sum (s) |
|---|---|---:|---:|---|---|---:|
| bottom | cost_probe | 4 | 260.7828994761221 | 68.59954152896535 / 123.52996737207286 / 123.52996737207286 | 139.978631448932 / 17.73412113590166 / 84.75987191987224 | 18.957641705172136 |
| bottom | modal_schur_including_samples | 976 | 91474.11646683724 | 105.85667004948482 / 136.14961000392213 / 306.09375961800106 | 48837.256919305306 / 6176.029820939526 / 29594.821537523763 | 7081.481639462756 |
| bottom | formal_modal | 960 | 90340.85915887542 | 105.87993654445745 / 136.18737301789224 / 306.09375961800106 | 48227.36092880694 / 6099.419908887241 / 29230.498126879567 | 6996.194431796903 |
| bottom | outer | 10 | 2395.5638189439196 | 80.39208332798444 / 650.1598564439919 / 689.9339378490113 | 1280.078159764642 / 168.65051933540963 / 775.5702761069406 | 176.9064923322294 |
| top | cost_probe | 4 | 407.6624744720757 | 94.19762945745606 / 156.4351340380963 / 156.4351340380963 | 219.0618424054701 / 29.374434218974784 / 130.7482474767603 | 29.49469513213262 |
| top | modal_schur_including_samples | 976 | 91493.65305071231 | 105.6035790470196 / 136.7951175631024 / 359.24694890808314 | 48862.51957798959 / 6559.03811931028 / 29394.25792963244 | 6902.41703384812 |
| top | formal_modal | 960 | 90443.30406217626 | 105.69277824799065 / 136.9260180380661 / 359.24694890808314 | 48289.96794238221 / 6487.024378872709 / 29061.782369388267 | 6826.525625325739 |
| top | outer | 10 | 3087.595475415932 | 162.52467558102217 / 627.8503135940991 / 634.0634857409168 | 1659.1153715432156 / 222.75653227930889 / 995.1049590934999 | 218.2386420373805 |

该文件的 `p90` 定义为 `ceil(0.9*n)-1`（0-based nearest-rank）。更深的 P/PH、
MatSolve、A4 residual/refinement 细分在 S0 没有导出，保持 `unknown`，不从 uncovered
反推来源。

S1f 的新 fixed RHS raw/response、owned shard hash、完整 Schur、outer/recovery/RTA、
optimized/A-D timing、new producer/QEP 均 `not_run`。S1a-S1e 的插桩、service qualification、
finite binding 和 focused/static tests 只证明接口与生命周期边界，不替代这次未完成的 RHS；
当前提交集包含 BAL_H numerical core 与计时适配，但没有 A–D 等价性能优化。

## 证据索引与账本

compact 入口：
`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_completion_evidence.json`
，SHA=`5bae6062f6ad91abf3f4dfd91e21b9ed66c90b4e8c3e8a2a1e0df3d687330c3c`；本报告对应的
追踪 compact 为 [task041_schur_speed_v2.json](records/task041_schur_speed_v2.json)。它绑定 startup
index、launch manifest、config、input、descriptor、packet、resolved/physical、outer/public
memory、parent summary、finalizer、post files、rank affinity 和旧 H2/H3 comparator hashes；
大型 raw、场、matrix、factor 仍只在 ignored results。

本 unit 的六条 raw systemd journal 另存于
`/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/task041-s1e-rhs-baseline-1c1d36b1.journal.jsonl`
（SHA=`33b847ddf7206e33e876d290cb9130fcff55c90c07c55eb28aa55889694b2d96`）。其 `Consumed`
行给出 monotonic `1560545135499 us`、UTC `2026-09-15T05:39:48.195160Z`；从 unit start
`1558321618156000 ns` 得到外部包络 `2223.517343 s`，相对已记 finalizer wall 的尾差
`0.025435738 s` 已单独入账。

唯一 V2 ledger：
`results/task041_side_balh_component_audit/task041_schur_speed_v2_s1a_3890cdd2/task041_schur_speed_v2_compute_wall_ledger.json`
，当前 SHA=`902e8bbd40c5df4cbfef0a1f9c501d33575516e084fed6a10c54c275add26f7a`，used
`2881.0536036838917 s`；shared S0/S1/S3 remaining `18718.946396316107 s`，batch remaining
`198718.9463963161 s`，S2/S4=`0`。S1f finalizer `2223.491907262 s` 已只记一次，journal
terminal tail `0.025435738 s` 另记一次；两次独立文档检查外层 wall `1.125902230 s` 和
`1.110528022 s` 各记一次，共 `2.236430252 s`。未保存的完整 S1f preflight wall保持
`unknown`，不填零。

此记录不表示 S1f 通过，也不改写旧 H2/H3/H3g 分类。
