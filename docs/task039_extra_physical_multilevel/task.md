# Task39extra 任务书：真实物理中间层 Maxwell 预条件与 0.7 nm 三维路线

## 0. 身份、目标与本轮权限

```text
task                         = Task39extra
branch                       = task39extra
repository                   = Rookie1234567/MyFEniCS
base_branch                  = codex/20260820-task38-extra-full3d-iterative-0p7nm
base_SHA                     = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
base_latest_commit           = feat(task038): record V19 PML R0 resource anchor
base_latest_review_response  = review_report_v19.md / response_v19.md
historical_master_base       = 438caf150439343ee7c4c58ad7e02a3da812a23c
created_date                 = 2026-09-07
initial_status               = AUTHORIZED_FOR_LOCAL_13P5NM_IMPLEMENTATION
primary_entry                = python scripts/run_case.py input/path/to/case.dat
response_required            = response_v1.md
local_execution_batch        = A0 -> A1 -> A2 -> conditional A2R -> A3 -> A4 -> A5
local_mandatory_stop          = terminal failure or A5 closeout
workstation_phases           = W0 -> W1 -> W2 -> W3 -> W4; roadmap, not auto-authorized heavy runs
ordinary_default_change      = forbidden
master_merge                 = NOT_APPROVED
```

**首先要消除的blocker：目前只有便宜的positive辅助层级，缺少能在原始三维Maxwell方程上有效工作的全局物理纠错。本任务先在16GB本机、13.5nm上验证一个完整的物理中间层预条件器，然后立即检验同尺度非可分三维结构。**

最终目标为单节点约2TB物理内存内的0.7nm、complex128、Nedelec H(curl)、x/y双Floquet、z开放边界、任意非可分三维周期单胞散射。输出复数E/H、近场、R/T/A、体吸收及衍射级。非周期有限目标不在当前范围。

用户本轮明确要求从Task038-extra建立`task39extra`。因此本次是经授权的stacked research branch，不从master另建，也不把继承的research代码整体提升为production；远端分支已由ChatGPT按本轮明确指令建立。Codex须在canonical clone登记对应worktree并核对upstream，不再创建同义分支。该例外不改根规则，也不授权今后随意重建分支。

## 1. 文件与权威顺序

先读本目录三份文件：

- [文献报告](literature_review.md)：知识、公式、原始来源和证据等级；
- [历史经验报告](prior_attempts_retrospective.md)：所有主要尝试的因果链与边界；
- 本任务书：唯一初始执行合同，后续由本目录最新review补充。

同时读取根`AGENTS.md`、`docs/AGENTS.md`、`docs/repository_work_principles.md`、`docs/markdown_rendering_standard.md`、适用的`src/`与目录AGENTS。旧Task038-extra的task、最新review/response和summary用于继承事实，不再把旧任务的阶段控制流当本任务的执行权限。

权威：用户本轮指令 > 本task/本目录最新review > 适用AGENTS > 两份报告 > 旧task过程材料。新任务明确替代旧任务的“不得开启physical coarse/新分支”和MPI1严格2GB入场线；旧结果、旧Gate及负分类全部保持不变。Task039 Hybrid与Task040不是本任务，也不得在那些分支写入本任务代码或报告。

本任务书授权完成本机连续批次，不要求A0 docs-only后再等review。读完、完成安全预检后即可实现并进入真实计算；每次小测试之后不再停审。工作站heavy阶段须等本机收口、用户确认迁移与实际环境资格，不在本机启动5nm或0.7nm全尺寸PDE。

## 2. 本轮做什么，不做什么

| 范围 | 决定 |
|---|---|
| fine物理方程、材料、原始p6/h10离散与DtN | 冻结，不加物理吸收、不减少通道 |
| 主候选 | `physical_intermediate_p4_shifted_aux_v1`，完整外层真实求解 |
| positive pMG | 保留作fine pre/post辅助工具，不再单独资格化为完整inverse |
| 中间层 | same-mesh p4上的真实Maxwell修正；不是旧p3一次单位步长修正 |
| 中间层内部PC | 固定complex-shifted p4->p2->p1辅助循环 |
| PML/Robin/新DD/full-spectrum/75D/rank32 | 本机批次不实现、不扫描、不恢复 |
| 低内存实现 | fine及p4/p2 action matrix-free，转移局部/分布式；最底层小factor有严格cap |
| 小测试 | 一个合并的必要实现批次；不替代真实模型 |
| 准2D、沿y均匀特殊解法、模态中间区域、RCWA替代 | 禁止作为本任务求解核心 |
| 架构重写 | 不同时重写网格平台、全部JIT、MPI后端或切换有限元软件 |

**p4是一次有界的工程起点，不是文献证明的最优阶次，也不是提高阶次就能恢复波长鲁棒。** 本轮要明确验证其完整组合；失败则准确关掉此候选，不通过改p、sigma或inner上限连续抽签。

## 3. 物理和输入身份

### 3.1 A2原始锚点

| 项目 | 冻结值 |
|---|---|
| 周期单胞 | x/y=50/25nm，z=-10…130nm |
| grating | x宽17nm，y宽25nm，高120nm；原始boundary-fitted结构 |
| 材料 | air n=1；Si n=0.999002304859+0.00182649365i；mu_r=1 |
| 入射 | 真空13.5nm，grazing1°，azimuth0°，s，电幅值1 |
| fine FE | complex128，Nedelec degree6，target h10，hexahedron |
| 边界 | dual Floquet；原始Fourier-DtN，完整动态mode及quadrature |
| 历史行数锚点 | storage173802；不当作独立DoF |
| 历史模板input SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| physical model SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |

模板为`input/templates/full3d_iterative_example.dat`。新solver参数必须写入新的显式dat或版本化profile并进入resolved config；**新input SHA重新计算，不硬填旧模板hash**。physical/mesh/mode/源身份应保持等价；若schema扩展，逐字段桥接而不是追溯重定义历史hash。

规划新入口为`input/task39extra/original_13p5nm_p6h10.dat`与`input/task39extra/nonseparable_13p5nm_p6h10.dat`；首次实现时创建。不要将solver参数藏在一个task-numbered runner中绕过dat。

### 3.2 A3非可分结构

沿用原外部尺寸、网格、材料集合、入射与DtN。在原grating内，将cell中心满足`x>0`、`abs(y)<period_y/4`、`40nm<=z<80nm`的cell改为air，x/y坐标以单胞中心为原点。该recipe继承V19未执行的挑战，不声称是用户实际器件。

保存被改变cell的canonical keys、实际单元并集边界及原/新材料tag。证明该分布同时破坏y均匀和z挤出；选空或未破坏不变性是实现错误，不能静默调整到更容易的结构。

对于后续h细化，**以A3已解析出的实际材料实体并集为冻结几何**，对其进行boundary-fitted细化；不得重新按另一网格中心筛选出不同形状后称作h收敛。

本轮验证cell-wise非可分材料，不等于已覆盖任意曲面/拓扑；通用三维目标保持，复杂网格能力在工作站阶段逐步扩展。

## 4. 主候选的数学合同

### 4.1 不变的fine算子

```math
A_f=K_{{\rm curl},6}-k_0^2M_{\epsilon,6}+T_{{\rm DtN},6},\qquad A_fu=f.
```

沿用exact split action和streaming DtN。所有PC步骤只能产生修正方向，不能改变A_f、f或使用辅助残差代替true residual。

### 4.2 相容物理中间层

在同一物理网格构造Nedelec p4空间，保留完整材料。令`P_64:V4->V6`为合法primal延拓，dual限制为`P_64^H`：

```math
A_4=P_{64}^H A_f P_{64},\qquad g_4=P_{64}^H r.
```

初始实现可以使用composed action；若使用独立p4积分实现降低成本，必须以同一quadrature定义核对上述Galerkin作用。physical volume、mass和DtN分别比较。p4的外部mode集合不能改成较小的auto集合；fine和中间层通道key、normal/sign/normalization必须一致。

传递不得形成全局稠密矩阵，不存persistent FE-sized Z/AZ库，不做数值allgather。MPI1阶段也须用明确owned/primal/dual接口，避免后续靠复制整个全局向量并行。

### 4.3 shift仅存在于内部辅助方程

令`W_4`为权重`max(abs(epsilon_r),1e-12)`的正质量矩阵。定义：

```math
\widehat A_4=A_4-i\sigma k_0^2W_4,\qquad \sigma=0.5.
```

该符号按`exp(-i omega t)`约定的辅助吸收解释，实际仓库约定相反时使用对应符号并在manifest记录；这不是允许符号扫描。

采用同网格相容p4->p2->p1传递，辅助粗算子由Galerkin作用定义：

```math
\widehat A_2=P_{42}^H\widehat A_4P_{42},\qquad
\widehat A_1=P_{21}^H\widehat A_2P_{21}.
```

p1只解**移位辅助问题**，不声称p1已解析真实传播。sigma=0.5是冻结研究值，不从未取得全文的预印本推定最优，不自动调整。

### 4.4 辅助V-cycle的具体定义

p4和p2各用零初值开始的pre/post固定3步FGMRES处理当前辅助残差；其内部只用对应正定curl-plus-mass对角尺度进行Jacobi预处理。不能把SPD Chebyshev谱区间直接用于不定A。预平滑后restrict残差、调用下层、prolong correction、再后平滑；一次cycle，不重复增加次数。

最底p1允许现有MUMPS小问题作为本机development coarse solve，但同时满足：实际factor矩阵总行数<=4096（包含端口增广或保留的约束行，独立rows另报）、symbolic预估与实测全工作集在本机cap内、该矩阵+factor预算<=512MiB。不能因超限提高4096，也不能在工作站继续把p1膨胀为百万行global direct。最底层direct存在时，必须标记`bounded_development_coarse_factor=true`，禁止宣称factorization-free。

无需额外装配p6正定矩阵。p4/p2保持matrix-free；p1显式矩阵仅限上述辅助小问题。加法积分块应顺序编译、正确累加、边界约束只施加一次，积分metadata冻结，不能降低quadrature来压编译内存。

### 4.5 真实中间方程的有限求解

对`A4 e4=g4`使用right FGMRES，以一遍上述shifted V-cycle为PC：restart12、max_it36、相对true residual目标1e-2、零初值。每次内层结束都对A4显式计算该残差；零右端直接返回零，不除零。达到目标可提前终止；36步未到目标但finite且无breakdown时仍返回有限近似解供外层使用，记录为`INEXACT_INTERMEDIATE`，**不因一个内层未到目标自动否定整个外层**。

必须保留实际A4 residual、迭代数、shifted-cycle次数和耗时。不能报告`widehat A4`的残差冒充A4残差，不缓存基于历史RHS拟合的解来绕过fresh。

### 4.6 完整PC的pre/coarse/post与有限残差接受

设S6为已资格化positive p6->p3->p1的一次辅助cycle。其既有positive p1 factor与新shifted p1 factor不是同一矩阵，不得误共享或漏记；每个factor均受4096总行/512MiB限制，两个层级的全部同时存活对象计入总cap。原实现对p6/h10的限定若需适用于h5，必须按新配置核对，不能把旧资格自动外推。它不再独立承担全局物理解，只作为pre/post候选方向。每次PC输入q，初始化`z=0, r=q`，执行：

```text
1. d = S6(r)                     # positive预修正
2. 对d作当前fine真实残差的一维MR接受，更新z,r
3. e4 = bounded_FGMRES(A4, P64^H r, PC=shifted_cycle)
4. d = P64 e4                    # 全局物理中间修正
5. 对d作同样MR接受，更新z,r
6. d = S6(r)                     # positive后修正
7. 对d作同样MR接受，返回累计z
```

对每个候选d，计算`w=A_f d`，在w非零时：

```math
\alpha=\frac{w^Hr}{w^Hw},\qquad z\leftarrow z+\alpha d,
\qquad r\leftarrow r-\alpha w.
```

使用稳定缩放/复内积；zero RHS返回zero，zero direction跳过并记录；nonfinite停止。若数值上出现不可分辨的小分母，必须用明确machine-precision规则拒绝该方向并记录，不临时拟合alpha上限。每次PC只有这三个方向，不保存跨调用增大的投影空间。

必须报告raw单位步长rho与接受后的rho、alpha、方向范数和pre/coarse/post成本。MR不能增加空间所没有的信息，不能用“rho不增”声明鲁棒。输入q通常是外层Krylov向量，不要在代码中硬编码成物理RHS。

这一步使PC一般为非线性映射，外层必须FGMRES。它与V17失败的p3单位步长一次coarse修正、V18 standalone positive pMG、Task040 side bare-F及V19 PML双扫都不同；区别必须在response列明，而不是只说“p4更高阶”。

## 5. 主求解参数与性能预算

| 项目 | 本机冻结合同 |
|---|---|
| 外层 | right FGMRES，restart32，max_it512，zero start |
| 成功残差 | 原始fine `norm(f-Au)/norm(f)<=1e-6` |
| 真残差频率 | 每32步、退出前显式重算；需要时提前检查近收敛 |
| 中间层 | A4，restart12，max36，target1e-2 |
| 内部shift | sigma0.5，辅助p4->p2->p1，一cycle，p4/p2 pre/post各3步 |
| fine pre/post | 原positive一次cycle，各一次；不扫描平滑器 |
| 外层solve wall | 3600s硬性能预算，含所有内层工作 |
| 单case完整workflow | 7200s，含冷构建、setup、solve、release、postprocess与checker |
| early stop | nonfinite、真正breakdown、输入/算子错误、资源/监控失败；不设one-apply rho的外层入场门槛 |

这些数字是研究投入上限，不是数学不可能性定理；到限分类`PERFORMANCE_CONTROLLED_STOP`或`ITERATION_BUDGET_EXHAUSTED`，不得加到几万步。fine/intermediate/shifted/bottom所有迭代和A作用都计数，不能只用outer steps比较效率。

如单次PC成本很大，必须在运行中的stage heartbeat显示实际内层进度，且总wall watchdog能够终止完整进程范围；不等一次巨型PC返回后才发现已超预算。日志只写摘要与小计，避免每个内层向量都导出成巨大JSON。

## 6. 本机16GB资源合同

**16GB是整机资源，不是进程可占16GB。旧2GB仅作为本任务的stretch/reference指标，不是A2/A3入场硬门槛。** 本任务允许在以下实际安全线内证明真实求解：

```text
effective_total = min(可见物理RAM, 可读取的有效cgroup/容器memory limit)
reserve = max(4 GiB, 0.15 * effective_total)
launch_cap = min(12,000,000,000 B, effective_available - reserve)
warning = 0.85 * launch_cap
```

`effective_available`同时考虑MemAvailable、cgroup当前占用与限制，缺少某口径明确标注，不把宿主2TB当本进程可见16GB。cap非正则不启动。运行中同时监测系统余量，不能只依赖启动快照。

所有RSS为同期process-tree/cgroup包含MPI worker、Python parent、FFCx/gcc/cc1及后代；PSS另记不替代RSS。swap使用量和活动须满足该专用运行范围zero-swap，系统已占用swap不得伪写成程序swap0；具体scope写清楚，异常则停止。一次一个heavy，不与Task040/其他任务并行占机器。

编译子进程必须在watchdog范围内，worker退出后继续观察至后代清场和cache稳定。不能用脱离进程组、预热未记账或删除编译监控制造pass。允许hash/ABI/form一致的cache复用，但分开报告cold setup与warm solve资格。

有限最底层factor、可选诊断reference以及后处理全部使用同一实际cap。若资源不足，保留`RESOURCE_BLOCKED`，不得下调真实p/h或删除mode继续冒称同一模型。

## 7. A0–A5：连续执行，到真实结果再集中审阅

### A0：窄继承与预检

核对remote/local branch、HEAD、base ancestry、upstream、worktree clean和canonical clone登记。读取本任务三文档及变化过的source，不再次写十几页全历史继承报告。确认Python/DOLFINx/Basix/PETSc/MPI同一ABI、complex128、IntType、线程1、实际可见内存、swap、disk、watchdog。当前在本机CPU环境，不要求安装GPU栈或升级库。

A0完成后直接实现A1，不停下来等review。出现缺文件优先沿已有索引修正路径；不能用猜测补材料、mode或历史SHA。

### A1：一批必要实现检查，原始规模结构检查

实现通用物理中间层/shifted cycle、dat adapter和增量ledger。优先复用`src/solvers/fullspace_memory_first_krylov.py`、same-mesh transfer、exact physical action、streaming DtN和recovery。不要复制V19的1510行R0 runner或再建一个几千行单任务框架。

允许一个合并tiny fixture检查复dot、P/PH、slave语义、A4 Galerkin作用、shift符号/作用和MR公式；transfer/physical relative目标1e-10，shift组合1e-11，zero/finite/repeat1e-12。对原始p6网格做实际rows/metadata/底层容量计数，并以少量合法向量检查新传递和中间action，不跑新的positive-only四源campaign。

tiny使用同一生产实现，不用mock矩阵代替所有物理检查。旧实现未变的昂贵Gate不重跑。至少在第一场PDE前提交prototype，记录完整源码SHA，禁止dirty worktree正式运行。

p4独立form实现若与composed不符，先修明确metadata/约束错误；不得容差放宽。当前p4表示的phase/材料局限在manifest写明，不要求先做一项新的大LFA研究才能进入A2。

### A2：第一场外层PDE就是原始p6/h10模型

按新dat、zero start、§4–6合同运行。周期日志不断落盘，求解成功立即保存最终解、释放后恢复全部物理输出。不得只交付A2-PC-apply-pass后停审，也不额外做checkpoint continuation再fresh的两次同方法运行。

报告基线V18时使用历史曲线，不重跑长程positive基线；不同restart和时间口径写明，不能仅按迭代数声称严格speedup。

### A2R：至多一次、仅用于分清中间逆与空间问题的诊断

仅当A2未达目标且记录显示A4内层精度不足/成本为主要疑点时允许。保持A_f、P64、A4和pre/post/MR/外层参数全部不变，只把A4近似解替为高精度直接reference，目标true residual<=1e-10。禁止把A_f本身直接求逆用作PC。

A4 reference须先做一次实际symbolic容量预审，总工作集在§6 cap内。可用精确端口增广避免显式dense DtN，保持A4方程等价；超过cap则`REFERENCE_RESOURCE_BLOCKED`，不换另一阶次、不重开PML。最多一次原始模型外层reference运行，不给每个失败source单独构造oracle。

决策：reference也失败，只关闭本p4组合；reference成功而A2失败，登记`PHYSICAL_MIDDLE_REFERENCE_PASS_ITERATIVE_INVERSE_UNQUALIFIED`，不宣称生产PC成功。本批次不再扫描inner/restart/shift。为了尽早判定三维能力，reference若在cap内可用，允许A3沿用同一reference profile，但其结果始终是reference-only，不作可扩展资格。

### A3：同配置、同尺度非可分三维

A2或A2R有完整数值输出后，直接运行§3.2模型。使用成功的同一profile，不针对notch改任何算法参数，zero start，同预算。不得用准二维解析解、沿z模态传播或层平均材料替代三维core。

原模型通过而A3失败，明确记录`NONSEPARABLE_CHALLENGE_FAIL`；不能用原模型结果掩盖。A3成功只证明该非可分case，不宣称任意所有结构。

### A4：一个网格压力点和有限独立核验

首先查找并复用匹配物理/离散/通道/观察量的已有direct数组；只参数相近的旧scalar包不能当exact authority。若无匹配，可在安全预算内运行**至多一次原始模型的独立Full3D direct控制**，允许采用已有单元静态凝聚，但只能作reference，不作新PC；需确保同一fine离散与端口方程并显式核对原始残差。symbolic不安全则不执行，保留reference缺口，不循环尝试不同direct参数。

对A3的固定实际材料几何，规划一个p6/h5压力点。先做计数与资源预测；仅在底层cap和总体资源满足时进行setup/action与6次PC作用，完整solve仅在该预检支持时运行一次。若任一底层factor的4096总行或总cap不满足，标记`H_SCALING_BLOCKED_ON_16GB`并转A5，允许为工作站移交而结束，不为得到本机h点降低阶次、损耗或几何复杂度。

若fine h5真的求解完成，比较迭代/DoF、memory/DoF、每次PC成本、E/H/功率。单个h细化点只能称趋势证据；不能宣称渐近h鲁棒或连续精度已完全收敛。

### A5：收口和工作站移交包

整理全部模型表、失败/未运行项、运行身份、原始日志hash与当前源码。A0–A5之间不逐步等review，只有terminal failure或A5结束才提交`response_v1.md`集中审阅。

主实验数量上限：原始iterative一次、条件A2R一次、非可分一次、条件h5完整解一次、条件独立direct一次。明确bug修复后的重跑须保留旧证据且只重跑受影响项；数学失败不算bug，不重新抽签。所有未触发条件的case写not_run，不能为了把表填满而运行。

## 8. 数值、物理与输出Gate

### 8.1 数值

原始fine true residual<=1e-6；KSP reported norm与true norm使用同一归一化后核对。差异超过`max(1e-10,0.01*true_relative)`须调查，不能仅靠KSP reason宣称通过。小于machine-level的绝对差按记录解释，不忽略真实失配。

任何known nullspace/zero RHS使用明确规则，不制造除零。PC不能修改输入向量；repeat、约束、finite、orientation和mode identity有compact证据。

### 8.2 物理与参考比较

| 内容 | 要求 |
|---|---|
| 输出 | complex E/H、相同采样坐标的near-field、R/T/A、A_volume、全部真实mode功率与复幅值 |
| 独立能量 | abs(R+T+A_volume-1)<=1e-5；abs(A-A_volume)<=1e-5 |
| 被动性 | 有限、通道求和正确；数值微小负值与真实符号错误分开 |
| matched同离散direct E/H | 相对L2<=1e-4，近零值另报绝对误差；不拟合全局相位 |
| matched R/T/A/A_volume | 绝对差<=1e-5 |
| matched显著通道功率 | 绝对差<=1e-6；全部通道也输出，不只选择好看的 |
| matched复幅值 | 向量相对L2<=1e-4，近零通道加绝对差 |

上述比较容差是本任务工程验收标准，不是连续误差定理。没有匹配独立数组时记录`AUTHORITY_LIMITED`，不能伪造；可取得数值/输出资格并移交进一步开发，但不能称完整精度资格。

沿用历史12个显著通道列表时，要逐key核对是否在当前inventory；缺失记`not_present`，不能补零或改变mode选择。非可分模型可能激发新的n不等于0通道，必须包含，不可只输出旧二维风格切片。

h变化时RTA/场差异用于离散精度，不要求两张不同网格的解满足same-discretization的1e-4；必须另给误差趋势和参考限制。

### 8.3 保存和释放

每32步写`cycles.jsonl`：真实残差、外层步数、fine/intermediate/shifted/bottom计数与wall、pre/coarse/post贡献、资源。每128步写solution-only checkpoint；成功、性能停止及用户停止安全边界，无论是否128整倍数，都保存最终/最后解和true residual。

硬资源终止优先；不能为了保存而越cap。信号handler只置位，不在其中执行MPI/PETSc。最终流程：保存最小recovery packet -> 销毁outer/inner KSP、PC、无用matrix/factor -> 记录RSS下降 -> E/H及RTA恢复。所有输出在统一资源范围内。

## 9. 状态与停止条件

| 状态 | 含义与下一步 |
|---|---|
| `IMPLEMENTATION_BLOCKED` | 输入/映射/算子错误未闭合，不评判方法数学有效性 |
| `RESOURCE_BLOCKED` | 当前可见机器预算不足，保留阶段和对象账本 |
| `EVIDENCE_INCOMPLETE` | 源码或进程尾段等不能闭合；不得标formal pass |
| `NUMERICAL_FAIL` | 同一合法系统在冻结迭代上限没有达到目标 |
| `PERFORMANCE_CONTROLLED_STOP` | wall预算停止，不等于永远不收敛 |
| `REFERENCE_ONLY_PASS` | 高精度中间reference成功，迭代中间inverse仍不合格 |
| `DISCRETE_SOLVER_OUTPUT_PASS` | true residual和输出通过，参考/精度/扩展性另列 |
| `LOCAL_13P5NM_3D_READY_FOR_WORKSTATION` | 主iterative profile在原始与非可分case均通过数值/输出/本机资源；独立reference及h证据列明；不等于0.7nm通过 |
| `REFERENCE_ONLY_HANDOFF` | 仅A2R及其非可分reference通过；允许移交机制证据，但不能声称主iterative候选已可用 |

终止后不自动切到PML、FFT背景、全局direct PC、另一粗阶次或另一Krylov。下一版review只能根据精确failure机制选择变化；本任务的失败不建立整个Full3D iterative不可能性结论。

## 10. 迁移工作站后的0.7nm路线

以下阶段是明确roadmap。只有用户实际迁移、W0环境确认及最新review冻结每个波长的dat/材料/预算后，才启动对应heavy；不让Codex在本机直接追到0.7nm，也不承诺无条件成功。

| 阶段 | 目标 | 通过什么后继续 |
|---|---|---|
| W0 | 同源码/输入在工作站复算13.5nm原始与非可分case；核对实际RAM、NUMA、MPI/线程、ABI | 原始可观测量与本机一致，zero-swap、process-tree闭合 |
| W1 | 先5nm，真实非可分case；同波长至少两个有意义离散；复用Task039压力记录但不混淆10°与1° | solver、field、orders、体吸收与精度趋势；不是只跑旧coarse网格 |
| W2 | 消除随N增长的底层direct瓶颈；分布式/有界coarse与优化matrix-free；建立至少3个实测规模点 | 不能用全局直接coarse兜底；内存和总工作模型有校准 |
| W3 | 2nm或1nm中的一个必要中间点，再0.7nm受控规模的全三维非可分PDE | 对应材料、通道inventory、误差资格与容量预检，不做准2D替代 |
| W4 | 0.7nm目标尺寸非可分三维，几何/材料拓扑逐步扩展 | 完整physics/numerics/resource/provenance联合Gate |

W2与W1的工程准备可交错，但不得在未解决底层cap时用更大机器把global direct coarse无界放大。若5nm已经出现明显算法退化，应先定位物理中间层表示还是内部inverse，不能继续缩波长堆预算。

中间波长不是必须凑齐13.5/10/5/2/1/0.7六点；只用能够隔离尺度变化的最小集合。0.7nm受控规模仍保留三维材料变化与矢量Maxwell，只缩总体规模，不做准二维/可分离假设。

### 10.1 2TB容量模型

使用实际MemTotal定义预算，报告decimal TB和TiB，不允许单程序占满整机。工作站上限暂以`min(0.80*effective_total, effective_available-reserve)`规划，具体watchdog在W0按机器与系统余量冻结；0.8是规划保守线，不是实测RSS。

必须建立：

```text
正式波长材料 -> actual external channels -> accuracy-qualified h/p
-> independent FE/trace rows -> fine/intermediate/auxiliary memory
-> all simultaneously alive Krylov -> coarse maps/factors -> DtN work
-> setup/compiler -> solve -> recovery/postprocess -> process-tree peak
```

对1e9复未知量，FGMRES32仅基向量模型已约1040GB，尚无任何FE/PC；所以本机restart32不承诺作为0.7nm固定配置。工作站必须按有效PC与容量重新资格化短重启，不能只扩大restart。任一p1底层factor的cap一旦触发，必须改成有界局部/分布式多层求解，而不是取消cap。

所有规模预测明确为derived/predicted，注明指数、校准点和不确定性。至少区分实际材料、网格精度、外部通道、local inverse、global coarse、DtN、MPI复制七类blocker。旧256GiB no-go不直接当2TB no-go。

## 11. 允许改动、提交与证据

数值核心进入通用`src/solvers/`模块；dat/schema只增加必要profile与三维材料recipe入口；runner负责运行/监控，checker只读raw重算。沿用现有positive、transfer和postprocess，禁止无关BLAS/系统重装、历史目录清理和整库重构。

建议提交序列：

```text
1. feat(maxwell): add opt-in physical intermediate and shifted auxiliary cycle
2. feat(runner): connect dat, final solution, incremental ledger and lifecycle
3. evidence(task39extra): record original and nonseparable 13p5nm results
4. docs(task39extra): close local batch and prepare workstation handoff
```

前两项可合成一个可说明的prototype，但必须在正式PDE前有clean SHA。每次改动只跑targeted tests；阶段收口跑task-focused suite，完整repo suite最多最终一次且不得伪称未执行为pass。没有CI就只报告本地测试。

每次正式运行必须保存：`input_original.dat`、`resolved_config.json`、`run_manifest.json`、`input_sha256.txt`、`physical_model_sha256.txt`、`source_sha.txt`、`run_summary.json`，外加网格/tag/mode/ABI/MPI/线程、profile全部参数、resource timeline与artifact hashes。

新任务outcomes只需少量中心文件，不再每个小T生成一套平行文档：

```text
outcomes/summary.md
outcomes/records/run_index.json
outcomes/test_summary.md
outcomes/workstation_handoff.md
response_v1.md
```

重型mesh/field/basis/factor/timeline只在ignored artifacts，Git保留轻量索引和摘要。正式PDE或受控负结果后同步更新`docs/development_progress.md`与`docs/development_model_registry.md`，保留保护区。不得修改Task038-extra旧review/response/outcomes来获得新通过。

`response_v1.md`至少报告：branch/base/final SHA、worktree/测试、哪个完整case已运行、原始/非可分/网格/参考的独立结果、主profile与A2R区别、fine与各内层真实残差/计数/时间/内存、输出与reference限制、stage-specific停止原因、最底factor扩展缺口，以及是否已经满足本机移交条件。

## 12. 最终执行原则

**本机阶段的首要成果是：在安全内存内，用同一完整算法得到13.5nm原始和非可分三维问题的真实场，而不是又完成一串辅助PASS。之后按明确移交和容量Gate向0.7nm推进。**

这份任务书是有限候选的研究合同，不是收敛保证。它让失败能够区分为物理中间空间、内部近似逆、实现、资源或精度问题，并限制重复试验成本。没有最终review和用户授权，不merge master；成功也不把13.5nm fixed-case提升为0.7nm任意三维production资格。
