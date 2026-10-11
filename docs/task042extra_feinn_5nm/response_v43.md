# Response V43：同一第4轮状态续算与冻结消融完成，M5联合FAIL

**Review V42完整包已连续完成，两条均运行到总第8轮并独立验收，非接口或commit交棒。新增学习没有稳定的联合精度优势，M5未求准，无合格NN资源收益。**

本轮没有从零重训，也没有换表示。把已经学习四轮的同一完整网络分成两份：一份继续更新隐藏函数，另一份保持这些隐藏函数不变、只求输出系数。它回答“第4轮以后继续学习隐藏层有没有额外帮助”，控制也继承了此前学习，不能叫从未训练的非神经基线。

保留原 M5：5nm、8×6×8=384hex、h1.25nm、p3、31968独立复FE系数及全部40端口；原Si/air非可分三维缺口、材料、背景、双Floquet、DtN和A/f不变。三轴sin网络秩(1,8,8,1)、9072实参数，其中912隐藏参数。原未折叠横向相位chi（取出已知横向传播振荡，让小网络表达剩余复包络）在完整边/面/内部矩及Piola之前相乘，MPC展开一次，H来自最终FE场的curl。体/DtN q15、网络q30及独立q60均保留。

| measured；原 M5 / 5nm / 384hex / p3 / N31968 / 40端口 | R4之后追加隐藏学习 | 同态冻结隐藏层 | 原门与口径 |
|---|---:|---:|---|
| 完整轮次 / 核访问 | 8 / 24 | 8 / 24 | 包含继承4轮/12访问；两条本批新增4轮/12访问 |
| LSMR迭代 / 隐藏实际调用 | 6905 / 109 | 6923 / 53 | 核心上限300；调用不是epoch |
| 接受核心 / 接受隐藏更新 | 24 / 8 | 24 / 4 | 真实原loss不增并完整落盘 |
| 内层停止码 / 最大真伴随残差比 | {'2': 2, '7': 10} / 0.236198678193 | {'2': 2, '7': 10} / 0.771437135195 | 停止码不是PDE PASS；完整线性及伴随残差在内层CSV |
| native / augmented | 0.426368073351 / 0.426368073351 | 0.426728354382 / 0.426728354382 | 各≤1e-6 |
| 独立total原方程 | 0.201971307269 | 0.202141973027 | ≤1e-6 |
| 总E / 散射E | 0.0838589615128 / 0.122287212177 | 0.0836773693023 / 0.122022405592 | 各≤1e-4；原参考分母 |
| 总H / 散射H | 0.083793811236 / 0.122543035005 | 0.0836067118294 / 0.122269414211 | 各≤1e-4；原参考分母 |
| 总scaled-curl / 散射scaled-curl | 0.083793811236 / 0.122543035005 | 0.0836067118294 / 0.122269414211 | 各≤1e-4；原参考分母 |
| 六点total/scattered复E/H最大误差 | 0.1583985894 | 0.157582607914 | 六点×三分量全部保留；≤1e-4 |
| 完整total复通道 | 0.0863311443683 | 0.086057350332 | 每类完整40复向量；≤1e-4 |
| 完整scattered复通道 | 0.153272902785 | 0.152786806984 | 每类完整40复向量；≤1e-4 |
| 完整出射复通道 | 0.0414347656612 | 0.0413033577919 | 每类完整40复向量；≤1e-4 |
| 边界面出射复通道 | 0.0401726183244 | 0.0400168017138 | 每类完整40复向量；≤1e-4 |
| R / T / A_balance / A_volume | 0.811314470118 / 0.0254417526173 / 0.163243777265 / 0.130200192977 | 0.811471888052 / 0.0254054923689 / 0.163122619579 / 0.130222726588 | 原残差未过，仅diagnostic |
| R / T / A_balance / A_volume绝对差 | 0.00111202893953 / 0.00702064347794 / 0.00813267241747 / 0.0249109118702 | 0.000954611004932 / 0.00705690372633 / 0.00801151473127 / 0.0248883782591 | 对原同p3参考，各≤1e-5 |
| R00_s / R00_p / R00_total | 0.811305637068 / 3.51657542071e-10 / 0.81130563742 | 0.811463731277 / 5.32707574459e-10 / 0.811463731809 | 零级两极化与和分别记录 |
| 能量闭合 / 最大逐级功率差 | 0.033043584288 / 0.0068916271332 | 0.0328998929907 / 0.0069282293204 | ≤1e-5 / ≤1e-6 |
| 实际模型完整矩重建 | 1.22643903466e-14 | 1.73336583822e-14 | ≤1e-10；独立旧逐点乘chi |
| 网络q30/q60系数 / 原作用漂移 | 1.19933433288e-14 / 1.80539423405e-11 | 8.07592116001e-15 / 1.51320358611e-11 | 各≤1e-8 |
| FE积分q15/q30漂移 | 9.13274811176e-15 | 1.32379007145e-14 | ≤1e-8 |
| MPC / 端口恢复 | 0 / 3.05174861788e-15 | 0 / 3.14564599129e-15 | 各≤1e-10 |
| 原G场误差 | 0.122536739374 | 0.122263335292 | 仅隔离评分稀疏G乘法；无G逆 |
| 实际attempt秒 / 同时自身树RSS采样峰B | 1625.0439828 / 916746240 | 1597.94472169 / 843309056 | 含加载、准入、setup、检查及保存 |
| 停止理由 | NO_CONTINUED_JOINT_PROGRESS | AUTHORIZED_TOTAL_ROUND_LIMIT | 科学分流或原硬预算；不重置 |
| actual / producer联合门 | FAIL / FAIL | FAIL / FAIL | 两份完整评分，不挑有利版本 |

## 起点、方法及轮次

唯一parent从V42原index定位为committed_000023.pt，1887719B，SHA256820482a3ff75c87203f301e628b5874be2e387b0627b8765a96e1a8ae6076c2f，原数值source c1c82474d9a26675f1829db5a219efdc04a60f59。两份首态完整模型/buffers/c/r/RNG逐位等同该parent；一次定向真实c/r资格配对为0/0，两路线各自必要的恢复配对也通过。继承4轮、12核心、3358 LSMR迭代、53隐藏调用；旧第4轮validation=false与FAIL保留，未重复前缀。

学习本批完成总第5—8轮，新增12核心、3547 LSMR迭代、4次有效隐藏更新/56次实际调用；冻结对照新增12核心、3565迭代、零隐藏调用。累计分别6905/6923迭代和109/53隐藏调用。冻结隐藏与parent逐位相同；学习隐藏相对parent变化范数0.000164150108774，全部相位及坐标buffers不变。已保存的CoreBoundary/位置、模型、c/r、RNG和已完成隐藏优化器状态可复读，不声称恢复未保存LSMR内态。

核心求解只在一个神经轴的输出参数空间中进行：用原A与完整矩构成B=AK/||f||，LSMR以反复算子作用进行小参数块最小二乘迭代，求使原残差下降的输出增量，返回后实际写回模型、复算完整c/r并检查线性配对≤1e-10及原loss不增。damp0、atol/btol1e-8、conlim1e12、每核300、零增量起点不变。总第5轮z→x→y，第6轮反向，交替使用最新状态。学习路线每轮后固定输出、fresh原L-BFGS更新912隐藏参数，最多20实际调用；这不是精确VarPro梯度。无PC、N×d列库、A*A、全FE完成器、Maxwell/Gram全局因子或Gsolve。

第6轮仅诊断，第8轮学习路线最近两轮R/E/H比为0.993955419495/0.925066951709/0.925401400577，未同时≤0.9，亦未进入R≤1e-5、场≤1e-3的精修区。因此NO_CONTINUED_JOINT_PROGRESS，不启动第9—12轮；冻结控制按总第8轮上限结束。旧第4轮关卡未再次执行，政策数字在运行前冻结。标量验证参与停止，明确validation_used_for_stopping、benchmark_previously_seen、design_informed_by_reference_diagnostics=true；训练仍未读取参考向量或监督权重。

| 总轮次；原完整范数 | 学习R/E/H | 同态冻结R/E/H | 分流 |
|---|---|---|---|
| 4（共同parent） | 0.444550296117 / 0.132626683892 / 0.132884263175 | 完全同态 | 保留旧FAIL和false |
| 5 | 0.435201668815 / NOT_RETAINED / NOT_RETAINED（未安排场评分） | 0.435281693503 / NOT_RETAINED / NOT_RETAINED（未安排场评分） | 完成并继续 |
| 6 | 0.428960962422 / 0.132192823396 / 0.132421492909 | 0.429973771043 / 0.133857967292 / 0.134076957996 | 仅诊断，继续 |
| 7 | 0.426824157144 / NOT_RETAINED / NOT_RETAINED（未安排场评分） | 0.427303344505 / NOT_RETAINED / NOT_RETAINED（未安排场评分） | 完成并继续 |
| 8 | 0.426368073351 / 0.122287212177 / 0.122543035005 | 0.426728354382 / 0.122022405592 / 0.122269414211 | 学习趋势STOP；控制轮数上限 |

## 共同时间与中期/终态

共同新增wall T=1595.77329967s，先按两路线较短的最终committed时间选T，再取各自不晚于T的最近完整提交，不按参考误差挑best。

| 路线 | 已保存时间/s及滞后 | 完整提交状态 | 原R / 散射E / H |
|---|---|---|---|
| BLOCH_FTTNN_R4_LEARNED_CONTINUE | 1475.36544777 / 120.407851904 | 完整7轮，下一总轮8，已完成该轮2核心 | 0.426509970103 / 0.12026947519 / 0.120515407903 |
| BLOCH_FTTNN_R4_FREEZE_ABLATION | 1595.77329967 / 0 | 完整8轮，下一总轮9，已完成该轮0核心 | 0.426728354382 / 0.122022405592 / 0.122269414211 |

学习边界是第8轮前两个核心已经完整落盘后的状态，后一个核心尚未开始；它不是半次LSMR。该时刻E/H比最终第8轮更好，最终变化仍保留，不把中期状态替换终态。共同时间边界存在约120.408s的保存滞后；现场使用不同合格单核、共享工作站，不能把该表包装成严格同成本算法优势。共同第6轮学习略好，共同第8轮冻结E/H略好而学习R略低，新增隐藏学习没有稳定的联合优势。

## 裁决、成本与修复

两份actual及producer都NUMERICAL_GATE_NOT_REACHED。原方程各1e-6、场/样点/四类完整复向量各1e-4、功率/吸收/能量1e-5、逐级1e-6、模型/MPC/端口1e-10、独立求积1e-8均不降低。学习终态独立total原残差0.201971307269、散射E/H0.122287212177/0.122543035005、能量闭合0.033043584288；冻结对应0.202141973027、0.122022405592/0.122269414211、0.032899892991。实际完整重建、MPC/恢复、求积通过，故不能把约12%的场误差归咎于writer或未完成export。完整失败量、原分子/分母、六点和区域在原记录。

保留相对第4轮的实际场改善PARTIAL_LEARNED_FIELD_IMPROVEMENT_OBSERVED，也保留冻结控制的改善、较好的中期边界与最终退化。后续隐藏学习的边际结论仅针对本次固定相位/r8/native-EUC/LSMR300的有限续算，不排除所有NN或FTT。当前有限续算关闭；没有支持新神经生产候选或同严格精度20%资源收益的证据。保持FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED和NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE。

0.7nm缩小pilot因LEARNED M5联合门未过而NOT_RUN，未注册空stage。没有监督fit/oracle、rank/seed/loss/载波/优化器扫描。原50×25×140nm、Si17/120nm、lambda0.7完整3D FE、decimal2e12B整机、ownswap/OOC0、172800s完整冷流程及原门仍未达成。本支只做神经，不恢复W0/W1、全口面、传统PC或主线接入，不给其他任务派活。旧M3600较好、Mfinal退化、D0成本否决/D1未运行、全部失败、UNKNOWN和费用永久保留。

新增唯一28800s窗口自首个保留准备时刻2026-10-11T00:39:29.170614+00:00固定，未重开。此前只读检查精确费用NOT_RETAINED，另列120s保守余量，不能冒称实测；采集时窗口已过5679.55945277s，尾段持续补账，远低于总上限。正式attempt合计3738.99306932s，包括失败比较及恢复；学习/冻结正式attempt为1625.0439828/1597.94472169s。核心/隐藏/审核/存盘互斥计时与嵌套K/A计时分开，不重复相加。

各逻辑路径须归属已付V42学习前缀2920.6633467029314s，但项目账不再收费；另有必需网格/native/moments准备，不免费。loaded-packet新增费用、已付前缀、可复用准备、研发历史及完整冷N=1分开；冷N=1和项目精确历史累计仍UNKNOWN。没有同合格精度，所以不授NN20%资源收益。

数值阶段串行自身同时树RSS采样峰最大916746240B，约0.854GiB；含后续浏览器的已监督轻任务/数值树采样峰最大1100705792B，约1.025GiB，非整机峰或峰值相加。numeric warn12/hard16GiB、规划12GiB、cache/AD1GiB、轻2GiB；CPU-only/MPI1/math及Torch intra/inter-op1、原PSI/CPU-SMT/系统及384GiB邻增长门未改，成功60s准入计墙钟。数值、测试及验收树swap/OOC0并清场；只读工具控制没有完整峰值测量，不虚构全机资源PASS。新global Maxwell/Gram因子、Gsolve、全FE Krylov和参考重求均0；隔离验收G仅稀疏乘法。

最小定向测试最终25项、Ruff/compileall通过，非full pytest、无CI声明。初始fixture错误把dummy截止设成60s，触发原保存预留守卫，两项失败保留；只将fixture截止改300s，未改变正式保护或数学门。最终比较辅助步骤的common_wall目录缺失使attempt1在健康FE审核之后失败；增加先建立目录、实际原子writer→重开回归，通过25项后以--attempt 2恢复缺失步骤。启动默认attempt1被已有阶段守卫拒绝，未启动重复worker；明确恢复沿原分配时钟。所有失败、修复、测试和等待计费。

健康reconstruction.json与verifier_result.json逐字hash未变，未重训或重做健康物理producer。pure保存checker恢复时重新从同一数组重算，其load_and_pairing_seconds重新计时，JSON hash变化；首版hash留存，首版计时字段原文NOT_RETAINED，不虚称字节一致。大数组/原PT保持原位ignored。用途false贯穿manifest/checkpoint/raw/compare/reopen，R/T/A因原残差未过只作diagnostic，绝不升级official。

有限GitHub实际首屏检查及其限制见[呈现记录](outcomes/records/render_check_v43.json)；发布尾段采集时连续窗口为6871.540424s，另列120s未保留初检的保守余量。[尾段费用](outcomes/records/publication_tail_v43.json)保留检查、修复、网页与失败成本，最终commit/push/fetch及清场的结束时刻由ignored交付收据记录，不把采集截点冒充最后成本。

## 身份与证据

初始现场HEAD9ec83316492b25391fec50591b2721d4ac19b67a、clean、锁FREE，无本任务活跃作业；精确fetch/ff-only取得Review V42发布34ccdfa87b6682812570ef23e12dc22a02542e9b。base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff，canonical /home/fenics/Projects/NN-Lab-V2，common Git /home/fenics/Projects/Maxwell3D-Lab/task-repository.git。

原资格及两训练source dce792d18a45a1c874c29dfa4a42a8052fffe40f，独立全场重建/FE审核source fe56d165fa6b75193155e8ed6bfc1ece269e701a，目录修复及缺失辅助恢复source bc85c8af422acb77f3dca599334b6d96c981d7a9。运行前均clean实现commit；后续文档HEAD绝不冒充运行source。native/moments/material/mesh/modes/phase/PT/input/source/env/resource完整hash见run_index。原V1同p3参考SHA2560c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7仅由隔离评分读取，没有MUMPS重求。

[parent/恢复](outcomes/records/parent_and_recovery_v43.json)、[路线/真实分叉](outcomes/records/conditional_core_routes_v43.json)、[核心内层](outcomes/records/conditional_inner_solver_v43.csv)、[隐藏/轮次](outcomes/records/hidden_updates_and_rounds_v43.json)、[标量/趋势](outcomes/records/isolated_scalar_continuation_v43.json)、[共同轮次/wall](outcomes/records/same_state_hidden_ablation_v43.json)、[完整Gate/区域/分母](outcomes/records/full_numerical_gates_v43.json)、[四类40通道](outcomes/records/full_40_complex_channels_v43.csv)、[六点复场](outcomes/records/six_point_complex_fields_v43.csv)、[功率/能量](outcomes/records/power_and_energy_v43.csv)、[定义](outcomes/records/channel_and_norm_definitions_v43.json)、[source/run/hash](outcomes/records/run_index_v43.json)、[费用](outcomes/records/resource_costs_v43.json)、[tests](outcomes/records/tests_v43.json)、[修复](outcomes/records/repair_log_v43.json)。

[专题](outcomes/bloch_ftt_trend_continuation_v43.md)。最终完整HEAD、tracking/ahead-behind、clean与自身清场另在发布收据及最终答复精确核对；只推本分支，完成后等待review，不通知隔壁或自动开启下一批。
