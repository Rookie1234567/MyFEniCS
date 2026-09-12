# Task39extra Review V14：准确p4 Schur内存对照与有界接口近似逆的连续验证

## 0. 目标、身份与一次性执行权限

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task39extra
review_date            = 2026-09-12
reviewed_HEAD          = 044499e012fd5aafb1d79572f88fdddb84a93e29
last_diagnostic_source = 3457b5e2f54dec690fcb70deb1f387fe7f6d57cd
previous_contract      = review_report_v13.md + response_v14.md中的用户续算授权
execution              = Q0 -> Q1 -> Q2 -> conditional Q3 -> conditional Q4 -> conditional Q5 -> Q6
response_required      = response_v15.md
ordinary_default       = unchanged
master_merge           = NOT_APPROVED
```

**本轮先回答用户的直接问题：把同一个p4物理方程准确地用Schur补求解，包含内部因子、接口因子和恢复在内，究竟有没有省内存？随后才检验一种明确的接口近似逆，避免把“未知量变少”误当成“迭代变容易”。**

对应的最终blocker是：0.7 nm任意非可分三维计算需要低存储而有用的全局物理纠错，不能依赖随规模增长的全局LU，也不能用数百次内层迭代换取表面低内存。本轮仍在16 GB笔记本的固定13.5 nm模型上研究；5 nm并行任务不等待、不重复、不修改。

用户本轮明确要求先做准确Schur求解。因此本文为Q1/Q2给出**仅限本机固定模型的直接分解对照例外**：允许各一次原p4全局LU和全局接口增广LU，用于准确性/内存比较。它们不是新增物理真值，不替代已有参考，不是0.7 nm生产方案。V13的“不得新建全局参考factor/Schur factor”不再阻止这两项明确对照；其余旧profile、负结果和限制不追溯修改。Q3–Q5仍禁止原p4或全局接口直接因子进入近似PC。

连续执行合同已在本文冻结。普通阶段通过后不逐项停审；数学负结果按规定分流，不临时扫描参数。硬安全、身份不一致或必要正确性失败时受控停止受影响分支，保存已完成成果。Q6统一回答：准确Schur是否省内存、接口近似是否更有效、完整p6是否通过、下一步保留或关闭哪一部分。

## 1. 已接受的证据，不重复做V13诊断

依据：[V13回应](response_v14.md)、[总览](outcomes/summary.md)、[方向诊断](outcomes/p4_direction_diagnosis_v13.md)、[接口蓝图](outcomes/next_method_blueprint_v13.md)。下表为既有记录，非本review新测量。

| 已有事实 | 数值/范围 | 本轮含义 |
|---|---:|---|
| p4独立/存储行 | 48,960 / 53,084 | 固定模型，不能混作同一DoF口径 |
| 内部I / 接口Gamma盘点 | 35,868 / 13,092 | 结构库存；新内部factor和Schur action尚未资格化 |
| 42块局部回代 | 最大约3.94e-14（V13分解检查） | 不继续提高旧局部LU精度 |
| 两个困难输入的48列最小原残差 | 0.935877 / 0.964795 | 调整这批已有响应的系数不足以获得强纠错 |
| fixed scaled-Z / selected-L10 | strong-action均false | 不继续这些具体候选或recycling扫描 |
| V12宏块四步完整p6 | 64步rho=0.766639，场误差0.948824 | 冻结配置关闭，不追加长跑 |
| V5准确p4＋BAL_H | original/notch已完成 | 固定案例数值参考；不代表0.7 nm或通用鲁棒性 |
| 旧诊断资源 | 新工作集369,795,024 B；树RSS3,287,973,888 B | V13诊断完成；不再优化其256/512 MiB账本 |

准确Schur只是消元重写，不保证条件数、填充量、时间或内存改善。全局稠密13,092阶complex128矩阵本体的派生载荷是2,742,407,424 B；这不是实际Schur必然占用的存储，因为体积Schur可保留块稀疏结构，DtN已有低秩端口表示。

## 2. 冻结物理、输入与公共环境

原始模型保持13.5 nm、grazing1度、azimuth0、s偏振；周期50×25 nm、z=-10..130 nm；原Si/air复材料；p6/h10、252 hex、80个原DtN条目、MPI1/线程1、合格Linux complex128/int32 ABI。真实A6/b、quadrature、材料、几何、双Floquet映射和mode顺序不变。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
ordered_mode_sha256   = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
N6 independent/storage = 164592 / 173802
N4 independent/storage = 48960 / 53084
```

Q1/Q2/Q3用同序的三份已有hash-bound右端项和匹配离散参考：`A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09`。原来的有限参考残差保留，不强制设零。参考只在评价侧；不得用于分区、谱方向、初值、粗空间或参数选择。第三份仍为留出核验，不根据它调参。

读取root/docs及适用目录AGENTS、工作原则、task、V13、最新response/summary和本review；确认canonical clone/worktree、精确branch/HEAD/upstream、clean source及ABI。任务目录当前没有独立新增补充task文件；用户512 MiB授权位于response_v14第6节，只作用于旧诊断。旧文档合同测试的既存缺件单列，不为绿表改动别的Task。

每个数值profile均通过`python scripts/run_case.py input/path/to/case.dat`，一个dat是一场明确计算，不能按调用顺序暗中切换数学方法。允许同一固定控制workflow含三份预先规定的RHS。至少独立区分Q1 full-direct、Q2 Schur-direct、Q3 interface-control、Q4 original、Q5 notch；新输入/source/hash重算。没有SSH工作站或5 nm heavy权限。

## 3. 共同Schur核心：准确消元，不丢物理项

### 3.1 I/Gamma划分与有限元支撑

复用V13的结构规则，不重新调42个种子分组：Gamma包含共享宏块独立坐标、非零DtN输入和输出支持；其余按唯一owner归入I_i。检查原体积图，跨不同I_i的连接必须为零；出现差异先查身份/映射，不带着未消除的内部跨块耦合使用块对角公式。复算35,868/13,092及全覆盖，所有矩阵操作在合法独立坐标完成。

**新A_IiIi的逆不是旧重叠D_i的逆。** 直接从完整原单元贡献和约束映射累加内部、耦合与接口块；支撑跨种子边界的积分不能漏算。不要为方便先构建旧42份D_i因子再全部扔掉。旧C_U/S-p2、旧实体因子和失败macro因子不是这套核心的依赖。

### 3.2 沿用实际端口增广，避免人为制造稠密全局Schur

现有`fullspace_p4_reference.py:augment_physical_volume`使用`[V B; -D H]`。本文用V表示不含DtN的完整物理体积矩阵，B/D/H直接来自原carrier：H含`normalization_h`，D按代码保存的projection行使用，**不能擅自将D替换为B的共轭转置**。若显式写出低秩项，必须先验证H各项合法；实现优先沿用增广，不倒置或截断有问题的通道。

```math
A_4=V+BH^{-1}D,\qquad
\mathcal A_4=\begin{bmatrix}V&B\\-D&H\end{bmatrix}.
```

所有非零B/D支持都在Gamma，内部端口耦合为零。消去I后得到准确的体积Schur和端口增广系统：

```math
\begin{aligned}
S_V&=V_{\Gamma\Gamma}-\sum_i V_{\Gamma I_i}V_{I_iI_i}^{-1}V_{I_i\Gamma},\\
f_\Gamma&=g_\Gamma-\sum_i V_{\Gamma I_i}V_{I_iI_i}^{-1}g_{I_i},\\
\mathcal S&=\begin{bmatrix}S_V&B_\Gamma\\-D_\Gamma&H\end{bmatrix},\qquad
\mathcal S\begin{bmatrix}x_\Gamma\\\alpha\end{bmatrix}=\begin{bmatrix}f_\Gamma\\0\end{bmatrix},\\
x_{I_i}&=V_{I_iI_i}^{-1}(g_{I_i}-V_{I_i\Gamma}x_\Gamma).
\end{aligned}
```

本例独立接口增广行数预期13,172；原full-direct存储包含slave identity行，另报其实际总行数，不用少掉的slave行假装全是Schur收益。Q2只显式构建**体积稀疏Schur＋原80个端口**，不形成全局稠密物理S，也不打开MUMPS dense-Schur导出选项。局部消元会增加块内填充，必须实测NNZ，不能假定Schur仍与原矩阵一样稀疏。

局部消元按邻接Gamma列分批（最多32列）回代、累加；不生成35,868×13,092的全局扩展矩阵，不同时保存所有局部逆。先从图获得结构pattern，准确预分配；不得按数值大小drop项。CSR/COO转换、重复装配副本及端口转换全计费。

### 3.3 一套核心同时提供显式参考与matrix-free作用

```math
\begin{aligned}
Sx&=S_Vx+B_\Gamma H^{-1}D_\Gamma x,\\
S_Vx&=V_{\Gamma\Gamma}x-\sum_i V_{\Gamma I_i}V_{I_iI_i}^{-1}V_{I_i\Gamma}x,\\
F(g;x_\Gamma)&=\left[\{V_{I_iI_i}^{-1}(g_{I_i}-V_{I_i\Gamma}x_\Gamma)\}_i;x_\Gamma\right].
\end{aligned}
```

实现也必须提供相容共轭转置作用，用原复数内积检查。准确内部恢复时：

```math
g-A_4F(g;x_\Gamma)=\begin{bmatrix}0\\f_\Gamma-Sx_\Gamma\end{bmatrix}.
```

实际内部舍入误差另记。全p4最终残差始终除以原g的范数，不用较大的接口RHS分母制造通过。所有场误差用恢复后的p4场及已有P64/真实M0、scaled-curl评价，不以接口系数范数代替。

## 4. Q0–Q2：先交付准确Schur有没有省内存

### Q0：集中完成必要接线与预检

复用已合格的输入、metric、carrier和MUMPS基本接口，不重复旧原因诊断或ICNTL49调查，不升级ABI。为原factor包装增加默认关闭的资源对照策略即可；不能因原p1/p2类的行数上限不适合本次直接对照，就静默提高旧限制。

精确full和精确Schur都使用相同的MUMPS版本、排序/主元/缩放/精度选项，BLR/OOC关闭。工作配额统一使用现有V11公式`ceil_MB(max(32 MiB,2*symbolic_estimate_padded+8 MiB))`，作为新reference profile的明确策略；全局参考实例不冒称满足旧512 MiB小底层限制。保存所有选项与estimate/allocated/used。若与V5历史分配策略不同，必须说明：历史仅背景，正式内存差值来自本批同策略配对。

轻量单元测试集中检查复数端口正负号、非Hermitian B/D、消元/恢复、伴随、约束与生命周期。真实构建再核对局部回代≤1e-10、显式/作用桥接≤1e-10、伴随内积操作尺度≤1e-10。无相关变化的旧测试不重复扩大；新捕获和checker不允许重写求解核心。

### Q1：原p4直接法的同环境资源基线

fresh worker使用已有原p4体积装配＋端口增广＋MUMPS，三份RHS依次准确求解，factor只建一次。保留与Q2相同的公共mesh/map、native A4、P64、评价和必要fine空间；不人为添加旧C_U或macro库存。记录实际矩阵/因子行数和NNZ、symbolic/numeric峰值、每份回代/native residual/场评价、因子仍存活的稳定工作集、清理后RSS。

每份原A4相对残差≤1e-10，匹配参考L2/scaled-curl差≤1e-8；失败标`EXACT_CONTROL_UNQUALIFIED`，不可当准确成本基线。允许至多两次基于原A4残差的同因子迭代改进，每次记账，不松容差或改pivot/shift试参数。

Q1不是重新建立完整p6参考或运行原564步全场。已有匹配数据同scope、同source策略且全过程记录完整时允许复用，否则只做这一次fresh基线。完成后退出并确认全部因子销毁，Q2绝不与它同时运行。

### Q2：准确Schur解同一p4方程

fresh worker构建全部新内部因子、S_V与端口增广mathcal-S，依次symbolic Gate、numeric Gate、三份RHS消元/接口回代/内部恢复。原A4残差及匹配场门槛与Q1完全相同；保存解差、端口增广残差及接口/体内残差分解。必要的至多两次改进调用整个Schur求解过程修正原A4残差，均计费。

将S_V显式作用与matrix-free体积Schur、完整S与原carrier作用交叉核对。已有reference只能验证，不能填充缺失的接口解。允许向ignored artifact保存准确稀疏S_V、局部coupling和metadata，供后续构建复用；文件hash和生成成本明确，不保存新全局factor用于近似PC。

**准确Schur省不省内存，以完整流程判断，而不是13,172行比53,164行少就判通过。** Q2必须包含全部内部因子、接口全局因子、体积/接口/端口矩阵、装配转换、解和评价工作区、恢复与清理。反复调用粗逆时内部及接口factor必须存活，不能先释放它们取低RSS，再忽略重新分解成本。仅在全部RHS及恢复完成后才销毁；绘制或列表阶段峰值即可，不另建监控平台。

Q1/Q2采用相同cold/warm-JIT口径；不为清空系统cache做破坏性操作。记录JIT/cache状态及scope差异。主要比较：

| 同口径项目 | Q1 full-direct | Q2 Schur-direct |
|---|---|---|
| 精度 | 原A4残差、参考场/curl、RHS hash | 同左，加消元/恢复闭合 |
| 存储结构 | 原aug rows/NNZ、factor entries | I_i库存、S_V/aug NNZ、全部factor entries |
| 运行内存 | 完整树RSS/PSS峰值、因子常驻工作集 | 同左；所有内部factor计入 |
| 成本 | fresh setup、三次准确调用、清理、总wall | 含消元装配、接口factor、每次内部恢复 |
| 来源 | measured / backend-reported / derived分列 | 同左；预测不替代numeric实测 |

定义`memory_ratio=Q2_workflow_peak/Q1_workflow_peak`及常驻比，并报告绝对字节差。比值≤0.90且精度合格，称`MEANINGFUL_FIXED_CASE_MEMORY_REDUCTION`；0.90–1.00称`SMALL_OBSERVED_REDUCTION`；≥1.00如实称没有观察到节省；测量scope不一致则`COMPARISON_INCONCLUSIVE`。10%只是工程意义线，单次采样不是统计结论。并列setup和回代时间，不把省内存说成更快。

**分流：** 精确Schur不省内存或更慢，不阻止Q3检验无全局接口factor的近似路线。仅全局接口numeric被资源/费用挡住时，保留准确benchmark未完成结论；若内部factor、S action/adjoint和已知reference的消元/恢复都通过，可继续Q3。若内部可逆性、映射或原算子等价性未通过，则停止共同Schur路线，不能用近似方法掩盖错误。

## 5. Q3：唯一的接口近似候选，直接提供p4修正

### 5.1 明确简化旧嵌套

Q3实现一个完整的`F_interface`，输入g，消元得到f_Gamma，一次固定接口两级作用返回x_Gamma，再恢复全部x_I。**以它直接替换原来的整个I4入口**，不是在旧`C_U -> macro -> C_U`、四步I4里再塞一个接口周期。

本候选不构建旧42份D_i、不构建旧C_U/S-p2、不保留全局p4或全局接口LU；不叠加内部FGMRES、recycling、H4或另一个参数路线。p6的H6、P64、BAL_H和外层FGMRES32保持。这样一次BAL_H是两次F_interface，不是两次×四步×另一套PC。

这是一个reference-free、固定作用的实验性两级接口PC，不保证成功，也不把取消内部Krylov当性能保证。下面的构造是一个候选；本轮不实现面向所有网格的自适应多层平台。

### 5.2 局部接口矩阵与可靠的方向生成

沿用原42种子与Gamma的交集G_i，按canonical规则得到R_i。取真实物理限制S_i=R_i S R_i^H，包含所有邻接内部消元以及原DtN限制，不只计owner的I_i。局部数值可以从已通过的稀疏S_V/原carrier提取并与作用核对；没有该artifact则从局部coupling分批构建，不逐列装配全局稠密S。

先顺序处理两个由geometry/graph冻结的代表patch：最大G_i、最大非零DtN支持patch（相同则取次大不同patch）。不按误差或参考答案挑选。每patch≤2048行，完整矩阵/SVD/LU workspace一次只保留一份，所有临时副本计入1 GiB工作区。若两patch的实际setup和剩余结构计数已表明全42构建超出本节3600秒预算，按成本停止，不进入谱算法参数研究。

对每个patch定义正尺度Delta_i为V13已合格、无材料权重p4质量对角在G_i的限制：

```math
T_i=\Delta_i^{-1/2}S_i\Delta_i^{-1/2}
=U_i\Sigma_i V_i^H.
```

采用本机既有LAPACK直接SVD，固定`gesvd`、complex128、顺序处理，取最小的至多8对左右奇异方向；小矩阵完整SVD不是全局p4分解。检查两侧奇异对残差的操作尺度≤1e-10、重构及有限性。不研发64步近零特征值迭代，不扫描SVD/shift/rank。重数内的基只代表相同子空间，保存输出hash并做子空间核验，不宣称逐列跨库唯一。

局部平滑使用同一S_i的**完整局部LU回代**，不是只保留8项的截断逆，也不是蓝图中未经检验的diag(A_GG)。局部LU只建一次；不另留完整U/V，提取8对后释放。局部factor失败、原局部残差>1e-10时停止此候选，不增加人为吸收、静态pivot扰动或偷偷改ILU。准确局部S_i逆仍非全局S逆。

### 5.3 配对试探/检验空间，保留真实端口响应

令W_i为接口输出1/multiplicity权重。局部候选分别为：

```math
p_{ij}=R_i^H W_i\Delta_i^{-1/2}v_{ij},\qquad
q_{ij}=R_i^H W_i\Delta_i^{-1/2}u_{ij}.
```

复材料/非Hermitian问题不强制Q=P。局部奇异向量不保证覆盖全局难模态，这仍由真实求解裁决。

端口增加原carrier的两个方向族。对原B列b_m和D行d_m，构成Delta_Gamma^(-1)b_m及Delta_Gamma^(-1)conj(d_m)^T；两族都作为相同的候选列分别放入P和Q，不用80模式中的部分子集代替完整物理通道。模式零列可按确定阈值剔除，保存原条目到候选的映射；不对物理DtN减M。

候选按patch编号/奇异值/原mode顺序处理。P、Q各自用复数两遍正交化；一对候选只有在两侧归一后的新分量都大于1e-12时同时接纳，不存在一侧单独截断后行数不匹配。同shape但不相同的P/Q必须有各自identity。当前候选对数上界42×8+160=496；实际秩另报。密化、QR副本和去相关代价计费，不隐去全局接口长向量库存。

```math
E=Q^HSP,\qquad C_\Gamma r=P E^{-1}Q^H r,\qquad
Jr=\sum_iR_i^H W_i S_i^{-1}R_i r.
```

仅E允许小型全局LU，最多512行、matrix+factor+solve库存64 MiB。独立谱/粗矩阵稳定性验证，rcond<1e-12或粗解残差>1e-10标`COARSE_PAIR_UNSTABLE`并停止，不临时改为P^HSP或追加shift。配对设计不是inf-sup稳定性的保证。512行是本批固定scale的上限，超过时不在线拼一个未经验证的递归层级。

### 5.4 一次固定接口周期及完整p4调用

```math
\begin{aligned}
u&=J f_\Gamma,\\
v&=u+C_\Gamma(f_\Gamma-Su),\\
x_\Gamma&=v+J(f_\Gamma-Sv),\\
F_{\mathrm{int}}(g)&=F(g;x_\Gamma).
\end{aligned}
```

这是一次预平滑、粗修正、后平滑，无独立的“迭代到收敛”循环。原native A4 residual和恢复后的场/curl用于评价。局部与粗层LU都复用；全局S仅算作用，Q3数值比较前释放Q2全局接口factor以及用于构建的全局S_V副本（仅保留matrix-free所需的V_GG、局部coupling及carrier）。保存并核对释放后的RSS/对象库存。

单次F_int的第一层上界：内部RHS消元42次、两次S各42次内部回代、恢复42次，即168次内部回代；另有两次J合计84个接口局部回代、一次小E回代和所有乘法/归约。一次p6 BAL_H为两次F_int，所以最多336次内部回代、168次接口局部回代、2次E回代，再加H6、A6和传递。计数不是时间；内核昂贵就按真实成本停止。新C_U调用数必须为0，不沿用旧账覆盖新方法。

### 5.5 三份真实输入短对照与准入

正常路径同一Q3构建复用三份RHS，每份只调用一次F_int，不加四步包装。保存原A4残差、恢复后的L2/scaled-curl误差、内部/接口残差、单次全部工作及RSS；与Q1/Q2准确结果和V13旧I4记录并列。保存一次p6合法q上的BAL_H代数记账核验，g2由本次c1/H6实际产生，不能使用旧预存反馈RHS。

进入Q4的工程准入：两个困难01/09均满足rho≤0.5、eta≤0.5、eta_curl≤0.6；反馈02的rho≤0.2、eta/eta_curl≤0.9；单次F_int含native最终检查≤15秒、未触及资源线。若部分参考无法读取，先依据原hash定位，不换更容易输入；关键field无法核验则不冒充准入。该门槛不是PC单步必须收敛的理论要求，而是本次高成本新构造应表现出明确收益的投入筛选；临界结果不改线、负结果不自动延长。若不满足，Q6保留准确Schur结论并关闭本近似候选。

## 6. Q4–Q5：在真实p6上完成判决，而不只交局部PASS

Q4从零初值运行原始p6，真实A6/b不变、right FGMRES32、无recycling；BAL_H中的两次中间求解均直接使用F_int：

```math
\begin{aligned}
c_1&=F_{\mathrm{int}}(P_{64}^Hq),&z_c&=P_{64}c_1,\\
s&=H_6(q-A_6z_c),&c_2&=F_{\mathrm{int}}(P_{64}^HA_6s),\\
z&=z_c+s-P_{64}c_2.
\end{aligned}
```

保留eps1/eps2及`P64^H(q-A6z)=eps1-eps2`操作尺度1e-8核验；闭合误差和实际缺陷范数分开，不把恒等式通过当强PC。新F_int最多一次固定cycle，不调用旧I4或S/p2。外层接口适配和原H6不混改，正式运行不读取任何reference修正方向。

同一个KSP先观察最多64步窗口，不为检查点退出重开。每8步原A6真残差/计数、每32步安全解和既有参考场检查，30秒PC硬费用仍作安全边界（25秒请求返回由现有外层安全点处理，不返回未完成的半个线性作用）。若64步时rho>0.10，或到64步solve>1800秒且仍未达最终精度，按性能停止；不重新跑同一前缀。首次约1800秒安全点rho>0.10停止，约5400秒rho>1e-3停止；通过早期窗口则在同一KSP继续，最多2048步、solve10800秒/workflow14400秒。已达到最终目标立即结束，不为了填表跑满64步。

必须并列同一步数和同时间附近实测节点，至少32/64；与V5、V7及V12历史数据用相同物理身份对照，注明诊断频率差异；不插值虚构节点。成功必须完成本节后续物理Gate，不能只报递推residual。

Q4完整通过后立即执行Q5：同配置的冻结V5非可分缺口（8个原canonical cell keys/实际材料实体，不按新规则改形状）。重新构建依赖材料的I_i/S_i/P/Q/E和内部因子；结构映射可按identity复用，数值因子/方向不可从original搬来。缺口不调rank、块、restart或cycle。资源或收敛失败则保留局限、收口，不再另起ONE_C/R64/新PC。

| 最终Gate | 不变要求 |
|---|---|
| 原p6方程 | full explicit norm(b-A6x)/norm(b)≤1e-6 |
| 同结构场 | L2/scaled-curl相对差≤1e-4，复E/H和同坐标近场，无拟合整体相位 |
| R/T/A与A_volume | 各自参考绝对差≤1e-5 |
| 独立守恒 | R+T+A_volume−1及A−A_volume绝对值≤1e-5 |
| 全部80模式 | 复幅值向量相对差≤1e-4，逐通道功率最大绝对差≤1e-6 |
| provenance/resources | 完整input/source/physical/mode/artifact identity、全程RSS与时间、zero job swap |

未过A6 residual的场只作diagnostic，不发布official R/T/A；本批通过也只是同离散资格，不替代h/p精度和5 nm/0.7 nm验证。V5参考流程448页global pswpout归因历史边界继续保留。

## 7. 资源与时间：保护机器，不再用未说明的组件整数线中断

以下新profile预算明确分离直接对照与可扩展候选；旧profile阈值不动。

| 项目 | 本批固定边界 |
|---|---|
| 全进程树运行上限 | min(8 GiB, effective_available−reserve)，且原动态内存/cgroup检查同时满足 |
| 整机reserve | max(4 GiB,15% effective_total)；zero job swap、无新增全局交换，一次一个heavy |
| Q1/Q2数值常驻库存 | 合计≤6 GiB，含所有矩阵/factor/已知缓存；不是单factor各6 GiB |
| Q3–Q5近似路径常驻库存 | 合计≤3 GiB；包括内部、接口局部、粗层因子及P/Q、carrier等，默认不保存失败旧stack |
| 内部/接口单patch | ≤2048行；单factor matrix+reported allocated预算≤512 MiB |
| E底层 | ≤512行且matrix+factor+solve≤64 MiB |
| 装配/SVD/QR等工作区 | 最大同时1 GiB；未知库副本预留，不另加多个各1 GiB工作池 |
| MUMPS/浮点 | 相同complex128/int32 ABI，V11 symbolic配额规则；不OOC、不BLR、不升级ICNTL49 |
| 正式批次累计预算 | 43,200秒，含预检、全部构建、检查、失败、保存和两个条件完整模型 |
| Q0 / Q1 / Q2 | 600 / 1800 / 3600秒，各为workflow上限 |
| Q3（两patch＋全部构建＋三输入） | 3600秒，两个patch合计900秒，余量须足够完整构建 |
| Q4 / Q5 | 各workflow14400秒、solve10800秒，另受阶段进度线约束 |
| 修复与结束 | 总预算内最多一次真实实现bug修复重放；数学失败不重试；工程活动另计不扣formal两次 |

8 GiB与6/3 GiB都不是允许无条件分配的承诺。每次大分配前使用同时存活清单、后端symbolic、转换和恢复余量预审；实际RSS+未触及预留超过launch cap就停。后端allocated/used、派生库存和实测RSS/PSS分别报告，不能用used字段绕Gate。原V13的512 MiB只读诊断workspace不复用成此处全程cap；本文新预算仅用于这批明确计算。

Q1/Q2不同时保留两个全局factor；Q2结束后全局mathcal-S factor不能进入Q3/Q4。Q3控制后的原始/缺口fresh setup如必须重建就计入各workflow，不开发因子序列化平台。Q2 artifact可复用构建数据，但同时报告复用速度和从零重建的已知setup成本，不能把一次性谱/Schur构造藏到“免费预处理”。

这里的近似路线仍是小规模机制候选：固定42patch和≤496粗维数不能直接推广到更多网格/端口。后续需分布式传递、受控层级、streaming DtN和局部规模策略；本轮不实现通用递归聚合、不声称解决了全部2 TB容量问题。准确Schur-direct即使省内存也不改变其全局直接分解增长属性。

## 8. 实现、证据与统一收口

### 8.1 最小改动与可复用接口

| 位置 | 责任 |
|---|---|
| `fullspace_p4_reference.py` | 复用原体积/端口增广；新benchmark配额为显式opt-in，不改普通reference默认 |
| 新`physical_interface_schur.py`或现有合适模块 | I/Gamma映射、内部factor、稀疏Schur装配、matrix-free apply/adjoint、准确及近似恢复 |
| 同模块的interface two-level实现 | 顺序局部SVD、paired P/Q、小E、固定cycle；无reference参数、无隐藏内层KSP |
| 既有physical intermediate/BAL_H适配口 | 将F_int适配成中间inverse返回solution/applied/residual/facts，清楚标记近似，不误报inner-converged |
| `scripts/run_case.py`及现有runner/schema | 新显式profiles、同一watchdog/ledger，runner不承载数值核心；不用复制Task专属框架 |

测试合并为一批：非Hermitian低秩端口与Schur准确解；零RHS/约束/伴随；内部与外部残差关系；paired rank/局部SVD/粗矩阵坏条件停止；释放全局factor后近似apply可独立运行；reference隔离；禁用新profile时旧行为不变。最终改动后重跑相关测试、compileall、diff-check及文档检查，保存raw stdout/stderr。不声称full pytest/CI已通过；旧缺件与新增失败明确分开。

建议普通commit顺序：共同Schur与资源对照接线；Q1/Q2结果；固定接口PC与测试；Q3及条件Q4/Q5结果；response/outcomes收口。每场正式worker前clean source SHA。不得amend/强推、删除负结果或合并master。

### 8.2 必需交付，不新增一整套诊断材料

```text
response_v15.md
outcomes/p4_schur_v14.md
outcomes/records/p4_schur_v14_compact.json
outcomes/records/p4_schur_v14_comparison.json
outcomes/records/run_index.json
outcomes/summary.md / outcomes/test_summary.md
```

同时增量更新development_progress、development_model_registry和selective-merge边界。原数组、稀疏矩阵、方向、factor临时及全时间线留ignored；Git只存轻量标量、路径、hash和必要小矩阵。采用本仓库fenced math和表格规范，提交前本地预览/公式检查，推送后检查GitHub rendered view，访问失败如实记录。

Q6首屏必须给出三个互相独立的答案：

1. **准确Schur是否省内存？** Q1/Q2同口径峰值与常驻量、原A4精度、setup/重复调用成本；若阻断则给准确阶段、实值和限值，不凭估算宣布省。
2. **接口近似逆是否值得继续？** 真实三RHS及p6节点、与旧PC的同成本/同步数比较；达到准入不等于完整成功。
3. **接下来采用什么？** 准确Schur通过且节省：保留小中规模参考；近似F_int完整original/notch通过：保留候选并提出单一后续尺度验证；近似失败：关闭本固定配置，明确失败在构建、局部/粗空间合法性、纠错还是成本，不在本批再开参数路线。

只做完Q2不主动结束：共同核心正确且资源允许时进入Q3。只得到局部SVD/回代PASS不作为交付终点：按准入进入真实p6或明确关闭候选。任何未运行项如实标`not_run`，不为了完成流程无视停机条件。

## 9. 依据及边界

| 来源 | 使用范围 |
|---|---|
| [最新回应](response_v14.md)、[既有诊断/蓝图](outcomes/next_method_blueprint_v13.md) | 结构库存、旧失败和下一方向的证据；其具体谱迭代/旧嵌套建议由本review明确替换 |
| [原p4 reference代码](../../src/solvers/fullspace_p4_reference.py) | 已有`[V B;-D H]`端口增广、native residual和factor生命周期 |
| [MUMPS配额代码](../../src/solvers/fullspace_bounded_mumps.py) | V11 symbolic-sized策略；大reference实例显式新profile，不绕旧底层行数限制 |
| [PETSc Schur action](https://petsc.org/release/manualpages/KSP/MatCreateSchurComplement/) | Schur可仅算作用；不提供本案例收敛保证 |
| [PETSc MUMPS](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/) | factor/workspace及Schur选项的区分；在线版本不替代本机ABI |
| [SciPy 1.11.4 SVD](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.linalg.svd.html) | 小型复数直接SVD的左右向量/工作区接口，不升级软件栈 |

消元/恢复和增广公式由本review代数定义推出。两级粗空间、8对方向、512行和阶段门槛是一次受限工程设计，不是适用于所有Maxwell问题的理论保证。用户要求的准确Schur内存测试与最终低存储迭代路线必须始终分开报告。

**本批终点：先用实测回答“准确p4 Schur有没有省内存”，再让一个明确、去除多余嵌套的接口近似逆接受真实问题检验；不再用一连串局部PASS代替完整结论。**
