# Review V1：Task042 V3 审阅与有界全局误差空间／两层修正

## 0. 审阅决定、身份和本轮执行范围

**接受 V1–V3 已提交资料作为有限研究与负结果档案；现有粗逆仍不合格，不批准 production 或合并。授权下一批在固定几何局部 PC 上检验有界全局误差空间和两层修正，不要求局部 PC 先收敛。暂不训练新神经网络，不运行 p6 外层。**

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-09-29
reviewed_HEAD              = 4503d9dd7bdcd68f2634e31baa5b312eb23fda4f
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
latest_response_reviewed   = response_v3.md
previous_formal_review     = none
V3_reuse_source            = b158c5301e7ff59000b15b335672afdb61c5e5e1
V3_geometry_source         = 7fc3f1434cf4f38f43e5244ebfed3a19d0780a26
research_record_review     = ACCEPTED_WITH_LIMITATIONS
existing_solver_gate       = NOT_QUALIFIED
new_execution_batch        = V4_GLOBAL_ERROR_TWO_LEVEL
response_required          = response_v4.md
new_NN_training            = NOT_AUTHORIZED_IN_THIS_BATCH
F5_p6_outer                = NOT_AUTHORIZED_IN_THIS_BATCH
master_merge               = NOT_APPROVED
```

本任务服务的最终目标仍为约 2 TB 整机物理内存内、真空波长 0.7 nm、周期单胞任意非可分三维 Maxwell。**本批要减少的不确定性是：取消全局 p4 LU 后，局部修正留下的困难误差，能否由少量可跨 RHS 复用的全局方向有效处理。** 它是 neural-assisted coarse-space 路线的前置数值试验，不是新增 PINN、黑盒 R/T/A 代理或 0.7 nm 容量资格。

本次审阅核对了远程源码、任务合同、响应及已提交轻量 records；没有 SSH 重跑工作站 FE，也没有重新计算 ignored 大 artifact 的全部 hash。以下 measured 数字均指仓库实测记录，不是 ChatGPT 新测量。审阅不宣称穷尽所有实现错误，也不等于 full pytest/CI 全绿。

审阅时该任务目录没有旧 review 或独立补充 task；适用增量授权保存在 outcomes 的共享授权和 V3 预登记中。执行前仍须读取根／目录 AGENTS、仓库工作原则、task.md、本 review，以及本 review 之后出现的有效用户指令／正式 review；不因 README 或原 task 的历史 PLANNED/F0 字样回到初始执行顺序。

## 1. 覆盖关系：纠正停止前提，不改写历史

### 1.1 明确覆盖的要求

上一轮聊天指导和 [V3 预登记](outcomes/bounded_diagnostic_design_v3.md) 要求：几何局部 PC 若仍为量级 1 停滞，则不开展新的误差空间对照。Codex 按此前合同停止是正确执行；**本 review 纠正的是该研究设计前提，而不是把正确停止记为执行错误。**

局部方法不能处理的分量可能正是粗空间应该处理的分量。自本批开始，取消“局部 PC 必须先通过或摆脱停滞，才解锁全局空间试验”的条件；直接允许 §5 的训练误差捕获和两层组合。V3 的失败与停止记录逐字保留，不追溯更名为成功。

以下仅本批覆盖：原先新空间 not_run 的停止流；每步完整 native 审核频率；新增训练轨迹的 64 步捕获上限。**候选验证的 RIGHT FGMRES32/max256、原 A4/port/recovery 的 1e-10 门限、物理模型、原矩阵和资源上限不放宽。** 64 步只是离线生成误差快照的预算，不是降低正式返回精度。

### 1.2 继续有效的用户共享授权

[shared_authorization_v2.md](outcomes/shared_authorization_v2.md) 和 V3 现场准入中的 Task042 受控共享 CPU 授权继续有效，不因其他 heavy 存在自动等待全机空闲，也不重新要求独占全机 heavy lock。仅持 Task042 自有 nonblocking lock，一次一个 Task042 数值阶段；不碰邻任务及其锁、HEAD、环境、优先级、亲和性、watchdog 和输出。

保持 MPI1／数学线程1、现场选空闲物理核心、Task042 自身 nice10/idle I/O；整树 RSS hard16 GiB/warn12 GiB、自身 swap0、禁止 OOC、原系统 reserve 加邻增长规划128 GiB、磁盘自由至少50 GiB、artifact总量上限20 GiB。无 cgroup 委派时继续如实声明0.5 s采样阈值停止，不冒充连续内核硬限额。现场压力、监督失效或自身资源触线只停止本任务后代。

本批 CPU-only，不安装／切换 CUDA，不争用已有 GPU。FE/ML/源码导入和所有可写缓存继续隔离在 NN-Lab；只读复用合格 ABI 前缀。CPU 编号每次实测，不永久绑定历史0/12/33/45。所有运行时间与内存均标 shared-workstation；不承诺绝对零干扰或无争用加速。

## 2. 已证实结果、审阅发现与边界

依据：[Response V2](response_v2.md)、[Response V3](response_v3.md)、[最新 summary](outcomes/summary.md)、[V3 原字段 Gate](outcomes/records/gate_decisions_v3.json)、[残差诊断](outcomes/residual_diagnosis_v3.md)、[结构记录](outcomes/records/structure_complete_v3.json)。

| 对象／数据身份 | 实测或审阅判断 | 本次决定 |
|---|---|---|
| F1 原 FE/传递与 V2 teacher | 所测原 A4/PH A6P、凝聚及非零内部/port 接口一致；384对 teacher 有原方程审核 | 复用合格身份，不因文档变化重做整批 |
| V2 三候选 | 各15个非零 RHS 均失败，仅零通过；NN 没有额外正信号 | 不提升，不再扩大同Q系数MLP |
| V3 原残差映射 | 新native配对最大约3.18e-14；独立Schur约1.04e-14；所测reported与显式结果一致 | 未发现解释当前停滞的残差映射错误；非穷尽证明 |
| V3 几何PC | 252个单元trace＋完整80port重叠主子块，max272行；全因子302047392 B | 固定为本批局部B；不再扫描块、重叠或shift |
| V3 候选结构 | 未构建global p4 LU、无hidden fallback/private audit CSR；仍存储原p4稀疏矩阵 | 无global factor不等于全路径matrix-free或成功低内存求解 |
| 新全局误差空间 | 未运行 | 不得从一层失败推断两层组合已经失败 |
| 正式场／泛化 | F5、R/T/A/A_volume、完整E/H/衍射终态比较及短波未运行 | 不作production、任意3D或0.7 nm通过声明 |

| 已消费诊断RHS | V3 原A4相对残差 | 固定原Schur RHS相对残差 | 最后32步Schur降幅 | 严格门限／判断 |
|---|---:|---:|---:|---|
| physical_PH_b6 | 0.891957825531 | 0.909624475501 | 5.70298292157e-6 | 原A4/port/recovery 1e-10；FAIL |
| port-only | 0.935861877336 | 0.948989903082 | 1.23982140442e-5 | 同上；FAIL |
| mixed | 0.932010701839 | 0.974243567085 | 1.24422653291e-7 | 同上；FAIL |

三项是 consumed diagnostic，不是 fresh test。几何结构仅有局部改善信号，尚无证据将剩余误差命名为某个特定低频、共振或传播模态。局部 PC probe 对不同路线各自的末端残差，不是同一向量的交叉消融，不能给出因果性能结论。

### 2.1 端口尺度必须继续分账

物理RHS的旧B0端口绝对残差约0.0353871，新GEO约0.187211；新operation分母约24.2159，因此相对closure虽降至0.007731，不能称端口绝对误差改善。保留原operation-relative门限，同时增加绝对值与固定参考尺度，避免变化分母带来的误读。不要为获得好看的曲线修改方程、范数定义或训练loss权重。

### 2.2 审核成本应降频，不应取消

三个V3 RHS的 solve-and-audit 区间相加为2386.621095 s，observation相加2077.924221 s，占87.0655%（derived，分母为这三个区间，不是全工作流）。原始字段见结构记录。其密集审核回答了残差映射问题；本批按 §6 减少频率。节省这部分监测不等于改善数学收敛，也不直接推算新速度。

### 2.3 已纠正事项不重复制造阻塞

V2“全部CPU0”的概括已由V3逐run证据纠正：oracle33、F4-B0为45，V3-reuse12／overlap0；沿真实manifest/affinity记录，不回写raw。已有全仓文档枚举／旧registry错误保留为 inherited，不用无关全仓清理阻止本批；本批相关数值、接口和资源测试必须通过。

## 3. 冻结物理、算子和局部预条件器

| 身份 | 固定值／来源 |
|---|---|
| 物理 | original Si矩形块，13.5 nm，grazing1度、azimuth0、s、幅值1 |
| 几何 | 周期50×25 nm，z=-10..130 nm；光栅17×25×120 nm；与原task一致 |
| 材料 | air n=1；Si n=0.999002304859+0.00182649365i；mu_r=1；epsilon=n*n |
| FE/端口 | p6/h10对应的同网格p4，252cells；p4 FE storage53084；quad15；双Floquet；完整80 Fourier-DtN |
| 本批求解系统 | 独立p4凝聚trace＋port系统 S，n=21824，stored NNZ=8184464；不是p6外层 |
| S 的CSR SHA | 150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560 |
| physical SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| ordered mode SHA | d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb |
| 局部B | 原 R-GEO-CELL80-v3；支撑、限制／平均延拓、完整port、局部主子块与因子均不改 |
| 验证KSP | RIGHT FGMRES，restart32，max256，zero start，unpreconditioned norm，原rtol1e-12/atol0 |

S指含端口行的凝聚增广矩阵；A4指恢复后的原物理算子。二者残差不能混称，p4空间不能通过对p6凝聚矩阵作未经证明的trace投影得到。本批只在p4内层改变PC，保持原A4=PH A6P、原H6、原BAL_H和最终验证流程不变。不得将Hp与Hhat互换，不减少通道，不重复施加已进入MPC装配的Floquet相位。

参考源码：[几何PC](../../src/solvers/learned_geometry_overlap.py)、[内层backend](../../src/solvers/learned_coarse_inverse.py)、[原p4构建](../../src/solvers/learned_coarse_runtime.py)、[旧低维修正](../../src/solvers/learned_reduced_correction.py)、[V3诊断](../../src/runners/task042_diagnostics.py)。

## 4. 新算法合同：完整Schur范数中的平衡两层修正

### 4.1 先解释它改变哪一步

局部B分别处理许多小区域，但不能自动协调所有区域的困难误差。新全局空间Z提供少量跨域修正方向，先消除其能表示的残差，再做局部修正，并消除局部步骤重新引入的该空间分量。代价是保存两个n×r数组及小三角矩阵、每PC一次额外S作用和若干基乘；收益只能由试验决定。它不是新的物理解，也不是增加一个全局大LU。

旧R-LIN在旧Q和native残差范数中已经计算精确最优系数；同Q、同目标的MLP不能比该最优系数更准。本批改为**完整Schur残差范数和显式两层组合**。旧native编码U/R不复用，只读取已验证的旧Q作为候选Z之一，重新构造SZ。因此新OLD-POD路线不同于旧R-LIN，不能混淆归因。

### 4.2 数学定义与矩阵作用

Z的每列都是独立canonical trace＋port的解方向，Z行数必须等于n。令SZ列满秩，薄QR为：

```math
SZ=UR,\qquad U^HU=I,\qquad C_Z=ZR^{-1}U^H.
```

这里R的逆仅表示三角求解，不显式形成逆矩阵；所有共轭转置必须正确。粗修正解决固定Z上的完整Schur最小残差问题，不是SPD能量投影，不是把Z当作原p6/p4传递P。

```math
B_2=C_Z+(I-C_ZS)B(I-SC_Z).
```

作用顺序固定为：

```math
\begin{aligned}
a&=U^Hr, & z_c&=Z\,\mathrm{solve}(R,a),\\
r_{\perp}&=r-Ua, & y&=Br_{\perp},\\
w&=Sy, & z&=z_c+y-Z\,\mathrm{solve}(R,U^Hw).
\end{aligned}
```

利用SCZ=UUH，不再为了算r_perp额外调用S。每个B2调用的数学工作为两次C、一次B、一次S；实现须报告实际counter，临时对象预分配并避免重复持有转置／conjugate副本。S只是借用的真实作用，不能形成n×n密集投影、显式B2或法方程。

列满秩且精确运算时，有：

```math
C_ZSZ=Z,\qquad SC_Z=UU^H,\qquad B_2SZ=Z,\qquad U^H(r-SB_2r)=0.
```

这些可检验的恒等式说明粗空间被正确处理，**不保证补空间收敛，不保证B2可逆／波长鲁棒，也不意味着所有真实误差都在Z内**。不凭恒等式通过就跳过真实KSP或原A4验算。失败时分别判断空间、SZ病态、局部B、两层接线和全局收敛；不得声称理论保证成功。

### 4.3 秩和数值稳定性

最大rank仍为128，但128不是必须填满的配额。误差快照用复数薄SVD/稳定QR，默认相对奇异值阈值1e-10；零快照排除。不得随机补方向或复制快照凑rank，不通过反复调阈值寻找成功。

SZ使用rank-revealing QR或薄SVD审计，小R的奇异值／条件数与实际effective rank全部记录。允许按同一固定1e-10相对阈值做一次确定性的依赖方向剔除／旋转，然后重建Z/U/R；不加正则、shift或隐藏伪逆。若没有有效方向或恒等式／实际三角解精度不达标，该路线记COARSE_SPACE_NUMERICAL_BLOCKED，不以降低检查标准放行。

旧Q优先截取到新误差基的有效rank再作相同SZ审计，形成同rank对照；如审计后effective rank不同，明确报告实际rank、存储和 unmatched-rank 限定，不宣称纯粹同容量优劣，也不追加扫rank。新空间失败不得阻止已有旧Q两层路线完成其有限诊断。

## 5. 执行顺序与样本隔离

### P0：身份复核、有限计划与纯代数检查

只做必要的branch/HEAD/worktree/ABI/资源复核，不重复F0环境安装、旧teacher384对或V3三条长诊断。读取本review后把实际执行批次、候选名、数据清单和Gate写入一个参数化配置；新增功能research opt-in，数值核心放src/solvers，runner只编排。

先在小型复数非Hermitian矩阵上验证 §4 四项恒等式、线性与复相位／幅值缩放、零RHS、输入不变、rank-deficient拒绝、作用次数及ownership。再在同一真实S上做少量方向配对；使用独立原作用作为见证，不能mock替代真实S。纯数组和真实action接口通过后自动P1，不等局部B收敛。

### P1：最多16个训练问题，捕获真正的迭代误差

优先从 [V2 teacher manifest](outcomes/records/dataset_model_manifest_v2.json) 的**原train**选择16个互不重复whole_problem：按已存标签顺序取前8个 seeded_full_internal_port 和前8个 manufactured_original_A4，均须来自原train而非validation/heldout；若类别不足，仅按原train确定顺序补齐并在运行前登记，不依据新求解结果选样。至少报告真正独立family数，不把相位／幅值亲属算独立问题。数据抽取每批不超过32对。

不得读取已消费physical/port-only/mixed终测的teacher解来构造Z；这些只可在P3作诊断。不得把未知测试误差放入Z再测试同一RHS，或把已看过的16项重新标fresh。

逐个核验选定teacher的source、operator/physical/mode、归一化和原残差。优先复用hash-bound的准确reduced解；若指定训练reference确实缺失，仅允许一个离线teacher进程补这些已登记训练RHS、至多16对，不重建整个数据集。按原symbolic/resource Gate建小模型参考LU，严格检查，销毁并退出清场后才启动候选轨迹；不能在B2在线查询teacher或持有全局factor。

对每个训练RHS从reduced零初值用冻结B做最多64步FGMRES，保存m=8,16,24,32,40,48,56,64的reduced状态。出现正常提前收敛就结束该轨迹，少得快照如实记录；不强行添加零误差。每个误差方向定义为：

```math
e_j^{(m)}=x_j^{\ast}-x_j^{(m)}.
```

x_star和x_m必须在同一n维canonical trace＋port坐标及同一归一化中；不能用53084维full-field替代21824维reduced向量，不能混用raw RHS和normalized teacher。误差e不是残差r。保存二者的关系S e = r及相应teacher残差项，作为数据自检。

每个非零误差先按其2范数规范化，再按该family实际有效快照数的平方根做权重，避免一个家族因快照多支配POD。最多16×8=128列；相位约定／权重／遗漏原因入manifest。这个有界n×128快照矩阵允许物化用于稳定薄SVD（约42.63 MiB载荷），不等于允许把全部384对full teacher场加载进RAM。原始快照和尺度保留本地ignored。

**B在64步内停滞仍是有效误差采样，不是P1停止条件。** 非有限值、真实接口不一致或资源触线才停止。不要把“原局部解未过1e-10”误判为禁止构造其误差基。

### P2：冻结两个基，验证空间与组合

| 路线名 | 使用空间／局部部分 | 用途 |
|---|---|---|
| GEO-BASE-V4 | 冻结V3的B，不加空间 | 历史平台；已有同RHS记录优先复用，三项最多一次同监测策略短对照 |
| TWOLEVEL-OLDPOD-V4 | 旧V2 Q，经新的完整Schur QR；相同B | 旧空间在新目标／两层组合中的效果 |
| TWOLEVEL-ERROR-V4 | P1新误差基，经相同Schur QR；相同B | 针对停滞误差的空间是否更有效 |

旧Q身份以 [数据与模型账](outcomes/dataset_and_model_provenance.md) 的hash为准，旧U/R和神经weights不得带入新PC。旧基用256训练对、新基最多16条训练轨迹，两者训练信息与离线工作量不同，必须显式报告；差异不能全归因于组合公式或“学习能力”。空间冻结后不得再根据P3/终测更新。

本批只这两个两层候选，不增加NN、ORAS/shift、局部patch设计或其他recycling算法。少量same-Z最小二乘和in-subspace自检属于算法检查，不记作泛化成功。

对各候选保存Z、SZ的正交性／秩／条件数、QR重建差、C S Z、B2 S Z和U^H剩余残差的operation-scaled缺陷，目标<=1e-10；纯数组再与显式最小二乘／显式B2配对。真实S必须使用未改变的operator SHA。只做小矩阵／小数目随机方向与空间内方向，不生成global dense矩阵。

### P3：先测3个已消费RHS，再决定是否解锁新终测

对两个数值合格的两层候选，各自在原physical index0、port-only10、mixed11从零运行一次RIGHT32/max256。最多6个诊断solve，所有结果保留，不增迭代／rank／shift重试。局部B的V3平台可作数值对照，但其逐步审核频率和硬件条件不同，不作新时间分母。

明确分流：

| 判断 | 固定判据 | 后续 |
|---|---|---|
| STRICT_DIAGNOSTIC_PASS | 三项原A4/port/recovery均<=1e-10，原约束／identity通过 | 可进入P4，但仍不是fresh资格 |
| GLOBAL_SPACE_DIAGNOSTIC_POSITIVE | 非严格通过，但physical和mixed各自的原A4相对残差、固定原Schur RHS相对残差均<=0.1；全部finite、独立identity通过 | 可进入P4探明独立范围，不改正式1e-10门限 |
| BOUNDED_TWOLEVEL_NEGATIVE | 两条候选均不满足上述任一条件 | 保存对照，结束本批；不扩大网络或无界空间 |
| COARSE_SPACE_NUMERICAL_BLOCKED | 秩／identity／构建失败 | 区别于收敛负结果；其余独立合格路线仍可完成 |

0.1是预先冻结的研究分流阈值，不是物理精度目标、理论收敛界或可用于生产的容差。新两层没有通过这些阈值时，结论只限本模型、两个基和当前B；不能否定所有粗空间、所有神经方法。

P4只选择一条路线：先比较三项strict通过数（多者优先），再比较三项最终原A4相对残差的最大值（小者优先），再比较固定Schur相对残差最大值；完全同值则OLDPOD优先。不要用共享负载下的最快时间挑选。选择只基于consumed诊断，选择记录和最终checkpoint在读取新终测数值前冻结。

### P4：条件解锁的16项未用终测，不自动进入F5

使用 [既存未用计划](outcomes/records/unconsumed_test_plan_v3.json)：seed420620，一个零项＋5个完整问题家族，各3个幅值／相位变体，共16项。先核查这批数组／结果从未用于训练、空间选择、阈值或候选选择；验证完候选冻结后才生成。它是5个非零独立family及变体，不是15个独立物理问题。若已被其他后续工作消费，报告TEST_POOL_CONSUMED，不悄悄换种子或继续叫fresh。

只用冻结的选中候选，每项一次RIGHT32/max256。验证进程只加载RHS、冻结PC／空间和原S；不加载对应teacher解，不改变初值，不在线学习。每项输出完整原A4、port、recovery、slave/identity和固定Schur真残差，strict标准不变。任何非零项失败，整组不取得STRICT_P4_RETURN_QUALIFIED；可保留局部正信号。终测一经读取即consumed，不能用它重训后继续称同轮独立终测。

全部通过也只称FIXED_OPERATOR_P4_QUALIFIED，尚无p6外层、非可分几何、网格收敛或0.7 nm资格。本批到此交付review；F5/p6/RTA仍不授权，避免再把粗层组件通过直接外推为完整物理解。

## 6. 监测、精度和失败处理

每步保留廉价KSP标量历史。完整显式Schur、原native A4、端口、内部恢复、约束及恒等式检查放在0、每32步、最终和异常点；P1误差捕获的8步采样只保存必要状态，不要求每次作完整native审核。每次试图向外返回一个合格粗解之前必须完整严审，不能因为降频省掉最终witness。

保留以下相互独立的量：绝对reported／显式Schur范数；除固定原Schur RHS范数的相对值；原native有效RHS相对值；port绝对范数和原operation-relative；recovery及native/Schur映射缺陷。固定端口参考尺度可取同一RHS reduced零初值按原particular recovery得到的初始port操作尺度，并对近零采用沿用的绝对规则；尺度需记录，不能将零分母硬改为有利常数或替代原门限。

每条候选独立记录setup、快照／SVD／QR、B2总apply、C/B/S各自calls/time、Krylov、审核／恢复、I/O及释放。C/S计时可能嵌套，不能把子项与父项重复相加。V3高频审核计时只作历史，不直接相减预测加速。RSS、数组载荷、后端factor bytes和VRAM口径分开，时间共享负载不可比就标inconclusive。

同一个明确实现bug允许一次有记录的最小修复、targeted tests和仅受影响阶段重放；不同实现bug逐项登记，不给正常停滞贴bug标签。数据损坏、ABI／算子身份改变、非有限值、监督失效、own swap或资源触线停止受影响阶段并保留packet。不得借失败无限扫描、全局factor fallback或调整精度。

## 7. 内存预算与后续可扩展性边界

| 对象／口径 | 数值或约束 | 身份 |
|---|---:|---|
| 一份n×128 complex128数组 | 44,695,552 B，约42.63 MiB | derived，n=21824 |
| 在线Z＋U两份数组 | 89,391,104 B，约85.25 MiB | derived；不含R/工作向量 |
| R，128×128 complex128 | 262,144 B | derived；三角解，不显式逆 |
| 冻结几何及cell/port因子 | 302,047,392 B | V3 measured payload；须新构建核对 |
| 全部局部／bottom因子 | <=512 MiB | 包含R等小型求解数据，不能漏账 |
| 表示／索引／在线buffer与构建workspace | 各峰同时存活总量<=512 MiB | 新manifest按backing对象去重；不只数checkpoint |
| 全任务进程树 | warn12 GiB/hard16 GiB，own swap0 | 0.5s采样，保留系统余量 |

两个候选分进程顺序构建／运行，不让旧basis、新basis、teacher因子和全部Krylov栈长期重叠。需报告QR/SVD库的临时workspace及文件解压副本；用预分配和生命周期控制，不因模型小就忽略复制。可以保留小规模真实稀疏S用于本次研究，不形成global denseS/C/B2，不复制private audit CSR。

本批全局dense Z/U只被授权为当前小模型的可行性试验。其存储随n×r增长，不能宣称自动满足0.7 nm预算。后续若空间有效，应再研究局部／分布式表示或神经生成局部粗基；本批无权升级为大模型复制全局basis的生产架构。

## 8. 执行入口、提交和证据

所有新真实FE阶段经唯一入口 `python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`。每dat对应一项明确stage/operator/RHS inventory，不隐藏跨物理批处理。复用已有参数化runner和watchdog，新增数值核在src/solvers；只作必要的opt-in适配，不改旧默认，不整体merge别的research分支。

建议提交：C1本批配置／two-level纯代数核与测试；C2快照／基构建及原算子接口；C3有限诊断与条件终测；C4证据／response。每次正式运行前实现clean commit，记录真实source；报告HEAD不能替代运行SHA，不在活跃本任务run中为文档提交改变受检HEAD。只提交推送本分支，不amend/force/rebase/merge master，不改root AGENTS或旧task/review。

本批证据至少包括：

```text
response_v4.md
outcomes/two_level_global_error_v4.md
outcomes/records/two_level_design_v4.json
outcomes/records/training_snapshot_manifest_v4.json
outcomes/records/coarse_space_algebra_v4.json
outcomes/records/two_level_comparison_v4.csv
outcomes/records/fresh_qualification_v4.json
outcomes/records/gate_decisions_v4.json
outcomes/records/run_index_v4.json
outcomes/summary.md
outcomes/test_summary.md
```

未解锁的终测文件明确not_run及原因，不捏造结果。只新增v4原始索引，保留v1–v3负结果。大型state、basis、teacher、checkpoint、完整日志和矩阵在ignored目录；CSV/compact保存必要指标与hash，不在多个JSON重复嵌套完整大历史。同步本分支development_progress和model_registry的Task042段，不做无关文档重构。

每run保留input_original.dat、resolved_config、manifest、input/physical/source SHA、run_summary、ABI/MPI/线程/affinity、resource口径和artifact hashes；增加training family、snapshot权重/尺度、有效rank、Z/U/R、QR/剔除规则、选择决定和test-consumption身份。推送后核对branch/HEAD/upstream/worktree/clean/ahead-behind；只使用精确Task042 refspec。

无需等每个小步骤再批准。满足本review的前置Gate就推进到下一个已授权阶段；真的资源／数值失败按上述分流收口，不恢复“有其他heavy就只做F0”。不建立后台无限等待或自动更大规模试验。

## 9. Response V4 必须首先回答的问题

| 必答项 | 不能替代它的内容 |
|---|---|
| 两个空间各是什么、实际rank、是否来自未泄漏的训练误差 | 仅写POD128或模型文件存在 |
| 两层恒等式／S作用／MPC和port是否真实通过 | 仅mock或scalar标签 |
| 三诊断是否突破平台，哪条被选、独立终测是否全部通过 | 训练集in-subspace自检或只报一个relative port |
| 是否仍无global p4 factor，完整空间/因子/进程树峰如何 | 仅checkpoint大小或derived bytes |
| 离线成本、在线成本、审核成本分别是多少 | 只报outer次数或把V3 observation相减当新实测 |
| 能否继续神经辅助空间路线／需要解决哪个残余blocker | 无证据声称神经已成功或所有神经不可行 |

正式结论同时保留research evidence、numerical qualification、resource与performance四种身份。没有新网络训练，G-neural写not_run，不把非神经空间收益归给NN。即便获得固定p4资格，也先停止等待review，不进入p6或短波，不merge。

## 10. 方法依据与适用限制

本批公式由 §4 的QR关系直接定义和验证。可参考 [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/) 的右预条件与可变PC说明，以及 [PETSc PCDEFLATION](https://petsc.org/release/manualpages/PC/PCDEFLATION/) 对投影／粗修正组织的说明（访问日2026-09-29）。后者的默认Galerkin公式不是本review的Schur最小残差C_Z，不能只打开该选项就宣称实现等价；其默认粗底层还可能调用LU，必须核查实际构造。

这些在线文档是方法背景，不授权升级工作站PETSc3.19.6或ABI。不存在关于本Maxwell模型、当前空间或0.7 nm的外部通过证明；成功只能来自本分支原方程、独立数据及全过程资源证据。

**本批的终点不是“训练完成”，而是对以下问题给出可复现答案：在不保留全局p4因子的情况下，有界且可跨RHS复用的全局误差空间，是否让当前局部方法真正开始有效求解。**
