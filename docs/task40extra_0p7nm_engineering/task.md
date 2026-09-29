# Task40extra：面向0.7 nm任意三维Maxwell的可计算工程路线

## 0. 当前授权：先得到真实0.7 nm非可分三维小模型，再建立扩展依据

**第一批不要再把13.5 nm笔记本模型压快几秒，也不要一上来重做“低内存强p4逆”。先复用Task39extra双凝聚路线，在笔记本上完成真实0.7 nm材料、完整Floquet/DtN、非可分三维缩小几何的有限元解；用不同离散、边界截断和一个适度电尺寸增长点，确定实际精度/成本。**

本任务的最终目标是约2 TB物理内存单节点上快速、可复现地求解0.7 nm、周期单胞内任意非可分三维Maxwell。第一批的缩小几何是工程验证载体，**不是目标尺寸的0.7 nm资格**。最终生产路线必须摆脱随全域增长的大型直接因子和无界局部/端口库存。准确p4双凝聚继续作为近期可靠求解器与小规模对照，不把它直接宣称为最终架构。

```text
repository                 = Rookie1234567/MyFEniCS
new_task                   = Task40extra（不是既有Task040 Hybrid）
execution_branch           = task40extra_0p7nm_engineering
base_branch                = task39extra
base_SHA                   = 95dacd01e86f0f7f1d29ee2d5e5a16039bb41871
inherited_numerical_HEAD    = e09bd1612c4f6ca5fb5cf3572835748ad5c16207
inherited_V31_run_source    = d9b545e824296fce1b489c32a5d96e5e9303ff3c
created_date               = 2026-09-29
initial_batch              = A0 -> A1 -> A2 -> A3 -> conditional A4 -> A5 -> A6
response_required          = response_v1.md
initial_environment        = qualified laptop WSL/Linux, complex128, MPI1/math_threads1
formal_entry               = python scripts/run_case.py input/path/to/case.dat
workstation_changes        = NOT_AUTHORIZED
master_merge               = NOT_APPROVED
ordinary_default_change    = NOT_APPROVED
```

base必须是已经包含Task39extra最终报告的收口提交；它不是master的生产release。用户明确要求从task39extra派生新分支，允许本次stacked research branch及远端初始化。Codex不另造同义分支，在canonical clone登记独立worktree，追踪同名origin分支；旧工作站树和旧任务资料只读。

**本批消除的blocker：** 缺少便于快速试验、真实0.7 nm材料的非可分三维PDE锚点，尚不知道精度合格的离散需求和内存增长分别由哪些对象主导。不能在没有这组事实之前，把13.5 nm内核提速外推成0.7 nm工程方法。

## 1. 开始前必须读的继承材料

读取根与适用目录AGENTS、`docs/repository_work_principles.md`、`docs/markdown_rendering_standard.md`，再读：

1. [Task39extra最终报告](../task039_extra_physical_multilevel/final_report.md)和[最终review](../task039_extra_physical_multilevel/review_report_v30.md)。
2. [Response V33](../task039_extra_physical_multilevel/response_v33.md)、[补跑record](../task039_extra_physical_multilevel/outcomes/records/projection_layout_v31_authorized_rerun.json)、[V29基线](../task039_extra_physical_multilevel/outcomes/records/a4_tensor_h6_v29_compact.json)。
3. [历史经验](../task039_extra_physical_multilevel/prior_attempts_retrospective.md)、[文献边界](../task039_extra_physical_multilevel/literature_review.md)及与拟选算法直接有关的旧review，不重新全量重测过去失败方法。
4. [冻结2 nm工作站交接](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/f2_running_handoff_20260928.md)：只当2026-09-28快照，不宣称实时状态。

旧Task39extra的单批额度、8 GiB旧字段、实验顺序和禁止进入0.7 nm的范围不自动继承为本任务授权。根规则、真实数值/物理正确性与安全原则继续适用。本task没有授权修改工作站策略、停机、热更新或启动工作站PDE。

## 2. 三条路线及本批边界

| 路线 | 目的 | 本批执行权限 |
|---|---|---|
| **A：双凝聚工程锚点** | 尽快得到真实0.7 nm非可分小模型的完整FE解，量化离散误差和成本 | **必须实现/运行本任务列出的首批模型，不得只交docs或组件PASS** |
| **B：无全局大因子的Full3D路线** | 有界局部求解＋多层全局波动纠错；不要求廉价p4逆模仿LU | 本批完成证据驱动设计和接口/规模分析；完整新PC在下一review冻结后实施，不一次摊开多种PC |
| **C：高通道与一般几何存储** | 避免全域FE×mode表、每cell稠密因子和无限类型缓存 | 本批做真实局部尺寸的有界容量/动作组件审计；不自动替换已失败的流式生产路线 |

先把A做出实际解，再依据A/C的结果选择B的一种具体方案。此顺序防止既没有0.7 nm参考、又一次性重写PC/网格/端口三套架构。B/C不是放弃，而是作为本任务后续主线；后续不得无限停留在小模型准确p4或单线程微优化。

MUMPS后端、排序、主元、BLR/OOC、线程和已资格化ABI，本批保持原设定；改变矩阵的物理输入是新模型的必要变化，不构成后端扫描。初始不试p3/p2粗阶、不换H6次数、不改restart、不引入神经网络/GPU/Hybrid替代核心。原有正确性Oracle保留。

## 3. A0：已有成果只读收口与新worktree登记

核对远端新分支、base祖先、HEAD/upstream、canonical worktree和clean状态。若已有新提交先读差异，不reset、不强推、不整体cherry-pick研究分支。确认旧heavy进程未占用笔记本；不通过SSH处理工作站运行。

只读本机已有V31补跑与V29/V30的raw：重算可用的FE L2/scaled-curl、同坐标E/H、复模式差，补齐能从原记录恢复的ABI与实际线程信息。缺失则标unknown，不用当前环境反填。输出`outcomes/inherited_baseline_audit.md`及轻量record，不改旧final_report/response，不为旧场再启动PDE。

若只是旧raw丢失，记录限制后继续新任务；若发现可重复的实际映射、残差或数据身份错误，先作最小修复和相关小测试，不带错进入新物理模型。

## 4. A1：冻结真实0.7 nm材料与几何，不复用13.5 nm光学常数

### 4.1 材料

真空波长固定0.7 nm。先找仓库已归档的0.7 nm Si、介质和外部半空间材料原始来源；只读其他已授权仓库分支的材料/compact可以，禁止把其全部数值源码迁过来。已有合格数据优先，不因网页新值不同擅自覆盖。

若继承快照没有合格0.7 nm材料，本task授权从CXRO/LBNL原始光学常数或其原始散射因子数据建立**新的研究材料包**。保存URL、访问日期、原始表、波长/能量转换、密度和单位、插值规则、n/epsilon/mu的符号约定以及SHA。不得跨吸收边无说明插值，不使用13.5/5/2 nm的n冒充0.7，不放大损耗帮助收敛。原始数据无法取得、材料身份冲突或缺项时，对受影响PDE标`MATERIAL_BLOCKED`，仍完成不依赖材料的审计，不伪造数值。

空气沿继承物理模型的真空背景n=1约定记录；Si用于grating和substrate，mu_r=1。与e^{-i omega t}约定相容的被动复材料须核对。0.7 nm数值**不在本任务书预填**，以保存的原数据和解析结果为准。

资料入口：[CXRO折射率数据](https://henke.lbl.gov/optical_constants/getdb2.html)。本批是连续介质Maxwell工程研究，缩小至纳米几何时bulk局部epsilon的物理适用性仍为建模假设，不能把FE求解通过当作原子尺度材料模型验证。

### 4.2 非可分三维缩小几何G0

从Task39extra已冻结的notch实体并集/边界面生成器继承**实际物理实体**，不是在每张新网格上重新按cell中心筛选不同空洞。参考几何外尺寸50×25 nm、z=-10…130 nm、Si栅宽17 nm/高120 nm、Si基底厚10 nm；对应notch实际并集见旧`dual_condensed_robustness_v21`及其frozen mesh plan。

对所有几何坐标、界面、probe和采样平面统一乘：

```math
s_0=0.7/13.5=7/135.
```

得到G0外周期约2.592593×1.296296 nm，z约[-0.518519,6.740741] nm。以原始float64坐标及唯一比例生成，保存未舍入值和identity；展示小数不是数据源。材料改用4.1的真实0.7 nm包，不保持旧epsilon。

必须证明材料分布不沿y或z均匀，且没有把内部区域替成解析传播；记录nonseparable witness cell/坐标和实体volume。若旧notch几何artifact缺失，依据已跟踪的实体并集与界面坐标重建并独立核对，而非静默改成original挤出模型。

这保留了与13.5 nm源模型相近的电尺寸，只能检验0.7 nm材料/实现链，**不能证明波数或目标几何扩展性**。A4另设固定0.7 nm、增大物理尺寸的试验。

### 4.3 网格和通道

同一G0上首先使用两张boundary-fitted p6网格：

| case | 目标h | 用途 |
|---|---|---|
| G0-C | 10×s0 nm，约0.518519 nm | 先得到小规模完整0.7 nm非可分解 |
| G0-F | 7.5×s0 nm，约0.388889 nm | 同一几何的加密解；继承细轴计划可约990 cells，最终以实际count为准 |

保留所有材料界面和notch边界；可以通过合并/细分界面之间的中性区间构造coarse网格，但不能删除界面来降低容量。F的原始计划需实际geometry/key核对，不硬填990掩盖变化。p6和同网格p4使用同一合法mesh及相容约束。

x/y双Floquet，grazing1°、azimuth0°、s偏振、电幅值1，z外部仍Fourier-DtN。为G0真实0.7 nm材料重新生成全部传播通道及既有规则所需的倏逝通道；记录signed beta分支、ordered keys、near-grazing项和normalization。不沿用旧80这个数字，不把输出显示范围当算子通道范围。C/F比较先冻结同一端口inventory/积分资格。

生成`outcomes/records/model_plan_v1.json`，记录上述全部实际数字、几何/材料/mesh/mode/probe hash、p6/p4完整/独立/trace行数和字节预算。在正式求解前提交冻结；后续变化另起case identity，不能重写已经运行的计划。

## 5. A2–A3：用双凝聚完成两张网格，不只做setup

### 5.1 数学与实现

```math
A_6x=b_6,\qquad C_4=P_{64}F_4P_{64}^{H},\qquad
M_6=C_4+(I-C_4A_6)H_6(I-A_6C_4).
```

继承p4装配时凝聚＋MUMPS、p6 matrix-free凝聚外层、right FGMRES32/max2048、零初值、H6原短处理/原power10、完整A6/A4验算和V31自然序。尺寸/材料变化时全部重新生成必要局部数值数据和factor；只复用身份合格的JIT/只读参考表。

新profile建议`physical_p6_trace_0p7nm_engineering_v1`。原runner中硬编码13.5、990或80的地方只做最小通用参数化并加真实小例测试，不删除identity检查、不将新数值算法塞进task-numbered benchmark。保留旧profile字节行为。只读oracle不得暗中启用新候选实现作为唯一对照。

每次原A4初解及精化后完整检查，目标1e-10、最多两次额外同factor精化；有限完整但目标未达时按最佳FE/alpha/A4c/e一致状态返回并继续外层。因子/约束损坏与NaN/Inf仍拒绝。记录logical C、actual MatSolve和检查次数，不能把“exact LU”当每次浮点残差必为零。

### 5.2 完整运行和参考

先G0-C，成功后直接G0-F，不在每一个组件测试、setup或candidate选择后停审。正式入口：

```bash
python scripts/run_case.py input/task40extra_0p7nm_engineering/g0_c_0p7nm.dat
python scripts/run_case.py input/task40extra_0p7nm_engineering/g0_f_0p7nm.dat
```

以上文件由Codex基于冻结计划创建，每个dat只表示一次运行。正式前clean源码、已提交，环境qualified；运行中不改该worktree源码或HEAD。每场setup通过后，直接用同进程同factor完成KSP和后处理；不额外建工程factor测一次PC后再重建。

独立原A6真残差、释放后残差均<=1e-6，每8步完整残差、每32步场，末态不论是否整倍数都保存可用状态。可用时对G0-C做**至多一次同离散p6直接authority**，只在symbolic与实际总内存安全时运行，目标1e-10。不安全即`DIRECT_REFERENCE_BLOCKED`，不降阶/换网格后冒称匹配参考，也不为参考开启OOC/BLR。它只用于小模型检查，不作为大规模生产路线。

h比较使用公共物理积分点或合法跨网格FE比较，界面两侧和材料区域分别处理，不把节点插值误当H(curl)参考。保存复E/H、curl、所有模式复振幅与功率、R/T/A、体吸收和同坐标近场。

## 6. 数值、误差和性能Gate

| Gate | 要求 | 失败含义 |
|---|---|---|
| 数值实现 | 作用/传递/约束/凝聚恢复小例等价相对1e-10；接近零量用既有绝对尺度 | 实现缺陷先修，不评判方法不可能 |
| 正式线性求解 | 原A6及释放后<=1e-6，所有量finite | 未达到则不出official R/T/A |
| 能量/吸收 | abs(R+T+A_volume-1)<=1e-5，abs(A_balance-A_volume)<=1e-5 | 与残差分开报告，不靠能量单独证明全场 |
| 同离散authority（若有） | FE L2/scaled-curl、E/H和复模式相对<=1e-4；R/T/A绝对<=1e-5；逐模式功率<=1e-6 | missing为AUTHORITY_LIMITED，不伪造PASS |
| 首批h工程目标 | C/F的全E/H和scaled-curl相对变化<=1e-3；R/T/A/A_volume绝对变化<=1e-4 | 两点只能叫tested-pair指标，不称连续极限收敛 |
| 弱散射可辨识性 | 另报E_scattered相对/入射归一绝对误差及显著衍射复幅值；相对1e-2为首批目标，分母近零同时给绝对尺度 | 不能仅用被入射场主导的total E误差掩盖散射误差 |
| 边界截断 | 6.1的扩充inventory对照；缺失或不达标单独限制资格 | 不把h变化当DtN截断已收敛 |
| 性能 | wall/CPU、setup/KSP/check/output、迭代及全部内求解、完整RSS；一数量级真实残差所需时间 | 少outer步不等于更快，局部便宜不等于总量小 |

这里1e-3/1e-4是本任务初始工程筛选目标，不是用户实际器件精度规格或误差定理。弱信号相对误差分母必须在A1定义，保存绝对范数，不对结果拟合全局相位。固定波长材料下不同几何的场不得拿same-discretization Gate直接比较。

### 6.1 一个必要的DtN敏感性点

在已成功的G0-C同一网格上，保留全部原keys，再按当前Fourier索引规则至少扩展一圈允许的外部倏逝阶，不删传播阶、不改几何/材料。若现有接口只能auto_propagating，允许最小的显式inventory入口实现，但必须独立测试索引、branch、范数和fine/coarse的一致性。

完整执行至多一次`g0_c_more_modes_0p7nm.dat`。使用原单元积分精度及必要更高边界积分，分列这两种误差影响；与G0-C比较同坐标E/H相对1e-3、R/T/A变化1e-4。通过只称该截断配对通过；不通过则保留`DTN_TRUNCATION_UNQUALIFIED`，不自动逐级增M扫描。下一review决定是否增加隔离层、边界表达或通道数。G0-F可作为离散求解证据继续报告，但不能因此授予完整工程精度PASS。

## 7. A4：一个电尺寸增长点，而不是再次同比缩小所有量

仅当G0-C/F数值正确、资源与误差事实已记录且笔记本有安全余量时，构造G1：**波长仍0.7 nm，真实材料不变，G0所有几何长度乘1.25，h保持G0-F的目标值**，所以k0L真实增加。notch实体也同比放大，再重新生成boundary-fitted网格及完整通道。不要把h也乘1.25而使离散工作量几乎不变。

先只做count、channel inventory、symbolic与容量检查；满足资源条件才执行一次`g1_f_0p7nm.dat`。因容量不满足标`SCALE_POINT_RESOURCE_BLOCKED`，不自动选择1.1、降p或削M替代。安全预测是准入依据之一，但旧固定2×symbolic、8GiB和历史RSS成绩不得自行当硬停止线。

G1目的不是与G0场值相同，而是测每单元/每trace/每mode存储、factor填充和每log残差下降成本。一个增长点不构成渐近标度证明；配合已有13.5/5/2 nm记录，只建立带不确定性的模型，不混合来源拟合一个“精确幂律”。

## 8. A5：为2 TB生产路线形成可执行的下一步，而不是只写愿景

### 8.1 先算真实库存，后决定哪种算法

对本批每场保存matrix/因子、局部数值cache、端口、Krylov、ghost/map和监控库存，区分ndarray view与backing buffer、后端used/allocated和同期RSS。要对重复类型丰富与全部局部几何独立两种情况做派生上界；不制造TB数组验证一个尺寸公式。

```math
M_{\mathrm{Krylov,principal}}=16N_\Gamma(2m+1),\qquad
M_{\mathrm{local\ LU,unshared}}\approx16n_i^2N_{\mathrm{cell}},\qquad
M_{\mathrm{peak}}=\max_t\sum_jM_j(t).
```

p6 ni=450只是当前单元族。给出总局部因子数与最大单块大小，不以“单块很小”掩盖所有局部因子总和。分析schema/CSR/mode/全局行号的32位溢出风险；本机合格int32不等于目标规模可用，64位ABI是后续迁移Gate，不在本批升级整个环境。

2 TB整机预算按十进制与TiB分列，扣除明确OS/监督余量，设置例如1.3/1.6/1.8 TB的**情景表**，不是改写工作站当前1.3 TB硬线。目标几何优先用户已有实际定义；未给新器件时仅以旧50×25×140 nm作benchmark外推，并明确不是最终所有几何的保证。材料、通道实际inventory和精度合格h须重新生成；h=0.525 nm只是2nm例子保持h/lambda的情景，不能当精度结论。

### 8.2 真实局部尺寸的高通道小组件

复用已存在端口代数和组件接口，固定1–4个实际p6局部块（内部450、trace432或本场真实边界支撑），取本场通道，再取512和3904的组件维度诊断。超过本机安全池时只做解析计数，不构造mode平方oracle或全网格FE×mode表。与现有低维toy区别写明：mode方向/权重来自实际规则时标physical-component；合成数据标diagnostic。

检查左右耦合独立、非Hermitian复材料、非零内部/端口RHS、凝聚/恢复身份。只做原合格缓存方式和一种有界分块作用的组件对照，完整matrix action时间和重计算次数都计入；不直接启用旧端口流式负候选，也不因为省字节就默认接受更慢方案。

### 8.3 无全局大factor路线的下一版具体设计

输出`outcomes/next_solver_design.md`，至少把以下两类问题分清，并依据本批残差/库存选**一个**首选：

- 高阶正定/局部处理：相容H(curl)辅助空间、low-order-refined或有界局部问题，用来降低高阶操作/局部逆成本。它不是把同网格p6改成p1，也不自动解决高频不定性。
- 真实跨区传播：在p6 trace空间进行有界子域处理与多层全局纠错，避免全域p4 LU；粗层继续递归/迭代，不能在顶层引入另一个随总规模增长的direct factor。

示意结构只规定组织，不冒充已验证实现：

```math
\mathcal M_\Gamma=\mathcal M_{\mathrm{local}}+
P_0\mathcal C_0R_0(I-S_\Gamma\mathcal M_{\mathrm{local}}).
```

下一设计须给出：局部边界及吸收仅在PC的位置；H(curl)梯度/旋度/周期相位相容性；coarse空间如何表达长程波动而非仅正能量低频；单块/总factor/粗层/端口库存上界；内部工作上限；不变量与失败诊断。将与Task39extra早期42宏块、弱p4、普通AMG/Schwarz失败相比的**实质差异**写明，不允许仅换名再扫ILU/shift。

本批不强行部署未经定义的新PC到0.7 nm；完成实际小PDE和上述设计后，由下一review冻结唯一候选、指标与试验顺序。后续全局p4只可作小规模reference；不能只要它还能装下就无限扩大，绕开最终架构目标。

参考边界：

- [Bonazzoli等，Maxwell吸收问题的DD](https://arxiv.org/abs/1711.03789)：波数鲁棒理论依赖足够吸收及尺度/重叠条件，不是给真实材料加损耗的授权。
- [Pazner等，de Rham low-order-refined](https://arxiv.org/abs/2203.02465)：支持高阶正定/扩散型辅助问题的低阶细化结构，不直接保证含完整DtN的高频不定Maxwell收敛。

## 9. 运行资源与明确停止规则

本任务建立新账本，不复用/清零Task39extra或工作站的运行额度。初始在笔记本qualified WSL Linux环境、MPI1/数学线程1、接电和固定电源模式执行。不得在Windows路径运行正式PDE，不升级ABI来追逐性能。

本批最多五场计划内正式PDE：G0-C、G0-F、同网格扩充mode对照、条件p6直接authority、条件G1。这些是不同目的的case，不是同一性能场反复重跑。若数学不收敛、材料缺失或真实资源不支持，保存结果，不自动改物理/网格/后端连续重试。真实实现bug经最小修复后允许至多一次受影响case定向重放，旧成本全保留；误停不是数值负结果，不能删除。

每个新run生成显式`active_resource_contract.json`：实际RAM/cgroup、当前MemAvailable、task RSS scope、reserve、launch cap、runtime动态余量、swap policy、停止reason、PID/start_ticks及清场规则。

本task新场reserve取`max(1 GiB, 5% effective_total)`，采用原有physical-memory-pressure机制据此计算有效额度，持续检查真正系统/cgroup余量；这是新任务的明确安全设置，不回写旧profile。不是固定8GiB限制，也不是准许程序占满全部物理内存。资源预测仅标predicted；MUMPS symbolic与未来live-set核对后才numeric，后端额度不擅自扩大。

新输入不要再把已失效的`terminate_memory_gib=8`等遗留字段作为可读合同保留而不解释。schema暂时必须保留时，在resolved config显式标inactive并给唯一生效策略；人工操作者与watchdog读同一合同，不另凭印象停止。cgroup memory.current不等于process-tree RSS，但真实cgroup硬限和压力不能忽视。

本批运行要求任务范围swap=0并记录全机活动但不乱归因；如果已有监控只是observe_only，须明确增加新profile的相关检测/受控退出及小fixture后才能称zero-swap资格，不能只改report标签。PSS在heavy期间保持disabled/null，快速RSS/status、失联、OOM预防及后代清场持续有效；不读smaps大扫描做性能判定。

时间目标是尽快完成可审计工程解，不承诺具体分钟或48小时保证。计划内每场沿time observe_only和原max_it，不能因为超过历史126步或40分钟就停；真正数值breakdown、达到max_it、资源/环境/磁盘/监督错误按合同受控结束。一次只运行一个heavy；不自动把账本剩余时间当作新增case许可。

## 10. A6：结果与提交

| 阶段 | 完成物 | 是否可以止于文档 |
|---|---|---|
| A0 | inherited audit、环境和worktree | 否；缺旧raw不阻断无关工作 |
| A1 | source-qualified材料包、nonseparable geometry、mesh/mode与active-resource计划 | 仅材料/身份真实blocked可终止受影响PDE |
| A2 | G0-C完整0.7 nm解 | 必须进入真实求解，不只setup |
| A3 | G0-F、h比较、mode敏感性；条件同离散direct | 数值或资源失败如实收口，不补造通过 |
| A4 | 条件G1实际电尺寸点 | 不安全则明确not_run，不换更容易case冒充 |
| A5 | 2TB情景库存、高通道真实尺寸组件、唯一下一PC设计 | 不用新平台堆砌替代本批实际PDE |
| A6 | response_v1、summary、模型总账和可继承route | 推送同分支后统一审阅，不逐阶段停审 |

状态至少区分`REDUCED_0P7NM_DISCRETE_PASS`、`TESTED_PAIR_ACCURACY_PASS`、`DTN_TRUNCATION_UNQUALIFIED`、`AUTHORITY_LIMITED`、`MATERIAL_BLOCKED`、`RESOURCE_BLOCKED`、`NUMERICAL_FAIL`、`CONTROLLED_STOP`、`NOT_RUN`。不能把target-size0.7、任意曲面几何、2TB/48h或多核资格填PASS。

每场保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json、材料/几何/mesh/mode/ABI/线程/资源及artifact hash；正式E/H、R/T/A、体吸收、全部复模式和near-field不可只保留scalar。

小型JSON/CSV/Markdown跟踪，原始场/矩阵/因子/日志进入ignored artifacts。统一输出以下文件（Codex创建，不提前伪造outcome）：

```text
response_v1.md
outcomes/summary.md
outcomes/inherited_baseline_audit.md
outcomes/engineering_route_v1.md
outcomes/accuracy_and_scaling_v1.md
outcomes/next_solver_design.md
outcomes/records/model_plan_v1.json
outcomes/records/material_provenance_v1.json
outcomes/records/run_index.json
outcomes/records/capacity_2tb_scenarios_v1.json
outcomes/test_summary.md
```

同时更新`docs/development_model_registry.md`和`docs/development_progress.md`中的**新任务章节**，不覆写旧总结。提交按阶段分组：D1计划/参数化/测试，D2冻结输入及实现，D3每场稳定证据，D4整体收口；正式进程活动期间不修改其源码/HEAD。无需为文档提交重复PDE。

最终回答须清楚说明：现在哪个0.7 nm几何已实际算完、哪张网格/多少通道、真实误差与资源如何、最值得继承的路线是什么、达到目标尺寸还缺什么。任何缺项如实报告，测试通过不能代替独立理解/物理资格；后续迁移工作站需用户明确授权，不由本task自动执行。
