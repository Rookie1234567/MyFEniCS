# V9：全参数阻尼 Gauss–Newton 对照

本页说明本轮改变的训练方法。它先计算“网络参数的小改动会怎样改变原方程残差”，求一个受阻尼限制的方向，再用真实非线性目标检查是否接受。因此一次外层步可以包含很多完整方向作用和拒绝试探；它既不是一个 epoch，也不能与旧 L-BFGS 的一次 closure 等价。以下数值来自冻结后的独立验收，严格、研究和监督表示门限分别判定。

固定问题仍为 M5、5 nm、384 hex、p3、体/DtN q15、31968 独立复 FE 和完整40端口。plain 和单入射相位网络保持3×64 tanh、6输出、8966实参数、FP64。全部隐藏层与末层都可以更新，全部 Nédélec 边、面和内部矩都进入同一原方程；这里没有冻结195维末层、扩大网络或改变物理离散。

## 更新方向与实际目标

网络及完整矩插值把实参数映射为复 FE 系数，JVP 表示沿参数方向的系数变化，VJP 把系数梯度拉回参数。它们不是空间导数。闭包按最多8个cell分块，不保存完整网格自动微分图、全 Jacobian 或大参数矩阵。

```math
r=A c(\theta)-f,\qquad d_G=f^*G^{-1}f,\qquad L=\frac{r^*G^{-1}r}{2d_G}.
```

```math
g=\frac{\mathrm{Re}(J^*A^*G^{-1}r)}{d_G},\qquad
Kv=\frac{\mathrm{Re}(J^*A^*G^{-1}AJv)}{d_G},\qquad
(K+\mu I)s=-g.
```

K 是参数空间的 GN 曲率，不是一般非线性 loss 的完整 Hessian；G 是有限元场的正定度量，也不是 K。每条 C 路线新建一个准确稀疏 G 因子，标 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`，并计入建立、求解、常驻 RSS 和释放。matrix-free 只指 J/K 以及既有 A 作用，不能称整套方法无全局因子。训练不建立 Maxwell 因子。

初始曲率尺度 h0 用 seed421901 的6次作用估计，不是条件数或严格谱界。μ初值为1e-3 h0，限定在[1e-12 h0,1e6 h0]。真实目标下降为正且实际/预测下降比η≥0.1才接受；η>0.75时μ除以3，η<0.25时乘2，拒绝则乘10，每outer最多8个试探。阻尼只控制更新，不加入正式 loss。

内层实 CG 默认40次、真相对线性残差目标0.01。有有效下降的未完全收敛方向仍可检查真实目标。连续3次慢 CG 触发固定 rank32 的随机range/Ritz参数辅助：用64次K作用构造小基，改善内层方向尺度；它不是全FE或Maxwell预条件器。C每条最多构造2次、D每条1次，PCG最多80次，旧基复用时明确来源。没有有效下降时仅使用预登记 Cauchy 保护，仍不能接受则保存 `GN_MODEL_STAGNATION`，不重置预算。

## 阶段边界、标签与保全

| 路线 | 读取的唯一 V8 Adam500 字节hash | 原前缀归属 / s | 本段性质 |
|---|---|---:|---|
| C plain | e976d3e629c433c1f1dc6b7ae3c343acaa5dfa5cd948818231e93a3a9298f9a0 | 1097.641308126 | 无标签原方程 GN |
| C phase | 07c77c468c175edc9455025651a058ac589f2313fc1f15d9b38c3c6628daffae | 1144.848724030 | 无标签原方程 GN |
| 条件 D plain | 1f3929eacd6afe3b19b5bc6552a37316326bd9b3434f14060cafd81c39716234 | 989.700669310 | 隔离监督 FIT-GN |
| 条件 D phase | 91c7696d34eec5c01e90be6559198bd8983fe81affa8640393a3be532d8041aa | 1019.104531524 | 隔离监督 FIT-GN |

只复用各自参数和buffers，不重做500次Adam，不加载旧optimizer历史。原边界source为 `bc052a3744528277f00a7a9a5566aa4a6d7393ed`；完整c、source、参数顺序、阶段、buffer及标签核对见[边界记录](records/prefix_identity_v9.json)。C白名单没有 reference_state、D模型、Phi/Q或p4/p5场。C声明 benchmark_previously_seen=true，reference_used_for_training=false、features_reference_exposed=false、pde_only_solve=true、production_initialization_allowed=false。

每个接受步先同步原子保存匹配模型/buffers/GN状态/μ/h0/RNG/预算/PC来源，再发布 committed 审核行；trial独立。更新量是返回后的参数差。异常恢复匹配状态，已经耗费的作用和时间保留。SIGKILL只能保证上一成功flush/fsync/原子替换边界，不能保证 finally 保存。

C两条终态冻结并独立比较后，phase未严格合格且共同资格/资源仍合格时，自动触发D。D只用原参考的G场拟合、G乘法和完整矩JVP/VJP，不逐步调用A/AH/Gsolve或Gram factor。其标签已暴露，PDE-only、production、official始终false，任何D权重都不反馈C或其他任务。

## 资格和比较口径

[真实 GN 资格](records/gn_checks_v9.json) 包含两个 C 边界的 hidden/last/random非零实方向差分、实伴随、解析切线、K对称和能量正性、batch1/8、输入冻结及准确Gsolve；[定向测试](records/targeted_tests_v9.json) 另有非Hermitian复小模型、拒绝回滚、原子加载与PC见证。既有环境和完整矩资格复用，没有整套旧回归或 full pytest。

冻结后独立ML从参数重建q15系数并用q30复核；FE compare-only只读V1原p3参考，审核total/scattered E/H/curl、六点复场、四类各40级复通道及分母、逐级功率、R/T/A/A_volume/R00和材料/界面区域。严格原残差≤1e-6、场/通道≤1e-4、功率/能量≤1e-5、逐级功率≤1e-6。研究信号还要求同表示、共同时间下native与augmented均比V8降低至少10倍，散射L2/curl均≤0.1且更好；这仍不是严格合格。

共同时间比较只选择两边真正保留的、目标时间之前最近 committed 状态，报告实际时间差，不插值造场、不用参考误差挑最佳状态。原L-BFGS作为已有对照，不重跑。历史前缀计入每条逻辑路径上限，但不在全项目账重复计费。训练墙钟包含导入/加载、fresh Gram/PC、拒绝试探、保存和原方程审核；独立验收及辅助费用另列全账。

## 冻结后的实际结果

下表均为独立冻结审核的 measured 值，使用原V1同p3参考。C为无标签原方程训练；D为标签已暴露的表示诊断。功率仅在严格合格时才可称 official；监督字段始终禁止升级为独立求解。

| 同p3路线 | native | augmented | E_G | 散射E L2 | 散射curl/H | 判定 |
|---|---|---|---|---|---|---|
| V8-PLAIN-DUAL | 1.0554095372 | 1.0554095372 | 0.99896503888 | 0.99894518398 | 0.99896554034 | PDE_OPTIMIZATION_NEGATIVE |
| V9-PLAIN-DAMPED-GN | 1.0285051156 | 1.0285051156 | 0.99894183584 | 0.9989232163 | 0.9989423061 | PDE_OPTIMIZATION_NEGATIVE |
| V8-PHASE-DUAL | 1.3192886662 | 1.3192886662 | 0.21451237122 | 0.21346679983 | 0.21453871283 | PDE_OPTIMIZATION_NEGATIVE |
| V9-PHASE-DAMPED-GN | 1.0187461988 | 1.0187461988 | 0.43776795997 | 0.43715907484 | 0.43778332738 | PDE_OPTIMIZATION_NEGATIVE |
| V8-PLAIN-REFERENCE-FIT | 3.5240979258 | 3.5240979258 | 0.025091592274 | 0.025729506595 | 0.025075270611 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 11.001030573 | 11.001030573 | 0.09939045116 | 0.068217087643 | 0.1000521103 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V8-PHASE-REFERENCE-FIT | 0.76628249085 | 0.76628249085 | 0.010408853984 | 0.010057213825 | 0.010417581545 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.8082166866 | 0.8082166866 | 0.013059766413 | 0.014403534682 | 0.013024032447 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |

原残差限值1e-6；严格场/复通道1e-4。D表示正/部分见证要求E_G、散射L2和curl三项均≤1e-3/1e-2，不能用其残差或拟合成绩替代C评分。

| V9路线 | total E L2 | total curl/H | 六点total复E | 六点total复H | 六点散射复E | 六点散射复H |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 0.68501572698 | 0.68306765072 | 0.67831184805 | 0.67166506315 | 1.0025426415 | 1.0000488943 |
| V9-PHASE-DAMPED-GN | 0.2997836436 | 0.29935225201 | 0.29333839474 | 0.28993816387 | 0.4335531658 | 0.43169185967 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 0.046780149988 | 0.068414721765 | 0.040822187554 | 0.063899892032 | 0.060335056599 | 0.09514119444 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.0098772834789 | 0.0089057147665 | 0.0086735824179 | 0.0098364759417 | 0.012819525789 | 0.014645628348 |

| V9路线 | total通道 | outgoing通道 | boundary-outgoing通道 | scattered通道 |
|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 0.56288107191 | 0.27015563712 | 0.25968056801 | 0.99934289584 |
| V9-PHASE-DAMPED-GN | 0.22412350933 | 0.10756842338 | 0.10405173287 | 0.39791040776 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 0.10708988446 | 0.051397954931 | 0.050808497759 | 0.19012811159 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.013575254686 | 0.0065154643877 | 0.0063884466725 | 0.024101599798 |

每类通道完整40级，以物理side/m/n/极化/参考平面对齐；相对误差分母是整类参考复向量范数（含固定近零自然尺度），不是逐个近零幅值。原复数值、绝对差、实际分母、全部六点及逐级功率保存在[原始PDE比较](records/pde_comparison_v9.json)和通道CSV中；不拟合全局相位。

| V9路线，入射功率归一 | R | T | A_balance | A_volume | R00_s | R00_p | R00_total |
|---|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 0.83742149248 | 0.11324361848 | 0.049334889034 | 0.46508410374 | 0.83732200974 | 4.9136786443e-10 | 0.83732201023 |
| V9-PHASE-DAMPED-GN | 0.79552935118 | 0.056384531239 | 0.14808611758 | 0.26902804567 | 0.7955167162 | 3.6564527673e-07 | 0.79551708185 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 0.82174534833 | 0.036121409888 | 0.14213324178 | 0.15705055129 | 0.8122280192 | 0.0016546189228 | 0.81388263812 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.81034611294 | 0.032231395236 | 0.15742249183 | 0.15453568083 | 0.81031486242 | 2.1748139964e-05 | 0.81033661056 |

| V9路线 | 能量闭合绝对差 | 最大逐级功率差 | 原total增广残差 | q30相对漂移 | G/L2/curl恒等式差 |
|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 0.4157492147 | 0.080861244804 | 0.48720468468 | 4.2757519299e-15 | 4.7787602612e-14 |
| V9-PHASE-DAMPED-GN | 0.12094192809 | 0.024032411413 | 0.4825818686 | 1.6269959963e-15 | 6.1605709991e-14 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 0.014917309507 | 0.004694092096 | 5.2112075577 | 1.8489166304e-12 | 3.7074246703e-14 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.0028868109962 | 0.0019419560478 | 0.38285366788 | 1.5898226722e-15 | 5.9830605731e-14 |

能量闭合使用独立A_volume：R+T+A_volume−1；A_balance=1−R−T本身不能证明闭合。能量/功率限值1e-5、逐级功率1e-6。原区域均独立保存，界面区域包含两侧cell，不通过只看全域平均掩盖局部差。

| C原区域 | 区域 | 散射L2 | 散射curl | total L2 | total curl |
|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | air | 0.99483720218 | 0.99719499697 | 0.65109861627 | 0.64841413239 |
| V9-PLAIN-DAMPED-GN | substrate | 0.99917971262 | 0.99920390392 | 0.88297202669 | 0.88297412889 |
| V9-PLAIN-DAMPED-GN | grating | 1.0053676617 | 1.0016492216 | 0.72540544971 | 0.72463352332 |
| V9-PLAIN-DAMPED-GN | interface_near | 1.000599036 | 0.99991888028 | 0.69727140243 | 0.69605421773 |
| V9-PHASE-DAMPED-GN | air | 0.43680815897 | 0.43655668808 | 0.28588113438 | 0.28386577048 |
| V9-PHASE-DAMPED-GN | substrate | 0.38800719323 | 0.39181829228 | 0.34288075854 | 0.34624105646 |
| V9-PHASE-DAMPED-GN | grating | 0.44457811683 | 0.44616029761 | 0.32077756334 | 0.32277038852 |
| V9-PHASE-DAMPED-GN | interface_near | 0.43491529362 | 0.43577416967 | 0.30307244541 | 0.30334705621 |

| D原区域 | 区域 | 散射L2 | 散射curl | total L2 | total curl |
|---|---|---|---|---|---|
| V9-PLAIN-FIT-GN-DIAGNOSTIC | air | 0.067276100148 | 0.10534038527 | 0.044030697303 | 0.068496326928 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | substrate | 0.12750804002 | 0.16320723056 | 0.11267846123 | 0.14422257726 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | grating | 0.055903092914 | 0.076207559029 | 0.040335898798 | 0.055131627731 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | interface_near | 0.066535412229 | 0.090800599388 | 0.046365465612 | 0.063207267532 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | air | 0.014815053418 | 0.012856197038 | 0.0096961198869 | 0.0083595885193 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | substrate | 0.015543021338 | 0.017609047805 | 0.013735319961 | 0.015560721476 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | grating | 0.013534855662 | 0.012466574016 | 0.0097658383425 | 0.0090188234147 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | interface_near | 0.015176060203 | 0.013334349378 | 0.010575497677 | 0.0092821830937 |

## 共同累计时间与已有L-BFGS

| 表示 | 共同目标s | GN保存点s | GN差距s | V8保存点s | V8差距s | native下降倍数 | aug下降倍数 | 研究信号 |
|---|---|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 9291.6953416 | 9194.2257484 | 97.469593144 | 9290.8250096 | 0.87033197901 | 1.0094418096 | 1.0094418096 | 0 |
| V9-PHASE-DAMPED-GN | 8745.0180056 | 7687.3372678 | 1057.6807378 | 8744.2674016 | 0.750603989 | 1.2649844162 | 1.2649844162 | 0 |

共同窗口由两条逻辑路径终点取较短者，状态按实际保留时间选取。没有历史保存态则NOT_RETAINED，不重放、不利用标签选择。GN接受outer和L-BFGS closure不等价，时间差和原方程/场的未过量一起报告。

## 真实工作量、阻尼与Gram费用

| 路线 | 旧前缀归属s | 新段worker时钟s | 逻辑路径s | 接受outer | 完整loss/梯度 | 试探loss | K | JVP | VJP | 停止原因 |
|---|---|---|---|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 1097.6413081 | 9525.9775147 | 10623.618826 | 29 | 30 | 37 | 2449 | 2449 | 2479 | WALL_BUDGET_SAVE_RESERVE |
| V9-PHASE-DAMPED-GN | 1144.848724 | 9483.4139183 | 10628.262646 | 54 | 55 | 75 | 1923 | 1923 | 1978 | WALL_BUDGET_SAVE_RESERVE |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 989.70066931 | 2437.5242545 | 3427.2249358 | 6 | 7 | 8 | 265 | 265 | 272 | WALL_BUDGET_SAVE_RESERVE |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 1019.1045315 | 2402.8554933 | 3421.960028 | 4 | 5 | 4 | 247 | 247 | 252 | WALL_BUDGET_SAVE_RESERVE |

表中worker逻辑时钟用于路径上限；[资源账](records/resource_costs_v9.json)按完整launcher单调时钟收费，包含退出尾段。历史前缀不在本项目累计账重复相加。内层尚未完成的试探被回滚，已耗工作与费用仍在总计中。

| 路线 | d_G（C）或d_ref（D） | h0六次估计 | 终态mu | A | AH | 完整native审核 | Gsolve | G乘法 | PC构造数 |
|---|---|---|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 0.0011981303657 | 1673393.1176 | 0.39499955481 | 2524 | 2479 | 7 | 2525 | 0 | 2 |
| V9-PHASE-DAMPED-GN | 0.0011981303657 | 506073208.19 | 8.7029320213 | 2066 | 1978 | 12 | 2067 | 0 | 0 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 984.6107903 | 1205.0447139 | 0.016530105815 | 0 | 0 | 3 | 0 | 285 | 0 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 984.6107903 | 119.3106327 | 0.0014729707741 | 0 | 0 | 2 | 0 | 260 | 0 |

| C fresh RESEARCH_ONLY Gram | setup s | solve次 | solve s（嵌套） | 最大真相对残差 | 释放前RSS B | 释放后RSS B |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 66.847788519 | 2525 | 619.65686641 | 9.5164549602e-13 | 1073541120 | 562438144 |
| V9-PHASE-DAMPED-GN | 67.030681012 | 2067 | 590.01069994 | 1.4225179597e-12 | 1130549248 | 619446272 |

| 参数range/Ritz PC | 来源outer | 保留rank | K作用数 | setup s（嵌套） | 正交缺陷 | 投影对称差 |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 4 | 32 | 64 | 195.64457824 | 8.0140662736e-15 | 1.4154597098e-15 |
| V9-PLAIN-DAMPED-GN | 9 | 32 | 64 | 197.40057131 | 8.0479041775e-15 | 1.2267380426e-15 |

| 路线 | 试探行 | 接受行 | 拒绝行 | inexact试探 | CG迭代合计 | Cauchy试探 |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 37 | 29 | 8 | 21 | 2207 | 0 |
| V9-PHASE-DAMPED-GN | 75 | 54 | 21 | 25 | 1687 | 0 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 8 | 6 | 2 | 0 | 217 | 0 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 4 | 4 | 0 | 2 | 128 | 0 |

完整mu、内部迭代、pred/ared/eta、接受与拒绝、PC谱/来源及所有预算在[内层历史](records/inner_solver_history_v9.json)。K作用还包括真线性残差复核、预测下降、h0及PC构造，不能只用CG迭代数估算。互斥全阶段wall收费，嵌套G/JVP/VJP/K计时不再次相加。旧V8没有保存的d_G仍为NOT_RETAINED，不倒填本轮数值。

## 全批资源、排障与结论边界

| 子包，新增有载/辅助 | 实收s | 本轮限额s |
|---|---|---|
| A | 954.36190151 | 7200 |
| B | 204.88059772 | 3600 |
| C | 19014.926468 | 21600 |
| D | 4846.8746953 | 7200 |
| E | 337.56714569 | 3600 |

截至本页数据冻结，新增保守账25358.610808s，旧账74341.020606s全部保留，累计99699.631414s；后续浏览器/交付尾段继续补入资源JSON。旧失联3284s和重放费用未删除。CPU-only/MPI1/数学及Torch线程1；各自启动按现场闲核和至少384GiB邻增长余量复核，自身swap0，无OOC。峰值为约0.5s采样的同时数值进程树RSS，tmux管理server另记启动快照，不能称内核连续上限。

| V9阶段/attempt | 实际source SHA | 完整launcher/辅助s | 同时整树峰值B | 分类 |
|---|---|---|---|---|
| v9_fit_gn_compare | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 59.305431874 | 477523968 | COMPLETED |
| v9_fit_gn_reconstruct | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 42.918935966 | 548253696 | COMPLETED |
| v9_gn_checks | 2f7d6c0f6d9102742c951907df25efa04aaf16cc | 178.73114433 | 1256349696 | COMPLETED |
| v9_gn_compare | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 57.939700314 | 479256576 | COMPLETED |
| v9_gn_reconstruct | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 40.910086819 | 553992192 | COMPLETED |
| v9_p5_checks | c044db06f07cf0267f92808efdaf669151c64dfd | 4.9715540489 | 161312768 | WORKER_FAILED |
| v9_p5_checks | 921f21302472ce214e0a33ce46ae63cb8a568ec2 | 37.020646618 | 917921792 | WORKER_FAILED |
| v9_p5_checks | f5b3c7d93af2cb57e3e4e0de48c4d23997d7f4f7 | 489.90165027 | 1695006720 | COMPLETED |
| v9_p5_reference | ee295a30c2631a8f019ba3e435b83d211ea051a7 | 147.77891903 | 7190847488 | COMPLETED |
| v9_p_ladder_compare | 2f7d6c0f6d9102742c951907df25efa04aaf16cc | 260.03396415 | 486072320 | COMPLETED |
| v9_phase_fit_gn | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 2406.0687207 | 627761152 | COMPLETED |
| v9_phase_gn | ebff76949c78560187d836830483172faf0cfc9a | 9486.6698242 | 1264005120 | COMPLETED |
| v9_plain_fit_gn | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 2440.8059746 | 555671552 | COMPLETED |
| v9_plain_gn | bc4ecb2192e687273926e1d1f0ce5e7df4b78542 | 9528.2566436 | 1264013312 | COMPLETED |
| v9_a_abi_20261001T010900278424Z | development_worktree | 2.5551030589 | 145231872 | COMPLETED |
| v9_a_final_unit_20261001T010942434296Z | development_worktree | 1.911963771 | 50946048 | COMPLETED |
| v9_a_mpc_repair_20261001T011257946493Z | development_worktree | 2.489312315 | 139632640 | COMPLETED |
| v9_a_small_geometry_repair_20261001T011543902746Z | development_worktree | 5.782570436 | 441442304 | COMPLETED |
| v9_a_unit_20261001T010831297367Z | development_worktree | 1.91621781 | 51146752 | COMPLETED |
| v9_b_acceptance_telemetry_20261001T020239255963Z | development_worktree | 6.471924344 | 377495552 | COMPLETED |
| v9_b_final_gn_unit_20261001T012950627515Z | development_worktree | 5.886681473 | 374759424 | COMPLETED |
| v9_b_gn_unit_20261001T012746654582Z | development_worktree | 7.212424328 | 374902784 | COMPLETED |
| v9_b_runner_unit_20261001T013632353668Z | development_worktree | 6.5784232521 | 377688064 | COMPLETED |
| v9_e_final_checks_20261001T044524311059Z | development_worktree | 2.578923562 | 158941184 | COMPLETED |
| v9_e_lint_20261001T044448050021Z | development_worktree | 1.9429350749 | 42983424 | WORKER_FAILED |
| v9_e_ml_transaction_20261001T044546918126Z | development_worktree | 6.593929189 | 375545856 | COMPLETED |
| v9_e_provenance_check_20261001T072845745154Z | development_worktree | 2.733347357 | 102842368 | COMPLETED |
| v9_e_targeted_20261001T044342178101Z | development_worktree | 2.643855533 | 157470720 | COMPLETED |

p5小资格的配置阶次与粗网格身份问题已分别修复，失败费用保留；检查器未使用名称的lint失败也已定向复查。FE/ML分派先验修复未被写成真实候选失败。完整failure→hypothesis→change→test→retry见[修复账](records/repair_log_v9.json)。

下一轮仅建议先资格化等价的分块切线/激活复用：在这四个已冻结状态上做有界 JVP/VJP 配对与计时，保持原矩、参数导数和目标完全不变，再决定是否值得开展同预算 GN 对照。本轮实测 JVP＋VJP 占 C 新段约90%、D约97%–98%，是可定位的主要费用；该建议不授权继续训练、换 loss/PC、扩大模型或放宽门限。 本轮不自动新增loss、PC、载波、网络宽度、p6/h细化、目标尺寸5nm或0.7nm。p5是A的独立精度审计，不替换C/D的同p3基准。

## 未提交工作与费用位置

| 路线 | 最后完整边界之后K作用 | 完整PC构造 | 细分 |
|---|---|---|---|
| v9_plain_gn | 18 | 2 | CG/PC逐次子阶段NOT_RETAINED |
| v9_phase_gn | 30 | 0 | CG/PC逐次子阶段NOT_RETAINED |
| v9_plain_fit_gn | 55 | 0 | CG/PC逐次子阶段NOT_RETAINED |
| v9_phase_fit_gn | 103 | 0 | CG/PC逐次子阶段NOT_RETAINED |

这部分仍包含在总K/JVP/VJP与launcher收费。D-phase最后一个完整边界在约1415.49s；余下工作没有产生第五个完整接受态。没有保留每次K的调用栈，不能为最后103次作用伪造具体PC分解时间、谱或收益；完整PC表仅表示成功完成的构造。

| 路线 | 完整JVP嵌套秒 | 完整VJP嵌套秒 | 两者占新段worker时钟 |
|---|---|---|---|
| v9_plain_gn | 4462.9157668 | 4117.1512163 | 0.90070199829 |
| v9_phase_gn | 4493.7363433 | 4017.7333797 | 0.89751114908 |
| v9_plain_fit_gn | 1347.3866596 | 1028.8909497 | 0.97487342124 |
| v9_phase_fit_gn | 1340.251867 | 1018.4803057 | 0.98163713099 |

这些导数接口计时包含网络重算与矩操作；网络前向、矩和反向子计时与之重叠，不能再次相加。资源账只加互斥的完整阶段wall。
