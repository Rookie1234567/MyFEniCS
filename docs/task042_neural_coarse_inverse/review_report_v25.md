# Review V25：接受V27零消费停止，补齐验算后只续一次未运行诊断

## 0. 审阅决定与身份

**接受V27的`NOT_RUN_CPU_ADMISSION`收口，关闭review v24 §3的真实窗口测试依赖问题；不接受任何V27数学正／负结论，因为两个回流方向均未运行。** 本次重新执行相同相关scope，**67 passed in1.62s**。下一步应补齐可审阅性，再在合格资源条件下做一次原定诊断；没有理由改方向、加回流轮数、训练网络或回到旧迭代预算。

[response_v27](response_v27.md)已正式回应v24，故按AGENTS §15新建 **review_report_v25.md**，保留v24及其余历史。本报告授权V28为一次**未消费数值任务的续行**：先完成§3的checker／记录修复，再作一次正式准入；通过才执行原两个状态的一种回流方向。V27窗口／ledger保持closed，不修改旧记录或把这次续行写成V27已经运行。

| 身份／证据范围 | 核实值及限制 |
|---|---|
| 被审阅远端及本地HEAD | `1e7703ccb4202f7ba1b358c0493a80e3031f8e8c`，非交互ls-remote与本地一致，起始工作树干净、upstream同步 |
| 实现／尝试入口source | `7b0e03f2fbfb504b13a5f5b4c46c52e0e96a5eb9`；实际数值actor source=null。d8fa672a为结果文档，1e7703cc为交付观察，不能称运行source |
| 执行分支／canonical工作树 | `task42_neural_coarse_inverse`；`/home/fenics/Projects/NN-Lab`，登记于`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 本机状态 | 2026-10-03约03:14 UTC主机只读检查未发现匹配本任务的actor；V27正式run=0、active=null、closed=true，V26 ledger hash保持。相近Task042extra分支单列，未操作 |
| 本次范围 | 根／docs规则、任务及最新review／response／summary；33个增量文件、全部新数值核／reader／window／接线／测试；原准入、辅助监督、状态与源身份记录交叉核对 |
| 独立证据 | 50个规范化路径、21,281,236 B文件hash；3个辅助CPU候选集合、资源峰／费用重算；V26缓存基线checker复核；67项相关小测试通过 |
| 深度边界 | 不加载真实局部因子、不做新原S/Sᴴ／LU solve／QR／SVD／FE／训练；现有测试的小合成代数另列。旧全历史按547文件索引和后继增量核对，不声称全仓逐行语义审计 |

[本次独立核验记录](outcomes/records/review_v25_independent_checks.json)含脚本、hash、测试日志、零消费推导、缺失父指针及静态成本分账。此前review／response相对222aa0af均字节未改，导航／汇总历史后缀保留。未使用subagents或重置卡；没有修改求解源码、dot／其他分支或master，没有启动正式实验。精确GitHub页面仍Cache miss，视觉`NOT_VERIFIED`；本地表格／围栏／链接及治理测试另查，不声称CI／全仓测试通过。

文档收口的治理／总账Markdown测试为 **12 passed in0.06s**，新增report与README静态检查通过。v24已记录的跨任务registry章节／缺失证据合同失败本轮未重跑或修复，仍不宣称全仓绿。

## 1. V27做成了什么，什么仍未运行

回流方向先在联合区域J处理输入，再让外部六块处理它引起的方程不平衡，最后回到J补偿反作用。它改变信息在区域间传播的次序，可能增加一个原九方向没有的有效响应；代价是七套既有因子的读取、三角解和原方程作用。V27完成了代码和小型代数检查，**没有在实际微型三维模型上检验这种可能性**。

| 内容与数据身份 | 本次判断及证据 |
|---|---|
| 旧V26窗口测试修复／已执行 | 两测试改用临时plan／ledger及受控clock，active／consumed／closed／expired分别测试；生产V26 loader/window未改，真实ledger hash仍`93e059e96fdd0ed0fd43c1cd05f24db6e048004a84a98231e64821f63a0f3853` |
| 合成数值与只读reader／已执行 | 非Hermitian、非互伴40port、J内抵消、外域放大反例、复线性／零、秩缺陷、9→10列LS、重复／近零方向、hash／pivot／次数拒绝通过；它们不是真实七套因子重载资格 |
| 正式准入／受控停止 | 辅助准入曾失败，唯一只读复核随后通过；实现提交后正式准入再次拒绝。本批额度用完后停止，符合原v24合同 |
| 正式数值／NOT_RUN | S/Sᴴ=0、reader=0、联合／外域solve=0、端口factor/solve=0、薄分解=0、正式run=0；无formal manifest／结果目录，无新npy／npz |
| 两固定冷终态／NOT_RUN | LZ4和LCZ4的eta10、g10、新方向可分辨性均null；没有真实抵消、外域变化、创新或独立重组结论 |
| 完整物理与学习／NOT_RUN | 没有新FE终态、native、E/H/curl、复通道或功率资格；没有训练、fresh消费或NN性能对照 |

V27 namespace只有`launch_rejection.txt`、`minimum_cost.json`、`minimum_result.json`；ledger所有数值计数为0。这比直接相信`NOT_RUN`标签更有约束力。入口源码在`task042_shared.launch`的audit处先拒绝，尚未创建formal目录／worker。测试中合成LU的费用已计辅助时间与峰值，不能混入真实因子计数，也不能因此将本批写成“没有任何计算费用”。

两个真实输入仍是0.7nm、384hex、p3、q15、18144 trace＋40port的已消费V24冷末态；域1.4×1.05×1.4nm。历史V26基线eta9为 **0.966205505618／0.981968429990**，分母是各自输入trace残差范数。它们仍是旧测量，不是V27结果、场误差或原b归一的求解资格。

## 2. 成本与CPU停止证据的含义

| [费用记录](outcomes/records/resource_costs_v27.json)、[run index](outcomes/records/run_index_v27.json)、[交付观察](outcomes/records/delivery_receipt_v27.json) | 独立核对与口径 |
|---|---|
| 三次受监督辅助wall | 4.255312403＋3.551517930＋4.559827035＝12.366657368 s；正式actor wall=0；读取／准入／实现／发布分项unknown仍计总elapsed |
| 同时树RSS采样峰 | 134,275,072 B，三个辅助timeline共20条采样重算；ownswap=0，任务VRAM/OOC=0；这是辅助峰，非数值actor峰，更不是部署内存 |
| 成功辅助准入CPU | 40／38／0；从各自冻结topology、busy fraction及thread delta重新执行`spare_cores`，三次均只剩该一个候选核 |
| 不可刷新旧窗口 | start02:14:16.872215 UTC；heavy-stop03:29:16.872215、deadline03:44:16.872215；02:33:48.487已closed；receipt02:40:50.867观察、elapsed1593.994888 s |
| 数值容量／未分配 | 4,807,239,744 B是同时规划，不是测量。J与六外块全部A+LU载荷合1,591,420,032 B是derived总量；顺序只驻留一外块的峰另算，pivot／packet／副本等另计 |
| 存储观察 | 本轮输出含辅助TMP及docs观察30,460,620 B，全Task artifacts18,024,892,615 B；receipt写入前观察，不宣称最终绝对库存 |
| 历史账 | formal研发下界77,161.557139 s保持；旧辅助和单解完整暖链成本unknown；不得以本次actor0秒宣称加速 |

正式拒绝的原因只能表述为**当次策略未找到可审计的空闲物理核**。失败时没有保存CPU候选筛选快照；现有文件明确标作工具异常与命令的转录，而非原始redirected stderr。故可以接受“入口在该Gate拒绝并且数值未消费”，但不能独立重算每个核为何被排除、证明整机全部CPU一直满载，或据此判定策略错误。

三次成功辅助记录显示候选核很少且变化，支持资源条件随时间变化的有限观察，不证明它导致了后一次失败。`spare_cores`保留窄affinity、排除忙核及SMT同胞、按短窗>5% busy筛选；本次不放宽这些规则、不保证下一时刻准入。审阅阶段没有通过重复扫描去为下一actor挑核；执行时必须重新核实。

交付receipt中的ahead/behind=2/0是**推送前**观察；本次远端已核实包含完整1e7703cc，不能误判为当前未推送。Git观察时点、正式运行source和文档HEAD须继续分开。

## 3. 续行前必须补齐的两项P2及记录要求

### 3.1 正式结果缺少独立checker，准入checker不能替代它

当前tracked新文件有数学核、study、runner和测试；`benchmarks`中没有针对V27保存数组的eta10／g10资格checker。[admission_checker_v27.json](outcomes/records/admission_checker_v27.json)检查的是零run、零计数、无新数组及源身份，正确支持本次NOT_RUN，**无法验收将来的实际回流结果**。`return_block_direction.decision()`只按调用者给出的trustworthy／resolved／g10分类；它不是独立证据审核。

V28正式actor前应补齐可复用、tracked checker及小fixture。它只读取原始记录与保存向量，不调用原A、真实LU或新QR／SVD；不能把数学核再执行一遍当checker。至少独立核对：

- 恰好两个指定且唯一的state，逐名绑定原V24 parent／成员、V25八方向及V26九方向；完整operator／mode／master／b／source身份，禁止替换基线。
- 必需数值gate集合、有限数及非负范数、RHS列／三角pass／reader／原作用／分解／端口预算；失败、缺项、空样本、重复、错label、NaN／Inf不能获成功。
- 从保存向量重算e9、e10、eta9、eta10、g10，核对真原作用保存残差与薄组合；J内抵消、线性重组、J内／外范数、旧九列驻点及新增方向正交／投影证书。
- 已解基线（e9=0）、零／重复／近零新增响应、可分辨但与e9正交的方向分别处理；不可把null变0、要求所有合法负结果都有rank10，或因新增系数beta=0而拒绝一个有效的“没有收益”结果。

为使最后一条不依赖除以beta，数值端可在**同一次既有薄分解**中保存九维投影系数p9，checker检查`a_d−h_d=W9*p9`及h_d与W9正交；这是增加轻量证书，不是增加方向或重新分解。rank、门限与原运算尺度仍沿v24，不因checker方便而重算真实原A或改数值方法。小回归要有完整正例、可信弱增量例、上述退化边界及库存／预算反例；真实数组缺失时明确NOT_RUN，不伪造实际通过。

### 3.2 紧凑记录的parent指针为空

[输入库存](outcomes/records/input_inventory_v27.json)及[对比表](outcomes/records/return_direction_results_v27.json)两行均写`parent: null`；预登记却有非空`parent_result`，分别指向V24的LZ与LCZ stage_result，hash前缀4971ba16／3051afc2。状态和缓存hash仍正确，旧V25／V26链也保留，所以这没有抹掉真实输入身份，更没有影响一个尚未运行的数值结果；但紧凑入口本身丢失了应有的父记录映射。

修复通用输出映射和schema／checker，要求非空`parent_result`及其hash与预登记一致；在V28记录中给出对这两个旧null的纠正引用，**不覆盖V27历史原文件**。一并保存生成／检查记录的tracked入口或可审阅脚本身份，避免只提交手写PASS布尔表。此项无需重跑V24–V27。

### 3.3 下一次准入要留下可重算快照，不改准入门限

在现有audit的成功和失败分支，都保存本任务所有的结构化观察：UTC／monotonic、进程身份／cwd与精确input、允许CPU及socket/core/SMT、采样间隔和CPU busy分数、相关thread start identity／delta、候选集合与排除原因、已检查到的资源Gate。CPU阶段先拒绝时，尚未检查的内存／PSI等写NOT_CHECKED，不补造PASS。原始stdout/stderr从调用时重定向保存，不能以事后转录冒充。

可给既有audit增加默认不影响其他stage的可选receipt出口，或在本批薄adapter中记录；不扩建另一个资源管理器。小fixture覆盖拒绝快照可重算和成功策略不变。不得读取或输出secret、任意环境，沿现有已过滤路径与最小进程字段；不扫邻任务smaps、不改其affinity／锁／监督器，也不通过放宽5%或忽略SMT来过Gate。

## 4. 下一步为何仍是原诊断，而不是换路线

V26的联合响应确实脱离旧八方向，但相对e8残差仅多降1.7322%／0.8037%，同时J外不平衡增加。因此“一轮外域处理加内部补偿是否增加有效方向”是尚未回答的问题。V27没有提供反证，不能从资源拒绝推导回流无效或转向更复杂接口。

设B_J为原联合主块逆注回全trace，L_O为原外域六块的固定局部解。V28构造与v24相同，不增加参数：

```math
q_J=B_Jr,\qquad w=L_OAq_J,\qquad
 d=-w+B_JAw,\qquad q_{\mathrm{ret}}=q_J+d.
```

原A保留完整40端口消元与全部原物理贡献。精确主块代数给出`E_J A d=0`；它说明补偿后新增响应应只改变外域，但必须实际验证。q_ret只依赖J内3888个输入分量，rank≤3888<18144，仍不能独立充当全空间右PC。加入q_ret与加入d在已有q_J的九方向基础上是同一个扩展空间，禁止分别尝试后择优。

基线仍为V26九方向W9，新增一个a_d=A d，比较的是**相对于e9的新增可消除残差**：

```math
\eta_{10}=\min_{c,\beta}\frac{\|r-W_9c-\beta a_d\|}{\|r\|},\qquad
 g_{10}=\eta_{10}/\eta_9.
```

完整构造／输入／列均衡／cond=1e-12／64eps创新分辨／rank／驻点／原作用重组Gate继承[review v24 §5](review_report_v24.md#5-v27唯一任务验收与停止)，仅批次身份改为V28；不能把旧八方向再当基线重复领收益。只使用 **V24-LZ-CYCLE4、V24-LCZ-CYCLE4**，没有新增fresh、warm、初态或参数。

| 在全部数值及checker见证通过后 | 决策及停止 |
|---|---|
| 两状态创新可分辨且g10≤0.75 | 有限`RETURN_EXTRA_DIRECTION_SIGNAL`；仅提出一个保有全空间作用、完整成本可承受的后续方案，停止等review，不启动求解或学习 |
| 两者g10≥0.95，或两者新增空间均不可分辨 | 保留实际分类，关闭固定J→O→J单轮提案；不加循环、阶数、顺序、块对或训练救场 |
| 混合／中间值 | STATE_DEPENDENT_INCONCLUSIVE；两状态全部列出并停止，不追加样本投票 |
| 资源／输入／数值Gate失败 | 对应NOT_RUN／controlled_stop／unresolved；保留真实计数及原始失败，禁止借新编号自动重试 |

若出现数值负结果，替代分析应利用已有向量区分：内部抵消是否成立、外域是否减少、创新是否重复、创新与e9的投影是否弱，以及系数／大项抵消／验证成本。若没有明确不同的信息传播机制，结束此固定方向序列，等待dot的参考与尺度证据；不要再次换同p1空间测试、scalar-tau或继续旧迭代。

## 5. V28唯一续行合同：新窗口，累计费用不清零

重新授权的理由是**原定真实诊断尚未消费**，不是V26负结果值得加预算。保留V27关闭记录，创建独立V28 namespace／UTC-monotonic-boot_id窗口，输出response_v28。复用现有`DiagnosticWindow`和数学核、参数化薄接线；不得复制整套数值实现，也不能把v27 dat静默路由到新窗口。

| 项目 | 上限与实施要求 |
|---|---|
| 工作顺序 | 先§3、最小测试及checker合成证据，再clean源码提交；随后一次正式准入，通过才启动唯一actor。审阅本身不执行它 |
| 窗口 | V28首次工作起总elapsed≤5400 s，start＋4500 s停有载，最后900 s收口；读取、实现、hash、测试、等待、发布均计入。旧V27 elapsed及12.366657368 s辅助费用另列、不可清除 |
| 累计有载费用 | **V27＋V28 actor及受监督辅助合计≤600 s**；V28起始剩余最多587.633342632 s，新的辅助／失败继续扣除。两个窗口及两轮累计全程wall另报，不能把600 s当N=1求解耗时 |
| 正式尝试与资源停止 | 只允许一次新的正式入口准入；拒绝即保存结构化快照和最小包并停止，不重入、不后台排队、不反复轮询找核。辅助若准入失败也不反复启动。再次失败后的下一动作应是外部资源条件改善，不是自动新一轮相同尝试 |
| 数值库存 | 两原冷态、一种回流方向；7个bundle reader、外域≤24 RHS列、J≤8列、三角pass≤64、S＋Sᴴ≤64、薄流程≤2且≤10列；端口factor≤1、solve调用及RHS列分别≤128 |
| 绝不新增 | 局部装配／LU／gecon=0；无另一联合块、全局fine矩阵、旧p1 T/U/R／D_L、旧Krylov方向、REF7／teacher／神经权重、新FE终态或迭代／训练 |
| 内存与线程 | derived同时规划≤8GiB；树RSS0.5s采样warn12／hard16GiB、ownswap0、MPI1／math1、pure环境，无FE/JIT／Torch／GPU／OOC；因子、hash、mmap页、LAPACK副本与两状态数组全计 |
| 读取与费用 | J一次、六外域各一次顺序加载；原5/7 LU不读。文件hash／数组hash扫描／mmap及pivot副本分别计费，RHS列不隐藏在batch调用中；历史因子设置仍是完整N=1依赖成本 |
| 存储／共享 | V27＋V28新增持久输出含TMP合计≤128MiB，旧V27约30.46MB计入；全Task artifacts≤20GiB，自由盘≥50GiB；系统reserve=max(128GiB,10%effective total)、邻增长128GiB和本任务16GiB余量、PSI及自有锁规则均保持 |
| 修复 | actor前最多2个新且已定位代码根因，每个1次、≤600 s且计总window；actor一旦开始，不再启动第二个actor。后处理／checker可从hash-bound保存数组修复，不能重做原作用／factor／薄分解或刷新预算 |

按当前直线控制流静态分账，预计S34＋Sᴴ2＝36次原作用、J解4列、外域24列、三角pass56、端口35列、reader7、薄流程2。**这是derived计划，不是V27测量，也不替代durable运行计数**；预登记的38次原作用上界仍可作为保守计划，不能写成已经发生。新证书／checker本身不应增加真实原作用或薄流程；若实际需要突破上限，停止说明，不临时加额。

交付包括response_v28、结果与compact records、预登记和逐名parent／所有成员hash、准入成功或失败原始快照／stderr、数值source／环境、七bundle资格及IO成本、9→10增量和checker重算、失败／NOT_RUN、窗口／累计账／清场。同步README／summary／test_summary／changed_files，发生正式运行或资源停止时同步模型总账／development_progress。旧review／response／raw不改写，只在新记录纠正指针。推送精确本分支并给出完整HEAD、base、upstream／工作树、测试与证据后停止；不merge。

## 6. 历史去重、原尺寸和神经收益

| 已尝试／已关闭／未运行路线 | 当前边界；不因本次续行而改变 |
|---|---|
| V1–V5旧13.5nm p4严格粗逆 | 已关闭；不是当前0.7nm原尺寸或p3成功证据 |
| V6–V15神经FE trace与固定特征 | V7训练、V13真实hidden更新均无完整资格；固定头／随机特征不能称本轮训练收益；V11未做hidden更新仍未运行 |
| V16–V21全空间校正／ILU0／class64 | 曾改善残差，完整物理失败；算子工程加速不等于收敛改善或NN增益；不延长旧预算 |
| V22–V23 Galerkin／image-QR | 表示误差空间与可消除残差已分开；同p1空间换左测试、tau微调均不重开 |
| V24 local-only／image-coarse组合 | warm／zero四路首4周期已运行；完整0/5，无追加周期授权 |
| V25八方向、V26联合新方向 | 八方向系数最优仍弱；联合对e8增量仅1.7322%／0.8037%，该独立提案关闭；同空间NN不能超精确LS |
| V27／V28回流方向 | V27只实现与fixture，真实NOT_RUN；V28只续这一未消费检验，不能提前写有效或无效 |

逐轮证据继续见[v21完整清单](review_report_v21.md#102-历史去重什么已经尝试什么仍没有运行)、[v22](review_report_v22.md)、[v23](review_report_v23.md)、[v24](review_report_v24.md)和[最初索引](outcomes/records/independent_review_v21_20261002.json)。本次按原索引及33文件增量检查，没有把旧结论写成新试验；fresh池、原F5／p6物理解、新p4 enrichment、原尺寸精度／规模与NN完整收益仍没有被补做。

完整资格仍 **V23 0/6、V24 0/5**。V23 warm Schur约2.507714e-6、zero约0.06811318；V24 warm LW4 Schur2.5021179e-6／功率差1.6669687e-6超1e-6／1e-6，LZ4 Schur0.0813766679／散射E差0.568888278／功率差0.007245974超1e-6／1e-4／1e-6。native单项通过或一次校正下降不替代原方程、全场／端口／逐通道功率共同资格。

原目标仍是原尺寸50×25nm周期、z=-10..130nm尺度下，身份明确的非可分三维几何、0.7nm、完整三维FE；完整同时峰≤2e12 B、端到端≤172800 s。当前micro输入与fixture都不提供原尺寸精度、完整解或资源资格。固定稠密局部因子的平方存储／立方设置、全局image基`16*n*r`、R的`16*r²`及QR的`n*r²`工作不能从成本账中消失；增加块数或改变接口则是尚未资格的新方法，不能直接外推。

神经收益标准继续覆盖早期10%条款：**在相同正确性下，相对最佳合格非神经路线，完整N=1耗时或完整同时峰值内存至少改善20%，另一项仍合规。** 需包含数据生成、训练、设置／加载、推理、全部精确校正、恢复／审核和IO。当前无这样的合格配对；LU、QR、固定特征和回流均为传统代数，不是NN收益。网络若只替代微小LS系数运算，现有成本占比不支持20%结论；未来真正学习什么、替代哪项大成本、fresh划分和消融必须另行立项，本报告不授权。

dot继续自己的`task40extra_dot_parallel_cloud`，承担完整三维参考逆、周期分块、共享存储与规模验证；Task042只做冻结算子的有限方向资格和学习增量评估，不重复同一完整求解器／规模实验，不修改其分支。另有相近Task042extra任务也不在本轮范围。原尺寸正确性、2TB／48h与NN20%均仍`NOT_QUALIFIED / NOT_DEMONSTRATED`，**无merge approval**。
