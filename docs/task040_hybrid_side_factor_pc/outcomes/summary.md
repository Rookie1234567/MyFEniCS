# Task040 结果摘要

Task040 研究的是：在冻结 Hybrid 方程、裸算子 `F`、物理输入和 M480 不变时，能否用较小的
side inverse（侧向逆作用）替代完整的 exact side factor。通俗地说，side inverse 试图只
在人工截面附近保留必要的信息，以减少内存；但它必须先证明传递方向正确，再谈完整 Hybrid。
本页把已完成的 T40-3、V1-1 与 V1-2 Run B 分开登记，不能把组件峰值当作完整工作流节省。

## 阶段总表

| 阶段 | 作用范围 | 状态 | 关键事实 |
|---|---|---|---|
| T40-0 | inherited audit | completed | 冻结身份、ABI、基线与禁止路线已绑定 |
| T40-1/T40-2 | F/action identity、人工界面阻抗与 MPI tiny identity | completed | `q=-i beta`、两界面 mass/support、bare `F` unchanged |
| T40-3 | bottom bare-F one-apply transmission oracle | controlled numerical negative | `TRANSMISSION_MECHANISM_FAIL`；worst rho `28.316064601533686` |
| V1-1 | fixed scalar transmission right-FGMRES screen | controlled numerical negative | `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL`；五个 `r16 >= 0.9`，32 not run |
| V1-2 | exact interface Schur/Steklov sampled audit | controlled resource stop | `45.05752944946289 GiB` hard stop；仅到 exact oracle ready/release，未完成数值资格 |
| V1-3 | conditional projected-exact transmission | setup_started_but_not_ready | setup 已开始但未到 `projected_ready`；resource stop，numerical capacity `NOT_EVALUATED` |
| V1-4 | analytic mode-aware transmission | not_run_by_gate | V1-3 setup 未到 ready，前置 Gate 未完成 |
| V1-5 | conditional bounded-patch Level B | not_run_by_gate | V1-2/V1-3 前置 Gate 未完成 |
| V1-6 | bottom/top/both/full Hybrid | not_run_by_gate | V1-5 未运行 |
| V1-7 | conditional h3 scalability probe | not_run_by_gate | V1-6 未运行 |
| V1-8 | evidence/docs closeout | completed | 本页、compact record 与 `response_v2.md` 已完成并通过轻量合同检查 |
| V2-A1 | interface-Schur packet producer | completed_diagnostic_oracle | packet 完整、独立 checker 通过；这是诊断/oracle authority，不是 scalable side inverse 或 V2-B 结果 |

## 正式身份与最新 Run B 资源

| 字段 | 值 |
|---|---|
| source SHA | `16ecba568be901325e53c3652aa10bb432de5a6b` |
| MPI / threads | `8 / 1` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| V1-2 probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| exact-spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| formal root | `results/task040_v1_2_v1_3_run_b_mpi8_16ecba56` |
| watchdog termination | `absolute_memory_limit`; process group SIGTERM；未需 SIGKILL |
| hard stop / peak RSS | `48,318,382,080 B` / `48,380,153,856 B` |
| peak RSS | `45.05752944946289 GiB`；约高于 hard stop `61,771,776 B` |
| peak swap / status readability | `0 B / all_status_readable=true` |
| wall口径 | process-sample `1485.4694942460628 s` |

最新 root 到达 `system_ready`、两个 interface mass ready、`projection_begin`、
`v1_2_exact_oracle_ready` 和 `v1_2_exact_oracle_released`。exact oracle 的 factor count
是 `3 -> 0`，lower/upper mode count 为 `296/480`。随后代码已进入 V1-3 projected
transmission 的 setup，RSS 继续增长，但没有发出 `v1_3_projected_ready` marker，也没有
`run_summary.json`、per-probe contractions、rank/condition 或 one-apply/FGMRES checkpoint。
因此 V1-2 仍是 `not_qualified_due_resource_stop`，V1-3 是
`setup_started_but_not_ready`、同样因资源停止未资格化；V1-3 numerical capacity 为
`NOT_EVALUATED`，不能分类为 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。

## 已完成数值结果与资源边界

| 路线 | 结果 | process-tree peak | wall | 状态 |
|---|---|---:|---:|---|
| T40-3 bottom bare-F component | 五个非零 rho 全部大于 1；worst `28.316064601533686` | `28.333576202392578 GiB` | `660.6481867840048 s` | `TRANSMISSION_MECHANISM_FAIL` |
| V1-1 scalar component | 五个 `r16 >= 0.9`；32 not run | `27.790115356445312 GiB` | `669.4473022361053 s` | `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL` |
| V1-2 Run B | exact oracle ready/released；数值 probe 未序列化 | `45.05752944946289 GiB` | `1485.4694942460628 s` | `V1_2_RESOURCE_HARD_STOP_BEFORE_NUMERICAL_QUALIFICATION` |
| inherited direct full workflow | matched reference | `93.377006531 GiB` | inherited | reference |
| inherited exact-side iterative full workflow | residual/physics/lifecycle pass | `80.025856018 GiB` | inherited | reference |

28.333576202392578 GiB、27.790115356445312 GiB 和 45.05752944946289 GiB 都是各自
组件或失败尝试的 process-tree 峰值，不是完整 workflow saving tier。PSS/USS 在最新 raw
中没有记录，不能从 RSS 推算。最新 hard stop 也不能说明 projected transmission 的数学
机制失败：它只说明同一进程的资源生命周期在完成 exact oracle 后仍未能在安全线内完成后续阶段。

## 生命周期与停止解释

`v1_2_exact_oracle_ready` 证明三个 exact oracle factor 已构造；紧接的
`v1_2_exact_oracle_released` 证明其 recorded factor count 已回到 0。它不等于 projected
transmission 已经作用或通过。PETSc、MPI、allocator 和后续 trace/projection 对象可能仍保留
进程 RSS；对象逻辑销毁与操作系统立即回收页不是同一件事，所以 factor count 变为 0 后，
后续构造仍可能继续推高 RSS。

## 依赖阶段

V1-4 至 V1-7、Level B、top、full Hybrid 和 h3/0.7 nm scaling 全部
`not_run_by_gate`；V1-3 仅有未完成的 setup，numerical capacity 未评估。当前证据不能判断 bounded local patch 是否失败、是否必须引入 coarse
information，也不能判断完整 Hybrid 或 0.7 nm feasibility。若未来继续，首先应审查阶段分进程、
持久化 V1-2 packet 或有证据的 collective heap trim；本轮未实现这些方案。

## 选择性复用边界

| 类别 | 内容 | 结论 |
|---|---|---|
| reusable candidate | package-invocation watchdog regression、interface support/mass audit、factor owner cleanup | 可独立审阅；未改变 ordinary defaults |
| research-only | 三个 cross-section exact oracle、固定一阶 impedance、V1-2 resource-stop evidence | 保留证据；不是 scalable side inverse |
| do-not-promote | V1-2 未资格化的 projected route、T40-3 action、full Hybrid、0.7 nm capacity claim | 禁止提升 |

完整 raw 和日志留在 ignored `results/`；轻量证据见
[V1-2 resource-stop compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_v1_3_run_b_resource_stop_v1.json)。

## V2-A1 producer 结果

V2-A1 使用独立 producer 进程在同一冻结 5nm/1deg/phi0/S/p6h4/M480/MPI8 配置下完成
hash-bound interface-Schur packet。它的作用是把人工截面的精确信息整理成后续 consumer
可以读取的诊断包；它没有运行 PDE、QEP、FGMRES，也没有构造 V1-3 projected factor。

| 项目 | 实际结果 |
|---|---|
| producer source / checker-fix SHA | `942c43881e4162085348c48b09c79fbbdac18cd9` / `bd70ab98009de2a2b45561793be6418a6a9bfcc8` |
| formal root | `results/task040_v2_interface_packet_producer_mpi8_942c4388` |
| exit / wall | natural exit, rc0 / `1202.5501016210765 s` |
| peak / preferred / hard | `30,823,858,176 B = 28.706954956054688 GiB` / `<=45 GiB` pass / `55 GiB` 未触发 |
| swap / A2 fallback | `0 B` / `not_run_not_needed` |
| packet | 34 files, 653,804,117 B；24 owner-row shards |
| Gamma rows / modal spans | `7560/15120/7560` / `296/776/480` |
| Gram rank / condition | `296/776/480` / `187.9352369709664`, `1075856.58741676`, `113913.61949721041` |
| reports | physical/interface/middle/complement `15/8/8/4` |
| lifecycle | exact oracle `3 -> 0`；full/global/nested `0/0/0` |

首次 checker 失败是 schema implementation failure：真实 physical report 没有 `finite` marker，
但其显式数值字段和 contractions 全部 finite；旧 checker 错误要求该 marker。修复后
serial/MPI2/MPI4 的 test306 均为 `6/6 passed`，fresh checker `rc0`。producer packet、
历史失败输出和 V1 resource stop 均保留，未被改写为算法负结果。

本次 packet 只证明 diagnostic/oracle authority 和可复核的 owner-row 数据包完成；
`max_projected_exact_relative=1.0281892054707484` 不是 V2-B Gate。V2-B consumer 仍为
`pending`，当前没有新的 full-workflow saving tier；完整 workflow baseline 仍以
`93.377006531 GiB` direct 和 `80.025856018 GiB` exact-side iterative 为准。详细身份、
raw hashes 和 checker 输出见
[V2-A1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_interface_schur_packet_producer_v1.json)
与
[V2-A1 producer outcome](interface_schur_packet_producer.md)。
