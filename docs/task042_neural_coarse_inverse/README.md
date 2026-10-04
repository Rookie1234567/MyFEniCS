# Task042 V39：原生边界接口资格通过，体积组合保留真实失败

通过稀疏实体映射将体积系数取到边界，并按共轭周期相位把力加回；新增的是接线，不是神经训练。真实体积组合已运行并失败，接线修复通过小回归，但剩余慢oracle额度不足以完整重放，非零内部RHS恢复和完整解仍未资格化。

| 对象／方法 | 实际值及原因 | 分类／证据 |
|---|---|---|
| .7nm／p6／q30／四类20hex／12冻结mode | native最大1.36230187281e-12<1e-10；全32060输出链接最大1.51058119943e-13 | NATIVE_BOUNDARY_ADAPTER_QUALIFIED_ON_WITNESSES，MPI1 |
| 原内部零迹／计算存储 | 六面完整882基，切向max4.89818e-13；20对MPC存储／展开副本 | 原浮点C/D保留，不硬设0；旧未归一化L2 6.42361e-12 FAIL保留 |
| 有限体积组合／非零载荷恢复 | 912.591881218s后carrier含slave而失败；4内部LU class，修复后完整重放预测超235.030s余量 | SETUP_EXECUTED_NOT_QUALIFIED／恢复NOT_RUN_AFTER_FAILURE |
| 消费接口 | extract/scatter/forward/adjoint/modal/implicit Hp，demo差≤1.35886e-12 | 明确零volume callback，非物理解 |
| 同时整树峰／ownswap／费用 | 2073407488B／0；component992.281548s，native972.877846s | 0.5s采样、shared-workstation；全部费用另列 |
| 原尺寸全PDE／E/H／R/T/A/A_volume／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 本轮没有训练，不归神经收益，不授原尺寸资格 |

[Review V36](review_report_v36.md) · [response](response_v39.md) · [结果](outcomes/native_boundary_volume_integration_v39.md) · [run/source](outcomes/records/run_index_v39.json) · [原始证据](outcomes/records/raw_evidence_index_v39.json) · [成本](outcomes/records/resource_costs_v39.json) · [集成就绪](outcomes/records/integration_readiness_v39.json)。唯一下一建议：匹配体积引擎，补有限非零内部／port RHS恢复及独立残差恒等式，再作原尺寸容量准入；结束独立边界测速轮次。以下历史正文逐字保留。

<!-- V39-LATEST-END -->

# 当前审阅入口：Review V36 / 下一执行 V39

[Review V36](review_report_v36.md)已独立审阅V38交付`6166ad27e36c08408f81d4bba07d2f6b035e9f2b`。接受q30／真实MPI1的原尺寸完整32060端口边界组件；原尺寸完整0.7nm三维前向解、2TB／48h和NN20%仍未资格化。

V39一次连续接通native边界抽取／对偶散布、有限体积组合和非零内部载荷恢复，并交付可直接消费的接口及完整资源公式。允许报告规定的有界native体积作用／局部内部LU，不运行全局求解或dot实验；普通bug同轮修复，真实数值／身份／资源门按报告处理，不等待dot包才开始自身工作。

[独立核验](outcomes/records/review_v36_independent_checks.json) · [文档检查](outcomes/records/review_v36_documentation_checks.json)。提交推送／清场后通过同一队列交接，两个窗口不并行仓库工作；不merge。以下完整历史正文逐字保留。

---

# Task042 V38：全原尺寸边界作用通过，完整体积解仍未资格化

将相同有限元边界积分按x/y方向收缩并共享几何，减少逐通道重算，代价是局部坐标桥及7.28MiB缓存。它只加速端口组件，不改变体积三维Maxwell，也不是神经训练增量。

| 对象／数据身份 | measured或not_run结果 | 边界 |
|---|---|---|
| .7nm／50×25nm／上下2628面／p6／32060端口 | 四类native q30完整882基，最差1.48686e-12；两一般复输入全量PASS | q30/MPI1 TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q |
| 逐通道q30/q60／独立12mode全表面 | max1.60663e-12／2.39972e-14<1e-10 | 未删通道／校幅相；不证明h/p收敛 |
| 完整q30首次forward／adjoint | 0.077134419／0.076004680s；cache7628096B | setup／失败／IO与旧费用全部另记；shared-workstation |
| 同时整树采样峰／own swap | 1047965696B／0 | 0.5s，不是连续cgroup硬峰；MPI1/数学1，无GPU |
| 原方程／E/H/curl／R/T/A/A_volume | NOT_RUN；全目标native row adapter与solver未合格 | 仅边界组件，无新official结果 |
| 2TB／48h／NN20% | NOT_QUALIFIED／NOT_DEMONSTRATED | 历史成本及unknown保留；旧q15FAIL/native q60未运行保持 |

[review](review_report_v35.md) · [response](response_v38.md) · [结果](outcomes/directional_boundary_structure_v38.md) · [证据](outcomes/records/raw_evidence_index_v38.json)

唯一下一建议：匹配体积solver的native边界row抽取／散布及内部恢复资格；本批不实施、不merge。完整旧正文逐字保留。

<!-- V38-LATEST-END -->

# 当前审阅入口：Review V35 / 下一执行 V38

[Review V35](review_report_v35.md)已独立审阅V37交付`011718d84606cc052085c200d2ce767030f21e38`。接受普通p6面片的有限未裁剪分块资格；q15负结果、native q60存储停止和周期缺项保留。原尺寸完整0.7nm前向解、2TB／48h与NN20%仍未资格化。

V38一次连续推进：补齐周期native q30与独立q60见证、修复完整checker和重复元数据、实现同离散的分方向边界计算，并在数值／容量门通过后执行原尺寸完整表面及全部32060端口组件。普通bug同轮修复；不重复巨型q60 JIT或旧7/8块，不运行dot体积solver。完整范围、验收、预算和失败替代均以本报告为准。

[独立核验](outcomes/records/review_v35_independent_checks.json) · [文档验收](outcomes/records/review_v35_documentation_checks.json)。完成提交／推送／清场后按原队列交接，两个窗口不并行仓库工作；不merge。以下历史正文逐字保留。

---

# 最新交付导航：V37 / Review V34 已连续收口

已完成普通p6真实4hex／12mode未裁剪积分、单mode面片分块及独立保存数组检查。q15不合格；原生q60 JIT超过新存储门，周期缝／角点未完成，故仅P6_TILE_INTERFACE_QUALIFIED_ON_PARTIAL_WITNESS，无目标全量边界／完整求解／NN20%资格。

[合同](review_report_v34.md) · [response](response_v37.md) · [完整结果](outcomes/target_p6_boundary_tiles_v37.md) · [run/source](outcomes/records/run_index_v37.json) · [checker](outcomes/records/component_checker_v37.json) · [费用](outcomes/records/resource_costs_v37.json) · [原始证据](outcomes/records/raw_evidence_index_v37.json) · [部署与缺口](outcomes/records/deployment_package_v37.json)。失败保留；正式入口仅列复现身份，closed后不得重开运行。以下完整历史正文保留，“当前”只指当时状态。

<!-- V37-LATEST-END -->

# 当前审阅入口：Review V34 / 下一执行 V37

[Review V34](review_report_v34.md)审阅交付HEAD `bc2efb6e9013ceeb3e34d4c295a21db8b054c837`。接受V36的32060原尺寸ordered端口、解析容量及与现有裁剪表面实现的micro组件等价资格；不授原尺寸完整求解或NN20%。

V37一次连续完成：dot已发布包的语义身份验收、目标p6面片的未裁剪积分／q15→30→60审计、单mode内部面片分块及容量／作用验证。缺匹配solver也继续自身边界任务，不重跑dot求解或旧七／八块路线。普通bug同轮修复，真实Gate和预算依报告执行；交付response_v37后清场队列交回。

[本轮独立核验](outcomes/records/review_v34_independent_checks.json) · [文档验收](outcomes/records/review_v34_documentation_checks.json)。以下V36及此前历史全文保留；不merge。

---

# 最新导航：V36 / Review V33 已连续收口

已完成原尺寸规则3D物理／32060全端口／解析容量包，以及真实384hex/p3/q15/40mode按需provider边界配对。只获PORT_COMPONENT_QUALIFIED_ON_MICRO；目标solve、2TB/48h、NN20%未合格。旧V35七／八块追加路线关闭，未重复actor。

[review](review_report_v33.md)、[response](response_v36.md)、[完整结果／命令](outcomes/original_size_port_preparation_v36.md)、[run/source](outcomes/records/run_index_v36.json)、[独立checker](outcomes/records/component_checker_v36.json)、[费用](outcomes/records/resource_costs_v36.json)、[原始证据](outcomes/records/raw_evidence_index_v36.json)。新四个one-run已执行，scope收口closed；只读包查看见结果文档，不授权重复数值。

以下全部历史正文逐字保留；旧“当前”不是待执行命令。

<!-- V36-LATEST-END -->

# 当前审阅入口：Review V33 / 下一执行 V36

[Review V33](review_report_v33.md)审阅交付HEAD `9a6cadff62771d63a4996a6dccc9424df431ee4c`。接受V35唯一冷启动GMRES256的可信负结果：原Schur残差0.2052488635，高于0.01继续门；不追加固定七／八块周期。完整原尺寸0.7nm、2TB／48h及神经20%均未资格化。

V36执行一个连续工作包：原尺寸物理／完整mode／无装配容量合同，真正限制缓存大小的端口provider与既有真实micro边界作用对照，供全局solver消费的输入和验收接口。dot继续其完整3D参考逆、周期分块、共享存储及规模验证；不重跑其求解、不改其分支。普通bug在V36内修复，按报告预算与真实Gate一次收口，交付response_v36。本审阅不授予merge approval。

[独立证据核查](outcomes/records/review_v33_independent_checks.json) · [本次文档验收](outcomes/records/review_v33_documentation_checks.json)。以下V35及此前历史全文保留。

---

# V35最新交付：在线冷启动可信负结果，固定块族收口

本轮首次真实冷启动，用七区局部解处理任意新残差，并由GMRES选择修正组合。代价是每个非零输入八次局部solve和两次传播作用；这是传统块方法，没有神经训练。

| 模型／结果身份 | measured或not_run结果 | 解释／边界 |
|---|---|---|
| .7nm／384hex／p3／q15／18144trace＋40port | 首256步Schur0.20524886351900365>0.01 | ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT，关闭固定七／八块追加预算 |
| 原完整方程 | native/augmented0.07959628543991103、total augmented0.027619862207395922>1e-6 | port/恢复/MPC通过不足以授完整解资格 |
| 费用／同时采样树峰 | actor188.162088667s／2108018688B／ownswap0；834次S/SH、264次PC | shared-workstation，全部aux/探针/旧费用另列，不双加嵌套计时 |
| 原因／范围 | 保存残差平方99.19%在外域；第二周期与FE/REF7 NOT_RUN | 无official R/T/A、NN20%或原尺寸2TB/48h资格 |

[Review V32](review_report_v32.md)／[response](response_v35.md)／[完整结果](outcomes/online_full_input_qualification_v35.md)／[规模桥接](outcomes/original_scale_bridge_v35.md)／[run index](outcomes/records/run_index_v35.json)。

唯一下一建议是匹配外域Schur的周期／层次全局逆接口与容量资格；本轮不实现。历史后缀逐字保留。

<!-- V35-LATEST-END -->

# 最新审阅：Review V32／唯一冷启动在线完整资格

[Review V32](review_report_v32.md)独立重算V34两态保存数组、分区与费用，接受完整输入单位单步的负结果；不授予完整物理解、NN20%或原尺寸资格。[独立审阅证据](outcomes/records/review_v32_independent_checks.json)包含969份文件hash、61份原始包及本次3.666822s缓存审核；没有新PDE或真实因子求解。

V35只授权一个连续工作包：任意RHS的七区B_full固定右PC→零trace GMRES256最多两周期→达原方程门后的独立完整物理验收→原尺寸成本桥接与失败替代分析。首周期Schur≤0.01才可继续第二周期；没有测试后审批，普通bug轮内修复。新在线资格预算900s与已关闭212.190444/600s方向诊断分账，失败消费不清零。禁止追加旧方向、调整scalar-tau、重开旧周期、训练或复制dot求解器。

最终目标仍是原尺寸0.7nm完整3D FEM、2TB/48h；micro通过也不能直接外推。执行窗口通知execution-review-handoff-20261003已收，审阅发布后停止再交接V35；始终只激活一个窗口。以下历史逐字保留，旧“仅只读下一步”建议由最新review替代。

# V34最新交付：完整输入诊断已实测，固定单步提案关闭

按[Review V31](review_report_v31.md)同轮修复、定点复验、真实actor及独立缓存审核全部完成。两态rho_full=2.97739708904112／4.065825954112519，均放大且比七区单位相加对照更差，`FULL_INPUT_FIXED_STEP_INSUFFICIENT`。J内残差消除、六外域放大，block6最终norm最大；是可信传统块方法负结果，非新完整物理解或神经收益。

[response_v34](response_v34.md)／[详细结果](outcomes/full_input_block_correction_v34.md)／[run index](outcomes/records/run_index_v34.json)／[独立checker](outcomes/records/full_input_checker_v34.json)／[原始证据](outcomes/records/raw_evidence_index_v34.json)／[完整费用](outcomes/records/resource_costs_v34.json)。首次11/2失败保留，最小修后13通过；真实sourcefbc5c578…，checker sourcea4cf9c0…，actor仅一次20.032768s。新收费50.984808s、累计212.190444/600s；树采样峰1,019,056,128B/ownswap0/后代清空，全部shared-workstation。

队列closed且不重入；历史V23 0/6／V24 0/5、旧closed和失败不改。NN20% NOT_DEMONSTRATED、原尺寸/2TB/48h NOT_QUALIFIED。唯一下一建议仅只读核对dot不同周期/全局信息传播接口、恢复与全成本，未实施，不改dot或merge。以下旧导航逐字保留；历史停止／等待建议不覆盖本次已完成结论。

# 最新审阅：Review V31／修复后同轮推进真实数值诊断

[Review V31](review_report_v31.md)接受V33真实CPU停止，但独立合成复验为4 passed／2 failed：checker混用新旧残差并强求逐位相等，存储fixture误期望V32累计0B。前者最小修复方向在隔离审阅中通过两态及12个破坏性反例；生产源码未改、正式资格未授予。证据见[独立审阅记录](outcomes/records/review_v31_independent_checks.json)。

V34直接授权修复、定点复验、原两冷态B_full诊断、缓存审核和归因连续执行；普通bug自行修复，暂时资源拒绝进入等待，不再设置测试后或一次拒绝后的新review审批。有限修复重入全部收费；旧closed及失败保留，600s累计预算不增，本次审阅辅助保守计入后carry161.205635980s。仅资源等待日历改为固定24h，数值门和现场资源门不放宽。原尺寸0.7nm／2TB／48h与神经20%仍未资格化。以下历史逐字保留，旧建议不覆盖最新合同。

# V33最新交付：外域直接输入实现，唯一辅助CPU准入拒绝

[Review V30](review_report_v30.md)授权新B_full固定两态诊断，旧V32 B_ret提案保持关闭。新数学／单dat／独立缓存checker和合成接线已提交；最终source a874498a1a8b854f394520627eaf09158b77fbf9只有16 Python静态编译／符号检查通过。前测唯一fresh准入在48候选CPU均被原忙碌／亲和性／SMT规则排除后拒绝，worker0，真实两态和checker NOT_RUN；RESOURCE_STOP不冒称机制负结果。

[response_v33](response_v33.md)／[详细交付](outcomes/full_input_block_correction_v33.md)／[run index](outcomes/records/run_index_v33.json)／[原始准入](outcomes/records/raw_evidence_index_v33.json)／[费用](outcomes/records/resource_costs_v33.json)。累计监督151.4889468078036s不清零；probe1.240283s计总elapsed。dot14项身份缺口和NN20%必要条件已完成，未等待或修改dot。账本closed／active=null，数值及原尺寸资格不提升；只建议先独立验收冻结合成可信链，随后任何真实诊断需新授权窗口。以下历史逐字保留。

# 最新审阅：Review V30／接受V32负结果，执行外域输入补齐诊断

[Review V30](review_report_v30.md)接受V32两冷态真实回流的弱增益结论，关闭B_ret固定方向。V33新授权一次B_full外域直接残差入口诊断：复用六块已保存响应，只重载J一套因子，直接核验单位系数完整残差，不增加第11方向拟合或旧迭代。普通软件／测试错误同轮修复、定点复验后继续，不以等待dot作为全部后续工作。

[独立证据](outcomes/records/review_v30_independent_checks.json)核对159个文件hash、原12项测试及三阶段资源／准入记录；本次缓存数值复验因CPU准入拒绝未启动，未冒称重新验证数组。V27起累计151.488946808s不清零；原尺寸0.7nm／2TB／48h与神经20%仍未资格化。以下历史逐字保留，旧停止建议不覆盖最新合同。

# V32：真实回流诊断已完成，固定提案关闭

[Review V29](review_report_v29.md)／[response_v32](response_v32.md)／[详细结果](outcomes/return_direction_execution_v32.md)／[run index](outcomes/records/run_index_v32.json)。统一存储计数与V32独立准入、12 targeted通过后，一次原两冷态actor完成，独立checker CHECKED。eta10为0.9648437480／0.9807007112，g10为0.9985906129／0.9987090025；创新可分辨但仅再降低e9范数0.14094%／0.12910%，按预登记关闭固定回流序列。

source1fe058e3…；actor83.140185s、辅助15.668586s、V27起累计151.488947s，树采样峰1,247,059,968B／自身swap0，closed且后代清空。后审核首次存储预留停止后仅清理未引用bytecode、同门限另ID通过，没有重跑actor。无新FE／NN训练／完整物理解；旧0/5、0/6和NN20%／原尺寸未资格化保持。以下历史逐字保留，不授权下一实验。

# 最新审阅：Review V29／同轮修复复验后推进真实诊断

[Review V29](review_report_v29.md)接受V31合成study接线；本次独立定点复验已修复的拒绝fixture，1 passed，关闭该软件缺口。按用户新指令替换“一次前测错误即等待review”：V32应在同一窗口和累计预算内定位、修复、定点复验并继续一次原两冷态真实回流诊断，不以测试准备完成作为交付终点。存储守卫漏计路径也在同轮直接修复。

[独立证据](outcomes/records/review_v29_independent_checks.json)核对69个文件hash及原109通过／1失败，历史不倒填。累计有载52.680176060s不清零，原尺寸0.7nm／2TB／48h和NN20%仍未资格化；旧closed与数学门限保持。以下历史逐字保留，旧停止建议不覆盖最新合同。

# V31最新交付：真实接线通过，前测fixture错误停止正式运行

[Review V28](review_report_v28.md)／[Response V31](response_v31.md)／[详细结果](outcomes/return_direction_workflow_v31.md)／[run index](outcomes/records/run_index_v31.json)。relative导入与V31独立namespace已实现，实际study→保存→结算→collector合成测试通过；唯一前测整体109 passed／1 failed，新拒绝fixture缺窗口接口。已最小补齐但修后runtime NOT_RUN；依合同停止，不作正式准入或actor／后checker。监督12.731163s、累计52.680176s、树RSS254,758,912B／ownswap0；真实S/SH/reader/FE/训练0，eta10/g10未运行。旧负结果与closed历史不变，NN20%及原尺寸资格未获得。以下历史逐字保留。

# 最新审阅：Review V28／准备通过，真实回流有条件解锁

[Review V28](review_report_v28.md)接受V30轻量入口及合成审核资格，关闭上一轮两项缺陷。真实study另有未导入`relative`的旧接线问题；V31先修复并验证实际工作流，再在fresh准入和累计预算内只做一次原两冷态、V26九方向基线的回流诊断。不得直接启动旧dat、重开closed窗口或追加迭代／训练。

[独立证据](outcomes/records/review_v28_independent_checks.json)核对84个文件hash、162项原始测试及资源记录；本次没有新真实数值运行。原尺寸0.7nm／2TB／48h与神经20%仍未资格化。以下历史逐字保留，旧建议不覆盖最新合同。

# V30最新交付：轻量入口与合成审核已资格化

[Review V27](review_report_v27.md)／[Response V30](response_v30.md)／[详细结果](outcomes/light_entry_acceptance_v30.md)／[run index](outcomes/records/run_index_v30.json)。重复keyword、输出目录和负例误报已修复；source `1a18f520dae3ecd702a1369b0d9241ec3e81802a`上22文件编译、最小7及完整162测试通过，完整轻量入口exit0，CPU缓存重算／固定三小矩阵／成本账已执行。监督18.785167s、累计39.949013s，真实actor／S+SH／reader／FE／训练0。这里只资格化软件入口与合成checker，非真实方向／物理解／NN20%或原尺寸资格；清场等待review。以下历史逐字保留，V26–V29 closed不变。

# 最新审阅：Review V27／修复轻量入口与测试误报

[Review V27](review_report_v27.md)接受V29一次CPU准入停止。独立审阅发现轻量入口重复keyword导致编译失败；相关测试147通过、8失败，32个负例曾被目录错误掩盖。临时目录补齐后的checker反例及三种小矩阵验证有效，但不能代替原样入口资格。V30只修这两项并完成一次有界轻量验收，不启动真实回流、PDE或训练。

[独立证据](outcomes/records/review_v27_independent_checks.json)保存原日志、hash、冻结快照和隔离复核；原尺寸0.7nm／2TB／48h与NN20%仍未资格化。以下历史逐字保留，旧建议不覆盖最新合同。

# V29最新交付：审核链实现完成，唯一辅助准入拒绝

[Review V26](review_report_v26.md)／[Response V29](response_v29.md)／[A/B/C详细记录](outcomes/checker_full_space_cost_v29.md)／[准入证据](outcomes/records/admission_stop_v29.json)／[run index](outcomes/records/run_index_v29.json)。新checker及全链合成fixture已提交，但唯一辅助CPU准入在worker前拒绝，新测试／小矩阵／缓存分析均NOT_RUN。只完成冻结表转录、纸面代数及成本必要条件，不授予checker或求解资格。V27/V28 closed，actor0／S+SH0／reader0，不重试、无NN训练／真实全空间补项。等待review，神经20%及原尺寸资格均未获得。以下历史逐字保留。

# 最新审阅：Review V26／V29轻量工作包

[Review V26](review_report_v26.md)接受V28辅助CPU准入停止，父指针和失败快照问题关闭；独立复跑100项通过，但新反例表明checker仍漏查完整消费及回流向量。下一轮只执行审核修复、全空间补项的小矩阵代数验证和神经20%完整成本分析；不重开V27/V28真实actor，不训练、不延长旧迭代。

[独立核验记录](outcomes/records/review_v26_independent_checks.json)包含原始hash、冻结准入重算和反例。原尺寸0.7nm／2TB／48h及NN20%资格仍未获得。以下历史逐字保留，旧建议不覆盖最新合同。

# V28最新交付：checker／parent／准入证据完成，CPU Gate停止

[Review V25](review_report_v25.md)／[Response V28](response_v28.md)／[详细结果](outcomes/return_direction_v28.md)／[独立checker](outcomes/records/return_direction_checker_v28.json)／[准入快照重算](outcomes/records/admission_checker_v28.json)／[raw index](outcomes/records/run_index_v28.json)。100项相关回归、compileall与dat验证通过；第二辅助准入失败后停止，正式准入0／actor0／S+SH0／reader0。两态回流NOT_RUN，不将资源停止写成数值负结果；V27 closed保持，新记录纠正旧null父指针。累计有载21.163846770s，NN20%及原尺寸资格未获得。等待审阅，不自动重入。以下历史完整保留。

# 最新审阅：Review V25／接受V27零消费停止

[Review V25](review_report_v25.md)接受V27的CPU准入停止，关闭真实窗口测试依赖问题；本次67项相关测试通过。真实回流方向仍未运行，不能称数值负结果。

V28先补齐独立数值checker、非空parent映射及可重算的准入记录，再仅作一次新的正式准入；通过才执行原两冷态、相对九方向基线的唯一回流诊断。V27窗口保持closed；两轮actor和受监督辅助合计仍限600秒，旧12.366657368秒不清零。禁止新LU、迭代延长、训练或参数扫描。

[独立核验记录](outcomes/records/review_v25_independent_checks.json)保留hash、零消费推导、辅助CPU候选重算和记录缺口。原尺寸0.7nm／2TB／48小时及神经20%均未资格化，无merge approval。下方历史逐字保留，不覆盖最新合同。

# Task042 V27：修复测试后，回流诊断因CPU准入未运行

固定J→外域→J只计划检验九个历史方向之外的一个方向，没有改变有限元方程。67项pure回归、compileall及新dat验证通过；正式入口未找到合格空闲物理核，已用完允许的一次只读复核，actor前以NOT_RUN_CPU_ADMISSION收口。两冷态eta10/g10均NOT_RUN，不把资源停止改成方向失败。

| 数据身份／完成项 | 结果与具体边界 |
|---|---|
| 测试窗口修复／measured | 旧42scope+4拒绝+21新回流fixture=67通过；V26真实窗口仍closed，不重开、不重算 |
| 唯一正式入口／not_run | source7b0e03f2fbfb504b13a5f5b4c46c52e0e96a5eb9已clean；actor0/S+SH0/reader0/新LU0，数值资格未测试 |
| 两冷态历史基线 | LZ4 eta9=.966205505618、LCZ4 .981968429990；本轮回流抵消/创新/eta10/g10无实测 |
| shared-workstation成本／measured | 辅助12.366657368s、采样整树峰134,275,072B、ownswap/VRAM0；总window自02:14:16.872215Z不刷新，准入读取独立费用unknown计总wall |
| 原方程／NN | 新完整场资格NOT_RUN；V24 0/5、V23 0/6保持；无NN训练或合格配对，20%收益NOT_DEMONSTRATED |
| 因子及容量／边界 | 原七bundle实际未读；计划rank≤3888<18144，不可独立全空间右PC；derived4,807,239,744B非RSS，不声称factor-free |
| 停止／下一步 | CPU准入额度耗尽，ledger closed/active null；仅建议下一review判断是否重新授权未消费诊断，当前不重入，无merge approval |

[Response V27](response_v27.md)／[详细记录](outcomes/return_direction_v27.md)／[成本](outcomes/records/resource_costs_v27.json)／[原始索引](outcomes/records/run_index_v27.json)。GitHub视觉NOT_VERIFIED，本地静态另查。以下历史逐字保留，旧建议不授权本轮继续。

# 最新审阅：Review V24／V26负结果已接受

[Review V24](review_report_v24.md)接受V26有限负结果，关闭上一轮样本库存缺口；本次42项相关测试为41通过、1失败，需修复测试对真实已关闭窗口的依赖。联合块的新方向可分辨，但对旧八方向残差仅额外降低1.7322%／0.8037%，停止这一固定联合方向提案。

V27只授权先修测试，再做一个固定J→外域→J回流方向、两份既有冷终态的离线诊断，以**V26九方向**为基线；无新LU、无迭代、无训练，总elapsed上限90分钟。该回流算子秩至多3888，不能独立当作全空间右预条件器。正信号也必须收口等待review。

[独立核验记录](outcomes/records/review_v24_independent_checks.json)保存hash、缓存重算、失败日志及复现脚本。V24完整资格仍0/5、V23仍0/6；原尺寸0.7nm／2TB／48小时及NN20%均未资格化，无merge approval。下方历史逐字保留，旧下一建议不覆盖最新review。

# Task042 V26：联合新方向可信但增量不足

**V26已完成，数值资格通过，预登记决策为 `FIXED_JOINT_DIRECTION_INSUFFICIENT`。** 两终态g均≥0.95，未达到两者g≤0.75的继续研究信号。关闭本固定5／7联合方向提案，不新启动迭代、另一块对或训练。它产生了可分辨的新方向，但不能显著消除旧八方向留下的残差；不是新的有限元解，也不否定所有接口／神经方法。

把两个相邻局部块一起解，是让一次局部解考虑它们之间的双向耦合。本批把这个新向量的原方程响应，加入已有八个向量的响应集合，只检查多出的方向是否有用。代价是一套更大的稠密矩阵／LU、一次只读重载与有界原作用；不把诊断向量作为部署PC或求解终态。

eta8／eta9是修正后原trace残差范数除以各自当前残差范数；g比较加入新方向前后剩余残差，分母不是物理b或参考场。范数下降与平方范数消除分别列出，均为measured／derived offline diagnostic。

| 固定已消费冷终态 | eta8 | eta9 | g=eta9/eta8 | 相对e8范数下降 | 相对e8平方范数消除 | rank |
|---|---:|---:|---:|---:|---:|---:|
| V24-LZ-CYCLE4 | 0.983236989810 | 0.966205505618 | 0.982678149451 | 1.732185% | 3.434365% | 9 |
| V24-LCZ-CYCLE4 | 0.989924628585 | 0.981968429990 | 0.991962823870 | 0.803718% | 1.600976% | 9 |


两个状态不是fresh终测，均为V24已消费冷末态。旧V25数值和原始记录不改；本批没有调用REF7、teacher、NN权重、旧p1 T/U/R、D_L或Krylov库存。
实际source `652cb206cd1ebeb1c4182ac2300c1dc23c57b48f`，actor33.262622s、采样峰1,625,231,360B、ownswap/VRAM0；S14/SH2、唯一joint LU1、solve9/显式pass18/gecon保守22；JOINT_5_7_DENSE_LU_PRESENT，无旧八LU读取。没有新物理解/参考/NN；神经20%仍未证实。

唯一建议是另审“外域已有块处理泄漏后回到J补偿”的固定回流方向资格，不扩大块、不启动迭代。[回应](response_v26.md)／[详细结果](outcomes/joint_block_direction_v26.md)／[run index](outcomes/records/run_index_v26.json)／[费用](outcomes/records/resource_costs_v26.json)。以下原历史逐字保留，旧下一步不授权重跑。

# 最新审阅：Review V23／V25弱方向证据已接受

[Review V23](review_report_v23.md)关闭六场／四功率库存修复，接受V25两冷终态的八方向弱增量结论；旧V24完整资格仍0/5。下一轮V26仅补齐诊断样本库存，再对固定块5／7的一套联合主块、两个保存终态做新增方向资格诊断，总elapsed上限2小时；不续旧迭代、不训练NN。

[独立核验记录](outcomes/records/review_v23_independent_checks.json)包含原始hash、缓存重算和空／缺／重复样本反例。原尺寸0.7nm／2TB／48小时与NN20%尚未资格化，无merge approval。以下历史原文保留，旧“下一建议”不覆盖最新review。

# 最新交付：V25／Review V22已执行

[V25回应](response_v25.md)及[三残差八方向结果](outcomes/block_residual_direction_diagnostic_v25.md)：checker必需库存修复，93 focused通过；V24仍0/5。两个末态eta8=0.9832369898／0.9899246286，数值可信但当前八方向削减能力弱，无新物理解或NN20%收益。25.665227s actor、S39、整树峰约1.707GiB、ownswap0，已冻结清场，等待review。

仅建议下一review的一项块5/7跨界面联合方向容量／资格检查，尚未实施。下方全部历史导航保留，不批准继续V24、旧空间或训练。

# 最新审阅：Review V22／V24结果已复核

[Review V22](review_report_v22.md)接受V24有界负结果，完整资格仍为0/5；review v21两项控制流修复关闭。后续只按v22执行checker完整性修复及三份保存残差的八块方向诊断，V25总预算90分钟；不继续旧周期、不训练网络。原尺寸0.7nm／2TB／48小时、神经20%和合并资格仍未取得。

[独立核验记录](outcomes/records/review_v22_independent_checks.json)含源码身份、原始hash复核和checker反例。以下V24结果和历次导航原文保留；旧“下一建议”不覆盖最新review。

# Task042 V24最新收口：对称首块与唯一审核完成

四条首块及唯一冻结审核已完成，完整同离散资格0/5。资格由原方程、场、端口及逐通道功率共同决定；单项native通过或残差降低不能替代完整资格。神经20%增量独立记NOT_DEMONSTRATED：本批无隐藏层训练，也没有最佳合格非神经同精度／完整端到端成本的配对性能证据。

本批用八个固定几何区域中的完整局部解来修正残差，再比较追加既有低阶作用像校正的效果。局部解考虑同组未知量的耦合；组合解在局部修正后再处理粗空间能够消除的部分。原有限元方程、跨块耦合、内部恢复和全部40端口保持，代价是八块稠密LU、每次八个局部解及组合路线额外的原作用和全局薄矩阵乘法。

| 路线／起点 | 周期 | Schur（≤1e-6） | native（≤1e-6） | 散射E差（≤1e-4） | 最大通道功率差（≤1e-6） | 完整资格 |
|---|---:|---:|---:|---:|---:|---|
| V21-C-FINAL | 历史暖点 | 2.528117033e-06 | 9.804133464e-07 | 7.816080389e-05 | 1.719644651e-06 | FAIL |
| LW-FINAL | 4 | 2.502117907e-06 | 9.703307865e-07 | 7.778607315e-05 | 1.666968717e-06 | FAIL |
| LCW-FINAL | 4 | 2.524169303e-06 | 9.788824018e-07 | 7.808877891e-05 | 1.708820964e-06 | FAIL |
| LZ-FINAL | 4 | 0.0813766679 | 0.03155817955 | 0.5688882779 | 0.007245973616 | FAIL |
| LCZ-FINAL | 4 | 0.3252622227 | 0.12613792 | 0.8368884535 | 0.007757579435 | FAIL |

| 状态；全部为未资格诊断 | R00_s | R00_p | R_total | T_total | A_balance | A_volume | 能量误差 |
|---|---:|---:|---:|---:|---:|---:|---:|
| LW-FINAL | 0.1176449645 | 6.952925802e-13 | 0.1176460215 | 0.8770494499 | 0.005304528605 | 0.005306406598 | 1.877993788e-06 |
| LCW-FINAL | 0.1176449706 | 7.011877452e-13 | 0.1176460275 | 0.8770494918 | 0.005304480711 | 0.005306406825 | 1.92611376e-06 |
| LZ-FINAL | 0.1104079944 | 3.889963505e-12 | 0.1104090388 | 0.8698018277 | 0.01978913352 | 0.005272352662 | 0.01451678086 |
| LCZ-FINAL | 0.109887183 | 1.728616029e-09 | 0.109900937 | 0.8797669468 | 0.01033211621 | 0.005293212092 | 0.005038904117 |

固定Full3D/p3/h0.175nm/q15/MPI1：384hex、storage34050、trace18144、internal13824、slave2082、40通道；fine全局NNZ未构造。正式wall1977.711696s、整树采样峰2782064640B、自身swap/VRAM0；分阶段成本与hash均见本轮回应及records。

唯一下一建议：以本批已保存的零初值残差为输入，预登记一次有界的块内／跨块耦合作用分账，判断下一种局部通信机制需要补足的方向及容量；不立即改变块数、重叠、粗空间或追加求解。

[本轮回应](response_v24.md)。以下历史原文逐字保留；其中“当前”仅指记录当时。

# V24续行记录：账户接口及执行审批已恢复

2026-10-02T14:07Z之后实际只读主机核验通过：新候选核CPU15、PSI full avg10=0、原系统/邻增长余量和磁盘Gate通过。周额度用尽时允许使用现有余额；明确禁止使用重置卡，未调用重置功能。以下认证阻塞是早先真实历史，保留原始失败；本批现继续原Review V21队列，原heavy-stop15:34:23.502588Z、deadline16:04:23.502588Z保持。当前真实数值仍未运行，后续来源与计数由正式run绑定。

# 最新导航：V24 / Review V21：实现已提交，正式数值执行受认证阻塞

本轮已实现固定八块局部完整LU与同规格粗层配对的数值核、角色reader、有限队列和六个one-run入口。最终小模型定向回归28 passed，六入口均validate；正式SETUP和LW/LCW/LZ/LCZ/VERIFY均NOT_RUN。首次队列未通过空闲物理核准入，数值actor未创建；有界复核找到核后，启动重试因自动审批服务令牌刷新403而未执行。这不是方法的数值负结果；没有新的原方程/场/功率资格或神经增量。

[正式Review](review_report_v21.md)、[本地待提交Response](response_v24.md)、[结果](outcomes/local_block_coarse_pair_v24.md)、[分流](outcomes/records/qualification_and_dispatch_v24.json)、[源码/入口](outcomes/records/run_index_v24.json)、[审批故障](outcomes/records/approval_block_v24.json)。没有正式actor，旧导航不授权重跑历史campaign。

唯一下一建议：恢复Codex客户端认证后，原窗口仍有效且fresh资源准入通过时继续已验证的原队列；窗口耗尽则等待下一review明确新的时间窗口，不扩大数值范围。
以下历史正文逐字保留；旧“当前”只指其当时阶段。

# 最新导航：V23 / Review V20 已收口

[Review](review_report_v20.md)、[Response](response_v23.md)、[结果](outcomes/p1_image_minres_comparison_v23.md)、[Gate](outcomes/records/qualification_and_dispatch_v23.json)、[source/run](outcomes/records/run_index_v23.json)。S/D/M/Z/V完成，六状态0/6完整资格；同T原作用像QR可信但未突破暖平台，零trace散射未求出。数值已清场等待review，不merge。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# 最新导航：V22 / Review V19 已收口

[Review](review_report_v19.md)、[Response](response_v22.md)、[结果](outcomes/p1_trace_galerkin_correction_v22.md)、[Gate](outcomes/records/qualification_and_dispatch_v22.json)、[run/source](outcomes/records/run_index_v22.json)。S/N/P/Z/V完成，T未准入；粗层资格通过，0/3新候选原方程与完整物理通过。队列已清场，等待review；旧阶段只作历史，不merge。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# 最新导航：V21 / Review V18 已收口

[Review](review_report_v18.md)、[Response](response_v21.md)、[详细结果](outcomes/exact_action_recycled_correction_v21.md)、[Gate](outcomes/records/qualification_and_dispatch_v21.json)、[run/source](outcomes/records/run_index_v21.json)、[费用](outcomes/records/resource_costs_v21.json)。D0/A/B/C/V已执行，条件T/Z按原进展准入。数值队列清场后等待review，不能依旧导航继续旧实验；不merge。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# 最新导航：V20 / Review V17 已收口

[Review V17](review_report_v17.md)、[Response V20](response_v20.md)、[结果](outcomes/fixed_p3_ilu0_port_v20.md)、[原Gate](outcomes/records/qualification_and_dispatch_v20.json)、[source/run](outcomes/records/run_index_v20.json)、[费用](outcomes/records/resource_costs_v20.json)。S0/N/P0/P40/V已实际完成，0/5资格；T/C未准入。正式数值清场于窗口内，总elapsed交付超限单列。等待review，不merge。

以下历史正文保留，旧“当前”仅指其当时阶段。

# 最新导航：V19 / Review V16 已收口

[Review V16](review_report_v16.md)、[Response V19](response_v19.md)、[完整结果](outcomes/post_lsqr_residual_polish_v19.md)、[原Gate](outcomes/records/qualification_and_dispatch_v19.json)、[run/source](outcomes/records/run_index_v19.json)、[费用](outcomes/records/resource_costs_v19.json)。C0/P/L/VERIFY已实际执行，完整0/8资格；数值队列退出，当前仅等待review，不merge。下方“当前/待运行”是历史，不能继续旧campaign。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# 最新导航：V18 / Review V15 已完成

[Review V15](review_report_v15.md)、[Response V18](response_v18.md)、[完整结果](outcomes/gmres_repair_residual_completion_v18.md)、[独立Gate](outcomes/records/qualification_and_dispatch_v18.json)、[source/run index](outcomes/records/run_index_v18.json)、[费用](outcomes/records/resource_costs_v18.json)。F0/G64/G256/R/VERIFY均已实际执行，8冻结状态0合格；数值队列已退出，等待review，不merge。下方所有旧“当前/待运行”只是历史，不授权继续旧campaign。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# 当前导航：V17可恢复全空间续算已完成

最新合同为[Review V14](review_report_v14.md)，执行结果[Response V17](response_v17.md)、[完整证据](outcomes/resumable_full_trace_campaign_v17.md)、[run index](outcomes/records/run_index_v17.json)。旧版本导航仅为历史，不构成继续运行授权；当前清场等待review，不merge。
以下历史正文逐字保留；旧版本的“当前”只指其当时阶段。

# 最新执行导航：V16 / Review V13

本批为原有限元全空间校正，固定随机神经／多项式基只作辅助。三路线均实际启动，GPOLY/GNN资源中断、终态证据缺失；一次独立FE验证已收口；完整资格0/6。先读[Response V16](response_v16.md)、[正式Review V13](review_report_v13.md)、[完整结果](outcomes/augmented_full_trace_lsqr_v16.md)、[run/source](outcomes/records/run_index_v16.json)与[费用](outcomes/records/resource_costs_v16.json)。

五项one-run dat位于input/task042_neural_coarse_inverse/v16_*.dat，均显式opt-in；本轮已执行项不能在新的review前自行重跑。以下旧导航／初始化命令为历史，现工作树已正确登记于canonical common git。

# 当前入口：V15局部表示配对已完成

最新正式合同[Review V12](review_report_v12.md)，回应[Response V15](response_v15.md)，[结果](outcomes/local_trace_representation_v15.md)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index_v15.json)。六个规定V15 dat已实现并实际执行；局部1544/组合3098、8状态0合格，多项式组合更好，无神经训练增量。旧p4路线关闭；全部有限队列已完成，等待review。以下“当前/最新”和初始化命令都是保留历史，不是待执行步骤。

# 当前入口：V14正交trace与有限hidden位置重求

最新正式执行合同：[Review V11](review_report_v11.md)；本轮已完成：[Response V14](response_v14.md)、[方法与结果](outcomes/orthonormal_trace_reprofile_v14.md)、[统一summary](outcomes/summary.md)、[raw Gate/分流](outcomes/records/qualification_and_dispatch_v14.json)、[run index](outcomes/records/run_index_v14.json)。新家族ORTHONORMAL_NEURAL_FE_BASIS，6固定+2有界新点、独立10状态，decoder合格但物理全部失败；等待review。下方旧最新导航/初始化命令为历史，不需要再执行Git准备或旧campaign。


# 当前 V13 交付导航

[Review V10](review_report_v10.md)是本批正式合同；[Response V13](response_v13.md)、[切向／响应／联合补偿结果](outcomes/tangent_scale_head_compensation_v13.md)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index_v13.json)为最新入口。三个固定头切向通过新向量Gate；B收益不可分辨后继续C，两个合格联合方向实际接受1步，J相对改善仅7.149e-7，按门限不再继续。独立一次FE验证3个冻结状态，原Schur约0.798、native约0.309、散射误差约0.734，仍不合格。旧V11头1e-8、V12标量FD及全部负结果保留，不称精确VarPro或神经求解成功。一次末尾JSON错误仅恢复已保存证据，实际候选source与恢复source分列。

四个规定V13入口均已实现并经 `scripts/run_case.py` 实际one-run；有限Taylor复核及记录恢复各有显式独立dat，不表示无限重执行。求解／验证队列已经冻结，无新p4参考、GPU、最大模型或merge；等待review。以下V12及更早“当前／最新”全部是保留的历史导航，不能作为新的待执行合同。

# 当前 V12 交付导航

[Review V9](review_report_v9.md)授权固定头真实残差偏导及有界隐藏更新，明确不要求旧 V11 输出头先过 `1e-8` 驻点 Gate。[Response V12](response_v12.md)、[完整负结果](outcomes/actual_loss_block_descent_v12.md)、[最新 summary](outcomes/summary.md)、[run index](outcomes/records/run_index_v12.json)为本批入口。T1 对 M2/物理残差完成分账；T2 的实际三方向 FD 未出现规定稳定区，故 T3 不运行；有限 F 八次试探均使损失升高，接受隐藏步0、头建议0。T4 独立确认原方程和散射场仍失败。旧 M2/实际头内部门限与全部原结果保留，p4 强逆关闭、最终0.7nm／48小时未合格；只推送本执行分支待 review，不合并 master。以下 V11 与更早“当前”是历史导航原文。

# V11 历史交付导航

[Review V8](review_report_v8.md)是本轮正式合同；[Response V11](response_v11.md)、[完整结果](outcomes/stable_head_varpro_v11.md)、[最新summary](outcomes/summary.md)和[run index](outcomes/records/run_index_v11.json)为当前交付。原0.7 nm／384hex／p3／40端口保持；小系数制造问题通过，大系数在一次同分解修正后仍未过1e-8，实际稳定头的物理残差一致性亦未过1e-8。真实隐藏参数更新0次，独立FE场及原方程仍失败；旧p4路线关闭，最终目标未合格。下方带“当前／最新”的V7/V8及初始说明均是**历史原文**，不代表当前合同或状态。

# 当前 V8 交付导航

[Response V8](response_v8.md)、[尺度与执行对照](outcomes/scaling_and_execution_v8.md)、[最新summary](outcomes/summary.md)。列尺度负结果、batch等价与共享微基准成本正信号分别记录；旧p4路线关闭，不自动长训练／p6／大目标。Review V5为本轮合同，原文及以下历史导航保留。

# V7 当前入口：材料已授权，继续神经FE单次求解

最新执行合同为 [Review V4](review_report_v4.md)，数值方法／精度／资源沿用 [Review V3](review_report_v3.md)。0.7／2nm用户原值已固化，5／13.5nm旧输入核验值同表保存；唯一canonical材料为 [si_optical_constants_v1.json](../../input/materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`。nominal0.7使用source标签0.699999988原行，不插值；外部数据库元数据缺失不再阻塞。

本批 `V7_MATERIAL_FIXED_NEURAL_FE_CONTINUATION` 在已有384-cell/p3三维缺口几何上续跑真实S/Sᴴ、完整上下端口和恢复；真实N1通过后顺序NEURAL-TRACE／FREE-FE-OPT／FE-LSQR，再按条件独立验证。旧p4路线关闭，旧teacher／seed420620封存；不做四波长扫描、不启动最终规模。累计10小时预算包含V6已有费用，各路线仍最多2小时／2000完整closure或算子配对。Git、受控共享CPU、独立环境／缓存、自有锁和16/12GiB树监督继续；无合并授权。

本批已实际完成材料固化、真实N1、三条路线和独立p3盲验证。三候选全部未通过原方程／同离散场／功率Gate，p4 enrichment未准入；材料不再阻塞，最终目标仍未资格化。见 [Response V7](response_v7.md)、[完整结果](outcomes/neural_fe_single_solve_v7.md)、[summary](outcomes/summary.md)。只有等待review的一个最小建议，未启动最大模型或旧p4路线。

所有正式运行使用独立V7 one-run dat，经 `scripts/run_case.py`；唯一参考后处理错误只修复范数表达式、复用原参考重放验证，没有重分解或训练。源码／输入／模型／数据hash与全部费用见 [run index](outcomes/records/run_index_v7.json)、[resource costs](outcomes/records/resource_costs_v7.json)。

以下首次创建说明仅为历史，不代表当前状态，原文保留。

# Task042：NN-Lab 入口

唯一初始执行合同是 [task.md](task.md)。本目录目前只有任务文档，没有新实现、训练、PDE或性能结果。后续review、response、outcomes均留在同一分支。

| 项目 | 值 |
|---|---|
| 执行分支 | `task42_neural_coarse_inverse` |
| 冻结base | `ccd357885f7f9be84efe3be07868cc94f13d93fc`，来自`task39extra_para_workstation_capacity` |
| 本机工作树 | `/home/fenics/Projects/NN-Lab`，目录本身即仓库根 |
| 首轮问题 | 神经辅助低内存p4迭代粗逆；不是直接代理完整Maxwell场或R/T/A |
| 顺序 | 隔离与轻测试 → 单一13.5 nm小FE → teacher/可表达性oracle → 线性与NN → 严格粗逆 → 条件p6嵌入 |
| 正确性 | 原A4粗返回1e-10；条件p6原A6残差1e-6和完整物理/场检查 |
| 部署边界 | 候选不构造global p4 LU；teacher/参考进程单独运行和释放 |
| 资源 | 一次一项heavy；Task042空闲窗口RSS<=16 GiB，训练单GPU<=8 GiB |
| 当前状态 | `PLANNED_NOT_RUN`；现场环境与资源尚未核验 |
| 首轮交付 | 本目录`response_v1.md`与`outcomes/`，由Codex实际执行后写入 |
| 合并 | `NOT_APPROVED` |

## Linux命令行准备

以下命令由用户在已经登录远程工作站的Linux终端执行。`mkdir`只建目录，`git fetch`下载本分支对象，`git worktree add`将该分支检出到独立目录；不是在旧运行目录切分支。canonical Git路径来自已有工作站交接，脚本会先核对存在及origin；不满足时停止，不自动clone到另一个不登记的仓库。

先建目录：

```bash
mkdir -p /home/fenics/Projects/NN-Lab
ls -ld /home/fenics/Projects/NN-Lab
```

再执行整个括号块。它仅适合第一次初始化；目录非空或本地分支已存在时会停止，禁止为了重试使用rm/reset/--force。

```bash
(
  set -euo pipefail
  REPO=/home/fenics/Projects/Maxwell3D-Lab/task-repository.git
  TARGET=/home/fenics/Projects/NN-Lab
  BRANCH=task42_neural_coarse_inverse

  test -d "$REPO" || { echo 'STOP: canonical Git目录不存在，请核对原工作站记录。'; exit 1; }
  test -d "$TARGET" || { echo 'STOP: 请先创建NN-Lab目录。'; exit 1; }
  test ! -L "$TARGET" || { echo 'STOP: NN-Lab不能是指向旧任务的符号链接。'; exit 1; }
  ORIGIN=$(git --git-dir="$REPO" remote get-url origin)
  case "$ORIGIN" in
    https://github.com/Rookie1234567/MyFEniCS|https://github.com/Rookie1234567/MyFEniCS.git|git@github.com:Rookie1234567/MyFEniCS|git@github.com:Rookie1234567/MyFEniCS.git)
      ;;
    *) echo 'STOP: origin与预期仓库不一致，请人工核对，不修改origin。'; exit 1 ;;
  esac
  if [ -n "$(find "$TARGET" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo 'STOP: NN-Lab非空，不覆盖。'; exit 1
  fi
  if git --git-dir="$REPO" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    echo 'STOP: 本地分支已存在，请先检查worktree list，不重复创建。'
    git --git-dir="$REPO" worktree list
    exit 1
  fi

  git --git-dir="$REPO" -c gc.auto=0 fetch \
    --no-auto-maintenance --no-write-fetch-head --no-tags origin \
    "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  git --git-dir="$REPO" worktree add --track -b "$BRANCH" \
    "$TARGET" "refs/remotes/origin/$BRANCH"

  git -C "$TARGET" status --short --branch
  git -C "$TARGET" rev-parse HEAD
  git -C "$TARGET" rev-parse --abbrev-ref '@{upstream}'
  git --git-dir="$REPO" worktree list
)
```

成功后再进入新目录：

```bash
cd /home/fenics/Projects/NN-Lab
pwd
git branch --show-current
sed -n '1,100p' docs/task042_neural_coarse_inverse/task.md
```

应显示分支`task42_neural_coarse_inverse`、upstream `origin/task42_neural_coarse_inverse`。linked worktree中`.git`是指向common Git登记的文件，这是正常结构，不要把旧目录的`.git`或`.venv`复制进来。Git历史/refs共享，不等于工作文件、Python环境、缓存和运行资源共享；环境与资源隔离继续按task执行。

认证提示由用户自己在终端处理，不向聊天粘贴密码/私钥/token。Codex执行网络操作前使用非交互认证检查；失败应报告而不是静默卡住。不需要sudo，不改全局Git配置，不在原任务目录pull/checkout。

## 发给Codex的执行要点

在NN-Lab打开新会话，读取根/目录AGENTS、仓库原则、本README及完整task.md。先F0；若原2 nm或其他heavy运行，只做允许的轻量工作并以`WAITING_FOR_SHARED_WORKSTATION`交付，不能因此改旧watchdog或抢占硬件。资源空闲且各Gate通过后可顺序完成获授权阶段，不逐小步等待确认，不越过真实精度/资源失败。

只提交推送`task42_neural_coarse_inverse`。第一轮结束报告精确HEAD、source/输入/模型身份、无global p4因子证据、线性/NN对照、真实残差、全过程RSS/VRAM/时间及未运行项；不把目录/分支创建等同于环境已隔离或神经方案已通过。


## V9 最新有限批次入口

[Review V6](review_report_v6.md)授权固定误差定位；[Response V9](response_v9.md)及[完整结果](outcomes/frozen_error_localization_v9.md)为本轮交付。六状态齐次恢复/物理区域/原方程作用核验完成，没有新求解、训练、PC或loss变更。旧p4路线关闭，V7/V8负结果保留；后续建议等待review，未自动执行。


## V10 最新自主批次入口

[Review V7](review_report_v7.md)授权单个七小时窗口的原方程幅相／端口、固定隐藏线性头与随机特征对照，明确覆盖旧只诊断与仅本任务heavy独占限制。[Response V10](response_v10.md)、[完整结果](outcomes/autonomous_neural_head_v10.md)为本轮交付。A/B1/B0/C及D1/D2已完成，四候选均严格负结果，E/P条件未满足；全部可执行路径结束后提前收口，不重复计算填满窗口。旧p4路线关闭，历史与普通default不改；下一制造RHS建议仅提议未执行，推送后等待review，不merge。
