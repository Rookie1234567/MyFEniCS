# Task43 Review V3 执行回应：有限工程整改（V4）

本轮只处理 Review V3 §9 的 N1–N6 工程与证据事项，没有新增正式 PDE、dispatch、attempt 或 READY。代码组件测试用于验证保存顺序、异常权限和阶段记录；它们不构成新的 Maxwell 解或生产资格。原执行分支为 `task43_hp_adaptivity`，基线为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`；本轮执行回应的是提交 `185ae91424c66780caa54a85e59eb3163cad3964` 新增的 `review_report_v3.md`，该 review 审阅的代码提交为 `6f6bf3b6ad9b534eb12794a72471157218859de1`。历史 V1/V2/V3 review、合同、READY、终态和原始负结果均未覆盖或改写。

WorkflowLedger 像运行日志，记录真实入口走到哪个阶段以及是谁的进程在执行，这样监督器可判断网格或求解是否真正开始；代价是少量文件写入。原子写入先完整写临时文件再替换目标，避免异常留下半份 JSON，但增加文件同步与磁盘开销。`primary`保存正常校正后、额外回代前的状态；`extra`用同一已分解矩阵再回代一次，保存独立原向量以检查额外校正是否真正降低残差。把这些数据提前落盘，可以避免后续物理场恢复或采样出错时丢掉已有证据；代价是额外 NPZ 写入和临时存储。这些工程措施都不替代网格精度检验。

## N1–N4 整改结果

| 项目 | 实施与实际验证 | 结论边界 |
|---|---|---|
| N1：A1 真实入口账本 | 在真实 `h100_anchor.main` 的 V3 opt-in 路径中，先校验绝对 phase 路径和 watchdog 父 PID，再创建 `WorkflowLedger`，并在首次 mesh builder 前写入 phase/stage。mesh-boundary sentinel 测试实际调用该入口，读到了 `workflow_started → identity/input bound → mesh_setup_started → failed`，终态为 `INCOMPLETE`、`official_result=false`，所有 continuation 均 false；mesh builder 被调用一次后由 sentinel 截断，assembly/solver 调用为0。缺 phase 与错误父 PID 两个分支在运行目录或 mesh 之前拒绝。 | 这是隔离入口组件测试，不是 A1 正式 attempt。A1_q2 的真实 G2 缺线及主控在该事实上的错误放行/停止仍按历史记录保留；本次修复不追溯改变该 dispatch。 |
| N2：A2 异常权限一致性 | 对已经生成的 comparison 后处理，分别注入“comparison 已成功写出后回调抛出 `OSError`”和“summary 被截断后记录回调抛出 `OSError`”。保存的 comparison 原字节转存 sidecar 并绑定 SHA；当前 comparison/summary/endpoint authority 全部关闭，所有 continuation 为 false，`R_total=0.25000001` 与最大功率差 `2.5e-8` 等测量字段保留，primary NPZ 字节和 hash 不变。两种路径均保留并抛出原始异常，terminal 文件可读。 | 仅验证后处理故障路径和原子写盘 helper，不代表真实 A2 endpoint 重算或数值门通过。 |
| N3：extra 原向量及时留证 | native extra correction 的凝聚残差、独立 A6、zero-slave carrier residual、port residual、对应 RHS/solution、计数和 identity 在物理输出恢复及场采样前写入不可覆盖 NPZ。故障注入覆盖后续恢复失败、collective transport 失败和 q10 采样失败；primary hash保持不变，已落盘 extra 可读取。测试读取 NPZ 内嵌的 `__task43_record_json__`，重新计算凝聚、A6、full-active residual 并与其中 scalar 核对；`extra_full_active_strict_decrease=false` 与 `FAIL_UNCONTROLLED_EXTRA_CORRECTION` 原负门保留。 | 故障测试使用小数组及已有 writer/callback，不执行真实 MUMPS factor、构网或 PDE；不重写 A2_q3 的 extra 负结果。 |
| N4：监督器停止原因 | watchdog 现区分后代仍未清除与无后代但 cache metadata 仍不稳定。测试使用真实子进程；后代分支触发超时后恢复默认清理余量，核对 stop reason、leader exit、SIGTERM/SIGKILL 时序、最后资源行和观察到的 PID 均已清除。cache 分支允许在此前合法发信号的情况下记录信号，但要求最后资源行无后代且 leader exit 0。 | 旧 A2 `LIMITED` 终态不重分类。一次早期测试把清理余量也缩短，得到 `EVIDENCE_INCOMPLETE`；该负结果保留，修正后的后代节点重新验证通过。 |

## N5 生命周期与资源账

N5 使用已保存的 A2_q3 `stages.jsonl` 与 5,971 条 resources 记录，不重新采样、积分或求解。Root 审计记录在 [V4 root audit index](outcomes/records/v4_root_audit/index.json)、[CPU/affinity intervals](outcomes/records/v4_root_audit/A2_q3_affinity_intervals.json) 和 [lifecycle cost](outcomes/records/v4_root_audit/A2_q3_lifecycle_cost.json)。105 个 PID/start-ticks 时间区间中，5,959 条可读数值 worker 命令样本固定在 CPU1；宽 affinity 只见于 watchdog 与起始 shell 短区间，另有两个末尾空 cmdline 区间只能按同 PID/start-ticks 前序身份关联，不能称为连续命令采样。

原阶段账分别列 assembly 4,772.249 s（内部 4,771.324 s，窗口重叠不相加）、numeric 1,162.841 s、normal solve 66.524 s、primary 输出与 q8 采样 179.033 s、q10 采样 156.601 s、extra 与残差 137.226 s、停止前未完成阶段 64.839 s、清理 12.420 s。`solve_started` marker 写在 normal correction 后，不能据它把求解开销算成约 0.002 s。上述区间来自原 marker / 资源时钟，不能与 whole-watchdog wall 或彼此重叠窗口重复相加；旧 A2 `LIMITED` 与 cleanup cache-stability 异常均保留。

本轮 monitored 支持检查与测试按 watchdog whole-wall 逐次记账；每个 driver 上限 300 s、树 RSS 上限 8 GiB、task swap 0，累计不超过 1,800 s。未单独计时的 activation/preflight 操作标为 `not_measured`，不写作零秒。失败 driver 和针对定位问题的重跑全部保留在 compact，不删除或合并为一次成功。

## Review V3 的 V3-01–V3-08 对应处理

| Review 项 | 本轮处理与最终边界 |
|---|---|
| V3-01：A1 READY/ledger | A1真实入口已有mesh前账本组件回归；A1_q2现场缺ledger、已构网进入装配后由主控停止的事实不变，旧READY仍不能授权后续派发。此前把通用fixture外推成真实入口证据，是主控放行判断错误。 |
| V3-02：科学资格 | 不新增端点；A2_q3 primary仍是partial，extra full-active严格下降门为负，完整q/R endpoint未资格化。 |
| V3-03：最终共享文件生产资格 | 未关闭。旧Stage1的66路径overlay复核为59/66同字节、核心/共享路径23/27同字节；本轮局部N1–N4 focused不等于拟合入文件及共享依赖的干净production/full-suite qualification。原collection与SLEPc ABI问题保留，不改环境或忽略范围。 |
| V3-04：A2后处理权限 | comparison成功写出后的回调异常和summary截断后的记录异常均关闭当前qualified/official权限，保留原comparison副本/hash、primary hash、测量数值及原始异常。 |
| V3-05：extra保存时序 | extra代数/A6/full-active packet提前原子保存；后续物理恢复、运输或q10采样错误后仍可读取，严格下降负门不变。 |
| V3-06：监督器原因 | 新测试分别覆盖残留后代清理未完成与无后代但cache稳定性等待超时；旧A2 `LIMITED`分类不改写。 |
| V3-07：CPU亲和性 | 引用root对旧A2资源日志的PID/start-ticks区间审计：5,959条可读数值worker命令样本固定在CPU1；两个末尾cmdline缺失区间只能按同PID/start-ticks前序身份关联，不声称连续读取。 |
| V3-08：文档时序 | README、summary、manifest、模型总账和progress增加V4当前状态；V1 inventory、Stage1与V2/V3正文仍按各自历史范围解释。 |

前置门分开报告：G0为历史枚举/终态原件的有限核对；G1组件回归不代表A1现场到达primary或A2 endpoint完整；G2 A1现场不满足、A2真实native入口ledger成立；G3旧场Av/612/q8/q10输入核验成立，但不构成fresh endpoint资格；G4以V4验证compact绑定的源码、测试和日志为准。没有综合门可把组件整改“通过”解释为正式计算通过。

## N6 当前状态、能力与边界

G0–G4 不合并成单一总 PASS：N1–N3 的代码/fixture 整改与 N4 的监督器分支属于组件范围；旧 A2 的 G0/G3 取证和 N5 生命周期审计来自原件读取。A1_q2 现场实际没有 WorkflowLedger，原 READY 被该真实入口问题反证，主控在已构网并进入装配后停止，未有因子/完成求解证据；责任是此前把通用测试外推到实际入口的主控放行判断，不归因环境或数值方法。A2_q3 现场确实写出 native phase ledger，但 7200 秒停止后 full endpoint 不完整，extra full-active residual 未严格下降。工程整改通过、分支计算资格和生产合并资格是三个不同结论。

正式 dispatch 仍为 **5/6**：A1 **2/2**、A2 **3/3**，剩余一个槽封存；本轮新增正式 attempt **0**。A1_R、A2_R、B、C、迭代、成本 campaign 和 0.7 nm 均不运行，额度不重试、不跨组重分配。五项能力保持原状态：空间 `PARTIAL`，选择 `PARTIAL`，精度 `NOT_PASSED`，同精度全过程成本 `NOT_ESTABLISHED`，迭代 `NOT_RUN / NOT_QUALIFIED`。accepted9/R9 仍是最后接受状态，最终空间精度未达；没有 production merge approval。

最终 focused、文档合同、静态检查和各次受监控结果以 [V4 validation compact](outcomes/records/v4_focused_validation_v1.json) 为准。该索引绑定本轮 source/test 字节、原始 worker 日志和 watchdog summary；没有在本轮重新运行 full suite 或完整 p6 FFCx witness。后续以 ChatGPT 的外部 review 为准，本回应本身不授权合并或计算。
