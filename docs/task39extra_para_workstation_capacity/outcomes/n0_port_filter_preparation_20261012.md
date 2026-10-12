# 0.7 nm N0 通道筛选：准备及旧场停止记录

本记录是 2026-10-12 的实现中快照，**新目标场尚未启动**。后续启动和终态必须另附实际 run/source 身份与测量，不能把这里的准备检查当成求解结果。对应[小型 JSON](records/n0_port_filter_preparation_20261012.json)绑定原始证据路径及 SHA256。

本轮只在端口边界上减少待耦合的衍射通道：完整清单仍保存，但只将其中 `n==0` 的通道接入新算子。这样能减少端口准备和端口块的规模；代价是新算子与原 32060 通道算子不同，必须分别检验残差。它不把三维有限元改成二维，也不证明被省略的衍射通道实际为零。

| 合同项目 | 本轮状态 / 证据边界 |
|---|---|
| 目标 | 0.7 nm Si 光栅、p6/h0.7、p6→p3、完整三维 FE；530856 cells 为旧实际目标数，新 mesh 仍待现场复核 |
| 通道筛选 | 当前真实 metadata 枚举 32060→572，严格 `n==0`；top/bottom × s/p 各143，m=-142…0 |
| 不是清单前缀 | 首个保留 parent index=10，末个=32059；不是截取前572项 |
| 父清单 hash | `7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb` |
| 新清单 hash | `946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b` |
| 保留索引 hash | `f423721c90fe6259f9d9ea9f514aa9c5f1abdd7723ffd49fac64c79af03c56b2` |
| 积分规则 | 继续用完整父清单派生的端口 q160，体积分不变 |
| 材料/几何身份 | physical SHA `965c5ad2c25b817b01dbe5eaab1ee557a3d5c84ea4913b620466bb13f0795e4e` 未变；实际 y 不变 cell-tag/几何检查将在目标 mesh 建立后执行 |
| 求解合同 | 准确 A3 凝聚 MUMPS、BAL_H、FGMRES32、零初值；A3≤1e-10，最多两次同因子精化；QA与16步共享一个因子 |
| 资源 | 整树实测 RSS 硬线 **1,950,000,000,000 B**，以用户最后更正为准；PSS/USS关闭，swap/预测/预计耗时仅观察 |
| 运行位置 | 当前任务分支；worker CPU24、parent CPU9、MPI1/math1、NUMA interleave0–1不变 |
| 时间守卫 | p6端口准备完成后24小时仍未进solve则受控停止；进入solve永久撤销；新572身份guard仅已准备，尚未启动 |
| 新运行 | `N0_PORT_FILTER_TARGET_PILOT`，尚未取得新 clean source/run instance；没有新端口/setup/factor/KSP耗时或RSS实测 |

旧运行 `20261011T070335.458824Z` 已按用户授权受控结束，`USER_CONTROLLED_STOP/exit1`，后代清空；root/MPI/worker及独立guard均核为 absent。停止时仍为setup，p6已完成32060项，p3最后阶段记录8367项，落盘目录快照8380项。整树历史采样RSS峰726,530,977,792 B，任务swap峰0。这里引用原终态小摘要，不重扫大型resources日志，不把终态样本变旧解释成运行中失联。

| 旧完整目标准备 attempt | workflow wall / s | 终态 | sampled tree RSS峰 / B |
|---|---:|---|---:|
| 20261005T054606.313917Z | 246558.558494 | USER_CONTROLLED_STOP | 88331550720 |
| 20261008T230249.073983Z | 55091.481307 | USER_CONTROLLED_STOP | 188210724864 |
| 20261009T231005.014329Z | 112318.641526 | WORKER_FAILED | 319242330112 |
| 20261011T070335.458824Z | 78277.660374 | USER_CONTROLLED_STOP | 726530977792 |

当前落盘store来源的后两场 workflow 共190596.301900 s（52.9434 h）；四场共492246.341701 s（136.7351 h）。这是不重叠运行的总墙钟相加，包含JIT、读取、装配、写盘和清场，不是单独端口积分时间，也不包含场间等待或小型对照；四场均未获得完整求解资格。

旧store中存在572项p6、148项p3所需N0的manifest/payload路径。这只证明文件存在，不代表payload hash或新mesh/DOF/MPC身份已通过。正式复用必须只读逐项验证：阶次、原始mesh/DOF/MPC、方向、端口/材料、q160、模式身份和payload hash；不满足时只补建对应N0项。新布局的store、派生矩阵和因子使用新身份。p6数组不作为p3数组使用。新报告分别记录复用与重建计数、读取/hash/写盘和FE准备成本。

本轮已做真实metadata枚举（9.5186 s，无mesh/FE）及必要纯/fake检查：残差命名6项、材料/tag metadata helper7项、pilot记录checker9项、独立572守卫11项通过；这些不是数值PDE或完整集成通过。当前仍在完成runtime、缓存和终点检查接线，最终源码与测试receipt需在冻结时复核。

`A6_n0_relative` 专指572算子；原32060算子终点检查单独记录 `A6_full_relative`。只在pilot终点尝试分批读取已有完整p6数据，不建立完整A3因子、不每步扫描；数据不足则记 `FULL_DTN_NOT_VERIFIED`，不补做数天全通道准备。即使16步计划执行完，仍不自动延长，不据此宣称原完整0.7 nm求解、正式R/T/A、任意三维资格或48小时目标通过。
