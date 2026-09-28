# Task042：神经辅助低内存 p4 粗逆首轮试验

## 0. 身份、授权与要消除的 blocker

```text
task_id                  = Task042
repository               = Rookie1234567/MyFEniCS
execution_branch         = task42_neural_coarse_inverse
upstream                 = origin/task42_neural_coarse_inverse
base_branch              = task39extra_para_workstation_capacity
base_SHA                 = ccd357885f7f9be84efe3be07868cc94f13d93fc
base_latest_commit       = docs: hand off running 2nm workstation evidence
base_latest_review       = docs/task39extra_para_workstation_capacity/review_report_v5.md
base_latest_response     = docs/task39extra_para_workstation_capacity/response_v5.md
base_running_source_SHA  = 64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa
created_date             = 2026-09-28
execution_root           = /home/fenics/Projects/NN-Lab
task_directory           = docs/task042_neural_coarse_inverse
status                   = PLANNED_NOT_RUN
response_required        = response_v1.md
master_merge             = NOT_APPROVED
```

**Blocker：Full3D 的细层作用已经可以不物化全局 p6 矩阵，但当前准确 p4 粗逆仍依赖增长型全局 LU；它同时占据大量内存，并在每次 BAL_H 预条件中反复调用。** 本任务研究能否以低内存迭代粗逆替代该因子，并由学习模型改善难消除的误差。目标仍是约 2 TB 整机物理内存内的 0.7 nm、任意非可分三维周期单胞 Maxwell。首轮只验证一个小规模固定算例，不承诺完成目标规模，不宣称通用神经求解器。

这里的“神经网络代理”是**求解器内部的粗逆/误差修正代理**，不是参数到 R/T/A 的黑盒，也不是 PINN 替代全部 Maxwell 方程。先比较传统低内存基线、线性降维基线和一个神经候选；神经模型没有额外收益时必须如实报告。

用户本轮明确要求 ChatGPT 新建 task42xxx 分支并写入任务书，故本次分支创建是对通常“Codex 创建执行分支”的一次性明确覆盖，不修改根治理规则。本任务明确选择上述研究分支的冻结 SHA 作为 base，而不是 master；这是继承已存在的 p6/p4 作用、凝聚和验算接口，不是批准整体合并研究代码。旧任务的“不得开发新迭代法/不得使用 GPU”只约束旧任务；本任务在下述有界范围内单独授权开发与离线训练。不得改写旧证据或接管旧运行。

## 1. 必读依据与历史边界

先读根 AGENTS.md、docs/AGENTS.md、docs/repository_work_principles.md、docs/markdown_rendering_standard.md、相关目录 AGENTS、本任务 README/task 及本目录以后出现的补充任务书和最新 review/response。不得把其他任务的执行顺序继承为 Task042 的待运行命令。

| 依据 | 应取得的信息 |
|---|---|
| base 中的工作站 task.md、最新 review_report_v5.md、response_v5.md、outcomes/summary.md | 正确区分成功参考、当前运行和已被覆盖的旧合同 |
| docs/task39extra_para_workstation_capacity/outcomes/f2_running_handoff_20260928.md | 运行 source 不同于文档 HEAD；p4 因子、C、端口缓存和监控边界 |
| docs/task039_extra_physical_multilevel/outcomes/summary.md 及 balanced_coupling_v5.md | 原物理 coarse 与正定 smoother 的区别；原始/非可分资格范围 |
| src/solvers/physical_balanced_coupling.py、physical_inexact_balance.py | BAL_H 的实际调用和精确/非精确粗平衡区别 |
| src/solvers/p4_cell_condensed_inverse.py、p6_cell_condensed_action.py、physical_retained_fgmres.py | 任意 RHS、内部恢复、累积端口状态、原方程检查和外层空间 |
| src/runners/physical_retained_condensed_v20.py；相关 physical_* runner/profile | public adapter 到真实算法的调用链、旧 source 白名单及资源限制 |
| src/test/test_task039extra_v20_noncommuting_contract.py 及 p4 ledger tests | 凝聚不与 p 传递、curl/mass 分别凝聚交换 |

旧神经分支只读参考固定为 `ChatGPT/20260715-para-task-neural-local-pc` @ `d91652dd2d611d6d6bedd10e677c3f7030c07d4f`。读取该 SHA 中 PARA-Task001、004、005 的 task、最新 review/response 和 outcomes/summary，以及实际复用的模型/捕获/teacher 接口；不要整体 merge/cherry-pick。若某文件不存在，列出实际文件而不猜造。

必须保留的历史教训：Task001 单 slab ILU+NN 迭代改善很小且整体更慢；Task004 全16 slab exact two-step 有局部求逆改善的全局正信号，但这不是所有 learned PC 的数学上限；Task005 局部质量/模型微基准有正信号，完整 model+basis+private audit CSR 超预算，后续全局集成未运行，非线性模型未明显胜过线性。不要重复“旧 ILU 常驻，再附加一个 NN”的默认路线；也不要把新的低内存收益错误归给神经网络。

基线事实仅作历史 measured：2026-09-28 10:34 UTC+8 的 2 nm 快照尚未收敛，原 A6 残差约 0.02236，过程树 RSS 约 1.151 TB；p4 numeric 后端 used 数据约 916.7 GB，不是独立因子 RSS；两次 C 约 1371 s，但 MatSolve/恢复/原 A4 验算内部份额仍 unknown。PSS 高频扫描已有干扰旁证但无关闭对照。上述记录不能当作此刻的实时状态，也不能直接用来预测 Task042 加速。

## 2. 目录、Git、环境与共享硬件隔离

### 2.1 独立工作目录，不操作旧工作树

`/home/fenics/Projects/NN-Lab` 本身是 Task042 仓库工作树根目录，不再嵌套另一个 MyFEniCS。使用已登记 canonical Git repository 的 linked worktree。交接记录中的 common Git directory 是 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，须现场确认存在、origin 和 worktree list 后使用；该路径是既有记录，不是本任务已经完成的现场核验。

只 fetch 本分支，登记新 worktree 并建立 upstream；若路径非空、分支已在另一目录检出、origin 不符或 SHA 非预期，停止受影响步骤并报告，不删除或强制覆盖。不得在旧工作树 checkout/switch/reset/stash/clean/pull，不改其 HEAD/index/文件。worktree 共享 Git objects/refs/config，不共享各自 HEAD/index 和源码工作文件；因此也不得擅改共享 remote、全局/仓库级默认配置、运行 gc/prune/repack。只允许本分支 upstream 的必要配置。

正式提交与推送都在 NN-Lab；使用精确 refspec `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。不创建其他远程执行分支、不 amend、不强推、不合并 master/其他任务。既有 research 代码只是继承背景；Task042 新变化只留在本分支。

### 2.2 环境隔离

先只读盘点原生 Linux、Python、FEniCS/complex ABI、MPI、BLAS、GPU 驱动和现有 ML 环境。不安装 WSL，不修改系统 alternatives/驱动/CUDA，不在旧任务 .venv 或 library prefix 中 pip install/upgrade，不复制正在使用的大 factor、场或缓存。

在 NN-Lab 内建立 task-local activation 和必要的独立 FE/ML 环境。可只读复用已验证的原生库前缀，但 FE 和 ML 优先分进程/分环境，通过有 hash/schema 的数组 packet 交换。不得因为 PyTorch 依赖把另一套 MPI/BLAS/PETSc 动态库注入 FE 进程。所有本项目 src 模块必须从 NN-Lab 导入；记录 sys.executable、src.__file__、关键模块路径及实际 loaded-library 路径。

旧 activation 含工作站特有 prefix/临时路径，不能在新 worktree 盲目 source 后宣称环境通过；新脚本须显式配置前缀并完整核验 complex128、IntType、DOLFINx/Basix/FFCx/MPC/PETSc/mpi4py 的兼容性。64-bit 工作站 ABI可保留，不能为接模型擅自重装它。没有现成可用 ML 栈时，只允许隔离环境内固定版本的最小依赖准备；需提权、认证或系统级变更时报告，不等待密码、不索取 secret。

results、benchmarks/artifacts、TMPDIR、FFCx/JIT、Python bytecode、Matplotlib、Torch、模型下载和训练缓存全部重定向到 NN-Lab 独立 ignored 目录。不得写回旧目录或通过 symlink 隐藏共享写入。缓存/数据/权重不提交 Git。

### 2.3 并行开发不等于允许并行 heavy

两条线可同时读写各自代码、文档和做真正轻量测试；**同一工作站一次只运行一个 heavy case**，包括 FE/JIT、teacher factorization、大批数据生成、持续 GPU 训练和完整后处理。

如果 Task39extra F2 或其他 heavy 仍运行，Task042 只做文档、静态检查和有界 pure-array 小测试：整树 RSS 不超过 2 GiB、数学线程1、不使用 GPU、不触发 FE JIT；选择不与已有 worker/监督器共物理核心的空闲 CPU。若现场状态无法可靠确认，按有 heavy 处理。完成可做部分后写 `WAITING_FOR_SHARED_WORKSTATION` 并交付，不写无限等待循环或后台自动启动器。

进入下述数值阶段，须取得同一机器级 heavy lock，并独立检查已有进程树，因为旧任务未必使用相同锁。只读用已有短日志、PID/start_ticks、status 和轻量资源查询；不得扫描邻任务巨大 resources 全文、重复读取 smaps/numa_maps、热修改其 watchdog、kill/暂停它，或卸载其模型/因子。

工作站空闲后的 Task042 固定预算：整树 RSS hard=16 GiB、warning=12 GiB；GPU 单卡峰值上限 8 GiB（仅训练或已资格化推理，任一时刻一个任务）；MPI1，OMP/OPENBLAS/MKL/NUMEXPR/BLIS等数学线程1。现场 effective MemAvailable 在启动前须至少保留 max(128 GiB, effective_total 的10%)，另加本任务16 GiB预算；磁盘自由量不少于50 GiB，artifacts 总量上限20 GiB。先作尺寸/内存模型，不能依赖 OOM 探容量。

任务自身 swap 必须为0，禁止 OOC。全机 swap 计数只是诊断，不能将邻进程的变化归罪 Task042；有真实系统压力则不启动。尽量使用已验证的低扰动 process-tree/cgroup watchdog，记录实际执行范围；不能只监测启动 shell。触线或监督持续失效，仅停止本任务后代并保存原因，不更改全机 swap/governor/CPU/NUMA 策略。新的重型阶段不得与 teacher/训练进程重叠驻留。

## 3. 首轮冻结模型和数学边界

### 3.1 一个固定模型，不做短波和几何扫描

物理与离散种子是 base 中 `input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat`，blob=`0c5211a0e99b4f1b74ad5e4223b5d91066b57816`。只读取其物理/离散定义，为 Task042 创建独立 dat/profile；不启动旧 profile 的容量 campaign，不抄旧硬编码 source gate。

| 身份 | 首轮冻结值 |
|---|---|
| 模型 | original rectangular block grating；Full3D，不是 Hybrid |
| 周期/高度 | x/y=50/25 nm，z=-10..130 nm，interface z=0 |
| 光栅 | x/y宽17/25 nm，高120 nm |
| 材料 | air n=1；Si n=0.999002304859+0.00182649365i；mu_r=1；epsilon=n*n |
| 入射 | 真空13.5 nm，grazing1度、azimuth0、s、幅值1 |
| FE | 六面体、boundary_fitted h10、Nédélec p6；同网格物理 p4 |
| 边界 | x/y双Floquet、layered background、完整auto_propagating Fourier-DtN；无PML |
| fine outer | retained/trace+port FGMRES RIGHT、restart32、max2048、zero start；同一候选间保持一致 |
| 参考含义 | p6原方程离散参考；不是网格收敛或0.7 nm资格 |

历史规模锚点为252 cells、p6 storage173802、p4 FE storage53084、80外部通道；必须从当前实际mesh/mode对象核对，不用硬编码强填。首轮上限为p6 storage200000、p4 full+port rows60000。数量/几何不符时先解释版本差异并停止规模推进，不能自动改到h7.5/990 cells或短波。

冻结真实轴坐标、cells/material tags、全mode keys/相位/归一化、积分规则、MPC canonical映射、physical SHA及输出采样。三类候选只改变p4求逆实现；fine A6/b、p4物理方程、H6数学作用、P/P^H、DtN库存、材料和输出点完全相同。已有等价快速作用可以复用并配对核验，但不得为候选省时减少模式或积分阶数。

### 3.2 精确算子、近似预条件和严格粗返回分开

fullspace层面原物理关系为：

```math
A_4=P^H A_6P,\qquad C=P A_4^{-1}P^H.
```

首轮保留 BAL_H 和每次粗返回的严格精度，把 p4 的全局 LU 替换为**以原 A4 为算子的内层 FGMRES**；网络只在这个内层的 PC 中。内层返回须通过原 A4 相对残差1e-10及独立端口/恢复检查，之后才能交给外层。不是把一个误差百分之几的 NN 输出直接塞给旧精确 coarse ledger。

不得假设 `P_trace^H S6 P_trace` 就是凝聚后的 A4。在fullspace或独立凝聚p4路径上任选一种经过验证的实现并在F1冻结；真实A4、内部RHS、primal/dual、slave-zero、完整累积port状态必须一致。新backend使用清楚的inverse protocol；不得绕过 `P4RefinementLedger` 的类型/因子专有合同，也不为适配它伪造MatSolve次数。新增独立的迭代粗逆验证器及最小测试，原LU路径保持原行为。

A4中物理复质量、负号和DtN不变；带吸收/正定辅助作用若用于PC必须单独命名，绝不代替原A4检查。首轮不开发宽松的 inexact BAL_H，也不改精度门槛来迁就模型。

## 4. 实验设计：先找到能被学习的修正，再部署

### F0：隔离与接口准备

完成Git/目录/环境/资源盘点，建立本任务文件与最小pure-array tests。检查旧神经分支哪些接口确实可复用，列文件/blob/依赖；需要迁移时只作最小重实现或文件级迁移并复核，不继承旧absolute path、数据划分或在线CSR副本。若共享工作站忙，止于F0并如实交付。

### F1：小规模原算子与baseline

资源空闲后构造唯一冻结FE模型，先作A6/A4、传递、凝聚恢复和非零内部/端口RHS的真实组件检查。使用现有小规模准确 p4 LU仅作为离线teacher/数值与成本reference；各阶段顺序启动、退出清场，不与候选共驻留。

冻结一个非神经低内存内层PC B0：优先复用已有可验证的有界局部/多层组件，而非重写整套求解器。允许点/小block平滑、有界patch因子和有界粗空间；禁止global p4 LU、ILU参数扫描及隐藏同规模factor fallback。每patch行数<=6000、全部PC因子载荷<=512 MiB、最底粗问题<=2048行且其factor包含在同一512 MiB中；不得把“p1/p2/coarse”名称当成容量证明。冻结划分/overlap/次数，不逐次调整直到通过。

将B0对任意RHS的失败方向和真实迭代残差保存为训练设计依据。B0未收敛是可保留的baseline，不自动结束所有离线研究；但不得启动无界算法扫描。若已有同物理/同表示组件具备有效证据，优先复用，不重复历史大规模负实验。

### F2：teacher与低维可表达性oracle

按精确A4生成有界teacher对 `rhs -> correction`，记录每对原A4 residual。采样包括真实粗调用/内层Krylov残差，以及有固定种子的代数manufactured对 `rhs=A4*e`；后者仅为覆盖手段，不替代真实残差。细层参考场只用于最终验证，不作为初值/PC泄漏输入。

训练/验证/终测按独立seed和整段轨迹划分，不能将同轨迹相邻RHS随机切分后声称泛化。建议上限train1024、validation256、heldout256，每个完整problem单列；按32 RHS以内批次流式生成/读写，禁止一次保存全部大full-field解到RAM。teacher因子只在离线阶段存在，训练开始前确认释放。原输入、规范化、零RHS、复相位/幅值缩放、几何/DOF/端口身份都进入dataset manifest。

用真实teacher误差/修正建立POD或局部低秩基，最多比较rank16/32/64/128，basis+映射+在线buffers总预算<=512 MiB。先用非学习的投影/小矩阵最小二乘作为可表达性oracle，区分“该基不能表示难误差”和“网络训练不好”；这是离线诊断，不能借teacher在线求真解。若最高允许rank仍无可表达性正信号，记录 `REPRESENTATION_NEGATIVE`，不靠放大网络或增加global basis无界补救。

### F3：线性基线与一个神经候选

同一数据、同一表示和同一完整预算下，至少实现：

| 路线 | 作用与边界 |
|---|---|
| R-LU | 离线/小算例准确p4参考；不是候选在线依赖 |
| R-B0 | 原A4内层FGMRES + 固定传统低内存PC |
| R-LIN | 同B0与表示上的线性降维修正，作为必须超过的非神经对照 |
| R-NN | 同B0与表示上的一个小型神经修正；不保留原global p4 LU |

首轮优先让模型学习B0/粗修正后难消除分量的低维坐标，或patch/接口上的共享修正，不建立 `Linear(N,N)`。网络家族只选一种小型residual MLP，至多两个预先登记宽度（例如64/128）、两层hidden、固定seed、epochs<=300；固定同rank与输入归一化后与线性对照。总训练GPU/CPU有载时间预算2小时，是本任务资源上限而非ETA。选择依据只用validation；heldout一旦参与选型即标为consumed，不能再称终测。

训练loss应包含修正误差及真实/独立作用核验的方程残差，不能只优化投影残差后宣称全系统通过。固定算子的真逆是线性的；神经非线性不自动优于线性低秩映射，尤其相同输出子空间上不能宣称超越精确最小残差投影的下界。若线性胜出，记录 `LINEAR_BASELINE_PREFERRED`，保留神经负结果，而不是为了NN标签跳过对照。学习跨几何/材料的basis或算子生成器留待后续review决定。

首轮默认FE/外层/验算为complex128，模型参考训练及冻结推理使用float64实虚双通道，明确FP64成本；不静默用FP16/TF32或改FE精度。低精度推理另经后续资格，不属于本轮必须项。离线训练结束固定checkpoint，关闭dropout/随机性/online learning。优先CPU冻结轻量推理避免FE动态库污染；GPU模型微基准可在隔离进程做，但必须包含传输/同步，未经实际集成不得声称GPU求解提速。

B0承担未学习分量的全空间处理，不能只用秩远低于N的代理作为唯一右预条件而把搜索空间永久限在低秩像中。输入为raw/normalized residual而非旧ILU修正；没有ILU隐藏依赖。任何投影、基存储和全局粗解必须有容量上限，不能仅用一个大dense basis替代一个大factor。

### F4：严格p4逆验证，先看真实返回再看速度

冻结每个candidate，内层统一RIGHT FGMRES/restart32/max256/zero start；具体counter与每次原A4验算清楚记录。先测试至少16个未训练RHS，必须包含真实早期/后期残差、零RHS、复相位缩放、显式非零内部及端口载荷。全部非零RHS的原A4残差<=1e-10，零RHS按精确零处理；独立port closure<=1e-10，finite/约束/恢复通过。NN输出不要求单次到1e-10，但迭代粗逆返回必须达到。

不达标准或到256步则保存 `COARSE_INVERSE_NOT_QUALIFIED`；不偷偷调用全局LU补一次，也不继续p6外层。局部实现bug允许一次有明确诊断的修复重试；数值停滞不是bug，不能改restart/容差/shift反复试到通过。

每条通过路线做三次相同RHS组的独立进程计时，固定CPU、线程、冷/暖缓存定义与顺序，保存全部值及中位数。同时记录完整setup、PC apply、A4作用、恢复/port check、传输和生命周期；训练、teacher、模型加载及审核成本分别列出。模型microbenchmark不能替代完整严格粗逆成本。

### F5：条件的小规模p6嵌入，不跨过粗返回Gate

只有至少一个低内存candidate通过F4，且没有隐藏global p4 factor、没有额外private audit CSR、完整内存模型符合上限，才进入同一冻结p6问题的正式嵌入。小规模准确p4-LU baseline一次；R-LIN和R-NN各最多一次，且各自先通过F4。无通过candidate时不运行p6，只提交F0-F4证据。

每次正式FE计算必须经 `python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`。一个dat是一条明确运行，不藏扫描；组件capture/teacher的多RHS行为要显式写出stage、同一个物理operator和RHS inventory，不伪装多场正式PDE。必要dispatcher/profile新增为research opt-in，普通默认和旧source/whitelist合同不改变。

外层独立原A6 residual<=1e-6，所有原A4 coarse return<=1e-10，原BAL_H粗平衡/约束沿既有标准；无法精确返回就fail closed。与本轮baseline比较：canonical场L2/scaled-curl、selected复E/H和完整模态幅值相对差<=1e-4；R/T/A/A_volume绝对差<=1e-5；每通道功率绝对差<=1e-6；abs(R+T+A_volume-1)、abs(A_balance-A_volume)<=1e-5。近零使用既有绝对规则并报告，不拟合相位/重新归一化，不删通道。official结果只来自合格场。

求解结束先计算原残差、保存最小恢复packet，释放KSP/PC/因子和无用对象，记录RSS变化，再作恢复/后处理。teacher训练验证终态进程不得共驻留。首轮不运行notch/5/3/2/0.7 nm，不进行h/p/角度扫描；固定original的成功只能称固定离散首轮资格。

## 5. 怎样判断本轮有用

数值正确、资源改善、神经独立贡献分别判定，不合并为一个PASS。

| Gate | 本轮标准/解释 |
|---|---|
| G-identity | 相同物理/mesh/mode/A4/A6身份，ABI一致，source/输入/模型可追溯 |
| G-no-factor | 候选从构建起没有global p4因子；不得先建再释放后只测solve峰；有界cell/patch/bottom因子全部记账 |
| G-numerical | F4或F5各自全部真实残差/恢复/物理要求；明确哪个阶段通过 |
| G-memory | 完整process-tree峰+GPU峰合规；相对R-LU峰RSS降低>=20%才称本pilot的memory positive，其他情况记录实际比值 |
| G-time | 包含setup/模型加载/验算的端到端成本相对R-LU减少>=20%才称整体time positive；单次PC快不等同整体快 |
| G-neural | 同预算/精度下R-NN相对R-LIN端到端中位成本至少减少10%，或明确达到R-LIN未达到的数值资格，才能称神经增量正信号；不能把B0/降维本身的收益算给NN |
| G-generalization | 首轮只评估固定operator未见RHS；跨几何/波长/网格/非可分和0.7 nm全部not_run |
| G-amortization | 列teacher+dataset+train+setup+N次solve总成本、N=1/10/100以及在单次节省为正时的break-even；不只比较推理时间 |

这些百分比是首轮研究决策阈值，不是预测值或普遍算法定理。小case无法体现大factor主导时，要说明测量范围；不能仅凭小case无收益断言所有规模无用，也不能仅凭derived bytes宣传TB内存已消除。

完整内存账必须含weights、basis、编码/解码、patch/core、port、内层及外层Krylov、恢复、audit witness、Python/Torch/BLAS/GPU allocator和临时通信。数组载荷、后端allocated/used、RSS/PSS/VRAM分开；不累加不同阶段峰，不把共享view重复算独立存储。优先共享已存在的只读exact action作审核，不给每个模型私有复制CSR。

## 6. 允许/禁止修改与交付

可新增 `src/solvers/learned_*`、明确命名的coarse inverse protocol/adapter、对应tests、独立activation、research dat/profile、通用参数化runner/checker、Task042文档。数值核心进入src，不塞在benchmark。修改旧模块只限显式opt-in接口，附原路径不变测试；不得重构无关Hybrid/QEP/DtN/材料/几何核心，不整体复制另一个研究分支。

F0即建立轻量run/decision index，标明measured/derived/predicted/diagnostic/not_run/failed/controlled_stop/blocked。结束时至少交付：

```text
docs/task042_neural_coarse_inverse/
  response_v1.md
  outcomes/summary.md
  outcomes/environment_and_isolation.md
  outcomes/architecture_and_oracle.md
  outcomes/dataset_and_model_provenance.md
  outcomes/accuracy_performance_memory.md
  outcomes/test_summary.md
  outcomes/changed_files.md
  outcomes/records/run_index.json
  outcomes/records/gate_decisions.json
  outcomes/records/component_metrics.csv
  outcomes/records/full_p6_comparison.csv
input/task042_neural_coarse_inverse/...
```

未运行的full_p6表明确not_run及原因，不填假数据。正式run保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json、环境/资源/hash；学习增加dataset/model/basis/normalization/schema/training source/seed及split hashes，teacher原A4残差、checkpoint exact bytes identity。大artifact仍ignored，Git只提交必要小摘要。同步本分支docs/development_progress.md；发生正式PDE/资源运行后更新docs/development_model_registry.md的Task042小节，保留旧记录。

建议commit顺序：C1隔离/合同/接口与pure tests；C2实际A4和teacher/oracle/数据；C3线性与NN及推理；C4严格粗逆/条件p6与checker；C5真实结果/response。正式运行前实现先commit并确认clean；后续文档HEAD不能冒充运行source，不在活跃run中为了提交文档改变它受检的HEAD。

测试用金字塔：pure-array→真实小FE/非零RHS→coarse协议→Task042 focused回归→条件p6。不得在邻heavy运行时跑full pytest，也不要求为每个文档改动重复大FE。复杂bug不能用多个未记录重放覆盖负结果；监督/精度/资源触线按原记录停止。缺少已知条件时完成仍可做的部分，不自行扩大范围。

## 7. 首轮response必须回答

先给精确branch/HEAD/base/upstream/worktree、执行到哪一阶段、邻任务是否占用、是否真的无global p4 factor，再说明：原A4中哪个环节被替代；B0/线性/NN分别贡献什么；teacher与部署是否物理隔离；真实残差和端口恢复是否全部通过；完整时间与内存是否改善；NN是否超过线性；训练是否可摊销；失败由表示、训练、迭代、实现还是资源导致。

只有实现或组件证据时明确标注，不声称production、任意3D或0.7 nm通过。本任务完成、受控负结果或资源等待后，提交推送同一执行分支并停止等待review，不merge、不自动推进更短波长或更大网络。
