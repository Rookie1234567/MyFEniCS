# Review V9：修复真实 W1 求积失败，补齐 p6 代表类，衔接 dot 的 AUTO 验证

## 0. 本轮决定与依据

**主线下一项是解释并修复已经发生的 W1 积分失败，再只补缺失的两个 p6 代表类。W0、两个 p4 体积单元以及 dot 已通过的小型完整链不重跑。dot 则消费新编译资源负结果，完成尚未运行的独立积分和有界原生向量候选。** 本报告批准第4节固定的新窗口及有限工程修复；完成修复后应在窗口内继续数值交付，不停在“已提交修复”。

| 对象 | 本次核对的远端 HEAD | 裁决 |
|---|---|---|
| 主线 `task40extra_0p7nm_engineering` | `8c1a0ce23bd53cf92fffbed7a2daccd58cbf49a5`，未发现更新 | W0闭合；W1求积失败、p6未运行。第2–4节 **GO** |
| dot `task40extra_dot_parallel_cloud` | **更新至 `7580f5a48407a5c984aaf9311dc3733060d79f08`**；原指定基准0b860237保留为源检查点 | C1a/b/c通过；degree160准备已资源停止。第5节独立积分/有界原生候选 **GO**，原样编译重试 **NO-GO** |
| 完整AUTO作用/恢复 | 现有两代表面、选定top/x均不足 | 边界修复后按第6节顺序接通；不继承manual532资格 |
| W2 / 完整p6周期参考逆 | dot C1c这个先决条件已满足，但p6完整链和AUTO仍缺 | 本轮优先W1；不自动消费旧W2额度，不先做新的PC性能组 |
| 原尺寸正式求解 | 精度、后端/fill、全部q并存、冷流程总成本均未闭合 | **NO-GO；未具备正式大规模运行资格** |

审阅日期：2026-10-05（Asia/Singapore）；运行记录中的Z时间均为UTC。硬目标不变：**50×25×140 nm、λ0.7 nm、完整三维且保留非可分缺口能力；整机≤2,000,000,000,000 B、无swap，冷编译/构造/全部q因子/迭代/内部恢复/输出/独立检查的完整流程≤172,800 s。**

本报告审阅远端源码、提交差异、JSON收据和测试源码。审阅端按指定bash/workdir尝试后仍无法启动本地命令，未直接读取ignored NPZ或Library科学数组、未运行FE/pytest；以下“独立检查通过”指已发布运行收据，不能读成审阅端新做了一遍。主线报告目录已有V8且已被Response V8回应，故新增V9，仅提交本文件。

## 1. 已有结果的准确边界

### 1.1 主线：W0接受，W1保留真实负结果

| 实际对象 | 数值、资源与证据 | 本轮处理 |
|---|---|---|
| W0，80 cells/p6/532/φ5 | worker `d4b6ed6…`，797.628623s、树RSS 2,204,782,592B；checker `0a15ac5…`，955项、18.994374s、478,863,360B | 接受`W0_FULL_COMPONENT_AND_INDEPENDENT_CHECK_PASS_NO_PDE`；不重做 |
| W0原方程/恢复 | 制造态原native残差1.0779495733e−15≤1e−10；恢复1.4966004617e−12≤1e−11 | 组件/制造态闭合，不是物理全器件A6或场精度 |
| W0持久性 | 1,602成员、604,158,016B；逐文件fsync、重开hash和数组hash全部通过；29修正类、3,287成员角色 | 原目录可继续消费；没有额外archive，原`durable_archive_verified=false`不改写 |
| W1两代表面/全32,060 keys | q30/q60最大逐通道差 **5.705909332721303**，限1e−10；worst index8576 / top,−67,−34,s；component差/原H为4.1493038268067535；完整作用差 **0.008663088994999783** | **NUMERICAL_FAIL**。完整作用约0.866309%虽小于1%，但这里验收门是积分1e−10，不能借场比较1%门通过 |
| W1 p4 top/bottom | 恢复4.0710058e−13 / 3.3184049e−13；原/约化方程及全keys端口身份通过；每cell 300行、108内部 | 保留q30离散下的局部代数PASS；不是准确积分或完整AUTO器件资格。复用保存体积张量 |
| W1 p6 top/bottom | 两项没有数组；UTC−monotonic首次差6.277888281s，超过当时5s门 | **INTERRUPTED_NOT_RUN**，不能称p6数值失败 |
| W1资源/保存 | worker监督38.649290s、树RSS1,221,480,448B；保存数组checker2.047160s、306,634,752B；104成员NPZ共38,026,664B | 原负结果已独立重算；不重启原runner来重复q30/q60/p4 |

W1完整NPZ的SHA256为`a475bba1618abd74981622a66e127b2fd88b43f52a2339f5087115ed9b1a82f8`；checker SHA为`a1c52f9f438fba8fba6c4fc012ff78dd3dd85ec6ba29b882841870bfdeb117cb`。路径及worker源`c354afa449fb80cfb5012e7d2ff66a3e3e64e088`见[W1收口记录](outcomes/records/review_v8_w1_boundary_checkpoint_closeout_v1.json)，W0见[组件收口记录](outcomes/records/review_v8_w0_component_closeout_v1.json)和[Response V8](response_v8.md)。

这些运行的task swap峰0、记录区间global pswpin/out增量0；全局历史计数783/3167页不是当前SwapUsed，也不能证明宿主Windows/pagefile或整机零swap。W1当时service MemoryMax16GiB，但动态准入只有9,132,195,840B，下一轮不能直接分配16GiB。

W1旧窗口`2026-10-04T15:24:35.195396Z → 17:24:35.195396Z`已结束。两段已知监督耗时共40.696450314s；准备、失败启动、空档与总charge仍`UNKNOWN_NOT_SETTLED`。W0成功/失败各phase、旧200.87894401792437s小计、V6已结算5428.582333962078s及未知准备费用全部保留；不把UTC端点差充当完整monotonic账。

### 1.2 dot：C1c已经通过，优化版仍只有保存数据资格

| 对象 | 已发布证据 | 尚未证明 |
|---|---|---|
| C1a p6组件 | 955项；worker1349.135s/RSS2,191,613,952B；checker18.142s；完整Library取回 | 原尺寸AUTO及完整p6逆 |
| C1b p4稠密端口参考链 | 148项；worker97.766s/RSS863,150,080B；checker3.779s；全四q、regular/notch及全部内部恢复 | 原尺寸/生产资格 |
| C1c p4紧凑链 | 实际本地source `17c0a656b44ed5b47351f6c2504579c8b3100f63`；399项；worker2086.831996s/RSS656,293,888B；checker29.930988s/RSS427,638,784B | 是缩小80cells/φ5/manual532。独立checker消费live FFCx权威向量，没有另做独立体积装配；完整列映射/生命周期仍含producer控制 |
| C1c因子/完整解 | 四块1884/1960/1960/1960全部保留；规则/缺口最大原残差6.6834162e−12 / 7.9671203e−12；八组全532输出、8,640内部恢复通过 | 实际backend为`scipy.sparse.linalg.splu`；各`factor_memory_bytes=null`。PETSc索引检查不等于公共PETSc后端和fill资格 |
| 保存投影优化 | 八组系数差0、CSR逐位相同；监督231.886s/RSS352,264,192B；owned峰27,957,560B | 4.84–7.95倍是固定顺序、单次warm小片段add比值；没有新live完整链或原尺寸加速 |
| 原尺寸库存 | 32,060、各侧16,030，全propagating；p6积分degree160；监督8.306145s/RSS495,730,688B；完整原件Library保存取回 | 0b860237时仅元数据；最新7580f5a已建18cell空间/MPC，编译准备资源停止，表面作用和高阶积分仍NOT_RUN，见第5节 |

证据：[C1a/b](https://github.com/Rookie1234567/MyFEniCS/blob/0b86023780aa9fba658ac44998c002cf6312f5b3/docs/task40extra_dot_parallel_cloud/outcomes/renewed_C1ab_20261004_zh.md)、[C1c完整记录](https://github.com/Rookie1234567/MyFEniCS/blob/0b86023780aa9fba658ac44998c002cf6312f5b3/docs/task40extra_dot_parallel_cloud/outcomes/records/paired_C1c_allq/paired_C1c_compact.json)、[优化范围](https://github.com/Rookie1234567/MyFEniCS/blob/0b86023780aa9fba658ac44998c002cf6312f5b3/docs/task40extra_dot_parallel_cloud/outcomes/saved_vectorized_all8_v1_zh.md)、[AUTO库存](https://github.com/Rookie1234567/MyFEniCS/blob/0b86023780aa9fba658ac44998c002cf6312f5b3/docs/task40extra_dot_parallel_cloud/outcomes/records/target_AUTO_identity_v1/compact.json)。

dot新的源提交与完整回执已取代V8时“未获继续许可/未运行”的时点状态，不再重复索要旧C1a许可。主线Response V8中的“dot仍HELD”是旧快照。两线源码、数组数量和环境不同，不合并它们的955项或直接比较复数值。所有worker/checker表中时间都不是含准备、归档、Library传输的完整总费用。

## 2. 先对齐可比较的对象，不重生成模式

### 2.1 编码差异已查明，逐行数值等价仍需从现有原件完成

| 项目 | 主线 | dot / 决定 |
|---|---|---|
| Si、λ、角度、周期 | n=0.9998851703688496+4.3236152269189515e−6i；λ0.7、θ89、φ0、50×25nm | dot当前值一致；不再套用Task042旧Si差异，不换材料 |
| ordered key编码 | `[side,m,n,polarization]`，compact JSON、UTF-8；SHA `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` | `[index,side,m,n,polarization]`、canonical ASCII JSON；SHA `08d7464c448a75bd5f41986f726ae0f97484cc050891dcfaaa24efc5f2900899` |
| 完整文件hash | 36,244,923B；`52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d` | physical manifest SHA `7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e`；schema/范围不同，不能直接断言冲突或一致 |
| 体积几何 | 主线外部库存的组合identity还携带历史缺口box，但其scope明确仅外部端口 | dot原尺寸fixture为规则结构、void=null。外部模式可相同，整个体积identity不能因此合并 |
| 表面坐标 | W1 x∈[−25,25]、y∈[−12.5,12.5]；272×4，保存面索引(100,1) | dot x∈[0,50]、y∈[0,25]；3×2表面，18cells。不是同一面/同一函数 |
| 实际x分段 | `_proportional_axis`给90/46/46/90；由源码推导，续作以保存axis数组为准 | 与早期78/58/58/78计数候选不同；不能仅凭“272×4×14”混用离散hash |
| 端口相位 | W1方向投影含`exp(-i conj(kz) z_port)`；native B含global-z相位 | dot选定原生表面/独立helper使用`kz(z−z_port)`。需写清B/D/H及端口未知量的显式变换 |

第一项交付是小型身份桥：从两份已有原件，各自计算有索引和无索引的同一种canonical编码，核对32060项一一对应、无重复遗漏、各side/pol及全部k/e/traction/H。保存两份原hash和新的共同编码说明，不把新摘要覆盖旧权威；不再运行模式生成器。现有Git紧凑记录没有交付全部行，本审阅不能声称已逐行重算等价。若dot原件暂未交到主线，先完成本线两种编码和参数表，继续本线积分归因；dot回传同格式结果后再闭合跨线桥，不为等待传输停下主线。

坐标平移固定为`(25,12.5,0)nm`。只能按源公式推导相位和原投影分母随坐标/参考面变化的转换，连同入射、载荷和输出一起变换；禁止拟合一个相位。主线旧失败首先在自己的原坐标、原相位、原H和原trace上分析，不能靠改成dot坐标使它“通过”。不同网格的trace系数本来不可逐项对比；跨线见证用明确的同一物理多项式/函数。剩余逐字段差异若无法由编码、变换或可解释的浮点路径说明，仅停止跨线数值比较，主线可继续自己冻结身份的积分归因。

### 2.2 源码解释了为什么已有PASS不能覆盖这次失败

[主线runner](../../benchmarks/run_task40_w1_boundary_probe.py)把q30/q60都送到相同方向积分内核；[旧局部见证](../../src/solvers/task40_w1_local_probe.py)则用相同q30的直接Basix积分作对照。后者首个key不是最高y振荡，且制造RHS与恢复使用同一积分规则，故可以在积分不够准时仍代数闭合。现有测试主要是较小波数/较小面片，不能替代当前55rad量级的实际见证。

本次y面宽6.25nm、最大n=35，跨面相位跨度约54.98rad；q30/q60名义分别为16/31个一维Gauss点，实际节点/weights由本机Basix身份核验。**沿y欠积是有源码与几何支持的假设，还没有从104个保存成员完成独立归因。** 伴随关系通过只说明两个方向相互一致，q60也必须被检查，不能预先当真值。

## 3. 主线唯一数值续作：保存数组归因 → 一个修正 → 两个 p6 类

### 3.1 独立可信见证

利用面上有限元切向场是低次多项式这一事实，可把“多项式乘振荡指数的积分”化成少量已知函数值。这样得到一个不依赖q30/q60节点的参考；代价是高精度标量计算，仅用于代表面和去重的一维频率，不建立新FE网格。

采用Legendre多项式与球Bessel函数的积分关系，并明确当前代码的单位参考坐标约定：[NIST DLMF 10.54.2](https://dlmf.nist.gov/10.54.E2)。

```math
I_\ell(\kappa;x_0,L)
=\int_0^1 P_\ell(2r-1)e^{i\kappa(x_0+Lr)}\,dr
=e^{i\kappa(x_0+L/2)}i^\ell j_\ell(\kappa L/2).
```

这里是`dr`积分；物理Jacobian/Piola系数沿原代码另乘，不能再多乘一次L。B用其原正向k，D/投影使用原来的共轭及符号；κ=0按解析极限处理。实现放入可复用src小模块，checker不调用生产积分表构造器。

执行固定流程：

1. 读取原104成员及hash、两个保存面、trace/dual/alpha、模式和原H。先从保存量复现旧指标；不重做原FE、q30/q60作用或两个p4体积装配。
2. 独立构造实际p6切向多项式：核对native基、方向、Jacobian和坐标，以独立Basix tabulation/实体映射作见证，不能直接调用生产`project_components`充当参考。高精度80位计算上式，100位作一次固定复核；另在已保存最差key、最大y频率key及零y频率key核对独立直接积分/零频极限。精度复核不是扫q。报告高精度、基变换和complex128舍入各自的不确定量；参考误差应低于正式1e−10门的1/100，否则标参考未资格，不宣称谁正确。
3. 覆盖全部32060输出，分别报告旧q30、旧q60相对独立参考的误差；拆出x/y一维矩、两切向分量、模态投影和回散布的贡献。使用固定少量反证组合“参考x+旧y / 旧x+参考y”，仅保存数组/矩作用，不开新的网格、p或模式扫描。
4. 正式逐模式尺度继续冻结为旧checkpoint的`max(norm(q60_components_j)/H_j, finfo.tiny)`；完整作用尺度保留旧`norm(q60_apply)`，H不改。新参考只替代尚未可信的比较值，不扩大分母。绝对积分误差、运算尺度和近零取消另列诊断，不能替代原门。旧q30/q60失败始终保留。

**有界修正只选一次：**若已有q60对独立参考及全部上述正式门通过，采用已被独立确认的q60；若q60也未通过，预登记一个“在原面内部切分积分区间”的复合q30候选。子区间只改变积分，不改变FE网格/材料/DoF；按完整频率和实际面长一次确定分割，令每段最大相位跨度≤π，利用Gauss余项/多项式导数界确认截断误差预算后冻结。计算一维矩并稳定累加，复用现有方向收缩，不构造高阶二维巨型FFCx表。依据见[NIST Gauss求积余项](https://dlmf.nist.gov/3.5#v)。若预估的误差或资源界本身不能满足，就停止这个候选，不以q80/q100/更细分段继续试到通过。

新候选对独立参考必须过原1e−10逐通道门及同尺度完整作用门，并核对forward/adjoint、非零modal RHS、B/D各自的符号和归一化。新增参考或复合积分均是**本轮待实现、未运行**，不能写作现有资格。已有数值负结果不是重放许可；一次候选的真实数值失败即收口。

### 3.2 只补 p6 top / bottom，复用 p4 已存体积

时钟门和修正积分均通过后，原(100,1)面及原上下单元边界、材料保持；只创建缺失的p6 top/air、bottom/Si两项，每cell882行=450内部+432trace、全部32060 keys，原非零xi/trace/port制造态与batch64保持。保留细小但非零的内部B/Di项，不能裁零。检查完整内部恢复≤1e−11、原/约化方程≤1e−10、全keys端口作用、非零内部特解及原生方向/行映射。

积分规则变化后，旧p4 q30的代数PASS仍属旧算子；若要组成新的p4/p6统一接口，用保存的p4 volume tensor和映射只重算新边界/载荷/恢复的受影响代数项，**不重建p4 mesh/JIT/体积**。p6每项完成立即保存，工程修复优先复用已合格部分。

未消元Hp的隐式单位块不能代替Hhat；继续分批计算Di·solve(Bi·alpha)和Di·solve(fi)，不物化32060²稠密方阵（单个complex128方阵16,445,497,600B）。局部制造态PASS仍不代表完整原尺寸物理解或全局MPC映射。

[当前runner](../../benchmarks/run_task40_w1_boundary_probe.py)只有`--modes/--output`且顺序重跑边界、p4、p6，不是续作入口；checker退出码0也可以表示科学负结果。允许在这个runner上增加最小的保存数据/修正边界/p6-only阶段与resume参数，保留旧raw不可变、显式绑定旧producer和新checker/source；依赖是否改变由文件差异记录，不能改旧source manifest。只补定向测试：真实高y振荡见证、时钟/截止、p6-only不触发W0或p4装配、负结果不会自动进入下一阶段。不要另造平行数值runner或重跑昂贵全仓Gate。

## 4. 新主线窗口、时钟处理和有限自修复

### 4.1 明确的新授权

**本报告新增一次主线14400s窗口。** 从本轮第一项执行准备记录唯一T0、UTC截止、monotonic/boottime、boot ID和持久累计账，至raw/checker读回及清场全部包含；提交源码、重启service和更换attempt不刷新。旧W1许可剩余为0，V9是明确增量，不是默默重开旧窗口；不把历史unknown回填0，也不重新制造一个假精确的历史总和。

| 范围 | 上限与结束条件 |
|---|---|
| 保存数组归因/独立参考 | ≤3600s，包含该阶段定向测试和所有尝试；不运行新FE |
| 修正边界、仅缺失p6及独立checker | 合计≤7200s，任何单worker/checker≤4500s；到达上限即保存终态 |
| 全轮 | ≤14400s，剩余额度涵盖时钟核验、接线修复、打包/读回和收口；最后预留600s，不在清理时追加时间 |
| RAM | 任务树硬上限16GiB=17,179,869,184B与实时物理/cgroup准入取更小者；至少128MiB证据/终止余量包含在该上限内，计算可用额再扣减，编译器/子进程不遗漏 |
| 新磁盘 | raw≤512MiB，JIT/生成代码≤2GiB，日志/紧凑记录≤256MiB；总新占用≤4GiB并保留至少1GiB空闲。旧604MB W0和38MB W1只读复用，不复制成新全量包 |
| 环境 | 明确的本地WSL2、既有合格独立prefix、MPI1/数学线程1；complex128与实际int32身份原样核验。不得切换工作站、SSH、换环境或新建worktree |
| swap | 任务VmSwap/cgroup swap必须0；global pswpin/out新增即停止并记录归因边界。当前SwapUsed、宿主/pagefile可见性另列；不擅自swapoff，不声称整机零swap |
| 自修复 | 最多3轮明确工程根因的修复+定向回归，最多4次新的FE worker启动，全部在同一窗口；已完成的cell/raw尽可能直接续接 |
| 不重放 | 同一根因两次修复仍失败；真实新数值门失败；内存/磁盘/swap/累计时间停止；模式/材料身份无法说明——停止受影响升级，不靠新编号扩额 |

工程修复包括可选依赖、参数/模块入口、表示/序列化、时钟接线、FD/写出与checker读取错误；原数学、模式、材料、相位、分母和数值限值不变。修复后应自主继续，不需每次新的文字批准。记录每次source diff与targeted结果，不为无关文档改动重跑FE。

### 4.2 时钟是独立工程问题，不增大5秒门来掩盖它

[workflow_timebase.py](../../src/runners/workflow_timebase.py)已有`STRICT`及`CONSERVATIVE_REALTIME`，后者按相邻区间保守扣费，UTC前跳计入、回跳不返还；不是新研究算法。6.2779s的外因目前未知，不能直接认定为WSL休眠或NTP。

先读取旧parent三钟样本/boot和采样时刻，区分：UTC跳变、monotonic/boottime不一致、跨采样暂停或错用不同起点。统一parent→worker→checker的时钟来源和已持久T0；必要时记录读取前后时间括号以识别采样期间被挂起。做一次约60s的同service、无FE实际三钟核验，加已有forward/backward注入、deadline和清树的最小测试。

**优先保持strict。若样本明确显示monotonic与boottime一致、只有可调UTC发生跳变，本报告允许本次显式选择已有`conservative_realtime`。** 三方必须同策略、同起点；仍保留原monotone一致性/缺失/倒退门，并同时在以下任一条件首次达到时终止：固定UTC截止、monotonic或boottime的14400s界、相邻区间保守累计费用14400s。UTC回跳、暂停、重启不能延长；起点/boot身份变化停止，不自建新窗。原strict失败收据保持原分类，不能追认通过。若不是单纯UTC异常或无可靠双单调钟，则停止FE，只完成已有数组分析；不关闭guard或扩大5s/原比例容差。

新账记录整窗持续监督区间和未知缺口；父/子重叠不重复相加，准备、修复、compiler、输出及checker不漏计。若仍存在不可计空档，完整费用保持unknown，即便个别数值门通过也不能授予成本资格。

### 4.3 执行入口与实际本地身份

使用[任务目录AGENTS](AGENTS.md)指定的`/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering`，显式`/bin/bash`、`login:false`。根聊天Task37路径不是执行目录。实施者按现有分工不自行commit/push，由主控审核冻结source并统一提交；不新建聊天/subagent/定时任务。

已有环境资格与activation命令如下，变量须来自本机已有prefix及本次新目录，不猜路径。它们是**环境步骤，不会启动W0**；整个shell及后续阶段受上述父监督和累计窗口约束。

```bash
cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
export UCX_TLS=self
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$T40_PREFIX/bin/python" scripts/task40_fresh_c1/qualify_imports_only.py \
  --runtime-profile local_wsl2_authorized --record "$T40_V9_ABI"
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh \
  "$T40_PREFIX" "$T40_V9_ABI" "$T40_V9_JIT_CACHE"
```

每个新shell都重复同一activation和ABI核验，不能直接用旧`.venv`或把本机收据叫云端收据。不要调用`run_fresh_c1_p6_local_wsl.sh`来启动V9，它会重跑已结束的W0。

V9续作CLI尚待第3.2节最小扩展；执行者应在本窗口内交其真实`--help`和完整命令，并直接完成“读取旧checkpoint→归因/修正→p6-only→独立checker”。新参数必须通过一次无FE合同检查，证实不调用旧W0或p4体积装配；不要把当前只有`--output`的全探针伪装成可直接resume。

## 5. dot 的最新更新与互补数值交付

**本次审阅期间远端新增`7580f5a48407a5c984aaf9311dc3733060d79f08`，必须改变原先“尚未编译”的计划。**[新回执](https://github.com/Rookie1234567/MyFEniCS/blob/7580f5a48407a5c984aaf9311dc3733060d79f08/docs/task40extra_dot_parallel_cloud/outcomes/target_surface_compile_stop_v1_zh.md)及[原始紧凑记录](https://github.com/Rookie1234567/MyFEniCS/blob/7580f5a48407a5c984aaf9311dc3733060d79f08/docs/task40extra_dot_parallel_cloud/outcomes/records/target_surface_compile_stop_v1/compact.json)表明：

| 原尺寸选定编译尝试 | 实测 / 分类 |
|---|---|
| 18cells、p6/882基、双Floquet MPC | 空间/约束构造已完成；仍不是准确网格 |
| 一个top/x、degree160 | 监督75.948353018s后`RESOURCE_CONTROLLED_STOP`；leader−9由监督器终止，不能称内核OOM |
| 树RSS峰 / cap | 3,247,665,152 / 3,221,225,472B，超约26.44MB；tree swap0、后代已清 |
| 停止位置 | 302样本仅Python、外部C编译器数0；C与临时C均0B。处于Python侧UFL/FFCx/Basix准备区，具体函数/大数组仍未实测 |
| 估算失效 | precompile admission 2,327,080,960B不是可靠峰值上界，不能重复拿它授予同次编译准入 |
| 未产生 | 二进制、表面向量、高阶独立积分、因子、PDE均未完成 |
| 证据 | 11成员、1,887,259B完整失败包已Library保存/新目录取回；source仍本地`6dba8257053c6b2e474b7808b708a745f202733b` |

**不在3GiB下重试原样degree160大编译，不靠抬cap、换18cells或降低degree使它过门。** 这个负结果只否决本云环境中当前编译组织，不否决原尺寸数学问题。旧C1a/b/c和八组saved优化不重做。

dot下一项改为：**先让已有独立积分helper实际运行；再在同一有界窗口内验证一个保持degree160、分块访问原生基函数的selected raw向量候选。** 主线修复的是两代表面全keys的方向积分；dot验证实际native/MPC向量及原尺寸18cell上的独立积分，两者不重复。

1. 从已存AUTO原件完成第2节共同编码桥、复用Library seal。当前`run_surface_stage`还重新调用`_fresh_inventory`且把reference放在大编译之后；以最小接线允许消费封存数据并先运行reference-only。保留原metadata producer和新consumer的不同source，不能改旧seal。只读重建mode对象不等于重做清单生成。
2. 用已保存采样/事件和源码定位最后完成阶段，列出可能同时存在的数组及尺寸，未知项保留。**不为补profile重启已失败的大编译**。这项归因与第3项独立数值运行同窗完成，不成为无限的准备任务。
3. 复用[现有helper](https://github.com/Rookie1234567/MyFEniCS/blob/0b86023780aa9fba658ac44998c002cf6312f5b3/src/solvers/target_higher_quadrature_reference.py)，只构造同一18cell空间/MPC和三组既定状态，不调用primary form。选定原三tuple`(0,0)、(-142,-5)、(-85,-35)`及两极化、top/x不变；public Function.eval按固定degree168/176、chunk≤512。规则差过原`1e−10 × integral operation scale`、无分母floor；再以第3节独立多项式矩/误差控制认证参考。两种高阶规则相近不自动等于真值。
4. **唯一新raw候选**：保持degree160与完整native基/实际面/MPC，按预登记chunk256分块tabulate原生基、Piola/方向变换、收缩并共轭拉回独立行；不请求一次生成全高阶FFCx表，不构造大C/D或Hhat。核实际规则点/weights及native行身份，每批只保留预算内workspace。数值核心进src，独立Function.eval不得调用该候选的装配函数。它是新增待验证路径，**不是已失败FFCx内核的通过或bitwise继承**；只改积分实现的存储组织，不改物理模式/积分degree。若无法在固定对象界内实现，则止于已完成的参考证据，不另试第二种算法。
5. 保存selected全部raw系数与三种状态的作用，同独立参考过原1e−10门；若保留旧masked诊断，另列`max(1e−30,1e−13*maxabs(raw))`带来的损失，不让裁零影响正式raw门。两个极化、所有native行与MPC slave-zero身份完整。成功只授予新`STREAMED_SELECTED_NATIVE_TOP_X`候选在此fixture的有限资格，不能称原production FFcx cold compile、全AUTO C/D或原尺寸提速。
6. 完整scientific raw及Library新目录取回，交准备、空间、规则构造、基函数分块、映射、checker、保存的互斥阶段和整窗wall/RSS/磁盘。保留原75.948353s与所有历史费用，不用本次新方法成本覆盖它。

**dot本轮独立新窗≤7200s，单worker/checker≤4500s、整树≤3GiB、MPI1/线程1、swap门不变；最多3轮工程修复/4次新worker，完成阶段优先复用。** 新科学数组≤512MiB，JIT/生成代码≤2GiB、日志/紧凑证据≤256MiB，总新占用≤4GiB且留1GiB空闲。准备、Library传输/读回与失败都在自己固定T0内，不借主线额度；原C1c保存例外不自动继承。监督预停线须扣除证据余量并考虑采样超调，不能把旧峰超过cap当成新豁免。真实积分/身份或资源失败即止，不自动变更chunk/degree/夹具或启动原编译重放。

本节是对**新路径和独立reference**的明确有界授权，不是撤销旧资源停止。dot自己修改/发布其分支，主线不改dot源码、不复制云端ABI。旧portable/recovery文档的“环境不可用/AUTO未生成”保留历史并由新response/index连接当前事实。两线交接source、共同身份、raw/Library索引、误差与成本，无需各跑一遍对方实验。

## 6. 完成当前缺口后的最短顺序与最终放行条件

| 次序 | 必须完成的数值交付 / owner | 进入下一项的条件 |
|---|---|---|
| 1，当前授权 | 主线：全keys积分归因和一个合格修正、缺失p6上下恢复；dot：已失败编译成本归因、独立积分及有界degree160原生向量候选 | 保持各自完整门与raw，不能用其中一边的PASS代替另一边 |
| 2，统一完整AUTO | 主线负责同一原尺寸候选/全native-MPC行映射及完整上下x/y边界作用；dot提供已核验的紧凑投影/端口表示；全32060输入输出、非零内部/port RHS、完整p6恢复及独立原方程检查 | 两代表面或选定top/x只是入口；完整覆盖、全部实际类别和支持必须闭合。数值接口变化触及的资格重新绑定，未变体积/旧raw复用 |
| 3，后端与全部q成本 | dot优先用已存四q CSR和RHS接公共PETSc后端，补非Hermitian求解/原块残差和整数容量；再对最终候选做有界symbolic/setup准入 | 现有四个小q同时保留只证小例；报告各q L/U NNZ、fill、allocated/used及workspace，**全部因子实际并存**；private ctypes不可用，PC.setUp不能伪称已分开symbolic/numeric |
| 4，原尺寸求解候选 | 主线在目标机器自身ABI/资源准入后求完整p6原方程，完整恢复/全部输出；必要时才做旧V7/V8定义的单一p4-PC/p6参考逆反证 | 明确每步完整PC成本、外层步数上限与冷总耗时。相同准确p4逆的存储优化不能自动降低p6步数 |
| 5，原尺寸精度与交付 | 原尺寸同物理的独立参考/有针对性的离散误差检查；固定背景、相位、公共体积、模式清单和分母，输出E/H/curl及全部模式 | 数值、精度、资源、持久原始证据全部通过，才可能最终批准 |

第2–5项是明确的后续准入顺序，**本报告不授予无预算的目标规模装配、分解或求解许可**。当前可直接连续完成的是第1项；不在完成一项便宜检查后停掉已经授权的另一项。公共后端使用旧CSR可避免FE重跑；若接入优化版，则必须在首次实际消费中绑定新source和完整原方程/恢复证据，不能把saved投影PASS改称新的live链。

整机总账至少包含冷JIT/求积及生成表、mesh/MPC、C/D及投影临时量、单元内部LU与恢复项、H/Hhat/RHS修正、全部q因子fill/workspace并存、outer Krylov与完整PC、采样/输出/hash/fsync/独立checker，以及OS/其他进程/文件缓存的正余量。阶段对象字节、峰RSS、累计分配和后端used/allocated分别报告；不能用缩小RSS线性外推或只算H。原H对角512,960B的收益不等于整个流程收益；C1c `factor_memory_bytes=null`更不能填0。

后续原尺寸求解的执行准入要求有可信的全流程内存/时间上界及原尺寸精度验证计划；**最终目标放行**还须实测闭合：完整原A6显式残差≤1e−6，原方程/恢复身份按既有门通过，场与显著复模式≤1%、功率差≤1e−3、能量≤1e−5；显著模式选择规则在比较前冻结，保留全部输出和绝对误差。32060是完整冻结的传播通道库存，不单独证明端口截断精度；原尺寸验证应说明这一误差是否已受控。完整冷流程≤172800s，整机峰≤2e12B且零swap；若仍在WSL2，必须涵盖宿主/pagefile，不能只看guest任务树。

Gx784继续只称`tested_x_agreement`，不能证明原尺寸272×4×14、尤其y/z及缺口精度。旧2.611883%/2.750374%场差、1.555605%复模式差、系统151页swapout保留；不重跑背景归因、Gx784、旧185小时2nm OOM路线。F5已做的优化不重复；单独消除C步骤的约1.554倍上限仍不能解释目标规模完整加速。

若原尺寸单qfill或完整PC/步数已不支持预算，就明确关闭该参数路线的规模升级；可先核算有限因子分批/精确重算是否还能满足48h，不能暗换swap/OOC。只有确需改变规模增长时才另提有反证的局部求解/多层纠错，不自动恢复历史失败扫描。本轮首选是修复已证实的积分问题，尚无证据宣布最终目标已可达或不可达。

## 7. 交付与给执行 Codex 的文本

本轮成功交付必须是数值和原始证据：身份桥、旧q30/q60独立误差归因、冻结修正结果、两个p6代表类及checker、双方各自完整费用/内存/保存收据。若失败，交最后真实阶段、实际数值/限值、完整命令/source/input/ABI、保存成员hash、停止和清树证明；unknown成本继续列出，未运行项不补造。由各线主控更新自己已有response/summary/run index，不再为每个工程错误新增review编号。

本报告只做远端审阅、Markdown结构和单文件差异核对，不声称本地pytest/CI通过。GitHub渲染检查结果在提交回执说明。

> 主控在本机canonical登记的task40extra_0p7nm_engineering工作树安全拉取并完整读取docs/task40extra_0p7nm_engineering/review_report_v9.md。审阅主线基准8c1a0ce23bd53cf92fffbed7a2daccd58cbf49a5，dot最新只读基准7580f5a48407a5c984aaf9311dc3733060d79f08（原0b860237源检查点不变）。严格使用任务目录AGENTS指定的本地WSL2工作树和既有独立prefix，不SSH、不切项目/主机、不新建聊天/subagent、不改dot/master。W0已955项通过，不重跑。
>
> V9明确新增一次14400秒主线窗口，从第一项准备冻结唯一T0/deadline及三钟/boot/累计账，旧W1窗口已关闭。保留200.878944秒旧小计、V6旧账、W0所有phase和W1已知40.696450秒及全部unknown准备费用。先用现有三钟记录定位6.2779秒偏差，按第4.2节核验/修复；strict优先，仅证实UTC单独跳变时可显式使用已有保守计费策略，不能扩大门或延长截止。
>
> 先读原38,026,664B/104成员NPZ及两个已有32060清单，统一indexed/unindexed键编码、材料、坐标和相位变量变换。材料当前一致，但主线居中坐标/90-46-46-90分段、dot0起点/18cell及相位规范不同；不得仅凭hash不同判物理不同，也不得拟合相位。旧q30/q60负结果、原H和分母保持。
>
> 按第3节，用独立高精度多项式-指数矩检查全keys，分辨q30/q60各自误差及x/y来源。q60独立过门才采用；否则只做一次按完整相位跨度/误差界冻结的复合q30积分修正，不扫q。新候选真实数值失败即停。时钟和新积分通过后，只补p6 top/bottom及独立恢复checker；p4只复用保存体积做必要边界重收缩，不重建FE。扩展现有runner为实际resume/p6-only入口，不能裸重启原全探针；checker退出0不等于科学PASS。
>
> 主线保存归因≤3600秒，新数值和checker≤7200秒，总窗≤14400秒；任务树≤16GiB且取动态准入更小值，raw≤512MiB、JIT≤2GiB、总新盘≤4GiB；MPI1/线程1。最多3轮工程修复、4次FE worker，合格raw优先复用；同根因两次修复无效、数值/资源/swap/累计时限触发即停止。task swap0、global新增swap即停，宿主零swap资格单列。完整命令和本机ABI均按第4.3节冻结。
>
> dot最新7580f5a已记录degree160准备75.948353秒/3.2477GB资源停止，没有C内核或向量。不得重试原样编译。dot自己按第5节在新7200秒/3GiB窗口先跑18cell/三tuple双极化/public Function.eval168/176独立reference，再只验证一个chunk256、degree160的原生基分块raw候选并Library取回；复用身份清单，不重复主线两代表面实验。C1a/b/c已通过各自小例；八组saved优化不冒充新live加速。双方之后按完整AUTO作用/恢复→公共后端及全部q同时因子成本→原尺寸收敛→场/模式精度与冷端到端账的顺序接续；后续大规模运行仍须独立准入。
>
> 当前原尺寸维持NO-GO：完整三维50×25×140nm、λ0.7nm、全部模式及未来缺口能力不变，整机十进制2TB无swap、完整流程48小时。完成授权数值交付或达到明确停止条件后集中回应，不只修报告、不追加网格/阶数扫描、不用新编号刷新预算。
