# Task041 Review V9：面向 0.7 nm／2 TB／48 h 的无逐列 Schur 路线

## 0. 决定、身份和本轮要消除的 blocker

**接受已完成的 5 nm 数值、物理与本作业资源证据，不再重跑一场 52–56 h 的旧路线来证明它能解。当前主要 blocker 是大量侧区响应的总工作量，而不再是那两条已修复的响应配对。下一步先验证仓库已有的“固定线性反馈＋按需模态内迭代”，取消预先逐列构建完整模态 Schur；保留原 Hybrid 方程、准确侧区修正和最终验收。随后用真实 2 nm 尺寸校准，再推进有正式材料与离散资格的 0.7 nm。**

```text
repository              = Rookie1234567/MyFEniCS
working_branch          = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date             = 2026-10-06
reviewed_base_SHA       = df9c3b368516eb0a14574b2d9f9ea1d90ce32bf0
base_latest_commit      = fix(task041): support frozen rank CPU maps
previous_review         = review_report_v8.md
latest_response_present = response_v10.md; response_v11.md not yet present
newest_formal_evidence  = 2026-10-03 completed 5 nm A6 consumer
formal_baseline_source  = 5bfb813870182fda172f658c8f276f58318844a5
batch                   = task041_v9_hybrid_0p7nm_2tb_48h
response_required       = response_v11.md
execution               = H0 -> H1 -> H2 -> H3 -> H4
primary_candidate       = fixed_h6_modal_gmres_research, opt-in
swap_policy             = task041_v8_swap_observe_continue, unchanged
master_merge            = NOT_APPROVED
```

目标默认是一份冻结几何、单次入射／单偏振的完整计算：**从目标输入开始，经 QEP、PDE、恢复、核验到清理，<=172800 s**。已有 packet 的 warm-consumer 时间另列；开发和网格／模式资格研究的累计费用也另列。只证明 warm 求解低于48 h，不等于冷启动全过程达标。48 h是性能目标，不是用户要求的自动强杀线。

本报告明确授权在同一 Task041 分支验证上述新模态 PC、有限的物理反馈备选，以及0.7 nm材料／容量／离散阶梯；覆盖旧 task 的 exact-only、full_0p7nm 禁止及 V8 默认继续昂贵逐列 Schur 的顺序。本报告不改变普通默认，也不授权无证据地启动月级正式运行。已在健康运行的任务先只读核对，不为换 review 强杀或热改源码。

**适用范围是当前可作模态传播的 Hybrid 单胞，不是任意非可分三维 Full3D 已通过。** 长期通用路线仍须发展分布式、matrix-free、可扩展 Full3D iterative；不能把本轮特定结构的成功外推为任意三维成功。

## 1. 最新结果审阅：有完整解，但没有短波长性能资格

依据固定 base 下的 [V8终态outcome](outcomes/formal_5nm_2nm_v8.md)、[V8 record](outcomes/records/task041_v8_formal_5nm_2nm.json)、[summary](outcomes/summary.md)、[旧2 nm终态](outcomes/2nm_d1e_terminal_20260920.md)。

| 证据 | 实测／分类 | 本轮裁决 |
|---|---|---|
| 10月3日完成的5 nm | W、p6/h4、M480、MPI8×1、cell_condensed、A6融合体作用；1920/1920正式响应；五残差最大6.21753923942821e-11，原门5e-9 | 接受该固定离散数值、恢复和物理通过，不再追查已关闭的旧配对问题 |
| R/T/A/A_volume | 0.7331842733875563 / 0.00022009869572797534 / 0.2665956279167157 / 0.2665962726229846；closure6.447062688152982e-7 | 完整值保留；守恒不替代场／离散资格 |
| exact数值对照 | RTA最大绝对差6.534e-13、E/H最大相对差约2.296e-11、canonical约4.014e-10；600个外部通道及法向通量通过 | comparator总false来自旧exact producer资源证据缺失，不否定本次独立数值／资源门，不为补旧账重跑PDE |
| 本作业资源／终态 | authority43,966,554,112 B；tree43,415,531,520 B；cgroup历史peak43,975,204,864 B；job swap0；finalizer exit0、10项全真 | 在旧53,221,163,008 B cap内；resident、历史peak与swap分列 |
| 本次完整consumer时间 | 202124.563261555 s＝56.146 h；9月28日较早consumer为52.590 h | 最新实际更慢约6.76%，不满足24 h，连5 nm也未达48 h；有干扰时不把差值全归因于kernel |
| A6单独动作／真实两RHS | 体＋DtN局部降时约36–58%；两个17步RHS降时约9.6–9.8%；not_isolated | A6的sum-factorized实现已经存在且有数值证据；局部收益不代表完整流程收益 |
| 新2 nm | 尚未见启动／完整结果；旧D1e重复样本失败，0/4800正式响应 | 旧样本约102.6 s/内部步、约132.9日的全列算术只是历史诊断，不是新算法ETA |
| Modal-Anderson | 10月4日serial/MPI2 tiny algebra/stub通过；旧raw residual2.799失败保留 | 不等于真实FE／0.7nm／性能通过；复内积问题未证明是旧失败唯一原因 |
| fixed-H6模态GMRES | 代码已接入；当前已读outcome未提供该路线真实FE全场结果 | 从真实FE验证开始；不把最新CPU映射提交当求解结果 |

summary和项目级进度仍把9月28日52.59 h及旧public exit3置于前台，而专项outcome已更新到10月3日56.15 h且正常exit0。H0以运行身份核对并修正文档入口，保留两场历史；这不是再开计算的理由。未上传的本机结果须先生成小型hash-bound摘要，不能从代码存在推断已运行。

## 2. 原因与路线选择：必须减少总侧区工作，不只让一小段更快

用符号表示当前三块原系统（实际代码的符号、法向和phase保持不变）：

```math
\mathcal A
\begin{bmatrix}u_b\\u_t\\a\end{bmatrix}
=\begin{bmatrix}D_b&0&G_b\\0&D_t&G_t\\L_b&L_t&C\end{bmatrix}
\begin{bmatrix}u_b\\u_t\\a\end{bmatrix}=f,\qquad
S=C-L_bD_b^{-1}G_b-L_tD_t^{-1}G_t.
```

每侧有2M个模态输入，旧构建至少支付4M次侧区响应：5 nm为1920次，2 nm为4800次，另有repeat、准入和恢复费用。一个响应内部又有多次BAL_H、A6/A4、p4回代及精化。因此，“外层只有5步”不是计算便宜的证据。现有batch32是列容器／组织方式，不能算32路同时求解。

H0从两场已完成consumer的所有RHS审计一次性统计：正式／样本／outer／恢复的侧区调用、内部步数、p4回代／精化、各阶段wall与原始计时树；对齐A6、Q、A4检查、H6、传递、局部恢复、通信及监控开销。inclusive父子区间不能相加，rank-max之和不是端到端wall。至少解释56.15 h相对52.59 h的差别属于调用量、修正次数、单次成本、环境干扰还是未测，不能靠两条容易RHS推断整场。此步优先读现有日志，不重建factor。

### 2.1 主候选：固定线性模态反馈，不逐列求响应

沿用已实现的 `FixedH6ActiveTraceAction` 和 `_FixedH6ModalKrylovSystem`：

```math
B_s^{H}=J_s H_{6,s}J_s^H,\qquad
\widetilde S_Hv=Cv-L_bB_b^{H}G_bv-L_tB_t^{H}G_tv.
```

通俗地说：不预先把所有模态激励都送进昂贵侧区迭代；模态内迭代只对当前向量执行一个廉价、固定的侧区反馈。H6是正定辅助近似，不是磁场，也不是准确Maxwell逆。原LDU其他位置仍保留已资格化的BAL_H侧区逆；**没有把整个求解器退化成H6，也没有删除原方程的DtN。**

保持H6谱窗、次数、系数和映射在一次候选内固定；内层GMRES求的是线性替代块，不把它冒充真实Schur。沿用当前rtol1e-3、max_it8及10次总matmult的首个有界配置，并独立计算未缩放的替代块残差。原全局外层仍为right FGMRES，原A和f不变，最终原五残差与物理Gate照旧。[S1–S2]

**精度判断不能反过来要求替代Schur与真实Schur一致到1e-10，否则否定了预条件近似本身。** 对原D、G/L、P/PH、映射、同后端重复／线性和数据未变仍严格验证；替代块质量由原外层收敛、总工作量和最终物理输出裁决。FGMRES允许非线性PC，不意味着可以把任意非线性作用当作它要解的原A。

新分支不得调用全列Schur构建或隐式回退到4M响应。当前factory在fixed-H6之前仍调用原BAL_H侧区的early sampled repeat，可能预付大量昂贵响应：**本轮允许将这个旧PC专属前置检查改为新固定反馈的两次有界混合模态输入重复／线性检查，保持1e-10原数值精度；原侧区求解检查在实际被调用时保留。** 先在5 nm证明对象／公式一致，不把旧2 nm repeat失败改成PASS，也不关闭原全局残差。基线完整响应Schur若被调用，仍执行其原repeat合同。

### 2.2 只允许一个有条件的物理反馈备选

H6缺少物理粗层和真实DtN逆反馈，可能导致外层步数增加；不能保证它一定有效。若真实FE显示其收敛或总成本无优势，不扫描许多弱PC。允许复用现有准确p4因子、原物理A6和H6，构造**一次固定BAL_H作用**替代B_s^H：

```math
B_s^{\mathrm{bal}}=J_s\left[Q_s+(I-Q_sA_{6,s})H_{6,s}(I-A_{6,s}Q_s)\right]J_s^H.
```

这里是一次平衡修正，不是一次求到容差的侧区FGMRES。若作为内层MatMult，Q的精化次数和全部算子必须固定并通过线性／重复检查；基于RHS残差动态停止的逆不能假装固定线性算子。固定1次精化可作为首个诊断，达不到原A4精度即失败，不删除检查。其成本、额外物理反馈与实际收益单独比较，不与H6结果混称。

现有按需Anderson仍会在每次S评估中调用两个完整BAL_H侧区求解，保留为已有研究证据而非本轮第三条自动扫描路线。小代数复内积修复不应再次占用一周。若上述两候选均失败，提交实际外层轨迹、成本和最小缺失物理信息，暂停更大规模；不增加上万步去掩盖PC质量问题。

## 3. H0–H2：从已有结果连续推进真实 5 nm、2 nm

| 阶段 | 明确工作 | 合格后动作 |
|---|---|---|
| H0，旧数据审计 | 核对最新本机状态和运行SHA；完成1920项全量费用表及summary纠偏；读取已有新FE证据 | 冻结一个主候选，不重跑旧56 h基线 |
| H1，真实FE与5 nm | 最小正式调用链测试；一次必要13.5 nm真实Hybrid；继而原W/5 nm/p6h4/M480/MPI8，无全列Schur | 在同一运行中检查双侧驻留、原外层和全部物理，完成一场新5 nm |
| H2，真实2 nm | 复用对应旧QEP，W/2 nm/p6h1.5/M1200/MPI8；一次构造，先有限原方程迭代与成本观察 | 有效且容量安全则利用存活factor继续完整求解，不另退出重建 |
| H3，0.7 nm准备与缩减3D | 可在H1/H2准备阶段做无重负载的材料、实际通道、网格/M和容量计划；再做一个缩小几何的真实0.7 nm Hybrid | 明确reduced范围；不是目标单胞通过，也不以其总时间直接外推目标 |
| H4，目标规模0.7 nm | 满足第4–6节后执行冻结的原50×25 nm目标单胞；需要时先作一个有原因的中间尺度 | 同生命周期完成正式求解、原场、核验和清理；报告2 TB与48 h分别是否达标 |

H1不以小mesh性能替代真实5 nm。原13.5/5 nm准确参考和两个已完成解均复用；同数学源码已有合格新路线FE结果可直接接受。新模态PC的第一次真实FE是必要变化资格，不等于把旧迁移全部从头重测。

新5 nm先在原真实g上观察最多32个外层步骤或自然收敛，统计原五残差、完整昂贵侧区工作和替代作用。它是连续运行中的决策点，不是新的物理收敛上限：有显著下降、剩余成本可支付即可继续；停滞、nonfinite或明显无优势才切换一次备选。不能在每步保存全场或为了每项诊断再施加原A。原最大迭代保护不提高。

性能必须报告原始计数和加权工作：全部SideBalancedInverse调用、内部总步数、Q/p4回代／精化、H6与模态作用、C求解、outer和检查成本。**取消1920列但在内层偷偷执行同样数量侧区求解，不算成功。** 首阶段争取昂贵侧区总工作较旧基线减少至少4倍，作为架构目标而非捏造测得值；最终以全流程wall裁决，不要求事先预测必然<48 h才允许一次有界实测。

2 nm不再自动续开已知月级的旧4800列方法；本轮用新路线的实际工作判断。若已有健康旧作业，先报告真实状态，不擅自杀掉。对新路线先测真实尺寸，不用h10速度代替h1.5；测得成本仍明显无法接近48 h时，不新开更大的0.7 nm长跑，优先按第5节处理已识别瓶颈。

数学代码放在src/合适模块；沿用已有runner、service、rank映射和数据接口。不得再往巨型benchmark里堆一套新求解器、复制每波长脚本或新造通用审计体系。入口metadata修复用小调用链测试；已有数值结果只读派生重验，不重跑昂贵PDE。

## 4. 0.7 nm的物理、网格和模式不能靠5 nm结果代替

目标几何继承原50×25 nm周期、z=-10…130 nm、内部接口10/110 nm、1° grazing、phi=0、S入射；p6作为首选，双Floquet、complex128、完整DtN保持。缩小几何的pilot使用独立model_id，不冒充目标尺寸。Hybrid内部区域必须满足所用模态传播假设，不将任意非可分内部结构强行压成均匀传播段。

**材料：**5 nm仍用原W折射率0.99396854453+0.00435380777i；2 nm用原0.99880148307+0.000213688647i。0.7 nm必须取得该波长的W材料数据，记录来源版本、密度、能量／波长、插值规则、符号约定、delta/beta/n/epsilon及hash；不得借用2 nm值或把合成材料称为正式W。能量约1771.2 eV仅为换算，不是材料数据。优先已有合格材料库或可追溯CXRO/Henke等原始来源；材料暂不可得只阻塞0.7物理运行，5/2 nm继续。[S5]

**离散：**保持几何时，若假设h/λ不变，2→0.7 nm的体单元量约增23.3倍，表面量约增8.16倍；这些是derived尺度例子，不是准确网格需求。h=1.5×0.7/2=0.525 nm只能作为规划候选，不能直接宣布网格合格。逐方向网格取整、接口插入和真实拓扑由实际生成器盘点。

**通道与内部M分开：**按0.7 nm正式材料/入射重新枚举完整external keys；M按内部QEP选模与误差验证，不按外部传播通道数简单替代，也不直接把M1200沿波长平方外推为正式值。采用一个起点和相邻加密点分别检查h/p与M，必要时再加一个点，避免全笛卡尔扫描；两点变化只称局部收敛证据，不宣称严格误差上界。

新增0.7离散目标：在预先固定的物理坐标／材料侧和显著通道集合上，相邻合格离散的R/T/A/A_volume绝对变化<=1e-4，selected复E/H与显著复衍射幅值相对变化<=1e-3，能量／体吸收原门仍<=1e-5；原参考若要求更严则从严。避开奇异边角的点值要声明，弱级保留绝对量，不凭低R/T掩盖大相对误差。这些是本轮工程精度目标，与同一离散算法对照1e-8等门完全不同。未达到时可以给出PDE结果，但不能标“accuracy-qualified 0.7 nm”。

## 5. 2 TB／48 h必须有逐对象、逐阶段的容量和时间模型

取消全列Schur只消除一个大成本，**不会消除QEP、模态基、两侧p4因子和端口存储**。H0/H2建立以下表，不能只用“5 nm约44 GB×某倍率”预测整机峰：

| 分项 | 必须盘点的实际量 | 有超预算风险时的优先改进 |
|---|---|---|
| p6/p4 FE与局部恢复 | owned/ghost/trace/interior行、cell-class数据、局部LU与缓存、临时数组、MPI副本 | 固定布局复用、有界批处理；保持无global p6 factor |
| p4因子 | 实际凝聚rows/nnz、factor entries/bytes、setup与每次回代、原A4精化 | 先保留已有效的准确逆；不因“p4”就假定可无限扩展 |
| QEP | 原多项式维度、显式线性化与shift-invert因子、nev/ncv/mpd、求模时间、全过程workspace | 必须时才开发TOAR紧致基或分批选模；shift因子和多模式数量仍可能主导 |
| 选模基与接口 | 16×N_cross×N_selected字节载荷及副本、完整投影/traction、传递map | producer与PDE错峰；已选packet只读共享／分布式owned数据，流式投影 |
| 模态C与内层空间 | C的(2M)^2条目、负向trace映射、内部修正、C LU与条件估计workspace、每rank副本 | 按实测预算保留小C或分布式/结构化作用；禁止假定C为对角 |
| exterior DtN | 实际trace×channel矩阵、索引、临时buffer、W/K及模式副本 | 原keys不变下有界streaming/matrix-free，不形成巨大稠密乘积 |
| outer／恢复／输出 | FGMRES基向量、残差检查、recovery packet、场与衍射输出 | 分布式数据、release-before-recovery，避免全场allgather |

当前C由negative_trace_to_positive、传播因子以及内部修正组成；不能为加速只留下单位/对角项。只在证明特殊结构与完整原C等价后使用逐模态小块求解。C LU目前最后rank持有，但C本体仍有复制；M增大后owner瓶颈、O(M^3)分解及条件数计算都要入账。

SLEPc TOAR通过隐式线性化和紧致基降低多项式特征问题存储；大量特征对时要同时审计nev/ncv/mpd，而不是一味增加ncv。它不保证大量所需模式或shift因子变便宜，也不能把有损Maxwell误设为Hermitian/STOAR适用问题。[S3–S4] 如需修改QEP，只选当前最大超预算项做一组实现，保留原多项式残差、传播方向/通量与簇子空间、全部被选模式及packet一致性验证；禁止把截少模式当作算同一问题。

时间模型使用实际计数而非外层步数：

```math
T_{\rm cold}=T_{\rm QEP}+T_{\rm FE/PC}+\sum_s\sum_{j=1}^{N_s}T_{{\rm side},s,j}
+\sum_{k=1}^{N_{\widetilde S}}T_{\widetilde S,k}
+T_{\rm outer\ other}+T_{\rm recovery/check/output/cleanup}.
```

区间互斥计账，完整wall作总核对；原A和PC内部包含关系必须去重。规划表同时给central与保守情景及假设，用5 nm全量统计、2 nm实际短段和目标规模库存校准。没有数据的项写unknown，不自动填0；特别是0.7 QEP预算未知时不能宣称48 h可行。争取保守情景<=38.4 h以留下20%执行余量，这是规划余量，不是已经证明的时间上界。

若只做A6/A4等局部优化，先检查未优化部分的时间底线；即使局部无限快，整体仍有上限。已有A6融合代码应复用；至多再优化两项由真实计时决定的热点，如A4物理残差kernel、H6/传递/恢复或DtN。不能将两个17步RHS或无人隔离的microbenchmark当全量提速。MFEM资料支持partial assembly与张量作用的机制，不提供本程序提速倍数。[S6]

若0.7瓶颈是p4 factor超预算，先以数据明确该blocker；本轮不再盲扫ILU、不自动引入另一个global coarse LU。选择性低内存强逆的迁移须有相关已资格化donor与最小接口证明；否则交下一项边界明确的coarse-solver任务，而不是偷偷降低p4精度。

## 6. 资源、正式准入和有限执行边界

**2 TB是物理容量，不是程序RSS许可。** 首先记录实际MemTotal、各NUMA节点可用量和单位。为本轮“2 TB”严格声明，采用B_phys=min(实测MemTotal,2,000,000,000,000 B)作规划；机器若实际为2 TiB，另报该口径，不悄悄把多出的容量用于2 TB达标。整机reserve至少max(0.2×B_phys,412,316,860,416 B)，0.7新作业cap不得大于B_phys-reserve；已有5 nm cap53,221,163,008 B、2 nm旧cap及实际节点限制取更严值。

默认继续socket0/node0、MPI8×1，沿最新已支持的冻结rank CPU map，逐rank核对真实绑定与private pages。CPU0/node0运行不能使用node1容量作为可用量证明。48个物理核的硬件数量不等于当前用了48核；不从8核时间简单除以6。**node1尚未资格化时，不强制等它修好才做5/2nm，但也不能宣称已经利用整机2 TB。** 本轮不自动改BIOS、拆DIMM、启用node1或启动另一轮硬件排障。

swap严格继承V8：出现、增长或缺测本身不拒绝启动、不停止、不判数值失败；记录global/job/cgroup及真实驻留。swap不计入可用RAM，不能通过换出页隐藏超预算工作集；对“2 TB达标”同时披露可测的resident＋job swap存储诊断，缺失时资格限定而非捏造0。OOM、真实cap/reserve越界、硬件错误、磁盘不足和明确数值失败仍受控停止，不通过降低资源reserve换结果。

H4目标规模准入要有：正式0.7材料、实际external keys、局部h/M资格或明确先行pilot标签、目标库存、可支付时间情景、5 nm新路线及真实2 nm证明。不是要求预先有完整0.7解才准启动；这些前置证据通过后，双侧驻留与最终场资格在同一正式运行中取得。若测量已明确显示月级成本，不启动更大的盲长跑。48 h到时若健康运行，报告目标未达、原残差和剩余工作，不强杀重来；用户可随时停止。

本批主候选＋一个备选，13.5真实新路线回归最多一场必要运行；5 nm每个候选最多一次连续评估，不另重跑旧基线；2 nm先一个真实尺寸试算并在同生命周期延续；0.7一个缩减pilot及有依据的局部离散相邻点，再一场目标规模计算。明确实现事故允许一次最小受影响重试，费用/负证据保留；不要每修schema就跑全套。材料/容量/PC失败只停止受影响分支，其他可安全完成的证据继续，不轻易全任务停摆。

## 7. 数值Gate与原方程身份

| 检查对象 | 要求 |
|---|---|
| 原reported/global/bottom/top/modal residual | 全部<=5e-9，原完整Hybrid算子独立重算 |
| projection／traction／external-q | <=1e-8／1e-8／1e-10，原法向与phase |
| 准确p4作用 | 原physical/augmented<=1e-10；已资格化5nm侧区target5e-13、最多2次修正保持；2/0.7候选不能宣称自动通过 |
| 原D/P/PH/映射、重复、固定反馈线性 | 沿原动作门；新固定反馈重复/线性<=1e-10，复数系数与零/近零输入分开 |
| 替代模态内问题 | 检查实际固定S_H或S_bal的未缩放残差、迭代和真实调用预算；不拿C缩放残差替代；不当成原Schur精度证明 |
| 相同离散对5nm现有authority | R/T/A/A_volume绝对差<=1e-8；selected复E/H<=1e-6、canonical<=1e-5、显著衍射复幅值/功率<=1e-6、normal flux<=1e-4 |
| 吸收／守恒 | abs(A_balance-A_volume)、abs(R+T+A_volume-1)<=1e-5；全部衍射级保留 |
| 2/0.7无完整参考 | 如实注明，以原残差、独立物理核验及第4节离散资格分层裁决，不借用5nm参考或新建巨大p6直接因子 |

所有正式PDE仍用 `python scripts/run_case.py <one-case.dat>` 及既有MPI/service路径。每个case保存input_original、resolved_config、run_manifest、input/physical/source SHA、环境、MPI/线程、material/mesh/mode identities、run_summary与artifact hashes。新算法改的是PC，不能在恢复或验收时悄悄换原方程来让结果通过。

## 8. 交付、Git与避免再次被流程本身拖住

立即以旧数据形成一张“56 h花在哪里”的表及最新快照；随后先交真实FE无列求解结果，而不是只交tiny通过数。主控与执行可沿仓库内部审核，但满足本报告条件的阶段转移不重复向用户索要授权。

输出 `response_v11.md`、`outcomes/hybrid_0p7nm_2tb_48h_v9.md` 和一个小型机器record；同步summary、test_summary、development_progress、development_model_registry。至少包含：选用候选和实际公式、原残差/完整物理、总侧区及p4/H6调用、setup/QEP/outer/recovery完整时间、每rank复制与peak、48 h cold/warm分别状态、0.7材料/网格/M资格、node0限制及唯一剩余blocker。

不要把diagnostic qualification=false当已测数学失败；不要用旧exact producer缺资源记录否定新作业自己的资源证据；也不得反过来伪造旧reference资源通过。运行中仅允许预先登记的文档与结果更新，runtime source与document HEAD分列；结束HEAD因获准文档变化而不同，不得再次单独使有效PDE失败。通过固定代码/输入manifest与allowlist判定，真正代码变化仍保留失败。

不为每个列写全量审计数组；原检查已有的标量用于汇总。长阶段沿已有轻量状态至少每小时记录一次，运行开始/结束/真实blocker及时推送：wave/p/h/M、PC、runtime SHA、unit/PID/starttime、阶段、工作计数、残差、wall和资源。没有现场新结果就说未上传，不用旧summary假装实时状态。

普通提交顺序：最新证据整理；主候选最小接线/测试；必要的一次备选或热点修正；真实5/2nm结果；0.7材料/容量与pilot/目标结果。只在当前Task041分支提交，不整体merge donor、不改master、不amend/force-push、不删除负结果。没有最终review和用户merge授权，不合并。

本轮最低有价值交付是**真实5nm无逐列路线的完整收敛与费用结论＋真实2nm容量/工作量＋0.7正式材料与48h逐项缺口**；达成后按准入连续推进0.7，不把最低交付当提前停止理由。若0.7/2TB/48h未达，明确是哪项measured/derived/predicted阻塞和需要减少多少成本，不能因目标困难放弃，也不能保证尚未实测的加速。

## 9. 依据

固定仓库base为本报告§0 SHA。已读根/文档AGENTS、仓库工作原则、task及最新review；任务目录无另列补充任务书，历次review覆盖保留。最新response仍为V10，与10月3日专项outcome时间不同，按运行身份采用最新记录。

主要代码：`hybrid_fem_modal_block_ldu.py`（全列/Anderson/fixed-H6三条真实分支）；`physical_balanced_side_inverse.py`（FixedH6ActiveTraceAction及原侧区修正）；`hybrid_fem_modal_augmented_direct.py`（真实C、modal owner）；`physical_balanced_fused_volume.py`及已发表A6结果；`p4_cell_condensed_inverse.py`与原恢复/计时接口。当前rank映射提交不是新的数值结果。本次只提交review，未执行工作站PDE。

外部原始资料于2026-10-06核对，API能力以工作站已安装版本为准，不为本任务自动升级ABI：

- [S1：PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：非线性PC与right-preconditioning支持，不保证任意PC收敛。
- [S2：PETSc KSP手册](https://petsc.org/release/manual/ksp/)：原线性算子与PC角色、右预条件原残差。
- [S3：SLEPc TOAR](https://slepc.upv.es/release/manualpages/PEP/PEPTOAR.html)：隐式线性化与紧致Krylov基。
- [S4：SLEPc PEPSetDimensions](https://slepc.upv.es/release/manualpages/PEP/PEPSetDimensions.html)：nev/ncv/mpd的不同成本角色。
- [S5：LBNL CXRO光学常数](https://henke.lbl.gov/optical_constants/getdb.html)：材料、密度、能量输入的可追溯要求；此链接不是已经取得0.7nm W数值。
- [S6：MFEM高阶partial assembly](https://mfem.org/performance/)：局部张量作用与存储机制；不把其他库基准当本程序实测。
