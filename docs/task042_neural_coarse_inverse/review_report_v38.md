# Review V38：接受有限体积恢复，推进原尺寸拓扑与分布式接入

## 0. 决定与最终目标

**V40补齐了真实有限体积作用、非零内部载荷恢复及新进程消费，接受其8hex见证资格；原尺寸0.7nm完整前向计算仍未完成。V41集中交付“原尺寸实际几何／方向库存＋真实MPI的有限编号桥＋可消费的边界owner接口与容量合同”。不再单开边界测速或重复8hex LU轮次，不开展与dot相同的参考逆、共享factor或收敛实验。**

最终对象仍是50×25nm周期、z=−10..130nm、17×25×120nm规则Si光栅、λ=0.7nm，完整三维Nédélec有限元前向解，并保留非可分三维能力。完整N=1耗时≤172800s，同时任务整树／可用专属cgroup峰≤2e12B，系统与邻任务余量另留。p6/h≤0.7nm当前只是容量情景，不是已经证明足够准确的最终离散。

神经增益门为**20%**：相同正确性下，相对最佳合格非神经路线，完整耗时或同时峰内存至少改善20%，另一项合规；数据、训练、构建、加载、推理、校正、恢复、审核及IO全部计费。旧任务书10%只保留为首轮历史门，不再适用。当前没有目标完整非神经基线、没有新增训练；边界结构、LU、缓存和编号优化不是神经收益。

本报告回应`execution-review-handoff-20261004-v40`。response_v40已回应Review V37，符合AGENTS §15新建下一正式报告条件；下一执行为**Task042 V41**。审阅期间执行窗口停止。本次只读源代码、原始字节和元数据，没有启动新FE、矩阵作用、factor或solve，没有修改求解源码、dot／其他分支／master，没有subagents或重置卡。无最终成功或merge approval。

## 1. 本次核验范围与证据身份

| 项目 | 独立核实结果 |
|---|---|
| 本地／远端交付HEAD | `b2dcd6a7497f272abb4c5298d8830b41fb803b84`；canonical `/home/fenics/Projects/NN-Lab`；唯一分支`task42_neural_coarse_inverse`；接手clean、无本任务actor |
| base／上一review | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`f3bf7942f62e725057c3ae44820bc1ca1794ee59` |
| 首次构造／后续修复源码 | `48e4c0d8fdcea0a37e03cdc5812e58b03d4fa1d3`／`920527707948c2325f0750af1d50cdc479551f69`；文档HEAD不替代运行源码 |
| 全库恢复索引 | 7623个tracked文件逐件读取／hash／导航，110050583B文本；40份response、37份review及任务书进入索引；不等于全仓逐行语义审计 |
| 历史保护 | 对上一review核验2840份旧保护材料字节不变，其中76份旧review／response；README及三个任务汇总保留旧后缀 |
| 原始档案 | 339份gzip双hash及长度通过；330个现存原路径匹配某个归档版本，无现存内容不匹配；394份合成fixture无损归档另验 |
| 科学数组 | 11个NPZ，**129个逻辑成员、120个实际NPY成员、9个alias**；文件／dtype／shape／C-order内容hash逐项通过；Fortran布局按索引次序重排字节核验，未运行数值矩阵运算 |
| 源码与资源 | 7次正式manifest及checkpoint的source依赖hash核对；19次监督逐样本RSS／swap／峰／清场、CPU tick／SMT准入和费用重算；ledger closed、active为空 |
| 保存的测试／标量 | 13份增量Python静态compile；7份JUnit保留39例1失败及后续修复，最终40例通过；66个分子／分母／判定重算，15文档测试及ABI/getter、Ruff等回执核对 |

[独立记录](outcomes/records/review_v38_independent_checks.json)、[审计脚本](outcomes/records/review_v38_metadata_audit.py.gz)、[全库索引](outcomes/records/review_v38_repository_index.gz)、[本报告文档检查](outcomes/records/review_v38_documentation_checks.json)。索引原文SHA256为`637dd7e8c60ebae445302b367a28c7ddb3bfbf7739979f0c132858c66ea7deb7`。深入源码审阅覆盖新增恢复／packet／checker／runner／测试、稀疏adapter及相邻凝聚、方向和编号路径；没有声称本次重跑66项向量运算。人工审阅和一般IO成本未监督，保留unknown。

**计数纠正：** `array_inventory_v40.json`的`logical_members=138`与逐包成员表不符。逐包为0、10、10、10、10、7、18、4、8、41、11，总129；再加9个alias才是138，属于重复计数。11包文件完整，非丢失9个数组。V41在新response／记录中明确纠正并让汇总从实际receipt生成；保留V40原记录，不为此重跑数值或单开review。

## 2. V40成立的结论及其边界

单元内部的未知量可以用小型LU消去，但恢复时必须补上内部非零载荷产生的特解。V40把原体积、端口、周期约束和这项特解连接起来，再用独立装配的小矩阵检查。因此新增的是正确接线和可恢复数据，不是已经求出了电磁场。

| 对象／比较 | measured结果与门 | 审阅资格 |
|---|---:|---|
| 8hex xy_corner／p6／两材料／12mode | 7056 storage、2796独立trace、3600内部、660slave；实际MPI1 | 只覆盖上下边界角点有限见证，没有贯通全高的体积传播 |
| 原体积 vs 独立CSR，一般a正向／伴随 | 1.82757032779e-14／1.82955389138e-14<1e-10 | 原作用和共轭转置一致；非Hermitian／非互伴端口合成反例另有测试 |
| 非零f_i、g与仿射恢复 | f范数112.7807031283，g范数5.47891418907；仿射差4.63203030563e-16 | 未缩放载荷；存储slave为0、物理展开保留相位；特解未当作误差场 |
| 最大局部内部平衡 | 2.40980311198e-10 / 59.341399371 = 4.06091386035e-12<1e-10 | 无局部精化；不能解释成完整PDE残差 |
| 原native／增广恒等式 | 5.48586872447e-17<1e-10 | `[V,B;-D,I]`，有效RHS为`f-Bg`，`r_native=r_FE-B*r_port`；一般输入并未求解 |
| 压缩RHS／凝聚作用／原trace残差注入 | 2.66051930632e-17／4.22687826858e-17／3.96077373003e-14 | 有限恢复链闭合；原C/D浮点内部项保留 |
| 两材料体积q15/q17/native矩阵 | 最大4.13409338553e-15<1e-10 | 仿射常材料多项式体积积分资格；不推翻Fourier边界q15的旧FAIL |
| 新进程消费 | 真volume正向1次、伴随1次；非零RHS恢复及原矩阵审核通过 | `REAL_VOLUME_RECOVERY_CONSUMER_QUALIFIED`；不是零callback |
| 完整原尺寸PDE／场／功率／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 无新official R/T/A、R00_s/p/total或A_volume |

授予`COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES`，范围限实际8hex、固定12mode、边界q30／体积q15-q17、MPI1及上述source。独立checker确实从原CSR、C/D、局部原矩阵、保存LU和RHS重算；LU以L/U乘积与置换重构原V_ii，无新的分解。两条来源和checker数学有实质独立性。

首次BUILD因Basix实数方向变换接口拒绝complex128而失败。修复分别对实部／虚部的两个轴施加同一实变换，符合`T A T^T`，不会变成共轭或改写非Hermitian体积。之前昂贵张量、LU及CSR已保存，后续只补求积；两次源码间没有改变已保存class所依赖的数值核心，当前复用可接受。

**方向覆盖尚窄。** 四个真实class的permutation均为0，原张量与oriented张量因此逐位相同并以alias保存。非零方向测试使用p2合成复矩阵；它支持修复的代数公式，但不授予目标所有p6方向／真实MPI资格。八个角点片段还没有检验连接的体积内部共享面与跨rank通信。此边界必须随部署包保留。

物理继续冻结：nominal0.7nm、source0.699999988显式alias；Si n=`0.999885140474+4.32477054e-6i`，epsilon=n²、mu_r=1、1°掠入射s偏振，原参考面−10／130nm。原尺寸raw库存含air/tag1、substrate/tag2、grating/tag3；有限见证只有前两tag，虽两Si区域材料值相同，也不能默认所有tag路径都已执行。

证据：[response_v40](response_v40.md)、[完整结果](outcomes/native_volume_affine_recovery_v40.md)、[独立checker](outcomes/records/component_checker_v40.json)、[checkpoint](outcomes/records/checkpoint_inventory_v40.json)、[消费包](outcomes/records/deployment_package_v40.json)、[原始索引](outcomes/records/raw_evidence_index_v40.json)。

## 3. 成本、容量与下一步必须解决的问题

| 项目 | measured／derived值 | 解释 |
|---|---:|---|
| 19次监督／probe／bootstrap／close保守额 | 1260.375694644＋24.514265201＋3＋5＝1292.889959845s | 包含失败、测试和归档；不是完整冷N=1 |
| native／慢oracle；formal组件 | 934.331522755/2400s；966.454819266/5400s | 总额内子集，不能再次相加 |
| 初次BUILD／补求积 | 860.362899838／34.735824945s | 初次失败费用保留；没有重建mesh、kernel、LU或小CSR |
| class构造／其中kernel／其中LU相关 | 282.005639117／275.595345427／0.777338275s | 子计时嵌套；小LU快不等于整体setup快 |
| 原小CSR／保存 | 550.145130343／7.032965543s | 实际装配且未分解；不得把oracle无偿排除或外推到全目标 |
| 实际4个450内部LU与cache | 56274336B | 含恢复、RHS投影、Schur等；原矩阵／oracle／加载副本另算，无全局QR／p4因子 |
| 同时整树采样峰／own swap | 1265823744B／0 | configured0.5s；BUILD实测间隔中位0.878012s、max约1.07810s，非连续cgroup硬峰 |
| 新存储／Task artifacts | 482946231B／15589782476B | 最终快照；pre04曾越2GiB，不能改称全程合规 |
| 历史监督研究下界 | 81027.72151924176s | 接续旧下界及V39/V40监督；未监督实施、元数据及完整旧N=1仍unknown |

[成本](outcomes/records/resource_costs_v40.json)与逐样本审计支持上述结论。pre04合成fixture存储停止、pre05缺name、首次BUILD及post01元数据断言失败全部保留。共享工作站邻任务影响仍INCONCLUSIVE，不能凭own swap0宣布无干扰。

**P1：原尺寸不能直接调用现有全局Python编号路径。** `_owned_trace_numbering`／`_trace_constraint_map`把全部trace编号allgather并在每个rank建立全局dict及逐行小数组；`LocalNativeVolumeAction`建立全storage长度G/Gᴴ。目标trace超过1亿，向量345771066行；把270类缓存共享了，并不会消除这些对象。新增接口必须以实体、owner和需要的ghost条目为单位传递；rank增加时不允许每rank复制全局trace字典。V41不重写dot的体积引擎，用受资格的接口包和明确不兼容项隔离这条旧实现。

**P1：86880B不是完整构建工作区上界。** 已去除`84×Nvolume`稠密数组和全native长度转置指针，这一改进成立；但`build_literal_adapter`仍先建882×84 float64方向数组，单此项592704B，另有primal、local、索引、差值，以及同时存在的`coefficients`／`rr,cc,vv` Python列表、COO／CSR／Eᴴ副本。`scatter_into`还产生按全部nnz的repeat及乘积。86880B只是一项条件实体载荷，不能当整条构建链峰值。V41给出预分配／分块构建和散布的真实共存表，不能只把最终CSR字节当RSS。

**P1：checkpoint依赖合同需按阶段闭合。** 当前`dependencies()`只列五份数值源码；决定geometry／quad／recovery的`native_integration_study.py`、`target_boundary_witness.py`、`native_recovery_study.py`相关函数和部分配置来源未进入该复用拒绝门。正式run总manifest记录了它们，因此V40来源仍可审核；但将来修改这些依赖时，单靠`PacketStore.read()`不能阻止陈旧包复用。V41新增不可变的阶段依赖图／新消费envelope，以实际产出source与输入hash为准；纯调度变化允许复用前置包，改变积分／恢复公式必须使对应包失效。checker也核对system列出的class manifest hash，不只接受另一个同名自洽packet。禁止回写V40的成功checkpoint或为修元数据重算全部LU。

**270类是有用的新信息，但还不是缓存容量证明。** 本审阅独立遍历保存轴的全部530856个盒子，按原矩形材料谓词重算，得到完全相同270个raw宽度/tag键：air336636、substrate39420、grating154800 cells。相近浮点宽度没有四舍五入合并。尚缺actual native canonical顶点次序、orientation类、各rank用户和驻留生命周期。

若暂假设每raw键仅一种方向、一个450 float64单位阵全共享：270个raw882矩阵载荷3360631680B；LU／pivots／恢复／RHS投影／Schur及共享单位阵为3362737680B；如果oriented矩阵另存，再加3360631680B。它说明**逐cell缓存4956275464704B>2TB不能直接否定精确共享路线**，也不能据此宣称路线已合规。方向类、Python映射、通信、solver向量、加载alias解码副本和audit仍须加入。字节dedup不会自动保证加载后的内存共享，当前`read_arrays`会分别解码逻辑alias。

本轮真实消费装载10.88413s、两作用合计0.170528s、恢复0.061963s只是有限包。目标还缺完整体积作用、PC及K；公式仍为`T_setup+K*(T_volume+T_boundary+T_adapter+T_PC)+T_recovery+T_audit+T_IO`。边界约0.08s或微型LU用时不能证明48h。

## 4. 历史去重与分工

| 路线 | 已有结果及本轮决定 |
|---|---|
| V1–V5 p4严格神经粗逆 | 关闭，不复活global p4因子 |
| V6–V14神经FE trace／固定特征／线性头／hidden训练 | 分别保留；V11 hidden更新未运行、V12梯度失败、V13一次更新非整体成功；没有本轮训练增量 |
| V15–V21全空间校正／算子复用 | 加速与收敛分开；GPOLY含随机神经G0，不是纯非神经最佳基线 |
| V22–V23 p1 Galerkin／image-QR | 误差表示98.99%不等于可消残差；V23完整0/6，warm Schur约2.5077e-6、逐通道差约1.69973e-6，zero约0.0681；所有LU／QR费用保留 |
| V24八块local／image组合 | warm与zero都已执行，完整0/5；LZ4约0.081376668、LCZ4约0.325262223；不是仍待运行的计划，不加周期／tau |
| V25–V34残差方向／回流诊断 | 数学负结果与软件／资源停止分开；单步放大不证明GMRES必失败 |
| V35七区PC／zero GMRES256 | Schur0.2052488635>0.01继续门，固定七／八块追加关闭 |
| V36–V38库存、局部积分、全量边界 | V38为q30／MPI1完整32060边界资格；旧q15FAIL、巨型native q60存储停止保留 |
| V39–V40 native接口／体积恢复 | V39失败未倒改；V40完成有限恢复，原尺寸native编号与分布式体积仍缺 |
| 原尺寸冷求解／场功率／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED；仍是最终目标 |

[Review V21](review_report_v21.md)、[Review V32](review_report_v32.md)、[Review V35](review_report_v35.md)、[Review V37](review_report_v37.md)及全部response/raw继续约束。warm-start与zero-trace、表示能力与可消残差、传统预条件器与训练增益不得合并宣传。

dot远端只读核实仍为`077ec9c8386c976da232093779279fb9d1a93033`，材料n差2.991716531811656e-8、缩小notch／532mode、canonical及恢复等缺口未消除。它负责完整体积参考逆、周期分块、共享factor及规模验证；V41只生产目标几何／实体／owner／边界对接协议，不执行其C1/X/XZ/Y、factor、体积性能或solver实验，不读取其旧因子或改ref。若其匹配包到达，只读逐字段验收；缺包不阻止下述自身工作，也不把其他任务的新源当本任务自动授权。

## 5. V41一次连续工作包

### 5.1 固定消费协议，修复小问题并继续

完整读取V40数据、源与本报告。建立新envelope，绑定物理／三种tag、原轴、basis、q、mode、Floquet、源依赖、dtype、index width、slave计算存储／物理展开语义；复用V40不可变数组及V38完整边界。纠正129/120/9计数和工作区口径，闭合§3阶段依赖及class hash门。加入同shape错source／material／phase／owner／class拒绝反例；普通bug定点修复，不因此等待review。

导出实体packet而非全trace字典：实体维数、真实顶点身份／方向、owner、owned/ghost角色、局部moment索引、周期master实体和复系数、basis变换、producer编号与consumer编号分别定义。周期角点必须只有一次规范化master归属，正向用原相位，对偶散布用共轭。完整实体的高阶矩不得拆分归属、遗漏或重复累加。MPI通信只路由被本rank使用的实体，计数／小class表可collective，所有trace逐行allgather禁止进入目标路径。

### 5.2 一次连接的真实p6编号／owner见证

先冻结一个**最多64hex的连接三维fixture**，含内部共享面、x/y周期及角点、air/tag1、substrate/tag2、grating/tag3；几何仍取目标的真实坐标／材料面，不用缩放波长／相位或二维替代。可在原大周期上用少数较宽轴区间覆盖这些材料／边界，此时只授编号资格，不授h≤0.7精度。rank分区必须使周期master和共享实体实际跨rank；记录实测跨rank条目数量，不能只运行MPI但所有映射都在同一rank。

对同一个冻结fixture顺序做真实native MPI1、2、4的mesh／p6 space／MPC与实体导出，**不编译体积或端口form、不装配A、不新LU**。用完整有限见证向量核对实体到实际DOLFINx dofmap的双向映射、周期展开与共轭散布、owned/ghost唯一性、相邻cell的同实体坐标、全向量rank间canonical一致性，比较门1e-10、整数库存必须精确、计算slave严格0；一般复向量种子固定，零和复缩放另查。保存真实映射和完整小向量，独立checker从literal重算，不用合成MPI顶替。

对实际遇到的非零p6方向，至少覆盖边反向及面旋转／反射；若自然编号全为零，可在该同一fixture的合法顶点重编号副本上做一次受控方向见证，先证明几何／材料／实体一一对应。用保存V40 raw882矩阵和原生DOLFINx变换API对照新的实体变换，两轴公式相对门1e-10；只做必要方向的矩阵变换，不构造新kernel／LU。不能把p2代数测试升格为p6真实方向覆盖。未遇到或未验证的方向明确列出，目标出现新方向时停止相关资格提升，保留纯库存。

这是接口检验，不是体积求解实验。沿用V40的非零RHS恢复包作为数值anchor；新分布式编号通过只授`DISTRIBUTED_NATIVE_ENTITY_BRIDGE_QUALIFIED_ON_FIXTURE`，不自动把MPI1恢复包授为MPI4求解器。成功后无需等review，继续5.3。

### 5.3 门通过后一次原尺寸真实几何／拓扑库存

本报告明确放开**原尺寸530856hex的geometry/topology-only构建**，区别于仍禁止的全目标p6 FunctionSpace／完整dofmap／field／A。使用冻结V36/V40目标轴和相同公共几何约定，创建一阶几何hex mesh、真实edge／face拓扑、cell permutation及material tags；不创建任何345771066行对象、不调用旧全局trace字典路径。默认本阶段MPI2、数学线程1；若CPU准入暂缺，等待既定间隔，不擅改多种rank做性能扫描。

先用5.2同一个小mesh取得拓扑阶段对象计数和实际同时峰、构建阶段成本；按目标点／cell／edge／face和MPI临时复制清点保守上界，不能把p6单向量5.53GB误列为本阶段必需，也不能用线性斜率掩盖Python巨型列表。入场要求预测树峰≤6GiB、剩余重阶段有载足够覆盖目标及一次必要修复／验收、存储合规。guard hard8GiB只是后备。可使用预分配／分块输入和数据包避免整个Python tuple网格；不得为通过准入删除真实拓扑或调整目标轴。

流式导出每个owned cell的完整raw宽度／material tag／canonical几何身份／实际orientation、实体owner／ghost、周期配对，按完整key去重；统计各rank实际用户与全局唯一类，给出压缩载荷、工作区和峰，原尺寸530856cell及边／面／边界覆盖必须闭合。raw类别与270项逐键比对；若native几何次序导致key还需细分，保存差异并使用实际key，不凑成270。只存类描述和映射，不生成270份原张量、LU或Schur。这与dot的共享因子实验互补。

将原尺寸上下各2628面、378432边界矩、全部32060 ordered端口身份接到该owner实体协议，完成全部边界实体的提取／对偶散布路由验收。向量只存需要的owner边界条目，可按完整全局实体键生成预登记一般复输入；独立对照V38的canonical边界输入／输出，保留全复向量，不能抽几个通道代替全量覆盖。不重编译native Fourier边界，不新做q30/q60积分／测速曲线；既有边界action只为检验通信与接线执行少量完整调用。散布使用分块临时量及调用者合法owner缓冲，不申请全体积向量。

**编号资格必须准确命名。** 此阶段native mesh实体ID／owner／permutation为实测；按实体前缀构造的p6 moment编号是明确的canonical协议编号，不能称为已经构造的全目标DOLFINx p6 DoF号。有限5.2证明桥的实现，但不能填补不存在的全目标p6编号证据。若体积consumer使用自身等价编号，必须提供其actual绑定表／hash并通过接口门；缺失时给出精确待接字段。目标库存与路由全部过门才分别授`TARGET_NATIVE_TOPOLOGY_INVENTORY_QUALIFIED`、`TARGET_BOUNDARY_OWNER_ROUTING_QUALIFIED`，依旧不是PDE或目标体积引擎资格。

### 5.4 同轮交付可消费包及下一次完整求解的准入差距

用新消费进程加载阶段packet，验证identity、完整实体覆盖、owner唯一、方向及周期链、边界完整输出和对偶散布；缺rank／错owner／错phase／遗漏一面必须拒绝。实现物理映射和计算核心进src，runner保持通用参数化，checker只重算保存数据。不得再增加一套task-numbered求解器，旧入口只作薄调度。

提供真正可调用的owner边界适配器、体积consumer的最小接口描述，以及V40的非零f_i/g／恢复／原native残差anchor。体积调用者须能提供独立trace、内部RHS、非零port RHS、forward／adjoint、原空间恢复和full explicit residual接口；不能以零volume callback授通过。没有匹配体积包时明确consumer未接入，但上述自身包与独立检查仍完成。

容量按实际native类数和各rank使用关系重算：raw／oriented矩阵、LU、恢复、RHS投影、Schur、共享identity、owner／ghost索引、E/EH、通信／IO／解码临时、Krylov／PC及audit生命周期分别列出。列出单份全节点共享、按rank私有两种**条件情景**，不实施新的共享factor试验。不要把raw geometry类、oriented类、约束后局部class混为一种；逐cell约束映射可独立应用不等于每个映射都需一份LU。

在同轮给出完整目标就绪矩阵：物理／离散一致性、全体积算子、可用PC／参考逆、已知收敛资格、恢复、精度／mode截断、完整成本分别由谁负责、哪个精确产物仍缺。已关闭七／八块PC不能充当可用solver。以`172800−T_setup−T_recovery−T_audit−T_IO`列出剩余迭代预算，再对实测或明确unknown的单步成本给出条件K上限，不能填造全目标耗时。这次不只是把UNKNOWN表复制一遍：实际拓扑、类库存、owner路由和构建峰应提供新的准入依据；若未能测到则给出真实拒绝算式与已保存产物。

不自动启动全目标求解或NN训练。下一次是否允许体积action／完整求解，取决于匹配体积引擎和完整数值／资源合同，不能由“接口通过”自动解锁。

### 5.5 失败后的有效替代与停止范围

| 实际遇到的门 | 同轮必须继续的工作／停止范围 |
|---|---|
| 导入、schema、lint、路径、计数、普通MPI接线bug | 自主修复、定点复验并继续同一工作包；可信前置packet复用，不为小问题交回 |
| 非零方向、MPC共轭或owner一致性失败 | 保存完整最小反例，分离basis变换／相位／重复散布／编号错误；修复后重验受影响阶段；未过前不得授目标路由资格 |
| 目标拓扑入场预计超预算／内存 | 不启动会越门的actor；完成有限真实MPI桥、流式结构轴清单和逐对象下界，定位需要改为压缩／邻居通信的对象；结构编号仍derived，不能冒充native全量 |
| 目标actor资源触线 | 停完整自有进程组，保存所有已发布阶段；不更改目标网格续跑，不重开旧账；独立checker、失败机理与容量分析继续 |
| 完整类key碰撞／native raw与270库存不一致 | 保留精确坐标、tag、方向与差异；未确认等价的类不得共享；不四舍五入合并、不用近似矩阵伪装精确共享 |
| 没有匹配dot体积包／没有可靠PC | 自身接口、容量和可消费包继续；完整PDE／收敛仍NOT_QUALIFIED，不擅自重复dot或旧PC实验 |
| 真正总额／ABI／物理身份门不可满足 | 停受影响重阶段，保留未运行原因及费用；完成仍可执行的文档和交付，不把资源停止写成方法失败 |

不得把未过某门等同于整个工作包立即结束。只有真实数值、身份、ABI、资源、硬预算门才能阻止依赖工作；普通bug不作为“等下一review”的理由。负结果和每次修复费用保留。

## 6. 有界授权、验收及交接

V41为新范围，全部旧ledger保持closed。首次接手冻结UTC／monotonic／boot，日历24h、最后1h交付；总有载≤7200s，所有真实native／拓扑／MPI／owner阶段及失败修复合计≤4800s，其中原尺寸拓扑与路由阶段≤2400s；probe累计≤90s，末180s清场。辅助单次≤600s／2GiB。先规划完整依赖链再运行，不让入场时只够构造却没有checker余量。

新局部native仅一个≤64hex fixture，MPI1/2/4及必要一次方向副本／修复累计mesh构建≤512hex；全目标topology-only默认一次，若纯软件错误且有已保存可信checkpoint及完整剩余余量，可从失败阶段继续，最多一次完整重建，所有费用累计。新native PDE装配、volume／Fourier form JIT、LU、QR、Krylov、训练次数均为0；旧4class只读，不新增共享factor性能实验。

数学线程1、无GPU；真实MPI仅上述1/2/4小见证及MPI2原尺寸拓扑，整树warn6GiB／hard8GiB、own swap0，按现场CPU／SMT为每rank分配不冲突的可用核，一次一个heavy actor，低优先级，不干预邻任务。临时CPU不足至少120s后再探，不算数学失败。所有rank使用Task042资格化native activation、complex128／IntType64同ABI、实际库路径及getter；当前task规则优先于泛用WSL入口。

新增存储≤2GiB，含失败、测试fixture、JIT复制、解码／压缩共存及交付，≥256MiB科学证据／交付余量；Task artifacts总≤20GiB、free≥50GiB。本轮不需要新PDE JIT，禁止无意义复制旧196MB编译目录。测试fixture立即复用／经hash核实归档，避免重演pre04累计多个完整副本才触线；成功／失败科学证据不可删除。原尺寸拓扑按紧凑数组、流式hash与原子阶段保存，不把大数组进Git。

验收至少包括：5.1拒绝门与库存纠正、5.2真实native完整小向量MPI1/2/4、5.3实际目标库存／完整边界路由或精确受控停止证据、5.4新进程消费及完整容量表。全目标p6 FunctionSpace、全native向量、A/SH、体积kernel、全局LU/QR/Krylov、训练、旧q60、dot solver／factor仍禁止。Hp=I保持隐式，不建立32060²稠密端口块。小fixture动作不授完整解资格。

最小相关测试→必要组件serial／真实MPI→Task-focused、Ruff、compile、ABI/getter及文档合同，已经通过且依赖未变的昂贵Gate不重跑。报告与checker必须断言实际版本／文件／SHA，防止旧Review V36检查误指V35的问题重现。测试与元数据故障同轮修复，不能触发全仓重测或环境重装。

完成后一次交付response_v41、outcomes／总账、原始run/source、阶段依赖图、实际拓扑／类／owner与coverage记录、可消费包、完整费用、就绪矩阵和依赖分组selective manifest。Git使用`-c gc.auto=0 -c maintenance.auto=false`，不改共享配置、不amend／force／merge。仅提交推送本分支；ledger closed、清除全部自有actor、clean/upstream0/0与远端精确SHA核实后，通过原队列`execution-review-handoff-20261004-v41`交回并停止仓库工作。审阅／执行两个窗口不并行。

原尺寸正式解仍须full explicit true residual≤1e-6、完整场／复振幅差≤1e-4、R/T/A/A_volume差≤1e-5、逐通道功率差≤1e-6、能量／吸收一致性≤1e-5，并有匹配参考及h/p／外部截断资格。以上均未由V40或本报告满足。GitHub精确页Cache miss，视觉NOT_VERIFIED；本地文档检查不等于网页或CI。
