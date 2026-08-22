# Task040 Review Report V1：标量阻抗负结果复核与 mode-aware transmission 续研计划

## 0. 审阅决定

```text
review                                     = Task040 Review Report V1
reviewed_branch                            = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review         = d58368ba87ab5b8ed4ee424da23724797bd97bac
reviewed_numerical_source_sha              = 483275dcdfa65fbc578bbee510878f2d065e2429
reviewed_response                          = response_v1.md
reviewed_compact_record                    = task040_level_a_bare_f_transmission_v1.json
review_status                              = PASS_WITH_QUALIFICATIONS
T40_3_execution_and_evidence               = PASS
T40_3_fixed_scalar_candidate               = CONTROLLED_NUMERICAL_NEGATIVE
all_impedance_or_z_partition_routes_closed = false
scalar_PC_FGMRES_capacity_tested           = false
mode_aware_transmission_tested             = false
bounded_patch_PC_tested                    = false
extension_status                           = AUTHORIZED_WITH_STRICT_DECISION_TREE
same_branch_continuation                   = required
new_branch                                 = forbidden
master_or_Task039_write                    = forbidden
ordinary_default_change                    = forbidden
physical_case                              = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
QEP_M_physical_DtN_global_Hybrid_change    = forbidden
full_0p7nm_PDE                             = forbidden
response_required                          = response_v2.md
```

正式裁决：

1. T40-3 的实现、身份、资源、生命周期和独立 checker 闭环通过；
2. 冻结的“三组 two-layer exact subdomain + 标量一阶阻抗 + 六步 multiplicative sweep”
   对五个非零 source 均产生 `rho > 1`，所以这个**具体候选**是真实数值负结果；
3. 该结果不能扩大成“z 分区失败”“所有 impedance Schwarz 失败”或“iterative side inverse
   不可行”；
4. 当前还没有直接测试该固定 action 作为 right-FGMRES preconditioner 时的真实能力；
5. 当前 artificial impedance 使用 zero-order、normal-incidence scalar `q=-i k0 n_substrate`，
   尚未表达 1° grazing 下的横向 Floquet 波数、不同极化以及上部混合横截面的多模传播；
6. 下一轮先区分“方向有用但尺度/相位错误”与“方向本身错误”，再以离散接口 Schur/Steklov
   oracle 为依据，条件构造 mode-aware transmission；
7. 只有 transmission mechanism 在 exact-subdomain Level A 中通过，才继续 bounded patch
   Level B。不得把更弱的 bounded local solve直接接到已经失败的标量传递机制上。

本 Review 不改写 T40-3 历史负结果，只重新限定其适用范围并授权下一条受控研究链。

---

## 1. 已审阅结果

### 1.1 完整 workflow 基线

| 路径 | 范围 | process-tree RSS peak | 数值/物理状态 |
|---|---|---:|---|
| Hybrid direct h4 | full workflow | `93.377006531 GiB` | matched authority pass |
| exact-side Hybrid iterative h4 | full workflow | `80.025856018 GiB` | residual、recovery、R/T/A、E/H、canonical、channels pass |
| Task040 T40-3 | bottom bare-F component | `28.333576202 GiB` | transmission numerical negative |

T40-3 是 component，不得用 `28.334 GiB` 声称完整 workflow saving。

### 1.2 T40-3 一次作用结果

```math
\rho_j
=
\frac{\lVert b_j-F_bM_0^{-1}b_j\rVert_2}
     {\lVert b_j\rVert_2}.
```

| source | measured `rho` | mandatory limit |
|---|---:|---:|
| modal traction positive | `16.5126891915` | `<1` |
| modal traction negative | `14.2420148005` | `<1` |
| external DtN coupling | `22.9451239354` | `<1` |
| fixed random repeat 0 | `28.3160646015` | `<1` |
| fixed random repeat 1 | `25.7070183906` | `<1` |

同时通过：

```text
finite / zero-map / repeat / linearity
restriction-prolongation / PoU
artificial-interface mass and support identity
bare F unchanged
cross-section oracle factors ready -> cleanup = 3 -> 0
full-side exact factor = 0
global direct factor = 0
nested KSP = 0
swap = 0
watchdog natural exit
```

证据入口：

- [response_v1.md](response_v1.md)
- [outcomes/summary.md](outcomes/summary.md)
- [outcomes/transmission_mechanism_oracle.md](outcomes/transmission_mechanism_oracle.md)
- [compact record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_level_a_bare_f_transmission_v1.json)

---

## 2. 负结果的准确边界

Level A 使用三个 exact MUMPS subdomain factors，因此已经排除“局部 solve 不够准确”作为
当前主因。即使局部块精确求解，整体 correction仍放大 residual；所以立即把 exact local solve
替换成 bounded patch只会增加新的误差来源，没有技术依据。

但 T40-3 只测试了：

```text
three groups         = [0,1] / [2,3] / [4,5]
impedance            = q M_t
q                    = -i beta
beta                 = k0 * n_substrate
same scalar q        = both artificial interfaces
multiplicative order = 0 -> 1 -> 2 -> 2 -> 1 -> 0
one unit-coefficient correction from zero initial guess
```

它没有测试：

```text
right-FGMRES with the same action
actual order-dependent Floquet beta_mn
S/P-dependent admittance
upper heterogeneous cross-section modal transmission
projected discrete interface Schur transmission
bounded patch PC
coarse correction
```

所以正式分类是：

```text
FIXED_NORMAL_INCIDENCE_SCALAR_IMPEDANCE_TRANSMISSION_FAIL
```

禁止扩大为：

```text
ALL_IMPEDANCE_SCHWARZ_FAIL
Z_PARTITION_FAIL
ITERATIVE_SIDE_INVERSE_IMPOSSIBLE
COARSE_SPACE_PROVEN_MANDATORY
0P7NM_HYBRID_INFEASIBLE
```

---

## 3. 为什么 `rho > 1` 不足以判定 FGMRES 必然失败

T40-3 等价于从零初值做一次单位系数 correction：

```math
x_1=M_0^{-1}b.
```

right-FGMRES 会在 Krylov 子空间内选择复数系数，并不被迫使用系数1。下一轮必须计算：

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

解释：

| 观测 | 含义 |
|---|---|
| 原始 `rho` 大，但 `rho*` 小且 `c` 接近1 | correction方向有用，主要是尺度或复相位问题 |
| `rho*` 仍接近1且 `c` 小 | correction方向缺少正确传播模式 |
| modal source好、random source差 | PC只覆盖部分物理子空间 |
| 所有 source低相关 | 当前 scalar transmission可以关闭 |

`alpha*` 只作诊断；不得直接把它变成 damping参数后宣称通过。正式能力由固定 right-FGMRES
true residual决定。

---

## 4. 为什么当前 scalar impedance 不是充分传播模型

当前实现取：

```text
beta = k0 * n_substrate
q    = -i beta
```

它继承自 zero-order、normal-incidence Robin sanity path。当前案例却是 `1° grazing`：切向波数
不可忽略。下方人工截面位于均匀 substrate，可按 Fourier/Floquet order处理；上方人工截面位于
混合 grating/air 横截面，不能由同一个 substrate scalar描述。

均匀周期横截面中，不同 order 的 z 向传播常数概念上为：

```math
\beta_{mn}
=
\sqrt{(k_0n)^2-k_{x,m}^2-k_{y,n}^2}.
```

不同 order、极化、near-cutoff和evanescent方向具有不同阻抗或导纳。上方混合横截面应使用
现有 cross-section QEP mode 的 trace/traction关系。

因此当前最严格结论是：

> `q=-i k0 n_substrate` 的标量切向质量项不足以作为当前三分区 side PC的唯一跨接口信息。

---

## 5. 扩展目标与冻结项

扩展只回答：

> 能否在相同 bare `F_b`、相同三分区和相同 source family下，以离散接口 oracle验证的
> mode-aware transmission使 exact-subdomain Level A成为有效 right-FGMRES PC；若能，再把
> 横跨截面的 exact factors替换为 bounded patch PC？

继续冻结：

```text
5 nm / 1° / phi0 / S / p6h4 / M480 / MPI8
material / geometry / Floquet
selected-mode packet and QEP identity
static condensation and explicit bare F operator
physical external DtN C/D/H/W/K
modal traction/projection/modal Schur
global Hybrid MatPython operator
recovery/postprocessing/checkers
```

只允许改变：

```text
artificial-interface transmission inside the side PC
```

transmission通过后，才允许按原任务书替换 local exact factors。

---

## 6. Implementation bug 自主修复

Codex可自行修复并继续：

```text
syntax/import/type/path/package invocation
schema/marker/SHA/manifest透传
PETSc ownership、VecScatter、owner/ghost、workspace alias
对象destroy顺序和明确内存泄漏
由独立oracle证明的orientation/phase-once接线错误
checker/watchdog/artifact/telemetry wiring
```

要求：保留失败 root，标为 `implementation_failure`；先用 unit/tiny/MPI test复现；最小修复；
新增回归测试；绑定新 SHA重跑同一阶段。

不得冒充 bug fix：

```text
调 beta、阻抗系数或damping
为追逐结果手动翻sign
改变三分区、sweep顺序或sweep count
扫描overlap/restart/tolerance
增加coarse或新PC family
放宽数值与资源Gate
```

---

# 7. 连续执行顺序

```text
V1-0  inherited review audit，docs-only
V1-1  current scalar optimal-scaling/correlation + fixed FGMRES screen
V1-2  sampled discrete interface Schur/Steklov oracle
V1-3  projected-exact mode-subspace transmission oracle
V1-4  analytic mode-aware transmission
V1-5  conditional bounded-patch Level B
V1-6  conditional bottom full side / top / both / full Hybrid
V1-7  conditional h3 scalability probe
V1-8  outcomes、Pareto、response_v2.md
```

Codex正常通过或修复 implementation bug后自动继续；只有真正 Gate、完整成功或授权阶段全部结束
才停止等待review。

---

## 8. V1-0：继承审计

第一提交：

```text
docs(task040): audit review v1 transmission extension
```

创建/更新：

```text
outcomes/review_v1_inherited_audit.md
outcomes/scalar_transmission_krylov_screen.md
outcomes/interface_schur_oracle.md
outcomes/mode_aware_transmission.md
```

至少绑定：

```text
branch / HEAD / upstream / worktree
review_report_v1 identity
T40-3 raw/compact hashes
input/physical/selected-mode/external-key hashes
scalar q/beta authority
both artificial-interface z/material identities
93.377 / 80.026 / 28.334 GiB baselines
all forbidden routes
```

不得修改 Python或启动 heavy run。

---

## 9. V1-1：当前 scalar PC 的方向诊断与 FGMRES screen

完全复用 T40-3：

```text
same bare F
same three groups and exact subdomain factors
same q=-i*k0*n_substrate
same PoU and 0/1/2/2/1/0 sequence
same five nonzero sources plus physical zero-map
```

### 9.1 必须报告

```text
||M^-1 b|| / ||b||
||F M^-1 b|| / ||b||
alpha* real/imag/magnitude/phase
rho*
correlation c
original rho
five-source cross-correlation matrix
```

checker必须从 raw contractions重算。

### 9.2 固定 right-FGMRES

在一个 shared setup中对五个非零 RHS运行：

```text
zero initial guess
checkpoints = 0 / 4 / 8 / 16
conditional checkpoint = 32
```

只有16步时所有量 finite、最近8步 true residual至少下降 `0.25 decade`、RSS低于45 GiB且
无swap，才允许32。禁止其他budget、restart、damping或tolerance菜单。

### 9.3 Gate

首个 checkpoint同时满足：

```text
all mandatory true residual <=1e-2
modal+ / modal- / external  <=1e-3
```

则：

```text
SCALAR_TRANSMISSION_KRYLOV_PASS
```

直接进入 V1-5，保持 scalar transmission不变。

若16步后五个 source均仍 `>=0.9`，或没有持续下降，不运行32：

```text
SCALAR_TRANSMISSION_DIRECTIONAL_FAIL
```

若32仍未通过：

```text
SCALAR_TRANSMISSION_KRYLOV_CAPACITY_FAIL
```

两者都关闭 scalar candidate，但继续 V1-2，不立即结束整轮。

---

## 10. V1-2：离散 interface Schur/Steklov oracle

人工 transmission应近似“给定接口切向场后，相邻子域返回的真实 traction”。局部矩阵按
interior `I` 与 interface `Γ` 分块：

```math
S_\Gamma
=
A_{\Gamma\Gamma}
-
A_{\Gamma I}A_{II}^{-1}A_{I\Gamma}.
```

使用现有 exact subdomain factors只做 action/projected oracle，不形成 FE-sized dense interface
matrix。

分别处理：

```text
lower interface:
    uniform substrate
    Fourier/Floquet transverse-mode basis

upper interface:
    heterogeneous grating/air cross-section
    inherited M480 right/left QEP trace and traction basis
```

### 10.1 Probe manifest

任何 action前先提交并 hash绑定：

```text
canonical mode/order keys
branch/polarization/beta metadata
physically induced traces from five frozen RHS
fixed-seed modal combinations
fixed-seed complement probes orthogonal to modal span
```

看过结果后不得修改。若 packet缺少不可恢复的 left/right trace或traction identity，按真实
blocker停止，不得重跑或改变 QEP。

### 10.2 报告

当前 scalar `Z0=qM_t` 对 exact `SΓ`：

```text
sampled action relative error
projected rank / singular values / condition
per-probe alpha*/rho*/correlation
selected-mode-span projection error
complement-probe error
lower/upper separately
```

资源：

```text
no FE-sized dense Schur
no full-side factor
three exact cross-section factors only as oracle
peak <=45 GiB
swap=0
cleanup 3 -> 0
```

---

## 11. V1-3：projected-exact mode-subspace transmission

目的：判断在固定 Fourier/QEP span中使用 exact projected interface map后，三分区和固定 sweep
是否可成为有效PC。

```math
\widehat S
=
Y^H S_\Gamma Z.
```

`Z` 是 right trace synthesis，`Y` 是符合当前非 Hermitian/QEP规范的 left dual。禁止默认
`Y=Z`，禁止丢失orientation、Floquet phase或branch identity。

selected span外保留冻结 scalar base；projected-exact correction使用低秩/action或Woodbury形式，
不得物化 FE-sized dense matrix。

运行与 V1-1 相同的 one-apply diagnostics和 `4/8/16/(32)` FGMRES ladder。通过标准仍为：

```text
all mandatory <=1e-2
modal+ / modal- / external <=1e-3
```

若32步仍失败，停止：

```text
THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT
```

不得继续 analytic formula、bounded patch、top或full Hybrid。必须指出 lower/upper、selected span、
complement和失败 source family。

通过才进入 V1-4。

---

## 12. V1-4：analytic mode-aware transmission

### 12.1 Lower uniform interface

使用实际 transverse Floquet wavevector：

```math
k_{x,m}=k_x+\frac{2\pi m}{L_x},
\qquad
k_{y,n}=k_y+\frac{2\pi n}{L_y},
```

```math
\beta_{mn}
=
\sqrt{(k_0n_{sub})^2-k_{x,m}^2-k_{y,n}^2}.
```

按当前时间约定、outgoing branch和S/P导纳构造 modal impedance。branch、square-root和
near-cutoff处理必须由独立oracle验证，不能由结果选择符号。

### 12.2 Upper heterogeneous interface

复用冻结 M480 packet：

```text
right/left modes
positive/negative beta branches
existing trace/traction normalization
existing phase/orientation
```

构造 biorthogonal modal transmission；不得重跑QEP、改M、静默重新归一化或用 raw coefficient
逐项差异代替物理身份。

### 12.3 表示合同

```text
owner-row / batched / action-only
no FE-sized dense interface matrix
no full mode basis per-rank replication
small projected matrices only
fixed scalar base on unresolved complement
physical external DtN unchanged
```

先与 V1-2 exact projected oracle比较，再运行同一 one-apply和FGMRES ladder。正式通过由 side
true residual决定。

若32步未通过：

```text
ANALYTIC_MODE_AWARE_TRANSMISSION_FAIL
```

停止；禁止mode-count、beta shift、rational order或damping扫描。

若通过：

```text
MODE_AWARE_TRANSMISSION_MECHANISM_PASS
```

进入 V1-5。

---

## 13. V1-5：bounded patch Level B

只有 V1-1 scalar 或 V1-4 mode-aware transmission通过才允许。保持通过的 transmission完全
不变，只把三个 cross-section exact factors替换为：

```text
fixed small-restart local FGMRES
+
bounded overlapping patch PC
```

沿用原合同：

```text
max_local_rows <=1024
patch size不随global side DoF增长
same exact class reuses one packed factor
one deterministic MPI owner per class
owner-consistent PoU
no FE-sized allgather
no per-rank full basis replication
full-side factor=0
full-cross-section factor=0
```

若 Level A通过，而 bounded local PC稳定、内存合格但 side FGMRES出现长程停滞：

```text
COARSE_INFORMATION_REQUIRED
```

停止等待review；Codex不得自行添加coarse、trace-harmonic、Petrov或local-spectral family。

Level B bottom通过后按原任务书继续：

```text
bottom full A_side with unchanged physical DtN
top with identical algorithm configuration
both-side setup-only
one full Hybrid formal
conditional p6/h3 bottom scaling probe
```

---

## 14. 资源与完整结果 Gate

### 14.1 Level A

```text
peak <=45 GiB
swap=0
full-side factor=0
three cross-section factors only as oracle
cleanup=3 -> 0
```

### 14.2 Level B bottom

| 分类 | bottom peak |
|---|---:|
| no benefit | `>=49.313 GiB` |
| minimum positive | `<49.313 GiB` |
| meaningful | `<=35 GiB` |
| strong | `<=30 GiB` |

并要求：

```text
retained <=30 GiB
max_local_rows <=1024
no growth-sized factor
swap=0
```

### 14.3 Full Hybrid

| 分类 | full workflow peak |
|---|---:|
| no new best | `>=80.025856018 GiB` |
| new best | `<80.025856018 GiB` |
| >=20% saving vs direct | `<=74.701605225 GiB` |
| >=30% | `<=65.363904572 GiB` |
| >=40% | `<=56.026203919 GiB` |
| >=50% | `<=46.688503266 GiB` |

完整 numerical/physics Gate继续沿用 Task039 V7，不得降低。

---

## 15. 有限运行决策树

```text
Run A:
    current scalar alpha*/correlation
    + one shared 4/8/16/(32) FGMRES screen

Run B, only if scalar fails:
    both-interface sampled exact Schur oracle
    + projected-exact transmission screen

Run C, only if projected-exact passes:
    one analytic mode-aware transmission screen

Run D, only if transmission passes:
    one bounded-patch bottom campaign

Then only by Gate:
    bottom full side -> top -> both setup -> one full Hybrid -> optional h3
```

禁止：

```text
beta/sign/damping scan
mode-count scan
sweep-count/order/partition scan
generic ILU/BLR/drop/restart scan
second-order/rational impedance auto-extension
coarse auto-extension
physical dynamic DtN redesign
QEP/M/global operator change
direct/exact-side full rerun
0.7 nm PDE
```

---

## 16. 时间与停止条件

```text
default heavy timeout = 21600 s
one heavy job at a time
swap=0
```

只有已经进入 FGMRES、RSS低于hard line、无NaN/Inf、最近90分钟至少4个 true-residual
checkpoint、残差下降至少0.5 decade或接近Gate、预计剩余不超过2小时，才允许一次延长到总计
8小时。interface oracle construction和factor setup不得延长。

真正停止并保存证据：

```text
identity/ABI mismatch
swap>0 or resource hard stop
non-finite after implementation identity qualified
projected-exact transmission到32步仍失败
analytic mode-aware到32步仍失败
mode packet缺少不可恢复的left/right trace/traction identity
Level B违反max_local_rows/factor ownership/scalability
Level A pass但Level B出现COARSE_INFORMATION_REQUIRED
bottom通过后同配置top真实失败
full Hybrid residual/physics failure
```

scalar candidate关闭后按本 Review继续 V1-2，不算整轮停止。

---

## 17. 交付物与 response_v2

必须创建/更新：

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

未运行阶段写 `not_run_by_gate`。`response_v2.md` 必须回答：

1. scalar action主要是尺度/相位问题，还是方向问题？
2. fixed right-FGMRES能否利用当前 action？
3. lower/upper scalar impedance分别与 exact interface Schur差多少？
4. Fourier/QEP mode span能否覆盖 physically relevant interface action？
5. projected-exact transmission能否使三分区成为有效PC？
6. analytic mode-aware能否复现该能力？
7. bounded patch能否在 `max_local_rows<=1024` 下保留能力？
8. 最低 bottom RSS、最好 residual和时间是多少？
9. 是否得到新的完整 Hybrid memory point？
10. 面向0.7 nm，下一 blocker是 local solve、mode inventory、coarse information还是其他对象？

---

## 18. 最终判断

```text
T40-3 implementation identity            = PASS
T40-3 evidence/resource/lifecycle         = PASS_COMPONENT
fixed scalar one-apply mechanism          = FAIL
fixed scalar FGMRES capacity              = NOT_EVALUATED
z partition                               = NOT_REJECTED
mode-aware transmission                   = NOT_RUN
bounded patch scalable PC                 = NOT_RUN
current best full Hybrid RSS              = 80.025856018 GiB
0.7 nm scalable side inverse              = NOT_ESTABLISHED
merge approval                            = NO
```

核心判断：

> T40-3 已证明法向零级 scalar impedance不足，但没有证明 FGMRES无法利用该action，也没有证明
> 多模非局部 transmission无效。下一步先做最优缩放和固定Krylov screen，再用 discrete interface
> Schur验证 mode subspace；只有传递机制通过，才值得继续删除横跨截面的 local factors。
