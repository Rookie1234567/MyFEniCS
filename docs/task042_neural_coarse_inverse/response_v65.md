# Response V65：同一P6完整物理解已完成，p5/p6场精度增量仍未闭合

本批完成了原7680四面体/p6/828模式、981180行的完整0.7nm有限问题：新构建一次体矩阵并原子保存，从准备包重开，完成两列独立作用资格、一次MUMPS数值分解、物理零初值求解、完整场及独立审核。没有静态凝聚，全部内部未知量留在系统。正式原方程通过；严格direct目标及B/P6空间增量失败，分别保留。这里的“完整”指该有限模型的方程、场、端口和费用链完整，不代表原尺寸或连续真解已经准确。

新核先在每个单元把系数变到参考基，再积分场和向量，避免为每个几何方向复制整张基函数表。它改变同一弱式的计算顺序，没有降低求积或删场分量；生产矩阵仍由原UFL/FFCx完整弱式组装。新增checkpoint是将数小时的体矩阵准备落盘，下游中断后能够从它继续；不是保存因子或批准目标规模全局矩阵。

## 身份、时间与实际入口

canonical `/home/fenics/Projects/NN-Lab`；唯一分支 `task42_neural_coarse_inverse`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。Review `1cc254583559969b3fdeb9385104011d5f479a50`、blob `2a1b13df965ddf17cf7518bee30e7518399aa2a4`、正文SHA256 `11297b97131b61da489dc42ee27625e209452179839827004cef8324bf0279f1` 均核实，正文未改。被审V64 `63141f0d4de7b74f6a22414edfedb43c9d458271`。原旧报告冲突、closed窗口和失败不重开。[身份记录](outcomes/records/report_identity_v65.json)

Q/PREPARE实际source `7686f2fa9653adf5d95bdadea34ae7708e214cd9`；SOLVE实际source `2679c96f1eecfcb5c8a61a61397f75ef8b4c0280`；最后定点资格与保存消费者source `5212ae051c72ff264a7108faecfcbbb4e8e8aedd`。文档HEAD与运行source分开。四个v65 dat均真实创建、clean提交、validate并执行；VERIFY没有factor/solve。Linux资格activation、complex128及PETSc int64 ABI保持，MPI/CPU/math1、GPU/Loader0、已观察ownswap/OOC0。

首次UTC `2026-10-08T23:31:45.023823726Z`、monotonic1427299.88、boot绑定；heavy-stop `2026-10-09T12:31:45.023823726Z`，总截止13:31:45.023823726Z。14h总窗、11h有载、同P6累计10h不刷新，最终VERIFY保守并入同P6账。numeric后symbolic实时预算重新通过4500s验收余量门。单独时长forecast是在PREPARE运行后才保存，不能冒称事前收据；该provenance缺口如实保留。

物理保持s=7/135、真实三维NOTCH、λ0.7nm、入射1°/5°/s/幅值1，κ=(8.94046081729244,0.7821889682108057,0)，完整Cκ与双周期；Si n=0.999885140474+4.32477054e−6i、epsilon=n*n、mu=1，canonical材料hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。不是原50×25nm目标几何。所有828物理mode键、参考面、复振幅、功率均保留。

## 实际方程与物理场

| measured指标 | 数值 | 门及结论 |
|---|---|---|
| 独立true / native | 2.32584924e-10 / 2.32584924e-10 | 1e−6 PASS |
| 独立augmented / port | 2.32585091e-10 / 1.04881637e-15 | 1e−6 PASS |
| 生产true | 3.32931088e-11 | 独立direct为2.32584924e-10，1e−10 FAIL，不能互替 |
| MPC identity / 完整共享周期切向E | 1.76954562e-18 / 8.71291344e-15 | 1e−10 PASS；15232面 |
| 独立producer/consumer残差向量操作差 | 0 | 1e−10 PASS |
| R / T / A_balance | 0.0762185598 / 0.905665158 / 0.0181162824 | 完整828模态官方结果，方程已合格 |
| R00_s / R00_p / R00_total | 0.0762181437 / 2.52470985e-16 / 0.0762181437 | 零级两极化分别保存 |
| A_volume / 独立能量闭合绝对误差 | 0.0181162824 / 2.53652654e-12 | 能量1e−5 PASS；q23/q31吸收操作差6.86895086e-16 |

保存完整包络/native/MPC/κ、total/scattered复E/H/curl、固定240点六向量、828参考面复通道及逐mode功率。Hcode=curl(E)/(i*k0*mu)，物理H=Hcode/eta0；未改变原单位。独立PUBLIC_BASIX在全部7680cell做q17体作用，边界只读独立q63；检查不读取生产矩阵、15表或Schur。[完整物理与独立消费](outcomes/records/complete_physics_v65.json)

## B/P6完整精度判断

下表相对范数为同一物理场差除以P6原场范数；240点同样比较完整复向量。共同真实tet分别评价原场，差分精确多项式积分及原q23/q31分母保存，没有投影、校幅相或更换近零尺度。total含入射背景，scattered只表示物体改变的部分，因此total较小的相对差不能掩盖散射误差。

| 场 | 全域相对增量 | 240点相对增量 | 全域平方差 / P6平方范数 | 1e−4门 |
|---|---|---|---|---|
| E_total | 5.81857645e-05 | 6.26211352e-05 | 1.31949836e-07 / 38.9740345 | PASS |
| H_total | 5.89962028e-05 | 0.000169896141 | 1.35626479e-07 / 38.9669459 | FAIL |
| curl_total | 5.89962028e-05 | 0.000169896141 | 1.09271812e-05 / 3139.49666 | FAIL |
| E_scattered | 0.000405047017 | 0.000432840746 | 1.31949836e-07 / 0.804262794 | FAIL |
| H_scattered | 0.000410694274 | 0.00117438869 | 1.35626479e-07 / 0.804094688 | FAIL |
| curl_scattered | 0.000410694274 | 0.00117438869 | 1.09271812e-05 / 64.784461 | FAIL |

分区复算显示，平方差约64.08%（E）/65.01%（H）位于缺口外空气域，27.86%/27.14%位于Si块，缺口空气本身为4.64%/4.48%。这描述误差分布，不能将缺口或某个分量断言为唯一根因；下一方案须按完整逐cell差分核算相容闭合，不能只盯缺口。

828物理复振幅增量3.92351323e-05≤1e−4；逐mode功率最大差6.28022693e-08≤1e−6；R/T/A_balance/A_volume最大差6.52493643e-08≤1e−5。共同q23/q31操作尺度差1.93299652e-15；两场独立能量均通过。独立缓存checker重算判定一致，**完整p5/p6增量FAIL**。功率稳定不能据此称完整场收敛；P6不指定为真值，不追加p7。[原分子分母及checker](outcomes/records/paired_comparison_v65.json) · [差分区域](outcomes/records/paired_regions_v65.json)

## 准备资格、容量和真实费用

24个事前固定实际p6单元最大相对配对1.2198491e-15；保存p5完整向量6.23420198e-12。同一局部小批次旧变换表17.5065222s、新系数核0.188863603s，仅此局部计时，不授整case速度比。正式P6两列完整作用最大差6.24119357e-14；每列分别计费。P6解的单列body实际49.7807044s，参考表22680648B、完整向量workspace 47862528B，不常驻旧11.81GiB表库。[资格](outcomes/records/kernel_qualification_v65.json)

独立FE980352、native1005528、完整981180行、local216、superdegree6、192缺口tet。体K实测323539200存储项，增广362966076；K包16成员/6507698292B，manifest SHA256 `e12a930840dcf0cff8d3e27a04439a0b7f888c41c7c34e0e5acb3a32b619bbb5`。初始 `ASSEMBLED_NOT_YET_ORACLE_VERIFIED` 不改写；后续两列全域资格另存收据。[原子checkpoint](outcomes/records/body_checkpoint_v65.json)

symbolic估计64477 decimal MB；现场RSS+两倍symbolic+2GiB=169431011968B（157.794926GiB）≤192GiB，通过后才numeric。ICNTL22=0、ICNTL23=128954decimal MB；原ordering/shift不变。原INFOG9=-2934，未在本ABI下资格化其负编码的精确项数解释，exact fill保留unknown，完整后端统计已交付。实际一次numeric、2次同因子线性调用含既有精化，不能误记为2次数值分解。

本批当前全集采样树峰95051673600B（88.523769GiB）、最大已观察采样gap 1.369836s；最终费用按文档/收尾后的全集更新。ownswap/OOC观察为0；0.5s是配置，不是连续硬峰保证。因子实际释放后输出RSS约9.5GiB；SOLVE source仍保留prepared K/mmap引用，该事实和占用保留。后来在清场边界修复引用释放并做弱引用定点回归，没有重solve或声称修复后的真实PDE峰。[容量及生命周期](outcomes/records/capacity_and_lifetimes_v65.json)

| measured完整费用口径 | 秒 | 含义 |
|---|---|---|
| PREPARE完整进程 | 12240.424729 | 启动至checkpoint/后代清场 |
| prepared-start SOLVE完整T_N1 | 2508.029019 | K/边界重开、作用、factor、solve、审核、所有输出、IO/清场 |
| 本次成功链 | 14748.453748 | 两完整进程之和，约4.096793h；父子计时不重复加 |
| 唯一VERIFY完整进程 | 274.948752 | 保存原式/切向/输出审核及B/P6比较 |
| 同P6累计含VERIFY | 15023.402500 | 36000s配额内，补消费不刷新 |
| V64失败+本次成功链 | 29804.788763 | 丢失旧K的失败费用仍支付；不是成功N1 |

本次成功链复用了健康q47/q63边界，实际重开/验证费均计入；旧首次生成60.583201/63.998702s保留在历史账，不再次加到研究账，也不把读取冒充fresh构建。体K本批真实新构建一次，JIT/form为精确缓存命中；OS/JIT未人为清空。完全fresh编译/边界的冷N1未配平实测，prepared-start与本次成功链均给出真实数值，不把当前完整费用统写unknown。[互斥阶段与完整费用](outcomes/records/deployment_cost_v65.json) · [最终费用](outcomes/records/resource_costs_final_v65.json)

研究总投入另含Q、实现/失败/修复、CPU准入、独立比较、索引和文档。历史已知下界245130.14639971292s（已含V64全部新费用），再加本轮最终账，不能另加15056.335016s重复计费；未知历史及控制/Git CPU保持unknown。新完整解还没有同精度最强传统配平基线，确定性审核运算不归NN20，未授生产加速比或2TB/48h资格。

## 修复、停止与下一步

同轮修复共享P6最终审核计费及post-symbolic余量接线、现有Ruff调用、控制器keyword/API、prepared引用生命周期和费用字段；每次失败/source/受影响重验均保留，没有因普通bug重装环境或重新PDE。[修复记录](outcomes/records/repair_journal_v65.json)

最终10个相关targeted测试、相关Ruff/compile、四dat真实validate通过；三次受影响轻量资格均计费。一次紧凑15文档合同及最终交付字节核验单列，不跑full pytest/CI或历史全盘hash。GitHub视觉NOT_VERIFIED。本批新矩阵/场留ignored，Git只存新证据与父hash。

停止原因是授权队列完成，完整场已返回，但跨p增量仍不满足精度。唯一下一建议：以冻结B/P6逐cell差分为唯一新依据，设计并先核算一次有界相容局部h参照的实际闭合网格；在新的完整合同下判断未闭合的散射场分辨与跨阶差异，当前不启动新求解。 原尺寸准确网格、模式、PC/fill、迭代和完整RSS/N1仍unknown；不自动开启新窗口。

[专题](outcomes/coefficient_first_p6_completion_v65.md) · [运行索引](outcomes/records/run_index_v65.json) · [最终交付索引](outcomes/records/delivery_index_v65.json)。最终closed/active null、后代清场、自有锁释放、仅本分支push与实时remote/clean/upstream核实后向用户交付暂停，不通知邻窗或merge。
