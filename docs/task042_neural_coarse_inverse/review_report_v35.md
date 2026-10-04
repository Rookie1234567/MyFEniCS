# Review V35：接受V37有限边界结果，推进原尺寸完整表面的可用计算核

## 0. 决定与最终目标

**V37提供了可信的普通面片组件结果和新的积分负结果；最终目标尚未达成。接受`P6_TILE_INTERFACE_QUALIFIED_ON_PARTIAL_WITNESS`，不授予完整目标边界或PDE资格。下一轮V38不以重启巨大的q60 JIT为唯一任务，而是一次完成周期见证、同一离散积分的结构复用、条件的原尺寸完整边界作用与消费包。普通bug同轮修复，经过真实数值／容量门再决定扩大，最后集中交付。**

最终对象仍为50×25nm周期、z=−10..130nm、17×25×120nm规则Si光栅、λ=0.7nm的完整三维Nédélec有限元前向计算；保留非可分三维能力。完整N=1耗时≤172800s，同时任务整树／可用专属cgroup峰≤2e12B，并保留系统及邻任务余量。规则光栅是原尺寸首对象，不能把边界降维计算、二维／2.5D结果或微型缺口解当最终三维解。

神经增益门为**20%**：在正确性相同的条件下，相对最佳合格非神经路线，完整耗时或同时峰内存至少改善20%，另一项合规；计入数据、训练、构建、加载、推理、精确校正、恢复、审核和IO。本轮没有训练，也没有合格完整N=1基线；边界分块或张量计算即使更快也属于非神经改进。

本报告回应`execution-review-handoff-20261004-v37`。response_v37已正式回应review_v34，按AGENTS §15新建v35，下一交付response_v38；不修改已回应的旧review。审阅期间执行窗口停止；本审阅只读源码／元数据／原始字节并写审阅材料，未启动新数值、改求解源码、使用subagents或重置卡，未修改dot／其他分支／master。推送并完成核验后通过同一会话队列交回，审阅窗口停止仓库工作。

## 1. 独立核验与身份

| 项目 | 本次核实与边界 |
|---|---|
| 交付本地／远端HEAD | `011718d84606cc052085c200d2ce767030f21e38`；canonical `/home/fenics/Projects/NN-Lab`，唯一分支`task42_neural_coarse_inverse`，开始时clean、upstream 0/0，无本任务数值／编译actor |
| base／上一审阅 | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`02fe5f860562f6a7ef689f9d53b061cfaf30a43b` |
| native q15/q30实际source | `ce18a6056731780d1feb4f47c96dfcc4f52aa6d1` |
| CAPACITY／CHECK实际source | `bd7d7e2bc8167973ee1156deb0e8a23607a37db6` |
| 最终实现／DEPLOY实际source | `d7ec9180af1b45f55bd37b49a6f0ac450920589e`；最终文档HEAD不是运行source |
| 全仓导航恢复 | 6195 tracked文件逐份hash，107697971 B文本建立标题／定义索引，包含37份response、34份review及任务书；**不等于全仓逐行语义审计** |
| 历史保护 | 1424份旧保护材料逐字不变，含70份旧review／response；四个汇总导航保留完整旧后缀 |
| 原始证据 | 361份gzip的压缩／解压hash及长度核对；360个现存原路径匹配归档版本，无现存内容不匹配；5个NPZ及227个成员核对字节hash、shape和dtype，未重跑向量运算 |
| 资源／费用 | 20份监督逐样本重算整树RSS／swap／峰及清场；20份准入从CPU tick、线程及SMT拓扑重算；closed账本核实 |
| JIT失败保留 | 34份归档逐块解压核对原hash／长度，共1559383311B原生成文件、254668906B压缩文件；未重新编译或恢复运行 |
| 静态与测试证据 | 14份增量Python静态compile通过；读取原JUnit的28例1失败→28例通过→最终31例通过及MPI2/4记录，未把本次审阅称为新FE测试 |

证据：[本轮独立核验](outcomes/records/review_v35_independent_checks.json)、[审计脚本](outcomes/records/review_v35_metadata_audit.py.gz)、[全仓索引](outcomes/records/review_v35_repository_index.gz)。索引原文SHA256为`24660faf35d18627ba6b86caa40d292c370b7a59f4c3bb72ea84a1534402e78b`。重点逐段检查了真实面片构造、Basix积分／方向／Piola、原MPC组装、分块正向／伴随、H不变性、独立checker、MPI及存储监督。审阅人工工作和一般读写未单独监督，费用unknown，不补零。

## 2. V37哪些结论成立

端口把边界上的有限元场转换成各个衍射方向的振幅，再将边界牵引返回有限元方程。V37把一个方向的系数拆成多个面片，减少单次存储；它没有求解体积内部的传播，也没有改善迭代收敛的证据。

| 真实模型／项目 | V37 measured结果 | 审阅判定 |
|---|---:|---|
| 原尺寸库存／有限见证 | 32060 ordered mode；预登记12mode、四类20hex；实际唯一4hex普通面片，失败重建累计16hex | 12mode和普通面片的资格，不能当全库存已运行 |
| q15与q30完整泛函最大相对差 | 1.3259472061511423e-5，门1e-10 | **q15未获本目标见证资格**；最差bottom `(m,n)=(0,0),s`、原index32058，分子2.7718637525461538e-5／分母2.09047821790138 |
| q30 native与q60 Basix | 4.692431704831983e-13 | 对该普通面片支持q30；不是native q60通过或全部目标通道精度证明 |
| 同q30 Basix／native | 4.689163825724463e-13 | 有限组未裁剪映射一致 |
| 分块forward／adjoint／完整选中复振幅 | 2.79307870108e-13／2.61645760695e-13／1.59542409236e-13 | 同一未裁剪native离散作用的组件资格 |
| 复线性／dual operation／H／单位通道功率最大差 | 4.58310e-16／2.45695e-18／0／7.10542735760e-15 | 均过1e-10；单位模态功率不是PDE求解后的R/T/A |
| 旧两道裁剪q30 | 删除14928、112个分量；C/D最大差约1.9269e-13 | 本组选中通道未超门、未删空；不能证明32060通道安全 |
| native q60、max普通、周期缝／角点 | NOT_RUN_STORAGE_GATE | 保留缺项；部分成功不能授予`TARGET_P6_BOUNDARY_WITNESS_QUALIFIED` |
| 真实FE／MPI | MPI1真实p6；MPI2/4合成共享row和空owner | 不称目标FE MPI资格 |
| 原方程残差、E/H/curl、R00_s/p/total、R/T/A、A_volume | NOT_RUN | 无official场／功率，无2TB／48h或NN20%资格 |

canonical材料仍为n=`0.999885140474+4.32477054e-6i`、epsilon=n²；nominal0.7与source0.699999988显式alias不变。坐标是x=0..50、y=0..25；Si在x=16.5..33.5、y=0..25、z=0..120。旧微型notch选择器的实际几何解释沿用Review V34，不凭名称重解释。p6/h≤0.7的530856cell／105298704 canonical trace／345771066 full storage仍是容量情景，未建立该体积mesh。**此次边界q15负结果不能被忽略，也不自动证明体积q30合格。**

来源：[response_v37](response_v37.md)、[详细结果](outcomes/target_p6_boundary_tiles_v37.md)、[原始checker](outcomes/records/component_checker_v37.json)、[模式与实际分子分母](outcomes/records/gate_decisions_v37.json)。本次重算125项已存标量比值／判定并核对底层数组身份，没有重新执行该数值实验。

## 3. 成本与必须随推进修复的问题

| 口径 | 核实值 | 含义 |
|---|---:|---|
| 全部监督＋探针＋bootstrap保守收费 | 446.204937213＋25.657178592＋3＝474.862115805s | 含失败、测试、JIT、归档和checker；不是完整成功N=1 |
| PATCH＋CAPACITY累计 | 269.670777797s | 最长失败PATCH236.722477617s，CAPACITY8.110290449s |
| 同时整树采样峰／own swap | 3387654144B／0 | 0.5s样本，非连续cgroup硬峰；不将不同阶段峰相加 |
| 分块作用集合／creator／hash | 1.810418537／1.628519290／0.041459786s | 后两项包含于前者；192次tile loads、96passes、5visits，不重复计时 |
| tile／保守整mode支撑 | 42336B／111259016B | 前者有限见证载荷；后者旧creator上界超过64MiB；9.08MB只是另有假设的理想支撑 |
| 最终新增存储／Task042 artifacts | 477669342／14963754484B | 最终门内不能抹去曾经越512MiB |
| 条件全FE输入＋输出／GMRES256向量组 | 11064674112／434673050112B | 数组载荷；未包含完整solver／内部恢复／MPI等共存峰，后者仍unknown |

历史formal下界77349.71922726494s不重置；最终费用表中的77821.58134307021s仅增加监督和探针，不含本轮bootstrap保守收费3s。完整历史与未监督实现／元数据仍有unknown，不能作为完整N=1或神经加速分母。共享工作站缺少可比隔离数据，性能干扰仍INCONCLUSIVE。费用见[resource_costs_v37](outcomes/records/resource_costs_v37.json)。

**P1，完整checker未来可能把缺项误报为通过。** `benchmarks/check_boundary_witness.py:60–153`只核patch数量／上限，未逐项强制预登记patch身份、q集合和每个action witness；缺q60或缺actions时可能让`all([])`为真，并直接复制上游`result['status']`。V37实际走`check_partial`，其明确保留NOT_RUN且重算H／power，已完成结果不因此作废。V38必须先修成按预登记覆盖矩阵逐项验收、缺失拒绝、独立重建分类；不能只补一条status断言。加缺整组q、缺action、重复patch替代另一patch和错误身份反例，同轮继续数值工作。

**P2，元数据复杂度与声明不符。** `src/solvers/tiled_port_action.py:59–83,98–112`将每mode的完整`tile_ids`序列化、保存为tuple并在每pass重验。按一面一个tile直接推广，32060×2628＝84253680个plan引用，单份8B引用就约674MB，还不含tuple、JSON字节和重复字符串。因此`capacity_lifecycle_v37.json`的“O(Nport) metadata”不足以描述该完整接口。V38改为共享有序面片表＋按side／几何类的范围／摘要，mode只绑定该表身份；任何新增moment表、reader索引、数组与Python对象也分别计费。

**P2，MPI异常合同尚不完整。** 当前仅字节预拒绝用了collective；identity检查在其之前，load/hash/row异常又可在其之后单rank抛出。另一rank可能进入下一次归约。V37只证明合成容量共同拒绝，不能外推为任意输入错误均可安全返回。V38在实际增加的分布式边界上实行共同阶段检查／失败传播，并用单rank坏H或坏hash负例验证有界退出；不用无界挂起代替失败。若仍仅真实MPI1，资格明确保持MPI1。

**存储监督缺口已被如实承认，但修复资格有限。** V37的live guard和回归验证了分支逻辑，尚未证明真实大JIT不会在0.5s间隔内明显越界。下一轮必须在分配／编译前预算C、o、so及临时副本共存；采样是后备停止，不是分配许可证。不得在同一路径重复生成四套约359.8MB的q60 form再等待采样终止。原始科学数组和失败归档保持只读。

## 4. 历史去重及与dot的分工

| 路线 | 已有答案／当前决定 |
|---|---|
| V1–V5 p4严格神经粗逆 | 小例严格逆未资格，已关闭；不改名回跑 |
| V6–V14 神经FE trace、固定hidden／线性头、hidden更新 | 真实训练与固定特征分开；V11更新未运行、V12梯度失败、V13一次接受并非完整解；低loss不是神经收益 |
| V15–V21 全空间校正／ILU0／class64／GCROT | 表示、真正残差改善和作用降时分别评价；GPOLY含随机神经G0，不能称纯非神经最佳完整基线 |
| V22–V23 p1 Galerkin／image-QR | 98.99%误差表示不等于能消除残差；V23完整0/6，warm Schur约2.5077e-6、逐通道功率差约1.69973e-6，zero约0.0681；LU／全局QR成本保留 |
| V24局部八块及image组合 | warm／zero已运行，完整0/5；原V24不再是“未发布计划”；不加第五周期、scalar-tau或同p1换测试 |
| V25–V34固定方向／回流诊断 | 精确LS可移除残差有限；Bfull单步放大不等于GMRES必失败；软件／资源轮不重复计为物理失败 |
| V35任意RHS七区PC＋冷GMRES256 | 实测Schur0.2052488635>0.01继续门；固定7/8块族停止追加 |
| V36原尺寸库存／lazy provider | 32060库存与micro旧裁剪算子等价；未解决单mode容量与重算时间 |
| V37未裁剪p6普通面片／tile | 新积分负结果和有限组件正结果；周期、全表面、完整solver未资格；下一步解决边界重复计算 |

详表与旧费用保留于[Review V21](review_report_v21.md)、[Review V32](review_report_v32.md)、[Review V33](review_report_v33.md)、[Review V34](review_report_v34.md)，本次用旧文件字节一致性延续历史，不将旧结论包装为新实验。

dot远端仍为`077ec9c8386c976da232093779279fb9d1a93033`，与V37只读验收一致。其恢复source明确未恢复合格runtime和C1科学raw；p6/80cells/532mode组件、缩小的notch几何与本任务目标不同，材料n差2.991716531811656e-8真实存在。mode、Floquet、canonical row和恢复证据仍缺，不能因同为0.7nm／p6而消费为同一求解器。见[语义consumer验收](outcomes/records/consumer_v37.json)。不因序列化hash不同就判物理不同，也不忽略真实差异。

dot继续负责体积参考逆、周期分块求解、共享存储和规模验证。本任务推进**真实三维FE的边界数据供应和作用**；不执行其C1/X/XZ/Y、移植其逆、调用其factor或修改其ref。缺少dot新包不成为V38停止自身工作的理由。

## 5. V38唯一连续工作包：正确的边界积分加上可承担的全表面作用

### 5.1 为什么改变下一步重点

现路径按每mode、每面片重新算积分、方向和行映射。目标一次双遍历有`2×32060×2628＝168507360`次面片访问。**若机械沿用本次每tile creator均价0.0084818713s**，仅creator条件乘积约1429258s，是48h预算约8.27倍；这是暴露复杂度的敏感性算式，**不是目标实测或可靠预测**，也没有计全局solver。仅补native q60不会改变这项成本。

原尺寸外表面是规则矩形，有限元基函数和Fourier相位有可利用的分方向结构。下一步把相同的参考积分计算一次，再按真实单元尺寸、方向、周期约束和位置相位组合；进一步按x、y两个方向作矩阵收缩，避免逐通道重访全部面片的Python循环。**只重排同一边界离散运算，不减少mode、不学习系数、不把体积Maxwell方程变成二维。** 代价是明确native基与张量布局之间的映射、额外小表及全边界reader，必须逐项资格化。

本轮只选这一条“同一求积规则的可分边界计算”路线。优先复用本地Basix的公开基函数／系数／张量表示，保留完整native N1curl、方向和Piola；接口是否支持须查本地实际版本，不能按开发版文档升级环境。[Basix接口说明](https://docs.fenicsproject.org/basix/main/python/_autosummary/basix.finite_element.html)区分了native DoF变换和张量表示／排列，不能假定两者编号相同。这里的“等价”是同q离散代数等价，不是解析积分精确或连续解收敛。

### 5.2 先建立可信桥接，并补齐周期覆盖

复用V37冻结的32060库存、12mode和四类面片清单；旧q15/q30普通面片数组不重新生成。修复§3 checker、共享plan和实际用到的异常合同，不将这些软件修复单独交付为本轮成果。冻结本轮实现／基／求积规则／mode／面片／布局hash后进入新账本。

对新增的max普通、x周期缝、xy角点做**q30未裁剪DOLFINx/MPC原生面组装**与新计算核的同q比较；普通面片复用原数组。对四类都做独立的q60 Basix二维求积对照，必须保持与新分方向收缩不同的求值路径。保存全882基的面贡献、literal cell permutation、完整方向变换、Piola、global坐标、原50／25nm周期、slave到master的共轭和corner链；不得裁剪微小系数来制造一致。

**本报告明确覆盖上一轮“必须native q60才可补齐”的下一建议：V38不再生成原巨型q60 UFL C/o/so。** native q30负责原生装配／MPC接口锚定，独立二维Basix q60负责更高阶对照，新分方向实现负责效率；三者职责和依赖分别记录。原native q60始终保留NOT_RUN_STORAGE_GATE，不回填成成功，不复用V37原完整资格标签。若三者共享基函数定义，应如实说明该共同依赖，不能称三套完全独立物理求解器。

门限保持：非零完整泛函／作用`norm(a-b)/max(norm(a),norm(b))≤1e-10`，全零另验精确零；伴随／线性operation≤1e-10；H相对及单位通道功率最大绝对差≤1e-10。另报抵消前尺度、最差mode／实体／row，不能用放大分母覆盖失败。q30/q60失败则不升级q120，也不选有利通道删除；保留真实差异并进入5.5。可定位的方向／映射／接线bug按同一数学合同修复、targeted重验，不立即等待review。

### 5.3 实现可被体积solver消费的完整边界布局与计算核

核心放入通用src；复用当前runner、监督、mode与consumer，不再复制task-numbered求解器。以side／几何实体／方向矩为边界身份，独立建立**仅上下边界**的紧凑布局，报告其与native小面片行的双射。不得虚构全目标DOLFINx canonical行号，不创建530856cell体积mesh或完整345771066维向量来取得编号。完整体积solver以后提供显式row adapter，并经native抽取／散布验收后才接入。

冻结一个同q30的分方向计算核：相位平移与局部尺寸分开，C与D独立，s/p可共享相同波数的参考积分而各自保留E、traction和H；每侧mode有序输出不变。缓存key必须含完整基／quadrature／尺寸／方向／source身份，不能用有损坐标舍入把不同单元误合并。结构性零须有数学布局依据和未裁剪native差异证据，不能将旧1e-13裁剪作为证明。禁止全mode×全表面稠密C/D、全局QR、低秩截断、FFT替代扫描或神经拟合；有界局部基变换不属于新全局逆。

所有数值缓存／moment表合计≤64MiB，mode处理块≤64；临时工作区另作分配前字节预算，单组件整树仍≤8GiB。共享几何／row表只保存一次，元数据不再物化mode×face重复计划。给出输入、输出、工作区、缓存、预计算表和hash材料的共存生命周期；不把6MB量级边界向量误称完整5.53GB体积向量。理论周期边界trace候选计数为每侧`2×p²×73×36＝189216`、两侧378432行；这是待与布局核对的derived计数，不是已取得native全体积映射资格。

### 5.4 条件完成原尺寸全表面、全部32060端口的真实组件作用

5.2及布局门通过后，本轮**应继续**全边界组件，不停在小测试。使用真实原尺寸上下表面、2628面／侧、全部ordered mode及上述紧凑边界DoF；输入是固定seed 423801／423803的两组一般复边界系数，包含x/y混合变化，不是只测可分平面波或n=0。它们是验证作用的任意场，不是PDE解。

先固定64→1024→32060的成本预检阶梯，取原有序前缀，仅用于估计同一计算核的内存和剩余费用，不用于精度选型。缓存identity／mode完备性必须先过。前缀是一次连续组件的已计费阶段，扩大时复用合法几何表；不通过资源预检不得盲目启动最后一级。完整批次含两个输入的投影、forward、adjoint、modal RHS、复线性／dual和零输入；保存全部32060复振幅、完整紧凑边界输出及source/hash。

独立核验分两层：①冻结12mode在完整上下表面的显式面片求和，与新计算核逐通道比较，不只比较总功率；允许分批，限定原oracle累计≤1200s，不强行重复慢参考直到预算耗尽。②对全部32060模式的新q30/q60计算结果比较完整向量和逐通道最大差，抽取的本地积分仍由5.2独立路径约束。记录q30/q60共同依赖；全部mode比较不能替代h/p收敛。对能解析核对的单位模态H／参考面功率全量重算。所有结果仍须明确是否做过真实MPI2/4，合成fixture不能顶替真实MPI资格。

全量启动前需给出剩余调用数乘实测前缀单价的保守费用估计，加setup、checker和清场后仍在本轮剩余总额内；对单次完整边界作用另限600s。估计只是准入，不授予48h。若不足，停止全量扩大、保留最高完成前缀及精确操作量，按5.5交付；不偷偷增预算、减少正式mode或把前缀标成全量。

### 5.5 无论正负，交付实际可用的下一层信息

输出统一的原尺寸物理／mode／边界layout／C-D-H符号与归一化合同、输入输出dtype／ownership／primal-dual、显式row adapter要求、独立checker及组件成本。原增广H=I约定与内部projection denominator必须明确转换，不能把Hp／Hhat／单位H混成同一矩阵。dot仍缺匹配solver时保留`SOLVER_PACKAGE_NOT_QUALIFIED`，但完成此包；不执行其体积求解。

验收分开报告：`NATIVE_P6_PERIODIC_PATCH_BRIDGE_QUALIFIED`仅四类native桥接；`TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q`仅在完整表面／32060模式／规定独立核验全部通过时授予，带MPI和q覆盖；费用另标实测，不自动称可满足完整48h。任何覆盖缺失都降为PARTIAL并列出具体缺失，不用总通过数掩盖。无论结果如何，原尺寸完整PDE、全部场／功率、2TB／48h及NN20%仍未资格化。

失败后有意义的替代分析必须同轮完成：

- native桥接不一致：区分排列／T_apply／Piola／周期复相位和corner重计；保存最小反例，不用训练补偿；修复软件后继续原范围。
- 分方向表示不能与native等价：只允许退回**相同q的参考积分按几何／波数复用＋有界mode批处理**这一近邻实现，沿用全部门和预算；不另开FFT、低秩、NN或求解器竞赛。若仍过不了，交付准确不可复用对象和操作量，不泛称有限元不可行。
- 积分q30/q60不一致：报告实际分子分母与截止／尺寸／相位依赖；停止精度扩大。可交付原q作用等价与容量结果，但不得授予精度资格。
- 正确但太慢／太大：报告预计算、一次作用、重放、归约、hash、IO和缓存失效的真实份额；给出`T_setup + K×T_boundary + T_volume/PC/recovery/IO`预算式及K未知的敏感性。不能把operator降时叫收敛改善；不再无界优化同一路线。

这份工作包通过后，真正下一道关键门才是与**同物理、同离散、同row／恢复接口**的全局solver合并资格，然后完整原方程／场／功率与h/p/外部截断验证。该集成尚未授权执行，更不能以边界完成声称最终目标达成。

## 6. 预算、停止条件及交接

V38为新增边界结构计算范围的新账本，V24–V37永久closed。不是旧q60或七／八块路线延长预算。首次接手登记UTC／monotonic／boot，日历24h、末1h仅清场交付，不随提交刷新。全部新增有载wall≤7200s，组件合计≤5400s，显式慢oracle含于其中且≤1200s；辅助单次≤600s／2GiB；探针累计≤60s；最后180s保留清场。数学线程1、无GPU，真实FE warn6GiB／hard8GiB、own swap0；单次完整边界作用600s上限须在预检满足后才启动。

真实native仍≤4类／≤24mode／累计≤32hex构造，复用完成面片对象和旧普通数组；仅边界的完整layout不计为体积mesh，禁止扩展完整体积图／A／SH／LU／QR／solve／训练。新增存储≤512MiB、Task042 artifacts总20GiB、自由磁盘≥50GiB；事前计入生成C/o/so、临时压缩共存和证据余量，未通过就选择本报告已授权的无巨型q60 JIT方案。新metadata／索引／数组同样计入，不能搬出任务目录躲门。

沿用Task042 native activation／complex128／IntType／ABI／BLAS实际getter及共享CPU／SMT准入，低优先级、独立缓存、一次一个heavy actor，不干预邻任务。暂时CPU拒绝至少120s后再探，不作为算法失败或提前等review理由。环境、身份、实际资源、数值门和总预算是真实停止条件；停止受影响扩大后完成5.5。普通导入、schema、lint、映射接线或测试失败在同轮预算内自主定位修复，不为小问题往返写报告。失败和修复费用全部保留。

一次交付response_v38、outcomes／项目总账、全部已运行／未运行／负结果、source／ABI／raw索引、全费用与依赖分组manifest；core保持opt-in、ordinary default不改。只提交推送本执行分支，不merge、不amend／force、不动其他分支。报告精确运行source、checker source、最终HEAD、clean／upstream 0/0；全部自有actor清除、ledger closed后通过原队列一次交回审阅并停止。

**本报告不授予merge approval。** 本地文档验收见[检查记录](outcomes/records/review_v35_documentation_checks.json)。GitHub精确交付页访问返回Cache miss，视觉NOT_VERIFIED；不称CI通过。
