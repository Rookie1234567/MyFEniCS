# Task43「自适应 h/p 网格研究」正式 V2 审阅报告

审阅日期：2026-10-24（Asia/Singapore）。本报告直接审阅固定提交的源码、任务合同、测试和 Git 中轻量证据；不以执行方总结或其 root 审计标签代替独立核查。

## 1. 正式决定

**接受本轮有明确范围的工程整改和证据整理；维持 PARTIAL / CONTROLLED_NEGATIVE。独立精度仍未通过。先完成第 10 节无新正式 PDE 的前置门，再有条件授权 A1_q attempt2、A2_q attempt3 各一次；本次可执行累计上限为 5/6。生产合并不批准。**

| 决策 | 本次裁决 | 准确含义 |
|---|---|---|
| 整改验收 | **有条件接受，部分通过** | 三项已发生故障有针对性修复；Q03/Q04/Q06/Q07/Q08 的限定整改通过。Q01 科学目标未通过，Q02 生产回归门和 Q05 严格冻结时序仍部分通过；另有 primary 留证、Av 规则和启动清单完整性三项 P2 前置要求。 |
| 继续计算授权 | **条件放行两次 q 诊断，当前不可直接派发** | 前置门通过并冻结新补充合同后，依次最多一次 A1_q2、一次 A2_q3。A2 子额度明确由 2 调整为 3；历史失败不抵扣。R、B/C、成本 campaign 和迭代均不随之开放。 |
| 合并资格 | **NOT_APPROVED** | 可保留研究分支及负结果归档；未取得 production/default 资格。本报告只新增审阅文档，不合并、不提交 master。 |

提交证据记录了 **3 次正式调度，其中 1 次到达 PDE 与部分输出，0 个合格完整 V2 端点**。这不构成“三次 h/p 方法失败”。继续工作的目的，是取得能区分 q 扰动和工程故障的完整证据，不是修改旧容差、凑第十次接受或保证在剩余额度内完成整个研究。

## 2. 对象身份、审阅方法与访问边界

### 2.1 固定身份

| 对象 | 完整身份 |
|---|---|
| 仓库 / 执行分支 | Rookie1234567/MyFEniCS / task43_hp_adaptivity |
| 本次送审 HEAD | **fd4a63098893a82374f43f8c3066b74285e9c020** |
| 送审 tree | 8ae80e8d9bf9ffc035b49154c6b4eafa4fbaf51c |
| 送审 HEAD 的父提交 | a879554d7149bef1187b31bd731b09629f33fef3 |
| V1 正式 review | 7458fadccde01d37ed93187ebe4c39177783d60b |
| V1 被审代码 | 5f89dd2ba35f067593983d1a68f845de965dfb6b |
| 原代码基线 | 405e3aff42ac421a4c99315df1ed9b96941ecbe4 |

独立读取远端分支、commit、完整 recursive tree 和 compare：送审分支指向所给 HEAD；相对 V1 review 为 ahead 15、behind 0，共 46 个变更路径，V1 review 是共同祖先。执行方“工作站干净、与 origin 0/0”的工作树状态没有在本次工作站现场重验；远端身份一致不等于已经核验其本地工作树。[提交差异][DIFF]

完整阅读根、docs、任务目录的 AGENTS；任务 README、task、baseline_audit、codex_handoff、V1 review、V2 diagnostic_plan 与三份正式机器合同、response_v2、summary、selective manifest，以及重点 records。两份模型/进展总账遍历全文并核完整差异：registry 1853 行、progress 3097 行；新内容集中于文首 Task43 段，旧余文保持。[任务][TASK] [诊断计划][PLAN] [总账][REGISTRY] [进展][PROGRESS]

### 2.2 本次实际做过的核验

- 按固定 tree 的 Git blob 验证取得的源码/文档字节；对 root_final_review_audit_v2 的 105 个索引对象，实际核对 **78 个 tracked 文件**的 SHA-256 与 Git blob，全部一致；其余 **27 个 ignored 原件未取得**。
- 独立脚本完成 10 项身份、历史保护、逐项成本和交叉 hash 断言；64 个 V1 保护文件字节不变，且不在本轮 46 路径变更集合内。
- 重算历史 56 个唯一成本条目、旧 18 行与 15 个正式 solver 条目的对应关系、新 3 次正式调度小计、legacy 3 次恢复/采样小计。
- 直接检查新 comparator、legacy resampler、A1 observer、A2 adapter、native P6 runner、watchdog 和相关测试；另执行 6 项 AST 隔离纯函数检查和 4 项 reporting 边界断言。这些是本次审阅的纯检查，不是工作站 pytest 或数值资格测试。
- 本地没有 pytest、mpi4py、petsc4py、DOLFINx；**没有执行 fresh PDE、完整模块/native ABI 导入、工作站 pytest、原始场重新积分或 MPI 端点重放**，也没有安装或重建环境。

**工作站原始 watchdog/worker 日志、launch JSON、ABI/ldd、矩阵、完整场和 612/836 通道原数组：本次未独立核验。** 本报告能够确认 Git 中记录的字节身份、算术、内部一致性和与源码的对应；不能把原件 hash、执行方摘要或其“root 已审计”当作本审阅亲自重算原件的证明。第 5 节的资源、退出码和现场数值均以“轻量记录报告值”引用。[执行方 root 索引][ROOTAUDIT] [收口记录][CLOSEOUT]

Git 本身也不能证明工作站不存在第 4 个未入 Git 的正式启动目录。本次没有发现额外正式调度的证据；继续前必须在 canonical 工作站对 launch/attempt 目录做一次只读枚举并补出完整计数依据。

## 3. V1 Q01–Q08 逐项裁决

“通过”均限表中所列问题的整改范围，不能累加成任务整体通过。

| V1 问题 | V2 裁决 | 具体证据与验收边界 |
|---|---|---|
| **Q01：精度及较少 FE 的联合目标** | **未通过；诚实保留结果这一项通过** | accepted9/R9、R10 拒绝、独立 holdout 失败和原失败链均未改；旧样本重放、旧系数重采样、重新积分和 fresh PDE 已分开。三次新调度没有合格端点，故不能解除 Q01。[V1 review][V1] [正式尝试][FORMAL] [旧场重放][REPLAY] [重采样][RESAMPLE] |
| **Q02：全仓收集、ABI 与共享路径回归** | **部分通过** | 原 8 个错误已有准确索引；干净 tracked checkout 仍有 SLEPc 冲突。直接路径的小组件与 MPI2 采样补证有效；生产/full-suite 门未关闭，见第 8 节。[Q02][Q02] [八项错误][ERRORS] |
| **Q03：selective merge 依赖闭包** | **通过，限依赖表整改** | 原 A→B→C 错误分拆已改为 27 文件首个原子核心组；共享 config、geometry、IO 等依赖纳入。旧 overlay 不冒充新 A2 接线资格。仍不是合并许可。[manifest][MERGE] [闭包记录][CLOSURE] |
| **Q04：56 份终态成本与恢复费用** | **通过，限轻量账闭合** | 56 个唯一 path 可逐行重算；restore 有独立路径/hash/166.96172243729234 s，不再只能倒算。R8 部分窗、测试、支持工作和新 3 次调度分账；原件及完整 campaign 仍未外审闭合。[成本表][COST] |
| **Q05：冻结内容与冻结时间** | **部分通过** | 合同 hash 一致与时间证明边界分开；未发现实际运行源码之后倒改阈值。首候选前严格时序仍缺独立证明，不能由 mtime/Git 共存补出。V2 主合同最终字节从 ed95df3 起一致，不是从首次 68ed596 起一致。[冻结证据][FREEZE] [主合同][CONTRACT] |
| **Q06：p3 方向/子单元测试** | **通过，限两个组件节点** | test197 两处 degree 参数加入 p3，分别覆盖 8 个 D4 和 256 个 oriented-child 组合；与最终测试/source hash 对应。不能外推一般多层 h、任意 cross-h 或完整模型 MPI 能力。[组件记录][Q0607] [测试][T197] |
| **Q07：R8 缺失终态例外** | **通过，限该 reporting 路径** | 必须精确 attempt=round8_p 且 resolved run root 匹配；其他缺 summary 拒绝。旧 partial 值从 hash-bound audit 读取，不复制到任意缺失记录；R8 完整终态仍未知。[helper][SCOPE] [库存生成][INVENTORYCODE] |
| **Q08：文档/总账/测试版本一致性** | **通过** | 旧 5 passed 的 0.08/0.11 s 已分阶段；最终另有 5 passed/0.06 s，不能互换。两份总账、V2 response、summary 和 compact 保持同一失败分类；64 份 V1 权威/负证据不变。[文档测试历史][REGTEST] [收口][CLOSEOUT] [root 索引][ROOTAUDIT] |

## 4. 按严重程度排列的未关闭问题

### V2-01 — P1，科学验收未完成：没有新的合格端点，独立精度仍失败

这是资格缺口和有限方法负结果，不是本次确认的 Maxwell 数值实现错误。R9 独立 FE 110472，比对照 237600 少 53.5050505%，但对 Y5_1 的 J=4.014410424；R10 为 118800 FE、J=2.786521166，仍失败。R10 与 Y3 的一次有限比较通过不能替代 holdout。九次接受保留，不能用新 q 诊断回填 transition10。[原独立比较][POST] [R10 拒绝][R10]

**验收条件：** 最终同时达到空间合法、原方程/代数门、事前冻结的完整物理输出精度及独立验证资格，并满足候选 FE<237600。第 10 节两次 q 诊断即使成功，也只解决其中一个误差来源，不能自行关闭本项。

**最小行动：** 先封闭端点留证和真实入口；最多取得两个 q 诊断。维持原精度状态，不改选择目标、不重新挑有利参考。

### V2-02 — P1，生产合并门：全仓测试体没有得到有效执行证据

原 full pytest 为 1 skip、8 collection errors、0 个测试体。新增干净 checkout 收集记录绑定 V1 review 7458fad，3121 items、1 SLEPc error、0 测试体；不是最终 fd4a630 的全仓重跑。旧 scratch/ignored 收集问题和真实 SLEPc/complex-PETSc 不匹配已分开，但共享路径的最终生产回归仍未取得。[Q02][Q02] [错误索引][ERRORS] [closeout 的未重跑声明][CLOSEOUT]

**验收条件：** 在匹配的生产 ABI 上，对真正拟合入集合及其共享依赖运行有关测试体，并如实报告全仓剩余阻塞。import/collect-only 和 direct helper 不能替代此门。

**最小行动：** 本轮保持 production 锁定即可；不为研究归档或两个限定 direct 诊断重建无关 SLEPc 环境。直接路径自己的 complex/int64、MPI1 和相关组件门仍须过。

### V2-03 — P2，确定的失败留证缺口：primary 已算结果过晚落盘

A1 先保存 pre_validation_checkpoint 的 before 系数；但 primary A6、显式残差和 q8/q10 样本仍在 captured 内存中，随后先执行 extra-LU 与结果广播，成功返回后才写主要样本与完整 record。已发生的 MappingProxy 广播故障正会截断这条证据链。[A1 checkpoint/observer，3284–3422 行][H100OBS] [A1 后写样本，3501–3517 行][H100WRITE]

A2 在 3965–4072 行计算 primary A6/full-active 并记录 ledger 标量；4087 行开始 extra，raw primary residual/RHS 与样本却要到两端输出、采样之后才写。extra、recovery 或 sampler 抛错会留下部分日志，但没有保证独立 primary raw packet。[native primary][P6PRIMARY] [native raw 落盘][P6RAW]

另有同一失败语义问题：native runner 在 4440 行先赋 official_result；正常 gate-fail 会降级为 measured_endpoint_output_not_official，4890 行后的异常分支却只改 FAILED，可能留下 FAILED 与 official_result 并存。现有 checker 还要求 passed/hard gates，未发现由此产生假 PASS，但字段可被下游误用。[输出/异常处理][P6FAIL]

**验收条件与最小修复：** primary 测量完成后、任何额外 correction 前，原子落一个有限 before 包：身份、系数/checkpoint 引用、独立 A6、显式/凝聚残差、同 RHS 原向量及正常 correction 记录；已算样本随即持久化。额外阶段失败不覆盖 before 包，并明确 FAILED/INCOMPLETE 与 measured/partial，所有 continuation 标志关闭。用现有 fake Vec/Mat、临时目录和三处故障注入（extra、bcast、sampler）验证可读/hash 不变/不产生合格端点；不需要新 PDE 或新通用控制框架。

### V2-04 — P2，积分规则溯源不完整：A2 的算子 q19 不等于 Av 显式 q19

native opt-in 的 curl/mass 形式 metadata 改为 q19，cfg 只显式设置 incident/port q32。Av 经 recover_p0_outputs 把原 cfg 传到 rta_3d；cfg 未声明或设置 stage4_volume_quadrature_degree，getattr 回落 automatic。[native q 配置][P6Q] [当前 Av][AV]

追到原 Y6 源 6320ae621ddf94d39e9006628a5ef68b0dfdfffe，旧 Av 的 dx 本来也没有 quadrature metadata。因此不能称“旧 Av q15、新 Av q19”；也不能据此断定体吸收错误。对本任务仿射 p6、分片常系数场，自动规则可能已足够精确，本次没有现场有效规则或原场数值支持进一步断言。[旧 Av][OLDAV]

**验收条件与最小行动：** 分开记录 operator、incident、port、Av 的实际规则。二选一补证：取得自动规则的实际节点/精度及对本被积函数足够精确的依据；或用同一 hash-bound 旧场作 auto/q15/q19 三次纯后处理积分，保存规则、数值与差值。若仍无法证明满足冻结 q19 的输出口径，只在 Task43 V2 opt-in 接入 Av q19，并补实际 form metadata 组件门。旧 Y6 automatic 事实不得回写成 q15；新接线只前瞻生效。比较所需原场不可读，或没有有效规则/积分补证，则 A2 不派发。

### V2-05 — P2，审阅证据边界：终态原件与“仅三次”的完整性未独立证明

三条 compact 的 source、input hash 入口、退出码、清理和 RSS 相互一致，源码也解释了失败原因；但现场原件未取得，不能独立逐样本重算峰值、重放进程清理或排除其它 ignored dispatch。[正式记录][FORMAL] [root 索引][ROOTAUDIT]

**最小行动：** 下一次启动前只读枚举 canonical attempt/launch 目录，逐条列明正式/支持类型、phase、编号、启动时间、源码/合同、terminal 路径与 hash；发现遗漏正式调度立即计入原账，停止使用本文基于 3 次已用量的新增分配。新端点提交可外审的逐项终态/采样统计与 checker 摘录，大原件仍留 ignored。历史 R8 终态、h1 辅助 ABI 或旧时间线无法取得时继续标未独立核验，不能补造，也不作为其它已独立满足门的新 q 诊断的全局否决。

### V2-06 — P3，阶段标题可更清楚

summary 的“最终本地检查”宜标为 V1 历史；manifest 的“当前代码身份”宜显式写 Stage1 fad2df0。上下文已有分段，未发现实际把旧记录冒充最终全套重跑；后续用新增说明澄清即可，不重写历史失败。

## 5. 三次正式失败及三项修复

### 5.1 调度、终态和费用

下表为提交轻量记录的报告值。本次核对其算术、路径/源码身份及源码故障机制，未重新量测现场。

| 调度 | source HEAD | whole-watchdog 秒 | sampled process-tree RSS 峰值（字节） | 到达阶段 / 资格 |
|---|---|---:|---:|---|
| A1_q1 | ed95df3370973c2f06168ed938666250587ece6d | 4882.447373806033 | 9708847104 | 已求解和部分输出；observer 嵌套 MappingProxyType 经 mpi4py object broadcast 失败；无完整端点 |
| A2_q1 | a3657ca1f82fbac0b18aead39ad78285b0887c38 | 18.740401392802596 | 190795776 | watchdog CLI 未传 phase path；网格前失败 |
| A2_q2 | 5b23aabe839effc1cb18f8a31820ea83219ec8d4 | 13.984614439308643 | 190918656 | ABI/phase 检查后，旧 Y6 profile 缺 display_label；网格前失败 |
| **三次合计** | **3 个正式槽位** | **4915.1723896381445** | 不对峰值求和 | **0 个新的合格完整端点** |

记录分别报告 3930、15、12 个资源样本；WORKER_FAILED、worker/leader exit=1、launcher exit=2、task swap=0、进程树清理完成。源码前后绑定分别覆盖 A1 的 43 项和 A2 的 60 项选定源文件，A2 输入分别 34/42 项；不是“所有运行依赖”的证明。[正式记录][FORMAL] [A1 部分终态][A1]

原 watchdog summary SHA-256：

| 调度 | 原件 SHA-256 |
|---|---|
| A1_q1 | df465af9e3274c343fcf7b28e07130bb1a9ad6bbc776b0c44d7a583b27f89728 |
| A2_q1 | da13ba37df08870e92d52414c6ef979e0ab25cd5fdfce46f06e7bc220304b73a |
| A2_q2 | 7a4fb9e3caa0c79ba97e928f494953abf4ce8c1afee89fb0308a22d61716f894 |

hash 是原件入口，不是本报告已获取原件的声明。A2 的 576 cells、380160 FE=120960 trace+259200 interior、121572=120960+612 rows 均为计划/历史身份；本轮两次没有实际构网、DoF/NNZ 或求解测量。

### 5.2 三项修复是否充分

| 修复 | 源码与测试核查 | 裁决 |
|---|---|---|
| MappingProxy 运输 | h100 的 _plain_nested_containers 对 Mapping/tuple/list 递归转换，保留数组/复数，不修改原对象；before-state、完整 result 广播及 record 都接入。两个测试覆盖原对象不可 pickle、转换后 pickle/JSON 可用。[运输实现][TRANSPORT] [运输测试][TTRANSPORT] | 针对已知故障的修复成立；未完成现场 MPI observer 全链路资格。另须修 V2-03。 |
| watchdog phase path | CLI 新增可选 --phase-path 并转给既有 supervise；默认 None 和原资源/超时策略未改变。测试实际启动 tiny child、写 WorkflowLedger、核绝对路径/父 PID/phase/cleanup。[watchdog][WATCHDOG] [tiny child 测试][TWATCHDOG] | 有效的局部接线修复，不改变数值合同。 |
| 旧 Y6 display_label | 对固定原 profile 深拷贝，仅补缺失 D15-Y6-1 标签；错误已有标签、其它数值/资源 profile 漂移继续拒绝；之后调用原 native validator。调用层先验证真实输入 hash，旧输入不写回。[兼容 helper][PROFILE] [调用层绑定][A2BIND] [helper 测试][TA2] | a879554d7149bef1187b31bd731b09629f33fef3 的局部修复合理；最终组件/真实输入预检通过不等于 A2 PDE 成功。 |

native P6 新 q、额外一次 same-LU、Task43 资源策略及端点输出由显式 task43_v2_diagnostic 开启，默认参数为 None。所审 diff 未发现将研究路径变成普通默认数学路径；normal correction 的旧循环策略保留，但新增记录和较长 factor 生命周期需要最终相关回归，不能以“opt-in”免测。[native 入口][P6ENTRY]

### 5.3 A1 部分数值能支持什么

A1 compact 报告旧 R10→primary 最大通道功率差约 8.1846e-12、复幅组差约 8.2694e-12；primary→extra 分别约 2.5369e-14、3.4571e-14；两端 closure 约 4.10e-12 和 4.05e-12。**有限推断：若保存的这些行值正确，已记录端口输出的 q/回代扰动远小于 1e-7 扰动门，不像足以解释旧约 2.8e-6 功率差的主因。** 原数组未取得，本次没有重算这些行。[A1 部分数据][A1]

缺 primary q8/q10 完整场、持久化的 primary/extra 独立 A6 和完整端点 record，故不能由这组小差异认定 q 或 same-LU 资格通过。日志 5.177423112815622e-13 不能替代原方程独立 A6；更不能排除参考离散、场、R 截断或侧壁误差。

### 5.4 原 A2 重试的配额与授权

A2_q1 后先取消尚未执行的 A2_R，把 A2 组第二槽用于 A2_q2；总额和 A2≤2 都未突破，阈值未改。与此前允许预算内修复、失败/重试照计、规则前瞻冻结的用户授权相容。retry JSON 没有冒称新的 ChatGPT 正式批准。[一次性 retry 合同][RETRY]

该文件首次随 5b23aabe839effc1cb18f8a31820ea83219ec8d4 入库；A2_q2 的 source HEAD 正是这一提交，支持“运行源码包含 retry 授权”。实际 launch 时间原件未取得，不能说已独立重演完整现场时序。旧合同明确 attempt2 后不再 A2；adapter 只接受 attempt1/2，且拒绝 A2_R。**下一次 q3 必须依第 10 节新增前瞻合同和入口约束，不能只改 choices 或借剩余总额度。**

## 6. 科学比较、自由度与五项能力

### 6.1 选择与角色隔离

原选择参考、最终 holdout 和两种 6×10×6 controls 的角色没有因本轮修复而改变。64 份保护文件及九轮接受链不变；没有发现将后验 control 结果回写 marks、阈值或 accepted9 的证据。运行前知识隔离仍受原始时间线访问限制，不能由 Git 顺序证明全部工作站知识。

R10 的 G 改善 8.41290070174027e-6 低于冻结 epsilon_G=9.088158796603444e-6，拒绝仍正确。h10 冻结动作的 interior 下界为 224×240+530×450=292260>237600，足以排除该动作满足 FE 目标；不能外推到所有局部 h/p、各向异性 h 或其它标记策略。[接受合同][ACCEPT] [R10][R10] [V1 审阅科学分析][V1]

已做过真实单层 h1、mixed-p 约束/组装/恢复和独立 action；h1 代数合格而空间精度差。九轮是人工受控、基于实际收益和新增 FE 的选择实验；不等同全自动控制器或一般多层资格。p3 新增两项方向回归补的是明确缺口，不是新增深层 h 验证。

### 6.2 新比较器的核查结论

阅读 compare_v2_endpoints 全文件后，未发现新的 reference 方向、完整库存或弱量归一算术错误。[比较器][COMPARE] [比较测试][TCOMPARE]

- R13 严格 612 键，R14 严格 836 键；缺失、重复、非有限、side/power 与 R/T 聚合不一致会拒绝。完整四组复幅、逐通道功率和 R/T/Av/R00 均入门。
- reference 放第一个参数；复幅分母取参考组 L2 与固定 incident floor 的较大值，无相位拟合。R13→R14 共 612、新增 224 分开；新增键在 R13 为 absent/null，不补零；共同差与 tail 的联合幅度门存在。
- 总/散射 E/H、curl/k0 的 G 比较检查物理身份、相同点权、背景及 H/curl 关系。q10 为主、q8 为稳健性核查，不因此声称积分收敛。
- helper 对给定行做一致性检查，不单独重新推导 modal Poynting/power-carrying，也不单独认证给定采样点覆盖全域。真实端点须另核 mode physics、Gauss 规则、域体积 350000 nm³、点数/owner 与原数组。
- 当前 modal helper 要求相同 discretization hash，适合 A 的 q/R/same-LU；不能原样用于 B/C 跨空间。未来若解锁，只允许有限的跨空间调用层，保留不同 FE 身份和共同物理采样，不伪造同 hash 绕过。
- 垂直四个材料侧壁的双侧单边 E/H 迹仍 NOT_MEASURED，顶部/底部四组端口幅值不能替代。旧 holdout 已揭盲，不能在后续选择中当作全新 blind witness。

### 6.3 旧场工作的不同含义

| 工作 | 实际范围 | 不具备的资格 |
|---|---|---|
| old-field joint replay | 旧 sample arrays 重算 E/H/G/modal；Av 沿用旧 record | 不是重新采样、重新材料积分或 fresh A6/PDE |
| legacy R10 resampling | 由旧系数、原 mesh/P6 carrier 恢复；q8=92160 点、q10=180000 点 | 没有新组装/factor/solve，不恢复原 A6 的现场资格 |
| 固定旧场 Av auto/q15/q19 后处理（本报告要求） | 只重新积分相同系数场 | 不计为新 PDE，不等于新 q 解 |
| A1_q1 | fresh q19/q32 PDE 与部分新输出 | 失败后仍没有完整合格端点 |
| A2_q1/q2 | 正式 dispatch，实际网格前检查 | 没有 PDE 数值结果 |

以上区分在新记录和代码中基本诚实；未来必须继续按实际行为标注。[重放][REPLAY] [恢复/采样记录][RESAMPLE] [resampler 源码][RESAMPLERCODE]

### 6.4 五项能力

| 能力 | 状态 | 本次可支持的结论 |
|---|---|---|
| 空间能力 | **PARTIAL** | 有真实单层局部 h、mixed-p、p3 方向补证；一般多层、侧壁等未资格化。 |
| 选择能力 | **PARTIAL** | 九次接受和 R10 拒绝保留；冻结候选集合内的人工受控闭环成立，未证明一般 hp 最优或 fully automatic。 |
| 精度 | **NOT_PASSED** | 少 FE 的规模事实可信；R9/R10 独立精度未过，V2 无合格新端点。 |
| 同精度全过程成本 | **NOT_ESTABLISHED** | 轻量成本账显著完善；同精度前提、统一生命周期及完整 campaign 不具备。 |
| 迭代能力 | **NOT_RUN / NOT_QUALIFIED** | 本轮 direct、同因子诊断和小组件不能授予迭代接线/收敛资格。 |

独立 FE=trace+interior；carrier storage 包含恢复存储和 Floquet 从属行，凝聚增广矩阵又另加端口行。R9 35352+75120=110472，矩阵 35964；R10 37800+81000=118800，矩阵 38412；控制 75600+162000=237600。这些是不同计数，不可用更小 trace/矩阵或更大 carrier 代替 FE。[统一模型账][MODELS] [DoF 估计][DOF]

## 7. 成本与冻结证据

### 7.1 成本分账与去重

| 账项 | 记录秒数（口径见右列） | 范围 |
|---|---:|---|
| 历史 56 份终态 summary | **63340.73598930752** | 56 唯一路径；15 正式 solver +41 支持/准备/比较等；包含失败和中止 |
| 其中 15 个完整 solver watchdog | 33194.906630876474 | 已包含于 56 份，不再相加 |
| 其中 post-selection restore | **166.96172243729234** | 已包含于 56 份；support_work 再次索引不是新增费用 |
| R8 部分窗口 | 3109.3891972089186 | 2491 样本，窗口 RSS 6844891136 字节；没有完整终态，不是全过程 |
| V1 最后两次测试 | 135.19351344974712 | 单独支持费用 |
| V2 三次正式调度 | **4915.1723896381445** | 与历史 56 路径无重叠；不是完整 V2 成本 |
| V2 legacy 恢复/采样三次 | 152.32824470987543 | 两次支持预检失败加一次后处理成功；没有新正式 PDE |
| V2 旧样本 joint replay | 46.21374210854992 | 新后处理工作，不能冒充旧 restore 或 fresh PDE |
| V2 clean collection / same-LU 组件 | 76.31309780385345 / 156.69584573293105 | 两笔支持工作，不冒充模型尝试 |

56 份中终态分类为 41 COMPLETED、11 WORKER_FAILED、3 USER_CONTROLLED_STOP、1 MONITORING_FAILED，不是 56 次数值成功。本次按条目重算，恢复行原件路径/hash 已补齐；未取得原始 summary，故这是提交轻量账的外审闭合。[成本表][COST] [正式/支持记录][FORMAL] [Q02][Q02]

原参考生成、未监控支持工作、R8 全程等仍有缺口；部分成本 not_measured 必须保留。不同 source、缓存、恢复/重新组装和 factor 生命周期的 wall 不能直接相除成同精度加速。未来完整研究成本还要纳入失败/重试、参考、转移、比较、重建与支持，并保持互斥计费。

### 7.2 内容身份不等于冻结时间证明

V1 acceptance SHA-256 一直为 e589d7c980b4467fc21e13445c4af19202ea662cae9f7277f61e98a3e7702647；新增 snapshot/hash 入口加强内容一致性，但 worker 首事件没有合同 SHA，watchdog 缺可独立对时的完整起点，严格首候选前时序仍未证明。[冻结摘录][FREEZE]

V2 合同须准确描述：

| 合同 | 关键 Git 身份 | 本次结论 |
|---|---|---|
| 主合同 | 初次 68ed596；最终内容在实际 A1 source ed95df3370973c2f06168ed938666250587ece6d | 中途补了 normal correction/primary-extra/raw gates；当前与 ed95 字节一致，不能说自 68ed 未变 |
| native A2 合同 | 647a85afeff121248cdbeecb3700fad93b8ee11d | 当前与首次提交一致 |
| A2 一次 retry 合同 | 5b23aabe839effc1cb18f8a31820ea83219ec8d4 | 当前与首次提交一致；q2 source 包含它 |

三个当前 SHA-256 分别为 33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc、77c533673eba4178868ef22f4a27f8d7ecfbf50d6a47acbcbf2fe45b269960d0、f6b004d30e524a2c3560b6117983762c293602c5ddee8d92f2d9de40ffe073ed。[主合同][CONTRACT] [native 合同][NATIVE] [retry][RETRY]

未发现各自实际运行源码之后倒改合同；Git 提交顺序及 compact 绑定不能替代本次未取得的实际启动原件。无需伪补历史时间戳；下一轮在真实 dispatch 前写入不可变 launch 身份及合同 hash。

## 8. 测试覆盖、工程职责与选择性合并

### 8.1 版本对应，不能合成“最终全套通过”

| 证据 | 与最终源码的关系 | 资格 |
|---|---|---|
| Stage1 focused 40 passed /3 skipped | 相关核心/test hash 可追溯；另有 MPI2 sampling 补三项 skip | 有限旧场/辅助组件，不是全仓 |
| 小空间/assembly/recovery/action 3 passed | 对应源/测试 hash 与最终相同 | 小组件资格 |
| MPI2 sampling 每 rank 4 passed | 同字节采样模块 | 不能相加称 8 个独立测试或整个 hp MPI2 |
| 27-cell same-LU 1 passed | 对应最终共享实现 | 不是正式 A1/A2 端点 |
| Q06/Q07 4 passed | 4 个相关 source/test hash 与最终相同 | p3/报告归属限定通过 |
| native 历史 34 passed | native P6 核和 test40direct 字节与最终相同；adapter/helper 后改 | 有效同字节组件证据，不是最终 adapter 全测 |
| retry wiring 36 passed | 最终 watchdog/test354 同字节；当时 adapter/helper 非最终 | phase-path tiny child 接线证据；此前 35 pass/1 fail 保留 |
| A1 transport 2 passed | 最终 h100 与运输测试 hash 匹配 | pickle/JSON 修复，不是现场完整端点 |
| 最终 26 helper passed /0.96 s | 最终 adapter/helper hash 匹配 | profile、route、raw helper 等；不执行完整 native 恢复/输出/采样链 |
| 最终 registry 5 passed /0.06 s | 最终总账/文档 hash 匹配 | Markdown 文档资格 |
| 最终 Ruff/format/compile | 只覆盖 adapter 与 helper 测试两文件 | 不能当全核心、ABI 或 pytest |
| 全仓收集 | 原 8 errors；干净记录仍 SLEPc 1 error | **测试体未执行；无 full-suite/CI PASS** |

因此，“只测了过时源码、所有测试都无效”也不准确。应保留同字节组件证据，并明确新增整体路径未取得正式成功端点。[Q02][Q02] [native 组件][NATIVETEST] [retry 接线][RETRYTEST] [正式修复记录][FORMAL] [closeout][CLOSEOUT]

八个旧错误具体为：ignored artifacts 中同名模块冲突 1 项、SLEPc 注册冲突 1 项、旧 scratch 缺失模块 6 项。ABI compact 给 custom PETSc complex128/int64 与 system SLEPc real 库路径，支持环境不匹配分类；本次未获取 ldd 原件，不声称现场重现。清理 ignored 收集问题不能修复真实 SLEPc gate，也不必为本轮限定 direct 诊断扩大环境工程。

### 8.2 核心与 runner

数值 action、约束、凝聚、恢复、独立 A6 等保留在 src；benchmark 负责冻结身份、尝试调度和研究比较，方向合理。native P6 的新诊断接线规模较大，需要 V2-03 的明确边界测试，不宜再把权威判定散入更多 runner。没有必要重写控制平台。

依赖清单 66 项包含 27 production/shared core、25 explicit tests、9 research runner/checker、4 reporting、1 watchdog。旧 overlay 证明的是 4 imports 和 25 文件 collect-only、157 nodes、0 测试体。66 项中 64 与最终同 hash，后改 h100/watchdog；27 核心仍全部同字节。manifest 已明确新 native A2 分支、adapter、comparator/resampler 不借用旧 overlay。[依赖清单][CLOSURE] [manifest][MERGE]

| 交付组 | 当前资格 | 合入前条件 |
|---|---|---|
| 文档、负结果、轻量成本与审阅 | 可在研究分支归档 | 保留版本/范围/缺口；本报告不执行 master 合并 |
| 27 文件共享数值核心及测试 | 可继续作为复用候选 | 原子依赖组、实际目标分支回归、匹配 ABI 与共享默认行为检查 |
| watchdog 小 CLI 修复 | 可单独评估的工具修复 | 有关 tiny-child/资源/清理回归；不随之批准 Task43 全路径 |
| V2 native 诊断、A1 observer、adapter/comparator/resampler | **research-only** | 修 V2-03/04、完整端点和相关回归；不能设 production default |
| 多层 h、侧壁、迭代、同精度性能声明 | **未资格化** | 各自科学/工程门和后续明确授权 |

## 9. 论文支撑及其适用边界

1. Jiang 等，*An Adaptive Finite Element DtN Method for Maxwell’s Equations in Biperiodic Structures*，arXiv:1811.12449（2018）。本次查阅全文中的 Theorem 3.1、Table 5.1：有限元误差与 DtN 截断误差分列，支持分别诊断空间与 R；不能把该文定理直接当成本仓库高阶、约束和输出误差的保证。[原论文][PAPERDTN]
2. Becker、Rannacher，*An optimal control approach to a posteriori error estimation in finite element methods*，Acta Numerica 10（2001），DOI 10.1017/S0962492901000010。本次核对出版社摘要：全局范数控制不自动给出所关心输出的充分精度。这支持保留 G 与零级功率的不同判据；本轮不据此另建 DWR/伴随框架。[出版社原文摘要][PAPERDWR]

上述文献只支撑误差分解和目标量区分的判断。当前端口差、工程失败和配额裁决均来自本仓库证据，不能用文献替代端点资格。

## 10. 继续计算的前瞻授权

本节是针对用户本次明确要求的正式决定。**只调整未来次数分配及必要留证/输入兼容接线，不改变旧物理、接受容差、历史失败和 accepted9。旧 diagnostic_plan/retry 合同保留原样；新建补充执行合同绑定本报告。**

### 10.1 固定配额

| 分项 | 已用 | 本次最多新增 | 本次累计上限 |
|---|---:|---:|---:|
| A1 组 | 1 | **1：A1_q attempt2** | **2** |
| A2 组 | 2 | **1：A2_q attempt3** | **3，明确由原 2 前瞻增加为 3** |
| A1_R、A2_R | 0 | **0** | 继续锁定 |
| B、C | 0 | **0** | 继续锁定 |
| 封存未分配槽 | — | **0** | 原总 6 内剩余 1，不得自行使用 |
| **正式模型合计** | **3** | **最多 2** | **最多 5/6** |

分配来源明确：原未运行的 A1_R 槽转 A1_q2；原 B 槽前瞻转 A2_q3；原 C 槽封存。A2_q2 已消耗原 A2_R 槽的历史事实不变。A1_q2/A2_q3 不自动解锁任何 R/B/C；新代码/记录的 continuation 标志也必须关闭。

**次数从正式 dispatch 起计，失败、网格前 preflight 失败、资源停止、重试和任何 fresh baseline 都计数。** 本次仅授权上述两个 q 求解，不另授权基线重建 PDE。比较所必需的旧场/身份缺失时，停止相应项并报告，不换一个方便参考。发现此前漏记的正式调度时先纠正历史并停止新增分配，不能仍按“已用 3”执行。

若两次都消耗，剩余 1 次不足以完成两条 R 加 B/C。此授权只救回有限 q 诊断，不承诺完成原六步序列；不能因此自动扩大总额、跳过 R 或挪用封存槽。

### 10.2 零新正式 PDE 前置门

以下修复、只读核验和小组件测试可立即做；**只有 G0–G4 对相应分支全部满足，才可正式 dispatch。通过后在本节范围内执行，无需再请求重复确认。**

| Gate | 必须完成的最小工作 | 通过证据 |
|---|---|---|
| **G0：历史计数及基线可读** | 工作站只读枚举全部正式 launch/attempt 和支持目录；复核三条终态原件/源码/输入 hash。逐项验证 R10/Y6_1 旧系数、模态、物理/FE 身份及需要的采样数据确实可读。无关旧 R8/ABI 缺口单列。 | 完整 attempt 索引；没有遗漏正式调度；比较所需原件实际读取检查。不能只核文件存在。 |
| **G1：primary 先持久化与失败语义** | 按 V2-03 提前原子写 before 包；故障注入 extra、bcast、sampler；实际 MPI1 object transport 与 JSON/NPZ roundtrip。 | before 文件可读、范数可复算、hash 不变；失败端点不是 official/pass；continuation 全 false。不得把 fake fixture 说成新 PDE。 |
| **G2：真实入口接线** | 用资格化 activation，核实际 CLI 参数构造、watchdog-owned 绝对 phase path/父 PID/WorkflowLedger、固定 Y6 profile 严格校验、CPU/thread 与 direct ABI。用真实 CLI tiny-child 和受限测试替身覆盖启动链；在测试驱动下禁止调用 mesh/solver。组件驱动使用隔离临时路径，不创建/占用正式 q2/q3 attempt/run，也不登记正式 dispatch。 | 最终代码下的组件输出及精确正式 argv/env 清单；缺 phase、错 label、数值/资源漂移均拒绝。A2 q3 绑定新授权与旧两条 terminal，不能只扩 choices。 |
| **G3：积分与比较输入** | 按 V2-04 明确 Av 有效规则或固定旧场 auto/q15/q19 核验；检查全部 612 模态、mode-physics、q8/q10 全域点权、H/curl/背景和 reference 方向。 | 原场/规则/点数/域体积/hash、重算值与限值。所有输出差仍用冻结门，不另拟合相位、改 floor 或删弱通道。 |
| **G4：最终版本和一次性冻结** | 对实际变更依赖运行有限测试，绑定同一干净 source SHA；新增补充合同固定本报告、旧合同、配额、q2/q3 唯一路径、argv、资源和停止条件。主控读取真实结果后分别记 READY_FOR_ONE_A1_Q / READY_FOR_ONE_A2_Q。 | 可审阅的 Gate 记录及已提交合同；不是一个总 PASS 自动批准下游。源码/合同/输入在 launch 前写入身份，前后再核 hash。 |

G2 是组件测试/只读准备，不能启动正式 A1/A2 实例后因其在网格前退出，就改记为免费支持工作。**任何实际正式 phase dispatch，即使只在 preflight 失败，也消耗该唯一槽位。** 无 PDE 门失败可以做局部修复与针对性复验；门未过就不启动正式模型。不扩大 full-suite、无关环境重建或参数扫描。

### 10.3 执行顺序与科学门

1. 先 A1_q2，再 A2_q3，单重型队列。A1 保持 R10 原 180 cells、全 p6、118800 FE、原 variable-p condensed/MUMPS/约束配置；A2 保持 Y6_1 native P6 576 cells、预计 380160 FE，实际构网后复核。两者均固定物理与 R13，只按原合同加严体算子 q19、incident/port q32，并明确 Av 的实际规则。
2. primary 必须为原常规 correction 策略结束、额外诊断 correction 之前的场。A1 正常一次；A2 原 native 最多两次并记实际次数；额外仅一次、同 matrix/RHS/factor，不择优改用 extra 场。
3. 保持硬门：独立原方程 A6 与完整 active explicit residual 均≤1e-8，condensed≤1e-9，abs(1−R−T−Av)≤1e-5；原始残差/同 RHS 范数有限，常规和额外 correction 的要求依旧合同严格复核。native MatSolve 用真实 MUMPS INFOG(1)=0、symbolic/numeric/solve counters 与原向量审计，不伪造 KSP reason。[native 合同][NATIVE]
4. q/extra 输出扰动门不变：逐通道及 R00_s/p 功率≤1e-7；R/T/Av/R00_total≤1e-6；四复幅组、全/散射 E/H/G 的固定地板范数≤1e-5。q10 主比较与 q8 稳健性分别留值；端点硬门、q 门、extra 门分别标 pass/fail/incomplete。
5. 一项局部数值负结果不自动否定另一项独立 q 诊断；共同 ABI、输入身份、运输/持久化或资源缺陷使相关 Gate 失效时停止受影响工作。每项实际 dispatch 后无论原因都没有该项下一次自动重试额度。修复可归档，但不得挪用封存槽。
6. 即使两个 q 全通过，仍保持 R/B/C continuation=false；即使 q 未过，也不得沿旧 plan 的自动 R 规则继续。本文对未来执行顺序的限制优先，历史计划原文不改。

### 10.4 资源与时间预算

沿用 task43_hp_adaptivity_resource_v1 和现有资格化 activation：MPI1、一个可用 CPU、OMP/OpenBLAS/MKL/NumExpr 各 1 thread，一次一个 heavy。

- 每个正式 q attempt 的完整 watchdog 上限 **7200 s**；两次新增正式工作最多 **14400 s**。这是含启动/输出/extra 的停止上界，不是预测；不得运行中延长。
- 同时 process-tree/cgroup RSS 绝对上限 192 GiB；reserve=max(64 GiB,15%有效总内存)，launch cap=min(192 GiB,80%有效总内存,available−reserve)，planning cap=min(192 GiB,75%有效总内存,launch cap)。记录实际值，不承诺每次都有 192 GiB。
- task-tree VmSwap 必须为 0；规划/余量不满足不派发；出现 task swap、内存/时间越限、worker 失败或硬门拒绝，按原 watchdog 清理并保留失败。global swap 单独观察。
- 支持工作单列费用，限定为本节枚举的组件、输入检查和同旧场最多三种 Av 规则，不用支持名义启动 fresh 模型、反复整包测试或盲扫。超出这些目的则停止并说明缺口。

### 10.5 每次必须持久化的端点证据

| 层次 | 必须保存 |
|---|---|
| 启动与计数 | 完整 source SHA、真实 argv/env/activation、合同与父输入 hash、时间、phase/attempt、唯一目录、已用/剩余配额、launch 前后源码/输入一致性 |
| 空间与算子 | 物理、mesh/axes、p-map/closure、独立 FE/trace/interior、Floquet 从属/carrier、矩阵 rows/NNZ，q/R 和 Av 规则；预测与实测不同字段 |
| primary 独立 before 包 | 系数/checkpoint、原 RHS/solution/residual 数组及 hash、独立 A6/explicit/condensed、常规 correction/counters；extra 前落盘 |
| 两端完整输出 | primary/extra 612 通道、四复幅、R/T/独立材料 Av/R00、原场、q8/q10 点权与总/散射 E/H/G；raw checker 从字段复算门值 |
| 终态与成本 | watchdog summary、资源样本、峰值定义、swap、exit、cleanup；失败也有端点完整性清单、错误阶段和 partial 标志；支持工作互斥分账 |

Git 提交轻量索引和足以核查门值的完整表/摘录，原场、矩阵与大日志保留 ignored。不得只有一个 passed 标签和一串原件 hash。重新采样/积分可补充诊断，但必须标清时间和来源，不能把 A1_q1 的失败 retroactively 改为成功。

### 10.6 下游保持锁定与未来解锁条件

| 项目 | 本轮授权 | 后续需满足的条件 |
|---|---|---|
| A1_R | **不授权** | 完整可信 A1_q primary、硬数值/资源/基线门；明确有限 R 因素诊断理由、新额度和冻结合同。q 扰动超限可成为诊断理由，但不会自动解锁。 |
| A2_R | **不授权** | 同上，且必须是自身 native A2 的资格；另明确恢复此前取消的 R 权限与额度。 |
| B | **不授权** | 原 A1/A2 全部 q/R 和 extra 门通过；原计划的同核/等价 reference Gate、固定 R9 父与 cell8 单层动作、实际 FE<237600、跨空间比较和资源门；另行正式分配额度。 |
| C | **不授权** | B 有冻结可用候选；预定 9×16×6 参考的未揭盲范围、实际资源预估和独立比较合同；另行额度。一次 C 不自动证明其自身 q/R 或侧壁资格。 |
| 同精度全过程成本 | **不授权 campaign** | 候选与对照先通过同一独立精度标准；同环境/源码/缓存/生命周期和包含失败/参考/转移/比较的成本合同。当前继续记账。 |
| 迭代接线 | **不授权** | 空间、精度与直接法端点先可验；再单列真实迭代算法、残差、收敛与完整成本任务及预算。 |

某分支前置门不能通过时停止该分支；另一分支仅在自身及共用门均有效时继续。两条均无法继续或本次额度用完后，按实际结果收口；若仍无合格诊断，按原五项能力状态结项，写明失败机制、实际费用和原件缺口，保留 PARTIAL / CONTROLLED_NEGATIVE。不得重启 NN/FTT、0.7 nm、无关环境工程或新控制框架。

## 11. 下一次交付要求

执行方沿同一任务目录和既有合同结构，新增 diagnostic_plan_v3.md 及 outcomes/records/diagnostic_plan_v3_contract.json，仅承载本报告的前瞻差异并引用原冻结事实，不另建平行控制体系。完成有限修复，保持 V1/V2 历史权威文件、失败 records 与旧合同原样。最后新增 response_v3.md 与轻量 Gate/attempt/端点/成本记录，按阶段追加更新 README、summary、模型总账、开发进展和 manifest。每项声明都标 source SHA、原件可访问性、是否实际 PDE/重新采样/重新积分、预测还是实测。

收口应逐项回答 V2-01–V2-06，分别报告工程整改、q 诊断资格、五项能力、配额和合并资格。全仓未过继续写未过；新结果不得给旧 R9/R10 重判。只提交并推送 task43_hp_adaptivity，不提交 master、不合并。最终报告完整提交 SHA 与分支 ahead/behind；若执行止于前置门也应提交可复查的失败/未运行记录。

本正式 review 的交付是单独新增本文件；审阅提交完整 SHA 由承载本文件的 Git commit 和交付回复报告，审阅对象始终为第 2 节固定的 fd4a630。

## 参考文件与源码

以下源码链接固定到送审 HEAD，明确标为旧源码者除外；记录链接相对本报告所在目录，历史身份以第 2、7 节为准。

[DIFF]: https://github.com/Rookie1234567/MyFEniCS/compare/7458fadccde01d37ed93187ebe4c39177783d60b...fd4a63098893a82374f43f8c3066b74285e9c020
[TASK]: task.md
[PLAN]: diagnostic_plan_v2.md
[V1]: review_report_v1.md
[REGISTRY]: ../development_model_registry.md
[PROGRESS]: ../development_progress.md
[ROOTAUDIT]: outcomes/records/root_final_review_audit_v2.json
[CLOSEOUT]: outcomes/records/v2_closeout_validation_v1.json
[FORMAL]: outcomes/records/v2_formal_attempts_and_profile_fix_v1.json
[REPLAY]: outcomes/records/post_selection_old_field_replay_v2.json
[RESAMPLE]: outcomes/records/v2_legacy_r10_resampling_attempts_v1.json
[Q02]: outcomes/records/q02_collection_and_abi_v2.json
[ERRORS]: outcomes/records/full_repository_collection_error_index_v2.json
[MERGE]: outcomes/selective_merge_manifest.md
[CLOSURE]: outcomes/records/selective_merge_dependency_closure_v2.json
[COST]: outcomes/records/completed_watchdog_cost_inventory_v2.json
[FREEZE]: outcomes/records/round1_freeze_timing_evidence_v2.json
[CONTRACT]: outcomes/records/diagnostic_plan_v2_contract.json
[NATIVE]: outcomes/records/diagnostic_plan_v2_a2_native_contract.json
[RETRY]: outcomes/records/diagnostic_plan_v2_a2_q_retry_authorization.json
[Q0607]: outcomes/records/q06_q07_component_validation_v2.json
[REGTEST]: outcomes/records/registry_markdown_attempts_v2.json
[POST]: outcomes/records/post_selection_existing_fields_validation_v1.json
[R10]: outcomes/records/round10_rejected_candidate_v1.json
[A1]: outcomes/records/a1_q_failed_observer_serialization_v1.json
[ACCEPT]: outcomes/records/round1_acceptance_contract_v1.json
[MODELS]: outcomes/records/unified_model_attempt_inventory_v2.json
[DOF]: outcomes/records/uniform_dof_estimates_v1.json
[NATIVETEST]: outcomes/records/a2_native_component_validation_v1.json
[RETRYTEST]: outcomes/records/diagnostic_plan_v2_a2_retry_wiring_validation.json
[T197]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/test/test_197_task035d_hanging_trace.py
[SCOPE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/reporting/watchdog_scope.py
[INVENTORYCODE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/reporting/build_unified_model_attempt_inventory.py
[H100OBS]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/h100_anchor.py#L3284-L3422
[H100WRITE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/h100_anchor.py#L3501-L3517
[P6PRIMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/runners/p6_condensed_direct.py#L3965-L4087
[P6RAW]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/runners/p6_condensed_direct.py#L4501-L4565
[P6FAIL]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/runners/p6_condensed_direct.py#L4790-L4925
[P6Q]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/runners/p6_condensed_direct.py#L3124-L3138
[AV]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/postprocessing/rta_3d.py#L50-L72
[OLDAV]: https://github.com/Rookie1234567/MyFEniCS/blob/6320ae621ddf94d39e9006628a5ef68b0dfdfffe/src/postprocessing/rta_3d.py#L50-L55
[TRANSPORT]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/h100_anchor.py#L460-L475
[TTRANSPORT]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/test/test_task43_v2_live_observer_transport.py
[WATCHDOG]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/subreaper_watchdog.py#L836-L844
[TWATCHDOG]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/test/test_354_subreaper_watchdog.py#L48-L106
[PROFILE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py#L1199-L1294
[A2BIND]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py#L1394-L1455
[TA2]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/test/test_task43_v2_native_p6_diagnostic_helpers.py
[P6ENTRY]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/runners/p6_condensed_direct.py#L2919-L3029
[COMPARE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/compare_v2_endpoints.py
[TCOMPARE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/src/test/test_task43_v2_comparison.py
[RESAMPLERCODE]: https://github.com/Rookie1234567/MyFEniCS/blob/fd4a63098893a82374f43f8c3066b74285e9c020/benchmarks/task43_hp_adaptivity/sample_v2_legacy_r10_fields.py
[PAPERDTN]: https://arxiv.org/pdf/1811.12449
[PAPERDWR]: https://doi.org/10.1017/S0962492901000010
