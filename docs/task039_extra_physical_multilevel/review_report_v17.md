# Task39extra Review V17：有界BLR压缩—精度试验与条件式完整三维验证

## 0. 决定、身份与执行权限

**本轮不换PC，也不把V16的3%内存下降追溯改判为通过。先核查BLR实际覆盖的因子范围，再以固定顺序检查最多两个新增压缩阈值：先1e-3；仅在它确实节省内存、但修正质量不足时补1e-4。出现合格配置就停止选参，立即进入完整p6原始模型和条件非可分缺口。没有合格配置则收口，不开启下一串epsilon。**

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task39extra
review_date            = 2026-09-14
reviewed_base_SHA      = d40f7d39fbbac974efbcaf94d89a439e4beb88eb
previous_review        = review_report_v16.md
previous_response      = response_v17.md
accepted_exact_source  = 6a8b273c383d5bd9da37d6630a48bd24d6a90cce
accepted_tau1e-5_source = 24bd767e6b0d158ac20deb360a135f10c0611ede
new_batch_identity     = review_v17_p4_blr_tradeoff
new_profile            = physical_p4_blr_tradeoff_v17
execution              = T0 -> T1(1e-3) -> conditional T2(1e-4) -> conditional T3/T4 -> T5
response_required      = response_v18.md
time_policy            = observe_only
ordinary_default       = unchanged
master_merge           = NOT_APPROVED
```

本轮要回答的blocker是：**已知能够给出强p4修正的全局物理响应，能否在明显减少存储后仍然支撑完整三维求解？** 这是0.7 nm、任意非可分三维、约2 TB目标中的过渡可压缩性试验，不是无全局factor的生产架构。仍只在16 GB笔记本上执行13.5 nm、MPI1，不运行5 nm/0.7 nm，不影响同步工作线，不用准二维或Hybrid代替。

用户本轮明确同意这一有界后续。因此本文只对新profile替代V16的“禁止新增epsilon”限制；旧V16 profile、checker、门槛、费用和负结果保持不变。保留V16对原p4全局BLR factor的研究例外，不允许A6整体LU。读根/目录AGENTS、仓库原则、task、V16、最新response/summary后连续执行；中间小检查不逐次等审阅。实际HEAD若已改变，先核对新增提交，不覆盖新的任务或结果。

## 1. 已接受的证据，不重复制造基线

来源：[Response V17](response_v17.md)、[V16 compact](outcomes/records/p4_blr_v16_compact.json)、[V16 decision](outcomes/records/p4_blr_v16_decision.json)、[原Q1准确对照](outcomes/records/p4_schur_v14_comparison.json)。以下是远程已报告并独立checker核对的数据，不是本review新运行。

| 指标/单位 | 原p4准确LU | BLR tau=1e-5 | 当前结论 |
|---|---:|---:|---|
| 全过程树RSS，B | 2,825,973,760 | 2,741,243,904 | ratio=0.9700174654，只降约3% |
| factor-live树RSS，B | 2,825,973,760 | 2,741,243,904 | 包含仍存活的矩阵/公共对象/评价，不是factor-only RSS |
| 数值因子条目 | 53,417,584 | 53,040,280 | 条目只降0.7063%；不等于allocated降幅 |
| 后端allocated upper，B | 2,343,000,000 | 1,693,000,000 | 后端字段，不替代RSS |
| 后端used upper，B | 1,382,000,000 | 1,420,000,000 | 增加38,000,000 B |
| numeric自身时间，s | 18.4888 | 19.9465 | 不等于完整构建/验证耗时 |
| 完整控制monotonic，s | 536.4680 | 571.5147 | 两侧完整采样；非完整p6求解 |

| 固定输入 | tau=1e-5原A4相对残差 | 场L2相对差 | scaled-curl相对差 |
|---|---:|---:|---:|
| A2R160_BAL_H_p4_01 | 0.01274778723 | 0.00046894138 | 0.00046501473 |
| A2R160_BAL_H_p4_02 | 0.00071668691 | 0.00063819706 | 0.00063300628 |
| LIGHT448_BAL_H_p4_09 | 0.01767784456 | 0.00051846030 | 0.00051422891 |

三输入各一次MatSolve，ICNTL(10)=0，原残差恒等式约1e-17。S3/S4未运行，不能称BLR完整外层成功或失败。V16结论`STRONG_BUT_INSUFFICIENT_MEMORY_GAIN`保留；不重跑1e-5，不重建p6参考，不复活失败的Schur接口/宏块/recycling路线。

## 2. 冻结对象、控制与参考隔离

物理、材料、p/h、网格、积分、端口及输入身份沿V16：13.5 nm、1度掠入射、azimuth0、s；50×25 nm周期单胞、z=-10..130 nm、原Si/air；252 hex、p6/h10、双Floquet、80个DtN条目。p4独立/存储/增广行数为48960/53084/53164；p6独立/存储行数为164592/173802。最终缺口沿用V5冻结的8个canonical cell keys对应材料实体，不重新选形状。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
ordered_mode_sha256   = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

沿用已资格化Linux complex128/int32、MPI1、线程1；DOLFINx/Basix 0.10系列、PETSc 3.19.6及已链接MUMPS 5.6.2身份按V16复核，不由共享库文件名猜版本，不升级ABI。三份RHS、参考、map和各hash直接复用合格索引；每份新dat重新生成input/resolved/source身份。

| 数值控制 | 新批固定规则 |
|---|---|
| CNTL(7) | T1为1e-3；T2仅按第5节为1e-4；选定后在original/notch固定 |
| ICNTL(35) | 2，在symbolic前设置并读回；压缩存储用于回代 |
| ICNTL(10) | 0；禁止后端隐藏迭代改进 |
| ICNTL(36/37/38) | 延续V16实测0/0/600；不调BLR变体或贡献块压缩 |
| ICNTL(39/49) | 39公开读回不可用如实保留；不展开49调查，不直接访问私有结构 |
| ICNTL(22/31/32) | 均为0；无OOC、丢factor或前置消元变体 |
| 排序/主元/缩放 | 原Q1/V16策略，实际选项/可得排列与缩放身份记录；不新加shift、reorder或变尺度 |
| 配额 | V11原symbolic-sized公式，取该版本满秩/BLR估计的较保守值；不按已知结果回调 |
| 数值存储 | complex128；不加混合精度、量化或新后端 |

CNTL(7)是局部块压缩的绝对截断阈值，不是原A4相对残差或场精度保证。因而只改变该参数，保持原物理算子和尺度；较宽阈值的误差与内存不作线性、单调或连续区间保证。[S1–S2]

沿用原端口增广，不显式展开稠密DtN，不形成显式逆：

```math
A_4=V+BH^{-1}D,\qquad
\mathcal A_4=\begin{bmatrix}V&B\\-D&H\end{bmatrix},\qquad
F_\tau(g)=\left[\widetilde{\mathcal A}_{4,\tau}^{-1}\begin{bmatrix}g\\0\end{bmatrix}\right]_{\rm FE}.
```

一次F_tau仅一次已建factor的MatSolve。三份非零控制输入各一次；零输入可直接返回零并计数为零。不加p4内层Krylov、外部迭代改进、MR缩步或参考辅助初值。参考只用于评价及预先写死的准入分流，不进入factor/PC。三输入共同决定准入，因此第三输入不宣称是统计独立、从未用于选型的留出测试。

## 3. T0：先读压缩覆盖统计，不再建立诊断平台

首先复用V16原始MUMPS日志、controls与128项相关测试资格。优先读取`Number of BLR fronts`和`Fraction of factors in BLR fronts`；front是分解过程中形成的局部消元矩阵，覆盖率指进入BLR处理的满秩因子条目占比，不是实际压缩率。[S1]

同时记录每次分解的INFOG(29/35/9)、RINFOG(3/14)、实际ordering、可得最大front/延迟主元统计及allocated/used。按本机5.6.2字段定义解释单位和负数编码，不把ICNTL(38)估计值当覆盖率或实际压缩率。已有日志缺coverage时，只在T1的必要分解中启用适量标准统计输出并采集；不要为补这个字段重新分解1e-5。该版本确实不输出时写`coverage_unavailable`，总条目/RSS/质量仍可用于准入。

设同一记账下满秩条目N中比例f进入BLR，这部分保留比例q；忽略元数据且其余部分不变时，有如下说明性关系：

```math
N_{\rm compressed}/N=(1-f)+fq.
```

f小提示当前处理范围受限；f大而实际条目比接近1提示范围内压缩很少。此式只解释条目，不直接预测RSS；改变阈值可能影响数值主元等细节，不能用旧f给新运行或任意网格作严格容量界。 **coverage不是新设的准入整数线：不因字段缺失或主观认为f偏小而无限停审；只要既有BLR支持和安全检查仍成立，就完成一次T1，用其实际收益裁决。**

先核对canonical worktree/branch/HEAD/clean source、实际ABI、材料、网格与mode keys、MemAvailable/cgroup/宿主卷空间、swap、disk与watchdog。旧EIO已有恢复证据且当前预检正常时不重做历史恢复研究；再次真实I/O或监控错误则停止，不无限重试。

## 4. T1/T2：同一个原p4问题上的有限控制

T1用tau=1e-3建立一份原p4增广factor，对上述三输入各裸回代一次，先原子保存结果再进入下一输入。T2仅按第5节触发，规则相同但tau=1e-4。两份候选factor绝不同时常驻。

每份保存原g、输出、native A4作用/残差、增广上下残差、场/curl的原范数、factor调用差值、选项读回、matrix/RHS/参考hash，以及以下恒等式核查：

```math
e_{\rm aug}=\begin{bmatrix}g\\0\end{bmatrix}-\mathcal A_4\begin{bmatrix}c\\\alpha\end{bmatrix}
=\begin{bmatrix}e_{\rm top}\\e_{\rm port}\end{bmatrix},\qquad
g-A_4c=e_{\rm top}-BH^{-1}e_{\rm port}.
```

恒等式操作尺度误差≤1e-10；map/slave-zero及输入不被修改的检查沿用。真实rho始终除以原g范数，不以大端口RHS稀释；P64场/curl相对差均对匹配参考。正确性缺失不得混同于单纯质量不足。

### 4.1 避免重复构建，但不能破坏资源对照

优先复用已合格公共内核、JIT缓存和现有hash-bound矩阵缓存；不要为了两次测试新建序列化平台。默认采用V16同一fresh-worker管线，旧Q1与1e-5无需重跑。没有可直接复用矩阵时接受必要的重新装配并计费，不假装旧进程销毁后factor还在。

若确实改为加载矩阵、改变公共对象或生命周期，先明确对照scope；**最多补一场同路径、同选项的未压缩p4 control**，作为该新scope分母。它不是新建p6参考，且各RHS须满足原A4≤1e-10、场/curl≤1e-8。旧1e-5不同scope的时间/内存只能列历史背景。不能拿新warm加载峰值除以旧cold组装峰值，或给每个阈值分别新建一套基线。

候选默认各用独立fresh worker，避免前场分配器高水位污染下一场RSS。共享缓存的生成、加载、转换和全部重复构建成本分列且进入总费用；非重叠阶段的峰值只在都有实测且确实非重叠时取max，不把缺失的构建峰值当零。

### 4.2 四种存储指标必须并列

| 项目 | 必需口径 |
|---|---|
| BLR覆盖与内容压缩 | fronts/f（可用时）、INFOG29/35/9及条目比；本次理论满秩分母与旧Q1分别说明 |
| 后端资源 | symbolic estimate、真实配额、allocated/used、浮点工作量；不冒充RSS |
| factor-live | post-numeric至第三输入评价结束，factor及必要矩阵仍存活的连续parent树RSS/PSS最大值 |
| 完整workflow | 从启动、公共准备、装配/加载、分解、三输入、保存至清理的树RSS/PSS峰值；全部同时存活对象及workspace |

原Q1、旧1e-5、T1、条件T2用一张表；每列标measured/derived/not_run及来源。保存setup、symbolic、numeric、纯MatSolve、native检查、评价和总时间，避免把端口检查时间说成纯回代。缺统计字段不插值或推测，结果包不得等到整个批次成功才保存。

## 5. 唯一分流：两项独立Gate，不按结果再修改规则

定义Q为三输入均有限、正确性核验通过，且每份**rho≤0.5、L2≤0.25、scaled-curl≤0.25**。定义有效内存比较下的M为：

```math
M:\quad R_{\rm peak}\le0.90\quad\text{或}\quad
\left(R_{\rm live}\le0.80\ \text{且}\ R_{\rm peak}\le1.05\right).
```

R_peak/R_live沿第4节同口径未压缩p4分母；不以allocated、used、条目减少替代。还须证实本次BLR真正启用、实际条目压缩存在。10%/20%和质量线是固定工程筛选，不是普遍收敛必要条件或统计显著性判据。时间记录但不作准入否决。

| 当前结果 | 后续唯一动作 |
|---|---|
| T1：Q=true、M=true、实际压缩存在 | 选定tau=1e-3，跳过T2，直接T3 |
| T1：正确性/资源/证据完整、M=true且有实际压缩，但仅Q质量线未过 | 授权一次T2=1e-4，检验能否恢复质量 |
| T1：M=false，不论Q是否通过 | T5收口；不试1e-4、1e-2或其他阈值 |
| T1：非有限、breakdown、分解失败、资源停止、选项失效或比较无法建立 | 分类收口；不得把失败自动转换成“补中间点”许可 |
| T2：Q=true、M=true、实际压缩存在 | 选定tau=1e-4，直接T3 |
| T2：不满足上述全部条件 | T5收口；不插入中间值，不返回1e-5长跑 |
| T3/T4数学不合格 | 结束选定配置；不退回T2、另一tau、refinement或不同restart |

因此本批正常路径最多两个新增阈值控制、最多一个选定配置的完整original和一个条件notch。用三输入作选择只限本表，不允许根据某一项误差连续调整tau。参数顺序是固定实验设计，不宣称取得全区间最优点或严格证明区间内没有解。

**不用全部因子条目减少很大来掩盖RSS不降，也不用RSS偶然下降来宣称大量因子被压缩。** 若条目压缩明显但M不通过，说明当前完整工作集收益不足；若条目基本不变但Q很好，说明强度主要来自近乎满秩的存储，本批应停止而非再次包装成突破。

## 6. T3/T4：出现合格点就让真实p6裁决

当前V16 runner的S3/S4仍为NOT_RUN占位。不得把admit字段改成true就冒充接线完成。复用已有通用完整p6 runner、BAL_H/H6、独立物理后处理与watchdog；只增加新BLR inverse适配和显式profile/输入。数值核心仍放src/solvers，不复制几千行Schur runner；用小型mock/复数代数先确认dispatch及禁用旧stack，不为此重跑旧PDE。

选定tau之后，一次BAL_H依旧为：

```math
\begin{aligned}
g_1&=P_{64}^Hq,& c_1&=F_\tau(g_1),&z_c&=P_{64}c_1,\\
s&=H_6(q-A_6z_c),&g_2&=P_{64}^HA_6s,&c_2&=F_\tau(g_2),\\
z&=z_c+s-P_{64}c_2.
\end{aligned}
```

两次p4调用各一次MatSolve，没有旧四步I4/C_U/S-p2/recycling/Schur接口层；H6自身的已有辅助层级不改。g2必须在线从当前c1/H6生成，不能输入旧反馈packet。记录实际epsilon1/epsilon2和粗层闭合，操作尺度1e-8；闭合不是强度证明。

T3从零初值，right FGMRES32。每8步原A6真残差/计数/资源，每32步先存解再评价参考。 **64步时rho>0.10停止；否则同一个KSP继续至原A6≤1e-6或最多2048步。** 已经收敛就立即后处理，不为填表跑满。时间仍observe_only，无600秒、25/30秒、1800/5400秒或总wall终止线；非有限、breakdown、资源、安全、用户停止有效。

T3完整通过后立即T4同配置冻结缺口，重建该材料的矩阵、缩放及BLR factor；tau/restart/次数/方法不变，不搬用原始factor。T3失败不跑缺口；T4失败保留几何局限，不自动修成容易模型。T3/T4需要fresh factor时照实计费；这不属于新增tau控制，也不允许先以准确factor求新初值。

| 最终Gate | 保持不变 |
|---|---|
| 原A6方程 | full explicit norm(b-A6x)/norm(b)≤1e-6，递推与真实值并列 |
| 同离散场 | L2/scaled-curl≤1e-4，复E/H与同位置近场，无拟合整体相位 |
| 功率 | R/T/A/A_volume各自参考绝对差≤1e-5 |
| 独立守恒 | R+T+A_volume−1与A−A_volume绝对值均≤1e-5 |
| 全部80模式 | 复幅值向量相对差≤1e-4，逐通道功率最大绝对差≤1e-6 |
| 来源与资源 | input/source/physical/mode/artifact完整，全过程树RSS/PSS/时间、zero job swap、全局交换无增量、后代清场 |

成功求解后保存最小recovery packet，销毁KSP/BLR factor及无用矩阵、确认RSS下降，再恢复后处理；控制实验为反复调用对照须留factor至所有评价完成，两种生命周期分开。没有同scope的新完整exact-p6对照时不宣称全p6节省百分比，只报完整BLR实测和历史背景。

## 7. 资源、执行次数和实现边界

| 项目 | 本批固定边界 |
|---|---|
| 树RSS cap | 启动min(8 GiB,effective_available−reserve)；运行沿已修正动态检查，不重复扣当前RSS |
| reserve | max(4 GiB,15% effective_total)，真实cgroup/宿主卷/磁盘预检，一次一个heavy |
| 数值常驻库存 | 合计≤6 GiB，含全部矩阵、factor、H6、传递、缓存和向量 |
| 临时工作集 | 最大同时1 GiB，含后端/CSR/评价/保存副本，不叠加多个独立池 |
| 后端配额 | 原V11规则，原矩阵尺度与控制保持；不能用预测压缩率放行，也不另调工作数组来制造收益 |
| 正常控制次数 | T1一次、条件T2一次；只在scope不匹配时一个未压缩control；不重跑1e-5 |
| 正常完整模型 | 选定tau的T3一次、条件T4一次；不重复相同前缀或给失败tau补外层 |
| 实现bug | 整批最多一次有证据修复重放，只重放受影响阶段/同tau；不当作新增选参额度 |
| 其他失败 | 真实数学、资源、I/O/监控不合格收口；不自动抬cap、换精度、升级ABI或循环恢复 |
| 时间政策 | 父launcher/worker/PC/checker统一observe_only；保留心跳、各时钟及实耗，无人为短timeout |

新batch `review_v17_p4_blr_tradeoff`只分隔本次授权和计数，旧V14/V16账本hash、费用、政策占用和unknown只读引用。不得把新batch说成旧成本清零；不重新实现整个恢复/调度平台。正式耗时按父workflow、不重复叠加子阶段；工程编辑/测试/监督单列，未知不写0。

建议只对既有configured BLR factor、runner/profile/schema、checker做参数化：新profile接受本表允许tau，旧V16仍强制1e-5，不能全局替换硬编码导致历史checker接受不同配置。一个dat只对应一个明确tau/阶段，选择结果写入hash-bound decision，后续模型读取并核验所选值，不按运行次数暗中切换。

集中测试默认不变、允许值与非法值、T1/T2分流全部分支、压缩字段与比例单位、CNTL在symbolic前生效/每次读回、一次MatSolve且无refinement、实际map与复对偶、原残差恒等式、references隔离、S3/S4真实dispatch、observe_only与非时间安全规则、异常清理。沿用未变化的128项旧资格，最终改动后运行直接相关集合、compileall、diff及文档检查；缺Ruff/full pytest/CI如实记录，不为此装库。

## 8. T5交付、终止后选择与提交计划

```text
response_v18.md
outcomes/p4_blr_tradeoff_v17.md
outcomes/records/p4_blr_tradeoff_v17_compact.json
outcomes/records/p4_blr_tradeoff_v17_decision.json
outcomes/records/run_index.json                    # 增量
outcomes/summary.md / outcomes/test_summary.md
```

同时增量更新development_progress、development_model_registry和selective merge边界。提交顺序为：显式新profile/参数化/真实外层接线及定向测试；T1和条件T2记录；条件T3/T4结果；response/总览收口。每个正式worker前clean source。每份RHS与阶段及时原子保存，raw matrix/factor/场/完整日志只放ignored；Git只存轻量结果、路径和hash。

T5必须先回答：**覆盖范围是什么、改变tau实际压掉多少内容、同scope内存有没有收益、原p4修正保住多少、完整p6及缺口是否通过。** 原LU、旧1e-5、1e-3及条件1e-4分列，不填未运行数据。不用一条allocated下降代替完整结论。

| 本批最终证据 | 后续唯一建议的类型 |
|---|---|
| 一个tau满足内存/质量且original/notch通过 | 保留过渡候选；提出一个与5 nm线协调的后续规模点，不自动运行 |
| 条目有明显压缩，但本批允许点无法兼顾质量或RSS | 关闭本批阈值路线，指出误差/工作集限制；不再建议下一epsilon |
| 较宽阈值仍几乎不压缩，coverage亦低 | 记录当前BLR覆盖/分解组织限制；后续只有改变表示或分解组织才构成新假设，不自动实施 |
| 较宽阈值仍几乎不压缩，但coverage较高 | 记录已覆盖块在该尺度/阈值下秩仍高；不称所有频率或全部BLR不可压缩 |
| coverage缺失 | 如实说明未区分覆盖与秩限制；已有条目/RSS/质量仍能支持是否继续的工程决定，不为该字段重跑 |
| 工程/环境/资源阻断 | 精确记录阶段、实值、限值、缺件；不把未执行写成数学失败 |

只有原始通过、缺口失败时，保留原始固定案例资格，不宣称非可分鲁棒性。无合格点是停止这次有限设计，不是证明整个参数连续区间无解。所有成功仍为同离散资格，不替代p/h或5 nm、0.7 nm验证。2 TB不能只靠全局factor轻微压缩解决；通用Full3D的分布式、matrix-free、可扩展PC及有界粗问题主线保持。

## 9. 依据与适用边界

- 仓库事实：[最新回应](response_v17.md)、[当前总览](outcomes/summary.md)、[V16决策](outcomes/records/p4_blr_v16_decision.json)、[上一数值合同](review_report_v16.md)、[仓库原则](../repository_work_principles.md)。原始数值SHA在第0节，旧结果不改写。
- [S1] [MUMPS官方用户手册](https://mumps-solver.org/doc/userguide_5.9.1.pdf)，§5.20.2–5.20.3：绝对截断、BLR fronts/覆盖率和条目统计的概念。本review查阅的是5.9.1说明；实际字段/默认/能力必须沿已核验5.6.2，尤其不引入新版本默认ICNTL(36)或新精度控制。
- [S2] [PETSc MUMPS公开接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：控制与统计接口分类，不替代本机读回，也不保证当前Maxwell收敛。

**本批只新增一个有分流的有限问题：1e-5端几乎满秩但修正很强，向1e-3及唯一条件中间点移动后，能否取得值得完整三维验证的存储—质量折中。数据给出答案后立即转入完整模型或明确结束，不继续逐轮微调。**
