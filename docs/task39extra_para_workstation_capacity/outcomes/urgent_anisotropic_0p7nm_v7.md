# V7 紧急 0.7 nm 各向异性准确 p4 求解记录

更新时点：2026-10-12，U0 已完成，U1 实现完成，联合 pure/接口 58/58 通过，guard 纯测试 15/15 通过。新正式 run 尚未启动。

| 字段 | 启动前合同 / 已有实测 | 口径 |
|---|---|---|
| Review | `5f8356bbe3f751b1530bc174b3bb6b19096d1242` | 本轮授权文档提交 |
| 执行分支 | `task39extra_para_workstation_capacity` | canonical worktree，不修改其他任务或 master |
| 新模型 | 0.7 nm Si，50×25 nm 周期，17×25×120 nm 光栅；1°/0°/s | 与 V7 指定物理一致；无连续精度资格 |
| 网格 | `[100,2,234]`，预期 46800 hexahedra | 尚待正式 setup 实际检查，不是已生成网格 |
| 方程与修正 | 完整三维 p6；准确 p4 单元凝聚 MUMPS；BAL_H、FGMRES32/max2048 | full_solve，无 16 步计划停止 |
| active DtN | n=0、m=-142…0、上下×s/p=572；父 metadata=32060，q160 | p6/p4 同清单；FE 装配前筛选 |
| RSS / 线程 | hard=1950000000000 B；MPI1/math1、CPU9/24、interleave0–1 | 实际 RSS Gate；PSS/USS off，swap 观察 |
| 新场时间 / RSS / 残差 / RTA | `NOT_RUN` | 尚无结果或容量保证 |
| 完整 DtN / 精度 | `FULL_DTN_NOT_VERIFIED / AUTHORITY_LIMITED` | 不把 A6_n0 等同 A6_full |

旧 N0 p3 run `20261012T065422.607789Z` 在 `retained_forms_compiled/setup` 被本轮优先级切换受控结束。workflow `11131.505397025961 s`，采样整树 RSS 峰 `333521260544 B`，任务 swap 峰 0，exit1/后代清场；未完成 factor/KSP。旧缓存保留，但不用于新网格。原始字段、信号、SHA 和读取范围见[priority switch](records/v7_priority_switch.json)。

新场的实际 mesh/port/局部凝聚/H6/symbolic/numeric/QA/KSP/恢复/检查/输出、每步和两次 C 分项将在运行后按原始阶段边界列出。父子计时不相加，数组载荷、backend 分配和同时整树 RSS 分开。此文目前不提供完成时间或内存外推。

实现与结果范围见 [Response V7](../response_v7.md)；旧记录继续保留在[历史总账](summary.md)。
