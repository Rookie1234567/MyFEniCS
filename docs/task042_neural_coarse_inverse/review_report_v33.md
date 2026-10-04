# Review V33：接受V35在线负结果，转入原尺寸输入与完整端口的可执行准备

## 0. 决定、目标与本轮边界

**V35的零初值在线负结果可信；关闭当前固定七／八块预条件器族的追加数值预算。下一轮V36完成一个连续工作包：原尺寸物理与离散容量合同 → 全部端口的有界存储接口及真实小模型作用配对 → 可交给全局求解器的输入、验收与资源包。普通bug在本轮修复，不因测试失败另开review；不再用另一个局部方向、restart周期或同p1空间换测试方式推进。**

最终目标仍是**原尺寸50×25 nm周期、z=−10..130 nm、λ=0.7 nm的完整三维有限元前向计算，完整时间≤172800 s，同时任务整树／可用专属cgroup峰值≤2,000,000,000,000 B，并保留非可分三维几何能力**。工作站自身和邻任务还需要独立余量，2TB不能解释为可立即独占的配额。神经网络必须在相同正确性下，相对最佳合格非神经路线的**完整N=1时间或同时峰至少改善20%**，另一项合规；包含数据、训练、构建、加载、推理、精确校正、审核、恢复与IO。当前这两项最终资格均未取得。

response_v35已回应review_v32，依AGENTS §15新建v33，下一交付response_v36。收到`execution-review-handoff-20261004-v35`后，审阅窗口接手；执行窗口已停止。审阅没有启动新数值、读取真实LU、重跑PDE或改求解源码，没有subagent、reset card、其他分支改动或merge。发布后通过同一会话队列交接，再停止仓库工作。

## 1. 独立核查覆盖与证据身份

| 项目 | 核实结果及限制 |
|---|---|
| 交付本地／远端HEAD | `9a6cadff62771d63a4996a6dccc9424df431ee4c`；非交互ls-remote一致，工作树clean，宿主进程检查无Task042 actor |
| 原执行分支／base | `task42_neural_coarse_inverse`／`ccd357885f7f9be84efe3be07868cc94f13d93fc`；canonical登记worktree为`/home/fenics/Projects/NN-Lab` |
| 实际数值source | `af0d3d3e7d2b05ab915902bbb66b6ddbd7ed912e`；最终checker为`6e17883a672d6166472bb80c27999afc46d4a059`，包装为`54e6437f36956da499ae46ea85df64745eed1b82`；不得用交付HEAD冒充运行source |
| 压缩后全仓恢复 | 对5509 tracked文件逐份hash，识别文本106578477 B并建标题／定义索引；任务书、全部35份response与32份review可检索。**这是全仓导航和增量审阅，不是全仓每行语义审计** |
| 本轮独立证据核验 | 205份带hash元数据／源码记录、157份原始gzip；13组监督资源及13份CPU准入从原始字段重算；5份JUnit逐例核对 |
| 历史保护 | 956份原任务文件逐字不变，含既有66份review/response；四份汇总保留原文完整后缀，16份旧closed文件hash一致；V35账本closed、无active、仅一条真实运行 |
| 源码与测试审阅 | 核查七区PC、旧／快作用、恢复、在线返回、checker、资源窗口与测试；本轮增量19份Python静态编译通过，未执行数值测试 |
| 审阅局限 | 未重新加载因子、执行A/SH或重算保存向量的数值范数；接受的是源码与hash绑定原始审核链，不声称本轮又做了一次独立PDE |

[独立核验记录](outcomes/records/review_v33_independent_checks.json)、[可复现元数据审计脚本](outcomes/records/review_v33_metadata_audit.py.gz)、[全仓索引无损包](outcomes/records/review_v33_repository_index.gz)保存覆盖与边界。索引原文SHA256=`c64295591db03a3602c329d9b7e650c36e05e238cd8f3dd277370987ee83f684`。本审阅使用Task042既有pure activation进行标准库检查，没有新增软件栈；元数据读取／写作耗时没有单独监督，标unknown，不能写成零费用。

## 2. V35已回答的数值问题

局部预条件器先在各小区内部解方程，再把邻区影响传回来。V34只测了固定输入的一次校正；V35首次把同一完整七区算子用于任意迭代残差，让GMRES选择方向组合。因此，这次有实质新信息，不能与V34单步放大混为同一实验，也不能从实现通过推导求解成功。

固定模型仍是1.4×1.05×1.4 nm、384hex、Nédélec p3、q15、18144 trace＋40端口、真实三维缺口、双Floquet。Si使用canonical用户表，nominal0.7 nm，原表0.699999988仅作显式alias，n=`0.999885140474+4.32477054e-6i`，epsilon=n²。trace从精确零开始；内部仿射特解和端口按原方程恢复，初始端口范数实际为0，不能据此把一般端口载荷强设零。

| V35 measured量 | 实际值 | 门限／结论 |
|---|---:|---|
| 首周期内步／周期数 | 256／1 | 仅一条零初值轨迹；info=1 |
| 原Schur残差／完整物理b | 0.20524886351900365 | **>0.01继续门，>1e-6资格门** |
| native／augmented相对残差 | 0.07959628543991103 | **>1e-6** |
| total augmented相对残差 | 0.027619862207395922 | **>1e-6** |
| port／完整b；port operation | 1.3018827521e-16；7.0373341243e-17 | 两项≤1e-6，不能替代整方程 |
| 恢复；原方程恒等式 | 3.8442995044e-13；4.2996403286e-13 | 两项≤1e-10 |
| slave storage | 0 | 约束存储通过 |
| 第二周期；FE物理审核；REF7读取；official R/T/A | NOT_RUN | 因首周期真实进展门失败，不是丢失交付 |

独立按原始标量与预登记阈值重算，接受`ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT`。不放宽0.01，不追加周期。旧V24-LZ首周期Schur为0.222600466、第三周期0.099023685；其累计原作用265／795。V35总体834次作用后仍0.205248864，其中含资格与审核，不能把它们全算成Arnoldi工作，也不能插值制造严格同成本比。它至少没有显示足以继续付费的新收敛能力。

可信链还包括：旧／快S与SH对照最大完整b归一化差1.46416e-13≤1e-11、operation最大1.18089e-16≤1e-10；PC复线性误差7.42378e-14，J平衡最大3.39863e-13≤1e-10；七reader的原主块／伴随配对、两种子solve witness及只读身份通过。实际核严格执行两次J解、六外块解和两次A传播，未读warm、参考场或旧方向来形成解。

最终残差平方的99.1900179%落在六外块，J占0.8099821%，block1＋3占53.7432330%。这是**canonical系数分区**，不是材料场能量。它与当前局部近似未解决外域耦合一致；既不证明唯一物理病因，也不证明任意全局方法都会失败。外域真实剩余算子仍是`A_OO−A_OJ A_JJ^{-1}A_JO`；当前六块对角代替不了其完整传播。

证据入口：[response_v35](response_v35.md)、[run index](outcomes/records/run_index_v35.json)、[checker](outcomes/records/online_checker_v35.json)、[保存残差分析](outcomes/records/residual_analysis_v35.json)。

## 3. 完整费用与两个非阻断的软件问题

| 费用／消费 | 核验后的值 | 正确解释 |
|---|---:|---|
| actor监督／完整launcher | 188.162088667／191.156734449 s | 包含关系，不相加 |
| GMRES周期／PC inclusive | 155.226302155／129.565810602 s | 嵌套时间，不是exclusive可替换份额 |
| 七reader加载hash／全部局部solve | 约14.69／56.797606099 s | 因子并非免费；历史构建另列 |
| 本轮actor＋辅助＋探针 | 188.162088667＋56.737857865＋16.639802861＝261.539749393 s | 首次失败、修复、资源归档和测试均收费；不等于完整合格N=1 |
| 同时整树采样峰／own swap | 2108018688 B／0 | 13组原始样本重算；无专属cgroup连续硬峰证明 |
| 七块A＋LU／pivot | 1591420032／72576 B | 同时数组载荷，不是RSS；共七套真实dense局部因子 |
| 原／快S和SH总次数 | 45＋789＝834 | inherited raw `all_batch_equivalent_actions=45`只计旧作用，已另附修正 |
| PC／零输入PC | 264／2 | 非零262；J=2＋2×262=526，外块=12＋6×262=1584 |
| 三角pass／端口factor／port solve | 4220／2／822 | Hhat与原Hp不同；不得合并成一套或省掉审核 |
| 原audit／恢复 | 1／1 | raw恢复字段0是元数据缺陷，实际调用链与修正均保留 |
| 历史formal时间下界 | 77161.55713859801 s | 不是全部历史费用或N=1，不能作为加速分母 |

[费用](outcomes/records/resource_costs_v35.json)与[元数据修正](outcomes/records/metadata_corrections_v35.json)保留原raw，不回写旧负结果。没有新全局QR、大LU或训练。当前因子压缩虽有存储份额，仍没有合格完整非神经解，也没有训练成本、增迭代成本和20%配对证据。共享工作站的不同日期耗时不能当精确加速比。

测试历史为25例中的24通过／1失败，修复后25通过；后审核26通过；收口41例中34通过／7失败，恢复公开`FAMILY`导出后仅受影响7例复跑通过。保留各自source，不写成最终HEAD全套41例重跑。两次存储预留拒绝在actor／reader前发生，归档后准入，真实actor仍只有一条。

发现以下问题，均不改变已完成的负结果，不值得单独一轮review：

1. **P2，闭账后的测试不可稳定复跑。** `src/test/test_task042_v35_cache.py`末项直接调用真实`v35_verify.dat`，期望“requires original equation pass”；但`src/io/full_input_online.py`先检查live／closed账本，现在会先报closed，未来还会遇到deadline。V36用隔离临时fixture分别测试“closed拒绝”和“数值负结果禁止参考读取”，不能重开V35账本。其余真实缓存测试应显式标注artifact依赖，不让普通干净checkout假装具备ignored证据。
2. **P2，尚无跨启动续跑资格。** 通用`gmres_cycle_commit`支持同目录返回点恢复，但V35 `solve_trajectory`从零开始，checkpoint位于新`stage.artifact`，上层新启动没有绑定旧返回目录。允许FAILED后重新进入不等于跨进程续接。当前只有一次正常返回，没有因它重复消费数值；V36只需修正能力声明并用小fixture验证新工作包的分阶段重入。**不为修复一条已关闭路线开发新V35续跑或启动第二条轨迹。**

## 4. 历史去重与路线状态

早期逐轮表保留于[Review V21 §10.2](review_report_v21.md)，后续完整对照见[Review V32 §3](review_report_v32.md)。以下是当前决定，旧文中的NOT_RUN只能按其当时语境读取。

| 路线 | 已尝试／已否定的范围 | 当前边界 |
|---|---|---|
| V1–V5 p4神经严格粗逆 | 13.5nm固定小例未获严格逆资格，后续有受控反事实 | 已关闭；不是当前0.7nm的新结果 |
| V6–V14 神经FE trace／固定hidden／线性头／hidden更新 | 部分有真实训练；V11真实hidden更新未运行，V12梯度失败，V13一次接受仍无完整求解收益 | 不把固定特征／精确线性头称NN增益，不以loss降代替场资格 |
| V15–V21 固定空间、全空间校正、ILU0、class64、GCROT | 真正残差改善与算子作用降时分别存在，完整物理未过；GPOLY含随机神经G0 | 不称最佳纯非神经完整基线；算子加速不等于收敛改善 |
| V22–V23 p1 Galerkin／image-QR | 约98.99%误差表示不等于能消除残差；V23完整0/6，warm Schur2.507714e-6、通道功率差约1.69973e-6；zero Schur0.0681132 | 不换同空间测试方式、调scalar-tau或忽略global QR／coarse LU费用 |
| V24八原p3主块及image组合 | warm／zero已分别运行；完整0/5，zero LZ4=0.081376668、LCZ4=0.325262223 | 原V24计划已回答；不再称尚未发布，也不追加第五周期 |
| V25–V26 八列最佳LS、J第九方向 | 精确有限空间最优收益很小 | 同列系数网络无新上限，关闭 |
| V27–V32 固定回流第十方向 | 多轮是软件／资源，不是多次PDE失败；实际V32仅再降0.14094%／0.12910% | 关闭，不新增第十一方向 |
| V33–V34 完整输入单位步 | V33未跑；V34两态放大至2.9774／4.0658 | 固定单步关闭 |
| V35 任意RHS七区PC＋冷GMRES | 本次已跑首256步，Schur0.20525，未达0.01 | **完整在线判别已完成，当前固定7/8块族停止追加** |
| 真正全局传播、原尺寸精度／资源、NN20% | 任务内没有相应合格证据 | 不把未运行写成方法失败；全局参考逆交由dot推进 |

## 5. 下一步为什么改做原尺寸完整端口

反射和透射可以沿许多衍射方向离开单胞。DtN端口把这些方向对边界电场的作用带回有限元方程；完整输出也要保留每个方向的复振幅和功率。原尺寸有约数万通道，micro只有40。一个能解内部方程的全局方法，如果仍把所有边界耦合表同时放入内存，或只验几个零阶，仍到不了最终目标。

本次进一步源码检查发现一个具体容量风险：[fullspace_dtn_action.py](../../src/solvers/fullspace_dtn_action.py)虽按batch执行作用，但`FullspaceDtnCarrier`保存全部`entries`；builder的`component_cache`和`entries`也随全部mode增长。它避免显式全局C/D矩阵，**没有证明全部边界泛函存储只随batch增长**。`dtn_surface_vector_cache.py`还需计缓存、构建瞬时副本及MPI分布。PETSc的[shell矩阵文档](https://petsc.org/release/manualpages/Mat/MatCreateShell/)只提供自定义存储和作用接口，并不保证用户上下文的内存有界；不因此升级本地PETSc版本。

这不是已经测得原尺寸必超2TB的结论，而是必须在扩大求解前回答的实现问题。V36要留下能运行的容量检查和端口数据供应接口，不能再只列“target unknown”。代价也明确：逐批生成或读取会增加每步时间和IO；内存下降不能自动算完整求解加速，更不属于NN收益。

### 5.1 与dot的精确分工和目标口径

只读远端dot HEAD为`5be1210aa79f25c13a7677cc291a4a766a548650`。本次读取该版本任务书、README、response_v15和增量：新提交只是63867 B合成NPZ传输探针，不是新PDE或512MiB共享传输资格。已发布Y仍是p4、120cells、6q／3twists、532手动端口；regular最大原残差约8.92748e-12、notch约7.28650e-12，属于其不同材料／网格／几何／端口身份。AUTO32060、p6、原尺寸精度和2TB／48h仍未资格化。

其任务书最新用户范围把首个原尺寸比较对象明确为**规则Si线光栅，不加缺口，仍要求完整3D和后续非可分能力**。本任务原始seed也有完整规则几何；因此V36把“规则原尺寸首对象”和“非可分能力见证”分别登记。前轮“完整非可分三维”的要求继续约束算法能力，不能借规则几何退回二维／2.5D，也不把micro缺口按比例放大成未授权的目标实体。既有`positive_x_middle_y_z40_80`是另一个明确非可分见证，不与规则首对象混同。

- **dot继续拥有**完整3D参考逆、周期q分块、因子／共享存储与规模验证。Task042不迁移或重跑其X/XZ/Y求解，不修改其分支，不实现另一套周期求解器。
- **Task042 V36拥有**原尺寸输入／mode／容量校验、全边界端口泛函的按需供应与完整输出验收接口。接收dot的冻结solver包时先做身份比对，当前不把不同身份的矩阵或factor接上。
- 若dot已实现等价的真正有界端口provider，先按精确文件／接口读证据；同轮复用并验证最小适配，不重复开发。没有匹配包也不等待，完成自有接口与实证。只读外部源码不代表授权整体cherry-pick。

## 6. V36连续工作包：产出具体能力后一次交付

### 6.1 A：冻结原尺寸合同和无装配容量入口

新建独立V36 scope，复用通用input/config、mode和轴计划函数；不通过V35冷求解入口，不依赖任何live历史账本。新增opt-in入口只允许以下准备／组件阶段，默认绝不触发完整目标PDE。

1. **可机器读取的原尺寸物理合同。** 以task.md原seed为几何来源，50×25nm、z=−10..130nm、interface0、17×25×120nm Si光栅；沿该配置的中心／坐标约定给出所有实体边界、tags、上下参考面、单位。λ=.7、grazing1°、azimuth0、s、幅值1、canonical Si用户表、air1／mu1、layered背景、双Floquet、完整三维Nédélec、开放DtN固定。记录source wavelength alias与epsilon=n²，不能借dot近似材料值替换。规则主对象与原有notch见证分别hash；缺口selector是midpoint标签规则的事实必须明示，容量计划要使物理平面对齐，不能假装旧不对齐网格已经表示解析缺口。
2. **真实ordered模式库存。** 调用现有`outgoing_port_modes_3d`／manifest定义，逐mode记录side、m/n、极化、alpha/gamma/beta、传播／倏逝／Rayleigh状态、功率归一化、reference plane、Floquet相位及原H定义。保存紧凑hash和统计，完整数组留ignored。独立用色散关系与整数枚举界检查有无漏项、重复、顺序／相位错误；dot的32060只作历史核对，不硬编码合格数量。`auto_propagating`清单完整仍不等于外部截断误差收敛，保留`CHANNEL_TRUNCATION_UNQUALIFIED`。
3. **准确计数，不造目标mesh。** 生成短轴坐标列表／轴段数和解析实体计数，不创建体积网格、全量DoF编号或矩阵。主容量假设固定p6、最大轴间距0.7nm、q15；这是本轮选定的**容量情景，非已证明精度的生产网格**。另以旧micro密度p3/h0.175/q15作纸面风险对照，两者均不得运行目标PDE或做h/p求解扫描。材料／端口／notch平面必须显式对齐，不从体积比85034硬乘DoF。
4. **容量与运行包。** 给出完整存储、凝聚trace、interior、slave和port数量；PETSc.IntType范围；FE向量、恢复、Krylov、各类局部数据、边界泛函、原H／消元Hhat、IO／缓存的生命周期。每项标确切数组下界、条件上界或unknown，不能把下界拼成峰上界。所有`Nport²`对象列来源／必要性；Hp常为对角不代表Hhat也对角。给出单个稠密complex128端口矩阵的`16*Nport²`字节及共存份数，不能因数万通道就直接判定其单表超过2TB。

六面体张量网格可独立核查：每edge有p个、每face有`2p(p−1)`个、每cell有`3p(p−1)²`个Nédélec自由度。设Nx/Ny/Nz为轴cell数，x/y周期但z开放，在无额外约束时canonical边数为`Nx*Ny*(3Nz+2)`，面数为`Nx*Ny*(3Nz+1)`；trace按上述加权，interior另加。未约束storage须使用未配对的边面计数，不能把active数当storage。该公式在旧8×6×8/p3上应重得trace18144、interior13824、full storage34050、slave2082；它是计数校准，不是创建一个新micro算例。

生产p/h、积分精度、外部衰减通道截断、跨网格场误差及总迭代数尚未证明。把这些保留成**执行前的资格要求**，同时交付可运行的输入和容量检查；不能因精度未证明就把已知几何和可枚举mode继续全写unknown。

### 6.2 B：一个有界端口provider，复用已有作用与审核

这里的provider只负责按要求交出某一批端口的边界系数，消费方负责原作用、恢复与输出。它替换“一次保留所有端口系数”的存储方式，不改变Maxwell、模态截断、极化、投影归一化或求解方法。

- 先沿现有`fullspace_dtn_action`／surface assembler／cache走一遍对象生命周期。复用能满足接口的代码；缺项才在通用`src/`补充惰性迭代provider及消费适配。runner只编排，不复制另一套体积求解器。ordinary default保持，研究入口显式opt-in。
- 一批必须携带完整mode key、canonical rows／ownership、projection和traction／coupling复系数、原H及schema/hash。不得假定D=Cᴴ或Hp=Hhat；上下端口不能丢一侧。批次重放次序固定，逐批完成MPI collective，空owner正常参与。不得在每个rank暗建全量mode×surface值表。
- 默认最多64个mode、数值缓存上限64MiB；两者取更严格者，活跃生成／复制／消费对象另行计入上界。**若单mode超过缓存上限必须显式拒绝并报告必要的surface-row分块接口，不能静默放大cap。** 小fixture和真实micro见证使用最多2个mode、1MiB缓存以强制淘汰，检查早期批次没有仍被外层列表／component_cache引用。mode元数据、返回的全端口振幅O(Nport)、FE向量O(NFE)可保留，但必须单独计量。
- 允许重算或只读逐批载入已有泛函；source及缓存身份变化要失效，原始字段不能被覆盖。分别记录生成／加载／hash／作用／伴随／归约／输出和读写字节，区分cold与缓存复用；峰内存包括creator、provider、consumer及子进程，不只报cache.nbytes。
- 若给dot的是边界作用接口，应保留完整3D ownership和复Floquet约定；若给的是输出验证接口，应输出全ordered复振幅和逐通道功率，不能仅R00。不会接管dot的q逆、共享因子或压缩投影实验。

### 6.3 C：先本地修bug，随后完成一次真实组件资格

合成测试先覆盖非Hermitian复数据、非零两端输入、零输入、复线性、adjoint点积、只读／坏hash／乱序拒绝、空owner、缓存淘汰和中断后安全重入。修复§3测试，使用全新临时scope，不碰真实closed窗口。按改动运行相关serial及必要MPI2／MPI4；源码／ABI／math-thread getter先过，费用纳入同一包，不重跑无关旧全仓PDE。

**不得停在合成测试通过或只交一张容量表。** 使用已有冻结micro的几何、p3、q15、完整40mode，接入原FE表面组装／泛函路径，在一个受监督的组件actor内对比旧resident与新provider。只构造所需小FE空间、边界系数与作用，不构造新全局LU、不解体积方程、不读七区LU、不重新做GMRES。若已有合格边界泛函可复用，核对hash后使用，不能冒充重新组装。

固定两组未拟合复输入seed=`423611,423613`，包含两个端口侧、共享实体／Floquet非零相位及空rank测试；另用零输入与复数缩放。对每个全量输入执行原边界作用、新作用及其伴随对照；保存输入／输出和每批身份。恢复完整40复端口，并从同一保存的端口向量独立重算逐通道功率。它是**边界组件准确性**，不能写成新的全前向解或official R/T/A。

| Gate | 固定验收／动作 |
|---|---|
| mode身份 | 全ordered keys、side、相位、归一化和schema配对；无重复／丢失；失败先修实现 |
| 数值等价 | 非零量用`norm(new-old)/max(norm(new),norm(old))≤1e-10`，并保存分子／分母；两者为零单独要求零。强抵消时补充抵消前operation尺度，但不得用它遮蔽原相对门失败 |
| 伴随／复线性 | 点积及缩放按抵消前operand尺度≤1e-10；不要求算子Hermitian |
| 端口／功率 | 全复向量相对≤1e-10；单位归一化见证的每通道功率最大绝对差≤1e-10；通道近零不能用相对误差除零 |
| 缓存有界 | 可审计全部数值对象、引用释放与最大活跃批数；无全mode×surface隐藏表，配置cap不被越过；额外复制单列 |
| MPI | 对实际修改的collective／ownership路径，必要MPI2／4小fixture与serial完整向量一致；不能只比较一个R/T总值 |
| 原尺寸入口 | 完整真实mode元数据与解析mesh计数实际生成、checker通过；**原尺寸全表面FE作用、体积求解及精度仍NOT_RUN** |

组件出现数值失配，先定位行序／共轭／归一化／cache bug，同一V36修复并只重跑受影响部分；不降低阈值，不用重复投机运行选择通过样本。当前review不授权目标尺寸FE装配、原尺寸矩阵／因子、完整PDE、网络训练、全局QR或任何新预条件器试验。

### 6.4 D：按结果直接完成部署接口与替代分析

- 组件通过：交付一个完整命令入口，能够生成原尺寸contract／mode／容量报告、消费冻结组件证据并输出“可进入哪一阶段”的机器状态；列出全局solver需要提供的source、3D作用／恢复、mode/row身份和资源字段。若没有匹配solver，状态必须是`TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED`，准备命令不得自动启动目标solve。新的端口组件只获`PORT_COMPONENT_QUALIFIED_ON_MICRO`。
- 组件虽正确但cold生成／IO过贵：保留每次端口作用和读写费用，计算48小时内可供全局solver使用的剩余时间／作用次数条件，不能以省内存单项称整体成功。后续优先消费dot已有紧凑投影或等价边界结构；本轮不新开FFT、低秩、NN压缩三条竞赛路线。
- 准入或容量门拒绝：继续完成不用数值的目标合同、精确计数、接口与排除式；指出哪个**同时存活对象／未知成本**导致不能进入下一阶段，不笼统说“原尺寸不可算”。单mode越界则交surface-row分块的最小协议与所需bytes，不伪造已实现／已资格化。
- 与dot身份不匹配：输出逐字段差异及最小适配需求；保留本组件的独立正确性。不得等待dot代替本轮全部工作，也不得把其p4/532结果冒充本p6/AUTO资格。

只有“完整可执行准备包＋真实组件结果（或已触发的真实Gate及有效替代分析）”才是V36收口；一个lint失败、一个导入错误、只完成schema或暂时无空闲CPU都不构成提前交回理由。

## 7. V36预算、停止条件与一次交接

本轮不扩大工作站共享配额。使用新ledger，保留所有失败／重入收费；历史V24–V35账本永久closed。既有Task042 native activation、complex128、MPI/ABI一致、实际math threads=1、无GPU；重型组件一次一个，使用新鲜共享CPU准入／SMT避让、nice/IO优先级及原系统／邻增长余量。不得依据整机空闲内存自行加CPU。

| 预算／边界 | V36固定上限与解释 |
|---|---|
| 日历窗口 | 首次实际启动登记起24h；末1h只清场／证据／交付。不是目标48h预算，修改source不重置 |
| 新增有载总wall | 1800 s，含组件、合成／MPI测试、checker、探针及失败；末60 s留清场，先写账再做工作 |
| 真实micro边界组件 | 累计≤900 s，warn6GiB／hard8GiB，own swap0；是合同资源门，不是外层任意短timeout |
| 纯inventory／小fixture／文档 | 每个受监督辅助≤300 s、2GiB；累计与组件共享1800 s，不重复计嵌套时间 |
| 探针 | 实测累计≤30 s；暂时CPU拒绝有序WAIT，间隔≥120 s再探，不重新排相同actor；WAIT本身不冒充数值失败 |
| 存储 | 新增ignored数值artifact≤512MiB；Task042原总20GiB与磁盘自由≥50GiB继续；只有hash可验证的无损归档能回收重复证据 |
| 调用范围 | A/SH完整体积作用、新LU、QR、完整solve、训练均0；授权的是mode枚举、边界组装／作用和小fixture |

真实身份／ABI／数值／资源门触发时保存原始原因并停止受影响actor，清除完整自有后代；普通实现bug在剩余预算内修复，有限输出持久化后续接，已通过且source/hash无关的阶段不重跑。不得因为日历尚有余量就突破有载预算，也不得因用户要求持续推进而绕过这些门。预算耗尽仍完成metadata-only归因及部署缺口表，不能偷偷重置窗口。

V36一次性提交实现、相关测试、原尺寸contract及清单、完整组件原始证据／checker、费用与生命周期、失败替代分析、`response_v36`和outcomes／项目总账更新。按依赖组区分通用核心、runner/checker、研究入口和compact文档；组件不提升ordinary default。明确列出：目标p/h／积分精度、外部截断、原尺寸完整残差／场／全部衍射级、2TB峰、48h完整N=1及NN20%仍未资格化的项目。

只fast-forward提交推送当前原执行分支，不amend／force、不merge/rebase master，不修改dot。结束后清场、closed、报告精确HEAD/base、upstream 0/0和证据索引，通过既有队列通知审阅窗口，再停止仓库工作。**本报告不授予merge approval。**

本次文档检查见[验收记录](outcomes/records/review_v33_documentation_checks.json)。GitHub页面读取未成功，本地结构检查不能替代已观看远端渲染，不声称CI或GitHub视觉通过。
