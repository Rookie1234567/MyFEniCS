# Task042 V58增量：完整有限基线与成对carrier负结果

| measured模型 | 物理/离散与结果 | 完整成本/资格 |
|---|---|---|
| C6 | λ0.7nm、s7/135、真NOTCH、Z2/p6/828，全部104832FE；独立true1.14919e-11，R/T/A_volume=0.076218704147/0.905665171695/0.018116124158 | 完整N1=904.0364s，树峰7.4326GiB；同离散再现PASS，不是连续准确性 |
| G6/G7 | 同物理κ′=κ+(0,2π/Ly,0)；p6/p7完整原式、828、能量通过 | 890.3844/1770.5065s；散射E/H约3.4%FAIL，峰7.408/14.336GiB |
| target/NN | 无目标PDE/训练，3个有限全局MUMPS numeric，原路径继承 | 原尺寸0.7nm、2TB48h、NN20未资格；没有传统收益归NN |

[完整场/828 mode/240点](task042_neural_coarse_inverse/outcomes/records/scientific_checks_v58.json) · [成本与峰/gap](task042_neural_coarse_inverse/outcomes/records/resource_costs_final_v58.json) · [回应](task042_neural_coarse_inverse/response_v58.md)。全部R/T源自通过原式的实际场；跨p场FAIL独立保留。历史账和正文逐字保留。

---

# Task042 V57 模型增量：p6 新准备与 y 细化

新表仅改变原张量准备，不改变相位有限元/828模式或物理；有限全局MUMPS因子存在，微型求解资格不等于原尺寸可扩展。误差相对旧同离散/空间对照分别列出，未指定高p为真解。

| measured模型 | FE/trace/internal/含端口行 | 独立true/aug/port | R/T/A_volume/能量 | 比较/最终状态 |
|---|---|---|---|---|
| B6: NOTCH λ.7/p6/160cell/828mode | 104832/32832/72000/33660 | 1.5046718057e-11/3.5411949625e-11/1.6543298564e-13 | 0.076218704147/0.9056651717/0.018116124158/1.9717560917e-13 | 同离散再现PASS；无NN/目标资格 |
| Y6: NOTCH λ.7/p6/320cell/828mode | 209664/65664/144000/66492 | 7.0714337697e-11/6.6391365851e-11/1.34950602e-13 | 0.076218704116/0.90566517169/0.018116124179/-1.3648304709e-11 | y增量PASS；跨p散射场3.4% FAIL；无NN/目标资格 |

R00_s/p/total、全部828复模式、完整E/H/curl/240点、资源口径与费用见[专题](task042_neural_coarse_inverse/outcomes/common_weak_phase_preparation_v57.md)及[科学](task042_neural_coarse_inverse/outcomes/records/scientific_checks_v57.json)。shared-workstation，缓存增量不当冷全流程，raw/失败/旧记录保留；不通知邻窗、不merge。以下历史逐字保留。

---

# Task042 V56模型总账增量：0.7nm相位NOTCH有限场

方法保持E=g*u、完整Ckappa与双Floquet/DtN、真实三维缺口。H7仅消费保存场；T6是已冻结x方向的一次独立零初值直接对照。有限直接因子如实登记，解后释放；不是NN或原尺寸可扩展资格。

| 模型/身份 | measured R/T/A_balance/A_volume | 关键准确性结果 |
| --- | --- | --- |
| H7，320hex/p7/(1,1,4)/828 | 0.0762050392206742 / 0.9056592417408208 / 0.01813571903850497 / 0.018135719038380065 | R7→H7 scattered E/H1.974e-5/2.004e-5 PASS；跨p约3.4%FAIL |
| T6，320hex/p6/(2,1,2)/828 | 0.07621855303723198 / 0.905665159001867 / 0.018116287960901034 / 0.01811628796029644 | R6→T6 scattered E/H7.466e-4/7.351e-4 FAIL；能量-6.046e-13 |

H7 R00_s/p/total=0.07618641355480682/3.1826484806399306e-14/0.07618641355483864；T6=0.07621813108109572/3.1666449346672126e-16/0.07621813108109604。全部828复杂振幅和逐mode功率见ignored数组的hash绑定入口，不由功率反推。直接1e-10目标与正式1e-6门分别记录，不能只以一项残差或能量授资格。

[全部原式/完整场与费用](task042_neural_coarse_inverse/outcomes/saved_field_closure_target_bridge_v56.md) · [源/输入/数组索引](task042_neural_coarse_inverse/outcomes/records/delivery_index_v56.json)。原尺寸/2TB48h/NN20未资格，merge未批准。以下历史逐字保留。

---

# Task042 V55模型增量

| 模型 | 完整原方程 | 原场/功率资格 | 资源/成本 |
| --- | --- | --- | --- |
| 旧R6/R7/C，独立补审 | PASS，true约1.19e-11/1.93e-11/1.93e-11 | 旧有限模式结论保留，跨p约3.413%FAIL | factor/solve0；补审收费 |
| 0.7nm NOTCH Z4/p7/828，320hex | actor及保存checker true4.2039e-11 | R00_s=0.07618641355、R00_p=3.18e-14、R00_total=0.07618641355；R_total=0.07620503922/T_total=0.90565924174/A_balance=0.01813571904；体吸收/能量/场增量not_run | 89756凝聚行，采样整树22.833GiB；完整因子存在后释放 |
| 条件T6 x2/z2/p6/828 | not_run | not_run，时间不足非数值FAIL | 容量通过，完整准备预算拒绝 |

[完整532/828父与新828库存、恢复/费用](task042_neural_coarse_inverse/outcomes/spatial_resolution_audit_v55.md)。未授原尺寸/连续收敛/2TB48h/NN20，传统确定性准备/凝聚不算NN训练。以下旧模型总账不回写。

## Task042 V54 有限准确性库存

| 模型 | 原actor原方程 | 完整分辨／交付资格 |
| --- | --- | --- |
| Z2/p7/828，160hex/46076行 | true1.92427e-11 | 532→828增量FAIL；新独立VERIFY未运行 |
| Z2/p6/828，160hex/33660行 | true1.18713e-11 | 532→828增量PASS；新独立VERIFY未运行 |
| Z2/p7/1188，160hex/46436行 | true1.92314e-11 | 828→1188增量PASS；新独立VERIFY未运行 |

全部存在有限exact直接因子，非生产factor-free；同828跨p FAIL，NN训练0/NN20未资格。成本/峰与hash见[专题](task042_neural_coarse_inverse/outcomes/p_order_dtn_separation_v54.md)。历史原文保留。

## Task042 V53：相位 hp 完整解与前向准确性

结论 `HP_ACCURACY_NOT_CLOSED`；本轮无NN训练，完整方程与场增量分别验收。

| 角色 | 模型 | 独立 FE | trace | 内部 | 含端口行 | CSR存储NNZ | 状态 | 原 true/native | 方程门 | dat 冷链下界/s | 采样树峰/GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 320hex/p6 | 208512 | 64512 | 144000 | 65044 | 57830216 | COMPLETED | 2.497271538e-11 | True | 4543.819512 | 11.82277679 |
| B | 160hex/p7 | 166208 | 45248 | 120960 | 45780 | 55977992 | COMPLETED | 1.908293633e-11 | True | 10396.57293 | 13.44511795 |

| 比较 | total E | total H/curl | scattered E | scattered H/curl | selected 最坏 | 复通道 | 逐 mode 功率最大差 | RTA/体吸收最大增量 | 完整增量门 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H_A | 9.688497585e-05 | 0.0001008670976 | 0.0006744466865 | 0.0007021770088 | 0.0005873418678 | 6.4374625e-05 | 4.153222769e-07 | 3.632744375e-07 | False |
| A_B | 0.004961750278 | 0.004957575642 | 0.03449623102 | 0.03446770769 | 0.02745212901 | 0.0009438804165 | 3.267453909e-05 | 1.977228261e-05 | False |
| P_B | 0.004961753259 | 0.004957579357 | 0.03449625175 | 0.03446773352 | 0.02745091748 | 0.0009440884403 | 3.266549595e-05 | 1.97720082e-05 | False |
| P_A | 4.707929018e-06 | 5.558465295e-06 | 3.277336964e-05 | 3.869474415e-05 | 4.773034799e-05 | 6.573700128e-06 | 1.977922481e-08 | 6.649845119e-10 | True |
[回应](task042_neural_coarse_inverse/response_v53.md)；[完整物理/容量/费用](task042_neural_coarse_inverse/outcomes/phase_hp_completion_v53.md)。

## Task042 V52：固定相位NOTCH p/h完整分辨对照

结论 `FLAT_PASS_NOTCH_NOT_QUALIFIED`；完整方程与物理场分别验收，无NN训练。

| 角色 | 模型 | 凝聚行含端口 | 状态 | 原 true/native | 增广 | 端口 | dat 冷链下界/s | 采样树峰/GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H | 320hex/p5 | 44532 | COMPLETED | 9.41863913e-12 | 1.04411663e-11 | 1.25726032e-14 | 2286.97282 | 5.72674179 |
| P | 160hex/p6 | 33364 | COMPLETED | 1.15504849e-11 | 2.59656282e-11 | 2.42913714e-13 | 5904.75728 | 6.98644257 |
| HP | 320hex/p6 | 65044 | CAPACITY_BLOCKED | not_run | not_run | not_run | 4746.49044 | 6.70747757 |

| 比较 | total E | total H/curl | scattered E | scattered H/curl | selected 最坏 | 参考面复通道 | 逐 mode 功率最大差 | 完整增量门 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H_P | 9.68962309e-05 | 0.000100919081 | 0.000674525015 | 0.000702538865 | 0.000586944796 | 6.44169784e-05 | 4.06279138e-07 | False |
| B0_H | 1.83822935e-05 | 1.98752705e-05 | 0.000127963241 | 0.000138358066 | 0.000152955333 | 2.79515602e-05 | 5.01556003e-08 | False |
| B0_P | 9.83037936e-05 | 0.000102462232 | 0.0006843235 | 0.000713281367 | 0.00060656272 | 6.88730217e-05 | 4.37547584e-07 | False |

[response_v52](task042_neural_coarse_inverse/response_v52.md)；[完整物理/费用](task042_neural_coarse_inverse/outcomes/phase_notch_hp_accuracy_v52.md)。

# Task042 V51最新交付：平界面准确，三维缺口精度仍未资格

把已知的快速横向相位解析保留，让有限元计算包络，再恢复完整电场和磁场。它改善场的表示，仍使用原Maxwell方程和完整532模式；这是确定性离散，本批没有NN训练。FLAT解析场通过，NOTCH的p/h场差仍超过1e-4，不能用小残差或守恒代替准确性。

| 实际完整物理解 | 原true/native残差，门1e-6 | 物理准确性 | dat启动下界s／采样整树峰GiB |
|---|---|---|---|
| 80hex/p4 FLAT | 2.88117e-12 | 解析E/H为3.85798e-8／4.63574e-8，PASS | 294.248354／1.032608 |
| 80hex/p4 NOTCH | 2.93150e-12 | p4/p5 scattered E/H差9.61667e-4／9.41540e-4，FAIL | 118.554778／1.007263 |
| 80hex/p5 NOTCH | 4.77771e-12 | p5/Z2 scattered E/H差8.53183e-4／8.53072e-4，FAIL | 625.778514＋补审142.573980／2.245213 |
| 160hex/p5 NOTCH Z2 | 4.67476e-12 | 复通道差1.51246e-4，FAIL；功率差通过 | 841.587038／3.496330 |

四次完整solve及冻结后的唯一独立VERIFY完成，全部恢复/slave门通过。N5后处理失败只补审，原返回向量和失败费用保留。F5/OC未运行；有限全局p4/p5直接因子存在，保存向量后释放，不重开生产p4强逆。所有成本为shared-workstation下界，OS/JIT未清，正式加速INCONCLUSIVE；原尺寸0.7nm、2TB/48h和NN20%未资格。唯一下一建议是新合同下同物理p5/Z4完整NOTCH对照，44532凝聚行超本批35000门，不自动启动。

[response_v51](task042_neural_coarse_inverse/response_v51.md)；[全物理/RTA/R00与费用](task042_neural_coarse_inverse/outcomes/phase_explicit_full3d_accuracy_v51.md)；[资源](task042_neural_coarse_inverse/outcomes/records/resource_costs_final_v51.json)；[就绪/容量边界](task042_neural_coarse_inverse/outcomes/records/next_scale_capacity_v51.json)。

原50×25nm目标和AUTO32060未运行；固定532有限问题未证明模式截断或连续收敛。R/T/A/体吸收、逐mode功率和恢复通过，但NOTCH场与复振幅仍FAIL；不追溯改变V50或更早负结果。与隔壁5nm learned-wave/greedy分工明确，未启动或通知其窗口。本分支提交推送后暂停。

以下历史逐字保留。

<!-- V51-LATEST-END -->

# Task042 V50最新交付：完整积分闭合，当前有限空间准确性不足

先检验完整物理积分，再用解析平界面判定有限元空间是否足以表示真实波。本轮完成两个新完整p5求解、全532端口、原方程/恢复与完整场/功率审核，保留准确性负结果。六Gram通过是传统准备控制，不是神经增量；不会自动追加纯FE轮次或旧NN训练。

| 工作 | 实测／门 | 状态 |
|---|---|---|
| 全532 q47/q63 | p4/p5最大差7.73e−14／7.72e−14，门1e−11 | 完整积分通过；旧q和截断归因单列 |
| FLAT p5完整场 | 原rho5.66631e−12；E/H误差1.012702／1.012696，门1e−4 | 方程通过，物理准确性FAIL |
| 四固定空间 | X2/p6最佳H/curl插值误差9.50015e−4；derived下界9.37460e−4 | 全部未准入，三个条件solve未运行 |
| NOTCH p5六Gram传统控制 | 原rho7.02190e−12；全部真实体类／方向约1e−15 | 传统准备有限资格，非NN收益 |
| 全费用／目标 | 失败、资格、两solve、独立审核均收费；无训练 | 准确性anchor／原尺寸／2TB48h／NN20未资格 |

[两完整模型](task042_neural_coarse_inverse/outcomes/records/complete_accuracy_checks_v50.json) · [结果与全部532通道](task042_neural_coarse_inverse/outcomes/complete_physics_accuracy_cost_v50.md) · [完整费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_final_v50.json)

唯一下一对象是显式保留入射/Bloch相位的完整物理离散及神经系数生成；需新的准确性与全费用合同，本批不自动实施。旧task/review/response/raw逐字保持，以下历史不覆盖当前交付。

<!-- V50-LATEST-END -->

# Task042 V49最新交付：完整有限散射链通过，p增量精度未收敛

从真实物理dat到完整三维Maxwell/DtN、内部恢复、E/H/curl、532复端口和功率的执行链已经完成。REGULAR及真实两cell NOTCH的p4直接/全四q结构引擎各自原方程与同离散观测量通过；NOTCH唯一p5对照的总E/H差2.95319/2.81472，不能宣称离散精度或原尺寸资格。本轮未训练NN，准备/凝聚成本是主要瓶颈；尾部逆/初始化即使免费也不足20%完整时间。

| 完成项 | 实际结果 | 边界 |
|---|---|---|
| p4两个完整物理case | 原rho 9.11e-13/8.04e-12；完整532端口、1/3外步 | 同p4完整2/2，通过不等于连续真解 |
| NOTCH p5 | 自身原rho2.58e-12；总E/curl与p4差2.95/2.81 | 离散精度未收敛，未追加p/mesh扫描 |
| 完整数值冷成本 | 直接118.673/71.548s；结构137.522/138.236s | shared-workstation、OS/JIT cache不等价，早期启动unknown |
| 原尺寸0.7nm/2TB48h/NN20 | 有限完整基线就绪，神经训练0 | 三项均未资格；旧路线关闭与负结果保持 |

[完整五条物理路线](task042_neural_coarse_inverse/outcomes/records/complete_physical_results_v49.json) · [p4/p5原式与精度](task042_neural_coarse_inverse/outcomes/complete_scattering_engine_anchor_v49.md) · [完整费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_final_v49.json)

普通数值默认不变。全部有限全局直接/四q因子如实登记；新数值核在src/solvers，八个one-run dat已真实validate并执行。结束后closed、清场、push本分支，原队列一次交回并停止；不得依据此导航重开closed窗口。以下完整历史逐字保留。

<!-- V49-LATEST-END -->

# Task042 V48最新交付：无损存储通过，冻结神经压缩额外收益为负

保留所有有限元系数位，用因果预测+逐位XOR保存预测错误，真正按需恢复一条历史trace做内积/向量更新。本轮比较8条强传统控制和同特征LIN/NN，不是新PDE。

| 对象 | 实测/限值 | 状态 |
|---|---|---|
| LIN/NN真训练 | 各256更新，26/1538实参数；FD门1e-6通过；val码流均选0 | 真训练，未取得训练后的码流改善 |
| heldout8×10路线 | 全trace/full canonical/两遍consumer位相同 | 有限无损消费资格 |
| 公开迁移16×10路线 | 完整位一致，不读取旧标签 | 迁移诊断，不是fresh PDE盲测 |
| NN完整bank byte规划 | heldout2.02713×RAW、迁移1.53632×RAW，门≤.8 | FAIL；不做三次计时、不续训 |
| shared-workstation一次consumer | NN .276324/.640264s，RAW .002942/.004590s | 保留成本负结果，不声称无争用性能 |
| 原尺寸0.7nm/2TB48h/NN20 | 新FE/求解/原作用0，旧资格不变 | 未资格 |

[response](task042_neural_coarse_inverse/response_v48.md) · [完整结果](task042_neural_coarse_inverse/outcomes/lossless_vector_storage_v48.md) · [最终资源/成本](task042_neural_coarse_inverse/outcomes/records/resource_costs_final_v48.json) · [独立checker](task042_neural_coarse_inverse/outcomes/records/lossless_checker_v48.json) · [必要条件](task042_neural_coarse_inverse/outcomes/records/conditional_cost_bounds_v48.json)。codecs/模型/码流为research-only，旧失败保留。以下历史逐字保留。

<!-- V48-LATEST-END -->

# Task042 V47最新交付：固定坐标50% trace删系数见证失败

先检验知道答案时能否删去一半边/面系数，避免训练网络突破同一坐标下界。完整内部保留、原方程不变；新16/4/8振荡制造数据，前20问题主门0/20，条件NN/仿射训练与heldout消费未运行。原尺寸0.7nm/2TB48h/NN20未资格，旧负结果/closed不改。

| 对象 / measured见证 | η门1e-4 | trace门1e-4 | 原ρ门1e-6 | 结果／费用边界 |
|---|---|---|---|---|
| 50% / 6912 trace | .000647155.. .0226250，0/20 | .00129242.. .0426650，0/20 | .0665621.. .732182，0/20 | 固定坐标删系数关闭，SUBSPACE_WITNESS_ONLY |
| 80% / 11059 trace，诊断 | 2/20 | 2/20 | 0/20 | 不替代主门，不是前向求解 |
| 完整矩/原桥/独立checker | 两见证约5e-16 | 全部内部28800/问题 | 40保存见证身份通过 | 146原作用/峰1127350272B/ownswap0；无训练收益 |

背景/方法/全部样本/[费用与上下界](task042_neural_coarse_inverse/outcomes/records/resource_costs_v47.json)见[response](task042_neural_coarse_inverse/response_v47.md)和[完整结果](task042_neural_coarse_inverse/outcomes/trace_subspace_selection_v47.md)。目标half trace仅省完整向量payload15.3%，完整峰/solver/冷费用unknown；不能授NN20。唯一下一建议：关闭本次删系数，集中审阅保留完整矩信息的编码及同容量线性控制的新神经合同，不自动实施。

以下历史逐字保留。

<!-- V47-LATEST-END -->

# Task042 V46最新交付：同一成本消费与引擎拒绝

先确认算对，再比较从准备到审核的一次完整费用；unknown不能当0。本轮只修费用/身份决策，没有新PDE、模型推理或训练。原尺寸0.7nm完整解、2TB/48h和NN20仍未资格。

| 对象 | 新决定／事实 | 证据 |
|---|---|---|
| R0/CL44/LIN-H/NN-L/NN-H | 历史完整均0/8，性能准入拒绝；NN-L/H选零修正 | [证据](task042_neural_coarse_inverse/response_v46.md) |
| 冷N=1选择器 | 实际timing接统一九阶段费用；CL44继承493.748953s准备/训练，不重复旧在线；unknown→拒绝 | [证据](task042_neural_coarse_inverse/outcomes/records/cold_n1_cost_contract_v46.json) |
| dot快照7f03a48d | 仅7/135缩尺q0组件，不是完整同物理引擎 | [证据](task042_neural_coarse_inverse/outcomes/records/engine_matching_v46.json) |
| 原尺寸关键路径 | 完整引擎/正确性/冷成本→不同学习对象必要机会→fresh资格，依赖关闭 | [证据](task042_neural_coarse_inverse/outcomes/records/critical_path_v46.json) |
| 下一步 | 仅有实质完整引擎或独立新学习对象/可核算20%机会才另立合同；不安排纯FE演示/同A微调 | [证据](task042_neural_coarse_inverse/outcomes/neural_deployment_decision_v46.md) |

以下历史全文逐字保留。

<!-- V46-LATEST-END -->

# Task042 V45最新交付：完整矩分层NN与配对终测

让实体保留全部实虚矩并传递远处残差信息；同信息线性和局部消融辨别贡献。三模型各128真实更新，validation拒绝非零NN head，完整资格与原尺寸/NN20仍未达成。

| 路线 | ρ门 | η门 | 完整资格 | ρ范围，门1e-6 | η范围，门1e-4 | 总Arnoldi | 含共同前段的8项求解s |
|---|---|---|---|---|---|---|---|
| R0 | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 258.393582 |
| CL44 | 8/8 | 0/8 | 0/8 | 2.581975482e-08..3.78853399e-08 | 0.0003508615011..0.0005405081646 | 128..128 | 263.432889 |
| LIN-H | 8/8 | 0/8 | 0/8 | 2.61547387e-08..3.861573114e-08 | 0.0003484809644..0.0005296573543 | 128..128 | 260.056874 |
| NN-L | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 250.222528 |
| NN-H | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 260.343939 |

背景：旧两跳宽32候选已关闭，本次新增完整12/120/900实通道和分层内容。原A／材料／RHS规范／128步与最终门保持，NN不替代最终有限元审核。机制和新梯度成立不等于求解能力；NN-L/H采用零修正，LIN-H小误差改善不能冒充20%神经增量。64hex/p6/q15无完整DtN，E/H/全通道/功率NOT_RUN。

唯一下一建议：把本轮冻结输入／完整系数／原残差／伴随／全部费用接口交给同物理合格传统引擎做一次匹配，先判断难误差与冷N=1是否存在20%空间；不再在同一A上换seed、加层、调tau或延长128步。本批不重建传统引擎、不复制dot求解器。

[response_v45](task042_neural_coarse_inverse/response_v45.md) · [完整结果](task042_neural_coarse_inverse/outcomes/full_moment_hierarchy_v45.md) · [费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v45.json) · [完整库存](task042_neural_coarse_inverse/outcomes/records/array_inventory_v45.json)。研究-only、无merge批准，以下全部历史逐字保留。

<!-- V45-LATEST-END -->

# Task042 V44最新交付：后期误差学习与五路线终测

四模型各128次训练，封存heldout在全部求解冻结后独立审核。ρ与完整η同时过门才合格，完整原尺寸与NN20未资格。

| 路线 | ρ门 | η门 | 完整资格 | ρ范围 | η范围 | 总Arnoldi | 8项求解s |
|---|---|---|---|---|---|---|---|
| R0 | 8/8 | 0/8 | 0/8 | 2.512542745e-08..3.98664504e-08 | 0.0003359336327..0.0005311309217 | 128..128 | 244.588831 |
| NN-R | 8/8 | 0/8 | 0/8 | 2.490087855e-08..4.2150641e-08 | 0.0003674131818..0.0005308487408 | 128..128 | 247.686011 |
| NN-E | 8/8 | 0/8 | 0/8 | 2.651771046e-08..4.215432378e-08 | 0.0003643483429..0.0005497722015 | 128..128 | 245.305868 |
| RL-E | 8/8 | 0/8 | 0/8 | 2.651087888e-08..4.21524334e-08 | 0.0003643298497..0.0005496776936 | 128..128 | 246.041111 |
| CL-E | 8/8 | 0/8 | 0/8 | 2.610389954e-08..4.146630952e-08 | 0.0003642299582..0.000517074058 | 128..128 | 207.051734 |

共同身份：64hex/p6/q15/3tag/0.7nm、45000native/42624独立/2376slave；NN-R/NN-E/RL-E70144实参数、CL-E74240，各128更新。原A无完整DtN，旧恢复FAIL与原尺寸E/H/32060通道/功率/2TB48h未资格保留。数值费用共享工作站，完整冷成本unknown、NN20 NOT_DEMONSTRATED。

[response](task042_neural_coarse_inverse/response_v44.md) · [完整结果](task042_neural_coarse_inverse/outcomes/late_error_learning_v44.md) · [全费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v44.json)

唯一下一建议：在新合同中只比较一种包含远距离残差信息、并扩大单元内部输出表达能力的可扩展神经表示及同信息线性控制；先以本轮封存误差诊断确定所需容量，不复用它们训练。本批不实现该网络，不再为同一两跳宽32表示追加初始化、训练步或GMRES步数。

以下完整历史逐字保留。

<!-- V44-LATEST-END -->

# Task042 V43：真实神经残差训练及完整对照完成，严格代数资格仍为负

网络根据相邻实体残差输出全部有限元修正，再用相同传统迭代清理；训练／推理／清理和原矩阵都计成本。本轮实际训练encoder、message和decoder，并对8未见右端比较NN、同邻域线性及零初值。不能只用训练loss下降宣称突破。

| 固定问题／指标 | measured结果和原因 | 边界 |
|---|---|---|
| 64hex/p6/q15/3tag/0.7nm | 45000native，42624独立，2376slave；原A/Aᴴ配对通过 | A无完整DtN，有限代数，不是原尺寸模型 |
| NN / LIN | 70144 / 74240实参数，两轮邻域消息宽32，各128更新，val选128 | 全系数直接loss，旧恢复FAIL保持；不是纯FE阶段 |
| R0 / R-LIN / R-NN | 完整各0/8；ρ门8/4/8，但η范围0.00627..0.01678 / 0.03404..0.45859 / 0.05712..0.22704，均>1e-4 | NN没有相同正确性合格基线，NN20 NOT_DEMONSTRATED |
| 同时树峰／swap／作用 | 2696056832B / 0；4090 A/Aᴴ，21 B；新mesh/JIT/LU/QR/target0 | 采样树峰非连续cgroup；有限CSR和AH副本计入 |
| 完整原PDE／E/H/RTA/Avolume／2TB48h | NOT_RUN / NOT_QUALIFIED | 不把梯度或有限制造rhs当完整物理资格 |

[Review V40](task042_neural_coarse_inverse/review_report_v40.md) · [response](task042_neural_coarse_inverse/response_v43.md) · [完整结果](task042_neural_coarse_inverse/outcomes/neighborhood_residual_correction_v43.md) · [独立checker](task042_neural_coarse_inverse/outcomes/records/neural_heldout_checker_v43.json) · [费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v43.json) · [source](task042_neural_coarse_inverse/outcomes/records/run_index_v43.json)。唯一下一建议：只比较同一架构的零输出层初始化与本轮初始化，其他数据生成族、seed、128更新及清理规则不变；检验训练是否主要花在撤销有害初值。该对照需未来review授权，本轮不实施；即使改善，残差与完整系数误差仍须同时过门，不能因此授NN20%。

以下历史全文逐字保留。

<!-- V43-LATEST-END -->

# Task042 V42：有限原作用可信，恢复门未过；保持神经突破主线

Task042的研究目的仍是神经网络突破：在相同原有限元正确性下，相对最佳合格非神经方法，完整耗时或同时峰内存至少改善20%，另一项合规。本轮没有神经训练或推理；分布式体积、伴随和残差接口用于以后核验神经场，不能记作神经贡献。用户本轮再次明确这一主线，下一轮建议必须回到神经接入与非神经对照，不能把接口准备无限延长为独立纯FE研究。

| 对象／单位／身份 | measured结果及原因 | 资格边界 |
|---|---|---|
| 同连接64hex／p6／三tag／MPI1/2/4 | 原CSR全向量正向／伴随可信；独立内部平衡max7.5914669173601817e-10>1e-10，99/192 FAIL | 作用可用，完整恢复未资格化 |
| 原V40八hex／12port／新MPI2/4 | 实际消费及原作用通过；独立CSR内部1.0104485117650333e-10>1e-10 | 不四舍五入过门，旧证据保持 |
| 原尺寸530856hex／32060port | 类重算270raw／858oriented／私有306/900一致；完整动作NOT_RUN | 有限门失败、backend未实现及资源／预测缺口保留 |
| 因子／峰／swap | 6新450局部LU；旧B4类只读；CSR未分解；树采样峰3729522688B／0 | 无global p4因子，非factor-free；无新求解或NN训练 |
| 完整PDE／场功率／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 传统接口不算神经收益 |

[Review V39](task042_neural_coarse_inverse/review_report_v39.md) · [response](task042_neural_coarse_inverse/response_v42.md) · [结果](task042_neural_coarse_inverse/outcomes/distributed_volume_recovery_v42.md) · [checker](task042_neural_coarse_inverse/outcomes/records/component_checker_v42.json) · [费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v42.json) · [就绪](task042_neural_coarse_inverse/outcomes/records/integration_readiness_v42.json)。唯一下一建议（只交审阅，不自动实施）：在已可信的有限原作用／伴随接口上，将一个冻结神经trace表示接到canonical实体及原残差，核验真实伴随梯度并做同正确性非神经对照；把尚未通过的非零内部恢复门作为显式限制，未闭合前不授完整求解或20%收益。不得用目标参考场监督拟合，不能把传统缓存收益归神经。

以下历史全文逐字保留。

<!-- V42-LATEST-END -->

# Task042 V41：原尺寸实际拓扑与owner边界接口完成

本轮将全部trace行号复制改为按完整边／面实体向实际owner通信，保留原相位、方向和全部矩。真实MPI桥与原尺寸低阶拓扑已经完成，完整三维前向解尚未完成。

| 对象／单位／身份 | measured结果及原因 | 资格边界 |
|---|---|---|
| 64hex／p6／三tag／真实MPI1/2/4 | 全向量max1.48144941502e-15<1e-10；slave精确0，跨rank周期角点 | 有限编号/MPC/owner资格，非h≤0.7精度 |
| 原尺寸MPI2低阶geometry/topology | 530856hex、555814顶点、1642171边、1617214面；270raw／858oriented | 不建全目标p6空间／345771066向量／A；方向补审62种通过 |
| 完整边界owner／新进程消费 | 378432行、上下各2628面、32060port，max1.39302196607e-15 | 路由和MPI2消费资格；匹配分布式volume未连接 |
| 峰／ownswap／来源 | 1895116800B／0，shared-workstation，source81c776fddcd173cf7db898f20f3068eb7cf7ae2b | 采样树峰非连续cgroup峰；无新form/LU/QR/Krylov/训练 |
| 完整PDE／场／功率／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 无official结果；传统接口优化非神经收益 |

V40计数纠正为129逻辑=120实际+9alias，旧138不改写。失败接线、错误伴随输入和全部费用保留；只复用可信packet补受影响阶段。容量使用实际class/rank库存；PC/K、目标单步和完整恢复/审核仍unknown。[结果](task042_neural_coarse_inverse/outcomes/native_entity_owner_topology_v41.md) · [response](task042_neural_coarse_inverse/response_v41.md) · [checker](task042_neural_coarse_inverse/outcomes/records/component_checker_v41.json) · [费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v41.json) · [就绪](task042_neural_coarse_inverse/outcomes/records/integration_readiness_v41.json)。

唯一下一建议：连接匹配同物理分布式体积引擎，先验证有限非零RHS及原作用消费，再申请完整目标容量/求解Gate，不再独立边界测速。以下历史全文保留。

<!-- V41-LATEST-END -->

# Task042 V40：真实有限体积与非零载荷恢复闭环通过

先保存每个昂贵阶段，再将原体积、完整有限端口与内部非零载荷连接并独立审核。这样接线错误只补未完成阶段。本轮通过有限接口，不是完整PDE解，也没有神经训练。

| 对象／数据身份 | 实际结果及原因 | 资格边界 |
|---|---|---|
| .7nm／8hex xy_corner／p6／q30-q15-q17／12冻结mode | 原数组66/66；最大内部平衡4.06091e-12<1e-10；两tag求积max4.13409e-15 | COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES，真实MPI1 |
| 昂贵checkpoint与真实消费 | 4类882原张量/450局部LU，小CSR/q/RHS/恢复11包；新进程volume+恢复PASS | 4LU/cache56274336B，无global p4逆；不是factor-free |
| 初次失败及继续 | Basix complex接线失败860.3629s，随后只补求积34.7358s | mesh/JIT/LU/CSR未重建；pre04存储停止及全部费用保留 |
| 同时整树峰／ownswap／预算 | 1265823744B／0；native934.331523s<2400 | 0.5s采样、shared-workstation，全费用见账 |
| 原尺寸容量 | raw精确几何/tag270键；E单实体workspace86880B | native方向/owner/MPC未知，单向量5.53GB、逐cell缓存4.96TB不可直接部署 |
| 完整PDE／E/H/RTA/2TB48h/NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 不把接口或传统存储优化称神经收益 |

[Review V37](task042_neural_coarse_inverse/review_report_v37.md) · [response](task042_neural_coarse_inverse/response_v40.md) · [结果](task042_neural_coarse_inverse/outcomes/native_volume_affine_recovery_v40.md) · [checker](task042_neural_coarse_inverse/outcomes/records/component_checker_v40.json) · [费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v40.json) · [容量](task042_neural_coarse_inverse/outcomes/records/original_size_integration_capacity_v40.json)

唯一下一建议：资格化同物理全体积引擎的native owner/MPC映射与精确class缓存容量，以本轮非零RHS包作接口anchor；本轮不自动启动。以下旧历史正文逐字保留。

<!-- V40-LATEST-END -->

# Task042 V39：原生边界接口资格通过，体积组合保留真实失败

通过稀疏实体映射将体积系数取到边界，并按共轭周期相位把力加回；新增的是接线，不是神经训练。真实体积组合已运行并失败，接线修复通过小回归，但剩余慢oracle额度不足以完整重放，非零内部RHS恢复和完整解仍未资格化。

| 对象／方法 | 实际值及原因 | 分类／证据 |
|---|---|---|
| .7nm／p6／q30／四类20hex／12冻结mode | native最大1.36230187281e-12<1e-10；全32060输出链接最大1.51058119943e-13 | NATIVE_BOUNDARY_ADAPTER_QUALIFIED_ON_WITNESSES，MPI1 |
| 原内部零迹／计算存储 | 六面完整882基，切向max4.89818e-13；20对MPC存储／展开副本 | 原浮点C/D保留，不硬设0；旧未归一化L2 6.42361e-12 FAIL保留 |
| 有限体积组合／非零载荷恢复 | 912.591881218s后carrier含slave而失败；4内部LU class，修复后完整重放预测超235.030s余量 | SETUP_EXECUTED_NOT_QUALIFIED／恢复NOT_RUN_AFTER_FAILURE |
| 消费接口 | extract/scatter/forward/adjoint/modal/implicit Hp，demo差≤1.35886e-12 | 明确零volume callback，非物理解 |
| 同时整树峰／ownswap／费用 | 2073407488B／0；component992.281548s，native972.877846s | 0.5s采样、shared-workstation；全部费用另列 |
| 原尺寸全PDE／E/H／R/T/A/A_volume／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 本轮没有训练，不归神经收益，不授原尺寸资格 |

[Review V36](task042_neural_coarse_inverse/review_report_v36.md) · [response](task042_neural_coarse_inverse/response_v39.md) · [结果](task042_neural_coarse_inverse/outcomes/native_boundary_volume_integration_v39.md) · [run/source](task042_neural_coarse_inverse/outcomes/records/run_index_v39.json) · [原始证据](task042_neural_coarse_inverse/outcomes/records/raw_evidence_index_v39.json) · [成本](task042_neural_coarse_inverse/outcomes/records/resource_costs_v39.json) · [集成就绪](task042_neural_coarse_inverse/outcomes/records/integration_readiness_v39.json)。唯一下一建议：匹配体积引擎，补有限非零内部／port RHS恢复及独立残差恒等式，再作原尺寸容量准入；结束独立边界测速轮次。以下历史正文逐字保留。

<!-- V39-LATEST-END -->

# Task042 V38：全原尺寸边界作用通过，完整体积解仍未资格化

将相同有限元边界积分按x/y方向收缩并共享几何，减少逐通道重算，代价是局部坐标桥及7.28MiB缓存。它只加速端口组件，不改变体积三维Maxwell，也不是神经训练增量。

| 对象／数据身份 | measured或not_run结果 | 边界 |
|---|---|---|
| .7nm／50×25nm／上下2628面／p6／32060端口 | 四类native q30完整882基，最差1.48686e-12；两一般复输入全量PASS | q30/MPI1 TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q |
| 逐通道q30/q60／独立12mode全表面 | max1.60663e-12／2.39972e-14<1e-10 | 未删通道／校幅相；不证明h/p收敛 |
| 完整q30首次forward／adjoint | 0.077134419／0.076004680s；cache7628096B | setup／失败／IO与旧费用全部另记；shared-workstation |
| 同时整树采样峰／own swap | 1047965696B／0 | 0.5s，不是连续cgroup硬峰；MPI1/数学1，无GPU |
| 原方程／E/H/curl／R/T/A/A_volume | NOT_RUN；全目标native row adapter与solver未合格 | 仅边界组件，无新official结果 |
| 2TB／48h／NN20% | NOT_QUALIFIED／NOT_DEMONSTRATED | 历史成本及unknown保留；旧q15FAIL/native q60未运行保持 |

[response](task042_neural_coarse_inverse/response_v38.md) · [结果](task042_neural_coarse_inverse/outcomes/directional_boundary_structure_v38.md) · [checker](task042_neural_coarse_inverse/outcomes/records/component_checker_v38.json)

唯一下一建议：匹配体积solver的native边界row抽取／散布及内部恢复资格；本批不实施、不merge。完整旧正文逐字保留。

<!-- V38-LATEST-END -->

# Task042 V37模型总账：普通p6面片分块接口通过，q15不合格，全量边界未获资格

端口把边界场分解为不同衍射方向。新接口将单个方向的边界数据继续拆成面片：第一遍累加一个复振幅，第二遍重放面片并累加牵引。这样不必常驻整张单方向系数表，代价是两次遍历与生成；它不改变三维体积方程，也不是神经收益。

| 对象／数据身份 | measured、derived或not_run结果 | 门限／边界及证据 |
|---|---|---|
| 原50×25nm周期、z=−10..130nm、.7nm、p6容量情景 | 32060 ordered端口；530856 cells／345771066 storage，均复用V36 | 未建目标体积mesh／完整编号或解PDE |
| p6真实普通面片，4hex、882局部basis、12预登记mode、MPI1 | q15→q30最大相对差 1.32594720615e-05 | 高于1e-10，q15未获此见证资格 |
| 未裁剪native q30 vs Basix q60 | 最大相对差 4.69243170483e-13 | 低于1e-10；原生q60、max普通／周期缝／角点未完成，不授全量边界资格 |
| q30分块正向／伴随／复振幅 | 2.79307870108e-13／2.61645760695e-13／1.59542409236e-13 | H独立重算差0；单位功率绝对差7.1054e-15；仅P6_TILE_INTERFACE_QUALIFIED_ON_PARTIAL_WITNESS |
| 数值tile／creator工作区 | 42336B／q30上界22127616B、q60上界81821376B | 缓存与生成临时对象分开；真实全量support／周期扩张上界unknown |
| shared-workstation费用／峰 | 计费 474.862115805s；同时树采样峰 3387654144B；own swap0 | 0.5s采样，非连续cgroup硬峰；实现／元数据读写未单独监督部分unknown |
| 新存储停止及最终库存 | 原JIT C/o/so重叠曾越512MiB；无损归档后 477669342B | 保留越界事实，不改成全程合规；原生q60与扩大面片停止 |
| 原方程、total/scattered E/H、curl、40或32060通道物理解、R/T/A/A_volume及能量 | 本轮全部NOT_RUN | 仅任意边界向量与单位通道泛函，没有新合格场 |
| dot语义消费／原尺寸2TB、48h／NN20% | SOLVER_PACKAGE_NOT_QUALIFIED／NOT_QUALIFIED／NOT_DEMONSTRATED | 不忽略材料差2.9917e-8，不以小面片或缓存节省推断生产能力 |

[response](task042_neural_coarse_inverse/response_v37.md)／[完整结果](task042_neural_coarse_inverse/outcomes/target_p6_boundary_tiles_v37.md)／[独立checker](task042_neural_coarse_inverse/outcomes/records/component_checker_v37.json)／[全部费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v37.json)／[run与source](task042_neural_coarse_inverse/outcomes/records/run_index_v37.json)。本批closed，全部自有actor清除，V24–V36永久closed，旧资格及负结果保持。唯一下一建议：取得一次可预估JIT峰存储的未裁剪原生q60周期缝／角点边界见证，补齐精度与MPC覆盖；不自动运行、不升级到体积求解或NN训练。

<!-- V37-LATEST-END -->

# Task042 V36模型总账：有界完整端口组件通过，原尺寸求解仍未授权

新provider按需生成／读取一批边界系数并释放，避免保留全mode×surface表；代价是更多生成和IO。它是存储接口工程，不是NN收益，也不代替全局求解。

| 对象／实际工作 | 结果／费用 | 资格边界 |
|---|---|---|
| 原50×25×140nm／.7nm规则3D | 完整32060ports；p6容量530856cells／345771066storage | 解析计数／mode实生成，未造目标mesh或PDE |
| 384hex/p3/q15/40port真实边界 | 两seed全部作用／adjoint／复振幅／单位功率≤1e-10；cache82960B／live2 | PORT_COMPONENT_QUALIFIED_ON_MICRO |
| shared-workstation费用／全树采样峰 | 175.774027562 s（所有失败／aux／探针）；603471872B／ownswap0 | 0.5s采样，非连续cgroup峰；IO独立时钟unknown |
| 原方程／E/H/curl／R/T/A/A_volume／逐通道能量 | 本轮NOT_RUN | 无新完整解；旧V35 Schur0.2052488635负结果保持 |
| 神经／原尺寸2TB／48h | NN20% NOT_DEMONSTRATED；TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED | 不以流式cache或micro推断生产资格 |

[response](task042_neural_coarse_inverse/response_v36.md)／[结果](task042_neural_coarse_inverse/outcomes/original_size_port_preparation_v36.md)／[部署](task042_neural_coarse_inverse/outcomes/records/deployment_package_v36.json)。

唯一下一建议：取得与本轮physical／mode合同匹配的dot冻结全局solver包，按部署清单做一次逐字段身份与端口接口验收；本轮不自动实施。
本批已清场，V24–V35永久closed，V36也closed后等待review；下方“当前”仅指其历史时点。

<!-- V36-LATEST-END -->

# Task042 V35：原micro在线块PC未合格，未发布official场／功率（2026-10-04）

本轮首次真实冷启动，用七区局部解处理任意新残差，并由GMRES选择修正组合。代价是每个非零输入八次局部solve和两次传播作用；这是传统块方法，没有神经训练。

| 模型／结果身份 | measured或not_run结果 | 解释／边界 |
|---|---|---|
| .7nm／384hex／p3／q15／18144trace＋40port | 首256步Schur0.20524886351900365>0.01 | ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT，关闭固定七／八块追加预算 |
| 原完整方程 | native/augmented0.07959628543991103、total augmented0.027619862207395922>1e-6 | port/恢复/MPC通过不足以授完整解资格 |
| 费用／同时采样树峰 | actor188.162088667s／2108018688B／ownswap0；834次S/SH、264次PC | shared-workstation，全部aux/探针/旧费用另列，不双加嵌套计时 |
| 原因／范围 | 保存残差平方99.19%在外域；第二周期与FE/REF7 NOT_RUN | 无official R/T/A、NN20%或原尺寸2TB/48h资格 |

[response](task042_neural_coarse_inverse/response_v35.md)／[完整原门](task042_neural_coarse_inverse/outcomes/records/online_checker_v35.json)／[模型身份](task042_neural_coarse_inverse/outcomes/records/run_index_v35.json)。

唯一下一建议是匹配外域Schur的周期／层次全局逆接口与容量资格；本轮不实现。历史后缀逐字保留。

<!-- V35-LATEST-END -->

# Task042 V34：固定完整输入块校正，实测负结果／无新物理解（2026-10-03）

让六个外域块先处理自己的残差、再由联合块抵消反馈，检验跨区域传播能否减少同一原方程残差；保存缓存避免六套因子重载，部署仍需付这些费用。没有训练或新的有限元解。

| 模型／方法／数据身份 | measured结果／资源 | 资格与证据 |
|---|---|---|
| 原.7nm micro、384hex/p3/q15、18144trace/40port、双Floquet/MPI1 | LZ4 rho_full2.97739708904112；LCZ4 4.065825954112519；rho0为2.5444381411607355/3.4623458468352646 | 两态残差放大，FULL_INPUT_FIXED_STEP_INSUFFICIENT；[response](task042_neural_coarse_inverse/response_v34.md) |
| 固定单位系数J+外域补项 | J抵消成功但六外域放大，block6最大；真实S20SH2 | 独立CHECKED，关闭本单步；不否定或自动运行所有Krylov，[checker](task042_neural_coarse_inverse/outcomes/records/full_input_checker_v34.json) |
| 因子／成本／shared-workstation | readonly J dense LU，净483729408B；actor20.032768s，新增全部50.984808s、累计212.190444s，树采样峰1019056128B/ownswap0 | 非factor-free，无global p4/新LU/FE/train；合格N=1仍unknown，[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v34.json) |
| 新E/H/curl、R00_s/p/total、R/T/A/A_volume、40复通道及功率 | 全NOT_RUN，未记录新official值 | 旧V24完整0/5、V23 0/6保持；不能从方向诊断授完整解资格 |
| 神经／原尺寸2TB48h | NN20% NOT_DEMONSTRATED／NOT_QUALIFIED | 无同正确性完整N=1对照、训练或扩模；传统块方法不归NN |

唯一下一建议为不同周期/全局信息传播的信息来源先做身份/恢复/成本对应；dot14项只读更新，unknown保持，未修改其分支。旧失败、task/review/response/raw逐字保留，无merge approval。以下历史原文保留。

# Task042 V33：固定外域输入补齐实现，资源停止／未新增物理解（2026-10-03）

传统块校正给旧回流漏掉的外域残差一个直接入口，可能改善信息传递但不保证收敛；此轮数学／缓存checker已实现，唯一辅助CPU/SMT准入拒绝后没有真实诊断，不能把未运行记为负数值或神经增量。

| 模型／方法／数据身份 | 实际值／单位与成本 | 资格／证据 |
|---|---|---|
| 原.7nm micro、384hex/p3/q15、18144trace/40port、双Floquet | 两冷态rho_full/rho0/rho_ret／外域隔离比全null；actor／原作用／reader／solve0 | RESOURCE_STOP，旧V23 0/6／V24 0/5不提升；[response](task042_neural_coarse_inverse/response_v33.md) |
| B_full固定单位系数／static研究 | final source a874498a…16 compile通过，合成测试／cached checker NOT_RUN | IMPLEMENTED_NOT_QUALIFIED，不作production；无新NN/训练 |
| shared-workstation准入／measured | 48候选为空，probe1.240283s；新监督worker0，累计151.4889468078036s | 内存/PSI等未查；实际tree峰／ownswap／BLAS getterunknown，[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v33.json) |
| 因子／derived容量 | 计划只重载J，A+LU483,729,408B、同时规划4,246,745,088B≤8GiB | 未加载；原生部署仍J2＋外solve6＋A2，非factor-free，不删历史因子 |
| E/H／R00_s/p/total／R/T/A／A_volume／功率 | 本轮全部NOT_RUN，无新official结果 | 小模型／单步诊断不替代最终精度／尺度资格 |
| NN20%／原尺寸2TB48h | 完整合格N=1对照unknown，NOT_DEMONSTRATED／NOT_QUALIFIED | dot p4/120/532不同，不作同正确性分母 |

唯一建议先独立资格化冻结合成可信链；任何真实诊断需新明确窗口与资源授权。历史后缀逐字保留，无merge或自动扩模。

# Task042 V32：固定两冷态回流可信负结果（2026-10-03）

用已有联合与六个外域块的局部解检验一个新增残差方向，原物理和完整40端口不变；好处是可能改善跨块信息传递，代价是七套因子读取和原作用。未形成新有限元场，不提升旧模型资格。

| 模型／方法／数据身份 | 实际值 | 资格／费用与证据 |
|---|---|---|
| 0.7nm micro／384hex/p3/q15、MPI1、18144trace/40port；measured诊断 | LZ4 eta10=.964843748003/g=.998590612859；LCZ4 .980700711250/.998709002549 | 两态rank10创新可分辨，但额外下降仅.14094%/.12910%，关闭固定回流，[response](task042_neural_coarse_inverse/response_v32.md) |
| 完整原作用及checker；measured | S34/SH2，reader7，J4/外域24，pass56，薄流程2，port factor1/solve35；CHECKED | 新LU/assembly/gecon/FE/训练0；保留既有local LU，非factor-free |
| 资源／shared-workstation；measured | actor83.140185s、辅助15.668586s、累计151.488947s，树采样峰1,247,059,968B/ownswap0 | 未取得kernel cgroup权限；实际采样.582–1.021s；旧成本/unknown不免费化，[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v32.json) |
| E/H、R00_s/p/total、R/T/A/A_volume及功率 | 新值NOT_RUN；旧V24 0/5、V23 0/6保持 | 不把方向改进当完整物理合格或official结果 |
| 神经／原尺寸目标 | NN20% NOT_DEMONSTRATED；原尺寸/2TB/48h NOT_QUALIFIED | 本批无NN训练、最佳合格非神经N=1配对或扩模 |

以下历史逐字保留；唯一建议等待dot身份匹配参考/规模证据，不修改其分支、不自动实验或merge。

# Task042 V31：前測实现失败，未新增物理解（2026-10-03）

| 模型／方法／数据身份 | 实际值 | 资格边界／证据 |
|---|---|---|
| 固定0.7nm micro／384hex/p3/q15/40port，not_run | actor0／S+SH0／factor读取0／FE0；两冷态eta10/g10未运行 | 无新E/H或R/T/A，旧V24 0/5／V23 0/6不改，[response](task042_neural_coarse_inverse/response_v31.md) |
| 实际study合成／measured | 18144/40、两态、七synthetic reader及collector通过；前测整体109/1 | 拒绝fixture缺接口；最小修后仅静态通过，非正式方向资格，[测试](task042_neural_coarse_inverse/outcomes/records/tests_v31.json) |
| shared-workstation辅助／measured | CPU11；12.731162693s，累计52.680176060s，树采样峰254,758,912B／swap0 | 一次前测后封闭，formal/checker0，旧账/unknown保留 |
| 神经／目标尺度 | NN20% NOT_DEMONSTRATED，原尺寸/2TB/48h NOT_QUALIFIED | 无训练、完整合格基线或配对；不将传统接线当神经贡献 |

以下旧模型记录逐字保留，不改dot或其他分支，不merge。

# Task042 V30：轻量软件资格，不新增物理解（2026-10-03）

审核器检查保存向量和完整消费；本轮修复入口编译与目录/负例接线，并以最终source完成唯一有界验收，不改变原有限元模型或求解算法。

| 模型／方法／数据身份 | 数值／资源与结果 | 资格边界／证据 |
|---|---|---|
| 0.7nm、384hex/p3/q15、完整40端口；本轮只轻量验收 | 22文件编译、最小7／完整162通过，source1a18f520…，原真实actor/S+SH/reader/FE/训练0 | 无新E/H／R/T/A；旧V24完整0/5、V23 0/6保持，[回应](task042_neural_coarse_inverse/response_v30.md) |
| 合成checker／固定三小矩阵，measured | 32语义变异拒绝且有正控制；三固定fixture通过，2×2残差放大6倍，零局部块拒绝 | 只资格化入口与合成证据链；非真实PC／神经收益，[记录](task042_neural_coarse_inverse/outcomes/records/checker_acceptance_v30.json) |
| shared-workstation辅助，measured | CPU21/math1；树RSS195,633,152B／ownswap0；监督18.785166597s，V27起累计39.949013367s | hard2GiB/warn1GiB；自身后代清空，非无争用性能，[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v30.json) |
| NN20%／原尺寸／2TB／48h | NOT_DEMONSTRATED／NOT_QUALIFIED | 无合格同精度完整N=1对照，unknown保留，不能将传统代数改善归NN |

本轮队列closed，等待review；不重开V26–V29、不改dot或其他分支，不merge。以下历史原文保留。

# Task042 V29：无新模型结果，辅助CPU准入拒绝

| 固定对象／数据身份 | 本批记录与资格边界 |
|---|---|
| 0.7nm micro／not_run | 原384hex/p3/q15、18144trace＋40port、三维缺口／背景/MPC／用户材料不变；真实packet和因子未读取 |
| 新完整方程／场／功率 | NOT_RUN；actor0／S+SH0／reader0／FE0／新LU0；不发布新official R/T/A |
| checker／implementation | source bea514e634a0fde7b1b929535f79a6268856d01b；更严格的完整库存及向量证书、全链fixture已准备，测试未运行，IMPLEMENTED_NOT_QUALIFIED |
| B／纸面 | 全空间传统块补项有条件可逆但非收缩；不接入真实PC、不训练NN，不给神经标签 |
| 成本／shared-workstation | 唯一辅助CPU Gate拒绝；worker前停止，新有载0s，旧21.163846769952215s累计保持；完整合格N=1成本和峰值unknown |
| 旧资格／下一步 | V24 0/5、V23 0/6及NN20%未证实保持；仅下一review可另授权轻量验收，无原尺寸／2TB／48h资格、无merge approval |

[Response V29](task042_neural_coarse_inverse/response_v29.md)／[详细证据](task042_neural_coarse_inverse/outcomes/checker_full_space_cost_v29.md)／[资源账](task042_neural_coarse_inverse/outcomes/records/resource_costs_v29.json)。以下原模型记录原样保留。

# Task042 V28：验算与准入证据补齐，数值仍未消费

独立checker从保存数组重算回流诊断，防止零系数或退化被错误拒绝；新parent映射纠正旧null，成功／失败CPU快照可重算。100项小回归、compileall和V28 dat通过；最终辅助准入未找到合格物理核，前置资源Gate失败后停止，正式准入0／actor0／S+SH0／reader0。没有真实方向结论、新FE或学习资格。

| 项目／数据身份 | 实际值／边界 |
|---|---|
| source／离散 | 4808fcab78bbf1b1284ffba1f3ff19b0033fb937实现；数值source=null；原0.7nm/384hex/p3/q15/40port不变 |
| 成本／shared-workstation | 新辅助8.797189402s，两轮累计21.163846770s/600s；辅助同时RSS150,163,456B、自身swap0；旧77,161.557139s formal下界／N=1 unknown保持 |
| 资源停止／measured | 成功CPU11、最终候选空；原5%/SMT门限未变，失败未查memory/PSI=NOT_CHECKED；原始stderr及快照保存，不重试找核 |
| 资格与下一步 | V24 0/5、V23 0/6保持，NN20%未证实、原尺寸2TB/48h未合格；建议外部条件改善后另审授权，不自动重入/merge |

[Response V28](task042_neural_coarse_inverse/response_v28.md)／[summary](task042_neural_coarse_inverse/outcomes/summary.md)／[原始索引](task042_neural_coarse_inverse/outcomes/records/run_index_v28.json)。旧历史逐字保留，无dot、其他分支、邻任务或系统设置改动。

# Task042 V27：修复测试后，回流诊断因CPU准入未运行

固定J→外域→J只计划检验九个历史方向之外的一个方向，没有改变有限元方程。67项pure回归、compileall及新dat验证通过；正式入口未找到合格空闲物理核，已用完允许的一次只读复核，actor前以NOT_RUN_CPU_ADMISSION收口。两冷态eta10/g10均NOT_RUN，不把资源停止改成方向失败。

| 数据身份／完成项 | 结果与具体边界 |
|---|---|
| 测试窗口修复／measured | 旧42scope+4拒绝+21新回流fixture=67通过；V26真实窗口仍closed，不重开、不重算 |
| 唯一正式入口／not_run | source7b0e03f2fbfb504b13a5f5b4c46c52e0e96a5eb9已clean；actor0/S+SH0/reader0/新LU0，数值资格未测试 |
| 两冷态历史基线 | LZ4 eta9=.966205505618、LCZ4 .981968429990；本轮回流抵消/创新/eta10/g10无实测 |
| shared-workstation成本／measured | 辅助12.366657368s、采样整树峰134,275,072B、ownswap/VRAM0；总window自02:14:16.872215Z不刷新，准入读取独立费用unknown计总wall |
| 原方程／NN | 新完整场资格NOT_RUN；V24 0/5、V23 0/6保持；无NN训练或合格配对，20%收益NOT_DEMONSTRATED |
| 因子及容量／边界 | 原七bundle实际未读；计划rank≤3888<18144，不可独立全空间右PC；derived4,807,239,744B非RSS，不声称factor-free |
| 停止／下一步 | CPU准入额度耗尽，ledger closed/active null；仅建议下一review判断是否重新授权未消费诊断，当前不重入，无merge approval |

[Response V27](task042_neural_coarse_inverse/response_v27.md)／[详细记录](task042_neural_coarse_inverse/outcomes/return_direction_v27.md)／[成本](task042_neural_coarse_inverse/outcomes/records/resource_costs_v27.json)／[原始索引](task042_neural_coarse_inverse/outcomes/records/run_index_v27.json)。GitHub视觉NOT_VERIFIED，本地静态另查。以下历史逐字保留，旧建议不授权本轮继续。

# Task042 V26：联合新方向可信但增量不足

**V26已完成，数值资格通过，预登记决策为 `FIXED_JOINT_DIRECTION_INSUFFICIENT`。** 两终态g均≥0.95，未达到两者g≤0.75的继续研究信号。关闭本固定5／7联合方向提案，不新启动迭代、另一块对或训练。它产生了可分辨的新方向，但不能显著消除旧八方向留下的残差；不是新的有限元解，也不否定所有接口／神经方法。

把两个相邻局部块一起解，是让一次局部解考虑它们之间的双向耦合。本批把这个新向量的原方程响应，加入已有八个向量的响应集合，只检查多出的方向是否有用。代价是一套更大的稠密矩阵／LU、一次只读重载与有界原作用；不把诊断向量作为部署PC或求解终态。

eta8／eta9是修正后原trace残差范数除以各自当前残差范数；g比较加入新方向前后剩余残差，分母不是物理b或参考场。范数下降与平方范数消除分别列出，均为measured／derived offline diagnostic。

| 固定已消费冷终态 | eta8 | eta9 | g=eta9/eta8 | 相对e8范数下降 | 相对e8平方范数消除 | rank |
|---|---:|---:|---:|---:|---:|---:|
| V24-LZ-CYCLE4 | 0.983236989810 | 0.966205505618 | 0.982678149451 | 1.732185% | 3.434365% | 9 |
| V24-LCZ-CYCLE4 | 0.989924628585 | 0.981968429990 | 0.991962823870 | 0.803718% | 1.600976% | 9 |


两个状态不是fresh终测，均为V24已消费冷末态。旧V25数值和原始记录不改；本批没有调用REF7、teacher、NN权重、旧p1 T/U/R、D_L或Krylov库存。
实际source `652cb206cd1ebeb1c4182ac2300c1dc23c57b48f`，actor33.262622s、采样峰1,625,231,360B、ownswap/VRAM0；S14/SH2、唯一joint LU1、solve9/显式pass18/gecon保守22；JOINT_5_7_DENSE_LU_PRESENT，无旧八LU读取。没有新物理解/参考/NN；神经20%仍未证实。

唯一建议是另审“外域已有块处理泄漏后回到J补偿”的固定回流方向资格，不扩大块、不启动迭代。[回应](task042_neural_coarse_inverse/response_v26.md)／[详细结果](task042_neural_coarse_inverse/outcomes/joint_block_direction_v26.md)／[run index](task042_neural_coarse_inverse/outcomes/records/run_index_v26.json)／[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v26.json)。以下原历史逐字保留，旧下一步不授权重跑。

# Task042 V25记录：固定算子的诊断，非新物理解

| 模型／方法／状态 | 原方程／场资格 | 资源及source |
|---|---|---|
| 0.7nm三维缺口384hex/p3/h0.175nm/q15/MPI1/40通道；三份V24冷残差、原8块LU方向 | rank8／原作用及最小残差见证通过；LZ4/LCZ4 eta8=0.9832369898/0.9899246286，EIGHT_DIRECTIONS_WEAK；新native/E/H/RTA NOT_RUN，V24历史0/5保持 | shared-workstation25.665227s、同时整树峰1,832,550,400B、swap/VRAM0；S39、LU40、三角80；source bc88fe5a81d086059dec705db333b9cf9bf2921e |

这里只复用LOCAL8_DENSE_LU_PRESENT，不新装配／分解，不读REF7／NN权重／T/U/R；没有新模型扫描、神经训练增量、原尺寸0.7nm/2TB/48h或production资格。旧上游和历史未知费用保留，神经收益门槛20%。[回应](task042_neural_coarse_inverse/response_v25.md)／[原始证据](task042_neural_coarse_inverse/outcomes/records/run_index_v25.json)。以下模型总账历史字节保持。

# Task042 V24最新收口：对称首块与唯一审核完成

四条首块及唯一冻结审核已完成，完整同离散资格0/5。资格由原方程、场、端口及逐通道功率共同决定；单项native通过或残差降低不能替代完整资格。神经20%增量独立记NOT_DEMONSTRATED：本批无隐藏层训练，也没有最佳合格非神经同精度／完整端到端成本的配对性能证据。

本批用八个固定几何区域中的完整局部解来修正残差，再比较追加既有低阶作用像校正的效果。局部解考虑同组未知量的耦合；组合解在局部修正后再处理粗空间能够消除的部分。原有限元方程、跨块耦合、内部恢复和全部40端口保持，代价是八块稠密LU、每次八个局部解及组合路线额外的原作用和全局薄矩阵乘法。

| 路线／起点 | 周期 | Schur（≤1e-6） | native（≤1e-6） | 散射E差（≤1e-4） | 最大通道功率差（≤1e-6） | 完整资格 |
|---|---:|---:|---:|---:|---:|---|
| V21-C-FINAL | 历史暖点 | 2.528117033e-06 | 9.804133464e-07 | 7.816080389e-05 | 1.719644651e-06 | FAIL |
| LW-FINAL | 4 | 2.502117907e-06 | 9.703307865e-07 | 7.778607315e-05 | 1.666968717e-06 | FAIL |
| LCW-FINAL | 4 | 2.524169303e-06 | 9.788824018e-07 | 7.808877891e-05 | 1.708820964e-06 | FAIL |
| LZ-FINAL | 4 | 0.0813766679 | 0.03155817955 | 0.5688882779 | 0.007245973616 | FAIL |
| LCZ-FINAL | 4 | 0.3252622227 | 0.12613792 | 0.8368884535 | 0.007757579435 | FAIL |

| 状态；全部为未资格诊断 | R00_s | R00_p | R_total | T_total | A_balance | A_volume | 能量误差 |
|---|---:|---:|---:|---:|---:|---:|---:|
| LW-FINAL | 0.1176449645 | 6.952925802e-13 | 0.1176460215 | 0.8770494499 | 0.005304528605 | 0.005306406598 | 1.877993788e-06 |
| LCW-FINAL | 0.1176449706 | 7.011877452e-13 | 0.1176460275 | 0.8770494918 | 0.005304480711 | 0.005306406825 | 1.92611376e-06 |
| LZ-FINAL | 0.1104079944 | 3.889963505e-12 | 0.1104090388 | 0.8698018277 | 0.01978913352 | 0.005272352662 | 0.01451678086 |
| LCZ-FINAL | 0.109887183 | 1.728616029e-09 | 0.109900937 | 0.8797669468 | 0.01033211621 | 0.005293212092 | 0.005038904117 |

固定Full3D/p3/h0.175nm/q15/MPI1：384hex、storage34050、trace18144、internal13824、slave2082、40通道；fine全局NNZ未构造。正式wall1977.711696s、整树采样峰2782064640B、自身swap/VRAM0；分阶段成本与hash均见本轮回应及records。

唯一下一建议：以本批已保存的零初值残差为输入，预登记一次有界的块内／跨块耦合作用分账，判断下一种局部通信机制需要补足的方向及容量；不立即改变块数、重叠、粗空间或追加求解。

[本轮回应](task042_neural_coarse_inverse/response_v24.md)。以下历史原文逐字保留；其中“当前”仅指记录当时。

# V24续行记录：账户接口及执行审批已恢复

2026-10-02T14:07Z之后实际只读主机核验通过：新候选核CPU15、PSI full avg10=0、原系统/邻增长余量和磁盘Gate通过。周额度用尽时允许使用现有余额；明确禁止使用重置卡，未调用重置功能。以下认证阻塞是早先真实历史，保留原始失败；本批现继续原Review V21队列，原heavy-stop15:34:23.502588Z、deadline16:04:23.502588Z保持。当前真实数值仍未运行，后续来源与计数由正式run绑定。

# Task042 V24模型总账／执行服务阻塞，非数值负结果

| 项目 | 本轮实际证据／限制 |
|---|---|
| 原模型 | 0.7nm/384hex/p3/q15/完整40端口；原材料/方程保持 |
| 实现source | 370b7bbe2455448b320ca4272eb62950e4715ecc；尚无formal run source |
| 定向回归／入口 | 28 passed、2个已消费旧用例deselected；6/6 valid |
| 八块实际因子／周期／审核 | 0／0／0；真实资格NOT_RUN |
| 规划容量 | 5709615024B≤8GiB；矩阵+LU1354430592B≤2GiB；derived非RSS |
| 已监督小测试／准入 | 43.5801978582s；树峰156880896B，ownswap/VRAM0；非部署峰 |
| 原方程、E/H、通道和R/T/A | 没有新值；既有负结果保持 |
| 截止 | start12:04:23.502588Z；heavy15:34:23.502588Z；total16:04:23.502588Z，不刷新 |
| Git | 实现ahead1；认证故障后的交付文件本地待commit/push，未伪称已推送 |

本轮已实现固定八块局部完整LU与同规格粗层配对的数值核、角色reader、有限队列和六个one-run入口。最终小模型定向回归28 passed，六入口均validate；正式SETUP和LW/LCW/LZ/LCZ/VERIFY均NOT_RUN。首次队列未通过空闲物理核准入，数值actor未创建；有界复核找到核后，启动重试因自动审批服务令牌刷新403而未执行。这不是方法的数值负结果；没有新的原方程/场/功率资格或神经增量。

局部块解旨在每次修正中考虑一组相邻未知量的完整耦合，粗层再处理同一低阶空间中的剩余响应。收益尚待真实试验，代价为局部LU/三角解、粗矩阵读取及原算子作用。当前真实局部矩阵、LU和D_L均未构造，不称它们已存在或factor-free。

原0.7nm模型、canonical用户材料和top20+bottom20保留。新Schur/native/total-native、恢复、场、通道、R/T/A/A_volume、功率和能量均未测量。真实因子0；部署将明确LOCAL8_DENSE_LU_PRESENT与组合GLOBAL_TALL_IMAGE_QR_PRESENT。未训练NN，上游formal研发下界75124.91759302444s及未知暖链费用保持；无最终0.7nm/48小时或merge资格。

唯一下一建议：恢复Codex客户端认证后，原窗口仍有效且fresh资源准入通过时继续已验证的原队列；窗口耗尽则等待下一review明确新的时间窗口，不扩大数值范围。

[回应](task042_neural_coarse_inverse/response_v24.md)、[分流](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v24.json)。
以下历史正文逐字保留；旧“当前”只指其当时阶段。

# Task042 V23模型总账／research-only

按Review V20完成S作用像资格、D同残差粗比较、M四周期暖校正、Z八周期独立零trace及冻结后的唯一FE审核。六个去重状态0/6完整合格，M/Z新求解0/2原方程合格。MR单次最小残差性质通过，但未突破暖平台；零trace散射仍基本未求出。没有神经训练增量、严格同精度加速、目标0.7nm/48小时或merge资格。

本次保持1248个低阶来源的修正方向不变，先计算每个方向在原方程中的响应，再把这些响应正交化。这样可以在同一空间里选出使当前完整残差最小的一次修正，避免旧Galerkin校正只消去部分测试分量却放大完整残差。随后仍保留全部fine自由度运行GMRES。代价是一张大型薄像矩阵、全局薄QR、每次读U并做小三角解；单次最小化不保证完整场准确或后续迭代收敛。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 散射E≤1e-4 | 散射H/curl≤1e-4 | 单通道功率差≤1e-6 | 完整资格 |
|---|---|---|---|---|---|---|
| V21-C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | FAIL |
| D-G | 5.78958683346e-05 | 2.24522366775e-05 | 7.78244591217e-05 | 7.78408347361e-05 | 1.61837477908e-06 | FAIL |
| D-MR | 2.52781296425e-06 | 9.80295427727e-07 | 7.81607966537e-05 | 7.81769594619e-05 | 1.71964931439e-06 | FAIL |
| M-FINAL | 2.50771436526e-06 | 9.72501113856e-07 | 7.80593538145e-05 | 7.80755355416e-05 | 1.69973146436e-06 | FAIL |
| Z-FINAL | 0.068113177161 | 0.0264145476792 | 0.989143298805 | 0.989118901047 | 0.00910569035662 | FAIL |
| Z-CYCLE4 | 0.0690781713672 | 0.0267887760816 | 0.998538390324 | 0.998515077488 | 0.00940673781215 | FAIL |


GLOBAL_TALL_IMAGE_QR_PRESENT；同T1248/tau、40端口，raw与derived分开。实际source `0d64407e9ec8c5d0b1da947a17f7bc390b8ccd52`，正式wall1061.43058951s，历史下界75124.917593s，树峰2061123584B。暖上游精确per-solution账unknown；零trace不是geometry-to-solution fresh。

唯一下一建议：在相同冻结T/40端口下，预登记一套按FE邻接构造的固定p3局部细层作用，替换目前的标量tau项；先验证原作用/容量/线性与完整fine方向，再仅做最多4个暖及零trace周期，与本批scalar-fine控制配对。依据是本批AT作用像只覆盖约0.024%的暖残差平方范数，单次左测试改换可信却M仍停滞、Z散射仍遗漏；这支持检验细层作用是否不足，但不证明它是唯一根因。该建议尚未执行，不自动调patch/ordering/shift、重开p4或扩大模型，需下一review明确合同。

[Response](task042_neural_coarse_inverse/response_v23.md)、[Gate](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v23.json)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v23.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# Task042 V22模型总账／research-only

本批按Review V19完成真实p1传递、固定粗层与PC资格、无PC暖对照N、PC暖校正P、独立零trace路线Z，以及冻结后的独立FE审核V。条件T未准入。原方程合格0/3，新候选完整同离散资格0/3；连同历史暖参照，审核0/4。没有新合格解、神经训练增量或同严格精度加速，最终0.7nm大模型/48小时仍NOT_QUALIFIED。

本次让低阶有限元场提供一组可跨单元耦合的修正方向：先把真正的p1边/面矩插值到原p3有限元空间，再取独立trace。将原p3方程投影到这些方向，得到1248阶小粗矩阵；解粗矩阵后仍保留全部fine方向继续GMRES。它改变每次残差校正，不改变原有限元方程。收益候选是减少困难方向的搜索；代价是真实传递构造、一个有容量上限的全局粗LU、每次额外fine作用与粗解。结果没有显示本固定配置能突破暖残差平台。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射H/curl≤1e-4 | 单通道功率差≤1e-6 | 完整资格 |
|---|---|---|---|---|---|---|---|
| V21-C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 3.40202831061e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | FAIL |
| N-FINAL | 2.50988202767e-06 | 9.73341741358e-07 | 3.37748990869e-07 | 7.80692408032e-05 | 7.80854267327e-05 | 1.70671444066e-06 | FAIL |
| P-FINAL | 2.51429776221e-06 | 9.75054180268e-07 | 3.38343204781e-07 | 7.79710706735e-05 | 7.79872769396e-05 | 1.69129085703e-06 | FAIL |
| Z-FINAL | 0.00411726221107 | 0.00159668985526 | 0.000554050400082 | 0.022911848074 | 0.022911564544 | 0.00266031533569 | FAIL |

P1_TRACE_GALERKIN：n1=1248、全局有界粗LU明确存在；完整fine方向、40端口和原方程保留。新warm源24fbbad/验证7a7a44e，正式wall3092.887219s，研发历史formal下界74063.487004s，上游per-solution精确账unknown。微型模型未合格，目标0.7nm/2TB/48小时不获资格。

唯一下一建议：在同一冻结T、同一暖点原残差上，仅比较一次原作用像最小残差粗校正与当前Galerkin粗校正。前者直接用barS*T的薄QR求能减少当前原残差的T系数，保留原40端口及完整fine方向；不读REF7，不造正规方程，不改T/rank/tau或扫参数。目的是区分“同一粗空间中的左测试/粗细耦合选择”与“必须增加空间”这两个可能性。依据是约99%的trace误差平方范数已有表示，但其两个分量的原A作用约为完整误差作用的2448倍并抵消；这尚不证明唯一根因或病态。本批未实施，须下一review另行授权。

[Response](task042_neural_coarse_inverse/response_v22.md)、[Gate](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v22.json)、[来源](task042_neural_coarse_inverse/outcomes/records/source_inventory_v22.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# Task042 V21模型总账／research-only

按Review V18执行D0、A、B、C和冻结后的独立V（B存在下述历史向量读取缺口），完整资格 **0/5**，分类 **NOT_QUALIFIED**。B/C未取得完整有限元资格；不宣称完整求解、神经训练增量或同严格精度加速。

本轮分别改变两步：把完全相同类别的局部矩阵按最多64个单元一起乘，减少每次重复展开；然后用固定GCROT配置保留少量修正方向及其方程作用，检验是否减少后续重复搜索。前者是精确作用的工程优化，后者是线性残差修正；均未训练隐藏层或改原有限元方程。代价包括类别缓存、最多33对回收向量、内部Krylov向量、副本、端口闭合、逐周期原审核与保存。

原0.7nm、384hex/p3/h0.175/q15、双Floquet、top20+bottom20通道保持；trace18144、内部13824、slave2082、完整z18184。Si从canonical用户表离线读取：n=0.999885140474+4.32477054e-6i、epsilon=n*n，source0.699999988仅明确alias到nominal0.7，不插值。

表中原rho为旧oracle的完整norm(b-Sz)/norm(b)，分母固定为原完整物理b；wall含该路线本批失败/恢复费用。measured、无量纲残差及秒；共同baseline为V19 L-GPOLY末态，未用V20 N/ILU结果。证据：[逐周期](task042_neural_coarse_inverse/outcomes/records/cycle_history_v21.csv)、[状态](task042_neural_coarse_inverse/outcomes/records/checkpoint_inventory_v21.json)。

| 路线 | 完整边界调用 | 原rho起点 | 原rho最终 | 原native最终 | charged S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|---|---|
| B | 16 | 9.67833470962e-06 | 7.73068606402e-06 | 2.99798928999e-06 | 4656 | 393.743535608 | CALL_LIMIT |
| C | 112 | 9.67833470962e-06 | 2.5281170328e-06 | 9.80413346383e-07 | 30645 | 2939.28866421 | TIME_VERIFY_RESERVE_STOP |

冻结后的独立场审核才读取已有REF7；其实际原native=3.01796304395967e-12、独立total-native=1.43744486618839e-12，没有置零、重建准确解或参考反馈。两种native分母不同，不能互换。下表场误差相对同mesh/p3参考，不是离散误差或连续解误差，全部measured；[完整Gate](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v21.json)。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 独立total-native | 散射E≤1e-4 | 散射curl≤1e-4 | 逐通道功率差≤1e-6 | 完整合格 |
|---|---|---|---|---|---|---|---|
| V19-L-GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | 1.7855346417e-06 | False |
| V19-L-GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | 5.64706064632e-06 | False |
| B-FINAL | 7.73068606402e-06 | 2.99798928999e-06 | 1.0403004379e-06 | 7.94237400141e-05 | 7.94361776624e-05 | 1.88874663809e-06 | False |
| C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 3.40202831061e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | False |
| C-CALL32 | 4.43845248007e-06 | 1.72124865592e-06 | 5.9727222794e-07 | 7.88465049064e-05 | 7.88620685216e-05 | 1.8483718407e-06 | False |

自然排序ILU0/P40在V20负结果已收口，本轮分别测试重复局部张量展开的执行成本与固定GCROT回收空间。作用44.536534→23.471869s为工程收益；循环机制必须另看原残差和全部场Gate。实际source97a17aee9a9cc2d91904b4c89f07c4d1cfbd631c, c91954c47d55242fd95ae7efcb44272dcce3a0ec, d7bfcb58632b344f8ed9b9fd1467c6c224df0bc4；新增formal wall3482.125663s，历史下界70970.599785s。失败费用、上游暖初始化成本和旧超时记录保持。

## 最终取舍和唯一下一建议

B/C未取得完整有限元资格；不宣称完整求解、神经训练增量或同严格精度加速。作用实现的收益与循环空间的原残差效果分开；功率及场资格仍由全部原Gate决定，低loss/小内存不能替代它们。这里只是micro固定离散对照，最终0.7nm非可分目标、离散误差、目标规模可扩展容量和48小时均NOT_QUALIFIED。

唯一下一建议：在同一冻结micro上，只预登记一次“固定p1原物理粗层＋现有局部修正”的容量／传递资格及最多4个GMRES256周期对照：让更低阶的原Maxwell方程处理远距离耦合，保留负质量项、Floquet及完整40端口，避免把正定AMS/HX成功误当散射资格。先复核可复用高低阶传递与既有负结果；容量不合格就不启动，任何global p1 factor必须明确披露，不能称factor-free或重开p4强逆。依据是本批无PC循环的同工作量无优势、112调用仍不合格且最后16调用降幅不足5%。可用性、低阶色散误差与收益均unknown，只作为下一review的单一有界建议。 本批未实施，等待下一review；不自动增加循环容量/迭代、建PC、启动新参考或放大模型，不merge master。

[详细结果](task042_neural_coarse_inverse/outcomes/exact_action_recycled_correction_v21.md)、[run](task042_neural_coarse_inverse/outcomes/records/run_index_v21.json)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v21.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# Task042 V19模型总账／research-only

P在每个周期重新搜索256个方向，只留下当前解；L额外保留本路线最近至多3个修正方向，用于减少下个周期重复搜索。两者都继续解完整原方程，保留40端口和单元内部的原恢复。这里改变的是重启之间保存的信息，没有训练网络、改变材料或缩减物理未知量。

| 方法／库 | 实际调用 | 原rho起点→最终 | 本路线S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|
| P_GPOLY | 64 | 0.000146307718165 → 2.23358499521e-05 | 16768 | 2279.93663295 | FIXED_64_CYCLE_LIMIT |
| P_GNN | 64 | 0.000199556374692 → 3.24881797774e-05 | 16768 | 2261.5433094 | FIXED_64_CYCLE_LIMIT |
| L_GPOLY | 64 | 0.000146307718165 → 9.67833470962e-06 | 16962 | 2298.25489228 | FIXED_64_CYCLE_LIMIT |
| L_GNN | 64 | 0.000199556374692 → 1.44393838546e-05 | 16962 | 2327.33009045 | FIXED_64_CYCLE_LIMIT |


新增正式one-run监督wall **9199.970576s**；本批辅助监督wall **102.206160s**（截至费用快照，含失败小测试；后续交付开销计入总elapsed）。V6起formal累计下界 **66613.525719s**，旧辅助unknown保持。同时整树采样峰 **796585984B（0.741879GiB）**，own swap/VRAM **0B**。父队列和子one-run计时嵌套，不重复相加；全部成本标shared-workstation。

完整资格0/8，FIELD_AND_EQUATION_PROGRESS_NOT_QUALIFIED。原micro/用户材料/40ports不变，实际run source `b58919a4a0dcd677b915eb7d9bbd314520aef0e0`。两库共同随机神经G0，GPOLY不称完全无神经；无hidden训练、new基、p4逆或参考LU。上游建基/LSQR不可省略、精确缺项unknown；未改production default/未merge/目标48小时NOT_QUALIFIED。
[Response](task042_neural_coarse_inverse/response_v19.md)、[结果](task042_neural_coarse_inverse/outcomes/post_lsqr_residual_polish_v19.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v19.json)。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# Task042 V18模型总账／research-only

| 固定模型与路线 | 完成/资格 | 新增工作与成本 |
|---|---|---|
| 0.7nm/384hex/p3/q15/40ports; G64/G256 | 两库16/8周期，原方程FAIL | 每库1024+2048 Arnoldi；无Q/U/R加载 |
| 同模型原V17 GK独立R | GP12831/GN11903；完整0/8 | 新GK6484/5784；wall边界，不是已证实停滞 |

新增正式one-run监督wall **19905.129134s**（5.529203h）；V6起formal下界 **57413.555143s**。旧辅助unknown保持。同时整树采样峰 **2576646144B（2.399689GiB）**，own swap/VRAM **0B**，全部成本为shared-workstation。

无hidden训练、新基、PC、global p4 LU或新参考；两库共同随机神经G0，GPOLY不称纯非神经。实际run source `d3e5800ee379168ca33bc3dae595de1c8aa71063`，无production default/merge/目标48小时资格。[回应](task042_neural_coarse_inverse/response_v18.md)、[结果](task042_neural_coarse_inverse/outcomes/gmres_repair_residual_completion_v18.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v18.json)。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# Task042 V17模型登记：冻结基辅助可恢复全空间与GMRES，research-only

| 同一0.7nm micro／固定Q3098 | 最终LSQR逻辑步 | 新GK measured..charged | G周期 | Arnoldi步 | 最终Schur | 最终native | 散射E误差 | 散射curl误差 | LSQR停止／G停止 |
|---|---|---|---|---|---|---|---|---|---|
| GPOLY | 6347 | 6091..6091 | 0 | unknown; discarded 0..64 | 0.000490220469 | 0.000190109352 | 0.000265162174 | 0.0002631196 | LSQR_RESERVED_G_BOUNDARY / GMRES_INTERFACE_FAILED |
| GNN | 6119 | 6119..6135 | 0 | unknown; discarded 0..64 | 0.000594477082 | 0.00023054046 | 0.000249203787 | 0.000245918456 | LSQR_RESERVED_G_BOUNDARY / GMRES_INTERFACE_FAILED |

原物理micro与两库Q3098保持；不是新NN训练、监督拟合、p4预条件逆或最终目标资格。

新增正式数值监督wall **16284.035028s**；V6起formal累计下界 **37508.426009s**。同时整树采样峰 **2577092608B（2.400105GiB）**，own swap **0B**、GPU分配0；全部成本为shared-workstation。

[完整数据/source/hash](task042_neural_coarse_inverse/outcomes/records/run_index_v17.json)、[Response](task042_neural_coarse_inverse/response_v17.md)。未改变production default，未批准merge。
以下历史正文逐字保留；旧版本的“当前”只指其当时阶段。

# Task042 V16模型登记：固定基辅助全空间LSQR，research-only

| 模型／方法 | 容量与身份 | measured资格／资源 |
|---|---|---|
| task042_v16_fixed_0p7nm_p3_micro | 原384hex/p3/q15/双Floquet/40ports/canonical USER Si；physical2b532f…；source ef60675dada2556a5527101f90fc83540d60e242 | 同离散0/6；不表示最终目标48h资格 |
| CLOSED-0／GPOLY／GNN | Q=0／3098／3098＋完整18144／15046／15046维补空间；G0共同随机神经1560，local POLY／NN补充1538；无hidden训练或新dataset | formal监督新增下界4447.81145s、树峰4003057664B、ownswap/VRAM0、shared-workstation；大基/QR/workspace计入，无训练；GPOLY/GNN资源partial不冒充完整数值失败 |

[basis/hash](task042_neural_coarse_inverse/outcomes/records/basis_identity_v16.json)、[配对](task042_neural_coarse_inverse/outcomes/records/candidate_comparison_v16.csv)、[Response](task042_neural_coarse_inverse/response_v16.md)。旧p4逆关闭，未改默认、未批准merge。以下模型总账历史原样保留。

# Task042 V15模型登记：局部随机特征/多项式与配对组合，research-only

| 模型/身份 | 方法与容量 | measured资格 |
|---|---|---|
| task042_v15_fixed_0p7nm_p3_micro；原384hex/p3/q15/40ports、canonical USER Si、physical2b532f… | 8盒完整canonical实体，单原入射载波；POLY65与seed420906固定NN65，匹配1544复列；G0+共同补空间各3098列 | LOCAL双方原Schur约.824；UNION-POLY .517714/散射E .283235、UNION-NN .579986/.766071；全部NOT_QUALIFIED，无hidden训练dataset/更新 |
| decoder/source/资源 | 逐块Qc/精确40Hhat闭合/原仿射恢复；纯方程LS、不参考初始化或训练；source db0e68e519767554412c960af14b3c185012f9de，大Q/U/权重/hash在NN-Lab ignored artifact | formal 2106.167431s/树4175888384B、swap0/VRAM0；新artifact约1.020GB，LS工作区计入；shared-workstation性能INCONCLUSIVE |

[表示及权重身份](task042_neural_coarse_inverse/outcomes/records/basis_inventory_v15.json)、[对照](task042_neural_coarse_inverse/outcomes/records/local_candidate_comparison_v15.csv)、[Response](task042_neural_coarse_inverse/response_v15.md)。不替代旧模型、生产默认或合格FE求解；目标48h仍unknown，merge未批准。以下总账历史原文保留。

# Task042 V14模型登记：ORTHONORMAL_NEURAL_FE_BASIS，research-only

| 模型／物理身份 | 实际方法和目的 | measured结果／资格 |
|---|---|---|
| task042_v14_fixed_0p7nm_p3_micro；0.7nm/384hex/p3/q15、true3D notch、40ports、full34050/trace18144 | 8576实hidden生成1560复方向，QR直接Qc；同位置重求头与有限射线对照；不是纯MLP推理或准确场监督拟合 | 6+2profile/10audit，rank1560；最终Phi.317897055，Schur.797366986/native.309221932，散射E/curl.733565775/.733670474，**NOT_QUALIFIED** |
| canonical材料与成本 | Si n=.999885140474+4.32477054e-6i、epsilon=n*n、USER V1；source 87940891c12ccdec35fca39cd453ab9a29eeeda5；Q/c与全部state hash登记 | formal2510.272780s/树peak3.021GiB、ownswap0、shared-workstation；R/T/A仅diagnostic，目标48小时unknown |

[身份与数组](task042_neural_coarse_inverse/outcomes/records/plan_and_input_identity_v14.json)、[原字段比较](task042_neural_coarse_inverse/outcomes/records/candidate_comparison_v14.csv)、[Response](task042_neural_coarse_inverse/response_v14.md)。old p4路线closed；不覆盖旧模型、不改生产default，master merge未批准。以下历史原文保留。


# Task39extra V6最新结果：递归粗逆未资格化，V5双模型成功基线保留

G1/G2已完成，旧新C真实负结果保留；用户补充授权继续有依据的p4/p2诊断，G5与response_v8尚未最终收口。该授权超出V6原停止分流，不改变物理、精度或安全线；不复跑G1/G2。

| 项目 | 最新结论 |
|---|---|
| V6原始LO | 13步true0.667843080037，1800.799s筛选不合格；COARSE_APPROXIMATION_UNQUALIFIED |
| G1/G2精度 | 固定6输入0/6达LO；正式26I4均未达；映射/残差闭合与成本账通过 |
| 资源 | 新screen峰1491857408B、swap/globalΔ0；仅失败13步，不是2GB成功解/完整求解峰 |
| V5保留 | 原始564/notch576步，完整残差、匹配参考与物理Gate通过；参考448页global out归因UNRESOLVED保留 |
| 分流 | HI未资格化、notch/recovery未运行；G1_G2_COMPLETED_DIAGNOSTIC_CONTINUATION_AUTHORIZED；无W0/5nm/0.7nm/生产默认资格 |

方法和失败边界见[Task39extra V6](task039_extra_physical_multilevel/outcomes/coarse_inverse_replacement_v6.md)。成功V5仍为工作站复现基线；新C已实际测试并关闭本轮有限实现，未启动新的内部路线。

以下完整保留历史正文；“当前/下一步”仅指当时阶段，以本节为最新状态。

---

# Task39extra V5最新状态（历史正文保留）

原始13.5nm/p6h10/MPI1 BAL_H零初值564步、唯一notch576步，完整残差分别9.932289220e-7/9.351705517e-7，匹配离散参考和独立物理Gate通过。原始输出平面错误由同一checkpoint的output-only恢复处理，历史WORKER_FAILED不改写。

两次迭代全系统swap增量均0；条件参考global pswpout增加448页，归因UNRESOLVED，尽管采样tree swap0，仍不能声称整个workflow全系统swap0。未取得2GB或0.7nm/生产默认资格。唯一下一对象为有界内存/分布式物理近似C替代全局p4 LU，同时保持粗细平衡；未实施新路线。

统一结果与证据见[Task39extra V5](task039_extra_physical_multilevel/outcomes/balanced_coupling_v5.md)。以下旧阶段结论按当时范围保留。

---

# 开发阶段研究对象与计算结果总账

## Task39extra Review V4：新增诊断登记（不新增official资格）

| 模型/方法 | measured结果与边界 |
|---|---|
| 13.5nm/1°/s/Full3D p6h10/MPI1/线程1/80modes | clean b127546f172e46d0b217680338b4e0ea7aa39f12；8PC、4互补、10逻辑p4、12MatSolve；诊断完成，full solve未运行 |
| 表示/粗响应 | 无损L2投影找p4最佳表示，110步闭合；eta_space=0.084774901、实际粗修正eta_G=0.092065368、range identity3.92727e-13 |
| 互补/真实残差 | H6/S6场误差保留0.941689514/0.934259170；真实JOINT448 LIGHT/JOINT残差比0.999706716/0.999674195 |
| p4精化 | 重建首次1.0086968840613473e-10>1e-10；一次同LU修正后9.492574739321824e-13；旧默认精化0、旧失败不改 |
| rows/NNZ/资源 | p6存储173802/独立164592；p4存储53084/独立48960/增广53164；allocated24730144/factor53417584；RSS峰3540959232 B、reserve4GiB、swap0、3936样本无违规 |
| 时间/终态 | outer保守1130.973242739s<5400s；worker DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS，watchdog/launch COMPLETED、exit0、父进程及2后代清场 |
| 未运行与下一步 | official R/T/A/A_volume/R00_s/p/total/衍射级/EH、p/h/M/MPI/Hybrid扫描、新full solve均not_run；优先取得同A6/b/1°匹配fine参考/真实误差，复用packet，不造新PC |

这个人工误差上p4表示与粗响应均较好，不能据此认定p4色散或真实误差已定位。H6/S6对互补场误差削减有限，即使残差明显下降；粗方向MR使场误差0.092→0.213而残差改善，是诊断目标差异，生产MR未改。C4既有2D QEP不支持规定3D Bloch控制，UNRESOLVED。新批计算账独立于V3，审计时1142.571742s，最终静态补费见[中心JSON](task039_extra_physical_multilevel/outcomes/records/diagnostic_completion_v4.json)。方法、原因矩阵与hash见[中心说明](task039_extra_physical_multilevel/outcomes/diagnostic_completion_v4.md)及[Response V5](task039_extra_physical_multilevel/response_v5.md)。下文保留既有总账历史。

> **用途。** 本文是项目级“模型—方法—结果—资源—状态”总账。它不替代各 Task 的 `task.md`、`outcomes/summary.md`、`response_vN.md` 和正式 JSON record，而是把分散在不同任务中的重型计算统一登记，便于回答：已经算过什么、使用什么算法、得到什么物理结果、消耗多少资源、哪些结果可作为参考、哪些只是探索或负结果。
>
> **维护规则。** 从本文建立起，每次新增正式 PDE、QEP、Hybrid、迭代或自适应模型，都必须在对应 Task 收口时同步更新本文。历史记录没有保存的字段必须写“历史未记录”，当前未执行的字段写 `not_run`，不得猜测。
>
> **2026-07-26 历史回填。** 独立 backfill 重新核对 Task000–Task035c 的 outcomes、response、review 和 compact records。方法级成功表补齐 Task034 的 p2/p3/p4 Full3D、Hybrid、M funnel 与 MPI identity；逐 Task 第3章继续保留失败、停止和未运行证据。
>
> **2026-07-28 收口。** 在不覆盖上述回填的前提下，三方加入 Task035d 最终总账、Review V1 口径修正和 Task035e `staged/not_run` 入口。
>
> **2026-07-29 Task035e partial checkpoint。** 保留原 `config.json` 最终 ledger
> 语义，同时登记 source
> `f1ba5627f163da54fa383b43be58fd38c0da7bc9` 的 Path A cycle 0
> current/p-shadow/h-shadow、59-goal actual DWR/cellwise replay、v27 Path B
> controlled resource stop，以及 sealed reference 的身份/Gate 状态。selected
> action、transition、candidate、cycle 1、Path B v28 与 Hybrid 仍为
> `not_run`；不得把 partial stage pass 提升为 Task035e completion。
>
> **2026-07-29 Task035e selected-p controlled negative。** numerical source
> 仍为 `f1ba5627f163da54fa383b43be58fd38c0da7bc9`；只运行一次 Path A
> cycle-0 selected-p actual candidate。候选的数值与资源 Gate 通过，但既有
> cellwise DWR action prediction 仅 `19/59` factor-two，且 `25/59`
> opposite-sign，故 candidate rejected、cycle 0 current 保留、
> `cycle_advanced=false`。
>
> **2026-07-29 Task035e single-cell p-up controlled negative。** 在相同
> numerical source 上只验证 `cell:r42:l1:i1:j0:k0 p4→p5`。candidate 的
> 数值/资源 Gate 通过，但既有单-cell DWR prediction 为 `0/59`
> factor-two、`30/59` opposite-sign，正式逐级与总量中 `24/53`
> opposite-sign。candidate rejected、cycle 0 current 保留；当前
> cellwise-p quantitative predictor 关闭，只保留 ranking-only 角色。
>
> **2026-07-30 Task035e structured-anchor 与 goal-oriented trace 收口。**
> 既有 p6/h10、h7.5、h5 在冻结 tolerance 下均为 `59/59`；p6/h5
> `factor_nnz` 的 int32 overflow 已用同一 raw MUMPS telemetry 离线修正为
> `2,277,000,000`，没有重跑 PDE。同网格 M1 fixed p5-trace/p6-interior
> 为 `52/59`；field-projection 200-orbit candidate 为 `50/59` 且
> `13.004326 GiB`。最后一次 goal-oriented 16-orbit MPI8 candidate
> 在 `10.929794 GiB`、zero swap 和全部求解/物理 Gate 通过时仅为
> `49/59`：被显式优化的 6 个物理目标全部恢复，但 10 个原本通过的旁路
> 目标越界。因此 direct selective-trace lane 关闭，不再运行第二批或修改
> 阈值/排名公式；iterative 与 Hybrid 保持 `not_run`，等待后续授权。
>
> **2026-07-30 Task035e final closeout。** 最终 Review V1 将本任务冻结为
> `PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED`：reference certification 与
> true local-h/local-p component capability 为 `pass`，automatic
> reference-blind hp cycle 为 `incomplete`，production candidate 为
> `none`，direct selective-trace 为 `closed_controlled_negative`，
> Hybrid/iterative 为 `not_run`，ordinary default 未改变。

---

## 0. 阅读方法、物理对象与统一记号

### 0.1 本文区分的三类物理配置

不同软件或不同 Task 并不总是使用完全相同的几何、偏振和衍射级集合，因此不能把所有数值混为一个收敛序列。

| 配置 ID | 用途 | 周期单元 / 几何 | 波长与入射 | 偏振 | 边界与衍射级 | 主要来源 |
|---|---|---|---|---|---|---|
| `C-COMSOL-P0` | COMSOL 直接/迭代求解器对照 | 周期 `50×25 nm`；空气 `50×25×130 nm`；基底 `50×25×10 nm`；光栅 `16×25×120 nm` | `13.5 nm`；`80°`（相对法线） | P | 两周期端口 + 双 Floquet；仅 `(0,0)` 零级 | `docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md` |
| `C-COMSOL-HO-S` | COMSOL p2–p6直接法与p2 GMRES+GMG收敛矩阵 | 固定三维高阶benchmark；精确geometry/source hash保存在MPH而非Markdown | 13.5 nm项目主点；入射身份以MPH为准 | 偏振身份以MPH为准（Markdown未冻结） | 双Floquet/周期端口；保存R00与总R/T/A，未逐项冻结12通道复振幅 | `docs/COMSOL_direct_solver_report.md` |
| `F-STAGE4-S` | FEniCS Stage4 原始完整 FE 矩阵、Hybrid 和迭代主线 | 单元 `50×25×140 nm`；Si 块 `17×25×120 nm` | `13.5 nm`；`theta=80°`、`phi=0°`，即 `10°` 掠入射 | S | 双 Floquet + Fourier-DtN；top/bottom 各 40 个传播模态，共 80 个辅助量 | Task027–Task033 |
| `F-HO-S` | FEniCS 高阶、h/p、自适应、静态凝聚与Hybrid高阶闭合主线 | Task034 冻结规则矩形光栅；与 `F-STAGE4-S` 同一工程主点族 | `13.5 nm`；`10°` 掠入射 | S | 双 Floquet + DtN；显著衍射级使用 Task035b reference v1 | Task034–Task035e；Task035e 已按 Review V1 以 partial + closed controlled negatives 收口 |

### 0.2 总量、自由度和资源字段

| 字段 | 通俗解释 |
|---|---|
| `FE DoF` / `Full3D-equivalent DoF` | 完整有限元场若全部作为未知量时的自由度。静态凝聚后，其中部分内部自由度不再进入全局求解器，但仍会在求解后恢复。 |
| `rows` / `active rows` | 实际送入 PETSc/MUMPS/Krylov 的全局未知量数量。 |
| `matrix NNZ` | 全局稀疏矩阵中实际非零元素个数。 |
| `factor NNZ` | MUMPS 或局部 ILU/LU 分解产生的因子非零元素；通常大于原矩阵 NNZ。 |
| `R00` | 零级反射功率；在 S 偏振单场模型中等同 `R(0,0)_s`。 |
| `Rtotal` / `Ttotal` | 所有已启用传播衍射级的总反射/总透射。 |
| `A_volume` | 材料体吸收；与 `1-R-T` 的闭合关系需要单独检查。 |
| `Aclosure` | `1-Rtotal-Ttotal`。它是能量闭合定义，不一定等于独立体积分得到的 `A_volume`。 |
| `complex amplitude` | 衍射通道的复振幅，包含幅值和相位；反演和弱衍射级比较时通常比只看功率更敏感。 |
| `peak memory` | 必须注明 RSS/PSS/cgroup、MPI 数和生命周期；不同口径不得直接相减。 |
| `build` | 有限元准备阶段；需要进一步区分 mesh、function space、单元 tensor、Schur、全局插入和 DtN。 |
| `MUMPS setup` | MUMPS symbolic analysis + numeric LU factorization，不是最终回代。 |
| `solve/backsolve` | 已有 LU 后的前后代入；直接法中通常很短。 |

### 0.3 固定登记的显著衍射通道

Task035b 在 `p6/h10` 高阶参考上，以功率阈值 `1e-8` 冻结了 12 个显著通道。后续能够输出完整衍射谱的模型，至少登记以下通道：

- 反射：`R(0,0)`、`R(-1,0)`、`R(-2,0)`、`R(-4,0)`、`R(-5,0)`、`R(-7,0)`；
- 透射：`T(0,0)`、`T(-1,0)`、`T(-2,0)`、`T(-4,0)`、`T(-5,0)`、`T(-7,0)`；
- 有复振幅时，再登记对应的 `r(m,0)` 和 `t(m,0)`；
- 其他新出现且超过当前显著性阈值的传播级必须追加，不能为了保持表格固定而省略。

### 0.4 状态枚举

| 状态 | 含义 |
|---|---|
| `success` | 完成正式求解并通过该模型合同规定的残差、物理和资源 Gate。 |
| `success_with_qualifications` | 主要目标通过，但仍有明确适用范围或工程限制。 |
| `controlled_negative` | 正式运行完成，结果可信，但没有达到研究目标；负结果必须保留。 |
| `failed` | 求解、实现或正式 Gate 失败，不能作为物理结果。 |
| `not_run` | 没有运行，通常由资源、能力或前置 Gate 阻止。 |
| `incomplete` | 已完成部分能力或组件测试，但尚无完整正式模型。 |

---

# 1. 已成功或已形成正式数值证据的模型

## 1.1 COMSOL 收敛与求解器参考

COMSOL 结果分成两套不能混写的配置：

- `C-COMSOL-HO-S`：`docs/COMSOL_direct_solver_report.md` 中的固定三维高阶基准，包含 p2–p6 直接法和 p2 GMRES+GMG 网格序列；用于研究 h/p 收敛趋势。该 Markdown 报告没有冻结 geometry/source hash，所以它是跨软件趋势参考，不与 FEniCS record 宣称逐字节同一模型身份。
- `C-COMSOL-P0`：Task029 的 P 偏振、仅零级求解器 profile 对照；用于比较 GMRES/FGMRES/TFQMR 和 GMG 的时间/内存，不是 p2–p6 高阶收敛矩阵。

COMSOL 报告中的“物理/虚拟内存”来自保存解的求解器历史记录，并非独立 process-tree 峰值；不能与 FEniCS watchdog RSS/PSS 直接相减。

### 1.1.1 COMSOL 直接法：p2–p6 完整收敛矩阵

全部直接法均使用 MUMPS。`R(0,0)` 是零级反射，`R/T/A` 是总量；非零衍射级的逐级功率和复振幅没有在该报告中逐项保存。

#### 二阶（p2）直接法

来源：`3D_benchmark_direct_5to2.mph`。

| 单元 | h (nm) | 保存解 | DoF | R(0,0) | R | T | A | R+T+A | 编译 (s) | 求解 (s) | 总计 (s) | 物理/虚拟内存 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 六面体 | 5.0 | `sol26` | 44,778 | 0.089196444 | 0.089205034 | 0.442485354 | 0.468309588 | 0.999999975 | 6 | 6 | 12 | 6.07 / 7.53 |
| 六面体 | 3.0 | `sol27` | 198,518 | 0.004606061 | 0.004617853 | 0.583648428 | 0.411733715 | 0.999999997 | 6 | 17 | 23 | 10.90 / 13.45 |
| 六面体 | 2.5 | `sol28` | 298,062 | 0.002702704 | 0.002713499 | 0.592823341 | 0.404463159 | 0.999999999 | 8 | 26 | 34 | 14.80 / 18.04 |
| 六面体 | 2.0 | `sol29` | 615,188 | 0.001333357 | 0.001343167 | 0.599213117 | 0.399443711 | 0.999999995 | 6 | 62 | 68 | 31.90 / 36.81 |
| 六面体 | 1.5 | `sol30` | 1,347,314 | 0.000961782 | 0.000971205 | 0.601283002 | 0.397745792 | 1.000000000 | 8 | 182 | 190 | 80.54 / 92.25 |
| 六面体 | 1.0 | `sol31` | 4,379,832 | 0.000791550 | 0.000800726 | 0.602435023 | 0.396764251 | 1.000000000 | 13 | 6,656 | 6,669 | 138.22 / 177.40 |
| 四面体 | 5.0 | `sol21` | 137,082 | 0.003269959 | 0.003649150 | 0.590974352 | 0.405377540 | 1.000001041 | 6 | 11 | 17 | 5.56 / 7.43 |
| 四面体 | 3.0 | `sol22` | 680,916 | 0.000920292 | 0.000930855 | 0.601402819 | 0.397666324 | 0.999999998 | 7 | 60 | 67 | 24.45 / 30.64 |
| 四面体 | 2.5 | `sol23` | 1,176,820 | 0.000839963 | 0.000849423 | 0.602038258 | 0.397112319 | 1.000000000 | 8 | 121 | 129 | 46.90 / 59.14 |
| 四面体 | 2.0 | `sol24` | 2,331,302 | 0.000787537 | 0.000796864 | 0.602442510 | 0.396760626 | 1.000000000 | 12 | 354 | 366 | 113.96 / 143.16 |
| 四面体 | 1.5 | `sol25` | 5,570,202 | 0.000764398 | 0.000773537 | 0.602623242 | 0.396603221 | 1.000000000 | 20 | 8,433 | 8,453 | 114.95 / 168.96 |

#### 三阶（p3）直接法

来源：`3D_benchmark_direct_5to2p3.mph`。

| 单元 | h (nm) | 保存解 | DoF | R(0,0) | R | T | A | R+T+A | 编译 (s) | 求解 (s) | 总计 (s) | 物理/虚拟内存 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 六面体 | 5.0 | `sol36` | 145,943 | 0.001080892 | 0.001090416 | 0.600622445 | 0.398102183 | 0.999815043 | 7 | 21 | 28 | 10.98 / 12.97 |
| 六面体 | 3.0 | `sol37` | 656,405 | 0.000780334 | 0.000789493 | 0.602514829 | 0.396678272 | 0.999982594 | 8 | 89 | 97 | 41.01 / 46.43 |
| 六面体 | 2.5 | `sol38` | 987,929 | 0.000763846 | 0.000772980 | 0.602630122 | 0.396589884 | 0.999992986 | 7 | 153 | 160 | 64.09 / 71.71 |
| 六面体 | 2.0 | `sol39` | 2,047,298 | 0.000755345 | 0.000764467 | 0.602690126 | 0.396543827 | 0.999998420 | 8 | 409 | 417 | 147.79 / 172.98 |
| 六面体 | 1.5 | `sol40` | 4,498,103 | 0.000753516 | 0.000762636 | 0.602702826 | 0.396534236 | 0.999999698 | 10 | 6,126 | 6,136 | 177.38 / 207.10 |
| 四面体 | 5.0 | `sol32` | 395,228 | 0.000797221 | 0.000806276 | 0.602364232 | 0.396791981 | 0.999962489 | 8 | 30 | 38 | 14.86 / 18.48 |
| 四面体 | 3.0 | `sol33` | 1,974,905 | 0.000754575 | 0.000763705 | 0.602694311 | 0.396540721 | 0.999998737 | 11 | 269 | 280 | 103.48 / 126.22 |
| 四面体 | 2.5 | `sol34` | 3,418,457 | 0.000753501 | 0.000762623 | 0.602702776 | 0.396534135 | 0.999999533 | 10 | 638 | 648 | 206.17 / 253.79 |
| 四面体 | 2.0 | `sol35` | 6,780,326 | 0.000753049 | 0.000762169 | 0.602706346 | 0.396531379 | 0.999999894 | 16 | 12,658 | 12,674 | 187.96 / 212.63 |

#### 四阶（p4）直接法

来源：`3D_benchmark_direct_5to2p4.mph`。

| 单元 | h (nm) | 保存解 | DoF | R(0,0) | R | T | A | R+T+A | 编译 (s) | 求解 (s) | 总计 (s) | 物理/虚拟内存 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 六面体 | 5.0 | `sol44` | 339,972 | 0.000757190 | 0.000766316 | 0.602677531 | 0.396652507 | 1.000096353 | 10 | 95 | 105 | 25.49 / 29.56 |
| 六面体 | 3.0 | `sol45` | 1,540,028 | 0.000753065 | 0.000762185 | 0.602706300 | 0.396540399 | 1.000008884 | 10 | 413 | 423 | 126.11 / 145.79 |
| 六面体 | 2.5 | `sol46` | 2,320,620 | 0.000752940 | 0.000762060 | 0.602707173 | 0.396534328 | 1.000003560 | 11 | 519 | 530 | 211.38 / 232.46 |
| 六面体 | 2.0 | `sol47` | 4,818,792 | 0.000752895 | 0.000762014 | 0.602707488 | 0.396531295 | 1.000000797 | 12 | 7,216 | 7,228 | 238.21 / 266.56 |
| 四面体 | 5.0 | `sol41` | 862,488 | 0.000753534 | 0.000762665 | 0.602702752 | 0.396546969 | 1.000012386 | 8 | 89 | 97 | 42.78 / 49.54 |
| 四面体 | 3.0 | `sol42` | 4,323,924 | 0.000752897 | 0.000762016 | 0.602707468 | 0.396530921 | 1.000000405 | 10 | 7,014 | 7,024 | 132.70 / 181.82 |
| 四面体 | 2.5 | `sol43` | 7,490,900 | 0.000752891 | 0.000762010 | 0.602707520 | 0.396530614 | 1.000000143 | 17 | 16,314 | 16,331 | 238.98 / 294.15 |

#### 五阶（p5）直接法

来源：`3D_benchmark_direct_p5.mph`。

| 单元 | h (nm) | 保存解 | DoF | R(0,0) | R | T | A | R+T+A | 编译 (s) | 求解 (s) | 总计 (s) | 物理/虚拟内存 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 六面体 | 6.0 | `sol44` | 341,665 | 0.000753562 | 0.000762683 | 0.602702884 | 0.396431918 | 0.999897484 | 6 | 193 | 199 | 30.69 / 34.39 |
| 六面体 | 7.0 | `sol45` | 299,200 | 0.000753566 | 0.000762686 | 0.602702808 | 0.396431947 | 0.999897442 | 9 | 165 | 174 | 27.09 / 30.77 |
| 六面体 | 7.5 | `sol46` | 285,045 | 0.000753572 | 0.000762692 | 0.602702738 | 0.396431963 | 0.999897392 | 7 | 158 | 165 | 25.61 / 29.66 |
| 六面体 | 8.0 | `sol47` | 160,400 | 0.000772575 | 0.000781718 | 0.602527337 | 0.396505825 | 0.999814880 | 8 | 82 | 90 | 14.73 / 17.27 |
| 四面体 | 6.0 | `sol48` | 927,150 | 0.000752911 | 0.000762030 | 0.602707265 | 0.396529554 | 0.999998849 | 7 | 173 | 180 | 53.71 / 60.83 |
| 四面体 | 7.0 | `sol49` | 570,570 | 0.000753259 | 0.000762379 | 0.602705975 | 0.396527168 | 0.999995522 | 8 | 88 | 96 | 30.15 / 35.42 |
| 四面体 | 8.0 | `sol50` | 407,620 | 0.000754044 | 0.000763173 | 0.602700986 | 0.396529191 | 0.999993350 | 7 | 82 | 89 | 21.60 / 25.43 |
| 四面体 | 9.0 | `sol51` | 261,125 | 0.000751393 | 0.000760515 | 0.602655055 | 0.396564606 | 0.999980177 | 7 | 45 | 52 | 14.71 / 17.11 |

#### 六阶（p6）直接法

来源：`3D_benchmark_direct_p6.mph`。

| 单元 | h (nm) | 保存解 | DoF | R(0,0) | R | T | A | R+T+A | 编译 (s) | 求解 (s) | 总计 (s) | 物理/虚拟内存 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 六面体 | 7.5 | `sol44` | 488,150 | 0.000752896 | 0.000762015 | 0.602707484 | 0.396534894 | 1.000004393 | 8 | 498 | 506 | 61.27 / 66.62 |
| 六面体 | 8.0 | `sol45` | 273,998 | 0.000753398 | 0.000762518 | 0.602702779 | 0.396545414 | 1.000010710 | 11 | 258 | 269 | 33.04 / 37.29 |
| 六面体 | 8.5 | `sol46` | 223,154 | 0.000753762 | 0.000762883 | 0.602701624 | 0.396596135 | 1.000060642 | 7 | 197 | 204 | 27.86 / 30.02 |
| 六面体 | 9.0 | `sol47` | 223,154 | 0.000753760 | 0.000762880 | 0.602701639 | 0.396596161 | 1.000060681 | 8 | 211 | 219 | 27.86 / 29.94 |
| 六面体 | 9.5 | `sol48` | 210,836 | 0.000753774 | 0.000762894 | 0.602701565 | 0.396596246 | 1.000060705 | 7 | 196 | 203 | 26.19 / 28.33 |
| 六面体 | 10.0 | `sol49` | 173,882 | 0.000753784 | 0.000762904 | 0.602701310 | 0.396596333 | 1.000060547 | 8 | 180 | 188 | 22.75 / 24.87 |
| 四面体 | 7.0 | `sol50` | 950,924 | 0.000752895 | 0.000762014 | 0.602707512 | 0.396528638 | 0.999998164 | 6 | 250 | 256 | 62.85 / 72.69 |
| 四面体 | 8.0 | `sol51` | 678,668 | 0.000752916 | 0.000762036 | 0.602707403 | 0.396526993 | 0.999996432 | 10 | 166 | 176 | 43.83 / 49.43 |
| 四面体 | 9.0 | `sol52` | 434,150 | 0.000752859 | 0.000761978 | 0.602706295 | 0.396526991 | 0.999995264 | 11 | 96 | 107 | 26.83 / 31.46 |
| 四面体 | 10.0 | `sol53` | 285,668 | 0.000753151 | 0.000762263 | 0.602706606 | 0.396520162 | 0.999989030 | 5 | 57 | 62 | 18.37 / 20.88 |

#### COMSOL 高阶收敛中心与使用边界

高阶六面体/四面体共同支持的离散中心约为：

```text
R(0,0) ≈ 0.000752895
Rtotal ≈ 0.000762014
Ttotal ≈ 0.6027075
Aclosure = 1-R-T ≈ 0.3965305
```

p5 六面体的 R/T 很稳定，但 `R+T+A≈0.9998974`，因此其直接输出 A 不能单独作为吸收率权威。名义 h 也不是唯一可比指标：p5 六面体 h7.5→h8 和 p5 四面体 h8→h9 都出现非单调变化，实际网格分段、拓扑和材料界面对齐必须一起记录。

### 1.1.2 COMSOL 迭代法

#### p2 GMRES + GMG 网格序列

来源：`3D_benchmark_iterative_gmres_gmg_5to1.mph` 与 `3D_benchmark_iterative_gmres_gmg_smaller.mph`。求解器为 GMRES + GMG V-cycle（1层）。

| 单元 | h (nm) | 数据集 / 解 | DoF | R(0,0) | R | T | A | R+T+A | 编译 (s) | 求解 (s) | 总计 (s) | 物理/虚拟内存 (GB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 四面体 | 5.0 | `sol9` | 137,082 | 0.003270011 | 0.003649197 | 0.590973762 | 0.405377369 | 1.000000328 | 12 | 18 | 30 | 3.49 / 4.65 |
| 四面体 | 3.0 | `sol10` | 680,916 | 0.000920300 | 0.000930863 | 0.601402532 | 0.397666261 | 0.999999656 | 10 | 69 | 79 | 9.04 / 11.42 |
| 四面体 | 2.5 | `sol11` | 1,176,820 | 0.000839995 | 0.000849455 | 0.602040629 | 0.397112717 | 1.000002801 | 11 | 194 | 205 | 13.93 / 16.67 |
| 四面体 | 2.0 | `sol12` | 2,331,302 | 0.000787518 | 0.000796845 | 0.602443826 | 0.396761124 | 1.000001795 | 16 | 181 | 197 | 22.33 / 25.85 |
| 四面体 | 1.5 | `sol13` | 5,570,202 | 0.000764490 | 0.000773629 | 0.602623512 | 0.396603283 | 1.000000424 | 22 | 632 | 654 | 64.47 / 70.18 |
| 四面体 | 1.2 | `sol14` | 10,954,464 | 0.000757581 | 0.000766711 | 0.602673825 | 0.396560450 | 1.000000986 | 42 | 1,581 | 1,623 | 136.48 / 147.94 |
| 四面体 | 1.0 | `dset1` / `sol1` | 19,056,646 | 0.000754947 | 0.000764070 | 0.602690266 | 0.396544380 | 0.999998716 | 27 | 4,838 | 4,865 | 238.31 / 283.72 |
| 六面体 | 3.0 | `sol15` | 198,518 | 0.004605940 | 0.004617728 | 0.583648951 | 0.411734058 | 1.000000738 | 6 | 253 | 259 | 14.79 / 16.67 |
| 六面体 | 2.5 | `sol16` | 298,062 | 0.002702743 | 0.002713539 | 0.592822671 | 0.404462433 | 0.999998642 | 10 | 101 | 111 | 16.13 / 18.06 |
| 六面体 | 2.0 | `sol17` | 615,188 | 0.001333470 | 0.001343281 | 0.599212939 | 0.399443764 | 0.999999984 | 11 | 145 | 156 | 20.97 / 23.30 |
| 六面体 | 1.5 | `sol18` | 1,347,314 | 0.000961807 | 0.000971230 | 0.601282918 | 0.397745805 | 0.999999954 | 10 | 1,458 | 1,468 | 32.67 / 35.61 |
| 六面体 | 1.0 | `sol19` | 4,379,832 | 0.000791578 | 0.000800755 | 0.602435163 | 0.396764293 | 1.000000211 | 21 | 1,192 | 1,213 | 78.27 / 84.31 |
| 六面体 | 0.8 | `dset2` / `sol2` | 8,802,928 | 0.000768335 | 0.000777478 | 0.602595998 | 0.396626826 | 1.000000302 | 23 | 3,854 | 3,877 | 153.29 / 164.63 |

这些p2迭代模型证明GMRES+GMG可以把更细网格推进到数百万乃至千万DoF，但从精度/资源比看，p4–p6高阶粗网格明显更经济。迭代法与直接法内存口径均来自COMSOL solver history，而非外部进程峰值。

#### COMSOL P 偏振求解器 profile 对照

该表来自 Task029 的 `C-COMSOL-P0`，只启用 `(0,0)` 零级。它与上面的高阶S主线不是同一个物理收敛序列。

| 案例 | 外层方法 / 预条件器 | R00=Rtotal | T00=Ttotal | Atotal | 相对 direct 的总量绝对差 | 峰值内存 | 迭代数 | 总时间 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `gmres_gmg_default` | 右 GMRES；restart 300；GMG；GCRO-DR on | `8.2297e-4` | `0.61672815` | `0.38244946` | `4.31e-7` | `13.376 GB` | 历史表未单列 | `232 s` | `success` |
| `gmres_gmg_restart100` | 右 GMRES；restart 100；GMG | `8.2297e-4` | `0.61672773` | `0.38244928` | `1.95e-8` | `11.699 GB` | `544` | `417 s` | `success`；推荐折中方案 |
| `gmres_gmg_restart50` | 右 GMRES；restart 50；GMG | `8.2297e-4` | `0.61672769` | `0.38244930` | `3.20e-8` | `10.547 GB` | 历史表未单列 | `750 s` | `success`；更省内存但更慢 |
| `gmres_gmg_left` | 左 GMRES；restart 300；GMG | `8.2203e-4` | `0.61673963` | `0.38245066` | `1.10e-5` | `11.994 GB` | 历史表未单列 | `152 s` | `success_with_qualifications`；最快但误差较大 |
| `fgmres_gmg_default` | 右 FGMRES；restart 300；GMG | `8.2297e-4` | `0.61672815` | `0.38244946` | `4.31e-7` | `18.290 GB` | 历史表未单列 | `236 s` | `success`；内存未优于GMRES |
| `tfqmr_gmg_default` | 右 TFQMR；GMG | `8.2296e-4` | `0.61672783` | `0.38244933` | `1.06e-7` | `8.992 GB` | `1,241` | `869 s` | `success`；筛选中最低内存 |
| `tfqmr_gmg_saved` | 右 TFQMR；保存模型复跑 | `8.2297e-4` | `0.61672768` | `0.38244931` | `3.72e-8` | `9.010 GB` | `1,142` | `800 s` | `success` |
| `gmres_pc_directpre` | GMRES + DirectPreconditioner | `8.2297e-4` | `0.61672772` | `0.38244931` | `1.19e-13` | `23.110 GB` | 历史表未单列 | `337 s` | `success`；本质仍依赖直接分解 |

**COMSOL总结：**高阶 p4–p6 结果把离散中心稳定在 `R00≈0.000752895`、`R≈0.000762014`、`T≈0.6027075`。p2 GMRES+GMG能够显著降低同网格直接法的内存并推进更细网格，但单纯全域减小h的成本远高于高阶粗网格。COMSOL阶次与FEniCS first-family Nédélec阶次并非一一对应，不能直接复制参数，只能作为收敛趋势和方法选择依据。

---

## 1.2 FEniCS 原始完整 FE 矩阵法：直接求解

这里的“原始完整矩阵法”指：由 UFL/FFCx/DOLFINx 组装包含全部边、面和 cell-interior 自由度的全局 FE 矩阵，再施加 Floquet 和 DtN；没有做 Task035b 的 cell-interior 静态凝聚。

### 1.2.1 Full 3D

Task034 的 `all_model_compact_fixture.json` 冻结了固定几何 S 偏振主线的 40 行事实。下表把其中所有正式 Full3D 求解或受控资源停止逐项登记；主表每行都使用该 compact fixture 中同一 source/MPI8 shard 的 NNZ、factor、residual、peak 和 time，不按相同 `p/h` 从 Task029/032/033 拼接字段。后面的 p4/h5 M-funnel 是单独的 MPI4 authority。

| Task / 模型 | p/h | cells | FE DoF | total rows | matrix NNZ | factor NNZ | R00 | Rtotal | Ttotal | Avolume | true residual | peak GiB | total s | 状态 / 说明 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Task034 Full3D | p2/h5 | 1,680 | 44,698 | 44,778 | 4,896,156 | 31,053,132 | `0.0890130359` | `0.0890216029` | `0.442588279` | `0.468390118` | `9.707e-12` | 2.959606 | 16.5676 | `success`；低成本同网格基线 |
| Task034 Full3D | p2/h3 | 7,776 | 198,438 | 198,518 | 21,317,860 | 258,736,244 | `0.00460127305` | `0.00461303141` | `0.583653357` | `0.411733611` | `7.340687e-12` | 9.534939 | 152.972 | `success` |
| Task034 Full3D | p2/h2 | 24,570 | 615,108 | 615,188 | 65,448,472 | 1,190,762,960 | `0.00133312476` | `0.00134293285` | `0.599213229` | `0.399443838` | `1.747833e-11` | 32.539612 | 1,235.54 | `success`；p2 最细正式点 |
| Task034 Full3D | p3/h10 | 252 | 23,073 | 23,153 | 5,754,869 | 15,148,907 | `0.0553826781` | `0.0553984905` | `0.406067867` | `0.538533643` | `2.649470e-12` | 2.744572 | 20.0918 | `success`；粗网格高阶起点 |
| Task034 Full3D | p3/h7.5 | 720 | 63,747 | 63,827 | 15,675,515 | 55,947,095 | `0.00307976819` | `0.00309072745` | `0.591160863` | `0.405748409` | `7.682277e-12` | 4.609695 | 52.3277 | `success_with_qualifications`；固定-p等精度压缩点 |
| Task034 Full3D | p3/h5 | 1,680 | 145,863 | 145,943 | 35,566,727 | 165,491,291 | `0.00108058337` | `0.00109010701` | `0.600622478` | `0.398287415` | `6.982003e-12` | 9.040073 | 149.658 | `success`；MPI identity authority |
| Task034 Full3D | p3/h3 | 7,776 | 656,325 | 656,405 | 157,785,425 | 1,307,605,045 | `0.000780309834` | `0.000789467957` | `0.602514984` | `0.396695548` | `8.489277e-11` | 44.068672 | 1,726.36 | `success`；p3 收敛主点 |
| Task034 Full3D | p4/h10 | 252 | 53,084 | 53,164 | 24,730,144 | 55,462,256 | `0.00187216051` | `0.00188231722` | `0.596619520` | `0.401498163` | `4.626760e-12` | 5.639561 | 115.525 | `success` |
| Task034 Full3D | p4/h7.5 | 720 | 147,844 | 147,924 | 68,065,896 | 197,474,720 | `0.000793283286` | `0.000802469015` | `0.602429773` | `0.396767758` | `1.271517e-11` | 12.724396 | 345.384 | `success` |
| Task034 Full3D | p4/h5 | 1,680 | 339,892 | 339,972 | 155,421,000 | 565,926,400 | `0.000757187647` | `0.000766313377` | `0.602677531` | `0.396556156` | `2.401474e-11` | 28.888458 | 917.470 | `success`；Task034 高阶固定几何参考 |

#### Full3D 资源停止（不是成功物理解）

| p/h | 已完成阶段 | rows / NNZ | measured peak | 预测或停止原因 | 状态 |
|---|---|---:|---:|---|---|
| p2/h1 | assembly | 4,379,832 / 461,122,320 | 67.922901 GiB | factor upper 418.821 GiB；未启动 factorization | `not_run_by_conservative_resource_gate_after_assembly` |
| p3/h2 | assembly | 2,047,298 / 488,789,000 | 64.014950 GiB | factor upper 232.460 GiB；未启动 factorization | `not_run_by_conservative_resource_gate_after_assembly` |
| p4/h3 | assembly | 1,540,028 / 696,091,072 | 80.537712 GiB | factor upper 204.132 GiB；未启动 factorization | `not_run_by_conservative_resource_gate_after_assembly` |

**证据：** `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、
`benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/all_model_compact_fixture.json`、
`benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json`、
`benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/mpi_identity_summary.json`
和 `benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/canonical_benchmark_manifest.json`。
Task034 的非零衍射级与复振幅保存在 Case093 heavy/compact records；本表只
登记跨全部固定网格都具有统一 authority 的总量、零级、规模和资源字段。

### 1.2.2 Hybrid FEM–Modal

Hybrid 把上下短 3D FEM 区保留为完整 FE 矩阵，中间均匀长段改用二维本征模态传播。下表完整登记 Task034 固定几何中已经实际完成的 MPI8 M160 Hybrid shard；`pass only` 表示线性求解与本 shard 物理量有效，但缺少同网格 Full3D closure 或 M funnel，不能提升为最终基准。p4/h5 的 MPI4 M-funnel 在后表单独登记，不能用其 residual/peak 覆盖这里的 MPI8 行。

| Task / 模型 | p/h | local FE DoF（上下合计） | modal `2M` | total rows | R00 | Rtotal | Ttotal | Avolume | true residual | peak GiB | total s | 状态 / 说明 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Task034 Hybrid M160 | p2/h5 | 13,652 | 320 | 14,052 | `0.0890118197` | `0.0890210691` | `0.442586743` | `0.468392188` | `7.706079e-12` | 3.284866 | 96.2844 | `success`；同网格 Full3D closure |
| Task034 Hybrid M160 | p2/h3 | 68,396 | 320 | 68,796 | `0.00460111770` | `0.00461281990` | `0.583650940` | `0.411736240` | `6.710467e-12` | 4.695160 | 164.317 | `success`；同网格 Full3D closure |
| Task034 Hybrid M160 | p2/h2 | 180,696 | 320 | 181,096 | `0.00133309761` | `0.00134288473` | `0.599212676` | `0.399444439` | `2.239274e-11` | 11.305332 | 461.776 | `success`；同网格 Full3D closure |
| Task034 Hybrid M160 | p3/h10 | 7,194 | 320 | 7,594 | `0.0553792864` | `0.0553988021` | `0.406069310` | `0.538531887` | `1.377971e-12` | 2.867710 | 91.9203 | `controlled_negative`；formal closure 未通过 |
| Task034 Hybrid M160 | p3/h7.5 | 26,598 | 320 | 26,998 | `0.00307976491` | `0.00309064738` | `0.591159679` | `0.405749673` | `3.164220e-12` | 3.614460 | 117.671 | `success_with_qualifications`；固定-p等精度压缩 |
| Task034 Hybrid M160 | p3/h5 | 43,614 | 320 | 44,014 | `0.00108058359` | `0.00109009569` | `0.600622368` | `0.398287536` | `1.055473e-11` | 4.908238 | 143.515 | `success`；MPI identity authority |
| Task034 Hybrid M160 | p3/h3 | 223,770 | 320 | 224,170 | `0.000780309829` | `0.000789467334` | `0.602514979` | `0.396695554` | `6.718e-12` | 14.271553 | 661.410 | `success`；M funnel authority |
| Task034 Hybrid M160 | p3/h2 | 595,956 | 320 | 596,356 | `0.000755344038` | `0.000764466671` | `0.602690128` | `0.396545405` | `3.613e-11` | 49.641502 | 3,513.82 | `success_with_qualifications`；仅 shard pass，无 Full3D closure/M funnel |
| Task034 Hybrid M160 | p4/h10 | 16,216 | 320 | 16,616 | `0.00187215501` | `0.00188234769` | `0.596619395` | `0.401498258` | `2.135697e-12` | 3.517616 | 136.253 | `success` |
| Task034 Hybrid M160 | p4/h7.5 | 61,064 | 320 | 61,464 | `0.000793283227` | `0.000802464969` | `0.602429757` | `0.396767778` | `5.300110e-12` | 5.967117 | 279.377 | `success` |
| Task034 Hybrid M160 | p4/h5 | 100,520 | 320 | 100,920 | `0.000757187631` | `0.000766313235` | `0.602677530` | `0.396556157` | `4.082573e-12`（MPI8 same-grid authority） | 9.205917 | 412.422 | `success`；高阶同网格 closure |
| Task034 Hybrid M160 | p4/h3 | 522,136 | 320 | 522,536 | `0.000753065135` | `0.000762184540` | `0.602706301` | `0.396531514` | `2.924e-11` | 42.481407 | 3,662.69 | `success_with_qualifications`；仅 shard pass，无 Full3D closure/M funnel |

#### Hybrid 资源停止

| p/h | measured progress | measured peak | status |
|---|---|---:|---|
| p2/h1 M160 | local factors/Schur 完成并进入 field recovery；7200 s timeout | 95.878723 GiB | `timeout_during_field_recovery_no_official_solution` |

#### M funnel

| case | MPI | M | total rows | R / T / Avolume | R00 | true residual | peak GiB | total s | 相邻 M 最大总量差 |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| p3/h3 | 8 | 80 | 224,010 | `0.000789467335 / 0.602514979 / 0.396695555` | `0.000780309830` | `2.076e-11` | 12.737340 | 529.556 | baseline |
| p3/h3 | 8 | 120 | 224,090 | `0.000789467334 / 0.602514979 / 0.396695554` | `0.000780309829` | `6.972e-12` | 13.708720 | 567.573 | `1.103e-9` |
| p3/h3 | 8 | 160 | 224,170 | `0.000789467334 / 0.602514979 / 0.396695554` | `0.000780309829` | `6.718e-12` | 14.271550 | 661.410 | `8.570e-12` |
| p4/h5 | 4 | 80 | 100,760 | `0.000766313235 / 0.602677530 / 0.396556158` | `0.000757187631` | `5.182e-12` | 5.048573 | 558.967 | baseline |
| p4/h5 | 4 | 120 | 100,840 | `0.000766313235 / 0.602677530 / 0.396556157` | `0.000757187631` | `5.726e-12` | 5.497772 | 634.194 | `1.107e-9` |
| p4/h5 | 4 | 160 | 100,920 | `0.000766313235 / 0.602677530 / 0.396556157` | `0.000757187631` | `7.031e-12` | 5.961403 | 734.218 | `8.713e-12` |

#### MPI identity：p3/h5

| method | MPI | rows | peak GiB | core/total s | max physical drift | identity |
|---|---:|---:|---:|---:|---:|---|
| Full3D | 1 | 145,943 | 6.339725 | core `1050.519`；total历史未冻结 | `0` | pass |
| Full3D | 8 | 145,943 | 9.013885 | core `150.511` | `8.776e-13` | pass |
| Full3D | 16 | 145,943 | 11.358720 | core `72.971` | `8.706e-13` | pass |
| Full3D | 32 | 145,943 | 15.772570 | core `41.948` | `8.817e-13` | exploratory pass |
| Hybrid M160 | 1 | 44,014 | 1.244774 | total `431.072` | `0` | pass |
| Hybrid M160 | 8 | 44,014 | 4.900311 | total `144.692` | `3.852e-13` | pass |
| Hybrid M160 | 16 | 44,014 | 7.149570 | total `134.132` | `1.942e-13` | pass |
| Hybrid M160 | 32 | 44,014 | 12.087820 | total `201.097` | `1.488e-13` | exploratory pass |

**证据：** `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、Case092 compact fixture、Case093 fixed-geometry records。Full3D/Hybrid各方法内的fields、interfaces、orders、complex amplitudes、QEP beta和true residual也通过对应MPI identity Gate。

---

## 1.3 FEniCS 原始完整 FE 矩阵法：迭代求解

这些模型不做 cell-interior 静态凝聚。外层真实算子使用完整 FE 矩阵 `F`，并以 auxiliary-free DtN Schur `F-C H^{-1}D` 处理 80 个端口辅助量。这里的“凝聚”只针对小型 DtN 辅助块，不是 Task035b 的单元内部自由度凝聚。

### 1.3.1 Full 3D

#### Task027：固定 75D 粗空间 + physical z-slab Schwarz

| h (nm) | FE DoF | F NNZ | 外层方法 | iterations | full true residual | Rtotal | Ttotal | Avolume | solve / total | 峰值 RSS | 状态 |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 44,698 | 4,840,396 | 右 FGMRES100；16 slab；ILU1；两步 shifted-F 平滑；75D coarse | 1,201 | `9.8395e-7` | `0.0890216032` | `0.4425882752` | `0.4683901190` | `91.10 / 110.91 s` | `1.957 GB` | `success` |
| 3 | 198,438 | 21,167,444 | 同一算法规则 | 993 | `9.9326e-7` | `0.0046130324` | `0.5836533646` | `0.4117336036` | `317.85 / 361.74 s` | `5.070 GB` | `success` |
| 2 | 615,108 | 65,122,664 | 同一算法规则 | 1,804 | `9.9974e-7` | `0.0013429363` | `0.5992132418` | `0.3994438284` | `2179.96 / 2328.13 s` | `12.958 GB` | `success_with_qualifications`；内存通过、物理尚未跨网格收敛 |

#### Task030：compact physical-slab low-memory profile

| h (nm) | FE DoF | 外层方法 | iterations | full true residual | Rtotal | Ttotal | Avolume | 峰值 RSS | 相对 Task027 内存 | 状态 |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 44,698 | FGMRES90；ILU0 对称 pre/post；local shift；factor-only；75D coarse | 855 | `9.924905e-7` | `0.0890216035` | `0.4425882732` | `0.4683901222` | `1.687653 GB` | `-15.24%` | `success` |
| 3 | 198,438 | 同一算法规则 | 962 | `9.903890e-7` | `0.00461303218` | `0.58365335775` | `0.41173361173` | `3.792912 GB` | `-25.37%` | `success` |
| 2 | 615,108 | 同一算法规则 | 1,873 | `9.972228e-7` | `0.00134293442` | `0.59921323601` | `0.39944383222` | `9.374729 GB` | `-28.33%` | `success_with_qualifications`；慢但低内存 |

#### Task031：assembled-F-free、overlap 0.125 与 compact lifecycle

| h (nm) | FE DoF | 外层方法 | iterations | full true residual | Rtotal | Ttotal | Avolume | solve / total | simultaneous peak | 状态 |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 44,698 | Task030 PC + public matrix-free form action + overlap0.125 + compact lifecycle | 1,157 | `9.959903e-7` | `0.089021602568` | `0.442588275323` | `0.468390124569` | `350.851 / 374.342 s` | `1.619598 GiB` | `success_with_qualifications` |
| 3 | 198,438 | 同一算法规则 | 1,994 | `9.973853e-7` | `0.004613031629` | `0.583653357934` | `0.411733610310` | `2311.581 / 2370.351 s` | `3.474346 GiB` | `success_with_qualifications` |
| 2 | 615,108 | 同一算法规则 | 1,977 | `9.998454e-7` | `0.001342934186` | `0.599213235569` | `0.399443835926` | `11982.581 / 12173.086 s` | `7.897675 GiB` | `success_with_qualifications`；强内存成功但约 3.33 h |

**显著衍射级状态：**Task027–031 的正式总结以 total R/T/A 和 80 模态身份为主，未在 summary 中保存 Task035b 的 12 通道表；后续需要从 heavy records 自动回填各级功率和复振幅。

### 1.3.2 Hybrid

当前没有“原始完整 FE 局部矩阵 + Hybrid + 正式迭代求解器”的成功资格化模型。

| 模型 | 当前状态 | 说明 |
|---|---|---|
| Hybrid iterative | `not_run / not_qualified` | Task032–033 的 Hybrid 主线采用直接法；迭代 Hybrid 需要独立接口/模态块预条件和完整通道闭合。 |

---

## 1.4 静态凝聚法：直接求解

静态凝聚先在每个高阶单元内部消去只属于本单元的 cell-interior 自由度，只把 edge/face trace 送入全局矩阵；求解后再逐单元恢复完整场。它不是近似删自由度，而是精确块消元。Task035b 当前正式实现只资格化规则、轴对齐、仿射六面体。

### 1.4.1 Full 3D：总量、矩阵与资源

| 模型 | 网格 / 空间 | Full3D-equivalent DoF | active rows incl. DtN | matrix NNZ | factor NNZ | R00 | Rtotal | Ttotal | Aclosure | true residual | 峰值 / 主要时间 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| p4/h10 global | `(6,3,14)`；global p4 | 53,084 | 21,824 | 8,184,464 | 40,151,936 | `0.001872161` | `0.001882317` | `0.596619520` | `0.401498163` | `2.35e-11` | peak `历史未冻结`；build `35.64 s`；MUMPS setup `13.36 s` | `success`，但未达高阶收敛 |
| p5/h10 global | `(6,3,14)`；global p5 | 101,815 | 35,000 | 20,140,928 | 101,062,900 | `0.000785714` | `0.000794886` | `0.602483954` | `0.396721160` | `1.25e-11` | peak `历史未冻结`；build/setup/solve `24.72/36.48/0.077 s` | `success`，接近 p6 |
| p6/h10 global reference | `(6,3,14)`；global p6 | 173,802 | 51,272 | 41,989,040 | 202,441,352 | `0.000753761` | `0.000762881` | `0.602701634` | `0.396535485` | `1.26e-11` | build/setup/solve `102.32/102.54/0.167 s`；隔离 direct peak `15.964 GiB` | `success`；best available same-code discrete reference |
| global p6/h15 | 粗化网格；global p6 | 84,492 | 24,704 | 19,207,136 | 59,616,320 | 见 record | 见 record | 见 record | 见 record | `7.87e-12` | pair peak `12.000 GiB`；build/setup/solve `396.93/21.53/0.057 s` | `controlled_negative`；弱通道不满足 |
| fixed p5-trace/p6-interior h15 | `(6,2,10)` | 74,890 | 16,880 | 9,195,812 | 27,916,600 | `0.000755888314` | `0.000765024318` | `0.602685146796` | `0.396549828886` | `8.83e-12` | canonical direct MPI8 peak `5.803 GiB`；cold/warm non-KSP `19.242/6.141 s` | `controlled_negative`；总量通过、通道失败 |
| fixed p5-trace/p6-interior h14 | `(6,2,11)` | 82,315 | 18,500 | 10,104,512 | 31,347,000 | 见 record | 见 record | 见 record | 见 record | `4.45e-12` | `6.376 GiB`；build/setup/solve `62.312/11.474/0.0315 s` | `controlled_negative`；z 方向正信号但不完整 |
| fixed p5-trace/p6-interior h13 | `(6,2,12)` | 89,740 | 20,120 | 11,013,212 | 36,273,200 | `0.000756117570` | `0.000765246512` | `0.602682451672` | `0.396552301816` | `5.81e-12` | accuracy peak `6.411 GiB`；canonical setup peak约 `5.03 GiB`；cold/warm non-KSP `19.410/6.696 s` | `controlled_negative`；当前预算内最强点 |

**峰值内存口径说明：**p4/h10与p5/h10的同表记录保存了rows、NNZ、factor、物理量和阶段时间，但没有冻结单独的per-model峰值内存；因此显式写为`历史未冻结`，不能空着也不能由p5/p6 pair peak反推。p6/h10同时有隔离direct peak `15.964 GiB`和后续Task035c MPI8 static Full3D peak `14.722 GiB`两套不同source/生命周期authority，二者不能混写。

### 1.4.1.1 12 个显著通道功率

#### 反射功率

| 模型 | R(0,0) | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | Rtotal |
|---|---:|---:|---:|---:|---:|---:|---:|
| p6/h10 reference v1 | `7.53761220068e-4` | `6.66930965425e-6` | `1.47769085130e-6` | `2.67523960967e-7` | `7.45730053677e-8` | `6.26354242222e-7` | `7.62881475133e-4` |
| fixed h15 | `7.55888313624e-4` | `6.68359026100e-6` | `1.48261801533e-6` | `2.60181249500e-7` | `7.78127363894e-8` | `6.27007582029e-7` | `7.65024318140e-4` |
| fixed h13 | `7.56117570116e-4` | `6.67510914774e-6` | `1.47657836307e-6` | `2.72339140129e-7` | `7.35017831938e-8` | `6.26378308638e-7` | `7.65246511550e-4` |

#### 透射功率

| 模型 | T(0,0) | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | Ttotal | Aclosure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| p6/h10 reference v1 | `6.02673872347e-1` | `2.17816739855e-5` | `2.95984139513e-6` | `4.37288897207e-7` | `2.11920825720e-7` | `2.36201044924e-6` | `6.02701633986e-1` | `3.96535484539e-1` |
| fixed h15 | `6.02657398112e-1` | `2.18040789857e-5` | `2.94463911877e-6` | `4.12666159013e-7` | `2.15875293566e-7` | `2.36220894231e-6` | `6.02685146796e-1` | `3.96549828886e-1` |
| fixed h13 | `6.02654698626e-1` | `2.17753807955e-5` | `2.95868518886e-6` | `4.35489199428e-7` | `2.12204228069e-7` | `2.36225288824e-6` | `6.02682451672e-1` | `3.96552301816e-1` |

### 1.4.1.2 显著通道复振幅

#### 反射复振幅 `r(m,0)`

| 模型 | r(0,0) | r(-1,0) | r(-2,0) | r(-4,0) | r(-5,0) | r(-7,0) |
|---|---|---|---|---|---|---|
| p6/h10 reference v1 | `-2.52523043536e-2 +1.07741517021e-2i` | `-1.03270771592e-3 +7.67833921753e-4i` | `4.94231617062e-4 -2.05515769764e-4i` | `2.10223336125e-4 -4.97304361281e-5i` | `-9.81780791859e-5 -6.53550324587e-5i` | `-5.05209111247e-4 -2.60888617007e-5i` |
| fixed h15 | `-2.52679489973e-2 +1.08360078947e-2i` | `-1.03216329353e-3 +7.70869059128e-4i` | `4.94645323058e-4 -2.06840346497e-4i` | `2.06054361758e-4 -5.41082464827e-5i` | `-1.00138975344e-4 -6.69829310030e-5i` | `-5.05459008402e-4 -2.63630100680e-5i` |
| fixed h13 | `-2.52711749561e-2 +1.08390629878e-2i` | `-1.03272204657e-3 +7.68751847368e-4i` | `4.93434424824e-4 -2.06901901623e-4i` | `2.12784701368e-4 -4.72186363878e-5i` | `-1.00926387945e-4 -5.93655036535e-5i` | `-5.05224210350e-4 -2.59847102187e-5i` |

#### 透射复振幅 `t(m,0)`

| 模型 | t(0,0) | t(-1,0) | t(-2,0) | t(-4,0) | t(-5,0) | t(-7,0) |
|---|---|---|---|---|---|---|
| p6/h10 reference v1 | `6.31378703348e-1 +4.73020981038e-1i` | `2.09101338530e-3 -1.02337986284e-3i` | `-6.97002780558e-4 +2.97942080721e-4i` | `-2.62132207531e-4 +8.74322690375e-5i` | `1.34032696607e-4 +1.47005784286e-4i` | `9.81221050834e-4 -8.72374996020e-5i` |
| fixed h15 | `6.31685464148e-1 +4.72593246678e-1i` | `2.09051124045e-3 -1.02712258858e-3i` | `-6.91980021337e-4 +3.04622473840e-4i` | `-2.49901308066e-4 +9.80178800675e-5i` | `1.39598241988e-4 +1.44313125131e-4i` | `9.81176181394e-4 -8.82042041001e-5i` |
| fixed h13 | `6.31731380082e-1 +4.72528917690e-1i` | `2.09015756157e-3 -1.02436264988e-3i` | `-6.96291673953e-4 +2.99225357519e-4i` | `-2.61125984121e-4 +8.86378025759e-5i` | `1.34725687090e-4 +1.46551622295e-4i` | `9.81167544398e-4 -8.84024041667e-5i` |

### 1.4.1.3 未通过项必须写具体数值

| 模型 | 未通过的功率 | 未通过的复振幅 | 结论 |
|---|---|---|---|
| fixed h15 | `R(-2)=1.482618e-6`、`R(-4)=2.601812e-7`、`R(-5)=7.781274e-8`、`T(-2)=2.944639e-6`、`T(-4)=4.126662e-7`、`T(-5)=2.158753e-7` 未落入 reference v1 band | `r(-4)`、`r(-5)`、`t(-2)`、`t(-4)`、`t(-5)` 未通过 | `controlled_negative`；总 R/T/A 接近参考不代表弱通道收敛 |
| fixed h13 | `T(-4)=4.354892e-7` 与 `R(-4)=2.723391e-7` 未通过 | `r(-4)=2.127847e-4-4.721864e-5i`、`r(-5)=-1.009264e-4-5.936550e-5i` 未通过 | `controlled_negative`；当前 `<=90k` 最强点仍非同误差候选 |

### 1.4.2 Hybrid

Review V3 已把 cell-interior 静态凝聚接入 Task032/033 Hybrid 的上下局部
三维 FEM 端区。static 路径与原始 Hybrid 路径达到逐通道等价，但 p2/h5
static Hybrid 没有与同离散 static Full3D 完成显著通道闭合。因此当前有
正式实测的工程能力和 controlled negative，没有 Hybrid 物理成功模型。

| 模型 | local FE / trace / total rows | matrix / factor NNZ | R00 / R / T / Aclosure | residual / fields | peak / total | 状态 |
|---|---:|---:|---|---|---:|---|
| p2/h5 static Hybrid M120 | 6,826 full FE/side；4,800 active trace/side；9,920 total | 976,400 / 5,968,912 pair | `0.089011819673 / 0.089021069106 / 0.442586742743 / 0.468392188151` | `3.18e-12`；full/interior residual pass | 2.747 GiB / 114.21 s | `controlled_negative`；static-equivalence 12/12+12/12，Full3D closure 3/12+2/12 |
| p2/h5 static Hybrid M160 | 6,826 full FE/side；4,800 active trace/side；10,000 total | 976,400 / 5,986,184 pair | `0.089011819673 / 0.089021069106 / 0.442586742743 / 0.468392188151` | `3.45e-12`；interface E/H 与 middle plane pass | 3.308 GiB / 186.36 s | `controlled_negative`；M120→M160 12/12+12/12，但 Full3D closure 3/12+2/12 |

M160 的相对 `1e-3` 失败功率为
`T(-5,0)=1.667074e-7`、`T(-4,0)=3.172633e-7`、
`T(-2,0)=4.723171e-7`、`T(-1,0)=5.146400e-6`、
`R(-7,0)=2.232991e-6`、`R(-5,0)=1.984830e-7`、
`R(-4,0)=9.446546e-8`、`R(-2,0)=7.121444e-8`、
`R(-1,0)=6.647511e-6`；复振幅还在 `T(-7,0)` 失败。对应 Full3D
值、复振幅、绝对差和冻结限值见
`benchmarks/cases/095_high_order_local_hp_resource_envelope/records/hybrid_static_condensation_h1a_mpi8_v1.json`。
H1-B p2/h3 为 `not_run_by_review_prerequisite`，不是普通待运行项。

#### Task036 direct Hybrid closeout

Task036 先修复 Full3D/Hybrid 共用的投影、界面牵引、beta 身份、near-degenerate
检测、trace alias、MUMPS 计数、对象生命周期和资源语义，再追查低维 direct Hybrid
为什么不能在小掠射角/P 偏振下复现 Full3D 全通道。通俗地说，模态传播核心本身能工作，
但低维端口没有装下完整的界面电场和磁牵引信息；继续增加同一类模式没有得到生产解。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task036_original_physical_qep_M120_M240` | frozen Task036 SHA `7a0334008dc9bbdeefe55dd0ffa535cc756e661c` | p5/h10 Full3D reference 与 direct Hybrid 接口 | physical-QEP port，M120/M240 | 完整 joint-Cauchy 与全通道合同未闭合；F2/F5 P 的 M120 energy closure 分别 `1.00994e-3`、`2.56646e-5`，均高于 `1e-5` | `CONTROLLED_NEGATIVE_CLOSED`；complete port not production-qualified | [`final_summary.md`](task036_forward_solver_bugfix_hardening/outcomes/final_summary.md) |
| `task036_M120_long_range_modal_core` | frozen exact operator audit | 40/60/100 nm 长程传播段 | selected M120 R/W space | exact FE 与 modal selected operator 误差约 `1.59e-11–1.95e-11` | `retained`；只证明 selected-space propagation，不证明端点完整 | 同上；V8 |
| `task036_strong_trace_M120_A004S` | Task036 measured research result | p5/h10、MPI8 direct | M120 strong trace | E jump `4.588e-15`；energy `1.531666e-5 > 1e-5`；fixed channels `77/96`；峰值 `7.893 GiB` vs Full3D `10.549 GiB` | `RESEARCH_ONLY_CONTROLLED_NEGATIVE`；19项失败 | [`fix_report.md`](task036_forward_solver_bugfix_hardening/outcomes/fix_report.md)；V8 |
| `task036_exact_FE_trace_chain_oracle` | frozen Task036 exact audit | one-cell two-port Schur、endpoint Cauchy、serial/MPI trace-chain | full-space direct FE trace-chain | 域分解、恢复与 direct algebra 对齐；无 scalable-resource claim | `RESEARCH_ONLY_CORRECTNESS_ORACLE`；不是 scalable solver | [`review_report_v8.md`](task036_forward_solver_bugfix_hardening/review_report_v8.md) |
| `task036_B1_discrete_bloch_d_le_360` | frozen research branch | Full3D/Hybrid interface port | low-dimensional discrete-Bloch，`d<=360` | 未满足完整 production contract | `CONTROLLED_NEGATIVE_CLOSED` | 同上 |
| `task036_C1b_C1c` | 用户撤销授权 | teacher/POD/compressed-port 路线 | 96-RHS teacher、POD、actual compressed candidate | 没有 live teacher 或 PDE 结果 | `CANCELLED_NOT_RUN` | 同上 |
| `task036_0p7nm_2TiB` | planning boundary | 目标 0.7 nm | 整作业内存上限 2 TiB | 没有通过精度与资源 Gate 的 solver；实测/资格化结果为 `not_run` | `NOT_SOLVED` | [`final_summary.md`](task036_forward_solver_bugfix_hardening/outcomes/final_summary.md) |

选择性整合身份为 Group 1 `7735a2617d18fe5f869331a90d47ec16632fd8d3`、Group 2
`a741ad1b5cfb579e2667600bcc6497ec5c4f23d9`，Group 3
`4c9e1b9cedd4b04d65824698202c9fff96f3a0dc`。在 Task036 结项时，Task037 空分支已从
已推送 master `b615a130d7c34060a3445c352c1f683bbf3aa23f` 创建并推送；该历史占位
现由下方 1.5 的 Task037 V7 当前结论替代，不应再解读为 Task037 未定义。

---

## 1.5 静态凝聚法：迭代求解（待定）

Task037 证明了一个可复用但必须显式 opt-in 的 p6/h10 Full3D 迭代基线：
matrix-free fine action、80-mode Matrix-free DtN component、owner-local
static-Schur 与 M3a physical-slab/75D coarse 组合均有正式证据。它不是 ordinary
default，也不是 `0.7 nm` resource-scalability qualification。

| Model ID | 方法与规模 | 结果 | 状态 |
|---|---|---|---|
| `task037_e0_matrix_free_dtn` | 80-mode Matrix-free DtN；p6/h10；MPI1 | 80/80；primary C/D `0/0`；global A/F `false/false`；action/recovery 约 `1e-15` | component pass；ordinary unchanged |
| `task037_m3a_opt_in` | owner-local static-Schur；75D coarse；16 slabs；overlap `.125`；MPI1/2/4/8 | MPI4 full residual四项均 `<=1e-6`；12/12 power、12/12 amplitude；official true | research baseline；不是 default |
| `task037_canonical_active_full` | canonical active/full comparator | relative L2 `1.2553897989392794e-06` / `7.880394014572244e-07` | pass at `1e-5` |
| `task037_A_B2_B4_C_D_R7_p4_F_E` | 已运行的候选与关闭路线 | negative、plateau、partial 或 capacity `6/6` fail | controlled negatives；不生产化 |

证据绑定 reviewed source `d8b16c349f7726b4873ce1932668c12a1ba78926` 与 final
numerical source `0fcf08a3f09e3beb137212d41f411823cb2e24e8`。详见
[`Task037 summary`](task037_static_condensed_full3d_iterative/outcomes/summary.md)
和 Case100 compact records。

### 1.5.1 Full 3D

M3a 是 explicit opt-in research baseline；约 `91.4M` p6 local factor NNZ，不能
据此宣称 `0.7 nm` scalable solver。ordinary solver profile 与普通 defaults 不变。

### 1.5.2 Hybrid 与 Task37b

Task037b 登记一个冻结但仅供研究使用的 Hybrid iterative capability。它不是 ordinary
direct/default，也不是 production service；入口必须显式 opt-in，且改变参数后必须重新
取得 source、数值、物理、资源和独立 checker evidence。

| Model ID | source / 冻结域 | 数值与物理结果 | 资源与身份 |
|---|---|---|---|
| `task037_full3d_m3a_iterative_research` | Task037 M3a；p6/h10；Full3D；explicit opt-in | Full3D iterative baseline；ordinary default unchanged | `research_only`；不作 0.7 nm qualification |
| `task037b_frozen_m10_hybrid_iterative` | historical implementation `ea132d8a31e5ccd6c45fb90bbb9b5f676cd78b0e`；formal source `b291f3dfdf5f0064ff243038f6809172f811d7aa`；p6/h10、13.5 nm、S、10°、M120/240、MPI8 | `792` iterations；reported/global/bottom/top/modal residual `3.578062165607276e-09 / 3.578062144715876e-09 / 4.921856578759462e-09 / 2.6635965562403923e-09 / 1.4561321294580367e-15`；traction bottom/top `4.820141813913522e-09 / 2.6635965562403923e-09`；physics、canonical、`12+12` 通过 | process-tree RSS `5.8775 GiB`；swap `0`；`research_only`、explicit opt-in、ordinary default unchanged；0.7 nm `not_qualified` |

M10 的 exact action、fixed endcap ILU(0)+DtN Woodbury、recovery、own-physics、canonical
和生命周期证据由 Case101 两份 compact record 绑定；raw artifact 不进入 Git。

---

## 1.6 自适应求解

### 1.6.1 Full 3D

当前没有达到 production qualification 的完整自动 h/p 自适应模型。

| 路线 | 已完成内容 | 未完成内容 | 状态 |
|---|---|---|---|
| Task035 tetra local-h | 真实 DWR、周期闭合、一次局部 h 细化和固定细化网格 p6 对照 | 同一 patch 上 h/p 公平竞争、`<=90k` 最终候选 | `research evidence / incomplete` |
| Task035b structured-hexa directional-h | h15→h14→h13 的 z 向全共形细化，h13 达到 89,740 DoF | 12/12 通道闭合；局部 hanging-node hexa h 路径 | `controlled_negative` |
| selective p6 trace | fixture 中 active-row 省略、Floquet pullback、MatShell action | actual enriched residual、channel DWR、orbit selection、正式 PDE | `incomplete` |
| Task035d exact-sequence local-p + true local-h | capability/resource pass；h15 top-air `82,925 DoF / 18,470 rows / 7.50068 GiB / 6/12+6/12`；left-grating `88,915 / 21,650 / 8.06120 GiB / 4/12+6/12` | accuracy fail；automatic cycles 1–4 not completed；未形成 production hp candidate | `PARTIAL_WITH_CONTROLLED_NEGATIVES` |
| Task035e reference-blind multilevel hp | sealed p6/h10、h7.5、h5 certification 身份/Gate；Path A current+p/h shadow；59-goal endpoint/cellwise DWR；离线 p/h marking；一次 four-cell 与一次 single-cell selected-p actual candidate | 两条 candidate 的数值/资源均通过，但 action prediction 分别仅19/59与0/59 factor-two；single-cell 排除 grouped interaction 解释，cellwise-p quantitative predictor 已关闭；selected-h、cycle 1、Path B v28、hidden final audit 和 Hybrid 均未运行 | `PARTIAL_CELLWISE_P_PREDICTOR_CLOSED` |

### 1.6.2 Hybrid

| 状态 | 说明 |
|---|---|
| Task035d `not_run_full3d_hp_gate_failed` | Full3D 候选未通过 12/12+12/12，Hybrid 不得提供精度信用。 |
| Task035e `not_run` | 只有 hidden audit 通过的 Full3D blind candidate 才能进入 static Hybrid M120；cycle-0 selected-p candidate 已运行但被 action-level effectivity Gate 拒绝，因此仍无 Hybrid 结果。 |

---

# 3. Task000–Task035e 逐任务统一总账

> 本节编号固定为 `3.1 Task000` 至 `3.40 Task035e`。每个 Task 先用通俗语言回答“研究什么、为什么研究、改变了哪段流程、最终结论是什么”，再用同一表头登记身份、物理、离散、算法、规模、总量、逐级结果、资源和处置。历史没有保存的字段统一写“历史未记录”，不填 0、不由功率反推复振幅。早期 `linear_system_relative_residual` 明确标成 legacy explicit residual，不冒充 Task035b–Task035d 的 full explicit true residual。

统一表头如下，后续 checker 会检查每个 Task 都存在这一表头：

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `schema_only` | source SHA、record/hash | 几何、材料、波长、入射、cell、p/h | Full3D/Hybrid、direct/iterative、DoF/rows/NNZ | R00/R/T/A/residual、12 通道/幅值、时间/内存 | 实际未通过值与状态 | tracked path |

## 3.1 Task000

研究对象是仓库结构和任务留痕流程，目的不是求解 PDE，而是建立 `task → outcomes → review` 闭环。它改变了协作、审查和轻量证据入库方式；最终形成可追溯工作流，但没有物理 benchmark。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task000_review_code_workflow` | branch=`codex/review_code`；精确 source SHA 历史未记录 | 无物理模型；离散不适用 | 无 PDE；DoF/rows/NNZ 不适用 | R/T/A、残差、逐级、时间和内存均 `not_run` | `documentation_success`；早期代码判断被 Task001–004 取代 | `docs/task000_review_code/outcomes/summary.md` |

## 3.2 Task001

研究对象是早期 Stage4 flat-layer 与 zero-contrast 小模型，目的是固定 13.5 nm 和 Si 复折射率入口并区分 sanity 与 benchmark。流程加入 `numerical_sanity_only`、材料标签和功率来源说明；两个极粗网格模型一致，只能算工程 smoke。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `Stage4A_flat_layer` | source SHA/geometry hash 历史未记录 | 13.5 nm normal-s；Si substrate；p1 h50 hexa，12 cells | 原始 Full3D direct；75 FE DoF | R/T/A=`0.999843746435/0.000132382785/2.387078e-5`；只启用零级，复振幅历史未记录；8.981 s，281.125 MB | `engineering_success; numerical_sanity_only` | `docs/task001_stage4_validation_cleanup/outcomes/summary.md` |
| `Stage4B_zero_contrast` | 同一历史数据族 | block tag 保留但 `n_grating=1+0j`；27 cells | 原始 Full3D direct；144 FE DoF | 与 flat-layer 同一 R/T/A；8.537 s，280.5 MB；residual 历史未记录 | `engineering_success; numerical_sanity_only` | `docs/task001_stage4_validation_cleanup/outcomes/metrics.csv` |

## 3.3 Task002

研究对象是 flat-layer、zero-contrast 与 real-Si block 的 R/T/A、probe、net-flux 和体吸收接口。目的是建立多口径一致性 Gate；九个模型全部暴露错误归一化/参考面，物理数值不可用，但成功定位了问题并推动 Task003/007 修正 official 口径。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `flat_layer_h5` | source SHA 历史未记录；Task002 raw summary | 13.5 nm normal-s；p1 h5 hexa；尺寸历史表见 evidence | Full3D direct | port R/T/A=`0.0184287/1.0440977/-0.0625264`，Avolume=`0.0291011`，closure mismatch=`0.0916275`；逐级/幅值历史未记录 | `diagnostic_success; physical_gate_failed`；R/T 口径被 Task003/007 取代 | `docs/task002_rta_output_volume_absorption/outcomes/summary.md` |
| `real_si_block_h3` | 同一数据族 | Si substrate+block；62,475 cells，197,136 DoF | Full3D direct | R/T/Aport=`0.00188633/1.09051232/-0.0923987`，Avolume=`0.0430043`，mismatch=`0.135403`；2623 s，13,213 MB | `diagnostic_success; physical_gate_failed`；失败值不得作参考 | `docs/task002_rta_output_volume_absorption/outcomes/metrics.csv` |

## 3.4 Task003

研究对象是 lossy flat layer 的解析闭合和 10 nm 小单元收敛，目的是修复 Task002 的吸收归一化、透射参考面和 DtN traction 符号。流程确立 DtN port R/T 与 Avolume 主口径，probe/net-flux 降为诊断；小单元机器精度闭合，但不是目标光栅基准。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `flat_layer_auto_h5` | source SHA 历史未记录 | 100×100×150 nm；13.5 nm normal-s；p1 h5 hexa | Full3D direct；39,270 FE + 708 modal rows | R/T/A=`0.0216956/0.918733/0.0595716`，closure `-5.1e-14`，legacy residual `9.26e-11`；12 通道/幅值历史未记录 | `engineering_success; not_converged_reference`；仍约2.17%伪反射 | `docs/task003_stage4_power_consistency/outcomes/summary.md` |
| `small_cell_h1` | 同一算法版本 | 10×10×10 nm；p1 h1；1000 cells | Full3D direct；3630 FE + 4 modal rows | R/T/A=`6.61569e-5/0.99167204/0.00826180`，closure `-2.22e-15`，legacy residual `6.61e-14`；19.9 s | `engineering_success`；仅零级传播 | `docs/task003_stage4_power_consistency/outcomes/small_cell_metrics.csv` |

## 3.5 Task004

研究对象是 10 nm flat-layer 的 p1/p2 收敛、MPI1/4/8 一致性和 Stage1–4 smoke。目的是冻结小规模回归基线；流程加入统一 residual、MPI delta 和阶段 smoke，最终成为长期基础设施，但不代表目标光栅收敛。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `conv_p2_h1p5` | source SHA 历史未记录 | 13.5 nm normal-s；10 nm flat layer；p2 h1.5 hexa | Full3D direct；10,740 DoF | R/T/A=`1.240889e-6/0.991537318/0.008461442`；legacy residual `2.997e-13`；21.60 s，548.5 MB；仅零级 | `production_success`（回归基线） | `docs/task004_small_cell_p_convergence_mpi_regression/outcomes/metrics.csv` |
| `mpi_p1_h1p5_and_p2_h3` | 同一 tracked metrics | 同一小单元 | MPI1/4/8 direct | official R/T/A delta `<1e-8`，closure `<1e-10`；PSS/cgroup 历史未记录 | `infrastructure_success` | `docs/task004_small_cell_p_convergence_mpi_regression/outcomes/mpi_consistency.csv` |
| `stage1_to_stage4_smoke` | regression metrics | 极粗阶段模型 | serial/MPI staged smoke | 全路径通过；Stage2B/2C 不是精度 benchmark | `infrastructure_success` | `docs/task004_small_cell_p_convergence_mpi_regression/outcomes/regression_metrics.csv` |

## 3.6 Task005

研究对象是 100×100×150 nm、50×50×50 nm Si block 的 p2 full-matrix direct/OOC 资源边界，目的是区分矩阵存储与 LU fill。流程新增 assemble-only、default direct、OOC 和失败边界；h5 可完成，h4 在 factorization 失败。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `assemble_p2_h2` | source SHA 历史未记录 | 13.5 nm normal-s；规则 hexa p2；195,075 cells | MPI8 Full3D assemble-only；4,764,870 rows，523,627,904 NNZ | 无 official R/T/A；AIJ估计11.74 GiB | `diagnostic_success`；direct/OOC RAM 仅预测，未实测 | `docs/task005_stage4_real_grating_memory_estimation/outcomes/assemble_matrix_scale.csv` |
| `direct_p2_h5` | Task005 record family | 同一模型；p2 h5 | MPI8 MUMPS；301,648 rows | legacy residual `8.90e-12`；R/T/A=`0.00019604/0.90542068/0.09438328`；RSS upper 18.67 GiB，698.63 s；逐级历史未记录 | `diagnostic_success`；非最终 benchmark | `docs/task005_stage4_real_grating_memory_estimation/outcomes/direct_default_scale.csv` |
| `direct_or_ooc_p2_h4` | failure boundary | p2 h4 | direct / OOC | direct factor stage signal 9；OOC `INFOG(1)=-90`，调参90 min超时且 scratch约30.09 GiB | `controlled_negative`；fill-in主导 | `docs/task005_stage4_real_grating_memory_estimation/outcomes/failure_boundary.md` |

## 3.7 Task006

研究对象是同一 100 nm-period block 的 70 nm reduced-height 资源模型，目的是检验缩短端口距离并测真实 process-tree memory。流程加入独立采样、MPI1/8 与 tuned OOC；资源诊断成功，但物理量不能代替 150 nm 模型。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `reduced70_p2_h5_np8_direct` | source SHA 历史未记录 | 70 nm reduced-height；p2 h5；5,600 hexa cells | Full3D direct；142,188 FE，142,896 rows，18,803,220 NNZ | R/T/A=`0.000707967/0.964603346/0.034688687`；legacy residual `1.21e-12`；process-tree peak 13.646 GiB，119.94 s | `diagnostic_success` | `docs/task006_reduced_height_grating_convergence_memory/outcomes/memory_profile_summary.csv` |
| `reduced70_p2_h3_ooc` | failure record | p2 h3；759,698 rows，91,259,656 NNZ | MUMPS OOC | `INFOG(1)=-90`，无 official R/T/A | `controlled_negative` | `docs/task006_reduced_height_grating_convergence_memory/outcomes/summary.md` |
| `reduced_vs_original` | comparison CSV | 70 vs 150 nm domain | direct comparison | R `0.000708 vs 0.000196`，T `0.964603 vs 0.905421`，A `0.034689 vs 0.094383` | `negative_result_success`；证明 reduced-height 非物理替代 | `docs/task006_reduced_height_grating_convergence_memory/outcomes/reduced_vs_original_domain_comparison.csv` |

## 3.8 Task007

研究对象是 100 nm-period Si block 在 70/110/130/150 nm 域高下的 official DtN modal R/T，目的是替换不可靠 probe 并量化端口参考面影响。流程正式冻结 modal amplitudes + Avolume；能量闭合通过，但域高依赖说明这些不是 continuum 解。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `height70_p2_h5_np8` | source SHA 历史未记录 | 13.5 nm normal-s；p2 h5；5,600 cells | Full3D direct；142,188 FE + 708 aux | R/T/A=`0.0007079669/0.9646033456/0.0346886875`；closure `7.55e-15`；legacy residual `1.84e-12`；89.70 s，max-rank RSS 2.207 GB | `production_success`（当时口径） | `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_official_rta.csv` |
| `height150_p2_h5_np8` | 同一数据族 | 12,000 cells | Full3D direct；300,940 FE，301,648 rows，35.634M NNZ | R/T/A=`0.0001960416/0.9054206822/0.0943832762`；closure `-3.08e-14`；617.12 s，max-rank RSS 2.620 GB | `success_with_qualifications`；R00/12通道/幅值历史未记录 | `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_resource.csv` |

## 3.9 Task008

研究对象是实际 `F-STAGE4-S` 固定目标：50×25×140 nm、17×25×120 nm Si block、13.5 nm、80°斜入射 s 偏振。目的是冻结 direct reference；流程加入双 Floquet 相位、p1/p2 h 扫描和内存 Gate，p2/h2 成为 best available discrete reference。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `target_p2_h2_direct_reference` | source SHA/geometry hash 历史未记录；raw summary tracked | `F-STAGE4-S`；hexa p2 h2；24,570 cells | MPI8 MUMPS；615,108 FE，615,188 rows，65,448,472 NNZ | R/T/A=`0.001342932846/0.599213229444/0.399443837710`；closure `-1.066e-14`；legacy residual `1.345e-11`；1665.78 s，RSS upper 20.533 GiB；12通道/幅值历史未记录 | `production_success; best_available_discrete_reference`，非 continuum | `docs/task008_70nm_official_convergence_benchmark/outcomes/raw_runs/direct_p2_p2_h2p0/run_summary.json` |
| `target_p2_h1p5_direct` | failure record | 1,347,314 rows，142.656M NNZ | MPI8 MUMPS | KSP setup signal 9；最后 RSS upper 14.37 GiB；无 official output | `controlled_negative` | `docs/task008_70nm_official_convergence_benchmark/outcomes/failure_boundary.csv` |
| `target_p2_h1_assemble` | failure record | 4,379,752 rows，459.939M base NNZ | assemble-only | base assembly后2400 s超时并大量 swap | `controlled_negative` | `docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md` |

## 3.10 Task009

研究对象是目标系统上的黑盒 PETSc Krylov/PC 组合，目的是找 factor-free 低内存法。流程建立 profile 筛选和“不收敛不输出 official R/T/A”；所有组合失败。最终 review 纠正了一个关键口径：`0.00355849` 是 KSP ratio，true relative residual 是 `0.161741`。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `iter_gmres_jacobi_p2_h1p5` | source SHA 历史未记录；final review 纠偏 | `F-STAGE4-S`；p2 h1.5；1,347,314 rows，142.656M NNZ | MPI8 assembled GMRES/Jacobi，1000步 | terminal KSP ratio `0.00355849`，true relative residual `0.161741`（limit `1e-6`）；solve/total `360.86/551.03 s`，RSS upper 13.992 GiB；无 official R/T/A/通道 | `controlled_negative`；不得再写成 true residual `3.558e-3` | `docs/task009_iterative_solver_profile_screening/outcomes/iterative_failure_cases.csv` |
| `black_box_profile_family` | profile summary | p2 h5/h4 | GMRES/FGMRES/BiCGStab + Jacobi/BJacobi/ASM/ILU/LU/GAMG/FieldSplit | 多数1000步停滞或恶化；无 official output | `negative_result_success`；排除黑盒 lane | `docs/task009_iterative_solver_profile_screening/outcomes/summary.md` |

## 3.11 Task010

研究对象是 MUMPS-BLR 和 shifted/positive Maxwell 原型，目的是检验近似直接法与最小物理 PC。BLR 可控但仍持有 MUMPS factors；shifted lane 失败，不能称低内存 iterative。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `fgmres_mumps_blr_1e-5_p2_h2` | source SHA 历史未记录 | `F-STAGE4-S`；615,188 rows，65.448M NNZ | MPI8 FGMRES + MUMPS-BLR，4 iterations | true residual `2.08534e-8`；R/T/A=`0.001342932839/0.599213228940/0.399443837551`；closure `-6.701e-10`；17.853 GiB，1357.57 s | `engineering_success; explicit_fallback`；不是 factor-free | `docs/task010_shifted_maxwell_preconditioner/outcomes/blr_profile_summary.csv` |
| `blr_p2_h1p5` | failure record | 1.347M rows级 | MUMPS-BLR | setup signal 9，最后RSS upper 13.805 GiB | `controlled_negative` | `docs/task010_shifted_maxwell_preconditioner/outcomes/preconditioner_failure_cases.csv` |
| `shifted_positive_asm_ilu` | profile summary | p2 h5/h4 | assembled FGMRES | 1000步失败；最佳 h4 positive+ASM/LU true residual约`0.1978` | `negative_result_success` | `docs/task010_shifted_maxwell_preconditioner/outcomes/shifted_positive_profile_summary.csv` |

## 3.12 Task011

研究对象是低-restart Krylov、FE-only AMS/HX 和 matrix-free action，目的是分离“低内存但不收敛”“AMS 可行性”和“矩阵存储可消除性”。流程引入 FE-only 正定代理与 matvec 等价 smoke；只得到研究信号，没有完整 Stage4 solver。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `low_memory_gmres40_p2_h4` | source SHA 历史未记录 | `F-STAGE4-S`；p2 h4 | MPI8 assembled Jacobi-GMRES | 1000步 true residual `0.234320`；RSS upper 3.284 GiB；无 official R/T/A | `controlled_negative` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/low_memory_krylov_summary.csv` |
| `real_fe_only_ams_p2_h5` | FE-only tracked CSV | 50×25×140 nm positive Maxwell；p2 h5 | MPI2 AMS；规模细节见 evidence | 7步 residual `4.024e-7`，RSS 6.930 GiB；无 Floquet/DtN/通道 | `research_only_positive` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_summary.csv` |
| `complex_fe_only_ams_p1_h10` | failure record | complex FE-only | hypre AMS setup | `malloc invalid size` + PETSc signal 11 | `failed` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md` |
| `matrix_free_fe_action_p2_h5` | feasibility record | p2 h5 | UFL action vs assembled matvec | relative action error `7.563e-16`，RSS约0.445 GiB；不是 solver residual | `research_only_positive` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/matrix_free_matvec_feasibility.md` |

## 3.13 Task012

研究对象是周期 H(curl) Maxwell 预条件文献，目的是停止盲扫黑盒 PETSc profiles。流程形成 real/imag split AMS/HX、p-coarsened auxiliary、DtN/Floquet coarse 与 matrix-free 路线图；本 Task 没有运行 PDE。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task012_literature_route_registry` | 文献表与 scorecard；source SHA 不适用 | 周期 H(curl) 方法综述；无具体模型 | 无 PDE；DoF/rows/NNZ 不适用 | R/T/A、残差、通道、时间、内存均 `not_run/not_applicable` | `documentation_success`；理论建议需由后续实验限定 | `docs/task012_literature_review_maxwell_preconditioners/outcomes/summary.md` |

## 3.14 Task013

研究对象是 FE-only complex Maxwell 的 real-split AMS，目的是绕过 complex hypre AMS 崩溃。流程把复矩阵转成实 2×2 块并比较 H1 auxiliary；same-H1 有 B 档正信号，但没有 Floquet/DtN/R/T/A。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `fe_only_p2_h5_same` | source SHA 历史未记录 | 50×25×140 nm FE-only；hexa p2 h5 | serial FGMRES + same-H1 AMS；37,446 complex DoF，74,892 real rows，14,233,968 NNZ | 310 iterations，true residual `9.964e-7`，RSS 1.323 GiB；R/T/A/12通道不适用 | `research_only_positive`；不可推广为 Stage4 | `docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_summary.csv` |
| `fe_only_p2_h4_same_equivalence` | equivalence CSV | p2 h4 | real split action；82,878 complex / 165,756 real rows | matvec error `1.671e-16`，assembly RSS 1.924 GiB；solve未运行 | `incomplete; equivalence_only` | `docs/task013_real_split_ams_hx_qualification/outcomes/real_split_equivalence.csv` |

## 3.15 Task014a

研究对象是 default100 p1/h5 Stage4 的 real-split FE/aux block PC，目的是把 Task013 信号接入 Floquet MPC + DtN。流程验证 split、索引与 AMS 数据；最小 `FE-AMS + aux identity` 太弱，p2 Gate 关闭。这里的 reduced 不是 cell-interior static condensation。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `tiny10_p1_h5` | source SHA 历史未记录 | tiny10 Stage4；p1 h5 | real-split FGMRES；144 FE+4 aux complex，296 real rows，18,600 NNZ | 37步 true residual `9.601e-7`，RSS 0.261 GiB；问题过小，无权威通道 | `diagnostic_success` | `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_summary.csv` |
| `default100_p1_h5` | tracked CSV | 100×100×150 nm；p1 h5 | FE-AMS+aux identity；39,270 FE+708 aux complex，79,956 real rows，9,390,960 NNZ | 1000步 true residual `0.0214656`，limit `1e-6`，RSS 0.786 GiB；无 official R/T/A | `controlled_negative` | `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/summary.md` |

## 3.16 Task015

研究对象是 Task014a 残差的 FE/aux、port、衍射级和 Schur 分解，目的是定位停滞。流程从强化 FE AMS 转向边界慢模态审计；确认残差集中在 top `(0,0),y` aux mode，但简单 correction 无效。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `default100_boundary_diagnostic` | source SHA 历史未记录 | 同 Task014a default100；79,956 real rows | FE-AMS+aux identity + residual decomposition | true residual `0.0214655595`；FE/aux fraction=`0.04331/0.999062`；top `(0,0),y` 占 aux `0.9999999989`；无 official R/T/A | `diagnostic_success` | `docs/task015_boundary_aware_pc_diagnostic/outcomes/boundary_residual_decomposition.csv` |
| `aux_exact_diag_modal` | combined diagnostic | 同一模型 | aux exact/diag/modal corrections | residual仍约`0.02146556`；Schur-diag反而`0.442726` | `controlled_negative` | `docs/task015_boundary_aware_pc_diagnostic/outcomes/combined_boundary_pc_diagnostic.csv` |

## 3.17 Task016

研究对象是 top/bottom 零级模式的 right-only lifted coarse correction，目的是检验 Task015 dominant mode 能否形成低秩 PC。流程构造1–4维 coarse space；改善只有万分之几，关闭 right-only lane。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `top_y_diag_minres_one_shot` | source SHA 历史未记录 | default100 reduced Stage4 | right basis `[-P_FE^-1 C_j;e_j]` | residual `0.0214655595→0.0214645967`，improvement `1.00004486×`；目标≤0.002或≥10× | `controlled_negative` | `docs/task016_zero_order_lifted_coarse_correction/outcomes/one_shot_coarse_correction.csv` |
| `lifted_ksp` | KSP summary | 同一规模 | additive/residual/minres，300步 | best residual `0.0214656363`，improvement `<1`；无 official R/T/A | `negative_result_success` | `docs/task016_zero_order_lifted_coarse_correction/outcomes/lifted_coarse_ksp_summary.csv` |

## 3.18 Task017

研究对象是 Petrov/adjoint left space 与 true-FE sampled lift，目的是判断 Task016 缺左空间还是 FE lift 不准。Petrov 无效，但 two-mode true-FE one-shot 把残差降约5.8倍，形成研究正信号，KSP 集成仍失败。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `true_fe_sampled_top_bottom_y` | source SHA 历史未记录 | default100 p1/h5 | SciPy GMRES近似解2个 selected FE RHS | residual `0.0214655595→0.00368878394`，5.819×，RSS约1.802 GiB；未达≤0.002或≥10× | `research_only_positive` | `docs/task017_petrov_adjoint_coarse_correction/outcomes/true_fe_sampled_lift_diagnostic.csv` |
| `true_fe_lift_ksp` | KSP summary | 同一系统 | right-preconditioned FGMRES | 300步 residual `0.0235498770`，反而恶化；PETSc AMS RHS另报 error 101 | `controlled_negative / failed` | `docs/task017_petrov_adjoint_coarse_correction/outcomes/petrov_ksp_summary.csv` |

## 3.19 Task018

研究对象是把 Task017 one-shot 变成 residual-corrected solver-like 过程，目的是决定 sampled-Schur lane 是否继续。交替 FE-AMS 段和 selected correction 得到约12.9倍改善，但离 production `1e-6` 仍约1662倍。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `residual_outer_zero` | source SHA/artifact hash 历史未记录；轻量CSV保留 | default100；79,956 real rows，9.391M NNZ | bounded FE-AMS + sampled correction，3 cycles | residual `0.0214588→0.001661623468`，12.914×；limit `1e-6`；RSS upper 1.571 GiB，wall约21.7 min；无 official R/T/A | `research_only_positive; incomplete_for_production` | `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/residual_corrected_loop_summary.csv` |
| `projected_gmres` | prototype record | 同一系统 | projected prototype | residual约`0.00170842`，350.2 s；不是最优 | `research_only_positive_not_best` | `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/summary.md` |

## 3.20 Task019

研究对象是把 p1 sampled-Schur 信号迁移到目标 p2/h5，目的在于验证可扩展性。流程执行严格同口径比较；改善仅 `1.0018×/1.0804×`，因此关闭低维 sampled-Schur 主线。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h5_sampled_schur` | source SHA 历史未记录 | `F-STAGE4-S` p2/h5 | sampled response/coarse；规模见 evidence | two comparison ratios `1.0018×/1.0804×`，远低于研究 Gate；无合格 official R/T/A | `negative_result_success`；路线不迁移 | `docs/task019_p2_h5_true_fe_sampled_schur_qualification/outcomes/summary.md` |

## 3.21 Task020

研究对象是 default100 算法沙盒的四条 wave-aware route，目的是在分支卫生约束下快速排序。p1 Route C 达到 `1e-6`，但目标 p2 仅约 `0.0525`，所以只是路线排序，不能作为目标物理结论。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `route_c_p1_and_p2` | branch=`codex/20260709-task20-wave-solver-search`；精确 SHA 历史未记录 | default100 algorithm sandbox；p1/p2 | wave-aware route C | p1 residual达到`1e-6`；p2 residual约`0.0525`；official R/T/A与12通道历史未记录 | `research_only_positive`（p1）/`controlled_negative`（p2） | `docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_progress.csv` |

## 3.22 Task021

研究对象是目标 p2/h5 的 DtN residual selector 与 FE-response Schur，目的是验证边界响应机制。serial SciPy h5 达到 `1e-6`，证明机制，但尚非 MPI 且 h2 未资格化。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h5_spilu_full_schur` | Task020 research branch；精确 SHA 历史未记录 | `F-STAGE4-S` p2/h5 | serial SciPy SPILU/full Schur | residual达到`1e-6`；资源与12通道历史未记录 | `research_only_positive`；证明机制，不是 production | `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/summary.md` |

## 3.23 Task022

研究对象是 p2/h2 Schur 资源 preflight，目的是在分解前判定内存。流程把 CSR 装配与 SPILU 估计分开；CSR在6.277 GB内完成，但 SPILU 估计27.79 GB，因此受控阻断，无 field/RTA 回填。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h2_csr_preflight` | Task020 research branch；source SHA 历史未记录 | `F-STAGE4-S` p2/h2 | CSR assemble + serial SPILU estimate | assembly/CSR peak 6.277 GB；SPILU estimated 27.79 GB；R/T/A、residual和通道 `not_run` | `diagnostic_success; controlled_negative`（内存 Gate） | `docs/task022_p2_h2_schur_pc_preflight/outcomes/summary.md` |

## 3.24 Task023

研究对象是 PETSc MPI FE-response PC，目的是把 Task021 serial 机制迁入 MPI 并建立 field/RTA 回填。h5 residual 和 official RTA 闭合，h2 residual约1失败；AMS auxiliary 接口未完成。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h5_petsc_fe_response` | Task020 research branch；source SHA 历史未记录 | `F-STAGE4-S` p2/h5 | PETSc MPI FieldSplit/selected response | h5 residual与 official R/T/A 闭合；精确数值/资源见 evidence；12通道历史未记录 | `infrastructure_success; diagnostic_success` | `docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md` |
| `p2_h2_petsc_fe_response` | 同一数据族 | p2/h2 | 同算法 | terminal residual约`1`，limit `1e-6`；无 official output | `controlled_negative` | `docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md` |

## 3.25 Task024

研究对象是 p2 h2/h1.5 的低内存 FE-response 工程原型，目的是修复 complex dot、MPI CSR 导出并评估 manual FGMRES。基础设施可复现，但算法收益 Gate 失败，也不是完整80-aux production 解。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `manual_fgmres_fe_response_h2_h1p5` | branch=`codex/20260709-task20-wave-solver-search`；SHA历史未记录 | `F-STAGE4-S` p2 h2/h1.5 | manual FGMRES + MPI CSR export | complex-dot与导出回归通过；算法收益 Gate失败；official totals/12通道不合格 | `infrastructure_success; negative_result_success` | `docs/task024_engineering_iterative_solver_fast_track/outcomes/summary.md` |

## 3.26 Task025

研究对象是参数鲁棒 multilevel H(curl) 与 cached-Q augmented Schur，目的是跨 h5/h2 稳定。h5 有强信号，但 h2 residual `0.1185`，远超 `1e-6`，且 response 质量不足；后由 Task026 exact auxiliary condensation 取代架构。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `cached_q_augmented_schur_h5_h2` | branch=`codex/20260710-task25-parameter-robust-hcurl-pc`；精确 SHA 历史未记录 | `F-STAGE4-S` p2 h5/h2 | cached-Q multilevel H(curl) | h5 strong signal；h2 terminal residual `0.1185`，limit `1e-6`；无合格 official通道 | `research_only_positive / controlled_negative`；被 Task026取代 | `docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/summary.md` |

## 3.27 Task026

研究对象是 auxiliary-free 3D modal port，目的是精确消去80个 DtN auxiliary 并建立 matrix-free `F-C H^-1D`。h5 达到 `1e-9` 且 h2 action 等价通过，但初始 two-level PC 不鲁棒；精确算子基础进入后续稳定模块。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `auxiliary_free_h5` | branch=`codex/20260711-task26-auxiliary-free-3d-modal-port`；精确 SHA 历史未记录 | `F-STAGE4-S` p2/h5 | exact auxiliary Schur + matrix-free action | full residual达到`1e-9`；official R/T/A闭合；逐级和资源详见 evidence | `production_success; infrastructure_success` | `docs/task026_auxiliary_free_3d_modal_port/outcomes/summary.md` |
| `auxiliary_free_h2_two_level` | 同一数据族 | p2/h2 | initial two-level PC | action/transpose等价通过，但 solver Gate 未过 | `controlled_negative`；PC仍不鲁棒 | `docs/task026_auxiliary_free_3d_modal_port/outcomes/summary.md` |

## 3.28 Task027：mesh-independent physical-slab Schwarz

**探索目的：**在 14 GB 工作站内，用同一 MPI4 迭代算法求解 h5/h3/h2，并使最大/最小迭代数比小于 2。

它改变了迭代主线：以 owner-computes physical slabs、固定75维 coarse 和两步 shifted-F smoothing 替代失败的 spectral/GenEO 假设。三网格残差与资源 Gate 通过，但迭代数不单调，准确结论是 mesh-robust workstation candidate。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task027_h5_h3_h2_sm2` | branch=`codex/20260711-task27-mesh-independent-spectral-schwarz`；精确 SHA 历史未记录 | `F-STAGE4-S` p2 h5/h3/h2 | MPI4 right FGMRES100，16 slabs，ILU1，75D coarse；DoF `44,698/198,438/615,108` | iterations `1201/993/1804`，full residual `9.8395e-7/9.9326e-7/9.9974e-7`；h2 R/T/A=`0.0013429363/0.5992132418/0.3994438284`，RSS 12.958 GB；12通道/幅值历史未记录 | `success_with_qualifications`；spectral/GenEO residual `0.2187–0.2504` 为 controlled negative | `docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| owner-slab + 一步平滑 | h5/h3/h2 迭代数 `2765/1836/3682`；比值 `2.0054` | 只差严格门槛约 10 步；h2 更快但不满足 `<2` | `controlled_negative` |
| owner-slab + 两步全局平滑 | `1201/993/1804`；比值 `1.8167`；h2 RSS `12.958 GB`；h2 R/T/A=`0.0013429363/0.5992132418/0.3994438284` | 同一规则跨三网格通过；物理 R 跨网格仍未收敛 | `success_with_qualifications` |
| spectral / GenEO / interface harmonic coarse | h5 100 步真残差约 `0.2187–0.2504`，远差于固定 75D coarse `6.272e-3` | 谱子空间代数正确，但没有捕获非正规 Floquet-DtN 慢误差 | `controlled_negative` |

## 3.29 Task028：阶段整合、master 迁移与 benchmark 冻结

研究对象是 Task000–027 的生产能力、研究负结果与依赖边界，目的是把历史分支中真正稳定的算子、回归和证据选择性迁入 master。流程建立 progress CSV、依赖分组和 selective-merge 规则；本 Task 主要是整合，不新增物理 PDE。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task000_task027_consolidation` | base/master 与 manifest 身份见 Task028 outcomes；逐历史 SHA 多数未记录 | 汇总 Task000–027 多种模型 | read-only audit + selective integration；无新增 PDE | 冻结 Task007 official RTA、Task026 exact auxiliary Schur、Task027 workstation iterative；本 Task R/T/A/资源 `not_run` | `documentation_success; integration_success`；失败 spectral/sampled-Schur 不进 ordinary API | `docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_summary.md` |

## 3.30 Task029：原始完整矩阵直接法内存剖析

**探索目的：**确定 full3D p2 direct 的内存峰值，并测试 rank、对象生命周期、OOC、BLR、ordering 和线程。

流程把 assembly、MUMPS setup/factor、solve 与生命周期分开采样，证明 h3 峰值来自 LU fill，而非 RHS 或 postprocess；ordinary direct default 保持不变。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task029_h3_mpi4_direct` | Task029 fresh WSL record；source SHA见 outcomes | `F-STAGE4-S` p2/h3 | MPI4 MUMPS；198,518 rows，matrix/factor NNZ `21,317,860/266,127,836` | true residual `1.382e-11`，R/T/A Gate通过；worker RSS 8651.098 MiB；12通道/幅值历史未冻结 | `success`；MPI2只降15.119%、release只降5.462%、BLR residual `4.704e-3` 均为负结果 | `docs/task029_stage4_direct_memory_forensics/outcomes/summary.md` |

| 模型/候选 | rows / NNZ | 数值结果 | 资源/时间 | 最终状态 |
|---|---|---|---|---|
| h5 MPI4 MUMPS baseline | p2 h5；详细 rows 见 Task032 | full solve 与 R/T/A Gate 通过 | worker RSS `2328.145 MiB` | `success`，冻结基线 |
| h3 MPI4 MUMPS baseline | 198,518 rows；matrix/factor NNZ `21,317,860/266,127,836` | true residual `1.382e-11`；R/T/A Gate 通过 | worker RSS `8651.098 MiB`；主峰来自 KSPSetUp LU fill | `success`，诊断基线 |
| h3 MPI2 | 同一物理 | 数值等价 | `7343.137 MiB`，仅下降 `15.119%`，未达 20% | `controlled_negative` |
| release base matrix | 同一物理 | 数值等价 | h3 仅下降 `5.462%` | `controlled_negative`；生命周期非主因 |
| OOC | h5 | 数值通过 | 内存 `-13.744%`，Stage4 时间 `1.539×`，scratch 559.7 MB | `controlled_negative` |
| BLR `1e-5` | h5 | true residual `4.704e-3`；R/T/A 最大偏差 `1.073e-3` | 返回码为 0 但数值错误 | `failed` |
| MPI1×4 threaded | h5 | residual/RTA 通过 | KSPSetUp 仍约 1 核；Stage4 `48.273 s` | `controlled_negative`；当前镜像无线程因子化收益 |
| h2 direct | 预测 `18.882–27.913 GiB` | 未启动 | 超安全 Gate | `not_run` |

## 3.31 Task030：H(curl) 低内存迭代与层级基础设施

**探索目的：**在保持 h5/h3/h2 真残差和 R/T/A 的同时，进一步压低 Task027 的迭代内存。

流程用 symmetric pre/post、ILU0、factor-only、local shift 和 restart90 压缩内存；p/h multilevel coarse 五类试验 residual `0.374864–0.680155` 失败，真正成功来自更紧凑的 physical-slab 配置。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `compact_physical_slab_h5_h3_h2` | Task030 records，source SHA见 outcomes | `F-STAGE4-S` p2 h5/h3/h2 | FGMRES90 + ILU0 symmetric pre/post + 75D coarse | iterations `855/962/1873`，residual `9.924905e-7/9.903890e-7/9.972228e-7`；RSS `1.688/3.793/9.375 GB`；h2 R/T/A=`0.00134293442/0.59921323601/0.39944383222` | `success_with_qualifications`；restart80 与 p/h coarse为 controlled negative | `docs/task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md` |

| 模型/候选 | 结果 | 具体原因 | 最终状态 |
|---|---|---|---|
| p/h multilevel coarse（5 类） | 100 步真残差 `0.374864–0.680155`，比 Task027 基线差 145–264 倍 | 792D p1 coarse 未包含 Maxwell 梯度/近核和掠入射慢误差 | `controlled_negative` |
| symmetric pre/post + ILU0 + factor-only + local shift + restart90 | h5/h3/h2 full pass；内存 `1.688/3.793/9.375 GB`；R/T/A 见第 1.3 节 | 对称平滑是关键；不是 p/h multigrid 成功 | `success_with_qualifications` |
| restart80 | weak-positive Gate 未过 | Krylov 内存继续下降不足以抵消收敛恶化 | `controlled_negative` |

## 3.32 Task031：assembled-F-free 极限内存路线

**探索目的：**不在 Krylov 过程中常驻 assembled `F`，并压缩 overlap 和对象生命周期。

流程改为 public form action、overlap0.125 和 compact lifecycle。它把 h2 simultaneous peak 压到7.898 GiB，但每次 MatMult 重做 form action/通信，h2耗时约3.33小时。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `assembled_F_free_h5_h3_h2` | Task031 records，source SHA见 outcomes | `F-STAGE4-S` p2 h5/h3/h2 | matrix-free form action + Task030 PC | iterations `1157/1994/1977`，residual `9.959903e-7/9.973853e-7/9.998454e-7`；peak `1.620/3.474/7.898 GiB`；h2 total `12173.086 s` | `success_with_qualifications`；强内存成功、速度负担很大 | `docs/task031_compact_physical_slab_memory_optimization/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 代价/不足 | 最终状态 |
|---|---|---|---|
| public form-action + overlap0.125 + compact lifecycle | h5/h3/h2 full pass；峰值 `1.620/3.474/7.898 GiB` | h2 solve `11982.581 s`，约 3.33 h；每次 MatMult 重新做 form action 和通信 | `success_with_qualifications`；强内存成功、速度很慢 |
| restart50 | 内存约 `-1.89%`，残差和时间更差 | 收益低于停止阈值 | `controlled_negative` |
| fixed Richardson linear PC | 200 步 residual `0.7703` | 恢复线性但失去有效平滑 | `controlled_negative` |
| boundary Jacobi selective local solver | residual 恶化到 `0.0118`，RSS 无收益 | 破坏物理 slab 修正 | `controlled_negative` |

## 3.33 Task032：Hybrid FEM–Modal direct baseline

**探索目的：**用上下两个短 3D FEM 区 + 中间二维模态传播，降低 Full3D 行数和 NNZ，并验证与同网格 Full3D 一致。

流程建立同离散 Full3D–Hybrid closure 和 M160 基线；h5/h3 都把 rows/NNZ 显著压缩且 R/T/A 最大差约2–3e-6，但不等于跨网格 continuum convergence。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `hybrid_h5_h3_M160` | Case080 authority；source SHA见 Task032 summary | `F-STAGE4-S` p2 h5/h3 | direct Hybrid M160；rows `14,052/68,796`，NNZ `2,000,624/8,594,673` | h5 R/T/A=`0.0890210691/0.4425867427/0.4683921882`，residual `2.5455e-12`；h3=`0.0046128199/0.5836509402/0.4117362399`，residual `2.6036e-12`；same-grid max delta `2.07e-6/2.63e-6` | `success_with_qualifications`；QEP h5 beta误差29.5323%为离散负结果 | `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| full3D h5/h3 | R/T/A 分别见第 1.2 节 | h5 与 h3 物理结果差异明显，不能称连续收敛 | `success`，同网格基线 |
| Hybrid h5 M160 | rows `44,778→14,052`；NNZ `4,896,156→2,000,624`；最大 R/T/A 差 `2.07e-6` | QEP h5 beta 离散误差仍大 | `success_with_qualifications` |
| Hybrid h3 M160 | rows `198,518→68,796`；NNZ `21,317,860→8,594,673`；最大差 `2.63e-6` | 只证明同离散一致 | `success_with_qualifications` |
| QEP air h5 | beta 相对误差 `29.5323%`，但多项式 residual `<=1.82e-15` | 代数求解正确不等于横截面离散收敛 | `controlled_negative`（离散精度） |
| h2 Hybrid | 中心/上界资源 Gate 未满足 | 未运行 | `not_run` |
| 0.7 nm current direct layout | 预测不满足资源 | 当前显式模态、多 RHS 和 local LU 不可扩展 | `predicted negative` |

## 3.34 Task033：高阶 Floquet、Hybrid fixed-p 与 p4 资源 Gate

研究对象是高阶 p3 Floquet、同阶 Hybrid 和固定-p等精度压缩，目的在于证明高阶 local FEM 与 modal coupling 可共同工作。流程完成 p3/h5 closure、M80/120/160 漏斗和 p3/h7.5 等精度点；p4/h5 Full3D 在12.616 GiB assembly Gate受控停止。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p3_h5_full_vs_hybrid_M160` | Task033 record identities | `F-STAGE4-S` hexa p3/h5 | Full3D direct vs Hybrid M160 | Full residual `5.442e-12/2.343e-12`；Full rows 145,943、NNZ 35,566,727、7.781 GiB、103.59 s；Hybrid local rows `21,847×2+320`、NNZ `5,156,503×2`、2.618 GiB、111.94 s；R/T/A与16项Gate通过 | `success` | `docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/hybrid_vs_full3d_summary.md` |
| `p3_h7p5_hybrid_M160` | Phase D authority | 同物理 p3/h7.5 | Hybrid direct M160 | 26,998 rows，factor inventory 17,057,414，2.008 GiB，74.908 s；相对 p2/h3 物理误差不劣 | `success_with_qualifications`；固定-p等精度压缩 | `docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md` |
| `p4_h5_full_assembly_gate` | controlled-stop record | p4/h5 | Full3D assembly-only Gate | 339,892 rows，155,205,040 base NNZ，12.616 GiB停止；未factor、无official物理 | `controlled_stop` | `docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| p3/h5 full3D | peak `7.781 GiB`；true residual `5.442e-12` | 成功建立同阶 Hybrid 对照 | `success` |
| p3/h5 Hybrid M80/120/160 | M160 true residual `2.277e-12`；M120→160 R/T/A 差 `7.216e-14`；显著功率/幅值差 `3.676e-10/1.925e-10` | fixed-p M 漏斗闭合 | `success` |
| p3/h7.5 full3D | `3.667 GiB`、`44.487 s`、residual `6.449e-12` | 相对 p2/h3 全部物理误差不劣 | `success_with_qualifications` |
| p3/h7.5 Hybrid M160 | `2.008 GiB`、`74.908 s`；16项 Gate 通过 | 等精度压缩成功 | `success_with_qualifications` |
| p4/h5 full3D assembly | 339,892 rows；155,205,040 base NNZ；12.616 GiB 时停止 | 未进入 factorization；目标资源 Gate 失败 | `controlled_stop` |
| variable-p / hp | native cellwise variable-p H(curl) 未资格化 | 没有 target PDE | `not_run / incomplete` |

## 3.35 Task034：WSL、固定几何 p2/p3/p4 收敛矩阵、Hybrid 与 graded-h

**研究对象。** Task034 在工作站WSL环境中冻结 `F-HO-S` 规则矩形光栅，完整计算 p2、p3、p4 的固定几何 Full3D/Hybrid 矩阵，并补充 M 漏斗、MPI identity、资源停止和 graded-h。该任务不是只得到一个 p4/h5 点，而是形成了26个固定几何主线/补充模型、6个 M-funnel模型和8个MPI identity模型，共40行统一事实。

**为什么重要。** 这些结果是后续高阶、静态凝聚、Hybrid和h/p自适应的基础：它们说明提高阶次能在较粗网格上迅速接近高阶参考，也说明“Hybrid rows少”必须与同网格Full3D物理闭合、M收敛和实际内存一起判断。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task034_fixed_geometry_matrix` | Case092/093 compact authority；source/geometry identity见 Task034 summary | `F-HO-S` fixed rectangular grating；p2/p3/p4 structured hexa | Full3D/Hybrid direct；26个主线/补充模型、6个M-funnel、8个MPI identity | p4/h5 Full3D `339,892 DoF / 28.888458 GiB / 917.470 s`；Hybrid `100,920 rows / 9.205917 GiB / 412.422 s`；完整矩阵见下表 | fixed-geometry convergence authority；graded-h 为 controlled negative | `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md` |

### 3.35.1 固定几何 Full3D / Hybrid 物理矩阵

| p/h | Full3D status | Full3D R/T/A | Full3D FE DoF / peak / total | Hybrid M160 status | Hybrid R/T/A | Hybrid rows / peak / total |
|---|---|---|---|---|---|---|
| p2/h5 | pass | `0.0890216029 / 0.442588279 / 0.468390118` | `44,698 / 2.959606 GiB / 16.568 s` | pass | `0.0890210691 / 0.442586743 / 0.468392188` | `14,052 / 3.284866 GiB / 96.284 s` |
| p2/h3 | pass | `0.00461303141 / 0.583653357 / 0.411733611` | `198,438 / 9.534939 GiB / 152.972 s` | pass | `0.00461281990 / 0.583650940 / 0.411736240` | `68,796 / 4.695160 GiB / 164.317 s` |
| p2/h2 | pass | `0.00134293285 / 0.599213229 / 0.399443838` | `615,108 / 32.539612 GiB / 1235.543 s` | pass | `0.00134288473 / 0.599212676 / 0.399444439` | `181,096 / 11.305332 GiB / 461.776 s` |
| p2/h1 | assembly stop | `not_run` | `4,379,752 / 67.922901 GiB / 792.958 s assembly` | timeout | no official output | `95.878723 GiB / 7200 s` |
| p3/h10 | pass | `0.0553984905 / 0.406067867 / 0.538533643` | `23,073 / 2.744572 GiB / 20.092 s` | formal not pass | `0.0553988021 / 0.406069310 / 0.538531887` | `7,594 / 2.867710 GiB / 91.920 s` |
| p3/h7.5 | pass | `0.00309072745 / 0.591160863 / 0.405748409` | `63,747 / 4.609695 GiB / 52.328 s` | pass | `0.00309064738 / 0.591159679 / 0.405749673` | `26,998 / 3.614460 GiB / 117.671 s` |
| p3/h5 | pass | `0.00109010701 / 0.600622478 / 0.398287415` | `145,863 / 9.040073 GiB / 149.658 s` | pass | `0.00109009569 / 0.600622368 / 0.398287536` | `44,014 / 4.908238 GiB / 143.515 s` |
| p3/h3 | pass | `0.000789467957 / 0.602514984 / 0.396695548` | `656,325 / 44.068672 GiB / 1726.362 s` | pass | `0.000789467334 / 0.602514979 / 0.396695554` | `224,170 / 14.271553 GiB / 661.410 s` |
| p3/h2 | assembly stop | `not_run` | `2,047,218 / 64.014950 GiB / 1334.645 s assembly` | shard pass only | `0.000764466671 / 0.602690128 / 0.396545405` | `596,356 / 49.641502 GiB / 3513.818 s` |
| p4/h10 | pass | `0.00188231722 / 0.596619520 / 0.401498163` | `53,084 / 5.639561 GiB / 115.525 s` | pass | `0.00188234769 / 0.596619395 / 0.401498258` | `16,616 / 3.517616 GiB / 136.253 s` |
| p4/h7.5 | pass | `0.000802469015 / 0.602429773 / 0.396767758` | `147,844 / 12.724396 GiB / 345.384 s` | pass | `0.000802464969 / 0.602429757 / 0.396767778` | `61,464 / 5.967117 GiB / 279.377 s` |
| p4/h5 | pass | `0.000766313377 / 0.602677531 / 0.396556156` | `339,892 / 28.888458 GiB / 917.470 s` | pass | `0.000766313235 / 0.602677530 / 0.396556157` | `100,920 / 9.205917 GiB / 412.422 s` |
| p4/h3 | assembly stop | `not_run` | `1,539,948 / 80.537712 GiB / 3035.139 s assembly` | shard pass only | `0.000762184540 / 0.602706301 / 0.396531514` | `522,536 / 42.481407 GiB / 3662.685 s` |

### 3.35.2 收敛指导

- p2需要细到h2才接近高阶中心，且Full3D峰值已达32.54 GiB；
- p3从h7.5到h3持续逼近高阶中心，p3/h3为正式M漏斗点；
- p4/h7.5已经接近p4/h5，说明规则结构的大部分场适合高阶逼近；
- p4/h5的 `R/T/A = 0.000766313377 / 0.602677531 / 0.396556156`，是Task034阶段的高阶工程参考；
- 后续Task035b/035c的p6/h10将离散参考进一步推进到 `R/T/A ≈ 0.000762881475 / 0.602701634 / 0.396535485`。

### 3.35.3 M 漏斗与MPI identity

M80→120的总量差约 `1.1e-9`，M120→160约 `1e-11`，所以当前13.5 nm固定结构在这些离散上M120已基本稳定，M160是保守正式点。p3/h5 Full3D和Hybrid在MPI1/8/16均通过，MPI32只作exploratory；更高rank降低core时间但增加进程复制内存，Hybrid MPI16相对MPI8只小幅加速。

详细6行M漏斗和8行MPI identity见第1.2.2；权威数据来自Task034 summary表2/表3和Case092/093 compact records。

### 3.35.4 graded-h 与资源负结果

| profile / case | 实际结果 | 状态 |
|---|---|---|
| conservative graded-h | raw DoF reduction `1.561×`；peak3.964GiB；112.12s | `controlled_negative`；未通过同误差Gate |
| balanced graded-h | raw DoF reduction `3.172×`；peak3.292GiB；96.63s | `controlled_negative` |
| aggressive graded-h | raw DoF reduction `9.590×`；peak2.537GiB；71.92s | `controlled_negative` |
| p2/h1 Full3D | assembly后预测factor upper418.821GiB | `not_run_by_resource_gate` |
| p3/h2 Full3D | assembly后预测factor upper232.460GiB | `not_run_by_resource_gate` |
| p4/h3 Full3D | assembly后预测factor upper204.132GiB | `not_run_by_resource_gate` |
| 0.7nm current layout | 多个单组件超过2TiB；simultaneous peak未知 | `production_feasibility_unknown / stress-test negative` |

**证据：** `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、
`benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/all_model_compact_fixture.json`、
`benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json`、
`benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/mpi_identity_summary.json`、
`docs/task034_workstation_wsl_adaptive_scalability/outcomes/all_model_authority_audit.json`。

## 3.36 Task035：H(curl) goal-oriented adaptivity

研究对象是 periodic tetra 上真实 discrete adjoint/DWR、一次 local-h 与固定网格 p-up，目的是建立目标导向 h/p 判别而非无限 h-refine。流程完成周期闭合、normalized R/T/A multi-goal 与 strict-R audit；选定 p4/p5、theta0.7、每初始网格最多一次local-h，但预算内仍未获得 strict same-error 候选。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `h50_p4p5_one_local_h` | Case094 hash-bound record；source SHA见 summary | `F-HO-S` periodic tetra；base180 cells，p5 15,405 DoF | strict-R DWR theta0.7，一次 local-h；refined1,248 cells，101,210 DoF | base vector/strict-R error `2.2032e-2/1.5130e-3`；refined `6.3581e-4/4.3764e-4`；>90k | `controlled_negative`（预算与strict-R） | `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md` |
| `refined_mesh_global_p6` | same-origin Case094 | 同refined mesh；p6 | fixed-mesh global p+1；167,784 DoF | vector/strict-R error `1.0224e-4/5.1371e-5`；精度正信号但远超90k | `controlled_negative`（预算） | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json` |

| 模型/候选 | 实际结果 | 具体不足 | 最终状态 |
|---|---|---|---|
| tetra h50 base p5 | 180 cells；15,405 DoF；vector error `2.2032e-2`；strict-R error `1.5130e-3` | 基础误差较大 | `research baseline` |
| one-local-h p5 | 1,248 cells；101,210 DoF；vector error `6.3581e-4`；strict-R `4.3764e-4` | 超 90k；不是同 patch h/p 公平竞争 | `controlled_negative`（预算） |
| refined mesh global p6 | 167,784 DoF；vector error `1.0224e-4`；strict-R `5.1371e-5` | 精度更高但远超 90k | `controlled_negative`（预算） |
| classifier/DWR | multi-goal DWR 和周期标记通过 | structured hexa 无 hanging-node transition；selected tetra p6 架构缺失 | `incomplete` |

## 3.37 Task035b：高阶 local-hp、静态凝聚、通道恢复和资源

研究对象是 fixed rectangular hexa 的高阶 DoF 分解、assembly-time static condensation、setup/cache、方向性 h 和 local-p/selective-trace 研究。流程取得精确物理消元、显著内存/rows压缩与 setup 加速；但 `<=90k` 最强 h13 仍只通过10/12功率和10/12幅值，不能宣称 same-error 成功。selective trace与condensed iterative均不得提升为production。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `global_p6_h10_reference_v1` | Case095 source/geometry/tensor hashes见 record | `F-HO-S`；(6,3,14) hexa；global p6 | MPI8 assembly-time exact static-condensed direct；173,802 FE，51,272 active rows，41,989,040 NNZ，202,441,352 factor NNZ | R00/R/T/A=`7.537612e-4/7.628815e-4/0.602701634/0.396535485`，true residual `1.26e-11`；12 powers/amplitudes见1.4；direct peak15.964 GiB，build/setup/solve `102.32/102.54/0.167 s` | `success; best_available_same_code_reference` | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json` |
| `fixed_p5trace_p6interior_h13` | Case095 hash-bound record | `(6,2,12)`；89,740 Full3D-equivalent DoF | MPI8 assembly-time static-condensed direct；20,120 rows，11,013,212 NNZ，36,273,200 factor NNZ | R00/R/T/A=`0.000756117570/0.000765246512/0.602682451672/0.396552301816`，residual `5.81e-12`；`T(-4)=4.354892e-7`、`R(-4)=2.723391e-7`、`r(-4)=2.127847e-4-4.721864e-5i`、`r(-5)=-1.009264e-4-5.936550e-5i`失败；peak 6.411 GiB | `controlled_negative`；10/12+10/12，不是same-error | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json` |
| `condensed_iterative_three_profiles` | Case095 negative records | h15 condensed trace | Jacobi GMRES30、ASM/ILU0 FGMRES30、z-slab/DtN coarse，均200步 | terminal residual ratios `0.861662/0.999661/0.996265`；peak `3.921/4.462/3.885 GiB`；无official R/T/A/channel | `controlled_negative`；不得提升production | `docs/task035b_high_order_local_hp_resource_envelope/outcomes/summary.md` |
| `selective_p6_trace` | fixture/capability v2；无PDE record | p5trace/p6interior storage + research orbit | MatShell/action-only fixtures | actual DWR、row plan、正式PDE数量均0；资源/物理 `not_run` | `incomplete; research_only` | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_selective_trace_execution_capability_v2.json` |
| `hybrid_static_h1a_p2_h5` | source `148729c28c3f9aefec8e5646cc644c5c4e2332da`；raw SHA 绑定 compact record | `F-STAGE4-S`；p2/h5 hexa；Full3D 44,698 FE；Hybrid local 6,826 FE/side | MPI8 direct；local static condensation；M120/M160；M160 10,000 total rows、976,400 matrix NNZ pair、5,986,184 factor NNZ pair | M160 R00/R/T/A=`0.089011819673/0.089021069106/0.442586742743/0.468392188151`，residual `3.45e-12`；static-vs-standard 12/12+12/12；Full3D-vs-Hybrid 3/12+2/12；peak 3.308 GiB，186.36 s | `controlled_negative`；H1-A channel Gate fail，H1-B not run | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/hybrid_static_condensation_h1a_mpi8_v1.json` |

### 3.37.1 精度候选

| 模型 | 目的 | 具体结果 | 未满足项 | 状态 |
|---|---|---|---|---|
| global p6/h15 | 以更粗 h 压缩 p6/h10 | 84,492 DoF；24,704 rows；12 GiB pair；总量/场通过 | 仅 6/12 功率、8/12 幅值；弱衍射级未收敛 | `controlled_negative` |
| fixed p5-trace/p6-interior h15 | 降低共享 trace 阶次并保留 p6 interior | 74,890 DoF；16,880 rows；5.803 GiB；R/T/A 接近参考 | 具体失败通道见第 1.4.1.3 | `controlled_negative` |
| directional-z h14 | 只增加 z 分辨率 | 82,315 DoF；功率/幅值通过数 7/12、9/12 | `R/T(-4,-5)` 等仍超 reference band | `controlled_negative`，有正信号 |
| directional-z h13 | 使用接近 90k 的 z 分辨率 | 89,740 DoF；R/T/A 和场通过 | `T(-4)`、`R(-4)` 功率及 `r(-4),r(-5)` 幅值失败，数值见第 1.4.1 | `controlled_negative`；预算内最强 |
| h13 top-two z redistribution | 固定 DoF 移动内部 z 平面 | 8/12 功率、8/12 幅值 | 比原 h13 退化 | `controlled_negative` |
| h14 exact reverse | 验证相反节点移动 | 7/12 功率、8/12 幅值 | 没有支持该机制 | `controlled_negative`；z-node lane closed |
| global p6/h14 trace discriminator | 判断 full p6 trace 是否有帮助 | 92,850 DoF；9/12 功率、12/12 幅值 | 超预算 2,850 DoF，且功率仍非12/12 | `diagnostic controlled_negative` |
| selective p6 trace | 只激活关键 p6 edge/face orbit | fixture 中 inactive rows=0、Floquet pullback和MatShell action通过 | actual channel DWR、正式 row plan、runner 和 PDE 均为 0 | `incomplete` |

### 3.37.2 Setup/cache 与 direct rank

| 研究点 | 实际结果 | 解释 | 状态 |
|---|---|---|---|
| h15 cold/warm setup | non-KSP build `19.242/6.141 s`，相对旧 `61.61 s` cold 加速 `3.202×` | 缓存复用 tensor、Aii factor 和 local Schur；warm 仍需全局矩阵和 MUMPS numeric | `engineering success` |
| h13 cold/warm setup | `19.410/6.696 s` | 无同 h13 旧 cold baseline，不能宣称 cold-code 2.9× | `engineering success_with_qualification` |
| h15 MPI1/2/4/8 direct | RSS `1.295/2.158/3.100/4.711 GiB`；总时间 `76.007/74.913/61.849/53.901 s` | MPI1 是最低实测 direct 内存；MPI8 最快，但不是最低内存 | `engineering success` |

### 3.37.3 静态凝聚迭代负结果

| Profile | 200步后 residual ratio | 内存 | 具体结论 | 状态 |
|---|---:|---:|---|---|
| GMRES30 + Jacobi | `0.861662` | `3.921 GiB` | 没有 global factor，但残差只下降约14%，未产生 official R/T/channel | `controlled_negative` |
| FGMRES30 + ASM(1)/ILU0 | `0.999661` | `4.462 GiB` | 几乎完全停滞；含局部 ILU | `controlled_negative` |
| FGMRES + z-slab ILU0 + DtN trace coarse | `0.996265` | `3.885 GiB` | 物理分块和80D coarse仍未改善谱；不是严格 factorless | `controlled_negative` |
| matrix-free selective trace MatShell | fixture action正确，不构造 global matrix/LU | 无正式 PDE、KSP 和内存 authority | 只降低存储不会自动解决预条件器问题 | `incomplete` |

### 3.37.4 Review V3 static Hybrid H1-A

| 研究点 | 实际结果 | 未满足项 | 状态 |
|---|---|---|---|
| Full3D standard/static 等价 | 12/12 power、12/12 amplitude；rows `44,778→30,800`；peak `2.960→2.763 GiB` | 无 static-equivalence 失败 | `engineering success` |
| Hybrid standard/static M160 等价 | 12/12 + 12/12；rows `14,052→10,000`；NNZ pair `1,454,248→976,400` | factor 只降6.3%，peak升0.7%，total升93.6% | `engineering mixed_negative` |
| static Hybrid M120→M160 | 12/12 + 12/12；总量和场几乎不变 | 增大 M 没有修复 Full3D channel closure | `converged discriminator` |
| static Full3D↔Hybrid M160 | 相对口径3/12 power、2/12 amplitude；strict absolute 2/12+2/12 | 9个功率和10个幅值失败，逐项值/限值见 compact record | `controlled_negative` |
| H1-B/H1-C/H1-D | PDE 均未启动 | Review V3 要求 H1-A 全通过后才能进入 H1-B | `not_run_by_review_prerequisite` |

## 3.38 Task035c：Hybrid逐通道与高阶静态内存闭合

Task035c先用p2/h5解释“总R/T接近但弱衍射级不对”的原因，再在p6/h10上
正式比较Full3D与Hybrid、standard与static。Hybrid把中间均匀长段替换成二维
模态传播；static condensation再精确消去上下局部三维单元内部自由度。最终
12通道物理与正式15%/25%内存Gate通过，但用户期望的50%峰值下降没有达到。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task035c_p2_h5_continuous_symbol_baseline` | Task035b H1-A + Case096 root-cause ledger | `F-STAGE4-S`；p2/h5；MPI8 | Hybrid continuous QEP phase + continuous traction；M120/M160 | M160 对 same-source Full3D 仅 `3/12 powers + 2/12 amplitudes`；提高 M 未修复 | `controlled_negative_root_cause_baseline`；不是 M 截断不足 | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p2_h5_root_cause_v1.json` |
| `task035c_p2_h5_discrete_phase_only` | source/record hash见 Case096 compact | 同一 fixed rectangular p2/h5 | 只启用 scalar-CG discrete phase，traction仍连续 | `4/12 powers + 4/12 amplitudes`；相对原始有改善但未闭合 | `controlled_negative_discriminator`；phase必要但不充分 | same compact record |
| `task035c_p2_h5_discrete_phase_traction` | source `8a1e40c...`；Case096 compact | `F-STAGE4-S`；p2/h5；MPI8 | Hybrid M120/M160；`full3d_uniform_cg` + `scalar_cg_discrete_derivative` opt-in | 两点均12/12 powers+12/12 boundary amplitudes；phase-only仅4/12+4/12 | `diagnostic_success`；root cause closed | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p2_h5_root_cause_v1.json` |
| `task035c_p6_h10_full_standard` | source `244b62e1...`；clean MPI8 | `F-HO-S`；global p6/h10；173,802 FE | standard Full3D direct；173,882 rows；210,353,168 matrix NNZ；438,050,956 factor NNZ | R/T/A=`0.000762881475133/0.602701633983338/0.396535484541529`；residual`1.709e-11`；peak34.041GiB；2581.55s；12/12+12/12 | `success; discrete_reference` | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json` |
| `task035c_p6_h10_full_static` | same source/mesh/MPI | `F-HO-S`；p6/h10 | exact cell-interior static；51,272 rows；41,989,040 NNZ；212,343,992 factor NNZ | R/T/A=`0.000762881475126/0.602701633985538/0.396535484539337`；residual`3.092e-11`；14.722GiB；260.74s；12/12+12/12 | `engineering_success`；peak -56.75% | same compact record |
| `task035c_p6_h10_hybrid_standard_M120_M160` | same source；MPI8 | local p6/h10 ends + discrete modal middle | M120/M160；52,292/52,372 total rows；60,434,236 NNZ；141,010,528 factor NNZ | peaks11.077/11.247GiB；times942.03/1014.71s；两点12/12+12/12 | `success baselines` | same compact record |
| `task035c_p6_h10_hybrid_static_M120` | same source；MPI8 formal authority | local exact static + modal middle；17,168 rows | 12,313,232 matrix NNZ；45,293,792 factor NNZ | R/T/A=`0.000762881475142/0.602701633984217/0.396535484540641`；residual`2.079e-12`；RSS7.544GiB；PSS/USS `5.769862/5.491413 GiB`；322.78s；12/12+12/12 | `success; selected`；RSS -31.89%，PSS/USS -38.88%/-40.31%；用户50%目标仍open | six-path + PSS/USS compact records |
| `task035c_p6_h10_hybrid_static_M160` | same source；MPI8 | `F-HO-S`；local p6/h10 ends + discrete modal middle | 17,248 rows；same local matrix/factor inventory | RSS7.929GiB；PSS/USS `6.169376/5.888676 GiB`；393.84s；12/12+12/12；相对M120无物理收益 | `success_not_selected`；RSS -29.50%，PSS/USS -35.81%/-37.16% | same compact records |
| `task035c_static_rank_MPI1` | source `244b62e1...`；measured | Full static formal pass；Hybrid static M120 | Hybrid measured1.752GiB、1328.72s | 12/12+12/12但positive QEP biorthogonality `1.197600e-6 > 1e-6` | `controlled_negative_numerical`；非内存floor | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_static_rank_study_v1.json` |
| `task035c_static_rank_MPI2` | same source；measured | Full static formal pass；Hybrid numeric pass | Hybrid measured3.142GiB、798.20s | terminal launcher-drain RSS/swap readability失败 | `controlled_negative_resource_authority`；MPI4 not run by stop rule | same rank record |

### 3.38.1 Task035c 选择、内存口径与能力边界

M120 被选择是因为它与 M160 都通过 12/12 功率、12/12 physical-boundary
complex amplitudes、R/T/A/场/残差 Gate，而 M160 没有可测物理收益，却使 static
RSS增加 `5.1052%`、modal coupling 增加 `38.9106%`、总时间增加
`22.0146%`；因此停止 M160 lane，不运行 M240。用户提出的 `>=50%` static
Hybrid RSS 降幅仍为 `not_achieved/open_engineering_gap`。

PSS/USS 来自原始 MPI8 timeline 中逐 rank `/proc/<pid>/smaps_rollup` 的历史
回填。只使用 8 个 rank 同时可读的样本，不由 RSS 推算且没有重跑 PDE。正式
Task035c relative-memory authority 仍为 simultaneous process-tree/live-worker
RSS；PSS/USS 是共享页/私有页诊断。compact authority 为
`benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_pss_uss_ledger_v1.json`。

| qualified scope | not qualified / must fail closed |
|---|---|
| fixed rectangular block grating；structured tensor-product；axis-aligned first-order affine hexa；modal middle uniform z；single axial h；p1–p6；complex128；Floquet；sparse auxiliary DtN；direct standard/static Full3D/Hybrid | nonuniform z；local-h/hanging hexa；curved/distorted/high-order geometry；tetra static；hexa/tetra/prism/pyramid mixed；sloped/rounded/rough/defect或任意 irregular geometry；production automatic hp adaptivity |


## 3.39 Task035d：exact-sequence local-p 与 true local-h 自适应

Task035d 固定使用 Task034 矩形块光栅、p6/h10 Full3D static reference-v1、
MPI8 direct MUMPS 和冻结的 12 个显著功率/复振幅 Gate。首批只检验真实
assembly-time variable-p active space：inactive 高阶模式不生成 global row，
并继续使用 exact cell-interior static condensation。两个正式 p-only 候选均为
结构与资源成功、同精度失败的 controlled negative；不能把资源压缩写成物理
成功，也不能据此放宽 12/12 Gate。

Review V1 统一分类：

```text
capability_status = pass
resource_status = pass
accuracy_status = fail
```

当前预算内最佳 accuracy/resource 工程候选仍是 Task035b fixed
p5-trace/p6-interior h13（`89,740 DoF / 20,120 rows / 6.411 GiB /
10/12 powers + 10/12 amplitudes`）。Task035d 最强通道结果 h15 top-air
为 `82,925 / 18,470 / 7.50068 GiB / 6/12 + 6/12`。Task035d 的
local-h/local-p 架构更通用，但尚未在“精度 + 内存”上超过 h13。

同 MPI8、同 process-tree watchdog、同求解生命周期下的正式资源基线为：

| baseline | peak |
|---|---:|
| Full3D static p6/h10 | `14.721756 GiB` |
| Hybrid standard p6/h10 M120 | `11.076893 GiB` |
| Hybrid static p6/h10 M120 | `7.544262 GiB` |

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task035d_case097_closeout` | source、plan、MPI identity 与 checker SHA 均冻结 | Task034 fixed rectangular grating；p4/p5/p6 exact-sequence local-p；balanced-hexa local-h | MPI8 direct static；最佳资源点76,205 DoF/18,470 rows；最终判别点88,915/21,650 | 最佳通道6/12+6/12；最终4/12+6/12；峰值最低7.29866 GiB；Hybrid未运行 | `PARTIAL_WITH_CONTROLLED_NEGATIVES`；无 production hp candidate | `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/summary.md` |

| Model ID | source / plan identity | p4/p5/p6 cells | FE DoF / active rows | matrix / factor NNZ | residual / peak | strict physics | status / evidence |
|---|---|---:|---:|---:|---:|---|---|
| `task035d_t30_h10_mpi8` | solver `c3768cf4723c2ae949c82d1ce8b18a56f5ab0f7b`；checker `5f960f912809b162e363259b0896af25ef3b0018` | `144/56/52` | `87,600 / 28,990` | `15,253,176 / 63,564,300` | `1.410e-11 / 10.0929 GiB` | `0/12 power + 0/12 amplitude`；R/T/A L2 `21.214`；volume/interface `9.337%/9.884%` | `controlled_negative_accuracy`；`benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t30_h10_mpi8_controlled_negative_v1.json` |
| `task035d_sidewall_z0_guard_h10_mpi8` | solver/checker source `a6f2d8a3b88efda581aa0e36f5ebcd9d6776e0cf`；plan SHA `31922411775580b2f44b474897dbf877d96b7887f74d22e02b3f0e410c205bc2` | `72/168/12` | `89,870 / 31,064` | `16,490,572 / 76,721,484` | `7.560e-12 / 8.38265 GiB` | `1/12 power + 0/12 amplitude`；R/T/A L2 `13.271`；volume/interface `3.733%/4.016%` | `controlled_negative_accuracy`；`benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/sidewall_z0_guard_h10_mpi8_controlled_negative_v1.json` |

相对 global-p6 static baseline（173,802 FE DoF、51,272 rows、
41,989,040 matrix NNZ、212,343,992 factor NNZ、14.72176 GiB），T30 的
rows/matrix/factor/peak 分别下降 `43.46%/63.67%/70.07%/31.44%`；
sidewall guard 分别下降 `39.41%/60.73%/63.87%/43.06%`。这些是正式实测
的资源正信号，但两条精度结果连续为负，因此 T25、T15 和第三条 p-only PDE
均不运行，研究转向 true local-h。

`sidewall_z0_guard_v1` 冻结通道误差如下。误差与 tolerance 均来自独立
checker；只有 `top(-1,0)` power 通过，所有 complex amplitude 均失败。

| side/order | power error / tolerance | amplitude error / tolerance |
|---|---:|---:|
| bottom -7 | `7.25323e-7 / 2.15869e-9` | `1.23293e-3 / 1.21657e-5` |
| bottom -5 | `7.92214e-9 / 3.89127e-10` | `9.95785e-6 / 1.28065e-6` |
| bottom -4 | `4.38440e-9 / 5.25100e-10` | `2.07690e-5 / 2.54166e-6` |
| bottom -2 | `4.61647e-8 / 4.65105e-9` | `2.99641e-5 / 4.58081e-6` |
| bottom -1 | `1.84990e-6 / 1.11441e-7` | `2.06358e-4 / 1.27290e-5` |
| bottom 0 | `1.86466e-3 / 2.17577e-4` | `5.08728e-2 / 6.77963e-3` |
| top -7 | `2.28277e-7 / 1.24944e-9` | `6.72145e-4 / 7.99504e-7` |
| top -5 | `8.23809e-9 / 1.19430e-9` | `7.92162e-6 / 1.11321e-6` |
| top -4 | `1.58210e-8 / 1.08649e-9` | `1.60124e-5 / 1.88152e-6` |
| top -2 | `3.03981e-9 / 1.24228e-9` | `2.03888e-5 / 3.18649e-6` |
| top -1 | `4.78904e-8 / 5.11184e-8` pass | `8.61368e-5 / 7.41338e-6` |
| top 0 | `1.21288e-4 / 3.19529e-5` | `2.83493e-3 / 8.33027e-4` |

该段登记的是当时的阶段状态。后续 Attempt 2 已补齐 compiled tensor、
PETSc ownership、full recovery/residual 和 MPI1/2/8 production identity，
并启动最小正式 local-h/hp PDE；最终结果登记在 3.39.2–3.39.6。Attempt 1
记录仍保留为能力演进证据，不回写成当时已经具备 PDE credit。

### 3.39.1 True local-h Attempt 1 component authority

source `b12b1887ca3acb534f36186c93e9e5efb10cf2ad` 已完成前述 Gate
中的几何与纯约束图部分：

| capability | measured authority | status |
|---|---|---|
| true local split | 2-cell fixture `2→9` leaves；全局坐标平面 control 需12 cells | pass |
| broken carrier boundary identity | 42 facets；30 topological exterior = 25 physical + 5 catalogued hanging；unexplained=0 | pass |
| H(curl)/H1 face restriction | p4 `144x40`、p5 `220x60`、p6 `312x84`；full rank/commuting | pass |
| 3D orientation | 6 hexa faces；每阶 `4×8×8=256` child/D4 组合 | pass |
| static Schur exchange | local-condense-then-hanging 与 one-shot 误差 `<=2e-12` | pass |
| periodic+hanging graph | 37 cells、8 patches、raw 5,120→independent 3,384、chain depth2、residual `1.4621e-15` | pass |
| MPI identity | MPI1/2/8 stable physical authority SHA `19e032d3...96afa8` | pass |
| compiled cell tensor / PETSc ownership / PDE | 未绑定、未运行 | `in_progress/no_PDE_credit` |

MPI comparison authority 为
`benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt1_mpi_identity_v1.json`
（SHA256 `d341ad69dd52df6bbedcec8a522084cd75ae99fd9fd7d751bab7bfb73655fe44`）。
该记录明确保持 `heavy_pde_started=false`、`pde_accuracy_credit=false`。
因此 Attempt 1 是结构正信号；下一步必须完成实际 cell-oriented
`C_K`、compiled FFCx tensor、RHS/recovery、PETSc row ownership 与 MPI2
matrix/action identity，才能进入 local-h PDE。

### 3.39.2 Attempt 2、正式 local-h 与 combined-hp 总账

Attempt 2 将 physical geometry-key graph 绑定到 compiled FFCx tensor、
`C_K^H S_K C_K`、RHS/recovery、DtN、PETSc owner-routed rows 和完整
active-space residual。MPI1/2/8 production identity 通过；inactive p6 mode、
hanging slave 和 periodic slave 不生成 global row。

正式模型均为 Task034 fixed rectangular block grating、13.5 nm、S 偏振、
MPI8 direct MUMPS、assembly-time static condensation、zero swap：

| Model ID | numerical source | local-h / p plan | FE DoF / rows | matrix / factor NNZ | residual / peak / total | strict physics | status / evidence |
|---|---|---|---:|---:|---:|---|---|
| `task035d_h15_top_air_local_h_mpi8` | `ed9c8fc6002bf086f19bef94492b23d7c24b7287` | 120 roots→134 leaves；p5 trace/p6 interior | `82,925 / 18,470` | `10,186,108 / 30,865,200` | `5.740e-12 / 7.50068 GiB / 202.762 s` | R/T/A、Avolume、fields pass；`6/12 power + 6/12 amplitude` | `controlled_negative_accuracy`；`h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json` |
| `task035d_h15_symmetric_remote_p5_mpi8` | `54cb665e05e72027d8e617b1a1c546413c127f0e` | 120→148 leaves；p5 trace；p5/p6 interiors `32/116` | `84,240 / 20,060` | `11,176,430 / 32,658,700` | `2.124e-11 / 7.50883 GiB / 208.766 s` | scalar/energy/fields pass；`4/12 + 4/12` | `controlled_negative_accuracy`；`h15_symmetric_top_air_remote_p5_interior_mpi8_candidate_check_v2.json` |
| `task035d_h15_factorial_bridge_mpi8` | `d194075dda0aceef8bf566dd76412c9517fe4bb3` | 120→134 leaves；p5 trace；p5/p6 interiors `32/102` | `76,205 / 18,470` | `10,186,108 / 30,865,200` | `3.433e-12 / 7.29866 GiB / 198.400 s` | scalar/energy/fields pass；`4/12 + 4/12` | `controlled_negative_accuracy`；`h15_top_air_remote_p5_interior_bridge_mpi8_candidate_check_v1.json` |
| `task035d_h15_selective_ten_face_mpi8` | `0ecd914b246f433614252f6f3c0513b06b078542` | 120→134 leaves；10 physical p6 faces；其他 trace p5 | `83,125 / 18,670` | `10,406,108 / 32,683,000` | `1.287e-11 / 8.06898 GiB / 279.206 s` | scalar/energy/fields pass；`5/12 + 6/12` | `controlled_negative_accuracy`；`selective_face_selection_compact_v1.json` |
| `task035d_h15_left_grating_single_root_mpi8` | `333cb7e437906c78c95c94788abb76e2f263bc80` | 120→162 leaves；p5 trace；p5/p6 interiors `48/114` | `88,915 / 21,650` | `12,382,332 / 37,250,750` | `3.267e-11 / 8.06120 GiB / 297.114 s` | scalar/energy/interface pass；volume max fail；`4/12 + 6/12` | `controlled_negative_accuracy`；`h15_left_grating_top_closure_p5fine_mpi8_controlled_negative_compact_v1.json` |

相对 p6/h10 Full3D static，实测压缩：

| Model ID | rows | matrix NNZ | factor NNZ | peak RSS | PSS / USS |
|---|---:|---:|---:|---:|---:|
| h15 top-air local-h | `-63.9764%` | `-75.7410%` | `-85.4645%` | `-49.0504%` | `6.41306 / 6.25235 GiB` |
| symmetric remote-p5 | `-60.8753%` | `-73.3825%` | `-84.6199%` | `-48.9950%` | `6.42191 / 6.26128 GiB` |
| factorial bridge | `-63.9764%` | `-75.7410%` | `-85.4645%` | `-50.4227%` | `6.21633 / 6.05586 GiB` |
| ten-face selective trace | `-63.5864%` | `-75.2171%` | `-84.6085%` | `-45.1901%` | `6.98143 / 6.83401 GiB` |
| left-grating single-root | `-57.7742%` | `-70.5106%` | `-82.4574%` | `-45.2430%` | `6.92657 / 6.77756 GiB` |

最小 `76,205` DoF 候选仍高于 preferred `75,000` 上界，并且物理 Gate
失败；不得因资源正信号将其登记为 same-error hp success。

Task035d `task.md` §3.2 的统一控制组没有遗漏：global p6/p5 h10、
Task035 p4→p5 DWR theta0.7、Task035b fixed h15/h14/h13，以及 Task035d
p-only、h-only、combined resource best 和 final discriminator 的
DoF/rows/NNZ/peak/channel/status 对照集中登记在 Task035d
`outcomes/summary.md` §4.1。Task035 tetra DWR 与 global p5 缺少同一
Case095 12-channel/peak 口径的字段均明确写为未记录，不由其他量推断。

### 3.39.3 弱通道失败总账

下表列出所有失败通道身份；每行最后给出该候选最大超限的实际
error/tolerance，完整 12 行保存在对应 checker。

| Model ID | power failures | amplitude failures | 最大 power error/tol | 最大 amplitude error/tol |
|---|---|---|---:|---:|
| h15 top-air local-h | bottom `-5,-4,-2`；top `-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `2.333561e-8/5.251003e-10` | bottom -4 `1.589564e-5/2.541658e-6` |
| symmetric remote-p5 | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-1` | bottom -7 `1.008269e-7/2.158694e-9` | top -7 `2.285933e-5/7.995039e-7` |
| factorial bridge | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-1` | bottom -7 `9.977858e-8/2.158694e-9` | top -7 `2.371900e-5/7.995039e-7` |
| ten-face selective trace | bottom `-7,-5,-4`；top `-7,-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `2.221993e-8/5.251003e-10` | bottom -4 `2.051506e-5/2.541658e-6` |
| left-grating single-root | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `1.204267e-8/5.251003e-10` | top -4 `1.087300e-5/1.881525e-6` |

### 3.39.4 DWR 与 h/p 归因

| Authority | measured conclusion | credit boundary |
|---|---|---|
| `h15_top_air_nested_p_dwr_mpi8_checker_v2.json` | 12 unit-channel、36 real-goal closure pass；16 periodic p-down pairs 无 conservative-safe action | 不授权继续 remote p-down |
| selective-face raw DWR `bd19254a...76bf1` | independent checker `36/36`；ten-face contribution 可重算 | posthoc attribution；不授予 causal selection credit |
| `hp_factorial_bridge_attribution_v1.json` | local-h、symmetric combined、factorial bridge 三点实测归因 | factorial attribution pass；combined-hp accuracy false |
| `bounded_single_seed_top_air_hp_selection_v2.json` | compact-DWR location oracle；left-grating cost-normalized score最高 | actual local-h DWR unavailable；success forecast false |

16 个 periodic same-trace remote-interior p-down pair 在 conservative
budget 下无一安全：远端均匀空气仍携带弱衍射通道相位，几何距离不是
p-down 的充分条件；trace 不变时只降 cell interior 的 global-row 收益还可
为零。该证据禁止继续当前 same-trace remote-interior 盲扫，但不能推出
任何 local-p 都不可能成功。

### 3.39.5 Final left-grating observables

| R00 | Rtotal | Ttotal | Aclosure | Avolume | normalized R/T/A L2 |
|---:|---:|---:|---:|---:|---:|
| `0.000755218940191` | `0.000764349909195` | `0.602685528512531` | `0.396550121578274` | `0.396550121578974` | `0.117446` |

volume weighted relative L2 `0.01229361` 通过，但 maximum point error
`0.04688675 > 0.04102079`；interface relative L2/max
`0.00788774/0.02208509` 均通过。最终 raw watchdog/full/compact checker
SHA256 分别为：

```text
7d4c7a1efa0068c7a6c478ad4cef4b88fdfa1f5acbd10532d4c2794a356f7165
1b9dd3cdb931f5fe69da5a0a567ff278a47416f7082d47cef2e0b5e4109e2492
d6e03061465b29ce4e958bfd6ac7972f245130fdf66de197541caed09e8e4225
```

最终 record 的计时字段为嵌套 wall timers，而不是可相加的 stage 分解：

| timer | value | semantics |
|---|---:|---|
| outer solver elapsed | `297.114 s` | solver 入口到场输出的外层 wall clock；权威 total |
| base matrix assembly | `256.515 s` | 完整 base/reduction build 的 MPI-max wall envelope |
| legacy `total_build_seconds` | `68.972 s` | variable-p condensed-system builder 的 MPI-max 内层 diagnostic，包含于上一项 |
| MUMPS setup / backsolve | `13.524 / 0.041 s` | MPI-max wall timers，均包含于 outer total |

这些字段禁止相加；Task035e 必须另建 mutually-exclusive timeline。

### 3.39.6 Lane closure 与 Task035d 分类

| item | final status |
|---|---|
| p-only | closed after T30 and guard formal negatives |
| remote p5 interior | closed controlled negative |
| frozen ten-face selective subset | closed controlled negative |
| whole top-port selective trace | incomplete/not run；未运行 modes 未被证伪 |
| bounded single-root top-air local-h | closed after top-air and left-grating formal negatives |
| outer-periodic | `not_run_by_lane_stop`；不是 PDE failure |
| multi-seed | `not_evaluated_by_stop_rule` |
| automatic cycles 1–4 | `not_completed`；只有 manual bounded discriminators，没有 per-cycle authority |
| Hybrid Phase F | `not_run_full3d_hp_gate_failed` |

Task035d 最终登记：

```text
classification = PARTIAL_WITH_CONTROLLED_NEGATIVES
production_hp_candidate = none
phase_e = partial_manual_bounded_discriminators
ordinary_default_changed = false
```

local-h 技术层支持非均匀叶单元；正式搜索却只覆盖
`h15 + global p5 trace + bounded single requested root + mandatory closure`，
没有完成多层、多区域、多 refinement-level 自动网格。关闭该 single-root
lane 不等于证明所有 local-h 无效。frozen ten-face 负结果也没有证明其他
top-port faces、periodic orbits、edge modes 或 material-interface faces
无效。

重新开启该 lane 前，必须先在新 candidate space 上产生 actual per-channel
local-h 或 trace-orbit DWR；当前 compact location oracle 不足以授权继续扫描。

## 3.40 Task035e：reference-blind 多层 local-h/p 自适应

Task035e 先由独立 certifier 对 p6/h10、p6/h7.5 和 p6/h5 建立收敛资格，再把
数值结果封存在 hidden reference package 中；blind controller 只能读取冻结的
低阶目标集合、当前解、局部 indicator、成本和自身历史，不能读取 reference
值、路径、hash、误差图或已知最优网格。2026-07-29 已完成 Path A cycle 0 的
current、p-shadow、h-shadow 与 59-goal/cellwise 离线重放，并依次验证一次
固定 four-cell selected-p actual candidate 与一次保守 single-cell p-up
diagnostic。两条 candidate 的数值/资源 Gate 均通过，但 action-level predictor
Gate 均失败；single-cell 结果进一步关闭了当前 cellwise-p quantitative
predictor。因此没有晋级 cycle 1，仍只能登记 partial progress，不能登记 cycle
完成或 hidden-reference 精度通过。

2026-07-30 又完成 structured reference-visible 收敛核验和两种
selective-trace 排名。三条 global-p6 structured endpoint 均为 59/59；M1
fixed trace 只有 52/59。普通场投影 200-orbit candidate 同时触发精度和资源
negative；最后一次 6-adjoint goal-oriented 16-orbit candidate 通过资源与
求解 Gate，却因 10 个未纳入 adjoint 的旁路目标越界而只有 49/59。这个结果
关闭 direct selective-trace，而不是把 Task035e 或 blind adaptive cycle 写成
完成。

本节 evidence 路径属于保留的 Task035e 研究分支，master 的
documentation-only integration 不复制对应 source、workers、records 或
outcomes。完整证据固定在
[`27ca26718b9ee60215243bcc98ffafcd46bfd221`](https://github.com/Rookie1234567/MyFEniCS/tree/27ca26718b9ee60215243bcc98ffafcd46bfd221)
历史快照；master 中的本表和 Review V1 是其轻量索引。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task035e_reference_certification_sealed` | certification source `03ddc8319fa9ee9da6a9ee948b539a067e9c3dd0`；sealed package `69b620…12d7`，47,421,013 bytes；package 未提交/未解析 | `F-HO-S`；p6/h10、p6/h7.5、p6/h5；S；Full3D static | direct MUMPS；MPI8；三个 full solve | 三个 run 的 residual/energy/resource 均 pass、zero swap；reference 数值、逐通道、场和 error map 不进入总账 | `SEALED_IDENTITY_ONLY_NO_REFERENCE_VALUES`；reference-leak static/manifest/dynamic 全通过 | [sealed manifest @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/task035e_sealed_reference_manifest_v1.json) |
| `task035e_structured_p6_h10` | existing certification source `03ddc8319fa9ee9da6a9ee948b539a067e9c3dd0`；same frozen 59-goal inventory | `(6,3,14)`；252 cells；global p6 trace/interior | static condensed direct MUMPS；MPI8；173,802 FE DoF；51,272 rows；41,989,040 matrix NNZ；202,441,352 factor NNZ | residual `1.483287e-11`；R00=`0.0007537612`，R=`0.0007628815`，T=`0.6027016340`，Avolume=`0.3965354845`；59/59；14.466988 GiB；zero swap | structured accuracy anchor；超过11 GiB，不是压缩候选 | [structured anchor compact @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/structured_anchor_selective_trace_v1.json) |
| `task035e_structured_p6_h7p5` | 同一 certification source 与 inventory | `(9,4,20)`；720 cells；global p6 trace/interior | static condensed direct MUMPS；MPI8；488,070 FE DoF；145,232 rows；119,738,672 matrix NNZ；708,620,576 factor NNZ | residual `2.076296e-11`；R00=`0.0007528960`，R=`0.0007620151`，T=`0.6027074846`，Avolume=`0.3965305003`；59/59；31.880505 GiB；zero swap | 更细 accuracy endpoint；h7.5→h5 max差仅 `0.004416 tau` | 同上 |
| `task035e_structured_p6_h5` | 同一 certification source；factor telemetry 离线修正绑定 raw run summary `f19e827a…60b49` | `(12,5,28)`；1,680 cells；global p6 trace/interior | static condensed direct MUMPS；MPI8；1,127,502 FE DoF；337,040 rows；279,032,240 matrix NNZ；**2,277,000,000 corrected factor NNZ** | residual `1.039818e-10`；R00=`0.0007528884`，R=`0.0007620075`，T=`0.6027075352`，Avolume=`0.3965304573`；59/59；77.945587 GiB；zero swap | best available discrete endpoint；raw PETSc `-2017967296` overflow 和 MUMPS `INFOG(9)=-2277` 均保留；未重跑 PDE | 同上 |
| `task035e_fast_hp_mechanism_negatives` | source `f1ba5627f163da54fa383b43be58fd38c0da7bc9`；reference-visible development only | 160-leaf C1/C2 与 216/272-leaf H2/P3/H3；另含同拓扑 global-p6 A 与 p5-trace/p6-interior C | MPI8 direct static；broad-p、isotropic full-h 与 trace/interior mechanism discriminators | C2/P3 E2 分别恶化 `9.219512%/9.227268%`；H2/H3 仅改善 `0.021457%/0.022178%` 且显著增资源；A 为4/59、12.335 GiB；C 为0/59、8.999 GiB | broad-p 与 isotropic-h 为 controlled negatives；A/C 只作机制证据；160-leaf topology 不再生成候选 | Task035e branch `27ca267...`；`outcomes/fast_hp_sprint_v2.md`、`outcomes/mechanism_isolation_sprint_v1.md` |
| `task035e_H10_fixed_p5trace_p6interior_M1` | source `f1ba5627f163da54fa383b43be58fd38c0da7bc9`；与 p6/h10 同一 mesh/geometry | `(6,3,14)`；global p5 trace + p6 interior | static condensed direct MUMPS；MPI8；154,735 FE DoF；35,000 rows；20,140,928 matrix NNZ；101,141,150 factor NNZ | residual `1.150501e-11`；52/59；normalized L2 `5.397523`；9,784.469 MiB historical upper bound；zero swap | 低内存 base；7 个正式失败行，不是 accuracy anchor | 同上 |
| `task035e_H10_projection_200_faces` | source `d9e2c2f8c8edbd91d96a0e642d8f4e1cc0778e6e`；field-energy projection ranking | M1 + 200/774 face orbits；233 geometry keys；无 edge/local-h | static condensed direct MUMPS；MPI8；159,395 FE DoF；39,000 rows；24,696,176 matrix NNZ；116,348,600 factor NNZ | residual `2.478629e-11`；50/59；normalized L2 `5.762190`；13.004326 GiB；zero swap | accuracy+resource controlled negative；普通场投影排序关闭；第二批 `not_run` | [structured anchor outcome @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/structured_anchor_selective_trace_v1.md) |
| `task035e_H10_goal_DWR_support` | numerical source `69cd41c74ba0dfc310d8631cf7bbd8103ec8fc73`；M1 7 fail rows→6 independent physical goals | global-p6 fine factor；B/S/F exact hierarchy；774 physical face orbits；6 transpose adjoints | factorization-only MPI8；51,272 rows；41,989,040 matrix NNZ；184,588,160 factor NNZ；无 primal solve、无 official endpoint | 6 adjoint residual `1.675e-13`–`1.729e-12`；B→S→F error `1.776e-14`；face residual unexplained `6.604e-10`；support historical upper bound 19.107769 GiB | estimator support pass；只用于冻结唯一16-orbit batch，不计 candidate memory或reference credit | [goal-DWR compact @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/h10_goal_oriented_selective_trace_v1.json) |
| `task035e_H10_goal_DWR_16_faces_actual` | 同一 numerical source；plan `dcd41fa…86fa1`；selected orbit `[748,747,605,749,603,674,682,672,681,683,673,751,741,606,752,742]` | M1 +16 p6 physical face orbits；p5 edge；p6 interior；252 cells | static condensed direct MUMPS；MPI8；155,055 active FE DoF；35,320 rows；20,492,976 matrix NNZ；93,656,300 factor NNZ | residual `9.865452e-11`；R=`0.0007629447`，T=`0.6026812190`，Avolume=`0.3965558363`；49/59；power10/16、amplitude28/32、totals5/5、fields6/6；10.929794 GiB；zero swap；286.620 s | optimized 6/6 与 dedup R00 都 pass，但新增10个旁路失败；`CONTROLLED_NEGATIVE_GOAL_ORIENTED_SELECTIVE_TRACE`；direct selective-trace关闭 | [goal-DWR outcome @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/goal_oriented_selective_trace_v1.md) |
| `task035e_path_a_c0_current_v28` | numerical source `f1ba5627f163da54fa383b43be58fd38c0da7bc9`；forest `f9b666…77a1f` | Path A current；160 leaves；level 0/1=`32/128`；p4/p5/p6=`24/136/0` | variable-p static condensed；MPI8；59,264 FE DoF；20,202 rows；10,798,392 matrix NNZ；41,217,460 factor NNZ | residual `1.373246e-12`；R00=`0.0864978439`，R=`0.0949734914`，T=`0.3774035414`，Aclosure=`0.5276229672`；RSS/PSS/USS=`8368.988/6491.735/6234.652 MiB`，swap 0；wall `239.304 s` | current stage pass；不是 adaptive candidate | [Path A stage authority @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_v28_stage_authority_v1.json) |
| `task035e_path_a_c0_p_shadow_v28` | 同一 numerical source；forest 与 current 相同；degree map `14c4ad…6c8e` | 160 leaves；level 0/1=`32/128`；p4/p5/p6=`15/138/7` | variable-p static condensed；MPI8；62,284 FE DoF；20,564 rows；11,084,868 matrix NNZ；43,034,248 factor NNZ | residual `1.873484e-12`；R00=`0.0623430295`，R=`0.0685259183`，T=`0.4081864213`，Aclosure=`0.5232876605`；RSS/PSS/USS=`8345.027/6955.710/6847.707 MiB`，swap 0；wall `236.323 s` | p-shadow pass；59/59 endpoint DWR pass；不是 selected action/candidate | 同上；`records/path_a_cycle0_v28_59goal_dwr_compact_v1.json` |
| `task035e_path_a_c0_h_shadow_v28` | 同一 numerical source；forest `d6a7c9…8de7` | 181 leaves；level 0/1/2=`32/125/24`；p4/p5/p6=`24/157/0` | variable-p static condensed；MPI8；66,434 FE DoF；22,189 rows；11,821,621 matrix NNZ；41,744,755 factor NNZ | residual `1.671519e-12`；R00=`0.0864985747`，R=`0.0949741323`，T=`0.3774025559`，Aclosure=`0.5276233119`；RSS/PSS/USS=`10482.977/9541.340/9394.934 MiB`，swap 0；wall `395.487 s` | h-shadow pass；whole-job RSS `10.237282 GiB <= 11 GiB`；59/59 endpoint DWR pass | 同上；`records/path_a_cycle0_v28_59goal_dwr_compact_v1.json` |
| `task035e_path_a_c0_cellwise_v28` | p/h cellwise authority `dc4674…7933` / `9ff5d9…bb67`；各160 rows | current leaf partition；59 formal goals；global endpoint closure 与 cellwise attribution 分离 | actual residual-adjoint pairing；equal-weight normalized multi-goal；offline replay | 两 lane 均完整覆盖 160 leaves；最大 signed closure error `2.776e-15` / `1.668e-17`；p marked 4 cells；h verification-only 1 target + 1 periodic closure | `offline_compact_replayed`；selected action/transition/candidate 均 `not_run` | [cellwise authority @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_v28_cellwise_marking_v1.json) |
| `task035e_path_a_c0_selected_p_actual` | numerical source `f1ba5627f163da54fa383b43be58fd38c0da7bc9`；action `c054f3…633c`；forest 与 current 相同 | 160 leaves；level 0/1=`32/128`；p4/p5/p6=`22/136/2`；仅 r42 两个 p4→p5 与 r13/r37 两个 p5→p6 | variable-p static condensed；MPI8；59,997 Full3D-equivalent DoF；20,251 augmented rows；10,834,433 matrix NNZ；41,278,819 factor NNZ | residual `2.421043e-12`；R00=`0.0160886209`，R=`0.0276394999`，T=`0.4322933170`，Aclosure=`0.5400671831`；RSS/PSS/USS=`7887.426/6458.675/6349.059 MiB`，swap 0；worker `207.671 s` | 数值/资源 pass；selected-cellwise prediction 仅 `19/59` factor-two、`25/59` opposite-sign，故 `CONTROLLED_NEGATIVE_ACTION_LEVEL_EFFECTIVITY`；cycle 0 current 保留 | [four-cell actual @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_selected_p_actual_checkpoint_v1.json) |
| `task035e_path_a_c0_single_cell_p_actual` | numerical source `f1ba5627f163da54fa383b43be58fd38c0da7bc9`；target `cell:r42:l1:i1:j0:k0 p4→p5`；action file `a08161…c89a`；forest 与 current 相同 | 160 leaves；level 0/1=`32/128`；p4/p5/p6=`23/137/0`；+132 interior、+0 edge、+16 face modes | variable-p static condensed；MPI8；59,412 Full3D-equivalent DoF；20,218 augmented rows；10,810,712 matrix NNZ；41,157,452 factor NNZ | residual `2.707608e-12`；R00=`0.0863527953`，R=`0.0948725837`，T=`0.3774527359`，Aclosure=`0.5276746804`；RSS/PSS/USS=`7741.539/6361.860/6249.074 MiB`，whole-job `7.560097 GiB`，swap 0；worker `191.195 s` | 数值/资源 pass；single-cell prediction `0/59` factor-two、`30/59` opposite-sign、formal `24/53` opposite-sign，故 `CONTROLLED_NEGATIVE_SINGLE_CELL_ACTION_LEVEL_EFFECTIVITY`；cellwise-p quantitative predictor 关闭，cycle 0 current 保留 | [single-cell actual @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_single_cell_p_actual_checkpoint_v1.json) |
| `task035e_path_b_c0_v27_partial` | source `1fa06c93593e3b6a97b05e1138147999a4587074`；仅复用 v27 local evidence | Path B current+p-shadow+h-shadow attempt | MPI8；h-shadow 11 GiB controlled resource Gate | current pass；p-shadow pass；h-shadow 在 `11.055027 GiB` controlled stop，未产生 run_summary/evaluation/bridge | `PARTIAL_CONTROLLED_RESOURCE_STOP`；`cycle_complete=false`；没有 v28 Path B run | [Path B partial @ 27ca267](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_b_cycle0_v27_partial_authority_v1.json) |
| `task035e_final_closure` | Review V1；reviewed head `27ca26718b9ee60215243bcc98ffafcd46bfd221` | 不新增 PDE；汇总 Task035e frozen scope | documentation-only closure；production code merge `none` | reference certification `pass`；component capability `pass`；automatic blind hp `incomplete`；production candidate `none`；Hybrid/iterative `not_run`；ordinary default `unchanged` | `PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED`；direct selective-trace `closed_controlled_negative` | `docs/task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md` |

### 3.40.1 隔离与完成边界

- `reference_certifier/`、`blind_controller/` 和 `hidden_auditor/` 必须是三层
  独立数据路径；controller 不得读取 hidden package 的内容或身份。
- p6/h5 若未通过资源 preflight，必须保留
  `REFERENCE_CERTIFICATION_INCOMPLETE`，不得把 h7.5 冒充最终 reference。
- automatic blind cycle 必须真实产生多层、多区域 local-h、p-shadow 和
  h-shadow 证据；Task035d 的 manual single-root discriminator 不计作完成。
- 当前 clean-source stage authority、一次 grouped selected-p candidate 与一次
  single-cell p-up diagnostic 已产生；两条 action-level effectivity Gate 均
  失败，candidate 均未晋级。当前 cellwise-p quantitative predictor 已关闭，
  只保留 ranking signal。hidden final audit、selected-h 均未产生，
  cycle-state transition 也未提交；因此 Task 总状态保持 partial，而不是
  completion。
- structured reference-visible lane 已确认 p6/h10、h7.5、h5 三点 59/59，
  但 M1 fixed trace、projection 200-orbit 和 goal-DWR 16-orbit 都不是
  59/59 candidate。最后一条虽满足 `10.929794 GiB <= 11 GiB`，仍因
  10 个旁路目标越界而被拒绝。direct selective-trace 已关闭，第二批、
  threshold 扩展和 ranking retune 均 `not_run/not_authorized`。
- goal-DWR 结果只证明“6 个显式目标的 signed orbit response 可预测”，不能
  推广成“完整59目标稳定”。iterative/Hybrid 是后续可能路线，但当前均
  `not_run`，不能写成已有解法。
- `config.json` 的最终 ledger schema 不能无歧义表达此 partial progress，故保持
  原 `SCAFFOLD_NOT_RUN` 语义；hash-bound checkpoint 单独位于
  `records/path_a_cycle0_v28_progress_checkpoint_v1.json`。

---

## 3.41 Task39extra：原 13.5 nm p6/h10 主候选与诊断参考

### D5最新数值诊断收口

| 项目 | 最新结果与适用边界 |
|---|---|
| 来源与模型 | clean source `bf8e0c1d16c9c86677e866cdf29fd5491f076e32`；原始13.5nm、1°、s、Full3D p6/h10、MPI1/线程1、80 DtN modes；无参考D1/D3诊断 |
| 数据/作用 | 3份历史快照原A6残差复现，最大绝对差2.77556e-16；native独立系数逐位匹配，分项和与A作用一致 |
| 调用计数 | 8 started / 7 completed；第8次JOINT448→LIGHT未完成，不能记为完整PC；已知误差/投影/互补/D4均not_run |
| 终止 | 原A4残差1.0086968840613509e-10>1e-10（超限0.8696884%）；worker DIAGNOSTICS_FAILED，watchdog/launch WORKER_FAILED，outer exit2 |
| 资源/清场 | 同期树RSS峰3777171456 B<实际cap8367992832 B；reserve4294967296 B、最低available9252577280 B；3324样本无违规，swap0；父进程及20个已观测后代清场 |
| 时间 | watchdog mono866.072315784 / BOOTTIME866.072315245 / UTC945.518512242 s；逐段保守收费945.519546580 s，outer含pre/post952.495114811 s |
| 规模 | p6存储173802/独立164592行、252cells；p4存储53084/独立48960、增广53164行、allocated NNZ24730144、factor NNZ53417584 |
| 物理输出与比较 | 无新R/T/A、A_volume、R00_s/p/total、衍射级、复E/H或full solve资格；无p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 后续范围 | 数学根因仍未完成；唯一优先是补存同一失败p4输入，核对增广系统与原A4残差差别/可靠性，再补缺失表示与响应诊断；本轮不重跑或精化 |

七份同输入PC响应已从保存数组复算；PC是提供近似修正的辅助步骤，单次rho不能代替真实场误差。失败p4向量未存，0.87%越限不能解释历史外层停滞。数据/成本/原因矩阵及依赖组见[中心报告](task039_extra_physical_multilevel/outcomes/nonconvergence_diagnosis_v3.md)。

### 历史阶段（以下当前/0次仅指原时刻）

### Review V3 / D5

| 对象 | 当前结果 |
|---|---|
| 原始13.5nm/1°/p6h10/MPI1/80modes诊断 | 唯一启动source `24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650`；`TIMEBASE_INCONSISTENCY`，不是新完整求解或数值失败 |
| 完成/未完成 | D0与微型验证完成；setup止于s6_transfer_cycles_started；fresh canonical/原A残差、已知误差、p4投影及PC探测均未完成；完整PC0、互补0、投影0，D4 not_run |
| 时间 | 首次Gate区间mono61.410906241 / BOOTTIME61.410906659 / UTC67.359115896 s，差5.948209655>5 s；245样本发现两次离散UTC相对跳变，系统原因未定 |
| 资源/清场 | 同期树RSS峰639950848 B<cap8417038336 B；reserve4294967296 B、最低effective available12219453440 B、swap0、违规0；parent及已观测后代清场 |
| D2 | 缺完整MPI1峰值上界，参考未启动；REFERENCE_UNAVAILABLE_ON_16GB仅限本轮安全路径，非普遍不可能 |
| 结果边界 | 新残差/official R/T/A/A_volume/R00_s/p/total/衍射级/EH均not_run；历史LIGHT576=0.0791360407785889、JOINT476=0.10535820013809101仍>1e-6 |
| 模型规模/比较 | 历史存储173802行、独立164592行、252cells；fresh NNZ未到达。未新增p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 下一步 | 数学原因UNRESOLVED；仅优先时间资格及冻结同输入最小补证，本轮不重试、不提新PC、不merge |

PC是外层方程求解的辅助修正；本轮计划在同一输入上分辨空间表示与实际修正，但在setup阶段时钟保护停止，尚无对应测量。详情与依赖分组见[中心报告](task039_extra_physical_multilevel/outcomes/nonconvergence_diagnosis_v3.md)。以下V2/V1保持历史口径。

| Review V2 / F5 | 当前结论 |
|---|---|
| F1 / F2 | 完整packed S6数学等价通过；配对中位0.938459>0.75，速度不足，F2 not_run |
| F3原始模型 | 13.5nm/1°/p6h10/MPI1/80modes；source `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；零初值476步真残差0.10535820013809101>1e-6 |
| 方法与失败含义 | 保留H6–准确p4–H6三个顺序方向，仅末尾联合选权；局部残差比中位0.979479，rank3/无回退；不足以让完整p6收敛 |
| 用户收尾 | USER_REQUESTED_CONTROLLED_STOP；raw worker CONTROLLED_STOP、wrapper WORKER_FAILED/exit4并列；未触发原自动budget/stagnation Gate |
| 时间限制 | workflow monotonic7588.369777 / UTC8363.831318 s；solve至请求monotonic6791.466003 / UTC7478.995420 s；UTC solve超7200，原因未唯一确定，不能声称全部wall预算通过 |
| 资源与清场 | RSS/PSS峰3351887872/3317217280 B，28753样本均可读；cap8525078528 B、至少4GiB余量无违规；swap0，56 PID清场 |
| 后续 | F4/official锁定，无第三候选、续跑或0.7nm资格；仅F5文档/测试/审阅后提交推送，非master merge |

本轮在PC末尾联合组合原三个方向，减少同输入局部误差但未解决完整收敛。原p4最大残差7.870604378195616e-11，476PC中位11.460344589024317 s；14周期+28尾段。无R/T/A、A_volume、零级/衍射复幅值、E/H或非可分资格；无p/h/M/MPI/Hybrid扫描。raw、双时钟、对照和依赖组见[中心报告](task039_extra_physical_multilevel/outcomes/packed_and_joint_mr_v2.md)。

### 历史V1/A5记录（下文未运行指当时）

| Review v1新增记录（同物理/离散/MPI1/80modes） | 实际结果 | 资格限制 |
|---|---|---|
| R0 / R1同机profile | 旧PC非warm中位22.021386729524238 s；等价原型74.87089344408014 s，ratio3.3999172878472805 | 等价通过、速度Gate失败；R2 not_run；不是S6数学失败 |
| R3 H6–p4–H6；`cbf56e87e515ab0c3fc5756cb6cf52feb047f610` | 582完整PC，中位10.293892393587157 s；last_safe576真残差0.0791360407785889>1e-6；583次p4原残差≤7.058163970105702e-11 | solve7200.255611149943 s性能停止，workflow7966.278611822054 s，RSS3352014848 B，swap0；动态cap/4GiB余量无违规 |
| R3退出与事后代码修复 | parent清场；worker终态、final arrays、normal checker/official输出缺失；代码HEAD `597546311feea60d61acb2a9999b706dd895dcf0`修未来LIGHT停止路由 | 小fixture通过不补齐R3，未重跑；R4/R5/第三PC not_run |

H6在p6上做局部平滑以节省S6内p3/p1工作，B6是辅助算子；p4仍是全局分解诊断。两条路线本轮结束，但完整S6+contiguous packing未重新资格化，不能说算法已被穷尽。没有非可分、独立全场authority、0.7nm物理收敛或生产/容量资格。完整时间口径与hash见 [R6成本](task039_extra_physical_multilevel/outcomes/cost_and_contribution_v1.md)。以下旧A5记录保留。

| Model ID / 方法 | 实际结果 | 资源和状态 |
|---|---|---|
| task39extra_A2_old_setup；Full3D/MPI1/80 modes | outer 未开始，未产生 official 场或 R/T/A | workflow 5946.465141321009 s；RSS peak 1582481408 B，swap 0；用户 setup 受控停止 |
| task39extra_A2_optimized；相同物理，S6 精确对角优化 | S6 143.69 s；7 次完整 PC 各 36 步，A4 残差 0.636–0.847；第 8 次 partial；outer final `not_available` | workflow 3015.3758775380556 s；RSS peak 1849683968 B，swap 0；`USER_AUTHORIZED_COST_CONTROLLED_STOP` |
| task39extra_A2R_reference；原 p4 直接逆辅助原 p6 外层；source `54ab46cf4c8378a9b27650ca6963cadb34013a2f` | 163 次原 A4 检查 ≤1e-10；原 A6 第32/64/96/128/160步残差 0.46338436888430473 / 0.41005441732961595 / 0.3139861672303239 / 0.2753887167051727 / 0.18250767622880507，均未达1e-6 | `PERFORMANCE_CONTROLLED_STOP`，solve3600 s；workflow4451.728501909005 s；RSSpeak3588677632 B，swap0；非生产默认、非outer PASS |

A2R 测量前另有一次 `adapter_unavailable`（source f93edc8ae9e90c4ed07e375d964312eb68999ee9，0.014696567959617823 s），未启动 watchdog/MPI/symbolic，修复后才完成上表唯一 reference。163 完整 PC、第164 pre partial；最后有效 checkpoint160，不冒称停止瞬间残差。正常 worker summary/release/recovery/checker completion 缺失，62 PID 已清场。RSS16993样本均可读，PSS有1个不可读样本。旧 S6/S3 生命周期序号误加字段原样保留，独立重算每完整周期64、全体完整PC各326次；未来计数窄修不改变数值证据。A3/A4/official输出/5nm/0.7nm未运行，未取得成功移交资格。

S6 优化只省掉取得对角项时不需要的计算；A2R 用额外矩阵及分解内存换取准确中间修正。RSS 为同期进程树采样峰值。两次 A2 均没有最终物理结果；初始 checkpoint 不能代替最终残差，成本受控停止不能推出不收敛定理。这是 13.5 nm 阶段记录，不代表 0.7 nm 已通过。来源、完整 SHA 和 hash 见 [Task39extra 运行索引](task039_extra_physical_multilevel/outcomes/records/run_index.json)，解释见 [阶段总结](task039_extra_physical_multilevel/outcomes/summary.md)。

## 3.42 Task39extra_para：原生工作站迁移与性能停止

本项目复现既有V5 BAL_H + 全局p4 LU，MPI1/线程1、13.5 nm Si、p6/h10。原native mode末位浮点差身份桥已修复，但首段时间Gate未通过；无official场或光学结果，尚未解锁短波。

| Model ID | source / measured数值规模 | measured结果与资源 | 状态及证据 |
|---|---|---|---|
| native_R1_attempt1 | `492cd519da07a8790980f9f2f21cbef24bed1643`；252 cells；p6 173802/164592；p4 53164 rows、24730144 NNZ、factor 53417584 NNZ | workflow2731.775 s；整树峰值2992881664 B；swap0；清场 | FAILED_SETUP_MODE_IDENTITY；outer未运行；[compact](task39extra_para_workstation_capacity/outcomes/records/r1_attempt1.json) |
| native_R1_retry1 | `b2e132a7b1f1078eb3359c87a336123b3c7dfbdd`；规模同上 | 62步true0.019433158954790204；p4最差4.893382586118271e-11、124次无修正；workflow3997.651 s；峰值3395833856 B；swap0；清场 | SCREEN_BUDGET_NO_QUALIFIED_PROGRESS；无R/T/A/A_volume、R00_s/R00_p/R00_total或official E/H；[compact](task39extra_para_workstation_capacity/outcomes/records/r1_attempt2.json) |
| native_5nm_formal_attempt1 | `85a681b9bd61104466888546b83df87c27806169`；3780 cells；p6 2514372、p4 754696 rows；p6 matrix-free/H6、p4 exact augmented | 698步 true `9.986638454029182e-7`；p4 1396 RHS/1419 MatSolve/23 refinement；R=`0.7331834812424759`、T=`0.00022243948430485038`、Avolume=`0.26659407694262094`；观测整树RSS峰50161172480 B、swap0 | own numerical/physical Gate 通过；`REFERENCE_AUTHORITY_LIMITED`、资源断档 `NOT_CONTINUOUS_RESOURCE_PASS`；[compact](task39extra_para_workstation_capacity/outcomes/records/5nm_formal_attempt1.json)、[600通道](task39extra_para_workstation_capacity/outcomes/records/5nm_dtn_600_channels.csv)、[checker](task39extra_para_workstation_capacity/outcomes/records/5nm_checker_recheck.json) |

第32步native/WSL完整true绝对差3.13e-13，主要问题是单位迭代耗时。p4矩阵按行访问及独立curl系数循环合并，在严格浮点真实单元测试中逐位一致，诊断加速分别约3.6倍、p6约2倍/p4约1.4倍；尚无优化后full R1。RSS/PSS监督开销已最小修复，未换PC或放宽Gate。R2、条件reference、S5/S3/S2/G均NOT_RUN_BY_PREVIOUS_GATE；不能从当前性能停止推断内存容量或物理失败。见[本轮总结](task39extra_para_workstation_capacity/outcomes/summary.md)。

### Task39extra 当前2 nm h1.5 PORD64收口

| Model ID | 身份/离散 | 实测结果 | 状态 | evidence |
|---|---|---|---|---|
| `native_2nm_h1p5_formal_attempt2` | source `9da01fb0402bc5f7da1cdaf4cc543bb53162deea`；Si用户输入；p6/h1.5；10604228体行、4752199344体NNZ、10608132增广行、4899800920增广NNZ | symbolic `INFOG(1)=-9999, INFOG(2)=4`；numeric/solve/outer未运行；330197资源样本，树RSS峰277758349312 B、swap0、descendants清场 | `WORKER_FAILED; PORD_MIXED_WIDTH_BLOCK`; 不称OOM/数值失败，正式NEDGES8未记录 | `task39extra_para_workstation_capacity/outcomes/records/2nm_h1p5_pord64_qualification_v1.json` |
| `native_2nm_h1p5_pord64_fixture` | 同一新PETSc专属prefix；8-cell p4/MPC；1944行、701496 NNZ；int64/complex128 | query=64；`INFOG(7)=4`、`INFOG(1)=0`；symbolic/numeric/solve=1/1/1；真残差2.922259846318588e-11；唯一新PETSc map | `component_qualification_only`; 不代表整张h1.5 numeric通过 | 同上；`scripts/activate_task39extra_pord64.sh` |


### Task39extra_para 2026-09-18：PORD64终态与实测内存重试

| Model ID | measured | predicted / policy | 状态与证据 |
|---|---|---|---|
| `native_2nm_h1p5_pord64_attempt3` | symbolic INFOG(1)=0；133624.287 s；同期RSS采样峰277716156416 B，swap0，已清场 | 原预测2716776698624 B超过1537541295924 B门限 | `REFERENCE_RESOURCE_BLOCKED`；numeric/outer未运行，无R/T/A；[compact](task39extra_para_workstation_capacity/outcomes/records/2nm_h1p5_measured_retry_v1.json) |
| `native_2nm_h1p5_measured_retry` | 尚未取得新数值结果 | 用户授权按实测整树RSS达到1537500000000 B停止；预测不拦截，保留reserve/swap | 提交时为启动准备；实际run身份见本任务ignored launch_check.json；[Response V3](task39extra_para_workstation_capacity/response_v3.md) |
| `native_2nm_h1p5_measured_retry_current` | source `41caf5141493ad6c5d6c518a64ee74fda8d7a7db`；run `20260918T035017.294454Z`；54332 cells、p6 35594790、p4 10604228、augmented 10608132、augmented NNZ 4899800920；3904 modes/3902 propagating | symbolic facts `INFOG1=0, INFOG7=4, INFOG16=1222577, RINFOG1=1100362818940466`；p4 numeric 进行中，末次RSS `477900079104 B`、swap0；1300 GB guard attachment peak 同值 | `RUNNING; NOT_NUMERIC_OR_PHYSICS_QUALIFIED`；outer/RTA未运行，阶段峰值未完整聚合；[compact](task39extra_para_workstation_capacity/outcomes/records/2nm_h1p5_measured_running_snapshot_v1.json)、[Response V4](task39extra_para_workstation_capacity/response_v4.md) |
| `native_2nm_h1p5_measured_retry_terminal` | 同一 run/source；workflow `176218.086 s`；原 watchdog 整树RSS峰 `635625377792 B`、任务树swap0；global pswpout `2→73`（delta71页） | 独立1300 GB guard attachment峰 `640141377536 B`，随后因 RSS unreadable/`monitoring_failed` 停止，约晚于原 watchdog stop `0.245228993 s`；两峰均未达各自 cap | `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED; exit=-9`；无 numeric complete/outer/RTA；不称OOM或数值失败；[terminal compact](task39extra_para_workstation_capacity/outcomes/records/2nm_h1p5_measured_terminal_snapshot_v1.json) |

## 3.43 Task042：神经辅助低内存 p4 粗逆

### 3.43.0 F0历史（response_v1）

本任务研究用原p4方程上的迭代求逆减少全局LU存储，并分别比较传统低内存、线性降维和神经修正。本轮共享工作站仍有原2nm计算及其他GPU训练，按任务合同止于隔离、接口与有界数组验证；没有取得新的正式模型资格。

| Model ID / 数据身份 | 物理与离散 | 本轮方法 / 规模 | 实际结果与具体未满足项 | 状态 / evidence |
|---|---|---|---|---|
| `task042_original_13p5nm_p6h10`；静态冻结，runtime not_run | Si矩形块、13.5nm、1°、phi0、s、Full3D p6/h10，同网格p4、双Floquet/完整auto DtN | mesh/mode/A4/A6、实际DoF/rows/NNZ尚未构建；252cells/173802/53084/80是历史锚点 | 原A4/A6残差、R/T/A/A_volume、R00_s/p/total、全部通道幅值/功率、E/H、场/scaled-curl均not_run；无R-LU/B0/LIN/NN本轮对照 | `not_run / WAITING_FOR_SHARED_WORKSTATION`；[summary](task042_neural_coarse_inverse/outcomes/summary.md)、[统一CSV](task042_neural_coarse_inverse/outcomes/records/full_p6_comparison.csv) |
| `task042_f0_strict_return_toy`；measured纯数组 | complex128解析3×3+port+slave toy，非Maxwell | 独立原方程/累计端口/恢复返回检查；实际FGMRES/PC未实现 | 33测试通过；11toy返回native最大1.2757622972373108e-16、port/recovery0；受监督F0采样RSS最大236548096B、own swap0、无GPU训练；不作物理或因子消除资格 | `component_interface_pass`；clean source`9934c2e08d017124ba70bdc86ec0c22f39ca792f`；[audit](task042_neural_coarse_inverse/outcomes/records/pure_component_audit.json)、[运行账](task042_neural_coarse_inverse/outcomes/records/run_index.json) |

F1–F5由邻heavy占用而未启动，不是数值方法失败。teacher/dataset/basis/线性map/model/checkpoint均无；神经增量、20%时间/内存改善与摊销没有数据。NN-Lab为canonical linked worktree，新FE/CPU-only ML环境及可写缓存隔离，旧计算源码/HEAD/环境/watchdog保留。下一步先由review检查F0，再重新核查同机空闲/lock，完成真实无global p4 factor的opt-in构造和逐阶段Gate。没有master merge或ordinary default变更。

### 3.43.1 V2：受控共享首轮实际数值

上一小节表为response_v1的F0历史。用户2026-09-28授权仅Task042受控共享CPU，override本任务heavy/全机锁要求，未修改其他任务合同或宣布F0正式review通过。真实fixed operator与F1/F2/F3/F4已经运行，终态严格粗逆未合格，未获正式p6场资格。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task042_original_13p5nm_p6h10_interfaces_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / original Si block 13.5nm、1°/phi0/s、Full3D p6/h10，同网格p4、完整80DtN；252cells、p6/p4 storage173802/53084，p4 Schur21824rows/8184464NNZ；原p6未物化全局CSR，NNZ not_assembled | A4=PH A6P差3.366065072840215e-15，非零内部/port制造解A4/A6残差1.2255722548154e-14/2.0935547822786585e-14；F1监督1242.043s/1641930752B | `real_component_pass`，非最终物理解 | [F1](task042_neural_coarse_inverse/outcomes/records/f1_real_components_v2.json) |
| `task042_offline_p4_teacher_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / 原p4准确LU仅离线参考/384对teacher；256train/64validation/64heldout，每batch<=32，native/port/internal/恒等式审核 | 最坏native3.959901353972973e-12；factorNNZ40282272，后端644.516352decimalMB；监督1687.602s/1558155264B，swap0；shared-workstation | `TEACHER_QUALIFIED`，factor.destroy并退出后才部署，无候选共驻留 | [teacher](task042_neural_coarse_inverse/outcomes/records/teacher_complete_v2.json) |
| `task042_rank128_oracle_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / 固定B0难分量POD，ranks16/32/64/128；独立原native残差像QR | validation表示比.5138245738/native最佳残差比.3338841772，线性一步native中位1.2612261732；监督358.751s/1405636608B | `REPRESENTATION_POSITIVE`仅诊断，非1e-10资格 | [oracle](task042_neural_coarse_inverse/outcomes/records/oracle_complete_v2.json) |
| `task042_cpu_fp64_mlp_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / 同rank128/B0/归一化，2hidden64、FP64实虚、103040参数；CPU-only Torch、线程1/Loader0 | 300epochs、validation选51，有载19.036174s/监督22.267641s、RSS361848832B、swap0；权重824320B；无本任务GPU分配 | `TRAINING_COMPLETED`，非部署资格 | [model](task042_neural_coarse_inverse/outcomes/records/training_complete_v2.json) |
| `task042_r-b0_strict_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / 同16未见RHS、RIGHT FGMRES32/max256/zero，全部无global p4 LU/私有CSR；R-B0比较传统/线性/神经增量 | 物理PHb6原A4=0.998654967105、port=0.465471752706，限值1e-10；1/16仅zero，非零256步；486.668s/851476480B，swap0；shared-workstation | `COARSE_INVERSE_NOT_QUALIFIED` | [严格CSV](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv) |
| `task042_r-lin_strict_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / 同16未见RHS、RIGHT FGMRES32/max256/zero，全部无global p4 LU/私有CSR；R-LIN比较传统/线性/神经增量 | 物理PHb6原A4=0.998261536287、port=0.239495977416，限值1e-10；1/16仅zero，非零256步；1239.273s/1032511488B，swap0；shared-workstation | `COARSE_INVERSE_NOT_QUALIFIED` | [严格CSV](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv) |
| `task042_r-nn_strict_v2` | measured / shared-workstation | 固定original13.5nm；p6/h10接口、同网格物理p4 | 原A4 / 同16未见RHS、RIGHT FGMRES32/max256/zero，全部无global p4 LU/私有CSR；R-NN比较传统/线性/神经增量 | 物理PHb6原A4=0.998455926264、port=0.179987283836，限值1e-10；1/16仅zero，非零256步；1238.082s/1006587904B，swap0；shared-workstation | `COARSE_INVERSE_NOT_QUALIFIED` | [严格CSV](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv) |

所选NN的validation原方程loss为1.837990301367067，初始线性映射为1.6581681312213055；离线native目标记录LINEAR_BASELINE_PREFERRED，两者部署资格均失败。所有official R/T/A/A_volume、R00_s/p/total、80通道复振幅/功率、复E/H、场/scaled-curl与能量闭合均not_run，F4没有合格路线所以不嵌入p6。G-time/G-memory inconclusive、G-neural无正信号，不能把去因子或表示改善算给NN；teacher/oracle/train/各候选成本分别记录，不累加RSS峰。CPU现场选核、16GiB整树阈值/own swap0、额外128GiB邻增长余量、独立FE/ML/缓存保护邻任务，未改原watchdog/锁；PSI无持续压力但无可比阶段吞吐，不能宣称零影响。原p6实际物理解、三合格计时、5/2/0.7nm/几何泛化全部not_run。无production/default或master merge approval；仅推送执行分支后等review。[Summary](task042_neural_coarse_inverse/outcomes/summary.md)、[Response V2](task042_neural_coarse_inverse/response_v2.md)。


# 4. 今后新增模型的登记模板

每次正式计算至少新增一行主表，并按可用性新增衍射级和复振幅表。

## 4.1 主模型表模板

| Task | Model ID | 配置 ID | 研究目的 | Full3D/Hybrid | 原始完整矩阵/静态凝聚/自适应 | direct/iterative | 网格类型 | p/h | cells | FE DoF | active rows | matrix NNZ | factor NNZ | MPI/threads | residual | R00 | Rtotal | Ttotal | Avolume | Aclosure | peak RSS/PSS/cgroup | build | MUMPS setup | iterations/solve | total | status | evidence |
|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 4.2 显著衍射功率模板

| Model ID | R(0,0) | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | Rtotal | T(0,0) | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | Ttotal | Avolume | Aclosure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 4.3 显著衍射复振幅模板

| Model ID | r(0,0) | r(-1,0) | r(-2,0) | r(-4,0) | r(-5,0) | r(-7,0) | t(0,0) | t(-1,0) | t(-2,0) | t(-4,0) | t(-5,0) | t(-7,0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 4.4 失败或未完成模型模板

| Task / Model ID | 探索目的 | 实际运行到哪一步 | 实际数值 | 未满足的具体物理量/资源 Gate | 直观原因 | status | 下一步或停止理由 | evidence |
|---|---|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 不得只写“10/12”或“失败”，必须列具体通道和数值 | 待填写 | 待填写 | 待填写 | 待填写 |

---

# 5. 当前数据缺口与后续自动化

1. Task000–035d 已逐项回填；Task035e 已登记 sealed certification、三条
   structured global-p6 endpoint、Path A cycle-0 stage/shadow、两条
   selected-p negative、M1、projection negative 和 goal-oriented trace
   negative，但尚无 accepted adaptive candidate、hidden final audit、
   iterative 或 Hybrid。早期没有保存的 source SHA、geometry hash、
   12 通道、factor NNZ 或 PSS/cgroup 明确标成“历史未记录”。
2. Task032–034 的 heavy JSON 包含比总账更细的衍射级、场误差和资源字段；总账保留权威 evidence path，不建立第二份易漂移的逐字段副本。
3. COMSOL 参考只计算零级；非零衍射级不能写 0。
4. 不同物理配置、偏振、网格和软件之间的数值只能做标注清楚的横向参考，不能混成单一收敛序列。
5. 新任务不得以未填写占位词收口；历史缺口必须说明“历史未记录”，当前未运行项必须写 `not_run`。

---

# Task038-extra Review V2：T5/R4 bounded iterative lane

本条登记的是当前分支上的 authority、sweep 和资源边界，不是完整 Maxwell PDE 结果。`action` 只表示当前离散算子的向量作用；`sweep` 是两个 z-slab 的固定 forward/backward 残差传播；`transmission` 是 slab 间边界数据动作。Candidate C 只替换人工 PC transmission，不改变 exact physical action、材料、Floquet phase 或 Maxwell 弱式。

| Model ID | source / identity | method and scope | measured result | resource / status | evidence |
|---|---|---|---|---|---|
| `task038_t5_R1_identity` | clean R1 source `cd1ca8dfe6fdcc7a526d2794d2963dd6cd81a470`; final code/evidence source `ea7fc96b8c95eca13b5ee8055d7e0762f9ab02dc` | current structured physical identity vs historical W5 identity；252 hexahedral cells、p6/h10、13.5 nm | geometry witness exact；old mandatory wavelength/Floquet/orientation/quadrature/H fields unavailable；old/current RHS relative L2 `10.934736136386151` | `PASS` as fail-closed historical classification；not a same-physics claim | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/t5_physical_identity_v2.json` |
| `task038_t5_R2_current_dual_oracle` | source `09b926428babc2f0a8dd4b4061b7e18d7dd23aba` | fresh component/direct oracle；p2/p3 MPI1 and p6/h10 MPI1/MPI2；no PDE | max relative L2 p2 `8.692664947436813e-15`、p3 `2.5937308039595027e-14`、p6 `4.559266389658486e-14`; all-mode/group recompose 0; repeat `<=7.611020931512763e-17` | `PASS`; current dual only | R2 compact records and ignored `r2_09b9264` raw/check |
| `task038_t5_R3_current_historical_state_residual` | source `2c8fca90c7300b85b30021081868b699c0b306d2`; source name `CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE` | current `b-A_current x_old` after primal canonical mapping；MPI1/MPI2；no old PC replay/scaling | primal roundtrip `1.3336463445521434e-17`; residual closure `2.381515544959568e-18`; mapped primal pair `1.4389898139779045e-17`; residual pair `1.145631881739048e-14`; repeat 0 | `PASS`; Path A remains not qualified；process-tree watchdog provenance未测，不是 resource qualification | `t5_long_tail_authority_v2.json` and ignored `r3_2c8fca90` |
| `task038_r4_candidate_A` | formal source `1a4d495a4f7a78bafb389ab9b30d0b49fe7bd5be` | fixed first-order Robin PC; two-slab residual propagation；MPI1 physical/gradient only after fail-fast | physical rho `0.8145890334049838 > 0.60`; gradient rho `0.8889127715646881 <=0.90`; closures `1.2458376041083906e-16` / `1.271047984953834e-19` | physical numerical contraction fail; gradient pass；remaining 8 `not_run_by_fail_fast`; not implementation failure | `t5_sweep_candidate_a_v2.json` |
| `task038_r4_candidate_B` | final source `ea7fc96…` | intended propagating/near-cutoff interior modal transmission | no numerical value; current interface mixed Si–Si/Si–air and T3 authority only exterior | `NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED` | `t5_sweep_candidate_b_v2.json` |
| `task038_r4_candidate_C` | final source `ea7fc96…` | focused fixed second-order local impedance authority; one p6/h10 physical formal attempt | focused tests pass；formal worker stopped before record | `CONTROLLED_STOP_HARD_12_GIB`; process-tree peak `12,942,209,024 B`, wall `406.7977727999969 s`, swap 0, return `-15`, `hard_stop_12_gib`; rho and formal payload not run | `t5_sweep_candidate_c_v2.json` and ignored watchdog raw/compact |

R4 overall is `FAIL / CONTROLLED_STOP_RESOURCE`; R5/T6-S, T6-F, official E/H/RTA, R/T/A, T7–T9 and full 0.7 nm remain `not_run`. The `<2 GB` strategic target is not met: Candidate A's 5.145 GB and gradient's 1.324 GB are sweep process-tree observations, not full PDE memory certification. `outcomes/summary.md` and `docs/development_progress.md` remain T9-closeout records and are intentionally not rewritten as completed.

## Task038-extra Review V9：P1 memory-first controlled negative

本条登记 Review V9 P8 的正式受控负结果，不改写旧 Task038/V8 negative。memory-first 是每 20 步释放 GMRES 基、只保留当前解并重算显式真残差，以控制长期内存；它不保证高 p 阶在固定迭代上限内收敛。

| Model ID | source / scope | measured result | resource / status | evidence |
|---|---|---|---|---|
| `task038_v9_P0_memory_first_authority` | P0 fresh source `ba9016310d09c388a953fce93d9e71761343311f`；p2/h50/MPI1 | checkpoint/restart、explicit residual、PC legality 和 provenance PASS | P0 PASS；不是 p6/PDE 结果 | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_authority_contract.md` |
| `task038_v9_P1_memory_first_small_v2` | source `891ef7fba8cb7d154ad9cac61d67652f02063fbb`；p2/p3 × MPI1/MPI2，固定 `restart=20`、`max_it=2000`；实际 9/16 | 8 p2 cases PASS；`p3-mpi1/random` 在 2000 steps 后 explicit true residual `0.01027838962263555 > 1e-8` | `FAILED_AT_FIXED_MEMORY_ITERATION_CAP`；p3 cycle process-tree peak `155860992 B`，process-tree/rank swap `0`，GNU time `Swaps=0`；共享 cgroup 只作 diagnostic，不是 dedicated Gate | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/memory_first_small_v2.json`; `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json`; `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2.md` |

P1 剩余 7 个 frozen cases 与 P2–P7 均为 `not_run_by_gate`。本登记不包含 p6 setup、PDE、official physics 或 `<2 GB` complete-workflow authority；完整 raw arrays/checkpoints 仍在 ignored formal root，compact 只保存 hash-bound 标量摘要。

## Task038-extra Review V10：Q0 exact-reference controlled negative

本条登记 Review V10 Q0 的正式受控负结果，不改写 V8/V9 的历史结论。Q0 用小模型 exact LU/MUMPS 辅助 solve 检查当前 LOR-HX 路线的基础代数；它不是 production PC、p6 或 Maxwell PDE 结果。

| Model ID | source / scope | measured result | resource / status | evidence |
|---|---|---|---|---|
| `task038_v10_Q0_exact_reference_p3_mpi1_random` | source `47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f`；p3/h50；MPI1；random；Reference E/N | E exact edge residual `9.13154427545479e-16`，但 500 步后 explicit rho `4.203423379090078e-4 > 1e-8`；N 四项 direct nodal residual `5.134041203635995e-16–5.241317476841507e-16`，final rho `2.1958595524302254e-3` 仅 diagnostic；N pre evidence composition `2.8019257502717445` | `LOR_AUXILIARY_FOUNDATION_FAIL`；cycle process-tree RSS `185102336 B`，swap `0`；GNU time Maximum RSS `293908 KiB`、Swaps `0`（单 worker 口径） | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/p3_exact_reference_triage.md`; `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json`; `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1_checker.json`; raw root remains ignored at actual command path `benchmarks/artifacts/task038_extra3d_q0_v10/47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f/p3-mpi1/random` |


## Task038-extra Review V19：PML 双向扫描 R0 真实结构

PML 是局部边界外的人工吸收层，local inverse 用局部物理算子近似开放边界；它的代价是额外局部网格、系数和编译工作集。本条只登记 R0 结构/资源证据，不把小型 fixture 或结构算术提升为 full PDE authority。

| Model ID | source / scope | physical and algorithm | measured result | status | evidence |
|---|---|---|---|---|---|
| task038_v19_R0_p2_structure | measurement baseline HEAD afa0aa066de67557cddaa80901c3cf7710833abe；MPI1、p2 focused fixture；measurement worktree dirty | local PML Maxwell action、stretch-one map、owner dual/primal map、PoU；同一 MUMPS factor symbolic→numeric→solve | local action 1.440782276734707e-15；MUMPS residual 1.7250761895437276e-13；INFOG16=50；predicted peak 230830208 B | measured PASS；不是 p6/PDE qualification | [V19 R0 outcome](task038_extra_full3d_iterative_0p7nm/outcomes/pml_double_sweep_real_structure_v19.md) |
| task038_v19_R0_p6_inventory | same measurement baseline；p6/h10、degree6、4 core、3 interfaces | exact split volume action + streaming DtN；PML 只在 local subdomain；global transfer matrix/numeric allgather=false | 173802 rows、252 cells、14 layers；trace rows 1350/1350/1350；support-union count 190855440；matrix_assembled=false | measured structural anchor | [V19 compact](task038_extra_full3d_iterative_0p7nm/outcomes/records/pml_double_sweep_real_structure_v19.json) |
| task038_v19_R0_p6_symbolic | same baseline；真实 p6/h10 local PML resource preflight | local mesh 后进入 FFCx C 编译；尚未完成 local form、AIJ、MUMPS 或 outer Krylov | sampled RSS 8609562624 B ≥ watchdog cap 8585588736 B；sampled PSS 8580238336 B；timeline swap 0；已观察样本内 hard 12 GB 未触及，尾段未知 | REAL_ANCHOR_REFERENCE_RESOURCE_BLOCKED；partial evidence，R1 not_run | [V19 compact](task038_extra_full3d_iterative_0p7nm/outcomes/records/pml_double_sweep_real_structure_v19.json) |

R0 不改变旧 V16–V18 结果；R1/R2/R3、official E/H、near-field、R/T/A、recovery 和
0.7 nm/2 TiB scalable solve 均 not_run。p6 local object file 在最后 timeline 后才落盘，
因此完整同期 process peak 与 cache closeout 仍是 unknown；不得把该条目登记为已通过的
production model。

## task39extra Review V5：5 nm Si p6/h4 q4 F5 完整场

| run / source | 数值与物理结果 | 资源与状态 | evidence |
|---|---|---|---|
| `20260923T231207.264441Z` / `b468907cf54d04280b461cae5fc9078186302d54`；input `03a9992d576612335135fa22f25192f97754feb4a281e6c06ce29534e4095d36`；3780 cells、p6/h4、600 DtN channels | 121步；explicit A6 residual `8.60422e-7`；244/244 p4 returns `<=1e-10`、最多1次 refinement；`BALANCED_OUTPUT_PASS` 与旧5 nm 同物理 `MATCHED_REFERENCE_PASS`；全场 L2/scaled-curl `7.20455e-8/7.16517e-8`；R/T/A/A_volume=`0.733183508848/0.000222439621/0.266594051531/0.266594036660`；energy closure `1.49e-8` | workflow `22680.912 s`、solve `10671.216 s`；整树RSS峰 `38,934,622,208 B`、swap0；watchdog completed/cleared。后续独立setup-only须另立run身份，不代表完整物理结果。 | [F5 compact](task39extra_para_workstation_capacity/outcomes/records/f5_5nm_q4_terminal_compact_v1.json) |
| `F5_GEOMETRY_EQUIVALENCE_COMPONENT` | 同一5 nm Si物理/材料输入；派生105-cell网格；每阶18个raw类→9个tensor组；4个实际零阶mode | 逐raw类代表tensor、A6、Aq、p4原A4及独立增广port RHS检查通过；仅组件资格，非完整setup/600通道/资源PASS | [105-cell compact](task39extra_para_workstation_capacity/outcomes/records/v5_5nm_geometry_105_component_v1.json) |
| `F5_SETUP_ONLY_V5` | run `20260924T092250.568977Z`、source `96057565d171077cc84a8dae3cd4eb88b6ff21ea`；同一5 nm Si input/physical SHA；3780 cells、p6/h4、q4、600 channels | `SETUP_ONLY_COMPLETED`、setup checks PASS；setup `2023.440526 s`，workflow `2028.390414 s`；p6/p4各175 raw几何类实际并为6个近似tensor组，kernel `292.039/33.847 s`；RSS峰 `37236830208 B`、6192样本全可读、swap0、后代清场。`outer_solve/full_a6_recovery/RTA/checker=NOT_RUN`，不构成新完整数值/物理资格；当前分组策略仍待完整F2场验证 | [setup-only compact](task39extra_para_workstation_capacity/outcomes/records/f5_setup_only_v5_compact_v1.json) |


### 3.43.2 V3：唯一几何重叠结构诊断，旧负结果保留

用户授权一个有限批次，原fixed original13.5nm/p6h10对应p4、252cells、80完整DtN、A4/port/recovery1e-10保持。新结构把真实FE边/面和Floquet master支持重叠起来，252个272行块，factor含cell/port302047392B，构造前预算，部署无global p4 LU/私有audit CSR/fallback。新与旧数据都只作consumed诊断；freeze后另选未消费pool而未运行。

| 已消费诊断RHS / index | 旧B0原A4 | 新GEO原A4 | 新GEO port closure | 新GEO port绝对残差 | 末32步Schur降幅 | 严格返回 |
|---|---|---|---|---|---|---|
| physical_PH_b6 / 0 | 0.998654967105 | 0.891957825531 | 0.00773091335604 | 0.187210874612 | 5.70298292157e-06 | False |
| unseen_port_only / 10 | 0.954192801905 | 0.935861877336 | 0.725338952963 | 0.000935056697255 | 1.23982140442e-05 | False |
| unseen_mixed / 11 | 1.000780838 | 0.932010701839 | 0.677921290639 | 0.000951255917368 | 1.24422653291e-07 | False |

新数值源：reuse b158c5301e7ff59000b15b335672afdb61c5e5e1，结构7fc3f1434cf4f38f43e5244ebfed3a19d0780a26；clean/真实source绑定，文档HEAD不替代。两阶段wall2636.49526309s、整树峰1074900992B、swap0，CPU现场选核/math1/16GiB监督，shared-workstation/perfinconclusive；无零干扰证明。CPU纠正oracle33和F4-B045，旧CPU0概括不准确。固定Q上LIN已精确最小native残差，本轮不训练NN、不扩大rank或迭代。

严格粗逆未合格，量级1末段停滞触停止，实际误差空间对照/新teacher/fresh资格/F5/official RTA、场、通道/短波/GPU全部not_run；BOUNDED_STRUCTURAL_GLOBAL_STAGNATION，research-only待review不merge。[V3 response](task042_neural_coarse_inverse/response_v3.md)、[source/资源](task042_neural_coarse_inverse/outcomes/records/run_index_v3.json)、[实际结构](task042_neural_coarse_inverse/outcomes/records/structure_complete_v3.json)、[旧48项失败](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv)。


### 3.43.3 V4：有界全局误差与平衡两层，真实代数通过而收敛未资格化

局部PC修正相邻区域后仍可能留下全局误差。本批固定原几何局部步骤，再用有限全局解方向处理它可表示的残差，比较旧解POD与真实停滞解误差空间。两条都使用同一完整Schur两层公式/128容量；空间内自检不能代替外部RHS严格验算。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `T42_V4_P1_ERROR_SNAPSHOTS` | source8b792d78b06903ef874fbcf14fa06d951ae9c2ff；原train12–27、16独立whole_problem | 原13.5nm/p6h10对应p4、252cells、80DtN；n21824 | 固定B/RIGHT32，64步，各8快照；准确teacher归一化同坐标，未用诊断/测试解 | 128非零误差；teacher原native最大1.827e-13，误差关系最大7.475e-15；独立candidate无global factor | `TRAINING_ERROR_SNAPSHOTS_COMPLETE`；局部停滞仍允许构建空间 | [快照manifest](task042_neural_coarse_inverse/outcomes/records/training_snapshot_manifest_v4.json) |
| `TWOLEVEL-OLDPOD-V4` | source5691d79abe87d3582ede5bbaf8369c5487e7c392；旧256train的Q；新Schur U/R | 同原A4/Schur/MPC、full80；53084 FE/21824reduced、8184464NNZ | rank128、C+(I−CS)B(I−SC)，RIGHT32/max256/zero | Rcond334.013；三诊断原native .998588/.949243/.905074；全部256步/strict0/3；302309536B全局部＋R因子，89391104B Z＋U | `BOUNDED_TWOLEVEL_NEGATIVE`；无global p4 LU/私有CSR/fallback，非production | [两层与Gate](task042_neural_coarse_inverse/outcomes/records/gate_decisions_v4.json) |
| `TWOLEVEL-ERROR-V4` | 同5691source；16 train轨迹、128真实解误差，未泄漏 | 同原physical/operator/mode SHA；无F5/p6外层 | 同rank128/同Schur范数/同B/同两层公式/同256预算 | Rcond586.120；三诊断原native 0.999863649936/0.937175812499/0.901084822725；strict0/3；formal全批wall1534.00828393s、同时整树峰1128828928B、swap0 | `BOUNDED_TWOLEVEL_NEGATIVE`；P4未解锁，既存终测未消费 | [完整结果](task042_neural_coarse_inverse/outcomes/two_level_global_error_v4.md)、[source/成本](task042_neural_coarse_inverse/outcomes/records/run_index_v4.json) |

正式source真实绑定，文档HEAD不替代。六阶段fresh核查后均CPU0/MPI1/math1，own lock/整树16GiB监督/独立cache，只有自有优先级降低，无neighbor或GPU修改；shared-workstation、performance inconclusive。没有把V3昂贵审核成本相减当新加速，没有新teacher/NN训练，G-neural not_run。原V1–V3 task/review/response/负结果逐字保留；Formal Review V1替代V3“局部量级1停滞禁止全局空间”。P4/fresh资格、F5/official RTA/A_volume/场/正式通道/短波均not_run。仅Task042分支待review，不merge。


### 3.43.4 V5：固定operator的失效定位（非新solver资格）

本轮把相同残差交给局部B、两个粗空间C和原B2，再看保留方向的小最小二乘，分辨空间不足与组合失效；新probe只在U正交补中测完整输出，不把小投影矩阵当全局谱。3个原已消费RHS仅两个whole families，12共同state全部真实可用，准确teacher只离线审核三行且不进入PC。没有新训练/换基/长KSP，旧负结果保留。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| LOCALIZATION-OLDPOD-V5 | source5d82651af0f723c73487783deb43969f05d46ed3；旧冻结basis hash见run index；12共同states原0/10/11 | 原Si13.5nm/p6h10对应p4、MPI1/full80；53084 FE/21824 reduced、8184464NNZ | 固定B/Z/U/R rank128；12同r×8原审核、16补空间probe；无新KSP | 完整TV最小奇异值4.771224799；树RSS/阶段cost见run index；无global p4 factor | FIXED_OPERATOR_LOCALIZATION_COMPLETE；strict0/96诊断修正，非production | [同向量定位](task042_neural_coarse_inverse/outcomes/failure_localization_v5.md) |
| LOCALIZATION-ERROR-V5 | source5d82651af0f723c73487783deb43969f05d46ed3；旧冻结basis hash见run index；12共同states原0/10/11 | 原Si13.5nm/p6h10对应p4、MPI1/full80；53084 FE/21824 reduced、8184464NNZ | 固定B/Z/U/R rank128；12同r×8原审核、16补空间probe；无新KSP | 完整TV最小奇异值3.034800156；树RSS/阶段cost见run index；无global p4 factor | FIXED_OPERATOR_LOCALIZATION_COMPLETE；strict0/96诊断修正，非production | [同向量定位](task042_neural_coarse_inverse/outcomes/failure_localization_v5.md) |


四正式阶段wall1144.401529s、整树同时峰1135407104B/own swap0；两空间有效rank128/128，补空间16/16。shared-workstation、performance/邻影响inconclusive，MPI1/math1、实时CPU0/0/0/13/own lock/16GiB监督/独立cache；不动邻任务，未委派cgroup不声称内核连续限额。物理eta_r接近1、OLDPOD eta_e≈.222 vsERROR≈.713；port-only保留Z＋Br的Schur反事实较好，但原A4/port失败，未确定唯一根因或真实奇异。唯一建议需后续review、未实施；seed420620 fresh/F5/p6/短波/GPU/NN/official RTA/A_volume/场/衍射均not_run，无神经收益归因。[hash/source/分阶段账](task042_neural_coarse_inverse/outcomes/records/run_index_v5.json)、[原独立Gate](task042_neural_coarse_inverse/outcomes/records/independent_checks_v5.json)。


### 3.43.5 V6：神经FE单次求解micro接口，材料阻塞

本批让坐标网络通过原有限元边／面矩生成trace，尝试直接求目标场；增加优化与反向作用成本，尚无solver收益。Review V3关闭原小局部块／固定低秩／系数网络p4路线，V5 augmentation未实施；本条新增阶段，原模型／负结果全部保留。

| Model ID／数据身份 | 物理／几何与离散 | 实际unknowns／算法 | 数值／资源／具体阻塞 | 状态与证据 |
|---|---|---|---|---|
| NEURAL-FE-MICRO-INTERFACE-V6／measured geometry+interface | 0.7nm设计，居中micro三维缺口；Si n/epsilon/source unknown；384 hexa p3、MPI1；FE34050／trace18144／slave2082 | FP64、3×64 tanh、8三分量复载波、11696参数；完整边／面矩和原MPC，仅trace表示；内部13824/完整物理port未构造 | FE插值差约1.8e-15、q15/q30差1.1695e-15；合成梯度FD9.7612e-9；原S/NNZ/完整原残差/EH/RTA/A_volume/通道功率均not_run。三formal wall26.136697164s，树RSS314408960B/own swap0，CPU0/0/12 | MATERIAL_0P7NM_BLOCKED、局部N1接口通过、完整N1未通过；[结果](task042_neural_coarse_inverse/outcomes/neural_fe_single_solve_v6.md) |
| NEURAL-TRACE-V6／not_run | 同一review目标Si材料和完整DtN不足，top20通道仅derived、bottom/total unknown | 计划网络trace＋全部复port；Adam500＋L-BFGS／最多2000 closure和2h，实际0 | 原S/Sᴴ/native/port/恢复Gate未具备；无准确解／teacher／训练／物理解 | not_run、神经增量unknown；[三路线](task042_neural_coarse_inverse/outcomes/records/neural_fe_comparison_v6.csv) |
| FREE-FE-OPT-V6／not_run | 同一未完整冻结micro operator | 计划全部独立trace＋port自由实虚参数，同loss/optimizer/zero start，实际0 | 材料／完整N1阻塞，不能形成可比基线 | not_run；[独立Gate](task042_neural_coarse_inverse/outcomes/records/neural_fe_gate_decisions_v6.json) |
| FE-LSQR-V6／not_run | 同一未完整冻结micro operator | 计划原S/Sᴴ、无PC、最多2000配对和2h，从零；实际0 | 未构造真实S；无solver／参考／E/H／功率或离散资格 | not_run，最终目标48h NOT_QUALIFIED；[预算](task042_neural_coarse_inverse/outcomes/records/target_48h_budget_v6.json) |

成功接口run source2a2cb4af78ba869a26a1254b4b4b76c9ac158366，首次居中坐标载体错误source64c128c3541887e22788343692cc4f7832a45696保留；一次最小research修复，普通默认/原FEM/Floquet不改。用户Task042受控共享CPU授权继续，既有FE/ML独立环境/缓存、MPI1/实际线程1、自有锁/16GiB树监督、GPU0；无cgroup委派不冒称连续内核限额，只监督自身树，未发现持续压力，邻影响／性能inconclusive，全部shared-workstation。无global目标/p4 factor、Riesz/ILU hidden inverse、private audit CSR或目标准确解读取，旧teacher和seed420620不消费。参考/enrichment/F5/p6/最大目标均not_run；目标材料／尺寸／通道／实际配额／完整步成本／所需步数unknown。唯一下一最小步骤为核验Si0.7nm材料来源和数值身份，不自动实施或merge。[运行源／全过程成本](task042_neural_coarse_inverse/outcomes/records/run_index_v6.json)、[Response V6](task042_neural_coarse_inverse/response_v6.md)。


### 3.43.6 V7：用户材料下三路线单次求解micro，全部未资格化

网络通过原Nédélec边/面矩生成当前目标trace，单元内部用原局部方程恢复，全部端口单独优化，尝试省去global分解；代价是新增训练和原S/Sᴴ作用。材料已经永久ready，原V6阻塞和旧p4负结果不回写。唯一canonical四波长表SI_OPTICAL_CONSTANTS_USER_20260929_V1在input/materials/si_optical_constants_v1.json，0.699999988→nominal0.7明确alias，Si n=0.999885140474+4.32477054e-6i、epsilon=n*n，空气1。模型固定384hex/p3/h0.175nm、三维缺口、MPI1、full40DtN；FE34050/trace18144/interior13824/slave2082，physical2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de。

| Model ID／source及数据身份 | 未知量／算法 | 原残差／同离散场／功率 | 全树费用／具体停止 | 状态／evidence |
|---|---|---|---|---|
| NEURAL-TRACE-V7／7c4037a279cefd8546c51e8ae6cf0172c3eab89d | 固定11696 FP64网络参数＋40复port；完整原矩→trace；Adam500、L-BFGS history20 | Schur0.913263145、native0.661163226、port op0.003140447；全场L2差0.069196457、闭合0.07034118 | wall7149.384082808s、RSS760279040B、1611closure/48完整L-BFGS外层，时间预算停；swap0 | CONTROLLED_NUMERICAL_NEGATIVE；[对照](task042_neural_coarse_inverse/outcomes/records/neural_fe_comparison_v7.csv) |
| FREE-FE-OPT-V7／同7c4037a2完整source | 18184复trace/port自由参数，同loss/optimizer/zero start | Schur0.797338565、native2.179411163、port op0.446120482；L2差0.105509404、闭合0.00733968 | wall592.483452100s、RSS753737728B、2000closure/69外层，closure预算停；swap0 | CONTROLLED_NUMERICAL_NEGATIVE；[全审核轨迹](task042_neural_coarse_inverse/outcomes/records/convergence_checkpoints_v7.csv) |
| FE-LSQR-V7／同7c4037a2完整source | 原S/Sᴴ、无PC/逆、零初值；包含审核的2000作用限额 | Schur0.071602580、native0.028727752、port op0.656567941；L2差0.104639933、scattered差0.999953257、闭合0.00337133 | wall564.795250180s、RSS560558080B、1921步/S1999/SH1922，action预算停；swap0 | CONTROLLED_NUMERICAL_NEGATIVE；[独立Gate](task042_neural_coarse_inverse/outcomes/records/neural_fe_gate_decisions_v7.json) |
| BLIND-P3-REFERENCE-V7／factor19adac7e3babb50c0028714684c220b713979196，验证1ff6f8ba3dcb48dee0fd41f762bf624822ea1457 | 三候选冻结后独立18184行/3901384NNZ一次p3 LU；销毁后原FE/EH/功率 | Schur6.424e-12、native3.018e-12、独立native1.437e-12；R/T/A0.117645819/0.877047783/0.005306398、A_volume0.005306398、闭合2.906e-12 | 初次14.456428306s后处理Form错误，最小修复仅验证25.633409183s、无新LU/solve；树峰1073967104B | SAME_DISCRETE_REFERENCE_ONLY；非部署/训练依赖、p-enrichment未准入；[复E/H/全通道/功率](task042_neural_coarse_inverse/outcomes/records/independent_blind_validation_v7.json) |

真实N1 source70f5f5437533693e343ede67a37363e89b062330，原S/adjoint/native/恢复最大8.491e-15、真实FD最大1.8213e-9，完整40通道与原MPC不改。三候选从构建起无global p4层/factor、global FE CSR/LU、Riesz/ILU inverse、私有audit CSR或hidden fallback/准确目标解初始化。保存局部原张量/恢复和padded端口packet209239672B、网络/optimizer/激活/工作区，并非只有93568B模型参数。完整复振幅与逐级功率在[channel CSV](task042_neural_coarse_inverse/outcomes/records/channel_observables_v7.csv)；候选RTA只为未资格化诊断，参考未证明continuum。p/h/M/MPI未扫描。

8正式stage wall8579.825040766s、同时树采样峰1073967104B/own swap0；V6 carry101.861302031s和全部辅助/失败/后续检查费不重置。用户Task042受控共享授权继续，MPI1/math/Torch1/实时核/own lock/16GiB hard与12GiB warn/独立缓存，CPU-only/GPU0；无cgroup委派不称内核连续限额，邻任务/其锁环境监督不改，无持续PSI触线，影响和性能inconclusive，全部shared-workstation。

神经场有部分信号，仍方程/场/功率0/3，神经增量NOT_DEMONSTRATED；NEURAL_OPTIMIZATION_NEGATIVE。p4 enrichment/final目标/48h/F5/p6/旧teacher/seed420620/四波长扫描not_run；目标尺度/通道/配额/步cost/所需步数unknown，材料已ready。唯一下一建议为固定pilot目标解无关的对角变量尺度均衡LSQR对照，原loss/验算保持，未实施/需review，不回旧p4或自动更大模型。32相关pytest及局部静态/Markdown通过，Review V4实际GitHub4表1math，历史原文保留。[Response V7](task042_neural_coarse_inverse/response_v7.md)、[全费用/source](task042_neural_coarse_inverse/outcomes/records/run_index_v7.json)。


### 3.43.7 V8：尺度负结果，等价批量化工程观测

本轮固定原0.7nm/384hex/p3/40port对象，只将列单位均衡以及同网络八单元同时计算，另修复异常保存边界，三项独立。C1七测试PASS；C2唯一D由原组装S列范数、setup无factor，1915步/S1999/Sᴴ1919最终Schur0.068283273738/native0.026675035784/scattered L2差0.998598490718，严格/研究均失败。C3三状态full trace/loss/grad/clone Adam/FD等价PASS，固定参数三pair中位降幅48.55%，35107584B缓存，不训练、不把成本收益写成解通过。初次C2额外未用3369888B moment包在新source最小收口，原真实RSS/数值保留，无完整重放。

11正式supervised wall791.658916180s/树峰816152576B/own swap0/无GPU；全aux/失败/V6+carry不重置，最终资源账linked。受控共享CPU/MPI1/mathTorch1/DataLoader0/自有锁/16-12GiB树监督/独立cache保持，无cgroup内核连续保证，邻任务不操作；无持续PSI压力，影响与无争用加速INCONCLUSIVE。旧p4仍关闭，最终0.7nm/48h、神经数值增量未资格化，target单步/步数/存储unknown。唯一下一建议：固定pilot上仅对已经冻结的误差方向做原S/恢复/端口分量审核，复用已有p3参考作离线核对，定位残差下降为何没有恢复散射；不训练、不建新PC、不扫描。 未实施，停止等review，不merge。[Response V8](task042_neural_coarse_inverse/response_v8.md)、[完整结果](task042_neural_coarse_inverse/outcomes/scaling_and_execution_v8.md)、[最终费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v8.json)。


| 新登记模型／角色 | 固定库存与来源 | 数值／工程状态 | 时间与内存口径 |
|---|---|---|---|
| FE-LSQR-COLUMN-SCALED | 同384hex/p3/0.7nm，D来自原S列范数，18184 rows/40port；source1a2984a完整见run index | Schur0.068283273738/native0.026675035784/scattered差0.998598490718，严格及研究FAIL | setup树wall6.818829s/RSS641200128B；solve树563.163265s/RSS553803776B，shared-workstation |
| NEURAL-TRACE-BATCH8-EXECUTION | 同11696参数/8载波，全q15矩与MPC，source52d47d3完整见run index | 三状态等价PASS，三pair中位降幅48.55%；工程观测，未新训练/无数值增量 | cache35107584B，含warmups/全部样本与cold setup见batch_costs_v8；本批最大树RSS816152576B |
| TARGET-0P7NM-48H | micro不是最终目标，目标规模/通道/步数/误差预算unknown | NOT_QUALIFIED，不扩大模型 | 无外推／预测冒充实测 |


## Task042 V9：固定误差定位完成，旧求解负结果保留

| 对象／阶段 | 本分支新增结果与边界 |
|---|---|
| 0.7nm/384hex/p3/40端口/MPI1 | Z0/NN7/FREE7/LSQR7/LSQR8/REF7共6状态；D0–D4完成，无新solve/train/LU/PC/loss |
| 误差与真实场 | Se=r-r_ref≤2.925e-12，齐次恢复≤3.082e-16；NN散射范数比0.457259/相关0.999809，LSQR7/8幅值约0.26%/0.37%，均未资格化 |
| 区域／原作用 | y分量和上下(0,0,s)主导，全域四区分布；LSQR8方向增益0.0683784、体/port抵消0.059273/0.000209768；根因未唯一确定 |
| source／共享费用 | a1dc3466294c30b6de292468d6dd1aa9b685b193；唯一stage234.760s、树峰0.939442GiB/swap0；首次checker失败保留，e21仅数组审核修复 |
| 资格／下一步 | FIXED_ERROR_DIAGNOSTIC_COMPLETE≠solver PASS；原V7/V8及旧p4负结果保留，最大0.7nm/48h仍NOT_QUALIFIED；只建议后续有界原V内部作用平衡检查，未实施 |

身份、40复通道、区域、方程分量与累计资源见[Task042 V9](task042_neural_coarse_inverse/outcomes/frozen_error_localization_v9.md)、[Response V9](task042_neural_coarse_inverse/response_v9.md)。受控共享CPU授权继续，无cgroup委派不冒称连续限额；未观测持续PSI压力，邻影响INCONCLUSIVE。原seed420620封存，不改变其他Task合同/记录，不merge。


### Task042 V10：固定0.7nm micro-pilot输出头／端口对照

| 模型／机制 | 实际残差与场／功率结果 | 最终分类 |
|---|---|---|
| 原Full3D384hex p3/40复端口，A NN7复幅相＋port | Schur/native0.912888/0.687417；scatter E/H差0.634723/0.634718；R/T/A_balance/A_volume0.0889836/0.835105/0.0759116/0.00502812 | CONTROLLED_NUMERICAL_NEGATIVE |
| 同对象B1已学习隐藏＋1600列薄方程LS | Schur/native0.797694/4.381516；scatter0.700726/0.700810；R/T/A/Avol0.0845095/0.796652/0.118838/0.00484248 | rank1600，未合格；包含原7143s训练成本 |
| 同对象B0随机隐藏＋同薄LS | Schur/native0.797324/10.964503；scatter0.732080/0.732146；R/T/A/Avol0.0851194/0.798195/0.116685/0.00485441 | rank1600，随机loss略优B1，未合格 |
| 同对象C原Hhat精确40端口闭合＋同B1隐藏 | Schur/native0.798258/0.309567、port6.509e-17；scatter0.697842/0.697932；R/T/A/Avol0.0843697/0.796538/0.119092/0.00484248 | rank1560，只解决端口/native放大；NEGATIVE |
| D1/D2 offline diagnostic | 同空间参考拟合E差约0.001025/curl约0.00320；LSQR8误差curl/mass≈10.402、V0.04745，重组1.697e-14 | 非求解/非训练；多因素仍INCONCLUSIVE |
| E/P/最大0.7nm/48h | 无P/P+与原完整方程资格，未做50步隐藏更新/p4 enrichment/放大 | NOT_RUN_NOT_ADMITTED；最终NOT_QUALIFIED |

以上新R/T/A全部未资格化诊断、不是official物理结果；原限值方程1e-6/场1e-4不变。R00_s/p与完整40复通道及参考面见[候选](task042_neural_coarse_inverse/outcomes/records/candidate_comparison_v10.csv)、[通道](task042_neural_coarse_inverse/outcomes/records/channel_observables_v10.csv)。原材料表及physical/mode/action identity不变，p/h/MPI/波长影响未扫描；原NN7接受unknown保持，reference在冻结后独立验证，D后禁回训。

12正式含失败/replay wall650.093757705s、同时树峰2.213718GiB/own swap0；全aux/继承训练/设置及历史费用见[resource](task042_neural_coarse_inverse/outcomes/records/resource_costs_v10.json)。共享CPU MPI1/线程1、独立cache/自有监督/原25200s总窗口，无GPU/邻任务修改，性能与影响INCONCLUSIVE。无global p4 LU/新global S/CSR或hidden inverse；旧路线关闭，旧Task/results不改。全部可执行路径完成后提前收口，唯一下一制造RHS建议仅建议未执行，待review不merge。[Response](task042_neural_coarse_inverse/response_v10.md)、[完整证据](task042_neural_coarse_inverse/outcomes/autonomous_neural_head_v10.md)。


### Task042 V11：稳定输出头与有界变量投影准入

| 模型／状态 | 固定数据及方法 | 真实数值与判定 | source／资源与资格 |
|---|---|---|---|
| M1/M2 原算子制造见证 | 同0.7nm/384hex/p3、完整40端口、seed420906随机hidden；M1小非零γ/α，M2历史B0无标签大γ；原action产生完整RHS | M1稳定残差1.23470e-14≤1e-8；M2 raw1.29159e-7、初始稳定3.11751e-7、同分解唯一修正2.89518e-8＞1e-8；已知z/齐次恢复通过 | MAIN a2cba71533edafb4fa1c701eae503e7ab526eac4，REPLAY 036e36ec637488b1baddd9b061c80c6f34cde254；`S1_FAILED`，[见证](task042_neural_coarse_inverse/outcomes/records/manufactured_recovery_v11.json) |
| RANDOM-HIDDEN-PORT-CLOSED-VARPRO／稳定基线 | 原q15边面矩、P=ZR、原S对Z构A、gelsd/cond1e-12，40维Hhat精确闭合，真实Torch头回写；P/A rank1560/1560 | 实际网络与薄预测残差差3.95983e-8＞1e-8；原Schur/native0.797721738/0.309359507，port2.051e-19；散射E/curl差0.734256809/0.734361587，R/T/A/Avol仅未资格化诊断 | `S2_FAILED`／same-discrete FAIL；VERIFY同036e source。三阶段监督wall574.980116768s、同时树峰4668329984B/own swap0；[结果](task042_neural_coarse_inverse/outcomes/stable_head_varpro_v11.md) |
| 真正可变hidden VarPro／最终目标 | 同8576实hidden参数，review限40次P/A、48头、65000 S/Sᴴ、18FD、最多5接受更新 | 小型复非Hermitian梯度测试通过；真实FD0、trial0、accepted0，因S1/S2失败停止。无新p4参考、p6、最大目标或official R/T/A | `NOT_RUN_DEPENDENT_GATE`；最终0.7nm／48h `NOT_QUALIFIED`，不是对隐藏自适应本身的负证明；[分流](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v11.json) |

V11不修改原物理/MPC/材料/普通默认，旧p4强逆持续关闭；没有构造候选global p4 LU、完整S/global CSR、正规方程、ILU/Riesz或hidden fallback。REF7仅在求解冻结后独立验证，非训练或选择输入。V6–V10历史有载11159.165418899036s照记，V11正式wall后可核下界11734.145535666961s；全aux在原14400s总elapsed窗口内，不伪称精确有载。shared-workstation CPU0现场选核、MPI1/math1、16/12GiB采样整树监督/own swap0、无GPU/邻任务修改；无cgroup委派不能称内核连续限额，邻影响和无争用加速INCONCLUSIVE。p/h、Hybrid、M、MPI、最终几何尺度均未扫描。唯一下一建议为冻结M2的有界浮点来源归因，需后续review，未实施；不merge。[Response V11](task042_neural_coarse_inverse/response_v11.md)、[run index](task042_neural_coarse_inverse/outcomes/records/run_index_v11.json)。

### Task042 V12：固定头真实损失偏导与函数值备选

| 模型／方法身份 | 真实原方程／场／端口 | 数值分类和成本 |
|---|---|---|
| 同0.7nm／384hex／Nédélec p3、原Si、q15、40复端口、seed420906随机hidden；V11唯一修正物理网络/头为本批唯一起点 | 原Schur/native/port相对残差0.797721738/0.309359507/2.051e-19；散射E/scaled-curl0.734256809/0.734361587，完整通道相对差0.0494152，能量闭合0.112133 | 原方程1e-6、同离散场1e-4均FAIL，R/T/A/A_volume仅未资格化诊断；无新official结果 |
| T1同旧P/A／M2制造与物理RHS残差分账 | 物理网络回写3.80478e-8、`Pγ/Zc`2.36230e-7、原作用薄列差1.04273e-12；齐次恢复8.672e-17 | 原M2与实际头1e-8 Gate维持FAIL；分账不能称物理求解 |
| T2原action＋Hhat40＋真实网络固定γ隐藏偏导；T3预登记三块L-BFGS | 同点loss0.318179986／delta2.22045e-14；三真实FD最小h差0.06346/0.07599/0.17425＞1e-5 | `FIXED_HEAD_PARTIAL_GRADIENT_NOT_QUALIFIED`；T3真实hidden更新0、头建议0，属未准入非训练失败 |
| F两方向／正负／双步长函数值备选 | 8试探最小实际loss2.80461＞0.31818，native恶化到0.91847 | `FUNCTION_ONLY_POLL_NEGATIVE`，0接受；不再增加seed或扫描 |

原物理／MPC／材料／普通default和旧task/review/response/raw不改，旧global p4逆关闭，无global p4 LU、完整S/CSR、ILU/Riesz或hidden fallback。参考仅T4独立读，未回传训练；无新p4参考／p6／最大目标／p/h/M/MPI对照。三成功run clean source `d9df7068ca3310a0499164251a57841dbdfbc7f5`，两次接线失败source与完整费用另见[run index](task042_neural_coarse_inverse/outcomes/records/run_index_v12.json)。五次监督wall182.268s、同时树峰2322427904B/swap0，历史有载下界11916.413697s、辅助费未知；共享CPU0/MPI1/线程1、独立环境/缓存、自有锁、16/12GiB采样watchdog、GPU0，不操作邻任务、无cgroup连续上限承诺，影响/加速INCONCLUSIVE。最终0.7nm/48h `NOT_QUALIFIED`；唯一未实施下一建议为冻结同头同三方向JVP/VJP与原作用配对。见[Response V12](task042_neural_coarse_inverse/response_v12.md)和[详细负结果](task042_neural_coarse_inverse/outcomes/actual_loss_block_descent_v12.md)。


### Task042 V13：固定0.7nm micro的切向尺度／隐藏头补偿

| 模型／方法；measured/derived、无量纲 | 实际原方程与场／功率 | 数值分类／成本 |
|---|---|---|
| 原Full3D三维缺口384hex/p3/q15，原Si，40复端口，V12唯一修正网络为B/C共同起点 | 原Schur/native0.797721738/0.309359507，散射E/H0.734256809/0.734361587 | 旧头1e-8／V12标量FD均FAIL保留，不重跑旧campaign |
| A独立逐层tanh及全部矩映射切向、B实际响应尺度 | A三固定头方向通过新向量Gate；B预测gain小于分辨率，0试探／0接受 | 不是旧Gate通过或求解资格；继续独立C |
| C同步改变hidden/head，P/A rank1560/1560、固定gelsd cond1e-12 | 5试探／1接受，hidden变化3.26e-6；原Schur/native0.797721453/0.309359396、port1.46e-16；散射E/H0.734256339/0.734361116，40复通道差0.049415129，能量差0.112132933 | OBJECTIVE_ONLY_IMPROVEMENT，J相对下降7.149e-7不准入下一步；严格残差1e-6／场1e-4失败，神经增量NOT_DEMONSTRATED |
| 同head更新、hidden不变twin，贡献对照 | Schur/native23.780955/9.222344，scatter0.731445461/0.731535615；loss282.766917 | 方程明显恶化，不能按参考场稍好而选择；没有参考反馈 |

接受点R00_s/p/total=0.08496405695/1.28142e-7/0.08496418509；R_total/T_total/A_balance/A_volume=0.084966252/0.798045949/0.116987799/0.004854866，全部仅UNQUALIFIED_DIAGNOSTIC，无official R/T/A。完整40复通道原键/极化/reference plane在[通道CSV](task042_neural_coarse_inverse/outcomes/records/channel_observables_v13.csv)，selected复场与total/scattered E/H及curl另有hash绑定验证；同离散0/3状态合格，最终目标0.7nm/48h仍NOT_QUALIFIED。p/h/Hybrid/M/MPI/波长影响未扫描；没有新p4参考、p6或最大模型。

六次one-run含JSON writer失败及仅已保存记录恢复：wall243.725626s、同时树RSS最大2852761600B、swap0/VRAM0、全部自身后代清场；实际接受source33f7d613…、恢复/D source7615baae…分列，旧历史有载下界加formal为12160.139323s，辅助unknown仍unknown。shared-workstation每run现场CPU0、MPI1/mathTorch1/Loader0、自有锁/cache/16-12GiB采样监督，无cgroup连续限额声明；不改邻任务、无零干扰或无争用加速结论。未构造global p4 LU、全局S/CSR、正规方程或hidden逆，旧p4路线关闭。一次小实LS系数及失败逐作用计时unknown不补造，失败与旧合同/raw不改。[Response V13](task042_neural_coarse_inverse/response_v13.md)、[方法及资格](task042_neural_coarse_inverse/outcomes/tangent_scale_head_compensation_v13.md)、[source/资源](task042_neural_coarse_inverse/outcomes/records/run_index_v13.json)。唯一未实施建议为稳定输出正向坐标的表示调整，需新review，不继续同配置循环、不merge。


## Task042 V20：固定p3不完全因子／端口对照收口

| 路线 | 周期 | 原rho起点 | 原rho最终 | 下降% | S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|---|---|
| N | 4 | 9.67833470962e-06 | 9.39226219695e-06 | 2.95580305139 | 1052 | 193.57554083 | FIXED_CYCLE_LIMIT |
| P0 | 4 | 9.67833470962e-06 | 9.6529428923e-06 | 0.262357296786 | 1056 | 281.796204941 | FIXED_PROGRESS_RULE_STOP |
| P40 | 4 | 9.67833470962e-06 | 9.63671604509e-06 | 0.430018859409 | 1056 | 330.972634754 | FIXED_PROGRESS_RULE_STOP |


S0/N/P0/P40/V已实际执行，完整0/5。natural native ILU0配置固定（level0/shiftNONE），K nnz3852576，GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT；无global p4 factor、hidden训练/Q/image新建。P40约1.0043倍暖残差改善，低于T/C准入，迁移/零trace未运行。原Schur/native和逐通道功率仍失败，低loss/近参考场不替代资格。formal wall874.948403s、同时树峰934690816B/ownswap0/VRAM0；formal累计下界67488.474122s，历史aux unknown保留。成本shared-workstation，邻影响与加速INCONCLUSIVE。

正式source d41470d17d2babf29fabb0960886b0f60ae2aceb，38 focused passed；七dat与实际端到端验证。正式监督在原窗口内结束，总elapsed交付已超4h，延后reader测试因剩余0未启动；不刷新预算。没有新p4/最大模型/merge。见[Response V20](task042_neural_coarse_inverse/response_v20.md)、[结果](task042_neural_coarse_inverse/outcomes/fixed_p3_ilu0_port_v20.md)、[费用/截止](task042_neural_coarse_inverse/outcomes/records/resource_costs_v20.json)。唯一下一建议为申请一个固定几何ordering短对照，未自动实施。
