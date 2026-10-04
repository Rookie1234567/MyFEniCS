# Review V37：接受V39有限接口资格，补齐可恢复的体积集成闭环

## 0. 审阅决定与最终目标

**V39的四类native边界接口可以接受；体积组合、非零内部／端口载荷恢复仍未资格化，完整0.7nm前向计算尚未完成。V40不再增加独立边界测速轮次，而是交付“可持久复用的真实体积／恢复证据包＋原尺寸集成容量合同”。先把接线和数据保存提前，再完成一次有限native闭环；成功后同轮完成部署及容量分析，普通bug不单独交回review。**

最终对象不变：50×25nm周期、z=−10..130nm、17×25×120nm规则Si光栅、λ=0.7nm，完整三维Nédélec有限元前向解，并保留非可分三维能力。完整N=1耗时≤172800s，同时任务整树／可用专属cgroup峰≤2e12B；系统及邻任务余量另留。边界计算、微型片段、二维／2.5D替代模型不是最终解。

NN增益仍要求**20%**：相同正确性下，相对最佳合格非神经路线，完整耗时或同时峰内存至少改善20%，另一项合规。数据／训练／构建／加载／推理／校正／恢复／审核／IO全部计费。当前没有目标完整非神经基线，也没有新增训练；边界结构复用、局部LU或传统接口优化不能称神经收益，不能沿用旧10%门。

本报告回应`execution-review-handoff-20261004-v39`。response_v39已正式回应Review V36，因此按AGENTS §15新建v37，下一执行为Task042 **V40**（不是dot的Task040）。审阅期间执行窗口停止；本次只读源码、原始字节和元数据，未运行新FE／算子／factor／solve，未修改求解源码、dot／其他分支／master，未用subagents或重置卡。不授予merge approval。

## 1. 独立核验与纠正审阅侧检查范围

| 项目 | 本次独立核实 |
|---|---|
| 交付本地／远端HEAD | `6f7a5576c7f87dcb014d6ea993fc792b1ff884c9`；canonical `/home/fenics/Projects/NN-Lab`，唯一分支`task42_neural_coarse_inverse`；clean、upstream 0/0，无本任务数值／编译actor |
| base／上一review | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`9430495d8a2cc6870ea1b79cfe4c60889ef5e3db` |
| 成功ADAPTER／失败COUPLED source | `79f8e25bda6e74d3222c23228360c3b1b9f5d519`；旧失败source及数组另外保留 |
| CHECK／消费demo source | `6fd4a43323e1aef7a4fd0df515eb63c1054aae2c`／`1987e51943a5e9027ddd41b951b7d19185e220a9` |
| 最终实现source | `8efb82029829dcba3f133b0ab90a1f05d9aa6c60`；包括callback存储验证和basis费用；文档HEAD不是数值source |
| 全仓索引与历史 | 7245 tracked文件hash／导航，109382914B文本，含39份response、36份review及任务书；2437份旧保护材料字节不变，含74份旧review／response；四个任务汇总保留旧后缀 |
| 原始档案与数据 | 376份gzip压缩／解压hash和长度通过；370个现存原路径匹配归档版本，无现存原内容不匹配；18个NPZ／426逻辑成员hash、shape、dtype、alias逐项通过 |
| 执行身份与资源 | 7次正式阶段manifest对应各自source的实现hash；24次监督逐样本RSS／swap／峰／清场重算，24次CPU tick／线程／SMT准入重算；ledger closed、active为空 |
| 静态／已存测试 | 12份增量Python静态compile；读取12份JUnit，保留18例3失败→修复通过及最终23例；最终21文件编译、ABI/getter、Ruff与15文档测试回执分别核对，不声称本次重跑数值测试 |

[审计记录](outcomes/records/review_v37_independent_checks.json)、[脚本](outcomes/records/review_v37_metadata_audit.py.gz)、[全仓索引](outcomes/records/review_v37_repository_index.gz)。索引原文SHA256：`53e40144bd5a0d9d26c69d6eb38978f87844a4b55017c255008cea5332d587ec`。185个已存标量比值／绝对判定独立重算；没有重新计算FE向量。源码深入检查覆盖新增adapter、体积组合／恢复driver、checker、预算／runner、测试和相邻现有凝聚／canonical模块。全仓索引不等于每个文件逐行语义审计；人工审阅和一般读写费用unknown。

**审阅侧文档检查错误确认并纠正。** `review_v36_documentation_checks.json`实际记录的是`review_report_v35.md`和当时README；审阅脚本替换版本名时漏改了报告文件名。因此它不能支持“V36报告本身已通过表格／链接检查”的旧声明。V39已检查真正V36，本次再次按明确文件名及SHA补验V36和新V37，见[文档检查](outcomes/records/review_v37_documentation_checks.json)。旧报告和错误记录保留，不倒改历史；此前数值字节／资源审计范围不受该文件名漏项影响。今后checker必须断言期望报告文件名、版本、SHA与实际读取一致。

## 2. V39哪些结论成立

`E`把真实有限元边／面系数取到紧凑边界，`Eᴴ`把边界力按共轭周期相位加回独立行。V39的新信息是原生编号和边界组件能正确连接；它尚未证明体积内部传播、恢复或求解。内部恢复还必须加上右端非零载荷产生的特解，只有零载荷例子不足以验证。

| 对象／比较目的 | 实际值与门 | 审阅结论 |
|---|---:|---|
| V38完整32060库存与独立12mode保存输出直接链接 | 两输入×12mode×q30/q60，共48项；max1.51058119943e-13<1e-10 | 修复旧checker缺口，复用既有数据；不是新的全量边界运行 |
| literal片段坐标关系／新E独立重算 | 旧20个cell方程max4.91206274743e-15；新四类完整向量最差1.36230187281e-12<1e-10 | `NATIVE_BOUNDARY_ADAPTER_QUALIFIED_ON_WITNESSES`，真实MPI1 |
| native普通两类、x缝、xy角 | 20唯一hex；storage3360/3360/3528/7056，内部1800/1800/1800/3600，slave0/0/168/660 | 真实四类有限见证；不是完整目标native rows |
| 未归一化纯内部输入 | forward／adjoint L2 6.42361410933e-12>绝对1e-12 | **原FAIL保持**；不能因为新输入通过而追溯改判 |
| 后续冻结unit-L2纯内部输入 | max绝对L2 2.31700717997e-13≤1e-12 | 新输入资格；支持尺度明确的结构零迹见证，不证明任意幅值下同一绝对误差界 |
| 六面原882基及450内部列 | Piola后切向max4.89817664524e-13；native C内部max1.30125352253e-11、D内部max6.10159124822e-14<系数门1e-10 | 原浮点项保留；拓扑支撑映射内部列为零不等于原native浮点数组逐位为零 |
| 计算存储／物理展开 | 20对保存副本；计算slave精确0，展开副本保留复周期系数 | 用途分离通过；未包含真实非零载荷内部恢复 |
| 有限体积COUPLED | actor912.591881218s，4个450行内部LU实际构造，carrier包含MPC slave导致异常 | `SETUP_EXECUTED_NOT_QUALIFIED`；实现失败，不是迭代收敛负结果 |
| 修复后真实恢复／残差恒等式 | NOT_RUN_AFTER_IMPLEMENTATION_FAILURE；合成非Hermitian40port及真实公共carrier方法小测试通过 | 真实native资格仍缺，测试不能代替 |
| 消费demo | max1.35885572735e-12；volume callback明确为零 | 仅接口演示；没有物理体积作用资格 |
| 原尺寸PDE／E/H/curl／R00_s,p,total／R/T/A/A_volume | NOT_RUN | 无完整物理结果，无2TB／48h及NN20%资格 |

unit-L2变化本身是合法的新见证定义，但必须限制宣传范围。V40固定该尺度，保留旧原输入及其失败数值，不能继续缩小f、g、alpha或参考量来让不合格门通过。对恢复后的实际大幅值场，使用原合同的完整残差和明确operation scale，不把unit-input通过当作所有输入的误差承诺。

canonical物理仍为nominal0.7、source0.699999988显式alias，Si n=`0.999885140474+4.32477054e-6i`、epsilon=n²、mu_r=1，原参考面130／−10nm、50／25nm周期、1°掠入射s偏振。体积q15只针对仿射、cell内常材料的多项式curl／mass项；它不同于已失败的Fourier边界q15。V39的q15/q17和native对照只在控制流中经过，原标量／tensor未保存，不能补写PASS。

证据：[response_v39](response_v39.md)、[完整结果](outcomes/native_boundary_volume_integration_v39.md)、[原始索引](outcomes/records/raw_evidence_index_v39.json)、[checker](outcomes/records/component_checker_v39.json)、[就绪矩阵](outcomes/records/integration_readiness_v39.json)。

## 3. 失败原因、成本及必须改变的执行方式

| 项目 | 实测／推导值 | 意义 |
|---|---:|---|
| 全监督／probe／bootstrap／close保守额 | 1249.459315514＋31.049503698＋3＋5＝1288.508819213s | 24次监督含失败、测试、编译和交付；不是完整N=1 |
| native／慢oracle累计 | 972.877846075/1200s | 其中912.591881218s是失败COUPLED；不能称已实际耗尽1200s |
| 组件含basis保守额 | 1000.189400152/5400s | 总额内子集，不重复加到全监督 |
| 同时整树采样峰／own swap | 2073407488B／0 | 0.5s样本，非连续cgroup硬峰；共享工作站干扰INCONCLUSIVE |
| native构造／局部LU | 36hex；实际4class，失败安全上界收费8/16 | 不是factor-free；实际cache payload缺失，规划112548672B不能冒充实测 |
| native C/o/so／新库存保守额 | 196161322／438002301B | 新2GiB内；Task artifacts15430859850B、free3365925904384B是交付快照 |
| 历史下界与unknown | 78517.88650908363s原下界保留，本轮监督另接续 | 历史完整费用及未监督实现／普通元数据unknown；不重置、不重复计费 |

源错误很具体：旧接线把全部非内部storage行交给`P6DirectTracePortTerms`，其中包括660个slave；公共API要求独立trace行，即`owned_active_original_dofs`。改用真实独立行并拒绝遗漏支撑上的非零C/D是正确修复。它本可用已保存literal、C/D和便宜的约束编号预检提前发现，不能继续等到所有native tensor／LU完成后才检查。

当时重放余量235.030006397s，而记录的JIT生成后至局部class结算时间戳跨度311.419277446s更大。允许据此保守拒绝**同一完整8hex构造**，但时间戳不是可复现子计时，更不是重放时间的严格下界；也没有证明所有4hex最小见证／精确缓存复用都不可能。执行没有违规延长原1200s，不过当前拆分把大部分工作变成失败后不可复用的临时对象，必须改。最后六面audit7.907852472s仍已计入native费用，未刷新旧上限。

**P1：昂贵阶段在最后才保存，导致证据与复用数据一起丢失。** `native_integration_study.py::coupled_stage`把class tensor、局部cache、原生小CSR、q15/q17比值和子计时积在内存中，carrier构造之后才统一写入。V39真实做过4个LU，却不能审核payload或重新使用tensor。V40必须先持久化每个已完成阶段，后续失败只使后续阶段缺失，不抹掉前面的科学证据；不从mtime或代码路径倒填本轮缺失值。

**P1（原尺寸接入门）：当前“稀疏E”构建仍含全native长度稠密中间量。** `build_literal_adapter`使用`G[...].toarray()`及每个边界row一条长度n的`candidate`；`native_entity_map_checks`也构造`len(active)×n`。小片段成立，但若n换为345771066，一个84×n complex128临时数组就要464716312704B；若保留全部378432个边界row的长度n候选，条件载荷约2.09PB。最终E是CSR并不能证明构建可扩展。转置后强制全native行CSR又会产生随n增长的indptr。V40仅改为entity-local非零master packet和owner索引散布，不创建目标全体积数组；不要继续用小片段低RSS外推2TB。

**P1（消费身份门）：尺寸相同不足以证明callback匹配。** `CoupledNativeBoundaryAction.__init__`目前仅核对边界行数和callable，adapter的identity是片段名字符串。冻结mode和坐标能防止原对象被修改，却不能拒绝另一个同尺寸、不同几何／Floquet／basis的对象。V40绑定结构化layout／basis／geometry／MPC身份以及volume物理／离散／source合同；以同shape但错误相位／材料／编号的反例测试拒绝。当前正式driver另有literal校验，四类已有结果不因此作废。

**P2：完整body checker必须重算新保存的原始证据。** 目前`check_coupled_vectors`主要比较事先保存的输出／残差对，`checker_stage`也没有消费丢失的q15/q17原tensor。本轮正确标记body缺失。V40需从保存的原native小CSR、C/D、局部tensor、f/g、存储／展开和压缩残差重算作用与平衡，不能仅信上游status、两个相等的摘要向量或控制流经过。checker只做矩阵／向量核验，不另实现求解器。

## 4. 历史去重与互补分工

| 路线 | 已有事实／是否继续 |
|---|---|
| V1–V5 p4神经严格粗逆 | 已关闭；无global p4因子复活 |
| V6–V14神经FE trace、固定特征／线性头、hidden训练 | 各自结论保留；V11 hidden更新未运行，V12梯度失败，V13一次更新不等于完整解；不是本轮新训练 |
| V15–V21全空间校正／算子复用 | 作用降时与收敛分开；GPOLY含随机神经G0，不能作为纯非神经最佳完整基线 |
| V22–V23 p1 Galerkin／image-QR | 98.99%误差表示不等于可消残差；V23完整0/6，warm Schur约2.5077e-6、通道功率差约1.69973e-6，zero约0.0681；LU及全局QR费用保留 |
| V24八块local／image组合 | warm／zero都已执行，完整0/5；LZ4约0.081376668、LCZ4约0.325262223；不加周期或scalar-tau |
| V25–V34残差方向／回流诊断 | 真实可移除性与软件／资源停止分开；单步放大不证明GMRES必失败 |
| V35固定七区PC／zero GMRES256 | Schur0.2052488635>0.01继续门，固定七／八块追加路线关闭 |
| V36库存、V37积分面片、V38完整边界 | 分别是库存／micro、有限p6、全原尺寸q30边界；q15负结果和巨型native q60停止保持 |
| V39 native适配器与有限体积尝试 | 四类adapter通过；真实体积恢复未完成；不再单开边界速度／输入尺度轮次 |
| 原尺寸完整冷求解／场与功率／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED；仍是最终缺口 |

完整历史由[Review V21](review_report_v21.md)、[Review V32](review_report_v32.md)、[Review V33](review_report_v33.md)、[Review V35](review_report_v35.md)、[Review V36](review_report_v36.md)及逐轮response/raw继续约束。保持warm-start与zero-trace、表示能力与残差改善、训练收益与传统算法收益分开；不因有局部LU或一次校正就称整体成功。

dot远端再次只读核实为`077ec9c8386c976da232093779279fb9d1a93033`。已记录的材料n差2.991716531811656e-8、缩小notch／532mode、canonical／恢复／runtime／raw缺口仍在，不能当匹配原尺寸solver。dot负责体积参考逆、周期分块、共享存储和规模验证；本任务只补其可消费的边界／体积接口与恢复证据，不执行它的C1/X/XZ/Y、factor或完整solver，不改其ref。V40可只读验收新包，但自身有限见证不等待该依赖。

## 5. V40唯一连续工作包

### 5.1 先完成可复用的数据协议和便宜预检

完整读取V39 raw/source及本报告。将`COUPLED`拆成可独立保存、hash绑定并继续消费的阶段：native geometry／约束与carrier预检 → class tensor／局部LU及恢复 → 原native小CSR和q15/q17对照 → 非零RHS组合／恢复 → 独立checker／部署。仍复用通用runner／watchdog和src数值模块，不为每个case复制求解器。

在任何新cell kernel或LU前，利用已有adapter、C/D和新建立的便宜native dofmap／约束映射检查真实独立trace行。实际调用公共carrier路径验证，不只构造一个与实现同形的断言。预先冻结dtype、shape、slave零存储、原Hp=I、归一化D和牵引B：增广块`[V,B;-D,I]`，native算子`A=V+B D`，有非零g时native有效右端为`f-Bg`。

完成§3稀疏中间表示及结构化身份绑定。每个edge／face仅持有其非零master索引与系数，最大实体变换沿用6／60行；去重按完整实体，不按浮点阈值。consumer使用压缩边界列／owner-local索引，散布进入调用者合法向量，不为全native列建稠密候选或长度n转置指针。小片段与V39保存E、Eᴴ和完整输出逐项等价；允许便宜的旧数组回放，不重建四类native边界或重新跑32060端口测速。

每个成功阶段立刻原子保存数组、元数据、完整source／输入／ABI／物理／basis／约束hash、准确子计时和对象唯一bytes。局部LU、恢复算子、原始tensor、小CSR不遗漏；保留失败checkpoint。后续软件修复只有不改变某packet的实际数值依赖时才可复用，必须用依赖hash证明；不能因HEAD变了而无条件重建，也不能因同路径同名而无条件沿用。

V39已完成的JIT C/o/so可在精确kernel身份、ABI及文件hash核实后只读复用或复制到新独立命名空间；复制及共存计入库存。V39没有保存的tensor／q15-q17／cache不能伪装成可复用packet。旧账本保持closed，不将compiled cache复用时间混为完整冷N=1成本。

### 5.2 一次有限native恢复闭环，必要修复从checkpoint继续

默认保留V39的8hex xy_corner、两种真实材料、p6/边界q30/体积q15/12冻结mode和原周期相位，保证新结果可直接补上原缺口。先在便宜几何／类身份预检中统计真正不同的raw geometry/material/orientation类，不把4个旧class机械当作所有fixture的数量。若全8hex预估不能在本轮剩余额度内完成，允许改用**唯一4hex x_seam**作为最小充分体积见证，但必须仍含air／Si、真实周期约束、内部行、非零f_i/g；先登记改变的覆盖，不能将它授为xy_corner资格。不扫描其他mesh／参数；先选定一个案例再启动。

新native首次构造之前给出冷／精确缓存复用两种费用、后续完整checker／交付成本和一次软件修复余量，使用V39实测作保守校准，不能把mtime跨度当精确内核定时。读不到准确分项则标范围／unknown并留足余量。组件进程定期输出阶段及已保存packet身份；连接错误、普通schema／lint等只修受影响阶段，不重复前面合格kernel／LU。

从既有本分支体积kernel建立受控cell class，保存完整882×882原native张量；独立Basix q15/q17对每个实际材料至少一代表作比较，保存两套原数组及差值，门1e-10。几何、Piola、orientation和材料身份分别核对。体积原生小CSR仅用于独立oracle，不因子化；固定目标全域mesh／A仍不构造。

使用两组一般复输入、零／复缩放，以及固定种子的非零内部f_i、非零端口g、一般trace／alpha。沿用合法MPC独立计算存储，另存物理展开副本。真实完成并保存：volume与独立CSR作用及伴随、`V+E^H B D E`与native完整作用、压缩RHS、恢复场、局部内部平衡、native／增广／Schur残差全部向量。恢复须包含`V_ii^{-1}f_i`，并检查仿射差`F(a)-F(b)=F(a-b)-F(0)`，不能把零RHS恢复函数直接套于非零RHS。

独立计算`r_native=r_FE-B r_port`及压缩RHS／恢复关系，比较门1e-10，全部保存分子分母与最差行；原生C/D内部浮点残项保留。一般输入的物理残差可以很大：这是算子／恢复一致性，不是PDE求解通过。严格零输入仍要求精确零；新unit-L2零迹规则冻结，不再缩放输入以规避失败。

若局部内部平衡超门，先区分接线、约束双重应用、方向、材料、数值条件与浮点项。只有明确属于局部舍入时，允许最多两次**同V_ii、同LU**的迭代精化，记录每步原矩阵残差与耗时；禁止shift、删项、改方程或静默正则化。若仍失败，停止该资格提升并按5.5分析，而不是开新的全局PC竞赛。

### 5.3 独立数组检查与真实volume消费演示

checker读取上述原native CSR／局部tensor、原C/D、输入f/g与完整恢复／残差数组，重新计算作用、局部平衡、MPC storage／physical映射、压缩残差注入及native恒等式；不能只检查“两个摘要相等”。缺q17、缺非零内部／g、漏slave、错class／物理identity、破坏一个恢复项时必须拒绝。保留现有非Hermitian／非互伴端口小反例，避免把D误当Bᴴ。

随后启动一个新的受监督消费进程，只加载冻结packet和真实volume callback，完成一般输入forward／adjoint、非零RHS恢复和残差审核；统计hash／解码／装载／作用／恢复／IO及同时峰。它必须实际使用已保存体积证据，不能再以零callback的PASS作为本轮主要交付。只做少量预登记调用，不做重复性能曲线、不运行Krylov。

有限闭环所有门通过才授予`COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES`，明确8hex xy或4hex x、MPI1／q／source范围。class packet可复用不等于可供任意几何使用；错材料、错几何、错orientation、错source依赖必须拒绝，不能为共享缓存合并近似相同对象。

### 5.4 同轮完成原尺寸集成容量合同

这是成功后必须继续做的推进，不另等review。复用V36原尺寸轴／物理库存和V38完整边界；只作流式索引、对象／生命周期和条件操作量分析，**不分配目标体积mesh、345771066行向量或完整A**。

列出原尺寸378432边界行的entity／非零master表示、索引宽度、owner分区与散布需要；给出稀疏E／转置实现及构建工作区的上界，证明不再有O(Nboundary×Nvolume)对象。实际native全体积ID尚未构造时，只能报告canonical实体协议与条件映射，不能把公式编号当实测DOLFINx编号。consumer协议为未来分布式owner留出口，真实MPI仍只资格MPI1，不用合成MPI顶替。

对体积缓存区分原tensor、LU、恢复、Schur、per-cell映射与共用class。允许从冻结结构轴／material tag推导几何／材料类库存和orientation条件上界，不运行dot的体积scale／共享factor实验。近似相同尺寸不能四舍五入后当相同矩阵；native orientation／全局约束缺失项仍unknown，不能用四片段class数代替全目标。

完整容量情景仍是530856cell、105298704 trace、238885200内部、345771066 storage行；单全complex128向量5532337056B。逐cell同时保存LU／恢复／Schur的条件载荷4956275464704B超过2TB；共享class是否避免该增长须由合同和实际对象数支持。Hp=I保持隐式，禁止目标32060²稠密端口矩阵16445497600B。所有局部LU／小变换真实成本列出；没有全局QR则写未构造，不能藏入setup。

将实测有限作用／恢复成本、边界既有成本、精确packet装载和未测全体积／PC／Krylov成本分开，给出生命周期共存表及`T_setup + K×(T_volume+T_boundary+T_adapter+T_PC) + T_recovery+T_audit+T_IO`。不得用微型cell单价直授48h，也不能把边界0.08s当完整iteration。输出可以支持／拒绝下一步原尺寸准入的具体缺项，避免只把现有UNKNOWN表原样再抄一遍。

dot仍无匹配包时，交付本分支真正可调用的有限体积／恢复包以及所需的物理、mesh、basis、MPC、row、forward／adjoint、恢复和资源字段；不等包才做上述工作，也不替dot重跑同一参考逆。若其新包已经到达，只读语义匹配，报告是否可消费；本轮不授权完整目标求解。

### 5.5 失败后同轮仍要交付的信息

| 真正未通过项 | 有效替代分析／停止范围 |
|---|---|
| 普通接线／导入／schema／lint／文档bug | 自主修复并定点重验，从可信checkpoint继续；不结束为“测试失败等review” |
| native tensor／q15-q17／orientation不一致 | 定位到材料／几何类和矩阵项，保留两条原数组、比值和差异结构；停止该体积类资格，不让后续恢复掩盖 |
| 体积作用正确、恢复或残差恒等式失败 | 用独立原矩阵分离V_ii求解、RHS约束、trace注入、端口归一化；保存最小非零RHS反例；不改输入尺度／不删通道 |
| 资源／时间预检拒绝8hex | 若尚未启动且唯一4hex仍满足所有语义及余量，按5.2执行；否则保存已完成包和准入算式，不把无法重跑某一构造泛化为方法失败 |
| 重放修复遇到额度不足 | 保留已完成阶段供未来消费，不再重复丢弃class；完成容量、失败机理和精确未运行清单后清场 |
| 原尺寸容量暴露不可扩展对象 | 给出随cell／class／边界行／rank增长的具体对象和字节，说明替代为共享／局部存储的必要条件；不能仅重复“需要更多内存” |
| dot不匹配／NN暂无完整基线 | 自身可完成范围继续；目标资格缺失明确记录，不训练来掩盖未解决的数值接口 |

停止扩大只依据真实数值／身份／ABI／资源／总预算门。失败不要求立即结束整个工作包：不依赖失败项的5.3保存数据审核和5.4容量分析仍完成。每次修复／精化／失败均计费，旧负结果不重写。

## 6. 本轮有界授权与交接

V40是持久化体积／恢复闭环及原尺寸容量合同的新范围；V39和所有旧窗口永久closed。它不是给旧七／八块PC或native q60续费，也不是原样重复V39末尾才保存的actor。首次接手冻结UTC／monotonic／boot，日历24h、末1h交付，提交不刷新窗口。总有载≤7200s、组件≤5400s，**native／慢oracle含失败与修复累计≤2400s**；此限额为一次完整构造、可信checkpoint继续及有限修复明确预留，不再把单次冷JIT吃掉大半额度后只允许不可恢复的整体重启。probe累计≤60s，辅助单次≤600s／2GiB，末180s保留清场。

数学线程1、真实FE MPI1、无GPU，FE warning6GiB／hard8GiB、own swap0；使用Task042 native activation与完整complex128／IntType／ABI／实际getter，沿用共享CPU／SMT准入、低优先级和独立缓存。一次一个heavy actor，不干预邻任务；临时CPU准入拒绝至少120s后再探，不算数值失败。

仅一个选定体积见证；新native mesh构建累计≤16hex（含失败重建），新局部450行LU累计实际≤8个class构建，write-ahead保守额度与实际分别记录；有证据确认未构造的预留可结算释放，真实已构造或未知失败份额不能扣除。总LU／恢复／Schurcache≤256MiB。小native CSR oracle单次≤8hex且不因子化。允许保留精确class packet用于只读检查／修复后消费，不能把重新factor计数清零。最多一次完整重建；之后必须利用可验证packet继续或按真实门收口，不无限开新case。

新增存储≤2GiB，其中新JIT／复制／压缩临时共存≤1.5GiB，≥256MiB留给科学证据和交付；Task042 artifacts总≤20GiB、自由磁盘≥50GiB。事前算入编译、序列化、矩阵／数组副本与索引，live guard仅后备。大数组ignored，历史raw和失败证据只读。禁止完整目标体积mesh/A/SH、全局LU/QR、Krylov求解、训练、旧q60重启，以及dot求解器运行／factor读取或ref修改。

最小相关测试→组件相关serial／必要合成MPI→收口Task-focused、Ruff、compile、ABI/getter和文档合同；已有昂贵Gate不因文档改动重跑。相关数值依赖变化重新资格化，纯计数／路径修复不冒充新数值结果。Git继续`-c gc.auto=0 -c maintenance.auto=false`，不改共享配置。

完成后一次交付response_v40、outcomes／项目总账、真实run/source/raw／checkpoint索引、完整费用、可消费包、原尺寸容量合同和依赖分组manifest。只提交推送唯一执行分支，不merge／amend／force；报告精确HEAD，ledger closed、全部自有actor清除、clean及upstream 0/0后，按原队列`execution-review-handoff-20261004-v40`交回并停止仓库工作。两个窗口不得并行执行。

原尺寸正式解的full explicit true residual≤1e-6、完整场／复振幅差≤1e-4、R/T/A/A_volume差≤1e-5、逐通道功率差≤1e-6及能量／吸收一致性≤1e-5仍未满足或未运行；参考身份、h/p及外部截断资格也不从本轮继承。**本报告没有最终成功或merge approval。** GitHub精确提交页Cache miss，视觉NOT_VERIFIED；本地文档检查不代替网页或CI。
