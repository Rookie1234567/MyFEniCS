# Task39extra Review V20：保留双层凝聚的内存与生命周期优化

## 0. 决定、身份与本轮权限

**接受V19在固定original上的112步完整通过。下一批不再筛选PC，而是在保持p6/p4双层单元凝聚、原BAL_H/H6和准确p4逆不变的条件下，集中处理编译叠峰、显式恒等缓存、p4矩阵与因子共存、最终恢复后的对象释放。正常路径只运行一场整合后的original，不逐项各跑一场，不恢复notch。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-14
reviewed_base_SHA           = 802a38722ba3d52b4ad079676a3e5807fa4fe961
latest_commit              = Record V19 original pass and full time-memory tradeoff
previous_review/response   = review_report_v19.md / response_v20.md
accepted_numerical_source  = 8eff068b06f4713cc6d1281c92ed82d370060403
V18_original_source        = 8a2d5cbba6ed834a6d731a30dd3735c8824fa762
new_batch_identity         = review_v20_dual_condensed_memory_lifecycle
suggested_profile          = physical_p6_trace_p4_condensed_lowmem_v20
suggested_input            = input/task39extra/v20_y3_lowmem_original.dat
execution                  = Y0 -> Y1 -> Y2 -> Y3(original only) -> Y4
response_required          = response_v21.md
time_policy                = observe_only
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

本批消除的blocker是：**已经显著加速的双层凝聚，是否因不必要的同时存活对象而付出可避免的内存峰值？** 不是重新寻找低内存弱PC。最终目标仍是0.7 nm、任意非可分三维周期单胞、约2 TB整机内存；本批只验证13.5 nm固定original，仍保留增长型p4全局trace LU，不能宣称已解决短波可扩展性。

用户明确要求按上一轮代码分析尝试。因此，仅对新profile授权：编译前置；精简等价缓存；有证据的p4矩阵提前释放或安全回退；原A6最终核验与完整场保存后释放不再需要的求解对象，再做official后处理。**这覆盖V18/V19对新profile的“必须保留因子到最终评价结束”要求，不修改旧profile、checker及历史结果。** 旧notch继续用户关闭，本批不恢复、不重跑，也不另开新notch；不运行5 nm/0.7 nm，不影响Task41及工作站线，不新建分支。

先读取根和目录AGENTS、仓库原则、本task、最新review/response/summary及本报告。连续完成本批，不在每个小检查之后停审。发生真正的正确性/安全阻断时保存证据，而不是为了节省某个百分比继续改变算法。

## 1. 已知事实与可优化对象

来源为[Response V20](response_v20.md)、[V19详细结果](outcomes/dual_cell_condensed_v19.md)、[决策](outcomes/records/dual_cell_condensed_v19_decision.json)及[compact](outcomes/records/dual_cell_condensed_v19_compact.json)。以下数据是既有measured/derived记录，不是本review新运行。GB=10^9 B，GiB=2^30 B。

| 同一original，MPI1，完整流程 | V18仅p4凝聚 | V19双层凝聚 | 范围说明 |
|---|---:|---:|---|
| 外层步数 | 564 | 112 | FGMRES32、同一原A6精度要求 |
| 原A6最终真实残差 | 9.92314718715e-7 | 9.73081785358e-7 | measured，均不大于1e-6 |
| process-tree峰值RSS，B | 2,528,460,800 | 3,965,534,208 | measured，包含JIT/compiler及最终输出 |
| 常驻数值库存，B | 1,830,284,886 | 2,031,387,110 | 对象/后端账，不是RSS |
| 完整monotonic时间，s | 6,609.661379 | 1,352.012123 | 含准备、评价及清理，不相加嵌套计时 |
| p4全局准确系统 | 21,824行 | 21,824行 | 内容hash相同；不是重新压缩p4 |

V19最高RSS发生在约155.140523 s的p6 setup：worker=2,337,185,792 B，cc1=1,574,236,160 B，其余case parent/MPI/gcc=54,112,256 B。V18峰值位于另一个阶段；不能把两个worker值相减当作全部数值工作集的因果差异。

V19新增p6数组201,102,224 B；65个V/Z向量的派生载荷减少127,431,200 B。新增缓存可以抵消向量节省，**没有一张原全局p6 AIJ或p6 LU可再删除**。历史Task035b直接法35.024→16.998 GiB同时避免了完整装配与大因子，不能外推为本批还应减半。

| 代码位置/对象 | 已核对事实 | 本批处理 |
|---|---|---|
| `physical_p4_schur_v14._v14_q4_q5_fullspace` | 先进入p4 factor stack、再建H6、最后建retained adapter | 把编译准备从这条依赖链中前置；不在大因子之后首次编译p6矩阵核 |
| `physical_retained_outer_adapter.RetainedOuterAdapter.build` | 此时才调用完整p6双线性form的`fem.form` | 借用已准备的同一compiled form，记录是否命中缓存 |
| `hcurl_assembly_time_condensation` | 每个定向类创建450阶float64单位矩阵，三个字段共享该类同一数组 | 当前恒等路径改为隐式identity或同尺寸只读共享，不把真实投影误删 |
| `cell_condensed_stack`及`P4CellCondensedInverse` | p4矩阵和因子在context中长期共存；矩阵已分配载荷约232,205,060 B | 先核验后端借用关系；安全才分离矩阵/因子生命周期 |
| 最终恢复与退出 | 完整p6场已可独立保存，但p4因子/p6缓存留到official输出后 | 保存并核验必要packet后释放不再使用的对象，保持后处理完整 |

显式identity按12×450×450×8计算为19,440,000 B；三个字典字段本来就别名共享，不能再乘3。只共享一张450阶identity时派生减少17,820,000 B；隐式表示最多移除上述19,440,000 B数值载荷，不等于同量RSS必然下降。

## 2. 冻结数学、输入与安全范围

保持原单胞50×25 nm、z=-10…130 nm、Si/air、13.5 nm、1°掠入射、phi=0、s偏振、幅值1；n_Si=0.999002304859+0.00182649365i，mu_r=1。保持252个轴对齐仿射hex、p6/h10、同网格p4、原积分、双Floquet与完整80个DtN通道。正式前核对而不硬编码跳过实际盘点。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
ordered_mode_sha256   = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
original_rhs_sha256   = e8ece14d273d8bcdec672f2e29ac8c62971bb0d0fe4af7cc63e741df21934686
p4_CSR_content_hash   = 19b9fbf759e6dc586d1316b53c69099647bd3a23e43378535b718c1db2c218d8
```

外层仍为51,272维trace＋端口上的right FGMRES32，零保留初值、max_it=2048；完整恢复场可含原内部RHS特解。p4是一份21,824行准确凝聚LU，BLR关闭、后端refinement关闭，原排序/缩放/主元/线程等设置不变。一份非零p4输入只做一次全局MatSolve；内部RHS缩减和完整恢复不省略。

```math
\mathcal M_{\Gamma,6}=J\mathcal M_{\mathrm{aug}}J^H,
\qquad
\mathcal M_{\mathrm{aug}}:
\begin{cases}
w=r_{FE}-BH_p^{-1}r_p,\\
z=\mathcal B_{6,H}w,\\
\alpha=H_p^{-1}(r_p+Dz).
\end{cases}
```

原BAL_H仍为两次准确p4修正加一次H6；每次外层PC只调用一次BAL_H。不能截P64后假定Schur-Galerkin关系成立，不能用Hhat替代原Hp；原A6、H6、传递及所需完整空间scratch在求解中继续保留。不得新增内层KSP、BLR、MR、recycling、42宏块、局部谱空间或低精度近似。

保留已资格化WSL/Linux、PETSc3.19.6 complex128/int32、DOLFINx0.10/Basix0.10、MUMPS5.6.2、MPI1/线程1；不升级ABI或自行修改后端源码。正式入口仍为一个dat对应一次`python scripts/run_case.py`，通过已有用户service薄入口启动，完整watchdog必须先于所有本场编译与计算。

## 3. Y0/Y1：集中实施四项工程优化

### 3.1 编译先于大因子，不在统计外预热

先从V19已有events/resource timeline确认准备与输出使用的form签名、编译窗口和对象生命周期；不重跑旧PDE。优先复用现有DOLFINx/FFCx接口，把“准备compiled forms”与“构建数值solver”解耦。建议增量接口为pre-factor form-preparation及adapter延迟绑定PC；不复制大型runner。

期望顺序：

```text
同一case watchdog和计时开始
→ 最小网格/空间/材料/form准备
→ 必要p6/p4及评价内核顺序编译，保存签名/选项/缓存事实
→ 释放不再需要的临时编译引用
→ 构建准确p4因子、H6、p6局部缓存及原桥
→ 同一case求解、原残差核验、释放、完整后处理
```

要先编译的是完整单元矩阵所需rank-two核，不是把已有rank-one action核当作它。保持原完整form、quadrature、编译优化选项及标量精度；本批不同时改成分项kernel、不换编译器、不降低积分精度，也不重做全部软件栈。不得为了复用form先构建不再需要的全局A6/S6矩阵。

**缓存合同：** 小测试使用工程缓存；正式场用独立ignored缓存目录或可验证的等价安排，不删除用户共享缓存。尽量复用其他合格模块，但在正式watchdog范围内至少实际编译一次造成旧峰值的同一p6完整form模块，记录cache miss、编译子进程及完成事件；可在独立目录中不预置该模块及其完成标记，不改生成代码来强造新签名。构建及求解随后复用本场生成的模块，不重复编译。

若现有API无法可靠控制单模块缓存，不为此开发缓存平台：记录实际hit/miss及缺口，允许继续同一数值验证，但不能把仅warm命中带来的低峰写成“已证明编译顺序优化的收益”。所有实际编译仍计入冷/复用混合全过程；不从RSS剔除cc1，不移到未监督的另一个进程。无需重跑旧V19作人为冷基线。

构建期临时raw/oriented张量、检查数组和大字符串不应被debug/closure长期持有；在最后使用点释放，保留小hash而非复制完整矩阵。当前raw/类缓存已做共享的部分不得重复优化或将临时预留误当作实际数组。

### 3.2 缓存精简：先做确定的恒等表示，保留真实物理数据

优先为当前完整阶次凝聚引入有明确shape/dtype/语义的identity标记及统一apply接口；无法以小改动完成时，采用同尺寸只读identity共享。一般选择性路径继续使用真实矩阵，不更改旧默认行为。

逐个核对调用者：内部RHS投影、solution embedding、residual projection、数组库存和hash/checker必须识别隐式identity。不得只把字典设为None却让调用者执行矩阵乘法；不得为hash将identity展开成大型矩阵。表示hash改变可以接受，但逻辑identity和数学作用必须可独立复算。

保留12类准确局部LU、恢复、RHS缩减与局部Schur的正确共享。禁止把左右耦合假定共轭，禁止只因尺寸相同而共享不同材料/几何/方向算子。顺手消除被证明确实无用的重复map/端口副本即可，不做全仓数据结构重写，也不删数值检查来获得收益。

### 3.3 p4矩阵提前释放：先解决所有权，不把危险操作当节省

**新增的后端核查：PETSc v3.19.6的`MatConvertToTriples_seqaij_seqaij`在取得SeqAIJ数值数组后将`mumps->val`指向它，而不一定另复制数值。** 参见第9节固定tag源码。因子和原矩阵是两个对象，不足以证明原矩阵可立即销毁；关闭ICNTL10也不自动证明后续solve、误差分析或销毁不会访问原数组。

因此必须先在当前实际安装的wrapper/PETSc/MUMPS路径上核验：转换的借用关系、numeric后的有效依赖、solve/refinement/error-analysis设置、销毁顺序、矩阵引用计数及可用公开API。不得通过ctypes改私有结构指针、手工free后端数组、屏蔽保护或升级ABI来“完成”释放。

只在有可靠生命周期依据时，做一个同后端的小型复非Hermitian/端口增广fixture：factor一次，原矩阵释放前后多个不同RHS及重复/线性求解一致；释放后安排普通内存复用以避免只因旧页尚未覆盖而假通过；清理无悬空引用、重复释放或泄漏。测试通过是补充证据，不替代源码/接口依赖核验。

| 预先确定的依赖结论 | 本批唯一配置采用的策略 |
|---|---|
| 原矩阵可经现有安全接口真正释放 | 保存factor前后CSR/hash、向量布局与必要元数据后释放；保持同一factor反复回代 |
| 后端仍借用原数值或无法证明安全 | `MATRIX_RETAINED_BACKEND_DEPENDENCY`；保留矩阵，不把整个批次卡住 |
| 仅Python引用释放但后端仍持有全部数据 | 如实报告“未物理释放”，不记账为矩阵载荷消失 |

fallback允许用**同一stored结构与数值**的精确预分配缩小空余容量；考虑完整凝聚后的Bhat/Dhat/Hhat支撑，不用drop tolerance删除条目，不改变模式。这样可保留原CSR内容hash。若需要大范围重写预分配，保留原矩阵并继续其余三项，不追求本轮一定释放232 MB。

不允许为绕开借用而另复制整张矩阵/数值数组后仍声称全部释放；任何必需替代缓冲都计入新常驻和峰值。矩阵释放与其预分配收益不可重复相加。p4全局因子只能在最后一次PC之后释放，不能每次调用都重分解。

### 3.4 求解后释放：先保存完整场并核验原A6，再进入official评价

V18/V19保留因子到最终评价结束是旧对照策略，不是数学必要条件。本批明确允许改变它：

```text
KSP结束
→ 恢复并保存完整p6 x、原b、retained y/alpha及最小provenance
→ 独立native A6最终残差、内部/端口恒等式通过并保存
→ 保存p4/p6最终identity、计数和资源；断开不再使用的回调
→ 销毁p4因子及剩余矩阵、H6/PC和不再需要的p6凝聚缓存
→ 保留原native A6、网格/材料/端口及必要评价对象
→ 再做一次释放后的native A6核验及完整E/H、功率、体吸收、80模式评价
→ 最终清理、结算
```

额外释放后A6核验及其计时计入本场；不需要再恢复/求解一次PDE。若依赖分析发现某个恢复对象仍被最终评价使用，就精确保留该对象，不退回整套solver保留，也不为了释放先丢必要场信息。

处理所有权而非只调`destroy()`：现有`AssemblyTimeCondensedSystem.destroy()`只销毁PETSc矩阵；拥有者应显式清掉已不再需要的cache、cell/map引用和closure，借用者不能提前销毁共享缓冲。已有p4适配器的owning清理可复用；测试正常退出、提前失败和重复destroy。释放事件必须对应真实对象生命周期，不能先减ledger后仍由callback持有大对象。

本批不新增malloc_trim、gc阈值扫描或系统allocator设置。允许普通必要gc用于解除已死引用，但不得把RSS未立即下降解释成数学对象仍必需，也不得承诺释放载荷会等量归还RSS。只做上述显式生命周期，避免同时加入另一种难以归因的堆调优。

## 4. 数学不变性与必要小检查

本批改变内存表示和执行顺序，不改变如下消元关系。内部块i为单元内部，t为独立trace，alpha为原端口：

```math
\widehat g_t=g_t-V_{ti}V_{ii}^{-1}g_i,\qquad
\widehat g_p=D_iV_{ii}^{-1}g_i,
```

```math
c_i=V_{ii}^{-1}(g_i-V_{it}c_t-B_i\alpha).
```

保留一般非零Bi/Di和内部/端口RHS，Hhat完整处理；已MPC作用的dual storage不再次乘C^H。输出strict slave-zero不放宽。参考只参与评价，不能用于初值、PC、算子或选策略。

Y0/Y1把必要小检查合并完成：复数非Hermitian局部代数；identity显式/共享/隐式作用；一/两单元及Floquet方向；完整form预编译复用；p4后端所有权fixture；可选精确预分配结构一致性；释放后的完整场、native action和小型后处理；normal/error/double-destroy；旧profile默认与新分流/checker。未受影响的BLR、Schur诊断、服务生存等已通过检查不重新研究。

算子/局部恢复及桥的操作尺度等价限值沿V19，至多1e-10；小纯代数oracle沿1e-11。p4新建矩阵在numeric前后、可能释放之前保存原生CSR内容hash并与已绑定值一致。仅改变容量不会改变getRow数值流；若结构或值变了，先定位，不用“生命周期优化”解释未核对的算子变化。

p6中Schur/LU/恢复的数值hash与逻辑映射应保持可比；identity的表示hash与语义hash分开，不能要求被删除数组仍存在或为通过旧hash而重新展开。新checker按新对象状态核验，旧checker对旧记录不放宽。

## 5. Y2/Y3：同一正式根的准备、核验和完整original

正常路径只有一场新original。Y2在这场的同一watchdog根完成编译、setup与有限检查；通过后同对象直接进入Y3，不退出重建factor。新profile通过公开dat/resolve/manifest记录所有已确定策略，不在求解过程中切换配置。

若实际启用p4矩阵释放：在这份真实factor上允许释放前求一次已有01输入，释放后按01/02/09最多三次回代检查原A4<=1e-10、场/旋度<=1e-8及strict-zero；保存独立原action结果并及时丢弃参考工作向量。这最多4次额外回代，单列诊断成本，无第二份factor、无新参考。若矩阵必须保留，复用既有p4资格，不为配表重跑完整p4控制。

沿V19在同根做三个固定trace/port/mixed向量的native恢复恒等式和一次真实PC计数检查；费用单列，无“单次必须降残差”Gate。所有通过后直接完成original：FGMRES32、max2048、时间observe_only；每8步保存Schur与恢复后原A6真实残差，每32步保存y及场评价，最终回到原方程裁决。

**112步是已测基线，不是新停止线。** 不强求逐字节相同迭代轨迹，不按结果改restart/精度/最大步数；若轨迹显著不同，报告身份及作用差异而非自行把它归为舍入。保留非有限、breakdown、最大步数、用户停止及资源安全线；不恢复旧第64步0.1硬筛选或wall timeout。

| 最终Gate | 要求 |
|---|---|
| 原A6 | full explicit norm(b-A6x)/norm(b)<=1e-6，释放前后均核验；不以Schur/KSP残差代替 |
| p4在线准确性 | 已建准确factor、每次非零输入一次MatSolve、原A4<=1e-10，无隐藏refinement |
| 恢复与端口 | 内部/native恒等式操作尺度<=1e-10，端口闭合<=1e-8；零尺度按原绝对规则 |
| 场与采样 | L2/scaled-curl<=1e-4；同坐标E/H、界面切向场沿原1e-4和近零绝对例外 |
| 功率与守恒 | R/T/A/A_volume对参考绝对差<=1e-5；两项独立闭合<=1e-5 |
| 80模式 | 原key/order/phase/normalization；幅值向量相对差<=1e-4，逐模式功率最大绝对差<=1e-6 |
| provenance/资源 | source/input/physical/mode/对象与保存数组身份完整、全树安全、零swap、终态及清场 |

新postprocess checker应验证“最后PC及最终残差/packet之后释放，official后处理之前释放”，而不是删除旧的生命周期Gate。p4矩阵若留存到factor销毁、某个p6对象确需评价时留存，必须记录其准确状态。缓存不随调用增长；KSP和factor计数分别列setup诊断与正式求解部分。

## 6. 资源、比较与停止合同

### 6.1 原安全线不提高，时间继续observe_only

启动tree cap=min(8 GiB,effective_available-reserve)，reserve=max(4 GiB,15% effective_total)，按原动态方式避免重复扣自身RSS；数值常驻总库存<=6 GiB、同时临时池<=1 GiB；作业swap与新增global swap为0，无OOC，一次一个heavy。JIT及编译后代属于同一case树，不另设不可见预算。

预算/库存是安全预测，不是实际内存。记录RSS/PSS、allocated/used、数组载荷、临时上界和Python/PETSc实际对象，不将释放数值载荷直接从历史RSS扣除。保留系统余量和服务完整清场；不改WSL宿主内存、swap、linger或磁盘设置。

正常一场；最多允许一次有明确错误定位的实现bug修复后受影响formal重放，同公式/同输入/不扩cap，旧失败与费用保留。数值不收敛、内存未省、后端矩阵不能释放都不是重放许可。再次I/O或parent失联则停止并保存，不自动重启基础设施；每个阶段先保存再进入下阶段。

### 6.2 不用warm命中或降低输出量制造节省

主要基线为V19完整original：3,965,534,208 B、112步、1,352.012123 s monotonic；V18的2,528,460,800 B/564步/6,609.661379 s作为较低内存对照，不重新运行。历史约3.5 GB与p4-only数据只作有标注背景，不进入本批主比值。

从旧raw轨迹尽量重算四段峰值：编译/准备、分解/缓存构建、迭代、恢复/后处理。旧粗phase不足时用事件边界、PID与时间戳映射并记录误差；无法获得则标unknown，不伪造，也不重跑旧场补字段。

新场用同一个父watchdog连续覆盖全部阶段，输出全峰、阶段峰、峰值时各PID RSS/PSS、算子/factor是否已存在、cache hit/miss、释放前后样本及最后使用事件。主峰始终包括compiler，另列“没有compiler时的已观测求解阶段峰值”作诊断，不改名为全过程峰值。

```math
R_M=\frac{M_{\mathrm{new,full}}}{3965534208},\qquad
R_T=\frac{T_{\mathrm{new,monotonic}}}{1352.0121227929922}.
```

比值只能称本次已运行流程的观察比较；缓存覆盖、诊断附加回代和生命周期改动必须列出。仅warm命中时，不宣布编译前置消除了多少冷启动峰值；不将单场微小差异称统计稳健收益。若数值等价但资源无收益仍收口，不以10%、50%或3.5 GB为强制通过线，不再接着调更多参数。

安全通过不等于省内存；全峰下降与常驻下降分开，时间增加也必须报告。只在数学/物理通过后讨论采用新路径；未通过则保留V19为当前快路线、V18为较低峰基线。

## 7. 实现边界、阶段与提交

| 阶段 | 交付与停止点 |
|---|---|
| Y0只读盘点 | 复用V19数据、冻结SHA/输入/策略及source依赖；有限整理原phase峰，不另建诊断平台 |
| Y1最小实现/小检查 | form预编译、identity缓存、p4释放可行性或fallback、最终packet/清理、同配置checker；提交clean source |
| Y2同根准备 | 全程受监督的实际编译、对象构建、原p4/桥身份及有限核验；同对象进入Y3 |
| Y3一个完整original | 同一KSP到最终裁决，原残差后释放与完整物理；成功/负结果/停止均留证据 |
| Y4统一收口 | 重算Gate及资源取舍，写Response V21、registry、progress与selective边界，推送后等审阅 |

优先在`physical_retained_outer_adapter.py`和现有stack加入准备/绑定/释放生命周期接口；数值表示辅助函数放`src/solvers/`。允许给已有通用runner加可选factory/hook，但旧默认顺序不变。不要复制上千行V14 runner，不在benchmark里实现新的数值核心。

p4提前释放这一个优化被后端阻断时，立即记录并安全保留，完成其他优化；不做新MUMPS绑定或持久化factor系统。整个批次也不同时改分项编译、sum-factorization、MPI并行、端口数量或H6架构。

提交计划：①最小实现＋focused tests＋显式profile/dat；②完整original轻量证据和新checker；③response/summary/registry。每次commit说明单一阶段，正式计算源码clean并绑定before/after；不amend、强推、批量merge/cherry-pick，不覆盖旧报告、旧数据或未知账务。

## 8. 必需证据与最终决定

```text
response_v21.md
outcomes/dual_condensed_memory_v20.md
outcomes/records/dual_condensed_memory_v20_compact.json
outcomes/records/dual_condensed_memory_v20_decision.json
outcomes/records/run_index.json                  # 增量
outcomes/summary.md / outcomes/test_summary.md   # 保留历史
```

同时维护development_progress、development_model_registry及依赖分组selective manifest。新账本只追加`review_v20_dual_condensed_memory_lifecycle`；V19已测1474.858420 s、旧V18结算、43200/600秒政策占用及actual unknown均保留，不清零、返还或混作本场时间。observe_only不意味着隐藏或丢弃费用。

每个正式根保持one-dat-one-run的input_original、resolved_config、run_manifest、input/physical/source SHA、run_summary、MPI/线程/ABI、资源轨迹和artifact hash。新compact应包含优化启用/未启用原因、borrowed-buffer判断及依据、identity语义、CSR释放前身份、引用与销毁时间线、分阶段峰值及最终物理结果；重型数组和完整日志仍在ignored，不创建永久大对象审计平台。

最终第一屏必须回答：

1. 编译是否真的发生在大因子前、冷/复用状态是什么，是否避免了已知叠峰？
2. identity/缓存实际减少多少载荷；p4矩阵是否真正释放，若未释放为何？
3. 哪些求解对象在最终评价前释放；完整场、原A6与official输出是否仍正确？
4. 完整/迭代/后处理峰值和总时间各变化多少；原112步收敛能力是否保持？
5. 采用新lowmem配置、仍保留V19，还是存在时间—内存取舍？下一blocker是什么？

任何策略仅部分实现必须明示。未省内存也允许数值PASS，但不得称工程目标完成；全峰下降却因warm-only无法归因时，明确`MEMORY_COMPARISON_WITH_CACHE_QUALIFICATION`。不因某个可选优化失败否定已保持的原数值方法，也不把本机一次正结果当作0.7 nm或任意三维production资格。

## 9. 来源与本review验证边界

仓库事实固定第0节SHA。主要代码：`physical_p4_schur_v14.py`的stack/H6/adapter次序，`physical_retained_outer_adapter.py`的form编译和缓存，`hcurl_assembly_time_condensation.py`的共享identity与destroy语义，`p4_cell_condensed_inverse.py`的单次回代与所有权，`p6_cell_condensed_action.py`的借用关系。数学及最终Gate沿[Review V19](review_report_v19.md)，旧结果见第1节链接。

- [PETSc v3.19.6 MUMPS源码](https://github.com/petsc/petsc/blob/v3.19.6/src/mat/impls/aij/mpi/mumps/mumps.c)：`Mat_MUMPS`的val/val_alloc与`MatConvertToTriples_seqaij_seqaij`表明存在原数值数组借用；这不是可以安全删除矩阵的证明。实际安装补丁与后端执行语义仍须核对。
- [DOLFINx JIT源码](https://docs.fenicsproject.org/dolfinx/main/python/_modules/dolfinx/jit.html)：说明form编译、cache_dir和选项组织；main仅作接口背景，实际使用已资格化0.10栈，不按在线新版本升级。

ChatGPT本次只新增review，不实现或运行项目PDE。文档须检查fenced math、表格、链接及本地预览；无法核验GitHub rendered view时如实说明，不声称网页视觉通过。本报告定义的内存减少目标是待测工程假设，不将已知对象字节数相减冒充未来RSS。
