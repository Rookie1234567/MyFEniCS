# Task43 正式审阅 V4：有限工程整改部分接受，继续禁止新增正式计算

审阅日期：2026-10-25。审阅对象为固定提交，不按分支未来内容追认资格。本报告只审查 Review V3 第 9 节 N1–N6 的落实；不重新签发旧 READY，不修改历史负结果或冻结判据。

## 1. 裁决先行

| 裁决维度 | 本轮决定 | 实际含义 |
|---|---|---|
| 有限整改验收 | **部分接受，仍需有限整改** | A1 真实 main 的 ledger 接线、A2 两条原后处理故障修复、extra 提前留证、watchdog 原因区分及旧日志算术都有实质进展；但 A1 拒绝非空输出根后仍可能改写旧记录，A2 原件路径/hash 也有确定错误。有限工程闭环尚不能给最终 pass |
| 下一轮工作 | **只允许第 10 节列明的无新 PDE 小范围修复和验收** | 不新建控制框架，不重跑整个研究，不为文案或保存路径修复重算 Maxwell |
| 新增正式计算授权 | **0；不批准** | A1/A2 q 重试、R、B/C、fresh baseline、成本 campaign、迭代、0.7 nm、NN/FTT 均不启动；最后一槽继续封存 |
| 生产合并资格 | **不批准，production merge gate = fail** | 本次不是整体或代码组的 merge approval；文档/轻量证据可作未来选择性迁移候选，仍需届时明确批准、用户授权和 Codex 执行 |
| 研究状态 | **PARTIAL / CONTROLLED_NEGATIVE 保持** | 工程保存与测试改善不改变独立空间精度未通过的事实 |

这里“ledger”是运行到哪一步的持久日志；“primary”是正常校正结束、额外校正前冻结的解；“extra”是使用同一已分解矩阵再校正一次的诊断状态。提前保存能减少后处理失败造成的证据损失，代价是文件写入和因子存活时间延长。它解决留证可靠性，不直接改善网格精度。[V3] · [PLAN3] · [CONTRACT3]

本轮最高优先问题是**拒绝重入时保护旧目录**，不是要求再次验证已知未达标的精度。第 10 节给出明确收口条件；满足这些条件后仍须提交回应并等待审阅，不能自动开始计算或合并。

## 2. 分支、提交及实际审阅范围

| 身份 | 独立核对结果 |
|---|---|
| 仓库 / 分支 | Rookie1234567/MyFEniCS / task43_hp_adaptivity |
| 固定被审提交 | 80f51ad2694acaa0a2494c01752e84023c03beca |
| 固定 Git tree | e3aac6a968ef47f3421e954a8564ee494114c585 |
| 直接父提交 / V3 review | 185ae91424c66780caa54a85e59eb3163cad3964 |
| 长期代码基线 | 405e3aff42ac421a4c99315df1ed9b96941ecbe4 |
| V3 review → 被审提交 | 1 个提交，18 个变更路径，其中 8 个 Python 文件 |
| 首次远端核验 | refs/heads/task43_hp_adaptivity 正好指向被审 SHA；没有后续提交 |
| 工作站工作树与 upstream | “干净、ahead/behind=0/0”是执行方交付陈述；本审阅没有访问该工作站 canonical worktree，不能独立确认本地状态 |
| 本 review 自身 SHA | 由新增本文件的 Git commit object 确定，交付消息提供完整 SHA；文件内不制造自引用 SHA |

已直接读取三层 AGENTS、仓库协作规则、Task43 任务书、既有诊断计划和冻结合同、V3 review、V4 response、全部 18 路径差异、相关源码/测试，以及指定的 validation、root index、完整 affinity 与生命周期轻量 JSON；并核对 README、summary、manifest、模型总账和进展。[DIFF] · [TASK] · [PLAN2] · [CONTRACT2] · [PLAN3] · [CONTRACT3] · [RESPONSE] · [VALIDATION]

审阅缓存中的 **186 个文件全部与固定 tree 的 Git blob 相符**，18 个变更路径均取得完整内容。对当前源码/文档和历史保护清单作 SHA256 交叉核对；既有 110 份 records 的 Git blob 未变，V1 保护清单中取得的 64 份文件实际重算 hash 一致。历史 review、合同、READY、正式失败记录没有出现在本次改动中。这个结论针对 Git 中的字节；它不证明工作站所有 ignored artifact 从未变化。

本次还执行了只涉及临时 JSON、最终函数 AST、hash/AST 和已提交数字的独立检查：复现 A1 拒绝非空根后的副作用、A2 后处理与二次写失败；重算 105 个 affinity 区间和 34 个生命周期切片；重构最后一次 noqa 改动前的完整源码字节。**没有启动 native runner、构网、装配、分解、求解、旧场重新采样或积分，也没有运行工作站 pytest。**

## 3. 按严重性排列的问题与验收条件

本节区分确定实现缺陷、资格边界与文案问题。没有把未访问的原件推定为错误，也没有把历史生产资格缺口算成本轮新引入的数值故障。

### V4-01 / P2：A1 拒绝非空 run root 后，失败处理仍改写旧 summary / endpoint

**定位：** h100_anchor.py 第 3265–3277 行拒绝非空输出根；第 4909–4942 行的外层 wrapper 在异常后仅检查 root 是目录，就调用失败写入器；第 2036–2111 行先原位降权限已有 solve/run_summary.json 和 task43_v2_a1_endpoint.json。第 2125–2128 行才检查旧 partial terminal，存在时返回其旧引用，不能保护此前已被改写的两个文件。[H100]

**根因：** failure context 在本次尚未成功建立/接管空输出目录之前，就保存了传入的 run_root。失败处理把“目录存在”当成“本次运行拥有该目录”。这使“refusing to overwrite nonempty output root”与实际副作用相矛盾。新 ledger 在空目录上的接线是正确的，但不会阻止这个更早发生的拒绝路径。

**本审阅实际复现：** 抽取固定源码中的真实 wrapper 和 demotion writer，使用临时 JSON、rank-0 MPI 替身、JSON writer/terminal factory 及模拟同一非空根拒绝的 callback。没有运行完整 main 或 PDE。对 HEAD 与父版本分别测了有/无旧 terminal 两种情形：

| 临时目录初态 | 拒绝后的实际结果 | 正确结果 |
|---|---|---|
| 已有 run_summary、endpoint；无 terminal | 原拒绝异常保留；两个旧 JSON hash 改变，并新增 partial terminal | 所有既有字节、文件集合不变 |
| 以上文件且已有旧 terminal | 原拒绝异常保留；旧 terminal hash 不变，但旧 summary/endpoint hash 改变 | 所有既有字节、文件集合不变 |

父版本也复现，故这是**本轮发现、此前已存在的保护缺陷**，不归因为 V4 新引入。现有合同要求正式 attempt root 事前不存在，旧 READY/额度也已耗尽；本报告不声称有合法 formal 绕过，更不声称真实历史原件已经被改坏。Git 历史保护检查仍成立。[CONTRACT3]

**最小修复：** 显式记录“本次成功取得空 run root 的写入资格”，仅此后才允许 wrapper 在该 root 中写失败记录。目录重入、身份/preflight 失败且尚未取得该资格时，只返回原异常/外层监督器日志，不进入旧 root 降权限。复用已有 context 即可，不新建状态平台。

**验收：** 在现有真实-main fixture 中增加“有旧 terminal / 无旧 terminal”两个临时非空根用例，核对拒绝前后整个目录的文件集合和逐文件 hash 完全相同，mesh/assembly/solver 均为 0；同时保留“本次空 root → mesh-boundary sentinel → 可读 failed ledger/terminal”的正例。不得用真实历史 attempt 目录做测试。这是有限工程闭环和任何未来 A1 入口复用前的必须修复项。

### V4-02 / P2（资格边界）：二次持久化失败不能被概括成磁盘上所有成功字段必然关闭

**定位：** A2 adapter 第 203–289 行，candidate_checkpoints.py 第 311–384 行；已有两条 fixture 在 failure-safe test 第 564–700 行附近。[A2] · [CHECKPOINTS] · [FAILTEST]

原子写入保证一份文件的替换完整，但 summary、comparison、partial terminal 三份文件并非一个原子事务。本次纯文件故障注入确认：

| 回调失败后额外发生的故障 | comparison | summary | partial terminal |
|---|---|---|---|
| 无二次写故障；comparison 已写后回调失败 | 降权限 | FAILED / passed=false | 可读、非 official |
| 无二次写故障；summary 截断后回调失败 | 降权限 | 从缓存恢复为 FAILED / false | 可读、非 official |
| comparison sidecar 写失败，或 comparison 降权限写失败 | **可残留旧 endpoint_qualified=true** | FAILED / false | 可读、非 official |
| summary 降权限写失败 | 降权限 | **可残留旧 passed=true** | 可读、非 official |
| partial terminal 写失败 | 降权限 | FAILED / false | 未生成；错误被记录 |

上述复现均保留原回调 OSError，primary 字节未变。既有 A2_R reader 第 1900–1942 行读取的是冻结 V2 的 A2_q_attempt1/run，展示了可复用的 summary、comparison 身份/hash 和原始硬门联合规则；它不是 V3 attempt3 的现实自动消费者，不能充作本轮 V3 二次写失败已经验过的现场防线。V3 本身在第 2597–2603 行固定 R continuation=false，且本 review 继续禁止下游。因此**没有证据证明发生自动续算或现有正式数值结论被翻转**，也不能把当前锁定状态夸大成任意组合写盘失败都已通过资格验收。

Response V4 第 12、31 行的关闭陈述具体对应那两条已测回调场景，本报告接受这两条修复；仍应补清二次持久化边界。文件系统整体不可写时，不要求程序保证写出不可能写出的终态。

**最小收口与验收：** 在本轮现存消费路径或明确的联合读取约定内，以有限文件 fixture 展示“单份 true 不授予资格”；明确失败 terminal、失败进程终态、任何降权限、缺失/不匹配绑定均否决端点，不能只读一个 PASS 字段。若当前 V3 尚无自动消费端，以纯文件联合判定 fixture 和文案收口，不为此新建、启用或扩展被锁定的 A2_R 路径。若已有实际消费路径缺少失败终态否决，只在该入口补齐。保留原异常、警告和旧测量；不引入新控制框架，不做 PDE。本项是资格范围与读取规则的收口，不要求重写原已通过的两个用例为失败。

### V4-03 / P3：降权限 comparison 的 original_record_path 与 original_record_sha256 不对应

**定位：** A2 adapter 第 100–114 行正确保存旧字节 sidecar；第 131 行却写 original_record_path=str(comparison_path)，第 132 行仍配旧 hash；第 164 行又用降权限内容覆盖 comparison_path。[A2]

本次两个原故障用例均复现：沿当前 comparison 的 original_record_path 读取，得到新内容，hash 与声明的旧 hash 不同。正确旧字节仍在 comparison_record.json.pre_failure.<旧SHA256>.json，返回 reference 和 terminal 也有正确 sidecar 引用，因此**不是原件丢失或数值篡改**，而是原件追溯字段自相矛盾。

**最小修复：** original_record_path 指向已成功保存的 sidecar；若需记录原当前路径，使用含义不同的字段。现有两条测试各增加以下检查即可：

    original_path = Path(current_comparison["original_record_path"])
    assert original_path.read_bytes() == original_comparison_bytes
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == current_comparison["original_record_sha256"]

同时保持 primary hash、测量字段、原异常和所有权限断言。无需追加模型尝试。

### V4-04 / P3：空 cmdline 尾段是三段，不能笼统写成两段

**定位：** response_v4.md 第 18、34 行及 development_model_registry.md 第 11 行；完整 affinity JSON 的 intervals[102:105]。[RESPONSE] · [REGISTRY] · [AFFINITY]

| 区间索引 | PID / start_ticks | 缺失样本 | 当前分类 / 能关联什么 |
|---|---|---:|---|
| 102 | 2194643 / 276351410 | 9 | other_or_unknown；同身份前序为 launch shell / native numerical worker |
| 103 | 2342976 / 277069482 | 9 | other_or_unknown；同身份前序为 compiler toolchain |
| 104 | 2194694 / 276352117 | 8 | MPI_runtime，comm=orted；cmdline 同样为空 |

实际共 3 段、26 条进程成员观察，其中只有前两段归入 other_or_unknown。可改成“两条 other_or_unknown 尾段，另有一条 MPI runtime 的空命令尾段”，或直接写“三段”。这不改变 5,959 条可读数值 worker 样本均为 CPU1 的结论。修正文案和当前总账即可，保留原 JSON；不补造缺失命令。

### 持续阻塞，非本轮新增实现错误

| 项目 | 保持的边界 |
|---|---|
| 完整科学端点 | A1_q2 无完成求解/primary；A2_q3 不完整、extra 严格下降失败；独立精度未通过 |
| 生产与 ABI | 全仓 collection/SLEPc/complex PETSc ABI blocker 未关闭；本轮没有 full repository pytest 或完整 p6 FFCx witness |
| 原件可访问性 | 工作站 ignored 原始日志、资源流、NPZ 等未取得；不能将执行方记录的原件核验写成本次亲自复核 |
| 合并证据身份 | 旧 Stage1 overlay 只有 59/66 路径、23/27 核心/共享路径与当前字节相同；不能覆盖全部最终共享文件 |

这些阻塞不会通过修好 V4-01 或增加几个 fixture 自动消失。[V3] · [CLOSEOUT3] · [MANIFEST] · [CLOSURE]

## 4. 对 V3-01–V3-08 的逐项回答

“通过”只针对该行明确写出的工程/陈述范围，不授予科学端点或生产资格。

| V3 问题 | V4 验收 | 直接依据与未关闭范围 |
|---|---|---|
| V3-01：A1 实际入口漏接 ledger、错误 READY | **部分通过** | 真实 main → _run_impl → WorkflowLedger → 首次 mesh builder 的接线已成立；缺 phase/错父身份提前拒绝；失败 stage/terminal 有测试。旧 A1_q2 已构网并进入装配、主控错误放行后停止的责任明确保留。但新发现的 V4-01 旧目录保护缺陷必须修 |
| V3-02：primary partial、extra 负门、完整端点缺失 | **对结论保留通过；数值资格仍未通过** | V4 无新端点；没有把 primary q 稳定性称为空间精度，没有把 extra 严格下降失败回写为 pass |
| V3-03：最终共享文件 production qualification | **对诚实披露通过；生产门未通过** | manifest 明列 59/66、23/27 和四个变化共享文件；未用 focused/旧 overlay 替代最终全仓资格 |
| V3-04：A2 后处理权限不一致 | **部分通过** | 缓存 summary、原子写和原字节 sidecar 修好两条原复现；V4-03 的路径错误及 V4-02 的二次写失败范围仍需收口 |
| V3-05：extra 保存太晚 | **通过，限组件与源码顺序** | 原向量包确在必要代数恢复/A6/full-active 后、物理输出/采样前；测试读取 NPZ 重算 norm；不补造历史 A2_q3 extra 原件 |
| V3-06：watchdog 清理原因误归属 | **通过，限组件** | 原因区分覆盖后代残留与 cache 未稳定，清理限额/最终 reap 未放宽；旧 LIMITED 不改判 |
| V3-07：CPU affinity 角色混合 | **部分通过** | 完整区间表将监督器、shell、worker、compiler、MPI 分开，内部算术一致；三段空 cmdline 文案须更正，raw resources 未在本环境复核 |
| V3-08：旧状态段落误作当前 | **主要通过；小范围文案收口** | 当前 5/6 与封存状态一致；原 4/6、A2 未 READY 段明确标历史时点；V4-04 与二次持久化边界应进入下一版说明 |

对应材料分别为源码、测试和 records，不以 response 中的“完成”替代判断。[H100] · [NATIVETEST] · [A2] · [P6] · [FAILTEST] · [WATCHDOG] · [WATCHTEST] · [AFFINITY] · [SUMMARY] · [MANIFEST]

## 5. N1–N4 的代码、测试与现场边界

### 5.1 N1：真实 main 的 sentinel 足够验证接线，不能验证求解

h100_anchor.py 第 3282–3293 行在首次 mesh 前创建 WorkflowLedger，写入 phase、watchdog 父身份与后续输入/源码身份；第 3480 行的复核允许本次 ledger 已创建的 phase 文件。异常 wrapper 保存 previous_stage、exception_type/message 和 terminal 引用。[H100]

native workflow test 第 202–275 行实际调用 h100_anchor.main，以 frozen candidate 输入进入原入口，只替换首次 build_airbox_mesh_3d 为 sentinel，并替换 solver 为“一旦调用即失败”的检查。测试验证 builder 边界调用一次、无真实网格目录、无 solver 调用、phase/stages 末项失败、terminal hash 可读且 continuation 全 false。第 278–299 行为 missing phase / wrong parent 两个负测，目前只断言 exit 2 和 run directory 未创建；没有断言具体拒绝原因，孤立看不能排除更早的冻结输入校验先失败。源码与正例共同支持当前接线判断，F1 应顺手补具体报错断言，不增加实验种类。[NATIVETEST]

这比只测通用 WorkflowLedger 更接近真实启动链，足以接受 N1 的接线修复。测试仍使用临时输出目录和被替换的 mesh builder，依赖工作站 ignored frozen candidate 输入；缺输入会 skip。它不验证真实构网、装配、MUMPS、primary 或完整现场资源门，也不能覆盖 V4-01 的非空根路径。旧 A1_q2 的 G2 失败和主控责任仍成立。

### 5.2 N2：两种原错误确已修复，测量与授权分开保留

adapter 第 184–187 行在回调前深拷贝有效 summary；后续坏 JSON 不再覆盖原回调异常。V3 后处理 writer 在第 2547–2554、2578、2605、2626 行使用已有原子 JSON helper。comparison 降权限保留测量字段，summary 将原 official 测量内容迁入明确非权威字段。[A2] · [CHECKPOINTS]

本次独立纯文件复现和 tracked fixture 的断言一致：comparison 成功写出后异常、summary 截断后异常，都能保存可读失败终态，保留原 OSError、原 comparison sidecar、primary 字节及测量值。合成值 R_total=0.25000001 和 max_power_delta=2.5e-8 是 fixture 数据，不能列入物理模型结果。V4-02/03 说明剩余边界。[FAILTEST] · [VALIDATION]

### 5.3 N3：extra 包保存时机与实际字段正确，测试是小数组证据

P6 runner 第 4404–4495 行完成一次额外同因子校正、凝聚残差、独立 A6、full-active 检查及必要代数恢复；第 4496–4622 行保存 extra NPZ；第 4623 行之后才创建 extra field，随后做物理输出和采样。[P6]

包中分开保存 recovered storage、condensed solution、condensed b−Ax/RHS、独立 A6 residual/effective RHS、zero-slave carrier residual 和 port residual；绑定 primary 包 path/hash、source/contract/plan、primary/extra 两侧 RHS 及 factor/correction 计数。相同 RHS 用数组相等检查；严格下降判据仍按原 before/after 的 residual norm 和相对值，未改成“低于硬阈值即可”。新逻辑受 V3 opt-in 控制，没有为留证增加一次 factor 或 solve。[P6] · [CHECKPOINTS]

测试的精确含义：

| 测试方式 | 能支持 | 不能支持 |
|---|---|---|
| 源码顺序检查 | early packet 位于恢复/采样风险点之前，失败分支带其引用 | 不是完整 native 运行 |
| 小数组 writer + 恢复/transport 异常 | 已保存 primary/extra 字节不丢，原数据/计数/负门保留 | transport 用例是单 rank bcast 成功后人为抛错，不是多 rank 故障资格 |
| q10 callback 故障 | q8 已保存而 q10 未完成时，q8/primary/extra 仍可读取，权限关闭 | 不是新的物理采样或旧 A2 extra 补算 |
| 从 NPZ 重算指标 | norm(r_condensed)/norm(b_condensed)、norm(r_A6)/norm(b_native)、carrier/port 合成范数比与保存 scalar 一致 | 不是独立重新装配算子后计算 A×x−b，更不是空间精度核验 |

因此 N3 可以按 V3 授权的有限组件要求接受，无需为了本轮留证修复重开正式模型。A2_q3 历史缺少 extra 原向量与完整 extra q8/q10 样本的事实不变。[FAILTEST] · [A2RAW3]

### 5.4 N4：分类修复没有放宽清理

watchdog 新增 _stop_clearance_timeout_message：有后代时报告 descendants 未清除；无后代但 leader 未退出时单列 leader；两者已清除/退出而 cache 未稳定时报告 cache。正常生产额外清理余量仍为 10 秒，信号、末尾 reap 和最终清理结构保留。[WATCHDOG]

test_354 第 140–230 行使用真实小子进程；为触发分支，在测试内部缩短触发间隔、延迟部分 child 信号，达到目标后恢复原清理余量。它检查 stop reason、leader exit、SIGTERM/SIGKILL 记录次序、resources 末行、remaining PIDs 和观察到的 PID 消失。故障注入期间的 first_SIGTERM/first_SIGKILL 是 signal helper 调用记录，不能证明当时已经实际递送；达到目标分支后恢复真实递送，最终核对 PID 消失。cache 分支允许此前合法信号，要求末行无后代、exit=0；这不是放松清理，而是避免把“无后代”误等同于“从未发过信号”。[WATCHTEST]

本审阅没有重跑这些工作站子进程测试；所述 pass/失败来自绑定版本的 compact，源码与测试逻辑已直接核对。原早期 EVIDENCE_INCOMPLETE 和各次失败重跑保留，旧 A2 的 LIMITED_NOT_UNCONDITIONAL_PASS 不因新实现而改判。[VALIDATION] · [A2TERM3]

## 6. N5：旧 A2 affinity 与生命周期费用

### 6.1 CPU 结论限于采样角色，不等于连续运行轨迹

完整表有 **105 个区间、44 个不同 PID/start_ticks 身份、18,343 条进程成员观察**。本审阅逐区间重算命令文本 hash、样本数量/跨度、角色合计和身份相邻范围。角色数为 supervisor 5,971、launch_shell 2、ABI_helper 2、MPI_runtime 5,965、native_numerical_worker 5,959、compiler 426、other_or_unknown 18，合计一致。[AFFINITY]

5,959 条可读 native worker 样本对应 resources 第 3–5961 行、elapsed 约 2.580–7200.711 秒，记录 affinity=[1]；宽 affinity 区间只出现在 supervisor 和起始 shell。shell 与随后 exec 的 worker 可有相同 PID/start_ticks，必须同时看命令和时段，不能只按 PID 标签判断。

空命令尾段只能按同身份前序关联，见 V4-04。affinity 表示进程可运行的 CPU 集合，不单独证明实际 CPU 利用率、数学库线程数、MPI rank 数或所有采样间隙。由于原 5,971 行 resources 不可访问，本次验证是已提交区间表的内部一致性及与既有轻量摘录的交叉核对，**不是从原资源流独立重建所有区间**。

### 6.2 生命周期账算术闭合，但窗口不能重复相加

已直接读完 lifecycle JSON，重算全部 **34 个相邻且不重叠的切片**；起终点连续，样本数合计 5,971，时长之和为 **7213.133929461241 秒**，与 whole-watchdog 一致。表中 9 个操作窗口明确标 nonadditive；它们是这些切片的另一种归并，不能再加一遍。[LIFECYCLE]

| 阶段或窗口 | 秒 | 解释 |
|---|---:|---|
| watchdog 启动至首个 workflow marker | 8.352000 | 包含在总数内 |
| watchdog 启动至 volume assembly 起点 | 437.557661 | 包含上一行、mesh、surface/编译等；两行不能相加 |
| volume assembly 窗口 | 4772.249342 | 内部 assembly timer 为 4771.323931；两者重叠 |
| matrix 完成至 action-view / RHS ready | 47.753565 | 已计入切片，不能漏作“无 solver 费用” |
| symbolic 窗口 | 19.256474 | 含 marker 间准备 |
| numeric factorization 窗口 | 1162.840823 | 分解费用，不是 solve-only |
| 初始求解、正常 correction 和 residual 工作 | 66.523617 | 未分别测初始 MatSolve 和 correction MatSolve |
| primary 恢复与 A6 / primary 包写入 | 154.398587 / 2.422611 | 两个相邻窗口，均已含于总账 |
| primary 物理输出与 q8 / q10 | 179.032975 / 156.601405 | modal、Av、q8 没有各自独立计时 |
| extra correction 与独立 residual 工作 | 137.226384 | 不是一次孤立 MatSolve timer |
| 最后 extra marker 至触发停止 | 64.838913 | 未完成且无细分完成标记，不能全部归给某个 witness/采样器 |
| 触发停止至终态清理 | 12.420494 | 属完整 watchdog 生命周期，不是额外获准计算时间 |

上表用于解释主要窗口，**完整求和以 JSON 的 34 个切片为准**，其中还保留毫秒级 marker 过渡。solve_started 写在正常 correction 之后；它到 solve_complete 的 0.002223 秒不能当成求解耗时。资源 epoch 与 monotonic 对齐有约 0.008041 秒的 origin spread；因此切片是日志边界推导值，不是每个底层函数的精确独立计时。[LIFECYCLE] · [P6]

峰值 27,098,828,800 字节是记录中同时进程树 RSS 的最大采样值；不能相加各阶段峰值，也不能仅凭这些数据分离 factor 分配。原 stop、缺完整 endpoint、cache-stability 异常和 LIMITED 均保留。没有证据据此给出同精度加速、cold-cache 优势或完整研究成本。

## 7. 测试、最终源码身份与支持成本

### 7.1 测试必须按阶段解释

| 记录阶段 | 执行方保存的结果 | 本审阅可以独立确认 / 限制 |
|---|---|---|
| final focused attempt1 | 36 passed、2 failed | 最终测试选择器静态展开为 38 个案例；两个失败及 fixture 原因保留。不是“38 全过” |
| 两个失败节点修正后 | 2 passed | 两个 selector 可在最终测试文件定位；该次原日志及运行时文件快照未取得，不能与前项拼成一次最终同字节全套运行 |
| 后续受影响节点补验 | 9 passed | 五个选择器展开为 9 个案例；source hashes 可核 |
| 最后一处 noqa 移除 | 未再跑功能测试 | 本审阅从最终 adapter 第 193 行加回该注释，重构字节 SHA256 恰为 30a688b6…；最终为 1ce7f246…，去位置属性 AST 完全相同。可接受为注释等价，不伪称同字节重跑 |
| V4 scoped Ruff | 当前 21、基线 21、新增 0；exit 1 | 只覆盖 8 个改动 Python 文件；未取得 ignored Ruff 原始输出，不称全绿 |
| compileall / 文档静态 | 8 Python、32 links、4 JSON、历史保护检查报告通过 | 最终源码可解析、相关 JSON/hash 已在本审阅核对；工作站完整检查日志未取得 |
| V3 57 passed/1 skipped、后续 1 passed | 历史不同 HEAD | compact 已标 81c97e7c… / fc260b1e…；不覆盖 V4 最终新增路径 |
| full repository pytest / 完整 p6 FFCx witness | 本轮未运行 | 既有 collection/ABI blocker 与 production qualification 缺口保持；不能称全仓或 CI 通过 |

相关结果均见逐次命令、source/test hash 和 watchdog 引用。[VALIDATION] 本审阅核对了 8 个改动 Python 文件及 6 个文档最终 SHA256 与当前 Git 字节一致，也核对注释等价；**这些 hash 核对不能替代读取 pytest stdout 或亲自重跑测试**。

此次测试足以支持不少有限工程判断，仍漏掉 V4-01 非空根负路径和 V4-03 当前 comparison 自身原件路径的断言。这是针对具体风险的小补验需求，不构成再次跑全仓/重建环境的理由。

### 7.2 去重后的支持费用

| 组 | 唯一 watchdog 驱动数 | whole-wall 秒 |
|---|---:|---:|
| executor 组件与失败重跑 | 8 | 209.23098790319636 |
| 两次旧 A2 日志只读审计 | 2 | 8.707812543958426 |
| final static / recheck / finish | 3 | 26.33053978951648 |
| 合计 | **13** | **244.26934023667127** |

9 项补验的 final_static_recheck 同时被 test_runs 和 static driver 列表引用，本审阅按同一 watchdog summary 路径/hash 去重，只计一次。13 份 compact 中最长单次 80.1084968992509 秒，最高树 RSS 342,376,448 字节，swap=0；就这些已列数值而言，均低于 300 秒/8 GiB，累计低于 1800 秒。[VALIDATION] · [ROOTINDEX]

一次在 watchdog/pytest 前失败的支持 precheck 明记 not_measured，未监控的文件/hash/Markdown 检查也未计入；不能把 244.269 秒写成包括所有活动的完整成本。失败 driver 和针对性重跑没有从费用中删去。这里是对 compact 的算术复核，原资源流/退出码/清理现场仍未独立复核；亦不能仅凭这份账证明工作站绝无未列活动。

本轮源码与轻量清单没有显示新的 formal attempt、dispatch 或 READY；按其证据范围接受新增为 0，历史仍是 5/6。支持测试中的“attempt1/2”是测试驱动标签，不能倒扣历史正式尝试，也不能混入正式模型数。

## 8. 原件缺口、科学结论与五项能力

### 8.1 需要工作站补核的具体原件

| 原件范围 | 具体路径 / 身份入口 | 本次没有独立核实什么 |
|---|---|---|
| 旧 A2 全生命周期原始流 | benchmarks/artifacts/task43/v3_diagnostics/A2_q_attempt3/watchdog/summary.json、resources.jsonl；run/stages.jsonl | 原始逐行 CPU/命令、停止信号、RSS、采样完整性和时钟映射。compact 所列 hash 分别以 5b15cbe6…、c80cf7e4…、3283b938… 开头 |
| N5 派生脚本及两次运行日志 | benchmarks/artifacts/task43/v4_root_audit/read_old_a2_timeline.py；old_a2_logs_watchdog/、old_a2_logs_watchdog_refined/ 下 summary/resources/worker logs | 脚本字节与原流到派生表的完整生成过程；脚本声明 SHA256 5587f5ab… |
| V4 支持测试原日志、ABI、fixture 包 | validation 中逐项列出的 benchmarks/artifacts/task43/v4_support/ 各 driver；保存的 pytest fixture 目录 | 原 pytest 运行结果、真实 native ABI、父子进程与文件保存现场 |
| 三次最终静态驱动原件 | benchmarks/artifacts/task43/v4_root_audit/final_static/、final_static_recheck/、final_static_finish/ | Ruff 逐项输出、launch_record、完整 stdout。最后 noqa 等价已可由 Git 字节独立重构，不必为此重跑 |
| A2 primary 原向量/全场样本 | A2_q_attempt3/run/numerical_output/ 中由 A2_q3_primary_raw_audit.json 列明的 NPZ | 本审阅不能重新做原向量/物理场独立算术复核；这里只核读既有轻量审计 |
| “104 项 hash 一致”最终主控清单 | 用户交付所述清单及其原始输出；当前 tracked validation/root index 未给出可逐项对应的 104 项完整列表 | 不将该陈述变成本审阅“亲自核对 104 原件”。143 个 hash 字段或 109 个唯一 digest 也不能替代该清单 |

上述原件 hash 是定位和内容身份约束，不是已经访问原件的证明。若需补证，只提供/核对已有清单及与本轮整改相关的最小原件；缺失则明确未独立核验，不重算 PDE、不重采样、不重积分，不启动全盘恢复。历史 A2 extra 原向量与完整 extra 样本本来未保存，**不能通过本轮新 fixture 或新 hash 追溯补造**。[ROOTINDEX] · [VALIDATION] · [A2RAW3]

### 8.2 科学边界保持

本轮没有增加 FE 空间或选择步骤。R9 的 110,472 独立 FE 仍低于控制 237,600，约少 53.5%，但该自由度节省与独立精度通过是两个条件，后者未满足。R10 仍是被拒绝的候选，无第十次接受；与某一 6×10×6 控制的有限接近不能反向授予 holdout 通过，也不能反馈选择器。[SUMMARY] · [TASK]

旧 A2_q3 的 primary 仅支持有限同空间 q 扰动与代数稳定性观察。其 380,160 独立 FE 是 389,832 carrier 行减去 9,672 约束行；求解矩阵 121,572 行包含 trace/port 口径，不能用矩阵行数冒充独立 FE，亦不满足候选 FE<237,600 的目标。它本来就是诊断参考路线。[CLOSEOUT3] · [A2RAW3]

extra full-active 相对残差由 1.1972486317982494e−11 增至 1.2068417985488609e−11，未严格下降。虽都低于 1e−8 硬阈值，冻结的严格下降门仍失败；本轮代码保留该逻辑。不能据小幅增量倒改旧规则，也不能仅凭这项失败断言所有 h/p 方法无效。7200 秒停止、whole-watchdog 7213.133929461241 秒包含清理、无完整 native summary/comparison 和 LIMITED 清理边界均不变。[V3] · [CLOSEOUT3] · [CONTRACT3]

| 能力 | V4 后状态 | 结论范围 |
|---|---|---|
| 空间 | PARTIAL | 已有 mixed-p / 一层局部 h 基础；本轮没有新网格资格，不外推一般多层 h |
| 选择 | PARTIAL | accepted9/R9 和 R10 拒绝链保持；本轮未新增接受更新 |
| 精度 | NOT_PASSED | 仍缺满足冻结标准的独立精度核验；q 稳定性、低代数残差、组件 pass 均不能替代 |
| 同精度全过程成本 | NOT_ESTABLISHED | 精度前提未过；正式失败、支持费、旧采样、重建和不完整窗口不能拼成加速结论 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 本轮无接线或验证，不由 direct/observer 测试继承 |

旧 Y6 automatic Av 配置、operator q19、incident/port q32 的角色仍按冻结合同分开。本次没有新 Av 积分或 sidewall 资格；也不借本轮工程修复改变 R8 不完整费用窗口等既有历史限制。[CONTRACT2] · [CONTRACT3] · [SUMMARY]

## 9. 选择性合并与架构裁决

本轮没有新增数值算法：主要是既有诊断入口的运行日志、失败权限和原向量写入顺序。新增 A1 WorkflowLedger 导入来自既有 src/runners/physical_intermediate.py；A2/p6 使用的新增 writer 来自同组 candidate_checkpoints.py。直接检查没有发现本轮新增且漏列的文件依赖。task-numbered adapter 和 runner 仍是研究接线，不能因位置在 src/ 或通过组件测试而成为 production default。[DIFF] · [MANIFEST]

旧 66-file 依赖集合仍有 59 项同字节；27 个核心/共享文件中 23 项同字节。四个不同的共享文件是 common_3d_case_flow.py、dtn_port_3d.py、hcurl_variable_p_reduction.py、solve_maxwell_3d_stage_4b_block_grating.py。本轮没有改这四项，但 V1/Stage1 旧证据不能代替当前最终版本的资格。新的 p6 diagnostic 路径也不在旧 overlay 的全部资格范围内。[CLOSURE] · [MANIFEST]

| 依赖组 | 具体文件 / 必需依赖 | 当前证据 | 合并决定与阻塞 |
|---|---|---|---|
| 文档与轻量证据 | 本 review、response_v4.md、README、summary、manifest、development_model_registry.md、development_progress.md；validation JSON、root index、affinity/lifecycle JSON及其引用的历史轻量记录 | 固定 Git 内容、历史保护、区间/费用算术 | 可作为未来 docs-only 选择性迁移候选；需先修正文案、明确缺原件范围；**本次不授予实际合并许可** |
| 可复用 watchdog | benchmarks/subreaper_watchdog.py + src/test/test_354_subreaper_watchdog.py；其现有 native-capacity/profile 与 WorkflowLedger 测试依赖 | 原因函数与真实小子进程 fixture，资源上限/清理结构不变 | 最接近可独立迁移的代码组，但须在目标 clean base 上验证实际依赖与相关非 PDE 测试；现阶段不批准代码合并 |
| A1 ledger / failure wrapper | h100_anchor.py + native-workflow/failure-safe tests + candidate_checkpoints.py + 既有 WorkflowLedger；同时依赖其原数值调用链 | 真实 main mesh 前 sentinel | Research-only；**V4-01 阻塞**；修好仍无真实 A1 endpoint / production 资格 |
| A2 后处理 / extra packet | a2_native_p6_diagnostic.py、candidate_checkpoints.py、src/runners/p6_condensed_direct.py + failure-safe/native-ledger tests；与现有 A2 helper、native core、冻结输入同组 | 两故障路径、小数组、源码保存顺序 | Research-only；V4-02/03 收口；组件证据不覆盖最终完整 native 数值/ABI 路径 |
| 原 Task43 数值核心 / 共享行为 | 既有 manifest 的 src/adaptivity、约束、variable-p、凝聚和公共 solver 依赖组，特别是上述四个共享文件 | V1 与 Stage1 的限定历史证据；本轮未重新数值资格化 | 不从本轮得到新的 production approval；未来须按拟迁移字节/目标基线选择最小闭包并另审 |
| 禁止直接迁移为 production | 未资格化研究入口默认化、旧 READY 作为启动许可、失败场作为 official、全部 research branch 整体 merge | 没有可支持的资格 | Do-not-merge；ignored 大原件保持原位置，只提交轻量引用 |

若未来有 docs/watchdog 的单独选择性批准，仍必须经过用户授权并由 Codex 执行；本次不创建合并、不向 master 写入，也不借此报告触发 production qualification campaign。

## 10. 下一轮唯一允许的工作：有限非 PDE 收口

**新增正式 PDE / dispatch / attempt / READY 均为 0。** 下面只授权小型工程修复和验证。不得把第 11 节的未来条件当成已有计算许可。

| 顺序 | 允许修改 | 最小可执行验收 |
|---|---|---|
| F1 | 修 V4-01：A1 只对本次取得写入资格的空 root 写失败终态 | 在临时目录经真实 main 验证有/无旧 terminal 两种拒绝；旧文件集合和逐文件 hash 不变；mesh/solver=0。保留空 root sentinel 正例；missing phase/wrong parent 还须断言对应拒绝消息，不能仅凭 exit 2 通过 |
| F2 | 修 V4-03：comparison 原件路径/hash 一致 | 原两 N2 用例增加原件路径字节与 hash 断言，测量/primary/原异常/权限断言保持；只改单点实现与相关测试 |
| F3 | 收口 V4-02：二次写失败范围与联合读取规则 | 用临时小文件覆盖 comparison/sidecar 和 summary 降权限失败，保留原异常；在现存消费路径或联合读取约定内证明单份 true 不授予资格。当前 V3 无自动消费端则以纯文件 fixture/文案收口；不得为此启用或扩展 A2_R，不开发新 controller |
| F4 | 修 V4-04，更新当前回应/summary/manifest/总账/进展 | 明确三段空 cmdline；逐项写 F1–F3 范围、测试对应字节、未核原件及状态。104 清单若已有则提供最小索引/原日志；没有就保持未独立核验，不重跑一套大审计 |

执行约束：

1. 保持同一 task43_hp_adaptivity 分支，读取本 review 后修改。不得覆盖本 review、旧 review、冻结合同、READY、失败记录或旧 attempt artifact；本轮修复不追溯改变历史分类。
2. 用现有资格化 activation、CPU1/MPI1/单线程，只运行上述受影响的纯文件、sentinel 和必要小子进程节点；真实模型 mesh builder 必须先被 sentinel 拦截。不得以“组件测试”命名运行模型。
3. 下一轮每个受监控 driver 最多 300 秒，**本次新收口的累计 whole-watchdog 上限 600 秒**，树 RSS≤8 GiB、task swap=0，并遵守现有更严格可用内存门。600 秒仅用于上述少量非 PDE 测试：参考本轮最慢小 driver 80.108 秒、最后 9 节点约 16.788 秒 whole-wall，留有限失败定位余量；不是新增模型预算。
4. 先最小节点，之后最多一次相应 focused 收口；仅对已定位并修正的问题重跑相关节点，失败及重跑同账。触顶、需构网/因子/求解才可继续、或出现未知 ABI 依赖时停止记录，不换名续跑。
5. 不运行 full repository pytest、完整 p6 FFCx witness、重采样/积分、旧模型 replay、环境重建或性能 campaign 来处理这些问题。静态检查只覆盖改动文件；保留 Ruff 非零/历史诊断的真实边界。
6. 使用新的 support 目录或 pytest 临时目录，原历史 attempt 只读。保存命令、source/test hash、测试输出、运行终态、失败/重跑、whole-wall、RSS/swap 与清理结论；新 fixture 的合成数据明确标识。
7. 以最小代码/测试、response_v5.md 和轻量验证记录收口，提交推送同一分支后停止等待审阅。对未运行/未核验项如实标记，不拼接不同阶段的通过数。

F1–F4 是闭环范围；不要求重新设计 h/p 方法，也不要求另建一套冻结合同来修复文件保存和文案。完成这些动作仍不签发新的 READY。

## 11. 正式配额与后续路线：全部维持锁定

| 额度 / 路线 | 本 review 后状态 | 未来必须另行满足的条件 |
|---|---|---|
| 历史总额度 | 5/6 已用；A1 2/2、A2 3/3；剩余 1 封存 | 本 review 不重分配、不扩大任何组/总上限 |
| A1_q / A2_q 重试 | **不允许** | F1–F4 相关问题关闭；提出尚待区分的科学问题、为何旧 partial 不足、完整预计生命周期和端点证据；另行获得明确授权 |
| A1_R | **锁定** | 完整可信 A1_q 及所需硬门/基线/资源证据，R 诊断科学必要性和新授权 |
| A2_R | **锁定** | 完整可信 A2_q、extra 与失败语义处理、完整端点证据，以及新授权；primary partial 不代替 |
| B / C | **锁定** | 原计划各自的 A/R、同核/空间身份、候选及独立参考前提分别满足，另行逐项批准；任一 q 成功不自动解锁 |
| 同精度全过程成本 campaign | **锁定** | 独立精度通过、候选 FE<237600、控制角色隔离、同一成本口径覆盖完整生命周期，再另审 |
| 迭代接线 | **锁定** | 前置空间/精度资格及具体迭代方案另审；不由 direct 组件测试继承 |
| fresh baseline、0.7 nm、NN/FTT、参数盲扫、新控制框架 | **禁止启动** | 不在本轮范围，不因修复完成或总额度尚有 1 槽而自动许可 |

本报告**不建议现在新增正式计算**，因此不指定任何新模型命令、attempt 目录或可执行槽位。若将来申请，必须在运行前明确分支/attempt、组与总额度调整、共同/分支 Gate、冻结输入 hash、唯一输出目录、CPU/MPI/线程/ABI、RSS/swap/墙钟上限、失败即停止/不自动重试和必须保存的 primary/extra/完整端点证据，并获得新的明确授权。

任何残差容差、严格下降或接受规则调整都必须解释理由、前瞻生效。不得将 R9、R10、A1/A2 历史失败、extra 负门或 LIMITED 清理状态重写为通过。当前可接受的科学结项仍是部分空间/选择能力与独立精度未达；本轮有价值的成果是改善运行可追溯性，同时发现并限定剩余工程问题。

## 固定证据链接

以下链接均固定到被审 SHA；V3 review 使用其正式提交。代码行号均指被审版本。工作站 ignored 路径只作为索引，不表示本审阅已访问原件。

[DIFF]: https://github.com/Rookie1234567/MyFEniCS/compare/185ae91424c66780caa54a85e59eb3163cad3964...80f51ad2694acaa0a2494c01752e84023c03beca
[V3]: https://github.com/Rookie1234567/MyFEniCS/blob/185ae91424c66780caa54a85e59eb3163cad3964/docs/task43_hp_adaptivity/review_report_v3.md
[TASK]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/task.md
[PLAN2]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/diagnostic_plan_v2.md
[CONTRACT2]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json
[PLAN3]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/diagnostic_plan_v3.md
[CONTRACT3]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json
[RESPONSE]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/response_v4.md
[VALIDATION]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v4_focused_validation_v1.json
[ROOTINDEX]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v4_root_audit/index.json
[AFFINITY]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v4_root_audit/A2_q3_affinity_intervals.json
[LIFECYCLE]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v4_root_audit/A2_q3_lifecycle_cost.json
[H100]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/benchmarks/task43_hp_adaptivity/h100_anchor.py
[A2]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py
[CHECKPOINTS]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/benchmarks/task43_hp_adaptivity/candidate_checkpoints.py
[P6]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/src/runners/p6_condensed_direct.py
[FAILTEST]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/src/test/test_task43_v3_failure_safe_order.py
[NATIVETEST]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/src/test/test_task43_v3_native_workflow_ledger.py
[WATCHDOG]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/benchmarks/subreaper_watchdog.py
[WATCHTEST]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/src/test/test_354_subreaper_watchdog.py
[SUMMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[REGISTRY]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/development_model_registry.md
[PROGRESS]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/development_progress.md
[CLOSURE]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/selective_merge_dependency_closure_v2.json
[CLOSEOUT3]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v3_formal_diagnostic_closeout_v1.json
[A2RAW3]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json
[A2TERM3]: https://github.com/Rookie1234567/MyFEniCS/blob/80f51ad2694acaa0a2494c01752e84023c03beca/docs/task43_hp_adaptivity/outcomes/records/v3_root_post_pde_audit/A2_q3_terminal_audit.json
