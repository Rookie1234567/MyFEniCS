# Task39extra Review V10：完整局部物理粗逆与框架/重启的有界归因

## 0. 身份、审阅结论与授权

```text
repository         = Rookie1234567/MyFEniCS
branch             = task39extra
review_date        = 2026-09-10
reviewed_HEAD      = 64ed6eb167137ee67fb85e8dac372f3c506a0c11
original_task_base = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_materials = review_report_v9.md / response_v10.md
execution          = M0 -> M1 -> M2 -> conditional M3(original/notch) -> M4
response_required  = response_v11.md
ordinary_default   = unchanged
master_merge       = NOT_APPROVED
```

**本轮针对的blocker：没有全局p4 LU时，现有高阶实体小块的近似逆质量与总成本不足；但不能把所有困难预先归给内部逆，也不能把准确粗逆下成功的BAL_H当作不可替换的框架。** 本轮用一个完整多单元物理局部逆增强基础修正，并用有限同输入分析分开“内部解质量、两次粗修正的组合、外层restart损失”。最终仍由完整原始与非可分三维求解裁决。

接受V9受控负结果，关闭V7–V9实体小块/两组/recycling具体变体；不扩大rank、不继续单RHS长跑。保留V5准确p4 LU的双模型成功。5 nm已由另一条线执行，本批只在笔记本既有合格Linux环境处理13.5 nm，不等待、不重复、不干扰另一条线。

用户本轮授权在同任务分支继续探索。本文窄范围覆盖旧review的“不得新增DD”和固定I4工作策略；允许第3节的一个局部逆、第4节的一个框架对照及第5节的32/64有界重启对照。它们不是可自由组合的参数库。本轮明确允许评价端用匹配参考作第4节一次框架选择；参考不得进入PC、Krylov方向或逐次自适应。除此以外的物理、精度、参考隔离、系统安全、Git规则不变。目录盘点未见新的补充task文件；不得将历史outcomes中的旧“继续”措辞解释为额外授权。

最终目标仍是单节点约2 TB整机内存内，0.7 nm、complex128、Nedelec H(curl)、双Floquet、Fourier-DtN、任意非可分三维周期单胞散射。本轮即使通过，也不代表波长鲁棒、连续解准确或最终无全局底层因子。

## 1. 现有证据与本轮必须纠正的概念

以下为已提交measured记录；时间、字节等只使用各自记录的口径，不是本review新跑PDE。原始模型相同，rho为原A6相对残差。

| 版本 | 共同PC32：rho / solve秒 | 终态 | 意义 |
|---|---|---|---|
| V5准确p4 | 0.0731226 / 346.127 | 564步达约9.93e-7；notch576步通过 | 有效机制基线，外层本来就用restart32 |
| V7 A实体16 | 0.1223131 / 1414.353 | 121步0.0425645 | 内层成本高，完整未通过 |
| V8复用/新8 | 0.1511041 / 985.329 | 59步0.0911428 | 部分时间窗改善，没有合格解 |
| V9复用/新16 | 0.1312380 / 1549.065 | 38步0.1292009 | 等新工作量没有带来整体收益 |

证据：[V9中心结果](outcomes/equal_work_recycled_p4_v9.md)、[Response V10](response_v10.md)、[V7结果](outcomes/bounded_inexact_outer_v7.md)、[V5 compact](outcomes/records/balanced_coupling_v5.json)。V9完整准备时间unknown、V5条件参考448页系统换出归因未明等限制不追溯改判。

必须区分三件事：

1. **旧PC内部逐段MR选步长**：V5改为粗—细平衡，没有这些逐段缩步。这不是取消Krylov restart。
2. **p6外层FGMRES32 restart**：每32步保留当前近似解，但丢弃本周期搜索基；并非把解重置为零。V5成功和后续失败都使用过它。
3. **每个p4 RHS的有限内部求解及跨RHS复用**：V7每RHS至多16步，V8/V9 GCROT只跑一轮；多数调用尚未发生同RHS的内部restart就返回。不能将这种失败直接解释为“内部重启丢方向”。

目前没有同一新PC下完整32/64对照，不能总结为“不restart更好”。本轮只检验前64步不发生重启是否有实质价值，不授权无限增长的unrestarted生产求解。

## 2. 冻结模型与可变接口

| 项目 | 冻结内容 |
|---|---|
| 原始物理 | 13.5 nm、grazing1度、azimuth0度、s；50×25 nm周期，z=-10…130 nm；Si/air及原损耗 |
| 原physical SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| ordered mode SHA | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| 离散 | p6/h10，252六面体；p6独立164592/存储173802；p4独立48960/存储53084 |
| 真实算子 | full-space matrix-free A6/b、native A4、已合格cached volume、完整80模式DtN、P64/P64H与quadrature不变 |
| fine辅助 | 已合格H6不变；不恢复S6或旧逐段MR |
| 原粗层组件 | 保留现有CU及其单元内部响应、S/p2底层的数学作用；不把它误称简单的原生p2 Galerkin逆 |
| 缺口 | V5冻结8个cell keys及实际材料实体、自己的物理身份和reference；同网格，不换简单形状 |
| 输出 | 探针127.5/-7.5 nm、同坐标复E/H与近场、R/T/A/A_volume、完整模式 |
| 环境 | 既有同ABI、complex128、MPI1、线程1；不升级PETSc/SciPy，不装新后端 |

新数值实现进入通用`src/solvers/`，复用native action、`physical_bounded_runtime.py`、`physical_balanced_coupling.py`、既有局部矩阵/映射和watchdog。runner只编排，checker独立重算，不复制另一套任务专用求解框架。明确新profile，旧profile与ordinary default不动。

所有真实规模试验，包括64步probe，均通过`python scripts/run_case.py input/path/to/case.dat`，一个dat表示一次运行并冻结solver mode/restart/maxit/预算。允许两个小诊断profile和最终选择的正式profile，不允许改变材料或右端项来调通。

## 3. 唯一新基础PC：多单元完整p4代数重叠块

### 3.1 它处理什么，为什么与旧patch不同

旧实体可接触多个单元，但只联合处理选出的高阶边/面方向。本候选将一组相邻单元涉及的**全部p4独立自由度**放入一个局部物理问题，包括低/高阶、边/面/内部耦合。不沿z假设均匀，不使用内部模态传播，不是恢复16个全横截面slab。

固定几何分组：从已冻结的6×3×14结构化cell拓扑出发，以最小坐标为原点，用`(floor(i/2), floor(j/2), floor(k/2))`形成不超过2×2×2个cell的种子组；末端不足两个的组保留，不改变网格。由此预计42组（derived，必须核对实际canonical keys）。每组I_i取组内单元触及的所有合法独立p4坐标，经Floquet主从映射去重。相邻组共享边/面独立坐标，形成**代数索引重叠**；不是额外一整层cell重叠。记录覆盖次数、遗漏、周期接缝和实际局部行数。每个独立坐标必须被覆盖。

不在本轮扫描块大小、平移分组、重叠层数或权重。该固定最小多单元候选不能保证波传播鲁棒；若不足，报告其限制，不自动扩大。

### 3.2 局部矩阵必须是正确的原A4限制

在独立坐标中，R_i为局部选择，n_i为局部独立行数：

```math
R_i\in\mathbb C^{n_i\times N_4},\qquad
D_i=R_iA_4R_i^H.
```

从已有单元矩阵与合法展开/双对偶归并直接累加D_i。**需包括所选基函数在种子组外的全部支撑贡献；不能只积分种子组cell便声称得到上述主子矩阵。** 对含外端口坐标的块，精确加入相关DtN限制，可沿用等价端口增广以避免显式稠密端口耦合；使用全部适用的既定通道、正确相位和符号。全局A4仍保持matrix-free。

这个局部模型对应其余独立系数置零的代数限制，不冒称透明人工边界。主子矩阵可能近奇异；不偷偷加入Robin/PML/shift、不改变物理损耗，不用伪逆遮盖奇异。局部失配或奇异分别记录`LOCAL_OPERATOR_INVALID`或`LOCAL_INVERSE_UNQUALIFIED`。不装配全局p4/p6矩阵来提取局部块，不做逐全局单位列探测。

优先沿现有合格稀疏LU后端构造一次并反复回代。每个块包含端口辅助量的总行数上限2600；不满足先停止预审，不缩减真正需要的自由度以凑数。该数为本机pilot容量边界，不是理论最优值。局部矩阵、因子和缓存按矩阵身份保存，材料变更的notch必须独立重建。

输出采用固定的重数分配W_i=diag(1/multiplicity)，不在输入端再乘一次W_i：

```math
\sum_i R_i^H W_iR_i=I,\qquad
M_D r=\sum_i R_i^H W_iD_i^{-1}R_ir.
```

这是输出partition-of-unity加权的加法Schwarz作用，不混称为已经验证的标准RAS/ORAS。局部LU固定、输出权重固定，不加逐块MR；不再叠加旧1566实体逆或full252逆。

### 3.3 与现有全局纠错配合，但不再增加长内层

令C_U为现有实际`complete_pq`粗修正（含单元内部响应与对应S/p2求解），保留其限制、伴随、物理作用桥；**不能把相同shape的新p2矩阵冒充原C_U。** 新基础PC只用M_D替代原高阶实体修正：

```math
B_4^{DD}=C_U+(I-C_UA_4)M_D(I-A_4C_U).
```

不显式创建这些N4方阵。已有精确粗层限制关系必须核对，但不重做整套旧投影诊断。

正式I4使用right FGMRES、零初值、**最多4次新的B4_DD作用、一个4维周期**。1e-4仍仅作提前返回目标；未达标但有限、约束合法就返回近似。每次计算native A4残差和eps；不跨RHS保留搜索池，不使用已知解热启动，不增加到8/16/64步寻找通过。25秒请求安全返回、30秒费用线沿既有机制；每个A4/局部/粗层回调均可见外层deadline。

**四步是一次固定候选，不是四步一定足够的承诺。** 两级PC表示局部/全局两种修正，不是两套必须迭代收敛的循环。所有local solve、S solve、A4、正交化、真实残差成本均计入；MPI1成本按全部块之和，不按最慢块冒充并行时间。若四次强修正仍无整体收益，关闭本候选，不自动用几百次I4换取内层收敛。

## 4. M0–M1：一次合并检查，区分近似逆问题与组合问题

M0按根/docs/适用AGENTS和当前task核对canonical worktree、branch/HEAD/upstream、clean source、ABI/complex128/IntType、MPI/线程、MemAvailable/cgroup、swap、disk、watchdog。prototype提交后再正式运行。读取旧16-slab/PML、实体/patch的相关经验，不再重写全历史。

只做一个合并focused批次：复数内积、Floquet合法R/RH与回填、完整覆盖/权重、局部主子矩阵、端口增广符号、输入不变、单块奇异、零RHS、有限截断、计数/清理。局部每块用两个固定合法w构造D_i w并回代，真实相对残差不高于1e-10；不为每块形成稠密L乘U或求全谱。选至多三个代表块（材料交界、端口、普通内部）用native A4嵌入/限制的三个固定向量核对D_i，沿操作尺度1e-10；cached/native沿1e-11。

检查实际C_U粗层闭合及DD公式；local准确不冒充全局准确。可复用物理/形状/坐标和ABI完全一致的对象，不能因局部行数相同混用材料因子。notch不依赖只适用于original的历史硬编码owner packet：复用通用生成路径，仅重建材料变化影响的对象并绑定hash。

### 4.1 少量已有g/c_ref：直接看内部误差，不只看残差

最多复用六个旧g1/g2及确实匹配的p4参考系数，不重新构建p4或fine全局参考因子。仅有g无匹配c_ref时记录残差与局部统计，误差项为`REFERENCE_UNAVAILABLE`，不猜误差，不单独阻断正确的正式试跑。

在每个g上比较一次B4_DD作用和本轮最终I4_4；前者可从后者首步共享算子数据，不要求首步MR修正等于裸B4输出。报告：

```math
\epsilon=g-A_4c,\qquad e_4=c_{\rm ref}-c,\qquad
\rho_4=\frac{\|\epsilon\|_2}{\|g\|_2},\qquad
\eta_4=\frac{\|e_4\|_{M_4}}{\|c_{\rm ref}\|_{M_4}}.
```

M4为已有无损场范数，scaled-curl另报。核对A4 e4=eps-r_ref及reference自身残差。与可复用的旧实体16结果同输入比较，旧数据缺失不重跑旧长程。最多新增6次I4；仅将M0场误差分配到材料/高度和patch边界带作线索，不能把残差系数当电场，也不能仅凭界面集中判定反射。

### 4.2 三个真实难误差：直接比较“保留/取消第二次反馈”

对A2R160、LIGHT448、JOINT448最多三个现有合法q，使用同一新I4_4计算一次zc、s和第二次粗响应t，同时得到两种完整方向：

```math
z_c=P_{64}I_4(P_{64}^Hq),\qquad s=H_6(q-A_6z_c),
```

```math
z_{BAL}=z_c+s-P_{64}I_4(P_{64}^HA_6s),\qquad
z_{ONE}=z_c+s.
```

**ONE_C是粗修正后接一次细修正的单向乘法组合**，不是旧H6-C-H6逐段MR，也不是更改物理A。它少一次p4求解，但不再保证精确粗层平衡；是唯一框架挑战者，不预先认定BAL更强或ONE更强。两个方向共享首次p4/H6计算，最多6次新增I4，不创建两个独立重型PC。

对q对应的真实误差e（正确处理q归一化）分别测量剩余场误差、scaled-curl、原A6残差比和完整方向成本。q不是b时不能拿x_ref本身当e；必须从匹配旧x与reference得到e，检查Ae与q的关系。未取得该关系的样本只报告残差，不冒称真实误差控制。三个旧e高度相关，不视为三个独立谱模态或所有RHS的证明。

同时检查，而非强迫为零：

```math
P_{64}^H(q-A_6z_{BAL})=\epsilon_1-\epsilon_2,\qquad
P_{64}^H(q-A_6z_{ONE})=\epsilon_1-g_2.
```

闭合沿操作尺度1e-8；分别报告右边真实大小和闭合误差。后者小只是实现记账正确，前者才反映尚未满足的粗层方程。第二次近似反馈使场或残差恶化，不等于反馈公式写错，也不直接等于rank不足。

### 4.3 框架只选择一次，不跑笛卡尔积

M1至少两个有匹配e的有效样本时，若ONE/BAL的场误差比例几何平均不高于0.80、最大不高于1.10，scaled-curl几何平均不高于1.10，原A6残差比几何平均不高于1，并且ONE的完整作用时间不高于BAL的0.80，则选择ONE_C；否则选择BAL_H。近零分母按1e-12的共同输入场尺度处理并标记，不能用除零制造收益。选择阈值是有限工程规则，不是框架优劣定理。

缺匹配e时保留BAL_H作为已验证机制起点，框架诊断标`AUTHORITY_LIMITED`；不从几个残差比强推ONE_C。ONE未被选择不等于其数学失败。不要求裸PC单次残差小于1、不要求所有rho4低于1e-4。正确性、资源与可用非零方向合格后，直接进入真实规模比较。连续两次非零输入没有合法修正、或每次I4持续超30秒则`INNER_COST_BLOCKED`，不长跑。

M0/M1合计计算预算5400秒，其中新局部构建不超过3600秒、有限数值控制不超过1200秒（包含关系）。已有数据直接复用；不做新的fine reference、全局特征值/奇异值分解、LFA或另一轮最佳p投影。独立诊断项目缺参考，不取消不依赖它的检查；共同算子/约束/非有限/资源错误严格停止。

## 5. M2：同一PC下比较restart32与64，避免将相关性当因果

采用M1选定的一个框架和同一DD4，固定B4及局部因子、零外层初值、无recycling/状态池、同样orthogonalization。两次真实original probe分别用right FGMRES32、FGMRES64，各最多64个外层步、solve2400秒、workflow3600秒。仍是原三维PDE，不改网格或RHS，不用玩具矩阵替代。

两probe顺序执行，局部因子可在同身份下加载；cache/fresh费用分别列出。每次保存实际A4/B4/local/S/A6次数、每8步真残差、每32步solution-only checkpoint、完整RSS和时间。禁止保留第一个probe的Krylov基或解给第二个。前32步应在既有数值容差内复现，核对真残差及第32步解；不一致先报告PC状态/源码/数值身份问题，不能将差异解释为restart收益。

第二个probe的前64步没有周期性restart，但正式选64后仍每64步重启；不是无限unrestarted。64比32可能保留更多方向，也会增加正交化与存储。当前存储长度173802下，按两组V/Z估算新增64个长向量约177973248 B（derived），与实测RSS分列；不能把此固定模型字节数外推为短波常数。

比较同一步数32/40/48/56/64的rho与场误差（评价端可用已有fine reference），以及总用时；不要拿不同停止点作残差排名。两次都到64时，记：

```math
q_R=\rho_{64}^{(restart64)}/\rho_{64}^{(restart32)}.
```

若q_R不高于0.50、到64步的solve时间比不高于1.25且资源合格，正式选restart64；否则正式选restart32。只在该输入/PC/64步窗口下说明是否有实质restart损失，不宣称一般定理；32附近出现平台本身不是证据。

如资源或单步成本使某probe在2400秒内未达到64，不插值、不补长跑：restart归因记`INCOMPLETE_AT_COST_CAP`，正式默认32。若两probe均未达48步，则本候选按`WHOLE_PC_COST_NOT_VIABLE`收口；不能为一个昂贵PC继续延长内部。某probe已达最终残差可立即执行第7节官方输出，完整通过则算实际original成功并直接notch，余下probe/重跑为not_run_goal_met。

**M2最多两次原始短probe；不再扫描96/128/256或无界full GMRES。** 若内存允许而两个64步窗口仍都弱，不能只根据Krylov小矩阵条件数归因全部物理误差。采用样本上的直接纠错/受控干预结论，不需要全谱才能作下一决策。

## 6. M3：选择后完整求解，不再修改配置

若M2未已完成original，最多一次新正式original，使用所选框架/restart及同一I4_4，从零开始。不能加载probe末尾解来冒充fresh成功，也不重新建立无关数据；这部分重复前缀成本须明确计入总账，是将有界归因与完整资格分开的代价，不是四套不同算法。

外层max2048，每8步及退出检查原A6真残差，每32步保存安全解。沿V9时间投入线：solve约1800秒时rho大于0.10停止；约5400秒仍大于1e-3停止；否则最多solve10800秒/workflow14400秒。全部内层和检查计费，首个安全点如实记录越线，不等巨型PC返回才看预算。不要求内部先收敛，不放宽最终1e-6。

original通过后立即同配置notch，重建匹配材料对象，零初值，无历史空间。不得为notch改块、框架、restart或I4工作量。失败保留几何适用性缺口并收口，不自动启用另一个框架。如果所选框架和重启仍无效，本批不再试剩余组合。

因此本批最多：两个64步原始probe、一个选定配置fresh original、一个条件notch；M1不另起full solve。存在直接达到目标的probe时省略重复工作。每一场包括失败probe都须注册为真实PDE记录，不能将它们隐去后称“只跑了一次”。

## 7. 精度、资源与可扩展性边界

| 完整Gate | 固定门槛 |
|---|---|
| 原始fine方程 | norm(b-A6x)/norm(b)不高于1e-6 |
| 同模型reference场 | L2与scaled-curl相对差不高于1e-4；selected E/H、近场同坐标；近零量另报绝对差，不拟合相位 |
| 功率/体吸收 | R/T/A/A_volume分别对同模型reference绝对差不高于1e-5 |
| 独立守恒 | R+T+A_volume与1之差、A与A_volume之差不高于1e-5 |
| 全部80模式 | 复幅值相对差不高于1e-4；逐通道功率最大绝对差不高于1e-6 |
| 数值身份 | 局部限制、native/cached、CU、框架对应eps关系合格；ONE不能误套BAL零粗残差测试 |
| 资源 | 全生命周期同期process-tree/cgroup、系统余量、zero-swap、全部成本与hash合格 |

未达最终残差的场只作diagnostic，不输出official R/T/A。两种结构不互作误差参考。仅收敛后输出工程故障允许从同一合格解恢复一次，不重求场。失败解可按现有参考计算diagnostic场误差，不能因为不是official输出就禁止原因分析。

本机reserve=max(4GiB,15% effective_total)；effective_total取可见物理与cgroup有效限额较小者；cap=min(12,000,000,000 B,effective_available-reserve)，运行中维持余量。一次一个heavy，包含编译器/子进程；swap新增按原合同安全停止并区分归因，不改系统校时。硬安全优先于保存和诊断。

S/p2仍受8192总行、其matrix/factor/转换/workspace预审512MiB约束。本轮新增全部局部matrix/factor/索引常驻预审上限2GiB；局部构建与分解临时workspace另预留1GiB并计入总cap。超过预算时在相应阶段停止，不扩上限或偷偷切ILU。旧实体因子可释放，不同时常驻旧与新两套大PC；已有CU/FE/缓存、I4短基和外层基另列。以上是policy/derived模型，不是保证实际RSS小于该值。

| 费用项 | 本轮上限（非完成时间承诺） |
|---|---|
| M0/M1全部准备、构建、测试、控制 | 5400 s；子预算为包含关系 |
| M2两个真实probe | 各solve2400 s / workflow3600 s |
| M3 original与条件notch | 各solve10800 s / workflow14400 s |
| 全批实际计算总账 | 43200 s；父子不重复，reservation与actual分开 |
| 不授权 | p4/fine全局LU、全局稠密Schur、局部参数扫描、超过4次I4工作、无限unrestarted、旧recycling增rank、其他波长heavy |

开始计时必须覆盖实际本轮准备；若旧准备阶段缺日志就明确unknown，不能把reserved额度变为实测。新局部符号/数值setup、warm加载、所有块回代的合计、全局粗层次数、Krylov正交化和后处理分别记录。局部LU非零数乘16只是数值下界，不能替代总RSS。参考与候选不同时间峰值不相加。

当前42个组与2600行只是pilot设计；未来固定块行数并不自动保证波长鲁棒，更多块的全局纠错、粗问题规模、DtN分布、总因子库存仍需解决。即使本轮收敛、内存超过旧1.5GB，也如实评估完成同任务的总成本，不追求最低组件RSS。2TB目标既不是全局LU放行理由，也不要求所有局部因子为零。

## 8. M4：输出可操作的归因，不再只写“PC弱”

统一提交`response_v11.md`，建议仅新增一个中心`outcomes/physical_macro_inverse_v10.md`和一个hash-bound compact。更新summary、run_index、test_summary、development_progress、development_model_registry、handoff；历史正负结果不改判，不无限叠加互相矛盾的“最新”段落。

必须用下面的决策表收口，各项证据不足可并存，不强迫单一根因：

| 已测情况 | 支持的下一判断 | 不能推出 |
|---|---|---|
| 局部D_i回代不合格 | 局部逆/人工限制先不具备资格 | 所有DD无效、p4本身无解 |
| 局部准，rho4与真实e4改善很弱 | 当前分块/全局纠错配合不足 | 仅靠增加几百步即可解决 |
| I4质量较好，BAL比ONE显著差 | 两次近似粗反馈可能不适配；由选定ONE完整结果继续裁决 | BAL_H在所有情形错误 |
| 同PC的R64比R32明显更好 | 该窗口restart损失值得处理 | 无限不重启就是0.7nm生产方案 |
| R32/R64都弱 | 延长搜索空间不是当前已证实的主解法 | 全部低内存迭代算法不存在 |
| 同离散场/功率通过但成本很高 | 数值机制有效、工程成本不足 | production/波长鲁棒已通过 |

每个模型分别给出同迭代节点和同时间附近节点，附所有内层/局部/底层成本。框架比较列出zc、s、t的作用，不把正确的eps闭合误写成eps足够小。restart比较是当前新PC诊断，不追溯宣称解释全部旧失败。没有匹配参考时必须保留精度限制。

结论状态至少区分`LOCAL_INVERSE_UNQUALIFIED`、`RESOURCE_BLOCKED`、`FRAMEWORK_COMPARISON_LIMITED`、`RESTART_DIAGNOSIS_LIMITED`、`FULL_OUTER_CONTROLLED_NEGATIVE`、`ORIGINAL_PASS_NOTCH_UNQUALIFIED`、`TWO_MODEL_NUMERICAL_PHYSICS_PASS`及资源/时间附加资格。没有完整结果不能把局部测试数或低RSS当作突破。

本批结束即停止，正常分流连续执行，不每个小测试停审。失败则提出唯一主要缺口与一项后续设计，不自行追加另一个shift、PML、粗空间或网格。BAL_H只是当前基线；若无优势，保留其成功记录但停止将它作为未来唯一框架。5nm独立线的进展由其任务裁决，不由本review取消或等待。

提交计划：局部构建/作用与最小测试 -> clean SHA有限检查/选择 -> 两个有界真实probe -> 冻结单一正式配置并完成条件原始/缺口 -> compact/docs/response。所有运行绑定input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json及ABI/MPI、mesh/map/mode/factor与artifact hash。终止保存合法解及真残差、释放KSP/PC/因子与无用矩阵、记录RSS下降后恢复合格输出。

ChatGPT只新增此review；Codex不改review、不amend、不强推、不合并master，不擅自merge/rebase其他活动分支。HEAD推进先核对变更范围及运行身份。

## 9. 理论依据与适用边界

- [PETSc PCASM](https://petsc.org/release/manualpages/PC/PCASM/)：局部块各有自己的求解器；局部近似和组合需明确。本候选直接构造局部矩阵，不以PCASM名字为由要求全局AIJ。
- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：允许内部非线性/变化求解；不保证任意截断近似有效。
- [PETSc KSPGMRESSetRestart](https://petsc.org/release/manualpages/KSP/KSPGMRESSetRestart/)：较长搜索基的收敛、内存和正交化权衡。在线版本不是本机ABI升级授权。
- [历史经验](prior_attempts_retrospective.md)：旧physical slab成功、固定粗空间的短波限制、巨型PML构建成本以及旧长Krylov负结果均需保留，不以相同方法名重复宣称新颖。

**本轮的交付不是“一个更复杂的PC”，而是一个受内存和工作量约束的完整物理粗逆候选，加上能区分内部质量、框架耦合与restart损失的真实证据，并在有资格时尽快完成原始与非可分三维计算。**
