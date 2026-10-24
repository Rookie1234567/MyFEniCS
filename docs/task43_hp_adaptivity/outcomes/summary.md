# Task43 结果：部分完成，受控负结果

## 最新收口：V3 两次有限诊断（2026-10-24）

V1接受状态仍冻结在R9，最终空间精度未达。V3在原始最多6次formal dispatch额度内完成了两次获准尝试，累计共5/6次；A1组2/2、A2组3/3，剩余1次封存。A1_q2构网并进入装配后，因为实际A1入口没有建立要求的`WorkflowLedger`，由主控受控停止；A2_q3确实建立ledger、完成Y6_1网格与装配、保存primary和q8/q10场样本，但在7200秒墙钟门到期后停止，完整端点与比较未产出。两项均不是完整q/R资格，A1工程接线缺陷也不能归咎数值方法。

| V3 formal dispatch | 实测结果 | 分类、资源与缺口 |
|---|---|---|
| A1_q attempt2 | 180格网格已建并进入装配；无因子分解/完整求解结果 | `G2_A1_WORKFLOW_LEDGER_NOT_WIRED`受控停止；whole-watchdog `159.36019697086886 s`，采样树RSS峰`948682752 B`，task swap峰0。见[A1停止原件](records/a1_q_attempt2/dispatch_and_stop_record.json)和[独立终态审核](records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json) |
| A2_q attempt3 | Y6_1 native p6网格576格，R13 612模式；q19体算子、q32入射/端口；FE=380160 derived（389832 carrier−9672 constrained slave=120960 trace+259200 interior）；矩阵121572²，stored NNZ实测111681742、allocated 128135952，assembly `4771.323931380641 s`。旧Y6 stored-NNZ预测112458734另列，不推测预测差异原因 | primary residual和样本均留存；extra full-active explicit residual略增且未严格下降；7200秒性能停止，native summary与完整端点比较缺失。whole-watchdog `7213.133929461241 s`（资源时钟导出的stop event `7200.713435649872 s`，后续清理`12.420493811368942 s`），树RSS峰`27098828800 B`，task swap峰0；cleanup另有cache-stability异常，最终观察到后代清除但仅列有限清理证据。详见[完整V3 compact](records/v3_formal_diagnostic_closeout_v1.json)、[实际launch excerpt](records/A2_q3_actual_launch_process_excerpt_v1.json)和[tracked root终态审计](records/v3_root_post_pde_audit/A2_q3_terminal_audit.json) |
| 总账 | V2三次 `4915.1723896381445 s`；V3两次 `7372.49412643211 s`；五次formal watchdog小计 `12287.666516070254 s` | 只相加whole-watchdog wall，不含支持工作、未监控检查或R8不完整历史；RSS峰不可相加，也不是完整campaign成本 |

A2_q3正常修正后的primary-before-extra指标由root从保存的raw vectors独立重算为：returned condensed `b−Ax`相对值`3.0440529386035694e−12`、full-active transformed `1.1972486317982494e−11`、独立原方程A6 `3.078522812304335e−10`，均低于各自冻结门。旧Y6_1→primary的612通道功率最大绝对差`4.507666462316706e−11`（限值`1e−7`，0通道失败）；四组边界复幅最大归一差`6.139994079567577e−11`（`1e−5`），能量闭合`5.071976172388304e−11`（`1e−5`）。q8/q10样本分别有516096/1008000个正权Gauss点，域体积约350000 nm³；E/H、散射E/H与G中最大归一差`6.04423083302925e−11`（`1e−5`）。native完整`comparison_record.json`未产出；root已独立复核保存的primary场和原向量，这些属于partial raw audit，不等于完整端点比较。root没有重新积分A_volume，而读取现有hash绑定材料积分记录；不作相位拟合。完整raw值和输入hash见[primary raw audit](records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json)，SHA256 `95524c004138eecbf59ce6a61cc87426558ea10746caee1f06164d93273d49ba`。

extra后 full-active explicit residual从`1.1972486318e−11`升至`1.2068417985e−11`，没有严格下降，故extra不确定性门为负；condensed从`3.0440529386e−12`降至`2.4209863927e−12`，A6从`3.0785228123e−10`降至`3.0781012464e−10`。extra raw向量未保存，这些extra标量没有独立raw重算。没有extra样本、native summary或完整comparison record；不得由primary partial的数值接近推出完整端点、积分通过、截断通过或空间精度。

V2 Stage1与V3 G0–G4原件、校验及支持性费用索引见[V3 pre-PDE证据索引](records/v3_root_pre_pde_audit/index.json)；三次V2 dispatch及历史原件见[V2 formal compact](records/v2_formal_attempts_and_profile_fix_v1.json)。A1_q2此前签发的READY已被实际入口没有workflow ledger这一事实反证，仅作为历史授权保留；A2_q3 READY只授权过该次dispatch。A1/A2各组额度均耗尽，不再重试或重分配；A1_R、A2_R、B、C未运行，剩余额度封存。用户要求的五项能力、逐项审查回应与合并边界见[Response V3](../response_v3.md)。

以下统一模型表、选择轨迹和原最终测试均为V1历史结果；除本节明确追加外，不回写任何原场或选择记录。

本任务检验：能否根据真实场差，把有限元单元局部细分（h）或提高表示阶次（p），以相近精度比用户的6×10×6、p6对照使用更少独立未知量。任务书还要求比较同精度的全过程成本，但不要求成本必须获胜。九次中间更新被接受，但最后接受状态仍未满足全部输出精度；第10轮求解数值合格，却因改善未超过事前冻结的参考噪声而未接受。选择已停止，后验holdout/control结果不再反馈选择。

| 最终判断对象 | 当前结论 | 证据与边界 |
|---|---|---|
| G0 身份/环境 | native complex128/int64、MPI1/线程1、CPU1；正式记录分别绑定实际source/ABI/command | R8 supervisor资源终态与h1辅助ABI覆盖缺口单列，不能泛称所有provenance无条件PASS |
| G1 可复现空间／G2 h/p闭环 | 真实场驱动9次接受更新；p3–6变阶及one-level局部h/周期/悬挂的已验组件、完整恢复、独立原方程A6及612已验；level2与跨h转移未资格化 | [最后接受transition9](records/round9_selection_transition9_v1.json)；中间接受不代表最终空间精度 |
| 最后接受状态R9 | FE110472；η_G=3.995683423e−5，J∞=4.065061945；相对Y6_1参考，top/bottom `(0,0,s)`功率绝对差为4.065061945e−6/2.148245071e−6，均超1e−6；holdout另判 | accepted9冻结，不以R10替换 |
| 未接受R10诊断 | 自然到180格全p6、FE118800；G改善8.412900702e−6<ε_G9.088158797e−6，故不产生transition10 | 对Y6_1的自身精度另判：仅top `(0,0,s)`功率绝对差2.837172688e−6超1e−6，另611通道过；[拒绝证据](records/round10_rejected_candidate_v1.json) |
| 真实h动作 | 初始父状态的600叶p3 h1重试完成；A6=8.745351252e−10，η=.245641161、J=300895.081，空间精度未达 | 全任务第14次求解尝试，属于原h1谱系的资格重试，不修改transition1；[真实h记录](records/h1_real_action_qualification_v1.json) |
| G3 独立后验验证 | q8/q10九对完成，R9/R10对Y5_1均仍FAIL；以Y3为reference的R10对照单对PASS，Y3/Y3_2本身对Y6_1均FAIL；全原数组已独审 | 六场原场比较，无新PDE、无新accepted状态 |
| 更少DoF与同精度成本 | 尚未完整证明 | R9比实际控制237600 FE少53.505%；R10少50%但未接受；单看规模或两场接近不能证明相同精度。任务书要求比较同精度全过程成本，但不要求成本必须获胜 |
| G3未完成资格／G4迭代 | 最终空间精度、参考自身q/R、PDE联合q加严/R14/终点、双侧壁、等精度冷启动成本及可扩展迭代 | 不默认多跑求解追PASS；G3六文件草稿未应用，G4源码只读观察不是实测资格 |
| G5 0.7nm条件pilot | NOT_RUN | 13.5nm最终独立精度及adaptive iterative前置未过，不宣称全尺寸0.7nm/2TB/48h能力 |

## 对象、误差和单位

模型为50×50nm周期、z=−10…130nm计算域，Si块17×20×120nm，波长13.5nm，θ=89°/φ=90°、s偏振。空气n=1，Si光栅及基底n=.999002304859+.00182649365i，ε=n²=.9980022690345409+.0036493427323206554i。所有R/T/A_volume是相对于入射功率的无量纲比例；R00_s、R00_p和两者之和R00_total分开报告。电场和旋度从原高阶系数恢复，在共同物理积分点评价；H按原物理单位定义由curl(E)恢复。G把电场和curl(E)/k0的差合并，按单位入射场尺度归一，表示相对于有限离散参考的差，不是已知连续真误差。

J∞把每个输出误差除以该输出允许值再取最大值，只有J∞≤1才表示整组通过。逐通道功率及R00_s/p允许绝对差1e−6，R/T/A_volume/R00_total为1e−5；E/H/G与四组复边界幅的固定入射地板归一误差为1e−4。弱量的原始相对误差另列，不能因采用地板就宣称原始相对误差也达标。Y6_1是事前固定的选择参考，Y6_2用于冻结参考噪声；二者及后验Y5_1都只称可用有限离散参考，未证明连续收敛。

## 统一模型结果

| 模型与作用 | 单元/阶次；独立FE=trace+interior | R / T / A_volume | 原方程/精度资格 |
|---|---|---|---|
| 初始正式current | 180格p3；15120=8640+6480 | .807473677583 / .005279003523 / .187247318894 | A6=2.3848e−10；η=.428071730，远未达精度 |
| R1已接受中间状态 | 180格；FE19679 | 0.619051847080 / 0.012126176567 / 0.368821976411 | η=0.292759，J=367686；离散残差通过，非最终精度通过 |
| R2已接受中间状态 | 180格；FE32358 | 0.385363241190 / 0.023644896449 / 0.590991862361 | η=0.124587，J=134008；离散残差通过，非最终精度通过 |
| R3已接受中间状态 | 180格；FE43208 | 0.293641473138 / 0.037723817989 / 0.668634708875 | η=0.048336，J=42271.5；离散残差通过，非最终精度通过 |
| R4已接受中间状态 | 180格；FE53659 | 0.258839644327 / 0.052155779229 / 0.689004576445 | η=0.00954282，J=7475.08；离散残差通过，非最终精度通过 |
| R5已接受中间状态 | 180格；FE70212 | 0.254762604502 / 0.056767101216 / 0.688470294283 | η=0.00341154，J=3407.04；离散残差通过，非最终精度通过 |
| R6已接受中间状态 | 180格；FE83959 | 0.251540795421 / 0.057013313685 / 0.691445890896 | η=0.000409699，J=182.906；离散残差通过，非最终精度通过 |
| R7已接受中间状态 | 180格；FE97557 | 0.251411251282 / 0.057119092082 / 0.691469656635 | η=0.000194591，J=54.875；离散残差通过，非最终精度通过 |
| R8已接受中间状态 | 180格；FE106725 | 0.251367166961 / 0.057123097324 / 0.691509735713 | η=0.000125888，J=10.6024；离散残差通过，非最终精度通过 |
| R9最后接受状态 | 180格，p5/p6=28/152；110472=35352+75120 | .251358530702 / .057125858956 / .691515610340 | A6=8.153704654e−9；独立612和全场已审，最终精度FAIL |
| R10未接受诊断 | 180格全p6；118800=37800+81000 | .251357303795 / .057127637031 / .691515059173 | A6=8.164074071e−9；噪声接受门失败与R00_s精度失败分开 |
| h1真实局部细分 | 600格p3；47235=25635+21600 | 0.552257539830 / 0.015288131019 / 0.432454329152 | A6通过，完整场比较空间精度未过；非新接受状态 |
| Y6_1选择参考／噪声校准 | 576格p6；原恢复约束推得FE380160=120960+259200 | 0.251354466181 / 0.057128007072 / 0.691517526782 | 仅有限离散参考；相互差用于冻结ε，未证明连续/q/R收敛 |
| Y6_2选择参考／噪声校准 | 576格p6；原恢复约束推得FE380160=120960+259200 | 0.251354507926 / 0.057128001222 / 0.691517490858 | 仅有限离散参考；相互差用于冻结ε，未证明连续/q/R收敛 |
| Y5_1独立holdout | 504格p6；332640=105840+226800 | 0.251354516833 / 0.057128000037 / 0.691517483140 | 恢复原12800点及612身份过；参考自身q/R未资格化 |
| Y3控制，轴分布1 | 360格p6；237600=75600+162000 | .251357176873 / .057127628246 / .691515194892 | 与第二轴分布同阈值并列；不是新源码fresh solve |
| Y3_2控制，轴分布2 | 360格p6；237600=75600+162000 | .251541084721 / .057101768811 / .691357146465 | 不择有利轴分布；独立比较结果另列 |

控制的237600 FE来自实际恢复：244644个存储系数减7044个独立Floquet从属行，并与周期边/面实体公式交叉一致。Y5_1为341436−8796=332640；不得把存储长度当作独立未知量。恢复只验证原场身份，不把历史求解提升为当前源码的新A6/q/R资格。

## 全部模型的功率与独立自由度

下表统一分开零级 s/p 反射功率与二者之和；`R/T/A_volume`均为相对入射功率的无量纲比例，FE是完整场的独立未知量。该表和[旧inventory V1](records/unified_model_attempt_inventory_v1.json)仅覆盖V1的16次完整求解尝试（12条lineage）以及5份从旧任务导入的场；它不包括V2/V3后续formal dispatch。缺值写“—”，表示未产出或历史未记录。V2/V3新尝试见本页开头的独立版本表与[V3 compact](records/v3_formal_diagnostic_closeout_v1.json)。

| 模型/尝试 | 角色与状态 | R00_s | R00_p | R00_total | R_total | T_total | A_volume | 独立FE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 初始正式current | official_initial | 0.807460399 | 1.23971096e-26 | 0.807460399 | 0.807473678 | 0.00527900352 | 0.187247319 | 15120 |
| 初始tightening校准 | same_initial_lineage_tightening_calibration | 0.807460399 | 1.23971096e-26 | 0.807460399 | 0.807473678 | 0.00527900352 | 0.187247319 | 15120 |
| R1已接受 | accepted_update | 0.619007975 | 8.17053137e-22 | 0.619007975 | 0.619051847 | 0.0121261766 | 0.368821976 | 19679 |
| R2已接受 | accepted_update | 0.385330141 | 2.17040981e-25 | 0.385330141 | 0.385363241 | 0.0236448964 | 0.590991862 | 32358 |
| R3已接受 | accepted_update | 0.293593838 | 2.0686056e-24 | 0.293593838 | 0.293641473 | 0.037723818 | 0.668634709 | 43208 |
| R4已接受 | accepted_update | 0.258797391 | 4.10463802e-24 | 0.258797391 | 0.258839644 | 0.0521557792 | 0.689004576 | 53659 |
| R5已接受 | accepted_update | 0.254729354 | 1.85146e-24 | 0.254729354 | 0.254762605 | 0.0567671012 | 0.688470294 | 70212 |
| R6已接受 | accepted_update | 0.251505217 | 8.28547881e-24 | 0.251505217 | 0.251540795 | 0.0570133137 | 0.691445891 | 83959 |
| R7已接受 | accepted_update | 0.251377186 | 3.08792789e-24 | 0.251377186 | 0.251411251 | 0.0571190921 | 0.691469657 | 97557 |
| R8已接受（资源终态缺失） | accepted_update | 0.251332914 | 9.87086852e-24 | 0.251332914 | 0.251367167 | 0.0571230973 | 0.691509736 | 106725 |
| R9最后接受 | accepted_update | 0.251326376 | 1.56664477e-23 | 0.251326376 | 0.251358531 | 0.057125859 | 0.69151561 | 110472 |
| R10拒绝诊断 | solver_qualified_but_rejected_G_noise | 0.251325148 | 1.61235584e-23 | 0.251325148 | 0.251357304 | 0.057127637 | 0.691515059 | 118800 |
| h1真实资格重试 | same_h1_lineage_real_h_qualified_not_spatial_accuracy | 0.552217392 | 2.78843677e-25 | 0.552217392 | 0.55225754 | 0.015288131 | 0.432454329 | 47235 |
| h1原尝试（中断）；FE未形成 | interrupted_unknown_sender_no_Task43_official_field | — | — | — | — | — | — | — |
| R2 p前置失败 | full_active_preflight_failed_before_checkpoint_A6 | — | — | — | — | — | — | — |
| R5 p性能停止 | root_performance_stop_no_numerical_or_resource_failure | — | — | — | — | — | — | — |
| Y6_1 | potential_selection_reference_only（历史导入场） | 0.251322311 | 7.48016072e-22 | 0.251322311 | 0.251354466 | 0.0571280071 | 0.691517527 | 380160 |
| Y6_2 | potential_reference_uncertainty_calibration_only（历史导入场） | 0.251322353 | 2.41152266e-21 | 0.251322353 | 0.251354508 | 0.0571280012 | 0.691517491 | 380160 |
| Y5_1 | potential_independent_validation_only（历史导入场） | 0.251322362 | 9.39122516e-22 | 0.251322362 | 0.251354517 | 0.057128 | 0.691517483 | 332640 |
| Y3 | post_selection_control_only（历史导入场） | 0.251325022 | 2.87476237e-23 | 0.251325022 | 0.251357177 | 0.0571276282 | 0.691515195 | 237600 |
| Y3_2 | post_selection_control_only（历史导入场） | 0.251508932 | 1.41535558e-22 | 0.251508932 | 0.251541085 | 0.0571017688 | 0.691357146 | 237600 |

## 新求解尝试的矩阵规模、阶段时间与完整watchdog成本

矩阵 `rows` 是实际增广求解行数，`operator NNZ` 是主算子非零元；`factor NNZ`按保存的因子矩阵统计字段，缺失值不补推。阶段秒数分别为base装配、modal vector/loop、KSP setup、KSP solve；它们属于阶段计时，不应与watchdog总墙钟相加。RSS是同时进程树采样峰值，不能与因子对象估算或旧场restore wall混称。

| 模型尝试 | FE | 增广rows | 算子NNZ | factor NNZ | base s | modal-vector s | modal-loop s | setup s | solve s | watchdog wall s | 同时树RSS峰 B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 初始正式current | 15120 | 9252 | 2420652 | 11483200 | 14.2500717 | 133.452064 | 134.322115 | 18.4296402 | 0.0938721243 | 395.323212 | 1270714368 |
| 初始tightening校准 | 15120 | 9252 | 2420652 | 11483200 | 24.842582 | 214.756265 | 216.106203 | 27.0407565 | 0.0938700577 | 930.666683 | 1428434944 |
| R1已接受 | 19679 | 10499 | 3049725 | 13886615 | 90.5763747 | 684.456267 | 686.372159 | 56.3585063 | 0.166632471 | 1694.68647 | 1438400512 |
| R2已接受 | 32358 | 14214 | 5643898 | 26989198 | 326.777651 | 968.483086 | 971.016051 | 109.333289 | 0.213721001 | 2252.18298 | 2165133312 |
| R3已接受 | 43208 | 17054 | 7862404 | 39661072 | 220.059671 | 871.731412 | 873.590805 | 174.504988 | 0.339726021 | 2448.93437 | 2783928320 |
| R4已接受 | 53659 | 20047 | 10274139 | 54095179 | 600.437677 | 795.858643 | 797.367189 | 378.354896 | 2.12651468 | 3704.76166 | 3752202240 |
| R5已接受 | 70212 | 24486 | 14583076 | 72608080 | 1051.43416 | 464.348769 | 469.891188 | 1000.19201 | 2.73116622 | 3150.03959 | 4975054848 |
| R6已接受 | 83959 | 27973 | 18441921 | 92517035 | 1588.02764 | 417.42067 | 421.901215 | 70.2348844 | 1.15817477 | 2918.3594 | 5598105600 |
| R7已接受 | 97557 | 32289 | 23873213 | 120398039 | 1205.70547 | 657.165467 | 663.15001 | 62.2401707 | 2.44564716 | 2740.41261 | 6623186944 |
| R8已接受（资源终态缺失） | 106725 | 34947 | 27580627 | 143208081 | 1083.11582 | 874.167547 | 881.910048 | 103.140333 | 3.05978938 | — | — |
| R9最后接受 | 110472 | 35964 | 29002434 | 153262664 | 563.106629 | 1003.34783 | 1013.61934 | 128.210813 | 3.26078245 | 2878.93479 | 6283513856 |
| R10拒绝诊断 | 118800 | 38412 | 32419692 | 168268752 | 156.7229 | 916.661083 | 925.517092 | 140.265198 | 4.38344608 | 2588.5174 | 6572441600 |
| h1真实资格重试 | 47235 | 26247 | 6696599 | 38540453 | 452.698301 | 376.332197 | 379.66178 | 19.4492559 | 1.457131 | 1547.41297 | 2051149824 |
| h1原尝试（中断） | — | — | — | — | — | — | — | — | — | 2430.82857 | 2904961024 |
| R2 p前置失败 | — | — | — | — | — | — | — | — | — | 1283.60544 | 1965150208 |
| R5 p性能停止 | — | — | — | — | — | — | — | — | — | 2230.24047 | 2911133696 |

R8 PDE原始supervisor终态缺失；表中该行watchdog wall/RSS留空，单独保留2491个采样点、3109.389197s观察窗下界和窗内RSS峰6844891136B（不是全程值）。后三个失败/停止运行的rows与算子NNZ为空，是因为未形成完整候选模型。五份导入场的FE来自恢复后约束计数；其原历史求解时间在inventory内保留，但与本分支PDE或冷启动成本不可直接比较。

## 每轮真实动作与闭包

标记使用原θ=.5最小贡献集合；p6已饱和格保留在标记中，不剔除后重排。闭包是为维持相邻、材料和周期连接而额外调整的单元。h只给内部行下界时，actual trace/总FE保持null，不冒充已构建空间或h求解失败。

| 轮次 | 标记/可升/饱和；额外p闭包 | p实际FE=trace+interior；η_G / J∞ | h请求+闭包；叶数；独立FE | 选择/未运行分类  p PDE完整wall(s) |
|---|---|---|---|------|
| 1 | 46/46/0；+0 | 19679=9887+9792；0.292759 / 367686 | 46+14；600；47235=25635+21600 | p接受；h原实际运行后中断、排名受支配，后补真实资格  1694.686 |
| 2 | 51/51/0；+41 | 32358=13602+18756；0.124587 / 134008 | 51+6；579；80028=35208+44820 | p接受；h按界剪枝  2252.183 |
| 3 | 60/60/0；+9 | 43208=16442+26766；0.048336 / 42271.5 | 60+0；600；103652=41804+61848 | p接受；h按界剪枝  2448.934 |
| 4 | 57/57/0；+9 | 53659=19435+34224；0.00954282 / 7475.08 | 57+31；796；127397=53339+74058 | p接受；h按界剪枝  3704.762 |
| 5 | 60/53/7；+30 | 70212=23874+46338；0.00341154 / 3407.04 | 60+30；810；215092=78010+137082 | p接受；h按界剪枝  3150.040 |
| 6 | 48/48/0；+12 | 83959=27361+56598；0.000409699 / 182.906 | 48+1；523；171122=60020+111102 | p接受；h按界剪枝  2918.359 |
| 7 | 54/52/2；+0 | 97557=31677+65880；0.000194591 / 54.875 | 54+25；733；273728=89114+184614 | p接受；h按界剪枝  2740.413 |
| 8 | 31/31/0；+0 | 106725=34335+72390；0.000125888 / 10.6024 | 31+17；516；251732=80222+171510 | p接受；h按界剪枝  null；R8仅采样窗下界3109.389s |
| 9 | 39/13/26；+0 | 110472=35352+75120；3.99568e-05 / 4.06506 | 39+52；817；actual=null；内部下界309060 | p接受；h按界剪枝  2878.935 |
| 10 | 46/28/18；+0 | 118800=37800+81000；3.15439e-05 / 2.83717 | 46+36；754；actual=null；内部下界292260 | p噪声门拒绝；h对更少DoF目标推导不可行，非score剪枝  2588.517 |

h9内部309060行只给ΔFE≥202335，足以构成更保守的分数上界并被R9严格支配。h10内部292260行已高于控制实际237600，合法空间还需非负trace未知量，所以这个被冻结h动作不可能满足更少DoF目标；没有为它构建完整authority或求解，也不把它说成数值失败。表列wall只指相应p PDE完整watchdog；失败、计划、transfer、比较等成本不隐去，另由最终watchdog清单逐项列出，不与嵌套阶段重复相加。逐轮原计划、评分、资源与负结果见[records索引](#证据与审阅入口)。

## 网格、阶次和独立未知量

![R9真实网格与单元阶次](figures/accepted9_mesh_degree.svg)

R9图覆盖三个真实x slab的y-z断面，采用nm等比例坐标；不是三维透视，也不是所有边/面阶次图。蓝色p5/橙色p6表示单元内部阶次；额外边/面连接由实际authority核算。R10全p6来自原标记规则自然输出，不是事前指定的均匀p扫描。

![真实h1细分层级](figures/h1_mesh_levels.svg)

h1六个x断面显示原根单元及其一次八分子单元；粗单元可横跨两个切片，不能重复计成更多叶。h1始终p3，颜色代表细分层级。共享边/面上的场表达必须一致，因此不能把每个单元局部系数相加当总独立FE。

| 未知量所在位置 | 通俗作用 | 实际计数口径 |
|---|---|---|
| edge/face（单元边与面） | 邻单元连接处共同决定场的切向分量；周期、悬挂连接会进一步消去从属系数 | 合为独立trace：R9 35352、R10 37800、h1 25635；以空间authority和完整A6行数核对 |
| cell interior（单元内部） | 只影响单元内部、在边界迹上为零的自由方向 | R9 75120、R10 81000、h1 21600；p6每格450。内部方向不被trace连接约束消去，因此可用于h9/h10总FE下界 |
| carrier storage / solver rows | p6载体系数用于保存完整场；求解时可消去内部未知量并另加端口模式 | R9独立FE110472，与35964个增广求解行及p6存储长度不是同一量 |

![相对于固定Y6_1的完整接受轨迹](figures/selection_trajectory.svg)

轨迹纵轴为log；空心R10只是被拒绝诊断，不与accepted9连成第10次接受。R10的G下降不足冻结噪声宽度和它自身仍有一个功率通道未达精度，是两个不同判断。

| 空间的实际计划/authority核对 | 周期edge阶次/行 | 周期face阶次/行 | 单元interior | 独立FE |
|---|---|---|---|---|
| R9最后接受 | p5×148、p6×452；3452行 | p5×115、p6×455；31900行 | 75120行 | 3452+31900+75120=110472 |
| R10未接受诊断 | p6×600；3600行 | p6×570；34200行 | 81000行 | 3600+34200+81000=118800 |
| h1真实h | 局部p3；悬挂消元后的edge/face独立行未分别拆存 | 合格authority给合并trace25635 | 600×36=21600行 | 47235；不假造另一次迹实现 |

R9/R10边/面直方图来自原实际degree-map计划的独立周期实体计数，与合格authority/完整A6行吻合；图中cell-p色彩不能代替这些阶次/约束。统一[全部16次正式求解及5份导入场机器表](records/unified_model_attempt_inventory_v1.json)另绑定每次原record/summary/watchdog，覆盖R00_s/p/total、rows/NNZ、阶段wall/树峰及source/ABI；未测和历史局部界保持null/明确分类。

## 停止选择后的独立九组比较

联合全部六场真实网格断点：1008子盒，q8共516096点、q10共1008000点。每场每级q仅采样一次，全部九对采用表列reference方向；不拟合相位。下表列q10结果，q8判定完全相同。E/H/G均采用固定入射地板归一，允许值1e−4；612逐通道功率绝对差允许1e−6；J∞≤1才整组通过。总场与散射场分别原数组重算；[后验compact](records/post_selection_existing_fields_validation_v1.json)逐对列出全部超限通道键、实测绝对差和1e−6限值，并保存六项E/H/curl/G全量指标（含原始相对差与归一地板值）、四组边界幅值及R/T/A_volume绝对差。

| reference → 比较场 | E / H / G归一差 | 最大逐通道功率差；超限数/612 | J∞ / 全组 |
|---|---|---|---|
| Y5_1 → round9_p_up | 1.46658029e-05 / 5.43083889e-05 / 3.97774237e-05 | 4.01441042e-06；2/612 | 4.01441042 / FAIL |
| Y5_1 → round10_p_up | 1.3063896e-05 / 4.22834213e-05 / 3.12933946e-05 | 2.78652117e-06；1/612 | 2.78652117 / FAIL |
| Y3 → round9_p_up | 1.30397525e-05 / 3.46511519e-05 / 2.61795481e-05 | 1.76948798e-06；2/612 | 1.76948798 / FAIL |
| Y3 → round10_p_up | 1.15035872e-05 / 6.94504937e-06 / 9.50174274e-06 | 1.26453607e-07；0/612 | 0.126453607 / PASS |
| Y3_2 → round9_p_up | 0.00017700409 / 0.000388568229 / 0.000301923597 | 0.000182556013；2/612 | 182.556013 / FAIL |
| Y3_2 → round10_p_up | 0.00017821785 / 0.000388298276 / 0.000302106896 | 0.000183783902；2/612 | 183.783902 / FAIL |
| Y6_1 → Y5_1 | 8.02181172e-07 / 5.91679001e-06 / 4.2220788e-06 | 5.06515217e-08；0/612 | 0.0591679001 / PASS |
| Y6_1 → Y3 | 6.2241412e-06 / 4.20736957e-05 / 3.00743728e-05 | 2.71071908e-06；1/612 | 2.71071908 / FAIL |
| Y6_1 → Y3_2 | 0.000179893749 / 0.000389542324 / 0.000303401535 | 0.000186621075；2/612 | 186.621075 / FAIL |

独立holdout Y5_1以Y6_1为reference通过本次有限离散比较，但R9与R10对Y5_1仍分别有2和1个零级功率通道超限。两控制都未通过同Y6_1的全向量阈值：Y3只有零级s功率差2.710719081e−6超限；Y3_2还出现E/H/G、top_s复幅与R/T/Av差超限。以Y3为reference时R10对照的PASS只说明这两个有限离散场彼此接近，不能用这个有利轴分布替代holdout或宣称独立最终合格。

q8→q10的全部九组归一指标变化最大为4.09006162e-13倍最终容差，任何冻结PASS/FAIL均未改变。绝对差范数变化也完整保存，G最大2.06501483e-14；不另造硬阈值。这仅支持本次后处理积分稳定性，不是PDE积分加严、R14、参考自身q/R或连续精度资格。选择已停止，不因后验结果增加accepted状态。

## 成本、失败和未完成项

56份完整模型/组件watchdog wall小计63340.73598930752s；另历史R8仅有3109.3891972089186s采样窗下界，合计66450.12518651644s。final focused/full repository测试另有135.193513449747s watchdog wall，作为测试费用单列；把这些明确观测相加为66585.31869996618s下界，但它仍不是完整campaign成本，也不是完整R8耗时。未监控工作/测试及导入参考生成另列。16次完整求解尝试来自12条科学谱系，accepted9；后验恢复/比较未增加PDE。

| 关键运行 | 完整wall / 进程树RSS峰 | 资源与口径 |
|---|---|---|
| R9 PDE / 比较 | 2878.934788s / 6,283,513,856B；281.777613s / 1,126,117,376B | 完整资源/清理通过，task swap0 |
| R10 PDE / 比较 | 2588.517400s / 6,572,441,600B；279.032614s / 1,140,314,112B | 完整资源通过；base156.723s已含空间准备，先前authority206.957s不重复加到PDE |
| 真实h1重试 | PDE1547.412973s；两次比较623.859s失败+712.541s成功均留存 | 初次比较属旧initial-schema兼容缺口，局部修复后仅重跑比较，非h数值失败 |
| 历史R8 PDE | summary缺失；2491样本至3109.389197s，窗内观测峰6,844,891,136B | shell143、sender未知；不得称全程峰/全程零swap/exit0或完整成本；后续成功不修补它 |

资源峰指同一时刻整个进程树RSS，不是因子对象字节、单进程峰或对象累加。原WSL-global文字保留，实际是native host全机诊断；全机swap增量不直接归因Task43。各正式run的gate在启动前登记，未运行中静默延长。共享JIT不等于冷启动，均无CI通过或同问题后端加速结论。

### V1最终本地检查（历史记录）

| 检查 | 实际结果 | 证据和范围 |
|---|---|---|
| Task-focused suite | 40 passed、3 skipped；pytest报告21.25s，watchdog 30.923094s、树RSS峰386,138,112B、swap增量0、exit0清理 | 916源码/56输入hash与进程采样由root复核；无新PDE，[测试compact](records/final_test_attempts_v1.json) |
| 全仓pytest | collection中1 skip、8 errors，测试体0执行；pytest报告91.42s，watchdog104.270419s、树RSS峰406,917,120B、swap增量0、exit2清理 | 1个Task43 ignored-artifact模块名冲突、1个SLEPc注册冲突、6个旧ignored Task42 scratch缺模块；保留真实trace，不写成8个测试体失败或“0 tests collected”；无CI声明，见[测试compact](records/final_test_attempts_v1.json) |
| 已有registry文档合同 | `src/test/test_183_development_model_registry_markdown.py`：5 passed / 0.08s | 在最终模型总账修改后定向重跑；不涉及PDE，stdout/exit由送审包验证compact绑定 |
| 报告工具与文档合同 | 最终三脚本Ruff format/check、compileall及JSON/XML/Markdown表格/本地链接/hash合同逐项核验 | 实际命令、日志和逐文件哈希绑定在[送审包验证compact](records/final_review_package_validation_v1.json)；局部检查不等于全仓测试通过 |

| 必须保留的负项/缺口 | 最终解释 |
|---|---|
| R5 p attempt1性能停止2230.240470s | 主控性能停止，非用户发起/数值方法失败；严格零载荷组件修复成本保留 |
| 原h1停止 | 原记录USER_CONTROLLED_STOP枚举保留，但无sender证据且用户未发起；新h1资格重试不改旧证据 |
| h1辅助ABI JSON被误覆盖 | 原独立文件旧字节不能恢复；原worker前置ABI和数值/资源验证仍有效；证据链辅助缺口不伪造补写 |
| 旧source清单缺项 | R5原40文件清单漏transfer；真实运行中补充身份与原时间分类保留，不倒写为pre-run |
| p4 golden hash、组件负项、JSON末尾失败 | 原失败与serial/MPI组件修复证据均保留；不因文档修改重算昂贵PDE |
| 最终G3/G4 | 无最终空间精度PASS，不默认再跑baseline/q19q32/R14/终点；双侧壁trace、参考自身q/R、可扩展迭代及等精度冷成本仍未完成 |

## 证据与审阅入口

基线`405e3aff42ac421a4c99315df1ed9b96941ecbe4`。后验数值与比较器及focused/full pytest均使用source HEAD `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`；历史PDE仍以各自run的source snapshot/dirty map为准。三份报告生成器是在本次送审diff中新加入，分别由统一模型表、cycle index与图provenance中的脚本SHA绑定；最终送审commit将绑定它们。大型mesh/field/matrix/timeline保持ignored，Git保存图、生成脚本、轻量hash证据和报告，原source/ABI/命令/原数组hash由compact指向canonical artifacts。

| 类别 | 入口 |
|---|---|
| 起点/参考与冻结合同 | [正式起点](records/initial_current_and_reference_restore_v1.json)、[参考公共比较](records/reference_comparison_v1.json)、[接受合同](records/round1_acceptance_contract_v1.json)、[控制身份](records/final_control_contract_v1.json) |
| 接受历史1–9 | [R1](records/round1_selection_transition1_v1.json)、[R2](records/round2_selection_transition2_v1.json)、[R3](records/round3_selection_transition3_v1.json)、[R4](records/round4_selection_transition4_v1.json)、[R5](records/round5_selection_transition5_v1.json)、[R6](records/round6_selection_transition6_v1.json)、[R7](records/round7_selection_transition7_v1.json)、[R8](records/round8_selection_transition8_v1.json)、[R9](records/round9_selection_transition9_v1.json) |
| 后续负结果与后验准备 | [R10拒绝](records/round10_rejected_candidate_v1.json)、[真实h1](records/h1_real_action_qualification_v1.json)、[后验接线/测试](records/post_selection_existing_fields_preparation_v1.json)；[六场q8/q10联合结果](records/post_selection_existing_fields_validation_v1.json)；root raw/resource audit已hash绑定且通过 |
| 组件与成本边界 | [G1](records/g1_components_v1.json)、[36格后端同问题资格](records/direct_factor_backend_component_v1.json)、[零载荷投影修复](records/sparse_zero_skip_component_v1.json) |
| 审阅交付 | [response](../response_v1.md)、[依赖组manifest](selective_merge_manifest.md)、[测试compact](records/final_test_attempts_v1.json)；PARTIAL/CONTROLLED_NEGATIVE，等待ChatGPT外部审阅，未获merge approval |

## V2诊断尝试与最终收口

Stage1 Q01–Q08工程补账后，按冻结V2计划启动了3次正式诊断。三次均在取得所有端点资格证据前以工程错误结束；它们不能解释为h/p方法数值失败，也没有给出完整q/R扰动结论。三份原始watchdog与root审计保留在[V2正式尝试compact](records/v2_formal_attempts_and_profile_fix_v1.json)中。

| 诊断端点 | 实际结果 | 原始观测和具体缺项 |
|---|---|---|
| A1_q attempt1 | worker在结果广播时失败；不是数值方法失败 | watchdog wall 4,882.447373806033s，采样进程树RSS峰9,708,847,104B、task-tree swap峰0、3,930个样本、后代清理。observer含嵌套`MappingProxyType`，mpi4py无法pickle。saved 612-modal比较有很小差值，但缺primary场样本和primary/extra独立A6持久记录，故endpoint不合格。 |
| A2_q attempt1 | 缺watchdog phase-path参数，在网格/PDE前退出 | watchdog wall 18.740401392802596s、RSS峰190,795,776B、task swap0、15个样本；60个源码/34个输入前后hash一致；数值输出为空。 |
| A2_q attempt2 | 原生resolved-profile元数据检查在网格前拒绝 | watchdog wall 13.984614439308643s、RSS峰190,918,656B、task swap0、12个样本；60个源码/42个输入前后hash一致，真实phase与ABI门通过。旧Y6_1文件只缺`display_label=D15-Y6-1`；没有mesh、装配、R/T/A、NNZ、残差或场输出。计划Y6的576 cells/380,160 FE不是本次装配实测。 |

三次正式watchdog wall合计4,915.1723896381445s。该值仅合计上述正式dispatch完整watchdog wall；component测试、支持性preflight、旧场恢复和root审计另列。56份历史summary小计63,340.73598930752s以及R8不完整采样窗下界3,109.3891972089186s仍保持V1 Q04账本口径，不合并成全campaign总成本。

预算实际为3/6：A1_q 1次、A2_q 2次。A2配额2/2已用尽；A1_q没有完整endpoint/A6证据，故A1_R冻结前置不成立。A2_R未运行，其中一个原A2_R槽位按前瞻授权仅重分配一次给A2_q attempt2。A1未资格化，因此B和依赖B的C锁定；没有跨组或进一步重分配，也没有任何后续模型获准启动。

随后提交的profile兼容修复只针对hash绑定的旧Y6_1 resolved config：在内存副本中补齐唯一缺失的`display_label`，确认其余数值/资源事实完全一致，并调用原生`_validate_resolved_profile`。原resolved文件和native默认validator未修改。26个helper测试通过，真实read-only frozen-input preflight也通过；该修复属于组件/profile兼容性，不是fresh PDE，且没有重开已耗尽的A2预算。

V1的最后接受态仍是R9（110,472 FE），最终空间精度不达标；R10因改善小于冻结噪声而拒绝。V2没有完整积分/端口扰动结论、独立q/R资格或h见证，也不改变上述科学判断。五项能力、Q01–Q08逐项回应、各次成本、root原件审计和测试命令见[response V2](../response_v2.md)与上述compact。Task43保持`PARTIAL / CONTROLLED_NEGATIVE`并等待外部审阅；未获merge approval，也未合入master。

正式尝试以外的支持工作入口、可计量的独立watchdog费用、未监控时间的`not_measured`标记和保留的前置失败列于[V2 compact的support_work](records/v2_formal_attempts_and_profile_fix_v1.json)。这些费用不并入4,915.1723896381445s formal watchdog subtotal，也不拼成全campaign总额。

## V3整改与待审的有限诊断

V3已派发一次A1_q attempt2，预算累计4/6。实际入口构建了180格网格并进入装配路径，但未留下因子分解或求解完成证据；主控发现A1路径没有接入要求的WorkflowLedger后，按指令对该次运行受控停止。该结果是工程接线不完整，不是数值方法失败，也没有official primary/endpoint。原READY只作为这次派发的历史记录，不授权任何后续运行；A2未READY、未派发，A1_R/A2_R/B/C均锁定。原始终态和身份见[A1_q2执行记录](records/a1_q_attempt2/dispatch_and_stop_record.json)及[root独立终态审计](records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json)。

A2真实native入口另有一个受控组件测试：使用冻结Y6输入进入`run_p6_condensed_direct`，由该入口创建绝对phase文件和`stages.jsonl`，随后在首次mesh-builder边界触发sentinel，因此没有真实构网、solver调用或正式attempt消耗。该测试补充native入口的ledger接线证据，不签发A2 READY，见[组件测试记录](records/a2_native_workflow_ledger_component.json)。

Root已复核G1故障注入/默认路径和G2真实watchdog tiny-child链；G0、G3复用带hash的旧记录。最终bounded focused在源码HEAD `81c97e7c`上为57 passed、1 skipped，随后最终HEAD `fc260b1e`上重跑唯一变动的生命周期AST节点，1 passed。跳过项是需显式开启的完整p6 FFCx矩阵见证，本轮未运行。compileall、JSON/Markdown和diff检查通过；Ruff仍有与`fd7ebd2a`基线相同的77项既有诊断，新增诊断为0，因此不称全量Ruff通过。命令、日志hash及root源码审阅见[最终验证索引](records/diagnostic_plan_v3_final_validation.json)和[root G1/G2复核](records/v3_root_final_source_review.json)。

本次A1尝试使用的资源预测为：A1锚点118,800 FE（37,800 trace+81,000 interior）、38,412行、32,419,692个已用矩阵非零元；旧 q15 R10 的进程树RSS峰为6,572,441,600B，而此前q19/q32 A1_q1部分尝试实测峰为9,708,847,104B、全程4,882.447秒，未完成完整端点。A2的Y6_1历史锚点为380,160 FE（120,960 trace+259,200 interior）、121,572行、112,458,734个已用非零元、进程树RSS峰26,919,141,376B。由于新留证会让输出与因子重叠，A1约32GiB、A2约96GiB是保守规划余量，均为预估而非实测峰值；实际仍受7200秒和192GiB硬门约束。60条源码、47项直接输入及7项启动支持hash见[阶段G4 source/input inventory](records/diagnostic_plan_v3_g4_source_input_inventory.json)及[root独立复核](records/v3_root_g4_inventory_recheck.json)，预测假设见[有限资源预估](records/diagnostic_plan_v3_resource_prediction.json)。Root曾完成G0–G4并为A1_q2单次派发签发READY；实际入口的ledger缺口使该次运行受控停止，该READY不再授权后续运行。当前没有后续READY、合并批准或0.7nm运行。


## V2阶段一（Q02–Q08）证据补账

本节追加V2 review证据，不改写V1选择、accepted状态、原负结果和response。当前源码审阅身份为 `fad2df0fb5c15ab1e14fabddf262a772c126cda5`；V1数值/PDE运行仍按原source snapshot，主要数值实现HEAD `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`。阶段一没有启动新正式模型PDE，详细路径、source/input SHA、完整命令和stdout/stderr/exit见[阶段一门索引](records/stage1_gate_v2.json)及Q02–Q08记录。主控将直接诊断门判为PASS_WITH_LIMITATIONS；生产与全仓门仍受SLEPc ABI和tracked collection问题阻塞。任何Stage2模型尝试前仍须提交并审阅V2计划和机器合同。

| 项目 | 已取得事实 | 尚未证明的边界 |
|---|---|---|
| Q02 全仓collection与ABI | 原8个collection error按1个Task43同名忽略artifact、1个SLEPc key1211220注册冲突、6个旧Task42 scratch缺模块逐项索引；clean tracked collection 3121项，另1个SLEPc阻塞；real SLEPc与complex128/int64 PETSc链接不兼容。当前direct regression含40 passed/3个MPI2-only skip；3个skip节点在同模块MPI2两rank另复验通过；空间/局部Schur、mixed p3/p4装配与内场恢复、independent active action为3 passed；当前same-LU 27-cell组件为1 passed，watchdog完整记录。 | 全仓pytest仍在collection中止、0测试体；SLEPc/Hybrid路径受环境阻塞；组件与saved-field fixture不是正式模型资格。原`test_petsc_residual_correction.py`相同测试和实现SHA已有4 passed记录，未重跑。 |
| Q03 selective依赖闭包 | 从干净base405临时worktree叠加66个显式SHA文件；root逐文件核验主树/overlay hash、实际4个import来源、157节点原日志；25个changed-test依赖路径collect-only为0 errors/skip、0测试体。 | import/collection只证明闭包与可收集性，不代替数值测试；本次没有向base/master提交或合并overlay。审核原件`overlay_dependency_audit.json` SHA `439a7bef5f1e7d0982fb3140cc9f6b7d522e75ddddd31733d6040bcd04390015`。 |
| Q04 56份workflow成本清单 | 去重后56份原始summary逐项列路径、hash、原分类及summary记录的whole watchdog elapsed；小计63,340.73598930752s。`post_selection_restore_attempt1`覆盖Y5_1/Y3/Y3_2的完整恢复workflow，原件[`watchdog/summary.json`](../../../benchmarks/artifacts/task43/post_selection_restore_attempt1/watchdog/summary.json) SHA `075c2d9dbc19a0d45dd069288723d6af1806fcc43256d18118c02c41bb05d8b6`记录实测166.96172243729234s，不以总额倒算；root逐项成本审计通过。 | 56条含失败、监控失败、preview、比较和受控/中断记录，不是56次数值成功；R8缺summary，其3,109.389197s只算采样窗下界。审核原件核验56行、58个原件hash、R3原18行与V1 64个不可变文件。 |
| Q05 规则冻结时序 | 冻结acceptance contract SHA在候选pre-run snapshot中匹配，snapshot还列出当时untracked文件。 | 首个candidate之前的严格时间顺序没有独立证明；worker没有写合同hash的前置事件，不能从mtime猜时间。 |
| Q06 p3方向组合 | 将p3加进原有完整D4八变换和256个oriented-child参数组，对应2个新p3节点通过。 | 只资格化这两个p3组件性质，不声称level2、跨h或一般MPI能力。 |
| Q07 R8特例 | 只有`round8_p`且run.resolve精确等于原R8 run root才读取partial审计的观察量，生成器还核partial文件SHA；V2 inventory单独生成，V1 inventory保持字节不变。 | outer exit143、sender unknown、2491样本/3109.389197s观察窗与窗内RSS仍不是全程终态或资源峰。 |
| Q08 registry Markdown | 保留两次相同的5项回归：0.08s和0.11s，最近一次5 passed。 | 这是文档合同，不代表完整文档测试或CI通过。 |

V2 root对六场stored-field replay的14项raw inputs复核与V1 audit逐项hash一致。它从保存样本数组重算612模式Poynting及E/H/G比较，不从系数重采样；A_volume沿用原记录，未重新体积分。另有原残差scalar的算术重组和保存moment检查，但没有新施加完整算子或fresh A6。上述复核的watchdog wall 46.21374210854992s；0.143265s residual arithmetic未监控且不加到watchdog墙钟账。详见[旧场重放V2记录](records/post_selection_old_field_replay_v2.json)。
