# Review V37：FTTNN进入一次完整数值试验，不再停留于纸面准入

## 0. 裁决、目标和执行身份

**接受V37的设计与证据边界：旧稠密波库已关闭，FTTNN尚未运行，不能授予生产资格。本报告明确批准一次新的、小型FTTNN研究试验。所需秩和冷单场成本未知，是本试验要测的量，不再用“没有实验数据”循环阻止实验；也不把研究准入等同于一定收敛。**

要消除的blocker：此前神经方法需要全局N×m列库及重复QR，仍未达到精度；现在检验直接连乘的小神经核能否避免这两项，同时实际求准同一非可分三维方程。只减少参数/列库而不收敛，不构成收益。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task42extra_feinn_5nm
canonical_worktree      = /home/fenics/Projects/NN-Lab-V2
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD    = 5838d9c7560403164bdfee8b60d997bf4e18eeba
result_commit_time      = 2026-10-09T15:05:08Z / 2026-10-09 23:05:08 +08:00
review_date             = 2026-10-10 Asia/Singapore
previous_review         = review_report_v36.md
reviewed_response       = response_v37.md
campaign                = V38_FTTNN_NUMERICAL_PILOT
required_response       = response_v38.md
research_admission      = APPROVED_BOUNDED_EXPERIMENT_NOT_PRODUCTION
new_total_window_s      = 28800
ordinary_default       = UNCHANGED
production_and_merge    = NOT_APPROVED
```

最终目标不变：0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN、完整E/H/衍射/体吸收；十进制2e12B为整机物理内存，须留系统余量，自身swap/OOC为0；单场必要准备至完整验收≤172800s。原50×25×140nm目标尚未通过。本批8h是研发上限，不是目标48h成绩。

本报告覆盖V36的“仅准入说明、不得改src/input或新训练”，并把V37的PROPOSED_NOT_AUTHORIZED改为以下明确范围的研究授权。旧波库及其幅值/q/kappa续扫仍关闭。**本支只做神经研究，不恢复W0/W1、全口面、模式恢复、传统PC、主线接入或存储工程；不修改或安排Task42、主线、dot、master及其他工作树。** 必要的原FE算子和小型参考只用于本神经试验。不得因旧README的暂停状态再次要求逐步授权。

## 1. 本次审阅与已有结论

已读当前branch、Response V37、准入说明、summary、根/目录规则及仓库原则，核对上版review之后3次提交；这些提交只改文档，没有新数值代码或运行。前一完整review从会话挂载副本读取，原task和目录规则按未变blob及原文核对；目录无新增独立supplement。读取了feinn_torch、feinn_native和feinn_optimization相关实现。没有SSH、工作站训练或大型原数组复算。

| 对象与证据身份 | 已知事实 | 本轮处理 |
|---|---|---|
| V37，measured工作范围 | 新FE、网络前向、A/G作用及训练均0 | 不是FTTNN数值失败，也没有通过证据 |
| V36旧学习/控制空间，复用measured | 各1377列；最佳native约0.143188/0.144407；最佳G场误差0.00317624/0.00310153 | 固定空间不合格已闭环，不重算oracle |
| V37候选，derived | 秩链(1,8,8,1)，9072实神经参数；Chebyshev控制9120实参数 | 检验这一固定试验点，不预设小秩充分 |
| 冷单场与目标资源 | 新方法完整成本、所需秩、原尺寸精度均UNKNOWN | 实验量化，不先填2TB/48h PASS |

证据：[Response V37](response_v37.md)、[准入说明](outcomes/neural_restart_admission_v37.md)、[当前summary](outcomes/summary.md)、[V36原数值](outcomes/records/field_oracle_v36.json)。V37只是文本、形状和文献检查，不能沿用旧结果给新网络定性。

原始依据为[Feng等，FTTNN，2510.13386v1](https://arxiv.org/html/2510.13386v1)。本审阅读取方法与实验文字：它以神经核连乘表示函数；标量实验、单A100执行和高波数逐级初始化不提供本案CPU冷启动保证；其分离积分的前提不移植到本非可分材料。下面是保留原FE方程的复向量推广，不声称复现论文全部算法或继承其误差定理。

## 2. 冻结唯一表示、控制与训练目标

### 2.1 神经核与确定性控制

三维场的每个分量由三个小矩阵函数相乘得到。中间维度r允许多个方向耦合，不是要求材料或解是一个简单乘积；但固定r依然限制表示能力，不能据此宣称支持任意复杂三维场。

```math
E_{\theta,s}(x,y,z)=F_{x,s}(x)F_{y,s}(y)F_{z,s}(z),\qquad
F_{x,s}\in\mathbb C^{1\times8},\quad F_{y,s}\in\mathbb C^{8\times8},\quad F_{z,s}\in\mathbb C^{8\times1}.
```

| 路线 | 固定表达与实参数数量 | 真正被优化的对象 |
|---|---|---|
| FTTNN_R8_NATIVE_EUC | 三轴网络1→16→16→(48,384,48)，两层sin、线性末层；9072 | 全部神经权重和偏置 |
| CHEB_TT_R8_NATIVE_EUC | 同秩同三分量；每个核元素使用Chebyshev T0..T18；9120 | 固定一维基的全部复系数 |

每轴三个分量共享隐藏层但输出分开；实虚按最后维成对，物理坐标nm先按真实盒中心/半宽归一化。sin就是sin，不增添载波、Fourier字典、材料gate或额外频率扫描。Chebyshev使用固定递推，不作参考TT-SVD。两路线同秩且参数近似相等，不等于函数族完全等价；这是真正的神经核与固定函数核对照，不以弱随机控制代替。

采用seed4213701，初始化方案在第一次数值学习前写入design并固定：神经各Linear用Xavier uniform、bias为0；x/y末层非零，z仅末层weight/bias置零。控制x/y复系数实虚独立正态、标准差1/sqrt(38)，z系数全零。允许初始化时仅用固定33点Gauss一维节点把x/y每个分量核的均方元素模归一到1，缩放值写入初始化参数和收据，两路线同规则；这是一次初始化，不是训练中按结果重新归一。零/非有限归一因子是错误，不加epsilon掩盖。

不能三个核都置零。零散射时x/y及z隐藏层梯度为零可能正确；用非零资格态及初始z更新后的状态核验全部参数链。正式训练不靠强制扰动伪造参与，不挑seed或旧best。乘积的规范自由度可能影响优化，本轮仅记录各核范数与梯度，不增加自适应重标度/新的优化器来扫描。

### 2.2 原方程保持，训练不读取准确解

固定M5：λ=5nm、h=1.25nm、384hex、p3、31968独立复FE和完整40端口；原Si/air缺口、背景、材料表、积分degree15、MPC与DtN不改。参考为原同p3，而不是p4/p5或连续精确解。矩积分沿原q30，最后独立q60；不删除边/面/内部矩。

```math
c_\theta=I_h^{\rm curl}E_\theta,\qquad r=A c_\theta-f,\qquad
L(\theta)=\frac{r^*r}{2f^*f},\qquad
 g_c=\frac{A^*r}{f^*f},\qquad
 g_{\theta,j}=\mathrm{Re}\{(\partial_jc_\theta)^*g_c\}.
```

native欧氏残差是V37已提出的明确假设；它在新表示上是否有效必须实测，旧EUC负结果不抹去。无人工吸收、loss权重扫描、Gram逆、全FE逆、Krylov完成器、A*A或大Jacobian；端口原有的准确小块消元保留。训练白名单为原native/moments/几何/材料/约束，不包含reference_state、旧U/Q、oracle、POD、旧网络或参考误差图。

## 3. A：同批完成最小实现与真实资格，不开发另一套系统

### 3.1 必须修正的接线风险

[旧优化器](../../src/solvers/feinn_optimization.py)硬编码CoordinateField且用route != FEINN-EUC决定加载Gram；不得把新路线名直接塞入旧函数。用显式model_kind/metric_kind适配小型通用入口，原默认行为不变。metric_kind=native_euc必须有Gsolve/global_Gram_factor/global_Maxwell_factor均0的测试。复用较新、已合格的事务与durable边界，不照抄早期parameter-only checkpoint。

[旧完整矩映射](../../src/solvers/feinn_torch.py)缓存全C×Q×3坐标，且一个8cell图可能产生很大的r²核输出。新opt-in映射逐cell/块生成坐标，保留最多8cell，点微批默认512；先把FE系数余切经固定矩映射的共轭转置拉回点值，再逐点批对核连乘反传。每个点批backward后释放图，只累加参数梯度，不能cat所有微批后保留全图。

允许复用块内相同一维坐标的核评价，前提是重复坐标的VJP正确scatter-add；数值缓存绑定参数版本，接受/恢复后正确失效。允许点批512→256→128的等价资源修复，选定后两条同设置，单独计入费用；不改数值目标。所有矩/Piola/orientation/owner和MPC只应用一次，法向不额外连续惩罚。

原[FullNativePacket](../../src/solvers/feinn_native.py)已把局部体张量展开限定为8cell，但完整local/values数组仍为C×L；复用并如实计入。本轮不重写全局算子、端口或分布式数据系统。网络输出小不消除这些O(N)、O(CL)成本。

### 3.2 资格与执行量

先pure复数小矩阵检查，再用实际M5 packet作新增映射资格；不重跑旧oracle、全套E0/E1或full pytest。新参数非零态使用独立seed4213802，仅作测试，不作候选初值。

| 新接口Gate | 必测与限值 |
|---|---|
| 连乘/参数与初始化 | 9072/9120实际计数；非零复核心与独立einsum；三核非交换顺序/实虚错误负控；正式c0严格为0 |
| 完整矩 | 旧可靠非微批实现或独立逐cell映射与新映射相对差≤1e-10；覆盖edge/face/interior和两非单位Floquet缝/角点 |
| 梯度 | 实伴随≤1e-10；至少3个非零参数方向，h=1e-4/1e-5/1e-6中心差分稳定区≤1e-5；零态不替代非零态 |
| 等价分块 | batch1/8和点批128/512的c/loss/VJP≤1e-10；相同状态一次更新配对；无全网格AD图 |
| 原作用与求积 | 复用原A/A*资格，仅核对新c上的作用和梯度；非零初测q30/q60 c及A c≤1e-8；未过先定位，不训练后追改积分 |
| 保存/恢复与隔离 | 一个完整Adam和L-BFGS步恢复一致；线搜索中断恢复模型与匹配optimizer/RNG；强制误读reference/旧oracle拒绝；writer→fsync→重开实际c一致 |

在两个同样的非零资格态各测最多8次完整closure，互斥记录坐标、核评价、收缩、矩、A/A*、VJP、优化器、保存；同时记录RSS，不捏造旧瓶颈比例。该短测只决定工程是否可运行与微批，不按参考精度选择网络。实测能运行但预计1000次超过路线时间时，继续按真实时间上限执行并报告数量；不因预测不确定再只交准入文档。超资源先等价修复，无法安全容纳才是硬出口。

## 4. B：直接运行同一M5的两条无标签数值路线

A合格后自动串行执行FTTNN和CHEB控制，各从其固定零散射初态开始、互不warm-start。沿V37预登记Adam500(lr1e-3、无weight decay)后fresh L-BFGS(lr1、history20、strong-Wolfe、max_iter20/max_eval25、tolerance_grad1e-7/tolerance_change1e-9)。每条最多1000实际loss+gradient调用或3600s，先到者；导入/加载/所有失败试探/保存/方程审核在该路线预算内。是否执行到L-BFGS必须如实记录，不能用max_iter冒充实际调用。

不扫描rank/宽度/seed/lr/控制次数；Adam结束释放其状态再进入L-BFGS。每个完整外层step返回后原子保存参数、buffers、optimizer、RNG、阶段、计数、实际c/r和身份；已保存后才发committed。线搜索trial单列，异常恢复整套状态而不是只恢复参数。每25个完整调用后的下一个已提交边界和最终检查native/增广/独立total；实际调用数和检查间隔记录，完整停机保留≥120s。

原方程三项≤1e-8时先冻结并独立验收；若场未过且路线仍有预算，只按原r继续到1e-10，不得接收参考向量或调loss。正常时间/调用上限、优化器实际不再更新或非有限数值安全收口后，仍必须完成保存状态验收。一个候选失败不取消另一候选。不要在第一个有限但未收敛的模块、一次commit或普通bug处交棒。

标记reference_used_for_training=false、features_reference_exposed=false、benchmark_previously_seen=true、production_initialization_allowed=false。参考仅在冻结后独立评分；标量继续判定参与时明确continuation_uses_validation_scalars=true。新FTT未运行前不能保留PRODUCTION_READY，也不能因旧族CLOSED拒绝本次新授权。

## 5. C：联合验收，以及同批有条件的表示诊断

实际新模型由独立进程重新生成q30/q60完整FE系数，FE compare-only再读原V1参考，SHA256=0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7。模型schema另设FTT，不能调用旧wave exporter冒充新网络。复用最新独立pure监督父进程及FE checker，不重复V36的MPI父进程限制错误。

| 联合数值Gate，沿用原分子/分母 | 要求 |
|---|---:|
| native、增广、独立total原方程 | 各≤1e-6 |
| total/scattered E、H、scaled-curl；六点复场；四类完整复通道向量 | 各≤1e-4 |
| R/T/A/A_volume误差、吸收一致性、独立体吸收能量闭合 | ≤1e-5 |
| 每级功率绝对误差 | ≤1e-6 |
| 实际模型重建、MPC、端口恢复 | ≤1e-10 |
| 网络q30/q60系数和原作用；FE范数积分复核 | ≤1e-8 |

实际模型与producer分别验收，不选择较好版本；近零规则沿旧合同，不拟合整体复相位。功率在原残差未通过时只作diagnostic。仅同p3联合通过，不称h/p/端口收敛。

**若FTTNN未联合通过且完整映射资格仍合格，自动补一次新表示诊断，不再等下一轮review。** 两种模型从各自原零初态重新开始，目标为原G范数的参考场拟合，各Adam100后fresh同配置L-BFGS，最多500调用/1800s。只G乘法，不G逆，不把B失败终态或旧oracle当初值。两条均固定r8，不作TT-SVD/rank扫描。标记reference_used_for_training=true、pde_only_solve=false、official_candidate_results=false、production_initialization_allowed=false，数据/模型与B隔离；其权重不得反馈B或0.7nm。

诊断结束独立报告G误差和E/H/curl等原指标。拟合通过而B失败支持“存在可用表示但本残差优化未实现”；拟合失败只能否决这次配置/预算，不能证明整个r8函数类不可表示。该诊断不是又一次最佳线性空间oracle，不声称全局最优。没有新场时准确保留NOT_RUN，不为表完整伪造结果。

## 6. D：真正通过后，自动做一个缩小0.7nm实例

仅当B的FTTNN真实模型联合PASS、无资源安全阻塞且剩余≥7200s含最终验收时准入；否则此项NOT_RUN，不预建空stage来假装推进。M5全部物理长度×0.14，保持同一真实三维缺口拓扑、p3及网格细分数，波长0.7nm；正式Si数据只取统一材料表的名义0.7条目，n=0.999885140474+0.00000432477054i。重新建立材料/模式/背景/输入及算子身份，不能硬套40模式或旧FE系数。

FTTNN保持r8和同一参数化，从固定seed零散射开始，至多1000调用/3600s；不加载C的监督诊断或旧波库。数据准备、一次独立小型同离散参考和完整验收合计在D≤7200s内。准确参考只允许该缩小case独立评估使用；先容量Gate，必要时复用已合格准确凝聚，释放factor后恢复/输出。参考不能成为网络完成器，不为此开发新Full3D算法。

所有联合Gate沿用本例真实分母与全模式。本缩放保持近似相同几何/波长比，只检验0.7nm材料及接口下的小型非可分求解，**没有检验原尺寸的高频规模困难**。不得据此宣布原尺寸、任意三维或2TB/48h通过。D成功也只交回证据，不自动更大规模。

## 7. 成本门与2TB/48h的正确关系

新的FTT从零初始化，**旧10186.178641493432s波库训练不是其必要前缀**，不能机械加入新单场成本；它仍永久留在项目研发历史账。实际复用的native/moments/网格构建若是一次新问题必需，则必须计入冷N=1；不能因为本次从已加载包开始就漏算。把loaded-packet实测、可复用setup、完整冷成本、研发历史四种口径分开；冷账缺项继续UNKNOWN，不虚构比672.462895s历史FE更快。

神经权重9072×8=72576B只是一项。显式旧U/Q和反复QR不应出现；禁止用等价N×r²或N×P数组把它们换名加回。训练仍要计原算子、完整c/r/余切、CL展开、矩、点微批核/AD、优化器历史、序列化和端口，最终验收另计其生命周期同时峰。至少给出实测全过程树RSS、ownswap和互斥时间，以及按N/秩/积分点的对象模型。

只有两个结果达到相同联合精度，才能谈同成本算法优势；与合格传统FE比较同精度完整时间或同时峰改善≥20%才授资源收益。两失败候选的误差曲线/时间仅为研究对照。删去旧失败NN的U/Q不能算删去传统FE成本；不使用未来反演查询摊销。若数值通过但成本更高，写NUMERICAL_PASS_NO_VERIFIED_RESOURCE_GAIN。

预登记研究信号（不是成功门）：FTT终态native/增广≤1e-3且散射E/H/curl均≤1e-3，才记录SOLVER_RESEARCH_SIGNAL；任一未到仍如实FAIL，不只报loss。新机制的代码运行、NN更新、数值资格、成本收益和原尺寸资格五项独立判定。达到正式Gate前，本神经支线仍不能承诺承担原尺寸交付；不以扩大2TB配额解决低秩表示/优化问题。

## 8. 自主修复、资源和执行链

新连续总窗28800s；A实现/资格软7200s，B两条各硬3600s，条件表示诊断两条各1800s，D条件小0.7合计≤7200s，完整验收/发布软3600s。表示诊断与D互斥；未用软预算可登记转给受影响资格/验收，不放大单路线调用/训练上限，最后至少预留1800s。旧窗/旧成本不重置；本批预算不是必须跑满的时长。

普通model factory、dtype、导入、点批、导数、序列化、目录、checker和保存错误同批定位→最小修复→定向验证→健康边界继续，不设“第三个bug就交棒”。失败次数、耗时和旧源码保留；不重跑健康native/参考/已冻结候选。正常优化停滞不是bug，不改rank/seed/门限维持运行。资源/权限/ABI/无法恢复输入或总预算是明确硬出口；科学负结果完成验收后也是有效结束，不保证一定PASS。

CPU-only、MPI1、数学及Torch线程1、单当场合格物理核，避开忙SMT；数值整树warn12/hard16GiB、含临时规划≤12GiB，轻任务≤2GiB；自身swap/OOC0。保留原PSI60s稳定窗、系统余量max(128GiB,有效总量10%)及至少384GiB邻任务增长（已有合同更高取高）。不修改邻任务、共享库、全机swap/亲和性；全链durable launcher/watchdog/worker受监督，worker停止前150s收口，至少120s保存。成功准入计墙钟，不扣旧1200s拒绝池；真正拒绝后前台等待/重采样≤900s，不后台无限抢跑。

Git先核对分支/HEAD/worktree/锁及活跃run。已有合法作业时不改HEAD或盲kill；精确fetch/ff-only，不reset/stash覆盖不明修改。数值核进入src，runner只作参数化编排；先targeted测试与clean实现commit，再正式运行。新model和用途schema贯穿ready、恢复、独立重建和checker，训练端不隐式import FE、FE端不顶层import Torch。不重装环境、不full pytest、不全盘hash/重渲染历史。

在input/task042extra_feinn_5nm下实现并validate最小one-run入口后依赖串行运行：

```text
v38_ftt_checks.dat
v38_fttnn_native.dat
v38_chebtt_native.dat
v38_ftt_reconstruct.dat
v38_ftt_compare.dat
v38_fttnn_reference_fit.dat       # 条件：B未联合通过
v38_chebtt_reference_fit.dat      # 同一条件
v38_ftt_fit_compare.dat          # 含独立重建和FE评分
```

只有D实际准入后才建立v38_0p7_reduced_prepare/solve/compare三个明确输入，不能只注册未实现保护入口。长阶段均使用既有包装：

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

包装按任务spec选择正确FE/ML/pure activation，并调用scripts/run_case.py；每项清场后才下一项。不把全部命令并发发出，不绕开新stage白名单/身份。断连先识别原run，仍在运行就附着；真正退出才从完整状态恢复，预算不重新起算。

## 9. 证据、提交与最终回报

交付response_v38.md、outcomes/fttnn_pilot_v38.md及紧凑design/identity、接口与梯度、closure费用、两路线原场指标、联合Gate、条件拟合、实际D或未运行原因、repair/run/resource/provenance记录。大模型/场/原轨迹留ignored；不复制整份历史表到每个JSON。每个正式run仍绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/MPI/线程及artifact hash。独立checker从原数值重算，不只信producer状态。

README/summary当前页同时写“旧稠密波库关闭”与“新FTT研究实际状态”，保留所有历史原文；同步本分支progress、模型总账、tests/changed_files。建议分成接口资格、真实候选与修复、完整证据三组提交，不amend/强推/merge。只推本执行分支。

最终必须回答：是否真的从零训练三个神经核；是否未产生全局列库/大导数图；同秩控制与FTT各自原残差及完整E/H/R/T/A是多少；增加的成本是否抵消结构节省；条件拟合说明了什么；0.7nm是否实际运行及为什么。**不得只交“实现了”“证据不足待授权”或再次重复V36审计。** 出口必须是真实数值结果，或有证据的硬阻塞及所有仍可完成的独立工作。

本审阅端只做小型复数连乘/点批VJP与参数数量的合成检查，不是M5/FE验收。GitHub完整视觉尚未验证，本地结构与远端blob一致性另记；执行端只有限补查新关键页，网页服务错误不阻断数值或导致健康计算重跑。最终报告精确HEAD、显式tracking/ahead-behind、clean及自身清场，完成本有界工作包后等待review，不自行开启新rank/新架构或扩大原尺寸任务。
