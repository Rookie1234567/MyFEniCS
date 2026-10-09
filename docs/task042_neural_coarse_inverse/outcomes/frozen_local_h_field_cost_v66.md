# V66：冻结局部h完整物理场与交叉空间费用

V66已实际消费V64原样保存的25576个四面体局部细化网格，完成p4、1043792行、828模式的0.7nm完整有限问题。全部内部未知量进入标准UFL/FFCx系统，没有静态凝聚。独立原式残差为2.27244591e-10，通过formal1e-6门；空间交叉结论为SPACE_INCREMENT_FAIL。它是有限模型的完整方程、场和费用链，不授连续真解、原尺寸0.7nm或2TB/48h资格；本批没有NN训练或NN收益。

体矩阵是将每个单元的完整Maxwell相位弱式累加到全局，保留场的每个内部系数。它先原子落盘，独立核验后才分解，减少下游故障导致重装配的风险；这不是目标规模的存储方案。局部细化只增加冻结区域的分辨，不按新结果改网格。

## 唯一身份与执行

canonical `/home/fenics/Projects/NN-Lab`，branch `task42_neural_coarse_inverse`，base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。Review `5a6689d321b74233b104c8b0ce5bab7d7bd8e39e`、blob `798dcc32b4496e646809554c34e9b90b0449390e`、SHA256 `bd9bdd437c45db2495e8bd8cc731a00fd9604743e2aa5528e1546e7402cf6f18` 已核实，报告原文不改。正式源码与文档HEAD分开列在[身份](records/report_identity_v66.json)。

首次真实UTC `2026-10-09T06:07:22.581808Z`，monotonic1451037.442696116、boot绑定；heavy-stop17:07:22.581808Z，总截止18:07:22.581808Z。12h研发窗、10h科学有载、L4F累计8h、条件M3h不刷新。forecast在昂贵PREPARE前保存。资格activation原LinuxABI、complex128/int64、MPI1/math1/CPU1、GPU/Loader0保持。

冻结mesh SHA256 `c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c`；实际25576tet、1000个NOTCH tet、native1066716、独立FE1042964、828端口。旧V64 admitted=false、NOT_RUN、标记及所有失败费用保持。未重标记、refine、调theta或重求P6。

保持s7/135、真实未舍入NOTCH、lambda0.7nm、grazing1度/azimuth5度/s，原kappa=(8.94046081729244,0.7821889682108057,0)，完整Ckappa及双Floquet。Si n=0.999885140474+4.32477054e-6i、epsilon=n*n、mu=1，canonical材料hash55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2。不是旧40通道或原尺寸目标。

## 完整方程、场和功率

| measured指标 | 值 | 门/边界 |
|---|---|---|
| independent true/native | 2.27244591e-10/2.27244591e-10 | formal1e-6 |
| augmented/port | 2.2724452e-10/6.99334023e-16 | formal1e-6 |
| direct1e-10 | False | 单列，不用生产残差替代 |
| MPC identity / 切向E | 3.20894593e-18/1.25617169e-14 | 1e-10 |
| R/T/A_balance | 0.0762184733/0.905665213/0.0181163135 | 全部828物理模式 |
| R00_s/R00_p/R00_total | 0.0762180547/6.26807638e-17/0.0762180547 | 零级两极化分别保存 |
| A_volume/能量误差 | 0.0181163135/1.73261405e-12 | 能量1e-5 |

完整total/scattered复E/H/curl、固定240点六向量、828物理参考面复通道/单mode功率、q23/q31体吸收均实际输出。Hcode=curl(E)/(i*k0*mu)，物理H=Hcode/eta0，单位和入射分母不改。生产body q11，独立PUBLIC_BASIX q13；真实p4维数84/superdegree4。q47/q63边界分别新建，oracle不读生产K或raw/Schur。[完整物理](records/complete_physics_v66.json) · [全模式独立复算](records/modal_recalculation_v66.json)

## P6/L4F一次积分、两个固定分母

L4子tet作为共同积分域，核对真实保存父关系和顶点包含，分别直接求两场；不投影、不校幅相。全域差平方分子只积分一次，下面分别除以L4F和保存P6范数。240点也保留两端完整复向量分母。total含背景，不能用total较小的变化掩盖散射FAIL。

| 场 | L4F分母全域差 | P6分母全域差 | L4F分母240点 | P6分母240点 | 共用差平方分子 |
|---|---|---|---|---|---|
| E_total | 4.89025449e-05 | 4.89025433e-05 | 0.000109383274 | 0.000109380365 | 9.32047955e-08 |
| H_total | 5.02703034e-05 | 5.02703018e-05 | 0.00026921854 | 0.000269231106 | 9.84734953e-08 |
| curl_total | 5.02703034e-05 | 5.02703018e-05 | 0.00026921854 | 0.000269231106 | 7.93383218e-06 |
| E_scattered | 0.000340423564 | 0.000340423976 | 0.000756033974 | 0.000756043124 | 9.32047955e-08 |
| H_scattered | 0.000349949643 | 0.000349950066 | 0.00186071778 | 0.00186103089 | 9.84734953e-08 |
| curl_scattered | 0.000349949643 | 0.000349950066 | 0.00186071778 | 0.00186103089 | 7.93383218e-06 |

六场/240点各1e-4，两归一化必须同时通过。参考面复振幅差7.25831697e-05、逐mode功率最大差2.06869078e-07；RTA/体吸收最大差8.65597656e-08，两场能量各按1e-5检查。q23/q31原分母操作尺度差1.31613231e-15，独立高q子单元见证保存。结论 **SPACE_INCREMENT_FAIL**；即使一致，也不指定P6或L4为连续真值。[原分子/双分母](records/paired_comparison_v66.json) · [独立保存checker](records/paired_saved_checks_v66.json) · [区域分量](records/paired_regions_v66.json)

完整828通道按真实参考面配对。辅助未知量含倏逝模的指数坐标缩放，其raw相对差0.823763157不是参考面物理振幅误差。新增296通道子集差范数3.24273413e-06、参考范数9.01002844e-08、相对差35.9902763均保留，完整向量沿原门评分；没有改分母或隐藏该近零子集。通道整体通过仍不能覆盖全场FAIL。

实际3444/7680个父cell有多个保存子tet，包含相容闭合造成的细分，不能把它们都叫原1267个指标标记。P6/L4F差平方在这些已细分父区内的E/H/curl比例为0.581057438/0.573528586/0.573528586；其余差异仍在未细分区域。由同一分子纯数组汇总，没有新积分或新标记，也不是连续误差界或唯一根因。[冻结区域差异分布](records/frozen_refinement_coverage_v66.json)

辅助A/L4F同p4局部h增量：散射E/H=0.000679731527/0.000693791357，240点最大0.0021923965，判定False；它是解释，不能要求旧粗场追溯变准确。

## 实际存储、生命周期与完整成本

体K实测151551034存储项，增广165965686；独立FE1042964、完整1043792行。K包3071094072B及原子COMMIT，初始ASSEMBLED_NOT_YET_ORACLE_VERIFIED不回写，通过后新增独立资格收据。两列全域作用分别收费。本有限参照明确使用全局直接LU，不是factor-free。numeric使用可信symbolic及实时RSS+两倍decimalMB+2GiB<=192GiB；保持ICNTL22=0、无OOC。[准备包](records/body_checkpoint_v66.json) · [容量/生命周期](records/capacity_and_lifetimes_v66.json)

PREPARE完整进程2784.742089s，prepared-start SOLVE完整进程2058.551381s，必要成功链求和4843.293469s，包含原式、全部输出、IO及后代清场。比较/局部解释/文档另列研究费用，不重复相加嵌套计时。父A/B、标记、旧P6失败都继承一次。L4新建边界，P6复用旧边界；OS/JIT未清空，未经配平且未达到同准确性，**不授生产速度或内存比**。峰值、采样gap及最后文档费用以[最终全集](records/resource_costs_final_v66.json)为准；当前科学快照54.461544GiB/gap2.047919s，不冒充连续硬峰。

| 完整有限候选 | tet/阶数 | FE/行/aug nnz | formal原式 | 必要成功链s | sampled GiB | 精度边界 |
|---|---|---|---|---|---|---|
| A | 7680/p4 | 314624/315452/59971384 | 2.15658828e-10 | 2270.28588 | 18.120335 | historical coarse candidate; prior FAIL retained |
| B | 7680/p5 | 585920/586748/156995068 | 2.16275894e-10 | 5645.94699 | 40.259663 | historical coarse candidate; prior FAIL retained |
| P6 | 7680/p6 | 980352/981180/362966076 | 2.32584924e-10 | 14748.4537 | 88.523769 | B/P6 scattered and selected FAIL; not truth |
| L4F | 25576/p4 | 1042964/1043792/165965686 | 2.27244591e-10 | 4843.29347 | 54.461544 | SPACE_INCREMENT_FAIL |

历史A的失败入口另有91.234595s，其全部进程链2361.520471s，不清零；表内列成功链。V64 P6失败15056.335016s和父A/B生成/标记仍在历史总账，不再加第二次。可靠factor原统计及负编码未知见[模型费用比较](records/model_cost_comparison_v66.json)。各case的峰为同时树采样，不是所有对象累计字节。

| 阶段，父子不相加 | 秒 |
|---|---|
| PREPARE/tetra_mesh_materials_full_periodic_space | 29.9558368 |
| PREPARE/fresh_triangle_all828_q47 | 19.5871084 |
| PREPARE/fresh_triangle_all828_q63 | 21.2903103 |
| PREPARE/body_JIT_form | 0.00441337214 |
| PREPARE/body_PETSc_assembly | 2582.44659 |
| PREPARE/standard_UFL_FFCx_full_uncondensed_body | 2582.45443 |
| PREPARE/body_native_CSR_copy | 4.31858531 |
| PREPARE/body_MPC_Hermitian_pullback | 14.9767181 |
| PREPARE/atomic_unscaled_body_CSR_checkpoint_IO | 18.2729634 |
| SOLVE/tetra_mesh_materials_full_periodic_space | 30.4668919 |
| SOLVE/readonly_body_K_identity_and_reopen | 15.5873375 |
| SOLVE/checked_readonly_this_case_q47_q63 | 8.87444739 |
| SOLVE/two_standard_UFL_PUBLIC_BASIX_operator_pairs | 27.5589302 |
| SOLVE/h_sparse_symbolic_capacity | 10.6494243 |
| SOLVE/h_bounded_numeric_factor | 918.787058 |
| SOLVE/full_uncondensed_tetra_direct_solve | 31.1606465 |
| SOLVE/independent_COEFFICIENT_FIRST_PUBLIC_BASIX_body_q13_triangle63 | 17.2109978 |
| SOLVE/full_physical_E_H_curl_240_points | 1.7333464 |
| SOLVE/complete_tetra_volume_and_analytic_q23_q31 | 852.404437 |
| SOLVE/all828_complex_channel_powers_and_output | 0.271519403 |

合法完整解返回后独立原式，释放factor、生产矩阵、prepared及mmap引用再输出，保存实际事件及RSS。没有因为元数据或JSON重新factor。本次INFOG9=2143620280，reported factor项数=2143620280，相对增广存储项的fill=12.9160451；负编码的历史统计继续unknown。[完整冷链](records/deployment_cost_v66.json)

## 条件M、失败、目标边界和唯一下一步

M决定：L4M_NOT_RUN_SPACE_INCREMENT_FAIL；两固定分母下散射E/H/curl和240点仍超过1e-4；formal、物理通道、功率及能量通过不替代全场。条件模式未准入就不运行。这里没有p7、第二轮标记、训练或原尺寸作用；旧P6/B仅冻结后比较，不读取factor或warm-start。所有普通修复与失败来源见[修复](records/repair_journal_v66.json)，各stage一项one-run，COMPARE_GATE只消费且不提前冻结最终队列。[裁决/未运行](records/decision_and_not_run_v66.json)

准确空间仍需目标可扩展的局部消元、trace迭代、matrix-free/流式DtN与分块恢复；本批未实现这些生产接口，不能把有限全矩阵checkpoint推成目标策略。48h必须包含必要构建/审核，2TB为整机并留余量。NN门仍为同完整正确性下相对最佳非神经全部耗时或同时峰改善至少20%，另一项合规，本轮未测试NN。

唯一下一pilot：在同一冻结L4网格、同0.7nm/真实NOTCH/828下做一个统一p5完整场对照，先以实际图及symbolic评估新增空间/因子容量，再与保存L4F/P6核对全场；它只用于区分固定局部分辨中的阶数限制，需新合同，不改theta/网格或模式。 当前不启动它。未merge、不改master/邻支、不通知隔壁。

## 证据与交付

10项定点测试、相关Ruff/compile、六dat真实validate及p4实际消费资格通过；未运行full pytest/CI/历史扫描。一次紧凑文档合同见[文档](records/documentation_checks_v66.json)，GitHub视觉NOT_VERIFIED。旧task/review/response/raw保持。[运行](records/run_index_v66.json) · [源码](records/source_bindings_v66.json) · [raw](records/raw_archive_index_v66.json) · [数组](records/array_inventory_v66.json) · [依赖分组](records/selective_manifest_v66.json) · [最终交付](records/delivery_index_v66.json)。最终精确remote/HEAD与clean/upstream0/0在推送后回报，运行source不替换为文档HEAD；closed/active null、后代和锁核对后暂停。
