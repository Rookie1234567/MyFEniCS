# Task038-extra Review Report V4：关闭当前 trace-harmonic 构造，继续同分支开展容量优先的固定局部谱多级 pilot

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V4
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 1d87a6b7ff37c817d1b61ebb764dcadb9324552d
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 39 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v3.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v3.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
T1_T2_T3_T4                             = ACCEPTED_AND_FROZEN_PASS
R2_current_physical_dual                = ACCEPTED_AND_FROZEN_PASS
R3_current_difficult_residual           = ACCEPTED_AND_FROZEN_PASS
D1_small_trace_harmonic_oracle          = ACCEPTED_AS_RESEARCH_ORACLE
D2_trace_harmonic_p6_construction       = CLOSED_CONTROLLED_NEGATIVE
D2_rerun_or_inner_solver_campaign       = forbidden
D3_D4_T6_from_D2                        = not authorized
Candidate_A_standalone                  = CLOSED_NUMERICAL_FAIL
Candidate_B                             = CLOSED_NOT_APPLICABLE
Candidate_C                             = CLOSED_RESOURCE_AND_PRIORITY
transmission_only_sweep                 = CLOSED
new_primary_lane                        = bounded_local_spectral_multilevel_v1
continuous_authorized_batch             = N0 through N4, conditional on every prior Gate
mandatory_review_stop                   = after N4 screen or any earlier hard stop
T6_full_solve_and_physics_recovery       = not authorized
T7_T8_T9                                = not authorized
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_write_or_merge                   = forbidden
whole_Task37_extra_migration            = forbidden
whole_Task039_migration                 = forbidden
amend_rebase_force_push                 = forbidden
response_required                       = response_v4.md
```

本 Review 接受 `response_v3.md` 的主要事实与分类：D0 内存算术完成，D1 在 p2/p3 小型 fixture 上建立了 trace-harmonic 数学和 MPI identity；D2 在 p6/h10、MPI1、`trace_basis_build` 阶段，由 slab 0 interior CG 在固定 500 步后返回 `KSP_DIVERGED_ITS (-3)`，没有得到合法的 `Z`、`AZ` 或 `E=Z^H A Z`。D3、D4、T6 和所有后续 PDE 均正确未运行。

D2 的实测 construction process-tree peak 为 `3,013,468,160 B`，swap 为 `0 B`，worker 自然退出。该结果不是 12 GiB watchdog 停止，也不是 OOM；但它同时暴露：

```text
p6 harmonic-extension auxiliary solve does not close under the frozen contract
construction already exceeds the 2,000,000,000 B strategic line
no coarse vector has yet been produced
no online contraction has yet been measured
```

因此，本 Review 正式关闭当前：

```text
adaptive_trace_harmonic_two_level_v1
= two large z-slabs
+ repeated p6 slab-interior harmonic extensions
+ unpreconditioned CG
+ global rank-64 trace-harmonic basis construction
```

禁止通过增加 CG 步数、改成 GMRES、增加 inner PC、降低容差、改变 trace rank、预热 cache 或原样重跑来恢复 D2。否则会把原始 Full3D iterative blocker递归转移到 coarse construction 的 nested auxiliary solver。

本 Review 允许继续使用同一执行分支，但下一候选必须在结构上不同：采用**固定局部尺寸的三维 overlapping subdomains、固定容量的局部辅助 factors、局部谱模式和分布式多级 coarse**。第一步是容量审计；只有预算和小模型 oracle 均通过，才允许一次 p6/h10 setup与 contraction pilot。

---

# 1. 对 Response V3 的审阅结论

## 1.1 Git、范围与停止行为

| 审阅项 | 结果 | 说明 |
|---|---|---|
| base / merge-base | pass | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| reviewed HEAD | pass | `1d87a6b7ff37c817d1b61ebb764dcadb9324552d` |
| branch relation | pass | 审阅时 `ahead 39 / behind 0` |
| same branch | required | 继续当前执行分支，不新建分支或 worktree |
| ordinary default | unchanged | `full3d_iterative` 仍为显式 opt-in |
| master | unchanged | 未 merge、未写入 `master` |
| Candidate C | remained closed | 未重跑、未优化、未改 Gate |
| D2 hard Gate | correctly obeyed | MPI1 failure后未进入MPI2、D3、D4或T6 |
| full 0.7 nm PDE | correctly not_run | 没有运行或伪造结果 |

Codex 拉取本 Review 后，开始 N0 前仍须重新报告：

```text
branch
HEAD
upstream
ahead/behind
git status --short
canonical worktree identity
Python/MPI/PETSc/DOLFINx/Basix ABI
PETSc ScalarType/IntType
OMP/OpenBLAS/MKL threads
MemAvailable
system/process-tree/cgroup swap state
disk free
```

远端审阅无法观察本地 ignored artifacts 和 nonignored untracked 文件。工作树、ABI 或资源身份不合格时不得开始 N0。

## 1.2 接受并冻结的正成果

以下能力继续作为当前分支的正资产：

| 资产 | 当前身份 | 后续用途 |
|---|---|---|
| T1 `.dat` contract | frozen pass | one-dat/one-run、resolved config与provenance |
| T2 full-space volume action | frozen pass | exact fine operator volume action |
| T3 dynamic streaming Fourier-DtN | frozen pass | exact top/bottom open-boundary action |
| T4 owner-local topology | frozen pass | MPC/Floquet、owner-local support与接口数据身份 |
| R2 current physical-dual oracle | frozen pass | 当前 RHS/component authority |
| R3 current-compatible difficult residual | frozen pass | 正式 long-tail source |
| D1 p2/p3 trace-harmonic oracle | research oracle pass | 小模型辅助能量、trace mass和MPI identity参考 |
| process-tree watchdog/provenance | frozen reusable pattern | setup/online/termination资源权威 |

这些正结果不能推导：

```text
D2 p6 basis pass
D3 contraction pass
T6 iterative pass
complete workflow < 2 GB
0.7 nm feasibility pass
```

## 1.3 D1 的保留边界

D1 的 p2/p3 四个 formal case证明：

```text
auxiliary B_i and interface M_Gamma definitions are algebraically coherent
small assembled generalized eigenproblem closes
restriction/prolongation and MPC/Floquet identity close
MPI1/MPI2 canonical action identity closes
```

D1 只保留为小模型 oracle。禁止把其 dense algebra、两个大 slab 或 serial eigenbasis直接扩展为 p6 production implementation。

## 1.4 D2 controlled negative 的正式裁决

D2 的正式事实为：

| item | measured / actual |
|---|---:|
| formal source SHA | `cc8de60cc3e21b647aafb29ac9c10b46919823e7` |
| case | p6/h10 MPI1 |
| stage | `trace_basis_build` |
| local solver | CG, PC=NONE |
| tolerance / max_it | `rtol=1e-12`, `max_it=500` |
| failure | slab 0 interior CG `KSP_DIVERGED_ITS (-3)` |
| wall | `557.385958733 s` |
| process-tree peak | `3,013,468,160 B` |
| swap | `0 B` |
| termination | natural exit, rc=1 |
| `Z/AZ/E` | not obtained |
| D2 MPI2 / D3 / D4 | not run by Gate |

正式分类：

```text
ADAPTIVE_TRACE_HARMONIC_TWO_LEVEL_V1
= CLOSED_BY_NESTED_AUXILIARY_SOLVE_AND_CONSTRUCTION_RESOURCE_DEBT
```

这不等于“所有局部谱 coarse 永远无效”。关闭的是：以两个随问题规模增长的大 z-slabs为基础，为全界面 trace反复求大型 p6 harmonic extension的当前构造。

禁止：

```text
CG 500 -> 1000/2000
CG -> GMRES parameter trial
adding ILU/ASM/HX inside D2 harmonic extension
loosening rtol
reducing required rank after failure
warm-cache-only rerun
hiding construction outside watchdog
using unfinished extension vectors as coarse columns
```

D2 production core、runner和checker保持 `research-only / do-not-merge`。负记录、raw hash和文档不得删除或覆盖。

---

# 2. 为什么下一候选在结构上不同

## 2.1 当前 D2 的结构性问题

D2 采用：

```text
2 large z-slabs
→ interface trace candidate
→ solve large slab B_II harmonic extension
→ repeat for many candidates
→ construct global rank <=64 basis
```

即使最终 coarse rank很小，每个 coarse column都隐含一次随 slab尺寸增长的大型 H(curl) auxiliary solve。若需要再给该 solve设计一个可扩展 PC，就形成：

```text
outer FGMRES
→ two-level PC
→ coarse construction
→ harmonic-extension KSP
→ another H(curl) PC
```

这没有消除 blocker，只是把它推到内层。

## 2.2 新候选的限定结构

新的 `bounded_local_spectral_multilevel_v1` 必须采用：

```text
fixed-size 3D overlapping subdomains
+ one frozen positive H(curl) auxiliary operator
+ fixed-cap local factors or fixed-cap local solves
+ explicit gradient near-kernel handling
+ bounded local spectral enrichment
+ partition-of-unity embedding
+ distributed regional coarse levels
+ bounded top level
```

与 M3a 和 D2 的区别必须在 N0 文档中逐项证明：

| item | M3a | D2 | new pilot requirement |
|---|---|---|---|
| subdomain geometry | 16 growing z-slabs | 2 growing z-slabs | fixed-size 3D patches |
| local inverse | retained shifted ILU factors | large factor-free harmonic CG | fixed-cap local auxiliary factor/solve |
| coarse basis | fixed 75D wave | global trace-harmonic rank64 | local spectral modes + multilevel aggregation |
| scalability risk | factor size grows | inner KSP condition grows | local size and top level both bounded |
| global matrix | condensed trace operator | none | none |
| production fine action | condensed | full-space matrix-free | full-space matrix-free |

允许小型 local factors的理由是：单个 factor的 active DoF和factor bytes必须在 N0 中设定硬上限，并在 h-refinement下保持不增长；只允许 subdomain数量随全局规模增长。禁止 growing slab factor和global factor。

---

# 3. 新连续批次概览

本 Review 在同一执行分支上条件授权：

```text
N0  capacity-first closeout and architecture audit
→ N1 p2/p3 fixed-local spectral oracle
→ N2 p6/h10 cold setup and retained-layout qualification
→ N3 p6/h10 one-apply contraction qualification
→ N4 conditional T6-S 20/100/150/200 screen
→ response_v4.md and stop
```

正常通过时 N0–N4之间不需要逐阶段等待 ChatGPT。任一 hard Gate触发时，保存真实结果、提交轻量证据、写 `response_v4.md` 并停止。

本轮仍不授权：

```text
T6-F final 1e-6 solve
official E/H recovery
R/T/A/A_volume
full diffraction channels
T7 h-scaling
T8 0.7 nm/2 TiB audit
T9 closeout or master integration
```

---

# 4. N0：容量优先的 docs-only 审计

## 4.1 作用

N0 必须先回答：

> 固定局部尺寸的三维 H(curl) spectral/multilevel方法，能否在当前 p6/h10 完整 setup+online+Krylov预算中留下小于2 GB的可信窗口？

N0 是 docs/records-only，不得新增 solver、runner或重型测试。必须读取并引用当前仓库中的实测数据：

```text
Task037 M3a slab factor inventory and process-tree peaks
Task37-extra fixed local patch/factor payloads
Task038-extra T2/T3 exact action retained payloads
Candidate A cold and warm-like process-tree observations
D2 construction peak and failed CG facts
current full vector length and Krylov vector arithmetic
```

## 4.2 N0 必须冻结的单一设计

N0 不允许提供一串未决候选。必须在文档中冻结一套设计：

```text
subdomain construction rule
maximum owned active DoFs per subdomain
maximum overlap layers
single local auxiliary operator
single local solver/factor type
maximum factor bytes per subdomain
maximum selected modes per subdomain
maximum regional levels
maximum top-level rank
ownership and ghost routing
lifecycle order
```

可审计菜单只允许在 N0 静态比较后选一个：

```text
vertex/edge-star fixed patches
or fixed-cell-block 3D patches
```

不得在代码阶段扫描两者。

## 4.3 N0 内存闭合

必须分别闭合：

```text
exact matrix-free volume action
streaming Fourier-DtN
MPC/Floquet metadata
all local factor payloads
local spectral vectors
partition-of-unity data
regional coarse shards
bounded top-level operator/work
outer FGMRES restart=20 vectors
source/residual/solution vectors
watchdog and telemetry
recovery packet reserve
cold setup/JIT/allocator reserve
lifecycle overlap
```

每一项标注：

```text
measured
exact arithmetic
derived
budget
unknown/not_measured
```

禁止用 Candidate A warm-like peak替代 cold complete-workflow预算，也禁止用单个 factor bytes替代全部 factors。

## 4.4 N0 Gate

全部满足才允许 N1：

```text
central p6/h10 complete-workflow budget < 1,800,000,000 B
hard upper p6/h10 budget             < 2,000,000,000 B
unknown/unclosed major component      = none
local active DoF cap                  = frozen and global-N independent
local factor byte cap                 = frozen and global-N independent
maximum levels                        <= 3
maximum top-level rank                <= 64
no global AIJ/Schur/factor
no FE-sized numeric allgather
no per-rank full coarse basis replication
no global direct coarse solve
```

若 N0 不能闭合到硬上限，分类为：

```text
BOUNDED_LOCAL_SPECTRAL_MULTILEVEL_BLOCKED_BY_CAPACITY_PREFLIGHT
```

并停止，不写 N1 数值核心。

## 4.5 N0 输出

至少创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/adaptive_trace_harmonic_closeout.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/local_spectral_multilevel_preflight.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/n0_local_spectral_capacity_v1.json
```

并更新 `outcomes/test_summary.md` 的阶段矩阵，不得改写历史负结果。

---

# 5. N1：p2/p3 fixed-local spectral oracle

## 5.1 目标

N1 只验证新局部谱方法的代数，不运行 p6或PDE。必须使用 N0 冻结的单一 subdomain规则和单一 local solver。

局部正定辅助能量继续与当前物理算子分离。概念上可使用：

```math
B_i(u,v)
=
(\mu_r^{-1}\operatorname{curl}u,\operatorname{curl}v)_{\Omega_i}
+k_0^2(|\epsilon_r|u,v)_{\Omega_i}
+\tau (u,v)_{\partial\Omega_i},
```

但 `tau`、局部边界处理和质量度量必须在 N0 冻结，不能在 N1 扫描。

## 5.2 必须显式处理 gradient near-kernel

N1 的 coarse candidate不得只依赖未知谱向量。必须明确构造和审核：

```text
discrete gradient near-kernel directions
local spectral enrichment directions
partition-of-unity embedding
local-to-regional aggregation
```

必须报告 gradient方向与谱方向的线性独立、质量归一化和重复性。禁止把某个 residual或physical RHS用于生成 basis。

## 5.3 N1 formal cases

固定为：

```text
p2/h50 MPI1
p2/h50 MPI2
p3/h50 MPI1
p3/h50 MPI2
```

至少验证：

```text
local auxiliary Hermitian/positive identity
local factor/solve residual
local generalized eigen residual
PoU closure
restriction/prolongation adjoint
canonical MPI1/MPI2 source/action identity
mode ordering and phase determinism
fixed selected-mode cap
no numeric allgather
no global matrix/factor
repeat identity
```

小模型可使用 assembled oracle，但 production primary必须保持 owner-local。

## 5.4 N1 Gate

```text
all algebra relative errors <= 1e-11
MPI1/MPI2 canonical identity <= 1e-12
local solve residual <= 1e-11
repeat relative difference <= 1e-13
PoU/adjoint error <= 1e-13
selected modes <= N0 frozen cap
no parameter retry after numerical failure
```

若一次窄 implementation defect可被明确证明，允许一次代码修复并在新 SHA 下重跑全部四案；否则停止。

## 5.5 N1 输出

至少创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/local_spectral_oracle.md
records/n1_local_spectral_p2_mpi1_v1.json
records/n1_local_spectral_p2_mpi2_v1.json
records/n1_local_spectral_p3_mpi1_v1.json
records/n1_local_spectral_p3_mpi2_v1.json
records/n1_local_spectral_aggregate_v1.json
```

---

# 6. N2：条件 p6/h10 setup 与 retained-layout 资格化

只有 N0、N1全部通过后才允许 N2。

## 6.1 N2 冻结身份

```text
wavelength                    = 13.5 nm
space                         = p6/h10 full-space Nedelec
MPI                           = MPI1 first; MPI2 only after MPI1 pass
subdomain rule                = exact N0 frozen rule
overlap                       = exact N0 frozen value
local solver/factor           = exact N0/N1 frozen choice
max modes per subdomain       = exact N0 frozen cap
levels                        = exact N0 frozen count
top-level rank                <=64
basis source                  = operator/geometry/material only
physical residual fitting     = forbidden
```

## 6.2 N2 只做 setup，不做 outer contraction

N2 必须完成：

```text
owner-local subdomain inventory
local matrix/factor construction
local gradient and spectral basis
regional aggregation
bounded top-level packet
retained byte inventory
build lifecycle release
MPI1/MPI2 canonical setup identity
```

禁止在 N2 运行 outer FGMRES或把 setup pass写成PC contraction pass。

## 6.3 N2 资源 Gate

必须分别测量：

```text
cold setup/JIT process-tree peak
post-setup retained process-tree RSS
one no-op/identity apply setup overhead
swap
termination and no-orphan status
```

Gate：

```text
cold setup process-tree peak          < 2,000,000,000 B
post-setup retained process-tree RSS  < 1,800,000,000 B
measured retained component closure   <= N0 hard budget
process-tree/cgroup swap              = 0 B
local factor byte cap                 not exceeded
mode/subdomain/level caps             not exceeded
no global AIJ/Schur/factor
no global direct coarse solve
```

若 setup超过2 GB，即使 online预测较小，也分类为 complete-workflow resource fail并停止。

## 6.4 N2 迭代边界

局部 factors允许一次直接构造，不允许失败后切换 solver、增加fill、改变patch或减少证据case。若单一明确实现错误可被独立证明，允许一次窄修；否则停止。

---

# 7. N3：p6/h10 单次预条件器 contraction

只有 N2 MPI1和MPI2 setup identity及资源 Gate全部通过才允许 N3。

## 7.1 exact physical action

所有 residual更新必须用：

```text
current matrix-free full-space Maxwell volume action
+ current dynamic streaming Fourier-DtN
```

局部辅助 factors和coarse只属于 `M^{-1}`，不得改变物理 `A`。

## 7.2 五类正式 source

```text
physical RHS
gradient-dominated residual
curl-dominated residual
checkerboard/high-frequency residual
R3 CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE
```

## 7.3 contraction Gate

一次冻结的 multilevel PC apply 后：

| source | required `rho=||r-Az||/||r||` |
|---|---:|
| physical RHS | `<=0.60` |
| gradient | `<=0.90` |
| curl | `<=0.90` |
| checkerboard/high-frequency | `<=0.75` |
| R3 difficult long-tail | `<=0.70` |

还必须满足：

```text
explicit true-action closure <=1e-11
repeat relative difference <=1e-12
MPI1/MPI2 canonical result identity <=1e-11
online process-tree peak <2,000,000,000 B
max(cold setup peak, online peak) <2,000,000,000 B
swap=0
```

任一 source失败后按 fail-fast停止剩余 heavy case，并分类为当前 bounded local spectral family的数值负结果。禁止增加local modes、levels、overlap、factor fill或top rank。

## 7.4 N3 输出

至少创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/local_spectral_contraction.md
records/n3_local_spectral_contraction_mpi1_v1.json
records/n3_local_spectral_contraction_mpi2_v1.json
```

---

# 8. N4：条件 T6-S residual screen

只有 N3 全部 numerical/resource Gate通过后才允许 N4。

外层冻结：

```text
right FGMRES
restart = 20
standard in-memory Krylov
no disk-backed Krylov
no restart scan
no local/coarse parameter changes
```

## 8.1 checkpoint Gate

| checkpoint | full explicit true residual Gate |
|---:|---:|
| 20 | `<=0.40` |
| 100 | `<=0.05` |
| 200 | `<=0.005` |
| 150→200 improvement | `>=20%` |

必须在20/100/150/200保存 hash-bound solution/residual compact packets，并用 exact physical action显式重算 true residual。

## 8.2 N4 资源 Gate

```text
complete screen process-tree peak <2,000,000,000 B
swap=0
no OOM/no orphan
cold setup included in same workflow authority
```

不得把预热后的 screen与另一次setup拼接成完整流程通过。

## 8.3 N4 停止点

无论 T6-S通过或失败，完成后必须停止。禁止继续：

```text
final <=1e-6 solve
official E/H recovery
R/T/A/A_volume
channel comparison
T7/T8/T9
master integration
```

通过时保存solution、residual、Krylov/PC telemetry和lifecycle evidence，等待下一次 review决定是否授权 T6-F。

---

# 9. 资源、生命周期与证据纪律

## 9.1 formal heavy run共同要求

```text
one heavy job at a time
threads=1
process-tree watchdog active
MemAvailable preflight
process-tree and cgroup swap=0
warning at 1.8 GB
hard stop at 2.0 GB for qualification runs
development emergency hard stop at 12 GiB remains as safety backstop only
TERM→KILL group termination
no-orphan verification
expected/start/end source SHA
clean tracked worktree
```

2 GB是本候选的战略资格线，不是机器安全硬上限。达到2 GB时必须分类为resource fail并停止；不能继续到12 GiB后再称开发可接受。

## 9.2 build和online必须分开记录

每个阶段至少标记：

```text
preflight
mesh_space_mpc
JIT
subdomain_inventory
local_factor_build
local_mode_build
regional_coarse_build
top_level_build
post_setup_release
online_apply
true_action_recompute
cleanup
```

每个stage保存process-tree RSS/PSS/USS、swap、elapsed和主要对象inventory。不得用warm cache隐藏cold construction。

## 9.3 prohibited accounting

禁止：

```text
derived bytes reported as measured RSS
rank-local RSS reported as process-tree peak
sum of historical independent peaks reported as simultaneous measurement
warm-only run reported as complete workflow
ignored raw deleted after failure
missing record fields treated as pass
```

---

# 10. 本批次明确禁止

| 对象 | Review V4 决定 |
|---|---|
| D2 trace-harmonic CG rerun | forbidden |
| D2 inner PC development | forbidden |
| Candidate C rerun/JIT optimization | forbidden |
| new Robin/Padé/rational transmission | forbidden |
| changing Candidate A parameters | forbidden |
| growing z-slab factors | forbidden |
| global AIJ physical operator | forbidden |
| global condensed Schur | forbidden |
| global direct coarse factor | forbidden |
| per-rank full basis replication | forbidden |
| FE-sized numeric allgather | forbidden |
| residual-fitted basis | forbidden |
| rank >64 top level | forbidden |
| levels >3 | forbidden |
| unbounded local mode count | forbidden |
| N0 design scan after implementation | forbidden |
| T6-F/EH/RTA | not authorized |
| T7/T8/T9 | not authorized |
| full 0.7 nm PDE | forbidden |
| new branch/worktree | forbidden |
| merge/rebase master | forbidden |

---

# 11. 全批次 hard-stop 条件

任一条件发生，保存证据、提交当前轻量结果、写 `response_v4.md` 并停止：

1. branch、base、upstream、canonical worktree或ABI错误；
2. N0无法冻结单一subdomain/local-solver设计；
3. N0 central预算不低于1.8 GB或hard预算不低于2.0 GB；
4. N0存在未闭合的major memory component；
5. local active DoF或factor bytes会随global refinement增长；
6. 需要levels>3或top rank>64；
7. N1 algebra/MPI/PoU/gradient-near-kernel Gate失败且无单一明确implementation defect；
8. N2 setup cold peak达到2 GB、出现swap或local factor/mode cap超限；
9. N2需要global matrix、global Schur或global direct coarse solve；
10. N3任一source contraction Gate失败；
11. N3需要增加modes、overlap、fill、levels或rank；
12. N4任一residual checkpoint失败或150→200改善不足20%；
13. 出现OOM、orphan、termination失败或provenance不闭合；
14. 工作转向Hybrid、z-separable internal modal propagation或full 0.7 nm PDE；
15. 必须改变物理弱式、材料、Floquet phase、DtN normalization或official Gate才能继续。

Hard stop只关闭当前候选，不得扩大为“Full3D iterative永久不可能”。

---

# 12. 提交计划

继续使用同一分支：

```text
codex/20260820-task38-extra-full3d-iterative-0p7nm
```

推荐提交顺序：

```text
docs(task038-extra): close trace-harmonic lane and audit local spectral capacity
feat(dd): add bounded fixed-local spectral oracle                 # only if N0 passes
evidence(task038-extra): qualify p2/p3 local spectral oracle
feat(dd): add bounded p6 local spectral multilevel setup          # only if N1 passes
evidence(task038-extra): record p6 setup and contraction
bench(task038-extra): run conditional T6 residual screen          # only if N3 passes
docs(task038-extra): respond to review v4
```

每个提交只包含一个阶段；禁止 amend、force push、rebase、创建新分支或混入无关清理。活动期间即使 `master` 更新，也继续使用冻结 base `438caf...`，未经新 review不得同步。

---

# 13. 测试与证据要求

## 13.1 每个代码阶段

至少运行：

```text
focused unit tests
serial fixture
MPI2 fixture where applicable
compileall
git diff --check
AST duplicate-key check
compact JSON parse
independent checker
Markdown fence/table/link checks
```

若schema或`.dat` adapter未修改，不得无故扩大公共输入合同。所有测试在阶段最终代码后重跑；没有GitHub Actions时只报告local tests。

## 13.2 本批次文档

至少新增或更新：

```text
outcomes/adaptive_trace_harmonic_closeout.md
outcomes/local_spectral_multilevel_preflight.md
outcomes/local_spectral_oracle.md                     # if N1 runs
outcomes/local_spectral_setup.md                      # if N2 runs
outcomes/local_spectral_contraction.md                # if N3 runs
outcomes/full3d_iterative_screen.md                   # if N4 runs
outcomes/test_summary.md
response_v4.md
```

`outcomes/summary.md` 与 `docs/development_progress.md` 仍属于后续 T9 closeout；本轮不得提前伪造最终项目完成。

## 13.3 compact record建议

```text
records/n0_local_spectral_capacity_v1.json
records/n1_local_spectral_p2_mpi1_v1.json
records/n1_local_spectral_p2_mpi2_v1.json
records/n1_local_spectral_p3_mpi1_v1.json
records/n1_local_spectral_p3_mpi2_v1.json
records/n1_local_spectral_aggregate_v1.json
records/n2_local_spectral_setup_mpi1_v1.json
records/n2_local_spectral_setup_mpi2_v1.json
records/n3_local_spectral_contraction_mpi1_v1.json
records/n3_local_spectral_contraction_mpi2_v1.json
records/n4_t6_screen_v1.json
```

实际命名可适度调整，但必须清楚包含stage、case、MPI、source SHA和classification，且不得覆盖旧D2 negative evidence。

---

# 14. `response_v4.md` 必须回答

1. branch、base、Review V4 start HEAD、final HEAD、upstream、ahead/behind和worktree；
2. N0–N4 planned/run/pass/fail/not_run矩阵；
3. 当前D2 trace-harmonic family的正式closeout和do-not-merge文件清单；
4. N0冻结的唯一subdomain、overlap、local solver、factor cap、mode cap、levels和top rank；
5. p6/h10 complete-workflow内存闭合，逐项measured/exact/derived/budget/not_measured；
6. 与M3a、Task37-extra patch family和D2的结构差异；
7. 若运行N1，gradient near-kernel、local spectral modes、PoU和MPI identity结果；
8. 若运行N2，subdomain/factor/mode/coarse inventory、cold setup peak、retained RSS和swap；
9. 若运行N3，五类source的MPI1/MPI2 rho、closure、repeat、wall和资源；
10. 若运行N4，20/100/150/200 true residual、150→200改善、RSS、swap和wall；
11. 任何窄implementation fix及受影响fresh regressions；
12. global AIJ/Schur/factor、numeric allgather和basis replication audits；
13. T6-F、E/H、R/T/A、T7–T9和0.7 nm准确not_run边界；
14. measured/derived/budget/failed/controlled_stop/not_run分类；
15. changed files、tests、checker、artifact hash和selective-merge建议；
16. 下一轮是否应授权T6-F，或是否关闭当前local spectral family。

负结果必须给实际值、Gate和机制，不能只写“未通过”。

---

# 15. 下一次 Review 的裁决范围

下一次 Review 将判断：

```text
fixed-local spectral architecture是否在N0容量上真实可行
local factors是否保持global-N independent
p2/p3 oracle是否正确包含gradient near-kernel
p6/h10 cold setup和online是否都低于2 GB
multilevel correction是否真正改善physical和R3 long-tail residual
T6-S是否表现出足够的迭代收敛信号
是否授权T6-F完整Maxwell solve和official physics
哪些T1–T4/authority/watchdog组件进入selective-merge候选
```

在下一次review前不得开始T6-F、T7、T8、T9或master integration。

---

# 16. 最终决定

```text
T1_T2_T3_T4 = ACCEPTED_AND_FROZEN_PASS
R2_R3       = ACCEPTED_AND_FROZEN_AUTHORITY_PASS
D1          = ACCEPTED_RESEARCH_ORACLE_PASS
D2          = CLOSED_CONTROLLED_NEGATIVE
D2_RERUN    = FORBIDDEN
D3_D4_T6    = NOT_AUTHORIZED_FROM_D2
A_B_C       = CLOSED
TRANSMISSION_ONLY_SWEEP = CLOSED

N0 = AUTHORIZED_DOCS_ONLY_CAPACITY_GATE
N1 = CONDITIONALLY_AUTHORIZED_AFTER_N0
N2 = CONDITIONALLY_AUTHORIZED_AFTER_N1
N3 = CONDITIONALLY_AUTHORIZED_AFTER_N2
N4 = CONDITIONALLY_AUTHORIZED_AFTER_N3
T6_F = NOT_AUTHORIZED
T7_T8_T9 = NOT_AUTHORIZED
MASTER_MERGE = FORBIDDEN
```

Codex可以在同一执行分支连续推进N0→N4，但每一步都受前述Gate约束。正常停止点是N4 screen完成；若N0容量不闭合、N1代数失败、N2 setup超过2 GB、N3 contraction失败或任何更早hard stop触发，则提交并推送当前证据、创建`response_v4.md`，然后停止等待下一次审阅。
