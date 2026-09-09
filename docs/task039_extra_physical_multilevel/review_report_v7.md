# Task39extra Review V7：停止单右端项延长，以完整 p6 裁决有界低存储粗逆

## 0. 审阅结论与本轮授权

```text
repository          = Rookie1234567/MyFEniCS
branch              = task39extra
review_date         = 2026-09-09
reviewed_HEAD       = f3b3a5f869657b28050304a27820e335bcde5142
original_task_base  = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_review     = review_report_v6.md
latest_response     = response_v7.md (V5成功；V6补充研究尚无response_v8)
execution           = J0 -> J1 -> J2(A) -> conditional J3(B) -> conditional J4(notch) -> J5
response_required   = response_v8.md
new_outer_profiles  = bounded_entity16_v7 / bounded_projected_seq2_16_v7
ordinary_default    = unchanged
master_merge        = NOT_APPROVED
```

**本轮要消除的 blocker：已有低存储 p4 组件显著改善了部分难误差，但尚未证明它们在有限内部工作下能支撑完整 p6 求解。现在不再等待每次 p4 内部方程达到 1e-4，先把改进后的组件接回成功的 BAL_H，由原始 p6 方程、物理输出和完整资源成本裁决。**

这不是取消内部正确性，也不是宣布任意粗糙修正都有效。允许返回的是：针对正确的 A4 和当前 RHS，在固定预算内得到、有限、约束合法且可核查残差的近似解。外层仍必须达到原 A6 的 1e-6，并通过原有物理 Gate。

本轮用户明确要求新 review 及连续推进。本文取代 V6/补充诊断中“继续单 RHS、不得进入外层、等待再审”的阶段性限制；旧结果与阈值不追溯改判。V6 本来就允许有限不精确粗逆进入外层，且最初的递归 H4/p2 已在 G2 实际失败。**本轮新增的是使用后续已改善的高阶实体组件、限制内层工作、增加一个唯一跨块组合备选并完成外层裁决，不是原样重跑旧 G2。**

最终目标仍为约 2 TB 整机内存内的 0.7 nm、complex128、Nedelec H(curl)、双 Floquet、Fourier-DtN、周期单胞内任意非可分三维散射。本批只运行已有 13.5 nm 两个固定离散模型，不授权短波重型计算。

## 1. 接受哪些证据，关闭哪些重复工作

表内均为已提交记录，不是本审阅新测量；不同计时、RSS与输入范围不得拼成同一性能曲线。

| 对象 / 单位 | 已测结果与证据 | 本次裁决 |
|---|---|---|
| V5 BAL_H + 准确 p4 LU，原始 / notch | 外层564 / 576步，true约9.9323e-7 / 9.3517e-7；完整场和80通道比较通过；树RSS约3.466 / 3.601 GB。[V5结果](outcomes/balanced_coupling_v5.md) | 成功基线保留；不重跑本机旧基线或直接参考 |
| V6最初递归 H4/p2 | 原始外层13步、约1800s、true=0.667843；不是新实体组件。[V6结果](outcomes/coarse_inverse_replacement_v6.md) | 该失败保留，不重跑、不称为低内存成功 |
| 高阶边/面实体 + owner-route | 一个固定g1，60步、true=0.0080024124，M0/curl场差约0.002381 / 0.002380；树RSS约0.911 GB。source9dbf12355e6e6c7eac23d055c12da4e7eda2a7d8 | 有实质正信号，但只是内部组件；作为首选接回外层 |
| projected full252 | 一个内部RHS分段累计256步到3.7381775e-4，未达1e-4；不是不间断零初值曲线。[最新诊断](outcomes/recursive_p4_complement_diagnostic_v6.md) | 不再延长到512/1024步；不以更复杂、更新为由认定优于实体版 |
| 局部求解与跨块拆分 | 固定方向局部求解约舍入级；块外耦合与权重项存在抵消；系数范数不是场L2 | 只支持一次跨块组合试验，不改权重、不重新提高局部LU精度 |
| full252构建 | 1603.835402s、36,288次S列求解、252个局部LU | 计入构建账；不能以接续进程约0.47 GB冒充完整solver峰值 |

保留 V5 原始非法输出平面后的同解恢复链，及 notch 参考448页全系统换出归因未定的限制，不重复运行以清洗历史。上述证据入口同时包括[最新summary](outcomes/summary.md)、[V7回应](response_v7.md)、[补空间compact](outcomes/records/recursive_p4_complement_diagnostic_v6.json)。

本批关闭：单 RHS 接续、三份旧投影重算、fine reference 重建、原 H4/p2长跑、HI容差扫描、PML/Robin/普通ILU扫描、p5/新粗空间、扩大restart、重新调查系统时钟。没有新授权不增加第三个外层候选。

## 2. 冻结物理、外层与接口身份

| 对象 | 固定合同 |
|---|---|
| 原始模型 | 13.5 nm、grazing1度、azimuth0度、s；50 x 25 nm周期，z=-10到130 nm；Si/air、原损耗；p6/h10，252六面体 |
| fine rows | p6独立164592 / 存储173802；不改变约束坐标约定 |
| middle rows | p4独立48960 / 存储53084；原80个有序DtN模式，不让低层自行删模式 |
| 原physical SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| 原mode SHA | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| notch | 复用V5已解析的8个cell keys及其独立physical SHA；同尺寸不同材料分布，各自匹配自己的参考 |
| fine A6 / b | 原full-space、matrix-free真实作用；原积分、双Floquet、DtN、incident RHS不变 |
| 外层 | right FGMRES32、max2048、zero start；保留BAL_H调用顺序、H6、P64/P64H；不恢复逐段MR |
| 输出 | V5合法外部探针127.5 / -7.5 nm；完整E/H、near field、R/T/A/A_volume、80复振幅/功率 |
| 执行环境 | 当前已资格化Linux、complex128、记录IntType、MPI1/线程1；不擅自升级ABI或套用MPI1索引到MPI2 |

formal继续通过 `python scripts/run_case.py input/path/to/case.dat`。新profile、全部内部参数和缓存身份进入dat/resolved_config/manifest；不得让正式外层依赖只接受一个保存g1的临时诊断runner。

未知量全保留在p6；辅助p4组件内已有局部消元不等于把fine生产路径改回静态凝聚。不得重新装配全局p6/p4 AIJ、全局p4 LU或全局稠密T。参考答案只用于测量，不能进入PC、初值、分组或方向构造。

## 3. 内层可以未达目标，但每次返回必须可解释

一次外层PC按以下函数流程定义，I4是算法而不一定是固定线性矩阵：

```text
g1 = P64H(q)
c1, eps1 = I4(g1)             # zero start; eps1 = g1 - A4(c1)
zc = P64(c1)
s  = H6(q - A6(zc))
g2 = P64H(A6(s))
c2, eps2 = I4(g2)             # new RHS; do not reuse old g2 or c1
z  = zc + s - P64(c2)
return z
```

由正确的Galerkin身份得到：

```math
P_{64}^{H}(q-A_6z)=\varepsilon_1-\varepsilon_2.
```

检查的是恒等式左右的闭合，不要求右边为零。每次保存两份原A4相对残差、绝对残差范数、RHS范数、停止原因、内部步数和成本；不能仅报相对残差而忽略第二份RHS的尺度。正式首PC、每32次PC及退出前核对实际平衡缺陷，操作尺度相对闭合限1e-8，成本计入。fine原A6仍准确，不能把内层误差混入fine矩阵作用。

### 固定I4工作合同：两条路线相同

| 项目 | 本轮值 / 含义 |
|---|---|
| 解的方程 | 真实 A4 c=g，不是B4、S或投影残差替代 |
| 内部方法 | right FGMRES，restart16、最多16步，每个RHS从零开始 |
| 1e-4 | 仅提前终止目标与质量标签，不是外层入场要求；原1e-4负结果不改判 |
| 每次I4费用 | 30s目标上限，含末次native A4检查；25s开始请求安全返回并预留退出工作。超出30s如实记账，不暗中增加预算；外层watchdog始终优先 |
| 返回值 | 已完成合法Krylov步对应的有限近似及原A4残差；未达目标标`INNER_APPROXIMATE_RETURN`，不得伪装成`CONVERGED` |
| 不允许 | 达到16步后继续、按参考误差调整停止、恢复旧x64/x256、跨RHS保存解作热启动、外层途中换profile/改内层步数 |

16步是一轮受限的工程投入选择，不声称最优。真实回调成本可能使少于16步即到时间线，记录实际步数。连续两次I4未完成任何合法方向，或连续三次超过30s，按`INNER_COST_BLOCKED`停止该路线，而不是无限返回零或无限越界。零RHS可直接返回零并单列，不计为上述异常。

非有限、共享/约束污染、错误映射、真实算子不一致、真正Krylov breakdown无可用修正、底层要求的正确性失效，不能冒充“允许不精确”；保存最小证据并停止受影响路线。达到软精度目标与达到资源硬线是两回事。

底层S/p2仍是参考型局部组件依赖：保持原真实残差要求、至多两次已授权同因子精化和失败前保存；不把底层精确块恒等式静默改成不精确版本。本批不同时重设计底层。

## 4. 路线A：现成实体组件先进入外层，不等另一个新算法

**目的：检验已有高阶边/面纠错作用，截断为便宜的粗逆后，是否已经足以帮助完整p6。**

复用source9dbf12355e6e6c7eac23d055c12da4e7eda2a7d8已测的`physical_owner_route_trace_component_v1`数学作用：通用CU、内部响应、792个edge/774个face实体修正、原权重与双侧反馈、cached exact volume及原DtN、固定MPI1 owner路由。当前HEAD中的等价实现可复用，但需有身份桥。不要把它换回最初的H4/p2，也不要因full252更新就默认改选full252。

变化只限：通用多RHS接口、正式p6接线、按第3节把I4限制为16步/30s、必要的inexact账本。构建一次、多个RHS复用；正式notch则按自己的材料重新构建，不复用原始物理因子。

路线A完成必要正确性检查后**直接运行J2原始p6**。不得先实现路线B、扩大诊断或等待所有内部RHS达到1e-4。若A原始和notch达到目标，B记`not_run_goal_met`。

## 5. 唯一备选B：projected full252的两组顺序修正

仅在A原始未取得本批完整目标、且不存在共同A/P/资源监管错误时实施B。它针对已记录的块间耦合；不是宣称加法必然差、乘法必然好。

复用已有252个投影局部块、每块144方向、原局部LU和两侧重数平方根权重。由原structured mesh生成规范cell坐标索引(i,j,k)，组号固定为 `(i+j+k) % 2`，按0组后1组，组内仍加法；不根据参考场、材料标签、残差大小挑顺序，不反扫，不再测试其他组数。周期接缝和端口造成组内耦合是允许存在的，**两组不表示代数独立或无耦合着色**。

令T表示现有固定方向拆分中所用的完整高阶互补系数作用；它包括已消去内部响应、粗层反馈及原DtN。令M0、M1分别是两组原局部逆的加法作用，原两侧权重保持，不在组内重新归一化。这里M0表示第0组局部逆，不是旧诊断的质量矩阵。

```math
\begin{aligned}
d_0&=M_0 f,\\
f_1&=f-Td_0,\\
d_1&=M_1 f_1,\\
z_T&=d_0+d_1.
\end{aligned}
```

亦即：

```math
M_{\mathrm{seq2}}=M_0+M_1-M_1TM_0.
```

这使后一组看到前一组已产生的影响。一次作用仍各局部块只回代一次，相比原加法增加一次完整T作用及有限工作向量；不得变成每252块一次全局更新。T只能按现有全物理作用和已资格化左右映射计算，不能换成未投影体矩阵、块对角或仅近邻矩阵来省时间。非Hermitian左右耦合不得假定互为伴随。

复用已有full252的lift/restriction和CU组合，只替换互补系数逆的apply，再按第3节有限I4接回p6。新增小复数重叠fixture核对顺序公式；原网格固定输入比较新apply与显式两组流程的一致性，不要求它等于旧加法输出。附带记录两者成本与作用；这不是新增第三个完整PDE路线。

原始保存块可按hash及完整物理/数值身份加载。不同材料notch不能加载原始投影块；允许每个实际需要的模型至多一次有界setup，按现有实现构造并记录全部S列求解、峰值和时间。若构建超预算，标`SETUP_COST_BLOCKED`，不把缺失块补零、不扩大空间或反复改缓存分类。全局粗响应使局部有效块未必能按几何类直接复用，不能未经逐位/作用资格就合并252块。

**A与B并非只差一个开关；B必须另外给出与原full252加法的一次有限同输入对照，避免把实体版和投影块版的差异全归功于顺序。**不追加原full252长跑。

## 6. J0/J1：一批有限准入，之后必须接回真实p6

J0按根/docs AGENTS与工作原则核对branch/HEAD/upstream/canonical worktree，读取本task、V6/V7、最新response/summary与相关代码。新提交不授权合并其他分支。现有原始/notch参考、旧误差/残差包、模式输出和缓存按hash复用；已保存的目标解只由评价端读取，PC对象不持有它。

每条真正实施路线只做以下合并批次：

- 一个合并focused测试：复共轭、zero RHS、slave/owner、合法截断返回、异常隔离、eps记账、输入不变、重复新RHS不串状态；B增加两组公式和重叠权重测试。
- 原始网格上，复用旧资格桥；只重核改动影响的native/cached A4、转移及完整作用，限固定少量向量。数学等价限沿原1e-10，cached对native沿已用1e-11；B改变的是PC，不对B要求等于A。
- 最多两次完整新BAL_H调用，输入用已存A2R160和LIGHT448的真实q。每次实际计算新的反馈g2，共四次I4；记录场与残差、成本和平衡。旧准确g2可作记录对照，但不能代替新c1产生的实际g2。

不要求两次调用或四次I4达到1e-4，不要求一次PC残差下降，不要求参考场误差达到人为倍数才准进入J2/J3。正确性、有限可用方向、资源和基本成本准入合格即运行外层。两次完整调用中至少一次成本不超过90s；若两次均超90s，仅允许一次最多8步/600s的p6接线与成本终审，随后该路线以`COST_NOT_VIABLE_AT_FIXED_BUDGET`收口，不扩展长跑。

不重做质量投影、谱分析、全场reference、全252列的重复构建/全面hash审计。缺文件只恢复实际需要的已绑定artifact；恢复不了就明确受影响项，不猜身份。旧raw的完整审计已存在，普通复用核对将加载的文件即可。

## 7. J2/J3/J4：以完整外层进展和目标输出裁决

### 原始模型，每条路线最多一次零初值求解

外层FGMRES32/max2048，持续使用同一KSP；每8步和退出前计算原A6真残差、每32步保存solution-only checkpoint。中间观测和筛选不清空Krylov空间、不用参考热启动。

以 rho_k 表示原始rhs归一化的真实残差。128步或保守solve1800s先到时作一次投入判断：

```text
已达到1e-6：直接进入完整输出检查；
否则继续条件为：
  rho <= 1e-2；或
  已有至少16步，rho <= 0.30，且最后两个完整8步区间均下降，
  两个缩比的几何平均 <= 0.80。
其余：保存当前解及成本，NORMAL_SCREEN_STOP；不宣布永不收敛。
```

这是本轮固定的工程投入规则，不是收敛定理。使用最近三个8步节点计算两段缩比，不用尚未完成的reported residual，也不要求一定完成两个32步restart周期。

获准继续时，solve到5400s再作一次有限检查：未达到1e-6且真实残差仍大于1e-3，保存结果并按`PROGRESS_INSUFFICIENT_AT_MID_BUDGET`退出；否则在同一KSP继续至本轮完整上限。该线不追溯用于旧V5。每场最多solve10800s/workflow14400s/2048步，先到者终止；全部内层、监控、保存成本计入，退出越线如实标注。安全超时从内部回调可见，不等巨型PC结束才发现已超外层预算。

A原始不通过则自动进唯一B；B不通过则收口，不等用户再审每个小步骤。不因内部未达1e-4提前杀死外层；也不因内部残差很小就允许外层无进展地续跑。

### 第一个原始通过者立即运行唯一notch

同一内部工作量、同一算法参数、同一H6、同一外层；notch有自己的A4、S与局部因子。先完成各模型setup准入，引用已有各自reference；输出门槛如下。notch同样使用上述进展/完整预算，不特殊调参。

本批最多两次原始求解和一次notch。A原始通过则先notch，不先跑B；notch若不通过，报告几何适用性缺口并结束本批，不为缺口换第三方案、不在缺口上扫参数。原始和notch都通过即提前完成研究目标，其余路线not_run_goal_met。

| 最终Gate | 目标 / 比较方式 |
|---|---|
| 原A6方程 | 完整真实相对残差不高于1e-6 |
| 同模型参考场 | L2、scaled-curl相对差不高于1e-4；selected E/H与near field按同坐标比较，近零量另报绝对差；不拟合相位 |
| R/T/A/A_volume | 各自对同模型参考绝对差不高于1e-5；原始与notch不互作误差参考 |
| 独立功率闭合 | R+T+A_volume与1之差、A与A_volume之差均不高于1e-5 |
| 全部80模式 | 复振幅向量相对差不高于1e-4，逐通道功率最大绝对差不高于1e-6；保留新激发通道 |
| 资源 | 同期完整进程树RSS、安全余量、zero-swap和全部生命周期记录合格；不得用单I4峰值替代 |

只有目标残差合格的场可产生official输出。若收敛后仅输出工程问题，允许在剩余预算内从同一解恢复一次，不重解。原始/notch参考数组已经存在，不授权新增直接参考。

## 8. 资源、总成本和停止边界

本机继续动态安全线：effective_total取物理/有效cgroup较小值；reserve=max(4GiB,15% effective_total)；cap=min(12,000,000,000B,effective_available-reserve)，运行中维持余量，一次一个heavy。采用已稳定的保守经过时间政策，UTC跳变记录但不单独作为数学错误；不改系统校时。job swap或系统新增swap活动按既有合同安全停止并分类，归因不明不得伪写zero-swap或数学失败。

全局p4/p6矩阵与因子禁止；S/p2增广底层保持8192行、其矩阵/转换/factor/工作集预审512MiB上限。局部factor、bubble/trace、owner索引和相关附加缓存另设256MiB数值/索引载荷上限，并纳入总live-set；这些是本机pilot上限，不可随波长任意放大。任何旧缓存已有更严的正确性要求继续保留。新路线不能同时留着A/B两套PC或旧p4 LU；顺序释放。

完整峰值计入p6外层V/Z、I4基向量、native及cached动作共存、H6、S因子/矩阵、所有局部对象、编译器和后处理。RSS与derived bytes分列，reference和候选峰值不相加；allocator保留导致RSS不下降时如实说明，不伪称全部已释放。

| 计算项 | 本轮上限；非日历时间估计 |
|---|---|
| A接线、focused、setup和有限控制 | 合计3600s；达到后不得用剩余时间开新诊断 |
| 条件B实现验证、setup和有限控制 | 合计5400s；原始已有投影块优先复用 |
| 原始PDE | A一次、条件B一次；各solve10800s / workflow14400s |
| 条件notch | 至多一次；solve10800s / workflow14400s，notch setup计入自身workflow |
| 所有实际计算总账 | 43200s；子/父嵌套不重复；本轮失败、编译、测试、恢复均计入，各项不是保证可叠加使用 |
| 禁止新增 | 单g1长跑、512/1024步接续、第三PC、fine direct、旧基线复跑、工作站/5nm/0.7nm heavy |

缓存加载耗时和已有构建成本分别报告；首次cold费用不隐去，notch不能凭原始缓存假装免费。当前full252构建36,288次全局S列求解是扩展债务，即使本轮成功也须明示；不以有界局部因子名称冒称factorization-free。

## 9. J5：必须给出完整替换判断并终止本批

提交统一`response_v8.md`，在同一回应中收口V6及其补充研究，再单列V7新批结果；没有response_v8不代表必须先停下来写一轮再执行。本轮正常失败按预定分流直到J5，一般不逐项停审。

更新summary、`docs/development_progress.md`、`docs/development_model_registry.md`、run_index和workstation_handoff。新增中心说明建议`outcomes/bounded_inexact_outer_v7.md`与对应compact，最多这一套中心材料，不给每个检查再建新任务文档。summary以一张最新表为入口，历史阶段保留在原报告或明确历史区，不再用连续“最新/待审”段落掩盖当前终态。

| 必须回应的问题 | 不能用什么替代 |
|---|---|
| 哪个完整p6模型实际求解，true与场/功率如何？ | 内部一个g1达标或局部测试通过数 |
| 是否移除了p4全局矩阵/因子，总RSS节省多少？ | 只报告0.47/0.91 GB组件峰值 |
| 每次粗逆用多少步、几秒，目标未达占比及eps缺陷？ | 隐去未收敛调用或一律标PASS |
| 完整总时间与V5基线相比怎样？ | 只比较外层步数或每个小LU速度 |
| 两组顺序是否值得其额外T作用？ | 比更差的旧H4/p2好就称成功；只看一次残差比 |
| 短波的存储与构建债务是什么？ | 内部低RSS就声称0.7nm/2TB可行 |

状态分开：`TWO_MODEL_P4_FACTOR_REMOVED_PASS`只在完整两模型数值/物理/资源成立时使用；内层仍未达目标要同时报告，并说明这不等于独立A4求解器资格。收敛但存储或时间无优势标`NUMERIC_PASS_NO_RESOURCE_ADVANTAGE`；阶段受控停止、正确性阻碍、资源阻碍、未运行各自记录。全部不成功则关闭本批两个具体实现，不继续自发改权重、换组、增步或追加诊断。

保留V5可移交成功基线，不要求先本机2GB成功再准备工作站。这里只更新移交包及5nm材料/通道/容量预审清单；不因本文自动启动SSH、搬动现有计算目录或新短波PDE。不同重型分支不抢同一机器资源。

## 10. 提交、证据与理论边界

提交顺序：A通用接线/合法截断及focused测试 -> clean源码A原始/条件notch -> 需要时B实现及clean源码运行 -> 统一response/总账。ChatGPT仅新增本review；Codex实现和执行，不修改旧review、不amend、不强推、不合并master。

每次正式保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json，以及ABI/MPI/线程、材料网格/模式、缓存及artifact hashes、全过程资源。成功和失败每阶段即时落盘；signal只置位，安全回调保存，不能在handler中执行MPI/PETSc。结束后释放内外KSP、S/局部因子、无用矩阵和缓存，确认资源下降，再恢复场与功率；异常清理所有后代。

数学依据只用于解释候选，不替本问题提供成功保证：

- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)允许在预条件器内部使用非线性/变化的Krylov过程。它保证框架适用性，不保证任意不精确粗逆都收敛。本项目仍使用现有已资格化ABI，不照网页版本升级。
- [PETSc PCCompositeType](https://petsc.org/release/manualpages/PC/PCCompositeType/)区分加法和根据新残差依次施加的乘法组合。本文只借用这一组织方式，不套用SPD收敛保证或改变原非Hermitian方程。
- 本review的eps恒等式和两组公式可由所列运算直接推导；一次局部作用的残差增大不自动否定FGMRES，少量样本的场误差改善也不等于整体通过。

**本轮交付的核心不再是“把内部p4解到某个数字”，而是“受控不精确粗逆是否让完整p6取得正确解，并以怎样的资源代价取得”。必要检查集中完成，随后直接用原始与非可分模型裁决。**
