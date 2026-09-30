# Response V6：固定特征残差下限完成，严格资格仍未通过

本轮已测得此固定195维特征空间的原方程最小残差，但没有获得物理解资格。V6实际网络 native/augmented 均为 **0.570577990454**，高于严格1e-6；G场误差 **0.569932119000**，散射E L2 **0.569893933222**，scaled-curl/H **0.569933083410**。相比V5，残差降低而场、功率显著变差。分类 `FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED` 只说明线性最小二乘子问题已测完，不表示solver通过或整个网络类不可能。

| 身份 | 准确值 |
| --- | --- |
| 执行分支 / worktree | task42extra_feinn_5nm / /home/fenics/Projects/NN-Lab-V2 |
| 本页生成前HEAD | 46c9d66544352e8b91d00ac483b1dcf1d4fdbdff |
| 四阶段实际clean source | a2f6ea85a24cb5e7c233d266aaab9911fc695dcc |
| review发布 / 审阅基线 | 3ab4a251c76208897729473add43f1e91c9d634a / b5be93b130a6102d89511a345cbaf54341cd345d |
| 冻结base | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| canonical common Git | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git |
| upstream | remote origin；merge refs/heads/task42extra_feinn_5nm；共享fetch未映射，@{upstream}不可解析；只用精确refspec及显式tracking ref核对 |

## T0–T2实际完成

这一步把已经学到的隐藏特征固定，只重新组合最后一层，使原方程左右两边尽量接近。它回答同一组特征最有利的末层能把原方程残差降到哪里；收益是消除“末层优化还没求好”的不确定性，代价是195次原算子作用、约100MB受限矩阵及稳定分解。隐藏特征曾读过参考场，当前读出只用原载荷f，整条路线仍不是无标签求解。

保持原M5、5nm Si/air、384hex、p3/q15、31968独立复FE（边3744、面14400、内部13824）、2082slave、40端口、材料/背景/MPC/DtN。冻结8576实隐藏参数和坐标buffers，仅改变390实末层参数。复用V5已资格化Phi/Q_eff，不新增列，不重新G-QR；全部内部矩经原网络forward、Piola/orientation/MPC完整生成。

| 阶段 | 实测结果 | 边界 |
| --- | --- | --- |
| T0 | 10项新tests及3方向原算子/回写通过 | 复用V5资格，未重跑P0/E0/E1 |
| T1唯一 | rank195；rho0.570577990454；回写/最优性通过 | 仅195维完整冻结空间的数值下限 |
| T2独立ML/FE | q15差0；q30差7.26e-13；范数/勾股通过 | 只复用V1参考，无新MUMPS |
| 严格物理/表示 | 方程、场、功率失败；三项未均≤0.01 | PDE-only/official固定false |
| p4/目标尺寸5nm/0.7nm | not_run | 本轮结束等待review |

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

## 已核清与仍不确定

G把电场本身和旋转变化一起计入能量，curl项的权重较大。因此降低G误差并不保证L2单项下降。独立参考原积分给出N_E=24.255317346031813、N_C=24.3260883092953；ell=5nm、ell*k0=2pi。两项在G总参考能量中的权重约2.46%和97.54%，未用舍入误差反推。

```math
 E_G^2=\frac{N_E E_{L^2}^2+(2\pi)^2N_C E_{\mathrm{curl}}^2}
 {N_E+(2\pi)^2N_C}.
```

参考G能量：FE积分984.6107903008689、CSR984.610790300809，相对缺陷6.08e-14。V4/V5/V6的加权恒等式均通过；V6误差平方差1.44e-15。相对V5最佳场，V6误差能量0.32482262026816017=V5的0.00013435029895563817＋两场距离能量0.3246882699691961，归一化勾股缺陷8.44e-15≤1e-8，没有低于V5 G最优的身份异常。

本轮已排除所测末层布局、两套置换混用、G/物理范数不一致、回写不稳、参考泄漏进读出右端项、q15漂移和最终状态丢失等因素。新残差下限高出1e-6约570578倍，回写原方程分辨差仅2.31e-11；它支持此冻结空间达不到原残差门限的数值结论，不是带区间误差界的数学证书，也不排除改变隐藏参数后的网络。V5 G最优已经不足以让L2/curl同时≤1%，当前读出的约57%场误差不能当有效求解进展。无标签神经增量仍未证明。

**唯一后续设计建议：在原M5上设计包含物理传播相位的隐藏表示，并先冻结其完整矩/原方程验证方案。** 不在本轮实施，不再扫描同一冻结特征的loss或末层超参，不继续hidden训练/VarPro/PDE微调。目标尺寸5nm需另行冻结几何、网格及可扩展求解设计后才可晋级；本轮p4、目标尺寸5nm与0.7nm均not_run。旧V1/V2负结果、V3中断及失联3284s费用不改。

## 源码、资源、证据与交付

实际A/A*按列合计206/3，完整native审核4次另列（其中FE含2次独立DOLFINx作用），G合计16列；限值256/8/12/512均未超。新增Gsolve/Gram factor/Maxwell factor/optimizer step均0。原G稀疏payload146851456B、Phi/B各99740160B（数组体积，不是RSS）；旧Gram装配648.765s、历次factor、准确参考和监督特征学习费用保持原账，从零成本不能用本次约49s主阶段代替。

数值树峰1290457088B（约1.20GiB），自身swap采样全0、各阶段完整清场。主阶段完整launcher48.924852s含导入、加载、哈希、A/QR/SVD、存盘和审核；退出剩1751.075s，150s收口和至少120s保存留白通过。组件细分计时未保存，标NOT_RETAINED，不重放补计；父wall完整计费，嵌套/数组payload不重复相加。

本页冻结前V6账约257.8s（含全部已完成辅助及直接/最终120s保守额度）；发布与浏览器费用继续追加[最终资源账](outcomes/records/resource_costs_v6.json)。旧累计44815.22461795143s和失联/重放成本不删除；本批≤3600s、主阶段≤1800s、T0≤600s及原57600s分别审核。CPU-only、MPI1、数学/Torch1，现场空闲物理核，本批正式CPU12；系统余量216310038528B＋384GiB邻增长＋自身cap，警戒12/硬16GiB，轻测试/浏览器≤2GiB。tmux管理服务器约4.7MB稀疏样本单列，不称连续峰；无cgroup委派，约0.5s树采样监督，不宣称连续内核限额或零干扰。

轻量Ruff曾报告两处unused import，提交前局部修正；其中checker去掉无用import后没有重复昂贵数值验算。一次人工状态探针误用大写route文件名，已改用load_index；主阶段实际收尾在ML启动前，launcher的自有锁及依赖hash核对继续有效，没有重复主阶段。上述检查费用计入直接/辅助账。T0及最终审核没有权限、资源或数据阻塞，严格负结果按原门限保留。

[design](outcomes/records/residual_readout_design_v6.json)、[checks](outcomes/records/residual_readout_checks_v6.json)、[projection](outcomes/records/residual_readout_projection_v6.json)、[三场CSV](outcomes/records/residual_readout_comparison_v6.csv)、[完整Gate/复通道/区域](outcomes/records/gate_decisions_v6.json)、[run/source/hash](outcomes/records/run_index_v6.json)、[最终资源账](outcomes/records/resource_costs_v6.json)、[新GitHub渲染](outcomes/records/render_check_v6.json)。大数组留ignored，compact记录绑定文件hash和实际source，后续文档HEAD不冒充运行源码。

[详细诊断](outcomes/frozen_feature_residual_v6.md)包含稳定性、完整通道分母和原区域对照。本轮10项定向tests、Ruff、compileall与文档本地合同分别记录，不声称CI或full pytest通过。Git最初安全快进到review发布SHA；只修改当前canonical linked worktree及同分支，没有共享Git配置改动。最终准确HEAD、显式tracking ref/ahead-behind和clean/自有作业收尾状态由最后Git receipt及终端报告给出；本页和实际数值source清晰分开。

新review与必要新增页实际GitHub rendered view只看本轮内容，状态见render记录，不把本地解析当视觉通过。只执行指定push，之后停止等待review，不amend/强推/merge。
