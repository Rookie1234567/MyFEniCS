# Review V1：定位G0恢复一致性误差，完成0.7 nm双凝聚首批验证

## 0. 本轮决策、身份与权限

**要消除的blocker：真实0.7 nm、三维非可分G0已进入p6迭代，但凝聚表示与独立原A6残差在第8步出现约1e-9的向量差；现有固定identity门槛提前停止，尚无完整G0/G1场。先确认两条计算路径是否实现了同一方程，再完成首批工程结果，不新增PC路线。**

本review依据用户“写个review report，并附Codex执行文字”的本轮指令编写。它是同一任务的定向续作要求：保留旧结果，恢复下文明确的运行许可；不是重分类attempt4，也不改变工作站或普通默认。

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task40extra_0p7nm_engineering
review_base_SHA         = 5ae274c748eaa030ddcc1eca5437ac58c61be3ca
last_run_source_SHA     = de44f5bb4da48cd076df2b295ef6fe08b83d52fa
review_file             = docs/task40extra_0p7nm_engineering/review_report_v1.md
response_required       = response_v2.md
execution               = R0 -> R1 -> R2/R3 -> qualified R4 -> R5
machine                 = 笔记本已资格化WSL/Linux；MPI1/数学线程1
workstation_change      = NOT_AUTHORIZED
ordinary_default_change = NOT_APPROVED
master_merge            = NOT_APPROVED
```

读取根与目录AGENTS、仓库工作原则、[task.md](task.md)、[Response V1](response_v1.md)、[summary](outcomes/summary.md)、[attempt4记录](outcomes/records/g0_attempt4_identity_gate_stop.json)及[旧续作授权](outcomes/records/g0_user_authorized_continuation_v1.json)。本目录此前没有review文件，本报告从V1开始，不沿用Task39的review编号。若HEAD新增合法提交，先读差异，不reset或重写历史。

本review仅在以下事项上补充/取代旧合同：本轮有条件的G0/G1续算许可、数值误差已经定位后的显式identity工程预算、必要时调整唯一G0直接参考的顺序、保存首个停止原因。其余物理、离散、原A6、完整A4检查和资源合同保持。旧“只修实现bug”的授权不能冒称已经允许数值Gate变更；新行为必须绑定本review和独立policy身份。

## 1. 审阅裁决：已有进展与缺口

所有下列历史数字均来自同一attempt4记录；它们不是本review新做的测试。

| 项目 | 值/状态 | 数据身份及解释 |
|---|---:|---|
| 模型 | 0.7 nm、有限x/y/z空气缺口、G0 336 cells、p6/q4、80 modes | 原输入与实际setup记录；缩小几何，不是最终器件尺寸 |
| p6 / q4完整存储rows | 229,680 / 69,856 | measured，不是独立外层行数 |
| 外层已执行 | 8 matvec / 8 PC | measured；不是2048步耗尽 |
| 原A6相对真残差 | 0.16667295750232392 | measured；迭代尚未收敛 |
| native identity相对差 | 3.0748104980683956e-10 | 超过旧1e-10门槛约3.07倍 |
| identity差向量范数 | 1.0129916171163611e-9 | 保存数组重算记录 |
| identity operation scale | 3.29448470971699 | 与上一行形成上述比例 |
| internal / port / Schur-port | 6.4490e-18 / 1.4794e-15 / 1.3094e-29 | 各自定义下通过；不代替独立原矩阵检查 |
| workflow monotonic / realtime | 356.929 s / 392.257 s | 两套时钟，分别报告 |
| 整树RSS采样峰值 | 2,954,866,688 B | measured；不是完整成功运行峰值资格 |
| 任务swap / 资源停止 | 0 B / false | measured；PSS禁用 |
| 原始worker分类 | V20_RELEASE_GATE_FAIL | 保留；首个callback停止属于源码推导 |
| 原始KSP reason、纯KSP时长 | 未持久化 | unknown，不用其他时钟倒推 |
| 合格全场、official R/T/A、G1、direct reference | 未取得 / NOT_RUN | 不把诊断场或p2结果当作替代 |

裁决：`REQUIRES_TARGETED_NUMERICAL_INVESTIGATION`。前三次启动实现错误与第四次identity停止分开保留。第8步原A6残差大于1e-6不是提前中止的充分理由；当前代码是因为identity超限主动返回停止。不能宣称Krylov天然崩溃，也不能未经验证称此次差异“只是roundoff”。

## 2. 数学对象和必须分清的两种检查

### 2.1 本次不是p4粗修正精度问题

p4检查针对一次预条件修正是否满足其右端项；已有“最多两次额外精化后返回最佳完整状态、允许外层继续”策略不变。

本次p6 native identity检查的对象更基础：恢复得到的完整场，代回原方程，是否与凝聚/增广代数推导的残差一致。它涉及外层实际求解的算子，不能照搬p4软返回规则直接删掉。

采用现有非Hermitian符号，完整增广系统为：

```math
\begin{bmatrix}V&B\\-D&H_p\end{bmatrix}
\begin{bmatrix}u\\\alpha\end{bmatrix}
=\begin{bmatrix}f\\g\end{bmatrix}.
```

这里的$H_p$是原始端口块，不是H6平滑器，也不是内部消元后的$\widehat H$。左右耦合$B,D$独立，不能自行令$D=B^H$。定义：

```math
\begin{aligned}
e_{\mathrm{FE}}&=f-Vu-B\alpha,\\
e_p&=g+Du-H_p\alpha,\\
A_6&=V+BH_p^{-1}D,\\
b_6&=f-BH_p^{-1}g.
\end{aligned}
```

相容的两条路径应满足：

```math
r_{\mathrm{native}}=b_6-A_6u
=e_{\mathrm{FE}}-BH_p^{-1}e_p
=r_{\mathrm{derived}}.
```

逆号均表示solve，不要求形成显式逆。检查差向量与三个独立指标：

```math
\Delta r=r_{\mathrm{native}}-r_{\mathrm{derived}},\qquad
\eta_{\mathrm{id}}=\frac{\lVert\Delta r\rVert_2}{s_{\mathrm{id}}},\qquad
\eta_b=\frac{\lVert\Delta r\rVert_2}{\lVert b_6\rVert_2},\qquad
\rho_6=\frac{\lVert b_6-A_6u\rVert_2}{\lVert b_6\rVert_2}.
```

$s_{\mathrm{id}}$继续使用现有operation scale，保存全部组成项。不得通过换大分母使旧失败消失。非零端口右端项时必须使用实际$b_6$，不能把原始$f$范数直接当成有效物理RHS范数。

用attempt4记录的RHS范数1.5304071041作比较，差异归一化约6.62e-10，约为最终1e-6目标的0.066%。这是单个向量上的派生量，不是误差上界、场误差或放行证明。

### 2.2 内部自洽检查不是独立原积分oracle

[当前残差实现](../../src/solvers/p6_cell_condensed_action.py)使用`_factored_matrix_action(cell.interior_lu, ...)`及同一`cell.recovery`构造部分内部作用。因此极小internal residual能说明已存对象自洽，不能独立排除raw矩阵、缓存身份、方向变换或恢复映射误差。

本轮必须增加有限范围的独立原始块检查：

```math
r_{i,K}^{\mathrm{ind}}
=f_{i,K}-V_{ii,K}^{\mathrm{raw}}u_{i,K}
-V_{it,K}^{\mathrm{raw}}u_{t,K}-B_{i,K}\alpha_K.
```

`raw`来自同一物理/积分定义的原FFCx/native局部积分，不从被检验的LU重构。保留原检查，但不把它重新包装成完全独立的验证。

## 3. R0：冻结已有输入和诊断向量，不重复构造一个工程因子

本阶段核对同一run的source、input、物理、模式、网格、Basix方向及存储布局；从本机ignored结果读取真实文件，依[attempt4记录](outcomes/records/g0_attempt4_identity_gate_stop.json)逐项核验hash。

```text
run_id = task40extra_0p7nm_nonseparable_g0_iterative_v1
run_directory = results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g0_iterative_v1__full3d_iterative__mpi1__Mna/20260929T230709.246850Z
input_sha256 = 8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c
physical_model_sha256 = 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661
retained_packet_sha256 = 58dc271acc5e33ad5b206e60c0cc9a083cd63f10f7481ac7364a718d5de12488
residual_packet_sha256 = 058b4832505428da041b9cc11cb72d8aed1c8afc6bd3fd969a99ec4ec4c29303
```

先读取保存的retained向量、完整storage场、alpha、RHS、两条残差和差向量；没有的字段写缺失，不由文件名猜内容。重算现有差向量和比例，确认第8步证据身份。完整场保留slave-zero的原始计算坐标；可视化的MPC展开副本不能未经变换拿来做native action。

不再跑p2 tiny，不建立p4全局因子，不重新生成已合格材料包，不重复全仓回归。允许一次合并的G0 p6网格/FE/局部数据重建，供后续所有作用对照复用；它是记录成本的operator diagnostic，不是假称“纯离线零成本”。重型数组不存在时先检查已有路径与manifest，不能默默重跑G0制造同名证据。

## 4. R1：对第8步真实向量做定向分解

先做只读数组定位，再做最小局部/算子重放。不得仅用随机向量通过替代真实失败向量。

| 对照 | 实际工作 | 交付与判断 |
|---|---|---|
| 差向量支撑 | 内部、active trace、周期面、端口及缺口邻域分别统计；重叠集合标明，不重复求和 | 范数、最大分量、贡献最大的单元/类型及坐标 |
| 原A6分项 | 同一场分别算curl、mass、DtN、组合；对照缓存/native路径实际接线 | 各作用范数、差异、积分/材料/方向身份；是否存在大项抵消 |
| raw tensor vs快速tensor | 同一真实几何与材料比较原FFCx和当前blocked Gram完整局部矩阵及真实局部向量作用 | 分块误差、作用误差、原始Jacobian与class key；不新加rounding合并类型 |
| raw内部残差 | 用上一节独立原始块检验恢复结果，必要时对最可疑局部块作有限条件性/后向误差检查 | 区分局部求解、恢复映射、原积分与同因子自洽 |
| 凝聚/恢复恒等式 | 恢复后原始局部作用与Schur注入对照；保留非零内部及端口RHS | Schur、trace内部修正、端口修正的符号/约束一致性 |
| 数值累加 | 仅当上述证据指向累加抵消时，对少量主导行做更稳定或更高精度累加对照 | 验证实际dtype精度；更高精度累加不代表输入表格也获得了更高精度 |

优先检查真实贡献最大的局部类型。若误差由多类共同贡献，再覆盖本G0的实际类型；始终逐类型/固定批次流过，不复制一套每cell稠密矩阵。局部参考矩阵可临时生成，用后释放。不得为定位而装全局p6 AIJ或复制整套p4因子。

在线残差计算仍保留独立native A6。纯局部诊断可以重建内部小LU；这与禁止额外全局p4 factor不矛盾。保存第8步完整向量重放和最多两个有实际含义的补充输入，例如其trace/port拆分或固定扰动，说明选择原因。保存向量不同分量的重组必须保留正确RHS与恢复关系。

输出一份`identity_localization_v1.json`：基线是否复现、主要贡献来自哪里、证实和排除到何种程度。若无法复现，先核对source/FFCx/几何/积分及存储坐标；不能直接用当前较小结果覆盖attempt4。不要扩展成库版本、batch、MUMPS、p/h的大扫描。

## 5. R2：优先修复原一致性；只有证据充分才启用工程误差预算

### 5.1 路径A：实现差异或可修复的数值组织

有物理/几何/积分/方向/cache身份错误，必须修复；不得归类为浮点噪声。若定位到局部累加、恢复或缩放问题，允许同方程的最小稳定实现修复，包括有界局部求解精化或等价缩放；不得扩大为更换PC、全局高精度、修改材料或移除通道。

首选在原定义下恢复`eta_id <= 1e-10`。用第8步原向量和独立raw块验证；变更影响共享核心时，做相应旧profile的最小兼容性测试，不重跑父任务整场。严格路线的全部Gate原样保留。

### 5.2 路径B：仅对已定位的有限精度差异，允许显式研究预算

**本节不是立即将1e-10改成1e-8。**必须先同时满足：

- 两条路径的物理、积分、约束、材料和端口定义一致；不存在未解决的标签、符号、缺项、缓存误用。
- 独立raw内部方程与局部作用对照完成；不能仅靠同一LU自检或两个残差范数相近。
- 有实际分项/累加或条件性证据解释差异主要来源；第8步误差可复现、主要贡献可追踪，补充输入未暴露另一个未解释误差。单独说“complex128有舍入”不够。
- 最小稳定修复已评估；剩余误差影响确实小于下面事先冻结的工程预算。缺证据时本节不可启用。

定义单独allowlisted policy `task40_native_identity_rhs_budget_v1`，默认仍为strict，不提供任意阈值扫描。冻结：

```math
\tau_6=10^{-6},\qquad
\tau_{\mathrm{id},b}=10^{-2}\tau_6=10^{-8}.
```

这是本review预先规定的“表示差异不超过最终残差目标1%”的工程预算，不是理论前向误差上界，也不是从观察到的3.07e-10倒推门槛。只限本轮已核验的Task40族，不推广为所有模型的数值定律。

启用后仍在每个原定检查点完整计算两条残差，保留原`s_id`、`eta_id`与旧strict是否通过；另外要求`eta_b <= 1e-8`。保留finite、internal<=1e-10、Schur-port<=1e-10、port<=1e-8和实际原A6检查。有效RHS为零/非有限时拒绝；不加`max(1, norm(b))`这种改变归一化含义的补丁。

在旧identity略超限、上述资格有效且新预算通过时，记录`IDENTITY_BUDGET_QUALIFIED_CONTINUE`并继续FGMRES；不伪写`STRICT_IDENTITY_PASS`。任何检查点预算超限、资格身份变化或出现真实实现/非有限错误都停止。最终原A6及release后仍须<=1e-6，不能用derived残差替代。

**路径B的G0是受控研究验证，必须优先完成原计划中的唯一G0同离散direct参考，再推进G1。**参考须采用独立原积分作用并满足task的场/模式/功率比较；参考尚未完成时，G0可保存完整场和带provisional标记的诊断功率，但不宣称本预算路线已取得official资格。参考精度不足以判别候选差异、资源不安全或比较失败时，保留G0为`AUTHORITY_LIMITED`/未完成该预算路线资格，不推进G1、不提升默认。不得用p2、粗化几何或能量闭合代替同离散参考。

R1/R2资格与policy、原因、预算、source写入`identity_policy_decision_v1.json`，先提交再运行。不满足路径A或路径B条件时，收口明确未解释的具体分项，而不是放宽直到通过。仍可按第7节提前用唯一G0直接参考定位，但不另加参考名额。

## 6. R3：保存首个停止原因，统一callback与release/checker

[FGMRES实现](../../src/solvers/physical_retained_fgmres.py)已返回status、reason和纯KSP计时，但后续release异常会让本场证据只剩下游分类。

在不改变KSP数学过程的前提下：

1. callback第一次决定停止时，保存iteration、触发Gate、原始指标、实际policy、应用status和拟返回reason；只保存小型JSON。
2. `KSP.solve`返回后，在终态snapshot、cache核验、release之前，持久化实际`getConvergedReason()`、迭代/动作数及`ksp_solve_monotonic_seconds`。异常返回缺失值标unknown，不编造。
3. 终态检查和release追加各自状态，不覆盖primary cause。原`V20_RELEASE_GATE_FAIL`历史保持；以后能同时读到primary与secondary。
4. strict/条件budget的同一数值决策应贯通callback、setup校验、terminal、release与动态checker；不能删一个raise后仍由旧副本误停，也不能让checker一律放行新标签。

用小fixture覆盖：严格通过、旧identity失败/未资格、合格预算继续、预算超限、错误符号或字段、非有限、late-release failure不覆盖primary原因、旧profile行为不变。记录真实reason与源码推导的区别。检查器只读证据，不实现另一个求解器。

## 7. R4：授权完成G0/G1与最多一场参考

这是对已失败首批的明确、有条件续作授权，不借用已经耗尽的旧replay计数，不擦除旧累计成本。新运行使用独立run目录/attempt身份，必要的新profile与`.dat`只改变实现或policy元数据；原物理配置及ordered keys必须逐项一致，物理hash算法改变时解释字段范围。

正常至多：**一场修复后G0 iterative、一场安全且前置通过的G1 iterative、最多一场G0同离散direct参考。**条件参考提前或已存在可复用结果时，不再重复最后一场。

| 路径 | 顺序 | 可继续条件 |
|---|---|---|
| A：原strict已修复 | G0 -> G1 -> 条件G0 direct -> 对照收口 | G0残差/identity/物理通过；G1容量安全 |
| B：已证实有限精度预算 | G0研究验证 -> G0 direct -> G1 -> 对照收口 | G0原A6与预算通过且同离散参考比较通过 |
| 定位仍有歧义且参考有判别价值 | 预检安全后可先用唯一G0 direct；随后依据证据修复，再决定上述G0/G1 | 不用direct绕过未解释identity；不增加参考次数 |

仍经`python scripts/run_case.py input/...dat`、独立监督、clean committed source启动。G0/G1原入口：

```text
input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat
input/task40extra_0p7nm_engineering/nonseparable_g1_p6_q4.dat
input/task40extra_0p7nm_engineering/nonseparable_g0_p6_direct_reference.dat
```

正式G0零初值；第8步保存向量只用于定位，不冒称fresh运行的初值。每场只建其必需的一份全局因子，setup通过直接完成求解与输出，不在候选选定后等待额外阶段批准。不热改运行源码，不用“第8步复现了”替代终态资格。

本轮另允许至多一次hash-bound真实实现bug的定向重放；数值超限、资源不足和性能不佳不属于实现bug。启动身份/JIT路径等先在R0/R3闭合，不用正式运行反复试接线。遇到新错误先保留证据、最小修复和对应测试，不能不断更改阈值或累计新增相似run。不得因旧attempt计数耗尽而拒绝本节已重新授权的正常场。

### 7.1 不变的物理/数值资格

- 0.7 nm Si/air、解析缺口、G0 336/G1 880计划及实际网格身份、原入射、双Floquet、完整已冻结80模式不变；80模式来自当前inventory，不是任意节省上限。截断未资格化继续披露。
- p6/q4、双凝聚、BAL_H、FGMRES32/max2048、H6数学动作与power10规则不变；不切回旧谱窗常量。
- MUMPS后端、排序、主元、BLR/OOC、线程不改。每次p4完整A4验算及精化后检查不减；两次额外精化后返回最佳一致状态的既有规则保持。
- 每8步独立原A6，每32步场/解，终态与release后原A6<=1e-6；NaN/Inf或真实约束/实现错误仍停止。
- official功率只对最终合格场生成；路径B同时标注预算/参考资格。输出E/H、curl、各有序模式复幅、R/T/A_balance/A_volume及零级s/p。
- 能量绝对闭合<=1e-5；同离散reference按task的场/模式相对1e-4、R/T/A绝对1e-5、逐模式功率1e-6。reference本身精度与独立性范围必须如实列出。
- G0/G1同解析几何/材料/keys，在共同物理坐标比较总场与散射场；h变化工程目标沿task的场1%、功率绝对1e-3，不称连续极限证明。弱吸收同时报相对/绝对变化，避免绝对闭合掩盖小量误差。

### 7.2 资源与运行纪律

使用实际资格化ABI/complex128和IntType，不假定已安装v0.10/int64。运行时线程变量与库线程读回保存。笔记本接电、固定电源模式，MPI1/数学线程1，一次一个heavy。

保留真实physical-memory-pressure、系统/cgroup余量、快速树RSS、任务scope零swap、失联与后代清场保护。PSS未采样记null。全机换出页数不能直接归因任务；不改OS全局swap策略。OOM不是正常验收。

旧8GiB、历史RSS、旧126步/40分钟均不是新停止线；time保持observe_only，max2048和实际安全/数值规则保留。必要JIT、诊断和checker的时间/子进程内存纳入对应记录，不能通过缩窄进程树或清零peak制造收益。已有104个合格JIT文件可按真实签名复用，硬链接字节不是RSS，不为新物理强行复用不相容二进制。

## 8. R5：交付、判定与提交顺序

新增`response_v2.md`，不要再次覆盖Response V1的旧因果链。summary增加本轮结果，run index和两级项目总账同步，保留attempt1–4及所有旧hash/unknown。轻量文件可合并，但需要覆盖：

```text
outcomes/identity_recovery_v1.md
outcomes/records/identity_localization_v1.json
outcomes/records/identity_policy_decision_v1.json
outcomes/records/identity_recovery_v1_results.json
outcomes/test_summary.md
outcomes/summary.md
response_v2.md
```

报告按setup、KSP、后处理列时间/次数/主要内存对象，父子计时分开；至少保存真正KSP-only、primary stop、reference次序、每个模型实际policy以及整个树峰值所属阶段。不得从两套时钟差推造某阶段耗时。保存数组在ignored结果目录，Git只放compact、配置、hash和最小复现命令。

| 最终状态 | 可以说什么 | 不能说什么 |
|---|---|---|
| STRICT_IDENTITY_REPAIRED | 独立检查定位并修复；旧阈值下通过的范围明确 | 局部通过就等于正式场通过 |
| SCALE_BUDGET_QUALIFIED | 原strict值仍如实报告；有限精度证据与新预算明确 | 所有3e-10误差都属于roundoff |
| G0/G1完整通过 | 当前0.7 nm缩小连续介质模型的离散解与相应物理结果 | 目标尺寸任意三维在2 TB内已经可行 |
| REFERENCE/H_AGREEMENT_PASS | 对实际参考或两网格做过指定比较 | 连续极限、通道截断已全部收敛 |
| IDENTITY_UNRESOLVED / REFERENCE_RESOURCE_BLOCKED | 精确列出仍缺的证据或安全限制，保留合格部分 | 用便宜p2结果、空字段或PASS标签替代 |
| 资源/数值失败 | 给出同scope的实测值、门槛、首因与后续状态 | 自动降p/删mode/换PC试到成功 |

建议提交：C0固定旧证据与最小诊断；C1最小修复及停止原因保存/测试；C2冻结policy和正式输入/clean source；C3各场结果与最终回应。R1–R3连续完成；满足明确条件后继续R4，不每做一个字段修复就停审。只有真实blocker或本轮授权范围完成才统一回应。

本轮不启动Phase II，不推广工作站，不开新分支、不merge master。若G0/G1通过，R5用实际误差和资源指出下一项唯一主候选；当前仍以“先得到正确的0.7 nm小模型”为目标，不又回到低内存强逆参数扫描。

## 9. 证据与源码入口

- [当前任务书](task.md)：冻结物理、G0/G1、reference、资源与Phase II边界。
- [当前回应](response_v1.md)、[summary](outcomes/summary.md)、[attempt4 compact](outcomes/records/g0_attempt4_identity_gate_stop.json)：历史数值、source及artifact hash。
- [旧续作授权](outcomes/records/g0_user_authorized_continuation_v1.json)：只修启动bug且数值Gate不变的历史边界，不改写。
- [FGMRES callback](../../src/solvers/physical_retained_fgmres.py)：检查间隔、停止返回、真实reason和计时保存位置。
- [p6凝聚与残差](../../src/solvers/p6_cell_condensed_action.py)：非Hermitian块、内部恢复、两条残差及operation scale。
- [outer适配](../../src/runners/physical_retained_outer_adapter.py)、[worker](../../src/runners/physical_dual_cell_condensed_lowmem_v20.py)：native原作用、诊断packet、release与summary传播。

以上源码以review base SHA读取；本文代数为该符号约定下的推导，工程预算是本次显式设计，不伪称已有实测通过。ChatGPT本次只审阅并写review，未重放FE数组、未运行PDE、未验证最终根因。执行后的每个结论由Codex的原始证据和下一轮审阅确认。
