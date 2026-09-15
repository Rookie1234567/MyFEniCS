# Task041 Review V3：解除构造期阻塞，分侧测速后恢复等价提速验证

## 0. 本轮决策与身份

**接受 S1f 的资源受控停止记录，不接受任何新的数值失败或提速失败推论。授权继续同一 Task：先定位构造期峰值，将八 RHS 组件诊断改为分侧顺序执行，在原内存上限内完成配对；满足条件后恢复 V2 的 13.5 nm 与 5 nm 完整验证。内存上限不提高，求解精度不降低。**

```text
repository                 = Rookie1234567/MyFEniCS
working_branch             = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                = 2026-09-15
reviewed_HEAD / base_SHA    = 74ea02308070ed047989d8997e2627cee79e35db
S1f_run_source             = 1c1d36b168bfb3939314ee2faf5b943cca804382
historical_H3_run_source    = 51694bbc49d90e70eef87c953f07c695f5fc519c
previous_review / response = review_report_v2.md / response_v3.md
implementation_profile     = task041_schur_speed_v2 (explicit opt-in)
response_required          = response_v4.md
MPI / mathematical_threads = 8 / 1 per rank
master_merge               = NOT_APPROVED
```

本轮消除的 blocker 是：用于优化 Hybrid 侧区重复响应的有限测试，在尚未执行任何 RHS 时就因双侧构造重叠超限，无法取得细分耗时和等价优化证据。它服务于 2 TB 内的 0.7 nm 目标，但不证明短波、任意三维或通用 production 已通过。

本文是对已由 Response V3 回应的 V2 的新审阅，因此新增 V3，保留 V1/V2 与所有旧结果。本文覆盖 V2 中组件构造顺序、对应准入和本次停止后的继续授权；未明确覆盖的物理、数值、内存、输出和安全要求继续沿用 V2。ChatGPT 只提交本 review，不修改求解器、不启动 PDE。Codex 在同一执行分支实施；不创建 Task42，不整体合并 donor，不修改 master 或邻近 Full3D 任务。

## 1. 接受的证据与尚未定位的根因

依据：[Response V3](response_v3.md)、[S5a 中心报告](outcomes/schur_speed_v2.md)、[compact](outcomes/records/task041_schur_speed_v2.json)、[summary](outcomes/summary.md)。

| 项目 | 已有事实与数据身份 |
|---|---|
| 测试 | 5 nm / p6h4 / M480 / MPI8，未做主要性能优化的 fixed-eight baseline |
| 进度 | top adapter 构造期间停止；固定 RHS 0/8；新 QEP、完整 Schur、outer、recovery、RTA 均 not_run |
| 直接原因 | controlled_negative_resource_stop / process_tree_rss_limit |
| 严格 RSS cap | 53221163008 B，沿用 V2；不是整机容量 |
| 触发样本 | raw line 7349，RSS 53331742720 B，超出 110579712 B；PID 同刻 RSS 求和闭合 |
| 停止前增长 | line 7313 到 7349，约 10.80 s 内增加约 5.05 GiB；derived，不预测后续峰值 |
| 其他资源 | job swap 与新增换页为零，reserve 未触发；不是时间预算耗尽 |
| 生命周期 | SIGTERM 后 systemd 清理剩余任务成员；公共 summary 未完成，不是自然成功退出 |
| 旧 H3 | 数值比较 PASS 保留；RESOURCE_COMPARISON_INCONCLUSIVE 保留 |

不能把约 105 MiB 的触发超出量称为完成所需的额外内存；构造仍在增长。不能用不同时间的 PSS/USS、public-only 子树或 cgroup 数值替代本轮 RSS。

V2 将旧不完整采样段的最大观测值作为新完整监督范围的严格 cap，却没有先确认原算法基线能在这个新范围内完成构造，这是实验准入设计的不足，不是 Codex 必须绕过 cap 的理由。本轮通过减少对象重叠和分侧诊断处理，不自动增加 5% 容差，也不扣除新监督进程。

代码定位以本页 base_SHA 为准：`benchmarks/task041_exact_side_workflow.py::_run_task041_balh_candidate_setup` 先构建并保留 bottom，再构建 top，之后才判断 representative_rhs；`src/solvers/physical_balanced_side_inverse.py::build_side_balanced_inverse` 又包含 full physical action、p4 factor、P/PH transfer、H6 及 adapter/KSP 的整套初始化。因此，`top_factor_setup_begin` 不能单独定位到 MUMPS numeric。具体增长源目前是 unknown，禁止直接宣布内存泄漏、p4 factor 失败或 H6 失败。

## 2. 冻结身份与不可修改项

正式物理基线、exact authority、积分、网格、双 Floquet、接口相位/法向、DtN、selected-mode packet 和恢复流程不变。5 nm 输入仍为：

```text
input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat
input_sha256     = 9e77be901d54a8eb6d4f090588dec26c4913facd7c16c53fb46c0025eb31adb2
packet_manifest  = 306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f
RHS manifest     = outcomes/records/task041_representative_rhs_v1.json
RHS manifest SHA = fb68011ed3e55861c59455d082be549cdd9f6c2d5a569015cf88bdc739f5636a
```

原八项顺序及 formal column 保留：bottom positive 207、15，bottom negative 671、493，top positive 310、12，top negative 666、493。用原 `modal_coupling_action(e_column)` 生成，不再乘一次传播因子，不按“容易收敛”重新挑选。实际 owned-vector hashes 在生成后记录；S1f 的 not_materialized 不能补写为已测。

```text
inner                 = right FGMRES32, max_it128, rtol1e-2, zero start
outer                 = right FGMRES32, max_it2048, five-residual threshold5e-9
p4 physical residual  = <=1e-10, original refinement policy
BAL_H balance         = original 1e-8 operation-scaled Gate
full p6/global factor = 0/0
p4 inverse            = same accurate physical inverse, no alternative PC
```

不改 M、p/h、材料、物理吸收、精度、restart、初值或迭代停止要求。不引入混合精度、fast-math、BLR、recycling、新粗空间、近似模态 Schur，也不将本机 p4/p6 凝聚方案整体搬入。原 action/oracle 与独立 comparator 保留，不能同时改待测实现和参照来相互证明。

## 3. 执行顺序：先取得有效组件证据，避免重复卡在双侧 setup

### R0：只读旧日志，保留未知项

安全核对 branch、HEAD、upstream、worktree、当前 AGENTS 和 ABI。若 HEAD 前进先读差异，不 reset、不覆盖修改。复用已有 S0 统计和固定八项，不重算全 Schur。

流式读取 S1f 停止前的 memory/markers/stdout，形成一张按时间对齐的表：bottom ready、top begin、每个已有细阶段、同刻 PID RSS、factor inventory 和终止。核对运行时实际导入代码及是否有重复对象。原材料/packet/hash 核验使用已有入口，不重新生产 QEP。日志缺少子阶段就保留 unknown；不为填表原样重跑相同失败命令。

### R1：最小子阶段标记与分侧诊断入口

复用当前通用 runner、representative_rhs 参数和 service；增加一个明确记录在 manifest 的 `side_setup_schedule=sequential_component`，只对组件诊断生效。完整 consumer 默认仍为双侧实际求解组织，不静默改变它。

组件诊断改为：

```text
已有 packet / side systems / coupling 按必要依赖准备
→ build bottom adapter → bottom admission → 原 bottom 四 RHS → 保存 owned shards
→ destroy bottom adapter → 核对 live factor/KSP=0、借用对象未损坏、RSS 记录
→ build top adapter → top admission → 原 top 四 RHS → 保存 owned shards
→ destroy top adapter → 同样核对 → 正常关闭组件运行
```

组件阶段最多一套侧区 adapter 的 p4 factor 存活，不在 MPI rank 内复制串行全侧因子。优先只调整 adapter 生命周期；不为此重做 mesh、MPC、traction 或全局 operator。必要的借用 side system/coupling 可以保留；不得通过提前释放借用对象导致下一侧或原 operator 失效。

将原全局 action/RHS 的不变性检查分布到每侧构造/释放前后；可以顺序使用同一组有界测试向量，不能删除检查。每侧 admission 在该侧存活时执行，不要求已释放侧继续存在。共享对象和输入不变、零 slave、orientation、Hermitian dual、MPI empty-owner/ghost 均按旧合同检查。

在原 builder 中增加可选、默认 no-op 的少量阶段回调：full-action；p4 form/assembly、symbolic/numeric（后端能可靠分开时）；transfer；H6 diagonal/window/runtime；adapter ready；release。每阶段记录起止时间、可对齐的 RSS 和去重后的主要对象字节。不能记录到的 native workspace 标 unknown，不靠 NumPy nbytes 宣称完整 RSS。标记不按每单元/每次 matvec大量落盘，不再建立一套调度平台。

### R2：原算法分侧 baseline，随后最多两组热点优化

先在新的分侧时序下测原算法的固定八项，取得 P/PH、MatSolve、A4 residual、A6/H6、分配/通信的细分时间及输出 shards。这一结果名为“原算法、分侧组件基线”，不是原 S1f 重现成功，也不是双侧全流程基线。

若单侧构造仍逼近/达到 cap，不尝试另一轮同配置：利用已完成的子阶段证据先检查已无后续用途的装配临时量、重复数组、FFCx/H6 初始化数据和跨阶段引用。只允许有证据的提前释放、替换式有界 scratch、收紧对象生命周期。必要时优先完成这种构造释放修复，再把修复后的同一公共 setup 用于 baseline 与 optimized，两者的共同变化单独报告。

特别检查 `physical_balanced_physical_operator.py::P4ExactFactor` 的源矩阵与 factor 所有权：factor_only_storage 不等于 wrapper 的源矩阵已经释放。只有确认全部 layout/vector factory/诊断消费者，并保留原 A4 独立残差所需数据后，才允许以小型 metadata/向量模板替代纯结构用途的存储；不得盲目 destroy，也不得删掉 residual oracle。此处是审计候选，不是已证实的峰值根因或必做重构。

取得 baseline 后，按 V2 第4节选择最多两组实际热点：优先固定传递通信/伴随临时量，以及物理 action/残差作用的重复工作；H6 或向量池只在计时支持时做。每项先局部等价检查，再纳入 optimized。原八项由同样分侧时序、相同 MPI/线程/packet 顺序配对，baseline 与 optimized 在不同 fresh 进程中运行，不同时驻留。不要先做完所有优化，再补造一个“旧基线”。

单列流式 Schur可以按 V2 保留为后续集成优化，但它发生在 setup 之后，不能被用作本次 top 构造超限的解释或修复证明。小型对象/通信优化是否值得做由实测决定，不预先承诺倍速。

### R3：符合条件后，恢复 V2 的完整验证

先完成一次 13.5 nm / p6h10 / M120 / MPI8 优化 candidate 完整回归，与已冻结 exact 输出比较；不重跑 exact，不重新求 QEP。该次必须使用实际双侧求解布局并正常完成，RSS 不超过原 13.5 nm cap。

进入 5 nm 完整 consumer 前必须同时具备：原八项数值/等价通过；同口径配对内存不增；八项 apply 总时间新/旧 <=0.80；两侧分别报告且无未解释严重退步；setup 成本及原1920个正式响应的总成本预测计入，不能只报单次 kernel 速度；根据子阶段库存和已测数据没有明确的双侧超限证据。预测标 predicted 并列假设，不作为容量通过。

满足这些条件后，仅允许一次优化后的 5 nm 集成运行，沿用 V2 的 S4：在同一 invocation 中先完成双侧构造、原 admission 和有限 cost check；若超限/失败立即收口，不进入全 Schur。若通过则继续原全列 Schur、outer、recovery；不要额外先跑一场完整双侧 setup、销毁后再重建一次。组件测试的缩小驻留不能用来豁免这个真实双侧准入。

保留原1920正式响应及32独立模态样本，最终以完整 consumer 时间和峰值验收，不要求仍恰好5个outer iterations。没有20%组件收益或双侧准入依据，就交付组件结果并停止，不为追求全场 PASS 再投入旧53小时。13.5 nm 或 5 nm 有新实质数值问题时按旧 Gate 停止，不临时换另一种数学候选。

## 4. “内存不增”必须保持同口径

| 范围 | 严格上限 / 要求 |
|---|---|
| 5 nm 组件和完整 consumer | 同时任务进程树 RSS <=53221163008 B；运行时达到停止阈值按原 watchdog 执行 |
| 13.5 nm 完整 consumer | 同时任务进程树 RSS <=9159106560 B |
| 其他安全要求 | 取现有更严限制；原 reserve、有效 cgroup 限制、job swap=0 均保留 |
| 覆盖 | service parent、public、MPI ranks、编译器、采样/收尾子进程均纳入，至最终文件写完及任务成员退出 |
| 配对 | 相同分侧时序、同环境的 baseline/optimized；各侧 retained、临时峰、setup/apply、总组件峰分别列出 |
| 最终结论 | 分侧组件峰不等于双侧完整峰；旧H3不完整峰值不能当新完整历史基线 |

RSS采用同一采样轮的所有专属进程求和，不求各PID历史峰之和；PSS/USS另列，不改变判据。新监督对象不能从账里扣除，也不能把邻作业内存误算为本任务。某对象destroy后RSS未降不直接判内存泄漏，区分引用、allocator保留和native工作区；原有安全heap cleanup只能在合适阶段使用，不能以删文件、换页或OOC代替释放。

新缓存必须替换旧表示或由同一生命周期中已证实的释放支付；不在 baseline 之外偷偷预热/建立大缓存。微小波动不自动放宽 cap，无法证明不增则 MEMORY_NONINCREASE_UNPROVEN。任何超限样本保留，不能剔除后重算峰值。

## 5. 精度、测试与监督修复边界

全部 V2 数值门槛继续生效：基本 action 等价相对差 <=1e-11（原更严者沿用）；p4 原物理残差 <=1e-10；BAL_H 平衡 <=1e-8；内部原1e-2及真实reason；Hybrid reported/global/bottom/top/modal均 <=5e-9；projection/traction <=1e-8、external-q <=1e-10；独立体吸收/能量误差 <=1e-5。与 frozen exact 的 R/T/A/A_volume 绝对差 <=1e-8、selected E/H rel L2 <=1e-6、canonical <=1e-5、显著通道复幅/功率 <=1e-6、flux <=1e-4，保留全部80/600 channels，无相位拟合。

不硬要求浮点轨迹逐bit相同；内部恰好触碰阈值导致步数变化须记录并解释，不能只看最终标志跳过 action 等价。分侧代表性响应没有完整场，不能产生 official RTA。

测试以改动相关的生命周期/顺序 pure tests、真实小 FE、必要 MPI2 和实际 MPI8八项为主。必须覆盖：销毁bottom后top仍可用；borrowed对象不被销毁；异常时只清理拥有的对象；无双侧adapter重叠；release后原action/RHS不变；hash绑定不漂移。最终代码后重跑受影响测试及scoped Ruff/compileall；旧105项通过不是新实现通过，不因无关文档改动重跑heavy或全仓测试。

复用现有systemd/service和finalizer，最小修正正常退出与受控停止的分类：预期资源停止、非正常成员残留、最终清场分开报告；不得把S1f历史service_boundary_failure追认为成功。旧public summary停在launching时，由外层另写权威终态索引并保留原文件/hash，不伪造worker正常完成。新运行检查整个专属service cgroup，而不只检查一个PGID；不得杀邻任务或修改全局系统设置。已有合格监督测试复用，仅补受影响的退出/所有权测试，不开启新的监控框架研究。

## 6. 预算、停止条件与交付

继续使用原V2唯一ledger，不清零、不另获一轮完整预算。已提交记录 used=2881.0536036838917 s，共享S0/S1/S3剩余约18718.9464 s；执行前读取实际最新值。R0/R1/R2及有限诊断计入共享21600 s；13.5 nm对应S2的7200 s；5 nm对应S4的172800 s；整批201600 s。失败尝试也计入。按最外层单调时钟计费，不累加嵌套wall或MPI CPU时间；复用已有账本，不为微小尾差另开反复核查任务。

本次允许变更后的分侧baseline和optimized各一次；明确局部实现问题最多一次受影响阶段修复复测，仍在剩余预算内。资源超限不自动重试；若新子阶段表明剩余构造超cap而本轮无法安全释放，立即提交具体对象/阶段与建议，不猜测只需多给105 MiB。所有阶段Gate满足可连续推进，不每个小步骤向用户重复请求批准；存在真正安全、精度、范围或预算阻塞则收口。

同工作站仍只允许一个heavy case：启动前检查实际进程、CPU占用和heavy lock，不能因邻作业只在CPU23便默认许可并行。邻作业运行中可只读分析/编辑代码，heavy标记BLOCKED_BY_ACTIVE_HEAVY_JOB，不等待循环或终止邻任务。若另有用户明确并行授权，保留其原文和作用范围，不由本review推断。

提交以下最小交付，不复制一套新任务目录：

```text
docs/task041_mpi1_shortwave_hybrid_capacity/response_v4.md
docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/setup_recovery_v3.md
docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_setup_recovery_v3.json
```

更新本任务summary/test_summary、development progress/model registry，保留旧S1f/H3记录。交付表至少回答：实际峰值子阶段及unknown；删除/提前释放了什么；baseline/optimized每侧与八项总时间；原p4/action残差与完整物理结果（未跑则not_run）；常驻/临时/全树RSS；双侧准入与完整consumer是否达到；QEP仍为0；正常/受控退出；完整source/input/physical/resolved/packet/artifact hashes与命令。

普通commit顺序：最小分侧/标记与所有权测试；经计时选择的必要释放/两组热点优化及测试；正式结果和Response V4。正式运行先clean commit，source SHA与最终文档HEAD分开；不amend、不force-push、不merge master。

状态分开：组件通过可写 COMPONENT_EQUIVALENT_SPEEDUP_MEMORY_NONINCREASE；双侧setup通过仅为 DUAL_SIDE_SETUP_PASS；完整数值/时间/内存/覆盖都通过才写 FULL_CONSUMER_SPEEDUP_MEMORY_NONINCREASE。受控资源停止、精度失败、监控缺失和无足够提速分别保留，不一概写算法失败。

**本轮要恢复的是有效的数值与性能实验，而不是放宽门槛或增加一轮治理工程：先让组件诊断真正跑起来，再用同一原方程验证低内存提速。**
