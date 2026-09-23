# Task041 Review V7：定位上侧两条响应分歧，完成修复与 5 nm 全流程验证

## 0. 审阅决定与冻结身份

**继续暂停 node1/双路硬件研究和 2 nm。当前不是侧区求解不收敛，而是 full 与 cell-condensed 两种准确 p4 逆支持的有限精度迭代，在上侧两条困难 RHS 上未满足响应强一致性门。本轮必须找到首次差异及其放大环节，作针对性修正；数值资格关闭后，优化实际重复热点并连续推进一场完整 5 nm。不得再用一份“6/8，原因未知”的同类摘要代替定位，也不得靠直接抬高门槛取得通过。**

```text
repository                  = Rookie1234567/MyFEniCS
working_branch              = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                 = 2026-09-23
reviewed_base_SHA           = cb63086bd9f872a8e90f4ac33bd34522593ad1ce
latest_commit               = docs(task041): record V6 transfer and 5nm outcome
previous_review             = review_report_v6.md
latest_response             = response_v9.md
failed_fixed8_runtime_SHA   = a4ccd850faaabbfb13caf98153cfbf65fa4fe0a9
accepted_13p5_runtime_SHA    = a330e30aa87f53aa9b13980551fa87716922e982
transfer_fix_SHA            = b518fb33dbff523bee8c13d31345025f183d40d5
migration_reference_SHA     = 2ba8c891afb9a15095d38f7abc18879fa6a44d95
batch                       = task041_review_v7_causal_fix_and_5nm
response_required           = response_v10.md
execution                   = G0 -> G1 -> G2 -> G3 -> G4 -> G5
hardware                    = socket0/node0, MPI8, one math thread per rank
formal_case                 = W, 5 nm, p6/h4, M480, original Hybrid equation
time_target                 = complete public consumer <= 86400 s
time_policy                 = report target; no automatic 24h kill
ordinary_default            = unchanged; explicit qualified candidate only
master_merge                = NOT_APPROVED
```

本轮消除的 blocker 是“准确凝聚迁移缺少真实困难方向上的因果诊断与最终资格，重复作用净成本未降低”。长期仍服务 0.7 nm、任意非可分三维、约 2 TB；本轮通过不代表这三项最终目标通过。ChatGPT 在此提交分析与执行合同，未在工作站运行诊断，不能把以下候选根因或修复动作写成已经证实。

继承 V6 的物理/ABI/单路隔离、原精度、packet、内存和生命周期要求。本报告明确细化 V6 的“响应强比较失败如何裁决”，并授权 G2 中有限的精度增强及有条件的数值敏感性裁决；不是修改原 PDE 目标、降低阶次或换弱 PC。V5 的硬件先行和 2 nm 个位秒不是前置条件。既往 64 GiB 仅一次 fixed-eight 特许，不自动延续到本轮或完整 consumer。

## 1. 事实、定位边界与此次必须回答的问题

本节据 base 下的 [Response V9](response_v9.md)、[V6 outcome](outcomes/transfer_fix_5nm_24h_v6.md)、[V6 record](outcomes/records/task041_v6_transfer_5nm_24h.json)；旧完整数值 authority 见 [H3/H2中心结果](outcomes/side_balh_transfer_v1.md)。

| 事项 | 已有实值/身份 | 结论边界 |
|---|---|---|
| 旧共享行失败 | 绝对差 1.3116919128020489e-11 > 1e-11；已用实体 trace/closure 构造修复，MPI8 tiny-FE通过 | 与本轮响应差是不同指标；不推定二者同源，不回滚已证明的实体支撑 |
| 13.5 nm cell-condensed | 原五残差、物理量和完整H2数值向量通过 | 总checker被旧资源合同拒绝；不是数值方程失败 |
| 5 nm top column12 | full/condensed均57步；e_x=2.361490171146484e-8，e_A=6.410084067690454e-8 | 超原两项1e-8门；未证明新后端解错 |
| 5 nm top column493 | full/condensed均57步；e_x=2.584982558163933e-8，e_A=7.016739340072887e-8 | 同上；与12是否近似成比例尚待核验 |
| 其余六对 | bottom四对、top310/666两对通过；16次响应均完成，单侧原残差满足1e-2 | 不是128步迭代预算耗尽；全局5nm尚未运行 |
| p4记录 | 每响应最后一次调用的原A4残差通过；condensed最大快照5.23638213224212e-12 | 不是全部p4调用的最大误差；A4残差不是逆作用误差的充分上界 |
| 构造与重复作用 | 两侧构造合计 full1326.091360391 s / condensed327.639773617 s；八响应报告汇总1185.079661994 /1173.609554288 s；均280步 | 构造约4.05倍，响应约1%降时；不是24h资格 |
| 旧四次5nm尝试 | 两次接口接线异常、一次53.221GB cap停止、一次cap64配对失败 | 接口测试不足、内存与数值原因必须分列；不得全部写成solver不收敛 |
| 最新配对资源 | tree/authority峰65674952704 B；专场hard68719476736 B；swap增量0 | 不满足原53221163008 B上限；配对峰不等于新后端单独完整峰 |

**“以前成功、现在失败”必须按身份解释。** 原 H3 是完整原 Hybrid 解对 exact-side authority 的检查；本轮是两种后端各自求到内部1e-2后的响应配对。二者不是同一个命题。此次两后端共用新的传递与相同布局，不能把“full”名称等同于旧 H3 全部代码不变。57步两条超限、49步下侧未超限，既不能证明“restart导致”，也不能排除上侧系统的敏感性。

本轮必答：首次差异发生在共同输入、原算子、p4逆、P/PH、BAL_H、Arnoldi/停止、投影还是checker；通过什么独立证据区分实现错误与数值放大；改变哪一步能可重复地消除或解释差异；准确凝聚的回代收益被哪些重复操作抵消。

## 2. G0：先消化现有证据，不重跑完整八项

启动前读取实际branch/HEAD/worktree、root与适用目录AGENTS、仓库工作原则、task、历次覆盖及本review；检查运行源码与记录对应关系。task/blob和既有review不可改写。环境仍为canonical原生Ubuntu，先激活 `.venv/bin/activate_myfenics_native.sh`，确认每rank complex128、实际PETSc/Basix/MPI/BLAS库和IntType。沿用已开发的rank-NUMA钩子核验task policy和私有计算页，不再开发新的硬件监控体系。

先只读旧 runroot：

```text
results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/
task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/
20260923T115515.717201Z/consumer/numerical_output/
```

读取 `p4_backend_pair_top.json`、`p4_backend_pair_bottom.json`、`p4_backend_pair_audits.jsonl`、`representative_rhs_audits.jsonl`、16份manifest及已保存响应分片；先核hash再复用，不重复hash不可变大数组。实际文件是否含完整iteration history和逐次p4信息逐项说明，没有则标未保存，不从last_solve补造。

离线首先重算 e_x/e_A：写出真实分子、分母、向量空间、取范数范围、owner/slave/ghost处理、端口是否包括、零/近零处理。不得将一个checker中的e_A默认等同另一个。另行保留无歧义诊断：

```math
r_f=g-Dx_f,\quad r_c=g-Dx_c,\quad
\delta x=x_c-x_f,\quad D\delta x=r_f-r_c,\quad
\eta_D=\frac{\lVert D\delta x\rVert_2}{\lVert g\rVert_2}.
```

若需原D作用，归入G1一次构造，不为每个离线字段单独重建求解器。此恒等式的有限精度核验是checker/输入一致性诊断，不是最终真解误差估计。

汇总现有详细timing的字段树。逐行耗时和已有汇总有可重算差异：八行full总1184.6910936099885 s、condensed总1172.9663018830033 s，与报告汇总分别差0.388568384011478/0.6432524049967014 s。核明计时口径，不把任一小差异直接叫算错；统一后再报告速度。不再用“约1%”替代热点分解。

## 3. G1：一条困难响应的共同输入回放，找到第一处分歧

### 3.1 固定对象及成本边界

首个因果对象为 **top formal column12**；保留493作为关联复核，再保留已成功的top310或666为控制。用保存的g计算12与493的最佳复数比例及剩余范数；若接近共线，两条仍都复核，但不得把它们称为独立推广证据。不得改变模式数/材料/网格、换容易RHS或缩放后删除原失败输入。

旧日志足够就离线裁决；不足时允许一次5nm **top-only** 共同布局诊断。重建一份侧区/原D及必要p4因子是实际成本，不承诺恢复已退出进程的因子。原5nmQEP按validator复用，不重跑QEP或旧53h整场。bottom无需陪跑。两种p4因子严格顺序存活，p6 side/layout/RHS保持或用持久映射证明相同；还须核对p4重建后的空间/owner/port对应，不能只证明p6相同。

### 3.2 记录哪些数据才足以定位

按 `side/column/KSP_iteration/PC_call/Q_call` 关联记录，不能只留last_solve：每次p4原physical和增广残差、rhs/solution范数、精化次数、回代数、累计最大值及argmax；原代码已经计算的检查只记录结果，不为每个日志字段重复施加A4。每步保留reported residual，首步、restart边界及末步有限次独立原D残差。若需要超过129条history，修正目前硬编码截断以覆盖实际max_it，不伪造缺失历史。

缺少向量时仅在column12的固定位置流式捕获：第一次PC、30/31/32/33附近和末两步，初始不超过8个PC输入；含对应两次Q的实际输入、P^H后的粗RHS和少量输出。每个文件均绑定实际维度、p6/p4空间、传递策略、owner/约束/端口映射及source。额外RAM最多为预声明的少量全宽工作向量，并仍计入原cap；诊断磁盘初始上限2GiB，按单向量精确字节盘点后决定是否能保存。不能保存全部4800场、allgather全向量、并存两套大因子或每次迭代堆一份历史空间。

当前向量不同，不能把“第k次Q”的两份输出差当作“同输入Q误差”。正确顺序：先从full固定输入集合获得参考输出，流式保存；释放full因子后，用cell_condensed重放**完全相同的字节和物理布局**；自由运行的condensed轨迹另作观察。单个回放节点先查输入与P^H，再查p4恢复、P、完整PC和D。没有发现问题才增加失败区间内至多一轮中点定位，不重复全八项。

### 3.3 原算子与逆的交叉检查

若first difference在p4逆，分别将full和condensed返回的完整FE/port解交给**同一个独立原A4/端口残差实现**；两种后端不可各自只由自己的新代码验自己的答案。核对相同体积分规则、物理材料、端口key/归一化、MPC与符号，区分局部消元矩阵构造误差和回代/恢复误差。允许保存小型关键单元块供高精度离线oracle；不建立新的全局p6因子。

每个共同输入继续要求原A4相对残差<=1e-10，Q差<=1e-11、PC差<=1e-8、P/PH及原action oracle沿V6；超门时不进入“只是迭代敏感”分支。残差通过但逆输出不一致要继续查条件敏感性，不能用1e-10后向指标自动证明前向差<=1e-11。

## 4. G2：按首次差异修正，允许两个有明确依据的稳定化动作

| 证据定位 | 允许的具体修复 | 修后必须证明 |
|---|---|---|
| checker/空间不匹配 | 修分母、物理映射、owner-only范数、rank/port顺序，保留原错误结果 | 保存同一向量的离线oracle与反例，不改生产解 |
| 输入/ghost/对象状态漂移 | 修输入别名、scratch清零、同步、MPC施加次数、销毁时借用关系 | 相同输入交替/重复调用可复现，输入不变，MPI反例被拒绝 |
| p4构造或恢复偏差 | 修局部矩阵/积分、端口符号、一般内部/端口RHS消元、约束与full恢复 | 完整原A4/增广交叉残差、同输入逆/Q和单元oracle全部通过 |
| 原算子/传递偏差 | 修已定位的离散实现；P与P^H同步，保留F1实体支撑资格 | 原p6 action、P/PH点积与Galerkin对照通过，不回退旧泄漏来匹配旧输出 |
| p4有限精度差经迭代放大 | 定向试一次额外同因子残差修正，或固定更严内部p4求解目标作诊断 | 有改动前后、同输入和全步记录；不能靠保存旧答案代替新逆 |
| Krylov数值稳定性 | 按4.1做有界再正交化对照 | 实际KSP策略生效、原残差与repeat通过，并记录新增通信/时间 |

### 4.1 正交化对照必须接入真正的内部KSP

当前 `SideBalancedInverse.__init__` 显式设置FGMRES/right/restart32、UNPRECONDITIONED、零初值和rtol，却未显式设置或审计正交化；该创建路径也没有 `setFromOptions()`。因此，仅在命令行加入GMRES选项可能不生效。

先读取实际PETSc版本与KSP view/受支持getter，再在明确opt-in路径、setUp之前，通过该版本受支持API配置。优先一个 `classical GS + refinement always` 对照；只有它不适用且证据支持时再作一次modified GS对照，二者不是无界扫描。不得为此升级PETSc、手写替代FGMRES或修改未知私有内存。CGS refinement选项只作用于CGS，不能把MGS配同一个flag就称又做了再正交化。[S1–S3]

保留restart32、零初值、最大128步和1e-2正式内部目标；记录实际策略而非仅保存requested string。必要的小Hessenberg/正交性诊断只在现有安全接口可取时启用，不为取内部基向量另造大框架。策略修复如获证据支持可用于本轮显式candidate，必须重新验证5nm repeat和固定响应，并把变化归为数值稳定化而非原运算逐位等价。

### 4.2 p4与侧区精度诊断不扩散成全部列高精度计算

若共同输入定位到p4舍入，可在column12上至多增加两次同因子残差修正，并验证是否有效减小原残差及Q差。保留真正原A4，不以新凝聚算子自检替代。全体精化数和耗时均入账；若确实需要成为正式策略，先选单一、有证据的策略，不能按column编号特判。原p4门不放宽，也不无条件追加到所有Q调用。

若逆/PC已经通过而只能检验终止敏感性，允许对column12及关联复核使用现有 `(max_it=256, rtol=1e-4)` 诊断配置；不把这当正式所有1920响应的新标准，也不继续收紧到无法支付的精度。结果需区分新旧轨迹差、真实残差和最终误差，不能仅凭更严容差就宣称原因已定。

### 4.3 两条合法收口路径：既不盲目放宽，也不无限要求近似解逐位一致

**路径A：严格配对修复。** 已定位并修复实现/稳定性问题；固定八项沿原e_x/e_A<=1e-8通过，原action/p4/PC/repeat及资源门通过，直接进入G3/G4。

**路径B：有限精度敏感性被解释后的有条件全流程验证。** 不改写旧强配对结果；仅在以下证据全部齐备时，本review允许将跨后端有限容差响应强配对降为保留的诊断，获得 `RESPONSE_SENSITIVE_FULL_VALIDATION_ADMITTED`，而不是生产PASS：

1. 共同输入的原D/A4、完整p4逆、Q、BAL_H、P/PH与端口全部满足上面的原动作门，输入/映射不变，未发现实际实现偏差；不是只有两份最终残差<=1e-2。
2. 至少一项有界干预（再正交化、原残差精化或已定位的舍入路径校正）可重复地改变该差异，且与捕获的首处分歧及后续放大一致。若仍无可解释因果，不能选本路径。
3. 同一后端的重复/交替调用与5nm原模态repeat门通过；保存first/second小模态样本、上下侧及输入身份。跨后端敏感性不能用来豁免同后端工作区漂移或原repeat失败。
4. 报告原e_x/e_A、直接计算的模态投影差、实际分母和全部失败项，禁止把阈值从1e-8直接换成刚好容纳7.02e-8的数，禁止用“大概只是roundoff”替代证据。
5. 仅授权一场以**不变原Hybrid action/RHS**为算子的完整5nm验证，最终五残差、E/H、RTA/体吸收/衍射/资源门全部照旧。FGMRES允许非精确PC不等于必收敛；全场通过以前，不能把本路径标成精度证明。[S1,S4]

本条是对辅助响应诊断用途的明确审阅裁决，不降低p4、原PDE或物理精度，不自动适用2nm/其他模型。若完整结果失败，保存并退出，不继续调门槛；若完整结果通过，仍报告跨后端响应敏感性及资格范围。未经本节证据不得跳过G2。

## 5. G3：查清为什么构造快4倍、迭代仅快约1%，再做最多两组等价加速

先从已保存的逐RHS detail timing产生净成本表：`q_factor_solve_seconds`、`q_p4_storage_rhs_reduction_seconds`、`q_p4_solution_recovery_seconds`、`q_a4_residual_refinement_seconds`、其内嵌physical_action时间、P/PH、A6/H6、侧区D、MPI/正交化。每项列调用次数和计时范围，**不要把父子inclusive时间或不同操作的max-rank相加**。未测项不得用零填充。

下面是本次源码实际看见的候选，不是已测到的主瓶颈；先用旧日志或G1短窗口决定先后：

| 位置 | 可避免的重复工作候选 | 允许的等价改造及验证 |
|---|---|---|
| `P4CellCondensedInverse._reduce_storage_rhs` | 已用缓存的trace-from-interior矩阵形成trace correction，但仍先计算xig；在无内部端口贡献时xig随后可能未使用 | 只在端口内项实际需要时执行该局部LU；不跳过任何非零端口、FE RHS或恢复；用含/不含端口及非零内部RHS oracle验证 |
| `_active_solution_map` / `_exchange_active_values` | 每次遍历固定cell/trace、unique/searchsort、Python列表alltoall、返回字典 | 将布局不变的请求与owner路由在setup构建一次，数值按有界原生buffer交换；新路由替换旧常驻结构，不增全局gather；empty-owner/ghost/MPC反例必测 |
| 完整p4包装及残差 | 每次创建多份Vec、数组与端口投影；原A4动作占比未明 | 复用严格所有权的scratch，保留全部原残差检查；预打包只能缓存不变数据，输入每次正确更新 |
| A6/A4/H6与DtN | 通用装配、逐单元/逐mode小操作可能主导 | 仅按实测最大热点做编译/张量/有界批量作用；不降低积分、模式、complex128；独立原action oracle验证 |

最多两组真正进入真实5nm评估的性能修改；不因一个实现局部更快就无限扩展到新框架。G2稳定化修复不计作借口继续扫描PC。禁止GPU/node1/MPI16/神经网络/recycling/弱Schur/APF/全局p6LU/BLR/OOC/混合精度及改变物理M/p/h。

同输入下必须比较净Q、完整BAL_H及整条side.apply，不只比较局部MatSolve。若新增缩减/恢复抵消回代收益，明确修改哪一项以及净收益；若最终仍约1%，如实报告并进入已授权的一场完整运行检验总成本，而不是再把构造倍数当总加速。

## 6. G4：完善正式调用链与内存准入，然后交付完整5nm

### 6.1 前两次接口事故不得在大模型上重现

用小型真实FE和精简mock共同覆盖**正式调用方**：创建/metadata、full与condensed的FE向量/原action访问、一般port RHS、异常时audit、destroy前后diagnostics、返回生命周期、最终清理。测试不能强迫新后端伪造 `.matrix` 属性指向不等价矩阵，应使用共同的物理action/向量接口。返回记录包含调用方实际需要的释放诊断；已销毁对象不得再读悬空指针。

修正旧H2 checker与V6/V7资源ledger/time-policy/继承producer的合同适配，只重读原raw完成；保留旧checker失败与新的独立复核。`Full3D secondary not_run`仍不是pass。不能为让总check变绿重跑原QEP或把缺失producer资源证据填成真。普通失败/预期组件退出/完整生产失败应分开分类，finalizer始终执行且保留真实错误。

### 6.2 内存保持原合同，不继承一次性cap64

正式上限仍为 `53221163008 B`，host reserve沿用 `412316860416 B` 并另外检查node0真实可用内存；swap=0、一次一个heavy、无OOC。如果当前profile有更严限制沿用更严者。上一场 `68719476736 B` 只属于那一次授权，本review不把它变成新默认。

优先top-only诊断；后端比较不把两个侧区、两个因子、整套对照数组长期重叠。用阶段所有权表分清原side数据、p4组装、因子、recovery、P/H6、scratch、allocator保留和page cache。允许消除重复保存/不必要重叠，不能通过删除原checker、关监测或提前销毁后端依赖矩阵省内存。

G2闭合后，单独的新后端双侧构造资格与配对流程峰值分开测；将该准入嵌入正式consumer并进入同一场后续计算，避免为证明setup再重建一次。超cap即受控停止，不自行再次提高；明确其为资源blocker，不归数值失败。不把未知native内存随意相减或以PSS代替既有RSS上限。

### 6.3 完整5nm按原方程验收

保留V6的W折射率、几何、1°入射、p6/h4/M480、原外部完整通道与传播/traction、MPI8×1。新dat显式声明cell_condensed及已资格的稳定/性能profile，使用 `python scripts/run_case.py <case.dat>` 及既有service，实读bottom/top backend防止silent full fallback。QEP用**对应5nm**的合格packet，producer/consumer source分开绑定，不能用2nm packet。

13.5nm已有完整数值通过；只在本轮数学相关源码/运行配置变化影响它时重跑一次，否则复用原数值记录并补合同复核。固定八RHS中不受影响且hash/布局充分的结果可复用，受影响项定向复验；不为日志字段反复重跑全八项。通过G2、完整调用链与资源准入后，连续执行一场完整5nm，不再等待每个小步骤的人为重复批准。

| 最终Gate | 固定要求 |
|---|---|
| reported/global/bottom/top/modal原真实残差 | 各<=5e-9；独立重算，不只看KSP监视值 |
| projection / 双侧traction / external-q | <=1e-8 / <=1e-8 / <=1e-10 |
| 每次p4原physical及增广残差 | <=1e-10；全调用统计、refinement与回代数完整 |
| R/T/A_balance/A_volume对原exact-side authority | 各绝对差<=1e-8 |
| selected complex E/H | 原relative L2<=1e-6，固定物理键，无phase fit |
| canonical trace/full场 | 原relative<=1e-5，映射已证实 |
| 显著衍射级复幅值/功率 | 原relative<=1e-6；全部弱级也输出 |
| normal flux | 原relative<=1e-4 |
| 守恒与体吸收一致性 | 原两项abs<=1e-5 |
| RSS、node0、swap、退出/清理 | 本节及V6原合同；release-before-recovery且原场恢复通过 |

Schur同后端repeat门仍是原门，不把G2跨后端强配对的有条件资格扩展为repeat豁免。失败前保存小的first/second模态样本，不重新丢失上下侧/column信息。无最终合格解时不产生official RTA成功状态。

## 7. 24小时是交付目标，结果不得再只停留在局部倍数

```math
T_{\mathrm{consumer}}=T_{\mathrm{public\ start\ to\ completed\ finalizer}},\qquad
T_{\mathrm{target}}=86400\ \mathrm{s}.
```

计入packet load、preflight/setup、Schur、outer、全部核验、场恢复与清理；worker、历史producer成本与fresh-equivalent分列。旧53.24h只有worker/历史口径，不能对不同口径声称严格2.22倍软件收益。

5nm的1920次正式侧区响应，即使忽略setup/outer，也只允许平均45s/响应。现有8项是有意挑选，不能把其平均当无偏ETA，更不能把新后端的4.19s/步直接当24h必达。G3需依据全部已有模态分布、慢样本与分阶段成本做带不确定性的预测，仅用于定位热点；不要求预测必然低于24h才准许一次实测。

到24h若仍正常推进且数值/资源安全，记录未达时间目标及阶段/列数，不强杀、不归零重来；继续同一场以取得完整结果。数值/资源失败、用户中止或真实死锁仍停止。只授权一个完整成功目标运行；若因有证据的局部实现事故早停，最多一次修复后受影响重试，全部费用保留。

## 8. G5交付、最小提交与停止规则

建议复用现有框架新增一个中心报告 `outcomes/causal_fix_5nm_v7.md`、一个机器记录 `outcomes/records/task041_v7_causal_fix_5nm.json` 及 `response_v10.md`。原始向量和详细日志留ignored目录，Git只保留compact与hash。同步summary/test_summary、development_progress和development_model_registry。不可改写旧review/task/失败，禁止amend/强推/master合并；正式运行绑定clean source，文档提交和实际运行SHA分开。

提交顺序：离线定位与最小复现接线；根因/稳定性修复及反例；至多两组热点优化与完整调用链；最终clean-source资格；完整5nm结果及Response V10。各阶段内部可按AGENTS双窗口审核，但数学/资源条件已满足时不要求用户逐项重新授权。

Response V10必须用表格回答：

| 必答问题 | 不接受的替代说法 |
|---|---|
| 首次分歧在哪个调用/输入/模块，证据文件与前后值是什么 | 仅“top难收敛”或“可能roundoff” |
| 根因如何验证，改了什么，原失败输入修后如何 | 只改阈值、换RHS或又一次6/8 |
| 走G2路径A还是B，原强配对与新裁决分别是什么 | 将旧失败覆盖为pass |
| Q/PC/p4全调用与repeat是否通过 | 只给每响应最后一次p4快照 |
| 凝聚降低的回代成本与新增恢复/检查成本各多少 | 只报setup4倍 |
| 新候选单独峰值与配对峰值分别是多少 | 把专场64GiB自动变成正式预算 |
| 完整5nm的五残差、E/H、RTA/吸收/衍射和wall | 仅tiny-FE或八RHS成功 |
| 24h是否达成，若未达是哪项真实成本 | 预测或局部kernel倍数 |

若根因仍不闭合，至少交付已冻结的共同输入、首处分歧/排除结果及下一项唯一缺失证据，不能再次只返回相同汇总。真正实现缺陷/原action失败未修复、packet不合格、无法隔离node0或资源越界时不得为拿结果继续；但纯粹没有达到时间目标不阻止记录完整数值结果。完成后推送并停止等待ChatGPT最终审阅。

## 9. 审阅依据与技术参考

本次读取base的root AGENTS、task、当前目录清单、Response V9与V6记录/summary及下列相关代码；已读仓库原则、docs/AGENTS和Markdown规则继续适用。V6本地上传副本的Git blob与远端目录 `e7f60fb7f95efa2199e04c49a5f6fe39a39f162c` 对应；task无新增补充文件，本报告不替代Codex启动时完整权威读取。

- `src/solvers/physical_balanced_side_inverse.py`：内部KSP构造/审计、history截断、Q内两后端接口、现有详细计时。
- `src/solvers/physical_balanced_physical_operator.py`：共同物理A4、full/condensed完整逆、原残差与有限精化；既有原始源码审阅不等于已运行验证。
- `src/solvers/p4_cell_condensed_inverse.py`：每次RHS缩减、固定trace请求重复建立、Python alltoall与恢复。
- `benchmarks/task041_exact_side_workflow.py` 与 `task041_balh_workflow.py`：Codex在G0继续核对实际配对指标、返回协议、正式调用链及计费边界，不把历史描述当当前实现。
- [S1：PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：右预条件和非线性/不精确PC支持，不保证任意PC的收敛。
- [S2：PETSc classical Gram-Schmidt](https://petsc.org/release/manualpages/KSP/KSPGMRESClassicalGramSchmidtOrthogonalization/)：再正交化的稳定性与成本。
- [S3：PETSc CGS refinement类型](https://petsc.org/main/manualpages/KSP/KSPGMRESCGSRefinementType/)：never/ifneeded/always语义，以工作站实际版本API为准。
- [S4：PETSc KSP tolerances](https://petsc.org/release/manualpages/KSP/KSPSetTolerances/)：容差约束残差，不直接约束相对于真解的误差。

外部资料于2026-09-23核对，仅解释机制；不授权升级ABI，也不把当前release文档版本当工作站已安装版本。本文采用GitHub math围栏，需静态和可用渲染检查；不能核验GitHub视觉页面时如实注明。此次仅文档审阅，未完成工作站修复或宣称24h通过。
