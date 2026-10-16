# Task40para：方位90°方柱阵列的方向网格、DtN截断与0.7 nm凝聚直接计算

## 0. 决定、身份和执行范围

**本任务采用新的物理模型，从13.5 nm开始，用p6装配时单元静态凝聚＋全局凝聚系统MUMPS直接求解，分别验证x/y/z网格，再在5 nm验证二维衍射级截断，最后据此选择0.7 nm候选网格与端口集合并执行完整计算。不是继续p4/BAL_H迭代，不需要等待旧A4返回故障关闭。**

```text
repository                 = Rookie1234567/MyFEniCS
task_id / execution_branch = task40para_phi90_mesh_modes_direct
task_directory             = docs/task40para_phi90_mesh_modes_direct
created_date               = 2026-10-16 (Asia/Singapore)
base_branch                = task39extra_para_workstation_capacity
base_SHA                   = 922466da9d7faff408cbb47b7882d179320bdc44
base_latest_commit         = docs: archive V8 P0/P1 BAL_H diagnosis
base_review_response       = review_report_v8.md / response_v8.md
model_id                   = si_block_phi90_50x50_17x20_h120
sequence                   = N0 -> N1 -> D13 -> D5 -> M5 -> DESIGN07 -> D07 -> Z
fine_space                 = complex128 Nedelec H(curl), p6, hexahedron
solver                     = assembly-time p6 cell condensation + exact MUMPS LU
p4_or_p3_coarse_inverse     = NOT_USED
BAL_H / outer_FGMRES        = NOT_USED
formal_MPI / math_threads  = 1 / 1 initially, frozen within all comparisons
worker / parent            = verified CPU24 / CPU9; no CPU-number topology assumption
NUMA                       = interleave nodes0-1 after live topology/permission checks
memory_cap_0p7nm_bytes      = 1800000000000 (decimal 1.8 TB)
memory_cap_13p5nm_5nm       = no user-fixed RSS cap; real host safety remains
PSS_USS_smaps               = disabled; use low-overhead process-tree RSS
swap                       = observe_only; no swap-triggered automatic kill
response_required          = response_v1.md
ChatGPT_scope              = branch and task documents only
Codex_scope                = isolated worktree, adaptation, tests, cases, results
master_merge               = NOT_APPROVED
```

**所消除的blocker：入射与几何身份更正后，没有可继承的方向网格精度或模态截断证据；先建立这一新模型的可信离散参考，避免用错误入射、二维对称约简或不足的端口集合决定0.7 nm网格。** 最终目标仍是约2 TB整机内存中，单场必要构建、求解、恢复、输出和检查全过程不超过48小时的0.7 nm计算能力。本任务的方柱仍是特定结构，不代表任意非可分三维已通过。

用户明确授权ChatGPT从上述父分支新建本分支和任务，此为本次对“通常由Codex建分支、默认从master分支”的覆盖；不修改长期仓库规则。父分支只是代码/历史来源，新任务的执行权威在本目录。用户本轮物理及direct要求覆盖父任务中phi0、50×25、N0/572、p3/p4迭代、pilot16和5万单元限制；旧记录不被改成通过、不用于新模型参考。

用户所说“前面的3阶”，按给出的(-2,-2)、(-2,-1)等例子，本任务明确解释为**每方向0、±1、±2，即m,n各取-2…2，25对级次**，不是只取3个通道、不是仅9个负级次，也不是按功率排序。该范围是要验证的候选，不是已接受的精度结论。

## 1. 分支隔离、已知结果与必读文件

### 1.1 基线事实及其边界

父分支最新Response V8将P0/P1归档为`V8_OPEN / A4_RETURN_GATE_OPEN`。原7步后第17次p4返回仍未通过，native/fast差异的根因未证明；新任务不开展其根因研究。

父分支已有**p6凝聚直接法D**：旧phi0、50×25 nm、沿y不变模型，47,200单元、572通道，A6_n0约1.32e-7，workflow约14.65小时，树RSS约1.304 TB。它证明该直接流程已在工作站完成过，不证明新50×50 nm方柱同样省内存、同样快或同样精确。旧RCWA报告、旧N0解、旧p6h1.5和p4因子均不是新模型authority。[P1][P2]

已核对的直接入口`src/runners/p6_condensed_direct.py`明确只物化一份p6 trace/port矩阵，无p4、H6或外层Krylov。该文件仍含旧profile、572个端口、固定行数和物理身份等专用合同。必须新增本任务的参数化显式入口，**不能仅改dat后绕过或删除这些校验**。[C1]

### 1.2 执行前读

根`AGENTS.md`、`docs/AGENTS.md`、`docs/repository_work_principles.md`、`docs/markdown_rendering_standard.md`；本任务README和完整task；父目录原task、最新V8/Response V8、`outcomes/summary.md`、`review_handoff_0p7nm_balh_20261016.md`、`validation_plan_dispersion_directional_mesh_20261015.md`和`response_dispersion_validation_20261015.md`；相关输入及直接求解/凝聚/模式/后处理实现。

读取旧材料是为了识别资产与缺口，**不是先执行旧V8、旧53万单元、旧N0或旧p3任务**。父V8未关闭是旧任务状态，新任务是明确另立的新物理/direct资格。

### 1.3 工作目录与同步

在canonical clone登记独立worktree，建议`Projects/Maxwell3D-Phi90`；实际路径现场解析。只检出`task40para_phi90_mesh_modes_direct`，不得在旧`Maxwell3D-Lab`或Hybrid工作目录switch/reset/stash/clean。旧任务按用户已有暂停授权保存并收口，不为本任务继续旧长场；未知进程、其他项目不得终止。

结果、JIT/TMP、profile和case路径独立。可以沿用经核验的native Linux ABI，不能复制WSL虚拟环境、重装共享MPI/PETSc或修改隔壁环境。库、解释器、PETSc scalar/index、PORD64及实际映射库逐项记录。没有资格化多线程/MPI收益时沿用MPI1/math1，不扫描排序/主元/BLR。

本分支在base处已包含父代码，无需整体merge其他研究分支。后续必要修复最小迁入并登记来源；不向父分支、task39extra、task40extra、Hybrid或master写入本任务改动。

## 2. 新物理模型：冻结，不再沿用旧对称性

| 项目 | 新固定值 | 必须核验 |
|---|---|---|
| 周期单胞 | x=[0,50] nm，y=[0,50] nm | 周期面积2500 nm²；不能继续用1250 nm²归一化 |
| Si方柱 | x=[16.5,33.5] nm，y=[15,35] nm，z=[0,120] nm | 中心(25,25) nm；宽17×20 nm，高120 nm |
| 基底/空气 | 界面z=0；下端口z=-10，上端口z=130 nm | 基底厚10 nm，上方净空气10 nm，不缩物理域 |
| 入射 | 掠角1°，方位角90°，s偏振，电场幅值1 | 方位从+x转向+y，入射由上向下 |
| 波长顺序 | 13.5 nm -> 5 nm -> 0.7 nm | 每个波长独立材料/模式/physical SHA |
| 材料 | 方柱和基底均为原波长对应Si；air=1，mu_r=1 | 标量复折射率；eps=n*n，不用abs(n)^2 |
| 边界 | x/y双Floquet，上下Fourier-DtN，layered背景，无PML | 原入射traction/背景/总场约定保持 |
| FE | 三维p6 Nédélec H(curl)，complex128，仿射六面体 | 全E/H分量；无二维或TE-only替代 |

按仓库角度约定，应有：

```math
(k_x,k_y,k_z^{\rm inc})/k_0=(0,\cos1^\circ,-\sin1^\circ),\qquad
\mathbf e_s=(-1,0,0),\qquad k_0=2\pi/\lambda_0.
```

最终记录实际代码的波矢、极化向量、两方向Floquet复相位、入射功率、时间谐波约定。90°的cos舍入不能变成不一致的源/边界；仅在既有角度精度策略内一致处理，不能只改其中一处。全局极化符号沿仓库约定，比较复场不事后拟合整体相位。

入射快相位主要沿y，但**kx=0并不表示场沿x不变**：方柱在x/y都有材料边界。不得启用`n=0`、`m=0`、572、286、y两层对称约简或单偏振端口；每个外部级次保留两种切向极化，退化处按实际x/y基处理。镜面对称可作功率诊断，不能不经资格就删除半空间/交叉偏振。

### 2.1 材料原值及来源

沿用父分支的固定材料值，不在此任务中重新拟合：

| lambda0 (nm) | n_Si（方柱=基底） | 父输入来源 |
|---:|---|---|
| 13.5 | 0.999002304859 + 0.00182649365 i | `v5_node1_13p5nm_p6h7p5_q4.dat` |
| 5 | 0.99396854453 + 0.00435380777 i | `v6_5nm_p6_condensed_direct_full600_y2.dat` |
| 0.7 | 0.9998851259969171 + 0.000004325285938225562 i | `v7_0p7nm_si_p6_direct_candidate_d.dat` |

上述均在父`input/task39extra_para_workstation_capacity/`下，base SHA固定。记录材料原始来源及插值身份；本表只是继承数值，不把材料数据误差当成已校准。发现来源矛盾先报告，不静默换材料。新model_id、input SHA、physical SHA、mesh SHA、operator/mode SHA分别计算，不能硬填旧值。

## 3. 求解方法：p6单元凝聚直接法，不是双层p4修正

先在每个单元消去内部自由度，再对全局共享边/面trace和端口未知量做一次准确LU；由保留解恢复完整p6场。示意如下，实际端口符号沿生产实现：

```math
\begin{bmatrix}A_{ii}&A_{ir}\\A_{ri}&A_{rr}\end{bmatrix}
\begin{bmatrix}u_i\\u_r\end{bmatrix}=
\begin{bmatrix}b_i\\b_r\end{bmatrix},\qquad
S_6=A_{rr}-A_{ri}A_{ii}^{-1}A_{ir},\quad
\widehat b_r=b_r-A_{ri}A_{ii}^{-1}b_i.
```

r包含合法的trace与端口；左右端口块不能假设互为共轭转置。内部使用局部LU/回代，不存显式逆；先合成物理curl与复质量矩阵再凝聚，不能分别凝聚后相加。

```text
method.kind = full3d_direct
solver.linear_solver = direct
p6 cell condensation -> one materialized S6+ports -> MUMPS LU -> recovery
```

`preonly+lu+mumps`或现有等价直接API均可，但必须确认实际分解的是p6凝聚系统。不要被旧profile名里的`dual_condensed_balh`误导；新manifest应清楚写`no_p4_factor/no_H6/no_outer_Krylov`。[C1][E1]

保留已测方向变换、fast/native见证、blocked Gram、正确MPC和端口积分。一般参数化必须覆盖新中心位置、50×50、phi90、任意有界轴数组与完整二维模式；旧专用profile维持历史行为。

生命周期：求解后取得凝聚真残差，保存必要解/恢复包，释放MUMPS/KSP及无用矩阵，再恢复/输出；若独立完整残差需要先恢复，先只完成必要场/残差，释放因子后再做重后处理。以实际依赖顺序为准，不释放仍被引用对象。每场正常只建一个全局因子，最多两次同因子残差校正；不以重新分解抽签代替正确性。

## 4. 两种误差必须分开：网格与DtN截断

### 4.1 模式索引与参考集合

```math
\alpha_m=k_x+2\pi m/L_x,\qquad \gamma_n=k_y+2\pi n/L_y,\qquad
\beta_{s,mn}=\sqrt{(k_0n_s)^2-\alpha_m^2-\gamma_n^2}.
```

采用原向外/衰减分支、Rayleigh判据和有损下端口功率定义。改变方位不交换索引定义：m始终沿x，n始终沿y。新phi90下传播区域沿负n偏移，绝不是把旧143个m直接换个标题。metadata很便宜，先枚举真实完整物理keys再装FE端口。

按上述材料与父判据的独立算术，自动传播metadata约为13.5 nm 168、5 nm 1232、0.7 nm 64120通道（含上下及两偏振）；这是**推导校核值，不是本程序新实测，不作为硬凑数量的Gate**。现场以固定公式和实际源枚举为准，差异须解释。旧80/600/32060/572不得作为新数量authority。

13.5/5 nm的方向网格研究使用足够大的、冻结的矩形参考集合R：覆盖全部自动传播级次，并在自动横向包络外每轴多一格，**包含矩形内倏逝模式**。对当前数值预计R13为m=-4…4、n=-8…8（最多612通道），R5为m=-11…11、n=-20…20（最多3772通道）。mode实际分类与极化决定最终列表；不能将它们与纯传播计数混用。该有限R仍须用再扩一格的同网格对照检验尾部，不称无限精确DtN。[E2][E3]

这样5 nm的BOX2/4/8都是R5的真子集，避免“参考只含传播波，候选又加了倏逝波”造成非嵌套比较。若扩一格仍影响结果，只追加有依据的一格并更新比较身份；不把旧R的网格误差结论偷移给新R，至少复核最终选定网格和最敏感方向。

### 4.2 用户的三阶候选

```math
\mathcal B_2=\{(m,n):m,n\in\{-2,-1,0,1,2\}\}.
```

BOX2包括25对级次、上下端口和两偏振，通常100通道；保留原beta的传播/倏逝属性，不把倏逝模式也计入远场R/T。这是硬级次选择，不是现有auto模式下的`max(user,auto)`扩大规则。实现新的显式模式策略或显式key列表，不改旧参数含义；输出窗口与求解窗口分开。

先R5后BOX2，同网格/积分/材料/源码；至少再测BOX4（-4…4，81对、通常324通道），BOX8只在BOX2/4不能满足比较时执行。不能只输出25级，却在算子中仍装全R后宣称完成截断试验。

同一比较族始终使用由最大的比较清单决定且经过检查的表面积分规则；新波长按实际模式重算，不机械继承q160。体积分metadata保持不变。若为节省工作想降低表面积分，另做积分对照，不与模式/网格变化同场归因。

## 5. D13：13.5 nm的x/y/z独立网格研究

### 5.1 初始网格与单变量对照

用户的p6h10作为起点，不预判足够。精确包含材料面：x断点0/16.5/33.5/50，y断点0/15/35/50，z断点-10/0/120/130 nm。各材料区间按目标h向上取整。h10的实际轴预计为[6,6,14]、504 cells，而非简单50/10相乘。

| case | x/y/z轴构造 | 预计cells | 比较目的 |
|---|---|---:|---|
| D13-B | h10拟合后的原始三轴 | 504 | 起始完整参考端口解 |
| D13-X | 仅将B每个x区间二分 | 1008 | x敏感性 |
| D13-Y | 仅将B每个y区间二分 | 1008 | y敏感性，入射快相位方向 |
| D13-Z | 仅将B每个z区间二分 | 1008 | z传播/材料界面敏感性 |
| D13-J | 三轴二分的联合对照，或经记录的敏感轴组合 | 三轴全二分为4032 | 排除单轴结论掩盖组合影响 |

必须二分已有实际坐标，不重新按一个标量h生成全网格，否则“只改x”可能同时改变y/z材料区间。固定其他两轴数组SHA、模式SHA、积分及采样点；局部张量缓存按真实metric/orientation处理。

### 5.2 有界自适应推进，不扫描所有组合

先按B/X/Y/Z取得指标；若均满足第8节标准，做J并比较B/J，得到h10候选的工程精度证据。任一方向失败，优先改动该方向；最多再做两级二分并在最终组合上复核剩余方向。不得只有R稳定就跳过T、复场或显著模式。

如J比单轴结果暴露新影响，使用J为新中心，只补必要方向邻点。某一旧case已具有完全相同输入与数值身份时复用其结果，不重复求解。D13最多12场完整PDE（含参考端口尾部对照）；通常先5场即可得到初步结论，不必须用满。预算内连续推进；若仍不收敛，提交真实方向误差与缺口，不默认开始短波最大模型。

## 6. D5/M5：5 nm先定网格，再判断三阶截断

### 6.1 方向研究

保持p6、同一新几何和phi90。默认从hx/hy/hz目标各4 nm开始；按材料面拟合预计[15,13,36]=7020 cells。13.5 nm若显示某方向需更严格相位尺度，可在D5启动前按其结果选择更细初轴，记录推导，不把13.5 nm通过当5 nm通过。

按D13相同办法做B/X/Y/Z（每次仅二分一轴，默认各14040 cells），再选敏感轴组合。不要无依据强制全三轴二分：默认全二分为56160 cells，p6直接因子成本可能很大。联合核验应依据敏感性安排；若三轴都不敏感，追加最敏感方向一级或资源合适的联合邻点，说明得到的是有界工程收敛证据，而非严格误差上界。

最终选定网格至少有各方向单独加密的对照；必要时围绕新中心补邻点，不用不同网格同时改模式。D5最多12场完整网格/参考尾部PDE；不按“13.5 nm h10足够”跳过。无用户固定RSS cap不等于主机内存无限，真实可用量仍须检查。

### 6.2 模式截断对照

在已选定D5网格上冻结源码、积分、材料、入射、采样与direct参数，复用该网格已有R5参考解。正常新增BOX2和BOX4两场，条件BOX8一场；全是完整求解，不是16步pilot。

每场输出**活动集合的原A6残差**及**参考R5算子作用于该场的残差**。若入射RHS也有差异，必须实测并在缺陷公式中计入，不能假设相同：

```math
r_R=b_R-A_Ru_B
=r_B+(b_R-b_B)-(A_R-A_B)u_B.
```

参考残差可以用R5已有耦合数据分批作用，无需第二份参考因子；不同mode集合的矩阵/因子不能假称是同一个数值对象。参考场中被省略模式的功率和复投影、候选场的省略边界作用都要记录。尾功率小、候选能量闭合或小KSP残差，单独都不是截断充分证据。

按第8节输出/场比较决定最低可接受K。BOX2失败就明确“当前精度下前三阶不足”，不能因为用户估计足够而放宽Gate。BOX4/8仍失败则保留R5，不继续盲扫。若输出误差过门但rho_R未到1e-6，分别标`OUTPUT_CONVERGED_TRUNCATION_APPROXIMATION`与`FULL_REFERENCE_OPERATOR_NOT_EQUIVALENT`；不能称完全相同离散解。对于0.7 nm，这种近似只能作为候选，仍需本波长验证。

## 7. DESIGN07/D07：按新物理与前两波长证据推进0.7 nm

### 7.1 准入不是“把h按波长缩放一次就算完”

D13/D5/M5须先回答：哪一轴最敏感、各量的变化趋势、接受的网格和参考端口、BOX2是否合格、材料/离散/边界哪些仍不确定。写`design_0p7nm.json`后，在本授权范围内继续，不为每一步等待新批准。

用纯轴planner和模式metadata列至少两种候选：

- **保守相位缩放**：从已选5 nm的各轴尺寸按0.7/5缩放，计算实际材料拟合cell/trace/mode与矩阵载荷，不分配全目标矩阵。
- **有证据的方向选择**：y按入射快相位与实际FE色散条件选择；x依新方柱侧壁/横向衍射敏感性；z依保留传播/倏逝波的beta、体内场与5 nm方向结果。记录每轴最大实/虚波数乘h、实际Jacobian、材料层厚与场变化；可参考同一p6真实单元的廉价传播校核，不启动新的方法研究。

不直接继承旧phi0的hx=.25、hy=12.5，不直接将x/y互换；当前y不再均匀且x/y物体宽度不同。单元数少于旧47,200也不能据此保证直接因子小于1.8 TB。保守planner和方向候选都是设计，不是精度证明。

0.7 nm初始模式候选至少包括5 nm接受集合和一个更宽集合的metadata对照。保持相同无量纲角向覆盖的索引范围约按5/0.7扩大，但这只是候选生成规则，不是必须保留量或强度证据；保持相同K也只能称激进候选。依据5 nm尾部及0.7 nm边界缺陷风险冻结初始K和扩展K，绝不默认K=2跨波长通用。不能用只沿x/y单方向的模式集代替二维级次。

### 7.2 正式完整场和有限验证

不恢复旧53万单元任务。本任务0.7 nm授权最多4场完整PDE：选定候选一场，同网格端口扩展一场，同端口最敏感方向网格加密一场，以及必要的第二敏感方向或联合校核一场。已自然完成且身份相同的结果可复用；不必用满4场。不安排仅16步pilot后宣称算完。

初场经过环境/轴/模式/稀疏结构预检，以单一p6凝聚直接MUMPS完成。后续对照一次只改一个对象；若模式扩展改变了原先网格需求，资格范围缩回、说明不足，不混成“h收敛”。参考边界可以分批矩阵自由作用，避免存第二份大因子。

完整二维自动传播/倏逝参考metadata必须保留；没有构建全参考作用时`A6_full_parent`为NOT_VERIFIED，不能从有限BOX残差冒称全DtN通过。0.7 nm两组BOX输出稳定只是截断收敛迹象，结合省略边界贡献/尾部验证评价；若只抽样，明确覆盖范围而非全模式证书。

任何候选因精度要求或真实容量无法继续，都保留已得到的场和限制：`DISCRETE_RESULT_ACCURACY_LIMITED`、`CONTROLLED_RESOURCE_STOP`或`TARGET_0P7NM_48H_NOT_ESTABLISHED`。不以更粗网格/更少模式偷偷换取目标通过；不自动换p4/p3迭代、BLR、DD、低精度或Hybrid。目标难以达到时给出实测占比与剩余缺口，不把直接法某场容量边界说成0.7 nm所有方法不可能。

## 8. 数值、物理、比较与输出Gate

### 8.1 单场求解与身份

| Gate | 要求 |
|---|---|
| 物理/离散身份 | 本任务新几何、phi90、对应材料、真实mesh/modes/integration/source逐项匹配 |
| 凝聚直接残差 | 默认目标<=1e-9；记录矩阵尺度、范数、MUMPS原状态和校正次数 |
| 恢复后完整A6 | 本场活动DtN算子上的独立原p6相对残差<=1e-6；保留全部合法自由度，不用凝聚残差替代 |
| 凝聚/恢复一致性 | 非零内部与端口RHS、方向/MPC、左右块及恢复满足既有局部/全局合同；不因切direct忽略已知核差 |
| 能量 | abs(1-R-T-A_volume)<=1e-5，abs(A_balance-A_volume)<=1e-5；两者关系相关，不当两个独立精度证据 |
| 有限与被动性 | E/H、modal幅值均finite；功率/吸收符号按原物理约定，负小量与容差原样记录 |
| 模式范围 | active/reference/all-propagating不同字段；未装配的mode不能填实测零 |
| direct实际性 | 记录p6矩阵维数/NNZ与一份MUMPS因子；无p4、H6、BAL_H、外层KSP搜索 |

不改变源方程来压小残差。遇到相消或native/fast差异，用已有独立作用/保存向量定位；此任务不要求先修旧p4故障，不把旧A4的1e-10作为不存在的内层停止门。必要最小实现bug可修复，受影响case最多一次登记重放；物理/网格差异不是bug，不能无限重放。

### 8.2 同物理方向与截断比较

| 比较量 | 本任务工程接受目标 | 注意 |
|---|---:|---|
| R/T/A_balance/A_volume绝对差 | <=1e-5 | 同边界参考平面、同面积和入射功率 |
| 同坐标复E/H及界面切向场相对L2 | <=1e-4 | 不拟合相位；网格间不能直接比系数向量 |
| 可得全域FE L2/scaled-curl差 | <=1e-4 | 公共积分/合法transfer；未实现写未测，不拿样本差冒充全域范数 |
| 有序共同模式复幅值整体相对差 | <=1e-4 | 同key/极化/法向/相位原点；近零值附绝对误差 |
| 每传播模式R/T功率绝对差 | <=1e-6 | 所有传播级，不能只验零级 |
| 省略传播功率和 | <=1e-5为辅助线 | 不能单独保证边界或近场正确 |
| 原参考DtN残差 | <=1e-6才可写参考算子等价通过 | 输出通过但此项不过时单列近似资格 |

这些是任务验收目标，不是由一个网格差证明连续误差的定理上界。每个方向至少有明确的同源单变量证据；若只两级且无渐近趋势，称工程敏感性/参考受限，不称严格h收敛。源修改影响数值后，旧比较不能伪装同源配对。

### 8.3 输出内容

每场保存完整复E/H（或E与可复现的H恢复）、curl、所有活动模态的复幅值/功率和完整metadata，R/T/A/A_volume，场/界面公共采样坐标及hash，必要残差/解向量。针对新几何，采样覆盖方柱内外和x/y侧壁，避开边角奇异点与不连续法向分量的混比；全域吸收仍按真实材料积分。

高频场的采样不得沿用旧40×20或24×24网格就宣称无混叠：增加沿快速传播方向的充分分辨率线采样、非等距见证或公共积分范数。正式衍射幅值由已资格化FE端口泛函得到，不用低分辨率可视化/探针DFT代替。

报告表格同时按m和n组织；显式给R00_s/R00_p/总量及T对应值、BOX2的25对级次、盒外尾部与最大差级次。未传播的倏逝幅值可以输出，远场R/T按既有有效模式功率定义，不能把复beta条件简化为Im(beta)=0而漏掉有损透射。

## 9. 内存、48小时与主机安全

### 9.1 本次用户资源覆盖

- **只有0.7 nm有用户固定上限：1,800,000,000,000 B的同期整树实测RSS。** 从mesh/JIT到factor、恢复、输出、checker全部纳入；不混GB/GiB。0.7 nm达到上限受控结束完整本任务进程树。
- **13.5 nm和5 nm不设用户固定RSS上限。** 新profile采用显式nullable/disabled语义，不沿用旧1.3/1.8/1.95 TB、8/12GB、5万cells等人工门；不得把0解释成零字节许可，也不得用Infinity写JSON。
- 全波长仍需低扰动资源监督、真实主机可用内存/NUMA/cgroup检查和系统余量；没有用户cap不等于允许把整机压到OOM。实测主机进入危险内存压力或持续丢失监督时按明确记录的安全机制收口，不称用户RSS触线。
- swap、pswp、预测字节数、估计时间只记录，不单独触发运行期kill。PSS/USS/smaps停采。实际发生swap则不能宣称zero-swap生产资格；不改swappiness/swapoff、不关闭热保护、不改邻项目OOM策略。
- 真实0.7 nm峰不一定与单元数线性；symbolic估计、数组载荷、MUMPS used/allocated、进程树RSS分别报告。资源预测不能冒充实测触线；同样不以不可信预测承诺可行。

每场启动前冻结系统余量方案和实际cgroup/node范围；whole machine约2 TB不是独占预算。一次一个heavy case，锁在worktree外；无锁配合时仍检查已存在进程和资源，不抢占/杀其他任务。0.7 nm保持跨node可用，不严格membind单node；保留CPU24/core/node与NUMA实际核验。

### 9.2 时间

48小时是**0.7 nm单场端到端目标**，不是整个研究任务截止或自动杀进程线：

```math
T_{\rm mesh+JIT+ports+assembly+factor+solve+recovery+output+checks}\le172800\ {\rm s}.
```

不给13.5/5 nm设置1800秒筛选，也不继承旧p6端口结束后24小时guard或pilot16停止。每个新任务完整场有自己的起点；cold构建、cache读取/核验、因子及输出都计入。环境安装和开发时间另列，warm-cache/复用结果不冒充cold首算。模型间串行排队时间独立；总研究成本与单场48小时分别报告。

若时间超目标但未触安全/数值停止，记录`TIME_TARGET_MISSED`，不得自动说已通过48小时，也不因旧任务超时结束本场。正式声明同时看精度、内存和完整时间。

## 10. 代码改动、缓存与测试约束

优先复用父实现，只新增本任务必要的显式profile/参数化：

| 模块/资产 | 要做的窄修改 |
|---|---|
| `src/runners/p6_condensed_direct.py`、`task038_full3d_direct.py` | 接入本任务通用phi90、波长、动态row/mode及full-solve合同；避免新建每case一个求解脚本 |
| `src/geometry/mesh_builder_3d.py` | 真正每轴独立坐标/分段与可追溯二分；旧R13/fixed-grid校验不删除 |
| `src/common/modes_3d.py`、`src/solvers/fullspace_dtn_action.py` | R与BOX显式可配置，完整metadata/父子清单、传播/倏逝与极化保留；旧N0默认不改变 |
| input schema/validation/resolved、native profile、launcher/checker | 新物理/矩阵/波长cap和清晰残差scope，全链一致，不靠一个外层override |
| assembly-time condensation/端口/输出核 | 保留方向、MPC、积分、复材料及恢复正确性；只修新物理暴露的可重现缺陷 |

不要复制全部53万单元FE端口store。新周期、角度、几何、网格和阶次身份已经不同；只复用软件、符号/参考张量及满足身份的JIT缓存。**同网格仅改变模式集合**时，可在证明单模式物理/FE映射/积分一致后只读复用原始泛函，重新生成ordered manifest和派生矩阵；数值因子不跨矩阵复用。记录实际缓存收益，不把未持久化对象称已保存。

最低测试：新geometry中心/tag/体积；phi90波矢与s极化；双Floquet/端点映射；BOX2完整25对及上下/偏振、reference包含候选；negative tests拒绝N0/旧mode hash/同名旧物理；单轴二分仅一轴SHA变化；direct不建立p4/H6；残差checker scope；0.7 cap与其他波长无用户cap；PSS关闭和后代清场。可用B13作为第一场真实端到端anchor，不先重跑一串旧PDE。定向pure/FE/compileall/文档检查逐项记录，全仓CI未跑不声称通过。

## 11. 证据、运行数和提交计划

正式入口始终：

```bash
python scripts/run_case.py input/task40para_phi90_mesh_modes_direct/<one-case>.dat
```

一个dat只表示一场明确计算；批次调度与比较由薄工具组织，不把多波长/多网格隐藏进单dat。case清单记录参数、父比较case、唯一变动、预期用途及结果。

正常顺序：N0隔离/身份 -> N1窄参数化/测试 -> D13 -> D5 -> M5 -> DESIGN07 -> D07 -> Z。阶段资格过门后连续执行，无需每个case再请用户批准。实现bug在原scope内修复并登记；科学对照不满足时按上述有限规则扩展。缺资源、矩阵奇异、全域参考不可得或耗尽有限研究范围时保留成果并收口，不无界扫描、不用改物理强行继续。

上限是防止无边界研究，不是必须完成数量：D13<=12、D5<=12（均含对应reference尾部），M5新增<=3、D07<=4；正常用最少足够对照。数值源码稳定后先提交再正式运行；若后续数值修复改变比较基础，重新核对受影响最小case，不把所有旧场全盘重跑。

推荐提交组：

1. 新task profile、geometry/incidence/mode/resource接线与定向测试；冻结case及source。
2. D13证据和方向结论；D5独立证据；每场完成可追加compact，不修改活跃运行工作树。
3. M5截断对照与DESIGN07；受控0.7 nm执行及适用检查。
4. `response_v1.md`、`outcomes/summary.md`、`test_summary.md`、case索引、选择性迁移清单及项目级progress/model registry（仅本分支）。

必备轻证据：`branch_provenance.json`、`physics_identity.json`、`case_plan.json`、`mesh_directional_13p5nm.csv`、`mesh_directional_5nm.csv`、`modal_truncation_5nm.csv`、`design_0p7nm.json`、各场compact及Gate JSON。原始大数组、矩阵、factor、场与资源日志留ignored。每场保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、mesh/mode/integration/ABI身份、run_summary.json、环境/线程/node、阶段时间和artifact hash。

Response首屏回答：新入射和方柱是否正确；实际是p6凝聚直接还是误走迭代；13.5 nm h10是否够、三方向哪个敏感；5 nm选定轴与误差；BOX2的真实影响及是否可采用；0.7 nm为什么选该网格/模式、获得什么精度边界、完整时间及1.8 TB是否通过；哪些not_run/failed/controlled_stop。保留旧问题、未测项和门槛，不伪造成功。默认不合并master，不再自动继续父V8或其他任务。

## 12. 来源与文档交付边界

下列父仓库路径均固定于base `922466da9d7faff408cbb47b7882d179320bdc44`；不是声称父任务科学结论自动适用于本任务。新任务只建分支/文档，未执行工作站预检或PDE。公式使用GitHub fenced math；本地检查表格列数、链接及围栏，提交后回读远端。无法取得GitHub实际渲染时明确记未验证，不能宣称在线视觉通过。

[P1]: https://github.com/Rookie1234567/MyFEniCS/blob/922466da9d7faff408cbb47b7882d179320bdc44/docs/task39extra_para_workstation_capacity/response_v8.md
[P2]: https://github.com/Rookie1234567/MyFEniCS/blob/922466da9d7faff408cbb47b7882d179320bdc44/docs/task39extra_para_workstation_capacity/response_dispersion_validation_20261015.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/922466da9d7faff408cbb47b7882d179320bdc44/src/runners/p6_condensed_direct.py
[E1]: https://petsc.org/release/manual/ksp/
[E2]: https://doc.comsol.com/6.3/doc/com.comsol.help.woptics/woptics_ug_optics.6.16.html
[E3]: https://doc.comsol.com/6.4/doc/com.comsol.help.models.roptics.diffraction_grating/diffraction_grating.html
