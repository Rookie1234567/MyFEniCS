# Task041：MPI1 短波长 exact-side Hybrid 容量与离散阶梯

## 0. 任务身份

```text
task                                      = Task041
task_kind                                 = MPI1_EXACT_SIDE_HYBRID_SHORT_WAVELENGTH_CAPACITY_CAMPAIGN
status                                    = READY_FOR_CODEX_EXECUTION
repository                                = Rookie1234567/MyFEniCS
base_branch                               = codex/20260822-task40-hybrid-side-factor-pc
base_SHA                                  = 50897c0c62d1f35abed5b196ae17997b2e7521cc
working_branch                            = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
remote_upstream                           = origin/codex/20260902-task41-mpi1-shortwave-hybrid-capacity
branch_creation_authority                 = user explicit instruction on 2026-09-02
master_write_or_merge                     = forbidden
Task038-extra_write_or_merge              = forbidden
Task040_write_or_reclassification         = forbidden
ordinary_default_change                   = forbidden
public_run_entry                          = python scripts/run_case.py <one-case.dat>
formal_MPI                                = 1
threads                                   = 1
method                                    = inherited exact-side Hybrid iterative
new_side_PC                               = forbidden
Task040 experimental_PC                   = forbidden
full_side_exact_factors                   = allowed; this Task measures current technology
QEP_M_study                               = allowed only by frozen ladders in this task
full_0p7nm_PDE                            = forbidden
primary_wavelengths_nm                    = 5, 3, 2
primary_goal                              = measure numerical equivalence, convergence evidence, and minimum-memory reach under about 2 TiB physical RAM
response_required                         = response_v1.md
merge_approval                            = NO
```

仓库长期原则通常由 Codex 创建执行分支；本任务由用户明确要求 ChatGPT 从 Task040 当前
HEAD 创建 Task041 分支，因此这是一次有记录的用户级覆盖。除分支创建与任务书提交外，
角色分工保持不变：ChatGPT 负责任务书与 review；Codex 负责实现、测试、正式运行、
`outcomes/` 和 `response_v1.md`。

---

# 1. 本任务解决的 blocker

本任务不开发新的预条件器，而是回答一个当前必须先由实测确定的问题：

> 使用现有已经在 5 nm、p6/h4、M480、MPI8 下通过数值与物理 Gate 的 exact-side
> Hybrid iterative 技术，在全部计算改为 MPI1、工作站约有 2 TiB 物理内存时，完整
> workflow 的最低 process-tree RSS 是多少；同一技术能否进一步完成 3 nm 与 2 nm，
> 并在给定 p6 网格阶梯上取得 M 收敛和网格收敛证据？

这项工作为后续 0.7 nm 架构提供两个不能靠推测替代的实测锚点：

```text
1. MPI8 -> MPI1 后，rank duplication、MUMPS runtime、QEP packet和Krylov对象究竟减少多少；
2. exact-side factor architecture 随 h、wavelength、external channels 和 M 的真实增长有多快。
```

Task041 的成功不代表 exact-side factor 可以扩展到 0.7 nm。它只建立“现有技术在约
2 TiB 单节点上实际能走到哪里”的容量边界。若在 3 nm 或 2 nm 被资源 Gate阻止，负结果
必须保留，并用于约束 Task040/后续 Full3D scalable iterative 架构。

---

# 2. 继承的 5 nm 权威

## 2.1 固定 MPI8 数值与资源基线

Task041 原样继承以下 Task039/Task040 权威，不重跑 MPI8：

| 项目 | 继承值 | 口径 |
|---|---:|---|
| wavelength / incidence | `5 nm / 1 deg grazing / phi=0 / S` | measured identity |
| discretization | `p6 / h4` | measured identity |
| Hybrid modes | `M480 positive + M480 negative` | measured identity |
| MPI / threads | `8 / 1` | measured identity |
| Hybrid direct full workflow peak | `93.377006531 GiB` | process-tree RSS |
| exact-side Hybrid iterative full workflow peak | `80.025856018 GiB` | process-tree RSS |
| outer iterations | `1` | exact block-LDU authority |
| global/bottom/top/modal residual | all passed | existing formal |
| recovery / R/T/A / A_volume | passed | existing formal |
| selected E/H / canonical vectors / normal flux / channels | passed | existing formal |

MPI1 必须与 `80.025856018 GiB` 的最新 V7/V10 exact-side full-workflow authority比较，
不得误用较早的 `104.334560394 GiB` V4 implementation peak作为当前基线。

## 2.2 固定算法路径

Task041 使用与上述 80 GiB authority 相同的算法语义：

```text
selected-mode packet producer
→ producer process完全退出
→ exact-side Hybrid iterative consumer
→ bottom exact bare-F MUMPS side factor + physical Woodbury
→ top exact bare-F MUMPS side factor + physical Woodbury
→ matrix-free global Hybrid action
→ right FGMRES / exact block-LDU
→ full explicit true residual
→ 保存最小recovery packet
→ 销毁outer KSP、bottom/top factors和不再需要的矩阵
→ 验证RSS下降
→ recovery / E/H / R/T/A / A_volume / diffraction channels
```

禁止：

```text
Task040 low-memory experimental side PC
whole-endcap ILU
BLR
moving-PML
full-spectrum sweep
adaptive coarse
physical p-coarse
global Hybrid direct factor
silent direct fallback
```

Task041 的目的就是测量当前 exact-side 技术，不把算法研究与容量测量混在同一个变量中。

---

# 3. 冻结几何、边界和入射

除 wavelength、材料、mesh target、M、MPI 和只影响输出覆盖的
`reporting_harmonic_bound` 外，全部正式 case 保持以下身份：

```text
dimension                         = 3
geometry                          = rectangular_block_grating
period_x_nm                       = 50.0
period_y_nm                       = 25.0
z_min_nm / z_max_nm               = -10.0 / 130.0
interface_z_nm                    = 0.0
air_height_nm                     = 130.0
substrate_thickness_nm            = 10.0
grating_width_x_nm                = 17.0
grating_width_y_nm                = 25.0
grating_height_nm                 = 120.0
bottom_interface_nm               = 10.0
top_interface_nm                  = 110.0
grazing_angle_deg                 = 1.0
azimuth_deg                       = 0.0
polarization                      = s
amplitude                         = 1.0
n_air                             = [1.0, 0.0]
mu_r                              = [1.0, 0.0]
x/y Floquet                       = true / true
vertical boundary                 = dtn_port
scattering background             = layered
dtn_order_policy                  = auto_propagating
dtn_assembly                      = auxiliary
use_pml                           = false
finite element                    = p6 Nedelec H(curl)
mesh kind                         = structured_hex
assembly backend                  = assembly_time_static_condensed
floquet constraint                = auto
method                            = hybrid_iterative
propagation model                 = full3d_uniform_cg
traction model                    = full3d_one_cell_exact_schur
side preconditioner               = exact_factor
side residual correction          = 0
outer linear solver               = gmres/right
restart                           = 90
max iterations                    = 4000
reported/global/bottom/top/modal rtol = 5e-9
zero initial guess                = true
exact traction                    = true
streaming modal Schur             = true
consumer QEP                      = false when packet is supplied
```

正式运行必须使用：

```bash
mpiexec -n 1 python scripts/run_case.py input/official/task041/<case>.dat
```

不能用普通 `python` 代替 MPI1，因为 Task041 要审计完整 MPI 初始化、owner layout和
process-tree资源。

## 3.1 Formal 前的 surface quadrature 语义修复

Task041 分支继承的 `src/solvers/dtn_port_3d.py` 仍可能使用
`form_compiler_options={"quadrature_degree": ...}` 传递 surface quadrature。Task038-extra
最新只读证据已经发现，更可靠的 DOLFINx/UFL 语义是把 `quadrature_degree` 写入每一个
surface integral 的 metadata。

在创建第一个正式 Task041 packet或external source前，Codex必须选择性重写通用 helper：

```text
surface vector assembly
reusable surface component assembly
mode projection
surface scalar integration
```

要求：

```text
preserve all existing integral metadata
preserve integrand / facet tag / sign / phase
no Task038-extra runner import
no whole-branch cherry-pick
focused serial regression
focused MPI1 source-only comparison
```

对 5 nm、p6/h4、M480 的 `external_dtn_coupling`，先比较修复前后：

```text
canonical physical key set
canonical value digest
source norm
relative vector difference
orientation/sign
Floquet phase exactly once
surface quadrature degree
```

决策：

```text
relative difference <= 1e-12
    -> Task039 MPI8 numerical reference保持严格可比

relative difference > 1e-12
    -> 保留旧MPI8 reference，但标记REFERENCE_SOURCE_SEMANTICS_CHANGED
    -> Task041仍可继续测量corrected MPI1 current-technology capacity
    -> 不得声称完整MPI1-vs-MPI8 equivalence
    -> 不重跑MPI8 heavy，不重跑positive operator campaign
```

该修复属于通用数值语义修复，不是新的 PC，不允许改变材料、M、mesh或物理边界。

---

# 4. 材料合同

## 4.1 5 nm：数值材料必须与 MPI8 reference 完全相同

用户本轮提到“材料属性改一下”，但没有提供另一组 5 nm `delta/beta`。MPI1 与 MPI8
数值可比性的前提是物理材料完全相同，因此 5 nm lane 必须继续使用 Task039 authority：

```math
\delta_{5}=0.00603145547,\qquad
\beta_{5}=0.00435380777.
```

```math
n_{5}=1-\delta_5+i\beta_5
=0.99396854453+0.00435380777i.
```

```math
\epsilon_{r,5}=n_5^2
=0.9879545118729884805480
+0.0086550959446206099962i.
```

正式 `.dat` 中：

```text
materials.substrate_name = "W / tungsten, 5 nm Task039 authority"
materials.grating_name   = "W / tungsten, 5 nm Task039 authority"
materials.n_substrate    = [0.99396854453, 0.00435380777]
materials.n_grating      = [0.99396854453, 0.00435380777]
```

允许修正材料标签，不允许改变 5 nm 数值。若未来用户另行提供 5 nm 新材料，必须新建
no-reference supplemental lane，不得覆盖本 MPI equivalence case。

## 4.2 3 nm

用户提供：

```math
\delta_{3}=0.00264782505,\qquad
\beta_{3}=0.000883207249.
```

因此：

```math
n_{3}
=0.99735217495+0.000883207249i.
```

```math
\epsilon_{r,3}
=0.994710580822450721354499
+0.00176173734144351242510i.
```

正式 `.dat`：

```text
materials.substrate_name = "W / tungsten, 3 nm"
materials.grating_name   = "W / tungsten, 3 nm"
materials.n_substrate    = [0.99735217495, 0.000883207249]
materials.n_grating      = [0.99735217495, 0.000883207249]
```

## 4.3 2 nm

用户提供：

```math
\delta_{2}=0.00119851693,\qquad
\beta_{2}=0.000213688647.
```

因此：

```math
n_{2}
=0.99880148307+0.000213688647i.
```

```math
\epsilon_{r,2}
=0.997604356919993639934291
+0.00042686507507764341258i.
```

正式 `.dat`：

```text
materials.substrate_name = "W / tungsten, 2 nm"
materials.grating_name   = "W / tungsten, 2 nm"
materials.n_substrate    = [0.99880148307, 0.000213688647]
materials.n_grating      = [0.99880148307, 0.000213688647]
```

所有 run manifest 必须同时记录 wavelength、delta、beta、n、derived epsilon、
material role和hash。`delta/beta` 是 provenance metadata，不是第二套独立求解输入。

---

# 5. M 的真实合同

## 5.1 当前没有自动 M

当前公开输入中：

```text
method.requested_modes_per_direction
```

仍是显式 Hybrid 用户输入。代码自动派生的是：

```text
candidate pool
actual external DtN channel inventory
Woodbury dimensions
modal Schur dimensions
QEP workspace/lifecycle
```

因此 Task041 不得省略 M，也不得把 `auto_propagating` external DtN policy误写成
internal Hybrid M 自动收敛。

## 5.2 允许的最小 M 辅助功能

Codex可以新增一个纯 planning/preflight helper，用于：

```text
读取 wavelength / mesh / cross-section size
列出显式M ladder
检查candidate pool和QEP dimension是否容纳该M
估计selected packet / modal Schur / Krylov payload
生成建议的独立.dat文件名
```

该 helper 不得：

```text
在formal run中静默改变M
按残差在线增加M
修改public input schema
把多个M塞进一个dat
```

每个 formal `.dat` 必须写出唯一明确 M，并在结果目录名、resolved config和manifest中
保存。

## 5.3 冻结 M 阶梯

### 5 nm

```text
M = 480 only
```

原因是 MPI1 lane要复现已有 MPI8 authority，不能同时修改 M。

### 3 nm

第一张网格 `p6/h3` 上使用：

```text
M800
→ M1200 confirmation
→ conditional M1600 only if M800 vs M1200 fails
```

### 2 nm

第一张网格 `p6/h2` 上使用：

```text
M1200
→ M1800 confirmation
→ conditional M2400 only if M1200 vs M1800 fails
```

这些起点来自 5 nm M480 的线性波数缩放并向 40 的倍数取整：

```math
M_{\mathrm{start}}(\lambda)
=
40\left\lceil
\frac{480(5/\lambda)}{40}
\right\rceil.
```

该公式只是固定执行起点，不是 mode-count convergence 证明。更高一档用于相邻结果
比较；禁止继续到 M3200/M4800 或无边界扫描。

## 5.4 M 收敛 Gate

同一 wavelength、同一 mesh 的相邻 M run，首先都必须独立通过 own residual和physics
Gate。随后按以下 Mandatory 标准比较：

| Gate | Mandatory |
|---|---:|
| R/T/A/A_volume absolute difference | `<= 1e-4` |
| significant-order power relative difference | `<= 1e-3` |
| significant-order complex-amplitude relative difference | `<= 1e-3` |
| selected E overall relative L2 | `<= 5e-3` |
| selected H overall relative L2 | `<= 1e-2` |
| coordinates / material / external physical key set | exact |
| delivered positive/negative selected modes | exactly requested M |
| canonical trace and passive-branch authority | pass |

Significant order取两次结果中 power `>=1e-8` 的并集。若第一对通过，选择较小 M；若第一
对失败而第二对通过，选择中间 M。若最高允许 M仍不通过：

```text
M_NOT_CONVERGED_WITHIN_TASK041_LADDER
```

后续更细网格不得获得 accuracy-qualified 或 grid-converged结论。为了回答“机器能否跑到
哪里”，允许在最高已完成 M 下继续至恰好一个下一网格作 `capacity_only`，但不得继续整个
网格阶梯或把该结果写成物理收敛。

---

# 6. 正式 case 阶梯

## A. 5 nm MPI1 等价性与最低内存

固定：

```text
A1 = 5 nm / p6h4 / M480 / MPI1
```

执行顺序：

```text
A0 input + ABI + material + source + packet preflight
A1 fresh MPI1 selected-mode packet producer
A2 producer完全退出并确认RSS/进程树下降
A3 MPI1 exact-side Hybrid iterative consumer
A4 true residual + minimum recovery packet
A5 release-before-recovery
A6 official recovery/physics
A7 offline MPI1-vs-MPI8 comparison
```

不得复用 MPI8 owner-sharded packet作为 MPI1 resource result。可以复用它作为
owner-independent canonical mode identity reference；正式 MPI1 workflow必须生成自己的
MPI1 packet并单独测量 producer峰值。

### A-lane 继续条件

进入 3 nm 前必须满足：

```text
own numerical residual pass
own recovery/physics pass
swap = 0
no direct fallback
bottom/top factors lifecycle closed
MPI1 source/material/external keys bound
```

若旧 MPI8 raw E/H/canonical arrays可读，还必须完成完整 MPI comparison。若旧 raw arrays
不可用，但 MPI1 own Gate、tracked scalar authority和external key identity通过，可分类为：

```text
5NM_MPI1_OWN_PASS_REFERENCE_ARRAYS_PARTIAL
```

并继续 3 nm；不得声称完整 MPI equivalence。

## B. 3 nm

固定 mesh ladder：

```text
B1 = p6/h3
B2 = p6/h2.5
B3 = p6/h2
```

用户提出 `p6/h2.4` 理论上可能足够。Task041 不把该预测当作结论，而用 `h2.5` 和 `h2`
在两侧夹逼验证；本轮不额外运行 h2.4。

执行：

```text
B1先完成M800/M1200/条件M1600资格
→ 选定最小M
→ B2使用同一M
→ B3使用同一M
```

若 B1 的最高 M未收敛，最多允许一个 B2 capacity-only run，然后停止 3 nm accuracy
阶梯。

## C. 2 nm

固定 mesh ladder：

```text
C1 = p6/h2
C2 = p6/h1.5
C3 = conditional p6/h1
```

执行：

```text
C1先完成M1200/M1800/条件M2400资格
→ 选定最小M
→ C2使用同一M
→ 若C1/C2未收敛且资源预测允许，才运行C3
```

如果 C1 与 C2 已通过 Mandatory grid Gate，`p6/h1` 不运行；`p6/h1.5` 是
accuracy-qualified coarser candidate，`p6/h1` 没有必要为追求更小 h而消耗资源。

---

# 7. 每个 formal run 的固定数值与物理 Gate

## 7.1 线性系统

| Gate | Limit |
|---|---:|
| reported residual | `<= 5e-9` |
| global explicit true residual | `<= 5e-9` |
| bottom true residual | `<= 5e-9` |
| top true residual | `<= 5e-9` |
| modal true residual | `<= 5e-9` |
| interface projection | `<= 1e-8` |
| bottom/top exact traction | each `<= 1e-8` |
| external-q identity | `<= 1e-10` |
| finite values | required |
| KSP converged reason | positive |

小 reported residual、outer iteration=1或小 modal residual均不能替代五项 true residual。

## 7.2 物理与恢复

每次 completed run必须生成并检查：

```text
complex E/H
selected E/H at z = 10, 30, 60, 90, 110 nm
R/T/A_balance/A_volume
energy closure
all external order keys
per-order complex amplitude and power
normal flux
canonical active-trace and full-FE vectors
```

| Gate | Limit |
|---|---:|
| abs(R+T+A_balance-1) | `<=1e-5` |
| abs(A_balance-A_volume) | `<=1e-5` |
| finite E/H and channels | required |
| coordinate identity | exact |
| channel-key uniqueness and completeness | required |

## 7.3 MPI1 对 MPI8 的 5 nm比较

优先复用既有 Task039 comparator，不得放宽其 Gate。若需要 Task041 独立 checker，最低
标准为：

| Comparison | Limit |
|---|---:|
| R/T/A/A_volume absolute difference | `<=1e-8` |
| significant-order power relative difference | `<=1e-6` |
| significant-order complex-amplitude relative difference | `<=1e-6` |
| selected E overall relative L2 | `<=1e-6` |
| selected H overall relative L2 | `<=1e-6` |
| canonical active/full vectors relative L2 | `<=1e-5` |
| external physical key set | exact |
| material/geometry/incidence/M | exact |
| only allowed identity difference | MPI layout / owner ranges |

5 nm MPI8 scalar reference至少包括：

```text
R        = 0.733184273689319
T        = 0.00022009869492546226
A_balance= 0.2665956276157555
A_volume = 0.2665962726139155
```

若最新 hash-bound V7/V10 authority中数值位数更多，以其原始记录为准，不手工截断。

---

# 8. 网格收敛 Gate

同一 wavelength、同一 qualified M 的相邻网格使用 Task039 已建立的 Mandatory标准：

| Gate | Mandatory | Strong |
|---|---:|---:|
| R/T/A/A_volume absolute difference | `1e-4` | `1e-5` |
| significant-order power relative difference | `1e-3` | `1e-4` |
| significant-order complex-amplitude relative difference | `1e-3` | `1e-4` |
| selected E overall relative L2 | `5e-3` | `2e-3` |
| selected H overall relative L2 | `1e-2` | `5e-3` |
| each-run energy closure | `1e-5` | `1e-5` |
| physical external key set | exact | exact |
| non-mesh physical identity | exact | exact |

判定：

```text
3 nm:
    h3 vs h2.5
    h2.5 vs h2

2 nm:
    h2 vs h1.5
    conditional h1.5 vs h1
```

只有完整 identity、observables、fields和significant orders均通过，才可称
`grid_mandatory_pass`。`R+T+A≈1` 或总场整体接近不能抵消单个显著衍射级失败。

---

# 9. 输出 harmonic bound

`boundary.dtn_order_policy=auto_propagating` 决定 PDE 中的全部 physical external modes；
`output.reporting_harmonic_bound` 只决定报告覆盖，不得改变 PDE。

预期初始值：

```text
5 nm -> reporting_harmonic_bound = 25
3 nm -> reporting_harmonic_bound = 40
2 nm -> reporting_harmonic_bound = 60
```

在每个 wavelength 的 mode-only preflight 后，若实际 propagating key存在更大的
`|m|` 或 `|n|`，必须把 reporting bound提高到覆盖全部 propagating keys，并重新生成
对应 `.dat`；不得截断 official diffraction output。

---

# 10. MPI1 资源与安全合同

## 10.1 统一环境

正式 heavy前检查：

```text
branch/HEAD/upstream/worktree
PETSc complex128 and IntType
MPI library and MUMPS availability
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
VECLIB_MAXIMUM_THREADS=1
NUMEXPR_NUM_THREADS=1
swap used = 0
one heavy process tree only
disk and inode availability
input / physical / resolved / source hashes
```

不允许 WSL swap、Linux swap或 MUMPS OOC作为隐藏 fallback。Task041 主结论测量的是
in-core physical-memory workflow；OOC若未来另测必须是独立 supplemental task。

## 10.2 资源线

### 5 nm A lane

```text
warning process-tree RSS = 192 GiB
hard process-tree RSS    = 256 GiB
minimum MemAvailable     = 384 GiB
swap hard                = 0 B
total wall cap           = 172800 s
```

### 3 nm / 2 nm lanes

工作站约有 2 TiB 物理内存，但程序不得占满整机：

```text
planning ceiling         = 1.50 TiB = 1649267441664 B
warning process-tree RSS = 1.40 TiB = 1539316278886 B
hard process-tree RSS    = 1.60 TiB = 1759218604442 B
minimum MemAvailable     = max(predicted_peak + 256 GiB, 1.70 TiB)
swap hard                = 0 B
```

建议 wall cap：

```text
3 nm formal = 259200 s
2 nm formal = 345600 s
```

wall cap到达而 factor/solve未完成时分类为 resource/time controlled stop，不得写成 numerical
failure。

## 10.3 下一网格 launch preflight

在每个更细网格前，使用所有已完成 case形成 object-by-object预测：

```text
active side rows
explicit F NNZ/bytes
bottom/top MUMPS factor INFOG/estimated bytes
QEP workspace
selected packet bytes
C/D/H and W/K bytes
modal Schur bytes
Krylov vectors
recovery packet
construction overlap
process-tree RSS
```

预测必须区分：

```text
measured
derived
predicted central
predicted upper
```

只有：

```text
predicted upper <= 1.50 TiB
MemAvailable满足要求
swap=0
disk足够
```

才可启动下一网格。若预测 upper超过 1.50 TiB：

```text
NOT_RUN_BY_2TIB_CAPACITY_PREFLIGHT
```

不得为了“试一下”绕过；已完成的上一网格即为当前技术 capacity frontier。

## 10.4 p6/h1 的特殊条件

2 nm p6/h1 只有同时满足下列条件才运行：

```text
h2 and h1.5 both completed
h2 vs h1.5 Mandatory grid Gate未通过
selected M已资格化
h1 predicted upper <=1.50 TiB
MemAvailable >=1.70 TiB
swap=0
no other heavy process
```

任何一项不满足，h1标记为 conditional not_run。

---

# 11. 生命周期与资源测量

每个 packet producer与consumer都必须是 fresh process。需要记录：

```text
process-tree RSS peak
process-tree PSS/USS peak when readable
per-rank RSS
swap
wall
CPU time
disk scratch
MUMPS INFOG/RINFOG
factor count and factor bytes
QEP calls/workspace
selected packet bytes
external key inventory
```

consumer必须写以下关键 marker：

```text
system_ready
bottom_F_ready
bottom_factor_setup_begin
bottom_factor_ready
bottom_woodbury_ready
bottom_construction_cleanup
top_F_ready
top_factor_setup_begin
top_factor_ready
top_woodbury_ready
both_side_actions_ready
modal_schur_build_begin
modal_schur_ready
outer_ksp_setup_ready
solve_started
solve_complete
true_residual_complete
minimal_recovery_packet_saved
outer_ksp_destroyed
bottom_top_factors_destroyed
large_matrices_destroyed
rss_drop_confirmed
recovery_started
recovery_complete
official_outputs_written
final_cleanup_complete
```

完整 workflow peak定义为：

```math
B_{\mathrm{workflow}}
=
\max(
B_{\mathrm{packet\ producer}},
B_{\mathrm{consumer}}
).
```

不能把不同进程阶段的峰值相加。也不能只报告每 rank最大值替代 process-tree sum。

---

# 12. 失败、修复和自动推进

## 12.1 允许 Codex自行修复并继续

以下明确 implementation问题可以保留失败root、最小修复、加focused regression后自动继续：

```text
path/cache/marker/schema/hash
MPI1 empty-owner handling
canonical owner remap
surface quadrature metadata
scatter/workspace
orientation/conjugation
lifecycle and checker bookkeeping
watchdog terminal sample race
```

同一个根因最多一次 formal retry；不得借 implementation修复改变物理、M、mesh、Gate或
solver identity。

## 12.2 必须停止的真实 Gate

```text
5 nm own numerical/physics failure
5 nm genuine MPI1-vs-MPI8 mismatch
nonfinite solve
swap > 0
hard RSS stop
factor failure or MUMPS numerical error
M ladder最高档仍不收敛
next-grid predicted upper >1.50 TiB
grid identity mismatch
recovery/physics failure
```

若5 nm仅因旧 MPI8 raw arrays缺失而 comparison不完整，但 MPI1 own Gate与tracked scalar
authority通过，不属于真实物理失败，可继续并明确 qualification。

## 12.3 连续执行要求

不要在每个小步骤后等待审阅。建议自动连续执行：

```text
5 nm MPI1 complete
→ 3 nm M qualification
→ 3 nm h2.5/h2
→ 2 nm M qualification
→ 2 nm h1.5
→ conditional h1
→ summary/response
```

只有本节真实 Gate或用户中止才停止。一次只运行一个 heavy case。

---

# 13. 正式输入文件

Codex至少应创建下列独立 `.dat`；条件 M输入只在需要时创建：

```text
input/official/task041/
├── 5nm_p6h4_m480_mpi1.dat
├── 3nm_p6h3_m800_mpi1.dat
├── 3nm_p6h3_m1200_mpi1.dat
├── 3nm_p6h3_m1600_mpi1.dat              # conditional
├── 3nm_p6h2p5_m<Mselected>_mpi1.dat
├── 3nm_p6h2_m<Mselected>_mpi1.dat
├── 2nm_p6h2_m1200_mpi1.dat
├── 2nm_p6h2_m1800_mpi1.dat
├── 2nm_p6h2_m2400_mpi1.dat              # conditional
├── 2nm_p6h1p5_m<Mselected>_mpi1.dat
└── 2nm_p6h1_m<Mselected>_mpi1.dat       # conditional
```

占位文件名中的 `<Mselected>` 必须在 M Gate后替换为实际整数；Git中不得保留不可解析的
正式 dat。

每个 `.dat` 只代表一次 run。不得引入 batch section或隐藏 CLI physics override。

---

# 14. 结果与 provenance

每个正式 root必须包含：

```text
input_original.dat
resolved_config.json
run_manifest.json
input_sha256.txt
physical_model_sha256.txt
source_sha.txt
run_summary.json
environment.json
mpi_environment.json
resource_summary.json
memory_stages.jsonl
memory_stage_markers.jsonl
factor_inventory.json
selected_mode_manifest.json
external_mode_manifest.json
numerical_output/
```

Git中只提交 compact evidence，不提交完整场、因子、矩阵、QEP workspace或大型日志。

---

# 15. Outcomes 与 Response

Task041 至少提交：

```text
docs/task041_mpi1_shortwave_hybrid_capacity/
├── task.md
├── response_v1.md
└── outcomes/
    ├── summary.md
    ├── inherited_task039_task040_authority.md
    ├── material_and_case_contract.md
    ├── mpi1_5nm_equivalence.md
    ├── mode_count_qualification.md
    ├── mesh_convergence_3nm.md
    ├── mesh_convergence_2nm.md
    ├── resource_scaling_and_capacity_frontier.md
    ├── lifecycle_and_release_before_recovery.md
    ├── test_summary.md
    └── records/
        └── compact JSON records
```

并更新：

```text
docs/development_progress.md
```

`outcomes/summary.md` 必须以表格为主，列出每个 wavelength/mesh/M：

```text
status
source SHA
input/physical/resolved SHA
active rows
external keys
M delivered
iterations
five true residuals
R/T/A/A_volume
grid/M comparison
producer/consumer/workflow RSS/PSS/USS
wall
swap
factor inventory
classification
evidence path
```

---

# 16. 最终分类

Task041 最终必须明确给出以下之一或组合：

```text
5NM_MPI1_EQUIVALENCE_PASS
5NM_MPI1_OWN_PASS_REFERENCE_ARRAYS_PARTIAL
5NM_MPI1_NUMERICAL_OR_PHYSICS_FAIL
3NM_M_AND_GRID_MANDATORY_PASS
3NM_COMPLETED_NOT_GRID_CONVERGED
3NM_RESOURCE_FRONTIER
2NM_M_AND_GRID_MANDATORY_PASS
2NM_COMPLETED_NOT_GRID_CONVERGED
2NM_RESOURCE_FRONTIER
NOT_RUN_BY_2TIB_CAPACITY_PREFLIGHT
CONTROLLED_STOP_WALL
CONTROLLED_STOP_RESOURCE
```

并回答：

1. MPI1 5 nm是否与 MPI8数值一致？
2. MPI1 5 nm packet、consumer和完整 workflow峰值分别是多少？
3. MPI1 相对 MPI8 `80.025856018 GiB` 节省或增加多少？
4. 3 nm最小资格 M是多少？
5. 3 nm `h3/h2.5/h2` 是否网格收敛？
6. 2 nm最小资格 M是多少？
7. 2 nm `h2/h1.5/条件h1` 是否网格收敛？
8. 在 1.50 TiB规划上限下，当前 exact-side技术的最细完成网格是什么？
9. 最大内存对象是 side factor、explicit F、QEP、DtN、modal Schur还是recovery overlap？
10. 从实测 h/M/wavelength阶梯看，0.7 nm为何仍需要或不需要 Task040/Full3D scalable iterative架构？

本 Task不批准合并到 `master`。完成后等待 ChatGPT review。
