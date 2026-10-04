# Response V6：阶段执行回应与Z文档收口

## 首屏阶段总表

Review V6的E0→E1→E2→E3→F5→P2→R48均有阶段记录。本文把此前已经实现并测试的迁移与本轮仅归档的Z文档变更分开说明；Z没有修改求解源码、输入、数值Gate或运行参数。

| 阶段 | 实际工作与状态 | 结果边界 | 主要记录 |
|---|---|---|---|
| E0：旧F2中断基线 | 保留2026-10-02的node1受限分配 `CONSTRAINT_MEMORY_POLICY` OOM；worker exit137，watchdog sampled RSS峰`1154381864960 B`，低于`1.3e12 B`硬线 | 触发分配PID `1172428` 的任务归属、具体策略与VMAs unknown；不能归因邻任务，也不是已证明的RSS watchdog stop | [旧F2报告](outcomes/f2_terminal_oom_20261002.md)、[旧F2 compact](outcomes/records/f2_terminal_oom_20261002_compact_v1.json) |
| E1：窄范围迁移 | 基于已测donor按依赖组选取组件；关闭PSS/USS持续扫描，保留轻量整树RSS和身份监督；保留精确p4、Aq和原A4合同 | 不整体合并donor；H6-only运行源`06b6895f...`早于后续metadata优化 | [migration manifest](outcomes/records/v6_migration_manifest.json) |
| E2：组件与入口证据 | real 5/2 nm Si、全部600/3904 modes、18-cell受限FE的两配置组件通过；监督、scope、MPI及真实FE回归按分离进程完成 | 组件测试不等于完整PDE资格；实际WIP源码身份和失败尝试保留在记录中 | [component/H6 compact](outcomes/records/v6_component_and_h6_only.json)、[test summary](outcomes/test_summary.md) |
| E3：math1/math4有界对照 | 四场18-cell fixture自然完成，AB/BA同factor工作量和NPZ对照通过；2 nm warm math1/math4比为AB`1.0477536`、BA`0.9755149` | 结果未显示稳定math4 full-PC收益；不做第三轮或8线程，冻结MPI1/math1、worker CPU24、parent CPU9、NUMA interleave0-1；MUMPS共享内存能力unknown | [thread-selection compact](outcomes/records/v6_thread_selection.json)、主审receipt SHA `81f8bdf2...8545d6` |
| F5：5 nm完整场 | 5 nm Si p6/h4 q4、3780 cells/600 modes；121步；完整原A6`8.704501286501755e-7`，主审接受完整FE/EH/mode/物理与244个p4返回 | 此离散和配置通过，不是continuum convergence | [F5 terminal compact](outcomes/records/v6_5nm_terminal.json)、主审receipt SHA `b06c8044736c06b6db00bd792f83e1b075493d8e8869ac3813b6b500212cabd3` |
| P2：2 nm十六步pilot | setup加16步，自然exit0；准确p4 single factor供QA与16步共用，原A6第16步`0.35320202729663724` | `NOT_SOLVER_QUALIFICATION`；不是收敛或物理资格；RTA和checker `NOT_RUN`，不续跑 | [P2 compact](outcomes/records/v6_2nm_16step_pilot.json)、主审receipt SHA `16af3bb771f74e743a45e396adf4f15f24cf1f97a850de04254d80882b8a6554` |
| R48：0.7 nm容量 | 纯axis planner与完整dynamic external-mode inventory；100×50×280=1,400,000 cells、32,060 modes | `TARGET_0P7NM_48H_NOT_ESTABLISHED`；无FE网格、矩阵、因子、0.7 nm PDE或精度资格 | [R48 compact](outcomes/records/v6_0p7nm_48h_capacity_plan.json)、metadata receipt SHA `c7429a289b862fcf3cea361eca6818c1b3236258d295e46a2604ad3872f9375a` |

E1/E2的代码迁移、MPC metadata复用和四项入口修复在此前已完成；组件记录中的旧失败/未判定结果继续保留。本回应和Z只更新compact与文档，不把既有WIP组件测试重新归类成更干净source，也没有重测或重跑F5、P2、H6。

## Review V6第9节逐项回应

### 1. 旧F2 OOM边界

旧2 nm F2触发的是kernel `CONSTRAINT_MEMORY_POLICY`、nodemask=1的node1受限分配OOM，发生于2026-10-02约03:52:46 UTC；worker exit137。整树RSS采样峰`1154381864960 B`，没有达到1.3e12 B RSS硬线。另一个PID `1172428`是触发分配进程，但它的任务归属、具体内存策略与VMA归属unknown。证据不能说明是当前任务或任何邻任务触发，也不能将它改称RSS watchdog终止。

### 2. 低内存p4逆研究

本批新增低内存p4逆、递归p2、patch、recycling、BLR、ILU或子域逆实验为0。外层仍使用装配时逐单元静态凝聚、对全局凝聚增广矩阵建立一次准确MUMPS因子；每次C仍验算完整原A4，`Aq<=1e-10`，最多两次同因子额外精化。P2的16步计划停止不是换PC或继续求解的理由。

### 3. 监督开销范围

PSS/USS/smaps全链停采；保留快速RSS采样、PID/start_ticks身份、swap记录和进程树清场。P2 watchdog实测整树RSS峰`1150080622592 B`、tree swap峰0、332532条样本全可读，PSS为disabled。全机pswpin增加24页、pswpout增加0页，归因unknown，不能写成全机swap为零。E3/F5/P2均无运行时间截止，swap仅观察。

### 4. reference-metric H6

P2 reference-metric H6 diagonal计时`48.728370 s`；H6 parent`1537.579012 s`，power10 child`1363.672048 s`。父子计时不相加。原始`physical_intermediate_summary` producer没有保存实际fallback count字段，因此fallback count未知。H6-only source为`06b6895f5b6efba7c7e75f2360ad7ebacf410595`，仅覆盖其原scope；其全流程`17521.1324 s`、H6 parent`17426.405945 s`、diagonal`15918.245316 s`、power10`1375.127170 s`（20 actions共`1335.037848 s`）均按原运行记录保留。旧F2 H6 diagonal `118597.092899 s`→H6-only `15918.245316 s`，约7.45是两个不同工作集的工程比；它不是P2 `48.728370 s`的比较对象，不能归因PSS变化或预测P2/TB耗时。后续MPC metadata复用不在H6-only运行源中。

### 5. C粗修正的实际分项

P2最后一次PC记录序号17，对应outer step16，内部有两次C修正。第一次parent `697.140085 s`，2次factor solve/1次额外精化；PH/P=`5.306163/9.599449 s`，RHS reduction=`95.926199 s`，MatSolve=`427.625033 s`，recovery=`51.517966 s`，A4 parent=`105.266306 s`（其中volume/DtN子项`102.102503/2.862180 s`），port closure=`1.062378 s`。第二次parent `353.815833 s`，1次solve/0次额外精化；PH/P=`5.284472/9.547292 s`，RHS=`47.882317 s`，MatSolve=`213.019665 s`，recovery=`25.834629 s`，A4 parent=`51.283492 s`（volume/DtN子项`49.705014/1.426173 s`），port closure=`0.532128 s`。A4 volume/DtN是A4 parent的子项，各分项与父计时不能重复相加；两次C合计约17.52分钟不等于回代时间。主耗时子项是MatSolve，但完整C还含RHS、恢复、A4验算和端口闭合。

### 6. 实际采用的数值组件与线程决策

迁移/测试记录覆盖blocked Gram张量生成、A6 curl/mass融合、快速完整A4作用、reference-metric H6对角及直接后端的自然积分点顺序；这些已进入E1/E2实测组件，不是本次Z新增实现。原算子、方向、积分、complex MPC、full DtN和粗解Gate保持不变。正式F5/P2及后续冻结配置为MPI1/math1、parent CPU9、worker CPU24、NUMA interleave nodes0–1。

E3在5 nm小fixture的warm math1/math4比AB/BA为`1.384866/1.717097`，但仅为18-cell组件；2 nm为`1.047754/0.975515`，未稳定受益。故保留math1，不做第三轮或8线程。E3 math4配置/库读回为4、OS线程6；`parallel_runtime=1`是`openblas_get_parallel()`的`OPENBLAS_THREAD`类型枚举，不是线程数。MUMPS共享内存能力仍unknown。结果与NPZ/summary哈希见[thread-selection compact](outcomes/records/v6_thread_selection.json)。

### 7. F5相对旧V5的边界

F5 5 nm新旧工程比为setup `11263.075601/1696.196008=6.6402x`、workflow `22680.911776/12534.182499=1.8095x`。这不是受控因果比较，运行实现、几何分组、NUMA、PSS和缓存条件不同。F5在121步达到完整原A6 `8.704501286501755e-7 < 1e-6`；旧run和新run的完整场/EH/mode/物理核验另按相同离散reference记录。F5 qualified的是本离散模型，不证明连续体收敛。

### 8. P2前16步与工程比

旧V5 F2与本P2 pilot前16个callback均值为`1904.390336→1532.733350 s`，即约`31.74→25.55 min`，工程比`1.24248x`。它含callback检查和落点；两run不是受控配对，不能归因单一优化、PSS或NUMA，也不能替代完整PC稳定收益或外推收敛总步数。P2 numeric API `57870.129416 s`与旧`44111.673835 s`范围不同，不比较成LU speedup。原A6第16步仍为0.3532020273，未过完整求解器残差Gate。

### 9. 0.7 nm的精度、容量和时间缺口

实际planner轴计数是1,400,000 cells、external inventory 32,060 modes，不是54332×27实测。周期公式已用P2运行控制核对：P2 p6/p4周期独立网格场行为35,248,752/10,450,240，p6 retained+ports为10,803,256，p4凝聚矩阵4,586,288行。R48派生p6/p4周期独立场行为907,560,000/268,960,000，retained trace+ports为277,592,060/117,792,060；公式和完整行数见[capacity frontier](outcomes/capacity_frontier.md)。

FGMRES32按约65个complex128数组、每个数组长度等于p6 retained+ports向量作载荷情景，为`288695742400 B`；单个32060×32060 complex128矩阵为`16445497600 B`。P2 buffer inventory的108004276088/106341066752/91060468992 B三项有交叠，按ndarray object id而不是底层allocation去重；Hlocal及全局Hp/Hhat可能按mode平方增长，未保存shape则unknown，不统一乘cell或mode倍率。

P2 backend `INFOG[22]=916713 MB`原值若按916.713 GB并假定仅线性随cell增长，得到约23.621 TB的敏感度情景；不是实测、下界、预测或R48容量资格。P2 stored matrix NNZ若维持原值/cell，则值加int64索引约1.2803714 TB，同样只是条件算术。stored NNZ与backend字段、factor填充/分配量、array payload、整树RSS分列。48小时target分给setup/solve/recovery-output-cleanup `43200/115200/14400 s`；假设256/512/1024个完整步时，平均步预算为450/225/112.5秒。总迭代数、factor fill、各array shape、R48实际峰值、0.7 nm误差与物理资格都未建立；不能由16步残差外推收敛时间。

硅材料值由Henke 1756.82/1785.24 eV表行线性插值并按项目约定换算，属于derived capacity metadata，不是直接CXRO计算或精度资格。没有启动0.7 nm精度PDE，也没有新增低内存p4逆试验。

## H6/P2数据更正与证据口径

P2 `physical_intermediate_summary.json` 的实际路径是run根目录，SHA `b058c56f0f20c90b3d1722962e26245b3448d55af5099fe73a69ff3b24aeae3a`；manifest里的numerical-output目录不存在，不据此宣称RTA。原始INFOG一基键16–19均1091654、键22为916713 MB；键3/9/20/29的−54415是backend原始编码，语义和单位unknown，不是负派生差值或负NNZ。RINFOG键17/18=`879471.61023/1058655.467209`。MB到bytes换算与factor NNZ解码保持unknown。

P2资源主审已对resources.jsonl完成一次全量审计：332532样本、raw SHA `8339e5fba652460381e3bc30c3cc1277a3d97c91e59a28ff5d159dfe21b0d35a`，size3381243014 B；后续没有重扫。资源回执在[P2 compact](outcomes/records/v6_2nm_16step_pilot.json)中绑定。

## Z文档范围、验证与下一步

本轮Z更新P2/R48 tracked compact、summary、capacity frontier、run index、test summary、project progress/model registry及本回应。此前迁移/修复/组件测试和正式F5/P2均按自己的WIP/clean source SHA与artifact hash记录；本次docs-only更改不改变这些运行身份，不重新跑已过测试或计算。失败与未判定记录保留；不改review/task/default/master或邻项目。

| 依赖组 | selective-merge建议 | 本批状态 |
|---|---|---|
| production numerical/core | 核心改动仍留执行分支并按migration manifest逐组审，不整体迁入 | V6源码阶段此前已实现；本次Z无源码差异 |
| reusable runner/watchdog | 按PSS/USS停采、RSS监督和已测入口依赖选择性审阅 | 已有回归与正式run证据，本次不改 |
| checker/benchmark | 只纳入可复核的manifest、checkers和小型records | P2 RTA/checker未运行，R48不是benchmark求解 |
| compact evidence/docs | 可作为docs-only收口审阅 | 本回应、compact、summary与容量账；无需新的FE或性能验证 |
| research-only | 保留H6-only、E3和pilot的scope标签 | 不提升为solver或physics qualification |
| do-not-merge | 低内存p4逆实验、0.7 nm PDE、邻任务和其他分支 | 本批未开展或触碰 |

实际提交 `b06865d89c0b6a1a4c8480ed62622fbeddb91f6a` 的GitHub richText结构核验覆盖7页、189张表，HTTP均为200，表头列数和各表体行宽均与该提交本地Markdown一致；页面来源、bytes与rendered-richText SHA见[结构回执](outcomes/records/v6_github_render_closeout.json)。本次窄补充仅改response与test summary；对应新提交推送后，将复核这两页并把新页面及richText哈希写入ignored最终回执，其余5页以b068下原bytes SHA不变作为覆盖依据。人工视觉检查和CI均为`NOT_RUN`。本任务本阶段结果为`PASS_WITH_QUALIFICATIONS`，等待主审Z文档复核；未获merge approval，不合并master。
