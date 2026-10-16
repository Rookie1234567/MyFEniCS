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
| 状态 | 任务书已建立，Codex尚需工作站预检、适配与执行；无新PDE结果 |

禁止沿用旧N0/572对称约简：新方柱沿x/y都变化。旧0.7 nm结果、RCWA比较和p4返回故障只作历史，不当本模型验收标准。全部新结果/response只写本分支；不改父任务、Hybrid或master。
