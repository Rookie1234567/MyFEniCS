# Task041 V6：13.5 nm 回归与 5 nm fixed-eight 配对结果

## 范围与结论

本记录收束 F1/F2/F3a 与四次 5 nm fixed-eight 尝试。5 nm 配对在每侧复用同一 mesh、MPC、layout 和 RHS，先运行 full，再确认 full 因子/矩阵/solver 销毁，随后运行 cell-condensed；两后端按每侧顺序构建，不并存两套因子。本轮 8 个 RHS 共完成 16 次主响应。它是组件级后端配对探针，不是完整 5 nm consumer、RTA 或 24 小时求解。

**结果为数值 Gate 未通过。** 8 对中 bottom 4/4 通过，top 2/4 通过；top formal column 12 与 493 的 `e_x`、`e_A` 均超过原 `1e-8` 门。释放、同布局、输入不变与 side residual 门通过，不能覆盖这两项配对失败。

## F1、F2 与 13.5 nm F3a

| 阶段 | 证据与结果 | 限制 |
|---|---|---|
| F1 transfer 修复线 | 相关提交 `b518fb33dbff523bee8c13d31345025f183d40d5` 在 transfer 加入 `entity_closure` 与 `reference_entity_trace_v1`，用 Basix 实体支撑构造边/面传递，而不是上调数值阈值。F1 保留旧 transfer 负结果 `1.3116919128020489e-11 > 1e-11`，原 A4 `6.795828778707217e-11 <=1e-10` | 旧 R3i3 run summary 未自带 source SHA；不把后续源码身份追认为原始 summary 字段，也不写成新方法通过。F1c/F1d compact：[Basix 支撑分析](../../../results/task041_review_v6_transfer_and_5nm_24h/f1a_mpi8_transfer_diagnostic_20260922/run_20260922T005426.371809368Z/f1d_basix_support_compact_v3.json)、[F1c/F1d 离线摘要](../../../results/task041_review_v6_transfer_and_5nm_24h/f1a_mpi8_transfer_diagnostic_20260922/run_20260922T005426.371809368Z/f1c_f1d_offline_compact.json) |
| F2 MPI8 tiny-FE | 获批节点 `test_347_task041_balh_mpi8.py::test_task041_h1e_mpi8_side_inverse_old_new_q_pc_and_apply` 通过；full→释放→cell-condensed backend equivalence | source 关联来自主控审核配置/报告；旧 `run_20260923T002941Z/summary.json` 未自带 `source_sha`。这是 tiny-FE backend equivalence，不是 5 nm 数值通过 |
| F3a 13.5 nm 显式 cell-condensed | source `a330e30aa87f53aa9b13980551fa87716922e982`；runroot [`20260923T014600.066882Z`](../../../results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8_cell_condensed/task041_13p5nm_p6h10_m120_mpi8_cell_condensed__hybrid_iterative__mpi8__M120/20260923T014600.066882Z)。五项 true residual：reported `2.0407563274601412e-11`、global `2.0407682658500268e-11`、bottom `4.774538782631132e-11`、modal `6.605548156027185e-13`、top `1.498789504457955e-11`，均通过 | `consumer_summary.gates.pass=true`；`integrated_checker.status=not_available`, `role=full3d_secondary_not_run`, `pass=false`。另有旧 metadata `time_stop_policy.scope=registered_2nm_case` 与 13.5 nm model_id 不符 |

F3a 的 R/T/A 为 `0.36562578909448007 / 0.012990632409137788 / 0.6213835784963821`，`A_volume=0.6213835794980791`，closure `1.001696947611208e-9`。与既有 H2 exact consumer 的坐标、场、observable、canonical、external 80 channels 和 normal flux 数值比较均通过；差值：R `2.138844656940364e-13`、T `1.0846705478240182e-13`、A_balance `1.0536016503692736e-13`、A_volume `3.03146396873899e-12`。H2 总 checker 仍为 `pass=false`，原因是旧资源合同拒绝 V6 的 ledger/time-stop/producer-inherited 口径（candidate `batch_compute_wall.pass=false`、`limits_match_frozen_contract=false`、producer phase resource false），不是数值向量失败。V6 独立资源复核：consumer authority/tree RSS `9,220,177,920 B`，cgroup history peak `18,133,061,632 B`；最小 host MemAvailable `2,137,279,156,224 B` 高于 `412,316,860,416 B` reserve；swap/pswp delta 0。复用 producer packet，不重算 QEP。

## 5 nm 四次尝试

| 尝试 | source / unit / public run | finalizer charge；authority peak 与 finalizer | 终止分类 |
|---|---|---:|---|
| 1 | `d2a055ffefd211663b4e271032bcfac5856f8404`；`task041-f3c3-5nm-fixed8-pair-20260923T064840Z.service`；`20260923T070526.132033Z` | `2388.163648714 s`；`38,426,513,408 B`；[原 finalizer](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_fixed8_pair_20260923T064840Z/finalizer/finalizer_summary.json) | release caller 从返回记录读不到已保存的 post-destroy diagnostics；旧 marker 显示各销毁计数 1、live 0、release gate true。实现接线错误 |
| 2 | `cf0938c2cc0831bd4d54d6a833ef6ea53d5314df`；`task041-f3c3-5nm-fixed8-pair-releasefix-r1.service`；`20260923T084835.095176Z` | `2421.446287095 s`；`44,938,231,808 B`；[原 finalizer](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_fixed8_pair_releasefix_r1_20260923/finalizer/finalizer_summary.json) | `P4CondensedExactFactor` 没有 `.matrix` 属性；实现接口错误 |
| 3 | `d8e9e0169e0c74ab2e2f7746b621abb94d2164f4`；`task041-f3c3-5nm-fixed8-pair-matrixfix-r1.service`；`20260923T100119.032031Z` | `3501.209503633 s`；`53,276,790,784 B`；[原 finalizer](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_fixed8_pair_matrixfix_r1_20260923/finalizer/finalizer_summary.json) | 旧 cap `53,221,163,008 B` 下 authority peak 超限，资源 Gate 停止。bottom pair 只在内存形成、没有持久 pair JSON；不将其当作可审核数值结果 |
| 4 | `a4ccd850faaabbfb13caf98153cfbf65fa4fe0a9`；`task041-f3c3-5nm-fixed8-pair-cap64-r1.service`；Invocation `eeb07914bbf5481caf3bc0b31d6223ee`；public run [`20260923T115515.717201Z`](../../../results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260923T115515.717201Z) | `5069.064609306 s`；`65,674,952,704 B`；[原 finalizer](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_fixed8_pair_cap64_r1_20260923/finalizer/finalizer_summary.json) | 本次用户限定 fixed-eight 的 64 GiB cap 下完成 16 响应，但 top 两对数值 Gate 失败；不是旧 49.57 GiB 门通过，也不改变其它 case 的 cap |

以上 charge 来自各自 finalizer。第 4 场 outer phase wall 为 `5068.415153590991 s`，workflow wall 为 `5068.415249351994 s`；finalizer 的 `5069.064609306 s` 是账本 charge，三种口径分别保留、不互换。

第 4 次同一 RHS 的详细记录如下。`e_x` 是 full 与 condensed 响应向量的相对差，`e_A` 是原算子作用到两响应后结果的相对差；它们是后端配对差，不是最终场对真解的误差。`full/condensed iter·s` 来自两后端逐 RHS apply audit；`last P4` 两列是各 manifest 中 `metadata.p4_factor_audit.last_solve` 的**最后一次 P4 调用**快照，不能解释为该 RHS 所有 P4 调用的最大值。

| side / branch / formal column | full iter·s | condensed iter·s | side residual | `e_x` | `e_A` | condensed last P4 physical / relative residual | refine |
|---|---:|---:|---:|---:|---:|---:|---:|
| bottom / positive / 207 | 17 · 72.084033 | 17 · 72.706915 | 0.008369287 | 1.002917e-12 | 6.802212e-13 | 1.343329e-13 / 1.343311e-13 | 0 |
| bottom / positive / 15 | 49 · 207.987782 | 49 · 209.546302 | 0.008589299 | 1.272654e-11 | 2.665771e-11 | 1.679230e-13 / 1.679206e-13 | 0 |
| bottom / negative / 671 | 17 · 72.136200 | 17 · 72.667637 | 0.009208186 | 1.272603e-12 | 1.075758e-12 | 1.435369e-13 / 1.435364e-13 | 0 |
| bottom / negative / 493 | 49 · 208.499575 | 49 · 209.579755 | 0.008841676 | 1.401676e-11 | 2.985109e-11 | 1.732160e-13 / 1.732136e-13 | 0 |
| top / positive / 310 | 17 · 71.952398 | 17 · 69.898061 | 0.009202848 | 1.546191e-12 | 2.921251e-13 | 1.215132e-13 / 1.167707e-13 | 0 |
| top / positive / 12 | 57 · 240.186948 | 57 · 234.350630 | 0.009387047 | **2.361490e-8** | **6.410084e-8** | 5.236382e-12 / 2.777617e-12 | 0 |
| top / negative / 666 | 17 · 71.686585 | 17 · 69.971046 | 0.009453705 | 9.200606e-12 | 4.409973e-12 | 2.684081e-12 / 1.848853e-12 | 0 |
| top / negative / 493 | 57 · 240.157573 | 57 · 234.245956 | 0.009387047 | **2.584983e-8** | **7.016739e-8** | 3.779368e-12 / 2.489565e-12 | 0 |

所有 side residual 小于 `0.01`。两条失败 RHS 的 condensed last-apply P4 物理/代数残差仍低于 P4 `1e-10` 门，且 refinement 为0；这些事实不解除 full 与 condensed 之间的响应差失败，也不定位其共同成因。两失败列的共同路径证据仅为均属 top、均 57 iterations、均触发 `1e-8` 配对门失败；现有数据不足以判定根因。

### 生命周期、资源、service 与费用

- 顺序为 `full → destroy → cell_condensed`；同 side/layout/RHS 身份、输入未变，销毁门通过。full 的八个 P4 A4 检查最大 `2.433735377048887e-12`，p4 refinement 均为0。
- 八 RHS full apply 合计 `1185.079661994 s`，condensed `1173.609554288 s`，派生差约 `0.97%`；setup rank-max：bottom full/condensed `656.4925441849919/160.87149969600432 s`，top `669.5988162059948/166.7682739209995 s`。由于配对数值门失败，不授予性能资格。
- full 八份 per-response manifest 的 P4 `last_solve` A4 快照中最大值为 `2.433735377048887e-12`，八个快照的 refinement 均为0；这不是所有 full P4 调用全过程的最大值。condensed 八份 manifest 的 `last_solve` 快照均通过，physical-relative 最大 `5.23638213224212e-12`、relative 最大 `2.77761696352628e-12`、refinement 均为0；同样只覆盖每个 RHS 最后一次 P4 调用。16 份小 manifest 的字节数和 SHA 见 compact v2，不读取大型场数组。
- 本次特例资源合同：hard cap `68,719,476,736 B`、warning `61,847,529,062 B`、host reserve `412,316,860,416 B`。authority 按 `max(process-tree RSS, dedicated cgroup current)`；authority/tree RSS peak `65,674,952,704 B`，dedicated cgroup history peak `63,524,495,360 B`。warning 已越过，hard cap 未越过；outer summary 记录 host 最低 MemAvailable `2,079,507,968,000 B`；swap/pswp delta 0，进程组清理完成。该 64 GiB 授权只适用于这次 fixed-eight 配对。
- Finalizer `failed/service_boundary_failure`，service exit status 3；`.checks.closed_artifacts_hashed`, `ledger_written`, `post_cgroup_finalizer_only`, `pre_exit_members_clean` 均 true，而 `public_result_completed=false`、`service_terminal_normal=false`。因此不是“finalizer 未运行”，而是 public 结果失败后 finalizer 已执行并记账。
- V5 ledger 为24 entries，本场 ID 唯一匹配1次；本场 charge `5069.064609306 s`，旧总额 `18767.174425671998 s`，新总额 `23836.239034977996 s`。不再写账或重复收费。

## 测试与覆盖边界

F3c4 两个轻量 mock 模块最终 `99 passed`, `rc=0`，父侧 wall 约 `11.40 s`；首次失败记录保留，原因是测试期望把 formal 13.5 nm cap误写为9 GiB、以及 fixture 用运行时覆盖 cap 生成历史 RHS manifest，随后仅修复测试期望/fixture，生产 validator 未变。没有重跑 full repository tests、PDE、QEP、F3a 或新的 ABI。

F3a 的 H2 对照仍应描述为“数值全向量通过；旧 H2 资源合同不可直接移植”。Full3D secondary、完整 5 nm consumer、RTA、EH、24 小时完成均 `not_run`/`not_assessed`。本次文档收口不改源码或阈值。

机器可读的身份、逐行结果、资源、finalizer、费用和 16 份小 manifest 的 SHA/字节数见[record](records/task041_v6_transfer_5nm_24h.json)及 [ignored compact v2](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/preparation/f3c3_cap64_r1_20260923/cap64_r1_postmortem_compact_v2.json)。compact v2 SHA-256：`9251e772de18796d2c55ea5cf641aaf650760390d436204c0f477cfabecff92a`；v1 与所有原始失败证据保留。
