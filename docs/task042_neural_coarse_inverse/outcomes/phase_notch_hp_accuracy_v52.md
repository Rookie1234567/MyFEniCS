# V52：固定相位三维缺口的 p/h 分辨对照

本轮结论：`FLAT_PASS_NOTCH_NOT_QUALIFIED`。升 p 是让每个单元表达更丰富的场形状；沿 z 加密是把单元切得更薄。本轮用这两种独立变化检查真实缺口散射，而不是只看线性方程是否解得足够精确。它们付出的代价分别包括更多内部矩、共享未知量、局部准备、全局稀疏因子和完整场审核。

固定 λ0.7 nm、缩尺 s=7/135、真实三维 NOTCH、grazing1°/azimuth5°/s、双周期及完整532模式。Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；canonical材料hash为55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2。旧FLAT/p4解析PASS直接复用，没有重复平界面计算；旧B0=V51实际Z2/p5数组，不由summary重造。

## 完整物理计算

以下原 true/native、增广和端口均以原未凝聚 Cκ＋完整DtN独立审核。正式门1e-6，直接参考内部目标1e-10；恢复/操作身份门1e-10。dat时间包含本case构造、求解、恢复、输出及队列要求的场比较；不是只计最后一次求解。

| 角色 | 模型 | 凝聚行含端口 | 状态 | 原 true/native | 增广 | 端口 | dat 冷链下界/s | 采样树峰/GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H | 320hex/p5 | 44532 | COMPLETED | 9.41863913e-12 | 1.04411663e-11 | 1.25726032e-14 | 2286.97282 | 5.72674179 |
| P | 160hex/p6 | 33364 | COMPLETED | 1.15504849e-11 | 2.59656282e-11 | 2.42913714e-13 | 5904.75728 | 6.98644257 |
| HP | 320hex/p6 | 65044 | CAPACITY_BLOCKED | not_run | not_run | not_run | 4746.49044 | 6.70747757 |

全局有限直接LU和局部内部LU确实存在，声明 `FINITE_AUTHORITY_EXACT_FACTOR_PRESENT`；本批不是factor-free生产迭代路线，不改变原方程或普通默认。每次返回先保存完整包络/port/κ/mesh/MPC身份，再释放全局因子及矩阵，保留原作用审核路径。

| 角色 | R00_s | R00_p | R00_total | R_total | T_total | A_balance | A_volume | 能量闭合 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H | 0.0762178788 | 1.64357188e-16 | 0.0762178788 | 0.0762183717 | 0.905665141 | 0.0181164872 | 0.0181164872 | 4.13002965e-14 |
| P | 0.076218285 | 3.99951801e-16 | 0.076218285 | 0.0762187041 | 0.905665172 | 0.0181161242 | 0.0181161242 | 3.0375702e-13 |

R00_s/p/total为零级反射两极化及其和；R/T为全部模式的出射功率占比。A_balance=1-R-T，A_volume为Si体内吸收独立积分。能量闭合小只能证明这些量相互一致，不能单独证明散射场准确。全部532复振幅、物理键、参考面和逐级功率保留于hash-bound ignored输出。

唯一VERIFY用q63原未凝聚作用重新审核两份新场，没有新因子或求解；随后独立checker从保存的体作用、耦合、端口和内部恢复数组重算：

| 角色 | 独立true | native | 增广 | 端口 | 原作用身份 | 内部恢复操作尺度 | 最坏cell恢复 | slave zero | 方程/恢复门 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H | 9.44810776e-12 | 9.44810776e-12 | 1.04413662e-11 | 1.23425406e-14 | 4.32079146e-16 | 1.04972875e-15 | 1.40650234e-15 | True | True |
| P | 1.15910715e-11 | 1.15910715e-11 | 2.59656995e-11 | 2.42594082e-13 | 4.12469829e-16 | 1.15343276e-15 | 1.43085648e-15 | True | True |

另复用已资格化的完整模式公式，逐项由复振幅和原波矢重算出射通量，不仅读取保存的R/T标签；[独立模式记录](records/modal_power_recalculation_v52.json)绑定两份科学数组及模式JSON原hash。

| 角色 | 实际模式数 | 振幅/功率操作最大差 | 全模式R/T/A重算最大差 | 独立能量闭合 | 门 |
| --- | --- | --- | --- | --- | --- |
| H | 532 | 7.10542736e-15 | 7.66053887e-15 | 3.35911854e-14 | True |
| P | 532 | 6.88338275e-15 | 7.43849426e-15 | 2.96339342e-13 | True |


## 完整空间增量

场、selected及参考面复通道门1e-4，逐mode功率差门1e-6，R/T/A/A_volume增量及能量门1e-5。curl相对差与curl/k0的scaled-curl相对差相同，完整绝对分子/分母保留于原数组。

| 比较 | total E | total H/curl | scattered E | scattered H/curl | selected 最坏 | 参考面复通道 | 逐 mode 功率最大差 | 完整增量门 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H_P | 9.68962309e-05 | 0.000100919081 | 0.000674525015 | 0.000702538865 | 0.000586944796 | 6.44169784e-05 | 4.06279138e-07 | False |
| B0_H | 1.83822935e-05 | 1.98752705e-05 | 0.000127963241 | 0.000138358066 | 0.000152955333 | 2.79515602e-05 | 5.01556003e-08 | False |
| B0_P | 9.83037936e-05 | 0.000102462232 | 0.0006843235 | 0.000713281367 | 0.00060656272 | 6.88730217e-05 | 4.37547584e-07 | False |

total与scattered的差分分子相同，但减去同一解析背景后的散射参考幅度更小，故两者相对差不同。total通过不能掩盖scattered失败。H/P等非嵌套场在两网格共同几何细分上分别求原场，没有先投影；q23/q31复核操作尺度1e-10。固定V51物理选点保留；人工细面按统一高侧规则取值，不选有利的新点。

raw端口在消逝模式下可有巨大幅值和差异；raw、加权原端口行残差、物理参考面复振幅三种尺度分别保存。没有拟合相位或更换分母。

以下为同一差分场的平方误差在四个互斥几何材料区中的份额；各区和为1，notch未重复算进air，场分量交叉项保留。它描述近似解之间的差，不是对未知连续解的已认证误差：

| 比较/场 | 缺口外air份额 | notch air份额 | substrate份额 | Si block份额 |
| --- | --- | --- | --- | --- |
| H_P/E_scattered | 0.367068454 | 0.0820628304 | 0.0459407413 | 0.504927975 |
| H_P/H_scattered | 0.420978424 | 0.0772014064 | 0.0415736054 | 0.460246564 |
| B0_H/E_scattered | 0.673748359 | 0.0276352304 | 0.0818772368 | 0.216739174 |
| B0_H/H_scattered | 0.676496812 | 0.0296246094 | 0.0700174836 | 0.223861095 |
| B0_P/E_scattered | 0.376395055 | 0.0799604646 | 0.0469138176 | 0.496730663 |
| B0_P/H_scattered | 0.429384187 | 0.0754999738 | 0.0424308837 | 0.452684955 |


## 条件分流与未运行

| 角色 | 分类/原因 |
| --- | --- |
| HP_numeric_solve | CAPACITY_BLOCKED: live tree +2*6948 decimalMB +2GiB = 22783656448B >16GiB; numeric0/solve0 |
| T | BUDGET_PLANNING_NOT_ADMITTED: remaining 3736.391077s after1200s final-audit reserve; calibrated T raw-kernel+one common-field comparison alone 5077.992729s, other construction/factor/output costs additional |
| M | NOT_ADMITTED_NO_CROSSCHECKED_FIXED_532_ANCHOR; original three comparisons allFAIL and HP has no returned field |

完整决定及父证据hash见[科学门](records/hp_accuracy_checks_v52.json)。HP/T/M仅按Review V50预登记规则准入；M需要先有两个独立分辨方向支持的固定532锚点。有限增量PASS也不是严格连续误差界、无限DtN、原尺寸32060模式、2TB/48h或NN20资格。

## 容量、成本和修复

稀疏装配/symbolic行门80000，事前同时规划16GiB；numeric必须实际树RSS＋2倍可信MUMPS INFOG16/17(decimalMB)＋2GiB余量≤16GiB。没有调ordering、shift、BLR或OOC来过门。warning20GiB、采样整树停止24GiB与MUMPS ICNTL23不是同一种内存口径。采样峰不能称内核连续峰。

| 角色 | 装配规划/GiB | symbolic时实际树RSS/GiB | INFOG估计/decimal MB | numeric两倍余量规划/GiB | numeric准入 | 采样树峰/GiB |
| --- | --- | --- | --- | --- | --- | --- |
| H | 6.27958503 | 3.08464432 | 3327 | 11.2816647 | True | 5.72674179 |
| P | 7.93441254 | 4.06534576 | 3572 | 12.7187142 | True | 6.98644257 |
| HP | 10.9297351 | 6.27727509 | 6948 | 21.2189336 | False | 6.70747757 |

装配规划来自所有共享cell Schur贡献、精确未舍入类、全部非零边界支撑及矩阵副本；symbolic为预测，RSS为实测采样。不能以采样峰小于规划值倒推被拒绝numeric也安全。完整INFOG/ICNTL、独立行数及每项字节载荷保留于原始容量记录。

| 角色 | dat链含准入/s | 局部tensor/内部凝聚/s | 全模式q47/q63/s | 全局symbolic+numeric/s | 求解恢复+精化/s | 场配对积分/s | 监督区间未单列/s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H | 2286.97282 | 1042.79594 | 125.55593 | 35.5943404 | 3.3115846 | 992.239804 | 59.1374203 |
| P | 5904.75728 | 3027.55918 | 216.69609 | 50.0608831 | 3.76718545 | 2406.24127 | 116.961237 |
| HP | 4746.49044 | 4463.4086 | 236.265494 | 4.00466584 | 0 | 0 | 22.7230898 |
| VERIFY_COST | 369.534595 | 313.319111 | 0 | 0 | 0 | 0 | 33.9864074 |

上表子计时由嵌套时间轴拆成互不重叠区间，不再相加重复计算。完整mesh/MPC、物理RHS、输出、I/O和其余区间见[增量费用](records/resource_costs_v52.json)。H/P的dat链包含规定的场配对研究费用，不能冒充仅线性求解耗时；最小研究下界包含所有stage、准入、失败、修复、checker、最终文档及结算，见最终费用记录。HP只完成准备和symbolic，其numeric/solve未运行；VERIFY明确没有numeric/solve，不用一个0秒替代未知旧费用。

新窗口2026-10-05T11:29:57.715299Z开始，最晚17:44:57.715299Z停止重负载、18:29:57.715299Z交付；总7h、科学有载5h、最终独立审核至少1200s，均未刷新。MPI1、数学/CPU1、Loader0、GPU0、ownswap/OOC0。现场选核，未改变邻任务。所有费用标shared-workstation；未观察到自身swap/持续PSI压力时也不宣称绝对零干扰，争用性能结论INCONCLUSIVE。

修复保留于[修复账](records/repair_journal_v52.json)。证据汇总括号及资源标签属性错误在同轮定点修复；失败提交93c315361c6245c3c1d3609aeb33ebbc272fa818未用于正式PDE，历史未改写。旧H/P合法解没有因这些元数据改动重解。最终已测费用下界、实际最大采样间隔、全部失败/监督/启动成本见[最终费用](records/resource_costs_final_v52.json)；旧费用未知项仍unknown。

## 真实源码与证据

| 角色 | 执行source | solve source | 科学数组SHA256 |
| --- | --- | --- | --- |
| H | 001b3495f4d542ed636ae477e8313ddaff3daab1 | 001b3495f4d542ed636ae477e8313ddaff3daab1 | fd337b7ccc4174e96649a89bd1b8e8931eadf5d95c0aa9a5f9ffb7740b7b3e66 |
| P | 138a1681a870fdd2e3d754365fc06d1dcabbe8dd | 138a1681a870fdd2e3d754365fc06d1dcabbe8dd | 4a2b310045a754e17c0162e6621d5cdf4d0e5ed170948e6a850f53e1ab83d27f |
| HP | 6230cd12286fb823dabc4fac04a424922d860995 | not_run | not_run |
| VERIFY_COST | 6230cd12286fb823dabc4fac04a424922d860995 | not_run; 原作用审核无新求解 | 逐状态审核数组见运行索引 |
| 保存模式checker | e937d315d49587dd03c3dbc9da2308bdc7add195 | not_run; 无FE/求解 | modal_power_recalculation_v52.json绑定H/P数组 |

运行source与最终文档HEAD分开。H/P/HP/VERIFY分别绑定实际clean实现，独立模式checker另有自己的clean source。[运行索引](records/run_index_v52.json)、[源绑定](records/source_bindings_v52.json)、[数组库存](records/array_inventory_v52.json)、[原始归档](records/raw_archive_index_v52.json)、[物理身份](records/physical_identity_bindings_v52.json)、[生命周期](records/object_lifetimes_v52.json)、[互斥区域](records/physical_error_regions_v52.json)、[最终交付索引](records/delivery_index_v52.json)保留增量及父hash，没有嵌套复制旧campaign。

## 下一完整pilot

保持本轮同几何 NOTCH Z4/p6、320cell、65044凝聚行及全部532模式，取得这一个完整物理解并补H→HP和P→HP两组场审核。现场两倍symbolic规划为21.218934GiB，超过本轮16GiB；只有新的资源合同明确覆盖该规划及宿主/邻任务余量后才准numeric，不能仅因本次采样峰6.707GiB就放行。未保存完整类tensor/Schur科学包，不宣称可免费复用本次昂贵准备；该pilot重新构造费用及共同场审核需完整预留。本轮不启动它、不改门，不自动转NN、Z8或p7。

两个更大尺度的真实编号公式和载荷设计区间见[容量桥接](records/next_scale_capacity_v52.json)，factor fill/工作区/迭代数未知。不得以微型测时外推原尺寸48h。本批没有NN训练；[NN20必要成本条件](records/necessary_NN_cost_conditions_v52.json)只给费用空间约束，不将确定性表示或传统因子收益归为NN。GitHub精确页面视觉NOT_VERIFIED，相关本地结构/文档检查见[测试](records/tests_v52.json)。
