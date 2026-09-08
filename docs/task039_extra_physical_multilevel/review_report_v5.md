# Task39extra Review V5：粗—细平衡的三路线有限验证

## 0. 身份、裁决与连续执行范围

```text
repository                = Rookie1234567/MyFEniCS
branch                    = task39extra
review_date               = 2026-09-08
reviewed_HEAD             = 50575a9dd0bf8b43e41f66d34a7154e003b88397
latest_response           = response_v6.md
previous_review           = review_report_v4.md
actual_error_source       = 2251d7d0d3d3e8498ee34d38f8ec70f70d2f0d98
matched_reference_source  = f09476792d9928d6169cae8cc16b4c008f9bc694
original_task_base        = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
new_scope                 = BALANCED_COARSE_FINE_BOUNDED_CAMPAIGN
routes                    = BAL_H / BAL_S / PROJ_K6
execution                 = E0 -> E1 -> E2(A,B,C conditional sequence) -> E3 -> E4 -> E5
response_required         = response_v7.md
ordinary_default_change   = NOT_AUTHORIZED
master_merge              = NOT_APPROVED
```

**本轮消除的 blocker：p4 能表示主要实际误差，但单独粗修正引入很大的细层残差，逐段 MR 又把该修正压掉；现有细层处理未与粗修正形成有效反馈。** 这次从已经测到的耦合缺陷出发，比较三个明确的完整 PC，不再只做原因定位，也不再凭方法名称扫描。

用户明确要求下一轮适当增加路线并统一审阅。本文件授权在同一执行分支连续实现、比较及条件式真实求解，覆盖旧 review 的“不得新 PC/不得外层求解”停止范围；不修改旧 task、review、response 或负结果。某条路线正常数值/性能不合格，就自动进入下一条；共同物理身份、实现正确性或资源监管失效才阻断共享工作。阶段之间不重复请求授权。

最终目标仍是约 2 TB 单节点内的 0.7 nm、complex128、Nedelec H(curl)、双 Floquet、Fourier-DtN、周期单胞内任意非可分三维散射。本轮仅在约 16 GB 本机检验 13.5 nm。生产 fine-space 保持 uncondensed full-space matrix-free；不回到单元静态凝聚生产路径，不使用准二维/模态可分离假设。

## 1. 接受哪些结果，不接受哪些外推

依据 [Response V6](response_v6.md)、[真实误差报告](outcomes/actual_error_diagnosis_v5.md) 与 [记录](outcomes/records/actual_error_diagnosis_v5.json)。以下为这些固定历史来源的 measured/derived，不是本 review 新测结果。

| 已有证据 | 数值或边界 | 本轮使用 |
|---|---|---|
| 匹配离散参考 | 原 A6 相对残差 1.6160e-11；一次修正后变化受控 | 复用解、映射、原 RHS 与 hash；不重跑原始 fine direct |
| 三真实误差 | 相对参考 L2 22.46% / 24.92% / 31.34%；相位无关相关均大于 0.9975 | 作为共同难样本，不解释成已找到唯一特征模 |
| p4 最佳表示 | 不可表示范数约 0.83%；约 99.993% 的平方范数可表示 | 不默认扩大到 p5，不重做相同最佳投影 |
| p4 解精度 | 四 RHS 原 A4 残差均不高于 1e-10；range identity 约 2.53e-12 | 没有依据继续提高精度以解决外层平台 |
| 耦合失衡 | 小互补引起近等大反向粗驱动；方向上的粗响应放大约 57–59 倍 | 检验粗—细整体反馈，不称条件数或已证色散 |
| 粗修正与 MR | 单位粗修正剩余场约 48%，细层残差增 22–53 倍；MR 步长约 1e-4 | 不再对原有三个方向仅重新选权；也不单独强制旧粗步长为 1 |
| 独立资源 | 参考峰值 7.230 GB；诊断峰值 3.882 GB；均 swap0 | 不相加、不当作 p4 factor 单独大小或 2 GB 资格 |

诊断在这三个同模型误差上形成了闭合证据，接受为设计依据；没有得到低内存迭代、非可分结构、h/波长鲁棒性或连续解资格。对“机制定位”的接受不等于下述候选保证有效。

原参考第一次失败来自 incident 表面积分不匹配，之后只对参考入口用 degree25 对齐。此次原 A6 和原 b 必须沿用已经匹配的 native 路径；不得把参考的局部修正扩展为修改 ordinary 默认。官方物理输出仍按 task Gate 判断。

## 2. 冻结物理、代码角色与复用边界

| 项目 | 冻结要求 |
|---|---|
| 原始 case | task.md §3 的 13.5 nm、1° grazing、azimuth0、s、50×25×140 nm 单胞、原 Si/air 分布 |
| fine | p6/h10、252 个六面体；存储/独立 rows 为 173802/164592；MPI1、线程1、complex128 |
| 真实 A/b | 原 curl、负复材料质量项、80 个 DtN modes、相同 RHS/quadrature/Floquet；不加吸收、不删 modes |
| p4 | 同网格 P/P^H、原 A4 与现有增广 LU 参考；独立 rows48960，不改变阶次或排序参数 |
| physical SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| H6 | 已有三阶 positive Chebyshev fine-only 平滑，原对角和谱窗口；不是乘一次 B6 |
| S6 | 已有 positive p6→p3→p1 的一次 upper cycle；不是完整 S6–p4–S6 wrapper |
| 数值内核 | 复用 exact A、传递、p4 reference、H6/S6、有限 Krylov 和恢复；新增组合进通用 src 模块 |
| 新 dat/profile | 三个独立显式 profile：`balanced_h6_p4_v5`、`balanced_s6_p4_v5`、`projected_krylov6_h6_p4_v5`；全部 resolved 参数进入 manifest |

原始正式 case 统一由 `python scripts/run_case.py <明确的一次计算.dat>` 进入。诊断作用可复用已有薄入口，但不能在 benchmark runner 内重写数值算法。新增源码先提交 clean SHA，再测量；不把源提交不同自动当作算子不等价，需保留实际 identity 桥。

不重跑已有投影、参考、packing、旧长程 FGMRES；只为新组合补必要接口检查。相同数学对象的编译 cache 可复用，必须绑定 ABI/form/quadrature/hash。新路线输出、temporary vectors 与原始 packet 不覆盖历史文件。

## 3. 共用数学定义：粗修正与两个不同的投影

以下先在独立自由度、精确算术下定义。A 指真实 A6，P 是 p4→p6 延拓，星号使用 Hermitian 伴随：

```math
A_c=P^HAP,\qquad C=P A_c^{-1}P^H,
\qquad \Pi_p=I-CA,\qquad \Pi_d=I-AC.
```

C 输入方程残差（dual）并返回场修正（primal）。Pi_p 作用于场，Pi_d 作用于残差；两者不能互换，也不能将其当成同一个正交投影。理想情况下：

```math
CAC=C,\quad \Pi_pP=0,\quad P^H\Pi_d=0,
\quad A\Pi_p=\Pi_dA,\quad P^HA\Pi_p=0.
```

**这里的代数补空间是 Pi_p 的值域，即 ker(P^H A)，不是先前 M0 最佳投影定义的 L2 正交补空间。** 旧互补诊断不能直接当作新 projected 方向的收缩证明。新 PC 不在每次调用中求 M0 投影；M0 仅用于独立评估。

A 非 Hermitian、不定；Pi_p/Pi_d 可以很不正交。上式只是代数关系，不保证范数收缩。有限精度及 p4 有界精化时，按实际 action 检查这些关系，不假装投影完全精确。p4 的严格残差通过仍不构成整体前向误差界。

本轮不显式形成 C、Pi_p、Pi_d、A P 大矩阵或全局 Schur 补。它们由已存在的 A、P/P^H 和 p4 求解调用实现；未删除 fine 未知量，因此不是重新启用单元静态凝聚。

## 4. 三条路线及其不同问题

### A：BAL_H，轻量的双侧平衡修正

它先做粗修正，再让 H6 处理粗修正后完整残差，最后抵消 H6 对粗方程造成的反作用。关键是把粗、细两部分作为整体返回，而不是在每个中间阶段缩步。

```math
\mathcal B_H(q)=Cq+\Pi_p H_6(\Pi_dq).
```

精确调用顺序：

```text
zc = C(q)
u  = A(zc)
rc = q - u
s  = H6(rc)              # 无新增 MR，不借用旧已缩步方向
v  = A(s)
t  = C(v)
z  = zc + s - t
return z
```

理想情况下，P^H(q−Az)=0，且对 q=APa 有 z=Pa。但这不保证完整 q−Az 小，也不保证新粗/细投影不会放大其他方向。

一次 apply 的主要工作为 2 次 C、1 次 H6、2 次 fine A；外层的 Az、p4 原残差检查、传递和监控另计。此计数是 derived 结构账，不是实测时间。

### B：BAL_S，保持平衡结构，改用更完整的细层响应

调用顺序与 A 完全相同，只将 H6 替换为旧 S6 的一次 positive upper cycle：

```math
\mathcal B_S(q)=Cq+\Pi_p S_6(\Pi_dq).
```

这一对照回答：轻量 fine 平滑不足时，保留旧 p3/p1 处理能否有效消除由粗修正产生的新残差，而不仅仅是增加成本。只调用一次 S6，不再是旧 pre-S6→p4→post-S6，也不新增平滑次数/窗口/ILU 参数。

S6 如果包含非线性内部求解，上式按函数组合理解，不当作固定矩阵去测谱。外层统一 FGMRES。比 A 更贵但不更有效，是允许的负结果；不要因为 B 已构建就强行把它称为改进。

### C：PROJ_K6，在平衡补空间内做有限 Krylov 修正

A/B 一次细层作用可能仍不足。C 不另造子域或粗空间，而是让最多六个**新生成的、满足粗层约束的细层方向**共同处理剩余残差。这与旧 JOINT 对同一组三个顺序方向重选权不同：每个新方向来自当前 projected residual 与真实 A 的传播。

先取 zc=Cq、rc=q−Azc。构造一次零初值、最大维数6的 flexible Arnoldi 最小二乘过程。每个内部 Arnoldi 向量 v_j 产生：

```math
h_j=H_6(v_j),\qquad z_j=h_j-C(Ah_j)=\Pi_p H_6(v_j),
\qquad w_j=Az_j.
```

正交化只作用于真实 w_j，以稳定 QR/Givens/小 SVD 解小最小二乘；不要形成正规方程。得到系数 y 后返回：

```math
\delta=\sum_{j=1}^{m}z_jy_j,\qquad
z=zc+\delta,\qquad m\le6.
```

内部方程的目标是 Aδ≈rc，而不是重新解 A4，也不是正定 B 问题。初始 rc 理想上属于 ker(P^H)，所有 Az_j 也属于该空间，因此子空间过程相容。**不要用奇异投影 PC 对任意完整 RHS 启动普通线性求解并假定它可逆**；必须使用上述兼容 rc 和 projected directions。约束检查不依赖 reference field。

冻结参数：最大6步、无内部 restart、零初值；达到 norm(rc−Aδ)/norm(rc)≤0.25 时可提前返回。rc为零直接返回zc。未达到0.25但结果有限、约束和小最小二乘合法，则返回已取得的有限近似，标 `INNER_TARGET_NOT_REACHED`，不将其自动当成整个外层失败。不增加到12/36/100步，不自适应扫描 inner target。

happy breakdown 必须以显式内部残差核查；有效子空间饱和而目标未到，只能有限返回并记录，不能谎称收敛。非有限、严重正交化/角色错误按正确性失败处理。内层最长算力、p4 求解与日志均纳入外层时间预算。

本轮第三条固定使用 H6，不再自动增加 PROJ_K6_S6 成为第四条。主要成本上界为 1+6 次 C、6次H6、1+2×6次 fine A（不含额外审计和外层Az）；p4每次检查与至多两次精化另计。最多约13个内部Krylov长向量，不能用“内部只有6步”忽略其与外层同时存活的内存。

### 三路线共同禁止事项

不调用旧 `modified_residual_accept` 对粗方向或补偿方向逐段缩步，不在 PC 末尾再做全局标量 MR/旧 JOINT。外层 FGMRES 自己仍以原 A/b 最小化残差。这是新的整体 PC 设计，不是取消真实残差验收。

不使用 x_ref、实际误差向量、预计算的精确修正或这些向量的拟合系数作为 PC 输入之外的数值知识。参考与难误差只用于测量；不得将共同难误差偷偷加为第四个粗方向。保持相同算法处理原始入射 RHS 和以后非可分结构。

## 5. 共享 p4 参考、精化与身份规则

本轮仍是 reference-backed 的机制验证：C 复用同一个已资格化 p4 增广因子，不是0.7nm生产近似逆。每个原始模型过程仅一份 numeric factor，按需共享，不每次 apply 分解。不同材料模型必须重建自己的算子/因子，不能按相同rows误复用。

原 A4 相对残差保持≤1e-10，采用 V4 已实现的显式有限精化策略：原回代超过门槛才使用同一因子，最多再修正两次；不扫描排序、主元、精度、物理参数。每次原残差检查保持；拒绝抛出前必须保存必要失败向量。E1样本及新拒绝保留完整packet；正式外层中成功的常规p4调用只写标量、计数及必要身份，不把每次回代的全部向量持续导出。超过门槛不能静默当成合格 C；也不能为一个新增 RHS 创建新的大规模精度项目。

某个 RHS 有限精化后仍拒绝时，保留 raw、保护当前候选并转其他不依赖该失败调用的已授权项；若故障证明是共享映射/作用/因子损坏，则共同停止。不得提高门槛或将上一批0.87%越限改PASS。成功精化后的 C 与一次回代策略分别标识，全部工作计数。

原 native A4 与增广残差关系继续沿 V4 核对，不要求两个舍入级小残差之间再达到1e-10相对一致性。新增投影恒等式默认以操作尺度归一化的1e-8作诊断闭合线；分母采用参与项范数之和，不能以理论为零的小量作分母。此线不是原A4解门槛，也不是外层1e-6门槛。若不闭合，先核查精度放大/接线，不能强行把不正交投影解释为正交。

## 6. E0–E1：一批实现检查，直接使用现有真实误差

E0只读取本文件、最新response/summary和改变的相关源码，核对branch/HEAD/upstream/clean worktree、ABI、线程、内存及artifact。根与docs AGENTS及工作原则继续适用。不重写历史综述，不安装新求解栈、不调查NTP/Hyper-V、不优化packing。

E1用一个合并的tiny代数/接口批次检验：复共轭、primal/dual/zero-slave、借用向量生命周期、C与投影恒等式、A/B作用定义、C路线的兼容初残差与有限Arnoldi、zero RHS、有限精化拒绝及终态保存。tiny问题允许精确求解作预期值，但不能冒充原尺寸求解通过。新数值组件进入可复用src模块，runner只组织case；尽量复用现有有界FGMRES，不同时重写整个Krylov平台。

接着在当前原始模型上对**三份已保存真实误差加一份V4预定义人工三维控制**，每条路线各调用一次，共同样本共12次新PC apply，另允许每路线一次原尺寸coarse-range恒等式控制，总计最多15次。统一使用q=Ae；若复用旧r，显式扣除参考残差，按原比例同时归一化q和e。已有x_ref、P/M0投影及旧PC结果直接复用，不重新求参考、不再次算三份最佳表示。

每个apply保存以下有限指标：输入/修正/实际Az、剩余场L2与scaled-curl、原残差比、P^H(q−Az)操作尺度缺陷、粗/细/反馈阶段范数及计数/时间。对BAL记录反馈前后；对PROJ_K6记录每个内层步的真实残差、约束漂移和小Hessenberg。参考只在独立评估端读取。

这些同输入指标用于解释机制，不作为“rho必须小于1才能启动外层”的门槛。若合法有限但单次场或残差放大，仍允许进入限定真实试跑；不得恢复早期one-sweep筛选造成的未测完整方法。非有限、错误的identity或资源风险则不运行对应候选。

E1输出每个样本即落盘。若一个候选实现受阻，可隔离并继续其他不依赖它的候选；不能在报告中将未运行记成算法失败。E1完成后连续进入E2，不停审。

## 7. E2：三条路线的真实求解与自动分流

所有数学/资源合法的候选按 **BAL_H → BAL_S → PROJ_K6** 顺序，从零初值求原始A6u=b。每条至多一次正式原始case，不能把上一候选解当下一候选初值。保存的旧失败解只用于E1，不用于正式启动。

### 7.1 每条路线先取得真正外层结果，再决定是否投入完整预算

统一外层 right FGMRES、restart32、max_it2048、原 true relative residual目标1e-6。先运行至128步，或者solve累计1800s先到；这不是第二次启动，不人为清空Krylov空间。每32步显式残差，reported每步轻量记录，停止前构造当前解并重算原残差。

达到此短程边界且未通过时，满足以下任一条件可自动继续同一live KSP至完整预算：

- 当前原相对真残差≤1e-2；或
- 最近三个完整32步checkpoint为r0,r1,r2，两个周期均下降，且sqrt(r2/r0)≤0.65。

已达到1e-6则直接进入输出与E3。没有足够三个checkpoint、又不满足1e-2时，记录 `SCREEN_BUDGET_NO_QUALIFIED_PROGRESS`，进入下一候选；不靠外推一天后会收敛继续。

以上是**本轮有限投入的工程分流规则**，不是数学不收敛定理；单次PC指标不参与该规则。不得将screen stop改成永不收敛。边界处若正在原子PC步骤中，可在安全返回点裁决；外部完整wall/内存硬线仍有效，不能为等一项超长PC返回而失去监管。

### 7.2 完整预算及成功后的顺序

每条原始case的solve总上限7200s、完整workflow上限10800s，包括screen而非另加。任何步数/时间上限先到即按实际原因停止，不追加长期续跑。

一条原始路线取得数值与可用输出后，**立即进入E3的同尺度非可分挑战**，不用先跑完其他原始路线。若E3通过，余下原始重型路线可标 `not_run_goal_met` 并收口；12个有限共同样本对照仍保留。若E3数值/性能失败，继续后续未测试原始路线，但本批不对同一非可分case反复更换PC长跑；保留参数域局限集中审阅。

原始数值通过但恢复出现明确工程错误，允许最小修复并从保存最终解恢复，不重求原始场；物理/参考不匹配时须调查，不得为进入E3忽略。共享A/b/输入错误不可用“换路线”绕过。

## 8. E3–E4：非可分三维与完整输出，不再留到下一任务

E3使用task.md §3.2已冻结的同尺度三维缺口：原外域、p6/h10、13.5nm/1°不变；原grating中按既定cell key/几何recipe切出air。先核对确实同时破坏y均匀与z挤出，保存材料实体与新physical SHA。不是单纯给原规则材料输入三维RHS。

只运行一次，使用首条取得合格原始结果的同一profile、same fixed smoother/inner/restart，不对缺口调参。外层仍zero start、2048步、solve7200s、workflow10800s；本项允许完整预算，不因缺少新结构参考误差而取消运行。自己的p4增广matrix/factor必须重建；最高资源与系统余量不变。

原始和非可分每次成功都要保存最终p6解、最小recovery packet，释放p4 factor及全部内外KSP/PC/无用矩阵，确认RSS下降后恢复complex E/H、近场、R/T/A、A_volume、全部衍射功率与复幅值。官方输出门槛不放宽：原full residual≤1e-6；独立能量abs(R+T+A_volume−1)≤1e-5，abs(A−A_volume)≤1e-5；检查被动性和所有实际通道，不能只输出旧n=0通道。

原始模型用已有x_ref独立系数计算场L2/scaled-curl差；接受标准相对场差≤1e-4，近零量另报绝对误差。若已有参考尚无完整可观测量，允许仅从保存reference solution用同一官方后处理生成一次，**不重建fine direct因子**。有匹配数组时，R/T/A/A_volume绝对差≤1e-5、显著通道功率绝对差≤1e-6、复幅值向量相对L2≤1e-4；不拟合整体相位。

没有非可分独立参考时，可记录真实残差/守恒/输出通过，但独立场精度标 `AUTHORITY_LIMITED`。E4允许**至多一次**成功非可分模型的已有fine direct控制：必须先释放PC栈、分级容量准入、原A/b/积分同一身份、全流程≤3600s。预测不安全就不numeric，不降低p/h、不提高cap，且不撤销已经真实取得的有限资格。

不强制在本机新增h5/其他波长。无h/p误差序列不能宣布连续精度；一个缺口通过不能宣布所有任意三维结构通过。完整迭代器和输出未过Gate时，不从失败场生成official结果。

## 9. 新批次预算、计数与安全

本轮是用户授权的新有限批次，不借用或重写历史余额。计算费用从执行动作累计，测试、预检、编译、setup、factor、作用、求解、恢复、失败均计入；同一父/子时间不能重复累加。文档编辑、聊天等待单列，不用“从review提交UTC起一直计时”使尚未执行的计算先耗尽预算。

| 项目 | 硬上限或限定 |
|---|---|
| 合并测试＋共享setup＋E1有限作用 | 5400s；新PC共同样本12次＋range控制3次，总计最多15次，不为性能统计重复几十次 |
| 原始候选 | 至多3次zero-start正式case；每条screen含于7200s solve和10800s workflow |
| 非可分完整求解 | 至多1次，7200s solve/10800s workflow |
| 新fine direct | 仅条件非可分reference至多1次，3600s；原始reference不得重跑 |
| 全批次实际计算费用 | 43200s，所有限额不是可另外相加的授权；达到总额即收口 |
| 生产范围 | 不执行5nm/0.7nm，不改主线为凝聚，不扫MPI/线程/BLAS/PML/DD |

这些都是投入上限，不是预计完成时间，更不是要求把预算用满。新组合在screen无进展就及时切换，已有成功就优先非可分，不为增加“尝试数”运行明显多余的heavy。

有效内存取可见RAM和cgroup约束，系统reserve=max(4GiB,15%有效总RAM)，程序cap=min(12,000,000,000B, effective_available−reserve)，启动及运行中动态检查；warning为0.85cap。一次一个heavy、swap0、完整parent/MPI/compiler后代与cleanup监控。资源超限、监控失效仍严格停止。

复用已经运行过的diagnostic `conservative_realtime`政策，记录mono/BOOTTIME/UTC和逐段保守费用，不重新研究系统时钟、不把单独UTC跳变误标数值失败。使用同一进程/明确公共时间基准，不跨机器混减时间。

每32步保存安全解与真残差；若单周期过长，按现有不重启的BuildSolution安全接口作时间间隔保存。性能/用户停止先安全保存，资源硬线优先。结束始终写最小summary；析构异常不能吞掉先前已完成数据。不重建已丢失的Krylov基后冒称无缝续跑。

## 10. 实现、浮点与可扩展性约束

共同映射、借用/owned buffers、复内积和slave处理使用已核对接口。新的Pi_p作用必须处理primal，Pi_d作用必须处理dual。C是近似逆作用，不能把p4系数直接当p6方向。控制向量和物理量必须同时归一化，不能只缩放q而不缩放用于评估的e。

E1在一个合法原尺寸coarse-range控制上检查B(APa)≈Pa；在一般输入上检查P^H(q−ABq)的scaled闭合。这只需有限个A/C调用，不形成全长AP。tiny还检查投影幂等及恒等关系。关系通过不代表谱/收敛定理；不通过也需分清有限p4误差放大与实现错误。

PC内部及Krylov只持有有限长向量，不得创建N×48960全局基底、dense projector或新的全局fine factor。PROJ_K6在其有限维内层使用稳定正交化，残差可靠性与rank退化要可见。新增附加工作向量按目标不超过32个fine长度预算并实际计数；当前N=173802时其complex128数值载荷约89MB（derived，未含库/ghost/缓存）。外层65个FGMRES32基向量和S6/p4其他对象另计，不得据此声称整体89MB。

**三条路线现在都仍依赖全局p4参考LU，成功只能得到reference-backed迭代机制资格，不是最终0.7nm可扩展PC。** 不允许以新名字隐藏该债务，也不为了本轮“无factor”重启已经失败的36步shifted p4内层。

若至少一条通过原始和非可分case，E5必须交付下一阶段的唯一扩展对象：如何以受控内存的物理多层/分布式近似实现C，同时保持本轮测到的平衡关系；什么精度由耦合放大决定、global p4 factor何时必须取消。只写方案与账本，本轮不再增加第四条内层路线。

若三条都失败，应依据新q/z/Az、补偿前后与内层进展，区分“投影放大但细层响应无力”与“每步有效但总工作过大”。停止本组组合变体，不自动改p5、换权重或上PML。后续传递/检验空间或物理局部逆的改变须另有证据和review；不用失败反推所有MG/DD不可能。

## 11. 证据、提交与集中审阅

新增少量中心材料：`outcomes/balanced_coupling_v5.md`、`outcomes/records/balanced_coupling_v5.json`、`response_v7.md`；更新summary、run_index、test_summary及两本项目总账。重型向量、mesh、cache、checkpoint和日志留ignored artifact，Git只保留索引/hash。旧actual-error报告和审计脚本不修改、不覆盖旧audit路径。

每次正式case保留input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary及环境、模式、网格材料、MPI/线程、资源和全部artifact hash。共享setup的费用明确列出，不分摊后假装每条是冷启动，也不以warm性能代表冷构建资格。

推荐普通commit顺序：新增通用C/投影/三组合与focused tests；连接显式dat/profile、runner和输出并提交clean source；运行/保留正负证据；统一response与总账。只重跑改动实际影响的最小测试，不安装Ruff/新库或空称CI通过，不做无关代码整理。不同候选若最后代码未改变，不为同一底层组件重复资格化。

response_v7至少给出：三路线实现/运行状态与源码、E1四输入的场/残差/平衡数据、原始真实曲线和筛选分支、全部内外调用/时间/RSS、参考场差和输出、非可分结果、typed失败与未运行原因、factor扩展债务，以及下一个唯一对象。不得仅交“projection identity pass”“PC更快”“内部六步完成”便结束。

E0–E5连续执行到全部已授权条件结论或共同安全/正确性阻碍；正常单路线失败不回用户处请求换下一条。工作结束提交推送同一task39extra并等待集中review，不merge master。

## 12. 方法依据与保证边界

- [PETSc PCDEFLATION](https://petsc.org/release/manualpages/PC/PCDEFLATION/)：定义复数粗修正与投影、允许多层及非SPD粗解。它不是本文件双侧公式的现成黑盒复现，也没有为本Maxwell case提供保证；不直接启用其默认全局粗求解。
- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：允许变化/非线性PC、使用右预条件；具体运行仍绑定现有PETSc3.19 ABI，不为了文档版本升级环境。
- [Southworth–Manteuffel, On Compatible Transfer Operators in Nonsymmetric Algebraic Multigrid, arXiv:2307.05900](https://arxiv.org/abs/2307.05900)：提示非正交粗修正可放大误差，平滑器需处理该放大。此次核对原始摘要，不能引用它作为三候选的Maxwell波长鲁棒性定理。

本文件的C/Pi公式及兼容子空间关系为显式代数推导；本轮冻结的H6、S6、六步上限和screen标准是工程研究选择，不冒充上述文献的最优参数。报告编写没有运行新的项目PDE；数值有效性以随后实际证据为准。
