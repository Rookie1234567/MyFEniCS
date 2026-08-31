# Task040 Review Report V9：闭合 full-spectrum source bridge，取得 adaptive coarse 首次数值信号并连续推进 factor-free 主线

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V9
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = e4fe590f43bafd52c2913806fba203da01b367ec
reviewed_implementation_head                = 0ed2ebef3916fa209136310b104ec72b54f167d7
reviewed_previous_review                    = review_report_v8.md
reviewed_response                           = response_v9.md
reviewed_primary_outcomes                   = outcomes/summary.md
                                               outcomes/route_signal_ledger.md
                                               outcomes/full_spectrum_floquet_sweep.md
                                               outcomes/adaptive_spectral_schwarz.md
                                               outcomes/0p7nm_side_pc_capacity.md
review_status                               = CONTINUE_ACCELERATED_SIGNAL_FIRST
Task040_closed                              = false
merge_approval                              = NO
V7_full_interface_identity                  = REVIEW_ADJUDICATED_PASS_D0
full_spectrum_transform_identity            = PASS
full_spectrum_numerical_signal              = NOT_MEASURED_SOURCE_BRIDGE_BLOCKER
adaptive_stage_A_local_service              = COMPONENT_PASS
adaptive_explicit_coarse_numerical_signal   = NOT_MEASURED_RESOURCE_PREFLIGHT_STOP
current_primary_blockers                    = SOURCE_CANONICAL_BRIDGE
                                               COARSE_DIMENSION_AND_EXPLICIT_MATPRODUCT
next_required_stage                         = V9_A_SOURCE_BRIDGE_ONLY_PREFLIGHT
conditional_heavy_stage_1                   = V9_B_FULL_SPECTRUM_TWO_SOURCE_FORMAL
conditional_heavy_stage_2                   = V9_C0_EXPLICIT_COARSE_ONE_RHS_ORACLE
primary_scalable_stage                      = V9_C1_MATRIX_FREE_GALERKIN_COARSE
old_776_route_C                             = retired_no_signal
current_owner_serial_moving_PML              = retired_no_rerun
full_side_factor_rescue                     = permanently_closed
full_target_0p7nm_PDE                       = forbidden_in_Task040
same_branch_continuation                    = required
new_execution_branch                        = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
response_required                           = response_v10.md
```

本 Review 的目标不是再增加一层诊断框架，而是用最少的实现与最多两次有边界的重程序，取得此前始终缺失的 **full bare-`F` true-residual 数值信号**，并在出现正信号后不再停在组件阶段，连续推进到 factor-free bottom、top 和完整 Hybrid。

本轮正式裁决如下。

1. `V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0` 已完成审阅裁决，不重跑。
2. full-spectrum 的 actual transform 已通过；当前失败只发生在 source owner-vector load，不能写成 numerical no-signal。
3. adaptive Stage A 已证明 bounded local patch solve 可以在约 18 GiB 级内存下稳定施加，但单独 one-apply 的 global true residual=`2.390497409724407`，所以它只能作为 local smoother。
4. adaptive Stage B/C 没有数值失败；它在显式构造 `P`、`P^H`、`FP` 和 `P^HFP` 之前，被 45 GiB conservative symbolic memory Gate 正确停止。
5. 当前 100800-dimensional coarse 同时存在两个独立问题：每 patch 160 列尚未做真正的 spectral selection；显式 `FP/P^HFP` 物化产生不可扩展的内存与 transient。
6. 为尽快判断 basis 是否有价值，允许一次研究级高内存 one-RHS oracle；它若有信号，必须立即转为 matrix-free Galerkin coarse，不得成为正式候选。
7. 若 full-spectrum 与 adaptive coarse 都给出真实 no-signal，才切换到已准备的 structured Floquet-background / fixed LOR 路线；不得重开旧 776、普通 ILU 菜单或 owner-serial moving-PML。

---

## 1. 最新证据的正式审阅

### 1.1 Full-interface Schur 已不再是 blocker

Review V8 已根据三个输入尺度、D0/D1、repeat、linearity 和 group backward-error 证据正式选择：

```text
selected_action = D0_lower_memory
classification  = V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0
```

相对误差处于约 `1e-14–1e-13`。旧 V6 absolute-threshold negative 保留为历史 raw 事实，但不得再阻塞 full-spectrum 或 adaptive 路线。

### 1.2 Full-spectrum 已通过 transform，尚未进入数值 apply

最新 formal 已完成：

```text
actual lower / upper rows    = 7560 / 7560
canonical channels per plane = 72
Floquet harmonics            = 105 = 15 x 7
numeric_allgather             = false
full_plane_numeric_replica   = false
transform identity           = PASS
process-tree peak            = 38975795200 B = 36.29903793359375 GiB
swap                         = 0
elapsed                      = 1533.1877333139993 s
```

随后两个 source 均在 `load_and_condense_exact_rhs(...)` 的 owner-vector load 阶段，因 live canonical tokens 与 persisted layout tokens 不一致而停止。没有 source begin/end marker、没有 one-apply、没有 FGMRES checkpoint，PC/action apply count 均为零。

因此当前正式语义只能是：

```text
FULL_SPECTRUM_IMPLEMENTATION_FAILURE_AT_SOURCE_CANONICAL_BRIDGE
FULL_SPECTRUM_NUMERICAL_SIGNAL_NOT_MEASURED
```

不能将 transform pass 写成 solver pass，也不能将 source load failure 写成 full-spectrum no-signal。

### 1.3 Adaptive Stage A 是可用 local service，不是完整 side inverse

Stage A 的正式组件事实为：

```text
patch count                  = 630
rows per patch               = 432 / 432 / 432
one overlap                  = true
partition-of-unity error     = 0
PC-only shift                = 0.1
setup wall                   = 255.8505309909815 s
one apply wall               = 3.498585887020454 s
process-tree peak            = 19211452416 B = 17.892059326171875 GiB
swap                         = 0
local solve residual max     = 4.401656276000086e-15
global bare-F residual ratio = 2.390497409724407
```

局部 factor 的数值正确性和 apply 成本均有正面证据。global residual 大于 1 表明缺失的是跨 patch、跨层和长距离波传播修正，而不是 local factor solve 精度。

### 1.4 Adaptive coarse 当前是 resource-unavailable，不是 numerical negative

Economical harmonic route 已生成：

```text
630 patches x 160 columns = 100800 coarse unknowns
570 local factor classes
630 multi-RHS harmonic solves
max local rows = 432
```

但当前 Stage B/C 仍计划显式执行：

```math
F_P = F P,
\qquad
A_c = P^H F_P = P^H F P.
```

symbolic preflight 的主要 component 为：

| component | projected bytes |
|---|---:|
| `P` | `871970408` |
| `P_H` | `871718408` |
| `F_times_P` | `10653602408` |
| `P_H_times_F_times_P` | `24945446408` |
| PETSc sparse allocation overhead | `37342737632` |
| MatProduct transient | `35599048816` |
| iterative vectors | `543312000` |
| one-patch workspace | `15796544` |
| conservative total | `130502065136 B = 121.539519295 GiB` |

正式进程只实测到 allocation 前的 `18.427753448486328 GiB`；`121.54 GiB` 是 derived projection，不是 measured RSS。由于 `P/P_H/FP/Ac/KSP` 均未分配，adaptive coarse 还没有 one-apply 或 outer residual。

---

## 2. V9 执行纪律：只为首次数值信号付费

V9 必须遵守以下顺序。

```text
A. source bridge only，轻量，先消除身份问题
B. corrected full-spectrum，两源，一次正式重程序
C0. 若B无正信号，使用现成代码做一次高内存 one-RHS coarse oracle
C1. oracle有信号或显式物化资源不可用，改为 matrix-free Galerkin coarse
C2. matrix-free有信号后，才做固定 spectral selection
D. 任一路线有正信号，连续做到 factor-free bottom/top/full Hybrid
E. 两条主路线均真实无信号，自动进入 structured-background/LOR 最小 pilot
```

禁止：

```text
重复V7三尺度identity
重新建立full-side factor
重跑owner-serial moving-PML
恢复776 Route C
扫描普通ILU/drop/BLR参数
扫描full-spectrum background/cutoff/pair sequence/sweep count
先实现复杂adaptive controller再测one-apply
为每个小修复停止等待review
```

只有 identity、数值 no-signal、资源 hard stop、holdout/generalization、factor-free scalability、top 或 full-Hybrid Gate 才停止等待审阅。

---

# 3. V9-A：source bridge only canonical preflight

## 3.1 目的

在不建立三个 group factors、不建立 full-spectrum transform、不运行 PDE solve 的轻量进程中，证明两个冻结 RHS 能被安全地重建到 current active PETSc ownership。

固定 source：

```text
external_dtn_coupling
fixed_random_repeat_0
```

## 3.2 新入口

新增薄入口，推荐：

```text
--v9-source-bridge-only
```

它只允许创建：

```text
current active layout metadata
current canonical physical-key inventory
two source canonical packets/current owner Vec
source roundtrip/checker artifacts
```

禁止创建：

```text
full-side factor
three group factors
interface Schur action
full-spectrum transform
QEP
physical DtN operator
outer FGMRES
```

## 3.3 Canonical identity 合同

不得再要求：

```text
persisted PETSc local token order == current PETSc local token order
persisted raw global rows          == current raw global rows
```

必须要求 owner-independent physical key 的双射。canonical key 至少应绑定：

```text
source label
active side/domain identity
periodic master identity or canonical periodic coordinate index
entity dimension and canonical entity/moment identity
tangential family/component
orientation/conjugation sign
Floquet phase application count
```

允许 compact metadata allgather；禁止 FE-sized numeric allgather。complex values 应按 key owner-sharded 保存和路由。

优先实现路径：

```text
persisted canonical key/value packet
→ validate physical-key set
→ repartition values to current PETSc row owner
→ build current active RHS
```

若 persisted descriptor 确实不包含足够的 owner-independent key，允许使用当前仓库中冻结的 source provider 在 current process 重新生成相同 source，但必须绑定相同 input/physical/source semantics，并证明 canonical values 与已有 authority 在可比较 key 上一致。禁止按旧 raw row index 猜测映射。

## 3.4 必须检查

两个 source 均必须报告：

```text
input / physical / resolved / source semantic SHA
persisted key count
current key count
missing / extra / duplicate key count
key-class histogram
orientation and phase-once audit
persisted canonical value hash
current canonical value hash
active RHS norm
owner-vector -> canonical -> owner-vector roundtrip
repeated current reconstruction difference
condensed RHS repeat difference
numeric allgather = false
```

Gate：

```text
missing keys                       = 0
extra keys                         = 0
duplicate keys                     = 0
phase application count            = 1
owner roundtrip relative error      <= 1e-12
repeated reconstruction relative    <= 1e-12
source norm relative difference     <= 1e-12
condensed RHS repeat relative       <= 1e-12
all values finite                   = true
```

先运行 serial 与 MPI2 focused regression；随后允许一次 MPI8 source-only preflight。MPI8 source-only 必须在不建立 factors 的条件下完成。

## 3.5 决策

```text
两源均通过：
    classification = V9_SOURCE_CANONICAL_BRIDGE_PASS
    写出hash-bound owner-independent source packet
    自动进入V9-B

明确的path/schema/owner bug：
    保留失败root
    最小修复 + 一个直接serial/MPI2 regression
    自动重跑source-only，不等待review

physical key set真实不兼容或缺少不可恢复身份：
    classification = SOURCE_AUTHORITY_CANONICAL_IDENTITY_UNAVAILABLE
    禁止heavy full-spectrum
    自动进入V9-C0
```

V9-A 不得因完成轻量 packet 或文档而停止。

---

# 4. V9-B：corrected full-spectrum two-source formal

## 4.1 入口与冻结项

只在 V9-A 两源通过后运行。继续使用独立入口：

```text
--v8-full-spectrum-only
```

或增加等价的 `--v9-full-spectrum-only` 薄别名；不得复制数值核心。

冻结：

```text
case                  = 5 nm / 1 deg / S / p6h4 / bottom
MPI / threads         = 8 / 1
bare operator         = current explicit F
source packet         = V9-A hash-bound canonical packet
Schur action          = review-adjudicated D0
transform             = existing 72 x 105 actual transform
full-side factor      = 0
group factors         = 3, mechanism oracle only
QEP                    = 0
physical DtN          = unchanged/not rebuilt for this bottom bare-F screen
```

不得再运行 V7 scale identity、D0/D1、partition、refinement 或 exact-output production。

## 4.2 新增 marker

在原有 marker 上增加：

```text
v9_full_spectrum_source_packet_validated
v9_full_spectrum_external_owner_vector_ready
v9_full_spectrum_random0_owner_vector_ready
```

然后必须得到：

```text
one_apply_begin/end
r8 / r16 / r32 / r64
```

每个 marker 保存 process-tree RSS、swap、stage wall、PC/action apply count 和 source identity。

## 4.3 资源边界

```text
minimum MemAvailable       = 96 GiB
preferred process-tree RSS <= 40 GiB
hard stop                  = 45 GiB
swap                       = 0
setup target               <= 1800 s
one-apply target/source    <= 1200 s
total wall hard cap        = 10800 s
```

## 4.4 两源分类

沿用 V8 的固定判定，不新增参数扫描。

正信号满足任一：

```text
两源 r32 <= 0.7
两源 16→32 均下降 >= 0.15 decade
两源 r64 <= 0.5
```

严格 no-signal：

```text
两源 r64 > 0.8
且两源 32→64 下降均 < 0.10 decade
```

若 r64 位于中间区间，只在 elapsed、RSS 和 swap 条件均满足现有 conditional contract 时允许同 setup 零初值 replay 到 128；禁止 256。

## 4.5 后续

```text
positive:
    同一setup扩展五源
    若五源bounded positive，进入V9-D factor-free wave-layer组合

strict no-signal / unstable:
    不扫描symbol参数
    自动进入V9-C0

V9-A已通过后再次出现owner/source identity failure：
    视为full-spectrum integration bug
    只允许一个最小修复root
    修复仍失败则退休当前full-spectrum implementation并进入V9-C0
```

full-spectrum 使用三个 cross-section group factors，因此即使数值正信号，也只能称为 wave-transmission mechanism pass；最终候选必须在 V9-D 删除这些 factors。

---

# 5. V9-C0：一次显式 adaptive coarse 高内存 one-RHS oracle

## 5.1 为什么允许

当前 `P/FP/P^HFP` 代码已存在，而 100800-dimensional basis 从未获得任何 global true-residual 数值结果。工作站约 2 TB，当前 `121.54 GiB` conservative projection 不构成整机容量禁止。一次严格受限的高内存 oracle 可以快速回答：

> 当前 160-columns-per-patch coarse content 是否至少包含有效的 global error directions？

这项运行只判断 basis 内容，不是可扩展候选，也不改变 Task40 的 45 GiB 正式目标。

## 5.2 固定范围

```text
source                   = external_dtn_coupling only
local action             = qualified Stage A patches
coarse basis             = current 630 x 160 economical columns
P / P_H / FP / Ac        = current explicit implementation
coarse solver            = current bounded GMRES/Jacobi
outer FGMRES             = not run initially
composite apply          = local → coarse → local, exactly one
full-side factor         = 0
global direct factor     = 0
coarse direct factor     = 0
```

禁止五源、top、full Hybrid 或参数扫描。

## 5.3 资源与 marker

运行前：

```text
MemAvailable >= 320 GiB
swap = 0
一次只运行一个heavy case
```

资源线：

```text
preferred peak <= 160 GiB
warning        <= 176 GiB
hard stop       = 192 GiB
setup hard cap  = 10800 s
total hard cap  = 14400 s
one apply cap   = 1800 s
```

必须写：

```text
P_ready
P_H_ready
FP_ready
Ac_ready
coarse_ksp_ready
external_one_apply_begin/end
cleanup_complete
```

每个 stage 保存 actual Mat rows/columns/NNZ/memory、MatProduct wall、process-tree RSS 和 swap。derived projection 与 measured RSS 继续分开。

## 5.4 数值分类

Stage A local-only baseline：

```text
rho_local = 2.390497409724407
```

显式 coarse composite one-apply 得到 `rho_coarse`。

```text
strong positive:
    rho_coarse <= 0.5

weak positive:
    rho_coarse <= 1.0
    或 rho_local / rho_coarse >= 2.0

no signal:
    rho_coarse >= 1.5
    或 non-finite/unstable

intermediate:
    1.0 < rho_coarse < 1.5 且 improvement < 2
```

只有 intermediate 时允许 exactly 8 outer FGMRES iterations；若 `r8<=0.8` 或相对零解下降至少 `0.20 decade`，按 weak positive处理，否则按 no-signal处理。

## 5.5 决策

```text
positive:
    classification = ADAPTIVE_COARSE_CONTENT_POSITIVE_EXPLICIT_ORACLE
    显式Ac不得继续到五源
    自动进入V9-C1 matrix-free实现

resource/time unavailable before one-apply:
    不写numerical negative
    自动进入V9-C1，因为被证明的blocker正是显式物化

no-signal:
    classification = CURRENT_160_PER_PATCH_HARMONIC_COARSE_NO_SIGNAL
    不实现同一basis的matrix-free版本
    自动进入V9-E structured-background/LOR fallback
```

显式 oracle 只允许一次，不得通过提高到 256/512 GiB 或延长到下一天反复追逐结果。

---

# 6. V9-C1：matrix-free Galerkin coarse

## 6.1 改变哪一步

真实 fine operator仍为 current bare `F`。只删除显式：

```text
P_H
F_times_P
P_H_times_F_times_P
MatProduct transient
```

coarse operator改成 PETSc MatShell：

```math
A_c c = P^H\bigl(F(Pc)\bigr).
```

第一版允许保留一个 distributed sparse `P`，因为当前 projection 约 `0.81 GiB`、无 per-rank replication，且在 selected rank bounded 时为近线性对象。禁止构造显式 `P_H`、`FP` 或 `Ac`。

后续 strong candidate 可再将 `P/P^H` 改成 owner-local streamed patch action；V9-C1 不要求先完成该优化才测数值信号。

## 6.2 最小实现合同

MatShell 一次 multiply：

```text
coarse c
→ distributed P.mult(c, fine_work_0)
→ bare_F.mult(fine_work_0, fine_work_1)
→ P.multHermitian(fine_work_1, coarse_y)
```

必须：

```text
complex128
repeat/linearity relative <= 1e-11
serial/MPI2 tiny explicit-vs-shell action relative <= 1e-10
no FE-sized numeric allgather
no full basis per-rank replica
no global/coarse direct factor
```

coarse KSP 初始固定：

```text
GMRES
restart = 8
max_it  = 8, 16, conditional 32
PC      = NONE
zero initial guess
```

不得先增加复杂 coarse PC。若 PCNONE 在 8 步完全无下降，只允许一个自然 patch-block/Jacobi coarse PC；禁止 global sparse factor。

## 6.3 精确 vector inventory

不得继续使用 `75 fine + 70 coarse` 的保守固定预算作为实际分配。必须分别登记：

```text
outer KSP live fine vectors
local Stage-A work vectors
MatShell P/F work vectors
coarse KSP vectors
source/solution/residual vectors
```

并按真实 simultaneous lifecycle分配和销毁。研究 screen 先只分配 one-apply 和 inner coarse KSP 所需的最小对象。

## 6.4 第一次数值 Gate

先只运行：

```text
source = external_dtn_coupling
coarse KSP = 8 / 16 / conditional 32
one composite local-coarse-local apply
```

资源：

```text
preferred peak <= 35 GiB
hard stop       = 45 GiB
swap            = 0
setup cap       = 3600 s
one apply cap   = 1800 s
```

若 V9-C0 取得 explicit oracle结果，matrix-free one-apply 与 explicit one-apply 必须在：

```text
relative difference <= 1e-8
```

内一致；否则先处理 action identity，不得比较 residual趋势。

正/no-signal 判定沿用 V9-C0。只有 weak/strong positive 才进入 C2 与第二 source。

---

# 7. V9-C2：在现有 160-column subspace 内做一次固定 spectral selection

## 7.1 进入条件

仅当 full 160-column matrix-free coarse 对 external source有 weak/strong positive 时运行。若 full basis无信号，压缩不会创造缺失的全局方向，禁止继续。

## 7.2 固定 selection

不得扫描 rank menu。复用仓库已有 positive Maxwell-harmonic metric和固定阈值：

```text
rho  = 0.007865985598112241
rho2 = 6.187372942970919e-05
```

在每个 patch 已生成的 160-column harmonic subspace `W_l` 中构造：

```math
B_l = W_l^H G_l W_l,
\qquad
A_l = (D_l W_l)^H G_l (D_l W_l),
```

并解：

```math
A_l q = \lambda B_l q.
```

只保留满足固定理论判据的方向；禁止为了满足内存人为修改阈值或只保留训练 source最优方向。

为避免重演 exact B1 的 10800 s wall：

```text
复用已生成harmonic columns
复用/缓存local metric与factor-class数据
bounded batch处理patch
每64 patches写一次wall/RSS/selected-count marker
不重新生成全部exact B1 authority
```

## 7.3 0.7 nm-oriented rank Gate

报告 selected-count histogram、total rank 和 coarse/fine ratio。不得静默截断。结构资格要求：

```text
max selected modes per patch <= 32
selected coarse dimension / fine active dimension <= 0.25
```

若固定阈值产生更大空间，只能分类为：

```text
5NM_MECHANISM_POSITIVE_BUT_COARSE_NOT_0P7NM_SCALABLE
```

不能包装成 scalable candidate。

## 7.4 两源与五源

压缩后先运行：

```text
external_dtn_coupling
fixed_random_repeat_0
iterations = 16 / 32 / 64
```

两源均有 bounded positive 后，自动扩展：

```text
modal_traction_positive
modal_traction_negative
fixed_random_repeat_1
```

holdout 不得比 full 160-column basis 恶化超过 fixed roundoff allowance；否则 classification 为 overfit/selection inadequate。

---

# 8. V9-D：任一路线出现正信号后的连续主线

## 8.1 Full-spectrum 正信号路径

full-spectrum 的三个 group factors只允许作为 mechanism oracle。五源 positive 后，必须建立：

```text
Stage-A bounded local pre-smoothing
→ full-spectrum actual-Gamma wave correction
→ Stage-A bounded local post-smoothing
```

exact outer operator 使用 bare `F`；wave layer 的 interface lift/back-substitution不得再依赖 full-cross-section factor。允许复用 bounded patch action和 actual 72x105 transform。

## 8.2 Adaptive coarse 正信号路径

Stage-A local action + matrix-free selected coarse 本身构成候选 multiplicative PC：

```math
y_0 = P_{loc}^{-1}r,
```

```math
r_1 = r-Fy_0,
```

```math
y_1 = y_0 + P A_c^{-1}P^H r_1,
```

```math
P^{-1}r = y_1 + P_{loc}^{-1}(r-Fy_1).
```

## 8.3 必须连续执行到的 Gate

任一 factor-free family 对五源达到正信号后，Codex不得在小阶段停止，按顺序连续执行：

```text
1. bottom bare-F five-source FGMRES，最大256
2. bottom完整A_side，physical DtN保持不变
3. top使用完全相同算法与参数
4. both-side simultaneous setup
5. 唯一一次full Hybrid formal
6. recovery / R/T/A / A_volume / selected E/H / canonical / channels
7. 条件p6/h3 setup+apply+有限checkpoint
8. 0.7 nm / 2 TB capacity ledger
```

最终 side numerical Gate：

```text
all five full bare-F true residual <= 1e-2
modal+ / modal- / external       <= 1e-3
iterations                        <= 256
```

最终结构 Gate：

```text
full-side factor count              = 0
full-cross-section factor count     = 0
global direct/coarse factor count   = 0
max local factor rows               <= 1024
FE-sized numeric allgather          = false
full-basis per-rank replication     = false
construction peak                   <= 35 GiB
strong target                       <= 30 GiB
swap                                = 0
```

若 h4 positive 仍依赖 100800-column uncompressed basis或显式 sparse `Ac`，它只能称为 mechanism pass，不能进入 h3/0.7 nm scalability claim。

---

# 9. V9-E：两条当前主路线均真实无信号时的自动 fallback

进入条件必须是：

```text
full-spectrum 已得到真实 two-source no-signal/unstable
且 adaptive coarse 已得到真实 one-apply/8-step no-signal
```

source identity failure或resource unavailable不能冒充 numerical no-signal。

满足进入条件后，不重开旧路线。Codex获准只读参考：

```text
branch = chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
relevant files:
    docs/task040_parallel_floquet_envelope_hcurl/structured_background_fft_hcurl.md
    docs/task040_parallel_floquet_envelope_hcurl/low_order_refined_hcurl.md
    src/solvers/floquet_background_hcurl.py
    src/test/test_319_task040_parallel_background_hcurl.py
```

只允许 selective file-level migration，不整体 merge/cherry-pick research branch。

固定 fallback 顺序：

```text
B0 constant Floquet background inverse
B1 z-layered Floquet background inverse
fixed LOR/matrix-free H(curl) local service
```

先完成 tiny homogeneous/layered DOLFINx MatShell identity；只有 reference residual至少改善 8 倍才进入 reduced 5 nm bottom source。B0/B1均无信号时，停止 Task40 并产出 Full3D/Hybrid共同的下一架构 handoff；不得再扫描大量背景介电常数或 shift。

本 fallback 不重新启动 carrier-envelope 或自动 h/p adaptivity。

---

# 10. 测试政策

只运行与修改直接相关的最小测试。

V9-A：

```text
canonical source key bijection serial
source ownership remap MPI2
phase/orientation once
roundtrip/hash helper
source-only MPI8 preflight
```

V9-B：

```text
source packet load serial/MPI2
marker/schema/classification helpers
touched Ruff / compileall
```

V9-C：

```text
MatShell Ac explicit-reference serial
MatShell Ac MPI2 ownership
P/P^H adjoint identity
repeat/linearity
vector lifecycle
resource preflight arithmetic
fixed spectral-selection tiny test
```

禁止每个小阶段运行 full repository pytest、无关 MPI4 或 Task39 heavy regression。最终 closeout 时集中运行 repository/benchmark/documentation contracts。

普通 path/schema/hash/owner routing/marker/workspace bug：保留失败 root，最小修复，加一个直接 regression 后自动继续。

---

# 11. 停止条件

只有下列事件停止等待下一轮 review：

```text
1. V9-A发现不可恢复的physical canonical source identity缺失；
2. V9-B在已通过source preflight后仍耗尽唯一integration-fix预算；
3. full-spectrum取得正式two-source no-signal；
4. adaptive coarse取得正式numerical no-signal；
5. matrix-free/selected coarse超出45 GiB或rank scalability Gate；
6. factor-free bottom五源、top、full Hybrid或h3失败；
7. B0/B1 structured-background最小pilot均无信号；
8. ABI、swap、physical/input/hash identity真实失败。
```

其中第3项单独发生时不停止，自动进入 adaptive；第4项单独发生且 full-spectrum已失败时才进入 fallback；只有路线漏斗到达真实 Gate 后才停止。

---

# 12. 必交证据

新增或更新：

```text
docs/task040_hybrid_side_factor_pc/response_v10.md
outcomes/v9_source_canonical_bridge.md
outcomes/full_spectrum_floquet_sweep.md
outcomes/adaptive_spectral_schwarz.md
outcomes/matrix_free_galerkin_coarse.md
outcomes/route_signal_ledger.md
outcomes/memory_residual_time_pareto.md
outcomes/0p7nm_side_pc_capacity.md
outcomes/summary.md
```

每个 formal 必须绑定：

```text
branch / source HEAD / upstream / clean status
input_original / resolved / physical SHA
MPI / threads / ABI
exact command
raw marker hash
run summary hash
process-tree RSS / swap / wall
factor and vector lifecycle
true residual checkpoints
measured / derived / predicted / not_run classification
```

若进入 V9-E，还需更新：

```text
outcomes/full3d_0p7nm_architecture_handoff.md
```

但不得在 current adaptive 只有 resource stop、没有 numerical negative 时提前创建“方法失败”式 handoff。

---

# 13. 合并裁决

```text
Task040 status           = OPEN_CONTINUE
selective merge approval = NO
master merge approval    = NO
```

V9 的成功定义不是“又完成一个组件”，而是至少取得以下之一：

```text
FULL_SPECTRUM_TWO_SOURCE_NUMERICAL_CLASSIFICATION
ADAPTIVE_COARSE_ONE_RHS_NUMERICAL_CLASSIFICATION
```

若取得正信号，则必须继续到 factor-free five-source side candidate；若两者均取得真实 no-signal，则进入结构化背景/LOR fallback，而不是回到已经证伪或不可扩展的旧路线。
