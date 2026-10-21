# Task41extra Review V8：最大误差行的完整局部证据与消元缺陷审计

## 0. 决定、范围与固定身份

**接受V7已由真实复数向量确认并修正Bα漏项；维持原full-action与V6候选初次恢复FAIL。下一唯一工作包是 `selected_trace_star_audit`：先利用保存数组和局部块，再仅补active行4,766,937的全部关联单元（含MPC映射贡献）的元数据及确实缺失的局部数值，分开消元缺陷、算子差异和归因求值误差。禁止无依据重建28,000键或重复完整模式遍历。**

“行的完整局部星区”指对该独立trace行有非零贡献的所有单元；不是任取两个相邻单元。它用于把一次全域失败缩到可以逐项复算的局部计算链，不是新的小型PDE或新PC。本轮出口是有证据的最小生产修复建议及可重放局部包，不是完整作用PASS。

| 项目 | 冻结值 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 审阅结果base | `368124f5d17e99d6086424bf2b8cda73ebae95ef` |
| V7 consumer source | `184822fa7ec5cd2af33a6ff39b5c6e7e5641cab6` |
| V6候选producer | `210fbbf271faa14c62ac30153b80332d0e645982` |
| 原donor source | `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` |
| 日期 / 职责 | 2026-10-21，Asia/Singapore；ChatGPT仅写review，Codex实现、定向测试、获准提取与审核 |
| 物理与最终目标 | 原0.7 nm、50×50×140 nm计算域、17×20×120 nm居中Si、φ90°、p6；完整三维场、十进制2 TB含余量、任务swap0、必要冷流程≤48 h |

本次读取response_v7、compact、summary、run index、test summary及实际源码。根AGENTS、既有docs规则与task.md继续适用；task.md blob仍为`5b669c109006fa91fdeebba2a81d97ba17b640b0`。Review V7本地全文与远端blob `723854cea78af8b2edbb5360516e0cc708152bd5`匹配；本轮增量未修改这些治理文件或增加独立补充任务书。历史V6两份文档和用户指定执行权威保持原记录，不在本轮重新争议局部门。只提交本分支，不动master或其他任务。[R1][R2][R3][R4][R5]

本审阅未登录工作站、未读取其大型NPY、未运行项目测试或FE。唯一新增计算为当前Chat容器的微型复数分块恒等式核验，非项目资格。源码事实、代数推导、需工作站验证的假设分别标明。

## 1. V7的接受范围

| 项目 | 实测结论及边界 |
|---|---|
| 旧约198归因闭合 | 漏减Bα已获全复数向量证据；旧闭合减Bα与修正式差约1.13e-14 L2。不是原action的修复 |
| 四组正确闭合 / 原D | col0 j0/j3为1.848852249621133e-11 / 9.744506610665259e-12；col1为3.8826091267246497e-11 / 2.0487825368991332e-11 |
| 闭合占原差 | 5.66%–10.76%；体积式几乎相同，仍不足以可靠确定主导根因 |
| reducer交叉检查 | 保存reduce_r_volume与原生trace残差加T_r_i约1e-22–1e-24一致；只证明此已存小残差输入下两条路径一致，不证明原大RHS的缩减无相消误差 |
| 两状态d_hat差 | col0/1为3.992795315768375e-8 / 8.380520829133848e-8 |
| 原完整action | 1.7183209126709868e-10 / 3.6180522433957604e-10，原门1e-11，FAIL |
| V6候选恢复 | 初次forward约1.98e-11仍FAIL；native残差约1.44e-15通过；额外修正0次，旧donor j3不转授 |
| 成本/资源 | service父250.110605 s包含约200.484060 s审核子段；tree RSS9,049,808,896 B、cgroup1,801,805,824 B分列；task swap0、host计数增量0、后代清场 |
| 新证据 | 8份闭合数组728,065,024 B；累计证据14,622,146,704 B，原16 GiB配额当时余2,557,722,480 B；启动时重读实际值 |
| 尚未取得 | 200q、全参考、FGMRES、原尺寸场、A6/物理、最终精度及完整2TB/48h资格 |

三种误差不要混淆：原action FAIL、候选初次恢复FAIL、诊断恒等式的闭合余差。修正诊断只改变第三类。V7的10项测试与saved-audit完成不转成前两类PASS。INVALID_LAYOUT_ATTEMPT保持无效，未记录费用保持UNKNOWN。[R1][R2]

## 2. 先把消元缺陷定义正确：S的构造检查不等于凝聚恒等式

沿现有块划分，K为内部-内部，G为内部-trace，J为trace-内部，L为trace-trace；R≈−K⁻¹G，T≈−JK⁻¹，S由L+JR计算。原生产代码使用真实`interior_positions`和其补集提取块，不能把882行连续切成450/432两段。[C1]

对**同一生成机制、同一方向及同一局部排序**的已存矩阵，定义：

```math
E_R=KR+G,\qquad E_T=J+TK,\qquad C_S=S-L-JR,\qquad E_S=S-L-TG.
```

它们满足以下纯代数关系；这里“精确”指对已经存下的数值作精确算术，不要求实际浮点计算逐位一致：

```math
E_S=C_S+E_TR-TE_R,\qquad
E_St-E_Tu=C_St+E_T(Rt-u)-T(E_Rt).
```

因此：

- `S-(L+JR)==0`只检查构造表达式的重复求值；即使C_S确为零，也不能推出E_S为零，因为E_R/E_T还在。
- 还有更细一层：S已经是一次舍入后的和，重复相同complex128表达式可能得0，却遮蔽存储矩阵之间的真实小差。简单例子：float64中L=10^16、JR=1、S=fl(L+JR)=10^16，重复`S-(L+JR)`为0，而存储值的精确差S−L−JR为−1。不能用这种0排除相消/累加误差。
- 同一trace下j0与j3的E_S t相同；两状态d_hat不一致，**不能单独归因于E_S**。E_S可能贡献原action差，但状态差还必须检查局部乘加、全局累加、状态绑定及native配对。

当前容器的小型非Hermitian复数例子有意扰动R/T：相同表达式重算差为0而E_S范数约7.48e-8；以70位诊断算术核验上述关系及两个状态的d_hat一致。这个例子只验证公式，不说明工作站本例根因。

## 3. 已确认的源码约束：如何避免再误启完整owner

1. `Task41V5VolumeAttributionAccumulator.observe`分别计算Ku、Gt、Ju、Lt，再组成Tδ_i、E_S t、−E_Tu；delta_t从负native trace开始逐cell加贡献。它包含多次大项相减，必须测量误差，不能先称“只是舍入”。actual构建按八键前缀优先顺序观察，恢复map随后还原原cell顺序；P6与归因的累加顺序并非自动相同。[C2][C3]
2. `iter_selected_volume_audit_cells`依赖完整`AssemblyTimeCondensedSystem`以及全部T/R/S/LU缓存，**不能为了找一行调用完整owner builder**。现成`_cell_trace_expansion`等元数据逻辑可以复用，但选行与数值cache读取须做窄分离。[C4]
3. 现有`build_task41_v4_volume_only_owner`先建完整owner再选旧行，仍不是本轮入口。复用它前面的同mesh p6/MPC准备和原行核验，选定cells后只对必要cell生成张量。[C2]
4. 部分`volume_class_*`保存的是独立FFCx K/G/J/L与候选owner T/R/S；不能因同为actual几何，就把这组混合数据当作生产候选的同算子缺陷。优先使用V6明确命名的`candidate_oriented_tensor`与`candidate_R/T/S`，reference组独立比较。旧candidate/reference哈希清单足以先审计这项绑定。[C2][R6]

本轮不改blocked-Gram算法、积分、材料、几何key、MUMPS或PC，不增加第4次恢复修正。

## 4. 唯一执行包：先保存数据代数，再补目标行完整局部星区

### P0：冻结输入、排除最后一层求和与角色混配

复用原141数组、V6的174数组、V7的8个闭合数组及各自hash/index；完整carrier仅引用其既有身份，连两个B帧也优先使用已经保存的稀疏Bα包。每个实际使用文件在同一只读会话核验一次，不反复扫描全部目录。

先建小型role表：producer、column、state、basis/方向、raw/oriented、candidate/reference和hash。`j0/j3`仍是donor状态，不是V6候选精化次数。用保存行号核验trace相同、slave存储为零、RHS和native action严格配对。V7无效连续切片不复用；确无保存的局部分区时，从相同Basix element身份生成`entity_dofs[tdim][0]`及原有补集，并与已存cell行图交叉核对。

在保存全域向量上，只补一次有界、逐chunk的高精度/补偿**最后组合**比较：重算四组闭合及j0/j3差，区分最后几次加减/范数造成的误差与已经写进累加数组的误差。可用平台确实更宽的longdouble诊断或实/虚部分别补偿求和；记录真实mantissa，不声称`complex256`必为四倍精度。它不改变生产complex128，也不能恢复已经丢失的逐cell加数。已有V7普通复算不必重复写8个全长数组；优先只保存指标、最坏位置和所需小切片。

同时在已有同身份八键局部块中，真正计算E_R/E_T/C_S/E_S及其对原trace/内部状态的作用，而不是只抄V6的资格摘要。完整缺陷矩阵仅逐key暂存；保存局部作用向量及指标。没有可靠partition或匹配块，就明确该项缺失，进入下一阶段补元数据，不胡乱切块。

### P1：先找全incident cells，再分配任何新张量

固定首个目标为active trace行**r=4,766,937**。不把它当full-storage原行；先由保存`active_original_rows[r]`得到原行身份。一次元数据检查确定所有满足`E_c[:, local_index(r)]`非零的cell，包括通过周期slave贡献的cell；不是只检查该原行是否直接出现在`dofmap.cell_dofs`中。

优先检查实际已有maps/索引；V7已将完整目标行关联标为MISSING，本轮不能再默认其存在。确缺时明确允许**一次metadata-only补建**：同物理同MPI1网格、p6空间、finalized MPC、cell排列/方向、实际坐标、原行/active编号；可扫描28,000格的整数映射，但不生成全域局部张量、凝聚owner、surface或factor。核验保存active/slave图、FE/Basix及28,000-key清单的实际坐标/材料/方向身份，再保存目标行完整incident列表和每个cell的E CSR、真实I/T位置、original/active rows、coords/key/permutation。不能只凭cell号相同认定身份相同。

若编号变化且不能由现有可靠映射消除，则在数值补算前停止并报告具体差异。不得修改旧向量来适应新编号，也不通过重做全部原数据回避。

### P2：只补星区中实际缺失的数值，算完即保存

先按cell/key查V6保存的数值块；已存在的原样读取。缺失的cell按V6冻结的`actual_qmetric_blocked_gram`、实际坐标、原kernel/积分/方向，在该cell上生成一次完整candidate张量，沿原strict LU与R/T/S公式消元；每个必要cell最多再取一份同坐标的原FFCx reference张量作为独立对照。原slow FFCx只限实际缺失的星区cell，不能扩成全域或再次跑八键资格前缀。

复用现有低层evaluator与`_tabulate_volume_audit_path`的调用，不调用会默认同时做canonical的整套geometry-pair wrapper，也不调用有全28,000键前缀条件的owner。准备开销计费，原compiled/JIT可以在合法身份一致时复用。局部LU是本次新建，不能称V6已销毁LU仍存活。

新增块标`RECONSTRUCTED_SELECTED_CELL`，绑定本次source与V6算法身份；若V6完整报告有该cell raw/oriented张量digest则核对。没有旧LU/R/T/S的逐cellhash时，不声称新生成块就是旧内存逐字节拷贝；随后以保存的目标行S作用、reduced RHS和归因向量作为重放锚点。若无法重现，先查身份/求和路径，不据新块宣布旧全域根因。

全部incident cells必须覆盖，不能到任意数量上限就漏掉余下cell后叫完整。先用元数据计算实际新增文件、工作集和时间预算，满足原16 GiB总证据/2 GiB空闲及动态资源门才生成。一次只保留必要工作块，不复制donor全场；不得未经许可扩大到所有28,000份缓存。

### P3：对两列和严格配对状态，分开生产误差与诊断求值误差

令w_c为E_c中对应目标active行的列，t_c=E_c t。b是原native_volume_rhs，n_s是该state的保存native体积作用。先分别重建该行的生产S作用和缩减，再相减：

```math
s_r=\sum_{c\in\mathcal S_r} w_c^H S_ct_c,\qquad
 g_r=b_t[r]+\sum_{c\in\mathcal S_r}w_c^H T_cb_{i,c},\qquad d_r=s_r-g_r.
```

全局b_t只加/减一次。完整端口式沿V7正确Bα定义，原已做MPC的Bα只重编号、不再乘相位或E^H。分别对照保存`s_full/g_full/d_volume/full_p6/full_reduced_rhs`在该行的值，保留RHS拆分与不同累加次序产生的差。**不能只计算一个特殊联合残差而跳过生产S作用和RHS缩减各自的重放。**

对每个cell、每列、donor j0/j3（known及V6初始恢复仅在有匹配native数据时另列），保存δ_i、投影trace项、Tδ_i、E_S t_c、−E_Tu_i、T r_i，保留实部/虚部而不仅是范数。局部矩阵、native值、t/u状态、方向须严格配对。

现有Q的表达式还具有一个消去中间大项的诊断恒等式：

```math
\begin{aligned}
q_c&=T_c\delta_{i,c}+E_{S,c}t_c-E_{T,c}u_{i,c}\\
   &=(S_c-L_c)t_c-J_cu_{i,c}-T_cn_{i,c},\\
\widehat d_{s,r}&=\delta_{t,r}+\sum_c w_c^Hq_c-(b_t[r]-n_{s,t}[r])-\sum_cw_c^HT_c(b_{i,c}-n_{s,i,c}).
\end{aligned}
```

对同trace和同b，精确算术中d_hat不依赖j0/j3，且E_S t在状态差中抵消。分别用原V6逐项次序、上式重组及有界高精度/补偿诊断比较：Ku+Gt、Ju+Lt、E_S/E_T求值、局部项组合、E^H、跨cell累加以及最后相减各贡献多少误差。诊断精度不得被写入正式候选或拿来直接判生产通过；不默认高精度必然比原native更接近连续真解。

至少输出以下两条可区别的证据链：

- **生产差异链**：同身份张量/local native差、R/T解残差、S的形成误差、生产matvec/reduce的累加对真实d_r的带符号影响。
- **诊断不闭合链**：同一存储矩阵/向量，改变诊断求值组织后，C_r和两状态d_hat差是否缩小；这只解释归因误差，不能据此改写保存action FAIL。

分别将星区原次序重放与V6保存的δ_t、Q、U及V7闭合在该行对照；记录observer八键前缀顺序和生产原cell顺序。若最后一层求和或局部大项相减占主导，要量出实际向量差，而不是仅说“像舍入”。若只在少数cell证实一种机制，结论仍为LOCAL，不能称全域唯一根因。一个最大分量不是全域L2误差的全部来源。

## 5. 本轮完成条件与下一步边界

**本轮成功交付：**目标行全部incident cells及角色/布局身份闭合；同一份局部包可以重复重现该行的原生产输出和四组归因；能量化至少一项剩余误差来源，或明确排除几项并指出唯一尚缺的最小量。随后给出一个有局部反事实验证的最小生产修复建议：实际文件/函数、改变哪一段计算、不改变什么、需要重验哪些证据以及成本。不要以“继续研究几何一致性”收口。

若明确发现普通编号、状态、漏/重复累加或接口错误，可在同一包定向修复并用上述原输入重放。若证据仅支持某处有限精度问题，可在现成局部数组上验证一种由证据选出的稳定计算次序；不得同时扫描多个PC/积分/精度/缓存方案。无证据不预先指定换S公式、再次改actual几何或增精化次数。

**本轮不授权全域重建或200q。**局部结论或诊断闭合不是全域门。原两列1e-11、候选forward1e-11、native门及原分母继续FAIL/PASS原状态；候选额外恢复修正仍0次，donor j3不转授。未来只有受影响生产实现、完整两列和恢复及独立checker重新闭合，才能解锁后续求解。

停止条件：缺关键身份/全部incident不能验证、局部重放无法绑定旧结果、非有限、证据/内存/时间门，或局部反事实仍不能解释差异。保留此前完成的metadata/blocks/报告；普通字段、导入、序列化问题定向修复继续，不因其重新生成已保存局部块。不能用归因闭合向量从原action中“减掉误差”。

## 6. 资源、时间和开发约束

沿既有`fenics-ws:/home/fenics/Projects/laptop_share`，complex128/int32、MPI1/math1、exact MUMPS合同、1.5 TiB task cap、64 GiB host reserve、task reserve0和task swap0。一次一个heavy；不操作邻任务。PSS未采样保持null。选区局部LU不等于q/global factor，本轮后者禁止。

证据实际余额启动前重算；V7已用14,622,146,704 B，当时16 GiB配额余2,557,722,480 B，另外须满足真实磁盘2 GiB空闲底线。新包只保存目标行局部矩阵/向量和小metadata，不再复制全场或8份全域闭合。旧315数组和carrier不移动；mmap页计入资源。父service含checker，metadata、selected kernel/LU与代数子阶段分列、不重复加；未知工程费用不补猜。

原V6窗口T0为`2026-10-20T10:21:59.261754681Z`，数值截止`2026-10-21T10:01:59.261754681Z`，总截止`2026-10-21T10:21:59.261754681Z`；对应新加坡今天18:01:59与18:21:59。审阅开始查询为2026-10-21 11:22:58 Singapore，尚未到期；这是时钟快照，不是工作站可用余额。接收、冻结、启动及局部补算前读UTC/monotonic/账本更紧余额，不使用V7历史26,308秒快照，不刷新T0。

本review明确把V7严格saved-only边界窄扩展为“必要metadata＋目标行完整星区的缺失局部块”；原窗口有效、原资源门及预算通过时可连续完成，无须每个cell另等review。到原截止就停止新增数值工作并按原总截止收口。若过期，新窗须用户一次明确批准；备用提案总21,600秒、数值20,400秒、收口1,200秒，状态`PENDING_USER_APPROVAL`，仅覆盖本窄包，不自动恢复旧时钟或授权完整场。

复用现有saved审计/volume-only监督入口，加入明确的metadata/selected-cells scope与禁止全域构建断言；实际CLI由本轮prepare产生并验证，不虚构已存在的选项。不新建V8 runner/版本框架、不全仓重构。

定向回归只需覆盖：①非连续I/T分区与复MPC的完整star选择，不能漏slave贡献或重复b_t；②C_S/E_S区别、非Hermitian块、状态混配和同精度假零的代数；③真实入口从元数据到所选cell提取，断言不会调用全owner/carrier/200q。昂贵kernel可替身，但修改的选择/角色/保存链不能全mock。不跑全仓pytest或重新安装运行库。

建议两笔执行提交：实现/相关回归冻结；局部证据与response_v8收口。ChatGPT本次仅新增review。主控集中推送同一分支，更新现有summary、run_index、test_summary与项目总账；无master合并。response首先给目标行原行号、完整cells/key清单、带符号误差分项、原次序/补偿对照、局部修复建议与实际成本，再列测试。完整场、最终精度、2TB/48h均不提前声称通过。

## 7. 给Codex的连续执行文本

```text
继续Task41extra，读取review_report_v8.md。
结果base=368124f5d17e99d6086424bf2b8cda73ebae95ef，V7 source=184822fa7ec5cd2af33a6ff39b5c6e7e5641cab6。

V7的Balpha漏项已关闭，原action与V6初次恢复仍FAIL，不重做这轮已接受审核。
下一唯一包是selected_trace_star_audit：保存数组＋active行4766937全部incident cells。
禁止重建28,000键、扫描/生成carrier、全模式遍历、A1/A2、200q或全局factor。

先核candidate/reference、raw/oriented、真实I/T位置和donor j0/j3身份。
不得连续切882矩阵；不得把FFCx K/G/J/L与Gram T/S混配称生产同算子。
在已有数组上补一次有界补偿/更高精度的最后组合检查，并实际复算现存局部块：
E_R=KR+G，E_T=J+TK，C_S=S-L-JR，E_S=S-L-TG；
验证E_S=C_S+E_T R-T E_R。重复S-(L+JR)=0不证明E_S或存储值C_S为零。
同trace的E_S t在j0/j3差中抵消，不能用它单独解释状态差。

按保存active_original_rows找4766937的原行，再找全部E列非零的cell，
包括周期slave贡献。优先现存map；确缺时只建同mesh/p6/MPC/编号元数据，
复用底层行展开逻辑。iter_selected_volume_audit_cells依赖全owner，不能直接
先建完整owner再选行。禁止借metadata步骤启动全张量/端口准备。

选择完成且预算允许后，只补这些cell实际缺失的candidate/reference张量及
各自R/T/S/LU，每cell一次保存。使用冻结actual几何/evaluator与原kernel/方向；
旧已保存块复用，新增块标RECONSTRUCTED_SELECTED_CELL，旧source/hash不改。
没有旧hash就不能称旧内存逐位复刻；用原保存行输出核验重放身份。

对原两列、严格配对j0/j3，分别重放目标行S作用与RHS缩减，b_t全局只计一次；
保存Tdelta_i、E_S t、-E_T u、T r_i及E^H后复数分项。
对照原V6次序、等价重组Q=(S-L)t-Ju-Tn_i及有界精度诊断，
区分生产差、局部消元缺陷、诊断乘加/全局累加误差。
不把高精度诊断写成生产PASS，不从norm反推分项，不用保存差向量补答案。

本轮应交完整星区证据与一个经局部反事实检验的最小生产修复建议；
局部无法闭合就给唯一具体缺项/差异，不自动扩大到全域构建。
普通工程bug同包定向修复，不重算已完成数据。
原1e-11作用/forward、native门、精化次数和完整场准入不变。

沿原V6数值截止2026-10-21T10:01:59.261754681Z、总截止10:21:59.261754681Z，
接收/冻结/启动读真实余额。过期需新窗口一次授权，不刷新旧T0；
review中6小时仅为待批准窄包提案。既有主机/cap/reserve/ABI/线程/swap0不变。
累计16GiB证据与2GiB磁盘底线照常准入，不复制全域向量。

复用现有监督入口并输出真实命令，只做分区/MPC、缺陷恒等式、选择与保存调用链
相关测试，不全仓pytest、不新框架。主控集中提交response_v8及精确原件hash到
同一分支，不合并master，不声称完整0.7nm场或最终2TB/48h已通过。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/docs/task41extra_phi90_p50x50_g17x20/response_v7.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v7_saved_attribution_20261021.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v6_actual_qmetric_hash_index_20261021.json
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/src/solvers/hcurl_assembly_time_condensation.py#L2100-L2345
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/src/solvers/task41_v4_volume_only_audit.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/src/solvers/hcurl_assembly_time_condensation.py#L2700-L3675
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/368124f5d17e99d6086424bf2b8cda73ebae95ef/src/solvers/hcurl_assembly_time_condensation.py#L650-L1030
