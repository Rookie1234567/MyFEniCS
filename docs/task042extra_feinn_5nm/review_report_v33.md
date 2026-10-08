# Review V33：关闭实波矢续扫，检验含衰减的神经波表示

## 0. 裁决、目标与本轮身份

**V33两条真实回拟合及独立验收均未通过。接受其负结果与工程修复，不授予M5求解、NN收益或0.7nm资格。关闭原样实波矢回拟合、从零重复greedy和单纯加列。下一轮仅检验一个物理表示变化：让神经指数同时具有可学习的振荡和指数衰减，而不是只学习实波矢。该变化有源码及材料依据，但尚未证明是旧失败的主因，更不保证收敛。**

本支只做神经研究；不回到W0/W1、原尺寸全口面、模式恢复、主线接入、传统PC或存储工程。不向Task42、主线、dot、master或其他工作树安排工作。原生FE算子、参考与后处理只服务于本神经试验。

```text
repository          = Rookie1234567/MyFEniCS
branch              = task42extra_feinn_5nm
canonical           = /home/fenics/Projects/NN-Lab-V2
original_base_SHA   = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_HEAD       = 427c1762ea8838f35a13bf2a0ebc1ad3ab46c63c
result_commit_time  = 2026-10-08T14:30:34Z / 2026-10-08 22:30:34 +08:00
review_date         = 2026-10-09 Asia/Singapore
response_reviewed   = response_v33.md
previous_review     = review_report_v32.md
campaign            = V34_COMPLEX_WAVE_NEURAL_REPRESENTATION
required_response   = response_v34.md
new_research_cap_s  = 57600
ordinary_default    = UNCHANGED
merge               = NOT_APPROVED
```

最终目标是0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN，在十进制2e12B整机物理内存且留系统余量、ownswap/OOC=0条件下，单场必要准备、求解、恢复、输出和独立检查≤172800s。原50×25×140nm目标尚未资格化。本轮16h是研发上限，不是目标48h成绩，旧费用不清零。

本报告明确覆盖V32中“禁止复波矢”的限制、相应参数schema和本批预算；不改原物理方程、离散、误差定义、标签隔离或安全阈值。普通bug同批修复，不按次数交棒；科学负结果、资源/权限硬条件与总预算仍有明确出口。不能把“持续执行”理解成无限重试或保证PASS。

## 1. 审阅依据与最新结论

已实际读取最新response、summary、专题、原规则、材料、原任务身份及相关源码，核对上版发布以来8次提交的变更清单。上一Review V32从已挂载完整副本读取并核对远端blob；原task和任务目录规则未变。目录未出现新的独立补充任务书。本端未SSH、未执行M5训练/FE、未取得工作站大数组；没有逐数组重算完整Gate。下表为仓库已发布measured，不是审阅端新测量。

| 同M5/5nm/384hex/p3/31968独立复FE/40端口 | 确定性回拟合 | 梯度学习回拟合 | 原要求 |
|---|---:|---:|---|
| 固定列/块；访问/接受q更新 | 1377/246；32/26 | 1377/246；32/16 | 数量不是精度 |
| native/augmented相对残差 | 0.145267760566 | 0.153422848264 | 各≤1e-6，FAIL |
| 独立total原残差 | 0.0688135940267 | 0.0726766734318 | ≤1e-6，FAIL |
| 散射E相对L2误差 | 0.0169085982306 | 0.0261450641986 | ≤1e-4，FAIL |
| 散射H/scaled-curl相对误差 | 0.0170339038993 | 0.0262147320859 | ≤1e-4，FAIL |
| 独立体吸收能量闭合 | 0.00411715027038 | 0.00851200542286 | ≤1e-5，FAIL |
| 最大逐级功率绝对差 | 0.00285115820236 | 0.00548620931117 | ≤1e-6，FAIL |
| 实际点值→完整矩重建 | 6.06332494493e-14 | 9.37729176923e-13 | ≤1e-10，PASS |
| 新增完整路线跨度/s | 7629.76473598 | 5196.90465669 | 含失败/暂停/审核，不重复加内部attempt |
| 必要历史前缀归属/s | 10186.178641493432 | 10186.178641493432 | 项目历史已收费 |
| 路线同时树采样峰/B | 4170592256 | 4186972160 | ownswap0，非连续内核硬峰 |

证据：[Response V33](response_v33.md)、[专题](outcomes/fixed_capacity_backfit_v33.md)、[数值Gate](outcomes/records/full_numerical_gates_v33.json)、[成本](outcomes/records/cost_and_capacity_v33.json)、[运行](outcomes/records/run_index_v33.json)。控制终态source=`86417820b04a5abd56892d37a1ce15279d783c7a`；学习终态及最终独立验收source=`f1ae5d7b7319836c802aad548e02e0f016798bef`，不得用发布HEAD替代。

确定性终态比共同起点2.889%的场差改善，但神经终态仍约2.615%，并劣于其首检查点2.514%。原残差降低不代表场误差单调降低。两条按第二个预登记数值节点停止，非OOM、PSI、writer失败或人为耗尽预算；强相消、状态重绑定和日志bug已处理。不能再把未通过解释为“差修最后一个bug”。

多尺度V32相对V31恢复了大量散射场，这是已测阶段性进展；V33证明有限次实波矢回拟合没有把它提升到要求。它没有证明所有NN无解，也没有证明整个1377列非线性模型的全局最优，但已足以关闭这份投入配置。新假设必须改变表示机制，不能只换优化器/seed维持试验。

## 2. 新机制的依据及不允许的过度推断

### 2.1 源码事实与物理量级

[WaveMoments](../../src/solvers/neural_wave_moments.py)明确将q转为float64，并使用窗口乘exp(i q·d)。复幅值p不等于复波矢。局部窗口可以改变包络，多波叠加也可以逼近衰减；因此不能说旧模型数学上不能表示衰减。准确的限制是：**每个指数神经元本身没有可学习的指数衰减率。**

用[统一Si表](../../input/materials/si_optical_constants_v1.json)、空气入射、掠角1°，对均匀Si内沿正向深度的平面波，推导：

```math
k_0=2\pi/\lambda_0,\qquad \beta_{\rm Si}=k_0\sqrt{n_{\rm Si}^2-\cos^2(1^\circ)},\qquad \mathrm{Im}(\beta_{\rm Si})>0.
```

| derived，非M5运行结果 | 5nm | 0.7nm |
|---|---:|---:|
| beta / nm^-1 | 0.0473985000+0.1441773440i | 0.0778013439+0.0044780583i |
| 振幅1/e深度 / nm | 6.9359025 | 223.31107 |

5nm均匀Si波沿深度7.5nm的振幅比约0.33914；这是单个解析分量的量级，不是M5散射场答案。0.7nm材料不同，不能将5nm改善自动迁移。上下端口的全局z符号仍按原出射约定，不能直接把表中正向深度beta当成两侧kz。

参考[3D球内倏逝平面波稳定逼近研究](https://smai-jcm.centre-mersenne.org/articles/10.5802/smai-jcm.130/)及[VarPro神经PDE](https://arxiv.org/abs/2201.09989)。前者为标量Helmholtz和特定域，不是有损非可分Maxwell；其“纯传播波”的假设也不等于本项目带窗口、可变实频率的整个函数类。本轮只借鉴复传播向量可降低表示压力的机制，不搬用其不可能性或收敛定理。论文完整HTML未在本端成功加载，不宣称逐页复现。

### 2.2 唯一新函数族

```math
\psi_{j\nu}(x)=\chi_j(x)\exp\{[i q_{j\nu}-\kappa_{j\nu}]\cdot(x-x_j)\},\qquad
E_s(x)=\sum_{j,\nu}\psi_{j\nu}(x)p_{j\nu},\qquad c=I_h^{\rm curl}E_s.
```

q和kappa各为3个实参数，单位nm^-1；p仍为3分量复幅值。kappa=0精确退化到原模型。它让网络直接学习衰减方向和尺度，增加非线性参数但不增加1377个复线性槽、波数、窗口或FE自由度。仍在原p3空间中求解，不能突破该空间的离散精度。

不增加材料gate、不切换DG、不开发另一套边界或传统求解器；不同时改loss。局部窗口乘指数一般不严格满足局部Maxwell齐次方程，自由q/kappa也不强制色散关系，因此不得称精确Trefftz基。物理色散只用于校准和预登记种子；原A/f及最终全场负责验收。

## 3. A/B：新复波矢核与校准，一次接完全部链路

### 3.1 参数、导数、数值稳定性

不能把complex q塞进原float64转换让虚部静默丢失。新增显式schema，将q_real、decay_kappa、窗口、T、幅值、单位及缓存身份完整保存；旧schema读取kappa=0但旧hash/原始记录不改。候选生成、完整矩、VJP、差量、缓存、导出、独立点值重建、checkpoint和复读都必须支持kappa。

令d=x−x_j，则：

```math
\partial_{q_a}\psi=i d_a\psi,\qquad \partial_{\kappa_a}\psi=-d_a\psi.
```

梯度采用实参数约定dL=Re(g*dc)。优化变量为q/k0和eta_a=kappa_a R_a，R_a是该窗口实际支持与域相交后，相对中心的最大坐标距离；全域用真实域边界，不误用旧半径。链式因子分别为k0和1/R_a。

固定q/k0分量界±4，eta分量界±8/3。因此所有实际评价点上指数实部绝对值≤8，允许有符号局部增长/衰减但不改变材料被动性。不得用abs(kappa)、指数clip、FP32或后验截断修改模型。边界方向必须显式投影；错误方向回滚。R_a=0或非有限数视为输入错误，不能加epsilon掩盖。

微小参数变化用原基点指数乘expm1((i delta_q−delta_kappa)·d)，避免近指数相减。沿用已通过的补偿累加、围绕原完整态的差量幅值求解、经济型QR删除/插回；活动块之外的投影不能包含活动列。保持原T、原列掩码和rcond=1e-12；每次试探重求全部线性幅值，禁止增加旧被丢弃幅值方向。数值秩改变要记录并核验，不能把跨秩点当光滑导数保证。

原方程r=f−Ac，目标仍phi=r*r/(2f*f)。对实参数z=(q,kappa)：

```math
d\phi[z][\delta z]=-\frac{\mathrm{Re}\{r^*A[dC[z][\delta z]]b\}}{f^*f}.
```

不得引入Gram逆、Maxwell逆、全FE Krylov完成器、teacher或A*A。用既有矩/A/A*和不超过24列活动块；数值核进src，旧普通默认不变。失败的缓存不能通过重建全部历史前缀“修复”。

### 3.2 必需资格及物理种子

| Gate | 必须实际验证 |
|---|---|
| kappa=0回归 | 四种支持、全部边/面/内部矩、c/A作用/VJP与旧核≤1e-10；旧schema正向读取、新虚部不可被忽略 |
| 复波核 | 非零q、非零kappa、纯衰减、上下符号、三极化、非单位Floquet；独立点值完整矩和原A/A*≤1e-10 |
| 实参数导数 | 含q-only、kappa-only和混合方向的中心FD，稳定步长区相对≤1e-5，近零另列绝对量；必须非零幅值 |
| 线性读出 | 小复数非Hermitian及秩亏例与独立LS≤1e-10；活动列删除、T/置换、中心差量、接受/拒绝回滚和实际保存复读 |
| 真实初态 | kappa全0还原共同c/r≤1e-10；不以新QR悄悄改变起点；只复用健康已资格化数据 |
| 求积 | 网络矩q30/q60及对应原作用≤1e-8；漂移时按固定相位/衰减跨度细分积分并独立配对，不改FE算子或科学门 |

5nm/0.7nm各做一个均匀介质衰减平面波的局部校准：K·K=k0²epsilon、K·p=0用非共轭双线性点积，curl(E)=i K×E。校准原函数和同场独立FE插值分别比较；原函数准确不代表p3连续精度。不给M5训练提供解析散射答案，不新建平界面PDE或重求历史参考。

共享物理种子只用已知材料、原入射横向波矢及方向约定，不用参考场。每个活动块候选包括原态和±Im(beta_Si)的z向衰减（投到上述eta界，明确记录投影）；其他分量初为0。两路线得到完全相同的种子和代价，原态可被选中，不强迫非零kappa。可在4个预登记global/粗/中/细块上各最多8次真实无标签试探作资格见证，然后完全恢复共同初态；一个块无改善不取消其余块或合格后的C。

## 4. C：一对固定容量、含衰减的真实对照

### 4.1 共同初态与标签边界

复用[anchor_identity_v33](outcomes/records/anchor_identity_v33.json)定位的V32最终FIXED模型：1377列、246块，原native约0.15743176704993547，anchor描述hash=`737dd067f2cc3ebe021f3c7f445992c87d993e562213c62cc7a40b148a33501e`。这个hash是原索引中的anchor身份，不冒称每个模型NPZ的hash。所有实际文件另按原索引核对。

不取V33更好中间场、不取V33两个终态、不用旧LEARNED或监督权重。沿用无标签固定前缀是为了明确比较增量，不重新从零造1377列。必要前缀10186.178641493432s继续归属；原参考hash=`0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7`只供隔离验收。缺失先查已声明副本，不以重训或重算参考当默认补救。

物理不变：M5原10×7.5×10nm三维缺口、384hex/p3、h1.25nm、31968复FE、40端口、原A/f和Si/air、掠角1°/phi0/s、完整内部、双Floquet/DtN。体/DtN q15，网络q30/独立q60。材料表hash=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`、native hash=`2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215`。

### 4.2 运行规则

| 路线 | 更新方式 | 唯一区别与共同条件 |
|---|---|---|
| DETERMINISTIC_COMPLEX_WAVE_BACKFIT | q/k0与eta上的无梯度固定模式搜索 | 同物理衰减种子、同1377槽、同起点、全部幅值重求 |
| LEARNED_COMPLEX_WAVE_BACKFIT | 实q/eta梯度的有界L-BFGS-B | 真正学习振荡及衰减，不强制改动 |

两者都在参数化神经波函数中调参，这是梯度与强无梯度搜索的对照，不是纯“有/无NN”消融。旧V33实波矢结果为历史控制，不重新跑第三条长训练；新旧整体改善与梯度学习增量分开归属。

seed4213401。每轮16个不同块：按六分量归一化梯度RMS选8个，按global/粗/中/细及block id轮转8个，去重补齐；两边都计公共预选费用。只修改现有块，不增加波数/窗口/列容量。每次访问最多48次完整评价，含种子评价、失败试探及最终独立值；零变化核验和接受原A审核另列且同样计费。无梯度步长按每轮1/8、1/16、1/32、1/64循环，坐标顺序固定轮转；学习maxiter20、maxls12、maxcor10、ftol1e-12、gtol1e-10，显式实际调用守卫，不多算result.x。

各新增至多4h、64次块访问、3072完整评价，先到者为准；初始化/QR/保存/恢复/标量审核包含在路线时钟。活动补空间一访问只准备一次。接受条件是完整原残差不增（加原1e-10舍入容忍）、约化/原作用与模型重建通过；改变目标、看参考误差挑点或人为扰动均禁止。

32访问或120min先到的完整边界审核。若原native/augmented均未比共同起点减半且散射E/H均≥1%，再给8次访问或30min先到的一次确认；仍成立记录COMPLEX_WAVE_NO_USEFUL_PROGRESS，结束该候选并完成另一条及终验。不在第一次软件失败停止整包，也不因为有剩余时间无限复活数值负结果。该标量门只是投入控制，不是数学不可能性证明。

原残差到1e-8立即做联合验收；方程过门但场未过，最多按原r继续至1e-10，不回传参考误差向量。每个接受块持久化q/kappa/T/全部幅值/QR/c/r/RNG/source/预算，trial独立；checkpoint不混用旧全0衰减缓存。冻结点按固定时间/访问节点，不按参考挑best。

## 5. E：完整验收与这次必须作出的决定

| Gate | 完整要求，不放宽 |
|---|---|
| 原方程 | native、未凝聚增广、独立total各≤1e-6，固定原RHS分母 |
| 场与通道 | 同p3参考的total/scattered E/H/scaled-curl、六点复场、全部40复通道各≤1e-4 |
| 功率 | R/T/A/A_volume误差及独立体吸收能量闭合≤1e-5；逐级功率≤1e-6 |
| 参数与恢复 | 实际含kappa点值→完整矩、MPC和端口恢复≤1e-10；producer另行评分 |
| 求积 | 网络矩及其原A作用q30/q60、FE场积分q15/q30变化各≤1e-8 |
| 标签 | training_reference=false，validation_reference=true；不回传向量，标量参与及benchmark_previously_seen=true |

只有这些联合通过才有M5数值资格；不合格功率仍diagnostic。参考、四类通道、所有分母和近零规则沿V33独立checker，不以新名称改变评分。增加complex参数后必须由独立点值路径核验，不能只重读producer的pass字段。

本轮研究正信号至少要求学习native/augmented≤1.574317670499e-2，散射E/H均≤1e-3；同时报告相对新控制是否改善。这不是正式Gate。仅小幅残差改善、较少评价或低采样峰不算突破。如果联合Gate未过且此信号也未到，明确关闭这份复波矢配置及当前全局稠密波库的同类续扫，不建议再做一轮优化器/半径/seed延长。

每条完整归属含10186.178641493432s前缀、新实现所需数值setup、训练、失败修复、保存和全部必要审核。项目历史不重复收费；loaded-packet成本与冷N=1不同，未知仍为UNKNOWN。历史传统672.462895s/1245822976B只作旧基线，不伪造新公平速度比。即使M5数值通过，当前前缀已不支持本小案冷成本竞争力；不能授NN20。只有与最佳合格非神经方法在同精度完整成本上时间或峰值改善≥20%，才可能另授资源收益。

列数固定不消除目标尺度的32Nm字节U/Q存储。N=1e7、m=1377仅两列库为4.4064e11B，是形状推导而非目标N或RSS；原算子、R、临时、端口与系统余量另计。复波矢若不能显著减少所需列数/求解工作，不能凭新增参数很少宣称解决2TB/48h。不得在本支另开存储重构来救一份尚未求准的方案。

## 6. D：仅真正通过后推进0.7nm缩小三维

学习路线通过M5联合Gate、资源安全且本批剩余≥7200s（含验收），才自动准入原M5全部长度×0.14的真实非可分缺口。使用统一0.7nm材料，重建该小case必需算子/矩/全部实际模式及一次既有独立参考；不开展全口面或新传统引擎，不硬套40/32060模式。

允许无标签原神经函数按中心/半径×0.14、q/kappa÷0.14转移，必须重新计算当前材料下完整矩和幅值。这只是初值：材料变化导致旧衰减不再是新解，须真实训练/验收，前缀全计。也保留当前材料解析衰减种子供同规则选择，不从参考场调参。

主场输出仍为Nédélec插值场，原函数校准、同离散资格、p/h/端口资格分列。p3精度不足不能靠网络原函数准确掩盖。条件未到写NOT_RUN，不运行最大0.7nm目标，不以一个平面波代替三维pilot。

## 7. 自主修复、资源和执行顺序

新连续57600s从首项实际准备起计；A/B软3h，C各硬4h，E软2h，条件D软3h，最终至少预留1800s完整保存/交付。软分配可调，C公平上限不单边延长，旧窗/旧费用不复活或清零。目的为连续完成A/B→C两路线→E→条件D，不在测试、commit或普通bug处等待新review。

schema、虚部丢失、符号/共轭、QR、dtype、序列化、状态、导出和接线问题同批按failure→hypothesis→最小修改→targeted test→健康边界恢复。没有普通bug次数交棒卡；不full pytest、不重装环境、不重新训练健康前缀、不因网页/归档失败重求参考。无法恢复的科学数据、ABI/权限与安全条件才停止受影响链，并完成独立可做部分。

CPU-only/MPI1/math和Torch线程1、当前合格物理核；数值warn12/hard16GiB，含临时规划≤12GiB，轻树2GiB，ownswap/OOC=0。保留系统max(128GiB,10%有效总内存)+384GiB邻增长+本任务预算，原PSI60s/CPU-SMT/cpuset规则不改。成功准入计总墙钟，不套旧1200s观察池；拒绝后额外前台等待/重采样≤1800s，无后台抢跑。数值QR/矩角色正确登记，不能误设轻树2GiB。

durable launcher/watchdog全链保留，计时含导入/setup，150s前收口，至少120s保存。断连先核对旧进程；仍在运行则附着，不另启动；确实退出从完整checkpoint恢复且继承费用。不得操作邻项目、全局库、affinity、锁或watchdog。

## 8. 输入、提交与一次性交付

先核对无活跃本任务run、branch/HEAD/worktree/锁，再命令级精确fetch并ff-only同分支。完整读取根/目录规则、仓库原则、原task、Review V32、Response V33及本报告。不新clone/分支，不reset/stash覆盖不明工作，不amend/强推/merge。数学核明确opt-in，先clean实现commit再正式运行，source与后续文档HEAD分开。

新stage必须先实现并validate；下列名称是本轮待实现接口，不是假称当前已可运行：

```text
input/task042extra_feinn_5nm/v34_complex_wave_checks.dat
input/task042extra_feinn_5nm/v34_complex_wave_calibration.dat
input/task042extra_feinn_5nm/v34_deterministic_complex_backfit.dat
input/task042extra_feinn_5nm/v34_learned_complex_backfit.dat
input/task042extra_feinn_5nm/v34_complex_reconstruct.dat
input/task042extra_feinn_5nm/v34_complex_compare.dat
input/task042extra_feinn_5nm/v34_0p7_complex_prepare.dat  # 条件D
input/task042extra_feinn_5nm/v34_0p7_complex_solve.dat    # 条件D
input/task042extra_feinn_5nm/v34_0p7_complex_compare.dat  # 条件D
```

使用现有`python scripts/launch_task42extra_durable.py <one-run.dat>`选择正确FE/ML环境，再调用`scripts/run_case.py`。每dat一次明确计算，阶段串行并先清场，不把新输入塞进旧白名单或旧窗。

交`response_v34.md`、`outcomes/complex_wave_neural_v34.md`及compact的design/anchor/衰减推导/完整矩与梯度/逐次替换/Gate/cost/resource/repair/run/provenance证据。每次run保留input_original、resolved_config、run_manifest、input/physical/source hash、run_summary和artifact hash。完整数组留ignored，compact CSV保留分子/分母/实际值；不要多份万行JSON复制相同数组。同步本分支README/summary页首、progress、模型总账、tests、changed_files，历史不改。

最终必须回答：是否真实学习了非零衰减而非仅改复幅值；该新函数族是否改善同容量精度；梯度相比强控制有没有收益；M5联合Gate与冷成本分别是否通过；0.7nm缩小case究竟是否执行。失败明确关闭哪份配置，不用“有待进一步研究”代替资源决策，也不宣称数学上所有NN无解。

发布端只作材料传播量和小复数导数/变量投影检查，不是M5实测。完整HTML获取受限、浏览器视觉未确认的部分如实NOT_VERIFIED；Codex有限补查新关键页，网页问题不阻断数值。只推`git push origin HEAD:refs/heads/task42extra_feinn_5nm`；完整包或明确科学/硬出口后一次交付准确HEAD/tracking/ahead-behind、clean及自身清场，等待review。
