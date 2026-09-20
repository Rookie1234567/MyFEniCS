# Review V3：实测 RSS 停止策略、双凝聚迁移与 CPU23 的 5 nm p6/h4 对照

## 0. 审阅结论、身份与授权

**接受 2 nm 旧运行因全局换页计数而停止的事实，不追溯改判；按用户本轮要求，后续本任务的资源自动终止改为实测整树 RSS 达到已声明 Gate，不再因换页、预测内存或预计耗时提前中断。本批选择性迁移 `task39extra` 的 p6/p4 双层单元凝聚，完成必要资格后，只运行一场新的 5 nm Si、p6/h4、MPI1/数学库线程1、worker CPU23 对照。**

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task39extra_para_workstation_capacity
review_date             = 2026-09-20
reviewed_target_HEAD    = 47cb73bf083072ed03788f67830f6ca1e933b60c
previous_review         = review_report_v2.md
previous_response       = response_v4.md
historical_branch_base  = 450255f4575792d052c1bac29837d39955ee1039
source_branch           = task39extra
source_snapshot         = ea717ed5c6ffe45214ecdeca80cabdaeaef5960b
source_latest_review    = docs/task039_extra_physical_multilevel/review_report_v22.md
source_latest_response  = docs/task039_extra_physical_multilevel/response_v24.md
new_profile_suggested   = dual_condensed_balh_native_5nm_v3
new_input_suggested     = input/task39extra_para_workstation_capacity/original_5nm_si_p6h4_dual_condensed_v3.dat
resource_policy         = measured_tree_rss_only_v3
formal_MPI              = 1
math_threads            = 1
worker_cpu              = 23
parent_watchdog_cpu     = 9
response_required       = response_v5.md
execution               = D0 -> D1 -> D2 -> D3 -> D4
formal_new_5nm_runs     = 1 normally
restart_2nm             = NOT_AUTHORIZED
master_merge            = NOT_APPROVED
```

本轮消除的 blocker 是：**全机换页事件错误地充当本任务容量界；以及完整 p4 全局分解、完整 p6 外层向量与重复单元计算，使已成功的 Full3D 路径在短波放大后过重。** 双凝聚可能减少全局未知量、迭代步数和装配成本，但新增局部缓存可能提高某些阶段内存，必须以同一 5 nm 案例实测判断。

最终目标仍是约 2 TB 整机物理内存内的 0.7 nm、complex128、Nédélec H(curl)、双 Floquet、开放 z 边界和任意非可分三维周期单胞。此批不是 0.7 nm 资格，不是子域法开发，也不是一项无限参数研究。

用户本轮明确授权覆盖原 `task.md` 的“本批不开发新求解表示”、旧 swap 自动终止及相关预测准入限制，限于本文件范围。允许在同一执行分支扩展双凝聚，不另建分支；原 task、旧 review/response、失败和旧输入/profile 均保留。不把笔记本的新研究执行流、内存上限或多线程试验自动带入工作站。

## 1. 审查依据与历史边界

先读根 `AGENTS.md`、`docs/AGENTS.md`、`docs/repository_work_principles.md`、本任务 [task.md](task.md)、[Review V2](review_report_v2.md)、[Response V4](response_v4.md)、[summary](outcomes/summary.md) 和适用目录规则。目标目录目前无另列补充任务书；过去用户例外授权已记录在本目录 response 中，本轮由本 review 明确承接和覆盖。

源分支必须按冻结 SHA 阅读，不只看当前分支名：

| 来源 | 本轮使用内容及限制 |
|---|---|
| [V19双凝聚证据](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/outcomes/dual_cell_condensed_v19.md) | p6 retained Schur、p4凝聚准确逆、J逆桥；13.5 nm固定案例成功与RSS增加均保留 |
| [V20生命周期](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/outcomes/dual_condensed_memory_v20.md) | 共享缓存、编译顺序和后端矩阵借用边界；不能盲目提前销毁矩阵 |
| [源summary](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/outcomes/summary.md) | original h10、notch h10的通过范围与h7.5负项分开 |
| [源Response V24](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/response_v24.md) | h7.5原A6收敛，但一次在线p4残差超过1e-10，总checker不是PASS |
| [源Review V22](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/review_report_v22.md) | 有界同因子精化与热点建议；属于授权，不当成已实现加速结果 |
| [源容量补充](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/user_authorization_v22_b_capacity.md)、[源物理内存补充](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/user_authorization_v23_physical_memory.md) | 仅理解源结果，不照搬笔记本6/8 GiB、128 MiB余量或4687 MB后端限额 |
| [本机旧5 nm compact](outcomes/records/5nm_formal_attempt1.json) | 新5 nm同离散数值/物理及工程成本对照，不是连续真解 |
| [旧5 nm资源覆盖](outcomes/records/5nm_resource_coverage.json) | 保留监督断档；旧观察峰不能升级为完整RSS authority |
| [2 nm终态](outcomes/records/2nm_h1p5_measured_terminal_snapshot_v1.json) | 只复核停止原因、PID清场、数值未运行和各采样器口径；不重做2 nm |

本次审查使用远程已提交记录及关键源码，没有SSH运行PDE，也没有复核工作站全部ignored原始数组。Codex在D0核对现场raw/hash及实际导入依赖；缺项明确记录，不凭文档填造数组或参考值。

### 1.1 本次换页停止到底是什么

旧run `20260918T035017.294454Z`，source `41caf5141493ad6c5d6c518a64ee74fda8d7a7db`，2026-09-20 04:46:37 UTC触发、04:47:15 UTC收尾。

| 量 | 已提交事实 | 判断 |
|---|---:|---|
| 全机 pswpout | 2到73页，增加71页 | 4096 B/页下为290816 B，即284 KiB |
| 原watchdog停止样本/记录峰RSS | 635625377792 B | 未达到1300 GB或1537.5 GB |
| 任务树swap | 0 B | 不能把全机71页归因给本任务 |
| MemAvailable / 旧reserve | 836791996416 / 324465062092 B | 不支持全机RAM耗尽判断 |
| 独立1300 GB guard接管后峰 | 640141377536 B | 单独采样口径，不与原watchdog拼峰 |
| 终态 | exit=-9，GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED | 后代已清场；无numeric complete、outer或RTA |

后一个guard约晚0.245秒因worker已退出不可读而收尾，不是首次中断原因。旧负结果成立于旧合同，不删除、不改成内存通过或2 nm求解通过。**本轮不重启该2 nm任务；先完成5 nm双凝聚。**

### 1.2 为什么采用双凝聚，但不预先保证收益

源V19在13.5 nm original p6/h10中，外层向量173802降到51272，564步降到112步，完整monotonic时间6609.6614降到1352.0121 s；同时RSS从2528460800增加到3965534208 B。源V20调整生命周期后，同original为112步、1479.1772 s、RSS2831749120 B。不同版本时间/内存口径分开；不把其中最低值拼成一场虚构基线。

源h7.5最新126步完成，但254次p4逻辑调用中有一次rho=2.8870661155266027e-10超过1e-10；该结果仍NOT_FULL_PASS。本轮必须执行第4.3节的返回质量合同，不能只迁移最后版本标签并忽略这个缺陷。源13.5 nm提速不证明5 nm也有相同步数或倍数。

## 2. 资源策略：换页只记录，资源终止依据实测整树 RSS

### 2.1 唯一显式内存 Gate 与新策略

为本批新profile统一采用最近额外guard已使用的较保守上限，不把它暗中提高到原1537.5 GB：

```text
rss_hard_limit_bytes             = 1300000000000
units                           = decimal GB (1300 GB, not 1300 GiB)
rss_warning_bytes               = 1170000000000
resource_stop_policy            = measured_tree_rss_only_v3
swap_policy                     = observe_only
global_swap_delta_policy        = observe_only
prediction_admission_policy     = record_only
memavailable_runtime_policy     = observe_and_warn_only
resource_sampling_target_seconds= 0.25
pss_uss_policy                  = low_frequency_diagnostic
```

**本分支后续采用该显式资源策略的运行，不因任何全机换入/换出增量、任务VmSwap非零、swap使用量变化、major/minor fault、预测峰、预计耗时、低于Gate的后端allocated/used或旧对象库存额度自动停止。** 不仅取消全机71页的路径，也必须检查任务swap和下层采样器是否仍有等价的隐藏kill条件。

资源自动终止谓词是：有效、可读的同期本任务进程树RSS大于或等于1300000000000 B。整树包含本次launcher、MPI、worker、编译器和属于本run的后代，按PID/start_ticks去重；线程不是多个独立进程RSS，不把邻近Hybrid计算加到本任务树中。PSS/USS、VmSize、cgroup memory.current、RSS+swap不能悄悄替代已声明的RSS Gate。

启动前记录实际MemTotal、MemAvailable、cgroup祖先限制、邻近负载和必要系统余量；若实际环境连上述Gate及合理余量都不能容纳，启动前说明冲突，不悄悄降低门槛。运行中MemAvailable及系统压力只记录和告警，不另以旧reserve线或预测分配量中断。本条是本轮用户对旧资源停止规则的覆盖，不是把整个2 TB交给本任务独占。

这只改变**资源政策触发条件**：用户主动停止、真正数值/物理失败、不可恢复的实现或I/O错误、迭代上限、以及持续丢失监控仍必须明确处理，不要求崩溃程序继续运行。监控丢失不能假报RSS超限；PID正常退出导致的尾样本消失也不能制造第二个根因。短暂读失败先复核PID生命周期并在5秒内至多重采3次，仍无法判断则以MONITORING_LOST收口，不能盲跑。

到达Gate由独立watchdog终止本run，先保存触发样本，复用已有整树清场机制；不能为了等待某次长MUMPS调用返回而持续越线。采样存在间隔，不能保证逐字节无超调。不得修改邻任务或关闭硬件热保护；操作系统自身的OOM/分配失败、管理员信号也不能由本程序保证永不发生。

### 2.2 必须消除多层规则不一致

D1逐项检查：public launcher、native profile、独立父watchdog、worker `resource_sample`、p4 symbolic/numeric准入、retained/p4凝聚库存检查、后处理checker，以及旧的附加guard。所有属于新run的活动监督器必须报告同一个policy和Gate；不得只改最外层而保留内部global-swap拒绝。

只为新policy增加显式接线，历史profile行为仍可复现。若旧schema的 `require_zero_swap=true` 与新策略冲突，为新输入明确记录false及observe_only含义，保留swap采样；不能保留旧字段为true、后台忽略检查而让结果自称zero-swap。

MUMPS INFOG及对象预测照常记录，但不由它们拒绝numeric或后续H6/Krylov构建。本批新profile不安装基于预测扣减或笔记本额度的ICNTL(23)，用0并读回，由整树RSS监督；不从源分支复制4687 MB等硬额。实际后端错误如实保存，不换排序、BLR或OOC兜底。

不执行全机swapoff、改swappiness、修改系统服务、启用OOC，或为了避免swap告警而额外设置 `memory.swap.max=0`。后者可能改变分配/回收行为，不是“换页只记录”。已有cgroup限制只读披露，不擅自修改。Linux cgroup的 `memory.current`、swap计数和进程RSS不是同一口径，参见[内核cgroup文档](https://docs.kernel.org/admin-guide/cgroup-v2.html)与[/proc文档](https://docs.kernel.org/filesystems/proc.html)。

swap非零时仍可取得本policy下的RSS资格，但明确记录 `SWAP_OBSERVED`，不得标成严格zero-swap通过；仅全机换页而任务未观测到swap时，记录 `GLOBAL_SWAP_OBSERVED_ATTRIBUTION_UNRESOLVED`。若存在换页，资源/耗时表注明影响，不通过隐去swap获得漂亮百分比。

### 2.3 必须先通过的监督测试

用小型进程/注入样本验证，不真实制造系统换页或TB分配：

| 场景 | 新policy预期 |
|---|---|
| RSS低于Gate，全局pswpout按2到73变化 | 记录284 KiB等诊断，继续 |
| RSS低于Gate，任务VmSwap或fault计数增加 | 记录，继续；不宣称zero-swap |
| 实际RSS低于Gate，但symbolic/对象预测超过Gate | 保存预测，允许继续；小MUMPS实例检查ICNTL23=0 |
| RSS达到Gate（小测试缩放到如256 MiB） | 触发一次正确根因、保存样本并清场 |
| 活进程持续不可读、正常退出尾样本、PID复用 | 区分监督失败、正常退出与新进程，不误杀旁支 |
| 新policy经launcher传到worker、p4、checker | 实际生效字段一致；旧zero-swap profile回归不变 |

## 3. 功能迁移边界与固定执行环境

从source_snapshot选择性迁移已测V18准确p4凝聚、V19 p6 retained外层、V20共享缓存/安全生命周期，以及后续已实现的尺寸参数化和affine修复；不要整体merge/cherry-pick `task39extra`。D0写最小migration manifest，逐文件列来源blob/commit、依赖、目标差异与测试，不复制失败BLR、宏块、bubble、旧任务预算或整套历史runner。

优先核对以下实际路径及其import依赖：

```text
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/hcurl_affine_isotropic_tensor.py
src/solvers/p4_cell_condensed_inverse.py
src/runners/physical_p4_cell_condensed_v18.py
src/runners/physical_retained_outer_adapter.py
src/runners/physical_dual_cell_condensed_lowmem_v20.py
src/runners/physical_p4_schur_v14.py
src/solvers/physical_balanced_coupling.py
src/solvers/physical_reference_diagnostics.py
src/solvers/physical_light_setup.py
src/solvers/fullspace_partial_assembly.py
```

retained adapter实际位于 `src/runners/`，不是源Review V22建议清单中的 `src/solvers/` 同名路径。源review列出的尚未存在模块/性能实现只能当待开发建议，不能当已测依赖。源branch如继续前进，只额外读取相关已提交修复并登记SHA；不能自动追随其HEAD、把笔记本多核试验并入本批或等待其全部研究完成。

工作站继续现有独立canonical/worktree；不得操作笔记本或Hybrid的文件、环境、进程及Git refs。先确认旧2 nm后代已清理；若现场还有本任务正在运行的进程，不在运行工作树pull/改源码，使用独立文档工作树处理版本。必要更新fast-forward，不reset、amend或强推。

**新5 nm实际计算固定逻辑CPU23、MPI1、全部数学库线程1；父监督器固定CPU9。** 不复制源V22的2/4线程试验，不通过迁到更快CPU、改NUMA或更换BLAS来混合收益。沿已记录的preferred_node1/允许节点0,1做单次对照，保存实际页分布、频率/温度和邻近负载；共享资源影响注明，不承诺完全隔离。若现场硬件存在需停机处置的故障，先报告，不关闭保护强行运行。

优先使用本工作站现有已资格化的task-local complex128/int64/PORD64栈并做真实小例检查，不复制WSL的 `.venv`/二进制或改系统安装。旧5 nm运行与新ABI不同时必须明示；结果比较属于方法与实现的工程比较，不声称只有一个变量变化。编译/缓存/临时/结果路径仍为本任务独立可写目录。

## 4. 双凝聚数学合同与p4精度修复

### 4.1 “双凝聚”具体改变什么

p6和p4都在每个单元内消去内部自由度。p6外层只迭代独立trace加端口，Schur作用保持matrix-free；p4只装配trace加端口系统并建立一份全局准确LU，每次粗修正缩减RHS、回代并恢复完整p4场。不能先形成原完整全局矩阵再凝聚，也不能为证明省内存而同时长期保留新旧全局矩阵。

一般复非Hermitian增广块写为：

```math
\mathcal A_p=
\begin{bmatrix}
V_{ii}&V_{it}&B_i\\
V_{ti}&V_{tt}&B_t\\
-D_i&-D_t&H_p
\end{bmatrix},\qquad
\mathcal S_p=
\begin{bmatrix}
V_{tt}-V_{ti}V_{ii}^{-1}V_{it}&B_t-V_{ti}V_{ii}^{-1}B_i\\
-(D_t-D_iV_{ii}^{-1}V_{it})&H_p+D_iV_{ii}^{-1}B_i
\end{bmatrix}.
```

```math
\widehat b_p=
\begin{bmatrix}b_t-V_{ti}V_{ii}^{-1}b_i\\b_p+D_iV_{ii}^{-1}b_i\end{bmatrix},
\qquad u_i=V_{ii}^{-1}(b_i-V_{it}u_t-B_i a).
```

这里第二个式子的 `b_p` 是端口右端，`a`是端口未知量。内部、端口RHS不得假定为零；测试必须包含非零Bi/Di。完整curl与复质量张量相加之后再凝聚，不能分别凝聚后相加；非Hermitian左耦合不能替换成右耦合的共轭转置。原H_p与凝聚后Hhat严格分开。

共享局部LU/Schur/恢复缓存按实际几何、材料、积分及方向身份分类。不得按舍入后尺寸错误合并不同单元，不要求整个器件沿z可分离，不降低积分规则。对本次仿射六面体可复用已资格化参考张量组装，但保留与原FFCx的实际局部/整体作用核验。

### 4.2 保留完整空间BAL_H，通过已测J桥接到retained外层

```math
A_4=P_{64}^{H}A_6P_{64},\qquad
C=P_{64}A_4^{-1}P_{64}^{H},\qquad
\mathcal B_{6,H}=C+(I-CA_6)H_6(I-A_6C).
```

retained残差通过J的共轭转置注入完整FE加端口空间，内部置零，原端口逆与BAL_H处理后再由J提取。按源V19的符号合同：

```math
w=r_{FE}-BH_p^{-1}r_p,\qquad z=\mathcal B_{6,H}w,\qquad
 a=H_p^{-1}(r_p+Dz),\qquad
\mathcal M_{\Gamma,6}=J\mathcal M_{aug}J^H.
```

**不能只截取P64的trace行，再假定S4是S6的直接Galerkin粗算子；凝聚与p传递一般不交换。** 迁移实际逆桥和对应反例测试，而不根据上述简写重新造一个PC。J不重复施加Floquet约束，primal/backsubstitution与dual共轭累加分开，p4/PC返回严格slave-zero。

零初值指retained未知量为零；非零内部RHS的恢复特解可以使对应完整初始场不为零。必须保存初始化语义；不能为对齐旧完整空间零解而错误丢掉内部载荷。外层收敛最终由原A6完整场残差判定，不仅看Schur或预条件残差。

### 4.3 p4每次返回必须合格，最多两次同因子精化

源h7.5已暴露一次p4质量超限，不能迁移“超限但仍返回、最后checker再失败”的行为。定义F4为当前一次凝聚缩减、准确trace/port回代和完整恢复。每个非零原g先得c=F4(g)，再计算原A4残差r=g-A4c；若rho=norm(r)/norm(g)>1e-10，按顺序至多两次：

```math
\delta c=F_4(r),\qquad c\leftarrow c+\delta c,\qquad
r\leftarrow g-A_4c.
```

始终用最初g归一化，完整记录裸值和各次精化值。零RHS直接返回零；近零输入沿既有严格绝对例外，不用任意放大分母获得通过。先排除映射/符号/原A4评价错误，不能用精化掩盖不同算子。

合格才返回外层；两次修正后仍超限或非有限，保存当前g/c/残差及矩阵身份，停止该case为P4_NUMERICAL_UNQUALIFIED，不换PC、排序或阈值。复用同一因子，不为精化重新factor。逻辑p4次数、物理MatSolve次数和精化次数分开；每次BAL_H仍两次逻辑p4，额外setup PC另计。此修复是本review明确授权，不能声称源V22已完成它。

## 5. 唯一正式目标与不变的物理身份

旧模型由 [5 nm compact](outcomes/records/5nm_formal_attempt1.json) 绑定，run为 `20260911T065955.813489Z`，source `85a681b9bd61104466888546b83df87c27806169`：

```text
old_input_sha256    = 773b5f3ac5f3636a31209b2150c0de9109899514805db13008d35f942281ecf8
old_physical_sha256 = 96b548e4cd7fbec7f5397d6be7fa22cf5f9e0faaaeb2f70ff95cf01f0f8af88d
old_resolved_sha256 = 6f529f67b179bad64fa12b06f5b06428abe5fc8477bcec1c037d2a73922de058
```

| 对象 | 新场冻结要求 |
|---|---|
| 波长/入射 | 5 nm、1度掠入射、azimuth0、s、electric amplitude1 |
| 材料 | 用户给定Si、density2.33 g/cm3、n=0.99396854453+0.00435380777i，epsilon=n*n；air1、mu1 |
| 几何 | 50×25 nm周期，z=-10…130 nm；原grating宽17×25 nm、高120 nm、substrate10 nm；无notch |
| 网格 | 原5 nm p6/h4 boundary-fitted affine hex；逐坐标/单元/材料/约束身份与旧场核对 |
| p空间 | 原p6与同网格p4；变的是求解表示和局部消元，不改有限元物理离散 |
| 边界 | 双Floquet、原Fourier-DtN、完整600通道及积分；不是源13.5 nm的80通道 |
| 输出 | 原探针top127.5/bottom-7.5 nm；原内部平面10/30/60/90/110 nm、采样坐标和侧别 |
| 迭代 | right FGMRES32、max2048、一次KSP、zero retained start，无旧场warm-start或recycling |
| H6 | 原positive算子、degree3与power10/seed规则；不减少检查或平滑次数提速 |
| 时间 | time_limit_mode=none；不以旧1800秒、预计30天或历史费用提前终止 |

材料在旧task中曾标W，后续用户执行记录已指定Si；本次沿上述旧5 nm的数值与名称，不擅自换材料或重新查库替换参数。新input/resolved/source重新计算hash，不硬填旧input SHA；physical SHA应保持同一语义，若schema改变则逐字段证明，不通过改物理来匹配字符串。

不可迁移源h7.5的990单元、notch union或neutral alignment planes来改变本次h4网格；也不沿用173802/51272等13.5 nm行数常量。所有full/interior/slave/trace/port counts从新实际对象计算，80-channel硬编码必须变为输入完整inventory。官方DtN600通道与采样Fourier150条诊断量不同，不能混用。

第128步只保留真实残差/进展记录，不以旧完整空间的0.01或周期经验线提前终止新Schur外层。max2048和所有最终数值/物理Gate不变；不能把历史698或源112当预设步数、保证或上限。若未收敛到2048步，如实数值收口，不增加restart/次数抽签。

## 6. 实施与验证顺序

| 阶段 | 工作 | 通过后行为 |
|---|---|---|
| D0 | 核对两端SHA/规则、旧2 nm清场和旧5 nm数据；列最小迁移清单和固定运行身份 | 明确继承与不做项后继续，不等待另一个分支完成研究 |
| D1 | 新资源policy全链路接线及第2.3节小监督测试 | 真实采样/清场通过后允许后续构建 |
| D2 | 双凝聚核心、J桥、共享缓存/生命周期、动态600模式、p4有界精化和小型实际FE资格 | 提交clean实现后直接进入D3 |
| D3 | 一场新5 nm p6/h4，CPU23、MPI1/线程1；完整恢复/原A6及物理核验、资源闭环 | 完成即比较并收口，不自动跑2 nm |
| D4 | 原数组checker、历史对照、负结果/缺项及response_v5 | 同分支提交推送，等待集中review，不merge |

D2合并成一次有区分力的组件批次：小型复非Hermitian块、非零内部/端口RHS及Bi/Di、真实p6/p4单元、MPC复相位/方向、condensed/native原方程等价、非交换反例、输入不变与恢复、精化计数、矩阵生命周期；不能全部用mock，也不为每个函数重建大因子。包含5 nm实际材料/积分/几何类和与600模式相关的输入检查，13.5 nm只作必要组件回归，不重跑历史564/112步整场。

5 nm setup/action/身份核验可在D3同一run、同一份对象上完成后直接进入KSP，不要为了阶段审查重建一次factor。本批不要求再跑整场旧方法，也不把短波高精度full-direct作为新增前置条件。必要实现错误可最小修复，正式重放至多一次并登记根因、新source和旧失败；无提速、内存回退、数值困难或预测不好不属于bug replay。

正式唯一公开入口：

```bash
python scripts/run_case.py input/task39extra_para_workstation_capacity/original_5nm_si_p6h4_dual_condensed_v3.dat
```

activation、cwd和绑核在同一个native shell；保持已工作的独立服务/launcher生命周期，不受SSH窗口关闭影响，不嵌套MPI。源码/profile/ABI在正式前冻结，运行中不修改。共享工作站并跑许可沿既有用户记录，但本任务自己一次只运行一个heavy；不得操作邻任务，实测并跑影响进入对照限定。

## 7. 成功判据、完整场与生命周期

| Gate | 要求 |
|---|---|
| 全问题收敛 | 完整恢复后独立重算原A6：norm(b-A6u)/norm(b)<=1e-6；Schur残差另列 |
| p4返回 | 每次最终原A4 rho<=1e-10；精化最多2，全部裸/修正残差可查 |
| 代数正确性 | 局部/完整作用、RHS缩减/恢复、J逆桥等价<=1e-10操作尺度；约束保留原更严检查 |
| 接口/内部/端口 | 内部方程与端口闭合按源资格，端口闭合<=1e-8；原Hp和Hhat分列 |
| 自身物理一致性 | abs(R+T+A_volume-1)<=1e-5，abs(A_balance-A_volume)<=1e-5；全部E/H、curl、幅值和功率finite |
| 对旧5 nm总量 | R/T/A/A_volume最大绝对差<=1e-5 |
| 对旧5 nm场 | 可读且canonical对齐的L2/scaled-curl、相同坐标selected E/H相对差<=1e-4；近零量同时报告绝对误差，无整体相位拟合 |
| 对旧600模式 | 集合、顺序映射/偏振/侧别/归一化可靠；全部复振幅向量相对差<=1e-4，逐通道功率最大绝对差<=1e-6 |
| 资源 | 新policy下完整采样及正确清场；RSS/交换/后端内存分列，不能再以全机swap否决数值结果 |

参考解只用于独立比较，不能进入初值/PC/基函数选择。旧完整场缺失时优先按既有路径读取本任务raw，不为补缺项重跑60小时旧场；仍比较已有600通道和own Gate，将缺少的场比较标为 `REFERENCE_ARRAYS_PARTIAL`，不能声称完整场等价。旧解只是同离散迭代对照，比较通过也不是网格收敛或连续真解资格。

迁移源V20的安全生命周期：准备必须的编译，构建p4一份凝聚因子及共享p6缓存；不照搬不相容的factor-only detach。源后端存在 `MATRIX_RETAINED_BACKEND_DEPENDENCY` 时，矩阵必须活到后端不再使用；不为减RSS提前销毁引发非法内存访问。

成功后先恢复并保存足够的完整p6场/最小recovery packet、核验原A6，再销毁KSP/p4 factor及无用矩阵；p6恢复所需局部LU不能提前释放。仅保留独立残差及后处理必需对象，完成释放后的同场残差/身份核验和E/H/RTA，再清场。不要为了释放后检查重建大矩阵或factor；必要独立action提前准备。RSS未下降如实记，不强行heap trim或虚报释放量。

中途受控停止保存最后安全解及其retained/full-space身份、原输入/source/资源触发证据；没有完整合格场就不生成official结果。允许离线恢复同一个已保存合格解，不把输出bug变成新的大PDE重跑。

## 8. 与旧5 nm的内存和耗时比较

固定旧分母如下，来自本分支已有compact，不从笔记本13.5 nm借用数字：

| 指标 | 旧5 nm p6/h4 fullspace BAL_H | 口径 |
|---|---:|---|
| 外层步数 / matvec / PC | 698 / 719 / 698 | measured |
| p4逻辑RHS / MatSolve / refinement | 1396 / 1419 / 23 | measured |
| solve时间 | 206568.51908412296 s，即57.38 h | 历史记录口径 |
| full workflow时间 | 217665.16384237396 s，即60.46 h | 历史记录口径 |
| 观察到的整树RSS峰 | 50161172480 B，即50.161 GB | measured observed peak；有约8h34m监督断档，不是完整峰值authority |
| 原A6最终残差 | 9.986638454029182e-7 | measured |
| R / T | 0.7331834812424759 / 0.00022243948430485038 | own输出已通过，reference-limited |
| A / A_volume | 0.26659407927321926 / 0.26659407694262094 | own能量差约2.33e-9 |

新旧至少并列表格：full/interior/slave/trace/port rows，p4 stored/allocated NNZ和factor entries，去重缓存/临时payload，setup/单元张量/assembly/symbolic/numeric/H6/PC/KSP/原残差检查/输出/清场时间，迭代及全部嵌套调用，全程与阶段RSS/PSS、swap/全机换页、可用RAM、CPU/NUMA/ABI/JIT与邻近负载。

```math
S_{\mathrm{workflow}}=217665.16384237396/T_{\mathrm{new,workflow}},\qquad
S_{\mathrm{solve}}=206568.51908412296/T_{\mathrm{new,solve}}.
```

只有计时边界/时钟口径对齐时给对应比值；monotonic、保守ledger和相邻marker区间不混用，工程准备/小测试另列，不从正式run里扣掉实际发生的编译或检查。分开报告迭代数减少和平均每步成本变化，不把少迭代全部称为kernel提速。

旧RSS有断档，只能报告“相对旧已观察峰”的比值和明确限定，**不得给未经支持的完整峰值节省百分比**，也不追认旧RESOURCE_PASS。若以后确需严格同环境完整资源A/B，再另授权旧方法重跑；本批不为补齐表格自动增加60小时计算。

若新场更快但RSS增加，标 `TIME_GAIN_MEMORY_REGRESSION`；更省内存但更慢，标 `MEMORY_TIME_TRADEOFF`；没有收益也如实结束。不把derived缓存bytes、MUMPS allocated/used或矩阵payload当成RSS，不把两个版本最优指标拼接。新policy允许观察到swap不等于仍满足历史zero-swap资格。

## 9. 提交、证据与最终回应

建议正常提交：D1资源policy与测试；D2最小迁移、p4返回修复、动态模式/输入与回归；冻结clean D3 source；新5 nm结果；D4文档收口。全部只推送 `task39extra_para_workstation_capacity`。源task39extra、Hybrid、master、旧raw/输入/profile只读，不amend、强推或整体合并。新review不替代Codex实现，本次ChatGPT只提交本文件。

至少交付本任务目录：

```text
response_v5.md
outcomes/dual_condensed_5nm_v3.md
outcomes/records/dual_condensed_v3_migration.json
outcomes/records/dual_condensed_v3_resource_policy_tests.json
outcomes/records/dual_condensed_v3_component_qualification.json
outcomes/records/dual_condensed_5nm_v3_compact.json
outcomes/records/dual_condensed_5nm_v3_checker.json
outcomes/records/dual_condensed_5nm_v3_comparison.json
outcomes/records/run_index.json
outcomes/summary.md
outcomes/test_summary.md
```

可以合并相邻小证据，避免重复账本；上述信息不能缺。每个正式run保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json，以及环境/MPI/线程、网格/模式、实际policy/Gate、阶段事件、资源覆盖与artifact hash。矩阵、因子、全场、长日志和缓存仅放ignored；每次PC写标量摘要，故障前保存必要向量，不逐调用导出巨量全场。

更新本分支 `docs/development_progress.md` 和 `docs/development_model_registry.md`，保留2 nm旧失败与5 nm旧资源限制。定向真实FE/监督/旧profile回归、compileall/diff、文档合同和GitHub渲染检查真实报告；未跑全库测试/CI不写通过。

Response V5第一屏必须说明：换页是否已在所有层面改为仅记录；实际RSS Gate和CPU23/MPI1是否生效；迁移了哪些已测双凝聚组件及额外p4修复；新5 nm的原A6/每次p4/物理与600通道结果；实际全程时间、峰值内存、相对旧方法的可支持收益及限制；是否出现swap；所有未运行项、异常与最终commit。

判定可组合 `DUAL_CONDENSED_5NM_NUMERICS_PHYSICS_PASS`、`RSS_GATE_POLICY_PASS`、`SWAP_OBSERVED`、`REFERENCE_ARRAYS_PARTIAL`、`TIME_GAIN_MEMORY_REGRESSION`、`MEMORY_TIME_TRADEOFF`、`NUMERICAL_FAIL`、`MONITORING_LOST`、`RSS_GATE_STOP`；必须有原始值和解释。完成后统一等待review，不因成功而自动进入2/3/0.7 nm、notch、MPI扩展或新PC路线。

**本批交付的是一个可核验的资源策略修正和一场CPU23上的5 nm双凝聚对照，不是把任何换页都当失败，也不是把双凝聚的加速和节省内存预先写成结论。**
