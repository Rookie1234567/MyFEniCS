# Review V3：关闭当前 p4 近似逆路线，转向单次神经有限元求解

## 0. 审阅决定与身份

**接受 V5 为有限失效定位档案，关闭当前“小局部块＋固定低秩空间／系数网络替代全局 p4 LU”的持续优化路线。不执行所建议的 port-only augmentation。Task042 本身继续，最终目标明确为：在现有约 2 TB 工作站资源内，端到端不超过 48 小时，得到一个新的、0.7 nm、真正非可分三维周期单胞的合格有限元解。**

本 review 授权下一批有限的 **神经参数化目标有限元场** 试验：从本次原方程训练 trace 系数，不依赖强 p4 逆、不使用目标准确解训练。它是新候选的可行性检验，不是已经实现的加速，不授权直接启动最大目标模型。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-09-29
reviewed_HEAD             = 0caf151a8274f87363d7dc804d89070f7ba9eb7d
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review           = review_report_v2.md @ 91c4a0dbfa2e8a14df273eab5e27726059d7c835
latest_response_reviewed  = response_v5.md
V5_numerical_source       = 5d82651af0f723c73487783deb43969f05d46ed3
V5_record_review          = ACCEPTED_WITH_LIMITATIONS
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
Task042                   = ACTIVE_SCOPE_REORIENTED
next_batch                = V6_NEURAL_FE_SINGLE_SOLVE_PILOT
response_required         = response_v6.md
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

本批要消除的不确定性是：**绕开已失败的 p4 近似逆链，网络能否直接产生满足原有限元方程的目标场，并提供值得向 0.7 nm 目标规模扩展的收敛／成本证据。** 不是参数扫描或反演代理，不依赖大量高保真样本摊销，不以网络训练完成代替解的资格。

审阅依据是远程任务、review、response、轻量 records 和相关源码。ChatGPT 未 SSH 重跑工作站、未逐个重算 ignored 大数组 hash；以下 measured 指仓库记录。本次没有取得新的 FE 计算或性能测量。

## 1. 证据与明确收口

依据：[Response V5](response_v5.md)、[V5 详细诊断](outcomes/failure_localization_v5.md)、[覆盖原始值](outcomes/records/coverage_v5.csv)、[同向量审核](outcomes/records/same_residual_actions_v5.csv)、[独立检查](outcomes/records/independent_checks_v5.json)、[最新 summary](outcomes/summary.md)。

| 已核对证据／口径 | 实际结果 | 本次解释 |
|---|---|---|
| V5 共同状态 | 12/12，两个 RHS whole families 的零／历史终态；192 项修正审核 | 不是192次独立完整求解；诊断完成不等于 solver pass |
| physical 初态剩余残差比例 eta_r | OLDPOD 0.9990665004；ERROR 0.9997844639 | 当前 SZ 像对这个物理残差的直接覆盖极少，不是消除了99.9% |
| physical 保留 Z 与 Br 的最优 Schur 小LS | 0.9982538270／0.9994714049 | 即使不依靠网络预测系数，单次最优组合仍几乎不减残差；非所有多步方法的下界 |
| port-only 最优组合 | OLDPOD B2opt 0.9926200741，ZB-LS 0.6171863522；后者原A4仍0.9554190180 | 有固定组合利用不佳的局部证据，但不足以支持目标主线继续 |
| 补空间探针 | 每空间rank16；完整TV最小奇异值4.771224799／3.034800156 | 未得到真实near-null见证；不是全局谱，不能宣称B2奇异 |
| V4 完整迭代 | 两空间各3项，全部256步未通过；physical原A4约0.998588／0.999864 | 不是只差严格容差最后几位 |
| V5 新资源 | wall1144.401529 s；整树采样峰1135407104 B；own swap0 | shared-workstation，有界诊断成本，不是合格解成本或2TB容量极限 |

关闭的是这套具体研究实现和继续增量调优的投入，不是证明所有低内存 Maxwell 方法不可能。保留通用 Full3D 的 matrix-free、分布式数据与可扩展求解长期方向。已证实的原算子、MPC、凝聚、恢复、端口和审核接口继续复用；不再以增加rank、epoch、patch、shift、recycling或port-only试验自动延续旧路线。

## 2. 权威、覆盖与共享资源

先读根／目录 AGENTS、[仓库原则](../repository_work_principles.md)、[原任务](task.md)、[Review V1](review_report_v1.md)、[Review V2](review_report_v2.md)、最新 response/outcomes 和本 review。原 task/review/response、V1–V5原始结果不回写。

用户已明确 Task042 的最终目标并要求本次新 review，故本批在**同一 Task042 分支**正式调整范围；不新建分支、不改根治理规则。本 review 覆盖原 task 的“仅p4粗逆”、Review V2 的“不得新NN／新方程求解／短波pilot”对本批的限制；只授权下面 N0–N4。旧 p4 返回1e-10 Gate与失败分类保留，新目标场判据见 §7，不能把新对象的判据回填旧结果。旧 seed420620 终测池封存，不消费来调新网络。

用户受控共享 CPU 授权继续：存在别的heavy不是自动阻塞，不要求独占全机锁；Task042 自有 nonblocking lock、内部一次一个阶段。现场选空闲物理核心并避开忙碌SMT同胞，MPI1、全部数学线程1，自身nice10／idle I/O；不碰邻任务、锁、环境、HEAD、亲和性、优先级或watchdog。

本次小pilot仍采用整树RSS hard16 GiB/warn12 GiB、own swap0、无OOC、磁盘自由至少50 GiB、Task042 artifacts总量不超过20 GiB。保留 max(128 GiB, effective_total的10%)系统余量、邻增长规划128 GiB和本批16 GiB；cgroup未委派时如实用0.5 s采样停止，不冒称连续内核限制。触线仅停止本任务后代。CPU-only、既有独立FE/ML环境、complex128／float64；不争用GPU、不升级系统ABI/CUDA/BLAS。

这些是**当前共享试验的预算**，不是最终单次48小时任务永远只准单核16GiB。最终资源配额须根据实际可用CPU/RAM/GPU单独冻结，不能按整机容量估算、却在剩余资源上运行并承诺48小时。2TB为物理总量而非RSS上限。全部本批时间标shared-workstation，不能声称零邻影响或无争用提速。

## 3. 48小时终极Gate与本批身份

```math
T_{\rm target}=T_{\rm mesh/setup}+T_{\rm target\ training}+T_{\rm solve/closures}+T_{\rm full\ checks}+T_{\rm recovery/output}\le172800\ \mathrm{s}.
```

这是未来冻结目标模型的单次预算，不是开发期限、当前ETA或成功承诺。为新模型专门建基、预训练、调参、失败重启、加载和检查的成本均须计入实际单次账；复用的通用模型及其离线成本另列，不能在求解前偷偷训练目标解再只计推理。

N0登记最终目标的几何/尺度、0.7nm材料、激励、精度和通道需求。当前缺乏明确目标级字段时写 TARGET_IDENTITY_NOT_FROZEN，不能自动将下面micro-pilot当成目标。该缺口不阻止已有授权的小试验和算子接线，但阻止声称完成最终48小时Gate。

本批总新数值有载wall上限10小时（含候选、非神经对照及小参考），每条优化路线最多2小时，函数/算子次数上限另见§6；均为停止预算而非运行时间预测。不消费完整48小时去盲目训练。小pilot通过只允许提交下一步容量论证，不自动放大、迁移GPU或启动目标规模。

## 4. 新计算链：网络生成目标FE trace，原方程计算loss

网络不预测任意残差的逆，不查询p4 PC；它为本次物理激励直接生成有限元trace系数。单元内部由原局部凝聚关系恢复，完整端口未知量单独优化。这样尝试避免全局分解；代价是新增网络优化和每步正反向算子作用，可能不收敛或反而更慢。

```math
z(w)=\begin{bmatrix}t_h(\theta)\\\alpha\end{bmatrix},\qquad
w=(\theta,\Re\alpha,\Im\alpha),\qquad r=b-Sz(w),\qquad
L(w)=\frac{\|r\|_2^2}{2\|b\|_2^2}.
```

S为本批唯一目标FE的完整凝聚trace＋port算子，不是原物理p4粗层。为首轮可解释性，训练目标固定为未加权完整Schur欧氏残差（仅固定全局RHS尺度），不扫描范数权重，不引入全局Riesz逆／shift／p4预条件loss。原native、完整未凝聚增广方程和端口仍独立检查。b为零用专门解析测试分支；真实物理pilot不得将非零散射载荷判成零。

平方残差可能继承甚至加剧病态；不把欧氏loss称为严格误差估计，也不宣称FEINN理论自动覆盖当前不定散射。参数梯度小或优化器success不等于r小。若有梯度停滞而原残差不合格，记录真实负结果，不藏入昂贵全局逆救场。

### 4.1 trace生成与相容性

沿用标准Nédélec H(curl) FE，不切换DG、标量nodal PDE或仅collocation PINN。网络输出三维复向量函数的局部相位／包络，通过**实际边／面矩插值和方向变换**得到独立canonical trace系数。共享entity只保留一个owner定义；周期从自由度由原MPC/复相位处理，不重复乘相位。保留face高阶矩及全部切向分量；不能用节点值、每entity一个标量或高阶矩清零冒充完整空间。

内部未知量不由全局平滑网络强加连续性，使用原局部物理恢复；材料界面应允许原H(curl)空间容许的法向跳变。所有higher-order/方向／Jacobian／master映射必须有独立FE插值配对。不得给每个FE自由度附加独立可训练embedding后宣称紧凑神经表示；参数数、trace系数数和表示局限必须报告。

初始候选固定为一个坐标包络MLP：归一化三维坐标输入，3层hidden×64、tanh、输出8组三分量复包络；显式乘8个固定载波，方向为±x/±y/±z、入射和镜面反射方向，波数取真空k0。包络保持三维自由，不假定z均匀或模态可分离；这8个载波不是外部DtN通道清单。seed=420906，FP64实虚双通道，无dropout；hidden正常固定seed初始化，末层为零，使散射trace和port从零开始，不全网络零权重。只有一种架构，不按结果增宽/加方向/调频；不足时如实记录表示或优化限制。

网络矩积分使用固定可复现求积，先与独立更高阶求积配对。起始采用本FE规则，不合格时仅按预登记的15→30→60阶一次有界求积精度检查，满足相对1e-8或明确近零绝对规则后冻结；这不是网络超参扫描。FE本身的算子积分规则不随训练变动。不把“参数少”解释为可用不解析0.7nm振荡的粗FE网格。

### 4.2 正向与共轭转置不是求逆

```math
g_z=-S^H r/\|b\|_2^2,\qquad
\mathrm dL=\Re(g_z^H\mathrm dz).
```

通过trace生成器的实参数VJP和port实虚映射累积梯度。S^H是**共轭转置乘法**，不是解伴随方程；禁止误加一次全局伴随LU。原非Hermitian体／端口符号、Hp/Hhat、D/B非互伴关系、MPC及局部消元都要按实际算子转置，不凭对称性猜测。

优先复用 [p6 action-only 核](../../src/solvers/p6_cell_condensed_action.py)和[装配时凝聚](../../src/solvers/hcurl_assembly_time_condensation.py)的目标degree单层接口；文件名p6不意味着必须建p6/p4层次。正向候选不建全局目标稀疏因子或p4层。允许小N1见证进程显式装配同S及S^H作配对，退出清场后才训练；候选训练中不持有该私有CSR作为隐藏依赖。

需要共享FE/ML时首选隔离环境中的薄适配／packet或同进程经已验证的库加载；不将不相容MPI/BLAS/PETSc注入FE。CPU-only Torch仅在本任务环境内；禁止为此升级已有FE ABI。若无法证明运行时兼容，停止受影响训练接线，其他独立可测部分继续。

### 4.3 内存与全残差规则

禁止保留覆盖全部单元的巨大autograd图。采用分块前向生成系数、原S算r与S^H r、再按同一冻结参数重计算网络块并累积VJP；一个完整梯度累积完再optimizer.step。chunk前后梯度和参数更新须与小规模一体计算一致。共享entity/归一化不能因batch改变。

不能将sum_K(norm(r_K)^2)当成norm(sum_K r_K)^2，不能只采样少数元素或端口就声称优化了原全残差。所有行、真实邻接累积和完整端口作用都参与每个正式loss；不裁mode、改变波长或用解析背景场替代散射未知量。可采用准确streaming，但记录累计代价。

## 5. N0：冻结一个真正三维的0.7nm micro-pilot

先关闭旧路线的执行入口计划，不删除代码；旧路径保持research opt-in。只做必要Git/ABI/资源检查，不重跑384个teacher、旧V5诊断或环境安装。

本批新几何是**专门设计的micro-pilot**，不是缩写的最终模型，也不是把旧13.5nm结果同比例换单位：

| 字段／单位nm | 冻结设计 |
|---|---|
| 真空波长／材料 | 0.7；air和同一正式0.7nm Si材料，epsilon=n²、mu_r=1 |
| 周期／范围 | x∈[-0.7,0.7]，y∈[-0.525,0.525]，z∈[-0.175,1.225] |
| 基底／块 | z<0为Si；块x∈[-0.35,0.35]、全y、z∈[0,1.05]为Si，其余air |
| 空气缺口 | 块内x∈[0,0.35]、y∈[-0.175,0.175]、z∈[0.35,0.70]改为air |
| 入射／边界 | grazing1度、azimuth0、s、幅值1；layered background；双Floquet＋完整Fourier-DtN，无PML替换 |
| 唯一候选FE | 六面体各轴步长0.175，8×6×8=384 cells；Nédélec p3，FE积分degree15 |
| 小参考 | 同一mesh/p3准确独立参考；条件允许的p4只作离散误差对照，绝不是重开p4预条件路线 |

采用已有参数化几何构建能力或一个明确research-only的参数化缺口入口，不把原硬编码z40–80配方覆盖掉。网格面与材料界面对齐，实际tags必须显示y与z变化，所有尺寸、canonical cells和mesh/physical SHA入档。材料mask为这里定义的分片常数几何，不靠网络猜材料。微型单胞只有少数波长跨度，**不能凭其通过宣称高频目标规模已经通过**。

正式Si值必须从仓库既有0.7nm材料／Task039审计的原始来源和版本中核实，记录来源路径/commit、波长/能量单位、复数符号和数值；目前本review不猜填n。不得沿用13.5/2nm材料。若现存记录不足，保存 MATERIAL_0P7NM_BLOCKED，完成仍可做的纯数组/插值/接口工作，不用假材料输出正式0.7nm结果、不转回p4研究。

在任何FE分配前估算真实trace/full rows、channels、局部LU和端口数据；目标级上限为本pilot候选及验证各≤200000 full FE系数、≤100000独立trace系数，另完整列出所有port。mode数来自本次物理库存，不锁成80。原算子/网络/optimizer/矩积分/反向/恢复/库临时对象总预算合规才运行；超限停，不自动缩几何、p或通道来过Gate。

## 6. N1–N3：先验证可微计算链，再做唯一神经与非神经对照

### N1：真实接口与梯度

先做小型复数非Hermitian含端口的纯数组测试，再在唯一pilot S上验证：正向与独立FE作用、共轭转置dot test、凝聚／恢复、MPC slave-zero和端口身份（operation-scaled差≤1e-10）。梯度用至少3个非零实参数方向的中心差分核验，预登记h=1e-4/1e-5/1e-6，以稳定收敛区相对误差≤1e-5为Gate，近零另报绝对值。不能在零网络/零梯度点独自通过。

网络矩映射与Basix/DOLFINx相同FE插值配对，导数和chunked累积与小一体autograd配对；全loss梯度同时覆盖网络和非零port参数。原S作用及实际S^H算子不能由mock代替。N1后冻结网络、求积、尺度、optimizer和全部source；N1失败不启动长训练。

### N2：同一目标的三条路线，顺序分进程

| 路线 | 未知量／作用 | 目的 |
|---|---|---|
| NEURAL-TRACE | §4冻结网络参数＋全部复port | 检验网络是否能从原方程求当前解 |
| FREE-FE-OPT | 全部独立trace＋port直接作实虚参数，同loss、初值、optimizer | 不把优化器更换的收益归给网络 |
| FE-LSQR | 同原S/S^H、无PC的复数LSQR或等价实嵌入、从零开始 | 避免只与弱优化基线比较；不是新的PC调参任务 |

NEURAL和FREE固定先Adam 500次更新（lr1e-3，无weight decay），再L-BFGS（history20、初始步长1、strong-Wolfe）；各路线loss＋gradient完整closure总数最多2000（Adam计入），包含所有线搜索回退，且各最多2小时wall。记录外层update与closure分别多少，不能用L-BFGS多次闭包藏算子成本。早停只认独立原残差或明确非有限/预算结束，不认小梯度success；不得根据结果调lr、schedule、模型宽度或重启seed。

FE-LSQR最多2000次S/S^H配对作用且最多2小时，原显式残差在规定检查点重算；可以标准化残差和做原算法内部正交化，不能偷偷加ILU/p4/bottom逆。三条路线的初始化构建费用、kernel次数和收敛曲线分别列出；非神经对照有额外失败不自动禁止神经路线。函数次数相等不是时间相等，真正比较仍用相同正确性下的端到端成本。

每25次更新或closure固定检查点记录独立Schur/native/port；每步轻量loss/gradient/计数，最终必查全部方程。保存loss下降与原残差下降的对应，不将每小batch当一次完整训练步。不读准确reference，任何route都不能从另一条路线的解warm start。

### N3：冻结候选后独立盲验证

三条路线都终止并冻结checkpoint/状态/hash后，才允许一个单独的同mesh/p3准确参考进程；它可在16GiB预算和原symbolic Gate下使用小规模全局直接法，**仅作为测试见证**，不是部署或训练依赖。记录成本、销毁因子、确认RSS/后代释放。候选进程和训练文件没有读取参考解权限/接口，不能根据参考回训。

先在相同离散比较，随后仅当至少一条route取得同离散资格且预算足够，允许同网格p4一次准确参考用于p-enrichment差异检查。额外reference不叫teacher数据生成，不扩大dataset或短波扫描。不允许反复加密直到表格通过；p差异过大则标DISCRETIZATION_NOT_QUALIFIED，留待review。

## 7. 精度、研究判断与失败边界

本批解的是新目标FE方程而非向p6外层返回p4修正。以下为本pilot预先登记的资格标准；不改变旧p4全套1e-10门限。正式目标级精度还须在target identity中冻结，不能用更容易的pilot精度偷换。

| Gate | 新pilot标准／解释 |
|---|---|
| 代数与约束 | N1 identity、S/S^H、恢复、方向与MPC按§6；所有finite，slave-zero；恢复相对缺陷≤1e-10 |
| 完整目标方程 | 原Schur和完整未凝聚增广系统显式相对残差各≤1e-6，固定原RHS分母；独立native体方程≤1e-6 |
| 端口 | 同时报告绝对／固定RHS尺度／原operation-relative；port绝对范数除完整增广RHS范数≤1e-6，operation-relative≤1e-6（继承近零绝对规则），禁止仅靠变大分母过关 |
| 同离散准确参考 | 全FE L2、scaled-curl、selected复E/H及完整ordered复通道向量相对差≤1e-4；近零采用明确绝对规则，不拟合相位 |
| 功率与吸收 | R/T/A/A_volume绝对差≤1e-5，逐通道功率绝对差≤1e-6；能量闭合和A_balance/A_volume差≤1e-5 |
| 非零散射资格 | 除total场外单独比较scattered场和相对背景的通道变化，报告信号尺度；不能因Si弱对比而用零散射解蒙混通过 |
| 离散误差 | 仅条件p3/p4比较；E/H/curl与通道差异目标≤1e-3（明确近零规则）。只是一次p差异检查，不称连续极限证明；未做即not_run |
| 神经增量 | 同正确性、同资源口径下NEURAL比最佳可用非神经路线端到端时间或完整峰RSS改善至少20%且另一项不超预算，才记本pilot增量正信号；共享负载不可比则inconclusive |
| 最终0.7nm48h | 本批始终NOT_QUALIFIED：未运行冻结的目标规模，不能因micro-pilot成功改写 |

以上百分比是研究决策阈值，不是理论收益或预测。残差合格但同离散场误差不合格，仍不可交付official场；同离散通过但p差异未通过，仅为离散代数解。神经失败不能证明所有神经表示无效；反之参数少、梯度正确或训练loss下降均不能证明求解成功。

正常优化停滞不是实现bug。明确实现错误允许一次记录充分的最小修复及仅受影响阶段重放；总预算不重置，不基于结果进行网络/优化扫描。结束时可以是NEURAL_DISCRETE_PASS、NEURAL_OPTIMIZATION_NEGATIVE、DISCRETIZATION_NOT_QUALIFIED、MATERIAL_BLOCKED或RESOURCE_CONTROLLED_STOP等明确阶段身份，不强行用单一PASS覆盖所有Gate。

## 8. N4：48小时资源论证，不作未经测量的外推

报告每完整训练步的网络前向／矩映射、S、S^H、VJP、线搜索、通信/搬运和full audit成本；分别列measured wall、数组bytes、RSS、实际线程和温度/争用状态（仅低开销可得项）。首步JIT与稳态分开，停止/失败费用不删除，不加总父子嵌套timer。

```math
N_{\rm affordable}=\frac{172800-T_{\rm setup}-T_{\rm full\ checks}-T_{\rm recovery/output}}{t_{\rm complete\ step}}.
```

只在分子非负、t为目标规模实测或有注明不确定性的预测时使用。小模型一次测量不能确定目标规模t或所需步数；两者未知即写unknown。训练的S^HS病态和网络非凸性仍可能使该预算不可达，不把stationarity当收敛。

容量账包括FE/trace、真实0.7nm通道、原端口密集项、局部因子、网络、optimizer历史、激活/分块重算、所有工作向量和恢复。禁止把模型参数bytes当作全过程。当前网络参数化不自动减少FE网格或通道，也不自动解决nport²库存；若目标级端口已不可承受，记录独立streaming/distributed blocker，不用预测端口取代物理。

目标模型只作解析尺寸/库存估算，不分配其大矩阵、不启动48小时run。最后建议唯一下一最小阶段，并说明是否值得继续本新表示；不自动回到被关闭的p4路线。

## 9. 代码、Git与交付

所有真实FE阶段经 `python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`，一个dat一项明确stage、operator和运行。允许NN优化内部多closure，但不得隐藏多物理campaign。新数值核放src/solvers，现有runners仅作必要参数化opt-in编排，避免再复制大量task-specific orchestration。

只新增必要网络trace映射、目标单层action/VJP、checker及测试；不改普通默认或旧solver数学行为，不整体merge其他分支。不改原task/review、原负结果、AGENTS；文档新增最新段落保留历史。相关测试用pure→真实小FE→唯一pilot递进；无关旧总账checker基线问题如实记录，不全仓清理、full pytest或回放旧昂贵计算。

建议提交：C1旧路线关闭记录和V6预登记／纯代数与映射；C2原S/S^H/VJP和真实接口；C3三路线及只读validation；C4证据和response。每个正式run前clean实现commit并绑定实际source，受检活跃run中不为文档提交改变HEAD。仅推送 `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`，不用master中转，不amend/强推/合并。

最少交付：

```text
response_v6.md
outcomes/neural_fe_single_solve_v6.md
outcomes/records/neural_fe_design_v6.json
outcomes/records/material_geometry_identity_v6.json
outcomes/records/adjoint_gradient_checks_v6.json
outcomes/records/neural_fe_comparison_v6.csv
outcomes/records/neural_fe_gate_decisions_v6.json
outcomes/records/target_48h_budget_v6.json
outcomes/records/run_index_v6.json
outcomes/summary.md
outcomes/test_summary.md
outcomes/changed_files.md
```

未运行项明确not_run原因，不空填。大矩阵、场、autograd/训练日志和checkpoint只在ignored目录；Git只存compact数据/hash，不重复嵌套巨大JSON。每run保存input_original.dat、resolved_config、manifest、input/physical/source SHA、run_summary、环境/MPI/资源与artifact hash；新增NN seed/架构、moment映射、loss/closure次数、参考隔离和S/S^H身份。同步本分支development_progress/model_registry的Task042新阶段。

Response V6首先回答：旧p4路线是否确实停止；NN到底计算了哪些未知量；真实0.7nm材料与非可分tags是什么；是否没有目标teacher/隐藏强逆；完整梯度与原方程是否正确；与FREE-FE-OPT和LSQR相比如何；代数、物理、离散、资源和神经增量各自是否通过；目标48小时还缺哪些实测。

本批前置Gate通过后直接进入下个已授权阶段，不逐小步再问用户、不因邻heavy自动等全机空闲；真实停止条件按证据收口。推送后停止等待review，不自动更大模型、不merge。

## 10. 方法参考与不能照搬的边界

[Compatible finite element interpolated neural networks](https://arxiv.org/html/2411.04591v2)（Badia、Li、Martín；本文核对日2026-09-29）提供网络插值进入Nédélec空间、用离散残差训练的参考。其文中Maxwell测试主要是正反应项的H(curl)内积模型，不是本项目高频不定Floquet/DtN散射；文献的预条件loss、精确FE初始化或未插值网络优于FE的结果，不得挪作本次合格有限元解证据。本批的trace参数化、完整端口和matrix-free反向是项目新研究，尚未验证。

本review不保证新方案达到0.7nm/48小时。**关闭旧路线是基于现有证据的资源取舍；授权新路线是一个可证伪的有界试验，而不是用新的网络名称替换同一个未解决的强逆依赖。**
