# task42hybrid：新入射与二维截面任务入口

当前执行任务为 **task42hybrid_az90_50x50_17x20_0p7nm**。完整执行依据见[task.md](task.md)。

| 项目 | 当前决定 |
|---|---|
| 执行分支 | `task42hybrid_az90_50x50_17x20_0p7nm` |
| 起点 | Task041分支SHA `94700f95f2bef02e2359e6ca89872c11e65978fb` |
| 新物理 | 方位90°、掠入射1°、s；周期50×50 nm；居中17×20 nm矩形光栅 |
| 保持的高度 | 光栅z=0..120 nm、域z=-10..130 nm、Hybrid接口10/110 nm |
| 材料 | 13.5 nm与0.7 nm的光栅、基底均为Si；用户于2026-10-16覆盖task.md原W段，权威原始值与推导见[用户常数记录](materials/user_supplied_si_optical_constants.json) |
| 首批工作 | 13.5 nm Full3D直接参考 → Hybrid直接对照 → BAL_H双凝聚迭代 |
| 后续主线 | 前述必要门通过后直接0.7 nm，不要求5/2 nm中间梯级 |
| Codex项目 | **原项目显示名、根目录、环境和账户不变**；在原项目内安全切换Git分支 |
| 输出 | 本目录`response_v1.md`与`outcomes/`，大工件用独立ignored结果根 |
| 当前状态 | A0输入、材料、公共dry-run、外通道和小型边界拟合网格检查完成；未运行Full3D PDE、QEP或直接分解，资源合同尚未接入 |

Task041历史仍保留在继承目录；其旧模型结果、预算、失败和Review V19四次B诊断不被更名或改写。本任务从新的物理参考开始，不以解决旧物理全部待办作为前置，也不将旧失败视为自动解决。

本任务不重写求解器体系、不修改ordinary默认、不在master开发。源代码复用，物理相关QEP、source、mesh/MPC、矩阵及场必须重新绑定；有效缓存只能在新任务同身份内验证复用。新任务有独立预算和账目，具体Gate、额度、停止条件及48小时口径见task.md。

材料覆盖说明：`task.md` 保留建立任务时的W材料要求作为历史原文；用户于2026-10-16明确本任务两波长都使用Si，覆盖该段。13.5 nm与0.7 nm的Delta/Beta均由用户提供并按 `n=1-Delta+i*Beta` 推导，来源分类是 `user_supplied_delta_beta`，不是外部数据库或实验资格。0.7 nm材料数值已冻结，但按任务阶段顺序，A0不运行0.7 nm PDE。

阶段证据见[响应](response_v1.md)、[A0结果摘要](outcomes/summary.md)和[测试/费用摘要](outcomes/test_summary.md)。当前13.5 nm输入的48小时字段仍是旧入口的硬超时；A1必须先完成Task42显式资源/软目标接线，不能直接用该输入启动PDE。

开始执行前读取根/目录AGENTS、仓库工作原则和本task；检查HEAD、upstream、dirty、stash及实际运行任务。切分支不能覆盖未提交工作或热改运行源码。用户当前Codex项目名不等于Git分支名，不另建空项目、不要求重新安装环境。
