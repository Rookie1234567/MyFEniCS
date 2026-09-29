# Task042 V7：真实材料下的神经 FE 单次求解对照

**材料解除；M0、真实 N1、三路线及独立 p3 盲验证完成。NEURAL-TRACE、FREE-FE-OPT、FE-LSQR均未达到原方程／场／功率 Gate，p4 enrichment未准入。终态 NEURAL_OPTIMIZATION_NEGATIVE；最终0.7nm／48h NOT_QUALIFIED。** 旧V1–V6记录不改，不再回到已关闭的p4近似逆路线。

新方法让网络先产生三维复向量，通过原有限元的边／面矩转成trace系数；单元内部再由原局部方程恢复，所有外部端口幅值一起优化。希望避免大规模全局分解，代价是每步网络前后向及原S/Sᴴ作用。FREE直接优化全部FE系数，检验收益是否仅来自优化器；LSQR直接用同一线性方程，检验网络是否胜过无需网络的线性方法。本轮全部只解一个固定micro激励，没有准确解训练、warm start或参数扫描。

| 范围／数据身份 | measured／derived／not_run | 入口 |
|---|---|---|
| 材料 | 四行永久离线可读；本次只加载nominal0.7，明确source0.699999988 alias，MATERIAL_READY_USER_SUPPLIED | [载入及来源](records/material_loaded_v7.json) |
| 原物理／几何 | 384 hex、p3/h0.175nm、grazing1°、s；原双Floquet/DtN；FE34050／独立trace18144／内部13824／slave2082 | [真实身份](records/material_geometry_identity_v7.json) |
| 真实端口 | top20＋bottom20＝40；原物理库存自动生成，未套旧80或删通道 | [完整库存CSV](records/channel_inventory_v7.csv) |
| 完整N1 | 原S、Sᴴ、native、非零内部和port RHS、恢复、方向／MPC、真实梯度全部通过 | [原字段／复算](records/adjoint_gradient_checks_v7.json) |
| 三路线 | 三次独立从零、冻结source和状态；全部未资格化 | [对照](records/neural_fe_comparison_v7.csv)、[226审核点](records/convergence_checkpoints_v7.csv) |
| 盲参考 | 三路线结束后一次p3 global LU；先symbolic Gate，释放后原FE/E/H/功率验证 | [参考与独立Gate](records/independent_blind_validation_v7.json) |
| 条件验证／目标 | p4因无合格候选not_run；F5/p6、最大目标、GPU、旧teacher/seed420620、四波长扫描not_run | [决策](records/neural_fe_gate_decisions_v7.json) |

## 材料、离散和未知量

canonical路径为 [input/materials/si_optical_constants_v1.json](../../../input/materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`；SHA256 `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。原表0.7/2是user_supplied/user_authorized，5/13.5来自冻结旧输入；原十进制字符串、历史SHA/blob、Review V4 commit、完整复平方检查值均保留。无原数据库版本不再构成材料blocker，未知波长拒绝，不作nearest/interpolation。

| nominal nm | Delta／Beta 原值 | 实际 epsilon=n*n（real／imag） |
|---|---|---|
| 0.7 | 0.000114859526 / 4.32477054E-06 | 0.9997702941220071 / 8.648547597811433e-6 |
| 2 | 0.00119851693 / 0.000213688647 | 0.9976043569199937 / 0.00042686507507764344 |
| 5 | 0.00603145547 / 0.00435380777 | 0.9879545118729887 / 0.00865509594462061 |
| 13.5 | 0.000997695141 / 0.00182649365 | 0.9980022690345409 / 0.0036493427323206554 |

求解λ=0.7nm，source标签字符串0.699999988原样绑定，n=`0.999885140474+4.32477054e-6i`；exp(-iωt)、mu=1。Si基底／块／解析layered background／底端口一致，air n=1。未将delta/beta当epsilon或取abs(n)²。

范围x[-0.7,0.7]、y[-0.525,0.525]、z[-0.175,1.225]nm；Si基底z<0、块x[-0.35,0.35]／全y／z[0,1.05]，空气缺口x[0,0.35]／y[-0.175,0.175]／z[0.35,0.70]。实际air200／substrate48／block136、notch8，六面facet48/48/64/64/48/48。canonical mesh SHA `7f19322a0e3d610a2ef4080118dd3ac1c535e52ac888085266ea632e8c63e8e3`，geometry/tags SHA `459c2fe77aa175edf70d30d6b9a7bee7dee7759b00a96097cbac089fa1787ced`，physical SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`，mode SHA `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262`。

网络固定3×64 tanh、8组三分量复包络、真空载波、seed420906，11696 FP64实参数。完整边36＋面72 trace矩／cell经Piola、orientation、唯一master owner及原MPC进入18144个独立trace；2082 slave只由MPC展开。网络不预测13824内部系数，使用原36行/cell局部恢复；40复port另80实参数。FREE直接使用36368实参数；LSQR使用18184维完整trace＋port向量。三者均无global FE逆或隐藏初始化；已知背景只是原方程精确换元，内部particular来自原局部载荷。

## N1与真正的方程

材料独立的V6 q15/q30 moment配对复用；真实S来自目标degree3单层、原体／DtN／MPC，不建p4/p6层。三原FE配对最大S2.605e-16、Sᴴ dot1.917e-15、native8.491e-15，恢复／Schur-native身份约1e-15，slave-zero。非零内部RHS范数164.995964、port8.105587，均检查原native和port符号；没有用端口零值或合成195维测试替代。

```math
L(w)=\frac{\lVert b-Sz(w)\rVert_2^2}{2\lVert b\rVert_2^2},\qquad
g_z=-S^H(b-Sz)/\lVert b\rVert_2^2.
```

每次loss先组装完整残差再求范数，未使用局部残差平方和或抽样元素／端口。Sᴴ是共轭转置乘法，不是伴随求解。真实三非零方向、h=1e-4/1e-5/1e-6共9项FD最大相对差1.821306846e-9，至少两个连续h通过；真实分块VJP与一体配对0。forward/VJP每块重算，不保留全mesh autograd图。N1未读取目标解，optimizer更新0。

## N2：完整残差与盲场比较

所有比值dimensionless。Schur分母固定为原散射b；native使用对应原散射载荷，augmented含未凝聚体／port。独立total-native使用原total RHS，是另一固定分母，不能与前者混称。

| 路线 | Schur／限1e-6 | 未凝聚aug／限1e-6 | native散射／限1e-6 | 独立total-native／限1e-6 | port绝对数组范数／固定RHS／operation-relative |
|---|---|---|---|---|---|
| NEURAL-TRACE | 0.913263145 | 0.354166901 | 0.661163226 | 0.229423234 | 8.288413e-4 / 0.003887693 / 0.003140447 |
| FREE-FE-OPT | 0.797338565 | 0.309210911 | 2.179411163 | 0.756254336 | 0.004305684 / 0.020195881 / 0.446120482 |
| FE-LSQR | 0.071602580 | 0.027767751 | 0.028727752 | 0.009968512 | 1.761764e-4 / 8.263581e-4 / 0.656567941 |
| 独立p3参考 | 6.42415e-12 | 2.54382e-12 | 3.01796e-12 | 1.43744e-12 | 8.723611e-15 / 4.091824e-14 / 1.503947e-14 |

三候选recovery分别2.1284e-13／6.1579e-14／1.7260e-15、slave0通过原1e-10身份门限。其他方程门限全部失败；没有由放大port分母或total背景规模获得资格。

| 路线 | 全场L2／scaled-curl相对差 | selected E／H相对差 | 完整复port差 | scattered L2相对差 | energy closure绝对／限1e-5 |
|---|---|---|---|---|---|
| NEURAL-TRACE | 0.06919646 / 0.06919723 | 0.06914946 / 0.06942873 | 0.06903300 | 0.66125064 | 0.07034118 |
| FREE-FE-OPT | 0.10550940 / 0.10546635 | 0.10500655 / 0.10558820 | 0.10423453 | 1.00826204 | 0.00733968 |
| FE-LSQR | 0.10463993 / 0.10464025 | 0.10464453 / 0.10464821 | 0.10450793 | 0.99995326 | 0.00337133 |

全场／curl／selected复E/H／复port标准1e-4均未满足。H_code=curl(E)/(i k0 mu_r)，采用项目模式的归一化H；相对差与物理H的共同常数缩放无关，未拟合相位。六个固定cell中心的完整复E/H、40个ordered复port及每通道功率均已存入[独立验证](records/independent_blind_validation_v7.json)和[通道CSV](records/channel_observables_v7.csv)。参考total/scattered L2分别1.9151545/0.2004110，scattered port norm0.1974501，信号不是可忽略的零散射。

以下三候选功率明确是**未资格化诊断**，不能作为official结果。参考为同离散准确场，不称连续极限。

| 状态 | R_total | T_total | A_balance | A_volume | R00_s／R00_p／R00_total |
|---|---|---|---|---|---|
| p3参考 | 0.117645819 | 0.877047783 | 0.005306398 | 0.005306398 | 0.117644762 / 1.034e-27 / 0.117644762 |
| NN诊断 | 0.089067048 | 0.835562015 | 0.075370937 | 0.005029755 | 0.089065872 / 4.147e-7 / 0.089066287 |
| FREE诊断 | 0.114817729 | 0.887199077 | -0.002016806 | 0.005322870 | 0.114715296 / 1.479e-6 / 0.114716775 |
| LSQR诊断 | 0.113248845 | 0.884808516 | 0.001942640 | 0.005313967 | 0.113248661 / 1.780e-27 / 0.113248661 |

参考体吸收grating0.0039305467、substrate0.0013758510，闭合2.90634e-12；R/T(-1,0,s)=8.38000015e-7/7.89288729e-7，R/T(-3,0,s)=9.29438327e-8/8.77596447e-8，所有级完整记录。候选最大单通道功率差0.0414858/0.0100632/0.00776155，远超1e-6；R/T/A与体吸收不能只选接近的一项判成功。

NN比两个对照更接近参考场，但依然不满足原方程、场、能量门限；其2小时费用没有产生合格解。LSQR把Schur降到0.0716却几乎未恢复真实散射场，说明loss下降不能替代场验算。空间限制、变量尺度／病态与优化预算的贡献未单独定位，不能宣布唯一根因或全部神经方法无效。神经增量NOT_DEMONSTRATED，无合格、同正确性20%收益对照；共享性能INCONCLUSIVE。

## 生命周期、时间与内存

每次正式运行均为clean源码、scripts/run_case.py独立one-run dat。NN 1611 closure／Adam500／48完整L-BFGS外层调用，最后一调用预算中断；S1677/Sᴴ1611/audit66。FREE2000/500/69，S2082/Sᴴ2000/audit82；LSQR1921步，S1999/Sᴴ1922/audit78。Adam和全部strong-Wolfe回退均计closure，未用小梯度success早停、补跑或调参。

| 独立阶段／shared-workstation | CPU | 全树wall s | 同时RSS采样峰 B | 源码 |
|---|---|---|---|---|
| M0材料／真实库存 | 12 | 3.418278214 | 243851264 | 70f5f543… |
| M1真实FE作用／JIT／恢复 | 0 | 199.162803520 | 820604928 | 70f5f543… |
| M1真实梯度 | 0 | 30.491336455 | 682270720 | 70f5f543… |
| NEURAL-TRACE | 0 | 7149.384082808 | 760279040 | 7c4037a2… |
| FREE-FE-OPT | 0 | 592.483452100 | 753737728 | 7c4037a2… |
| FE-LSQR | 0 | 564.795250180 | 560558080 | 7c4037a2… |
| p3参考＋后处理失败 | 0 | 14.456428306 | 1073967104 | 19adac7e… |
| 仅后处理修复重放 | 0 | 25.633409183 | 700133376 | 1ff6f8ba… |

完整source SHA、input/physical/artifact hash与环境见[run index](records/run_index_v7.json)。正式wall共8579.825040766s；顺序运行同时树峰取最大1073967104B，不加总。所有own swap0／后代清场。V6 carry101.861302031s和全部辅助／失败／检查／发布费用继续计入10h，最终更新在[全过程费用](records/resource_costs_v7.json)。编辑／Git交互会话未连续采样，不伪称精确全会话RSS。

| worker内排他分项 s（包含在父wall，不再次加总） | NEURAL | FREE | LSQR |
|---|---|---|---|
| 网络前向／矩映射 | 1600.525922 | 0 | 0 |
| 网络VJP／分块重算 | 5051.039604 | 0 | 0 |
| 全部S | 156.681770 | 184.582420 | 176.421895 |
| 全部Sᴴ | 299.605383 | 348.823869 | 349.301652 |
| 原方程audit（扣除内含S） | 24.260457 | 29.930444 | 28.482348 |
| optimizer（扣除closure） | 4.080166 | 14.101274 | 0 |
| I/O | 0.495493 | 0.384740 | 0.334774 |

共同FE准备mesh/MPC0.662889、原作用JIT12.739352、局部凝聚／端口169.634530、载荷背景／packet2.372972、独立FE审核8.332895、packet I/O1.325469s。NN完整closure累计7134.945174s，除1611仅为此micro共享条件的平均4.428768s，不是目标规模完整步实测；原JIT冷费用另列，未宣称清除了争用。

参考只在三状态冻结后构造global p3 CSR，one symbolic603 MB，numeric准入9592 MB、ICNTL22=0、一次numeric/solve，factor销毁证据保留。后处理一个UFL Form除法错误最小修复后只重放FE/E/H/功率，新增symbolic/numeric/solve均0；没有重做长轨迹或参考以填计时。异常前子timer未保存，数值／审核费用包含在14.456s父wall，单独值unknown。

候选无global p4 LU／层、global FE CSR／LU、Riesz/ILU逆、private audit CSR或fallback；局部36行LU／Schur／原F与恢复按122实际类复用，普通默认不变。构造前包含临时拷贝、完整port、库／JIT、optimizer的保守容量6113460224B；跨ABI packet payload209239672B。模型参数93568B并不等于全过程：内存转移到局部原张量／Schur／恢复、padded40-port数据、Torch/optimizer历史、chunk激活重算和审核工作区。[容量与48h账](records/target_48h_budget_v7.json)。

继续用户受控共享授权，只有Task042 §2.3独占限制被覆盖，原合同历史及邻锁不改、F0未冒称正式review通过。每次现场核查48实际物理核、忙碌worker/监督器/加载线程、SMT、MemAvailable/cgroup／磁盘／GPU后选核，MPI1／数学1／Torch intra/inter-op1／DataLoader0，编译1；仅自身nice10/idle I/O、自有nonblocking锁、隔离cache/results/artifacts。原FE前缀只读，CPU-only ML，不安装ABI/CUDA，不碰邻任务。

16GiB hard／12GiB warn、swap0、磁盘50GiB／artifact20GiB与系统＋128GiB邻增长余量保留。无cgroup委派，已有configured0.5s整树采样停止监督，实际包含采样开销，非连续内核限制。全正式样本无不可读树／warning／持续PSI触线；最小effective_available942196768768B、reserve353748992000B。两GPU持续约99–100%，本任务VRAM0。邻阶段只读短记录缺可比速率，影响INCONCLUSIVE；不承诺绝对零干扰。[低开销资源证据](records/resource_observations_v7.json)。

## 资格、测试、48h与唯一下一步

独立checker从原残差字段和完整复E/H／通道重算，忽略saved status，确认方程／场／功率0/3；FE L2/curl标量来自同一独立DOLFINx积分，没有重复FE。[模型／数据身份](records/dataset_model_provenance_v7.json)。最终32相关pytest及此前CPU-only2000closure预算断言通过，新增代码Ruff/format/compileall与局部Markdown检查通过；一次测试路径误写已修正，失败保留。Review V4实际GitHub4表1math通过，无review改写、全仓清理、full pytest、MPI2/4或CI声明。

p/h、MPI和M未扫描，只有这个p3/h0.175/M40/MPI1模型；p4 enrichment没有合格候选不准入，因此离散误差NOT_RUN，连续极限NOT_PROVEN。没有F5／p6、最大模型或旧seed420620消费。

目标geometry/规模、真实channels、精度冻结、实际资源配额、完整步cost和所需步数仍unknown；材料已ready，不再以旧材料不足收口。micro仅x/y/z几个波长，不能据它计算目标48h可负担步数，也不分配目标大对象。**唯一下一建议：同一pilot上一个预登记、无需目标准确解的对角变量尺度均衡FE-LSQR对照，原loss及完整验算不变。** 用它检验残差下降却缺失散射方向的尺度／病态因素，不保证有效，未实施，等待review；不加网络、不回旧p4、不自动更大模型。

| Selective merge依赖组 | 内容／依赖／证据 | 边界 |
|---|---|---|
| production numerical/core | 无新合格solver；材料离线表/转换可独立审阅 | 不提高神经／LSQR为默认，不改原A4/A6/MPC |
| research-only numerical | degree3单层packet、真实adjoint/VJP、固定三路线、后冻结p3参考 | 依赖V6完整moment＋材料；真实N1与盲验证，三路线负结果 |
| reusable runner/watchdog | 原run_case/share仅必要V7 opt-in、budget与既有整树监督 | 一dat一stage，own lock；不复制watchdog或改变普通默认 |
| checker/benchmark | 复数observable/Gate checker与32相关测试 | 无solver复写，无FE长重放 |
| compact evidence/docs | 四行材料／完整通道／raw scalar／source/hash／费用／响应和总账 | 历史保留，建议只依赖顺序审阅合入 |
| do-not-merge | packets、checkpoint、accurate reference、global reference矩阵/因子、JIT/cache/大日志/临时helper | ignored只在NN-Lab；不提交大型运行对象 |
