# V12 最新交付：真实固定头梯度未取得数值资格，有限函数值备选为负

在相同 0.7 nm、384hex/p3、完整40端口的三维缺口 micro 上，本批尝试先固定输出头，用原 Maxwell 方程的真实残差判断隐藏层改变是否有效。它只在数值可信时才允许有界 L-BFGS；旧 V11 大系数制造与实际头 `1e-8` Gate **仍为 FAIL**。前两次是受影响 T1 接线失败并保留，第三次完成 T1；T2 的真实偏导有限差分未过 Gate，F 的 8 个有限函数值试探均使损失升高，所以**没有接受任何新的隐藏状态**。T4 仅独立重验旧修正后的物理起点。[Response V12](../response_v12.md)、[方法和完整结果](actual_loss_block_descent_v12.md)、[raw Gate](records/qualification_and_dispatch_v12.json)。下方 V11 及更早“最新”标题是保留历史，不代表本轮状态。

| 同一模型／方法、为何比较 | 原 Schur/native/port 相对残差；原门限各 `1e-6` | 散射 E/scaled-curl 同离散误差；限 `1e-4` | 结果与证据 |
|---|---|---|---|
| V11 唯一修正后的随机隐藏＋稳定头，V12 原物理起点 | **0.797721738／0.309359507／2.051e-19** | **0.734256809／0.734361587** | 原方程和场仍失败，端口虽合格不代替整方程；[候选CSV](records/candidate_comparison_v12.csv) |
| T1 已消费 M2 与物理状态的同算子分账 | 两者原作用对薄列组合差 `1.84e-12`／`1.04e-12`；物理网络回写 `3.80e-8`、`Pγ/Zc` `2.36e-7` | 仅诊断，不产生新物理候选 | 旧 M2 `1e-8`失败保留；[残差等式](records/roundoff_decomposition_v12.json) |
| T2 固定头原 loss 偏导 | 同点损失 `0.318179986`，分辨率 `2.22e-14`；三真实方向 FD 最小步相对差 `0.0635/0.0760/0.1742` | 未准入 L-BFGS，不能据此称隐藏训练失败 | [30点步长表](records/fixed_head_gradient_checks_v12.json) |
| F 仅函数值两方向×正负×两步长 | 最小试探 loss `2.80461`＞`0.31818`；native `0.91847`＞`0.30936` | 已执行负结果，0个接受 hidden、0个头建议 | [进度](records/block_descent_progress_v12.jsonl) |
| T4 独立参考和最终目标 | 只读旧 REF7，1个状态；R/T/A_balance/A_volume诊断 `0.0849663/0.798046/0.116988/0.00485487`，能量闭合 `0.112133` | **无 official R/T/A**；p4 enrichment、p6、最大目标、h/p/M/MPI/波长扫描未运行；48小时资格 unknown | [完整40通道/资源](records/run_index_v12.json) |

正式五次 one-run（含两次接线失败）监督 wall 合计 **`182.268 s`**；同时进程树采样 RSS 最大 **`2322427904 B≈2.163 GiB`**、自身 swap0，所有后代已清场。三个成功阶段运行源码均 `d9df7068ca3310a0499164251a57841dbdfbc7f5`，不是后续 checker／文档 HEAD。独立 FE／CPU ML 环境及缓存、自有锁、现场 CPU0、MPI1、线程1、整树16GiB hard/12GiB warn保持；两次修复只涉 Task042 子进程接线与事件名，不改原方程、材料、邻任务或旧负结果。无 cgroup 委派，不宣称连续内核上限或零干扰；共享负载下速度结论 `INCONCLUSIVE`。[全部费用和历史下界](records/resource_costs_v12.json)。候选从未构造 global p4 LU、全局 S/CSR、ILU/Riesz 或隐藏 fallback。唯一下一建议是固定同头／同三方向的 JVP/VJP 与原作用线性化配对，需新 review 授权；本批不实施，不合并 master。

# V11 历史交付：稳定头大系数回收未过 Gate，未启动隐藏更新

本批对同一0.7 nm、384hex／p3、40复端口三维缺口micro，先检验“答案已经在当前网络空间里时能否从原Maxwell方程稳定地找回”，再计划改变隐藏特征。小系数见证通过，大系数失败；一次原分解修正改善残差但未到1e-8，因此不使用该不可靠头训练。下列功率均仅是未资格化诊断，完整解释见[Response V11](../response_v11.md)和[结果](stable_head_varpro_v11.md)。此前V1–V10全部历史正文保留。

| 固定模型／方法与比较目的 | 原Schur／native／port固定RHS相对残差；限1e-6 | 同mesh散射E／scaled-curl差；限1e-4 | 能量闭合；限1e-5 | 状态、原因、证据 |
|---|---|---|---:|---|
| V10-B0随机hidden原薄头，历史对照 | 0.797324／10.964503／0.00582247 | 0.732080／0.732146 | 0.111831 | 旧负结果，无神经增量；[历史CSV](records/candidate_comparison_v10.csv) |
| V11小系数M1制造RHS，测试数值接线，不是物理求解 | 原制造残差1.2347e-14、已知z差5.5365e-13、齐次恢复9.2584e-17 | 不产生物理场资格 | 不计算 | 三项内部门限通过；[见证](records/manufactured_recovery_v11.json) |
| V11大系数M2制造RHS，测试约1.30e5输出权重 | 初始3.1175e-7、同分解修正后**2.8952e-8＞1e-8** | 不产生物理场资格 | 不计算 | S1失败，raw头1.2916e-7亦失败；不使用其梯度训练 |
| V11随机hidden正交头＋原Hhat40闭合，唯一物理基线 | **0.797721738／0.309359507／2.051e-19** | **0.734256809／0.734361587** | **0.112132956** | 真实网络与薄残差差3.9598e-8＞1e-8，原方程／场仍失败；[独立Gate](records/qualification_and_dispatch_v11.json) |
| V11真实VarPro FD／L-BFGS隐藏更新／最终目标 | FD0、试探0、接受0 | 无可验新隐藏状态 | 无official R/T/A | 因S1/S2未过停止；新p4参考、p6、最大0.7nm模型未运行，48小时资格unknown |

V11物理基线的R_total/T_total/A_balance/A_volume为0.0849662553/0.7980459227/0.1169878220/0.0048548661；R00_s/R00_p为0.0849640599/1.28216e-7。原p3参考R/T/A≈0.117645819/0.877047783/0.005306398；新功率差与能量闭合远超门限，**无新official结果**。[40复通道](records/channel_observables_v11.csv)、[完整候选CSV](records/candidate_comparison_v11.csv)。未做p/h、Full3D/Hybrid、M或MPI的本批对照，不能以同一micro估计这些影响。

正式三stage均clean source：MAIN `a2cba71533edafb4fa1c701eae503e7ab526eac4`，REPLAY／VERIFY `036e36ec637488b1baddd9b061c80c6f34cde254`，后续文档HEAD不冒充运行源码。监督wall **574.980116768s**、同时采样过程树RSS峰 **4668329984B**、own swap0；V6–V10有载carry11159.165418899036s，正式wall累加下界11734.145535666961s，辅助工作另在四小时elapsed内。[全部费用](records/resource_costs_v11.json)、[数据／源码](records/run_index_v11.json)。现场CPU0/MPI1/mathTorch1、自有锁/16GiB hard/12GiB warn、独立缓存、无GPU/cgroup委派；邻任务不操作，影响和无争用速度 **INCONCLUSIVE shared-workstation**。

真实目标仍缺合格micro原方程／散射场与独立离散精度、目标规模存储/通道/单步和迭代预算证据；旧global p4逆关闭，候选无global p4 factor/完整S或CSR/隐藏fallback。Review V8实际GitHub5表5公式通过；结果页发布核验另列。唯一下一建议是下一review若批准，对冻结M2及相同P/A/真实回写作一次有界浮点误差来源归因；本轮不自动训练/改rank/放宽Gate。下方所有“最新”字样仅为历史标题。

# V10 最新交付：输出头／精确端口多路径负结果，有限诊断完成

固定原0.7nm／384hex／p3／40复通道。网络隐藏层提供空间函数，本批直接由原有限元方程求线性组合，检验是否可免去线性输出层长训练；同时用随机隐藏函数区分已学习特征与线性代数收益。薄矩阵和稳定分解增加设置内存，仍不能外推最终大模型。所有原V1–V9正文按字节保留。

| 模型／方法／比较目的 | 原Schur／native／固定RHS端口残差；无量纲measured | 散射E L2／curl-H相对差 | 状态与具体原因 |
|---|---|---|---|
| A原NN7方向的复幅相＋40端口 | 0.912888／0.687417／0.00458282 | 0.634723／0.634718 | 原S/b决定c，原方程1e-6及场1e-4均失败 |
| B1已训练隐藏＋直接线性头 | 0.797694／4.381516／0.00695473 | 0.700726／0.700810 | rank1600；降低Schur loss却native放大 |
| B0随机隐藏seed420906＋同线性头 | 0.797324／10.964503／0.00582247 | 0.732080／0.732146 | rank1600；原loss略优B1，场略差，未证明神经增量 |
| C同B1空间、原Hhat精确端口闭合 | 0.798258／0.309567／6.5094e-17 | 0.697842／0.697932 | rank1560；只解决port/native放大，体场未合格 |
| D1参考辅助固定空间拟合，非求解 | B1/B0 trace差0.00115672／0.00115235 | E约0.001025，curl约0.00320 | 远优于方程拟合但仍超1e-4；不是整个NN或物理L2下限 |
| D2原curl/质量作用定位，非求解 | LSQR8误差两项约10.402，相加V=0.04745 | 重组最大operation差1.697e-14 | 强抵消固定方向证据，非全局奇异/唯一根因证明 |
| E/P与最终目标 not_run | 无候选P/P+或严格资格；micro未通过 | 无新p4 enrichment/最大模型 | E/P未准入；最终0.7nm／48h NOT_QUALIFIED |

四候选R/T/A_balance/A_volume分别为A 0.0889836/0.835105/0.0759116/0.00502812，B1 0.0845095/0.796652/0.118838/0.00484248，B0 0.0851194/0.798195/0.116685/0.00485441，C 0.0843697/0.796538/0.119092/0.00484248；能量闭合差0.07088–0.11425，全部仅未资格化诊断，无official R/T/A。R00_s/R00_p及完整40通道见[候选CSV](records/candidate_comparison_v10.csv)、[通道](records/channel_observables_v10.csv)，不把背景主导total误差约0.07当作散射准确。

正式12次launch含失败与保存向量重放共650.093757705s，整树同时采样峰2.213718GiB、自身swap0；B1/B0新构建204.3765/190.4928s。B1/A/C另继承NN7原7142.986s训练及原FE/moment/真实梯度设置；全账不重复累计父子时间，不清零历史carry10209.145962639828s。[全过程成本](records/resource_costs_v10.json)、[run index](records/run_index_v10.json)。共享CPU实时核11/13/0、MPI1/mathTorch1/自有锁/16-12GiB采样整树监督，独立缓存、无GPU/cgroup委派；不修改邻任务，未观测持续PSI压力，影响与正式加速INCONCLUSIVE。

每正式stage clean source绑定：A/B为1fb8a949bbed81f34645d96e80c7025a3b22ef4d；C/D/三见证补核为6e564a66868374560dae66321564f3e767f5639c；D2仅元数据修复／保存向量重放为6cbaec7848936b81bf2c34c862358a38090c58c0。最初B只有一个见证，三见证补核晚于冻结，时序偏差保留。D reference barrier后无训练／新候选。原task/review/response/records和旧p4负结果不改；普通default/原方程/MPC/材料不改，无global p4 factor/完整S/CSR/正规方程/ILU/Riesz/hidden fallback。

最终25相关pytest及三个ML矩/输出头见证通过，真实C九FD最大1.088e-8。Review V7实际GitHub3表5公式通过，最终文档显示/历史保护见新compact记录；无full pytest/MPI2/4/CI声明。[Response V10](../response_v10.md)、[完整结果](autonomous_neural_head_v10.md)、[独立Gate](records/qualification_and_dispatch_v10.json)、[journal](records/progress_journal_v10.jsonl)。唯一下一建议是固定随机特征空间内一次已知非零系数的制造RHS回收检查，区分薄LS/回写稳定性与目标表示/弱响应；未自动实施。全部可执行路径结束后提前交付，不以重复失败填满7小时，不merge。

# V9 最新交付：固定误差定位完成，求解负结果保留

本轮把六个固定向量恢复成真实FE场，定位遗漏散射和原方程响应。完成D0–D4，独立状态FIXED_ERROR_DIAGNOSTIC_COMPLETE，solver_pass=false；没有新增求解、训练、参考LU或神经增量资格。[Response V9](../response_v9.md)、[完整定位](frozen_error_localization_v9.md)。

| 对象／方法／身份 | 实测与边界 | 证据 |
|---|---|---|
| 原微型模型 | 0.7nm/384hex/p3/h0.175/MPI1，FE34050/trace18144/内部13824/slave2082；top20＋bottom20完整40通道，原canonical Si | [六状态／全部数组身份](records/frozen_state_inventory_v9.json) |
| 准确同离散参考 | REF7原Schur/native6.424e-12/3.018e-12；仅offline diagnostic，不升级连续收敛 | [原残差／齐次恢复](records/error_identity_checks_v9.json) |
| 原方程与恢复配对 | Se=r-r_ref最大2.925e-12；齐次恢复3.082e-16、增广/native1.601e-11/1.589e-11；错误默认recover会多加0.00120339特解 | [独立Gate及最小checker修复](records/gate_decisions_v9.json) |
| 散射幅值／形状 | NN7范数比0.457259、相关模0.999809，仍有幅值/相位缺口；LSQR7/8范数比0.002574/0.003671、误差约1 | [系数与真实E/H场分开](records/field_error_components_v9.csv) |
| 区域／端口 | 192/8/48/136互斥区域，主要y分量贯穿全域，误差约50/2/12.5/35.5%；上下(0,0,s)主导，不等于功率差 | [区域](records/region_error_integrals_v9.csv)、[全部40通道复误差](records/port_error_components_v9.csv) |
| 原体／端口作用 | LSQR8 body/port抵消0.059273/0.000209768，方向增益0.0683784；不推导条件数或唯一病态根因 | [含复交叉项的原分量](records/equation_components_v9.csv) |
| 资源／source | clean a1dc3466294c30b6de292468d6dd1aa9b685b193；一次正式wall234.760s，整树峰0.939442GiB/swap0；S11/SH0/unc34/recover16，12小Hp solve及16审核乘法 | [run index](records/run_index_v9.json)、[包含失败/辅助/发布的费用账](records/resource_costs_v9.json) |
| 旧物理量与资格 | 原R/T/A/A_volume/重要衍射级仅引用V7/V8绑定记录；四候选仍不满足原方程1e-6与场1e-4，旧p4路线关闭 | [V7盲验证](records/independent_blind_validation_v7.json)、[V8盲验证](records/scaled_blind_validation_v8.json) |
| 未运行／原因 | 无新模型、p/h/M/MPI扫描、loss/D/PC/网络变化、p4 enrichment/F5/p6/GPU/最大目标/seed420620；本批只定位 | [停止与唯一建议](records/gate_decisions_v9.json) |

共享CPU授权继续，现场选正式CPU0/单线程、16/12GiB树监督、自有锁及隔离缓存；无cgroup委派，不称内核连续限额。未观察持续PSI压力，缺邻任务可比速率，影响INCONCLUSIVE，全部费用标shared-workstation。初次checker用抵消后的结果当运算尺度导致失败，单次局部修复后仅重放数组checker，原失败raw/source/费用保留。最终23相关pytest通过，Review V6实际GitHub5表/6公式通过。没有新的official物理结果或无争用性能结论。

数据/正确恢复未见错误；主导散射遗漏遍及全域，NN和LSQR结构不同，但表示上限、优化原因和V内部机制仍未确定。唯一下一建议为待review后对冻结LSQR8误差与参考方向，量化原未凝聚V的curl-curl/epsilon质量及必要边界作用平衡；本批未执行。最终0.7nm/48h目标仍NOT_QUALIFIED，目标规模成本/步数unknown。

以下全部历史正文按字节保留。

# V8 最新交付：列尺度仍未收敛，等价批量计算降低单步成本

列均衡把未知量换成作用大小相近的单位；batch8把相同网络／边面矩同时算八个单元。前者是数值假设，后者是实现成本，两者分别验收；停机事务另修复保存边界。

| 固定micro／measured | 结果／限值／边界 | 证据 |
|---|---|---|
| 对象 | 原0.7nm／384hex／p3／h0.175nm／Full3D，40port／MPI1；FE34050/reduced18184，材料canonical表不变；Hybrid/p/h/M/MPI影响未新测试 | [身份](records/run_index_v8.json) |
| C1 | 7强Wolfe／一致checkpoint测试PASS；V7接受点unknown，旧负结果不改 | [停机](records/optimizer_stop_semantics_v8.json) |
| C2原方程 | Schur0.068283273738/native0.026675035784/port op0.049261505581，全部>1e-6；恢复2.86e-15、slave0 | [对照](records/scaled_lsqr_comparison_v8.csv) |
| C2真实散射 | L2相对差0.998598490718（限1e-4，研究限0.5），严格及研究正信号FAIL；R/T/A仅diagnostic | [全场/40channel](records/scaled_blind_validation_v8.json) |
| C3 | 三状态等价＋非零FD通过；全步三pair中位降幅48.55%，新增缓存33.48MiB，无训练 | [样本](records/batch_costs_v8.csv) |
| 费用／shared-workstation | 11正式树wall791.658916s，树峰816152576B/own swap0/GPU不用；所有aux及历史累计见最终账，不重复累加嵌套 | [资源](records/resource_costs_v8.json) |
| 所有权限制 | C2初次额外读未用3.21MiB moment包，已修adapter/边界回归，无完整重放；无CSR/参考/global p4因子部署 | [完整说明](scaling_and_execution_v8.md) |
| 未运行／目标 | 长训练/p4 enrichment/F5/p6/大模型/GPU/seed420620皆not_run，0.7nm/48h NOT_QUALIFIED，神经数值增量未证明 | [独立Gate](records/gate_decisions_v8.json) |

候选source `1a2984a44ca48573bbe18ffe8a7f8c5d6bdacc05`，C3 source `52d47d35656c5a763bed07e07f827fb6fb285bb7`；后续文档HEAD不是run source。Review V5实际GitHub4表/2公式，新响应见[Response V8](../response_v8.md)。邻影响及无争用加速INCONCLUSIVE。唯一下一建议：固定pilot上仅对已经冻结的误差方向做原S/恢复/端口分量审核，复用已有p3参考作离线核对，定位残差下降为何没有恢复散射；不训练、不建新PC、不扫描。 未实施，停止等review，不合并。下文V1–V7全部历史正文按字节保留。

# V7 最新交付：材料解除，真实 N1 通过，三路线数值负结果

网络通过原有限元边／面矩产生当前问题的trace，再由原局部方程恢复内部未知量，尝试避免全局分解；代价是网络优化与原S/Sᴴ作用。材料已经永久登记，本轮实际做了同一三维缺口micro的三路线和盲参考，不能把梯度正确、loss下降或参数少当成合格解。

| 项目／统一对象 | measured结论／边界 | 证据 |
|---|---|---|
| 材料／身份 | MATERIAL_READY_USER_SUPPLIED；四行canonical表，0.699999988→nominal0.7专用alias，n=0.999885140474+4.32477054e-6i、epsilon=n*n | [来源／载入](records/material_loaded_v7.json) |
| 唯一真实模型 | 384hex／p3／h0.175nm／MPI1；FE34050、trace18144、内部13824、slave2082；air200／substrate48／block136／notch8；完整top20＋bottom20=40 | [物理hash与库存](records/material_geometry_identity_v7.json)、[全部通道](records/channel_inventory_v7.csv) |
| N1真实接口 | S差2.605e-16、Sᴴ dot1.917e-15、native8.491e-15；非零内部/port；FD9项最大1.8213e-9、chunk0 | [真实N1](records/adjoint_gradient_checks_v7.json) |
| 三路线／资格 | NN wall stop1611closure、FREE2000closure、LSQR1921步；原方程／同离散场／功率全部0/3合格 | [对照](records/neural_fe_comparison_v7.csv)、[独立Gate](records/neural_fe_gate_decisions_v7.json) |
| 独立p3参考 | 三状态冻结后一次LU，释放后审核；Schur/native6.424e-12/3.018e-12，独立native1.437e-12；R/T/A0.117645819/0.877047783/0.005306398，A_volume0.005306398、闭合2.906e-12 | [E/H／功率](records/independent_blind_validation_v7.json) |
| 全过程费用 | 8正式阶段含后处理失败wall8579.825040766s，树同时采样峰1073967104B、own swap0；V6 carry＋全部辅助费继续计入10h，GPU/VRAM0 | [run index](records/run_index_v7.json)、[最终费用账](records/resource_costs_v7.json) |
| 未运行 | p4 enrichment因无合格候选不准入；p/h/M/MPI扫描、F5/p6、最大目标、四波长扫描、GPU、旧teacher和seed420620均not_run | [48h unknown](records/target_48h_budget_v7.json) |

| 路线／完整负结果 | Schur（限1e-6） | 原native（限1e-6） | port operation-relative（限1e-6） | 全场L2相对差（限1e-4） | 能量闭合（限1e-5） |
|---|---|---|---|---|---|
| NEURAL-TRACE | 0.913263145 | 0.661163226 | 0.003140447 | 0.069196457 | 0.07034118 |
| FREE-FE-OPT | 0.797338565 | 2.179411163 | 0.446120482 | 0.105509404 | 0.00733968 |
| FE-LSQR | 0.071602580 | 0.028727752 | 0.656567941 | 0.104639933 | 0.00337133 |

参考scattered L2=0.200411、total L2=1.91515；NN散射相对差0.6613，FREE/LSQR约1.0083/0.99995。NN得到部分真实信号但未合格；LSQR loss下降不等于完整散射响应，不能以弱材料对比或接近某项体吸收宣称通过。三候选RTA只作未资格化诊断；原完整E/H、复通道、逐级功率见[CSV](records/channel_observables_v7.csv)，恢复与slave-zero通过，其他Gate失败。神经增量NOT_DEMONSTRATED，shared-workstation性能和邻影响INCONCLUSIVE。

正式source：N1 70f5f5437533693e343ede67a37363e89b062330；三路线7c4037a279cefd8546c51e8ae6cf0172c3eab89d；参考19adac7e3babb50c0028714684c220b713979196；后处理最小修复1ff6f8ba3dcb48dee0fd41f762bf624822ea1457。一个UFL Form除法错误只重放FE/E/H/功率，无第二次LU／solve或训练，失败费用不删除。候选无global p4层/因子、global FE CSR/LU、Riesz/ILU逆、私有audit CSR或hidden fallback；不是只用网络参数内存，局部/端口packet209239672B、工作区/optimizer/激活另计。

用户Task042受控共享CPU授权继续，仅覆盖本任务§2.3独占限制；实时选核、MPI1/数学/Torch1、自有锁/整树16GiB hard/12GiB warn/swap0、独立cache。无cgroup委派不称连续内核限制，只停止自身树，邻任务不改；未观测持续PSI压力，缺可比阶段速率，不承诺零干扰。Review V4 GitHub4表1math通过，最终32相关pytest通过，不重装环境，不重跑旧campaign或full pytest，不宣称CI。

最终0.7nm／48h NOT_QUALIFIED：目标geometry/channels/配额/完整步cost/所需步数unknown，材料已ready。唯一下一建议为固定pilot上预登记、目标解无关的对角变量尺度均衡LSQR对照，原loss/验算不变；未实施，待review，不自动扩大模型或回旧p4。[Response V7](../response_v7.md)、[完整结果](neural_fe_single_solve_v7.md)、[模型/source身份](records/dataset_model_provenance_v7.json)。以下V1–V6全部历史按字节保留。

# V6 最新交付：材料阻塞，神经FE接口部分完成

按Review V3关闭旧小块／低秩／系数网络p4路线，V5 augmentation不执行，全部历史正文保留。本批新网络把三维复向量变为原有限元边／面矩，尝试直接求当前场；实际只完成材料独立接口，尚无原方程、物理场或神经收益资格。

| 项目／数据身份 | 结果／资源／未完成原因 | 证据 |
|---|---|---|
| 批次／终态 | V6_NEURAL_FE_SINGLE_SOLVE_PILOT；MATERIAL_0P7NM_BLOCKED，旧路线CLOSED_RESEARCH_NEGATIVE | [Response V6](../response_v6.md) |
| N0 geometry measured | 0.7nm设计、384-cell p3、FE34050／独立trace18144／slave2082；air200／substrate48／block136／notch8，y/z变化 | [材料／几何](records/material_geometry_identity_v6.json) |
| 材料／端口 not_run / derived | Si0.7nm源和复n缺失；已知top空气20通道derived，底侧／总量unknown，完整物理身份未冻结 | [source审计](records/material_source_audit_v6.json) |
| N1 interface measured | 完整p3矩／Piola／orientation／原MPC，FE插值相对差约1.8e-15；NN求积15/30差1.1695e-15；合成梯度FD最大9.7612e-9 | [分开Gate](records/adjoint_gradient_checks_v6.json) |
| 全部三路线 not_run | NEURAL-TRACE／FREE-FE-OPT／FE-LSQR均未启动，真实S/Sᴴ、native/port/recovery Gate不足；参数11696，未训练 | [对照CSV](records/neural_fe_comparison_v6.csv) |
| R/T/A/A_volume、全通道、E/H、误差 not_run | 无真实物理operator及参考，不产生official结果或成功残差；p/h、MPI、M影响未试验 | [独立决策](records/neural_fe_gate_decisions_v6.json) |
| 正式资源 measured / shared-workstation | 含失败三run总wall26.136697164s，树RSS同时峰314408960B，own swap0；实时CPU0/0/12、MPI1／线程1、16/12GiB树监督，无GPU | [完整账](records/run_index_v6.json) |
| 神经增量／48h unknown | 无求解对照；目标尺度／材料／通道／资源配额／完整步成本和所需步数unknown，最终NOT_QUALIFIED | [48h预算](records/target_48h_budget_v6.json) |
| 停止／唯一下一步 | 补齐并审核真实Si0.7nm来源／版本／单位／符号／数值；本批不自动实施、不回旧p4、不merge | [详细结果](neural_fe_single_solve_v6.md) |

成功接口真实source `2a2cb4af78ba869a26a1254b4b4b76c9ac158366`，首次失败source `64c128c3541887e22788343692cc4f7832a45696`；一次居中坐标载体最小修复后通过，失败保留／预算不重置。原A4/A6/default/旧结果不改，未建全局目标或p4因子、私有CSR或隐藏逆，未用目标准确解。用户Task042受控共享授权保留，只监督自身后代，无cgroup委派不冒称内核限制；未观察持续压力，邻影响／无争用性能inconclusive。旧seed420620池封存；正式目标、参考／enrichment、F5／p6未运行。23相关pytest＋两ML断言、局部静态／输入检查通过；Review V3 GitHub4表／4math通过，后续发布证据另列。

以下原V1–V5历史按字节保留。

# Task042 V5 最新状态：固定对象失效定位完成，严格粗逆仍未资格化

同一个残差分别测局部B、粗空间C与原两层B2，再做有限方向的最小二乘，区分空间覆盖与组合失效；这不是新的求解器或训练。所有数值比例dimensionless，绝对port为原数组欧氏范数，无新物理R/T/A。

| 最新范围 / 身份 | measured结论 / 边界 | evidence |
|---|---|---|
| 完成阶段 | Review V2 D0–D4，12/12共同state、3已消费teacher离线审核、24同r作用和192原方程审核 | [response_v5](../response_v5.md) |
| 固定模型 | 原Si13.5nm/p6h10对应p4、MPI1/80DtN，53084FE/21824reduced/8184464NNZ；S/B/双rank128 Z/U/R不改 | [预登记](records/localization_design_v5.json) |
| 覆盖 | 物理初态OLDPOD eta_r/e .9990665/.2216303、ERROR .9997845/.7134416；e与r覆盖区别明确 | [24覆盖](records/coverage_v5.csv) |
| 同向量组合 | port-only Bopt .9845925；OLDPOD B2opt .9926201/ZB .6171864，ERROR .9872461/.7423358；部分组合利用不佳，原A4/port仍失败 | [192审核](records/same_residual_actions_v5.csv) |
| 补空间 | 有效rank16/16，完整TV最小奇异值4.771224799/3.034800156；无已证near-null，不能据小投影谱断言真实奇异 | [探针](records/complement_probes_v5.json) |
| 资格 / 未运行 | strict0/192诊断修正，无新solver pass；fresh seed420620、F5、短波、NN/GPU/official均not_run | [D4及唯一建议](records/localization_decisions_v5.json) |
| 内存 / 时间 | 四阶段wall1144.401529s，整树同时RSS峰1135407104B，own swap0；shared-workstation/performance inconclusive | [完整费用](records/run_index_v5.json) |
| 源码 / Git / 环境 | 四阶段clean source`5d82651af0f723c73487783deb43969f05d46ed3`，canonical NN-Lab / origin同任务branch；只读native prefix/独立cache，实际现场CPU0/0/0/13数学1，自有树16GiB监督 | [前检](records/pre_run_checks_v5.json) |

D4三假设分别评价、多因素或INCONCLUSIVE允许；[中心说明](failure_localization_v5.md)列实际连续指标、范数分母、完整像与限制。未修改A4/A6/80通道/原1e-10，未构造global p4 factor或隐藏fallback。未发现持续压力，但邻阶段没有可比时长，不宣称绝对零影响/提速。唯一下一试验仅建议、未实施；等待review，不merge。以下V1–V4正文逐字保留。

---

# Task042 V4 最新状态：两个全局空间仍未通过严格粗逆

| 最新范围 / 身份 | 实际结果 | 证据 |
|---|---|---|
| 合同 / 完成阶段 | 正式Review V1，V4_GLOBAL_ERROR_TWO_LEVEL；P0/P1/两P2/两P3完成，不沿用V3局部停滞禁令 | [response_v4](../response_v4.md) |
| 两空间 | 旧256训练对Q vs新16轨迹的128解误差；都重建Schur编码，rank均128，四恒等式和真实接口合格 | [空间](records/coarse_space_algebra_v4.json) |
| 收敛 / 负结果 | 6非零诊断strict0/6，全部256步；physical/mixed未满足预登记native和固定Schur各0.1 | [Gate](records/gate_decisions_v4.json)、[原始字段CSV](records/two_level_comparison_v4.csv) |
| P4 / F5 | 未解锁16项终测，仍未生成/读取/消费；F5/p6/official RTA/A_volume/field/channels/短波not_run | [fresh](records/fresh_qualification_v4.json) |
| 无全局因子 | 固定原GEO局部PC＋两层，无global p4 LU/私有CSR/fallback；局部＋R302309536B、Z＋U89391104B | [预算/作用](records/coarse_space_algebra_v4.json) |
| 全过程资源 | 六阶段整树wall1534.00828393s、同时RSS最大1128828928B、own swap0；MPI1/math1、现场核/own lock/16GiB监督 | [run/cost](records/run_index_v4.json) |
| 归因 / 边界 | 未训练NN，G-neural not_run；固定局部步骤上的全局空间未获得严格收敛，不否定全部空间/神经路线 | performance inconclusive，全部shared-workstation |

局部修正可能遗留跨模型误差。本批用有限全局解方向在局部步骤前后消除其可表示残差，代价是额外基存储与S作用。两空间的数学作用通过自检，但在规定的已消费问题上没有达到有效研究分流或1e-10严格精度；训练空间内自检不等于泛化成功。

| 路线 / 已消费RHS | 原A4相对残差 | 固定Schur/RHS | port绝对范数 | port operation-relative | 严格返回 |
| --- | --- | --- | --- | --- | --- |
| TWOLEVEL-OLDPOD-V4 / 0 | 0.99858818727 | 0.999092817197 | 0.0333030546374 | 0.0654894807753 | False |
| TWOLEVEL-OLDPOD-V4 / 10 | 0.949242609663 | 0.971634245187 | 0.000954707150083 | 0.480383202996 | False |
| TWOLEVEL-OLDPOD-V4 / 11 | 0.905073739084 | 0.97721673465 | 0.000949297617596 | 0.235770374702 | False |
| TWOLEVEL-ERROR-V4 / 0 | 0.999863649936 | 0.99961809965 | 0.0256415022841 | 0.0849928945237 | False |
| TWOLEVEL-ERROR-V4 / 10 | 0.937175812499 | 0.957474274981 | 0.000927512266936 | 0.334601298612 | False |
| TWOLEVEL-ERROR-V4 / 11 | 0.901084822725 | 0.963534624076 | 0.000946698188098 | 0.203706802155 | False |

原13.5nm Si、p6/h10对应p4、252cells、80完整通道、A4/A6/MPC和最终验算保持。数据来源/单位/normalization/rank、native与Schur/port分母、实际CPU和邻影响边界、离线/在线/审核/IO/释放费用以及selective merge分组见[中心结果](two_level_global_error_v4.md)。新teacher/NN/GPU未运行；资源未触线，缺邻可比实时阶段指标，不能证明零干扰。原task/review/response_v1–v3和全部历史证据保留；下面V3/V2“当前”均指当时，最新状态以本节为准。

---

# Task042 V3：几何重叠的局部作用，严格全局粗逆仍未合格

| 项目 | 最新实际状态 / 身份 | 证据 |
|---|---|---|
| 状态 | `BOUNDED_STRUCTURAL_GLOBAL_STAGNATION`，有限批次完成，待review，F5 not_run | [原字段重算Gate](records/gate_decisions_v3.json) |
| 授权 | 用户仅授权一个新B0/表示诊断批次，保留旧合同与负结果；继续仅Task042受控共享CPU，不代表F0正式review | [预登记与准确授权](bounded_diagnostic_design_v3.md) |
| Git | NN-Lab canonical linked worktree，`task42_neural_coarse_inverse`；起点d42a7de47bcd966472d58367bab93872d31584e7；base ccd357885f7f9be84efe3be07868cc94f13d93fc | [运行source](records/run_index_v3.json)；最终HEAD另由实际push回报 |
| 旧结果 | 三路线各15个非零失败、仅零通过；16个heldout已消费，全部原始结果保留 | [response_v2](../response_v2.md)、[旧CSV](records/strict_rhs_metrics_v2.csv) |
| 新结果角色 | 重算9个旧失败状态，不重跑旧KSP；一个几何PC仅3个已消费RHS，非fresh资格 | [复用](records/reused_diagnostics_v3.json)、[结构](records/structure_complete_v3.json) |

单元边/面上相邻场分量需要一起修正，旧按连续编号切512行块可能切断这种耦合。本轮把每个单元的全部trace支撑和80端口放进一个小问题，分别解后按共享次数平均；代价是252个局部因子和更多局部回代。它处理完整空间并借用原方程，最终是否可用仍由原A4/port/recovery全部1e-10决定。

## 实际实施矩阵

| 阶段 / 身份 | 完成项 | 未完成边界 |
|---|---|---|
| inherited implementation | 复用原A4/A6接口、p4-only、严格协议、固定Q的精确native最小残差LIN、冻结FP64 NN | 旧F1/teacher/训练不重跑，不把历史证据冒充新数值 |
| consumed artifact diagnosis | physical0/port-only10/mixed11 ×B0/LIN/NN，原Schur/native/port/恢复及PC4快照重新核查 | 旧未保存的restart显式状态不猜补 |
| new structural measurement | R-GEO-CELL80-v3，252个几何支持重叠子域，各192trace+80port；3 RHS各固定256步，逐步独立审核 | no global p4 LU / fallback / private audit CSR；非新大型NN |
| conditional finite-space comparison | not_run | 原physical/mixed仍量级1且末周期停滞，触预登记停止；不扩展teacher/训练 |
| new unconsumed pool | 候选freeze后另选seed420620/整族16项，未生成数组、未求解 | [计划](records/unconsumed_test_plan_v3.json)，不能称fresh终测 |
| F5 / p6 / shortwave / GPU | not_run | 本轮F5未授权；严格逆未资格化；无official物理结果 |

## 冻结模型和容量

| 对象 / 单位 | 实值或预算身份 | 保持的合同 |
|---|---|---|
| 模型 | original13.5nm、1°/phi0/s、同p6/h10对应p4；252cells | 原Si、双Floquet、无PML、quad15、完整80 DtN |
| A4 | trace+port21824、NNZ8184464；CSR SHA150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560 | 每次与qualified F1原方程身份完全一致；p4 FE53084，未改变原A4/A6 |
| 几何PC因子 | 302047392 B，measured NumPy payload（含cell/port） | 构造前预算，maxpatch272<6000、bottom80<2048，全因子<512MiB |
| PC索引/次数/权重/buffer | 3010048 B，derived budget | <512MiB；dense局部临时上界3586048B，无private audit CSR |
| 整树规划与限制 | engineering reserve8GiB；实限制RSS16GiB/warn12GiB，own swap0 | 无cgroup委派，0.5s整树采样停止，包含launcher/compiler/后代；不假称连续内核限额 |

## 原方程实测（dimensionless；绝对port为原数组范数）

| 已消费诊断RHS / index | 旧B0原A4 | 新GEO原A4 | 新GEO port closure | 新GEO port绝对残差 | 末32步Schur降幅 | 严格返回 |
|---|---|---|---|---|---|---|
| physical_PH_b6 / 0 | 0.998654967105 | 0.891957825531 | 0.00773091335604 | 0.187210874612 | 5.70298292157e-06 | False |
| unseen_port_only / 10 | 0.954192801905 | 0.935861877336 | 0.725338952963 | 0.000935056697255 | 1.23982140442e-05 | False |
| unseen_mixed / 11 | 1.000780838 | 0.932010701839 | 0.677921290639 | 0.000951255917368 | 1.24422653291e-07 | False |

新结构带来原native残差的部分下降；完整误差仍为量级1，末周期进展不足以取得严格收敛。端口相对closure的分母随状态参与项范数增长，不能把相对值下降等同于绝对端口错误下降。每步真实数据见[完整历史CSV](records/full_residual_history_v3.csv)，每restart PC作用见[PC probe](records/pc_probes_v3.csv)。

## 复用诊断的结论

| 检查 / 身份 | 结果 | 解释边界 |
|---|---|---|
| KSP vs显式Schur | 四个已存快照及最终状态一致 | reported是绝对范数；Schur/RHS与operation-scaled audit为不同分母 |
| native residual映射 | 复用9状态最大7.44e-15；新每步差见[结构记录](records/structure_complete_v3.json) | 原A4有效RHS含非零port贡献；局部恢复误差及端口映射独立核对 |
| 原port范数 | physical旧B0/LIN/NN绝对0.0353871/0.0420845/0.0399233 | LIN/NN相对closure变小不等于绝对误差变小；没有先改loss权重 |
| CPU记录 | oracle实际33、F4-B0实际45，其余已核FE0；V3见成本表 | v2“全部CPU0”不准确，本轮明确纠正；[manifest/source_state/affinity](records/cpu_provenance_v3.json)，未猜填 |
| 固定Q最优性 | R-LIN已是固定native范数中的精确最小残差修正 | 同Q MLP不能优于该最优解；局部/空间选择/接口响应等学习方向需后续review及空间证据 |

## shared-workstation 完整新数值成本

| 新阶段 | 真实clean source | 现场核 / threads | 整树wall s | 整树RSS峰 B | own swap B |
|---|---|---|---|---|---|
| V3-reuse | `b158c5301e7ff59000b15b335672afdb61c5e5e1` | 12 / 1 | 141.744161531 | 1074900992 | 0 |
| V3-overlap | `7fc3f1434cf4f38f43e5244ebfed3a19d0780a26` | 0 / 1 | 2494.75110155 | 945766400 | 0 |

两阶段监督wall合计2636.49526309s，阶段同时整树RSS最大1074900992B（峰取最大、不相加），swap0。新teacher/训练成本0（not_run），复用固定模型的诊断成本包含在reuse阶段；几何setup/数值PC/每步审核probe分别在[结构记录](records/structure_complete_v3.json)。所有成本shared-workstation；负载、缓存和审核频率不同，性能inconclusive，无无争用加速声明。编辑/Git/审阅时间及总会话RSS未持续计量，辅助测试/后处理另列。

## 停止、测试与下一步

| 项目 | 实际判断 / 身份 | 原因 / 证据 |
|---|---|---|
| 新严格p4返回 | 3项均未资格化，diagnostic only | 原A4/port均未达1e-10，[Gate](records/gate_decisions_v3.json)；不得进入p6 |
| 资源与邻影响 | own swap0，持续PSI未触线、邻身份/CPU推进只读记录 | 无可比实时阶段耗时，不能证明零影响或宣称邻性能不受争用；不改邻任务/锁/监督器 |
| 测试 | 48纯数组/协议，4 FE ABI/支撑/旧默认，4准入/监督通过；最终检查另见测试页 | Ruff/compile/diff、protected history/独立Gate与GitHub实际render在交付收口核验 |
| 未运行 | 新teacher、真实误差128维空间对照、训练、fresh qualification、F5、正式RTA/场/通道、短波、GPU | 同一有界结构未解决全局困难方向；停止扩大，保留旧神经负结果 |
| 后续 | 待review根据真实残差/范数/全局方向决定唯一下一设计 | 不扩大同Q网络、不参数扫描、不merge/master；源码保持显式research opt-in |

## 依赖与合入边界

| 分组 | 改动 / 证据 | 边界 |
|---|---|---|
| research core | bounded geometry overlap、可选逐步observer、原协议/新支撑测试 | 无严格资格，不提升默认；既有B0与普通运行不变 |
| Task042 runner/config | V3两dat/独立预登记、明确opt-in dispatcher及活动样本选核 | 旧V2准入默认不改，不操作共享父cgroup或邻任务 |
| compact evidence/docs | v3残差CSV/JSON、CPU纠正、response/两总账 | 原task/review、response_v1/v2、原raw/v2数字逐字保留 |
| do-not-merge | ignored full arrays、原state、JIT、env、权重与运行日志 | 全在NN-Lab；仅本执行分支push，之后review |

本页是V3最新状态，下面保留V2完整历史，其“当前”只指当时。CPU概括以本页逐run纠正为准。

---

# Task042 第二轮：真实首轮试验，严格粗逆未合格

| 项目 | 实际结果 / 单位与身份 | 证据 |
|---|---|---|
| 终态 | `COARSE_INVERSE_NOT_QUALIFIED`；F1、teacher、oracle、CPU训练和三条F4路线已运行；F5 `not_run` | [独立重算Gate](records/gate_decisions_v2.json) |
| 授权 | 用户允许Task042受控共享运行，覆盖本任务§2.3 heavy禁令和全机独占锁；原task/review保留；不代表F0正式review通过 | [授权原文与适用边界](shared_authorization_v2.md) |
| 工作树 / 分支 | `/home/fenics/Projects/NN-Lab` canonical linked worktree；`task42_neural_coarse_inverse` | [隔离](environment_and_isolation.md) |
| 冻结模型 | original Si矩形块13.5nm、1°/phi0/s、p6/h10、同网格p4、完整80个DtN通道；252cells | [真实F1](records/f1_real_components_v2.json) |
| 真实运行源码 | F1 `cca180f875bd22146f2d30fa4d004e372135dfbb`；teacher `b72448bb2117a0221f041f1b47ac41049750a3c7`；oracle `d9de8ad69bfeeac4860e5187e1738c902a3d808e`；训练 `a221d881bae9405c98e351df2b0b9533582e6d50`；F4 `7216efa605bae155ee383fd716c0fae422448b52` | [逐run索引](records/run_index_v2.json)；后续文档HEAD不替代source |
| 候选无全局p4 LU | B0及线性/NN构建全过程没有global p4 factor；只有有界cell/port、43个<=512行patch和128行bottom | [构造与全部F4](records/run_index_v2.json)、[架构](architecture_and_oracle.md) |
| 资源 | MPI1、现场选核CPU0（48独立物理核，无SMT）；数学/编译/训练线程1；nice10/idle I/O；整树RSS hard16GiB/warning12GiB、own swap0 | [资源与影响](environment_and_isolation.md) |
| GPU / 性能 | 两卡持续邻训练，CPU-only；所有成本标 `shared-workstation`，性能结论 `inconclusive` | [时间与内存](accuracy_performance_memory.md) |

粗层直接分解提前存储一套精确求解辅助表，迭代粗逆则反复纠正误差，节省因子存储但可能难以收敛。本轮用固定传统块方法B0处理全部未知量，再分别增加线性低维修正与小型神经修正，检验它们能否把原方程的误差降到严格门限。真正的p4返回需原A4、端口和恢复全部通过`1e-10`；局部误差或训练loss变小不等于返回合格。

## 完成的数值阶段

| 阶段 | 实际结果 | Gate与限制 |
|---|---|---|
| F0历史 | 独立Git/FE/ML/缓存和33解析协议测试；先前因heavy等待 | [response_v1](../response_v1.md)及无后缀records是保留历史；不再把等待状态当本轮终态 |
| F1真实接口 | 原A4=PH A6P相对差`3.366065072840215e-15`；独立p4 Schur作用差`2.3566154699905024e-16`；非零内部/80端口制造解p4/p6原残差`1.2255722548154e-14 / 2.0935547822786585e-14` | 接口通过；F1 B0七个非零载荷在256步失败，全部保留 |
| F2 teacher | 256train/64validation/64heldout，每batch<=32；384对原方程/端口/内部/恒等式均<=1e-10；最坏native`3.959901353972973e-12` | global LU仅离线teacher；destroy且退出后才运行下一阶段 |
| F2可表达性oracle | ranks16/32/64/128全部通过预登记的诊断标准；rank128 validation误差比`.5138245737888352`、最佳native残差比`.3338841772011458` | 仅表示正信号，非严格逆资格；固定rank128继续，未扫描扩大 |
| F3 R-LIN / R-NN | 同basis/FP64/归一化/B0；NN两hidden64、103040参数、300epochs，validation选51；有载训练19.036s | 独立CPU-only Torch进程；heldout不参与训练或选型 |
| F4严格返回 | 三路线各同16 heldout；每路线只有精确零通过，其余15个均256步后未达1e-10 | 无fallback、无数值调参重跑；端口失败独立记录，内部恢复小不改变判定 |
| F5 / 三次合格计时 | `not_run` | 无F4合格路线，不能嵌入p6；不产生official R/T/A、场或通道数据 |

## 同组严格粗返回结果

| 路线/作用 | 严格通过 | 实际 PH b6 原A4残差 | 同 RHS port closure | 非零 RHS 内部恢复最大 | 整树 wall s | 整树 RSS 峰 |
|---|---|---|---|---|---|---|
| R-B0 | 1/16，仅零 RHS | 0.998655 | 0.465472 | 4.70942e-16 | 486.668 | 0.793 GiB |
| R-LIN | 1/16，仅零 RHS | 0.998262 | 0.239496 | 2.11953e-16 | 1239.273 | 0.962 GiB |
| R-NN | 1/16，仅零 RHS | 0.998456 | 0.179987 | 2.20347e-16 | 1238.082 | 0.937 GiB |

原A4残差是完整原方程的相对不平衡量，port closure是端口方程的独立相对不平衡量；门限均`1e-10`。内部恢复达到很小误差，只证明局部消元有效，全局及端口错误仍接近原载荷量级。全部16项与实值见[逐RHS CSV](records/strict_rhs_metrics_v2.csv)和[准确性分析](accuracy_performance_memory.md)。

去全局因子已由构造及容量记录证明；B0、线性降维和NN均未提供合格粗返回。oracle显示线性子空间能表示部分训练/验证误差，但未使严格迭代成功。神经额外贡献没有正信号，不能把表示改善或去因子的效果算给NN。共享负载、缓存及生命周期不同，不能据此宣布正式20%内存/时间改善或10%神经加速；N=1/10/100合格求解摊销与break-even未定义。

## 全过程数值成本及未运行项

全部正式组件尝试（包含4次实现/环境失败）监督wall合计`8250.064 s`；阶段同时整树RSS最大`2.198 GiB`（取最大，不相加），各树swap0。teacher、oracle、训练和各路线分别计费；安装/测试/预检另列，编辑器/Git/只读审阅的总会话内存与耗时未持续采样。所有数值成本均shared-workstation，未启动Task042 GPU，无本任务VRAM分配，PSS及cgroup峰未采样。

原p6物理载荷求解与全部R/T/A/A_volume、R00_s/p/total、复E/H、场/scaled-curl、80通道复振幅/功率均`not_run`，见[统一p6 CSV](records/full_p6_comparison_v2.csv)。p6仅F1矩阵作用/制造解接口验证，不冒充最终物理解。5/2/0.7nm、h/p/角度/几何泛化、GPU训练和无界参数扫描均未运行。

运行中未观测到触线的持续内存压力或Task042 swap，邻worker/监督器身份保留并有CPU时间推进；已有可读阶段记录缺少可比实时耗时，不能证明绝对零干扰，也不能判断邻任务自然阶段变化是否受影响。详见[环境与影响证据](environment_and_isolation.md)。

## 审阅与合入边界

研究接口、参数化监督器、严格checker、有限数值证据和模型总账可审阅；本轮研究粗逆未合格，不作为production默认。[实际变化与依赖分组](changed_files.md)、[测试](test_summary.md)、[数据与模型身份](dataset_and_model_provenance.md)、[response_v2](../response_v2.md)给出完整入口。保留所有失败与F0记录；只推送本执行分支，之后停止等待ChatGPT review，不合并master。
