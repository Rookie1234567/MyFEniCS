# Task39extra Review V6：冻结双模型成功基线，替换全局 p4 粗逆并准备工作站移交

## 0. 审阅身份、结论与授权

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task39extra
review_date             = 2026-09-09
reviewed_HEAD           = a894c4eee7c97837f5f020063233283fcc715bab
successful_run_sources  = 2bb6770ad00b35881558c576e7296e250656e571 / 094204b7281fe867744fe334e8753d2faebaf89b
previous_review_response= review_report_v5.md / response_v7.md
original_task_base      = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
review_verdict          = PASS_WITH_QUALIFICATIONS_FOR_TWO_DISCRETE_13P5NM_CASES
new_scope               = BOUNDED_PHYSICAL_COARSE_INVERSE_REPLACEMENT
execution               = G0 -> G1 -> G2 -> conditional G3 -> G4 -> G5
response_required       = response_v8.md
ordinary_default_change= NOT_AUTHORIZED
master_merge            = NOT_APPROVED
```

**本轮消除的 blocker：BAL_H 已能求解原始及非可分三维模型，但其粗修正 C 依赖一个随规模增长的全局 p4 LU。下一步只替换 C 的内部求解，在保留成功外层组织的条件下验证较低存储的物理近似逆。** 这不是重新找整套外层 PC，也不是再次诊断已经查清的同一误差。

最终目标仍为约 2 TB 整机内存内的 0.7 nm、complex128、Nedelec H(curl)、双 Floquet、Fourier-DtN、周期单胞内任意非可分三维 Maxwell 散射。本机先运行 13.5 nm；full-space、matrix-free 真实 fine 算子保持不变。

本轮用户已要求审阅及后续执行合同。授权同一 task39extra 内的有限 C 接口替换、两个精度档位的条件式验证和移交材料，不另建分支。覆盖 V5 中“本批不实施第四条内层路线”的停止限制；不修改旧 task/review/negative。G0–G5 连续推进，正常子项不合格按本文分流，不每完成小测试就停审。共同正确性或资源安全失效仍停止相关计算。工作站实际运行须另满足 §10 的迁移授权条件，不因写出移交包就自动发起 SSH 或短波 heavy。

## 1. 接受的成功与保留的限制

依据 [Response V7](response_v7.md)、[V5中心报告](outcomes/balanced_coupling_v5.md)、[compact](outcomes/records/balanced_coupling_v5.json)、[summary](outcomes/summary.md) 和成功版本源码。下表为已提交的 measured/derived 记录，不是本审阅重新运行的测量。

| 指标 / 单位 | 原始模型 | 非可分 notch | 裁决 |
|---|---:|---:|---|
| BAL_H 零初值外层步数 | 564 | 576 | 两个完整离散问题均通过 |
| 原 A6 相对残差 | 9.932289220e-7 | 9.351705517e-7 | 均满足 1e-6 |
| 相对参考场 L2 差 | 1.36698742e-8 | 1.39878303e-8 | 同离散参考，不是连续精度 |
| 80 复振幅相对差 | 4.23335991e-9 | 1.00161454e-8 | 无整体相位拟合 |
| R / T / A | 0.365625791 / 0.0129906323 / 0.621383577 | 0.337120585 / 0.0162886742 / 0.646590741 | 体吸收及匹配功率比较通过 |
| 保守 solve 时间 / s | 6102.614 | 6261.471 | 比较时保留相同计时口径 |
| 迭代进程树 RSS 峰 / B | 3466235904 | 3600924672 | 不等于 p4 因子独占内存 |
| 迭代 global swap 增量 | 0 | 0 | 不扩展为整个 campaign 的全系统 swap0 |

原始输出曾因 top=110 nm 不在结构顶面120 nm以上而失败；只从同一收敛 checkpoint 将外部输出探针改为127.5/-7.5 nm后恢复，A/b 未变，不重求场。这条恢复链可接受，旧 worker 失败保留。

notch 直接参考窗口内 global pswpout 增448页、归因未定；部分完整树采样从中途开始。参考数值/物理通过与资源证据限制分列，不写整个 campaign 全系统 zero-swap，也不将此升级为两次迭代数值失败。本轮不为洗掉该历史记录重做参考。

BAL_S/PROJ_K6 仅有有限作用结果，heavy 为 not_run_goal_met；不为凑齐路线补跑。接受的是单一13.5 nm、p6/h10、MPI1及两个材料分布的数值/物理资格，不是2GB、h鲁棒、波长鲁棒、0.7nm或 production default 资格。

## 2. 冻结哪些对象，允许改变哪个接口

| 对象 | 本轮要求 |
|---|---|
| fine A6 / b | 原13.5nm、1°、s、p6/h10、252六面体、164592独立/173802存储行、80 modes；负质量、复材料、双Floquet和完整DtN不变 |
| 原物理 SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| 原 mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| notch | 复用 V5 已解析的8个被修改 cell keys、材料实体和自己的 physical SHA；不重新筛选一个更容易的缺口 |
| 外层 | BAL_H 的粗—细反馈顺序、H6、P64/P64H、FGMRES32、zero start、完整 true residual 判断保持 |
| 允许变化 | C 内部由 p4 LU 改为有界的物理迭代；必要的误差记录、依赖拆分、level 参数化和显式新 profile |
| 参考用途 | 原始/notch准确解及旧误差包仅用于独立比较，不进入 PC，不拟合已知答案、不 warm-start 正式解 |
| 禁止替换 | 不改成单元静态凝聚生产路径，不回到旧逐段MR/JOINT，不重开PML/普通ILU扫描/FFT背景/Hybrid或准二维 |

新 profile 保持 opt-in，建议名为 `balanced_h6_recursive_p4_lo_v6` 与 `balanced_h6_recursive_p4_hi_v6`。dat、resolved_config、manifest 必须完整记录内部算法和上限；旧 `balanced_h6_p4_v5` 默认仍使用原 reference 策略，不静默改变它。

读根/docs及适用src AGENTS、工作原则、task和V5/V6；同目录无补充任务书时以已记录用户授权链为准。正式前绑定 clean source、ABI、网格/约束/模式/RHS身份；同一物理算子可跨源码提交，但必须有明确逐字段桥，不能仅用“SHA不同”否定等价。

## 3. 成功结构继续保留；近似 C 不再冒充精确投影

准确粗修正及成功的组合是：

```math
A_4=P_{64}^{H}A_6P_{64},\qquad C=P_{64}A_4^{-1}P_{64}^{H},
\qquad \mathcal B_6=C+(I-CA_6)H_6(I-A_6C).
```

本轮用算法 I4(g) 近似求 A4 c=g。一次完整 PC 仍按下面顺序，不对中间方向另做 MR：

```text
g1 = P64H(q)
c1 = I4(g1)                    # 零初值，返回解及原A4残差eps1
zc = P64(c1)
s  = H6(q - A6(zc))
g2 = P64H(A6(s))
c2 = I4(g2)                    # 同一内部profile，另一个右端项
z  = zc + s - P64(c2)
return z
```

内部 I4 可能非线性/随右端项变化，以上按函数调用定义，不把它当固定矩阵测谱。外层继续 FGMRES；真实 A6 action 始终准确，不把内部误差混成 fine 矩阵作用误差。

令两次内部残差为：

```math
\varepsilon_1=g_1-A_4c_1,\qquad
\varepsilon_2=g_2-A_4c_2.
```

在同一 Galerkin 定义下，可直接推导：

```math
P_{64}^{H}(q-A_6z)=\varepsilon_1-\varepsilon_2.
```

这是新近似逆的**误差记账恒等式**，不是要求右边为零。必须分别记录内部相对残差、eps1/eps2绝对范数、差向量范数及实际粗平衡缺陷。第二个 RHS 可以比第一个大，不能只看到两次相对残差都小就忽略绝对误差。

**旧 p4 reference 的1e-10门槛和精确投影1e-8检查保留在旧 profile；新 inexact profile 不套用它们作为“必须近零”的硬线。** `PhysicalBalancedCoupling.balance()` 当前的精确粗平衡拒绝逻辑需作显式策略区分，默认不变。新策略核对“实际缺陷减去eps1−eps2”是否在操作尺度1e-8内闭合，同时报告未消除的缺陷大小，不把它伪写成零。

尺度使用参与项范数之和，例如 P64H q、A4c1、P64H A6s、A4c2，零向量按明确规则处理。不得对两个舍入级小残差要求额外1e-10相对一致性。G1检查全部新样本；正式求解首个PC、每32次PC及退出前检查一次实际粗平衡恒等式，额外A6作用计时计数。其余调用保存两次已算出的内部残差摘要。

原A6非有限、映射/共轭错误或此记账恒等式显著不闭合，是正确性问题；“内部未达到目标，但有限且记账正确”是近似质量问题，不能混为同一异常。

## 4. 唯一首选内部机制：p4 内再用物理平衡层，而非旧 shifted V-cycle 原样重跑

### 4.1 物理 p2 层与有界底层

在同一网格构造相容 p4/p2 传递 P42，定义：

```math
A_2=P_{42}^{H}A_4P_{42},\qquad
C_{42}=P_{42}A_2^{-1}P_{42}^{H}.
```

A2保留真实复材料、负质量项、同一80模式和相应DtN归一化，不让下层auto inventory自行减小。优先复用native低阶物理action，必须按原fine积分metadata与composed action核对；不能通过降低积分阶次压缩构建成本。

本机第一版允许 p2 增广小矩阵的 MUMPS 底层，**总矩阵行数不超过8192（包含slave存储与端口）**，且预审的矩阵/转换/factor/工作集预算不超过512MiB。记录实际矩阵/因子NNZ、solver估计及阶段RSS，未知项不得写measured。依据原structured网格作计数可预计在此范围，但正式必须实数，不硬填预期值。

这是对原任务4096行底层限制的**仅本机physical p2 pilot例外**；旧p1限制不改。8192上限不随h、波长、MPI或机器内存增长。底层超限则停止该构建并标 `BOTTOM_SCALE_LIMIT`，不改用全局p4 LU、不自动增大上限。成功也只能称“取消了p4全局因子的分层原型”，不能称factorization-free或最终0.7nm已可扩展。

p2分级assembly/symbolic/numeric须在总进程树cap内；一次分解多右端项。原A2残差目标1e-10，最多两次同因子精化，沿用失败前保存策略；不调MUMPS排序/主元参数。无需另构p3/S6/p1完整栈。

### 4.2 p4 细层平滑与平衡预条件器

H4只是一遍p4正定curl-plus-mass的三阶Chebyshev/Jacobi平滑，复用现有通用实现，不是又做一个positive-only campaign。对角按p4真实约束计算；谱窗口用同一既有power10规则在p4上估计，种子与窗口保存，不能复制p6窗口。p6 H6本身保持逐配置不变。

定义用于内部 A4 方程的预条件过程：

```math
\mathcal B_4(g)=C_{42}g+(I-C_{42}A_4)H_4(g-A_4C_{42}g).
```

按和 BAL_H 相同的双侧反馈顺序实现：两次C42、一遍H4、两次A4；不用逐段MR。p4/p2空间相容是必要条件，不代表这个较低层一定有效。本轮正在检验这个递归假设，不能从p6/p4成功推导p4/p2必然成功。

复用 `physical_balanced_coupling.py` 的组合骨架，但把层级身份、计数和底层精度写清楚；不能让硬编码的p6路由/记录误称实际对象。原有p4/p2 action、owner transfer与参数化低阶装配可复用，避免将reference=True的旧builder意外带入p4全局装配。正式候选只能构造6/4/2三层及必要局部数据，不构造用不到的全部层。

### 4.3 真正求解的内部方程仍是 A4 c=g

I4使用right FGMRES，PC为B4，restart16、max64、零初值；每16步和退出前显式重算原A4残差。不得用B4或正定辅助残差替代。合法happy breakdown核对真残差；有限维饱和或达到64步仍未满足目标时返回有限近似及 `INNER_INEXACT_AT_CAP`，不能伪称内层通过，也不无界追加。

冻结两个精度档位，其他数学参数全部相同：

| profile | 原 A4 相对目标 | 工作量上限 | 用途 |
|---|---:|---|---|
| LO | 1e-4 | restart16/max64 | 首选，测试便宜近似是否足以保留外层平衡效果 |
| HI | 1e-6 | 同样restart16/max64 | 条件对照，只检验误差降低能否恢复外层，不扩大内层维数 |

这些容差是研究设计，不是从旧57–59倍响应推导的普适界，也没有假定内层必须比外层更准。旧p4 LU的1e-10 reference资格不改；新结果另标策略。内部未达目标但finite允许进入有限外层screen，不恢复以单次修正rho小于1为入场条件。

不恢复旧A2的shift0.5、p4→p2→p1辅助V-cycle。这里的变化是以真实p2物理层和粗细反馈预处理A4，不是仅把旧36步改成64步。不得进一步扫描shift、p3/p1底层、restart或平滑次数。

一个外层PC最坏可包含128次B4作用、256次底层求解（精化另计），远多于旧两次p4回代。**取消大因子可能节省内存却增加时间，所有内层工作必须摊入完整解成本。** 单次I4另设60s保守计算上限，越限返回已完成的安全近似及状态；共同外层/工作流watchdog仍优先。不能只报告outer564步而隐藏几十万底层调用。

## 5. G0–G1：有限组件对照，不重新建立已完成的诊断

G0先核对成功两模型的输入、参考、输出探针和hash。旧x_ref/真实误差/最佳投影/80模式输出均复用；不重跑fine direct、三份投影或旧外层。原始与notch材料算子各有身份，不因rows相同而共用同一factor。

一次合并的focused测试覆盖：新层级复内积与slave语义、P42伴随/Galerkin、零RHS、有限内层返回、eps1−eps2恒等式、reference/inexact策略隔离、拒绝前保存及cleanup。新物理作用比较沿用1e-10，记账闭合按§3。测试结束提交clean prototype，再执行原尺寸检查；不先交一个docs-only response等待下轮。

固定组件输入来自三个既有真实误差：q=A6e，各取g1=P64H q与按旧准确C/H6路径生成的反馈g2，共至多六个p4 RHS。已保存g/y直接按hash复用；缺少的g2允许用既有准确p4路径重建，不能猜作已存。最多一次原始p4 reference factor重建、至多六次逻辑参考求解，仅用于生成/核对这些输入；不是新fine参考，也不是正式新PC的fallback。保存后先销毁reference矩阵/factor并确认释放，再测候选内存。

每档至多这六个I4调用，加三份真实q上的完整新BAL_H作用；HI只在需要比较时运行，不重复旧baseline作用。记录原A4残差、对准确C的场作用差、完整场L2/scaled-curl误差、原A6残差比、平衡缺陷与全部调用成本。参考答案只在测量端读取，不用于内部初值、coarse basis、循环停止或拟合校正。

这里只定位替换的代价与精度，不要求新C对所有样本达到一个凭空设定的“10倍改善”。若数值合法，即使单次rho大于1也允许G2。若所有六个LO输入都在上限内不能接近其目标，仍可作一次有限G2 screen，但不能声称HI在相同64步内必能解决，也不能无限提高内部工作量。

整个准备、校准和focused测试的计算费用上限5400s。每项结果完成就落盘；一个比较缺参考时标 `REFERENCE_LIMITED_ON_THIS_RHS`，不因此重做全部历史。共同A/P/安全错误仍不准启动formal。

## 6. G2–G4：直接验证两个真实模型，条件精度对照不逐项停审

### G2：LO原始模型

只更换C，使用原BAL_H的H6和反馈顺序、原A6/b、right FGMRES32/max2048、zero start。每32步和退出前检查真残差；长周期用已验证BuildSolution保存，不强制重启，不加载参考解作初值。

沿用V5的首段投资规则：128步或保守solve1800s先到；真残差≤1e-2，或最近两个完整32步周期均下降且几何平均缩比≤0.65，可继续同一live KSP。未满足则 `SCREEN_BUDGET_NO_QUALIFIED_PROGRESS`，不是永不收敛。

为比较存储替换的成本，本轮每场solve上限明确为10800s、workflow14400s，仍最多2048步；包括screen而非另加。旧V5的7200s结果不改判。新版本即使通过但显著更慢，也必须标出 `MEMORY_TIME_TRADEOFF`，不以放宽预算伪称加速。

### G3：只有可分辨的精度问题才启动HI

LO原始未通过，或LO原始通过而notch失败时，若六个组件输入中至少四个确已达到LO目标、且至少一个停止残差仍高于HI目标，可检查HI六输入并允许一次HI原始模型。若HI并未取得更小实际内部残差，则不重跑完整HI，记 `NO_REALIZED_ACCURACY_CONTRAST`。

不得在LO内层长期达不到1e-4时，盲目把目标写成1e-6又做同一失败长跑。LO失败若来自模型/映射/资源问题，不靠HI绕过；若仅因内层代价过高，也不把更严格目标作为速度优化。

HI成功后立即运行同一HI配置的notch；LO已对两个模型通过则HI heavy为not_run_goal_met。若LO与HI都未建立有效低存储粗逆，结束这一内部实现，不自动加第三种C/PML/ILU/p5。保留V5成功，问题归于新C，而不是重新否定整个BAL_H。

### G4：首个通过原始的profile立即验证notch和完整输出

不先把所有原始候选跑完。notch使用已冻结8个cell keys，独立重建A4/A2/H4与自己的底层factor，其他算法参数与对应原始运行一致。每档至多一场notch；不为缺口单独调容差。若LO缺口失败且HI满足G3，可用HI重新验证两个模型，全部失败保留。

两模型的准确解和输出已经存在，**不再构建fine direct参考**。用既有127.5/-7.5nm外部输出探针及对应参考平面；初始化只检查合法性，不偷偷调整几何。收敛后保存完整解，释放内外KSP、p2 factor及无用矩阵，确认RSS下降，再恢复E/H、近场、80模式幅值/功率和体耗散。

| Gate | 本轮标准 |
|---|---|
| 目标方程 | 原A6完整相对残差≤1e-6，不降低要求 |
| 参考场 | 同模型L2、scaled-curl相对差≤1e-4；近零量另报绝对值，无相位拟合 |
| 功率/吸收 | R/T/A/A_volume对参考绝对差≤1e-5 |
| 独立守恒 | abs(R+T+A_volume−1)≤1e-5；abs(A−A_volume)≤1e-5 |
| 衍射 | 全80复振幅相对差≤1e-4、逐通道功率最大绝对差≤1e-6；不只输出n=0 |
| 不混淆 | 同离散求解资格不等于h/p精度、波长鲁棒或所有几何通过 |

数值通过而输出出现明确工程错误，允许只恢复同一保存解，不重新求场。失败场不得输出official。正常一条路线不合格自动分流；共同安全/正确性阻碍不可消除才提前收口。

## 7. 资源与存储：不把瓶颈从p4搬到另一张大矩阵

正式LO/HI求解中，p6和p4均不得装配全局AIJ或保存全局LU；唯一允许的显式物理底层为§4的有界p2。校准参考阶段的p4因子必须先释放，不在后台保留“应急准确解”，也不持久保存所有过去p4 RHS/解来暗中做全局低秩inverse。

完整峰值计入外层FGMRES的V/Z、p4内层的V/Z、两个层级工作向量、转移、几何材料、DtN、p2矩阵/转换/factor、编译器和后处理。至少提供每阶段对象账本及同时存活关系；不把两个不同阶段的峰值相加，不用各rank各自历史峰值相加冒充同期值。

以当前p4存储53084行为例，restart16的约33个complex128基向量载荷约28.0MB（derived，非RSS）；但每次A4/B4成本可很高。旧p4因子数值载荷下界约0.855GB也不是其完整可释放RSS。取消旧对象的事实、总RSS变化和时间代价必须同时报告。

本机安全线不变：effective_total取可见物理/cgroup较小值；reserve=max(4GiB,15% effective_total)；cap=min(12,000,000,000B,effective_available−reserve)，运行中继续守住余量。一次一个heavy、无swap/OOC、包含父进程/MPI/compiler全部后代。沿用已稳定运行的conservative_realtime，不另开时钟调查；UTC偏移保留但不单独当数学错误。

正式候选发生job VmSwap或系统swap增量时先安全暂停/停止并分类，不能声称严格zero-swap通过；仅全系统活动而未归因时保留 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`，不伪造数值失败，也不继续压力运行。本批不为了追溯448页来源修改系统或重复旧参考。工作站移交说明如何完整从启动前采样祖先和后代。

本轮2GB是优化指标，不是进入真实试验的硬门槛。若去掉p4大因子仍无总内存收益，报告新层级开销；若有存储收益但非常慢，报告交换关系。不能把“主矩阵没存”自动写成低内存成功。

## 8. 计算预算与失败分类

| 项目 | 有限授权 |
|---|---|
| G0/G1实现验证、setup、校准 | 计算费用合计≤5400s；至多一次p4参考构建，仅用于六个组件输入 |
| 新原始full solve | LO一次；条件HI一次；各solve10800s/workflow14400s |
| 新notch full solve | 每个实际通过原始且有资格的档位至多一次，总计最多两次 |
| fine direct / 旧准确BAL_H本机重跑 | 不授权；复用已有参考与曲线 |
| 本轮本机总计算费用 | ≤43200s；所有失败、测试、编译和恢复计入，各单项不是可叠加保证 |
| 工作站重型 | 本文只准备；实际执行按§10显式激活，不挪用本机余额 |

文档编辑/等待单列，不用从review提交开始的日历时间消耗尚未运行的计算预算。父/子时间不重复收费。总预算到限保存已有结果，尚未执行记not_run_by_budget，不宣称已否定方法。结构明确的bug修复只重跑受影响小测试，不能将数学失败定义为bug后重复抽签。

| 终态 | 含义 |
|---|---|
| `V5_BASELINE_PASS_WITH_QUALIFICATIONS` | 两个旧准确C结果保留，无需再次证明 |
| `COARSE_APPROXIMATION_UNQUALIFIED` | 新I4精度/有效性不足；不推翻准确C的成功 |
| `BOTTOM_SCALE_LIMIT` | 固定最底层容量界触发，不允许随问题放大 |
| `MEMORY_TIME_TRADEOFF` | 已取得真实解但时间/存储存在显著交换，分别量化 |
| `P4_GLOBAL_FACTOR_REMOVED_TWO_CASE_PASS` | 正式两模型不保存p4全局矩阵/因子，数值/物理/资源Gate通过；仍有有界p2底层 |
| `G5_COMPLETED_WITH_LIMITATIONS` | 计算条件收口和移交材料完成，明确未解决项 |

本轮不承诺相位/波长鲁棒，不将本机p2 factor的通过解释成短波可无限复制。下一阶段若底层规模增长，必须引入额外层或有界局部/分布式求解，并保持总对象和工作量有界；不是直接提高8192上限。

## 9. G5：一次性提交结果、内存账本和移交包

新增中心文件建议 `outcomes/coarse_inverse_replacement_v6.md`、`outcomes/records/coarse_inverse_replacement_v6.json`，更新summary、run_index、test_summary、两本项目总账及workstation_handoff。`response_v8.md`集中给出结论，不在组件通过后提前结束。

保留原/新C的接口定义、两模型真实曲线、内层残差分布/上限命中、eps1−eps2平衡、field/80通道误差、全部层级计数、同时RSS和时间。最慢输入和失败向量先保存后抛异常；普通成功调用只写标量/必要身份，避免逐次巨量输出。

正式保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary、环境/ABI、MPI/线程、模式、材料网格、资源与artifact hashes。参考与notch raw不覆盖；历史failed/authority_limited/全局swap限制不倒改。

提交顺序：通用有界I4与inexact记账及focused tests -> 显式profile/runner输出并提交clean源码 -> 有界正式结果 -> response与总账。ChatGPT只写review；Codex实现/测试/outcomes。完整仓库测试仅在确有影响且环境支持时最后一次，不能空称CI。角色与同分支规则不变，不merge master、不amend、不强推。

## 10. 工作站移交：现在准备，不以必须先达2GB为前提

G5无论新C成功或失败，都整理**已成功的V5准确C基线**和新C结果，形成两个清晰profile的移交包。新C失败不撤销已有13.5nm可迁移的数学基线。

立即准备源码/输入/参考/结果hash、只读原始及notch输出、最小环境清单和启动前检查命令；不复制LU因子、不发送凭据、不重装系统。所有模型/算子数据按owner存储设计，不能为未来MPI在每rank复制全局矩阵。当前未运行MPI>1就不得声称分布式已通过。

**本机任务书只授权移交准备。** 用户明确指定工作站执行位置并授权迁移后，Codex才能激活W0；没有该信息时交付准备包并完成response，不等待它阻断本机G0–G5，也不自行探索SSH主机。W0可复用同review的如下合同，不需因为逐项预检再次停审：

- 先核对实际物理RAM、NUMA、磁盘、cgroup、complex128/PetscInt与库路径。以MPI1/线程1复现原始和notch，每个模型一次；精确C基线与新C不得同时驻留。每case沿用V5的输入/精度/内存安全线和7200s solve、10800s workflow，不因机器有2TB而抬高小模型cap。
- 工作站实际复现以**V5准确C基线**为环境对照，不同时改变模型、粗逆与MPI数。新C是否也在工作站跑由本机结果和剩余授权明确列出；本段不自动再增加整组新C重型运行。
- 从进程启动前监控完整父/子、global swap-in/out及时间；正确性对照使用已存参考。环境差异导致错误先闭合，不用增加内存解释一切。

W0通过后，下一份review应尽早固定一个5nm的**真实三维非可分**压力案例及正式材料/外部channel inventory，分开求解器与网格精度。不要求先把本机压到2GB才允许推进；但不在本轮自动跑5nm/0.7nm，不用增长型p4/p2全局LU在工作站兜底最大模型。2TB容量要由多个实测点和准确性合格离散建立，当前单点不外推结论。

## 11. 依据与保证边界

- [V5 review](review_report_v5.md)、[双模型结果](outcomes/balanced_coupling_v5.md)、[真实误差诊断](outcomes/actual_error_diagnosis_v5.md)：本轮的物理/数值事实源。旧结果不重跑或改判。
- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：支持内部变化/非线性近似求解，且使用右预条件。该事实不保证任意粗糙I4都有良好收敛。
- [PETSc PCDEFLATION](https://petsc.org/release/manualpages/PC/PCDEFLATION/)：给出多层粗问题由预条件FGMRES递归处理的组织方式。本轮借鉴结构，不直接启用其默认底层LU，也不声称复现了它或获得Maxwell波长鲁棒定理。

本报告的两次内层残差平衡关系是显式代数推导；p4/p2、64步、两个容差与容量上限是冻结研究选择。编写本报告未执行新的项目PDE。新增递归层可能失败，但失败应回答“下层表示/内层响应是否不足、还是成本过大”，不把已经通过的BAL_H整体推倒重来。

**本轮交付应是一个真实可比较的粗逆替换结果，以及可直接移交的成功基线；不是又一份仅含‘下一步研究低内存C’的计划。**
