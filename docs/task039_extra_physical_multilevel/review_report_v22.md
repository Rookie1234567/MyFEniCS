# Task39extra Review V22：先关闭p4精度缺口，再做内存不增加的单步加速与h7.5完整对照

## 0. 决定、范围与执行身份

**接受旧B已取得的原A6收敛与成本证据，但不将其58/59的checker改成PASS。本批在同一`task39extra`分支、个人笔记本的既有合格环境中，先处理那一次p4精度超限，再优化传递、A6/H6与准备过程；可条件采用共享内存多线程，正常路径最终只跑一场完整original p6/h7.5，和已记录的93.02分钟比较。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-20
reviewed_base_SHA          = 4d0f85397501d8a04f9eb62140cd1dd9789fcf85
base_latest_commit         = docs(task39extra): finalize V23 evidence delivery
previous_review            = review_report_v21.md
previous_execution_rules   = user_authorization_v22_b_capacity.md + user_authorization_v23_physical_memory.md
latest_response            = response_v24.md
baseline_formal_source     = d3596ac31bdabc2bb9233963adea3e91ddc2f220
batch_identity             = review_v22_laptop_speed_after_a4_fix
suggested_new_profile      = physical_p6_trace_p4_condensed_laptop_speed_v24
response_required          = response_v25.md
execution                  = P0 -> P1 -> P2 -> conditional P3 -> P4 -> P5
formal_MPI                 = 1
threads                    = 1; optional qualified 2/4 shared-memory kernel threads
formal_full_PDE             = one original p6/h7.5 normally
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

Review编号继续为V22；执行profile采用新的v24后缀，是因为资源执行profile已经用到v23，两者不是同一编号序列。若建议profile名称已被占用，选择唯一新名称并记录映射，不覆盖旧profile。

本批消除的blocker是：**已有双层凝聚在网格变大后仍可收敛，但每次PC成本偏高；准确p4调用还有一个有限精度缺口。必须先保证每个返回的粗修正合格，再以不增加整场内存的方式减少重复计算和数据搬运。** 这服务于约2 TB内的0.7 nm任意非可分三维目标，不宣称本批已解决短波或全局粗因子增长。

用户明确授权了本批修复、性能实现、多核条件试验和一次h7.5回归。本review仅对新配置覆盖前驱的“禁止新内核/线程变化”和“每个非零p4必须恰好一次回代”：允许第3节的有界显式精化及第5节的内存中性线程。其他物理、离散、容差和安全要求不放宽。旧review、109份冻结历史文件、27个旧profile及其后新增的历史记录保持原内容和分类；列表实际由基线遍历核对，不仅硬编码数量。

不运行A、C或新notch，不运行5/2/0.7 nm，不迁移或干预工作站、task39para/Task41、正在执行的2 nm进程。不新增p3/p2/p1、H4、多层PC、BLR、PML、recycling或新的粗网格。读完本报告后连续执行，仅在真实阻断或P5收口停审，不要求每个小测试后等用户批准。

## 1. 已有证据与本批比较基线

来源：[Response V24](response_v24.md)、[V23 compact](outcomes/records/dual_condensed_physical_memory_v23_compact.json)、[V23 checker](outcomes/records/dual_condensed_physical_memory_v23_checker.json)、[V19分项计时](outcomes/dual_cell_condensed_v19.md)、[V20生命周期](outcomes/dual_condensed_memory_v20.md)。GB=10^9 B，GiB=2^30 B。下列历史值不重跑凑表。

| 对象/口径 | 基线值 | 数据身份与边界 |
|---|---:|---|
| B：13.5 nm，original p6/h7.5，MPI1 | 9×5×22=990单元；80通道 | measured；不是720单元，也不是7.5 nm波长 |
| 完整流程monotonic | 5581.178597819002 s，即93.0196433 min | measured；本批主要时间分母，不用口头90 min |
| KSP区间monotonic | 4737.310983555995 s | measured；不等于含setup PC的watchdog solve阶段 |
| 外层 | 126步；127 BAL_H/H6；254逻辑p4调用 | measured；含一次setup PC |
| 原A6最终残差，释放前/后 | 9.2831649554582e-7 / 同值 | measured；达到1e-6，但无同离散高精度参考 |
| 在线p4 | 253/254合格；PC2第1次rho=2.8870661155266027e-10 | measured；原门槛1e-10，旧总体NOT_FULL_PASS |
| 异常p4 RHS/绝对残差 | 0.800839353350057 / 2.3120761610371854e-10 | measured；不是近零RHS归一化异常 |
| 全过程整树RSS/PSS峰 | 7387607040 / 7355427840 B | measured；RSS峰位于迭代，swap0、清场完成 |
| p4 MUMPS allocated/used | 4687 / 4326 decimal MB | native读数；不代替RSS；ICNTL23=4687 MB |
| p4凝聚矩阵 | 84680行，32320342 NNZ | measured；原CSR/mapping/values见第2节 |
| p6局部数值缓存 | 450893192 B | 数组载荷，不是RSS |
| JIT | 11 hit / 0 miss | measured；新运行需分开说明冷/暖与新增内核编译 |

旧B的R/T/A/A_volume为0.3650975537006217/0.013016803347759965/0.6218856429516183/0.6218856421339087；80通道及物理一致性检查通过，但这些不消除旧p4负项。它可作运行成本和同离散回归对照，不升级为高精度authority。

早期同一双层凝聚数学方案的h10计时揭示：BAL_H合计978.18 s，其中结构A6约324.19 s、H6约261.02 s、粗修正过程379.01 s；后者包含p4缩减/回代/恢复47.00 s及另约97.62 s的A4检查。剩余约234.39 s还含传递及包装，不能全归因某一个函数。这些是V19旧h10热点线索，不是本次h7.5实测分项，不将嵌套区间相加。

本批因此优先优化传递与物理/辅助作用，而不是再压缩已相对便宜的p4回代或删除检查。h7.5在P2/P4补齐同一组低开销分项即可，不另造通用profiling平台。

## 2. 冻结物理、矩阵与数学作用

正式输入从`input/task39extra/v23_b_physical_memory_original_h7p5.dat`复制语义到新dat，保留原resolved物理与网格计划；改变的是显式性能/精化profile，新input/source SHA重新计算。

| 内容 | 本批不变的合同 |
|---|---|
| 物理 | 13.5 nm、1度掠入射、azimuth0、s偏振、幅值1；原Si/air复材料、mu与周期/开放边界 |
| 几何 | 50×25 nm周期，z=-10…130 nm；原始grating与990单元共同对齐计划不变；不挖缺口 |
| 离散 | 同网格p6/p4、Nédélec H(curl)、complex128、原积分规则与双Floquet |
| 边界 | 全部80个原DtN通道、key/order/相位/归一化不变；不降积分、不只保留部分衍射级 |
| p6 | retained-space matrix-free Schur＋完整恢复；无全局A6/S6稀疏或稠密矩阵、无p6全局LU |
| p4 | 装配时单元凝聚、一份准确全局trace/port LU，跨全部调用复用；不改排序/主元/BLR/后端 |
| 外层 | right FGMRES32，max2048，零retained初值，一次KSP创建/求解/销毁；126步不是上限 |
| H6 | 同正定算子、Chebyshev次数、power10与seed规则；不通过减少平滑或放宽谱窗提速 |
| 生命周期 | 编译前置、共享identity、MATRIX_RETAINED_BACKEND_DEPENDENCY、完整场与最终A6核验后释放，沿V20 |

旧B实际p6 storage=667152、独立trace=199260、端口80、外层199340、内部445500、slave22392。以实际对象复核这些锚点，不用h10常数替代。

p4基线内容身份：

```text
CSR     857bc8bb5f04b28a55283fb960a2b695e1078983e55ff151687780de5dab8ee0
mapping bed2794532a40630632e06637cfda5a7bb52a06a7209824d5344085b6fa2cb1d
values  cf081185f6950ebb2c704e0426e02bb0687ef7ae47faf34115d729c8eb832b34
A6 RHS  b85dde2599428906be4ffd2f2200438f3011e57358d20a541679b3ab50687824
```

本批不优化p4装配/排序，默认要求上述p4内容相同；若发现输入或未授权数值变化导致不同，先停止受影响路径。线程仅用于第5节选定局部内核，MUMPS及p4分解保持原单线程配置。新缓存布局可改变字节hash，但必须有数组布局变更说明、数学等价检查，并保持单场factor前后/使用后CSR身份一致。

以完整空间简写，纠错组织仍为：

```math
C=P_{64}A_4^{-1}P_{64}^{H},\qquad
\mathcal B_H=C+(I-CA_6)H_6(I-A_6C).
```

retained外层继续使用原增广逆桥`J M_aug J^H`。不截取P64并假设两层Schur满足直接Galerkin关系。所有内部非零RHS、Bi/Di、原Hp与修正Hhat、MPC dual/primal、方向变换和strict slave-zero均保留。第3节只提高A4逆作用的浮点实现质量，不换粗空间；条件精化会使有限精度PC略有变化，不能要求新场逐字节或步数与旧B一致。

## 3. P1：先把p4返回质量做可靠，不扩大成长期诊断

### 3.1 核清现象，区分原因与补救

旧PC2第一次超限是真实记录，尚无唯一根因。不得先写成“舍入而已”，不得把它解释为2 nm等待的原因，也不得因它否定已测原A6收敛。

先读取对应g、c、端口状态、原A4作用/残差包和factor/矩阵身份。若旧raw没有保存该组向量，明确写missing；允许一次同B、同旧数学/seed的最短前缀，达到setup PC与PC2目标调用即保存退出，不能重新跑完126步。这个前缀属于已授权诊断，有自己的dat/source/资源和成本，不占用或改写旧run，也不假装零成本。没有保留下来的LU不能声称可直接复用；需重建时只建一份、随后处理所有必要RHS。

只检查异常RHS及最多两个已有正常对照，记录：原native A4残差、显式凝聚系统残差、内部恢复残差、增广端口残差和它们的代数关系；保持相同坐标、符号、范数与原g。记录curl/质量/端口各作用范数，帮助区分解算误差与大数抵消。无需求完整条件数、谱分解、全新p6参考或成百上千随机样本。

若是映射/符号/重复约束/评价实现错误，先最小修复共同核心并做定向测试；不能用多次回代掩盖不同算子。若native与凝聚作用一致而裸回代有限精度不足，执行下述显式修正。若唯一根因仍不能分离，但一致性检查与有界修正可实测保证原输入返回质量，则允许按`CAUSE_UNRESOLVED_BOUNDED_REPAIR_QUALIFIED`推进；如实保留未知，不把完整性能任务无限阻塞于根因叙事。

### 3.2 明确授权同因子残差修正，最多额外两次

定义F4为现有“一次局部缩减＋一次准确全局MatSolve＋完整内部恢复”。每个逻辑输入先执行F4；仅在原native残差超过1e-10时修正：

```math
c^{(0)}=F_4(g),\qquad e^{(j)}=g-A_4c^{(j)},\qquad
\rho_j=\frac{\lVert e^{(j)}\rVert_2}{\max(\lVert g\rVert_2,\mathrm{tiny})}.
```

```math
\rho_j>10^{-10}\ \Longrightarrow\quad
\delta c^{(j)}=F_4(e^{(j)}),\qquad
c^{(j+1)}=c^{(j)}+\delta c^{(j)},\qquad j=0,1.
```

非零逻辑RHS总计最多3次全局MatSolve；零RHS直接零的原分支不变。分母始终是最初g，不改为当前小残差范数。每次修正后用原native A4对总c重新检查；达到要求立即返回，2次额外修正后仍不合格就保存并停止，不继续迭代或调整门槛。非有限、约束或身份错误立即停止，不进入修正。

后端`ICNTL(10)=0`保持，禁止隐藏MUMPS refinement或新增inner KSP。复用一份原factor，不重新numeric，不另造全局矩阵。复用现有`physical_reference_diagnostics.py`的残差身份和有界策略思想，但适配到凝聚接口，不能照搬其未凝聚matrix维数或历史逻辑RHS总数上限。

**端口状态必须对应总修正。** `P4CellCondensedInverse`的`last_port_solution`会被下一次裸apply覆盖；累计修正时须合并原端口状态与增量，或按原端口消元关系从总场一致重建，并核对闭合。不得只累加FE向量却留下最后一次delta的端口幅值。内部非零RHS和恢复同样完整处理。每个逻辑调用记录裸rho、各次rho、最终rho、额外回代数、实际MatSolve数和耗时；旧负输入及前后向量强制保存，正常项可仅保存既有轻量证据。

P1定向测试覆盖：不触发路径、一次修正、达到两次上限仍失败、零/非有限RHS、非零内部与端口耦合、重复调用/输入不变/slave-zero、端口总状态、factor只创建一次及清理。所有返回成功的逻辑p4必须实际满足原1e-10；没有“外层最终会收敛所以忽略本次”的分支。只在wrapper成功后更新worker成功计数，checker从raw重算，不能再出现未解释的worker总体PASS而在线A4失败。

## 4. P2：先优化单核的重复工作，再考虑增加核心

先用现有计时器或少量PETSc events分开累计P/PH、A6 volume/DtN、H6、p4缩减/回代/恢复、A4核验、正交化、checkpoint与setup。不要逐单元打印日志或全量trace。旧h10分项只用于排序；P2以同一组实际维数/材料/约束的输入比较修复版单核与各优化，不以更少工作或不同精化次数计算速度。

### 4.1 首选：p6与p4之间的传递

优先检查`fullspace_same_mesh_hcurl_pmg_runtime.py`的`_candidate_packet`、`apply_primal_into`与`apply_adjoint_into`：逐单元`matrix.conj().T`、列表/concatenate、共享目标检查与scatter是否反复分配。

允许按真实局部映射身份缓存只读P/PH；实矩阵可用转置视图，复矩阵每类至多一份必要共轭缓存。矩阵提供者可能按cell不同，不能仅按方向码误合并。按相同映射分组、小批量矩阵乘法，预分配有界gather/scatter工作区，复用固定MPI1 owner计划；避免新增全局稠密/稀疏传递矩阵。不得将共享FE行重复相加或删除owner一致性检查。

保持原primal canonical-owner和dual带authority权重的加法语义、Floquet C/C^H各自次数及方向变换。比较新旧P/PH输出，并验证伴随身份：

```math
\langle Pu,v\rangle=\langle u,P^H v\rangle.
```

沿用旧row-consistency门槛；合法单位尺度向量的操作相对差/伴随差不大于1e-10，已有更严测试不放宽。批量临时空间有总上限，不能由全部单元数乘线程数增长。缓存PH新增字节必须进入去重库存，不能因只读就不计内存。

### 4.2 第二优先：BAL_H内部A6与H6的等价快速作用

外层Schur已经较快，不以它的微优化替代主要工作。先检查`fullspace_partial_assembly.py`、`fullspace_mpc_action.py`及实际BAL_H接线；新内核必须接到被调用的A6/H6，而不是只新增未启用的benchmark函数。

优先做同类型批处理、连续布局、小工作区复用、减少逐cell Python调度/临时数组/重复方向变换。保留所有积分点、复数材料、covariant Piola、curl变换、局部到全局约束和原DtN。可以融合有代数等价依据的遍历，但不同积分规则不能被错误混为一套。

若上述修改后profile仍明确由参考表收缩主导，允许对**一条**主导作用实现有界的张量积sum-factorization，作为同一算子的后端，不引入新的PC或替换有限元软件。它是将三维基函数求值分成一维收缩，不是把三维材料/物理降为准2D。需实际确认当前Basix变体的tensor-product排列及Nédélec各分量阶次；不能猜测可分解关系。未能在现有ABI下闭合时保留已完成的批处理优化，标明未实施，不拖住P4。

本批不同时增加“每类完整882阶稠密A6缓存”另一条路线，不构造全局A6/S6、不复制每单元大张量、不升级ABI、不启用complex64/fast-math或GPU。任一可选后端不等价或变慢就撤出新profile，继续其他已合格优化；不得删除旧实现。

旧native A6/A4仍作为独立核验路径。不能同时把运行算子和唯一核验算子换成同一个新核，然后用它们相等自证正确。必要同数据oracle只在组件资格中顺序运行，不在正式每步同时保留两套大对象。

### 4.3 第三优先：H6 setup及局部对角

`physical_light_setup.py`当前先用原FFCx作用完成power10，再安装packed作用；`fullspace_quadrature_diagonal.py`对每个cell/target重复积分。允许提前使用已资格化的快速正定作用、复用按真实局部类型计算的对角贡献，减少重复几何/基函数工作。

保持正定算子、同一seed recipe、power10次数、谱窗安全系数和Chebyshev次数；在组件资格比较旧/新对角、power history与最终谱窗，操作尺度差不超过1e-10且旧更严检查不放宽。不要求改变求和顺序后字节相同；差异超出已资格数值范围就回退原setup，不扫参数。不得把h10对角/谱窗搬到h7.5。

受约束对角必须来自`diag(C_K^H B_K C_K)`，共享master的交叉项不能丢失。内域可走已经证明无交叉项的快速分支，周期边界/多master走正确一般路径。相同材料分布的局部共享不依赖整个结构可分；保留非均匀材料、定向和非仿射拒绝测试。

### 4.4 不靠少检查来提速

每个逻辑p4返回前仍做原native A4检查；原A6每8步、场每32步与最终评价频率不变。可以复用同一状态上刚计算的等价量、降低无意义重复分配，不能只返回cached residual或用Schur residual代替原A6。计数说明省掉的是重复运算而非检测覆盖。旧B未分别记录的时间写unknown，不由总时间硬拆。

## 5. P3：多核只能在不增加内存的条件下采用

用户的条件是**不以更多内存换速度**。本批保持MPI1，仅允许共享内存局部内核/已加载数值库的线程；不允许MPI2/4、多进程池、每核复制p4因子/网格/向量/缓存。共享一个factor、一组只读缓存；PETSc/MUMPS API和同一factor回代不从多个线程并发调用，MUMPS线程仍为1。

先测实际物理核、WSL/cgroup限制、已加载BLAS/OpenMP及可用线程控制接口。限定1、2、最多4线程；先2线程，有稳定收益且内存条件通过才试4线程，不扫描所有核数，不更换BLAS/PETSc/MUMPS。环境不支持则单线程继续，不把安装新栈作为任务前置。

共享数据只读；并发写全局FE向量须用确定性分块归并、合法着色或等价安全方案。不得多个线程同时`np.add.at`同一输出并假定线程安全。所有线程合计scratch预算保持有界，不做每线程一份全局长度reduction buffer；计入线程栈、BLAS私有buffer、gather/scatter、JIT、factor外对象。禁止嵌套OpenMP×BLAS超额线程及反复创建线程池。

选用多核须同时满足：

1. 同source、同输入、同工作量、同修正次数的修复版单核对照中，候选操作/组合PC的中位时间稳定下降；至多三次定时重复，首调用/预热另记，报告离散性，不选一次偶然最快值。
2. 去重常驻载荷＋全部线程合计临时空间不高于修复版单核工作集；同scope实测RSS/PSS不增加。测量噪声无法分辨是否增加，视为**未证明内存中性**，选择单核，不任意允许5%/10%增长。
3. 组件选择只是准入，正式整场最后还要满足`RSS_peak <= 7387607040 B`，并分列迭代峰和PSS；不靠减少检查、统计外预热或漏计线程证明。该数值是采用多核的收益合同，不是取代现场物理内存的强制终止线。

线程方案与各阶段线程上限在正式P4前冻结并写入resolved配置；无合格多核则自动选已合格单核，无需再问用户。正式中不根据收敛或RSS暗换线程/内核。若最终发现内存回退，即使更快也不能宣布多核配置可采用；如实收口，不自动补第二场单核完整PDE。

## 6. 组件试验与正式运行顺序

| 阶段 | 工作及规模 | 完成条件/失败分流 |
|---|---|---|
| P0 | 当前branch/HEAD、规则、旧B与异常证据、WSL ABI和资源；建立新profile/输入/轻量计时 | 身份可靠；不重做已合格ABI/安装平台 |
| P1 | 异常输入最小复现、必要一致性修复、有界精化；必要时仅一个到PC2的前缀 | 旧缺口不改判，新的返回合同有实际证据；未闭合不启动正式长场 |
| P2 | 按4.1→4.2→4.3实施单核热点优化，组件同输入比较 | 保留正确且有效的实现；一个可选优化失败不拖住整个流程 |
| P3 | 条件比较共享内存2/4线程 | 无内存中性正证据则选单核；不运行多套完整PDE |
| P4 | 冻结clean source后，一场同B original p6/h7.5完整求解 | 原A6、所有p4逻辑调用、物理、资源和证据共同裁决 |
| P5 | 增量整理完整加速与成本因果、未实施项及限制，提交response_v25 | 推送同分支后统一等待审阅，不合并master |

组件试验优先使用旧已保存合法向量与局部class数据，包含真实复数材料、周期行、不同方向和非零内部RHS。数据不足时用固定seed生成合法向量并记录；实际990网格上的整套服务检查应复用必要构建，不为每个函数各重建全局factor。不可避免的重建照实计费，不承诺销毁后的factor能够跨进程复用。

P2最多一个“当前路径＋修复”的单核比较组、一个整合单核候选，再条件一个线程候选组。局部参数由工作区公式确定，不做无限batch-size/compiler-flag扫描。对每个主要模块报告调用数、首次/重复中位时间、峰值和操作差异，区分inclusive/exclusive；组合PC测量应包含gather/scatter、检查和精化，不只计BLAS核。

可在P2保留原H6 seed/window，用来隔离新apply速度；正式P4按新配置的已资格规则重新setup，不持久携带旧向量/初值/跨case Krylov空间。整合后至少核验一个完整PC输入的输出与修复版旧PC相容，避免各组件单独通过而组合接线错误。

**P4正常只运行一场。** 不另跑“只修复版”的93分钟基线，不为1/2/4线程各跑全场，不重跑O10/A/C。组件即使没有达到预想加速倍数，只要修复与安全合格，仍执行一次最终h7.5交付真实结果；没有“必须先快2倍才能进入”的新门槛。

正式输入建议`input/task39extra/v24_laptop_speed_original_h7p5.dat`。沿`python scripts/run_case.py input/path/to/case.dat`和已有独立用户服务/父watchdog执行。新run root/ledger/source，zero retained start；同根setup核验通过后直接进入同一KSP，不阶段性等审、不重复factor。组件探针不进入正式90分钟比较分子，另列总工程成本；若探针放在正式root内，其时间必须同时报告，不能从真实wall里消失。

## 7. 精度、内存、时间与停止要求

### 7.1 数值与物理

| 检查 | 要求 |
|---|---|
| 原A6完整残差 | 独立计算norm(b-A6x)/norm(b)<=1e-6，保存完整场后及释放后都通过 |
| 原A4每个逻辑返回 | rho<=1e-10，原g分母，裸值与全部精化值保存；最多2次额外回代 |
| 作用、传递与恢复 | 新旧操作尺度等价<=1e-10；保留原更严row/constraint检查；端口闭合<=1e-8 |
| 外层计数 | 每次PC一次BAL_H、一次H6、两次逻辑p4；实际MatSolve=非零逻辑输入数+额外精化数，不把精化当多次PC |
| 方程与缓存身份 | 同B physical/mesh/mode与p4矩阵内容；单场前后不可变缓存一致、严格slave-zero |
| 物理一致性 | abs(R+T+A_volume-1)<=1e-5、abs(A-A_volume)<=1e-5，80通道求和/归一化/被动性完整 |
| 完整输出 | 复数E/H、curl、近场/界面切向量、R/T/A/A_volume和全部模式幅值/功率；finite不冒充场准确性 |

旧B保存场可作同离散回归目标：L2/scaled-curl、同坐标E/H和复模式相对差<=1e-4，R/T/A/A_volume绝对差<=1e-5，逐模式功率最大绝对差<=1e-6，沿既有近零绝对例外，不拟合相位。这是regression，不是新matched-reference authority。无独立h7.5参考仍标`AUTHORITY_LIMITED`；旧B总checker失败也继续保留。回归异常先记录，不用合适相位/重新归一化消除差异。

不以126步、112步或旧64/128步经验残差线终止新场；max2048、nonfinite/breakdown、原物理/身份与用户停止仍有效。精化引起步数变化照实报告，不把它全部称为内核提速。

### 7.2 安全与内存口径

沿最新用户物理内存策略，在现场确认Linux effective RAM、cgroup及Windows/WSL宿主机余量，保持zero-swap、独立监督、可写证据与进程清场。至少保留现行128 MiB监督/写盘余量，并尊重实际系统压力；它不是允许吃满物理内存的承诺。不恢复旧6 GiB库存、8 GiB整树或3.857 GB续算阈值来再次否决已经实测可行的B，不以固定2倍预测作唯一拒绝理由。

本批没有提高物理安全额度或MUMPS已验证4687 MB额度的授权；新临时/线程对象必须纳入账本。真实内存压力、swap、不可恢复的I/O/监督故障时受控停止完整进程树，OS OOM不是正常终态。预测用于选批量/线程，不冒充已分配RSS。

全部正式阶段RSS包括JIT/编译后代、线程和共享库真实驻留；PSS、native allocated/used、缓存数组与RSS分列。保留当前后端矩阵借用的安全策略，不为加速detach、关闭allocator安全或做heap trim。

### 7.3 加速判据与公平对比

主要分母固定为旧B完整monotonic 5581.178597819002 s；另列KSP 4737.310983555995 s、126步和7.387607040 GB全峰。新完整wall包含输入、setup、numeric、求解、全部检查/输出/释放/清场；保守ledger时间和monotonic不可互换。

```math
S_{\mathrm{full}}=\frac{5581.178597819002}{T_{\mathrm{new,full}}},\qquad
\Delta t_{\mathrm{min}}=\frac{5581.178597819002-T_{\mathrm{new,full}}}{60}.
```

报告完整时间、KSP时间、步数、每步分摊成本、固定工作量组件速度、精化次数和各阶段峰值。新旧检查频率相同。旧B是warm JIT；复用合格cache，不清缓存制造冷启动。新增内核的首次编译在工程或正式阶段发生在哪里就记在哪里，单列冷/暖；正式发生的miss一律纳入全wall/peak。不把统计外预热称为冷启动加速，不要求为可比性额外全场重跑。

同一次最终场与旧B的比值是工程比较，含精度修复与可能的线程变化；不能声称所有差额纯由某一个内核贡献。线程没有采用时仍交付单核优化结果。无提速、轻微提速、内存回退或数值失败都可正常研究收口，不自动再开算法路线。

正式失败只有真实实现bug才沿既有hash-bound机制允许至多一次必要重放；慢、残差正常未达到、内存收益不足或计时不漂亮不属于重放许可。无法完成的项保存具体阶段/值/限制，不用空泛FAIL。

## 8. 实现组织、提交与证据

核心放`src/solvers/`，配置/阶段和薄调度复用现有io/runners；不得复制整份上千行runner。优先审查：

```text
src/solvers/p4_cell_condensed_inverse.py
src/solvers/physical_reference_diagnostics.py
src/solvers/fullspace_same_mesh_hcurl_pmg_runtime.py
src/solvers/fullspace_partial_assembly.py
src/solvers/fullspace_quadrature_diagonal.py
src/solvers/physical_light_setup.py
src/solvers/fullspace_mpc_action.py
src/solvers/physical_retained_outer_adapter.py
src/runners/physical_p4_cell_condensed_v18.py
```

旧profile/checker数值行为保持，通用修复须有旧回归；新增checker复用已合格读取/norm/物理逻辑，只扩展新profile、逻辑/物理调用计数和线程/性能证据，不重新实现求解器。正式前完成最小FE、复非Hermitian、非零内部/端口RHS、MPC和方向、输入不变、重复/释放以及线程竞争相关定向测试；然后一次task-focused、compileall/diff/文档检查。有依赖缺项按事实报告，不借此升级整套ABI；不宣称未运行的CI/全仓测试。

建议普通提交顺序：P1修复与测试；P2等价性能内核与测试；P3可选线程和冻结profile；clean正式source；P5证据与文档。不开新分支，不amend/强推，不在运行中改源码，不触碰master或工作站。若远端出现并行新增提交，非破坏性核对并保留，不能reset覆盖。

至少交付以下轻量文件，已有总览只增量更新：

```text
docs/task039_extra_physical_multilevel/response_v25.md
outcomes/laptop_speed_v24.md
outcomes/records/laptop_speed_v24_a4_repair.json
outcomes/records/laptop_speed_v24_components.json
outcomes/records/laptop_speed_v24_thread_selection.json
outcomes/records/laptop_speed_v24_compact.json
outcomes/records/laptop_speed_v24_checker.json
outcomes/records/laptop_speed_v24_decision.json
outcomes/records/run_index.json
outcomes/summary.md / outcomes/test_summary.md
```

同步`docs/development_progress.md`、`docs/development_model_registry.md`及selective merge清单。大型g/c/残差包、全场、矩阵、factor、资源timeline和编译cache在ignored，compact绑定路径/hash。每次正式运行保存input_original/resolved_config/run_manifest/input/physical/source SHA、环境/ABI、MPI/线程与实际绑核、调用计数、完整采样及终态。旧账本不清零，新组件/前缀/工程时间与唯一正式场分别记录；未知不写0。

Response第一屏要回答：旧p4缺口是否复现、根因证明到什么程度及怎样修复；哪个热点真正变快；是否采用2/4线程及内存依据；新h7.5用了多少分钟、相对93.02分钟的倍数/节省；步数、额外回代、全峰RSS和完整物理是否合格。

建议分别报告`A4_RETURN_QUALITY`、`DISCRETE_SOLVE`、`PHYSICS_CONSISTENCY`、`AUTHORITY_LIMITED`、`SPEEDUP`、`MEMORY_NONINCREASE`和`MULTICORE_ADOPTION`，不能压成一个不解释原因的PASS。任一旧证据不能升级为通过；任何新多核内存增长不得称为符合本轮条件。结束后推送同一分支、报告精确HEAD与clean状态，统一等待ChatGPT审阅，不合并master。

## 9. 来源与本报告自身边界

仓库权威为本轮用户指令、[task](task.md)、[最新已完成review](review_report_v21.md)、两份已保存用户授权及第1节证据；执行前继续读取根/目录AGENTS和仓库工作原则。上文代码热点来自已读源文件与旧分项记录，不代表已经测得本批速度。

外部资料仅支持设计含义，不替代当前PETSc3.19.6/NumPy/BLAS实际能力：

- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)说明flexible右预条件可接受变化的PC；这不自动保证任何修正有效。
- [PETSc profiling](https://petsc.org/release/manual/profiling/)说明轻量事件与嵌套计时；本批只用当前版本可用接口。
- [NumPy thread safety](https://numpy.org/doc/stable/reference/thread_safety.html)说明共享可写数组的竞争风险；不据此要求升级到文档展示的新版本。

本次ChatGPT仅新增review并检查文档/局部代数，不运行项目PDE、ABI或线程性能试验。正式交付检查fenced math、表格、链接、本地预览和远程回读；GitHub网页无法访问时如实记录限制，不能声称已目视通过。新方法即使更快，也仍只属于当前13.5 nm同离散范围，后续工作站/短波迁移另行资格化。
