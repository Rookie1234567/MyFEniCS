# Task39extra Review V27：粗层精化未达标继续外层；A4、p6局部矩阵与H6三项加速

## 0. 决定、身份和执行权限

**本轮落实用户两项决定：第一，原A4每次仍完整验算，目标仍为1e-10，但初次求解加最多两次精化后仍未达标，只要计算状态有限且实现完整，就返回已计算的较好修正，让外层FGMRES继续；不再仅凭该内部目标未达中止整场。第二，实际尝试A4正向验算加速、p6完整局部矩阵生成加速、H6在线作用加速。MUMPS后端、分解配置与准确p4粗空间不变，不开展分解调参或后端替换。**

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-24
reviewed_base_SHA          = cb828b77e137556590c26cce13cc8dfce30cba6a
latest_review_response     = review_report_v26.md / response_v29.md
baseline_formal_source     = 4c504fe9d268ae5841dc439b79988f386a1c09b1
batch_identity             = review_v27_a4_tensor_h6_continue_outer
suggested_profile          = physical_p6_trace_a4_tensor_h6_v29
response_required          = response_v30.md
execution                  = P0 -> P1 -> P2 -> P3 -> P4 -> P5 -> P6
normal_fresh_full_PDE       = 1
model                      = original / wavelength13.5nm / p6-h7.5 / coarse-p4
numeric_cache_mode         = build
environment                = qualified personal-laptop WSL/Linux, MPI1
ordinary_default_changed   = false
master_merge               = NOT_APPROVED
```

本轮针对的blocker是：**可用Full3D预条件器仍需反复执行昂贵的局部作用和一次性高阶矩阵生成，且把内部精化软目标当整场硬停止条件，会提前放弃本可继续的外层求解。** 最终目标仍是约2 TB整机内存内的0.7 nm、complex128、Nédélec H(curl)、双Floquet、z开放边界、任意非可分三维周期单胞。当前固定小模型的时间收益不等于目标规模资格。

用户明确要求原A4只加速实现，**不减少检查频率、不使用便宜筛查、不用抽样或低精度作用代替完整原A4残差**。p6局部矩阵与H6必须作为独立实现目标尝试，不能因本机只可能省几分钟就跳过；但不承诺大规模必然节省几小时。用户排除的第4项即MUMPS分解优化，本批不试。

这是同一执行分支的新授权批次，不消耗或重置已经结束的旧批次额度。允许必要src实现、测试、profile/入口/检查器接线及一次完整h7.5回归，不要求每一步再等确认。真实实现bug保留hash和成本后，允许一次必要的定向正式重放；性能不佳或正常外层不收敛不属于bug。禁止无目的反复启动整场、热改运行源码、改写历史负结果或合并master。

执行前读取根/适用目录AGENTS、[工作原则](../repository_work_principles.md)、[task](task.md)、[V22补充授权](user_authorization_v22_b_capacity.md)、[V23补充授权](user_authorization_v23_physical_memory.md)、[Review V26](review_report_v26.md)、[Response V29](response_v29.md)、[summary](outcomes/summary.md)及[性能备忘](performance_followup_notes_20260923.md)。本review明确替代本批的“原A4每次未达1e-10必须拒绝”和“不改局部矩阵生成后端”限制；旧profile与旧结论原样保留。

## 1. 已证实结果与新比较分母

主要分母为[V28修复后完整记录](outcomes/records/fused_operator_speed_v28_post_repair_compact.json)，不是更早且更慢的场。全部为同一990单元、80通道、准确p4版本。时间s，内存B；GB=10^9 B。累计动作是inclusive计时，与父区间不可重复相加。

| 对象 | 数值 | 数据身份及范围 |
|---|---:|---|
| workflow monotonic | 2936.0762416610087 | measured，48.93分钟，整场主要分母 |
| workflow conservative realtime | 3203.447879573999 | measured，独立时钟同口径比较，不与上一行相减解释某个步骤 |
| setup / pure KSP | 773.9463588640065 / 2113.442534869 | measured，各有明确边界 |
| iterations / original A6 residual | 126 / 9.283164917015627e-7 | measured，126不是停止上限 |
| tree RSS / PSS peak | 7356289024 / 7324145664 | measured，10901个样本，swap=0 |
| original A4 verification | 268次 / 457.12798303701857 | measured，volume456.5357608549966、DtN0.43980413099052384 |
| p4 reduce / MatSolve / recover | 76.98887651201221 / 90.85710013094649 / 71.47568589297589 | measured，262逻辑调用、268实际求解；仅能推得6次额外精化，不能据此写6个异常RHS |
| H6 apply | 131次 / 527.5183640260511 | measured；先前shared-contraction未采用 |
| A6 fused live action | 263次 / 517.3248120769858 | measured；保留本轮已成功融合，不重新包装成新成果 |
| p6 raw kernel / local Schur | 228.84196730799158 / 11.954928313018172 | 历史同规模engineering measured，见[Response V28](response_v28.md)，不是V28本场分项 |

[V28](outcomes/fused_operator_speed_v28.md)已经有完整离散求解与场/模式回归，保留其成果及修复前软件失败。此前六组短配对未复现V26在线明显退化，不再调查旧场供电/19%退化；H6共同前向收缩减少次数却未形成可信速度收益，不原样重试。原A4加速、新的局部矩阵生成和新的H6执行优化均属本轮待测，不能提前标pass。

## 2. 冻结数学与资源身份

从[已通过的V28输入](../../input/task39extra/v28_fused_kernel_original_h7p5_post_repair.dat)继承。新增run_id、显式profile与所选实现/精化策略字段；重新生成input/source hash，物理/网格/mode身份逐字段核对，不改写历史hash。

| 项目 | 本批合同 |
|---|---|
| 物理 | 13.5 nm、1° grazing、azimuth0、s偏振；原Si/air复材料、mu_r和单胞几何 |
| 网格与空间 | 9×5×22=990个原六面体；p6 full-storage667152；p4 full-storage201520；h7.5不是波长 |
| 边界 | 原x/y Floquet、z Fourier-DtN、全部80个key、相位、法向与归一化 |
| 凝聚 | p4直接装配84680行凝聚系统；p6保留局部Schur供199340维外层作用，不形成全局p6矩阵 |
| 外层 | right FGMRES、restart32、max2048、零初值；每8步原A6、每32步场检查 |
| PC | 原增广逆桥、BAL_H、每次两次逻辑C4和一次H6；不增加H4、inner KSP或新粗空间 |
| H6数学 | 原正定B6、约束对角、Chebyshev次数和谱窗规则、power10种子与步数；只改执行实现 |
| MUMPS | 现有已资格化库、准确p4矩阵/排序/主元/BLR关闭/ICNTL(10)=0；现有有限额度规则与单线程不变 |
| 输出 | 原完整E/H/curl、界面量、R/T/A/A_volume、80复模式及逐模式功率；不拟合相位或重归一化 |
| 生命周期 | 合格JIT在大factor前；每场fresh numeric build，因子跨调用复用；因子活跃时不释放借用矩阵；最终检查后释放再后处理 |

原目标与PC结构保持：

```math
A_6x=b_6,\qquad C_4=P_{64}F_4P_{64}^H,\qquad
M_6r=C_4r+H_6(r-A_6C_4r)-C_4A_6H_6(r-A_6C_4r).
```

这里F4代表一次粗层缩减、已有凝聚LU回代、内部恢复及本节授权的有界精化，不是显式逆矩阵。F4在精化分支下可随输入变化，不能用固定线性逆的恒等式假装所有粗残差为零。

不运行p3/p2、notch、5nm/2nm或工作站任务。公共内核应避免硬编码p4/p6专用物理假设，以便后续复用，但本轮不再做粗阶筛选。不得切换直接求解后端、扫描MUMPS排序/主元、启用BLR/OOC、改变全局factor线程数或升级ABI。

## 3. P1：最多两次额外精化后继续外层，不再误判整场

### 3.1 所改变的是失败策略，不是检查频率或最终精度

对每个逻辑粗层输入g4，照常求解并完整计算：

```math
c^{(0)}=F_{4,0}g_4,\qquad e^{(j)}=g_4-A_4c^{(j)},\qquad
\rho_j=\frac{\lVert e^{(j)}\rVert_2}{\max(\lVert g_4\rVert_2,\mathrm{tiny})}.
```

F4,0为无额外精化的原因子缩减—回代—恢复操作。初次返回不达1e-10时，最多做两次：

```math
\delta c^{(j)}=F_{4,0}e^{(j)},\qquad c^{(j+1)}=c^{(j)}+\delta c^{(j)}.
```

每次都对累计后的完整c重新执行原A4正向作用，不以残差递推、凝聚残差或最后一次增量代替。原g的范数始终是分母，不能用越来越小的精化RHS改变相对残差定义。端口alpha同步累计。

```text
初次solve + 完整A4验算
→ 达到1e-10：返回，NOT_NEEDED
→ 第一次额外精化 + 完整A4验算
→ 达到1e-10：返回，REFINED_TARGET_MET
→ 第二次额外精化 + 完整A4验算
→ 达到1e-10：返回，REFINED_TARGET_MET
→ 仍未达到：选已计算、有限且状态完整的最小rho修正，继续外层KSP
             标记COARSE_TARGET_UNMET_CONTINUE，不抛精度拒绝异常
```

正常至多是初次加两次额外、合计三次因子求解；不增加第三次精化，不无限while。零RHS沿合格零返回语义处理，计数不得伪造MatSolve。没有“第二次必成功”的承诺。

**继续外层不只限于一个新指定的残差区间。不得暗加另一个粗残差阈值、最大软超限次数或增长比，再以此中止外层；有限数值状态下，单纯未达粗目标不是硬停止理由。** 真正的NaN/Inf、因子错误、不可逆局部块、MPC/方向/端口状态损坏、恒等式接线错误、外层自身breakdown或实测资源安全问题仍按原规则停止，不能catch所有异常后一律继续。原外层max2048和最终A6门限保留。

### 3.2 选出的修正、端口和验算证据必须属于同一个状态

若三份都不达标，固定选择已完整验算状态中rho最小者，平局选最早者；每次有更好状态只保存一份best快照，禁止长期保存全部调用向量。必须同步选择c、alpha、A4c、e以及对应记录。可复用该次真实计算的A4c/e，无需为恢复best再计算一次；不能拿best解配最后一次残差或端口。已经达标时立即返回，不能用best选择改变原来的成功路径。

保留最多一份best状态的新增数组载荷和生命周期计入库存/RSS。返回阶段记录selected_attempt、last_attempt_rho、returned_rho和min_rho；退回较早attempt不抹去之后两次真实计算及成本。

### 3.3 不是只删一行raise：接通整个判定链

明确opt-in策略，例如`coarse_refinement_exhaustion_policy=continue_outer_best_finite`；旧profile仍为原strict策略，不改历史结果。

重点检查[粗修正及精化](../../src/solvers/physical_interface_balanced.py)、[inexact ledger](../../src/solvers/physical_inexact_balance.py)、[外层适配](../../src/runners/physical_retained_outer_adapter.py)、profile/runner/launcher和[动态checker](../../benchmarks/task39extra_v25_dynamic_checker.py)。新profile的原A4软目标不得在setup兼容检查、每个boundary、最终checker、parent wrapper或summary中被再次当作整场失败。完成的soft-return PC仍计为completed，计数来自真实调用，不能把它丢出时间/残差统计。

保留inexact闭合关系而非强迫粗误差为零：

```math
P_{64}^H(r-A_6z)=\varepsilon_1-\varepsilon_2.
```

ledger使用实际返回状态的eps1/eps2；已有operation-relative闭合检查继续检查两边是否一致，不以缺陷本身非零拒绝。改变的是粗目标未达策略，不是把映射或算子错误也豁免。

checker必须分别输出`coarse_target_met_all`、`coarse_unmet_continued_count`、最大/分布、原A6终态与物理结果。`coarse_target_met_all=false`可以与`DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`并存；后者只在原最终Gate全部满足时成立。returned_rho按selected_attempt重算，不能再机械等于最后一条repair record。旧profile仍沿旧判定。

最小测试必须主动制造：初次达标；一次/两次精化达标；两次后仍有限超限且下一外层调用实际继续；后一次变差而best状态一致返回；零RHS；非finite/真实因子错误仍拒绝。用mock/小复数fixture验证分支，不人为破坏正式p4因子、降低精度或注入误差来强迫完整h7.5触发soft-return。若正式场没有触发，只能说分支已fixture验证，不能伪造实际触发结果。

## 4. P2：原A4完整正向作用只做加速，不改逐次检查

目标是减少当前457.13秒累计验算成本，不是优化仅约90.86秒的LU回代。当前原A4体积作用占几乎全部验算成本；已有A6融合成功不等于A4回调已自动更换。

优先把[融合volume](../../src/solvers/fullspace_fused_split_volume.py)、[张量积内核](../../src/solvers/fullspace_n1e_sum_factor.py)和[物理后端](../../src/solvers/physical_equivalent_fast.py)适配到真实p4作用。共享gather/MPC/方向与系数变换，curl/mass分别用原积分规则，合并后正确回写；完整原A4加一次DtN，slave identity计一次。它仍计算完整A4c，不是少算一部分的筛查；不使用p4 LU或其同一个Schur生成结果作为唯一验算oracle。

**所有原本发生的A4验算仍发生：初次、每次精化后的累计修正均完整计算。禁止隔N次才查、只查部分DoF/通道、随机sketch、便宜前筛、低阶/低精度作用、复用上一输入的输出、只看因子/凝聚残差。** 独立旧native实现保留作资格oracle，正式选定一种合格的完整A4实现，不在每次调用中再同时运行两份完整实现来抵消收益；是否在额外资格测试中调用oracle与正式检查频率分开记账。

性能比较的分母是当前实际A4回调，不以更慢的人工路径替代。利用已保存的真实g/c对，包含可取得的精化边界输入；比较完整作用及e=g-A4c，不能只比较随机向量上的action相对误差。action资格至少沿原operation-scale 1e-10；对非零实际g另要求新旧残差差除以原g范数不超过1e-11，目标达到1e-12量级，防止1e-10验算目标被新内核误差淹没。近目标的浮点判定差异逐项披露，不改门槛凑一致。资格不通过就保留旧native A4，P1继续外层策略仍须实现。

记录数学算子身份与执行实现身份：新fast A4不能仅沿用`native_A4`标签让人误以为仍在运行旧FFCx路径。旧字段必要时保留兼容别名，但加implementation和oracle身份，完整次数、时间及输出norm均可追溯。不构建第二个p4全局矩阵或因子。

## 5. P3：加速p6完整局部矩阵生成，不重做已完成的类型缓存

现有模块已使用装配时单元凝聚和按类型复用；本机12类raw/26类定向数据是实测结果，不硬编码为算法前提。当前瓶颈是生成一次真正需要的完整882阶局部矩阵，不是约12秒的局部消元，也不是990个单元各做一份MUMPS。

在[单元凝聚模块](../../src/solvers/hcurl_assembly_time_condensation.py)的raw-tensor入口增加显式候选，以原基函数、原积分点/权重、材料和几何，分块计算：

```math
V_K=G_K^H W_{\mu,K}G_K-k_0^2\Phi_K^H W_{\epsilon,K}\Phi_K.
```

本式是原积分的矩阵组织，不是材料或几何近似。curl/mass积分规则不同就分别累加；复材料乘在原物理位置，不能错误共轭epsilon，也不能假设有损V_K为Hermitian只填一半。必须与现有FFCx核保持test/trial索引、covariant Piola、点顺序、积分tag和duplicate-integral语义一致。材料/几何超出当前后端支持范围，保留显式原路径或准确not-supported，不能默默降成可分离物理。

优先同积分的blocked Gram/矩阵乘法方案，按积分点或矩阵块限制scratch；若局部结构足以安全张量化，可在同一入口采用，不能扩成另一整套求解平台。先求完整curl+mass的V_K，再按原块做Schur，不能把两个Schur相加。此候选先限定p6准备，不顺带改变p4矩阵/排序/分解输入；共享通用模块有变化时用profile/degree路由保证q4 numeric仍走原合格路径。

先对实际类别做完整矩阵、作用、局部Schur和非零内部RHS恢复对照；复用小型独立native/FFCx oracle。原矩阵operation-scale相对差<=1e-10、原局部消元/端口/恢复闭合<=1e-8，已有更严检查保持。局部逆敏感时必须看Schur和恢复，不能只凭矩阵Frobenius小差就采用。

每种原始类型只构建一次，临时高阶参考表和矩阵分块用后释放；缓存大小受实际类别数约束，遇到很多不同材料/尺寸允许流式或有限缓存，不把“恰有12类”当作任意3D保证。p6仍`materialize_global_matrix=False`，禁止逐单元稠密库和跨运行factor缓存。输出每类耗时、总kernel耗时、每类/每cell成本、唯一载荷与scratch；不要把本次cold构建移出workflow计时。

组件测试无需p4全局因子。每类正确性一次覆盖，性能用代表类别短配对并给出全部类别真实构建总成本；不为每个局部块重建FE/全局factor。不能仅增加计时器后以“需要新积分实现”为由放弃本项，用户已授权新局部实现尝试；确无收益则保留失败候选和具体证据。

## 6. P4：H6在线作用的新执行优化，数学H6保持不变

目标是当前累计527.52秒的H6 apply，而不是已经只需数秒的对角。H6的数学、次数、谱窗规则保持：

```math
D_6=\operatorname{diag}(B_6),\qquad
H_6r=D_6^{-1/2}q(D_6^{-1/2}B_6D_6^{-1/2})D_6^{-1/2}r.
```

利用现有coefficient_transform/reference_forward/metric/reference_backward子计时，选择一个真正主导步骤实现新候选。优先检查Nédélec与多项式系数双向转换的实虚布局、批量矩阵乘法及重复拷贝：可把实/虚RHS在同一有界批次中组织成连续运算、共享真正相同的只读系数布局，或将收缩改成固定形状的直接矩阵乘法/已有栈可编译的局部执行。若主要成本在投影，减少实际重排/临时数组而非只换开关。无论选择哪项，都明确减少了哪次拷贝、调度或算术及其完整apply收益。

不得把V28已经否定的shared-forward-contraction原样再测，或重开旧projection-reuse开关称新实现；不按容差截断Basix系数，不改变基、积分、材料、H6次数或power10。可利用精确为零的结构，但必须完整保留其余系数且验证真实方向/MPC。不把减少运算计数直接当作实测提速。

先固定同一D和谱窗比较B6/H6 apply；合格后才能用于原power10，记录窗口舍入差异。B6/H6相对等价沿原1e-10，正定能量与正确约束对角保持。新通用内核若影响A6，需在同一批向量上确认V28已成功融合路径不退化；否则只对H6显式启用。失败回退该项，已合格的A4与p6准备优化继续。

2/3两项面向后续大模型：重点保持按批次有界的存储与可复用接口，不增加随全域积分点数增长的永久张量，也不以沿z均匀或内部可模态分解为假设。只报告本次实测和有前提的复杂度分析，不能从几分钟线性外推出必省几小时。

## 7. 执行顺序、线程范围与一场完整回归

| 阶段 | 交付与分流 |
|---|---|
| P0 轻量预检 | 新batch登记；核对profile、独立service、实际apply接口、fused-owner库存字段及checker策略，不再等大factor建完才发现KeyError |
| P1 继续外层策略 | 实现策略和端口/best快照一致性；mock/小fixture证明两次后未达目标仍有下一外层迭代 |
| P2 A4加速 | 实际实现、完整作用和残差对照；不合格则用原A4，不改频率 |
| P3 p6矩阵生成 | 实际局部kernel候选，逐类矩阵/Schur/恢复资格和构建计时；不合格则用原FFCx |
| P4 H6在线优化 | 实际新执行候选和固定D/谱窗配对；不合格则用原H6 |
| P5 唯一正式组合 | 冻结合格子项与新精化策略、提交clean source；一场同original p6/h7.5完整求解 |
| P6 统一收口 | 原始检查、计时/内存总表、response/outcomes、提交推送同一分支待审 |

三个加速对象分别有实现尝试和证据；不同时要求三个都成功，也不让可选性能失败阻断P1及最终回归。必要测试合并执行，不每改一行跑完整测试集；局部和A4/H6组件不建立无关p4因子，完整PC兼容检查与正式必要工作集合并。正式场只保留一套所选算子和一份p4因子。

本批默认MPI1、单线程。MUMPS始终沿原单线程设置，无ordering/BLR/后端/并行factor试验。若P3的纯局部矩阵生成只需现有支持即可作一次两线程补充候选，沿原“最后试、不可靠立刻退回”条件：主线程JIT/只读输入，worker独立输出、内部BLAS1、join后恢复；完整生命周期峰值不增加且能读回真实能力才可采用，不装新运行库、不扫描4/8线程。不得以此拖住三项串行主线或引入多核KSP；H6和正式外层仍单线程。前移缓存与线程残留全部计入峰值，不把归还线程数量等同于归还内存。

P1本身是需要完整验证的行为变化，因此即使三个加速候选都未采用，只要P1资格通过，仍运行一次新策略的完整h7.5，不以`NO_ADOPTED_SPEED_CHANGE`跳过用户的继续外层目标。正式无需故意制造不合格粗逆；其未触发分支由fixture证明。

正式使用`python scripts/run_case.py input/path/to/case.dat`、现有独立user-service/watchdog。每场dat仅一次运行；合格JIT正常复用，局部数值数据与全局factor本场build、不读旧解/局部LU缓存。setup通过后同一进程和因子直接完成外层，不逐阶段等确认。126步、48.93分钟仅比较基线，不是进度停止线；不因性能较差自动再跑。

## 8. 最终Gates、资源与可读的时间/内存账

| 类别 | 判定 |
|---|---|
| 原A4每次完整验算 | 必须执行并保留真实值；1e-10是精化目标，最多两次额外精化后有限未达不导致整场fail |
| 返回完整性 | FE/alpha/原A4作用/残差/selected-attempt一致；非finite、真实因子/约束/接口错误仍硬拒绝 |
| BAL_H | 每次两次逻辑C4、一份H6；原inexact eps1-eps2操作尺度闭合<=1e-8，不要求eps都为零 |
| 最终原A6 | 完整恢复后独立重算、释放前后<=1e-6；不得只用KSP或Schur内部残差 |
| 场/模式回归 | 对V28同离散FE L2/scaled-curl、同坐标E/H/界面与80复模式relative<=1e-4 |
| 功率/守恒 | R/T/A/A_volume绝对差<=1e-5、逐模式功率差<=1e-6、能量闭合及吸收一致性<=1e-5 |
| 成功范围 | DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED；粗软目标统计单列，不宣称全场/波长鲁棒或连续收敛 |

全程接电、固定电源模式，一次一个heavy；沿最新新profile的time/swap observe_only及真实物理内存压力政策，核对wrapper/worker/watchdog一致，不恢复旧固定预测容量挡板或提高MUMPS额度。实测zero-swap仍为资源/性能比较目标，实际发生swap必须披露并限制性能结论；系统余量、磁盘、外层真正breakdown和监督失联照常保护。A4软目标未达不是这些硬错误。

新增内核优先复用现有空间，允许有界且记账的局部scratch，目标不增加本机完整峰值；不以大量永久缓存换速度。运行中保存同一时点的MUMPS统计、矩阵载荷、p6/p4缓存、H6/Krylov/PC向量和可识别临时空间，去除alias重复计数。无需新建内存分析平台；无法闭合的残余明确unknown，不把`RSS−MUMPS used`全部叫Python开销。阶段峰值不相加，后端allocated/used不冒充RSS。

最终response必须按用户要求给出三大块逐步表：

| 大块 | 细目与记录口径 |
|---|---|
| setup | 空间/约束/端口/JIT；p4局部装配、symbolic/numeric；H6对角与power10；p6 raw tensor、局部LU/Schur/恢复；桥和启动检查。各项时间、建立的常驻对象/临时载荷及阶段RSS/PSS |
| KSP | 每次PC两次C4；C4内P/PH、缩减/回代/恢复、每次完整A4验算和精化；A6、H6/B6；外层Schur、正交化及独立残差/场检查。真实次数、累计、均次及内存对象 |
| 后处理 | 完整恢复、最终原A6、释放及释放后检查、物理输出；明确计时与剩余对象 |

同一原始边界分别保存monotonic、realtime conservative、CPU；不得将267秒历史时钟差解释成某个setup操作，也不能挑更短时钟。主分母更新为V28：full2936.0762416610087、KSP2113.442534869、setup773.9463588640065 s、RSS7356289024 B；r2仅作历史附列。缺失旧分项写unknown；inclusive和exclusive分开，不拼接各轮最优子项当一场成绩。

新策略本身与三项加速分别判断。若soft-return实际触发，外层次数/方向可能变化，必须把单次调用收益与迭代数变化分开，不能全部归因内核。相同数学重排允许舍入差与因子hash变化，但p4路径不应被无意更改；所有新增测试/编译/重复构建与正式时间分开计入批次成本。

## 9. 提交与交付要求

建议D1提交精化继续策略、动态checker及针对性测试；D2提交三类实际内核候选和配对证据；D3冻结选择/profile/dat及最终相关测试；D4提交一场正式证据、response与总账。实现进可复用src，benchmark只做调用/计时/独立检查，避免复制task-numbered巨型runner。旧strict profile、负结果、备忘和review不改写。

轻量证据可合并文件，但至少包含以下独立事实：

```text
response_v30.md
outcomes/a4_tensor_h6_v29.md
outcomes/records/a4_tensor_h6_v29_refinement_policy.json
outcomes/records/a4_tensor_h6_v29_components.json
outcomes/records/a4_tensor_h6_v29_selection.json
outcomes/records/a4_tensor_h6_v29_compact.json
outcomes/records/a4_tensor_h6_v29_checker.json
outcomes/records/a4_tensor_h6_v29_decision.json
```

正式绑定input_original.dat、resolved_config、run_manifest、input_sha256、physical_model_sha256、source_sha、run_summary、环境/MPI/线程、完整残差与FE/端口输出hash；矩阵、因子、完整场、timeline留ignored artifacts。同步summary、test_summary、run_index、development_progress与模型总账，selective manifest分清已测与research-only，不合并master。

response直接回答：两次精化后未达是否真正能继续、正式触发几次或未触发；逐次A4检查是否一项未少；三项各尝试什么、采用/撤出及原因；setup/每步/整场各省多少；峰值内存及剩余对象是否清楚；MUMPS是否完全保持；后续规模适用边界。不可用“任务完成”代替速度结论，也不可为了性能结论丢掉软件失败成本。

公式/表格遵守[Markdown标准](../markdown_rendering_standard.md)，运行相关文档合同与本地预览，推送后核对GitHub rendered view；有不可访问项明确披露，未跑CI或全库测试如实写not_run。最终推送同一task39extra并回报完整HEAD、上游ahead/behind和工作树，统一等待审核。

理论边界参考：[PETSc FGMRES官方说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)允许变化/非线性预条件作用；这只支持继续外层的算法合法性，不保证有限粗修正必使外层收敛，也不授权升级本机PETSc。
