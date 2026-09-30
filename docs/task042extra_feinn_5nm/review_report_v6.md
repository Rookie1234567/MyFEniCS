# Review V6：关闭冻结特征续扫，先核验 M5 的 p3/p4 离散敏感性

## 0. 决定、身份与本批要消除的 blocker

**接受 Response V6 的固定特征最小残差及独立复验证据；该冻结空间的末层诊断到此关闭，NN 求解资格仍未通过。下一批只授权一次同几何、同网格的 p4 直接法参考和 p3/p4 对照，并交付一个相位表示方案；不开始新的 NN 训练。**

本批针对用户新提出的离散问题：已有 p3 参考准确满足其离散方程，但它对连续问题的精度尚未经 p/h 检查。继续投入新表示之前，先量化提高一次阶次会使参考场和可观测量改变多少。**这是准确性基准审计，不是用网格问题解释 NN 在同一 p3 方程上的失败，也不是重新研发直接法生产路线。**

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42extra_feinn_5nm
worktree                   = /home/fenics/Projects/NN-Lab-V2
review_date                = 2026-09-30
reviewed_HEAD              = fa83e9cb751ecd213e04ce79804cda4643fc3232
latest_commit              = docs(task42extra): bind V6 rendered view and complete resource costs
latest_commit_UTC          = 2026-09-30T10:27:04Z
original_base_SHA          = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review            = review_report_v5.md @ 3ab4a251c76208897729473add43f1e91c9d634a
latest_response_reviewed   = response_v6.md
V6_numerical_source        = a2f6ea85a24cb5e7c233d266aaab9911fc695dcc
next_batch                 = V7_M5_P3_P4_AUTHORITY_AUDIT
response_required          = response_v7.md
neural_solver_qualified    = false
master_merge               = NOT_APPROVED
```

最终目标不变：约 2 TB 整机物理内存内，0.7 nm、周期单胞内任意非可分三维 Maxwell 的准确、稳定、可复现计算。本批属于**有限元离散与参考准确性**，不是 0.7 nm、目标尺寸 5 nm 或 48h 生产资格。2 TB 扩大资源余量，不取消可扩展 Full3D iterative/matrix-free 主线；小型 direct 仅作 authority。

本次通过 GitHub 读取最新分支/目录、规则、task 相关条款、最新 response/summary/资源账、受限最小二乘与已有 p_check/exact_solve 代码，并核对前一 review 后的4个提交。未改动的 task/review blob 与既有全文及交接文件对应；目录未见新补充合同。没有 SSH 重跑、没有重新核验工作站 ignored 大数组；下文 measured 指已提交记录，推导计数标 derived，新运行均 not_run。

先读根/目录 AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、Review V1–V5、[Response V6](response_v6.md)、[summary](outcomes/summary.md)及本报告。**本报告明确覆盖旧 task E4 的“NN p3 候选先通过才可做 p4”前置条件，以及先前本批禁止 p4/新 Maxwell factor 的限制；仅限下述一次独立 p4 authority。** 不改写旧合同、旧 p4 not_run 或任何候选 qualified 字段。

## 1. V6 结果：线性子问题完成，物理解没有通过

依据：[三场对照](outcomes/records/residual_readout_comparison_v6.csv)、[详细诊断](outcomes/frozen_feature_residual_v6.md)、[summary](outcomes/summary.md)、[资源账](outcomes/records/resource_costs_v6.json)。表内误差无量纲，场误差均相对同 p3 的准确参考。

| measured 指标 | V4 联合拟合 | V5 最佳 G 场拟合 | V6 最佳 native 残差读出 | 原严格要求 |
|---|---:|---:|---:|---|
| G 场相对误差 | 0.01387169130 | 0.01159095764 | 0.56993211900 | 表示门限与物理门限分开 |
| 散射 E L2 相对误差 | 0.01325124766 | 0.01393540627 | 0.56989393322 | 1e-4 |
| 散射 scaled-curl / H 相对误差 | 0.01388700270 | 0.01152557206 | 0.56993308341 | 1e-4 |
| native / augmented 相对残差 | 1.608844720 | 1.977909150 | 0.570577990 | 各1e-6 |
| 独立体吸收能量闭合绝对差 | 0.001183989956 | 0.001316110186 | 0.211210189884 | 1e-5 |
| 最大逐级功率绝对差 | 0.000351344847 | 0.000626436219 | 0.038556906280 | 1e-6 |

V6 的195/195数值秩、经济QR/小R SVD、最优性、真实网络回写及 q15/q30 配对支持 `FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED`。0.570578不是“小 residual”，只是该冻结空间的数值最小值；与1e-6相差约570578倍，而回写原方程差约2.31e-11。接受此空间不足的数值结论，但它不是区间算术证书，也不是整个可变隐藏层网络类的下界。

V5/V6分别把场距离和方程残差优化到各自最优；两者不一致不是逻辑矛盾。V6已核对 G 与物理范数：参考 L2/curl 能量24.2553173460/24.3260883093，在 G 中权重约2.46%/97.54%；相对V5的勾股配对缺陷约8.44e-15。不要据此立即扫描 G 权重、混合 loss 或截断来追求好看的某一项。

主阶段完整 launcher 48.924852s，数值树峰1,290,457,088B，自身采样swap0；这不是整条神经路线从零成本。新因子/optimizer均0；组件计时缺项保持 NOT_RETAINED，不为补账重跑。参考训练血缘未消失：V6读出仅使用f，但隐藏特征来自监督训练，旧标签及失败记录继续保留。

**结束范围：** 不再对这份固定 hidden/Phi/Q 换末层求解器、loss、ridge、rcond或更多读出。不续训 V4/V5/V6，不把 V6 残差下降叫神经求解进展。下一次神经试验必须改变隐藏表示或训练机制，并另有明确合同。

## 2. 为什么本批先做离散审计

把连续场、准确的当前离散场和 NN 的 FE 插值场区分开。固定其余物理/端口近似后，有如下纯代数分解：

```math
 E-E_{h,3}^{\mathrm{NN}}
 = (E-E_{h,3}^{\mathrm{FE}})
 + (E_{h,3}^{\mathrm{FE}}-E_{h,3}^{\mathrm{NN}}).
```

V1–V6主要测量第二项。提高一次阶次所测的是 p3/p4 两个准确离散解的差，帮助判断第一项的敏感性，**不能直接当连续误差的严格上界**。即使 p3/p4相近，也仍未排除 h 误差、端口截断误差或两个离散共同的误差。q15/q30是积分检查，不是p/h收敛。

已有同 p3 直接参考 residual约6.79e-12，说明同一离散方程可以求准。因此，无论本次 p 差异大小，都不得回写“V6失败只是网格粗”。反过来，也不应把 NN 先通过设为永久阻止验证参考准确性的条件。

这里改为独立 audit，是根据用户关于网格的新问题调整顺序；V6建议的相位表示仍值得设计，但没有证据证明它必定有效。先补一个可审计的离散比较，避免接下来把新的网络表示、参考标签变化和网格误差混在一起。

## 3. 冻结物理、数据与唯一改变量

| 对象 | 本批冻结定义 |
|---|---|
| 物理 | M5，真空5nm，Si/air，grazing1°/phi0/s/幅值1，原时间约定和layered背景 |
| 几何 | 盒[-5,5]×[-3.75,3.75]×[-1.25,8.75]nm，原Si基底/光栅/三维空气缺口；材料tags不变 |
| 网格 | 同一8×6×8六面体拓扑与坐标，384cells，h1.25nm；不细化h、不改变缺口 |
| 边界 | 原双Floquet、Fourier-DtN；完整40通道的key/极化/归一化/传播分类/顺序不变 |
| 唯一离散改量 | Nédélec第一类 p3 → p4；原积分degree15保留，不同时改材料/损耗/边界或端口库存 |
| 计算类型 | p3已保存准确解只读复用；p4一次原方程直接参考，不用NN初值、不训练网络 |
| 数值环境 | 原生Linux，PETSc complex128/int64，同ABI、MPI1、数学线程1；FE进程不导入Torch |

5nm Si沿用材料表：n=0.99396854453+0.00435380777i，epsilon=n*n，mu_r=1。不得重新猜填或更换数据来源。

从V1/V6 run index读取真实路径，现场核对文件字节hash：

```text
p3 native packet = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
p3 reference     = 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7
material table   = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
mesh coordinates = 78e294e0337292d2750f587ddf394aaa868bd726f8b1104d4eae6a68db039086
mode manifest    = 1e37bd91b3cabafe27741db2e0cb99fce7392c2521c84ff9e67f4cfd6a28c14e
```

原physical_model_sha256有“离散算子packet hash”的历史含义；p4的算子、master顺序、背景插值和rhs必然可能不同，不强制相等。保留两边各自的算子/输入hash，另以显式 `physics_equivalence_fields` 对照几何、材料、入射与边界；不静默重定义历史hash。

按当前拓扑推导，p4独立边/面/内部复自由度为4992/28800/41472，总75264；native含slave共78936，slave3672，增广行数预计75304。**全部为 derived，不是实测**；由现场元定义、拓扑/MPC逐项确认，不为凑数量删自由度。全cell 300×300 complex128张量的直展payload为552,960,000B，同样不是RSS或factor估算。容量准入必须另算。

## 4. U0：最小资格与p4容量预检

先确认本任务没有活跃作业、正确branch/HEAD/clean source、原artifact可读和现场资源窗口。旧数组缺失或损坏标 ARTIFACT_BLOCKED，不自动重新计算p3参考。已资格化的环境不重装，旧E0/E1/P0/NN训练不重跑。

选择性复用 `src/solvers/feinn_reference.py` 的 `p_check`、`exact_solve`、`field_physics` 及原网格/空间构建，但新增明确的 reference-audit入口。旧p_check要求合格候选，**不能把旧qualified数组伪造为True，不能放宽旧路线默认Gate，也不能覆盖旧e4_p4的not_run索引**。

p4/跨阶比较需要最小新资格：

- 原物理数据相同，分别验证p3/p4的元族、cell数、坐标/tag、MPC波矢与完整模式身份；p3重建自由度顺序必须等于旧packet，或有实际验证的唯一映射。
- 在小型同网格p3→p4嵌入测试中使用非零复系数/多分量，核对场及curl、orientation和周期约束。按单元公共积分点交叉评价，与基于兼容插值的嵌入配对，operation-scaled差≤1e-10。不能用不同长度的系数向量直接相减。
- 核查p4的原组装与native/端口action一致性；复用已有独立组装配对逻辑，非零复向量差≤1e-10。若新p4暴露局部维数硬编码，做最小明确修复并测试，不修改p3已冻结物理。

在p4大数组、转换或分解前先写rows/NNZ上界、各常驻/临时对象、local tensor、端口耦合、MPI复制和factor的容量账。沿用 `exact_solve` 的装配/符号分析分级Gate，12GiB为内部保守规划线，整树16GiB硬停止线不变。符号估计必须读取实际后端字段并记录含义；若估计不可得、时间余量不足或workspace+现有RSS不能安全容纳，不进numeric，标 P4_REFERENCE_RESOURCE_BLOCKED。

U0含小测试≤1200s；只做本次改变相关tests/Ruff/compileall。不是整套full pytest或新环境安装。

## 5. U1：一次独立p4参考，完整释放生命周期

通过共同身份/资源Gate后，唯一一次p4 formal solve，仍走one-run入口。使用原未凝聚增广Maxwell方程的独立装配和当前已验证MUMPS参考路径；保留全部内部、trace与完整端口。**本批只对该小型authority允许新增global Maxwell CSR/factor；明确 REFERENCE_ONLY，不是NN训练fallback或生产PC。** 不新增Gram矩阵/Gram factor，不把p4当旧p4粗逆。

先做symbolic容量检查，再numeric、solve、完整true residual。同一matrix/factor只求固定rhs；不启动参数扫描或备用求解路线。p3准确解、NN权重、Phi/Q均不能作p4求解的初值或额外约束。

p4自身资格：native、原augmented及独立total方程相对残差各≤1e-10，使用各自原rhs分母；全port恢复/约束缺陷≤1e-10，finite和slave存储合同通过。随后取得独立体吸收能量闭合及absorption一致性≤1e-5。残差通过不自动推出物理/离散通过。

生命周期必须是：solve→true residual→保存最小p4 c/port/恢复与provenance packet→销毁factor/KSP/无用矩阵→确认RSS下降→完整E/H与R/T/A/衍射后处理。若复用helper只能先释放再输出，则保持其原顺序；禁止为了跨p比较把factor与两套后处理对象一起长驻。数值停止优先安全，不为final audit越过资源硬线。

p4新的参考状态写明 `c_scattered`、`alpha_scattered`、`alpha_total` 的准确含义或唯一对应schema，避免旧p_check把total alpha存成含义不清的alpha。原p3 reference字节不改。p4计算采用新packet/hash，不将p3的31968维状态塞入p4空间。

本阶段从launcher起≤3600s，使用已修正单调时钟，提前150s停止新增长工作，保留至少120s安全收口。只准一次真实p4数值启动；失联先核对同一受监督作业，不重复启动。明确局部bug可修代码和定向测试，但正式重放须在response说明并等review，不自行第二次factor。

## 6. U2：p3/p4在同一物理空间比较

p4自身原方程不合格时，不把它当reference继续比较；保留已完成记录并停止受影响步骤。p4合格后冻结其c/port/source/hash，独立compare-only进程加载原p3和新p4，两边不再次factor/solve。允许重建必要网格/FE后处理对象，不重新生成全局参考矩阵。

准确p3 FE场在同几何的p4 Nédélec空间中嵌入，必须通过U0的场/curl配对；也可直接在公共积分点分别求值，避免引入投影误差。不能用网络的q15/q30检查替代跨阶资格。原p_check的候选过滤、最后仅汇总errors的逻辑不能替代新p4自身R/T/A/A_volume审核。

至少报告total和scattered的全场L2、scaled-curl、六点复E/H（沿用原六点及其实际cell/参考坐标），air/substrate/grating/interface-near各区域误差，完整四类40级复通道、逐级功率、R/T/A_balance/A_volume与R00_s/R00_p/R00_total。H_code沿原curl(E)/(i k0)约定，与SI量区别写清；不要在不同空间上误用cell中心表达式去评价另一个位置。

定义主比较为p3减p4，以p4对应场范数作分母，并同时保存绝对差、原p3/p4范数、实际分母和自然尺度近零处理。保留原量的单位，不拟合全局相位。完整通道按物理key/极化/side/参考平面对齐，不能按两个文件的行号盲比，也不由功率反推复振幅。端口库存未变不代表端口截断已经收敛。

公共后处理积分固定degree15；可对最终差值积分做一次degree30复核（不重新组装或求解PDE），归一化能量积分差≤1e-10。舍入导致的极小负能量只按有尺度的舍入检查处理，不能无条件abs或max隐藏显著负值。若复核不合格，标 COMPARISON_QUADRATURE_UNRESOLVED，不自行提升积分后重求p4。

本批预登记的是**一次阶次敏感性信号**，不是新增NN通过标准：

| Gate / 新比较量 | 限值或处理 |
|---|---|
| p4自身方程/资源资格 | U1全部原残差≤1e-10、恢复≤1e-10、能量/吸收≤1e-5及资源/provenance通过 |
| total/scattered全场L2、scaled-curl、六点复E/H及全部40级复向量的p差异 | 主要相对差各≤1e-3；完整原值/逐点值均报告，近零使用原自然尺度规则 |
| R/T/A_balance/A_volume的p差异 | 入射功率归一的绝对差各≤1e-4 |
| 每级功率p差异 | 最大绝对差≤1e-4；同时列显著与近零级 |
| 区域误差 | 全部单列，与1e-3对照；只在全局量通过、区域仍偏大时标 LOCAL_SENSITIVITY_REMAINS，不省略局部问题 |
| 嵌入与积分一致性 | U0/U2配对分别≤1e-10；不能把插值/比较误差当p误差 |

以上1e-3/1e-4是本次离散对照阈值，不放宽旧NN同离散1e-4、原方程1e-6或功率1e-5门限。即使全部小，也只能记 `P3_P4_SMALL_CHANGE_LIMITED`，明确 `continuum_convergence_claim=false`、`mesh_accuracy_qualified=false`、`port_truncation_qualified=false`；表示尚无充分证据授予最终连续精度资格，不是否定这次差异测量。

若显著变化，记 `P3_P4_SENSITIVITY_OBSERVED`，说明哪些场、区域、级次未过，p3只是旧同离散基准，下一轮需要进一步离散设计。若p4或比较不合格，分别记 REFERENCE_FAILED/COMPARISON_UNRESOLVED/RESOURCE_BLOCKED，不声称p3物理错误。**一次p3/p4相近不能证明p/h收敛，一次不相近也不能推翻旧NN对p3方程的失败结论。**

U2≤1200s，无新增求解。完成后不自动再跑p5、h细化、更多端口或目标尺寸；不将p4标签直接用于训练。

## 7. 相位表示：只形成下一轮候选设计，不执行

在 `outcomes/phase_representation_plan_v7.md` 提交一个具体、单一的后续候选：保持完整FE物理不变，在坐标网络点值进入Nédélec插值之前乘已知入射传播相位，让网络尝试表示剩余复包络。示意为：

```math
 E_\theta(x)=\exp\!\big(i\,k_{\rm inc}\cdot(x-x_c)\big)\,a_\theta(x),
 \qquad c(\theta)=\mathcal I_{h,p}^{\rm curl}E_\theta.
```

这只改变有限参数的场表示，不将任意三维结构假设为沿z可分离。相位不是凭标签拟合出来：k_inc、正负号、单位、参考点必须从原入射场实现核对；散射波可能含反射、衍射和倏逝成分，不能预设单载波包络一定慢变或一定有效。

设计首选同3→64→64→64→6、8966实参数/FP64的单载波对照，避免同时扩宽、改loss和改网格。不是沿用当前冻结hidden只扫末层，而是将来重新学习这一不同表示。完整Nédélec插值必须在积分点评价相位后进行，不能给边/面/内部系数随意乘一个中心点相位；Floquet仍只按原MPC约束展开，避免重复相位。

文档应说明：若p3/p4敏感，应如何选择未来基准；若差异小，怎样在同离散/同预算下比较原网络与相位网络；如何检查完整矩/VJP、参考暴露血缘、原残差及物理Gate；有哪些证据会否定这一个候选。**本批不实现训练器、不训练、不做phase参数或载波数量扫描、不引用这个示意式作收敛保证。** 后续由review决定，不因离散信号通过就自动启动。

## 8. 资源、Git与执行边界

本批全部新增有载及有界辅助≤7200s，同时受原16h剩余额度约束。V6最终保守累计45161.81665198447s，原剩12438.183348015533s；现场补计之后费用，不能用summary早期快照重置。旧失联3284s、重放、Gram/NN学习及参考成本全部保留。p3复用新solve实耗0；p4的装配/转换/symbolic/numeric/solve/恢复/输出全部新计费，不把它隐藏成神经方法成本为零。

工作站原生Linux、同一canonical worktree、独立FE环境/cache/锁、内部串行。CPU-only、MPI1、数学线程1，现场空闲物理核、避免邻任务SMT；数值树warn12/hard16GiB、自身swap0、无OOC，轻测试/浏览器≤2GiB。系统reserve=max(128GiB,effective_total的10%)，邻增长至少384GiB再加本任务预算；disk free≥50GiB、artifact总量≤20GiB。p4不是因为机器有2TB就自动准入。

复用已合格持久launcher＋watchdog＋worker链；不得移出监督、绕过权限/沙箱或修改其他项目。无cgroup委派则如实约0.5s同时整树RSS采样，tmux管理开销单列。新增直接参考在共享负载下须重新准入；邻任务将进入heavy且余量不可确定时只停止自身数值阶段，记录 RESOURCE_WINDOW_UNAVAILABLE，不抢资源、不无限等待/自动后台重启。

先确认无本任务活跃作业再fetch/fast-forward同分支。共享origin.fetch不映射本分支时用精确refspec/显式tracking ref，不改共享配置、不将无法解析的upstream当通过。先clean实现commit再run，运行source与后来文档HEAD分开；不新clone/分支，不reset/stash/amend/强推，不merge master或其他支线。

## 9. 最小实现、交付与停止

新入口明确 `DISCRETIZATION_AUTHORITY_AUDIT`，不修改现有NN defaults、不把新factor移植到训练路径。可新增小型跨阶audit模块，选择性复用现有p_check/exact_solve/后处理，runner只编排。旧p4入口和旧not_run证据不覆盖；本批无NN前向训练、POD、ILU、Krylov、VarPro、G重新加权或新矩阵-free重构。

建议顺序：C1预登记/跨阶测试/显式stage与容量Gate；C2一次p4参考及冻结；C3独立比较/checker/相位候选设计/Response V7。新的one-run文件在实现并资格化后使用：

```text
input/task042extra_feinn_5nm/v7_p_transfer_checks.dat
input/task042extra_feinn_5nm/v7_p4_reference.dat
input/task042extra_feinn_5nm/v7_p3_p4_compare.dat
```

按已有 `python scripts/launch_task42extra_durable.py <one-run.dat>` 包装逐个执行，包装选择FE activation并调用 `python scripts/run_case.py <one-run.dat>`；先扩展显式stage白名单，不运行旧v4/v5/v6输入冒充新任务。每阶段确认清场/输出hash后再下一阶段。

至少新增：`response_v7.md`、`outcomes/p3_p4_authority_v7.md`、`outcomes/phase_representation_plan_v7.md`，以及 `records/discretization_design_v7.json`、`p_transfer_checks_v7.json`、`p4_reference_v7.json`、`p3_p4_comparison_v7.csv`、`gate_decisions_v7.json`、`run_index_v7.json`、`resource_costs_v7.json`。新记录区分本批没有NN训练、direct-reference资格和未取得的连续/神经/生产资格；V1–V6的标签政策和数据血缘原样保留。p4输出当前只供accuracy audit，后续训练使用需新授权。

每个formal run保留input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json及ABI/MPI/资源/artifact hashes。独立checker从原数值字段重算结论，不能只相信status。矩阵、完整场和日志留ignored；summary追加V7保留历史，同步progress/模型总账/tests/changed_files。

只对新review及必要新文档做有界GitHub rendered-view检查，无法取得视觉证据如实blocked，不能把本地Markdown结构检查当视觉PASS。前置Gate通过后连续推进，不逐小步请示；失败完成仍可做的独立部分并收口。最终只推送 `HEAD:refs/heads/task42extra_feinn_5nm`，报告准确source/HEAD、现场身份、实际结果与一个下一最小建议，停止等待review；不自动开始NN训练、p5/h细化、目标尺寸5nm或0.7nm。
