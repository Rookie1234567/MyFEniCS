# Review V3：保全已提交状态，从 Adam500 阶段边界补全固定拟合

## 0. 决定、身份与本批 blocker

**接受 Response V3 的 P0、留存 Adam500 复验和中断记录；完整拟合维持 `INTERRUPTED_FIT_NO_FINAL_STATE`，不判成功，也不以会话中断判网络数学失败。下一批只授权运行保全修复、最小故障测试，以及从已核验 Adam500 阶段边界进行一次固定 L-BFGS 重放，随后独立复验。**

本批消除的是“已有拟合进展无法保全、因而无法取得可复验终态”的执行 blocker，属于**执行可靠性＋监督表示诊断**，不是新预条件器或物理方案。最终目标仍是约2 TB内、0.7 nm、任意非可分三维周期单胞的合格 Maxwell 解；当前 M5 监督拟合不能替代该目标，也不是无标签求解。

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task42extra_feinn_5nm
worktree                = /home/fenics/Projects/NN-Lab-V2
review_date             = 2026-09-30
reviewed_HEAD           = d04873f94a51a885e9cab23920767e263af22c7a
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review         = review_report_v2.md @ a668fb20dcf49f105cc4c7dfeeda145ee492ae14
latest_response         = response_v3.md
V3_fit_source           = d9e5a7d00a1cac82390b058384e0cd9193b472d4
V3_retained_audit_source= 7c2bffe4dff7b2c9a918ade6ec02a45e168b4890
next_batch              = V4_DURABLE_ADAM500_BOUNDARY_REPLAY
new_route               = FEINN-REFERENCE-FIT-G-ADAM500-REPLAY
response_required       = response_v4.md
solver_qualification    = NOT_QUALIFIED
master_merge            = NOT_APPROVED
```

ChatGPT读取了远程目录、最新review/response/summary、原始检查与资源记录、拟合源码，并核对上次review后的5个提交。没有SSH检查现场、重跑PDE或重新下载ignored数组；下文实测均指仓库记录。文件路径/hash需要Codex现场复核。本review不修改旧task/review/response及负结果，只对本批阶段边界重放、检查点和受监督持久执行作明确例外授权。

执行前读取根/目录AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、[Review V1](review_report_v1.md)、[Review V2](review_report_v2.md)、[Response V3](response_v3.md)、[summary](outcomes/summary.md)及本review。已查目录无其他补充任务书；出现更新时以同任务最新正式合同为准，不从其他支线继承命令。

## 1. V3 已证据化的结果

依据：[表示对照CSV](outcomes/records/representation_comparison_v3.csv)、[详细诊断](outcomes/representation_diagnostic_v3.md)、[中断记录](outcomes/records/fit_interruption_v3.json)、[原始梯度检查](outcomes/records/reference_fit_checks_v3.json)。误差无量纲；表内“留存”不等于完整拟合最终态。

| 对象 / 证据身份 | 结果 | 本次解释 |
|---|---|---|
| P0两个FREE终态 measured | G场误差0.991760/0.954121，负梯度与参考修正的欧氏实余弦0.02306/0.00508 | 原负梯度的两次解析最佳实步长几乎不改场；不是全局条件数或所有方向的结论 |
| P1接口 measured | batch差至多7.96e-16；3方向×3步长FD最大约2.31e-8 | 已记录样本支持拟合目标与VJP；不代表执行生命周期通过 |
| Adam500 retained / measured | E_G=0.2008211341；散射E L2=0.1620127280；scaled-curl=0.2017046510 | 较零态有实质拟合进展，尚未达到原表示门限 |
| Adam500原方程/物理 measured | native/augmented=14.2634632072；能量闭合0.0417011582 | 全部严格Gate仍失败，不是接近合格的PDE解 |
| 参数/矩独立复验 measured | 参数到q15系数差0；q30/q15差2.8584e-12 | 支持该留存场身份与求积精度，不是p/h收敛 |
| 后期 scalar log only | closure817的committed审核E_G约0.0603363、native约8.19881 | 相应参数未保存，不能据此给出L2/H/功率或最终资格 |
| 失联 unknown cause | 日志至少到825完整closure；final、last_trial、optimizer、supervisor summary均缺失 | 不是已证wall/resource/numerical停止；不声称实际总closure恰为825 |
| 已采样前缀 measured | RSS峰697479168 B、VmSwap峰0；最后采样3097.314 s | 未观测尾段未知，不把前缀峰当整个失联过程严格上界 |

失联与客户端回合边界时间相邻，但因果机制未证实；不得写“已确定是SSH、Codex、OOM或watchdog杀死”。旧阶段继续保留保守3284 s费用和全部原字节，不补造正常终态/退出码。

源码明确只在zero、Adam500、finally保存参数，L-BFGS期间的committed数组仅在内存中更新；故正常异常回滚不足以处理整条执行链消失。Adam日志的`parameter_update_norm`又在更新前计算，不能解释为真实接受步长。这两点是本批修复范围；它们不证明拟合目标或Maxwell算子错误。

## 2. 为什么可以从 Adam500 边界重放，而不是盲目续训或重算500步

[当前拟合源码](../../src/solvers/feinn_reference_fit.py)的顺序是：完成500次Adam，保存`adam500_checkpoint.npz`，**之后才创建一个全新的L-BFGS**。当前网络无dropout，拟合输入/求积固定。因此，可以针对这一特定阶段边界验证如下续接：加载相同网络参数与缓冲区，核对坐标/完整矩/标签，重新创建原配置的空历史L-BFGS。后续不再调用Adam，不需要恢复已结束Adam的动量。

这并不意味着一般parameter-only文件可恢复任意训练：第817次所在L-BFGS的历史已经丢失，不能恢复该位置；本批只是**从最后可验证优化器切换边界重放后段**。旧Adam500无optimizer状态的历史标注不改，新记录写`ADAM500_TO_FRESH_LBFGS_BOUNDARY_REPLAY`，不写exact-resume-at-817、fresh-zero-run或新独立随机试验。

必须先通过第4节的边界等价检查。若原文件/配置/代码流不能验证，标`BOUNDARY_REPLAY_NOT_QUALIFIED`，不得自动改成从零重训、任意warm start、恢复假L-BFGS历史或加载参考系数替换网络输出。

## 3. 冻结对象、标签和预算身份

| 对象 | 本批固定定义 |
|---|---|
| 物理与离散 | 原M5：5nm Si/air、384hex、p3/q15、h1.25nm、1°/phi0/s；双Floquet＋完整Fourier-DtN |
| 未知量/网络 | 全部31968复FE和40端口；原3→64→64→64→6 tanh、8966实参数、FP64；初始化血缘seed421001 |
| 训练目标 | 原监督G场误差；原G、散射c_ref和分母不变，不回到残差训练或V2变量D |
| 阶段锚点 | V3的Adam500参数，且已独立复验；绝不使用仅有日志的817/825状态 |
| 数据政策 | reference_used_for_training=true；pde_only_solve=false；production_initialization_allowed=false |
| 生产/泛化 | pde_only_solver_qualified=false，official_candidate_results=false；不接回旧路线、Task042或0.7nm |

```math
 e=c(\theta)-c_{\rm ref},\qquad d_{\rm ref}=c_{\rm ref}^*Gc_{\rm ref},\qquad
 J_{\rm fit}=\frac{e^*Ge}{2d_{\rm ref}},\qquad E_G=\sqrt{2J_{\rm fit}}.
```

必须从V1/V3 run index取得实际路径并核对下列文件字节SHA256。新运行使用新stage/index/artifact，不覆写旧记录。

```text
Adam500 checkpoint = 4e818a16b876ffd0776e74438654ca7de5632b1e17269a38e87749b5b3ad6a97
native packet      = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
Gram file          = 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9
moments q15        = 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e
reference state    = 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7
material table     = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
```

拟合closure仍只有G matvec、网络及完整矩VJP，无Gsolve、Gram factor、A/AH或Maxwell factor。A只用于受限审核；已有P0不重跑。相同数值接口/环境按source与hash复用，不重装环境、不重新求参考。

## 4. R0：最小运行保全及阶段边界资格

### 4.1 受监督持久执行，不是取消监督

先读现有launcher/subreaper/fit退出路径和可得的短日志，登记父子PID/start_ticks、session/process group、stdout去向、cgroup/scope、任务锁及退出链。旧退出原因无证据就保留unknown，不作全机取证或扫描邻任务日志。

优先采用现场**已经可用且获准**的持久终端/作业机制；例如独立命名的tmux会话可承载本任务的完整launcher＋watchdog＋worker。必须先检查可用性/权限，实测最小断连情形，不能因tmux存在就声称所有客户端/作业回收路径均能存活。持久会话只承载本次人工明确批准、有限时长的工作，不创建cron、自动抢跑或无限重启器。

原资源准入、数值锁、时间限制、整树RSS/swap监督都要在持久执行端继续有效；不能仅把worker移到监督树外。标准输出/错误直接记录任务文件，不以客户端管道为唯一输出；同一run以独占锁和PID/start_ticks防重复。任务外会话管理开销说明口径，不伪称已包含于worker树峰。

不得绕过工具沙箱、权限、平台回收策略，不修改系统服务/登录策略或装系统包。已有机制无法在允许边界内满足保全时，交付检查点与轻测试，标`DURABLE_EXECUTION_BLOCKED`；不得发起长训练碰运气。这里的持久执行授权不要求更换用户Codex前端。

### 4.2 每个完整外层step都要有可恢复的磁盘状态

只在Adam更新或L-BFGS**外层step正常返回**后提交，不能把closure试探态作为提交态。本次新正式段只有L-BFGS，但修复遥测/小测试可涉及Adam。保留最后两个完整检查点及阶段锚点/最终/审核点，不无限保存逐closure大数组。

每个完整提交记录模型state、实际buffer、参数顺序、当前优化器state与超参、阶段、全局及本段计数、RNG状态（或准确的无随机运算说明）、source/输入/标签/矩hash、已耗预算与run ID。保存过程同步完成后才进入下一step；不要将可变state_dict引用交给未受控异步线程。检查点至少可从参数重建c，审核点和最终同时保存c及其hash。

采用同目录临时文件写入、flush/fsync、原子替换，最后更新指向完整文件的指针；文件hash/计数/state_kind一致。写入中断或磁盘错误时保留上一代，不拿半文件继续。新完整optimizer检查点必须经加载后短程等价测试，未经测试不能标resumable。

预算/非有限/安全停止恢复最后完整提交的参数及匹配optimizer状态；不能把已改动的优化历史与旧参数混装。最后试探态独立保存并明确not_committed。对SIGKILL/整树销毁不能承诺finally或final文件一定执行：有效保证是**已成功落盘的上一完整边界**；终态缺失时如实记录unexpected_exit，不伪造completed。监督失效不得留下无限运行的无监督worker，采用现有合格父进程死亡/租约机制或等价的有界安全停止，不开发全机常驻平台。

遥测改为在外层step正常返回后计算`norm(theta_after-theta_before)`，单列相对增量。closure中若保留试探位移，名称明确为trial displacement；不能继续把更新前的0叫接受步长。磁盘检查点先与记录绑定，再发布committed审核行，避免再出现“日志817有进展、参数全丢”的情况。旧遥测不补写。

### 4.3 必须用小问题验证的故障情形

| 测试（仅自身合成子树） | 必须取得的证据 |
|---|---|
| 正常与中途加载 | 小型复数loss的连续执行与完整state保存/加载后后续步骤一致；参数/目标/optimizer状态相对1e-12或更严格明确规则 |
| 优化器切换 | 小模型Adam结束→fresh L-BFGS连续路径，与保存参数→重建fresh L-BFGS路径一致；不用旧Adam状态冒充任意续训能力 |
| 原子文件中断 | 写临时文件期间中断只影响新文件；上一完整检查点/hash可读；只注入自己的测试子进程 |
| 线搜索与预算异常 | 确实触发非零L-BFGS试探；异常恢复声明的完整外层边界，计入试探费用 |
| 启动端断开/输出管道关闭 | 在现场获准机制中模拟短启动端退出，受监督dummy仍完成或按声明安全收尾；保留证据，模拟不能冒称真实所有断连路径通过 |
| 明确停止/监督失效 | 给自身测试树停止，资源监督仍能清场；监督死亡不会造成持续无监督负载；检查点可读且退出状态真实 |

R0整体新增有载/辅助≤1800s，轻测试树≤2GiB。真实M5边界核验允许至多12次完整fit loss/gradient评价，不更新生产候选；核对原Adam500参数生成c、E_G=0.2008211341及原残差14.2634632（用原记录精度容差），并以克隆状态比较旧/新目标和梯度相对≤1e-10。不重新做整套FE/Gram资格，不把测试状态作为新训练初值。失败只最小修复受影响处；所有费用保留。

## 5. R1：一次 Adam500 → fresh L-BFGS 边界重放

R0共同安全/身份Gate全部通过后，启动新唯一one-run输入，建议命名`v4_reference_fit_boundary_replay.dat`。真实入口仍是`python scripts/run_case.py input/task042extra_feinn_5nm/<one-run>.dat`；持久执行包装不得直接跳过该入口调用裸worker。

加载核验的Adam500参数、原固定buffers和完整矩；**本段不再执行Adam**。创建空历史L-BFGS：lr1/history20/strong-Wolfe/max_iter20/max_eval25/tolerance_grad1e-7/tolerance_change1e-9，与V3在此阶段会创建的配置相同。不恢复不存在的817历史，不换优化器/学习率/seed/网络/载波/求积或loss。

单独记录`inherited_committed_Adam_updates=500`、`new_complete_fit_closures`、`logical_path_closures=500+new_complete_fit_closures`；旧失联段观察到的825只是旧尝试下界，其500之后重复计算的成本不得删除。新段最多3500次完整fit closure、最多10800s（含加载/检查点/审核/最终保存，预留≥120s），先触者停止。这个本次重放限额是明确新授权；不得说整个首次实验只用3h/4000closure，旧尝试和本段的真实研究成本累计入第7节总账。

每25closure可记轻量fit与梯度；每个完整外层step保存持久状态及真实更新量。每跨过100个本段closure在最近完整committed态做一次native审核，起末共≤40次；同一个参数态的拟合误差、native残差、checkpoint ID必须对应。达到E_G≤1e-3可在完整审核边界提前冻结。小梯度/tiny step如实记停滞，不反复重置L-BFGS以消耗余下预算。

本批只允许**一次正式后段重放启动**。客户端仅断开而作业仍受监督运行时，重连同一作业，不另启动。若新作业真正再次失联/失败，先保全检查点并停止，不自动再次重启，也不切换成全新从零试验；以后恢复授权另审。本批的小问题恢复测试不等于对正式运行授予无限续训。

## 6. R2：完整终态独立复验与分流

新段结束先冻结最终已提交参数和c。复用V3的独立ML参数→q15/q30重建、FE compare-only及标签策略；只重建必要后处理对象，不新增MUMPS symbolic/numeric/solve、Gram factor或global Maxwell CSR。V3 Adam500独立结果可复用，主要审核新终态；如新终态不存在，只审核确实保存的最新边界并保留中断分类，不替代完整试验。

继续报告E_G、total/scattered E的L2与scaled-curl、六点复E/H、各类完整有序复通道及明确分母、R/T/A_balance/A_volume、独立能量闭合；按原air/substrate/grating/interface-near集合给出诊断。参数→c配对≤1e-12、q30/q15差≤1e-8，失败标身份/求积不合格，不改q15再训练。

| 最终分流（沿用Review V2） | 判断 |
|---|---|
| E_G及独立散射E L2、scaled-curl三项均≤1e-3 | REPRESENTATION_WITNESS_POSITIVE，仅此网络/本参考的监督表示实证 |
| 三项均≤1e-2而未满足上行 | PARTIAL_REPRESENTATION_WITNESS，未证明原精度可达 |
| 有完整终态但仍超限 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED，不据此证明数学上无法表示 |
| 再次中断或缺终态 | INTERRUPTED_FIT_NO_FINAL_STATE，单列留存快照，不叫正常预算负结果 |
| 任何严格物理Gate通过 | 单独记录数值事实；参考已用于训练，pde_only_solver_qualified及official_candidate_results仍固定false |

严格诊断标准不变：原方程1e-6、场/通道1e-4、功率/能量1e-5、逐级功率1e-6、MPC/恢复1e-10；研究1e-3不是降低物理门限。不得用监督权重启动PDE残差微调或目标模型。只有取得完整终态后再决定是否改表示/优化，不把本次执行修复变成任意调参许可证。

## 7. 资源、费用与Git

原生Linux、同一canonical worktree，独立环境/cache/锁、内部串行；CPU-only、MPI1、数学/Torch线程1、DataLoader0，现场选空闲物理核并避开邻任务SMT。数值树warn12/hard16GiB、自身swap0/无OOC；轻测试/浏览器≤2GiB。系统reserve=max(128GiB,effective_total的10%)、邻增长至少384GiB、再加本任务预算；磁盘自由≥50GiB、artifact总量≤20GiB。不改邻任务HEAD/环境/锁/affinity/watchdog、系统BLAS/CUDA或安全策略。

本批全部新增有载与辅助≤4h，同时受原16h剩余额度约束；R0≤30min，R1≤3h，R2/文档等使用其余且总量不超限。V3最终[资源账](outcomes/records/resource_costs_v3.json)给出旧累计保守值33070.52670758043s、原16h剩余24529.473292419574s；现场再加后续真实费用，不能用summary较早快照重置。旧失联3284s完整保留，新后段重复工作/存盘/外壳/监督/加载/复验均计入；跨主子timer不重复累计。

无cgroup委派时如实沿用约0.5s采样；不把前缀swap/RSS当未知尾段保证。持久执行不豁免准入或运行中压力检查；资源紧张只停自身，不抢占邻任务，不无限等候。性能标shared-workstation，不承诺零干扰。

仅安全fetch/fast-forward本分支。共享origin.fetch没有映射本分支时，命令级精确refspec并显式核对tracking ref及ahead/behind；不把无法解析的`@{upstream}`当通过，不擅改共享配置。无本任务活跃负载才修改源码/提交，正式启动前clean实现commit并绑定source。只推送`HEAD:refs/heads/task42extra_feinn_5nm`；不新clone/分支、不amend/强推、不merge master或其他支线。

## 8. 最小实现、证据和 Response V4

复用`feinn_reference_fit.py`、原CompleteMomentMap/FitMetric/compare-only、`feinn_workflow.py`和现有watchdog。新数值入口只做明确opt-in阶段边界装载，持久运行/存盘作为小型可复用组件；不改旧路线数学默认，不新建通用调度系统。FE进程避免顶层import Torch。版本变化不触发重跑P0、全部FE检查、全仓pytest或安装环境。

建议提交C1：运行/检查点协议与故障tests；C2：Adam500边界资格与新one-run adapter；C3：唯一正式重放及独立验算；C4：compact证据、summary/总账/response。代码错误可一次有证据最小修复，预算不重置；不得用修复名义悄悄重复长训练。

最少交付：`response_v4.md`、`outcomes/durable_replay_v4.md`，以及records下的`replay_design_v4.json`、`durability_checks_v4.json`、`run_index_v4.json`、`checkpoint_index_v4.json`、`representation_comparison_v4.csv`、`gate_decisions_v4.json`、`resource_costs_v4.json`。原大数组/checkpoints留ignored目录；Git只保存必要hash和小摘要。保存input_original/resolved_config/run_manifest/input/physical/source SHA及run_summary；末态缺失如实分类，不伪造summary。

summary追加V4保留V1–V3；同步本分支development_progress、development_model_registry、test_summary、changed_files。Response先报告实际HEAD/source、是否通过运行保全和边界资格、是否启动唯一新段，再分开报告累计工作量、最终/留存参数、表示/物理/资源结论和标签政策。明确旧817状态未恢复、旧825仅是日志下界。

本次只新增review，不改旧task公式。文档检查限新review和必要新证据，原渲染通过记录复用，不再次浏览所有历史页面。GitHub视觉渲染不可访问则如实标not_verified/blocked，不能伪造截图或PASS；不因渲染失败重跑数值。

接口参考仅用于实现核对，不改变现场固定版本：PyTorch官方[Optimizer.state_dict](https://docs.pytorch.org/docs/stable/generated/torch.optim.Optimizer.state_dict.html)说明优化状态与参数组的保存；[tmux官方说明](https://github.com/tmux/tmux/wiki)介绍detach/reattach。具体库版本、持久执行权限和断连行为以工作站实测为准，不根据文档宣称本任务已通过。

完成本轮提交推送后等待review。没有完整终态就不扩大网络；即使监督表示通过也不自动升级为PDE求解、p4、目标尺寸5nm或0.7nm/48h通过。
