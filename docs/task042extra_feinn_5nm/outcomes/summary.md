# Task42extra Review V6 后续：V7 p4装配受控停止

本轮完成了同网格 p3→p4 的完整场/旋度嵌入、原算子配对与数组容量资格，但唯一 p4 参考在装配阶段耗尽数值工作窗口，状态 **P4_REFERENCE_TIME_BLOCKED**。没有获得 p4 参考场，因此未启动 p3/p4 比较，不能判断阶次变化大小。已按预算主动请求自有 watchdog 停止，原因明确；这不是 OOM 或 p4 精度失败证据。

提高阶次让同一个单元内的电场能表达更多细节，几何和网格都不变。准确 p3/p4 场的差可检查离散敏感性，不能直接当连续误差上界；代价是更大的有限元系统及一次独立准确参考。原 NN 对同一 p3 方程的失败与这个精度审计是不同问题，旧结论不改。

| 原方程/功率 / measured、原rhs或入射功率归一 | p3原参考 | p4本轮 | 验收 |
| --- | --- | --- | --- |
| native_relative | 6.78883619212e-12 | NOT_RUN | 参考各≤1e-10 |
| augmented_relative | 6.78883897883e-12 | NOT_RUN | 参考各≤1e-10 |
| original_total_augmented_relative | 3.514516446e-12 | NOT_RUN | 参考各≤1e-10 |
| independent_DOLFINx_total_native_relative | 3.26041877377e-12 | NOT_RUN | 参考各≤1e-10 |
| R_total | 0.812426499057 | NOT_RUN | 不能比较 |
| T_total | 0.0324623960953 | NOT_RUN | 不能比较 |
| A_balance | 0.155111104848 | NOT_RUN | 不能比较 |
| R00_s | 0.812256818464 | NOT_RUN | 不能比较 |
| R00_p | 1.25634444139e-26 | NOT_RUN | 不能比较 |
| R00_total | 0.812256818464 | NOT_RUN | 不能比较 |
| A_volume | 0.155111104847 | NOT_RUN | 不能比较 |

| 阶段 / measured | 完整launcher wall / s | 同时树RSS峰 / B | CPU | 自身swap峰 / B | 实际结果 |
| --- | --- | --- | --- | --- | --- |
| v7_p_transfer_checks | 158.807494071 | 1586601984 | 12 | 0 | U0资格通过 |
| v7_p4_reference | 3452.53531242 | 1289834496 | 11 | 0 | 预算受控停止 |
| v7_p3_p4_compare | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | p4参考未资格化 |

U0现场核实p4含slave78936、slave3672、独立复FE75264（边4992/面28800/内部41472）、40端口，完整矩/非零公共点E/curl/MPC及原action≤1e-10；M5/5nm/384hex/h1.25/体与DtN q15相同，仅p3→p4。数组/转换12GiB规划通过，symbolic/factor容量未完成，不作PASS。

没有p4恢复packet、没有U2或q30差值复核，全部p场/功率/通道/原区域差NOT_RUN，不宣称连续/h/端口收敛。旧e4_p4 not_run、V1–V6所有NN失败和标签血缘保持。新p4仅REFERENCE_ONLY，训练/生产/神经资格仍false。

launcher在 3450.00074385s 到达原3600s的150s收口边界时，由Codex按用户预算请求停止。先核对自有PID/start_ticks和one-run命令，再只向launcher发SIGTERM，由既有watchdog终止/回收自身后代。原分类USER_CONTROLLED_STOP、worker exit−15，descendants_cleared=true；完整退出wall 3452.53531242s，剩余 147.464685061s≥120。本批全部数值阶段树峰 1586601984B（1.47763824463GiB），自身swap0，没有内存硬线、监督失效或OOM证据。

本页冻结前新增全账 3762.8175588s，含正式阶段、全部已完成辅助失败与直接/最终120s保守额度；旧45161.81665198447s及失联3284s/旧Gram/重放费用全部保留。原累计 48924.6342108s，剩 8675.36578922s。浏览器与发布后检查继续补入[最终资源账](records/resource_costs_v7.json)。U0含轻检查181.809311786s≤1200，唯一p4≤3600，新批≤7200/原≤57600均未越线。未取得装配完成timer，写NOT_RETAINED，不重放补计；父wall已包含这段CPU费用，不能重复相加或删除。

C1中断manifest保留p3依赖的provisional operator hash，不能冒充p4；实际输入由U0 hash/冻结依赖与degree4事件核清，原字节不改。C2修正启动前p4身份与长原生调用150s watchdog截止，10项targeted tests通过，未正式重放。[详细审计](p3_p4_authority_v7.md)列明保全与未知因素。

唯一下一步建议：review先决定如何在既定小型authority约束内解除p4装配预算阻塞并冻结比较基准，再决定是否授权[同规模单载波复包络方案](phase_representation_plan_v7.md)的最小完整矩/VJP资格与同预算对照。本批只交计划，不实现训练器、不训练、不自动第二次factor。目标尺寸5nm和0.7nm、p5、h细化、更多端口均未启动；小型p4未完成不能推广为模型不可计算。

[Response V7](../response_v7.md)、[run/source/hash](records/run_index_v7.json)、[U0](records/p_transfer_checks_v7.json)、[p4停止](records/p4_reference_v7.json)、[Gate](records/gate_decisions_v7.json)、[新渲染](records/render_check_v7.json)。实算source 76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2，后来文档HEAD不替代它。以下V1–V6历史原文原样保留。

# Task42extra Review V5 后续：V6 固定特征原方程残差下限

本轮已测得此固定195维特征空间的原方程最小残差，但没有获得物理解资格。V6实际网络 native/augmented 均为 **0.570577990454**，高于严格1e-6；G场误差 **0.569932119000**，散射E L2 **0.569893933222**，scaled-curl/H **0.569933083410**。相比V5，残差降低而场、功率显著变差。分类 `FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED` 只说明线性最小二乘子问题已测完，不表示solver通过或整个网络类不可能。

这一步把已经学到的隐藏特征固定，只重新组合最后一层，使原方程左右两边尽量接近。它回答同一组特征最有利的末层能把原方程残差降到哪里；收益是消除“末层优化还没求好”的不确定性，代价是195次原算子作用、约100MB受限矩阵及稳定分解。隐藏特征曾读过参考场，当前读出只用原载荷f，整条路线仍不是无标签求解。

保持原M5、5nm Si/air、384hex、p3/q15、31968独立复FE（边3744、面14400、内部13824）、2082slave、40端口、材料/背景/MPC/DtN。冻结8576实隐藏参数和坐标buffers，仅改变390实末层参数。复用V5已资格化Phi/Q_eff，不新增列，不重新G-QR；全部内部矩经原网络forward、Piola/orientation/MPC完整生成。

| 同p3参考、无量纲 / measured | V4 final | V5 G最优 | V6残差最优实际网络 | 门限 |
| --- | --- | --- | --- | --- |
| G场误差 | 0.0138716912975 | 0.0115909576376 | 0.569932119 | 三项表示0.001/0.01；物理场各1e-4 |
| 散射E L2 | 0.0132512476647 | 0.0139354062682 | 0.569893933222 | ≤1e-4，V6未过 |
| 散射curl / 完整H_code L2 | 0.0138870027008 | 0.0115255720568 | 0.56993308341 | ≤1e-4，V6未过 |
| total E L2 | 0.00908709789134 | 0.00955626248333 | 0.390807121709 | ≤1e-4，V6未过 |
| total curl / 完整H_code L2 | 0.00949580596642 | 0.00788108119955 | 0.389715051586 | ≤1e-4，V6未过 |
| 六点total复E | 0.00975197801709 | 0.00979563175999 | 0.386657557378 | ≤1e-4，V6未过 |
| 六点total复H | 0.00716738817286 | 0.00774628935817 | 0.383341995305 | ≤1e-4，V6未过 |
| 六点scattered复E | 0.0144133908755 | 0.0144779109614 | 0.571478575904 | ≤1e-4，V6未过 |
| 六点scattered复H | 0.0106715966193 | 0.0115335284392 | 0.570761767393 | ≤1e-4，V6未过 |
| native | 1.60884472011 | 1.97790914967 | 0.570577990454 | ≤1e-6，V6未过 |
| augmented | 1.60884472011 | 1.97790914967 | 0.570577990454 | ≤1e-6，V6未过 |
| 原total augmented | 0.762112577426 | 0.936939047704 | 0.270283798984 | ≤1e-6，V6未过 |
| 独立DOLFINx total | 0.762112577426 | 0.936939047704 | 0.270283798984 | ≤1e-6，V6未过 |

| 入射功率归一 / measured | V4 | V5 | V6 diagnostic |
| --- | --- | --- | --- |
| R | 0.813057790084 | 0.813166677492 | 0.831595684579 |
| T | 0.0327381741782 | 0.0327293240969 | 0.070897304214 |
| A_balance | 0.154204035738 | 0.154103998411 | 0.0975070112071 |
| A_volume | 0.155388025694 | 0.155420108597 | 0.308717201091 |
| R00_s | 0.812608163311 | 0.812222944068 | 0.83153891879 |
| R00_p | 5.02695584979e-05 | 0.000626436218627 | 1.2298159737e-07 |
| R00_total | 0.81265843287 | 0.812849380286 | 0.831539041772 |
| 独立能量闭合绝对差 | 0.00118398995593 | 0.0013161101857 | 0.211210189884 |
| 最大逐级功率差 | 0.000351344847336 | 0.000626436218627 | 0.0385569062796 |

195/195数值秩、经济QR/小R SVD/原网络回写全部合格，但rho0.570578远高于1e-6。G与物理L2/curl加权恒等式差约1.44e-15；相对V5 G最优的勾股缺陷8.44e-15；当前场没有低于V5最佳误差的异常。表示三项均约0.57，高于0.01；严格原方程、场、功率均失败。全40复通道/分母、逐级功率、六点复E/H、材料/界面区域均在[Gate](records/gate_decisions_v6.json)。

| 阶段 / measured | 完整launcher单调wall / s | 监督wall / s | 同时树RSS峰 / B | own swap / B |
| --- | --- | --- | --- | --- |
| v6_operator_readout_checks | 19.5020307989 | 15.379218037 | 967532544 | 0 |
| FEINN-FROZEN-FEATURE-RESIDUAL-READOUT | 48.924852098 | 46.314578537 | 1290457088 | 0 |
| v6_residual_readout_reconstruct | 22.060632084 | 19.683359519 | 536113152 | 0 |
| v6_residual_readout_compare_only | 23.720625111 | 20.4761449989 | 473350144 | 0 |

```text
reference_used_for_training=true
features_reference_exposed=true
readout_rhs_uses_reference=false
pde_only_solve=false
production_initialization_allowed=false
pde_only_solver_qualified=false
official_candidate_results=false
```

这些字段贯穿所有新输入、manifest、PT/NPZ和结果；新状态是parameter-only，没有Adam/L-BFGS历史。权重不得接回旧路线、Task042或0.7nm。准确参考只在冻结后的T2加载；不重新MUMPS求解，没有Gsolve/Gram/Maxwell因子、Krylov或optimizer step。

实际A/A*按列合计206/3，完整native审核4次另列（其中FE含2次独立DOLFINx作用），G合计16列；限值256/8/12/512均未超。新增Gsolve/Gram factor/Maxwell factor/optimizer step均0。原G稀疏payload146851456B、Phi/B各99740160B（数组体积，不是RSS）；旧Gram装配648.765s、历次factor、准确参考和监督特征学习费用保持原账，从零成本不能用本次约49s主阶段代替。

数值树峰1290457088B（约1.20GiB），自身swap采样全0、各阶段完整清场。主阶段完整launcher48.924852s含导入、加载、哈希、A/QR/SVD、存盘和审核；退出剩1751.075s，150s收口和至少120s保存留白通过。组件细分计时未保存，标NOT_RETAINED，不重放补计；父wall完整计费，嵌套/数组payload不重复相加。

本页冻结前V6账约257.8s（含全部已完成辅助及直接/最终120s保守额度）；发布与浏览器费用继续追加[最终资源账](records/resource_costs_v6.json)。旧累计44815.22461795143s和失联/重放成本不删除；本批≤3600s、主阶段≤1800s、T0≤600s及原57600s分别审核。CPU-only、MPI1、数学/Torch1，现场空闲物理核，本批正式CPU12；系统余量216310038528B＋384GiB邻增长＋自身cap，警戒12/硬16GiB，轻测试/浏览器≤2GiB。tmux管理服务器约4.7MB稀疏样本单列，不称连续峰；无cgroup委派，约0.5s树采样监督，不宣称连续内核限额或零干扰。

本轮已排除所测末层布局、两套置换混用、G/物理范数不一致、回写不稳、参考泄漏进读出右端项、q15漂移和最终状态丢失等因素。新残差下限高出1e-6约570578倍，回写原方程分辨差仅2.31e-11；它支持此冻结空间达不到原残差门限的数值结论，不是带区间误差界的数学证书，也不排除改变隐藏参数后的网络。V5 G最优已经不足以让L2/curl同时≤1%，当前读出的约57%场误差不能当有效求解进展。无标签神经增量仍未证明。

**唯一后续设计建议：在原M5上设计包含物理传播相位的隐藏表示，并先冻结其完整矩/原方程验证方案。** 不在本轮实施，不再扫描同一冻结特征的loss或末层超参，不继续hidden训练/VarPro/PDE微调。目标尺寸5nm需另行冻结几何、网格及可扩展求解设计后才可晋级；本轮p4、目标尺寸5nm与0.7nm均not_run。旧V1/V2负结果、V3中断及失联3284s费用不改。

[Response V6](../response_v6.md)、[详细诊断](frozen_feature_residual_v6.md)、[投影](records/residual_readout_projection_v6.json)、[三场CSV](records/residual_readout_comparison_v6.csv)、[run/source/hash](records/run_index_v6.json)、[资源](records/resource_costs_v6.json)、[新渲染](records/render_check_v6.json)。以下V1–V5历史原文保留。

# Task42extra Review V4 后续：V5 固定隐藏层输出诊断

本轮取得了**稳定、实际可回写网络的固定隐藏层投影**，去掉了V4剩余G误差能量的30.180006%，但未获得表示门限或严格物理资格。G场误差 `0.0138716912975` → `0.0115909576376`，散射curl误差下降；散射E L2 `0.0132512476647` → `0.0139354062682`、native `1.60884472011` → `1.97790914967`、复通道和能量闭合反而变差。分类为 `REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED`。固定特征的线性子问题已通过最优性审核；这个分类保留的是整个可变隐藏层网络及PDE求解的未决范围，不表示本轮线性优化又未完成。

本节追加V5，以下V1–V4原文保留。冻结V4 final的8576实隐藏参数与坐标buffers，仅改390实输出层参数；完整边/面/内部矩产生31968复FE，原M5/5nm/384hex/p3/q15/40端口不变。固定特征的线性组合经G-QR＋小R SVD重求一次，没有新增参考生成特征列、Adam/L-BFGS、Gsolve或Gram/Maxwell因子；参考已暴露，只是监督诊断。

| 阶段 / measured | 结果 | 资格边界 |
| --- | --- | --- |
| S0 | 原a0配对3.08e-15；复数/纯虚/bias/三类矩/batch通过；Phi一次14.806s | 不是PDE solver PASS |
| S1唯一投影 | rank195/195，G正交2.32e-13，实际网络最优性1.39e-13，gamma0.301800 | 此固定数值可辨子空间；不推广整个网络类 |
| S2独立ML/FE | 参数→c差0；q30差7.89e-13；新MUMPS0 | 仅复用V1同p3参考 |
| 表示/物理 | 三项未均≤0.01，严格方程/场/功率均失败 | G和curl改善，散射L2/native/通道/能量变差 |
| p4/目标尺寸5nm/0.7nm | not_run | 没有放大或合并授权 |

| 同p3参考 / measured、无量纲 | V4 final | V5实际网络c1 | 门限 |
| --- | ---: | ---: | --- |
| G场误差 | 0.0138716912975 | 0.0115909576376 | 表示正/部分要求三项均≤0.001/0.01，未通过 |
| 散射E L2 | 0.0132512476647 | 0.0139354062682 | 严格≤1e-4，未通过 |
| 散射scaled-curl / 完整H_code L2 | 0.0138870027008 | 0.0115255720568 | 严格≤1e-4，未通过 |
| total E L2 | 0.00908709789134 | 0.00955626248333 | 严格≤1e-4，未通过 |
| total scaled-curl / 完整H_code L2 | 0.00949580596642 | 0.00788108119955 | 严格≤1e-4，未通过 |
| 六点total复E | 0.00975197801709 | 0.00979563175999 | 严格≤1e-4，未通过 |
| 六点total复H_code | 0.00716738817286 | 0.00774628935817 | 严格≤1e-4，未通过 |
| 六点scattered复E | 0.0144133908755 | 0.0144779109614 | 严格≤1e-4，未通过 |
| 六点scattered复H_code | 0.0106715966193 | 0.0115335284392 | 严格≤1e-4，未通过 |
| native / augmented | 1.60884472011 | 1.97790914967 | 各≤1e-6，未通过 |
| 原total augmented | 0.762112577426 | 0.936939047704 | ≤1e-6，未通过 |
| 独立DOLFINx total原方程 | 0.762112577426 | 0.936939047704 | ≤1e-6，未通过 |

| 功率 / measured、入射功率归一 | 同p3参考 | V4 final | V5实际网络c1 |
| --- | ---: | ---: | ---: |
| R | 0.812426499057 | 0.813057790084 | 0.813166677492 |
| T | 0.0324623960953 | 0.0327381741782 | 0.0327293240969 |
| A_balance | 0.155111104848 | 0.154204035738 | 0.154103998411 |
| A_volume | 0.155111104847 | 0.155388025694 | 0.155420108597 |
| R00_s | 0.812256818464 | 0.812608163311 | 0.812222944068 |
| R00_p | 1.25634444139e-26 | 5.02695584979e-05 | 0.000626436218627 |
| R00_total | 0.812256818464 | 0.81265843287 | 0.812849380286 |
| abs(R+T+A_volume−1) | 2.97762e-13 | 0.00118398995593 | 0.0013161101857 |
| 最大逐级功率差 | 0 | 0.000351344847336 | 0.000626436218627 |

| 阶段 / measured | 监督wall / s | 完整launcher单调wall / s | 采样同时树峰 / B | own swap / B |
| --- | ---: | ---: | ---: | ---: |
| v5_readout_checks | 29.1011772191 | 30.969128705 | 711270400 | 0 |
| FEINN-FROZEN-HIDDEN-READOUT-G | 362.10759266 | 364.272690128 | 1673396224 | 0 |
| v5_readout_reconstruct | 17.1475315631 | 19.403170257 | 517783552 | 0 |
| v5_readout_compare_only | 18.6208139439 | 20.795906125 | 462159872 | 0 |

reference_used_for_training=true；pde_only_solve=false；production_initialization_allowed=false；pde_only_solver_qualified=false；official_candidate_results=false。主阶段完整launcher364.273s、树峰1673396224B、自身swap0，120s留白通过；真实M5总G列作用1773≤2500，因子成本新增0，稀疏G/QR/SVD/存盘均包含于实耗。旧累计44119.848638203344s保留，后续辅助与浏览器计费以[最终资源账](records/resource_costs_v5.json)为准，采样峰不相加，管理tmux服务器单列。

[Response V5](../response_v5.md)、[详细诊断](frozen_hidden_readout_v5.md)、[完整通道/区域Gate](records/gate_decisions_v5.json)、[run/source/hash](records/run_index_v5.json)、[投影](records/readout_projection_v5.json)、[新渲染](records/render_check_v5.json)。固定特征里确有更优G组合，但它不足以通过门限，仍不能否定改变hidden后的同架构。下一最小建议交由review决定是否授权区分隐藏特征与原方程约束的单项诊断，本轮不自动实施。

# Task42extra Review V3 后续：V4 持久 Adam500 边界重放

本节追加V4，下面V1–V3历史原文保留。网络读取已知V1参考场作监督标签；本轮修复的是完整step的运行和存盘保全，让固定模型取得可独立审核终态。它不是PDE-only求解，拟合权重不能接回旧路线、Task042或0.7nm。[Response V4](../response_v4.md)、[详细诊断](durable_replay_v4.md)、[run/source/hash](records/run_index_v4.json)、[检查点](records/checkpoint_index_v4.json)。

| V4阶段 / measured | 结果 | 解释 |
| --- | --- | --- |
| R0运行保全 | 9项小tests＋4类进程故障通过；真实M5仅2次loss/gradient | 模拟断开只证明所测路径，SIGKILL只保证先前成功落盘边界 |
| R0 Adam500切换资格 | c/目标/梯度差0；E_G0.2008211341、native14.2634632 | 旧Adam500参数＋确定性重建buffers，创建fresh L-BFGS；817历史未恢复 |
| R1唯一正式后段 | WALL_BUDGET；新2129完整闭包、logical2629、93完整外层step | 末次未完成step回滚，final对应2122闭包边界；7次试探费用照计 |
| R2独立重建与FE compare-only | 参数→q15差0；q30/q15差8.5141e-13；新MUMPS0 | 所有参数、buffer和optimizer保留；V1同p3参考不重求 |
| 表示分类 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED | G/scattered L2/curl三项均未达部分0.01，更未达正0.001；不是数学不可表示证明 |
| 保存留白规则 | C1遗漏导入，至少120s规则未满足；总wall未超3h | C2已改launcher时钟/150s留白且targeted测试通过；未第二次正式运行 |
| p4 / 目标尺寸5nm / 0.7nm | not_run | 原无标签三路线负结果与旧V3中断不改 |

| 同一5nm M5、384hex、p3/q15、31968独立复FE、40端口 / measured | Adam500留存 | V4 final | 标准或参考 |
| --- | ---: | ---: | --- |
| G场误差 | 0.2008211341 | 0.01387169130 | 三项均≤0.001正 / ≤0.01部分，未达部分 |
| 散射E L2 / scaled-curl | 0.1620127280 / 0.2017046510 | 0.01325124766 / 0.01388700270 | 严格各≤1e-4，失败 |
| total E L2 / scaled-curl | 0.111101 / 0.137924 | 0.009087097891 / 0.009495805966 | 严格各≤1e-4，失败；完整H相对差与curl相同 |
| 六点total E / H_code | 0.112268 / 0.132886 | 0.009751978017 / 0.007167388173 | 全复向量及逐点严格≤1e-4，失败 |
| native / augmented | 14.2634632 / 14.2634632 | 1.608844720 / 1.608844720 | 各≤1e-6，失败 |
| 原total / 真出射 / scattered复幅相对差 | 0.137244 / 0.0658706 / 0.243664 | 0.02134370402 / 0.01024394361 / 0.03789375775 | 各≤1e-4；四类40级复值及各自分母见Gate |
| R/T/A_balance/A_volume | 0.828087/0.0419968/0.129916/0.171617 | 0.8130577901/0.03273817418/0.1542040357/0.1553880257 | 参考0.8124264991/0.03246239610/0.1551111048/0.1551111048；仅diagnostic |
| R00_s / R00_p / R00_total | 0.806827 / 0.00138799 / 0.808215 | 0.8126081633 / 5.02696e-5 / 0.8126584329 | 分极化完整定义，不用含糊R00 |
| 能量闭合 / 最大逐通道功率差 | 0.0417012 / 0.0130081 | 0.001183989956 / 0.0003513448473 | ≤1e-5 / ≤1e-6，失败 |

[独立Gate](records/gate_decisions_v4.json)保存全部40通道、六点复E/H及原材料/界面集合、绝对误差和分母。μ_r=1时H_code=curl E/(i k0)，完整H相对L2差等于相应curl相对差。port恢复和slave存储通过不替代体方程失败。五个标签政策字段贯穿manifest/checkpoint/results：reference_used_for_training=true；pde_only_solve/production_initialization_allowed/pde_only_solver_qualified/official_candidate_results全部false。监督场误差下降不等于神经求解增量。

| V4资源 / measured或保守计费 | wall / s | 同时整树RSS峰 / B | 自身swap / B |
| --- | ---: | ---: | ---: |
| R0 M5边界 | 15.843932监督 / 22.015435整launcher | 533176320 | 0 |
| R1唯一后段 | 10688.701736监督 / 10690.413275整launcher | 764751872 | 0 |
| R2 ML q15/q30 | 17.516962监督 / 19.315401整launcher | 523923456 | 0 |
| R2 FE compare-only | 18.164625监督 / 20.000318整launcher | 584249344 | 0 |

本页数值冻结时V4全账快照10934.6917s，含120s直接/最终保守费用；后续aux/浏览器与最终费用在[资源账](records/resource_costs_v4.json)追加。旧累计33070.52670758043s和失联3284s保留。新Gram factor/Gsolve均0；G CSR payload146851456B，2154次matvec95.4165s、检查点3.8402s、保留payload88078236B计入R1父wall/RSS，不重复加计，不将payload当RSS。tmux管理服务器在树外一次样本4702208B，不称全过程峰值。系统余量＋至少384GiB邻增长＋自身预算现场准入，内部串行、CPU-only/MPI1/线程1、采样swap0；共享运行性能不作方法速度归因。

保存留白偏差明确留存：C1时钟起点在worker导入后，闭包收口侵占原120s；退出后整launcher余量109.587s（监督111.298s），总3h未超。C2计时接线已修正，仅针对性测试，未重启重放。新review和必要新证据的实际GitHub渲染状态见[记录](records/render_check_v4.json)，历史页面不批量重渲染。本轮不merge，不改变旧负结果，下一步仅提交完整终态和计时偏差供review，未获准再训练或扩展模型。

# Task42extra Review V2 后续：V3 参考暴露表示诊断

本节追加 V3，下面的 V2 与 V1 历史及其负结果原文保留。固定 M5 的同一 5 nm Si/air、384 hex、p3/q15、31968 独立复 FE 系数和 40 端口不变。P0 用已保存四态考察场误差与原方程残差的关系；P1 唯一新路线 `FEINN-REFERENCE-FIT-G` **读取 V1 准确散射系数训练**，P2 冻结后独立 FE 审核。因此这项试验只探查固定网络能否表示已知参考，`reference_used_for_training=true`、`pde_only_solve=false`、`production_initialization_allowed=false`；V1/V2 无标签路线仍为原来的负结果，不能把监督拟合提升为独立求解成功。[详细方法与结果](representation_diagnostic_v3.md)、[Response V3](../response_v3.md)、[run index](records/run_index_v3.json)。

| V3 阶段 / measured | 数值或状态 | 解释 |
| --- | --- | --- |
| P0 四态 `A(c−c_ref)=r−r_ref` | 最大 operation-scaled 差 `3.45e-13`，参考原残差 `6.79e-12` | 恒等式和保存的参考均实算；未把参考残差设零 |
| P0 V1 FREE / V2 scaled FREE | `E_G=0.991760/0.954121`、原 native `0.596914/0.607772`、负梯度方向余弦 `0.02306/0.00508` | 两次解析最优实步长只作离线见证，场误差几乎不变 |
| P0 Gram 成本 | setup `96.880 s`、11 Gsolve `3.466 s`；A/Aᴴ `11/4`；树峰 `1,038,958,592 B`、自身swap0 | 仅 P0 进程一个研究用稀疏因子，结束释放 |
| P1 梯度/事务资格 | 三条非零实方向、batch1/8、合成复数目标与回滚通过 | fit 闭包只用 G matvec和完整矩 VJP，无 Gsolve/A/Aᴴ |
| P1 唯一拟合 | `EXECUTION_SESSION_LOST_NO_FINAL_CHECKPOINT`；观察825 closure，仅Adam500参数保存 | 受监督会话意外消失；没有final/last_trial/optimizer状态，不重启训练；不是 PDE-only 解 |
| P2 独立场/原方程/功率审核 | 留存态compare-only完成；严格Gate均失败 | 只审核Adam500并复用V1 p3参考，新MUMPS计数0；不得当完整候选终态 |
| p4 / 目标尺寸5nm / 0.7nm | `not_run` | 本批无放大授权 |

中间 Adam 日志的 `parameter_update_norm` 在更新前采样，0 不是接受更新幅度；每25 closure 的真实更新范数标 `NOT_RETAINED`，不重放唯一训练补历史。第817次已提交参数审核只留有`E_G=0.0603363`和原残差`8.19881`，相应参数未保存，不能用于P2；唯一可重建的Adam500态为`E_G=0.200821`、native`14.26346`。失联训练采样时长至少3097.314s、保守按3284s计入本批账，树RSS峰697479168B、自身swap0。[中断身份和账](records/fit_interruption_v3.json)。

| 同一 M5、同p3参考 / measured | 准确参考 | Adam500留存网络态 | 严格资格 |
| --- | ---: | ---: | --- |
| G场误差 | 0 | 0.200821 | 完整拟合研究正阈值0.001；缺final不得作最终分类 |
| 原native / augmented残差 | 约6.79e-12 | 14.263463 / 14.263463 | 各≤1e-6，未通过 |
| 散射E L2 / scaled-curl相对差 | 0 | 0.162013 / 0.201705 | 各≤1e-4，未通过 |
| total E L2 / scaled-curl相对差 | 0 | 0.111101 / 0.137924 | 各≤1e-4，未通过 |
| 40级原total / 真出射 / scattered复幅相对差 | 0 | 0.137244 / 0.0658706 / 0.243664 | 各≤1e-4，未通过 |
| R/T/A_balance/A_volume | 0.812426/0.0324624/0.155111/0.155111 | 0.828087/0.0419968/0.129916/0.171617 | 功率差与体吸收、能量均未过；候选仅diagnostic |
| `R00_s/R00_p/R00_total` | 0.812257/约1.26e-26/0.812257 | 0.806827/0.00138799/0.808215 | 单列极化，避免“R00”歧义 |
| `abs(R+T+A_volume−1)` / 最大逐通道功率差 | 约2.98e-13 / reference | 0.0417012 / 0.0130081 | 限值1e-5 / 1e-6，未通过 |

完整网络参数确实产生保存的全部FE系数，q30/q15差`2.85841e-12`、无求积漂移。六点复E/H、全40有序复通道及其分母、air/substrate/grating/interface-near双侧单元的场积分与cell集合hash见[完整诊断](representation_diagnostic_v3.md)和[独立Gate](records/gate_decisions_v3.json)。审核source为`7c2bffe4dff7b2c9a918ade6ec02a45e168b4890`；它不生成新的准确参考或MUMPS求解，`pde_only_solver_qualified=false`、`official_candidate_results=false`。快照未达研究阈值，但完整拟合最终参数已丢失，最终表示能力保持`INTERRUPTED_FIT_NO_FINAL_STATE`。

| V3资源口径 / measured或保守计费 | wall / s | 同时树RSS峰 / B | 自身swap / B | 说明 |
| --- | ---: | ---: | ---: | --- |
| P0误差—残差及唯一Gram因子 | 104.833 | 1,038,958,592 | 0 | 因子setup96.880s、11solve3.466s，结束释放 |
| 唯一P1训练尝试 | 3284.000保守计费；实际监督采样至少3097.314 | 697,479,168 | 0 | 会话消失无`run_summary`；保守计到首次确认进程不存在 |
| Adam500留存态登记 / q30重建 / FE独立审核 | 6.043 / 14.101 / 24.169 | 492,134,400 / 520,720,384 / 647,409,664 | 全0 | 各为独立监督阶段，不加RSS峰 |
| GitHub首轮8页浏览器检查 | 77.844 | 2,042,216,448 | 0 | 轻量2GiB内；26截图hash，抽看关键公式/表格 |

首轮已发布文档在GitHub实渲染8页、11表、7公式通过；Review V2为4表/5公式，V3详细诊断为3表/2公式。[渲染证据](records/render_check_v3.json)绑定精确发布blob与截图。首次本地Markdown检查因尚未生成此渲染记录的链接失败，生成真实待验记录后8页/38表通过，失败费用仍计入资源账。到首轮浏览器及其验算后，本批正式阶段加中断保守计费`3462.842s`、辅助`116.443s`、终端/最终尾段保守预留`120s`，合计`3699.285s`；原16h仍余约`24672.776s`，本批4h仍余约`10700.715s`。最终二次发布渲染与尾段费用以[完整资源账](records/resource_costs_v3.json)为准。最大同时树RSS是浏览器的`2,042,216,448B`，不把阶段峰值相加；所有自有树采样swap为0。目标尺寸5nm与0.7nm均未运行。

# Task42extra Review V1 后续：V2 固定尺度诊断

本节追加 Review V1 的唯一后续试验，下面的 V1 16节原文完整保留。原模型 M5、全部 31968 复 FE 系数、40端口、材料与弱残差未改。V2 把原 Gram 对角用于优化变量 `c=Dy`，用于检查各类系数尺度是否让旧 FREE 优化困难；它没有训练新网络。D0既有状态诊断、D1梯度资格、D2唯一候选及D3独立复验均完成。[详细解释和完整表](scaling_diagnostic_v2.md)、[Response V2](../response_v2.md)、[独立Gate](records/gate_decisions_v2.json)。

| V2 阶段 / measured | 实际结果 | 身份与边界 |
| --- | --- | --- |
| D0旧状态 | 4个保存态的loss/gradient；Adam500参数与optimizer state=`NOT_RETAINED` | 原native/Gram/history/checkpoint；不补跑历史 |
| D1缩放资格 | `diag(D*GD)`最大偏差4.44e-16；3个非零复向量、3个非零实方向及事务恢复通过 | `D`仅从原MPC后全局G对角取值，hash见[设计](records/scaling_design_v2.json) |
| D2唯一新候选 | 4000 closure停止；native/augmented均0.607772 | `CLOSURE_BUDGET`；相对V1 FREE 0.596914未改善 |
| D3 compare-only | 散射E L2相对误差0.954209；MUMPS symbolic/numeric/solve=0 | V1同p3参考复用，非新准确解或连续极限 |
| 严格/研究判定 | 方程、场、功率均未通过；`SCALING_DIAGNOSTIC_NEGATIVE` | 研究正信号需残差≤0.05969144472114且散射E≤0.5，均未满足 |
| 条件p4/目标 | p4=`not_run`；目标尺寸5nm/0.7nm=`not_run` | V1的`DISCRETIZATION_NOT_QUALIFIED`表示p4未准入 |

| 同口径量 / measured | V1 FREE-FE-DUAL | V2 scaled FREE | 用途 |
| --- | ---: | ---: | --- |
| `L_D` / native残差 | 0.103899 / 0.596914 | 0.0990053 / 0.607772 | loss降低不能替代原方程 |
| 散射E L2 / scaled curl | 0.991925 / 0.991755 | 0.954209 / 0.954118 | 仍远高于严格1e-4和研究0.5 |
| ordered原total port / 真出射复幅 | 0.573349 / 0.275180 | 0.554439 / 0.266104 | 分母分别是参考原port范数/出射范数 |
| R/T/A_balance/A_volume | 0.845194/0.115246/0.0395601/0.459627 | 0.841893/0.109807/0.0483005/0.443408 | 均为未资格化diagnostic；准确参考0.812426/0.0324624/0.155111/0.155111 |
| closure / A / Aᴴ / Gsolve | 4000/4002/4000/4003 | 4000/4002/4000/4003 | 同计算工作数，未隐藏额外closure |
| 候选监督wall / 树RSS峰 / 自身swap | 2901.906s / 1366249472B / 0 | 2539.810s / 1365712896B / 0 | shared-workstation，时间不可归因于方法 |

首轮“出射复通道”约0.27518确实对应 `ordered_outgoing_channels`，CSV约0.573349对应 `ordered_total_channels`；两者分子相同但参考分母分别0.913080与0.438234，旧V1文件不改。[V2 checker](records/gate_decisions_v2.json)从原40级复数组逐项复算。本批数值阶段最高同时树RSS为1365712896B，V1数值阶段最高约1.313GiB，而V1含浏览器的完整账最高2095390720B；不要混同口径。本批最终辅助/渲染成本与首次compare-only接线失败、默认沙箱MPI socket失败均在[资源全账](records/resource_costs_v2.json)和[run index](records/run_index_v2.json)保留。

本轮从 V1 研究档案延伸，不改变两条FEINN网络的旧负结果，也没有新的神经增量证据。Gram三次fresh factor setup约97.20/96.93/101.07s及全部solve均计入；候选复用G装配实耗为0，从零归属另加648.765s，不把此归属再计进本批实际wall。缩放不足以取得本固定M5的合格解，不能推论所有神经方法无效。下一步只能作为新的review建议，不在本批自动开展p4、目标尺寸5nm、0.7nm或其他尺度扫描。

Review V1与task一行公式修正的GitHub实际预览完成：前者6表/3公式、后者6表/7公式，表格列一致且无公式错误；关键截图抽看，24张截图均核hash。[渲染记录](records/render_check_v2.json)保留第一次导航超时和第二次Firefox `eager` 成功的费用。V2完整监督账含浏览器的同时树RSS峰为1,741,213,696B，自身swap0；[资源账](records/resource_costs_v2.json)给出全部阶段和快照截止，不能把数值峰1,365,712,896B称为会话峰。

# Task42extra 首轮执行总结

本轮完整接口资格为 True，三路线同离散资格 0/3。结果以原方程、独立完整FE场和功率审核为准。本轮比较的是同一M5、同全部独立FE、同原方程/材料/模式/初值的三条路线。坐标网络通过积分产生边、面和内部矩；FREE直接优化完整复系数。DUAL用正定测试内积衡量弱残差，增加真实稀疏Gram因子成本。LE与LD不能直接按数字大小比较精度。

## 1. 最终状态

| 项目 | 实际状态 | 边界 |
| --- | --- | --- |
| E0 Git/环境/资源 | 完成 | 原生Linux；canonical linked worktree；受控共享 |
| E1 | INTERFACE_PASS_ONLY | 完整矩/A/Aᴴ/Gram/梯度通过；不是5nm solver PASS |
| E2 | 0/3同离散合格 | 具体停止/失败量见下表与raw records |
| E3 | True | 独立参考资格单列，不反馈训练 |
| E4 | DISCRETIZATION_NOT_QUALIFIED | 未准入时P4 PDE不运行 |
| E5 | 完成成本/增量/容量设计 | 目标尺寸5nm与0.7nm均not_run/not_qualified |

## 2. 任务目标与非目标

| 目标 | 比较方式 | 未获资格项 |
| --- | --- | --- |
| 正确完整插值能否求得真实5nm FE解 | EUC/DUAL/FREE同物理与全部FE | 不是旧Task042 trace/p4粗逆续跑 |
| 分开度量与网络贡献 | EUC→DUAL度量；DUAL→FREE表示 | 无teacher/目标准确解监督或warm start |
| 决定目标尺度下一步 | 容量和全过程账 | 不启动大5nm/0.7nm，不扫描p/h/M/MPI或网络 |

## 3. 基线、冻结配置和环境

| 量 / 单位 | 冻结或实测值 | 证据性质 |
| --- | --- | --- |
| 物理 / nm | lambda5；Si/air；grazing1°/phi0/s/amp1 | frozen |
| 盒 / nm | [-5,5]×[-3.75,3.75]×[-1.25,8.75] | frozen |
| 离散 | h1.25、384hex、N1curl p3、q15、MPI1 | measured |
| native / slave / independent FE | 34050 / 2082 / 31968 | measured；内部13824完整保留 |
| 边 / 面 / 内部矩 | 3744 / 14400 / 13824 | measured；无内部物理恢复 |
| 材料cell / notch | air200、substrate48、block136；notch8 | measured；y/z同时变化 |
| 完整DtN / NN实参数 | 40 / 8966 | measured；3×64 tanh，6输出、FP64 |
| FREE实参数 | 63936 | 全部31968复FE实虚分量 |
| dtype / env | PETSc complex128/int64；Torch2.7.1+cpu；数学/interop1 | 新env，合格原生库只读接线 |

材料唯一hash与实际mesh/tags/mode/Gram/source见[run index](records/run_index_v1.json)及[预登记](records/design_v1.json)。Si n=0.99396854453+0.00435380777i，epsilon=n*n；不重新猜材料。环境与三个既有项目见[隔离记录](environment_and_isolation.md)。

## 4. 实现与方法

| 方法 | 用途 | 代价/限制 |
| --- | --- | --- |
| 完整Nédélec矩插值 | 把连续坐标网络转成原FE解；边36/面72/内部36每cell | Piola、T^-T、唯一owner和原MPC相位一次 |
| 原局部未凝聚A/Aᴴ | 对全部独立FE训练与真残差审核 | local tensor+约束COO+全部端口；无global A CSR/AᴴA |
| 原端口消元 | alpha=solve(H,gp+Dc) | 原[V B;-D H]，正表面归一化H；只消端口 |
| 正定Riesz | LD=r*G^-1r/(2f*G^-1f) | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，非Maxwell逆 |
| 有界VJP | 最多8cell图，重算反向 | 8966参数之外还有坐标/矩/激活/算子缓存 |
| 有界事务优化 | Adam500、L-BFGS history20/strong-Wolfe | 每条3h/4000完整closure；outer返回才提交 |
| 盲参考 | 冻结后独立准确同p3审核 | 只作authority，全局Maxwell因子不进入训练 |

详细论文方法与改动见[映射](method_and_paper_mapping.md)。论文正定Dirichlet模型及refined test与本复数不定开放同p3问题不同；没有论文原样复刻、波长鲁棒或超收敛结论。

## 5. 实验/运行矩阵

| 阶段 / evidence身份 | 实际source | 监督 wall / s | 同时树RSS / GiB | 结果 |
| --- | --- | --- | --- | --- |
| e1_fe | a3dd65f594dd | 737.521 | 1.13985 | FE_INTERFACE_PASS |
| e1_grad | a3dd65f594dd | 201.116 | 1.19316 | INTERFACE_PASS_ONLY |
| e1_smoke | a3dd65f594dd | 44.1878 | 0.494907 | PASS |
| e3_reference | 7a79b3007d92 | 672.463 | 1.16026 | INDEPENDENT_REFERENCE_PASS |
| e4_p4 | 7a79b3007d92 | 1.96302 | 0.0635757 | DISCRETIZATION_NOT_QUALIFIED |
| FEINN-DUAL | 7ac01a62453e | 10688.1 | 1.31262 | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-EUC | 7ac01a62453e | 10690.7 | 0.65601 | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | 7ac01a62453e | 2901.91 | 1.27242 | FEINN_OPTIMIZATION_NEGATIVE |

制造解是8-cell单位正定curl-curl+mass诊断，wavelength=None，不能叫5nm结果。正式FE均通过one-run dat和`scripts/run_case.py`，实际数值source与之后文档HEAD分开。每阶段结束清场再启动下一阶段。

## 6. 关键结果表

| 路线 | native / augmented | 散射E L2 / scaled-curl | selected total E/H | 出射复通道 | R/T/A_balance/A_volume |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 0.928287/0.928287 | 0.999215/0.999234 | 0.678586/0.671902 | 0.270177 | 0.837415/0.113261/0.0493242/0.465089 |
| FEINN-DUAL | 1.10264/1.10264 | 0.998885/0.998906 | 0.678322/0.671303 | 0.270119 | 0.837391/0.113257/0.0493519/0.464992 |
| FREE-FE-DUAL | 0.596914/0.596914 | 0.991925/0.991755 | 0.672954/0.670815 | 0.27518 | 0.845194/0.115246/0.0395601/0.459627 |

| 场身份 | R00_s / R00_p / R00_total | 最大逐级功率绝对差 | abs(R+T+A_volume−1) |
| --- | --- | --- | --- |
| REFERENCE | 0.812257/1.25634e-26/0.812257 | reference | 2.97762e-13 |
| FEINN-EUC | 0.837279/6.91785e-10/0.837279 | 0.080903 | 0.415764 |
| FEINN-DUAL | 0.837271/7.0838e-11/0.837271 | 0.0808367 | 0.41564 |
| FREE-FE-DUAL | 0.844749/1.02397e-08/0.844749 | 0.0825716 | 0.420067 |

未资格化候选的R/T/A标diagnostic；只有全部Gate通过的候选成为official。total/scattered E L2与scaled-curl、六点total/scattered复E/H逐点和整体、完整ordered原port/出射/scattered复幅、40级功率均见[独立物理记录](records/blind_physics_v1.json)。相对误差保留absolute与denominator，无全局相位拟合。A_balance=1−R−T；非平凡闭合使用A_volume。

三候选checkpoint/hash冻结后，独立DOLFINx原体矩阵和完整未凝聚增广系统建立一次MUMPS准确参考；factor/matrix销毁且RSS下降后才后处理。参考从未反馈训练。它是同p3离散authority，不是连续解。

| 独立参考量 / 单位 | 实测值 | 资格边界 |
| --- | --- | --- |
| native / augmented | 6.78884e-12/6.78884e-12 | 目标各≤1e-10 |
| original total / 独立DOLFINx native | 3.51452e-12/3.26042e-12 | 原RHS，无训练反馈 |
| R / T / A_balance / A_volume | 0.812426/0.0324624/0.155111/0.155111 | 同mesh/p3 authority；不是连续解 |
| R+T+A_volume−1 / A_balance−A_volume | 2.97762e-13/2.97734e-13 | 独立吸收闭合≤1e-5 |
| Maxwell symbolic / numeric / solve / s | 0.43006/5.97992/0.361829 | reference ONLY，禁止训练fallback |
| 释放前 / 后 worker RSS / B | 1.08556e+09/2.31522e+08 | 释放factor和matrix并确认下降后才后处理 |
| reference qualified | True | 方程、能量、资源分别审核 |

## 7. 数值正确性与 Gate

| 接口Gate | 原始字段独立重算结果 | 范围 |
| --- | --- | --- |
| positive_manufactured | True | 接口资格；不能替代方程/场/功率 |
| complete_moments | True | 接口资格；不能替代方程/场/功率 |
| full_uncondensed_model | True | 接口资格；不能替代方程/场/功率 |
| native_ports | True | 接口资格；不能替代方程/场/功率 |
| Gram_variational | True | 接口资格；不能替代方程/场/功率 |
| Gram_solve | True | 接口资格；不能替代方程/场/功率 |
| quadrature | True | 接口资格；不能替代方程/场/功率 |
| EUC_batch | True | 接口资格；不能替代方程/场/功率 |
| EUC_gradient | True | 接口资格；不能替代方程/场/功率 |
| DUAL_batch | True | 接口资格；不能替代方程/场/功率 |
| DUAL_gradient | True | 接口资格；不能替代方程/场/功率 |
| e1_smoke_resource | True | 接口资格；不能替代方程/场/功率 |
| e1_fe_resource | True | 接口资格；不能替代方程/场/功率 |
| e1_grad_resource | True | 接口资格；不能替代方程/场/功率 |

| 路线 | 实际停止 | 方程 / 场 / 功率 | 状态 |
| --- | --- | --- | --- |
| FEINN-EUC | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-DUAL | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | CLOSURE_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |

方程≤1e-6；同离散场/通道≤1e-4；MPC/消元恢复≤1e-10；功率总量差与闭合≤1e-5、逐级功率差≤1e-6。完整阈值重新计算于[独立Gate](records/gate_decisions_v1.json)，不靠optimizer success、小梯度或status字符串通过。q15/q30非零见证相对差1.47451e-15，q15冻结，q60未运行。

## 8. 性能或资源结果

| 路线 | closure尝试 / 完成 / 完整外层 | 实际完整wall / s (derived) | 从零归属 / s | 运行树峰 / GiB | own swap / B |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 2219/2219/578 | 10692.4 | 10783.2 | 0.65601 | 0 |
| FEINN-DUAL | 2387/2387/586 | 10689.9 | 11429.5 | 1.31262 | 0 |
| FREE-FE-DUAL | 4000/4000/649 | 2903.75 | 3643.38 | 1.27242 | 0 |

| 辅助量 / 单位 | 实测值 | 含义 |
| --- | --- | --- |
| Gram rows / NNZ | 31968 / 7336179 | 全部独立p3；材料无关正定测试内积 |
| Gram CSR payload / B | 146851456 | 数组体积，不是RSS |
| 首次装配 / s | 648.765 | 完整计入DUAL/FREE从零成本，研究实账只计实际一次 |
| 资格factor setup / s | 110.571 | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR；LLᴴ/AMD |
| symbolic L NNZ | 1.88397e+07 | symbolic后容量Gate，非dense inverse |
| CHOLMOD current / peak B | 5.44919e+08 / 6.33593e+08 | 辅助因子也计资源 |
| 资格Gsolve max true relative | 9.13339e-12 | 限值1e-11；训练各路线另逐次检查 |

| 路线 / research-only | fresh setup / s | 全部Gsolve / s / count | max true residual | factor current / peak B |
| --- | --- | --- | --- | --- |
| FEINN-EUC | 0 | 0 / 0 | not_run | not_run/not_run |
| FEINN-DUAL | 128.442 | 810.233 / 2390 | 6.10176e-13 | 5.44919e+08/6.33593e+08 |
| FREE-FE-DUAL | 113.025 | 1394.34 / 4003 | 7.53354e-13 | 5.44919e+08/6.33593e+08 |

发布前数值/测试快照的监督实账25985.9 s；含启动/发布的workflow快照约26016.6 s（UTC/mtime derived）。发布后实际render及复核费用追加到最终[resource账](records/resource_costs_v1.json)，本快照不代替最终全账。首轮停止预算57600 s，以最终完整账重算。独立参考、资格和失败轻测试另列并包含研究全账。从零归属按本轮E1准备减exclusive Gram assembly作为保守common，DUAL/FREE各加完整assembly；各自fresh factor已在其运行账，不重复加。该归属不是额外研究耗时，也不是空机器冷启动benchmark。

原C2首个H除法同时位于setup和aggregate port timer。compact互斥账保留首项在setup，将其后port归入other_control，raw port timer只作非累加diagnostic；network/moment/Gsolve/A/Aᴴ/VJP/optimizer/IO均保留，避免父子重复相加。所有bytes/payload与采样RSS区分，峰取同一树同时最大而非加阶段峰。完整资源账见[records](records/resource_costs_v1.json)。

## 9. 根因解释

| 问题 | 已排除/已确认 | 仍未确定 |
| --- | --- | --- |
| 接口实现 | 完整矩、多项式/方向/MPC、A/Aᴴ、非零port/内部载荷、FD通过 | 通过不是普适几何/所有网络参数的求积证明 |
| 保留未知量 | 31968全部独立FE及13824内部矩实测 | 不是仅trace/内部局部物理恢复 |
| Riesz成本 | 真实SPD稀疏factor与每次solve准确性 | 正定G不保证不定A训练/波长鲁棒 |
| 优化与表示 | 三路线同固定预算与zero start | 有限负结果不能唯一归因于网络表达或优化条件 |
| 离散 | 仅固定p3/h1.25/M/MPI1 | p4有条件；continuum和目标未资格化 |
| 共享资源 | 未触线，own swap0，保护邻任务配置 | 无零干扰反事实或20%可比性能结论 |

## 10. 成功路线

完整数学接口、原生环境和事务检查提供可复核的实现证据。准确参考若通过，仅提供同离散authority；不会提升未通过的候选或目标尺寸资格。

## 11. 失败、负结果与未运行项

| 路线 | 实际停止 | 方程 / 场 / 功率 | 状态 |
| --- | --- | --- | --- |
| FEINN-EUC | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-DUAL | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | CLOSURE_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |

p4判定：DISCRETIZATION_NOT_QUALIFIED。目标大5nm、0.7nm/48h、更多几何/波长/seed/宽度/carrier、监督拟合和raw NN点云超收敛均not_run。每条停止原因、last committed/trial与费用保留，checkpoint为parameter-only，未存一致optimizer state，不支持一致续训。closure尝试在开始时计数；完整loss＋gradient按成功history另计，失败/不完整尝试也保守占用预算。raw内层计数是最后完整外层的Torch n_iter；最后异常外层的partial inner次数未另存，其全部已完成closure/A/Aᴴ/Gsolve及费用照计。

| 对照轴 | 本轮身份 | 可得结论 |
| --- | --- | --- |
| p | p3 measured；p4 not_run | p3候选未过资格，禁止p4条件求解；无连续极限结论 |
| h | 1.25 nm fixed | 没有h收敛实验 |
| Full3D/Hybrid | 本任务仅原生完整Nédélec FE | 未比较不同离散/算法 |
| Fourier模式M | 原规则自动得到40个完整端口 | 未扫描M；不能代替模式收敛 |
| MPI | 1 | 没有并行加速或跨MPI等价声明 |

## 12. 代码和文件变化

详见[changed files](changed_files.md)：数值核在src/solvers，runner只参数化编排。普通默认solver数学不变；旧Task042历史/环境/运行目录保持只读；新scope为Task42extra。

## 13. 最终合并建议

| 依赖组 | 实际改动 | 本轮合入建议 |
| --- | --- | --- |
| production numerical/core | 原默认solver数学不改；run_case增加明确opt-in dispatch | 需review；不把未资格路径设默认 |
| runner/watchdog | task-local activation、资源准入与子树监督；依赖既有通用watchdog | 可单独审阅，不影响邻任务 |
| checker/benchmark | stdlib compact checker、容量推导、render检查 | 只读复核，依赖本任务compact records |
| research-only | 完整矩、A/Aᴴ、稀疏Riesz、三路线优化、reference/p检查 | 研究路径，不能当可扩展PC或生产solver |
| evidence/docs | 本任务response/outcomes、进度与模型总账追加 | 保存正/负结果，不改Task042历史 |
| do-not-merge | venv/cache/raw矩阵/场/history/checkpoint/浏览器profile | ignored；无master/跨支线merge |

只推执行支线，等待review；没有master/其他支线merge、amend、强推或生产默认资格。

## 14. 局限

只测一个固定小模型、单seed、p3/h1.25/M40/MPI1及当前共享工作站；未扫描这些影响。native Linux证据见ABI，通用watchdog旧raw label `WSL-global diagnostic`仅为复用标签，不表示运行于WSL。没有cgroup委派，使用目标0.5 s同时子树RSS采样，不冒称连续内核限额；自身swap按样本VmSwap，全球swap仅诊断。性能/邻任务影响为inconclusive。近零规则E0冻结，没有事后调分母或相位。

GitHub rendered-view 检查实际发现[发布任务书](../task.md) §5.4 使用的 `\operatorname{Re}` 被拒绝；该文档 Gate 为 `RENDERED_VIEW_FAIL_TASK_MATH`，不记为通过。本支线可修改的方法映射中的同类 `\operatorname{solve}` 已修正，复核证据及截图 hash 见[render记录](records/render_check_v1.json)。这不改变冻结数值实验和其失败判断。

## 15. 下一步决定

建议后续review只授权固定M5的一条FREE-FE-DUAL变量尺度诊断：用正定Gram对角给全部FE系数统一单位尺度，原loss、零初值、closure/wall和全部验收不变。该诊断不使用目标准确解训练、不调用Maxwell逆、不扩大模型；用于先区分优化条件问题与神经表示问题。本轮未实施。

目标尺寸容量与需要先解决的临时张量/Gram阻塞见[5nm计划](target_5nm_scale_plan.md)。本轮交付后停止等待review，不借剩余预算启动目标PDE。

## 16. 证据索引

| 入口 | 用途 |
| --- | --- |
| [response_v1](../response_v1.md) | Git/source与执行边界 |
| [run index](records/run_index_v1.json) | 每stage source/input/env/resource/artifact hashes及失败费用 |
| [interface](records/interface_gates_v1.json) | 原始完整矩/算子/梯度/Riesz Gate字段 |
| [comparison CSV](records/route_comparison_v1.csv) | 三路线完整统一口径 |
| [physics](records/blind_physics_v1.json) | 复E/H/全40级复幅与功率/原残差 |
| [Gate](records/gate_decisions_v1.json) | stdlib checker独立重算 |
| [resource](records/resource_costs_v1.json) | 实际/归属/互斥成本及树RSS/释放 |
| [tests](test_summary.md) | 相关tests、static、Markdown与render记录入口 |
