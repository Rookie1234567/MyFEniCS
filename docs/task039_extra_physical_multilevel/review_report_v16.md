# Task39extra Review V16：原p4全局BLR近似因子的单配置验证

## 0. 决定、身份与本批权限

**结束V14/V15的固定接口候选。本轮不再给Schur接口换一组粗方向，而从已经有效的原p4全局LU出发，只检验一个BLR压缩因子：压缩后是否保留有用的全局物理修正，且确实减少内存？有明确收益就立即进入完整原始p6与条件非可分缺口，不只交内部测试。**

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task39extra
review_date            = 2026-09-13
reviewed_HEAD          = e369c940d257a1f7fbae7fd4a3ce03ad60b62852
accepted_Q1_Q2_source  = 6a8b273c383d5bd9da37d6630a48bd24d6a90cce
closed_interface_source = 188224ad5fc81b34156a0ae3678bd2121b1206da
previous_response      = response_v16.md
new_batch_identity     = review_v16_p4_blr
candidate              = physical_p4_blr_bal_h_v16
execution              = S0 -> conditional S1 -> S2 -> conditional S3/S4 -> S5
response_required      = response_v17.md
time_policy            = observe_only
ordinary_default       = unchanged
master_merge           = NOT_APPROVED
```

要削弱的最终blocker是：0.7 nm任意非可分三维问题所需的全局物理纠错，目前仍依赖增长型直接因子，已有低存储局部组合不足。本批是**强近似逆的可压缩性和工程取舍试验**，不是最终无全局factor架构；仍仅在16 GB笔记本的13.5 nm固定模型执行，不启动5 nm/0.7 nm，不修改并行工作线。

本review明确授权：在**原p4端口增广矩阵**上建立一份全局BLR近似因子，并用于p6的PC；必要时各模型之外最多补一场未压缩p4资源对照。该研究例外替代旧review的“Q3近似路线不得全局p4 factor/不得BLR”限制，不允许对A6整体LU作PC，不追溯修改旧profile与负结果。

用户已要求时间gate暂不阻断推进；本批明确继承`observe_only`：时间继续完整记录和比较，但不恢复600秒、25/30秒PC、1800/5400秒等时间终止线。有限模型数量、步数、数值准入、系统安全和用户停止仍有效。新批次与旧V14账本分开编号，旧费用、政策扣款及未知终态保持不变，不把换编号说成旧成本清零。

## 1. 已接受证据与关闭边界

来源为[最新回应](response_v16.md)、[当前汇总](outcomes/summary.md)、[准确配对](outcomes/records/p4_schur_v14_comparison.json)。以下均为已有记录，不是本review新测量。

| 已有结果 | 实值与口径 | 本轮决定 |
|---|---|---|
| 原p4 LU / 准确Schur | 全流程树RSS 2,825,973,760 / 4,267,347,968 B；比值1.510045 | 保留准确性证据；不重跑Schur或优化其全部库存 |
| Q1 / Q2准确性 | 最大原A4残差6.56e-11 / 8.68e-11；场/curl差0 / 1.94e-12 | 原Q1可作为同离散参考；0不代表连续物理误差为零 |
| Q1增广矩阵 / factor | 53,164行，24,730,144 NNZ；后端padded allocated 2,343,000,000 B | 新候选的对象是这一原增广系统，不是13,172行接口系统 |
| 旧接口一次作用 | 三输入rho=37.272086 / 0.726414 / 41.825936；场差约1.011 / 0.963 / 1.002 | 冻结接口候选关闭，不增加rank、cycle或补外层长跑 |
| 旧接口运行异常 | 指标保存后BAL_H map guard比较了不同层次的metadata keys | 最小修复数值map比较；不能删除guard，也不为补此项重跑旧PC |
| Task010 BLR历史 | p2/h2、13.5 nm、10度、MPI8，epsilon=1e-5时4步、残差2.085e-8 | 支持选择该固定起点，不是当前p4/p6资格 |
| Task010内存边界 | 17.85 / 20.53 GB为rank峰值乘rank数的旧上界；h1.5被kill | 不冒称巨大压缩或zero-swap成功，不与当前树RSS混算 |

历史来源：[Task010原始汇总](../task010_shifted_maxwell_preconditioner/outcomes/summary.md)。本轮只取得一个压缩配置上的观测，不称为完整“精度—存储曲线”，也不能用一次失败否定所有压缩分解。

## 2. 冻结物理、环境和参考隔离

先读根与docs的AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、V14/V15、最新response/summary及本review。任务目录没有独立新增补充任务书；`response_v16`记录的用户时间授权仍有效。检查canonical worktree、精确分支/HEAD/upstream、clean source；相关源码变化先普通提交再正式计算。

| 项目 | 冻结值 |
|---|---|
| 几何/材料 | 原50×25 nm周期单胞，z=-10..130 nm，Si/air，原252 hex、p6/h10；Si复折射率与V14相同 |
| 入射/边界 | 13.5 nm、grazing1度、azimuth0、s；双Floquet；原80 DtN条目，顺序/符号/归一化不变 |
| 独立/存储行 | p6=164592/173802；p4=48960/53084；p4增广=53164 |
| ABI | 已资格化Linux DOLFINx/Basix 0.10系列、PETSc complex128/int32、MPI1/线程1；具体库版本和路径重新记录 |
| 原始物理SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| 三输入顺序 | `A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09` |
| 缺口 | V5已冻结的8个canonical cell keys对应实际材料实体；不重新选择更易结构 |

复用现有Q1/V13索引中的RHS、map、参考向量及全部hash；不在本文复制另一套hash常量。第三输入仍作为不调参的留出检查。参考只进入评价/checker，不能进入factor、缩放、排序、PC、初值或容差选择。不得省略材料、减少通道、降低阶次、使用准二维或Hybrid替代。

正式执行统一用`python scripts/run_case.py input/path/to/case.dat`。只增加必要的BLR control、original、notch和条件exact-control显式输入；一份dat表示一次明确workflow，固定control可含这三份RHS。profile/CLI默认值写入resolved config和manifest；不能按先后调用次序暗中切换算法。

## 3. 唯一候选：压缩原p4的全局因子，而非另造局部粗空间

### 3.1 压缩的是哪一个对象

沿用`fullspace_p4_reference.py`的原增广，不展开稠密DtN。V、B、D、H取自当前合法离散和carrier，D不被替换成B的共轭转置。

```math
A_4=V+BH^{-1}D,\qquad
\mathcal A_4=\begin{bmatrix}V&B\\-D&H\end{bmatrix},\qquad
\mathcal A_4\begin{bmatrix}c\\\alpha\end{bmatrix}
=\begin{bmatrix}g\\0\end{bmatrix}.
```

BLR在分解过程中近似保存部分块，不是先存准确LU再对它事后压缩。用包含排序/缩放的完整后端求解动作表示近似因子逆：

```math
\begin{bmatrix}\widehat c\\\widehat\alpha\end{bmatrix}
=\widetilde{\mathcal A}_{4,\tau}^{-1}\begin{bmatrix}g\\0\end{bmatrix},
\qquad F_\tau(g)=\widehat c,\qquad \tau=10^{-5}.
```

`inverse`仅为数学记号，不形成显式逆矩阵。一次F_tau只做**一次已建BLR因子的回代**，factor在所有RHS及p6循环间复用。无内层FGMRES、无外部迭代改进、无recycling、无Schur宏块/SVD/旧C_U/S-p2包装；p6的H6本身已有辅助层级不改。若裸回代不足，记录不足，不能偷偷补几次solve使它看似准确。

### 3.2 参数一次冻结，必须确认真正生效

[S1]–[S3]只解释公开接口；**实际可用性以本机已链接MUMPS及PETSc接口为准**，不由PETSc版本号猜MUMPS版本，不升级ABI。

| 控制 | 本批值/规则 | 目的 |
|---|---|---|
| ICNTL(35) | **2，且在symbolic之前设置** | factorization与solve使用BLR存储；不是仅factor计算近似后存满秩 |
| CNTL(7) | **1e-5** | 唯一压缩阈值；不试1e-4/1e-6等相邻配置 |
| ICNTL(36) | 本机该版本的默认值，S0读出并冻结 | 不扫描BLR变体；在线新版本默认不覆盖已安装版本 |
| ICNTL(37) | 0 | 本批先隔离因子压缩，不另加贡献块压缩策略 |
| ICNTL(38/39) | 保留并记录本机默认估计；不据结果回调 | 它们是内存预测输入，不是测得的压缩率 |
| ICNTL(10) | **0** | 禁止后端隐藏迭代改进；两次BAL_H粗调用各一次MatSolve |
| OOC/丢factor/提前消元 | ICNTL(22/31/32)=0 | 因子在内存中可重复使用；无磁盘换容量 |
| 精度 | complex128；已安装版本支持自适应精度控制时明确关闭 | 不引入complex64、混合精度或量化 |
| 排序/主元/行列缩放 | 原Q1策略；记录真实值，不做新扫描或加shift | 不借压缩之名改变物理/数值身份 |

**CNTL(7)不是原A4残差容差，也不是“场误差保证为1e-5”。** MUMPS手册将其定义为块压缩中的绝对阈值，因此原尺度与缩放必须记录；它本身不保证整个因子或逆的相对误差。ICNTL(35)在symbolic后才打开可能没有所需分析信息，不能这样“启用”。参见[S1]§5.20与[S2]/[S3]。

现有`_MumpsFactor`已有整数控制，允许以同一公开PETSc C API最小增加CNTL setter/getter和BLR信息读取，校验complex128/int32签名及返回码；不直接解引用MUMPS私有结构。所有设置前后读回并保存，禁止仅把选项写到未被使用的Options数据库而称已生效。小fixture没有可压缩front不等于不支持BLR；真实p4是否压缩必须以S2统计判断。

### 3.3 原物理残差必须独立计算

令增广残差为 `[e_top; e_port]=[g;0]-mathcal_A4*[c;alpha]`，则由上式直接推出：

```math
g-A_4c=e_{\rm top}-BH^{-1}e_{\rm port}.
```

每个控制输入保存并核对这条关系、原native A4残差、合法slave-zero输出及恢复后的P64场/curl；不能用端口增广残差或BLR后端误差代替原A4。H必须按原carrier处理，不截断通道。

BLR的块误差可在全局逆中放大。一次回代很便宜不等于方向强，因子小也不等于全流程小；本批正是测量这两个未知项，不预设结果。

## 4. S0–S2：一次必要接线，直接进入真实p4配对

### S0：资格与最小修复

确认实际MUMPS版本、库路径、BLR可用性、公开控制读回和日志字段含义。复用ABI、端口和metric已有资格；不重做I/O恢复、旧宏块构建或V13方向诊断。环境只作正常启动预检，宿主存储与原zero-swap/watchdog继续检查。

修正已知map guard：先按保存包schema取数值map子对象，再比较规范化数组、shape/dtype/hash、master/slave和primal/dual语义；metadata键可以不同，但数值数组不允许忽略。用真实已保存map与小型适配检查，不删除guard，不为修复它重跑旧接口PC。

集中完成：非Hermitian端口符号与原残差恒等式；零RHS、线性/重复/输入不改；BLR在symbolic前生效；CNTL7读回；ICNTL10=0且一次F_tau正好一次solve；无参考进入PC；销毁及异常清理；旧默认不变。小代数测试不是BLR真模型收敛资格。提交clean source后进入S1/S2，不只以“若干测试通过”收口。

### S1：只在必要时补一个未压缩p4对照

优先复用V14 Q1原始资源轨迹、矩阵/选项/公共对象和三RHS证据，明确identity桥接。若ICNTL10、缩放、allocation策略、公共对象或采样范围不一致，**最多补一场fresh uncompressed control**；它用与S2同一装配、评价、生命周期和监控，仅BLR关闭。不是新建p6真值，也不重跑准确Schur。

ICNTL10=0的未压缩对照按原A4≤1e-10、参考L2/curl≤1e-8核验。结果不合格则先排查原矩阵/环境/设置，不以它作内存分母；不靠隐藏refinement制造配对。原Q1已有“无显式迭代改进”记录不自动证明其后端ICNTL10相同，需读真实选项。

同一时刻只能保留一份全局factor；对照结束退出并确认回落，再构建BLR。基线复用失败的原因要具体，不能因为source增加一份文档就重建对照。

### S2：一个BLR factor、三份真实输入、一次完整资源比较

按第3节直接构建原p4增广矩阵并BLR分析/分解。不要先构建未压缩factor来取得初值或候选；也不要按小数值drop原矩阵。三输入每份恰好一次F_tau，立即保存向量、原残差和场度量，再评价下一份。原输入/参考hash、粗调用及factor计数绑定。

**至少区分以下四个指标，不把估计压缩率当作实测内存：**

| 指标 | 记录方式 |
|---|---|
| BLR实际存储 | 本机手册支持的低秩/满秩因子条目、压缩块与有效存储统计，原字段/单位/版本一起保存 |
| 分解workspace | symbolic estimate、配额、allocated、used，明确发生阶段 |
| factor-live工作集 | factor与原矩阵存活时，三次回代前后process-tree RSS/PSS；不先释放factor取低值 |
| 全流程成本 | 完整RSS/PSS峰值，setup/symbolic/numeric/每次回代/native检查/评价/保存/清理时间 |

优先读本机已支持的INFOG/RINFOG及标准BLR日志；不同版本字段不能硬套。负数表示百万计量等特殊编码按该版本解释。若打印日志已有所需真实统计，直接解析一次，不开发新的通用监控平台。actual字段不可得时明确`COMPRESSION_STATS_UNAVAILABLE`，只凭设置成功或ICNTL38默认60%不得声称压缩60%。

CNTL7的实际选择与预处理固定，禁止后验按三输入选参数。控制结果只用于按下节继续或关闭，不用于自动调阈值。

## 5. 进入完整p6的准入与资源收益判读

本批以固定一次回代替代高频p4粗逆，不要求它单独达到1e-4或准确LU的1e-10。仍需用真实输入排除明显无效方案：三份输入均须有限、map/原残差闭合合格，且**rho≤0.5、L2≤0.25、scaled-curl≤0.25**。这些是本次投资筛选，不是所有PC必须满足的理论必要条件；未通过只关闭此裸BLR配置，不推论BLR类方法不存在。

以内存同口径对照定义：`R_peak=BLR完整树RSS峰值/exact完整树RSS峰值`；`R_live=BLR的factor-live最大树RSS/exact相同阶段最大树RSS`。只用post-numeric至第三次评价结束、两侧对象均保留的实际样本；不减去不同流程的空进程RSS拼出因子字节。基线缺少live样本时该比值不可用。

| S2结果 | 行动 |
|---|---|
| 质量准入且R_peak≤0.90 | 进入S3，标记固定p4控制的明显内存下降 |
| 质量准入、R_live≤0.80且R_peak≤1.05 | 也进入S3；只称反复粗调用的常驻收益，不能称构建峰值降低 |
| 质量合格但两条内存条件均不满足 | `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN`，S5收口，不跑长p6或另换epsilon |
| 质量不足 | `BLR_ACTION_UNQUALIFIED`，S5收口；不加内层/迭代改进 |
| 选项未生效或根本未压缩 | `BLR_UNAVAILABLE_OR_NO_EFFECT`；不以普通LU复现冒充BLR成功 |
| 正确性/存储范围不能核验 | `IMPLEMENTATION_BLOCKED`或`COMPARISON_INCONCLUSIVE`，不给未有依据的PASS |

10%/20%是一次明确的工程收益线，不是统计显著性或0.7 nm容量证明。时间全记录但不作准入否决；特别不能用“单次超过15秒”覆盖用户observe_only。最终仍要并列时间与内存，较慢结果不会被包装成加速。

没有新建factor或调用就能补齐的metadata/原始日志缺项先直接补齐；不为拿一个非关键compression字段反复运行PDE。需要改变数学配置才能改善时则关闭，不视为bug重放。

## 6. S3/S4：保持BAL_H，一次BLR回代直接替换整个p4入口

保留已成功的H6、P64及right FGMRES32；不采用刚失败接口的S_V、局部S_i、P/Q/E，也不构建旧C_U/S-p2和四步I4。一次p6 PC按以下动作执行：

```math
\begin{aligned}
g_1&=P_{64}^Hq,&c_1&=F_\tau(g_1),&z_c&=P_{64}c_1,\\
s&=H_6(q-A_6z_c),&g_2&=P_{64}^HA_6s,&c_2&=F_\tau(g_2),\\
z&=z_c+s-P_{64}c_2.
\end{aligned}
```

实际g2必须来自本次c1/H6；不得将旧预存反馈RHS放进完整求解。一次BAL_H两次BLR solve，除此没有内部收敛循环。保存epsilon1/epsilon2，并核查`P64^H(q-A6z)=epsilon1-epsilon2`操作尺度≤1e-8；闭合误差和粗层实际缺陷分开。它不要求近似逆是精确投影，也不保证粗缺陷小。

S3从零初值执行当前原始13.5 nm模型；预检通过后就进入真实A6，不重跑positive辅助资格。每8步保存原A6真残差、迭代/PC/factor调用和资源；每32步先保存解再评价已有参考场。原数组在ignored内，参考隔离于数值路径。64步时原rho>0.10则数值进展不足，关闭；通过则**同一KSP继续**，至最终rho≤1e-6或最多2048步，不退出再从头跑。时间进展线只记观测，不触发25/30秒、1800/5400秒或总wall停止；非有限、breakdown、资源和用户停止保持。

最终原始模型通过后，立即S4同配置notch。重建该材料对应的原p4矩阵和BLR factor，不复用original数值factor；几何map仅按identity复用。不能调整CNTL7、排序、restart、单次solve数或材料。原始失败则notch不运行；缺口失败明确限定适用范围。

| 最终Gate | 要求 |
|---|---|
| 原A6 | full explicit norm(b-A6x)/norm(b)≤1e-6；报告递推与真实残差差异 |
| 同离散场 | L2/scaled-curl≤1e-4；复E/H、同采样坐标近场，无拟合整体相位 |
| 功率 | R/T/A/A_volume各自参考绝对差≤1e-5 |
| 独立守恒 | R+T+A_volume−1与A−A_volume绝对值均≤1e-5 |
| 全部80模式 | 复幅值向量相对差≤1e-4；逐通道功率最大绝对差≤1e-6 |
| 全流程 | 完整provenance、RSS/PSS、时间、zero job swap、全局交换无增量及子进程清空 |

不通过原A6残差，不生成official功率结论。成功保存最小恢复数据后，先销毁KSP/BLR因子和无用矩阵、确认RSS下降，再恢复后处理；控制阶段为反复调用对照必须保留factor，不混淆两种生命周期。没有新的完整exact-p6对照时，只报告BLR完整实测与V5历史背景，不能将S2的p4内存百分比冒充完整p6百分比。

## 7. 资源、次数与时间政策

| 项目 | 本批规则 |
|---|---|
| 整树cap | 启动min(8 GiB, effective_available−reserve)，运行沿已修正动态容量检查，不能重复扣当前RSS |
| 系统reserve | max(4 GiB,15% effective_total)，检查真实cgroup/宿主余量；一次一个heavy |
| 数值常驻库存 | S1–S4合计≤6 GiB，含原矩阵、压缩因子、H6/传递/向量及已知缓存；不是每个对象各6 GiB |
| 临时工作集 | 最大同时1 GiB，含CSR/COO、后端/序列化/评价副本；不并列多个独立1 GiB池 |
| 其他 | zero job swap、无新增全局交换、无OOC/BLR混合精度/ABI升级；错误终态不追认通过 |
| 正常worker数量 | BLR三RHS control一次，条件exact control至多一次，条件original一次、notch一次 |
| 真实实现bug | 本新批至多一次有证据修复重放；保留费用与失败，仅重放受影响阶段 |
| 数学/资源不合格 | 不改变epsilon或抬高cap，不反复重试；直接S5收口 |
| 时间 | observe_only覆盖父launcher、worker、PC、checker；monotonic/UTC/保守计时分列，不人为短timeout |

6 GiB为此**全局压缩因子研究**的明确合计库存线，不再套用接口试验3 GiB或p1类512 MiB行数/库存限制；旧profile不变。研究cap不表示已获得节省，节省仍由第5节实测对照判断。

MUMPS配额保留V11规则：`ceil_MB(max(32 MiB,2*estimate_padded+8 MiB))`；BLR symbolic输出含满秩/估计压缩两种口径时，以本机手册映射并取两者较保守值作本批配额/预分配，记录来源。不能把默认估计压缩率当实测容量放行；也不能先按准确LU配额分配后却把其未触及空间从账上删掉。实际预留、allocated/used及树RSS始终分列。

新账本使用唯一`review_v16_p4_blr`，记录旧V14最终ledger hash和总费用引用，不改写其恢复事件。延续observe_only不表示无需计时；CPU/时钟/保存异常仍要可识别，真正监控失效或基础设施错误先停止受影响流程，不自动再次恢复。没有必要再开发调度或通用内存审计平台。

## 8. 实现收敛、证据与提交

尽量在既有通用p4 factor与BAL_H inverse接口增加可选backend，不复制现有几千行Schur runner。runner只负责公共配置/调用/资源，BLR控制、增广回代和原残差接口放`src/solvers/`；checker只读结果重算。允许最小修复map canonicalization，不把本批变成大规模架构清理。

阶段提交：①显式BLR控制、map修复及定向测试；②S1/S2资源与质量；③条件S3/S4结果；④response/summary收口。每次正式worker为clean source。最后改动后跑相关测试、compileall、diff/doc检查；如缺Ruff或未跑full pytest/CI如实说明，不为此迁移环境。GitHub math fences和表格按既有标准。

必需中心交付如下，重型矩阵/因子/场/轨迹只放ignored，向量及时原子保存：

```text
response_v17.md
outcomes/p4_blr_v16.md
outcomes/records/p4_blr_v16_compact.json
outcomes/records/p4_blr_v16_decision.json
outcomes/records/run_index.json             # 增量
outcomes/summary.md / outcomes/test_summary.md
```

同时增量维护development_progress、development_model_registry与selective边界。每场绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA及run_summary；补matrix/选项/ABI/真实RHS/metric/模式/数据hash。metadata不足不可用人工填PASS补齐。

S5首屏必须分开回答：

1. **实际压缩了什么、减少了多少？** 区分后端因子条目、工作区、factor-live和完整峰值；给同口径baseline及未知项。
2. **是否保住有用的全局纠错？** 三RHS的单次裸回代实值；不能用参考组合或隐含refinement来改善。
3. **完整p6与非可分是否通过？** 给同步数和同时间附近实际节点、最终物理/资源Gate；无数据填not_run，不外推。
4. **下一步保留什么？** 双模型成功且节省成立：保留过渡候选，提出一个与并行5nm线协调的后续规模点；仅有小幅压缩或质量失败：关闭本固定配置；ABI不支持：准确报告后端限制，不另装新库。

只有“设置已启用”“三RHS通过”或后端报告压缩都不构成完整solver成功。通过也不宣称h/波长鲁棒或0.7 nm资格。BLR仍有全局消元树、增长的front/rank与setup工作集；最终Full3D生产路线仍需分布式matrix-free算子、可扩展迭代与有界粗问题，Hybrid仅作可利用结构的并行加速路线。

## 9. 来源与适用边界

| 来源 | 用途 |
|---|---|
| [S1 MUMPS 5.9.1手册](https://mumps-solver.org/doc/userguide_5.9.1.pdf) §5.20 | BLR启用阶段、低秩因子存储与CNTL7语义；本机须按实际安装版本核对，不升级 |
| [S2 PETSc MUMPS接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/) | 公开BLR及factor控制；在线API不证明本机支持 |
| [S3 PETSc CNTL setter](https://petsc.org/release/manualpages/Mat/MatMumpsSetCntl/) | 最小公开实数参数接口与返回检查 |
| [Task010历史](../task010_shifted_maxwell_preconditioner/outcomes/summary.md) | 单一epsilon起点的经验，旧几何/角度/阶次/MPI与内存口径不能移植成新成绩 |
| [当前response](response_v16.md)、[Q1/Q2配对](outcomes/records/p4_schur_v14_comparison.json) | 已核实准确基线、失败与可复用成本证据 |
| [原p4增广](../../src/solvers/fullspace_p4_reference.py)、[factor包装](../../src/solvers/fullspace_v17_p3_oracle.py) | 原方程、公共factor生命周期；不改普通默认 |

公式为本review的代数定义与推导，阈值是一次受限工程实验，不是收敛定理。**本批只沿一个已知强逆的压缩方向推进：有真实内存与质量收益就以完整三维模型裁决，没有就给出明确边界，不自动开启下一串参数尝试。**
