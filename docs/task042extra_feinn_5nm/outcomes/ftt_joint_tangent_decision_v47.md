# V47：联合切线短试步及固定FTT组合裁决

**导数资格通过，联合更新得到可信但过小的下降；短试步投入门FAIL，正式ALL/OUTPUT_ONLY均按合同未启动。独立磁盘重开探针末态后，actual与producer的原联合门均FAIL，无强研究信号。关闭此固定FTT求解组合：CLOSE_CURRENT_FTT_SOLVER_FAMILY / NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE。0.7nm未准入，不自动另开同类变体；这不构成所有神经网络不可能的结论。**

旧流程把输出系数和隐藏函数分开更新；本次让修正网的三轴输出与隐藏函数一起移动，检验配合更新是否能解除停滞。这种受阻尼联合切线（GN/LM）先用导数预测小步，再实际评价完整非线性场，按真实收益决定接受和阻尼。它增加导数与试探成本，不能保证找到全局最优。基网19200实参数冻结，修正网19200（其中隐藏3360），持有总量38400；W32/r8与载波不变，未增第三网。

原Si/air非可分三维M5：lambda5nm、8×6×8=384hex、h1.25nm、p3、31968独立复FE、34050完整FE行及40端口。材料/A/f、双Floquet/完整DtN、背景/相位、q15/q30/独立q60不变；p/h/M/MPI固定，NNZ=NOT_ASSEMBLED（矩阵自由作用），未做收敛扫描。训练用固定g=f−Ac0、norm(g)=0.1043574223800681，正式分母norm(f)=0.29104200262261154；原f不改。残差衡量原方程的不平衡量；场误差均对原同p3参考归一化。独立total使用原完整方程载荷分母0.6143992411628639。H为H_code=curl(E)/(i*k0*mu_r)，scaled-curl为curl(E)/k0，均沿原nm单位约定。

| measured；M5/5nm/384hex/p3/N31968/40端口 | actual：磁盘双网旧逐点完整矩 | producer：保存合成FE系数 | 原门及含义 |
|---|---|---|---|
| 原native / augmented / 独立total残差 | 0.346345909527 / 0.346345909527 / 0.16406466733 | 0.346345909535 / 0.346345909535 / 0.164064667333 | 各≤1e-6 |
| 总E / 散射E | 0.0443150832984 / 0.0646224076254 | 0.0443150832984 / 0.0646224076254 | 各≤1e-4 |
| 总H / 散射H | 0.0442099770045 / 0.0646542349573 | 0.0442099770045 / 0.0646542349573 | 各≤1e-4 |
| 总scaled-curl / 散射scaled-curl | 0.0442099770045 / 0.0646542349573 | 0.0442099770045 / 0.0646542349573 | 各≤1e-4 |
| 六点复E/H最大相对差 | 0.0726413444529 | 0.0726413444528 | ≤1e-4 |
| total复通道 | 0.039411137487 | 0.0394111374871 | 全部40复向量；≤1e-4 |
| scattered复通道 | 0.0699708024129 | 0.069970802413 | 全部40复向量；≤1e-4 |
| outgoing复通道 | 0.0189154361171 | 0.0189154361171 | 全部40复向量；≤1e-4 |
| boundary-outgoing复通道 | 0.0183045592109 | 0.0183045592109 | 全部40复向量；≤1e-4 |
| R / T / A_balance / A_volume | 0.804741633978 / 0.0294616644541 / 0.165796701568 / 0.143057573825 | 0.804741633978 / 0.0294616644541 / 0.165796701568 / 0.143057573825 | 原残差FAIL；仅diagnostic |
| R00_s / R00_p / R00_total | 0.804721128151 / 3.03000529096e-09 / 0.804721131181 | 0.804721128151 / 3.03000529093e-09 / 0.804721131181 | 零级两极化及其和 |
| R/T/A/A_volume绝对差 | 0.00768486507878 / 0.00300073164119 / 0.01068559672 / 0.0120535310221 | 0.00768486507882 / 0.00300073164119 / 0.01068559672 / 0.0120535310221 | 各≤1e-5 |
| 能量闭合 / 最大逐级功率差 | 0.0227391277424 / 0.00753569031283 | 0.0227391277424 / 0.00753569031287 | ≤1e-5 / ≤1e-6 |
| 功率差额对体吸收 / 两种体积分配对差 | 0.0227391277424 / 3.60822483003e-16 | 0.0227391277424 / 1.38777878078e-16 | 各≤1e-5 |
| 双网完整矩重建 / MPC / 端口 | 5.9392333013e-14 / 0 / 1.22306950153e-14 | 5.9392333013e-14 / 0 / 2.15032640402e-18 | 各≤1e-10 |
| q30/q60系数 / 原A作用 / FE积分漂移 | 3.16656272984e-14 / 5.28668157396e-11 / 1.29207347351e-14 | 3.16656272984e-14 / 5.28668157396e-11 / 1.23301201999e-14 | 各≤1e-8 |
| 原方程 / 场 / 功率 / 重建 / 求积 / 联合 | FAIL / FAIL / FAIL / PASS / PASS / FAIL | FAIL / FAIL / FAIL / PASS / PASS / FAIL | 由原字段重新计算 |

同一V46完整六轮末态出发，3次实际试步均接受，无拒绝/Cauchy后备，LSMR共34次。原native由0.346345939539降至0.346345909535，相对下降8.66308290305e-08，要求≥1e-3；独立重复漂移3.50119933046e-12，下降超过其10倍，但幅度条件未达。父状态随后逐位恢复；保留的探针末态仅用于独立验收。FTT_JOINT_LM_ALL和FTT_JOINT_LM_OUTPUT_ONLY均NOT_RUN_PROBE_GATE_FAILED，没有正式长路线的隐藏消融胜负。

| 试步 | LSMR | pred / ared | rho | 步后原残差 | 隐藏 / 输出步范数 |
|---|---|---|---|---|---|
| 1 | 12 | 1.52803995568e-08 / 1.52693951927e-08 | 0.999279837936 | 0.346345933871 | 1.90115570442e-08 / 2.66829167699e-08 |
| 2 | 10 | 2.42787958071e-08 / 2.42973917097e-08 | 1.00076593183 | 0.346345924852 | 3.74261703102e-08 / 6.88379045639e-08 |
| 3 | 12 | 4.1264939854e-08 / 4.12603698985e-08 | 0.999889253309 | 0.346345909535 | 7.65893376881e-08 / 1.66936288051e-07 |

| 接受步 | 原loss | 仅隐藏loss | 仅输出loss | 联合实际loss |
|---|---|---|---|---|
| 1 | 0.466503448306 | 0.466503440808 | 0.466503441877 | 0.466503433036 |
| 2 | 0.466503433036 | 0.466503424596 | 0.466503422125 | 0.466503408739 |
| 3 | 0.466503408739 | 0.466503396628 | 0.466503389322 | 0.466503367479 |

隐藏参数确实变化，累计范数1.27840252486e-07；输出累计2.60004307152e-07。前3步仅隐藏、仅输出和联合的真实loss均记录，联合下降比任一单独部分大，但量级约1e-8，不能据此认定有实用隐藏净收益。LSMR真增广残差约0.965923，真normal缺陷比依次0.062911933169 / 0.395107817406 / 0.474157378719；stop_code=2不等于精确子问题最优或PDE通过，不追加300+900续扫。父状态已验散射E/H为0.0646210654522/0.0646528880296，本次分别约0.0646224076254/0.0646542349573，场误差略增；旧健康评分复用，未重新求父场。

| 真实父状态方向 | 非零Jv范数 | 两档FD最大相对差 | 实伴随相对差 |
|---|---|---|---|
| hidden | 987.021433892 | 7.30880765673e-10 | 2.83426508684e-14 |
| output | 1305.23668102 | 5.56292045259e-10 | 8.79285757671e-16 |
| mixed | 2807.81282077 | 9.47039858522e-11 | 1.97617786863e-15 |

真实隐藏/输出/混合非零方向FD、实伴随均通过；VJP对旧完整逐点梯度相对差1.501234336e-10≤1e-9，三轴退化到旧K最大差6.57689065044e-15≤1e-10。7项恢复负控、4类实际标签打开负控均拒绝。h=15384236452.3来自seed4214701的4次幂迭代末Rayleigh，仅为估计；lambda0=1e-3h，3次接受后为569786.535272。单次JVP/VJP/真实试步/保存合计11.1284737219s。没有大J/J*J/全网格AD/新全局因子或FE逆。

完整导数含(DX)YZ+X(DY)Z+XY(DZ)，基网不参与。实化保范，父tensor尺度S=max(1,RMS)全批冻结；JVP和实VJP通过原A/A*与完整矩。增广LSMR使用[J;sqrt(lambda)I]、[-e;0]，atol=btol=1e-6、conlim=1e12、maxiter200、零初值。pred不含阻尼，rho=ared/pred≥0.1且两者正才接受；rho>0.75时lambda除3。本次没有拒绝；拒绝/恢复及后备由定向测试覆盖。非线性实际场不要求等于线性预测。

```math
e=\operatorname{realify}((Ad(\theta)-g)/\|g\|_2),\quad \mathcal L=\tfrac12 e^T e,\quad c=c_0+d(\theta).
```

磁盘重开双网，旧逐点函数先求和，再完整H(curl)矩重建；背景、Bloch相位、Piola/MPC及原端口公式沿用，不能直接相加两套含背景端口。FE compare-only只读原同p3参考，不反馈参考向量；actual与producer各自评分，全部失败的功率保持diagnostic/official=false/production=false。区域、完整场、六点、四类40复向量及独立q60都有证据。

新唯一28800s总窗，含准备、失败、等待与验收；采集时已过3505.11761264s、余25294.8823874s，保留1800s发布。初检精确起点未留，保守预扣300s；登记UTC不冒称更早检查时刻。正式attempt合计796.349269309s（不叠加内部算子计时或重复累计span），自身树RSS采样峰最高621559808B，ownswap/OOC=0。探针attempt1无合格空闲核，在终端/worker产生前拒绝；attempt2继承原900s截止，不重开窗。一次重复默认入口被EXISTING_STAGE拒绝，未产生新worker，随后使用既有--attempt 2。

| 实际attempt | 分类 | CPU | attempt秒 | 自身树RSS采样峰/B | ownswap/B |
|---|---|---|---|---|---|
| v47_joint_compare_attempt1 | COMPLETED | 36 | 360.86354091 | 621559808 | 0 |
| v47_joint_step_probe_attempt1 | RESOURCE_ADMISSION_REJECTED_BEFORE_TERMINAL | None | 12.2058298748 | None | 0 |
| v47_joint_step_probe_attempt2 | COMPLETED | 1 | 156.03814389 | 441548800 | 0 |
| v47_joint_tangent_checks_attempt1 | COMPLETED | 12 | 267.241754634 | 426496000 | 0 |

每条逻辑部署仍须必要旧前缀21928.32951481887s＝原基网12788.395328277858s＋V46学习9139.93418654101s，共享研发不重复计费。mesh/native/moments冷准备缺项，完整冷N=1仍UNKNOWN；未留细分的非正式活动NOT_RETAINED而非免费。没有同精度20%资源收益证据，未满足完整M5和余时/资源联合条件，不登记空0.7nm输入。本支不转Full3D外围工程。

本地53个不同定向case通过（重复不累加），覆盖复乘积网络、三种mask、增广LS对小SVD、接受/拒绝/恢复和实际微型保存流程；Ruff、compileall、五dat validate-only和diff检查通过。实际M5资格通过，但数值门独立FAIL。初次ML ABI现场准入无空闲核，未运行测试/PDE，原门重试后通过；无数值实现修复、full pytest、重装或CI声明。CPU-only/MPI1/math与Torch intra/inter1，一个现场合格物理核；numeric warn12/hard16GiB、规划12GiB、新增cache/AD1GiB、轻2GiB、原PSI/系统及384GiB邻增长保护不变。

Review发布4439c45d666f0527eb659e01b8deeb74944c47b0，结果基线0efeaa97f6a2e109ef981c14dd3f7bc65ae2e7e2，原任务base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。本批资格/探针/compare实际source统一为ce8f1f5e89cbdb848488b671305188a39c824046；后续发布HEAD仅代表证据/文档。用途沿用benchmark_previously_seen/design_informed_by_reference_diagnostics=true，非盲测；生产初始化false。父PT由V46 run/index解析：committed_000033.pt，SHA256 3bfe977c9235ea4305a1eb4049401b098c30dce87bfce76f635e5c88e3bf8c58、6513249B；不是同名猜测或历史best。基网/修正模型、base/g/native/moments/phase及S/mask/h、实际c/r/RNG均绑定；模型hash不冒充PT文件hash。

[parent/source/index](records/run_index_v47.json)、[父状态](records/joint_parent_v47.json)、[真实导数](records/joint_qualification_v47.json)、[短门](records/joint_probe_v47.json)、[逐试步](records/joint_trials_v47.csv)、[保存态/隐藏配合](records/joint_routes_v47.json)、[完整原Gate](records/full_numerical_gates_v47.json)、[四类40复向量](records/full_40_complex_channels_v47.csv)、[六点](records/six_point_complex_fields_v47.csv)、[功率](records/power_and_energy_v47.csv)、[定义](records/channel_and_norm_definitions_v47.json)、[成本](records/resource_costs_v47.json)、[测试/修复](records/tests_and_repairs_v47.json)。大型PT/轨迹/数组留ignored，compact记录只保存本批新标量及hash入口；不重复嵌套历史。

| 依赖组 | 变化 | 依赖与验证 |
|---|---|---|
| production numerical/core | 无合格production新默认 | ；原M5联合FAIL，不提升默认 |
| research-only numerical | 实参数完整三项FTT JVP/VJP、阻尼LSMR、原子实际试步和恢复 | joint_least_squares、ftt_joint_tangent、ftt_joint_io、ftt_joint_training、ftt_joint_qualification；53本地定向case及fresh M5导数/三步；短投入门FAIL |
| reusable runner/watchdog | 既有CoreWorkerProfile可选trainer钩子；schema17/profile与五输入 | research-only numerical、ftt_core_worker、ftt_joint_campaign、ftt_joint_worker；五dat validate、fresh串行资格/探针/compare；原watchdog和资源门复用 |
| checker/benchmark | 旧双网逐点完整矩与FE compare-only沿用；design47允许 | reusable runner/watchdog、ftt_continuation_joint；fresh actual/producer分别全门，原参考只读，无重求 |
| compact evidence/docs | 只保存本批新证据，更新入口与总账 | checker/benchmark；源/数组hash、数值门独立重算及有限Markdown/呈现 |
| do-not-merge | ignored大PT/数组及未资格化研究默认；自动变体/0.7nm/生产merge | ；无production/master授权 |

[交付核对](records/delivery_check_v47.json)、[有限呈现状态](records/render_check_v47.json)、[发布尾段](records/publication_tail_v47.json)。未见页面/公式保持NOT_VERIFIED，不以本地解析代替实际呈现。
