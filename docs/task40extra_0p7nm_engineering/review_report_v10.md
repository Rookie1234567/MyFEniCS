# Review V10：从边界核验推进到完整 p6 参考逆与三维缺口求解

## 0. 决策与执行身份

**本轮消除的 blocker：主线已有可信的缩小模型解和 x 方向精度证据，dot 已有完整 p4 周期参考逆及有界高振荡表面积分正结果，但它们尚未组成主线的完整 p6 求解能力。最近数轮被启动接口、时间政策、参考证明和存储校验反复截断。本轮不再以“又完成一个收据”为终点：必须实际尝试完整 p6 周期参考逆、非可分三维缺口求解与同离散对照，同时补齐原尺寸边界积分的必要缺口。**

用户本轮要求实质进展、遇到 bug 自行修复继续。以下是新的显式研究授权，不追认 V9 通过，也不重开其旧窗口。没有授权工作站运行或原尺寸全局分解。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task40extra_0p7nm_engineering
review_base_SHA        = 5cbcb507584bb52a3f15f321ebfde9d1c9ef5b72
latest_response_read   = response_v9.md
parallel_readonly_SHA  = 3f4fb69b20d33d382975bb96db73b44bba583ebd
review_file            = docs/task40extra_0p7nm_engineering/review_report_v10.md
response_required      = response_v10.md
campaign               = task40extra_v10_integrated_p6_engineering
machine                = 既有笔记本 local_wsl2_authorized，MPI1 / 数学线程1
canonical_worktree     = /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
ordinary_default       = UNCHANGED
workstation/master/dot_write = NOT_AUTHORIZED
```

先读根/目录 AGENTS、仓库工作原则、task、Review V7–V9、Response V6/V8/V9 和 summary。原始 task、V1–V6 历史保留。执行者沿现有窗口工作，不新建聊天、subagent、worktree 或环境；**执行者负责实现、测试、运行，主控负责审查、冻结源码、commit/push**。本报告只提交主线，dot 保持独占分支。

最终目标保持：50×25×140 nm、真空波长 0.7 nm、完整三维 Maxwell 和非可分缺口能力；整机物理内存不超过 2,000,000,000,000 B、无 swap、冷编译/构造/全部因子/迭代/恢复/输出/独立检查端到端不超过 172,800 s。目前原尺寸为 `NOT_QUALIFIED_FOR_TARGET_RUN`，不是“已证明数学上不可能”。

## 1. 本次审阅结论

下表为已发布记录，不是审阅端新计算；时间与资源不得跨环境相加或做严格速度比。

| 层次 | 已证实的结果 | 当前资格与缺口 |
|---|---|---|
| 主线缩小模型 | G0/G1、G0同离散直接参考完成；严格 identity 通过，不靠放宽门槛 | 同离散求解可靠；原固定样本通过不替代体积/curl精度 |
| 主线 x/z 误差分析 | Gx560更接近F5；后续Gx784原A6=9.6921151626e-7，恢复identity=6.4223807147e-11；与Gx560/F5八项场量最大差约6.42e-4 | 已测 x 方向一致性通过；y、连续极限及目标原尺寸网格未资格 |
| Gx784完整成本 | workflow monotonic3431.622642s；同时树RSS7,782,744,064B，任务swap0 | 当前可复用完整物理结果；没有匹配direct，不能称所有误差闭合 |
| 主线 W0 | 80-cell/p6/manual532/φ5，完整组件与955项独立保存数组检查通过；worker797.629s，树RSS2,204,782,592B | 无物理PDE；组件资格不等于完整p6参考逆 |
| 主线 W1/V9 | 原尺寸两代表面32060 keys；q30相对独立矩参考最大误差5.70590933；q60保存投影约4.03393e-12 | q30负结果成立；q60有限诊断好，不是完整作用资格。缺真实n=0、冻结分母重判等；p6未运行 |
| V9停止 | 归因阶段保守费用下界3617.121945s，超过旧3600s子限额；没有新FE或R/T/A | 按旧合同时间停止，不是Maxwell失败。历史总费用仍有unknown |
| dot完整p4参考逆 | 小80-cell/4q/manual532：regular最大原残差5.2672e-12；真实两cell缺口3–4步、最大约7.9667e-12；全部8640内部载荷和端口恢复 | 结构有正证据；弱扰动小模型，splu后端，不是主线MUMPS/p6或原尺寸资格 |
| dot最新有界积分 | 原尺寸18-cell边界fixture，六个top/x分量：degree160对168/176，最大运算尺度误差3.9087e-14；监督44.552426s、树RSS944,046,080B | 仅选定六分量。不是完整C/D、上下双分量或32060模式算子 |

证据入口：Response V3–V6/V8/V9、主线 summary；dot Response V11、最新 chunked_surface_mass_v2 记录及发布提交。dot最新发布SHA不等于数值生产源码：canonical源码仍为6dba8257053c6b2e474b7808b708a745f202733b，外部helper/reference/runner另有hash，移交时分别绑定。

### 1.1 对最近数轮的判断

既有精度、完整非零内部载荷、相位和独立原方程检查有必要；但是，“每个接口错误只能重放一次”“保存数据分析满一小时就阻断后面的独立求解”“要求完整浮点路径证明后才能做有限小模型试验”使有效组件迟迟无法形成求解器。这些是本轮要调整的执行和研究组织，而不是降低最终物理解要求。

本轮不重做：G0 direct、Gx784旧性能场、W0整套导出、两个p4原体积张量、32,060模式生成器、dot已成功的C1a/b/c和六分量原样试验。旧全部错误、超限、成本及unknown保留。

## 2. 两条工作链解耦：不要用原尺寸积分阻断小模型求解

| 链条 | 本轮必须尝试的数值交付 | 前置与失败处理 |
|---|---|---|
| A：原尺寸边界 | 修正参考核验；32,060 keys的两代表面完整作用；缺失p6 top/bottom原方程与内部恢复 | 复用W1与局部张量；只阻断使用该原尺寸积分的后续，不阻断已合格manual532小模型 |
| B：完整求解，第一优先 | 80-cell/φ5/manual532：准确p4完整PC对照与全p6周期参考逆；真实两cell三维缺口、完整物理RHS及输出 | 依赖主线W0和本机完整参考逆资格，不依赖链A的原尺寸AUTO通过 |
| C：工程锚点，条件继续 | 在既有Gx560/φ0/manual340物理缺口上使用唯一合格p6参考逆，比较保存准确p4场和完整成本 | B完整通过、能力与内存允许；不另换几何冒称Gx560 |
| D：成本与交付 | 全q真实后端、同时存活因子、边界/内部库存、端到端阶段时间；冻结下一档推广包 | 使用本轮已有结果，不为补表另建全局因子 |

**B为本轮主交付。**A的n=0/分母补正应先做，因为便宜且已有数据；但不得在A重复花数小时高精度全量计算而不开始B。本轮可以仅得到B而A仍有限，也可以A完成而B真实失败；各自如实报告，不相互冒充或互相否定。

## 3. A链：把高振荡边界积分变成可用组件

### 3.1 先修已有参考结果，不重新开始分析

读取旧W1 104成员与V9新增10成员，核对原source、输入、形状和hash。补：

1. 实际清单中`n=0`的模式及对应原场见证；区分“n=0”与κy=0，后者还受Bloch ky影响。本W1 φ0可检查零y频率解析极限；φ5不能假定为零。
2. 用原冻结`norm(saved q60_apply)`重算完整作用误差；每模式仍使用V9冻结尺度和原H，不改成新参考范数，不新加分母floor。原尺度为零时使用原已声明绝对规则，不用除近零“制造失败”或以max(1,...)“制造通过”。
3. 全32060输出重判q30、q60；保存x/y矩、B/D、两切向分量、投影和回散布的差异。高精度只计算去重的一维频率与有限低次矩，不给每模式、每基函数重做80/100位积分。
4. 同时补签名/相位桥。只有外部模式字段经比较一致才能复用；main中心坐标与dot正坐标差(25,12.5,0)nm，端口平面相位也不同。按显式公式变换，不拟合相位。dot大raw未在本机时，不等待Library传输才做主线已有数据。

独立矩公式使用NIST DLMF 10.54.2：

```math
I_\ell(\kappa;x_0,L)=\int_0^1 P_\ell(2r-1)e^{i\kappa(x_0+Lr)}\,dr
=e^{i\kappa(x_0+L/2)}i^\ell j_\ell(\kappa L/2).
```

这是dr积分，不重复乘物理L；Jacobian/Piola沿原定义处理。κ=0用解析极限；负实频率、复参数与相位分支按真实dtype测试。保留80/100位有限见证，但不把高精度一致自动等同全路径误差界。

### 3.2 明确调整参考资格合同，不伪称旧门已经通过

**本轮有限研究不再以“证明完整浮点构造到scatter的严格上界”为进入p6组件的必要前置。**该证明未完成继续记录，不给原尺寸生产精度资格。进入有限组件需同时有：

- 独立解析矩与一套不同实现的分块直接积分，在旧worst key、最大x/y频率、真实n=0和非零入射/端口见证上相符；差异按相同物理运算尺度报告。有限参考交叉差目标1e-12，不称普适界。
- 旧逐模式及完整作用的**原1e-10门不变**；在已保存输入之外，补一个预登记generic复输入及非零端口输入。不能只对有利输入放行。
- 对B、D原始完整局部行的受影响系数作分块交叉检查，包括微小非零内部迹；禁止裁零、以D=B^H替代、重标H或调整raw权重求和。
- 资格写`REFERENCE_EMPIRICALLY_QUALIFIED_FOR_TESTED_FACETS_AND_INPUTS`；不回写V9`REFERENCE_NOT_QUALIFIED`为PASS，不声称所有向量/所有网格已证明。

若q60满足这些门，直接用它完成本W1代表面，不开展q80/q100扫描。若不满足，唯一补救为在原面内部按相位跨度划分的复合Gauss积分或已验证的解析矩作用；这是同一个边界积分修复方向，不改变FE网格。分块规则根据全频率范围预先定，不依观察误差逐模式挑选有利规则。明显增加阶数的FFCx巨型表编译不再尝试。

允许选择性借鉴dot的分块原生向量实现，但必须把正式采用的数值核心放入主线src、记录来源文件hash和本机差异；不能直接运行云端scratch路径，也不把dot六top/x成功当本机全C/D成功。

### 3.3 完成两个真实p6局部对象

复用原W1面(100,1)、保存axis、top/air与bottom/Si；p6每cell882=450内部+432trace，所有32060 keys，模态批次默认64。仅新建缺失p6 volume/局部消元一次；旧p4 volume使用保存数据，只更新受影响边界和代数。

沿main既有DirectionalBoundaryAction/FacetPolynomial及native adapter扩展，不复制第二套大型runner。以非零内部、trace和port载荷验证原/约化方程≤1e-10、完整恢复≤1e-11。保留细小非零Bi/Di。H_p对角可紧凑表示，但Hhat的Di·solve(Bi·alpha)修正不能删；不物化32060²矩阵，不保存全域FE×模式稠密耦合。

一次完成一个对象即保存checkpoint。checker只重算真正数值关系和必要hash；某文件FD/路径/字段问题只修checker并重读，不重建已合格p6。A通过是代表类资格，尚非原尺寸全部面、全局MPC或截断收敛。

## 4. B链：全p6周期参考逆，而不是再改p4的一个开关

### 4.1 它解决什么问题

现有BAL_H用较低阶p4近似纠正p6，仍需较多外层步骤。新候选用**同阶p6的规则参考问题**提供更强修正；规则参考可按离散y平移相位拆成小块，而真实目标仍保留完整非可分三维缺口。

```math
A_{\rm target}=A_{\rm ref}+\Delta A,\qquad
A_{\rm target}B_{\rm ref}=I+\Delta A B_{\rm ref}
\quad\text{(理想准确参考逆时)}.
```

这解释了为什么弱局部缺口可能少步，但不是对任意缺口/强对比的收敛保证。它是结构利用型Full3D参考预条件器，不是二维最终解，也不能代替长期通用多层路线。

对已正确消元、包含端口的参考系统，用实际的primal/dual变换表示：

```math
T_L S_{\rm ref}T_R=\mathop{\rm diag}_{q\in\mathcal Q}S_q,
\qquad
S_{\rm ref}^{-1}=T_R\mathop{\rm diag}_{q\in\mathcal Q}(S_q^{-1})T_L.
```

只有实际证明变换酉性后才能将T_L写成T_R^H。所有q保留；Ny=4时四q全部执行且因子同时计入资源，不因φ0入射看似只激发一支就删分支，也不默认±q共享。

### 4.2 继承范围与本机资格

复用dot已发布的完整p4 two-cell/quotient/compact方案、公共组装与恢复接口，不重做p2/p4云端历史。先确认其最小源码依赖，选择性复制到main并记录原blob/hash、修改点和实际后端；不merge/cherry-pick整个dot分支、不写dot。

主线W0科学raw与955项checker是本机p6局部权威入口。**本轮必须构建新的完整p6参考逆，不能将W0 p6-component模式重命名成全链。**读取dot完整raw是辅助而非永久前置；若不可取得，利用已发布源码和本机已有W0数据完成本机独立验证，资格按本机新证据授予。

使用既有合格local_wsl2_authorized独立prefix；不得混入旧PETSc3.19/OpenMPI与新PETSc3.25/MPICH。每个进程记录Python、DOLFINx/Basix/MPC、PETSc complex128/IntType与库线程。沿现有MUMPS接口实施q因子，不改原准确p4的MUMPS选项，也不扫描后端；dot splu旧结果保留其原范围，不冒充MUMPS证据。局部dense LU可继续使用既有实现。

必须真实证明：全部原FE行的映射、所有内部RHS及端口RHS、原H与Hhat、几何方向/MPC、phase wrap、全部mode aliases，恢复后原A6相符。配方内存按所有同时存活q总和核算；不能以一q峰值乘4代替实际共存测量。禁止用制造载荷的代数闭合替代后面的物理缺口求解。

### 4.3 B0：80-cell同条件完整对照组

固定主线已完成W0族：缩小0.7nm、80 cells/4×4×5、φ5°、p6、manual532、同材料与真实两cell缺口。从既有receipt读取全部配置、mode keys、缺口cell与坐标；不能凭聊天重新造近似fixture。输入名带q4不代表允许改阶。

先做参考逆一次完整regular制造载荷检查：包含generic、interior-only、nonzero-port和physical，全部36,000内部自由度保留。regular原方程≤1e-10，作用/恢复沿1e-11，端口与变换身份原门保持。用同一已建参考因子接着完成真实两cell缺口的物理RHS外层，不在中途销毁后为了正式场再构建。

完整物理对照各一次：

| 路线 | 作用 | 运行规则 |
|---|---|---|
| B0-control | 当前准确p4-based BAL_H，求同一p6缺口问题 | 若已有真正同source/ABI/离散/相位/输入的完整物理结果可复用；只有组件记录不能代替 |
| B0-candidate | 新全p6周期参考逆，求同一完整p6缺口问题 | zero start、right FGMRES32、max2048；不沿用旧W2固定128步的提前负判 |

两场分别从clean committed source通过run_case与user-service启动，先后执行，因子不共存于两个独立流程。控制与候选物理A6、完整端口和原始入射相同。候选不要求每次解旧A4问题；**现有准确p4路线的A4验算不能被删，候选改成p6参考逆后须如实替换检查对象，而不是报告虚假的A4调用数。**

比较完整setup、所有q factor、全PC、KSP、恢复、输出和checker，不只比外层步数。输出E/H/curl、全部532复模式和R/T/A/A_volume。真实A6及释放后≤1e-6、恢复/identity≤1e-10、端口≤1e-8、能量绝对闭合≤1e-5。两份同离散解的FE/场/复模式相对差≤1e-4、总功率绝对差≤1e-5、逐mode功率差≤1e-6，近零量另报绝对尺度且不拟合相位。

若主控认为公共后端接线失败，先修其实际接口；不要退回splu后仍称“公共MUMPS通过”。若数学不等价或出现非有限/严重identity错误，停止候选升级并定位；不能用增加迭代掩盖错误算子。

## 5. C链：从小夹具走到既有工程锚点

B0-candidate准确通过且资源可控后，完成**至多一场Gx560新候选**，而不是再开一种PC。使用Response V4已保存的Gx560：10×4×14、560 cells、φ0、0.7nm、原解析三维空气缺口、manual340，完整原A6相同；p6参考问题只填回缺口作为规则背景，不改变target。保持所有四q与全部内部未知量。该真实缺口不是B0两cell扰动，正用于检查参考逆是否只对很弱小扰动有效。

优先复用Gx560准确p4保存场比较，不重跑基线。若ABI/基函数/积分身份无法映射而确实缺少同离散对照，先用独立原A6和物理坐标评估核验差异；仅确有必要时允许一场同条件准确p4控制，必须记录不可复用的实际原因。不同ABI/机器的历史时间只能辅助，不授予严格速度百分比。

若Gx560全部q共存预审不安全，**不提升cap、不缩小模型后仍叫Gx560**。保留B0完成值和Gx560实际阻塞对象，继续A及成本分析；不因此宣布整轮失败。C通过也只授予该离散缺口资格，不声称任意三维/原尺寸/2TB目标通过。

B0若正确但更慢，可基于实际分项做同一候选的一次明确低风险优化（分组局部solve/去掉重复数组/复用不变变换），先保存前后组件成本再决定C；不得改成多个shift/ILU/AMG/DD组合扫描。若劣化来自不可接受的全部q因子总成本，保留负结果并不做更大的C。

## 6. 原尺寸边界与新参考逆的衔接，避免过度推广

A通过不能直接对原尺寸15,232-cell计数候选建立全部q分解。该候选y4、z14的精度未被小模型x一致性证明；32,060仅传播AUTO库存，也不是完整DtN截断资格。

本轮只用实际A/B/C数据形成清单：边界每代表类构造/作用时间，q数量、每q行/NNZ、真实分解后端、全部q共存树RSS、内部与端口恢复库存、Krylov向量、cold JIT、输出以及生命周期。原尺寸项目中尚未实测的填充和时间保持unknown。

若B/C有显著收益，下轮选择原尺寸分级准入或更大电尺寸参考逆验证；若仅小扰动有效，下轮必须研究缺口扰动的全局误差补偿/多层方法，而不是将所有任意几何都强行解释成小扰动。

## 7. 运行与自修复：新完整窗口，不再逐个bug停审

### 7.1 本轮明确的新许可

本review新增**一个24小时（86,400 s）主线campaign**，含环境准备、修复、有限测试、A/B/C、checker、保存与清场。第一项执行前记录唯一T0、UTC/monotonic/boottime、boot ID和时间namespace；所有阶段共用，不因source提交、service重启、run_id变化刷新。旧V9窗口已结束，成本与unknown独立保留；24h研究预算不是原尺寸48h成功证据。

不再设置“归因满3600s即停止全部后续”的子限额。建议A必要补检后优先进入B；A可独立暂停并保存，B用合格小模式合同继续。最后预留600s整理与清场；不是无限延长许可。正常物理场最多B0两场+C一场，确有身份必要时增加C控制一场；制造载荷和局部A是有账组件，不藏成免费PDE。新算法失败不通过自动扩展场次或更换参数碰运气。

### 7.2 时间政策只做最小接线，不再开时钟研究任务

使用既有`CONSERVATIVE_REALTIME`累计：相邻样本对UTC正增量、monotonic和boottime取保守最大值并持久累加，回跳不返还。固定T0+24h UTC截止、boot内累计时长及保守累计任一耗尽即停，全部在一个parent监督下。启动和结束采样放在实际数值段前后；KSP另报自身monotonic。

**仅UTC与单调钟相差超过旧5s不再直接判数值失败或停止一个尚有预算的正常组件。**本条是显式V10策略变化，不把V8/V9历史改判。双单调钟/boot/namespace身份丢失、计时倒退或安全监督失联仍停止受影响运行。优先复用已测试timebase；只补必要的policy传递及一个无FE入口测试，不再连续运行两次60s clock-only服务。

Linux CLOCK_REALTIME可被调整，CLOCK_BOOTTIME包含挂起时间；记录差异不意味着已查明本机异常成因。[Linux clock_gettime官方手册](https://man7.org/linux/man-pages/man2/clock_gettime.2.html)是语义依据，不是WSL原因诊断。

### 7.3 安全与资源不放弃

每场effective cap取16GiB与实际物理/cgroup准入较小者，再保留系统与至少128MiB终止/证据余量；**16GiB不是允许在只有约9GiB可用的机器上分配16GiB**。B/C实际factor累计提前准入，不能用单个q估算取代全部共存。每次一个heavy，编译器、checker与后代全部计入。

任务VmSwap/cgroup swap保持0，非零或真实物理压力触发停止。全机pswpin/out另记；**仅未归因的全机历史/增量页数不自动等于本任务swap违规**，不作为独立停止理由，实际全机压力仍可触发资源保护。本条仅新campaign，不改旧V9的global-swap严格分类；不自行swapoff或改宿主pagefile。

PSS禁用记null。保留RSS采样、PID/start_ticks、失联保护和完整后代清场。新raw/缓存增量预审≤8GiB且保持至少2GiB磁盘空余；不无条件复制所有旧科学数组，不能靠删失败/旧权威清空间。cap不足则分块/复用；不缩窄进程树、不reset峰值、不恢复巨型二维求积表。

### 7.4 自修复和接续规则

- 不沿用每个case只准一次bug重放的旧门；本campaign内不同明确实现错误可自行修复。每次保留失败source/日志，解释根因，定向测试，主控冻结新source后继续。执行者不自行commit/push。
- 允许路径、activation、模块导入、tuple/list、元数据、FD、序列化、checker、native映射、实际索引或积分实现错误的最小修复；正确性修复必须有独立复验，不能只删除raise。
- 同一失败输入没有代码或物理上可解释的修复时禁止原样重跑。已通过的上游数组不重新生成；checker坏了只重读checker，输出坏了从已合格保存场恢复并另记状态。
- 不得为赶进度降低残差/积分门、删mode、裁掉小Bi/Di、少q、少内部RHS、改材料或将真实失败叫纯工程问题。
- 一个科学分支失败只阻断其依赖；继续其他已授权工作。最终时间/安全上限到达必须保存停止，不自动新建V10b延长。
- 只维护一个主清单和必要数值checker。不要对每个hash/格式错误另开十几个新报告或重跑全仓测试；历史完整字节保留，新的比较记录来源与转换即可。

## 8. 提交、证据与“实质进展”的判据

主控可按“最小接口及数值实现冻结—B0结果与C准入—综合结果”集中管理提交；不为每个函数修复要求新的用户授权，不超过既有每轮三次集中审阅往返。正式PDE仍须在clean committed source下，由`python scripts/run_case.py <实际新dat>`进入既有user-service/subreaper。新dat/profile须先实现并验证，不能声称旧p6-component CLI已能全链运行。

新规范路径可用`input/task40extra_0p7nm_engineering/review_v10_*.dat`；同一dat只代表一个明确计算。CLI与service参数由实现后的`--help`核验，报告真实命令，不凭文件名推测能力。

新增最小交付：

```text
response_v10.md
outcomes/review_v10_integrated_p6.md
outcomes/records/review_v10_manifest.json
outcomes/records/review_v10_boundary.json
outcomes/records/review_v10_p6_inverse.json
outcomes/records/review_v10_physical_comparison.json
outcomes/records/review_v10_cost_and_repairs.json
```

可以合并重复JSON，不能省核心字段。保存source/input/physical/discretization/ABI/ordered modes及变换身份；首次KSP停止原因、实际PETSc reason、KSP-only时钟在release之前写出。artifact原件一份，fsync和重开hash一次；必要独立checker实际读取数值，不以CRC或文件存在代替残差。

| 交付状态 | 允许的结论 |
|---|---|
| A完成、B未完成 | 原尺寸代表边界/局部p6的有限资格；未形成新求解器，必须写清B的实际阻塞 |
| B0完整通过 | 首个本机全p6周期参考逆及真实非可分缺口求解；比较完整总成本，不只写3步/4步 |
| B0+C完整通过 | 两个明确三维缺口范围内的工程路线，仍非任意结构/目标规模保证 |
| 正确但慢/内存更大 | 数学合格、性能负结果；不得升级为推荐快速低内存默认 |
| 只有测试、字段、论文或新计划 | 不能称本轮数值目标完成；说明剩余工程/数值/资源限制，不用PASS数量遮盖 |

以setup、全部factor、PC、KSP、恢复/输出三个大阶段组织最终表；一切父子计时和同一对象别名不重复累计。列每步成本、总步数、到真实残差目标的完整时间、同时树RSS与因子总库存。y分支不是物理维度裁剪；新路线适用边界必须与一般任意三维目标并列。

同步summary、run index、development_progress与development_model_registry。本轮只研究主线；dot数据按只读引用，是否新增其云端任务需单独授权。不开PR、不merge master、不动工作站；主控推送后返回完整远端HEAD和主要数值结果统一审阅。

## 9. 阅读与引用

- [主线近期完整物理解](response_v6.md)、[x/z四角](response_v4.md)、[最新受限结论](response_v9.md)、[summary](outcomes/summary.md)。
- [原W2全p6设想](review_report_v7.md)、[V8组件链](review_report_v8.md)、[V9边界冻结尺度及失败](review_report_v9.md)。本报告重新授权并解耦其依赖，不假称W2已经运行。
- [dot p4完整恢复逆](https://github.com/Rookie1234567/MyFEniCS/blob/3f4fb69b20d33d382975bb96db73b44bba583ebd/docs/task40extra_dot_parallel_cloud/response_v11.md)、[dot最新发布](https://github.com/Rookie1234567/MyFEniCS/commit/3f4fb69b20d33d382975bb96db73b44bba583ebd)：小结构与六分量正证据，不能相乘外推原尺寸速度。
- [当前方向边界实现](../../src/solvers/directional_boundary.py)、[现有W1 runner](../../benchmarks/run_task40_w1_boundary_probe.py)：扩展现有接口，保留native完整行与精确坐标。
- [NIST DLMF 10.54.2](https://dlmf.nist.gov/10.54#E2)：Legendre—球Bessel积分恒等式。它提供参考数学关系，不提供本项目整条浮点计算的现成误差界。

审阅范围：远端任务/规则、近期response/outcomes、关键源码和dot发布记录；没有在审阅端运行FE、PDE或读取ignored完整科学数组重新计算。本文指标来自所引记录，新许可与候选是研究设计，不是已有性能成绩。
