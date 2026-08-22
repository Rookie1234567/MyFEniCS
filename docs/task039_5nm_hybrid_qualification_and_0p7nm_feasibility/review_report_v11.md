# Task039 Review Report V11：双端 exact-response 消元与 response-based side PC

## 0. 审阅决定

```text
review                                  = Task039 Review Report V11
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = b4d4759e3cff670c2cc420146a5130fe957ad79b
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
matched_Hybrid_direct_reference_GiB     = 93.377006531
current_best_full_iterative_GiB         = 80.025856018
current_best_full_saving_percent        = 14.298113646
bottom_response_producer_peak_GiB       = 50.7548675537
bottom_response_payload_bytes           = 2034244800
minimum_full_workflow_objective         = strictly below 93.377006531 GiB
next_full_workflow_objective            = strictly below 80.025856018 GiB
useful_target_GiB                       = 74.701605225
major_target_GiB                        = 56.026203919
half_memory_target_GiB                  = 46.688503266
J1_inner_FGMRES_family                  = closed at 16-step stagnation
V9_original_SN2_SGS                     = closed
raw_load_vector_Petrov_family           = closed
current_frozen_holdout_compression      = generalization negative, not global noncompressibility proof
Hybrid_direct_rerun                     = forbidden
V7_exact_side_full_rerun                = forbidden
bottom_full_response_producer_rerun     = forbidden
Full3D_new_heavy_run                    = forbidden
full_0p7nm_PDE                          = forbidden
generic_ILU_BLR_budget_scan             = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_consumer_timeout_seconds    = 28800 total, one time only
response_required                       = response_v12.md
```

V10 已建立四项关键事实：

1. 三个 two-layer supernode 的 conventional 与 factor-only solve 均 finite，局部 residual 为
   `1e-12` 到 `5e-11`；V9 历史 `Inf/NaN` 的根因仍未建立，不能写成通用 MUMPS 或 MatSolve bug。
2. `SN2-J` 比 single-layer `J1` 强，但最坏 bare-`F` residual 仍为 `17.0879610640`，不能直接充当
   side inverse。
3. J1-preconditioned side FGMRES 在16步后 true residual 仍约 `0.997` 到 `0.999`，当前 family关闭。
4. bottom exact-response producer 已准确生成960个 modal responses：最大 residual
   `1.52248376596e-10`、峰值 `50.7548675537 GiB`、payload `2034244800 B`、factor `1 -> 0`、swap0。

V11 的主线因此改为：

```text
已有 bottom exact response
-> 生成 top exact response
-> 无 side factor 的双 packet consumer
-> 完整 recovery / physics
-> 固定案例压缩与 response-based factor-free coarse correction
```

该路线先建立5 nm低内存 exact authority。producer仍使用一个临时 exact side factor，所以即使成功也不是
0.7 nm production solver。

---

## 1. V10 最终分类

| 路径 | 范围 | 峰值 RSS | 正式结论 |
|---|---|---:|---|
| h4 Hybrid direct | full workflow | `93.377006531 GiB` | matched authority |
| V7 exact-side Hybrid | full workflow | `80.025856018 GiB` | 当前最好完整结果，节省14.298% |
| V10 SN2-J | bottom component | `27.0815505981 GiB` | finite/resource pass，side residual fail |
| V10 J1-inner-FGMRES | bottom component | `22.0071983337 GiB` | 16步停滞，family closed |
| V10 bottom response producer | bottom component | `50.7548675537 GiB` | exact response authority pass |
| V10 compression consumer | bottom component | `15.4776763916 GiB` | execution/resource pass，holdout generalization fail |

完整 workflow saving tier保持：

| saving | full-workflow upper bound | 当前状态 |
|---:|---:|---|
| 5% | `88.708156204 GiB` | reached |
| 20% | `74.701605225 GiB` | not reached |
| 30% | `65.363904572 GiB` | not reached |
| 40% | `56.026203919 GiB` | not reached |
| 50% | `46.688503266 GiB` | not reached |

当前950-column training / 10-column holdout压缩只能分类为：

```text
CURRENT_HOLDOUT_GENERALIZATION_FAIL
```

因为 rank512 时 `0/1/480/481` 四列误差约 `0.9673`。但训练 tail 已降到
`3.8908212468e-12`，因此不能据此声称全部960列不可压缩。V11 将固定案例 closed-set compression与
unseen-mode generalization分开审计。

---

## 2. Exact-response 数学身份

对 side `s in {bottom, top}`，以实际 assembled block identity 为权威，概念上写成：

```math
A_s u_s + B_s a = f_s.
```

定义：

```math
X_s=A_s^{-1}B_s,
\qquad
u_s^0=A_s^{-1}f_s.
```

这里公式中的 `u_s^0` 是 side physical-response solution。于是：

```math
u_s=u_s^0-X_s a.
```

正式代码不得照抄本文符号猜测正负号。必须从实际 block action、V7 exact-side authority与 sampled column
identity中推导 sign、order和normalization；任何不一致都在离线 audit停止。

每侧 packet必须包含：

```text
960 modal response columns
actual physical RHS response
independent zero-map validation
```

若某侧 actual physical RHS为零，manifest可以明确 alias physical与zero payload，但不得静默省略身份。

---

## 3. 执行顺序

```text
V11-0  inherited audit，docs-only
V11-1  bottom packet algebra/sign/order资格
V11-2  bottom全960列 closed-set compression + mode metadata
V11-3  top response pilot
V11-4  条件 top full response producer
V11-5  factor-free two-side packet consumer + 条件 recovery/physics
V11-6  条件 response-interpolatory bottom side PC
V11-7  条件 structured unseen-mode compression
V11-8  outcomes / Pareto / 0.7 nm implications / response_v12.md
```

重型作业严格串行。V11-1/2只读现有 packet和authority，不启动新 factor/PDE。top pilot通过后才运行
full top producer；full top通过并退出后才启动 consumer。

---

## 4. 通用 Gate

### 4.1 Producer

```text
process-tree peak                 <= 60 GiB
exact side factor ready/final     = 1 / 0
global Hybrid direct factor       = 0
producer/consumer overlap         = false
per-side packet payload           <= 16 GiB
swap                              = 0
QEP                               = 0
wall                              <= 21600 s
per-column true residual          <= 1e-9
```

已有 bottom producer禁止重跑。若 bottom packet hash、coverage或algebra identity失败，则停止等待新 review。

### 4.2 Factor-free consumer

```text
bottom exact factor               = 0
top exact factor                  = 0
global direct factor              = 0
QEP                               = 0
response access                   = owner-row mmap / streamed
consumer absolute hard stop       = 79 GiB
swap                              = 0
```

完整 workflow峰值：

```math
B_{workflow}
=
\max(B_{bottom\ producer},B_{top\ producer},B_{consumer}).
```

不得相加不同进程峰值，也不得只报告 consumer。

### 4.3 Full numerical/physics Gate

沿用 V7 exact-side正式 Gate：

```text
reported/global/bottom/top/modal true residual <= 5e-9
projection bottom/top/combined                  <= 1e-8
exact traction bottom/top                       <= 1e-8
R/T/A/A_volume delta vs matched direct          <= 1e-6
selected E / H relative L2                      <= 5e-3 / 1e-2
canonical active/full relative L2               <= 1e-5
power-weighted channel error                    <= 1e-4
external keys/order identity                    = exact
normal flux / orders / powers / amplitudes      = inherited Gate pass
all finite / swap                               = true / 0
```

新增 packet algebra Gate：

```text
sampled response equation residual              <= 1e-9
bottom/top Schur contribution relative error     <= 5e-9
modal amplitude relative difference              <= 5e-9
condensed trace relative difference              <= 5e-9
```

### 4.4 时间

producer不得自动延长。two-side consumer只有在 RSS<79 GiB、swap0、无NaN/Inf、linear Gate已通过或明确
持续下降、预计剩余不超过2小时，才允许一次从6小时延长到总计8小时。

必须分别报告：

```text
cold serial wall = bottom producer + top producer + consumer
reuse wall       = consumer only
```

---

## 5. V11-0：继承审计

第一项提交：

```text
docs(task039): audit v11 exact response full hybrid baseline
```

创建 `outcomes/review_v11_inherited_audit.md`，至少记录：

```text
branch / HEAD / upstream / worktree
review_report_v11.md identity
V7 full record/hash
V10 bottom response compact record/hash
bottom producer source SHA = dbc5e9bfdf9ad0520881caa168c7a27316d50f10
bottom manifest SHA256 = 1f4e8acaf278bde0d0d14a2a096335049ee988cdbc1b406bca4197918ff64a0e
selected-mode packet identity
input / physical_model / resolved-config hashes
MemAvailable / swap / disk / ABI / MPI / threads
93.377 / 80.026 / 50.755 GiB baselines
all forbidden routes
```

不得夹带 Python修改或heavy运行。

---

## 6. V11-1：bottom packet algebra资格

必须验证：

```text
960 indices完整唯一
每列与实际 B_bottom 的 mode key / branch / sign / normalization exact match
owner-row coverage / shape / dtype / hash exact
actual bottom physical RHS norm与身份
zero column能否合法代表 bottom physical response
```

若 bottom physical RHS非零，只允许以后生成一个单独 physical-response column，不得重跑960 modal columns。

离线 algebra checks：

1. 对冻结10个 sampled columns重算 `A_bottom X_j` 与真实 source；
2. streamed形成 bottom Schur contribution；
3. 与 V7 exact-side Schur authority或 sampled reconstruction比较；
4. 使用 V7 modal amplitude重构 bottom condensed trace；
5. 与 V7 bottom trace/selected reconstruction比较。

Gate：

```text
source identity exact
sampled equation residual                 <= 1e-9
Schur contribution error                  <= 5e-9
modal-amplitude action error              <= 5e-9
bottom trace error                        <= 5e-9
factor/QEP/PDE                            = 0/0/not_run
packet released                           = true
```

失败则停止 top/full，不自动翻转符号或重算 packet。

---

## 7. V11-2：closed-set compression 与 metadata

只读取全部960个非零 bottom responses，不设置 holdout。只做一次：

```text
owner-row TSQR
-> one small-R SVD / rank-revealing decomposition
-> all-column reconstruction
```

禁止 normal equations。必须报告：

```text
960 singular values
numerical rank
max per-column error <=1e-6 / 1e-8 / 1e-10 所需最小 rank
Frobenius、max、median、p95 error
branch/group max error
compressed payload、RSS、wall
```

分类：

```text
FIXED_CASE_CLOSED_SET_COMPRESSION_PASS_1E6 / FAIL
FIXED_CASE_CLOSED_SET_COMPRESSION_PASS_1E8 / FAIL
FIXED_CASE_CLOSED_SET_COMPRESSION_PASS_1E10 / FAIL
```

首次 full consumer必须使用未压缩 packet。

同时记录每列 metadata：

```text
positive/negative branch
mode/partner index
propagating/evanescent
attenuation or |beta| bucket
group/family
branch edge / singleton
```

必须解释旧 holdout `0/1/480/481`，但不得因其失败就直接塞回training并宣布泛化通过。

---

## 8. V11-3/4：top pilot 与 full producer

### 8.1 Pilot

固定 modal indices：

```text
0, 1, 2, 239, 240, 267, 478, 479,
480, 481, 482, 719, 720, 746, 958, 959
```

另含 actual top physical RHS 与 independent zero validation。manifest必须区分三类列。

Pilot Gate：

```text
all responses finite
residual <=1e-9
zero norm <=1e-13
projected full wall <=21600 s
projected payload <=16 GiB
peak <=60 GiB
factor 1->0
swap0
coverage/hash exact
```

### 8.2 Full top producer

pilot通过后只允许一次 full producer：960 modal + physical + zero。必须保存 column schedule、residual compact
history、packet hashes、factor lifecycle、RSS/swap/wall。producer退出并确认factor=0后才启动consumer。

---

## 9. V11-5：双 packet factor-free consumer

consumer必须：

```text
reuse selected-mode packet
load bottom/top response packets
fixed batch=32 streamed Schur contributions
assemble reduced 960x960 modal system
solve modal amplitudes
stream local packet columns to reconstruct side condensed traces
release packets
conditional recovery / postprocess / checker
```

不得重跑QEP，不得建立side factor或global augmented factor。允许960x960 dense LU，但必须记录rank、condition、
bytes和wall。

同一次 formal run先完成 modal solve、five residuals、algebra与resource checkpoint；全部通过后才继续
recovery/postprocess，不重复相同 solve。

完整分类：

| 分类 | workflow peak |
|---|---:|
| no improvement | `>=80.025856018 GiB` |
| new low-memory best | `<80.025856018 GiB` |
| 20% saving | `<=74.701605225 GiB` |
| 30% saving | `<=65.363904572 GiB` |
| 40% saving | `<=56.026203919 GiB` |
| 50% saving | `<=46.688503266 GiB` |

已有 bottom producer为 `50.7548675537 GiB`。若 top和consumer均不高于它，则派生 saving约45.645%；这是条件
预测，不是预先通过值。成功措辞只能是：

```text
5NM_FIXED_CASE_EXACT_RESPONSE_PACKET_FULL_HYBRID_PASS
```

不得写成0.7 nm、factor-free producer或arbitrary-3D pass。

---

## 10. V11-6：response-interpolatory bottom side PC

V11-1通过后才允许。设 `B` 为 modal source matrix，`X=A_side^{-1}B` 为 exact response。固定候选：

```text
M_resp r = X c + M_J1 (r - B c)
```

`c` 由 owner-row TSQR / small-R rank-revealing least squares得到；禁止 normal equations、drop tolerance或rank扫描。
J1只允许在这里处理 source-space补空间。

Gate：

```text
modal source interpolation error        <=1e-8
sampled/all modal residual              <=1e-8
zero/repeat/linearity                   <=1e-13 / 1e-10 / 1e-10
five frozen mandatory residual          <=1e-2
modal+/modal-/external                  <=1e-3
construction / retained                 <=45 / 30 GiB
exact/global factor                     =0/0
swap                                    =0
```

若只通过 modal/external而随机补空间失败，分类为：

```text
MODAL_SUBSPACE_RESPONSE_CORRECTION_PASS_RANDOM_COMPLEMENT_FAIL
```

不得进入完整 Hybrid。五项全部通过后，才允许一次 `M_resp`-preconditioned bottom FGMRES
`4/8/16/条件32`；不得再运行J1-alone。

---

## 11. V11-7：结构化 unseen-mode 泛化（条件）

仅当 closed-set达到 `1e-8` 且metadata足够时执行一次 deterministic stratified split。strata至少包含：

```text
branch
propagating/evanescent
attenuation bucket
group/family
edge/singleton status
```

singleton/edge可按metadata规则 exact-keep；每个非单例 stratum必须同时有training和holdout，不得把整个困难
family移入training。报告 exact-keep payload、compressed remainder rank和逐stratum holdout error。

必须分开分类：

```text
FIXED_CASE_CLOSED_SET_COMPRESSION_*
STRATIFIED_UNSEEN_MODE_GENERALIZATION_*
```

---

## 12. 0.7 nm 边界

即使 V11 full workflow通过，producer仍临时使用 exact sparse factor。它只建立：

```text
5 nm低内存 exact authority
solution-response oracle
packet/consumer architecture
response-based coarse-space evidence
```

0.7 nm前仍需解决：

```text
exact producer factor替代
O(N_side M) payload增长
matrix-free/iterative external K
modal Schur随M增长
QEP/mode扩展
跨mode与跨波长泛化
```

V11不得运行0.7 nm PDE，也不得把当前约2 GB packet线性外推为0.7 nm正式上界。

---

## 13. 测试、证据与提交

Focused tests至少覆盖：

```text
source/sign/order identity
packet hash/coverage/release
physical/zero separation
top pilot/full manifest
streamed Schur contribution
consumer no-factor inventory
conditional recovery
closed-set all-column reconstruction
response-interpolatory projection
```

新 helper需通过serial、MPI2、MPI4 tiny fixtures；正式h4仍为MPI8。还必须完成：

```text
Ruff check / format-check
compileall changed Python
focused pytest
MPI tiny
check_benchmarks --no-write
compact JSON/hash consistency
Markdown links/math/tables
git diff --check
```

full repository pytest/CI未运行时写 `not_run`。

必需文件：

```text
outcomes/review_v11_inherited_audit.md
outcomes/v11_bottom_packet_algebra.md
outcomes/v11_closed_set_response_compression.md
outcomes/v11_top_response_packet.md
outcomes/v11_two_side_packet_full_result.md
outcomes/v11_response_interpolatory_pc.md
outcomes/v11_structured_response_generalization.md
outcomes/v11_memory_residual_time_pareto.md
outcomes/v11_0p7nm_implications.md
outcomes/summary.md
outcomes/test_summary.md
docs/development_progress.md
response_v12.md
```

未运行的条件文件写 `not_run` 和原因。raw matrices、response shards、JSONL、fields、factors不得提交Git。

建议提交职责：

```text
docs(task039): audit v11 exact response full hybrid baseline
feat(task039): qualify response packet block algebra
feat(task039): add top response packet producer
feat(task039): add factor-free two-side packet consumer
feat(task039): add fixed-case response compression audit
feat(task039): add response-interpolatory side correction
record(task039): add v11 packet workflow evidence
docs(task039): close v11 exact response results
```

---

## 14. Stop conditions

发生以下任一项，停止依赖 lane并收口：

```text
bottom source/sign/order identity fail
top pilot residual/resource/hash fail
top producer >60 GiB、swap>0或超时
consumer出现side/global factor或QEP
consumer peak >=79 GiB
linear/physics Gate fail
packet algebra与V7不一致
response-interpolatory action NaN/Inf或source interpolation fail
```

禁止通过重跑bottom960列、修改M480/网格/材料、删除困难列、放宽residual、把component RSS写成full saving、
把closed-set写成unseen-mode generalization来绕过。

---

## 15. response_v12.md 必答问题

1. bottom 960列与实际 modal block的key/sign/order/normalization是否exact match？
2. bottom packet重构Schur contribution与trace solution的误差是多少？
3. closed-set在 `1e-6/1e-8/1e-10` 下最小rank是多少？
4. `0/1/480/481` 的mode metadata是什么？
5. top pilot/full的residual、RSS、wall、payload与factor lifecycle是多少？
6. top physical RHS是否非零，如何存储？
7. consumer是否完全没有side/global factor与QEP？
8. five residual、R/T/A、E/H、canonical、channels是否通过？
9. workflow peak、cold wall、reuse wall是多少？
10. 是否刷新80.026 GiB，达到哪个saving tier？
11. response-interpolatory PC的modal与random-complement结果是什么？
12. closed-set与unseen-mode generalization各自分类是什么？
13. 哪些可selective merge，哪些research-only，哪些不得promotion？
14. 对2 TB / 0.7 nm消除了哪个blocker，剩余哪些blocker？
15. top/full/compression/response PC/0.7 nm分别是pass、fail还是not_run？

完成所有未被stop condition阻断的阶段后，提交并推送同一分支，更新 `response_v12.md`，然后停止等待审阅。
未经新 review，不得开启新solver family、完整0.7 nm PDE或master合并。
