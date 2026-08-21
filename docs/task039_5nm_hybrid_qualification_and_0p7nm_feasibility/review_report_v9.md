# Task039 Review Report V9：Bare-F 诊断、Schur-aware layer solver 与低内存 side Krylov

## 0. 审阅决定

```text
review                                  = Task039 Review Report V9
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 72addb495b7b996c879ae0a8f3026ad32225e8fd
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
primary_method_line                     = Hybrid direct authority + low-memory Hybrid iterative research
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
matched_Hybrid_direct_reference_GiB     = 93.377006531
current_best_full_iterative_GiB         = 80.025856018
current_best_full_saving_percent        = 14.298113646
minimum_full_workflow_objective         = strictly below 93.377006531 GiB
next_full_workflow_objective            = strictly below 80.025856018 GiB
strongest_primary_target                = at least 50 percent saving vs direct
half_memory_target_GiB                  = 46.688503266
simple_J1_F1_FB_family                  = closed as production candidate
FB8_or_more_defect_corrections          = forbidden
current_raw_source_Petrov_family        = closed
Petrov_rank_above_512                   = forbidden
third_BLR_profile                       = forbidden
generic_ILU_or_budget_scan              = forbidden
Hybrid_direct_rerun                     = forbidden
exact_side_full_rerun                   = forbidden
Full3D_new_heavy_run                    = forbidden
full_0p7nm_PDE                          = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_outer_timeout_seconds       = 28800 total, one time only
response_required                       = response_v10.md
```

本 Review 接受 V8 的结构正结果和数值负结果：

- 六层 local `F` block operator 已经由真实 h4 assembly 重构并通过 action identity；
- 六个 layer diagonal factors 的 construction 峰值只有 `22.273887634 GiB`，没有 full-side 或 global direct factor；
- 但 `J1/F1/FB1/FB2/FB4` 到 FB4 仍远未通过真实 side residual，且 defect correction 呈明显发散趋势。

因此，下一轮不再继续增加 sweep 次数，也不把低 component RSS 误写成完整 solver 成功。V9 要回答两个更基础的问题：

1. layer sweep 是连 bare finite-element operator `F` 都近似不好，还是主要在与 DtN low-rank correction 组合后失效；
2. 能否用真正考虑层间 Schur 影响的 supernode / inner Krylov / low-rank Schur 表示，保留约 20–45 GiB 的 component 内存，同时取得可用的 side true residual。

这项工作直接针对最终 0.7 nm Hybrid 路线中的主要 blocker：

> 用 bounded layer/supernode factors 和可扩展迭代 action，替代随网格细化超线性增长的完整 side sparse factor。

---

## 1. V8 最终审阅

### 1.1 当前统一结果

| 路径 | 范围 | 数值/物理 | process-tree RSS | 当前角色 |
|---|---|---|---:|---|
| h4 Hybrid direct | full workflow | own Gate pass | `93.377006531 GiB` | matched authority |
| V7 Lane A exact-side iterative | full workflow | 1 outer；residual、recovery、R/T/A、E/H、canonical、channels pass | `80.025856018 GiB` | 当前最好完整 iterative；14.298% saving |
| V7 streamed Petrov | bottom component | rank64/128/256/512 residual fail | `23.038208008 GiB` | low-memory numerical negative |
| V8 layer block reconstruction | component | exact local-F action/graph identity pass | `15.069286346 GiB` | structural authority |
| V8 J1/F1/FB sweep | bottom component | all five candidates numerical fail | `22.273887634 GiB` | resource positive / numerical negative |

V8 的正式 bottom 结果为：

```text
J1 worst mandatory residual   = 45.2474734898
F1 worst mandatory residual   = 141.532433583
FB1 worst mandatory residual  = 1244.72825119
FB2 worst mandatory residual  = 52831.6545991
FB4 worst mandatory residual  = 2.0250579258646484e12
mandatory limit               = 1e-2
preferred modal/external limit = 1e-3
```

J1 的 repeat/linearity 通过，但 residual 仍差约四个数量级。随着 fixed defect correction 次数增加，residual、repeat/linearity error 和 channel `K` condition 同时恶化；FB4 的 `K` rank 已由296退化为55。该趋势已经足够关闭：

```text
FB8 / FB16
继续增加 defect-correction 次数
通过普通 damping 或 relaxation 做开放参数扫描
把 J1/F1 直接接入 top 或完整 Hybrid outer
```

### 1.2 V8 已建立的正结论

V8-1 已证明 local static-condensed `F` 在真实 z-layer 排列下严格为 block-tridiagonal：

```text
layer count            = 6
rows                   = 132300
NNZ                    = 105038640
same-layer NNZ         = 75327840
adjacent-layer NNZ     = 29710800
long-range NNZ         = 0
block half-bandwidth   = 1
```

因此失败不是漏块、错误层标签或 long-range FE coupling 导致。真正缺失的是：

> 消去前一层后，对当前层产生的 Schur-complement 修正没有被 `D_i^{-1}` 型简单 sweep 捕捉。

精确 block elimination 应满足：

```math
S_0=D_0,
\qquad
S_i=D_i-L_iS_{i-1}^{-1}U_{i-1}.
```

随后 forward/back substitution 使用 `S_i^{-1}`，而不是一直使用原始 `D_i^{-1}`。

### 1.3 当前最好完整工作流不变

V8 没有产生 top、both-side、outer、recovery 或 R/T/A，因此完整工作流的当前最好结果仍是 V7 Lane A：

```text
Hybrid direct              = 93.377006531 GiB
exact-side Hybrid iterative = 80.025856018 GiB
saving                     = 14.298113646%
```

正式 saving tier 保持：

| saving | full-workflow upper bound | 当前状态 |
|---:|---:|---|
| 0% | `93.377006531 GiB` | direct reference |
| 5% | `88.708156204 GiB` | reached |
| 20% | `74.701605225 GiB` | not reached |
| 30% | `65.363904572 GiB` | not reached |
| 40% | `56.026203919 GiB` | not reached |
| 50% | `46.688503266 GiB` | not reached |
| 60% | `37.350802612 GiB` | not reached |

---

## 2. V9 的关键数学边界

### 2.1 bare `F` 与完整 side operator 必须分开

本轮统一记：

```math
A_{\mathrm{side}} = F - C H^{-1}D,
```

其中：

- `F` 是 local FE/static-condensed operator；
- `C H^{-1}D` 是 external Fourier-DtN 的 low-rank/global correction；
- V8 的 layer graph 只证明 `F` 的 block bandwidth 为1，并不说明完整 `A_side` 仍是局部带状矩阵。

V8 直接用近似 `M≈F^{-1}` 构造 Woodbury side action，但没有独立报告：

```text
b - F M b
b - A_side M_side b
```

所以当前不能判断：

```text
layer sweep 本身对 F 已经很差
还是 F 近似尚有价值，但 approximate Woodbury 组合破坏了 side action
```

V9 必须首先关闭这个证据缺口。

### 2.2 fixed defect correction 已关闭

固定 defect correction 的误差传播形式为：

```math
e_{k+1}=(I-MF)e_k.
```

V8 的 FB1→FB2→FB4 实测表明该映射不是收缩。V9 不再计算更多 fixed powers，也不以调 relaxation 参数寻找偶然稳定点。

### 2.3 inner Krylov 与 Woodbury 必须保持数学身份清楚

若使用 inner GMRES/FGMRES，映射通常不再是一个固定、严格线性的 `M`，因此不得把它静默代入精确 Woodbury 公式并继续称为固定线性 side inverse。

V9 的 inner Krylov lane 必须直接求解完整 side equation：

```math
A_{\mathrm{side}}x=b,
```

layer/supernode action 只作为 inner preconditioner。若未来接入全局 Hybrid block-LDU，外层必须使用 `FGMRES`，并明确记录这是 variable/nonlinear side solve，而不是固定 Woodbury action。

---

## 3. V9 资源和数值 Gate

### 3.1 bottom component 资源线

```text
construction process-tree peak     <= 45 GiB
retained apply/solve state peak     <= 30 GiB
swap                                = 0
full-side exact factor count        = 0
全球/global direct factor count     = 0
ordinary defaults                   = unchanged
```

允许的因子只有：

```text
6 个 single-layer diagonal factors
或 3 个 two-layer supernode diagonal factors
```

所有因子必须记录 rows、NNZ、factor telemetry、setup wall、RSS marker，并在最终 cleanup 后回到0。

### 3.2 side numerical Gate

冻结的非退化 holdout 继续为：

```text
modal_traction_positive
modal_traction_negative
external_dtn_coupling
fixed_random_repeat_0
fixed_random_repeat_1
```

`physical_side_rhs` 若为零，只作 `degenerate_uninformative`。

完整 side solver 通过条件：

```text
finite                              = true
all mandatory true residual         <= 1e-2
modal+/modal-/external residual      <= 1e-3
repeat solution/residual error       <= 1e-8
KSP reason                           = positive，或在冻结预算边界恰好达到 residual Gate
NaN / Inf                            = absent
```

固定线性 action 另需：

```text
repeat relative error    <= 1e-10
linearity relative error <= 1e-10
```

inner FGMRES 是 solver 而不是固定线性 action，不用伪造 linearity pass；必须报告每个 RHS 的真实迭代数、residual history 和停止原因。

### 3.3 完整 workflow 仍使用分级目标

V9 默认先做 bottom component。只有以后形成完整 workflow 时才可比较：

```text
<93.377006531 GiB  = 低于 direct，最低正结果
<80.025856018 GiB  = 刷新当前 iterative 最低点
<=74.701605225 GiB = 至少节省20%
<=65.363904572 GiB = 至少节省30%
<=56.026203919 GiB = 至少节省40%
<=46.688503266 GiB = 至少节省50%，最强目标
```

任何 component 的20–30 GiB均不得冒充 full-workflow saving。

---

## 4. V9-0：继承审计

第一项提交必须为 docs-only：

```text
docs(task039): audit v9 schur-aware side baseline
```

创建：

```text
outcomes/review_v9_inherited_audit.md
```

至少记录：

```text
branch / HEAD / upstream / ahead-behind / worktree
review_report_v9.md identity
V7 exact-side full record/hash
V8 layer-block operator record/hash
V8 bottom sweep record/hash
frozen exact bottom spool catalog/hash
current h4 input / physical_model_sha256 / packet identity
MemAvailable / swap / disk / ABI / MPI / threads
current 93.377 / 80.026 GiB baselines
J1/F1/FB family closed
Full3D、direct rerun、exact-side rerun、0.7 nm PDE 均冻结
```

不得夹带 Python 修改或启动 heavy run。

---

## 5. V9-1：bare `F` 与完整 side residual 分离

### 5.1 目的

只回答：

> J1/F1 对 bare `F` 的近似到底有多差；approximate DtN/Woodbury 组合又增加了多少误差？

### 5.2 冻结对象

只重新评估：

```text
J1
F1
```

FB1/FB2/FB4 只读取既有 V8 raw/compact，不重新运行。

对五个冻结 holdout，分别输出：

```math
r_F(b)=\frac{\lVert b-FM_Fb\rVert}{\lVert b\rVert},
```

```math
r_A(b)=\frac{\lVert b-A_{\mathrm{side}}M_Ab\rVert}{\lVert b\rVert}.
```

同时记录：

```text
r_A / r_F amplification
F-action count
layer solve count
Woodbury C/D/H/K inventory
K rank/condition
repeat/linearity
每个阶段 wall 与 process-tree RSS
```

不得只输出一个 worst value；五个 label 必须逐项保留。

### 5.3 实现正确性 Gate

增加一个 tiny manufactured block-tridiagonal fixture：

```text
3–6 blocks
complex non-Hermitian
known dense direct inverse
serial / MPI2 / MPI4 ownership variants
```

必须验证：

```text
block reconstruction action error <=1e-12
J1/F1 formula matches explicit reference <=1e-12
repeat/linearity <=1e-12 on tiny fixture
```

若 h4 F1 的 repeat/linearity 仍高于 `1e-10`，先修复状态复用或浮点放大问题；不得将其误写为算法 residual 结论。

输出：

```text
outcomes/v9_bare_f_vs_full_side.md
compact record under case 103 records/
```

---

## 6. V9-2：Schur algebra fixture 与 two-layer supernode baseline

### 6.1 exact block-Schur 公式必须先在小规模成立

在 reusable `src/solvers/` 模块中实现或验证 exact block Thomas/Schur 递推：

```math
S_0=D_0,
```

```math
G_i=L_iS_{i-1}^{-1},
\qquad
S_i=D_i-G_iU_{i-1},
```

再执行对应 forward/back substitution。

在 tiny complex non-Hermitian fixture 上，与 monolithic direct solution 比较：

```text
solution relative error <=1e-12
true residual           <=1e-12
repeat/linearity        <=1e-12
serial/MPI2/MPI4        pass
```

这一步只证明 algebra，不能在 h4 上显式形成巨大稠密 `S_i`。

### 6.2 h4 three-supernode baseline

将六层固定分组为：

```text
SN0 = layers [0,1]
SN1 = layers [2,3]
SN2 = layers [4,5]
```

每个 supernode 内部的 diagonal 和相邻层 coupling 必须完整包含，并用一个稀疏 factor 求解。只允许两个固定线性候选：

```text
SN2-J   = three-supernode block Jacobi
SN2-SGS = one symmetric forward/backward supernode sweep
```

不得改变分组，不得扫描 overlap、drop tolerance 或 sweep count。

### 6.3 supernode Gate

```text
original F action reconstruction exact       = true
supernode row coverage                       = exact
full-side/global direct factor               = 0/0
supernode factor count ready/final           = 3/0
construction peak                            <=45 GiB
retained state                               <=30 GiB
swap                                         =0
repeat/linearity                             <=1e-10
```

五个 holdout 先只测 bare `F` residual。保留 J1、F1、SN2-J、SN2-SGS 的统一表格，选择 worst mandatory `r_F` 最低且稳定的 action，作为 V9-3 唯一 inner preconditioner。

即使 supernode baseline 未达到 `1e-2`，也不得直接判死；它的作用是提供比 single-layer J1 更强且仍低内存的 inner preconditioner。

输出：

```text
outcomes/v9_supernode_side_preconditioner.md
compact record under case 103 records/
```

---

## 7. V9-3：直接求完整 side operator 的 inner FGMRES

### 7.1 方法定位

本阶段不再用 approximate `F^{-1}` 构造一个假定精确的 Woodbury inverse，而是直接求：

```math
A_{\mathrm{side}}x=b.
```

使用 V9-2 选出的唯一稳定 layer/supernode action 作为 right preconditioner。

这解决的问题是：

```text
DtN low-rank coupling 由真实 A_side matvec处理
layer factor 只负责降低 inner Krylov 难度
不要求近似 M 满足精确 Woodbury 代数
```

### 7.2 冻结 inner budgets

同一 bottom component、同一五个 holdout，依次执行：

```text
FGMRES max_it = 4
FGMRES max_it = 8
FGMRES max_it = 16
```

只有当16步相对4步至少下降两个 decade、最近迭代仍持续下降且资源 Gate通过时，才允许一次：

```text
FGMRES max_it = 32
```

禁止64及以上，禁止 tolerance/restart/PC 参数扫描。每个 solve 使用零初值，保存 full explicit true residual history。

### 7.3 裁决

使用第一个通过 §3.2 side numerical Gate 的预算作为 preferred bottom solver。

若32步仍未通过：

```text
classification = LAYER_PRECONDITIONED_SIDE_FGMRES_NOT_REACHED_BY_32
```

随后停止 top/both/full，不得把 component 低内存写成 solver pass。

若通过，必须额外对冻结的10个 modal-Schur sampled columns执行 side solve，记录：

```text
每列 iterations / true residual / wall
median / p95 wall
预测960列单侧与双侧总时间
预测是否能在6h或条件8h内完成
```

这些是 derived time projections，不是 full run。

输出：

```text
outcomes/v9_layer_preconditioned_side_fgmres.md
outcomes/v9_side_solver_time_model.md
compact record under case 103 records/
```

---

## 8. V9-4：Schur-update compressibility audit（条件执行）

### 8.1 启动条件

仅在以下任一条件成立时执行：

```text
V9-3 到32步仍未通过，但 residual 随 Krylov budget稳定下降
或
V9-3 通过，但 sampled modal-column时间模型无法支持后续两侧构造
```

### 8.2 审计对象

从第一个真实 Schur update 开始：

```math
R_1=L_1D_0^{-1}U_0,
\qquad
S_1=D_1-R_1.
```

不得显式形成 dense layer-square `R_1` 或 `S_1`。使用固定 deterministic sketches：

```text
rank = 16 / 32 / 64
independent holdout vectors
complex non-Hermitian two-sided diagnostics where supported
```

必须记录：

```text
sketch/action wall
process-tree RSS
singular-value decay或等价压缩指标
holdout action relative error
small-core rank/condition
retained bytes
```

压缩 Gate：

```text
rank64 holdout action error <=1e-3
small core condition        <=1e12
construction peak           <=45 GiB
no dense layer-square matrix
```

若第一接口在rank64仍不满足，则：

```text
LOW_RANK_SCHUR_UPDATE_NOT_COMPRESSIBLE_AT_RANK64
```

并关闭该路线。不得继续更高 rank。

若第一接口通过，可在同一 component 中依次审计其余接口，但不得在 V9 内启动完整 Schur solver或full Hybrid formal；下一轮 review 再决定递归 Woodbury-Schur 表示。

输出：

```text
outcomes/v9_schur_update_compressibility.md
compact record under case 103 records/
```

---

## 9. top、both-side 与完整 formal 边界

V9 默认只要求 bottom side 形成可审阅的数值和资源结论。

若 V9-3 bottom side 通过，可条件运行一次 top side，必须使用完全相同的：

```text
supernode grouping
preconditioner identity
FGMRES budget
residual Gate
resource Gate
```

不得为 top 单独调参。

即使 bottom/top 都通过，V9 仍不自动运行完整 modal Schur 和 full Hybrid formal。必须先提交：

```text
10-column sampled time model
两侧 retained RSS envelope
预测960-column modal Schur wall
预测完整 setup是否可能低于80.025856018 GiB
```

然后停止等待下一轮 review。

因此 V9 中：

```text
full Hybrid iterative formal = not_authorized
matrix-free channel K        = not_authorized unless separate future review
0.7 nm PDE                   = forbidden
```

---

## 10. 时间与 watchdog

所有 heavy/component run 默认：

```text
timeout = 21600 s = 6 h
poll    = 0.25 s
swap    = 0 required
one heavy process tree at a time
```

V9 component 不自动延长到8小时。只有未来真正进入全局 outer iterative solve时，才可沿用一次性6h→8h延长规则：内存低于 direct、无NaN/Inf、true residual持续下降且预计两小时内完成。

达到资源 hard line时必须终止完整 process group；OOM kill 不构成合格停止。

---

## 11. 禁止事项

```text
重跑 Hybrid direct
重跑 V7 exact-side full formal
FB8 / FB16 或更多 fixed defect correction
普通 damping / relaxation 参数扫描
普通 ILU0/ILU1/drop tolerance sweep
第三个 BLR profile
Petrov rank >512
原样重跑 V7 raw-source Petrov
改变 p/h/M/MPI/物理/材料/external keys
运行新的 Full3D heavy
运行完整0.7 nm PDE
显式形成巨大 dense layer Schur matrix
未经 bottom Gate运行top/both/full
```

历史负结果、implementation failures、raw roots和compact records不得删除或覆盖。

---

## 12. 测试与证据

至少运行：

```text
new Schur/supernode focused serial tests
MPI2 / MPI4 tiny ownership/action tests
existing test_295 layer-block regression
Task39 launcher/watchdog focused tests
Ruff check
format-check
compileall
check_benchmarks.py --no-write
compact JSON parse/hash recomputation
Markdown links / tables / fenced math
git diff --check
```

正式测试必须绑定最终代码 SHA。没有运行全仓 pytest 或 GitHub Actions时，必须写：

```text
full repository pytest = not_run
CI = not_available / not_run
```

不得声称 zero failures 或 CI pass。

---

## 13. 要求的 outcomes 与 response

至少创建或更新：

```text
outcomes/review_v9_inherited_audit.md
outcomes/v9_bare_f_vs_full_side.md
outcomes/v9_supernode_side_preconditioner.md
outcomes/v9_layer_preconditioned_side_fgmres.md
outcomes/v9_side_solver_time_model.md
outcomes/v9_schur_update_compressibility.md          # conditional
outcomes/v9_top_side_boundary.md                     # conditional
outcomes/v9_memory_residual_time_pareto.md
outcomes/summary.md
outcomes/test_summary.md
docs/development_progress.md
docs/development_model_registry.md
response_v10.md
```

每个 outcome 必须区分：

```text
measured
derived
diagnostic
not_run
controlled_numerical_negative
resource_stop
implementation_failure
```

`response_v10.md` 必须回答：

1. bare `F` 和完整 `A_side` 的误差分别来自哪里；
2. three-supernode 是否显著改善 single-layer J1/F1；
3. full side FGMRES 的第一个通过预算是否存在；
4. bottom component 的实际最低内存、真实 residual 和时间是多少；
5. sampled modal columns 推导出的960列成本是否可接受；
6. Schur update 是否在rank64内可压缩；
7. 当前最好完整 workflow 是否仍为80.025856018 GiB；
8. 哪个 blocker 阻止20%或50% saving；
9. 哪些代码只属于research，不得提升ordinary default；
10. top/both/full/0.7 nm哪些项目仍为not_run。

---

## 14. 提交计划

建议按阶段提交，不 amend、不强推：

```text
docs(task039): audit v9 schur-aware side baseline
feat(task039): separate bare-F and full-side diagnostics
test(task039): qualify bare-F and side diagnostic contracts
feat(task039): add exact Schur fixtures and two-layer supernodes
test(task039): qualify supernode actions across MPI fixtures
feat(task039): add layer-preconditioned full-side FGMRES component
docs(task039): record v9 side solver evidence
feat(task039): audit low-rank Schur updates                 # conditional
docs(task039): close v9 side solver results
```

完成后提交并推送同一 Task39 分支，给出精确 HEAD、upstream、ahead/behind、工作树、测试和证据路径，然后停止等待审阅。不得合并 `master`。

---

## 15. 当前总判断

V8 已经把问题定位得更清楚：

```text
layer decomposition / memory structure = viable
simple D_i-based sweep                 = numerically inadequate
fixed defect correction               = divergent
full side factors                      = still the only qualified strong inverse
```

V9 的任务不是再找一个名字不同的简单 sweep，而是建立以下有明确数学身份的漏斗：

```text
bare-F / DtN error separation
→ stronger two-layer supernode preconditioner
→ direct full-side FGMRES
→ conditional Schur-update compressibility audit
```

只有这种路线才可能在不恢复 full side factor 的前提下，把当前14.3%的完整内存节省继续推进到20%、30%乃至50%，并为未来0.7 nm Hybrid计算建立可扩展 side inverse。