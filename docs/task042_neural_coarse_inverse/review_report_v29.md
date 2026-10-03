# Review V29：关闭V31测试缺口，同轮修复后必须推进真实诊断

## 0. 决定与本次用户指令

**接受V31真实study接线及历史停止记录；本次独立定点复验修好的拒绝fixture，1 passed，关闭该软件缺口。V32的主交付是原两冷态的一次真实回流诊断及独立审核，不再是又一轮测试准备。用户已明确要求“不应测试失败就等待审阅”：本报告替换Review V28中“前测出现新错误即停止数值推进”的规则，授权在同一冻结窗口和累计预算内定位、修复、定点复验并继续，不必再请求review。**

V31当时遵守了Review V28的一次前测合同，不能将其停止说成执行者擅自放弃；问题在于该合同把一个已定位fixture错误也变成了整轮停止条件。本次修正执行规则，不追溯改写V31失败或重开其closed账本。数值弱、输入身份失效、真实消费／资源耗尽仍有独立停止条件，不通过删除测试、降低容差或抹掉失败来“推进”。

[response_v31](response_v31.md)已正式回应[review v28](review_report_v28.md)，故按AGENTS §15顺延为v29。本轮只审阅并定点检查，没有修改求解源码、读取真实packet／因子、启动真实actor或大型实验；没有subagents或重置卡，没有修改dot、其他分支或master。

| 审阅身份／范围 | 独立核实与边界 |
|---|---|
| 精确远端／本地HEAD | `29278756f610c4ad1755fc82f37be17e06dc1699`；非交互ls-remote一致，起始工作树干净，无匹配Task042的actor／辅助worker |
| V31实际辅助source | `997397093f7061f7086b2088458d50c6ca773b7d`，历史110项运行绑定此提交 |
| V31最终实现source | `4734b22d1b9260b8500c32212e4e30b1c03f0507`；相对实际测试source仅改一份测试文件中的失败fixture，production路径字节不变；交付文档HEAD另列 |
| 分支／canonical worktree | `task42_neural_coarse_inverse`，`/home/fenics/Projects/NN-Lab`；common `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 增量与证据 | 53个变化文件；69个规范化路径、2,640,601 B hash核对，另对旧测试版本按997397提交核验；17文件编译／模块全局名称检查，原JUnit、gzip、CPU快照和18条资源样本交叉核对 |
| 历史完整性 | 58份旧review／response字节未改；四份导航／summary的历史后缀完整；沿原547文件索引及历轮增量继续核对，不声称全仓逐行语义审计 |
| 本次新增测试 | 只运行`test_failed_prequalification_stops_formal_route`：1 passed in0.89s；源码为被审阅HEAD，没有临时patch；没有重跑完整110项或真实study数值实验 |

[独立核验记录](outcomes/records/review_v29_independent_checks.json)保存脚本、原日志、hash、源差分、成本及存储守卫复核。GitHub rendered view与本地文档检查分别记录；不声称CI／全仓测试通过。

## 1. V31已经做成的事与本次关闭项

此前缺少`relative`导入，会在实际回流工作流计算抵消证书时崩溃。V31显式导入已有函数，没有改归一化或数学门槛；新增fixture实际调用study、生成证据、写出、结算并让collector读取，覆盖了该调用。其小算子只有16个活动维度，以18144 trace／40端口接口接线，没有制造巨大方阵。

| 内容 | 证据／结论 |
|---|---|
| study→保存→结算→collector | 历史JUnit中`test_actual_study_two_states_through_collector`通过；实际代码走过两个命名状态和抵消行，消费核对为合成S34/SH2、reader7、port35 |
| 失败路径与计费 | 合成reader拒绝后保留partial，真实结算函数将active清空；固定auxiliary summary按集合去重计费测试通过 |
| 旧namespace隔离 | V31单dat／plan、loader／worker／dispatcher／checker及窗口已接线；旧dat不重定向，closed／active／consumed拒绝测试通过 |
| 原前测失败 | 110个不同测试中109通过、1失败；失败fixture只提供TMP，loader绑定`require_live/ledger/auxiliary_wall`时出现AttributeError，尚未到预期InputError |
| 修复与新复验 | 4734b22d补齐三个接口，并使它们一旦调用便报错；本次定点测试通过，证明失败前测会在使用这些接口前被拒绝。不是绕过正式Gate |
| 资格表述 | 可以组合“历史109项通过＋修复差分仅影响一fixture＋本次该fixture通过”关闭局部问题；**不得改写成V31曾110/110，或本次全套110项重新通过** |

合成fixture明确替换了IO、readiness、因子文件receipt及reader，并将`stage.guard`置为空操作；实际代数、writer和计数链通过有意义，但它不资格化真实因子读盘、真实资源守卫或原三维算子。该边界不是再开一轮准备工作的理由：这些本来就要在有界真实诊断中验证。

| 原始资源／运行库存 | 本次重算 |
|---|---|
| V31准入 | 2026-10-03，唯一前测CPU11，候选11/14；原ticks、线程start及SMT决策重算一致；正式准入0、actor0、后checker0 |
| 监督 | WORKER_FAILED／exit1，12.731162693002261 s；pytest7.99 s和entry9.115107226 s嵌套，不重复收费；后代已清空 |
| 同时树采样峰 | 18条样本逐成员相加得到254,758,912 B、ownswap0；请求0.5s，实际间隔0.586–1.005s，只是采样峰 |
| V27起累计 | 52.68017605994828 s；600s中剩余547.3198239400517 s。actor、真实S/Sᴴ、reader、局部solve／LU／gecon／薄分解／FE／训练仍全0 |
| 窗口 | 10:00:29.125963 UTC开始，10:12:35.920648提前closed；交付观察elapsed1082.941415 s；V26–V30旧窗口／账本hash保持，V31也保持closed |
| 本次审阅复验 | 一次fresh准入、监督4.368644835 s，采样RSS114,909,184 B、swap0、后代清空；独立审阅费用另列，不倒填V31或清除历史费用 |
| 环境与完整成本 | V31独立native pure、NumPy1.26.4／SciPy1.11.4、MPI1/math1、三个BLAS getter1，无FE/JIT/Torch/GPU。历史formal研发下界77,161.557139 s与旧辅助／完整N=1 unknown保留 |

## 2. 同轮修复项：存储守卫与报告口径必须一致

[ReturnStage.guard](../../src/runners/return_block_diagnostic.py)的V31累计128MiB检查只扫描`tmp/v27*…v31*`和对应artifact目录，漏掉报告明确计入的`review_v24…`等审阅临时目录、新compact records及run results。按其原glob只读stat，本次得到58,748,742 B；仅漏掉的审阅目录就有52,621,180 B。V31最终库存已报告累计110,693,959 B，距离134,217,728 B上限只余23,523,769 B，不能再按“本轮32MiB上限”直接假定总量足够。

这不是实际超限结论，也不要求新容量实验。V32在准备过程中直接统一事前库存、运行守卫和结项账的路径清单，按规范化文件去重，包含本轮日志、records、results及约定审阅目录。用小临时文件做一项边界回归即可，**修复和通过后继续诊断，不把本项拆成等待下一review的阶段**。

两状态新数组的complex128净载荷可从源码形状推导为15,226,880 B（每状态15个trace向量、完整残差、J内向量、端口、至多10列Q、小R和系数）；这是derived，不含NPZ头、JSON、日志、TMP和写出峰。真实读取前必须留足这些额外空间。不需要复制旧factor／状态或再保存一套完整基。

允许清理**不被证据引用的字节码缓存和已经通过且无需复用的合成临时载荷**，记录清理清单；失败原始包、window／ledger、hash-bound证据和真实因子不得删除或改写。原始日志可无损压缩并保存未压缩hash与索引。存储准备应解决实际容量问题，不能通过漏计目录给Gate造PASS，也不为缓存膨胀反复新开实验编号。

## 3. V32主任务：完成一次真实两冷态方向诊断

唯一数学任务保持不变：先在联合区域J=[5,7]处理输入，再让外部六块处理其引起的不平衡，最后回到J补偿。它可能增加一个原九方向不包含、且能够消除剩余残差的响应；代价是七套已存因子的读取、三角解和原方程作用。

```math
q_J=B_Jr,\qquad w=L_OAq_J,\qquad
d=-w+B_JAw,\qquad q_{\rm ret}=q_J+d.
```

A始终是包含全部40端口闭合的原trace算子，L_O使用外块0/1/2/3/4/6。只处理V24-LZ-CYCLE4和V24-LCZ-CYCLE4，以V26九方向为基线；其历史eta9分别0.966205505618和0.981968429990。二者是zero-trace路线第四周期的已消费冷末态，不是新的零初值求解、warm-start或fresh泛化样本。q_J已在旧空间中，加入d与q_ret等价，不得分别试完择优。

V32至少应交付两状态的真实eta10、g10=eta10/eta9、新方向可分辨性、J内抵消、外部变化、原作用独立重组及完整消费／成本；如未能获得，必须具体指出实际资源、输入或数值障碍与已消费预算。**仅修完测试然后主动停下等待审阅，不满足本轮主任务。**

### 3.1 软件错误的修复权限：通过后自动继续

| 情况 | 本轮直接执行，不再请求review |
|---|---|
| fixture、导入、路径、schema、namespace、计费或writer错误 | 保存失败日志，定位根因，作最小修复，先重跑失败项及直接受影响测试；通过后继续正式诊断准备 |
| 同source历史测试可复用 | 用受影响文件／输入hash和差分说明哪些证据仍有效；无需因无关文档或局部fixture修复重跑110／162项。数值核或协议相关变化才重验相应anchor |
| 首个辅助测试失败 | 失败receipt保持不可变；同一V32窗口下给修复后尝试独立ID，全部监督秒数累加。不得通过删除`admission_attempt.json`或覆盖失败summary实现重试 |
| 前测准入标记／合格证明 | 改为引用当前实现有效的通过记录及其覆盖范围，同时关联此前失败；不能简单寻找任意旧PASS，不能继续硬编码“只允许第一次前测” |
| checker代码／序列化问题 | 在剩余预算内修复并只从既有hash-bound数组重跑checker；不重做原作用、factor solve或QR/SVD，不把原数值失配当writer问题 |
| 文档／元数据格式错误 | 局部修复、定点检查并完成交付，不触发真实实验重跑 |

每次复验必须对应明确修复或收窄后的诊断，不允许对相同失败盲目重复。**测试失败次数本身不作为停止条件**；停止由真实窗口／资源／累计预算或无法在既定数学范围内修复的障碍决定。测试和资源监督仍保留，不等于“忽略测试继续”。若只剩与本任务无关的已有文档失败，单独记录，不阻断已资格化数值路径。

V32复用V31的study、fixture、runner、watchdog、checker与`DiagnosticWindow`。优先对执行批次、输出与辅助attempt作最小显式参数化；稳定dispatcher若需要一个薄注册可以增加，但不得复制整套数值核、fixture或run脚本。旧V31默认和closed拒绝保持，V32使用新窗口／账本／路径，不把旧dat静默改指新窗口。

修复阶段允许必要的连续小提交；正式actor前源码必须clean且冻结完整SHA，合格测试绑定相关代码身份。全部真实工作经既有`python scripts/run_case.py <V32单个dat>`通道启动，不直接调用study绕过准入。主actor开始后的source不热改。

### 3.2 数值和真实消费合同不放宽

| 项目 | 验收／停止标准 |
|---|---|
| 固定物理／身份 | 0.7nm micro、384hex/p3/q15、18144 trace＋40port；原packet、材料、MPC、b、mode、两个parent／状态与V25/V26缓存逐名hash绑定；不新增warm、INITIAL或第三状态 |
| 因子 | J一次、六外块各一次，共7 reader；外块逐个加载后处理两状态并释放；不读旧5/7 LU，不新装配／LU／gecon或全局矩阵 |
| 因子见证 | 固定J种子422601/422602，外块b种子422401+2b、422402+2b；solve相对≤1e-8、operation≤1e-12，原主块／J伴随作用配对≤1e-10；失效即停止依赖计算，不fallback |
| 完整实际消费 | S34＋Sᴴ2=36，J solve4、外域solve24、L/U pass56、reader7、薄流程2、port factor1／单列solve35；ledger／manifest／结果独立对齐，合成计数不得冒充实际 |
| 保守硬上限 | S＋Sᴴ≤64、J≤8、外域≤24、pass≤64、薄流程≤2且≤10列、port factor≤1／solve及RHS列≤128；余量不授权新状态或方法，偏差不得靠修改checker EXPECTED自动放行 |
| 九→十方向 | 固定列均衡、QR＋小GELSD／cond=1e-12，同一分解给九方向基线；创新>64eps原操作尺度、相对Ad>1e-12且rank10才称可分辨；零、近零、重复和beta=0合法分类 |
| 原作用资格 | 状态／缓存差/b≤1e-11、端口≤1e-10；J内抵消operation≤1e-10；独立完整重组差/b≤1e-11、operation≤1e-10并列差/r；QR／正交≤1e-10、驻点≤1e-8、eta10≤eta9+1e-10 |
| 不授权 | B_full真实apply、完整迭代、增加回流次数／顺序／块对／tau，旧p1 T/U/R／Krylov／REF7／teacher／权重、新FE恢复／新场／official R/T/A或训练 |

上述完整构造与资格细节仍按[Review V24 §5](review_report_v24.md#5-v27唯一任务验收与停止)和[Review V28 §4.2](review_report_v28.md#42-真实消费数值gate与成本)，但辅助重试与窗口规则以本报告为准。

### 3.3 预算按剩余额度执行，不再机械卡在一次测试

| 项目 | V32合同 |
|---|---|
| 总窗口 | 首次工作冻结UTC／monotonic／boot_id；elapsed≤5400s，start+4500s停止有载，最后900s收口；实现、等待、修复、hash、测试、发布全计入，不刷新 |
| 累计有载 | 继承52.68017605994828s，V27起actor＋全部受监督辅助仍≤600s；本轮剩余547.3198239400517s，不重新给600s；审阅费用单列 |
| 辅助修复额度 | 本轮前测／定点复验／后checker合计≤90s，其中正式actor前辅助≤70s，预留最多20s给后checker；这只是同一600s余额内重分配，不增加真实数学预算。每次尝试都受监督、保留source与独立receipt并计费 |
| actor时长 | 只允许一个真实数值actor，监督上限取`min(480s, 600s−已累计有载−20s后审核预留−10s清场余量, 有载截止start+4500s之前的剩余时间)`；预算不足不启动。已累计包括carry及全部本轮失败尝试；不能侵占最后900s交付窗口 |
| 启动与停止 | 软件修复后的辅助可重新fresh准入，不受旧“一次前测”限制；CPU／SMT／内存／PSI规则不变。资源准入拒绝不反复采样找核或后台排队；正式actor仅一次准入。actor一旦启动本轮不再启动第二个，以免重读因子、重复消费或掩盖负结果 |
| 资源 | actor事前derived同时规划≤8GiB，整树warn12／hard16GiB；辅助warn1／hard2GiB；请求0.5s采样、ownswap0。实际采样间隔和峰口径另报，不称kernel硬限制 |
| 共享环境 | native Task042 pure、MPI1/math1、原生BLAS getter验证，独立cache与`PYTHONDONTWRITEBYTECODE=1`，无FE/JIT/Torch/GPU/OOC；自有锁、5%／SMT、reserve=max(128GiB,10%effective total)、邻增长128GiB及本任务16GiB余量、PSI规则保持，不干预邻任务 |
| 存储 | 本轮新输出含TMP≤32MiB且受**剩余累计额度**约束；V27起含约定review目录／records／results累计≤128MiB，全Task artifact≤20GiB、自由盘≥50GiB。按§2统一库存、事前分配数组／日志／测试空间和安全余量；32MiB不是追加到剩余额度上的许可 |
| 权限与闭环 | 同一canonical task42分支；不使用subagents／重置卡，不改dot、其他分支或master。保留旧closed和全部失败；最终结算active=null、closed、后代清空，提交推送后等review，不merge |

如果正式actor在真实消费后出现代码错误，不以用户要求推进为由无记录重启；先完成可做的静态修复及已有数组分析，准确交付已消费／未运行。这是保护不可重复真实预算，与前测fixture失败可修可续不同。资源或数值Gate未通过也必须停止受影响数值工作；有剩余时间应完成证据、归因及替代分析，不能无信息地等待。

## 4. 真实结果到手后怎样决定，而不是再开测试轮

| 所有身份／因子／数值／消费／checker通过后的两态结果 | 必须交付的决定 |
|---|---|
| 创新均可分辨且g10≤0.75 | `RETURN_EXTRA_DIRECTION_SIGNAL`；相对e9剩余范数再降至少25%的有限信号，列平方范数消除和完整费用；只提出后续全空间／成本方案，不自动训练或迭代 |
| 两态g10≥0.95或均不可分辨 | 关闭固定J→外域→J单轮提案；不加回流次数、换顺序、换块、调tau或延长旧预算 |
| 混合／中间值 | `STATE_DEPENDENT_INCONCLUSIVE`，保留两态实际值，不加第三状态投票，不称fresh泛化 |
| 真残差重组、因子、计数或身份不合格 | 分别标记数值未分辨、输入失效、partial或资源停止；明确失败量、实际值和限值，不输出可信的整体增益 |

失败后的有效分析应利用保存向量回答：内部抵消是否成立，外部不平衡是否下降，新响应是否重复旧空间，创新与e9是否对准，以及大系数／相消或资格成本是否消除了实用价值。checker只能读缓存重算，不能为分析再作原作用、factor solve或新QR/SVD。

B_ret仅依赖J内3888个输入分量，rank≤3888<18144，不能独立充当全空间右PC。V30验证的B_full增加外域输入通路，其代数可逆不保证收敛，固定2×2反例已有残差放大6倍；真实B_full仍NOT_RUN。B_ret失败不能否定该未运行补项，也不能自动授权它。若没有不同信息传播机制及完整费用依据，就结束固定局部方向序列，等待dot的参考／规模证据，不再换同p1测试或学同空间系数。

成本必须列本轮冷加载、资格见证、实际方向、原作用、端口、薄代数、独立checker和IO；嵌套timer不相加。七套A＋LU载荷1,591,420,032 B不是同时RSS，历史构建／factor、mmap页、hash扫描、pivot与LAPACK副本不能免费化。N=1暖启动链与最佳合格非神经全流程仍unknown，不能把本次诊断耗时当成功单解时间。

## 5. 交付、历史去重与未资格化目标

V32交付`response_v32.md`、两态结果／失败分析、独立checker及原始索引；每次辅助失败与修复记录、最终source、命令、环境／ABI、完整计数、同时峰和全程成本、window／ledger／清场必须可追溯。同步README、summary、test_summary、changed_files，真实诊断或资源停止同步模型总账和development_progress。不要再新建一个“测试准备已完成、请review后才运行”的平行任务书。

| 历史路线 | 去重结论；本次不重跑 |
|---|---|
| V1–V5 13.5nm p4神经粗逆 | 已关闭，不重新解锁旧F5／p6 |
| V6–V15 神经FE trace／固定特征 | 实际训练、hidden更新、固定特征／仅头部拟合分开；没有训练的传统结果不是NN收益，未运行hidden项不改名为新结果 |
| V16–V21 全空间校正／ILU0／class64 | 残差或算子速度改善未给完整物理资格；不延长旧迭代预算 |
| V22–V23 Galerkin／image-QR | 表示误差与可消除残差不同；同p1空间换测试／tau不重复，V23完整0/6 |
| V24 八局部LU／image-coarse组合 | warm／zero四路及overlap已执行，完整0/5，不再作为未运行路线 |
| V25／V26 八方向／联合方向 | eta8约0.983237／0.989925，联合对e8额外范数下降1.732185%／0.803718%，固定提案关闭 |
| V27–V31 回流准备 | 真实两态eta10／g10仍NOT_RUN；V30轻量已资格、V31study接线通过，本次修复fixture复验通过。没有新的数学正／负结果 |

完整历史沿[Review V21](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、[V22](review_report_v22.md)、[V23](review_report_v23.md)、[V24](review_report_v24.md)、[V25](review_report_v25.md)、[V26](review_report_v26.md)、[V27](review_report_v27.md)、[V28](review_report_v28.md)与[原547文件索引](outcomes/records/independent_review_v21_20261002.json)串联。本次是其后的53文件增量审阅，不将旧结论当新测量。

原目标仍是50×25nm周期、z=-10..130nm原尺寸、0.7nm、完整非可分三维有限元，同时峰≤2e12 B、端到端≤172800s。当前micro仅1.4×1.05×1.4nm。V23 warm Schur约2.507714e-6／zero约0.06811318且逐通道功率超限；V24 LW4 Schur2.502117907e-6／功率差1.666968717e-6均超1e-6，LZ4 Schur0.0813766679／散射E差0.568888278／功率差0.007245974超1e-6／1e-4／1e-6。native单项、测试通过或一次方向改善均不改变0/6、0/5和原尺寸`NOT_QUALIFIED`。

局部稠密A/LU的32Σn_b²存储／Σn_b³设置，全局image基16nr、R的16r²与QR的nr²工作仍计真实生命周期。神经增益标准保持**同正确性、相对最佳合格非神经N=1路线，完整时间或同时峰至少降低20%，另一项仍合规**，包含数据／训练／加载／推理／精确修正／审核／IO，不默认摊销；不能沿用早期10%。V26薄LS仅0.008964091s、约该诊断actor0.026949%，学习同空间系数既不能超越精确最小残差，也没有20%完整成本证据。

dot继续`task40extra_dot_parallel_cloud`的完整三维参考逆、周期分块、共享存储和规模验证；本任务只补有限方向机制及神经独立增益评估，不复制其完整求解器实验或修改其分支。原尺寸精度／fresh泛化／2TB／48h仍未资格化，NN20%仍`NOT_DEMONSTRATED`；**无merge approval**。
