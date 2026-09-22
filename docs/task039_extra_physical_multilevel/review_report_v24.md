# Task39extra Review V24：减少setup重复工作与局部内核开销

## 0. 结论、目标与本轮授权

**接受Q4插电复跑r2作为当前同模型速度基线：完整51.90分钟、126步、约7.391 GB。保持p6/p4双层凝聚、BAL_H/H6、准确p4凝聚逆和已合格张量积内核的数学作用，优先减少第一次setup中的重复工作，并继续优化实际A6/H6调用。正常只新增一场完整original p6/h7.5；局部磁盘缓存另做一次不含PDE的加载验证，不为每项优化各跑长场。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-22
reviewed_base_SHA          = 76bc2e1b161dbacdeb22fba373ce1edbbda08134
base_latest_commit         = docs: complete Q4 rerun comparison record
latest_review_response     = review_report_v23.md / response_v26.md + AC r2补充
baseline_formal_source     = 4bf2bba56cc2e568d56ff3096aeb4a108744f28d
batch_identity             = review_v24_setup_and_kernel_efficiency
suggested_new_profile      = physical_p6_trace_setup_efficiency_v26
response_required          = response_v27.md
execution                  = T0 -> T1 -> T2 -> T3 -> T4 -> conditional T5 -> T6
formal_case                = original, 13.5nm, p6/h7.5, 990 cells, q4, 80 modes
formal_environment         = existing qualified laptop WSL/Linux complex128 ABI
normal_new_full_PDE_count  = 1
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

本批消除面向“约2 TB、0.7 nm、任意非可分三维Maxwell”的工程blocker：**setup反复生成相同数据、局部积分及数组搬运成本过高**。它不是新的PC筛选，不授权工作站或其他波长运行，也不证明当前全局p4因子已具有目标规模可扩展性。

用户本轮明确要求实施上一轮讨论的值得优化项，并用同一p6/h7.5比较。本review授权连续实现、必要检查、同根正式运行和统一收口；不在每个小检查或setup后等待批准。首轮构建加速与重复运行缓存收益必须分开，不以热数值缓存结果冒充首次求解提速。

先读根及适用目录AGENTS、[工作原则](../repository_work_principles.md)、[任务书](task.md)、[Review V23](review_report_v23.md)、全部用户补充授权及[最新回应](response_v26.md)。新profile的范围由本review决定；旧profile、checker、review、负结果和资源账不追溯改写。此前r2和Q2的中止历史不删除；旧p4微小超限已由有界精化处理，不再重跑其定位前缀。

## 1. 审阅接受的事实与明确未知项

主要证据：[r2结果](outcomes/v25_q4_ac_swap_observe_r2.md)、[r2 compact](outcomes/records/v25_q4_ac_swap_observe_r2_result.json)、[首次Q4记录](outcomes/records/a6_h6_coarse_degree_v25_q4.json)、[summary](outcomes/summary.md)。GB=10^9 B，GiB=2^30 B。

| 同一990单元Q4 original基线 | r2数值 | 身份与口径 |
|---|---:|---|
| 完整workflow | 3114.283619607013 s；51.90472699 min | measured，主要时间分母 |
| 纯KSP | 2284.681783819 s；126步 | measured；18.13239511 s/step |
| 非KSP合计 | 829.601835788013 s；13.82669726 min | derived；包含setup、检查、输出、清场，不是setup单项 |
| 全过程RSS峰值 | 7390937088 B | measured，同时process-tree，不是worker单进程 |
| 原A6最终/释放后残差 | 9.283165086752956e-7 / 同值 | measured，limit=1e-6 |
| A6 live | 263次；823.1639212121663 s | 累计action，含volume与DtN |
| H6 apply | 131次；484.89414036102244 s | 累计父区间，不能与子项重复相加 |
| 供电与资源 | AC1首次成功启动后/结束均在线；作业swap0，全局pswpout增量0 | 不足以证明旧场变慢唯一由拔电造成 |

首次Q4的完整setup为836.8461274599977 s，其中numeric为218.3896326339891 s、H6对角47.394968193999375 s、power10准备39.93837261298904 s。**这些属于首次Q4，不能填入r2作为实测分项。**优先从r2已保存的lifecycle/events提取同边界setup数据；缺失就写unknown，不为补这个分母重跑旧完整求解。

r2动态checker只覆盖其声明的调用计数/接线范围，不能替代新优化所需的算子等价、原A6及完整场回归。r2与旧Q4是同离散迭代结果，不是独立高精度authority。Q3的低内存成功、Q2未完成和旧58/59均保留，但本轮不重新运行它们。

## 2. 冻结同一个物理与数值问题

新dat从[已测r2输入](../../input/task39extra/v25_q4_ac_swap_observe_r2_h7p5.dat)继承物理/离散字段，只增加明确的profile、run_id和实现选择。一个dat对应一次计算，最终由`python scripts/run_case.py input/path/to/case.dat`进入既有独立服务与watchdog。

| 项目 | 本轮冻结内容 |
|---|---|
| 物理 | 波长13.5 nm；1°掠入射、azimuth0、s偏振、幅值1；不是7.5 nm波长 |
| 单胞与材料 | 50×25 nm，z=-10…130 nm；original 17×25×120 nm grating；air与原Si复折射率；mu_r=1 |
| 实际网格 | 原冻结轴计划9×5×22=990单元，坐标/拓扑/tag一致；不按target重新生成另一网格 |
| fine FE与边界 | p6、原Basix变体、Nédélec H(curl)、complex128、双Floquet、原80个DtN key/order/相位/归一化 |
| p6规模 | full storage 667152；内部445500；独立trace 199260；增广199340 |
| 粗层 | 同网格p4；full storage 201520；独立trace 84600；准确凝聚因子84680行 |
| 外层与PC | retained-space right FGMRES32、max2048、零retained初值；原增广逆桥、BAL_H、一个H6及两次逻辑粗修正 |
| 内部质量 | 原A4返回<=1e-10；必要时同一因子最多2次额外精化；ICNTL(10)=0、BLR关闭、无inner KSP |
| H6 | 同一正定B6、积分、对角定义、Chebyshev规则、power10步数和seed生成规则；不调整谱窗比例 |
| 输出与检查 | 相同完整E/H、curl、界面量、R/T/A/A_volume、80模式；每8步原A6、每32步场；最终独立检查不减少 |
| 生命周期 | 先JIT后大因子；只读共享identity；因子活跃时安全保留原矩阵；最终场/原A6合格后释放再后处理 |

身份锚点：

```text
mesh_plan_sha256  = b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157
physical_model   = 0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6
fine_rhs_storage = b85dde2599428906be4ffd2f2200438f3011e57358d20a541679b3ab50687824
ordered_modes    = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

新input/resolved/source hash必须重算，不硬填旧hash。若旧physical hash含执行字段，保存原定义并提供fieldwise物理等价桥；不通过改hash定义掩盖变化。

不做p3/p2/p1、H4递归、粗网格p6、BLR、DD/PML、GPU、complex64、fast-math、积分降阶、通道删减或新的restart扫描。不形成全局p6矩阵/因子，也不新建逐单元稠密物理矩阵库。

## 3. T1：必须优先尝试的首次setup优化

### 3.1 不生成sum-factorization根本不用的完整参考表

审查入口：[ReferenceCellBasis](../../src/solvers/fullspace_quadrature_diagonal.py)与[IsotropicPartialAssembly](../../src/solvers/fullspace_partial_assembly.py)。当前`element.tabulate(1, points)`在判断`store_reference_tables`之前执行，因此新张量积路径虽然不保存完整values/curls，仍先生成并丢弃它们。

把完整tabulation移到真正需要它的分支；张量积路径仅建立实际消费的多项式系数、一维表、积分点/权重和Q1几何数据。保持FFCx选出的原积分规则、积分点顺序以及实际Basix元素/方向。不要把独立native见证路径一并改成依赖候选数值缓存。

初始化审计不再读取不存在的`table.nbytes`；用实际分配和明确的shape-derived上界分别报告。测试需证明新路径确实没有调用完整高阶tabulate，而非仅把返回数组设为None。旧需要参考表的路径保持原行为。

### 3.2 H6直接构建选定后端，避免先建再销毁native对象

审查入口：[physical_light_setup.py](../../src/solvers/physical_light_setup.py)与[FullspaceMpcFormAction](../../src/solvers/fullspace_mpc_action.py)。当前选用快速power10时，仍先创建native作用，再建立packed/sum-factorized作用替换它。

新opt-in路径先确定backend，直接构建该action及shell，再建立相同定义的对角、seed和smoother；避免立即销毁的native form、Function、MPC元数据和向量。保留历史fallback，不改变普通默认。快速power10已在V25实现，不能把重新打开该开关当作本轮新成果。

原A6独立验证对象仍保留；不通过让candidate与唯一oracle使用同一新内核来形成自证循环。开发配对所需旧H6对象只在组件阶段存在，正式场不同时常驻两套H6。

### 3.3 同一进程内共享不可变几何、编号和参考数据

将当前多个局部action重复构建的p6 cell DoF索引、方向、适用的几何metric及参考数据拆成可借用的只读对象，随同一live mesh/space拥有者管理。p4/p6的DoF表不能互用；curl/mass/positive的积分规则不同则分别保留，不能为共享而统一成较低阶积分。

键必须区分space/mesh版本、dtype、单元方向、metric约定、quadrature和材料依赖；可以共享几何，不擅自共享不同材料系数。不要把仅尺寸相同误当内容相同。可写scratch按实际串行调用关系复用，不能让嵌套或后续线程互相覆盖。

沿用已有12/26等局部类的实际盘点，不硬编码类数。报告构造次数、借用关系、唯一载荷、峰值与释放顺序；共享后不得造成缓存永久增长或对象使用后失效。

### 3.4 H6对角：按真实局部类型复用与批量积分

目标是减少[build_quadrature_positive_diagonal / accumulate_basis_energy](../../src/solvers/fullspace_quadrature_diagonal.py)中每个单元、每个target反复搜索和积分的工作，而不是近似对角。

令C_K为实际复数约束展开，B_K为同积分规则的单元正定作用，要求始终计算：

```math
d=\sum_K\operatorname{diag}\!\left(C_K^H B_K C_K\right).
```

按相同材料/metric/方向/积分身份复用局部能量；对不发生局部目标合并的行，用批量运算计算能量并scatter。发生多raw行映射到同一master、多master或复相位时，保留原交叉项和共轭关系；允许按规范化的局部约束模式缓存必要的小交叉块，不形成全网格稠密B6。

不能一般性地用`abs(C)^2 * diag(B)`替代上述公式。缓存局部模式时可把global master编号重编号，但必须保留相等关系、系数及多重贡献，实际global编号仍用于scatter。所有单元贡献和ghost/slave策略仍正确累加。

一次合并验证应包含：真实990网格对角对照、周期边界、复系数、多master/合并target局部fixture。对角正实性/finite/slave规则不变；局部能量与全局对角相对差目标<=1e-12，H6完整作用<=1e-10，并保留已有更严的局部合同。若重排求和超出已有容差，不放宽门槛，恢复该项旧路径继续其他优化。

power10仍用本场新对角和同seed生成，不能直接加载别场谱窗。若对角仅舍入级变化，允许报告新hash及数值等价，而非要求所有hash逐字节相同。不得通过减少power10步数、改变H6次数或谱窗倍数提速。

## 4. T2：有界的装配与实际apply优化

### 4.1 条件式收紧p4端口预分配

[当前p4 stack](../../src/runners/physical_p4_cell_condensed_v18.py)把全部单元作为appended support上界。首次Q4的NNZ used/allocated为32320342/45403840，这是存储机会，不是已测时间收益。

复用carrier和[现有预分配](../../src/solvers/hcurl_assembly_time_condensation.py)，为每个端口构造**消元后左右支撑的安全并集**。对非Hermitian问题分别保留B、D支撑；若内部端口耦合产生新trace或port-port连接，必须包含。不能只取原边界点，也不能把阈值小的非零删掉。若不能可靠闭合，保留原安全上界并记录未采用，不阻断主线。

启用`NEW_NONZERO_ALLOCATION_ERR`，保持全局行号、真实矩阵条目、端口和分解控制不变。允许allocated容量变化；若显式零的存储不同，保存规范化CSR逐项/作用等价与新旧hash桥。仅减少预分配不保证factor填充减少，报告不得混称。无需在990场同时装两张矩阵或分解两份factor。

### 4.2 对A6/H6已经记录的最大子步骤继续优化一项

使用[张量积内核](../../src/solvers/fullspace_n1e_sum_factor.py)及partial-assembly现有的`coefficient_transform/reference_forward/metric/reference_backward/gather/scatter`计时，从r2 artifact或同工作集短配对确认主要成本。不要再次进行“为什么插电变快”的完整复跑。

允许预分配并复用连续收缩中间缓冲、复用固定einsum路径、减少相同维数下的重复索引/重排、在保持原积分规则下复用重复计算。只针对一条共同后端，固定合理batch，不扫描大量batch/编译器参数。

若系数转换为主，可审查实际Basix系数映射的结构；只有证明相容才能使用结构化变换，不能凭尺寸推断稀疏性或按阈值截断系数。不同积分规则的curl/mass不得强行融合。必要的额外工作区必须固定、有账，不增加网格尺寸乘积级临时表。

优先测真实PC输入的旧/新action，一次首次调用与最多三次warm交错配对即可。完整PC的短兼容检查放到本场必要setup中，复用随后要用的唯一p4因子；不要为每个向量重新numeric。没有收益或内存明显退步的可选项撤出，继续合格组合。

本批不再研究LU detach、因子压缩、MUMPS排序/主元或后端升级。p4仍一次准确分解、跨全部迭代复用；相同形状不代表可以跨波长复用全局因子。

## 5. T5：条件式局部数值缓存复用，不冒充首次求解提速

当前凝聚已经在进程内按类型共享；新增对象只能是**跨进程可校验的局部数值packet**，不是重新宣布已实现的类型缓存。此项放在主线之后：已有小型artifact机制可以扩展则实施；若需要开发通用缓存平台，记录`DEFERRED_PERSISTENT_CACHE_SCOPE`，本批不扩大架构。

首次正式T4必须`numeric_cache_mode=build`：不加载以前保存的局部LU、Schur、对角或恢复数据；同场共享和合格JIT缓存可正常使用。这样主要完整时间仍包含本次第一次必要数值构建。

正式结束且大factor/工作集已释放后，可将本场过程中按需保存的局部packet在一个独立小工程进程中加载，核对身份和局部作用。若packet序列化在正式区间内执行，其时间和内存保留在完整成本；若只能事后由已保存的原始artifact导出，单列导出工程成本。不能为了导出在正式运行后半程仍扣留本应释放的大对象，不能重建整场factor。

缓存边界：只考虑合格局部张量、内部小LU及恢复/RHS算子；不存全局MUMPS因子、不存旧解/Krylov方向、不延续旧KSP。规范化key包含数值实现/ABI、实际FE与变体、dtype/endian、局部几何与方向、材料/波数、每项积分规则和消元选项。若存约束后数据则还需MPC/相位身份；原始体局部数据可以只依赖其真实数学输入，但必须明确依赖列表。

使用固定schema、原始数组文件及内容hash，禁止pickle或动态执行缓存内容；加载验证shape、dtype、finite、hash及数学身份，文件不完整/损坏/过期即拒用并局部重建，不改变原数据或静默沿用。同key只保留一份只读数组，按需加载，无无界resident缓存。

小测试验证材料、波数、q、几何、方向、quadrature或schema改变可正确失效，并验证损坏文件不被采用。加载后检查内部解、RHS缩减/恢复及局部Schur作用。**不再跑第二场完整PDE来展示热缓存；报告的结论只能是已测局部构建/加载收益，不能称完整热启动求解通过。**

## 6. 连续执行与唯一正式回归

| 阶段 | 工作 | 执行边界 |
|---|---|---|
| T0 | 短preflight、r2基线/原始字段、冻结物理与计时边界 | 不重跑r2、旧p4前缀或p3/p2 |
| T1 | 无用参考表、直接后端、同场共享、准确对角优化 | 集中必要小测试；逐项回退不拖住全批 |
| T2 | 条件预分配、一项主要apply开销优化 | 复用已有计时；可选负结果保存，不继续抽参数 |
| T3 | 组合等价性、实际路由/内存检查，冻结source/profile | 选定一套方案；不让探针替代完整计算 |
| T4 | 一场新的original p6/h7.5完整Q4 | 本次数值build，setup合格后直接用同factor进入KSP |
| T5 | 可选局部packet独立加载与失效检查 | 工程测试，无第二场PDE或全局factor |
| T6 | 同口径结果表、证据、response_v27、推送 | 统一待审，不合并master |

默认MPI1/thread1，以免setup优化同时混入并行变量。此前“多核不得增加内存”的要求继续有效：仅当局部组件已证明2线程更快、且相同q4实际工作集内存不增时，才可冻结为唯一正式设置；MUMPS仍单线程，不扫描4/8线程、不启动额外全场、不复制factor/mesh/global向量。没有正证据直接用单线程，不因此停审。

工程旧/新对象可短暂同时用于配对，但正式T4必须释放oracle的重复数值缓存，只保留独立native核验所需对象。所有子进程在监督树内。组件输入取已存实际向量或固定合法fixture，保留哈希；不在计时中生成不同输入。

若一项可选优化失败，恢复该项既有合格实现，继续其他项。若完全没有任何合格数值/存储改变，明确`NO_ADOPTED_OPTIMIZATION`并收口，不浪费一场重复旧基线。只有真实实现bug可沿现有hash-bound规则修复，最多一次必要正式重放；不为性能低于预期追加多场。慢本身不是bug，也不调整PC。

## 7. 同一精度和安全合同

### 7.1 数值、物理与回归

| 检查 | 要求 |
|---|---|
| 每个原A4返回 | 原始g分母，relative<=1e-10；最多2次显式同factor修正；同步累计FE/端口状态 |
| A6/B6/H6候选作用 | 同输入操作尺度相对差<=1e-10；沿原更严伴随、repeat与linearity合同 |
| H6对角 | 同定义、正实finite；相对差目标<=1e-12，保持slave/ghost与多master交叉项 |
| 凝聚与端口 | 完整单元物理项先相加再消元；非零内部RHS与左右端口耦合不省略；闭合<=1e-8 |
| 原A6最终 | 完整p6场恢复后、释放前后独立true residual<=1e-6 |
| 最终p6场回归 | 与r2保存场比较，FE L2/scaled-curl、同坐标E/H/界面及完整复模式relative<=1e-4 |
| 功率回归 | R/T/A/A_volume绝对差<=1e-5，逐模式功率最大绝对差<=1e-6 |
| 物理一致性 | abs(R+T+A_volume-1)<=1e-5，abs(A-A_volume)<=1e-5；原模式求和、被动性和归一化检查 |

近零项沿原绝对例外；不拟合相位、不重归一化、不平滑结果。126步和51.90分钟只是分母，不是停止上限。允许重排浮点求和带来的合格差异，不保证逐字节同解；明显迭代变化需结合H6/算子身份解释。只达到A6而场回归失败时分开记`SOLVE_PASS_REGRESSION_FAIL`。

动态checker按实际步数、setup/iteration/check角色及额外精化计数，不能硬编码126/263/131等历史observed值。继续保存每8步原A6和每32步场，不通过减少检查、RHS、模式、输出或只计BLAS时间提速。r2无独立h7.5高精度reference，全部通过仍为`DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`，不宣称连续精度或5nm/0.7nm资格。

### 7.2 资源、供电与状态

只在本机合格环境运行，一次一个heavy；不触碰工作站/2nm任务。检查有效RAM/cgroup/宿主压力、磁盘及监督清场，保留系统实际余量，不以OS OOM作正常终态。保留现行实际物理压力策略，不恢复旧固定6/8GiB库存或2倍symbolic作为唯一阻断；p4分解仍沿已验证额度/排序控制，不擅自提高MUMPS额度。

为同最近r2比较，本review仅在新profile内沿用最近用户追加授权的`time_policy=observe_only`和`swap_policy=observe_only`。启动时记录原授权来源及scope，新run_id不能冒用旧r2授权ID；不修改其他profile/全局监督默认。数值breakdown、非finite、身份错误、未修复粗返回错误、真实内存压力/证据不可写/监督失联和用户停止仍按既有安全机制收口。

作业与系统swap分别观测，目标仍为实测zero-swap，不通过交换内存支撑更大缓存；若实际发生交换，明确资源/性能资格受限，不宣布同条件无swap提速。无法归因的少量全局页活动不是作业OOM证据，不偷偷恢复旧“一见全局页变化就杀”的行为。

全程接电、固定电源模式、避免其他重负载；以现有接口记录启动/阶段/结束AC状态和可得频率/CPU时间，不安装新监控平台或修改散热保护。无法读取写unknown，不据此编造旧场拔电的唯一因果结论。供电变化时保留运行/用户选择，但将性能比较标记为受干扰。

报告全过程与各阶段同时树RSS/PSS、worker峰值、数组载荷和后端allocated/used，彼此不混用。7.390937088 GB是比较分母，不是新的固定硬终止线；工作集增加必须如实披露，不能用磁盘缓存或多线程的隐含空间掩盖。缓存导出/加载及组件工程成本另记，作业峰值不跨阶段相加。

## 8. 计时与裁决：最终必须知道哪里省了时间

复用既有marker和audit增加缺失边界，不另建profiling框架。至少区分：JIT/分析、参考初始化、共享metadata、H6对角、power10、p4预分配/局部张量/装配、symbolic/numeric、p6凝聚/桥、setup验证、纯KSP、最终native检查、释放、物理输出、缓存导出/加载。

原始monotonic起止与count随事件保存；CPU时间和wall时间分开。父子嵌套标注inclusive，可获得exclusive才报告；runtime/sample/fsync开销计入真实流程，不能由各项相减猜最大热点。`monitor.solve_seconds`不改名成纯KSP。

```math
S_{\mathrm{full}}=\frac{3114.283619607013}{T_{\mathrm{new,build}}},\qquad
S_{\mathrm{KSP}}=\frac{2284.681783819}{T_{\mathrm{new,KSP}}}.
```

首次数值构建T4中JIT正常复用、所有局部数值数据本场重建。新核首次编译计入所属工程/正式范围，记录hit/miss，不删除共享JIT制造冷场，也不把必要构建搬到统计外。磁盘局部缓存只另列`build/load/validation/serialization`实测，不拼装虚构的“完整热启动总时间”。

最终对照表至少有r2、本轮正式T4、可选cache-only三个scope；旧Q4 78.65分钟及V24 76.32分钟可以作历史附表，不用它们替代更快的r2主分母。若r2 setup边界确实缺失，对setup只报告本轮实测和组件配对，不给不存在的整场setup百分比。

合格且更快、资源未明显退步才建议作为性能候选；仅setup快而全程无收益，分别报告；数值合格但内存增加，标明tradeoff。没有必须减少几分钟/再减半的硬指标，不因收益不漂亮继续追加运行。

## 9. 交付、提交计划与response要求

本批新增数值实现进入可复用`src/`模块，runner/schema只作最小参数化；不复制整套task-numbered求解脚本。建议三次提交：D1实现及相关测试；D2冻结新dat/profile和正式source；D3运行后证据及文档。正式时tracked工作树干净；源码冻结后不在长运行中热修改。

使用现有pytest fixture集中运行受影响的参考表、MPC对角、H6、张量积、凝聚/端口、缓存生命周期及runner/checker测试；不要求每步跑全库，也不重新认证未改算法。lint/compile/diff与文档检查按现有工具执行，不安装无关工具、不声称未运行的CI。

推荐轻量交付位置（实现可合理合并文件，但必须覆盖信息）：

```text
outcomes/setup_efficiency_v26.md
outcomes/records/setup_efficiency_v26_components.json
outcomes/records/setup_efficiency_v26_cold_build.json
outcomes/records/setup_efficiency_v26_cache_reuse.json
outcomes/records/setup_efficiency_v26_compact.json
outcomes/records/setup_efficiency_v26_decision.json
response_v27.md
```

正式保存原input、resolved_config、run_manifest、input/physical/source SHA、run_summary、环境与MPI/线程、watchdog、矩阵/缓存/场artifact hash和完整输出。大数组与raw logs留ignored目录，只提交有来源和hash的轻量结果。新cache schema/载荷/失效原因应可审计，不把`status=PASS`作为唯一证明。

`response_v27.md`必须回答：

1. 首次setup哪些重复工作真正被删除，分别减少多少构造/积分/内存流量；哪些建议因无收益/不安全未采用。
2. 完整p6/h7.5相比r2的51.90分钟和38.08分钟KSP，分别快慢多少；迭代、A6/H6次数/单次成本及精化是否变化。
3. 原A6、完整场/模式/功率回归是否通过；没有新增独立reference的限制是否保持。
4. RSS/PSS、临时工作区、类缓存、MUMPS统计如何变化；供电/线程/swap是否影响比较。
5. 局部磁盘缓存是否实现及验证；仅局部热加载的收益与工程成本，不虚构第二场PDE结果。
6. 下一步应采用新组合、只保留其中部分，还是继续以r2为速度基线。

同步更新本目录summary、test_summary、run_index、项目development_progress和development_model_registry，以及最小selective merge清单；把“V24仍最快”明确标成旧批次结论，当前总览使用r2或新已测结果，旧历史不覆盖。

完成后推送同一`task39extra`并给出完整HEAD、工作树状态、测试与证据入口，统一等待审阅。不合并master，不自动启动notch、p3/p2或工作站迁移。

## 10. 审阅边界

本报告是基于上述SHA的远程记录与代码阅读所作的执行合同，不是新setup加速已被测得的结论。ChatGPT本次仅新增本review；没有执行项目PDE、实际ABI/内核性能试验或工作站操作。局部缓存、预分配和多核均不得预先写成有效。重点是把已有成功的p4双层凝聚实现得更经济，而不是重新挑选一种PC。
