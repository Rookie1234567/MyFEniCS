# Task39 Review V4：response v5 与最终分类

## 1. 一句话结论

本轮在共享的 5 nm、1°、phi=0、S、p6/h4、MPI8 物理、网格与 external-key identity 下，
分别裁决 Full3D、Hybrid direct 和 exact-side Hybrid iterative；只有两条 Hybrid 方法
使用并共享 M480 selected-mode packet，Full3D 的 M/packet 为 `N/A`。Hybrid direct 自身通过；Hybrid iterative
数值和物理通过但 RSS resource objective 未通过；Full3D 在 MUMPS factor setup 超时，
所以三方法完整比较没有成立。所有新增 exact-side 路径仍是固定 case explicit opt-in，
不是 general production。

## 2. 方法用通俗话说明

Full3D direct 直接在整个有限元系统上做大规模因子分解，内存峰值由 MUMPS setup 主导。
Hybrid direct/iterative 先用横截面模态描述中间区域，再把端口影响接回有限元系统；共享
packet 让 QEP producer 与两个 consumer 分进程，consumer 不重跑 QEP。iterative 路径
进一步只对 bottom/top 局部系统做 exact sparse factor，再用外层 FGMRES 解全局方程。
这换来了低 outer iteration，但需要较多局部 setup 和 action apply，时间并不自动更短。

## 3. 最终分类表

| 证据对象 | 最终分类 | 关键边界 |
|---|---|---|
| Full3D h4 lifecycle | `FULL3D lifecycle NOT_COMPLETED_TIMEOUT_DURING_FACTOR_SETUP` | 21600.036032 s timeout；factor 未 ready，solve/recovery 未运行 |
| Hybrid direct h4/M480 | `HYBRID_DIRECT_H4_OWN_PASS` | own residual/physics/lifecycle pass；Full3D integrated unavailable |
| Hybrid iterative h4 exact-side | `HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL` | 1 outer；五残差和 direct checker pass；RSS 高于 direct |
| h4 integrated physics against Full3D | `HYBRID_H4_INTEGRATED_PHYSICS_NOT_AVAILABLE_FULL3D_INCOMPLETE` | Full3D 没有完整 authority |
| QEP/memory research | `QEP_MEMORY_DIRECTION_NOT_ESTABLISHED` | Q-A owner-only；Q-B trace negative；Q-C/Q-D 未形成完整 Gate |
| 三方法资源比较 | `THREE_METHOD_RESOURCE_COMPARISON_NOT_COMPLETE` | Full3D 没有完成 solve/physics/resource authority |

## 4. h4 结果

| 方法 | reuse wall | cold wall | peak RSS | status |
|---|---:|---:|---:|---|
| Full3D direct | not_run | 21600.036032 watchdog elapsed | 208.315395 GiB | timeout during MUMPS setup |
| Hybrid direct | 6771.478625 s | 8430.560853 s | 93.377006531 GiB | own pass |
| Hybrid iterative | 12357.484926 s | 14016.567154 s | 104.334560394 GiB | numerical/physics pass; resource fail |

共享 packet preparation 为 1659.082228 s、9.478675842 GiB；cold peak 取串行阶段
最大值，不把峰值相加。iterative 相对 direct 的 reuse/cold wall 增幅为
`82.4932% / 66.259%`，RSS 增幅为 `11.734745%`，因此 resource saving 为
`-11.734745%`。Full3D observed stop peak 只允许导出 direct/iterative 的诊断下界
`55.175177% / 49.915099%`，不允许写成完成方法间 saving。

## 5. iterative 数值与生命周期

iterative 的五项 residual 为：

| reported | global | bottom | top | modal |
|---:|---:|---:|---:|---:|
| 5.1673119e-10 | 5.1673072e-10 | 3.2985246e-10 | 4.7629854e-10 | 2.5758782e-10 |

五项均小于 `5e-9`；R/T/A/A_volume 为
`0.733184273689319 / 0.00022009869492546226 / 0.2665956276157555 /
0.2665962726139155`，closure 为 `6.4499816e-7`。相对 direct 的四项绝对差约
`1.50e-12 / 1.15e-14 / 1.51e-12 / 3.33e-13`；selected E/H relative L2 为
`6.09547e-11 / 6.06059e-11`；四类 canonical、normal flux 和 power-weighted
channel comparison 均通过。raw 没有单独保存独立 `12+12` count，因此该字段保持
`not_separately_persisted`；600-key checker 通过。

清理前 bottom/top exact-side factor 为 `1/1`，global factor 为 `0`，nested iterative
KSP 为 `0`，local PREONLY KSP 为 `2`；清理后 bottom/top 为 `0/0`。packet
`qep_calls=0`、`consumer_qep_required=false`，两次 mmap/reference 均释放。

## 6. Q-A/Q-B/Q-C/Q-D 边界

Q-A 已证明 selected packet 是 owner-row 分布；四组 M480 payload 只有
`356,505,600 B`，不能解释为 93–104 GiB solver peak。Q-B 的 beta/polynomial residual
通过，但 trace subspace 约 `4.77e-7`–`7.60e-6`，超过 `1e-10`，因此 one-branch
替代仍未资格。Q-C 的 beta 最大误差约 `8.41e-14`、wall `-8.6204%`，但 factor
lifecycle 为 `1 vs 2` 且 RSS 未测，整体 `NOT_ESTABLISHED`。Q-D 的 M240/320/400
两支 group complete/nested，但没有 operator、RHS、重构或 observable map，所有低 M
physics/resource Gate 都是 `NOT_ESTABLISHED/pass:null`。

## 7. 生产和测试边界

ordinary defaults 未改变；exact-side 只属于固定 case explicit opt-in。没有宣称
production PC、普适 solver 或 0.7 nm PDE 可行。Full repository pytest 为 `not_run`，
没有 CI 声明。本轮只做 evidence/docs 收口，不启动新数值运行。

证据入口：

- [Full3D lifecycle](outcomes/v4_full3d_h4_lifecycle.md)
- [Hybrid direct lifecycle](outcomes/v4_hybrid_direct_h4_lifecycle.md)
- [Hybrid iterative lifecycle](outcomes/v4_hybrid_iterative_h4_exact_side.md)
- [Three-method comparison](outcomes/v4_three_method_comparison.md)
- [QEP/memory study](outcomes/v4_qep_m_memory_study.md)
- [V4 iterative compact record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_iterative_exact_side_v1.json)
