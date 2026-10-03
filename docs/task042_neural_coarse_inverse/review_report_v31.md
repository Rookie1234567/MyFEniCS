# Review V31：修复两个已复现的软件问题，同轮完成完整输入诊断

## 0. 决定：下一交付必须推进到数值判断

**接受V33如实记录的CPU资源停止，不授予实现运行资格。V34直接执行“修复—定点复验—原两态B_full诊断—独立缓存审核—归因及完整费用”，不再设置“先交测试结果、等待review才运行”的中间审批。** 本次已复现两个软件问题并验证其中一个最小修复方向；它们不是算法的数值负结果。

用户本轮明确要求“没有数值gate不允许停止等待审阅，遇到bug自己想办法修复”。据此，本报告覆盖[Review V30](review_report_v30.md) §4.4的“一次资源拒绝即关闭”和“已有任何真实消费即禁止修复重入”，也覆盖[response_v33](response_v33.md)末尾再次等待运行授权的建议。**测试失败、代码写完、静态编译通过、一次暂时CPU拒绝，均不是本轮等待review的理由。** 已授权范围内自行定位和修复；真实资源不可用时无载等待或保存可续作状态，不越过资源门、不冒造数值结果、不将障碍变成新的审批轮次。

response_v33已经正式回应review_v30，符合AGENTS §15的新一轮条件，故新建v31；历史review、response、负结果和closed账本均保留。本次只审阅和写报告，没有修改求解源码、启动真实actor/PDE或训练，没有使用subagents或重置卡。

## 1. 审阅身份、证据和实测边界

| 项目 | 本次独立核实 |
|---|---|
| 精确远端／本地交付HEAD | `177ce7c645f14cedea65e8f309ed2c33b65978ed`，非交互ls-remote一致；起始工作树干净 |
| 最终实现／原准入source | `a874498a1a8b854f394520627eaf09158b77fbf9`／`45d34165ea1208830edc7de1c71360a57c5b9dba`；V33实际数值source仍null |
| 分支／canonical worktree／base | `task42_neural_coarse_inverse`／`/home/fenics/Projects/NN-Lab`／`ccd357885f7f9be84efe3be07868cc94f13d93fc`；没有切换或修改其他分支 |
| 现场 | 宿主进程核对未见本任务actor或辅助worker；Task39、Task41和Metrology邻任务存在，未操作。相似task42extra分支／进程不算本任务 |
| 增量／历史 | 相对review_v30的68文件增量；16个改动Python静态编译；309个元数据／源码／历史文件、5,424,205 B hash核对；254份受保护材料与前review提交逐字一致，其中旧review/response共62份；四份任务导航／summary保留历史后缀 |
| 原始记录 | 8份gzip与原始文件逐字一致；V33 CPU ticks、线程增量、亲和性及SMT逐核重算与原拒绝一致；V26–V32的14份closed文件不变，V33 closed且active=null、runs为空 |
| 本次新合成复验 | 原样运行`test_task042_v33_workflow.py`：**4 passed / 2 failed**；监督6.665362164s、同时树采样峰187,076,608 B、自身swap0、后代清空 |
| 隔离根因验证 | 仅在审阅进程的独立命名空间修改checker函数文本，读取上述合成fixture；两态重算通过、12个破坏性反例拒绝。监督3.051327008s、采样峰102,936,576 B、自身swap0。不是仓库已修复或完整前测通过 |
| 环境／范围 | Task042 native pure、仓库`.venv`、NumPy1.26.4/SciPy1.11.4、实际BLAS getter均1；无真实因子读取、真实原作用、真实solve、FE或训练。合成fixture内的小矩阵动作不冒称真实算例消费 |

[独立检查及隔离脚本](outcomes/records/review_v31_independent_checks.json)、[原测试日志](outcomes/records/review_v31_tests.log.gz)、[JUnit](outcomes/records/review_v31_tests.junit.xml.gz)、[审阅准入](outcomes/records/review_v31_admission.json.gz)及[隔离验证准入](outcomes/records/review_v31_isolation.admission.json.gz)保留原始身份。两次review监督费用合计9.716689172s，分阶段RSS取最大，不相加；没有内核cgroup硬限或绝对零邻任务影响声明。

审阅沿此前全部历史核对和完整检索索引继续，对增量及相关核心深入检查；这不等于全仓每个文件逐行语义审计。GitHub页面抓取Cache miss，rendered view为NOT_VERIFIED；本地文档合同与链接检查另列，不声称CI通过。

## 2. V33实际结论及两个需要同轮解决的问题

### 2.1 资源拒绝属实，不能推出B_full无效

V33唯一准入发生于2026-10-03 11:55:15.696876–11:55:16.937154 UTC，48个CPU候选均因原忙碌／线程亲和性／SMT规则排除。原始逐核决定可重算；其他MEMORY、DISK、PSI及CGROUP_GPU_SNAPSHOT门均NOT_CHECKED。没有前测worker、正式actor或数组checker。11:59:14.792939 UTC提前closed符合当时review_v30，不能追责为擅自停止。

V33 carry仍151.4889468078036s，受监督新增0，probe1.240282989s计原总elapsed；完整launcher独占成本仍unknown。两态rho_full/rho0/rho_ret/外域隔离比都应保留null。V33的483,729,408 B J矩阵加LU载荷、4,246,745,088 B同时规划和10,577,920 B输出净载荷均为derived，不能以worker未运行获得“零成本加速”。证据见[费用](outcomes/records/resource_costs_v33.json)、[原始索引](outcomes/records/raw_evidence_index_v33.json)、[实际消费](outcomes/records/actual_consumption_v33.json)。

### 2.2 P1：checker混用了两种残差身份

有限精度下，同一残差经不同但等价的运算顺序重算，末位可能不同。真正要检验的是差值是否满足原数值限值，以及后续所有指标是否使用同一个已审核向量，不能额外要求逐位一致。

实际[study](../../src/solvers/full_input_block_study.py)第118–138行保存新算的`r=barb-bar.apply(t)`为`input_residual`，并以它计算指标。[checker](../../benchmarks/task042_full_input_checker.py)第29–47行先调用`state_certificate`验证新旧残差差/b≤1e-11，随后却以历史`state['residual']`为r，再要求`np.array_equal(input_residual,r)`；两种合同冲突，合法舍入差就能阻止完整审核。

| 原样合成输入；不是实际micro结果 | 新旧残差差范数 | 差/完整b | 原限值／原checker结果 |
|---|---:|---:|---|
| fixture的LZ4 | 5.7688880592e-16 | 9.4251309697e-17 | ≤1e-11；仍因逐位不等拒绝 |
| fixture的LCZ4 | 1.1999271755e-15 | 1.9604247243e-16 | ≤1e-11；仍因逐位不等拒绝 |

已隔离验证的修复方向：通过`state_certificate`后，checker以保存且已审核的`a['input_residual']`统一计算rn、rho、J_rhs和外域隔离比；历史残差仍用于原阈值配对，不删除来源审核。缓存方向、单位系数构造、hash、支持范围等本来应精确相同的项继续精确验证。**不是把所有array_equal替换成allclose，也不是改actor输出凑checker。** 增加接近门限两侧的残差反例、非有限值和错误来源反例；小误差可接受，超过原门限必须拒绝。生产修复后的实际完整前测仍由V34执行，本次隔离验证不签发其资格。

### 2.3 P2：存储fixture期待值与既有范围不符

[新测试](../../src/test/test_task042_v33_workflow.py)第95–105行创建四个5B文件，断言V33累计20B、新增10B正确，但又断言V32累计0。既有[范围函数](../../src/runners/diagnostic_storage.py)将`records/review_v30_test.json`按27≤version≤32计入，实际为5B；这条规则在V32已经存在。应把fixture改为显式断言那一个5B成员以及三个不应计入的成员，并保留V33的20/10结果。不能为了让测试过而删掉已有存储覆盖、改旧快照或扩大128MiB门限。

V34还需把自身及review_v31完整纳入**同一**事前/live/结项范围。V33交付累计114,818,852 B、余19,398,876 B；本次review新增失败合成fixture约13MB，不能当免费空间遗漏。先清理未被证据引用的pyc，或对合成失败载荷无损归档并保留逐名hash、原路径及还原方式，重新统计后预留至少原14MiB输出加新增日志开销。保留失败证据、真实数组、因子和closed账本；不得到checker写出时才发现空间不够。

## 3. 历史去重与这次诊断能增加的信息

| 路线／历史入口 | 已有结论与本轮限制 |
|---|---|
| V1–V5：13.5nm p4神经粗逆 | 已关闭，不重开旧F5/p6，不把后来的块方法收益归给这条神经路线 |
| V6–V15：神经FE trace、hidden／固定特征 | 有训练的网络、仅拟合头部、未训练的固定基分别评价；未运行hidden不补写为成功或失败 |
| V16–V21：全空间LSQR／校正、ILU0／class64 | 原残差和物理资格未闭环；算子作用变快与收敛改善分开，不延长旧预算 |
| V22–V23：Galerkin／image-QR | 同p1空间换测试、scalar-tau不再重复；完整0/6，原始全局QR与上游成本保留 |
| V24：八个几何非重叠原p3块LU、加image-coarse | warm、zero-trace和组合overlap已经运行，完整0/5；不能再把V24写成未执行计划或重跑一遍 |
| V25–V26：八方向和J=[5,7]联合方向 | 误差空间能表示不等于原作用像可消除残差；固定方向提案弱收益并已关闭，保存数组仅作已消费输入 |
| V27–V31：回流准备、资源停止、软件修复、小矩阵 | 准备／合成资格与真实数值结果分开；历史失败保留，不重复全套准备验收 |
| V32：B_ret真实回流 | 两态g10=.998590612859/.998709002549，只再降低剩余范数约0.14094%/0.12910%，固定回流方向已关闭；不能添加第11个拟合方向 |
| V33：B_full完整输入 | 仅实现，原两态从未运行；本review新增的是软件失败证据和隔离修复依据，**没有新增真实B_full数值** |

完整历史依据为[Review V21去重清单](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、[全历史索引](outcomes/records/independent_review_v21_20261002.json)及随后各轮原始记录。上表延续历史结论，不把它们当本次实测。

“回流”先处理联合块J中的残差，再沿外部六块返回J；旧B_ret完全漏掉外部本身的残差输入。B_full补上这个入口，可能产生更有用的修正，也可能因反馈放大而更差。代价是传播和局部求解；它是传统块方法，没有网络训练。设A为原完整40端口闭合的trace算子，B_J是J主块逆注回全空间，L_O是外部0/1/2/3/4/6六个主块逆之和：

```math
B_{\rm ret}=B_J-(I-B_JA)L_OAB_J,\qquad
B_{\rm full}=B_J+(I-B_JA)L_O(I-AB_J).
```

```math
u=L_Or,\quad k=B_JAu,\quad \delta=u-k,\quad
q_{\rm full}=q_{\rm ret}+\delta,\quad q_0=q_J+u.
```

补项`B_full−B_ret=(I−B_JA)L_O`此前真实未测，值得把这一次诊断完成。q0是相同七区域、单位系数的公平对照。B_ret负结果不否定该补项；B_full满秩也不保证收敛，既有2×2反例可使原残差放大6倍。V34只检验固定两输入的单步效力，不能从中授予任意RHS PC、Krylov、warm、新zero-start、NN或原尺寸资格。

## 4. V34连续执行合同

### 4.1 修复与运行直接连起来

1. 核对最新本分支、exact task actor、环境和存储；建立V34独立批次及预登记，不重开V26–V33 closed窗口。plan/ledger/results/checker输出均落V34，参数化现有checker的V33路径限制及输出名，不能覆盖历史NOT_RUN记录。复用当前数学内核和通用runner，以薄接线／参数扩展，不能复制一套求解器、fixture或checker。
2. 修复§2的两项；实现下面的暂时资源等待和收费修复重入。特别检查`allow_entry_repair`、辅助launcher的永久rejection marker、loader的runs拒绝、checker的`len(consuming)==1`与`ledger.charged==EXPECTED`：这些旧判断不能阻断已授权修复，也不能简单删除后失去计费。旧V33默认／closed行为保持。
3. 最小复验实际study→保存→结算→checker；覆盖新旧残差容差、差式/J抵消、非互伴完整端口、外域-only、零输入、奇异拒绝、列错位和语义破坏。继承V33默认相关范围及本次新增修复／重入反例；不机械重跑110/162项或全仓pytest。失败自行定位，最小修复后重验受影响范围，不能以第一次失败结束。
4. 正式运行source提交且clean，资格绑定相关文件hash和真实覆盖项；通过后**自动继续**`python scripts/run_case.py <V34唯一dat>`，执行下面固定两态。不得拿本review的4/6或隔离修改代替正式资格；前测通过也不能作为交付终点。
5. 原始结果保存后自动执行只读cached checker及归因。checker或写出bug优先用已完成数组修复复验，**不重跑成功actor**。完成可信正／负／状态依赖判断后，统一交付response_v34及证据，再进行集中审阅。

### 4.2 固定数学、可信度及数值判定

沿用review_v30 §4.2的精确物理／action／state／cache身份：0.7nm micro、384hex/p3/q15、18144 trace＋40port，仅`V24-LZ-CYCLE4`和`V24-LCZ-CYCLE4`，不加INITIAL、warm、第三状态、teacher或参考场。u是V25六块原修正的单位权重和，不能使用拟合后的系数。仅重载一套V26 J因子，不加载外部六套LU或旧5/7因子。

| 固定流程 | 必须保留的审核 |
|---|---|
| J资格一次 | 原种子422601/422602、两solve和原主块／伴随配对；solve相对≤1e-8、operation≤1e-12、作用配对≤1e-10；无新assembly/LU/gecon |
| 每态输入 | 完整state/z/端口重闭合及原b身份；新旧trace／full residual差/b≤1e-11，端口门≤1e-10；新旧r同时保存，指标明确统一用已审核的新r |
| 每态真实作用 | Au、Ak、Aδ、Aq_ret、Aq_full、Aq0六次；一次新J反馈solve；缓存Au与Aq_ret只作配对，不充当全部新的原作用 |
| 重组与抵消 | δ=u−k、q_full=q_ret+δ、q0=q_J+u；J内Aδ≈0、Aq_full≈r_J；每个配对同时差/b≤1e-11和operation≤1e-10，另列差/当前r；尺度来自抵消前实际操作数 |
| 外域拆分 | r_O把J置零，用已保存δ/Aδ计算norm(r_O−Aδ)/norm(r_O)；零分母NOT_APPLICABLE，无第三样本或新A作用 |

定义rho_full=norm(r−Aq_full)/norm(r)，rho0=norm(r−Aq0)/norm(r)，同时保存rho_ret。先确认输入、因子、原作用、消费和独立checker可信，再按预登记判定：

| 两态结果 | 数值Gate及后续动作 |
|---|---|
| 均rho_full≤0.75，rho0>0且rho_full≤0.8rho0 | `FULL_INPUT_SINGLE_STEP_SIGNAL`；可以提交有完整成本的下一求解设计，但本轮不自动启动Krylov／训练 |
| 均rho_full≥0.95，或均rho_full≥rho0−1e-10 | `FULL_INPUT_FIXED_STEP_INSUFFICIENT`；关闭这个固定未阻尼单步提案，不通过换系数／次序／样本追信号 |
| 其余可信完整两态 | `STATE_DEPENDENT_INCONCLUSIVE`；报告实际值、差异原因，不追加第三态投票 |
| 原数值可信度门实质失败 | 先排查软件、单位、分母、来源和审核接线；可修复就修。确认正确实现仍违反原门，保存实际误差／尺度／限值，才给`NUMERICALLY_UNRESOLVED`，不放宽阈值 |

普通异常不是上述数值Gate。软件修好前不能以“checker失败”关闭算法。资源／输入不可得时指标null、执行未完成；rho0=0不授予相对改善。这里的20%只是传统单步筛选，不等于神经增益20%。

### 4.3 允许收费修复，禁止换算法或隐去失败成本

下表把**一个成功完整actor的预期**与**包括失败修复的累计容量**分开，解决旧合同无法在有消费后修bug的问题。三个factor/readers的余量只供同一代码问题的必要重启，不是三种算法、参数扫描或三个有效结果挑最好。

| 计数 | 一个完整成功actor预期 | V34所有真实尝试累计硬上限 |
|---|---:|---:|
| 原作用S＋SH | 20＋2＝22 | 96，逐次区分S/SH |
| J reader／J solve RHS列／显式L/U pass | 1／4／8 | 3／12／24 |
| 40×40 port factor／solve／RHS列 | 1／21／21 | 3／96／96；所有试图构建也收费 |
| 外域reader/solve、新局部assembly/LU/gecon | 0 | 0 |
| QR/SVD/薄LS、新迭代、新FE/场、训练 | 0 | 0 |

完整尝试内部仍用原32作用／32port限值。每次失败保留attempt ID、source、日志、计数上下界和后代清空证明；不确定消费按write-ahead上界收费。只允许一个**有效完整结果**，完整成功run自身EXPECTED=22等预登记数，累计ledger应等于各次已结算charge之和；存在失败run时不能再要求累计ledger等于单次EXPECTED。独立checker必须验证两层账、失败原始来源、最终run和manifest一致，不接受把EXPECTED事后改成实际值。

在至少一个真实动作后发生可定位软件错误，允许最小修复、定点复验、冻结新source后重启同一固定诊断；前提是旧树已清空且累计时间／计数／存储足够。若已保存完整有效数组，只修元数据／checker并重放审核。不得用重入来重做已经可信的弱收益结果，不增加数学动作以“利用剩余预算”。

### 4.4 资源等待与预算，不再用瞬时拒绝制造review循环

| 项目 | 本轮规则 |
|---|---|
| 累计有载 | 原V27起151.4889468078036s不改；本次review辅助9.716689172084443s另保留并**保守并入下一预算**，V34起carry=161.20563597988803s，600s余438.79436402011197s。合成review计数不混入真实actor计数 |
| actor时间 | 单次≤180s，所有真实尝试合计≤300s；同时受600s余量、计数与截止限制，预留后checker20s及清场10s。不能把180s按重启次数无限追加 |
| 辅助／探针 | 前测及修复合计≤70s，后checker≤20s；合计≤90s并计600s。新准入探针实际累计≤20s，也计600s且与supervised时段去重。所有失败收费，不清零旧账 |
| 等待窗口 | **本轮改为一个固定24h总日历窗口，有载截止start+23h，最后1h用于无载交付**；首次工作记录UTC/monotonic/boot_id。只放宽资源等待的日历安排，不增加600s计算预算、数学样本或迭代。等待／实现／修复／发布总elapsed均显示，不伪称纯solver时间；旧V33窗口保持closed |
| 暂时准入失败 | 保存不可变receipt，状态`RESOURCE_WAIT`，释放自己的锁；不写永久禁止后续准入的标记。无载工作继续；同原因从至少120s退避至最多1800s再fresh检查，不密集找核、不持锁睡眠，不动邻任务。一次拒绝不结束阶段，不请求新review |
| 运行中资源停止 | 终止自身完整进程组、结算上界、保留已写结果；确认资源恢复后依同一授权和余量续作。环境、路径、缓存、计费bug同轮修复；输入身份错误先查找／修复指针，真实文件丢失或hash损坏不猜造替代数据 |
| 确实耗尽／不可恢复 | 到日历截止、600s／计数硬上限，或确认无有效输入，只停止依赖的有载工作，标明`RESOURCE_DEFERRED`／`INPUT_UNAVAILABLE`和精确剩余状态，完成无载归因及可恢复入口；**不得改成“数值失败，等待review批准重试”**。硬预算不可自行刷新；没有数值Gate就仍是未完成，不能结项批准 |
| 现场门不变 | 原CPU/SMT 5%／亲和性、内存reserve／邻增长128GiB＋Task16GiB余量、PSI、自身swap0及磁盘门不变。每个实际worker都fresh准入、MPI1/math1/BLAS getter1、native pure独立cache禁pyc，无Torch/GPU/FE/JIT/OOC |
| 内存／存储 | derived同时≤8GiB；actor warn12/hard16GiB、aux warn1/hard2GiB、请求0.5s整树采样；新批含TMP≤32MiB、累计含review≤128MiB、artifact≤20GiB、自由盘≥50GiB；stat-only事前/live/结项同口径 |

上述预算足以容纳原单reader短诊断以及有限修复，不是成功时间预测。没有CPU时不可把大hash扫描、数组检查或小矩阵运算偷偷改名为无载工作；无载工作限静态源码／小元数据／文档／费用模型。进度更新应说明当前阶段和下一次现场判断，不能让用户把安静等待误认为死锁，也不另起未授权后台服务。

## 5. 诊断失败后的有效分析与dot互补

单步校正失败后，仍应利用保存的向量回答具体问题，不只是写FAIL：

| 已有向量可完成的分析 | 需要解释什么；不新增A／solve／QR |
|---|---|
| J与外域残差分区 | J内是否确实消除，剩余主要在哪些原块；同时列范数及占原r的比例 |
| u、k、q_ret响应范数与复内积 | 外域输入补项方向错误、被反馈抵消，还是q_ret与补项相互放大；幅度变大不能单独当作残差改善 |
| rho_full/rho0/rho_ret及外域隔离比 | 顺序反馈是否优于同七区域直接对照；保持固定单位系数，不能混用V25 eta8/V32 eta10最优投影 |
| 在线费用还原 | 缓存诊断省掉的六reader和旧方向生成在任意RHS部署时必须回来：J两解、外域六解、两次A传播，另加端口、true residual、恢复与审核；原LU构建／IO／同时驻留不免费 |
| 有限结论 | 单步负结果关闭固定提案；所有B_full预条件Krylov继续NOT_RUN，不能据此证明其必失败，也不能自动开跑。正结果同样只有这两个已消费冷末态的证据 |

若没有可信数值结果，做静态调用／生命周期和输入缺口分析，不能用合成rho填实际表。若得到可信负结果，下一有效替代是基于上述区域耦合证据提出**不同信息来源**的候选，并先列完整内存／作用成本；不能回到同p1、tau、旧预算延长或第11方向。完整三维参考逆、周期分块、共享存储和规模验证继续由dot承担，Task042不再做一套同求解器实验。

本次只读核实dot最新SHA为`3c7458fad7c002babac4e634be4788b664be9ee5`，取得该对象但未更新dot分支／工作树。相对V33使用的98084c70，新发布[分块compact q投影](https://github.com/Rookie1234567/MyFEniCS/blob/3c7458fad7c002babac4e634be4788b664be9ee5/docs/task40extra_dot_parallel_cloud/outcomes/bounded_projection_candidate_v1_zh.md)：53项新合成测试、相关94 passed/4 skipped/1 deselected，只证明显式数组构造路径；未做新FE/PDE，process-tree RSS及真实求解性能未测。它不提供可直接移植的合格Task042参考逆，也不是NN收益。本review只读文档／差异，不代替dot独立数值审查。

V34沿[14项接口身份表](outcomes/records/dot_identity_gap_v33.json)只更新受新证据影响项：geometry/material/wavelength/mesh/p/quadrature/MPC/rows/modes/ports/RHS/action/recovery/cost。dot p4/120cells/532ports与本任务p3/384hex/40ports仍不能共享同正确性性能分母。未知保持unknown，不为凑表读取其大型因子，不等待dot才能做本轮两态诊断。

神经方向只做必要条件判断：同空间精确最小残差系数已经是该空间的最优，预测系数不会增加表达能力；V32薄代数0.023845749s仅占actor83.140184552s的0.0286814%，不能据此许诺20%完整耗时收益。若候选改为替代LU或构造更有效表示，应列出可省构建／加载／驻留、增加的数据／训练／推理／精确修正与审核费用，以及所需独立样本；本轮不训练。传统B_full即便过Gate，也不叫神经增益。

## 6. 交付、物理门与原尺寸边界

V34必须提供逐尝试source/环境/命令/失败日志/计数上下界、最终两态原向量hash、独立checker、修复复验、完整费用、存储和后代清空证明。response、summary、test_summary、changed_files、run index同步；实际诊断或资源停止同步模型总账及development_progress。测试修复和真实运行在同一执行批次连续进行，不再提交“测试已完成，请批准运行”的中间response。测试或软件缺口没有数值结论时保持执行未完成；可信数值Gate后的交付才进入集中review。只提交并推送本分支，不merge/master，不改dot。

| 原物理资格；历史实测，不是V34新结果 | 残差／关键物理误差 | 门限与结论 |
|---|---|---|
| V23 warm M-FINAL | Schur2.50771436526e-6；native9.72501113856e-7；最大逐通道功率差1.69973146436e-6 | Schur／功率各≤1e-6未通过；native单项通过不授予完整资格 |
| V23 zero Z-FINAL | Schur0.068113177161；散射E差0.989143298805；通道功率差0.00910569035662 | 分别超过1e-6／1e-4／1e-6；完整0/6保持 |
| V24 LW4／LZ4 | warm Schur2.502117907e-6、功率差1.666968717e-6；zero Schur0.0813766679、E差0.568888278、功率差0.007245974 | 完整0/5保持；单次校正有效不等于完整求解成功 |
| V34计划 | 原两冷末态固定单步诊断，无新完整场或官方R/T/A | 不能升级fresh zero-start、warm或完整物理解资格 |

最终目标仍为原50×25nm、z=−10..130nm、λ0.7nm、完整非可分三维有限元，**同时峰≤2e12 B、完整耗时≤172800s**；当前1.4×1.05×1.4nm micro不能替代它。误差表示、实际残差消除、算子加速、求解收敛、物理完整性和规模资格分别列项；局部LU和全局QR按完整生命周期计价。

**神经网络增益的唯一现行合同：同正确性下，相对最佳合格非神经路线，完整N=1耗时或同时峰至少改善20%，另一项仍合规；包括数据、训练、setup、加载、推理、精确修正、审核与IO，不默认摊销。早期10%条款不再使用。** 原尺寸精度／2TB／48h仍NOT_QUALIFIED，神经20%仍NOT_DEMONSTRATED，本报告无merge approval。
