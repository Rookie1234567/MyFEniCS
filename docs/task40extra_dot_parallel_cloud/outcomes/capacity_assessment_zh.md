# 容量与完整求解优先级

目标是可用的 0.7 nm 目标模型解，而非只缩短局部矩阵生成。2 TB 按十进制 10^12 B/TB；历史 48 小时目标适用日期仍待确认。下列计数不含 PDE，也没有实测大模型 RSS。

## 关键证据

| 项目 | 数值、数据身份 | 含义与限制 |
|---|---|---|
| 原 G1 workflow / KSP / setup | 父实测 4097.994 / 3135.913 / 908.009 s | KSP 占 76.523%；其他不变、全部 setup 消失的 derived 上限 1.28464 倍 |
| 历史 2 nm p4 MUMPS used / allocated | 父历史实测 916.713 / 1091.654 GB | 不与 RSS 相加；其矩形无缺口几何不同，旧实现与运行状态不同，不能作为本目标预测 |
| 单原始类型 p6 核心载荷 | derived 12,446,784 B | complex LU 450²、两个 450×432 块和 Schur 432²；不含端口、pivot、cache、全局因子或工作向量 |
| 假设恢复带缺口 50×25×140 nm，h=0.518519 nm | derived 1,369,452 cells，211 raw 材料+精确宽度键 | 不是已确认目标器件；未创建 DOLFINx 拓扑/方向，实际 factor 类数 unknown |
| 同假设一个方向/每 raw 类型 | derived 核心载荷 2.626271 GB | 仅条件形状载荷，不是实际分配、同时 RSS 或容量通过 |
| 同假设每 cell 独占全套核心 | derived 17.045273 TB | 仅无共享最坏表示；不能说此结构化几何必需 17 TB |

## 小型计数实验

重用冻结源码的有理分段，再转换 double 并取相邻轴差；G0/G1 坐标与历史 geometry_plan 完全一致。材料标签仍区分 air/substrate/grating，没有把 Si 标签合并来压低数量。

| 几何 | 单元数 | 原始材料+metric 类型数 | 方向类型 |
|---|---:|---:|---|
| G0 | 336 | 33 | unknown |
| G1 | 880 | 30 | unknown |
| E1，q1.25 | 760 | 156 | unknown |
| E2，q1.5 | 880 | 156 | unknown |
| 假设恢复带缺口原尺寸 | 1,369,452 | 211 | unknown |

数字是文档几何的派生计数，不是完整有限元库存。计数程序原运行约 0.475 s；发布路径调整后复跑得到相同计数。没有建立全局因子或目标 connectivity。原始 140 KB histogram 可从脚本重建；[compact record](records/exact_metric_inventory_compact.json)保留 hash。

## 决策

保留结构化精确共享路线，优先核对真实 orientation/factor 共享、端口和同时工作区，再判断是否需要改细空间表示。最重要的已知大规模风险仍是全域 p4 纠错因子及其每步成本。不能因为局部模板容易提速便把它当目标架构已完成；也不能把条件最坏载荷当成所有方法都不可能的证据。没有新的正证据前，不重做旧低内存强逆、42 宏块或已慢的端口流式扫描。

来源：[原 G1](../../task40extra_0p7nm_engineering/response_v2.md)、[Review V2](../../task40extra_0p7nm_engineering/review_report_v2.md)、[旧 2 nm 冻结账本](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/f2_running_handoff_20260928.md)、[其实际输入](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/input/task39extra_para_workstation_capacity/v5_node1_2nm_p6h1p5_q4.dat)。[另一个0.525nm条件场景](records/conditional_payloads.json)只是形状算术，与本次0.518519nm精确计数不能混称同一模型。
