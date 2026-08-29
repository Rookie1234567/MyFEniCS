# Task040 Review Report V8：正式接受尺度归一化 identity，专用 full-spectrum 数值筛选与主线加速

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V8
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 7f4fc288bb18670be1b419fc552449384fd6d452
reviewed_response                           = response_v8.md
reviewed_primary_outcomes                   = outcomes/v7_scale_normalized_identity.md
                                               outcomes/full_spectrum_floquet_sweep.md
                                               outcomes/moving_pml_sweep.md
                                               outcomes/adaptive_spectral_schwarz.md
review_status                               = CONTINUE_ACCELERATED_MAINLINE
Task040_closed                              = false
merge_approval                              = NO
V6_absolute_identity_negative               = preserved_historical_fact
V7_scale_normalized_identity                = REVIEW_ADJUDICATED_PASS_D0
selected_full_interface_action              = D0_lower_memory
repeat_scale_identity_heavy_run             = forbidden
full_spectrum_numerical_status              = not_measured_after_final_fix
next_required_stage                         = V8_DEDICATED_FULL_SPECTRUM_TWO_SOURCE_FORMAL
current_moving_PML_raw_classification       = INCONCLUSIVE_RESOURCE_GATE
current_moving_PML_implementation           = RETIRED_FROM_HEAVY_RERUN
moving_PML_method_family                    = not_numerically_rejected
adaptive_impedance_Schwarz                  = authorized_independent_of_PML_signal
factor_only_full_side_rescue                = permanently_closed
old_776_route_C                             = retired_no_signal
full_target_0p7nm_PDE                       = forbidden_in_Task040
same_branch_continuation                    = required
new_execution_branch                        = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
response_required                           = response_v9.md
```

本 Review 的第一项正式裁决是：

```text
V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0
```

该裁决只针对完整 `15120`-row interface Schur action 的代数 identity，不是 full-spectrum
预条件器通过、不是 side inverse 数值通过，也不是完整 Hybrid 或 0.7 nm 通过。

V6-2 在旧绝对阈值下的 negative 继续完整保留。V8 不修改旧 raw、旧 checker 或旧
classification；它依据 V7 新增的三尺度、D0/D1、Layer A/B/C 和独立 checker 证据，对项目级
代数结论作正式裁决。

本 Review 的第二项裁决是：full-spectrum 路线没有产生 numerical negative。最后一次修复
`a2acb9344a9bd246a399c9110207926c7e03460e` 只完成 serial/MPI2 targeted regression，之后
没有执行 corrected MPI8 two-source screen。因此下一步必须是一次独立、精简、可中途判定的
full-spectrum formal，而不是再次运行 scale identity，也不是原样重跑 moving-PML。

本 Review 的第三项裁决是：当前 moving-PML 实现已表现出真实的时间/架构不可用性。其 raw
结果仍保持：

```text
INCONCLUSIVE_RESOURCE_GATE / SIGNAL_UNAVAILABLE
```

不能改写为 `PML_SWEEP_NO_SIGNAL`。但该实现把完整横截面 core 矩阵集中到单个 owner，并在
`PETSc.COMM_SELF` 上保留增长型 MUMPS core factor；corrected formal 六小时仍未完成第一个
source 的 one-apply。该具体实现不得再被原样延时重跑。PML tensor、collar tagging 和
full-state sweep 思想可在 distributed/bounded local service 上复用。

为了尽快推进主线，adaptive impedance Schwarz 不再被“moving-PML 必须先取得数值分类”
这一串行依赖阻塞。若 dedicated full-spectrum 没有正信号、遇到真实资源不可用，或在一次
明确 implementation 修复后仍无法形成 formal，Codex 必须直接进入本 Review 冻结的经济型
adaptive Schwarz 路线。

---

## 1. 最新证据的正式审阅

### 1.1 V7 scale-normalized identity

V7 使用同一完整接口 action，在：

```text
scale = 2^-10, 1, 2^10
```

上检查三个 deterministic sources、固定 linearity pair、D0/D1 两种累加实现，以及三层误差。
独立 checker 给出：

```text
evidence_valid       = true
checker_pass         = true
D0_candidate         = true
D1_candidate         = true
selected             = d0_lower_memory
refinement_trigger   = false
partition_trigger    = false
```

关键最大相对误差为：

| 指标 | 最大观测 | V7 Gate | V8 裁决 |
|---|---:|---:|---|
| D0/D1 Schur identity relative | 约 `2.7e-14` | `<=1e-10` | pass |
| D0/D1 repeat relative | 约 `2.7e-14` | `<=1e-11` | pass |
| Layer C linearity relative | 约 `3.0e-14` | `<=1e-11` | pass |
| group backward relative | 约 `2.6e-13` | `<=1e-10` | pass |
| group solve-repeat relative | 约 `4.9e-13` | `<=1e-11` | pass |
| D0-D1 relative | 约 `2.8e-14` | diagnostic | equivalent |

绝对误差随输入尺度放大，而相对误差保持在浮点舍入量级。这证明旧 V6 absolute Gate 的失败
不能再解释为 full-interface Schur 公式、row mapping、group solve 或累加顺序的真实错误。

V8 因此正式选择：

```text
selected_action = D0
reason          = D0 and D1 are numerically equivalent; D0 has lower scratch memory
```

不得再次运行三尺度 heavy identity，也不得为了生成一个新的 `formal_adjudication=true` raw
字段重复支付三组 factor setup。V8 的 review adjudication 与原 raw 字段并存。

### 1.2 Full-spectrum 当前状态

full-spectrum 已建立或通过的组件包括：

```text
canonical H(curl) entity/block representation
discrete x/y level inventory
15 x 7 harmonic grid
72 tangential high-order channels per plane
lower/upper 7560-row coverage
dual/primal transforms
phase-once contract
FFT/DFT tiny roundtrip
empty-local collective-safe probe
serial/MPI2 targeted regression
```

两次 MPI8 attempt 都在 numerical screen 之前因具体 implementation bug 停止：

```text
1. floating geometric extent assumption
2. legal empty-local rank treated as invalid
```

第二项已经由 `a2acb934` 修复，但修复后没有第三次 MPI8 formal。因此：

```text
FULL_SPECTRUM_NUMERICAL_SIGNAL = NOT_MEASURED
```

禁止将其登记为 `FULL_SPECTRUM_SWEEP_NO_SIGNAL`。

### 1.3 Moving-PML 当前状态

corrected moving-PML formal 的权威事实为：

```text
source SHA                 = 7b237ea653ea5afa0a731b30739663f0ea2374fc
elapsed                    = 21601.760233 s
last authoritative sample  = 21600.410422 s
process-tree RSS peak      = 40560816128 B ~= 37.78 GiB
swap                       = 0
termination                = wall_timeout
last numerical stage       = sources started
one-apply                  = not reached
r8/r16/r32/r64             = not reached
route signal               = SIGNAL_UNAVAILABLE
```

这不是内存 hard stop，也不是数值 no-signal。它说明当前 local service 在可接受时间内不能提供
第一次预条件器作用。

源码结构同时显示：

```text
three groups
one full-cross-section core extraction per group
one PETSc.COMM_SELF MUMPS core factor on the selected owner
collar diagonal inverse
local GMRES max_it = 2
full sweep = 0,1,2,2,1,0
```

这种 owner-serial、横截面增长型 factor 即使最终能算出 residual，也不能满足 0.7 nm 的正式
scalability contract。因此本 Review 追加项目级分类：

```text
CURRENT_MOVING_PML_OWNER_SERIAL_LOCAL_SERVICE_RETIRED
```

它只关闭当前实现，不关闭 moving-PML 方法族。

### 1.4 Adaptive Schwarz 当前状态

adaptive spectral Schwarz 尚未构造 subdomains、local coarse 或 outer FGMRES；当前正式状态
仍是：

```text
NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE
```

它不是 numerical negative。V8 明确解除其对 moving-PML 数值分类的依赖。

---

## 2. V8 执行总原则：以“首次可审计数值信号”为中心

用户当前优先级是尽快推进能够服务 0.7 nm 的主线，而不是继续扩充前置框架。V8 采用以下
执行纪律：

```text
1. 已被现有 raw/checker充分证明的 identity 不重跑；
2. 每个 heavy route 必须在 setup、one-apply 和每个 Krylov checkpoint 发 marker；
3. 不能在规定时间内给出 one-apply，就分类为当前实现 resource unavailable并切换；
4. 两个代表 RHS先筛选，有正信号才扩展五源；
5. 无正信号不扫 parameter menu；
6. ordinary focused implementation bug最小修复后自动继续；
7. 一条路线出现正信号就沿该路线做到 factor-free bottom/top/full Hybrid；
8. 只有真正 identity、numerical、resource、generalization或scalability Gate才停止。
```

必须继续区分：

```text
implementation_failure
resource_unavailable
numerical_no_signal
positive_signal
production_pass
0p7nm_architecture_candidate
```

这些状态不得互相代替。

---

# 3. V8-0：继承审计与 review adjudication

本阶段只做轻量 docs/identity 绑定，不运行 PDE。

必须记录：

```text
branch / HEAD / upstream / worktree
Review V8 commit SHA
input SHA256
physical-model SHA256
resolved-config SHA256
selected-mode packet SHA
current bare-F identity
V7 scale raw/checker bundle SHA
full-spectrum last implementation SHA
moving-PML raw root/hash
```

随后在：

```text
outcomes/v7_scale_normalized_identity.md
outcomes/summary.md
outcomes/route_signal_ledger.md
```

中增加 review-level adjudication：

```text
V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0
review_adjudicated = true
raw_formal_adjudication = false_preserved
```

不修改原 raw/checker 文件，不改变 V6 absolute negative。

V8-0 完成后不得停下来等待审阅，直接进入 V8-1。

---

# 4. V8-1：dedicated corrected full-spectrum two-source formal

## 4.1 目的

本阶段只回答：

> 修复后的完整 Floquet 频谱 wave correction，对 current 5 nm bottom bare `F` 是否产生可审计
> 的 true-residual 正信号？

不重复 scale identity，不生成五源 exact packet，不运行 top、QEP 或完整 Hybrid。

## 4.2 独立入口

新增或整理一个薄入口，推荐：

```text
--v8-full-spectrum-only
```

该入口必须直接复用现有：

```text
current bare-F assembly
current canonical Gamma layouts
review-adjudicated D0 full-interface action
final discrete level metadata fix
empty-local collective-safe fix
existing hash-bound V5 RHS descriptors
existing selected-mode provider for modal source definitions
```

禁止从旧 combined V7 runner 再次执行：

```text
three-scale identity
D0/D1 comparison
refinement audit
partition audit
exact-output packet publication
```

允许在同一进程中重新建立三个 group factors，因为 dedicated process 必须拥有 live Schur
operator；但只建立一次并贯穿 transform、two-source screen 和最终 cleanup。

固定 identity：

```text
case                      = 5 nm / 1 deg / S / p6h4 / bottom
MPI / threads             = 8 / 1
operator                  = current explicit bare F
full-side factor          = 0
full-cross-section factors= 3, mechanism oracle only
C/D/H                     = 0/0/0
QEP                       = 0
physical DtN              = not constructed
full Hybrid               = not run
```

## 4.3 Actual transform Gate

在同一 formal 中，先对 lower/upper actual trace 执行：

```text
canonical block roundtrip
primal roundtrip
dual roundtrip
FFT/DFT roundtrip
mass-weighted Parseval
Floquet phase once
7560 + 7560 row coverage
72 channels per plane
105 harmonics
empty-local collective safety
no numeric allgather
no full-plane numeric replica
```

阈值保持：

```text
all relative/roundtrip/Parseval errors <= 1e-10
```

若失败，必须给出具体 failed field。只允许一次有明确 root cause、带 targeted serial/MPI2
regression 的 implementation 修复重跑。不得通过丢弃 channel、减少 harmonic inventory 或
修改 phase 取得通过。

## 4.4 必须新增的进度 marker

至少写出：

```text
v8_full_spectrum_preflight
v8_full_spectrum_system_ready
v8_full_spectrum_group0_factor_ready
v8_full_spectrum_group1_factor_ready
v8_full_spectrum_group2_factor_ready
v8_full_spectrum_lower_transform_ready
v8_full_spectrum_upper_transform_ready
v8_full_spectrum_symbol_ready
v8_full_spectrum_external_one_apply_begin
v8_full_spectrum_external_one_apply_end
v8_full_spectrum_external_r8
v8_full_spectrum_external_r16
v8_full_spectrum_external_r32
v8_full_spectrum_external_r64
v8_full_spectrum_random0_one_apply_begin
v8_full_spectrum_random0_one_apply_end
v8_full_spectrum_random0_r8
v8_full_spectrum_random0_r16
v8_full_spectrum_random0_r32
v8_full_spectrum_random0_r64
v8_full_spectrum_cleanup_complete
```

每个 marker 至少包含：

```text
wall from process start
wall from current stage start
process-tree RSS
swap
factor lifecycle
PC apply count
current source/checkpoint
```

即使 route 被资源 Gate停止，也必须能够判断时间耗在 setup、transform、one-apply 还是
FGMRES。

## 4.5 固定 two-source 顺序

```text
1. external_dtn_coupling
2. fixed_random_repeat_0
```

对每个 source：

```text
one-apply true residual
FGMRES restart = 32
zero initial guess
true-residual checkpoints = 8 / 16 / 32 / 64
```

不运行 256。只有第 4.8 节的 conditional 条件满足时才允许 128。

必须保存：

```text
reported residual
full bare-F true residual
interface residual
source norm
solution norm
one-apply residual
PC apply count
wall per checkpoint
```

## 4.6 Stage-level 时间与资源 Gate

正式 hard contract：

```text
minimum MemAvailable before launch  = 96 GiB
preferred process-tree peak         <= 40 GiB
absolute process-tree hard stop     = 45 GiB
swap                                = 0
system + three factors ready target <= 1800 s
transform identity after factors    <= 900 s
one full PC apply per source        <= 1200 s
two-source total wall cap           = 10800 s
```

`target` 不是静默放宽线。若 setup 或 transform略超 target但仍在 total cap内并持续发出有效
marker，可继续；若 one-apply 超过 `1200 s`，或某一阶段在没有新 marker 的情况下超过其 target
两倍，则停止当前实现并写：

```text
FULL_SPECTRUM_CURRENT_IMPLEMENTATION_RESOURCE_UNAVAILABLE
```

这不是 numerical no-signal，并自动进入 V8-3/V8-4。

## 4.7 正信号与负信号

设两个 source 在 checkpoint `k` 的 full true residual ratio 为 `r_k`。

### Strong/weak positive

```text
both finite
and (
    both r32 <= 0.7
    or both log10(r16/r32) >= 0.15
    or both r64 <= 0.5
)
```

分类：

```text
V8_FULL_SPECTRUM_TWO_SOURCE_POSITIVE
```

随后同一 setup 自动进入 V8-2 五源资格，不等待审阅。

### Strict no-signal

```text
both finite
and both r64 > 0.8
and both log10(r32/r64) < 0.10
```

分类：

```text
FULL_SPECTRUM_SWEEP_NO_SIGNAL
```

不得扫描：

```text
beta branch
near-cutoff floor
impedance constant
mass scaling
pair sequence
sweep count
restart
harmonic cutoff
```

直接进入 V8-3/V8-4。

### Nonfinite/unstable

任一 source 出现：

```text
NaN/Inf
KSP breakdown
PC failed
one-apply nonfinite
true residual > 10 with unstable growth
```

分类：

```text
FULL_SPECTRUM_SWEEP_UNSTABLE
```

直接进入 V8-3/V8-4，不通过 damping 菜单救援。

## 4.8 唯一 conditional 128

只有 two-source 到 `r64` 后同时满足：

```text
all finite
no strict no-signal
no positive classification yet
both r64 <= 0.8
and at least one source log10(r32/r64) >= 0.05
elapsed < 9000 s
current RSS < 42 GiB
swap = 0
```

才允许两源继续到 `128`。

128 后：

```text
both r128 <= 0.5
or both log10(r64/r128) >= 0.15
    -> V8_FULL_SPECTRUM_TWO_SOURCE_POSITIVE

both r128 > 0.8
and both log10(r64/r128) < 0.10
    -> FULL_SPECTRUM_SWEEP_NO_SIGNAL

otherwise
    -> FULL_SPECTRUM_SWEEP_NO_BOUNDED_POSITIVE_SIGNAL
```

第三种也直接切换路线，不再增加 iteration。

## 4.9 Implementation failure 纪律

final empty-local fix之后的 dedicated formal只允许一次新的最小修复重跑，条件是：

```text
有明确exception或collective divergence root cause
数学定义不变
新增一个直接serial/MPI2 regression
修复diff局部
```

若 corrected dedicated formal再次出现另一个独立 implementation failure，分类：

```text
FULL_SPECTRUM_IMPLEMENTATION_BUDGET_EXHAUSTED
```

不再堆补丁，直接进入 adaptive Schwarz。

---

# 5. V8-2：full-spectrum 有正信号后的自动续推

## 5.1 五源资格

在相同 operator、transform、symbol、pair sequence、restart 和 PC配置下，继续：

```text
modal_traction_positive
modal_traction_negative
fixed_random_repeat_1
```

加上已运行的：

```text
external_dtn_coupling
fixed_random_repeat_0
```

全部运行：

```text
one-apply
r8 / r16 / r32 / r64
```

五源 Gate：

```text
all finite
holdout sources do not worsen from r32 to r64
and (
    all five r64 <= 0.5
    or all five improve >= 4x vs their V3-2 bounded reference
)
```

其中 modal+/modal-/external 的强目标仍是：

```text
r64 <= 1e-2
```

达不到强目标但满足上述 weak Gate，只能写：

```text
FULL_SPECTRUM_WAVE_LAYER_WEAK_POSITIVE
```

仍允许进入 local-service productionization；不得称为 side inverse pass。

## 5.2 Wave layer 与 local layer 的职责

full-spectrum 只处理接口上的长距离传播、反射、相位、near-cutoff 和 evanescent content。
最终 side inverse 还必须处理材料跳变、几何边缘和局部误差。因此正信号后的正式组合为：

```text
local pre-correction
-> full-spectrum wave correction on updated residual
-> local post-correction
```

其乘法形式为：

```math
x_1=P_{loc}^{-1}r,
```

```math
x_2=x_1+P_{wave}^{-1}(r-Fx_1),
```

```math
x_3=x_2+P_{loc}^{-1}(r-Fx_2).
```

不得把三个 full-cross-section group factors留在最终组合中。

## 5.3 删除 group factors：bounded patch first

固定第一候选：

```text
3D overlapping active-row patches
one shared-entity overlap layer
max factorized local rows <= 1024
one deterministic owner per exact patch class
factor-class reuse enabled
owner-consistent partition of unity
PC-only shift = inherited dimensionless 0.1
```

硬禁止：

```text
full-cross-section factor
global direct factor
dense global coarse factor
FE-sized numeric allgather
full basis replication
```

如果 bounded patches 的固定内存常数或 128 步内数值质量不足，唯一 local-service fallback 是
Review V6 已定义的 fixed low-order-refined / three-grid matrix-free `H(curl)` service。它不是
自动 h/p 自适应：mesh 和 p保持冻结，只建立确定性的 auxiliary hierarchy。

## 5.4 Bottom candidate Gate

最终 bottom bare-`F` candidate 必须满足：

```text
full-side factor                 = 0
full-cross-section factor        = 0
global direct/coarse factor      = 0
max factorized local rows        <= 1024
construction peak               <= 35 GiB
strong target                   <= 30 GiB
swap                             = 0
all five true residual           <= 1e-2
modal+/modal-/external residual  <= 1e-3
preferred outer iterations       <= 64
research maximum                 <= 256
```

有正信号后 Codex自动连续执行：

```text
bottom bare F
-> bottom full A_side with physical DtN unchanged
-> same-config top bare F and A_side
-> both-side setup
-> one full Hybrid formal
-> conditional p6/h3 scaling
-> 0.7 nm / 2 TB capacity ledger
```

不得在完成某个小组件或 outcome 后停下来等待审阅。

---

# 6. V8-3：当前 moving-PML 实现的处理

## 6.1 不再原样重跑

禁止再次运行当前：

```text
owner-local full-cross-section core matrix
+ PETSc.COMM_SELF MUMPS core factor
+ two-step local GMRES
+ six-stage sweep
```

不得通过：

```text
延长到12小时
提高内存hard line
减少source但保持同一slow apply
减少checkpoint记录
```

伪造进展。

## 6.2 可保留的实现

允许保留并复用：

```text
z_pml_diagonal_tensors
material-preserving temporary PML tags
fixed quadratic collar
integrated attenuation = 6
full-state multiplicative sweep skeleton
bare-F unchanged/hash checks
```

必须替换：

```text
_owner_submatrix
COMM_SELF full-cross-section MUMPS factor
single-owner full local solve
```

## 6.3 Moving-PML 何时重新进入

只有 V8-2 或 V8-4 已建立一个满足以下条件的 distributed/bounded local service 后，才允许把
PML collar接回：

```text
no full-cross-section factor
max local factor rows <= 1024 or matrix-free local action
setup <= 3600 s
external one-apply <= 1200 s
peak <= 35 GiB preferred, 45 GiB hard
swap = 0
```

重新进入时只先运行：

```text
external_dtn_coupling
one apply
```

达到 finite true residual 和时间 Gate 后，才允许 8/16/32/64。否则分类：

```text
MOVING_PML_DISTRIBUTED_LOCAL_SERVICE_RESOURCE_NEGATIVE
```

并继续其他主线，不再重构第三套 PML local solver。

---

# 7. V8-4：full-spectrum 未通过时的经济型 adaptive impedance Schwarz

本阶段在以下任一条件下自动启动：

```text
FULL_SPECTRUM_SWEEP_NO_SIGNAL
FULL_SPECTRUM_SWEEP_UNSTABLE
FULL_SPECTRUM_SWEEP_NO_BOUNDED_POSITIVE_SIGNAL
FULL_SPECTRUM_CURRENT_IMPLEMENTATION_RESOURCE_UNAVAILABLE
FULL_SPECTRUM_IMPLEMENTATION_BUDGET_EXHAUSTED
```

它不再等待 moving-PML numerical classification。

## 7.1 通俗定位

该路线不要求三个 z-group 是 exact separator，也不假设接口附近材料均匀。它把三维 side
划分为许多有重叠的小型 subdomains：

```text
local solves处理几何、材料和近场误差
adaptive Maxwell-harmonic coarse处理跨subdomain的全局波误差
outer FGMRES仍求精确bare F
```

因此它比 Hybrid-specific interface sweep 更容易迁移到 arbitrary 3D Full3D。

## 7.2 Stage A：bounded local service viability

固定：

```text
3D brick/topology patches
one overlap layer
max local active rows <= 1024
one owner per patch class
partition of unity
local impedance boundary
PC-only absorption shift = 0.1
```

先只构造 local service并运行：

```text
external_dtn_coupling
one apply
```

本阶段不以全局 residual是否立即小于1作为失败标准；必须报告：

```text
patch count
rows-per-patch min/median/max
patch class count
local factor bytes
setup wall
one-apply wall
local RHS/final residual ratio distribution
partition-of-unity error
process-tree peak
```

viability Gate：

```text
max rows <= 1024
all local solves finite
median local residual ratio <= 0.5
90th-percentile local residual ratio <= 0.9
setup <= 3600 s
one apply <= 1200 s
peak <= 35 GiB
swap = 0
```

若 exact bounded patches不能满足资源/局部收缩 Gate，不增加 patch cap。直接进入 fixed
matrix-free LOR/three-grid local service；不得回到 full-cross-section factors。

## 7.3 Stage B：adaptive Maxwell-harmonic coarse

local service通过后，按 Review V6 已冻结的方法定义构造一次 adaptive local harmonic coarse。
不得在 formal h4 上扫描 eigenvalue tolerance。

必须满足：

```text
local generalized eigenproblem定义与引用方法一致
one fixed selection rule
basis owner-distributed
no full basis per-rank replication
coarse matrix sparse/distributed
coarse solve iterative
no dense global direct factor
```

报告：

```text
selected modes per subdomain histogram
total coarse DoF
coarse bytes
coarse communication
local eigenvalue gaps
setup/apply wall
```

如果 local eigenproblem成本过高，只允许 Review V6 已定义的 economical variant；不建立第三种
coarse family。

## 7.4 Stage C：two-source outer screen

固定：

```text
sources      = external_dtn_coupling, fixed_random_repeat_0
FGMRES       = restart 32
checkpoints  = 16 / 32 / 64
max          = 64
```

正信号：

```text
both finite
and (
    both r64 <= 0.5
    or both improve >= 4x vs Route C r64
)
and both log10(r32/r64) >= 0.15
```

有正信号后运行五源并自动进入 V8-2 §5.3–§5.4 的 productionization。

无信号：

```text
both r64 > 0.8
and both log10(r32/r64) < 0.10
```

分类：

```text
ADAPTIVE_SPECTRAL_SCHWARZ_NO_SIGNAL_AT_H4
```

此时才允许停止 Task040 的 side-specific campaign，并必须提交 arbitrary-3D Full3D 的下一任务
handoff。该 handoff不是放弃0.7 nm，而是把已验证或失败的 bounded local、wave/coarse
组件转移到通用 Full3D matrix-free iterative 主线。

---

# 8. 与 parallel research 分支的边界

用户已授权独立 parallel 分支：

```text
chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
```

Task040 执行分支不得整体 merge/rebase/cherry-pick该 research branch。

只有在 V8-2 或 V8-4 已出现明确正信号、并且需要 fixed LOR或structured-background helper 时，
才允许：

```text
只读对应理论/参考实现
重新在Task040 src模块中实现最小必要组件
独立增加focused test
记录来源和差异
```

禁止把 carrier-envelope family 带入 Task040 当前 heavy funnel。carrier路线仍只允许 tiny
E1/E2 feasibility，不与本任务争抢重型计算资源。

---

# 9. 0.7 nm 延伸的硬约束

V8 的 full-spectrum 或 adaptive 正信号只有在删除 mechanism-oracle factors 后，才可能升级为
0.7 nm-oriented architecture。

最终必须满足：

```text
volume high-order H(curl) action        = matrix-free path
full-side factor                        = 0
full-cross-section factor               = 0
global direct factor                    = 0
global dense coarse factor              = 0
physical DtN explicit W                 = 0
physical DtN action                     = FFT/streaming
full interface basis replication        = false
FE-sized numeric allgather              = false
max local factor rows                   <= 1024
Krylov restart/live vectors             = bounded
coarse/interface data                   = owner-distributed
swap                                    = 0
```

完整 h4 candidate通过后，才允许一次 p6/h3 bottom scaling probe。必须测量：

```text
N active rows
operator bytes
PC retained bytes
local/coarse/interface bytes
Krylov bytes
construction transient
process-tree peak
iterations
```

内存指数继续使用：

```math
p_{mem}
=
\frac{
\log(B_{PC,h3}/B_{PC,h4})
}{
\log(N_{h3}/N_{h4})
}.
```

目标：

```text
p_mem <= 1.30
```

0.7 nm ledger必须同时给出：

```text
naive lambda^-3 envelope
accuracy-qualified mesh estimate
measured h4/h3 bytes per DoF
iteration-growth envelope
external-channel growth
low/high memory prediction
```

高位 process-tree planning ceiling仍为：

```text
1.5 TiB
```

其余物理内存保留给 OS、filesystem cache、MPI/runtime 和安全余量。不得把 2 TB 全部当作
可用 RSS。

---

# 10. 最小测试政策

## 10.1 Full-spectrum

只运行：

```text
canonical transform targeted serial
empty-local collective targeted MPI2
two-source classification helper serial
runner marker/schema helper serial
Ruff touched modules
compileall touched modules
```

formal前不运行 full repository pytest，不重复 scale identity test，不运行无关 MPI4。

## 10.2 Adaptive/local service

只运行：

```text
tiny patch coverage/POU serial
owner routing MPI2
max-row cap regression
local residual-ratio regression
coarse distribution tiny test
Ruff/compileall touched modules
```

closeout 时再集中运行一次：

```text
all touched focused tests
repository/benchmark/documentation contracts
```

没有 GitHub Actions 时不得声称 CI。

## 10.3 Implementation bug

Codex可自行最小修复并继续：

```text
path/schema/hash/marker
empty-local ownership
collective-safe error propagation
canonical channel ordering
Alltoallv counts/displacements
workspace/lifecycle
selected-mode provider wiring
watchdog stage timing
checker recomputation
```

要求：

```text
保留失败 root
一个直接 regression
最小 diff
新 SHA重跑受影响阶段
```

不得因为普通 bug、outcome文档或未跑 full pytest而停下来等待审阅。

---

# 11. Heavy-run 预算

本 Review 预授权：

```text
1. one dedicated corrected full-spectrum two-source formal
2. at most one explicit implementation-fix rerun of that formal
3. same-setup five-source extension after positive signal
4. one adaptive bounded-local/coarse two-source formal if full-spectrum does not qualify
5. at most one implementation-fix rerun of adaptive formal
6. one selected full Hybrid formal after factor-free bottom/top qualification
7. one conditional h3 bottom scaling probe after full h4 pass
```

明确不授权：

```text
original moving-PML six-hour rerun
full-side factor retry
Route C 256/512/1000
ordinary ILU/BLR/drop menu
unbounded coarse-rank scan
full target 0.7 nm PDE
simultaneous heavy process trees
```

---

# 12. 自动继续与真正停止 Gate

## 12.1 不需要停止

```text
V8-0 docs adjudication完成
full-spectrum transform identity通过
full-spectrum two-source positive
full-spectrum five-source weak/strong positive
bounded local service通过
adaptive two-source positive
普通implementation bug修复
outcome阶段完成
```

任何 positive route必须继续到：

```text
factor-free local service
bottom bare F
bottom A_side
top
both-side
full Hybrid
h3
0.7 nm capacity ledger
```

## 12.2 必须停止等待审阅

```text
full-spectrum corrected formal仍不能形成可审计结果且implementation budget耗尽
adaptive bounded local service违反max-row或resource Gate
adaptive spectral Schwarz two-source正式no-signal
positive wave layer无法删除full-cross-section factors
same-config top出现无法解释的identity/numerical失败
full Hybrid true residual/physics/resource失败
h3出现明显超线性内存或迭代失控
ABI/physical identity无法恢复
```

full-spectrum单独no-signal不是停止点；它自动进入 adaptive。
current moving-PML resource negative也不是停止点。

---

# 13. Evidence 与 response_v9

至少新增或更新：

```text
outcomes/v8_review_adjudication.md
outcomes/full_spectrum_floquet_sweep.md
outcomes/full_spectrum_two_source_screen.md
outcomes/moving_pml_sweep.md
outcomes/adaptive_spectral_schwarz.md
outcomes/factor_free_local_service.md
outcomes/bottom_full_side.md
outcomes/top_full_side.md
outcomes/both_side_setup.md
outcomes/full_hybrid_result.md
outcomes/h_refinement_scaling.md
outcomes/0p7nm_side_pc_capacity.md
outcomes/full3d_0p7nm_architecture_handoff.md
outcomes/route_signal_ledger.md
outcomes/memory_residual_time_pareto.md
outcomes/test_summary.md
outcomes/summary.md
response_v9.md
```

只为实际运行或到达的阶段创建/更新详细 outcome。未运行阶段在 summary/ledger 中登记即可，
不得创建大量空文档。

`response_v9.md` 必须表格优先，并报告：

```text
branch/HEAD/upstream/worktree
V8 review SHA
V7 identity review adjudication
full-spectrum exact command/source/root/hash
每个stage wall和peak
one-apply与checkpoint residual
route classification与切换理由
moving-PML current implementation是否保持retired
adaptive实际到达位置
factor inventory
0.7 nm blocker消除/未消除项
selective merge = NO
```

---

## 14. 最终审阅结论

```text
Task040                               = continue
V7 full-interface algebra             = accepted pass with D0
full-spectrum numerical method        = still untested after final fix
immediate heavy priority              = dedicated two-source full-spectrum formal
original moving-PML implementation    = no rerun
adaptive Schwarz                      = unlocked fallback
full-side exact factor                = permanently rejected as production path
0.7 nm main requirement               = factor-free + matrix-free + distributed
merge approval                        = NO
```

当前最小、最直接的主线是：

```text
accept existing Schur identity
-> run corrected full-spectrum once with early numerical checkpoints
-> positive: finish factor-free Hybrid path
-> no signal/resource unavailable: immediately run bounded adaptive Schwarz
-> only after both families are genuinely exhausted, hand off to Full3D scalable iterative
```

不得再让已解决的 identity、原样 moving-PML 或重复小测试阻塞这一主线。
