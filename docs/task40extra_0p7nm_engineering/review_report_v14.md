# Review V14：完成已有工程求解，不让准入接线与装配暂存成为新阻塞

## 0. 本轮裁决、最终目标与权限

**首先消除的blocker：V12已经在本机建立Gx560全部四个p6参考因子，V13也已实现完整残差修正及受控不精确PC，但最新远端仍只有实现/修复提交，没有V13完整结果档案。当前最需要的是完成Gx560真实三维求解，而不是再增加一种PC。本review接续已有工作，补上两处具体执行缺口：让已授权的装配回退真正穿过CLI；避免全量Python结构集合与CSR重叠，重新制造内存障碍。**

最终目标保持：真空波长0.7 nm，50×25×140 nm目标域，complex128、Nédélec H(curl)、x/y Floquet、z方向Fourier-DtN，保留任意非可分三维目标方程；约2 TB为整机物理内存而非允许程序占满的RSS，保留系统余量、任务零swap；必要编译/构建/全部因子/迭代/恢复/输出/独立检查总时间不超过172800 s。当前没有该目标资格，也没有不可行性的数学证明。

研究关系不变：单元凝聚减少全局未知量；完整p6周期参考逆为真实三维target提供修正；共享模板和有界装配控制实现开销。参考背景可规则化，**target、RHS、真实缺口不得规则化**。这条路线是结构利用型工程候选，不证明任意三维都可少步，也不替代长期分布式、matrix-free、可扩展Full3D iterative主线。

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task40extra_0p7nm_engineering
review_base_SHA            = 0a442ba11a66525d5010d1b6cd6384d0de8d8eab
latest_review_before_this  = review_report_v13.md
latest_archived_response   = response_v12.md
last_archived_Gx560_source = 6d2c54389fe885ecf24d474a8782166ff31f9154
readonly_dot_SHA           = 15713d3e09b63f65511c7b7f61fa043fdb23dca5
review_file                = docs/task40extra_0p7nm_engineering/review_report_v14.md
response_required          = response_v14.md
canonical_worktree         = /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
execution                  = existing local_wsl2_authorized; MPI1; maththreads1
roles                      = 执行者实现/测试/运行；主控审查/冻结源码/commit/push
workstation/dot/master     = 不写入、不运行、不合并
ordinary_default           = UNCHANGED
```

本次是**进行中实现的综合审阅与续作授权**，不是V13最终验收。先按本机真实服务/账本核对V13是否运行、完成或停止；远端没有response不等于本机未运行。已运行的进程不得为应用本review而停止、热改源码或换PC。当前review不授权新环境、聊天、worktree、subagent或自动化。

## 1. 仓库快照与证据分层

审阅日期为2026-10-07。主线最新提交时间为2026-10-07 02:23:52 UTC（UTC+8为10:23:52）。相对Review V13提交ac7abfc0，远端有4个后续提交；变更列表没有新的outcomes或response_v13。最新结果总览仍是V12。dot仍是2026-10-05的15713d3e，没有新的远端发布，不能推断云端实时是否闲置。

| 层次 | 证据与实际内容 | 本次可接受的结论 |
|---|---|---|
| 已归档B0 | 80 cells、p6、532模式、全部四q；V12原A6残差1.6089774391665316e-8；保存场重核能量差8.287925901129256e-11 | 小模型有线性求解与保存场物理证据；原worker输出exit4不改写为fresh通过 |
| 已归档Gx560 V12 | 560 cells、340模式；四q全部numeric；allocated/used保守合计4.645/4.080 GB；tree峰10.181664768 GB | 内存已能容纳该构建前缀；不是完整target求解峰值或时间 |
| Gx560 V12失败 | 完整参考残差2.0058682739535859e-10、局部合并1.4183642641040464e-10、alpha闭合1.1770163447864681e-11 | 原strict失败保留；FGMRES未启动，不叫target不收敛 |
| V13已提交实现 | 增广残差修正、strict/inexact两级、预分配q装配、三份dat与入口接线 | 是源码事实，不是这些实现的完整性能或物理资格 |
| aaef9094修复 | CLI接受精确V13身份，提交信息记录14项定向测试 | 修复了前FE入口拒绝；无新完整PDE数字可供审阅 |
| 0a442ba1修复 | 恢复strict原合并局部范围；分扇区值仍记录；修正见证另命名；提交信息记录19+9项测试 | 方向与V13原合同一致；既往初次raw被覆盖的缺口必须保留，不假称已经恢复 |
| dot既有成果 | p4共享完整实体变换；原尺寸夹具完整882行选定边界通过，84行压缩未资格化 | 继承已迁入的思想及主线已有全模式代表面结果；不重复测试或整体merge |

主要证据：[当前summary](outcomes/summary.md)、[Response V12](response_v12.md)、[V12 formal results](outcomes/records/review_v12_formal_results.json)、[V13合同](review_report_v13.md)、[入口修复aaef9094](https://github.com/Rookie1234567/MyFEniCS/commit/aaef909487415e94d2e46aa7f352487ed419844a)、[strict与保存修复0a442ba1](https://github.com/Rookie1234567/MyFEniCS/commit/0a442ba11a66525d5010d1b6cd6384d0de8d8eab)。上述测试数来自提交说明，本审阅没有重跑测试或把它们当作完整计算证据。

## 2. 接手与执行：先复用正在进行的成果

主控先读取实际service、PID/start_ticks、run_index和固定窗口，形成一份简短continuation receipt，不为此运行FE。

| 接手状态 | 必须采取的动作 |
|---|---|
| V13合法heavy正在运行 | 按原冻结source/输入/监督让它继续；不pull到活跃源码、不重启。新review只在安全阶段接入；已有通过结果计入本轮里程碑 |
| V13已经完整通过B0/Gx560或Gx784但未推送 | 先整理原始证据、直接复用；不为了V14编号再跑同一场 |
| V13因具体工程错误已停止 | 复用合格保存数组和已完成检查，最小修复后续作；已清理因子不能假称仍在内存 |
| 当前已失败且无存活进程 | 完成下述入口/策略/存储定向检查，冻结唯一组合，再补缺失里程碑 |

**不另立“每完成一阶段等待主审”的门。** 主控冻结source是既有职责，不等于让ChatGPT每阶段再审批。response_v13若尚未形成，可先写简短交接，最终response_v14一并索引实际V13运行；不得凭空补写V13终态。

## 3. 数值策略保持V13，不再无依据收紧或放宽

### 3.1 修正对象与代价

原增广参考方程是：

```math
\mathcal A_r z=b_r,\qquad
\mathcal A_r=\begin{bmatrix}V_r&B\\-D&H_p\end{bmatrix},\qquad
z=\begin{bmatrix}u\\\alpha\end{bmatrix}.
```

初次状态不满足原strict时，至多使用同一四q因子做一次完整修正：

```math
e_0=b_r-\mathcal A_rz_0,\qquad
\delta z=M_re_0,\qquad z_1=z_0+\delta z.
```

FE与alpha一起更新；每次逻辑调用最多4次额外q MatSolve，无新factor、无递归修正、无隐式内层Krylov。保留独立native参考作用，不以同q矩阵自洽残差代替它。该做法可能改善，但不保证一次必达strict。

| 检查 | strict | 已授权inexact上界 |
|---|---:|---:|
| 原完整/增广FE参考方程 | 1e-10 | 1e-8 |
| 原局部方程合并值 | 1e-10 | 1e-8 |
| 每局部扇区 | 原样记录，不新增strict停止线 | 每个1e-8 |
| global alpha闭合 | 1e-11 | 1e-9 |
| 每次实际q求解 | 1e-10 | 1e-8 |
| 映射、覆盖、原算子身份、内部恢复和representation identity | 原门 | 不放宽 |

0a442ba1恢复strict的原合并范围，不是授权忽略真实扇区错误。几乎未被激励的扇区，其局部RHS可能很小；只有比值不能区分小分母与大绝对误差。记录实际分子、分母、全局激励及扇区份额；不把测试中的589.5067自动当作实测Gx560错误，也不因此删除该q、加任意floor或偷偷更改inexact规则。

初次strict通过立即使用，不为追求更小数值强制精化。若修正后比初次差，按V13同一完整状态的原尺度与冻结尺度规则选择合格者，不能只选最小的某一项，不能拼接u/alpha。超过inexact上界仍是受影响数值失败，不伪称普通bug。最终target原A6及释放后均<=1e-6、target identity<=1e-10、原物理门不变。FGMRES允许变化/非线性右PC，但不保证任何不精确PC收敛；原方程和场比较才是最终裁决，[PETSc说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)。

### 3.2 一批有针对性的防回归，而非再建立一套证明平台

复用已有19项、9项等定向测试，只补缺失边界：初次strict且一个诊断扇区小分母；初次inexact、一次修正变好/变差；累计FE/alpha与冻结尺度保持一致；真实结构错误拒绝；zero RHS保留零态；实际CLI能将所选组合传到startup/PC/parent/checker。需要真实FE的检查并入本轮必要B0构建，不额外建立工程因子。

检查初次已合格inexact而可选修正失败时的行为。只有明确的有限数值精度失败、初次完整状态已通过全部准入、原状态及原因子未被破坏且可核验，才允许记录该次修正负结果并返回原合格状态；不得catch任意异常。NaN、映射/端口/算子错误、factor损坏和资源停止仍按原规则处理。无法区分原因时不把未知异常吞掉。

### 3.3 原始科学证据不得再相互覆盖

保存身份至少区分run/attempt、RHS或PC call、initial/correction/selected和source。沿用已修复的sample_label，不全局重构所有保存器。新增见证使用独立名字与已存在文件拒写/显式恢复检查；先写临时文件并原子替换该新文件，摘要只在依赖文件成功后发布。初次raw已丢失的历史记录保持RAW_UNAVAILABLE；新源重建只能叫新诊断，不能恢复为历史实测。

修复checker、可选绘图、计数或JSON序列化，不要求重做已经合格的PDE。反过来，数值/映射核心改变须按影响范围重新验证，不能复用不相容场授予新方法资格。

## 4. 必须解决的实现冲突：优化失败时应当真的能回退

V13明确允许预分配优化无收益时保留旧装配继续求解。但当前`run_case.py`的V13合法tuple只接受`PREALLOCATED_CSR_PATTERN_V13`，测试还将V13改成`LEGACY_GLOBAL_CSR_SUM`作为拒绝案例。**因此，数值层虽然有legacy实现，正式入口却挡住了review授权的回退。**这是源码可复核的合同冲突，不是已测性能问题。

本轮明确授权：三个已审阅物理case在`STRICT_THEN_BOUNDED_INEXACT_V13`下，可以使用已验证的`PREALLOCATED_CSR_PATTERN_V13`或`LEGACY_GLOBAL_CSR_SUM`。若改为有界存储实现，使用明确版本化的策略身份或source/algorithm身份记录。主控冻结组合；相关schema/validation/CLI/launcher/worker必须从同一小型allowlist或一致的计划读取，不在每层重新猜一遍。**这不是删除run/profile/physical/campaign身份检查，更不放行任意profile。**

将“错误physics/profile/未知strategy必须拒绝”和“同一物理下被授权的装配回退应通过”分成测试。实际validate-only/dry-run可先验证三个case，没有必要靠失败FE启动来验证入口。

## 5. 预分配并不自动省内存：只改当前这一项setup候选

### 5.1 已定位的增长风险，不冒充新运行结果

当前`_assemble_preallocated_q_patterns`为一个sector的四个(p,q)块建立全量`list[set]`；对每项局部支持逐Python整数去重；每新增结构项按128 B预算；所有集合还活着时生成CSR，最后才`del row_columns`。这有资源准入保护，但仍可能用大的Python结构库存替代原来的CSR重复相加开销。

V12四个对角q的实际NNZ之和为：

```math
N_{\rm nz}=15451743+15479361+15581290+15479361=61991755.
```

仅按现有代码128 B/结构项的预算，合计为7,934,944,640 B。构建是分sector进行，**不能把这个跨sector累计量当同时峰值**；其中q0/q2两对角一组对应3,972,228,224 B预算，尚未计该sector两非对角结构、CSR物化重叠和已存其他对象。这是沿旧NNZ作的风险情景，不是V13新pattern数量或实测RSS。

另一个观察：`pattern_seconds`当前在CSR物化前就结束，而audit说明写成包括CSR构造；记录要分为pattern discovery、CSR materialization、numeric projection/accumulation，不能继续用未归因差额判断性能。

### 5.2 实现与选择

先读取本机已经完成的B0配对，若候选没有合格全构建收益，直接选择legacy完成主求解，不为预分配再等一轮review。若证据显示preallocation值得保留，则只在同一候选内收紧暂存：用有界row-tile的结构计数/紧凑索引拼接，或可验证的数组式结构构造，**不要全程保留每个全局非零项一个Python对象**。

规则：最终合法CSR/factor库存单独预算；额外可变pattern/COO/row-map暂存给出显式上限（建议不超过256 MiB，且仍取真实余量更小者），到边界前释放/切块，不等待OS OOM。只重复必要的轻量结构遍历，不因每个tile重新积分、重复凝聚或求解局部矩阵；材料/几何/方向均精确。不得无限缓存数值贡献，不同时保留Gx新旧全套oracle。

四个局部(p,q)块都要正确累计。非对角块的抵消必须在全部相关贡献相加后检查，不逐cell删掉；保留原算子/作用1e-11门。可以在完整累计后删除**精确等于零**的存储条目并记账，不对小非零阈值截断。报告stored NNZ、actual nonzero count、explicit zeros，防止结构超集送进symbolic造成无谓开销；SciPy明确区分显式零与未存储零，[说明](https://docs.scipy.org/doc/scipy/tutorial/sparse.html)。

选择看完整构建时间（含结构、转换、必要检查）与实际暂存，而不是仅numeric累计内核。一个候选失败仅回退该优化，不撤销已有共享bank和参考PC，不把“没有新加速”变成“不执行真实target”。本轮不另外扫描batch、AMG、DD、NN、BLR或MUMPS排序。

## 6. 主要交付与连续执行顺序

| 阶段 | 本轮动作 | 必须产生什么 |
|---|---|---|
| E0 接续 | 判断实际V13进程、结果、source及窗口；读取已有配对和失败见证 | 当前证据清单，不热改、不重复已成功场 |
| E1 定向闭环 | strict/inexact范围、完整候选状态、不可覆盖见证、允许装配回退的入口测试；选择唯一组合 | 同一真实入口可运行的冻结配置，不只是helper测试 |
| E2 B0 | 复用已完成且适用的V13 B0；只有尚缺合格anchor或核心改变时补一场 | p6/80cells/phi5/532模式/四q的完整目标解与输出；不能用制造载荷替代 |
| E3 Gx560 | B0合格后，原10×4×14、p6、phi0、340模式、真实缺口；同进程建立因子、startup修正、target FGMRES | 原A6、完整FE/alpha、R/T/A与体吸收、全部模式、全部q同时live库存、全过程时间与RSS |
| E4 Gx784 | Gx560通过且真实容量安全，原14×4×14、p6、340模式、原物理 | 同离散旧p4场比较和网格增长成本；不为少步缩小缺口 |
| E5 目标桥接 | 复用结果、已有原尺寸库存和输入，形成下一电尺寸准入包 | 明确可运行项/缺口/下一唯一瓶颈，不宣称2 TB/48 h已过 |

B0/Gx560/Gx784是**里程碑，不是每次review强制各跑一次的次数配额**。V13已经完成、满足实际所选核心身份的里程碑直接承认；本轮正常fresh数量只等于缺失或失效的里程碑，最多3场。合理自修复重放单列，不挑最快样本，不把失败成本隐藏。沿已有V13 dat路径或显式新run身份，不复制巨型worker；不同attempt目录和source/provenance必须分开。

本轮主数值里程碑是Gx560。已通过的参考检查/修正必须直接接target，不在中间销毁合格因子等待主审。若Gx560仍资源不安全，先完成已授权有界装配/明确冗余处理；确认是不可消除的当前容量缺口才停止其升级，继续已存场检查与目标准入包。不抬cap、删q或改物理来制造成功。

### 6.1 每场最终Gate

零初值、FGMRES32/max2048、MPI1/数学线程1、现有MUMPS配置不变；p6凝聚外层、全部四q、完整恢复。Gx560/Gx784内部行分别为252000/352800。每8步原A6、每32步场/解保存、终态及释放后原A6<=1e-6；真实target identity<=1e-10，完整finite E/H/curl、所有模式及能量/吸收绝对闭合<=1e-5。

同离散比较沿V13/V11原门及已存在的更严格专用门：不拟合全局相位；旧global-z与新boundary-plane先做合格坐标变换；总场、散射场、curl、显著复模式与全部模式功率并列。系数byte-equal可给代数等价结论，不冒充新增积分。求解通过而参考数组缺失时标明authority limitation，不删除已有合格物理解；跨网格一致性与连续误差资格继续分开。

## 7. 面向0.7 nm、2 TB、48小时的可执行桥接

本轮不得继续把开发窗口、单场PDE墙钟与48小时生产目标混作一个数字。完整生产成本为：

```math
T_{\rm case}=T_{\rm mesh/MPC/JIT}+T_{\rm local/ref/assembly}
+\sum_q T_{{\rm factor},q}+T_{\rm target\,KSP}
+T_{\rm recovery/output/checks}.
```

```math
M_{\rm peak}=\max_t\left\{M_{\rm live\,operators}(t)+M_{\rm all\,q}(t)
+M_{\rm local/port}(t)+M_{\rm Krylov/work}(t)+M_{\rm other}(t)\right\}.
```

每个父项/子项边界清楚；MUMPS18.1秒不能代表旧2089秒构建前缀，policy charge不能当FE time。cold JIT、同源复用JIT分别记录，不能把编译移到账外。tree RSS、cgroup、backend allocation和unique backing互不混称。q因子总量及局部因子总量都要记录，不只记录最大的一个。

生成`outcomes/v14_engineering_to_target.md`与一份紧凑JSON，至少明确：

| 层次 | 要回答的问题 |
|---|---|
| Gx工程证据 | 减少迭代后，完整时间是否下降？修正调用成本是否抵消收益？共享和装配各自影响什么？ |
| 固定0.7 nm的电尺寸阶梯 | 当前Gx560/784仍是缩小单胞网格变化，不是原尺寸增长；下一单一放大点如何保持解析几何/真实材料与可解释h/p？ |
| 原尺寸成本候选 | 现有272×4×14=15232cells与32060模式仅是候选身份，不授予y/z分辨率、截断或任意三维精度；列真实h_x/h_y/h_z、kL、phase-per-cell、trace/内部/端口计数 |
| 资源与索引 | 当前int32、全部q结构/fill、pattern暂存、端口数据、Krylov与恢复的增长；索引溢出检查同时看rows和NNZ/indptr，不只看矩阵行数 |
| 下一准入 | 由实测最大成本选一个对象；给可执行输入/已有脚本与未实现接口的区别，不虚构one-command目标程序 |

允许从现有解析轴和mode manifest做轻量计数/分组、准备下一固定0.7 nm电尺寸case的输入及dry-run，不自动启动新大PDE，不生成TB级矩阵。真实采样不足的目标时间/内存填unknown或带假设情景，不用cells线性倍率宣布48小时通过。

若全部q因子增长主导，后续研究q块内部的有界/多层求解；若构建主导，继续紧凑装配/重复数据消除；若真实三维差异使迭代恶化，才加强全局纠错。依据本轮证据选一个，不同时开多个算法试验。原尺寸完整运行、工作站推广、Ny任意增长和新PC须另行准入，本review不写工作站或dot。

## 8. 自修复、窗口和停止规则

**本review不刷新活跃V13窗口，也不为换编号强制终止合法运行。** 若窗口仍有效，继续原T0/deadline/账本，V14作为续作裁决；若它已终态或自然结束且里程碑尚缺，先写旧terminal receipt，再启用本review授权的唯一补完窗口，最长24h、收口预留600s。不得两个窗口重叠、旧账清零或为了单个bug反复续命。开发窗口与最终单场48h不同。

不同明确实现bug可最小修复、定向测试、主控冻结新source后继续；接口参数、计数、序列化、字段缺失和可选绘图不应成为整轮停止的理由。没有实质修复不得原样反复heavy；数值精度失败、容量不足或真实性不明不是普通bug。对无法消除的硬阻塞，完成不依赖它的独立工作并保留真实结果，不能降低物理要求换成功。

保留16 GiB与实际动态准入较小值、系统余量、task zero-swap、快速整树RSS、PID身份、失联与后代清场。PSS未采记null。总cap与新增headroom分开，旧8GiB、历史步数/时间/RSS成绩不是停止线。既不因小版本标签误停，也不因为用户要进展而绕过OOM风险、NaN/Inf、错误算子、约束破坏或factor失败。

## 9. 提交、证据与验收

主控按小型逻辑提交冻结：必要入口/保存修复；有界装配或回退选择；完整运行证据与总结。数值行为进入可复用src，不继续复制task worker。执行者不commit/push，主控在同一分支集中提交，无amend/强推/merge master。

优先少量、能够独立重算的证据：

- `response_v14.md`与更新summary/README/run_index，明确V13在审阅时未归档与后来实际状态；
- `review_v14_execution_handoff.json`：source、窗口、实际服务、复用/重跑理由；
- `review_v14_reference_and_assembly.json`：strict/inexact、候选选择、初次/修正见证、实际装配策略与暂存；
- `review_v14_formal_results.json`：三里程碑、source/input/physical/ABI、真实残差、场/模式/功率及统一分阶段成本；
- `v14_engineering_to_target.md/json`及两级模型总账。大型raw/NPZ/矩阵仍ignored，只提交必要hash、路径和紧凑字段。

旧已覆盖数据的缺口不得补成原件；未来见证不覆盖。checker从数组/原字段重算，不只读status。文档公式使用GitHub math fenced blocks，表格列数一致；实际未跑的FE、MPI4、全仓测试或CI均明示NOT_RUN。

**验收重点：是否取得Gx560完整真实解和成本，以及条件Gx784/下一电尺寸准入，而不是新增多少测试、修复多少小bug。** 若当前所有必要结果已经在本机完成，本review应让它们尽快形成可审阅交付，不再启动多余计算。

## 10. 审阅范围与依据

本报告由远端HEAD、最新已归档结果、V13变更和关键源码审阅形成；未在审阅端运行FE/PDE、未重放ignored科学数组，未获取本机实时进程。源码风险是待核验假设，未当作最新实测失败。dot只读至15713d3e，未运行或修改。

关键实现入口：[修正与选择](../../src/solvers/augmented_reference_correction.py)、[完整worker](../../src/runners/task40_v10_worker.py)、[q块装配](../../src/solvers/task40_v10_p6_yorbit.py)、[CLI](../../scripts/run_case.py)。公开资料只支持一般API语义，不替代本机ABI资格：[FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)、[稀疏数组与显式零](https://docs.scipy.org/doc/scipy/tutorial/sparse.html)、[PETSc COO预分配](https://petsc.org/release/manualpages/Mat/MatSetPreallocationCOO/)。不要求升级任何库，也不将COO当作无成本替代。
