# Review V26：接受V28准入停止，V29先完成可信链与全空间代数分析

## 0. 审阅决定与下一轮范围

**接受V28的 `NOT_RUN_AUXILIARY_CPU_ADMISSION`，关闭父指针缺失及失败准入无原始快照问题；独立结果checker仍需补齐两处可复现的审核缺口。真实回流方向仍未运行，不能判断有效或无效。下一轮V29安排三个有界工作包：checker修复、全空间补项的小型代数验证、神经20%收益的成本可行性分析。暂不重新授权真实回流actor。**

[response_v28](response_v28.md)已正式回应[review v25](review_report_v25.md)，本报告按根AGENTS §15顺延到v26，历史review／response均保留。本报告是V29唯一新增执行合同；旧V27／V28窗口保持closed，旧“下一建议”不构成重入许可。用户要求本轮独立审阅，因此本次仅提交文档，没有修改求解源码或启动数值实验，未使用subagents或重置卡。

| 身份／范围 | 核实结果及边界 |
|---|---|
| 被审阅远端与本地HEAD | `09b8b3d9415eed8c8daf8e17820d7f4ae1737139`；非交互ls-remote与本地及origin tracking一致，起始工作树干净 |
| 实现与运行source | 实现 `4808fcab78bbf1b1284ffba1f3ff19b0033fb937`；实际数值source=null；1d7b6514与09b8b3d9为结果／交付文档，不是运行source |
| 精确分支／canonical worktree | `task42_neural_coarse_inverse`，`/home/fenics/Projects/NN-Lab`；登记于`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 本机状态 | 本次主机只读进程检查未发现Task042 actor／launcher；有邻任务在运行，未改变其进程、affinity或监督器；相近`task42extra_feinn_5nm`不属本任务 |
| 本轮代码与证据 | 检查43个增量文件，深入检查checker、reader／数学核增量、namespace／准入／计数接线和测试；核验59个规范化路径、21,997,968 B文件hash |
| 历史去重 | 原547文件索引及后继审阅继续有效；相对v25提交的52份旧review／response字节未改，四份导航／汇总历史后缀保留；不把旧结论当本次实测 |
| 独立回归 | 一次准入后CPU16、pure/math1、2GiB上限执行原scope，100 passed in6.00s；监督wall8.577899s、同时树采样峰146,137,088 B、自身swap0、后代清场 |
| 审阅深度边界 | 未读取真实LU载荷，未作新真实S/Sᴴ、LU solve、QR/SVD、FE、训练；小型合成fixture另列。不是全仓每个文件的逐行语义审计 |

[独立核验与反例脚本](outcomes/records/review_v26_independent_checks.json)保存hash、冻结快照重算、零消费推导、测试日志和四个反例。当前代码100项通过并不能替代缺失的审核条件。审阅费用单列，不冒充V28 actor或单解性能。精确GitHub页面读取仍Cache miss，视觉 `NOT_VERIFIED`；本地文档检查另列，不声称CI／全仓测试通过。

文档治理／总账Markdown相关测试12项通过，新增报告与README的表格、围栏、136个本地链接及历史后缀检查通过。既有跨任务registry章节／缺失证据合同问题本轮未修复或重跑，仍不宣称全仓绿。

## 1. V28证据成立的部分

独立checker是“对保存的计算过程再算一遍结论”的审核器：它读取保存向量，检验残差、线性组合和预算，避免只信任PASS标签。V28新增九维投影证书，使新增系数为零时也能检查新增方向是否落在旧空间；这减少审核盲区，代价是保存少量数组，不是新的预条件器或神经收益。

| V28正式分类与证据 | 本次独立判断 |
|---|---|
| [parent库存](outcomes/records/input_inventory_v28.json) | 两状态父记录分别绑定`4971ba16…`／`3051afc2…`，与预登记及实际V24记录一致；V27原null文件未覆盖，此缺口关闭 |
| [准入checker及两份无损快照](outcomes/records/admission_checker_v28.json) | gzip解压与ignored原文件逐字一致；CPU tick、thread delta及候选集合重新计算一致；失败stderr为调用时redirect，旧转录问题关闭 |
| [正式数值结果checker](outcomes/records/return_direction_checker_v28.json) | 如实为NOT_RUN，无两份真实新向量，没有伪造数值PASS；新checker组件已经存在，但完整可信链尚未通过§3 |
| [ledger／原始索引](outcomes/records/run_index_v28.json) | closed=true、active=null、run空，全部数值计数0；formal admission marker不存在，formal结果目录0，新npy／npz=0 |
| 正式资源停止 | 第一次辅助执行成功；第二次辅助在worker创建前拒绝，随后未再准入、未启动正式actor；正确区别于V27的正式入口拒绝 |
| 旧窗口 | V27保持closed；V26 ledger SHA256仍为`93e059e96fdd0ed0fd43c1cd05f24db6e048004a84a98231e64821f63a0f3853` |

正式actor、S/Sᴴ、七bundle读取、真实局部／端口求解、新LU／gecon和薄分解均为0。V28 artifact只有最小结果／成本记录，无真实回流结果。两冷态eta10／g10仍null，不能从null推出方向无效，也不能把合成测试的通过转为真实因子重载资格。

## 2. CPU拒绝与费用：现在能解释到哪一步

| 冻结观察，measured／recomputed | 03:50:41 UTC辅助成功 | 03:52:00 UTC辅助拒绝 |
|---|---:|---:|
| 允许逻辑CPU数 | 48 | 48 |
| busy fraction≤5%的CPU数 | 28 | 30 |
| 原策略最终候选 | 11、22、26；选择11 | 空 |
| 仅因活跃宽affinity线程被排除的CPU数 | 25 | 30 |
| MEMORY／DISK／PSI | PASS | NOT_CHECKED |
| 准入观察耗时，秒 | 1.276557320 | 1.318466949 |

这解释的是**当次安全策略为何拒绝**，不是“整机48核持续满载”。失败快照中，gnome-shell的33个有tick增量的宽affinity线程覆盖33个最后观察CPU；Codex另有7个活跃线程，其排除集合有重叠，不能直接相加。忙核／窄affinity邻worker继续排除。Task042工作目录的一行已退出检查相关进程没有活跃宽线程，不能简单归因为Task042自占全部空闲核。以上是冻结快照分解，不是新的宿主机负载实验。

当前按>5%忙率、活跃宽线程和SMT同胞排除的实现与原策略一致，**没有证据支持静默忽略桌面／Codex线程、放宽门限或改邻进程affinity**。审阅小测试后来一次准入找到CPU16，只说明瞬时条件变化，不提供未来actor的资源预约。下一轮先使用已保存快照生成逐核原因表；不轮询挑核、不做准入成功率扫描、不为了数值实验新开同类窗口。

| [V28成本](outcomes/records/resource_costs_v28.json)与[交付观察](outcomes/records/delivery_receipt_v28.json) | 独立核实口径 |
|---|---|
| 受监督辅助／正式actor | 8.797189402 s／0 s；14条资源采样，峰150,163,456 B，自身swap0；这是辅助峰，非部署峰 |
| V27＋V28累计有载 | 12.366657368＋8.797189402＝21.163846770 s；原600 s的算术余额578.836153230 s不是重入授权 |
| 不刷新窗口 | start03:42:09.791551、heavy-stop04:57:09.791551、deadline05:12:09.791551 UTC；03:55:13.868已closed；交付前观察elapsed1227.446710 s |
| 存储观察 | 交付前V27＋V28新增含TMP为44,554,177 B；全Task artifacts18,024,901,709 B；自由盘3,388,300,509,184 B；观察之后的文件变动另记，不称永恒最终库存 |
| 容量与因子 | 规划4,807,239,744 B为derived、未分配；J＋六外块A/LU合1,591,420,032 B为载荷总量，非同时RSS；历史设置费没有因本批没读因子而消失 |
| 历史 | formal研发下界77,161.557139 s保持；旧辅助和完整N=1上游链仍unknown，不能把0 actor耗时当加速 |

V28回执ahead/behind=2/0明确为推送前观察；本次精确远端已包含09b8b3d9，不是现在未推送。

## 3. 尚未关闭的checker可信链：两个P2

以下反例只使用现有小fixture，不读取真实因子。它们没有推翻V28的NOT_RUN，也不证明实际solver算错；它们证明checker还不能独立承担未来正式数值验收。

### 3.1 P2：完整结果能绕过原作用／端口计数及因子资格

入口是[collect_task042_return_direction.py](../../benchmarks/collect_task042_return_direction.py)的`inventory()`（本次HEAD第90–106行）。它检查计数上限和部分固定总数，却不检查完整actor必需的原作用／端口库存，也未审核`factor_reloads`。

在既有`inventory_fixture()`中，把`actions/S/SH/port_solves/port_rhs_columns`同时改为0，仍能通过；另一次把`factor_reloads`改为仅一个`qualified=False,witnesses=[]`的J记录，也通过。实际`collect()`后续没有补查这些字段。故“7 reader、两份结果”不足以证明七套因子见证和原作用确实完成。

V29须将完成态与部分／失败态分开，独立核对J和0/1/2/3/4/6恰好各一次、规定seed与finite原始误差门限、source/hash/行身份、三角pass／RHS列、端口逐次shape／列及durable ledger／manifest／结果计数一致。当前直线实现的完整消费应为S34＋Sᴴ2=36、J4列、外域24列、三角56、端口35次单列、reader7、薄流程2；这些是代码预期，**不得填造为实测**。不完整数据应返回明确partial／unresolved或拒绝，不能仍给CHECKED。冻结source发生相关变化时先解释计数差异，不通过放宽下限掩盖。

### 3.2 P2：保存的回流向量及归一化数值未参与一致性检验

同文件`numeric()`检验了`return_image`，但`return_direction`只检查shape／finite；把合法fixture的`return_direction[0]`加100仍返回trustworthy。`residual_norm`翻倍也通过。当前实际eta计算使用真实范数，故后一问题没有直接改变eta；但发布记录可以自相矛盾，前一问题更无法绑定声称的回流向量。

V29应从hash-bound V26保存的q_J核对`q_ret=q_J+d`，并核对w在外域、feedback在J内的支持、实际输入残差范数、保存的状态／端口identity见证和操作尺度来源。对已有`cancellation`／`identity`／重组见证做必需字段、finite、阈值和数组一致性审核；不要因为`trustworthy=True`跳过它们。对已经能从保存数组重算的量，不再只信标签。确需新增证书时仅保存本来已计算的数据，不增加真实原作用、求解或分解。

**验收须穿过完整collector链**：临时目录中建立两个不同名称／父记录／成员hash的合成完整包，运行正式checker函数直到最终分类，再逐项破坏上述必需证据。现有测试直接调`numeric/inventory`，不能替代端到端接线测试。参数化输入／输出路径，默认保持现有语义；fixture不读取真实窗口、改旧记录或创建actor。保留零／重复／近零创新、可信弱结果、resolved但beta=0和已解基线等合法负例，不能修成“一律要求rank10或beta非零”。

## 4. V29可执行的三个工作包

### A：完成审核可信链及资源原因表

按§3修复checker及最小证书／接线，保留已通过的原100项相关scope。新增端到端合成包和针对反例，不扩写另一套solver；预处理／collector可复用，numerical algorithm不改。将两份冻结准入快照输出为逐核表，列socket/core/SMT、busy分数、排除线程的PID/TID/start identity及规则；集合重算必须精确等于`[11,22,26]`和`[]`。不另作live负载采样实验，也不改准入策略。

验收：四个本次反例被拒绝；缺／重／错bundle、失败见证、计数／ledger不一致、错父记录／成员hash、非有限数及缺少真实数组均不能获数值通过；合法负例仍通过。失败只修已定位根因、最多两次；不得用真实回流actor来调试checker。

### B：补外域输入的代数可行性，只做小矩阵

原回流只看J内的输入残差：外域如果有待解残差而J内为零，整条路线返回零。要成为可供任意残差使用的预条件器，必须给外域一个直接入口。下一轮先证明补项的含义与成本，防止把“一个方向有收益”误写为“完整预条件器已成立”。不在真实micro上实施新方法。

记A为原闭合trace算子，B_J为J主块逆注回全空间，L_O为外域六块局部逆之和；这两者仍包含稠密LU。原诊断和待分析的完整残差作用分别为：

```math
\begin{aligned}
B_{\rm ret}&=B_J-(I-B_JA)L_OAB_J,\\
B_{\rm full}&=B_J+(I-B_JA)L_O(I-AB_J),\\
B_{\rm full}-B_{\rm ret}&=(I-B_JA)L_O.
\end{aligned}
```

这只是“J先处理、外域处理剩余、J再补偿”的传统顺序块校正，**不是神经网络**。操作形式为q1=B_Jr、u=L_O(r−Aq1)、q=q1+u−B_JAu。与原方向不同之处是外域直接残差项；不能只重新命名q_ret或者在旧九空间换测试。rank(B_ret)≤3888，而B_full在J及外域各局部块可逆且覆盖全trace时具有全空间代数作用；其分块三角分解与可逆条件须明确写出，不能从这点推断收敛。

工作限于纸面推导和至多三个预登记的小矩阵fixture（n≤24，固定seed422901，complex128；不抽样选好例、不扫描参数）：验证上述差式、复线性／零输入、J内／外域支持、原输入次序及奇异局部块显式拒绝。至少保留下列反例：A=[[1,2],[3,1]]，J为第一行、L_O第二行局部逆；B_full=[[7,−2],[−3,1]]。外域输入r=[0,1]时B_ret r=0，但B_full r=[−2,1]，真实剩余残差为[0,6]。因此“补齐全空间／局部精确”仍不保证残差收缩。该例不能外推真实Maxwell会发散。

验收为代数与反例一致，数值等式按operand归一误差≤1e-12；零分母显式处理。函数若需实现，放在测试fixture／研究验算入口，不接入production PC、不注册新正式dat、不读取真实packet／因子。若代数或假设不成立，停止该提案并说明；不换块对、重叠、顺序或调tau救场。

**这是后续方案的必要条件分析，不是用新方法替代尚未运行的旧回流试验。** V27／V28的两冷态eta10/g10仍NOT_RUN。是否值得消耗一次真实回流／全空间校正预算，留待A、B、C交付后的review判断。

### C：完整成本与神经20%门槛的可行性账

利用V24–V28已存成本JSON／计数／文件大小，建立一次可复算的分账，不加载A/LU数值载荷、不重做benchmark。区分：上游packet／局部因子设置、读取hash与mmap、重复三角解、端口、原作用、全局／薄QR、后处理、审核及IO；嵌套timer不能相加。逐项标measured／derived／unknown，缺完整单解链就保留unknown。

给B_full分别列纯部署apply和资格检查成本：直接按固定流程每次使用J两次、六外块各一次、两次原A传播；最终true residual与端口闭合另列。冷启动七套因子的准备与存储、每次重新加载／可复用驻留两种生命周期分开；共享因子无需重复算字节，但副本、hash缓冲和同时峰不能漏。只分析这一个补项，不开展多个PC比较。

神经收益按**相同正确性下，相对最佳合格非神经路线，完整N=1耗时或完整同时峰内存至少改善20%，另一项仍合规**。时间必要条件可写为：

```math
T_{\rm new}=T_{\rm base}-T_{\rm removed}+T_{\rm added},\qquad
T_{\rm removed}-T_{\rm added}\ge0.20T_{\rm base}.
```

T_added须含数据生成、训练、模型设置／加载、推理、额外精确校正与审核；不默认跨多个rhs摊销。本批没有合格完整T_base，公式只能给必要条件／瓶颈位置，不能给加速结论。峰内存须按同时驻留对象重建，不能用“删除对象字节／累计总字节”代替峰比。

已有V26两次薄分解共0.008964091 s，相对33.262622 s actor仅约0.027%；即使免费替代这部分，在该诊断的同一成本口径下也远不到20%。这不是完整单解的占比证明，更不能代表所有神经方法无用。若学习只输出旧八／九个方向的系数，它不能超过同空间精确最小残差组合的消除能力；只有替代实际大成本或形成不同而可资格化的作用才可能值得另立合同。本轮只列必要条件，不训练，不把LU／固定特征／QR收益称神经收益。

交付一份结论明确的成本表：哪项值得后续研究、哪项已不可能靠局部提速达20%、哪些因unknown尚不可判断；不得填造最佳非神经成功基线。

## 5. V29资源、交付与停止合同

| 项目 | 授权与限制 |
|---|---|
| 执行人／分支 | 执行Codex在当前canonical worktree独立完成A→B→C，不启subagents；精确本分支，不修改dot／master／其他分支 |
| 首次工作窗口 | 总elapsed≤3600 s，前2700 s完成实现／轻量验证，最后900 s收口；UTC／monotonic／boot_id冻结，不刷新；没有真实数值actor窗口 |
| 轻量运行预算 | 新测试／合成验证／缓存分析有载合计≤120 s，且继续列入V27起600 s累计账；V27＋V28已有21.163846770 s不清零，审阅自身费用另列 |
| 轻量准入 | 仅为完成已准备好的轻量命令作一次辅助准入；尽量将相关检查合成一条受监督命令，原5%／SMT及内存余量／PSI规则保持。失败即停运行部分，完成静态推导／文档，不另找核；后续修复如需再次准入须留待review |
| 驻留／线程 | pure activation，MPI1/math1、无FE/JIT/Torch/GPU/OOC，树RSS0.5s采样hard2GiB、warn1GiB，自身swap0；只约束并终止本任务后代 |
| 数据读取 | 可读预登记V24–V28紧凑JSON／timeline／hash-bound小向量；真实packet、局部A/LU载荷、REF7／teacher／旧p1 T/U/R／Krylov／神经权重不读；checker端到端用合成包 |
| 新数值消费 | 真实S/Sᴴ、真实局部求解／装配／LU／gecon、真实薄分解、FE、迭代及训练均0；至多三组n≤24小代数fixture，与真实计数分开 |
| 存储 | V29新增含TMP≤16MiB，V27起新增累计≤128MiB；全Task artifacts≤20GiB、自由盘≥50GiB；不改写／删除旧失败证据 |
| 代码边界 | 允许checker、其测试、最小证书／参数化接线；B只放隔离fixture／研究验算。不开新正式runner／dat、不扩建资源管理器、不调整实际求解算法或准入门限 |
| 回归 | 最小新增反例→相关既有scope＋文档合同；无full pytest／MPI／FE。无关文档改动不重跑昂贵历史Gate |
| 提交 | response_v29、A/B/C的compact证据及复现入口、源码SHA／base、环境／实际命令、预算／hash、失败和NOT_RUN；更新README／summary／test_summary／changed_files。发生资源停止按docs规则更新总账；推送后停止等review |

A未通过就不能称未来回流数值checker已资格化；B只能证明代数条件；C若完整成本未知，交付unknown与缺口清单仍是有效结果。任一运行资源Gate拒绝后不重试、不后台排队、不因余额尚有而再开窗口。即使全部通过，本轮也不启动V27／V28原诊断或B_full真实应用。

以后若外部明确提供可审计的空闲条件，由新review决定是否授权一次尚未消费的原诊断；本轮审阅找到CPU16、或历史有成功准入都不是该授权。新授权仍须沿原两冷态、九方向基线及原g10≤0.75／≥0.95分流，不加样本、预算或训练。真实失败时先利用保存向量分清抵消、外域放大、创新重复／对准差及完整成本；没有新机制与可承受成本就关闭固定方向序列，等待dot证据，不能只加回流轮数。

## 6. 历史路线与原尺寸资格保持

| 路线／状态 | 已有事实及不可重复事项 |
|---|---|
| V1–V5，13.5nm p4神经粗逆 | 已关闭的研究负路线，不重开严格粗逆／条件p6旧预算 |
| V6–V15，神经FE trace | V7实际训练、V13hidden更新均无完整资格；固定特征／只拟合线性头分开；V11hidden更新等未运行项不填通过 |
| V16–V21，全空间残差校正 | 有残差改善，但完整物理未过；class64属于算子工程加速，不等同收敛或NN增益；旧迭代不延长 |
| V22–V23，Galerkin／image-QR | 同p1空间r=1248，误差可表示率不等于可消除残差；不再换左测试／scalar-tau；V23完整0/6 |
| V24，八原p3主块LU／加image-coarse | warm与zero两起点分别运行，四路首4周期及资格审核已完成；组合overlap-rank已在历史审核，完整0/5，不再把V24当尚未运行提案 |
| V25，八方向最优系数 | 两冷末态eta8=0.983236989810／0.989924628585，方向空间弱；同空间系数网络不能超精确LS |
| V26，固定5/7联合方向 | eta9=0.966205505618／0.981968429990；相对e8仅多降1.732185%／0.803718%，数值可信但增量不足，该独立提案关闭 |
| V27–V28，J→外域→J回流 | 代码／fixture已做，真实方向NOT_RUN；CPU拒绝不是数值负结果；V29不重复开actor窗口 |
| V29，审核／全空间补项／成本 | 本报告新授权的轻量任务，当前planned/not_run；不是新FE结果或NN性能实验 |

逐轮去重详见[v21全历史清单](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、[v22](review_report_v22.md)、[v23](review_report_v23.md)、[v24](review_report_v24.md)、[v25](review_report_v25.md)及[原始检索索引](outcomes/records/independent_review_v21_20261002.json)。本次增量审阅未声称重新逐字语义审计所有历史源码；索引／hash与具体证据核对的边界如§0。

当前micro为0.7nm、1.4×1.05×1.4nm三维缺口、384hex/p3/q15、18144 trace＋40port。V23 warm Schur约2.507714e-6、zero约0.06811318；warm通道功率差仍超限。V24 LW4 Schur2.502117907e-6、通道功率差1.666968717e-6，分别超1e-6；LZ4 Schur0.0813766679、散射E差0.568888278、功率差0.007245974，分别超1e-6／1e-4／1e-6。native单项通过、一次修正有效或方向rank通过均不授予整体成功。V23 0/6与V24 0/5保持。

原目标仍为50×25nm周期、z=-10..130nm原尺寸、0.7nm、身份明确的完整非可分三维有限元，完整同时峰≤2e12 B、完整端到端≤172800 s。固定块数时局部稠密A/LU载荷按32Σn_b²增长，设置按Σn_b³；全局image基16nr、R矩阵16r²、QR工作nr²及副本／通信均是真实成本，micro小峰值不证明规模可行。扩大块数、层级、周期共享或接口方法改变的是算法／结构，必须另资格化，不能靠外推表授予通过。

神经合同20%覆盖早期10%条款；本次无训练和合格配对，仍 `NOT_DEMONSTRATED`。原尺寸正确性、2TB／48h、fresh泛化／离散收敛与完整单解链仍 `NOT_QUALIFIED`。dot继续自己的`task40extra_dot_parallel_cloud`，负责完整三维参考逆、周期分块、共享存储与规模验证；Task042本轮只补审核、局部信息传播的代数必要条件和学习成本账，不重复其完整求解器实验、不修改其分支。**无merge approval。**
