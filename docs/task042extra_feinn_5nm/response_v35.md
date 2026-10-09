# Response V35：冻结神经空间的原方程读出与最佳场表示

回应[Review V34](review_report_v34.md)。A两空间和D投入决定完成；B触发不可重置的A/B共享7200s硬预算，随后因空间子目录缺失而写出失败。原WORKER_FAILED日志及费用保留；目录修复和5项定向测试通过后，C只恢复未完成元数据，并核对A两份旧场身份/复用原Gate。B没有已提交oracle场，最佳G场误差、最终秩、最优性及新场物理Gate均UNKNOWN/NOT_RUN；没有启动第二次投影。 本轮不续训练或构造新生产候选。当前配置原方程联合门未达到，当前稠密波库求解族关闭。

## 1. 实际数值与边界

本轮把“网络已经学出的波形”和“这些波形如何组合”分开检查。A只使用原方程，检验已有空间内最小残差的幅值读出是否可靠；B在A封存后才读取原准确参考，检验即使知道答案，固定波形能表示多准确。B是参考暴露的诊断，永久不能用于无标签求解或生产初值。没有新训练、扩列、换波长、参考求解或全局逆。

| measured；M5/5nm/384hex/p3/31968复FE/40端口 | V34学习冻结空间 | V34确定性强控制空间 | 限值/含义 |
|---|---:|---:|---|
| 冻结槽 / 块 | 1377 / 246 | 1377 / 246 | 无新增容量、无新q/kappa学习 |
| A保留秩 | 1377 | 1377 | 固定rcond=1e-12 |
| A最佳native原残差 | 0.143187704283 | 0.14440693779 | 各≤1e-6，FAIL |
| A归一化一阶最优性 | 2.36446091522e-11 | 1.95701596676e-11 | ≤1e-9 |
| A全作用 / 小系统配对 | 1.92206580485e-11 | 1.20825734309e-11 | ≤1e-10 |
| A旧c/r逐位未变 | True | True | 复用原完整Gate |
| A旧实际散射E L2 | 0.0180687044393 | 0.019606287833 | ≤1e-4，FAIL；并非最佳G误差 |
| A旧实际散射H / scaled-curl | 0.0181871468678 | 0.0197167792543 | ≤1e-4，FAIL |
| A旧独立total原残差 | 0.067828267702 | 0.0684058207612 | ≤1e-6，FAIL；分子/分母见原Gate |
| A旧独立体吸收能量闭合 | 0.00483197020387 | 0.00522906780337 | ≤1e-5，FAIL |
| A旧最大逐级功率绝对差 | 0.00289648662723 | 0.00317414690233 | ≤1e-6，FAIL |
| B完成状态 | CONTROLLED_STOP_NUMERICAL_BUDGET | NOT_RUN_NUMERICAL_BUDGET | 未完成不是数学失败 |
| B最终保留秩 | UNKNOWN | UNKNOWN | 最后日志的930选列不是最终SVD数值秩 |
| B实际最佳G相对场误差 | UNKNOWN_NOT_COMPLETED | UNKNOWN_NOT_COMPLETED | 联合E/curl必要门1e-4 |
| B数值最优误差下估计 | UNKNOWN | UNKNOWN | 浮点估计，非区间证明 |
| B数值归因 | INCONCLUSIVE_NOT_COMPLETED | INCONCLUSIVE_NOT_COMPLETED | 仅当前固定空间 |
| B散射E L2 | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B散射H / scaled-curl | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B总E L2 | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B总H / scaled-curl | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B native原残差 | NOT_RUN | NOT_RUN | 各≤1e-6；oracle永远不是无标签求解 |
| B独立体吸收能量闭合 | NOT_RUN | NOT_RUN | ≤1e-5；diagnostic |
| B最大逐级功率绝对差 | NOT_RUN | NOT_RUN | ≤1e-6 |
| B模型完整矩重建 | NOT_RUN | NOT_RUN | ≤1e-10；实际与producer分别评分 |

V34学习冻结空间：CONTROLLED_STOP_NUMERICAL_BUDGET；原A最佳残差仍FAIL，但B最佳场精度和表示归因保留UNKNOWN。

V34确定性强控制空间：NOT_RUN_NUMERICAL_BUDGET；原A最佳残差仍FAIL，但B最佳场精度和表示归因保留UNKNOWN。

结论限定为两份V34最终冻结空间。数值秩、最优性与独立积分是浮点资格，不能推广为所有NN数学上不可能。未完成项保持UNKNOWN；最佳场投影即使更好，也不能突破A已测原残差的数值最小值。

`CURRENT_DENSE_WAVE_SOLVER_FAMILY_CLOSED / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED`。没有证据支持新的单场神经生产候选：`NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE`。0.7nm三维pilot/p-h/端口扩展本轮全部NOT_RUN且未注册。原50×25×140nm、Si17/120nm、lambda0.7完整3D FE、decimal2e12B、ownswap/OOC0、172800s完整冷流程及原精度目标未达。


本次没有保存的新场，未运行新场评分；旧actual网络与producer两类原Gate分别复用。完整E/H/curl、六点、四类40复通道、功率、逐级功率、体吸收、原区域、MPC/端口恢复与q复核见[全部Gate](outcomes/records/joint_gates_v35.json)；没有新场时无新指标CSV，旧两态完整原Gate继续绑定复用。对未完成B不伪造场、通道或oracle资格。 旧R/T/A/A_volume/R00三项见[原功率复用](outcomes/records/reused_power_observables_v35.json)，全部仍为diagnostic；[原指标及分子/分母](outcomes/records/full_metric_index_v34.csv)、[四类40复通道](outcomes/records/complex_channels_v34.csv)、[逐级功率](outcomes/records/per_mode_power_v34.csv)、[六点](outcomes/records/six_complex_field_points_v34.csv)、[原区域](outcomes/records/material_interface_regions_v34.csv)逐位未变，不重造数值。

## 2. 可复核的执行与修复

沿用已见benchmark，旧V34隔离标量验收参与和benchmark_previously_seen=true保留，不称盲测。A先冻结，两份c/r逐位未变，因此复用V34独立完整场验收，只新增最优性证据。每个空间三组非零复组合，共六组实际点值完整矩与原A配对通过；未因版本改变重生成全部U/AU。初次小R SVD幅值重构的归一化最优性4.9680138955278485e-9未过1e-9；保留原失败。固定SVD秩通过后采用原三角QR回代，恢复数值精度，没有换loss、秩门、波形或标签。六组健康见证直接复用。小fixture、writer/seal/reopen、用途破坏和标签隔离通过；普通mock/路径/lint/元数据读取故障及费用见[修复账](outcomes/records/repair_journal_v35.json)。

B算法只用G乘法、两遍G正交化和小系数QR/SVD；此次实际停止在G-QR阶段，未达到最终小R SVD或幅值求解。最后日志为930个暂选方向、G按列作用至少4167次，两者都只是保留日志下界，部分基/幅值未保存。唯一B尝试含启动准入与加载耗时5110.947981953854s，完整费用保留。列流式≤8，没有G逆、global Gram/Maxwell factor或Krylov完成器。本次预算内未形成任何oracle幅值或模型。独立点值/FE/pure新场checker路径已实现，但没有新场可运行，保持NOT_RUN；C只核对旧两态身份并复用原Gate，q/kappa/窗口/T/原列掩码完全不变，原V1同p3参考只读，未重新MUMPS。

oracle永久标记：reference_used_for_coefficient_fit=true、reference_used_for_training=true、pde_only_solve=false、production_initialization_allowed=false、pde_only_solver_qualified=false、official_candidate_results=false。不反馈训练、Task42或0.7nm。

## 3. 费用、投入决定和未验证项

正式运行各自实际source在[run index](outcomes/records/run_index_v35.json)。初实现/S0/A初次source为00e226cf61f613e38f831e16f66dc20d247598ac；修复后A/B数值source为520cb681dc7c6b69f13caeaa11af98d3d90a7b4b；预算writer修复与C元数据恢复source为2c1546c2f195a9d6b89703b7e509e899e0db75dc。文档HEAD不当运行源码。冻结base=fbac3d8777fcfd897d93b898cb9f460f79ddd6ff，review发布=936fdcff435a772619ae720119e2a22de0dabccd。

本批连续14400s、A/B共7200s及1800s末段预留均使用同一个不可重置时钟。收集时墙钟10282.4772524s、正式attempt和6925.53399668s（嵌套worker不再相加），数值同时树采样峰5029191680B，采样自身swap0/OOC0。最终Git/网页/交付尾段另见本地`tmp/task42extra/v35/delivery_receipt.json`及最终完整HEAD报告。[完整费用与资源口径](outcomes/records/cost_capacity_v35.json)。峰值是同时树采样峰，非各阶段峰之和或连续内核硬峰。

必要前缀10186.178641493432s继续归属，历史项目账不重收费。完整冷N=1和项目精确累计UNKNOWN。历史传统参考672.462895s/1245822976B没有本批同精度新成本对照，不能虚构加速倍率；本批也没有合格无标签神经解，20%同精度神经资源收益未授予。

当前两空间的最优性/表示诊断不支持新的生产神经路线。固定波库幅值或波矢/衰减续扫关闭；没有新架构、0.7nm注册或训练。未来仅当新机制能指出删去哪项已测单场成本、N=1必要数据/训练费用、规模增长和可否决试验时再提出准入，不自动执行。[一页投入决定](outcomes/neural_route_decision_v35.md)。

## 4. 证据与交付

[专题](outcomes/neural_space_feasibility_v35.md)、[设计](outcomes/design_v35.md)、[快照](outcomes/records/snapshot_identity_v35.json)、[A最优性](outcomes/records/unlabelled_optimality_v35.json)、[B oracle](outcomes/records/field_oracle_v35.json)、[秩](outcomes/records/rank_stability_v35.json)、[全部Gate](outcomes/records/joint_gates_v35.json)、[测试/失败](outcomes/records/tests_v35.json)、[费用](outcomes/records/cost_capacity_v35.json)、[ignored原数组hash索引](outcomes/records/raw_artifact_index_v35.json)。本地targeted tests/ruff/compileall，未full pytest、重装或声称CI。有限新页GitHub视觉与本地结构分开记录；旧网页失败保留，服务错误不重做健康数值。

README/summary、progress、模型总账、tests/changed_files同步；历史原文、负结果、UNKNOWN和费用保留。只提交推送task42extra_feinn_5nm，不amend/强推/merge，不修改其他工作树或安排其他支线。最终准确HEAD、显式tracking/ahead-behind/clean及本任务清场在最终回报，之后停止等待review，不通知其他对话框。

有限GitHub呈现收据：[rendering_v35.json](outcomes/records/rendering_v35.json)。三份实际首屏的标题、正文和可见表格已目视，绑定页面发布901de943b6f6559badcb88ff9446518916e1b528与Review发布936fdcff435a772619ae720119e2a22de0dabccd。另一次公式锚点检查截图未定位到公式段，未授新公式视觉PASS；也不授整页或全部表格视觉PASS。本地fence/表格/链接结构另有通过收据。此后的封存仅补可复用功率/原CSV链接和收据，没有数值修改。
