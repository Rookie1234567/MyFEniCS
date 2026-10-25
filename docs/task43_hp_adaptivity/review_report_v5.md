# Task43 正式审阅 V5：文件保护修复接受，CPU1 门未过，联合身份 fixture 尚需小修

审阅日期：2026-10-25（Asia/Singapore）。固定被审提交为 `bc4563f6db55727c70ad8f6bf72475b559a8c914`。本报告依据 V4 review 第 10 节 F1–F4 审查有限非 PDE 整改，不追认后续字节，不改写历史 review、冻结合同、READY 或失败记录。

## 1. 分开裁决

| 裁决维度 | V5 决定 | 含义 |
|---|---|---|
| F1–F4 工程整改 | **部分接受：F1、F2、F4 接受；F3 部分接受** | 上轮两个实际文件写入缺陷已经修复。F3 的三类写失败与现有独立否决用例成立，但全包共同缺失身份时仍可能返回 true，需测试 helper 内的有限修复 |
| 资源与测试资格 | **有限工程证据可用；严格 CPU1 为 NOT_PASSED** | 不能将启动 taskset、preflight 末态或测试通过数代替全过程 CPU1；也不能因 CPU 偏离自动否定文件保护断言 |
| 新增正式计算 | **不批准，新增 PDE / dispatch / attempt / READY = 0** | 5/6、A1 2/2、A2 3/3 和封存槽均不改变 |
| 下一轮允许动作 | **仅第 9 节的有限非 PDE 收口** | 先读取已有原件；修补测试内身份存在性；最多两次短支持 driver，累计不超过 240 秒。不得重跑 25/31 全套、重建环境或运行模型 |
| 生产与实际合并 | **生产 merge gate = fail；本次不授予实际 merge approval** | 文档/轻量负证据可作未来独立迁移候选；研究入口与共享数值核心不因本轮组件证据获得生产资格 |
| 科学结论 | **PARTIAL / CONTROLLED_NEGATIVE 不变** | 空间和选择仍部分完成，独立精度、同精度全过程成本和迭代资格没有新增通过证据 |

本轮处理的是两类工程可靠性：失败后不改坏旧目录，以及把保存文件的身份和当前使用资格说清楚。它们使运行更容易追溯，但不增加有限元空间的表达能力，不改善已经算出的场，也不消除现有精度缺口。下文的“联合读取”指同时核对几份文件、退出状态和关联身份；一份 JSON 完整写入不代表这一组文件形成了一个不可分割的事务。[V4] · [RESPONSE5]

## 2. 身份、差异及本次实际核验范围

| 对象 | 核对结果 |
|---|---|
| 仓库 / 执行分支 | Rookie1234567/MyFEniCS / task43_hp_adaptivity |
| 固定被审 SHA | bc4563f6db55727c70ad8f6bf72475b559a8c914 |
| 固定 tree | f0615755d9ed27b7e24e31f17c986ff78a7bc948 |
| 直接父提交 / 正式 V4 review | d1a005385bcaa736a2e2b9d0d411dca35a93868a |
| 长期代码基线 | 405e3aff42ac421a4c99315df1ed9b96941ecbe4 |
| 基线祖先关系 | compare 为 ahead，64 个后续提交、behind=0，merge base 正是指定基线 |
| V4 review → 本次对象 | 1 个提交、13 个路径：2 个研究入口 Python、2 个测试 Python、7 个 Markdown、2 个新 JSON |
| 远端核对 | 首次读取及生成本 review 提交前的再次核对均指向固定被审 SHA，没有其他后续提交 |
| 工作站本地状态 | “干净、ahead/behind=0/0”仍是执行方陈述；本审阅未访问 canonical worktree，不能独立确认该本地事实 |
| 本 review 的完整 SHA | 由新增本报告的 Git commit object 确定，在交付消息报告，不在文件中制造自引用 SHA |

已完整阅读三层 AGENTS、任务书与 V4 review，并直接取得、检查全部 13 个改动路径、当前回应和两份 V5 记录；同时检查 README、summary、manifest、模型总账和进展中的 Task43 当前状态与相关历史范围。未变化的候选留证、watchdog、activation、旧合同和历史记录按固定 tree 的实际字节核对，不以旧聊天摘要替代源码。[DIFF5] · [TASK] · [V4] · [MANIFEST5]

审阅缓存共 192 个 tracked 文件与固定 tree 的 Git blob 匹配。全部差异中，records 只新增两份 V5 JSON；历史 review、合同、READY、正式失败 records 和 response_v4 未被修改。总账中对历史“三段空 cmdline”的订正明确写出旧说法和当前更正，未伪造原始命令。

本审阅还做了以下独立小检查：

- 用固定 A1 wrapper / writer 的 AST 和临时 JSON 对照父版本与当前版本，复现并确认旧目录保护行为改变；
- 用固定 A2 函数、纯文件 checkpoint writer 和小型合成数组核对原两种故障、联合读取既有用例及三类写失败；另复现共同缺失身份反例；
- 从最终测试字节精确重构改名前文件，核对 SHA；交叉核对 source/test、最终文档 hash、六次费用和资源摘录。

这些检查没有运行工作站 pytest、native main、MPI/PETSc/FEM 求解、构网、装配、分解、旧场采样或积分。合成 NPZ 是本次小 fixture 的临时数据，**不是工作站保存的 A2 原向量**。工作站 ignored 原始 stdout、resources 流、driver 快照和历史场 NPZ 未独立核验，具体缺口见第 7 节。

## 3. F1–F4 逐项验收

### 3.1 F1：接受，关闭 V4-01 的实际旧目录写入缺陷

`h100_anchor.py` 第 4917–4923 行每次新建 context，并将 `run_root_acquired` 置为 false；第 3265–3281 行在 rank 0 非空检查 / mkdir 成功、广播无错误并完成同步之后才置 true；第 4931–4936 行以该标志为失败写入的必要条件。此处只增加三行状态维护与判断，没有改数值方程或求解参数。[H100]

真实-main 测试第 278–368 行分别构造带 / 不带旧 terminal 的非空临时目录，实际调用 `h100_anchor.main`，要求命中特定的“refusing to overwrite nonempty output root”异常；调用前后的“相对文件名 → SHA256”字典完全相等，mesh 与 solver sentinel 调用均为零。第 202–275 行保留空 root 的 mesh 前正例，核对 ledger 阶段、terminal 引用/hash、原异常和所有 continuation=false；第 371–401 行新增 missing phase / wrong parent 的具体 stderr 断言，消除了只凭 exit 2 可能误中更早错误的歧义。[NATIVE_TEST]

本审阅抽取真实 wrapper / writer 的独立复现结果：

| 版本 / 临时目录 | 文件集合与旧 hash | 原拒绝异常 | 失败 writer 是否被调用 |
|---|---|---|---|
| V4 父版本，无旧 terminal | 两个旧 JSON 改变，并新增 terminal | 保留 | 是 |
| V4 父版本，有旧 terminal | 旧 terminal 保留，但两个旧 JSON 改变 | 保留 | 是 |
| V5，无旧 terminal | 全部不变 | 保留 | 否 |
| V5，有旧 terminal | 全部不变 | 保留 | 否 |

此复现只证明对应文件逻辑，不冒充真实 main 的工作站再运行。两个非空目录 fixture 为隔离文件逻辑，把 parent 环境值设成测试当时的 `os.getppid()`；它们本身不证明真实 watchdog 拓扑。要求实际 native watchdog 的空 root 正例第 215–216 行仍保留未弱化的直接父身份断言。因此应将文件保护、实际父身份和真实 PDE 现场分开评价。

旧 A1_q2 在已构网、进入装配后才因缺 ledger 被主控停止的事实和错误放行责任不变。F1 不回填该现场，也不解锁 A1 重试。

### 3.2 F2：接受，关闭 V4-03 的原件路径/hash 错配

A2 adapter 第 98–114 行先保存旧 comparison 原字节 sidecar；第 131 行现在使用 `original_ref["path"]`，第 132 行以 `current_record_path_before_demotion` 单独保留原当前路径，第 133 行仍绑定旧字节 hash，第 165 行调用原子 writer 替换当前 comparison。[A2]

原两条后处理故障测试第 564–702 行保留，新增第 690–694 行沿当前 comparison 的原件路径读取真实字节并计算 SHA。原测量、primary、原 callback 异常、q8 引用、sidecar、当前 comparison hash 和降权限断言仍在。本审阅纯文件复核与这些断言相符。[FAIL_TEST]

该修复是文件追溯字段修正，不是重新计算 comparison，更没有修改历史 A2_q3 数据。fixture 的 `0.25000001` 等测量是合成数据，不能列为新物理结果。

### 3.3 F3：部分接受，既有故障用例有效，但身份存在性仍缺一项

新增联合约定全部位于测试文件：

| 位置 | 实际检查 | 本轮评价 |
|---|---|---|
| 第 705–783 行 | 小 primary NPZ 与 summary / comparison / terminal 一致合成包 | 正例明确为 FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION |
| 第 786–866 行 | 从实际文件计算 hash，检查退出码、状态、权限、primary 引用与 source/contract/plan 一致性 | 有实质联合读取；存在第 4.2 节的共同缺失身份反例 |
| 第 869–951 行 | 一个正例、12 个独立否决案例 | 现有断言成立；不同否决不是只靠同一个坏 hash 假通过 |
| 第 954–1069 行 | 对真实 A2 failure writer 注入 sidecar、comparison 降权、summary 降权三类失败 | 原异常、primary 字节和测量保留；单份旧 true 不授予资格 |

修改 comparison / terminal 权限或 source 时，负例会同步更新其真实字节 hash，再检验对应否决规则，避免把身份/权限测试退化为“总有一个旧 hash 不匹配”。三种 writer 故障也在退出码 1 和 0 两种读取条件下都拒绝，并核对原异常对象没有被二次写入错误替换。[FAIL_TEST]

本审阅在 AST 抽取的函数和临时文件上核对了原 18 个相关场景断言：2 个 F2、1 个一致包、12 个独立否决、3 个 writer 故障。它们支持当前有限工程陈述；不等于工作站 25 项 pytest 重跑，不消除 CPU 门失败，也不覆盖任意磁盘损坏或所有故障组合。

回应准确说明单文件原子性不等于多文件事务、summary/comparison 可残留 true、整体不可写时 terminal 也无法保证保存，以及当前 V3 没有自动 consumer。源码 diff 没有启用 A2_R 或新建 controller。**仍不能把“缺失绑定均否决”无条件写成已完成**，原因见 V5-02。

### 3.4 F4：接受，历史与当前范围区分正确

当前 response、README、summary、manifest、总账和 progress 都将旧空 cmdline 更正为三段、26 条成员观察：两个 `other_or_unknown` 各 9 条，一个 `MPI_runtime` 8 条；保留旧 response_v4 原字节，不补造命令。旧 affinity JSON 的尾三段及当前更正对应一致。[RESPONSE5] · [OLD_AFFINITY] · [REGISTRY] · [PROGRESS]

文档明确保留：

- 25 项最小通过、30/1 focused 失败和 2 项局部恢复的分次事实；
- 四个 Python 文件与最终文案的字节范围不同；
- CPU1 NOT_PASSED、两次未监控 metadata 失败和费用未测；
- “104 项 hash 一致”没有持久逐项清单，不能称本轮独立核验；
- 旧 V4 support 原件和 A2_q3 场/向量 NPZ 本轮没有重读。

第 4.2 节新发现的 fixture 缺项应在下一份 response 中追加，不要求改写 response_v5 或既有失败记录。F4 接受不意味着其中引用的工作站原件已经由本审阅亲自核验。

## 4. 按严重程度排列的剩余问题

### 4.1 V5-01 / P2：严格 CPU1 门被可读观测反证，不能签发新的执行资格

**证据定位：** `v5_root_resource_recheck.json` 的 `runs[*].affinity_exceptions`，以及 validation 的 `resource_recheck`。以下索引均为 zero-based。[RESOURCE5] · [VALIDATION5]

| 支持 driver | 样本索引 | PID / start_ticks | 记录中的角色与状态 | affinity |
|---|---:|---|---|---|
| minimal_attempt2 | 2 | 3727682 / 283474809 | ABI preflight Python，R | [0] |
| minimal_attempt3 | 12 | 3728219 / 283480222 | pytest worker，S | [0] |
| focused_recovery2 | 3 | 3757211 / 283567338 | ABI preflight Python，R | [0] |
| focused_recovery1 | 6 | 3755876 / 283560945 | 空 cmdline，Z | 缺失 / null |

前三条是可读 affinity 的明确偏离；最后一条是单独缺测，不能归为 CPU0，也不能填成 CPU1。即使删去 Z 条目，前三条仍足以否定严格 CPU1。

affinity 是允许线程运行的 CPU 集合，并非某一段实际 CPU 用时。Linux 的该属性按线程设置，可被后续调用改变；fork 继承、exec 保留当前值，不使其永久固定。watchdog 第 556–567 行对成员 PID 调用 `os.sched_getaffinity`，没有遍历所有线程；遇 OSError / ValueError 时允许标记采样不可得。因此这三条反证不能用启动命令或 preflight 末态 [1] 抵消，也不能推导出“在 CPU0 上实际求解了多少工作”或“所有线程全程受检”。[WATCHDOG] · [LINUX_AFFINITY]

**原因尚未确证。** activation 脚本设置数值库单线程，但没有设置 affinity；它不能解释重绑定来源。当前 Git 里没有实际支持 driver / helper / preflight 的完整快照字节，也没有异常前后的原始资源行，无法确定是哪个阶段、哪个调用或哪条启动路径导致变化。不能未经取证归因 MPI，也不能把改版本字符串断言的 preflight 修复当成 ABI 或绑定问题已经全部解决。[ACTIVATION] · [VALIDATION5]

**影响分开处理：**

| 判断 | 裁决 |
|---|---|
| F1/F2 的确定文件保护断言 | 可以保留有限工程证据；现有偏离不足以自动否定文件字节比较、原异常或路径修复 |
| 本轮“严格 CPU1 条件下全套通过” | 不成立；资源门保持 NOT_PASSED |
| wall / RSS / swap / cleanup | 按提交的轻量数值和终态接受其支持门范围；没有独立重读 raw 流，不给无条件现场认证 |
| 科学计算结果 | 本轮没有新 PDE；不由 CPU 偏离推出 h/p 方法失败，也不重写旧科学结论 |
| 新正式计算 / production qualification | 继续禁止；不能凭低费用或测试 pass 绕过该门 |

执行方最终补查发现偏离后停止，当前披露是准确的；这不消除该偏离在整轮支持运行后才被发现的门控缺口。第 9 节只允许最小非 PDE 取证和局部修复，不能以资源问题为理由重跑全部 F1–F4、全仓或模型。

**验收条件：** 保存同一进程身份的异常前后原始摘录、原启动脚本字节及阶段 affinity；查明或保留具体未知边界。未来确认 driver 的启动、关键阶段自检和完整资源采样中必须均无可读活进程偏离，异常/缺测有原样记录并据此否决；明确检查的进程/线程和采样范围，不将离散观测称为严格连续保证。不得把结束前重新 taskset 当成“全程通过”，不得放宽旧 CPU1 门。

### 4.2 V5-02 / P3：联合读取 helper 会接受全包一致缺失的 source/contract/plan 身份

**定位：** `test_task43_v3_failure_safe_order.py` 第 812–865 行；第 881–951 行的现有独立负例没有覆盖这类共同缺失。[FAIL_TEST]

`_synthetic_joint_read_has_no_engineering_veto` 先用 `.get` 获取身份，再比较各处相等。单个文件漏一个字段会与其他完整值不一致；如果所有相关记录共同漏掉该字段，比较就可能成为 `None == None`，仍返回 true。这是“相互一致”与“身份实际存在”两个条件没有同时检查。

本次固定源码最小复现从已有合成一致包出发，仅改变身份，保持状态与原小数组不变，并依据实际写出字节重新计算 comparison、terminal 和 primary 的 hash：

| 反例 | 改变方式 | 现有 helper 实际返回 | 应有返回 |
|---|---|---|---|
| 共同缺 source SHA | summary、comparison、NPZ identity 省略 source；terminal 对应值为 null | true | false |
| 共同缺 contract SHA | 对应 contract 字段在关联记录中共同省略 / null | true | false |
| 共同缺 plan SHA | 对应 plan 字段共同省略 / null | true | false |
| 三者共同缺失 | 同时应用上述三个变化 | true | false |

这些反例不依赖错误 hash；primary 引用、NPZ 内嵌 identity、comparison 与 terminal 的实际 hash 仍相互匹配。因此不能继续泛称“缺失绑定均否决”。这是当前 test-only 约定的具体漏项，**不是已部署生产漏洞、真实端点已经误放行或旧数值证据被破坏**。

**最小整改：** 只在现有测试 helper 进行一致性比较之前，要求 source SHA、contract SHA、plan SHA 实际存在且为非空字符串；可按当前 40/64 位 SHA 字段形状作轻量检查。增加三个“全包共同缺一项身份”的参数化负例，保留一致包正例和原独立否决；若实现同时处理 null / 空字符串，测试明确所覆盖输入即可，不做组合盲扫。

**验收条件：** 上表反例拒绝，原一致包仍只返回“无该约定的工程否决”，原 12 个独立负例与 3 个 writer 故障继续成立；primary/测量/原异常断言保留。只补验这个 helper 的直接相关节点，不需要修改已修好的 A1/A2 adapter，不新增可信身份平台、生产 consumer、A2_R 或 controller。

### 4.3 持续限制，不是新增实现缺陷

| 限制 | 当前处理 |
|---|---|
| 支持驱动现场原件不可访问 | hash 可作索引，不能替代原脚本、pytest stdout、资源流或清理现场 |
| 没有最终同字节 31 项完整通过 | 局部恢复合理，仍按原分次结果陈述，不为得到漂亮通过数重跑全套 |
| 完整 p6 / 全仓 / ABI 资格 | 本轮未运行完整 witness 或全仓；历史 collection / SLEPc–complex PETSc 缺口仍保留 |
| 完整科学端点 | A1_q2 无 primary，A2_q3 不完整且 extra 严格下降失败；F1–F4 不回填 |
| 生产合并依赖 | 历史 overlay 不覆盖全部最终共享文件和新增研究路径；本轮没有 production 资格测试 |

## 5. 六次支持驱动、失败恢复与费用

### 5.1 分次结果与授权符合性

| 次序 / driver | 实际保存的结果 | worker / launcher exit | whole-watchdog 秒 | 资源样本数 |
|---|---|---|---:|---:|
| 1 minimal_attempt1 | 模块路径断言在 pytest 前失败 | 1 / 2 | 8.914583516307175 | 13 |
| 2 minimal_attempt2 | 已知 OpenMPI 版本字符串尾 NUL 比较在 pytest 前失败 | 1 / 2 | 4.417637757025659 | 9 |
| 3 minimal_attempt3 | 25 passed，pytest 报 11.59 秒 | 0 / 0 | 19.871055574156344 | 28 |
| 4 focused_attempt1 | 唯一 focused：30 passed、1 failed，pytest 报 6.70 秒 | 1 / 2 | 15.243286705110222 | 23 |
| 5 focused_recovery1 | 新增 Ruff RUF059 阻断，pytest 未执行 | 1 / 2 | 8.28013485390693 | 12 |
| 6 focused_recovery2 | 修正未用局部变量名后，两个相关节点通过，pytest 报 10.11 秒 | 0 / 0 | 28.119390034116805 | 33 |
| 合计 | 4 个失败支持 driver、2 个完成支持 driver；不是正式模型尝试 | — | **84.84608844062313** | **118** |

六个唯一 watchdog 目录、各次 summary / resources / worker.log 的 hash 引用在两份 JSON 中逐项一致；本审阅重新求和与交叉核对，没有重复计费。最大单次 28.119390034116805 秒；最大同时进程树**采样** RSS 为 263839744 字节；六次记录的 task swap 峰为 0、descendants_cleared=true。就轻量记录的数值而言，wall/RSS/swap/清理满足 300 秒/600 秒/8 GiB 的旧支持限额；严格 CPU1 独立失败。[VALIDATION5] · [RESOURCE5]

两次主控 metadata 检查分别因“假定所有成员 affinity=[1]”和“假定 Z 记录必有 affinity”失败；没有持久脚本/stdout、没有 timer，耗时必须保持 not_measured。它们不伪装为受监控 driver，也不能从费用账中写成零耗时。最终文案后的小型 JSON/hash/diff 检查同样未监控。因此 84.846 秒是六个 driver 小计，不是所有活动总成本，更不是 Task43 同精度成本或任何加速比。

两次 preflight 失败的具体归因与记录、既有环境身份相容；但原 preflight 快照未取得，不能仅据 hash 将具体修复代码标为已独立检查。它们都按支持失败计费，没有新增正式 PDE 的证据。

focused 失败与实际测试第 215–216 行相符：记录称 watchdog PID 为 3751507，而 pytest 直接父进程是 helper PID 3751589；断言在调用 main 之前失败。它属于支持驱动拓扑及主控审查遗漏，不是 mesh、ledger 数值接线或解的失败。恢复没有删除该断言。[NATIVE_TEST] · [VALIDATION5]

### 5.2 是否违反“最多一次 focused”

**按现有记录，未违反该项数量限制。** 只有一次 31 案例 focused；随后第一窄恢复停在 Ruff，第二窄恢复只运行原父身份失败节点和局部变量改名影响的合成一致包节点。没有把整套再跑一次改名为 recovery，也没有从正式配额中抵扣失败。

这项恢复范围符合 V4 允许“定位普通错误后只重跑相关节点”的规则。严格 CPU1 未满足是另一项资源约束，不能因恢复范围合规而被豁免。由于未取得完整原驱动与原资源流，此结论限于提交记录与源码的相互一致性，不声称已独立排除工作站所有未列活动。

## 6. 测试字节、最终文案和历史证据

### 6.1 dirty worktree 与提交身份不能混用

validation 明示 `tested_source_head=d1a005...`，同时注明实际测试的是含 V5 修改的 dirty worktree，并用逐文件 SHA 绑定。这不是“在 clean d1 提交测试 V5”，也不是提交后在 clean bc4563 上完整测试。

四个最终 Python 文件的 SHA256 均与记录和固定 Git 内容对应：

| 文件 | 最终 SHA256 | 与历史测试的关系 |
|---|---|---|
| h100_anchor.py | 3296d5cab3a0ce5315acc8104eb6e0d2dc092a9681d53b8ce2fe011ed57ac790 | minimal 与 recovery2 同字节 |
| a2_native_p6_diagnostic.py | b5c68b85448b9d3afd887d722f759c9e5a6dd1abc152bf98628c4772b9b90bbc | minimal 与 recovery2 同字节 |
| test_task43_v3_native_workflow_ledger.py | ef8bd230d0286c0dbde72d42262e408cafe21b297bb2c6a201d059b1d58a730c | 父身份断言和 F1 测试未因恢复被弱化 |
| test_task43_v3_failure_safe_order.py | 6ed75ffffc72e7db26bff75a3e1a94c4c515cd555cc0c3c0df3c580d5fd6135f | recovery2 最终字节；此前为下述旧 hash |

只把最终第 872 行唯一 tuple target `_comparison_path` 改回 `comparison_path`，完整旧文件 SHA 恰为：

`41f03f3dc2b040cfb832a1429ff9ec8b029991151770f1b52733c689f8ef3f8b`

该变量只有一次 Store、没有 Load，确为未使用局部变量改名，没有其他字节变化。这支持对未受改名影响的用例保留旧逻辑证据，同时接受针对受影响节点的局部补验；**仍不得把 25、30/1 和 2 拼成最终同字节 31 passed**。[FAIL_TEST] · [VALIDATION5]

### 6.2 静态检查与追加文案

recovery2 的四文件 Ruff 为 baseline/current/new=0/0/0，compileall、当时 5 个 JSON、10 个链接目标、7 份文档检查和 diff check 记录通过。它与 V4“八文件 21/21、新增 0”的范围不同，不能称所有历史 Ruff 问题已被清除，更不是全仓或 CI 全绿。

该次之后六份文档又有更新，docs/README 未变；root resource recheck 及最终文案另有最终 hash 列表。列表中 8 份文件的 hash 均与固定提交相符。最终追加文案只声明轻量 parse/hash/diff/existence 检查，未冒称由此前 pytest 或静态 driver 覆盖。

旧 66-path overlay 中，本轮差异只触及已经在 V4 不同于 overlay 的 h100_anchor；27 个核心路径与本轮差异交集为空。因此基于 V4 已有核验，59/66 和 23/27 的历史边界不变。本次没有重新下载、重验全部 66 项；不能把差异推导写成一次新的全量 overlay qualification。[MANIFEST5] · [CLOSURE]

## 7. 原件缺口与最小补核范围

下表的路径是已提交记录提供的原件索引，**不是本审阅已经访问的原件**。

| 尚未独立核验的原件 | 具体入口 | 对本次结论的限制 |
|---|---|---|
| 六次支持运行原流与终态 | `benchmarks/artifacts/task43/v5_support/{minimal_attempt1,minimal_attempt2,minimal_attempt3,focused_attempt1,focused_recovery1,focused_recovery2}/watchdog/{summary.json,resources.jsonl,worker.log}` | 118 是提交记录的总行数；本审阅核对其算术和摘录，没有亲自遍历 118 原始行、重看退出/清理现场 |
| 实际启动脚本和 ABI preflight | validation 的 `driver`、`abi_preflight`、`preserved_driver_snapshot_root`；包括初次 driver_sources 以及后续 driver_snapshot | 不能由命令 argv 或末态 ABI 推断完整 shell exec、导入顺序、重绑调用或真实运行库路径全过程 |
| focused helper 当次字节 | `focused_attempt1/driver_snapshot/benchmarks/artifacts/task43/v5_support/run_focused_checks.py`，声明 SHA 8ee22960…；恢复 helper 声明 SHA 0349752b… | 同一工作路径后来被修改；只有对应快照能核验当次实际 helper，不能读取后来版本代替 |
| pytest / Ruff / 静态原始输出 | focused 的 `pytest.stdout.txt`、各 worker.log、Ruff delta、source_sha256.txt、driver_sha256.txt | 可核对 Git 中 selector、最终字节和记录一致性，不能把摘要中的 pass 当作亲自执行 |
| CPU1 异常邻域 | 第 4.1 节四个样本所在 resources 原流及同 PID/start_ticks 前后记录 | 需要定位阶段及身份，不能仅靠三条摘录指定根因 |
| 旧 A2、V4 support、104 清单 | 原 V3 post-PDE / V4 audit 索引；104 项无持久逐项清单 | 不重新授予旧原向量、清理、性能或全量 hash 的外部核验；不存在的清单不能补造 |
| 两次未监控 metadata 失败 | root resource recheck 的 prior_unmonitored_checks | 没有脚本/stdout/计时，只接受其明确缺失陈述，不要求追溯捏造数据 |

下一轮只需取本轮相关已有原件和异常小窗口、保存可审阅摘录与生成规则；不要求全盘恢复旧研究数据，不下载大型场，不重新求解/采样/积分。若某份旧原件确实缺失，保持未独立核验和对应限制，不能以新运行替代旧现场。

## 8. 科学结论与选择性合并

### 8.1 五项能力和配额

| 能力 / 额度 | V5 后状态 | 本轮不能改变什么 |
|---|---|---|
| 空间 | PARTIAL | 没有新 h/p 空间、一般多层 h 或新组合资格 |
| 选择 | PARTIAL | accepted9/R9 为最后接受状态；R10 拒绝、无第十次接受不变 |
| 精度 | NOT_PASSED | 文件保护、低代数残差、同空间 q 稳定性和 fixture pass 都不能替代独立空间精度 |
| 同精度全过程成本 | NOT_ESTABLISHED | 六次支持 driver 的 84.846 秒与旧模型 wall 分账，不能作数值加速证据 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 没有迭代接线或 direct-equivalent 资格 |
| 正式额度 | 5/6；A1 2/2，A2 3/3，1 槽封存 | 不重分配、不扩大、不自动使用 |

R9 的 110472 独立 FE 小于对照 237600，但独立精度未通过；自由度条件和精度条件不能分拆成总体成功。旧 A2_q3 的 primary partial 与 extra 严格下降失败、7200 秒停止、完整 endpoint 缺失和 LIMITED 清理边界全部保留。V5 没有新模型端点，因此不能据其工程失败或工程修复判断所有 h/p 方法有效或无效。[SUMMARY5] · [V4]

### 8.2 分组裁决

| 组 | 文件与依赖 | 当前可接受证据 | 合并资格 / 阻塞 |
|---|---|---|---|
| 文档 / 轻量证据 | 本 review、response_v5、V5 两份 JSON、Task43 README/summary/manifest；docs/README、registry、progress 中相关 Task43 补丁；被引用的历史轻量记录 | 身份、费用算术、失败保留、原件缺口和研究状态可以保留为档案；F3 泛称由本 review 明确限制 | 可作未来 docs-only 迁移候选；目标 clean base 与链接闭包未在本轮审阅，不给本次实际 merge approval。不得整文件覆盖 master 的其他任务进展 |
| A1 研究入口 | h100_anchor.py、native-workflow test、failure-safe test；既有 WorkflowLedger、candidate_checkpoints 和原数值依赖 | F1 文件保护已修复，相关局部证据有效 | Research-only；不能把入口 fixture 当正式端点或 production 资格 |
| A2 研究入口 / test helper | a2_native_p6_diagnostic.py、failure-safe test、candidate_checkpoints、p6/native 既有依赖 | F2 原件追溯修复；F3 三类写失败已有证据 | F3 存在性小修待关；无部署 consumer，无 A2_R，不能迁移为默认生产防线 |
| 可复用 watchdog | benchmarks/subreaper_watchdog.py、test_354 及既有 profile / ledger 依赖 | V5 未修改；V4 分类修复证据保留 | 本轮没有新的目标基线验证；CPU1 采样不是自动绑定保证，不据本轮获得新的生产合并批准 |
| 数值核心 / 共享行为 | manifest 既有 A–D 原子依赖组；尤其 common_3d_case_flow、dtn_port_3d、hcurl_variable_p_reduction、solve_maxwell_3d_stage_4b_block_grating | 旧 PDE / overlay 仅按原身份保留；V5 未改这些数值文件 | 生产门仍未过；组件文件测试和旧 overlay 不覆盖最终共享文件全部资格 |
| 整分支、未资格化默认与大型原件 | 全 research branch、历史 READY 自动启动、ignored 场/矩阵/因子/完整日志 | 无支持资格 | Do-not-merge；不创建实际合并、不向 master 写入 |

本报告只提交同一研究分支。未来即使某一组取得明确 merge approval，仍需用户授权并由 Codex 执行具体选择性迁移；此次没有执行合并。[MANIFEST5]

## 9. 下一轮唯一允许范围：身份 fixture 小修与 CPU1 有限取证

**没有新增正式模型计算许可。以下是新的非 PDE 支持上限，不是 V4 剩余预算续用，更不是封存 formal 槽的使用权。**

### 9.1 允许的顺序与验收

| 顺序 | 允许工作 | 完成条件 |
|---|---|---|
| S1 先只读已有原件 | 核对第 7 节本轮 driver / helper / preflight 快照，四条异常及同身份邻域；查实际 fork/exec、显式 affinity 设置和导入顺序 | 将观测、推断、未证原因分开；保存小型逐项索引、关键原始行、hash、PID/start_ticks、退出与清理字段。无原件则明确缺失，不补造 |
| S2 只修现有测试 helper | 修 V5-02 的 source/contract/plan 存在性检查，增加共同缺失负例 | 一致包正例、原独立负例、共同缺失负例及三类 writer 故障的直接相关节点满足约定；不改生产 consumer，不改冻结数值合同 |
| D1 最多一次定位 driver | 在现有 activation / watchdog 路线中记录启动、相关导入前后、pytest 入口的身份与 affinity；可使用提前退出的小脚本或 fixture，不能调用模型 | 只定位启动/导入/执行链；出现活进程偏离或关键阶段无法读取即保存现场并停止，不继续整套测试；不得以末尾重新绑核掩盖偏离 |
| D2 最多一次修复后确认 driver | 只有已有证据将问题定位到可局部修复的启动/检查路径，且 S2 已完成，才确认同一链；运行 S2 直接节点，必要时加一个现存 A1 mesh 前 sentinel 节点 | 实际父身份不弱化，活进程可读 affinity 均为[1]，异常与 Z/退出缺测如实分类；source/test/driver 字节、结果、全生命周期费用和清理完整保存 |
| S3 收口 | response_v6.md、必要轻量验证记录、当前 summary/manifest/总账/进展 | 分别列工程、资源、科学、合并状态；提交推送同一分支后停止等审，不签 READY |

S2 的代码可以先静态修好；若 CPU1 原因仍未定位，不能为了取得 S2 的 pytest pass 绕过 D2 前置。此时只交付静态修复和诊断负结果，保留未运行项。若 S1 的已有原件已足以定位，并完成必要局部修复且满足 D2 前置，可跳过 D1，仅运行一次 D2 确认；若已经运行 D1，其次数和费用照计，不因后续确认而重命名或抵扣。不要求跑满额度。

### 9.2 硬边界

1. **最多 2 个受监控支持 driver，每个 whole-watchdog ≤120 秒，本轮累计 ≤240 秒。** 失败、preflight 失败和重试都计入；不允许第三个换名启动。该上限依据 V5 最长支持 driver 28.119 秒留有限诊断余量，不是新模型预算。
2. 同时进程树 RSS≤8 GiB，task swap=0，并服从现有更严格可用内存门；CPU1、MPI1、数值库单线程要求不放宽。诊断中观察到偏离只能记 fail / not_passed，不能授予资源资格。
3. D1/D2 使用新的 Task43 support 目录；历史 attempt 与原件只读。若修改启动包装，保留旧脚本快照，不覆盖本轮六次原驱动来源。
4. 不修改系统配置、全局 affinity/cgroup、共享 ABI、库版本或其他任务环境。不安装环境，不通过更换 MPI/解释器、重新构建依赖来绕过问题；未知 ABI blocker 立即停止。
5. 不运行完整 25/31 focused、全仓 pytest、完整 p6 FFCx witness、真实 mesh、装配、factor、solve、旧场 replay/采样/积分。若实际 main 被用于一个确认节点，首次 mesh builder 必须被 sentinel 拦截。
6. 保留 h100/A2 当前已关闭修复；除有具体直接证据，不再次重构这些入口。只改现存 helper、必要局部启动/检查代码和相关说明，不新建控制平台。
7. 保存完整命令、source/test/helper/shell hash、环境与父子身份、逐阶段 affinity、stdout、终态、RSS/swap、whole-wall 和最终清理。即使停止，也必须如实保留失败；不得把 post-edit 文案写成先前测试覆盖。
8. **完成 S1 和至多一次 D1 后原因仍未定位，或触顶、需要第三个 driver、模型或环境重建时，即结项为有限未解决，不继续试探。** 文档整理可继续；不得因只用少量时间而自动扩大授权。

完成上述工作也不自动解锁正式计算。任何将来的 A1/A2 q 申请仍须另行提出明确科学问题、为什么既有 partial 不足、冻结输入、唯一 attempt 目录、组与总额度、实际入口 Gate、资源与失败停止规则和必须保存的完整端点证据，获得新的正式授权。A1_R/A2_R/B/C、fresh baseline、同精度成本 campaign、迭代、0.7 nm 和 NN/FTT 全部继续锁定。

## 10. 最终审阅意见

上轮两个确定的运行文件缺陷已得到足够具体的修复证据，应关闭，避免反复要求重算模型。本轮剩余工作集中在一个明确的 test-only 身份缺值漏判，以及一项尚未定位的 CPU1 绑定偏离。二者可以用已有脚本、少量临时文件和有限启动链取证处理，不需要扩大数值研究。

验收必须同时保留进展和限制：修复了文件保护，不等于严格资源门通过；组件判定有效，不等于完整科学端点有效；研究档案可保留，不等于生产合并获批。本次不放宽任何残差、extra 严格下降、选择接受或独立精度规则，也不将旧负结果改写为通过。

## 固定证据链接

源码行号均指固定被审提交。参考资料只用于说明 affinity 的接口语义，不用于推断本工作站的偏离原因。

[DIFF5]: https://github.com/Rookie1234567/MyFEniCS/compare/d1a005385bcaa736a2e2b9d0d411dca35a93868a...bc4563f6db55727c70ad8f6bf72475b559a8c914
[V4]: https://github.com/Rookie1234567/MyFEniCS/blob/d1a005385bcaa736a2e2b9d0d411dca35a93868a/docs/task43_hp_adaptivity/review_report_v4.md
[TASK]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/task.md
[RESPONSE5]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/response_v5.md
[VALIDATION5]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/outcomes/records/v5_focused_validation_v1.json
[RESOURCE5]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/outcomes/records/v5_root_resource_recheck.json
[H100]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/benchmarks/task43_hp_adaptivity/h100_anchor.py
[A2]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py
[FAIL_TEST]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/src/test/test_task43_v3_failure_safe_order.py
[NATIVE_TEST]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/src/test/test_task43_v3_native_workflow_ledger.py
[WATCHDOG]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/benchmarks/subreaper_watchdog.py
[ACTIVATION]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/scripts/activate_task40_phi90_pord64.sh
[OLD_AFFINITY]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/outcomes/records/v4_root_audit/A2_q3_affinity_intervals.json
[SUMMARY5]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST5]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[REGISTRY]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/development_model_registry.md
[PROGRESS]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/development_progress.md
[CLOSURE]: https://github.com/Rookie1234567/MyFEniCS/blob/bc4563f6db55727c70ad8f6bf72475b559a8c914/docs/task43_hp_adaptivity/outcomes/records/selective_merge_dependency_closure_v2.json
[LINUX_AFFINITY]: https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html
