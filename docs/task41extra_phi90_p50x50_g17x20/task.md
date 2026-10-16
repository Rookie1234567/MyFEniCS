# Task41extra：90°方位角、50×50 nm周期、17×20 nm居中Si单元的三维Maxwell计算

## 0. 目标、分叉与第一交付

**本任务首先消除的 blocker：入射方向和实际几何已更正，旧 Task40extra 的矩阵、模式和数值资格不能代表新物理问题。复用已有程序，在原物理尺寸上先完成13.5 nm直接/迭代对照，再直接进入0.7 nm；不重做一串旧波长，不先整理全仓，不另造预条件器。**

| 项目 | 冻结值或决定 |
|---|---|
| 创建日期 | 2026-10-16，Asia/Singapore |
| repository | `Rookie1234567/MyFEniCS` |
| 唯一新分支与 task_id | `task41extra_phi90_p50x50_g17x20` |
| 任务目录 | `docs/task41extra_phi90_p50x50_g17x20` |
| 用户指定母分支 | `task40extra_0p7nm_engineering` |
| 精确 branch/base SHA | `939ffe1f7b8d5a7406a01e25a716c08d36090078` |
| 母线末次科学源码 | `37b92ca7897b38f8552dd76b54af3973817fbcde` |
| 母线状态 | V33已按用户要求暂停并收尾；不自动恢复 |
| Codex 项目与聊天 | **现有项目名、主控/执行对话和客户端不变**；Git分支/task改变不要求新建Codex项目 |
| 最终目标 | 新物理条件下0.7 nm、完整三维复场，整机十进制2 TB含余量、任务swap=0、必要单场冷流程≤172800 s |
| 第一可审成果 | 新模型13.5 nm完整直接场＋同离散Task40参考预条件迭代场；不是仅配置、单测或容量预测 |

本轮用户明确授权从 Task40extra 新建 Task41extra 分支，是对“通常由Codex建分支”和“从master起分支”的本次特定覆盖。ChatGPT只建立新分支和任务材料；Codex实现、测试、计算并写 `response_v1.md`。不改母分支、原task39extra、task39extra_para、Hybrid、Task042或master，不自动合并。旧 Task041 Hybrid 任务与本任务不同。

远端母线记录已清场，但实际切换前仍由主控核对本地/工作站进程。此前 q0/q4 的成功和失败按原身份保留，不能因新物理而删除，也不能重新署名为本任务成果。[S1][S2]

## 1. 项目名保持不变，代码与产物如何隔离

沿用现有控制入口和同一工作目录，不要求用户重建Codex项目或重新配置SSH。已知本机执行目录为 `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering`，工作站为既有 `fenics-ws`、`/home/fenics/Projects/laptop_share`；实际 `realpath`、仓库根、upstream和运行库来源由主控读回确认。路径含task40只是历史名字，不决定当前任务。

确认旧服务及后代已退出、tracked工作树干净、没有未收口写入后，在现有worktree切换到本新远端分支并登记upstream。允许本次有记录的分支切换；不在活动进程下switch，不reset/clean/stash掩盖未提交修改，不搬动旧大数组，不新建第二个执行项目。若有未提交工作，先由主控按其真实所属任务保全，不强行覆盖。

新输入置于 `input/task41extra_phi90_p50x50_g17x20/`，新数据置于 `benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/` 或 `results/task41extra_phi90_p50x50_g17x20/` 的唯一run子目录。旧runtime可在ABI核验后继续用，旧JIT只在代码/ABI/积分身份匹配时复用；新任务结果、窗口、selector和账本独立，不覆盖旧目录。

主控负责源码冻结、集中commit/push和工作站协调；执行者负责获准实现/运行/证据。保持既有SSH通道，不安装第二套Codex，不改系统库、其他项目环境或机器全局swap。母线目录内AGENTS的旧分支/P0/窗口只约束母任务，不作为本任务当前状态；根AGENTS和docs规则继续适用。

## 2. 唯一主物理模型

### 2.1 新几何与“其他不变”的明确解释

| 量 | 新任务固定值，单位nm（角度除外） |
|---|---|
| 周期单胞 | x∈[0,50]，y∈[0,50] |
| Si光栅主体 | x∈[16.5,33.5]，y∈[15,35]，z∈[0,120] |
| 主体中心/尺寸 | 中心(x,y)=(25,25)，尺寸17×20×120 |
| 显式基底 | z∈[-10,0]，整个50×50横截面为Si |
| 上方空气 | 光栅外为空气；顶部z=130，距光栅顶10 |
| 下方外域 | 从z=-10向下的同材料Si半空间，Fourier-DtN |
| 入射 | 从上向下，掠角1°、方位角90°、S偏振、归一化电场幅值1 |
| 边界 | x/y双Floquet；z双端口Fourier-DtN；layered背景；无PML |
| 求解 | 频域、complex128、三维Nédélec H(curl)，初始p6 |

**建模解释：本轮按用户最新给出的居中矩形Si主体定义主案例，不自动附加旧Task40用于研究的 `cell_notch` 或 `air_void_box_nm`。两项显式关闭，不从母输入继承。** 旧缺口在新y边界下可能被意外裁切，绝不能默默形成一个未描述的器件。主控在第一份物理清单中突出显示“完整居中矩形，无额外诊断缺口”；如用户另指定保留缺口，先冻结其新坐标并新建物理身份，不自行发明其位置。

目标已经在x/y两方向有有限材料边界，不能使用沿y不变、N0、二维TE或2.5D替代。它在主体高度区间沿z规则挤出，故本案成功也不自动证明任意非可分三维几何；长期任意三维目标保持，当前计算始终使用完整Full3D算子。

### 2.2 入射相位、偏振与坐标

沿仓库从向下-z计theta的定义，掠角1°对应 `incident_theta_deg=89`，不是theta=1。φ从+x朝+y计90°。真空入射波矢为：

```math
k_0=2\pi/\lambda_0,\qquad
(k_x,k_y,k_z)=k_0(\cos1^\circ\cos90^\circ,\cos1^\circ\sin90^\circ,-\sin1^\circ).
```

理论kx=0，ky>0，kz<0；浮点cos90°的微小值按统一配置处理并记录，不能让入射/RHS/Floquet/模式各用不同的清零规则。两方向相位分别为exp(i kx·50)、exp(i ky·50)，新y相位通常不是1。沿现有s基向量约定，E方向接近(-1,0,0)，不可只改φ却保留旧的+y偏振；H由同一k×E和单位约定生成。验证k·E、k·H、上下传播和能流方向，保留整体相位约定，不事后拟合场。[S3][S4]

由上述公式推导，0.7 nm入射相位周期：y约0.7001066 nm，z约40.10908 nm；13.5 nm时分别约13.50206 nm、773.5323 nm。它们仅是入射相位尺度，不是散射场或网格精度保证。kx=0不意味着散射场沿x不变，也不能因此只保留m=0。

### 2.3 材料按波长冻结，不混用其他分支

| 真空波长nm | Si主体与基底的既有复折射率 | 来源和范围 |
|---|---|---|
| 13.5 | 0.999002304859 + 0.00182649365 i | 母代码 `SI_GRATING_INDEX_EUV_13P5_NM`；继承数据，不称新测量 |
| 0.7 | 0.99988517036884961 + 4.3236152269189515e-6 i | 母线原尺寸Task40输入；与已核对的早期G0值一致 |

空气n=1，mu_r=1，epsilon_r在complex128下由n²计算。沿原时间谐波/吸收符号，保留材料来源文件及hash。[S3][S5]

注意 Task39extra_para 交接中0.7 nm Si值略不同；本任务明确基于Task40且“其他不变”，不得静默换用另一分支的n，也不得将13.5 nm材料沿用到0.7 nm。P0将暂停运行的resolved材料与上表读回对照；若有真实后续覆盖，报告差异而不是择一猜测。

## 3. 继承原思路，但重新验证适用性

本任务“原思路”指母线最新的 **真实p6 Full3D外层＋规则p6参考问题的准确q分块修正**。不是另起PC，也不是将Task39extra_para尚未关闭的p4 BAL_H故障迁入此任务。

单元静态凝聚先消去内部自由度，外层处理trace/port未知量；求得后用保留的局部关系恢复内部E/H。真实目标始终保留17×20的Si主体。参考预条件器才允许使用沿y填满的17×50×120规则Si条带，保持同一单胞、基底、波长、材料、入射、网格和端口；这是辅助算子，不能替换目标材料。[S6]

利用规则参考的平移重复性，在q坐标中准确求解再恢复修正。复用现有sector-first、row-tile、逐模式保存、准确MUMPS和因子驻留实现。容量允许优先保留全部准确因子，不固定使用单槽反复分解；记完整PC成本，不用outer步数代替成本。[S6][S7]

**新目标相对沿y填满参考的差异更大，且ky不再为0。旧模型少迭代不能作为新模型收敛承诺。** 先在13.5 nm真实新几何上与直接解对照，既验证算法实现，也测这种参考修正的实际效果。

对于均匀Ny层、两胞局部参考，令单层平移因子为t_q，必须满足：

```math
t_q=\exp\left(i\frac{k_yL_y+2\pi q}{N_y}\right),\qquad t_q^{N_y}=\exp(i k_yL_y).
```

两胞配对为q与q+Ny/2，但只有在实际Ny为偶数、同网格平移/材料/积分/端口恒等式成立时使用。不得沿用ky=0的roots、旧n别名或固定4/8 q。当前profile类已包含q_count/replication关系，应参数化现有允许入口而非伪造旧profile。每个新q的map、CSR、native、factor资格独立；reference跨q泄漏门不适用于真实target，真实target在q坐标中可以耦合。[S7]

有限规则实体不等于可将内部场降成独立二维问题；外层仍完整三维。Hybrid/QEP、神经网络、新DD、低内存弱p4及参数盲扫不在首批范围。

## 4. 从一开始按新物理产生完整外部模式

真实端口横向波矢是kx+2πm/50、ky+2πn/50。按新λ、上下介质、入射方向和原向外/衰减支路重新枚举整个二维(m,n)清单，保存side/polarization、传播/倏逝、Rayleigh近截止、原H、排序与set hash。[S4]

禁止继承旧572个N0、旧32060项、旧m=-142…0范围、旧q160或“把m/n索引换名”的数组。φ=90°仅使入射快相位改向y，新矩形散射仍包含m≠0和n≠0。模式缺项不能靠能量闭合自动补资格。

首场可使用现有 `auto_propagating` 的完整二维传播清单，标明其截断范围；这不是完整无限DtN。首个工程场不等待无限截断收敛才启动，但最终精度必须包含传播级全覆盖及所需倏逝扩展对照。积分按新清单与真实FE形式生成/核验，记录实际参考点数；direct与iterative同离散对照用相同积分和清单。

端口准备必须采用已有有界/逐模式持久化路径：完成一个模式或数值块后可严格重开；完整carrier确需缓存时必须计入实际backing、复用次数和峰值。不要先一次性生成巨大carrier再称为streaming。新case的B/D内部支持条件也须由实际数据验证，不能移植旧“内部为零”证书。

## 5. 连续执行路线：13.5 nm完成必要资格，直接转0.7 nm

### P0：一次性冻结新输入和正式入口

主控确认旧Task40暂停/清场与新分支，完成新physics/profile、geometry、selector、run_case、worker、mode generator、watchdog和checker的最小接线。共享数学代码保持；以配置传递新task/model/source/window，不复制一套task41求解核心或整套service。

将第2节写入真实DAT/resolved，输出几何边界/Si体积与占空比、incident k/E/H、Floquet相位、材料、完整mode inventory。纯主体Si体积17×20×120=40800 nm³，显式基底25000 nm³，是几何派生检查，不是场结果。检查没有遗留void、错误S偏振或旧N0选择。

定向测试只覆盖本次配置/相位/材料/网格、真实调度与身份拒绝路径；昂贵内核可替身化，但修改的参数传递不能全部mock。然后用首个真实13.5 nm运行验证科学链；不先跑全仓pytest或旧波长回归阶梯。

### A：原尺寸13.5 nm，有限且明确的资格阶段

建议起始边界拟合网格G13：x分界0/16.5/33.5/50，各分3/4/3；y均匀10层、hy=5，恰含15和35；z分界-10/0/120/130，各分1/12/1。计划10×10×14=1400 hexahedra、p6，真实生成后核验正Jacobian、材料面、周期面、方向和counts。Ny=10时参考应为10q、5个两胞sector，所有维数从实际profile/map读取，不能保留8q。

这是同离散正确性锚点，不是已证明精度网格。若当前网格接口引入额外必要平面，先记录真实计划、双方用同一网格；不靠错切材料面维持1400。

| 顺序 | 正式对象与完成条件 |
|---|---|
| A1 | 一场新几何13.5 nm p6凝聚直接解；完整原A6、恢复、E/H、R/T/A、体吸收、全模式输出通过。直接法只作此规模authority，不作为0.7 nm生产路线承诺。 |
| A2 | 一场同网格/材料/modes的p6参考预条件FGMRES解，zero start、原restart32/max2048；参考sector/q原生资格、准确因子和完整PC先在该规模通过；与A1独立对照。 |
| A3（条件一次） | 若A1/A2已闭合且需要判断网格方向，最多一场只加密y为20层的同物理对照。它是方向观察，不要求先完成所有精度扫描。 |
| A出口 | A1/A2的数学/物理/同离散资格闭合后直接进入B；A3不是强制前置，也不增加5、3、2 nm阶梯。真实迭代数学或收敛失败则定位同输入，不把direct成功写成PC成功。 |

参考与target的差异较旧Task40大；若PC准确但FGMRES进展不足，保留完整原A6历史、每步成本和预算，明确“参考有效性不足”而非“接口未完成”。不在本任务里自动改成另一PC或用direct解作初值。

### B：直接进入原尺寸0.7 nm，先资格和资源再完整场

A出口后保持50×50×140 nm实体不缩尺，更换为第2.3节0.7 nm材料和新模式。13.5 nm的网格、矩阵、factor、RHS、H、q映射和收敛次数均不能直接沿用。基函数代码、合法参考表与已合格软件机制可复用。

**B0：先在实际新物理上完成便宜的可计算性盘点，并尽快进入一次完整field。** 保持p6，优先细化快相位的y；x/z根据材料界面和散射成分独立评估，不将它们粗化视为已获得精度。首候选可取Nx10、Ny200、Nz14：y=0.25 nm并匹配15/35，28000 cells；此数目仅为资源/算子pilot设计，不承诺精度或LU内存。正式启动前用实际局部传播/恢复、端口投影、网格计数和全对象账确认适用；若需改变候选，记录明确原因及单独输入，不机械把三轴按13.5/0.7倍全部细化。

该候选沿单层q分解会是200q而非8q；相应局部sector数、生成成本、空端口q、准确因子总量必须真实测算。若接口只支持旧q数，修有限参数化并在13.5 nm10q先验证，不静默把q数压回8。也不把数学上允许的q数当作现有程序已经支持。

**B1：新模式/局部组件 → sector共同生产与完整q资格 → reference联合准入 → 原尺寸target一次完整迭代。** 每个sector只准备一次，数值及native分开持久化；避免用长时间global carrier前缀阻挡本可完成的sector。必要全局参考作用仍须建立并计费，不能靠延后构建假称已省去。以既有逐模式/row-tile存储保全进度，完成的资格按数学身份重开，不因新执行窗口全部作废。

条件满足后直接运行一场完整0.7 nm工程pilot，且保留live factor供同次参考/target使用。没有相同新物理的完整p6直接参考时，使用已建立的独立native/原方程/恢复/物理Gate，不要求先再做一次TB级p6直接解作为启动循环前提；相应精度authority仍有限。

如新0.7 nmq数、端口或局部缓存的真实成本超过预算，保留完整计数、已完成数组及具体主导对象；不得仅交“UNKNOWN/NOT_QUALIFIED”，不得凭cells或旧q0×数量承诺资源；不自动删模式、升cap或改PC。进一步架构选择交后续review，不盲目重跑同一失败条件。

## 6. 每一级必须保持的验收

| 层级 | 固定要求与可声称范围 |
|---|---|
| 原始方程 | 每场完整target A6真残差≤1e-6；迭代reported residual与独立原A6分列；恢复和释放后检查延续原门。 |
| q矩阵 | 两个不同非零全输入以及trace-only/port-only完整CSR/native作用误差≤1e-11；配对跨q泄漏使用对应非零原生主响应尺度，≤1e-11。保持独立B/D、原H、左右共轭及全部非零内部RHS。 |
| 准确q因子 | 每q fresh probe和同因子第二RHS的完整CSR真残差≤1e-10；精确MUMPS参数不扫描。 |
| 完整参考逆 | 继承已有原六类全空间startup、内部恢复和模式覆盖；strict与V15 PC准入各按原定义/门限报告，不能互换标签。 |
| 同离散A1/A2 | E/H/scaled curl及显著复振幅相对差≤1e-4；R/T/A/A_volume绝对差≤1e-5；逐模式功率绝对差≤1e-6。近零量另报入射尺度绝对差，不拟合整体相位。 |
| 本场物理 | abs(R+T+A_volume−1)≤1e-5，abs(A_balance−A_volume)≤1e-5；全通道及复场有限，独立分区体吸收，不能用A=1−R−T自己证明守恒。 |
| 最终离散精度 | 首场之后做单方向h/p与模式截断变化，至少分别考察y、x/z及倏逝尾部；工程目标R/T/A变化≤1e-4、显著通道功率/幅值≤1e-3、E相对L2≤5e-3、H≤1e-2；这些是测试间一致性目标，不是严格误差上界。 |
| 范围标签 | propagating-only或精度未闭合时分别保留MODE_TRUNCATION_UNQUALIFIED/ACCURACY_UNQUALIFIED；13.5通过、reference通过或小残差均不是0.7最终通过。 |

显著通道使用比较双方功率≥1e-8的并集，所有通道保留并报告弱级绝对差。网格变化时在同物理点/同材料侧或合法投影上比较，不相减未对齐的FE系数。旧φ0/50×25/n0 RCWA报告不能作为新结构的数值目标；仅在取得新条件且身份完整的RCWA结果时比较。

首次新方法/指标在response用简明语言说明解决哪一步、收益和边界；更完整公式沿既有源码/文档引用，不重复抄几十轮历史。

## 7. 资源、时间及执行授权

本轮授权主控在既有项目/工作站内切换本新分支、做必要参数化与定向测试，执行A1/A2，并在A出口和新资源门满足后连续进入B0/B1；不要求每个普通修复另等review。不是恢复Task40暂停服务，也不继承其未用完的窗口。ChatGPT本次不运行或操作工作站。

| 项目 | 本任务边界 |
|---|---|
| 物理整机目标 | 2,000,000,000,000 B，含操作系统/必要余量，不按2 TiB偷换 |
| 工作站任务cap | 不超过母Task40已用1.5 TiB＝1,649,267,441,664 B；并取真实host/ancestor/cgroup可用量的更紧约束 |
| host reserve | 至少既有64 GiB＝68,719,476,736 B；其他任务/系统占用另外实读，不能只减一次固定数就认为足够 |
| 小型13.5 nm计划 | 先预算，能在更低cap完成则使用更低值；单元数不保证LU空间，不为了达到上限而用满内存 |
| ABI/并行 | 母Task40资格化DOLFINx/PETSc complex128/int32、MPI1、数学线程1；实际版本/动态库读回；不移植Task39para的int64/PORD64合同 |
| 执行隔离 | 一次一个heavy，共享工作站排他检查包含邻项目；不停止邻任务或修改其监督器 |
| swap/测量 | task tree及dedicated cgroup swap=0，PSS/USS默认关闭记null；RSS/cgroup分别报告；宿主历史swap不冒充本任务活动 |
| 原生资源 | 原MUMPS排序/主元/精化/BLR/OOC策略不扫描；逐阶段INFOG与真实输入矩阵/因子共驻检查 |

正式run开始前由主控在当前实现的统一执行合同登记本任务、新case、source、输入及固定deadline，不复用旧window hash，不靠改标签绕过旧范围校验。每个正式单场从必要准备开始到required checker的固定总上限172800 s，其中数值截止171600 s、收口预留1200 s；这是本新任务的运行上限，不是完成时间预测。实现/定向测试及研究对照另计总账。已有流程不支持时仅参数化现有合同，不复制全套版本脚本。

同一场的分阶段resume保留原T0、累计费用和母子关系；无事务保障的数值填充从明确定义的清零点重启，不能对半成品重复+=。不同波长/同离散独立direct与iterative是不同正式case，各自计时；不能把分摊出去的必要producer/JIT/CSR/factor费用从最终0.7 nm冷账里删掉。warm成绩、开发费用和完整cold必需费用分别报告，缺项记UNKNOWN。

核心共驻账包含mesh/FE/MPC、实际局部类别/LU/恢复、所有q CSR及PETSc输入/转换、各factor、port B/D/H、Krylov、全场恢复、输出和checker；共享backing只计一次，文件mmap触页照计内存。优先在容量内保留准确因子；全驻留不准入时按实际成本限定固定保留集合，不能声称少量普通LRU槽在顺序全q遍历必然减少重分解。

真实身份、ABI、数值、RSS/任务swap、磁盘/索引溢出、监控失效或固定截止触发时停止受影响路径并清场；普通路径/字段/计数bug最小修复、冻结新source后继续，不热改运行源码、不刷新同场时钟、不降低门限。源码改变了数学算子则旧数组不能作为同算子继续；仅执行路径/窗口改变不得撤销数学上未受影响的资格。

## 8. 控制开发成本：先跑通，不先重构

只增加必要的新profile/配置和明确的参数适配。保留母线成果和旧失败；不全仓rename、不删除大数组、不建第二套mesh、PC、runner或数据平台。一个长期schema尽量服务多个task，task/review编号主要是记录值，不触发文件格式重写。

局部修复只运行失败回归及真实受影响调用链小集成，公共数值核心变化才增加直接依赖的数值验证。禁止默认“启动前全仓、结束后全仓、修复后再全仓”。保存失败输入优先定向复现；不为metadata重新做整场。完成当前授权步骤后连续前进，论文式完备测试和全仓合并整理放在首个合格0.7 nm场之后另议。

首个13.5 nm结果、同离散对照和首个0.7 nm场是主里程碑；测试数、commit数、mode前缀计数及方案文档本身不替代它们。

## 9. 提交与结果要求

推荐原子提交：①新物理/profile/调用链及定向测试；②13.5 nm直接/迭代和对照证据；③0.7 nm必要有界适配与实际run证据。每个formal源码clean，主控集中推送本分支，不amend、不强推、不写母分支/master。

Codex创建并维护 `response_v1.md`、`outcomes/summary.md`、`outcomes/test_summary.md`、`outcomes/records/run_index.json`、一份physics/mesh/mode manifest和简短handoff，并更新本分支 `docs/development_progress.md` 与 `docs/development_model_registry.md` 的新任务条目。继续既有命名，不每个小检查新建一份权威文件。

每次运行绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、ABI/数学参数、mesh/MPC/mode/hash、run_summary及artifact hashes；大数组/矩阵/因子/日志在ignored目录，只提交紧凑证据。不同source的结果分行，所有旧负结果保留。独立原A6、E/H、R/T/A_volume、衍射和near field齐全后才报对应scope的正式结果。

Response首屏回答：新几何/方位/S是否真实生效；13.5 direct/iterative各是否完成及差异；是否已进入0.7而非停在旧波长；真实mode/q数、主导内存和时间；0.7场/精度/2TB/48h各到哪一级；下一条可直接执行命令或具体阻塞。不能把13.5通过写成0.7可行性保证。

## 10. 首轮给Codex的执行摘要

保持现在的Codex项目名和主控/执行对话，不新建项目。母Task40已暂停；现场确认无活跃旧进程和干净工作树后，在同一目录切换 `task41extra_phi90_p50x50_g17x20`，从本任务书而非旧V33继续。不要重新clone整套项目，不改旧artifact。

新主实体为x/y周期50/50，x=[16.5,33.5]、y=[15,35]、z=[0,120]的居中Si块，基底/端口保持[-10,0]/130，掠角1°、方位90°、S；不自动叠加旧notch。沿Task40各波长材料，完整二维(m,n)模式，新q/twist与非平凡y-Bloch重新资格。旧q0/q4、572-N0、旧矩阵和旧RCWA数值不得借来宣布新问题通过。

先按A1/A2做原尺寸13.5 nm p6 direct与同离散p6参考预条件迭代。建议G13为10×10×14且Ny10真实匹配y=15/35，q数由实际网格和profile生成。原数学门通过后直接0.7 nm，不再插入5/3/2 nm；0.7 nm先新库存/方向离散/全资源准入，再一场原尺寸迭代。13.5 nm直接解只校验，不用于迭代初值。非零ky、S旋转、一般偶数q数及真实新材料是必经检查。

执行唯一正式入口 `python scripts/run_case.py input/task41extra_phi90_p50x50_g17x20/<已创建的单场文件>.dat`，由现有监督service运行。这个模板不是已存在DAT或支持所有新参数的声明；P0由实际代码生成direct/iterative两条真实命令并轻量验证路由。普通工程bug定向修复继续，不全仓测试、不大整理、不另造PC。

在既有工作站、最高1.5TiB task cap/至少64GiB host reserve、MPI1/math1、原complex128/int32与任务零swap范围登记新task/run合同；同场时钟不刷新。保留独立原A6、q/native、准确因子两RHS、恢复、物理及精度门。准备、生成与每步成本从实际函数计时，长模式流从第一次新生成就可靠持久化。主控集中提交本分支，先交新物理完整场，不合并master。

## 来源与阅读导航

以下均固定读取母线base `939ffe1f7b8d5a7406a01e25a716c08d36090078`。旧范围/窗口不作为本任务授权，数学内核与尚未解决的问题按真实范围继承。

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/docs/task40extra_0p7nm_engineering/response_v33.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/docs/task40extra_0p7nm_engineering/outcomes/summary.md
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/src/common/config_3d.py
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/src/common/modes_3d.py
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/input/task40extra_0p7nm_engineering/target_original_ny8_resource_pilot_v20.dat
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/docs/task40extra_0p7nm_engineering/review_report_v33.md
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/939ffe1f7b8d5a7406a01e25a716c08d36090078/src/solvers/task40_v10_p6_periodic_profile.py

首读根AGENTS、docs/AGENTS、repository_work_principles、当前任务书和本任务后续review/response；源模块改动读对应AGENTS。旧task40任务书、review33、response33、summary提供历史和继承边界，不要求为每次局部修复重复全文读取所有历史报告。
