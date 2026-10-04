# V46最小测试及边界

26项标量费用/身份/配置回归（pure24通过、ML专用1跳过并隔离单独通过），Ruff/compile、15文档合同见[tests_v46](records/tests_v46.json)。实际timing方法使用纯标量mock，完整合成合同PASS只证明消费软件；全五路线0/8与真实q0合同拒绝也已端到端执行。初始style失败和费用保留，未重跑62旧学习测试、旧FE或全数组审核。所有新数值/模型动作0。

以下历史逐字保留。

<!-- V46-LATEST-END -->

# Task042 V45最新交付：完整矩分层NN与配对终测

让实体保留全部实虚矩并传递远处残差信息；同信息线性和局部消融辨别贡献。三模型各128真实更新，validation拒绝非零NN head，完整资格与原尺寸/NN20仍未达成。

| 路线 | ρ门 | η门 | 完整资格 | ρ范围，门1e-6 | η范围，门1e-4 | 总Arnoldi | 含共同前段的8项求解s |
|---|---|---|---|---|---|---|---|
| R0 | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 258.393582 |
| CL44 | 8/8 | 0/8 | 0/8 | 2.581975482e-08..3.78853399e-08 | 0.0003508615011..0.0005405081646 | 128..128 | 263.432889 |
| LIN-H | 8/8 | 0/8 | 0/8 | 2.61547387e-08..3.861573114e-08 | 0.0003484809644..0.0005296573543 | 128..128 | 260.056874 |
| NN-L | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 250.222528 |
| NN-H | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 260.343939 |

背景：旧两跳宽32候选已关闭，本次新增完整12/120/900实通道和分层内容。原A／材料／RHS规范／128步与最终门保持，NN不替代最终有限元审核。机制和新梯度成立不等于求解能力；NN-L/H采用零修正，LIN-H小误差改善不能冒充20%神经增量。64hex/p6/q15无完整DtN，E/H/全通道/功率NOT_RUN。

唯一下一建议：把本轮冻结输入／完整系数／原残差／伴随／全部费用接口交给同物理合格传统引擎做一次匹配，先判断难误差与冷N=1是否存在20%空间；不再在同一A上换seed、加层、调tau或延长128步。本批不重建传统引擎、不复制dot求解器。

[response_v45](../response_v45.md) · [完整结果](full_moment_hierarchy_v45.md) · [费用](records/resource_costs_v45.json) · [完整库存](records/array_inventory_v45.json)。研究-only、无merge批准，以下全部历史逐字保留。

<!-- V45-LATEST-END -->

本輪最终62定点测试通过，真实新机制／9FD／3×128／40原作用及独立数组复算完成；15文档检查，CI、无关全库FE/MPI2/4未重跑。早期Ruff和只读失败保留。

本輪最终62定点测试通过，真实新机制／9FD／3×128／40原作用及独立数组复算完成；15文档检查，CI、无关全库FE/MPI2/4未重跑。早期Ruff和只读失败保留。

本輪最终62定点测试通过，真实新机制／9FD／3×128／40原作用及独立数组复算完成；15文档检查，CI、无关全库FE/MPI2/4未重跑。早期Ruff和只读失败保留。

本輪最终62定点测试通过，真实新机制／9FD／3×128／40原作用及独立数组复算完成；15文档检查，CI、无关全库FE/MPI2/4未重跑。早期Ruff和只读失败保留。

本輪最终62定点测试通过，真实新机制／9FD／3×128／40原作用及独立数组复算完成；15文档检查，CI、无关全库FE/MPI2/4未重跑。早期Ruff和只读失败保留。

# Task042 V44最新交付：后期误差学习与五路线终测

四模型各128次训练，封存heldout在全部求解冻结后独立审核。ρ与完整η同时过门才合格，完整原尺寸与NN20未资格。

| 路线 | ρ门 | η门 | 完整资格 | ρ范围 | η范围 | 总Arnoldi | 8项求解s |
|---|---|---|---|---|---|---|---|
| R0 | 8/8 | 0/8 | 0/8 | 2.512542745e-08..3.98664504e-08 | 0.0003359336327..0.0005311309217 | 128..128 | 244.588831 |
| NN-R | 8/8 | 0/8 | 0/8 | 2.490087855e-08..4.2150641e-08 | 0.0003674131818..0.0005308487408 | 128..128 | 247.686011 |
| NN-E | 8/8 | 0/8 | 0/8 | 2.651771046e-08..4.215432378e-08 | 0.0003643483429..0.0005497722015 | 128..128 | 245.305868 |
| RL-E | 8/8 | 0/8 | 0/8 | 2.651087888e-08..4.21524334e-08 | 0.0003643298497..0.0005496776936 | 128..128 | 246.041111 |
| CL-E | 8/8 | 0/8 | 0/8 | 2.610389954e-08..4.146630952e-08 | 0.0003642299582..0.000517074058 | 128..128 | 207.051734 |

共同身份：64hex/p6/q15/3tag/0.7nm、45000native/42624独立/2376slave；NN-R/NN-E/RL-E70144实参数、CL-E74240，各128更新。原A无完整DtN，旧恢复FAIL与原尺寸E/H/32060通道/功率/2TB48h未资格保留。数值费用共享工作站，完整冷成本unknown、NN20 NOT_DEMONSTRATED。

最终53项focused串行ML/纯数组/监督测试通过，实际梯度9FD、4×128训练及40状态独立审核；最终compile/Ruff和15文档测试见records。未重跑无关全库PDE、MPI2/4或CI；所有早期测试与软件失败保留。

[response](../response_v44.md) · [完整结果](late_error_learning_v44.md) · [全费用](records/resource_costs_v44.json)

唯一下一建议：在新合同中只比较一种包含远距离残差信息、并扩大单元内部输出表达能力的可扩展神经表示及同信息线性控制；先以本轮封存误差诊断确定所需容量，不复用它们训练。本批不实现该网络，不再为同一两跳宽32表示追加初始化、训练步或GMRES步数。

以下完整历史逐字保留。

<!-- V44-LATEST-END -->

# V43测试：真实神经链通过，完整候选资格仍为负

最终27项focused测试（含真超时／自身后代清场），9项真实全向量FD、3方向VJP、batch1/batch2 loss梯度及非零非互伴12port通过；128次实际NN和LIN更新，24项终测及独立原残差／完整系数审核已运行。数学接线通过不能替代求解通过，终测全部η超过1e-4。

失败fixture、依赖loader、线程query、active-worker预算与journal调用全部留证；无环境升级／CI／全仓昂贵测试声明。最终compile/Ruff/15文档合同及字节身份见新records，GitHub视觉NOT_VERIFIED。[focused](records/tests_v43.json) · [FD数组审核](records/saved_gradient_vector_audit_v43.json) · [文档](records/documentation_checks_v43.json)。以下历史逐字保留。

<!-- V43-LATEST-END -->

# V42测试与真实数值限制

最终clean实现上61项接线／反例测试通过；真实MPI1/2/4原作用通过，独立内部恢复FAIL保留。15文档合同、Ruff、compile及ABI/getter另列；测试通过不等于物理求解通过。pre13提交时序和全部失败费用保留，pre14独立重验。无CI或全仓pytest声明，GitHub视觉NOT_VERIFIED。[测试](records/tests_v42.json) · [文档](records/documentation_checks_v42.json)。

<!-- V42-LATEST-END -->

# V41测试与独立验收

最终已提交source上的38项相关测试与15项文档合同测试通过，ABI/真实compile/Ruff、真实native MPI1/2/4及全部保存向量checker通过。缺rank/owner/phase/face/方向/散布反例拒绝；失败全部保留。GitHub视觉NOT_VERIFIED，无CI声明。[测试](records/tests_v41.json) · [文档](records/documentation_checks_v41.json)。旧历史正文保留。

<!-- V41-LATEST-END -->

# V39测试：边界接线通过，真实体积恢复缺项保留

最后一次全相关serial为22项，最终新增callback反例及预算定点测试已复验；最终源码的小测试、真实compile／Ruff、15项文档合同结果见[tests](records/tests_v39.json)。相关MPI2/4为合成fixture，真实native仅MPI1。fixture dtype、carrier接线、旧输入FAIL等原始负例不删除，不称CI或完整PDE通过。以下历史逐字保留。

<!-- V39-LATEST-END -->

# V38测试：最终27个定点、合成MPI2/4及保存数组独立验收通过

完整checker缺q/缺action/重复/错身份、共享计划、单rank坏H/hash、单侧前缀、active worker预算、byte-identical别名及counter快照反例已覆盖。真实编译与复杂ABI/getter先于测试；最终aux_pre_12 27pass，MPI2/4通过，真实native与全量组件仅MPI1。没有重复旧campaign或CI声明。[测试身份](records/tests_v38.json) · [raw日志](records/raw_evidence_index_v38.json) · [独立checker](records/component_checker_v38.json)。文档检查另记；GitHub视觉NOT_VERIFIED。历史全文保留。

<!-- V38-LATEST-END -->

# V37测试：真实编译、31个定点与MPI2／4小fixture通过

复用最终aux_pre_06的逐文件hash和真实ABI记录；新增独立C/D、共享rows、H/source不变性、tile容量分配前拒绝、错误相位／转置／共轭、重复／丢face、坏hash及整树超时清场测试。31pass（pytest7.36s），MPI2／4完整向量和空owner／全体拒绝通过；真实FE仅MPI1。未重复旧campaign或全仓昂贵测试，无CI声明。

首次27pass/1fail、两次PATCH接线失败、q60存储停止及打包字段失败均保留，针对性修复同轮计费。[最终测试身份](records/tests_v37.json) · [原始日志](records/raw_evidence_index_v37.json) · [独立数组审核](records/component_checker_v37.json)。Ruff／文档本地检查结果单列，GitHub视觉NOT_VERIFIED；不以小fixture授目标资格。旧后缀逐字保留。

<!-- V37-LATEST-END -->

# V36测试：最终19定点与MPI2/4、真实组件及cache审核通过

实际编译发生在测试前；最终源文件hash绑定19个定点（含fixture closed／负结果reference barrier、actual dat、坏hash／readonly／空owner／weakref／独立保存数组反例），MPI2及MPI4保存实际完整向量并与serial配对。Ruff新文件通过。真实micro边界及独立cache checker两seed通过原1e-10门。

首次环境／MPI启动／静态格式／collector错误的raw、source和消费完整保留。没有重跑全仓PDE或声称CI。收口文档标准库测试单列在[测试记录](records/tests_v36.json)，不冒充更多PDE。

<!-- V36-LATEST-END -->

# V35测试：真实接线、缓存消费反例及最终静态复验

本轮首次真实冷启动，用七区局部解处理任意新残差，并由GMRES选择修正组合。代价是每个非零输入八次局部solve和两次传播作用；这是传统块方法，没有神经训练。

| 模型／结果身份 | measured或not_run结果 | 解释／边界 |
|---|---|---|
| .7nm／384hex／p3／q15／18144trace＋40port | 首256步Schur0.20524886351900365>0.01 | ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT，关闭固定七／八块追加预算 |
| 原完整方程 | native/augmented0.07959628543991103、total augmented0.027619862207395922>1e-6 | port/恢复/MPC通过不足以授完整解资格 |
| 费用／同时采样树峰 | actor188.162088667s／2108018688B／ownswap0；834次S/SH、264次PC | shared-workstation，全部aux/探针/旧费用另列，不双加嵌套计时 |
| 原因／范围 | 保存残差平方99.19%在外域；第二周期与FE/REF7 NOT_RUN | 无official R/T/A、NN20%或原尺寸2TB/48h资格 |

首次24pass/1fail保留，fixture结算修复后25pass；独立缓存26pass，含11项伪消费／状态变异拒绝。最终计数元数据修复后的相关suite、文档合同15项、真实编译与Ruff E9/F见[tests](records/tests_v35.json)。没有借用旧测试数量、full-repository／MPI2/4／FE／GPU或CI声明。Watchdog低成本超时测试真实清空自有后代，不操作邻任务。

唯一下一建议是匹配外域Schur的周期／层次全局逆接口与容量资格；本轮不实现。历史后缀逐字保留。

<!-- V35-LATEST-END -->

# V34测试：修后13定点通过，真实保存数组独立审核完成

| source／实际范围 | 原始结果 | 说明 |
|---|---|---|
| 79f3d5a8a4ff9abf75b640fb865872ce6003654e／首次前测 | 11 passed/2 failed，监督7.912601837s | WAIT fixture目录责任及full_linearity ValueError消息；失败原样保留 |
| fbc5c578e61adc670abda6f723f33192b1617e83／修后前测 | 13 passed，监督11.764919262s | actual study→save→settle→checker、残差原容差两侧/非有限/来源、收费消费/重入、WAIT退避/探针、closed与统一存储，含无损失败归档 |
| 同source／正式dat | 一次真实actorCOMPLETED | S20SH2/全部22作用与manifest、write-ahead、ledger、真实因子资格一致；不是合成计数 |
| a4cf9c0fc7dcb819bcbfe81559f040d5306720f6／最终checker | 保存分区与复交叉项小测试1 passed；实际CHECKED，5.926647831s | 零新作用/因子/solve/QR/reference，软件pass不写成数值改善 |
| 静态／文档 | 最终表格、链接、math fence及纯文档测试另列render记录 | GitHub视觉NOT_VERIFIED，不伪称CI或网页通过 |

[tests](records/tests_v34.json)／[首次与修后raw](records/raw_evidence_index_v34.json)／[资格](records/source_inventory_v34.json)／[repairs](records/repairs_v34.json)／[render](records/render_check_v34.json)。最终checker新增分析单独小测并实测审核，actor数值内核和环境未因文档变化重跑。没有MPI/FE/full-repository/Ruff/CI；不机械重复历史110/162或将旧review隔离修改当生产资格。以下旧测试逐字保留。

# V33测试：最终静态通过，runtime因CPU准入未执行

最终clean实现source a874498a1a8b854f394520627eaf09158b77fbf9的16 Python文件在内存中compile和全局符号检查通过，无科学库导入／pyc。准入发生在前一clean实现45d34165…；worker前被CPU/SMT拒绝。新6测试函数涵盖实际study→保存→结算→cached checker、非互伴port、差式／反馈抵消、外域-only／零输入、奇异块／错库存／wrong vector／zero-consumption／closed和V33存储边界，但本轮执行0，不借用旧12 passed作当前source资格。

runtime pytest、dynamic dat validate、Ruff、MPI/FE、full-repository与CI均NOT_RUN；拒绝后不重试。冻结CPU JSON／CSV算术重放和本地Markdown结构为stdlib静态核验，不是数学回归、fresh资源准入或GitHub视觉通过。网页Cache miss，视觉NOT_VERIFIED。证据：[tests](records/tests_v33.json)、[最终compile](records/compilation_final_v33.json)、[raw](records/raw_evidence_index_v33.json)、[render](records/render_check_v33.json)。以下旧测试原样保留。

# V32：12定点通过，唯一真实actor与独立checker通过

实际source1fe058e3d120c42d197531139fc62e02a1a2cd5f；13 Python compile／全局名称检查、12 targeted passed in5.29s。覆盖统一存储边界（review/records/results及去重）、namespace和closed／active／consumed拒绝、独立attempt计费、当前源码资格与deadline余量，以及实际study→保存→结算→collector。另覆盖三个直接受影响V31用例；没有机械复跑110／162项或声称full-repo／CI。

合成fixture仍是16个活动维度、18144/40接口，IO/readiness/reader与guard为桩；真实七readonly reader、因子见证、原两冷态和资源守卫由唯一actor资格。实际完整S34/SH2及全部计数与manifest/ledger/result一致；独立cached checker CHECKED，未调用原作用、factor、QR/SVD。

V31原109/1及Review V29独立fixture1 pass不改写。V32无新前测失败；后checker首次在worker／CPU准入前遇容量预留停止，stderr保持，清理未引用bytecode后另ID同门限通过。没有actor重跑。运行源码未再变化，文档改动只作局部静态公式／表格／链接检查；GitHub视觉NOT_VERIFIED。证据：[测试](records/tests_v32.json)、[raw](records/raw_evidence_index_v32.json)、[checker](records/return_direction_checker_v32.json)。以下旧测试逐字保留。

# V31测试：109通过／1失败，修后只静态检查

唯一受监督前测在clean source997397093f7061f7086b2088458d50c6ca773b7d执行110个不同测试：旧受影响102＋新V31 8，109 passed／1 failed，无skip。实际study两态／七合成bundle／保存／结算／collector及partial失败写出均通过。唯一失败test_failed_prequalification_stops_formal_route的window桩缺接口，AttributeError早于预期InputError，未误报通过。

4734b22d1b9260b8500c32212e4e30b1c03f0507最小补齐接口，17文件编译和符号检查通过；修后runtime NOT_RUN。Review V28规定前测新错误即停止数值链，不能为满足普通重测规则重复一次性准入。正式actor／后checker未运行，不声称CI、全仓或FE/MPI通过。原109/1保留。

[失败trace与资格](records/tests_v31.json)／[stdout](records/tests_stdout_v31.txt.gz)／[JUnit](records/tests_junit_v31.xml.gz)／[最终静态](records/compilation_after_v31.json)。以下旧测试记录保持。

# V30：最终实现的真实编译及唯一监督验收

source `1a18f520dae3ecd702a1369b0d9241ec3e81802a`：准入前22文件compile成功，无执行／NumPy导入；唯一受监督任务最小7 passed、完整162 passed（原155＋新7，最小7重复，169次实际执行）。32变异先确认未变异正控制通过，再断言准确ValueError/KeyError消息；专门IO回归证明任意FileNotFoundError不能误报通过。完整轻量入口PASSED／exit0，CPU replay、三固定代数、成本模块整体执行。scope含12项仓库文档合同；它们绑定运行时source，交付前新增文档另作静态结构／链接检查，不声明对文档HEAD重跑pytest。无CI／full-repository／FE-MPI／真实PDE验收。

[编译](records/compilation_v30.json)、[最小raw](records/minimal_stdout_v30.txt)、[完整raw](records/full_scope_stdout_v30.txt)、[JUnit](records/full_scope_junit_v30.xml)、[入口](records/entry_result_v30.json)、[原始监督](records/supervision_v30.json)。新source没有再修改或重启；V29原NOT_RUN及Review V27审阅测试分开保留。以下历史逐字保留。

# V29测试：唯一CPU准入拒绝，全部运行验收未执行

| 检查／数据身份 | 结果与具体限制 |
|---|---|
| 新四反例／完整collector合成包 | IMPLEMENTED_NOT_QUALIFIED；NOT_RUN，无零消费／失败因子／错向量／错范数的本轮运行通过声明 |
| 原100相关scope | 保留在预备队列，当前source NOT_RUN；Review V26历史100通过不替代此次回归 |
| B三个固定小fixture | n8/2/2、complex128、seed422901、显式奇异局部拒绝和非收缩反例；执行0 |
| CPU replay／缓存分析 | NOT_RUN；逐核表为已保存decision静态转录；成本为hash-bound JSON字段转录，不运行benchmark |
| AST／文档结构 | 准入前selected source AST静态解析；最终本地文档结构见render_check_v29，不称runtime或pytest |
| compileall／doc pytest／CI／full／FE／MPI | 全部NOT_RUN，原因唯一辅助准入拒绝；未在closed窗口补跑 |
| GitHub视觉 | 精确Review V26页Cache miss，NOT_VERIFIED，不伪称视觉通过 |

实际实现及准入launcher source bea514e634a0fde7b1b929535f79a6268856d01b，worker source=null。[测试库存](records/tests_v29.json)／[准入stderr及快照](records/admission_stop_v29.json)。准备复现入口`python -m benchmarks.task042_v29_light_checks`，本轮不可自行执行或再次准入。以下历史逐字保留。

# V28测试与实际未运行边界

| scope／身份 | 结果及证据 |
|---|---|
| 最终保留的pure实现 | 100 passed in5.28s；新33+旧67，不将重复执行相加；compileall与真实V28 dat validate通过 |
| 独立结果checker小fixture | 正例、弱增量、beta0、已解基线null、零/重复/近零、库存/预算/非有限/失败Gate反例通过；不调用真实A/因子或新QR/SVD |
| 实际准入重算 | 成功候选11/22/26及拒绝空集合重算一致；资源项已检查/NOT_CHECKED严格分列；原始stdio与无损快照hash绑定 |
| 最后辅助／真实诊断 | 第二辅助在CPU Gate拒绝，后续pytest/compile/validate命令NOT_RUN；可选加强未纳入源码，恢复首次通过实现；正式准入与数值actor0 |
| 成本／资格边界 | 新辅助8.797189402s、两轮累计21.163846770s；没有CI/full/MPI2/4/新PDE/Ruff或真实因子见证；旧跨任务checker失败未修，不宣称全仓绿 |

[测试原始日志](records/tests_v28.json)／[准入证据](records/admission_checker_v28.json)／[run index](records/run_index_v28.json)。GitHub精确页Cache miss，视觉NOT_VERIFIED；本地静态另记。以下历史逐字保留。

# V27最终测试与未运行边界

67项focused pure测试通过（1.70s），包含旧V26的42项scope、4项临时ledger／时钟拒绝与21项V27回流fixture；46和早期67为相同scope子集／重复，不相加。源码与clean commit7b0e03f2逐文件绑定。compileall及真实新dat validate PASS。生产V26窗口／ledger未变。

真实回流两态／factor重载／原S资格NOT_RUN：正式actor前CPU准入失败，一次复核额度已用完。没有新的CI、full pytest、MPI2/4、PDE或训练；Ruff未安装。旧跨任务总账合同失败由Review V24报告，本批不清理或声称全仓绿。[测试日志](records/tests_v27.json)／[零消费独立核验](records/admission_checker_v27.json)。以下历史保留。

# V26本地测试与证据范围

| 本地scope | measured结果／边界 |
|---|---|
| clean数值实现前focused | 94 passed in3.89s；早期86是子集，不相加；包含新库存19和联合核8、V25与V24默认/准入回归 |
| 冻结后新缓存checker | 15 passed in1.05s（早期14项为子集，不相加）；完整40模式紧凑引用、两name库存/失败/错hash绑定、原向量eta/g与innovation证书、closed准入拒绝；无新S/LU/QR/SVD |
| 仓库治理/模型总账文档 | 12 passed in0.07s；与94/14分列，原历史表/保护规则保持 |
| §3真实旧缓存 | 三状态CHECKED，EIGHT_DIRECTIONS_WEAK原样；empty/one/duplicate/label/parent/member/gates/nonfinite/missing rank/recombination拒绝 |
| 唯一真实原算子actor | 两cold状态全资格见证通过；负结果g0.982678149/0.991962824；S14/SH2，不是PDE/场资格 |
| compileall／one-run注册 | PASS；DIAGNOSTIC dat clean source validate，结束ledger closed拒绝新运行 |
| full/MPI2/4/FE/NN/CI/Ruff | 超范围NOT_RUN；Ruff未安装，不升级环境，不声明CI |
| GitHub视觉 | 精确页Cache miss，NOT_VERIFIED；本地渲染结构/链接另记 |

实际actor source `652cb206cd1ebeb1c4182ac2300c1dc23c57b48f`；后继checker仅审核保存数组。辅助准备D01/D02及草稿失败保留，正式重放0。[run index](records/run_index_v26.json)／[缓存](records/cached_array_checker_v26.json)／[费用](records/resource_costs_v26.json)。以下历史字节保留。

# V25最终测试与边界

| 本地检查 | 实际结果／口径 |
|---|---|
| six-field/four-power/40-mode必需库存 | 52 passed；逐缺键、empty、NaN/Inf/负误差、错mode／极化／参考面拒绝 |
| 最终Task042 focused | 93 passed in 7.72s；库存52包含在93内，不相加；含复非Hermitian／非互伴40port、零／秩亏／相消、wrong hash、deadline与完整后代清场，以及V24准入/reader默认回归 |
| 原V24 checker | 0/5保持；无重跑PDE，原six/four库存完整 |
| V25真实packet原作用见证 | 三状态全通过，S39/SH0；原映射、端口、对角／线性重组、QR／秩／驻点；不是field资格 |
| 独立cached-array checker | 重算3组eta／驻点／块交叉项，与actor一致；不增加S、QR、SVD或factor读取 |
| compileall／新dat | PASS（正式commit/actor前）；单个DIAGNOSTIC入口valid，结束后封存拒绝续跑 |
| Ruff／full pytest／MPI2/4／CI | Ruff未安装NOT_RUN；其他超出array-only范围NOT_RUN；不声明CI |
| GitHub视觉 | 精确页Cache miss，NOT_VERIFIED；新Markdown本地表格／fence／链接检查单列于render_check_v25 |

两个开发接线失败及一次辅助准入无空闲核拒绝保留，失败费用计入；两次最小修复后正式数值无重放。实际source bc88fe5a81d086059dec705db333b9cf9bf2921e。[库存](records/checker_inventory_v25.json)／[缓存审核](records/cached_array_checker_v25.json)／[失败](records/failures_and_not_run_v25.json)。以下原测试历史字节保留。

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

初版28 focused通过；§10控制流26 focused通过，6/6入口validate。保留全部失败；真实SETUP及四首块、唯一FE审核实际执行。未重跑full pytest/MPI2/4或声称CI。

收口checker最终5 passed（0.17s），参考资格也由保存的原始Schur/native/独立total-native重算；不能用记录里的true标志替代。checker独立复算局部／组合资格通过、5状态完整资格0通过、资源与首4周期上限通过。该轻量检查费用计入原批次elapsed，不新增FE或重开预算。

唯一下一建议：以本批已保存的零初值残差为输入，预登记一次有界的块内／跨块耦合作用分账，判断下一种局部通信机制需要补足的方向及容量；不立即改变块数、重叠、粗空间或追加求解。

[本轮回应](../response_v24.md)。以下历史原文逐字保留；其中“当前”仅指记录当时。

# V24 targeted测试与实际停止边界

| 检查 | 实际结果 |
|---|---|
| 复数/非互伴40port、共享cell/Floquet主块、L8/LC恒等式、奇异反例 | 最终小模型通过；不冒称真实FE资格 |
| dat→stage→右PC→GMRES→close→原子保存→旧oracle | 四新角色fixture均运行 |
| readonly重载/hash/返回补审/角色白名单/截止清场 | 最终28 passed（合并相关旧fixture），2已消费旧用例deselected |
| 六dat真实validate-only | 提交clean source后6/6 valid |
| 真实SETUP/rcond/D_L/四求解/独立场 | NOT_RUN；CPU准入后审批服务认证阻塞 |
| AST/历史保护/Markdown | 只作低成本静态核验；详见static_checks |
| full pytest/MPI2/4/CI/新昂贵测试 | not_run，未重装环境或宣称CI通过 |
| 精确GitHub公式/表格视觉 | NOT_VERIFIED；cache miss后网页接口token_expired401 |

首次SIGSEGV和后续二维反例失败保持；最小修复2/4。已消耗所有测试/失败费用保留。[测试](records/test_results_v24.json)、[静态](records/static_checks_v24.json)、[成本](records/resource_costs_v24.json)。
以下历史正文逐字保留；旧“当前”只指其当时阶段。

# V23测试／Review V20

最终相关pure-array/真实dat接线/事务/读取白名单/奇异反例/截止清场回归及记录篡改反例见[测试](records/test_results_v23.json)。五实际dat已实现并validate，正式S/D/M/Z/V均实际one-run。Ruff模块未安装，不改环境；full pytest/MPI2/4/CI/旧campaign not_run。原代码ActionPacket/recover/uncondensed/audit的数学实现未重定向到class64；共享IO/Stage只加保留原默认的显式参数，并有旧pure回归。本地GFM表格/围栏/链接/compile/diff与旧历史字节保护见[静态](records/static_checks_v23.json)，旧总账checker问题与review起点逐项相同，不做全仓清理。GitHub精确review/结果页无视觉证据，**NOT_VERIFIED**；本地结构不替代视觉。

| 类别 | 真实结果 |
|---|---|
| 复数小模型/40port/右PC/奇异反例/role/schema/返回失败/截止清场 | 最终相关测试由test_results_v23记录；不构造新FE解 |
| 真实S1248列/QR/原作用/PC | 通过；额外19 fine作用，rank不扫描 |
| 正式M/Z、独立6状态 | 全部实际执行，原方程与完整资格0/2新求解、0/6审核 |
| 离线通道功率 | 240项原公式配对通过；activation失败费用保留，仅重放辅助reader |


以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# V22 targeted回归与独立证据审核

| 检查 | 实际结果／边界 |
|---|---|
| 最初p1/右PC小fixture | 9 passed / 1 failed；过严fixture期待已局部更正，未改真实driver/Gate |
| 修正后事务/reader/六dat/schema/clock/cleanup | 25 passed / 1 deselected；无旧campaign重跑 |
| 离线齐次误差投影与cold角色补强后 | 27 passed / 1 deselected；内容与独立VERIFY source一致 |
| 正式p1→p3映射/Ac/LU/PC接线 | 真FE资格PASS；不等于物理求解通过 |
| 独立原方程/场/40通道/功率 | frozen后读取REF7，4状态完整资格0/4；derived逐功率与原公式配对PASS |
| 离线checker伪造通过反例 | 记录见tests_v22.json；从raw残差/场/功率重算，不信status |
| 本地Markdown/compile/diff/历史保护 | final/static records，不能替代GitHub视觉 |
| full repository/MPI2/4/CI/Ruff/GitHub视觉 | 未执行或NOT_VERIFIED，未升级环境/安装工具 |

正式求解source24fbbad55fbef07b75533e60fc1869749a2f8777，独立VERIFY7a7a44ea567abfc119e4eeec474e3e1bea46b519；无正式重放/资源重入；交付辅助R01/R02最小路径修复只重放static；R03隔离schema fixture窗口，最终33passed/1deselected，未重复数值。最终源码/文档相关最小检查及继承旧总账失败若存在逐项记录，不全仓清理。[测试](records/tests_v22.json)、[静态/历史](records/static_checks_v22.json)、[费用](records/resource_costs_v22.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# V21：真实作用、循环保存与读取边界的focused检查

| 检查／成本口径 | measured结果／限制 |
|---|---|
| 首轮精确class/循环/旧事务/reader | 42 passed / 1 deselected，后修正fixture及最终43 passed / 1 deselected；未重跑旧campaign |
| 最终preformal targeted | 19 passed；包括独立旧oracle、deadline过期拒绝、CU None/k+1/hash、真实B/C dat→保存→audit |
| R02/R03公共链与JSON发布 | 20 passed；C8原hash完整补发布，未重算Arnoldi |
| R04 parent reader | 旧x/outer_directions解码反例；两模式明确只解码四个物理数组，最终数量见record |
| V20 reader | 本批最小mutation回归通过；不追溯改变V20 not_run/时间FAIL |
| A真实原/new S与SH及完整暖点残差 | 数学Gate通过；性能只是shared-workstation工程收益 |
| 独立物理VERIFY与raw checker | frozen后读取REF7一次；原残差/场/功率重新判断，不信保存status |
| 完整pytest/MPI2/4/CI/Ruff/GitHub视觉 | not_run或NOT_VERIFIED，未安装或伪称通过 |

B的旧方向不得读取Gate仍FAIL_RETAINED；算法使用零校正与空方向不抵销字面读取缺口。R04后只补独立验证，不重跑已耗尽B预算。全部失败、辅助监督、测试耗时与源身份见[测试](records/test_results_v21.json)、[读取边界](records/data_loading_boundary_v21.json)、[费用](records/resource_costs_v21.json)。最后文档合同10 passed / 1 failed / 15 deselected；失败的总账Task列表及Task038路径在Review V18基线中逐项相同，未修改历史或扩大全仓清理，见[基线对照](records/legacy_registry_check_v21.json)。代码最终35项已在相同内容上通过，文档改动不重跑旧数值Gate。最终compileall/git diff与文字/历史保护见[静态](records/static_checks_v21.json)，本地结构不替代GitHub像素证据。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# V20 本地验证与截止

正式source d41470d17d2babf29fabb0960886b0f60ae2aceb提交前最终38 passed（test_task042_v20_ilu0＋V18/V19事务回归），compileall及git diff --check通过；七dat注册/schema验证通过。真实native PC小fixture及formal S0配对、N/P0/P40实际端到端均通过接口Gate。两次计划内fixture失败22/1和37/1保留，最终38/0；正式求解/验证重放0、意外修复0。

后置reader由raw hash/数组及现存equation/field规则重算EVIDENCE_CONSISTENT，0/5合格；新增mutation suite因截止未启动，未验证代码只留ignored，不称pytest通过。Ruff不可用；full pytest/MPI2/4/CI not_run。实时总elapsed超限，正式负载已在截止前清场。

Markdown本地结构/链接与GitHub视觉分别记录，视觉NOT_VERIFIED。[测试记录](records/test_results_v20.json)、[deadline](records/deadline_stop_v20.json)、[原始Gate](records/qualification_and_dispatch_v20.json)。

以下历史正文保留，旧“当前”仅指其当时阶段。

# V19 测试：成熟GMRES与方向保留新接口

| 检查 | 真实结果 | 证据／限制 |
|---|---|---|
| 接口与成熟driver targeted | 首次25 passed / 3 failed → 修复后28 passed | 真实40port BarAction；跨周期、独立读回、事务故障；无旧campaign重跑 |
| 后置raw reader | 15 passed | hash/预算/伪造status反例；无原action或solve |
| 最终同源targeted | 43 passed | 先41 passed/2 fixture failed；提前隔离测试目录后完整重测，费用保留 |
| 6个实际新dat | schema/stage + validate PASS | C0/P_GP/P_GN/L_GP/L_GN/V；条件队列不是盲跑 |
| compileall | PASS | V19相关数值、io、runner、tests文件；不重复大FE |
| native FE ABI | complex128 / int64 / MPI1 PASS | 独立qualified activation，当前src及同一只读ABI前缀 |
| 独立raw Gate | EVIDENCE_CONSISTENT | 0完整合格；负结果仍保留 |
| Markdown | 本地结构检查另列 | 精确GitHub页面未见视觉证据NOT_VERIFIED |
| CI / full pytest / MPI2/4 / Ruff | not_run | 共享窗口按合同只跑targeted；Ruff不可用，未安装 |


实际数值source `b58919a4a0dcd677b915eb7d9bbd314520aef0e0`，reader/test source `e13a7adab7ac8d5da17b688af6e0db27c6c27fa9`；两preformal根因、一个后置fixture修复及失败费用保留；solver周期重放0，VERIFY因sandbox本地MPI socket拒绝而同源授权重放1次。详见[测试记录](records/tests_v19.json)、[修复](records/repair_reentry_v19.json)、[独立Gate](records/qualification_and_dispatch_v19.json)、[run index](records/run_index_v19.json)。后置文档变化不重跑已hash绑定的昂贵FE。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# V18测试与可信边界

| measured检查 | 实际结果 | 证据/限制 |
|---|---|---|
| 计划F0纯小回归/既有共享监督/LSQR资格 | 首轮43通过/2夹具失败，最小修复后45通过；最终数值实现45通过 | 真BarAction、40port、dat→Stage、info/callback/zero、故障边界、进程树deadline |
| 8个dat的真实schema/stage注册、validate-only、定向compileall | PASS | 入口已实现后验证，正式每个slice为独立dat |
| 后置raw reader反例 | 15 passed | hash、z组成、原残差伪status、非有限/预算 |
| 原数组独立读取 | EVIDENCE_CONSISTENT；严格0/8 | 不信已存status；无新增S/求解 |
| 真实F0及冻结后一次FE | 两接口PASS，物理0/8 | 10次预检底层作用，不重复旧长试验 |
| CI/full repository/MPI2/MPI4/Ruff | not_run | 本批serial1；Ruff不可用，不安装；未声称CI |

[test records](records/test_records_v18.json)、[原始Gate](records/qualification_and_dispatch_v18.json)、[静态/历史保护](records/static_checks_v18.json)。测试后置reader不改变正式数值source；仅文档变化不重复昂贵FE。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# V17：恢复、冻结证据与接线的实际检查

| 检查／范围 | 实际结果 | 证据和限制 |
|---|---|---|
| 小复数恢复协议／旧递推／投影全空间／G周期单元 | 最终35 passed in 1.91s；监督5.425998s／231088128B／swap0 | `tmp/task042/v17/final_core_tests`；含独立reader、半写/kill、hash/已终止/计数上界和bit-identical旧20步；G算法小测试不等于正式G接线合格 |
| 每库真实32对16+reader+16 | 两库GK/z/原作用差0，qualified；原S164+SH133=297 | [R1](records/resume_qualification_v17.json)；监督193.188007s，无生产warm start |
| 独立原数字／hash／状态与完整Gate | EVIDENCE_CONSISTENT，0/8严格资格 | [checker](records/qualification_and_dispatch_v17.json)；监督20.110744s／965443584B／swap0，0新S/SH/求解 |
| 低成本独立watchdog超时／孤儿／失效清场 | 3 passed，8.549s | 原准备阶段自有证据，未操作邻任务，未为文档重跑 |
| 第3／4编号修复 | 26／32相关小测试PASS，失败源码和加载记录保留 | [修复账](records/repair_journal_v17.json)，最后35项覆盖最终实现 |
| 正式G接口 | 两库首周期后trace/port shape失败，0完整周期 | [真实错误](records/gmres_interface_stop_v17.json)；小G测试未覆盖该消费API，不能包装为G数值通过，四修复额度用尽后未第五修复 |
| 原FE独立验证 | 8去重状态、REF7原hash/native1.437444866e-12、0/8资格 | source59feb657…，监督29.445640s／760164352B，旧准确解仅读取，无新LU |
| 新入口schema | 六个base dat及真实slice均validate／实际manifest绑定 | 生产正式source clean；冻结后非VERIFY入口按reference barrier拒绝，不绕过屏障重验证旧输入 |
| final compileall／Markdown／历史保护 | 结果由下列最终record保存 | [最终检查](records/final_checks_v17.json)、[source table/math/link](records/static_checks_v17.json)、[旧blob](records/protected_history_v17.json) |
| GitHub rendering | NOT_VERIFIED；exact-review页面Cache miss，无浏览器像素 | [publication](records/publication_checks_v17.json)；不把源码静态检查冒称视觉PASS |

所有数值run MPI1/数学1/GPU0，现场选核、own swap0与独立整树监督；轻量tests使用qualified FE import ABI complex128/int64但不建mesh/form/JIT。最终checker源74a3f2643862a3fd73fc7b6b417cbc910a335388，formal求解/验证源59feb6570a74d72aa501853807013711d89279cd；输入和源码dirty状态如实在辅助证据中。Ruff、CI、full repository pytest、MPI2/4未运行；不因无关旧checker扩大全仓测试。

以下历史正文逐字保留；旧版本的“当前”只指其当时阶段。

# V16 本地测试与证据

| 检查 | 实测／限制 |
|---|---|
| 小型复数全空间／空Q／非零port／错误映射与共轭 | 初期focused21项通过；有限接线修复后23项通过，旧默认LSQR递推bit一致；最终checker及总账回归见final_checks_v16.json |
| 监督清场 | 0.75s低成本超时含孙进程，受控停止并清场；正式stage尾部失败另保留，不将JSON失败改写为数值成功 |
| 真实接口／物理 | 原A/QR两库合格，空Q/GPOLY dot/projector合格，GNN该标量证据丢失列unknown；物理资格0/6；制造资格不能冒充原物理通过 |
| 输入／ABI／静态 | 五dat validate、定向compileall、diff检查；native complex128/int64/MPI1，所有实际正式source与数组hash绑定 |
| checker／Markdown／GitHub | [最终本地记录](records/final_checks_v16.json)、[静态与历史保护](records/static_checks_v16.json)、[发布显示](records/publication_checks_v16.json)；browser glyph未观察 |
| 未执行 | full repository/MPI2/4/CI、GPU、旧campaign与新p4参考；Ruff按当前资格环境的实际可用性记录，未安装依赖 |

下面旧测试正文原样保留。

# V15测试与执行证据

| 本地检查/阶段 | 实测结果/限制 |
|---|---|
| C1/C2/最终C3 focused pytest | 17/30/33 passed（重叠集合，不相加）；最后33项5.32s，监督7.719236s，包含实体周期/秩/块配对/复数非Hermitian/非零port/仿射恢复/原子writer/超时清场及伪造success反例 |
| compileall / diffcheck / 六入口 | 通过；数值运行前clean source db0e68e519767554412c960af14b3c185012f9de，每dat独立stage；真实L0插值/MPC及两制造见证合格 |
| raw checker source 8d6df6926fc6f5c1afc27491dc06255791fcc044 | EVIDENCE_CONSISTENT，实际冻结Phi/Schur/decoder重算、4个trace差0、8资格全部False；监督15.725563s/树520765440B/swap0；不新建S或求解 |
| preflight偏差 | 额外WSL marker断言错用，shell未set-e；已有native ABI通过且重核_NATIVE/complex128/int64/MPI1通过。后续set-e；无ABI变更或正式重放 |
| Ruff / full repository / MPI2/4 / CI | Ruff unavailable；其余not_run或未声明，按固定MPI1批次只做相关回归，不重装、不将本地通过称CI |
| Markdown/GitHub | Review V12精确OID服务端4表3公式结构PASS；新文档本地与推送页另见[发布记录](records/publication_checks_v15.json)；浏览器glyph NOT_OBSERVED |
| 最终文档合同／总账 | 新文档与新增历史前缀的表格、围栏、相对链接、旧正文逐字保护通过；总账5个小测试passed，监督1.821683s/树48287744B/swap0、后代清场；[本地合同](records/static_checks_v15.json)、[最终检查](records/final_checks_v15.json)。没有重新执行数值队列 |

旧昂贵Gate由相同算子/数组复用，不重复旧campaign；历史测试原文保留。

# V14最终测试与证据资格

| 组件／目的 | 真实检查与结果 | 证据／限制 |
|---|---|---|
| writer与整树清场 | 初期9项小测试PASS：Mapping/NumPy/complex/整数key/原子中断、timeout/setsid own descendants，sibling未控制 | [资源辅助](records/resource_costs_v14.json)；早期key失败保留 |
| 正交数值核 | complex非Hermitian/非零40port，正确制造rhs/齐次恢复，逆序行恢复、错误旧A与Q、rank失败、比较余量/射线、reference屏障、元数据overwrite、缺port | 16项最终C2pure PASS；首次严格浮点断言改为approx，数值Gate未改 |
| C3 raw checker反例 | 强行pass、rank/driver阈值、raw gamma冒充、参考反馈、缺复通道/能量失败、FP32快照被拒 | 最终combined **22 passed**；[raw Gate](records/qualification_and_dispatch_v14.json) |
| 保留Q身份 | 原点及最终Q×c重新生成trace差0，完整state/hash均一致 | checker不启动FE、不重建P/A、不调用S；其余Q预声明可再生workspace |
| 真实资格 | 两新制造见证PASS；原点配对与逆序QR、6+2真实profile全执行；一次FE10状态全部FAIL | solver失败不改写；制造与记录PASS不能称物理PASS |
| 环境与静态 | pure/ML/FE activation/preflight；CPU Torch intra/inter1/BLAS1，FE complex128/int64；3dat validate、compileall、bash -n、diff检查 | [静态](records/static_checks_v14.json)；实际source 87940891c12ccdec35fca39cd453ab9a29eeeda5，C3 4efc94a… |
| 未执行 | Ruff未安装、无CI；full repository/MPI2/4未运行 | 本批MPI1固定pilot，不扩大共享负载或清理无关旧检查器 |

GitHub检查区分server richText表格/math-renderer与未观察的浏览器字形；当前参考native数值未落入复用验证器最终JSON，标明缺项，旧合格REF7身份保留。下方旧测试为历史。


# V13 最新测试与证据核验（历史检查完整保留）

| 检查范围／目的 | 实际结果／限制 | 证据 |
|---|---|---|
| 非Hermitian、非零port、非最优head、实hidden复head独立切向 | CPU ML四个小测试通过：手推层递推／原forward／VJP／向量FD、完整矩Piola/orientation、真实joint非linear-only、set_hidden后重写头 | [ML断言与实际线程](records/final_checks_v13.json)；ML环境无pytest，不称pytest通过 |
| 最终相关pure-array／head／watchdog回归 | **25 passed，1 deselected**，排除ML专属hidden_assignment并另有ML测试；原生主机现场选核，树345440256B、swap0、wall8.168026s，清场 | [完整命令／stdout／源码hash](records/final_checks_v13.json) |
| checker反例 | 实hidden被复更新、linear-only伪候选、无下降仍接受／错port、真实dual错误、补偿符号错误、缺通道、head清零均拒绝；不只信status | [独立raw Gate](records/qualification_and_dispatch_v13.json) |
| 实际数值Gate | A三方向新向量Gate通过；初次C联合Taylor失败，一次预登记复核后仅2方向通过；实际C接受1步而物理失败 | [真实切向](records/tangent_identity_checks_v13.json)、[全部试探](records/coupled_step_history_v13.jsonl) |
| 最小writer修复 | 复现mappingproxy TypeError、转换dict后通过；只恢复已保存记录，必要前向/audit计费，不重做优化 | [失败及source](records/run_index_v13.json) |
| 输入／compile／文档 | 定向compileall、四基础dat validate-only、diff、JSON/CSV／表列／链接／围栏；旧232项保护核对 | [最终静态](records/static_checks_v13.json)、[历史保护](records/protected_history_v13.json) |
| GitHub实际网页／公式 | Review V10 HTTP200 richText含3表／8数学renderer；server结构与本地检查分列；结果页面发布另核。没有浏览器像素／JS字形证据 | [Review显示](records/review_render_check_v13.json)、[发布显示](records/publication_checks_v13.json) |

纯数组／ML小测试与正式阶段均数学1、自身nice/I/O。收尾第一次沙箱轻测试可验证自身树，但沙箱PID视图不足以核对主机邻任务；费用保留，最后在原生主机重新审计并立即绑所选CPU0后重做同一25项。另一轮审计曾选CPU13，说明编号不能固化；活动检查最初按task042子串误匹配邻Task042extra，改用精确NN-Lab cwd排除该邻任务，未修改它。无GPU测试、全仓pytest、MPI2/4或CI声明。Ruff未安装不冒称通过；一次preflight误加`--mode pure`被argparse立即拒绝，按activation选择mode后通过，无数值启动。首次静态链接检查在生成自身记录前发现该文件不存在，原失败保留，之后只修正记录生成顺序；这些命令／文档检查不是数值核心的另一项修复。

# 本轮实际测试、失败与文档检查

| 检查 | 真实结果及范围 | 证据 |
|---|---|---|
| strict协议/PC/表示 | 33原协议测试、局部block容量/complex/input、streamed POD对精确SVD/native Gram/固定线性PC | 前期40/41项bounded array检查；最终focused数量与source见[final](records/final_checks_v2.json) |
| 真实FE配对 | F1 A4=PH A6P、primal/dual、p4 assembled与独立cell作用、非零内部/port制造解 | [F1](records/f1_real_components_v2.json)是物理组件资格；不同于toy或正式p6场资格 |
| borrowed p4/default | caller-owned p4材料化witness与默认拒绝/无所有权转移；真实80mode complex序列化保持相位 | paired tests与实际F1通过；最终同focused FE checks |
| resource enforcement | setsid grandchild触测试128MiB门仍被清场，独立sibling未被信号 | [bounded前期](records/shared_preimplementation_checks_v2.json)与最终focused watchdog验证；未控制邻任务 |
| teacher/表示/模型 | 384对原native/port/internal/恒等式<=1e-10；native像核验；CPU float64 intra/inter1 Loader0；Torch/NumPy probe | [teacher](records/teacher_complete_v2.json)、[oracle](records/oracle_complete_v2.json)、[训练](records/training_complete_v2.json) |
| strict F4 | 同16 heldout ×3候选；所有非零256步后未达到1e-10，zero自身精确0 | 独立raw Gate重算，[48项CSV](records/strict_rhs_metrics_v2.csv)；失败完整state/历史本地保留 |
| 本轮最终测试/静态 | targeted source regressions、Ruff、compile、bash、diff，Markdown表格/围栏/链接/JSON/CSV/原历史合同 | [final checks](records/final_checks_v2.json)、[独立静态](records/static_checks_v2.json)；dirty文档检查不冒充clean数值source |
| GitHub发布渲染 | push后检查真实exactHEAD的summary/架构/response_v2/两总账richText表格/标题/公式renderer | [publication](records/publication_checks_v2.json)；没有浏览器像素截图资格 |

此前接口错误与修复按原attempt保留：缺pyvista→独立固定依赖；CFFI缺setuptools→NN-Lab setuptools及complex CFFI probe；材料化p4被旧默认拒绝→显式borrowed witness/paired tests；mode包含complex且one-element数组需保留形状→定向metadata修复。没有改变p/h/通道/残差/FGMRES budget。F4-B0手写schema enum遗漏在正式数值前被静态parse拦截，一次局部修复/all-phase input test后运行，旧28a8 source没有formal负载。原失败resource与blob/hash记录均保留。

F4 zero路径会直接返回精确零、不调用backend；原报告字段沿用前次`audit.last`，数值zero检查正确但该附带native_audit不是本次。交付前仅修正记录条件，旧raw不改、v2置null并明确说明；算法、误差门和已运行source不变，不因报告修复再作正式数值重放。

首次广一点的affected input-schema检查为57pass/2fail；两个fail在精确起点a76e0435a40139dd6d2a31f0726fb229c7adaff8旧input_schema与README上复现：字段97预期/110实际，README行102实际/115预期。这是继承schema2文档枚举不一致，未增公共字段，不修改无关旧合同来制造全绿。受影响targeted regression56通过及最小input tests通过，见[前期检查](records/shared_preimplementation_checks_v2.json)。全仓pytest、MPI2/4、本任务GPU和F5物理验算not_run；用户仅授权共享受控阶段，任务仍禁止邻heavy下full pytest。没有CI声明。

各安装/probe/数组/serial FE接口/静态采样完整wall/RSS/swap、source和worker hash见[auxiliary账](records/auxiliary_costs_v2.json)；数值组件单列[run index](records/run_index_v2.json)，不重复相加同阶段RSS，不以pytest内计时替代监督wall。原F0记录在[历史bounded runs](records/bounded_f0_runs.json)、[原static](records/static_checks.json)、[原publication](records/publication_checks.json)完整保留。

所有测试和后处理Math threads1、仅自身nice/idle I/O、fresh现场选核及bounded监督。最终Markdown本地实际生成HTML并核对表格/标题/链接；local markdown-it的math按code展示，推送后用GitHub真实math-renderer核对，不能只凭本地预览宣称公式显示资格。

最终协议/表示/监督器44 passed（11 deselected），小型FE/80mode/默认与noncommuting/BAL_H18 passed（1 deselected），治理/文档27 passed。额外旧总账checker为1 failed：其40节固定序列和旧Task038缺失evidence在精确a76已存在；Task042表头缺失已在V2局部补成统一格式，基线对比当前无新增错误。[完整基线proof](records/registry_contract_baseline_v2.json)保留原失败及修复后剩余两项错误，不删历史章节、不改测试期待，也不称全仓全绿。Ruff0.16.6对20个新源/协议/测试文件通过，41个相关Python定向compile、bash与diff通过；没有重新运行昂贵F1–F4。


## V3 最新有限诊断的实际检查（V2历史完整保留）

| 检查 | 实际结果 / 范围 | 证据 |
|---|---|---|
| 前期pure/准入 | 48纯数组/协议/表示/几何、4准入与自有监督；首次lint阻断未执行tests/FE，全部尝试保留 | [辅助成本](records/auxiliary_costs_v3.json) |
| FE小接口 | ABI/complex128/int64、几何MPC主从支撑、原borrowed witness/80mode/default，4 passed；未重跑teacher/F1正式算例 | 本地tmp/task042/v3/overlap-fe-support-tests、[环境](environment_and_isolation.md) |
| 最终pure/source | 49 passed；11个相关Python定向compile，10文件Ruff无问题，input_schema仅对经proof的ISC004/RUF022作本次限定；bash/diff通过 | tmp/task042/v3/final-array-checks-complete；[继承schema lint proof](records/schema_lint_baseline_v3.json) |
| 资源测试真实失败 | 首次汇总observed_child_pids只记1，但原RSS样本含2后代及setsid孙进程，触128MiB测试门并整树清场、sibling仍活；另一次修复后lint未使用变量失败保留 | [原始样本与修复](records/watchdog_test_evidence_v3.json)、辅助账 |
| 资源测试最小修复 | 只把测试断言改为原始整树samples的后代/setsid证据，监督器与数值实现不变；49项重跑通过，不重跑任何数值 | src/test/test_task042_shared_watchdog.py；[冻结源码 proof](records/static_checks_v3.json) |
| 新正式残差 | 3项各0..256每步，reported/显式/独立native/port/internal与恢复，原字段重算5条件全部<=1e-10才passed，三项failed | [Gate](records/gate_decisions_v3.json)、[完整CSV](records/full_residual_history_v3.csv) |
| 文档/治理/原历史 | 定向治理/表格测试与V3独立表格/链接/围栏/Gate/hash/source/旧正文保护；结果见static，不冒充全仓CI | [独立static](records/static_checks_v3.json)、[继承registry proof](records/registry_contract_baseline_v3.json) |
| GitHub发布 | 首次push后实际exactHEAD richText表格与math-renderer，最终文档bytes保持一致；见实际检查，不称像素截图 | [publication](records/publication_checks_v3.json) |

扩大Ruff范围时input_schema原有12条诊断（11 ISC004、1 RUF022）与本轮起点d42逐项源码片段一致，未改旧schema错误。原schema字段/README枚举及总账40节/Task038历史问题不因V3改为green；registry检查当前与起点的错误相同。raw失败尝试完整保留，未放宽数值Gate或迭代预算来重跑。

全部检查单核math1、nice10/idle I/O、fresh现场核与自身2GiB整树监督；辅助wall/RSS/swap/source/命令/失败均在新v3账，V2记录逐字保护。新数值仅两个分进程阶段，CPU12 reuse、CPU0 structure，真实clean source各自绑定。旧16heldout消费边界、fresh未运行、teacher/训练/误差空间/F5/正式物理/GPU/短波not_run。未运行full pytest、MPI2/4，也没有CI声明。辅助峰为顺序树峰的最大，不是会话总峰；编辑/Git/审阅未持续采样。

V3治理/文档表格定向测试28 passed；registry当前继承两项错误与d42完全一致。首次独立static因其结果文件尚未生成而报告三处自身链接缺失，真实FAIL副本和辅助尝试保留；生成结果文件后仅重查静态链接/Gate，不重跑数值。

## V4 最终有界检查（V1–V3正文逐字保留）

| 检查 / 身份 | 实际结果 | 证据与范围 |
|---|---|---|
| 执行前相关协议/局部PC/准入/监督 | 57 passed；affected algebra/Gate 9 passed；FE monitor/ownership/full80/default 6 passed | [pre-run记录](records/pre_run_checks_v4.json)，均有界单核，未重复F0环境安装或旧384 teacher |
| P4隐私局部修复 | 6 passed、1 deselected；source core blob未改、未生成fresh数组 | [修复记录](records/p4_privacy_repair_v4.json)；不重放P0/P1 |
| 最终affected + Markdown | 17 passed in 1.04s | `tmp/task042/v4/final_focused/worker.log`；两层5、独立Gate5、monitor2、Markdown5，真实PETSc小fixture无FE JIT |
| 最终ABI | complex128/int64、MPI1、PETSc3.19.6；资格化activation/独立src与缓存 | `tmp/task042/v4/final_environment_fe.json`；preflight在pytest前，原生prefix仅只读 |
| 真实P0/P2算法资格 | rank4及双rank128、真实原S/native配对、四恒等式通过 | [空间/真实代数](records/coarse_space_algebra_v4.json)；不是收敛资格 |
| 真实P1/P3独立checker | 16train/128误差的teacher与S-error关系合格；两路线strict0/3，P4未解锁 | [快照](records/training_snapshot_manifest_v4.json)、[独立范数Gate](records/gate_decisions_v4.json)；六次负结果不改为成功 |
| 静态检查 / 历史保护 | 新10文件Ruff/format-check、11文件compileall、diff，101旧文件byte-exact；summary旧suffix、test_summary/项目总账旧prefix | [final static](records/static_checks_v4.json)；仅检查V4局部链接/表格，不做全仓清理 |
| 继承总账checker | Review333f与当前错误、实际41节数一致，BASELINE_IDENTICAL_NOT_GREEN | [基线proof](records/registry_contract_baseline_v4.json)；40节固定序列与旧Task038缺失路径仍继承，不改期待或伪称通过 |
| GitHub实际表格/公式 | Review333f的7表/5math-renderer检查已通过；V4发布后按实际提交检查 | [Review render](records/review_render_check_v4.json)；publication记录与原源码/Markdown哈希绑定 |

所有测试/聚合/后处理顺序在Task042 own lock、现场单核/math1、2GiB有界辅助监督中执行，own swap0；费用与原失败尝试见[本批辅助账](records/post_checks_v4.json)，不叠加嵌套timer。静态helper首次因相对Path不符合checker接口失败，保留1.98289s/38633472B/清场证据；只修正绝对路径并重查静态，没有数值重放。正式六阶段整树wall1534.00828393s、最大同时RSS1128828928B；共享工作站成本，不宣称CI、全仓pytest或无争用加速。正常数值停滞没有当bug，未重试、未扩参数或重跑旧昂贵Gate。full repository pytest/MPI2/MPI4/新teacher/训练/P4/F5均not_run，本批数值入口仅MPI1。


## V5 固定对象诊断检查（历史正文逐字保留）

| 检查 | 真实结果 / 限制 | evidence |
|---|---|---|
| 执行前相关pure/core/适配/协议 | 55 passed in1.50s；另9 adapter/准入/monitor/orphan监督通过，原default/full80/source不改 | [前检](records/pre_run_checks_v5.json) |
| 反例与正常例 | 旧四恒等式不保证补空间；复杂相位/尺度/零/不可变/精确小LS验证 | 新test_task042_fixed_localization.py；不把toy当FE结论 |
| 真实D0/D1 | 12可用，9历史native exact；3旧参考原A4/port/恢复<=1e-10 | [状态](records/common_state_manifest_v5.json)、[teacher](records/teacher_exception_v5.json) |
| 原同向量独立审核 | 24作用/192原方程审核/2补空间full-image重算合格，solver strict0/192 | [独立Gate](records/independent_checks_v5.json) |
| 最终文档/静态 | Markdown5；新8文件Ruff与5新文件format、9compileall、diff；继承schema及registry错误同Review91 | [static](records/static_checks_v5.json)、[baseline](records/registry_contract_baseline_v5.json) |
| 历史/隐私保护 | 原task/review/response/records逐字；summary旧suffix、test/总账旧prefix；基与冻结核hash不变、seed420620未消费 | static与原unconsumed plan；无全仓cleanup |
| 真实GitHub表格/公式 | Review91的5表/7math-renderer通过；新文档发布后实际HTML绑定推送HEAD | [review](records/review_render_check_v5.json)、[publication](records/publication_checks_v5.json) |

早期FE .venv无ruff模块，子命令真实失败；改用已有只读ruff0.16.6后修复一处新RUF005风格，未安装/重放数值。失败尝试全部保留[辅助成本](records/post_checks_v5.json)。四新FE阶段wall1144.401529s、最大同时树RSS1135407104B/own swap0，源`5d82651af0f723c73487783deb43969f05d46ed3`；所有成本shared-workstation，嵌套计时不相加，总会话编辑/Git/RSS未持续采样。full pytest/CI/MPI2/MPI4、旧teacher384、训练/新KSP/fresh/F5均not_run。


## V6：材料独立的神经FE接口检查

最终23相关pytest通过（几何／未知材料／input opt-in／复数梯度／Basix完整矩／原shared组件与orphan监督）；两项CPU-only ML无fixture断言通过，实际OpenBLAS和Torch intra/inter-op1。新增代码Ruff/format、compileall及两dat校验通过。初次预检查2项配置字段失败、2项complex空气波数失败、ML缺pytest均保留；标准库执行相同两断言，未安装环境。正式FE第一次因原[0,L]载体与新居中范围不符失败，唯一research坐标修复后FE／ML各一次成功，不扩大数值预算。

实际FE矩／MPC配对约1.8e-15，非平凡orientation96 cell／5类；NN q15/30差1.1695e-15，非零合成非Hermitian192trace＋3port的三实方向FD最大9.7612e-9，chunk／一体梯度差6.8049e-16。真实0.7nm S/Sᴴ、native/port/恢复、NEURAL/FREE/LSQR／参考／场／功率not_run：材料缺失；不称完整N1或物理解通过。独立聚合只重算已存FD字段、canonical tags和hash，不重放FE或网络。

[pre-run](records/pre_run_checks_v6.json)、[C1静态](records/precommit_static_v6.json)、[唯一正式修复](records/centered_geometry_fix_v6.json)、[C2静态](records/centered_fix_static_v6.json)、[接口](records/adjoint_gradient_checks_v6.json)、[源／资源](records/run_index_v6.json)、[精简checker](records/independent_evidence_checks_v6.json)。Review V3实际GitHub4表／4math渲染通过。最终文档／原权威保护／继承registry baseline及发布检查另列；不执行full pytest、MPI2/4或旧campaign，不声明CI。


## V7：真实材料、真实N1、三路线及盲验证

| 检查／实际范围 | 真实结果／边界 | evidence |
|---|---|---|
| 四波长材料回归 | 7通过；原decimal/复平方/正吸收符号/历史一致/单alias/未知拒绝/离线；无四波长PDE | input/materials/si_optical_constants_v1.json、test_optical_material_table.py |
| 真实N1 | 原S/SH/native/nonzero内部+port/恢复配对<=8.491e-15；三方向9FD最大1.8213e-9、chunk0 | [real检查](records/adjoint_gradient_checks_v7.json) |
| 固定预算／ML回归 | CPU-only FP64完整2000closure/Adam500断言，small gradient不作pass；既有ML无pytest用标准库执行原断言，不安装 | tmp/task042/v7/optimizer_final_regression/worker.log |
| p3参考接线与最小修复 | 首次29相关pytest；UFL Form除法后4个targeted通过，恢复后仅FE/EH/功率25.633s，无新LU/solve；14.456s失败保留 | [原参考／重放](records/independent_blind_validation_v7.json) |
| 最终相关pytest | 32 passed in1.85s；真实材料/complex action/LSQR/CSR/有效UFL forms/独立Gate反例/trace/basix | tmp/task042/v7/final_focused_tests/worker.log |
| 独立数值checker | 忽略saved status，从原审核字段/复E/H/全port重算；0/3方程/场/功率通过，参考准确；未重复FE | benchmarks/neural_fe_gate_check.py、[独立决策](records/neural_fe_gate_decisions_v7.json) |
| 静态／历史／文档 | 新增相关Ruff/format/compileall、局部表格/链接/公式及原authority/records byte保护，最终记录另列 | records/static_checks_v7.json；无全仓清理/昂贵回放 |
| Review V4实际GitHub显示 | 4表/1math-renderer、列一致，review未修改；新文档发布绑定实际commit和Markdown hash另列 | [review](records/review_render_check_v7.json) |

测试命令一次不存在文件名no tests ran/2.281s，随后更正真实路径并通过，费用保留；一个纯metadata查询把epsilon属性误称epsilon_r已更正，loader/材料/FE未变化。所有正式source/失败/修复/训练预算及辅助成本见[run index](records/run_index_v7.json)、[费用](records/resource_costs_v7.json)。32测试不代表三路线收敛或CI；本批MPI1 only，无full repository pytest/MPI2/4、环境安装、旧campaign或继承checker全仓清理。旧封存seed420620未生成/读取/消费。


## V8：停机事务、列尺度、batch等价与raw Gate

最终16个pure-array/输入边界pytest通过；另2个compact损坏状态反例通过，7个实际strong-Wolfe/初始/非有限/Adam/一致磁盘重载测试通过，tiny矩/VJP batch测试及原2000 closure预算小数组回归通过。真实C3三参数状态、非零端口、full trace/loss/grad/clone Adam/FD通过；C2原方程和独立物理资格均失败。新checker从raw absolute/norm/复observable/FD重算，未信任status。任务范围Ruff/format/compileall/差异/本地新文档合同/历史字节保护结果见static_checks_v8.json；Review V5实际GitHub4表/2公式，新文档publication见publication_checks_v8.json。原无关checker问题不全仓清理；full pytest/CI/MPI2/4及旧campaign均not_run。

所有测试、CLI参数错误与C4字段重名汇总失败均计入resource_costs_v8.json；修复仅局部元数据/IO，无昂贵FE重放。C2初次额外未用moment包披露且保存实际RSS，修正输入边界不改数值结论。16pytest不包含ML环境中没有pytest的7事务测试；各自不同环境分列，不夸大CI。


## V9：固定误差定位的验证与失败记录

最终23相关pure-array/packet/共享监督/列尺度pytest通过，clean e21af767d3522af531ad83c45eacc1df252566c9。7个受影响测试在checker最小修复后通过；初版5 helper测试、一次小fixture total资格错误断言、一次错误文件名no tests ran及随后的有效测试均保存费用。非Hermitian复数、非零内部特解/端口、非零参考残差、物理z不重复缩放、输入不可变、原native/增广符号、强抵消运算尺度、坏raw/status不被信任均有反例。

真实六状态S/恢复/原方程/MPC/全FE区域与交叉项通过1e-10；全部独立最大差1.60056e-11。首次正式stage checker平方恒等式分母错误失败保留，e21只修复运算尺度、只重放数组checker；未重算FE。参考原残差不置零，完整40通道和192/8/48/136区mask真实核验。FE preflight首次sandbox MPI socket失败，随后同只读ABI complex128/int64/MPI1合格，无升级/重装。[状态及独立Gate](records/gate_decisions_v9.json)、[资源](records/resource_costs_v9.json)。

新相关文件Ruff/format、compileall、one-run输入、本地表格/链接/公式、旧authority/response/records字节保护见[静态证据](records/static_checks_v9.json)。Review V6 GitHub实际5表/6math-renderer，review未修改；新文档发布检查见publication_checks_v9.json。旧V7/V8求解仍失败，不重跑teacher/训练/LSQR/参考LU；full repository pytest/MPI2/4/CI not_run。


## V10：薄输出头、端口闭合和自主监督

| 检查／真实范围 | 实际结果及边界 | evidence |
|---|---|---|
| 最终pure-array/task-focused回归 | 25 passed in5.54s；复非Hermitian、原packet/recovery特解、薄LS、Hhat闭合、原时间窗、整树超时/RSS清场、材料和raw Gate反例 | tmp/task042/v10/delivery_focused_tests_final/worker.log；clean b6546d762f5749ceca24b28e60ad4c380adc6741 |
| ML原矩/真实输出头小回归 | 三非零复系数，最大1.2314e-15；orientation/非对角Piola/owner/partial batch/实虚序一致；无pytest安装 | records/final_ml_mapping_v10.json |
| 真实pilot线性映射 | B1/B0各三个固定非零见证最大6.265e-16，真实保存trace再生差0；三见证补核在B冻结后，时序偏差不追溯改写 | records/head_mapping_and_rank_v10.json |
| C真实Hhat/原S/gradient | cond13284≤1e10、三solve与三块重组通过；三方向×三h非零FD最大1.088e-8≤1e-5 | records/port_closure_checks_v10.json |
| 独立数值checker | 从原审核、raw selected复E/H、全部total/scattered复通道和功率重算；四候选无P/P+、全部NOT_QUALIFIED，未信saved status | records/qualification_and_dispatch_v10.json |
| D2最小修复 | mappingproxy序列化一次修复，保存向量重放而非FE重装配；原数值/source/失败保留，重组最大1.69745e-14 | records/volume_balance_diagnostic_v10.json |
| 静态/历史/显示 | task新文件Ruff/compileall、one-run输入、diff、Markdown/链接、旧authority/结果byte保护；Review V7真实3表/5公式 | records/static_checks_v10.json、review_render_check_v10.json、publication_checks_v10.json |

一次ABI CLI错误、post线程探针库数量断言及compact括号/嵌套选核错误都记录失败并局部收口。没有重跑V7/V8、旧teacher/F0/长KSP；本批数值停滞不当作bug。新checker加入raw selected样本重算后最终25项重跑，之前24项费用保留；ML无新代码变更不重复昂贵Gate。共享工作站单核/mathTorch1/自有树监督，full repository pytest/MPI2/4/CI not_run。


## V11：稳定头、真实回收与独立 Gate

| 检查 | 结果／范围 | 证据或边界 |
|---|---|---|
| pure-array targeted | 最终 `12 passed in 0.24s`，覆盖复数头／端口小代数、V11固定数值协议、独立raw checker；checker最终source `c6c650ad18f278aa1a33cddd9395f899104b3bc2` | 命令 `source scripts/activate_task042.sh pure && python -m pytest -q src/test/test_task042_v11_checker.py src/test/test_task042_v11_stable_varpro.py src/test/test_neural_linear_head.py src/test/test_neural_port_closed_head.py` |
| 损坏证据反例 | saved success 标签不能覆盖坏制造残差；满秩不能覆盖实际残差差；坏散射场、缺端口、坏体吸收差均判失败 | [原始字段独立判决](records/qualification_and_dispatch_v11.json)，`src/io/stable_head_varpro_check.py` |
| ML矩与真实输出层 | V11实装前原 `test_neural_linear_head_ml.py` 小脚本通过，ML环境无pytest；真实主路径在MAIN中三个非零映射见证先于LS，回写及M1/M2另由原作用审核 | [进度](records/varpro_progress_v11.jsonl)、[制造](records/manufactured_recovery_v11.json) |
| 真实数值 Gate | M1通过；M2修正后2.89518e-8＞1e-8；S2实际网络对薄模型差3.95983e-8＞1e-8，S3真实FD0、S4接受0；REF7后验证原方程/场/功率失败 | [完整结果](stable_head_varpro_v11.md)、[run index](records/run_index_v11.json) |
| 静态与文档 | 受影响Python `compileall`、`git diff --check`及本地表格/链接/公式检查；Review V8实际GitHub richText5表／5数学块、列数一致。资格化环境无Ruff，未声称通过 | [静态检查](records/static_checks_v11.json)、[review渲染](records/review_render_check_v11.json)；结果页面发布检查单独记录 |
| 未运行 | full repository pytest、MPI2/MPI4、CI、真实FD/隐藏更新、p4 enrichment/最大模型 | 前两者超出本批局部验证需求；后者因数值Gate或范围不准入，不能写成通过 |

MAIN `stage_result` 的同名 `physical` 元数据覆盖数值键由已保存journal与下一REPLAY before找回；代码在REPLAY source只修序列化名，不改变原数组或旧raw。一个同分解数值修正仍失败，不把数值停滞伪装实现bug再重跑。最终相关测试在checker改动后重跑；不声明GitHub Actions或全仓测试通过。

本地历史字节核验的首次临时helper误把本轮尚未提交的`response_v11.md`列入`git show HEAD`而报路径不存在；修正筛选后，原task、全部旧review与旧response共19文件逐字节等于本轮前HEAD。该辅助错误没有修改历史、数值数据或重跑正式阶段，见[静态记录](records/static_checks_v11.json)。

## V12：固定头真实损失、受控分流与独立证据检查

| 检查 | 本批实际结果与适用边界 | 证据 |
|---|---|---|
| pure-array/已有监督 targeted | 实现 clean 前相关14项通过；最小两次接线修复后受影响5项通过。checker 新增后最终 **26 passed、1 deselected（3.58s）**；排除项是ML专属隐藏赋值测试，在ML环境另直接断言通过。无 full repository pytest、MPI2/4 或 CI 声明 | 命令 `source scripts/activate_task042.sh pure && python -m pytest -q src/test/test_task042_v12_checker.py src/test/test_task042_v12_actual_loss.py -k 'not hidden_assignment' src/test/test_task042_v11_checker.py src/test/test_task042_v11_stable_varpro.py src/test/test_task042_shared_watchdog.py src/test/test_task042_shared_components.py src/test/test_neural_linear_head.py src/test/test_neural_port_closed_head.py` |
| ML 环境实际检查 | CPU-only PyTorch，intra/inter1、OpenBLAS实际线程1、DataLoader0；同一γ在 `set_hidden` 后重写并 hash 相等，小非Hermitian固定头解析/FD相对差`1.393e-9` | `.venv-ml`未装pytest，使用资格化 activation 的直接断言；不把 pure pytest 算成 ML pytest |
| 真实物理数值 Gate | batch1/batch8完整loss分辨率`2.22e-14`；三方向真实FD30点未达`1e-5`稳定区；F8试探无下降；T4只验旧基线原方程/40通道/功率仍失败 | [梯度](records/fixed_head_gradient_checks_v12.json)、[分流](records/qualification_and_dispatch_v12.json) |
| 受控监督与失败保留 | 原自有watchdog测试含超时、setsid后代RSS触线并保护无关sibling；V12五次one-run后代均清场。首次旧探针MPI socket失败、第二次日志参数冲突保留，不改原raw | [逐run索引](records/run_index_v12.json) |
| 独立checker的坏证据反例 | 坏解析梯度、gamma hash变化、损失不降却标接受、错端口、缺40通道均拒绝；真实raw状态一致性PASS，但梯度与物理资格均false | `src/io/actual_loss_block_descent_check.py`、[raw判决](records/qualification_and_dispatch_v12.json) |
| 静态、输入与显示 | 三个one-run dat明确验证、`compileall`、`git diff --check`通过；Review V9 本地GFM表格/围栏/相对链接检查见compact记录。隔离环境无 Ruff；GitHub实际网页无法取得，标未核验 | [run source/输入](records/run_index_v12.json)、[渲染记录](records/review_render_check_v12.json) |

V12 的正式计算源码是 `d9df7068ca3310a0499164251a57841dbdfbc7f5`；随后checker和文档提交不冒充该源码。数值目标未过，不能因为单个小测试或checker一致性PASS而称 solver PASS。旧task、review、response和V1–V11 raw未改。
