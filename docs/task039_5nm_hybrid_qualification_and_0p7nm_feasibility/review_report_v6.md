# Task039 Review Report V6：Hybrid iterative 半内存目标与 0.7 nm 可扩展 side solver

## 0. 审阅决定

```text
review                                  = Task039 Review Report V6
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 6694530f4e38bfa3f563eaa66cddc5268009e6dc
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
primary_method_line                     = Hybrid direct authority + Hybrid iterative architecture research
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
matched_Hybrid_direct_reference_GiB     = 93.377006531
half_memory_target_GiB                  = 46.6885032655
stretch_60pct_saving_target_GiB         = 37.3508026124
Full3D_new_heavy_run                    = forbidden
full_0p7nm_PDE                          = forbidden
third_BLR_profile                       = forbidden
generic_fixed_budget_scan               = forbidden
h5_sidecar_rerun                        = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_iterative_timeout_seconds   = 28800 total, one time only
response_required                       = response_v7.md
```

本 Review 接受用户提出的战略目标：为了让 5 nm Hybrid iterative 的成果对未来 0.7 nm
具有实际意义，正式 iterative 候选不应只比 Hybrid direct 略省内存，而应在同一 h4 Hybrid
方程下把全过程 process-tree RSS 至少降低 50%。

这个 50% 目标是合理的，也是必要的工程约束，因为 0.7 nm 还会叠加更大的 external
channel inventory、可能增加的内部模式数、channel/modal Schur、P/T coupling、恢复对象和
allocator 高水位。5 nm 只节省 10%–20% 通常不足以为这些未来增长留出安全余量。

但必须同时保留边界：

> h4 相对 direct 节省 50% 是 0.7 nm-oriented strategic qualification 的必要条件，不是
> 0.7 nm 完整 PDE 可行性的充分条件。候选还必须消除显式大 `W`、避免 full side exact
> factor，并证明 coarse/channel/modal problem 的增长受控。

---

## 1. V5 最终结果与本轮继承边界

### 1.1 当前统一结果

| 路径 | 数值/物理 | process-tree / resource | 当前分类 |
|---|---|---:|---|
| h4 Hybrid direct | own residual、projection、traction、R/T/A/A_volume、canonical、external identity 通过 | `93.377006531 GiB` | `HYBRID_DIRECT_H4_OWN_PASS` |
| V4 h4 exact-side iterative | 1 outer；五 residual、recovery、physics、direct comparison 通过 | `104.334560394 GiB` | numerical/physics pass，resource fail |
| V5-2 exact-side setup-only | 15-marker setup evidence 完整 | `85.376991272 GiB` | advancement 未满足；非 full qualification |
| V5-3/4/5 compaction | factor-only、single modal Schur、固定 GMRES10、streaming-W component 已实现 | fresh h4 process-tree RSS 未测 | research evidence only |
| BLR 1e-5 / 1e-3 | numerical Gate 未建立 | bottom `75.896274567 / 95.398345947 GiB` | resource negative；family closed |
| fixed-budget32 bottom | modal traction residual `0.7481094 / 0.7377547`，limit `1e-2` | setup `21.677326202 GiB` | numerical negative controlled stop |
| current-lifecycle h5 direct sidecar | 主 residual/physics 多数通过，top condensed residual `1.0501691e-9 > 1e-9` | `50.356239319 GiB` | nonblocking borderline controlled-negative |

V5 已经充分否定以下简单延续：

```text
第三个 MUMPS BLR profile
只把 fixed side Krylov budget 从 32 改成 64/128
普通 ILU0/ILU1/drop-tolerance 参数扫描
把 streaming-W 的几十 MiB 对象变化写成 h4 十余 GiB RSS 修复
```

### 1.2 h4 峰值主因

V5-2 marker 表明，exact-side setup 峰值位于：

```text
bottom factor ready
→ bottom Woodbury construction
```

关键观测为：

```text
bottom F ready          = 77.0812 GiB
bottom factor ready     = 85.3308 GiB
bottom Woodbury ready   = 79.8107 GiB
bottom cleanup          = 48.4827 GiB

top factor ready        = 83.7078 GiB
both actions ready      = 79.6327 GiB
modal Schur ready       = 80.5443 GiB
outer KSP setup ready   = 71.8689 GiB
```

每个 side exact factor 的派生容量约为 25.7 GB。当前主要 blocker 是 full side sparse factor
及其与 F、Woodbury construction 和运行时 allocator 的重叠，而不是 outer iteration 数、
M480 packet、dense modal Schur 或当前 5 nm W 本身。

### 1.3 V5 仍未回答的问题

V5-3/V5-4 已实现 factor-only state、single-build modal Schur 和 GMRES10，但没有做 fresh
h4 post-compaction process-tree 测量。因此不能直接判定这些实现无效，也不能把对象 bytes
相加后宣称达到任何 RSS saving。V6 必须先关闭这个证据缺口。

---

## 2. V6 内存目标与正式分类

matched baseline 只使用既有 h4 Hybrid direct：

```text
B_direct = 93.377006531 GiB
```

新的正式目标为：

```math
B_{\mathrm{iterative}}
\le 0.5 B_{\mathrm{direct}}
=46.6885032655\ \mathrm{GiB}.
```

| 分类 | full h4 iterative peak RSS | 含义 |
|---|---:|---|
| resource regression | `>=93.377006531 GiB` | 不如 direct，失败 |
| regression removed only | `<93.377006531` 且 `>65.363904572 GiB` | 有进展，但不具备 0.7 nm 战略意义 |
| substantial research progress | `<=65.363904572` 且 `>46.688503266 GiB` | 至少节省 30%，仍未达到正式目标 |
| half-memory strategic pass | `<=46.688503266 GiB` | 相对 direct 至少节省 50%；V6 正式资源目标 |
| stretch pass | `<=37.350802612 GiB` | 相对 direct 至少节省 60% |

V5 的旧 20% line `74.701605225 GiB` 仅保留为历史中间线，不再称为正式 meaningful pass。
任何结果只有在完整数值、物理、生命周期和 process-tree Gate 全部通过后，才可使用：

```text
TASK039_V6_HYBRID_ITERATIVE_HALF_MEMORY_STRATEGIC_PASS
```

即使达到该分类，也必须写：

```text
fixed 5 nm h4 Hybrid case only
not 0.7 nm PDE qualification
not arbitrary-3D qualification
not ordinary production default
```

---

## 3. V6 总体技术判断

V6 不再把主力放在“如何把 full exact side factor 压小一点”。当前结果说明：

```text
exact-side LU = 很强的数值 oracle
exact-side LU ≠ 面向 0.7 nm 的生产 side inverse
```

后续采用三层路线：

1. **先验收已有 compaction**：用一次 fresh setup-only 判断 exact-side 是否还有意外的巨大
   生命周期收益；
2. **主力开发 port/modal-aware two-level side PC**：用物理困难子空间校正便宜 base
   inverse，不再依赖完整 side direct factor；
3. **并行审计 z-layer sweeping 与 matrix-free channel/modal action**：为 0.7 nm 建立不会
   随 side rows、external channels 或 M 失控的长期结构。

existing exact response spool 和必要时生成的最小 response packet只作为 oracle/validation
数据，不得把“先做一次大 exact factor”隐藏在正式 candidate 的生产流程中。

---

## 4. V6-0：继承审计

Codex 拉取本 Review 后，第一项提交必须为 docs-only：

```text
docs(task039): audit v6 half-memory hybrid baseline
```

创建：

```text
outcomes/review_v6_inherited_audit.md
```

至少记录：

```text
branch / HEAD / upstream / ahead-behind / worktree
response_v6 和 V5 compact hash
h4 direct / V4 iterative / V5-2 resource baseline
V5-3 factor-only、V5-4 single-Schur/GMRES10、V5-5 streaming code identity
existing bottom exact-response spool availability and hashes
MemAvailable / swap / disk / ABI / MPI / threads
50% target和setup advancement line
Full3D、0.7 nm PDE、BLR、generic budget scan均冻结
```

不得夹带 Python 修改或启动 heavy run。

---

## 5. V6-1：fresh post-compaction exact-side setup-only

### 5.1 目的

只回答：

> V5 已实现的 factor-only、single modal Schur、固定线性 GMRES10 和严格生命周期，在真实
> h4/M480/MPI8 process tree 中到底能把 setup peak 降到多少？

### 5.2 冻结路径

```text
same h4 selected-mode packet
same 5 nm / 1° / S / M480 / MPI8
same exact Hybrid equation
factor-only side handle
single-build modal Schur + frozen sampled repeat
fixed linear PC identity
GMRES restart10 setup
bottom build → cleanup → top build
retained-W for attribution consistency
no outer solve / recovery / RTA / field
```

本轮不把 streaming-W 接入该 measurement，因为 h4 两侧 W 到 streaming C 的派生对象差异
只有约 0.0565 GiB，无法决定 50% Gate。streaming-W 继续作为未来 0.7 nm component保留。

### 5.3 setup advancement Gate

为了让完整 full formal 有足够余量，setup-only 必须同时满足：

```text
process-tree peak                    <= 42.019652939 GiB
outer_ksp_ready resident RSS         <= 35.0 GiB
swap                                 = 0
bottom/top exact factors after cleanup = 0/0
packet/QEP references released       = true
all factor-only/single-Schur contracts pass
```

`42.019652939 GiB` 是 half-memory target 的 90%，为 outer solve、Krylov、recovery 和
telemetry保留约10%余量。

若 setup peak 高于该线：

```text
exact-side full formal = forbidden
exact-side role        = oracle only
```

不得因为低于 direct 或低于 V5-2 就启动 full solve。

### 5.4 piggyback 证据

本次 setup-only 在不增加第二个 heavy run 的前提下，同时输出：

```text
side F 的 z-layer ownership与NNZ block graph
same-layer / adjacent-layer / long-range coupling counts
block bandwidth与layer row counts
frozen validation RHS exact-response hashes（已有 spool优先复用）
```

不得为生成大规模 response basis 延长 factor 生命周期；只允许固定少量 validation probes，
按 owner-row shard流式写出。

输出：

```text
outcomes/v6_post_compaction_exact_side_setup.md
outcomes/v6_side_layer_graph_audit.md
compact records under case 103 records/
```

---

## 6. exact-side 后续边界

若 V6-1 通过 setup Gate，只允许一次完整 h4 exact-side formal。若未通过，则直接跳过。

完整 exact-side formal 必须：

```text
peak RSS                         <= 46.688503266 GiB
all five residuals               <= 5e-9
R/T/A/A_volume、E/H、canonical、channels 全部通过
6h/8h time policy                通过
```

若 full formal 峰值在 `46.6885–93.3770 GiB` 之间，只能分类为：

```text
EXACT_SIDE_RESOURCE_PROGRESS_HALF_MEMORY_NOT_MET
```

并立即把 exact-side 关闭为 production candidate。不得继续通过 restart、batch、allocator
或小参数微调反复重跑。

---

## 7. V6 主 family：port/modal-aware Petrov–Galerkin two-level side PC

### 7.1 它解决什么问题

V5 fixed-budget32 使用通用 ILU0+Krylov，modal traction probe residual 仍约 0.74，说明便宜
base inverse没有捕捉到 Hybrid 真正关心的困难方向。

新的 two-level side PC 不要求 base inverse在整个 side 空间都准确。它把误差分为：

```text
普通补空间          → 便宜 base inverse M0^-1
port/modal 困难子空间 → 小型 coarse correction
```

采用固定线性 residual-correction 形式：

```math
M^{-1}
=
M_0^{-1}
+
Z E^{-1}Y^H\left(I-FM_0^{-1}\right),
\qquad
E=Y^H F Z.
```

其中：

```text
F = one-side matrix-free operator
Z = distributed right coarse basis
Y = distributed left/test basis
E = bounded Petrov–Galerkin coarse operator
```

因为 side system 是 complex、lossy、non-Hermitian，V6 不把 `Y=Z` 的 Galerkin 假设当作
默认。必须显式构造或审计 left/right basis和 biorthogonality。

### 7.2 物理 source families

coarse basis必须来自固定的物理源族，而不是一般随机 seed：

```text
internal positive modal traction block
internal negative modal traction block
external DtN C block
discrete H(curl) gradient / near-null family
nonzero physical side RHS（若存在）
```

left/test family至少覆盖：

```text
projection / D adjoint-relevant directions
positive/negative modal dual directions
external channel dual sketches
```

训练与验证必须分离：

```text
training sketches  = 预先冻结、hash-bound
holdout probes     = 不参与basis构造
exact response     = 只用于validation，不用于formal candidate在线构造
```

existing exact-response spool可复用；若缺失，只允许在 V6-1 factor存在期间流式生成少量固定
holdout response，不得另开一个 exact-factor heavy campaign。

### 7.3 nested enrichment，不做无边界扫描

允许一个进程内的固定嵌套 ladder：

```text
coarse rank cap = 512
checkpoints      = 64 / 128 / 256 / 512
stop             = first passing rank
```

这不是普通参数 sweep：basis固定嵌套，先后 rank共享同一构造，不能改变 seed、source family、
阈值、base ILU或其他参数来追正结果。

所有 basis必须 owner-row 分布；禁止每个 MPI rank复制完整 side basis。dense coarse matrix只有
在 rank `<=512` 时允许复制，并必须报告每 rank bytes；长期 0.7 nm 设计仍需 distributed
coarse solve。

### 7.4 bottom-first component Gate

先只运行 bottom side component。必须同时满足：

```text
all mandatory probe values finite
repeat / linearity error                 <= 1e-10
modal traction positive true residual   <= 1e-2
modal traction negative true residual   <= 1e-2
external DtN holdout true residual       <= 1e-2
random holdout true residual             <= 1e-2
preferred modal/external residual        <= 1e-3
no exact side factor resident            = true
no global direct factor                  = true
coarse rank                              <= 512
bottom construction peak                 <= 22 GiB
bottom retained apply-state RSS          <= 16 GiB
swap                                     = 0
```

若 rank512仍未通过 numerical Gate，family分类为 numerical negative并停止；不得增加 rank、
重新选择训练 probe或修改 base ILU参数。

### 7.5 top 与 two-side setup

只有 bottom component通过，才允许：

```text
one top component
→ one both-side setup-only
```

both-side setup-only必须：

```text
process-tree peak                <= 42.019652939 GiB
outer_ksp_ready resident RSS     <= 35.0 GiB
coarse rank bottom/top           <= 512/512
no exact/global direct factor
```

通过后，最多选择一个固定 two-level candidate进入完整 h4 formal。

### 7.6 outer solver

若 coarse basis、E 和 base action在整个 solve中固定且 linearity/repeat通过，可使用：

```text
right GMRES restart10
```

若任何 inner tolerance、coarse enrichment或action随 iteration变化，必须使用：

```text
right FGMRES
```

不得为了减少 Krylov vectors错误地把可变 PC 标成固定 PC。

---

## 8. V6 正式 h4 two-level candidate Gate

最多运行一次完整 formal：

```text
5 nm / 1° / phi0 / S
p6/h4 / M480 / MPI8
same selected-mode packet
same Hybrid direct observable reference
global direct factor = 0
side exact factor    = 0
```

### 8.1 数值与物理 Gate

```text
KSP reason                         > 0
reported/global/bottom/top/modal   <= 5e-9
projection                         <= 1e-8
exact traction bottom/top          <= 1e-8
R/T/A/A_volume absolute delta      <= 1e-6
selected E relative L2             <= 5e-3
selected H relative L2             <= 5e-3
canonical active/full relative L2  <= 1e-5
normal flux relative delta         <= 1e-4
power-weighted channels            <= 1e-4
external key set/hash              exact
energy closure                     <= 1e-5
swap                               = 0
```

### 8.2 正式资源 Gate

```text
full process-tree peak RSS <= 46.688503266 GiB
```

必须同时报告：

```text
packet producer peak
side basis/coarse construction peak
both-side retained state
outer Krylov peak
recovery peak
cold serial max
wall time
```

不同进程峰值取串行最大值，不相加；对象 bytes不能冒充RSS。

---

## 9. V6 条件研究：z-layer sweeping / hierarchical side elimination

### 9.1 为什么值得研究

h4 每个 side只有约132300 rows，但 exact factor NNZ约 `1.07e9`，说明通用 sparse LU产生
巨大 fill。当前 side是薄层、结构化 hexahedral区域，可能存在沿 z 的层状耦合结构。

V6-1 必须先完成 graph audit。记录：

```text
每个 z layer 的owned/global rows
same-layer NNZ
adjacent-layer NNZ
跨两层以上NNZ
block half-bandwidth
static-condensation后layer graph
```

### 9.2 进入原型的条件

只有满足以下结构信号，才允许 component prototype：

```text
same + adjacent layer NNZ fraction >= 95%
effective block half-bandwidth     <= 2
layer ordering deterministic       = true
```

若不满足，记录 `LAYER_SWEEPING_STRUCTURE_NOT_ESTABLISHED` 并停止该方向。

若满足，只允许在 reduced/h5或tiny authority上实现：

```text
layer Schur / sweeping action
or block cyclic reduction
```

component必须与 explicit side action relative error `<=1e-10`，并报告预测 fill、front size、
通信和内存复杂度。本 Review 不自动授权第二个 h4 full formal；是否把 sweeping提升为正式
candidate由下一轮review决定。

---

## 10. V6 条件研究：matrix-free channel K 与 modal Schur

streaming-W解决了 resident `W`，但旧 0.7 nm audit 的external channels约为16030。即使2 TB
能容纳部分 dense对象，dense K/LU 的 `O(N_channel^2)` 内存和 `O(N_channel^3)` 时间仍可能
成为 blocker。

当 factor-light side action至少通过 component numerical Gate 后，允许建立：

```text
q → Hq - D F^-1(Cq) 的 matrix-free K action
channel-space iterative solve
H/diagonal + low-rank port correction PC
matrix-free modal Schur action
batched multi-RHS side action
```

V6 只做5 nm authority或synthetic scaled component，不运行0.7 nm PDE。Gate：

```text
retained dense K reference available on 5 nm
matrix-free K action relative error <= 1e-10
no permanent trace-by-channel W
no dense K/LU in scalable profile
repeat/linearity <= 1e-10
memory complexity and channel scaling explicitly reported
```

若没有数值合格的 factor-light `F^-1` action，该阶段记为 blocked，不得用失败的 ILU0 action
生成虚假的 channel qualification。

---

## 11. side-response packet 的正确定位

exact factor可用于生成 hash-bound side response spool，帮助：

```text
validation
coarse-space holdout comparison
low-rank spectrum audit
```

但 V5-2 已表明单 side exact factor阶段约85 GiB，因此“先做 exact factor再退出进程”本身
不能满足46.69 GiB的全过程生产峰值目标。

所以：

```text
side-response packet = oracle / research infrastructure
side-response packet ≠ 50% memory production candidate
```

不得把离线 factor成本从正式 capacity结论中静默删除；只有明确的多次复用场景才可另行报告
amortized时间，峰值仍必须如实保留。

---

## 12. 6h / 8h 时间政策

所有 heavy process默认：

```text
timeout_seconds = 21600
```

以下阶段不得自动延长：

```text
packet producer
setup-only
factor construction
side component
layer graph audit
尚未进入outer solve的运行
```

只有完整 h4 outer iterative solve已经开始，且满足以下条件，才允许一次延长到总8小时：

```text
swap=0
RSS始终低于46.688503266 GiB
KSP reason仍为iterating
iteration持续增加且无NaN/Inf
最近90分钟至少4个true-residual checkpoint
r_max至少下降0.5 decade，或已低于5e-7且最近3个best-so-far严格下降
保守log10外推预计剩余时间<=7200 s
没有其他heavy job
```

8小时仍未通过必须停止。时间可以比direct长，但不能以突破50%内存线为代价。

---

## 13. 重型运行上限

```text
V6 post-compaction exact-side setup-only     <= 1
V6 exact-side full formal                    <= 1，且仅setup Gate通过
port/modal bottom nested component           <= 1 process
port/modal top component                     <= 1，且仅bottom通过
port/modal both-side setup-only               <= 1
port/modal full h4 formal                     <= 1
z-layer reduced component                    <= 1，条件执行
0.7 nm full PDE                              = 0
Full3D new heavy                             = 0
h5 sidecar rerun                             = 0
BLR additional profile                       = 0
generic fixed-budget additional run          = 0
```

nested rank 64/128/256/512必须在同一 component内完成，不得拆成四个独立 heavy campaign。

---

## 14. 立即停止条件

```text
source/input/packet/physical hash mismatch
swap > 0
absolute process-tree memory line reached
NaN/Inf或invalid KSP reason
exact-side setup >42.019652939 GiB
port/modal bottom rank512仍有mandatory residual >1e-2
bottom retained state >16 GiB或construction >22 GiB
both-side setup >42.019652939 GiB
candidate引入exact/global direct factor
training/holdout发生污染
需要改变M480、物理、geometry或threshold才能继续
8h仍未收敛
```

失败结果和受控停止必须保留，不得改阈值或重新选probe追求通过。

---

## 15. 测试与证据 Gate

heavy前至少完成：

```text
factor-only fresh setup wiring test
single-Schur sampled-column hash/repeat test
fixed/variable PC identity test
Petrov–Galerkin coarse formula tiny exact comparison
left/right basis biorthogonality test
training/holdout separation test
nested rank determinism test
owner-row basis MPI2/MPI4 ownership test
coarse E rank/condition/repeat test
no-exact-factor inventory test
layer graph ordering/count test
matrix-free K action tiny equivalence test（条件阶段）
packet/spool hash validation
input validate/dry-run
```

静态与回归：

```text
focused pytest
MPI2/MPI4 tiny fixtures
Ruff check
Ruff format --check on changed Python
compileall
check_benchmarks --no-write
compact JSON parse
Markdown links/fenced math/table columns
git diff --check
```

full repository pytest不是强制Gate；未运行必须写 `not_run`，不得声称CI或zero failures。

---

## 16. 必须创建或更新的证据

```text
outcomes/review_v6_inherited_audit.md
outcomes/v6_post_compaction_exact_side_setup.md
outcomes/v6_side_layer_graph_audit.md
outcomes/v6_port_modal_two_level_side_pc.md
outcomes/v6_both_side_setup.md                     # conditional
outcomes/v6_h4_hybrid_iterative_half_memory.md     # conditional
outcomes/v6_matrix_free_channel_modal.md           # conditional
outcomes/v6_0p7nm_hybrid_capacity.md
outcomes/test_summary.md
outcomes/summary.md
docs/development_progress.md
response_v7.md
```

compact records进入：

```text
benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/
```

raw factor、basis、matrix、field、timeline和大型response spool继续放在ignored artifact root。

---

## 17. Commit计划

```text
docs(task039): audit v6 half-memory hybrid baseline
bench(task039): measure post-compaction exact-side setup
bench(task039): audit side layer coupling graph
feat(task039): add port-modal petrov-galerkin side pc
bench(task039): qualify port-modal side components
bench(task039): measure two-side half-memory setup
bench(task039): run half-memory h4 hybrid candidate          # conditional
research(task039): prototype layer sweeping side action      # conditional
research(task039): add matrix-free channel modal action      # conditional
docs(task039): close v6 half-memory and 0p7nm results
```

不得把算法实现、多个heavy结果和最终文档混在一个不可审阅commit中。

---

## 18. response_v7.md 要求

最终response必须表格优先，并至少包含：

1. branch、reviewed HEAD、最终 HEAD、worktree和测试；
2. V6-1 fresh post-compaction setup measured结果；
3. exact-side是否关闭为oracle；
4. side layer graph统计与sweeping decision；
5. port/modal two-level的source family、left/right basis、rank、condition和holdout；
6. bottom/top/both-side setup RSS；
7. 完整h4 candidate的五residual、R/T/A、E/H、canonical、channel和wall；
8. 相对direct的真实saving，是否达到46.688503266 GiB；
9. 6h/8h policy是否触发；
10. matrix-free K/modal阶段的完成或blocked原因；
11. 0.7 nm / 2 TB更新后的measured/derived/predicted表；
12. negative、not_run、controlled_stop和deferred项；
13. ordinary defaults、Full3D和arbitrary-3D边界；
14. selective-merge建议，但不得请求或执行merge。

Codex完成后提交并推送同一分支，然后停止等待下一轮ChatGPT review。

---

## 19. 当前核心判断

我同意把“相对 Hybrid direct 至少节省 50% 内存”设为 Task39 下一阶段的正式战略目标。
原因不是追求一个漂亮百分比，而是：0.7 nm 会引入当前5 nm尚未完整承担的channel、mode、
coarse、recovery和生命周期增长；如果5 nm h4只能节省10%–20%，这条路线几乎没有工程
安全余量。

V5 已经证明：

```text
普通BLR压缩不可靠
普通低预算Krylov不够强
streaming-W在5 nm不是主峰修复
full exact side factor无法作为长期生产核心
```

因此 V6 的正确方向是：

```text
先实测已有compaction
→ exact-side不达半内存即退回oracle
→ 用port/modal-aware left/right coarse space替代full side factor
→ 以z-layer sweeping限制side fill
→ 以matrix-free K/modal action限制0.7 nm channel与M增长
```

只有同时满足“数值正确、物理正确、全过程RSS不超过46.6885 GiB、无full side/global
factor、可扩展对象有明确上界”，才能说当前5 nm Hybrid iterative开始具备面向0.7 nm的
真实研究价值。