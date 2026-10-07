# Review V57：固定接口阶数，直接验证单元内部富集能否提高精度并限制全局规模

## 0. 裁决与主线

**V58按有限范围接受，`pass_with_qualifications`：完整单次部署已实测，审核去重/精确体求积已消费，三个完整解与保存输出可信；跨p约3.4%的场分歧仍FAIL，0.7nm原尺寸、2TB/48h和NN收益均未资格。** 不再重复换载波、24弱试验、普通uniform hp/M扫描或训练NN预条件器。

授权V59直接做一种有明确数值定义的有限元空间：**边/面的全局接口仍用p6，单元内部用p7，随后在同接口上检验p8内部。** 内部函数增加后仍在单元内消去，全球求解保持33660行。它针对“低阶解遗漏高阶内部平衡”这条新证据，实际求完整物理场，不只做一个对偶范数诊断。它不是已经证明有效的方法：内部缺陷大不保证内部富集足够，必须同时检查新场、剩余高空间缺陷和成本。

```text
repository          = Rookie1234567/MyFEniCS
branch              = task42_neural_coarse_inverse
canonical_worktree  = /home/fenics/Projects/NN-Lab
review_date         = 2026-10-07 (Asia/Singapore)
reviewed_HEAD       = 8033ed11640defa61d422b5916e5ae2d22b45ff2
latest_commit_UTC   = 2026-10-07T11:02:22Z
latest_response     = response_v58.md
previous_review     = review_report_v56.md
previous_review_SHA = 721c2731da0ce02ef528345f7b6ffcea459b033c
original_base       = ccd357885f7f9be84efe3be07868cc94f13d93fc
new_batch           = V59_TRACE_FIXED_INTERIOR_ENRICHMENT
required_response   = response_v59.md
new_complete_solves = two_planned; at_most_three_including_scientific_repairs
NN_training_PC      = NOT_AUTHORIZED_THIS_BATCH
merge               = NOT_APPROVED
```

最终目标仍为原50×25nm周期、z=-10..130nm、真空0.7nm、周期单胞内任意非可分三维Maxwell；单次必要准备至完整输出/验收不超过172800s，约2TB整机物理内存且保留系统余量。当前只做缩尺完整Full3D authority；不因有2TB就扩大本批资源许可，不把有限直接法当最终生产架构。

本报告明确覆盖V56的固定统一阶数和“不追加p8”限制，**只授权局部内部p8，最终接口固定p6，不授权uniform p8求解或扫阶数**。旧窗口不恢复、旧FAIL不改判。根/目录规则、原则与原task保持；同blob历史继承，当前范围以本报告为准。审阅读取最新response/summary/原合同、部署收据、6次提交的文件差异、跨空间缺陷及凝聚/恢复代码，未发现本任务新增补充合同。没有SSH或读取工作站完整ignored数组，没有审阅端新PDE；下文measured来自远程记录。

## 1. 已证实收益与剩余问题

依据：[V58回应](response_v58.md)、[完整专题](outcomes/deployment_cost_paired_gauge_v58.md)、[单次部署收据](outcomes/records/deployment_receipts_v58.json)、[科学记录](outcomes/records/scientific_checks_v58.json)、[最终费用](outcomes/records/resource_costs_final_v58.json)。实际科学source为`c47799d1c2bb7109a071358f06500a905fc42c43`，最终checker为`b4898819b58fdfe8a282bc0321a5c12262cf342e`，文档HEAD不是运行source。

| recorded measured | 实际值 | 裁决 |
|---|---|---|
| C6完整必要单次 | 904.036401666s；采样树峰7.432594GiB；独立true1.14919e-11 | 取得可用的N=1计时，不再全部unknown；仅本case数值冷，OS/JIT状态已记录 |
| C6/B6同离散再现 | scattered E/H约2.04327e-12；完整场/模式/功率PASS | 保留15表、边界包重载、独立体精确求积和无JIT后处理 |
| G6/G7新载波跨p | scattered E/H0.03408936/0.03406028；复通道9.36127e-4 | 原门1e-4，仍FAIL；载波改写没有消除主要分歧 |
| R6/G6与R7/G7 | scattered E4.27502e-5/2.50277e-6，完整增量PASS | 这次载波敏感性小，不授所有gauge或连续准确性 |
| G7完整必要单次 | 1770.506532182s；采样树峰14.336380GiB | 新载波p7成本，不与原载波不同流程随意拼速度比 |
| 高空间缺陷 | norm(b7-A7*P*u6)/norm(b7)=0.04999435 | p6不满足全部p7测试条件，非严格场误差界 |
| 缺陷完整/内部/trace范数 | 0.10838507 / 0.10617604 / 0.02177090 | 按这组系数坐标，内部约占缺陷平方范数95.97%；不是物理能量比例 |
| 解差作用identity | A7*(u7-P*u6)=defect-r7，操作差5.34772e-12 | 支持实际缺陷可信；不证明p7真解、inf-sup或条件数 |

C6末端symbolic/numeric/solve/refine约53.68148s，占904.0364s约5.94%。在这个有限例子里，理想地把末端求解完全免费也不足20%总时间；因此不优先恢复NN-PC。此比例不能外推原尺寸，大模型global factor仍可能是决定性瓶颈。

V58已经按计划完成，不是普通bug使三份解未返回。本次不重做C6冷基线、旧FLAT、旧gauge配对、原24弱函数、完整p嵌入随机campaign、旧H7补审或15表算法。没有配平旧完整冷启动对照，不宣布端到端速度倍数。

### 1.1 相邻分支去重

已读取`task42extra_feinn_5nm@a96f7775c9d2f33c85a61535e5512e5e511eae95`的最新V30 review：授权V31保存场审核与保留独立幅值的块波动神经求解。本支不训练、不做M5/字典/teacher、不接管该任务。NN-V3 ref仍为`1f01ae46bbe21f17200350a46513ef5f33e5cf6a`，仅核对ref，不宣称执行结果。

工程线`40dbe138f53b9a2ee39399eac66dc4b0867a2d50`正在维护V15参考逆和保存B0恢复；本次读取其最新提交范围，不授其完整目标结果。dot ref为`15713d3e09b63f65511c7b7f61fa043fdb23dca5`。本支不重新实现参考逆或流式边界，不改/通知这些工作树。这里复用的是**本分支已有**全p嵌入、原单元凝聚、15表和独立场审核。

## 2. 为何这次改变内部空间，而不是继续只诊断

接口未知量控制单元之间的连接；内部函数在本单元边界具有零切向迹，不增加邻单元之间的全局耦合未知量。提高内部阶数后，单元能表达更多内部场变化，再通过静态凝聚反馈到同一批接口未知量。这是有限元内部富集，不是神经代理、后处理拟合或把原p7解截掉一些系数。

定义包络空间，`p_t=6`固定，`p_c=q`为内部/承载元素阶数：

```math
V_{6,q}=\{v\in V_q:\gamma_t v\text{属于同网格p6的相容切向迹空间}\},\qquad q=7,8.
```

同族嵌套Nédélec元素和同一MPC下，`V6`包含于`V_{6,7}`，后者包含于`V7`；同一p6迹下`V_{6,7}`包含于`V_{6,8}`。保留完整g与Cκ。不得据此声称不定Maxwell的场误差必然单调下降，也不自动授通用混阶稳定性。

**新增局部空间不增加本批最终全局行数，但增加内部LU、恢复和场存储成本。** 当前R6遗漏高阶内部平衡只是动机；本轮要用完整M67/M68结果回答它能否实际改善场，而不是再花一整轮估计一个尚不可直接用于求解的稳定性常数。

## 3. 固定物理、规模和身份

使用V58原载波C6及V54 R7对应的同一未舍入descriptor：s=7/135，Z2=(1,1,2)，160hex真实三维NOTCH；lambda0.7nm、grazing1°/azimuth5°/s、幅值1。原κ=(8.94046081729244,0.7821889682108057,0)，**不用G6/G7的κ′**。Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；材料表hash55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2。完整828物理模式m±11/n±4/上下×s,p、参考面、RHS和全部内部特解保持。精确数值/父数组hash从run receipt读取，不由Markdown补低位。

| planned角色 | 最终trace / 内部 / mixed独立FE | 最终含port行 | 临时完整承载空间 |
|---|---|---:|---|
| 已有C6/R6 | 32832 / 72000 / 104832 | 33660 | p6，不重solve |
| M67：trace6/interior7 | 32832 / 120960 / 153792 | 33660 | p7独立FE166208、trace45248、含port46076 |
| M68：trace6/interior8 | 32832 / 188160 / 220992 | 33660 | p8独立FE247808、trace59648、含port60476 |

上述为derived拓扑，现场核对真实MPC/ownership。原局部Nédélec维数p6/p7/p8为882/1344/1944，内部为450/756/1176。mixed67/68局部坐标可用p6的432个局部迹坐标加756/1176内部坐标；高阶实体存储不能被误当最终独立未知量。输出明确`trace_degree=6`、`interior_degree=7或8`、`ambient_degree`和所有行数，不继续只用一个p字段描述模型。

## 4. 最短可实现路径：复用高阶凝聚，再限制接口

### 4.1 真实迹插值，而非按编号裁剪

复用`phase_p_order_consistency.FullBodyEmbedding`的插值/方向思想，建立稀疏`R_tau`：低p6独立trace到同网格高q独立trace。使用Basix元素插值、原DOF变换及两端Floquet primal/dual；每个共享实体只定义一次，不能把来自两个cell的同一插值重复相加。低p6内部函数的高阶切向迹应为零；用实体结构确认，不能用阈值裁剪数值支撑。

p6函数嵌入高q时可能产生高q内部系数。**取迹时可以不保存这些内部系数，因为随后所有高q内部系数都是独立未知量；不能因忽略它们而声称完整p插值只有trace块。** 新空间中的内部恢复必须重新由原方程求出，不固定为零，也不从旧高p场复制。

用少量实际实体/方向核对切向场保持、共享一致、复对偶和局部满列秩；不再建立全局稠密插值或重新跑旧全Q0。p8仅窄扩展同族元素/映射资格，旧degree7开关不能静默把8降为7。

### 4.2 凝聚公式及不会混淆的数学边界

设完整高q原系统已经按全部内部行消元，留下其trace与全部828端口，称为`S_q,bbar_q`。定义：

```math
Q_q=\operatorname{diag}(R_{\tau,q},I_{828}),\qquad
S_{6,q}=Q_q^H S_q Q_q,\qquad
\bar b_{6,q}=Q_q^H\bar b_q.
```

求解`S_{6,q} z= bbar_{6,q}`，再用`Q_q z`及**原高q的全部内部LU、原内部/port载荷**恢复完整高q系数。完整物理场按高q基求值，不投影回p6。不得把此候选称作原p7/p8完整方程的准确逆。

这不是过去被否定的“p传递和凝聚总可以交换”。**这里只有高q内部空间原封不动保留为identity，限制仅作用于高q迹，因此才可在同一高q凝聚后作上述合同。** 一般的`P6^H A7 P6`会同时限制内部，凝聚后不是这里的算子，更不能声称`S_{6,7}=S6`。

最小实现允许用原`scattering_anchor.condense`生成一次高q稀疏`S_q`，稀疏三乘积得到`S_{6,q}`；不对`S_q`做numeric factor。可用薄的`RestrictedTraceFactor`接原`P4CellCondensedInverse`的`solve_repeated`接口：对每次高q凝聚RHS先`Q^H`，调用低迹因子，再`Q`回到原恢复接口。命名/审计必须注明这是restricted Galerkin求解，不冒充旧exact inverse协议。端口等价坐标沿原`CoordinateFactor`，使用实际低trace行数；不得重复scale。

复数必须是真正共轭转置。PETSc `MatPtAP`定义是`P^T A P`，不能未经证明拿来替代`P^H A P`；使用明确Hermitian transpose与稀疏乘法，或同等可核验路径。`C/D/H`、可能非零的内部端口项和非零RHS全部由原高q链继承，不假设`D=C^H`、不删除微小项。

这一原型会暂存高q稀疏Schur、低迹Schur及插值/中间乘积，必须入账。数值因子前尽可能释放高q矩阵和乘积，保留独立原作用及恢复。它不是最终matrix-free实现；若更直接的逐cell投影易于复用，可以做，但不能为重新开发装配器耽误本轮两个真实场。

### 4.3 必要资格，合格就进入物理解

只做一组小型复非Hermitian块系统：非零内部/端口RHS、非互伴C/D、非正交复R，比较“完整受限系统直接解”和“高内部消元后限制迹”的完整恢复；另用改变内部trace lift的反例检验空间一致性。真实资格只补新映射与一个代表cell的两种形成方式。

内部p8的15参考表可复用V57数学核，按实际element/polyset选择覆盖2d的body求积，候选q19，必要对照q31；选两个预登记材料/长宽比类，以独立Basix向量验证，不重新FFCx生成全部p8类。表/工作区不安全就暂停M68，M67及其完整输出继续。普通p8配置/索引/序列化错误同轮最小修复，不要求用户重新批准。

新映射若在2小时目标内接入困难，保留这个同一公式的全局稀疏Schur投影后备，不改成新的PC或新载波；不能只交对偶诊断。新原式真实不可信则隔离依赖并交可用产物，不绕门硬算。

## 5. 直接做两个完整物理解，诊断嵌在前后而不是另开长线

### 5.1 M67：不增加全球接口，检验高阶内部场的实际价值

先从物理零初值运行M67。已有R6/C6、R7仅用于冻结后的比较，不能用于求解初值、RHS或teacher。原高q内部凝聚、物理DtN、低迹direct和完整恢复都真实执行。

可在本case已建立的同一组高7内部LU上，顺带消费V58保存的`Pu6`和内部缺陷：在固定旧trace下求一次局部内部修正，记录其物理scaled-H(curl)范数及对迹残差的反馈。全程无新全球factor/solve；不将“修好内部行后的场”冒充完整解。此短诊断目标600s，缺旧数组或接口不齐不阻塞M67；不建立全局Riesz逆/谱扫描。

M67求解后主要比较R6/M67、R7/M67。前者说明富集实际改变了什么，后者说明当前p7响应是否主要可由低迹＋高内部捕捉。**M67不接近R7也不是软件bug，也不自动阻止安全的M68。** 高空间缺陷和实际物理改变量分别记录，不以95.97%的系数比例预测收益。

### 5.2 M68：同接口进一步提高内部分辨，非uniform p8

M67映射/原式可信且剩余时间/内存能覆盖完整输出时，直接执行同p6接口的M68；这是预授权第二主计算，不等M67场先过1e-4才准继续。只提高内部阶数，物理、网格、carrier、828模式、接口未知量不变。低迹容许相同全局维数，不代表局部LU/workspace免费。

主比较M67/M68；另与R7最多一组诊断。若p8局部数值或容量不安全，保存真实原因，完整交付M67、缺陷分账与成本。不得以扫shift/ordering/正则化或伪逆强行通过，不自动运行uniform p8、p9、Z8、新模式或目标尺寸。

顺序为：窄preflight/映射与块代数 → M67（可顺带局部缺陷响应）→ M68 → 保存场比较/独立VERIFY/费用。每份解返回立即保存完整高基系数、低trace、port、map与source；后处理失败只补消费。最多三次新完整solve/numeric，包含受影响科学修复重放，通常两次；local LU次数独立计数，不混作全球numeric。没有新增普通控制PDE，M66恒等与q=q映射只用小代数或旧保存场验证。

## 6. 独立审核必须对应新空间，不要制造一个必然FAIL的旧Gate

**这是本批最关键的验收接线。** 高q未凝聚独立作用继续由PUBLIC_BASIX和本case独立q63边界产生，不读新Schur/raw来自证。设`J_q=diag(I_internal,R_tau,I_port)`为混合坐标进入高q原增广空间的映射，则：

```math
r_{\rm mixed}=J_q^H(b_q-A_qJ_qx),\qquad
r_{\rm ambient}=b_q-A_qJ_qx.
```

`r_mixed`是这一个新有限元离散的原弱式残差，不是GMRES估计或任意低秩loss；因为新空间定义正是`range(J_q)`。**`r_ambient`对应未纳入的高q迹试验，通常不为零，必须作为离散缺陷单列，不能要求它也过1e-6才承認M67解出，更不能删掉它宣布完整p7解出。** full7/8独立输出字段保留`NOT_A_FULL_AMBIENT_SOLUTION`，不得写旧`FULL_P7_PASS`。

native/增广/精确消去port后的mixed true均按本case混合原RHS归一化，正式<=1e-6；direct目标<=1e-10单列，最多两次既有精化。混合内部所有行、原port、映射一致/MPC/恢复操作门<=1e-10。每个case冻结自己的数学空间和分母；禁止迭代中换分母或通过丢弃已纳入的行来过门。

独立作用中保留所有高q内部行；高trace组用`R_tau^H`拉回，port全保留。验证`J^H A J`作用与新凝聚＋恢复配对、full/interior/trace三列恒等及未置零的内部特解。小型反例必须展示“mixed残差小而ambient残差非零”是正确受限解的可能情况，防止checker误判导致无意义修复。

空间比较一律比较原物理E/H、完整Cκ、240点、828物理参考面复振幅和逐mode功率，不比较未缩放的极倏逝辅助坐标。field/scattered/selected/复通道门1e-4，R/T/A/A_volume增量及独立能量1e-5，逐mode功率1e-6；体吸收与共同场q23/q31操作门1e-10，必要一次q39。不同载波G7不得替代原R7比较；没有精确同离散关系的比较不使用C6的1e-12再现数值冒充预期。

完整物理解只包含本混阶定义，全部系数可重建；不省略内部输出。M67/R7通过最多授`P7_RESPONSE_REPRODUCED_WITH_TRACE6`；M67/M68通过最多授固定接口的内部p增量一致性。二者都不能替代迹分辨、模式截断或连续真解资格。原x方向p6场增量失败继续保留。

## 7. 保留V58已经取得的部署成本，不再把测试成本混回去

两case沿V58 one-run计时边界，从启动到必要准备、mixed原式/恢复、全部场/模式/吸收/provenance/IO和清场，给出真实`T_N1`与采样树峰。研究局部响应、历史场比较、文档checker单列`T_research`；任何失败补消费费用不能偷偷剪除。空的本case数值缓存，OS/JIT命中明确记录，不清系统/邻缓存。旧q63/参考表可作控制，但新的部署成本必须说明复用策略。

p6迹比统一p7的全球含port行少26.95%；比统一p8少44.34%，均derived，不预测因子字节与运行时间按同率下降。本批高q临时Schur存储会抵消部分收益，必须分别列“接口/Krylov维度收益”和“实际整个运行RSS”。M67与原R7没有新的同环境完整冷对照就不授端到端加速比；新增T_N1实测本身仍可用。

报告实际raw/reference、local LU/Schur、稀疏R/三乘积、低迹symbolic/numeric、恢复、独立body/port、输出和IO；区分唯一存储owner与峰RSS。p7/p8内部LU与恢复表增加不能隐藏成免费静态凝聚。

## 8. 2TB/48h：本轮成果应如何连接生产架构

目标仍需准确空间＋matrix-free/分布式Full3D迭代＋流式DtN＋有界粗问题，不是直接扩大本global LU。固定低接口可抑制全球向量/Krylov维度，是本实验相对“全域一起升p”更贴近目标的原因；内部增加仍有存储与计算代价。

复用V58的场景，不重新生成同一库存表。旧极细cell原尺寸情景下65条trace+port主库p6/p7约527.9/727.8GB；若本机制有效，内部p提高时仍可保持p6迹主库，而非换成p7或全FE库。**这只是条件性结构收益，不是准确网格下界、实际FGMRES分配或2TB通过。** 主库之外还要算原作用、局部LU/恢复、mode、MPI复制、正交化、后处理与系统余量。

本轮允许在原型中形成高q稀疏Schur以快速取得科学结果；生产后续必须转为逐cell受限Schur作用`R_e^H S_e R_e`或等价流式作用，不能保留目标规模的高q全球矩阵再投影。此后续不在本批自动开发，不复制邻支PC。

实际决策：若M67已接近R7且M68增量小，下一步优先验证混阶空间的一个有依据的迹h/误差方向并测中间尺度，少接口路线值得继续；若内部富集变化大且尚不稳定，则先确认内部响应/局部块可解析性，不把高p当真；若两者仍不能解释主要差异，则停止这一固定机制，携完整ambient缺陷的分量/区域说明选择一个独立离散参照。不能只交“建议再测”，本批至少争取合法完整M67及独立结论。

不得从904秒线性外推原尺寸48h，也不得承诺NN20。最终要实测完整流程<=172800s和含系统余量的同时内存。本轮不生成桥接大mesh、目标向量或目标PDE。

## 9. 执行预算、可恢复性与减少无关测试

新八小时总研发窗，科学有载最多六小时，最后一小时收尾；实现、修复、等待、失败和文档/IO都在内，UTC/monotonic/boot_id首次冻结，上下文恢复读真实钟。映射/小资格实现目标2小时，局部物理响应仅600s目标；不因可选诊断超时停已可信主求解。每份case启动须给完整独立审核/输出和交付保留至少1800s。M68按p8实际局部/矩阵容量与阶段成本准入，不照搬p6秒数。

沿64GiB同时规划、80GiB警戒、96GiB采样树停止、100000行上限。该行门适用于所有临时高q和最终低迹矩阵；稀疏R载荷<=512MiB，参考表/分块求值新增同时工作区规划<=2GiB；稀疏三乘积中间矩阵另按真实图预估并计入64GiB，不误当小向量工作区。全部原型对象和副本计费。原numeric门保持live树RSS+2×可靠INFOG16/17(decimal MB)+2GiB<=64GiB，ICNTL22=0、自身swap/OOC0，不用OOM试容量。

本任务一次一个actor/一个全球factor，MPI1/math1/GPU0/Loader0。既有受控共享CPU例外按原宿主/PSI/cgroup/邻增长余量、物理核与忙SMT隔离准入；不因邻heavy名字自动停已授权合法轻载，也不绕过实际压力。原锁/隔离政策保持，不改邻任务affinity/进程、ABI/BLAS/CUDA或共享Git设置。资源前台观察相隔>=120s、累计<=1800s；实际不安全就先保存并完成可做轻量工作。

新ignored<=12GiB、Task去重总量<=102GiB、free>=50GiB，先按现场stat准入，旧失败不删除。实际采样gap单列，不把0.5s配置说成连续硬峰。

**普通bug同轮定位、最小修复、受影响targeted回归后继续，不按总次数机械停工。** 累计修复/受影响重放<=2h并服从总窗；同根因两次无效后改诊断或切换已授权稀疏投影后备，不第三次盲重跑。writer/路径/schema/collector错只补消费，不重新求解。新混阶审核字段未接齐优先修对应consumer，不改为要求full high残差零；真正矩阵、物理、ABI或监督不可信先隔离依赖。

不例行全库pytest/CI、全仓索引、全历史hash扫描、重新审计旧15表/FLAT/gauge/24弱函数。只测新限制/恢复/复对偶/高8窄接线、改动文件Ruff/compile及dat validate，一次紧凑文档检查。不要复制V58数万行嵌套array/source清单：新增manifest只引用父hash和本批新对象，展开归档留ignored；科研消费者与文档检查不互相循环触发昂贵PDE。

## 10. 交付和明确的Codex授权

单一新权威为本文件。建议待创建入口：

```text
input/task042_neural_coarse_inverse/v59_trace_enrichment_preflight.dat
input/task042_neural_coarse_inverse/v59_trace6_interior7.dat
input/task042_neural_coarse_inverse/v59_trace6_interior8.dat
input/task042_neural_coarse_inverse/v59_compare_verify_cost.dat
```

统一`python scripts/run_case.py <one-run.dat>`。preflight不暗藏完整solve；p8通过自己的资格和资源后执行，不等待M67先满足物理场门。最终consumer不隐含新factor。formal input_original/resolved/run_manifest/input/physical/numerical/source SHA、parent/map/basis/cell-degree hashes及完整资源保持。新数值核心进src/solvers；runner薄编排，复用当前可恢复输出和独立审核。

C1提交mixed映射/块代数及薄接口；C2 clean source运行M67；C3 p8资格和M68，必要修复只在无活跃受检run的边界提交；C4完整结果/response/费用。全部材料仅本分支，不merge/rebase别支或master，不amend/强推。

交付`response_v59.md`、`outcomes/trace_fixed_interior_enrichment_v59.md`与紧凑records：M67/M68正式mixed残差及ambient缺陷、完整场/模式/吸收/比较、低迹与高内部实际规模、local/global因子存在、T_N1/T_research、峰/gap/swap、修复及未运行原因、唯一下一pilot。更新summary及两总账只追加本轮短入口；不改旧task/review/response/raw。

只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`，核对remote/full SHA/upstream/clean、closed/active null、清场与锁释放后交付用户并暂停。不通知隔壁、不改dot/工程/NN邻支、不自动开新窗口。

## 11. 方法依据与审阅检查边界

[Basix0.10插值与DOF变换](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)、[MFEM静态凝聚公式](https://docs.mfem.org/4.4/classmfem_1_1StaticCondensation.html)、[PETSc MatPtAP](https://petsc.org/release/manualpages/Mat/MatPtAP/)、[PETSc Hermitian transpose](https://petsc.org/release/manualpages/Mat/MatHermitianTranspose/)。这些是公式/API依据，不代表建议升级工作站或迁移其他FE库。接口保持当前合格ABI。

审阅端只做了复非Hermitian小块的全受限解/Schur恢复/改变内部lift配对，差约4.06e-16/2.23e-15；该例mixed残差约4.70e-16而ambient残差约0.837，说明为何两个Gate必须分开。它不是Maxwell实测或新方案成功证据。真实混阶映射、p8资格、物理收益和费用均待执行。Markdown/链接/远程字节与GitHub实际页面视觉核查分列；未取得视觉证据时标NOT_VERIFIED，不因此重跑科学计算。
