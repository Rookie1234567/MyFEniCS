# Review V12：共享p6实体变换与收紧构建生命周期，完成Gx560并取得真实扩展成本

## 0. 决策、目标与执行身份

**本轮消除的blocker：p6周期参考逆已经在B0真实三维缺口上取得三步原A6收敛，V11又关闭了端口功率坐标错误；工程网格Gx560却在数值因子产生前已有10.295 GB常驻工作集。源码显示，它没有启用共享实体变换：全域与两个半域合计1120个单元，各自构造、保存450×450 complex128内部坐标变换，仅这一类原矩阵载荷就派生出3.6288 GB，尚不含后续逐实体缓存的逆。dot已有p4共享存储正证据，但主线没有迁入bank实现，p6也没有资格。本轮必须实施、验证这一具体存储改造，随后继续同一Gx560完整求解，不以完成内存清单或修复提交为终点。**

最终目标不变：真空波长0.7 nm，原尺寸50×25×140 nm，完整三维Maxwell、complex128、Nédélec H(curl)、x/y双Floquet、z方向Fourier-DtN；首先推进规则目标工程解，同时保留并实测非可分三维缺口能力。整机物理内存≤2,000,000,000,000 B、无swap，必要冷编译/构建/全部因子/迭代/恢复/输出/独立检查端到端≤172,800 s。**当前目标状态是未资格化，不是数学上已证明不可行。**

```text
repository          = Rookie1234567/MyFEniCS
branch              = task40extra_0p7nm_engineering
review_base_SHA     = 8bb945a43e8bd1f0125566399a402028c88f0010
latest_response     = response_v11.md
review_file         = docs/task40extra_0p7nm_engineering/review_report_v12.md
response_required   = response_v12.md
campaign            = task40extra_v12_shared_p6_transforms
readonly_dot_SHA    = 15713d3e09b63f65511c7b7f61fa043fdb23dca5
Gx560_run_source    = 9977284c47c8028751de4dbecd12b95d1912a580
canonical_worktree  = /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
execution           = existing local_wsl2_authorized; MPI1; math threads1
roles               = 执行者实现/测试/运行；主控审查/冻结源码/commit/push
ordinary_default    = UNCHANGED
workstation/master/dot write or execution = NOT_AUTHORIZED
```

先读根/目录AGENTS、仓库工作原则、task、V11、Response V11、summary及下列证据。原任务与全部历史保留。本报告取代旧review关于本次研究内容、续作次数和窗口的相应条款；不改物理、最终精度、真实资源安全和协作角色。目录中“当前V10”等旧导航不阻止本轮V12。保留Windows Codex客户端与既有WSL后端，不要求更换前端、环境、项目或worktree。

本次审阅基于远端源码、compact与提交差异，没有重放ignored科学数组或运行FE。公式载荷为审阅推导，不是新增RSS测量。只新增主线review，不写dot、工作站或master。

## 1. V11与dot综合裁决：接受已有成果，不重复做已闭合的工作

| 项目 | 已发布结果 | 接受范围 / 本轮处理 |
|---|---|---|
| B0原p6求解 | 80cells、φ5、532模式、四q、真实两cell缺口；3步；原A6/native约1.609e-8；原worker1051.699 s、树RSS3.714 GB | 保留完整离散求解正结果；4.899 s仅纯KSP，不称整场时间 |
| B0保存场功率修复 | R=0.9842736080926772；T=0.014240518143988908；A_balance=0.001485873763333926；A_volume=0.00148587384621333；能量差8.287925901129256e-11 | 接受SAVED_FIELD_PHYSICS_REVALIDATED；不是fresh PDE，旧exit4与energy FAIL保留。不再重做gauge归因 |
| 原尺寸两p6局部块 | forward约5.35e-14/5.14e-14，原方程约4.77e-16/6.41e-16 | 仅保存块的repair candidate，不追认为完整生产恢复链已迁入；本轮不重复全q60证据 |
| Gx560 | 10×4×14、p6、340模式；四q symbolic完成；numeric、KSP及场均未运行 | 真实资源准入停止，不能写solver失败或numeric已占4.6 GB。下一主交付仍是它 |
| Gx784 | 条件未满足，NOT_RUN | 保留；Gx560通过和真实准入安全后直接继续 |
| 主线V11全模式组件 | 两代表面、每面完整882行、各16030模式；Bα/Dx误差分别top约1.13e-13/3.86e-14、bottom约1.04e-14/3.91e-15 | 32,060库存的两面动作通过；不是全部边界、全域MPC或算子范数资格。本轮只读复用 |
| dot最新HEAD | 15713d3e与上轮相同；12选定模式、上下/x/y完整882路线通过，84压缩24/24未获证 | 没有新的远端进展，不能推断云端实时idle。不得把84压缩称成功，不另开压缩证书研究 |
| dot历史共享实体变换 | Response V12：p4/80cells，完整matrix/inverse逻辑69,435,392 B；共享backing owners410,624 B；原312数值门及存储门通过 | 是存储资格，不是RSS下降（测试期旧新对象共存）；不能直接授予p6资格，但应优先选择性迁移 |

主线最新提交是2026-10-06 09:40:52 UTC（UTC+8为17:40:52）。dot最新提交为2026-10-05 02:35:48 UTC。时间来自提交元数据，不当作实际运行终态时间。

证据：[Response V11](response_v11.md)、[结果总览](outcomes/summary.md)、[工程结果compact](outcomes/records/review_v11_engineering_results.json)、[dot共享存储](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/response_v12.md)、[dot最新边界](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/outcomes/paired_boundary_support_pilot_v1_zh.md)。

## 2. Gx560资源停止：厘清数字，不删安全门

### 2.1 实测和投影分开

| 对象 | 数值 | 口径 |
|---|---:|---|
| numeric前gate的live tree RSS | 10,295,283,712 B | 当时采样 |
| 本次tree RSS峰 | 10,418,892,800 B | 全过程同时进程树采样峰 |
| cgroup峰 / 限值 | 10,930,950,144 / 17,179,869,184 B | 与tree不同，不相加 |
| 原gate投影 | 15,205,944,640 B | 未发生的未来预算，不是measured RSS |
| 冻结有效finite cap | 13,462,286,336 B | 本场启动包络，不是下次可照抄常数 |
| 停止时MemAvailable | 3,301,220,352 B | 额外可用空间，不是允许任务总RSS只有3.3 GB |
| 余量扣除后的remaining headroom | 3,167,002,624 B | 增量口径，不能和总RSS直接比较 |
| Gx560 elapsed | service2041.826505 s；watchdog2041.652704 s | 中断场成本；不是完整求解时间 |
| task/cgroup swap | 0/0 B | 不能扩大为不可见Windows宿主的全机零swap资格 |

**本次停止有合理资源依据，不属于误把历史8 GiB当停止线。**即使存在下述冗余，未释放前也不能先假定内存已经省下。保留V11原RESOURCE_CONTROLLED_STOP_BEFORE_NUMERIC。

### 2.2 修正一个标签：4.776 GB不是纯MUMPS因子估计

四个INFOG16/17分别是1157、1150、1169、1165 MB。按当前代码每q加1 MB的保守解码：

```math
M_{q,\mathrm{sum}}=(1158+1151+1170+1166)10^6
=4,645,000,000\ \mathrm{B}.
```

现有未来向量预算使用114100行、72个complex128向量：

```math
M_{\mathrm{vec}}=114100\times72\times16
=131,443,200\ \mathrm{B}.
```

两者相加才是compact字段`all_q_native_symbolic_estimate_bytes=4,776,443,200 B`。再加128 MiB reserve，得到旧15,205,944,640 B投影。**只修正新报告/新schema的字段语义，不改写旧原件；分开记录factor_estimate、future_vectors与reserve。这项标签修正本身不省内存，不能据此放行。**

INFOG是后端统计，不能替代RSS。每q实际matrix NNZ和symbolic时间目前在最终compact缺失；从原事件能读到就补，读不到保持unknown。下一次必须在每个symbolic结束立即保存，而不是等numeric成功后才追加`factor_inputs`。数值因子尚不存在，不能把符号条目数当数值fill。

## 3. 源码已定位的首要改造：共享完整p6实体坐标变换

### 3.1 它是什么，不是什么

这些变换把同一有限元实体的native自由度坐标转换为周期分块所需的canonical坐标。它们不求解Maxwell，不是单元内部物理LU，也不是p4/p6全局因子。相同基函数和方向状态的完整变换可以有多个借用者，共用一个只读数值模板；每个实体仍保留自己的行号、位置、相位和MPC关系。

当前[source](../../src/solvers/task40_v10_p6_yorbit.py)的事实：

- `collect_y_orbit_entities(..., transform_bank=None)`默认逐实体保存矩阵；`build_task40_v10_p6_reference_inverse`对global和两个local的调用均未传bank。
- `cell_builder`对每cell建立882×882暂存、调用实际`Tt_apply`，取450×450内部块并`np.linalg.inv(...).astype(complex128)`；其450×450结果逐cell常驻。
- `YOrbitEntities.transform`又可在`_inverses[(orbit,base)]`逐实体创建第二份逆；是否在历史停止点全部发生未知，不能把未来逆库存冒充历史实测。
- 主线包含可选bank接口，但`src/solvers/y_orbit_transform_bank.py`在审阅主线ref不存在（读取404）；dot该模块存在，`bind_space`目前明确只允许degree4。**不能只打开一个布尔开关或删除degree检查后宣称p6已资格。**
- 上述yorbit文件在Gx560实际source9977284c和当前HEAD的Git blob相同：`aca109afa859b8515e2be01bbbe8c70f14749c57`。

对Gx560，global560+local280+local280=1120份，仅内部变换原矩阵形状载荷为：

```math
M_{\mathrm{T,old}}=1120\times450^2\times16
=3,628,800,000\ \mathrm{B}.
```

若所有实体lazy inverse都另建同尺寸，最多还增加这一量级。当前源码足以推导分配方式与矩阵载荷；它尚未构成历史10.295 GB RSS逐对象分账。**不能承诺恰好减少3.6288 GB RSS，也不把剩余未知强行归给Python。**

旧投影超cap为1,743,658,304 B。3.6288 GB的冗余载荷量级大于这个缺口，因而值得首先实施。仅作情景演算，完全去掉旧内部变换载荷而暂不计新模板与其他变化，投影为11,577,144,640 B；这不是下一次准入依据或内存预测上界。

### 3.2 必须实际实施的一项改造

选择性移交dot的[run-local transform bank](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/src/solvers/y_orbit_transform_bank.py)及必要小依赖，记录原blob/hash、p4资格范围和p6适配差异。进入主线src，不整体merge dot，不依赖其外部scratch路径。

一个run拥有一个bank，global及两个sector共同借用，matrix和inverse分别按真实身份共享。优先关闭450×450内部块的逐cell重复；边/面保持原正确路径，或经同样验证后共享。不能为了接一个缓存而新增一套求解器/runner。

Key必须包含实际Basix/element布局、dtype、通道顺序、变换语义、cell_info或edge/face方向状态。**内部cell_builder只依赖基函数与方向，而不是材料或单元尺寸；可复用的是这项坐标变换，不是不同几何/材料的Vii或Schur。**边/面若包含额外metric依赖，必须将实际依赖加入key或回退，不能靠舍入使之相同。

同一个key的不同实际实例需经原构造器验证其完整矩阵相等；碰到不相等，应细化正确key/保留不同owner，不强制覆盖。内容去重仅允许完整字节一致且语义兼容，不能按范数阈值合并。各实体行号、坐标和MPC真实见证独立保存。

保留完整450通道和矩阵语义，不假定所有变换为单位阵、酉阵或signed permutation；`inverse`、转置、共轭转置不可互换。可以缓存每个模板真正需要的逆及共轭派生对象，但不得每cell再复制它们。模板必须只读，消费者不原位修改；lifetime以单run为限，不跨ABI/源码/物理run复用未知可变对象。

目标复杂度从`O(N_entity*d²)`模板载荷和逐cell求逆准备，降到`O(N_state*d²)+O(N_entity*d)`索引；实际unique state数量必须测量，不能沿用dot p4的4个模板数。在线局部作用的全部成本仍计入，不预先保证加速比例。

### 3.3 有界验证，不把测试本身做成新的内存峰值

先用B0或独立小型真实p6空间检查所有实际出现的状态；Gx560的不同geometry/orientation类型只补缺失见证。legacy矩阵逐类生成、比较后释放；**正式大场禁止同时驻留两套完整legacy和新bank当oracle。**dot p4那次RSS增加来自资格对象重叠，不能照搬到本次性能场。

必须覆盖：完整矩阵/逆内容、native独立/slave行、全部内部和trace行、六种primal/dual/functional方向及多列输入、伴随功恒等式、四q相位输运、非零内部/端口RHS、mutability与cleanup。纯坐标恒等式沿原1e-12；局部action/recovery沿原1e-11；原参考方程与q残差沿1e-10。

正式迁移前至少给一份小型无全局factor的前后对照，记录builder次数、unique keys/backing bytes、逻辑借用字节、matrix/inverse已物化状态与时间。无需新做巨大全局映射矩阵，也不要求p6全部FE基向量逐列重放。代表模板的完整列及全向量方向见证足够检验本项存储改造，完整求解在第6节继续检验。

## 4. 第二优先：有所有权证据的生命周期改造，不是重写内存系统

完成bank后，对正常构建加少量阶段快照：target基础空间/端口、target凝聚、global reference entities、sector0/1、全部symbolic前后、各numeric前后、KSP入口、输出/释放。每个阶段只统计已知owner对象，不扫描全Python堆、不遍历全进程页表；PSS继续关闭。

以实际底层buffer去重，区分logical alias、unique ndarray/bytes、PETSc矩阵、MUMPS内部统计、进程RSS和未知native workspace。`source_matrices`与`csr_matrices`可能是同一对象，不能看到两个dict就当两份数值；PETSc CSR转换临时copy与真正live Mat也要分开。

允许紧接bank实施下列有证据的最小调整，不强求全部同时做：

1. 推迟不参与reference构建的target fast workspace等，或先释放仅供验证的临时对象，减少symbolic/numeric与准备对象重叠。必须同时检查KSP阶段是否会重新出现更大峰，不能只挪过准入门。
2. 原始局部张量、共享Schur/恢复缓存、q投影临时稀疏矩阵若已无消费者，在完成必要hash和独立作用见证后释放；保留用于实际apply/recovery的最小数据。不能释放MUMPS仍借用的CSR buffer或核验所需operator。
3. 两个reference sector的物理局部缓存只有在原精确几何、材料、积分、方向及原矩阵逐项一致时才可共享；Floquet约束、port、trace映射各自保留。此项为条件优化，不是bank的必需扩展，不再引入几何rounding。

**本轮不允许通过逐q删除/丢弃分支、±q假复用、重启时只加载q0、磁盘factor或重复每步分解来绕开全部因子共存合同。**这些改变时间/算法合同，当前先不做。若bank及明确生命周期处理后仍不安全，只停止受影响大场，并保留具体尚缺字节与对象；继续独立的已授权小场、映射和资源分析。

## 5. 内存准入保守但不能混口径；新记录不能再丢失关键数据

保留当前16 GiB硬上限与实时系统/cgroup允许值取小的策略；下次启动重新取得真实包络，不照抄13.462 GB或把停时3.167 GB当总cap。准入应分别检查：

```math
R_{\mathrm{live}}+\Delta M_{\mathrm{peak}}+M_{\mathrm{reserve}}\le C_{\mathrm{total}},
\qquad
\Delta M_{\mathrm{peak}}+M_{\mathrm{reserve}}\le H_{\mathrm{physical/cgroup}}.
```

其中live RSS已含实际存在对象；增量包含未产生的全部q numeric、未物化的共享inverse/检查工作区、外层向量、恢复与输出可能重叠的workspace。旧代码只列向量和128 MiB时，不可假定它覆盖未来全部逐cell逆；共享之后也须按实际key数保留未来模板预算。配套阶段表以同时存活为准，不把互斥阶段全部相加。

本轮初次Gx560重放继续采用当前四q INFOG16/17之和的保守numeric增量，不凭猜测扣掉已符号化的部分，也不把估计当严格峰上界。数值阶段仍由live watchdog保护。只有来源明确的重复**账项**可以纠正，不能降低安全系数、缩小观测树或假设未被实际释放的内存已可用。

当前代码有workspace fallback又单独相加的通用接口，若修改，应逐调用声明参数代表新增持有量还是临时量并加无FE测试；不要借笼统“重复计费”抹去真实workspace。增量/总cap、double-reserve、已分配/未来分配分别测试；不另造第三套watchdog或时钟框架。

每q symbolic完成立即持久化：actual rows、stored NNZ、source/input matrix hash、symbolic seconds、原INFOG及解码；即便随后停止也应有数据。numeric完成记录allocated/used、factor entries、验证残差和阶段RSS；销毁前保存独立快照，不从销毁后的0填表。沿当前合格MUMPS配置和统计API，不改变ordering、pivot、BLR、OOC、线程或ABI。

## 6. 本轮数值交付：完整通过，不再只停在构建或bank测试

### R0–R6执行顺序

| 阶段 | 必须做什么 | 接续条件 |
|---|---|---|
| R0 | 只读绑定V11原件/停止点/当前源码；核实旧服务已结束；修正资源字段标签 | 不重算B0 gauge、q60、S2或S5，不因历史unknown无限停留 |
| R1 | 迁入并资格化p6 run-local变换共享，完成小型真实p6映射对照 | 旧新完整变换正确，实际共享owner，无逐cell逆副本 |
| R2 | 完成少量ownership/lifecycle与准入接线修复；冻结V12 profile、dat与source | 实际入口测试通过，不仅修改profile名称 |
| R3 | 一场B0相同80cells/φ5/532/原两cell缺口fresh p6参考逆回归 | 所有四q、原残差、恢复、gauge功率及保存场对照通过后直接继续 |
| R4 | Gx560相同560cells/φ0/340/原解析缺口；全部numeric→KSP→输出→同离散比较 | 本轮主要里程碑。bank资格不是停止点，symbolic通过不是终点 |
| R5 | Gx560通过且全生命周期准入安全，完成Gx784同物理340模式 | 不以历史三步/126步或预计时间人工停止 |
| R6 | 形成真正覆盖setup/所有q/迭代/恢复的成本与目标路线判断，给下一任务冻结移交包 | 只提下一主候选，不自动启动原尺寸或工作站 |

R3的fresh回归是存储/映射核心迁移后的必要anchor，不重新跑旧失败p4控制；与V10求解及V11物理复核的保存场比较。无需再为了B0构造另一个全域direct。若完整映射和数值依赖已有同源fresh资格，明确指出可复用项，不重演未变化的全套W0/Library导出。

R4/R5严格保留实际target，不改变材料、缺口大小、几何、入射和模式来通过内存门。参考问题填回缺口只发生在PC。Gx560内部252000行，Gx784内部352800行；完整行数、各q维数以运行真实对象核验。统一MPI1/数学线程1、complex128、FGMRES32/max2048、零初值。p6 reference逆不要求H6；不得把旧p4 BAL_H/H6次数当这条新PC的执行合同。

全部正式PDE仍经`python scripts/run_case.py <本轮独立dat>`、user-service及独立watchdog；新dat须先创建、验证并提交，不在文档假装新路径已存在。现有runner/profile可做最小参数化，禁止复制又一份数千行worker或恢复框架。主控冻结source后，执行者在同一已有窗口连续运行，不能停在“等待主审候选选择”。

### 数值和物理门

- 最终与释放后独立原A6≤1e-6；native/凝聚identity≤1e-10，端口≤1e-8；finite检查完整。
- regular参考逆原方程/q残差≤1e-10；完整内部恢复及原局部action沿1e-11；不裁任何q、mode或微小内部耦合。
- 在线使用已修复的gauge-aware输出。能量和A_balance/A_volume绝对闭合≤1e-5；E/H/curl、全部532或340模式和科学场必须实际保存，可视化可选。
- B0对旧同离散场、Gx560/Gx784分别对已有准确p4同网格场：完整FE总/散射E/H与独立curl相对差≤1e-4；功率绝对差≤1e-5。模式整体复向量和原冻结显著集合分别比较，近零模式另报绝对误差，不拟合相位、不重挑模式。
- 旧p4参考是global-z时，按明确gauge和物理参考面转换后比较，不把裸alpha数组直接相减。缺原始参考时说明范围；缺少匹配reference不阻断已独立通过原A6/物理门的条件规模试验，但不能称matched-reference pass。
- 保留原h/模式/目标尺寸精度限制。三步或能量闭合均不代表连续场准确，也不保证任意强缺口少步。

### 资源失败后的有限替代路径

如果R4在已应用bank和明确生命周期修复后仍资源不足，**不重复相同失败，不抬cap，也不把整个campaign就地结束**：完成R3正式成本、R4已得结构/符号/owner证据和R6；若尚有窗口，可在已有的G0 336cells或Gx560的冻结中间参考身份中选至多一个已有同离散场且容量合格的p6工程点，必须另run_id和明确scope，并保持其原物理/模式。这个中间点仅是规模阶梯，不冒充Gx560达成。不得为此重新扫描一批任意网格或缩小缺口。

## 7. 原尺寸2 TB/48小时：本轮必须提供可执行的判断，而不是线性乐观外推

本次共享针对的是坐标变换，与先前几何舍入错误、84行端口压缩、单元Vii的物理因子不是一回事。它不依赖目标材料沿y可分离；参考逆本身仍利用规则参考的重复结构，而target保留完整三维。

对既有15232cells计数候选，如果仍按2N份450×450 complex128保存内部坐标变换，仅原矩阵形状载荷为98,703,360,000 B；lazy逆完全另存时可再增加同量级。**这是实现增长模型，不是原尺寸实测RSS、也不是准确网格推荐。**共享能消除这类不必要的N倍大模板库存，但不会自动消除物理局部缓存和所有q稀疏factor的增长。

R6必须同时回答：

| 问题 | 实际交付 |
|---|---|
| 有没有真正省内存？ | logical借用、unique owner、各阶段tree/cgroup峰与完整运行峰分别列；说明旧新是否并存、allocator是否归还，不将derived节省写measured |
| 有没有加速？ | 变换构建次数/耗时、symbolic/numeric、纯KSP、全workflow；不把B0的4.9s当完整速度基线，不拿失败p4的2048步作加速分母 |
| 现在的真正大对象是谁？ | 全部numeric q factors同时驻留、物理局部LU/Schur、carrier、trace/maps、Krylov、JIT/输出各自最大贡献和创建释放边界 |
| 原尺寸48h是否有可信路线？ | cold/复用JIT分开，预测setup和q factor需要实际多规模校准；未知总fill/精度不填0。至少列乐观/保守条件，不只按单元数乘时间 |
| 后续应改哪里？ | 若map已小而q factors主导，下一步是有界局部/递归或可扩展q求解，不继续“共享另一个小dict”；若求解步数对真实缺口恶化，研究全局纠错能力；若端口主导，才扩展全边界matrix-free动作 |

不得将两个代表面32,060-mode动作通过当作完整原尺寸AUTO算子；也不要求本轮重做那两个面。dot分支仍只读复用，独占云端的新任务/提交由其owner另行确认；主控与执行者不SSH到dot或工作站，不跨分支修复。

输出一个供其他任务读取的`v12_transfer_and_target_readiness.md`：列推荐启用的gauge/shared-transform/local-recovery/port模块、完整source与必要依赖、哪些仅research、三类真实input、必需ABI/int宽度、原尺寸仍未资格项。原尺寸全局factor、工作站实际运行、master合并都不在本授权中。

## 8. 新研究窗口、自修复及停止规则

本报告明确新增一次统一86,400 s的V12研究窗口。先核实V11所有数值服务已经终态、无后代；无需等待旧UTC截止才开展本轮。旧窗口剩余额度不挪用，旧费用按真实记录结算；历史unknown保留但不要求先重建旧三钟才允许新数值工作。第一项执行准备前记录本轮唯一T0、UTC/monotonic/boottime、boot ID和deadline。全部实现、修复、测试、编译、计算、保存、checker、主控提交收口同账，末600 s用于保存清场，不在其中追加计算。

沿用现成保守时钟和单一写账者，不新建clock-only研究、不恢复旧3600s归因子限额。旧review的attempt次数不绑定本轮。允许不同明确工程问题自行最小修复、定向回归，经主控提交clean source后继续；不要求每个bug再等ChatGPT批准。相同根因两次修复无效，转有判别力的小验证而非原样第三次heavy；继续不依赖该故障的工作。

资源仍取16 GiB与真实物理/cgroup/系统余量较小者；至少128 MiB证据/终止reserve；task/cgroup swap=0；快速RSS覆盖全部worker、编译器、checker和后代，PSS关闭时null。主机已有换出计数和本次增量分开，不把宿主不可见写成全机零swap。不能通过关采样、裁进程树、reset peak或杀别的任务腾内存。一次一个heavy，不热改活跃worker源码。

正常正式场最多：B0回归1场、Gx560 1场、条件Gx784 1场；只有R4仍受资源限制时，条件中间阶梯至多1场。明确修复后的重放单独登记，不受“一次replay就停”的旧规则限制，但全部计入同一窗口。性能不佳、真正数值不收敛或资源不足不是bug重放许可；不得降阶、删模式/q、改材料、抬阈值或缩缺口凑PASS。

output/checker/目录/序列化失败优先只重读合格保存数据；不能因此再建立全部因子。数值kernel、矩阵或RHS确实改变时才重跑相应anchor。普通文档或hash字段修正不触发FE。新代码必须保持科学输出与可选绘图区分。

## 9. 提交和交付：将结果留给下一轮，而不是再留一堆unknown

主控负责及时审查、冻结和提交/推送；执行者不执行Git写操作。建议最小提交组：C0已有证据与本轮profile；C1共享变换及定向测试；C2有依据的生命周期/准入/阶段快照；C3实际dat与必要集成；C4完整结果和交接。各次正式run绑定真实当时source、input、physical/model/mode/ABI与artifact哈希，收口HEAD不冒充全部run source。

建议轻量证据集中为：

```text
response_v12.md
outcomes/review_v12_shared_transform_engineering.md
outcomes/v12_transfer_and_target_readiness.md
outcomes/records/review_v12_transform_bank.json
outcomes/records/review_v12_memory_lifecycle.json
outcomes/records/review_v12_formal_results.json
outcomes/records/review_v12_cost_and_repairs.json
outcomes/records/review_v12_manifest.json
```

同步summary、run index、test summary、development_progress及model registry。原始场、矩阵、因子、JIT和大型时间线留ignored；只保存一次必要原件，checker流式消费，不为证明持久性反复拷贝大包。GitHub Markdown独立公式用math围栏，表格列数一致。渲染或工具不可访问如实记录，不能伪写通过。

**本轮期望的实质结果是：p6真正不再逐cell保留完整变换与逆，获得可复核的省内存/准备成本证据，并让Gx560完成numeric、KSP与物理输出；条件允许再完成Gx784。**若最终仍未安全完成大场，至少应有正确的B0新anchor、真实对象分账、未完成阶段的精确瓶颈和下一唯一架构决策；不能只交“已加计时器/又通过若干测试/等待主审”。

## 10. 关键源码和外部核对入口

- [V11回应](response_v11.md)、[V11工程compact](outcomes/records/review_v11_engineering_results.json)、[V11综合报告](outcomes/review_v11_engineering.md)。
- [p6实体与reference builder](../../src/solvers/task40_v10_p6_yorbit.py)：`collect_y_orbit_entities`、`cell_builder`、`YOrbitEntities.transform`、global/local调用与所有权。
- [p6主worker](../../src/runners/task40_v10_worker.py)：target先构建、allocation_gate、全部q准入和输出。
- [MUMPS包装](../../src/solvers/task40_v10_p6_mumps.py)：全部symbolic、future vector预算、numeric后才填完整audit的现有行为。
- [dot bank源码（冻结）](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/src/solvers/y_orbit_transform_bank.py)；[dot p4资格](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/response_v12.md)。
- [Basix 0.10有限元API](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.finite_element.html)：DOF变换、inverse-transpose、实体方向与系数，不要求升级ABI。
- [PETSc MatMumpsGetInfog](https://petsc.org/release/manualpages/Mat/MatMumpsGetInfog/)、[MatGetInfo](https://petsc.org/release/manualpages/Mat/MatGetInfo/)：分别是后端统计与矩阵信息，不能将它们混称进程RSS。

审阅端只实际核对远端代码和文本证据并重算上述字节公式；主线bank缺失、dot p4限制和调用未接线是源码事实，3.6288 GB/98.70336 GB为载荷推导。没有新的FE、数值独立checker、内存采样或工作站运行；不保证共享后一定在下一场实测中减少同样RSS，更不授予原尺寸2TB/48h通过。
