# Review V11：修复端口功率坐标接线，完成p6周期参考逆的工程网格验证

## 0. 本轮决策与身份

**要消除的blocker：V10已在完整80-cell三维缺口问题上做到p6参考逆三步残差通过，但端口平面振幅被送入旧global-z功率接口，存在重复乘传播相位的明确接线疑点；同一输出链的能量失败使更有工程代表性的Gx560被搁置。与此同时，原尺寸代表单元的p6恢复只在已知解前向误差上小幅超限，dot的完整882行分块积分已扩展到上下表面。本轮不再扩散PC种类，先利用现有场关闭具体错误，再完成Gx560与条件Gx784的真实求解、同离散场对照和所有q因子的成本测量。**

本报告依据用户最新“综合主线与dot、推进0.7 nm/2 TB/48小时、不要因bug停住”的授权。新增一轮有边界的连续执行；不追认旧失败，不恢复已结束V10窗口。最终目标为50×25×140 nm、真空波长0.7 nm、完整三维Maxwell且保留任意非可分缺口能力；整机十进制2,000,000,000,000 B、无swap、从必要冷编译到输出及独立检查的完整流程≤172,800 s。目标尚未资格化，不等于数学上已被证明不可行。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task40extra_0p7nm_engineering
review_base_SHA         = eb6489e95463f22798f0d004fe9e74e78cbc3937
latest_main_response    = response_v10.md
readonly_dot_HEAD       = 15713d3e09b63f65511c7b7f61fa043fdb23dca5
review_file             = docs/task40extra_0p7nm_engineering/review_report_v11.md
response_required       = response_v11.md
campaign                = task40extra_v11_gauge_recovery_engineering
canonical_worktree      = /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
execution               = 既有笔记本local_wsl2_authorized；MPI1/数学线程1
roles                   = 执行者实现/测试/运行；主控审查/冻结源码/commit/push
workstation/dot/master  = 不写入、不运行、不合并
ordinary_default        = 不变；新行为显式opt-in
```

先读根与目录AGENTS、仓库工作原则、task、Review V10、Response V10、summary和本报告引用的紧凑证据。更深目录约束仍适用。主控收到本review后将执行窗口明确绑定V11；目录AGENTS中“当前V10”是历史导航，不成为拒绝本次授权的理由。不得新建聊天、subagent、环境或worktree；旧分支、历史失败与费用原样保留。有更新HEAD先读差异，不reset。

## 1. 本次审阅：有实质正结果，也有可定位缺口

下表均为远端已发布记录，非审阅端新FE测量。时钟、RSS、cgroup与factor库存分开，不把父子区间重复相加。

| 对象 | 实际结果 | 本轮判断 |
|---|---|---|
| B0 p6候选 | 80 cells，p6，4个y相位分支，532端口；3步；显式A6=1.6089774391665316e-8，释放后native=1.6089791915820923e-8；KSP=4.899454752 s | 原离散线性求解有强正信号，不等于物理输出通过 |
| B0参考逆 | 全部36,000内部自由度、通用/内部/端口/物理regular RHS；q残差最大7.493923678060789e-12；regular原方程最大1.465060265308628e-11 | 保留这些范围的完整参考逆资格；全部4q继续保留 |
| B0输出 | R=0.984273608092677，T=0.014174698896746551，A_balance=0.0015516930105763937，A_volume=0.00148587384621333；能量差6.581916436299018e-5>1e-5 | 诊断值，不是official；优先审查坐标接线，不先归罪PC或网格 |
| B0成本 | worker=1051.699122267 s，树RSS=3,713,953,792 B，task swap0；输出恢复33.431334133 s/1,193,611,264 B | 4.90 s只是KSP；不能说完整场只需5秒。原worker因pyvista缺失exit4，后来保存场输出恢复另记 |
| B0 p4控制 | 同p6 target；2048步，reason -3，A6=0.966131083707469；KSP=1519.454145885 s | 真实负结果；不是可用的速度分母，也不否定全部历史BAL_H |
| A p4上下单元 | 已知内部场恢复误差4.071005827429115e-13/3.318404914520256e-13 | 保留通过，无需重复装配 |
| A p6上下单元 | 恢复前向误差2.202932653970648e-11/2.42442721473547e-11，要求1e-11；原方程残差≤1e-10已通过 | 小幅但真实负结果；与q60积分是否正确、B0能量失败是三个问题 |
| A q60 | 冻结分母5118.679535729753；完整作用差9.063390130105725e-15；真实n=0等五类见证通过；代表面全32,060 B/D行已覆盖 | 不重做旧q30/q60全调查。该资格不自动覆盖全部原尺寸边界/任意输入 |
| dot最新 | 原尺寸18-cell，12选定模式、上下/x/y；160对168/176最大运算尺度差约4.484e-14；worker148.798 s/1,033,064,448 B；独立checker通过 | 接受完整882行selected组件结果；不是全32,060模式或PDE |
| dot压缩 | 24/24个84行证书失败，全部回退882行；最大实测差7.24e-13但保守证书未通过 | 不宣称84行压缩成功；本轮不继续压缩证书研究，不裁掉小内部项 |

主线运行source：p4为cd9716dd3cb950c72b70487e7aa537d3b7381581；p6为c439ed40768de4745131b43fc0312bb8be8d9d50；保存输出恢复为f9a64e025e0656f5863bcc5367602a74f1806520。最新收口HEAD不是这些运行的数值源码。dot最新发布HEAD亦非canonical运行source；其canonical仍为6dba8257053c6b2e474b7808b708a745f202733b，活动helper/worker/checker另绑SHA256。

**裁决：保留B0线性求解正结果；不接受“已经物理通过”或“已获得严格性能加速”。优先检验下面的坐标错误，修复后允许以新的保存场复核报告关闭能量门，而不重建同一组因子。**

## 2. S0：冻结旧证据，避免重复算与错误拼接

读取[物理比较](outcomes/records/review_v10_physical_comparison.json)、[p6逆](outcomes/records/review_v10_p6_inverse.json)、[边界](outcomes/records/review_v10_boundary.json)、成本及run index。按source/input/physics/数组hash确定实际B0解：compact同时列出15:08:55的pre/post包和17:02:11的恢复目录，不能只凭run_id相同认为它们属于同一attempt。核对恢复程序实际读入的原场、RHS、alpha、mode文件及载荷；有差异先建立显式来源关系，不能复制或改写原manifest来凑一致。

先利用现有`reference_audit_snapshot`、`factor_audit_before_destroy`和marker补出每q setup、rows/NNZ、factor INFOG及同时驻留范围。取不到就保留unknown，并在下一场必需运行前加入轻量计时；禁止为补表重建B0四因子。释放后的used=0不代表曾经的因子峰值为0。

本轮直接复用V10通过的W0、有限q60、p4上下体积和模式清单，不再从模式生成器或全raw导出开始。取得dot已发布源码/紧凑结果不必等Library全包传输；需要其原科学数组作跨源逐值比较时才核验原件，缺失不阻断本线保存场修复。全部引用必须区分本地新运行、dot发布记录和审阅推导。

## 3. S1：端口振幅坐标的定向修复——先做保存场，不启动PDE

### 3.1 已确认的接口不相容与待核实的因果量

当前源码路径：

1. `task40_v10_saved_output_recovery.py`与candidate使用`build_same_mesh_physical_action(..., dtn_phase_gauge=BOUNDARY_PLANE)`。
2. `recover_p0_outputs`取得`recover_auxiliary(solution)`后，直接传给`_port_power_metrics`和`_write_port_outputs`，没有消费bundle的gauge。
3. 旧`_mode_power_at_boundary`及writer仍将系数再乘`exp(i*kz*z_boundary)`，按global-z坐标解释。
4. 已有`dtn_boundary_phase_gauge.py`提供`outgoing_solver_amplitudes`、`boundary_mode_power_from_solver`及显式坐标转换，尚未贯穿上述输出链。

这意味着接口语义不一致是源码可见的；**其对本场全部能量缺口的贡献尚须读取全部532个保存模式实际重算，不能先写成已完成的数值修复。**

设global-z系数为$a_j^g$，端口平面系数为$\widehat a_j$，$s_j=\exp(i k_{z,j}z_j)$：

```math
\widehat a_j=s_j a_j^g,\qquad
\widehat a_j^{\mathrm{out}}=
\begin{cases}
\widehat a_j^{\mathrm{total}}-\widehat a_j^{\mathrm{inc}},&\mathrm{top},\\
\widehat a_j^{\mathrm{total}},&\mathrm{bottom}.
\end{cases}
```

物理边界场为$\widehat a_j^{\mathrm{out}}\mathbf e_j$，不应再次乘$s_j$。功率继续使用同一既有code-unit或SI约定，不能混用单位；其物理定义为：

```math
P_j=\frac12\operatorname{Re}\int_{\Gamma_j}
(\mathbf E_j\times\overline{\mathbf H_j})\cdot\mathbf n\,dS.
```

**审阅端仅作了一个派生数量级核对：**用B0材料、波长、1°掠角和bottom z=-0.5185185185 nm，零级$\beta_b\simeq0.07783212154+0.00447509185i$ nm^-1，重复相位的功率因子约0.9953699161。把已报总T临时视为零级主导，$T(1/f_{00}-1)\simeq6.5935332\times10^{-5}$，接近实测能量缺口$6.5819164\times10^{-5}$。**总T包含不同模式，故这个估算不能作为修正公式或official新T。**它只是优先检查该接线的定量依据。

### 3.2 最小实现及一次全模式复核

在共享数值输出模块加入显式gauge合同，默认legacy global-z行为保持；Task40 BOUNDARY_PLANE调用现有plane功率helper。不得只在一个离线checker内乘常数把总T补平。修复必须贯通在线输出、saved-only恢复、JSON/CSV/NPZ模态字段及后续匹配比较。

- 保存solver坐标、total/outgoing与物理端口平面振幅，并明确每个字段语义。旧名若表示global-z，不得悄悄塞入plane值。
- 可表示时可另给global系数；不能为了输出而强制把强倏逝模式除以极小/溢出的$s_j$。直接从plane计算物理功率；不可表示的可选global字段为null并说明，非零模式和有限plane值必须保留。
- top入射扣除只做一次；bottom有损传播/倏逝模式使用各自完整复k、e和原功率规则。不能只改bottom总T或只处理00模式；全部532项均检查。
- 原始FE系数、材料、RHS、A6作用、模式和参考平面都不改变。先以旧公式重现历史诊断值，再用新公式计算逐模式差、两侧总量和体吸收闭合。
- 在同一场上核对模态合成的E/H或物理Poynting通量与plane功率；用保存mode系数和独立叉乘求和复核，不能再调用被检查的旧power函数作为唯一oracle。FE边界通量含截断、离散和同一(m,n)极化交叉项，若与单模和不一致，先保留完整交叉项分析，不将它强行归零。
- 直接复用保存体吸收，必要时只做一次同场独立积分；最终及释放后原A6≤1e-6、能量与吸收绝对闭合≤1e-5不变。

定向测试至少覆盖global旧行为、lossless top、lossy bottom、不同kz/复振幅的多模式、top incident subtraction、plane/global可表示等价，以及不能强制global转换的倏逝输入。不要用拟合相位或总能量归一化通过测试。

新目录保存`gauge_power_recheck`与新checker。输出修复后若全部门通过，可记`SAVED_FIELD_PHYSICS_REVALIDATED`并发布有明确来源的正式物理量；原worker exit4、旧energy FAIL、旧包和旧时长不覆盖。新结果不是fresh PDE或新的冷流程性能成绩。

### 3.3 输出和依赖不得再次消耗整场重算

科学输出（复系数、模式、E/H采样、体吸收、原残差）与可选PyVista可视化分离；可选绘图包不存在不能销毁已完成解。原必需科学字段不能借此省略。目录父级创建、通道单侧266/双侧532的scope、序列化及完整身份在无factor的保存场测试中一次检查。在线worker仍有硬编码通道条件时，与saved recovery一起修复，不只修离线副本。

若gauge修复仍未满足能量门，先从同一保存场定位体吸收、模态输出和真实弱式的功率账，再按第5节用唯一小型直接参考判别。不得立即下调门槛或重新搜索PC；也不能简单以粗网格解释所有能量缺口。

## 4. S2：处理原尺寸p6局部恢复，保持它与小模型求解解耦

这是A链的forward恢复检查，不是p4 PC的每次A4精化，也不是B0物理能量门。当前`stream_boundary_correction`先以双精度生成$ f_i=V_{ii}x_i^0+V_{it}x_t+B_i\alpha$，再减回后二项，最后调用一次`lu_solve`；在有抵消/条件性时，制造RHS舍入与求解误差都可能出现在已知解前向差中。未有数据前不宣称必然是哪一项。

复用已保存top/bottom原始张量、因子或可重建的450局部因子、已知$x_i^0,x_t,\alpha$和完整B/D，不重建全局p4/p6因子。先分别记录：原始Vii残差、制造及减回RHS误差、解前向误差、局部缩放/条件估计。禁止用同一LU重构Vii充当独立检查。

有实际求解误差时，先尝试**同一局部因子的残差精化**：

```math
r_i^{(j)}=f_i-V_{it}x_t-B_i\alpha-V_{ii}^{\mathrm{raw}}x_i^{(j)},\qquad
V_{ii}\,\delta x_i^{(j)}=r_i^{(j)},\qquad
x_i^{(j+1)}=x_i^{(j)}+\delta x_i^{(j)}.
```

正常最多三次额外局部修正，记录逐次残差/前向差和成本；明显停滞就停止内部循环，不能无限精化。残差可使用经dtype实测的更宽累加或补偿累加作有限诊断；输入原始数据、最终field和生产算子仍为complex128。若证据支持尺度不良，可试一项局部行列平衡，正确反变换原方程、所有交叉块、RHS与恢复；不修改全局MUMPS排序/主元/BLR或材料。

若主因是制造RHS的舍入，分别保存“同一已保存舍入系统的求解误差”和“相对理想制造态的差”，不可用后者低于机器可达水平的要求宣布Maxwell失败。允许稳定重组该局部运算形成新候选，但旧RHS/旧forward负结果不改写。未经新证据不改变原1e-11 forward门和1e-10方程门；不通过则A仍受限，**不阻断已经在自身离散上通过恢复与物理检查的Gx560路线**。

同一局部求解helper合格后用于Bi·alpha、fi及Vit·xt等实际需要的局部解，保持Hhat内部修正及非零port RHS。不得假定Hhat仍为原对角H，不构造32060平方稠密矩阵，不裁掉微小Bi/Di。输出一份两单元的前后对照，不再扩成全域高精度求逆项目。

## 5. S3：完成可比较的p6物理解，不把失败p4控制变成总障碍

### 5.1 B0 p4控制只做有限接线审计

核对它是否实际执行了约定的BAL_H、目标p6/gauge、P/PH、p4完整A4检查与原H6谱窗；不能仅信profile名称。发现明确错误，允许最小修复后做一次短真实向量动作对照，必要时一场修复后的控制。没有错误就保留2048步负结果，**不原样再跑2048步、不扫restart/shift/ILU**。p4不收敛不作为阻断正确p6候选扩展的唯一原因。

### 5.2 新增一份小型同离散参考的条件授权

修正功率后B0若缺少可信匹配控制，或仍无法区分输出与离散算子问题，允许**一场B0 target自身的p6凝聚直接参考**，预期trace+port=16,992+532=17,524行，实际以组装身份核验。它不是填平缺口的reference PC问题。沿用MUMPS，通过真实矩阵结构/工作区与系统余量准入，顺序执行，不与任何q因子组并存；不安全就不运行。

使用相同几何/材料/模式、精确坐标和原积分；独立原A6检验≤1e-10。能量/体吸收≤1e-5；同离散FE场、curl、E/H、模态整体相对差≤1e-4，R/T/A/体吸收绝对差≤1e-5。近零模态同时报绝对差，不能重新选择显著模式避开失败。正确的独立原作用不能只复用被检查的periodic inverse返回残差。

参考通过可替代失败p4控制提供本B0的同离散资格；不得称作原p4控制通过。无匹配参考但物理和原A6都通过时，可按下节运行工程候选并保留authority limitation，不为缺一份参考永久停审。后续Gx已有真实p4物理解是更有用的对照。

## 6. S4：本轮主要数值交付——Gx560，条件Gx784

### 6.1 先到已存在准确场的工程网格

B0输出坐标已实际核实并修复，且其原A6/恢复/物理门通过后，直接执行原V10未完成的C：**Gx560，10×4×14=560 cells，p6，phi0，manual340，真实解析三维缺口**。使用已有Gx560准确p4保存场作同离散比较，参考identity与实际数据由run index核对，不将B0/phi5字段混入。参考缺口填回只发生在预条件器，不改target材料标签或RHS。

必须推广现有p6参考逆模块，而不是复制另一个巨大worker。将80/532/36,000等B0特定断言分成case合同与算法通用维数；Gx560全部内部自由度为252,000，Ny=4仍需全部四q。mode数、局部各q维数、两胞元transport、真实MPC和输入全部从实际对象核验。不得只把input改560而继续运行80-cell fixture。

保持所有分支及aliases，不使用“phi0只需q0”或未证实±q复用。所有q因子同时存活时测量RSS与factor库存；因子生成完成后直接用于同一场求解，不为保存一个setup结果销毁后再建。若创建时无用体积/转换临时对象可释放，按明确所有权做生命周期处理，不隐藏其构建成本。

完整执行run_case→user-service→独立watchdog→setup→FGMRES→原A6/恢复→正式E/H/全部模式/RTA/体吸收→释放后检查，不能停在candidate-selected。线上输出直接使用修复后的gauge-aware函数。适配只在小型无factor入口测试中核对，旧正确组件不全套重跑。

### 6.2 条件推进到Gx784并取得真实增长数据

Gx560通过且准入安全时，继续**Gx784，14×4×14=784 cells、同物理几何/phi0/manual340/p6**。这是已有精度工程证据的x网格，可对已有Gx784准确p4结果；全部内部352,800、四q保持。网格和波长不暗改，不缩小缺口来恢复三步。

Gx560与Gx784每场都记录：零初值、实际KSP步数/原残差、两种背景下目标/reference区别、每q rows/NNZ/ordering/backend/INFOG、输入矩阵与因子数据的唯一所有权、全部共存峰、局部缓存、端口/传递与Krylov库存、每次PC实际分支回代次数、完整时间。

本轮不承诺三步一定保持。若步数变多，只要真实安全和数值检查正常，就按FGMRES32/max2048及统一窗口继续，不以历史三步/126步/40分钟为停止线。若明显无法在窗口/物理预算内完成，保存受控状态；不能以部分步数宣布已完成性能比较。

### 6.3 物理与性能如何判定

- 最终及释放后原A6≤1e-6；原identity≤1e-10、port≤1e-8；所有finite检查保持。
- 对各自同网格p4参考，用共同物理坐标、同相位和背景比较总/散射E/H、直接curl及界面切向量；优先已有原同离散1e-4门。无完整FE参考时给出采样范围，不把采样冒充体积积分。
- 全340模式保留；沿历史冻结显著集合补比较复振幅，不拟合整体相位、不重挑最容易的模式。功率绝对差≤1e-5、能量/吸收闭合≤1e-5；场差过门不代表连续/截断已收敛。
- 旧Gx完整参考若来自不同ABI或时钟边界，数值比较可在物理/离散映射明确后使用；性能只按真实同scope报告，跨环境比值标历史参考。需要严格受控速度比时，允许一次Gx560现有准确p4路线的配对，不能重复挑最快；它排在候选成功后，且不挤占Gx784的必要资格工作。
- B0的4.90s不是完整性能基线；1051.70s原worker不含成功科学输出。分别报告冷/已有JIT缓存条件、代码生成、全部因子、纯KSP和完整workflow。

## 7. S5：消费dot的完整882分块成果，不重做84行压缩

本节可与主线工程求解顺序穿插，但同一机器仍一次一个heavy。dot只读，不向其分支写入或下达超出其owner许可的新运行。主线可按本review选择性复制已发布最小helper，记录原文件SHA和本地差异；外部脚本归档在records不意味着直接成为production模块。只迁移实际数值核心到src，复用现有runner/watchdog，禁止整分支merge。

优先把点块和mode块分开：保留原生882行、全部必要Basix变换/真实MPC/两切向分量，固定有界point chunk与mode batch。参考基函数只按实际几何/方向类型复用，不能按模式重复制表；全模式action可以逐批积累，不长期保留882×32,060×全部面阵列。

1. 用本线现有模式/材料和A代表面验证完整882路径；复用dot已通过的机制证据，只补本地ABI、坐标/phase和新增接线真正受影响部分。
2. 原尺寸50×25×140 nm、lambda0.7、AUTO32,060仍是固定库存；已有manifest逐行映射来自冻结原件，不重新生成不同清单。top/bottom相位、H归一化、x/y平移变换以公式说明，不以phase-fit替代。
3. 在一个固定小批次上记录制表、phase、收缩、MPC、回散布和内存，再据剩余窗口/动态准入决定一次全32,060的有界作用。可用原18-cell边界夹具或本线既定两代表面，但scope必须在启动前冻结，不能把两面结果叫全边界；完整18-cell亦不是精度网格。
4. 全库存执行时不存全模式巨型系数图谱；保存全有序模式输出、少量输入状态、稳定hash与足以独立重算的参考矩/规则。独立参考按唯一频率和类型复用，不做32,060遍高精度相同积分。未覆盖模式记未运行，不拿12选定mode冒称全库存通过。
5. 条件全库存不安全/过慢则仅停止该扩展，交付已闭合的原代表p6与实际成本，不阻断Gx560/Gx784。原样巨大degree160 FFCx编译、84行证书再扫描、归一化求积权重、删除微小内部项均不做。

这是端口算子和局部恢复的规模测试，不是全原尺寸体积PDE。原H可对角，Hhat包含内部修正；严禁为了测试物化32,060平方complex128阵列。

## 8. S6：把小模型成功转成能否推广的资源和精度决策

当前四q参考逆只是将规则背景分块，不消除全部稀疏fill；它不能预先保证所有任意三维结构与强/大缺口仍易求解。允许规则参考作为PC，但每个target必须保持实际完整三维材料，并由原A6判断。

```math
A_{\mathrm{target}}=A_{\mathrm{ref}}+\Delta A,\qquad
A_{\mathrm{target}}A_{\mathrm{ref}}^{-1}=I+\Delta A A_{\mathrm{ref}}^{-1}.
```

以上解释为什么小扰动可少步，不是全局范数界。此次观察的三步只属于B0。Gx560/784要同时给出迭代成本和reference构建成本，不能用dot两cell/p4或B0三步来预测原尺寸。

按同一生命周期绘制下列总账，不要求强行闭合历史unknown：

```math
M_{\mathrm{peak}}=\max_t\bigl(
M_{\mathrm{mesh/maps}}(t)+M_{\mathrm{local}}(t)
+\sum_q M_{\mathrm{factor},q}(t)+M_{\mathrm{ports}}(t)
+M_{\mathrm{vectors}}(t)+M_{\mathrm{scratch/JIT}}(t)\bigr).
```

公式是对象账的组织，不可把不同采样/后端统计简单相加称RSS。列每q实测fill与总因子同时存活、cold setup、所有部件回代次数及时间；来自已销毁factor的零值不能入预测。已存before-destroy原件能补出的，优先不新增运行。

原尺寸单次目标时间分成全部准备/所有q分解/target iterations/恢复/输出/独立检查。用至少B0与Gx560、若有Gx784的真实资料形成情景区间，明确小样本、ABI、材料/网格和q规模变化；不得只乘单元数或单q×4当实测。原尺寸272×4×14只是计数候选，x/y/z精度尚未获证，不授予它1%准确资格。

如果各q因子增长已经占主导，下轮唯一架构问题是有界子域或递归粗层如何替代仍然过大的q因子；若factor可容纳而迭代随真实缺口恶化，先分析跨q误差耦合，再考虑局部/多层纠错。**本轮不并行启动DD/AMG/NN/BLR/新MUMPS扫描。**目标48h包含setup，不能以“outer三步”宣布48h通过。

交付一份可供后续工作站任务读取的冻结选择性移交清单：哪些gauge/局部恢复/参考逆/边界模块已资格、所需ABI和索引宽度、真实输入、测试和否决项。可提供分级准入的实际现有命令或明确待实现项，但**本轮不SSH、不启动工作站、不创建原尺寸全局factor**。int32下的小模型通过不能掩盖未来CSR/NNZ/offset超范围。

## 9. 连续执行、预算和自修复：不再因一个接口错误结束整轮

本报告明确新增**统一86,400 s的V11研究窗口**。第一项执行准备前由既有campaign supervisor记录唯一T0、UTC/monotonic/boottime和boot ID、固定截止；实现、准备、测试、编译、计算、checker和收口都在本窗。旧V10 charge、截止与unknown保留，不把新窗伪装为旧窗余额；原目标172,800 s是未来单次完整计算指标，不与研究窗口混为一谈。

沿V10已实现的保守时间机制和单一写账者；不再建新的clock-only研究项目，不恢复旧3600 s归因子限额。数值阶段可按实际进度分配剩余窗口，末尾留600 s保存/清场；不得提交或重启时刷新T0。UTC/单调钟偏差按既有策略计费，不凭5 s差异本身停止数学过程；真正boot/进程身份不明按原保护处理。

### 9.1 正常运行范围

| 类别 | 正常许可 | 说明 |
|---|---|---|
| B0保存场功率修复、A局部、边界组件 | 必须实际执行可独立项 | 不增加全局factor；有明确根因可修复接续 |
| B0 target direct | 条件1场 | 同离散对照，安全准入；不与reference q组共存 |
| Gx560 p6候选 | 1场 | 本轮主交付，B0物理修复合格后直接进入 |
| Gx784 p6候选 | 条件1场 | Gx560通过且资源/窗口安全 |
| 同机准确p4性能配对 | 条件至多1场Gx560 | 仅候选成功且比较需要；不重放失败B0控制来凑基线 |
| B0 fresh回归 | 仅数值核心/RHS/算子实际改变时1场 | 仅输出修复时不重新求解；与小reference/已存见证合理复用 |

这不是按attempt机械封死bug修复：允许不同明确工程根因的最小修复、对应测试、主控冻结源码后定向重放；首次异常保存source、首次原因、成本和依赖图。相同根因连续两次修复仍失败，先换有判别力的局部检查，不能原样第三次重跑；可继续独立任务。数值或资源失败不能假称bug，不能改阈值、删模式、降阶或缩缺口使其通过。

checker/序列化/输出目录/可选绘图错误，优先只重读合格保存数据；不可因output失败再建立完整因子。目录冲突可用新attempt目录，不能删除旧目录、改旧hash、沿用旧source或重置预算。没有历史raw时先检查manifest路径和合法缓存；缺某个dot归档不阻断本线独立积分/已有场修复。

### 9.2 资源与环境不松动

实际计算只在既有canonical WSL环境，MPI1/数学线程1、complex128与实际IntType。每个shell按目录AGENTS显式activation和ABI检查；记录本次run原始环境，不用当前shell补写旧run。MUMPS后端、排序、主元、BLR/OOC、线程均不改。

任务树上限取**16 GiB与实际系统/cgroup准入中的较小者**；保留正系统余量和至少128 MiB证据/终止reserve。16 GiB不是许可用满整机。所有q、local缓存、checker和编译子进程都纳入快速RSS；PSS未采记null，任务swap=0。全机历史换出页与本任务分开；不能把他人活动归因给本任务，也不能声称Windows宿主/pagefile不可见时整机已零swap。

一次一个heavy。已有资源压力、失联、PID/start_ticks、原数值identity/NaN/Inf、完整清场保护保留。不得仅因超过历史3步/126步、7.33 GB、旧8 GiB、单个阶段旧耗时就人工停机；也不得关闭真实保护来完成样本。磁盘新raw每场≤8 GiB、全campaign≤16 GiB并至少保留2 GiB空闲；合法只读复用旧数组，不再大批复制进Git。

运行前做一组针对真实入口的轻量检查，覆盖gauge、通道scope、case动态维数、service身份、可选可视化与保存字段，不重跑全仓昂贵FE。所有正式PDE通过run_case+user-service+独立watchdog。执行者不commit/push，主控按既有流程及时审查冻结必要source；中间bug修复不要求等待新的ChatGPT review。运行中不热改源码。

## 10. 交付、提交和本轮成功定义

新增`response_v11.md`、`outcomes/review_v11_engineering.md`和一组紧凑证据，建议合并为以下少量文件，不再建立几十个互相遮蔽状态的收据：

```text
outcomes/records/review_v11_manifest.json
outcomes/records/review_v11_gauge_power.json
outcomes/records/review_v11_local_recovery.json
outcomes/records/review_v11_engineering_results.json
outcomes/records/review_v11_cost_and_repairs.json
```

结果报告以setup/KSP/恢复后处理三段列每场时间、实际调用、各q库存及同时树峰值；同时列：原残差、能量/吸收、同离散场和全部模式、精度范围、工作站未资格项。按measured/derived/diagnostic/predicted/not_run/failed/controlled_stop分开。旧run恢复的新official packet不是旧worker重新exit0，原saved目录不改写。

更新summary、run index、test summary、development_progress和model registry；维护正确的status和交付scope。所有tests绑定其source；数值改动后重跑最小相关项，缺失CI不写CI通过。Markdown独立公式用math围栏、表格列数一致，GitHub渲染无法查看时明示缺口。

建议提交顺序：C0保存旧身份与gauge证据；C1共享功率/输出最小修复与tests；C2局部恢复、case维数及因子计时接线；C3冻结Gx输入并运行；C4结果、移交与最终回应。物理输出修复合格后直接继续主交付，不停在“代码已修好”。

**本轮最小实质结果应是：B0已保存p6解的物理输出被独立确认或明确定位新问题；完成至少Gx560的真实p6参考逆尝试并给出完整成本/同离散比较，而非再次只报组件测试数。**资源或真实数值阻塞时交付已完成独立成果及精确阻塞，不伪造成功、不继续原样浪费计算。Gx784和全AUTO为条件扩展，不影响已合格主成果的收口。

## 11. 核心证据与复用入口

- [Response V10](response_v10.md)、[summary](outcomes/summary.md)、[B0物理比较](outcomes/records/review_v10_physical_comparison.json)、[p6逆](outcomes/records/review_v10_p6_inverse.json)、[A边界](outcomes/records/review_v10_boundary.json)。
- [共享场/功率恢复](../../src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py)：`recover_p0_outputs`。
- [旧功率与writer](../../src/solvers/dtn_port_3d.py)：`_mode_power_at_boundary`、`_port_power_metrics`、`_write_port_outputs`。
- [已有gauge helper](../../src/solvers/dtn_boundary_phase_gauge.py)：`boundary_mode_power_from_solver`、`outgoing_solver_amplitudes`、显式global转换。
- [B0保存场恢复](../../src/runners/task40_v10_saved_output_recovery.py)、[B0完整worker](../../src/runners/task40_v10_worker.py)、[p6周期参考逆](../../src/solvers/task40_v10_p6_yorbit.py)、[q MUMPS](../../src/solvers/task40_v10_p6_mumps.py)。
- [局部原尺寸恢复](../../src/solvers/task40_w1_local_probe.py)：`stream_boundary_correction`和已保存raw tensor。
- [既有Gx784工程对照](response_v6.md)、[四角/Gx560接口](response_v4.md)。
- [dot最新完整882结果](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/outcomes/paired_boundary_support_pilot_v1_zh.md)。主线只读该冻结版本及最小依赖，不授予dot新的运行窗口。
- LAPACK的残差精化/误差估计资料：[ZGERFSX](https://www.netlib.org/lapack/explore-html/da/d5b/group__gerfsx_ga1b66a646a937389f13bef476b7ceaa8a.html)。这里只借鉴原矩阵残差与前/后向误差区分，不要求更换ABI或采用混合精度。
- [PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)支持变化的右预条件作用；它不将PC近似误差变成物理解正确的证明。

本报告的gauge因果结论是源码审查加标量数量级推导，尚未重放本机532个科学数组；不将估算的新T或候选精化写为实测。本次ChatGPT仅新增审阅文件，不运行FE、不修改数值源码，不批准master合并或原尺寸工作站运行。
