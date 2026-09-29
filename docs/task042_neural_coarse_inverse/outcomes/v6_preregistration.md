# V6 预登记：新神经 FE 单次求解 pilot，旧路线关闭

本批依据 [Review V3](../review_report_v3.md)，审查提交 `d5f45787168123a1680523ccf8e73c33de7c7a34`。旧小块／固定低秩空间／系数网络路线登记 `CLOSED_RESEARCH_NEGATIVE`；V5 建议的 port-only augmentation 不实施。V1–V5 源码、原始负结果和权限边界保留。

新表示尝试让一个坐标网络生成单元边、面上的完整有限元矩，再由原方程求解或优化。它可能省去全局分解，却增加矩积分、优化和反向作用成本；当前没有求解正确性或神经收益证据。冻结设计在 [design](../../../input/task042_neural_coarse_inverse/neural_fe_design_v6.json)，网络为 FP64、3×64 tanh、8组三分量复包络、seed420906、末层零初始化，无每自由度 embedding。

| 阶段／证据身份 | 本轮准入与预登记边界 |
|---|---|
| N0 材料 | 当前输入／材料代码没有合格 Si0.7nm 值；Task039 [归档审计](../../task038_extra_full3d_iterative_0p7nm/outcomes/task39_boundary_audit.md) 明确缺 delta/beta。其引用提交 `f4073adabb91bffe5c3954b8ae8b63270efa3e15` 在本地对象库不可用，未获取其他分支。状态 MATERIAL_0P7NM_BLOCKED；不猜填 n、不回用13.5/2nm材料。 |
| N0 几何／derived | 按review唯一微型模型，8×6×8、步长0.175nm，p3；解析 full FE34050、独立trace18144；条件参考p4解析78936／33792，未构造。材料tags可独立审核，完整port因Si缺失未知。 |
| N1 允许的部分 | 先纯数组复数非Hermitian、非零端口梯度；再独立真实网格、原MPC、全部108个p3边／面矩和DOLFINx插值配对。未知材料不影响这些几何接口；合格不代表真实S/S共轭转置、恢复或原方程Gate。 |
| 形式化输入 | 两个独立one-run dat分别只做FE插值和隔离ML packet/VJP，复用原shared launcher／subreaper。新入口只接受显式`task042_v6_interface`，普通PDE schema仍要求材料。manifest把design hash与物理operator SHA区分；后者null。 |
| N2／N3 | 真正Si材料和完整通道／目标S Gate未具备，因此三优化路线、准确参考和p-enrichment not_run；不生成替代物理结果。无旧teacher／目标准确解／隐藏强逆／GPU。 |
| N4 | 完成资源／未知目标字段账。最终规模未冻结、目标完整步耗时与所需步数 unknown；最终0.7nm／48h NOT_QUALIFIED。 |

构造前仅核准材料独立接口容量：两套矩packet、orientation、小型多项式插值、网格/MPC、库/编译临时与场向量的合计保守预测2.5GiB；不假装完成包含未知port的求解器总容量证明。无目标矩阵、Schur、全局或局部FE因子。真实FE插值运行前提交clean实现；一阶段最多600s（预计1–5分钟），packet／checkpoint在ignored `benchmarks/artifacts/task042/v6/`，原始资源与source在`results/task042/`。每个正式阶段只启动一次，失败保留，至多合同允许的最小实现修复；停止后不凭材料不足返回旧路线。

继续用户对Task042的受控共享CPU授权，覆盖原task §2.3 heavy／独占要求，不改变邻任务合同或锁，也不宣称F0取得正式review。每次现场选空闲物理核心，MPI1、数学/训练线程1、DataLoader0；独立缓存、自有锁、nice10、idle I/O。整树16GiB hard／12GiB warning、自身swap0，系统reserve＋邻增长128GiB保留；无cgroup委派时采用原0.5s采样停止，不能冒称内核连续限制。共享成本标shared-workstation，邻影响缺可比阶段指标时inconclusive。旧seed420620池封存。
