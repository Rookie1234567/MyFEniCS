# Review V39：接入分布式体积，条件推进原尺寸完整算子作用

## 0. 决定与目标

**接受V41的有限真实MPI编号桥、原尺寸实际拓扑库存和完整边界owner路由资格；原尺寸0.7nm完整前向计算尚未完成。V42不再增加独立边界演示，集中完成真实分布式体积消费、非零载荷恢复，并在数值和资源门通过后，执行一次原尺寸完整体积加边界的正向／伴随作用。该目标阶段本报告已作条件授权，无需完成小接口后再申请一份review。**

最终对象仍为50×25nm周期、z=−10..130nm、17×25×120nm规则Si光栅、λ=0.7nm的完整三维Nédélec有限元前向解，保留非可分三维能力。完整冷N=1耗时≤172800s、同时任务整树／可用专属cgroup峰≤2e12B；p6/h≤0.7nm目前是容量情景，尚无最终精度资格。接口、一次算子作用、残差恒等式成立，都不等于已经求解。

神经收益门保持**20%**：相同正确性下，相对最佳合格非神经路线，完整耗时或同时峰内存至少改善20%，另一项合规；计入数据、训练、构建、加载、推理、校正、恢复、审核和IO。旧10%只保留为早期历史合同。V41无训练，编号／通信／缓存优化不归神经收益。V42优先建立可用原方程作用与审核链，不引入新的NN、PC或收敛扫描。

本报告回应`execution-review-handoff-20261004-v41`。response_v41已正式回应Review V38，故按AGENTS §15新建**Review V39／下一执行V42**，保留旧报告。审阅只读取源码、冻结数组字节和元数据、重算整数库存及文档检查；未启动新FE、矩阵作用、LU、QR、Krylov或训练，未改求解源码、dot／其他分支／master，无subagents或重置卡。无merge approval。

## 1. 独立证据核验

| 项目 | 核实结果及范围 |
|---|---|
| 本地／远端交付HEAD | `545eee991318664770dec4edafe1ace5f00d02f3`，canonical `/home/fenics/Projects/NN-Lab`，唯一`task42_neural_coarse_inverse`；接手clean、无本任务actor |
| base／上一review／最终运行source | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`718c42ef2be1ce375f940a5092ad503ab3729d5a`／`81c776fddcd173cf7db898f20f3068eb7cf7ae2b`；13份正式运行manifest各按自己的source核验，不用最终文档HEAD替代 |
| 全库导航恢复 | 8311个tracked文件逐件读取、hash及导航；112312867B文本，41份response、38份review与任务书进入索引；不是全仓逐行语义审计 |
| 旧材料保护 | 相对Review V38，3205份旧保护文件字节不变，其中78份旧review／response；README和旧汇总完整后缀保留 |
| 原始档案 | 636个gzip版本双hash及长度通过；622个现存原路径匹配某个归档版本，无现存不匹配；结果文档“当前557”是较早快照，最终636由索引重算，不回写旧结果 |
| 科学数组 | 17个NPZ、708个逻辑及实际成员、0 alias；文件、shape、dtype和C-order payload逐项hash通过；不宣称重跑矩阵／向量运算 |
| 源／测试 | 12份增量Python静态compile；最终实现hash核对；16份JUnit快照保留中途失败及最终38例通过；正式15文档测试、Ruff、ABI／getter回执核对 |
| 资源／标量 | 34次监督逐样本树RSS、swap、峰、后代清场及费用重算；CPU tick／SMT准入重算；251项保存的分子／分母／判定复核；ledger closed、active为空 |
| 目标类独立重算 | 逐个读取530856个owned cell的保存坐标、tag和实际permutation整数；得到270 raw、858 oriented，rank0为108／405、rank1为198／495；不是只采信producer计数 |

[独立核验](outcomes/records/review_v39_independent_checks.json)、[审计脚本](outcomes/records/review_v39_metadata_audit.py.gz)、[全库索引](outcomes/records/review_v39_repository_index.gz)、[本报告文档检查](outcomes/records/review_v39_documentation_checks.json)。索引原文SHA256=`1f2c2b77b53d60eda469bfe8be3f22bc68a9acfb4fbf0c3c2ebf98fa2fa9c208`。重点语义审阅覆盖entity protocol／adapter／topology／dependencies／study、独立checker、runner、测试及原体积／恢复／仿射tensor实现。人工审阅、普通读取和审计脚本费用未单独监督，仍unknown。审计脚本一次变量名遮蔽错误已本轮修复，完整重跑通过；未触发数值重放。

## 2. V41通过什么，尚未通过什么

这里的“实体”是一条边或一个面；它带有一整组高阶系数。owner接口把这组系数交给负责它的MPI进程，并处理周期相位和方向变换，避免每个进程保存全体积的巨大行号字典。这解决数据归属和通信问题，代价是映射、发送接收缓冲及方向转换；它本身不计算体积电磁作用。

| 对象／比较 | measured结果；门1e-10，整数库存精确 | 审阅资格 |
|---|---:|---|
| 连接64hex，三tag，p6完整45000行，真实MPI1/2/4 | 全向量最大差1.4814494150199548e-15，计算slave严格0 | `DISTRIBUTED_NATIVE_ENTITY_BRIDGE_QUALIFIED_ON_FIXTURE`；粗轴跨度不能当h≤0.7精度 |
| MPI4跨rank周期实体 | 边2/1/3/41，面0/0/0/16 | 有真实跨rank通信，不是仅启动MPI |
| 原尺寸低阶geometry/topology，真实MPI2 | 530856hex；555814顶点、1642171边、1617214面 | `TARGET_NATIVE_TOPOLOGY_INVENTORY_QUALIFIED`；未建全目标p6 FunctionSpace／dofmap |
| 精确class | raw270、oriented858；各rank私有合计306／900 | 独立重算相符；air336636、substrate39420、grating154800 cells；实际参考顶点顺序均0..7，方向码75种 |
| 目标新增p6方向 | 62种以旧raw882和native双轴变换补审通过 | 只证明basis变换；没有新kernel或LU，没有证明新体积算子 |
| 全边界owner输入与32060端口 | 提取差1.3930219660660015e-15；振幅2.2101136192453272e-16；forward5.200704032750467e-16；独立y的adjoint及原alpha的modal为0 | `TARGET_BOUNDARY_OWNER_ROUTING_QUALIFIED`，完整378432行／上下各2628面；q30资格继承V38 |
| 新MPI2消费 | 保存owner条目的extract／conjugate scatter通过 | owner组件消费成立；真实distributed volume callback仍未接入 |
| 非零f_i／g与恢复 | V40的8hex／MPI1 anchor保留 | 未升格为MPI2/4完整体积消费 |
| 原尺寸完整PDE、场、功率、2TB48h、NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 没有新official R/T/A、R00_s/p/total或A_volume |

证据：[response_v41](response_v41.md)、[完整结果](outcomes/native_entity_owner_topology_v41.md)、[checker](outcomes/records/component_checker_v41.json)、[实际拓扑](outcomes/records/actual_topology_inventory_v41.json)、[消费接口](outcomes/records/consumer_interface_v41.json)、[运行身份](outcomes/records/run_index_v41.json)。

接受当前已保存的组件结果，但不接受把`stage_dependencies`称为已经对任意未来消费闭合，也不接受把owner散布测试称为完整体积＋边界作用测试。下列缺口应在V42先修复，继续同轮工作，不为其另起小review。

### 2.1 P1：缺失阶段可能被汇总成通过

`src/solvers/native_entity_study.py::finish`把缺失BRIDGE阶段写成仅含`status: NOT_RUN`的字典；缺TOPOLOGY等则直接省略。内部`qualified()`对没有`passed`的字典默认True，空列表也通过。因此缺少必要证据时仍可能产生`INDEPENDENT_NATIVE_ENTITY_CHECKS_COMPLETE`。ROUTING路径又隐含要求局部变量`t/o`先已定义，不能稳健表达“没有新方向时复用此前方向证据”。

当前正式checker的BRIDGE1/2/4、TOPOLOGY、ORIENTATION、ROUTING、ACTIONS确实齐全，本审阅逐项核实，故不是倒判V41数组失败。V42必须按阶段合同显式要求必需集合、rank数、输入／覆盖身份及肯定的通过字段；NOT_RUN、空结果、缺rank、缺方向来源都不能提升资格。加入缺整个阶段的反例，不只测单个packet内缺rank。

### 2.2 P1：消费时的expected必须来自当前调用者

`require_envelope()`将保存的`e['identity']`传给`validate_envelope()`。这验证了包与它自身记录的一致性，却没有在新消费时重算当前物理／配置及阶段依赖。创建envelope时有源比对，不能代替未来每次消费的兼容门。AST选取函数的hash也不会自动覆盖被调用helper、全局常量和配置默认值。

V42消费端独立构造expected，绑定真实调用路径的依赖图、配置／basis／ABI／q／mode、actual owner编号和class manifest；数值依赖变更只使受影响阶段失效。纯runner／文档修复允许复用旧包，但需记录为什么数值语义不变。加入“旧envelope完全自洽、当前材料或helper已变”的拒绝测试。不要改旧成功packet，也不要为改schema重算所有原张量。

### 2.3 P1：完整作用需要正确组合逆映射和对偶映射

当前`CompleteEntityAdapter.extract`从owner canonical系数得到physical实体系数，`canonical_from_physical`做逆；`scatter_into`是extract的共轭转置。V41完整boundary action是在合并后的canonical边界向量上调用，owner scatter另用预登记的synthetic dual验证；尚未把真实boundary traction加回匹配的分布式volume残差。

V42显式定义每个空间及映射。若P表示canonical到physical，physical输入转回canonical用P逆；对应的力回传是该逆映射的共轭转置，不能直接把P的共轭转置当作同一个接口。实际还包含owner求和和周期约束，必须从所用完整映射推导。用一般非零复输入、独立dual及非互伴端口反例检查组合，不能靠正向再逆向相消来掩盖错误。

### 2.4 P2：raw缓存共享仍是有条件的设计

270不是858的同义词。单元内部450个未知量不受边／面方向变换，但所有trace块、恢复和对偶项都要按实际方向作用；仅“LU可复用”不能证明完整oriented算子可复用。本审阅从保存数组补验了858及各rank计数，而当前checker主要独立重算raw库存；V42把oriented key和rank users的独立重算纳入checker。

传统缓存和方向优化有价值，但其正确性、完整时间与内存必须分别测量。V42只准入消费所需的有限局部LU，**不生成目标270／858类LU或另做共享factor实验**，保留与dot的分工。

## 3. 成本及目标差距

| 项目 | measured／derived值 | 含义 |
|---|---:|---|
| 监督／probe／bootstrap／收尾 | 582.874271517＋44.272283111＋3＋5＝635.146554629s | 34次监督，所有失败／修复收费；不是完整目标N=1 |
| native保守／目标阶段 | 580.737223476／168.049239116s | 总收费内子集，不再次相加 |
| 原尺寸拓扑／新增方向 | 41.160119517／70.441853583s | geometry-only成本及方向审计，不能外推成体积作用时间 |
| 整树采样峰／ownswap | 1895116800B／0 | 配置0.5s，实际最大间隔1.722761994s；非连续cgroup硬峰 |
| 新存储／Task artifact | 成本记录快照1877078033B／17417388941B | 后续少量文档有快照差；最终库另留256MiB；数组压缩量不是RSS |
| 历史监督下界 | 81610.59579075915s | 旧未监督实施和完整历史N=1仍unknown，不重置研究费用 |
| raw矩阵270／MPI2私有306份 | 3360631680／3808715904B | 条件载荷，不含Python映射、解码及通信 |
| 858 oriented矩阵／MPI2私有900份 | 10679340672／11202105600B | V41没有生成这些矩阵；不应默认全部常驻 |
| raw类LU＋恢复＋Schur条件载荷 | 节点共享3363223680B；rank私有3813057504B | 保守int64 pivot；不是实测因子RSS或已经实现的共享方案 |
| 单份完整native complex128向量 | 5532337056B | p6 storage345771066；独立trace105298704＋内部238885200另为344183904行，两者不能混叫native全号 |

[资源原账](outcomes/records/resource_costs_v41.json)、[原始档案](outcomes/records/raw_evidence_index_v41.json)、[容量](outcomes/records/original_size_integration_capacity_v41.json)、[就绪矩阵](outcomes/records/integration_readiness_v41.json)。BRIDGE1的flat-array错误、ROUTING输入y/x错误及测试失败均保留；复用可信checkpoint继续，处理方式正确。邻任务影响仍INCONCLUSIVE，ownswap0不等于无干扰。

V41已把“原尺寸编号库存未知”变成真实数据，下一瓶颈是**原尺寸完整体积作用和其消费链仍未执行**。继续只做边界路由不会回答全体积一次作用要多久、完整残差是否能在预算内核验。V42因此允许以下有界推进；不以接口成功自动解锁求解。

## 4. 历史去重与互补分工

| 路线 | 已尝试／否定／未运行及本轮决定 |
|---|---|
| V1–V5 p4严格神经粗逆 | 已关闭；不复活global p4因子 |
| V6–V14神经FE trace、固定特征、线性头、hidden训练 | 分别评价；V11 hidden未运行、V12梯度失败、V13一次更新非整体成功；没有V41训练增量 |
| V15–V21全空间校正／算子复用 | 算子加速不等于收敛改善；GPOLY含随机神经G0，不是纯非神经最佳基线 |
| V22–V23 Galerkin／image-QR | 表示98.99%不等于可消残差；V23完整0/6，warm Schur约2.5077e-6、通道功率约1.69973e-6超门，zero约0.0681；全部LU／QR费用保留 |
| V24八块local及image组合 | 已正式运行，完整0/5；LZ4约0.081376668、LCZ4约0.325262223；不能再说V24待运行，禁止换p1测试／scalar-tau／追加旧周期 |
| V25–V34方向与回流诊断 | 软件、资源与数学负结果区分；单步放大不证明GMRES必失败 |
| V35七区PC／zero GMRES256 | Schur0.2052488635>0.01继续门；七／八块旧路线关闭 |
| V36–V38原尺寸端口／积分／全边界 | q30完整边界通过；q15最大差1.325947e-5 FAIL、native q60存储门保留；无完整volume |
| V39–V40恢复链 | V39真实运行失败不倒改；V40有限8hex非零载荷恢复和原残差恒等式通过，仅MPI1 |
| V41实体／owner／目标拓扑 | 本轮新增实测；不等于distributed volume或PDE |
| 目标冷solve／场功率／2TB48h／NN20% | 仍未运行／未资格化；不能授整体成功 |

原任务书、全部历轮response／review／raw继续保留。[Review V21](review_report_v21.md)、[Review V32](review_report_v32.md)、[Review V35](review_report_v35.md)、[Review V38](review_report_v38.md)提供关键历史入口。warm-start与zero-trace、误差空间和真实残差、传统算法和训练贡献始终分开。

dot远端只读核实仍为`077ec9c8386c976da232093779279fb9d1a93033`。其最新可读response_v15仍为缩小几何、p4、manual532的X/XZ/Y校准；随后p6源码保存提交不是新目标运行资格。材料差2.991716531811656e-8及原目标mode／canonical／恢复缺口仍在。dot继续负责参考逆、周期分块、共享因子和求解规模路线；本轮不执行其C1/X/XZ/Y、不迁移旧因子、不改其分支。

V42的原尺寸作用属于**Task042边界与体积的接入及原残差审核路径**，不是第二套参考逆或factor／MPI性能扫描。优先复用本分支已有`AffineIsotropicMaxwellTensorFactory`及体积form语义，新增代码只承担必要的owner消费／完整作用。若dot提供身份相同的可调用引擎，只读审查后可替代相同阶段，不同时跑两个引擎；缺包不作为停止自身有限接入的理由。

## 5. V42一次连续执行合同

### 5.1 修复消费门，冻结真实体积协议

先完成§2四项，保留旧包，新的stage DAG明确每个数值对象由哪个source／配置／ABI／数组产生。核心进入`src/`；既有通用runner参数化扩展，不再复制task-numbered求解器。packet原子发布；昂贵构造后立即保存，不让后续方向、元数据或checker错误迫使从头重建。

体积consumer须提供caller-owned的canonical owned／ghost向量、cell内部系数、实际owner实体映射、正向／伴随作用、非零内部f_i及port g、恢复和原残差接口。禁止目标路径调用全trace Python字典allgather、全native长度G/GH或逐行小数组列表。MPI collective可用于小class表／标量归约；大系数仅交换实际所需实体。

冻结同物理：nominal0.7nm／source0.699999988显式alias；Si n=0.999885140474+4.32477054e-6i，epsilon=n²、mu_r=1、三tag、1°s及原Floquet／参考面。不得换成dot近似材料、缩短物理尺寸、降p或删除mode以求通过。

### 5.2 接通真实体积，并闭合有限分布式恢复

本阶段两个互补anchor在同一工作包连续完成，不再为它们分别交回。

**A：连接体积anchor。** 复用V41同一64hex三tag／原大周期／p6几何及实体packet。其全局raw类只有6种，足够检验跨cell和跨rank传播。用已有仿射各向同性体积factory产生这6类原矩阵，物理系数逐项来自正式Maxwell form。该factory把不同长宽高单元的积分拆成六份共同参考矩阵，再按真实宽度组合；它减少重复积分，付出参考矩阵和方向转换存储，适用范围严格限轴对齐仿射hex、分片常数各向同性材料、无PML／额外penalty。它仍作用于全部三维882个单元基，不是二维或分离场近似。当前代码已有此实现，本轮不是新建另一套Maxwell模型。

先与V40保存的原raw矩阵比较，再对本64hex的全部6个精确宽度/tag类验证native q15和独立q17积分，完整矩阵相对差≤1e-10。允许一个64hex native原体积CSR作为独立oracle，**不分解该全局CSR**；生产完整正向／伴随与oracle全向量比较≤1e-10，零／复缩放、slave语义、内部与共享面均检查。真实MPI1/2/4顺序运行同一consumer，使用同一canonical输入和完整输出；原CSR只需一次MPI1装配，其他rank数通过实际native实体桥比较，不重复装配同一oracle。所有raw张量／CSR／向量立即保存。

允许为这6个raw类各构造一个450行局部内部LU，用于有限非零f_i的压缩、恢复与内部平衡核验；这是单元内部消元，不是全局粗逆。方向在使用时施加，禁止按所有oriented类重建等价LU；若具体实现需要不同因子，先给出代数原因和预算，不能静默扩成几十类。新增成功局部LU全局唯一≤6，失败尝试单列计费；不借此开展共享factor性能实验。

**B：完整体积—端口恢复anchor。** 将V40已保存的真实8hex、原4类LU／CSR／C/D和非零f_i/g接入新owner consumer，顺序做MPI2/4的新进程消费，保留其12个冻结mode。需要时只重建同一8hex的真实native编号／MPC桥，不重算旧kernel、LU或原CSR；producer原MPI1编号与当前consumer编号明确分开。对原作用／伴随、凝聚RHS、仿射恢复、内部平衡、native／增广原残差恒等式和完整12复通道逐项≤1e-10，与不可变V40 oracle比较；不能只比较两个使用同一错误adapter的实现。

A证明连接体积和三tag／跨rank作用，B证明真实port与非零载荷恢复；**不得把B的8hex断连边界片段说成贯通全高的求解**。A不能借B提升粗网格精度。也不得把B的高横向频率12mode直接移到A的大面片上并无条件沿用q30：本轮不为这种几何变更另开Fourier求积campaign。原尺寸目标继续使用V38已资格化的真实细边界及全部32060mode。

原增广关系保持`[V,B;-D,I]`，有效RHS为`f-Bg`，原残差为`r_FE-B*r_port`；D只归一化一次、Hp=I隐式。一般非Hermitian／非互伴端口反例仍保留。通过才授`DISTRIBUTED_VOLUME_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES`，不是目标solve。A/B通过后自动继续5.3，不等待review。

### 5.3 条件准入原尺寸完整作用，不运行求解

**本报告新增授权范围：** 消费V41已保存的原尺寸MPI2 geometry／实体／owner packet和目标轴，构造分布式canonical高阶实体系数及cell内部系数，执行全530856cell体积与完整V38边界的组合正向一次、独立输入的伴随一次。允许这些完整系数向量；仍不要求也不授权构建目标DOLFINx p6 FunctionSpace／全局CSR／SH或任何目标LU／Krylov。生产接口必须真实处理全部内部与trace未知量，不能以只动边界的callback替代。

先依据5.2测量的真实对象、class构建和单cell／分块作用成本，冻结准入表；允许至多一个固定≤4096个目标owned cell的分块作为实现工作区及耗时校准，不做h/p/MPI扫描。该分块必须使用真实目标宽度、tag和方向，费用属于目标子预算；若无需它已有充分实测依据可省。分块不是原尺寸成功证据。

目标270个raw矩阵可由同一组已验参考积分生成并分块保存／按rank使用；全部精确IEEE宽度、三tag、实际方向必须覆盖。独立q17参考积分按完整270类重算比较，逐类≤1e-10；允许保存共同参考积分、每类几何／系数／矩阵hash及完整比较字段，避免把每个派生副本都常驻。保持native q15六类／V40原矩阵的独立来源anchor，诚实说明目标270类没有逐类运行FFCx。禁止将相近浮点宽度舍入合并。方向可按实体变换向量，不物化858份oriented矩阵；接口与checker分别验算映射、共轭和重复求和。

入场必须同时满足：全部有限数值／身份门通过；保守同时树峰预测≤32GiB；剩余有载覆盖完整目标正向／伴随、保存与独立检查，并留至少25%时间裕量；新增存储及宿主余量满足§6。缺测量不得填造预测，小块线性外推须加通信、Python索引、缓存解码、IO和不确定性，不能只用BLAS计时。

输入为预登记、独立的一般复向量x/y，覆盖所有owned trace和内部系数；固定seed、canonical编号、归一化及幅相，完整保存或以无损分片和可独立重建的逐片hash绑定。正向与伴随输出完整保存，不抽查若干cell或通道代替覆盖。各rank仅保存owned结果，ghost单列；整数coverage证明每个cell／实体贡献恰一次，周期slave计算存储与physical展开分开。验证全局双线性恒等式、全32060复振幅和真实boundary traction返回到volume的完整组合。内积门为归一化双线性差≤1e-10；范数尺度和近零绝对规则在运行前冻结，不能用相位拟合或重标幅值通过。

生产完整动作中的体积结果、边界结果和组合结果分别给出hash／范数／完整覆盖。独立checker不调用生产apply来生成expected；从保存类、literal映射及完整输入输出分块复核有限anchor与目标全局恒等式／覆盖。目标没有独立全局native CSR时明确保留该限制，不把伴随恒等式单项作为物理正确性全证据。目标可授`TARGET_FULL_OPERATOR_ACTION_QUALIFIED_IN_ENTITY_REPRESENTATION`，明确限定该离散和canonical表示；不能称已建立全目标native p6 DoF编号或取得目标场解。

只执行上述必要完整调用；普通bug修复后可复用已发布可信阶段，受影响的完整作用可在真实剩余预算足够时定点重放，全部失败／修复累计收费，不新增试验对象或刷新账本。禁止用大批随机RHS／多MPI数重复测速，禁止目标270类LU、全局QR／PC／Krylov／训练、旧q60与七／八块重启。若采用其他已有体积引擎替代factory，仍须同一物理／依赖／完整验证，不并列增加路线。

### 5.4 交付能用于下一次求解的接口与成本合同

新进程必须真实消费至少有限A/B产物；目标通过则新进程检查其不可变包和可调用入口，不为了“部署演示”再免费执行两次全目标作用。交付`apply_original`／`apply_original_adjoint`／boundary extraction及正确dual回传／finite recover／full-residual入口，错误source、material、rank、class、phase、缺阶段均拒绝。原尺寸recover如未实际执行，明确NOT_QUALIFIED；不把有限局部恢复吞吐量线性外推为已通过。

至少更新以下四项：完整目标算子是否实际可执行；其单次总成本与峰；可供dot或后续solver调用的精确协议和缺字段；求解准入还欠什么。原算子作用和凝聚／PC一步不是同一计时对象，不能把实测的原残差审核时间直接替代Krylov单步。已知量与unknown保留在式中：

```math
T_{N=1}=T_{setup}+K(T_{solve\_action}+T_{PC}+T_{communication})
       +T_{recovery}+T_{original\_audit}+T_{IO}\leq172800.
```

给出明确有条件的K预算或无法求K的缺失项；不得声称原算子通过即可48h收敛。下一次完整solve仍需匹配且已资格的参考逆／PC、收敛策略、真实非零物理入射RHS、恢复／场功率和精度／mode合同。dot包不足时列出具体缺字段和可直接消费的本轮接口，不简单写“等待dot”。保留无需NN的最佳候选成本，神经训练须待有可验证的剩余瓶颈后再决策。

### 5.5 失败后的有效替代及停止条件

| 门／故障 | 同轮行动与停止范围 |
|---|---|
| 导入、路径、schema、lint、计数、MPI接线、数组寿命等普通bug | 自主定位修复、定点复验、从可信checkpoint继续；没有真实数值／身份／ABI／资源门不允许以“等review”停止 |
| raw矩阵或方向／dual比较>1e-10 | 保存分子分母与最小完整反例，分离物理系数、积分、方向、phase和owner求和；有确定bug则修复；仍不等价则停止依赖目标阶段，完成已可信体积／恢复数据和成本分析 |
| 目标预测>32GiB或剩余时间／存储不满足 | 不启动越门actor；同轮先消除全局dict、重复解码、全oriented缓存及全量中间张量，保持同一算法和离散后重算一次准入；仍不过则输出逐对象下界／主导项、实测块成本与缺口，不能仅报测试失败 |
| 已准入目标actor实际触资源／时间门 | 停完整自有进程组，保留完整失败费用及已提交分片；不缩网格冒充目标、不重置账本；检查和部署有限可信部分继续 |
| 目标全局恒等式失败 | 不授目标作用资格；用已保存输出按rank／实体／cell归因，禁止改容差或改输入追求通过；修复后只重放受影响允许调用 |
| 无匹配dot包／无可靠PC | 不阻止A/B或合格的目标原作用；不运行目标求解。交付明确consumer／残差协议和完整成本，旧PC不借机复活 |
| 完整预算耗尽／物理身份或ABI不可恢复 | 停依赖数值工作，清场交付真实失败与NOT_RUN；不把资源停止等同数学路线失败 |

## 6. 本轮预算、验收与交接

V42是新的实质范围，旧ledger全部保持closed。首次接手固定UTC／monotonic／boot，日历24h、最后1h只作交付；总有载≤14400s，有限native／oracle／恢复≤6000s，目标构造／类审计／分块／正向伴随及其检查≤7200s，均为总额内子预算，不重复相加；probe累计≤90s、末180s清场。每次准入为下游验算和交付留额，不让BUILD吃完预算。未监督实施、git和普通元数据仍明确unknown，日历不刷新。

交付前宿主只读检查仍可见Task39extra和Task042extra的其他任务进程；本审阅未干预它们。“无本任务actor”不等于整机空闲。执行端必须重新核实机器级heavy锁和当前资源合同；原尺寸目标作用不得与其他heavy case同时运行。锁或排他条件不满足时，继续文档、实现和符合原限制的轻量检查，保留实际资源门，不绕过它启动48GiB阶段。

本轮增加内存／存储上限是为了容纳真正的原尺寸完整向量，**只适用于上述目标作用**：整树warn36GiB、hard48GiB，准入预测≤32GiB；有限native warn6GiB、hard8GiB，辅助纯测试2GiB。大数组保存／checker若实际需目标内存，归入目标阶段和预算，不藏进辅助费用。ownswap0、无OOC／GPU，数学线程1；有限MPI1/2/4、目标固定MPI2。分区向量、ghost、通讯、解码、页缓存口径及采样漏峰明确报告；若使用memmap，文件页并不免除同时驻留和IO收费。

四份完整独立系数向量约22.03GB，加rank私有raw载荷约3.81GB、拓扑约0.64GB只是payload情景，不是RSS上界；native storage每份5.53GB另有slave，不混计。实施时按生命周期避免四份全驻留、避免复制全局输入到各rank。新存储≤40GiB、Task artifacts总≤64GiB、free≥100GiB，启动前另留≥1GiB证据／交付额度；这是对V41的2GiB／20GiB的显式限定替换，旧失败不回改为合规。不得删除旧科学证据凑空间。

现场有效MemAvailable须覆盖任务预算并另留max(128GiB,有效总量10%)，按所有rank实时CPU／SMT、邻任务、PSI及宿主压力准入；一次一个自有heavy，不能与另一窗口并行仓库工作，不干预邻任务。资源忙是实测资源门，不是软件bug；CPU暂缺至少120s后再探，总probe／日历不刷新。沿用本任务资格化native activation、complex128／IntType64同ABI、实际库路径和getter，不能用未激活解释器运行测试。

新有限mesh累计≤512hex（含64/8重复桥和必要native单cell参考），不新增第三种fixture。成功局部内部LU新类≤6；目标LU／全局factor／QR／Krylov／训练次数0。目标只消费已存530856hex拓扑，若包不兼容先定位，不默许再建一次全目标p6空间。完整actor预告预计时长、日志和终止语义，监督全部后代，记录实际采样间隔。

验收采用最小pure反例→有限真实组件／MPI→Task-focused、Ruff、compile、ABI/getter和15项文档合同；同source／输入／hash未变的昂贵Gate不重跑，不为文档错误触发全仓测试或环境重装。checker断言本次版本、文件及来源，不沿用错误旧路径。

最终一次交付response_v42、outcomes表格、阶段DAG、真实volume consumer与finite恢复、条件目标全作用或精确受控停止、完整run/source／数组／raw／资源／清场记录、就绪矩阵及按依赖组selective manifest，同步总账。每个资格写清范围；原尺寸full residual≤1e-6、完整场／复振幅≤1e-4、R/T/A/A_volume≤1e-5、逐通道功率≤1e-6、能量／吸收≤1e-5及h/p/mode准确性，未实际取得仍全部NOT_QUALIFIED。不能把一次作用的向量当作物理解后发布功率。

Git一律`-c gc.auto=0 -c maintenance.auto=false`，同一分支精确refspec提交推送，不amend／force／merge，不修改dot／其他分支。ledger closed、全部自有actor清场／锁释放、clean/upstream0/0及远端完整SHA核实后，通过原队列`execution-review-handoff-20261004-v42`交回，回应`review-execution-handoff-20261004-v39`，随后停止仓库工作。GitHub精确V41页面本次仍Cache miss，视觉NOT_VERIFIED；本地文档检查不是网页视觉或CI资格。
