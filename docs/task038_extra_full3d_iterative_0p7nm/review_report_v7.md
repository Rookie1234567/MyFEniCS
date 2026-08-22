# Task038-extra Review Report V7：继续同一分支，关闭 FC3 local-spectral family，转向容量优先的 LOR-native-complex-HX pilot

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V7
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = c4f3cc623f5d641686cd72b7a7d18ab97d5fd574
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 63 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v6.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v6.md
working_branch_continues                = yes; same branch only, by explicit user instruction
new_branch_or_worktree                  = forbidden
selective_merge_now                     = not requested and not authorized
whole_branch_merge_to_master            = forbidden
T1_T2_T3_T4                             = ACCEPTED_AND_FROZEN_PASS
R2_current_physical_dual                = ACCEPTED_AND_FROZEN_PASS
R3_current_difficult_residual           = ACCEPTED_AND_FROZEN_PASS
FC1_all_class_factor_certification      = ACCEPTED_WITH_SCOPE_LIMIT
FC3_complete_N2                         = ACCEPTED_CONTROLLED_RESOURCE_NEGATIVE
bounded_local_spectral_multilevel_v1    = CLOSED_BY_FC3_RESOURCE_HARD_STOP
FC3_rerun_or_memory_tuning              = forbidden
new_primary_lane                        = lor_native_complex_hx_v1
continuous_authorized_batch             = L0 through L5 below, conditional on every prior Gate
mandatory_review_stop                   = after L5 screen or any earlier hard stop
T6_full_solve_and_physics_recovery      = not authorized
T7_h_scaling                            = not authorized
T8_0p7nm_2TiB_audit                     = not authorized in this batch
T9_merge_closeout                       = not authorized
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
amend_rebase_force_push                 = forbidden
response_required                       = response_v7.md
```

本 Review 接受 `response_v6.md` 的主要事实与停止行为：

1. FC1 在 p6/h10、MPI1 上对 26 个 deterministic exact classes 完成统一 local-factor certification；
2. FC1 的局部矩阵、Cholesky factor、dedicated triangular solve、class ownership 与 factor bytes 在其限定范围内通过；
3. FC3 在完整 N2 setup 中完成 local factor 与 local mode build，并进入 `regional_coarse_build`；
4. FC3 的 process-tree peak 达到 `2,228,187,136 B`，超过冻结 hard line `2,000,000,000 B`，watchdog 正确受控停止；
5. FC3 未完成 regional coarse、top-level `Z/AZ/E`、post-setup retained、MPI2、N3 或 N4；
6. 因而当前 `bounded_local_spectral_multilevel_v1` 没有完整 setup 资源资格，正式关闭，不允许继续压缩 rank、mode、factor 或 lifecycle 来追逐 `<2 GB`。

用户明确要求继续使用当前执行分支。本 Review 接受该治理选择：**开发连续性与最终 selective merge 是两个不同问题**。继续同一分支可以保留完整 provenance、负结果和跨阶段代码依赖；但这不意味着将来允许整体 merge。当前分支会继续作为 Task038-extra 的研究执行分支，最终进入 `master` 的内容仍必须按文件、依赖、测试和证据选择性审阅。

下一候选不能再次堆叠 local spectral modes、regional basis 或 top-level dense coarse，也不能简单重做旧 AMS/HX。新路线冻结为：

```text
high-order p6 complex full-space exact action remains matrix-free
+
low-order-refined lowest-order H(curl) auxiliary discretization
+
native complex PETSc auxiliary-space / Hiptmair-Xu-style preconditioner
+
scalar nodal PCGAMG only on positive H1 auxiliary operators
```

简称：

```text
lor_native_complex_hx_v1
```

它的核心目标是：用一个稀疏、分布式、低阶 refined de Rham complex 取代当前显式保存的 252 patch modes、regional `Z16`、top `Z32/AZ32` 和 local spectral hierarchy；同时避免当前环境中已知不安全的 direct complex hypre AMS，也避免将整个 complex Maxwell 系统扩成重复内存的 `2N x 2N` real-split production operator。

---

# 1. 对 Response V6 的审阅结论

## 1.1 Git、范围与停止行为

| 审阅项 | 结果 | 说明 |
|---|---|---|
| base / merge-base | pass | 均为 `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| reviewed HEAD | pass | `c4f3cc623f5d641686cd72b7a7d18ab97d5fd574` |
| branch relation | pass | 审阅时 `ahead 63 / behind 0` |
| same branch | required | 按用户明确指令继续当前分支 |
| ordinary default | unchanged | `full3d_iterative` 仍为显式 opt-in research method |
| master | unchanged | 未 merge、未写入 `master` |
| old evidence | preserved | N2 v1/v2、LA v1/v2/v3、FC1、FC3 均未删除或重分类 |
| FC3 stop | accepted | 达到 2 GB hard line 后未进入 FC4/N3/N4 |
| full 0.7 nm PDE | correctly not_run | 没有运行或伪造结果 |

Codex 拉取本 Review 后，开始 L0 前必须重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
Python/MPI/PETSc/SLEPc/DOLFINx/Basix/SciPy ABI
PETSc ScalarType/IntType
PETSc version and available PC types
OMP/OpenBLAS/MKL/NUMEXPR threads
MemAvailable
system/process-tree/cgroup swap state
disk free
```

远端审阅无法观察本地 ignored artifacts 和 nonignored untracked 文件。工作树、ABI、threads、资源或 source identity 不合格时不得开始 L0。

## 1.2 接受并冻结的正成果

| 资产 | 当前身份 | 后续用途 |
|---|---|---|
| T1 `.dat` contract | frozen pass | one-dat/one-run、resolved config、manifest 与 provenance |
| T2 full-space volume action | frozen pass | high-order exact physical volume action |
| T3 dynamic streaming Fourier-DtN | frozen pass | exact top/bottom open-boundary action |
| T4 owner-local MPC/Floquet topology | frozen pass | physical row identity、ownership、phase once |
| R2 current physical-dual oracle | frozen pass | 当前 physical RHS/component authority |
| R3 difficult residual | frozen pass | 当前 long-tail source |
| FC1 all-class local factor audit | scoped pass | 证明 p6 local B0/factor数值稳定；不作为新PC架构 |
| dedicated triangular solve | research fix | 保留正确三角求解语义；不等于完整N2通过 |
| watchdog/provenance | reusable pass | cold setup、online、swap、termination authority |
| canonical primal/dual packets | reusable pass | MPI identity和跨方法比较 |

这些结果不能推导：

```text
FC3 complete setup pass
local-spectral PC pass
LOR transfer pass
native-complex HX pass
N3 contraction pass
N4 iterative screen pass
complete workflow < 2 GB
0.7 nm feasibility pass
```

## 1.3 FC1 的接受边界

FC1 的正式事实为：

```text
exact classes             = 26
rows per class            = 882
all processed/all pass    = true/true
total packed factor bytes = 161,991,648 B
process-tree peak         = 1,547,800,576 B
swap                      = 0 B
```

最坏局部指标仍满足 prospective certification-v2：

```text
max kappa2                = 5.768906342088295e7 < 1e8
max factorization defect  = 9.360591063492774e-16
max ordinary residual     = 1.1713789755077614e-11 < 1e-10
max normalized backward   = 9.83496351829931e-19
```

该正结果只说明局部 B0 与 factor不是 FC3 的失败根因。它不能证明 252 patch mode payload、regional/top coarse、outer PC 或 full workflow 可扩展。

## 1.4 FC3 的正式资源裁决

FC3 的权威资源结果为：

```text
process-tree peak RSS = 2,228,187,136 B
hard line             = 2,000,000,000 B
excess                =   228,187,136 B
swap                  = 0 B
stop                  = hard_stop_2gb
no orphan             = true
SIGKILL required      = false
```

实际 marker authority：

```text
preflight
→ mesh_space_mpc
→ JIT
→ subdomain_inventory
→ local_factor_build
→ local_mode_build
→ regional_coarse_build started
```

未完成：

```text
regional coarse result
top-level build
Z/AZ/E
post-setup retained
identity apply
canonical evidence
MPI2
N3
N4
```

因此 `2.228 GB` 是未完成 setup 的 measured lower boundary，不是“完整 workflow 只差 228 MB”。即使释放当前 transient，后续 top-level、AZ、coarse workspace和Krylov仍未计入。当前 family正式分类为：

```text
BOUNDED_LOCAL_SPECTRAL_MULTILEVEL_V1
= CLOSED_BY_FC3_RESOURCE_HARD_STOP
```

禁止：

```text
重跑FC3
减少regional/top rank后重跑
减少每patch modes后重跑
改变factor class cap后重跑
拆分watchdog或预热cache
把setup阶段移出process-tree统计
只报告online而隐藏cold setup
```

---

# 2. 为什么继续同一分支，但仍保留 selective-merge 边界

## 2.1 两者不等价

继续同一分支回答的是：

> 后续研究历史、代码和证据放在哪里？

selective merge回答的是：

> 最终哪些文件和能力有资格进入 `master`？

当前用户选择继续同一分支是合理的，因为：

```text
T2/T3/R2/R3是新路线的直接依赖
旧负结果需要与新结果同一provenance链保存
无需复制或cherry-pick大量研究基础设施
```

但当前分支已经包含多个明确关闭的 research family。若未来整体 merge，会把：

```text
second-order transmission
closed sweep family
trace-harmonic family
local-spectral multilevel family
未资格化runner/checker exposure
```

一并带入 `master`，这仍然不允许。

## 2.2 本 Review 的治理决定

```text
same branch development       = authorized
new branch/worktree           = forbidden
whole branch merge            = forbidden
selective merge preparation   = postponed
closed family code deletion   = forbidden
closed family reactivation    = forbidden
```

新 LOR/HX 文件必须使用独立命名、独立 runner/checker、独立 records schema和独立 outcome文档，不能悄悄复用 closed family 的 production入口。

---

# 3. 历史 AMS/HX 路线审计：新任务不能重复什么

本 Review 在设计新路线前重新读取了以下历史结果：

```text
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md
docs/task013_real_split_ams_hx_qualification/outcomes/summary.md
docs/task013_real_split_ams_hx_qualification/outcomes/solver_profile_ranking.md
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/solver_profile_ranking.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md
docs/task024_engineering_iterative_solver_fast_track/outcomes/summary.md
```

## 3.1 Task011：direct complex AMS 已被本环境否定

Task011 已证明：

```text
real FE-only positive Maxwell + hypre AMS = 有正信号
complex PETSc/hypre AMS minimal smoke      = malloc invalid size / signal 11
```

因此本 Review禁止把当前 complex128 Fine operator直接交给：

```text
pc_type=hypre
pc_hypre_type=ams
```

也禁止用“新版文档支持complex”替代当前 PETSc 3.19/DOLFINx ABI 的本地负证据。

## 3.2 Task013：real-split same-H1 AMS 不是新路线

Task013 的最好 FE-only result：

```text
p2/h5
real-split AMS/HX
same-H1 auxiliary
310 iterations
true residual ≈ 9.964e-7
RSS ≈ 1.323 GB
```

它说明 real-split auxiliary-space有局部正信号，但：

```text
不是p6
不是full-space matrix-free+streaming DtN
不是LOR
不是200步内的强收敛
```

本 Review不授权简单复制 Task013的 `2N` real block作为新 p6 production候选。

## 3.3 Task014a：旧 Stage4 FE-AMS + aux identity不足

Task014a 的 default100 reduced Stage4：

```text
Jacobi residual ≈ 3.436e-2 after 1000
FE-AMS residual ≈ 2.147e-2 after 1000
improvement ≈ 1.60x
```

未达到可用收敛。旧方法还包含显式 DtN auxiliary unknown block，并把 auxiliary block近似为 identity。当前 Task038-extra 已采用 streaming DtN action，不再是同一增广系统。

## 3.4 Task023/024：FE-response和same-H1 hierarchy未形成高分辨率突破

Task023在h5闭合，但h2的ASM/ILU、selected response和local LU路线均失败或进入资源/时间边界。Task024的h2/h1.5低内存结果仍停在 residual约 `0.15–0.18`，没有达到相对历史基线的显著收益。

因此新路线必须与这些旧方法有清楚结构差异：

| 维度 | 旧 Task011–024 | 新 V7 要求 |
|---|---|---|
| high-order fine A | 多为assembled或旧augmented Stage4 | 当前T2/T3 complex matrix-free exact A |
| auxiliary edge space | same-order/same-H1或旧FE block | p-refined mesh上的lowest-order LOR H(curl) |
| scalar mode | direct complex hypre不安全；real split会2N化 | native complex PETSc，auxiliary matrices为real-entry complex AIJ |
| H(curl) multilevel | hypre AMS black-box | 自主构造LOR transfer + native HX decomposition |
| DtN | explicit auxiliary block/identity近似 | exact streaming DtN只在fine A；PC保持positive volume auxiliary |
| global coarse | response columns或custom dense basis | distributed nodal GAMG hierarchy；无global direct coarse |
| memory | high-order AMS/same-H1 hierarchy常偏大 | L0先闭合LOR matrix+nodal hierarchy+Krylov完整预算 |

---

# 4. 新主线解决什么 blocker

当前 blocker不是：

```text
local Cholesky不稳定
matrix-free action错误
DtN action错误
physical RHS identity不明
```

当前 blocker是：

> 在不保存 growing slab factors、自定义 patch spectral modes和显式全局 coarse basis的前提下，如何给高阶 full-space H(curl) operator提供近线性内存、p-robust的辅助逆，并对物理与long-tail误差产生足够 contraction？

LOR（low-order refined）思路把每个高阶 tensor-product Nédélec macro element映射到一个细化网格上的lowest-order edge space。对合适的插值/直方插值基，高阶与LOR的质量和curl-curl能量可以保持与h、p无关的谱等价；LOR稀疏矩阵随后可由低阶multigrid处理。

本项目不能直接照搬外部库实现。新任务只借用数学结构，在DOLFINx/Basix/PETSc中自主实现并重新资格化：

```text
high-order p6 fine operator   = matrix-free
high-order ↔ LOR transfer     = local tensor action + owner/ghost communication
LOR edge auxiliary operator  = distributed sparse AIJ
LOR H(curl) inverse           = native complex HX-style auxiliary decomposition
nodal auxiliary inverse      = PETSc PCGAMG on scalar positive H1 matrix
```

这与FC3的差异是：

```text
不保存252 patch x 8 modes
不形成regional Z16
不形成top Z32/AZ32
不保存26 local factors作为主PC
不构造global dense E
```

---

# 5. 冻结数学与算子身份

## 5.1 Exact physical fine operator保持不变

```math
A_h(E,v)
=
\int_\Omega \mu_r^{-1}\,\operatorname{curl}E\cdot\operatorname{curl}\overline v\,dx
-
k_0^2\int_\Omega \epsilon_r E\cdot\overline v\,dx
+
\langle T_{\mathrm{DtN}}E_t,v_t\rangle_{\Gamma_t\cup\Gamma_b}.
```

生产 outer action仍为：

```text
T2 matrix-free high-order volume action
+
T3 dynamic streaming Fourier-DtN
```

禁止改变：

```text
material
geometry
Floquet phase
DtN mode normalization
physical RHS
complex128
high-order p6/h10 anchor
```

## 5.2 Positive high-order auxiliary operator

新的PC不直接近似不定物理A，而是使用唯一冻结的positive auxiliary：

```math
B_h(u,v)
=
\int_\Omega |\mu_r^{-1}|\,\operatorname{curl}u\cdot\operatorname{curl}\overline v\,dx
+
k_0^2\int_\Omega |\epsilon_r|\,u\cdot\overline v\,dx.
```

冻结边界：

```text
no shift scan
no beta scan
no artificial Robin
no DtN term in B_h
no source-dependent coefficient
no residual-derived basis
```

`B_h`只是PC辅助算子。最终数值仍以exact `A_h` true residual裁决。

## 5.3 LOR refined de Rham complex

对每个p阶hexa macro cell，构造基于Gauss–Lobatto分点的p-refined低阶网格，并定义：

```text
LOR H1 nodal space
LOR lowest-order H(curl) edge space
LOR lowest-order H(div) face incidence identity（仅oracle需要时）
```

高阶与LOR edge系数通过局部tensor-product interpolation/histopolation变换连接：

```math
T_{H\to L}: V_h^{p,\mathrm{curl}}\rightarrow V_{L}^{1,\mathrm{curl}},
\qquad
T_{L\to H}: V_{L}^{1,\mathrm{curl}}\rightarrow V_h^{p,\mathrm{curl}}.
```

production禁止保存FE-sized dense global transfer matrix。允许：

```text
reference-cell small dense factors
1D tensor factors
owner-local index maps
bounded ghost exchange
matrix-free local transfer action
```

必须保持：

```text
edge orientation
cell orientation
x/y Floquet phase once
MPC slave/master identity
owner-local canonical row identity
```

## 5.4 Native complex HX-style low-order inverse

LOR edge辅助矩阵记为 `B_L`。新PC冻结为：

```math
M_L^{-1}
=
S_e
+
G_L K_0^{-1}G_L^H
+
\sum_{q\in\{x,y,z\}}
\Pi_q K_1^{-1}\Pi_q^H.
```

其中：

```text
S_e      = one fixed damped edge-Jacobi pre/post action, omega=2/3
G_L      = LOR nodal-to-edge discrete gradient
Pi_q     = q方向nodal vector到edge的lowest-order interpolation
K_0/K_1  = positive scalar nodal diffusion+mass auxiliary operators
```

为控制内存，冻结实现为：

```text
one scalar nodal matrix/hierarchy reused sequentially
x/y/z corrections applied sequentially, not stored as three hierarchies
all matrices use current complex PETSc ABI but have real positive coefficients
no real/imag 2N duplication
no hypre AMS
no global direct coarse solve
```

高阶PC为：

```math
M_H^{-1}=T_{L\to H}\,M_L^{-1}\,T_{H\to L}.
```

## 5.5 Nodal multigrid唯一候选

唯一允许的nodal hierarchy为当前PETSc ABI中的：

```text
PCGAMG
pc_gamg_type = agg
```

L0必须从当前PETSc 3.19 runtime `-help`、petsc4py capability和tiny smoke中冻结一套实际支持的显式options。只允许一套，不允许参数扫描。

必须强制：

```text
no PCLU on coarse level
no PCCHOLESKY on coarse level
no PCREDUNDANT/global rank-0 factor
no hypre inner PC
no processor-replicated full coarse matrix
fixed maximum levels
fixed one-cycle apply
```

若当前PETSc 3.19无法在complex ABI中稳定构造scalar nodal PCGAMG，或者无法禁止direct coarse factor，则本lane在L0停止；不得自动切换到hypre、AMGx、Trilinos或新的外部包。

---

# 6. 连续授权批次

本 Review 在同一分支条件授权：

```text
L0  historical/ABI/capacity audit and one tiny PCGAMG capability smoke
→ L1 high-order↔LOR de Rham transfer oracle
→ L2 small p2/p3 native-complex LOR-HX positive-operator oracle
→ L3 p6/h10 cold setup and one-apply resource qualification
→ L4 five-source exact-A contraction qualification
→ L5 conditional T6-S 20/100/150/200 true-residual screen
→ response_v7.md and stop
```

正常通过时L0–L5之间不需要逐阶段等待ChatGPT。任一hard Gate触发时：

```text
保存真实结果
提交轻量compact/docs
写response_v7.md
推送同一分支
停止等待审阅
```

本轮不授权：

```text
T6-F final 1e-6 solve
official E/H recovery
R/T/A/A_volume
full diffraction channels
h10→h5 solver scaling
0.7 nm PDE
2 TiB final feasibility audit
master merge
```

---

# 7. L0：历史、ABI与容量优先审计

## 7.1 目标

L0必须先回答三个问题：

1. 当前PETSc 3.19 complex ABI能否稳定构造并应用一个tiny scalar SPD `PCGAMG(agg)`？
2. p6/h10 LOR edge/nodal topology、AIJ、transfer和hierarchy的完整live-set是否存在可信 `<2 GB`窗口？
3. 新路线是否真的不同于Task011/013/014a/023/024和FC3？

## 7.2 L0必须创建

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/lor_native_complex_hx_preflight.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_preflight_v1.json
```

## 7.3 历史差异审计

必须逐项比较：

```text
Task011 direct complex hypre crash
Task013 real-split same-H1 FE-only
Task014a reduced Stage4 FE-AMS+aux identity
Task023 FE-response service
Task024 large FE response/m=1
Task038-extra FC3 local spectral multilevel
```

并明确：

```text
migrated code count
reused conceptual evidence
forbidden whole-file migration
new independent implementation surface
```

默认只允许复用当前分支已资格化的：

```text
T2/T3 exact action
T4 MPC/Floquet topology
R2/R3 source authority
canonical packet
watchdog/provenance
```

旧Task011–024源码不得整体迁移。

## 7.4 Tiny ABI smoke

只允许一个极小scalar SPD矩阵，验证：

```text
PETSc complex scalar ABI
PCGAMG type availability
pc_gamg_type=agg availability
one setup
one apply
finite output
repeat identity
no direct coarse factor in actual PC tree
clean destroy
```

这不是PDE，不得使用physical mesh或启动heavy worker。

若：

```text
PCGAMG unavailable
setup/apply崩溃
complex result非finite
实际PC tree出现direct coarse factor且无法禁用
```

则L0停止。

## 7.5 LOR容量账本

L0必须闭合以下项目：

```text
high-order T2/T3 runtime baseline
LOR refined vertices/edges/faces/cells
LOR edge AIJ rows/nnz/bytes
scalar nodal AIJ rows/nnz/bytes
discrete gradient bytes
Pi/edge-constant representation bytes
local tensor transfer factors
owner/ghost maps
PCGAMG hierarchy matrix/interpolation/work bytes
outer FGMRES restart20 vectors
source/residual/solution/work vectors
DtN retained data
watchdog/telemetry
recovery packet reserve
JIT/allocator reserve
lifecycle overlap
```

每项必须标记：

```text
measured
exact arithmetic
derived
budget
unknown/not_measured
```

禁止：

```text
用单个AIJ bytes代替整个GAMG hierarchy
用rank RSS代替process-tree
用warm run代替cold setup
把real/imag hierarchy算成只存一半但代码实际复制
用FC1 factor bytes替代LOR matrix/hierarchy
```

## 7.6 L0容量Gate

全部满足才允许L1：

```text
central p6/h10 complete setup+online+Krylov budget < 1,700,000,000 B
hard-upper budget                                  < 1,900,000,000 B
major unknown component                            = none
high-order global AIJ                              = false
real/imag hierarchy duplication                    = false
global direct coarse factor                        = false
FE-sized numeric allgather                         = false
```

正式后续worker仍使用：

```text
warning = 1,800,000,000 B
hard    = 2,000,000,000 B
swap    = 0
```

若L0预算达到或超过1.9GB，不得以“可能还有生命周期优化”为理由进入L1。

---

# 8. L1：high-order ↔ LOR de Rham transfer oracle

## 8.1 作用

L1先验证最核心的新数学资产：高阶Nédélec与lowest-order refined edge空间的映射是否保持方向、周期相位和de Rham结构。

## 8.2 冻结cases

```text
single affine hexahedron: p2, p3, p6
small periodic hexa mesh: p2 MPI1/MPI2, p3 MPI1/MPI2
```

不得运行p6/h10 full domain。

## 8.3 必须验证

### 维数与双向变换

```text
high-order edge dimension == LOR edge dimension
T_HL/T_LH finite
T_LH T_HL identity relative <= 1e-12
T_HL T_LH identity relative <= 1e-12
repeat exact or relative <= 1e-13
```

### de Rham commuting identity

对H1梯度和edge curl相关测试：

```text
||T_HL G_H - G_L T_H1|| / reference <= 1e-12
curl/edge-incidence commuting defect            <= 1e-12
```

### orientation/Floquet/MPC

```text
edge orientation applied once
cell permutation applied once
Floquet phase applied once
slave/master expansion complete
canonical MPI1/MPI2 source/action relative <= 1e-12
```

### 谱等价oracle

对单cell positive auxiliary比较：

```text
B_H
versus
T_HL^H B_L T_HL
```

要求：

```text
all generalized eigenvalues finite and >0
condition of equivalence <= 100 for p2/p3/p6
p6 equivalence condition <= 2 * max(p2,p3 equivalence condition)
```

该Gate用于排除错误basis/transfer，不是宣称已经证明全局理论。

## 8.4 production边界

L1 oracle允许materialize small local dense transfer和small local matrices。production path必须记录：

```text
global_transfer_matrix = false
local_tensor_action     = true
owner_local_maps        = true
numeric_allgather       = false
```

任一identity或spectral Gate失败，停止该lane；不得改GLL节点、basis scaling或orientation convention后在同一批次扫描。

---

# 9. L2：small native-complex LOR-HX positive-operator oracle

## 9.1 cases

```text
p2/h50 MPI1/MPI2
p3/h50 MPI1/MPI2
```

使用positive `B_h/B_L`，不运行physical `A_h`、DtN或R/T/A。

## 9.2 唯一PC结构

```text
one edge Jacobi pre-action, omega=2/3
one gradient nodal correction
three sequential vector-nodal corrections
one edge Jacobi post-action, omega=2/3
one shared scalar PCGAMG hierarchy
one V-cycle per nodal correction
```

禁止：

```text
AMS/hypre
real split
multiple hierarchy candidates
threshold scan
smoother scan
V-cycle count scan
coarse direct solve
```

L0冻结的当前PETSc-supported options不得在L2修改。

## 9.3 数值Gate

对以下positive-operator sources：

```text
deterministic random edge field
gradient field
curl-dominated field
checkerboard/high-frequency field
```

测试：

```text
one-apply rho_B = ||r-B_h M_H^{-1}r||/||r||
```

Gate：

```text
random       <= 0.45
gradient     <= 0.25
curl         <= 0.45
checkerboard <= 0.60
```

并运行固定PCG：

```text
rtol=1e-8
max_it=40
```

要求：

```text
p2/p3均收敛
p3 iterations <= p2 iterations + 10
true residual <=1e-8
MPI1/MPI2 canonical solution/action relative <=1e-12
```

这些Gate只资格化positive auxiliary inverse，不代表physical Maxwell收敛。

---

# 10. L3：p6/h10 cold setup与one-apply资源资格

只有L0–L2全部通过，才允许一次formal p6/h10 MPI1。

## 10.1 setup内容

```text
current T2/T3 exact fine action
p6↔LOR matrix-free transfer
LOR refined topology
LOR edge B_L AIJ
scalar nodal K AIJ
G_L and Pi representation
one shared PCGAMG hierarchy
HX shell/context
one deterministic zero/source-independent apply
```

不得运行physical outer KSP。

## 10.2 必须记录的inventory

```text
high-order rows
LOR vertices/edges/faces/cells
LOR edge rows/nnz
nodal rows/nnz
G rows/cols/nnz
Pi representation
transfer tensor bytes
MPC/Floquet maps
GAMG level count
per-level rows/nnz/matrix bytes
per-level interpolation bytes
coarsest rows and actual KSP/PC type
retained bytes by component
```

## 10.3 资源Gate

```text
cold process-tree peak       < 2,000,000,000 B
post-setup retained live set < 1,700,000,000 B
process-tree swap            = 0 B
warning/hard watchdog        = 1.8/2.0 GB
```

同时：

```text
no global high-order AIJ
no global Schur
no local spectral modes
no Z/AZ/E basis
no direct coarse factor
no rank0 full hierarchy
no FE-sized numeric allgather
```

若cold setup达到2GB，立即关闭；不得尝试降低GAMG levels、threshold或移除一个HX分量来重跑。

## 10.4 one-apply identity

对一个source-independent deterministic vector：

```text
finite output
repeat relative <=1e-13
input not modified
MPC/Floquet phase once
post-apply retained closure
```

MPI2不在L3运行；只有L4前的数值和资源均通过后，L4可选择在MPI1完成五source screen。跨MPI setup identity留给后续审阅，不得在本批次为了增加工作量提前复制完整hierarchy。

---

# 11. L4：五类 exact-A residual contraction

只有L3全部通过，才允许使用current exact physical operator：

```text
A = T2 volume + T3 streaming DtN
```

对每个source只做一次固定PC apply：

```math
z=M_H^{-1}r,
\qquad
\rho=\frac{\|r-Az\|}{\|r\|}.
```

sources与Gate保持和此前T5可比：

| source | Gate |
|---|---:|
| current physical RHS | `rho <= 0.60` |
| R3 current difficult long-tail residual | `rho <= 0.70` |
| checkerboard/high-frequency | `rho <= 0.75` |
| gradient | `rho <= 0.90` |
| curl | `rho <= 0.90` |

附加Gate：

```text
repeat relative <=1e-12
closure identity <=1e-12
process-tree peak <2,000,000,000 B
swap=0
```

所有source必须通过。任何一个失败，关闭：

```text
lor_native_complex_hx_v1
= CLOSED_BY_EXACT_A_CONTRACTION_GATE
```

不得：

```text
增加V-cycle
增加Jacobi steps
加入shift
加入modal coarse
加入residual-derived direction
改变omega
只挑通过的source
```

---

# 12. L5：条件T6-S 20/100/150/200步screen

只有L4全部通过，才允许运行：

```text
right FGMRES
restart=20
max_it=200
zero initial guess
fixed LOR-HX PC
exact true residual checkpoints
```

Gate：

```text
iteration 20  true residual <= 0.40
iteration 100 true residual <= 0.05
iteration 150 true residual <= 0.015
iteration 200 true residual <= 0.005
```

资源：

```text
complete screen process-tree peak <2,000,000,000 B
swap=0
```

必须记录：

```text
preconditioned residual history
exact true residual history
matvec count
PC apply count
wall by setup/online
GAMG apply wall
transfer wall
DtN wall
current/peak RSS
lifecycle release
```

若所有Gate通过，本轮仍必须停止。不得继续：

```text
final 1e-6 solve
E/H recovery
R/T/A
channel comparison
h5 scaling
```

这些只能由下一份Review授权。

---

# 13. Hard-stop矩阵

| 触发项 | 动作 |
|---|---|
| L0 PCGAMG complex ABI不可用或不稳定 | 关闭lane，写response_v7 |
| L0 hard budget `>=1.9 GB`或major unknown不闭合 | 不写solver，停止 |
| L1 transfer/de Rham/Floquet/MPI/spectral Gate失败 | 关闭lane |
| L2 positive auxiliary oracle失败 | 关闭lane |
| L3 cold peak `>=2.0 GB` | watchdog stop，关闭lane |
| L3 retained `>=1.7 GB` | 关闭lane |
| L3发现direct coarse/global replication | 关闭lane |
| L4任一source contraction失败 | 关闭lane |
| L5任一checkpoint或资源Gate失败 | 保存负结果并停止 |
| swap >0 | controlled stop |
| SIGKILL/OOM/orphan | resource failure，禁止重跑掩盖 |

本批次没有第二候选、fallback或参数扫描。

---

# 14. 明确禁止项

```text
重启FC3 local-spectral multilevel
重启Candidate A/B/C transmission
重启trace-harmonic D2
直接complex hypre AMS
real-split 2N production operator
same-H1 AMS复刻
high-order global AIJ
LOR global dense transfer
per-rank full hierarchy replication
global direct coarse factor
PCLU/PCCHOLESKY coarse
residual-derived coarse vectors
Floquet modal deflation追加
Robin/shift/overlap/mode/rank扫描
改变physical model或DtN normalization
完整0.7nm PDE
```

若新路线需要上述任一项才能继续，应停止并由下一份Review重新设计，而不是在实现中自行扩展范围。

---

# 15. 文件、commit与证据合同

## 15.1 建议新增实现文件

命名可在不改变结构的前提下微调，但必须与closed family隔离：

```text
src/solvers/fullspace_lor_transfer.py
src/solvers/fullspace_lor_topology.py
src/solvers/fullspace_lor_auxiliary.py
src/solvers/fullspace_lor_hx.py
benchmarks/run_task038_full3d_lor_hx.py
benchmarks/task038_full3d_lor_hx_checker.py
src/test/test_294_task038_lor_transfer.py
src/test/test_295_task038_lor_hx.py
src/test/test_296_task038_lor_hx_runner.py
```

禁止修改ordinary direct/Hybrid defaults。

## 15.2 Outcome文件

```text
outcomes/lor_native_complex_hx_preflight.md
outcomes/lor_transfer_oracle.md
outcomes/lor_native_complex_hx_oracle.md
outcomes/lor_p6h10_setup.md
outcomes/lor_exact_contraction.md
outcomes/lor_t6_screen.md
outcomes/records/lor_*_v1.json
response_v7.md
```

未运行阶段必须明确写：

```text
not_run
not_run_by_gate
not_authorized
```

不得留空或用planned冒充结果。

## 15.3 Commit计划

建议但不强制每个阶段一个focused commit：

```text
1. L0 docs/preflight
2. L1 transfer/topology oracle
3. L2 native-complex HX oracle
4. L3 p6 setup/records
5. L4/L5 formal results
6. response_v7 docs closeout
```

禁止amend、force push、rebase或删除负结果。

## 15.4 Response V7必须回答

至少逐项回答：

1. branch、HEAD、base、upstream、ahead/behind、worktree、ABI；
2. FC1/FC3和所有closed families是否保持原样；
3. Task011/013/014a/023/024历史差异审计；
4. L0 PCGAMG complex tiny smoke和实际PC tree；
5. LOR exact topology counts与完整容量账本；
6. high↔LOR transfer、commuting、orientation、Floquet、MPI identity；
7. local spectral equivalence区间；
8. L2 positive auxiliary contraction与PCG iterations；
9. L3 p6/h10 cold peak、retained、hierarchy inventory、forbidden audit；
10. L4五source rho、repeat和资源；
11. L5 20/100/150/200 true residual、wall和资源；
12. measured/derived/budget/failed/controlled_stop/not_run分类；
13. T6-F、official physics、T7–T9、0.7nm是否均未运行；
14. selective-merge边界和do-not-merge family；
15. tests、commands、records、raw hashes；
16. 下一轮建议。

---

# 16. 外部方法依据与本项目边界

以下资料只用于方法设计，不替代本仓库formal evidence：

1. W. Pazner, T. Kolev, C. R. Dohrmann, “Low-Order Preconditioning for the High-Order Finite Element de Rham Complex,” *SIAM Journal on Scientific Computing*, DOI `10.1137/22M1486534`。
2. C. R. Dohrmann, “Spectral Equivalence of Low-Order Discretizations for High-Order H(curl) and H(div) Spaces,” *SIAM Journal on Scientific Computing*, DOI `10.1137/21M1392115`。
3. A. T. Barker, T. Kolev, “Matrix-free preconditioning for high-order H(curl) discretizations,” *Numerical Linear Algebra with Applications*, DOI `10.1002/nla.2348`。
4. PETSc `PCGAMG` / `PCGAMGType` current documentation，用于理解aggregation AMG接口；实际实现以本项目PETSc 3.19 runtime capability为唯一权威。
5. PETSc `PCHYPRE`/AMS documentation只作为历史接口背景；当前项目已有direct complex AMS崩溃证据，所以本Review明确禁止该production路径。

这些文献主要覆盖definite Maxwell-type或positive auxiliary operator，并不直接证明本项目的complex、lossy、non-Hermitian、indefinite、Fourier-DtN physical operator会收敛。因此L4五source contraction与L5 true-residual screen是不可省略的科学Gate。

---

# 17. 最终审阅决定

```text
FC1 local-factor certification                    = accepted scoped pass
FC3 complete local-spectral setup                 = accepted controlled resource negative
bounded_local_spectral_multilevel_v1              = closed; no rerun
same execution branch continuation                = authorized by user
selective merge / whole branch merge              = not authorized
new lane lor_native_complex_hx_v1                 = conditionally authorized
L0-L5 continuous execution                        = authorized subject to every Gate
T6-F / official E-H-RTA / T7-T9 / full 0.7nm PDE  = forbidden
```

本 Review 的核心判断是：

> 继续同一分支有利于保持完整研究链，但不改变最终必须 selective merge 的治理边界。FC3 已证明“local factors + patch modes + regional/top spectral coarse”在完整setup中没有 `<2 GB`余量；下一步不再压缩同一family，而是利用当前已资格化的matrix-free exact action，构造p-refined lowest-order de Rham辅助空间，并在当前complex PETSc ABI内自主实现LOR-HX。该路线只有在容量、transfer、positive auxiliary、exact-A contraction和200步screen全部通过时，才有资格进入下一轮。