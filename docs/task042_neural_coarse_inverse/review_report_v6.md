# Review V6：V8 审查与冻结误差的物理分量定位

## 0. 审阅决定与要消除的 blocker

**接受 V8 的停机事务修复和固定 batch8 数学等价／共享微基准证据；列范数均衡未取得严格资格或预登记的研究正信号，此具体尺度试验收口，不继续扫描。Task042 继续，但本批只分析已有冻结解的误差，不启动新的训练、求解器或预条件器试验。**

当前必须回答的是：为什么原方程残差有所下降，真实散射场却基本没有恢复？本批将同一误差向量分别放到原凝聚方程、未凝聚体／端口方程和有限元场中检查，区分数据／恢复错误、场幅值或形状偏差、原方程分量抵消与优化目标敏感性。它直接约束下一项方法选择，但**本身不提高求解能力，也不保证查出唯一根因**。

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task42_neural_coarse_inverse
worktree                    = /home/fenics/Projects/NN-Lab
review_date                 = 2026-09-29
reviewed_HEAD               = ba5ec813cc16a90adde1433ecb91e4b822b9d601
original_base_SHA           = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review             = review_report_v5.md @ fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
latest_response_reviewed    = response_v8.md
V7_candidate_source         = 7c4037a279cefd8546c51e8ae6cf0172c3eab89d
V8_scaled_source            = 1a2984a44ca48573bbe18ffe8a7f8c5d6bdacc05
V8_batch_source             = 52d47d35656c5a763bed07e07f827fb6fb285bb7
V8_ownership_fix_source     = 9915f6168ec4035470870a5d8c3c3bbfe0e6277a
review_decision             = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
next_batch                  = V9_FROZEN_ERROR_PHYSICS_LOCALIZATION
response_required           = response_v9.md
material_state              = MATERIAL_READY_USER_SUPPLIED
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate         = NOT_QUALIFIED
master_merge                = NOT_APPROVED
```

最终目标保持：约 2 TB 工作站资源内，端到端不超过 48 小时，得到一个新的、真正非可分三维周期单胞的合格 0.7 nm 有限元解。当前 micro-pilot 的几个波长跨度不是最终目标规模，不转为扫参代理，不把数学自检或微基准当作求解通过。

ChatGPT 本次核对了远程合同、回应、结果与相关恢复／审核代码；没有 SSH 重跑工作站，也没有读取工作站全部 ignored 向量。下面的 measured 来自仓库证据，公式为代数定义／推导，下一批数据仍为 not_run。

## 1. V8 的已证实结果与限制

主要依据：[Response V8](response_v8.md)、[完整结果](outcomes/scaling_and_execution_v8.md)、[统一对照](outcomes/records/scaled_lsqr_comparison_v8.csv)、[独立审核](outcomes/records/independent_calibration_gates_v8.json)、[批量样本](outcomes/records/batch_costs_v8.csv)、[停机记录](outcomes/records/optimizer_stop_semantics_v8.json)。所有下表残差／误差均无量纲，分母沿原记录，不更换参考尺度。

| measured；同一固定 micro-pilot | V7 原 LSQR | V8 列均衡 LSQR | 判定标准／含义 |
|---|---:|---:|---|
| 原 Schur 相对残差 | 0.071602579856 | 0.068283273738 | 严格 1e-6；仅小幅改善 |
| native 散射相对残差 | 0.028727751543 | 0.026675035784 | 严格 1e-6 |
| 总场 L2 相对差 | 0.1046399326 | 0.1044981633 | 严格 1e-4 |
| 散射场 L2 相对差 | 0.9999532575 | 0.9985984907 | 严格 1e-4；研究门限 0.5 也未达到 |
| 能量闭合绝对误差 | 0.0033713277 | 0.0044349128 | 严格 1e-5，未改善 |

| 分项／证据身份 | 已取得证据 | 本次接受范围 |
|---|---|---|
| 停机事务 measured | 7 项测试，真实 strong-Wolfe 异常恢复参数／梯度／optimizer，消耗不回滚 | 保留修复；V7 接受点仍 unknown，不改原向量负结果 |
| 列设置 measured | 正确合并全局贡献；列范数比约 762.67；配对最大约 4.48e-16 | 定义／实现合格，不等于能解决全局波动耦合 |
| batch8 measured | 同 trace/loss/gradient；最大梯度差约 5.338e-13；新增缓存 35107584 B | 固定状态数学等价通过，不是新训练 |
| 完整评估成本 measured | 三对中位：4.756740→2.285877、4.891869→2.516729、4.594245→2.451498 s | 成对降幅中位 48.55%，仅共享环境工程正信号 |
| 部署所有权 limitation | C2 原次读取了未用的 3369888 B moment 包；后修复和边界回归，无整场重放 | 原成本含该对象；不能宣称最小所有权版本已整场实测 |

进一步线索来自 [V8 盲验证](outcomes/records/scaled_blind_validation_v8.json)：参考／候选的散射 FE **系数欧氏范数**约为 1.631513757／0.005806378，散射端口系数范数约为 0.197450149／0.000853844。候选约为参考的 0.356%／0.432%（derived 比例）。这些不是物理 L2 范数或功率；必须用本批的场积分与幅值／形状比较核对，不能仅凭数组范数断定物理方向。

当前不是“残差已通过但场错误”：0.068 仍远大于 1e-6。也没有证明 S 奇异、只有某个共振模式有问题、网络容量不足或调整一个超参必能通过。batch8 应保留；不得因更快而直接续训，也不得把列缩放的负结果外推到所有神经方法。

## 2. 冻结对象、授权和历史保护

先读根／目录 AGENTS、[仓库原则](../repository_work_principles.md)、[原 task](task.md)、已有全部 review、最新 response/outcomes 和本 review。本批只接续尚未定位的误差／残差关系；不重开已经关闭的 p4 近似逆。原 task、Review V1–V5、Response V1–V8 和原始负结果保持。

| 身份 | 冻结值／原记录 |
|---|---|
| 方程／离散 | Full3D、complex128、Nédélec H(curl)、原单层凝聚 trace＋port；384 hex、p3、h0.175 nm |
| 物理 | 真空 0.7 nm、grazing1°／azimuth0／s、原三维空气缺口、双 Floquet／layered Fourier-DtN |
| 数量 | full FE34050、独立 trace18144、内部13824、slave2082；reduced18184；top20＋bottom20=40 ports |
| 材料 | [canonical 表](../../input/materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1` |
| 材料 SHA256 | `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2` |
| physical SHA | `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de` |
| mode SHA | `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262` |
| action packet SHA256 | `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454` |
| 同网格 p3 参考 NPZ SHA256 | `a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355` |

Si 折射率仍为 0.999885140474+4.32477054e-6i，epsilon=n*n；保留 `source 0.699999988 -> nominal 0.7` 明确别名。材料已经可用，不重新索要、不联网替换、不重新做四波长审计。每个数组还须核对实际 source、shape、master 顺序、背景和 RHS，不能只核对 physical 字符串。

本批明确允许**离线诊断进程**读取已有 p3 参考向量，与已冻结候选比较。它不再是 fresh blind test，也不是训练数据生成；禁止把参考／误差回传网络、构造基／PC、选择权重或作为新求解初值。旧 seed420620 池保持封存。

## 3. D0：只登记五个固定状态和一个参考

| ID | 内容 | 读取与解释 |
|---|---|---|
| Z0 | reduced trace＋port 全零 | 从尺寸确定；完整散射场并非全零，内部载荷特解仍存在 |
| NN7 | V7 NEURAL-TRACE 最终保存 z | 使用已审核向量；接受状态 unknown 不妨碍分析该向量 |
| FREE7 | V7 FREE-FE-OPT 最终 z | 不从现有模型反推最后接受点 |
| LSQR7 | V7 原 FE-LSQR 最终 z | 直接读取冻结物理坐标 |
| LSQR8 | V8 列均衡 LSQR 最终 z | 明确保存的是 z，若保存 y 只允许用绑定的原 D 转为 z，禁止重复缩放 |
| REF7 | 已有同 mesh/p3 准确参考 z | 只读，不能重新 LU／solve |

路径从原 run index／state manifest 解析，不猜工作站路径，不从标量历史重建向量。不挑选“最好”的中间 checkpoint，不增加随机 RHS、时序快照或新几何。保留每个 NPZ／z／source hash，副本只写新 ignored 目录，原文件不可覆盖。

缺某一候选时继续其余可做部分并标 PARTIAL；缺参考时仍可审核候选原残差，但误差分析标 `REFERENCE_ARTIFACT_UNAVAILABLE`，不自动重求准确解。不能仅因缺一列就重复一轮 F0 或全部训练。至少复用原 action；moment／Torch 包本批原则上无需加载。

## 4. D1：先保证“误差向量”和“误差场”是同一个对象

### 4.1 残差恒等式，保留参考本身的非零残差

固定 S、b 和相同 canonical 坐标。定义误差为参考减候选：

```math
r_j=b-Sz_j,\qquad r_*=b-Sz_*,\qquad e_j=z_*-z_j,\qquad S e_j=r_j-r_*.
```

不要把 r_* 强置零。每个原向量重新审核一次，引用 V7/V8 的归一化分母；报 absolute、原固定 RHS relative 和必要 operation-relative，不能按结果重新定义分母。参考须重验原 Schur/native/端口及恢复约 1e-10 的既有参考资格；异常只停参考依赖分析，保留其它独立检查。

### 4.2 内部恢复是仿射的，恢复误差必须齐次化

现有 [ActionPacket.recover](../../src/solvers/neural_fe_action_packet.py) 包含 `i_rhs`。将它写作 F(z)=u_part+R0 z。内部行中，R_t 代表含实际 Floquet 展开的 trace 恢复作用：

```math
u_i(z)=u_i^{\rm part}+R_t t-X_{iB}\alpha,\qquad
\delta u=F(z_*)-F(z_j)=R_0 e_j,\qquad
\delta u_i=R_t e_{t,j}-X_{iB}e_{\alpha,j}.
```

用“两次原完整恢复之差”与“显式零内部载荷恢复 e_j”独立配对。**禁止把 e_j 直接交给默认 recover(e_j) 后当成误差场**，那会额外加入 u_part。原背景在 total 场相减时也应抵消；所有 slave-zero 的存储向量用原 MPC 展开为场，禁止二次乘 Floquet 相位。

小型测试必须覆盖复数非 Hermitian、非零内部特解、非零端口及缩放后的物理坐标；证明错误地加特解会被检查捕获。生产 S／F 行为不改，可新增明确的齐次误差 helper。D1 的配对目标 operation-scaled≤1e-10；近零先列绝对量，继承原1e-12近零约定，不用零对零独自证明接口通过。

## 5. D2：确定漏掉的是幅值、形状还是局部区域

使用原 p3 空间和原积分规则重建一次轻量 FE 验证环境，复用 [原场验证函数](../../src/solvers/neural_fe_blind_reference.py) 的必要部分；不要为每个状态重新装配算子或调用完整参考求解流程。允许为积分重建 mesh/space/MPC 和必要表单，不新建 global CSR／factor。

先统一三种对象：`coefficient_l2` 是系数数组欧氏范数；`field_L2` 是体积分范数；`curl_scaled_L2` 是 curl 的体积分范数除以 k0。三者分别报告，不互当“电场误差”。候选散射场是 F(z_j)，误差场是 R0 e_j，总场误差与散射场误差的**绝对分子**应一致，但相对分母不同。

对 Z0 和四个候选一次完成：

- trace／内部／端口的系数范数、误差范数；完整散射场及误差的 L2、scaled-curl，沿用独立参考作为固定分母。
- 原单元上的误差积分，使用四个不重叠区域：air excluding notch（192 cells）、notch air（8）、substrate（48）、Si block（136）；从实际原 masks/tags 核验数量，缺口不能在 air 和 notch 中重复计入。报告各区域原误差平方积分、占总误差的比例及参考区域范数。局部参考近零时只报绝对值，不产生假大相对值。
- 验证分区域误差平方和等于全域误差平方。场的 trace贡献与内部贡献一般不正交，不能把它们各自范数平方相加冒充总场；需要拆场时明确保留交叉项。
- 40个原顺序通道全部比较 e_alpha 的 real/imag／absolute；分别报告 top/bottom、s/p 和原键。沿用原归一化与参考面，不凭功率反推相位，不把误差振幅平方当作候选与参考的功率差。

为区分整体幅值不足与形状／相位错误，允许额外计算场范数比和复相关系数；它们只描述冻结场：

```math
\rho_j=\frac{\lVert E_{s,j}\rVert_{L^2}}{\lVert E_{s,*}\rVert_{L^2}},\qquad
\chi_j=\frac{\langle E_{s,*},E_{s,j}\rangle}{\lVert E_{s,*}\rVert_{L^2}\lVert E_{s,j}\rVert_{L^2}}.
```

本式内积采用第一项共轭。使用 UFL 时按其实际约定转换，并以小复数组测试验证；近零候选下 chi 标 undefined。**不按相关系数校相位、缩放候选或构造改进解。** R/T/A等既有失败场量优先引用已绑定记录，只核对必要一致性；本批不重新复制整套功率报告，更不产生 official 候选物理结果。

## 6. D3：同一个误差在原方程里怎样被看见

### 6.1 拆原体／端口作用，不拆散后重新凝聚

原未凝聚增广方程按现有代码的符号为体行 V u+B alpha，以及端口行 −D_p u+H_p alpha。这里 D_p 是端口提取作用，**不是 V8 的列尺度对角矩阵**，H_p 也不是凝聚后的 Hhat。它们已经包含实际坐标、相位和归一化。

令 delta u=R0 e，定义 a=V delta u、c=B e_alpha、d=D_p delta u、h=H_p e_alpha。用已有 `uncondensed` 对 (delta u,0) 和 (0,e_alpha) 分别作用即可获得这些量；不要复制一个新的物理算子。验证：

```math
\begin{bmatrix}a+c\\-d+h\end{bmatrix}
=r_{{\rm aug},j}-r_{{\rm aug},*},\qquad
n_j-n_*=a+B H_p^{-1}d.
```

第二式 n 是**未归一化的 native 残差向量**，不是 relative scalar；现有 audit 正是用 r_FE−B H_p^{-1}r_port 得到 native。允许复用原40维 H_p 求解作为既有审核的一部分，不形成新逆，不将它移进loss／PC，不解新的目标方程。

要分别保留 a、c、d、h 及其和的范数和复交叉项。抵消比例定义为：

```math
\eta_{\rm body}=\frac{\lVert a+c\rVert_2}{\lVert a\rVert_2+\lVert c\rVert_2},\qquad
\eta_{\rm port}=\frac{\lVert-d+h\rVert_2}{\lVert d\rVert_2+\lVert h\rVert_2},\qquad
\lVert a+c\rVert_2^2=\lVert a\rVert_2^2+\lVert c\rVert_2^2+2\Re(a^Hc).
```

分母为零／近零时按已登记规则标 undefined 并报告绝对值。小比例只说明这个固定方向上的作用存在抵消；**物理上正常的平衡也会抵消，不能单凭该数值宣布病态、舍入灾难或伪模态**。不能直接相加不同空间的体行范数与端口行范数后称作物理能量。

在组装后的原 Schur 行上另报 trace-row 与 port-row 的残差平方份额。所有共享贡献先累加、再求范数；不拿单元残差平方和代替全局残差平方。trace／内部行分组是系数空间统计；只有 D2 的单元场积分才能定位物理区域。

本批不新增 curl／mass 分别凝聚，不用 `Schur(curl)-k0² Schur(mass)` 代替原 S。若数据指向 V 内部仍有未定位抵消，结论标“体算子内部未分解”，作为后续取舍依据，而非当场增加新算子装配或波数扫描。

### 6.2 一个有界的方向敏感性指标，不做谱求解

对五个既有误差，仅记录 norm(e)、norm(Se)，并在分母非零时与同坐标参考方向比较：

```math
\gamma_j=\frac{\lVert S e_j\rVert_2/\lVert e_j\rVert_2}{\lVert S z_*\rVert_2/\lVert z_*\rVert_2}.
```

该量依赖当前代数坐标和单位，只是方向增益比，**不是最小奇异值、条件数或普遍误差界**。不得做 global SVD、shift-invert、全局特征值、随机大探针集、新的 Jacobian谱或 Krylov 轨迹。也不以准确误差方向作最优修正后声称求得新解。

## 7. D4：只作证据能支持的归因，结束这一有限批次

| 观察 | 允许的结论 | 不能推导 |
|---|---|---|
| D1恒等式或恢复不一致 | 数据身份／实现有具体问题，先最小修复受影响诊断 | 直接调网络超参掩盖错误 |
| 场范数小、与参考相关性明确 | 当前候选的散射幅值／相位／形状有定量缺口 | 从系数范数直接宣称物理L2或能量误差 |
| 大场误差对应较弱原方程响应 | 该固定方向是当前残差目标／有限迭代的困难证据 | 全系统必奇异、所有PC或NN不可能 |
| 原体／端口贡献显著抵消 | 具体分块与方向值得后续针对，须结合固定残差与场 | 自动批准修改端口物理或重加权loss |
| NN和非神经误差结构不同 | 提供表示／优化分工线索 | 未做表示试验就认定网络太小或八载波错误 |
| 未能区分机制 | 明确 INCONCLUSIVE 和尚缺证据 | 为交付强行宣布唯一根因 |

完成后只提出**一个**有证据支持的下一最小试验及其收益／成本假设，不自动实施。可以建议针对端口处理、训练尺度或表示的后续改动，但不得重开 p4 强逆、盲扫超参或把本批默认延伸成又一批泛化诊断。若这些固定状态仍不能支持选择，就报告未确定并交回审阅，不为了得到某个结论继续消耗剩余预算。

D0–D3全部适用检查完成时标 `FIXED_ERROR_DIAGNOSTIC_COMPLETE`；缺向量或身份未闭合则 PARTIAL／BLOCKED，逐项说明。这个状态不是 solver PASS。原求解门限1e-6、场／散射／curl／复通道1e-4、功率与能量原门限全部保持；本批不产生新候选，不做p-enrichment，不把已有参考升级为连续极限。

## 8. 执行、测试、资源与停止条件

授权顺序为 D0→D1→D2/D3→D4，前置通过可直接执行，无需逐小步确认。新增纯数组 helper 测试覆盖非零仿射特解、非零参考残差、复数符号、端口与native恒等式、交叉项和近零分母；配对按原 operation-scaled1e-10，实际场／分区积分一致性按1e-10并报告数值尺度。失败不能改阈值过关。

只读重用六个状态和原packet。至少统计 S、Sᴴ、uncondensed、recover、Hp审核作用、FE积分／JIT及I/O次数。**本批实际pilot的S与Sᴴ调用合计最多128次；uncondensed和recover各最多128次，既有小Hp审核调用最多128次。** 这是含自检／复算的上限，不是要求跑满；同一数据复用已经计算的结果。没有新solver loop或optimizer step，网络不训练、不给参考做监督拟合，不重复batch性能测试。

允许复用一次轻量FE验证环境作D2积分；禁止调用会重新构造全局因子／完整求解器的旧入口。仅增量实现必要helper、参数化stage和checker，数值核放src；复用run_case和shared watchdog，不复制每个状态一套runner。正式FE／资源阶段经 `python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`，dat明确同一个固定operator和状态inventory，不藏多模型扫描。

受控共享CPU授权继续，只覆盖Task042原已有heavy禁用／独占要求：其他heavy存在不自动阻塞。现场核查邻worker、监督器和SMT后选空闲物理核；MPI1、数学/Torch线程1、DataLoader0、自有nonblocking锁、内部顺序、nice10／idle I/O仅作用自身。独立环境／缓存／TMP，原库只读，不装新环境或升级ABI，不用GPU、不更改邻任务或其锁／环境／亲和性／优先级／watchdog。

整树RSS hard16GiB／warn12GiB、自身swap0、无OOC；系统reserve=max(128GiB,effective_total的10%)、邻增长128GiB及本任务余量继续保留，磁盘自由至少50GiB、artifact累计上限20GiB。没有cgroup委派时如实用原0.5s树采样监督，不承诺连续内核限额或绝对零干扰。资源触线只停止自身后代，紧急停止优先安全，不为补齐图表越界。

[截至V8累计账](outcomes/records/resource_costs_v8.json)为9804.434395463672 s。**本批新增数值有载及有界辅助检查总量最多3600 s，并同时受V6起累计36000 s剩余额度约束，取较小者；失败、JIT、最小修复重放和发布检查均计入，不重置历史预算。** 这是停止预算，不是预计耗时或允许自动执行3600秒。完整主流程与子计时不重复相加，process-tree峰、数组bytes和全会话未测范围分别说明。

若发现明确的新实现错误，允许一次最小修复并只重放受影响诊断；现有求解不收敛不是bug，不重跑V7/V8或准确参考。部分数据不可用时完成其它独立部分；无后台等待／无限轮询，不因结果不符合期待就增加状态。

## 9. Git、交付与 Response V9

开始核对branch/HEAD/upstream/worktree及本任务活跃run；安全获取同分支，不reset/强制覆盖、不触动邻工作树。实施前提交clean源码并绑定真实run source、原dat、resolved_config、manifest、physical/material/mode/array hashes和环境资源。文档HEAD不能冒充运行source，活跃受检run期间不为文档改变其HEAD。

建议两次实现提交：诊断helper／纯数组tests；参数化stage／身份与独立checker。第三次提交compact结果与response。必要最小修复单列提交，不amend，不修改旧task/review/response/负结果，不改ordinary默认、不整体merge其他分支。

必须有 `response_v9.md` 和 `outcomes/frozen_error_localization_v9.md`，以及下列轻量证据；同义字段可合并，避免复制多份漂移的来源：

```text
outcomes/records/frozen_state_inventory_v9.json
outcomes/records/error_identity_checks_v9.json
outcomes/records/field_error_components_v9.csv
outcomes/records/region_error_integrals_v9.csv
outcomes/records/equation_components_v9.csv
outcomes/records/port_error_components_v9.csv
outcomes/records/gate_decisions_v9.json
outcomes/records/run_index_v9.json
outcomes/records/resource_costs_v9.json
```

保留少量原始向量在ignored目录并hash绑定，Git只收表格和必需小摘要；本批不新生成VTU云图或大量图片。summary/test_summary/changed_files、development_progress和model_registry只新增本批及链接，保留旧正文和保护区。新公式用fenced math，表格列一致；检查本地与GitHub rendered view，无法取得网页则明确未核验，不能假称渲染PASS。

Response V9先报完整HEAD、base、工作树状态和实际可用状态数量；随后说明误差恢复是否齐次、残差恒等式是否闭合、散射幅值／形状和区域／端口分布、原方程分量抵消及方向增益能支持什么，哪些归因仍未知。明确没有新求解／训练、没有新LU、reference仅offline diagnostic；列出全部费用和未运行项。最后给一个下一最小建议，不能提出一串自动推进任务。

仅推送 `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；有限批次完成或触发真实停止条件后等待ChatGPT review，不merge master或其他分支。**本次允许一次固定误差定位，不授权改loss、改网络、续训、制造新PC或启动最大0.7nm模型。**
