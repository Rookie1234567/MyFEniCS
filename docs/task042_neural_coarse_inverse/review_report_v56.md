# Review V56：保留准备突破，建立完整单次成本，并成对验证相位表示

## 0. 裁决与本轮要消除的 blocker

**V57 按有限范围接受，结论为 `pass_with_qualifications`：15参考积分后端已经进入完整PDE且严格再现；同p6的y增量通过。跨p约3.4%的散射场分歧仍为FAIL，原尺寸0.7nm、2TB/48h与NN收益均未资格。**

下一轮不是继续原样加密，也不是再挑24个低频试验。授权 **V58：独立审核去重与精确求积资格 → 一个真实部署基线 → 同一倒格矢相位改写的p6/p7成对完整物理解 → 完整费用与资源决策**。保存场上的跨空间缺陷仅作一个短诊断，不得阻塞其他可信工作。

本批直接针对三个缺口：准确场基线未建立；准备优化后审核/边界重复工作已占主要成本；“完整必要单次计算”的实测计时仍unknown。必须交付实际运行可消费的改进、完整场及一份可直接使用的N=1费用，不能只有组件测试或下一轮建议。

```text
repository          = Rookie1234567/MyFEniCS
execution_branch    = task42_neural_coarse_inverse
canonical_worktree  = /home/fenics/Projects/NN-Lab
review_date         = 2026-10-07
reviewed_HEAD       = 8091c9515fc4c2116b57481408f71d05b0c7eb9b
latest_commit_UTC   = 2026-10-07T07:22:38Z
latest_commit       = docs(task042): close V57 with final costs and document evidence
latest_response     = response_v57.md
previous_review     = review_report_v55.md
previous_review_SHA = e08e598146f8bcd5a25d7bcf0364cf8c94c9f091
original_base_SHA   = ccd357885f7f9be84efe3be07868cc94f13d93fc
next_batch          = V58_DEPLOYMENT_COST_AND_PAIRED_GAUGE
required_response   = response_v58.md
new_complete_solves = at_most_3_including_scientific_repair_replays
NN_training_PC      = NOT_AUTHORIZED_THIS_BATCH
target_PDE          = NOT_AUTHORIZED_THIS_BATCH
merge               = NOT_APPROVED
```

最终目标仍是原50×25nm周期、z=-10..130nm、真空0.7nm、任意非可分三维单胞，单次必要准备到完整输出不超过172800s，约2TB整机物理内存并保留系统余量。当前是缩尺Full3D有限authority，不是Hybrid，不是原尺寸生产资格。2TB不会自动解决全局因子、端口显式耦合或不鲁棒迭代的问题。

本报告延续同一Task的离散稳定性/运行链验证；不新增通用求解器、NN架构或物理边界。明确覆盖V55的两次solve、固定载波不变、统一body q31和七小时窗口限制，改为下述三个有界计算与八小时窗口；不覆盖原物理准确性门，不重开V57旧时窗。V55之前的历史权限不自动恢复。

审阅依据为远程冻结源码、规则、task、V55 review、V57 response/summary/专题、run/source/费用/目标记录及最近13个提交的文件差异；本轮未新增补充任务文件。没有SSH、没有审阅端工作站全场数组重放、没有新PDE。下文measured指仓库所记录的实测，不是审阅端新测量；本报告建议均为planned/not_run。审阅端只做了小型复数相位恒等式、Gauss单项式及费用/内存算术检查，不能替代Basix/PDE资格。

## 1. 已证实结果与不应再做的工作

依据：[V57回应](response_v57.md)、[完整专题](outcomes/common_weak_phase_preparation_v57.md)、[阶段/source索引](outcomes/records/stage_verdicts_v57.json)、[科学记录](outcomes/records/scientific_checks_v57.json)、[最终费用](outcomes/records/resource_costs_final_v57.json)。

| recorded measured对象 | 实际结果 | 审阅判断 |
|---|---|---|
| K完整相位参考积分 | p6的58类、p7的64类；最大Frobenius差约2.31e-15/2.25e-15 | 当前仿射、常材料、实κ体矩阵有限资格；不重复建立15表算法 |
| B6，160cells/p6/828 | 独立true1.50467e-11、augmented3.54119e-11；全部内部恢复 | 正式门及direct目标通过；有限全局MUMPS因子确实存在 |
| R6→B6同离散 | scattered E/H约2.50914e-12/2.50927e-12；复通道3.07328e-12 | 后端真正进入PDE并严格再现，不是微基准 |
| Y6，320cells/p6/828 | 独立true7.07143e-11、augmented6.63914e-11 | 原式/direct/恢复/完整输出通过 |
| R6→Y6同p y增量 | scattered E/H2.23791e-6/1.66828e-6；240点2.60280e-6 | y增量通过1e-4，不授全方向或连续收敛 |
| R7→Y6跨p | scattered E/H0.03413294/0.03410379；复通道9.36145e-4；功率最大3.18721e-5 | 明确FAIL；不能由守恒或总场更小掩盖 |
| 24连续弱试验 | 四旧场与Y6的固定尺度缺陷很小，最大约2.37e-11 | 没有解释两簇场；不是完整对偶残差范数或误差上界 |
| 九项普通修复 | 原诊断DtN符号、近零尺度、抵消顺序及接线错误同轮修复；两solve未重放 | 按有效工作接受，不为bug数判任务失败 |
| 新费用/资源 | B6/Y6 dat1356.255/4692.117s，采样树峰7.6664/16.8848GiB，自身swap/OOC0 | 含研究消费者，不能称精简部署的完整cold N=1 |

此前T6横向x散射增量约7.47e-4仍失败；不要因这轮y通过就写“所有h方向收敛”。原点辅助倏逝幅值可能达极大指数尺度，B6/R6辅助坐标相对差约1.07而物理参考面差约3e-12，两者必须分列；不把辅助数组大差直接当物理错误，也不删其记录。

V57最终窗口closed，新增完整solve和numeric factor各2，NN训练0，原尺寸PDE0。完成队列后停止是合规交付，不是又被普通bug卡住。无需重跑H7消费、旧FLAT PDE、完整Q0随机嵌入资格、旧24弱试验或旧p/M扫描。

### 1.1 本轮只读邻支快照和分工

`task40extra_0p7nm_engineering@ffaf607384539e7d02bc35e1f685462e650abb21` 的V14已经完成Gx560四q因子/参考检查，但物理action identity为1.68346e-11，未过其1e-11门，target solve和官方RTA未运行；不能拿“四q通过”作为本相位空间可复用的完整PC资格。其B0、Gx560与本NOTCH载波/空间/模式身份不同，不能拼接功率表。工程线权限由其自身review负责，本报告不修改、不接管其任务。

其他只核对ref：`task42extra_feinn_5nm@cc6d0d5a7ae231563c6d4d49a2d822f0d3401d91`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`、dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`；不把ref读取说成完整审阅其最新结果。本批不训练NN、不做学习字典/teacher，不复制工程参考逆，也不重写dot的streaming算法。有限case内重用同一份已独立生成的q63包，只是本支生命周期接线，不是另一套边界研究。

## 2. 当前成本已换了主导阶段

按[V57非重叠费用](outcomes/records/resource_costs_v57.json)中Y6的exclusive口径：

| 阶段 | measured seconds | 相对于4692.1166s的derived占比 |
|---|---:|---:|
| 15参考表＋raw组合＋保存重开 | 163.9679 | 3.49% |
| 首次独立q63边界 | 1050.6428 | 22.39% |
| 后处理再次q63边界 | 623.4971 | 13.29% |
| 三列完整/内部/trace的独立body q31 | 706.1688 | 15.05% |
| 额外24函数弱诊断q23/q31 | 608.0067 | 12.96% |
| 全局numeric | 233.0546 | 4.97% |

两次q63与body合计约50.73%。首次独立q63不能免费删除；后一次须核对是否完全同身份后重用。弱诊断是研究支出，不因下一部署不再调用就虚报算法加速。旧表中的inclusive不再与上述相加，provider内/外层计时也不可混用。

**本轮时间方向应从重复raw积分转到“独立审核仍完整，但不重复构造”。** 一个理想化工作量情景：省去623.50s重复边界，并把body点数从4096降到512，约相当于该研究run的26.46%。这是含I/O/调度假设的优先级情景，不是预测速度、不作Gate、不承诺实际26%收益。

## 3. P：两个可回退、必须实际消费的运行链改进

### 3.1 已独立生成的端口包只构造一次

当前`phase_explicit_accuracy.boundary_check`生成q47与q63，随后`build_bundle`以及保存场审核又构造边界。本轮增加显式study-local provider：q47是生产构造，q63仍是独立构造；同一run后续分别读取原包，不再重复积分。

包身份必须包含：实际mesh/边界行及ownership、Basix basis与方向、MPC primal/complex dual、完整physical mode keys/kx/ky/side/polarization/参考面/normalization、κ、入射、q与quadrature points、producer source/module/hash。κ变化、p变化、MPC行变化均不能命中旧包。数组必须原子落盘、重开、长度/finite/hash核对；不通过则只回退该case的原正确构造器。

不能以q47生产包代替q63独立包，不能省略828任意模式或改变H的归一化；不能依赖旧native编号挪数组。q63可在factor前释放内存、保存磁盘，factor释放后重载供完整原式审核；pack/reload/驻留与实际建造次数全部计费。缓存重用不会自动证明目标规模streaming可行。

用一个已保存B6包做加载前后完整mode/行值对比及确定性复向量forward/adjoint配对，操作尺度门1e-12、向量相对门1e-10；不为验证reader重建全部旧q63。新PDE则实际生成本run自己的q47/q63并验证相互作用，随后完整消费。RHS也保持独立原入射构造，不从已求解场造b。

### 3.2 body原式采用经证明足够的求积，不降低物理Gate

对当前轴对齐仿射hex、单元内常数标量epsilon/mu、实常κ，实空间相位与共轭相消，body是有限阶多项式。设当前元素的`embedded_superdegree=d`，包络基与Cκ基都包含在逐轴Q_d空间，乘积逐轴不超过2d；实κ的大小不增加多项式阶数。

首选保守候选p6/q15、p7/q17；必须读取实际element/polyset确认d，检查实际Basix点数与多项式矩。若候选不覆盖2d，不得硬套p编号。该判断来自Basix官方`make_quadrature`的精确度定义及element属性，而不是“结果接近就算精确”。体源项若有非多项式背景、非仿射Jacobian、变系数或复κ，拒绝此优化并回退q31/既有可靠规则。

继续使用`phase_saved_uncondensed.local_vectors/uncondensed_vectors`的公开Basix独立评价，不读新15参考矩阵/raw/Schur来自证。保持完整、内部和trace三列、正确方向与MPC复对偶、curl/mass拆分与内部特解。先对保存B6及R7各做一次全cell三列向量低q重算，与其实际保存q31向量逐项比较：相对差<=1e-10；curl/mass贡献和的操作尺度差<=1e-12。近零独立列使用预登记运算尺度，不能用不相关小结果作分母；原true residual分母和1e-6门完全不改。

求积资格只用于body向量作用。**q47/q63 Fourier边界、带解析指数的RHS、跨gauge场差积分不适用该多项式捷径。** 输出体吸收及原q23/q31场比较本轮保留，避免同时优化所有消费者。新κ′的body先在两个固定实际长宽比单元上以q31独立复方向验证，再部署已资格低q，不重新生成全体旧高q审核。

一个候选未通过就回退q31，不为它重解已返回的PDE。资格费用、低q重算、磁盘和失败均计入研发总账，不能把这部分藏在“免费离线”。旧q31结果不改写。

## 4. C：一次真正完整、可计时的部署基线

新增`C6`，几何、p6/828、κ及物理与V57 B6完全相同：160cells、104832独立FE、32832 trace、72000内部、33660含端口行。实际运行从物理零初值开始，不能读取旧场作初值、PC或右端。

从独立空的本case数值缓存启动，重新构建本case所需15参考表、raw组合、凝聚、q47/q63和numeric因子；不清全机OS缓存、不操作邻JIT。记录环境/JIT缓存是否命中，将其准确命名为“数值准备冷启动、OS/JIT状态已记录”，不称全系统冷启动。

单次部署计时以进程启动为起点，到完整原式检查、全部内部恢复、240点/所需完整场数组、828复模式和功率、RTA/独立A_volume、provenance及必要写出完成为止。mesh/JIT、包加载/首次建造、factor释放、审核与IO都在其中。比较旧B6、历史审阅checker、24函数诊断或论文式比较另起保存场consumer，单列T_research，不嵌入部署时钟。

C6必须同离散再现V57 B6：total/scattered E/H/scaled-curl、240点及物理复通道<=1e-6；RTA/A_volume<=1e-8；逐mode功率<=1e-9。原方程/恢复门见§7。它验证新运行链，而不是再次声称找到了准确空间。

没有配平的旧完整冷链，不授端到端速度比。**但本批必须取得一个真正的完整T_N1实测值**，而不是因为没有旧对照继续把所有必要费用标unknown。允许另外给基于原exclusive阶段账的derived对照；两者分栏。普通writer错误只补保存场消费，实际重复费用也必须加回该case的完整总成本，不能剪掉失败时间。

## 5. G：固定一个倒格矢改写，但p6/p7成对求完整场

### 5.1 它改变表示，不改变物理入射

将有限元需要表示的一部分相位放入解析载波，在相同物理问题上检验有限空间与稳定性的敏感性。固定且仅固定：

```math
G=(0,2\pi/L_y,0),\quad \kappa'=\kappa+G,\quad
u'=e^{-iG\cdot x}u,\quad
E=e^{i\kappa\cdot x}u=e^{i\kappa'\cdot x}u'.
```

```math
C_{\kappa'}u'=e^{-iG\cdot x}C_\kappa u,\qquad
C_\kappa u=\nabla\times u+i\kappa\times u.
```

在当前s=7/135几何，Ly=35/27nm，Gy约4.84702866554nm^-1；κ′y约5.62921763375nm^-1。从未舍入descriptor计算，不用Markdown近似值补低位。连续Maxwell与Bloch边界不变；**有限空间gV_p和g′V_p一般不同，这不是矩阵的纯坐标相似变换，也不应要求两个有限解机器精度相同。** 新gauge差异是准确性/敏感性指标，不能自动叫bug或预先宣布新gauge更准。

禁止修改cfg的物理kx/ky、grazing/azimuth、入射极化、epsilon、几何或physical mode cutoff以实现κ′。新增独立的numerical carrier descriptor，沿make_setup/build_bundle/raw provider/RHS/surface/恢复/evaluator/independent audit显式传递；普通`carrier(cfg)`默认保持原行为，不全局monkeypatch。审计这些调用点，尤其防止保存了κ′但后处理仍重新从cfg生成旧κ。

所有828个**物理**mode的m/n、kx/ky、kz分支、侧、s/p、参考面及归一化保持；包络的横向频率是k_mode_parallel−κ′。shift=(0,1)时包络Fourier索引n_env=n−1，物理mode key仍为n。入射包络现在含exp(−iGy*y)，不能仍当横向常数。C与D按各自trial/test共轭独立推导，不能统一错换符号。

跨gauge比较必须恢复各自完整g*u和g*Cκu/(i*k0*mu)，使用同一个原物理背景定义scattered场；不直接比较u系数、不拟合幅相、不用新包络背景改变分母。物理hash与数值hash分开；若现有hash定义混含离散项，如实解释，不伪造相同hash。

### 5.2 前置控制不能变成新的长测试任务

做复数三分量相位/curl恒等式、双周期相位、两个实际cell的原式向量、完整828物理inventory与非零端口载荷控制。保留无PDE解析FLAT场检查：相同解析物理场以两种包络表示，独立连续body+port+load应给相同平衡。此控制不是要求两种有限元插值完全相等；必要时只检查已知背景表示误差并报告。

先通过输入、MPC、相位和端口身份，再启动真实G计算。普通控制器符号/字段错误同轮修复；诊断标量未稳定先隔离该诊断，不能把它未经验证的异常判为旧PDE错误。真实原式/材料/ABI/监督不可信则停止依赖数值计算，不越Gate。

| 新完整模型 | mesh / degree / modes | 独立FE / trace / 内部 / 含端口行（待现场复核） | 用途 |
|---|---|---|---|
| C6 | 原Z2 / p6 / 828 | 104832 / 32832 / 72000 / 33660 | 新运行链同离散再现与T_N1 |
| G6 | 同Z2 / p6 / 828，κ′ | 104832 / 32832 / 72000 / 33660 | 新表示下完整物理解 |
| G7 | 同Z2 / p7 / 828，κ′ | 166208 / 45248 / 120960 / 46076 | 与G6成对检验，不默认它是真解 |

固定原s=7/135 NOTCH、λ0.7nm、掠入射1°/方位5°/s/幅值1、Si n=0.999885140474+4.32477054e-6i、epsilon=n²、mu=1、air1。材料canonical表hash仍以V57登记55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2核对。所有内部自由度与非零特解保留。每个解独立物理零初值、原有限直接法与最多两次既有精化，不扫描载波/求解器参数，不复用另一case全局因子。

主比较只做：C6/B6、G6/G7、R6/G6、R7/G7；沿共同物理积分和原分母，全部828复通道/功率与240点保留，不展开全部两两组合。跨gauge项非多项式，继续q23/q31操作检查；必要时一次q39，未稳定标INCONCLUSIVE并保留解，不重复factor/solve。

**跨p准确性FAIL不应阻止G7**：它正是本批要测的对象。只有G6原方程/身份/资源不可信才阻止依赖比较。C6的新快路径不可信时隔离该路径，G6/G7可按原正确包构造和q31审核继续，并重新计算真实预算；不要为了再现C6盲目耗光三个solve槽。

## 6. S：消费旧实际解的完整跨空间缺陷，而非重做随机嵌入

旧`phase_p_order_consistency.FullBodyEmbedding`已验证完整P及复对偶，且SAVED_P见证保存了Ju、action7等。优先从身份匹配的Q0/保存包读数据；只研究同网格、同κ、同828物理mode的R6/R7。不同mode/几何/κ不能硬拼；确缺一个完整向量时最多补一次独立高空间作用，不重开整套Q0。

以未凝聚原物理作用或一致归一化的完整增广作用构造：

```math
r_{7\leftarrow6}=b_7-A_7Pu_6,\quad
\delta=u_7-Pu_6,\quad r_7=b_7-A_7u_7,
\quad A_7\delta=r_{7\leftarrow6}-r_7.
```

检查原P^H下的缺陷、实际完整新方向缺陷及上式identity，区分body/端口/内部/trace。不要将“高p中最后一段编号”直接当层级补空间，也不要把凝聚后的trace传递冒充完整P。若使用物理DtN作用，说明原端口残差如何计入；若使用增广作用，端口采用同一物理参考面坐标，不能将1e102辅助坐标加入Euclidean范数得到伪条件数。

本项回答的是：低空间解在高空间实际遗漏了哪些平衡条件，场差是否与这些缺陷相符。欧氏残差与物理场范数、运算尺度分开；无完整Riesz逆/谱资格，不宣称inf-sup常数、condition number或全误差上界。解差作为诊断可以使用，但不得拿它作新解的初值/teacher或声称独立验证。

S预算目标1200s，可在P资格阶段或保存场消费阶段顺序执行；超过预算保留partial继续C/G。24弱试验的旧小数值不重复做，S的缺陷大也不是软件bug证据。没有误差证书不能随意宣告任一簇场为真。

## 7. 门、排障、资源与执行顺序

正式true/native/augmented/port各<=1e-6，direct内部目标各<=1e-10单列；原作用identity、内部恢复与MPC<=1e-10。空间/跨gauge比较total/scattered E/H/scaled-curl、240点和物理复通道<=1e-4；RTA/A_volume及能量缺陷<=1e-5；逐mode功率绝对差<=1e-6。C6更严同离散再现门见§4。原分母与近零规则保持，不调门掩盖结果。

执行顺序为 **P资格及轻量G控制 → C6 → G6 → G7 → 保存场比较/独立VERIFY/完整费用**；S可在空档先完成，绝非总队列硬前置。每阶段保存可消费产物，代码提交或一组单元测试通过不交棒停工。数值部分必须在src，runner仅编排；复用已有参数化runner，不每个case复制求解器。

本轮新八小时总研发窗，科学有载最多六小时，最后一小时只交付；第一次实际工作冻结UTC/monotonic/boot_id，上下文恢复读真实时钟。实现、修复、等待、失败、启动、hash/IO和交付均计费，不刷新窗口。P与G控制总实现目标两小时；普通修复/受影响重放累计最多两小时且包含在总窗，不是额外加时。

最多三个完整新solve，包含科学修复重放，至多三个新全局numeric因子；既有最多两次精化的MatSolve不混称新的numeric factor。每个合法返回立刻保存最小完整packet；true residual/既有精化后释放factor和无用矩阵，再完成审核/输出。writer/schema/路径/collector错误只补消费，不重做已完成solve。

同一根因两次无效修复后切换本报告允许的正确回退或隔离该子项，不第三次盲重跑；不按总bug数机械停全队列。确认数学bug才宣布相关旧证据受影响，列精确scope/source/反例，不因诊断代码错误作全历史重算。资源/身份/监督红线不是可绕过的小bug。

保持64GiB同时规划、80GiB警戒、96GiB采样树停止、100000凝聚行；numeric前live整树RSS+2×可靠INFOG16/17(decimal MB)+2GiB<=64GiB，ICNTL22=0、自身swap/OOC0。MPI1/math1/GPU0/Loader0，一次一个本任务actor和factor；原宿主/PSI/cgroup/邻增长余量、物理核与忙SMT隔离规则保持。现场另一heavy不允许并发时只完成合法轻量部分，不占用邻任务预算、不改其affinity/锁/进程/工作树。

每次新solve须预留不少于1800s用于其完整审核/输出以及最终交付，G7以p7实际阶段成本重估，不把p6时间直接照搬。不为CPU探测或文档检查设置不合理的几秒强杀；资源观察相隔至少120s、累计前台等待最多1800s，不写后台自动重启器。

新ignored额度12GiB、去重总额度102GiB、free>=50GiB；现场stat后准入，不删除旧负结果。V57已记录约6.87GB新增/59.75GB累计，只是旧快照非当前可用性。名义0.5s采样与实际数秒间隔分列，记录最大gap；采样峰不称连续硬峰，监督失效先停止后代，不能用OOM探容量。不新增必须提权的环境/ABI/cgroup依赖。

只做相关targeted数学/接口回归、修改文件Ruff/compile、dat validate和一次轻量文档检查；不例行full pytest/CI、全仓索引、历史hash扫描或重复提交前全部重跑。新科学source先commit clean再运行，文档HEAD与运行source分列。

## 8. 2TB/48h预算要按实际算法存储，而不是“34个向量”泛称

直接消费[V57目标更新](outcomes/records/target_gap_v57.json)与V56原尺寸情景，不再创建同样的网格库存。那是保持极细物理cell的假设，不是准确空间下界；268156为manual模式情景，不是所有物理条件下必须的通道数。

对restart m=32、同时存V_(m+1)和预条件后方向Z_m的标准FGMRES，两个主向量库即65条，另有解/RHS/残差和workspace。V57“34条”被明确标为假设，但不能拿它当未来FGMRES总账。PETSc实现确实另分配prevecs；实际采用哪个solver、是否重计算/压缩/落盘，必须分别记录，不能假设所有方法都恰好65条。

| derived情景，decimal单位 | p6 | p7 |
|---|---:|---:|
| 原V56 trace行＋假设268156端口 | 507608956 | 699775356 |
| 一条complex128 trace+port向量 | 8.12174GB | 11.19641GB |
| 65条trace+port主库 | 527.913GB | 727.766GB |
| 65条完整FE主库，不含端口/其他对象 | 1.72571TB | 2.74026TB |

这是选择凝聚trace空间、完整内部按需恢复的动机，不是2TB资格。还必须计入本地因子/Schur、恢复表、mode/trace、operator、MPI复制、Krylov临时块、审核/输出和系统余量。分布式数据不能每rank复制完整库；当前MPI1有限direct实验没有验证未来这些对象。fullspace matrix-free不自动等于trace-space Krylov，也不能因不显式存A就忽略局部Schur和PC。

时间账至少采用：

```math
T_{N=1}=T_{mesh}+T_{JIT}+T_{operator/DtN}+T_{PC/setup}
 +N_{it}(T_A+T_{PC}+T_{orth/comm})+T_{recovery/output/audit/IO}.
```

172800s是完整部署目标，不是outer solve计时，也不是所有研发轮次累计上限。没有实测目标迭代数、每步原作用/PC/通信时间，不从C6直接线性外推原尺寸。先交本批真正T_N1，再为已资格空间安排多个中间规模的容量/时间标定；原global direct只作有限authority，生产仍需可扩展Full3D iterative与streaming DtN。Hybrid只能在可利用结构上作并行加速，不替代任意三维主线。

## 9. 有实质内容的决策与交付

| 本批观测 | 必须作的决策，不自动开新轮 |
|---|---|
| P优化再现通过，C6得到完整T_N1 | 接受有限运行链改进；给实际阶段费用/峰、独立审核来源与适用边界，不归NN |
| G6/G7仍约3.4%，跨gauge影响远小于跨p | 保留负结果；不追加载波、p8/Y4/Z8或模式；用完整跨空间缺陷确定下一项离散/稳定性验证 |
| gauge改变场但G6/G7未过门 | 说明表示敏感，不宣称新gauge更准；明确哪个完整observable失败 |
| G6/G7增量通过且物理/原式均过门 | 仅授新表示下p一致性候选；仍需独立h/误差资格，不能立刻升原尺寸或把高p当真解 |
| S定位实际映射/原式矛盾 | 最小修复受影响路径并在三solve总槽内重排；不强求同时完成全部G模型 |
| 新优化不可靠 | 正确回退并保持完整科学对照，交部分实现/费用和真实缺项，不在普通接口错误上整批停工 |

唯一新的review权威为本文件，不增加平行addendum。建议本轮入口（待实际实现，当前not_run）：

```text
input/task042_neural_coarse_inverse/v58_audit_pipeline_qualification.dat
input/task042_neural_coarse_inverse/v58_saved_p_defect.dat
input/task042_neural_coarse_inverse/v58_deployment_baseline_p6.dat
input/task042_neural_coarse_inverse/v58_gauge_y1_p6.dat
input/task042_neural_coarse_inverse/v58_gauge_y1_p7.dat
input/task042_neural_coarse_inverse/v58_compare_verify_cost.dat
```

统一`python scripts/run_case.py <one-run.dat>`，每个dat是一项明确计算，P/S不暗藏solve，最后消费者不暗中重跑PDE。输入original/resolved、run_manifest、input/physical/source SHA、环境MPI/线程、资源与artifact hashes均完整；数值carrier另有身份。大型数组仍ignored。

交付`response_v58.md`、`outcomes/deployment_cost_paired_gauge_v58.md`及紧凑records：阶段决策/source、C6/G6/G7结果、完整场/模式/恢复、P独立性与求积资格、S缺陷、T_N1与T_research非重叠账、RSS/gap/swap、repair journal、目标向量库实际scope。更新summary、development_progress与model_registry只追加简明本轮入口，不继续无限复制历史包。

Commit顺序：C1最小接口/控制与targeted tests；C2资格化后的P/G实现及dat，clean运行；C3保存消费者/必要最小修复；C4完整结果/response/费用。只在本分支提交推送，`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`，核对remote/full SHA/upstream/clean/清场/锁释放后暂停。未经最终review与用户授权不merge，不改dot/工程/NN邻支，不自动通知隔壁或开新时窗。

## 10. 方法依据与审阅边界

[Basix0.10求积定义](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.quadrature.html)、[元素及embedded_superdegree定义](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.finite_element.html)、[PETSc FGMRES源码的prevecs分配](https://petsc.org/release/src/ksp/ksp/impls/gmres/fgmres/fgmres.c.html)。外部文档用于数学/API依据，不代表工作站已安装最新PETSc版本，现场ABI保持不升级。

审阅端相位/curl代数相对差约1.52e-16，候选Gauss单项式检查误差不超过2.92e-16；这只检查推导和算术。远程原始ignored数组、真实FE求积等价、新运行链收益与G6/G7结果全部由本轮执行资格。GitHub页面视觉核验与文本/本地结构检查分列；无视觉证据不得写已验证，但不因此重跑科学计算。
