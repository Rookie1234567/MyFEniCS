# Task041 outcomes summary

> **2026-09-20 D3a 终态（as-of 2026-09-20T07:49:33.807349Z / 15:49:33.807349 CST）**：D1e 已结束，不能继续沿用下方 D2a 的“运行中”作为当前状态。producer QEP packet 已保存；consumer 在两侧合成 modal Schur 重复一致性门失败，原始分类 `IMPLEMENTATION_FAILURE`，finalizer 为 `failed/service_boundary_failure`。这不是 OOM、超时、外部 kill 或投影误差结论。40 行=8 probe+32 modal，bottom/top 各16；formal Schur `0/4800`，outer FGMRES `not_started`/0，RTA/full field `not_run`。本段只记录已自然终止的旧 D1e 与 producer metadata 复用核验，作为 Review V5 R0 的已有终态证据；R1–R6 均 `not_run`，不记人工受控停止。详见 [Response V8](../response_v8.md)、[D3a terminal record](records/task041_d3a_terminal_20260920.json) 和 [2nm terminal summary](2nm_d1e_terminal_20260920.md)。

| D3a 终态项 | 实际值 |
|---|---|
| 运行 source / unit | `bde0686891af10bb489e4b1cb14500791cb50351` / `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` |
| producer / consumer | `29504.116038094042 s, rc0` / `135717.4772190291 s, rc1` |
| public / finalizer | `165222.44361121487 s` / charged `165228.433265082 s`; finalizer `service_boundary_failure` |
| repeat gate | combined bottom+top sample: relative `4.427612e-05 > 1e-10`; `max_column_relative_error=1.169058e-04`; side root cause unlocalized |
| modal raw | 40 lines, `87154 B`, SHA `dd06b01eac2928ff0814bef9bd3951ac256d776366ed7fd177392374e0175cde` |
| resources | service-tree RSS peak `642483171328 B`; cgroup peak `647904940032 B`; warning/hard/reserve `1539316278886/1759218604442/412316860416 B`; global swap baseline `8192 B`, new used `290816 B`, pswpout +71 pages; job/cgroup swap `0` |
| producer reuse | packet retained; metadata validator `rc=0`, `producer_resource_qualified=true`; consumer-only restart/shard+ABI consumption validation not run |

底部样本 `16/352 iter/36004.124497986864 s/max residual 0.009981656767193032`，顶部样本 `16/394 iter/40527.54153031926 s/max residual 0.009939510152843832`；这些小 RHS 的 `reason=2` 不等于正式 Schur 或全局物理通过。D1e 的完整终态与旧 D2a 运行中记录分开保存。

> **2026-09-20 D2a 运行中状态纠正（as-of 01:19:51.480911341Z / 09:19:51 CST）**：下列旧段仍是历史登记，不再代表当前最新运行状态。D1e 已实际启动并仍在运行；producer QEP 已完整落盘，consumer 尚未完成 full solve，formal Schur `0/4800`，outer solver `not_started`/outer response `0`（分母不适用），RTA `not_run`。当前不是终态，`systemd Result=success` 不是 solver PASS。

模型是钨（W）、2nm、p6/h1.5、M1200、MPI8×1；Schur 是供外层迭代使用的模态耦合预条件矩阵。当前两侧各 8 列各算两遍的重复性计划共 32 次，已有 21/32 个样本，正式 Schur 仍为 `0/4800`，不是 21 项 formal 进度。

## 2026-09-20：Task041 D2a / D1e 运行中（历史快照，已被上方 D3a 终态覆盖）

| 项目 | 当前事实 |
|---|---|
| source / unit | `bde0686891af10bb489e4b1cb14500791cb50351` / `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` |
| host身份 | Invocation `1cf5e34338754dbfa80df487b322c72c`，MainPID `571560`；CPU1–8，数学线程1 |
| producer | QEP mode-prep wall `29501.598348574014 s`，packet ready，scope released |
| formal Schur / outer | formal Schur `0/4800`；outer FGMRES `not_started`、outer response `0`（分母不适用） |
| 21 modal样本 | bottom13 / top8；固定均值外推 `133.57896112787233 days`，仅 derived sample arithmetic，不是 ETA |
| modal数值审计 | 21行均 `reason=2`、`explicit_true_target_reached=true`；最大 `relative_residual=0.009981656767193032 <= 0.01`，不等于最终全局残差 |
| memory as-of | process-tree RSS `642483105792 B`；cgroup current/peak `647585968128/647695921152 B`；不是完整运行峰值 |
| producer reuse | packet/hash 已核验；缺 public `supervisor_summary.json`，consumer-only reuse 尚未 qualified |
| 状态边界 | 不停止、不重启、不发 signal；无 full solve/RTA/official qualification |

报告与记录：[Response V7](../response_v7.md)、[D2a hash-bound record](records/task041_d2a_progress_20260920.json)、[2nm progress](2nm_d1e_progress_20260920.md)、[D1e evidence index](../../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_evidence_index.json)。

## C2d：共同布局离线复核收口（2026-09-16）

本节为 2026-09-16 历史快照。C2c 没有启动新计算，而是对已有 C2 raw 运行做了最小摘要纠正：
raw 已有两侧各 4 对、每场 8 项，共 8 对/16 主响应；合并摘要把 `apply_count` 写成
`8`，派生视图仅改为 raw 重算的 `16`。因此离线 checker 可判定同布局响应等价通过，但
原 service 的 `PAIRING_SETUP_FAILURE` / `service_boundary_failure`、systemd exit3、旧
summary、run/finalizer/journal 和全部 raw 均保留，不能把原服务改写成成功。

| 维度 | C2d 实际结论 |
|---|---|
| scope / mode | `representative_rhs` / `common_layout_equivalence`；仅既有 C2 raw 的离线派生复核 |
| 主响应 / pairs | `16/16`、`8/8`；每侧 4 对；8 个固定 RHS，两个 variant 均 zero-start |
| 数值 | `max e_x=3.0316012438358734e-9`、`max e_A=8.229180550916894e-9`；原 reason/residual 逐项通过，inner residual 仍≤`1e-2` |
| layout/lifecycle | 同一 side 的 mesh/MPC/凝聚布局、A、p4 factor、P/PH/PC 和 bottom release→top 顺序由 raw checker 复核 |
| 组件耗时 | `1981.6339287383016 → 1454.4546840919647 s`，减少 `26.6033%`；仅同进程诊断，不是完整 cold/service 提速 |
| 资源 | C2 全树 RSS 峰 `51501744128 B`，硬 cap `53221163008 B`；含 service 采样口径，但不构成双侧 full 资格 |
| 正式边界 | `COMMON_LAYOUT_EQUIVALENCE_PASS_OFFLINE_DERIVED`；跨 fresh-run physical-row mapping 仍缺，旧 `PAIRING_IDENTITY_UNPROVEN` 不变 |

原始/派生 summary、16 audits、8 pairs、128+128 shards、诊断包及 checker 结果见
[C2c offline index](../../../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/c2c_offline_review_index.json)
（SHA `db0f4a1d247f6a75002981db927241d162375a82b425f9c0fe9acce2e3940aca`）。当前源码
修复已提交为 `caeb678225d63f16bd95272ba60b08b16caf36af`；C2c checker 绑定的运行源码为
`5b57375d50c777abb5d0096db843095683f49b5f`。唯一 V2 ledger 当前
`17762.27669256989 s`，shared remaining `3837.723307430111 s`，SHA
`e5803851257eabd643be7048e81fae2c8d5e9957c4309c7f433b75ddd3805e27`；C2c 追加
`7.820470533 s`，本次文档 JSON/diff 检查另追加 `0.066910437 s`，没有重复收费。

旧 S1f 双侧 `53331742720 B > 53221163008 B` 的 `process_tree_rss_limit` 受控停止、旧
H3 `RESOURCE_COMPARISON_INCONCLUSIVE`、旧跨运行编号缺口和所有事故证据均单独保留。
这次不启动新的 service/MPI/PDE；full Schur/outer/recovery/official RTA、13.5 nm、
QEP 和额外 optimized run 仍为 `not_run`。

## V4-A0 历史：启动前邻 heavy Gate（2026-09-16，保留）

以下是 A0 当时的历史快照，不覆盖上方已完成 C2 的最新状态：宿主上另一 worktree 的 Full3D
`original_2nm_si_p6h1p5_native.dat/full3d_iterative` 仍在运行。本阶段没有启动 Task041
测试、MPI、PDE 或 service；V4 C1 尚未实现，C2/C3 及 16 项主响应均 `not_run`，因此没有
本轮 RSS、提速或 response 等价数据。

| V4 项目 | 状态/边界 |
|---|---|
| 主响应 | `0/16`；8 对 `0/8`；`not_run` |
| layout、P、PH、PC、response 等价 | `not_run` |
| 新运行 | `scope.new_runs=false`（仅 V4 文档/启动前阶段；历史 R2 baseline 与唯一 R2g 已运行） |
| 历史正式配对 | `PAIRING_IDENTITY_UNPROVEN`，保留旧 R2/R2g 结果，不因本轮阻塞改写 |
| 双侧资源历史 | S1f `53331742720 B > 53221163008 B`，独立的 `process_tree_rss_limit` 受控停止 |
| 现场证据 | [V4-A0 host snapshot](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/active_heavy_protection.json)；SHA256 `8b3b1ce344bfcb66ad313db6fd714f01fda53375cbb6509432577b39541ff98d` |

完整状态与固定八项见 [V4 common-layout compact](records/task041_common_layout_equivalence_v4.json) 和
[V4 说明](common_layout_equivalence_v4.md)。本轮不填 runroot，不把旧分侧峰值或旧 apply wall
冒充 V4 测量；旧 H3 的 `RESOURCE_COMPARISON_INCONCLUSIVE` 继续单列。最终两项文档静态
命令 exit `0`、父侧 `CLOCK_MONOTONIC` wall `0.063355920 s`，账本一次追加后为
`11145.889606652894 s`，shared remaining `10454.110393347106 s`，ledger SHA256
`1473ad466c95a05bf4f4c186864d03f3304f58b904873a9ae6ecca08a7535953`；四次此前遗漏的失败
按 `tool_reported_command_duration` 补记 `0.180794456 s`，原始记录见
[`v4a0_final_json_diff_check.json`](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/v4a0_final_json_diff_check.json)。

## S5a：S1f fixed-eight baseline 的资源受控停止（2026-09-15）

本轮唯一新增 heavy 是未优化的固定 8 RHS baseline；它在第一条代表性 RHS 之前的
`top_factor_setup_begin` 阶段触发 simultaneous process-tree RSS cap，实际 `0/8`，
因此没有新的数值、物理、等价性或提速结果。状态是
`controlled_negative_resource_stop`，原因是 `process_tree_rss_limit`。本轮 shared
S0/S1/S3 的 21600 秒（6 小时）预算未触发；`RESOURCE_COMPARISON_INCONCLUSIVE` 仅
属于旧 H3 BAL_H 的完整资源比较缺口。这不是数值失败，也不能因为 host 余量充足而提高
cap；严格 cap 为 `53221163008 B`，外层峰为 `53331742720 B`，超出 `110579712 B`。

| S5a 项目 | 实际值/边界 |
|---|---|
| source / model / profile | `1c1d36b168bfb3939314ee2faf5b943cca804382` / `task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8` / `task041_schur_speed_v2` |
| scope | `representative_rhs`；固定 RHS `0/8`；full Schur、outer、recovery、official RTA `not_run` |
| outer wall | `2221.4903851540294 s`；service unit elapsed `2223.491907262 s`；两者不相加 |
| RSS authority | outer raw peak `53331742720 B`，cap `53221163008 B`，delta `110579712 B`；line 7349，PID sum 一致 |
| warning | line 7313，elapsed `2210.5727085701656 s`，RSS `47914586112 B` |
| sparse PSS/USS | `40538401792/40140140544 B`；74 complete、7276 missing；不是同刻度 RSS 替代 |
| swap / reserve | job swap `0`；global baseline `8192 B`，新增 used/pswpin/pswpout delta `0`；reserve 未触发 |
| lifecycle | outer return `-15`/`process_tree_rss_limit`；parent pre-exit members 不清空；finalizer `service_boundary_failure`、systemd exit status3；最终 cgroup 清空但不称自然成功 |
| evidence | [S5a report](schur_speed_v2.md)；[S0/S1 compact](records/task041_schur_speed_v2.json)；ignored compact=`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_completion_evidence.json`，SHA=`5bae6062f6ad91abf3f4dfd91e21b9ed66c90b4e8c3e8a2a1e0df3d687330c3c` |

完整 raw memory、markers、parent/finalizer、journal 和 public-only 段仍保留在 compact 指向的
ignored root；public `run_summary` 为 `launching/exit_status=null`，本次外层终态不从它推断。
此前 H2/H3 数值比较 PASS、H3 资源不完整、H3g 事故和所有旧负结果均保持不变。

## H4 当前 Task041 BAL_H 终态（2026-09-14）

BAL_H 用每侧一个准确 p4 粗因子和迭代平衡响应替代完整 p6 侧区精确因子；全局 Maxwell 方程、全局 action/RHS 和正式 recovery 定义不变。它是降低因子驻留内存的研究候选，代价是重复侧区求解和更长 wall，仍为显式 `research_only_approximate_candidate`，没有提升为 production default。

| 项目 | 结果 |
|---|---|
| 最终审查分类 | `RESOURCE_COMPARISON_INCONCLUSIVE` |
| 数值/物理 | H2 13.5 nm exact/BAL_H 与 H3 5 nm exact/BAL_H 均通过冻结比较；H3 candidate worker own gates 通过 |
| H3 comparator 原始分类 | `TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL`，exit1；`numerical_pass=true`、`comparison_contract_pass=true`、consumer resource false |
| H3 exact | p6/h4/M480/MPI8，consumer wall `1868.4593736410607 s`，完整 public-tree RSS/PSS/USS `89123696640/87368944640/87121264640 B` |
| H3 BAL_H | p6/h4/M480/MPI8，worker wall `191662.819902868 s`；Schur `183016.74211002886 s`、outer `5486.829851052957 s`；public parent/最终 summary 缺失，资源/正常退出未资格化 |
| H2 consumer 描述 | BAL_H RSS 比 exact 低 `254894080 B`（`2.707606%`），但 consumer wall 约慢 `7.68x`；不裁决跨模型可信节省 |
| 未运行 | `full3d_secondary`、H3/H4 的 5 nm 新 producer/QEP、全仓 pytest、CI；不启动更短波长 |
| 核心证据 | [H4 中心报告](side_balh_transfer_v1.md)、[compact record](records/task041_side_balh_transfer_v1.json)、[H3 completion audit](../../../results/task041_side_balh_component_audit/h3h_final_20260914_51694bbc/h3_completion_audit.json) |

H3 candidate 的完整数值比较仍为 PASS；整体 false 仅表示 public supervisor/资源证据不完整。H3g 的 terminal sampler 最后一行 gate false、实际九组 TERM 与 rank0 组 KILL、`notLoaded` 通知失败和 parent 丢失均保留，不改写成正常 MPI 退出或全流程资源通过。

H3 candidate 的 public memory 段是无 `record_type` 的 synthetic label：226484 行（preflight 1 + consumer 226483），RSS 峰 `53221163008 B`，同时可读 PSS/USS 峰 `50485623808/50090246144 B`（2287 行可读、224196 行缺测），min MemAvailable=`2023682953216 B`。job swap 为 `0`，global used 的既有 baseline 为 `8192 B`，used/pswpin/pswpout delta 为 `0`；这些只是该段观测，不能升级为完整 consumer 峰。

账本当前 `203701.83937335422 s` 仅是显式 measured records 的覆盖和；初始 `6000 s` 是 derived conservative allowance，不是数学上界，不能写成整批完整实测耗时。三段 orphan 记录均来自同一个 hash-bound 文件，按 `record_type` 为 `822/6284/442921`，不是三个独立 raw 文件。

## 历史 3 nm 总结判定

| 字段 | 最终值 |
|---|---|
| final classification | 3NM_COMPLETED_NOT_GRID_CONVERGED |
| 说明性停止状态 | CONTROLLED_STOP_AT_3NM_PHYSICS_GATE |
| merge approval | NO |
| 范围 | 3 nm p6/h3 M800、M1200；5 nm inherited/local MPI8/MPI1 evidence |
| authoritative result | M800/M1200 均 candidate physics negative；official RTA/canonical/grid withheld |

solve/recovery mechanics pass 不等于 own physics pass。以下表格保留每个
独立 evidence/run 的身份、资源 authority 和失败边界；NA 是对应 raw record
没有可可靠提取的字段，不是猜测的零值。

## 正式模型与证据表

| status | 完整 source SHA | input / physical / resolved SHA | active rows | external keys | M delivered | iterations / restart / KSP | 五 true residual（reported/global/bottom/modal/top） | R / T / A / A_volume | grid / M comparison | producer / consumer / workflow RSS/PSS/USS（authority） | wall | swap | factor inventory | classification | 完整 evidence path |
|---|---|---|---:|---:|---|---|---|---|---|---|---|---:|---|---|---|
| failed fresh attempt | 48f56ad46c49519de363b90695d1ed219236c662 | 5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782 | 268272 | 1748 | 800/800（producer packet） | NA（consumer formal fields null） | 7.246419845266236e-10 / 6.711767430501667e-10 / 6.842952026951734e-12 / 7.252171978674087e-11 / 6.339676899706935e-10（diagnostic marker only） | NA（consumer formal fields null） | NA；diagnostic only，不能作 M comparison | producer 16.784275055/15.785678864/15.674812317；consumer/workflow 255.465618134/253.694432259/253.435222626（workflow process-tree summary） | producer 18000.658898；consumer 22215.056788；workflow 40216.175178 s | 0 | bottom/top corrected NNZ 3.259e9/3.716e9；MUMPS factor-only；ICNTL14=40；global direct/coarse/OOC=0 | IMPLEMENTATION_FAILURE at consumer_exit(solution_snapshot_destroyed)；diagnostic marker only | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260907T111441.388055Z |
| candidate retry complete | 2dbe7ff76d734c7689740a656ba7c0fdb5ceadcb | 5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782 | 268272 | 1748 | 800/800（旧 packet 复用） | 1 / 10 / right GMRES | 1.0614289127347946e-09 / 1.3530838051427825e-09 / 9.525482983090863e-12 / 5.059125745287973e-11 / 1.278144562727163e-9 | 0.8048686830648746 / 0.0002839834330554354 / 0.19484733350206998 / 0.19486649353451532 | M800；无合法 M pair，physics negative | producer NA（consumer-only）；consumer 213.299564362/NA/NA；workflow 213.299564362/NA/NA GiB（raw cgroup/process diagnostic；direct PSS/USS NA） | producer NA；consumer/workflow 17047.323762 s | 0 | bottom/top corrected NNZ 3.304e9/2.861e9；MUMPS factor-only；ICNTL14=40；global direct/coarse/OOC=0 | TASK041_CONSUMER_NUMERICAL_FAILURE；measured_candidate_physics_negative；official withheld | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260908T001027.090767Z/consumer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260908T001027.090767Z/numerical_output/v3_7_hybrid_authority.json |
| linked candidate stages complete | producer c3a5bf4a424405c1f1de5cd6ac96be8db576f7b3；consumer c72b3e0d1540a5a891f5906fb0d75dc9146fefd2 | dab4209d2094d8640deaa61d5b6948a37d50362dc6b304762f93feff515b45c0 / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 077624826a392f1ed83e11d3c55bd462ae631a6c2ddcb01e2e2d1daa080d62e0 | 268272 | 1748 | producer 1200/1200；consumer 1200/1200（packet reuse） | 1 / 10 / right GMRES | 5.733598076322987e-10 / 5.650904282024035e-10 / 2.5112691971837548e-11 / 6.142421244928043e-11 / 5.337481450973294e-10 | 0.8048682104336213 / 0.000285259036006279 / 0.19484653053037237 / 0.19486523527614544 | M800→M1200 scalar diff R/T/A/A_volume = 4.726312532454813e-7 / 1.275602950843622e-6 / 8.029716976054591e-7 / 1.2582583698850236e-6；仍无合法 convergence pair | producer 28.318450928/27.452210427/27.341518402（parent telemetry diagnostic）；consumer 250.271244049/248.480698/248.221230（process-tree/control telemetry）；workflow同不重叠 max，不相加 | producer compute 15386.145391；consumer 15750.067281；workflow NA（linked sum 31136.212672 s，非 uninterrupted） | 0 | consumer bottom/top 3.646e9/3.135e9；MUMPS factor-only；ICNTL14=40；modal rank2400、batch32、75/side；producer为QEP packet phase | TASK041_CONSUMER_NUMERICAL_FAILURE + outer bookkeeping_failure；不是 uninterrupted supervisor PASS；measured_candidate_physics_negative | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer/producer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer/selected_mode_packet/manifest.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry/consumer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry/numerical_output/v3_7_hybrid_authority.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry.control/phase_failure.json |
| inherited reference complete | 9e31ecf189081afcb8ca27b0374ec89af0094e2d | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 / NA（tracked record无 physical hash） / NA（tracked record无 resolved hash） | NA（record） | NA（record） | NA（record） | 1 / 10 / GMRES（record） | 3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10 | NA（tracked record） | NA；Task039 inherited，不作为 Task041 M comparison | producer NA；consumer NA；workflow 80.0258560180664/NA/NA GiB（tracked process-tree peak） | producer/consumer NA；workflow 10126.231902 s | 0 | NA（tracked record未提供 factor inventory） | Task039 inherited full numerical/recovery/physics pass；不等于 Task041 MPI1 equivalence | /home/fenics/Projects/MyFEniCS/benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json |
| local reproduction complete | def547cfd139b6377b0cae2ba1736ec3591814b0 | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 / 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c / d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798 | 132300 | 600 | 480/480 | 1 / 10 / GMRES | 2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10 | 0.7331842733894981 / 0.00022009869572663576 / 0.26659562791477526 / 0.2665962726231523 | NA；独立 5 nm MPI8 reproduction，不与 inherited 合并 | producer/consumer/workflow RSS/PSS/USS=NA/NA/NA；仅有 workflow peak 80.2187461853 GiB（compact authority unspecified） | producer/consumer NA；workflow 8357.347033 s | 0 | MUMPS factor-only；corrected factor NNZ=NA | Task041 local MPI8 solve/recovery/physics pass；不证明 MPI1 equivalence | /home/fenics/Projects/MyFEniCS/results/task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf |
| final MPI1 inner complete, outer unqualified | d6c71401a7105d2c67e22596e40461354cfda21f | 5a6a87882828ae768c92d4f14b45dbcb5f90c0bf141b982b106e52dba2b4c5c0 / 65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4 / 536d0ccb93f6c7bf00c42a12f60ea58bfe44436725da7070af2230fad305dc73 | 132300 | 600 | 480/480 | 1 / 90 / FGMRES | 1.9141387966716752e-10 / 1.914124454116583e-10 / 8.551881036770462e-12 / 1.489643628946544e-11 / 1.7761587180860387e-10 | 0.7331842733878213 / 0.0002200986957195755 / 0.2665956279164591 / 0.266596272621591 | NA；external key identity mismatch prevents equivalence | producer 2.46059799194/2.42841053/2.41315460；consumer 43.2886276245/43.2520036697/43.2368469238；workflow max=43.2886276245/43.2520036697/43.2368469238 GiB（raw telemetry diagnostic） | producer 12285.1455821；consumer 37058.1461057；workflow 49346.574875 s | 0 | MUMPS factor-only；corrected NNZ=NA（compact evidence未提供） | inner solve/recovery/physics/candidate RTA pass；external_key_binding_pass=false；outer task041_resource_sample_failure | /home/fenics/Projects/MyFEniCS/results/task041_5nm_exact_side_hybrid_iterative_p6h4_m480/task041_5nm_p6h4_m480_mpi1__hybrid_iterative__mpi1__M480/20260904T152109.607989Z |

M1200 producer packet 的 manifest SHA 为 c7a36ab977e5fc11505ad27a6e8044fc9e909b42fd37a8ea1abeb72b6e49d71b，canonical identity SHA 为 cef2de437f0b0a247791acc8e4b865d1fd51082b181617ab6621cb9a95ba5d00，packet directory bytes=1370082162，32 shards，write max-rank=1.167526111 s。M1200 producer 与 consumer 是 hash-bound linked evidence，不是 uninterrupted supervisor PASS。

## 最终分类合同

task.md 的最终枚举中，本次唯一适用的是 3NM_COMPLETED_NOT_GRID_CONVERGED。
5nm 的三个枚举均不能诚实采用：

1. 不是 5NM_MPI1_EQUIVALENCE_PASS，因为 external identity binding 和 outer
   resource authority 尚未闭合；
2. 不是 5NM_MPI1_OWN_PASS_REFERENCE_ARRAYS_PARTIAL，因为该条件要求的
   reference identity/authority 仍不完整；
3. 不是 5NM_MPI1_NUMERICAL_OR_PHYSICS_FAIL，因为 final MPI1 inner
   solve/recovery/physics 并未失败。

因此另以 evidence boundary 记录 EQUIVALENCE_NOT_ESTABLISHED，而不伪造
task.md 枚举。CONTROLLED_STOP_AT_3NM_PHYSICS_GATE 只是说明性状态，不是
task.md 的替代枚举。

## M 与未运行项

M800 与 M1200 的 energy failure 分别为
abs(A_balance-A_volume)=1.9160032445286745e-5 和
1.8704745773062692e-5，均大于 1e-5。虽然 scalar absolute difference
较小，但两个 M 都没有 own pass，故不存在合法 convergence pair。

| item | result | final reason |
|---|---|---|
| 3 nm p6/h3 M1600 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE；no valid own-pass M pair，task.md §12.2 true Gate |
| 3 nm h2.5/h2 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |
| all 2 nm | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |
| post-gate MPI1 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |

M1200 是用户后来明确授权的 controlled continuation，不能用上述 reason
暗示它未运行。最细已完成对象是 3 nm p6/h3 M1200 candidate；它未
accuracy-qualify，minimum qualified M 和 accuracy-qualified frontier 均为 NA。

## 资源语义

用户后续指定的本次运行合同为 workflow warning/hard=224/256 GiB、
hard=274877906944 B、envelope=39600 s、swap0；producer=176/192 GiB、
18000 s；consumer=224/256 GiB、21600 s。shortwave timeout 按 phase
elapsed，producer 完全退出后才启动 consumer；workflow peak=max，不相加。
MemAvailable floor=1869169767220 B。该合同不改写 task.md 原 1.50 TiB
规划历史。

## 2026-09-16：Task041 V3 执行结果 / Response V4 收口

本轮不是“只有文档”的整轮：R1 完成 sequential component 生命周期入口，R2c 完成
A1 owner-row 批量路径与 A2 复数共轭临时量，随后有 R1/R2d/R2e 轻量测试和两场 R2
分侧八项运行；当前 R4 只整理已关闭证据，未新增计算。分侧流程先建 bottom、完成
四项并释放，再建 top 四项；全局方程、RHS、传播因子和原检查未被删除。

| run | source | fixed-eight apply（bottom / top / total） | full service wall | full-tree RSS peak | own result |
|---|---|---:|---:|---:|---|
| R2 baseline | `3ee452ac0adc0c3c88b9610b6446e93a3c02444a` | `790.5143905449659 / 889.7605694371741 / 1680.27495998214 s` | `4015.539370124 s` | `51975606272 B` | bottom/top 各4；reason=2，explicit residual `<=0.01` |
| R2g 唯一 optimized | `376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab` | `592.4704610940535 / 666.3774437108077 / 1258.8479048048612 s` | `3630.563676387 s` | `51796770816 B` | bottom/top 各4；reason=2，explicit residual `<=0.01` |

组件 apply 比为 `0.7491916113647505`，观测减少 `25.0808388635%`；full-service wall
减少 `9.587147784%`。优化峰低 `178835456 B = 170.55078125 MiB`，但不是双侧
内存不增资格；baseline/optimized margin 为 `1245556736/1424392192 B`，硬 cap
仍为 `53221163008 B`。PSS/USS 是稀疏诊断，不替代 RSS；两次 job swap、global 新增
swap 和 pswp 增量均为 `0`，global used 的既有 baseline 为 `8192 B`。

构造 marker 已按两份 consumer raw `markers.jsonl` 的 `(side,event)` 配对：全局
`system_ready` worker wall 为 baseline/optimized `983.0788940798957/1039.0930612850934`；
side `before_build→after_admission` 是侧构造/准入而非全局 setup；factor setup
begin→ready 为 bottom `983.5931301249657→1653.4143726038747`、
`1039.5970036741346→1696.573750832118`，top `2450.2057411340065→3114.250514271902`、
`2293.303577498067→2954.8940188910346`。完整 line/hash 和 outer-origin 对齐见
[setup/recovery](setup_recovery_v3.md) 与 [compact](records/task041_setup_recovery_v3.json)。

两次运行各保留 8 个 response manifest 和 64 个 owned rank shard，每次 shard 总计
`33901312 B`；lifecycle `created_total=2`、simultaneously-live peak=1、每侧释放后
p4/KSP=0。跨 fresh run 的 `132300` 凝聚行缺稳定几何/拓扑/方向/MPC active-row key，
正式状态固定为 `PAIRING_IDENTITY_UNPROVEN`；约 `sqrt(2)` 的按位置差只是未验证编号
诊断，不是 numerical failure 或 pass。

两次 `consumer_summary` 的 physical logical identity 为
`65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4`，resolved logical
identity 为 `95a155334dacf75d30c005338ff689fd676532b49ae392e6fad868d0eee23e51`；两份
public root 均实际保存 `resolved_config.json`，compact 分开记录逻辑字段与文件 SHA。

旧 S1f `53331742720 B > 53221163008 B` 的 `process_tree_rss_limit` 受控停止、旧 H3
`RESOURCE_COMPARISON_INCONCLUSIVE` 以及旧事故均继续保留。新 13.5 nm、完整 5 nm
双侧、full Schur/outer/recovery/official RTA、producer 和新 QEP 均 `not_run`；
`qep_calls=0` 是无新 QEP 调用事实，不等同于完整输出已产生。分侧配对的第二场（唯一
optimized R2g）已完成；整轮实际只有 baseline 一场和这一场 optimized，额外/重复
optimized run `not_run`。预算尚余不等于准入。

R1/R2c 的实现与测试事实、旧负结果和本轮证据入口见 [Response V4](../response_v4.md)、
[setup/recovery](setup_recovery_v3.md)、[compact](records/task041_setup_recovery_v3.json)
和 [test summary](test_summary.md)。ordinary/default 不变；merge 仍按 production
numerical/core、reusable runner/watchdog、checker/benchmark、compact evidence/docs、
research-only、do-not-merge 依赖组说明，负结果文档/compact 保留，临时 orphan sampler、
大型 raw 和未资格化 production promotion 不合入。

<!-- r4b-final-metadata -->
最终 compact：[task041_setup_recovery_v3.json](records/task041_setup_recovery_v3.json)，153382 B，SHA256 `7f5d84e6a2a9a6809d9438bbb6e9444a4ffead9d6272728b394d3346401852df`；R4b 仅完成文档检查，未新增计算。

## 2026-09-18：BAL-H 几何谓词修复与 D1e 准备（Response V6）

旧 D1d 在 top side 几何构造阶段因绝对坐标差的浮点抵消误判 affine，触发 `BAL_H requires affine geometry`；该失败不是 solver、内存、swap 或 MPI 失败。修复提交 `8ad30732a2753b902f5722c6e7c7647365ab0744` 已推送：两条几何使用路径均先减首节点坐标再 contraction，保留 `128*eps*scale` 与有限正 determinant 门。

修复后的 native serial targeted test 为 3 passed，MPI2 为每 rank 3 passed；Ruff check、compileall、diff check 通过，format check 未通过且本轮未扩大 format-only 改动。源码/测试身份和重建复现脚本均记录在 D1e evidence index；旧 D1d 记录保留且不宣称 solver pass。D1e 继续使用 fresh QEP、2nm/p6/h1.5/M1200/MPI8/CPU1--8/math threads1、旧 D1c ledger continuity 和新的实测内存/swap 门。

截至该版，D1e 未 dispatch，fresh QEP 未启动；文档提交后需以最终 source SHA 更新配置、重新做一次 fresh preflight，再按条件批准的精确 argv 单次启动。CPU23 邻项目的真实 worker `402163`/父 `402153` 仅允许在 CPU23、`VmSwap=0`，属于受保护独立作业。
