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
| 当前状态 | A0完成；A1已产生13.5 nm数值worker输出与场文件，但终态整作业资源authority不完整而拒绝，不能称整场通过；A2共享合同serial/MPI2通过，MPI8小型网格和p6截面空间/collapse sizing已完成，但MPC、QEP及后续阶段预算仍待sizing，当前不可启动，未运行QEP/因子/求解 |

Task041历史仍保留在继承目录；其旧模型结果、预算、失败和Review V19四次B诊断不被更名或改写。本任务从新的物理参考开始，不以解决旧物理全部待办作为前置，也不将旧失败视为自动解决。

本任务不重写求解器体系、不修改ordinary默认、不在master开发。源代码复用，物理相关QEP、source、mesh/MPC、矩阵及场必须重新绑定；有效缓存只能在新任务同身份内验证复用。新任务有独立预算和账目，具体Gate、额度、停止条件及48小时口径见task.md。

材料覆盖说明：`task.md` 保留建立任务时的W材料要求作为历史原文；用户于2026-10-16明确本任务两波长都使用Si，覆盖该段。13.5 nm与0.7 nm的Delta/Beta均由用户提供并按 `n=1-Delta+i*Beta` 推导，来源分类是 `user_supplied_delta_beta`，不是外部数据库或实验资格。0.7 nm材料数值已冻结，但按任务阶段顺序，A0不运行0.7 nm PDE。

阶段证据见[响应](response_v1.md)、[结果摘要](outcomes/summary.md)和[测试/费用摘要](outcomes/test_summary.md)。

## A1接线状态与正式运行边界

Task42显式opt-in现在将输入中的`timeout_seconds=172800`解释为48小时软目标：达到目标会记录状态并继续运行，不会仅因经过48小时而终止worker。该行为只用于本Task42 direct lifecycle；普通Task038继续使用原超时语义。内存、进程/cgroup、祖先资源和异常退出保护仍是硬门。

Task42分阶段准入使用整作业`J=max(launcher进程树RSS,可证明适用的专属cgroup current)`、本阶段新增分配量`Delta`以及余量`W`。大分配前核对`J+Delta+W<=C`、kernel `MemAvailable>=R+Delta+W`和每个有限适用祖先的headroom至少为`Delta+W`；运行中硬保护核对`J<=C`及`MemAvailable>=R`，不把W在每次轮询中重复扣除。预算及采样口径见[task.md](task.md)。

定向合同回归分开验证Task42公共入口/资源门fixture与原生8×8 MUMPS factor生命周期；后者覆盖symbolic、numeric、MatSolve、pre-recovery packet、销毁及小矩阵残差，并在同一新编译C bridge上覆盖`ICNTL(14)=None`默认路径和显式整数40控制。这些并非一次完整Full3D公共入口PDE运行。纯资源fixture另验证recovery gather临时数组按每rank分配并汇总，不把全局长度误记为只分配一次。具体selector、源码SHA、attempt费用和失败保留记录见[A1测试摘要](outcomes/test_summary.md)与[机器可读合同记录](outcomes/a1_contract_validation.json)。

以上段落记录的是正式A1启动前的计划状态。正式A1后来已运行并生成数值输出，但整场因末次进程树资源authority不完整而fail-closed拒绝；当前结论与缺项见[正式A1终态](outcomes/summary.md#2026-10-19正式a1非pytest运行与终态)及[response_v1](response_v1.md)。

开始执行前读取根/目录AGENTS、仓库工作原则和本task；检查HEAD、upstream、dirty、stash及实际运行任务。切分支不能覆盖未提交工作或热改运行源码。用户当前Codex项目名不等于Git分支名，不另建空项目、不要求重新安装环境。

## A2 Hybrid-direct当前边界

Task42独立A2输入使用用户指定的13.5 nm Si、p6/h10/M120，传播模型为`full3d_uniform_cg`，traction为`full3d_one_cell_exact_schur`。公共路由和共享输出/分级资源合同已有小型serial与MPI2合同覆盖；这只验证调用、身份、拒绝时序与collective写入行为，不是有限元、QEP或A2数值资格。

A2仍不可启动：2026-10-19已实测小型MPI8截面网格和p6 N1curl×Lagrange空间/collapse，但该2 GiB Delta只绑定本次`qep_mixed_space`阶段，既非实测峰也不可挪给MPC、QEP、凝聚、MUMPS或恢复。完整profile仍缺这些后续阶段的每rank/每side DoF、NNZ、QEP工作区、恢复缓存及MUMPS填充预算。dat原字节SHA和不含预算引用字段的规范化预算basis是不同身份。PETSc `KSP.setUp()`把MUMPS分析和因子分解放在同一阶段门内。2026-10-19的P1小型公式回归已修正Hybrid外通道行级`R/T`门控，保留`propagating`标签和原行schema；这只是报告合同修复，不是A2物理资格。mesh/space实测、完整停点和下一阶段边界见[space-only收口](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_space_only_mpi8_attempt_20261019T124500Z/space_only_closeout.md)。详见[Task42当前回应](response_v1.md)、[结果摘要](outcomes/summary.md)和[测试/费用摘要](outcomes/test_summary.md)。

通俗地说，Hybrid把中间区域的场用截面模式表示，两侧区域仍由有限元网格求解；这样可减少中间长结构的三维自由度，但会增加模式耦合和恢复数据。阶段预算要求在每次大分配前先估算该步新增内存；目前的小测试只验证接口和拒绝传播，不证明A2物理解正确，也不证明实际容量足够。
