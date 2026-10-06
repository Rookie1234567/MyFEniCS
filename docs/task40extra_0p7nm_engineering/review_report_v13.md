# Review V13：完成工程网格求解——完整参考残差修正、受控不精确PC与有界q块装配

## 0. 决策、最终目标与执行身份

**本轮要消除的blocker：共享p6实体变换已经让Gx560完成全部四q的数值因子，当前不再卡在内存准入；但参考逆在一个generic RHS上的2e-10级精度未达严格参考资格，导致真实三维target的FGMRES完全没有启动。本轮先实施一次完整增广参考残差修正，同时明确区分“准确参考逆资格”和“可用于FGMRES的不精确PC资格”，不再让前者的小幅超限永久阻断后者。必须继续取得Gx560真实解和条件Gx784结果，并实际尝试减少q块装配的全局CSR重复相加。**

最终目标仍是：真空波长0.7 nm、原尺寸50×25×140 nm；首先推进规则Si线光栅工程解，同时保留并验证非可分三维缺口。完整三维Maxwell、complex128、Nédélec H(curl)、双Floquet、Fourier-DtN；整机物理内存不超过2,000,000,000,000 B、无swap；必要冷编译、构建、全部因子、迭代、恢复、输出与独立检查端到端不超过172,800 s。**当前没有原尺寸资格，既不能宣称已通过，也不能称为数学上不可能。**

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task40extra_0p7nm_engineering
review_base_SHA        = a5d3ee6fa767d9dea4ee50a792a570994f9cad16
last_run_source_SHA    = 6d2c54389fe885ecf24d474a8782166ff31f9154
latest_response        = response_v12.md
readonly_dot_SHA       = 15713d3e09b63f65511c7b7f61fa043fdb23dca5
review_file            = docs/task40extra_0p7nm_engineering/review_report_v13.md
response_required      = response_v13.md
campaign               = task40extra_v13_refined_reference_engineering
canonical_worktree     = /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
execution              = existing local_wsl2_authorized; MPI1; math threads1
roles                  = 执行者实现/测试/运行；主控审查/冻结源码/commit/push
ordinary_default       = UNCHANGED
workstation/dot/master = 不运行、不写入、不合并
```

先读根/目录AGENTS、仓库工作原则、task、V12、Response V12和summary。目录中的“当前V10”等旧导航不阻止V13。本报告新增独立研究授权，明确取代旧review中本轮的参考逆精度准入、续作次数和阶段依赖规定；不改真实target方程、最终精度和资源安全。历史失败、已结束窗口和费用全部保留，不追认V12通过。保留既有客户端、环境和worktree，不新建聊天、subagent、checkout或定时自动化。

## 1. 最新结果与审阅结论

下表均为已发布证据；审阅端没有重放ignored数组、运行FE或实测新RSS。主线最后提交为2026-10-06 16:11:42 UTC，即UTC+8的2026-10-07 00:11:42。

| 对象 | 已发布数值 | 本轮裁决 |
|---|---|---|
| B0 fresh p6参考逆 | 80cells、532模式、四q、真实两cell缺口；A6=1.6089774391665316e-8；workflow1068.533 s、KSP4.583 s；tree RSS2,796,560,384 B | 求解通过，原worker输出门exit4保留；不能把离线修复写成原worker成功 |
| B0保存场复核 | 532模式计数修正后，FE系数/MPC与V10/V11字节一致；R=0.9842736080926772，T=0.014240518143988908；A_volume=0.00148587384621333；能量误差8.287925901129256e-11 | 接受保存场物理复核；无需再重做相位归因，E/H/curl零差是代数推论而非新增积分 |
| Gx560四q因子 | 全部numeric和探针通过；allocated/used保守解码合计4.645/4.080 GB；同时live快照tree RSS10.022 GB | 内存准入障碍已跨过；统计不是独占RSS，也不含尚未运行的KSP |
| Gx560全流程前缀 | workflow2089.322796 s；tree峰10,181,664,768 B；task/cgroup swap0 | 不是完整求解时间；本次不是资源/time停止 |
| 完整原参考方程 | 2.0058682739535859e-10，原限1e-10 | strict参考资格失败，保留；不能改写为target不收敛 |
| 两局部原方程合并 | 1.4183642641040464e-10，原限1e-10；twist0=2.8394442214050333e-10，twist1=9.563779087957973e-12 | 需同时检查分扇区与合并值，不用合并掩盖单扇区 |
| global alpha closure | 1.1770163447864681e-11，原限1e-11 | 小幅超限仍是原合同负结果，不预先认定为正常舍入 |
| 支持性证据 | q见证最大1.37345e-11；native扇区作用差2.34433e-12；内部恢复8.84513e-17；端口方程5.04393e-13；native identity7.12161e-12 | 对应门通过，但不能替代失败项；支持开展有界修正而非推倒方法 |
| p6共享bank | 1120次matrix请求、6次builder、1个3,240,000 B backing；命名视图与owner差3,628,800,000 B | 确认重复存储已消除；不是同等RSS下降的实测结论 |
| Gx784 | 输入已冻结，14×4×14、784cells、340模式；未运行 | 本轮在Gx560合格且资源安全后继续 |
| dot | HEAD仍为15713d3e，无新远端发布；p4共享及完整882行选定边界结果已被主线部分吸收 | 只读复用，不重复已完成实验；84行压缩仍未资格化 |

证据：[Response V12](response_v12.md)、[summary](outcomes/summary.md)、[formal results](outcomes/records/review_v12_formal_results.json)、[memory lifecycle](outcomes/records/review_v12_memory_lifecycle.json)、[readiness](outcomes/v12_transfer_and_target_readiness.md)。dot对应[共享存储](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/response_v12.md)与[完整行边界](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/outcomes/paired_boundary_support_pilot_v1_zh.md)。

### 1.1 这轮不能再误判的两点

四q symbolic合计约0.992421 s，numeric合计18.096982 s；输入矩阵已经存在后的MUMPS构造器约29.169 s。**它们都不是34.8分钟的整个setup。**本例没有依据继续把主要准备耗时归因于MUMPS；剩余准备与验证成本必须实测细分。

旧V12 generic检查失败后立即抛异常，四份已经建立的因子被清理。旧内存因子无法从NPZ恢复，下一场仍需建立一次；但本轮新代码应在同一次合法进程内完成原见证、必要修正和target求解，不能先停审再重建。

## 2. 唯一求解主线：有限完整参考残差修正

### 2.1 数学对象和代价

参考逆处理的是填回缺口的规则背景；最终FGMRES处理的是真实三维缺口target。二者必须分开。令完整参考增广系统为：

```math
\mathcal A_r
\begin{bmatrix}u\\\alpha\end{bmatrix}
=
\begin{bmatrix}V_r&B\\-D&H_p\end{bmatrix}
\begin{bmatrix}u\\\alpha\end{bmatrix}
=
\begin{bmatrix}f\\g\end{bmatrix}=b_r.
```

H_p是原端口块，不是H6平滑器，也不是凝聚后Hhat。保持原符号、boundary-plane坐标、复相位、全部q与模式；不假定D=B^H。

初次用现有完整四q参考逆M_r取得z0=(u0,alpha0)。若原strict目标未满足，至多再做一次：

```math
e=b_r-\mathcal A_rz_0,\qquad
\delta z=M_re,\qquad z_1=z_0+\delta z.
```

额外修正每次逻辑参考逆调用至多增加四次q MatSolve，不重分解、不调用递归修正、不再开内层Krylov。MUMPS排序/主元/BLR/OOC/ICNTL/线程保持不变。修正同时更新全部FE和alpha，不仅修u、不用投影后alpha覆盖计算出的alpha掩盖误差。所有local/port见证从累计后的同一状态重建。

精确代数下e1=(I-A_r M_r)e，所以可能改善，但没有一次必达标的保证。原参考算子作用用独立native体积与原carrier；不能用同一q矩阵、同一恢复映射形成的自洽残差冒充独立原方程。可在有限分块内使用补偿求和；若使用longdouble/clongdouble，必须读回实际mantissa精度并说明作用范围，不宣称全程变为高精度。

### 2.2 准入分成两种，最终target门绝不改变

先争取原strict全部通过，保留名称`STRICT_REFERENCE_PASS`。**本报告另显式授权`BOUNDED_INEXACT_REFERENCE_PC`：仅作为FGMRES的预条件器使用，不冒充准确参考解。**这是新的PC精度合同，不是追认旧失败或偷偷改原1e-10。

PETSc的FGMRES允许非线性/变化的右预条件器，预条件器内部不必达到最终方程的求解精度；但这不保证任意不精确PC都有效。本轮以实际target求解、独立残差及同离散场对照裁决。[官方KSPFGMRES说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)。

| 指标 | strict参考目标 | 新inexact研究准入上界 |
|---|---:|---:|
| 完整原参考方程相对残差 | 原定义1e-10 | 1e-8 |
| 局部原参考方程 | 合并原限1e-10；分扇区原样记录 | 每个扇区及合并均<=1e-8 |
| global alpha相对闭合 | 原定义1e-11 | 1e-9 |
| 每q实际求解相对残差 | 1e-10 | 每q、每次实际调用均<=1e-8 |
| 非数值精度类：覆盖、native/sector作用、映射、伴随、内部恢复与representation identity | 原合同 | **不放宽** |

所有旧strict bool、原始残差、分母、绝对误差继续保存。原metric的定义不变；另保存初次状态的分母，在同一输入下用于修正前后冻结尺度比较，不能放大分母制造改善。新上界必须同时通过原定义和冻结尺度检查。零RHS应返回精确零状态；近零项保留绝对误差，不新增floor吞掉缺陷。

只有以下条件全部具备，才可进入inexact路径：实际算子/材料/积分/相位/所有q和mode身份完整；native/sector作用及映射原门通过；因子有限且没有奇异/错误状态；初次或一次修正后的完整状态在表中所有上界内；没有已知未修的算子、约束或端口符号错误。按所有归一化指标的最大超限比选择同一完整状态，不拼接各自最小的u、alpha或残差。若初次strict已过则不修；若未过strict则执行至多一次修正，再选择合格状态。

新界限只是预登记的工程准入，不是场误差界，也不能因为1e-8小于1e-6就宣称最终误差必小。上线后的每次PC调用都应核验独立完整参考方程和端口闭合、记录四q残差；完整local四类startup见证不需每步重做。检查成本计入PC，不隐去。每次调用最多一次修正；无全局超限次数硬停止线，但超过新上界或出现结构错误必须保存真实原因并停止受影响solve。

最终target保持：原A6及释放后<=1e-6；target内部恢复/native identity/Schur-port identity原1e-10门；端口原1e-8门；能量和吸收一致性<=1e-5；所有模式完整输出。**小幅参考求解残差可允许外层纠正，但target凝聚与原A6不一致、错误的q/模式映射不能按inexact放行。**

### 2.3 必须贯穿调用链，不能只删一个raise

在`src/solvers/`增加或提取可复用的增广残差/一次修正/状态选择实现；现有worker只编排。保留未修正raw inverse接口，使修正调用不会再次递归修正。startup、每q求解、PC adapter、动态checker、最终parent判定统一读取同一显式策略。数值核心不得藏进benchmark或再复制一个巨型task worker。

四类已规定RHS（generic、全部内部、完整port RHS、物理regular RHS）都核验；在第一类strict未过而inexact已通过时不能提前退出，继续其余见证。每次修正的输入hash、真实额外MatSolve次数、时间、scratch、前后全部指标保存。手工改bool、仅返回初次结果却标“refined”、异常捕获后一概放行，均不允许。

## 3. 唯一setup加速候选：避免逐贡献重建整张q稀疏矩阵

### 3.1 源码证据与边界

当前`assemble_task40_v10_sector_blocks`对每项局部贡献，在四个(p,q)组合中反复执行：

```python
blocks[p, q] = (blocks[p, q] + term).tocsr()
```

见[src/solvers/task40_v10_p6_yorbit.py](../../src/solvers/task40_v10_p6_yorbit.py)。这会反复遍历、分配逐渐增大的全局CSR对象。源码证明存在重复组织，**尚未证明它独占34.8分钟或给出可预期加速倍数**。本轮必须给现有贡献生成/局部投影/全局累计各一个时间区间，不用未归因差额命名热点。

### 3.2 实际实施而非只加计时

优先：由真实结构支持建立稀疏pattern，分配一次值数组，按固定局部顺序累加；或采用严格有界的row-tile累加并只在终态规范化。选择一种，不扫描很多tile。结构遍历不能另做一次昂贵局部数值求解；元数据和数值贡献分离时保留原物理定义。

不得无限保留全部COO三元组、创建全域dense矩阵、删浮点小项或只组装对角q块。原两个off-diagonal q块的最终抵消/范数门仍必须独立计算：只能在全局贡献相加后判定，不能逐单元假定它们为零。保留全部B/D、Hhat内部修正和复数非Hermitian左右映射。

用B0真实贡献做旧/新四块对照，记录完整CSR数值/action/off-diagonal差、工作区和时间；两套oracle分阶段释放，不在Gx大场长期并存。旧/新完整作用与局部投影原1e-11门不降。支持pattern可为保守超集，但绝不能以阈值删去原非零项。累加顺序变化带来的hash差异必须绑定新源和新数值身份，不能要求不同算法必然byte-equal，也不能拿hash不同代替数值比较。

候选只有完整构建更快且内存安全才进入正式组合；没有收益就保留旧装配，继续第4节，不阻断主求解。不要为证明该候选额外建立Gx560工程因子。

## 4. 连续执行：本轮的主要交付是完整Gx560

| 阶段 | 必须完成的工作 | 续作规则 |
|---|---|---|
| P0 冻结 | 核对旧进程已结束、源/ABI/输入/保存场；读取V12失败NPZ及其hash；整理first-failure路径 | 不重做相位归因、AUTO库存、全W0或共享bank全套证明 |
| P1 实现与定向验证 | 增广修正与两类PC资格；带非零内部/port RHS的复数测试，四q覆盖；测试轻微strict超限继续与真正损坏拒绝 | 用真实小型p6作用复核符号/尺度；不额外全局factor，不先要求病态性完整理论证明 |
| P2 装配候选 | 实施一项有界q块装配，旧/新真实B0贡献短配对 | 失败仅回退该优化；完成唯一组合的源码冻结 |
| P3 B0 fresh anchor | 原80cells/phi5/manual532真实缺口、全p6；新PC与选定装配；完成在线终检、模式与输出 | 原保存场作对照；不跑旧失败p4控制，不只修输出后停审 |
| P4 Gx560 | 原10×4×14/p6/phi0/manual340、真实解析缺口；252000内部；四q全部numeric并存，startup修正与target FGMRES在同进程完成 | strict或符合第2节的inexact资格都可直接进入target；不等新review，不重建同一套因子 |
| P5 Gx784 条件阶梯 | Gx560通过、预算与真实资源安全后，原14×4×14/p6/manual340、352800内部 | 相同策略；容量不足保留具体限制，不降阶、删q或缩缺口 |
| P6 工程交付 | 完整场/功率/同离散比较、分阶段时间内存、2TB/48h差距及下一准入包 | 不以组件通过/输入冻结/测试数量替代正式结果 |

正常最多三场fresh PDE：B0、Gx560、条件Gx784。对应新dat使用原模型物理，只改run_id、显式PC策略和被选中的装配选项；建议路径为`b0_p6_reference_v13.dat`、`nonseparable_gx560_p6_reference_v13.dat`、`nonseparable_gx784_p6_reference_v13.dat`，位于本任务input目录。它们是待实现输入，不是假称当前CLI已存在。统一经`python scripts/run_case.py ...dat`、既有user-service与独立watchdog。

代码改变后需匹配的B0fresh资格，但不再为每个子修复完整重跑B0。同一合格物理场的输出/文件格式错误只离线修复。若旧raw本地缺失，采用现有生产构建生成本轮必需状态；单纯历史数组缺失不编造PASS，也不成为新solve永久前置条件。旧因子已销毁，不能假装从保存向量恢复了MUMPS对象。

### 4.1 数值与物理验收

零初值、right FGMRES32/max2048，MPI1/数学线程1不变。原A6每8步、每32步场/解检查点、终态与释放后检查保持。startup参考逆的1e-10不再被混作target停止线；target未达到精度仍继续到原上限或真实安全停止。

B0与原保存field同离散比较：相同MPC、坐标、相位和规范化；系数一致可报告代数等价，不能称新增体积分。若不byte-equal，执行已有FE L2/scaled-curl/模式完整比较，沿原同离散门限。

Gx560/Gx784分别对已有同网格准确p4保存场比较总/散射E/H及scaled-curl、显著复模式、全部模式功率；沿V11的同离散目标（场/显著复模式<=1%，功率绝对差<=1e-3，且本场能量<=1e-5），近零量报告入射归一化绝对差，不拟合全局相位。已存在的更严格专用对照门不应静默弱化。旧参考为global-z时先按已资格化gauge转换核对，不把错误相位比较当新solver缺陷。

原方程通过但场对照或能量失败，应保存完整场、定位输出/离散原因；不直接换PC。任何合格结果仅授予该离散与该缺口；Gx560/784仍为缩小单胞，二者不是原尺寸通过。

## 5. 成本必须回答48小时问题，而不只说“迭代几步”

本例18.1 s的四q numeric和约2089 s的流程前缀说明，单看MUMPS不能解释总时间。以下计时随必要运行采集，不为补账重跑旧场：

| 三大阶段 | 必需独立分项 | 内存口径 |
|---|---|---|
| Setup | mesh/MPC/JIT、target局部凝聚、reference全域/两sector、局部tensor、q局部投影、全局累计、CSR/PETSc转换、symbolic/numeric、startup见证与修正 | named unique owner、临时buffer、每qINFOG、全部factor同时live以及整树/cgroup峰分别记录 |
| KSP | target action、完整PC、每q回代、完整参考残差与额外修正、局部恢复/映射、正交化与固定检查 | Krylov实际峰值向量数；factor常驻；同一array别名去重 |
| 后处理 | 释放前/后原A6、完整恢复、模式/功率、独立体吸收、场对照与文件输出 | 编译器/子进程包含在监控；科学输出与可选绘图分开 |

每q行数/NNZ/hash/INFOG及symbolic/numeric计时在产生时落盘，不在销毁后读0。分阶段父子计时不相加；修正不能标记为免费；编译与保存不能移到墙钟之外。修正策略可能每次增加成本，必须用总时间而非仅迭代数判断收益。

若装配优化未选中，仍交付实测分账。可复用同源JIT须标明warm；最终目标的48小时必须另计所需cold preparation。当前笔记本与工作站CPU/内存带宽不同，禁止用笔记本时间直接乘cells得到已资格化48小时承诺。

## 6. 通向原尺寸的下一阶梯，不再只停留在更小benchmark

本轮交付`v13_target_readiness.md`与机器可读`target_readiness_v13.json`：列出原尺寸候选15,232 cells/32,060 modes已知身份、尚未资格的网格精度、索引宽度、全边界MPC、全部q填充、总时间与峰值的缺口；复用现存mode manifest，不再次生成库存。

用B0/Gx560/条件Gx784实测分离三类增长：构建与重复数据、所有q因子、target纠错工作。网格细化序列不等于电尺寸序列。原尺寸272×4×14仍只是成本候选，特别是y/z解析能力未证明；不能只凭R+T+A闭合授予目标精度。

下一阶段只选择一个真正主导对象：若构建占主导，继承本轮有界q装配并测目标代表块；若全部q因子主导，设计q块的有界/递归求解，不能只靠共享模板；若真实缺口迭代恶化，设计补偿跨q误差的修正。任何选择都必须有本轮时间/内存/残差证据，不能再次列一串PC名字。

准备工作站可读的冻结输入/依赖/预检与逐级运行清单，但本轮不操作工作站、不运行原尺寸全域PDE或TB级factor。已有合法runner接口能覆盖的给真实命令，未实现的标缺项，不虚构one-command已可用。完整参考逆仍是结构利用型工程候选：target保留完整三维，不代表任意非可分结构都能少步；长期通用Full3D仍需分布式、matrix-free与可扩展的全局纠错。

## 7. 自修复、停止和预算：继续解决问题，而不是继续生成停止收据

新增一个统一24小时研究campaign，第一项新准备前记录唯一T0、UTC/monotonic/boottime/boot ID及固定deadline，收口预留600 s。旧V12终态与未结算项保留，不复用余额、不刷新旧窗口。全部准备、实现、修复、测试、运行、检查及提交同账；24小时研究预算与最终48小时单次目标不同。复用现有成熟监督，不再增设一小时诊断子窗口或为时钟标签重写平台。

资源沿当前本机16 GiB上限与实际动态准入取小，明确十进制GB/GiB、总cap和增量headroom；保持系统余量、任务零swap、完整进程树RSS/失联/清场，PSS未采记null。不可见Windows宿主状态保留限制。不得因为历史8 GiB、3步、126步或旧耗时中止；也不得因用户要求进展而绕过真实压力、NaN/Inf、错误映射、factor失败或target identity失败。

不同明确bug允许最小修复、定向测试、主控冻结新源后继续，不设旧“一次replay”机械额度。无修复不原样重复heavy；数值不收敛/资源不足不是bug。检查器、序列化、目录、计数、绘图等错误，应尽量修叶子并重读已保存科学数组；不得重新求解只为修一份JSON。只在身份及政策明确时允许有限程序化修复，不能读取/回显secret。

本轮预先授权的inexact分支已经解决“strict稍超限后是否再来请示”的问题；条件满足即继续，不重新等待主审。条件不满足时停止受影响升级，继续其他独立的setup实现、保存数据分析和readiness交付。主控冻结阶段源码不等于每阶段重新等待用户授权；执行者不自行Git写入。

## 8. Commit计划与交付

建议按三个源代码逻辑组提交：①完整增广修正、PC资格分层、逆调用/输出端到端接线与测试；②有界q装配候选及等价/时间/工作区证据；③冻结所选组合输入后正式运行与收口。实际bug可增加单独修复提交，不amend、不强推、不删除负结果。每场source必须clean且先提交，不能将最终文档HEAD冒充run source。

新增`response_v13.md`，更新summary/README最新入口、test_summary、run_index、docs/development_progress.md与docs/development_model_registry.md。紧凑记录至少覆盖`review_v13_reference_correction.json`、`review_v13_pc_admission.json`、`review_v13_q_assembly.json`、`review_v13_formal_results.json`、`review_v13_cost_and_repairs.json`、`target_readiness_v13.json`，可共用现有schema避免无意义新账本。每个关键结论有raw路径/hash/字段/单位，保持measured/derived/predicted/diagnostic/not_run/failed/controlled_stop区别。

必须明确回答：修正后strict是否达标？inexact是否实际触发？target是否独立通过？Gx560是否真正完成？Gx784做到了哪一步？装配提速和总成本分别多少？所有因子同时驻留峰值多少？离2TB/48h缺的是精度、构建、factor、端口还是迭代？

审阅通过条件是实质数值与可复核工程证据，不是测试数量。若最终仍不能完成，要给出已执行有界修正/真实target尝试的结果和明确技术原因，不只写“需新review授权”。本报告已授权本轮连续工作，但没有承诺任何候选必然收敛。

文档使用GitHub fenced math与一致表格；本review审阅端做文本结构检查，远端渲染访问失败须如实留限制，不能标成已视觉通过。数值与资源结果不由文档渲染问题改写。
