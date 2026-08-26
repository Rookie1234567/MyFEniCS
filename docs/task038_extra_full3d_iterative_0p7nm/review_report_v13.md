# Task038-extra Review Report V13：正信号窄幅抢救、候选合理性预审与单层 LOR-edge H(curl)-GenEO 主线

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V13
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 2d37b9c5770e67dabdeafc4f778a4b55032c8b48
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 158 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v12.md
reviewed_outcome                        = docs/task038_extra_full3d_iterative_0p7nm/outcomes/interlevel_route_selection_v1.md
reviewed_next_architecture              = docs/task038_extra_full3d_iterative_0p7nm/outcomes/next_pc_architecture_after_v12.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
ordinary_default_change                 = forbidden
selected_hierarchy_at_review            = NONE
V12_Route_A                             = CLOSED_UNDER_V12_GLOBAL_ADJOINT_GATE
V12_Route_B                             = STRUCTURE_AND_RESOURCE_POSITIVE__NUMERICALLY_TOO_WEAK
V12_C1                                  = CLOSED_UNDER_MPI_CANONICAL_IDENTITY_GATE
V12_C2                                  = CLOSED_UNDER_SECOND_INTERLEVEL_WORK_GATE
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
production_Krylov                       = right-preconditioned GMRES
production_restart                      = 20, fixed
positive_auxiliary_max_it               = 10000, fixed
physical_Maxwell_max_it                 = 20000, fixed
full_0p7nm_PDE                          = forbidden
response_required                       = response_v13.md
continuous_authorized_batch             = A0 through Z2 below, with fixed branches
mandatory_stop                          = after Z2 or any earlier terminal hard stop
```

本 Review 继续服从唯一长期目标：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

用户冻结的当前优先级为：

```text
第一优先级 = 在有界内存内得到最终正确解
第二优先级 = 降低迭代次数与耗时
```

因此 V13 允许固定 `restart=20` 下的长迭代，但禁止用增大 restart、开放式参数扫描或无限增加 PC 变体掩盖近似逆质量不足。

---

# 1. 对 V12 结果的审阅

## 1.1 必须永久保留的事实

| 路线/证据 | V12 状态 | V13 解释边界 |
|---|---|---|
| Route A `6→3→1` | `CLOSED_BY_INTERLEVEL_SPECTRAL_GATE` | 10 个材料 class 的局部谱良好；唯一失败是 gradient global adjoint `2.8964367576123248e-11 > 1e-12` |
| Route B `6→2→1` | `STRUCTURALLY_QUALIFIED` | 层间谱、nested energy、setup 和约 1.005 GB 资源通过；random 在 7000 步受控停止，残差 `0.00814181052296021` |
| C1 same-mesh H(curl) | `CLOSED_BY_MPI_CANONICAL_IDENTITY_GATE` | MPI1/MPI2 内局部 work 通过，但相同 canonical keys 下 primal/dual coefficient relative 为 `0.10049859821442367 / 0.004662851981572301` |
| C2 nested LOR-edge HMG | `CLOSED` | 三个 level bridge 和第一对 transfer 通过；第二对 `h3star→h1star` owned work `0.018392534459166617` 失败 |
| p6 physical / official physics | `not_run_by_gate` | 没有 E/H、R/T/A、`A_volume` 或 12+12 channels |
| 0.7 nm / 2 TiB | `not_run_by_gate` | 没有 selected hierarchy，不得外推为通过 |

V13 不删除、不覆盖、不重分类以上历史结果。任何新的 PASS 都只能属于新 source SHA、新 schema 和新 artifact root。

## 1.2 当前已经建立的主线正结果

```text
exact high-order matrix-free action             = qualified
streaming Fourier-DtN                           = qualified
memory-first GMRES restart20 lifecycle          = qualified
high-order → level-6 LOR foundation             = positive
p6/h10 foundation live set                      ≈ 0.983 GB measured
three-level LOR hierarchy + restart reserve      ≈ 1.0–1.21 GB measured
exact level-6 LOR edge inverse at p3             = converged at iteration 3020
```

当前核心 blocker 已收缩为：

> 如何在不保留 global edge factor、不过度复制 coarse data、且全过程低于 2 GB 的前提下，可扩展地近似 level-6 LOR edge 正定算子 `B_L^{-1}`。

## 1.3 为什么允许两个窄幅抢救审计

Route A 的局部广义谱约为：

```text
lambda_min ≈ 0.4966
lambda_max ≈ 2.7341
condition  ≈ 5.506
```

且六个全局能量 probe 均为 order-one。唯一失败发生在大规模复数内积的标量 adjoint work 上，因此需要区分真实 `P/P^H` 缺陷与普通求和相消误差。

C1 的 physical canonical keys 在 MPI1/MPI2 间完整匹配，局部 work 也分别达到约 `1e-15`，但系数不同。必须先证明测试源本身由物理 key 唯一决定，而不是由 PETSc row、rank ownership 或 local ordering 决定。

这两个审计都是“确认旧正信号是否被测试口径误杀”，不是恢复旧 PC 参数搜索。

---

# 2. 总执行顺序与分支规则

Codex 按以下顺序连续执行，不需要在每个小阶段等待审阅：

```text
A0  Route A 稳定伴随审计
A1  条件 Route A p6 positive qualification
C0  条件 C1 canonical-key source identity 审计
C1  条件 same-mesh p-multigrid 小型与 p6 qualification
G0  条件 single-level LOR-edge H(curl)-GenEO 合理性与容量预审
G1  条件 GenEO 小型结构/数值 oracle
G2  条件 GenEO p6 setup 与 positive qualification
D0  条件 energy-minimizing BDDC/FETI-DP 合理性与容量预审
D1  条件 BDDC/FETI-DP 小型 oracle 与 p6 random screen
P0  任一 hierarchy positive PASS 后的 physical Maxwell MPI1
P1  条件 bounded Floquet/near-cutoff correction
P2  条件 MPI2、h5 setup-only 与 0.7 nm / 2 TiB 更新
Z0  所有候选失败后的架构收口
Z1  outcomes / development progress / response_v13.md
Z2  commit、push、停止等待审阅
```

固定分支规则：

1. A0 通过后优先执行 A1；A1 四源全部通过则跳过 C/G/D。
2. A0 或 A1失败后进入 C0；C1 全部通过则跳过 G/D。
3. A/C均失败后才进入 G0。
4. G 路线失败后才进入 D0。
5. D 路线失败后停止 numerical implementation，不得自行产生第五个 PC family。
6. Route B 原样长跑、C2 猜修、HX/PCGAMG、旧 local-spectral、旧 sweep 与 trace-harmonic 均禁止恢复。

---

# 3. A0：Route A 稳定伴随审计

## 3.1 目的

A0 不改变 `6→3→1` transfer、矩阵、材料、smoother 或 hierarchy。它只回答：

> V12 的 gradient global adjoint `2.8964e-11` 是否来自真实向量级伴随不一致，还是来自长复数内积的求和顺序与相消。

## 3.2 固定输入

```text
13.5 nm
p6/h10
MPI1 first; MPI2 only after MPI1 pass
same Route-A 6→3 transfer
same random / gradient / curl / checkerboard / physical-component / R3-long-tail probes
same owner-local Floquet/MPC phase-once routes
```

## 3.3 必须独立计算的四类事实

对每个 probe 保存：

```text
ordinary local np.vdot + MPI reduction
fixed canonical-order pairwise complex summation
Neumaier/Kahan-style compensated real/imag summation
vector-level canonical owner comparison between implemented adjoint route and explicit local P^H route
```

同时计算普通浮点 dot-product 的前向误差上界：

```math
\gamma_n
=
\frac{n\epsilon}{1-n\epsilon}.
```

不得用扩大旧 threshold 的方式通过；必须从原始 term magnitudes、`gamma_n` 和 deterministic ordering 得到可复核的误差界。

## 3.4 A0 prospective Gate

```text
all keys / dimensions / material identity        = exact
finite / input unchanged / repeat                 = pass
pairwise vs compensated relative                  <= 1e-13
compensated normalized work defect                <= 1e-12
vector-level canonical adjoint relative           <= 1e-11
ordinary absolute work defect                     <= 4 × computed floating forward-error bound
Floquet phase                                     = exactly once
MPI1/MPI2 result after canonical ordering         <= 1e-11, if MPI2 is run
```

若全部通过：

```text
route_A_v12_old_status = preserved FAIL
route_A_v13_status     = REOPENED_AFTER_STABLE_ADJOINT_CERTIFICATION
```

随后进入 A1。

若任一项失败：

```text
route_A_v13 = CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE
```

不得修改 transfer、阈值或 probe，进入 C0。

---

# 4. A1：Route A p6 positive qualification

在全新 source SHA / artifact root 下构建 `6→3→1 spectral-v2`，固定：

```text
one pre + one post degree-3 Chebyshev smoother
one V-cycle
p1 exact sparse solve = development oracle only
right GMRES
restart = 20
max_it = 10000
residual replacement every 20
solution-only checkpoint every 500
```

顺序：

```text
random → gradient → curl → checkerboard
```

每案 Gate：

```text
final explicit true residual <= 1e-8
complete process-tree peak   < 2,000,000,000 B
process-tree/rank swap       = 0 B
finite / checkpoint / provenance / no RSS growth = pass
```

不得因 500、2000、5000 或 7000 步趋势较慢而人工提前停止；只有用户再次明确要求、nonfinite、资源硬线或合同缺陷可以受控停止。

若 random 在 10000 步未通过，关闭 Route A并进入 C0。四源全部通过则：

```text
selected_hierarchy = route_A_6_3_1_spectral_v2
```

进入 P0。

---

# 5. C0：C1 physical canonical-key source identity 审计

## 5.1 目的

C0 不先改 same-mesh transfer。它先证明 MPI1/MPI2 的输入系数代表同一个物理向量。

## 5.2 唯一允许的源定义

每个 physical canonical key 的 complex coefficient 必须仅由以下字段的 deterministic hash生成：

```text
role
physical entity geometry key
entity dimension
entity-local basis index
canonical orientation state
Floquet master/phase state
fixed source seed
```

禁止使用：

```text
PETSc global row id
rank id
local row id
ownership range
iteration order
Python object hash
```

## 5.3 C0 Gate

先在 p3/h50 MPI1/MPI2 比较输入：

```text
canonical key sets                       = exact
input coefficient relative               <= 1e-13
input maximum absolute coefficient error <= 1e-12
```

再经过 same-mesh `P` 和 `P^H` 比较输出：

```text
primal output canonical relative <= 1e-11
dual output canonical relative   <= 1e-11
local/global adjoint             <= 1e-11
linearity/repeat/phase-once       = pass
```

若旧 C1 的输入本身不一致，只允许修复 source builder；旧 C1 negative永久保留。

若输入一致但输出失败，只允许一次明确归因的窄修，且必须唯一定位到：

```text
orientation
Floquet phase
owner reduction
primal/dual incidence
canonical ordering
```

不得同时改 transfer、operator和solver。无法唯一定位时关闭 C1，进入 G0。

## 5.4 C1 数值资格

C0通过后依次运行：

```text
p3/h50 MPI1/MPI2，四类 source，final <=1e-8 within10000
p6/h10 setup，peak <2GB、swap=0
p6/h10 random→gradient→curl→checkerboard，final <=1e-8 within10000
```

全部通过则：

```text
selected_hierarchy = same_mesh_hcurl_pmg_v1_requalified
```

进入 P0。任一 Gate失败则关闭 C1并进入 G0。

---

# 6. 为什么 G 路线值得进入，但必须先做 G0

V13 的首个全新候选为：

```text
single_level_lor_edge_hcurl_geneo_v1
```

其流程是：

```text
p6 high-order matrix-free exact operator
→ qualified level-6 LOR edge positive operator B_L
→ overlapping owner-local subdomain corrections
→ explicit gradient near-kernel coarse component
→ H(curl)-specific GenEO spectral enrichment
→ return to high-order space
```

它不再构造 `6→3→1`、`6→2→1` 或 `h3star→h1star` interlevel transfer，因此直接绕开 V12 的层间 blocker。

该思路有明确理论依据：Bootland、Dolean、Nataf 与 Tournier针对三维正定 Maxwell-type `H(curl)` 问题，构造了“梯度 near-kernel + 局部谱 enrichment”的两层重叠 Schwarz方法，并特别讨论了异质材料、孔洞和一般拓扑。该方法针对的是正定 Maxwell辅助问题，而不是直接替代真实 complex indefinite Maxwell外层。

它与 Task027 的失败 PCHPDDM/energy-GenEO 必须明确区分：

| 项目 | Task027旧路线 | V13 G路线 |
|---|---|---|
| 工作算子 | 凝聚/shifted physical FE operator | 已资格化的正定 level-6 LOR edge `B_L` |
| near-kernel | 未形成完整 H(curl)-specific split | 显式 gradient near-kernel先进入 coarse space |
| spectral对象 | 通用 PCHPDDM/局部能量模式 | 按 H(curl)-GenEO formulation 的局部 complement GEVP |
| fine architecture | p2 condensed/AIJ研究环境 | p6 high-order matrix-free + LOR auxiliary |
| 目标 | 直接改善物理外层 | 先构造可扩展的 `B_L^{-1}` 近似 |

因此 Task027 的负结果不能自动否定 G，但要求 G0先证明公式、容量和实现边界均闭合。

参考理论边界：

```text
Bootland et al., J. Scientific Computing 105 (2025), arXiv:2311.18783
Pazner, Kolev, Dohrmann, low-order preconditioning for the high-order de Rham complex, arXiv:2203.02465
```

---

# 7. G0：GenEO 合理性与容量预审，未通过前禁止数值实现

G0 必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/geneo_reasonableness_preflight_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/geneo_reasonableness_preflight_v1.json
```

## 7.1 必须完成的数学映射

在任何 eigenvalue或 residual运行前，文档必须冻结：

```text
level-6 LOR edge global space
8个2×2×2物理坐标子域，不依赖材料可分离性
one fine-LOR-cell overlap
restriction R_i
partition of unity D_i
local Neumann positive matrices
scalar-node to edge gradient incidence
split gradient near-kernel construction
GenEO complement local GEVP
local-to-global coarse prolongation
coarse operator与apply公式
Floquet/MPC phase-once位置
```

GenEO eigenvalue选择方向和 threshold必须从所采用理论的 condition-number准则及本分解的 overlap/multiplicity常数推导，并在读取任何正式 local spectrum之前写入 record。禁止根据结果选择 threshold。

若无法给出唯一、可编码、可独立检查的矩阵公式，G路线在 G0关闭，不进入代码。

## 7.2 固定容量边界

p6/h10 prospective central/hard预算：

```text
foundation measured anchor                 = 983,363,584 B
subdomain count                            = 8
retained total coarse rank, gradient included <= 96
retained global coarse basis bytes         <= 300,000,000 B
retained local factor/preconditioner bytes <= 350,000,000 B
all additional retained G objects          <= 600,000,000 B
predicted complete retained live set       < 1,700,000,000 B
predicted hard upper                       < 1,900,000,000 B
major unknown object                       = none
```

正式运行仍使用：

```text
warning = 1,800,000,000 B
hard stop = 2,000,000,000 B
swap = 0 B
```

若 coarse rank、gradient component、local factor或setup workspace不能在上述边界闭合，G0直接关闭；不得先实现再看是否OOM。

## 7.3 固定实现选择

```text
subdomains                    = 8 fixed geometric boxes
one-level local PC            = ILU(0), no fill scan
online local factors          = retained only if total factor cap passes
local eigenproblems           = sequential/streamed, one subdomain at a time
selected mode cap             = 12 per subdomain
retained total coarse rank    = 96 hard cap, including gradient component
coarse oracle                 = bounded dense solve allowed only for small/p6 positive research oracle
production physical coarse    = must have owner-distributed apply before P0
```

若 ILU(0) retained factors超过 cap，不允许自动换 ILU1/ILU2、AMG或更多 local iterations；G路线关闭。

---

# 8. G1：GenEO 小型结构与数值 oracle

仅在 G0通过后执行。

固定：

```text
p2/h50 and p3/h50
MPI1 then MPI2
same 8-subdomain rule scaled to fixture
random / gradient / curl / checkerboard
right GMRES / restart20 / max_it10000
```

必须验证：

```text
R_i / R_i^H work
PoU identity
local Neumann Hermitian/SPD
exact gradient inclusion
GEVP residual
selected-mode deterministic identity
coarse P/P^H
linearity/repeat/input unchanged
Floquet phase exactly once
MPI1/MPI2 physical canonical identity
final explicit true residual <=1e-8 for all cases
small process-tree peak <500,000,000 B
swap=0
```

任何结构 Gate失败立即关闭 G。仅迭代较多不失败，只要在10000步内最终通过。

---

# 9. G2：GenEO p6 setup 与 positive qualification

G1全部通过后，构建 p6/h10/MPI1：

```text
matrix-free high positive/physical actions
streaming DtN
level-6 LOR edge matrix
8 overlapping subdomains
retained ILU0 factors within cap
split gradient + selected GenEO basis
restart20 reserve
```

先完成 setup、10次PC apply、destroy/rebuild和资源测量，再运行：

```text
random → gradient → curl → checkerboard
```

Gate：

```text
final explicit true residual <=1e-8 within10000
complete process-tree peak <2GB
retained window <1.8GB
swap=0
coarse rank <=96
no FE-sized numeric allgather
no global high-order AIJ
no repeated RSS growth
```

四源通过后：

```text
selected_hierarchy = single_level_lor_edge_hcurl_geneo_v1
```

进入 P0。

G1或G2失败后进入 D0；不得生成 GenEO v2、扫描 threshold、mode cap、overlap或subdomain count。

---

# 10. D0：energy-minimizing BDDC/FETI-DP 只在预审合理时进入

第二个全新候选为：

```text
lor_edge_energy_minimizing_bddc_fetidp_v1
```

它的合理性来自 H(curl) BDDC/FETI-DP 的能量最小延拓和自适应局部界面 eigenproblem；但仓库已有严重资源警告：Task025 的 adaptive deluxe BDDC 在 h5 setup约10分钟仍未完成并达到约 `12.78 GB`，ordinary BDDC也没有优于ASM。

因此 D0 是强制容量否决阶段，不通过则不写solver。

D0必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/bddc_reasonableness_preflight_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/bddc_reasonableness_preflight_v1.json
```

并证明新候选与 Task025 的差异：

```text
works on positive level-6 LOR edge operator, not physical fine operator
8 owner-local subdomains
interface-only primal/dual unknowns
energy-minimizing extension
sequential local adaptive eigenproblems
no duplicated full subdomain factors
no global high-order AIJ
no global dense transfer
```

固定容量 Gate：

```text
retained local factors         <= 300,000,000 B
interface data                 <= 100,000,000 B
coarse basis/operator/solver   <= 150,000,000 B
all additional retained D      <= 550,000,000 B
predicted complete retained    < 1,700,000,000 B
predicted hard upper           < 1,900,000,000 B
major unknown                  = none
```

若任何一项无法闭合：

```text
D = CLOSED_BY_CAPACITY_PREFLIGHT
```

停止 numerical implementation，进入 Z0。

若 D0通过，D1只允许：

```text
p3/h50 two-subdomain MPI1/MPI2 structural oracle
then p6/h10 setup-only
then p6 positive random only
```

p6 random必须在10000步内达到 `1e-8` 且全过程低于2GB，才允许运行其余三类 source。禁止扫描primal constraints、deluxe scaling参数、eigen threshold、subdomain数或overlap。

四源通过后进入 P0；否则关闭 D并进入 Z0。

---

# 11. P0：任一 positive hierarchy通过后的 physical Maxwell MPI1

固定：

```text
13.5 nm
p6/h10
MPI1
exact matrix-free Maxwell volume
streaming Fourier-DtN
selected positive auxiliary PC
right GMRES
restart = 20
max_it = 20000
residual replacement every20
checkpoint every500
```

成功 Gate：

```text
final explicit true residual <=1e-6
complete process-tree peak <2,000,000,000 B
process-tree/rank swap=0
finite/provenance/checkpoint closed
```

通过后立即执行：

```text
save minimum recovery packet
destroy outer KSP/Krylov objects
destroy development-only coarse direct objects
confirm RSS release
recover E/H
compute official R/T/A
compute A_volume
compute 12+12 diffraction channels
compare against direct authority observable vector
```

## 11.1 physical 长尾的唯一强化

若 positive hierarchy通过，而 physical在20000步未达到 `1e-6`，且：

```text
last5000 steps降低至少1个数量级
finite
no memory growth
no algebra/provenance defect
```

才进入 P1，增加一次固定的：

```text
propagating + near-cutoff Floquet deflation
rank = actual qualified inventory
rank hard cap = 32
```

禁止 rank scan、residual-derived basis、random vectors或第二个coarse family。P1只重跑一次 physical formal。

---

# 12. P2：条件 MPI2、h5 setup-only 与 0.7 nm / 2 TiB 更新

仅在 MPI1 physical residual与official physics全部通过后执行：

1. 同一 selected PC 的 MPI2 physical；
2. 条件 p6/h5 setup-only与最多10次PC apply；
3. 更新 `0.7 nm / 2 TiB` optimistic/central/conservative capacity audit。

完整 0.7 nm PDE仍禁止。

---

# 13. Z0：所有候选失败后的停止边界

若 A、C、G、D均无 qualified positive hierarchy：

```text
selected_hierarchy = NONE
Task038-extra new-PC implementation = STOPPED_AFTER_V13_BOUNDED_CAMPAIGN
```

必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/next_pc_architecture_after_v13.md
```

只比较、不实现：

```text
three-level inexact subspace correction with distributed algebraic coarse solve
energy-minimizing BDDC/FETI-DP with matrix-free local solvers, if D0 failed only by retained factors
wave-aware domain decomposition combining a positive GenEO inverse with bounded physical Floquet coarse correction
```

不得自行开始第五个 PC family。

---

# 14. 通用资源、证据与停止条件

所有 p6/h10 formal：

```text
warning threshold = 1,800,000,000 B
hard stop         = 2,000,000,000 B
swap              = 0 B
one heavy job     = true
threads per rank  = 1
```

外部 watchdog必须覆盖：

```text
cold setup
retained dwell
PC applies
long solve cycles
release transition
recovery
postprocess
```

以下任一触发立即保存真实证据并按固定分支转移或终止：

```text
nonfinite
true residual cap failure
rank/SPD/adjoint/identity failure
RSS hard stop
swap>0
input/operator/physical identity mismatch
phase/orientation failure
checkpoint mismatch
orphan process
unapproved global object
```

所有新 core 必须进入 `src/solvers/`，benchmark只负责参数化 runner、watchdog和checker。不得继续累积只服务单个case的巨型task-numbered数值核心。

---

# 15. V13 需要的 outcomes 与 response

Codex必须更新或创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/development_progress.md
docs/task038_extra_full3d_iterative_0p7nm/response_v13.md
```

并根据实际执行路径创建对应的：

```text
route_a_stable_adjoint_v1.md
same_mesh_canonical_source_v1.md
geneo_reasonableness_preflight_v1.md
lor_edge_hcurl_geneo_v1.md
bddc_reasonableness_preflight_v1.md
lor_edge_bddc_fetidp_v1.md
p6_positive_v13.md
p6_physical_v13.md
feasibility_0p7nm_2tib_v5.md
next_pc_architecture_after_v13.md
```

只创建实际触达阶段的文件；未运行项在 summary/response 中写明确的 `not_run_by_gate`，不得创建伪 PASS 文档。

最终 response必须逐项回答：

1. Route A 的 ordinary、pairwise、compensated和vector-level adjoint分别是多少？
2. Route A是否被新身份重新开放？旧 V12 FAIL是否完整保留？
3. C1 canonical-key input在MPI1/MPI2是否先达到完全一致？
4. A或C是否完成p6四源positive资格？
5. 若进入G0，为什么它与Task027 GenEO不同？理论公式和threshold如何在看谱前冻结？
6. G0的gradient/coarse rank、local factor和完整live-set预算是否闭合？
7. GenEO小型与p6各source的true residual、迭代数、RSS和swap是多少？
8. 若进入D0，为什么新BDDC/FETI-DP没有重复Task025的12.78GB失败架构？
9. 是否获得selected hierarchy并运行physical Maxwell？
10. official E/H、R/T/A、A_volume和channels是否来自通过true residual Gate的场？
11. complete workflow peak、swap、release-before-recovery是否通过？
12. 0.7 nm / 2 TiB还有哪些measured、derived、predicted blocker？
13. 哪些代码是reusable、research-only和do-not-merge？

完成后提交、推送同一分支并停止等待审阅。不得运行完整0.7 nm PDE、改变ordinary default或merge master。
