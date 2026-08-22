# Task040 Review Report V1：标量阻抗负结果复核与 mode-aware transmission 续研计划

## 0. 审阅决定

```text
review                                      = Task040 Review Report V1
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = __REVIEWED_HEAD__
reviewed_numerical_source_sha               = 483275dcdfa65fbc578bbee510878f2d065e2429
reviewed_response                           = response_v1.md
reviewed_compact_record                     = task040_level_a_bare_f_transmission_v1.json
review_status                               = PASS_WITH_QUALIFICATIONS
T40_3_execution_and_evidence                = PASS
T40_3_fixed_scalar_candidate                = CONTROLLED_NUMERICAL_NEGATIVE
all_impedance_or_z_partition_routes_closed  = false
current_scalar_PC_FGMRES_capacity_tested    = false
mode_aware_transmission_tested              = false
bounded_patch_PC_tested                     = false
extension_status                            = AUTHORIZED_WITH_STRICT_DECISION_TREE
same_branch_continuation                    = required
new_branch                                  = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
physical_case                               = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
QEP_M_DtN_global_Hybrid_physics_change      = forbidden
full_0p7nm_PDE                              = forbidden
response_required                           = response_v2.md
```

本轮正式审阅结论是：

1. T40-3 的实现、身份、资源、生命周期和独立 checker 闭环通过；
2. 冻结的“三组 two-layer exact subdomain + 标量一阶阻抗 + 固定六步 multiplicative sweep”
   对五个非零 source 均产生 `rho > 1`，因此该**具体候选**是真实数值负结果；
3. 该结果不能扩大成“z 分区失败”“所有 impedance Schwarz 失败”或“iterative side inverse
   不可行”；
4. 当前任务还没有直接测试该固定 action 作为 right-FGMRES preconditioner 时的真实能力，
   也没有使用与 1° grazing、多模横截面相匹配的 mode-aware transmission；
5. 下一轮必须先区分“方向基本正确但尺度/相位不合适”与“传递方向本身错误”，再以离散接口
   Schur/Steklov oracle 为依据，条件开发 mode-aware transmission；
6. 只有 mode-aware transmission 在 exact-subdomain Level A 中通过，才继续原 Task040 的
   bounded patch Level B。不得把更弱的 bounded patch solve直接放到已经失败的标量传递机制中。

本 Review 不改写 T40-3 的历史负结果；它只重新界定负结果的适用范围，并授权下一条受控研究链。

---

## 1. 已审阅结果与当前基线

### 1.1 完整 workflow 继承基线

| 路径 | 范围 | process-tree RSS peak | 数值/物理状态 | 当前用途 |
|---|---|---:|---|---|
| Hybrid direct h4 | full workflow | `93.377006531 GiB` | matched authority pass | direct reference |
| exact-side Hybrid iterative h4 | full workflow | `80.025856018 GiB` | five residual、recovery、R/T/A、E/H、canonical、channels pass | 当前最好完整 iterative authority |
| Task040 T40-3 | bottom bare-F component | `28.333576202 GiB` | transmission numerical negative | component evidence，不是 full-workflow saving |

### 1.2 T40-3 数值结果

一次预条件器作用定义为：

```math
\rho_j
=
\frac{\lVert b_j-F_bM_0^{-1}b_j\rVert_2}
     {\lVert b_j\rVert_2}.
```

其中 `M_0^{-1}` 是当前冻结的 exact-subdomain scalar-impedance multiplicative action。

| source | measured `rho` | mandatory limit | 结论 |
|---|---:|---:|---|
| modal traction positive | `16.5126891915` | `<1` | fail |
| modal traction negative | `14.2420148005` | `<1` | fail |
| external DtN coupling | `22.9451239354` | `<1` | fail |
| fixed random repeat 0 | `28.3160646015` | `<1` | fail |
| fixed random repeat 1 | `25.7070183906` | `<1` | fail |

实现和资源证据同时为：

```text
finite / zero-map / repeat / linearity          = pass
restriction-prolongation / PoU                   = pass
artificial-interface mass and support identity   = pass
bare F unchanged                                 = pass
cross-section oracle factors ready -> cleanup    = 3 -> 0
full-side exact factor                           = 0
global direct factor                             = 0
nested KSP                                       = 0
swap                                             = 0
watchdog                                         = natural exit
```

因此，本结果不是 implementation failure、OOM、swap、factor cleanup 或 source identity 错误。
详细证据见：

- [response_v1.md](response_v1.md)
- [Task040 summary](outcomes/summary.md)
- [transmission mechanism oracle](outcomes/transmission_mechanism_oracle.md)
- [compact record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_level_a_bare_f_transmission_v1.json)

---

## 2. T40-3 负结果必须保持的准确边界

T40-3 已经排除一个重要解释：

> 失败不是因为三个 subdomain 内部解得不够准确。

因为每个 subdomain 在 Level A 中使用 exact MUMPS factor。即使局部 solve 准确，当前整体
correction仍把 residual放大到原来的约14到28倍。因此，不应立即进入 bounded patch Level B；
更弱的局部 solve不会自动修复错误的跨接口信息。

但 T40-3 只测试了以下固定对象：

```text
three groups              = [0,1] / [2,3] / [4,5]
artificial impedance      = q M_t
q                         = -i beta
beta                      = k0 * n_substrate
same scalar q on both artificial interfaces
multiplicative order      = 0 -> 1 -> 2 -> 2 -> 1 -> 0
one unit-coefficient correction from zero initial guess
```

它没有测试：

```text
right-FGMRES with the same fixed action
actual transverse Floquet propagation constants
TE/TM- or S/P-dependent admittances
upper heterogeneous cross-section modal impedance
projected discrete interface Schur transmission
bounded patch PC
coarse correction
```

因此正式分类只能是：

```text
FIXED_NORMAL_INCIDENCE_SCALAR_IMPEDANCE_TRANSMISSION_FAIL
```

不得写成：

```text
ALL_IMPEDANCE_SCHWARZ_FAIL
Z_PARTITION_FAIL
ITERATIVE_SIDE_INVERSE_IMPOSSIBLE
COARSE_SPACE_PROVEN_MANDATORY
0P7NM_HYBRID_INFEASIBLE
```

---

## 3. 为什么 `rho > 1` 还不足以判定 FGMRES 必然失败

T40-3 的 `rho` 检查等价于从零初值施加一次固定系数为1的 correction：

```math
x_1=M_0^{-1}b.
```

它直接检查：

```math
\lVert b-Fx_1\rVert.
```

right-GMRES/FGMRES 实际求解的是预条件后系统，并会在 Krylov 子空间中选择复数系数，不被迫
对 `M_0^{-1}b` 使用系数1。为了区分“幅值或相位错”与“方向错”，必须额外计算：

```math
y_j=F_bM_0^{-1}b_j,
```

```math
\alpha_j^\star
=
\frac{y_j^Hb_j}{y_j^Hy_j},
```

```math
\rho_j^\star
=
\frac{\lVert b_j-\alpha_j^\star y_j\rVert_2}
     {\lVert b_j\rVert_2},
```

```math
c_j
=
\frac{|b_j^Hy_j|}
     {\lVert b_j\rVert_2\lVert y_j\rVert_2}.
```

解释如下：

| 观测 | 含义 |
|---|---|
| 原始 `rho` 很大，但 `rho*` 小且 `c` 接近1 | correction方向有用，主要是尺度或复相位不合适 |
| `rho*` 仍接近1且 `c` 很小 | correction方向本身缺少正确传播模式 |
| modal source较好、random source较差 | PC只覆盖部分物理子空间 |
| 所有 source都低相关 | 当前标量 transmission family可关闭 |

这些量只用于诊断，不能用 `alpha*` 直接缩放正式 PC 后宣称通过，也不能据此扫描 damping。
最终能力必须由固定 right-FGMRES true residual验证。

---

## 4. 当前标量阻抗为什么不是充分的波传播模型

Task040 当前 `beta` 取：

```text
beta = k0 * n_substrate
q    = -i beta
```

该形式继承自仓库中的 zero-order、normal-incidence Robin sanity path。它可作为符号和弱式
一致性的起点，但不是当前人工截面的完整 optimized transmission authority。

本案例具有三个关键特征：

1. 入射为 `1° grazing`，切向波数不可忽略；
2. 下方人工截面约位于均匀 substrate 中，可以用 Fourier/Floquet mode逐阶描述传播；
3. 上方人工截面位于 grating/air 混合横截面内，单一 substrate 标量无法描述多个横向模式、
   极化和材料分布。

对均匀周期横截面，每个 Fourier/Floquet order 的 z 向传播常数概念上为：

```math
\beta_{mn}
=
\sqrt{(k_0n)^2-k_{x,m}^2-k_{y,n}^2}.
```

不同 order、极化以及 near-cutoff/evanescent方向具有不同阻抗或导纳。上方混合横截面则应使用
现有 cross-section QEP 模态的 trace/traction关系，而不是统一乘一个 `q`。

所以 T40-3 最有价值的新信息是：

> 在当前5 nm、1° grazing、混合横截面问题中，`q=-i k0 n_substrate` 的标量切向质量项不足以
> 作为三分区 side solver的唯一跨接口信息。

下一步应提升 transmission operator的物理内容，而不是先削弱 local solve。

---

## 5. 本轮扩展的唯一技术目标

本 Review 授权的扩展只回答：

> 在保持同一个 bare `F_b`、同一个三分区、同一个 source family和同一个 Hybrid物理身份时，
> 能否用经离散接口 oracle 验证的 mode-aware transmission，使 exact-subdomain Level A成为
> 有效的 right-FGMRES PC；若能，再把横跨截面的 exact factors替换为 bounded patch PC？

保持冻结：

```text
wavelength / material / geometry / angle / polarization
p6/h4 / M480 / MPI8
selected-mode packet and QEP identity
static condensation and explicit bare F operator
physical external DtN C/D/H/W/K implementation
modal traction/projection/modal Schur
Hybrid global MatPython operator
recovery/postprocessing/checkers
```

本轮只允许改变：

```text
artificial-interface transmission used inside the side PC
```

以及 transmission通过后，按原 Task040合同将 exact cross-section local solve替换为 bounded
patch iterative solve。

---

## 6. Codex 自主修复 implementation bug 的权限

沿用 Task040 `task.md` 的 bug处理合同。以下问题可以由 Codex自行最小修复、增加回归测试并
继续，不需要等待新 review：

```text
syntax/import/type/path/package invocation
schema/marker/SHA/manifest透传
PETSc ownership、VecScatter、owner/ghost、workspace alias
对象destroy顺序和明确内存泄漏
orientation/phase-once接线错误，前提是独立oracle先证明
checker、watchdog、artifact registry、telemetry wiring
```

必须保留失败 root、标记 `implementation_failure`、绑定修复前后 SHA。以下变化不得冒充 bug fix：

```text
调 beta 或阻抗系数
翻转符号追逐结果
改变三分区或 sweep顺序
增加 sweep count、damping、overlap或restart菜单
增加 coarse space或新PC family
放宽 residual、memory、repeat或linearity Gate
```

只有下面各节定义的真实数值、资源或可扩展性 Gate才停止等待审阅。

---

# 7. 执行顺序

```text
V1-0  inherited review audit，docs-only
V1-1  current scalar PC optimal-scaling/correlation + fixed FGMRES screen
V1-2  sampled discrete interface Schur/Steklov oracle
V1-3  projected-exact mode-subspace transmission oracle
V1-4  analytic mode-aware transmission candidate
V1-5  conditional bounded-patch Level B
V1-6  conditional bottom full side / top / both / full Hybrid
V1-7  conditional h3 scalability probe
V1-8  outcomes、Pareto、response_v2.md
```

Codex应按决策树连续执行，不因普通实现 bug或阶段通过中途停下。只有真正 Gate、完整成功或所有
授权阶段完成后停止。

---

## 8. V1-0：继承审计

第一项提交为 docs-only：

```text
docs(task040): audit review v1 transmission extension
```

更新或创建：

```text
outcomes/review_v1_inherited_audit.md
outcomes/scalar_transmission_krylov_screen.md
outcomes/interface_schur_oracle.md
outcomes/mode_aware_transmission.md
```

至少记录：

```text
branch / HEAD / upstream / worktree
review_report_v1.md identity
T40-3 source/raw/compact hashes
physical/input/selected-mode/external-key hashes
current scalar q/beta authority
both artificial interface z/material identities
93.377 / 80.026 / 28.334 GiB baselines
all forbidden routes
```

V1-0 不得修改 Python或启动 heavy run。

---

## 9. V1-1：当前标量 PC 的方向诊断与 FGMRES screen

### 9.1 冻结内容

完整复用 T40-3：

```text
same bare F
same three group row sets
same exact subdomain factors
same q=-i*k0*n_substrate
same PoU
same multiplicative sequence 0/1/2/2/1/0
same five nonzero sources plus physical zero-map
```

不得改变任何参数。

### 9.2 新增诊断

对每个非零 source报告：

```text
||M^-1 b|| / ||b||
||F M^-1 b|| / ||b||
alpha* real/imag/magnitude/phase
rho*
correlation c
original rho
```

还要生成五个 source之间的固定 cross-correlation表，检查一个 source的 correction是否主要被
映射到另一 source方向。所有量由 independent checker从 raw vector contractions重算。

### 9.3 固定 right-FGMRES screen

在同一个 shared setup中，对五个非零 RHS分别运行：

```text
right FGMRES
zero initial guess
checkpoints = 0 / 4 / 8 / 16
conditional checkpoint = 32
```

只有16步时所有量 finite、最近8步 true residual至少下降 `0.25 decade`、RSS低于45 GiB、
无swap，才允许32。不得运行其他budget、restart、damping或tolerance。

### 9.4 判定

当前 scalar transmission通过的唯一标准是首个 checkpoint同时满足：

```text
all mandatory true residual <= 1e-2
modal+ / modal- / external  <= 1e-3
all finite                   = true
swap                         = 0
```

若通过：

```text
SCALAR_TRANSMISSION_KRYLOV_PASS
```

随后直接进入 V1-5 bounded patch Level B，保持同一 scalar transmission。

若16步后五个 source均仍 `>=0.9`，或没有持续下降，则不运行32，分类：

```text
SCALAR_TRANSMISSION_DIRECTIONAL_FAIL
```

若32仍未通过，则分类：

```text
SCALAR_TRANSMISSION_KRYLOV_CAPACITY_FAIL
```

两种失败都关闭当前 scalar candidate，但不关闭 z 分区；继续 V1-2。

---

## 10. V1-2：离散接口 Schur/Steklov oracle

### 10.1 它解决什么问题

人工 transmission应近似“给定接口切向场后，相邻子域返回的真实 traction”。对一个局部块按
interior `I` 与 interface `Γ` 分块，离散 Schur action概念上为：

```math
S_\Gamma
=
A_{\Gamma\Gamma}
-
A_{\Gamma I}A_{II}^{-1}A_{I\Gamma}.
```

V1-2 使用已有 exact subdomain factors作为 oracle，只计算 action或小型 projected matrix，
不形成 FE-sized dense interface matrix。

### 10.2 两个人工接口分别处理

```text
lower interface:
    uniform substrate cross-section
    basis source = current Fourier/Floquet transverse modes

upper interface:
    heterogeneous grating/air cross-section
    basis source = inherited M480 right/left QEP trace and traction data
```

不得用同一个 substrate scalar operator替代两个接口。

### 10.3 冻结 probe manifest

在任何数值 action前，Codex必须提交一个轻量 probe manifest，固定并 hash绑定：

```text
canonical mode/order keys
branch/polarization
beta or propagation metadata
physically induced traces from the five frozen RHS
fixed-seed modal combinations
fixed-seed complement probes orthogonal to the selected modal span
```

probe清单不得在看到结果后修改。若现有 packet缺少完成 upper-interface biorthogonal projection所需
的 left/right trace或traction identity，按真实 blocker停止，不得重新运行或改变 QEP。

### 10.4 必须报告

对当前 scalar `Z0=qM_t` 与 exact `SΓ`，报告：

```text
sampled action relative error
projected matrix rank / singular values / condition
per-probe complex optimal scaling and correlation
current modal span projection error
complement-probe error
lower/upper interface分别统计
```

资源合同：

```text
no FE-sized dense Schur
no full-side factor
three exact cross-section oracle factors allowed only in Level A
process-tree peak <=45 GiB
swap = 0
factor cleanup = 3 -> 0
```

---

## 11. V1-3：projected-exact mode-subspace transmission oracle

### 11.1 目的

V1-2 只比较 action。V1-3 要回答：

> 如果在固定 modal/Fourier子空间中使用 exact projected interface transmission，三分区和固定
> multiplicative sweep本身是否可以成为有效预条件器？

对每个接口构造小型 projected operator：

```math
\widehat S
=
Y^H S_\Gamma Z,
```

其中 `Z` 为 right trace synthesis，`Y` 为与当前非 Hermitian/QEP规范一致的 left dual。
实现不得默认 `Y=Z`，不得丢失 orientation、Floquet phase或branch identity。

在 selected span外，保留冻结 scalar base `qM_t`；projected-exact correction只作用于固定 span。
推荐使用低秩 Woodbury/action形式，不把 correction物化为 FE-sized dense matrix。

### 11.2 数值 Gate

使用同一五个 source，先报告 one-apply `rho/rho*/c`，随后运行与 V1-1 完全相同的
`4/8/16/(32)` right-FGMRES ladder。

通过标准仍为：

```text
all mandatory true residual <=1e-2
modal+ / modal- / external  <=1e-3
```

若 projected-exact transmission仍不能在32步内通过，停止并分类：

```text
THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT
```

此时不得继续 analytic mode formula、bounded patch、top或full Hybrid。必须报告：

```text
selected-span coverage
complement error
which source family fails
whether failure comes from lower interface, upper interface or both
```

这是一个真正 Gate，因为即使使用 exact projected transmission和exact local solves仍失败，继续削弱
local solve没有依据。

若通过，则进入 V1-4。

---

## 12. V1-4：analytic mode-aware transmission

### 12.1 Lower uniform-substrate interface

使用实际 transverse Floquet wavevector：

```math
k_{x,m}=k_x+\frac{2\pi m}{L_x},
\qquad
k_{y,n}=k_y+\frac{2\pi n}{L_y},
```

```math
\beta_{mn}
=
\sqrt{(k_0n_{sub})^2-k_{x,m}^2-k_{y,n}^2},
```

并按现有时间约定、outgoing branch和S/P导纳构造 modal impedance。branch、square-root和
near-cutoff处理必须由独立 analytic/unit oracle验证；不得通过结果扫描选择符号。

### 12.2 Upper heterogeneous interface

复用已冻结 M480 selected-mode packet：

```text
right/left cross-section modes
positive/negative beta branches
existing trace/traction normalization
existing phase and orientation
```

从现有 mode trace与traction关系构造 biorthogonal modal transmission。不得重新运行QEP、改M、
重新归一化后隐藏 gauge差异，或将 raw coefficient逐项比较冒充物理身份。

### 12.3 表示与扩展性

analytic mode-aware transmission必须：

```text
owner-row / batched / action-only
no FE-sized dense interface matrix
no full mode basis replicated on every rank
small projected matrices only
fixed scalar base on unresolved complement
```

它只属于人工 PC接口，不修改 physical external DtN。

### 12.4 Gate

首先与 V1-2 exact projected oracle比较：

```text
lower and upper projected action errors
rank/condition
selected-span and holdout-probe errors
```

随后运行同一 one-apply诊断与 `4/8/16/(32)` FGMRES ladder。正式通过仍由 side true residual
决定，而不是只看 projected matrix误差。

若 analytic mode-aware在32步内不通过，分类：

```text
ANALYTIC_MODE_AWARE_TRANSMISSION_FAIL
```

停止等待审阅；不得扫描mode count、beta shift、rational order或damping。

若通过，分类：

```text
MODE_AWARE_TRANSMISSION_MECHANISM_PASS
```

然后进入 V1-5。

---

## 13. V1-5：bounded patch Level B

只有 scalar transmission在 V1-1通过，或 mode-aware transmission在 V1-4通过，才允许 Level B。

保持已经通过的 transmission完全不变，只把三个 cross-section-spanning exact factors替换为：

```text
fixed small-restart local FGMRES
+
bounded overlapping patch PC
```

继续执行原 Task040合同：

```text
max_local_rows <=1024
patch size由p6局部拓扑决定，不随global side DoF增长
same exact class reuses one packed factor
one deterministic MPI owner per class
owner-consistent PoU
no FE-sized allgather
no per-rank full basis replication
full-side factor =0
full-cross-section factor =0
```

如果 Level A transmission通过，而 bounded local PC有限、稳定、内存合格，但 outer side FGMRES显示
明确的长程停滞，则分类：

```text
COARSE_INFORMATION_REQUIRED
```

并停止等待review。Codex不得自行增加coarse、trace-harmonic、Petrov或local spectral mode family。

Level B bottom通过后，按原任务书顺序继续：

```text
bottom full A_side with unchanged physical DtN
top with identical algorithm configuration
both-side setup-only
one full Hybrid formal
conditional p6/h3 bottom scaling probe
```

---

## 14. 资源和完整结果 Gate

### 14.1 Level A oracle

```text
peak RSS <=45 GiB
swap =0
full-side exact factor =0
three cross-section factors allowed only as oracle
factor cleanup =3 ->0
```

### 14.2 Level B scalable bottom candidate

| 分类 | bottom component peak |
|---|---:|
| no memory benefit | `>=49.313 GiB` |
| minimum positive | `<49.313 GiB` |
| meaningful | `<=35 GiB` |
| strong | `<=30 GiB` |

并要求：

```text
retained state <=30 GiB
max_local_rows <=1024
no growth-sized factor
swap =0
```

### 14.3 Full Hybrid

| 分类 | full workflow peak |
|---|---:|
| no new iterative best | `>=80.025856018 GiB` |
| new best | `<80.025856018 GiB` |
| >=20% saving vs direct | `<=74.701605225 GiB` |
| >=30% saving vs direct | `<=65.363904572 GiB` |
| >=40% saving vs direct | `<=56.026203919 GiB` |
| >=50% saving vs direct | `<=46.688503266 GiB` |

完整数值与物理 Gate继续沿用 Task039 V7 authority，不得降低：

```text
reported/global/bottom/top/modal true residual <=5e-9
projection bottom/top/combined                  <=1e-8
exact traction bottom/top                       <=1e-8
R/T/A/A_volume delta vs matched direct          <=1e-6
selected E/H relative L2                        <=5e-3 / 1e-2
canonical active/full relative L2               <=1e-5
power-weighted channels                         <=1e-4
external keys/order exact
normal flux/orders/powers/amplitudes pass
all finite / swap=0
```

---

## 15. Heavy-run 数量和顺序约束

为避免再次形成无边界研究，本轮冻结为以下连续决策树：

```text
Run A:
    current scalar optimal-scaling + one shared 4/8/16/(32) FGMRES screen

Run B, only if scalar fails:
    both-interface sampled exact Schur oracle
    + projected-exact transmission screen

Run C, only if projected-exact passes:
    one analytic mode-aware transmission screen

Run D, only if transmission passes:
    one bounded-patch bottom campaign using the frozen passing transmission

Then only by Gate:
    bottom full side -> top -> both setup -> one full Hybrid -> optional h3 probe
```

同一阶段的实现 bug修复不计作新算法 attempt；必须保留失败 root。禁止：

```text
beta/sign/damping扫描
mode-count扫描
sweep-count或ordering扫描
partition扫描
普通ILU/BLR/drop/restart扫描
second-order/rational impedance自动扩展
coarse-space自动扩展
physical dynamic DtN redesign
QEP/M/global operator变化
direct/exact-side full rerun
0.7 nm PDE
```

---

## 16. 时间规则

```text
default heavy timeout = 21600 s
one heavy job at a time
swap =0
```

只有已经进入 right-FGMRES，且 RSS低于阶段hard line、无NaN/Inf、最近90分钟有至少4个 true
residual checkpoint、残差持续下降至少0.5 decade或已接近Gate、预计剩余不超过2小时，才允许
一次延长到总计8小时。

interface oracle construction、factor setup、QEP、direct或尚未进入Krylov的过程不得自动延长。

---

## 17. 真正停止条件

出现以下任一项，保存证据并停止等待review：

```text
branch/input/physical/packet/ABI identity mismatch
swap >0 or resource hard stop
non-finite output after implementation identity qualified
current scalar FGMRES到授权上限仍失败（关闭scalar后继续V1-2，不立即结束）
projected-exact transmission到32步仍失败
analytic mode-aware transmission到32步仍失败
mode packet缺少不可恢复的left/right trace/traction identity
Level B violates max_local_rows/factor ownership/scalability contract
Level A pass但Level B显示COARSE_INFORMATION_REQUIRED
bottom通过后同配置top出现真实数值Gate
full Hybrid residual或physics Gate失败
```

其中只有标注“继续V1-2”的 scalar关闭不是整轮停止；其余为真正 Gate。

---

## 18. 必需交付物

```text
outcomes/review_v1_inherited_audit.md
outcomes/scalar_transmission_krylov_screen.md
outcomes/interface_schur_oracle.md
outcomes/mode_aware_transmission.md
outcomes/bounded_patch_pc.md
outcomes/bottom_bare_f_pc.md
outcomes/bottom_full_side.md
outcomes/top_full_side.md
outcomes/both_side_setup.md
outcomes/full_hybrid_result.md
outcomes/h_refinement_scaling.md
outcomes/memory_residual_time_pareto.md
outcomes/0p7nm_side_pc_capacity.md
outcomes/test_summary.md
outcomes/summary.md
response_v2.md
compact hash-bound records
```

未运行阶段必须明确写 `not_run_by_gate`。`response_v2.md` 必须回答：

1. 当前 scalar action是尺度/相位问题，还是方向问题？
2. fixed right-FGMRES能否利用当前 `M_0^{-1}`？
3. lower/upper scalar impedance分别与 exact interface Schur差多少？
4. 现有 Fourier/QEP mode span能否覆盖 physically relevant interface action？
5. projected-exact transmission能否使三分区 sweep成为有效PC？
6. analytic mode-aware transmission能否复现该能力？
7. bounded patch能否在 `max_local_rows<=1024` 下保留数值能力？
8. 当前最低 bottom RSS、最好 residual和时间是多少？
9. 是否得到新的完整 Hybrid memory point？
10. 对0.7 nm而言，下一 blocker是 local solve、mode inventory、coarse information还是其他对象？

---

## 19. 测试与选择性合入边界

最少测试：

```text
formula/branch/orientation/unit tests
serial tiny interface Schur fixture
MPI2/MPI4 interface action identity
current scalar regression
projected-exact vs independent oracle
analytic mode-aware projected-action test
bounded patch class/owner/max-row tests
focused Hybrid regression
Ruff/format/compileall/git diff --check
document/benchmark checker
```

当前 T40-3 代码和结果仍为 research-only。可以单独审阅复用：

```text
interface support/mass identity
PETSc VecScatter/PoU carrier
factor lifecycle and checker infrastructure
```

不得提升：

```text
current scalar transmission as production PC
three cross-section exact factors as scalable solver
未通过的 mode-aware/bounded candidate
任何 full Hybrid或0.7 nm能力宣称
```

未经最终审阅和用户授权，禁止 merge到 `master`。

---

## 20. 最终审阅判断

```text
T40-3 implementation identity             = PASS
T40-3 evidence/resource/lifecycle          = PASS_COMPONENT
fixed scalar one-apply mechanism           = FAIL
fixed scalar FGMRES capacity               = NOT_EVALUATED
z partition                                = NOT_REJECTED
mode-aware transmission                    = NOT_RUN
bounded patch scalable PC                  = NOT_RUN
current best full Hybrid RSS               = 80.025856018 GiB
0.7 nm scalable side inverse               = NOT_ESTABLISHED
merge approval                             = NO
```

核心判断：

> T40-3 已经证明“法向零级标量阻抗不足”，但还没有证明“FGMRES无法利用该action”，更没有
> 证明“多模、非局部 transmission无效”。下一步必须先做最优缩放与固定Krylov screen，再以离散
> interface Schur为oracle测试 mode subspace；只有传递机制通过，才值得继续删除横跨截面的
> local factors。
