# Review V29：回到神经求解，连续推进自适应波动神经子空间的数值 Gate

## 0. 本轮裁决、范围纠正和执行身份

**本支线回到神经网络研究。结束 W0/W1、原尺寸全口面、模式清单恢复和主线接入的继续开发；不再用传统 Full3D 组件进展代替神经进展。旧 FEINN 配置的资源否决和数值失败保留，但它们不是“所有 FEINN 无解”的证明。授权一种明确不同的候选：学习新的局部波动函数，逐步扩展神经子空间，并在该子空间内稳定求解原有限元方程。**

用户要求“直到数值 Gate，否则不要停止”。执行含义为：实现、测试、修复、训练、扩充子空间、独立复验是一个连续工作包；不能在读完合同、接口通过、第一次报错、第一次不收敛或版本交棒处停止。**正常完成的最低条件是一个真正非可分三维 5 nm 散射案例的完整数值 Gate，而不是平面波、制造态或 reduced loss 通过。** 不保证必然通过；硬安全条件、总成本耗尽或可核实的算法容量否决仍是失败出口，必须如实交付未通过数值，不无限占机、不放宽精度、不伪造成功。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task42extra_feinn_5nm
canonical_worktree      = /home/fenics/Projects/NN-Lab-V2
review_date             = 2026-10-05
review_base_SHA         = bb0f5216976e58df834310595ebb3d23f1e37e3a
reviewed_response       = response_v29.md
previous_review         = review_report_v28.md
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
campaign                = V30_ADAPTIVE_WAVE_NEURAL_GALERKIN
required_response       = response_v30.md
new_campaign_hard_s     = 172800
normal_completion       = G_NUM_M5 evaluated and passed; full cost verdict supplied
ordinary_default        = UNCHANGED
master_or_other_branch  = NO_WRITE_NO_MERGE
```

本报告是用户明确要求在同一支线进行的方法更换，不新建分支。它覆盖旧 review 的 NN 全面暂停、固定旧网络/单载波/原优化器、按小阶段必须交棒和固定 bug 次数限制；也关闭 V27–V28 的后续确定性辅助工作。旧 task、review、response、raw、费用和历史状态均不回写。`LEGACY_FEINN_CLOSED` 只指旧配置；新增 `ADAPTIVE_WAVE_NN_AUTHORIZED_NOT_RUN` 不代表已经成功。

最终目标仍为 0.7 nm、约 2 TB 整机、任意非可分三维周期结构的准确前向计算。48h 是本次研发活动的成本上限，不是已证明的目标求解时间。本轮不直接启动原 50×25×140 nm 全尺寸问题，不向 Task42、Full3D 主线或 dot 写入代码、安排运行或发送自动任务。

## 1. 本轮依据与已经确认的事实

审阅刷新了精确远端 HEAD、任务目录、task、根规则、最新 review/response/summary 和材料表；历史数值依据下列原记录。本审阅没有访问工作站大数组或重跑计算，没有新的实测数值。目录中最新审查为 V28，执行回复为 V29，故新增 V29 并要求 Response V30。

| 依据 | 本次使用的事实，不扩大原资格 |
|---|---|
| [Response V29](response_v29.md)、[summary](outcomes/summary.md) | 全口面工作无新 NN、无体内散射解；额外 6307 项逐列失败仍保留。本报告不再续做其辅助闭环 |
| [V12 成本原记录](outcomes/records/auxiliary_cost_v12.json) | 旧 NN 必需前缀下界15758.74s，传统完整参考672.46s；23.43倍是前缀/参考成本比较，不是同精度通用速度比 |
| [Response V6](response_v6.md) | 当时固定195维特征的最小 native 残差约0.570578；只排除该冻结空间，不排除新特征 |
| [Response V11](response_v11.md)、[Response V18](response_v18.md) | M3600场误差约9.33%，Mfinal约12.29%；原残差下降没有转化为合格场。旧 GN/度量续扫关闭 |
| [Response V20](response_v20.md)、[Response V21](response_v21.md) | 固定横向相位进入 FE 基函数已经做过，精度未闭合。不能把固定单载波重跑称为新发现 |
| [材料表](../../input/materials/si_optical_constants_v1.json) | 本轮5nm和条件0.7nm均使用统一表；不混入W1另一份0.7nm数值 |

实现前读根/目录 AGENTS、仓库原则、本 task 和本报告；需要复用模块再读其目录规则。历史证据按 hash 复用，不为读过历史重装环境、重算全部 benchmark 或重渲染全部文档。当前论文依据为 [compatible FEINN](https://arxiv.org/html/2411.04591v2)、[DPWNN](https://arxiv.org/html/2310.09527v2)、[DGPWNN](https://arxiv.org/html/2506.09309v1)。借鉴的是兼容插值、复指数神经元、方向学习和逐步扩充空间；不声称复现这些论文，不把其边界/材料假设下的定理移植为本问题保证。

## 2. 方法必须有实质变化，同时避免另建传统求解器

### 2.1 学习什么

原网络是在一个固定大参数化中反复优化完整场。新方法每轮根据**还未满足的原方程**学习一个或一小组新的波动函数，冻结它们，再与此前所有函数共同重新求系数。新的空间随实际学习扩展，不复用旧195维特征、旧监督权重或旧 GN 方向。

一种可实施的原始网络函数为：

```math
v_\vartheta(x)=\sum_s\chi_s(x)\sum_{j=1}^{r_s}p_{sj}\exp\{i q_{sj}\cdot(x-x_s)\},
\qquad c_\vartheta=I^{\mathrm{curl}}_{h,\mathrm{MPC}}v_\vartheta.
```

这里坐标是输入；复指数是激活；复向量幅值和波矢参数是可学习权重；窗口中心/支持来自固定几何，不读取正确场。`chi_s` 为局部连续窗口，允许从粗分区扩至原网格的顶点星形邻域；不能只用全域单载波。幅值、方向和局部化的学习都要有真实梯度及参数变化证据。仅选择一个固定方向字典而不学习新方向的实现，归非神经控制，不能贴 NN 标签。

原始波动函数通过**全部边、面、内部 Nédélec 矩**进入既有 FE 空间，原方向变换与 Floquet 约束只施加一次。原始网络不是网格节点位移。周期边上的原始函数可用覆盖空间窗口的 Bloch 周期化构造；也可严格使用既有独立矩/MPC展开合同，但须区分“原始函数本身满足Bloch”与“插值场满足Bloch”，不能混称。对反向传播使用同一被资格化的映射。

**首轮刻意保留 M5 原 p3 离散，用来隔离“新神经求解机制能否求出一个已存在的离散解”。这不是已经改变连续 FE 空间，也不能消除该空间的离散误差。** 不把指数函数又插回旧空间后宣称突破 FE 表示下界。0.7nm原尺寸若需要波动富集空间，必须另有精度证据；本轮不同时编写 DGPWNN、另一个 DG/Full3D 引擎或重做 V20 的相位 FE 工程。

### 2.2 原方程驱动的可核验更新

令 A、f 为既有完整独立 FE 的 native 原算子及载荷，准确消去的端口按原合同恢复；单元内部仍完整保留。保存已冻结的神经列 U_m，求：

```math
a_m=\arg\min_a\|A U_m a-f\|_2,
\qquad c_m=U_m a_m,\qquad r_m=f-Ac_m.
```

本轮使用**完整 native 欧氏残差**，不是旧 Riesz loss 的续算。显式修改 loss 已由本报告授权，不修改物理 A/f。小残差仍必须经过增广、场、通道和功率的独立 Gate。

若 Q_m 为 A U_m 的正交列，训练新的波动函数去提高：

```math
z_\vartheta=(I-Q_mQ_m^*)A c_\vartheta,
\qquad S(\vartheta)=\frac{|z_\vartheta^*r_m|^2}{z_\vartheta^*z_\vartheta}.
```

这是原残差在一个新增有效方向上可被消除的能量。分母退化就拒绝此方向并换候选，不能靠任意epsilon制造高分。候选训练不得读取参考场、场误差向量、监督模型或精确逆。A作用与A*反传可使用已验证数组接口；网络空间参数导数不是 PDE 空间二阶导数。

新列加入后，以增量两遍正交化及小型秩揭示 QR/SVD 更新系数，**禁止求逆正规方程、形成全局 A*A 或全局 Maxwell 因子作隐藏完成器**。直接完整作用重算 r，而不是只信任小系统 residual。向已有空间加入独立列后，准确最小二乘的原残差不应明显增加；增加先查秩、正交性和映射，不把异常当正常训练。

新方法仍有代价：波动函数训练、插值、A/A*、列存储、QR、重新验算。它不保证病态性消失，也不保证比直接法更快。所有费用进入完整账。

## 3. 两个必须实际运行的公平候选

| 路线 | 内容 | 不得隐藏的限制 |
|---|---|---|
| `FIXED_WAVE_GREEDY_CONTROL` | 相同局部窗口、物理种子和完整矩；从固定方向字典按原残差选向，线性系数同样稳定求解 | 不只给一个很弱的随机网络作对照；包括入射/反射方向、规则球面方向和确定性局部细化 |
| `LEARNED_WAVE_GREEDY` | 从同一字典种子出发，用真实梯度优化连续方向/局部幅值，再扩充空间 | 初始字段、精度、容量上限、线性代数和审核口径与控制相同；学习开销全计入 |

字典的确定性分辨率序列、patch支持序列、频率范围、种子、每次新列训练策略，在首次真实学习前写入design并提交，**不需另等review**。建议从每个新模块1–2个复指数及小支持开始；不能把一次模块失败当整个方法失败。允许模块1→2→4→8个神经元、支持从粗窗口扩至实际网格邻域，以及新的独立方向种子；这都是同一学习机制，不恢复旧8966参数tanh/GN扫参。

外层容量可按32→64→128→256→512→1024→2048递增；必要时最多4096列，但必须先按 U、AU/Q、QR、临时列和原算子同时存活情况计算资源。维度界不是已测可用容量，更不是固定空间的成功承诺。列和导数按小块流式，禁止全网格自动微分图或额外全量Jacobian。秩门以固定1e-12相对奇异值起点；不能为结果扫rcond。近相关列拒绝/重选，物理基变换及误差保存。

需要缩放时只作可逆列归一化，完整系数变换保存；不改误差分母，不删难模式。小型列空间可以准确分解，必须记账；它不是全局FE直接逆。非神经对照同样得到已经验证的列归一化和稳定代数，不能只给NN加优势。

阶段性输出在固定时间/工作节点保存，不按参考误差挑最佳历史态。一条路线已经通过可冻结；另一条继续到同精度或其预登记比较上限。共享工作站争用不明时，速度结论为limited/inconclusive，不硬凑20%。

## 4. 模型、材料和精度身份

### 4.1 首要真正数值 Gate：原 M5，5 nm

保持原任务§4的几何和物理：周期10/7.5nm，x=[-5,5]、y=[-3.75,3.75]、z=[-1.25,8.75]；Si基底z<0，Si光栅x=[-2.5,2.5]、全y、z=[0,7.5]；空气缺口x=[0,2.5]、y=[-1.25,1.25]、z=[2.5,5]。掠角1°、方位0、s、幅值1，双Floquet/Fourier-DtN。原384hex、h1.25nm、N1curl p3、31968独立复FE和40端口，现场重新对照原packet身份，不凭计数通过。

Si使用统一表5nm条目：`0.99396854453 + 0.00435380777i`，epsilon=n*n、mu=1、exp(-i omega t)。旧原始 p3 native/moments/准确参考按其索引和SHA256只读复用；参考只供独立评分。文件缺失先查本任务封存副本；确实缺失，允许从冻结输入重建**该神经算例所需**的packet或一次同离散参考，不去重复W1全口面或改另一分支。

参考直接分解仅为独立验收，候选进程不得访问其因子、解或隐含读取标签的helper。小型参考采用已有方法，solve→true residual→保存最小packet→释放factor/KSP/无用矩阵→确认RSS下降→后处理。重建参考不成为新的传统求解器研究子任务。

### 4.2 0.7 nm 与空间表示的边界

开端做5nm及0.7nm解析平面波/平界面校准，原始神经函数误差与其 FE 插值误差分列。若原函数准确而插值误差大，不在同一不合格空间继续训练；只对**这个神经模型的验证离散**作必要p/h调整并记录新身份。解析/平界面不是M5完成，也不是主交付。

M5完整数值Gate通过后，在剩余预算内自动准入一个真实0.7nm缩小三维pilot：M5全部长度乘0.14，保留非可分缺口，使用材料表0.7nm条目 `0.999885140474 + 0.00000432477054i`。这是新物理身份，不是W1的另一Si值，不是原50×25×140nm问题。重新冻结实际模式集合，不硬套40或32060。

该pilot先作相应表示/插值校准，再重用同一个神经算法；不新增另一求解器。几何缩放只保持几何/波长比例，材料变化仍需真实计算。对p/h精度不足的空间，不以更多学习步掩盖；若本轮不能取得充分的物理参考，报告同离散资格与`DISCRETIZATION_NOT_QUALIFIED`，绝不宣称0.7nm目标已通过。

## 5. 数值 Gates：明确哪些才算完成

所有阈值为本轮预登记要求，不是已测结果。严格比较取同一物理定义，近零规则继承M5原checker并列实际分母、绝对差；不得拟合全局相位。旧40端口和新pilot端口分别使用自己的完整库存与参考面。

| Gate | 必须真正计算的内容与限值 | 结论边界 |
|---|---|---|
| `G_IMPL` | 全矩/方向/MPC/复数反传配对1e-10；非零实参数方向FD稳定区1e-5；小系统QR、秩缺陷和恢复正负测试 | 只是实现资格，不能停止交付 |
| `G_LEARNING` | 连续方向权重真实更新、非零梯度；训练不读标签；接受方向的实测下降与线性最小二乘配对 | 固定字典通过不算NN学习 |
| `G_NUM_M5` | full native、未凝聚增广、独立total原方程各≤1e-6；MPC/恢复≤1e-10；原全部内部/端口保留 | 不只验小空间方程，不以loss代替 |
| `G_FIELD_M5` | 同p3准确参考的total/scattered E、完整H、scaled-curl、原六点复E/H、完整复通道各≤1e-4 | 是同离散完整场资格，不是连续真解证明 |
| `G_POWER_M5` | R/T/A/A_volume误差和独立体吸收能量闭合≤1e-5，逐级功率≤1e-6 | A=1-R-T的恒等闭合不能充当证据 |
| `G_QUADRATURE` | 新波动函数插值/算子及最后独立重建在更高求积下变化≤1e-8；与原FE体积分设置分列 | q变化不是p/h收敛 |
| `G_NN_INCREMENT` | 上述正确性相同，对最佳合格非神经控制完整时间或同时树峰改善≥20%，另一项合规 | 分别报告表示收益与学习增量；不能只比参数字节 |
| `G_0P7_REDUCED` | 条件pilot同类全方程/全场/功率/资源门，独立新参考与p/h边界明确 | 不外推原尺寸、任意几何或2TB/48h |

**M5正常数值结项须 G_NUM、G_FIELD、G_POWER、G_QUADRATURE 联合通过。** 即使数值通过而成本不占优，也必须明确 `NUMERICAL_PASS_NO_NN_RESOURCE_GAIN`，不能按期望写NN收益。成本明显不利足以关闭这一具体部署方案，不证明所有神经方法无解。

原残差训练目标先用1e-8；若原方程达门但场未过，自动继续原残差目标至1e-10，仍只使用原r学习，不给训练器发送参考误差向量。不能靠改变验证定义救结果。若q漂移，先提高网络矩求积或按相位分段并重验受影响列；FE体/端口算子身份改变则创建新case并重核参考，不把不同矩阵的解直接比较。

## 6. 连续执行顺序与允许的自主排障

```text
S0：精确同步/数据复用 → 新波动神经元、完整矩、梯度和QR最小资格
S1：两波长解析校准，分清原神经表示与FE插值误差
S2：M5固定字典控制 + 真正可学习波动候选，从独立零散射初值开始
    └─ 原残差未过：修实现/增新有效方向/扩大已授权子空间，不能只打印FAIL就停
S3：冻结真实场 → 独立全数值验收、同成本对照
    └─ 求积/数值稳定问题：修相关部分，复用健康packet继续
S4：M5联合Gate通过 → 条件0.7nm缩小三维pilot，沿用同一方法
S5：一次Response V30：数值结果、学习贡献、完整成本、明确下一决策
```

S0/S1通过、代码commit、某个模块训练结束均不是新review请求点。没有新消息也继续当前授权依赖队列。定期给用户事实进度即可，不用“等审阅”终止自己的工作；用户的新停止指令始终优先。

**本批不沿用“第几个bug后自动停”的次数卡。** schema/path/API/dtype/写出/导入/方向/共轭/缓存/QR及checkpoint错误，在本批预算内定位、最小修复、跑受影响测试后继续。每次记录failure→hypothesis→change→test→resume，保留旧raw和费用。健康算子/参考/已接受神经列不因网页或归档错误重算。

正常不收敛不得改写为bug。若连续8个新模块在完整原残差上无可分辨下降，按已冻结顺序扩大支持/方向种子/模块宽度，再继续；不得原样重启同一参数无限训练。穷尽本报告的支持和4096列容量或总成本后，报告`NUMERICAL_GATE_NOT_REACHED`及实际r/场/功率、工作量和原因，不伪造数学不可能性证明。

对导数实现可在现有PyTorch自动微分与解析复指数VJP之间选择并独立配对；允许可逆列缩放、再正交化、分块与缓存、确定性求积分段、同一极小线性子问题的QR/SVD稳定实现。禁止暗加全FE精确完成器、teacher初始化、旧GN、全局Gram/Maxwell因子训练、改材料/波长凑成功、删通道或分母调优。

如果减少到只有非神经固定基才能通过，也交明确数值与贡献判断，不把其结果标神经。不得为“有实质进展”再转去W0/W1/存储/主线PC工作。

## 7. 运行预算、保护和持久执行

授权**新连续172800s研发窗**，从本批第一项实际准备起计入实现、等待、失败、学习、独立审核和交付；不重开旧窗口，不删除旧费用。该上限用于防止无限试错，不是要求跑满或保证48h内成功。不得复制旧每阶段20min/1h/3h后必须交棒规则；子阶段可依实际数据调配，最后至少留1800s完整验收/保存。每个单案例另报真正数值冷N=1时间，不能把全部研发账、历史前缀或只报推理的秒数混为同一费用。

CPU-only、MPI1、数学/Torch线程1、一个现场合格物理核；研究数值整树warn12/hard16GiB，轻检查2GiB，自身swap/OOC0。整机有效内存预留max(128GiB,10%)＋至少384GiB邻增长＋本任务预算；60s PSI稳定及原运行压力门保持。现有2TB整机不是本批RSS许可。项目其他heavy存在时仅依已授权小配额共享，不能新增第四个不受控heavy。

使用V27–V29已修复的原允许cpuset观察，不把单个固定核忙误写成整机无核；不为本任务改其他进程的亲和性、环境、锁或watchdog。当前合格核不存在/系统持续压力时停止本数值子树并做可独立轻工作；最多累计20min前台稳定窗口等待，全部计入总窗。不得后台无限轮询、放宽PSI、交换到磁盘或依赖OOM探容量。

持久launcher、watchdog、worker必须同一自有监督链。连接断开先确认原job是否仍运行；运行中就重新附着，不启动副本。每个接受列块保存参数、列/矩变换、正交因子、当前完整c/r、随机数状态、剩余额度和source绑定；atomic write/fsync/reopen，committed与trial分开。会话恢复后可从完整边界继续，不重做全部前缀；软件修复改变数学数据时，只重建受影响数据并版本化。

窗口还剩不足600s不再启动学习/QR大操作，保存及清场；最少120s安全保存缓冲。total窗口耗尽、安全硬门、无法恢复的权限/ABI/输入或授权表示容量耗尽，允许失败收口，但**不算已完成数值Gate，不授成功，不自动开下一48h窗**。这些不是普通bug处交棒的借口。

磁盘启动空闲≥50GiB，新数组总上限20GiB；列存储按活跃窗口规划。出现预算风险先分块/按需求值/释放无用图，不无计划扩RSS。常驻U、AU/Q与所有QR临时对象均计入，不以网络参数少宣称低内存。

## 8. Git、主入口、数据与交付

在既有canonical独占工作树执行。当前无本任务活跃run、工作树无不明修改后，仅精确fetch并ff-only同步本分支，不新clone/分支、不reset/stash/clean、不修改共享origin/fetch或其他worktree。每次实现/数学修复是新的小commit，不amend/强推；运行source与最后文档HEAD分开。

复用已有NN/FE独立activation、原M5完整矩和数组作用，以及稳定监督。新数值核放src/solvers，输入/编排薄层化。不要为新实验复制一套W1 receiver，也不要把W1的manifest和恢复门带入M5。新stage采用独立V30 opt-in身份，原case/default不变。

建议one-run输入：

```text
input/task042extra_feinn_5nm/v30_wave_checks.dat
input/task042extra_feinn_5nm/v30_wave_calibration_5nm.dat
input/task042extra_feinn_5nm/v30_wave_calibration_0p7nm.dat
input/task042extra_feinn_5nm/v30_m5_fixed_wave.dat
input/task042extra_feinn_5nm/v30_m5_learned_wave.dat
input/task042extra_feinn_5nm/v30_m5_verify.dat
input/task042extra_feinn_5nm/v30_reduced_0p7_fixed_wave.dat
input/task042extra_feinn_5nm/v30_reduced_0p7_learned_wave.dat
input/task042extra_feinn_5nm/v30_reduced_0p7_verify.dat
```

先实现/validate再运行，不把不存在的stage塞给旧白名单。一个dat只代表一个明确case/stage，不在单个dat里隐藏多波长campaign。现有durable包装调用 `python scripts/run_case.py <one-run.dat>`；各阶段按依赖串行。缺少自动续接时，只新增薄的dependency queue或复用现有queue，不开发新的通用作业系统。

每个run有input_original.dat、resolved_config.json、run_manifest.json、input/physical/source hash、run_summary、材料/几何/模式/矩/网络/列空间/参考身份、环境和整树资源；新几何和新作用绝不借旧hash。大数组留ignored，Git只放compact结果。正式候选训练输入白名单不得含reference_state、旧监督权重、精确逆或参考误差；审核在候选冻结之后另进程读取参考。

必须保存下列独立判定，不使用一个含糊总PASS：

```text
implementation_qualified
learned_direction_training_executed
m5_full_discrete_numerical_gate
continuous_discretization_qualified
neural_increment_qualified
reduced_0p7_numerical_gate
full_size_0p7_target_qualified = false
```

Response V30开头回答：有没有实际训练新的波动方向；有没有真正解出M5；神经是否优于同能力非神经控制；0.7nm缩小对象有没有实际运行；哪些Gate未过、具体差多少。`NUMERICAL_PASS_NO_NN_RESOURCE_GAIN`与`NUMERICAL_GATE_NOT_REACHED`均应直说，不能用测试数或辅助组件掩盖。

交付新增 `outcomes/neural_wave_galerkin_v30.md` 及design、training、basis_growth、full_numerical_gates、cost_comparison、repair_journal、run_index、resource_costs的compact记录。summary/README当前入口明确“本支只做神经”；保留历史全文和负结果；同步本分支progress与模型总账。不把参考求解/确定性控制的收益算NN，不将研发全部失败账虚构为未来每次必付成本，也不删除单次必须支付的训练/构造/纠错费。

GitHub视觉有限检查新review和关键新页；服务错误记BLOCKED，不阻断数值。禁止数小时全仓扫描、重复核对几千份无关历史、全量重新渲染或full pytest占据主要计算窗。每个已知可修工程bug在本轮修好，不再为同一个停止原因写十轮review。

最终只推送：

```bash
git push origin HEAD:refs/heads/task42extra_feinn_5nm
```

在联合数值Gate和成本判定完成，或上述明确失败出口触发后，交一次正式Response V30及准确HEAD、tracking/ahead-behind、clean和自身清场状态。不自动merge；不向隔壁任务发指令。**此前任何“完成接口后等待review”的历史文字都不截断本批授权。**
