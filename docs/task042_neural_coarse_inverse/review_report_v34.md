# Review V34：接受V36限定组件资格，推进目标p6边界精度与分块容量

## 0. 审阅决定与最终目标

**接受V36的原尺寸库存和`PORT_COMPONENT_QUALIFIED_ON_MICRO`，限于与现有表面离散实现的等价性。不能授予原尺寸求解、未裁剪边界精度或目标峰内存资格。V37不只等待dot的包：在一次连续工作包内完成solver接口身份核查、目标p6边界积分／裁剪审计，以及端口内部按面片分块的容量与作用验证。普通bug同轮修复，完成有意义的组件结果或触发真实Gate后一次交付。**

最终目标仍是50×25nm周期、z=−10..130nm、17×25×120nm规则Si光栅、λ=0.7nm的**完整三维有限元前向计算**，保留非可分三维能力，完整N=1时间≤172800s、任务同时整树／可用专属cgroup峰≤2e12B，并为系统和邻任务留足资源。规则首对象不能退化为二维／2.5D最终解；微型缺口资格也不替代原尺寸资格。

神经网络增益门仍是**20%**：相同正确性下，相对最佳合格非神经路线，完整耗时或同时峰至少下降20%，另一项合规；全部数据、训练、构建、加载、推理、精确校正、恢复、审核和IO计入。V36没有训练，也没有合格完整N=1基线，流式存储收益不属于神经增益。

response_v36已正式回应review_v33，依AGENTS §15新建v34，下一交付response_v37。收到`execution-review-handoff-20261004-v36`后接手；执行窗口停止。本审阅没有新FE／A／SH／LU／QR／solve／训练，没有subagents或重置卡，不改求解源码、dot或master，不merge。报告推送后通过原会话队列交接，审阅窗口停止仓库工作。

## 1. 独立核验与证据边界

| 身份／覆盖 | 本次核实 |
|---|---|
| 交付本地及远端HEAD | `bc2efb6e9013ceeb3e34d4c295a21db8b054c837`，clean、upstream一致；无本Task042 actor。宿主另有Task042extra相邻任务，未干预 |
| canonical／分支／base | `/home/fenics/Projects/NN-Lab`／`task42_neural_coarse_inverse`／`ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 实际inventory／FE source | `19eb5dc9ca4d245612d7ddbf9f1a750387b9c8d4` |
| 最终实现／冻结数组checker | `730e8f3336ddd6f9449b70430a48c77cdc1750e3`；后继bc2为文档交付，不冒充运行source |
| 全仓导航恢复 | 5791 tracked文件逐份hash，识别文本107097501 B，建立标题／定义索引；全部36 response／33 review及任务书纳入历史导航。**并非全仓每行语义审计** |
| 原始证据 | 239份gzip解压内容hash／长度核验；237个现存原路径与所归档版本一致，其余归档快照按原hash保留；16组资源样本逐条求整树RSS／swap及峰，16份准入逐核重算 |
| 历史与源码 | 1158份保护文件逐字不变，含68份旧review／response；汇总完整保留历史后缀。14份增量Python静态编译通过；源码、四阶段结果hash绑定 |
| 本轮审计方式 | Task042 pure activation下标准库读源码、元数据、归档和整数库存；没有重跑保存向量数值checker、真实表面组装或昂贵旧测试 |

证据：[独立核验](outcomes/records/review_v34_independent_checks.json)、[审计脚本](outcomes/records/review_v34_metadata_audit.py.gz)、[全仓索引](outcomes/records/review_v34_repository_index.gz)。索引原文SHA256=`feb78a8b9b35a7972d109fa413e2a69c91097ac4a436067aaac92f3515b36e37`。本次人工读写／索引费用未单独监督，明确unknown，不能补零。

重点检查了provider的缓存／弱引用／字节准入、原surface assembler及两处稀疏化、复数正向和伴随、独立保存数组checker、目标坐标与模式库存、MPI collective、费用／closed状态及V35隔离fixture修复。以下数值为**V36原始实测或本次整数推导**，不是本次又做了新数值实验。

## 2. V36确实推进了什么

端口是边界上不同衍射方向的电磁通道。V36一方面列出了原尺寸需要保留的全部通道，另一方面把边界系数改成分批提供并释放；它减少常驻数据，但要支付反复生成／读取的成本，不解决体积内的全局传播。

| 项目／模型 | 实际值／判定 | 资格边界 |
|---|---:|---|
| 原尺寸完整ordered mode | 32060＝16030top＋16030bottom | 原枚举与独立扩大整数盒／色散核对一致；不是硬填dot数字 |
| 原尺寸材料 | canonical n=`0.999885140474+4.32477054e-6i`，epsilon=n² | nominal0.7／source0.699999988的显式alias保持 |
| 规则实体坐标 | x=16.5..33.5、y=0..25、z=0..120 | seed使用x/y从0开始；不能按旧名称误读成中心坐标 |
| p6/h≤0.7/q15纸面情景 | 73×36×202＝530856 cells | 未建目标体积mesh；不是精度合格生产网格 |
| 原尺寸canonical trace／内部／storage／slave | 105298704／238885200／345771066／1587162 | 本次独立按边、面、单元整数公式复核 |
| 单complex128 FE向量／单稠密port表 | 5532337056／16445497600 B | 数组载荷，不是峰RSS；单port表本身未超过2TB |
| 真实组件 | 384hex／p3／q15、34050 storage、18144 trace、40mode | 仅既有micro的表面FE，未解体积方程 |
| 两seed完整forward／振幅／modal RHS差 | 0／0／0 | 相对≤1e-10门通过 |
| adjoint／linearity最大差 | 1.0888902683e-16／2.2031476003e-16 | 复数作用正确，不假设D=Cᴴ |
| 独立单位通道功率最大绝对差 | 2.8421709430e-14 | ≤1e-10；随机边界向量不是物理解，无official R/T/A |
| cache／lease峰、live对象 | 82960B／82960B、最多2 | 440次加载、438次淘汰；creator工作区和resident对照另计 |

V36还纠正了历史notch名称带来的坐标歧义：`x>0, abs(y)<period_y/4, 40≤z<80`在当前非中心坐标中实际选择光栅x全宽、y=0..6.25的一段，不能解释为中心半块缺口。它单独作为能力见证，未偷换规则主对象。该发现应保留，未来不能再按名称猜几何。

19个定点测试和MPI2／4完整向量记录通过；MPI为含空owner的小合成fixture，**真实FE组件本身是MPI1**，不扩大成目标MPI FE资格。最终730e只将逐次加载元数据改成每mode累计并增加不可变hash检查；实际数值作用未改，冻结数组复验支持不重跑FE。V35闭账／数值负结果两道guard已改成独立临时fixture；跨启动续跑没有被虚假授予资格。

证据：[response_v36](response_v36.md)、[完整结果](outcomes/original_size_port_preparation_v36.md)、[run index](outcomes/records/run_index_v36.json)、[独立checker](outcomes/records/component_checker_v36.json)。

## 3. 费用核算及需要收紧的能力声明

| 费用 | 核验值 | 含义 |
|---|---:|---|
| 16次监督＋探针＋bootstrap | 154.628100644＋20.818985255＋0.326941663＝175.774027562s | 包含失败／MPI／收口辅助，≤1800s；未监督实现／元数据时间unknown |
| INVENTORY／COMPONENT／CHECK／DEPLOY | 24.481769902／11.306872300／4.744587441／4.714764241s | 不因名字“preparation”漏掉实际运行费用 |
| 全批／FE组件同时树采样峰 | 603471872／352448512 B | 0.5s采样；无连续内核硬峰证明；own swap0 |
| 新apply5次／adjoint2次／recover2次／modal RHS2次 | 0.783487614／0.352583230／0.262895052／0.264056207s | inclusive；generation1.391014592s、hash0.067271366s已经嵌套 |
| resident表载荷 | 1187408B | 在对照actor中与新实现共驻留，不能用该actor峰计算独立旧／新节省率 |
| 原resident forward总时钟 | 0.002036733s | 调用集合与新apply5次不同，不能拿两个总数直接除成每步加速比 |
| 新数据／历史artifact | 216605035／14946636002B | 分别未越512MiB／20GiB；历史失败和原raw保持 |

新provider明显付出了重算开销，V36没有隐瞒这一点。本轮是容量组件准备，不是收敛改善、完整加速或NN收益。[资源账](outcomes/records/resource_costs_v36.json)、[最终状态](outcomes/records/final_state_v36.json)与原始样本一致，接受closed清场。

仍有三项具体问题，应在V37内解决，不另开小修复轮：

1. **原尺寸单mode支撑上界尚未接线资格化。** `capacity_plan`给出的9082376B取理想canonical切向边／面支撑。实际micro `SurfacePortSource`为防漏项使用“边界cell数×完整native单元维数”的保守上界。若原样移到73×36表面、p6维数882，按同一规则得到`48*73*36*882+8=111259016 B`，大于67108864B缓存门。它是**保守声明上界，不是测得实际非零数或证明9.08MB必错**；现有接口会在分配前拒绝。目标部署需要证明更紧的完整支撑，或把一个mode再按surface行／面片分块。不能一边使用保守creator，一边只给理想支撑作为运行上界。
2. **V36证明的是同一旧裁剪路径的等价。** `_ReusableSurfaceComponentAssembler.assemble_entries`调用`_vec_nonzero_owned_entries`，后续`_combine_owned_entries`又裁剪一次；二者阈值均为`max(1e-30,1e-13*global_max)`。新旧都经过这两道操作，所以forward差0不独立证明相对未裁剪表面积分的误差，也没有验证p6/h0.7/q15。V36 micro组件资格保持，增加明确`LEGACY_CLIPPED_SURFACE_EQUIVALENCE`边界；原尺寸仍不能宣称原始全端口精度合格。dot以前的低振幅通道问题同样说明“mode数齐全”与“泛函没有被删空”是两件事。
3. **P2，normalization未完全绑定到provider不可变receipt。** `_load`只要求`normalization_h>0`；`content_hash`和重复加载不变性只包含四个数组，没有绑定H。若loader在相同mode/数组下变更H，通用provider本身不会拒绝，作用却变化。真实V36 source从mode identity取H，独立checker还从k/E/参考面重算H，所以不推翻本次实测；但下一步需要将H／source／有序身份绑定，测试“数组相同、H被改”的拒绝以及cache hit／reload／invalidate路径。不要依赖事后checker替代执行入口的不变性。

上述不是把测试合格改成整体失败，而是明确剩余的**目标级**障碍；既有micro结果与新目标资格分开记账。

## 4. 历史去重与dot最新事实

早期完整路线表沿用[Review V21](review_report_v21.md)、[Review V32 §3](review_report_v32.md)、[Review V33 §4](review_report_v33.md)，本轮1158份保护文件hash延续历史，不把旧状态当本轮新实验。

| 路线 | 当前状态／不可重复事项 |
|---|---|
| p4严格神经粗逆V1–V5 | 已关闭；不能改名回迁 |
| 神经FE trace、固定特征、hidden更新V6–V15 | 真实训练／未训练／未运行分开；低loss或固定线性头不等于神经收益 |
| 全空间校正、ILU、class64、GCROT | 残差改善与算子降时分别存在；没有原尺寸完整资格 |
| p1 Galerkin／image-QR V22–V23 | 误差表示覆盖不等于可消除残差；V23完整0/6，warm Schur≈2.5077e-6且逐通道超限，zero≈0.0681；旧LU／global QR真实费用保留 |
| V24局部及image组合 | 已运行，完整0/5；warm/zero不能混评；不追加同空间／scalar-tau／旧预算 |
| V25–V34有限方向与回流 | 精确LS上限及实际单步放大均已有答案；资源／软件轮不算多次物理失败 |
| V35任意RHS七区PC＋冷GMRES | 首256步Schur0.205248864>0.01，固定7/8块族停止追加 |
| V36端口库存与惰性供应 | 新增真实组件资格；目标p6表面积分／单mode支撑／完整全局求解仍未测 |

本次只读ls-remote发现dot已从5be1210推进到**`077ec9c8386c976da232093779279fb9d1a93033`**。只获取Git对象供`git show`审查，没有更新dot分支ref或工作树。该增量是执行环境丢失后的native tensor源码恢复，明确`C1a/C1b/C1c/C2/target_not_qualified`；旧C1a两次失败的科学raw目前UNAVAILABLE，78／2测试仅历史声明，不能借恢复source重新授予PASS。

原Y仍是不同身份的p4／120cells／532手动通道、6q／3twists；后续p6源码恢复也不是可直接消费的原尺寸solver包。[本次保存的dot恢复收据](outcomes/records/review_v34_dot_recovery_receipt.json)是只读引用，不替dot审阅或重做实验。**不接受将V37全部工作写成“等dot匹配包”。** dot继续负责完整3D参考逆、周期分块、因子／共享存储和规模验证；Task042聚焦完整边界供应、精度／容量与可验证接口，不重跑其C1、X/XZ/Y或另写周期求解器。

## 5. V37唯一连续工作包

### 5.1 先做身份与源码边界核查，随后自主推进边界工作

只读核对dot精确最新发布SHA、source/runtime锁、科学raw可取得性和已资格字段。输出可机器读取的consumer验收器：按几何／材料／λ／入射／背景／完整mode／参考面／复Floquet／p／canonical row／内部恢复逐字段比对，区别真正物理差异、坐标平移／相位换算、不同schema命名和未提供证据。不能直接比较两个不同序列化schema的“physical hash”就断言不同物理；也不能将约3e-8的材料差静默忽略为相同算子。

若没有匹配全局solver，记录`SOLVER_PACKAGE_NOT_QUALIFIED`并**继续5.2–5.4**；本轮不移植／执行其solver、不消费缺失factor、不重建其云端环境。当前V36输入和32060 mode库存直接复用，不重复整套INVENTORY、micro40mode actor或存储probe。修复§3的H不变性，原V36证据和closed账本不改。

### 5.2 目标p6表面积分：从小而真实的面片回答精度问题

三维FE边界系数来自每个外表面的面片积分；可先在真实目标尺寸的少量面片上核查其局部计算，再把贡献逐块累加。**这只是边界积分的分块，不将Maxwell体积方程降维或改成二维解。** 它能区分积分不准、裁剪小系数和provider接线错误，避免再次用两个相同裁剪实现互证。

冻结V36 p6/h≤0.7容量情景、真实轴值、0.7 canonical材料及32060 ordered mode。新的目标面片组件使用实际p6 N1curl native basis、方向变换、Piola映射及真实物理坐标；保留全单元basis在面的作用，包括数值上的微小系数。以已有Basix/DOLFINx面组装和未稀疏化向量为独立对照，不新建530856cell体积mesh，不生成完整目标DoF图，不读dot volume tensor。

运行前用元数据确定一个固定见证集合，不按结果挑有利通道：

- 每侧／每极化取零级、最大横向波数绝对值的x/y两个方向及最小非零纵向波数的传播通道；并纳入非零n与两个横向分量均非零的代表。去重后**最多24个mode**，固定tie-break为原ordered index最小者。清单由32060真实库存产生，不能换成虚构通道。
- 从实际target axes确定最小／最大面尺寸组合及普通、周期缝、周期角点的所有权情形。**最多4类面片配置**；同一类可包含完成共享边／周期配对所需的少量相邻或平移面片，总native hex见证≤32个。记录真实全局坐标、参考面和正确周期50／25nm，不能把面片宽度当新的周期。
- q使用**15→30→60**这一组预登记比较。先保存q15/q30，若不合格直接计算q60并完成判别，不因普通数值门失败停下来等review；不得继续q120扫描。q60是本轮更高阶离散对照，不自动称精确积分。zero／near-zero按抵消前operand尺度及绝对分子单列。

q表示求积规则的多项式精确度，并非采样点数；含Fourier指数的积分不能仅因q大于某个多项式阶数就称精确。记录本地规则实际点数与权重，沿用已资格化软件版本，不按在线开发版升级。[Basix求积接口定义](https://docs.fenicsproject.org/basix/main/python/_autosummary/basix.quadrature.html)说明了degree的含义。

两个独立问题分别输出：①同q下按需／分块对未裁剪native积分的作用与伴随差；②q15／q30／q60的积分差。另保存两处旧阈值各自删除的系数数、幅度、范数、最差mode/row及旧裁剪结果对未裁剪结果的差，包含曾被删空的情况。旧阈值作为对照，不把它当“精确为零”的数学证明。

对非零完整局部泛函／作用，固定相对门`norm(a-b)/max(norm(a),norm(b))≤1e-10`；全零单独精确检查，强抵消另报operand尺度，不用后者覆盖前者失败。复伴随／线性operation≤1e-10。旧裁剪删除量如超过门，明确`LEGACY_CLIPPING_NOT_QUALIFIED_FOR_TARGET_WITNESS`；新的opt-in路径必须保留未裁剪贡献或给出另行可验证的误差界，不改ordinary default和旧算子身份。

q15对q30未过、q30对q60过时，结论是“q15未获本见证资格、q30在本见证与q60一致”；采用q30继续本轮的分块组件。若q30对q60仍超门，停止精度升级，保留三组数据并继续容量／接口分析，不选有利mode删除。**有限见证没有覆盖全部mode和所有面片，不能称目标边界积分全量资格或continuum convergence。**

### 5.3 实现一个mode内部的面片／行分块，解除全支撑分配前提

当前provider跨mode分批，但单mode仍要求完整支撑放得下。新接口在一个mode内再分块，先把所有面片对投影的贡献累加成该mode的一个复数，再完成MPI归约；取得振幅后重放相同面片，累加牵引贡献。这样不需要同时保存整张单mode支撑表，代价是第二次遍历／重算或已计费的小缓存。伴随按独立C/D的共轭定义实施，不能猜C=Dᴴ。

- 核心进入通用src；复用V36的mode身份、上层批次和consumer，避免再复制一套Task-numbered求解器。面片遍历、共享entity去重／相加、periodic slave向master的复相位及归约顺序有明确合同。
- 数值缓存仍≤64MiB，最多64mode；face tile再设独立字节上界并在分配前检查。小见证强制多tile，证明跨tile共享rows不会被覆盖或重复乘相位；空owner必须走相同collective。O(Nport)的metadata／输出与O(tile)数值缓存分开，不积累全部mode×全表面系数。
- **不能先用旧assembler创建完整345771066维目标FE向量再切片，声称实现了目标有界creator。** 小native见证可以用完整小向量作为oracle；目标provider的生成必须来自有界面片数据／reader，并逐项报告tabulation、orientation、map、临时副本、两次遍历、归约、IO与完整输出的生命周期。
- 逐mode绑定H、ordered identity、source和tile内容；同数组H改变、乱序、丢面片、重复face、坏相位、transpose/conjugate错误及坏hash都要有拒绝或明确数值失败。不能要求只有正例能跑。
- 若能证明完整原支撑的更紧安全上界，从而无需实际tile，也必须交付这个证明的依赖／适用条件并通过相同native反例；不能把9.08MB当无条件证明。仍保留单mode越界拒绝和面片接口，不提高64MiB来规避问题。

在5.2同一组真实p6面片上完成新分块对未裁剪native作用／伴随、所有选中复端口和单位功率验证。数值相对／operation门同上，单位通道功率最大绝对差≤1e-10。端口H／参考面相位另从k、E和面积重算，不只比较两个复用同函数的输出。MPI2／4先用小fixture验证完整向量、共享rows、空rank和全体拒绝；若新FE分布逻辑未有真实MPI证据，明确该资格仍限MPI1。

### 5.4 完成目标级资源排除式与可消费包，而非停在测试

无论5.2／5.3正负，都完成以下输出：

1. 更新目标容量表，明确理想trace支撑、当前保守creator、实际tile上界和未测真实全量support；给出端口缓存、FE向量、Krylov（V36条件GMRES256组约434.67GB）、内部恢复、全局solver／局部因子、MPI／IO的共存阶段。原尺寸实际峰仍unknown，不相加成伪上界。
2. 保存每面片／mode／双遍历的实测阶段费用、native oracle费用与JIT；不把它线性外推为48h承诺。以完整32060库存和已知面片数给出计算量公式，区分已测单价、复用假设、通信与迭代数unknown，指出未来哪个实测校准最能决定可行性。不要重跑micro resident速度竞赛或调batch超参。
3. 交付能被全局solver消费的只读contract／provider／验收入口和精确source/hash；缺solver时仍能运行资格检查并给出缺失字段，禁止自动启动完整target solve。默认继续`TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED`。
4. 失败替代：若积分门失败，归因是q／方向／相位／裁剪哪项，不转向NN补误差；若tile数据生命周期失败，修软件直到预算门或明确不可行对象；若组件正确但重算太贵，保留精确边界张量／重复几何复用的接口分析，后续优先消费dot已有结构，不本轮再开FFT／低秩／网络三条路线。

本轮不解目标PDE，不授权新的全局逆、体积A/SH、大LU、QR、旧7/8块、同p1空间变体或训练。通过最多称`TARGET_P6_BOUNDARY_WITNESS_QUALIFIED`并注明面片／mode覆盖；不改V36历史classification，不称所有32060通道的全FE作用已运行。

## 6. 预算、停止条件与交付

使用全新V37账本，V24–V36永久closed。继承native activation／complex128／IntType记录／真实BLAS getter／CPU及SMT准入、shared-workstation隔离；数学线程1、无GPU、不修改邻任务，重型actor一次一个。新源码／ABI Gate不通过不得运行FE；普通导入、schema、fixture、hash、MPI接线等bug在同轮剩余预算内修复，不另请review。

| 界限 | V37合同 |
|---|---|
| 日历窗口 | 首次检查登记起24h，末1h只清场／证据／交付；不随提交刷新 |
| 全部新增有载wall | ≤3600s，含JIT、组件、失败修复重跑、测试、checker和探针；末120s预留清场 |
| 真实p6面片及分块组件 | 累计≤2400s；warn6GiB／hard8GiB，own swap0 |
| 辅助fixture／checker | 单次≤600s、2GiB，与上项共享3600s总账；先尺寸预检，不把正常JIT用任意短外层timeout杀掉 |
| 探针 | 累计≤60s，暂时CPU拒绝WAIT至少120s再探；只重试准入，不重复已完成actor |
| 规模边界 | ≤24mode、≤4类真实面片配置、≤32 native hex见证；完整32060 metadata复用，禁止目标体积mesh／完整FE编号 |
| 新存储 | ≤512MiB；Task042 artifacts总20GiB、磁盘自由≥50GiB保持。原raw无损归档和hash完整后可回收重复副本 |

真实数值门不是bug：q30／60不一致、未裁剪／分块作用超门、错误MPC／H、单对象超字节门等都保存实际分子／分母、最差mode／entity并停止受影响的扩大步骤，按5.4完成替代分析。普通软件失败、一次CPU拒绝、source静态检查不通过或只有schema完成都不能作为提前等待审阅的理由。到总预算／日历／ABI或实际资源门时保存状态并清场，不重置账本绕过。

一次交付`response_v37`、outcomes／原始证据索引／失败与费用／项目总账、部署缺口和依赖分组manifest；只在原执行分支提交推送。报告精确base／运行source／checker source／最终HEAD，工作树clean和upstream 0/0。全部自有actor清除、ledger closed后通过既有队列交回审阅，执行窗口停止；不动其他branch、不amend／force、不merge master。

当前原尺寸完整方程、全部场／逐通道功率、生产h/p/q／外部截断精度、2TB／48h和NN20%均未资格化。**本报告不授予merge approval。** 本次本地文档检查见[验收记录](outcomes/records/review_v34_documentation_checks.json)；GitHub视觉未验证，不称CI通过。
