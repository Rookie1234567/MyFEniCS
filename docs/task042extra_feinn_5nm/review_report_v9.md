# Review V9：接受 p5 参考，先消除导数重复计算，再有条件续算完整 GN 状态

## 0. 决定、仓库身份与本批 blocker

**接受 Response V9 的 p5 准确参考、完整 GN 负结果与独立验算，不授予神经求解、生产或合并资格。下一批不追加 p6、不换 loss、不扫描新 PC：先在固定参数处实现并资格化可复用的完整 JVP/VJP，测量包含缓存建立的真实收益；合格后从各自 V9 最终已提交 GN 状态续算，而不是重跑 Adam500 或旧慢训练。单项工程问题先有据修复，独立工作继续。**

本批消除的 blocker 是：当前原方程训练尚未成功，而一次参数方向作用重复执行大量不随方向改变的网络/矩计算，使有界预算内可完成的有效 GN 更新很少。本批首先是**等价实现与成本诊断**，随后才是有条件的数值续研。更快的导数不自动改善条件数，也不保证 GN 收敛；这两种结论必须分开。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42extra_feinn_5nm
worktree                   = /home/fenics/Projects/NN-Lab-V2
review_date                = 2026-10-01
reviewed_HEAD              = 0277bddd50c910fb3b04fa276191872776728942
latest_commit              = docs(task42extra): bind V9 rendered evidence and closed resource ledger
latest_commit_UTC          = 2026-10-01T09:49:35Z
original_base_SHA          = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review            = review_report_v8.md @ 678a1ef5ed5aba9334f05569a6dec04c80e21be4
response_reviewed          = response_v9.md
next_batch                 = V10_EXACT_DERIVATIVE_REUSE_AND_BOUNDED_GN_CONTINUATION
response_required          = response_v10.md
new_batch_budget_seconds   = 43200
production_merge           = NOT_APPROVED
```

最终目标仍是约2 TB整机物理内存内、0.7 nm、周期单胞内任意非可分三维 Maxwell 的准确可复现计算。本批仍为5 nm小型M5、原p3上的算法研究；p5为独立参考。Full3D分布式、matrix-free与可扩展iterative主线不变，不能把小模型缓存收益外推为0.7 nm容量或48h通过。

本次实际读取远程分支/目录、最新response/summary、p序列、GN结果/资源/run索引、JVP/完整矩/GN/训练源码，并核对前一review后的10个提交。根/目录规则和task的未改动blob与已读全文对应，目录没有额外补充合同。大型 `inner_solver_history_v9.json` 通过当前连接器未取得有效正文；没有把它声称为逐行审完，相关判断依据可读汇总和源码。未SSH重跑或核验现场ignored数组。本文measured指仓库记录；本地小型复数链式法则测试只检查公式，不替代M5资格。

先读根/目录AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、历次review、[Response V9](response_v9.md)、[summary](outcomes/summary.md)及本报告。本报告仅覆盖：限定数值缓存/等价内核、预算边界的安全收口、V9完整状态的追加预算续算。旧task/review/结果/费用不改；旧冻结195维末层续扫仍关闭。

## 1. 最新事实：精度参考进步，GN没有获得有效求解

依据：[p序列](outcomes/p_ladder_v9.md)、[GN结果及计时](outcomes/damped_gn_v9.md)、[资源](outcomes/records/resource_costs_v9.json)、[run/source/hash](outcomes/records/run_index_v9.json)。场误差相对同p3参考；候选功率均diagnostic。

| measured，dimensionless | V8 plain | V9 plain GN | V8 phase | V9 phase GN |
|---|---:|---:|---:|---:|
| native/augmented相对残差 | 1.0554095372 | 1.0285051156 | 1.3192886662 | 1.0187461988 |
| 散射E L2相对误差 | 0.9989451840 | 0.9989232163 | 0.2134667998 | 0.4371590748 |
| 散射curl/H相对误差 | 0.9989655403 | 0.9989423061 | 0.2145387128 | 0.4377833274 |
| 独立能量闭合绝对差 | 0.4156885892 | 0.4157492147 | 0.0270002712 | 0.1209419281 |

V9 phase的原残差略低，但场和能量比V8明显变差；不能只按残差下降宣称方法进步。C严格原方程1e-6与场1e-4未通过。D监督phase的G/L2/curl为0.0130598/0.0144035/0.0130240，plain为0.0993905/0.0682171/0.1000521；均未通过1%部分表示门限，不能把D当C的求解结果或架构表达极限。

p5准确静态凝聚后分解54280行、30734728 NNZ，恢复全部146400独立复FE及40端口；native/augmented约1.22906e-11，独立total约6.76137e-12，体吸收闭合约7.03215e-13。树峰7,190,847,488B，参考launcher约147.779s，自身swap0。接受这个小型authority，不重复求p3/p4/p5补日志。

p4/p5散射E/curl相对差为2.15909593e-4/1.17944619e-3，六点total H为1.40896314e-3，R绝对差3.78778e-5。E/通道/功率变化已显著缩小，curl/H与区域仍超过1e-3。维持 `P4_P5_SENSITIVITY_OBSERVED`，不把它写成连续/h/端口收敛；也不据此解释NN为什么没有求准同一p3方程。

| V9实测工作 | C plain | C phase | D plain | D phase |
|---|---:|---:|---:|---:|
| 完整接受更新数 | 29 | 54 | 6 | 4 |
| 完整PC构造数 | 2 | 0 | 0 | 0 |
| 最后完整边界之后已计费K作用 | 18 | 30 | 55 | 103 |
| JVP+VJP占worker时钟 | 90.07% | 89.75% | 97.49% | 98.16% |

完整PC数0不能证明未尝试PC，更不能证明PC无效；未留存的CG/PC中断细分保持 `NOT_RETAINED`。源码在一次CG后、评价其候选步之前可能触发64个K作用的PC建立；这是一个需要防止预算末端丢失可用工作的位置，但不能反推V9每次未提交K究竟属于哪一步。

可读结果支持的首先是**导数执行成本主导**，不是“已证明某个条件数过大”或“只差调一个阻尼”。下一批不先加第三种PC、不重做旧全套资格。

## 2. 本批依赖和自主处理

```text
A：原证据聚合/身份/内层工作分解
  → B：等价导数缓存、事务资格、实测成本
       ├─ C：对应实现准入后，两个无标签V9终态续算
       └─ D：C-phase未通过时，对两个监督V9终态作隔离续算
E：所有实际终态独立验收；实现收益、数值收益和准确性分别收口
```

数值仍串行。C/D按各自实现Gate准入，不要求p5/新精度计算作为前置；本批根本不新增高阶PDE。一条路线工程失败不取消另一条或不依赖它的证据整理。每个明确根因最多3次有代码/测试证据的修复重试；每条长路线最多2次故障恢复，时间和计数继承。正常停滞不是bug，不能重置mu、随机种子或优化器刷新预算。

缓存版本错误、shape/实虚布局、API不适配、stage/索引、计时和序列化等可在本批修复。禁止通过降精度、丢矩、改方程、删失败证据或重装共享环境解决。数据副本只查本任务index/manifest/hash；没有完整可恢复状态时该路线仅做实现验证，不把parameter-only或last_trial伪装成续算点。

## 3. A：一次轻量证据收敛，不重放旧计算

读取V9四个实际终态及各自durable final、原始history和资源记录，提取compact表：接受/拒绝、CG真残差/迭代分布、mu/h0、pred/ared/eta、完成/未完成PC、每个阶段导数和矩操作计时、未提交工作。已有记录没有的信息写未留存，不用重跑补造。

原大历史文件继续保留；新增 `inner_summary_v10.json` 与逐outer CSV应控制体积，建议单JSON不超过200KiB，完整K级轨迹留ignored并绑定hash。远程可审阅性是交付的一部分，不再复制数万行嵌套历史到多个新JSON。

核对本次复用的V9 final既与NPZ参数/c一致，也与PT中的GN状态、RNG、PC基及source一致。核对期望native/G误差仅用于身份，不用它选状态。C只加载自己的无标签状态，D只加载自己的监督状态，不能按误差择优换边界。

| 冻结文件 | SHA256；其余路径/标签从V9 run index读取 |
|---|---|
| C plain frozen NPZ | 21ed65cec10c377bf18d4e06ff6621e4c892a0ba804a9d53f2d1e2d01b194fa9 |
| C plain durable final | 55583f893e83418834669e169310a2991d8a823cd8aa13a81af1ed4580275cdd |
| C phase frozen NPZ | b1aeef1e5cf28a9b4435b490147d4767d2f5ea9539e9707c66cdffe61432aef4 |
| C phase durable final | 8f590ed900323368d13afab86b03c141a5a672951087371f3f25616a9d487062 |
| 原p3 native | 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215 |
| 原p3 Gram | 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9 |
| 原p3参考 | 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7 |
| 原q15完整矩 | 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e |

D的两个final hash从 `run_index_v9.json` 指向的实际索引唯一取得，在A设计commit中冻结，禁止凭近似文件名挑状态。p5解不进入C/D或缓存生成。A只读现有p3/p4/p5差值，列剩余curl/H、h和端口精度问题；不启动p6或新参考。

## 4. B：同一导数，更少重复工作

### 4.1 为什么可复用

当前 `MomentJacobian.jvp` 每次通过 `torch.func.jvp/functional_call` 重新评价网络；`CompleteMomentMap.vjp` 又重建前向图并逐块反传。一次固定theta的CG和PC建立中，权重、坐标、相位、hidden激活和tanh导数都未变。可保存它们的数值，重复使用线性化，而不改变J、J的实伴随或K。

官方[torch.func.linearize](https://docs.pytorch.org/docs/stable/generated/torch.func.linearize.html)也明确以更高缓存内存换取同一点多次JVP的复用；这里只借鉴接口原则，不升级当前Torch、不要求把整网格图交给该API。首选现有解析MLP切线的**数值缓存＋对应解析伴随**；旧Torch自动微分路径保留作独立对照。

设一个块内第l层输入为X_l，权重为W_l，隐藏输出H_l=tanh(Z_l)。缓存输入/激活后，实方向导数为：

```math
Z_l=X_lW_l^T+b_l,\qquad
\dot Z_l=\dot X_lW_l^T+X_l\dot W_l^T+\dot b_l,\qquad
\dot H_l=(1-H_l^2)\odot\dot Z_l.
```

线性末层不乘tanh导数。六个实输出仍两两构成三个复分量，固定相位在点值层乘入，然后经过原Piola、方向、完整矩和唯一owner映射。VJP是这整条映射的实伴随：先做完整矩映射的共轭转置及相位共轭，再将实/虚分量按原布局传回实MLP。不得只复用JVP却留下非匹配VJP。

```math
L=\frac{r^*G^{-1}r}{2d_G},\qquad
K v=\frac{\mathrm{Re}(J^*A^*G^{-1}A Jv)}{d_G},\qquad r=Ac-f.
```

这些公式和原GN数学完全不变。G因子仍须准确作用并计费；缓存不是新的预条件器，也不是近似Jacobian。

### 4.2 缓存和存储合同

静态缓存绑定geometry/moments/owner/transform、相位buffer、dtype/device；动态缓存还绑定**完整参数字节hash与版本**。只存detached FP64/complex128数值，不存全网格AD图、大J或大K。每次运算块最多8cells；允许全模型分块数值缓存但新增resident cache上限2GiB，先按实际shape预估再分配；超线用有界块重算，不用OOC或FP32。

同一theta的mu变化可复用。试探theta+s的真实前向不得覆盖基点缓存；接受新theta后旧动态缓存立刻失效，拒绝回滚可复用旧基点；载波、积分、dtype、参数顺序或buffer变化同样失效。不能因对象地址相同而认定参数没变。checkpoint不必保存可重建激活，但必须保存缓存键/版本和重建成本；恢复后先核验或重建，不反序列化失配图。

允许对固定矩映射选择一次等价稀疏/分块收缩；只删对**经过方向/owner处理后的完整映射**严格零贡献的项。删除前后须独立配对，不按幅值筛除；共享积分点可严格去重，但反向须准确scatter-add。保留所有边/面/内部自由度、原q15和MPC一次展开。若已知PC探针可按至多4方向批处理，每列仍单独计费；普通CG方向有依赖，不能预先编造后续方向来凑batch。

### 4.3 正确性与成本准入

复用已有环境/FE/相位/原方程资格，不重跑旧E0/B。先小型复非Hermitian链，再在四个V9固定态验证；C检查不加载目标参考。候选内核限三个有理由的实现版本：旧AD作为基线、无缓存解析切线、缓存解析切线/伴随及必要的一次等价矩收缩修复；不无限扫描batch/库/线程。

| Gate | 要求 |
|---|---|
| c/JVP/VJP与原独立路径 | 非零hidden/last/random实方向和复dual；操作尺度相对≤1e-10；零/近零另列绝对误差 |
| 实伴随/相位/族完整性 | 至少3对向量，含纯虚dual与非单位Floquet；实伴随≤1e-10；边/面/内部均检查 |
| K和完整梯度 | 同一G因子下新旧≤1e-9；真实对称/正性沿V8合同，不把梯度差分误当完整GN曲率 |
| 缓存失效 | 接受、拒绝、同theta改mu、改buffer、保存/恢复；不得读到stale缓存；验证batch1/8 |
| 更新配对 | 小问题至少3个GN接受/拒绝步骤；真实每个C终态旧/新各一个完整proposal，充足预算下s/pred/ared≤1e-8并解释近阈值舍入 |
| 性能核验 | 各固定态测一次建立＋一次完整梯度＋16次K作用，warm-up单列；旧/新交替3次，方向固定seed4211001；包含缓存建立/释放/拷贝，不只报热JVP |

只用计算性能选择等价内核，不用reference误差选择实现。性能样本逐个记录、报告中位数与范围/共享负载；不得改邻任务取得好看速度。测量A/G共享setup时明确它被双方共同复用；候选正式运行仍fresh G setup。

**长续算准入：** 正确性全部通过、无换页且内存合规，含一次setup的上述总工作快至少1.30倍，且真实完整proposal成本没有明显反向恶化。每表示/目标单独判定，不能仅凭一项纯网络微基准晋级。若缓存暂不快，先用本节允许的等价收缩/去重复核修复；仍无收益则不追加该路线3h旧慢训练，完成其他合格路线和证据交付。性能负结果不意味着数学失败。

## 5. 预算末端：保留可用更新，不让可选PC吞掉收尾

这部分不是新优化算法；充分预算下保持原mu、CG、rank32与接受规则。新增begin/end/heartbeat覆盖CG、真内残差、PC的K Omega/KU/eigh、真实trial与commit。记录已开始/完成/未完成次数及费用，不能用完成数0代表从未尝试。

进入可选PC建立前，用本路线最近实际K用时的保守值预留64次作用、核验、真实trial、原子保存与120s收尾；不够则记 `PC_DEFERRED_BY_BUDGET`，保留已合格旧P，**仍可在时间足够时验证刚得到的有效CG方向**，不为PC强行丢掉它。未完成新PC不得覆盖旧基；继承PC来源和构造次数不重置。

内层接近工作/时间配额时，在安全缓冲区内提前终止CG并返回当前有限方向，预留显式真线性残差、K s预测、实际目标和保存的完整费用。方向满足g·s<0、pred>0且原接受规则通过才提交；否则保留上一完整边界。硬资源/权限/监督故障优先停止，不承诺任何SIGKILL可保存当前步。

必须有小问题测试：PC预留不足但有效方向可完成；CG提前结束真残差核验；PC中断原状态不变；缓存及GN回滚一致；预算耗尽不无限重试同一拒绝。按原始计数计入所有已完成或中断工作，不能因为未提交而冲销。充分预算下新旧proposal保持配对；只在已声明budget-frontier事件处允许调度差异，不把这种变化隐藏在纯内核提速里。

## 6. C：通过实现Gate后，从完整 V9 无标签终态续算

新路线 `V10-PLAIN-CACHED-GN-CONTINUE` 和 `V10-PHASE-CACHED-GN-CONTINUE`。只加载第3节各自V9 durable final，保留theta、mu/h0、RNG、accepted总数、slow_streak、PC来源/V/Lambda/已用构造次数；核对NPZ与PT参数、c、source和标签。不是V8 Adam500重放，不从V9最小native或最佳场态另选，不继承D。

固定M5/p3、31968独立复FE、40端口、完整矩、原A/f/G/d_G、8966实参数、plain/单相位、q15、FP64。GN仍为mu0历史保留、原8档阻尼、CG40/有PC80、目标0.01、原Cauchy保护和rank32策略；不换loss/变量尺度或加第三种PC。**PC生命周期上限仍为C总2次、D总1次，旧已完成构造计入**；不是每次续算重获2次。旧SPD基可按原规则继续用，不能称为当前K的准确近似。

允许每条新增最多120个接受outer、4000个K、8000个JVP+VJP、512次真实trial，新增launcher上限3h，取先到者；新增计数与继承计数分别保存，累计不清零。这明确是新增续研配额，不声称仍在旧3h从零预算内。原历史前缀及V9新段成本，在端到端路径中完整归属一次；不能把续算的3h与V8从零3h直接作算法速度比。

每条fresh准确G因子、d_G核对和缓存建立全计费。不以初始h0重新估计/重置mu伪装为续算；缺GN状态先查本任务副本，仍无法证明一致则只交接口/性能结果，不自动换初值。故障恢复最多2次，已有花费保留。

每个接受步原子保存完整状态；每5个接受步及至少每300s在下一个完整边界进行原方程审核，报告实际审核间隔，不虚构同秒状态。充分接近严格方程门限立即冻结，独立审核不通过时保留失败，不以能量小强行继续称成功。结束后保存final committed，不用last_trial或按参考挑best。

C始终：reference_used_for_training=false，features_reference_exposed=false，pde_only_solve=true，benchmark_previously_seen=true，production_initialization_allowed=false。导数优化测试接触过D不授权C读取D数据；C可读文件仍是本身状态、原算子/G/矩与纯数值配置。

## 7. D/E：隔离诊断、独立验收和结论分流

C-phase未严格合格，且对应D内核通过B、数据/资源合规时，自动从V9-D各自最终完整GN态继续 `V10-*-CACHED-FIT-GN-CONTINUE`，不再算Adam，不选V8更好拟合点。每条新增≤1h、60接受步、1000 K、2500 JVP+VJP、256trial；累计旧PC上限1次。保持原G拟合目标，只用G乘法/JVP/VJP，不逐步A/AH/Gsolve。D标签/权重永不反馈C或0.7nm；监督三项均≤1e-3可提前冻结，1%仍仅部分表示信号。

若B判定某D内核没有收益，跳过该长D、记录原因，完成其余工作。C-phase严格通过则不为跑满配额追加监督诊断。新actual字段严格区分C原方程、D监督、缓存速度与p序列精度，不混作一个PASS。

E独立ML从参数重建q15/q30，独立FE compare-only只复用原p3参考；完整total/scattered E/H/curl、六点复场、四类40级复通道/分母、逐级功率、R/T/A/A_volume/R00和材料/界面区域都报告。保持严格原残差≤1e-6、场/通道≤1e-4、功率/能量≤1e-5、逐级功率≤1e-6、MPC/恢复≤1e-10、q30配对≤1e-8。不新求p3/p4/p5，不给NN提供Maxwell逆。

| 分类 | 可以说什么，不能说什么 |
|---|---|
| EXACT_DERIVATIVE_ACCELERATION_PASS | B的数值等价＋含setup成本门限通过；只是工程加速，不是NN求解通过 |
| DERIVATIVE_REUSE_NO_GAIN | 等价但未改善实际成本；修复范围耗尽后不重复长旧训练 |
| GN_CONTINUATION_RESEARCH_SIGNAL | 相对对应V9 final，native/augmented均下降≥10倍且散射L2/curl均≤0.1；明确用了额外时间，不称同成本算法胜出 |
| PDE_SAME_DISCRETE_PASS | C全部严格原方程/物理/资源/provenance通过；仍仅p3固定M5，不等于网格收敛或production批准 |
| SUPERVISED_RECONSTRUCTION / PARTIAL_WITNESS | D按原严格/表示门限分别报告；PDE-only/official保持false |
| CACHE_OR_RECOVERY_UNQUALIFIED / CONTROLLED_STOP | 不把实现/资源失败归因为网络数学不可表示；保存具体不匹配项 |

若快内核已经合格、有效工作明显增加，C/D仍无数值改善，应明确结束“仅靠这类等价加速继续原GN”的尝试，给出一个由内层实际曲率/更新证据支持的下一方案，不自动换loss、扩大网络或叠加PC。GN未过依然不能证明整个FEINN不可行。

## 8. 资源、Git与执行

新批上限12h=43200s，不叠加V9未用预算。旧最终累计99,864.4864455976s永久保留，含V9新增25,523.465839726967s及旧中断/重放；以现场最终账补未计尾段，不清零。历史费用与新增费用分账；缓存build、setup、failed attempt、被拒方向、trial/PC、存盘及独立审核全部计入。

| 子包 | 新增有载/有界辅助上限 |
|---|---:|
| A证据/四态身份/轻诊断 | 1800s |
| B等价实现/资格/配对/性能及修复 | 9000s |
| C两条条件PDE续算 | 合计21600s；每条≤10800s |
| D条件两条监督续算 | 合计7200s；每条≤3600s |
| E独立验收/文档辅助 | 3600s；至少预留1200s |

未用预算可预登记转给既有工程修复，不突破C/D单路线限制或增加未授权实验。用户要求多推进不是必须跑满12h；方法Gate或真正的安全阻塞决定受影响部分。

工作站原生Linux、CPU-only/MPI1、数学/Torch线程1，逐阶段选空闲物理核；数值warn12/hard16GiB、factor规划12GiB、新detached缓存2GiB，轻tests/浏览器2GiB，自身swap0/OOC0。系统reserve=max(128GiB,10%effective total)＋至少384GiB邻增长＋自身预算；disk free≥50GiB、artifact≤20GiB。不改其他项目、全局BLAS/CUDA/ABI、锁或watchdog。无cgroup委派时仍如实约0.5s树RSS采样，管理tmux单列，不冒称连续硬限或零干扰。

复用durable launcher＋watchdog＋worker，计时从launcher含import/setup起，150s前停止新增长工作、留至少120s。只操作自己的PID/start_ticks/锁；断连先确认同一作业，不能重复启动。旧PC和缓存原子替换分别管理，保存完整真实失败，不承诺finally覆盖SIGKILL。

无活跃自身作业且工作树安全后仅fetch/fast-forward本分支。共享fetch未映射时用命令级精确refspec和显式tracking，不改共享配置。先clean实现commit再run，不把后续文档HEAD当实际source；不新clone/分支、不reset/stash/amend/强推/merge。

## 9. 实现入口和一次性交付

数值内核放src/solvers，runner只编排，复用已有MomentJacobian/CompleteMomentMap/GN状态/compare框架，旧接口作opt-in reference path保留。给缓存版本和上下文明确命名，不覆盖旧算子数学。FE进程不顶层import Torch；不full pytest、不重装环境、不重渲染全部历史。

建议按依赖实现以下one-run stage；先资格化白名单，不能直接运行尚不存在的文件：

```text
v10_state_and_work_audit.dat
v10_derivative_checks.dat
v10_derivative_benchmark.dat
v10_plain_cached_gn.dat
v10_phase_cached_gn.dat
v10_gn_reconstruct.dat
v10_gn_compare.dat
v10_plain_cached_fit_gn.dat
v10_phase_cached_fit_gn.dat
v10_fit_reconstruct.dat
v10_fit_compare.dat
```

路径统一 `input/task042extra_feinn_5nm/`。仍由 `python scripts/launch_task42extra_durable.py <one-run.dat>` 选择FE/ML环境并调用 `python scripts/run_case.py <one-run.dat>`。各阶段收尾清场后再启动下一项；同一路线attempt新命名、依赖hash绑定，不覆盖V1–V9索引。

至少交付：`response_v10.md`、`outcomes/derivative_reuse_v10.md`、`outcomes/cached_gn_v10.md`；compact `records/campaign_design_v10.json`、`state_identity_v10.json`、`inner_summary_v10.json`、`cache_checks_v10.json`、`derivative_benchmark_v10.csv`、`accepted_steps_v10.csv`、`repair_log_v10.json`、`run_index_v10.json`、`resource_costs_v10.json`、`gate_decisions_v10.json`。所有run保留原input/resolved/manifest/physical/source/hash和环境/模型/cache/标签身份。完整大history留ignored。

summary最前追加V10导航，保留全部旧结果；同步development_progress、development_model_registry、tests和changed_files。报告已完成哪些自主修复、真实加速是否成立、实际增加了多少接受更新、额外时间换来了多少原残差/场收益、p5还剩哪些准确性问题。没有的实测字段明确not_run/not_retained，不能补造。

新增Markdown按fenced math/一致表格检查，补查新review与关键新增页的GitHub rendered view；当前发布端未取得浏览器视觉证据，不冒称通过。渲染权限阻塞不停止独立数值工作。仅推送 `HEAD:refs/heads/task42extra_feinn_5nm`，提交后报告准确HEAD、tracking/ahead-behind、clean及清场，再等待review；不自动p6/h/端口扩展、目标尺寸5nm或0.7nm。
