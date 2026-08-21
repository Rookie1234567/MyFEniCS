# Task039 Review Report V10：Supernode 因子取证、J1-inner-FGMRES 与 side-response packet

## 0. 审阅决定

```text
review                                  = Task039 Review Report V10
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 5b2830eaae589af5660f73df2f9ad4999ed527eb
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
V8_J1_F1_FB_as_direct_side_inverse      = closed
V9_SN2_original_rerun                   = forbidden
V9_SN2_SGS_rerun_before_SN2_J_integrity = forbidden
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
conditional_iterative_timeout_seconds   = 28800 total, one time only
response_required                       = response_v11.md
```

本 Review 接受 V9 的两个正式负结果，但纠正下一步的优先级：

1. `J1/F1` 对 bare finite-element operator `F` 本身已经很差，当前失败不能归因于 DtN；
2. `SN2-J/SN2-SGS` 对非零 RHS 产生 `Inf/NaN`，甚至零 RHS 也产生非有限输出；
3. 因此在继续研究更大 supernode、更多 sweep 或 inner Krylov 之前，必须先确定非有限输出来自：
   - supernode principal block 的真实奇异/近共振；
   - factor-only detached solve 路径；
   - gather/scatter、workspace 或 action 实现。

与此同时，V9 已经证明 `J1` 是 finite、固定、可重复且低内存的线性 action。虽然它不能单次近似
`A_side^{-1}`，仍可作为 full-side equation 的 inner Krylov preconditioner。V10 因此采用三条有明确
先后关系的 lane：

```text
Lane A = supernode factor-integrity forensic
Lane B = J1-preconditioned full A_side FGMRES
Lane C = exact side-response packet，作为低内存 authority 与 response-basis 数据源
```

Lane C 不是最终 0.7 nm production solver，因为 producer 仍临时使用一个 exact side factor；它的作用是：

- 在 5 nm 下进一步降低完整工作流的同时峰值；
- 获得真正的 `A_side^{-1}b` 解响应，而不是再次使用 raw load vectors 构造 coarse basis；
- 测量 response matrix 的可压缩性，为后续 factor-free side solver 提供正确 oracle。

---

## 1. V9 最终审阅

### 1.1 当前统一结果

| 路径 | 范围 | 数值/物理 | process-tree RSS | 当前角色 |
|---|---|---|---:|---|
| h4 Hybrid direct | full workflow | own Gate pass | `93.377006531 GiB` | matched authority |
| V7 Lane A exact-side iterative | full workflow | 1 outer；residual、recovery、R/T/A、E/H、canonical、channels pass | `80.025856018 GiB` | 当前最好完整 iterative |
| V9-1 J1 | bottom component | finite/repeat/linearity pass；worst `r_F=50.7689715097` | `23.8684272766 GiB` | low-memory Krylov-PC candidate |
| V9-1 F1 | bottom component | finite；worst `r_F=367.2128685567` | `22.1353225708 GiB` | numerical negative，关闭 |
| V9-2 SN2-J | bottom component | five mandatory outputs `Inf` | `22.81266403198 GiB` | factor/action integrity unresolved |
| V9-2 SN2-SGS | bottom component | five mandatory outputs `NaN` | same process envelope | 不得继续运行 |

V9-1 已经建立：

```text
J1 worst r_F = 50.7689715097
J1 worst r_A = 50.2410648372
F1 worst r_F = 367.2128685567
F1 worst r_A = 141.0763808200
```

因此主要 blocker 是 local FE side equation；DtN/Woodbury 没有放大 J1，对 F1 反而降低了相对残差，
但仍远高于 `1e-2`。

V9-2 已经建立：

```text
three supernode factors constructed = true
construction peak                   = 22.81266403198 GiB
swap                                = 0
factor lifecycle                    = 3 -> 0
full-side/global direct factor      = 0 / 0
SN2-J output                         = Inf
SN2-SGS output                       = NaN
```

### 1.2 零 RHS 非有限输出的审阅含义

任何固定线性 action `M` 都必须满足：

```math
M0=0.
```

V9-2 中零 RHS 同样得到非有限输出，因此当前不能把结果简单解释成“two-layer approximation 不够强”。
至少存在三种互斥解释：

```text
A. principal supernode block 自身奇异、近奇异或发生人工腔体共振；
B. conventional factor 正常，但 factor-only detached handle 不正确；
C. 每个 factor solve 正常，但组合 action 的 scatter/permutation/workspace 不正确。
```

V10 的第一任务是通过同矩阵、同 RHS、两种 solve 路径和逐阶段 finite marker 把 A/B/C 分开。
在该取证完成前：

```text
禁止扩大 supernode 层数
禁止加入 shift/damping 后扫参数
禁止重新运行 SN2-SGS
禁止把 SN2 当作 inner Krylov PC
```

### 1.3 当前完整工作流基线不变

```text
Hybrid direct               = 93.377006531 GiB
exact-side Hybrid iterative = 80.025856018 GiB
saving                      = 14.298113646%
```

正式 saving tier：

| saving | full-workflow upper bound | 当前状态 |
|---:|---:|---|
| 0% | `93.377006531 GiB` | direct reference |
| 5% | `88.708156204 GiB` | reached |
| 20% | `74.701605225 GiB` | not reached |
| 30% | `65.363904572 GiB` | not reached |
| 40% | `56.026203919 GiB` | not reached |
| 50% | `46.688503266 GiB` | not reached |
| 60% | `37.350802612 GiB` | not reached |

任何 20–30 GiB 的 bottom component 数字都不得冒充完整 workflow saving。

---

## 2. V10 的总执行顺序

```text
V10-0  inherited audit，docs-only
V10-1  tiny factor semantics 与 zero-map tests
V10-2  real h4 three-supernode factor-integrity forensic
V10-3  条件最小修复 + SN2-J 单候选复核
V10-4  J1-preconditioned full A_side inner FGMRES bottom ladder
V10-5  条件 top component 与 10-column modal cost model
V10-6  条件 exact side-response packet producer/compression pilot
V10-7  Pareto、0.7 nm implications、selective merge 与 response_v11.md
```

重型作业必须严格串行。任一阶段达到明确 stop condition 后，跳过依赖它的后续阶段，但仍完成证据收口。

---

## 3. 通用资源与数值 Gate

### 3.1 Factor-free / layer-PC bottom component

```text
construction process-tree peak <= 45 GiB
retained apply/solve state      <= 30 GiB
swap                            = 0
full-side exact factor count    = 0
global direct factor count      = 0
ordinary defaults               = unchanged
```

允许保留的 factor：

```text
6 个 single-layer factors
或经 V10-2 证明可用的 3 个 two-layer factors
```

### 3.2 Exact response producer

这是独立 oracle lane，允许一个 side exact factor，但禁止两侧 factor 同时驻留：

```text
producer process-tree peak      <= 60 GiB
producer exact side factor      = 1 at ready, 0 after process exit
producer global direct factor   = 0
consumer exact side factor      = 0
consumer retained peak          <= 30 GiB
per-side packet payload         <= 16 GiB
swap                            = 0
producer and consumer overlap   = false
```

该 60 GiB line 只属于隔离的 exact response producer，不得用于放宽 factor-free Lane A/B 的45 GiB line。

### 3.3 Frozen side RHS

非退化 mandatory labels：

```text
modal_traction_positive
modal_traction_negative
external_dtn_coupling
fixed_random_repeat_0
fixed_random_repeat_1
```

`physical_side_rhs` 输入范数为零时只作 `degenerate_uninformative`，但所有 candidate 对零输入仍必须：

```text
finite output = true
output norm   <= 1e-13 * max(1, operator scale contract)
```

### 3.4 Side solver Gate

```text
finite                                  = true
all mandatory true residual             <= 1e-2
modal+/modal-/external true residual     <= 1e-3
NaN / Inf                                = absent
swap                                     = 0
```

固定线性 action 还需：

```text
repeat relative error    <= 1e-10
linearity relative error <= 1e-10
```

FGMRES 是 solver，不伪造 linearity Gate；必须记录每个 RHS 的迭代数、true-residual checkpoints、KSP reason
和停止原因。

---

## 4. V10-0：继承审计

第一项提交必须为 docs-only：

```text
docs(task039): audit v10 side factor and response baseline
```

创建：

```text
outcomes/review_v10_inherited_audit.md
```

至少记录：

```text
branch / HEAD / upstream / ahead-behind / worktree
review_report_v10.md identity
V7 exact-side full record/hash
V9-1 bare-F/full-side record/hash
V9-2 supernode record/hash
frozen exact-bottom spool catalog/hash
h4 input / physical_model_sha256 / resolved-config identity
MemAvailable / swap / disk / ABI / MPI / threads
93.377006531 GiB direct baseline
80.025856018 GiB current iterative baseline
J1 finite/fixed status
F1/FB and original SN2-SGS closure
all forbidden heavy routes
```

不得夹带 Python 修改或启动正式 component/PDE。

---

## 5. V10-1：tiny factor semantics 与 zero-map tests

### 5.1 目的

在真实 h4 重跑前，先验证当前 PETSc/MUMPS ABI 中以下语义：

```text
conventional KSP/PREONLY/LU solve
factor-only MatSolve after KSP destroy
borrowed matrix release
zero RHS map
nonzero deterministic RHS residual
MPI ownership/scatter round-trip
```

### 5.2 Tiny fixtures

至少包含：

```text
1. nonsingular complex non-Hermitian block
2. deliberately singular complex block
3. 3-block tiny supernode system
```

在 serial、MPI2、MPI4 下检查：

```text
conventional solve residual
factor-only solve residual
zero input output norm
finite inventory
source/target ownership range
scatter parent -> block -> parent identity
factor destroy lifecycle
```

Nonsingular fixture Gate：

```text
conventional residual <= 1e-11
factor-only residual  <= 1e-11
conventional vs factor-only relative difference <= 1e-11
zero output norm <= 1e-13
all finite = true
```

Singular fixture 只能要求：

```text
failure is explicitly detected or nonfinite is explicitly classified
no silent pass
no fabricated residual
```

若 tiny nonsingular factor-only path 失败，停止所有 real h4 heavy，并先修复通用 factor semantics。

---

## 6. V10-2：真实 h4 supernode factor-integrity forensic

### 6.1 冻结对象

只运行 bottom，沿用 V9 三组：

```text
B0 = layers [0,1]
B1 = layers [2,3]
B2 = layers [4,5]
```

不得改变分组、加入 shift 或运行 SGS。

### 6.2 每组必须记录的矩阵证据

```text
rows / local-global ownership
NNZ / diagonal NNZ
matrix 1-norm / infinity-norm（若 API 可用）
finite values
zero-row / empty-row count
diagonal absolute min/max（若可稳定取得）
factor setup status
factor NNZ / factor matrix stats
MUMPS/PETSc rank, pivot, factor-error diagnostics（仅记录 ABI 实际可取得字段）
```

无法取得的字段必须写 `not_available`，不得猜测 MUMPS INFOG/RINFOG 含义。

### 6.3 两种 solve path 必须串行比较

对同一个 `B_j`、同一个 RHS，分别运行：

```text
Path A = matrix + KSP/PREONLY/PC LU/MUMPS
Path B = factor-only detached MatSolve
```

两条 path 不得同时保留 factor。每个 supernode 的 RHS：

```text
zero RHS
deterministic normalized random RHS
restricted modal-traction RHS
restricted external-coupling RHS
```

每次 solve 前必须显式清零：

```text
rhs / solution / temp / correction work vectors
```

必须报告：

```math
r_j=\frac{\lVert B_jx-b\rVert}{\max(\lVert b\rVert,10^{-30})},
\qquad
G_j=\frac{\lVert x\rVert}{\max(\lVert b\rVert,10^{-30})}.
```

非零 RHS Gate：

```text
finite x              = true
relative residual     <= 1e-9 for exact local factor
norm amplification G  = measured，not silently clipped
```

零 RHS Gate：

```text
finite x   = true
||x||      <= 1e-13
```

### 6.4 Scatter/action 边界

如果 Path A/B 的单块 solve 都通过，还必须单独检查：

```text
parent -> group gather -> parent reverse scatter round-trip
SN2-J zero input after all workspaces explicitly zeroed
SN2-J one-group-only input
SN2-J three-group deterministic input
```

### 6.5 决策树

| 取证结果 | 分类 | 后续动作 |
|---|---|---|
| Path A 与 B 都非有限/高残差 | `SUPERNODE_PRINCIPAL_BLOCK_UNSTABLE` | 关闭当前 principal-submatrix SN2；V10 不试 shift/damping |
| Path A 通过、B 失败 | `FACTOR_ONLY_DETACH_IMPLEMENTATION_FAILURE` | 允许最小修复 factor-only 路径 |
| A/B 单块均通过、scatter round-trip失败 | `SUPERNODE_SCATTER_LAYOUT_FAILURE` | 允许最小修复 ownership/scatter |
| A/B 与 scatter均通过、SN2-J失败 | `SUPERNODE_ACTION_WORKSPACE_FAILURE` | 允许最小修复 action/workspace |
| 全部通过 | `SUPERNODE_FACTOR_INTEGRITY_PASS` | 进入 V10-3 SN2-J 单候选复核 |

V10-2 只允许一次 authoritative h4 forensic heavy root；implementation failure 可以在同一阶段以一个最小修复
root 复核，但必须保留旧 root。

---

## 7. V10-3：条件最小修复与 SN2-J 单候选复核

只有 V10-2 明确定位到 factor-only、scatter 或 workspace implementation failure 时才允许修改。

允许修改：

```text
显式 workspace zeroing
正确的 factor/source/target Vec layout
scatter IS / ownership mapping
factor-only handle lifetime
错误 alias 或过早 destroy
```

禁止修改：

```text
supernode 分组
矩阵物理
shift / damping / Robin 参数
MUMPS profile
SGS 公式
residual Gate
```

修复后只运行：

```text
SN2-J
```

不得同时重跑 `SN2-SGS`。

SN2-J advancement Gate：

```text
all finite                         = true
zero-map Gate                      = pass
repeat/linearity                   <= 1e-10
worst bare-F residual              < 50.7689715097   # 必须优于 inherited J1
construction                       <= 45 GiB
retained state                     <= 30 GiB
swap                               = 0
```

只有 SN2-J 达到上述 advancement Gate，未来 review 才可考虑它作为 inner Krylov PC。V10 本轮不再运行 SGS。

若 V10-2 证明 principal block 本身不稳定，V10-3 直接 `not_run`；impedance/Robin/overlap local problem 留给
下一轮独立 review，不在本轮静默开发。

---

## 8. V10-4：J1-preconditioned full-side FGMRES

### 8.1 定位

J1 单次 action 的 residual 很差，但它满足：

```text
finite
fixed linear
repeat pass
linearity pass
low-memory construction
```

因此它可以作为 Krylov preconditioner，而不能继续冒充 `A_side^{-1}`。

本阶段直接求解：

```math
A_{\mathrm{side}}x=b,
\qquad
A_{\mathrm{side}}=F-CH^{-1}D.
```

使用 right-preconditioned FGMRES；J1 只作为 PC。不得把有限步 FGMRES action 代入“精确 Woodbury”并称为固定线性 inverse。

### 8.2 Frozen ladder

对五个 mandatory RHS 分别从零初值运行一个连续 solve，并在以下迭代点记录 full explicit true residual：

```text
0 / 4 / 8 / 16
```

只有满足下列趋势才允许继续到32：

```text
all RHS finite through iteration16
worst r16 < worst r8
worst r16 <= 0.5 * worst r4
no KSP breakdown / NaN / Inf
resource Gate remains pass
```

允许的最大预算仅为：

```text
4 / 8 / 16 / conditional 32
```

不得增加24、48、64或扫描 restart。

### 8.3 KSP contract

```text
KSP          = FGMRES
right PC     = fixed J1 layer action
restart      = 32
rtol         = diagnostic; official Gate uses explicit true residual
max_it       = 16 or conditional 32
initial guess = zero for each RHS
```

每个 RHS 必须记录：

```text
KSP reason
iterations
reported residual history
explicit true residual at checkpoints
J1 apply count
A_side apply count
wall time
RSS/PSS/USS when available
```

### 8.4 Bottom pass

使用第一个同时满足所有 side Gate 的 checkpoint作为 preferred budget。若到32仍不通过：

```text
classification = J1_INNER_FGMRES_NUMERICAL_LIMIT_NOT_REACHED_BY_32
```

并关闭本轮 top/both/full lane。

---

## 9. V10-5：条件 top 与 modal-column 成本模型

只有 bottom FGMRES 在统一 budget `k <=32` 通过，才允许：

```text
1. top side 使用完全相同的 k；
2. bottom/top 各运行10个冻结 modal columns；
3. 建立960-column modal-Schur成本外推。
```

冻结 sampled columns：

```text
0, 1, 240, 267, 479, 480, 481, 720, 746, 959
```

每列必须记录：

```text
side true residual
iterations
wall
J1 apply count
finite/KSP reason
```

只有 bottom/top 均通过且：

```text
projected 960-column build wall <= 21600 s per complete modal-Schur stage
both-side retained setup prediction < 80.025856018 GiB
```

才可创建 both-side setup-only route。V10 不授权完整 Hybrid formal；完成 both-side setup/cost evidence 后停止等待新 review。

---

## 10. V10-6：条件 exact side-response packet

### 10.1 激活条件

在以下任一条件成立时激活 Lane C：

```text
J1-inner-FGMRES 到32仍未通过；
或 sampled modal cost 外推超过6小时；
或 bottom通过但预测 full workflow不能刷新80.025856018 GiB。
```

### 10.2 目的和代数对象

对一个 side，producer 计算并保存：

```math
X=A_{\mathrm{side}}^{-1}B,
```

其中 `B` 至少包含：

```text
960 个 modal coupling RHS
1 个 physical/incident RHS（若非零）
必要的固定 validation columns
```

该 packet 保存的是**解响应列**，不是 raw traction/load vector。

### 10.3 Pilot

先运行 bottom 16-column pilot：

```text
10 个冻结 modal columns
3 个 modal/external holdout columns
2 个 deterministic random columns
1 个 physical RHS（若非零，否则替换为额外 modal column）
```

Pilot Gate：

```text
每列 exact side true residual <= 1e-9
owner-row shard coverage exact
packet hash/shape/dtype pass
producer peak <= 60 GiB
factor 1 -> 0 after producer exit
consumer reads packet with exact factor count 0
per-column wall extrapolation finite
projected full packet <=16 GiB
projected 961-column producer wall <=21600 s
```

### 10.4 Full bottom packet

Pilot 全部通过后，允许一次 full bottom response packet producer。必须：

```text
batch/stream columns，不保留全部 temporary Vec
owner-row sharded complex128 packet
factor process退出后才启动 consumer
packet manifest绑定 input/physical/source/factor/column identities
```

完成 full bottom packet后，运行 response compressibility audit：

```text
nested ranks = 64 / 128 / 256 / 512
training columns 与 holdout columns严格分离
报告 singular values / QR or SVD residual / holdout response error
```

本 Review 不授权 top full response packet或完整 Hybrid consumer。bottom packet与压缩结果完成后停止等待审阅。

### 10.5 解释边界

即使 bottom response packet和压缩通过，也只能称：

```text
5NM_EXACT_SIDE_RESPONSE_AUTHORITY_AND_COMPRESSION_EVIDENCE
```

不得称：

```text
0.7 nm production pass
factor-free side solver pass
arbitrary-3D pass
```

---

## 11. 时间、watchdog 与停止条件

所有 heavy 默认：

```text
timeout = 21600 s
swap    = 0
one heavy job at a time
process-group watchdog required
```

只有已经进入 V10-4 FGMRES 且满足以下条件时，允许一次延长至总计8小时：

```text
RSS below route hard line
all values finite
iteration/checkpoint继续推进
最近两个 true-residual checkpoint持续下降
外推剩余时间 <=2小时
```

以下不得延长：

```text
factor forensic
response producer
factor setup
packet/compression audit
未开始 iterative solve 的运行
```

达到 hard memory line时完整终止进程组；OOM kill不是合格停止。

---

## 12. 测试要求

代码阶段必须完成：

```text
focused serial tests
MPI2 / MPI4 tiny factor/scatter tests
zero-map tests
factor-only vs conventional solve tests
launcher/watchdog/status tests
Ruff check
format check
compileall
check_benchmarks --no-write
git diff --check
```

正式 result closeout：

```text
compact JSON parse
raw hash recomputation
status-independent Gate recomputation
Markdown relative links
fenced math
consistent table columns
```

Full repository pytest/CI除非用户另行要求，保持 `not_run`；不得声称CI通过。

---

## 13. 必须生成的 evidence

至少创建：

```text
outcomes/review_v10_inherited_audit.md
outcomes/v10_supernode_factor_integrity.md
outcomes/v10_j1_inner_fgmres.md
outcomes/v10_side_response_packet.md              # 条件
outcomes/v10_memory_residual_time_pareto.md
benchmarks/.../records/task039_v10_supernode_factor_integrity_v1.json
benchmarks/.../records/task039_v10_j1_inner_fgmres_v1.json
benchmarks/.../records/task039_v10_side_response_packet_v1.json  # 条件
response_v11.md
```

未运行的条件文件可以创建边界页，但必须明确写 `not_run` 和停止原因，不得放占位词。

---

## 14. Response V11 必须回答

`response_v11.md` 必须明确回答：

1. `Inf/NaN` 首次出现于 conventional factor、factor-only、scatter还是组合 action？
2. 三个 principal supernode是否存在可测的奇异/近共振证据？
3. 零 RHS 是否在所有单块和组合路径严格映射为零？
4. 是否发生了最小实现修复，修复前后 raw root分别是什么？
5. J1-inner-FGMRES 在4/8/16/32的每个 RHS true residual是多少？
6. bottom首个通过 budget是否存在？
7. top和10-column modal cost model是否运行，结果是什么？
8. response-packet lane是否激活；pilot/full packet的RSS、时间、payload和残差是什么？
9. 当前最佳完整 workflow是否仍为 `80.025856018 GiB`？
10. 当前达到20%和50% saving的主要 blocker是什么？
11. 哪些代码是 reusable infrastructure、research-only或do-not-promote？
12. top/both/full/0.7 nm哪些明确为 `not_run`？

---

## 15. Selective merge 边界

### 可候选 production-generic，仍需逐 hunk审阅

```text
zero-map / factor-integrity diagnostics
status-independent resource/Gate checker
owner-row packet/hash/lifecycle utilities
generic scatter round-trip tests
```

### Research-only

```text
real h4 supernode forensic route
J1-inner-FGMRES side component
exact response packet producer/compression audit
```

### Do not promote

```text
V8 J1/F1/FB direct-inverse candidates
V9 original SN2-J/SN2-SGS numerical-negative route
任何未通过的 response compression candidate
raw heavy artifacts
```

ordinary/default solver不得改变。未经后续 final review与用户授权，不得merge master。

---

## 16. 最终审阅边界

V9 已经把主要问题从“DtN可能破坏 layer inverse”缩小为“bare `F` 的低内存 inverse不够强”；但
SN2 的零输入非有限输出还没有被正确归因。V10 的优先级必须保持：

```text
先证明 factor/action语义正确
→ 再使用有限且稳定的J1作为Krylov PC
→ 若Krylov成本或数值仍不合格，再生成真正的exact solution-response packet
```

当前核心判断：

> 简单的层对角或固定 sweep不能直接替代 `F^{-1}`；但低内存 layer action仍可能作为 Krylov PC。
> 若 Krylov 仍不能以可接受成本通过，逐 side、逐进程生成 exact response packet，是5 nm下最有希望
> 进一步降低完整同时峰值并建立正确 response-basis oracle的路线。它不是0.7 nm最终解法，但能明确
> 测出下一阶段需要压缩和替代的对象。
