# V51完整物理结果：固定解析相位的准确性和容量边界

本轮要解决的是“空间能否表示真实波”，不是继续把已有离散方程的残差压低。已知横向振荡从有限元系数中提取出来，物理场仍保留全部快速相位；包络的所有边/面/内部未知量和532个DtN端口一起求解。平界面已达到解析准确性，真实三维缺口仍未通过有限p/h一致性，分类 **FLAT_PASS_NOTCH_NOT_QUALIFIED**。本批不训练NN，不能将确定性表示收益写成神经收益。

## 身份、范围和实际入口

| 固定身份 | 实际值 |
|---|---|
| 权威／分支／base | Review V49@97ca0d4e2d90f7479a757e66d43061b7d54bf3aa；task42_neural_coarse_inverse；ccd357885f7f9be84efe3be07868cc94f13d93fc |
| 工作树与Git | /home/fenics/Projects/NN-Lab；canonical linked worktree，common Git为Maxwell3D-Lab/task-repository.git；origin保持 |
| 物理 | λ0.7nm；grazing1°/azimuth5°/s/幅值1；缩尺s=7/135，双Floquet，无PML |
| 材料 | canonical input/materials/si_optical_constants_v1.json；Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，air=1，mu=1 |
| 材料来源 | source_wavelength_nm=0.699999988，nominal=0.7；用户原值，不插值；JSON SHA256 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| 几何nm | x=(0,.8555555555555555,1.2962962962962963,1.737037037037037,2.5925925925925926)；y=(0,.32407407407407407,.6481481481481481,.9722222222222222,1.2962962962962963)；z=(-.5185185185185185,0,2.074074074074074,4.148148148148148,6.222222222222222,6.7407407407407405) |
| NOTCH | 原全精度盒，x=(1.2962962962962963,1.737037037037037)、y=(.32407407407407407,.9722222222222222)、z=(2.074074074074074,4.148148148148148)；80cell时两cell，Z2时四cell，不沿y复制 |
| 完整模式 | m=-9..9、n=-3..3，上/下×s/p=532；各侧266，记录84个propagating；非零小项全部保留 |
| 求积与单位 | 实际边界q47，独立Basix二维q63；体积完整Ckappa自动次数；共同物理积分q23/q31；Hcode=curl(E)/(i*k0*mu)，SI H=Hcode/eta0 |

未知为TOTAL_ENVELOPE，用周期Nédélec空间表示u。物理kx/ky、beta、偏振、导纳和入射载荷不改；只改变约束为包络单位周期，以及C/D/RHS中的横向积分相位。弱式trial和test均使用完整变换：

```math
E=g u,\quad g=e^{i\kappa\cdot x},\quad C_\kappa u=\nabla\times u+i\kappa\times u,
\qquad a(u,v)=\int \mu_r^{-1}C_\kappa u\cdot\overline{C_\kappa v}-k_0^2\epsilon_r u\cdot\overline v.
```

恢复保留内部特解及非零内部端口支撑：Hhat=H+Di*Vii^-1*Bi，ui=Vii^-1*(fi-Vit*ut-Bi*a)。小复数非Hermitian/非互伴/40port见证通过；真实四状态用独立未凝聚原体弱式与完整q63 DtN审核，不用凝聚矩阵自证，也不要求新物理场满足旧多项式离散方程。

| one-run入口 | 实际执行 | source／状态 |
|---|---|---|
| v51_phase_setup.dat | 新p4完整边界与接口 | db95e8cf859385f02eef12f6bdd1a942f2cec2e7，PASS |
| v51_flat_p4.dat | F4物理零初值完整解 | 同上，解析准确性PASS |
| v51_flat_p5.dat | not_run | F4准确，不需要F5 |
| v51_notch_p4.dat | N4物理零初值完整解 | 9100a925a2a074a2a305def8f27ec992451178c7，方程PASS |
| v51_notch_p5.dat | N5物理零初值完整解；后处理失败后的只补审 | 原solve同上；补审62537a4e7c56336160ec59f022081841abb8566c，未重解 |
| v51_notch_hprobe.dat | 160hex/p5/Z2，独立零初值 | c3009dd66993b42961666758068f343cd67044e8，方程PASS |
| v51_ordinary_flat_control.dat | not_run | phase-FLAT准确；只有schema，实际fallback未资格 |
| v51_verify_cost.dat | 全队列冻结后唯一独立审核 | 80e227660baac5bd89b0220455e4207bcb1d51d6，无因子／新solve |

最终source archive同时包含collector与文档检查版本；文档HEAD不能冒充上述source。完整原始dat、resolved、manifest、材料/物理/mode/数组hash见[身份](records/physical_identity_bindings_v51.json)、[run index](records/run_index_v51.json)、[交付索引](records/delivery_index_v51.json)。NH resolved的旧父描述cells=80保留为历史模板字段，实际cell_count=160、新z轴、容量及数组均为160；以实际mesh/数组库存为准，不回写raw。旧plan的q23说明不是本批求积，live resolved和实际工厂明确q47/q63。

## 完整方程、恢复和真实物理场

| 模型 | cell/p | native／独立FE／trace／内部 | 凝聚+port行 | 独立true/native | 独立增广 | 独立port |
|---|---|---|---|---|---|---|
| FLAT | 80/4 | 17204／15872／7232／8640 | 7764 | 2.881171206e-12 | 2.604557319e-11 | 1.460459122e-13 |
| NOTCH | 80/4 | 同上 | 7764 | 2.931495336e-12 | 4.807872298e-11 | 1.689311145e-13 |
| NOTCH | 80/5 | 32865／30800／11600／19200 | 12132 | 4.777705493e-12 | 2.663343450e-11 | 2.669964675e-13 |
| NOTCH Z2 | 160/5 | 64890／60800／22400／38400 | 22932 | 4.674761200e-12 | 3.746623604e-11 | 2.058893481e-13 |

原方程门1e-6、直接内部目标1e-10；四次均用一次固定残差精化，无再次增精化救场。原恢复最大单元操作尺度分别1.26083e-15、1.25817e-15、1.32557e-15、1.48409e-15，门1e-10；slave严格零、master存储差0。独立保存向量checker重算体作用、C*a、D*u、H*a和残差身份，四状态结构缺陷均为0；split action用不同操作范数重算仍约1e-15，不能把范数口径的小变化改写成新数值失败。

| FLAT解析量 | 相对／绝对误差 | 门 |
|---|---|---|
| total E/H/curl L2 | 3.857979470e-8／4.635741042e-8／4.635741042e-8 | 1e-4 |
| selected E/H/curl | 9.621053476e-10／2.452059209e-8／2.452059209e-8 | 1e-4 |
| 解析场代入独立原gVh弱式 | 3.104526466e-12 | 1e-10 |
| R/T/A_volume差 | 6.40876e-13／8.83182e-13／4.05145e-15 | 1e-5 |
| 全532最大逐mode功率差 | 8.83182e-13 | 1e-6 |
| 能量 | 2.46358e-13 | 1e-5 |

这与V50普通空间E/H误差约1.0127形成准确性进展：同样有限几何中，解析相位表示准确波，且原方程独立审核通过。不同空间和检查成本不等价，不由此声称耗时加速或连续收敛。

| NOTCH有限增量／门1e-4 | p4→p5 | p5→Z2 p5 | 判断 |
|---|---|---|---|
| total E/H/curl | 1.38146349e-4／1.35253263e-4／1.35253263e-4 | 1.22562271e-4／1.22544722e-4／1.22544722e-4 | 两组FAIL |
| scattered E/H/curl | 9.61666712e-4／9.41540102e-4／9.41540102e-4 | 8.53182994e-4／8.53072414e-4／8.53072414e-4 | 两组FAIL，不用强入射总场掩盖散射误差 |
| selected最大 | 9.07663635e-4 | 8.78633859e-4 | 两组FAIL |
| 全532实际参考面复振幅 | 1.84815101e-4 | 1.51245770e-4 | 两组FAIL |
| 共同q23/q31操作缺陷，门1e-10 | 1.53546740e-15 | 7.29379713e-16 | PASS |
| 最大逐mode功率差，门1e-6 | 8.28146204e-7 | 8.42200065e-7 | PASS，不覆盖场FAIL |
| R/T/A_volume差，门1e-5 | 3.06177e-7／5.26722e-7／2.20545e-7 | 4.66986e-7／4.58707e-7／8.27932e-9 | PASS |

物理场authority是完整native包络系数、原mesh/MPC/高阶矩定义和kappa，可重新求值E/H/curl。所有total/scattered selected复场只是额外输出，不作为authority或PINN点值替代。保存完整532键、侧、极化、参考面、归一化、原坐标与实际参考面复振幅及功率；没有投影回旧DG多项式。raw辅助坐标差0.659631/0.999024及约1e88最大差保留，物理ref-plane比较不作拟合相位。全mode独立Poynting通量、incident功率、port坐标和R/T/A重算最大缺陷7.11e-15，见[模式审核](records/modal_power_recalculation_v51.json)。

| 离散功率／code单位归一化 | FLAT/p4 | NOTCH/p4 | NOTCH/p5 | NOTCH/Z2 p5 |
|---|---|---|---|---|
| R_total | 0.113433408921 | 0.076218503903 | 0.076218810080 | 0.076218343094 |
| T_total | 0.882458998614 | 0.905665229740 | 0.905664703017 | 0.905665161724 |
| A_volume | 0.004107592466 | 0.018116266358 | 0.018116486903 | 0.018116495182 |
| R00_s | 0.113433408921 | 0.076217977246 | 0.076217558423 | 0.076217847492 |
| R00_p | 4.657277531e-25 | 1.639842220e-16 | 1.671677394e-16 | 1.688539083e-16 |
| R00_total | 0.113433408921 | 0.076217977246 | 0.076217558423 | 0.076217847492 |
| 能量绝对差 | 2.46358e-13 | 4.65628e-13 | 3.44835e-13 | 7.99361e-14 |

四状态离散功率均来自原方程合格解，NOTCH功率收支正确不等于场已准确。全部532逐项原始CSV/JSON及复系数在ignored数组目录，索引绑定其hash；未删小通道或四舍五入跨Gate。解析近零散射／零高阶模式按入射绝对尺度，非近零分母。

## 误差方向、区域及边界

N5包络梯度能量x/y/z=0.0001223083906／0.0000032020881／2.8128083629，按最大轴一次选择Z2。原80cell区域数量40空气(不含缺口)/2缺口空气/16基底/22Si块；Z2数量80/4/32/44。四区严格不重叠，误差平方和等于全域；total/scattered误差分子的背景相消，并非两套独立误差。

| p5/Z2差平方份额 | E | H |
|---|---|---|
| 缺口外空气 | 68.2085% | 67.5995% |
| 缺口空气 | 2.9345% | 2.9462% |
| 基底 | 4.3995% | 4.4000% |
| Si块 | 24.4575% | 25.0543% |

E差平方中y分量96.9269%；H在x/z分量约各半。它说明这不是仅缺口内的小局部误差；未知仍包括更细z分辨能否足够、横向不同散射相位和边缘贡献。不能宣布抵消、网络不足或某单一方向是唯一根因。当前两个增量还不够小，更不能给连续误差上界、模式截断收敛或原尺寸准确解。完整[区域数组归因](records/physical_error_regions_v51.json)只读取本批新数组，没有新FE/谱分析。

## 费用、因子生命周期与安全

把单元内部未知量先精确消去，缩小全局直接解，再把内部系数恢复出来，这一步仍有本批finite直接LU成本。F4/N4分别29/30个局部LU，N5为30、Z2为51；Z2实际26个raw体类和51个oriented Schur类。局部tensor/LU/recovery/Schur字节可能共享，不能将其累计载荷相加当同时RSS。有限全局p4/p5 MUMPS因子存在：保存合法返回向量后释放factor和凝聚矩阵，保留独立原弱式及最小恢复包；原因子不是生产p4粗逆、未藏fallback。

| 互斥阶段s；不加inclusive父计时 | F4 | N4 | N5原返回／失败阶段 | NH |
|---|---|---|---|---|
| mesh/MPC | 0.445322 | 0.358742 | 1.003151 | 0.775075 |
| 新q47/q63资格 | SETUP另费 | 复用同身份 | 18.229960／94.340440 | 19.614054／102.718931 |
| JIT／全部C/D/H | 28.201408 | 15.424569 | 36.756927 | 20.213423 |
| 内部凝聚／局部因子 | 142.937675 | 74.874926 | 400.952931 | 639.390018 |
| 全局factor（NH含symbolic） | 5.207626 | 2.702449 | 10.455195 | 1.242393＋17.951588 |
| solve／一次精化 | 0.176327＋0.543470 | 0.218361＋0.242425 | 0.532402＋0.532157 | 0.843315＋0.805011 |
| E/H输出＋全部功率／体吸收 | 0.091378＋2.534627 | 0.135138＋2.353923 | 0.471238＋6.669517 | 0.915461＋0.234914 |
| dat启动到退出下界 | 294.248354 | 118.554778 | 625.778514，补审再142.573980 | 841.587038 |
| 采样整树峰GiB | 1.032608 | 1.007263 | 2.245213，补审1.228489 | 3.496330 |

SETUP启动下界140.924203s；唯一VERIFY788.376920s，其中原作用准备约336.569180s、共同场积分410.472440s。F4还有真实解析积分与独立解析弱式约65.924s，不把这些审核时间相减后称新实测加速。N5补审实际126.847857s监督/142.573980s启动，其中共同积分83.497156s和方向指标11.081383s；原610.305686s失败费用完全保留。所有audit/IO未逐一分开的余量保持unknown，不将launcher或CFFI callback笼统叫LU。

每case数值对象冷构造，但OS/JIT缓存未清、边界资格按精确身份复用，所以这里只给冷N=1执行链下界，不能声称无缓存冷/无争用重复中位数。研究总费用含失败、准入、资格、补审、唯一VERIFY和所有收尾；独立审核全部算成本。[互斥费用](records/cold_n1_costs_v51.json)、[对象生命周期](records/object_lifetimes_v51.json.gz)和[最终账](records/resource_costs_final_v51.json)分列，不以阶段inclusive总和造“完整时间”。

NH的三倍稠密上界29.659995GB不准numeric，先用原cell图给装配规划11.399363GB；实际sparse symbolic estimate1768MB，按2倍＋live树2261233664B＋2GiB将numeric规划冻结为7944717312B，小于16GiB。既有后端ICNTL23=3536MB、ICNTL22=0；无ordering/shift扫描，没有用OOM探容量。采样峰3.496330GiB与预测口径分开，opaque factor/workspace包含在树峰，未伪造独立因子RSS。

新窗口09:05:22.289231Z开始，7h含实现/测试/修复/等待/计算/交付，heavy-stop15:20:22.289231Z；数值有载最多18000s。MPI1、数学1、CPU逐stage重新选0/1/4/5等现场空闲物理核，避忙SMT；complex128/int64、GPU/ownswap/OOC0；所有结果/JIT/TMP/bytecode独立。规划16GiB、warning20GiB、采样停止24GiB，自有锁、原PSI/系统与邻增长余量不变。无内核cgroup连续硬峰声明；实际采样最大间隔以最终资源账为准，科学阶段2.374964s。早期CPU准入拒绝及215.239782s冷却保留，后续未触资源停止；无法以邻任务不可比阶段证明无干扰，所有性能标shared-workstation/INCONCLUSIVE。

## 两个下一尺度及唯一建议

下表只推导保持本NH绝对单元宽度/p5时的两个更大几何，不分配新mesh或目标向量。NOTCH当前精度不合格，所以二者均不准自动启动。

| predicted/not_run | 2倍几何 | 4倍几何 |
|---|---|---|
| cells／native／独立FE | 1280／499380／483200 | 10240／3917160／3852800 |
| trace／内部 | 176000／307200 | 1395200／2457600 |
| manual容量设计aliases／凝聚行 | 1924／177924 | 7300／1402500 |
| 一条完整complex128向量B | 7731200 | 61644800 |
| C+D单mode流式区间B | 102400..1105920 | 409600..4423680 |
| 全boundary-cell支持库存保守上界B | 2127790080 | 32292864000 |
| 局部cache无去重上界B | 17915904000 | 143327232000 |
| 单张全稠密矩阵上界B，非稀疏RSS预测 | 506511196416 | 31472100000000 |
| sparse factor fill／workspace／同时RSS／迭代数 | unknown | unknown |

低端端口载荷只表示理想切向trace，实际本合同不剪裁浮点非零内部/法向支撑，因此上端保留全部boundary-cell自由度。manual模式数是按索引范围比例的容量设计，不等于AUTO或截断资格。去重类数、输出缓冲、MPI通信和opaque后端工作区都可能增长；只把当前3.5GiB峰线性乘cell数是不可信的。原尺寸50×25×140nm还有更大不同模式库存；这里没有证明2TB/48h。

唯一下一pilot为同物理、同532、p5的预登记Z4完整NOTCH对照，不扩大几何、不训练；需新的集中合同先审容量与共同场验证。它预计320cell、120800独立FE、44000trace、76800内部、44532凝聚行，已超本批35000门；没有可信numeric估计不得赌OOM。本批在唯一Z2之后关闭，不自动执行此建议，也不把一次p/h增量当连续收敛。

NN20%仍要求对最佳合格非神经完整引擎，在同正确性下完整耗时或同时峰至少改善20%，另一项合规。诊断即便尾部factor/solve免费只省2.0–2.7%，排除将几秒尾部校正当全程突破。准备链更乐观必要条件fV-H≥0.2*T_B中，H含冷数据/teacher/训练/加载/推理/清理/纠错/审核；最强准确基线和同时峰可省份额未知。当前NOTCH未准确，不能给它授性能分母或重新启动旧NN/codec路线。[必要费用界](records/necessary_NN_cost_conditions_v51.json)只是排除/机会条件，不是NN收益。

## 交付、测试和保留项

最小迁移只读冻结extra源码的carrier/完整curl弱式/包络周期和精确端口坐标小核，donor逐文件blob/hash见[迁移](records/minimal_migration_v51.json)。本支不做隔壁5nm M5训练/greedy、340通道或teacher，未读取其活跃工作树、启动或通知隔壁。生产default未改变，选择合入仍需审阅，见[依赖分组](records/selective_merge_manifest_v51.json)。

测试只覆盖新依赖：十项targeted、小复系统/真实UFL退化、八dat/schema、真实1s超时清场、真实全532及解析FLAT/完整NOTCH；相关Ruff/compile与一次15项紧凑文档合同。checker真正从保存action/端口/恢复数组及原Poynting公式复算，负结果不由status推导。没有CI、全仓pytest、全旧artifact哈希或索引重建。GitHub精确页无视觉证据，NOT_VERIFIED，科学结果独立保存不等网页。

普通bug只修复N5的波矢float后处理，已合法返回的解未重算；另在NH扩大前补可靠容量准入、在新记录中明确物理ref-plane复通道口径，保留raw诊断。后续source没有改旧case、原阈值或历史FAIL。局部solver、全局factor及数组仍如实列出，失败/冷却/未知费用不清零；old task/review/response/raw保持，V50窗口不重开。

最终证据以[交付索引](records/delivery_index_v51.json)、[科学门](records/phase_accuracy_checks_v51.json)、[完整新数组](records/array_inventory_v51.json)、[原始日志](records/raw_archive_index_v51.json)、[结算补档](records/post_settlement_archive_v51.json)、[最终source](records/source_bindings_final_v51.json)、[资源](records/resource_costs_final_v51.json)、[测试](records/tests_v51.json)与[实际文档字节](records/documentation_checks_v51.json)为准。数组和JIT保持ignored，Git只提交本批增量及父hash，不层层嵌套旧JSON。closed/active null、清场/锁释放、同分支push及实时remote/clean核实后暂停，不merge，不通知隔壁。
