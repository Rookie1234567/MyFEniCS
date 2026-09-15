# Task39extra Review V21：双层凝聚的非可分三维与 p6/h7.5 有限鲁棒性验证

## 0. 决定、身份与新授权

**接受V20在固定original上的完整结果，保留其数学方法及低内存生命周期。本批不换PC：先新跑已冻结的h10非可分缺口，再条件式运行原始p6/h7.5和同一加密网格上的缺口。正常最多三场新的完整PDE，统一收口；不重跑已有original h10，不恢复旧中断notch。**

```text
repository                = Rookie1234567/MyFEniCS
branch                    = task39extra
review_date               = 2026-09-15
reviewed_base_SHA          = 63f5943d609e4b1393d175fdb79289853ca35c9e
latest_commit             = Close Review V20 with Response V21 and measured time-memory tradeoff
previous_review/response  = review_report_v20.md / response_v21.md
accepted_V20_source       = b337d215c3d278d0c1e715f53e28b69f7f0ee3fe
new_batch_identity        = review_v21_dual_condensed_geometry_h7p5
suggested_profile         = physical_p6_trace_p4_condensed_robustness_v21
execution                 = Z0 -> Z1 -> Z2(A) -> conditional Z3(B) -> conditional Z4(C) -> Z5
response_required         = response_v22.md
time_policy               = observe_only
ordinary_default          = unchanged
master_merge              = NOT_APPROVED
```

本批消除的blocker是：**已经在一个简单original上成功的双层凝聚，能否在非可分材料分布和较细网格上保持有效纠错，其内存增长主要来自全局p4因子还是局部缓存？** 鲁棒性在这里指对这两项有限变化的敏感程度，不是数学上的任意网格无关性或波长鲁棒性。

最终目标仍是单节点约2 TB内的0.7 nm、任意非可分三维周期单胞Maxwell散射。本批是16 GB个人笔记本上的13.5 nm验证，仍保留p4全局trace LU，不宣称最终生产可扩展性。

用户本轮明确指定p6/h7.5，并要求先验证现有方法。因此本报告仅对新profile覆盖V19/V20的“只允许original、不新增notch和h变化”限制：**明确授权新运行A/C，不撤销旧notch的关闭与unknown状态。** 用户提出的p3/p2/p1物理粗层、粗网格p6以及H6/H4/p2递归层级，均列为后续待讨论方向，本批不实施、不比较、不因失败自动切换。旧review、profile、checker、成功/负结果和账本不追溯改判。

执行前读取根/目录AGENTS、仓库原则、本task、最新review/response/summary。本批在同一分支连续完成，只有真实阻断或Z5收口才统一审阅；不得用小fixture通过代替可准入的完整三维计算。

## 1. 已证实基线与要回答的问题

来源为[Response V21](response_v21.md)、[V20结果](outcomes/dual_condensed_memory_v20.md)、[V20决策](outcomes/records/dual_condensed_memory_v20_decision.json)及[V5非可分结果](outcomes/balanced_coupling_v5.md)。GB=10^9 B，GiB=2^30 B。

| 基线及范围 | 已有结果 | 本批用途及边界 |
|---|---|---|
| V20 original，13.5 nm、p6/h10、252 hex、MPI1 | 112步；原A6残差9.73081785358e-7；全峰RSS 2,831,749,120 B；完整monotonic 1,479.177230 s | 同方法original h10基线，直接复用，不再运行 |
| V20求解阶段 | iteration/final-residual峰值2,278,993,920 B；p4在线226次均<=1e-10 | 与全过程含编译峰值分列，不互换 |
| V20存储 | p6 retained 51,272行；p4凝聚全局21,824行；p6缓存183,282,224 B | h10事实，不在h7.5硬编码这些维数/hash |
| V5 frozen notch，h10 | 8个材料单元改变；旧BAL_H 576步、原A6约9.35170552e-7，匹配参考与物理通过 | 复用几何/参考；不是新双层凝聚方法的成功记录 |
| V18 notch中断 | 494个完整PC，最后明确原A6第488步约5.47830721e-6；旧运行用户关闭 | 只保留历史，不续算、不当最终通过 |

所有值属于既有记录。本review没有执行PDE，也没有把旧reference的生成过程提升为当前zero-swap资格。

本批必须回答四个问题：A的非可分结构是否仍可完整求解；original从h10到h7.5是否出现明显迭代长尾；缺口加密后是否仍可求解；资源增长由哪个实际对象主导。不能只交三行PASS而不解释成本与限制。

## 2. 实验矩阵：固定方法，最多三场

| 标识/阶段 | 模型、目标网格 | 与谁比较 | 启动条件 |
|---|---|---|---|
| O10，已有 | V20 original p6/h10 | 基线112步/2.832 GB | 仅读取，不新运行 |
| A / Z2_NOTCH_H10 | V20数学方法，冻结非可分缺口，p6/h10 | 匹配V5缺口参考；与O10比较结构变化 | 身份、必要实现与安全检查通过 |
| B / Z3_ORIGINAL_H7P5 | original，p6/h7.5；同网格p4 | 与O10比较网格变化 | A通过，且B实际资源预审通过 |
| C / Z4_NOTCH_H7P5 | 同一冻结缺口，p6/h7.5；与B相同几何网格/DoF布局 | 与A比较加密；与B比较同网格材料变化 | A/B求解与可适用物理Gate通过，C资源预审通过 |

每场独立dat、零初值、新run root、自己的矩阵/因子与provenance。B/C共享**网格计划和数值算法**，不共享不同材料矩阵的全局LU。不得从A/B的解初始化后继，也不做跨case recycling。

建议输入为：

```text
input/task39extra/v21_z2_notch_h10.dat
input/task39extra/v21_z3_original_h7p5.dat
input/task39extra/v21_z4_notch_h7p5.dat
```

必须通过`python scripts/run_case.py <one_case.dat>`和已有可靠用户service/整树watchdog执行；每个dat仍只代表一场计算。阶段顺序是执行合同，不把三场藏成一个dat。

A若数值或匹配参考Gate失败，保存失败并跳过B/C，不自动换PC。B若数值/一致性/资源失败，跳过C；B仅缺h7.5匹配参考或跨网格差较大，不构成这些失败，按第5节的分轴裁决继续。C不通过即收口，不追加第四种几何、h8/h5、另一阶次或另一PC。

## 3. 几何与h7.5：先冻结实体，再生成网格

### 3.1 h10缺口以已验收的实际单元并集为准

从V5及V18已绑定artifact读取8个被改变单元的canonical vertices/boxes、材料tag与参考身份，保存不可变的`frozen_notch_geometry`描述和hash。A复现这8个实际单元的并集、同一h10轴与材料分布，证明y/z材料变化，不以“recipe名称相同”替代实体一致性。

**有一处必须显式处理的历史文字差异：** 旧task把缺口选择坐标描述为中心原点；当前`SimulationConfig3D.x_min/y_min`为0，`cell_notch.py`直接对实际坐标作`x>0`、`abs(y)<period_y/4`和z区间筛选。本批不得自行平移坐标或按文字重新解释缺口。以已有通过参考所绑定的8个实际单元并集为本批冻结定义，并记录该解释差异；这不是授权修改旧task或重定义旧物理。

若旧数组路径变化，沿run index/绑定文件定位并验证hash；不能找到并闭合实际几何/参考时记`GEOMETRY_OR_AUTHORITY_EVIDENCE_BLOCKED`，不猜坐标，不生成一个新的“类似缺口”。h10的原坐标与tag同样由实际模型确认，不能只凭上述源码片段代替artifact核验。

### 3.2 h7.5不是简单把单元数乘(10/7.5)^3

`mesh_target_nm=7.5`为本批固定值；保持boundary-fitted、轴对齐仿射hex与材料界面对齐。现有`_subdivide_piecewise_axis`按每个界面区间的长度除目标h后向上取整。

以普通original的x区间16.5/17/16.5 nm、y长度25 nm、z区间10/120/10 nm为例，仅按这些界面可推导：

```math
N_x=3+3+3=9,\qquad N_y=4,\qquad N_z=2+16+2=20,
\qquad N_{\mathrm{cell}}=720.
```

**720只是从当前规则派生的无额外缺口对齐面计划，不是已生成的网格结果，也不是本批硬编码单元数。** 它已是252的约2.86倍；为保持缺口实体，正式B/C网格可能更多。因此不沿用此前“温和加密约1.5–2倍”的口头估计，也不把2.832 GB线性放大作为内存准入。

B/C使用一份在Z0/Z1、所有新PDE之前冻结的共同轴计划：从既有boundary-fitted h7.5规则出发，加入表示冻结缺口**外边界**所必需的坐标平面；用同一规则生成两场的x/y/z坐标，original不挖缺口，C按冻结实体改材料。允许先精确合并相邻旧cell boxes，避免把并集内部无物理意义的每个旧单元面都作为必需平面；不能用外包围盒替代不等价的实体并集。

使用已有通用轴生成辅助函数作最小扩展，不引入非协调网格/新自适应平台。B/C网格节点、单元拓扑、FE布局应一致，材料tag和矩阵数值可以不同。共享计划会在original中加入少量中性分割面，需在h变化解释中明确：这是保持固定实体的boundary-fitted加密，不是均匀嵌套二分，也不是纯单参数谱实验。

A保持原h10网格不动；不可为统一网格规则重跑O10/A旧参考。B/C的实际单元数、轴坐标、最小/最大/中位方向步长、长宽比、材料体积与界面对齐均写入mesh manifest；不能把cell diameter与每轴target混为同一个h。资源不够就停止h7.5阶段，不暗中用更粗目标或不对齐网格代替。

### 3.3 固定几何必须被核验，不只是固定材料体积

对C采用冻结实体与新单元的几何包含/相交检查：每个积分单元应完全属于一种材料（容许既有坐标容差），不得横跨未解析材料界面后仍按中心染色。记录并集对称差体积/边界平面及tag覆盖，以体积一致加边界一致证明；只比较总体积不充分。

旧h10选择器可为A复现而保留；h7.5使用新显式geometry/plan身份，不能在新网格重新运行旧midpoint阈值并称“同一缺口”。证明真实分布仍不沿y均匀且不沿z挤出；不使用准2D、沿z模态传播或层平均替代三维求解。

## 4. 冻结数学与必要的参数化

### 4.1 不改成功的纠错机制

保持13.5 nm、grazing1度、azimuth0、s偏振、幅值1；50×25 nm周期、z=-10…130 nm、17×25×120 nm grating，air/Si材料值与V20相同。n_Si=0.999002304859+0.00182649365i、mu_r=1。上下边界和采样位置沿原定义。

p6/p4均在每场同一物理网格上采用Nédélec、complex128、双Floquet与单元凝聚。p6全局Schur只提供matrix-free作用，p4保留一份准确全局trace/端口LU。无全局A6/S6装配或LU，无42宏块/252份MUMPS；局部紧凑LU及恢复/RHS数据按**真实材料、尺寸、方向与算子身份**共享。

```math
A_{6,h}x_h=b_h,\qquad
C_h=P_{64,h}A_{4,h}^{-1}P_{64,h}^{H},
```

```math
\mathcal B_h r=C_hr+(I-C_hA_{6,h})H_{6,h}(I-A_{6,h}C_h)r.
```

外层保留空间PC仍用V19/V20的增广逆桥：

```math
\mathcal M_{\Gamma,h}=J_h\mathcal M_{\mathrm{aug},h}J_h^H,
\quad
\mathcal M_{\mathrm{aug},h}:
\begin{cases}
w=r_{FE}-BH_p^{-1}r_p,\\
z=\mathcal B_hw,\\
\alpha=H_p^{-1}(r_p+Dz).
\end{cases}
```

不能截P64并假定两个凝聚层满足直接Schur-Galerkin关系；桥中Hp仍是原端口块，不换成Hhat。每次外层PC为一次BAL_H、一次H6、两次准确p4作用；每个非零p4 RHS只有一次全局MatSolve，后端refinement与BLR关闭。实际为零RHS的特例沿原实现单列，不能人为填满计数。保留所有非零内部RHS、Bi/Di、MPC dual/primal与strict slave-zero语义。

H6的构造规则、次数与参数不变，在新网格上重新构建必要数值对象；不能把旧网格的对角、谱估计、LU或恢复矩阵当作可直接复用数值。完整单元物理项先相加后凝聚，不分别凝聚curl与mass。外层right FGMRES32、max2048、零retained初值；内部RHS特解允许存在。无inner KSP、MR新层、recycling、restart扫描或低精度。

外部物理未变，本批冻结原80通道的key/order/normal/phase/normalization与选择规则，并独立复算盘点。h改变可改变积分数据、边界离散响应和数据hash，不应改变外部物理通道；不因notch出现y变化而只留n=0，也不为通过内存减少DtN modes或积分精度。

### 4.2 不把固定h10的维数和hash锁死到新问题

当前V20入口只允许`Y3_ORIGINAL`，retained adapter、reference loader、checker及资源预审还存在h10固定尺寸/身份。将其**在新profile中**参数化为每场的case manifest，而不是删掉身份检查。

| 需要处理的旧假设 | 新合同 |
|---|---|
| `173802 / 51272 / 21824 / 252`等常数 | 从实际FE实体、MPC、端口与mesh计数导出；A核对既有值，B/C核对自身值 |
| 原始RHS/physical/p4 CSR固定hash | O10用于旧记录核验；每场绑定自己的原RHS、native map、CSR及材料身份 |
| 原始/缺口只由固定stage名称推断 | 输入显式model variant和冻结几何身份，stage只是调度，不能静默进入original |
| 所有case必须读取h10参考 | A读取同缺口同离散参考；B/C走第5节可缺同离散参考的明确分支 |
| `_v14_known_preallocation_gate`等旧固定库存 | 依实际rows/NNZ/局部class/工作向量作保守预审，不移除资源Gate |
| 释放后还需adapter/closure | 保留V20最小场packet与native A6，清理真实拥有者后再核验/后处理 |

physical_model_sha若历史schema含网格字段，h变化时它可改变。另存几何/材料实体语义hash、mesh hash、discretization hash及转换明细，证明“同物理不同离散”；不得硬填旧SHA，也不得改写旧hash定义。不同case矩阵之间不要求CSR数值相同；同一case的factor前/后、最后使用前内容必须一致。

优先复用`physical_dual_cell_condensed_lowmem_v20.py`、`physical_retained_outer_adapter.py`、p4 stack、`physical_p4_schur_v14.py`的通用流程。薄入口/显式profile可新增，不复制上千行runner。实际几何/网格辅助放`src/geometry/`，数值核心留`src/solvers/`，checker只读保存数据。

### 4.3 保留V20生命周期，不再开启内存优化子任务

必要form编译在p4 factor/H6之前；使用身份合格的现有cache，所有实际miss都在当场watchdog/计时内。**本批不要求人为制造cold miss、不清缓存、不重跑编译对照**；几何/尺寸引起的新张量与材料class重新生成。记录每场hit/miss，不能把warm收益当h鲁棒性或节省率。

450阶identity沿共享只读方式；p4原矩阵在factor live时安全保留，仍用`MATRIX_RETAINED_BACKEND_DEPENDENCY`。最终完整场与原残差/端口检查通过后释放不再需要的求解对象，释放后native A6再核验，再做完整official后处理。无新detach、malloc_trim、分项kernel、sum-factorization、ABI升级或MPI扩展。

## 5. 验证分三轴，不能把网格差异当成求解错误

### 5.1 每场必须通过的离散方程与物理一致性

| Gate | 规则 |
|---|---|
| 原A6 | 恢复完整场后，独立norm(b-A6x)/norm(b)<=1e-6；释放前后均核验，不以Schur/KSP内部量替代 |
| p4准确作用 | 每次非零输入一次MatSolve；在线原A4<=1e-10，计入真实成本，无隐藏refinement |
| 算子/桥/恢复 | 沿V20操作尺度等价<=1e-10，端口闭合<=1e-8；零尺度用既有绝对规则 |
| 输入与约束 | 不改变PC输入；有限、正确MPC/方向与严格slave-zero；缓存不随迭代增长 |
| 独立物理闭合 | abs(R+T+A_volume-1)<=1e-5、abs(A-A_volume)<=1e-5；被动性、通道功率求和及归一化正确 |
| 输出 | 完整复数E/H、近场/界面切向量、R/T/A/A_volume、全部80模式复幅值与功率，不只12个显著项 |
| 资源与证据 | clean source前后、完整input/mesh/material/mode/矩阵/数组hash，连续整树安全、zero-swap、终态与清场 |

同根setup合并完成必要局部/传递/凝聚检查：保持V20三种固定构造规则的trace/port/mixed向量，尺寸从当场对象生成，加一次真实PC计数核验，之后不重建solver即进入同一KSP。对新h/tag必须核验native与凝聚作用、P/PH和物理p4一致性，不能只依赖mock；数量有限，不另开旧PC误差诊断或多套projection。单次PC残差可能增加，不能据此代替完整求解Gate。

每8步保存Schur及恢复后原A6真实残差；每32步与终态保存retained/full checkpoint和可适用场评价。路径A的参考只用于评价；B/C无参考时记录`reference_field_error=not_available`，仍保存场和原残差，不输出假零值。保存/评价都纳入成本，失败先保存已完成证据，不能只在最后统一写大包。

### 5.2 同离散参考资格

A必须复用hash-bound的h10缺口fine参考及输出，核对同实体、h/p、MPC、原A6/RHS、外部通道、采样坐标。按既有限值验收：L2/scaled-curl、同坐标E/H与复模式向量相对差<=1e-4；R/T/A/A_volume绝对差<=1e-5；逐模式功率最大绝对差<=1e-6；近零项沿原绝对例外，不拟合相位。不能拿original参考比较缺口。

B/C先查现有索引是否有**同一实际加密网格**的参考；没有就明确`MATCHED_REFERENCE_NOT_AVAILABLE`，不默认启动p6全局direct、不构建新oracle、不为报告完整性超预算。此时只可授予`DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`，不能授予同离散全场reference-pass或连续精度资格。

**B/C缺同离散参考不阻断其求解与C的条件启动。** 它不等于降低1e-4门槛，而是该比较轴尚未运行；原A6、内部/端口与物理闭合仍是硬Gate，A已有匹配参考的要求不放宽。

### 5.3 跨网格误差趋势另列

比较O10与B、A与C的R/T/A/A_volume和同key80模式；场只在同一物理坐标、相同材料侧、同一规范相位下比较，不直接相减不同长度的系数向量。优先复用既有物理采样；界面/尖角使用已有单侧规则或预先固定的排除点并列明，不事后删除差异大的点。跨网格全域L2若没有合格共同积分/传递实现就标not_run，不能把采样差标成全域L2。

这部分是离散变化，不施加同离散1e-4/1e-5参考等价阈值。差异大时标`DISCRETIZATION_CHANGE_SIGNIFICANT`并解释：迭代可能成功，但尚未网格收敛；不因此改材料、通道或采样。两个h点不能确定收敛阶、连续真解或严格h-independent convergence。

## 6. 资源增长与笔记本安全

### 6.1 不以固定单元倍率代替容量预审

保持V20：tree cap=min(8 GiB,effective_available-reserve)，reserve=max(4 GiB,15% effective_total)；总数值库存<=6 GiB、同时临时池<=1 GiB，warning按原6 GiB配置。按既有动态方式处理自身RSS，避免重复扣减。MPI1、线程1、同一已资格化complex128/int32 ABI；不占用工作站或与另一heavy并跑，无OOC、作业swap和新增global swap为0。

Z0/Z1先用实际mesh/FE/局部class计数预审，不建立全p6矩阵。每场在大的分配之前检查：p4矩阵结构/预分配与向量布局；局部raw/oriented张量工作集、局部LU/恢复/Schur缓存及映射；H6/传递/原native算子；端口数据；74向量安全池随retained rows增长的量；保存、参考读取与后处理临时空间。所有大矩阵/packet必须ignored并预检disk，容量不足不以删必需输出解决。

p4使用实际symbolic估计与既有SYMBOLIC_SIZED_LOCAL_MUMPS_V11策略，numeric前检查factor和其他同时存活对象，numeric后再用原生统计和RSS复核。不新设压缩、不用used替代allocated偷偷放行；估计和实测不符如实标记。不得先过量分配再补资源账，不能用操作系统OOM当停止机制。

h7.5预审不通过则登记`H7P5_RESOURCE_BLOCKED_ON_LAPTOP`、发生阶段/对象/bytes/cap；B/C不暗换h8、p4粗网格或减少端口。A允许完成并独立保留成功。h7.5若被共同网格的容量挡住，本批就形成笔记本容量边界，后续是否移工作站由下一review决定。

### 6.2 必须取得的增长账

| 量 | 每场记录及比较意义 |
|---|---|
| 规模 | cells、各轴数量、p6/p4 storage/independent/interior/trace/port行数，区分存储行和独立DoF |
| p4瓶颈 | CSR NNZ/allocated容量、factor条目、allocated/used原生字段、symbolic/numeric时间、factor-live阶段RSS |
| 局部缓存 | raw/oriented class数，LU/恢复/RHS/Schur/映射去重payload，class/cell比例、构建前后和迭代末身份 |
| 外层纠错 | 原A6残差按步数/时间、n_iter、KSP action、BAL_H/H6、p4回代与native检查次数 |
| 成本 | 完整monotonic、setup、KSP与PC组成；能直接计量时分开p4缩减/回代/恢复及正交化，否则unknown，不从嵌套时间乱减 |
| 实测资源 | 编译/准备、分解与缓存、迭代、释放后处理四段RSS/PSS及全峰；compiler子集、cache状态、swap和清场 |

分列同方法的两个几何与两个h层次。不同h的全流程更大不叫“内存优化失败”；辨别增长是factor填充、局部class增加、Krylov向量还是编译。后端allocated不是RSS，数组payload不是实际释放量。不得从两个规模拟合可靠的0.7 nm/2 TB容量结论。

### 6.3 时间与次数边界

时间继续`observe_only`，所有耗时和保守账本照实记录。禁止恢复600秒setup、25/30秒PC、1800/5400秒进展或第64步0.1停止线；dat中的历史timeout字段必须按新profile明确记录不作时间veto，不能由launcher/service暗中恢复硬wall停止。保留max2048、非有限/breakdown、硬资源、输入/身份错误、监督失联和用户停止。

112、576或其倍数仅作对照，不是停止步数；没有“必须仍112步”的Gate。未达1e-6就不得发布通过；单场到max2048仍未收敛，登记本冻结配置的负结果，不自动重启KSP/加restart/降粗阶。

正常最多A/B/C三场，至多**整个批次一次**明确实现bug修复后的受影响formal重放；不为小修复重跑已通过且未受影响的模型。数值长尾、物理差、内存不够或缺参考不是bug重放许可。再次EIO/parent失联停止保存，不自动重启基础设施；旧失败/费用照旧。全部冷/复用成本在各自根内，不为表格补跑原始h10。

## 7. 有限鲁棒性如何裁决

通过最终残差并不等于效率鲁棒。分别报告：

```math
G_{\mathrm{original}}=\frac{n_B}{112},\qquad
G_{\mathrm{notch}}=\frac{n_C}{n_A},\qquad
G_{\mathrm{geometry},h7.5}=\frac{n_C}{n_B}.
```

只在分子分母都完整通过时计算。主比较同时列总时间、平均PC成本、factor增长和实际单元倍率；相同步数不等于相同工作量。A与旧V5的576步可作历史实现比较，但不是相同PC版本的网格鲁棒性分母。

作为**结果解读而非运行停止条件**，若两个网格比均不超过2且三场可适用Gate通过，可标`TESTED_RANGE_ITERATION_GROWTH_WITHIN_2X`；超过2则标`TESTED_RANGE_ITERATION_GROWTH_LARGE`，即使最终求解通过也承认效率退化。阈值是本批预先声明的工程标签，不是理论结论，不授予全波长鲁棒性；字段未测不能填1。

| 实际结果 | 收口与下一研究对象 |
|---|---|
| A/B/C通过可适用Gate，迭代增长温和、资源可控 | 保留V20数学方案，准备工作站的更短波长资格；仍标参考/连续精度边界 |
| A结构变化即出现明显退化，p4准确/桥恒等式仍通过 | 保存真实轨迹，下一轮优先定位几何下的粗细/接口响应；本批不更换PC |
| 求解保持强，但p4因子增长主导或阻断h7.5 | 下一轮聚焦全局trace因子规模与替代；不能以编译优化掩盖factor瓶颈 |
| 局部class/cache增长主导 | 下一轮研究有界局部缓存/流式表示，不误判为全局逆质量失败 |
| 有解但跨h输出差明显 | 分开登记solver成功与离散精度未资格化，不宣称真实结构精度已足够 |
| 资源/参考/实现阻断 | 写明尚未测出的轴；不得把not_run换成“算法不鲁棒” |

本批不输出“所有任意3D通过”；只涵盖冻结缺口、当前仿射hex能力、一个新目标h及13.5 nm。用户提出的降p/粗网格/更多层级不在本表中自动执行，是否值得做由这些新数据决定。

## 8. 实施、提交和证据

| 阶段 | 必须完成的工作 |
|---|---|
| Z0 | 只读核对HEAD/worktree、旧成功及关闭记录、A参考与canonical实体；生成B/C共同h7.5计划、静态容量初审；冻结case清单 |
| Z1 | 最小参数化及几何计划接线；集中完成新尺寸/tag、非零内部RHS、MPC、同实体加密、无参考分支、资源/释放/停止及旧profile回归；提交clean source |
| Z2 | 新A：同一正式根setup/必要checks后直接完整h10 notch，匹配参考、原残差、释放后处理与checker |
| Z3 | A通过后新B：实际预审、同根完整original h7.5；无匹配参考时按第5节分轴裁决 |
| Z4 | A/B可适用Gate通过且资源允许后新C：同B网格、冻结实体，完整求解及跨h比较 |
| Z5 | 从保存原数据独立重算Gate、迭代/时间/内存表，提交回应与总账，停止统一审阅 |

测试应使用真实共用代码，必要少量同根检查后尽快进入完整计算。不再重做BLR支持性、后端detach、旧失败方向诊断或服务平台研究。旧profile输出和数学默认不得改变；无法维持新几何/尺寸参数化而需要大规模重写时明确阻断，不绕过guard强跑。

提交计划：①新profile/输入/几何计划及最小参数化、focused tests；②各已完成场的轻量结果及时提交，不能等第三场才首次保存；③统一response/summary/registry与selective manifest。未经用户与最终review授权不merge master，不amend/强推，不整体迁移Task41/其他工作站分支。

```text
response_v22.md
outcomes/dual_condensed_robustness_v21.md
outcomes/records/dual_condensed_robustness_v21_compact.json
outcomes/records/dual_condensed_robustness_v21_decision.json
outcomes/records/v21_frozen_geometry_mesh_plan.json
outcomes/records/run_index.json                         # 增量，保留旧记录
outcomes/summary.md / outcomes/test_summary.md           # 增量
outcomes/selective_merge_manifest_v22.md
```

同步维护`docs/development_progress.md`与`docs/development_model_registry.md`。几何计划和compact保持轻量；大量canonical cell数组、场/矩阵/factor、完整timeline、cache放ignored并提供hash索引。每场保留input_original、resolved_config、run_manifest、input/physical/source SHA、run_summary、原始/恢复向量、模式与环境/MPI/资源/终态；比较数据不覆盖原数据。新账本用本批identity追加，旧政策占用、unknown及负结果不清零或合并冒充实测runtime。

Response第一屏必须给出四格模型表（O10复用、A、B、C），分别列求解通过、同离散参考、跨网格趋势、资源/时间和范围限制；随后回答“非可分是否可用、h7.5能否完成、迭代增长多少、p4还是局部缓存主导、下一项应研究什么”。未运行字段写not_run与具体前置原因，不使用笼统WORKER_FAILED掩盖数值/资源/工程区别。

## 9. 来源与本review交付边界

本报告固定第0节远程快照。当前成果见第1节；数学与资源合同继承[Review V19](review_report_v19.md)、[Review V20](review_report_v20.md)，早期实体/加密原则见[task](task.md)及[V18回应](response_v19.md)。本报告的新授权只修改本批实验范围和参数化需求，不改历史事实。

本次特别核对的代码：`src/common/config_3d.py`的坐标约定；`src/geometry/cell_notch.py`的midpoint编辑；`src/geometry/mesh_builder_3d.py`的piecewise界面对齐；V20 dat/worker、retained adapter和原checker的固定模型假设。实际canonical缺口数组、h7.5网格和资源容量仍须由Codex在Z0/Z1核验；本review的720单元是规则推导，不是新PDE测量。

ChatGPT本次只新增review，不运行项目PDE或修改求解源码。本文件应完成fenced math、表格/链接、local preview和远程回读；GitHub网页渲染无法访问时必须如实报告，不能声称已目视通过。下一批通过也仅是有限tested-range资格，不是0.7 nm、2 TB或所有复杂三维的生产证明。
