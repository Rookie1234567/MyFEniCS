# Review V67：保留完整L5空间，实测精确凝聚与高阶模式增量

## 0. 裁决、目标和唯一身份

**V68按`pass_with_qualifications`接受：同一L5已完整返回，原式、恢复、全场和费用链完成；L4F/L5及P6/L5完整增量仍FAIL，不能授连续精度、原尺寸2TB/48h或NN收益。** 不再把已解决的SIGTERM恢复和矩阵准备当作新任务。授权 **V69_EXACT_TETRA_CONDENSATION_AND_P5_DTN**：以保存的同一L5为参照，把767280个单元内部未知量精确局部消去，实际求解保留全部p5接口的系统；同时有界检查固定点的取值语义，并完成唯一p5/1188模式对照。精确凝聚不改善空间误差，但可在不改变场空间的前提下推进全局规模控制。

本轮不是只交一份区域诊断，也不是再全域升p。两个独立blocker分别处理：准确性差异的位置/点值语义及p5模式截断；全局方程、因子和未来Krylov向量库过大。未达到连续精度不阻止同一离散系统的资源实现验证，资源收益也不能代替物理精度。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-10 Asia/Singapore
reviewed_HEAD          = 952259765ff1d1d284407183b45cc5dff1698008
latest_result_UTC      = 2026-10-10T01:46:42Z
latest_result_local    = 2026-10-10 09:46:42 +08:00
latest_response        = response_v68.md
previous_review        = review_report_v66.md
previous_review_commit = 9934973deeed79d9dfc6aa40a69902960f191ef9
previous_review_blob   = e83f0d50a6c6cd40822f8db81546d64087336ae3
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V69_EXACT_TETRA_CONDENSATION_AND_P5_DTN
required_response      = response_v69.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标保持真空0.7nm、原50×25nm周期/z=-10..130nm、任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN、复E/H/衍射/R/T/A/独立体吸收。完整必要准备至验收≤172800s，约2e12B是整机内存，须留系统余量。当前s=7/135有限问题不等于原尺寸资格。

明确覆盖上版“本批不静态凝聚/不新模式/只完成L5”的阶段限制；新操作是已有静态凝聚技术在同一四面体离散上的精确实现，不另开PC研究，不改变物理或有限元空间。历史FAIL、direct子门、成本、旧窗口和报告均不改。

## 1. 已审证据、收益和未决项

本端已读取当前结果、区域记录、K保存、原体/边界/求值/求解源码、根规则及仓库原则，核对上次review以后4次提交。原task身份及未变规则按此前审阅继承并核对当前blob；上一完整review从挂载副本读取。任务目录未检出新的独立supplement或同名V67报告。本端未SSH、未重演工作站大数组或运行新PDE；下表measured指仓库发布记录，不是审阅端复测。

证据：[V68回应](response_v68.md)、[当前汇总](outcomes/summary.md)、[原式与输出](outcomes/records/complete_physics_v68.json)、[配对](outcomes/records/paired_results_v68.json)、[区域](outcomes/records/paired_regions_v68.json)、[资产](outcomes/records/body_checkpoint_v68.json)、[最终费用](outcomes/records/resource_costs_final_v68.json)、[离散参照](outcomes/records/discrete_reference_contract_v68.json)。

| V68 recorded measured | 结果 | 解释 |
|---|---:|---|
| L5 tet/p/modes | 25576 / 5 / 828 | 冻结局部网格，真实NOTCH |
| 独立FE/完整行/增广nnz | 1943745 / 1944573 / 464436991 | 全部内部自由度进入全局LU |
| production true | 3.06036950484e-11 | 不替代独立审核 |
| 独立true/augmented/port | 3.35489014225e-10 / 3.35489193213e-10 / 1.05147422573e-15 | formal1e-6通过，direct1e-10失败单列 |
| R/T/A_volume | 0.0762185592269 / 0.905665161130 / 0.0181162796389 | 能量误差-4.25959268e-12 |
| L4F/L5散射E/H，240点最大六向量差 | 3.53386270e-4 / 3.61017764e-4 / 1.81995846e-3 | 完整增量FAIL |
| P6/L5散射E/H，240点最大六向量差 | 1.14449343e-4 / 1.23013215e-4 / 9.56041627e-4 | 更接近，但仍FAIL |
| P6/L5参考面复通道/最大mode功率差 | 1.27295664e-5 / 1.22639767e-8 | 不能覆盖场FAIL |
| prepared-start完整T_N1 | 5955.67641464s | 新进程至原式/输出/清场，不含研究比较 |
| 父PREPARE+本次部署 | 18050.7955984s | 分段小计，旧资格仍在旧失败调用内，非精确fresh冷链 |
| 同时树采样峰/最大gap | 129.562198639GiB / 1.00198483421s | 自身swap/OOC0；不是连续硬峰 |

P6/L5差平方中66.80% E、70.68% H位于缺口外空气，只说明区域归属，不说明离界面远或近，更不证明唯一根因。旧p4的828→1188通过不能迁移为p5模式充分性。当前两簇最细参照接近，是有限正进展，但不得说“只差一点可忽略”：240点指标仍约9.56倍于门限。

本轮保留三个已验证资产：V60实体支撑局部装配的同空间低存储成果；V65系数先收缩的独立原作用；V68持久会话/停止落盘和健康K恢复。不得再次全套重做。V68历史发信者仍unknown，不再次取证。矩阵准备费用仍须入总账，checkpoint不是免费构造。

## 2. D：短而具体的精度归因，不单独占据一轮

### 2.1 固定240点存在需要核对的取值语义

源码`independent_tetra_fields.selected_points`使用原宏盒及Z2盒中心；`independent_tetra_scope.physical_for`的fine h_ratio=2在x/y/z分别把原区间分成2/2/4份。按生成公式，这240个位置落在该fine父网格的顶点位置；必须用实际保存坐标复核，不凭公式替代数组证据。局部refinement继承父顶点的事实也要核对。

现有`locate`在多个候选tet中按几何排序选一侧。H(curl)离散只保证切向E跨面连续，不保证整矢量E或curl/H在人工单元面上单值。因此不同网格选到不同单元侧可能影响点值比较；这不是已证明的程序错误，也不能解释尚超门的全域L2差。不能据此删点、平均、平移评分点或改原门。

从保存P6/L5的mesh和240点读取：点到tet重心坐标、是否在人工面/边/顶点、所有相邻材料标签、旧选中cell几何。保持旧240点及旧FAIL，另作预登记方向的单侧诊断：方向为(±1,±sqrt(2),±sqrt(3))归一化后的8组；用重心坐标方向导数选择x+0+ d所在tet，然后在原x上评价该tet多项式。不能实际移动评分坐标、择优方向或取平均。各方向分别给六向量差和同场跨侧离散度；若方向不唯一，记录并跳过该诊断项，不伪造相同侧。

### 2.2 界面邻域只消费已存差分

在共同L5网格上，以真实不同材料标签的内部面（含真实缺口面）定义第一层邻域，再扩一层。周期接缝不误当材料界面，z端口另列。汇总两层cell并集的体积/单元比例、已有E/H差平方占比及240点分布；明确这是cell并集代理，不是固定物理厚度内的严格积分，也不是后验误差界。全域分母保持原值，不把局部子集重新归一化成新的正式门。

D目标30分钟、上限45分钟；无新PDE、factor、全域积分或网格标记。已有健康数组不足则交部分事实，不重复旧大数组审计。新诊断代码不可信只隔离D，不取消数学独立的C/M。若实际发现原保存场解释错误，先限定影响并补消费，不把诊断假设扩大成所有历史PDE重算。

## 3. C：同一L5的精确单元内部消元，不改变空间

### 3.1 为什么做，和旧混阶有什么不同

先在每个tet内部消去只属于本单元的未知量，再让边/面接口参与全局求解，解出接口后恢复全部内部场。这是静态凝聚，不是NN、低阶近似逆、混合阶次或删场。与旧trace6/interior7受限空间不同，本轮trace和interior都属于原p5，**一个p5边/面方向都不删**。

N1curl的本地p5维数140，其中单元内部30、边/面110；实际通过Basix实体DOF、方向及MPC映射核对。derived：25576×30=767280个内部，1943745−767280=1176465个独立边/面，含828端口后为1177293行；相比1944573行少39.4575%。1188模式时为1177653行。它是维数收益，不是同百分比RSS/时间保证。每个内部块很小，但局部LU、恢复、填充和临时CSR全部收费。

当前没有连续精度证书，但已有完整L5原方程资格，足以验证这一**完全同离散**代数优化。若严格再现通过，只授同离散实现，不授空间误差下降；精确凝聚应当保持原P6/L5差异，而不是神奇地消除它。

### 3.2 完整非互伴端口分块，符号不可省

在已完成MPC拉回的原系数顺序中，以i为所有cell内部、t为全部其余FE，a为全部模式：

```math
\begin{bmatrix}
K_{ii}&K_{it}&C_i\\
K_{ti}&K_{tt}&C_t\\
-D_i&-D_t&H
\end{bmatrix}
\begin{bmatrix}u_i\\u_t\\a\end{bmatrix}
=\begin{bmatrix}f_i\\f_t\\g\end{bmatrix}.
```

Kii必须是按cell分块的真实块对角；不能仅由编号位置猜。C、D不假定共轭，g的物理值为零但接口和回归必须支持非零。当前三角边界保留了owner cell的所有实际非零项，因此即使内部迹理论为零，也不得按阈值删除已保存Ci/Di。

```math
S_{tt}=K_{tt}-K_{ti}K_{ii}^{-1}K_{it},\quad
\widetilde C=C_t-K_{ti}K_{ii}^{-1}C_i,\quad
\widetilde D=D_t-D_iK_{ii}^{-1}K_{it},\quad
\widetilde H=H+D_iK_{ii}^{-1}C_i.
```

```math
\begin{bmatrix}S_{tt}&\widetilde C\\-\widetilde D&\widetilde H\end{bmatrix}
\begin{bmatrix}u_t\\a\end{bmatrix}
=\begin{bmatrix}f_t-K_{ti}K_{ii}^{-1}f_i\\g+D_iK_{ii}^{-1}f_i\end{bmatrix},\qquad
u_i=K_{ii}^{-1}(f_i-K_{it}u_t-C_i a).
```

使用局部LU solve，不显式求逆、不用质量矩阵或对角近似替代Kii、不分别凝聚curl/mass再相加。原port coordinate scaling在缩减系统上等价应用一次，仍由原H及物理phase确定；Htilde一般不再对角，不能送进只接受对角H的旧装配假设。公式中的消元是普通线性块乘法，原MPC/其他基变换才使用其正确共轭对偶，不乱添转置。

### 3.3 最短的可信实现：先消费原K，避免重新装配

唯一K父资产为V67/PREPARE：`benchmarks/artifacts/task042/v67/body_K/manifest.json`，SHA256=`4516d89efe3d919e8e658b8fe497b606cac5c355bf5c753b6b2cb503130cd0bf`，COMMIT=`bb2801a2cec6ab3b385475b1bb2e0f0c7b0bb7b667f4b255ab174725e9c3f896`。完整资格与成员沿[V68资产记录](outcomes/records/body_checkpoint_v68.json)。不重新UFL装配、不复制8.86GB为新K；一次身份校验后只读重载。原full L5场来自dda480bd6d2cb532aefd7875c1d69d874dbd6841，实际指针从V68离散参照取，不猜路径或用日志造场。

按`entity_dofs[3]`和native→independent映射逐cell建立I_e，核对每个内部DOF唯一、不含周期slave、没有不同cell内部之间的实际非零。其余独立DOF全部保留。从原K提取Kii及实际相邻trace块；Ktt只贡献一次，再累加每cell消元修正，不能把已装配Ktt重复加cell次数。周期master完整closure保留，不阈值drop，不改变节点或材料。

复用本分支已验证的局部消元、有限稀疏装配及恢复小核，新增四面体实体适配和原solve的显式backend/strategy参数即可；不复制大型runner，不将hex 15表用于tet，不重做通用CSR框架。优先按局部或行块直接形成缩减CSR；禁止全局稠密逆、全局稠密Q、超大COO一次聚集及全局内部LU。缓存/临时图预算在形成前实际规划。

保存缩减body、局部恢复packet及i/t置换的独立身份。mmap原K、CSC/CSR副本、缩减矩阵、scale矩阵、局部LU/Kit/Kti及边界拥有者逐项入账。原K在完成形成与作用见证后可释放；不得在numeric峰阶段无意保留全部原A及其副本。恢复packet允许分块文件和最多4GiB常驻cache；额外临时workspace≤2GiB，均计入role总预算。共享只能按精确数值身份，不舍入合类。

保留`condense_rhs(full_rhs)`、`apply_trace(v)`、`recover(trace_port, full_rhs)`和完整维数清单。apply_trace可以是当前稀疏实现，但必须说明仍持有哪种矩阵，不能称已完成无矩阵生产。该接口为后续凝聚trace迭代铺路，本批不研发或扫描预条件器。

### 3.4 必要资格后立即进入完整PDE

仅新增：一个复数非Hermitian、Ci/Di均非零且g/fi非零的块代数回归；至多两个真实tet的消元/恢复见证；一份新缩减完整向量经恢复后与原独立PUBLIC_BASIX作用的对应关系。旧K/基函数/原式资格同数学同字节复用，不重跑旧24cell、FLAT、全部历史大场或全库测试。

先使用随机/解析固定向量验证映射，不用L5系数决定形成、分区、丢弃或初值。若局部块确实数值不可解，不shift、伪逆或放松门：只允许把相应cell内部原样保留到全局，保持完全同方程，逐cell记录证据；最多128个例外cell且总行≤1300000。超过此界隔离C，不把大批失败变成新默认；因实现错误导致的失败先修正。

C5/828从物理零初值实际求解缩减系统、恢复原1943745个FE及828端口，完成**完整原方程**审核，不能只看Schur残差或投影残差。与保存L5严格同离散再现：total/scattered E/H/curl、240点、参考面复通道≤1e-6；R/T/A/A_volume差≤1e-8；最大mode功率差≤1e-9。本轮同网格场比较可按原精确多项式分子复用，旧高q分母保持。

C5如果没有内存/时间收益但数学正确，仍完成比较和M；行数下降不自动授资源收益。数学再现失败先定位，仅原式/恢复可信的独立路径可继续。C实现目标2h；超过时不再扩框架，保存具体缺项并转第4节已授权的原完整体系模式后备，不能整批只交微基准。

## 4. M：同p5的1188模式完整对照，不再拿p4结论代替p5

唯一新增物理离散对照为同L5网格/p5的1188模式，m=-13..13、n=-5..5、两侧×两极化。C5严格再现通过则采用已资格凝聚backend；C接入受阻/未通过时，允许直接使用原完整四面体求解链和父K完成M5/1188，完整行1944933。不得以精度区域D未完成或L4/L5失败取消可信M。

模式边界q47/q63必须在p5新建，p4的M4数值边界不能搬用。若配对未过，定位后只允许一次q63/q79替代并绑定新身份，不扫q。原body K、Kii、Stt在同数学下可复用，Ct/Dt/Ci/Di/H及新rhs、凝聚port修正、factor按1188重建。旧L5场实际投影新增360模式，不能补零，raw倏逝辅助系数不代替物理参考面振幅。

主比较为保存L5/新M5，全部六场/240点、物理复通道、逐mode功率与独立体吸收按原门，两端固定分母均保留。不要求空间先PASS。M5通过仅授这份p5空间的828→1188有限模式增量；不自动证明无限截断或原尺寸准确。若模式变化仍明显，记录影响，不追加第三个模式库存。

全批两项计划global solve，最多三次numeric attempts，额外一次仅用于无合法返回且已定位并修复的故障；科学修复或同一数字重放全额计费。局部30阶因子按所有实际调用另计，不伪装成零factor。C5已有合法场后只补消费，不重解。再次原因不明中断不盲重启。

## 5. 原Gate、保存和连续执行

物理固定s=7/135、25576tet/1000个NOTCH tet、lambda0.7nm、grazing1度/azimuth5度/s、幅值1；kappa=(8.94046081729244,0.7821889682108057,0)，Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；canonical材料SHA256=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。网格SHA256=`c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c`。空间p5不变，独立体q15、原生产body q13，原式不得读取新S来自证。

formal true/native/augmented/port各≤1e-6，direct1e-10单列；MPC/恢复/切向E/操作身份≤1e-10。新空间/模式的六场与240点完整复向量、物理参考面复通道增量≤1e-4；逐mode功率≤1e-6，R/T/A/A_volume差和每场能量≤1e-5。C5同离散另用第3节严格门。原单位、背景、floor、q23/q31分母不变，不删点、不校幅相、不用total或守恒掩盖散射FAIL。

每次完整系数返回立即原子保存full x/u/port、trace/内部恢复身份、mesh/MPC/kappa/source；独立全场原式后销毁KSP/PC/因子和无用原/缩减矩阵，确认拥有者与RSS变化，再完整输出。消元packet先保存，保存不等于通过。JSON/collector/文档失败只补消费，不能触发重新factor。候选冻结前禁止读取参考场作初值、优化接口或制造rhs。

复用V68持久会话和先落盘停止事件，工具短轮询不终止健康worker。用户/管理员停止、真实资源/时间/监督失败仍清理自身后代。普通API/shape/路径/方向接口/writer问题同轮最小修复和受影响回归；不按bug总数交棒。同根因两次无效换诊断/原正确后备，不第三次盲跑。D接口失败不使C/M原方程失效；公共原式/ABI/恢复真错误必须先隔离依赖。

## 6. 资源、时限和成本：不再抬高内存许可

新12h总研发窗、科学有载≤10h、最后1h收尾；实现、读库、修复、失败、等待、输出、文档全部计费，UTC/monotonic/boot从首次真实工作冻结。C形成/求解/完整审核累计≤7h，M≤4h，二者均服从全局剩余。D≤45min、C新实现目标2h、累计故障修复≤2h，不能逐项各刷新总时钟。每次numeric前按已测阶段预测其上界，并留≥3600s完整输出/独立验收与总收尾余量；预算不足先取消可选重复评分，不削减科学门。

| role | planning / warning / sampled stop | 许可 |
|---|---|---|
| D/轻资格/无factor消费者 | 64 / 80 / 96GiB | 不暗藏全局factor |
| C5/凝聚M5 | 256 / 320 / 384GiB | retained≤1300000；原完整场载体不误套此门 |
| M5原完整后备 | 256 / 320 / 384GiB | 同p5/1188，full≤2000000 |

numeric仍须live树RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤256GiB，不能因当前L5峰129.56GiB就免symbolic或假定凝聚更便宜。INFOG负编码不能当负内存或造fill；未知保持unknown。保持complex128/int64、原Linux ABI、MPI1/math1/CPU1、GPU/Loader0、ownswap/OOC0，原PSI/cgroup/宿主与384GiB邻增长余量、空闲物理核避忙SMT；一个自身heavy actor和一个global factor。不修改邻任务/系统/共享Git，不靠OOM探容量。

新增ignored≤48GiB、Task去重≤560GiB、free≥50GiB且留512MiB证据余量；原K不复制，保存缩减body、局部响应和新场。原子临时双份、行图、重开的mmap及局部cache计入同时峰和disk forecast。不能删除旧失败/场来凑新准入。

报告C5完整prepared-start T_N1：父K读取、分区/局部LU、形成/保存、symbolic/numeric、恢复、完整原式、240点/六场/828模式/体吸收、IO和清场。与V68的5955.67641464s和129.562198639GiB只作同离散历史观察对照，缓存/机器争用未配平不授严格冷启动速度比。父PREPARE12095.1191837s及V67失败区间仍计一次，不能把复用K冒充装配成本消失。M的体对象复用另列prepared-start，必要前缀不隐去。

## 7. 面向2TB/48h的交付与分支去重

本批同时交出三个明确结论：旧点值/区域差异的有限解释；完全同p5空间的实际凝聚原方程/场及全生命周期资源；同p5模式增量。任何一个都不能替代最终目标。C5若没有RSS/时间收益，承认它只验证了精确接口和向量维数；不因理论成立就宣布高效。

在`discrete_reference_contract_v69.json`引用原K/L5和新C5/M5，明确原空间、i/t/port分区、任意rhs的condense/recover、实际apply_trace依赖与资源。矩阵形成仍从全局K开始，是本批复用资产的有限原型，**不是assembly-time或matrix-free生产实现**。以后要把同样的局部数学移到单元装配/流式作用，避免先存全局K；本批不重建这一套，也不移植邻支求解器。

FGMRES资源按实际restart、V/Z库、trace+port及恢复工作区计费。以65条complex128主向量为例，本案例从1944573到1177293行减少约39.46%主向量字节，但不代表因子或整机RSS同比减少；目标网格未资格化，不将这一比例当2TB足够的证据。最终仍需分布式trace、可扩展PC/有界coarse、matrix-free体作用、流式DtN及分块恢复，而不是扩大全局LU。

相邻分支只读快照：Task42extra `670a33398dfa9413c275772796611e085ef17c35`已授权有界FTTNN数值pilot（不能仍称未授权）；工程 `6490389b2e6b7f9a4d47269e50acb93d61dc4c41`为V21边界映射/来源收口；dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仅核对ref。本支不做其训练、参考PC、原尺寸端口或通用CSR任务，不向邻工作树下命令。静态凝聚是既有方法，不声称新发明；本次对象是此前未凝聚的标准tetra L5，不能拿旧hex混阶资格直接盖章。

## 8. 提交、最小测试与一次交付

先提交薄的backend/parent/新输入适配和公共数值小核，clean/targeted回归/dat validate后冻结source。只验证新分区/块公式/非零内部与端口rhs/恢复/原式及停止保存契约；复用已资格相位、q、K、会话。改过的相关测试在最终source上跑一次，相关Ruff/compile保留；不full pytest/CI、历史hash扫描、全仓索引或旧FLAT/P6/L5/M4重跑。文档与新文件身份一次检查，目标15min。网页不可取写NOT_VERIFIED，不为视觉重跑PDE。

待创建的one-run入口如下，未实现不得声称可运行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v69_saved_field_and_partition_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v69_exact_p5_condense_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v69_exact_p5_condensed_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v69_p5_modes1188.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v69_compare_verify_cost.dat
```

PRECHECK/PREPARE/VERIFY不暗藏global numeric；局部30阶LU逐次计费；M的backend由已保存的数学资格显式冻结。C失败或未接齐时，只对M选择原完整后备，不重解旧L5凑成功。已有合法场后的補消费仍用one-run并计入同一窗口。

交付`response_v69.md`、`outcomes/exact_tetra_condensation_p5_modes_v69.md`及紧凑records：D实际点语义和邻域；C同离散全场/原式、i/t映射、实际nnz/fill/局部因子和恢复；M模式完整结果；全部T_N1/研究费用/峰/gap/失败/修复及一个下一pilot。重写建议不算执行结果。旧task/review/response/raw不改，summary/README/两总账短追加。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

核对完整remote SHA/upstream/clean、closed/active null、清场和锁释放后交付暂停；不merge、不改master/邻支、不自动开新窗口。下载副本与远程报告必须是同一blob。

## 参考和本端边界

[MFEM静态凝聚定义](https://docs.mfem.org/4.8/classmfem_1_1StaticCondensation.html)说明局部内部块、接口Schur和完整恢复；[Nédélec第一类定义](https://defelement.org/elements/nedelec1.html)支持实体自由度和切向连续性，本站subdegree需换算为本项目Basix degree；[PETSc虚Schur接口](https://petsc.org/release/manualpages/KSP/MatGetSchurComplement/)明确原作用与预条件矩阵不同。仅用数学依据，不要求升级安装版本或引入MFEM。本文方案尚未在本端运行PDE，维数和块代数为推导；实际内存、时间和物理资格由V69取得。GitHub页面视觉未取得时保持NOT_VERIFIED。
