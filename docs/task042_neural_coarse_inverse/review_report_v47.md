# Review V47：近期路线收口与完整散射引擎的本地执行基线

## 0. 本轮决定：不只回执停止，也不重训已被证据否定的候选

**接受V48在既定数据上的有限无损消费和成本负结果，保留Review V46的全部限制；明确授权V49连续执行一个新的完整工作包：在NN-Lab建立可运行、可独立验证、可计冷成本的有限三维散射基线。优先复用dot已发布的完整有限问题及引擎，不复制其原尺寸边界、q块或参数研究；若引擎接入受阻，继续同一物理问题的有界Full3D直接参考及输出验证，不因一个adapter bug终止整个工作包。**

这项工作消除的blocker是：Task042近期学习与存储试验缺少与完整开放边界前向计算匹配的实际消费引擎和冷N=1费用，导致正确的组件也无法转化为完整解或可核算神经收益。本轮交付目标不是又一张接口PASS表，而是`.dat → 网格/材料 → 原Maxwell方程与全部指定DtN模式 → 完整场 → 独立审核 → 全费用`的可执行链。

用户本轮要求继续实质工作、普通bug自行修复。本报告据此**覆盖Review V46中“仅回执、没有V49数值授权”的本批执行限制**，不覆盖其科学负结果和最终门限。本轮是Task042已有“完整引擎消费”工作的明确集成范围扩展，不开发另一套求逆理论、不改变ordinary default。按AGENTS §15新增独立执行范围的V47；V46原文不修改。执行窗口收到本报告后实际执行，不只确认阅读。两个Codex窗口不得同时写工作树或同时运行数值actor。

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task42_neural_coarse_inverse
worktree                    = /home/fenics/Projects/NN-Lab
review_date                 = 2026-10-05
reviewed_HEAD               = 01a44fafe9c5453ba7121d7b94b249e6d2faab86
reviewed_commit_UTC         = 2026-10-05T01:12:44Z
reviewed_latest_review      = review_report_v46.md
reviewed_latest_response    = response_v48.md
V48_delivery_HEAD           = 6c3dadb21aa0edfa7498e5865cf955766882f58a
original_base_SHA           = ccd357885f7f9be84efe3be07868cc94f13d93fc
read_only_donor_branch      = task40extra_dot_parallel_cloud
read_only_donor_HEAD        = 3f4fb69b20d33d382975bb96db73b44bba583ebd
next_batch                  = V49_COMPLETE_SCATTERING_ENGINE_ANCHOR
response_required           = response_v49.md
handoff_out                 = review-execution-handoff-20261005-v47
handoff_back                = execution-review-handoff-20261005-v49
decision                    = AUTHORIZE_BOUNDED_INTEGRATED_EXECUTION
target_0p7nm_2TB_48h         = NOT_QUALIFIED
NN20                        = NOT_DEMONSTRATED
master_merge                = NOT_APPROVED
```

最终目标仍是原50×25nm周期、z=−10..130nm、17×25×120nm Si结构、λ0.7nm、非可分三维能力；冷N=1总时间≤172800s，约2TB整机内保留系统余量、任务峰≤2e12B，ownswap=0。NN在相同正确性下相对最佳合格传统路线改善完整时间或同时峰至少20%，另一项仍合规。**本次有限模型通过，不等于原尺寸、离散收敛、通用生产PC或NN20通过。**

本次ChatGPT实际读取最新分支/任务导航、最新review/response/summary、近期路线汇总、相关源码和dot公开完整有限问题/资源记录。未SSH运行工作站，未解码全部ignored科学数组，未作全仓逐行语义审计。下述新执行为planned/not_run；旧数值为记录中的measured或derived，不把旧审阅者的本地核验称为本次运行。

## 1. 近期进展的集中裁决

依据：[V46审阅](review_report_v46.md)、[V48回应](response_v48.md)、[近期汇总](outcomes/summary.md)、[V45结果](outcomes/full_moment_hierarchy_v45.md)、[V47结果](outcomes/trace_subspace_selection_v47.md)、[V48结果](outcomes/lossless_vector_storage_v48.md)。

| 路线及范围 | 真实进展／负结果 | 本次取舍 |
|---|---|---|
| V15–V35：小模型表示、全空间迭代、局部/粗层 | 有算子实现与实际场改善；V24完整0/5，后续未形成合格目标解 | 不重开旧tau、patch、ILU、同A尾部迭代或p4强逆链 |
| V36–V42：FE/边界/恢复接口 | 有32060模式库存及有限作用证据；V42恢复约7.59e-10、1.01e-10仍越过1e-10门 | 保留可用接口与具体FAIL；不称完整引擎 |
| V43–V45：真实神经修正训练 | 有128次真实更新及梯度；V45五路线各0/8完整通过，两个NN选零修正 | 不是“没训练”；关闭这一固定A学习候选，不换seed/层数重来 |
| V47：固定坐标50%删trace | 前20问题的系数、trace、原残差门均0/20 | 停止依赖训练有依据；不能要求网络突破同坐标表示负结果 |
| V48：全部位保留的因果预测存储 | LIN/NN各256次更新；有限字节/消费通过；NN完整bank在线规划为RAW的2.02713/1.53632倍，码流也劣于shuffle19 | 冻结codec关闭；选step0不等于未训练，也不同于V45零输出 |
| 端到端与NN20 | 尚无原尺寸完整解、合格冷成本与NN20 | 不用单组件小内存、小残差或参数少替代最终资格 |

V43–V48的主要有限数据来自64hex/p6、42624独立系数的体算子，**没有接齐完整DtN**。这一对象与曾经的384hex/p3/40端口micro不同，也与下面80hex/p4/532模式不同；不能仅因同为0.7nm就复用矩阵、权重、误差资格或RHS身份。

V48一次真实消费中，NN约0.2763/0.6403s、RAW约0.00294/0.00459s；这是共享工作站有限消费证据，不是完整求解比较。近期大量失败属于表示、原方程或全成本负结果，不应统称为bug。反过来，reader、shape、API、保存、费用字段等已定位实现错误不应再制造一轮只有失败回执的任务。

### 1.1 dot已有什么、还缺什么

只读依据：[dot V11完整恢复逆](https://github.com/Rookie1234567/MyFEniCS/blob/3f4fb69b20d33d382975bb96db73b44bba583ebd/docs/task40extra_dot_parallel_cloud/response_v11.md)、[V12共享变换](https://github.com/Rookie1234567/MyFEniCS/blob/3f4fb69b20d33d382975bb96db73b44bba583ebd/docs/task40extra_dot_parallel_cloud/response_v12.md)、[最新原尺寸组件](https://github.com/Rookie1234567/MyFEniCS/blob/3f4fb69b20d33d382975bb96db73b44bba583ebd/docs/task40extra_dot_parallel_cloud/outcomes/chunked_surface_mass_v2_zh.md)。

缩尺80cell/p4问题已有15872独立FE、8640内部、7232 trace、532完整aliases及四q分支；规则结构与真实两cell缺口的完整原残差约5.27e-12/7.97e-12，缺口四载荷约4/4/3/4次外迭代。完整输出一致性不等于official功率或连续精度。V11四q因子setup约1.167s，整个worker约145.8s；V12共享模板410624B对逻辑重复体积69435392B，但完整worker采样峰并未因此获下降资格。**费用中可能更贵的是准备/构造，而非几次迭代；仍需本地完整计费，不能先猜一个NN瓶颈。**

最新原尺寸18-cell/p6夹具只覆盖六个选定top/x分量，操作尺度最大差约3.91e-14；不是全体积、全C/D、全部32060模式的原尺寸解。本报告不替dot追加原尺寸实验，也不写其分支。

本次实际取文件发现：Task042 HEAD下没有`src/solvers/y_orbit_two_cell_inverse.py`；历史V12运行SHA `3570347cbd1faf7149611146b8f0f1bdd71f19e6`经远程contents API不可取，但当前冻结dot发布HEAD中的数值文件可读。**历史运行SHA、当前发布源和本地迁移后运行SHA必须分开；不得让Codex反复fetch不可取旧SHA，更不能宣称当前源逐字等于旧资格源。** 通过可访问发布源与新本地验证建立新身份。

## 2. 本次要得到的实质交付

优先级：**完整物理输入/输出链 > 同物理两引擎配对 > 离散资格前进一步 > 全成本学习机会。** 不把数百项hash测试、一次人工RHS作用或“完整引擎字段匹配”当作完成。

| 必做包 | 最低实质产物 |
|---|---|
| P0：冻结与最小复用 | 新有限问题manifest；当前源依赖闭包；可运行的Task042 opt-in入口；未依赖旧不可取科学包 |
| P1：完整Full3D参考 | 规则与真实非可分缺口的物理入射求解、全部内部恢复、双Floquet、指定全部532模式；实际完整系数及原残差 |
| P2：现有结构利用引擎接入 | 同两个物理问题的独立零初值调用；与P1同离散比较，完整q与端口不删；或具体依赖阻塞，P1/P3仍继续 |
| P3：场与功率 | E/H、total/scattered、532复通道及逐级功率、R/T/A/A_volume、能量；共同规范下独立审核 |
| P4：有限精度与费用 | 有界同几何p5检查的实际结果/容量阻塞；逐阶段冷N=1时间和同时对象；一个真实昂贵学习对象或有量化依据的排除 |

本轮不重新训练旧NN、删系数或codec，不开发新的PC。不凭缺少NN20机会再次拒绝运行本轮完整基线；取得真实基线和费用本身就是本轮的新授权。也不为获得NN20而人为给传统引擎加bank、低效步骤或弱对照。

## 3. 冻结有限模型，不能与原尺寸或旧64-cell数据混用

以公开dot `pilot_config`和p4/phi5完整问题配方为来源，在第一次数值前生成明文resolved descriptor，所有算法读取同一个descriptor，禁止runner再悄悄改尺寸、阶数或材料。

| 项目 | 本批固定值／核验方式 |
|---|---|
| family | V49_COMPLETE_SCATTERING_ENGINE_ANCHOR；新physical/discretization SHA，不借旧micro SHA |
| 波长/材料 | λ0=0.7nm；canonical Si表原用户值；n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；air=1；0.699999988仅显式alias，不插值 |
| 几何尺度 | s=7/135；x轴s×(0,16.5,25,33.5,50)，y轴s×(0,6.25,12.5,18.75,25)，z轴s×(−10,0,40,80,120,130)；接口z=0 |
| 网格/FE | 4×4×5=80hex，Nédélec同族p4，complex128；期望独立15872、trace7232、内部8640、native17204；实际布局与编号另绑定 |
| 物理入射 | grazing1°、azimuth5°、s极化、幅值1；来源phi5完整夹具；不使用generic或interior_only人工RHS替代物理结果 |
| 两个模型 | REGULAR；NOTCH使用发布源中的真实两cell材料缺口规则；写出全部cell中心/标签/几何范围及实际cell-id，不沿y复制缺口 |
| 边界 | x/y双Floquet；Fourier-DtN top/bottom全部manual m=−9..9、n=−3..3、两极化，共532 aliases；532是有限截断库存，不是无限精确边界 |
| q | 结构利用引擎保留Ny=4全部q；只对规则背景求逆作结构利用，缺口原算子保留跨q耦合，不把最终解约束为可分离 |
| 局部求积 | 首先读取同一发布源的实际q与规则/权重；不从旧p6/q15猜等价，构造前写入manifest并由两引擎共同采用 |

维数/物理描述不符先定位版本、阶数、mesh/MPC；不可为了匹配表格直接删行。跨ABI的本地新网格、DOF排列、索引宽度和JIT签名可以不同，但必须有明确映射和完整作用/场配对；不得放宽旧远端的逐字Gate，也不得要求外国JIT字节相等才允许本地新参考。

将NOTCH先按几何意义冻结再分配native id，禁止新旧机器的cell编号不一致时改到另一块Si。若发布源中该规则不能恢复，给出明确缺项；可由可读函数重建同一物理定义，不从旧解或误差反推几何。

## 4. P0/P1：有界完整参考先行，不等一个理想的外部包

### 4.1 最小源复用与失败替代

读取冻结dot发布源的`task40extra_y_orbit_reference.py`、`y_orbit_two_cell_inverse.py`、`y_orbit_two_cell_inverse_probe.py`、`y_orbit_two_cell_transport.py`、`y_orbit_two_cell_block_audit.py`及其实际数值依赖。先列manifest（路径、Git blob/sha256、来源、必要性、是否已有本地实现），只迁移调用闭包；优先给现有公共构造器传参数/回调，不整体merge、cherry-pick分支或覆盖无关公共文件。

迁移到Task042 opt-in适配层，旧dot CLI及guard不直接作为NN-Lab入口。所有正式导入来自NN-Lab已提交的源码；不可从另一活跃工作树临时import。数值模块进`src/`，one-run orchestration与监督复用现有基础设施，不创建每个case一套大型runner。

**旧ignored packet缺失不是终止P1的理由。** 已有历史数值可作参考，但本轮允许从冻结物理descriptor使用本地FE栈重新生成该有限问题；生成、JIT、装配和因子全部付费。不要重跑dot历次归档/元数据campaign来取得旧hash。历史3570347不可取时使用可访问发布源，建立新source，不重建虚假的旧Git历史。

若结构利用依赖闭包/旧快照reader在90分钟实现预算内仍不能接齐，将P2记`ADAPTER_BLOCKED`；**继续P1完整直接参考和P3/P4**。不是改用无DtN制造算子，不是要求用户补述历史或等待dot。

### 4.2 完整方程与参考角色

两个算法共用原体弱式、Floquet约束、DtN库存、规范和物理散射RHS；审核仍从原未凝聚体作用和原端口构造重算。以实际实现符号记录：

```math
\begin{bmatrix}V&B\\-D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=\begin{bmatrix}f\\g\end{bmatrix},\qquad
V=K_{\mathrm{curl}}-k_0^2M_\epsilon.
```

不得假定D=Bᴴ、H为identity、内部RHS为零，或把H与消元后的Hhat混用。物理f/g由入射和背景公式生成，不用已知解制造。只为小测试允许非零内部/port制造见证。

P1采用已有Full3D assembly-time condensation及已有精确直接后端，得到同一p4有限系统的规则和缺口参考。**这是小规模authority许可，不是重开“准确p4逆作生产PC”研究。** 可物化该有限问题的凝聚trace+port矩阵；不物化原尺寸、不提取逆、不存factor全副本。

期望凝聚维数7232+532=7764；正式分配上限10000行且具体对象重叠规划≤8GiB。先计算CSR/稠密最坏载荷与factor/workspace包络；7764²×16约0.898GiB只是一张满复矩阵，不是完整进程峰。符号/数值factor受独立树watchdog，不以OOM探容量。优先当前已资格PETSc复数直接后端；没有该后端时，允许一次固定SciPy SuperLU/COLAMD精确分解fallback，先真实小复系统测试，不扫描排序、ILU或位移。

每个参考先solve→原true residual→保存最小recovery packet→释放KSP/PC及直接因子/无用矩阵→记录对象/RSS→恢复/输出。无法释放某个必要对象就如实说明，不宣称已释放。原作用oracle保持可独立复算，不能因释放因子一起删除唯一残差路径。

## 5. P2：实际消费结构利用引擎，不复制其研究

采用已发布四q/两胞元参考逆的现有算法，不重新开展q0、正负q复用、surface-mass或原尺寸32060组件实验。规则背景逆的所有局部/全局因子计费；NOTCH外层必须作用于完整非可分原A，保留所有内部和532端口。它是Full3D原问题上的结构利用预条件，不授通用任意几何收敛结论。

规则和缺口都从物理零初值独立求解；不得读取P1参考场、旧NN/Q/teacher、旧Krylov状态或另一模型的解来初始化。只允许配置和原方程构造代码共用。数据reader按角色白名单，SOURCE/BUILD不解压field；CANDIDATE不读取reference科学数组；VERIFY在候选冻结后才读。

完整新cold run从新case目录/进程构建其所需物理对象，不从上一例复制预制数值因子。允许OS文件缓存存在，但标明“进程/数值准备冷”，不冒称清空操作系统cache。编译缓存有无命中另列；首次编译成本不得从冷N1分母消失。

在小合成复数系统和两个真实完整问题上核对：全部q、primal/dual变换、非零内部与端口、相位与反向恢复、最终完整原残差。不得只取一个q或一个mode作最终通过。实际外层上限128次、restart按来源固定；第64次仍有下降且预算安全可完成到128，不因一个非关键序列化bug放弃已返回向量。

计算返回立刻原子保存完整系数/port及输入source hash，再保存派生审核；audit_pending可在同轮补审，不重算已经合法返回的求解。外部运行SHA不作为本次source。若候选始终不收敛，保留负结果；直接参考/P3/费用仍完成，不加新PC或用参考warm-start“救成功”。

## 6. P3/P4：完整场、有限精度和真实费用

### 6.1 同离散与物理审核分层

每个物理case保存完整E/H复系数、total/scattered、固定空间点selected E/H、532个原mode键/侧/极化/参考面/归一化/复振幅/功率及R/T/A/A_volume。H从原时间约定与curl(E)计算，记录单位，不能用电场幅值猜H。功率由原批准的端口/吸收公式计算；不能归一化R+T+A制造守恒。

原方程成功门：原完整true residual、原增广/端口与native≤1e-6；运算尺度恢复/恒等式≤1e-10、slave storage原规则。直接参考内部目标≤1e-10，有条件仅作固定最多2次残差精化；精化费用明列，不能反复直到隐藏实现问题。

同离散候选对P1参考的total/scattered E/H与scaled-curl、selected复场、完整复通道≤1e-4；R/T/A/A_volume绝对差≤1e-5，最大逐mode功率差≤1e-6，能量闭合≤1e-5。近零参考量使用既有固定绝对/相对混合口径，预先声明，不能事后改分母。propagating与evanescent模式完整保留；532有限截断没有自动取得截断收敛。

审核需有至少一条独立于候选凝聚/模态分支的原全体积作用。小规模直接参考与候选共享物理形式是同离散比较，不是独立软件或连续真解；报告明确共享项。若原方程通过但能量/通道失败，先检查单位、符号、背景、参考面、内积共轭和求积；不得将其写为完整physics pass。

### 6.2 一步有限精度扩展，不做无界网格扫描

规则及NOTCH的p4原方程和后处理链可信后，在剩余时间/容量允许时，仅对NOTCH做一个**同几何同网格p5直接参考**，仍保留532模式，p级/求积/维数形成新身份。不把p5解回传p4候选或NN。容量不合格则明确`P5_CAPACITY_BLOCKED`，仍交付p4完整数据，不能改成更小几何或删通道来凑通过。

比较p4/p5场的共同物理积分、全部重要通道、R/T/A/A_volume，报告实际差和网格限制。单次差小只称有限p增量一致性，不宣称continuum convergence。若p4能量门失败而代数/单位正确，可将p5用于区分离散/求积影响，但不得覆盖旧p4 FAIL；本轮不再加入第三个p或一轮参数扫描。

### 6.3 费用必须接在实际求解链上

每个引擎×case独立列：输入/mesh+MPC、JIT/原tensor、C/D/H与归一化、映射/共享存储、凝聚/因子、外迭代及全部作用、恢复、E/H/逐mode输出、原审核、IO/加载及失败。嵌套计时不得重复相加。记录同时对象的birth/death及至少四个阶段RSS；unique owner字节与整树峰分列，不能将后处理释放量当全过程峰下降。

两张账并列：本轮研究/参考/迁移/失败总费用；从物理输入起单一引擎一次完整运行的cold N=1部署费用。参考若用于运行时校正/标签必须入部署费用；仅作为外部资格测试另列，不能把两口径混成“几秒钟得到整个解”。训练为0需明确本批未训，不代表未来免费。没有对多个规模校准，不给原尺寸的确定时间/内存外推。

依据实际阶段排名最多选一个后续独立学习对象，检查乐观必要界：

```math
T_B=C+V,\qquad fV-H\ge0.2T_B,\qquad 0\le f\le1.
```

这里V必须是引擎确实执行且模型确实能替代的步骤，H包括数据/teacher/训练/模型/额外纠错等全费用；先计算H=0、f=1的乐观界，不排除才列可接受H预算，不凭假设先训练。内存按真实峰时对象判断V_B−V_N−W≥0.2M_B，并检查训练/prepare新峰。若瓶颈是确定性重复存储或无效构造，优先记录已有精确共享/生命周期方法，不把它改名为NN。

**本轮不自动训练一个未指定架构。** 得到完整基线和真实费用后，下次才围绕一个新的、与关闭路线不同的对象定实验；避免把主工作再次变成短组件训练。没有20%机会时交付可用完整基线和排除证据，而不是空手停止。

## 7. 连续执行、修复与失败分流

执行主顺序：`P0 → P1 REGULAR/NOTCH → P2 REGULAR/NOTCH → P3独立审核 → 条件p5 → 成本/交付`。实现可以并行思考但数值actor串行，接通一个完整case即可开始其受监督运行，不必先把全部后备代码写完。

| 情况 | 本轮必须采取的动作 |
|---|---|
| reader/API/shape/路径/序列化/费用字段bug | 保存根因和失败成本，最小修复、targeted回归，继续受影响阶段；不只是response写“下轮修” |
| 不可取旧SHA/旧ignored包 | 使用冻结公开源建立新身份；完整物理输入可恢复则本地fresh构造；不伪造旧hash |
| P2导入/结构引擎blocked | P1完整直接参考、后处理、有限精度/费用继续；不替代为无DtN小矩阵 |
| P1完整方程接线错误 | 先在非Hermitian/非零内部和port小见证定位，再在受影响case重新验证；不能继续依赖未知原方程的训练 |
| 原残差过、场/功率不过 | 分离数值、离散、后处理原因；保留原向量，优先补审不重解；允许上述一次p5，不能放宽物理门 |
| 一个模型/候选不收敛 | 记录真实负结果，继续另一独立case/参考/成本，不换材料、几何或算法直到成功 |
| 安全/身份/ABI不可置信 | 停止自身依赖重负载，有限复核；不关闭watchdog或影响邻任务；完成可做的低负载收口 |

不再用“累计四个任意小bug”作为整个任务必须停的机械条件。以全局截止和**意外修复累计≤7200s**为边界；同一根因两次未修好，必须重新定位/使用已授权替代路径，不能第三次盲重跑。发生原方程、安全、身份错误时不得以“不要停”绕过。数值不收敛不是bug，修复也不得偷偷换实验。

复用已提交、同身份有效的昂贵Gate；无关文档/字段修改不触发完整科学重放。重放只覆盖真正受影响的数据依赖，运行前有clean新source。长期命令无输出先查heartbeat/CPU/进程树和prompt，不重复启动；所有返回向量先存盘。没有必要的系统安装，不运行sudo；认证失败隔离网络步骤，不等待密码。

## 8. 预算、隔离和实际命令

从首次本轮实时时钟冻结**7小时总窗口**，最后45分钟用于清场/最小结果/交付；所有实现、检查、移植、失败、冷却、求解、后处理均计入。数值有载累计上限5小时，修复计时与数值重放不重复相加但均受总上限。不是要求跑满，也不能沿用/刷新V48 closed窗口。

正式大stage最多：p4直接2个、p4结构利用2个、条件p5参考1个；短非零内部/port见证随相应setup计费，不另起一个campaign。每个case solve全含准备默认上限3600s；符号factor与资源健康时不能用任意30秒timeout误杀。达到全局余量不足先保留P1/P3，再跳条件p5或尚未接齐的P2。至少预留600s完整verify及2700s总收尾。

共享原生CPU环境、MPI1、数学/BLAS线程1、Loader0、GPU不用；必须从Task042现有资格activation进入，不为原生Linux强制旧WSL marker。每stage现场选空闲物理核/避忙SMT。自身规划峰≤8GiB、warning12GiB、采样整树hard16GiB、自身swap0；0.5秒监督并报告实际采样间隔，没有可写cgroup不称连续内核硬峰。原PSI/系统和邻任务增长余量保持，只停止自身后代，不改邻任务、全机swap、系统BLAS/CUDA/ABI或共享Git配置。

本批允许新增ignored artifact≤4GiB、Task042累计去重≤28GiB、free≥50GiB；这一次容量许可不授权删除旧失败或其他任务数据。先查当前占用，缺空间则减少可重建debug副本/取消p5，不删required完整结果。大矩阵/factor/字段入ignored目录，Git只存紧凑索引与结果。优先逐文件hash和当前依赖闭包，不再次全仓/全部归档数GB扫描去凑审阅。

已有heavy存在不自动取消受控共享任务，但真实PSI/余量不安全停止自身重负载。资源停止后只允许一次≤600s冷却复核且重新满足原Gate的重入，费用计入；不能换算法绕过保护。

新入口在本报告提交时尚未实现。先实现/最小真实schema回归/clean commit，再执行；每个`.dat`是一项明确计算，内部Gate不能隐含启动另一个case：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_engine_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_reference_regular.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_reference_notch.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_engine_regular.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_engine_notch.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_verify_p4.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_reference_notch_p5.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v49_accuracy_cost_report.dat
```

两个条件入口按准入运行，不盲跑整个shell链。输入统一保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json，绑定实际mesh/材料/port/JIT/数组/环境/MPI和资源。新物理SHA按实际生成，不手填旧值。没有source/data可追溯就不授正式通过，但一次明确缺项不取消无依赖路径。

## 9. 交付、判定与commit计划

提交计划：C0新descriptor/源依赖manifest/入口与小回归；C1完整参考及结构适配器实现；必要Cfix按根因；R受监督运行；C2紧凑结果/独立checker/费用/最终response。每个真实run绑定其C1或Cfix，文档HEAD不冒充运行source。不要把原review/response/history改成新结论。

交付`response_v49.md`及`outcomes/complete_scattering_engine_anchor_v49.md`，至少包括：

- `engine_source_manifest_v49.json`、`physical_cases_v49.json`和跨ABI/不可取源处理；
- 每算法×case完整原残差/场/532通道/功率表、原完整系数artifact索引、直接与结构引擎共享/独立项；
- `cold_n1_costs_v49.json`、`object_lifetimes_v49.json`、真实树资源/阶段时间/失败成本和条件p5差异；
- `opportunity_decision_v49.json`：最多一个后续学习对象、代替哪一步、20%乐观界与unknown；
- `repair_journal_v49.jsonl`、run index、最小tests/changed-files、实际未运行与停止原因。

同步README最新入口、summary、development_progress和development_model_registry，只增最新前缀/必要条目，不复制几十份旧JSON。报告明确区分：COMPLETE_FINITE_EQUATION_PASS、FINITE_OBSERVABLE_PASS、P_INCREMENT_CHECK、TARGET_NOT_QUALIFIED、NN_NOT_TRAINED_THIS_BATCH。有完整原方程但某功率/阶次门未过，按实际部分资格；只有历史hash/接口测试不能称本轮实质成功。

旧Review V46没有被新科学证据推翻；本报告是用户授权下的下一集成执行，不追溯改变V48关闭。GitHub公式/表格须检查；拿不到视觉页面就标NOT_VERIFIED，本地结构不冒充网页/CI资格，但不因文档视觉外部服务不可达取消可信物理阶段。

只推送：

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

结束前查实时钟、实际remote HEAD/upstream/clean、ledger closed、active null、后代清场/锁释放。原队列一次交回`execution-review-handoff-20261005-v49`，附精确结果HEAD和唯一下一建议；不merge、不修改dot/master/其他工作树，不在7小时后后台继续。阶段边界可安全提交继续预授权队列，不每一步等用户确认。

## 10. 审阅引用与限制

复用方法依据为上文冻结仓库源和完整问题记录。原显式残差与后处理的外部接口参照：[PETSc KSPBuildResidual](https://petsc.org/release/manualpages/KSP/KSPBuildResidual/)、[DOLFINx 0.10完整散射/吸收演示](https://docs.fenicsproject.org/dolfinx/v0.10.0.post5/python/demos/demo_scattering_boundary_conditions.html)。演示是二维例子，只用于规范复数场/能流与独立后处理意识，不作为本三维Floquet/DtN的现成验证或替代公式。

本文件本地检查只涉及结构、预算与小型复数凝聚/恢复代数；没有运行FEniCS、dot引擎或新物理解。远端数值执行和全部最终Gate由Codex按本合同实际取得。
