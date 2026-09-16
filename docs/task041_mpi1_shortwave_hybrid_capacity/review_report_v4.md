# Task041 Review V4：共同布局下验证传递优化，关闭响应配对阻塞

## 0. 决策、范围与身份

**接受 V3 两场分侧组件计算均完成八项响应、出现约 25.1% apply 提速信号且观测 RSS 未上涨的事实；保留旧配对的 `PAIRING_IDENTITY_UNPROVEN`。本轮授权一次共同布局的有限验证：同一侧区、同一原算子、同一 p4 因子、同一 RHS，顺序调用 legacy 与 optimized 实现，直接比较。先把“是否计算相同响应”判清，不重跑完整 Schur，不另造一套通用自由度映射框架。**

```text
repository                  = Rookie1234567/MyFEniCS
working_branch              = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                 = 2026-09-16
reviewed_HEAD / base_SHA     = 59dd5035c9f4ec75949358aed392a8600d9f9d83
legacy_sequential_source    = 3ee452ac0adc0c3c88b9610b6446e93a3c02444a
optimized_source            = 376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab
previous_review / response  = review_report_v3.md / response_v4.md
existing_profile            = task041_schur_speed_v2
existing_scope              = representative_rhs
new comparison_mode         = common_layout_equivalence (explicit opt-in)
side_setup_schedule         = sequential_component
response_required           = response_v5.md
formal worker               = MPI8, one mathematical thread per rank
master_merge                = NOT_APPROVED
```

本轮解决的 blocker 是低内存 Hybrid 侧区加速的**等价性证据缺失**，不是重新证明 5 nm 的完整 Maxwell 解。它服务于 2 TB 内求解 0.7 nm 任意三维的长期目标，但仍属于 Hybrid 特定结构加速路线，不替代通用 Full3D。

本文新增 V4，因为 V3 已被 Response V4 正式回应；不覆盖历史文件。本文明确覆盖 V2/V3 中本轮的配对方式及自动推进顺序：完成本次共同布局验证和已有内存证据分析后，提交 Response V5 并停止。本轮不自动启动新的 13.5 nm 全场、5 nm 双侧 setup/full consumer、1920 列 Schur、QEP 或更短波长。其他物理、数值、安全与 Git 约束继续沿用 V2/V3。ChatGPT 只提交本 review；Codex 负责最小实现、测试与计算。

## 1. 审阅依据及结论边界

依据：[Response V4](response_v4.md)、[setup/recovery](outcomes/setup_recovery_v3.md)、[compact](outcomes/records/task041_setup_recovery_v3.json)、[summary](outcomes/summary.md)、[test summary](outcomes/test_summary.md)；旧停止与执行边界见 [V2](review_report_v2.md)、[V3](review_report_v3.md)。本页数值是这些既有证据的摘录，不是新运行结果。

| 既有事实 | 结果及口径 |
|---|---|
| 模型 | 5 nm / p6h4 / M480 / MPI8；bottom、top 各四个固定 RHS |
| own solve | 两场各 8/8；每项 reason=2、原侧区 true residual <=1e-2；各场总内部迭代280、p4回代560 |
| 八项 apply | baseline 1680.27495998214 s；optimized 1258.8479048048612 s；比值0.7491916113647505，约25.08%为 derived |
| 完整组件 service | 4015.539370124 s 对3630.563676387 s；不是完整 Hybrid consumer |
| 同时进程树 RSS | baseline 51975606272 B；optimized 51796770816 B；两场均低于53221163008 B cap，正常收尾、job swap=0 |
| 基本传递检查 | R2e 小 FE serial/MPI2 的 P、PH relative均为0；不替代 MPI8 响应对照 |
| 缺失证据 | 两场132300凝聚行没有跨运行稳定物理行映射，且 ownership ranges 不同 |
| 原始数组差 | 未对齐 RHS、response 按位置比较约sqrt(2)，仅为 diagnostic；既非数值失败也非等价通过 |
| 未关闭的另一问题 | 旧双侧 S1f 构造超cap；分侧成功不能证明双侧容量 |

本轮成功只新增“同一实际布局上的优化等价性”证据，不追认旧两场的缺失映射。也不能把旧约25%提升从带分区差异的实测信号升级为确定的独立因果效果，或把约170.55 MiB的单次观测下降称为稳定内存节省。

## 2. 为什么采用共同布局，而不是给旧数组重新排序

同一个物理解可以因网格分区、自由度排列及方向表示不同而生成不同顺序的系数数组。现有 artifacts 没有保留足够信息去恢复两场132300行的对应关系，不能靠相同长度、范数、input SHA、ownership range或事后重建一张新网格代替该证据。禁止按响应值匹配、排序坐标后硬配对、全局相位拟合或反复试排列直到差异变小。

短期方案：每侧只构建一次 side system/adapter；不改 mesh、MPC、凝聚映射、原算子和因子，生成一次 RHS；只切换 A1/A2 的执行实现。这样两份输出产生于同一内存中未变的自由度空间，逐项比较有直接意义。代价是一轮每个 RHS 两次求解，但不重复 setup、不同时保留两套 PC。

长期跨 fresh run 可复现性仍需要持久化的 mesh/dofmap/约束映射或稳定实体—方向—基函数键；本轮不开发通用 canonicalization。Nédélec 自由度不能普遍当成“一个坐标一个值”，方向变换也不总是简单交换。本轮不以这项长期工作未完成阻挡已经明确同布局的比较。

## 3. 冻结输入与实际执行的两条路径

沿用 V3 已绑定 input、physical/resolved、packet 和八项清单，不改变材料名称或数值。

```text
input = input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat
input SHA256    = 9e77be901d54a8eb6d4f090588dec26c4913facd7c16c53fb46c0025eb31adb2
physical SHA256 = 65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4
packet manifest = 306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f
RHS manifest    = outcomes/records/task041_representative_rhs_v1.json
RHS SHA256      = fb68011ed3e55861c59455d082be549cdd9f6c2d5a569015cf88bdc739f5636a
bottom columns  = 207, 15, 671, 493 (ordinal 0..3)
top columns     = 310, 12, 666, 493 (ordinal 4..7)
inner          = right FGMRES32 / max_it128 / rtol1e-2 / zero initial guess
p4             = original accurate physical inverse / residual<=1e-10 / original refinement
BAL_H          = original balance gate1e-8
p6/global LU   = 0/0
QEP calls      = 0
```

RHS 仍由原 `modal_coupling_action(e_column)` 生成，只生成一次供两条路径读取，不重复乘传播因子。暂存/散列只读 owned entries；ghost/MPC处理保持原语义。

| variant | 必须真正调用的实现 |
|---|---|
| legacy | 原 `_resolve_owner_candidates`；原 `matrix.conj().T @ masked_values` |
| optimized | `_resolve_owner_candidates_batched`；原已提交的 `_apply_conjugate_transpose_vector` |

两者均保持原数据流、积分、A6/A4、H6、J/JH、MPC、原独立检查器和 factor。对照 legacy 的函数内容应与冻结 legacy source 核对；不复制一个已经被优化的函数并命名为 legacy。当前性能 profile 在新代码上自动选 optimized，故不能只运行同一 profile 两遍、改输出标签。

复用 `physical_balanced_same_mesh_transfer.py` 与 `physical_balanced_side_inverse.py` 增加最小、受校验的 variant 选择。保留原 `representative_rhs` scope及冻结八项manifest，在原runner/service上显式增加 `comparison_mode=common_layout_equivalence`，不把原manifest的scope或hash改掉。只扩展此诊断所需的参数校验/记录，不复制巨型benchmark，不使用运行中全局monkey-patch或隐藏环境开关。variant、source、scope/mode进入manifest和每条audit；所有rank在两次KSPSolve之间同步切换，绝不在一次求解中途切换；异常后恢复原profile并清理拥有的对象。ordinary/default与原full consumer行为不变。

## 4. 执行顺序与共同布局证据

### C0：复用旧账，核对最小改动

读取根与相关目录AGENTS、工作原则、task、V1–V4、Response V4和compact。确认 branch/HEAD/upstream/worktree、native activation、complex128/int类型、实际import路径、MPI8×1/CPU0–7、packet/hash、磁盘、reserve和heavy lock。HEAD前进先检查差异，不reset/覆盖。不把远端文档提交SHA当运行源码SHA。

只读旧原始文件一次，复用已有耗时与内存统计；不得继续尝试从缺失映射的旧数组制造等价PASS。若恰有已保存且可证明的一对一映射可立即使用，可补充独立结果；不为查找它开启无界考古。

### C1：轻量回归先通过

在真实小FE与必要MPI2上检验：两种variant确实走不同原函数；共享对象/因子身份不变；legacy→optimized→legacy及反向切换无残留；输入、方向、Floquet、slave/ghost与空owner检查保留；相异layout或相异RHS会被比较器拒绝。原native action与独立oracle不得同步改写。

共享KSP每次都从零解开始，不使用KSPGuess/recycling或上一条响应。当前 `SideBalancedInverse.apply` 已清零target、重置每RHS计时并保留累计计数，优先沿用；检查 `getInitialGuessNonzero` 与真正求解设置。不为了重置计数销毁/重分解p4；不把重用工作空间误当作允许重用上一条解。

### C2：一次MPI8共同布局组件运行

```text
公共准备一次，保持原side systems与coupling
→ bottom adapter只构建一次，完成共同布局登记及基本动作对照
→ bottom四项：每项生成一次RHS；legacy和optimized各solve一次；比较/流式保存
→ bottom释放，factor/KSP归零，borrowed action/RHS未破坏
→ top按相同规则执行四项
→ 保存完整诊断终态并正常退出
```

主响应共16次KSPSolve，仍是原八个RHS各两条路径；原admission和基本动作对照另计，不能伪报总调用只有16。每侧至多一个adapter、一个p4 factor和一个内部KSP存活；全run累计p4 factor创建2次。不得同时构建legacy/optimized两套对象，不重建因子或H6谱窗来切换实现。

每项比较采用确定的交错次序：偶数ordinal先legacy，奇数先optimized；同一RHS的两次target均清零。此举只减少顺序偏向，不声称消除了缓存/温度/分区等性能影响。不得为追求漂亮时间比重抽顺序或重复整轮。

**布局身份不仅是写相同字符串。** 为每侧生成run-scoped `layout_instance_id`，在构建后登记并在每对前后检查：同一live mesh、dofmaps、方向/排列数据、MPC约束/权重、`owned_active_original_dofs`、side A、communicator/ownership和p4 factor；不重建或改变这些对象。使用已有数组的分rank流式摘要与runtime对象身份/创建计数证明未变；摘要不复制全局大数组，进程地址不当跨运行物理键。

每个ordinal生成一条pair记录，含legacy/optimized两份独立audit及输出路径，共八pair、16个主响应；checker只在本mode下识别该数量，不改旧“一项一次apply”的语义，也不能让两个variant覆盖同一shard。输出明确 `pairing_scope=same_live_layout`，两条variant绑定同一run、side、layout epoch与RHS owned hash；每次前后验证输入不变。manifest保留source及legacy/optimized函数版本，布局摘要每侧保存一次并引用，不按每RHS重复大块数据。离线checker只能在这些共同布局条件闭合后逐owned row比较；这不是为旧两场补写物理映射。

### C3：分层等价检查，避免错误的统一阈值

先在每侧同一实际布局上，用少量非零复向量检查P与PH，再用该侧一个固定RHS检查完整BAL_H PC作用。输入包括原真实RHS的JH提升及一个有界非零p4向量；逐组释放scratch，不把admission全部中间量常驻。小FE交替/线性检查已完成者不在MPI8重复大扫描。

| 层级 | 验收及未通过时的处理 |
|---|---|
| 同布局/同RHS | 必须通过；物理对象、映射、RHS变动即`PAIRING_SETUP_FAILURE`，不能继续位置比较 |
| P/PH线性作用 | old/new相对差<=1e-11；原更严门限沿用；独立dual/orientation/MPC检查保留 |
| 完整BAL_H PC作用 | old/new相对差<=1e-8且双方原balance、p4检查通过；这是同布局诊断门，不代替外层精度 |
| 每个p4 solve | 原physical A4残差<=1e-10，原精化策略和真残差检查不变 |
| 每条侧区响应 | 原A_s显式残差<=1e-2、reason>0、有限；零初值和128步上限不变 |
| 同布局响应比较 | 报告系数差、原算子作用于差向量的范数、残差向量差、迭代历史及reason，见下述判定 |

对同一RHS的两份响应，计算：

```math
e_x=\frac{\|x_o-x_l\|_2}{\max(\|x_o\|_2,\|x_l\|_2)},\qquad
e_A=\frac{\|A_s(x_o-x_l)\|_2}{\|b\|_2}.
```

非零输入使用真实范数作分母；近零的传播响应同样保留，例如旧样本有约1e-36量级。禁止用固定1e-30分母掩盖相对差。需要时仅对比较范数使用共同的安全缩放并报告绝对差，原solve的RHS和容差不变；双方严格为零则独立处理，不除零、不删掉该样本。不得相位拟合。

**不把近似KSP响应差强制设为1e-11。** 本轮预先采用 `e_x<=1e-8` 且 `e_A<=1e-8` 作为无需追加求解即可确认的强一致性诊断门，另须上表全部通过。它是新诊断的保守判定条件，不是两个残差各<=1e-2必然推出的数学结论，也不改变原PDE容差。

若共同布局已闭合、基本作用通过，但响应差超过此诊断门，记录首次差异、终止步数/轨迹与原A_s残差，分类为`RESPONSE_SENSITIVITY_UNRESOLVED`，而不是继续写“没有行映射”，也不直接判整套BAL_H失败。用已保存信息区分阈值触发敏感性与真正实现差异；不现场放宽门限、收紧原容差反复试验或增加完整求解。若基本action/原残差检查失败，则保留明确的`ACTION_EQUIVALENCE_FAIL`/`NUMERICAL_GATE_FAIL`及具体字段。一次局部实现错误可按第7节有限修复。

### C4：形成后续决策所需结论后停止

八项及动作对照都通过，可将本次新证据分类为`COMMON_LAYOUT_EQUIVALENCE_PASS`，关闭“无法判断当前两种实现在同一布局上是否等价”的阻塞。旧两场仍保持`PAIRING_IDENTITY_UNPROVEN`，旧性能数字仍为带分区差异的观测；无需恢复不存在的旧映射才允许后续研究。

顺带用既有及本次setup/release库存做一张**双侧构造的离线重叠表**：公共数据、bottom retained、top各子阶段临时量、p4源矩阵/因子、transfer/H6、allocator/native unknown。保留前后样本的时间口径；不把阶段RSS差或对象nbytes直接称为精确归因。不为填表另跑双侧setup。

有证据的下一候选仍是构造释放与A6/A4重复作用；本轮只给量化建议，不同时实现新热点或p4凝聚。旧双侧超cap不被分侧结果抵消；任何未来双侧验证必须先有明确释放方案及原cap下准入。本轮完成后提交Response V5，下一次review再决定是否恢复V3的13.5nm/完整5nm链，避免将身份修复和昂贵全流程放进同一个未审变量。

## 5. 内存、计时与资源安全

**不增加求解器常驻数据，不提高原严格cap。** 本次共同布局诊断同样使用同时专属进程树RSS上限53221163008 B（warning为90%，其他更严安全线优先）；包括service、public、MPI、编译、检查和收尾。job swap=0、reserve和有效cgroup要求不变。一台工作站只运行一个heavy；另有正在运行的Full3D时只读/编辑，标`BLOCKED_BY_ACTIVE_HEAVY_JOB`，不等待循环、不终止邻任务。

一份p4因子、一个H6和一套transfer work供两variant共享；不创建矩阵副本、第二套Krylov空间或全FE×mode缓存。每次最多保留一份active-trace参照输出，比较的短寿命差分向量尽量复用现有scratch；保存结果后释放，不将全部八项堆在RAM。以132300行complex128为例，一份向量的纯载荷2116800 B，是derived，不是PETSc/native总RSS。所有比较scratch纳入cap、单列库存，不凭“只有几MiB”豁免。

本轮的诊断峰值与求解器/variant的增量分别列出。低于cap不自动等于证明优化内存不增；高于旧48.24 GiB观测也不能隐藏。新增诊断开销不能进入ordinary PC常驻；无法支付或出现cap超限则受控停止，不减少监控/原精度检查。

保留原两场fresh-service wall和内存，不重跑它们。本次时间只报共同layout中的顺序诊断及分项，构造只收费一次，不能对每个variant重复计费；同进程结果不能称冷启动独立性能对照，不能将节省setup包装为算法提速。旧25.08%与本次等价证据可以并列支持继续优化，但不合并成严格fresh-layout三项全PASS。basic checks、normal-close监控只复用并最小扩展，不开发新服务框架。

## 6. 测试、证据与可复现输出

最小相关测试包括：variant正确接线与恢复；同layout旧/新/旧一致；错layout和错RHS负例；输入不变；p4因子创建计数不变；跨侧释放后borrowed对象可用；异常清理；复杂方向/Floquet/MPI2空owner。只跑受影响focused suites、scoped Ruff/compileall/文档合同；不为无关文档重跑heavy/full suite，不把历史测试数量搬成最终source的测试通过。

复用现有rank-sharded packet writer，保存每项共同RHS、两份response及必要诊断数组；每侧布局证据只写一次。允许checker按相同rank/ownership流式比较，禁止全向量allgather；scalar范数按MPI求和/规范范数处理。所有原A_s残差及p4检查由未改oracle重算。摘要不能只存布尔PASS，至少有每项reason/iterations、残差、e_x/e_A、linear action差、source/RHS/layout哈希、factor counts、时间和RSS覆盖。

正常/受控终态分别保留；不改旧run_summary、事故、旧pairing报告和raw hash。新的run metadata不能写成“修复了旧响应”。报告的summary顶部先给最新状态，再保留旧历史，避免读者再次把旧0/8当新结果。

## 7. 预算、提交与停止条件

继续原V2唯一ledger。Response V4提交时共享S0/S1/S3已用11145.609111173893325 s、余额10454.390888826106675 s，执行前读取实际余额；不清零、不挪用未运行S2/S4预算。本轮C0–C4全部计入共享21600 s以及整批201600 s旧合同。预算数字是投入上限，不是预计耗时。

授权一场共同布局MPI8组件运行，八项各两次主响应，两个侧区各只setup一次。轻量测试通过并按已有耗时核算余额后启动；余额不足即`BLOCKED_BY_REMAINING_BUDGET`。仅明确的局部实现错误允许一次受影响阶段修复复测，仍在剩余预算内；数值敏感性、资源超限或无收益不自动重试。不做额外完整baseline/optimized配对，不扫参数。

完成或触及身份/ABI、原精度、资源、监控失鲜、预算等真实Gate就收口。所有正常步骤在本范围内连续推进，不逐小步重复询问用户；现有双窗口协作规则若被用户启用，内部执行仍由主控按仓库规则批准。

```text
新增交付：
docs/task041_mpi1_shortwave_hybrid_capacity/response_v5.md
docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/common_layout_equivalence_v4.md
docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_common_layout_equivalence_v4.json

同步更新：
outcomes/summary.md、outcomes/test_summary.md
docs/development_progress.md、docs/development_model_registry.md
```

普通commit顺序：最小variant/共同布局接线及测试；clean source下有限运行；结果与Response V5。实际run SHA与文档HEAD分开，回读验证push；不amend、不强推、不merge master、不整体迁移donor。大矩阵、因子、全场和完整资源时间线留在ignored results。

最终同时报告：新共同布局身份是否闭合、实际动作与响应是否一致、精度是否保持、新增诊断内存、旧性能证据的限制、双侧内存仍缺什么，以及未运行项。成功状态仅`COMMON_LAYOUT_EQUIVALENCE_PASS`；不同时宣布`FULL_CONSUMER_SPEEDUP_MEMORY_NONINCREASE`、0.7nm或任意三维通过。

## 8. 代码与方法参照

本次具体接线依据：`physical_balanced_side_inverse.py::apply` 在每次调用清零target并记录原A_s真残差；`_apply_balanced_pc`经同一JH/BAL_H/J；same-mesh transfer已有legacy/optimized两个分支；`_run_task041_balh_candidate_setup`已有sequential_component、生命周期与固定RHS入口。优先在这些现有接口最小扩展，不增建并行系统。

官方语义核对：[PETSc KSPSetInitialGuessNonzero](https://petsc.org/release/manualpages/KSP/KSPSetInitialGuessNonzero/)说明零初值语义；[KSPSolve](https://petsc.org/release/manualpages/KSP/KSPSolve/)要求独立检查converged reason，调用返回不等于数值收敛；[Basix 0.10 DOF transformations](https://docs.fenicsproject.org/basix/v0.10.0/python/demo/demo_dof_transformations.py.html)解释方向/置换与一般自由度变换。在线PETSc版本不替代本机已资格化ABI，本轮不升级环境。

**核心判断：保留有效的性能进展，用一份真实布局和一份因子完成有意义的old/new比较；不为缺失的旧编号证据无限补流程，也不借此放宽内存或精度。**
