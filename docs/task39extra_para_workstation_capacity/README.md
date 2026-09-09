# Task39extra_para：工作站迁移与短波容量测试

本目录的唯一初始执行合同是 [task.md](task.md)。本轮先复现已有方法，不开发子域法或其他新迭代算法。

| 项目 | 冻结值 |
|---|---|
| 分支 | `task39extra_para_workstation_capacity` |
| 基线 | `task39extra` @ `450255f4575792d052c1bac29837d39955ee1039` |
| 运行位置 | 原生 Linux 工作站、独立 worktree；优先 `Projects/Maxwell3D-Lab`，须核实为空或属于本任务 |
| 数值方案 | V5 `BAL_H + accurate global p4 LU`；MPI1/线程1；不是V6低内存候选 |
| 顺序 | 环境/迁移检查 → 13.5 nm原始与原notch复现 → 5 nm → 条件3 nm → 条件2 nm → 至多一次条件网格对照 |
| 波长/主网格 | 13.5/p6h10；5/p6h4；3/p6h2.5；2/p6h1.5；均不是预先证明的精度资格 |
| 修改权限 | 明确迁移bug与配置参数化可自行最小修复；不得换PC、放宽数值Gate或修改邻近Hybrid环境 |
| 资源 | 工作站一次一个heavy，整树watchdog、zero swap、实际RAM余量；逐阶段容量预检 |
| 未授权 | 新迭代算法、MPI扩展研究、0.7 nm PDE、master合并 |
| Codex回应 | 本目录 `response_v1.md` 和 `outcomes/`，均由实际执行后产生 |

请从完整任务书开始，不从继承的旧 `workstation_handoff.md` 或笔记本V6未完成阶段推断本轮权限。`para`表示独立并行研究任务，不是MPI并行开发要求。

本目录创建时仅交付任务文档，尚未检查工作站实际环境、尚未运行任何新PDE。首个正式运行前必须提交迁移实现的clean源码并绑定input/physical/resolved/source身份。
