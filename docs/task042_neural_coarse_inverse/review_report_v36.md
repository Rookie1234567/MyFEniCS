# Review V36：接受原尺寸边界组件，下一轮接通真实体积接口与恢复

## 0. 决定、目标与本轮范围

**V38完成了有实质意义的原尺寸完整边界组件；最终0.7nm三维前向计算尚未完成。接受`NATIVE_P6_PERIODIC_PATCH_BRIDGE_QUALIFIED`和`TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q`，限定q30、真实MPI1及冻结输入身份。V39一次连续完成原生自由度抽取／散布、体积与边界组合、非零内部载荷恢复和独立残差恒等式，形成可被全局求解器直接消费的接口包。不得把“等待dot新包”或普通软件失败当作停止自身工作的理由。**

最终对象仍为50×25nm周期、z=−10..130nm、17×25×120nm规则Si光栅、λ=0.7nm的完整三维Nédélec有限元前向计算，并保留非可分三维能力。完整N=1耗时≤172800s，同时任务整树／可用专属cgroup峰≤2e12B，保留系统及邻任务余量。不能以边界分方向计算、二维／2.5D解或微型局部解替代最终三维解。

神经增益门继续为**20%**：正确性相同，相对最佳合格非神经路线，完整耗时或同时峰内存至少改善20%，另一项合规。完整费用包括数据、训练、构建、加载、推理、校正、恢复、审核和IO；任务书早期10%不是当前合同。V38没有训练，传统积分结构复用的收益不属于NN收益。目前也没有原尺寸合格完整非神经N=1基线。

本报告回应`execution-review-handoff-20261004-v38`。response_v38已正式回应review_v35，依AGENTS §15顺延为v36，下一执行交付response_v39。审阅期间执行窗口停止；本次未启动新有限元／求解实验、改求解源码、使用subagents或重置卡，也未修改dot／其他分支／master。下面的V39数值范围仅在正式队列交接后由执行窗口启动。

## 1. 独立核验及源码身份

| 项目 | 本次核验及边界 |
|---|---|
| 交付HEAD／canonical／分支 | `6166ad27e36c08408f81d4bba07d2f6b035e9f2b`；`/home/fenics/Projects/NN-Lab`；`task42_neural_coarse_inverse`；开始时clean、upstream 0/0，无本任务数值／编译actor |
| base／上一审阅 | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`cf0896e57f9f16970e5af6b55ad14920ab4c7815` |
| BRIDGE／LAYOUT source | `979192cdbd5c120ea46674c9fc60c73619b3d262`／`42b8baf9aeb4e6bb6548ca0087f67c3978be17a1`；保留min/max完成前缀20e287be及旧native ce18a605身份 |
| 完整COMPONENT／ORACLE source | `5529cc22a9dcc208b84ce930be271fdc54fcbbd1` |
| CHECK／DEPLOY source | `0e0184b9db55d517a8118a59061a4235a295c072` |
| 最终计数修复source | `6e4693620dc87802b44361da64620bf5d622b271`；部署文档的source_hashes是该最终快照，不能替代前列实际运行source；修复只复制计数字典快照 |
| 全仓恢复与历史 | 6831份tracked文件读取hash／导航，108611416B文本；38份response、35份review及任务书完整索引；1813份旧保护材料字节不变，含72份旧review／response；四个导航汇总保留旧后缀 |
| 原始记录 | 601份gzip压缩／解压hash和长度一致；597个现存原路径匹配归档版本，无现存原内容不匹配；11次正式阶段manifest实现hash对应各自source |
| 数组与生成文件 | 28个NPZ、733个逻辑成员逐份核对hash／shape／dtype及无损alias；236个去重生成／fixture归档解压核对668487576B原内容、113991353B压缩内容 |
| 资源与账本 | 32次监督逐样本重算成员RSS／swap／峰／清场；32次CPU tick、线程／SMT准入重算；ledger closed、active为空 |
| 静态与测试 | 14份增量Python静态compile通过；读取全部12份定点JUnit，最终27例通过；MPI2/4合成、ABI/getter与编译回执核对，不称本轮新FE测试 |

证据：[独立核验](outcomes/records/review_v36_independent_checks.json)、[审计脚本](outcomes/records/review_v36_metadata_audit.py.gz)、[仓库索引](outcomes/records/review_v36_repository_index.gz)。索引原文SHA256为`b3b061413ee8c4286070bff1f8b6e1bed0443026c56dab01b26b17dd6655bf89`。索引恢复不等于全仓逐行语义审计；本次深入检查新增积分核、原生映射、完整组件／oracle／checker、监督／归档和测试，回读现有体积压缩、canonical数据包及恢复源码。没有将旧记录当成新实验。

另用stdlib直接比较**已保存**的两组输入×12个复振幅，将独立oracle连接到最终32060维输出；未导入FE／NumPy／BLAS，未施加新算子。242项已存标量比值也独立重算。审阅人工及普通读写未单独监督，费用unknown，不补零。

## 2. V38的真实增量与资格边界

边界算子先把有限元边界场转换为每个出射方向的复振幅，再把这些方向的牵引返回有限元方程。V38利用矩形表面的分方向结构，将重复的面片积分改为共享小表和矩阵收缩；体积内部仍然是三维有限元。收益来自减少重复计算，代价是新边界坐标、映射、缓存以及它们的正确性验证。

| 被核验对象／为什么比较 | measured结果 | 判定 |
|---|---:|---|
| 四类native p6面片，完整882基／12mode；普通两类、x缝、xy角点 | 20唯一hex、累计28；同q30最差1.48686036402e-12<1e-10 | 原生MPC／方向／周期桥接通过；不等于全体积row映射 |
| 原尺寸上下表面完整作用 | 各2628面，378432紧凑边界行，32060 ordered端口，两组一般复输入 | q30/MPI1组件通过，已经运行全库存，不再仅是12mode外推 |
| 完整逐通道q30/q60差 | 最差1.6066324236103945e-12，index29663；分子6.00550e-15／分母3.73795e-3 | 小于1e-10；两者共享分方向核，独立性有限 |
| 完整forward／adjoint最大相对差 | 1.65302229731e-14／1.65163795364e-14 | 对冻结离散算子通过；不是迭代收敛改善 |
| 独立二维q60逐面求和，冻结12mode覆盖全表面 | 31536次面访问，已报完整比较max2.39972325681e-14 | 独立求积／求和路径通过；仍共享Basix基与边界布局 |
| 本次补查：上述12mode对最终全库存振幅对应项 | max1.5105811994279087e-13，输入a/index16028；8.87259363435e-16／0.00587362906 | 24项均过1e-10，补上已存数据的端到端链接；不是新计算结果 |
| 全库存H／单位通道参考面功率 | max5.46028927946e-16／3.41060513165e-13 | 小于1e-10；不是求解后R/T/A |
| 旧q15／巨型native q60 | 1.32594720615e-5>1e-10／NOT_RUN_STORAGE_GATE | 负结果与未运行状态保留 |
| 原尺寸体积A、完整原残差、E/H/curl、R00_s/p/total、R/T/A、A_volume | NOT_RUN | 无完整PDE／场／功率资格；无2TB／48h或NN20%资格 |

物理身份沿用canonical用户表：n=`0.999885140474+4.32477054e-6i`、epsilon=n²、mu_r=1；nominal0.7与source0.699999988保留显式alias。Si占x=16.5..33.5、y=0..25、z=0..120nm，原周期50／25nm、上下参考面130／−10nm、1°掠入射和s偏振不变。不要用dot的材料值或缩小notch几何静默替换。

p6/h≤0.7的530856cell、105298704 canonical trace、238885200内部行、345771066 full storage仍是容量情景；**尚未建立该完整体积mesh或证明该h/p足够准确**。边界q30通过不自动提升体积求积规则；体积q15情景也不能复活已失败的边界q15。

详见[response_v38](response_v38.md)、[完整结果](outcomes/directional_boundary_structure_v38.md)、[组件checker](outcomes/records/component_checker_v38.json)及[部署合同](outcomes/records/deployment_package_v38.json)。

## 3. 费用及接入前必须处理的问题

| 口径 | 核实值 | 含义 |
|---|---:|---|
| 全监督＋probe＋bootstrap | 654.956926790＋41.348239223＋3＝699.305166013s | 含失败、测试、JIT、归档；另5s保守close余量，实际close0.669592552s；不是完整成功N=1 |
| 组件／慢oracle保守收费 | 248.692253532／174.644424674s | 后者含失败BRIDGE，属于总额内份额，不能再加一次 |
| 同时整树采样峰／own swap | 1047965696B／0 | 0.5s样本，不是连续cgroup硬峰；共享工作站，性能干扰INCONCLUSIVE |
| 全q30 setup／首次forward／adjoint | 4.016996373／0.077134419／0.076004680s | 只说明组件成本；前缀、q60、oracle、IO及失败另已计入 |
| 边界cache／共享layout／一个边界向量 | 7628096／10596096／6054912B | 真实数组载荷，不是完整体积solver峰 |
| 新已知库存／保守含源码导航余量 | 433468326／434516902B | V38在512MiB内；不能改写V37曾越界的历史 |
| Task042 artifacts／可用磁盘 | 15220265565／3369251803136B | 交付快照，不替代下一轮现场准入 |
| 历史实测已知下界 | 78517.88650908363s | 不含bootstrap保守收费；完整历史及未监督实现／元数据仍unknown |

失败没有隐藏：首次inspect 4.001501996s，两次BRIDGE 79.488342440／24.846572670s，三次COMPONENT 8.438553591／11.864887528／12.850935348s均保留。原因分别涉及Basix variant、重复JIT预留／FFCx C文件缓存标志、单侧前缀、active预算查询及输出预留不足；这些已同轮修复，未重复请求review。初始提交触发auto packing提示、是否完成unknown；后续禁用自动maintenance且未见活跃gc/repack，不能倒称全程无maintenance。V39所有可能触发维护的Git命令继续加`-c gc.auto=0 -c maintenance.auto=false`，不改共享Git配置。

**P2：独立checker尚缺最终输出链接和literal adapter的独立重算。** `benchmarks/check_boundary_structure.py`的explicit比较使用另建的12mode实例，没有取最终32060输出的对应项；本次24项保存数据补查已排除本次结果受此影响。它也没有独立重算LAYOUT的原生映射。V39先补保存数组链接和映射checker：删去／打乱mode对应、破坏一个周期复系数或方向变换必须拒绝。不要重跑V38全套FE，仅重验受影响的保存数据和新增接口。

**P1（目标接入门）：面片的可逆坐标变换不等于真实体积自由度适配器。** 当前`qualify_patch_layout`通过原始矩阵关系求得324／624维片段映射，并验证小片段一致。这可以证明局部坐标等价，却还没有给出完整native体积向量怎样取出边界、怎样把对偶力正确加回，以及MPC slave零存储和物理展开副本如何区分。不能把局部least-squares映射延展成全目标稠密QR／逆；V39必须由真实entity／orientation／ownership生成稀疏局部映射。

**P2：部署对象的输入身份及生命周期须闭合。** 新`DirectionalBoundaryAction`对冻结runner有效，但通用调用仍需shape／finite／正H／geometry／mode identity检查；可变坐标及浅层mode字典不能在建cache后静默变化。V39将不可变快照或严格版本校验、分配前容量拒绝放进实际消费接口。当前真实FE只MPI1；合成MPI2/4不覆盖不等面片数的所有collective路径。V39不自动扩真实MPI，不向分布式consumer宣称已合格。

还有一个决定全尺寸可行性的尺度问题。p6单hex有450内部行、432 trace行。若机械地逐cell保存complex128的LU、450×432恢复矩阵和432×432 Schur块，530856cell的**条件载荷**分别为1719973440000、1651174502400、1585127522304B，合计4956275464704B，已超2TB。这不是不可避免的下界：相同物理／几何／方向类可共享，但必须证明类身份与真实数量，不能用V38四类边界代替体积class库存。逐cell稠密Schur作用还有99070470144次复数乘加／次的条件操作量，不把它换算成未经测量的秒数。

同样，32060×32060的complex128稠密端口矩阵单份16445497600B。现有`P6CellCondensedAction`保留小规模稠密Hp/Hhat的接口不能原样放大；V39消费包对目标端口使用对角／作用形式，禁止为单位Hp创建该稠密矩阵。上述风险比继续优化0.08s边界作用更接近最终瓶颈。

## 4. 历史去重、未运行项与dot分工

| 路线 | 已有答案与后续决定 |
|---|---|
| V1–V5 p4严格神经粗逆 | 关闭；不复活global p4因子或改名重跑 |
| V6–V14神经FE trace、固定特征／线性头、hidden训练 | 分别评价；V11 hidden更新NOT_RUN、V12梯度失败、V13一次接受不等于完整解；不能将固定基或低loss叫NN整体收益 |
| V15–V21全空间校正、算子class复用 | 真实残差改善与算子降时分开；GPOLY含随机神经G0，不能充当纯非神经最佳完整基线 |
| V22–V23 p1 Galerkin／image-QR | 98.99%误差表示不等于实际可消残差；V23完整0/6，warm Schur约2.5077e-6、通道功率差约1.69973e-6，zero约0.0681；全部LU／QR成本保留 |
| V24八个原p3局部LU／叠加image粗校正 | warm／zero已实跑，完整0/5；LZ4 0.081376668、LCZ4 0.325262223；不再作为尚未发布计划，不加第五周期 |
| V25–V34固定方向／回流诊断 | 有限残差可移除性；Bfull单步2.977／4.065放大不证明GMRES必失败；软件／资源轮不重复计为新数值负结果 |
| V35固定七区PC＋zero GMRES256 | 原Schur0.2052488635>0.01继续门，固定七／八块追加预算关闭；native单项或恢复通过不能授完整解 |
| V36库存与lazy provider | 真实32060库存与micro40端口旧裁剪等价；未证明完整目标作用 |
| V37 p6未裁剪普通面片 | q15失败；q30/q60有限正结果；周期／全量缺项及native q60资源停止保留 |
| V38分方向完整边界 | 本轮新增完整原尺寸组件正结果；非NN，不推导收敛、体积恢复或完整48h资格 |
| 原尺寸完整体积／冷求解／场与功率／h-p及外部截断资格 | NOT_RUN／NOT_QUALIFIED；这才是仍需完成的最终工作 |

历史依据仍是逐轮response／review／raw，详细路线表见[Review V21](review_report_v21.md)、[Review V32](review_report_v32.md)、[Review V33](review_report_v33.md)、[Review V34](review_report_v34.md)和[Review V35](review_report_v35.md)。不再安排同p1空间换测试、scalar-tau、旧预算延长或只做表示率的轮次。

dot只读身份仍为`077ec9c8386c976da232093779279fb9d1a93033`。此前逐字段验收记录的材料n差2.991716531811656e-8、缩小notch几何／532mode、canonical／恢复／合格runtime及raw缺口没有消失。见[consumer_v37](outcomes/records/consumer_v37.json)。同称0.7nm／p6不等于同算子，文件hash不同本身也不等于物理不同。

dot继续体积参考逆、周期分块、共享存储和规模验证。本任务V39只完成**边界接线和恢复／残差的集成正确性**，不运行或复制dot的C1/X/XZ/Y求解器试验、不调用其factor、不修改其ref。可以只读检查其新发布包，但缺包时继续下述本分支原生见证。合格体积包若确实到达，只接受本报告范围内的接口／作用检查；原尺寸求解仍需独立容量、正确性和执行准入，不能自动启动。

## 5. V39唯一连续工作包：让边界组件成为体积求解器可调用的一部分

### 5.1 先修证据链接，冻结真实数据合同

完整读取本报告与V38实现／原始数组，补§3 checker和输入生命周期。冻结物理、ordered mode、p6 variant、边界q30、几何／MPC／basis／layout／符号与归一化身份。既有V38数组只读；不重启closed窗口或巨型native q60编译。实现作为显式opt-in进入合适的src通用模块，复用现有runner／watchdog；不要另复制一套task专属求解器。

统一端口合同：用`D`表示已经除以projection denominator的振幅提取，用`B`表示V38 modal_rhs的牵引散布，则增广系统为`[V, B; -D, I]`，消元后的体积算子是`A=V+B D`。projection denominator、原Hp与消元后的Hhat分别定义；不能因为都叫H而混用。若使用未归一化D，写出显式对角转换并逐项验算，不改符号来凑通过。

### 5.2 实现真实native抽取与对偶散布，不依赖拟合全局矩阵

用既有p6 N1curl native element、真实cell permutation、entity keys、DOLFINx dofmap和MPC slave/master系数建立`E`：从native独立存储取出V38紧凑边界系数。`E^H`将边界对偶量加回native独立行，包含所有共轭、周期缝和corner去重。边界之外包括内部DoF不能误收力。保存原生literal证据和可重建局部entity变换；复用`hcurl_canonical_vector_dolfinx.py`／现有约束工具的适用部分，不重新发明编号系统。

可以使用有界edge／face小块变换及必要局部小线性解，必须记录次数、最大维数和成本；禁止全表面／全体积稠密拟合、全局QR或逆。native primal到紧凑primal的变换与dual回写不能用同一无共轭操作混代。保存严格slave零的计算向量和用于物理恢复的展开副本，两者明确隔离。

真实见证优先复用V38四类面片描述／已有literal；必要时在相同边界面片向体内增加一层，提供内部行和非零内部载荷。保持真实参考面、原50／25nm周期相位和目标边界cell宽度；最多四类，预登记全部新增几何、材料、层数、mode和源身份。它们是原对象的有限边界片段／collar，**不是完整原尺寸模型或局部物理解**，自由的人工内切面不能冒充真实边界条件。

对两组一般复native输入、纯内部输入、纯端口输入、零及复线性缩放，检查`E`与literal原生面泛函、`E^H`与原生载荷逐项一致；检查内积恒等式、所有选中复振幅／forward／adjoint／modal及MPC闭合。冻结12mode；顺序与原32060库存一一对应，不能事后挑容易的通道。保存数组独立checker重算全部向量与最差分子／分母，门为1e-10；精确零输入要求精确零，其他近零沿既有明确绝对规则报告。

### 5.3 在同一轮验证体积组合及非零载荷恢复

不求新逆、不做收敛竞赛，复用本分支现有体积action和cell内部消元语义，将组合实际接成`A_native x = V_native x + E^H B D E x`。对同一有限见证，用原生未裁剪FE体积／边界作用作为独立对照，保存完整输出向量，不能只测一个R/T或一个范数。必要时允许单个≤8hex见证的小型native稀疏装配用于oracle，禁止完整目标体积装配；同时计入矩阵、编译临时文件与输出的共存量。

体积积分先复用已资格化的同物理／同p6／同ABI kernel。没有精确匹配时，允许为这些有限见证建立新native体积kernel并绑定源码；对轴对齐仿射、cell内常材料的curl／mass多项式项单独说明体积q15的充分阶数并验算，不能拿边界Fourier积分q15失败来省略或否定这项检查。不要移植dot的新体积优化算法；原生kernel不可承担时按5.5给出真实容量缺口。

内部恢复是根据边界未知量与右端载荷还原每个cell内部系数，使求解器能得到完整场。必须验证仿射项：`u_i=V_ii^{-1}(f_i-V_it u_t-B_i alpha)`，不能只测`f_i=0`。允许有界450×450内部LU和必要局部恢复矩阵，最多16个独立class、所有LU／恢复／local Schur缓存合计≤256MiB；共享以物理／几何／方向／source的完整身份为依据，禁止静默正则化或调用旧warm／REF7／全局p4因子。

p6 cell内部基的切向边界迹应为零；用拓扑支持、完整882基native数组和误差门证明此事实，而非按数值阈值删项。若因此`B_i,D_i=0`且Hp=I，目标包用隐式单位／对角作用，避免生成稠密Hhat；如果实际基／约束违反前提，保存反例并停止该简化，不能硬编码零。

至少一个含真实内部行、一般非零`f_i`、非零port RHS `g`和周期约束的见证，保存：local内部平衡、压缩RHS、恢复场、原native作用、增广两块残差，以及独立形成的关系`r_native=r_FE-B r_port`（Hp=I且native有效右端为`f-Bg`）。分别从两条计算路径得到两边，误差≤1e-10；不要直接用一边定义另一边。一般输入不要求物理残差接近零，这是一致性验收，**不能标成PDE收敛**。复用`p6_cell_condensed_action.py`的reduce_rhs／recover_storage语义，但不能把其小规模稠密端口持有方式推广到目标32060。

这一阶段完成后，才能说“新边界核能与真实体积未知量和恢复流程共同工作”。这比单独继续测边界速度提供新的必要信息，但仍没有给出冷迭代次数。

### 5.4 交付可消费接口与完整成本公式，结束独立边界开发轮次

交付可调用的extract／scatter／boundary apply／adjoint／modal recovery接口和体积callback包装，dtype、局部／全局编号、ownership、MPI覆盖、MPC存储、参数身份、缓存失效与回收顺序齐全。部署demo只消费冻结见证数组／合法callback，不能隐含运行PDE或加载旧factor。原尺寸完整layout可复用V38库存作流式entity覆盖检查；未建立native体积mesh时，其全局native row IDs、完整MPC与恢复仍明确unknown，不将公式编号称实际DOLFINx编号。

完成一份**原尺寸集成就绪矩阵**：边界组件、native片段adapter、仿射恢复、同物理体积包、全目标row映射、分布式ownership、完整冷求解、原残差、场／功率、h/p与mode截断、2TB／48h、NN20%，每项分别给source／evidence／measured-derived-not_run分类及缺口。已有合格项不因纯元数据变化重跑。

从本轮实测给出抽取、散布、边界、局部恢复、数据封装／hash／IO的时间和共存峰；列出全目标尺寸及未知体积class数、solver向量数、迭代次数。使用`T_total=T_setup+K×(T_volume+T_boundary+T_adapter+T_PC)+T_recovery+T_audit+T_IO`，单独注明NN阶段尚未运行。可推导允许的K与每次volume/PC成本的条件关系，不用微型局部均价直接授予48h。内存按生命周期同时共存，既不将不共存峰相加，也不漏掉LU、恢复、Krylov和全局QR；本轮禁止新增全局QR。

该包收口后，独立边界路线不再靠增加相同测试滚动开新review；下一实质里程碑应是匹配体积引擎的完整集成／原尺寸容量准入。若尚缺dot合格包，准确列出可被其直接调用的接口及缺失字段，不能把等待依赖写成最终问题已解决，也不重复运行它的solver试验。

### 5.5 验收、真实停止条件与有用的失败替代

| 情形 | 同轮必须采取的动作与交付 |
|---|---|
| checker／导入／schema／lint／映射接线bug | 自主定位、修复、最小相关测试后继续B→C→D；失败与修复费用保留，不能只交“测试失败等待review” |
| native映射不一致 | 固定最差entity，分别检查排列、T_apply、Piola、周期共轭、corner重复与slave存储；保存可复现反例，在原路线预算内修复，不训练拟合误差 |
| literal映射通过、组合或仿射恢复仍超1e-10 | 分离体积tensor／orientation、内部消元、端口归一化／符号、RHS双重MPC约束；报告具体分子分母与失败行；无法修复时停止数值扩大，仍交adapter和缺失接口分析 |
| 局部LU真实奇异／数值门失败 | 保留rank／pivot／尺度证据；不把接口失败改成收敛结论，不追加新的全局PC或参数扫描 |
| JIT／内存／存储预检拒绝 | 优先复用精确hash kernel与已经保存的原生数据，仅无损归档本任务已退出生成副本；仍不够则停止新native阶段、交已验证部分和所需新增字节／时间，不放宽gate或删除失败科学证据 |
| dot包不匹配／尚未发布 | 继续本分支有限见证与消费包；缺失部分明确NOT_RUN，不启动dot实验、不假设不同物理可通用 |
| 达到真实ABI／身份／资源／数值／总预算门 | 停止受影响的新数值，完成原因拆分、成本／raw／未运行矩阵、closed及清场后集中交付；不以普通小bug提前触发此条 |

资格名保持分层：`NATIVE_BOUNDARY_ADAPTER_QUALIFIED_ON_WITNESSES`、`COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES`分别需要5.2、5.3完整通过；覆盖缺失标PARTIAL并逐项列出。全目标native row／完整solver／物理结果仍不得继承这些资格。最终物理解仍需full explicit true residual≤1e-6及全部合同物理门：完整场／复振幅差≤1e-4，R/T/A/A_volume差≤1e-5、逐通道功率差≤1e-6、能量与吸收一致性≤1e-5；参考身份与h/p外推范围需另外成立。warm与zero-trace不能互代，单步修正和native单项通过不能授整体成功。

## 6. 有界授权、交付与交接

V39为上述新集成范围的新账本，V24–V38永久closed；不是旧块PC、q60或V38性能测试续费。首次接手登记UTC／monotonic／boot，日历24h，末1h仅清场交付，提交不刷新窗口。全部新增有载wall≤7200s，组件合计≤5400s，其中新native／慢独立oracle累计≤1200s；辅助单次≤600s／2GiB，probe总≤60s，保留最后180s清场。费用包括失败、修复测试、JIT、checker、归档及部署；未监督实现／普通读写照实unknown。

数学线程1、无GPU；真实FE warning6GiB／hard8GiB、own swap0，沿用Task042 native activation、complex128／IntType／ABI／实际线程getter及共享CPU／SMT准入，低优先级、独立缓存、一次一个heavy actor，不干预邻任务。暂时CPU拒绝至少120s后再探，不当算法失败。全新native累计构造≤64hex、最多四类见证／12mode；单个体积oracle≤8hex；上述16个局部LU及256MiB缓存包含所有重建失败费用与峰，不把重建当新预算。真实FE维持MPI1，现有相关合成MPI2/4与共同失败测试按改动需要验收。

V39新增存储≤2GiB，Task042 artifacts仍≤20GiB，自由磁盘≥50GiB。此新增范围首次允许有限native体积kernel，明确给其C/o/so及临时副本留出空间，避免机械沿用边界轮512MiB导致同类存储往返；不追认旧越界，也不重启旧native q60。新JIT及其压缩共存预算≤1.5GiB，至少256MiB留给科学证据／最终交付，其余数组、索引和fixture计入同一2GiB。事前逐项核算并通过总库存门，采样guard是后备，不能代替分配前准入。大科学数组留ignored，旧raw只读。**本轮新授权只包含有界native体积作用与局部内部LU，不包含原尺寸体积mesh/A/SH、全局LU/QR、Krylov求解、训练或dot实验。** 小型独立oracle装配仅按5.3范围，不能借其扩大模型。

先做最小相关测试，组件阶段相关serial／必要合成MPI，收口Task-focused检查、ABI/getter、Ruff、compile和文档合同；相同source／输入的昂贵Gate不因文档修改重跑。数值实现和checker源身份分别冻结；计数快照与完整费用一并独立复算，不能用文档HEAD冒充run source。

最终一次提交response_v39、outcomes／项目总账、完整raw／run／source／费用索引、集成就绪矩阵及依赖分组manifest，只推送唯一执行分支，不merge、不amend／force。清除全部自有actor、ledger closed，核实精确HEAD、clean和upstream 0/0后，通过原队列一次交回审阅窗口并停止仓库工作。两个窗口不得并行；普通修补不额外制造review轮次。

**本报告不授予merge approval。** 本次[文档检查](outcomes/records/review_v36_documentation_checks.json)是本地检查；GitHub精确提交页Cache miss，视觉NOT_VERIFIED，不称CI通过。
