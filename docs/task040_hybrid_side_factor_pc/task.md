# Task040：Hybrid 可扩展 iterative side inverse 与 side factor 替代

## 0. 任务身份

```text
task                                      = Task040
task_kind                                 = SCALABLE_HYBRID_SIDE_INVERSE_CONTROLLED_CAMPAIGN
status                                    = READY_FOR_CODEX_EXECUTION
repository                                = Rookie1234567/MyFEniCS
base_branch                               = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
base_SHA                                  = 9dc9ac58e05e5422498dade503046f9ae87d13d9
working_branch                            = codex/20260822-task40-hybrid-side-factor-pc
remote_upstream                           = origin/codex/20260822-task40-hybrid-side-factor-pc
branch_creation_authority                 = user explicit instruction on 2026-08-22
Task039_write_or_reclassification         = forbidden
other_branch_write                        = forbidden
master_write_or_merge                     = forbidden
ordinary_default_change                   = forbidden
public_input_entry                        = python scripts/run_case.py <one-case.dat>
primary_case                              = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
primary_blocker                           = bottom/top full sparse exact MUMPS side factors
primary_goal                              = stable lower-memory iterative side inverse with no full-side exact factor
strategic_goal                            = side-PC architecture that remains credible under much denser 0.7 nm meshes
full_0p7nm_PDE                            = forbidden
new_QEP_or_M_study                        = forbidden
dynamic_DtN_redesign                      = forbidden
global_Hybrid_operator_redesign           = forbidden
response_packet_production_route          = forbidden
explicit_side_F_as_operator_authority      = allowed in Task040
full_side_F_factorization                 = forbidden in formal candidate
full_cross_section_factor                 = oracle-only, never a scalable final candidate
matrix_free_side_F_assembly               = deferred; not required for the first controlled qualification
coarse_space_addition                      = forbidden until a true Gate proves it is required
response_required                         = response_v1.md
```

仓库长期规则通常由 Codex 创建执行分支；本任务由用户明确要求 ChatGPT 从 Task039 最新
HEAD 创建 Task040 分支，因此这是一次有记录的用户级覆盖。除分支创建外，角色分工保持：
ChatGPT 负责任务书与 review；Codex 负责实现、测试、正式运行、`outcomes/` 与
`response_v1.md`。

---

## 1. 核心目标与控制变量

Task040 只处理一个 blocker：

> 当前成功的 Hybrid iterative 已经删除 global Hybrid direct factor，但仍同时保存 bottom
> 和 top 两个完整 sparse MUMPS side factors。它们主导 5 nm h4 的完整峰值，并会随网格
> 细化产生超线性 fill，不能直接服务未来 0.7 nm。

本任务的核心问题是：

```text
保持同一个5 nm Hybrid方程、同一个M480模态系统、同一个DtN、同一个global operator和
同一套recovery/physics，只把A_bottom^-1与A_top^-1中的full exact MUMPS side solve替换为
稳定、低内存、可迭代施加的side inverse，能够把内存降到哪里？
```

Task040 不同时修改 QEP、M、external-channel inventory、dynamic DtN、modal Schur、global
Hybrid operator 或 field recovery。这样无论结果正负，都能把变化归因到 side inverse。

### 1.1 “matrix-free/iterative side inverse”的准确含义

Task040 初期允许继续使用当前显式 static-condensed `F_s` 作为**精确 operator carrier**，
用于稳定的矩阵向量作用和独立 true residual。禁止对它做完整 factorization。

因此本任务的第一阶段是：

```text
显式F_s仍存在
但F_s^-1不再由full MUMPS factor施加
而由FGMRES + lower-memory PC近似施加
```

这属于 inverse/action 层面的 matrix-free/iterative 化。把显式 `F_s` 本身进一步改为
cell-wise matrix-free action 是后续变量，不在本任务同时修改。

---

## 2. Task039 继承权威

Task040 从 Task039 base SHA 原样继承全部正、负结果，不修改历史分类。

### 2.1 完整 workflow 基线

| 路径 | 范围 | process-tree RSS peak | 数值/物理状态 | Task040 用途 |
|---|---|---:|---|---|
| Hybrid direct h4 | 完整 workflow | `93.377006531 GiB` | matched reference pass | direct reference |
| exact-side Hybrid iterative h4 | 完整 workflow | `80.025856018 GiB` | five residual、recovery、R/T/A、E/H、canonical、channels pass | 当前最好 iterative authority |
| exact-side outer solve | 完整 workflow | `1` outer iteration | fixed exact block-LDU | 数值 oracle，不是可扩展生产 PC |

### 2.2 side factor 的阶段内存

下表来自同一次 V7 exact-side formal，是同时 process-tree RSS，不是对象字节简单相加：

| 阶段 | RSS | 解释 |
|---|---:|---|
| `bottom_F_ready` | `23.195 GiB` | 尚未建立 bottom factor |
| `bottom_factor_ready` | `49.313 GiB` | 一个完整 bottom factor 驻留 |
| `bottom_construction_cleanup` | `45.386 GiB` | construction 临时对象清理，factor仍驻留 |
| `top_F_ready` | `51.298 GiB` | bottom factor仍在，top F进入 |
| `top_factor_ready` | `79.464 GiB` | bottom/top 两个 factor 同时驻留 |
| `top_woodbury_ready` | `80.025856018 GiB` | 当前完整 workflow 峰值 |
| `modal_schur_ready` | `76.742 GiB` | modal Schur没有产生新峰值 |
| `outer_ksp_setup_ready` | `76.938 GiB` | Krylov storage不是当前主峰 |

阶段差分显示，一个 side exact factor及其 MUMPS/PETSc运行时约增加 `26–28 GiB` RSS。
该差分只用于定位瓶颈，不冒充精确 factor payload。

### 2.3 已有低内存负结果

| 候选 | bottom component peak | 主要思想 | 数值结果 |
|---|---:|---|---|
| six-layer `J1` | 约 `22.27 GiB` | 六个层对角 factors | worst residual约 `45`，失败 |
| `F1/FB1/FB2/FB4` | 约 `22.27 GiB` | 简单 forward/backward 与 defect correction | 不收缩并发散 |
| two-layer `SN2-J` | 约 `22–27 GiB` | `[0,1]/[2,3]/[4,5]` supernode factors | finite后 worst bare-F residual约 `17.09` |
| `J1`-inner-FGMRES | `22.007 GiB` | J1作为side Krylov PC | 16步 residual仍约 `0.997–0.999` |
| raw-load Petrov | 约 `23 GiB` | load-vector coarse basis | rank512仍失败 |

这些结果已经证明：去掉 full-side factor 后，内存结构可以回到 `20–30 GiB` 级；真正
未解决的是如何在该内存级别下稳定传递短波长 Maxwell 波并获得可用的 side inverse。

---

## 3. 冻结物理、离散与软件身份

整个正式 campaign 冻结：

```text
wavelength                         = 5.0 nm
grazing angle                      = 1 deg
azimuth                            = 0 deg
polarization                       = S
geometry/material                  = Task039 h4 formal identity unchanged
finite element                     = p6 Nedelec H(curl)
mesh                               = h4 formal mesh identity unchanged
scalar/index                       = complex128 / inherited PETSc IntType
Floquet x/y                        = unchanged
Hybrid internal modes              = M480 positive + M480 negative
selected-mode packet               = inherited hash-bound Task039 packet
external mode keys/order           = unchanged
static condensation                = unchanged
explicit side F matrices           = unchanged as operator authority
external DtN/Woodbury              = unchanged
modal traction/projection          = unchanged
modal Schur definition/sign/order  = unchanged
global Hybrid MatPython action     = unchanged
recovery/postprocessing/checker    = unchanged
formal MPI                         = 8
threads                            = 1
```

正式 heavy run优先复用已资格化 selected-mode packet，并记录：

```text
qep_calls = 0
consumer_qep_required = false
```

packet、input、physical model、external keys或ABI不一致时停止；不得静默重做 QEP、改 M
或使用另一个物理案例。

---

## 4. 面向 0.7 nm 的可扩展性合同

Task040 不运行完整 0.7 nm PDE，但算法设计必须考虑 0.7 nm 会使用更密网格这一事实。
5 nm h4 的低内存结果只有同时满足下列结构条件，才能称为
`SCALABLE_SIDE_INVERSE_CANDIDATE`。

### 4.1 禁止增长型 factor

正式可扩展候选中必须满足：

```text
full-side exact factor count                   = 0
full-cross-section exact subdomain factor      = 0
global Hybrid direct factor                    = 0
global direct coarse factor                    = 0
FE-sized numeric allgather                     = false
per-rank replicated full basis                 = false
```

横跨整个 x/y 截面的 two-layer factor可以在早期作为**传递机制 oracle**使用，但它的
尺寸会随横截面网格细化增长，因此不能成为 Task040 的最终 0.7 nm-oriented pass。

### 4.2 允许的长期局部 factor

可扩展候选允许小型局部 factors，但必须：

```text
patch/support size由p6局部单元拓扑决定
最大local rows有固定hard cap，不随global side DoF增长
相同exact class复用一个factor
每个factor只由一个deterministic MPI owner保存
patch数量可以随N增长，但单patch factor尺寸不得增长
```

T40-4 必须实测并冻结 `max_local_rows`。硬上限为：

```text
max_local_rows <= 1024
```

若 static-condensed p6 局部拓扑本身超过该上限，按真实 scalability Gate停止，不得通过
扩大上限把增长型 factor包装成可扩展方案。

### 4.3 内存增长目标

对 PC 自身长期 resident payload，目标是近线性：

```math
B_{PC}(N) = O(N)
```

这里的 `N` 是 side active DoF。必须分别报告：

```text
explicit operator carrier bytes
PC retained bytes
local factor total bytes
Krylov vector bytes
construction transient
process-tree RSS peak
```

显式 `F_s` 仍在 Task040 中，因此完整 process-tree peak不要求已经严格线性；但 PC自身不得
重新引入超线性 factor。Task040 结果必须区分：

```text
5NM_MECHANISM_PASS_ONLY
5NM_LOWER_MEMORY_PASS_NOT_0P7NM_SCALABLE
SCALABLE_SIDE_INVERSE_CANDIDATE
```

### 4.4 条件 finer-grid scaling probe

只有 h4 bottom scalable candidate通过数值和资源 Gate后，才允许一次 5 nm finer-grid
bottom setup/apply probe，优先使用 `p6/h3`。该 probe：

```text
不运行top
不运行完整Hybrid
不改变PC参数
不运行QEP
只测operator/PC inventory、一次apply和有限checkpoint
```

开始前必须有资源 preflight；预测峰值超过当前任务可用 hard line时，记录
`not_run_by_resource_preflight`，不得冒险启动。

若 h3 实际运行，PC-specific retained exponent定义为：

```math
p_{mem}
=
\frac{\log(B_{PC,h3}/B_{PC,h4})}
     {\log(N_{h3}/N_{h4})}.
```

战略目标：

```text
p_mem <= 1.30
max_local_rows unchanged
exact-class factor cap unchanged
```

该 probe是扩展性证据，不是空间收敛或0.7 nm PDE资格。

---

## 5. 总体算法路线

Task040 采用两级、严格顺序的控制变量路线。

### 5.1 Level A：impedance transmission 机制 oracle

目的：先判断旧 SN2 失败是否主要来自人工截面的错误波传递，而不是 z 分区思想本身。

固定分区：

```text
subdomain 0 = layers [0,1]
subdomain 1 = layers [2,3]
subdomain 2 = layers [4,5]
```

局部 operator概念上为：

```math
\widetilde B_j
=
R_j F_s R_j^T
+
T_j^-
+
T_j^+,
```

`T_j^-`、`T_j^+` 是人工截面上的固定一阶切向 impedance/Robin 项，仅属于 PC，
不改变精确 `F_s` 方程。

一次 apply固定为：

```text
forward:  0 -> 1 -> 2
backward: 2 -> 1 -> 0
```

Level A 可以临时使用三个 cross-section-spanning exact subdomain factors，以隔离并资格化
transmission 机制。它只允许得到：

```text
TRANSMISSION_MECHANISM_PASS/FAIL
```

即使 h4 内存和收缩很好，也不能据此声称 0.7 nm 可扩展。

### 5.2 Level B：真正可扩展的 local subdomain solve

只有 Level A 所有 mandatory source均稳定收缩时，才进入 Level B。保持以下内容不变：

```text
同一三分区
同一first-order impedance
同一forward/backward顺序
同一bare-F exact operator
```

唯一变化是：删除三个 cross-section-spanning exact subdomain factors，把每个局部 solve改为：

```text
fixed small-restart local FGMRES
+
bounded overlapping patch PC
```

patch PC冻结为：

```text
core                = one owned static-condensed cell trace support
overlap             = shared-entity overlap only
auxiliary form      = coercive H(curl) auxiliary operator
factor storage      = packed complex128 Cholesky per exact class
factor ownership    = one deterministic owner per exact class
PoU                 = owner-consistent partition of unity
source dependence   = forbidden
```

辅助形式概念上为：

```math
B_{0,p}(u,v)
=
\int_{\Omega_p}\mu_r^{-1}\,\mathrm{curl}(u)\cdot
\overline{\mathrm{curl}(v)}\,dx
+
k_0^2\int_{\Omega_p}|\varepsilon_r|u\cdot\overline v\,dx.
```

实际实现必须使用当前 static-condensed trace identity和 finalized constraints，不能照抄
full-space行号或 Task038-extra 的 runner。Task038-extra只可作为小型 packed factor、
orientation、owner routing的只读参考，不得整体 merge/cherry-pick。

本任务初始 Level B 不加入 global/trace-harmonic/local-spectral coarse space。若局部 PC有限、
稳定、内存合格，但 inner residual显示明确长程停滞，则这是一个真正 Gate：

```text
COARSE_INFORMATION_REQUIRED
```

Codex在本任务中不得自行添加 coarse space。

### 5.3 Side inverse 的 Krylov层次

bare side方程：

```math
F_s x=b.
```

使用 right-preconditioned inner FGMRES。固定 checkpoint：

```text
8 -> 16 -> 32 -> conditional 64
```

只有32步时 true residual仍有限、最近8步至少下降 `0.25 decade`、内存/时间 Gate通过，
才允许64。不得测试其他budget、restart或tolerance菜单。

Level B subdomain local FGMRES使用固定小预算，由 T40-4 tiny/component Gate冻结；不得在 h4
formal中再扫描。

### 5.4 Bare `F` 通过后才进入完整 side operator

完整 side equation概念上写为：

```math
A_s x=b,
```

其中 `A_s` 是当前代码既有 FEM + external DtN side action。正负号、C/D/H、normalization
以现有代码和 exact-side authority为准。

必须直接用 FGMRES迭代完整 `A_s` action；禁止把近似 `F_s^{-1}` 代入精确 Woodbury恒等式
后冒充 exact side inverse。DtN实现保持原样，只作为精确 operator action参与迭代。

---

## 6. 严格禁止项

Task040 禁止：

```text
修改波长、材料、几何、角度、偏振、p/h、M或formal MPI
重跑 Hybrid direct
重跑 V7 exact-side full formal
重跑 response-packet producer或继续packet路线
修改 global Hybrid MatPython action
初始campaign中把显式side F改成matrix-free
引入 dynamic/streaming DtN redesign
改变 C/D/H、W/K、external keys或normalization
改变 modal traction/projection/modal Schur
增加 Petrov、trace-harmonic或global coarse space
增加 second-order/rational impedance
扫描 Robin/impedance参数
扫描分区数、supernode组合或sweep count
扫描 ILU/BLR/drop tolerance/restart
继续 J1/F1/FB8/FB16或原SN2-J/SGS
使用response packet作为生产inverse
运行Full3D heavy
运行完整0.7 nm PDE
修改ordinary defaults
写入或合并master、Task039或其他分支
```

唯一预授权的算法 fallback是：Level B nonoverlap稳定收缩但inner FGMRES到64仍未通过时，
允许每个人工接口增加**一层真实 z-layer overlap**。其余参数全部不变，只运行一次完整
bottom component。

---

## 7. Codex 自主修复 implementation bug 的规则

本任务明确允许 Codex 自主修复实现类 bug，不需要每遇到一次 wiring/lifecycle问题就停下
等待 review。只有真正的数学、数值、资源或可扩展性 Gate 才停止。

### 7.1 可自主修复的 implementation failure

包括但不限于：

```text
syntax/import/type错误
路径、目录初始化、marker、schema或SHA透传错误
只读数组、workspace alias、对象destroy顺序或PETSc ownership错误
MPI scatter/gather、owner/ghost、restriction/prolongation接线错误
明显的orientation/phase-once实现错误，且有独立oracle证明
telemetry、watchdog、artifact registry或checker wiring错误
内存泄漏由未释放对象、重复引用或错误生命周期导致
```

处理合同：

```text
保留失败raw/root和implementation_failure分类
先在unit/tiny/MPI test中复现
做最小修复
新增回归测试
以新source SHA重跑同一阶段
通过后自动继续后续阶段
```

实现失败不消耗该算法的正式 numerical Gate attempt；但不得删除、覆盖或把旧失败改写为通过。

### 7.2 不能冒充 bug fix 的算法变化

以下不属于自主 bug fix，未经任务书授权不得修改：

```text
改变物理方程、材料、边界或Floquet约定
改变impedance系数、分区、overlap、sweep次数或ordering
改变FGMRES checkpoint、容差或Gate
增加shift/damping、coarse space、local spectral mode或新的PC family
手动翻转sign以追逐结果，除非独立operator oracle先证明代码接线错误
放宽内存、residual、repeat或linearity阈值
```

### 7.3 真正需要停止的 Gate

完成实现 identity资格后，出现以下任一项才停止并等待 review：

```text
Level A exact-subdomain transmission仍不稳定或不收缩
Level B bounded PC在冻结budget内数值失败
inner residual明确停滞/发散且已用完授权checkpoint
资源hard stop或swap>0
max_local_rows/class/factor ownership违反scalability合同
finer-grid PC exponent或factor cap违反扩展性Gate
bottom通过后同配置top出现不可解释的真实数值Gate
完整Hybrid数值/物理Gate失败
证据表明必须引入coarse/global information
```

正常阶段通过或可修复 implementation failure 均不要求中途 review。Codex应按本任务决策树
连续执行，直到真正 Gate、完整成功或所有授权阶段完成。

---

## 8. 冻结 source family 与诊断

bottom 使用 Task039 已冻结且可重建的 source family：

```text
modal traction positive
modal traction negative
external DtN coupling
fixed random repeat 0
fixed random repeat 1
physical side RHS（若为零，只作zero-map）
```

每个 source记录：

```text
input/output finite
zero-map
repeat
linearity
one-apply contraction
inner true residual checkpoints
KSP reason
PC/subdomain/local apply count
wall
process-tree RSS/PSS/USS（若可用）
swap
```

一次 PC apply contraction定义为：

```math
\rho_b
=
\frac{\lVert b-F_s M_s^{-1}b\rVert_2}
     {\lVert b\rVert_2}.
```

它只表示PC强度，不代替最终 inner true residual。

---

## 9. 数值、资源与扩展性 Gate

### 9.1 实现与代数 Gate

```text
all outputs finite                         = true
zero input maps to zero                    <=1e-13 contract
repeat relative error                      <=1e-10
linearity relative error                   <=1e-10
restriction/prolongation round trip        <=1e-12
MPI2/MPI4 tiny physical identity           <=1e-12
full-side exact factor                     = 0 in formal scalable candidate
global direct factor                       = 0
```

Level A oracle允许三个 cross-section factors，但必须显式标记：

```text
oracle_only = true
scalable_candidate = false
```

### 9.2 One-apply推进 Gate

```text
all mandatory rho                          <1.0
worst mandatory rho for inner-FGMRES start <=0.95
modal+/modal-/external preferred           <=0.90
```

若全部收缩但 worst位于 `(0.95,1.0)`，分类为 `STABLE_BUT_TOO_WEAK`，不启动重型inner solve。

### 9.3 Bare `F` inner FGMRES Gate

首个满足下列条件的checkpoint为preferred：

```text
all mandatory true residual <=1e-2
modal+/modal-/external       <=1e-3
all finite                   =true
swap                         =0
```

若32步没有持续下降，64不得运行。若64仍未通过，按真实原因分类为：

```text
TRANSMISSION_TOO_WEAK
LOCAL_SUBDOMAIN_SOLVER_TOO_WEAK
COARSE_INFORMATION_REQUIRED
```

不得笼统只写 `failed`。

### 9.4 Bottom资源 Gate

当前 exact bottom factor阶段基线：

```text
49.313 GiB process-tree RSS
```

| 分类 | bottom process-tree peak |
|---|---:|
| 无资源收益 | `>=49.313 GiB` |
| 最低正结果 | `<49.313 GiB` |
| meaningful | `<=35 GiB` |
| strong | `<=30 GiB` |

正式 scalable candidate还必须：

```text
post-setup retained state        <=30 GiB
full-side factor                 =0
full-cross-section factor        =0
max_local_rows                   <=1024
swap                             =0
```

### 9.5 完整 `A_bottom` Gate

只有 bare `F_bottom` 的 Level B preferred candidate存在时，才以完全相同配置求完整
`A_bottom`：

```text
all mandatory true residual <=1e-2
modal+/modal-/external       <=1e-3
no full-side/cross-section factor
bottom peak                  <49.313 GiB
```

不得为完整 `A_bottom` 重新调整 impedance、partition、local budget或ordering。

### 9.6 Top、both-side 与完整 Hybrid Gate

bottom通过后，top必须使用完全相同配置，不得单独调参。

bottom/top均通过后先运行 both-side setup-only：

```text
full-side bottom/top factors =0/0
full-cross-section factors   =0
both-side setup peak         <80.025856018 GiB
swap                         =0
```

通过后才允许唯一一次完整 Hybrid formal。由于 side inverse是可变迭代近似，outer使用
FGMRES。沿用 Task039 V7 Gate：

```text
reported/global/bottom/top/modal true residual <=5e-9
projection bottom/top/combined                  <=1e-8
exact traction bottom/top                       <=1e-8
R/T/A/A_volume delta vs matched direct          <=1e-6
selected E/H relative L2                        <=5e-3 / 1e-2
canonical active/full relative L2               <=1e-5
power-weighted channels                         <=1e-4
external keys/order                             =exact
normal flux/orders/powers/amplitudes            =inherited Gate pass
all finite/swap                                 =true/0
```

完整 workflow memory分级：

| 分类 | full workflow peak |
|---|---:|
| 未刷新当前 iterative | `>=80.025856018 GiB` |
| 新最低点 | `<80.025856018 GiB` |
| 至少节省20% vs direct | `<=74.701605225 GiB` |
| 至少节省30% vs direct | `<=65.363904572 GiB` |
| 至少节省40% vs direct | `<=56.026203919 GiB` |
| 至少节省50% vs direct | `<=46.688503266 GiB` |

50%是最强目标，不是唯一成功条件。必须报告真实 memory-residual-time Pareto极限。

---

## 10. 连续执行顺序

```text
T40-0   inherited audit，docs-only
T40-1   exact side F/action/source identity与baseline复核
T40-2   first-order impedance artificial-interface algebra、orientation、MPI identity
T40-3   Level A exact-subdomain transmission oracle：bottom bare-F one-apply contraction
T40-4   Level B bounded patch core、class factor、owner routing与tiny/local solver资格
T40-5   bottom bare-F scalable PC construction + one-apply contraction
T40-6   条件 bottom bare-F inner FGMRES 8/16/32/(64)
T40-7   条件唯一 one-z-layer-overlap fallback
T40-8   preferred配置求完整 A_bottom，DtN保持不变
T40-9   同配置 top bare-F + A_top
T40-10  both-side setup-only
T40-11  条件唯一一次 full Hybrid formal
T40-12  条件 p6/h3 bottom scaling probe
T40-13  outcomes、Pareto、0.7 nm capacity implications、response_v1.md
```

Codex不需要在正常阶段之间等待ChatGPT。只在第7.3列出的真正 Gate、全部阶段完成或完整成功后
停止。

---

## 11. T40-0 第一提交

第一项提交必须为 docs-only：

```text
docs(task040): audit inherited scalable side-inverse baseline
```

创建：

```text
docs/task040_hybrid_side_factor_pc/outcomes/inherited_audit.md
docs/task040_hybrid_side_factor_pc/outcomes/baseline_memory_attribution.md
docs/task040_hybrid_side_factor_pc/outcomes/task038_extra_reference_boundary.md
```

至少记录：

```text
branch/HEAD/upstream/ahead-behind/worktree
base Task039 SHA = 9dc9ac58e05e5422498dade503046f9ae87d13d9
input/resolved/physical/selected-packet hashes
93.377 / 80.026 GiB full baselines
23.195 / 49.313 / 79.464 / 80.026 GiB stage baselines
old J1/F1/FB/SN2/J1-FGMRES negative identities
Task038-extra只读参考文件与non-migration边界
ABI/MPI/threads/MemAvailable/swap/disk/watchdog
全部Task040禁止项和bug/self-repair合同
```

不得夹带Python、input、config、schema或数值运行修改。

---

## 12. 允许修改与代码组织

允许：

```text
在src/solvers/新增通用static-condensed side impedance Schwarz模块
新增bounded local patch/class factor/owner-routing模块
为现有Hybrid side action增加显式opt-in research hook
新增focused tests、tiny MPI tests、参数化runner/checker
新增Task040专用.dat，只表达同一冻结物理和research profile
新增Task040 outcomes、compact records和response
```

数值核心不得只写在task-numbered benchmark脚本。benchmark只负责参数、watchdog、telemetry、
checker和artifact orchestration。

不得整体复制 Task038-extra 文件；选择性参考必须在 inherited audit中列出来源、依赖、改写
原因和fresh tests。

---

## 13. 时间、资源与重型运行

```text
one heavy job at a time
swap = 0
default heavy timeout = 21600 s (6 h)
```

只有已经进入 inner或outer FGMRES，且同时满足：

```text
RSS低于对应exact-factor/full-workflow基线
无NaN/Inf
迭代持续增加
最近90分钟至少4个true-residual checkpoints
残差下降至少0.5 decade，或已接近Gate且趋势明确
外推剩余时间 <=2 h
```

才允许一次延长到总计8小时。setup、factor construction、QEP、direct或尚未开始Krylov的
过程不得延长。

每次heavy记录：

```text
process-tree RSS/PSS/USS（PSS/USS若可用）
swap
max-rank RSS
wall与stage markers
full/cross-section/local factor inventory
KSP residual history
artifact hashes
termination reason
```

---

## 14. 测试与证据

最少顺序：

```text
formula/orientation/unit tests
serial tiny block test
MPI2 tiny physical identity
MPI4 tiny physical identity
bounded patch/class ownership tests
focused existing Hybrid regression
bottom h4 components
conditional top/both/full
conditional h3 scaling component
Ruff/format/compileall
document contract
git diff --check
```

正式 checker从raw重算：

```text
rho
true residual
repeat/linearity
factor inventory与local cap
memory tiers与p_mem
full Hybrid physics deltas
```

不能只信任worker status。

tracked只保存轻量compact JSON/Markdown/config/hash；矩阵、factor、fields、timeline和完整logs
留在ignored `results/` 或 `benchmarks/artifacts/`。

---

## 15. 必需交付物

```text
docs/task040_hybrid_side_factor_pc/outcomes/summary.md
docs/task040_hybrid_side_factor_pc/outcomes/inherited_audit.md
docs/task040_hybrid_side_factor_pc/outcomes/baseline_memory_attribution.md
docs/task040_hybrid_side_factor_pc/outcomes/task038_extra_reference_boundary.md
docs/task040_hybrid_side_factor_pc/outcomes/impedance_interface_identity.md
docs/task040_hybrid_side_factor_pc/outcomes/transmission_mechanism_oracle.md
docs/task040_hybrid_side_factor_pc/outcomes/bounded_patch_pc.md
docs/task040_hybrid_side_factor_pc/outcomes/bottom_bare_f_pc.md
docs/task040_hybrid_side_factor_pc/outcomes/bottom_full_side.md
docs/task040_hybrid_side_factor_pc/outcomes/top_full_side.md
docs/task040_hybrid_side_factor_pc/outcomes/both_side_setup.md
docs/task040_hybrid_side_factor_pc/outcomes/full_hybrid_result.md
docs/task040_hybrid_side_factor_pc/outcomes/h_refinement_scaling.md
docs/task040_hybrid_side_factor_pc/outcomes/memory_residual_time_pareto.md
docs/task040_hybrid_side_factor_pc/outcomes/0p7nm_side_pc_capacity.md
docs/task040_hybrid_side_factor_pc/outcomes/test_summary.md
docs/task040_hybrid_side_factor_pc/response_v1.md
benchmarks/cases/<Task040 case>/records/<compact records>
```

未达到阶段也创建对应 outcome，明确写 `not_run_by_gate` 与停止原因。

`outcomes/summary.md` 必须表格优先，至少包含：

```text
方法/阶段/作用范围
factor inventory与最大local rows
single-apply rho
FGMRES checkpoints
bottom/top/full residual
RSS/wall/swap
相对49.313/80.026/93.377 GiB比较
h4/h3 PC-specific scaling
0.7 nm扩展性分类
失败与未运行项
selective merge分组
```

---

## 16. 完成判定

Task040 不以“必须节省50%”作为唯一完成条件，但不能把只依赖横截面大factor的结果称为
0.7 nm-oriented成功。

### A. Strategic scalable pass

```text
same Hybrid equation
full-side exact factors           =0/0
full-cross-section factors        =0
bounded local-factor contract     =pass
完整数值与物理Gate               =pass
workflow RSS                      <80.025856018 GiB
h-scaling/capacity classification =SCALABLE_SIDE_INVERSE_CANDIDATE
```

并报告20/30/40/50% tier。

### B. 5 nm lower-memory pass, scalability incomplete

```text
完整Hybrid正确且低于80.026 GiB
但仍依赖cross-section factor或缺少h-scaling证据
```

分类必须为：

```text
5NM_LOWER_MEMORY_PASS_NOT_0P7NM_SCALABLE
```

不得提升为战略完成。

### C. Side component pass only

```text
bottom/top side residual通过
full Hybrid因明确后续blocker未完成
```

必须指出 blocker和下一最小步骤。

### D. Bounded true negative

若 Level A、Level B与唯一overlap fallback在冻结合同内仍不能通过，必须给出：

```text
最低实测内存
最佳rho与FGMRES residual
失败source family
factor/local-cap证据
失败属于transmission、local solver还是缺少coarse information
```

最终无论A/B/C/D，都必须回答：

> 在保持其他Hybrid组件不变时，能否用稳定、可扩展的iterative side inverse替代两个exact
> MUMPS side factors；若不能，真正缺失的是哪一类全局信息，而不是继续无边界扫描参数。
