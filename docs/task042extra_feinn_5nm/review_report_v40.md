# Review V40：结束容量证明循环，批准固定秩神经核的交替线性求解试验

## 0. 裁决与身份

**接受 V40 已完成的内部矩、完整谱、固定特征与独立检查；保留 NO_VALID_FE_CAPACITY_CERTIFICATE。这个状态不是“没有做完”，也不是“r8 已不可能”。不追加一轮研究任意权重与 1e-15 nm 几何扰动的统一证明，不重复旧训练或 oracle。本报告明确批准一次改变训练分解方式的实际试验：保持 r8 和原 Maxwell 方程，将单个神经核的线性输出系数作为条件线性子问题求解，再更新非线性隐藏特征。**

要消除的 blocker：三核乘积中的线性系数和非线性特征一直一起交给通用优化器，尚不知道利用“固定其他核后，当前输出层严格线性”的结构，能否在低存储下产生有效的全场更新。该问题不能由容量必要条件回答，也不能靠原样增加 Adam 调用回答。此为有界研究授权，不是生产候选已成立，更不是保证收敛。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD   = 80d65063fc82592baffc5f479635aaba450a2eff
latest_commit_time     = 2026-10-10T10:12:47Z / 2026-10-10 18:12:47 +08:00
review_date            = 2026-10-10 Asia/Singapore
previous_review        = review_report_v39.md
reviewed_response      = response_v40.md
campaign               = V41_FTT_CONDITIONAL_CORE_SOLVE
required_response      = response_v41.md
new_total_window_s     = 43200
research_authorization = APPROVED_BOUNDED_NUMERICAL_EXPERIMENT
ordinary_default       = UNCHANGED
production_merge       = NOT_APPROVED
```

最终目标仍为原尺寸 0.7 nm、任意非可分三维周期单胞、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN、复 E/H/衍射/体吸收；十进制 2e12 B 是整机内存，须保留系统余量，ownswap/OOC=0，单场必要准备至完整验收不超过 172800 s。当前没有证据证明本神经路线可承担该交付。本批 12 h 是研究上限，不是目标 48 h 成绩。

本报告覆盖 Review V39 的“本批仅诊断、不得训练”及 Response V40 的等待授权状态，仅对以下 V41 实验生效。旧稠密波库、原 r8 全参数 Adam/L-BFGS 原样续算仍关闭。本支只做神经；不恢复 W0/W1、全口面、模式恢复、传统 Maxwell PC、存储系统或主线接入，不修改或给 Task42、主线、dot、master 及其他工作树派活。新方法仍是本任务神经参数训练的 opt-in 实现，不新建执行分支。

## 1. 审阅证据与结论边界

回读当前分支、Response V40、专题、独立 capacity_decision、summary、根规则与仓库原则，并比较上一审阅发布后的 5 次提交。核查 FTTField 的实际输出层结构。前版 review 从本会话挂载原件完整读取；原 task、目录 AGENTS 和执行补充使用远端未变 blob 与此前原文衔接，任务目录没有更新的 Review V40。未 SSH、未在工作站运行，也未在审阅端重算原大型 FE 数组。

依据：[Response V40](response_v40.md)、[专题](outcomes/ftt_capacity_decision_v40.md)、[独立裁决](outcomes/records/capacity_decision_v40.json)、[summary](outcomes/summary.md)、[V39 完整场](outcomes/records/full_numerical_gates_v39.json)、[V39 完整工作性能](outcomes/records/complete_performance_v39.json)。V40 张量/谱主要 source 为 9066ce669aca126753190a170cdc00a6079729f8，独立保存检查 source 为 a706d335d17ca534f8a36b53b33e79b9587d18b0；发布 HEAD 不替代数值 source。

| 对象；M5/5nm/384hex/p3/N31968/40端口 | 原记录数值 | 正确判断 |
|---|---:|---|
| 内部矩与独立 FE 积分配对 | 7.42856038896e-15 | 接口配对通过 |
| 内部矩能量占完整散射 E 能量 | 0.992386074567 | 不是完整场或 curl 验收 |
| 纯 r8 的条件性秩尾下估计 | 1.90261961344e-5 | 低于 E 门 1e-4；未排除，不等于足够 |
| native/fit 冻结隐藏函数条件性下估计 | 1.12480113846e-4 / 1.42785680139e-4 | 仅固定规范 Cartesian 图表；不推广到可训练隐藏层 |
| 原 J 最大非对角项 | 1.92220044999e-15 nm | 全权重秩桥接未闭合；不清零凑证明 |
| V39 native FTTNN 原残差 / 散射 E 误差 | 0.948212215045 / 0.999458825608 | 仍 FAIL；不是此次新测量 |
| V39 native Cheb 原残差 / 散射 E 误差 | 0.989534468620 / 0.999989164225 | 仍 FAIL |
| V39 隔离 fit 的 G 误差，NN/Cheb | 0.945276943861 / 0.0215169175885 | 有限监督拟合，不是前向解或全局最优 |
| V39 完整映射工作均值，NN/Cheb | 0.618107247244 / 0.607903906687 s | 加速成立；不等于同精度胜过 FEM |

V40 的 Basix 默认泛函规范不一致已同批修复；没有因该 bug 丢下数值工作。当前需要改变的是实际训练机制，不是继续修一个已经关闭的问题。小非对角量阻止的是一个“任意权重”证明，不能被当作约 100% 场误差的已证根因。

**结束以下循环：**不再补第三份容量审计，不根据未排除结果直接翻倍 rank，不把“目前没有生产方案”写成“连小型可证伪实验也不得开展”。新实验的依据是下面可直接验证的条件线性性，不是声称 V40 已证明 r8 充分。

## 2. 改变哪一步，以及不改变什么

当前场分量是三个核的有序矩阵乘积：

```math
E_s(x,y,z)=F_{x,s}(x)F_{y,s}(y)F_{z,s}(z).
```

神经核的两个隐藏层给出 16 个实函数，末层含 bias，共 17 个标量函数。固定这些隐藏函数和另外两个核时，当前核对其末层复系数严格线性。因此不必用几百次小梯度步去逼近这个条件子问题，可以直接以矩阵作用形式求一次最小二乘。随后允许隐藏函数更新，再重复。它可能避免乘积参数的部分优化困难，但不保证解决近相关性、原方程条件数或表示限制。

本实验称“交替条件线性核求解”，不是全局精确 VarPro，不宣称每轮求到了全部核的联合最优。核心借鉴分别是 [TT 交替算法](https://arxiv.org/abs/1304.1222)、[神经 PDE 的线性/非线性变量分离](https://doi.org/10.1016/j.cma.2022.115284) 和 [LSMR 的算子接口](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.lsmr.html)。没有移植 AMEn 的 SPD 收敛定理、rank enrichment 或可分材料前提；本案 A 非 Hermitian，原材料不压缩。

| 固定项 | V41 合同 |
|---|---|
| 物理/离散 | 原 M5、5nm、384hex、h1.25nm、p3、31968 复独立 FE、全部 40 端口、原 Si/air 缺口与背景 |
| 材料/边界 | 原正式材料记录、原 A/f、完整内部矩、Piola/orientation/owner、Floquet/DtN 不变 |
| NN | r=(1,8,8,1)，三轴原 sin MLP、9072 实参数；不改宽度、激活、seed、carrier |
| 强控制 | 原 Chebyshev T0..T18 同 r8、9120 实系数 |
| 积分 | 体/DtN q15，网络完整矩 q30，独立逐点 q60；不降低 q 或丢微小非零 |
| 目标 | 原 native 欧氏残差；不加 Riesz 因子、不换 loss 或分母 |
| 新授权 | 原核系数空间内的 matrix-free LSMR，以及学习路线的隐藏层更新 |
| 禁止 | 全 FE Krylov 完成器、全局 A/G 因子、A*A、N×P Jacobian、全局波列库、teacher/参考权重 |

[原模型](../../src/solvers/ftt_field.py)最后输出层的复杂系数数量可由实际布局核对：NN 的 x/y/z 分别 408/3264/408 复数，合计 8160 实线性参数；三轴隐藏层合计 912 实参数。Cheb 分别 456/3648/456 复数。它们是 derived 参数计数，不是内存或精度证据。

## 3. A：有限实现资格，完成后立即进入真实试验

### 3.1 条件线性算子和复共轭

固定一个轴 a 的隐藏层及另两轴全部参数，以 w_a 表示该轴末层全部复系数。当前散射系数为 c，定义 K_a 为只对该末层增量的完整 FE 映射：

```math
c(w_a+\Delta w_a)-c(w_a)=K_a\Delta w_a,\qquad
B_a=\frac{A K_a}{\|f\|_2},\qquad b=\frac{f-Ac}{\|f\|_2}.
```

每个核心子问题仅求：

```math
\Delta w_a\approx\mathop{\mathrm{argmin}}_{\Delta w}\|B_a\Delta w-b\|_2,
\qquad B_a^*v=\frac{K_a^*A^*v}{\|f\|_2}.
```

K_a 必须来自当前真实网络和完整矩，不能用容量审计的 Cartesian 张量替代；不依赖 V40 的秩桥接证明。保留真实几何与原验证过的准确点值后备。实际点值独立复验始终是最终依据。

通过当前核的线性输出直接计算 K_a 作用；不修改基点模型来模拟每次 Krylov matvec，不反复读写 checkpoint，不缓存 N×d_a 列。K_a* 从完整矩余切和核乘积共轭反向获得。复系数与原实虚成对参数准确转换；实 VJP 要组合成复伴随，不能误用仅 real 部分，也不能凭拼接半向量猜顺序。A 作用仍混合三个物理分量，不能把三个分量独立求解后声称原耦合问题通过。

复用已合格的 FactoredMomentMap/原 A/A*；旧逐点路径保留独立检查。仅重做新增的线性块/伴随/状态边界测试，不再跑完整旧加速 benchmark 或旧 oracle。

### 3.2 子问题求解与真实接受

使用现有环境的 scipy LSMR LinearOperator，complex128，damp=0、atol=btol=1e-8、conlim=1e12、maxiter=300，从增量零向量开始。现有版本接口不适配时允许等价实化为 2N×2d 的算子，不升级环境、不形成显式矩阵。可在小测试用稠密 SVD 作独立参照；真实 M5 不形成 B、B*B 或逆。

每次返回后独立计算原线性残差和 B* 线性残差，报告实际停因、迭代、norm/cond 估计与运算数。LSMR 的停止码或小法方程残差不是原 PDE PASS；到 300 次上限但方向有效时，允许检查并接受，而不是结束整批。

将增量实际写入候选模型，重新计算完整 c、原 A c，确认与 c+K_aΔw 配对≤1e-10，且原 loss 不增（比较裕量 1e-12×max(1,L_old)，在数值噪声内不计有效下降）。满足才原子提交；否则回滚该核心、保留负结果并继续其他轴。禁止通过缩短 residual 向量、换分母或用预测值覆盖真实值来接受。

每轴都从当前全部核出发，不能在扫完三个轴以后才应用同时计算的旧增量。线性性是单核条件性质，三个核同时变化时有交叉项。

### 3.3 必须通过的新增测试

| Gate | 要求 |
|---|---|
| 线性块 | 非零复数、纯虚方向、bias/全部三分量、x/y/z；c(w+δ)-c(w)=Kδ 相对差≤1e-10 |
| 伴随 | K/K*、B/B* 的复内积配对≤1e-10；至少三个非零见证 |
| 独立 LS | 小型非 Hermitian、满秩/秩亏/不同尺度例与稠密 SVD 的场/残差配对；不要求非唯一系数逐位相同 |
| 真 M5 | 每轴一个短子问题，旧逐点场与新映射配对；资格状态不得成为正式初值 |
| 隐藏梯度 | 非零态至少三个实方向 FD，稳定区≤1e-5；原梯度不伪称精确 reduced gradient |
| 状态 | 核更新/隐藏更新接受、拒绝、异常、重开；模型、缓存、c/r 与循环位置一致 |
| 标签/资源 | 故意读取 reference/fit/V40 张量被拒；无 N×d、大图或全局因子；真实几何后备有效 |

首次真实梯度更新前冻结 design 与实际参数顺序。允许优化不改变数学的核缓存、向量化、复共轭实现和作用复用；缓存绑定当前参数版本，隐藏/另一轴更新后自动失效。新代码进入 src，runner 只编排，不复制整套优化/监控系统。

## 4. B：三个同预算从零对照，明确识别神经增量

旧训练状态已证明有限流程不合格；本轮从原 seed4213701 的零散射初始化，不加载 V39 final、fit、V40 参考张量、旧波库或挑选历史 best。复用代码/算子文件不等于使用目标解。x/y非零、z末层为零；三核不能全部置零。三个正式分支的数据目录和新状态分开。

| 路线 | 线性核心更新 | 非线性隐藏更新 | 回答的问题 |
|---|---|---|---|
| FTTNN_CONDITIONAL_CORE_LEARNED | 三轴条件 LSMR | 每轮全部 912 实隐藏参数可更新 | 新神经训练机制是否真正求解 |
| FTTNN_CONDITIONAL_CORE_FROZEN | 同算法/同初始 NN | 隐藏层固定在原初始化 | 改善是否只是固定随机特征的线性代数 |
| CHEBTT_CONDITIONAL_CORE_CONTROL | 同算法，Cheb核系数 | 无神经隐藏层 | 同能力非神经函数核控制 |

NN learned/frozen 的所有初值逐位相同；Cheb 沿原固定初始化而非人为弱化。三条均 r8、完整物理、同核心预算。rank 相同不代表 NN/Cheb 函数族相同；必须同时报告 frozen-NN 消融，不能把线性求解带来的收益全部归给 NN。

一轮依次更新 z→x→y，下一轮反向 y→x→z，如此交替；零散射首轮必须先 z，否则 x/y 的零方向是数学结果，不是代码错误。每核心最多300 LSMR迭代。每条最多6个完整三轴轮次、18个核心访问、5400 LSMR迭代与7200s新增端到端墙钟，任一先到。所有 B/B*、A/A*、完整矩、缓存、真实接受和保存均计费；一次 LSMR迭代不等于一次训练 closure。

只有 learned 路线在每个三轴轮次之后更新隐藏层：固定当前末层系数，对同一原 loss 做 fresh L-BFGS，lr=1、history10、strong-Wolfe、max_iter10、max_eval20，实际 closure 硬计数≤20/轮。这里求的是固定输出系数下的普通隐藏梯度，不使用未成立的 envelope 定理。每轮 fresh 历史是因为核心系数已变，不能沿用上轮另一目标的 secant 对。隐藏更新真实 loss 不增才提交，随后下一轮重新求核心系数。拒绝或零更新保留并继续，不强制扰动制造“学习”。

一次完整三轴轮次后保存并审核 native/augmented/独立total；前2轮不因单核无下降停止。之后若连续2个完整轮次均改善不足1e-3，且原残差仍>1e-2，保存 BLOCK_ALTERNATION_STAGNATION 并完成其余路线与全场验收。该出口只关闭此配置，不能写成 r8 无解；到正常预算同理。小原残差若≤1e-8立即冻结作联合检查；严格场门未过，最多使用原剩余额度按同一原 loss 继续，不把参考误差向量或谱用于更新。

不准本批另试 rank/seed/宽度/载波/Riesz/人工吸收或新的 PC，不准调用全 FE 求解器补齐网络解。普通工程 bug 与算法停滞分开：前者同批修复；后者按上述有限规则得出结果，不伪装成 bug 重置预算。

## 5. C：独立完整验收与成本

每条正式终态从保存参数重新打开，由保留的逐点 FTT 模型+完整矩 q30/q60 重建，再独立 FE compare-only 读取原 V1 同 p3 参考。原准确参考 SHA256 为 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7，不重求 MUMPS，不加载监督权重。沿用原完整向量分母和近零规则，不拟合整体相位。

| 联合 Gate | 原阈值 |
|---|---:|
| native、增广、独立 total 原方程相对残差 | 各≤1e-6 |
| total/scattered E/H/curl、六点复场、四类完整复通道向量 | 各≤1e-4 |
| R/T/A/A_volume、体吸收一致性与独立能量闭合 | ≤1e-5 |
| 各衍射级功率绝对差 | ≤1e-6 |
| 模型完整矩重建、MPC与端口恢复 | ≤1e-10 |
| 网络矩/原作用与 FE 积分的独立求积配对 | ≤1e-8 |

actual 与 producer 分别评分，不挑有利版本。原方程失败时全部功率仅 diagnostic。V40 电场必要条件不替代 curl/端口或原方程门。三条分别交冷初始化、每轮、末态数字；新启动从零不必再负担旧 FTT 46/68 步前缀，但旧研发账永久保留，必要网格/native/moments 准备仍不能免费。

只在相同严格精度下判完整时间或同时峰≥20%的资源收益；与 frozen-NN 及 Cheb 控制比较之外，还须用最佳合格传统 FE 的同口径完整成本，缺项仍 UNKNOWN。研究信号另列：原残差≤1e-3且散射 E/H/curl≤1e-3；它不能授生产。若只有强控制通过，则写 DETERMINISTIC_CORE_SOLVER_SIGNAL_NO_NN_INCREMENT，不当神经成功，也不在本支扩成传统 TT/Full3D 工程。

本轮不自动再开监督拟合/oracle。V39/V40的参考诊断已足以说明边界；三条真实无标签试验与完整验收才是交付重点。训练标记 reference_used_for_training=false、features_reference_exposed=false、benchmark_previously_seen=true、design_informed_by_reference_diagnostics=true、pde_only_solve=true、production_initialization_allowed=false。原 reference 数据只由隔离评分进程读取，不用“设计看过诊断”掩盖实际 teacher 使用。

## 6. D：有实质结果才推进 0.7 nm

仅 learned 路线先完成 M5 联合 PASS，且其控制/消融已经冻结并完成验收、现场安全且剩余总窗≥7200s，才允许本批一次 0.7 nm 缩小非可分三维 pilot。它沿既有定义将 M5 几何长度乘0.14，使用统一材料表正式0.7nm条目，重新绑定实际模式、背景、网格、参考与全部 hash；不得套40端口或直接缩放旧 FE 系数。

允许用已经合格的无标签 M5 神经模型作为归一化坐标初值，明确归属其全部训练成本；不是冷零初值或无预训练的0.7nm证明。参考独立生成，小型 authority 如实计费，保持 release_before_recovery；它不能进入训练。沿同算法、最多2轮/1800s训练，余时优先留给完整验收；条件未过就 NOT_RUN，不注册空输入。

缩放保持近似电尺寸，最多证明新材料和小型三维求解链，不能证明原50×25×140nm问题、任意复杂场秩、p/h精度或全模式资源通过。下一步最终仍须建立：实际精度合格离散→多个规模全过程成本→中间电尺寸→原尺寸目标。2TB不解决未收敛，神经参数少不消除 O(N) 全场、原算子、CL展开和端口成本。

## 7. 资源与同批自主修复

新唯一连续总窗43200s，从首次实际准备计入代码/测试/失败/等待/数值/保存/审核/发布；不与旧剩余预算相加。A实现资格软10800s，三条B各硬7200s，C及发布软3600s，其余修复/条件D；必须始终保留至少1800s终验交付。若已存在合法本批run，识别后继续，不再创建新窗。

CPU-only、MPI1、math/Torch1，一个现场合格物理核；数值warn12/hard16GiB、临时对象规划≤12GiB，轻检查≤2GiB、新核心缓存/AD≤1GiB、自身swap/OOC0。保留原PSI、CPU/SMT、系统max128GiB或10%及384GiB邻增长保护。成功60s准入计墙钟，不复用旧1200s观察池；真正拒绝后额外前台等待≤900s。不得操作邻任务资源或全局环境。

核心优化器只保留有界 O(N) 残差向量、O(d_a) 系数向量和轴核缓存，禁止因m=3264可暂时塞进16GiB就建立N×m新库。方程复杂度没有消失；算子与临时峰必须实测，不能把三核权重bytes当RSS。

每个完整核心/隐藏更新为原子持久边界，保存模型、循环位置、当前c/r、累计工作/预算、RNG及source/input身份。LSMR没有原生迭代checkpoint时，不宣称可恢复半次bidiagonalization；异常丢弃未完成核心、从上一完整边界继续，全部已耗费用保留。进入核心前用短测估计并预留完整核验/保存时间，150s收口、至少120s保存；不靠SIGKILL的finally保全。

schema/API/复数布局/导数/排序/缓存/恢复/资源角色/输出问题允许在同批定位→最小修复→定向测试→健康边界继续，无普通bug次数交棒卡。软件修复不改变数学时不重跑健康producer；若数学影响已有证据，明确重验范围。真实权限/ABI/不可恢复输入、安全或总预算耗尽时保存证据并完成轻交付，不绕过限制、不无限轮询。页面服务失败不阻止数值，也不重复渲染全部历史。

## 8. Git、输入、证据与提交

只在canonical本分支检查锁/活跃作业/HEAD/worktree；合法运行中不改HEAD、不盲kill。无活跃作业且可安全更新后精确fetch/ff-only；不reset/stash覆盖、不amend/强推、不merge master。若同分支仅纯审阅文档与本地未推送实现分歧，沿已有执行补充的受限普通merge规则保留双方历史。

先最小实现及targeted测试，clean实现commit后依赖串行运行；新核心求解、计数与数学放src，复用现有durable/FE验证流程，不建立新调度系统。建议明确one-run输入：

```text
input/task042extra_feinn_5nm/v41_core_linear_checks.dat
input/task042extra_feinn_5nm/v41_fttnn_core_learned.dat
input/task042extra_feinn_5nm/v41_fttnn_core_frozen.dat
input/task042extra_feinn_5nm/v41_chebtt_core_control.dat
input/task042extra_feinn_5nm/v41_core_independent_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

wrapper选择正确环境并调用scripts/run_case.py；每项清场后再下一项。0.7nm输入只在D实际过门时创建。每次run保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/MPI/线程/资源及artifact hash。

提交 response_v41.md、outcomes/ftt_conditional_core_v41.md，及compact design、算子/复伴随资格、LSMR内层与真实接受、隐藏更新、消融/强控制、完整物理Gate、时间/内存、修复/run/provenance记录；独立checker从原字段重算，不只信status。大向量留ignored。更新本分支README/summary当前入口与progress/模型总账/tests/changed_files，历史全部保留。

建议commit顺序：最小核心/资格实现；经定位的必要修复；真实结果和独立交付。不要在“代码已写”“测试已过”“一个子问题没收敛”时交棒。整个授权矩阵或明确科学/硬出口后，一次报告完整HEAD、显式tracking/ahead-behind、clean、自身清场。只推task42extra_feinn_5nm，不给其他任务安排工作。

发布端只做小型复数代数核验与文档结构检查，不能代替M5。GitHub完整视觉未确认时如实NOT_VERIFIED，有限补查新关键页；不以截图生成成功冒充正文可读。最终必须回答：条件线性步是否真实改善原方程；隐藏学习相对冻结和Cheb是否有增量；完整物理是否通过；原尺寸2TB/48h还缺什么。无数值增益就关闭本配置，不自动延长或重命名续试。
