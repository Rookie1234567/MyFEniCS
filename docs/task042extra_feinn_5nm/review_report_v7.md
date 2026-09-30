# Review V7：自主排障恢复 p4，同时推进相位 FEINN 的完整对照

## 0. 决定、身份与授权变化

**接受 Response V7 的跨阶接口、受控停止及证据修正，不接受 p4/网格精度或 NN 求解通过。按用户本轮“多布置一些、遇到阻塞先尝试解决”的要求，下一批改为有界的完整执行包：A 恢复参考装配并比较 p3/p4；B 实现相位表示；C 完成从零原方程训练对照；D 在需要时进行隔离的表示诊断；E 独立验收和交付。A 与 B–D 的共同依赖是合格的原 p3 数据，而不是 A 必须成功。**

本批消除两个具体 blocker：参考装配的执行瓶颈，以及普通坐标表示对当前波场的求解能力不足。前者用等价装配和独立核验解决，后者用同参数规模的已知相位表示检验。不把故障排查无限前置于 NN，也不跳过安全/数值 Gate。

```text
repository                = Rookie1234567/MyFEniCS
branch                    = task42extra_feinn_5nm
worktree                  = /home/fenics/Projects/NN-Lab-V2
review_date               = 2026-09-30
reviewed_HEAD             = 64e945b386e4c2608450c78a7d9dec9328c691da
latest_commit             = docs(task42extra): bind V7 rendered view and final resource ledger
latest_commit_UTC          = 2026-09-30T13:47:36Z
original_base_SHA         = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review           = review_report_v6.md @ ecabef960cdf1ac194ef293ff83c65b14e8b7ba3
response_reviewed         = response_v7.md
V7_run_source             = 76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2
V7_fix_source             = c2bfd3ce2ae5d499b6d8afe6a0b3fc3cf743a2a9
next_batch                = V8_AUTHORITY_RECOVERY_AND_PHASE_FEINN
response_required         = response_v8.md
new_batch_budget_seconds  = 43200
master_merge              = NOT_APPROVED
```

最终目标仍是约 2 TB 整机内存内求解真空波长 0.7 nm、周期单胞内任意非可分三维 Maxwell 问题。当前全是 5 nm 小型 M5 的研究；direct 只作 authority，不能替代通用 Full3D iterative、分布式/matrix-free 架构。没有 0.7 nm、目标尺寸 5 nm 或 48h production 资格。

本报告明确覆盖以前“只启动一次、任何修复后必须再等 review”“本批不得训练相位网络”“必须 p4 成功后才可开始神经试验”等限制，并在第8节为新批单独增配时间；**旧记录不改，内存/线程/其他项目隔离不放宽，模型与合格阈值不降低。** 这是原 Task42extra 内的续研，不新建分支。

本次实际读了远程分支、目录、最新 response/summary/review、停止和资源记录、相位方案、reference/discretization/native 源码及最近4个提交。未改动 task/规则按其当前 blob 与已读全文核对；目录未见新补充任务书。没有 SSH 现场运行或复测 ignored 大数组；本文 measured 指仓库证据，推导和拟议实验分别标 derived/not_run。

## 1. V7 审阅结论：阻塞发生在哪里，哪些还不知道

依据：[Response V7](response_v7.md)、[summary](outcomes/summary.md)、[停止原记录](outcomes/records/p4_reference_v7.json)、[最终资源账](outcomes/records/resource_costs_v7.json)。

| 对象 / measured | 实际结果 | 审阅处理 |
|---|---|---|
| p4 拓扑/元/MPC | 384 hex；78936含slave、3672slave、75264独立复FE、40端口 | 接受所测身份；不是参考求解通过 |
| p3→p4 M5 场/curl/MPC | 约4.59e-16/4.87e-16/3.34e-16 | 接受同网格跨阶接口，不重跑整套 U0 |
| p4 native packet | 已保存；SHA256以062137c4开头 | 可以复用，不把未完成CSR误写成已保存 |
| 唯一 p4 launcher | 3452.535312 s；参考阶段树峰1289834496 B；swap0 | 预算受控停止，不是OOM或精度失败 |
| 最后完成的阶段标记 | reference_pre_assembly_capacity | 尚不能区分 form/JIT、MPC装配、CSR转换或后续未标记调用 |
| symbolic/numeric/solve | 无symbolic完成证据，numeric/solve为0 | 不声称MUMPS分解用了57分钟；p4残差/RTA均not_run |
| p3/p4对照 | 未运行 | 无法判断p敏感性，不能宣称p3已收敛或错误 |
| manifest修正 | 旧中断manifest含p3 provisional hash；实际p4输入由独立事件/依赖绑定 | 保留原字节与更正说明；新入口先绑定p4再启动worker |

V7按原合同及时停止是正确的；需要改进的是本次授权的执行计划，而不是倒过来责备 Codex 没有违反旧限时。`original_augmented_matrix` 把 `fem.form`、MPC装配、PETSc完成及CSR转换包在同一段，缺少细粒度完成标记。**当前不能下结论说“已确定是JIT”或“p4矩阵太大”。**

旧 V5/V6 的冻结隐藏空间已分别取得最佳 G 场误差约0.01159和最佳 native 残差约0.57058；这类末层续扫继续关闭。p3直接参考约6.79e-12说明原 p3 方程能求准；p4受阻不能用来解释 NN 同离散失败。

## 2. 一批做完的依赖图与自主修复规则

```text
共同准入/合格p3数据 ─┬─ A：装配定位→等价修复→p4 authority→p3/p4对照
                     └─ B：相位完整矩/VJP→C：原方程双路线→E：独立验收
                                                       └─ D：需要时双路线表示诊断
```

这里是逻辑独立，不是同时占用工作站；数值阶段仍串行。A失败不取消合格p3上的B/C/D，C数值失败不取消另一对照与D。阶段开始前检查本批剩余预算并为后续必需验收留余量，不让装配排障吞掉整批。

| 情况 | Codex本批获准的处理 | 禁止做法 |
|---|---|---|
| import、schema、hash接线、stage/环境选择、计时、checkpoint错误 | 定位根因→最小修复→定向测试→新attempt重试；继续独立工作 | 原样反复启动；改旧raw记录；先重装整个环境 |
| 长装配但无细分证据 | 加begin/end/heartbeat，短剖析；按第4节换等价装配 | 只把同一个1h timeout改大然后盲等 |
| p4因子预测超配额 | 改准确静态凝聚authority并核验恢复，或停止A继续B | 超16GiB试OOM；删除内部未知量的物理影响 |
| 一个NN候选预算内不收敛 | 保存完整数值负结果，执行另一候选/条件D | 把正常停滞叫bug以无限续训；降低门限 |
| 本任务进程中断 | 核对是否仍运行；匹配optimizer的持久边界可恢复，计数/费用继承 | 克隆第二个活跃作业；parameter-only冒充任意恢复点 |
| 缺必需artifact | 先查本任务index/保留副本/hash；必要时恢复可重建非解数据 | 全盘扫描其他项目；用近似数据顶替 |
| 宿主无安全资源、ABI不一致、无权限、换页或监督失效 | 停止受影响数值树；继续可做代码/文档；报告最小未解阻塞 | 绕过安全/权限、改邻任务、无限等待抢跑 |

每个不同根因允许至多3次有修复证据的重试，每次写 `failure→hypothesis→change→test→retry`。p4新增numeric尝试最多3次，只有改变了有依据的装配/准确凝聚/后端错误处理才可重试；成功一次后禁止再分解同一问题补日志。C/D每路线最多2次故障恢复；不得重置工作上限。用尽一项配额只关闭该项，不自动结束整批。

修复若改变loss、插值或数值语义，必须重新资格化受影响路线；不能从数学不一致的optimizer状态接着跑。小问题测试中必须涵盖非零实虚梯度、真实线搜索试探与异常恢复，不只做全零测试。

## 3. 冻结的物理与准确性身份

保持原 M5：5 nm、Si/air、盒[-5,5]×[-3.75,3.75]×[-1.25,8.75] nm，原非可分缺口，384 hex/h1.25nm，grazing1°/phi0/s，体和DtN积分degree15，双Floquet和40完整端口。材料、时间约定exp(-iωt)、背景与端口归一化不改。

**C/D一律以原p3作为固定代数研究基准**：31968独立复FE，完整边/面/内部矩。无论A得到小差异、大差异或仍未完成，都不静默将训练改成p4；p3连续精度分别标未资格化或敏感。A只在同网格增加一次p4比较，不自动p5、h加密或增加端口。

| 本地复用对象 | 文件SHA256；路径从原index读取 |
|---|---|
| p3 native | 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215 |
| p3参考 | 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7 |
| p3 Gram | 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9 |
| 原q15完整矩 | 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e |
| V7 p4 native | 062137c4c5be83b62be6a5373cfa24244f203f0b37244aeb4fb0b8feb75eb9ad |
| 材料表 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |

原始p3/p4 physical_model字段的历史含义保留；新manifest同时列 `physics_identity`、`discretization_identity`、`operator_packet_sha256`，先确定实际输入再启动。依赖索引缺失但原文件存在，可从本任务manifest恢复唯一索引并记录，不重新昂贵计算；解标签损坏/丢失不得猜补。

## 4. A：恢复 p4 authority，而不是再等一小时

### A0：定位实际瓶颈

把 `fem.form/JIT`、无约束/MPC稀疏装配、Mat.assemble、CSR提取与切片、端口拼接、PETSc转换、symbolic、numeric、solve、恢复分别记录开始/完成/单调时钟。检查自身进程栈、编译器子进程及少量cache元数据；已有记录不足可做累计≤10min的有界剖析，不复跑原57min流程只为补原因。进程采样不得替代阶段时间，没有证据仍写unknown。

当前DOLFINx的[form](https://docs.fenicsproject.org/dolfinx/v0.10.0/python/generated/dolfinx.fem.html)与[PETSc assembly](https://docs.fenicsproject.org/dolfinx/v0.10.0/python/generated/dolfinx.fem.petsc.html)为分开的操作；按已安装0.10栈操作，不为文档版本升级环境。

### A1：允许的等价修复顺序

先修正可确定的局部问题，如重复编译/失效缓存键、Python重复积分/逐项插入、矩阵格式转换、错误的大型临时对象。只调整本任务JIT/cache，不删除活跃共享cache，不改数学积分、fast-math或物理参数。

若MPC装配本身慢，允许先装原无约束体矩阵，再通过准确稀疏约束矩阵C计算C*KC。若原form/JIT仍为瓶颈，**允许由已存局部体张量和完整展开映射直接装配**：

```math
 V=\sum_K P_K^*F_KP_K,\qquad
 M=\begin{bmatrix}V&B\\-D&H\end{bmatrix},\qquad
 b=\begin{bmatrix}g\\g_p\end{bmatrix}.
```

P_K是原 `FullNativePacket.expand` 对应的局部映射，已含需要的方向/MPC作用；F_K、B、D、H来自原packet，不能重复乘相位。

采用有界cell批与预分配CSR/COO合并，不用逐列调用A来形成75264平方稠密矩阵。完整端口仍显式增广，避免消元产生稠密端口矩阵；任何压缩零项都须是结构零而非按幅值丢条目。

**独立性不能偷换。** packet装配与packet.apply相等，只是自洽，不构成独立authority。除至少3个非零复向量/伴随及非零port检查≤1e-10外，必须完成：小网格p4与独立DOLFINx/直接Basix积分逐元配对；M5上独立的UFL线性形式作用或独立积分核审核体项、材料、orientation/MPC；新p3装配对已保存p3准确场的残差审核，不重求p3。不把用于组装的同一张局部矩表换个函数名充当独立积分。

独立路径本身过慢时，可改为有限元线性形式/直接积分而非全局双线性矩阵，仍包含最终解全体自由度的原残差审核。共享材料/端口数据属于明确共同输入，记录独立范围；不足则 `REFERENCE_INDEPENDENCE_UNRESOLVED`，不能接受自洽解为新authority，但B–D仍可继续。

### A2：准确求解、可用恢复点与p比较

装配后立即原子保存CSR/分块、rhs、排序与hash，可分离后续factor阶段，不因客户端断开重装。numeric前记录symbolic因子/工作区估计，加现有RSS/转换余量须低于12GiB规划线；整树hard16GiB不变。若不合，可采用仓库既有准确assembly-time static condensation，p4内部41472个复自由度局部消去，凝聚trace预计33792、加40端口共33832行（derived，现场核验）。局部逆只用于authority准确消元，不转为NN预条件器；禁止shift、截断或近似内部恢复。

允许本任务小型authority在原MUMPS中作有依据的内存/ordering错误修复，不扫参数。凝聚也必须回到75264独立复FE和原增广方程验证。native/augmented/独立total残差各≤1e-10，恢复/MPC≤1e-10，体吸收能量/吸收一致性≤1e-5。solve→真残差→最小恢复packet→释放factor/KSP/无用矩阵并确认RSS下降→后处理。

复用V7合格跨阶映射，对p3/p4的total/scattered E/H/curl、六点复场、四类40级复通道、逐级功率、R/T/A/A_volume及原区域比较。主相对分母为p4对应范数、保留绝对差和近零自然尺度，不拟合相位。沿Review V6阈值：主要场/样本/通道≤1e-3、功率差≤1e-4；至多一次degree30差值积分复核≤1e-10，不重新求PDE。一次小差异仍不是h/端口/连续收敛证明。完整参考不合格时只对A做not_run/blocked分类，继续合格p3的神经试验。

## 5. B：相位网络的实现与完整资格

落实[已提交相位方案](outcomes/phase_representation_plan_v7.md)，不再只写计划。保留原3→64→64→64→6、tanh、8966实参数、float64、seed421001、隐藏随机/末层零；两个网络初始实参数逐位相同。相位是固定buffer，不新增可训练参数。

```math
 \rho(x)=\exp\{i k_{\rm inc}\cdot(x-x_c)\},\qquad
 E^{\rm scat}_\theta(x)=\rho(x)a_\theta(x),\qquad
 c(\theta)=\mathcal I^{\rm curl}_{h,3,\rm MPC}E^{\rm scat}_\theta.
```

k_inc=(1.2564456695248023,0,−0.02193134074032823) nm的倒数，xc=(0,0,3.75)nm；数值从实际cfg/入射实现核验后冻结。MLP输入仍归一化，rho必须用物理nm坐标。相位乘在边/面/内部积分点，早于Piola、orientation和完整矩，不能给FE系数乘中心相位。MPC只展开slave一次，不将包络强制设周期、不叠加第二次Floquet相位。

已知相位可能降低有限网络表达传播振荡的负担，但不是预先求解散射，也不保证反射/衍射/倏逝场的包络平滑；对无限维场的乘相位本身也不自动解决原算子的病态。本文是在[compatible FEINN](https://arxiv.org/html/2411.04591v2)插值链上的明确实验扩展，不套用其正质量项模型的收敛保证。

B必须包括k=0回归旧点值/矩；已知非零复多分量相位场的独立积分；边/面/内部矩、正反方向和MPC；至少一个明显非单位Floquet相位的合成检查；3个非零实参数方向中心差分；batch1/8的系数/loss/VJP/克隆更新。代数/同积分配对≤1e-10，VJP稳定区≤1e-5。不能因实际kxLx接近2圈而漏测相位符号。

网络插值求积q15→30→60只作预登记有界资格。原体/DtN离散q15不变；若q15网络矩不达1e-8而q30对q60达标，允许自动将**两条新路线共同**网络插值改为q30并重做相关配对，记录新map hash，不声称复用旧q15初值身份。最终用下一档规则复核，漂移需修复两条新路线的映射后重试，不能只抬高一条路线的标准或隐去失败费用。q60仍不可信则停止受影响NN阶段，A继续。

允许等价的固定坐标/相位缓存、≤8cell重算VJP与已资格批量优化；必须配对后同时用于新plain/phase对照，不改变旧结果。不得训练k、增加载波、扩大隐藏层、添加per-DoF embedding或材料分片网络。

## 6. C：从零完成原方程求解对照，不使用准确场训练

| 新路线 | 表示 / loss | 数据角色 |
|---|---|---|
| V8-PLAIN-DUAL | 原坐标网络；原Riesz对偶loss | PDE-only，准确参考只在冻结后审核 |
| V8-PHASE-DUAL | B的单载波网络；同一loss | 同上；与plain唯一数学改量是表示 |

先plain再phase、独立进程、数值串行；两条都从同seed/零散射开始，不加载V3–V6权重、Phi/Q、监督梯度或p4场。历史结果只作背景，不拿V4多段监督训练时间与新从零PDE路线比较。

```math
 r=Ac(\theta)-f,\qquad d_G=f^*G^{-1}f,\qquad
 L_D=\frac{r^*G^{-1}r}{2d_G},\qquad
 g_c=\frac{A^*G^{-1}r}{d_G}.
```

A/f/G及p3全FE/端口物理身份固定；沿用已资格的准确稀疏Gram辅助求解，Gsolve真实残差≤1e-11。每条从零成本单列fresh Gram factor/setup/solve，标 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`；旧装配复用归属与新增实耗分开。不形成global Maxwell factor作训练fallback，不显式形成A* A。

每条Adam500（lr1e-3、无weight decay）＋原L-BFGS（lr1、history20、strong-Wolfe、max_iter20/max_eval25、tolerance_grad1e-7、tolerance_change1e-9），上限4000完整loss+gradient closure及3h，从launcher计入所有setup/检查点，先到者结束。线搜索试探全部计数。允许工程修复，不允许看结果后单独改学习率/停止门限/Gram或增加训练时长。

保存zero、Adam500、每个完整外层step的模型/buffers/optimizer/RNG/计数/预算、final committed和独立last_trial，原子写入后才发布审核行。正常停滞不是bug；故障恢复只能从匹配完整状态继续且继承已耗时间/全部closure，不能重复使用已耗预算。每100closure在已落盘态做真实native/augmented/total/port审核；结束后无论成功失败都做独立物理验收。

C训练进程文件白名单不含任何reference_state或监督权重，不能复用会隐式读标签的 `load_problem/load_anchor`。标 `reference_used_for_training=false`、`features_reference_exposed=false`、`pde_only_solve=true`、`benchmark_previously_seen=true`、`production_initialization_allowed=false`。这是同一历史基准的无标签新求解，不叫全新盲测/泛化。冻结两条C候选之后，才由独立验证进程加载已知p3参考。

沿旧严格Gate：三类原残差≤1e-6，MPC/恢复≤1e-10，total/scattered场、curl/H、六点和完整复通道≤1e-4，R/T/A/A_volume、能量/吸收差≤1e-5，逐级功率差≤1e-6。全部通过可记 `PDE_ONLY_SAME_P3_DISCRETE_PASS`，不因此生产/merge/连续精度通过；未过的功率仍diagnostic。

科研比较另列：共同closure检查点、同总时间、全部A/A*/Gsolve/VJP及资源费用。phase只有在达到同资格更省成本，或在两个原残差与散射场都改善时，才记有限正信号；仅loss改善不算。建议将“同共同工作点残差至少10倍下降且散射L2/curl各≤0.1”记 `PHASE_RESEARCH_SIGNAL`，明确它仍远非物理PASS；不据这个信号自动扩大模型。

## 7. D/E：失败后继续有判别力的工作，而非立即结项

**D自动触发条件：C的phase未通过严格Gate，且共同插值/数据/资源合格。** 从新固定seed/零末层分别开始plain与phase的监督表示诊断，不用失败PDE或旧监督权重warm start；每条≤1h、≤1500完整closure，原Adam500＋同L-BFGS。两条使用同一原p3参考与同一个FitMetric：

```math
 e=c(\theta)-c_{\rm ref},\qquad
 J_{\rm fit}=\frac{e^*Ge}{2c_{\rm ref}^*Gc_{\rm ref}}.
```

这一目标不逐步调用A/A*、Gsolve或Gram factor，只使用G乘法和完整矩VJP；检查点/最后审核仍用原方程。D清楚标参考已暴露、PDE-only/official false，与C目录、index、模型路径隔离；D后不能回流C续训。p4标签仍禁用。

D不是保证在1h内证明表达极限，而是与同成本plain比较：两条均能拟合而C失败，指向残差优化；phase比plain明显改善，支持相位表示；两条都差仍为表示或拟合优化未决。三项G/L2/curl均≤1e-3为表示正见证，均≤1e-2为部分见证，未到不放宽；一次拟合失败不能证明数学不可表达。C本身已严格通过时跳过D，不为跑满预算增加无关试验。

E对每个真实冻结候选独立ML重建参数→完整矩、下一档求积核验，再用FE compare-only核对上述全部物理量和原区域。没有候选终态时审核真实留存状态并保留中断分类。引用p4只用于A的离散审计，不替换C/D评分基准。若A显示p3/p4敏感，继续保留C的有限代数资格并说明新精度基准尚待后续；不在本批改p/h重训。

E还须从过程记录输出“哪些阻塞已自行解决、哪些尝试被否定、哪些共同依赖确实不可用”的表。所有可独立完成的工作做完后才提交response；不得以一项样式/无用import/可定位schema错误宣告整批blocked。

## 8. 新批预算、资源与可恢复运行

用户本轮要求扩大执行包，本报告**新增12h（43200s）的V8有载与受监督辅助预算**；不再受旧16h剩余8592.723s约束。旧16h合同保留为V1–V7历史预算，不修改其结论。V7最终累计49007.27663535159s永久保留；新累计上限为该值＋43200s＝92207.27663535159s，另先补记V7已发生但未计入的尾段，不把历史成本清零。这里是研究停止预算，不是预计完成时间或0.7nm生产用时。

| 子包 | 分配上限 / s | 调度规则 |
|---|---:|---|
| A：定位/等价装配/参考/比较及其重试 | 7200 | 单次长阶段≤3600；可存盘分阶段。到该项上限后B继续 |
| B：相位和新增共享接口/恢复tests | 3600 | 优先最小定向测试，不full pytest |
| C：plain/phase原方程对照 | 21600 | 每路线10800及4000closure；工程重试费用不重置 |
| D：条件plain/phase监督诊断 | 7200 | 每路线3600及1500closure |
| E：最终验收、必要修复和交付辅助 | 3600 | 优先保留物理验算；不用于偷偷延长一条候选 |

未用时间可用于本批已有工作的一次有据工程修复，但不得突破C/D每路线可比上限、增加模型/种子/超参试验，或总计超43200s。A若需要更多工程时间，只可使用已确定跳过的D或E余量并预先写预算变更，仍需为最终验收保留至少1200s；不能先超支再补登记。

继续CPU-only、MPI1、数学/Torch线程1、DataLoader0，每阶段现场选空闲物理核且避开邻SMT；不擅自增加线程占用。数值整树warn12/hard16GiB，轻tests/浏览器≤2GiB，swap=0、无OOC；factor准入仍取12GiB内部规划。系统保留max(128GiB,effective_total的10%)、至少384GiB邻增长和自身预算。disk free≥50GiB，artifact默认≤20GiB；不删除旧负结果释放配额，不修改邻任务/系统库。

使用已有持久launcher＋watchdog＋worker，不裸worker脱离监督，不创建cron/无限抢跑。采用V7修正后的实际输入预绑定和native长调用watchdog截止；启动前short test验证而不重做整套V4故障测试。launcher起点包含import/setup；150s停止新增数值工作，至少120s安全收尾。紧急资源停止优先；不能承诺SIGKILL执行finally，保证已落盘边界可核查。

无委派cgroup时继续约0.5s采样并准确写口径，tmux外部管理开销单列。不将derived bytes当RSS、不把缓存命中当冷启动速度、不以shared-workstation wall差单独宣称算法加速。发生真正安全阻塞时停止自身，不暂停其他项目；可以交付代码与独立已完成项，不无限等待。

## 9. 实现、提交与 Response V8

先确认本任务无活跃run/锁，安全fetch/fast-forward同分支；共享origin.fetch未映射时用命令级精确refspec及显式tracking ref。不得reset/stash覆盖dirty文件、改共享origin配置、新clone/分支、amend/强推或merge master/其他支线。每次正式阶段前clean实现commit，运行source、修复source、文档HEAD分别记录。

复用 `feinn_native/reference/discretization_audit/optimization/reference_fit`、完整矩与持久checkpoint，新增明确opt-in phase表示和authority装配策略；solver核心在src、runner只编排，不复制每case一套大程序。FE进程不得顶层import Torch，不重装ABI/BLAS/CUDA；本任务独立环境/cache可做有证据的最小修复。

建议one-run输入如下；Codex先实现并资格化新stage/白名单，再按依赖串行运行：

```text
v8_authority_assembly_checks.dat
v8_p4_reference_recovery.dat
v8_p3_p4_compare.dat
v8_phase_checks.dat
v8_plain_dual.dat
v8_phase_dual.dat
v8_pde_compare.dat
v8_plain_reference_fit.dat       # D条件触发
v8_phase_reference_fit.dat       # D条件触发
v8_representation_compare.dat   # D条件触发
```

它们位于 `input/task042extra_feinn_5nm/`，每项仍是一项明确计算。长阶段使用 `python scripts/launch_task42extra_durable.py <one-run.dat>`，包装按spec选择FE/ML activation并调用 `python scripts/run_case.py <one-run.dat>`；检查stage使用同一正式入口和对应监督，不并行启动全部命令。新attempt单独run ID/index，成功artifact可hash复用；no-solve恢复/compare不得重新触发factor。

最少交付 `response_v8.md`、`outcomes/authority_recovery_v8.md`、`outcomes/phase_feinn_v8.md`，以及records中的campaign_design、repair_log、assembly_profile、authority、phase_checks、PDE/representation comparison、run_index、gate_decisions、resource_costs。每条结果注明measured/derived/predicted/not_run/failed/controlled_stop/blocked；表内单位、分母、实际值、限值与source/hash完整。主provenance仍含input_original、resolved_config、run_manifest、input/physical/source SHA、run_summary与环境/MPI/资源/artifact hash。

summary追加V8保留历史，更新progress、模型总账、test_summary及依赖组changed_files。checker从原字段重算结论，不相信status；浏览器只核验新review/新关键表，不让八次重复渲染挤占数值预算。Markdown本地结构检查不能冒充GitHub视觉PASS；渲染权限问题不阻塞其他数值工作，单列未验项。

Response V8开头明确：A是否得到合格p4以及p差异；C是否从零解出原p3；phase相对plain的同工作量改善；D是否区分表示/优化；解决了哪些真实阻塞与代价。即便方法仍失败，也应交付有针对性的修复和完整对照，而不是仅说“blocked，等下一次review”。

完成授权矩阵或用尽真实安全/阶段/总预算后推送 `HEAD:refs/heads/task42extra_feinn_5nm`，停止等待review；不自动做p5、h细化、多载波、目标尺寸5nm/0.7nm、不开始新的PC研究，不整体合并research branch。
