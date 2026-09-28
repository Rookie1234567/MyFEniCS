# Task041 Review V8：swap 仅观测，收束验证并连续推进 5 nm 与 2 nm

## 0. 决定与执行身份

**用户本轮明确要求“swap出现不阻塞程序运行”，并要求尽快推进5 nm和2 nm。本报告据此取消本轮作业的swap零值/零增量否决：global、process-tree、job/cgroup的swap及pswp活动均保留记录，但不能单独导致拒绝启动、停止、最终失败或阻止下一阶段。接受已经完成的数值证据，先完成一场5 nm，再在真实2 nm尺寸上完成必要准入并继续一场完整consumer。不得继续因同一swap事件、已通过的八项配对或尚未取得完整结果而循环增加前置任务。**

```text
repository                = Rookie1234567/MyFEniCS
branch                    = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date               = 2026-09-28
reviewed_base_SHA          = d74dcbc70937029b21d458bc269f0123bb597982
base_latest_commit        = docs(task041): update V7 side qualification status
previous_review           = review_report_v7.md
latest_response           = response_v10.md
qualified_entry_source    = c5f95db7f7c2c640b666035a1949f9dc666f4da4
batch                     = task041_review_v8_formal_5nm_2nm
response_required         = response_v11.md
resource_policy           = task041_v8_swap_observe_continue
execution                 = S0 -> S1 -> S2 -> S3
hardware                  = socket0/node0, MPI8 x 1 initially
5nm_time_target           = complete public consumer <= 86400 s
elapsed_time_policy       = observe_and_report; not automatic time kill
ordinary_default          = unchanged outside this explicit Task041 policy
master_merge              = NOT_APPROVED
```

本轮消除的blocker是“数值修正已有证据，却被swap判定和分散的入口/验证流程持续挡住”。长期仍是0.7 nm、任意非可分三维、约2 TB整机；本轮Hybrid结果不外推为该长期目标通过。此次ChatGPT只提交review，不宣称已修改工作站或启动计算。

本报告明确覆盖：V5–V7及旧task中的本轮swap硬门、V6/V7暂停2 nm、旧2 nm必须先达到个位秒/50 h预测才可进入实测的顺序限制；不覆盖原方程、材料、p/h/M、数值容差、内存安全、数据真实性和Git规则。Response V10建议“将global正增量加入停止谓词”不再执行。旧报告不改写；已发生的旧合同失败仍原样保留，新增本轮裁决而非倒签PASS。

## 1. 已有证据的明确裁决：可以结束哪些诊断

依据base下的[Response V10](response_v10.md)、[V7 outcome](outcomes/causal_fix_5nm_v7.md)、[V7 record](outcomes/records/task041_v7_causal_fix_5nm.json)及[summary](outcomes/summary.md)。

| 已有结果 | 本轮采用方式 | 不得作出的扩张 |
|---|---|---|
| G1同输入和PH逐字节相同，p4恢复/Q出现约5e-11差异 | 首次记录差异已定位到p4逆作用之后，不再返回泛泛检查RHS | 未唯一分离每个底层舍入来源 |
| G2r2同一输入追加一次原残差修正，Q差降至约3e-14 | 接受有实测支持的精度修正机制 | 不宣称任意波长都已资格化 |
| G2d bottom4+top4，5e-13内部目标、最多两次修正，原配对门通过 | 接受固定八项的分侧数值资格；核对源码差异后直接复用 | 不冒充完整双侧资源/全场已通过 |
| bottom旧service exit3、后续25项只读合同复核通过 | 保留旧终态，复用数值证据及经修正的合同结果 | 不为了让旧exit3变成exit0再跑一遍 |
| 2026-09-28的13.5 nm完整consumer数值/物理通过、自然exit0，约2269.04 s | 接受数学回归，不因swap或元数据单独重跑 | 该场target=None，不冒充5nm target全场验证 |
| 该场job/cgroup swap=0，global增加286720 B、pswpout增加70页 | 旧零增量合同失败保留；按本轮政策不再阻塞5nm | 来源未知，不指认是Task041，也不隐藏事件 |
| 新的正式5nm target入口、凝聚固定通信计划已推送 | 冻结已实现且有相关测试的版本，进入正式工作流 | 代码存在不等于24h或2nm成功 |

接受上述证据是本review的执行裁决；无需再等一份同内容的用户批准。检查最终source与已通过source的实际diff：纯资源政策、路由或文档变化只验证受影响调用链；确有数学变化才重测最小受影响节点。不得将`qualification_pass=false`的诊断scope自动误判为已测动作数值失败。

## 2. S0：swap政策一次性贯通，不新造监督体系

### 2.1 对当前批次的统一语义

| 事件 | 本轮动作 | 最终记录 |
|---|---|---|
| 启动前已有global/job swap | 记录baseline，不据此拒绝启动 | bytes、所属scope、时间 |
| 运行中global swap或pswpin/out正增量 | 警告并继续，归因未知就写unknown | 原值、峰值/增量、首次事件、阶段 |
| 本任务process-tree或cgroup实际swap非零 | 同样记录并继续；不能换成job-swap硬门 | 独立于global记录，不声称zero-swap资格 |
| 任一swap字段缺测 | 写unknown，不填0；其他安全监测有效时继续 | 缺测范围和原因 |
| 数值失败、原内存cap/可用量reserve真正越界、OOM/分配失败、磁盘不足或硬件错误 | 原安全规则仍生效，受控保存与停止 | 真实停止原因，不能只写swap |
| 仅有慢速、24h未完成或交换活动 | 给进度和时间诊断，不自动杀掉或重启 | 时间目标是否满足另行判定 |

swap不是额外的物理RAM预算，也不是OOC因子分解的授权。不得因页被换出、RSS变低就声称算法内存下降；分别报告同步resident、可读的本任务swap及合计存储诊断，避免把不同时刻的峰值相加。不增加RSS上限，不开启BLR、低精度或全局p6直接因子。

默认保持主机既有swap、BIOS和内核设置；不执行`swapoff -a`、不清计数、不创建新swapfile、不提高系统swap容量、不调全局swappiness。此决定首先修改应用的准入/停止/验收语义，并不要求主动让作业使用swap。记录实际继承的cgroup限制；不能为了“零swap证明”新增强制零交换配置，也不擅自修改父级或邻任务的cgroup。已有平台限制不因本报告自动消失；真正分配失败仍按资源失败处理。[S1]

不建立新的swap专用timeout、bytes阈值或“出现交换即视为系统失控”的替代门。只有可独立证明的硬安全事件、原进度检查确认的死锁/无进展或用户停止，才停止；单条RHS久、日志暂不更新、pswp计数增加均不是充分证据。

### 2.2 必须改到入口、运行和出口，而不只改一个if

复用现有资源合同传递机制，将`task041_v8_swap_observe_continue`和review路径/hash绑定至新run manifest。针对本批明确opt-in的5/2 nm consumer及必要准入执行：

- preflight不再拒绝非零swap；supervisor不因swap单项返回termination；worker资源汇总、checker、service/finalizer不再因swap单项否定完整结果或后续阶段。
- 保留`memory_stages.jsonl`中的现有swap/global pswp字段及原始事件，先保存样本再作非swap安全判定。`swap_observed`、`numerical_pass`、`resource_safety_pass`、`time_target_met`分别表达；不要伪造`swap_zero=true`来获得总PASS。
- 仅对本次显式policy生效；未选择它的旧profile和其他任务保持旧规则。旧13.5记录不重写，只新增“旧合同失败、本轮不构成继续阻塞”的审阅映射。
- 数学参数和raw结果正确、仅checker路由/schema误判的情况，允许修正后对已封存artifact做派生只读重验；没有实际数据就不能补造。纯监督修复不使原数值结果失效。

最小测试集中覆盖：global-only正增量、本任务swap正值、启动已有swap都继续且保留记录；同样样本叠加RSS/reserve/OOM等真实事件仍停止；未知policy不被静默采用；旧policy语义不变。用现有`test_344_task041_public_supervisor.py`、相关service/launcher测试做有界fixture与正式参数路由测试，不再用一次完整13.5 PDE验证一个swap分支。

S0只做必要的资源policy/实际调用链修复，不顺手重构benchmark、写通用审计框架或继续node1诊断。准备完成普通commit、记录clean source，随即进入S1。

## 3. S1：直接启动优化后5 nm的完整consumer

### 3.1 冻结输入与算法

| 项目 | 5 nm正式配置 |
|---|---|
| 材料 | W；substrate/grating折射率0.99396854453+0.00435380777i |
| 几何/入射 | 原50×25 nm周期单胞，z=-10…130 nm，内部接口10/110 nm，1° grazing、phi=0、S极化 |
| 离散/模式 | p6 Nédélec、原h4真实网格；M480正向+M480负向，共960内部系数 |
| 方程/边界 | 原Hybrid action/RHS，dual Floquet、完整external DtN，原传播/traction与恢复 |
| 侧区 | 已有p6 trace凝聚KSP；准确p4 cell_condensed完整逆；原BAL_H/P/PH/H6 |
| p4策略 | 当前已分侧验证的5e-13内部精化目标，最多两次修正；原physical/augmented A4验收1e-10不放宽 |
| 内外迭代 | 内层right FGMRES32、zero start、max128、rtol1e-2；外层原right FGMRES32、max2048、true residual5e-9 |
| 并行/政策 | socket0/node0、MPI8×1、complex128；本轮swap观测政策 |
| 输入入口 | `input/official/task041/side_balh/5nm_p6h4_m480_mpi8_cell_condensed.dat`；`python scripts/run_case.py <case.dat>` |

允许使用已通过测试的固定通信计划和已实现热点优化，不新增另一轮性能候选作为启动条件。运行日志必须实读bottom/top backend和target，不能从文件名推断；防止无意退回full p4或在正式入口丢掉target。现有target CLI通过公共入口传入并写入resolved配置与run manifest；保留原dat/hash，不私改正在运行的输入。

复用**对应5nm**的已合格QEP packet，按已有validator核身份/完整性；producer与consumer源码分列。不用2nm packet替代，不为了source变化、资源policy变化或重新包装manifest重算QEP。真实丢失/损坏/不兼容才构成具体blocker，不能绕过物理身份检查。

### 3.2 把双侧资源验证放进这同一场，不再单独开一个前置consumer

正式顺序：packet加载 → bottom构造/审计 → top构造/审计 → 同时驻留资源检查 → 原early Schur repeat → 全部1920项正式侧区响应 → 原外层求解 → 原true residual → 最小recovery packet → 释放factor/无用矩阵 → E/H、R/T/A/体吸收/衍射 → finalizer。

“未证明双侧同时驻留”和“未取得全场结果”是本场要完成的验证，不是拒绝启动本场的循环前提。仍须在分阶段构造中执行真实内存/数值Gate；不能为证明新后端再并存旧full与new两个大因子。不另外重跑全八项，不重跑旧53h full基线或旧exact参考。

24h按公共启动到最终输出与清场计时，非仅KSP。超24h记`TIME_TARGET_MISSED`并报告进度；有真实进展且安全时继续同一场，不kill、不归零、不把时间超标混成数值失败。低于24h不是进入2nm的前提；新方法没明显加速也必须报告实际结果。

## 4. S2：5 nm通过后立即推进2 nm，不等下一轮授权

5 nm取得原数值/物理结果并正常收尾、安全门通过后，先提交轻量5nm结果快照，随后连续进入2nm；不为了等待正式长篇Response或master merge暂停。5nm超24h或swap非零不阻塞这个转移。若5nm出现真实数值/资源失败，只修已定位最小问题或提交具体证据，不跳过失败直接开更大案例。

### 4.1 2nm冻结身份与最小接线

以[旧D1e终态](outcomes/2nm_d1e_terminal_20260920.md)对应dat、physical SHA和selected-mode packet为物理authority：W、2nm、p6/h1.5、M1200正向+M1200负向、MPI8×1、同几何/入射/dual Floquet/完整DtN。折射率为0.99880148307+0.000213688647i，不继承5nm材料。保持2nm原external keys、QEP排列、相位和归一化。

使用本轮已验证的p4 cell_condensed/BAL_H路线，首次候选沿用5e-13内部精化目标和最多两次修正，原A4验收仍1e-10；**这是2nm待检候选，不是5nm资格自动外推**。仅对2nm新增必要的显式注册配置/参数路由与小型调用链测试；沿用现有runner，不复制一套新求解脚本。原2nm full-p4 dat保留；新dat可命名`input/official/task041/side_balh/2nm_p6h1p5_m1200_mpi8_cell_condensed.dat`，明确记录与旧物理SHA相同、数值后端身份改变。

旧2nm packet的metadata复用检查曾通过，仍核实际文件和当前ABI；保留33文件/32数据分片及原producer证明。p4 factor和KSP没有checkpoint，**需要重建一次**，不能承诺读取QEP后立即恢复原内存状态。不重算约8.2h的QEP，也不为每条测试反复重建p4。

### 4.2 必要准入与正式计算在一个生命周期内连续完成

先在真实2nm尺寸构建当前侧区，检查原D/A4、传递/端口、实际p4策略和资源；原consumer已有的early重复样本承担本次有限响应准入，不再额外叠加一整套full-vs-condensed八RHS诊断。原样本列、重复次数及门限不减，样本通过后直接利用仍存活的同一批factor进入4800项正式响应，避免退出重建。样本和正式列的完成计数分开。

旧D1e的重复差约4.43e-5、最坏列约1.17e-4，不可因swap放行而被忽略。新2nm必须通过原repeat门；仅原残差<=1e-2不等于repeat通过。失败时先保存两份小模态样本矩阵、上下侧差、列身份和p4全调用摘要，再停止；不得只留下低精度异常字符串，也不得直接放宽repeat阈值。

2nm达到个位秒、预测<=50h或证明十倍加速均不作为本轮新增准入硬门。必须报告实测单步/响应与总耗时规划；若仍呈月级成本，明确提示时间blocker没有解决和已完成比例，不把用户未见的月级等待包装成“很快完成”。纯预测慢不自动清场或重建，用户保留中止权；实际安全、无进展/死锁和数值停止照常生效。

## 5. 统一安全和数值合同：放开swap不等于放开错误计算

### 5.1 资源与运行环境

5nm保持原simultaneous authority/tree cap **53,221,163,008 B**；旧一次64GiB特许不延续。2nm沿原D1e warning **1,539,316,278,886 B**、hard **1,759,218,604,442 B**；整机reserve至少 **412,316,860,416 B**，旧更严非swap条件继续。实际绑定node0时，还必须按node0容量/可用量及保留余量取更严预算，不能把node1的容量计入node0可用量。swap空间不进入这项RAM预算。

不因整机有2TB自动提高cap，也不把尚未测量的凝聚内存节省当作事实。原tree/cgroup同步口径、低频PSS/USS、disk、环境ABI、监测有效性、异常退出与精确PID清场保持。release-before-recovery继续使用；不改默认factor所有权，避免释放仍被引用的对象。

node1、BIOS、内存条和双路性能排障继续暂停。5nm/2nm两场不并发；优先独占性能窗口，不擅自杀停邻任务。已有用户明确授权的隔离并行可以沿用，但需满足CPU/node内存/总reserve隔离，实际干扰记为性能限定而非数学失败；本轮不扩大发生竞争的并行授权。不能要求先证明主机所有无关后台进程绝对零交换才运行。

若2nm实际node0可用容量不足，写出实测需求、已用量与缺口；先检查可释放对象和预分配，不自动改用未资格node1，不借swap伪装容量充足。这是真实资源blocker，不是恢复swap硬门。

### 5.2 数值与物理

| 指标 | 5nm和2nm的本轮要求 |
|---|---|
| reported/global/bottom/top/modal真实残差 | 各<=5e-9，原完整Hybrid方程独立重算 |
| projection/两侧traction/external-q | <=1e-8 / <=1e-8 / <=1e-10 |
| 每次p4原physical及augmented残差 | <=1e-10；记录全调用最大值/位置与精化统计；target和最终验收不可混淆 |
| 内层与repeat | 原内层残差、finite、原同后端Schur repeat门不放宽 |
| R/T/A与A_volume、closure | 各场原吸收一致性和守恒<=1e-5；输出复E/H及全部衍射级 |
| 5nm对既有exact参考 | R/T/A/A_volume绝对差<=1e-8；selected E/H相对<=1e-6；canonical<=1e-5；significant幅值/功率<=1e-6；normal flux<=1e-4 |
| 2nm没有完整同尺寸authority时 | 如实写reference unavailable；不挪用5nm参考，不新建超大p6直接因子，不宣称网格/M收敛 |

原P/PH、实体支撑、端口、恢复与输入未修改检查保持。只因policy或日志接线变化不再重做数学系列；真的改变数学内核则跑最小受影响节点。若5e-13目标在2nm达不到，保存原残差、精化历史和实际输出，不静默放宽目标或改成full后端冒充新路线。

## 6. 不再把一场计算拆成无限阶段

S0结束后，数学版本冻结。不要再加入GPU、神经网络、recycling、弱Schur、APF、MPI数扫描、改M/p/h或新增波长。已经测试的优化保留；另一个可能更快的方案不作为当前正式运行前提。若正式计算暴露明确实现缺陷，保存现场后最小修复，只复测受影响节点；每个波长最多一次此类重试，不反复用大模型验证返回字段。

若收到本review时已有身份匹配、数值健康的5nm/2nm作业正在运行，先只读核对，不为换review或重新计时强杀。不得热改其正在执行的源码；新政策在外部控制层可安全应用时保留该作业，不能热应用时明确记录实际运行policy，不承诺已修改旧进程。旧进程若被旧swap规则停止，保留事实，下次采用新policy，不追认从未发生的连续运行。

不重复收费、不清空历史账本。V5旧54条、45194.90092220603 s仅是已登记历史；各新run在既有相应ledger追加一次，批次汇总引用run ID，不另造竞争账本。单个作业内部的setup/诊断/Schur/outer为分项，不与顶层wall重复相加。

## 7. S3：交付实时进度和真实完整结果

使用现有日志与轻量JSON状态，不新建一套监控服务。运行阶段变化时保存状态，长阶段至少每小时更新一次小型进度：UTC时间、unit/PID/starttime、runtime SHA、wave/p/h/M/backend/target、阶段、已完成样本/正式列、当前RHS迭代与残差、累计wall、RSS、swap/global pswp、是否仍有进展。重型factor无列更新时报告真实阶段与活动，不伪造百分比或将暂未输出当死锁。

正式启动、完成/失败等节点将轻量进度同步到分支；不等Response写完才告知用户是否已经开跑。运行中只写结果目录与文档，不修改冻结数学源码；文档HEAD与runtime SHA分列。

最终新增`response_v11.md`、中心`outcomes/formal_5nm_2nm_v8.md`及一个小型record，复用summary/test_summary、development_progress与development_model_registry。必须分别给出：

| 交付问题 | 所需证据 |
|---|---|
| 是否真正完整运行5nm/2nm | 实际正式入口、runroot、runtime SHA、backend和原阶段结果，不以组件替代 |
| 精度和物理是否通过 | 全部原残差、复E/H、R/T/A/A_volume、衍射、恢复和参考对照 |
| 性能 | public-to-finalizer wall、setup/Schur/outer/recovery、每RHS/每步、迭代数；5nm24h是否达到 |
| 资源 | 原resident cap/reserve、实际节点放置、job/global swap原值/增量；swap只作观察不伪称zero-swap |
| 2nm是否仍被旧repeat问题阻塞 | 原门实值、两份小样本与分侧/列身份；新策略通过或失败均留证据 |
| 尚未完成 | 具体当前阶段、真实blocker和已有进度，不能只写qualification=false |

所有新run保留Task038 provenance：`input_original.dat`、resolved config、run manifest、输入与physical/source SHA、环境/MPI、artifact hash和run summary。数值结果、资源安全、交换观察、性能目标分别裁决；允许`NUMERICAL_PASS_SWAP_OBSERVED`这样的明确限定，不能把出现swap写成数值失败，也不能隐瞒真实OOM或内存超限。

普通commit依次为最小policy/入口与测试、必要2nm显式接线、运行阶段证据和Response V11。继续原执行分支，不amend/force-push、不覆盖本地未提交工作、不改master、不合并donor。内部双窗口审阅可以继续，但本review已经授权满足条件后的阶段转移，不让用户重复批准同一条小测试。最终通过仍待ChatGPT审阅，不授予master merge。

## 8. 审阅依据与执行边界

固定base为`d74dcbc70937029b21d458bc269f0123bb597982`。本报告依据根/文档AGENTS、仓库工作原则、原task及历次review覆盖、Response V10、V7 summary/record与D1e终态；目录中截至本次无新增补充任务书。latest Review V7 blob为`ec09c035f3f666fe7b617ca336c19d78a9d53812`，上传副本同源。Codex启动时还须核对新提交和本地工作，不用旧聊天替代当前源码。

[S1] [Linux cgroup v2官方文档](https://docs.kernel.org/admin-guide/cgroup-v2.html)：job/cgroup与整机资源归属不同，`memory.swap.current`与`memory.max`等具有不同语义；取消应用层swap否决不代表取消内核资源限制。2026-09-28查阅，仅说明机制，实际字段和权限以工作站环境为准，不授权升级内核或改父级控制器。

**本轮最小成功路径是：少量policy/路由测试 → 直接完整5nm → 同尺寸2nm原有准入/重复样本 → 同生命周期完整2nm。swap本身不再把这条路径打断；真实数值错误和真实内存安全风险仍然会。**
