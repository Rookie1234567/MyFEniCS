# Review V1：接受首轮负结果，执行一次固定 M5 变量尺度诊断

## 0. 审阅决定与身份

**接受 Response V1 为完整接口、独立参考及固定配置负结果的研究档案；不授予 FEINN 求解器或生产资格。下一批只授权“已有状态诊断＋一次 FREE-FE-DUAL 的 Gram 对角变量缩放＋冻结后独立验算”。不续训两个网络，不重跑原三路线，不重建准确 Maxwell 参考，不扩大几何或波长范围。**

本批针对的 blocker 是：即使不使用网络、直接优化全部 FE 系数，现有残差最小化仍未取得准确场。需要检验**变量尺度是否妨碍优化**，而不是先假定网络容量不足，或把所有困难归咎于 FEINN。它是通向 5 nm 有效求解和最终 0.7 nm 任意非可分三维目标的一次有界诊断，不是新的通用低内存强逆研发任务。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42extra_feinn_5nm
worktree                   = /home/fenics/Projects/NN-Lab-V2
review_date                = 2026-09-30
reviewed_HEAD              = 8de092afa15d65ef7fa9dbaafcec8481787b80d5
original_base_SHA          = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
task_publication_SHA       = 3b8474bff1b3cb9321a89afbca36868a9b95153d
previous_review            = NONE_IN_THIS_TASK
latest_response_reviewed   = response_v1.md
V1_interface_source        = a3dd65f594dda0ffd593ef53f7a0f4adfbd7a35e
V1_three_route_source      = 7ac01a62453e6b76d0e68ed20f3da5be282c9a1c
V1_reference_source        = 7a79b3007d92a9b699e0451d0c8b6dfdacee7ad9
review_decision            = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
next_batch                 = V2_FIXED_M5_VARIABLE_SCALING_DIAGNOSTIC
new_route                  = FREE-FE-DUAL-GRAM-DIAG
response_required          = response_v2.md
final_0p7nm_48h_gate        = NOT_QUALIFIED
master_merge               = NOT_APPROVED
```

审阅依据为远程 task/AGENTS、Response V1、summary、原始 CSV/JSON 和数值核心；本次没有 SSH 重跑工作站，没有重新核验全部 ignored 大数组。下文 measured 均指仓库运行记录，derived 指代数推导或明确算术；本 review 的新试验全部 not_run。已核对任务目录尚无其他正式 review 或补充任务书。

先读根/目录 AGENTS、[仓库原则](../repository_work_principles.md)、[原 task](task.md)、[Response V1](response_v1.md)、[summary](outcomes/summary.md) 和本 review。本 review 只覆盖原 task 中与本次唯一缩放及后续执行相冲突的限制，其余身份、精度、资源与历史保护继续适用。保持同一执行分支，原 Task042 及其他工作树不变。

## 1. 已证实结果与不能越过的边界

来源：[原始对照 CSV](outcomes/records/route_comparison_v1.csv)、[逐点审核](outcomes/records/convergence_audits_v1.json)、[独立 Gate](outcomes/records/gate_decisions_v1.json)、[Response V1](response_v1.md)。残差和场误差均无量纲，时间为监督阶段秒数，RSS 为同时进程树采样峰值。

| V1 路线 / measured | 完整 native 相对残差 | 散射 E 的 L2 相对差 | closure 数 | 监督 wall / s | 采样树峰 / GiB |
|---|---:|---:|---:|---:|---:|
| FEINN-EUC | 0.9282871956 | 0.9992148894 | 2219 | 10690.6684 | 0.65601 |
| FEINN-DUAL | 1.1026449759 | 0.9988851200 | 2387 | 10688.1087 | 1.31262 |
| FREE-FE-DUAL | 0.5969144472 | 0.9919248991 | 4000 | 2901.9062 | 1.27242 |

三路线均未满足原方程 1e-6、同离散场 1e-4 和物理 Gate。两个网络达到 wall 上限，FREE 达到 closure 上限；不是当前16 GiB耗尽。散射场相对误差接近1表示相对零散射误差基线改善很有限，不等于已证明输出向量严格为零。

| 证据 / 身份 | 结论与范围 |
|---|---|
| 完整插值、A/Aᴴ、端口、Gram、实参数梯度 measured | 接受所测接口；不是全面无bug证明，更不是求解成功 |
| 独立同p3参考 measured | native/augmented约6.78884e-12，能量闭合约2.97762e-13；存在合格同离散参考，不是连续极限 |
| 两条DUAL的Gsolve measured | 最大真实相对残差约6.10e-13/7.53e-13；没有证据将本轮失败首先归因于G求解太粗 |
| FREE含全部31968复FE变量 measured | 不存在网络表达空间限制；其失败揭示独立的优化问题，不能仅归因于网络容量 |
| p4边界 not_run | 因p3候选未资格化而未准入；不得改写成p4已经算过且离散误差失败 |
| 目标尺寸5nm/0.7nm not_run | 容量文档是提案/推算，不是实测准入或生产能力 |

Riesz loss 已正确接入，但没有取得本配置的有效解。论文 [Compatible FEINNs v2](https://arxiv.org/html/2411.04591v2) 的正质量项 H(curl) 模型和本不定开放散射不同；本支线也采用同p3试探/测试空间而非逐项复刻论文。保留论文思想的研究价值，不把一次负结果扩展为普遍不可能。

## 2. 为什么只检查变量尺度

固定原算子A、原散射载荷f和正定Gram矩阵G。当前目标及其在自由FE坐标中的二次型为：

```math
r=Ac-f,\qquad d_G=f^*G^{-1}f,\qquad
L(c)=\frac{r^*G^{-1}r}{2d_G},\qquad
H_c=\frac{A^*G^{-1}A}{d_G}.
```

这是对已有目标函数的代数解释，不是在代码中形成H_c。即使理想化地A=G，除固定标量外H_c仍为G而不是单位矩阵；合理的弱残差度量并不保证原FE坐标中的优化条件良好。网络还会引入额外参数化限制，但FREE的失败已足以支持先做一次尺度分流。

本次缩放是**对角变量预条件**，不回到旧p4粗逆。它只统一各基函数对应系数的能量尺度，不保证解决波动共振、不定性或全部病态。严格区别：loss几何、变量坐标、优化器和网络表示是不同环节。不得预先写“尺度是唯一根因”，也不得把缩放负结果称为所有神经方法失败。

## 3. 冻结模型与可复用数据

| 对象 | 本批冻结值 / 来源 |
|---|---|
| 物理 | 原M5，真空5nm，Si/air，grazing1°/phi0/s/幅值1，原layered背景和双Floquet/Fourier-DtN |
| 几何/离散 | 原缺口盒[-5,5]×[-3.75,3.75]×[-1.25,8.75]nm；384hex、h1.25nm、Nédélec p3、原q15 |
| 未知量 | 全部31968独立复FE：边3744、面14400、内部13824；slave2082；40端口按原关系准确消去/恢复 |
| 5nm材料 | n=0.99396854453+0.00435380777i，epsilon=n*n，原材料表与背景/端口一致 |
| G与loss | 原同p3 MPC约束Gram，ell=5nm；固定d_G及原native残差；不改成Schur/trace loss |
| 数值精度 | FE complex128/int64，Torch/参数float64实虚双通道；不换FP32/GPU |
| 初始化 | 新候选y=0，实际c=0；不使用V1末态、网络或参考warm start |

从[原run index](outcomes/records/run_index_v1.json)读取实际路径及绑定；以下是本次应核对的文件字节SHA256，不是新测的工作站hash：

```text
native.npz / physical packet:
2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
gram.npz:
2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9
moments_q15.npz:
0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e
material table:
55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
original design:
650af0bade61c4ef89583398624b375245691109a6778c168dd46d8c0e70524e
```

只读取本任务必要的packet、Gram、V1历史和固定checkpoint，不复算全部旧工况。完整加载后核对dtype/shape/master顺序/材料及mode身份；新设计/缩放hash独立记录，不能覆盖旧design hash或把D写入物理方程身份。

原环境、模型、插值和真实A/Aᴴ没有改变的检查按source＋artifact复用，不重新安装或进行整套E0/E1；新增缩放/接口单独资格化。若必要native/G文件缺失或损坏，报告ARTIFACT_BLOCKED，不重新装配/分解来悄悄填补。若仅准确参考文件缺失，仍可完成候选和原方程审核，但场资格not_run；不自动重建参考。

## 4. D0：已有状态诊断与预登记

先只读检查既有history及checkpoint，只使用实际保存的状态。建议状态池为零初值、V1 FREE最终已提交态、两个网络的最终已提交态，以及**确实仍保存**的Adam500结束状态。每条路线最多三个已存在状态；中间状态已被覆盖则写NOT_RETAINED，不重放训练来制造旧历史。未接受的last_trial只能独立标记，不替代committed。

输出以下紧凑诊断，不做全局SVD、不物化Hessian/Jacobian、不导出巨大逐自由度CSV：

- 按边/面/内部三族统计G对角及系数/系数梯度绝对值的min、p1、p50、p99、max，另列范数和零计数。网络参数按隐藏层/输出层分组，但只在实际必要的非零固定态做有限评价。
- 重算固定态L_D、欧氏native及增广残差，分别说明分母；记录原系数梯度和映射到缩放坐标的梯度。不能把不同loss数字直接比较为精度。
- 读取已有Adam/L-BFGS历史中的有效更新、已提交/试探状态、参数变化与停止信息。旧历史没有步长或内迭代接受记录则标unknown；不推测、回放或改已安装Torch补历史。

D0新增完整loss/gradient评价总数不超过20，不更新真实候选参数。未保存状态不阻止后面的唯一试验。计算需要的准确G因子可在本诊断进程内建立一次并复用，setup/每次Gsolve都计费，结束即释放；不得跨阶段隐藏驻留。

先将缩放定义、输入白名单、模型/数组hash、诊断状态池、近零规则、预算和下述阈值写入 `scaling_design_v2.json`。这些诊断不使用准确参考的场或解系数；其目的不是寻找最优缩放参数。

## 5. D1：唯一缩放及梯度资格

### 5.1 固定定义，不做扫描

从**已经施加MPC的原全局G**取对角。不得用未组装单元对角或未约束矩阵对角替代，也不取diag(G^-1)。

```math
a_j=\mathrm{Re}(G_{jj})>0,\qquad
D=\mathrm{diag}(a_j^{-1/2}),\qquad c=Dy.
```

D为固定实正对角，同一个D同时作用于实部和虚部。其定义只依赖原G，不依赖载荷解、旧最优状态或参考。虚部须满足原Hermitian精度，逐项正性/finite以及D的finite必须检查；失败标SCALING_DEFINITION_FAILED，不加任意epsilon、不截断极值、不扫指数或再乘结果驱动的全局系数。

这是按原基内积范数归一化，不是对A的全部病态进行精确白化。检查diag(D*GD)≈1并报告实际偏差。D与有关统计以新packet/hash保存；不改原G、A、rhs、矩求积、port或物理输入。

### 5.2 计算链

```math
\begin{aligned}
r(y)&=A(Dy)-f,\\
Gq&=r(y),\\
L(y)&=\frac{r(y)^*q}{2d_G},\\
g_c&=\frac{A^*q}{d_G},\qquad g_y=D^*g_c.
\end{aligned}
```

参数存储为两个float64通道，梯度赋值为Re(g_y)、Im(g_y)。端口只按原alpha(c)恢复，不新增训练port变量、不缩放端口块、不消去内部FE系数。所有原方程和物理验算先恢复c=Dy，不拿y的范数代替物理系数或场。

实现优先给 `feinn_optimization.py` 增加显式opt-in参数映射，复用 `FullNativePacket`、`ResidualMetric` 和 `SparseRiesz`。旧三路线数值语义不改，禁止复制整套新runner或修改已安装Torch/CHOLMOD。候选只允许原局部A/Aᴴ action、原G的准确稀疏factor和D；不新建global A CSR/LU或AᴴG^-1A，不引入其他PC。

### 5.3 必须通过的小测试

先合成复数非Hermitian A与Hermitian正定G，再在固定M5上测试至少3个非零复向量和3个非零实参数方向：

| 新增接口 / 单位 | Gate及边界 |
|---|---|
| D、c/y往返、原loss一致性 | operation-scaled相对差≤1e-10，近零单列绝对值 |
| AD的共轭转置 | D* A* dot test≤1e-10；不能把D当成左残差缩放 |
| 实参数梯度 | 中心差分h=1e-4/1e-5/1e-6，稳定区相对≤1e-5；不能只用零态 |
| Gsolve | 保持原每次真实相对残差≤1e-11，报告factor和求解成本 |
| 事务状态 | 预算/线搜索异常恢复已提交y；所存c须等于Dy；费用与试探记录不丢失 |

当前V1已经有事务处理，不预设它仍有旧Task042的停机bug。缩放新增测试只覆盖本次改变，不无故重写优化器。诊断/测试中的固定非零参数不作为正式初值，准确参考不参与测试数据生成。

## 6. D2：一次 FREE-FE-DUAL-GRAM-DIAG

D1通过后，从y=0开始一次运行。旧FREE-FE-DUAL为固定基线，不完整重跑；两个网络仅保留旧证据，本批不训练任何网络。数据点属于同一已知benchmark的诊断续研，不称fresh泛化资格。

保持与V1相同的Adam500（lr1e-3、无weight decay），随后L-BFGS（lr1、history20、strong-Wolfe、max_iter20、max_eval25、tolerance_grad1e-7、tolerance_change1e-9）。不增加schedule、restart、权重衰减、CG/LSQR或自然梯度。保持全部closure最多4000、路线wall最多10800s，均含Gram fresh setup、线搜索、检查和末态保存；沿用V1的最终审核预留，不因版本升级重置费用。

梯度/参数改变门限受坐标尺度影响，必须同时记录g_c与g_y范数、参数相对增量和实际停止原因。仍按原优化器门限执行这个对照，不能看结果后放松门限；小梯度、tiny step或优化器success不等于原方程通过。若由于停止门限而结束，明确归类，不能静默不断重启优化器。

每25次closure及每个原有committed检查点审核完整native、增广、total原方程与port；在同一日志中区分已提交态和试探态。记录A/Aᴴ/Gsolve数、完整closure数、外层/实际内迭代数、接受更新量；能从实际state可靠取得的步长才报告，不假装外层状态包含全部内部接受历史。

存在未通过场/功率门限的中间迭代也不得用于official结果。到预算、非有限值、监督或数值失败立即保存正确状态并停，不补足4000次，不续训旧checkpoint，不读取其他路线的解做warm start。

新增主入口输入建议为 `input/task042extra_feinn_5nm/v2_free_fe_dual_gram_diag.dat`；只表示本次一个固定算子的计算。新index/stage名必须独立于V1，不能为了绕过STAGE_ALREADY_PUBLISHED而覆盖旧index或删除原记录。

## 7. D3：冻结后验收与分流

候选终止，冻结committed checkpoint、D、source和hash后，独立验证进程才可加载V1已保存的同p3参考。只复用参考，不再次MUMPS symbolic/numeric/solve。现有reference模块若把对比与重求解绑在一起，只拆出最小compare-only入口；本地验证所需网格/后处理对象可在预算内重建，但不重建全局参考矩阵或因子。

记录输入白名单，证明candidate没有加载参考场。每个物理量沿用原规范，比较实际c=Dy、total与scattered场。旧参考已用于首轮验证，本次只能称同基准独立复验，不能重新称全新未见测试。

### 7.1 正式资格不放宽

| Gate | 本批要求 |
|---|---|
| 原方程 | native及完整未凝聚增广、原total方程相对残差各≤1e-6；固定原RHS分母 |
| 端口/MPC | 原port绝对/固定RHS/operation-relative全部报告；相对Gate≤1e-6；消元/MPC配对≤1e-10，slave合同及finite通过 |
| 场/通道 | total与scattered E的L2、scaled-curl、selected复E/H、完整有序复通道相对差各≤1e-4 |
| 功率/吸收 | R/T/A_balance/A_volume差≤1e-5，每通道功率差≤1e-6；独立A_volume能量闭合及吸收一致性≤1e-5 |
| 近零 | 原task与V1已冻结自然尺度、绝对误差和分母；不事后调分母或拟合相位 |
| p/规模 | 本批不做p4、不扩大M5；即使同p3通过也不代表离散收敛、目标尺寸5nm或0.7nm/48h通过 |

### 7.2 唯一研究正信号

除严格资格之外，预登记有限诊断阈值：在不超过V1 FREE的4000完整closure、相同3h上限内，最终已提交态的native与augmented残差均≤**0.05969144472114**（V1基线降低10倍），同时scattered E的L2相对误差≤**0.5**，且资源/身份通过，才记 `SCALING_DIAGNOSTIC_POSITIVE`。

这不是合格物理解。原A/Aᴴ/Gsolve及审核次数必须单列，并在已有共同closure检查点比较，不能把更多隐藏工作说成同成本。共享环境的时间改善若不可比较则inconclusive；仅缩放正信号不产生任何“神经增量”结论。

| 观察 | 必须采用的解释与后续边界 |
|---|---|
| 全部严格Gate通过 | 记FREE_SCALED_DISCRETE_PASS；只说明本M5非神经缩放优化成功，后续神经试验另议 |
| 达到诊断阈值但未严格通过 | 记录实际提升，支持后续一次明确的神经尺度/优化研究；本批不自动实施 |
| 只降低loss/原残差，散射误差仍接近1 | RESIDUAL_ONLY_NOT_FIELD_PASS；不视为路线已获救，不继续扫D |
| 未达阈值 | SCALING_DIAGNOSTIC_NEGATIVE；说明此次Gram对角不足，不能宣称排除所有优化或神经方法 |
| 参考缺失/字段不足/资源停止 | 对应not_run/blocked/controlled_stop；不臆造场资格，不自动重建昂贵证据 |

表达能力的监督诊断、载波/分片网络、其他残差度量或Krylov方案只可作为最终一个后续建议，**本批均未授权**。不要求先开发出通用强逆才允许研究神经网络，但也不能无限重复无判别力的缩放扫描。

## 8. 首轮报告应修正的证据表述

这些是小型文档/元数据修正，不触发重新训练或重新装配。

**通道指标：** V1 summary/response的“出射复通道”约0.270177/0.270119/0.275180，而CSV的 `ordered_total_channels_relative` 为0.562925/0.562805/0.573349。先从 `blind_physics_v1.json` 核对原port、出射幅和scattered/total的准确字段及分母，说明是否为不同向量；不得直接判为抄错，也不得沿用模糊表头。旧V1文件保留，在V2解释并给出逐字段映射，独立checker按明确key复算。

**p4与资源口径：** p4实际not_run，V1的DISCRETIZATION_NOT_QUALIFIED表示未获得资格，不是已测离散失败。数值阶段最高树RSS约1.313GiB，完整账含浏览器渲染的最高树RSS为2095390720B；不把前者称整个会话峰值。全机swap记录中的历史“WSL-global”字符串不是工作站实际运行于WSL的证据；V2按原生Linux实际scope标注，不修改历史读数。

**公式渲染：** 任务书§5.4的GitHub宏报错由[首轮render记录](outcomes/records/render_check_v1.json)保留。作为任务书发布方，ChatGPT在此仅授权Codex将该处唯一的 `\operatorname{Re}` 替换为 `\mathrm{Re}`，数学内容、门限及其余字节不变；这是一次明确的排版修正例外，不授予一般task/review改写权限。记录旧blob `e231804fd8173acf7fc48cb17fc752e9b505c7ab`、新blob及一行diff，实际复核GitHub渲染。其他文字规则继续只通过新增response/review澄清。

本review使用可渲染的Re写法。只对新review和上述一行修复做有界渲染检查，不批量渲染全部历史。浏览器临时占用也在资源限额和成本账内；渲染不可访问时明确blocked，不能声称已视觉通过。

## 9. 资源、预算与执行隔离

保持原生Linux工作树、独立FE/ML环境/cache、Task42extra自身锁和内部串行。MPI1，数学与Torch intra/inter-op1，DataLoader0，CPU-only；现场选一个空闲物理核并避开忙碌SMT同胞，较低优先级只作用自身。不修改Task042、Task39、Task041、Metrology或其他项目的HEAD、环境、锁、affinity、watchdog；不安装/升级系统BLAS/CUDA，不争GPU。

数值整树warn12GiB/hard16GiB，自身swap=0、无OOC；轻测试上限2GiB，磁盘自由至少50GiB、artifacts总量仍≤20GiB。系统保留max(128GiB,effective_total的10%)，邻任务增长预留**至少沿用V1现场384GiB，发现更高增长需求则增加**，再加本任务16GiB。不因为当前RSS低就撤销邻增长预留；未知或资源紧张只停自身阶段，先完成可做轻工作，不无限等候或后台自动启动。

本批新增有载及有界辅助检查**最多4h**，同时受原16h累计剩余额度约束，取较小值。D2最多3h；D0/D1、独立验证、必要测试/发布使用其余预算，总量不突破。V1完整账 `complete_supervised_research_and_validation_seconds` 为 **26195.446021194453s**；UTC launch-to-summary的derived口径为 **26240.100355625153s**，二者不能相加。为保守准入可用两者较大值作已消耗基数，并加之后真实新增费用；V1冻结、失败和辅助费用不重置。

准确G因子是 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`；重新在本次进程建立的factor/setup/solve、释放前后RSS都计入。复用G装配时同时给出新增实耗与沿V1口径的从零归属，不能省略准备成本宣称加速。已有同p3参考只复用不重求。父/子嵌套计时不重复相加，derived wall与monotonic measured分开。

无cgroup委派继续如实使用约0.5s整树采样监督，不冒称连续内核限制。预算和监督包含FE/ML/编译/渲染后代。紧急资源停止时优先安全终止自身树，不能为完成final audit越过硬线；完整结果不足则如实not_run。性能标shared-workstation，不宣称零影响。

## 10. 最小改动、提交与 Response V2

执行前确认正确branch/HEAD、无活跃本任务run、工作树状态及upstream，仅安全fast-forward读取本review。不新建分支/clone，不amend/强推，不把review带进master，不merge其他活动分支。

数值改变限参数映射/梯度链、新stage/profile/输入、必要诊断和compare-only验证；复用原算子、Gram和优化器。源代码进入src，runner只编排，旧路径保持默认语义。新增profile若受旧route名白名单限制，做最小显式扩展，不改物理design或绕过source Gate。局部明确bug允许一次记录充分的修复/受影响重放，预算照计；正常停滞不属于bug。

建议提交顺序：C1预登记/状态审计/一行排版修复；C2缩放wrapper及合成/真实有限测试；C3唯一新路线和复用参考的验证；C4 compact结果、独立checker与Response V2。每个正式运行前clean实现commit，保持运行source SHA不被后来文档HEAD替代。所有正式FE/固定算子求解阶段仍走one-run dat：

```bash
python scripts/run_case.py input/task042extra_feinn_5nm/<one-run>.dat
```

最少新增交付如下，文件名固定或在response解释唯一等价入口；V1 raw files不覆盖：

```text
response_v2.md
outcomes/scaling_diagnostic_v2.md
outcomes/records/scaling_design_v2.json
outcomes/records/state_diagnostics_v2.json
outcomes/records/scaling_checks_v2.json
outcomes/records/scaled_route_comparison_v2.csv
outcomes/records/gate_decisions_v2.json
outcomes/records/run_index_v2.json
outcomes/records/resource_costs_v2.json
outcomes/records/render_check_v2.json
```

summary在首部追加V2并保留V1历史；同步本分支development_progress、development_model_registry、test_summary及changed_files的新节。三条旧路线只引用，不重新写成新测。测试仅task-focused，禁止full repository重跑、环境重装或全历史artifact大扫描。

Response V2首先报告完整HEAD/source/upstream/worktree，D0–D3实际完成项、D的来源和hash，以及确认仍为原M5/全FE/40端口。随后给出旧FREE与新scaled FREE的同口径残差、散射场/通道/功率、closure及A/Aᴴ/Gsolve成本，严格资格和诊断阈值分别判断；明确参考复用、未重新Maxwell分解，以及missing/blocked项。说明现有证据更支持哪些因素、哪些仍unknown，不宣布唯一根因。最后仅提出一个有证据的下一最小建议。

前置Gate通过即可连续执行本批，无需逐小步再请示；权限/资源/身份或真实数值失败则按上述范围安全停止并交付。完成后只推送 `HEAD:refs/heads/task42extra_feinn_5nm` 并等待review。**本次不授权新神经训练、监督拟合、p4、目标尺寸5nm、0.7nm或merge。**
