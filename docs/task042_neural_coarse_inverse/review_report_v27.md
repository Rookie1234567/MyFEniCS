# Review V27：V29停止证据成立，先修轻量入口和误报测试再验收

## 0. 决定与审阅身份

**接受V29一次CPU准入拒绝后的零worker收口；不接受当前轻量交付入口已经可执行。独立审阅发现一个编译错误，并实测相关scope为147通过、8失败，其中32个负例的原“通过”被输出目录错误掩盖。仅在临时测试目录补齐输出目录后，checker的合法例和32个反例均按预期处理；三个小矩阵也通过。下一轮V30只修这些具体交付问题并完成一次轻量验收，不启动真实回流或新的三维求解。**

[response_v29](response_v29.md)已正式回应[review v26](review_report_v26.md)，按AGENTS §15顺延到v27。保留旧review、response、V29的NOT_RUN和全部原始失败。本次新测试是**审阅阶段的新证据**，不能倒填成V29已经执行。没有修改求解源码、调用subagents或重置卡，没有操作dot、其他分支或master。

| 身份／证据范围 | 核实结果与边界 |
|---|---|
| 精确远端／本地HEAD | `0b30054564440da6cd9c33723d70e28b5d872c19`；非交互ls-remote与本地、origin tracking一致；起始工作树干净 |
| 实现／准入launcher source | `bea514e634a0fde7b1b929535f79a6268856d01b`；V29测试／数值worker source=null；0b300545是交付文档HEAD |
| 分支与canonical工作树 | `task42_neural_coarse_inverse`，`/home/fenics/Projects/NN-Lab`，登记于`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 本机状态 | 起始主机只读检查未发现Task042 actor；未调整邻进程或准入规则。相近Task042extra分支不属本任务 |
| 本次增量 | 42个文件，含14个Python文件；重点检查collector、证书、写出／ledger接线、小矩阵、辅助入口、静态分析及测试；55个规范化路径、1,408,289 B文件hash核验 |
| 历史去重 | 相对v26提交的54份旧review／response均未改；原547文件索引与后继增量继续核对，导航／summary历史后缀保留；不声称全仓逐行语义审计 |
| 环境 | Task042资格化native Linux pure activation；独立`.venv`，NumPy1.26.4／SciPy1.11.4，三个原生BLAS getter均1线程，无FE／MPI库／Torch导入 |
| 真实数值边界 | 未读取真实packet或LU载荷，未作真实S/Sᴴ、局部solve／LU／gecon、真实QR/SVD、FE、迭代或训练；合成n≤16测试与固定8／2维代数另列 |

[独立核验、原日志及复现脚本](outcomes/records/review_v27_independent_checks.json)包含以下发现和有条件的隔离检查。GitHub精确页面仍Cache miss，视觉 `NOT_VERIFIED`；本地文档检查独立记录。没有CI或全仓测试通过声明。

## 1. V29停止与账本可信，不能由资源停止推导数学结论

V29的三个工作包分别是：补齐审核器的证据链；分析给外域残差增加直接入口；判断网络是否可能替代足够大的完整成本。它们没有授权新三维实验。审核器是检查“保存的向量、误差和消费是否相互一致”的工具，不是求解器；加强它不会直接改善残差或产生神经收益。

| [V29原始索引](outcomes/records/run_index_v29.json)／[成本](outcomes/records/resource_costs_v29.json) | 本次复核 |
|---|---|
| 一次准入 | 05:43:34.475826–05:43:35.721686 UTC；原gzip解压与ignored快照、stderr逐字一致；重新计算候选仍为空 |
| CPU原因 | 48个允许逻辑CPU中31个忙率≤5%，这31个均仅因活跃宽affinity线程规则被排除；其他核还有busy／窄affinity原因。是策略拒绝，不是48核持续满载的证明 |
| 未访问的Gate | MEMORY／DISK／PSI／CGROUP_GPU_SNAPSHOT均NOT_CHECKED，未填造PASS |
| 运行库存 | formal run空、auxiliary worker空、supervision目录不存在；ledger closed、active=null；无V29真实artifact或formal结果目录 |
| 真实消费与成本 | actor／S／Sᴴ／reader／solve／LU／gecon／真实分解／FE／训练均0；新监督有载0 s；worker峰及launcher峰unknown，不以0冒充实测 |
| 历史窗口 | V26、V27、V28均closed且hash保持；V29 start05:29:16.937526，05:45:04.616694提前closed，交付前elapsed1241.880788 s；没有刷新旧窗口 |
| 累计 | V27起监督有载仍21.163846770 s；历史formal研发下界77,161.557139 s，旧辅助／完整N=1链unknown保持 |
| 存储观察 | 交付前V29含代码上界610,398 B，V27起约45,166,770 B；全Task artifact18,024,901,709 B，自由盘约3.388 TB。是该时点观察，非永久最终库存 |

V28的两份CPU逐核静态表也逐项对回原冻结快照：socket/core/SMT、busy、PID/TID/start identity及排除规则一致，重算候选为`[11,22,26]`／`[]`。此次复核不修改V29原表“转录而非本轮重算”的历史身份。现有证据不支持忽略桌面／Codex线程、放宽5%门限或修改邻任务来找核。

## 2. 两项必须修复的交付缺陷

### 2.1 P1：轻量入口无法导入，AST检查不足以保证可执行

[task042_v29_cached_analysis.py](../../benchmarks/task042_v29_cached_analysis.py)第44–45行在同一个`dict(...)`中两次使用`snapshot=`，一次为标签、一次为文件引用。Python编译直接报：

```text
SyntaxError: keyword argument repeated: snapshot
```

[task042_v29_light_checks.py](../../benchmarks/task042_v29_light_checks.py)顶层导入该模块，故在进入任何资格检查／测试前就失败。本次只编译14个变化Python文件，13个可编译，只有此文件失败；在一次审阅准入通过后实际导入也得到相同异常。原V29的selected AST检查记录并非运行成功声明，但AST能构造不代表后续编译可通过。

下一轮把标签与文件引用拆为两个明确字段，所有消费者使用同一schema；在消耗唯一辅助准入前，对全部直接相关Python执行真正的`compile(...,'exec')`或等价编译检查，不执行模块、不触发数值工作。不能仅再次`ast.parse`，也不能通过跳过缓存分析来让总入口变绿。数值／运行验证仍须在准入及监督内完成。

### 2.2 P2：输出目录缺失导致8个正例失败，32个负例因错误原因通过

[src/test/task042_return_fixture.py](../../src/test/task042_return_fixture.py)第80行只定义`root/'records'`，没有创建它；collector首次写`input_inventory_v28.json`时，原子写函数要求父目录存在。因此7个合法结果和1个partial结果都在任何审核前失败。直接相关scope实测：

```text
8 failed, 147 passed in 5.41s
```

[src/test/test_task042_v29_checker.py](../../src/test/test_task042_v29_checker.py)第99行接受`(ValueError, KeyError, OSError)`，`FileNotFoundError`属于OSError。32个变异负例也在首次输出时遇到同一目录错误，于是被算作通过；它们当时没有证明触达预期的计数、因子、向量或状态Gate。不能把147个PASS全解释为有效的审核反例覆盖。

修复应明确输出目录由fixture还是collector负责创建，并测试正常入口在全新合法目录上可工作。负例须先确认未变异的完整包能通过，再验证预期异常类型及对应Gate／错误键；不让任意IO错误成为成功。只有专门的缺文件测试可接受明确路径的FileNotFoundError；本次32个数据变异均不需要OSError兜底。

为定位缺陷，本次只在**临时fixture目录**增加`records.mkdir()`，没有改tracked代码。结果是7个合法例全部CHECKED、partial为PARTIAL_UNRESOLVED，32个变异全部在相应审核处以ValueError／KeyError拒绝。该隔离结果表明原四个review反例的**组件修复有效**，范围包括零消费、因子失败、错误回流向量和错误残差范数；但不能代替修复后的原样入口／pytest资格。

| 临时目录准备后的合法例 | 独立返回；只是合成审核 |
|---|---|
| positive | RETURN_EXTRA_DIRECTION_SIGNAL |
| weak | STATE_DEPENDENT_INCONCLUSIVE |
| resolved、beta=0 | FIXED_RETURN_DIRECTION_INSUFFICIENT |
| zero／duplicate／nearzero | REDUNDANT_OR_UNRESOLVED，合法零系数保留 |
| solved baseline | g10=null，不填0；总分类STATE_DEPENDENT_INCONCLUSIVE |
| partial actor record | PARTIAL_UNRESOLVED，不发CHECKED |

无需改残差门限、秩阈值、系数准入或真实算法来修复这两项。原四个缺口已有新的组件证据，整体状态仍是 `QUALIFICATION_BLOCKED_BY_ENTRY_AND_TEST_HARNESS`。

## 3. B和C获得了哪些新信息

### 3.1 全空间补项的代数成立，不意味着真实收敛

旧回流B_ret只接收J内残差；J内输入为零时，即使外域有误差也返回零。B_full多加一个直接处理外域残差的入口，因此能作为全空间的代数作用。这改变的是区域间信息传播，而不是训练网络；仍需要J与外域的局部LU。

```math
B_{\rm ret}=B_J-(I-B_JA)L_OAB_J,\qquad
B_{\rm full}=B_J+(I-B_JA)L_O(I-AB_J).
```

```math
B_{\rm full}-B_{\rm ret}=(I-B_JA)L_O.
```

本次直接运行已登记的三种小矩阵，未新增参数、样本或方法。8维complex128非Hermitian例的差式／顺序作用／复线性／三角分解最大operand归一误差8.130e-17；2维反例最大1.906e-16，均≤1e-12；零局部块按预期拒绝。补齐局部可逆块给出的全空间可逆性来自分块三角乘积，不要求A正定，但不保证迭代收缩。

固定2维反例A=[[1,2],[3,1]]、r=[0,1]中，B_ret r=0，而B_full r=[−2,1]，原残差变为[0,6]，范数放大6倍。现在这是**本次审阅的小矩阵测量**，同时保留V29仅有纸面推导／fixture未运行的历史。它否定“补齐全空间就会收敛”的推论，不证明真实Maxwell会发散。

这部分必要条件分析可以接受，无需下一轮继续换小矩阵找正例。B_full真实micro作用、求解收敛与NN替代仍NOT_RUN；V27／V28原回流两冷態eta10／g10也仍NOT_RUN。二者不能互相代替，不能因小矩阵通过跳过真实因子、原作用和完整场资格。

### 3.2 成本结论仍有限，但足以排除“只加速小LS即可达20%”

[静态成本库存](outcomes/records/static_complete_cost_inventory_v29.json)的V24–V28费用逐项对回hash-bound原JSON。历史actor分别1977.711696／25.665227／33.262622／0／0 s，V27／V28辅助12.366657／8.797189 s；研发与未成功诊断不是合格单解时间。嵌套timer不与actor重复相加。

新缓存分析模块整体不能导入。本次仅从AST抽出**未修改的cost_ledger函数**在隔离namespace执行，输出与上述时间／载荷口径相符；这用于定位独立函数是否另有错误，明确不是新模块或正式入口通过。完整链仍需V30原样验收。

| 可保留结论 | 边界 |
|---|---|
| V26两次薄分解共0.008964091 s | 占该33.262622 s诊断actor约0.027%；即使免费替代也不到同口径20%，不是完整成功单解占比 |
| B_full直接apply | J两解、六外块各一解、16次显式三角pass、两次原A传播；最终true residual、端口闭合、恢复／审核另算，原A内端口费用不遗漏 |
| 七套A＋LU | 1,591,420,032 B；纯LU下界795,710,016 B；数组体积不是同时RSS，hash、页、LAPACK副本、pivot、库与workspace另计 |
| 冷准备／重载／驻留复用 | 生命周期不同，不把既有因子免费化，也不把资格见证按每次apply重复收费；B_full实际部署time／peak未知 |
| 最佳合格非神经N=1基线 | 当前没有完整合格配对，T_base／M_base仍unknown，不能计算神经收益通过率 |

神经标准继续为：**在相同正确性下，相对最佳合格非神经路线，完整N=1时间或完整同时峰内存至少降低20%，另一项仍合规。** 时间必须满足T_removed−T_added≥0.20T_base，新增费用包括生成数据、训练、设置／加载、推理、额外精确修正、审核与IO；不默认摊销。峰内存必须重建同一生命周期的同时驻留对象，不能用删除对象字节代替峰降幅。同八／九方向只学系数不能超过同空间精确最小残差；更换方向或替代大成本仍需独立合同与消融，当前没有训练或额外神经收益。

## 4. V30：只修具体缺陷并验收已准备工作

下一步值得做的是结束这条审核准备链，而不是再堆一个数值方案。本次已定位两个局部原因，临时目录复核支持小修即可恢复预期行为；资源准入失败并未证明方法无效。授权以下三个顺序工作包，由执行Codex独立完成。

| 工作包 | 实现／验收要求 | 禁止扩大 |
|---|---|---|
| A．修入口与负例 | 修重复keyword及schema；明确创建输出目录；负例先有未变异正控制，再断言具体Gate，移除无针对性的OSError兜底；准入前完成全部相关代码的编译检查 | 不改数学核、容差／rank、CPU策略，不跳过失败组件 |
| B．原样轻量验收 | 用提交后的最终source运行相关scope；当前155项均应通过，新增精准回归另列。执行完整轻量入口，生成CPU重算、三fixture和成本记录，检查其终态／退出码，不能只跑pytest子集 | 不把本次临时mkdir／AST函数抽取当交付修复；不重算真实因子或回流方向 |
| C．封存与下一步判定 | 将新证据写V30，关联V29失败及本报告证据；逐项列组件关闭／尚未运行。给出一次真实诊断还缺哪些执行条件与完整费用，提交后停止等review | 不将B／C通过变为真实actor授权，不新造“全部成功”标签 |

复用现有辅助监督／`DiagnosticWindow`和轻量入口，最小参数化本次batch、输出records及scratch路径即可；**不能将V30输出写回V29，不能修改V26–V29已closed窗口／ledger**。默认旧入口语义保持，新增参数只允许本次已授权namespace；不复制数值核或新建正式PDE dat。合成collector内部的历史字段名可保留，但临时包必须隔离，不覆盖真正的`return_direction_results_v28.json`。

对因子／manifest／ledger审核继续保持当前完整消费36次原作用、35次单列端口、七reader等约束；这些在V30只作为合成测试合同，**真实库存必须全部为0**。新轻量输出须明确synthetic／cached-metadata，不能因fixture构造了“36”就算真实原作用已发生。

| 资源与闭环 | V30上限与停止条件 |
|---|---|
| 分支／角色 | canonical NN-Lab，精确`task42_neural_coarse_inverse`；不使用subagents、不用重置卡，不改dot／其他分支／master |
| 总窗口 | V30首次工作起elapsed≤3600 s；前2700 s实现／轻量检查，最后900 s收口；UTC／monotonic／boot_id冻结，不刷新 |
| 有载预算 | 本次轻量有载≤120 s，承接V29未消费的验收额度，不叠加成240 s；V27起actor＋辅助累计仍≤600 s，已有21.163846770 s保留；审阅费用另列 |
| 准入 | 编译检查和修复准备完成后，仅一次新的辅助准入；原5%／SMT／内存与PSI规则保持。拒绝即停止运行部分并静态交付，不重试、不后台排队、不轮询找核 |
| 运行与修复 | 通过后在同一受监督任务中先最小回归再整体入口；不以缺少新准入为由绕过监督。运行出现新代码错误时保留失败并停止，不能在同一轮不断重启，交付具体根因 |
| 隔离与峰 | `source scripts/activate_task042.sh pure`，独立新cache；MPI1/math1，无FE/JIT/Torch/GPU/OOC，自身swap0；0.5s树采样warn1GiB／hard2GiB，清理本任务后代 |
| 数据权限 | 只读冻结紧凑JSON、准入gzip／timeline及合成包；不读真实packet、A/LU载荷、REF7／teacher、旧p1 T/U/R／Krylov或神经权重 |
| 数值与样本 | 不增加真实动作、LU、solve、QR/SVD、FE、迭代或训练；保持三种已登记小矩阵，不扫描参数／几何／波长／块对 |
| 存储 | V30新增含TMP≤16MiB，V27起新增累计≤128MiB；全Task artifact≤20GiB，自由盘≥50GiB；旧失败原文不删改 |
| 交付 | response_v30、原始测试日志及计数／峰、source／环境／命令／hash、入口编译及真实执行结果、CPU／代数／成本记录；更新导航／summary／tests／changed_files，资源停止按docs规则更新总账；推送完整HEAD后停止 |

本次审阅准入找到CPU43，不是未来资源预约或启动真实actor的理由。V30授权的依据是**已定位的交付缺陷修复与未完成的轻量验收**，不是继续增加数值预算。若再次仅因资源而无法验收，在外部提供可审计空闲条件前，后续不要自动开另一编号重复相同尝试；仍可完成静态审查，但数值与测试身份保持NOT_RUN。

## 5. 失败后的有效替代与历史去重

入口／测试失败先修局部问题；资源拒绝保留原始快照；代数反例已说明全空间可逆不保证收敛；完整成本unknown则交付缺失项和必要条件。这些各自有意义，不能混写成同一种“求解器失败”。若下一次真实方向诊断获得授权，仍以V26九方向为基线，保持两原冷末态、g10≤0.75／≥0.95分流与原预算；不拿旧八方向作新基线，不加循环、scalar-tau或训练救场。

| 历史路线 | 当前结论；本报告没有重跑 |
|---|---|
| V1–V5 p4神经粗逆，13.5nm | 已关闭；旧F5／p6条件路线未因本次审阅解锁 |
| V6–V15 神经FE trace／固定特征 | 实际训练与hidden更新的失败保留；固定特征、仅头部拟合和未运行hidden路线分别记账，不冒充神经增益 |
| V16–V21 全空间校正／ILU0／class64 | 残差改善不等于完整物理资格；算子加速不等于收敛改善，旧预算不延长 |
| V22–V23 Galerkin／image-QR | 同p1空间的表示能力与可消除残差已区分；不换左测试或tau再领新收益；V23完整0/6 |
| V24 八块LU与image-coarse组合 | warm／zero四路首4周期及overlap资格已执行，完整0/5；不再把原V24计划当待运行 |
| V25／V26 方向最优组合 | 八方向末态eta8约0.983237／0.989925；联合方向相对e8仅多降1.732185%／0.803718%，固定提案关闭 |
| V27／V28 真实回流 | 两状态eta10／g10均NOT_RUN；资源停止不是数学负结果 |
| V29／本次review | V29 worker0；本次补小矩阵和隔离审核证据，发现入口／测试缺陷；真实全空间补项、三维求解和NN仍NOT_RUN |

历史逐轮证据见[v21完整清单](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、[v22](review_report_v22.md)、[v23](review_report_v23.md)、[v24](review_report_v24.md)、[v25](review_report_v25.md)、[v26](review_report_v26.md)和[原检索索引](outcomes/records/independent_review_v21_20261002.json)。本次是按该历史基础做42文件增量审阅，未把旧测量改名为新结果。

原目标仍是50×25nm周期、z=-10..130nm原尺寸、0.7nm、完整非可分三维有限元，完整同时峰≤2e12 B、端到端≤172800 s。当前micro仅1.4×1.05×1.4nm、384hex/p3/q15、18144 trace＋40port。V23 warm Schur约2.507714e-6／zero约0.06811318、逐通道功率超限；V24 LW4 Schur2.502117907e-6／功率差1.666968717e-6均超1e-6，LZ4 Schur0.0813766679／散射E差0.568888278／功率差0.007245974超1e-6／1e-4／1e-6。native单项通过或小矩阵通过不能改变V23 0/6、V24 0/5。

固定块数的稠密A/LU载荷32Σn_b²、设置Σn_b³，全局image基16nr、R矩阵16r²及QR工作nr²仍要计真实生命周期；当前微型峰值不能外推2TB规模。dot独立承担完整三维参考逆、周期分块、共享存储与规模验证，本任务只补可信链和有限方向／学习成本分析，不重复其完整求解器实验或修改其分支。原尺寸、离散精度／fresh泛化、2TB／48h仍 `NOT_QUALIFIED`，神经20%仍 `NOT_DEMONSTRATED`，**无merge approval**。
