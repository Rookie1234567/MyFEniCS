# Review V44：加宽仅有有限收益；用小型可逆特征变换检验神经核心求解的病态性

## 0. 裁决、目标与身份

**接受V44三路线完整实施与联合FAIL。16→32扩展带来了有限场精度改善，但宽冻结略好于宽学习，且每核最多1200次后仍有未充分求解的核心。不能认定“网络太小”已经解释全部失败，也不能认定全部网络容量已耗尽。本报告不再增宽、增秩或追加原样长训练；只批准一次保持模型空间与原目标不变的神经输出参数右重标度实验，连同原坐标控制、隐藏学习消融和完整物理验收。**

要消除的blocker：近相关或尺度悬殊的轴向特征，可能使有限的核心迭代不能有效利用现有网络空间。当前证据支持检验这一因素，不支持宣布它是唯一根因。所批准的是研究实验，不是生产预条件器；本支只做神经，不回到Full3D外围工程。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task42extra_feinn_5nm
canonical_worktree      = /home/fenics/Projects/NN-Lab-V2
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD    = 110a31769d4295159bea083c332c3f5abcede7ec
result_commit_time      = 2026-10-11T09:43:57Z / 2026-10-11 17:43:57 +08:00
review_date             = 2026-10-11 Asia/Singapore
previous_review         = review_report_v43.md
reviewed_response       = response_v44.md
campaign                = V45_FTT_FEATURE_COORDINATE_SOLVE
required_response       = response_v45.md
new_total_window_s      = 43200
production_merge       = NOT_APPROVED
```

最终目标仍为原尺寸0.7 nm、任意非可分三维周期单胞、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN、复E/H、完整衍射和体吸收。十进制2e12 B是整机物理内存，须保留系统余量、ownswap/OOC=0，单场必要准备至完整验收≤172800 s。**本支尚无合格方案承担该交付。**本批12 h为研究上限，不是目标48 h成绩。

本报告仅覆盖旧“不得新增参数PC”和已关闭配置中的本次显式opt-in实验；不是放开传统Maxwell PC。旧稠密波库、W0/W1、全口面、模式恢复、传统求解器/存储系统及主线接入仍不开展。不修改或向Task42、主线、dot、master及其他工作树派活。旧FAIL、未运行项和费用不改，新消息不重复发放本批额度。

## 0A. 2026-10-12执行复核：没有新结果提交，继续或发布唯一V45，不另开试验

**本次重新访问远端时，分支仍为本报告首次发布提交e0508555ffec6d13fad68b7516971c5899a09901，最新数值回复仍是Response V44；在该SHA直接读取response_v45.md返回404。不能将这解释成工作站未启动、没有局部结果或新的参数变换已经失败。当前最小动作是由执行端核对本任务现场，继续尚未完成的原V45，或者发布已经完成但未推送的V45。**

| 2026-10-12远端复核项目 | 可核实事实或明确未知 |
|---|---|
| 复核分支 | task42extra_feinn_5nm |
| 复核前远端HEAD | e0508555ffec6d13fad68b7516971c5899a09901 |
| 该提交 | Review V44首次发布；2026-10-11 18:10:59 +08:00 |
| 最近数值结果HEAD | 110a31769d4295159bea083c332c3f5abcede7ec；2026-10-11 17:43:57 +08:00 |
| 最近执行回执 | response_v44.md；三路线联合FAIL |
| 结果HEAD到复核HEAD | 仅1个提交，新增本审阅书；没有新增数值源码或结果 |
| V45实现、进程、检查点及未推送产物 | 本审阅端未SSH，UNKNOWN；须在canonical工作树核实 |
| 本次身份 | 原Review V44的执行澄清；campaign/response仍为V45_FTT_FEATURE_COORDINATE_SOLVE / response_v45.md |
| 本次新增计算预算 | 0；原V45的43200s总窗及各路线额度不重置、不叠加 |

本节并入尚未被正式response回应的原review，符合根AGENTS第15节；不新建Review V45或平行addendum，不改旧response。下方第1节记录的是首次审阅V44结果的证据范围，不是宣称2026-10-12又取得一批数值。当前复核重读了规则、原task与最新执行内容，并核对报告原blob055d76948fc8f3166b96a270b165dc650e2d04c1；没有再次进行M5计算。参见[分支](https://github.com/Rookie1234567/MyFEniCS/tree/task42extra_feinn_5nm)、[最新已提交回执](response_v44.md)、[根规则](../../AGENTS.md)。

### 0A.1 先识别现场，然后按同一任务继续

执行端只读检查canonical路径、branch/HEAD/worktree、数值锁、PID/start_ticks/命令行、campaign实际起止与剩余额度、run index和最新完整检查点。简要汇报状态后继续下面动作，不把状态汇报本身当成交付；不全盘扫描或读取邻任务巨型日志。

| 现场状态 | 必须执行的动作 | 不得做的事 |
|---|---|---|
| V45正在合法运行 | 保持同一进程树与watchdog；读取日志，沿现有身份完成计算与验收；数学规则未变，无须为此文档停止作业 | 不pull/merge运行源码、不kill、不启动副本、不重置时钟 |
| V45已有部分合格步骤，当前无活跃run | 按source/input/env/artifact和P身份核验健康产物，从下一依赖步骤或最新完整V45边界续接 | 不退回V44 parent重算已完成的V45，不因文档HEAD变化重跑所有资格 |
| V45已经完成但未推送 | 优先整理response_v45、完整Gate与compact证据，保留真实源码SHA并推送；只补缺失的checker/元数据 | 不因又收到审阅消息重做三条训练，不冒称此次文档是运行source |
| V45确实未开始 | 安全同步本报告，登记真实准备起点，直接完成原§2—7授权的实现、三路线与验收 | 不再只交“等待授权”、不另开V46、不重新训练十二轮前缀 |
| 原V45窗口或路线硬额度已耗尽 | 封存最近完整态，交付实际指标、缺失项和耗时；预算内尚可做的独立轻检查继续 | 不利用本次消息再获得12h、不把耗尽写成数值PASS或所有NN无解 |

合法run已经退出但留下旧锁时，必须依据PID/start_ticks及锁owner证明不是活跃作业，再只清理本任务陈旧锁。不得绕过真正的安全/权限/ABI/物理身份问题。本节不提供异步监控或定时抢资源授权。

### 0A.2 不改变数学合同；修好接线后必须实际验证

仍只做§3—6的三条路线、同一V44宽32学习末态、同一33维可逆特征变换；不增加网络宽度/rank、LSMR第三段、Gram或Maxwell全局因子。特征相关性、内层未解充分和容量不足仍是不同问题。V44的宽学习散射E约8.38%、宽冻结约8.23%，仅支持有限加宽效果，不能支持“只要更大网络就够”或“新变换已经失败”。

必须保留四项关键检查：一是计算输出增量delta=P y后才写回原模型，不能把求解坐标y当物理参数；二是原e=b−Bdelta及B*e与变换坐标P*B*e分列，不用小的变换梯度代替原最优性；三是P在同一次内层求解中固定、正反传共轭一致；四是实际点值网络经旧独立完整矩路径重建，不能只让新映射与自己配对。不可逆截断、错误左加权或残差分母改变都不是允许的“bug修复”。

普通API、dtype、坐标语义、共轭、缓存、目录、schema、资源角色或保存错误：保留failure→hypothesis→change→targeted test→resume；最小修复后继续受影响阶段，没有普通bug次数交棒卡。用已有runner/恢复/checker，不把本次扩大成调度或存储系统重写。健康的A/f、moments、参考、模型与producer场不因writer或网页错误重算；相关数学改变则必须新source并复验受影响内容。

不要等待三条路线全部结束才首次保存数值。每个完整核心与隐藏步骤按§7保存匹配状态；每条结束先冻结并保存原残差/状态/预算，随后在既有验收步骤完成独立全场。共享汇总器失败时复用逐路线健康结果，只修汇总。维持串行资源策略，不将局部检查改成第四条长训练。

### 0A.3 预算、Git和本轮可交付结果

原V45总窗43200s从本任务实际首次准备起计，不能用review发布时间或本次日期替代；各路线原7200s、最后至少3600s验收发布及所有新增/继承工作上限不变。已经发生的失败、修复、等待和未提交内层作用全部继续扣除。起点记录缺失时以最早可信的本批记录加明确保守余量恢复计费，标记NOT_RETAINED，不凭当前时刻重开窗。

安全Git处理先只读非交互fetch所需身份。无活跃run、worktree clean且可快进时用精确refspec与ff-only。若本地已有未推送V45实现，远端自其共同祖先起仅有本文件的review改动，允许在无活跃run、clean、核实无数值冲突时做同一执行分支的普通merge保留双方历史；不rebase/amend/reset、不强推，不merge master或其他任务。不允许仅为拉取此文档而改动运行中的源码。身份不同但内容未变的健康数值产物保留实际运行source，不替换成文档提交SHA。

完成V45时必须给出三条路线的原坐标/变换坐标内层质量、实际网络原残差与完整E/H/复通道/功率、固定与学习的差异、全过程新增及继承成本。未运行项按NOT_RUN或BLOCKED说明，不能只有“33×33接口已完成”。M5联合Gate与§6的0.7nm条件保持不变；未取得M5合格解前不跳过到原尺寸0.7nm。缩小0.7nm即使通过，也只是同近似电尺寸的下一检查点，不是2TB/48h原尺寸资格。

本次只修改本review的执行说明，不修改数值代码、输入、历史结果、其他任务或环境。完整源码与产物均按原provenance绑定。网页呈现服务失效可有限检查并标NOT_VERIFIED，不阻断计算或重新生成健康数值；本审阅端的文档检查不构成工作站数值PASS。

## 1. 审阅证据与独立判断

本次实际回读分支、Response V44主体和成本/因果限定段、summary当前段、逐核CSV、路线/PT记录、条件核心与两段补足源码、根/目录规则和仓库原则，比较上次review后的5次提交。原task重新核对为未变blob a0d3606aedbbce37066338de3763fe802590dedb；前版review从本会话已挂载原件完整阅读，目录检查未见更新的Review V44。历史任务范围沿已读原文衔接，不宣称本次逐行重审所有旧版本。未SSH、未检查工作站实时进程、未在本端复算大型M5原数组。

主要依据：[Response V44](response_v44.md)、[summary](outcomes/summary.md)、[两段内层CSV](outcomes/records/conditional_inner_solver_v44.csv)、[原始两段记录](outcomes/records/two_segment_core_refinement_v44.json)、[路线和PT](outcomes/records/conditional_core_routes_v44.json)、[完整Gate](outcomes/records/full_numerical_gates_v44.json)、[核心实现](../../src/solvers/ftt_conditional_core.py)、[补足实现](../../src/solvers/ftt_core_refinement.py)。代码证据固定于上述审阅HEAD；正式三训练source为a4c0d5e703eee8efe59740e706632eaeae2803e0，后续独立验收及元数据source另列，不以发布HEAD替代。

| measured；M5/5nm/384hex/p3/N31968/40端口 | W16学习 | W32学习 | W32冻结 |
|---|---:|---:|---:|
| 实参数/隐藏参数 | 9072/912 | 19200/3360 | 19200/3360 |
| 原native及augmented残差 | 0.391639358503 | 0.361290385199 | 0.359499231987 |
| 散射E相对误差 | 0.107837273178 | 0.0837766785225 | 0.0823025669279 |
| 散射H/curl相对误差 | 0.107930568412 | 0.0838326969727 | 0.0823550720923 |
| 独立能量闭合误差 | 0.0302399260155 | 0.0266238760746 | 0.0263308364469 |
| 新内层迭代/12核心中未充分次数 | 11680/5 | 12925/7 | 13823/9 |
| 新attempt秒 | 5087.24450240 | 5483.30524566 | 5760.15365775 |
| 同时自身树采样峰/B | 916967424 | 911515648 | 842186752 |
| actual/producer联合门 | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL |

当前宽网络E误差仍约为1e-4门的838倍，残差约为1e-6门的361290倍，不能说“只差最后一点”。加宽相对同政策窄模型的E误差降低约22.31%，但花费和内层终止质量不相同；宽冻结反而略好，不能把这次改善全归于隐藏学习。保存的非零.grad也不是学习证明：KH会写梯度缓冲，应依据真实参数变化及接受步。

窄网络不加容量也有改善，说明容量不是已证唯一解释。宽度与TT秩是不同限制；本轮不从宽度结果推出rank8足够或不足。V40条件性容量诊断不被重新包装为原FE的证明。

已有补足确实降低了部分核心目标，但多项仍INNER_ACCURACY_UNRESOLVED。当前源代码把原始神经特征直接送入无右变换的LSMR；这是实现选择，不是已证bug。继续增加同一迭代次数，不能保证克服近相关特征。下面只检验一个低存储、可逆的改动，保留负结果出口。

## 2. 唯一起点：复用宽学习第12轮，不重算前缀

三路线均从V44的W32_REFINED_CORE_LEARNED最终committed状态开始，不取误差略低的冻结模型或中期best。

```text
parent_record          = outcomes/records/conditional_core_routes_v44.json
parent_route           = W32_REFINED_CORE_LEARNED
checkpoint_name        = committed_000023.pt
checkpoint_sha256      = 02109f3e8d8f5361bc1d7f3b16633e1d257017fd1cf3b808bba6aad4fa57708f
checkpoint_bytes       = 2020100
parent_source          = a4c0d5e703eee8efe59740e706632eaeae2803e0
native_sha256          = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
moments_q30_sha256      = 22715fac468c4e364c3947e99672117f0f855dfe424914f9fce16be090a693f5
phase_sha256           = 32824e3063679681f77f6bb103fbb1ec9264f09f3441201407f6d0144cdc2ecc
```

真实路径由V44 run/index解析，不因同名PT混用V42/V43。核对全部原参数/buffers、12轮、36核心、19830计费内层迭代、137隐藏调用及c/r/RNG；现场以原记录验证这些计数，冲突不得凑数。独立恢复c/r相对配对≤1e-10。只允许有限查找本任务声明副本；原件不可恢复就明确数据阻塞，不重训十二轮补文件。

三份起始物理场完全一致；P只用于求解增量，不预先改变模型。所有路径继承真实训练前缀，冻结路线不是从未训练的传统基线。V44初始加宽不重复。

## 3. 唯一数学改变：对轴向特征作有界、可逆的右变换

### 3.1 它改变什么、不改变什么

固定其他核及当前隐藏函数后，原条件问题仍为：

```math
B=AK/\|f\|_2,\qquad b=(f-Ac)/\|f\|_2,\qquad
\min_{\delta w}\|B\delta w-b\|_2.
```

用一个小矩阵P重新表示输出增量，不改变残差的衡量方式：

```math
\delta w=P y,\qquad \min_y\|BP y-b\|_2,\qquad
(BP)^*=P^*B^*.
```

P可逆时，原可行场集合及最小残差不变；有限迭代轨迹和参数范数一般会变。秩亏时最小系数范数也可改变，不能要求两个求解器给相同系数；应比较实际场/算子作用/原目标。参考[LSMR作者官方说明](https://www-leland.stanford.edu/group/SOL/software/lsmr/)中的右预条件与原问题停止核验。这里没有全局Maxwell逆、Gram逆或传统FE完成器。

这项变换可能缓解轴向特征相关性，但不消除Maxwell算子自身病态、跨核尺度冗余、非线性局部极值或表达不足。没有证据可以保证它提高整体收敛；小型变换的收益必须通过真实内层与全场测量。

### 3.2 固定构造，不扫尺度或截断秩

对活动轴j，取现有FactoredMomentMap使用的全部、精确去重的一维物理节点，按固定升序排列。节点只用于定义参数坐标，不改变FE积分。直接调用含原Bloch相位的axis_features，保留32隐藏函数及bias，共33列：

```math
F_j(n,t)=\phi_{j,t}(x_n)/\sqrt{n_j},\qquad
F_j=U_j\Sigma_j V_j^*,\qquad
P_j=V_j\,\mathrm{diag}\!\left[
\frac{1}{\max(\sigma_k/\sigma_1,\tau)}\right]V_j^*,\quad \tau=10^{-6}.
```

使用直接complex128 SVD，取得完整33维右基；不得通过F*F平方条件数。通常节点数大于33，用经济型SVD；若节点不足则以小型完整右基补足，不能遗漏零奇异方向。bias/相位使sigma1非零；真正异常应查输入，不制造分母。

所有方向都保留，包括极小或零奇异值对应方向；将增益上限限制为1e6不是删除特征，不是给PDE加ridge。这是有界去相关/缩放，不称严格白化或容量证明。报告完整33值谱、触及增益上限的数量、原/变换后特征条件性及数值精度；F的条件数不是B的条件数。

P只沿输出数组[feature, component, left_rank, right_rank]的第一维作用，三个物理分量和TT索引不混淆。末端核心792个复系数，中间核心6336个复系数；仅存33×33小变换，不显式构造对应792/6336方阵，更不构造N×d列库。单个P对象体积17424B为derived，不冒充过程RSS。

构造P不需参考、A逆或G作用。当前轴隐藏参数/相位/节点变化后重新构造；仅输出或其他轴更新时F理论上不变，允许按准确依赖hash复用。每次LSMR内P固定，不能迭代中改变。不要将P乘到载荷或对残差作左加权，不重复Bloch/MPC。

若tau=1e-6在独立变换/实际写回资格中失败，允许唯一的较保守tau=1e-4后备；须先排除代码错误，且只根据数值稳定性选择，不能依据最终场误差或哪个更快挑选。两条缩放路线使用同一资格化策略并完整记录；后备仍失败则结束该变换数值链，不扩为参数扫描。

## 4. 全链正确性与两段求解：原坐标核验不能遗漏

复用ConditionalCoreAction、solve_refined、parent-fork及完整映射；以小型显式coordinate_transform接口接入，不复制另一套训练器。特别注意原segment返回delta后立即调用true_pair：新LSMR返回的是y，必须先得到delta=P y，再调用原B/BH核验。不能让适配器把BP、原B、y、delta混为同一变量。

两段上限沿V44：先300次tol1e-8；原坐标真伴随比>1e-3或第一段stop7时，允许同问题残差再补900次tol1e-10。damp0、conlim1e12、两段零增量初始化不变。第二段仍用同一P，最终delta=P(y1+y2)，不重复变换或重复相加；第一段delta/P基点身份原子保存。适配器停止码仅作内层记录，不能代替以下原问题核验。

每段记录原e=b−Bdelta、B*e及初始B*b的绝对范数/原分母；另列P*B*e及变换后的相同比值，两种不能混用。原伴随初值严格零和极小非零按旧规则区分；比值小也不是条件数无关误差证明。两条缩放路线与原坐标控制都用原坐标比值≤1e-3判断内层诊断充分。补足更坏则回退已验证第一段，费用保留。

每次实际写回原模型后，完整c/r与预测线性作用配对≤1e-10、原loss不增才提交。不能仅保存稳定的求解坐标y、却无法从实际MLP重建同一个场。系数增大/相消风险单列；不可用参考场覆盖网络。隐藏步骤仍是原坐标、固定输出的fresh原L-BFGS，不对P求导，也不宣称精确VarPro梯度。

资格至少含：P=I旧行为回归；小型复数满秩/秩亏/重复特征对照独立SVD；零奇异方向未删除；错误共轭及把y当delta的负控；实际三轴纯虚/bias/三分量K(Pv)与独立点值增量；复伴随≤1e-10；非零隐藏FD稳定段≤1e-5；参数/相位/节点缓存失效、两段恢复和回滚。SVD后向误差≤1e-12；P及逆回代误差≤1e-8仅作内部坐标检查，实际模型/FE门仍1e-10。

A阶段只作三个轴一次小谱和必要非零见证，不运行新空间oracle、监督拟合或容量证明。有限数学见证通过后直接运行下面三条，不为“测试通过”停下等待新review。

## 5. 三条实际同态对照；原科学门与成本同样重要

| 路线 | 核增量坐标 | 隐藏函数 | 分离的贡献 |
|---|---|---|---|
| W32_R12_IDENTITY_FROZEN | 原坐标P=I | 冻结parent隐藏层 | 原内层算法控制 |
| W32_R12_FEATURE_SCALED_FROZEN | 本文P | 冻结相同隐藏层 | 参数变换的贡献 |
| W32_R12_FEATURE_SCALED_LEARNED | 同一P策略 | 原3360隐藏参数继续学习 | 后续隐藏学习的贡献 |

三条均r8/W32/19200参数、同M5/5nm/384hex/h1.25nm/p3/N31968/40端口、材料/背景/A/f/native-EUC、原相位、体与DtN q15、网络q30/独立q60。完整矩、真实Piola/orientation、owner、MPC、端口小块作用全保留。没有增rank、增宽、改网络或损失。

按表顺序串行，从总第13轮z→x→y、第14轮反向开始；每条先完成两个新增轮次/6核心，最多7200计费内层迭代，每条路线新增墙钟硬上限7200s。仅学习路线有最多40次隐藏调用，原lr1/history10/strong-Wolfe/max_iter10/每轮20实际调用不变。原有停止策略不重复套到parent，不因残差暂未到0.1就提前结束。安全、非有限数、真实写回不稳定或对应预算仍保护；一条失败不取消其余独立路线。

第14轮后全部取得完整独立验收。学习路线最后执行，因此两控制结果此时已有；若学习R/E/H相对parent各≤0.8，或已进入R≤1e-5且E/H≤1e-3的近门区，可在本路线原7200s及campaign余额内继续两个轮次一次至总第16轮。该路线总新增上限变为4轮/12核心/14400迭代/80隐藏调用，wall不重开；后两轮是额外工作，不拿终态直接冒充同预算优势。否则完成真实负结果交付，不原样追加更多轮次。

候选首次R≤1e-8立即联合验收，必要时仅在剩余额度中按原方程精修到1e-10一次。参考只由隔离checker返回规定R/E/H标量与身份；不得反馈参考向量、误差图或为P挑参数。标明validation_used_for_stopping及benchmark_previously_seen；这不是盲测。

比较共同第14轮以及共同新增wall最近完整边界，保留保存滞后、内层实际工作量和共享CPU差异。先看原方程/全场，再看内层次数。若只使小坐标梯度更小而原残差/实际场不改善，不能授增益；若缩放冻结已经有同样效果，不能全算成隐藏学习收益。

## 6. 联合Gate、失败裁决及0.7 nm晋级

| actual网络与producer分别核验 | 不变门限 |
|---|---:|
| native、augmented、独立total原方程 | 各≤1e-6 |
| total/scattered E/H/curl、六点、四类完整40复通道向量 | 各≤1e-4 |
| R/T/A/A_volume、独立体吸收一致性与能量闭合 | ≤1e-5 |
| 逐级功率绝对差 | ≤1e-6 |
| 实际模型重建、MPC、端口恢复 | ≤1e-10 |
| 网络q30/q60及原作用、FE独立求积配对 | ≤1e-8 |

复用旧逐点MLP显式乘chi与StreamingMomentMap独立重建，再FE compare-only。原V1同p3参考SHA256 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7只读，不重求。旧健康场验收不重复。所有未过原残差的R/T/A仅diagnostic；用途false贯穿raw/PT/manifest/compare/reopen。

最终必须区分：内层原最优性改善但PDE仍失败；同参数空间的参数变换无收益；冻结与学习差异；实际读出不稳定；研究信号与严格PASS。没有充分内层精度不能作容量排除证明；即使每个核心准确，交替优化仍不是全网络全局最优。对本固定试验仍无联合有效信号时，关闭此配置，不自动扩大P上限、换rank/宽度/PC或新开oracle。

仅FEATURE_SCALED_LEARNED通过M5全门、两控制已验收、安全且总窗剩余至少10800s时，才沿既有授权运行一次全部长度×0.14的0.7 nm非可分三维pilot；pilot≤7200s，训练≤1800s，另外3600s留最终交付。正式材料、真实模式/背景/chi/网格/参考重新绑定，不硬套40通道或缩放FE系数；未准入不建空stage。

该pilot保持近似相同电尺寸，不证明原50×25×140nm目标、连续精度或任意复杂场r8充分。原尺寸仍需准确离散、多个电尺寸/所需rank、算子/端口/全场O(N)资源与全过程实测。增加整机内存无法替代约8%场误差与1e-4要求之间的精度差距。本支不能承诺生产时间，也不得把参数P小当完整流程小。

## 7. 资源、自主修复、版本与交付

唯一新增总窗43200s，自首次实际准备持久登记；A实现/资格软7200s，三路线各硬7200s，最终验收/发布至少3600s。剩余优先真实修复与有条件pilot，不叠加旧额度；重复指令识别已有run，不重开窗。前缀约10029.01s为V42+V43+V44学习attempt归属，由原records精确重算；研发总账不重复计费，网格/native/moments及完整冷N=1缺项仍UNKNOWN。

CPU-only/MPI1/math/Torch1，现场一个合格物理核；numeric warn12/hard16GiB、含临时规划≤12GiB、新cache/AD≤1GiB、轻2GiB，ownswap/OOC0。原PSI/CPU-SMT、系统max(128GiB,10%有效内存)和384GiB邻增长保护不改。成功60s准入计墙钟，真实拒绝后额外前台等待≤900s，不用旧耗尽观察池。启动磁盘及artifact预算沿原合同。

普通API/schema/维数/复共轭/坐标语义/缓存/目录/恢复/角色/保存bug，在同一批定位→最小修复→受影响targeted测试→健康边界继续，没有bug次数交棒卡。不要因日志、文档或checker错误重跑健康producer。实际数学变更必须新source并重新核验受影响路径，不能改原门或隐藏数值退化。数值停滞不是bug；真实安全、不可恢复输入、正确性或预算出口必须保全交付，不保证PASS。

每完整核心/隐藏边界原子保存原参数、P身份与构造规则、c/r、RNG、循环位置、继承/新增/累计费用。第一段求解坐标和原增量明确区分，未保存LSMR内态不冒称可恢复。durable全链、150s收口和至少120s保存；恢复前核对PID/start_ticks，合法作业不改HEAD、不kill、不重复启动，不操作邻任务。

只读检查Git与工作树，安全时精确fetch/ff-only；无活跃run且clean、仅本任务review文档分歧时可沿已有受限普通merge规则保留双方历史。禁止reset/stash覆盖、rebase/amend/强推或merge master。实现先提交，正式数值进src，复用runner/parent-fork/独立评分，不复制训练/调度系统。

```text
input/task042extra_feinn_5nm/v45_feature_coordinates_checks.dat
input/task042extra_feinn_5nm/v45_identity_frozen.dat
input/task042extra_feinn_5nm/v45_feature_scaled_frozen.dat
input/task042extra_feinn_5nm/v45_feature_scaled_learned.dat
input/task042extra_feinn_5nm/v45_feature_coordinates_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

stage须先实现/validate、targeted测试及clean commit，wrapper选择合格FE/ML/pure activation并调用scripts/run_case.py，逐项清场。每run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/MPI/线程/资源/artifact hash。

交response_v45.md、outcomes/ftt_feature_coordinates_v45.md和紧凑parent/谱/可逆性/原坐标与变换坐标残差/两段/真实更新/完整Gate/共同成本/修复/tests/run证据。更新本分支README/summary当前入口、progress、模型总账和changed_files；保留历史。不full pytest、不重装、不全仓反复hash。新文档使用fenced math；有限GitHub实际呈现失败如实NOT_VERIFIED，不让网页服务或文档收据阻断数值。

**完成实际对照和验收，或遇到有证据的科学/硬出口，才一次交回。不能只交“33×33矩阵实现了”。**只推本分支，报告完整HEAD、显式tracking/ahead-behind、clean与自身清场。审阅端小型复数代数检查不是M5实测；本报告不宣称工作站已执行新实验。
