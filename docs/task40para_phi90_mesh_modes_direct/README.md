# Task40para｜phi90方向网格与模态截断

**执行分支：`task40para_phi90_mesh_modes_direct`。**

完整执行合同见[task.md](task.md)。本任务从父分支`task39extra_para_workstation_capacity@922466da9d7faff408cbb47b7882d179320bdc44`派生，仅继承代码，不继承旧物理/精度资格。分支来源见[branch_provenance.json](branch_provenance.json)。

| 项目 | 本任务固定选择 |
|---|---|
| 新几何 | x/y均50 nm周期；中心Si方柱17×20×120 nm；z=-10…130 nm |
| 入射 | 掠角1°，方位90°，s偏振 |
| 方法 | 三维p6 H(curl)，装配时单元凝聚，p6 trace/port MUMPS直接LU；不用p4/p3修正 |
| 顺序 | 13.5 nm方向网格 -> 5 nm方向网格 -> 5 nm二维BOX2截断对照 -> 有依据的0.7 nm完整计算 |
| 13.5 nm起点 | p6目标h10，材料拟合后预计504单元；是否足够由对照决定 |
| 5 nm起点 | p6目标h4，预计7020单元；先固定reference模式研究网格 |
| 三阶候选 | m,n各-2…2，25对级次；上下端口/两偏振，传播与倏逝分类保留 |
| 资源 | 0.7 nm实测同期整树RSS<=1.8e12 B；13.5/5 nm无用户固定cap，但保留主机安全 |
| 状态 | D13 的 B/X/Y/Z、Y2/Y3、X2 与 H15 B/X/Y/Z/YZ480 均有历史结果；Y2/Y3 提供同策略 y 对照。用户 2026-10-18 授权续行，当前下一场为从 Y2 实际 z 轴逐段二分的 Z2 `[6,24,28]` / 4032-cell；启动前的 source/profile/input/tests 正在冻结。full DtN 与 canonical 方柱侧壁 trace 仍未验证 |

禁止沿用旧N0/572对称约简：新方柱沿x/y都变化。旧0.7 nm结果、RCWA比较和p4返回故障只作历史，不当本模型验收标准。全部新结果/response只写本分支；不改父任务、Hybrid或master。

当前 D13 比较与限制见[outcomes summary](outcomes/summary.md)及[relative-only Y2 response](outcomes/response_d13_relative_cutoff_followup.md)。同策略 Y3 已完成；续行授权、Z2 精确轴计划和后续侧壁取证边界见[2026-10-18 continuation response](outcomes/response_d13_z2_continuation_authorized_20261018.md)。
