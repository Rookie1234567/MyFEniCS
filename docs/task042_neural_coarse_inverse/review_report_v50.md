# Review V50：保留相位表示突破，连续完成0.7 nm三维缺口的p/h准确性闭环

## 0. 决定、身份与主线

**接受V51的解析FLAT准确性、完整原方程及恢复证据；NOTCH的p/h场精度仍未通过。授权V52沿同一确定性相位有限元路线继续：Z4/p5与Z2/p6两条独立分辨对照，必要时在共同加密的Z4/p6上闭合；数值准确后才做一次有限模式截断对照。不得退回NN预条件器、另造神经子空间或重复平界面campaign。**

这项工作消除的blocker是：快速横向入射相位已经正确表示，但真实非可分三维散射尚缺足够的空间分辨证据。交付应为完整NOTCH场、严格原方程及共同物理误差、实际容量/费用，而不是又一组接口测试。普通bug同轮修复并继续；真实精度不足不能改称bug，安全门也不放宽。

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task42_neural_coarse_inverse
canonical_worktree         = /home/fenics/Projects/NN-Lab
review_date                = 2026-10-05
reviewed_HEAD              = 31a444d64b16d5078deeca01c9c3b661e6affc96
reviewed_commit_UTC         = 2026-10-05T10:58:19Z
previous_review            = review_report_v49.md
previous_review_commit     = 97ca0d4e2d90f7479a757e66d43061b7d54bf3aa
reviewed_response          = response_v51.md
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
sibling_branch_readonly    = task42extra_feinn_5nm
sibling_HEAD_readonly      = 8d617d4d206b08f38279320b67188db1b8ccd301
sibling_contract           = Review V29 / V30_ADAPTIVE_WAVE_NEURAL_GALERKIN
next_batch                 = V52_PHASE_NOTCH_HP_ACCURACY_CLOSURE
required_response          = response_v52.md
NN_training_or_NN_PC       = NOT_AUTHORIZED_THIS_BATCH
target_0p7nm_2TB_48h        = NOT_QUALIFIED
master_or_other_branch     = NO_WRITE_NO_MERGE
```

V49已由V51正式回应，故新增V50。本报告明确扩展有限p/h队列、稀疏分析行数和条件828模式对照，覆盖上一批的相应数量限制，不改旧结果、精度门或治理原则。用户转交执行；不得自动通知或接管隔壁窗口。同一工作树仅一个写入者/数值actor。

最终目标仍为50×25 nm周期、z=−10..130 nm、17×25×120 nm Si结构、λ0.7 nm并保留任意非可分三维能力；单次完整流程≤172800 s、约2 TB整机保留系统余量、任务峰≤2e12 B、ownswap/OOC=0。当前缩尺模型的有限增量一致性不等于原尺寸、严格连续误差界或生产架构。项目成功不要求使用NN；以后宣称NN收益时仍需相同正确性的完整成本比较。

本次ChatGPT读取实时两支线ref、V51回应/结果/源码/资源与拓扑记录及V49后11个提交的文件差异；未SSH工作站、未访问全部ignored数组、未重跑PDE或测量实时机器资源。同blob的根/目录AGENTS、仓库原则、原task、V49合同及既有补充限制继续复用；差异中没有新的补充任务书或另一份已执行review。下面数值属于仓库记录中的measured，拓扑为derived，新队列为planned/not_run。

## 1. V51的实质进展与尚未解决的问题

依据：[回应](response_v51.md)、[完整结果](outcomes/phase_explicit_full3d_accuracy_v51.md)、[科学门](outcomes/records/phase_accuracy_checks_v51.json)、[运行身份](outcomes/records/run_index_v51.json)、[区域](outcomes/records/physical_error_regions_v51.json)、[费用](outcomes/records/resource_costs_final_v51.json)。

| 同0.7 nm、固定相位gVh、完整532模式 | recorded measured结果 | 审阅结论 |
|---|---|---|
| 80hex/p4 FLAT解析E/H/curl | 3.85798e-8 / 4.63574e-8 / 4.63574e-8；门1e-4 | 明确准确性突破；不重复求解 |
| FLAT R/T/A_volume | 0.113433408921 / 0.882458998614 / 0.004107592466；最大逐mode功率差8.83182e-13 | 解析功率通过，不只守恒 |
| 四个完整状态原true/native | 2.88117e-12..4.77771e-12；最坏增广4.80787e-11 | 全部满足原1e-6；恢复最坏1.48409e-15满足1e-10 |
| NOTCH 80hex p4→p5 | total E/H差1.38146e-4 / 1.35253e-4；scattered E/H差9.61667e-4 / 9.41540e-4 | 超过1e-4；不是代数未收敛 |
| NOTCH p5→160hex Z2/p5 | total E/H差1.22562e-4 / 1.22545e-4；scattered差8.53183e-4 / 8.53072e-4；复通道1.51246e-4 | 仍未过场及复通道门 |
| 上述两组功率增量 | 逐mode最大8.28146e-7 / 8.42200e-7；能量约1e-13 | 功率单项通过，不覆盖场FAIL |
| 完整边界/共同积分 | q47/q63通过；场积分q23/q31操作缺陷≤1.54e-15 | 不再默认归咎于求积，也不重跑旧q归因 |

当前判断为`FLAT_PASS_NOTCH_NOT_QUALIFIED`。新相位表示没有把任意散射场自动变成低频；不能仅凭FLAT准确就启动原尺寸。p/h差是两个近似解的差，不是已认证真实误差，不能用假定h^p收敛率外推通过。

V51的方向指标来自`PhaseEvaluator.gradient_indicator`，对**总包络**u和Henv求导，x/y/z总量为0.0001223084/0.0000032021/2.8128084。它解释了为何按合同选Z2，但不是误差估计。约68%的增量差平方在缺口外空气、约24–25%在Si；Ey分量占比高也不等于应沿y细化。故不将“继续Z4”当唯一可能，不做无休止Z8/Z16序列。

V51的N5求解已返回，后处理将实值复波矢转float时失败；同轮修复并补审，**没有重解**。此流程应保留。F4 source=`db95e8cf859385f02eef12f6bdd1a942f2cec2e7`；N4/N5原solve=`9100a925a2a074a2a305def8f27ec992451178c7`；N5补审=`62537a4e7c56336160ec59f022081841abb8566c`；Z2=`c3009dd66993b42961666758068f343cd67044e8`；VERIFY=`80e227660baac5bd89b0220455e4207bcb1d51d6`。文档HEAD不是这些运行source。

Z2 dat链下界841.587 s、采样树峰3.49633 GiB；凝聚/局部准备639.390 s，全局symbolic+numeric约19.194 s。首次dense包络不合格后，可靠稀疏symbolic估计1768 decimal MB使numeric被安全准入。这说明不能把dense情景当实际稀疏峰，也不能假定更大模型仍只用3.5 GiB。共享CPU、缓存和审核口径不同，尚不授同准确性加速。

## 2. 与隔壁分工及冻结物理

**Task042继续确定性0.7 nm准确离散；Task42extra独立研究5 nm起步的学习波动greedy子空间。** 本批不训练方向、幅值、字典、teacher或NN-PC，不运行M5，不读隔壁训练数组，不修改/启动其工作树，不再次迁移固定相位模块。只读ref未变不代表隔壁本机无任务；共享资源仍现场检查。

主问题沿V51的全精度descriptor：s=7/135；x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)。固定λ0.7 nm、grazing1°、azimuth5°、s偏振、幅值1；air=1，Si n=0.999885140474+4.32477054e-6i，epsilon=n²、mu=1，材料表hash=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。不重新索要或替换材料。

NOTCH仍是V51精确几何盒，两原Si cell改为空气；新网格按几何范围标记，不能用旧cell编号。所有新case保持同一连续几何，不扩大计算域。模型维数、p、三轴划分倍数、mode清单和q必须写入真实resolved descriptor，不继续留下“cells=80/degree4”作为新case活动字段；旧raw模板不回写。

```math
E=e^{i\kappa\cdot x}u,\qquad
C_\kappa u=\nabla\times u+i\kappa\times u,\qquad
H_{code}=e^{i\kappa\cdot x}C_\kappa u/(i k_0\mu_r).
```

κ=(kx_inc,ky_inc,0)固定，u双周期，H_SI=Hcode/eta0。沿原完整Cκ trial/test弱式、真实物理入射RHS、全部内部自由度和通用增广凝聚；不得投回旧多项式场、使用paraxial近似、删除非零内部端口项或按幅值剪枝。原未凝聚物理作用作为独立oracle保留。

## 3. 一次连续计算包：h、p与共同加密，不只做单个Z4

B0为V51已保存的`NOTCH_HPROBE`（Z2/p5），不是新求解。F4/N4/N5/B0及边界资格从V51 run/delivery的父receipt解析，只重哈希实际消费文件一次；不复制全部历史索引。已缺失的某个场只阻塞依赖对照，其他新完整问题继续；不得从summary数字伪造系数。

| 新角色 | 三轴原区间划分倍数 / p | cell数 | 独立FE / trace / 内部（derived） | 凝聚行含532 | 作用 |
|---|---|---:|---|---:|---|
| H | (1,1,4) / p5 | 320 | 120800 / 44000 / 76800 | 44532 | 沿同p检验z分辨 |
| P | (1,1,2) / p6 | 160 | 104832 / 32832 / 72000 | 33364 | 同Z2升p，兼查横向与局部表示 |
| HP，条件 | (1,1,4) / p6 | 320 | 208512 / 64512 / 144000 | 65044 | H与P共同的更丰富空间 |
| T，条件 | (2,1,2)或(1,2,2) / p6 | 320 | 209664 / 65664 / 144000 | 66196 | 一次横向独立诊断，不开始参数扫描 |
| M，条件 | 已合格端点同网格同p / 828模式 | 不变 | FE不变 | 原行数+296 | 只检验有限模式截断增量 |

以上为结构化xy周期拓扑推导，须以实际MPC核实，不能删行匹配。允许通用三轴整数倍划分，不再用`grid[1:]`只能表示单轴的旧接线；旧入口语义保持。p6是本批明确的新p，不能被旧hard-coded p4/p5 role静默降阶。

### 3.1 主队列及停止“等下一份review”的位置

先做必要新增接线，然后顺序H、P，哪个因容量/独立接口被隔离，另一个照做；不要求H先准确才允许P。两者均从真实物理零初值独立求解，不用旧field造RHS。准确参考直接后端仍沿已资格MUMPS及精确端口坐标变换，无新PC、排序/位移/BLR/OOC或迭代器研究。

每个返回状态立即保存完整包络/port/输入与source，完成原方程审核后释放全局factor/无用矩阵，再做共同场积分。先比较B0→H、B0→P及H↔P，三组都按§5原门；H/P非嵌套，共同几何积分不得把一方简单插值为另一方后相减。

- 若上述三组全部通过，可记录加强的固定532有限一致性，不必为跑满预算再算HP；选合格端点中独立FE较少者作为M父case，平手按已冻结成本规则。
- 否则在容量/时间允许时**直接运行HP**，比较H→HP（同网格p增量）及P→HP（同p的z增量）。这两组都通过，才形成具有两个分辨方向支持的固定532锚点；旧B0失败不被改写，也不要求粗B0必须准确。
- HP数学可信但仍未形成上述锚点，或HP安全容量阻塞而P可用，允许一次T。按P的**散射包络**横向指标`I_d=sum h_K,d² integral(|∂d(u-u_bg)|²+|∂d(Henv-Hbg_env)|²)`、d=x/y，选最大轴，平手x；本层状背景去横向相位后x/y导数解析为零，不必新建背景拟合。T与P同z同p比较，可进一步指出横向分辨是否重要，不据此宣布共同加密已经收敛。不是根据Ey占比选y。
- 没有P时不从缺失场猜方向；T不运行，完成已有H/HP的可达比较。若仅一个p/h对照通过，记`ONE_INCREMENT_PASS_NOT_CROSSCHECKED`，不等同于上述加强锚点，也不启动M。

T是有界精度诊断，不自动扩成X2Z4、p7或另一套自适应框架。本批最多5个新完整solve，对应H/P/HP/T/M；T通常与M互斥。不以达到一次小残差、代码提交或阶段边界为停工点。预算/安全/真实数值能力限制始终有效，不保证本批必然跨过1e-4。

本批是确定性误差控制，可在保存并核对当前场后按以上规则继续；不机械继承NN“读过参考后不得再做确定性加密”的限制。不得用比较结果调阈值、材料、相位、分母或挑选最好中间解。

### 3.2 条件M：准确性锚点后只做一次完整截断对照

先固定p/h锚点与其源码/hash，再对**同一个**网格/p/材料/入射只把manual库存扩大为m=−11..11、n=−4..4，上下×两偏振，共828。仍保留全部模式，无AUTO32060/原尺寸surface campaign，不与隔壁或dot重复组件任务。532→828是新的有限边界模型，不是原矩阵同身份或严格无限模态收敛。

首个828对象明确检查完整新增库存和其q47/q63配对；若实测不稳，沿V49已授权的一次63/79有据配对，不循环增加q。确认积分后再完整求解。公共532 mode按(side,m,n,polarization,reference plane)配对，不按数组下标错配；两物理场在统一828参考面投影后比较全部复量，旧场新增mode不得直接假设为零。原532已发布功率原样保留，新增投影诊断另表。

比较完整E/H/curl、固定selected、共同532键及新增296模式的实际振幅/功率、R/T/A/A_volume；阈值仍§5。增量失败记`FINITE_MODE_INCREMENT_NOT_QUALIFIED`，保留已获得的固定532 p/h证据，不再追加第三套模式或修改门。通过也只授“这一对有限库存的增量一致性”。

## 4. 容量必须实际推进，但不能以OOM探路

本报告将这些明确有限case的**稀疏装配/symbolic行数上限提高至80000**；不提高RSS许可：计划同时≤16GiB、warning20GiB、采样整树停止24GiB，ownswap/OOC=0。旧35000是上一批授权界，不是Z4必定装不下的数学结论。

先用实际mesh/MPC、所有内部/trace/边界支撑和真实矩阵图估算装配。旧`h_capacity`的全cell重复缓存、全native×mode及多份稠密图上界超过16GiB时，可以通过**实际存储布局**取得更紧的安全界；不能直接把admitted设True。只计确实共享的同身份raw/方向类，保留全部非零边界cell支撑（包括浮点内部项），完整计PETSc索引宽度、COO/CSR副本、缩放副本与峰时对象。不得用理论零迹删项来降低容量。

装配有安全包络后，复用`AnalyzedDirectFactor`的阶段顺序：symbolic→读取现场INFOG/控制→numeric准入。固定工程策略保持`当前同时树RSS + 2×可信symbolic factor/workspace估计 + 2GiB后续reserve ≤16GiB`；同时检查自己的原RSS/swap与宿主余量。现场INFOG字段/单位按现有版本核对，估计缺失/溢出/不可靠不启动numeric。ICNTL(22)=0；ICNTL(23)限额与整树监督是不同层的保护，不把它称全进程内存保证。

只提高合法有限case行数，不调排序、pivot、shift、精化次数或factor精度。失败容量依赖隔离；例如H不准入仍可完成更少行的P。一次只驻留一套全局因子，solve→true residual→保存最小恢复包→释放factor及矩阵→恢复/后处理；不删除原oracle，不复制全部factor作统计。

原exact tensor与边界资格按完整数学身份复用，含p/κ/真实J/材料/方向/端口参考面/q；纯平移能否共享必须由现有合同证明，不按近似宽度或坐标四舍五入合类。旧六Gram若不包含Cκ交叉项，不能在本批替换当前正确FFCx核。本批不为加快准备另开优化研究。

## 5. 原门不改，比较必须在完整物理场上

| Gate | 要求 |
|---|---|
| 方程 | 原未凝聚完整Cκ弱式＋全部DtN；true/native/增广/port各≤1e-6；直接内部目标≤1e-10，至多两次既有残差精化 |
| 恢复 | 全内部特解、非零内部port支撑、MPC/slave和操作恒等式≤1e-10；保留原slave-zero规则 |
| 场增量 | 共同物理积分的total及scattered E/H/scaled-curl、selected和物理参考面复通道各≤1e-4，沿V51固定near-zero规则 |
| 功率 | R/T/A/A_volume增量及独立体吸收能量闭合≤1e-5；最大逐mode功率增量≤1e-6 |
| 积分 | 新p/几何所需边界配对1e-11/操作1e-10；共同场积分q23/q31操作门1e-10，并保留误差分子/参考分母 |

total与scattered都必须验；同一解析背景相减使差分分子相同，却使相对分母不同，不能拿total过门掩盖散射FAIL。两级物理场以`完整native包络+mesh/MPC/κ`重新求值，不以旧DG投影或样点代替authority。固定selected至少保留V51同一批物理点，避开不唯一材料界面取值；原细网格中心对照另存，不用换点改善结果。

H↔P或HP↔T等非嵌套比较在**两网格共同细分**上积分；对每个共同子盒分别确定两侧父单元并求原场，不要求“fine”一定几何包含“coarse”。只扩展现有`common_physical_difference`的几何配对，不开发新后处理系统。保存每个场的L2分子/分母、各互斥材料区平方份额，细化方向标记与精度界分开。

原raw端口在消逝通道可极端病态；保存raw差、H加权原行残差和已知参考面变换后的复振幅三种尺度，不能彼此冒充，也不能拟合相位。V51 raw差历史保留。功率/参考面公式已资格化，不再重写另一套。

FLAT源的数学依赖未变化，直接引用其解析PASS。若本轮发现并修正真正影响Cκ/物理RHS/端口符号的公共bug，需按影响范围重新验对应锚点；一项必要FLAT重验占用上述5个solve总额，优先替代T/M，不暗加无限回归。仅schema、writer、容量或新case接线变化不触发FLAT重跑。

科学判定至少区分：`FLAT_PASS_NOTCH_NOT_QUALIFIED`、`ONE_INCREMENT_PASS_NOT_CROSSCHECKED`、`CROSSCHECKED_FIXED_532_ANCHOR`、`FINITE_532_TO_828_INCREMENT_PASS`、`CAPACITY_BLOCKED`、`NUMERICAL_ACCURACY_NOT_REACHED`。任何有限pass都不是严格continuum/无限DtN/原尺寸/2TB48h或NN20。

## 6. 减少测试负担，普通bug不终止整包

复用V51已完成的相位curl、κ=0、非零内部/port凝聚、原保存/补审、单位与FLAT证据。新增targeted仅覆盖：三轴case和真实p6/模式绑定；非嵌套共同积分的一个多项式反例；旧/新稀疏容量准入正负例；条件828的实际长度与键匹配。相关Ruff/compile与一次紧凑文档检查即可。不例行全库pytest、不重建全仓索引、不重哈希全部旧artifact、不复制上千条旧JSON。

新p6、真正变化的边界layout/模式库存才增加完整新资格；相同数学face/class内核在case间复用其证据，只核对新的散布/作用。不对每cell重复同一tensor核，不因文档commit重跑科学数据。共同场验证最多同时打开一对解，缓存已算比较，不最后把所有健康父解全部重算一遍。

普通API/shape/复数dtype/stage/路径/缓存/序列化/collector bug按failure→hypothesis→最小修复→targeted→resume处理，**没有“第几个bug就停整批”的次数门**。同根因两次未修复，必须换定位方法或走独立已授权case，不第三次盲跑。累计修复及其重放≤7200s、元数据/文档检查目标≤1200s，均受总窗；非关键网页/格式问题不打断正确科学actor。

每次求解返回先原子保存完整向量、κ/port/实际descriptor/source/父hash，再做派生输出；`AUDIT_PENDING`补审不得重新factor/solve。提交与trial状态分开。只有数学源或输入改变使保存解真正失效时才重算受影响case，失败和旧向量都保留。权威文件/ABI/监督失效先隔离，不能把用户的“别中断”解释成跳过安全或精度。

H/P算完、代码commit、一次比较FAIL均不自动交棒；按§3继续HP、T或M等已授权可达路径。所有安全可做路线完成、全局预算耗尽、用户新停止指令或无法恢复的科学/权限/资源阻塞，才整体收口。数值不准是允许的诚实结果，但不能用测试条数来包装进展。

## 7. 时间、资源、交付和下一尺度

首项实际准备以UTC/monotonic/boot_id冻结新7h总研发窗，数值/科学审核有载≤5h，最后45min收尾；至少预留1200s给新增场的独立验收。实现/修复/等待/输出/归档/提交全部计费，旧V51 closed窗不重开。按实际首case费用提前分配剩余case额度，不用任意几十秒timeout杀正常JIT或factor；所有单case配额仍受总窗，不临近超时反复延长。每次上下文恢复和新stage重读实时钟及ledger。

资源沿V51：MPI1、数学/CPU线程1、GPU0、Loader0、ownswap/OOC0；计划16GiB、warning20GiB、采样整树stop24GiB。实时空闲物理核/避忙SMT、系统与邻任务增长余量、原PSI、自有锁和完整进程树watchdog保持。不能改隔壁/其他任务的进程、环境、亲和性、锁、watchdog或系统ABI/BLAS/CUDA。资源压力只清自己后代；至多一次≤600s前台冷却、原安全门恢复后续接，等待照计，不能无限轮询。

新ignored≤8GiB、Task042去重累计≤46GiB、free≥50GiB，交付至少留256MiB；这是显式增量磁盘许可，不删旧失败或他人文件。只在准入及stage边界统计存储，不让高频监督扫描全历史目录。实际采样间隔与口径如实记录，不宣称连续cgroup硬峰或绝对无干扰。

完成后只形成一个集中`response_v52.md`与`outcomes/phase_notch_hp_accuracy_v52.md`，含case/父hash、全场/模式/原残差、比较矩阵、条件分流、真实source、修复/补审、全部费用、同时对象及symbolic/实测峰。README/summary/两总账追加短入口，旧task/review/response/raw不改。无人工构造的CI/视觉PASS。

若取得锚点，给**一个**下一尺度完整pilot的精确几何/p/h/模式设计、行数与存储区间及真正未知的factor fill/迭代数；本批不启动更大几何。若只缺某方向或容量，给实际缺口及对应的下一最小变化，不默认转NN或继续Z8。原尺寸生产主线仍为准确高阶空间、分布式/matrix-free全局作用、streaming DtN及有界可扩展迭代；本批有限直接authority不改变这一定位。

## 8. Git与可执行入口

仅在canonical NN-Lab核对branch/HEAD/upstream/origin/worktree和本任务活跃进程后安全fetch/ff-only。不reset/stash/clean、不改其他worktree或共享Git配置。正式计算前提交clean数学源码；可在无活跃受检actor的stage边界提交后继续本合同，无需每小步等待review。旧case/plan窗口不改成V52，必须建立新namespace与真实descriptor。

复用run_case、现有phase物理核/凝聚/直接后端/补审/监督；新增数值仍在src。用薄的case参数与队列扩展，不再复制一个大型solver runner。待实现并validate的入口如下，各dat只表示一项明确stage/case：

```text
input/task042_neural_coarse_inverse/v52_notch_resolution_preflight.dat
input/task042_neural_coarse_inverse/v52_notch_z4_p5.dat
input/task042_neural_coarse_inverse/v52_notch_z2_p6.dat
input/task042_neural_coarse_inverse/v52_notch_z4_p6.dat
input/task042_neural_coarse_inverse/v52_notch_transverse_p6.dat
input/task042_neural_coarse_inverse/v52_notch_modes828.dat
input/task042_neural_coarse_inverse/v52_verify_cost.dat
```

统一经`python scripts/run_case.py <one-run.dat>`，不得在入口未实现时声称可运行，不盲跑未准入条件case。每run保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/discretization/material/mode/source/array hash、run_summary和全过程资源。科学状态先保存；精确GitHub视觉页面不可取就标NOT_VERIFIED，不重跑PDE。

仅推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。最终核对实时remote/HEAD、clean/upstream、closed/active null、清场/释放锁，交付给用户后暂停。不通知/接管隔壁、不启动新窗、不merge master或其他分支。

### 外部方法依据与适用范围

p/h比较仍需实际场证据，不能因单元阶数高就假定进入渐近收敛；高频Nédélec分析明确区分波数相关的分辨与前渐近误差，见[Chaumont-Frelet等，2024](https://arxiv.org/abs/2408.04507)。其边界/假设不直接授予本Floquet/DtN问题误差界，本批不实现新的残差估计器。MUMPS的INFOG读取、in-core控制与每处理器工作内存限制见[PETSc官方接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)；现场版本冻结，不借文档升级环境。
