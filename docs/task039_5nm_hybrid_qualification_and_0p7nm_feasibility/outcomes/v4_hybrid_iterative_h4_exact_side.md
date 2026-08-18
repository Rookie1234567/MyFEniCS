# V4 h4 Hybrid iterative exact-side 结果

## 结论

本结果是固定 5 nm、1° grazing、phi=0、S、p6/h4、M480、MPI8 的显式 opt-in
Hybrid iterative case。它把全局方程用 matrix-free right FGMRES 施加；bottom/top
各有一个局部 exact-side 稀疏直接因子，动态 DtN Woodbury 负责端口模态耦合。通俗地说，
它用两个小的局部直接解换取全局外层只需一次更新，但这不等于总计算只做了一次局部解，
也不等于它是适用于任意模型的 production PC。

最终分类为：

`HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL`

数值、恢复和与 h4 Hybrid direct 的离线 integrated comparison 均通过；资源目标未通过，
因为 iterative RSS 高于 direct baseline。formal 外层 `exit_status=4` 是这个 resource
objective 未满足的结果，不是数值失败，也不是 watchdog hard-stop 或 swap 终止。

## 固定身份与 packet

| 项目 | 绑定值 | 数据身份 |
|---|---|---|
| 物理/离散 | 5 nm、1°、phi=0、S、p6/h4、M480、MPI8 | measured/input |
| iterative source | `c2829b7e95ea995adcafc115836def1e915f1666` | measured/provenance |
| packet producer source | `eaad0f942f014b65474ac57e3d5e561316489f20` | measured/provenance |
| packet manifest SHA | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` | measured |
| canonical identity SHA | `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` | measured |
| external keys | 600，动态枚举，key hash `ba431ec6...` | measured |
| consumer QEP | `qep_calls=0`，`consumer_qep_required=false` | measured |
| packet lifecycle | mmap/reference 均释放 | measured |
| qualification scope | `task039_v4_p6h4_m480_1deg_s`，explicit opt-in | measured/contract |

Iterative 和 direct 消费同一 manifest、canonical identity 和 external-key identity；method
identity 没有被伪装成 direct。完整输入、run manifest、consumer、checkpoint 和 posthoc
comparison 的 hash 见 [iterative compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_iterative_exact_side_v1.json)。

## 数值与物理 Gate

| 指标 | iterative measured | 限值/比较 | 结果 |
|---|---:|---:|---|
| outer iterations | 1 | fixed max 4000 | pass |
| reported/global/bottom/top/modal residual | `5.1673119e-10 / 5.1673072e-10 / 3.2985246e-10 / 4.7629854e-10 / 2.5758782e-10` | each `<=5e-9` | pass |
| R / T / A_balance / A_volume | `0.733184273689319 / 0.00022009869492546226 / 0.2665956276157555 / 0.2665962726139155` | finite | pass |
| energy closure | `6.4499816e-7` | `<=1e-5` | pass |
| projection | `2.5758782e-10` | `<=1e-8` | pass |
| exact traction bottom/top | `3.2985246e-10 / 4.7629854e-10` | each `<=1e-8` | pass |

与 h4 Hybrid direct 的 R/T/A/A_volume 绝对差为 `1.50e-12 / 1.15e-14 /
1.51e-12 / 3.33e-13`。selected E/H relative L2 为 `6.09547e-11 /
6.06059e-11`；normal-flux comparison 为 `2.22507e-12`，power-weighted channel
comparison 为 `2.22127e-12`。四套 canonical active-trace/full-FE comparison 均通过，最大
relative L2 约 `1.07942e-9`，限值为 `1e-5`。

posthoc checker 报告 600-key set exact、full channel pass 和 power-weighted pass。raw
没有单独持久化一个独立的 `12+12` count，因此这里写
`independent_12_plus_12_count=not_separately_persisted`，不把它补写成不存在的计数。

## 因子与清理生命周期

| 生命周期字段 | before cleanup | after cleanup |
|---|---:|---:|
| global direct factor | 0 | 0 |
| bottom/top exact-side direct factor | 1 / 1 | 0 / 0 |
| local PREONLY KSP | 2 | — |
| nested iterative KSP | 0 | 0 |
| collective cleanup | — | `true` |

全局没有 direct factor；两个局部 side factor 是 exact-side 资格的核心。清理阶段还记录
collective PETSc cleanup 和 allocator trim，不能把 checkpoint 的 pre-destroy inventory
误读成最终仍存活对象。

## 时间与资源

| 方法/阶段 | reuse wall (s) | cold wall (s) | process-tree peak RSS | 数据身份 |
|---|---:|---:|---:|---|
| packet preparation | — | 1659.082228 | 9.478675842 GiB | measured |
| Hybrid direct | 6771.478625 | 8430.560853 | 93.377006531 GiB | measured |
| Hybrid iterative | 12357.484926 | 14016.567154 | 104.334560394 GiB | measured |

这里 cold 是串行阶段的 `packet preparation + method-specific run`，峰值取阶段最大值，
不把不同阶段的 RSS 相加。iterative 相对 direct 的 reuse wall 慢 `82.4932%`，cold wall
慢 `66.259%`；RSS 多 `11.734745%`，所以 resource saving 为 `-11.734745%`。swap 为
0；iterative PSS/USS 在 parent telemetry 中未单独测量。

Full3D h4 在 MUMPS factor setup 阶段 timeout，不能作为完成的同网格 baseline。相对于
该未完成 run 的 observed stop peak，direct/iterative 的 `55.175177% / 49.915099%`
只能叫诊断下界，不能称为完成方法间节省。

## 生产边界

ordinary ILU0/two-pass defaults、输入 schema 和其他 h5/h10 行为不变。exact-side 只对
这个固定 h4/M480/1° case 显式 opt-in；不能称 general production、不能外推到任意 mesh、
M、材料或角度。Full3D integrated status 继续是
`HYBRID_H4_INTEGRATED_PHYSICS_NOT_AVAILABLE_FULL3D_INCOMPLETE`。
