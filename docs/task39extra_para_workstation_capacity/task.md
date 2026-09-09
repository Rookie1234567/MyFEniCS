# Task39extra_para：原生 Linux 迁移、成功基线复现与短波 Full3D 容量测试

## 0. 身份、用户授权与本轮目标

```text
task_id                 = task39extra_para_workstation_capacity
repository              = Rookie1234567/MyFEniCS
execution_branch        = task39extra_para_workstation_capacity
remote_upstream         = origin/task39extra_para_workstation_capacity
task_directory          = docs/task39extra_para_workstation_capacity
base_branch             = task39extra
base_SHA                = 450255f4575792d052c1bac29837d39955ee1039
base_latest_commit      = Fix bubble diagnostic recording with one audited retry
baseline_review         = docs/task039_extra_physical_multilevel/review_report_v6.md
baseline_response       = docs/task039_extra_physical_multilevel/response_v7.md
created_date            = 2026-09-09
status                  = READY_FOR_CODEX_EXECUTION_AFTER_LOCAL_PREFLIGHT
execution_environment   = remote workstation; native Linux; about 2 TB physical RAM
formal_MPI              = 1
threads_per_process     = 1
solver_baseline         = V5 BAL_H + accurate global p4 LU
new_iterative_algorithm = NOT_AUTHORIZED
master_merge            = NOT_APPROVED
response_required       = response_v1.md
```

**本任务消除的 blocker：现有 Full3D 成功方案只在个人笔记本 WSL 环境完成了小规模资格，尚缺原生 Linux 工作站上的复现、短波运行能力及全过程容量证据。** 本轮先测“现有方法可以走到哪里”，不开发更好的迭代法，不执行前一轮讨论的子域法方案。

最终目标仍为约 2 TB 整机物理内存内的 0.7 nm、complex128、Nédélec H(curl)、双 Floquet、z 开放边界和周期单胞内任意非可分三维 Maxwell 散射。本轮只是迁移与 current-technology capacity campaign；不运行 0.7 nm，不承诺下列波长或网格一定通过。

用户本轮明确要求 ChatGPT 从 `task39extra` 创建独立分支并写任务书，因此本次分支创建是对通常“Codex 创建执行分支”的明确一次性覆盖。ChatGPT 只提交本目录任务文档；Codex 负责本分支后续实现性迁移、测试、运行和结果。个人笔记本继续原分支研究，工作站原目录继续 Hybrid 研究，互不接管。

本任务另明确授权：**在分级容量 Gate 内保留并测量增长型全局 p4 LU**，作为已有方法的容量测试；覆盖旧任务“短波前必须先去掉 p4 全局因子”的本轮执行限制。它不改变长期 scalable iterative 目标，不把这种因子提升为 0.7 nm production 路线，不提高旧任务的 p1/p2 底层行数上限。

## 1. 先读哪些文件，哪些旧状态不再作为本轮指令

先读根 `AGENTS.md`、`docs/AGENTS.md`、`docs/repository_work_principles.md`、`docs/README.md` 及修改目录下适用的 AGENTS，然后读本文件和以下继承证据：

| 文件 | 本轮用途 |
|---|---|
| [原任务 task.md](../task039_extra_physical_multilevel/task.md) | 原物理、空间、输入和历史范围 |
| [Review V6](../task039_extra_physical_multilevel/review_report_v6.md) | 已接受的 V5 双模型成功及限制 |
| [Response V7](../task039_extra_physical_multilevel/response_v7.md) | 成功链的执行回应 |
| [V5 完整结果](../task039_extra_physical_multilevel/outcomes/balanced_coupling_v5.md) | 数值、物理、时间、资源和恢复链 |
| [V5 compact](../task039_extra_physical_multilevel/outcomes/records/balanced_coupling_v5.json) | 精确数值与 raw/hash 索引；比较时不使用正文舍入值 |
| [最新 summary](../task039_extra_physical_multilevel/outcomes/summary.md) | 区分 V5 成功和 V6 未资格化粗逆 |
| [旧 workstation_handoff](../task039_extra_physical_multilevel/outcomes/workstation_handoff.md) | 仅历史移交边界；其 V2“未成功”已落后于 V5/Review V6 |
| [Markdown 标准](../markdown_rendering_standard.md) | 文档表格、公式与预览 |

分叉时目录最新 review/response 为 V6/V7，未发现独立补充任务书。旧 G5/response_v8 尚未收口，继续由笔记本 `task39extra` 负责；本任务不关闭它们，不等待新的 bubble 研究才开始迁移。

权威顺序：用户本轮明确指令 > 本任务及本目录后续 review > 适用 AGENTS > 继承证据。旧任务的 WSL-only、13.5 nm-only、12 GB-only 以及旧阶段停止流，仅在本文件明确覆盖处按本文件执行；旧数值结果、负分类、源码身份和资源限制不得追溯改写。不要从旧 handoff 的标题推断当前成功与否。

## 2. 工作目录、分支和邻近 Hybrid 的隔离

建议新 worktree 为工作站 `Projects/Maxwell3D-Lab`。若其为空，可用于本任务；若非空，先确认是否就是本分支 worktree，不删除、不覆盖，不把它嵌套在 `MyFEniCS` 里面。实际绝对路径由 Codex 在工作站解析并记录，不能假设登录用户或主目录。

初始化只允许：检查 canonical clone、非破坏性 fetch、登记本分支 worktree、设置本分支 upstream。新 worktree 必须来自上述远端分支及冻结 base，**不得使用当前 Hybrid 工作目录的 HEAD 作为基线**。不得在原目录执行 checkout、switch、reset、stash、clean、环境重装或全局 Git 配置更改。若本分支已在另一 worktree 检出，先报告，不使用强制重复 checkout。

运行时必须确认 `pwd`、`git rev-parse --show-toplevel`、branch/HEAD/upstream、tracked/untracked status、`src.__file__` 和关键模块实际导入位置都属于本 worktree。`results`、artifact、JIT/FFCx、TMP、Matplotlib 缓存及构建目录均为本任务独立可写路径；新结果不得通过 symlink 或硬编码绝对路径写回 Hybrid 或笔记本的结果目录。

两个工作站任务共用一套机器级 heavy-run 排他机制，锁文件放在 worktree 之外。若邻近 Hybrid 不使用该锁，仅持锁不能证明排他：还须检查已有 MPI/Python/MUMPS/编译进程树和资源，存在其他 heavy case 时不启动。本任务无权终止邻近任务、修改其 supervisor 或强删未知锁。等待资源记为 `WAITING_FOR_SHARED_WORKSTATION`，不是数值失败，也不消耗尚未开始的 PDE 计算预算。

本机笔记本是另一台机器，可继续其计算。工作站这两条线可以并行读写各自代码和文档，但一次只启动一个 heavy case，包括大 JIT、symbolic、factorization 和重型后处理。

## 3. 范围：只迁移和测量，不开发迭代法

| 允许 | 禁止 |
|---|---|
| 原生 Linux activation、ABI 检查、路径/权限/缓存/子进程适配 | 安装 WSL 或假装 Linux 是 WSL；改邻近环境 |
| 修复明确 API、dtype、MPI1、对象生命周期和输出 bug，并加最小回归 | 用“迁移 bug”名义改变 PC 数学结构 |
| 把旧 wavelength/h/80-channel/本机资源硬编码改为受验证的显式配置 | 删除校验、无约束任意 override、保留短波硬编码 80 channels |
| 为本任务新增 opt-in native-capacity profile，算法继承 V5 | ORAS/RAS/ASM、moving-PML、新粗空间、bubble/递归 p2、ILU 扫描 |
| 容量内的原 p4 增广 MUMPS LU、原两次粗修正和 H6 | 以 p6 全局 direct 替代正式 Full3D iterative，或 silent fallback |
| 本文冻结的波长/材料/网格阶梯、一个条件网格对照 | 任意角度/p/h/M/MPI/restart/shift 参数扫描 |
| 必需的低开销资源记录、保存与释放 | 一边容量测试，一边全面重写 matrix-free、static condensation、MPI 后端 |

`para` 表示与原研究并行的独立任务，不表示本轮必须开发 MPI 并行算法。正式运行先全部使用 MPI1/线程1；不因为内存大就切到 MPI8。后续 MPI 优化另立范围。

## 4. 被复现的成功方案与数学身份

### 4.1 不要选错 profile

继承 [原始 V5 输入](../../input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat) 和 [notch V5 输入](../../input/task39extra/nonseparable_13p5nm_p6h10_balanced_h6_p4_v5.dat)。不是 `original_13p5nm_p6h10.dat` 的早期候选，不是 V6 recursive LO/HI，也不是 BAL_S、PROJ_K6 或最新 bubble 诊断。

正式数值核固定为 full-space p6 Maxwell action、same-mesh p6/p4 相容传递、准确物理 p4 粗逆及 V5 BAL_H：

```math
A_4=P^H A_6 P,\qquad C=P A_4^{-1}P^H,\qquad
B_6=C+(I-CA_6)H_6(I-A_6C).
```

粗逆把残差送到 p4 物理空间求解，H6 做原来的正定辅助细层处理，再减去粗层反馈。每个 BAL_H PC 仍是两次 p4 求解；昂贵的是全局 p4 因子及其反复应用，不是 factorization-free 方法。

| 项目 | 固定合同 |
|---|---|
| fine 表示 | `standard_full` / full-space p6；继承 exact split action 与 streaming DtN |
| outer | right FGMRES，restart32，max2048，zero initial guess，单 live KSP |
| fine true residual | 原始完整 A6 的相对残差不超过 1e-6 |
| intermediate | same-mesh physical p4，准确增广方程和原 MUMPS 路径；原 A4 相对残差不超过 1e-10 |
| refinement | 最多原策略的两次同因子修正；失败前保存当前 RHS 与残差，不调整主元/排序抽签 |
| fine auxiliary | 原 V5 H6_degree3；谱窗随当前算子按原规则估计，不扫平滑步数 |
| PC 组织 | 无逐段 MR、无末端 MR、无新增内层 Krylov；粗平衡按原 1e-8 操作尺度检查 |
| 稀疏因子 | 正式允许一个 p4 全局因子；BAL_H 不额外建立无关 p1/p2 全局因子 |
| 边界/材料 | 原双 Floquet、完整 Fourier-DtN、复数损耗与负质量项，不加人工物理吸收 |

关键实现入口为 `src/io/physical_balanced_profile.py`、`src/solvers/physical_balanced_runtime.py`、`physical_balanced_coupling.py`、`physical_balanced_fgmres.py` 及现有 `src/runners/physical_balanced_*`。须沿 public adapter 追踪真实调用，不能根据 profile 标签推测有效参数。

已有 profile 包含旧本机预算与筛选限制，因此本任务允许新增显式 native-capacity adapter/profile，仅覆盖环境、本文运行规模和预算；旧 V5 profile/default 行为保持。所有生效参数进入 resolved config/manifest，包括仍由 profile 派生的值。不要只改 `.dat`，却让内部代码继续执行旧 12 GB 或旧超时。

### 4.2 WSL 成功基线：只引用，不冒充新测量

| measured 历史指标 | 原始 | 非可分 notch |
|---|---:|---:|
| 成功求解 source | `2bb6770ad00b35881558c576e7296e250656e571` | `094204b7281fe867744fe334e8753d2faebaf89b` |
| recovery/reference source | `094204b7281fe867744fe334e8753d2faebaf89b` | 同左 |
| outer iterations | 564 | 576 |
| full true residual | 9.932289220e-7 | 9.351705517e-7 |
| R | 0.365625790955 | 0.337120584975 |
| T | 0.0129906323212 | 0.0162886742427 |
| A_balance | 0.621383576724 | 0.646590740782 |
| A_volume | 0.621383574645 | 0.646590748463 |
| solve，保守秒 | 6102.614283 | 6261.471126 |
| 同期进程树 RSS 峰，B | 3466235904 | 3600924672 |

原始 p6 存储/独立行数为 173802/164592，252 个六面体；p4 FE 存储 53084、加 80 端口后 53164 行。以上来自 V5 报告/compact，不可硬填为工作站实测。旧 notch reference 有 global pswpout 448 页、归因未定的限制；本轮既不删除该历史，也不要求重做参考来“洗掉”它。

## 5. R0：原生 Linux 环境与迁移预检

### 5.1 已知的 WSL 专用问题

继承的 `scripts/activate_myfenics_wsl.sh` 检查 `/proc/sys/kernel/osrelease` 是否包含 microsoft，并写死 PETSc/SLEPc 3.19、Python3.12 site-packages 和 WSL marker。**不能原样作为原生 Linux 入口，也不能只删 kernel 检查并伪造 `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`。**

优先检查工作站已有、正在被其他任务使用的资格化 ABI 栈，只读复用其库；为本 worktree 建立独立 activation，例如 `scripts/activate_myfenics_linux.sh`，明确验证 native Linux。允许最小修改本分支中硬编码要求 WSL activation 的 launcher/preflight，使其识别真实 native qualification；保留原 WSL 路径的合法行为。路径必须来自实际安装，不能猜另一台机器的目录。

不要复制笔记本 `.venv`、编译二进制、FFCx 缓存或因子；不更改系统 BLAS alternatives、系统 MPI/PETSc、全局环境或邻近虚拟环境。不自行安装/升级整套依赖；缺必要系统权限或不可隔离的依赖时，报告具体 blocker 与人工步骤，不在对话中索取或记录密码、key、passphrase。

### 5.2 正式前的必检项

| 类别 | 必须保存的事实 |
|---|---|
| 主机 | hostname、kernel/distribution、CPU/NUMA、实际 MemTotal/MemAvailable、cgroup、磁盘及 inode |
| 仓库 | canonical clone/worktree、origin、branch/HEAD/upstream、base ancestry、clean 状态 |
| Python/import | `sys.executable`、sys.path、项目实际导入根、virtualenv、环境 marker |
| ABI | DOLFINx/Basix/FFCx/UFL/dolfinx_mpc、PETSc/petsc4py、SLEPc/slepc4py（若该路径导入）、mpi4py/OpenMPI及MUMPS版本/库路径 |
| 数值类型 | PETSc.ScalarType=complex128；PETSc.IntType、NumPy/SciPy index dtype、MUMPS接口能力 |
| 线程/执行 | MPI1；OMP/OPENBLAS/MKL/NUMEXPR/VECLIB 等线程1；记录 affinity，不自动换 BLAS 或扫 NUMA策略 |
| 存储与安全 | 原生 Linux 文件系统、独立缓存、zero swap、整树 watchdog、无邻近 heavy、排他锁、磁盘余量 |
| 输入 | original/physical/resolved/source SHA；材料、实际网格、约束、external keys、effective profile |

重点检查：旧绝对路径、Windows挂载路径、`wsl.exe`、只允许 WSL 的脚本、MPI launcher 嵌套、JIT cache 身份、PETSc BuildSolution/对象释放 API、端口 metadata 和跨版本 dof 排序。不要从客户端是 Windows 得出计算发生在 Windows；本任务所有项目命令都在 SSH 目标 Linux 内执行。

先做一次合并的最小 smoke：complex curl/mass、MPC/Floquet、DtN action、p6/p4 传递与复伴随、一个小 p4 MUMPS solve、真实残差、checkpoint/recovery和watchdog清场。相关旧 targeted tests 优先复用；不重跑笔记本的全部诊断 campaign。数值作用检查沿原 1e-10，禁止用 mock 替代所有物理测试。环境/路径修复和小测试通过后提交 clean source，进入 R1，不交 docs-only response 后等待。

## 6. 物理、材料、通道与输出身份

### 6.1 几何和离散

原始几何沿 V5：period_x/y=50/25 nm，z=-10…130 nm，substrate厚10 nm，grating宽x/y=17/25 nm、高120 nm，interface_z=0；1° grazing、azimuth0、s、electric amplitude1；air index1、mu_r1；结构化 boundary-fitted hexahedron、p6。

R2 notch 复用 V5 已解析的 8 个修改 cell、实际材料实体及其 keys/hash，不重新挑选更容易的缺口。短波主容量阶梯仅使用原始几何，**不在本轮额外开展短波 notch 扫描**；其成功不等于短波任意三维资格。

### 6.2 材料表：明确波长与材料同时变化

| wavelength，nm | substrate/grating | n 的实部 | n 的虚部 | 身份 |
|---|---|---:|---:|---|
| 13.5 | Si | 0.999002304859 | 0.00182649365 | V5 复现必须完全相同 |
| 5 | W | 0.99396854453 | 0.00435380777 | 继承既有 Task039/Task041 短波材料 |
| 3 | W | 0.99735217495 | 0.000883207249 | 继承 Task041 用户提供值 |
| 2 | W | 0.99880148307 | 0.000213688647 | 继承 Task041 用户提供值 |

短波材料来源固定为 [Task041 task.md §4](https://github.com/Rookie1234567/MyFEniCS/blob/c08dd39bb371e3b595943ace371874777c0ff476/docs/task041_mpi1_shortwave_hybrid_capacity/task.md)。只引用材料与必要物理定义，不迁入 Hybrid 数值代码、运行脚本或其停止流。

由 n 在 complex128 下计算 epsilon=n*n，保存 n/delta/beta/epsilon及来源。**13.5 nm Si→短波 W 是显式更换物理材料，不是纯波长单变量实验；不能把性能变化全部归因为波长。** 不将 Si 的 13.5 nm 参数原样用在短波，不自行外推光学常数。后续用户修改材料时须新身份，不覆盖旧 run。

### 6.3 外部通道和输出

各波长按原 `auto_propagating` 规则计算实际完整 external inventory；不沿用 13.5 nm 的固定 80 模式，不凭旧 Hybrid 表手填数量。保存每个上下端口的 (m,n,polarization,side)、传播分类、归一化、符号、phase 和 ordered/set hashes。p4 必须使用与 p6 一致的物理通道集和积分合同，不能在 p4 自行减少 auto channels。

本任务没有 Hybrid internal M、QEP、middle modal region、side factor 或 modal-Schur；不要为本任务添加 M800/M1200。

外部输出探针固定为 top=127.5 nm、bottom=-7.5 nm；内部参考平面 z=10/30/60/90/110 nm 不当作外部探针。继承原采样规则并输出复 E/H，比较时排除界面取值歧义、保持坐标与侧别。所有实际 external channels 必须输出，不能让 V5 input 的 reporting max_m/max_n=2 裁掉正式衍射结果。输出 bound/采样按实际 inventory确定并写入配置，不改变 PDE mode集合，也不把易混叠的采样 Fourier 当作 official 振幅。

## 7. 运行顺序：先复现，再逐级缩短波长

所有正式 PDE 均经唯一入口：

```bash
python scripts/run_case.py input/task39extra_para_workstation_capacity/<one-case>.dat
```

activation、`cd`、线程环境与命令处在同一个 Linux shell。按现有 launcher 合同保证实际 MPI size=1；若入口自行启动 MPI，外层不得再嵌套 mpiexec。一个 dat 只表示一个 case/run，不加入隐藏批量循环。

| 阶段 | 正式对象 | 目的与解锁条件 |
|---|---|---|
| R0 | 无大 PDE 的环境/迁移/最小测试 | 通过 §5 后自动进入 R1 |
| R1 | 13.5 nm Si、原始、p6/h10、MPI1 | 唯一主复现；必须先得到完整场与比较结果 |
| R2 | 13.5 nm Si、原 V5 notch、p6/h10、MPI1 | R1通过后一次小型三维回归；不是扩展新几何研究 |
| S5 | 5 nm W、原始、p6/h4、MPI1 | R1/R2各自通过、迁移比较资格明确、容量预检通过 |
| S3 | 3 nm W、原始、p6/h2.5、MPI1 | S5 own numerics/physics/resource通过且下一点预检通过 |
| S2 | 2 nm W、原始、p6/h1.5、MPI1 | S3同样通过后才解锁；3 nm失败不得跳过它直跑2 nm |
| G | 至多一个末端同波长网格对照 | 按 §7.3 条件执行；不是额外完整网格扫描 |
| Z | 结果与边界收口 | 真实 Gate失败或授权阶梯完成即整理并回应 |

主网格按接近 V5 的 h/λ 量级选择，只是容量试验的起点，不保证相同场误差：V5约0.741，S5=0.8，S3约0.833，S2=0.75（derived）。实际 boundary-fitted单元尺寸仍须计算；不能把 target h 当作每个方向精确单元宽度。不要先在5 nm继续h10而将欠分辨的“跑通”当成目标能力。

### 7.1 R1/R2 的比较与参考缺项

先按 V5 compact/hash索引查找已有 reference、成功解、完整80复振幅和材料/网格映射。只迁移最小必要可读数组与元数据，另写路径映射，不改旧hash，不复制整个LU/大缓存。可以复用用户已提供位置的只读数据，不自行探索其他SSH主机或索取secret。

R1/R2始终zero start，参考解只用于运行后的独立比较，不进入PC、初值、基函数选择或停止准则。跨ABI的 native dof顺序可能变化，按canonical物理key/方向/坐标映射比较，不能直接把未对齐数组相减，也不要求迭代次数精确等于564/576。

若旧完整场数组未随Git提供，记录 `WSL_FULL_FIELD_COMPARISON_PARTIAL`，不冒充完整WSL/Linux等价。原始与notch的tracked完整复振幅/功率、source/physical/mode identity和own Gate仍必须比较；不得只看R。

为避免仅因ignored旧场未搬运而停住，允许在缺项模型上各至多一次13.5 nm匹配离散direct reference：使用仓库已存在的reference路径及§9的小案例上限，先做symbolic预检，reference进程与迭代进程不得重叠；不开发新direct算法。通过后标 `NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL`，可进入短波容量阶梯，但不称完整跨环境场复现。若既无旧完整场又无法取得允许的native匹配参考，完成现有R1/R2记录后以 `REFERENCE_EVIDENCE_BLOCKED` 收口，短波不启动。

### 7.2 短波只测试原方法

为S5/S3/S2新增独立dat及显式native-capacity profile。允许参数化材料、波长、网格、真实channel数、资源和本文wall上限，保持§4数值机制不变。改变h后按原规则重建H6谱窗、A4、MPC、source与DtN；不把旧因子、旧mode cache或旧参考解作为新case输入。

上一波长通过不代表下一波长可预估成功。每一新点先按§9分级建模、装配、symbolic、numeric，才进入outer。若失败，先分类为迁移实现、资源、p4求逆、outer性能/迭代或物理一致性，不自动开发新PC。

本任务以capacity为主：每个短波case满足own numerics/physics/resource后可进入下一个点，无需先为每一波长完成整个h收敛阶梯；结果必须标 `DISCRETE_CAPACITY_PASS_ACCURACY_UNQUALIFIED`。这不是放弃精度要求：不能宣称accuracy-qualified或continuum-converged，且可用§7.3取得一个有限网格对照。

### 7.3 一个条件网格对照，不无边界扩张

主阶梯结束后，至多在最短已own-pass的短波点追加一次更细网格：5 nm h4→h3；3 nm h2.5→h2；2 nm h1.5→h1。仅选其中一项。只有剩余预算、symbolic/对象预测和主机安全Gate均通过才运行；若主阶梯因安全/实现问题停下，该问题未关闭前不运行G。

此对照从同一物理几何重建网格，PC不变，无新fine direct短波reference。比较全部复场、重要衍射级和R/T/A_volume；只有两个case各自own-pass才判网格差异。一个相邻网格对照通过仅称 `ADJACENT_GRID_AGREEMENT_PASS`，不是连续极限证明。失败或不具容量则保留精度/容量边界，不再加第三张网格；不因加密通过而自动重启已失败的另一波长。

## 8. 数值、物理、参考与错误分类 Gate

| Gate | 标准 |
|---|---|
| fine | 完整原A6相对true residual ≤1e-6；finite且KSP正常收敛 |
| coarse inverse | 原A4相对true residual ≤1e-10；最多两次原同因子修正，记录最差值及次数 |
| coarse/fine identity | Galerkin分项/复伴随/约束沿原1e-10检查，粗平衡沿1e-8操作尺度；不固定旧row count |
| own energy | abs(R+T+A_volume−1) ≤1e-5；abs(A_balance−A_volume) ≤1e-5 |
| fields/channels | 复E/H、实际全通道复振幅/功率、A_volume均finite；通道完整、无重复，物理坐标和材料侧别明确 |
| R1/R2匹配参考 | 场L2及scaled curl相对差≤1e-4；selected E/H相对差≤1e-4（近零量另报绝对差）；不拟合全局相位 |
| R1/R2功率/幅值 | R/T/A/A_volume绝对差≤1e-5；全80复振幅相对差≤1e-4；逐通道功率最大绝对差≤1e-6 |
| G网格对照 | R/T/A/A_volume绝对差≤1e-4；显著级功率/复幅值相对差≤1e-3；selected E整体相对L2≤5e-3、H≤1e-2 |

G显著通道取两次功率≥1e-8的并集，零/近零值同时报告绝对差。p/h比较不能把不同网格的native FE系数直接作差，要用相同物理位置或合法跨网格比较。R+T+A_balance=1如果由定义产生，不能作为独立能量证据。

官方输出只来自收敛且通过own物理Gate的场。已收敛但物理Gate失败时允许保存候选场和候选R/T/A，明确 `CANDIDATE_PHYSICS_NEGATIVE`，不得删除它们，也不得提升为official。

物理失败允许对同一保存解做一次有明确原因的检查：外部功率、各区域体吸收、积分metadata/输出覆盖；不重新跑整场、不临时放宽1e-5、不自行换材料。若明确是输出/后处理bug，可最小修复、focused测试后只恢复同一解；如果涉及A/b，按§11重新资格化，不能声称同一解修复。原因未明或真实离散物理不合格，停止主阶梯。

## 9. 容量预检、安全和全过程资源

### 9.1 不把整机2TB当可全部占用的RSS

R0实际测量 effective_total=min(物理MemTotal,有效cgroup上限)，区分decimal TB和TiB。短波规划策略（不是实测）为：

```text
reserve          = max(256 GiB, 0.15 * effective_total)
hard_ceiling     = min(1.60 TiB, 0.80 * effective_total)
planning_ceiling = min(1.50 TiB, 0.75 * effective_total)
launch_hard_cap  = min(hard_ceiling, effective_available_at_launch - reserve)
warning          = min(0.85 * launch_hard_cap, 1.40 TiB)
```

TiB=2^40 B，GiB=2^30 B。effective_available还要考虑cgroup余量；任何cap≤0不启动。每case frozen watchdog以bytes记录，运行中既检查同期进程树RSS/cgroup，也检查剩余系统可用量≥reserve。实际可用不足时收紧cap，不自动升高；容量预测上界必须≤min(planning_ceiling,launch_hard_cap)。系统余量被邻近进程侵占时安全停止，不归罪数值方法。

13.5 nm复现及条件reference使用小案例独立上限：hard=min(32 GiB,launch_hard_cap)，planning=min(24 GiB,hard)，warning=0.85*hard；不因为整机大就为小模型开放TiB预算。32 GiB只是迁移容差，不是目标RSS；仍报告相对旧约3.2–3.4 GiB的实际差异。

全任务swap使用与增量要求为0，禁止OOC/磁盘因子fallback。若有预存swap占用或活动，先报告，不自动sudo swapoff，不把系统swap和job VmSwap混为一谈。无法归因的全系统活动标 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED` 并安全停止压力运行，不伪造数学失败。

### 9.2 每张网格必须按阶段通过

| 阶段 | 允许做什么 | 下一阶段条件 |
|---|---|---|
| P0计数/容量计划 | 实际axis/cell/FE独立与存储行、p4增广行、channels、向量/局部张量、结构NNZ与dtype检查 | 装配及JIT本阶段上界在cap内 |
| P1装配 | 原p6 action/transfer、原p4 sparse/port增广；分项记录，避免未经预检的CSR整份复制 | live-set与稀疏index合法；预测symbolic安全 |
| P2 symbolic | 原MUMPS analysis一次，记录实际INFOG/RINFOG、矩阵/转换/工作区 | numeric与剩余求解/输出峰值上界≤规划线 |
| P3 numeric/setup | 原p4 factor；记录实际NNZ/字节估计与同期RSS | 数值稳定、原A4 residual通过、仍有outer/recovery余量 |
| P4 outer/recovery | 有界FGMRES、真残差、保存、释放、物理恢复 | §8和本节联合通过 |

容量账本至少包括p6/p4 FE与mesh、MPC/transfer、JIT compiler、DtN trace/streaming缓冲、p4 AIJ/COO/CSR及转换副本、因子、Krylov V/Z和全部工作向量、checkpoint/输出。FGMRES32约65个complex128基向量的16*N*65 B仅是derived基向量载荷，不含整个求解器，N采用实际存储/owned长度。

稀疏矩阵索引容量、NNZ计数、MPI count和MUMPS接口必须分别核对，不能只看自由度未超过int32范围。可使用工作站已有并已验证的兼容int64栈，但不能在运行中换ABI；若必须大规模重建依赖才能前进，记录 `ABI_OR_INDEX_CAPACITY_BLOCKED` 并收口，不以astype(int32)绕过。

第一个短波点没有校准过的factor尺度，不凭N的一个幂指数直接放行。允许先在安全预算内得到symbolic估计；若仍缺可靠numeric/总峰值上界，分类 `PREFLIGHT_UNCERTAIN`，不把“估计未知”当成“0字节”。后续点用新实测修正预测，并分别列 measured、derived、predicted central/upper。

### 9.3 监督与生命周期

watchdog从启动前覆盖Python parent、MPI、compiler、solver及所有后代，达到hard或安全线时终止本次完整进程组并验证清场；不使用宽泛pkill、不碰邻近进程。至少保存0.25–1s级RSS/swap采样和阶段marker；PSS/USS可较低频采样作为另列诊断，避免每次读取smaps拖垮求解。

峰值取同一时刻整树之和的最大值，不取各rank历史峰值之和；不叠加不同阶段峰值。记录wall、CPU、NUMA/affinity、IO/scratch、可用内存、swap、factor信息及采样覆盖/缺口。资源尾样本失败不能改写已经取得的数值结果，资源资格独立标记。

必须执行：solve→full true residual→最小solution/recovery packet落盘→释放outer KSP、p4因子/矩阵及无用对象→记录RSS变化→recovery/output→清场。操作系统未立即回收allocator页时说明实际事实，不伪造RSS下降。不能为测量后处理又把已释放factor留在后台。

## 10. 时间、迭代上限与有限投入

下表是本任务授权上限，不是预计运行时长。wall/solve预算的变更是显式容量合同，不作为相对笔记本的算法加速证据。

| case | 首段screen：步数或solve秒先到 | solve硬上限，s | workflow硬上限，s |
|---|---|---:|---:|
| R1原始13.5 | 128步或1800s，继承V5判断 | 14400 | 21600 |
| R2 notch13.5 | 继承V5 notch无screen，不新增筛选 | 14400 | 21600 |
| S5 | 128步或10800s | 86400 | 129600 |
| S3 | 128步或21600s | 172800 | 259200 |
| S2 | 128步或21600s | 259200 | 345600 |
| G | 按该波长同一规则 | 同该波长 | 同该波长 |

有screen的case沿V5标准：true≤1e-2，或最近两个完整32步周期均下降且几何平均缩比≤0.65，才继续同一live KSP。未形成足够完整周期且未到1e-2，则记 `SCREEN_BUDGET_NO_QUALIFIED_PROGRESS`，不是“永不收敛”。通过screen后仍受2048步及完整wall限制；不重启、warm-start、加restart或增加max-it。

迁移/小测试累计计算预算14400s；条件13.5 reference每模型workflow最多10800s。全campaign累计实际计算预算864000s，包含失败、JIT、测试、参考、各正式run和G，父子嵌套时间不重复计费；等待机器/密码/审阅与文档编辑另列。单项上限不是可全部相加的运行承诺，预算耗尽即保存收口。

沿既有conservative计时原则，同时记录monotonic/UTC；原生Linux不应无条件照搬WSL异常判断而误杀正常进程。可修复明确时钟/资源采样实现bug，但不得选择更短时钟掩盖真实耗时。运行中定期输出阶段/内层/PC心跳，不能因一段长factor没有打印就反复启动同一case。

## 11. Codex 可自行修复什么，何时必须停止

明确且局部的迁移错误允许Codex在本分支自行调查、最小修复、focused测试、提交clean source后继续；无需每个小测试都停审。修复必须说明根因、影响A/b/PC/输出/资源中的哪一项，并保留旧失败目录。

同一个根因最多一次正式retry；一个case累计最多两次迁移性正式retry。输出错误优先只恢复同一已保存解，不重复factor/outer。超过retry预算，或需要改变算法才能继续，保存现有结果交review。未到重型阶段的小单测修复正常推进，仍计入准备预算。

| 情况 | 本轮处理 |
|---|---|
| WSL硬编码、native路径、API签名、MPI1空owner、明确dtype/共轭/orientation实现bug | 最小修复并验证原数学合同；必要时只重跑受影响R1/R2 |
| source/surface quadrature修复导致旧A/b语义改变 | 单独保存前后差与身份桥；不得称原样复现；未证明等价前不进入短波 |
| 确认改变了物理积分/离散而非实现原合同 | `REFERENCE_SEMANTICS_CHANGED_REVIEW_REQUIRED`，不自行选择新权威 |
| p4原残差失败、factor数值失败、nonfinite | 保存RHS/分项/因子信息，停止本case；不换PC或扫MUMPS参数 |
| fine残差在screen/2048步/solve预算内未通过 | 数值或性能边界；停止主阶梯，不当bug重新抽签 |
| own physics未过 | 按§8核验同解；真实问题不闭合则停止主阶梯 |
| memory/swap/disk/index/watchdog Gate | 安全停止及清场，保留capacity或instrumentation分类 |
| 邻近heavy或权限需要人工操作 | 明确等待/blocked，不能杀其他任务或记录secret |

失败不得静默改称success。资源资格失败不自动否定数值结果；同样，数值通过不补上缺失资源证据。`not_run`、`failed`、`controlled_stop`、`blocked`、`diagnostic`分别使用。

## 12. 提交、证据和最终回应

### 12.1 提交计划

```text
1. native activation/preflight与隔离；最小迁移兼容修复和targeted tests
2. 显式native-capacity profile/dat接线；旧V5行为回归；clean prototype
3. R1/R2复现证据；必要迁移修复单独commit
4. S5→条件S3→条件S2→条件G，每个完成/停止点及时保存compact
5. outcomes、项目总账、response_v1.md与selective-merge建议
```

全部commit/push仅到 `task39extra_para_workstation_capacity`。不amend、不强推、不整体merge笔记本或Hybrid研究分支、不merge master。原分支后续前进不自动同步；需要移植其修复时列source SHA、最小文件/补丁和对当前结果影响，经审查后再做。旧任务文件只读，原base及其历史负结果保持。

### 12.2 一次运行的最小可复现证据

每个formal或controlled-stop root保存 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、`input_sha256.txt`、`physical_model_sha256.txt`、`source_sha.txt`、`run_summary.json`；另存环境/ABI、命令、MPI/线程、mesh/material/constraint/channel manifest、profile生效参数、residual曲线、PC/p4调用与时间账、阶段资源及artifact hashes。短波预检停止也有同等身份的preflight记录，不伪造run_summary通过。

完整field/mesh/checkpoint/factor/矩阵/大日志/JIT保持ignored，不进Git；原始数据不覆盖。Git只提交足以复核结论的小JSON/CSV、完整必要复振幅、配置和索引。跨环境参考路径重映射另列，input或run_id变化须计算新hash，不手填旧hash。

Codex在本任务目录形成：

```text
response_v1.md
outcomes/summary.md
outcomes/environment_and_migration.md
outcomes/reproduction_13p5nm.md
outcomes/capacity_frontier.md
outcomes/test_summary.md
outcomes/records/run_index.json
```

允许按实际内容合并相邻说明文件，避免每个小检查新建一套报告；上述信息不可缺。每个正式完成/停止同步更新本分支 `docs/development_model_registry.md`，最终更新 `docs/development_progress.md`。不得向原任务outcomes写本分支结果。

summary必须表格优先，逐case列模型/波长/材料/p/h、独立与存储DoF、p4增广rows/NNZ/factor、actual channels、outer与p4残差/次数、R/T/A/A_volume、E/H/衍射比较、完整wall/阶段时间、同期RSS/可用量/swap、数据身份、source/input/physical/resolved/hash、失败阶段及next_gate。预测和实测分表，不用候选替代official。

### 12.3 最终必须回答

1. 原生Linux环境是否资格化？修了哪些WSL/路径/API问题，是否改变A/b/PC？
2. R1/R2分别是否复现？与WSL的场/幅值/功率比较有哪些实证或缺项？
3. 最短完成的波长、最细完成的网格、最后own-pass点各是什么？
4. 止于内存、symbolic/numeric、index/ABI、outer收敛、时间还是物理/精度？
5. 全局p4因子、fine action、DtN、Krylov、JIT和输出分别占多少？哪些是实测，哪些只是derived？
6. G是否执行、相邻网格是否一致？无证据就明确accuracy-unqualified。
7. 哪个具体blocker应交给后续迭代法开发？本轮不得直接开始该开发。
8. 完整branch/base/final SHA、upstream、worktree、测试、证据入口及merge decision是什么？

可组合最终状态：`NATIVE_ENVIRONMENT_PASS`、`WSL_TO_NATIVE_REPRODUCTION_PASS`、`NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL`、`DISCRETE_CAPACITY_PASS_ACCURACY_UNQUALIFIED`、`ADJACENT_GRID_AGREEMENT_PASS`、`NUMERICAL_FRONTIER`、`PHYSICS_GATE_STOP`、`RESOURCE_FRONTIER`、`PREFLIGHT_UNCERTAIN`、`ABI_OR_INDEX_CAPACITY_BLOCKED`、`PERFORMANCE_CONTROLLED_STOP`、`EVIDENCE_INCOMPLETE`、`NOT_RUN_BY_PREVIOUS_GATE`。每个状态必须对应实际case/阶段，不能以枚举代替解释。

正式结束前运行task-focused测试、必要Ruff/compileall及文档合同检查；未运行的全库测试/CI不写通过。检查GitHub公式/表格rendered view与链接。给出依赖分组的selective-merge建议，但本任务没有merge approval；最终review和用户授权前不合并。

**本轮交付是可复现的迁移结果与已有Full3D方法的短波容量边界，不是一套新PC，也不是0.7 nm可行性承诺。**
