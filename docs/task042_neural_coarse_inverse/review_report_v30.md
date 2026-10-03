# Review V30：接受V32负结果，执行一次外域输入补齐诊断

## 0. 审阅决定与下一轮主交付

**接受V32的真实两态回流负结果，关闭固定B_ret方向提案。V33不再重复测试准备，也不以等待dot作为全部后续工作；本报告明确授权一次此前未运行的B_full外域输入补齐诊断，随后自动完成缓存审核、失败归因和成本判断。** 普通测试、导入、路径、序列化、资格接线错误继续按“定位—最小修复—定点复验—继续”处理，不因首次失败请求新review。真实资源、输入身份、数值可信度和消费预算仍是硬边界。

[response_v32](response_v32.md)已正式回应[Review V29](review_report_v29.md)，因此按AGENTS §15顺延v30，旧报告不改。V32确实做到了同轮推进：后checker首次因输出预留不足而未启动，保留失败记录、清理允许清理的字节码后继续审核，没有重跑actor。这应成为后续处理可修复问题的范例。

| 身份／范围 | 本次独立核实 |
|---|---|
| 精确远端／本地HEAD | `d21f67b1afa09ccf4113a8fb2a9f1b57eb11adf1`，非交互ls-remote一致，起始工作树干净 |
| 实际实现／前测／actor／checker | `1fe058e3d120c42d197531139fc62e02a1a2cd5f`；18项资格文件与该提交及当前文件hash一致，文档HEAD不冒充运行source |
| 分支／worktree／base | `task42_neural_coarse_inverse`；canonical `/home/fenics/Projects/NN-Lab`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`；未修改其他分支 |
| 现场 | 无匹配Task042的真实actor／辅助worker；邻任务仍存在，未干预。不能从Git没有更新推断机器空闲 |
| 增量审阅 | 相对前review的80文件增量；159个规范化文件、3,573,433 B hash核对无差异；13个变更Python文件静态编译，深入检查实际study、reader、完整端口作用、checker、窗口及存储路径 |
| 历史 | 前review时已有60份review／response字节不变；四份导航／summary历史后缀完整；V26–V31的12份closed文件hash不变，V32 closed／active=null |
| 原始证据 | gzip与原日志／JUnit／manifest／actor JSON逐字相同；12个不同测试均通过；三次CPU准入的ticks／线程／SMT判定重放一致；16／113／7条资源样本逐成员重算 |
| 本次复验边界 | 保存数组的数值复核在唯一fresh CPU准入被拒绝，候选为空，未启动worker、未重试。后续只做静态源码、文件hash、原始标量及资源重算；**本次没有独立重跑数组checker或V32的12项测试**，也无因子读取、原算子、求解、QR/SVD、FE或训练 |

[独立审阅记录](outcomes/records/review_v30_independent_checks.json)及[本次准入原记录](outcomes/records/review_v30_admission.json.gz)明确上述边界。该审阅准入拒绝不推翻V32已存在的fresh真实actor和独立cached checker，也不应成为停止编写、发布下一轮合同的理由。审阅沿已有全历史索引与逐轮增量延续，不声称全仓每个文件逐行语义审计。GitHub页面抓取Cache miss，rendered view为NOT_VERIFIED；本地结构检查另列，无CI声明。

## 1. V32得到了什么，而不是只数通过项

“方向”是一次可施加的场修正；它经原方程作用后产生的响应，必须与尚未消除的残差方向相近，才有用。V32先在J=[5,7]求解，再经外部六块反馈并返回J抵消内部反作用。它产生了新方向，但新响应与剩余残差几乎垂直，故最佳组合也只能多消除很少的残差。

| 固定已消费冷末态；V32 measured | 九方向eta9 | 十方向eta10 | g10=eta10/eta9 | 额外范数下降／平方范数消除 |
|---|---:|---:|---:|---|
| V24-LZ-CYCLE4 | 0.9662055056183673 | 0.9648437480030249 | 0.9985906128588339 | 0.1409387141%／0.2816787910% |
| V24-LCZ-CYCLE4 | 0.9819684299899415 | 0.9807007112496798 | 0.9987090025488145 | 0.1290997451%／0.2580328228% |

两态rank10、创新与完整响应范数比分别0.911608／0.869686，足够可分辨；创新与e9复相关却只有0.0530734200／0.0507969313。原标量重算满足`g10=sqrt(1−coherence²)`。不是空间重复，也不是本次接线失败。两态g≥0.95触发原`FIXED_RETURN_DIRECTION_INSUFFICIENT`；不能以数学实现正确或尚有预算改判。

| 可信度／机制；V32原始记录 | 实际值／限值与含义 |
|---|---|
| J内抵消 | Ad范数1.578071565e-16／9.856390657e-16，operation相对1.76320e-20／1.87525e-20≤1e-10；需同时保留抵消前尺度，不能只看小绝对量 |
| 外域单次响应 | q_ret响应是原q_J的1.6194875／1.8589285倍；这是响应范数增长，不自动等同于完整残差增长或迭代发散 |
| 完整重组 | 差/b为6.19116e-17／1.76225e-16≤1e-11；差/当前r为7.60803e-16／5.41795e-16另列；operation≤1e-10 |
| 薄代数 | QR、正交最坏4.585e-16≤1e-10；驻点最坏1.484e-16≤1e-8；原checker从数组重算，不只信status |
| 真实消费 | S34＋Sᴴ2=36，reader7，J solve4／外域24，L/U pass56，薄流程2，40端口factor1／单列solve35；actor、manifest、ledger与固定逐项见证一致 |
| 物理资格 | 没有新场、E/H、衍射功率或official R/T/A。旧V23完整0/6、V24完整0/5保持；两冷末态不等于fresh zero-start求解，更不是warm资格 |

证据：[原actor包](outcomes/records/raw_result_v32.json.gz)、[独立checker](outcomes/records/return_direction_checker_v32.json)、[区域与方向分析](outcomes/records/direction_analysis_v32.json)、[真实消费](outcomes/records/actual_consumption_v32.json)。本次核对了原始标量、来源与检查逻辑；因审阅资源准入拒绝，数组级可信度采用V32已执行的独立checker证据，不冒称本次再次实测。

## 2. 成本和软件闭环可以接受，不能包装为求解成功

| V32 measured；shared-workstation | 费用／边界 |
|---|---|
| 前测／唯一actor／后checker监督 | 11.14747028495185／83.1401845519431／4.521115910960361 s |
| V27起累计 | carry52.68017605994828＋本轮98.80877074785531＝151.4889468078036 s；600s余448.5110531921964 s，不清零 |
| 同时树采样峰／swap | actor1,247,059,968 B，前测278,028,288 B，checker137,129,984 B；取最大，不相加；自身swap0 |
| 采样限制 | 请求0.5s，实际0.582–1.021s；无cgroup委派，只能称采样峰及监督门，不能称连续内核硬限或零邻任务干扰 |
| 嵌套费用 | reader含hash/mmap/norm/guard38.168578001s，S/SH6.333904905s，局部solve1.826185764s，薄代数0.023845749s；已在actor内，不再相加，IO／资格独占份额unknown |
| 因子 | 七套A＋LU净载荷1,591,420,032 B；旧构建费用、页缓存、pivot及LAPACK副本不免费，不能称factor-free |
| 存储 | 统一stat-only去重范围已用于事前、live、结项。首次checker预留拒绝时余962,172 B；清理506份未引用pyc、10,722,813 B后通过，未删除失败原始证据 |
| 最终库存 | 新输出含TMP22,487,642 B，累计124,150,258 B，128MiB余10,067,470 B；下一轮须重新库存，不把32MiB单轮上限当追加额度 |
| 收口 | V32窗口10:42:27.034377Z开始，10:58:45.583814Z提前closed；最后交付观察elapsed2016.551026s≤5400s。无第二actor，失败stderr及交付进程误报原记录保留 |

[费用](outcomes/records/resource_costs_v32.json)、[库存](outcomes/records/storage_v32.json)、[清理清单](outcomes/records/storage_cleanup_v32.json)、[历史完整性](outcomes/records/evidence_integrity_v32.json)支持关闭Review V29的存储漏计和同轮推进项。不要为了本次文档审阅重跑已绑定相同source／input／ABI的12项或110／162项。

## 3. V33为什么还能有新信息

原B_ret只读取J内残差。若J内恰为零、外域有待消除残差，它始终返回零。B_full增加外域残差的直接入口；这是传统块校正，不是神经网络。记A为原完整40端口闭合的trace算子，B_J为J主块逆注回全空间，L_O为外域0/1/2/3/4/6六个原主块逆之和：

```math
B_{\rm ret}=B_J-(I-B_JA)L_OAB_J,\qquad
B_{\rm full}=B_J+(I-B_JA)L_O(I-AB_J),
```

```math
B_{\rm full}-B_{\rm ret}=(I-B_JA)L_O.
```

V30仅完成小矩阵代数；V32仅实测B_ret。B_ret负结果既不验证也不否定这个补项。本次**显式授权**补项诊断，覆盖旧review中“B_full不得自动执行”的本轮边界，保持B_ret关闭。不同之处是接收原先完全漏掉的外域输入，并对固定系数的完整输出直接验残差；不是继续添加第11个最小残差方向、换同p1测试、调tau或延长迭代。

这里已有低成本证据入口：V25保存了各块对同一r的修正与原作用像，V32保存了同一r的q_ret。无需再加载六个外域因子即可构造：

```math
u=L_Or=\sum_{b\in\{0,1,2,3,4,6\}}q_b,\quad
k=B_JAu,\quad \delta=u-k,\quad
q_{\rm full}=q_{\rm ret}+\delta.
```

因此V33只需一套J reader和两次实际反馈solve，加固定资格见证与原作用检查。**这是对两个已消费r的缓存辅助数学诊断，不是任意RHS的在线B_full实现或其完整部署计时。** 其原生apply仍需J两解、六外块各一解和两次A传播，另加true residual／端口／恢复；历史缓存生成也仍计研发账。

B_ret秩≤3888<18144；B_full在各主块可逆并覆盖trace的代数条件下可逆，但固定2×2反例已表明原残差能放大6倍。满秩、误差可表示、一次残差下降、Krylov收敛和完整物理解资格是不同结论。V33只回答其中“一次固定完整输入校正实际如何”。

## 4. V33一次完成的执行合同

### 4.1 实现、定点检查、真实诊断和审核连续执行

1. 固定新V33窗口及carry，确认没有活跃Task042运行，保留V26–V32全部closed记录。读取同一两态的V24 parent／state、V25方向与像、V26 J缓存、V32 q_ret与资格包，冻结source和逐名hash；不增加INITIAL、warm、第三状态、参考场、teacher或权重。
2. 复用现有SelectedBundle、BarAction、原状态审核、DiagnosticWindow、watchdog和run_case入口。新增数学只进入合适src模块；以明确算法／batch参数或薄注册接线，不能复制整套runner、fixture和checker。V32默认及closed拒绝保持。存储范围显式扩展到V33和review_v30，避免再次漏计；旧V32快照不回写。
3. 最小合成端到端fixture先验证实际study→保存→结算→checker，覆盖差式、J内抵消、完整非互伴端口、外域输入非零/J输入零、零输入、奇异局部块拒绝与缓存错位拒绝。复用V30三小矩阵，不再搜好例；不要求先重跑历史全套。新增／受影响路径通过后自动继续。
4. 真实actor前源码提交且clean、资格绑定当前相关文件；唯一dat经`python scripts/run_case.py <V33单dat>`执行下面两态流程。真实数据读取、hash扫描和数值动作都在监督内，不能以preflight名义免费读取大因子。
5. 保存每态完整小证据后自动运行只读cached checker，再完成判定、成本、dot对照与response_v33。数学弱收益也完成剩余审核和分析，不因方法负结果跳过交付；“代码已准备，请review才运行”不满足本轮合同。

### 4.2 固定数学流程与可信度

两态均为0.7nm micro、384hex/p3/q15、18144 trace＋40port，物理／材料／MPC／模式／b不变。V25的q_b列是原块逆作用于该态r，必须核实其列号、支持与hash，不能误用V25拟合系数加权后的修正。u取六列**单位权重和**；禁止读旧5/7 LU或其他六块LU。

| 顺序 | 必须执行／保存 |
|---|---|
| J资格一次 | 只读V26 J的A、LU、pivot；原种子422601/422602，两solve见证，原主块及伴随配对。solve相对≤1e-8、operation≤1e-12，作用配对≤1e-10；不重装配／LU／gecon，不fallback |
| 每态输入 | 完整state residual、端口重新闭合及原b身份审核，沿V32原限值：差/b≤1e-11，端口≤1e-10；报告当前r和完整b两个分母 |
| 外域直接入口 | 缓存合成u与Au_cached；一次真实Au与缓存和配对，再求k=B_JAu并核验J局部solve；分别真实计算Ak和Aδ，检查δ=u−k及Aδ=Au−Ak |
| 旧回流对照 | 对保存q_ret作一次原A配对。不是重新求B_ret或重新做9→10 QR；旧负结果保持 |
| 完整输入输出 | q_full=q_ret+δ，一次真实Aq_full；检查等于Aq_ret+Aδ以及其J分量等于r_J。固定系数，不加阻尼、标量线搜索、最小二乘或Krylov |
| 公平直接对照 | q0=q_J+u，一次真实Aq0，与缓存Aq_J＋新Au配对；这是相同七区域、没有顺序反馈的单位权重对照，不能将其改称V25最优eta8或V32最优eta10 |
| 仅缓存的外域隔离 | r_O在J置零，δ正是B_full r_O；报告norm(r_O−Aδ)/norm(r_O)。这是同一r的机制拆分，不算第三独立样本；r_O=0时为NOT_APPLICABLE，不造分母 |

每个原作用配对同时要求差/完整b≤1e-11、operation≤1e-10并列差/当前r；operation尺度从实际操作数计算，不以抵消后小范数自归一。J内Aδ、J内Aq_full−r_J同样报告原操作尺度≤1e-10及/b≤1e-11。保存抵消前后量、系数固定为±1的构造、来源和完整40端口库存。输入、因子或真残差资格失败时不得给可信增益。

| 派生的完整直线消费；不是实测 | 预期／本轮硬上限 |
|---|---|
| 原作用 | J见证S2/SH2；每态输入S3及u/k/δ/q_ret/q_full/q0六个S，共S20＋SH2=22；硬上限S＋SH≤32 |
| J与外域 | J reader1，J solve4 RHS列（2见证＋2反馈），显式L/U pass8；上述数量均为本轮上限。外域reader/solve、新局部assembly/LU/gecon全0 |
| 端口 | 原40×40 factor1；按既有BarAction流程预期21次单列solve，含reduced_rhs1、见证4、两态各8；硬上限solve与RHS列各32 |
| 分解／迭代／输出 | 新QR/SVD/薄LS0、迭代0、训练0、新FE／场／official R/T/A0；每态仅一个固定q_full，不能使用上限余量搜方向 |

实现前逐调用预登记，synthetic计数与正式独立计数分开。若接线造成预期计数差异，在正式消费前说明每次调用的必要性、修正预登记及测试；允许在上述硬上限内消除明确计数接线差异，不必为此等待review。不能在运行后把EXPECTED改成实际数来制造PASS，也不能隐去RHS列或重复动作。

### 4.3 预登记判定与失败后的有效分析

定义rho_full=norm(r−Aq_full)/norm(r)、rho0=norm(r−Aq0)/norm(r)，另列rho_ret和外域隔离比。它们都是**单位系数一次校正**，不能与最优投影eta直接当作同一种算法成本对照。

| 身份、因子、重组与checker全部通过后 | 本轮结论及后续边界 |
|---|---|
| 两态rho_full≤0.75，且rho0>0、rho_full≤0.8rho0均成立 | `FULL_INPUT_SINGLE_STEP_SIGNAL`；只证明固定两输入的单步信号，可提出有完整费用依据的下一求解方案，本轮不自动迭代／训练 |
| 两态rho_full≥0.95，或两态均rho_full≥rho0−1e-10 | `FULL_INPUT_FIXED_STEP_INSUFFICIENT`；关闭这一个固定未阻尼补齐提案，不换次序、块、系数、样本或预算继续追信号 |
| 其余 | `STATE_DEPENDENT_INCONCLUSIVE`；保留两态实际值，不追加第三状态投票 |
| 输入／数值／资源／代码消费失败 | 明确INPUT_INVALID、NUMERICALLY_UNRESOLVED、PARTIAL或RESOURCE_STOP；没有可信rho时写null，不把未运行叫方法无效 |

若rho0为0，完整输入不能声称相对改善，报告对照已解及绝对值；所有零尺度须显式处理。上述20%是本次传统机制筛选标准，**不是神经20%收益的代用指标**。

失败分析必须回答：J内消除是否成立；外域误差来自u、k还是q_ret的相互抵消／放大；完整输入是否比原单位权重七区域对照更好；缓存省掉的费用在部署时会如何回来。可用已保存向量计算范数、内积、区域分解，不重新作用A、solve、QR/SVD。即使单步放大，也只能关闭这一固定单步提案，不能证明所有B_full预条件Krylov必失败；后者继续NOT_RUN，本轮不以此为理由扩大范围。

### 4.4 同轮修复与资源预算

| 项目 | V33规则 |
|---|---|
| 不清零累计 | carry151.4889468078036s；V27起全部受监督actor＋辅助仍≤600s，剩余448.5110531921964s。旧研发formal下界77,161.557139s及旧aux／完整N=1 unknown保留 |
| 窗口 | 首次工作冻结UTC／monotonic／boot_id，总5400s，有载截止start+4500s，最后900s交付；实现、修复、等待、hash及发布都计入，不刷新 |
| 真实actor | 本轮上限`min(180s, 600s−当前累计有载−20s后checker预留−10s清场, 有载窗口剩余)`；同一机制最多一个有真实消费的actor。180s是较V32七reader83.14s有余量的监督预算，不是成功耗时预测 |
| 辅助 | 前测／定点修复≤70s，后checker≤20s，合计≤90s，均在同一600s中收费。每次尝试独立ID、source、原日志及结算；不覆盖失败记录 |
| 可修复失败 | 测试、schema、导入、writer、计费和资格接线问题：定位、最小修复、只重验直接影响范围，然后继续；失败次数不是停止条件。历史有效证据按相关文件hash复用，不能任取旧PASS，也不机械重跑全库 |
| actor入口失败 | 若原作用、reader、solve、port setup等所有真实消费均为0，可在本窗口内修复最小接线并以新receipt继续，保留原尝试及耗时；不是第二个数学实验。已有真实消费后不重放actor，优先从已提交状态数组修复写出／checker并完成可做分析 |
| 资源与身份硬停止 | fresh CPU/SMT、内存、PSI拒绝后不循环找核或后台排队；因子hash、数学门限失败不降低门槛。不把明确磁盘缓存清理或软件故障误判为CPU资源拒绝。仅停止依赖的有载工作，继续静态归因、计划与交付 |
| 环境／内存 | native Task042 pure，MPI1/math1、实际BLAS getter1、独立cache／禁pyc；无FE/JIT/Torch/GPU/OOC。derived同时规划≤8GiB，actor warn12/hard16GiB、aux warn1/hard2GiB，整树请求0.5s、ownswap0；原reserve、邻增长128GiB和Task16GiB余量／PSI规则不变 |
| 存储 | 本轮含TMP≤32MiB，V27起约定范围连同review_v24…v30／records／results累计≤128MiB，全artifact≤20GiB，自由盘≥50GiB；准入前为数组、日志、checker及交付预留空间，不能只预留数组净载荷 |
| 清理 | 可提前清理未被证据引用的pyc和不再需要的已通过synthetic临时载荷并记录清单；可无损压缩日志并保存原hash／索引。不得删除失败原始包、window／ledger、hash-bound数组或真实因子。现有review_v25–v27仍有字节码目录，可先作stat与引用核对，不必等写满才处理 |

V33不以本次审阅CPU拒绝作为将来现场准入结论。若本轮真正没有可执行资源，应交付已完成的机制代码、可复现入口、静态计数／容量、具体拒绝及替代分析；不能伪造实测，也不能仅写“等待审核”而省略不依赖资源的工作。

## 5. 与dot互补的可执行工作，不等待身份不存在的参考

本次只读核实dot远端为`98084c70792b7ab51e95da60d8dd9f3da97ccef9`，按该SHA取README及[response_v15](https://github.com/Rookie1234567/MyFEniCS/blob/98084c70792b7ab51e95da60d8dd9f3da97ccef9/docs/task40extra_dot_parallel_cloud/response_v15.md)，未fetch／checkout／修改其分支。本地旧remote-tracking ref为`eb5b0ecc…`，没有当成最新。

| dot已发布Y点；仅只读文档对照 | 与Task042的边界 |
|---|---|
| p4、phi5、120cells、Ny6/K3、6q/3twists、manual532 ports；完整12960 interiors | 与Task042 p3／384hex／40ports微模型不同，不能共享一个“同正确性”性能分母或直接移植field／PC／factor |
| worker1748.504064s，saved checker565.966513s，峰分别1,606,623,232／1,707,114,496B | 包括其控制和证据流程，不是Task042参考逆的可比纯solver时间；本审阅没有独立审核dot原数组或替dot批准结果 |
| 六q CSR52,709,744B；setup含controls/IO5.747859s，纯LU/per-PC unknown | 共享存储的对象载荷不是RSS，未知费用不能补造；原AUTO32060/p6、扩大光学尺寸、原尺寸2TB/48h仍未资格化 |

V33同步产出一张只读接口／身份缺口表：geometry/material/wavelength/mesh/p/quadrature/MPC/canonical rows/mode/port/RHS/原作用／恢复协议／成本口径逐项列匹配、不同或unknown。缺匹配项直接保留，不为凑对照再生成一套dot求解器实验。远端无新发布时用上述固定SHA完成表格，不反复轮询、不给dot发消息、不将等待dot设为补项诊断的前置条件。

神经可替代环节另列成本上界和依赖：学习旧十方向系数不能超过相同空间精确最小残差，而且V32薄代数仅0.023845749s／actor约0.0287%；这不是20%完整耗时机会。若提出替代局部LU／数据表示，必须说明它如何保持原方程审核、能省哪些构建与驻留、增加多少训练／加载／精确校正费用。现阶段不训练，不把传统补齐效果归NN。

## 6. 历史去重、交付与原尺寸边界

| 已有路线 | 最新有效状态；V33不重复 |
|---|---|
| V1–V5 13.5nm p4神经粗逆 | 已关闭；不解锁旧F5／p6 |
| V6–V15 神经FE trace、hidden／固定特征 | 训练收益、仅头部拟合与传统固定基分别评价；未运行hidden不改名为新结果 |
| V16–V21 全空间LSQR／校正、ILU0／class64 | 原残差／物理资格未闭环；算子快不等于收敛改善，不延长旧迭代 |
| V22–V23 Galerkin／image-QR | 同p1空间换测试、scalar-tau不重复；V23完整0/6 |
| V24 八块LU及image-coarse组合 | warm／zero与overlap已实际运行，完整0/5；不是待运行的新路线 |
| V25–V26 八方向／联合方向 | 增量弱，固定方向提案已关闭；缓存只作新补项的已消费输入 |
| V27–V31 回流准备／小矩阵 | 资源拒绝及软件失败原样保留；V30 B_full仅小矩阵代数，不是实际micro部署 |
| V32 B_ret真实回流 | 本次接受可信负结果，关闭；不增加回流次数、块对或第11方向拟合 |
| V33 B_full外域直接入口 | 本报告新授权，当前NOT_RUN；同两态、缓存辅助、一次单位系数真残差诊断，无任意RHS／完整求解资格 |

完整历史依据仍是[Review V21去重清单](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、其后各轮review／response及[原检索索引](outcomes/records/independent_review_v21_20261002.json)。本轮不将旧结论当新测量。

V33应提交`response_v33.md`、两态原始向量与hash索引、独立checker、完整计数／资源／source／环境、同轮修复及停止记录、dot身份缺口和NN费用判断；同步README、summary、test_summary、changed_files，发生实际诊断或资源停止同步模型总账与development_progress。源代码提交与文档HEAD分开；结算active=null、closed、后代清空，推送同一task42分支后等集中review。不得让小修正不断产生新的平行任务书。

最终目标仍是50×25nm、z=-10..130nm原尺寸、0.7nm、完整非可分三维有限元，同时峰≤2e12 B、端到端≤172800s。当前micro只有1.4×1.05×1.4nm。V23 warm Schur约2.507714e-6、zero约0.06811318且功率超限；V24 LW4 Schur2.502117907e-6／功率差1.666968717e-6均超1e-6，LZ4 Schur0.0813766679／散射E差0.568888278／功率差0.007245974超1e-6／1e-4／1e-6。native单项或一次校正不能授予整体成功。

所有局部LU和全局QR按真实生命周期、同时峰及完整耗时入账。**神经增益只在同正确性下，相对最佳合格非神经路线的完整N=1耗时或同时峰至少改善20%，另一项仍合规，并包含数据、训练、设置、加载、推理、精确修正、审核和IO；不用早期10%，不默认摊销。** 原尺寸精度／fresh泛化／2TB／48h仍NOT_QUALIFIED，NN20%仍NOT_DEMONSTRATED。无merge approval；不修改dot、其他分支或master，不使用subagents或重置卡。
