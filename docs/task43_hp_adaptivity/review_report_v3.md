# Task43 正式审阅 V3：整改与有限 q 诊断

审阅日期：2026-10-24（Asia/Singapore）。本报告审查固定提交 `6f6bf3b6ad9b534eb12794a72471157218859de1`，不把分支后续变化追溯为本次已审内容。文中代码行号均指该提交；历史运行仍使用各自的实际源码身份。

## 1. 正式决定

**接受本轮有明确边界的证据整理和部分工程改进；不接受“整改全部闭环”或“完整 q 诊断通过”。本次新增正式 PDE 授权为 0。只允许第 9 节的有限非 PDE 整改。Task43 维持 `PARTIAL / CONTROLLED_NEGATIVE`，不批准生产合并。**

| 决定类别 | 本次裁决 | 实际含义 |
|---|---|---|
| 整改验收 | **部分通过** | primary 提前持久化有真实实现，A2 现场保存记录与之相符；Av 口径和历史调度账明显改善。A1 真实入口仍缺 WorkflowLedger；异常状态、extra 原向量留证和监督器诊断仍有待修项。 |
| 分支计算资格 | **不允许新的正式模型计算** | 正式累计 5/6，A1=2/2、A2=3/3；剩余 1 槽封存。修好代码不返还失败槽，不产生新的 READY，也不自动授权重试。 |
| 科学结论 | **有限 q 稳定性观察成立；完整端点与独立精度未通过** | A2 primary 的完整 612 通道表及保存场指标显示很小的变化；extra 严格下降门失败、完整端点缺失。不能由此认定空间精度、参考收敛或 hp 成功。 |
| 合并资格 | **NOT_APPROVED** | 本报告可以作为研究审阅材料提交到执行分支；不批准整分支合入 master，不将研究接线提升为 production default。 |

这里的 primary 是“正常 correction 完成、额外 correction 尚未开始”的固定状态。extra 是复用同一矩阵因子再做一次回代，仅用于诊断代数误差；不能在两者之间挑选更有利的场作为结果。WorkflowLedger 是实际工作进程向监督器写入阶段、身份和失败状态的账本；环境变量里有路径，并不表示真实入口已经写账。

本轮停止有充分理由。A1 消耗一次正式槽后仍未到达数值端点；A2 虽取得有价值的 primary，却暴露了已经计算出的 extra 数据仍可能因后续采样而丢失的问题。现有缺口主要可以用真实入口哨兵、小数组故障注入和旧日志读取解决，再启动一个昂贵模型不能代替这些验证。[V2 执行权威][V2] [V3 合同][CONTRACT] [本轮终态][CLOSEOUT]

## 2. 身份核对、阅读范围和独立核验边界

### 2.1 固定身份

| 对象 | 核对值 |
|---|---|
| 仓库／唯一执行分支 | `Rookie1234567/MyFEniCS` / `task43_hp_adaptivity` |
| 送审 HEAD | `6f6bf3b6ad9b534eb12794a72471157218859de1` |
| 送审 tree | `74292354cd16f871fe93e34ad862fd4598b3319d` |
| 送审 HEAD 的父提交 | `d92c210a6704de99362f5e696d157d6c356d9efd` |
| V2 正式 review | `fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12`，执行权威为第 10 节 |
| V2 被审代码 | `fd4a63098893a82374f43f8c3066b74285e9c020` |
| 代码基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| V2 review 至本次 HEAD | 8 个提交，54 个变更文件；远端执行分支在本次取证时指向指定 HEAD |
| A1_q2 / A2_q3 实际源码 | `28dd150ac2917d6df272324e0b00b960064dad00` / `d92c210a6704de99362f5e696d157d6c356d9efd` |

已读取根、docs、Task43 三层 AGENTS，仓库工作原则与文档入口，task、V2/V3 计划和冻结合同、V1/V2 review、V2/V3 response、README、summary、selective merge manifest、模型总账和开发进展；直接检查 V3 的代码差异、测试源码及 pre/post 审计记录。未改历史 review、合同、失败记录或数值代码。

本次另核对了提交内 190 条 hash 引用，涉及 161 个唯一 tracked 路径，均与所取字节相符；G4 的 60 个源码文件全部核对，47 项输入中 12 项 tracked 输入可直接核对，另 35 项 ignored 输入和 7 个 ignored 启动脚本没有取得原件。V1 保护清单的 64 项文件以及 V2 既有 76 项 records 在此次差异中保持原字节／Git blob。上述身份检查证明取到的内容一致，**不单独证明工作站原件被实际执行的时间或未披露路径中绝无其他运行**。[G4 清单][G4] [G0 枚举][G0] [V2/V3 差异][DIFF]

### 2.2 本次真正重算了什么

“执行侧 root audit”是仓库中保留的执行现场审计；“本次外审重算”只指下面列出的实际操作，二者不混用。

| 证据 | 本次外审实际核验 | 未独立核验的部分 |
|---|---|---|
| Git 代码、合同、测试、轻量 JSON | 固定提交取字节、核 blob/hash、检查调用顺序和异常分支；解析全部相关 JSON 结构与表项 | 工作站 canonical clone 的实时工作树、upstream、进程和原始运行环境未直接访问 |
| A2 的 612 通道 | 全部 key、旧/新复幅、功率、差值、四组范数；用冻结物理参数从表内复幅独立重建 Poynting 功率 | 未从原 FE 系数重新投影模态 |
| q8/q10 全场 | 用记录中的原范数和固定 floor 重算归一；核点数、分区数、前后点权 hash 及参照方向 | 未打开原大 NPZ，未重新计算原数组的加权范数、逐点正权或重新采样 |
| primary／extra 残差 | 检查原向量生成源码、记录的作用域、计数、范数比例和严格下降关系 | 未取得原 residual/RHS/solution 数组；没有本次重新求原向量范数，更没有重新施加原 Maxwell 算子 |
| Av 三规则 | 逐材料功率除同一入射功率、求和、差值和记录的 form metadata | 未在本环境重新积分旧系数；新端点 automatic 的实际有效 degree 没有单独现场记录 |
| 调度／成本／清理 | 全部已提交调度条目、原终态摘录、命令摘录、时间算术和五次费用加总 | 未获得完整 resources.jsonl，不能亲自逐样本重算 RSS 峰、重放清理或排除记录范围之外的启动 |

本次运行了三个不导入求解器的本地检查：轻量数值表算术、工程 hash/计数核验，以及从最终源码提取真实异常守卫后的两种写盘故障注入；另对 watchdog 的原控制流做了假时钟分支复现。它们没有构网、装配、PDE 求解、MPI 数值运行、新采样或新积分，不作为工作站 pytest 通过记录。第 4.4 节列出故障输入和实际输出，便于在原测试模块补成回归。

## 3. V2-01～V2-06 与前置门逐项裁决

| V2 项 | 裁决 | 已落实部分及未关闭部分 |
|---|---|---|
| V2-01：科学验收 | **未通过；负结果保留合格** | accepted9/R9、R10 拒绝和独立 holdout 失败未改。V3 没有完整新端点，五项能力未被提升。A2 primary 是新增有限证据，不关闭原空间精度缺口。[summary][SUMMARY] [primary][PRIMARY] |
| V2-02：全仓／生产测试 | **未通过；范围说明合格** | 57/1、最终变化节点 1 项、native no-mesh 1 项和文档 5 项分别标版本。原全仓 collection 错误、干净 checkout 的 SLEPc/complex-PETSc 阻塞仍在，不能称全仓或 CI 通过。[测试索引][TESTS] [response][RESPONSE] |
| V2-03：primary 先保存及失败语义 | **部分通过** | 两条代码路径均前移 primary 保存；A2 现场留下 primary/q8/q10。A1 未运行到该段；extra raw 仍后写；A2 后处理守卫存在本次复现的权限状态矛盾和截断文件异常。[primary 实现][P6PRIMARY] [异常守卫][A2GUARD] |
| V2-04：Av 规则 | **通过，限于原要求的旧场补证及准确口径** | 同一旧场 auto/q15/q19 的材料积分和有效规则记录支持极小差异，旧配置仍 automatic；新 A2 operator q19、incident/port q32、Av automatic 分开。不是新 Av 收敛或整个 q 端点通过。[Av 补证][AV] [V3 计划][PLAN] |
| V2-05：调度枚举／终态外审 | **部分通过** | 已有 canonical 范围枚举、真实命令、别名去重、五次终态及费用；未发现失败改名抵扣。原件仍有外审访问缺口，CPU affinity 的汇总歧义尚未拆解。不能将索引中的 hash 当作本次读取了全部原件。[G0][G0] [A2 命令][LAUNCH] [终态][A2TERM] |
| V2-06：阶段和文档身份 | **部分通过** | V1/Stage1/V2 的范围大体标明，总账和 response 保留最新 5/6；summary 后部仍有未明确标历史的“4/6、A2 未派发”段落，见 V3-08。旧记录不需改写，只需明确其时间范围。[summary][SUMMARY] [manifest][MANIFEST] |

前置 Gate 不能由一个总 PASS 替代。尤其 G2 要验证实际入口，不是验证“存在一个能写账本的小程序”。

| 前置门 | A1_q2 | A2_q3 |
|---|---|---|
| G0：历史计数和输入身份 | 提交内计数与身份自洽；未发现额外正式调度，原件访问边界见第 2 节 | 在 A1 消耗后更新为 4 次，实际 A2 后为 5 次；无跨组再分配证据 |
| G1：持久化和失败语义 | 组件和源码有改进，现场未到 primary；本次发现的失败权限漏洞说明“全链路失败安全”仍不能总体 PASS | primary 现场保留有支持，但不能覆盖所有后续写盘／信号失败，见 V3-04/05 |
| G2：实际入口 | **NOT_MET，错误放行**；环境 guard 与通用 tiny-child 被外推成真实 A1 ledger 接线 | native mesh 前确实创建 ledger，另有真实 native no-mesh fixture 和现场 stage；这一局部分支接线成立 |
| G3：旧输入和积分口径 | 旧 R10/Y6 输入、612、点权和 Av 的前置补证成立；不等于新端点通过 | 同左；A2 的新 q 只得到 primary 部分观察 |
| G4：版本／测试／资源／READY | 字节绑定不补救遗漏的 G2；旧 READY 作为历史保留，不能称完整前置门满足 | 一次性源码、合同、配额与资源身份可追踪；CPU 全程口径须补原样本分段，不能从启动点扩大为全程结论 |

A1 失败后单独检查 A2 的真实 native 路线，再使用已经由 V2 分配的一次 A2_q3，本身符合分支隔离规则；A1 的局部缺线不等于 A2 必须具有同一缺线。但这不免除本次发现的共同失败语义问题，也不授权任何下一次运行。[A1 READY][READY1] [A2 READY][READY2]

## 4. 按严重程度排列的问题和验收要求

严重性按受影响的门区分：P1 阻断该类派发、科学验收或生产合并；P2 为确定实现／证据问题，需要有限修复；P3 为不改变数值结论的文档歧义。科学负结果不自动归为代码 bug。

### V3-01 — P1，执行门：A1 READY 错误放行，最终源码仍没有实际 ledger

`h100_anchor.py:188–208` 的 `_log_stage` 只打印 stdout JSON；`:2665–2688` 的 `_require_v3_watchdog_worker_identity` 只验证直接父 PID 和绝对 phase path；`:4860–4865` 调用该 guard 后继续执行。整条 A1 路线没有实例化 `WorkflowLedger`。测试 `test_task43_v3_failure_safe_order.py:447–471` 只测 guard，通用 tiny-child 也明确不覆盖正式 A1/A2 adapter。A1 READY 却把这些证据作为实际 G2 passed 的依据。[A1 源码][A1SOURCE] [A1 READY][READY1] [故障测试][FAILTEST]

现场 134 个资源样本没有非空 worker phase，指定 phase 文件不存在；180 格网格已经建立并进入装配。执行侧 terminal 明确承认主控接受了 tiny-child 证据而未检查实际 A1 调用。这是**实现遗漏和主控放行失误**，不能只称“运行后环境出错”，也不宜归咎为执行方擅自启动。[A1 终态][A1TERM] [停止记录][A1STOP]

最终 response、closeout 已充分承认 NOT_MET，旧 READY 仅为已消耗一次的历史记录；保留原 `USER_CONTROLLED_STOP` 并补原因 `G2_A1_WORKFLOW_LEDGER_NOT_WIRED` 是正确做法。文字承认不修复源码，也不返还额度。

**最小整改／验收：** 在既有 A1 opt-in 入口复用已有 WorkflowLedger，mesh 前建账并接入真实阶段和异常终态。用真正 A1 参数解析／主入口、watchdog 绝对 phase path 和隔离临时目录测试；仅在第一个 mesh builder 边界设置哨兵，断言此前已有可读 phase/stages，真实 mesh、assembly、factor、solve 调用数均为 0。缺 phase、错父身份必须在该边界前拒绝；哨兵异常保留失败阶段和关闭的 continuation。不得只再测 guard 或 A2，不能创建正式 attempt 目录。

### V3-02 — P1，科学资格：extra 负门和完整端点缺失仍阻断 q 诊断验收

A2 primary 的三个残差低于冻结门，但 extra full-active 显式残差由 `1.1972486317982494e−11` 增至 `1.2068417985488609e−11`，增加约 **0.8012677%**。两个数都低于 `1e−8`，仍不满足另一个独立条件“严格下降”。凝聚残差和 A6 下降不能替代该条件。保留 `FAIL_UNCONTROLLED_EXTRA_CORRECTION` 正确；不能因数值小而后验宽免，也没有原向量证据足以把原因确定为舍入。[extra 计算与门][P6EXTRA] [primary 审计尾部][PRIMARY]

extra 原向量和完整样本、native summary、comparison_record 均未取得完整交付；7200 秒停止亦未满足完整工作流要求。因此端点继续 `INCOMPLETE_NOT_QUALIFIED / NOT_OFFICIAL`。这是一项冻结诊断负结果与缺项，不证明 hp、直接法或所有 same-LU correction 都无效。

**验收边界：** 旧负结果保持原样。本轮只修留证与状态，不重跑去补旧端点。未来若另提正式诊断，须在新授权中先论证科学问题、完整端点可在预算内完成的依据和规则；任何规则变更只能前瞻适用，旧结果不重判。

### V3-03 — P1，生产合并门：旧测试闭包不覆盖最终共享文件

原全仓 pytest 是 1 skip、8 个 collection errors、0 个测试体；旧干净 checkout 的 SLEPc/complex PETSc 问题也未解决。V3 有限测试不替代真正拟合入文件及共享依赖的生产测试体。[V2 review][V2] [测试索引][TESTS]

另对 Stage1 的 66 路径机器闭包重核：当前仅 **59/66** 同字节；其中 27 个核心／共享依赖仅 **23/27** 同字节。变化的四个核心文件为 `common_3d_case_flow.py`、`dtn_port_3d.py`、`hcurl_variable_p_reduction.py`、`solve_maxwell_3d_stage_4b_block_grating.py`；其余差异含 watchdog、h100 和 candidate_checkpoints。因而不能只说“新增 native 分支不在旧 overlay”，还必须承认**这些最终共享文件整体也未由旧 overlay 资格化**。[机器闭包][MERGECLOSURE] [manifest][MANIFEST]

**最小行动／验收：** 维持 production 锁定；在当前 manifest 的历史闭包说明后补清楚版本范围。将来真正提 selective merge 时，先给最终文件／依赖闭包和相应回归，再单独审。此项不要求本轮重建无关 SLEPc 环境或启动全仓测试。

### V3-04 — P2，已复现实现问题：A2 后处理失败可留下“失败 summary／合格 comparison”

`a2_native_p6_diagnostic.py:84–124` 的失败守卫只降低 native summary 的权限。`:2429–2434` 先写 comparison，`:2454–2457` 再写 summary，之后还有输出；后一步异常时，已经写出的 comparison 不随之失效。`:2399–2402` 和 `:2454–2457` 仍为非原子 `write_text`；若先截断再写失败，守卫 `:96` 重读损坏 summary，会在保存失败终态前再次抛错。[守卫][A2GUARD] [后处理写序][A2WRITES]

本次以最终源码的真实守卫、真实纯 checkpoint helper 和临时合成记录复现两例，不调用数值求解：

| 注入位置 | 实际结果 | 应有结果 |
|---|---|---|
| 已写 `endpoint_qualified=true` 的 comparison 后抛 OSError | summary 为 FAILED，passed/official=false，partial terminal 可读；comparison 的 endpoint_qualified **仍 true** | 不得再存在可被消费者认作合格的当前端点 |
| 已有 comparison，summary 写入先截断为无效 JSON 再抛 OSError | guard 改抛 JSONDecodeError，partial terminal 未生成，comparison 仍 qualified | 保留原始异常、可读失败终态及 primary 引用，不依赖损坏文件才能降权 |

这两例的 R continuation 仍 false；本项不是证明 R 被重新解锁。本次实际 A2 没有生成 comparison，所以也不改变其已有 incomplete 分类。现有 `test_task43_v3_failure_safe_order.py:207–290` 只覆盖可读 summary，不覆盖这两个窗口。

**最小整改／验收：** 复用已有原子 JSON 写法；在内存保留 identity 和 primary 引用，使 summary 缺失／截断时仍可写失败终态；已生成 comparison 时，统一降低端点资格元数据或写明可被读取器强制遵循的取代性失败状态。保留所有 measured 数值、原 comparison 的身份和 raw hash，不能把实际已过的物理数值改成假失败。补上述两例，要求无有效 qualified endpoint、所有 continuation=false、原 primary/hash 不变、原 OSError 可追踪。

### V3-05 — P2，留证时机：extra 原向量仍要等昂贵后处理完成才写

native runner 在 `:4396–4544` 已完成 extra、A6 和 full-active 计算，`:4542` 写标量 stage；原向量到 `:4875–4922`、恢复和额外采样之后才写 NPZ。因此这次超时留下 extra 数字，却没有可独立复算的 extra 数组。primary 保存修复不覆盖这一风险。[extra 计算][P6EXTRA] [extra 后写][P6EXTRAWRITE]

**最小整改／验收：** extra 原向量及其残差、同 RHS 身份、factor/correction 计数计算完成后立即原子保存，再做任何额外物理输出或采样；负门也保存，引用 immutable primary hash。用小数组／现有 fixture 注入 extra 后恢复失败、运输失败、q8 已存而 q10 失败；核包可读、可重算、primary 不变、失败端点不合格。不得伪造本次缺失的 extra NPZ，也不授权为补包重解 Y6_1。

### V3-06 — P2，监督器诊断：清理异常消息不能证明当时仍有后代

原 watchdog 的 `exception_stage=cache_stability` 与消息 `descendants did not clear after SIGKILL` 均应保留，当前 `LIMITED_NOT_UNCONDITIONAL_PASS` 分类正确。不过直接读 `subreaper_watchdog.py:720–734` 可见：进入 cache_stability 的条件已经是 `exit_code is not None and not children`；随后总清理等待超限的判断没有再检查 children，仍抛这句消息。[watchdog 原代码][WATCHDOG] [A2 终态][A2TERM]

本次以这两段原 AST 和假时钟验证：children 为空、leader exit=-15、stop 后 12.1 秒、grace+10=12 秒、cache 稳定等待刚开始时，仍得到同一 RuntimeError 和 cache_stability 阶段。这确认了**错误归因分支**，不是重放真实 A2 资源流。实际 stage 支持当时已进入“无 children、等待稳定”的分支；不能只凭消息认定还有后代，更不能推断 cache 数据损坏。

**最小整改／验收：** 在现有 watchdog 内分开“后代尚未清除”和“后代已清除但稳定等待未正常收口”的状态／原因；保留 stop 时刻、信号、最后成员、最终退出码及原异常。小子进程或假时钟测试覆盖两种超时、正常完成和最终无 PID；不得因此回写这次 LIMITED 为历史 PASS。修改不能延长正式计算预算，也不能只删异常以取得绿灯。

### V3-07 — P2，资源证据：CPU1 启动点成立，全程 affinity 尚有歧义

实际 launch 摘录在 elapsed=`2.5797472912818193 s` 给出 native Python worker PID 2194643、直接父 watchdog 2194642、affinity `[1]`；watchdog 摘录的 launch shell 包含 `exec taskset -c 1`，ABI 摘录为 MPI1、complex128/int64、单线程、MUMPS。与此同时，terminal `resource_recomputed.worker_affinity_unique` 同时列 `[0..47]` 与 `[1]`，没有列出宽 affinity 对应的 PID、命令和时间段。[实际命令][LAUNCH] [终态资源字段][A2TERM]

watchdog 自身宽 affinity 不等于数值 worker 违反 CPU1；shell 到 exec 的早期窗口也是可能解释。但现有轻量记录不能把 union 中每项逐一归因，因此既不能断言 PDE 全程多核，也不能写成已经独立证明全程 CPU1。

**最小整改／验收：** 只读旧 resources.jsonl，导出按 PID+start_ticks+cmdline/阶段划分的 affinity 区间、样本数和首末时间，明确 supervisor、shell、ABI helper、编译子进程、native 数值 worker；给全时间窗中宽 affinity 的逐项归属。原件读不到则继续标“未独立核验”，不得用启动命令或新 fixture 填补旧采样事实。此项无需 PDE。

### V3-08 — P3，汇总时序：同一 summary 仍有未标历史的旧 V3 当前状态

summary `:248–256` 的“V3整改与待审的有限诊断”仍写累计 4/6、A2 未 READY／未派发、“当前没有后续 READY”，而文首已准确写 5/6 和 A2 终态；“最终 HEAD fc260”也应限定为该组件冻结阶段。[summary][SUMMARY]

**最小整改／验收：** 将该段明确标为 A2 READY 前的历史快照，并指向文首当前终态；限定测试版本措辞。不要改原 READY、失败 JSON 或冻结合同。response_v3、模型总账和开发进展的最新段落已一致，本项不改变任何数值判断。

## 5. 两次正式尝试：实际发生了什么

### 5.1 A1_q attempt2

真实入口建立 180 个六面体，carrier 124530、受约束行 5730，差为 118800 个独立 FE；该计数不等于完成装配／求解。没有 factorization/solve 完成、primary 或完整 q 比较证据。主控在核对 watchdog PID/start_ticks 后发 SIGTERM；原分类 `USER_CONTROLLED_STOP` 与补充 G2 原因并列保留。[A1 停止记录][A1STOP]

提交记录给出的 whole watchdog 为 `159.36019697086886 s`，134 个样本，采样同时进程树 RSS 峰 `948682752 B`，task swap 观测峰 0；leader=-15、watchdog/launcher=2，最终 descendants_cleared=true、remaining=[]。停止时间、PID 身份及退出码相互吻合，支持**已记录范围内的受控停止和最终清理**；本环境未访问完整原资源流和现场进程，不能改称本次亲自监测得到。

### 5.2 A2_q attempt3 的真实路线和规模

实际命令是 `benchmarks.task43_hp_adaptivity.a2_native_p6_diagnostic --phase A2_q --attempt 3` 并带固定 V3 plan/contract；watchdog 带绝对 phase path 和 `--wall-seconds 7200`。worker 使用 `scripts/activate_task40_phi90_pord64.sh` 的资格化 native 环境。运行不是 V2 两次构网前失败的“预测模型”：本次真实建立了 Y6_1 native p6、6×16×6、576 cells、R13/612 模式。[launch][LAUNCH] [terminal][A2TERM]

| 数量 | 实际／推导口径 | 不应混称 |
|---|---:|---|
| carrier 存储长度 | 389832 | 含从属系数，不是独立 FE |
| Floquet 从属行 | 9672 | 从存储中消去的周期从属关系 |
| 独立 FE | 389832−9672=**380160** | 等于 trace 120960 + interior 259200；不是更少 FE 的候选 |
| 实际增广求解矩阵 | **121572×121572** | 内部自由度凝聚后求解 trace，并加 612 模态；不等于完整 FE |
| stored / allocated NNZ | **111681742 / 128135952** | 非零存储和预分配不同；历史预测 112458734 另列，不推测差异原因 |

静态凝聚是在求解前消去可局部恢复的内部未知量，以减小实际矩阵；恢复完整场后这些内部自由方向仍计入独立 FE。A2 是较大的既定参考诊断，FE 为控制 237600 的 1.6 倍，不能用 121572 个矩阵行宣称达成“更少 FE”。[closeout][CLOSEOUT]

### 5.3 primary-before-extra：实现和现场证据分别成立到哪里

A1 在独立 A6 之后、采样及 extra 之前写不可覆盖的 primary NPZ，再广播记录；新可选 raw capture 从真实 action 复制向量。A1 本次未到该段，只有源码／组件证据。A2 在 native `:4281–4288` 写 primary 包，`:4302` 起保存 primary 物理输出，`:4354–4394` 逐阶保存 q8/q10，`:4395` 后才做 extra；随后复用已存 primary，不择优替换。[A1 primary 顺序][A1PRIMARY] [A2 primary 顺序][P6PRIMARY]

原子 helper 使用同目录临时文件、flush/fsync、replace，并拒绝覆盖已保存 NPZ。执行侧首次观察与终态记录引用同一 primary hash，q8/q10 也已在 extra 前完成。这个设计能保护已经写完的文件，不能保证外部 SIGKILL 前还没执行的终态写入必然完成；`except BaseException` 测试不等于信号终止的全面保证。[原子 helper][ATOMIC] [post 索引][POSTINDEX]

| primary 指标 | 执行侧原向量审计记录值 | 冻结门／口径 |
|---|---:|---|
| returned condensed 相对残差 | 3.0440529386035694e−12 | ≤1e−9；求解返回的凝聚系统 b−Ax |
| full-active 显式相对残差 | 1.1972486317982494e−11 | ≤1e−8；恢复后的完整 active 系统 |
| 独立原方程 A6 | 3.078522812304335e−10 | ≤1e−8；运行时另一条物理 action 的检查 |
| 正常 correction | 1 次；2.2945939789534043e−9 → 3.0440529386035694e−12 | 与额外 1 次分开，不能只报告配置上限 2 |
| primary 因子／求解计数 | symbolic/numeric/solve=1/1/2；MUMPS INFOG(1)=0 | 计数证据与残差门同时看 |

本次从提交的范数／计数字段核验一致性；**没有读取原 NPZ 重新算上述向量范数**。执行侧审计对保存向量做范数算术，也不等于离线重装矩阵并重做 A6 action。对 A1 的 constraint-dual trace norm，还必须使用保存的 metric action，不能随意把 trace/interior 数组拼成普通欧氏范数。[primary audit][PRIMARY] [raw scope 实现][REDUCTION]

### 5.4 7200 秒停止和清理

记录中的性能 stop event 为 `7200.713435649872 s`；whole watchdog 为 `7213.133929461241 s`，相差 `12.420493811368942 s` 属停止后的清理。采样／检测粒度导致的约 0.713 秒和清理费用不能解释成获准延长计算，也不能删去使成本看似恰好 7200 秒。[A2 terminal][A2TERM]

5971 个样本所报同时树 RSS 峰为 `27098828800 B`、swap 峰 0，低于本轮 `192 GiB = 206158430208 B` 上限。动态总量／可用内存记录给 reserve=`324465057792 B`、launch/planning cap=`206158430208 B`，与冻结公式相符；未触发内存门。内存通过不补墙钟或完整端点失败。原 cache-stability 异常、最终后代为空、随后执行侧 PID 检查均不存在是不同时间层次的事实；保留 LIMITED，具体诊断缺陷见 V3-06。

## 6. 科学结论：primary 能支持什么

### 6.1 612 通道及全场的独立算术

612 个 key 正好是 top/bottom × m=−4…4 × n=−8…8 × s/p，每组 153，无遗漏、重复或只留强通道。所有旧列与 pre-G3 冻结的 Y6_1 表一致；方向为**旧 Y6_1 → A2_q3 primary**。比较的是物理边界复幅，未把不同内部缩放系数直接相减，也没有额外相位拟合。[primary 完整表][PRIMARY] [冻结旧输入][OLDINPUTS] [模式物理][MODEPHYS]

本次独立按 λ=13.5 nm、50×50 nm 周期、θ=89°/φ=90°、材料参数、出射 beta 分支和 s/p 电磁向量，由表中复幅重算 outward Poynting。使用记录的同一入射功率 `21.815508046604222`，612 条旧／新功率与表逐值相同；独立由角度算入射功率时，最大差 `3.22e−15`。这证明表内物理归一自洽，未证明 FE→模态投影全过程已由本次重做。

| 本次从轻量表重算的 primary 差异 | 数值 | 冻结 q 诊断限值 |
|---|---:|---:|
| 全 612 通道最大功率绝对差，top(0,0,s) | 4.507666462316706e−11 | 1e−7，0 通道超限 |
| R_total / T_total 差 | 4.508143858217295e−11 / 1.889252643216821e−13 | 各 1e−6 |
| 四组边界复幅最大地板归一差 | 6.139994079567577e−11 | 1e−5 |
| A_volume 差 | 4.146905041579885e−11 | 1e−6；使用既有材料积分记录 |
| abs(1−R−T−A_volume) | 5.071976172388304e−11 | 1e−5；体吸收不是用 1−R−T 倒推 |
| q8/q10 记录范数中的最差地板归一差 | 6.04423083302925e−11 | 1e−5 |

q8/q10 使用冻结共同分区的 **1008 个盒**，点数分别为 `1008×8³=516096`、`1008×10³=1008000`，不是 576 个 FE 单元乘 q³。记录域体积约 350000 nm³，前后 points/weights hash 一致；本次重算总场 E/H/G、散射场 E/H 的范数归一，均与表一致。固定 E/H/G 地板分别为 `591.6079783099616`、`1.5703752972513016`、`836.6600265340755`；复幅地板为 1。弱量使用冻结入射尺度，不能据此声称其未经地板处理的相对误差也同样小。补充 G_scattered 不改变冻结验收集合。[V2 合同][V2CONTRACT] [共同分区与旧范数][OLDINPUTS]

### 6.2 Av 的 V2-04 关闭范围

| 同一旧 Y6_1 场的规则 | grating / substrate Av | 总 Av |
|---|---|---:|
| automatic | 0.654703246588021 / 0.03681428019413973 | 0.6915175267821607 |
| 显式 q15 | 与 automatic 相同 | 0.6915175267821607 |
| 显式 q19 | 0.6547032465880176 / 0.03681428019413963 | 0.6915175267821573 |

最大差 `3.4416913763379853e−15`。支持记录给出该旧场 automatic 吸收 form 分析 degree=15，常数材料体积 form degree=3；两者不能混用。V2 允许用同一 hash-bound 旧场三规则重积分补证，此项已按这个限定要求落实。本次外审核的是逐材料功率／归一和 metadata 记录，没有重新积分原场。[Av 支持][AV]

新 A2 的 **operator/physical action/condensation=q19，incident/port=q32，Av cfg=automatic**。旧配置从未因此变成显式 q15；新端点也没有单独测得 actual Av form degree。维持这一区分即可，不需为把文字写成“新 Av=q19”增加求解。

### 6.3 对研究目标的影响

提高 q 只检查同一有限元空间中积分近似的变化；该空间即使有较大空间误差，也可能对 q 几乎不敏感。小离散残差说明保存状态较好地满足所定义的离散方程；没有稳定性或条件数方面的证据，它既不能单独界定离散解误差，也不能界定网格／阶次误差。参考自身 q/R、端口截断、界面／侧壁等未完成资格不因 primary 接近而消失。A2 还同时改变 volume 与 incident/port q，因此不能从这一次比较分别辨认两种变化的独立影响。

| 能力 | 当前正式状态 | 本轮改变了什么／没有证明什么 |
|---|---|---|
| 空间 | **PARTIAL** | 保留既有 mixed-p、one-level 局部 h 的已验范围；不新增 level2、一般多层或跨 h 转移资格。A1 本次未到求解。 |
| 选择 | **PARTIAL** | 九次接受和冻结 R9 保留；R10 因改善未越噪声门拒绝。V3 没有新的 h/p 选择，不将后验 q 结果反馈选择。 |
| 精度 | **NOT_PASSED** | A2 primary 提供有限 q 稳定性观察；R9/R10 对独立 holdout 的失败仍在，没有连续精度或完整 q/R 端点资格。 |
| 同精度全过程成本 | **NOT_ESTABLISHED** | 未有同时达到独立精度与 FE<237600 的候选；不同源码、缓存和 factor/output 生命周期的耗时不能形成同精度加速结论。 |
| 迭代 | **NOT_RUN / NOT_QUALIFIED** | 未运行自适应空间迭代，不能从 direct 或 one-level 组件推断迭代性能。 |

R9 的 110472 FE 比控制 237600 少约 53.505%，是可信的规模计数；精度未过，所以“同精度更少 FE”仍未证明。h10 内部下界 292260 只能排除那个被冻结动作满足 FE 目标，不能排除所有 h/p 策略。A2 的有限 q 证据既不推翻这些历史边界，也不构成“hp 方法已失败”的证明。[原任务][TASK] [历史比较与能力][SUMMARY] [V1 review][V1]

## 7. 配额、费用和测试身份

### 7.1 五次正式 dispatch 不抵扣

G0 的 21 个目录组覆盖 358 个 V2 文件，识别 9 个实际 watchdog 工作流：3 个正式、6 个支持；两个 prelaunch alias 指向既有 A2 formal identity，未重复计费。A1_R 只有准备文件，无实际 watchdog/run。旧场重新采样／重积分、读取保存数组、组件测试和 formal PDE 已分开；支持失败也保留。当前轻量集合没有发现第六次正式调度，仍不能把 canonical 范围索引当作“所有未披露路径绝无启动”的证明。[G0][G0] [旧终态复核][OLDTERMS]

| 正式尝试 | 实际源码完整 SHA | 原结果 | whole-watchdog 秒 |
|---|---|---|---:|
| A1_q1 | ed95df3370973c2f06168ed938666250587ece6d | WORKER_FAILED，observer 运输失败 | 4882.447373806033 |
| A2_q1 | a3657ca1f82fbac0b18aead39ad78285b0887c38 | WORKER_FAILED，phase path 缺失 | 18.740401392802596 |
| A2_q2 | 5b23aabe839effc1cb18f8a31820ea83219ec8d4 | WORKER_FAILED，旧 profile display_label 缺失 | 13.984614439308643 |
| A1_q2 | 28dd150ac2917d6df272324e0b00b960064dad00 | USER_CONTROLLED_STOP；补充实际 G2 缺线 | 159.36019697086886 |
| A2_q3 | d92c210a6704de99362f5e696d157d6c356d9efd | PERFORMANCE_CONTROLLED_STOP；端点不完整、extra 负门 | 7213.133929461241 |

本次独立相加：V2 三次 `4915.1723896381445 s`，V3 两次 `7372.49412643211 s`，五次 **`12287.666516070254 s`**。这只是这五个正式 watchdog 的墙钟小计；不是完整研究成本。支持检查、旧场后处理、审计重试和未监控费用不塞进或假装已被覆盖；嵌套装配/求解阶段不能再与 whole wall 相加，RSS 峰不能相加。[closeout][CLOSEOUT] [支持账][PREINDEX]

历史 56 份终态账、R8 不完整采样窗和测试费用仍各自分账。R8 终态与 h1 辅助 ABI 原字节缺失没有被本轮修复。本轮额外的只读审计失败也不是免费抹去：错误数组 hash 算法、旧 Av 文件定位、NumPy bool JSON 输出等重试只要没有正式模型 dispatch，就属于支持工作；未计量部分继续 not_measured，不能用最终成功倒推其成本。[post 索引][POSTINDEX] [历史成本][COST56]

### 7.2 测试版本不合并成“最终全套通过”

| 记录 | 真正对应的代码／测试身份 | 本次认可的范围 |
|---|---|---|
| 57 passed / 1 skipped，26.71 s | 源码 `81c97e7c3357bbed1b29cab4ff40f2997e8bafdc`；52 个函数 selector 经参数展开为 58 节点 | 本次检查 selector 与测试 AST 数量一致；不是最终 HEAD 重跑全套。skip 是未显式开启的完整 p6 FFCx 矩阵见证。 |
| 最终变化节点 1 passed，1.01 s | `fc260b1e204b8f8f3aeebf136e57de2165b4920b` 的生命周期 AST 节点 | 其后相关实现字节未再改变，可按相同字节复用；仍不证明实际 A1 ledger。 |
| native no-mesh 1 passed，2.51 s | source `28dd150ac2917d6df272324e0b00b960064dad00`；测试当时 untracked，但 SHA256=`63dc239a212316d5f90da435ab2e531011481d8ec5a3fcac0d16edf1e45ffcd7`，与后来提交字节一致 | 真 native runner 创建 ledger 后在 mesh-builder 边界停下；不是完整真实 watchdog+PDE，且只覆盖 A2。 |
| 文档 registry 5 passed，0.06 s | closeout 给出命令、结果摘录，并绑定被测 registry SHA；最终 registry 字节匹配 | 文档结构检查，不是科学／ABI／全仓资格；该条不另含原日志文件 hash 或测试源码 hash。 |
| 历史全仓／clean checkout | 原 1 skip、8 collection errors、0 测试体；旧 clean tracked collection 另受 SLEPc 阻塞 | 没有最终全仓或 CI 通过声明。 |

早先 focused 的 55 passed / 2 failed / 1 skipped 记录保留，后续修的是生命周期断言；不能删除后只留绿色次数。Ruff 为最终与基线各 77 项既有诊断、改变行新增 0，不能写“全量 Ruff 通过”。本次外审没有复跑工作站 native pytest，只核对源码、版本、测试内容和已有记录，另执行第 2 节所列纯检查。[测试索引][TESTS] [native fixture][NATIVETEST] [收口][CLOSEOUT]

## 8. 工程职责和合并资格

数值 action、约束、恢复和 A6 仍位于 src；benchmark 主要负责冻结输入、编排和留证，方向合理。新增 capture 默认关闭，普通 Task40 路线仍在输出前释放因子；V3 opt-in 为提前保存 primary 而延长因子生命周期，其耗时／RSS必须按实际 whole workflow 记账。A1 的 V2 研究 checker 还被新增 scope gate 加严，不能笼统声称所有历史研究入口判定行为完全不变。[native 默认／opt-in][P6PRIMARY] [A1 源码][A1SOURCE]

native V3 路线动态依赖 benchmark 的 checkpoint helper；修复应复用现有模块，不再建立一层控制框架。若未来抽取通用核心，应在真正的 selective merge 中处理依赖，不在本轮为了“架构整洁”重写 runner。

| 分组 | 本次资格 | 后续门 |
|---|---|---|
| 可复用空间／求解／后处理核心 | 有历史研究证据，**未授予最终文件生产合并资格** | 最终依赖闭包、变更行为说明、相关测试体；见 V3-03 |
| watchdog | 可复用工具，但有 V3-06 的具体诊断缺陷 | 局部修复及两个清理原因的回归，不用正式 PDE 验证 |
| A1/A2 adapter、observer、early primary/extra、比较器 | **research-only / NOT_QUALIFIED** | 关闭 V3-01/04/05；组件通过仍不等于正式端点或 production default |
| compact evidence／文档 | 可以保留失败和部分结果；本报告属于该组 | 修复时间范围歧义；不得把文档归档当作源码 merge approval |
| 大型 raw、矩阵／因子／场、未验 level2／迭代默认开关、NN/FTT 输出 | **do-not-merge** | 大原件继续 ignored；未验路线不提升默认 |

本次明确 **不批准 merge/cherry-pick 到 master，也不批准整分支合并**。既有 manifest 的“待审／research-only”态度正确，但必须补清旧 66/27 文件证据对当前字节的适用边界。[manifest][MANIFEST]

## 9. 本次允许的最小后续行动：仅非 PDE 整改

本节是本 review 唯一新增执行授权。**正式 PDE 新增 0；不创建新 formal attempt/run，不签发 READY，不使用封存槽。** 原 V2 第 10 节的两次单次授权已耗尽；修复后不能继续用旧 argv/READY 重派。保持 CPU1/MPI1/单线程的资格化 direct 环境，不重建无关 SLEPc 环境。

按下表顺序做一个有限整改收口；多个独立读日志／纯代码检查可并行，但不并跑重型工作。

| 顺序 | 允许动作 | 可执行验收标准 |
|---|---|---|
| N1 | 修 A1 实际 ledger，复用现有 WorkflowLedger | 真 A1 入口、mesh 前 sentinel；phase/stages 和失败状态可读；真实模型构网/装配/求解 0 次；缺 phase/错父身份先拒绝；旧 READY 不变 |
| N2 | 修 A2 原子 summary 及端点 authority 一致性 | V3-04 两种故障注入均保留原异常和可读失败终态；不存在有效 qualified endpoint；primary hash 不变，数值字段不篡改 |
| N3 | extra 原向量计算后立即保存 | extra 必要的代数恢复及 independent A6/full-active 计算完成后，在后续物理输出恢复/采样前可读；有限数组重算与 scalar 一致；后续恢复、运输或 q10 失败不破坏 primary/extra 已存包；负门不放宽 |
| N4 | 修 watchdog 的清理原因归属；只读旧资源记录补 CPU 区间 | “后代未清除”和“无后代但稳定等待未完成”分别被测试；旧 A2 LIMITED 不重判；宽 affinity 按 PID/start_ticks/命令/时间段完整列明，读不到明确缺失 |
| N5 | 从已有 stage/resource 记录整理一次生命周期费用，不做新积分／采样 | 分列 assembly、normal solve、primary 输出/采样、extra、停止/清理；重叠窗口不相加，缺口 not_measured；不比较不同缓存/源码为同精度加速 |
| N6 | 更新当轮 response、summary、manifest、模型总账／进展和轻量验证索引 | 统一 5/6、A1 2/2、A2 3/3、封存 1；五项能力不变；修复对应最终 source/test hash；历史 review/READY/失败/合同原字节不变 |

测试仅运行每项实际改变的最小 fixture，再做一次相应 focused 收口和文档合同；已有完整 p6 FFCx 见证继续保持原显式 opt-in 边界，本轮不打开。允许小型 Vec/Mat 或进程替身验证文件和终态语义；native 入口测试必须在真实模型 mesh 前停止，不以“fixture”名称包装正式求解。

为使这轮工作保持有限：这些无 PDE 测试驱动每次最多 300 秒，合计实测执行墙钟最多 1800 秒；单驱动同时树 RSS 上限 8 GiB、task swap=0，并受现有更严格可用内存门约束。时间上限参考既有 focused 26.71 秒、native no-mesh 2.51 秒的组件观测；8 GiB 是本轮前瞻测试资源上限，不是已实测 RSS 或完成保证。该预算不适用于任何正式模型，也不授权延长原 7200 秒门。触顶或出现必须进入真实 PDE 才能继续的依赖时停止并记录，不能改名换驱动绕过；失败后的重跑仅限已定位并修复的相关节点，计入同一测试账。

本轮收口应提交 `response_v4.md` 和最小代码／测试／轻量证据到同一执行分支，然后等待审阅。不得修改本报告或旧 review 的裁决来取得放行，也不需要再新建平行控制合同。若只完成其中一部分，逐项标未关闭，不宣称整个工程门通过。

## 10. 下游锁定和今后如何提出新计算

| 路线 | 当前动作 | 未来解锁至少需要什么 |
|---|---|---|
| A1_q / A2_q 重试 | **不允许** | 第 9 节相关问题关闭；说明要区分的剩余科学原因和为什么已有 partial 不足；另行明确新槽位、组上限／总上限、唯一模型与命令、前置门、资源／停止和端点清单，并获得新的明确授权 |
| A1_R | **锁定** | 完整可信 A1_q primary/端点及数值／资源／基线门，另有有限 R 诊断必要性与独立授权；当前没有该前提 |
| A2_R | **锁定** | 完整可信 A2_q 端点和 extra/失败语义处理，另有 R 诊断问题及授权；primary partial 不能代替 |
| B / C | **锁定** | 原计划中所依赖的 A/R 资格与科学前提真正满足，B/C 逐项另审；不由任一 q 的通过自动开放 |
| 同精度全过程成本 campaign | **锁定** | 独立精度通过、候选 FE<237600、对照角色隔离及同等生命周期成本合同；不得用当前五次 wall 小计替代 |
| 迭代接线 | **锁定** | 前置空间／精度门和迭代方案另行审查，不从 direct 残差或组件测试推定 |
| fresh baseline、0.7 nm、NN/FTT、参数盲扫、新控制框架 | **不在本轮范围** | 不因剩余额度、修复成功或 partial 结果自动启动 |

本报告**不建议现在新增正式计算，也不调整既有任何组额度或累计上限**。若未来确有新的科学理由，提案必须在运行前获得新授权；不能把本表的条件当作自动许可，不能默认解封最后一槽。任何容差／接受规则修改均须解释理由、前瞻生效，不能回写 accepted9、R10、A1/A2 失败或本次 extra 负门为通过。

当前可以诚实结项为：真实 h/p 研究取得部分空间和选择能力，最终独立精度仍未达；V3 改善了 primary 保存并获得有限 q 观察，同时揭示实际入口和失败留证的工程缺陷。停止追加昂贵诊断、先完成可复查的有限整改，是本轮可执行的决定。

## 证据与固定源码链接

下列链接均固定到送审提交，历史 review 按其权威提交引用。本报告自身提交 SHA 以 Git commit object 为准，交付消息提供完整值；不在文件内制造自引用 SHA。

[V2]: https://github.com/Rookie1234567/MyFEniCS/blob/fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12/docs/task43_hp_adaptivity/review_report_v2.md
[V1]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/review_report_v1.md
[DIFF]: https://github.com/Rookie1234567/MyFEniCS/compare/fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12...6f6bf3b6ad9b534eb12794a72471157218859de1
[TASK]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/task.md
[PLAN]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/diagnostic_plan_v3.md
[CONTRACT]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json
[V2CONTRACT]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json
[RESPONSE]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/response_v3.md
[SUMMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[MERGECLOSURE]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/selective_merge_dependency_closure_v2.json
[CLOSEOUT]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_formal_diagnostic_closeout_v1.json
[PREINDEX]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/index.json
[POSTINDEX]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_post_pde_audit/index.json
[G0]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/g0_launch_inventory.json
[G4]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_g4_source_input_inventory.json
[OLDTERMS]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/three_historical_terminals_recheck.json
[READY1]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_ready_A1_q_attempt2.json
[READY2]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_ready_A2_q_attempt3.json
[A1STOP]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/a1_q_attempt2/dispatch_and_stop_record.json
[A1TERM]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json
[LAUNCH]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/A2_q3_actual_launch_process_excerpt_v1.json
[A2TERM]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_post_pde_audit/A2_q3_terminal_audit.json
[PRIMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json
[OLDINPUTS]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/g0_g3_frozen_comparison_inputs.json
[MODEPHYS]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/g3_saved_mode_physics.json
[AV]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/v3_root_pre_pde_audit/old_y6_av_support__old_y6_av_three_rules.json
[COST56]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/completed_watchdog_cost_inventory_v2.json
[TESTS]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_final_validation.json
[FAILTEST]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/src/test/test_task43_v3_failure_safe_order.py
[NATIVETEST]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/src/test/test_task43_v3_native_workflow_ledger.py
[A1SOURCE]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/benchmarks/task43_hp_adaptivity/h100_anchor.py
[A1PRIMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/benchmarks/task43_hp_adaptivity/h100_anchor.py#L4057-L4127
[A2GUARD]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py#L84-L124
[A2WRITES]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py#L2380-L2476
[P6PRIMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/src/runners/p6_condensed_direct.py#L4148-L4399
[P6EXTRA]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/src/runners/p6_condensed_direct.py#L4395-L4545
[P6EXTRAWRITE]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/src/runners/p6_condensed_direct.py#L4854-L4922
[ATOMIC]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/benchmarks/task43_hp_adaptivity/candidate_checkpoints.py#L38-L55
[REDUCTION]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/src/solvers/hcurl_variable_p_reduction.py#L609-L846
[WATCHDOG]: https://github.com/Rookie1234567/MyFEniCS/blob/6f6bf3b6ad9b534eb12794a72471157218859de1/benchmarks/subreaper_watchdog.py#L720-L805
