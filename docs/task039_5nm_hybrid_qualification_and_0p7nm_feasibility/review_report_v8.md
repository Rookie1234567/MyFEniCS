# Task039 Review Report V8：Layer-aware side inverse 与 Hybrid iterative 下一内存极限

## 0. 审阅决定

```text
review                                  = Task039 Review Report V8
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 58866d6cdc24287e141ae1bcddbddc208c410045
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
primary_method_line                     = Hybrid direct authority + layer-aware Hybrid iterative research
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
matched_Hybrid_direct_reference_GiB     = 93.377006531
current_best_full_iterative_GiB         = 80.025856018
current_best_saving_percent             = 14.298113646
minimum_objective                       = full workflow peak strictly below direct
next_candidate_objective                = beat 80.025856018 GiB current iterative best
strongest_primary_target                = at least 50 percent saving vs direct
half_memory_target_GiB                  = 46.688503266
Full3D_new_heavy_run                    = forbidden
full_0p7nm_PDE                          = forbidden
Hybrid_direct_rerun                     = forbidden
exact_side_full_rerun                   = forbidden
Petrov_rank_above_512                   = forbidden
current_raw_source_Petrov_family        = closed
third_BLR_profile                       = forbidden
generic_ILU_or_budget_scan              = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_iterative_timeout_seconds   = 28800 total, one time only
response_required                       = response_v9.md
```

本 Review 接受 V7 的完整正结果，同时明确它的工程边界：

> 当前 exact-side Hybrid iterative 已经在同一 h4 Hybrid 方程下把完整工作流峰值从
> `93.377006531 GiB` 降到 `80.025856018 GiB`，节省 `14.298113646%`，数值、恢复和物理
> Gate 全部通过。这满足“iterative 必须低于 direct”的最低目标，但没有消除 full side
> sparse factor，也没有达到 20%–50% 的长期目标。

下一轮不再通过细调 GMRES、普通 ILU、BLR 或继续增加 Petrov rank 寻求小幅改善。V7 已经
给出新的结构性证据：静态凝聚后的 local side matrix `F` 在真实 z-layer 排列下严格只有
同层与相邻层耦合。V8 因此转向：

```text
full side factor
→ bounded layer-block factors
→ fixed forward/backward z-sweep
→ dynamic DtN Woodbury correction
→ conditional full Hybrid iterative
```

该方向直接消除“整侧一次性稀疏分解”的主要 blocker，并测量其真实内存—残差—时间极限。

---

## 1. V7 最终审阅

### 1.1 统一结果

| 路径 | 范围 | 数值/物理 | process-tree RSS | 当前裁决 |
|---|---|---|---:|---|
| h4 Hybrid direct | full workflow | own Gate pass | `93.377006531 GiB` | matched authority |
| V7 Lane A exact-side iterative | full workflow | 1 outer；五 residual、recovery、R/T/A、E/H、canonical、channels pass | `80.025856018 GiB` | lower-memory positive；14.298% saving |
| V7 Lane B streamed producer | component | basis packet/lifecycle pass | `11.630760193 GiB` | resource architecture positive |
| V7 Lane B streamed consumer | bottom component | rank64/128/256/512 residual fail | `23.038208008 GiB` | numerical negative |
| V7 Lane C graph-only | graph component | block pattern measured；无 solve | `not_measured` | structural evidence only |

V7 Lane A 是当前唯一完整、数值合格且低于 direct 的 h4 Hybrid iterative。其五项 residual：

```text
reported = 3.506501655e-10
global   = 2.869197459e-10
bottom   = 1.732041001e-11
top      = 2.660035326e-10
modal    = 5.776295397e-11
```

均通过 `5e-9` Gate；最终 bottom/top factor 从 `1/1` 清理为 `0/0`，swap 为零。

### 1.2 当前 exact-side 极限

Lane A 的关键阶段为：

```text
bottom F ready              = 23.195 GiB
bottom factor ready         = 49.313 GiB
bottom cleanup              = 45.386 GiB
top F ready                 = 51.298 GiB
top factor ready            = 79.464 GiB
top Woodbury ready / peak   = 80.026 GiB
modal Schur ready           = 76.742 GiB
outer KSP ready             = 76.938 GiB
```

因此当前峰值已经不是 outer Krylov 或 modal Schur 主导，而是两个完整 side factor 的重叠。
继续减少 restart、保留 W 与否或再压缩少量 Python/PETSc carrier，无法稳定达到 20%–50% 节省。

V8 将 Lane A 固定为：

```text
5 nm h4 numerical authority / oracle
current full-workflow iterative baseline
not a 0.7 nm production candidate
no rerun
```

### 1.3 当前 Petrov family 的正确关闭方式

V7 streamed producer/consumer 的内存架构是正结果，但其 raw-source coarse space 数值失败。
四级 worst mandatory residual 为：

```text
rank64  = 219.375773963
rank128 = 310.531296720
rank256 = 1143.092533433
rank512 = 1521.816092530
```

而 Gate 为 `1e-2`。增加 rank 不仅没有趋近通过，还整体恶化。V8 因此冻结：

```text
current raw traction/load-vector Z/Y family = closed
rank > 512                               = forbidden
same packet/source schedule rerun        = forbidden
```

这不否定 owner-row packet、ownership remap、streaming producer 或 Petrov action基础设施；这些
可在未来使用“side response / sweep-error response”作为 basis 时复用。但 V8 不自动开展新的
Petrov basis campaign。

---

## 2. V7 layer graph 对新方法的授权依据

独立 Lane C 对 bottom/top local static-condensed `F` 得到完全相同的真实结构：

| 指标 | measured value |
|---|---:|
| z layers | `6` |
| active rows | `132300` |
| owned CSR NNZ | `105038640` |
| same-layer NNZ | `75327840` (`71.7144091%`) |
| adjacent-layer NNZ | `29710800` (`28.2855909%`) |
| long-range NNZ | `0` |
| block half-bandwidth | `1` |

每层 rows：

```text
[28350, 20790, 20790, 20790, 20790, 20790]
```

这说明按真实 layer permutation，local FE matrix 可写为 block-tridiagonal：

```math
PFP^T=
\begin{bmatrix}
D_0 & U_0 & 0   & \cdots & 0\\
L_0 & D_1 & U_1 & \ddots & \vdots\\
0   & L_1 & D_2 & \ddots & 0\\
\vdots & \ddots & \ddots & \ddots & U_4\\
0 & \cdots & 0 & L_4 & D_5
\end{bmatrix}.
```

这里仅指 local FE/static-condensation `F`。external DtN 的低秩/global coupling 必须继续作为
独立 Woodbury correction 处理，不能把 layer bandwidth=1 误写成完整 side operator 也是带状。

---

## 3. V8 正式内存分级与推进标准

完整 workflow 仍以 matched direct 为唯一最低目标 baseline：

```text
B_direct       = 93.377006531 GiB
B_current_best = 80.025856018 GiB
```

| 分类 | full workflow peak | 解释 |
|---|---:|---|
| no saving / fail | `>=93.377006531 GiB` | 不低于 direct |
| lower-memory positive | `<93.377006531 GiB` | 满足用户最低要求 |
| current-best not beaten | `>=80.025856018` 且 `<93.377006531 GiB` | 正结果，但无新内存极限 |
| new iterative best | `<80.025856018 GiB` | V8 至少建立新的实测低点 |
| useful pass | `<=74.701605225 GiB` | 相对 direct 节省至少20% |
| strong pass | `<=65.363904572 GiB` | 至少30% |
| major pass | `<=56.026203919 GiB` | 至少40% |
| half-memory strategic pass | `<=46.688503266 GiB` | 至少50%，最强目标 |
| stretch pass | `<=37.350802612 GiB` | 至少60% |

任何完整、数值合格且低于 direct 的结果都必须保留；但 V8 新算法只有低于
`80.025856018 GiB` 才可称为新的内存极限。

---

## 4. V8-0：继承审计

Codex 拉取本 Review 后，第一项提交必须为 docs-only：

```text
docs(task039): audit v8 layer-aware hybrid baseline
```

创建：

```text
outcomes/review_v8_inherited_audit.md
```

至少记录：

```text
branch / HEAD / upstream / ahead-behind / worktree
response_v8、V7 compact record 与 raw hash identities
Hybrid direct 93.377006531 GiB baseline
Lane A 80.025856018 GiB current best
Lane B producer/consumer positive/negative boundary
Lane C six-layer graph identity
MemAvailable / swap / disk / ABI / MPI / threads
existing h4 selected-mode packet identity
existing exact bottom holdout spool identity
Full3D、direct/exact rerun、0.7 nm PDE、BLR、ordinary ILU scan均冻结
```

不得夹带 Python 修改或启动 heavy run。

---

## 5. V8-1：layer block operator 与重构 Gate

### 5.1 目标

先把 graph evidence 变成可施加的 block operator，而不是直接开始求解器调参。

实现进入可复用 `src/solvers/` 模块，不得只写在 benchmark runner 中。必须构造：

```text
layer permutation / inverse permutation
D_i = F[i,i]
L_i = F[i+1,i]
U_i = F[i,i+1]
```

允许基于已组装 local `F` 提取 block CSR；不得形成 dense layer square。

### 5.2 数学等价性

对至少8个固定、hash-bound complex vectors检查：

```math
Fv
\quad\text{vs}\quad
P^T F_{\mathrm{block}} Pv.
```

Gate：

```text
relative action error       <= 1e-12
row coverage                exact
NNZ partition sum           exact
long-range block count      = 0
block half-bandwidth        = 1
repeat error                <= 1e-13
linearity error             <= 1e-13
```

必须分别输出 bottom/top：

```text
rows and NNZ per D/L/U block
ownership ranges
block hashes
CSR bytes
construction and destroy markers
```

该阶段不得建立 side factor、QEP、modal Schur 或 outer KSP。

---

## 6. V8-2：layer-factor inventory 与固定 z-sweep family

### 6.1 方法解决什么问题

现有 exact-side 对整个 `132300 x 132300` side matrix做一次稀疏分解，产生约十亿级 factor
NNZ。layer-aware 方法只分解六个对角 layer blocks，并用相邻层 coupling 完成前向/后向传播。

它改变的流程是：

```text
full side LU
→ six bounded D_i factors
→ block forward/backward sweep
```

这不会自动成为 exact inverse，但可显著减少跨层消元产生的 fill-in。

### 6.2 冻结 primary sweep

令：

```math
F=D+L+U.
```

一次固定 double sweep 定义为：

```math
S_{FB}=(D+U)^{-1}D(D+L)^{-1}.
```

其中 `(D+L)^{-1}` 用 layer factors 从底到顶前向代入，`(D+U)^{-1}` 从顶到底反向代入。
该问题为 complex、lossy、non-Hermitian，因此不得将其称为 symmetric solver；这里只称
`forward-backward block sweep`。

为测量时间—残差极限，在同一组 factors、同一个 bottom component run 中只允许以下固定动作：

```text
J1  = one block-Jacobi apply                 # diagnostic
F1  = one forward block sweep                # diagnostic
FB1 = one forward-backward sweep             # primary
FB2 = two fixed defect-correction passes
FB4 = four fixed defect-correction passes
```

固定 defect correction：

```math
x_0=0,
\qquad
x_{k+1}=x_k+S_{FB}(r-Fx_k).
```

`1/2/4` 是冻结检查点，不得继续扩展到 `8/16/...`，也不得对 relaxation factor做扫描。

### 6.3 factor 与生命周期合同

允许：

```text
one sparse factor per D_i
six layer factors per side
sequential layer construction
fixed transpose/adjoint solve capability only when explicitly audited
```

禁止：

```text
full side exact factor
full Hybrid direct factor
nested variable inner KSP
materialized dense Schur complement
materialized global layer basis on every rank
```

必须记录：

```text
D_i rows / NNZ / factor NNZ / factor bytes
per-layer analysis/factor/solve wall
all-layer retained bytes per side
construction peak and retained peak
factor count before/after destroy
MPI ownership and replication
```

---

## 7. V8-3：bottom-only layer-sweep side component

### 7.1 side operator

bottom component 的 local FE inverse使用 V8 layer sweep；external DtN 继续使用现有 dynamic
Woodbury algebra：

```math
A_{\mathrm{side}}=F-CH^{-1}D.
```

在 5 nm bottom component 中允许 retained-W 只作为数值诊断，因为其容量不是当前主峰；但任何
both-side/full candidate 必须使用已经验证过等价性的 streaming/action-only W 路径，避免把
5 nm 特例固化为 0.7 nm 架构。

### 7.2 frozen probes

复用既有 hash-bound exact bottom holdout，不重新生成 full exact factor。探针至少包括：

```text
physical side RHS（若为零则标 degenerate）
modal traction positive
modal traction negative
external DtN coupling
fixed random repeat 0
fixed random repeat 1
```

对 J1/F1/FB1/FB2/FB4 分别报告：

```text
true residual
repeat and linearity
apply wall
layer solve count
peak/retained RSS
```

### 7.3 数值 Gate

第一个同时满足以下条件的 checkpoint作为 preferred bottom action：

```text
finite                              = true
repeat relative error               <= 1e-10
linearity relative error            <= 1e-10
all nondegenerate mandatory residual <= 1e-2
modal+/modal-/external residual      <= 1e-3
full side exact factor count         = 0
swap                                 = 0
```

如果 FB4 仍不通过，则本 family 的 bottom classification 为：

```text
LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4
```

不得静默增加 sweep count。

### 7.4 bottom resource Gate

为了有机会在 two-side/full workflow 中低于当前 `80.025856018 GiB`，bottom component要求：

```text
construction peak <= 45.0 GiB
retained apply state <= 30.0 GiB
```

分级记录：

```text
<=25 GiB  = half-memory-oriented bottom component
<=35 GiB  = useful bottom component
<=45 GiB  = conditional continuation
>45 GiB   = stop before top
```

数值或资源任一失败，top 均不得运行。

输出：

```text
outcomes/v8_layer_block_operator.md
outcomes/v8_layer_sweep_bottom.md
records/task039_v8_layer_sweep_bottom_*.json
```

---

## 8. V8-4：top、both-side setup 与完整 formal（条件执行）

### 8.1 top

只有 bottom preferred action 同时通过数值和资源 Gate 后，才运行一次 top component。top使用
同一 action identity、同一 sweep checkpoint和同一 factor policy，不允许为 top 单独调参。

若缺少 top exact holdout，允许一次独立 oracle producer：

```text
build exact top factor
→ write only frozen six response shards + hashes
→ destroy factor
→ process exits
```

该 producer只用于验证，不属于正式 candidate workflow；不得把它隐藏在 production 路径中。

### 8.2 both-side setup-only

bottom/top均通过后，运行一次 both-side setup-only：

```text
build bottom layer-sweep action
→ cleanup construction temporaries
→ build top layer-sweep action
→ cleanup construction temporaries
→ streaming Woodbury
→ modal Schur
→ outer KSP setup
→ cleanup
```

Gate：

```text
process-tree setup peak        <= 76.024563217 GiB
outer-ready resident RSS       < 76.024563217 GiB
full side exact factor count   = 0/0
layer factor inventory         complete
packet/QEP references released = true
swap                           = 0
```

`76.024563217 GiB` 为当前完整 iterative best 的95%，给 outer vectors、solution snapshot、recovery
和 telemetry保留约5%余量。超过该线，不运行完整 formal；只报告 component Pareto。

### 8.3 full h4 iterative formal

both-side setup通过后，只允许一次完整 formal：

```text
right GMRES if action is proven fixed linear
right FGMRES otherwise
restart = 30
max_it  = 4000
```

正式 Gate：

```text
reported/global/bottom/top/modal residual <= 5e-9
R/T/A/A_volume and closure                 pass
selected E/H                              pass
canonical active/full                     pass
normal flux                               pass
orders/powers/amplitudes                   pass
external keys and coordinates             exact
release-before-recovery                    pass
swap                                       = 0
```

资源按 §3 分级。只有 `<80.025856018 GiB` 才可称 `NEW_ITERATIVE_MEMORY_BEST`；即使只是低于
`93.377006531 GiB`，也必须保留为正结果。

---

## 9. V8-5：条件性的 matrix-free channel K component

0.7 nm 的 external channel inventory 可能达到约 `16030`。即使 side inverse 解决，显式 dense
`K` 与 LU 的时间复杂度仍可能不可接受。V8 在 layer-sweep bottom通过后，允许一个 h4 component
验证：

```math
Kq=Hq-D\,S_F(Cq),
```

其中 `S_F` 是冻结的 layer-sweep action。

必须：

```text
不形成 W
不形成 dense K 作为 candidate state
stream C/D batches
与 h4 existing dense-K authority在16个固定向量上比较
relative action error <=1e-10
repeat/linearity <=1e-10
记录每次 K action wall和RSS
```

该 component只证明 action algebra，不授权 0.7 nm PDE。若 side sweep未通过，V8-5为
`not_run`。

输出：

```text
outcomes/v8_matrix_free_channel_k.md
```

---

## 10. 时间政策

内存和数值正确性优先。所有 heavy 默认：

```text
timeout = 21600 s = 6 h
```

只有完整 outer iterative solve 在约5.5小时满足以下条件时，允许一次延长到总计8小时：

```text
swap = 0
RSS below direct baseline
KSP iteration still advancing
no NaN/Inf
recent true residual checkpoints show sustained decrease
estimated remaining convergence time <=2 h
```

component、factor setup、oracle producer、QEP、graph和尚未进入 outer solve 的运行不得延长。

V8 不要求比 direct 更快。必须报告：

```text
setup wall
per-layer factor wall
per-apply wall
sweep pass count
outer iterations
recovery wall
total wall
```

内存下降若以显著时间增加为代价，仍可作为正结果，但必须进入 Pareto 表。

---

## 11. 停止条件

立即停止当前 lane，并保存真实证据，当出现：

```text
ABI/complex128/MPI identity failure
input or physical hash mismatch
swap > 0
watchdog resource line reached
block reconstruction error >1e-12
long-range local-F block出现
layer factor cleanup不完整
mandatory side residual在FB4仍失败
bottom construction >45 GiB
both-side setup >76.024563217 GiB
NaN/Inf or nonlinearity/repeat failure
```

不得通过放宽 residual、增加 sweep次数、改变 M、网格、材料、MPI或 hard line来取得正结果。

---

## 12. 禁止事项

V8 明确禁止：

```text
新的 Full3D heavy run
Hybrid direct 或 exact-side Lane A rerun
完整 0.7 nm PDE
M480 之外的 M sweep
第三个 BLR profile
ordinary ILU0/ILU1/drop-tolerance scan
fixed-budget 64/128 scan
Petrov rank >512
原样重跑 V7 raw-source Petrov
改变物理、网格、角度、偏振、材料或 MPI8 formal identity
修改 ordinary/default solver
同时运行多个 heavy case
```

---

## 13. 测试与证据

代码阶段至少要求：

```text
block extraction/reconstruction unit tests
serial tiny block-sweep tests
complex non-Hermitian repeat/linearity tests
factor inventory and destroy tests
MPI2/MPI4 ownership tests
Woodbury integration tests
focused Task39 pytest
Ruff check / format-check / compileall
git diff --check
check_benchmarks.py --no-write
compact JSON / links / tables / fenced math
```

全仓 pytest 延续既有用户成本边界，可为 `not_run`，但不得称为 CI 或 zero failures。

所有正式记录必须绑定：

```text
source SHA
input and physical hashes
selected-mode packet hashes
MPI/threads/ABI
block and factor inventory
true residuals
process-tree RSS/PSS/USS and swap
wall-time decomposition
artifact hashes
measured/derived/not_run classification
```

---

## 14. 提交顺序

建议提交序列：

```text
V8-0 docs(task039): audit v8 layer-aware hybrid baseline
V8-1 feat(task039): add layer block side operator
V8-2 test(task039): cover layer block ownership and actions
V8-3 feat(task039): add fixed layer sweep side inverse
V8-4 bench(task039): record bottom layer sweep Pareto
V8-5 bench(task039): record top and both-side setup          # conditional
V8-6 bench(task039): record full layer-sweep hybrid result  # conditional
V8-7 feat/bench(task039): audit matrix-free channel K       # conditional
V8-8 docs(task039): close v8 layer-aware results
```

每个提交只包含一个阶段，不 amend、不强推、不删除负结果。

---

## 15. 交付文件

Codex 最终必须更新或创建：

```text
outcomes/review_v8_inherited_audit.md
outcomes/v8_layer_block_operator.md
outcomes/v8_layer_sweep_bottom.md
outcomes/v8_layer_sweep_top.md                  # conditional/not_run allowed
outcomes/v8_layer_sweep_both_setup.md           # conditional/not_run allowed
outcomes/v8_layer_sweep_full_result.md           # conditional/not_run allowed
outcomes/v8_matrix_free_channel_k.md             # conditional/not_run allowed
outcomes/v8_memory_residual_time_pareto.md
outcomes/summary.md
outcomes/test_summary.md
docs/development_progress.md
docs/development_model_registry.md
response_v9.md
compact records under case 103 records/
```

`response_v9.md` 必须明确：

```text
current HEAD / source SHAs / worktree / upstream
which conditional stages ran or did not run
first passing sweep checkpoint or FB4 negative
bottom/top/both/full resource and residual tables
whether 80.025856018 GiB current best was beaten
whether 20/30/40/50% tiers were reached
0.7 nm implications and unresolved blockers
tests actually run vs not_run
selective merge grouping
```

---

## 16. 合并边界

本 Review 不批准 merge。

潜在 production-generic 内容仍需下一轮逐 hunk 审查：

```text
layer permutation/block extraction utilities
fixed linear block action infrastructure
collective lifecycle/telemetry
matrix-free channel action utilities
```

以下默认 research-only 或 do-not-promote：

```text
case-specific layer factors and runners
未通过 residual Gate 的 sweep candidate
V7 raw-source Petrov negative family
BLR/fixed-budget negative campaigns
heavy raw artifacts
```

只有新的完整 formal 同时通过数值、物理、资源和生命周期 Gate，才可讨论其最小组件是否进入
selective merge manifest。

---

## 17. 最终技术判断

V7 已经回答了一个重要问题：

> 在当前 exact-side 架构中，Hybrid iterative 可以可靠地比 Hybrid direct 省内存，但实测只有
> `14.298%`；两个完整 side factors 是进一步下降的主障碍。

V8 要回答下一个问题：

> 利用真实的六层 block-tridiagonal local-F 结构，能否用 bounded layer factors 和固定 z-sweep
> 在保持 side residual 与完整物理正确性的同时，建立低于 `80.025856018 GiB` 的新极限，甚至
> 逐步达到20%–50%节省？

即使 V8 未达到50%，也必须测清：

```text
layer factor总量
最佳固定 sweep checkpoint
bottom/top真实 residual
both-side setup peak
完整 workflow最低点
时间代价
阻止进一步下降的下一 blocker
```

该结果将决定后续是继续 layer sweep、升级 hierarchical Schur/cyclic reduction，还是重新设计
response-based coarse correction。任何结论仍只属于固定 5 nm h4 Hybrid case；0.7 nm 正式 PDE
和任意三维资格继续保持 `not_run/not_established`。
